"""Auto-calibrate the tuning thresholds so you don't guess.

Three calibrators:

  classifier (offline) — analyzes your recorded dataset with leave-one-out:
      for every sample, how far is its nearest same-label neighbour (genuine)
      vs nearest other-label neighbour (impostor)? A good `max_distance` sits
      above genuine matches but below impostors. `min_confidence` is then set to
      separate correct LOO predictions from wrong ones. No camera needed.

  mouse (live) — you hold the mouse gesture with fingers apart, then pinched;
      `pinch_threshold` is placed in the gap between the two distance clusters.

  voice (live) — measures your mic's noise floor vs speaking level and puts
      `energy_threshold` between them (for parallel/always-listen mode).

Each prints a suggestion; pass --apply to write it into gestures.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from .classifier import PoseClassifier, vote_from_distances
from .fsutil import atomic_write_text


def _pct(arr, q):
    return float(np.percentile(arr, q)) if len(arr) else float("nan")


# ----------------------------------------------------------------- classifier
def calibrate_classifier(dataset_path, k: int = 5) -> tuple[dict, str]:
    clf = PoseClassifier.load(dataset_path, k=k)
    V, labels = clf.vectors, clf.label_list
    n = len(labels)
    if n < 4:
        return {}, "Not enough samples to calibrate (record a few gestures first)."

    labels_arr = np.array(labels)
    genuine, impostor = [], []
    for i in range(n):
        d = np.linalg.norm(V - V[i], axis=1)
        same = (labels_arr == labels[i])
        same[i] = False
        if same.any():
            genuine.append(float(d[same].min()))
        diff = ~(labels_arr == labels[i])
        if diff.any():
            impostor.append(float(d[diff].min()))

    g95, i05 = _pct(genuine, 95), _pct(impostor, 5)
    # Hug the genuine distribution (accept real poses with a small margin), and
    # use the midpoint-to-impostor only as a ceiling so a far-apart class set
    # doesn't loosen the gate and invite false fires from random hand shapes.
    base = g95 * 1.3
    if np.isnan(i05):
        max_distance, sep = base, "single label — gate from genuine only"
    elif g95 < i05:
        max_distance = min(base, (g95 + i05) / 2)
        sep = "clean separation"
    else:
        max_distance = base
        sep = "genuine/impostor overlap — leaning toward accepting genuine"
    max_distance = round(float(np.clip(max_distance, 0.1, 2.0)), 3)

    # Leave-one-out predictions at this max_distance → confidence separation.
    correct_conf, wrong_conf, n_unknown = [], [], 0
    for i in range(n):
        d = np.linalg.norm(V - V[i], axis=1).copy()
        d[i] = np.inf
        pred = vote_from_distances(labels, d, k, max_distance)
        if pred.label is None:
            n_unknown += 1
            continue
        (correct_conf if pred.label == labels[i] else wrong_conf).append(pred.confidence)

    if wrong_conf:
        cand = (_pct(wrong_conf, 90) + _pct(correct_conf, 10)) / 2
        min_confidence = max(cand, _pct(wrong_conf, 90) + 0.02)
    else:
        min_confidence = _pct(correct_conf, 5) - 0.02 if correct_conf else 0.7
    min_confidence = round(float(np.clip(min_confidence, 0.5, 0.9)), 2)

    total_pred = len(correct_conf) + len(wrong_conf)
    acc = len(correct_conf) / total_pred if total_pred else 0.0
    counts = clf.counts()
    thin = [f"{l}({c})" for l, c in counts.items() if c < 15]

    report = (
        "Classifier calibration (leave-one-out over {n} samples, {labels} labels)\n"
        "  genuine dist  p50={g50:.3f}  p95={g95:.3f}\n"
        "  impostor dist p5={i05:.3f}   p50={i50:.3f}    [{sep}]\n"
        "  LOO accuracy  {acc:.0%}   (unknowns: {unk})\n"
        "  -> max_distance  = {md}\n"
        "  -> min_confidence = {mc}"
    ).format(
        n=n, labels=len(counts), g50=_pct(genuine, 50), g95=g95,
        i05=i05, i50=_pct(impostor, 50), sep=sep, acc=acc, unk=n_unknown,
        md=max_distance, mc=min_confidence,
    )
    if thin:
        report += f"\n  ⚠ few samples for: {', '.join(thin)} — record ~60 each for best results."

    return {"max_distance": max_distance, "min_confidence": min_confidence}, report


# ---------------------------------------------------------------------- mouse
def calibrate_mouse(camera_index: int, mouse_gesture: str | None = None) -> tuple[dict, str]:
    import cv2
    from .camera import Camera, banner, draw_landmarks, to_rgb
    from .landmarks import HandDetector
    from .mouse import MouseController

    detector = HandDetector(max_hands=1)
    open_d, pinch_d = [], []
    phase_open = phase_pinch = 0.0
    print("Mouse calibration: 'O' = sample fingers APART, 'P' = sample PINCHED, Q = done.")

    try:
        with Camera(camera_index) as cam:
            while True:
                frame = cam.read()
                if frame is None:
                    continue
                hand = (detector.detect(to_rgb(frame)) or [None])[0]
                now = time.monotonic()
                d = None
                if hand is not None:
                    draw_landmarks(frame, hand.landmarks)
                    d = MouseController._pinch_distance(hand)
                    if now < phase_open:
                        open_d.append(d)
                    if now < phase_pinch:
                        pinch_d.append(d)
                banner(frame, [
                    f"pinch-dist: {d:.3f}" if d is not None else "no hand",
                    f"OPEN samples: {len(open_d)}   PINCH samples: {len(pinch_d)}",
                    "O=apart  P=pinch (1.5s each)  Q=done",
                ])
                cv2.imshow("handsign — calibrate mouse", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("o"):
                    phase_open = now + 1.5
                elif key == ord("p"):
                    phase_pinch = now + 1.5
                elif key in (ord("q"), 27):
                    break
    finally:
        detector.close()
        cv2.destroyAllWindows()

    if len(open_d) < 5 or len(pinch_d) < 5:
        return {}, "Mouse calibration skipped (need samples of both apart & pinched)."
    p_hi, o_lo = _pct(pinch_d, 95), _pct(open_d, 5)
    threshold = round(float(np.clip((p_hi + o_lo) / 2, 0.1, 2.0)), 3)
    warn = "" if _pct(pinch_d, 50) < _pct(open_d, 50) else \
        "\n  ⚠ pinched not clearly closer than open — re-record with a bigger gap."
    report = (
        "Mouse pinch calibration\n"
        f"  pinched dist p50={_pct(pinch_d,50):.3f} p95={p_hi:.3f}\n"
        f"  open    dist p5={o_lo:.3f} p50={_pct(open_d,50):.3f}\n"
        f"  -> pinch_threshold = {threshold}{warn}"
    )
    return {"pinch_threshold": threshold}, report


# ---------------------------------------------------------------------- voice
def calibrate_voice() -> tuple[dict, str]:
    from .audio import AudioCapture

    cap = AudioCapture()
    cap.start()

    def sample(seconds: float) -> list[float]:
        vals, end = [], time.monotonic() + seconds
        while time.monotonic() < end:
            vals.append(cap.rms)
            time.sleep(0.1)
        return vals

    try:
        input("Voice calibration — stay SILENT, then press Enter...")
        noise = sample(2.0)
        input("Now SPEAK normally (a sentence or two), press Enter to start...")
        speech = sample(3.0)
    finally:
        cap.stop()

    noise_floor, speech_level = _pct(noise, 95), _pct(speech, 30)
    threshold = round(float(np.clip(max(noise_floor * 1.6, (noise_floor + speech_level) / 2),
                                    0.003, 0.2)), 4)
    warn = "" if speech_level > noise_floor * 1.5 else \
        "\n  ⚠ speech not much louder than noise — move closer to the mic."
    report = (
        "Voice energy calibration\n"
        f"  noise floor p95 = {noise_floor:.4f}\n"
        f"  speech level p30 = {speech_level:.4f}\n"
        f"  -> energy_threshold = {threshold}{warn}"
    )
    return {"energy_threshold": threshold}, report


# ----------------------------------------------------------------- apply
def apply_to_config(config_path, classifier=None, mouse=None, voice=None) -> None:
    path = Path(config_path)
    raw = json.loads(path.read_text()) if path.exists() else {}
    settings = raw.setdefault("settings", {})
    if classifier:
        settings.update(classifier)
    if mouse:
        settings.setdefault("mouse", {}).update(mouse)
    if voice:
        settings.setdefault("voice", {}).update(voice)
    atomic_write_text(path, json.dumps(raw, indent=2))
    print(f"✓ wrote calibrated values to {path}")

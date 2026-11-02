"""Record mode — capture labeled samples of a hand pose for the classifier.

Usage is driven from the CLI. You hold a pose; press SPACE to capture a burst
of samples (small natural variation makes the KNN robust); repeat from a few
angles/distances; press Q when done. Samples append to the dataset file.
"""

from __future__ import annotations

import time
from pathlib import Path

import cv2

from .camera import Camera, banner, draw_landmarks, to_rgb
from .classifier import PoseClassifier
from .features import extract_features
from .landmarks import HandDetector


def record(
    label: str,
    dataset_path: str | Path,
    camera_index: int = 0,
    burst: int = 15,
    burst_interval: float = 0.05,
    target: int = 60,
) -> None:
    clf = PoseClassifier.load(dataset_path)
    detector = HandDetector(max_hands=1)
    captured = clf.counts().get(label, 0)
    last_capture = 0.0
    capturing_until = 0.0

    print(f"Recording '{label}'. SPACE = capture burst, Q = save & quit.")
    print(f"Existing samples for '{label}': {captured}. Target ~{target}.")

    with Camera(camera_index) as cam:
        while True:
            frame = cam.read()
            if frame is None:
                continue
            hands = detector.detect(to_rgb(frame))

            now = time.monotonic()
            hand = hands[0] if hands else None
            if hand is not None:
                draw_landmarks(frame, hand.landmarks)

            # Bursting: capture one sample every burst_interval while active.
            if hand is not None and now < capturing_until and (now - last_capture) >= burst_interval:
                clf.add_sample(label, extract_features(hand))
                captured += 1
                last_capture = now

            status = "CAPTURING" if now < capturing_until else "ready"
            color = (0, 165, 255) if now < capturing_until else (0, 255, 0)
            banner(frame, [
                f"label: {label}   samples: {captured}/{target}",
                f"[{status}]  SPACE=burst  Q=save+quit",
                "no hand detected" if hand is None else f"hand: {hand.handedness}",
            ], color=color)

            cv2.imshow("handsign — record", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(" "):
                if hand is not None:
                    capturing_until = now + burst * burst_interval
            elif key in (ord("q"), 27):
                break

    detector.close()
    clf.save(dataset_path)
    print(f"Saved. '{label}' now has {clf.counts().get(label, 0)} samples.")
    print(f"All labels: {clf.counts()}")

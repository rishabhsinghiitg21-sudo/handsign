"""HandsFreeEngine — fuses gestures + voice + mouse into one input layer.

Main thread runs the camera loop (must own the GUI window on macOS): detect a
hand, classify the pose, then dispatch by the pose's *role*:

  - mouse gesture   -> drive the cursor (fingertip) + pinch-to-click
  - scroll gesture  -> vertical hand motion scrolls
  - push-to-talk    -> hold to record the mic; release submits the audio for
                       transcription, routed as dictation or command
  - anything else   -> normal pose action (key/text/shell) + sequence combos

Background threads (owned by their services):
  - mic capture (sounddevice callback)
  - parallel VAD segmenter (optional, "always_listen")
  - transcription worker (faster-whisper)

The transcription worker routes results via VoiceRouter; combined bindings read
the gesture held at capture time from a shared snapshot.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import cv2
import numpy as np

from .actions import Action, dispatch
from .audio import AudioCapture
from .camera import Camera, banner, draw_landmarks, to_rgb
from .classifier import PoseClassifier
from .config import Config
from .features import extract_features
from .landmarks import HandDetector, WRIST
from .mouse import MouseController
from .sequences import SequenceDetector
from .speech import Transcriber, TranscriptionService
from .voice import VoiceRouter


class HandsFreeEngine:
    def __init__(self, config_path, dataset_path, dry_run=False, show=True,
                 enable_voice=True, enable_mouse=True, event_sink=None):
        self.cfg = Config.load(config_path)
        self.dry_run = dry_run
        self.show = show
        # event_sink(payload: dict) — called per frame ({"type":"frame",...}) and
        # on each action fire ({"type":"event",...}). Used by the web server to
        # stream telemetry; None for plain CLI use.
        self.event_sink = event_sink
        self._stop = threading.Event()
        self.enable_voice = enable_voice
        self.enable_mouse = enable_mouse and bool(self.cfg.mouse("enabled"))

        self.clf = PoseClassifier.load(
            dataset_path, max_distance=float(self.cfg.setting("max_distance"))
        )
        self.detector = HandDetector(max_hands=int(self.cfg.setting("max_hands")))
        self.seq = SequenceDetector(
            self.cfg.sequences, timeout=float(self.cfg.setting("sequence_timeout"))
        )

        self.stable_frames = int(self.cfg.setting("stable_frames"))
        self.min_conf = float(self.cfg.setting("min_confidence"))
        self.cooldown = float(self.cfg.setting("cooldown"))

        # Roles
        self.mouse_gesture = self.cfg.mouse("gesture")
        self.scroll_gesture = self.cfg.mouse("scroll_gesture")
        self.ptt = self.cfg.push_to_talk  # {pose: mode}

        # Voice stack (lazy — only if enabled and something uses it)
        self.audio = None
        self.transcription = None
        self.router = None

        # Mouse
        self.mouse = None
        if self.enable_mouse:
            self.mouse = MouseController(
                smoothing=float(self.cfg.mouse("smoothing")),
                pinch_threshold=float(self.cfg.mouse("pinch_threshold")),
                margin=float(self.cfg.mouse("margin")),
            )

        # Shared state
        self._current_gesture = None       # live recognized label (for combined ctx)
        self._last_voice = ""
        self._scroll_prev_y = None

    def stop(self) -> None:
        """Ask the run loop to exit (used by the server to stop a headless run)."""
        self._stop.set()

    def _emit(self, payload: dict) -> None:
        if self.event_sink is not None:
            try:
                self.event_sink(payload)
            except Exception:
                pass  # never let telemetry break the control loop

    # ----------------------------------------------------------- voice setup
    def _voice_in_use(self) -> bool:
        return bool(self.ptt or self.cfg.voice_commands or self.cfg.combined
                    or self.cfg.voice("always_listen"))

    def _start_voice(self) -> None:
        """Bring up mic + voice routing. The (slow) speech model loads on a
        background thread so the camera loop can start immediately; push-to-talk
        is gated on self.transcription becoming non-None once it's ready."""
        if not (self.enable_voice and self._voice_in_use()):
            return
        self.router = VoiceRouter(
            self.cfg.voice_commands, self.cfg.combined, dry_run=self.dry_run
        )
        self.audio = AudioCapture()
        self.audio.start()

        def _load():
            print("Loading speech model "
                  f"({self.cfg.voice('model')}, {self.cfg.voice('compute_type')})...")
            transcriber = Transcriber(
                model=self.cfg.voice("model"),
                device=self.cfg.voice("device"),
                compute_type=self.cfg.voice("compute_type"),
            )
            svc = TranscriptionService(transcriber, self._on_transcript)
            svc.start()
            self.transcription = svc
            if self.cfg.voice("always_listen"):
                self.audio.run_vad(
                    self._on_parallel_utterance,
                    energy_threshold=float(self.cfg.voice("energy_threshold")),
                    silence_ms=int(self.cfg.voice("silence_ms")),
                    max_segment_s=float(self.cfg.voice("max_segment_s")),
                    min_segment_ms=int(self.cfg.voice("min_segment_ms")),
                )
                print("Parallel listening (VAD) active.")
            print("Voice ready.")

        threading.Thread(target=_load, daemon=True).start()

    # callbacks (run on worker / VAD threads)
    def _on_transcript(self, text: str, context: dict) -> None:
        msg = self.router.route(text, context)
        self._last_voice = f"\U0001f5e3  '{text}'  {msg}"
        print(self._last_voice)
        self._emit({
            "type": "event", "kind": "voice", "name": text,
            "mode": context.get("mode"), "detail": msg, "dry_run": self.dry_run,
        })

    def _on_parallel_utterance(self, audio: np.ndarray) -> None:
        # Default parallel mode = command routing; combined bindings still apply
        # using whatever gesture is held right now.
        self.transcription.submit(
            audio, {"mode": "command", "gesture": self._current_gesture,
                    "source": "parallel"}
        )

    # ----------------------------------------------------------------- loop
    def run(self) -> None:
        # Runs even with zero recorded gestures: the camera + skeleton still
        # stream for live preview; classification simply yields no pose until
        # gestures exist.
        if not self.clf.labels:
            print("No gestures recorded yet — running camera/preview only.")
        self._start_voice()

        print(f"Poses: {self.clf.labels}")
        if self.ptt:
            print(f"Push-to-talk: {self.ptt}")
        if self.enable_mouse:
            print(f"Mouse gesture: '{self.mouse_gesture}'  scroll: '{self.scroll_gesture}'")
        print("Q in window or Ctrl+C to quit." + ("  [DRY RUN]" if self.dry_run else ""))

        current, streak, committed = None, 0, None
        last_fire: dict[str, float] = {}
        listening, ptt_gesture, ptt_mode, release_run = False, None, None, 0

        def maybe_fire(name, action, now, kind="pose"):
            if action is None:
                return ""
            if now - last_fire.get(name, 0.0) < self.cooldown:
                return ""
            last_fire[name] = now
            if not self.dry_run:
                dispatch(action)
            self._emit({
                "type": "event", "kind": kind, "name": name,
                "action_type": action.type, "action_value": action.value,
                "dry_run": self.dry_run,
            })
            prefix = "[dry] " if self.dry_run else ""
            return f"{prefix}{name} -> {action.type}:{action.value}"

        try:
            with Camera(int(self.cfg.setting("camera_index"))) as cam:
                while True:
                    if self._stop.is_set():
                        break
                    frame = cam.read()
                    if frame is None:
                        continue
                    hands = self.detector.detect(to_rgb(frame))
                    now = time.monotonic()

                    label, conf, hand = None, 0.0, None
                    if hands:
                        hand = hands[0]
                        if self.show:  # server mode keeps frames clean; client draws mesh
                            draw_landmarks(frame, hand.landmarks)
                        pred = self.clf.predict(extract_features(hand))
                        if pred.label and pred.confidence >= self.min_conf:
                            label, conf = pred.label, pred.confidence
                    self._current_gesture = label

                    # ---- stability streak ----
                    if label is not None and label == current:
                        streak += 1
                    else:
                        current = label
                        streak = 1 if label is not None else 0
                        if label is None:
                            committed = None

                    event = ""

                    # ---- push-to-talk gate ----
                    if listening:
                        if label != ptt_gesture:
                            release_run += 1
                        else:
                            release_run = 0
                        if release_run >= 3 or label is None:
                            audio_seg = self.audio.stop_recording()
                            listening = False
                            self.transcription.submit(
                                audio_seg,
                                {"mode": ptt_mode, "gesture": ptt_gesture,
                                 "source": "ptt"},
                            )
                            event = f"\U0001f3a4 captured {audio_seg.size/16000:.1f}s ({ptt_mode})"
                            ptt_gesture = None

                    # ---- role dispatch on a committed pose ----
                    committing = (label is not None and streak == self.stable_frames
                                  and label != committed)
                    if committing:
                        committed = label

                    if self.enable_mouse and label == self.mouse_gesture and hand is not None:
                        st = self.mouse.update(hand)
                        event = f"\U0001f5b1 ({st['x']},{st['y']}) {'PINCH' if st['pinch'] else ''}"
                    elif self.enable_mouse and label == self.scroll_gesture and hand is not None:
                        wy = float(hand.landmarks[WRIST][1])
                        if self._scroll_prev_y is not None:
                            dy = (self._scroll_prev_y - wy) * float(self.cfg.mouse("scroll_speed"))
                            if abs(dy) > 0.5 and not self.dry_run:
                                self.mouse.scroll(dy)
                        self._scroll_prev_y = wy
                    else:
                        if self.mouse is not None and committed != self.mouse_gesture:
                            self.mouse.reset()
                        self._scroll_prev_y = None

                        # start push-to-talk when a PTT pose commits
                        # (only once the speech model has finished loading)
                        if (not listening and self.audio is not None
                                and self.transcription is not None
                                and label in self.ptt and committing):
                            listening = True
                            ptt_gesture = label
                            ptt_mode = self.ptt[label]
                            release_run = 0
                            self.audio.start_recording()
                            event = f"\U0001f399 listening ({ptt_mode})..."
                        # normal pose action (skip pose roles)
                        elif (committing and label not in self.ptt
                              and label != self.mouse_gesture
                              and label != self.scroll_gesture):
                            event = maybe_fire(label, self.cfg.poses.get(label), now)
                            matched = self.seq.push(label, now)
                            if matched is not None:
                                event = maybe_fire(
                                    f"SEQ:{matched.name}",
                                    self.cfg.sequence_actions.get(matched.name), now,
                                )
                    if event:
                        print(event)

                    # ---- telemetry for the web console (overwrite-latest) ----
                    if self.event_sink is not None:
                        self._emit({
                            "type": "frame",
                            "pose": label,
                            "confidence": round(conf, 3),
                            "hold": streak,
                            "stable_frames": self.stable_frames,
                            "committed": committed,
                            "listening": listening,
                            "mode": (ptt_mode if listening else None),
                            "mic_rms": round(self.audio.rms, 4) if self.audio else 0.0,
                            "sequence_progress": list(self.seq._buffer),
                            "hands": [h.landmarks.tolist() for h in hands],
                            "handedness": [h.handedness for h in hands],
                            "frame_bgr": frame,  # clean frame; server encodes/throttles
                        })

                    if self.show:
                        rms = self.audio.rms if self.audio else 0.0
                        hud = [
                            f"pose: {label or '-'}  conf: {conf:.2f}  hold: {streak}/{self.stable_frames}",
                            ("LISTENING " + (ptt_mode or "") if listening else
                             f"mic rms: {rms:.3f}" if self.audio else "voice: off"),
                            self._last_voice or event or "Q to quit",
                        ]
                        color = (0, 165, 255) if listening else (0, 255, 0)
                        banner(frame, hud, color=color)
                        cv2.imshow("handsign — hands-free", frame)
                        if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                            break
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def close(self) -> None:
        if self.mouse is not None:
            self.mouse.reset()
        if self.audio is not None:
            self.audio.stop()
        if self.transcription is not None:
            self.transcription.stop()
        self.detector.close()

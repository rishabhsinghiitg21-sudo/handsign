"""Headless gesture recording driven from the web console.

Owns the camera + detector and streams live frames/landmarks over the same
telemetry sink the engine uses, so the console viewport shows you live while
recording. Clicking "Capture" in the UI triggers a short burst that appends
samples for the target label; "Save" persists the dataset.

This is the no-terminal equivalent of `handsign record`. Only one camera owner
can be active at a time, so the manager ensures the engine is stopped first.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from .camera import Camera, to_rgb
from .classifier import PoseClassifier
from .features import extract_features
from .landmarks import HandDetector


class RecordSession:
    def __init__(self, dataset_path, camera_index: int, event_sink,
                 burst_seconds: float = 1.5, burst_interval: float = 0.05):
        self.dataset_path = Path(dataset_path)
        self.camera_index = camera_index
        self.event_sink = event_sink
        self.burst_seconds = burst_seconds
        self.burst_interval = burst_interval

        self.clf = PoseClassifier.load(dataset_path)
        self.detector = HandDetector(max_hands=1)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._capture_until = 0.0
        self._capture_label: str | None = None
        self._last_capture = 0.0

    # ---- control (called from request threads) ----
    def capture(self, label: str) -> None:
        with self._lock:
            self._capture_label = label
            self._capture_until = time.monotonic() + self.burst_seconds

    def save(self) -> dict:
        self.clf.save(self.dataset_path)
        return self.clf.counts()

    def counts(self) -> dict:
        return self.clf.counts()

    def stop(self) -> None:
        self._stop.set()

    # ---- camera loop (own thread) ----
    def run(self) -> None:
        try:
            with Camera(self.camera_index) as cam:
                while not self._stop.is_set():
                    frame = cam.read()
                    if frame is None:
                        continue
                    hands = self.detector.detect(to_rgb(frame))
                    hand = hands[0] if hands else None
                    now = time.monotonic()

                    capturing = False
                    with self._lock:
                        label = self._capture_label
                        if hand is not None and now < self._capture_until:
                            capturing = True
                            if now - self._last_capture >= self.burst_interval:
                                self.clf.add_sample(label, extract_features(hand))
                                self._last_capture = now

                    self._emit({
                        "type": "frame",
                        "recording": True,
                        "capture_label": label,
                        "capturing": capturing,
                        "counts": self.clf.counts(),
                        "pose": None,
                        "confidence": 0.0,
                        "hold": 0,
                        "committed": None,
                        "listening": False,
                        "mode": "RECORD",
                        "mic_rms": 0.0,
                        "sequence_progress": [],
                        "hands": [h.landmarks.tolist() for h in hands],
                        "handedness": [h.handedness for h in hands],
                        "frame_bgr": frame,
                    })
        finally:
            # Persist whatever was captured, then release the camera/model.
            try:
                self.clf.save(self.dataset_path)
            except Exception:
                pass
            self.detector.close()

    def _emit(self, payload: dict) -> None:
        if self.event_sink is not None:
            try:
                self.event_sink(payload)
            except Exception:
                pass

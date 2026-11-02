"""Webcam capture + small drawing helpers shared by record/run modes."""

from __future__ import annotations

import cv2
import numpy as np

from .landmarks import HAND_CONNECTIONS


class Camera:
    """OpenCV camera as a context manager. Yields BGR frames, mirrored."""

    def __init__(self, index: int = 0, mirror: bool = True):
        self.index = index
        self.mirror = mirror
        self._cap: cv2.VideoCapture | None = None

    def __enter__(self) -> "Camera":
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"could not open camera {self.index}. Is another app using it, "
                "or is camera permission denied for your terminal?"
            )
        return self

    def read(self) -> np.ndarray | None:
        assert self._cap is not None
        ok, frame = self._cap.read()
        if not ok:
            return None
        if self.mirror:
            frame = cv2.flip(frame, 1)  # selfie view
        return frame

    def __exit__(self, *exc) -> None:
        if self._cap is not None:
            self._cap.release()
        cv2.destroyAllWindows()


def to_rgb(bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def draw_landmarks(frame_bgr: np.ndarray, raw_landmarks_norm) -> None:
    """Overlay the hand skeleton. `raw_landmarks_norm` is a (21,3) array of
    image-normalized coords; we scale to pixels and draw bones + joints."""
    h, w = frame_bgr.shape[:2]
    pts = [(int(x * w), int(y * h)) for x, y, _ in raw_landmarks_norm]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame_bgr, pts[a], pts[b], (255, 255, 255), 2, cv2.LINE_AA)
    for (px, py) in pts:
        cv2.circle(frame_bgr, (px, py), 4, (0, 200, 255), -1, cv2.LINE_AA)


def banner(frame_bgr: np.ndarray, lines: list[str], color=(0, 255, 0)) -> None:
    """Draw a few lines of HUD text at the top-left."""
    y = 28
    for line in lines:
        cv2.putText(
            frame_bgr, line, (12, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 4, cv2.LINE_AA,
        )
        cv2.putText(
            frame_bgr, line, (12, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 1, cv2.LINE_AA,
        )
        y += 30

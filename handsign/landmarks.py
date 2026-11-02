"""Hand landmark detection via MediaPipe Tasks (HandLandmarker).

This MediaPipe build ships only the modern Tasks API (no legacy mp.solutions),
so we use vision.HandLandmarker in IMAGE mode. Per frame it returns, for each
detected hand, 21 landmarks (x, y, z in image-normalized coordinates) plus a
handedness label ("Left"/"Right").

Requires the model bundle at data/hand_landmarker.task (downloaded during
setup).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    HandLandmarker,
    HandLandmarkerOptions,
    RunningMode,
)

# 21 landmark indices we reference by name (MediaPipe Hands topology).
WRIST = 0
MIDDLE_MCP = 9

# Bone connections for drawing the skeleton.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),            # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),            # index
    (5, 9), (9, 10), (10, 11), (11, 12),       # middle
    (9, 13), (13, 14), (14, 15), (15, 16),     # ring
    (13, 17), (17, 18), (18, 19), (19, 20),    # pinky
    (0, 17),                                   # palm base
]

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "data" / "hand_landmarker.task"


@dataclass
class HandResult:
    """One detected hand in one frame."""

    landmarks: np.ndarray  # shape (21, 3), image-normalized coords
    handedness: str        # "Left" or "Right"
    score: float           # detection confidence


class HandDetector:
    """Wrapper around the Tasks HandLandmarker for per-frame inference."""

    def __init__(
        self,
        max_hands: int = 2,
        min_detection_confidence: float = 0.6,
        min_tracking_confidence: float = 0.5,
        model_path: str | Path = DEFAULT_MODEL,
    ):
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"hand landmarker model not found at {model_path}. "
                "Run ./scripts/download_models.sh to fetch it (or re-run ./setup.sh)."
            )
        options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=RunningMode.IMAGE,
            num_hands=max_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_tracking_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = HandLandmarker.create_from_options(options)

    def detect(self, rgb_frame: np.ndarray) -> list[HandResult]:
        """Run detection on a contiguous uint8 RGB frame."""
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self._landmarker.detect(mp_image)
        out: list[HandResult] = []
        if not result.hand_landmarks:
            return out
        for i, hand_landmarks in enumerate(result.hand_landmarks):
            pts = np.array(
                [[lm.x, lm.y, lm.z] for lm in hand_landmarks], dtype=np.float32
            )
            label, score = "Right", 1.0
            if i < len(result.handedness) and result.handedness[i]:
                cat = result.handedness[i][0]
                label, score = cat.category_name, cat.score
            out.append(HandResult(landmarks=pts, handedness=label, score=score))
        return out

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "HandDetector":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

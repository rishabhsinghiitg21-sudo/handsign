"""Facial-expression detection via MediaPipe Face Landmarker (blendshapes).

The Face Landmarker emits 52 ARKit-style blendshape coefficients (0..1) per
frame — eyeBlinkLeft, jawOpen, mouthSmileLeft, browInnerUp, etc. We fold those
into a small set of named, human-meaningful EXPRESSIONS, each with an intensity
and a trigger threshold, so an expression can drive an action exactly like a
hand pose.

Only mapped expressions fire anything; the rest are just reported for the HUD.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    FaceLandmarker,
    FaceLandmarkerOptions,
    RunningMode,
)

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "data" / "face_landmarker.task"


def _avg(bs: dict, *names: str) -> float:
    return sum(bs.get(n, 0.0) for n in names) / len(names)


# name -> (intensity function over blendshape dict, default trigger threshold)
EXPRESSION_RULES: dict[str, tuple] = {
    "smile":      (lambda b: _avg(b, "mouthSmileLeft", "mouthSmileRight"), 0.45),
    "mouth_open": (lambda b: b.get("jawOpen", 0.0), 0.45),
    "brows_up":   (lambda b: _avg(b, "browInnerUp", "browOuterUpLeft", "browOuterUpRight"), 0.45),
    "brows_down": (lambda b: _avg(b, "browDownLeft", "browDownRight"), 0.45),
    "frown":      (lambda b: _avg(b, "mouthFrownLeft", "mouthFrownRight"), 0.40),
    "pucker":     (lambda b: b.get("mouthPucker", 0.0), 0.50),
    "cheek_puff": (lambda b: b.get("cheekPuff", 0.0), 0.40),
    "tongue_out": (lambda b: b.get("tongueOut", 0.0), 0.30),
    "wink_left":  (lambda b: max(0.0, b.get("eyeBlinkLeft", 0) - b.get("eyeBlinkRight", 0))
                   if b.get("eyeBlinkRight", 0) < 0.4 else 0.0, 0.40),
    "wink_right": (lambda b: max(0.0, b.get("eyeBlinkRight", 0) - b.get("eyeBlinkLeft", 0))
                   if b.get("eyeBlinkLeft", 0) < 0.4 else 0.0, 0.40),
    "jaw_left":   (lambda b: b.get("jawLeft", 0.0), 0.40),
    "jaw_right":  (lambda b: b.get("jawRight", 0.0), 0.40),
}

EXPRESSION_NAMES = list(EXPRESSION_RULES)


class FaceExpressionDetector:
    def __init__(self, model_path: str | Path = DEFAULT_MODEL):
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"face landmarker model not found at {model_path}. "
                "Run ./scripts/download_models.sh to fetch it (or re-run ./setup.sh)."
            )
        self._fl = FaceLandmarker.create_from_options(
            FaceLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(model_path)),
                running_mode=RunningMode.IMAGE,
                num_faces=1,
                output_face_blendshapes=True,
            )
        )

    def detect(self, rgb_frame: np.ndarray) -> dict:
        res = self._fl.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        )
        if not res.face_blendshapes:
            return {"present": False, "expression": None, "intensity": 0.0,
                    "scores": {}, "face_points": []}

        bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
        scores = {name: round(float(fn(bs)), 3) for name, (fn, _) in EXPRESSION_RULES.items()}

        active, best = None, 0.0
        for name, (_, thr) in EXPRESSION_RULES.items():
            v = scores[name]
            if v >= thr and v > best:
                active, best = name, v

        pts = res.face_landmarks[0]
        # subsample to a sparse "constellation" for a light overlay
        face_points = [[round(p.x, 4), round(p.y, 4)] for p in pts[::4]]

        return {"present": True, "expression": active, "intensity": round(best, 3),
                "scores": scores, "face_points": face_points}

    def close(self) -> None:
        self._fl.close()

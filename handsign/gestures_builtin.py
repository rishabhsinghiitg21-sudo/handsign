"""Built-in, training-free hand-pose recognition from landmark geometry.

Like the facial-expression rules, these work instantly with no recording: we
infer which fingers are extended (via the joint angle at each finger's PIP) and
map the pattern to a named pose. Recorded (KNN) gestures still take priority
when present — built-ins are the always-available fallback so the Gesture
channel registers out of the box.
"""

from __future__ import annotations

import numpy as np

# (mcp, pip, tip) joint triples per finger for the straightness angle.
_FINGERS = {
    "index": (5, 6, 8),
    "middle": (9, 10, 12),
    "ring": (13, 14, 16),
    "pinky": (17, 18, 20),
}
_THUMB = (2, 3, 4)

BUILTIN_GESTURES = ["fist", "open_palm", "thumbs_up", "point", "peace", "three", "shaka"]


def _angle(a, b, c) -> float:
    """Angle (degrees) at joint b, using x/y only (z is noisy)."""
    v1 = a[:2] - b[:2]
    v2 = c[:2] - b[:2]
    n = (np.linalg.norm(v1) * np.linalg.norm(v2)) + 1e-6
    cosv = float(np.clip(np.dot(v1, v2) / n, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosv)))


def _fingers_extended(lm: np.ndarray) -> dict:
    out = {}
    for name, (mcp, pip, tip) in _FINGERS.items():
        out[name] = _angle(lm[mcp], lm[pip], lm[tip]) > 160.0
    out["thumb"] = _angle(lm[_THUMB[0]], lm[_THUMB[1]], lm[_THUMB[2]]) > 150.0
    return out


def classify(landmarks: np.ndarray) -> tuple[str | None, float]:
    """Return (gesture_name, confidence) or (None, 0.0)."""
    lm = np.asarray(landmarks, dtype=np.float32)
    f = _fingers_extended(lm)
    th, idx, mid, rng, pky = f["thumb"], f["index"], f["middle"], f["ring"], f["pinky"]
    four = [idx, mid, rng, pky]
    wrist = lm[0]

    # all four fingers curled
    if not any(four):
        if th and lm[4][1] < wrist[1]:        # thumb out and pointing up
            return "thumbs_up", 0.9
        return "fist", 0.9
    if all(four):
        return "open_palm", 0.92
    if th and pky and not idx and not mid and not rng:
        return "shaka", 0.85
    if idx and not mid and not rng and not pky:
        return "point", 0.88
    if idx and mid and not rng and not pky:
        return "peace", 0.88
    if idx and mid and rng and not pky:
        return "three", 0.85
    return None, 0.0

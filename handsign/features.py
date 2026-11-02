"""Turn raw hand landmarks into a pose-invariant feature vector.

The goal: two performances of the *same* sign should map to nearly the same
vector regardless of where the hand is in frame, how big it appears, or (for
left vs right hand) which hand is used.

Pipeline:
  1. Translate so the wrist sits at the origin.
  2. Mirror left hands onto the right-hand frame (x -> -x) so a sign performed
     with either hand classifies the same.
  3. Scale by the wrist -> middle-finger-MCP distance (a stable hand "span")
     so near/far from the camera doesn't matter.

We deliberately do NOT rotation-normalize: hand orientation is meaningful for
many seals (e.g. palm up vs sideways), so we keep it as signal. Record your
samples in the orientation you intend to use them.
"""

from __future__ import annotations

import numpy as np

from .landmarks import HandResult, MIDDLE_MCP, WRIST

FEATURE_DIM = 63  # 21 landmarks * (x, y, z)


def extract_features(hand: HandResult) -> np.ndarray:
    """Return a (63,) float32 feature vector for one detected hand."""
    pts = hand.landmarks.astype(np.float32).copy()

    # 1. Translate to wrist-relative coordinates.
    pts -= pts[WRIST]

    # 2. Mirror left hand to match right-hand geometry.
    if hand.handedness == "Left":
        pts[:, 0] *= -1.0

    # 3. Scale by hand span (wrist -> middle MCP). Guard against zero.
    span = float(np.linalg.norm(pts[MIDDLE_MCP]))
    if span < 1e-6:
        span = 1e-6
    pts /= span

    return pts.reshape(-1)

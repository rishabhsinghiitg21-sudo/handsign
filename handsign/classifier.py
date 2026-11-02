"""K-nearest-neighbour pose classifier over recorded samples.

Each gesture label owns a set of feature vectors (recorded in "record" mode).
Classification = majority vote among the k nearest stored samples, with a
confidence derived from vote agreement and distance. A prediction below the
distance gate is reported as "unknown" so a random hand pose doesn't fire an
action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .features import FEATURE_DIM
from .fsutil import atomic_write_text


@dataclass
class Prediction:
    label: str | None       # None == unknown / no confident match
    confidence: float       # 0..1
    distance: float         # mean distance to the k nearest of the winning label


def vote_from_distances(labels, dists, k: int, max_distance: float) -> "Prediction":
    """Shared KNN vote: given per-sample distances + their labels, decide.

    Used by PoseClassifier.predict (full set) and by calibration (leave-one-out,
    by passing distances with the held-out sample masked to +inf).
    """
    import numpy as _np

    if len(labels) == 0:
        return Prediction(None, 0.0, float("inf"))
    k = min(k, int(_np.isfinite(dists).sum()))
    if k <= 0:
        return Prediction(None, 0.0, float("inf"))
    nn = _np.argsort(dists)[:k]

    votes: dict[str, float] = {}
    for idx in nn:
        lbl = labels[idx]
        votes[lbl] = votes.get(lbl, 0.0) + 1.0 / (1e-6 + dists[idx])
    winner = max(votes, key=votes.get)

    win_d = [dists[i] for i in nn if labels[i] == winner]
    mean_d = float(_np.mean(win_d))
    agreement = sum(1 for i in nn if labels[i] == winner) / k

    if mean_d > max_distance:
        return Prediction(None, 0.0, mean_d)
    closeness = max(0.0, 1.0 - mean_d / max_distance)
    confidence = 0.5 * agreement + 0.5 * closeness
    return Prediction(winner, round(confidence, 3), round(mean_d, 4))


class PoseClassifier:
    """In-memory KNN with JSON persistence."""

    def __init__(self, k: int = 5, max_distance: float = 0.55):
        self.k = k
        self.max_distance = max_distance  # gate: beyond this, call it unknown
        self._labels: list[str] = []          # parallel arrays
        self._vectors: np.ndarray = np.empty((0, FEATURE_DIM), dtype=np.float32)

    # ------------------------------------------------------------------ data
    @property
    def labels(self) -> list[str]:
        return sorted(set(self._labels))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for lbl in self._labels:
            out[lbl] = out.get(lbl, 0) + 1
        return out

    def add_sample(self, label: str, vector: np.ndarray) -> None:
        vec = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if vec.shape[1] != FEATURE_DIM:
            raise ValueError(f"expected {FEATURE_DIM} features, got {vec.shape[1]}")
        self._labels.append(label)
        self._vectors = np.vstack([self._vectors, vec])

    def remove_label(self, label: str) -> int:
        keep = [i for i, l in enumerate(self._labels) if l != label]
        removed = len(self._labels) - len(keep)
        self._labels = [self._labels[i] for i in keep]
        self._vectors = self._vectors[keep] if keep else np.empty((0, FEATURE_DIM), np.float32)
        return removed

    @property
    def vectors(self) -> np.ndarray:
        return self._vectors

    @property
    def label_list(self) -> list[str]:
        return self._labels

    # --------------------------------------------------------------- predict
    def predict(self, vector: np.ndarray) -> Prediction:
        if len(self._labels) == 0:
            return Prediction(None, 0.0, float("inf"))
        vec = np.asarray(vector, dtype=np.float32).reshape(-1)
        dists = np.linalg.norm(self._vectors - vec, axis=1)
        return vote_from_distances(self._labels, dists, self.k, self.max_distance)

    # ------------------------------------------------------------ persistence
    def save(self, path: str | Path) -> None:
        path = Path(path)
        data = {
            "feature_dim": FEATURE_DIM,
            "labels": self._labels,
            "vectors": self._vectors.tolist(),
        }
        atomic_write_text(path, json.dumps(data))

    @classmethod
    def load(cls, path: str | Path, **kwargs) -> "PoseClassifier":
        clf = cls(**kwargs)
        path = Path(path)
        if not path.exists():
            return clf
        data = json.loads(path.read_text())
        clf._labels = list(data.get("labels", []))
        vecs = data.get("vectors", [])
        clf._vectors = (
            np.array(vecs, dtype=np.float32)
            if vecs
            else np.empty((0, FEATURE_DIM), np.float32)
        )
        return clf

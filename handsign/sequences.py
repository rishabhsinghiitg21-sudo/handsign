"""Detect ordered pose *sequences* (combos) from a stream of stable poses.

A pose is "committed" by the runtime once it's been held stable for a few
frames. Those committed poses (with consecutive duplicates collapsed) flow into
this detector, which watches for the tail of the recent stream matching any
defined sequence's steps. Think Naruto seal combos: Snake -> Ram -> ... -> Tiger.

A timeout resets the in-progress stream so an old, abandoned combo doesn't
glue onto a new one.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SequenceSpec:
    name: str
    steps: list[str]


@dataclass
class SequenceDetector:
    sequences: list[SequenceSpec]
    timeout: float = 3.0  # seconds; idle longer than this and the buffer clears
    _buffer: list[str] = field(default_factory=list)
    _last_time: float = 0.0
    _max_len: int = 0

    def __post_init__(self) -> None:
        self._max_len = max((len(s.steps) for s in self.sequences), default=0)

    def push(self, pose: str, now: float) -> SequenceSpec | None:
        """Feed one committed pose. Returns a matched sequence, if any.

        `now` is a monotonic timestamp (seconds) supplied by the caller.
        """
        if self._buffer and (now - self._last_time) > self.timeout:
            self._buffer.clear()
        self._last_time = now

        # Collapse consecutive duplicates — holding a seal isn't repeating it.
        if self._buffer and self._buffer[-1] == pose:
            return self._check()

        self._buffer.append(pose)
        if len(self._buffer) > self._max_len:
            self._buffer = self._buffer[-self._max_len :]
        return self._check()

    def _check(self) -> SequenceSpec | None:
        for spec in self.sequences:
            n = len(spec.steps)
            if n and self._buffer[-n:] == spec.steps:
                self._buffer.clear()  # consume so it fires once
                return spec
        return None

    def reset(self) -> None:
        self._buffer.clear()

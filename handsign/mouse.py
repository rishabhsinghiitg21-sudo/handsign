"""Gesture-driven mouse control.

When the configured mouse gesture is held, the index fingertip drives the
cursor; pinching thumb + index fingertips together = press (so a tap is a
click and holding-while-moving is a drag). Built on pynput's mouse Controller.

Cursor smoothing is an exponential moving average to tame landmark jitter.
The frame's index-finger position is mapped from a centered sub-rectangle
(controlled by `margin`) to the full screen so the screen edges stay reachable
without moving your hand off-camera.
"""

from __future__ import annotations

import numpy as np
from pynput.mouse import Button, Controller

from .landmarks import HandResult, MIDDLE_MCP, WRIST

INDEX_TIP = 8
THUMB_TIP = 4


def _screen_size() -> tuple[int, int]:
    """Main display size in *points* (the coordinate space pynput moves in).

    Uses Quartz (already present via pynput on macOS); needs no permission,
    unlike the AppleScript/Finder route. Falls back to a sane default.
    """
    try:
        import Quartz
        b = Quartz.CGDisplayBounds(Quartz.CGMainDisplayID())
        w, h = int(b.size.width), int(b.size.height)
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    return 1512, 982


class MouseController:
    def __init__(
        self,
        smoothing: float = 0.5,
        pinch_threshold: float = 0.6,
        margin: float = 0.15,
        screen_size: tuple[int, int] | None = None,
    ):
        self.smoothing = float(np.clip(smoothing, 0.0, 0.95))
        self.pinch_threshold = pinch_threshold
        self.margin = margin
        self.screen_w, self.screen_h = screen_size or _screen_size()
        self._mouse = Controller()
        self._sx: float | None = None  # smoothed cursor target
        self._sy: float | None = None
        self._pinched = False

    def reset(self) -> None:
        """Release any held pinch and clear smoothing (call when gesture ends)."""
        if self._pinched:
            self._mouse.release(Button.left)
            self._pinched = False
        self._sx = self._sy = None

    def _map_to_screen(self, nx: float, ny: float) -> tuple[int, int]:
        lo, hi = self.margin, 1.0 - self.margin
        span = max(hi - lo, 1e-6)
        fx = float(np.clip((nx - lo) / span, 0.0, 1.0))
        fy = float(np.clip((ny - lo) / span, 0.0, 1.0))
        return int(fx * self.screen_w), int(fy * self.screen_h)

    @staticmethod
    def _pinch_distance(hand: HandResult) -> float:
        """Thumb-tip↔index-tip distance, normalized by hand span."""
        pts = hand.landmarks
        span = float(np.linalg.norm(pts[MIDDLE_MCP] - pts[WRIST])) or 1e-6
        d = float(np.linalg.norm(pts[THUMB_TIP] - pts[INDEX_TIP]))
        return d / span

    def update(self, hand: HandResult) -> dict:
        """Move the cursor to track the index fingertip; manage pinch state.

        Returns a small status dict for the HUD.
        """
        tip = hand.landmarks[INDEX_TIP]
        tx, ty = self._map_to_screen(float(tip[0]), float(tip[1]))

        a = self.smoothing
        self._sx = tx if self._sx is None else a * self._sx + (1 - a) * tx
        self._sy = ty if self._sy is None else a * self._sy + (1 - a) * ty
        self._mouse.position = (int(self._sx), int(self._sy))

        pinch_d = self._pinch_distance(hand)
        pinch = pinch_d < self.pinch_threshold
        if pinch and not self._pinched:
            self._mouse.press(Button.left)
            self._pinched = True
        elif not pinch and self._pinched:
            self._mouse.release(Button.left)
            self._pinched = False

        return {"x": int(self._sx), "y": int(self._sy),
                "pinch": self._pinched, "pinch_d": round(pinch_d, 3)}

    def scroll(self, dy: float) -> None:
        self._mouse.scroll(0, dy)

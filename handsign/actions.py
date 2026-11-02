"""Dispatch recognized gestures to real effects.

Supported action types (see gestures.json):
  - key   : press a keystroke / shortcut, e.g. "cmd+enter", "esc", "a"
  - text  : type a literal string
  - shell : run a shell command (use for anything else — open apps, AppleScript,
            curl to the Claude API, osascript, etc.)
  - mouse : a mouse button action — "click", "right_click", "double_click"

Keystrokes use pynput. On macOS the running terminal needs Accessibility
permission (System Settings -> Privacy & Security -> Accessibility) for
synthetic key events to reach other apps.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from pynput.keyboard import Controller, Key
from pynput.mouse import Button, Controller as MouseController

_keyboard = Controller()
_mouse = MouseController()

# Friendly names -> pynput special keys.
_SPECIAL: dict[str, Key] = {
    "cmd": Key.cmd, "command": Key.cmd, "win": Key.cmd, "super": Key.cmd,
    "ctrl": Key.ctrl, "control": Key.ctrl,
    "alt": Key.alt, "option": Key.alt, "opt": Key.alt,
    "shift": Key.shift,
    "enter": Key.enter, "return": Key.enter,
    "esc": Key.esc, "escape": Key.esc,
    "tab": Key.tab, "space": Key.space, "backspace": Key.backspace,
    "delete": Key.delete, "del": Key.delete,
    "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
    "home": Key.home, "end": Key.end,
    "pageup": Key.page_up, "pagedown": Key.page_down,
}
for _i in range(1, 13):
    _SPECIAL[f"f{_i}"] = getattr(Key, f"f{_i}")


@dataclass
class Action:
    type: str   # "key" | "text" | "shell"
    value: str

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(type=d.get("type", "key"), value=str(d.get("value", "")))


def _resolve(token: str):
    token = token.strip().lower()
    return _SPECIAL.get(token, token)  # plain chars pass through as themselves


def press_combo(spec: str) -> None:
    """Press a chord like 'cmd+shift+p'. Modifiers held, final key tapped."""
    parts = [p for p in spec.split("+") if p.strip()]
    if not parts:
        return
    *mods, last = parts
    resolved_mods = [_resolve(m) for m in mods]
    for m in resolved_mods:
        _keyboard.press(m)
    try:
        key = _resolve(last)
        _keyboard.press(key)
        _keyboard.release(key)
    finally:
        for m in reversed(resolved_mods):
            _keyboard.release(m)


def dispatch(action: Action) -> None:
    if action.type == "key":
        press_combo(action.value)
    elif action.type == "text":
        _keyboard.type(action.value)
    elif action.type == "shell":
        subprocess.Popen(action.value, shell=True)
    elif action.type == "mouse":
        v = action.value.strip().lower()
        if v in ("click", "left", "left_click"):
            _mouse.click(Button.left)
        elif v in ("right_click", "right"):
            _mouse.click(Button.right)
        elif v in ("double_click", "double"):
            _mouse.click(Button.left, 2)
        else:
            raise ValueError(f"unknown mouse action: {action.value!r}")
    else:
        raise ValueError(f"unknown action type: {action.type!r}")

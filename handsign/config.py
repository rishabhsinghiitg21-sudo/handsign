"""Load gestures.json — maps poses, sequences, voice, and combined bindings to actions.

Schema (all sections optional):
  settings        : tuning knobs (gesture, voice, mouse)
  poses           : pose-name  -> { action }
  sequences       : combo-name -> { steps[], action }
  push_to_talk    : pose-name  -> { mode: "dictation"|"command" }
                    (hold the pose to listen; mode routes the transcript)
  voice_commands  : phrase     -> { action }   (spoken-command vocabulary)
  combined        : [ { gesture, phrase, action } ]  (require both at once)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .actions import Action
from .sequences import SequenceSpec
from .workflows import WorkflowStep

DEFAULT_VOICE = {
    "model": "base.en",        # faster-whisper model size
    "device": "auto",          # auto|cpu|cuda
    "compute_type": "int8",    # int8 is fast on CPU/Apple silicon
    "always_listen": False,    # parallel mode: VAD-segmented continuous listening
    "energy_threshold": 0.012, # RMS gate for the energy VAD (parallel mode)
    "silence_ms": 600,         # trailing silence that ends an utterance
    "max_segment_s": 12,       # hard cap on one utterance
    "min_segment_ms": 250,     # ignore blips shorter than this
}

DEFAULT_MOUSE = {
    "enabled": True,
    "gesture": "point",        # pose that activates cursor control while held
    "smoothing": 0.5,          # 0..1 EMA; higher = smoother but laggier
    "pinch_threshold": 0.6,    # thumb-tip↔index-tip distance (in hand-span units) below which = pinch/click
    "margin": 0.15,            # map this centered sub-rect of the frame to full screen (edges reachable)
    "scroll_gesture": "three",  # pose that scrolls (vertical hand motion) while held
    "scroll_speed": 60,
}

DEFAULT_SETTINGS = {
    "stable_frames": 8,
    "min_confidence": 0.7,
    "max_distance": 0.55,      # KNN distance gate; beyond this = "unknown"
    "cooldown": 1.0,
    "sequence_timeout": 3.0,
    "camera_index": 0,
    "max_hands": 1,
    "voice": dict(DEFAULT_VOICE),
    "mouse": dict(DEFAULT_MOUSE),
}


@dataclass
class CombinedBinding:
    """A multi-modal trigger: fires when ALL specified conditions hold at once.
    Any subset may be set:
      gesture    — a pose on EITHER hand (hand-agnostic)
      hands       — a multiset of poses across BOTH hands (e.g. ["fist","point"])
      expression — a facial expression
      phrase     — a spoken phrase
    """
    action: Action
    gesture: str | None = None
    expression: str | None = None
    phrase: str | None = None
    hands: list[str] | None = None


@dataclass
class Config:
    poses: dict[str, Action] = field(default_factory=dict)
    sequences: list[SequenceSpec] = field(default_factory=list)
    sequence_actions: dict[str, Action] = field(default_factory=dict)
    push_to_talk: dict[str, str] = field(default_factory=dict)   # pose -> mode
    voice_commands: dict[str, Action] = field(default_factory=dict)
    expressions: dict[str, Action] = field(default_factory=dict)  # expr -> action
    combined: list[CombinedBinding] = field(default_factory=list)
    workflows: dict[str, list[WorkflowStep]] = field(default_factory=dict)
    settings: dict = field(default_factory=lambda: _merged_settings({}))

    def setting(self, key: str):
        return self.settings.get(key, DEFAULT_SETTINGS.get(key))

    def voice(self, key: str):
        return self.settings.get("voice", {}).get(key, DEFAULT_VOICE.get(key))

    def mouse(self, key: str):
        return self.settings.get("mouse", {}).get(key, DEFAULT_MOUSE.get(key))

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.exists():
            return cls()
        return cls.from_dict(json.loads(path.read_text()))

    @classmethod
    def from_dict(cls, raw: dict) -> "Config":
        """Build a Config from already-parsed JSON (raises on a malformed shape)."""
        if not isinstance(raw, dict):
            raise ValueError("config must be a JSON object")
        poses = {
            name: Action.from_dict(spec["action"])
            for name, spec in raw.get("poses", {}).items()
            if "action" in spec
        }
        sequences = [
            SequenceSpec(name=name, steps=list(spec.get("steps", [])))
            for name, spec in raw.get("sequences", {}).items()
        ]
        sequence_actions = {
            name: Action.from_dict(spec["action"])
            for name, spec in raw.get("sequences", {}).items()
            if "action" in spec
        }
        push_to_talk = {
            name: spec.get("mode", "command")
            for name, spec in raw.get("push_to_talk", {}).items()
        }
        voice_commands = {
            phrase.lower().strip(): Action.from_dict(spec["action"])
            for phrase, spec in raw.get("voice_commands", {}).items()
            if "action" in spec
        }
        expressions = {
            name: Action.from_dict(spec["action"])
            for name, spec in raw.get("expressions", {}).items()
            if "action" in spec
        }
        combined = []
        for c in raw.get("combined", []):
            if "action" not in c:
                continue
            phrase = c.get("phrase")
            phrase = phrase.lower().strip() if phrase else None
            gesture = c.get("gesture") or None
            expression = c.get("expression") or None
            hands = c.get("hands") or None
            if isinstance(hands, list):
                hands = [h for h in hands if h] or None
            if not (gesture or expression or phrase or hands):
                continue
            combined.append(CombinedBinding(
                action=Action.from_dict(c["action"]),
                gesture=gesture, expression=expression, phrase=phrase, hands=hands,
            ))
        workflows = {}
        for name, spec in raw.get("workflows", {}).items():
            steps = []
            for st in spec.get("steps", []):
                if "action" in st:
                    steps.append(WorkflowStep(
                        action=Action.from_dict(st["action"]),
                        delay_ms=int(st.get("delay_ms", 0)),
                    ))
            workflows[name] = steps

        return cls(
            poses=poses,
            sequences=sequences,
            sequence_actions=sequence_actions,
            push_to_talk=push_to_talk,
            voice_commands=voice_commands,
            expressions=expressions,
            combined=combined,
            workflows=workflows,
            settings=_merged_settings(raw.get("settings", {})),
        )


def _merged_settings(raw: dict) -> dict:
    s = dict(DEFAULT_SETTINGS)
    s["voice"] = dict(DEFAULT_VOICE)
    s["mouse"] = dict(DEFAULT_MOUSE)
    for k, v in raw.items():
        if k in ("voice", "mouse") and isinstance(v, dict):
            s[k].update(v)
        else:
            s[k] = v
    return s

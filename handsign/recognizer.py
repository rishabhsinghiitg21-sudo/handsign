"""Stateful per-frame recognizer fed by browser-captured video frames.

The browser owns the camera (clean getUserMedia permission) and streams JPEG
frames over a WebSocket. This class decodes each frame, runs the exact same
detection → features → KNN → stability → sequence → action-dispatch pipeline
the CLI engine uses, but one frame at a time and with no camera of its own.

Two modes:
  - "run"    : classify, commit stable poses, fire keystroke/mouse/shell actions
  - "record" : append feature samples for a target label (browser recording)

Voice/PTT live elsewhere — this handles the visual gesture half.
"""

from __future__ import annotations

import time

import cv2
import numpy as np

from .actions import Action, dispatch
from .classifier import PoseClassifier
from .config import Config
from .face import FaceExpressionDetector
from .features import extract_features
from . import gestures_builtin
from .landmarks import HandDetector, HandResult, WRIST
from .mouse import MouseController
from .sequences import SequenceDetector
from .workflows import start_workflow, summary as workflow_summary


class Recognizer:
    def __init__(self, config_path, dataset_path, dry_run=True, enable_mouse=True,
                 enable_face=True):
        self.cfg = Config.load(config_path)
        self.dataset_path = dataset_path
        self.dry_run = dry_run
        self.clf = PoseClassifier.load(
            dataset_path, max_distance=float(self.cfg.setting("max_distance"))
        )
        self.detector = HandDetector(max_hands=int(self.cfg.setting("max_hands")))
        self.seq = SequenceDetector(
            self.cfg.sequences, timeout=float(self.cfg.setting("sequence_timeout"))
        )
        self.stable_frames = int(self.cfg.setting("stable_frames"))
        self.min_conf = float(self.cfg.setting("min_confidence"))
        self.cooldown = float(self.cfg.setting("cooldown"))
        self.mouse_gesture = self.cfg.mouse("gesture")
        self.scroll_gesture = self.cfg.mouse("scroll_gesture")
        self.enable_mouse = enable_mouse and bool(self.cfg.mouse("enabled"))
        self.mouse = (
            MouseController(
                smoothing=float(self.cfg.mouse("smoothing")),
                pinch_threshold=float(self.cfg.mouse("pinch_threshold")),
                margin=float(self.cfg.mouse("margin")),
            )
            if self.enable_mouse
            else None
        )

        # multi-modal combined bindings without a spoken phrase
        # (gesture / two-hand / expression — evaluated live from the camera)
        self.visual_combos = [
            b for b in self.cfg.combined
            if b.phrase is None and (b.gesture or b.expression or b.hands)
        ]

        self.workflows = self.cfg.workflows  # {name: [WorkflowStep]}

        # face / expressions
        self.expressions = self.cfg.expressions  # {name: Action}
        self.enable_face = enable_face
        try:
            self.face = FaceExpressionDetector() if enable_face else None
        except Exception:
            self.detector.close()   # don't leak the hand model if the face model is missing
            raise
        self._expr_stable = max(3, self.stable_frames // 2)
        self._expr_current = None
        self._expr_streak = 0
        self._expr_committed = None

        # state — tracked per hand ("Left"/"Right") so both hands work independently
        self.mode = "run"            # run | record
        self._hand_current: dict[str, str | None] = {}
        self._hand_streak: dict[str, int] = {}
        self._hand_committed: dict[str, str | None] = {}
        self._last_fire: dict[str, float] = {}
        self._scroll_prev_y = None
        # record
        self._capture_until = 0.0
        self._capture_label: str | None = None
        self._last_capture = 0.0
        self._burst_interval = 0.05

    # ----- control -----
    def set_mode(self, mode: str):
        self.mode = mode
        self._hand_current.clear()
        self._hand_streak.clear()
        self._hand_committed.clear()

    def capture(self, label: str, seconds: float = 1.5):
        self._capture_label = label
        self._capture_until = time.monotonic() + seconds

    def save(self) -> dict:
        self.clf.save(self.dataset_path)
        return self.clf.counts()

    def close(self):
        if self.mouse:
            self.mouse.reset()
        self.detector.close()
        if self.face:
            self.face.close()

    # ----- per-frame -----
    @staticmethod
    def decode(jpeg_bytes: bytes) -> np.ndarray | None:
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img

    def process(self, frame_bgr: np.ndarray) -> dict:
        rgb = np.ascontiguousarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        hands = self.detector.detect(rgb)
        hand = hands[0] if hands else None
        now = time.monotonic()
        events: list[dict] = []

        face = self.face.detect(rgb) if self.face else {"present": False}

        base = {
            "hands": [h.landmarks.tolist() for h in hands],
            "handedness": [h.handedness for h in hands],
            "face_present": face.get("present", False),
            "expression": face.get("expression"),
            "expression_intensity": face.get("intensity", 0.0),
            "expr_scores": face.get("scores", {}),
            "face_points": face.get("face_points", []),
            "events": events,
        }

        if self.mode == "record":
            capturing = False
            label = self._capture_label
            if hand is not None and now < self._capture_until:
                capturing = True
                if now - self._last_capture >= self._burst_interval:
                    self.clf.add_sample(label, extract_features(hand))
                    self._last_capture = now
            base.update({
                "recording": True, "capturing": capturing,
                "capture_label": label, "counts": self.clf.counts(),
                "pose": None, "confidence": 0.0, "hold": 0,
                "stable_frames": self.stable_frames, "committed": None,
            })
            return base

        # ---- run mode: classify EACH hand independently ----
        # Disambiguate duplicate handedness labels (e.g. two "Right") by suffix.
        per_hand = []  # (slot, label, conf, hand)
        seen: dict[str, int] = {}
        for h in hands:
            slot = h.handedness
            seen[slot] = seen.get(slot, 0) + 1
            if seen[slot] > 1:
                slot = f"{slot}{seen[slot]}"
            label, conf = None, 0.0
            # 1) recorded (KNN) gestures take priority when present
            if self.clf.labels:
                pred = self.clf.predict(extract_features(h))
                if pred.label and pred.confidence >= self.min_conf:
                    label, conf = pred.label, pred.confidence
            # 2) training-free built-in geometry fallback (instant, no recording)
            if label is None:
                bname, bconf = gestures_builtin.classify(h.landmarks)
                if bname:
                    label, conf = bname, bconf
            per_hand.append((slot, label, conf, h))

        # per-hand stability + commit detection
        committing_slots = []  # slots whose pose just committed this frame
        present = set()
        for slot, label, conf, h in per_hand:
            present.add(slot)
            if label is not None and label == self._hand_current.get(slot):
                self._hand_streak[slot] = self._hand_streak.get(slot, 0) + 1
            else:
                self._hand_current[slot] = label
                self._hand_streak[slot] = 1 if label is not None else 0
                if label is None:
                    self._hand_committed[slot] = None
            if (label is not None and self._hand_streak[slot] == self.stable_frames
                    and label != self._hand_committed.get(slot)):
                self._hand_committed[slot] = label
                committing_slots.append(slot)
        # drop hands no longer in frame
        for slot in list(self._hand_committed):
            if slot not in present:
                self._hand_committed[slot] = None
                self._hand_current[slot] = None
                self._hand_streak[slot] = 0

        committed_poses = [p for p in self._hand_committed.values() if p]

        # ---- mouse roles: use whichever hand currently shows the mouse pose ----
        mouse_hand = next((h for (s, l, c, h) in per_hand if l == self.mouse_gesture), None)
        scroll_hand = next((h for (s, l, c, h) in per_hand if l == self.scroll_gesture), None)
        if self.enable_mouse and mouse_hand is not None:
            st = self.mouse.update(mouse_hand)
            events.append({"kind": "mouse", "name": "cursor",
                           "detail": f"({st['x']},{st['y']}){' PINCH' if st['pinch'] else ''}"})
        elif self.enable_mouse and scroll_hand is not None:
            wy = float(scroll_hand.landmarks[WRIST][1])
            if self._scroll_prev_y is not None and not self.dry_run:
                self.mouse.scroll((self._scroll_prev_y - wy) * float(self.cfg.mouse("scroll_speed")))
            self._scroll_prev_y = wy
        else:
            if self.mouse is not None and self.mouse_gesture not in committed_poses:
                self.mouse.reset()
            self._scroll_prev_y = None

        roles = {self.mouse_gesture, self.scroll_gesture}

        # ---- facial expression state machine (parallel to poses) ----
        expr = face.get("expression")
        if expr is not None and expr == self._expr_current:
            self._expr_streak += 1
        else:
            self._expr_current = expr
            self._expr_streak = 1 if expr is not None else 0
            if expr is None:
                self._expr_committed = None
        expr_committing = (expr is not None and self._expr_streak == self._expr_stable
                           and expr != self._expr_committed)
        if expr_committing:
            self._expr_committed = expr

        # ---- unified multi-modal firing ----
        combo = self._match_visual_combo(committed_poses, self._expr_committed)
        if combo is not None:
            label_parts = list(combo.hands or ([combo.gesture] if combo.gesture else []))
            if combo.expression:
                label_parts.append(combo.expression)
            base["active_combo"] = {
                "gesture": combo.gesture, "expression": combo.expression,
                "hands": combo.hands,
                "action_type": combo.action.type, "action_value": combo.action.value,
            }
        any_pose_committing = len(committing_slots) > 0
        suppress_poses = suppress_expr = False
        if combo is not None and (any_pose_committing or expr_committing):
            cname = " + ".join(label_parts)
            if self._fire(f"combo:{cname}", combo.action, now, "combined", events):
                suppress_poses = bool(combo.hands or combo.gesture)
                suppress_expr = combo.expression is not None

        # individual per-hand pose fires (either hand can trigger a pose binding)
        if not suppress_poses:
            for slot in committing_slots:
                lbl = self._hand_committed.get(slot)
                if lbl is None or lbl in roles:
                    continue
                self._fire(lbl, self.cfg.poses.get(lbl), now, "pose", events)
                matched = self.seq.push(lbl, now)
                if matched is not None:
                    self._fire(f"SEQ:{matched.name}",
                               self.cfg.sequence_actions.get(matched.name),
                               now, "sequence", events)
        if expr_committing and not suppress_expr:
            self._fire(f"face:{expr}", self.expressions.get(expr), now, "expression", events)

        # primary pose telemetry (first hand with a recognized pose)
        primary = next(((l, c) for (s, l, c, h) in per_hand if l), (None, 0.0))
        label, conf = primary
        base["hand_poses"] = [
            {"hand": s, "pose": l, "confidence": round(c, 3)} for (s, l, c, h) in per_hand
        ]

        primary_slot = next((s for (s, l, c, h) in per_hand if l == label), None)
        base.update({
            "pose": label, "confidence": round(conf, 3),
            "hold": self._hand_streak.get(primary_slot, 0) if primary_slot else 0,
            "stable_frames": self.stable_frames,
            "committed": " + ".join(committed_poses) if committed_poses else None,
            "sequence_progress": list(self.seq._buffer), "recording": False,
        })
        return base

    def _fire(self, name, action: Action | None, now, kind, events) -> bool:
        if action is None:
            return False
        if now - self._last_fire.get(name, 0.0) < self.cooldown:
            return False
        self._last_fire[name] = now

        if action.type == "workflow":
            steps = self.workflows.get(action.value, [])
            if not self.dry_run:
                start_workflow(steps)
            events.append({
                "kind": "workflow", "name": name,
                "action_type": "workflow", "action_value": action.value,
                "detail": workflow_summary(steps), "dry_run": self.dry_run,
                "t": time.time(),
            })
            return True

        if not self.dry_run:
            try:
                dispatch(action)
            except Exception as e:
                events.append({"kind": "error", "name": f"dispatch failed: {e}"})
                return False
        events.append({
            "kind": kind, "name": name,
            "action_type": action.type, "action_value": action.value,
            "dry_run": self.dry_run, "t": time.time(),
        })
        return True

    def _match_visual_combo(self, committed_poses: list[str], expr):
        """A combined binding (no spoken phrase) whose conditions are all
        currently satisfied across the committed hand poses + expression.
        `committed_poses` is the list of currently-held poses (one per hand)."""
        pose_set = sorted(committed_poses)
        for b in self.visual_combos:
            if b.hands is not None and sorted(b.hands) != pose_set:
                continue
            if b.gesture is not None and b.gesture not in committed_poses:
                continue
            if b.expression is not None and b.expression != expr:
                continue
            return b
        return None

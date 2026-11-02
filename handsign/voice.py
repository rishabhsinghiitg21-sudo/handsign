"""Route a transcript to the right effect: dictation, command, or combined.

Given transcribed text plus the context that produced it (fusion mode + the
gesture held at capture time), decide what to do:

  1. Combined bindings win first — if a binding's gesture was held AND its
     phrase appears in the transcript, fire its action.
  2. command mode — match the transcript against the spoken-command vocabulary
     (exact, then substring, then fuzzy) and fire the matched action.
  3. dictation mode — type the transcript verbatim into the focused app.

All effects go through actions.dispatch so keystrokes/text/shell/mouse behave
identically whether triggered by gesture or voice.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .actions import Action, dispatch
from .workflows import start_workflow, summary as workflow_summary

_PUNCT = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    return _PUNCT.sub("", text.lower()).strip()


class VoiceRouter:
    def __init__(self, voice_commands, combined, fuzzy_threshold: float = 0.82,
                 dry_run: bool = False, workflows: dict | None = None):
        self.voice_commands = voice_commands        # {phrase: Action}
        self.combined = combined                    # [CombinedBinding]
        self.fuzzy_threshold = fuzzy_threshold
        self.dry_run = dry_run
        self.workflows = workflows or {}            # {name: [WorkflowStep]}

    def _fire(self, action: Action, why: str) -> str:
        if action.type == "workflow":
            steps = self.workflows.get(action.value, [])
            if not self.dry_run:
                start_workflow(steps)
            tag = "[dry] " if self.dry_run else ""
            return f"{tag}{why} -> workflow:{action.value} ({workflow_summary(steps)})"
        if self.dry_run:
            return f"[dry] {why} -> {action.type}:{action.value}"
        dispatch(action)
        return f"{why} -> {action.type}:{action.value}"

    def route(self, text: str, context: dict) -> str:
        norm = normalize(text)
        if not norm:
            return ""
        gesture = context.get("gesture")
        expression = context.get("expression")
        mode = context.get("mode", "command")

        # 1. Combined bindings that include a spoken phrase take priority — the
        #    phrase must be heard AND any gesture/expression condition met now.
        for b in self.combined:
            if not b.phrase or b.phrase not in norm:
                continue
            if b.gesture is not None and gesture != b.gesture:
                continue
            if b.expression is not None and expression != b.expression:
                continue
            cond = " + ".join(x for x in (b.gesture, b.expression, f"'{b.phrase}'") if x)
            return self._fire(b.action, f"COMBINED[{cond}]")

        # 2. Dictation: type it.
        if mode == "dictation":
            return self._fire(Action("text", text.strip()), "DICTATE")

        # 3. Command vocabulary.
        action, matched = self._match_command(norm)
        if action is not None:
            return self._fire(action, f"VOICE['{matched}'<-'{norm}']")
        return f"(no command match for '{norm}')"

    def _match_command(self, norm: str):
        if not self.voice_commands:
            return None, None
        # exact
        if norm in self.voice_commands:
            return self.voice_commands[norm], norm
        # substring: a command phrase spoken inside a longer utterance
        for phrase, action in self.voice_commands.items():
            if phrase and phrase in norm:
                return action, phrase
        # fuzzy
        best, best_r = None, 0.0
        for phrase in self.voice_commands:
            r = SequenceMatcher(None, norm, phrase).ratio()
            if r > best_r:
                best, best_r = phrase, r
        if best is not None and best_r >= self.fuzzy_threshold:
            return self.voice_commands[best], best
        return None, None

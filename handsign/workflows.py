"""Workflows — a named macro: an ordered list of action steps that run in
sequence (with optional delays) from a single trigger.

A workflow is invoked via an action of type "workflow" whose value is the
workflow name, so any pose / sequence / expression / voice command / combined
binding can launch one. Steps run on a background thread so delays don't block
the recognizer loop.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .actions import Action, dispatch


@dataclass
class WorkflowStep:
    action: Action
    delay_ms: int = 0   # wait this long BEFORE running the step


def summary(steps: list[WorkflowStep], limit: int = 4) -> str:
    parts = [f"{s.action.type}:{s.action.value}" for s in steps[:limit]]
    if len(steps) > limit:
        parts.append(f"+{len(steps) - limit} more")
    return f"{len(steps)} steps — " + ", ".join(parts) if steps else "0 steps"


def start_workflow(steps: list[WorkflowStep]) -> None:
    """Execute a workflow's steps in order on a daemon thread (real dispatch)."""
    if not steps:
        return

    def _run():
        for s in steps:
            if s.delay_ms:
                time.sleep(s.delay_ms / 1000.0)
            try:
                dispatch(s.action)
            except Exception as e:  # keep going; one bad step shouldn't abort
                print(f"[workflow step error] {e}")

    threading.Thread(target=_run, daemon=True).start()

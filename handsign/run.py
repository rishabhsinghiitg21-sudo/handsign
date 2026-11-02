"""Thin entry point for live recognition — delegates to HandsFreeEngine.

Kept as a stable function so the CLI and external callers have one place to
start the full gesture + voice + mouse loop.
"""

from __future__ import annotations

from pathlib import Path

from .engine import HandsFreeEngine


def run(
    config_path: str | Path,
    dataset_path: str | Path,
    dry_run: bool = False,
    show: bool = True,
    enable_voice: bool = True,
    enable_mouse: bool = True,
) -> None:
    engine = HandsFreeEngine(
        config_path, dataset_path,
        dry_run=dry_run, show=show,
        enable_voice=enable_voice, enable_mouse=enable_mouse,
    )
    engine.run()

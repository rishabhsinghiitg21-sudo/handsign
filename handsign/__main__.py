"""handsign CLI.

  python -m handsign record <name>     record samples for a gesture
  python -m handsign run [--dry-run]   live recognition -> actions
  python -m handsign list              show recorded gestures & mappings
  python -m handsign remove <name>     delete a gesture's samples
  python -m handsign calibrate [what]  auto-suggest tuning thresholds
  python -m handsign console [--port]  web control console
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "gestures.json"
DEFAULT_DATASET = ROOT / "data" / "dataset.json"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="handsign", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument("--dataset", default=str(DEFAULT_DATASET))
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("record", help="record samples for a gesture")
    pr.add_argument("name")
    pr.add_argument("--target", type=int, default=60)
    pr.add_argument("--camera", type=int, default=0)

    prun = sub.add_parser("run", help="live recognition (gestures + voice + mouse)")
    prun.add_argument("--dry-run", action="store_true", help="log actions, don't execute")
    prun.add_argument("--no-window", action="store_true", help="headless (no preview)")
    prun.add_argument("--no-voice", action="store_true", help="disable microphone/speech")
    prun.add_argument("--no-mouse", action="store_true", help="disable gesture mouse control")

    pc = sub.add_parser("calibrate", help="auto-suggest tuning thresholds")
    pc.add_argument("target", nargs="?", default="all",
                    choices=["all", "classifier", "mouse", "voice"])
    pc.add_argument("--apply", action="store_true", help="write results into gestures.json")
    pc.add_argument("--camera", type=int, default=0)

    pcon = sub.add_parser("console", help="launch the web control console")
    pcon.add_argument("--port", type=int, default=8000)

    sub.add_parser("list", help="show recorded gestures and mappings")

    prm = sub.add_parser("remove", help="delete a gesture's samples")
    prm.add_argument("name")

    args = p.parse_args(argv)

    if args.cmd == "record":
        from .record import record
        record(args.name, args.dataset, camera_index=args.camera, target=args.target)
    elif args.cmd == "run":
        from .run import run
        run(args.config, args.dataset, dry_run=args.dry_run,
            show=not args.no_window, enable_voice=not args.no_voice,
            enable_mouse=not args.no_mouse)
    elif args.cmd == "console":
        from .server import serve
        serve(port=args.port)
    elif args.cmd == "calibrate":
        _calibrate(args)
    elif args.cmd == "list":
        _list(args.config, args.dataset)
    elif args.cmd == "remove":
        from .classifier import PoseClassifier
        clf = PoseClassifier.load(args.dataset)
        n = clf.remove_label(args.name)
        clf.save(args.dataset)
        print(f"Removed {n} samples for '{args.name}'.")
    return 0


def _calibrate(args) -> None:
    from . import calibrate as cal
    from .config import Config

    target = args.target
    results: dict[str, dict] = {}

    if target in ("all", "classifier"):
        sug, report = cal.calibrate_classifier(args.dataset)
        print("\n" + report)
        if sug:
            results["classifier"] = sug

    if target in ("all", "mouse"):
        cfg = Config.load(args.config)
        try:
            sug, report = cal.calibrate_mouse(args.camera, cfg.mouse("gesture"))
            print("\n" + report)
            if sug:
                results["mouse"] = sug
        except Exception as e:
            print(f"\nMouse calibration skipped: {e}")

    if target in ("all", "voice"):
        try:
            sug, report = cal.calibrate_voice()
            print("\n" + report)
            if sug:
                results["voice"] = sug
        except (KeyboardInterrupt, EOFError):
            print("\nVoice calibration skipped.")
        except Exception as e:
            print(f"\nVoice calibration skipped: {e}")

    if not results:
        print("\nNothing to apply.")
        return

    if args.apply:
        cal.apply_to_config(
            args.config,
            classifier=results.get("classifier"),
            mouse=results.get("mouse"),
            voice=results.get("voice"),
        )
    else:
        print("\n(Re-run with --apply to write these into gestures.json.)")


def _list(config_path: str, dataset_path: str) -> None:
    from .classifier import PoseClassifier
    from .config import Config

    clf = PoseClassifier.load(dataset_path)
    cfg = Config.load(config_path)

    print("Recorded gestures (samples):")
    counts = clf.counts()
    if not counts:
        print("  (none yet — run: python -m handsign record <name>)")
    for name in sorted(counts):
        mapped = cfg.poses.get(name)
        m = f"{mapped.type}:{mapped.value}" if mapped else "unmapped"
        print(f"  {name:<16} {counts[name]:>4} samples   -> {m}")

    if cfg.sequences:
        print("\nSequences:")
        for s in cfg.sequences:
            a = cfg.sequence_actions.get(s.name)
            m = f"{a.type}:{a.value}" if a else "unmapped"
            print(f"  {s.name:<16} {' -> '.join(s.steps)}   => {m}")

    if cfg.push_to_talk:
        print("\nPush-to-talk (hold pose, speak, release):")
        for pose, mode in cfg.push_to_talk.items():
            print(f"  {pose:<16} -> mode: {mode}")

    if cfg.voice_commands:
        print("\nVoice commands:")
        for phrase, a in cfg.voice_commands.items():
            print(f"  {phrase:<16} -> {a.type}:{a.value}")

    if cfg.expressions:
        print("\nFacial expressions:")
        for name, a in cfg.expressions.items():
            print(f"  {name:<16} -> {a.type}:{a.value}")

    if cfg.combined:
        print("\nCombined (all at once):")
        for c in cfg.combined:
            parts = [*(f"hand:{h}" for h in (c.hands or [])), c.gesture, c.expression,
                     f"'{c.phrase}'" if c.phrase else None]
            print(f"  {' + '.join(p for p in parts if p):<28} -> {c.action.type}:{c.action.value}")

    if cfg.workflows:
        print("\nWorkflows:")
        for name, steps in cfg.workflows.items():
            print(f"  {name:<16} {len(steps)} step{"" if len(steps) == 1 else "s"}")

    mg = cfg.mouse("gesture")
    print(f"\nMouse: gesture='{mg}' (held = cursor + pinch-click), "
          f"scroll='{cfg.mouse('scroll_gesture')}'")


if __name__ == "__main__":
    raise SystemExit(main())

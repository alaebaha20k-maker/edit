from __future__ import annotations

import argparse
from pathlib import Path

from super_auto_editor_v2.config.settings import load_config
from super_auto_editor_v2.export_manager import ExportManager


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="super-auto-editor")
    p.add_argument("--avatar", required=True, help="Path to full avatar video")
    p.add_argument("--script", required=True, help="Path to script text file")
    p.add_argument("--timeline", required=True, help="Path to timeline json")
    p.add_argument("--output", required=True, help="Path to final output video")
    p.add_argument("--mode", default="ultra_fast_draft", choices=["ultra_fast_draft", "fast_final", "quality_final"])
    p.add_argument("--config", default="", help="Optional path to JSON config file")
    return p


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(Path(args.config) if args.config else None)
    manager = ExportManager(config)
    out = manager.build(
        avatar_video=Path(args.avatar),
        script_path=Path(args.script),
        timeline_path=Path(args.timeline),
        output_path=Path(args.output),
        mode=args.mode,
    )
    print(f"✅ Final video: {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
M5 Runtime CLI — local development entry point.

Subcommands:
  tts       Generate TTS audio batch from teaching_events.json
  build     Build playback_data.json from events + audio_manifest + teacher_card
  feedback  Submit student feedback

Usage:
  python modules/M5_runtime/run.py tts --events <path> --output <dir> --voice-id <id>
  python modules/M5_runtime/run.py build --events <p> --audio-manifest <p> --output <d> --teacher-card <p>
  python modules/M5_runtime/run.py feedback --session-id <id> --student-id <id> --feedback '<json>'
"""
from __future__ import annotations
import sys
import os
import json
import argparse
from pathlib import Path

# Add modules directory to path (for "M5_runtime" imports)
_PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent
_MODULES_DIR = _PROJECT_ROOT / "modules"
sys.path.insert(0, str(_MODULES_DIR))
sys.path.insert(0, str(_PROJECT_ROOT))

from M5_runtime.tts_service import generate_tts_batch
from M5_runtime.build_playback import build_playback_data
from M5_runtime.feedback import submit_feedback


def _parse_config(config_str: str = None, config_file: str = None) -> dict | None:
    """Parse config from JSON string or file."""
    if config_file:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    if config_str:
        return json.loads(config_str)
    return None


def cmd_tts(args):
    """Generate TTS batch from teaching events."""
    config = _parse_config(args.config, args.config_file)

    result = generate_tts_batch(
        events_path=args.events,
        output_dir=args.output,
        voice_id=args.voice_id,
        config=config,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "success" else 1


def cmd_build(args):
    """Build playback data."""
    config = _parse_config(args.config, args.config_file)

    result = build_playback_data(
        events_path=args.events,
        audio_manifest_path=args.audio_manifest,
        output_dir=args.output,
        teacher_card_path=args.teacher_card,
        config=config,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "success" else 1


def cmd_feedback(args):
    """Submit student feedback."""
    if args.feedback.startswith("@"):
        with open(args.feedback[1:], "r", encoding="utf-8") as f:
            feedback = json.load(f)
    else:
        feedback = json.loads(args.feedback)

    result = submit_feedback(
        session_id=args.session_id,
        student_id=args.student_id,
        feedback=feedback,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "success" else 1


def main():
    parser = argparse.ArgumentParser(
        description="M5 Runtime — EduNUWA Learning Runtime CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # TTS batch
  python run.py tts --events data/events/teaching_events_sample.json \\
      --output data/audio_output/turn_1/ --voice-id songhao_teacher

  # Build playback data
  python run.py build --events data/events/teaching_events_sample.json \\
      --audio-manifest data/audio_output/turn_1/audio_manifest.json \\
      --output data/audio_output/turn_1/ \\
      --teacher-card data/teachers/T_20260515_001/teacher_card.json

  # Submit feedback
  python run.py feedback --session-id SES_test --student-id U_001 \\
      --feedback '{"rating": 4, "comment": "Good explanation"}'
        """
    )
    sub = parser.add_subparsers(dest="command", help="Subcommand")

    # --- tts ---
    tts = sub.add_parser("tts", help="Generate TTS audio batch")
    tts.add_argument("--events", required=True, help="Path to teaching_events.json")
    tts.add_argument("--output", required=True, help="Output directory for audio files")
    tts.add_argument("--voice-id", required=True, help="Teacher voice ID")
    tts.add_argument("--config", default=None, help="JSON config string")
    tts.add_argument("--config-file", default=None, help="Path to JSON config file")

    # --- build ---
    build = sub.add_parser("build", help="Build playback_data.json")
    build.add_argument("--events", required=True, help="Path to teaching_events.json")
    build.add_argument("--audio-manifest", required=True, help="Path to audio_manifest.json")
    build.add_argument("--output", required=True, help="Output directory")
    build.add_argument("--teacher-card", required=True, help="Path to teacher_card.json")
    build.add_argument("--config", default=None, help="JSON config string")
    build.add_argument("--config-file", default=None, help="Path to JSON config file")

    # --- feedback ---
    fb = sub.add_parser("feedback", help="Submit student feedback")
    fb.add_argument("--session-id", required=True, help="Session ID")
    fb.add_argument("--student-id", required=True, help="Student ID")
    fb.add_argument("--feedback", required=True, help="JSON feedback string or @filepath")

    args = parser.parse_args()

    if args.command == "tts":
        return cmd_tts(args)
    elif args.command == "build":
        return cmd_build(args)
    elif args.command == "feedback":
        return cmd_feedback(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

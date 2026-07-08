#!/usr/bin/env python3
"""
M5 Runtime End-to-End Demo
===========================
M5 demo: TTS batch -> build playback data -> submit feedback

Usage:
    python demo/run_demo.py              # full demo
    python demo/run_demo.py --skip-tts   # skip TTS (build + feedback only)
"""
from __future__ import annotations
import sys
import os
import json
import time
import shutil
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Path setup
_DEMO_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_MODULE_DIR = _DEMO_DIR.parent
_PROJECT_ROOT = _MODULE_DIR.parent.parent
_MODULES_DIR = _PROJECT_ROOT / "modules"
sys.path.insert(0, str(_MODULES_DIR))
sys.path.insert(0, str(_PROJECT_ROOT))

from M5_runtime.tts_service.tts_engine import generate_tts_batch, _validate_events
from M5_runtime.build_playback.builder import build_playback_data
from M5_runtime.feedback.submit import submit_feedback

# Demo paths
EVENTS_FILE = _DEMO_DIR / "demo_teaching_events.json"
OUTPUT_BASE = _PROJECT_ROOT / "data" / "sessions" / "SES_demo_20260522"
AUDIO_DIR = OUTPUT_BASE / "audio" / "turn_1"
PLAYBACK_DIR = OUTPUT_BASE
TEACHER_CARD = _PROJECT_ROOT / "data" / "teachers" / "T_20260515_001" / "teacher_card.json"

SEP = "=" * 62


def print_step(step: int, desc: str):
    print(f"\n[Step {step}/4] {desc}")
    print("-" * 40)


def print_ok(msg: str):
    print(f"  [OK] {msg}")


def print_info(msg: str):
    print(f"  --> {msg}")


# ============================================================
# Step 1: Validate events
# ============================================================
def step1_validate():
    print_step(1, "Validate teaching_events.json")
    with open(EVENTS_FILE, "r", encoding="utf-8") as f:
        events_data = json.load(f)

    events = events_data["events"]
    print_info(f"Loaded {len(events)} teaching events")

    type_counts = {}
    for e in events:
        t = e["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    type_icons = {"speak": "[speak]", "board": "[board]", "formula": "[formula]",
                   "table": "[table]", "pause": "[pause]", "quiz": "[quiz]"}
    for t, c in sorted(type_counts.items()):
        icon = type_icons.get(t, "[-]")
        print_info(f"  {icon} {t}: {c}")

    err = _validate_events(events)
    if err:
        print(f"  [FAIL] Validation failed: {err['message']}")
        return False
    print_ok(f"All {len(events)} events validated ({len(type_counts)} types)")
    return True


# ============================================================
# Step 2: TTS batch
# ============================================================
def step2_tts(skip_tts: bool = False):
    print_step(2, "TTS Batch Synthesis (GPT-SoVITS)")

    if skip_tts:
        print_info("TTS skipped (--skip-tts)")
        return None

    if AUDIO_DIR.exists():
        shutil.rmtree(str(AUDIO_DIR))

    print_info("Loading models and synthesizing...")
    t0 = time.time()
    result = generate_tts_batch(
        events_path=str(EVENTS_FILE),
        output_dir=str(AUDIO_DIR),
        voice_id="songhao_teacher",
        config={
            "tts": {
                "engine": "gpt_sovits",
                "speed": 1.0,
                "use_voice_clone": True,
                "clone_reference_count": 3,
                "top_p": 0.6,
                "temperature": 0.6,
            }
        }
    )
    elapsed = time.time() - t0

    if result["status"] != "success":
        print(f"  [FAIL] TTS failed: {result.get('message', 'unknown error')}")
        print_info("Will use edge_tts fallback...")
        return None

    print_ok(f"Engine: {result['tts_engine']}")
    print_ok(f"Audio segments: {result['audio_count']}")
    print_ok(f"Total duration: {result['total_duration_sec']:.1f}s")
    print_ok(f"Wall time: {elapsed:.1f}s")
    if result['total_duration_sec'] > 0:
        rtf = elapsed / result['total_duration_sec']
        print_ok(f"RTF (realtime factor): {rtf:.2f}x")
    print_ok(f"Manifest: {result['audio_manifest']}")

    return result


# ============================================================
# Step 3: Build playback data
# ============================================================
def step3_build():
    print_step(3, "Build playback_data.json")

    manifest_path = AUDIO_DIR / "audio_manifest.json"

    if not manifest_path.exists():
        print_info("No audio_manifest found, creating mock data for demo...")
        os.makedirs(str(AUDIO_DIR), exist_ok=True)
        durations = [2.5, 3.2, 3.8, 2.1, 3.0, 2.6, 2.3, 2.8, 4.0, 2.7]
        mock_items = []
        for i in range(10):
            seq = i * 2 + 1
            evt_id = f"evt_{seq:04d}"
            mock_items.append({
                "event_id": evt_id, "seq": seq,
                "text": "...", "audio_path": f"audio/turn_1/{evt_id}.wav",
                "duration_sec": durations[i], "sample_rate": 22050
            })
        mock_manifest = {
            "event_file_id": "demo_functions_intro",
            "session_id": "SES_demo_20260522", "turn": 1,
            "tts_engine": "demo_mock", "voice_id": "songhao_teacher",
            "items": mock_items
        }
        with open(str(manifest_path), "w", encoding="utf-8") as f:
            json.dump(mock_manifest, f, ensure_ascii=False, indent=2)
        print_ok("Created mock audio_manifest.json")

    result = build_playback_data(
        events_path=str(EVENTS_FILE),
        audio_manifest_path=str(manifest_path),
        output_dir=str(PLAYBACK_DIR),
        teacher_card_path=str(TEACHER_CARD),
        config={"playback": {"speak_pause_after_sec": 0.3, "board_dwell_sec": 1.5}}
    )

    if result["status"] != "success":
        print(f"  [FAIL] Build failed: {result.get('message', 'unknown error')}")
        return None

    print_ok(f"Timeline items: {result['timeline_count']}")
    print_ok(f"Output: {result['playback_data']}")

    out_path = Path(result["playback_data"])
    with open(out_path, "r", encoding="utf-8") as f:
        pb = json.load(f)

    print_info(f"Teacher: {pb['teacher_id']}  Voice: {pb['voice_id']}")
    print_info(f"Total duration: {pb['total_duration_sec']:.1f}s")
    print_info("Timeline preview:")
    for item in pb["timeline"][:8]:
        t = item["type"]
        offset = item["start_offset_sec"]
        detail = ""
        if t == "speak":
            text = item.get("text", "")
            detail = f'"{text[:40]}..."' if len(text) > 40 else f'"{text}"'
        elif t == "board":
            detail = f'action={item.get("action", "")}'
        elif t == "quiz":
            detail = f'Q: {item.get("question", "")}'
        elif t == "formula":
            detail = f'latex={item.get("latex", "")[:30]}...'
        elif t == "table":
            detail = f'title={item.get("title", "")}'
        print_info(f"  [{offset:5.1f}s] {t:7s} {detail}")
    if len(pb["timeline"]) > 8:
        print_info(f"  ... ({len(pb['timeline']) - 8} more items)")

    return result


# ============================================================
# Step 4: Submit feedback
# ============================================================
def step4_feedback():
    print_step(4, "Submit Student Feedback")

    feedback = {
        "rating": 5,
        "comment": "Very clear! The three elements of function were explained well.",
        "fingerprint_feedback": {
            "pace": 0.45, "interactivity": 0.7, "humor": 0.3,
            "rigor": 0.75, "detail": 0.65, "abstraction": 0.3,
        },
        "pedagogy_feedback": {
            "concept_entry_perceived": "problem-driven",
            "analogy_density_perceived": "high",
            "misconception_alert_perceived": "proactive-explicit",
        },
        "completion_pct": 1.0,
    }

    result = submit_feedback(
        session_id="SES_demo_20260522",
        student_id="U_demo_001",
        feedback=feedback,
    )

    if result["status"] != "success":
        print(f"  [FAIL] Submit failed: {result.get('message', 'unknown error')}")
        return None

    print_ok(f"Rating: {feedback['rating']}/5")
    print_ok(f"Comment: {feedback['comment']}")
    print_ok(f"Output: {result['feedback_path']}")

    fb_path = Path(result["feedback_path"])
    if fb_path.exists():
        with open(fb_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        print_info(f"Fingerprint feedback: {json.dumps(saved.get('fingerprint_feedback', {}), ensure_ascii=False)}")
        print_info(f"Pedagogy feedback: {json.dumps(saved.get('pedagogy_feedback', {}), ensure_ascii=False)}")

    return result


# ============================================================
# Main
# ============================================================
def main():
    skip_tts = "--skip-tts" in sys.argv or "--no-tts" in sys.argv

    print(f"\n{'='*62}")
    print(f"  M5 Runtime - End-to-End Demo")
    print(f"  EduNUWA v2 - Learning Runtime")
    print(f"  Teacher: Song Hao | Topic: Functions")
    print(f"{'='*62}")

    if skip_tts:
        print(f"\n  * TTS synthesis skipped (--skip-tts)")
        print(f"  * Using mock audio_manifest for demo")

    results = {}

    # Step 1
    if not step1_validate():
        print("\n[FAIL] Event validation failed. Aborting.")
        return 1

    # Step 2
    results["tts"] = step2_tts(skip_tts)

    # Step 3
    results["build"] = step3_build()

    # Step 4
    results["feedback"] = step4_feedback()

    # Summary
    print(f"\n{'='*62}")
    print(f"  ALL STEPS COMPLETED SUCCESSFULLY")
    print(f"{'='*62}")
    print(f"\n  Output files:")
    print(f"    Teaching events: {EVENTS_FILE}")
    if not skip_tts and results.get("tts"):
        print(f"    Audio manifest:  {results['tts']['audio_manifest']}")
        print(f"    Audio directory: {AUDIO_DIR}")
    if results.get("build"):
        print(f"    Playback data:   {results['build']['playback_data']}")
    if results.get("feedback"):
        print(f"    Student feedback:{results['feedback']['feedback_path']}")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())

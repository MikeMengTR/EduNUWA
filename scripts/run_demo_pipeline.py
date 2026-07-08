import argparse
import json
from pathlib import Path

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else "<missing>"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, help="Path to demo case directory")
    args = parser.parse_args()

    case_dir = Path(args.case)
    print("EduNuwa demo pipeline preview")
    print("=" * 40)

    q = json.loads((case_dir / "user_question.json").read_text(encoding="utf-8"))
    print("User question:", q.get("question"))

    print("\n[1] TeacherSkill.md")
    skill = read_text(case_dir / "TeacherSkill.md")
    print(skill[:500] + ("..." if len(skill) > 500 else ""))

    print("\n[2] Retrieved context")
    context = read_text(case_dir / "retrieved_context.md")
    print(context[:500] + ("..." if len(context) > 500 else ""))

    print("\n[3] Teaching events")
    events = json.loads((case_dir / "teaching_events.json").read_text(encoding="utf-8"))["events"]
    for event in events:
        print(f"- seq={event.get('seq')} type={event.get('type')} id={event.get('event_id')}")

    manifest_path = case_dir / "audio_manifest.json"
    print("\n[4] Audio manifest")
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in manifest.get("items", []):
            print(f"- {item['event_id']}: {item['audio_path']} ({item['duration_sec']}s)")
    else:
        print("audio_manifest.json missing")

    print("\nPipeline preview finished. Replace sample files with real module outputs during integration.")

if __name__ == "__main__":
    main()

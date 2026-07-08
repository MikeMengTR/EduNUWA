import json
import sys
from pathlib import Path

REQUIRED = {
    "speak": ["event_id", "type", "seq", "text"],
    "board": ["event_id", "type", "seq", "action", "content"],
    "formula": ["event_id", "type", "seq", "latex"],
    "table": ["event_id", "type", "seq", "columns", "rows"],
    "pause": ["event_id", "type", "seq", "duration_ms"],
    "quiz": ["event_id", "type", "seq", "question"]
}

def validate(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data.get("events", [])
    if not events:
        print("ERROR: events is empty")
        return 1
    errors = []
    for i, event in enumerate(events):
        etype = event.get("type")
        if etype not in REQUIRED:
            errors.append(f"event[{i}] unknown type: {etype}")
            continue
        for key in REQUIRED[etype]:
            if key not in event:
                errors.append(f"event[{i}] missing key: {key}")
    if errors:
        print("Validation failed:")
        for err in errors:
            print("-", err)
        return 1
    print(f"OK: {path} contains {len(events)} valid events.")
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/validate_events.py <teaching_events.json>")
        raise SystemExit(1)
    raise SystemExit(validate(Path(sys.argv[1])))

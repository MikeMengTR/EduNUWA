"""
Feedback submission — validates and writes student feedback per M5 spec §5.4.
"""
from __future__ import annotations
import os
import json
from pathlib import Path
from datetime import datetime, timezone

from ..tts_service.audio_postprocess import atomic_write_json

_PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent.parent

VALID_FEEDBACK_KEYS = {
    "fingerprint_feedback", "pedagogy_feedback",
}
VALID_FINGERPRINT_KEYS = {"pace", "detail", "abstraction", "interactivity", "humor", "rigor"}
VALID_PEDAGOGY_KEYS = {
    "concept_entry_perceived", "analogy_density_perceived",
    "misconception_alert_perceived", "blackboard_strategy_perceived",
    "intuition_building_perceived",
}


def _validate_feedback(feedback: dict) -> str | None:
    """Validate feedback dict. Returns error message or None if valid."""
    # H12: rating is required
    if "rating" not in feedback:
        return "feedback must contain 'rating' field (integer 1-5)"

    rating = feedback["rating"]
    if not isinstance(rating, (int, float)) or not (1 <= rating <= 5):
        return f"rating must be integer 1-5, got {rating}"

    # Validate fingerprint_feedback sub-fields
    fp = feedback.get("fingerprint_feedback", {})
    for key in fp:
        if key not in VALID_FINGERPRINT_KEYS:
            return f"Unknown fingerprint dimension: '{key}'. Valid: {sorted(VALID_FINGERPRINT_KEYS)}"
        val = fp[key]
        if not isinstance(val, (int, float)) or not (0 <= val <= 1):
            return f"fingerprint_feedback.{key} must be 0.0-1.0, got {val}"

    # Validate pedagogy_feedback sub-fields
    pp = feedback.get("pedagogy_feedback", {})
    for key in pp:
        if key not in VALID_PEDAGOGY_KEYS:
            return f"Unknown pedagogy dimension: '{key}'. Valid: {sorted(VALID_PEDAGOGY_KEYS)}"

    # Validate completion_pct
    cpct = feedback.get("completion_pct", 1.0)
    if not isinstance(cpct, (int, float)) or not (0 <= cpct <= 1):
        return f"completion_pct must be 0.0-1.0, got {cpct}"

    return None


def submit_feedback(
    session_id: str,
    student_id: str,
    feedback: dict,
) -> dict:
    """Write student feedback to data/sessions/{session_id}/feedback.json.

    Args:
        session_id: Session ID
        student_id: Student user ID
        feedback: Feedback dict with at least {"rating": 1-5, ...}
                  See overall plan §5.5 for full schema.

    Returns:
        dict with status and feedback_path
    """
    # Validate
    error = _validate_feedback(feedback)
    if error:
        return {"status": "error", "message": error}

    # Determine output path
    # Try multi-tenant structure first, fall back to project data dir
    sessions_dir = _PROJECT_ROOT / "data" / "sessions" / session_id
    if not sessions_dir.exists():
        sessions_dir = _PROJECT_ROOT / "GPT-SoVITS-v2pro" / "data" / "sessions" / session_id

    os.makedirs(str(sessions_dir), exist_ok=True)
    output_path = str(sessions_dir / "feedback.json")

    # Build feedback object
    feedback_obj = {
        "session_id": session_id,
        "student_id": student_id,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint_feedback": feedback.get("fingerprint_feedback", {}),
        "pedagogy_feedback": feedback.get("pedagogy_feedback", {}),
        "rating": feedback["rating"],
        "comment": feedback.get("comment", ""),
        "completion_pct": feedback.get("completion_pct", 1.0),
    }

    # Preserve teacher_id / skill_id if provided
    for field in ["teacher_id", "skill_id"]:
        if field in feedback:
            feedback_obj[field] = feedback[field]

    # Atomic write
    atomic_write_json(feedback_obj, output_path)

    return {
        "status": "success",
        "feedback_path": output_path,
    }

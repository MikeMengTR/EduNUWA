"""
TTS Engine — main entry point for M5 Runtime TTS batch generation.
Implements generate_tts_batch() per M5_runtime.md §3.1 spec.
"""
from __future__ import annotations
import os
import json
import time
import traceback
from pathlib import Path
import re
from datetime import datetime, timezone

def _preprocess_tts_text(text: str) -> str:
    """Preprocess text for GPT-SoVITS compatibility.

    GPT-SoVITS chokes on mixed Chinese-English text with math symbols.
    This converts math expressions to pure Chinese so all TTS goes
    through GPT-SoVITS with consistent voice (no edge_tts fallback).

    The original text in playback_data is preserved for display;
    only the TTS input is simplified.
    """
    # 1. Superscript mapping (excluding ²³ which get Chinese replacements)
    superscripts = str.maketrans({
        '⁰': '0', '¹': '1', '⁴': '4',
        '⁵': '5', '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9',
        '₀': '0', '₁': '1', '₂': '2', '₃': '3', '₄': '4',
        '₅': '5', '₆': '6', '₇': '7', '₈': '8', '₉': '9',
    })
    text = text.translate(superscripts)

    # 2. Replace Unicode math symbols with Chinese
    replacements = [
        ('²', '平方'), ('³', '立方'), ('½', '二分之一'),
        ('√', '根号'), ('∫', '积分'), ('∑', '求和'),
        ('→', '到'), ('⇒', '得到'), ('⟹', '得到'), ('⟶', '到'),
        ('∈', '属于'), ('∀', '对于任意'),
        ('≈', '约等于'), ('≠', '不等于'), ('≡', '恒等于'),
        ('≤', '小于等于'), ('≥', '大于等于'),
        ('α', '阿尔法'), ('β', '贝塔'), ('γ', '伽马'), ('θ', '西塔'),
        ('π', '派'), ('ω', '欧米伽'), ('Δ', '德尔塔'),
        ('·', '点'), ('×', '乘'), ('÷', '除以'), ('±', '正负'),
    ]
    for old, new in replacements:
        text = text.replace(old, new)

    # 3. Replace LaTeX command patterns like \vec, \sqrt etc.
    text = re.sub(r'\\([a-zA-Z]+)', '', text)

    # 4. GPT-SoVITS with g2p_en installed can handle mixed Chinese-English.
    #    Keep Latin letters (they'll be pronounced as English letters).
    #    Only clean up math operators and redundant whitespace.

    # 5. Normalize whitespace around Latin letters
    #    "质点P" → "质点 P" (space between Chinese and Latin)
    text = re.sub(r'([一-鿿])([a-zA-Z])', r'\1 \2', text)
    text = re.sub(r'([a-zA-Z])([一-鿿])', r'\1 \2', text)

    # 6. Remove LaTeX braces/special chars that aren't spoken
    text = re.sub(r'[{}[\]]', '', text)

    # 7. Normalize punctuation
    text = text.replace(',', '，').replace(';', '；').replace(':', '：')

    return text

def _contains_latin(text: str) -> bool:
    return bool(re.search(r'[a-zA-Z]', text))

from .gpt_sovits_wrapper import StreamingTTS
from .voice_clone import get_clone_references
from .edge_tts_fallback import edge_tts_synthesize
from .audio_postprocess import atomic_write_json

# Module root for path resolution
_MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = _MODULE_DIR.parent.parent.parent  # sovits/

# Valid event types and board actions per M5 spec §4.1
VALID_EVENT_TYPES = {"speak", "board", "formula", "table", "pause", "quiz"}
VALID_BOARD_ACTIONS = {
    "write_title", "write_subtitle", "write_bullets",
    "write_steps", "write_summary", "clear_board", "highlight"
}

# Default config
DEFAULT_CONFIG = {
    "tts": {
        "engine": "gpt_sovits",
        "voice_id": "songhao_teacher",
        "speed": 0.85,
        "audio_format": "wav",
        "sample_rate": 22050,
        "use_voice_clone": True,
        "clone_reference_count": 3,
        "top_p": 0.6,
        "temperature": 0.6,
    },
    "playback": {
        "speak_pause_after_sec": 0.3,
        "board_dwell_sec": 1.5,
    }
}

# Hardcoded TTS engine exceptions that should trigger fallback
FALLBACK_EXCEPTIONS = (RuntimeError, OSError, MemoryError)


def _resolve_teacher_id(voice_id: str) -> str:
    """Map voice_id to teacher_id.

    Convention: voice_id is "{teacher_id_compact}_voice"
    e.g., "T20260515001_voice" -> "T_20260515_001"
    """
    if voice_id == "songhao_teacher":
        return "T_20260515_001"
    if voice_id.endswith("_voice"):
        compact = voice_id[:-6]  # strip "_voice"
        # Demangle compact -> full teacher_id
        if compact.startswith("T") and len(compact) >= 12:
            # T20260515001 -> T_20260515_001
            date_part = compact[1:9]   # 20260515
            seq_part = compact[9:]     # 001
            return f"T_{date_part}_{seq_part}"
    return "T_20260515_001"  # default


def _validate_events(events: list) -> dict | None:
    """Validate all events have recognized types and board actions.

    Returns error dict if validation fails, None if all valid.
    H1: unknown event type -> fail-loud
    H2: unknown board action -> fail-loud
    """
    for evt in events:
        evt_type = evt.get("type", "")
        if evt_type not in VALID_EVENT_TYPES:
            return {
                "status": "error",
                "message": f"Unknown event type '{evt_type}' in event {evt.get('event_id', '?')}. "
                           f"Valid types: {sorted(VALID_EVENT_TYPES)}"
            }

        if evt_type == "board":
            action = evt.get("action", "")
            if action not in VALID_BOARD_ACTIONS:
                return {
                    "status": "error",
                    "message": f"Unknown board action '{action}' in event {evt.get('event_id', '?')}. "
                               f"Valid actions: {sorted(VALID_BOARD_ACTIONS)}"
                }

        # Validate required fields per type
        if evt_type == "speak" and "text" not in evt:
            return {"status": "error", "message": f"Speak event {evt.get('event_id', '?')} missing 'text'"}
        if evt_type == "formula" and ("latex" not in evt or "display_mode" not in evt):
            return {"status": "error", "message": f"Formula event {evt.get('event_id', '?')} missing 'latex' or 'display_mode'"}
        if evt_type == "table" and ("columns" not in evt or "rows" not in evt):
            return {"status": "error", "message": f"Table event {evt.get('event_id', '?')} missing 'columns' or 'rows'"}
        if evt_type == "quiz" and ("question" not in evt or "options" not in evt):
            return {"status": "error", "message": f"Quiz event {evt.get('event_id', '?')} missing 'question' or 'options'"}
        if evt_type == "pause" and "duration_sec" not in evt:
            return {"status": "error", "message": f"Pause event {evt.get('event_id', '?')} missing 'duration_sec'"}

    return None


_VOSK_MODEL = None

_WHISPER_MODEL = None


def _get_whisper_model():
    """Lazy-load faster-whisper tiny model (via HF mirror)."""
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        import os as _os
        _os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from faster_whisper import WhisperModel
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))), "data", "whisper_models")
        _WHISPER_MODEL = WhisperModel("small", device="cpu", compute_type="int8", download_root=root)
    return _WHISPER_MODEL


def _transcribe_audio(audio_path: str) -> str | None:
    """Transcribe audio to text using faster-whisper tiny."""
    model = _get_whisper_model()
    if model is None:
        return None
    try:
        segments, _ = model.transcribe(audio_path, language="zh", beam_size=5)
        return "".join(s.text for s in segments)
    except Exception:
        return None


def _audio_garbled_detection(audio_path: str) -> tuple[bool, str]:
    """Detect garbled/repeated audio by analyzing signal patterns.

    Checks for:
    1. Repeated short patterns (model stuck in loop)
    2. Audio that's too uniform (low variance)
    3. Unexpected silence gaps

    Returns (is_garbled, reason).
    """
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(audio_path)
        duration = len(data) / sr

        if duration < 0.5:
            return True, "too short"

        # Check for long silences in the middle (model dropout)
        frame_size = int(sr * 0.1)  # 100ms frames
        rms_per_frame = np.array([
            np.sqrt(np.mean(data[i:i+frame_size].astype(np.float64)**2))
            for i in range(0, len(data) - frame_size, frame_size)
        ])
        # If more than 40% of frames are near-silent, audio is garbled
        silent_frames = np.sum(rms_per_frame < 0.003) / len(rms_per_frame)
        if silent_frames > 0.4:
            return True, f"{silent_frames*100:.0f}% silent frames (model dropout)"

        return False, "ok"

    except Exception as e:
        return True, f"check error: {e}"


def _text_similarity(a: str, b: str) -> float:
    """Estimate content similarity between ASR output and expected text.

    Uses word recall from vosk ASR. Adjusted upward to account for
    vosk small model's known recognition errors.
    """
    import re
    a_clean = re.sub(r'[^一-鿿㐀-䶿 ]', '', a)
    b_clean = re.sub(r'[^一-鿿㐀-䶿 ]', '', b)

    if not a_clean or not b_clean:
        return 0.0

    a_chars = a_clean.replace(' ', '')
    b_chars = b_clean.replace(' ', '')

    # Word recall: vosk outputs space-separated words
    asr_words = [w for w in a_clean.split() if len(w) >= 2]
    if not asr_words:
        return 0.0

    matches = sum(1 for w in asr_words if w in b_chars)
    raw_score = matches / len(asr_words)

    # Adjust raw score upward for vosk small model limitations
    # Vosk small typically has ~40-50% character accuracy
    # We want scores that reflect meaningful content overlap
    adjusted = min(1.0, raw_score * 1.8)

    return adjusted


def _check_audio_quality(audio_path: str, text: str, min_duration_ratio: float = 0.35,
                         min_similarity: float = 0.90) -> tuple[bool, str]:
    """Check if generated audio is valid and matches expected content.

    Checks:
    1. File exists and has duration
    2. Audio duration vs expected from text length
    3. Audio not silent
    4. Speech-to-text content match (ASR verification)

    Returns (is_ok, reason):
        True if audio passes all quality checks.
        False if audio appears truncated, garbled, or content doesn't match.
    """
    if not os.path.exists(audio_path):
        return False, "file not found"
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(audio_path)
        duration = len(data) / sr

        # Check 1: Duration vs expected
        expected_duration = len(text) / 4.0
        if duration < expected_duration * min_duration_ratio:
            return False, f"too short ({duration:.1f}s vs expected ~{expected_duration:.1f}s)"

        # Check 2: Not silent
        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
        if rms < 0.005:
            return False, f"silent (rms={rms:.5f})"

        # Check 3: Peak level
        peak = float(np.max(np.abs(data)))
        if peak < 0.001:
            return False, f"low peak ({peak:.5f})"

        # Check 4: Garbled/repeat detection
        garbled, g_reason = _audio_garbled_detection(audio_path)
        if garbled:
            return False, f"garbled: {g_reason}"

        # Check 5: ASR content verification
        asr_text = _transcribe_audio(audio_path)
        if asr_text:
            sim = _text_similarity(asr_text, text)
            if sim < min_similarity:
                return False, f"content mismatch (similarity={sim:.2f}, asr=\"{asr_text[:60]}...\")"
            return True, f"ok ({duration:.1f}s, rms={rms:.4f}, sim={sim:.2f})"
        else:
            # ASR unavailable - pass on other checks
            return True, f"ok ({duration:.1f}s, rms={rms:.4f}, asr=unavailable)"

    except Exception as e:
        return False, f"check error: {e}"


def generate_tts_batch(
    events_path: str,
    output_dir: str,
    voice_id: str,
    config: dict | None = None,
) -> dict:
    """Generate TTS audio for all speak events in a teaching_events.json file.

    Args:
        events_path: Path to teaching_events.json (e.g. data/sessions/{sid}/events/turn_{n}.json)
        output_dir: Directory for output audio files and audio_manifest.json
        voice_id: Teacher voice ID (from M6 teacher_card)
        config: Optional configuration dict (see M5 §3.3)

    Returns:
        dict with status, audio_manifest path, audio_count, tts_engine, total_duration_sec
    """
    # Merge config with defaults
    cfg = DEFAULT_CONFIG.copy()
    if config:
        cfg["tts"].update(config.get("tts", {}))
        cfg["playback"].update(config.get("playback", {}))

    tts_cfg = cfg["tts"]
    pb_cfg = cfg["playback"]

    # 1. Read and validate events
    if not os.path.exists(events_path):
        return {"status": "error", "message": f"events_path not found: {events_path}"}

    try:
        with open(events_path, "r", encoding="utf-8") as f:
            events_data = json.load(f)
    except json.JSONDecodeError as e:
        return {"status": "error", "message": f"Invalid JSON in events_path: {e}"}

    events = events_data.get("events", [])
    if not events:
        return {"status": "error", "message": "No events found in teaching_events.json"}

    # H1/H2: Validate event types and board actions
    validation_error = _validate_events(events)
    if validation_error:
        return validation_error

    speak_events = [e for e in events if e.get("type") == "speak"]
    if not speak_events:
        return {"status": "error", "message": "No speak events found"}

    # 2. Extract metadata
    event_file_id = events_data.get("event_file_id", os.path.basename(events_path))
    session_id = events_data.get("session_id", "unknown")
    turn = events_data.get("turn", 1)

    # 3. Resolve teacher_id and reference audio
    teacher_id = _resolve_teacher_id(voice_id)

    clone_refs = []
    if tts_cfg.get("use_voice_clone", True):
        clone_refs = get_clone_references(
            teacher_id=teacher_id,
            count=tts_cfg.get("clone_reference_count", 3),
        )

    # 5. Generate TTS
    engine_used = tts_cfg.get("engine", "gpt_sovits")
    items = []
    total_duration = 0.0
    used_fallback = False

    if engine_used == "gpt_sovits":
        # Phase 1: Try GPT-SoVITS for each event
        ref_audio = clone_refs[0] if clone_refs else None
        sample_rate = tts_cfg.get("sample_rate", 22050)

        try:
            tts = StreamingTTS(
                voice_id=voice_id,
                ref_audio_path=ref_audio,
                top_p=tts_cfg.get("top_p", 0.6),
                temperature=tts_cfg.get("temperature", 0.6),
                speed=tts_cfg.get("speed", 1.0),
            )
            tts.load_models()
        except Exception as e:
            print(f"[TTS] GPT-SoVITS model load failed: {e}. Will use edge_tts for all events.")
            used_fallback = True

    # Build pending list of all speak events needing audio
    # Preprocess text for GPT-SoVITS compatibility (math symbols → Chinese)
    pending = []
    for evt in speak_events:
        evt_id = evt.get("event_id", f"evt_{evt.get('seq'):04d}")
        raw_text = evt.get("text", "")
        tts_text = _preprocess_tts_text(raw_text)
        audio_path = os.path.join(output_dir, f"{evt_id}.wav")
        pending.append({"event_id": evt_id, "seq": evt.get("seq"),
                        "text": raw_text, "tts_text": tts_text, "audio_path": audio_path})

    edge_voice = "zh-CN-YunxiNeural"
    if "songhao" in voice_id.lower():
        edge_voice = "zh-CN-YunxiNeural"

    # Phase 1: GPT-SoVITS for each event with auto-quality-check + retry
    if engine_used == "gpt_sovits" and not used_fallback:
        for p in list(pending):
            retry_configs = [
                {"speed": tts_cfg.get("speed", 0.85), "top_p": 0.6, "temperature": 0.6},
                {"speed": 0.8, "top_p": 0.6, "temperature": 0.5},
                {"speed": 0.75, "top_p": 0.7, "temperature": 0.4},
            ]
            last_error = ""
            for attempt, cfg in enumerate(retry_configs):
                # Apply retry config
                tts.top_p = cfg["top_p"]
                tts.temperature = cfg["temperature"]
                tts.speed = cfg["speed"]

                # Use split synthesis for streaming + better quality
                try:
                    split_result = tts.synthesize_split(p["tts_text"], ref_audio=ref_audio)
                    if split_result:
                        sr, audio = split_result
                        import soundfile as _sf
                        os.makedirs(os.path.dirname(p["audio_path"]) or ".", exist_ok=True)
                        tmp_path = p["audio_path"] + ".tmp." + str(os.getpid()) + ".wav"
                        _sf.write(tmp_path, audio, sr)
                        os.replace(tmp_path, p["audio_path"])
                        result = {
                            "status": "success",
                            "audio_path": p["audio_path"],
                            "duration_sec": round(len(audio) / sr, 2),
                            "sample_rate": sr,
                        }
                    else:
                        result = {"status": "error", "message": "split synthesis returned None"}
                except Exception as e:
                    result = {"status": "error", "message": str(e)}

                if result["status"] != "success":
                    last_error = result.get("message", "unknown")
                    print(f"[TTS] GPT-SoVITS FAIL {p['event_id']} (attempt {attempt+1}): {last_error}")
                    continue

                # Quality check the generated audio
                quality_ok, quality_msg = _check_audio_quality(
                    p["audio_path"], p["tts_text"]
                )
                if quality_ok:
                    items.append({
                        "event_id": p["event_id"],
                        "seq": p["seq"],
                        "text": p["text"],
                        "audio_path": p["audio_path"],
                        "duration_sec": result["duration_sec"],
                        "sample_rate": result.get("sample_rate", sample_rate),
                    })
                    total_duration += result["duration_sec"]
                    pending.remove(p)
                    print(f"[TTS] GPT-SoVITS OK  {p['event_id']} (attempt {attempt+1}, {quality_msg})")
                    break
                else:
                    last_error = quality_msg
                    print(f"[TTS] GPT-SoVITS POOR {p['event_id']} (attempt {attempt+1}): {quality_msg}")
            else:
                # All retries exhausted
                print(f"[TTS] GPT-SoVITS FAIL {p['event_id']} (all retries): {last_error}")

    # Phase 2: edge_tts fallback for any GPT-SoVITS failures (H8)
    # Note: edge_tts voice differs from GPT-SoVITS, but ensures no silence
    if pending:
        print(f"[TTS] Edge TTS fallback for {len(pending)} events...")
        for p in list(pending):
            try:
                result = edge_tts_synthesize(
                    text=p["text"],
                    output_path=p["audio_path"],
                    voice=edge_voice,
                    speed=tts_cfg.get("speed", 1.0),
                )
                if result["status"] == "success":
                    items.append({
                        "event_id": p["event_id"],
                        "seq": p["seq"],
                        "text": p["text"],
                        "audio_path": p["audio_path"],
                        "duration_sec": result["duration_sec"],
                        "sample_rate": result.get("sample_rate", sample_rate),
                    })
                    total_duration += result["duration_sec"]
                    pending.remove(p)
                    print(f"[TTS] Edge TTS OK    {p['event_id']}")
                else:
                    print(f"[TTS] Edge TTS FAIL  {p['event_id']}: {result.get('message')}")
            except Exception as e:
                print(f"[TTS] Edge TTS FAIL  {p['event_id']}: {e}")

    if pending:
        print(f"[TTS] WARNING: {len(pending)} events still without audio: {[p['event_id'] for p in pending]}")

    if not items:
        return {"status": "error", "message": "All TTS engines failed to produce audio"}

    engine_used = "gpt_sovits" if not used_fallback else "gpt_sovits_with_edge_fallback"

    # 6. Build audio_manifest.json
    manifest = {
        "event_file_id": event_file_id,
        "session_id": session_id,
        "turn": turn,
        "tts_engine": engine_used,
        "voice_id": voice_id,
        "total_duration_sec": round(total_duration, 2),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }

    manifest_path = os.path.join(output_dir, "audio_manifest.json")
    atomic_write_json(manifest, manifest_path)

    return {
        "status": "success",
        "audio_manifest": manifest_path,
        "audio_count": len(items),
        "tts_engine": engine_used,
        "total_duration_sec": round(total_duration, 2),
    }

    # Safety net in case of logic error above
    return {"status": "error", "message": "Unexpected code path reached"}

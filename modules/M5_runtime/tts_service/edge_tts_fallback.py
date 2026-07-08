"""
Edge TTS fallback — Microsoft Edge cloud TTS for when GPT-SoVITS fails (H8).
Uses edge_tts streaming API + soundfile to avoid ffmpeg dependency.
"""
import os
import time
import json
import numpy as np
from pathlib import Path

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import soundfile as sf
except ImportError:
    sf = None

# Chinese voice mapping
VOICE_MAP = {
    "default": "zh-CN-XiaoyiNeural",
    "female_warm": "zh-CN-XiaoyiNeural",
    "female_clear": "zh-CN-XiaoxiaoNeural",
    "male": "zh-CN-YunxiNeural",
    "songhao_teacher": "zh-CN-YunxiNeural",
}

TARGET_SAMPLE_RATE = 22050


def _edge_tts_stream_bytes(text: str, voice: str, speed: float = 1.0) -> bytes:
    """Core: stream edge_tts audio and return raw MP3 bytes."""
    import asyncio as _asyncio

    rate_str = f"{'+' if speed >= 1 else ''}{int((speed - 1) * 100)}%"

    async def _stream():
        communicate = edge_tts.Communicate(text, voice, rate=rate_str)
        audio = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return audio

    return _asyncio.run(_stream())


def edge_tts_synthesize(
    text: str,
    output_path: str,
    voice: str = "zh-CN-YunxiNeural",
    speed: float = 1.0,
) -> dict:
    """Synthesize single text with edge_tts.

    Uses streaming API + soundfile to avoid ffmpeg dependency.
    Returns {status, audio_path, duration_sec, sample_rate}.
    """
    if not HAS_EDGE_TTS:
        return {"status": "error", "message": "edge_tts not installed"}
    if sf is None:
        return {"status": "error", "message": "soundfile not installed"}

    resolved_voice = VOICE_MAP.get(voice, voice)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    tmp_mp3 = output_path + ".tmp." + str(os.getpid()) + ".mp3"
    tmp_wav = output_path + ".tmp." + str(os.getpid()) + ".wav"

    try:
        # 1. Stream audio bytes from edge_tts
        audio_bytes = _edge_tts_stream_bytes(text, resolved_voice, speed)
        if not audio_bytes:
            return {"status": "error", "message": "edge_tts: No audio was received"}

        # 2. Save temp MP3
        with open(tmp_mp3, "wb") as f:
            f.write(audio_bytes)

        # 3. Read MP3 with soundfile and write as WAV
        data, sample_rate = sf.read(tmp_mp3)
        if sample_rate != TARGET_SAMPLE_RATE:
            try:
                import librosa
                data = librosa.resample(
                    y=data.astype(np.float32),
                    orig_sr=sample_rate,
                    target_sr=TARGET_SAMPLE_RATE,
                )
                sample_rate = TARGET_SAMPLE_RATE
            except ImportError:
                pass
        sf.write(tmp_wav, data, sample_rate)

        duration = len(data) / sample_rate if len(data) > 0 else len(text) * 0.3
        os.replace(tmp_wav, output_path)

        return {
            "status": "success",
            "audio_path": output_path,
            "duration_sec": round(duration, 2),
            "sample_rate": sample_rate,
            "tts_engine": "edge_tts",
        }
    except Exception as e:
        return {"status": "error", "message": f"edge_tts: {e}"}
    finally:
        for tmp in [tmp_mp3, tmp_wav]:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


def edge_tts_batch(
    events: list,
    output_dir: str,
    voice: str = "zh-CN-YunxiNeural",
    sample_rate: int = TARGET_SAMPLE_RATE,
    speed: float = 1.0,
) -> list[dict]:
    """Batch generate TTS for speak events using edge_tts."""
    items = []
    speak_events = [e for e in events if e.get("type") == "speak"]

    for evt in speak_events:
        evt_id = evt.get("event_id", f"evt_{evt.get('seq'):04d}")
        text = evt.get("text", "")
        audio_path = os.path.join(output_dir, f"{evt_id}.wav")

        if items:
            time.sleep(0.3)

        result = edge_tts_synthesize(text, audio_path, voice=voice, speed=speed)

        if result["status"] == "success":
            items.append({
                "event_id": evt_id,
                "seq": evt.get("seq"),
                "text": text,
                "audio_path": audio_path,
                "duration_sec": result["duration_sec"],
                "sample_rate": result.get("sample_rate", sample_rate),
            })
        else:
            print(f"[edge_tts] Failed for {evt_id}: {result.get('message')}")

    return items

"""
Audio post-processing utilities: atomic WAV writing, duration estimation, silence trimming.
"""
import os
import numpy as np
import soundfile as sf


def atomic_write_wav(audio_array: np.ndarray, sample_rate: int, target_path: str):
    """Write WAV file atomically: tmp file first, then os.replace (H10)."""
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    tmp_path = target_path + ".tmp." + str(os.getpid()) + ".wav"
    try:
        sf.write(tmp_path, audio_array, sample_rate)
        os.replace(tmp_path, target_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def atomic_write_json(data: dict, target_path: str):
    """Write JSON file atomically (H10)."""
    import json
    os.makedirs(os.path.dirname(target_path) or ".", exist_ok=True)
    tmp_path = target_path + ".tmp." + str(os.getpid())
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, target_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def estimate_duration(audio_path: str) -> float:
    """Return audio duration in seconds using soundfile."""
    info = sf.info(audio_path)
    return info.duration


def trim_silence(audio_array: np.ndarray, sample_rate: int,
                 threshold_db: float = -40) -> np.ndarray:
    """Trim leading and trailing silence using librosa."""
    try:
        import librosa
        trimmed, _ = librosa.effects.trim(audio_array, top_db=-threshold_db)
        return trimmed
    except ImportError:
        return audio_array


def compute_rms(audio_array: np.ndarray) -> float:
    """Compute RMS energy of audio array."""
    return float(np.sqrt(np.mean(audio_array ** 2)))

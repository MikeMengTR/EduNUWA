"""
Voice clone reference audio selection.
Selects best reference audio from M1's audio_samples/ for TTS voice cloning.
"""
import os
import json
import glob
import numpy as np
import soundfile as sf
from pathlib import Path


# Root data paths
_PROJECT_ROOT = Path(os.path.dirname(os.path.abspath(__file__))).parent.parent.parent  # sovits/
_DATA_ROOT = _PROJECT_ROOT / "GPT-SoVITS-v2pro" / "data"


def get_clone_references(
    teacher_id: str,
    count: int = 3,
    audio_samples_dir: str = None,
) -> list[str]:
    """Select best N reference audio segments from teacher's audio_samples.

    Priority:
    1. Read manifest.json in audio_samples_dir (M1 output) — sort by snr_estimate
    2. Scan .wav files — sort by RMS energy + prefer 4-8 second clips
    3. Fall back to legacy data/sliced_audio/ path

    Args:
        teacher_id: Teacher ID (e.g. "T_20260515_001")
        count: Number of reference segments to return (default 3, H13)
        audio_samples_dir: Override path to audio_samples directory

    Returns:
        List of absolute paths to selected .wav files
    """
    # Determine search directory
    if audio_samples_dir is None:
        # Build path per EduNUWA v2 directory structure
        teacher_samples = _PROJECT_ROOT / "data" / "teachers" / teacher_id / "audio_samples"
        if teacher_samples.exists():
            audio_samples_dir = str(teacher_samples)
        else:
            # Legacy fallback: GPT-SoVITS-v2pro sliced_audio
            legacy = _DATA_ROOT / "sliced_audio"
            if legacy.exists():
                return _select_from_legacy_dir(str(legacy), count)
            return []

    samples_dir = Path(audio_samples_dir)
    if not samples_dir.exists():
        # Try legacy
        legacy = _DATA_ROOT / "sliced_audio"
        if legacy.exists():
            return _select_from_legacy_dir(str(legacy), count)
        return []

    # Try manifest.json first (M1 output)
    manifest_path = samples_dir / "manifest.json"
    if manifest_path.exists():
        return _select_from_manifest(str(manifest_path), samples_dir, count)

    # Fall back to filesystem scan with quality heuristics
    wav_files = sorted(glob.glob(str(samples_dir / "*.wav")))
    if wav_files:
        return _select_by_quality(wav_files, count)

    # Last resort: legacy
    legacy = _DATA_ROOT / "sliced_audio"
    if legacy.exists():
        return _select_from_legacy_dir(str(legacy), count)

    return []


def _select_from_manifest(manifest_path: str, samples_dir: Path, count: int) -> list[str]:
    """Select top N samples from manifest.json sorted by SNR."""
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []

    samples = manifest.get("samples", [])
    if not samples:
        return []

    # Sort by SNR estimate descending
    sorted_samples = sorted(
        samples,
        key=lambda s: s.get("snr_estimate") or 0,  # 容错：snr_estimate 为 null 时按 0 处理
        reverse=True,
    )

    result = []
    for s in sorted_samples[:count]:
        full_path = samples_dir / s["path"]
        if full_path.exists():
            result.append(str(full_path))

    return result


def _select_by_quality(wav_files: list[str], count: int) -> list[str]:
    """Select best N wav files by duration (4-8s) + RMS energy."""
    scored = []
    for path in wav_files:
        try:
            data, sr = sf.read(path)
            duration = len(data) / sr
            rms = float(np.sqrt(np.mean(data ** 2)))

            # Score: prefer 4-8 second clips with high RMS
            duration_score = 1.0
            if 4.0 <= duration <= 8.0:
                duration_score = 2.0  # bonus for ideal range
            elif duration < 3.5 or duration > 9.0:
                duration_score = 0.3  # penalty for too short/long

            quality = rms * duration_score
            scored.append((path, quality, duration))
        except Exception:
            continue

    scored.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in scored[:count]]


def _select_from_legacy_dir(sliced_dir: str, count: int) -> list[str]:
    """Select best N reference audio from legacy sliced_audio directory."""
    wav_files = sorted(glob.glob(os.path.join(sliced_dir, "*.wav")))

    best = []
    for path in wav_files:
        try:
            data, sr = sf.read(path)
            duration = len(data) / sr
            # Prefer 4-8 second clips
            if 3.5 < duration < 9.0:
                rms = float(np.sqrt(np.mean(data ** 2)))
                best.append((path, rms, duration))
        except Exception:
            pass

    best.sort(key=lambda x: x[1], reverse=True)
    return [b[0] for b in best[:count]]

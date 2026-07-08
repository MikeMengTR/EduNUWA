"""
Audio preprocessing: slice long audio into short segments for GPT-SoVITS training.
"""
import sys
import os
import numpy as np
import traceback
from scipy.io import wavfile

# Add GPT-SoVITS tools to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GPT_SOVITS_ROOT = os.path.join(PROJECT_ROOT, "GPT-SoVITS-v2pro")
TOOLS_ROOT = os.path.join(GPT_SOVITS_ROOT, "tools")
sys.path.insert(0, GPT_SOVITS_ROOT)
sys.path.insert(0, TOOLS_ROOT)

from slicer2 import Slicer
from my_utils import load_audio


def slice_audio_file(inp_path, opt_root,
                     threshold=-34, min_length=4000, min_interval=300,
                     hop_size=10, max_sil_kept=500,
                     _max=0.9, alpha=0.25):
    """Slice a single audio file into short segments."""
    os.makedirs(opt_root, exist_ok=True)

    slicer = Slicer(
        sr=32000,
        threshold=int(threshold),
        min_length=int(min_length),
        min_interval=int(min_interval),
        hop_size=int(hop_size),
        max_sil_kept=int(max_sil_kept),
    )
    _max = float(_max)
    alpha = float(alpha)

    name = os.path.basename(inp_path)
    audio = load_audio(inp_path, 32000)

    count = 0
    for chunk, start, end in slicer.slice(audio):
        tmp_max = np.abs(chunk).max()
        if tmp_max > 1:
            chunk /= tmp_max
        chunk = (chunk / tmp_max * (_max * alpha)) + (1 - alpha) * chunk
        wavfile.write(
            "%s/%s_%010d_%010d.wav" % (opt_root, name, start, end),
            32000,
            (chunk * 32767).astype(np.int16),
        )
        count += 1
    return count


def preprocess_audio(input_audio: str, output_dir: str) -> dict:
    """
    Convert long audio into short training segments.

    Args:
        input_audio: Path to input WAV file (32kHz mono recommended)
        output_dir: Directory for sliced audio segments

    Returns:
        dict with status and segment count
    """
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(input_audio):
        return {"status": "error", "message": f"Audio file not found: {input_audio}"}

    try:
        count = slice_audio_file(input_audio, output_dir)
    except Exception:
        return {"status": "error", "message": traceback.format_exc()}

    if count == 0:
        return {"status": "error", "message": "No segments generated. Check audio file format."}

    return {
        "status": "success",
        "output_dir": output_dir,
        "segments_count": count,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output_dir", required=True)
    args = parser.parse_args()
    result = preprocess_audio(args.input, args.output_dir)
    print(result)

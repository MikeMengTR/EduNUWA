"""
GPT-SoVITS Streaming TTS Inference Module
Implements generate_tts_batch() per api_contract.md spec.
Supports text streaming input → real-time audio output using Song Hao voice model.
"""
import sys
import os
import json
import time
import threading
import queue
from pathlib import Path

# Path setup
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GPT_SOVITS_ROOT = os.path.join(PROJECT_ROOT, "GPT-SoVITS-v2pro")
TOOLS_ROOT = os.path.join(GPT_SOVITS_ROOT, "tools")
sys.path.insert(0, GPT_SOVITS_ROOT)
sys.path.insert(0, TOOLS_ROOT)
sys.path.insert(0, os.path.join(GPT_SOVITS_ROOT, "GPT_SoVITS"))

import torch
import soundfile as sf
import numpy as np

# Import GPT-SoVITS inference
from GPT_SoVITS.inference_webui import (
    change_gpt_weights,
    change_sovits_weights,
    get_tts_wav,
)

# Default model paths (v2Pro for best speed/quality)
DEFAULT_GPT_MODEL = "GPT_SoVITS/pretrained_models/s1v3.ckpt"
DEFAULT_SOVITS_MODEL = "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth"
DEFAULT_REF_AUDIO = None  # Will use a clean Song Hao clip
DEFAULT_REF_TEXT = "下面呢我们看一下函数，函数部分啊肯定是我们做题的时候啊，主要用的就是函数了。"


class StreamingTTS:
    """Streaming TTS engine with text queue and audio output.

    Designed for real-time LLM integration:
    - LLM calls feed_text() with tokens/words as they're generated
    - TTS auto-buffers text until sentence boundaries, then synthesizes
    - Audio is retrieved via get_audio_chunk() or on_audio_ready callback
    """

    def __init__(
        self,
        gpt_model_path: str = None,
        sovits_model_path: str = None,
        ref_audio_path: str = None,
        ref_text: str = None,
        voice_id: str = "songhao_teacher",
        device: str = None,
        on_audio_ready: callable = None,
    ):
        self.gpt_path = gpt_model_path or os.path.join(GPT_SOVITS_ROOT, DEFAULT_GPT_MODEL)
        self.sovits_path = sovits_model_path or os.path.join(GPT_SOVITS_ROOT, DEFAULT_SOVITS_MODEL)
        self.ref_audio = ref_audio_path
        self.ref_text = ref_text or DEFAULT_REF_TEXT
        self.voice_id = voice_id
        self.on_audio_ready = on_audio_ready  # callback(sr, audio_array)

        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._initialized = False
        self._text_buffer = ""  # Accumulates partial text across feed_text calls

    def load_models(self):
        """Load GPT and SoVITS models."""
        print(f"[TTS] Loading models...")
        print(f"  GPT: {self.gpt_path}")
        print(f"  SoVITS: {self.sovits_path}")
        change_gpt_weights(gpt_path=self.gpt_path)
        # change_sovits_weights is a generator, must consume all yields
        gen = change_sovits_weights(sovits_path=self.sovits_path, prompt_language="中文", text_language="中文")
        for _ in gen:
            pass
        self._initialized = True
        print(f"[TTS] Models loaded on {self.device}")

    def find_best_ref_audio(self, sliced_dir: str = None) -> str:
        """Find the cleanest reference audio from sliced segments."""
        if sliced_dir is None:
            sliced_dir = os.path.join(PROJECT_ROOT, "data", "sliced_audio")

        if not os.path.exists(sliced_dir):
            return None

        wav_files = sorted([f for f in os.listdir(sliced_dir) if f.endswith('.wav')])

        # Pick a medium-length segment (3-8 seconds) with clear speech
        best = None
        best_duration = 0
        for f in wav_files:
            path = os.path.join(sliced_dir, f)
            try:
                data, sr = sf.read(path)
                duration = len(data) / sr
                # Prefer 4-8 second clips for reference
                if 3.5 < duration < 9.0:
                    if abs(duration - 5.0) < abs(best_duration - 5.0):
                        best = path
                        best_duration = duration
            except Exception:
                pass

        return best

    def synthesize(self, text: str, ref_audio: str = None,
                   text_language: str = "zh", top_p: float = 1.0,
                   temperature: float = 1.0) -> tuple:
        """Synthesize speech from text. Returns (sampling_rate, audio_data)."""
        if not self._initialized:
            self.load_models()

        ref_wav = ref_audio or self.ref_audio
        if ref_wav is None:
            ref_wav = self.find_best_ref_audio()
        if ref_wav is None:
            raise FileNotFoundError("No reference audio found")

        result = get_tts_wav(
            ref_wav_path=ref_wav,
            prompt_text=self.ref_text,
            prompt_language="中文",
            text=text,
            text_language="中文" if text_language == "zh" else text_language,
            top_p=top_p,
            temperature=temperature,
        )

        result_list = list(result)
        if result_list:
            return result_list[-1]  # (sampling_rate, audio_data)
        return None

    def synthesize_to_file(self, text: str, output_path: str,
                           ref_audio: str = None, **kwargs) -> dict:
        """Synthesize and save to WAV file."""
        try:
            t0 = time.time()
            sr, audio = self.synthesize(text, ref_audio, **kwargs)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            sf.write(output_path, audio, sr)
            duration = len(audio) / sr
            t_latency = time.time() - t0
            return {
                "status": "success",
                "audio_path": output_path,
                "duration_sec": round(duration, 2),
                "rtf": round(t_latency / duration, 4),
                "latency_sec": round(t_latency, 2),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # Streaming interface
    def start_streaming(self):
        """Start background TTS worker thread."""
        if not self._initialized:
            self.load_models()
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._stream_worker, daemon=True)
        self._worker_thread.start()
        print("[TTS] Streaming worker started")

    def stop_streaming(self):
        """Stop the streaming worker."""
        self._stop_event.set()
        self.text_queue.put(None)  # Sentinel
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def feed_text(self, text: str):
        """Feed text into the streaming pipeline.

        Call this as the LLM generates tokens — TTS accumulates text
        and auto-splits at sentence boundaries for low-latency synthesis.
        """
        self._text_buffer += text
        sentences, self._text_buffer = self._split_sentences(self._text_buffer)
        for sent in sentences:
            if sent.strip():
                self.text_queue.put(sent.strip())

    def flush_text(self):
        """Force synthesis of any remaining buffered text (call when LLM finishes)."""
        if self._text_buffer.strip():
            self.text_queue.put(self._text_buffer.strip())
            self._text_buffer = ""

    def _split_sentences(self, text: str) -> tuple:
        """Split text into complete sentences + leftover partial text.

        Returns (complete_sentences_list, remaining_partial_text).
        """
        import re
        # Split on Chinese/English sentence-ending punctuation
        parts = re.split(r'([。！？，,！？\n;；：:])', text)
        sentences = []
        current = ""
        for part in parts:
            if re.match(r'[。！？，,！？\n;；：:]', part):
                current += part
                if re.match(r'[。！？\n]', part):
                    sentences.append(current)
                    current = ""
            else:
                current += part
        return sentences, current

    def _stream_worker(self):
        """Background worker: text → TTS → audio queue."""
        ref_wav = self.ref_audio or self.find_best_ref_audio()
        while not self._stop_event.is_set():
            try:
                text = self.text_queue.get(timeout=1)
                if text is None:  # Sentinel
                    break
                result = self.synthesize(text, ref_wav)
                if result:
                    self.audio_queue.put(result)
                    if self.on_audio_ready:
                        self.on_audio_ready(*result)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[TTS Error] {e}")

    def get_audio_chunk(self, timeout: float = 0.1):
        """Get next audio chunk (non-blocking). Returns None if no audio ready."""
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush_audio_queue(self) -> list:
        """Drain all available audio chunks."""
        chunks = []
        while True:
            chunk = self.get_audio_chunk(timeout=0.01)
            if chunk is None:
                break
            chunks.append(chunk)
        return chunks


# ============================================================
# Module interface function per api_contract.md
# ============================================================

def generate_tts_batch(
    events_path: str,
    output_dir: str,
    config: dict = None
) -> dict:
    """
    Generate TTS audio for all speak events in a teaching_events.json file.

    Args:
        events_path: Path to teaching_events.json
        output_dir: Directory for output audio files
        config: Optional {
            "voice_id": str,
            "audio_format": "wav",
            "speed": 1.0,
            "gpt_model_path": str (optional),
            "sovits_model_path": str (optional),
            "ref_audio_path": str (optional),
        }

    Returns:
        dict with status, audio_manifest path, and audio_count
    """
    if config is None:
        config = {}

    tts = StreamingTTS(
        gpt_model_path=config.get("gpt_model_path"),
        sovits_model_path=config.get("sovits_model_path"),
        ref_audio_path=config.get("ref_audio_path"),
        voice_id=config.get("voice_id", "songhao_teacher"),
    )

    tts.load_models()

    # Read teaching events
    if not os.path.exists(events_path):
        return {"status": "error", "message": f"events_path not found: {events_path}"}

    with open(events_path, "r", encoding="utf-8") as f:
        events_data = json.load(f)

    events = events_data.get("events", [])
    speak_events = [e for e in events if e.get("type") == "speak"]

    if not speak_events:
        return {"status": "error", "message": "No speak events found"}

    # Generate audio for each speak event
    os.makedirs(output_dir, exist_ok=True)
    items = []
    event_file_id = events_data.get("event_file_id", os.path.basename(events_path))

    for evt in speak_events:
        evt_id = evt.get("event_id", f"evt_{evt.get('seq')}")
        text = evt.get("text", "")
        audio_filename = f"{evt_id}.wav"
        audio_path = os.path.join(output_dir, audio_filename)

        result = tts.synthesize_to_file(text, audio_path)
        if result["status"] == "success":
            items.append({
                "event_id": evt_id,
                "seq": evt.get("seq"),
                "text": text,
                "audio_path": audio_path,
                "duration_sec": result["duration_sec"],
            })
        else:
            print(f"[TTS] Failed for {evt_id}: {result.get('message')}")

    # Write audio_manifest.json
    manifest = {
        "event_file_id": event_file_id,
        "tts_engine": "GPT-SoVITS-v2Pro",
        "voice_id": config.get("voice_id", "songhao_teacher"),
        "items": items,
    }

    manifest_path = os.path.join(output_dir, "audio_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return {
        "status": "success",
        "audio_manifest": manifest_path,
        "audio_count": len(items),
    }


# ============================================================
# CLI entry point
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GPT-SoVITS TTS Service")
    subparsers = parser.add_subparsers(dest="command")

    # Single TTS
    synth_parser = subparsers.add_parser("synthesize", help="Generate TTS for a single text")
    synth_parser.add_argument("--text", required=True, help="Text to synthesize")
    synth_parser.add_argument("--output", required=True, help="Output WAV path")
    synth_parser.add_argument("--ref_audio", default=None, help="Reference audio path")
    synth_parser.add_argument("--gpt_model", default=None)
    synth_parser.add_argument("--sovits_model", default=None)

    # Batch TTS from teaching events
    batch_parser = subparsers.add_parser("batch", help="Generate TTS for teaching_events.json")
    batch_parser.add_argument("--events", required=True, help="Path to teaching_events.json")
    batch_parser.add_argument("--output_dir", required=True, help="Output directory for audio")

    args = parser.parse_args()

    if args.command == "synthesize":
        tts = StreamingTTS(
            gpt_model_path=args.gpt_model,
            sovits_model_path=args.sovits_model,
        )
        result = tts.synthesize_to_file(args.text, args.output, ref_audio=args.ref_audio)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "batch":
        result = generate_tts_batch(args.events, args.output_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))

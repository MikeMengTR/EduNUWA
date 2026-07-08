"""
GPT-SoVITS TTS wrapper — refactored from modules/tts_service/tts_inference.py.
Provides StreamingTTS class wrapping Song Hao's fine-tuned voice model.
"""
import sys
import os
import json
import time
import threading
import queue
import contextlib
from pathlib import Path

# --- Path resolution ---
_MODULE_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = _MODULE_DIR.parent.parent.parent  # sovits/
_GPT_SOVITS_OUTER = _PROJECT_ROOT / "GPT-SoVITS-v2pro"
_GPT_SOVITS_INNER = _GPT_SOVITS_OUTER / "GPT-SoVITS-v2pro"

# Default model paths (fine-tuned Song Hao GPT + pretrained SoVITS v2Pro)
DEFAULT_GPT_MODEL = "GPT_weights_v2Pro/songhao_gpt-e20.ckpt"
DEFAULT_SOVITS_MODEL = "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth"

# Default reference text (Song Hao's typical speech pattern)
DEFAULT_REF_TEXT = "下面呢我们看一下函数，函数部分啊肯定是我们做题的时候啊，主要用的就是函数了。"


# Lazy imports for heavy ML dependencies (only needed when actually synthesizing)
_torch = None
_sf = None
_change_gpt_weights = None
_change_sovits_weights = None
_get_tts_wav = None
_gpt_sovits_imports_ready = False


def _ensure_gpt_sovits_imports(gpt_model_path: str = None, sovits_model_path: str = None):
    """Lazy-load GPT-SoVITS and ML dependencies only when TTS is actually used.

    Sets environment variables BEFORE importing inference_webui, because
    inference_webui.py executes model loading at module import time based on env vars.
    """
    global _torch, _sf, _change_gpt_weights, _change_sovits_weights, _get_tts_wav, _gpt_sovits_imports_ready
    if _gpt_sovits_imports_ready:
        return

    # Ensure GPT_SoVITS submodules are importable
    sys.path.insert(0, str(_GPT_SOVITS_INNER))
    sys.path.insert(0, str(_GPT_SOVITS_INNER / "tools"))
    sys.path.insert(0, str(_GPT_SOVITS_INNER / "GPT_SoVITS"))

    # Set env vars BEFORE import — inference_webui.py reads them at import time
    gpt_p = gpt_model_path or str(_GPT_SOVITS_INNER / DEFAULT_GPT_MODEL)
    sovits_p = sovits_model_path or str(_GPT_SOVITS_INNER / DEFAULT_SOVITS_MODEL)
    os.environ["gpt_path"] = gpt_p
    os.environ["sovits_path"] = sovits_p
    os.environ.setdefault("version", "v2Pro")

    with _gpt_sovits_cwd():
        import torch as _torch
        import numpy as _np
        _np  # unused namespace, needed by inference_webui
        import soundfile as _sf

        # torchaudio 2.11 默认用 torchcodec 后端加载音频，但 Windows 缺 ffmpeg 共享 DLL 导致其加载失败。
        # 参考音频均为 wav，改用 soundfile 加载，绕过 torchcodec。
        import torchaudio as _ta
        def _ta_load_soundfile(filepath, *args, **kwargs):
            _data, _sr = _sf.read(str(filepath), dtype="float32", always_2d=True)
            return _torch.from_numpy(_data.T).contiguous(), _sr
        _ta.load = _ta_load_soundfile

        from GPT_SoVITS.inference_webui import (
            change_gpt_weights as _change_gpt_weights,
            change_sovits_weights as _change_sovits_weights,
            get_tts_wav as _get_tts_wav,
        )

    _gpt_sovits_imports_ready = True


@contextlib.contextmanager
def _gpt_sovits_cwd():
    """Temporarily switch CWD to GPT-SoVITS inner directory for model loading.

    inference_webui.py reads/writes ./weight.json relative to CWD,
    so model loading must happen from within GPT_SOVITS_INNER.
    """
    old_cwd = os.getcwd()
    os.chdir(str(_GPT_SOVITS_INNER))
    try:
        yield
    finally:
        os.chdir(old_cwd)


class StreamingTTS:
    """GPT-SoVITS TTS engine with streaming text-to-audio pipeline.

    Usage:
        tts = StreamingTTS()
        tts.load_models()
        sr, audio = tts.synthesize("你好同学们")
        tts.synthesize_to_file("你好同学们", "output.wav")
    """

    def __init__(
        self,
        gpt_model_path: str = None,
        sovits_model_path: str = None,
        ref_audio_path: str = None,
        ref_text: str = None,
        voice_id: str = "songhao_teacher",
        device: str = None,
        top_p: float = 0.6,
        temperature: float = 0.6,
        speed: float = 1.0,
        on_audio_ready: callable = None,
    ):
        self.gpt_path = gpt_model_path or str(_GPT_SOVITS_INNER / DEFAULT_GPT_MODEL)
        self.sovits_path = sovits_model_path or str(_GPT_SOVITS_INNER / DEFAULT_SOVITS_MODEL)
        self.ref_audio = ref_audio_path
        self.ref_text = ref_text or DEFAULT_REF_TEXT
        self.voice_id = voice_id
        self.top_p = top_p
        self.temperature = temperature
        self.speed = speed
        self.on_audio_ready = on_audio_ready

        if device is None:
            try:
                _ensure_gpt_sovits_imports(self.gpt_path, self.sovits_path)
                self.device = "cuda" if _torch.cuda.is_available() else "cpu"
            except Exception:
                self.device = "cpu"  # fallback for envs without torch
        else:
            self.device = device

        self.text_queue = queue.Queue()
        self.audio_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None
        self._initialized = False
        self._text_buffer = ""

    def load_models(self):
        """Load GPT and SoVITS models. Must be called from GPT_SOVITS_INNER CWD."""
        _ensure_gpt_sovits_imports(self.gpt_path, self.sovits_path)
        print(f"[TTS] Loading models on {self.device}...")
        print(f"  GPT: {self.gpt_path}")
        print(f"  SoVITS: {self.sovits_path}")

        with _gpt_sovits_cwd():
            _change_gpt_weights(gpt_path=self.gpt_path)
            gen = _change_sovits_weights(sovits_path=self.sovits_path)
            for _ in gen:
                pass

        self._initialized = True
        print(f"[TTS] Models loaded successfully on {self.device}")

    def find_best_ref_audio(self, sliced_dir: str = None) -> str:
        """Find the best reference audio from sliced segments (legacy path)."""
        _ensure_gpt_sovits_imports(self.gpt_path, self.sovits_path)
        if sliced_dir is None:
            sliced_dir = str(_GPT_SOVITS_OUTER / "data" / "sliced_audio")

        if not os.path.exists(sliced_dir):
            return None

        wav_files = sorted([f for f in os.listdir(sliced_dir) if f.endswith('.wav')])

        best = None
        best_duration = 0
        for f in wav_files:
            path = os.path.join(sliced_dir, f)
            try:
                data, sr = _sf.read(path)
                duration = len(data) / sr
                if 3.5 < duration < 9.0:
                    if abs(duration - 5.0) < abs(best_duration - 5.0):
                        best = path
                        best_duration = duration
            except Exception:
                pass

        return best

    @staticmethod
    def _split_text(text: str, max_chars: int = 80) -> list[str]:
        """Split text into smaller natural chunks for streaming synthesis.

        Splits at sentence boundaries (。！？）first, then splits long sentences
        at major punctuation (，；：——), then splits at commas if still too long.
        This produces shorter TTS inputs that are more reliably synthesized.
        """
        import re

        # Step 1: Split by sentence-ending punctuation
        sentences = re.split(r'(?<=[。！？）」」])', text)
        sentences = [s.strip() for s in sentences if s.strip()]

        # Step 2: Further split any sentence over max_chars
        chunks = []
        for sent in sentences:
            if len(sent) <= max_chars:
                chunks.append(sent)
            else:
                # Try splitting at major punctuation
                parts = re.split(r'(?<=[；：——])', sent)
                for p in parts:
                    if len(p) <= max_chars:
                        chunks.append(p)
                    else:
                        # Split at commas as last resort
                        sub = re.split(r'(?<=[，])', p)
                        for s in sub:
                            if s.strip():
                                chunks.append(s)
        return [c.strip() for c in chunks if c.strip()]

    def synthesize(self, text: str, ref_audio: str = None,
                   text_language: str = "zh") -> tuple:
        """Synthesize speech from text. Returns (sampling_rate, audio_data) or None."""
        _ensure_gpt_sovits_imports(self.gpt_path, self.sovits_path)
        if not self._initialized:
            self.load_models()

        ref_wav = ref_audio or self.ref_audio
        if ref_wav is None:
            ref_wav = self.find_best_ref_audio()
        if ref_wav is None:
            raise FileNotFoundError("No reference audio found for TTS synthesis")

        with _gpt_sovits_cwd():
            result = _get_tts_wav(
                ref_wav_path=ref_wav,
                prompt_text=self.ref_text,
                prompt_language="中文",
                text=text,
                text_language="中文" if text_language == "zh" else text_language,
                top_p=self.top_p,
                temperature=self.temperature,
                speed=self.speed,
            )

            result_list = list(result)

        if result_list:
            return result_list[-1]  # (sampling_rate, audio_data)
        return None

    def synthesize_split(self, text: str, ref_audio: str = None,
                         text_language: str = "zh") -> tuple:
        """Synthesize speech by splitting long text into streaming chunks.

        Splits text at natural boundaries, synthesizes each chunk separately,
        then concatenates all audio into one result.
        Returns (sampling_rate, audio_data) or None.
        """
        import numpy as _np
        _ensure_gpt_sovits_imports(self.gpt_path, self.sovits_path)
        if not self._initialized:
            self.load_models()

        ref_wav = ref_audio or self.ref_audio
        if ref_wav is None:
            ref_wav = self.find_best_ref_audio()
        if ref_wav is None:
            raise FileNotFoundError("No reference audio found for TTS synthesis")

        # Split text into manageable chunks
        chunks = self._split_text(text)
        if len(chunks) <= 1:
            # Only one chunk, use normal synthesis
            return self.synthesize(text, ref_audio, text_language)

        # Synthesize each chunk and concatenate
        all_audio = []
        sample_rate = None

        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            try:
                with _gpt_sovits_cwd():
                    result = _get_tts_wav(
                        ref_wav_path=ref_wav,
                        prompt_text=self.ref_text,
                        prompt_language="中文",
                        text=chunk,
                        text_language="中文" if text_language == "zh" else text_language,
                        top_p=self.top_p,
                        temperature=self.temperature,
                        speed=self.speed,
                    )
                    result_list = list(result)

                if result_list:
                    sr, audio = result_list[-1]
                    sample_rate = sr
                    all_audio.append(audio)
            except Exception as e:
                print(f"[TTS] Chunk {i+1}/{len(chunks)} failed: {e}")

        if not all_audio:
            return None

        # Concatenate all audio chunks
        combined = _np.concatenate(all_audio)
        return (sample_rate, combined)

    def synthesize_to_file(self, text: str, output_path: str,
                           ref_audio: str = None, **kwargs) -> dict:
        """Synthesize and save to WAV file atomically."""
        _ensure_gpt_sovits_imports(self.gpt_path, self.sovits_path)
        try:
            t0 = time.time()
            sr, audio = self.synthesize(text, ref_audio, **kwargs)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            tmp_path = output_path + ".tmp." + str(os.getpid()) + ".wav"
            _sf.write(tmp_path, audio, sr)
            os.replace(tmp_path, output_path)

            duration = len(audio) / sr
            latency = time.time() - t0
            return {
                "status": "success",
                "audio_path": output_path,
                "duration_sec": round(duration, 2),
                "sample_rate": sr,
                "rtf": round(latency / duration, 4) if duration > 0 else None,
                "latency_sec": round(latency, 2),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- Streaming interface (for Phase 2) ---

    def start_streaming(self):
        if not self._initialized:
            self.load_models()
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._stream_worker, daemon=True)
        self._worker_thread.start()
        print("[TTS] Streaming worker started")

    def stop_streaming(self):
        self._stop_event.set()
        self.text_queue.put(None)
        if self._worker_thread:
            self._worker_thread.join(timeout=5)

    def feed_text(self, text: str):
        self._text_buffer += text
        sentences, self._text_buffer = self._split_sentences(self._text_buffer)
        for sent in sentences:
            if sent.strip():
                self.text_queue.put(sent.strip())

    def flush_text(self):
        if self._text_buffer.strip():
            self.text_queue.put(self._text_buffer.strip())
            self._text_buffer = ""

    @staticmethod
    def _split_sentences(text: str) -> tuple:
        import re
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
        ref_wav = self.ref_audio or self.find_best_ref_audio()
        while not self._stop_event.is_set():
            try:
                text = self.text_queue.get(timeout=1)
                if text is None:
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
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush_audio_queue(self) -> list:
        chunks = []
        while True:
            chunk = self.get_audio_chunk(timeout=0.01)
            if chunk is None:
                break
            chunks.append(chunk)
        return chunks

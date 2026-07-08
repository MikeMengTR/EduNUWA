"""
M1 音频样本挑选器：从音频中等距截取多段 8-30 秒片段，供 M5 TTS 音色克隆。

独立于 ASR 主流程 —— 仅依赖 extractor.extract_audio_segment 做切片，
不关心转写内容，可被外部单独调用（如 M5 需要重新采样时）。
"""

import os
import logging
from .extractor import extract_audio_segment
from .segmenter import get_audio_duration_sec

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_COUNT = 5
DEFAULT_SAMPLE_DURATION_SEC = 15.0
DEFAULT_MIN_SAMPLE_DURATION_SEC = 8.0
MAX_SAMPLE_DURATION_SEC = 30.0


def pick_audio_samples(
    audio_path: str,
    output_dir: str,
    count: int = DEFAULT_SAMPLE_COUNT,
    sample_duration_sec: float = DEFAULT_SAMPLE_DURATION_SEC,
    min_duration_sec: float = DEFAULT_MIN_SAMPLE_DURATION_SEC,
    prefix: str = "sample",
) -> list[dict]:
    """从音频中等距挑选 N 段片段，供 TTS 音色克隆。

    算法：在音频时长范围内等距分布 N 个起点，每段截取 sample_duration_sec。
    音频过短时自动减少段数或缩短段长。

    Args:
        audio_path: 源音频文件路径（WAV 最佳）
        output_dir: 输出目录
        count: 期望样本数（默认 5）
        sample_duration_sec: 每段时长秒数（默认 15，范围 min_duration_sec-30）
        min_duration_sec: 单条样本最短秒数（默认 8，防止截出过短片段）
        prefix: 输出文件名前缀（默认 "sample"，产生 sample_001.wav 等）

    Returns:
        [{"path": str, "start": float, "end": float}, ...]
    """
    sample_duration_sec = max(min_duration_sec,
                              min(sample_duration_sec, MAX_SAMPLE_DURATION_SEC))

    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"音频文件不存在: {audio_path}")

    total_dur = get_audio_duration_sec(audio_path)

    # 音频极短：取整段作为单样本
    if total_dur <= sample_duration_sec:
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, f"{prefix}_001.wav")
        extract_audio_segment(audio_path, 0.0, total_dur, output_path)
        logger.info(f"音频仅 {total_dur:.1f}s，取整段作为单样本")
        return [{"path": output_path, "start": 0.0, "end": total_dur}]

    # 计算实际可切段数
    actual_count = min(count, max(1, int(total_dur / min_duration_sec)))
    if actual_count < count:
        logger.info(
            f"音频 {total_dur:.1f}s 不足以切 {count} 段 8-30s，调整为 {actual_count} 段"
        )

    # 等距分布起点
    if actual_count == 1:
        # 单段：放在音频中间位置
        start = round((total_dur - sample_duration_sec) / 2, 1)
        intervals = [start]
    else:
        available = total_dur - sample_duration_sec
        interval = available / (actual_count - 1)
        intervals = [round(i * interval, 1) for i in range(actual_count)]

    os.makedirs(output_dir, exist_ok=True)
    samples = []
    for i, start in enumerate(intervals):
        end = round(start + sample_duration_sec, 1)
        if end > total_dur:
            end = total_dur
            start = max(0.0, end - sample_duration_sec)
        output_path = os.path.join(output_dir, f"{prefix}_{i + 1:03d}.wav")
        extract_audio_segment(audio_path, start, end, output_path)
        samples.append({"path": output_path, "start": start, "end": end})

    logger.info(f"样本挑选完成: {len(samples)} 段 → {output_dir}")
    return samples


def estimate_snr(wav_path: str, frame_ms: int = 20) -> float | None:
    """估算语音 WAV 文件的信噪比（dB），基于 RMS 能量比。

    算法：
    1. 将音频按 frame_ms 毫秒分帧
    2. 每帧计算 RMS 能量
    3. 取 RMS 中位数作为阈值：高于阈值 = 信号帧，低于 = 噪声帧
    4. SNR = 20 × log₁₀(avg_signal_rms / avg_noise_rms)

    纯 Python 实现，无外部依赖。
    """
    import wave
    import math
    import struct

    try:
        with wave.open(wav_path, "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            raw = wf.readframes(nframes)
    except Exception:
        return None

    if nframes == 0 or framerate == 0:
        return None

    # 解析 PCM 样本 → float（单声道取平均）
    if sampwidth == 2:
        fmt = f"<{nframes * nchannels}h"
        samples = struct.unpack(fmt, raw)
    elif sampwidth == 4:
        fmt = f"<{nframes * nchannels}i"
        samples = struct.unpack(fmt, raw)
    else:
        return None  # 仅支持 16-bit / 32-bit

    # 转 mono float
    if nchannels == 1:
        mono = [float(s) for s in samples]
    else:
        mono = [sum(samples[i * nchannels:(i + 1) * nchannels]) / nchannels
                for i in range(nframes)]

    # 分帧计算 RMS
    frame_len = int(framerate * frame_ms / 1000)
    if frame_len < 1:
        frame_len = 1

    rms_values = []
    for offset in range(0, len(mono), frame_len):
        chunk = mono[offset:offset + frame_len]
        if not chunk:
            break
        ms = sum(x * x for x in chunk) / len(chunk)
        rms_values.append(math.sqrt(ms))

    if len(rms_values) < 2:
        return None

    # 中位数分割：信号 / 噪声
    sorted_rms = sorted(rms_values)
    median_rms = sorted_rms[len(sorted_rms) // 2]

    signal_frames = [r for r in rms_values if r >= median_rms]
    noise_frames = [r for r in rms_values if r < median_rms]

    if not signal_frames or not noise_frames:
        return None

    avg_signal = sum(signal_frames) / len(signal_frames)
    avg_noise = sum(noise_frames) / len(noise_frames)

    if avg_noise <= 0:
        return 60.0  # 无噪声视为极高信噪比

    snr = 20 * math.log10(avg_signal / avg_noise)
    return round(max(0.0, min(snr, 60.0)), 1)


# ============================================================
# 本地测试入口
# ============================================================
if __name__ == "__main__":
    import tempfile
    import wave
    import struct
    import shutil as _shutil

    print("=== sample_picker unit tests ===\n")

    tmp_dir = tempfile.mkdtemp()

    # 创建 60 秒测试 WAV (16kHz, mono, 16-bit, 含模拟语音)
    test_wav = os.path.join(tmp_dir, "test_lecture.wav")
    with wave.open(test_wav, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        for i in range(16000 * 60):
            # 模拟语音：前 30s 有信号(振幅 10000)，后 30s 静音(振幅 100)
            val = 10000 if i < 16000 * 30 else 100
            wf.writeframes(struct.pack('<h', val))

    # 测试 1：默认参数挑选 5 段 × 15s
    out1 = os.path.join(tmp_dir, "samples_1")
    samples = pick_audio_samples(test_wav, out1, count=5, sample_duration_sec=15.0)
    assert len(samples) == 5, f"期望 5 段，实际 {len(samples)}"
    for s in samples:
        assert os.path.exists(s["path"]), f"样本文件应存在: {s['path']}"
        dur = get_audio_duration_sec(s["path"])
        assert 14.0 < dur < 16.0, f"每段约 15s，实际 {dur:.1f}s"
        assert "start" in s and "end" in s, "应包含 start/end 时间"
    print(f"[OK] 默认参数: {len(samples)} 段 × 15s")

    # 测试 2：自定义参数
    out2 = os.path.join(tmp_dir, "samples_2")
    samples = pick_audio_samples(test_wav, out2, count=3, sample_duration_sec=10.0)
    assert len(samples) == 3, f"期望 3 段，实际 {len(samples)}"
    for s in samples:
        dur = get_audio_duration_sec(s["path"])
        assert 9.0 < dur < 11.0, f"每段约 10s，实际 {dur:.1f}s"
    print(f"[OK] 自定义参数: {len(samples)} 段 × 10s")

    # 测试 3：音频极短（取整段）
    short_wav = os.path.join(tmp_dir, "short.wav")
    with wave.open(short_wav, 'w') as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        for _ in range(16000 * 5):
            wf.writeframes(struct.pack('<h', 5000))
    out3 = os.path.join(tmp_dir, "samples_3")
    samples = pick_audio_samples(short_wav, out3, count=5, sample_duration_sec=15.0)
    assert len(samples) == 1, f"短音频应只产 1 段，实际 {len(samples)}"
    dur = get_audio_duration_sec(samples[0]["path"])
    assert dur < 6.0, f"短音频样本应 <6s，实际 {dur:.1f}s"
    assert samples[0]["start"] == 0.0 and abs(samples[0]["end"] - 5.0) < 0.5
    print(f"[OK] 短音频整段: {len(samples)} 段, {dur:.1f}s")

    # 测试 4：sample_duration 边界 clamp（范围 8-30）
    out4 = os.path.join(tmp_dir, "samples_4")
    samples = pick_audio_samples(test_wav, out4, count=3, sample_duration_sec=999.0)
    for s in samples:
        dur = get_audio_duration_sec(s["path"])
        assert dur <= 30.5, f"clamp 后每段应 ≤30s，实际 {dur:.1f}s"
    print(f"[OK] 时长 clamp: 每段 {get_audio_duration_sec(samples[0]['path']):.1f}s (上限 30s)")

    # 测试 5：文件不存在
    try:
        pick_audio_samples("nonexistent.wav", out1)
        assert False, "应抛出 FileNotFoundError"
    except FileNotFoundError:
        print("[OK] FileNotFoundError")

    # 测试 6：SNR 估算
    snr = estimate_snr(test_wav)
    assert snr is not None, "SNR 不应为 None"
    # 前 30s 信号(10000) vs 后 30s 噪声(100)，SNR 应很高
    assert snr > 20, f"预期高 SNR，实际 {snr} dB"
    print(f"[OK] SNR 估算: {snr} dB")

    _shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\n[PASS] All sample_picker tests passed")

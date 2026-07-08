"""
M1 音频提取：从视频分离音频轨道 + 保存音频样本供 TTS 训练。

依赖 moviepy（惰性导入，仅调用相关函数时才需安装）。
"""

import os
import shutil
import logging

logger = logging.getLogger(__name__)

_moviepy_available = None


def _check_moviepy() -> bool:
    """惰性检查 moviepy 是否可用。"""
    global _moviepy_available
    if _moviepy_available is None:
        try:
            from moviepy import VideoFileClip  # noqa: F401
            _moviepy_available = True
        except ImportError:
            _moviepy_available = False
    return _moviepy_available


def extract_audio_from_video(video_path: str, audio_output_path: str) -> str:
    """从视频文件中提取音频轨道，输出为 WAV 文件。

    Args:
        video_path: 输入视频文件路径（.mp4 等）
        audio_output_path: 输出音频文件路径（.wav）

    Returns:
        audio_output_path（提取成功时）

    Requires: pip install moviepy
    """
    if not _check_moviepy():
        raise ImportError("moviepy 未安装，请执行: pip install moviepy")

    from moviepy import VideoFileClip

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    os.makedirs(os.path.dirname(audio_output_path) or ".", exist_ok=True)

    clip = VideoFileClip(video_path)
    try:
        clip.audio.write_audiofile(audio_output_path, logger=None)
    finally:
        clip.close()

    logger.info(f"音频提取完成: {video_path} -> {audio_output_path}")
    return audio_output_path


def save_audio_sample(source_audio_path: str, sample_output_path: str) -> str:
    """将音频文件复制到 audio_samples 目录，供后续 TTS 训练使用。

    Args:
        source_audio_path: 源音频文件路径
        sample_output_path: 目标路径（应在 audio_samples 目录下）

    Returns:
        sample_output_path
    """
    if not os.path.exists(source_audio_path):
        raise FileNotFoundError(f"源音频文件不存在: {source_audio_path}")

    os.makedirs(os.path.dirname(sample_output_path) or ".", exist_ok=True)
    shutil.copy2(source_audio_path, sample_output_path)
    logger.info(f"音频样本已保存: {sample_output_path}")
    return sample_output_path


# ============================================================
# 本地测试入口
# ============================================================
if __name__ == "__main__":
    import tempfile, wave, struct

    print("=== extractor unit tests ===\n")

    tmp_dir = tempfile.mkdtemp()
    test_wav = os.path.join(tmp_dir, "test_source.wav")
    with wave.open(test_wav, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        for _ in range(16000):
            wf.writeframes(struct.pack('<h', 0))

    test_sample = os.path.join(tmp_dir, "test_sample.wav")
    result = save_audio_sample(test_wav, test_sample)
    assert os.path.exists(result), "save_audio_sample failed"
    print(f"[OK] save_audio_sample: {result}")

    if _check_moviepy():
        print("[INFO] moviepy is available - video extraction enabled")
    else:
        print("[INFO] moviepy not installed - video extraction requires: pip install moviepy")

    import shutil as _shutil
    _shutil.rmtree(tmp_dir, ignore_errors=True)
    print("\n[PASS] extractor tests passed")

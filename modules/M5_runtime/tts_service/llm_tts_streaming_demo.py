"""
LLM + TTS 实时流式集成 Demo
===========================
演示 LLM 实时输出文本 → TTS 实时合成语音的完整流程。

用法：
    python llm_tts_streaming_demo.py

组员对接要点：
    1. 初始化 TTS（只需一次）
    2. LLM 每生成一段文本就调用 tts.feed_text(text)
    3. TTS 自动缓冲到句子边界后合成
    4. 轮询 tts.get_audio_chunk() 或注册 on_audio_ready 回调获取音频
"""
import os
import sys
import time
import threading

# 切到 GPT-SoVITS 内层目录（inference_webui 依赖 CWD 解析相对路径）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
GPT_SOVITS_DIR = os.path.join(PROJECT_ROOT, "GPT-SoVITS-v2pro")
os.chdir(GPT_SOVITS_DIR)
sys.path.insert(0, GPT_SOVITS_DIR)
sys.path.insert(0, os.path.join(GPT_SOVITS_DIR, "GPT_SoVITS"))  # 让 text/AR/BigVGAN 等模块可导入
sys.path.insert(0, PROJECT_ROOT)  # for modules.tts_service

# ── 配置模型路径 ─────────────────────────────────
GPT_MODEL = "GPT_weights_v2Pro/songhao_gpt-e20.ckpt"          # 微调后的 GPT
SOVITS_MODEL = "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth"  # 预训练SoVITS（微调版CFM未收敛，暂用预训练）
REF_TEXT = "面试呢我们看一下函数，函数部分啊肯定是我们做题的时候啊，主要用的就是函数了。"

from modules.tts_service.tts_inference import StreamingTTS

# 用回调收集音频（LLM 组员可直接送到播放器）
collected_audio = []

def on_audio(sr, audio):
    """音频就绪回调"""
    duration = len(audio) / sr
    print(f"[音频就绪] {duration:.1f}s, 采样率={sr}Hz")
    collected_audio.append((sr, audio))


def main():
    print("=" * 55)
    print("LLM + TTS 流式集成 Demo")
    print("=" * 55)

    # 1. 初始化 TTS（LLM 组员只需做这一步）
    tts = StreamingTTS(
        gpt_model_path=GPT_MODEL,
        sovits_model_path=SOVITS_MODEL,
        ref_text=REF_TEXT,
        on_audio_ready=on_audio,
    )
    tts.load_models()
    tts.start_streaming()

    # 2. 模拟 LLM 逐 token 输出文本（组员替换为真实 LLM generate）
    print("\n[LLM] 开始生成...")
    llm_output = [
        "我们先来看",
        "一个现象。",
        "函数是高等数学中",
        "最基本的概念之一，",
        "它描述了两个变量之间的依赖关系。",
        "同学们好，今天我们一起来学习",
        "一个新的知识点。",
    ]

    for chunk in llm_output:
        time.sleep(0.3)  # 模拟 LLM 生成延迟
        print(f"[LLM输出] {chunk}")
        tts.feed_text(chunk)  # ← 核心：逐段喂入文本

    # LLM 结束，flush 剩余文本
    tts.flush_text()
    print("[LLM] 生成完毕")

    # 3. 等待合成完成（v3 每句约 7-8s，最长等 120s）
    # 实际对接时 LLM 组员直接用 on_audio_ready 回调播放，无需等待
    max_wait = 120
    for _ in range(max_wait * 2):
        if not collected_audio:
            time.sleep(0.5)
            chunk = tts.get_audio_chunk(timeout=0.5)
            if chunk:
                collected_audio.append(chunk)
        else:
            time.sleep(0.5)
        # 检查是否还有待处理的文本
        if not tts.text_queue.empty():
            continue
        # 等待最后一段音频
        time.sleep(3)
        chunk = tts.get_audio_chunk(timeout=1.0)
        if chunk:
            collected_audio.append(chunk)
        break

    # 捞取剩余音频
    leftover = tts.flush_audio_queue()
    collected_audio.extend(leftover)

    print(f"\n[结果] 共合成 {len(collected_audio)} 段音频")

    # 4. 保存音频
    out_dir = "streaming_demo_output"
    os.makedirs(out_dir, exist_ok=True)
    for i, (sr, audio) in enumerate(collected_audio):
        import soundfile as sf
        path = os.path.join(out_dir, f"sentence_{i+1:02d}.wav")
        sf.write(path, audio, sr)
        print(f"  {path}  ({len(audio)/sr:.1f}s)")

    tts.stop_streaming()
    print("\nDone!")


if __name__ == "__main__":
    main()

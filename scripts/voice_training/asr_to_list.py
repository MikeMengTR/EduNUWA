"""
多老师语音训练 · 步骤 1：对 audio_samples 切片重新 ASR，生成 GPT-SoVITS 训练 list。

15s 切片在 transcripts 里没有逐条精确文本，必须重新转写。
使用 GPT-SoVITS 自带的本地 FunASR Paraformer 中文模型（无需联网、GPU 直跑），
输出标准 list：<wav绝对路径>|<说话人>|ZH|<文本>

用法:
    python scripts/voice_training/asr_to_list.py T_20260604_001 --exp T001
    python scripts/voice_training/asr_to_list.py T_20260604_001          # exp 默认取 teacher_id 尾号
"""
import os
import sys
import glob
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # EduNUWA/
GPT_INNER = PROJECT_ROOT / "GPT-SoVITS-v2pro" / "GPT-SoVITS-v2pro"
ASR_MODELS = GPT_INNER / "tools" / "asr" / "models"

_MODEL = None


def load_model():
    """加载本地 FunASR Paraformer（ASR+VAD+PUNC），GPU 优先。绝对路径 + disable_update 避免联网。"""
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    import torch
    from funasr import AutoModel
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[ASR] 加载本地 FunASR 模型 (device={device}) ...")
    _MODEL = AutoModel(
        model=str(ASR_MODELS / "speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"),
        vad_model=str(ASR_MODELS / "speech_fsmn_vad_zh-cn-16k-common-pytorch"),
        punc_model=str(ASR_MODELS / "punc_ct-transformer_zh-cn-common-vocab272727-pytorch"),
        disable_update=True,
        device=device,
    )
    print("[ASR] 模型加载完成")
    return _MODEL


def asr_teacher(teacher_id: str, exp_name: str, min_chars: int = 2):
    samples_dir = PROJECT_ROOT / "data" / "teachers" / teacher_id / "audio_samples"
    if not samples_dir.exists():
        sys.exit(f"[ERR] 找不到 audio_samples: {samples_dir}")

    wavs = sorted(glob.glob(str(samples_dir / "*.wav")))  # 只取 wav，自动排除 manifest.json
    if not wavs:
        sys.exit(f"[ERR] {samples_dir} 下没有 wav 切片")
    print(f"[ASR] {teacher_id}: {len(wavs)} 条切片，exp={exp_name}")

    model = load_model()

    out_dir = PROJECT_ROOT / "data" / "teachers" / teacher_id / "voice" / "train"
    out_dir.mkdir(parents=True, exist_ok=True)
    list_path = out_dir / f"{exp_name}.list"

    lines, skipped = [], []
    for i, w in enumerate(wavs, 1):
        try:
            text = model.generate(input=w)[0]["text"].strip()
        except Exception as e:
            print(f"  [{i}/{len(wavs)}] {Path(w).name}: 转写失败 {e}")
            skipped.append(Path(w).name)
            continue
        name = Path(w).name
        if len(text) < min_chars:
            skipped.append(name)
            print(f"  [{i}/{len(wavs)}] {name}: (空/过短，跳过)")
            continue
        # GPT-SoVITS list：wav|spk|lang|text（wav 绝对路径，预处理时取 basename + inp_wav_dir 拼接）
        lines.append(f"{w}|{exp_name}|ZH|{text}")
        print(f"  [{i}/{len(wavs)}] {name}: {text[:40]}")

    list_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[OK] 生成 {list_path}")
    print(f"     有效 {len(lines)} 条，跳过 {len(skipped)} 条")
    if skipped:
        print(f"     跳过: {skipped}")
    return str(list_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("teacher_id")
    ap.add_argument("--exp", default=None, help="实验名（默认 T+teacher_id 尾号）")
    args = ap.parse_args()

    exp = args.exp or ("T" + args.teacher_id.split("_")[-1])  # T_20260604_001 -> T001
    asr_teacher(args.teacher_id, exp)

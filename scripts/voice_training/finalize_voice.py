"""
多老师语音训练 · 步骤 3：把训练产物落地到各老师目录，每位老师独立部分分别归位。

落地内容 → data/teachers/{tid}/voice/:
  - {exp}_gpt-e{N}.ckpt    微调出的 GPT 权重（该老师独有，~149MB）
  - ref.wav               参考音频（从 audio_samples 选 SNR 最高的一条，零样本克隆音色用）
  - voice_profile.json    指向 GPT 权重 + 共享 SoVITS 底模 + 参考音频/文本
并更新 teacher_card.json 的 voice_id。

SoVITS 用 v2Pro 共享底模（不复制，所有老师共用一份），音色靠 ref.wav 零样本克隆。

用法:
    python scripts/voice_training/finalize_voice.py T_20260604_001 --exp T001
"""
import os
import sys
import json
import shutil
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GPT_INNER = PROJECT_ROOT / "GPT-SoVITS-v2pro" / "GPT-SoVITS-v2pro"
GPT_WEIGHTS = GPT_INNER / "GPT_weights_v2Pro"
SHARED_SOVITS = GPT_INNER / "GPT_SoVITS" / "pretrained_models" / "v2Pro" / "s2Gv2ProPlus.pth"

sys.path.insert(0, str(PROJECT_ROOT))


def pick_best_gpt_ckpt(exp):
    ckpts = sorted(GPT_WEIGHTS.glob(f"{exp}_gpt-e*.ckpt"),
                   key=lambda p: int(p.stem.split("-e")[-1]) if p.stem.split("-e")[-1].isdigit() else 0)
    if not ckpts:
        sys.exit(f"[ERR] 找不到 GPT 权重: {GPT_WEIGHTS}/{exp}_gpt-e*.ckpt（先跑 train_gpt.py）")
    return ckpts[-1]  # 最大 epoch


def prepare_ref(teacher_id, voice_dir, target_sec=8.0):
    """选 SNR 最高的参考切片，裁剪到 GPT-SoVITS 要求的 3~10 秒（取中段），
    并对裁剪段重新 ASR 得到与音频精确匹配的参考文本。返回 (ref.wav 路径, 文本)。"""
    import soundfile as sf
    from modules.M5_runtime.tts_service.voice_clone import get_clone_references

    refs = get_clone_references(teacher_id, count=1)
    if not refs:
        sys.exit(f"[ERR] 无法为 {teacher_id} 选参考音频")
    src = Path(refs[0])

    data, sr = sf.read(str(src))
    dur = len(data) / sr
    if dur > target_sec:  # 取中段 target_sec 秒，避开首尾可能的静音/片头
        start = int((dur - target_sec) / 2 * sr)
        seg = data[start:start + int(target_sec * sr)]
    else:
        seg = data
    dst_ref = voice_dir / "ref.wav"
    sf.write(str(dst_ref), seg, sr)
    print(f"[REF] {src.name} 裁剪 {len(seg)/sr:.1f}s → {dst_ref}")

    # 对裁剪段重新 ASR，保证文本与音频内容一致
    sys.path.insert(0, str(Path(__file__).parent))
    import asr_to_list
    ref_text = asr_to_list.load_model().generate(input=str(dst_ref))[0]["text"].strip()
    if not ref_text:
        print("[WARN] 参考段 ASR 文本为空，零样本质量会下降")
    print(f"[REF] 参考文本: {ref_text}")
    return dst_ref, ref_text


def finalize(teacher_id, exp):
    voice_dir = PROJECT_ROOT / "data" / "teachers" / teacher_id / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)

    ckpt = pick_best_gpt_ckpt(exp)

    # 拷贝 GPT 权重
    dst_ckpt = voice_dir / ckpt.name
    shutil.copy2(ckpt, dst_ckpt)
    print(f"[COPY] GPT 权重 → {dst_ckpt}")

    # 准备参考音频（选 SNR 最高切片 → 裁剪 3~10s → 重新 ASR 得匹配文本）
    dst_ref, ref_text = prepare_ref(teacher_id, voice_dir)

    # 写 voice_profile.json（路径相对项目根，便于跨机器）
    profile = {
        "voice_id": exp,
        "teacher_id": teacher_id,
        "engine": "gpt-sovits-v2pro",
        "gpt_model": str(dst_ckpt.relative_to(PROJECT_ROOT).as_posix()),
        "sovits_model": str(SHARED_SOVITS.relative_to(PROJECT_ROOT).as_posix()),
        "ref_audio": str(dst_ref.relative_to(PROJECT_ROOT).as_posix()),
        "ref_text": ref_text,
        "ref_language": "zh",
    }
    profile_path = voice_dir / "voice_profile.json"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[WRITE] {profile_path}")

    # 更新 teacher_card.json
    card_path = PROJECT_ROOT / "data" / "teachers" / teacher_id / "teacher_card.json"
    if card_path.exists():
        card = json.loads(card_path.read_text(encoding="utf-8"))
        card["voice_id"] = exp
        card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[UPDATE] teacher_card.voice_id = {exp}")

    print(f"\n[DONE] {teacher_id} 语音独立部分已归位:\n  {voice_dir}")
    return profile


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("teacher_id")
    ap.add_argument("--exp", default=None)
    args = ap.parse_args()
    exp = args.exp or ("T" + args.teacher_id.split("_")[-1])
    finalize(args.teacher_id, exp)

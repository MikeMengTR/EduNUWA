"""
改进某老师的参考音频：从 Top-N 高SNR切片各生成一个候选参考（去静音裁剪 + 精确 ASR），
用同一句话合成对比样本，便于人工挑选最清晰的一个。

挑好后用 --apply N 把第 N 个候选设为正式 ref（更新 voice_profile + 重合成 sample_test）。

用法:
    python scripts/voice_training/improve_voice.py T_20260604_001
    python scripts/voice_training/improve_voice.py T_20260604_001 --apply 2
"""
import os
import sys
import json
import shutil
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(HERE))

TEST_TEXT = "同学们好，今天我们来学习一个新的知识点，希望大家能够认真听讲。"
TOP_N = 4
SEG_SEC = 9.0          # 参考片段时长（3~10s 内）
TEMPERATURE = 0.5      # 比默认 0.6 略低，输出更稳定清晰
TOP_P = 0.6


def build_candidates(tid, exp):
    import soundfile as sf
    import librosa
    import asr_to_list

    samples_dir = PROJECT_ROOT / "data" / "teachers" / tid / "audio_samples"
    voice_dir = PROJECT_ROOT / "data" / "teachers" / tid / "voice"
    cand_dir = voice_dir / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((samples_dir / "manifest.json").read_text(encoding="utf-8"))
    top = sorted(manifest["samples"], key=lambda x: x.get("snr_estimate") or 0, reverse=True)[:TOP_N]

    asr = asr_to_list.load_model()
    cands = []
    for i, s in enumerate(top, 1):
        src = samples_dir / s["path"]
        data, sr = sf.read(str(src))
        if data.ndim > 1:
            data = data[:, 0]
        # 去首尾静音后取前 SEG_SEC 秒，尽量得到自然完整的语句开头
        y, _ = librosa.effects.trim(data, top_db=30)
        seg = y[:int(SEG_SEC * sr)]
        cand_wav = cand_dir / f"cand{i}.wav"
        sf.write(str(cand_wav), seg, sr)
        text = asr.generate(input=str(cand_wav))[0]["text"].strip()
        cands.append({"idx": i, "src": s["path"], "snr": s.get("snr_estimate"),
                      "wav": str(cand_wav), "text": text, "dur": round(len(seg) / sr, 1)})
        print(f"候选{i}: SNR={s.get('snr_estimate')} 时长={len(seg)/sr:.1f}s")
        print(f"   参考文本: {text}")
    (cand_dir / "candidates.json").write_text(
        json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")
    return cands, cand_dir


def synth_candidates(tid, exp, cands, cand_dir):
    profile = json.loads((PROJECT_ROOT / "data" / "teachers" / tid / "voice" / "voice_profile.json").read_text(encoding="utf-8"))
    from modules.M5_runtime.tts_service.gpt_sovits_wrapper import StreamingTTS

    tts = StreamingTTS(
        gpt_model_path=str(PROJECT_ROOT / profile["gpt_model"]),
        sovits_model_path=str(PROJECT_ROOT / profile["sovits_model"]),
        ref_audio_path=cands[0]["wav"], ref_text=cands[0]["text"],
        temperature=TEMPERATURE, top_p=TOP_P,
    )
    tts.load_models()
    import soundfile as sf
    import numpy as np
    for c in cands:
        tts.ref_text = c["text"]
        out = cand_dir / f"sample_cand{c['idx']}.wav"
        ok, r = False, {}
        for attempt in range(5):  # 无声时递增 temperature（0.5→0.9）自适应，避开输出退化/静音
            tts.temperature = round(TEMPERATURE + attempt * 0.1, 2)
            r = tts.synthesize_to_file(TEST_TEXT, str(out), ref_audio=c["wav"])
            if r.get("status") == "success":
                x, sr = sf.read(str(out))
                if x.ndim > 1:
                    x = x[:, 0]
                if float(np.sqrt(np.mean(x ** 2))) >= 0.01:
                    ok = True
                    c["temperature"] = tts.temperature  # 记录成功参数，apply 时写入 profile
                    break
            print(f"   候选{c['idx']} temp={tts.temperature} 无声，重试…")
        print(f"[合成] 候选{c['idx']} -> {out.name}  {('OK temp='+str(c.get('temperature'))) if ok else '仍无声'}  {r.get('duration_sec','')}s")
    # 回写 candidates.json（含成功 temperature）
    (cand_dir / "candidates.json").write_text(
        json.dumps(cands, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_candidate(tid, exp, n):
    voice_dir = PROJECT_ROOT / "data" / "teachers" / tid / "voice"
    cands = json.loads((voice_dir / "candidates" / "candidates.json").read_text(encoding="utf-8"))
    c = next(x for x in cands if x["idx"] == n)
    # 覆盖正式 ref.wav 与 profile
    shutil.copy2(c["wav"], voice_dir / "ref.wav")
    profile = json.loads((voice_dir / "voice_profile.json").read_text(encoding="utf-8"))
    profile["ref_text"] = c["text"]
    profile["temperature"] = c.get("temperature", TEMPERATURE)
    profile["top_p"] = TOP_P
    (voice_dir / "voice_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[APPLY] 候选{n} 已设为正式参考: {c['text']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("teacher_id")
    ap.add_argument("--exp", default=None)
    ap.add_argument("--apply", type=int, default=None, help="把第 N 个候选设为正式参考")
    args = ap.parse_args()
    exp = args.exp or ("T" + args.teacher_id.split("_")[-1])

    if args.apply:
        apply_candidate(args.teacher_id, exp, args.apply)
        return

    cands, cand_dir = build_candidates(args.teacher_id, exp)
    synth_candidates(args.teacher_id, exp, cands, cand_dir)
    print(f"\n对比样本已生成在: {cand_dir}")
    print("听完后用 --apply N 应用最清晰的那个候选。")


if __name__ == "__main__":
    main()

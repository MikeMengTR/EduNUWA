"""
诊断某老师不同 epoch 的 GPT 权重是否出声（排查训练退化）。
固定参考音频(候选1)，对 e20/e16/e12/e8/e4 各合成一句，报最大振幅。

用法: python scripts/voice_training/diag_epoch.py T_20260604_006
"""
import sys
import json
import numpy as np
import soundfile as sf
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

TEST = "同学们好，今天我们来学习一个新的知识点。"
EPOCHS = [20, 16, 12, 8, 4]


def main():
    tid = sys.argv[1]
    exp = "T" + tid.split("_")[-1]
    prof = json.loads((PROJECT_ROOT / f"data/teachers/{tid}/voice/voice_profile.json").read_text(encoding="utf-8"))
    cands = json.loads((PROJECT_ROOT / f"data/teachers/{tid}/voice/candidates/candidates.json").read_text(encoding="utf-8"))
    c = cands[0]

    import modules.M5_runtime.tts_service.gpt_sovits_wrapper as W
    from modules.M5_runtime.tts_service.gpt_sovits_wrapper import StreamingTTS

    gw = PROJECT_ROOT / "GPT-SoVITS-v2pro" / "GPT-SoVITS-v2pro" / "GPT_weights_v2Pro"
    tts = StreamingTTS(
        gpt_model_path=str(gw / f"{exp}_gpt-e20.ckpt"),
        sovits_model_path=str(PROJECT_ROOT / prof["sovits_model"]),
        ref_audio_path=c["wav"], ref_text=c["text"], temperature=0.6,
    )
    tts.load_models()
    print(f"参考: {c['text']}")
    for ep in EPOCHS:
        ck = gw / f"{exp}_gpt-e{ep}.ckpt"
        with W._gpt_sovits_cwd():
            W._change_gpt_weights(gpt_path=str(ck))
        res = tts.synthesize(TEST)
        if res:
            sr, a = res
            a = a[:, 0] if a.ndim > 1 else a
            mx = float(np.max(np.abs(a)))
            print(f"e{ep}: max={mx:.3f}  dur={len(a)/sr:.1f}s  {'OK' if mx > 0.05 else 'SILENT'}")
        else:
            print(f"e{ep}: None")


if __name__ == "__main__":
    main()

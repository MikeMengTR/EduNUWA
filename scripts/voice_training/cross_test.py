"""交叉诊断 T006 发散：分离 GPT 模型 与 参考音频 两个变量。"""
import sys, json
import numpy as np
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))
import modules.M5_runtime.tts_service.gpt_sovits_wrapper as W
from modules.M5_runtime.tts_service.gpt_sovits_wrapper import StreamingTTS

gw = PR / "GPT-SoVITS-v2pro" / "GPT-SoVITS-v2pro" / "GPT_weights_v2Pro"
sovits = PR / "GPT-SoVITS-v2pro" / "GPT-SoVITS-v2pro" / "GPT_SoVITS" / "pretrained_models" / "v2Pro" / "s2Gv2ProPlus.pth"
TEST = "这是一个测试句子，用来检查语音是否正常。"


def prof(t):
    return json.loads((PR / f"data/teachers/{t}/voice/voice_profile.json").read_text(encoding="utf-8"))


def mx(r):
    if not r:
        return -1.0
    a = r[1]
    a = a[:, 0] if a.ndim > 1 else a
    return float(np.max(np.abs(a)))


p1, p6 = prof("T_20260604_001"), prof("T_20260604_006")

# 实例: T006 GPT + T001 已知好的参考
tts = StreamingTTS(gpt_model_path=str(gw / "T006_gpt-e20.ckpt"), sovits_model_path=str(sovits),
                   ref_audio_path=str(PR / p1["ref_audio"]), ref_text=p1["ref_text"], temperature=0.6)
tts.load_models()
print("A) T006-GPT + T001-ref:  max=%.3f" % mx(tts.synthesize(TEST)))

# 切到 T001 GPT, 用 T006 参考
with W._gpt_sovits_cwd():
    W._change_gpt_weights(gpt_path=str(gw / "T001_gpt-e20.ckpt"))
tts.ref_text = p6["ref_text"]
print("B) T001-GPT + T006-ref:  max=%.3f" % mx(tts.synthesize(TEST, ref_audio=str(PR / p6["ref_audio"]))))

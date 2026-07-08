"""
多老师语音训练 · 验证：用某老师的 voice_profile 合成一句测试语音。

用法:
    python scripts/voice_training/synth_test.py T_20260604_001 "同学们好，今天我们来学习随机事件的概率。"
"""
import os
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    tid = sys.argv[1]
    text = sys.argv[2] if len(sys.argv) > 2 else "同学们好，今天我们来学习一个新的知识点。"

    profile_path = PROJECT_ROOT / "data" / "teachers" / tid / "voice" / "voice_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    from modules.M5_runtime.tts_service.gpt_sovits_wrapper import StreamingTTS

    tts = StreamingTTS(
        gpt_model_path=str(PROJECT_ROOT / profile["gpt_model"]),
        sovits_model_path=str(PROJECT_ROOT / profile["sovits_model"]),
        ref_audio_path=str(PROJECT_ROOT / profile["ref_audio"]),
        ref_text=profile["ref_text"],
        voice_id=profile["voice_id"],
        temperature=profile.get("temperature", 0.6),
        top_p=profile.get("top_p", 0.6),
    )
    out = PROJECT_ROOT / "data" / "teachers" / tid / "voice" / "sample_test.wav"
    print(f"[SYNTH] {tid} | text={text}")
    r = tts.synthesize_to_file(text, str(out))
    print("[RESULT]", json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()

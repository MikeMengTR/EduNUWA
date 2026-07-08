"""
多老师语音训练 · 批量：对多位老师依次跑 ASR → GPT 微调 → 落地。

每位老师独立产物落进各自 data/teachers/{tid}/voice/。失败的老师记录后继续下一位。

用法:
    python scripts/voice_training/train_all.py                       # 默认 002~006
    python scripts/voice_training/train_all.py T_20260604_003 T_20260604_005
"""
import os
import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
PYTHON = sys.executable

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(HERE))
import asr_to_list
import finalize_voice

DEFAULT_TEACHERS = [
    "T_20260604_002", "T_20260604_003", "T_20260604_004",
    "T_20260604_005", "T_20260604_006",
]


def train_one(tid, epochs=20):
    exp = "T" + tid.split("_")[-1]
    print(f"\n{'#'*70}\n# {tid}  (exp={exp})\n{'#'*70}")

    # 1. ASR 切片 → list
    print(f"\n>>> [1/3] ASR 转写切片")
    asr_to_list.asr_teacher(tid, exp)

    # 2. 预处理 + GPT 微调（独立子进程）
    print(f"\n>>> [2/3] 预处理 + GPT 微调")
    list_path = PROJECT_ROOT / "data" / "teachers" / tid / "voice" / "train" / f"{exp}.list"
    wav_dir = PROJECT_ROOT / "data" / "teachers" / tid / "audio_samples"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    r = subprocess.run(
        [PYTHON, str(HERE / "train_gpt.py"), exp,
         "--list", str(list_path), "--wav-dir", str(wav_dir), "--epochs", str(epochs)],
        env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"GPT 训练失败 (code {r.returncode})")

    # 3. 落地
    print(f"\n>>> [3/3] 产物落地")
    finalize_voice.finalize(tid, exp)
    print(f"\n[✓] {tid} 完成")


def main():
    teachers = sys.argv[1:] or DEFAULT_TEACHERS
    print(f"批量训练 {len(teachers)} 位老师: {teachers}")

    ok, failed = [], []
    for tid in teachers:
        try:
            train_one(tid)
            ok.append(tid)
        except Exception as e:
            print(f"\n[✗] {tid} 失败: {e}")
            failed.append((tid, str(e)))

    print(f"\n{'='*70}\n批量结果: 成功 {len(ok)} / {len(teachers)}")
    for t in ok:
        print(f"  [✓] {t}")
    for t, e in failed:
        print(f"  [✗] {t}: {e}")


if __name__ == "__main__":
    main()

"""
多老师语音训练 · 步骤 2：预处理(BERT/HuBERT/语义) + GPT(s1) 微调。

只微调 GPT（决定语气节奏）；SoVITS 用 v2Pro 共享底模 + 参考音频零样本克隆音色。
修正了旧 train_pipeline.py 的两个问题：
  1. 路径指向内层双层目录 GPT-SoVITS-v2pro/GPT-SoVITS-v2pro/
  2. 用当前 edu Python（旧脚本依赖不存在的整合包 runtime/python.exe）

产物：GPT-SoVITS-v2pro/GPT-SoVITS-v2pro/GPT_weights_v2Pro/{exp}_gpt-e{N}.ckpt

用法:
    python scripts/voice_training/train_gpt.py T001 \
        --list data/teachers/T_20260604_001/voice/train/T001.list \
        --wav-dir data/teachers/T_20260604_001/audio_samples \
        --epochs 20
"""
import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GPT_INNER = PROJECT_ROOT / "GPT-SoVITS-v2pro" / "GPT-SoVITS-v2pro"
GS = GPT_INNER / "GPT_SoVITS"
PRETRAINED = GS / "pretrained_models"
PYTHON = sys.executable  # 当前 edu 环境
FFMPEG_DIR = Path(sys.prefix) / "Library" / "bin"  # conda 装的 ffmpeg.exe（预处理读音频需要）

PREP = GS / "prepare_datasets"
BERT_DIR = PRETRAINED / "chinese-roberta-wwm-ext-large"
CNHUBERT_DIR = PRETRAINED / "chinese-hubert-base"
PRETRAINED_S2G = PRETRAINED / "v2Pro" / "s2Gv2Pro.pth"
PRETRAINED_S1 = PRETRAINED / "s1v3.ckpt"
S2_CONFIG = GS / "configs" / "s2v2Pro.json"


def _run(name, script, env_extra):
    """在 GPT_INNER 下用 edu Python 运行一个预处理脚本。"""
    print(f"\n{'='*60}\n  {name}\n{'='*60}")
    env = os.environ.copy()
    env.update(env_extra)
    env["PYTHONPATH"] = os.pathsep.join([str(GS), str(GPT_INNER / "tools"), env.get("PYTHONPATH", "")])
    env["PATH"] = os.pathsep.join([str(FFMPEG_DIR), env.get("PATH", "")])
    r = subprocess.run([PYTHON, str(script)], cwd=str(GPT_INNER), env=env)
    if r.returncode != 0:
        sys.exit(f"[ERR] {name} 失败 (code {r.returncode})")
    print(f"  {name} [OK]")


def preprocess(exp, list_path, wav_dir, opt_dir):
    # 预处理脚本有"产物已存在就跳过"的断点续传逻辑；清空旧产物以强制重新生成，
    # 避免上次失败留下的空文件导致 step1 被跳过、连锁产出空特征。
    if opt_dir.exists():
        shutil.rmtree(opt_dir, ignore_errors=True)
    opt_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "inp_text": str(list_path),
        "inp_wav_dir": str(wav_dir),
        "exp_name": exp,
        "i_part": "0",
        "all_parts": "1",
        "opt_dir": str(opt_dir),
        "is_half": "True",
    }
    _run("1/3 文本/BERT 特征", PREP / "1-get-text.py",
         {**base, "bert_pretrained_dir": str(BERT_DIR), "version": "v2Pro"})
    _run("2/3 HuBERT 特征", PREP / "2-get-hubert-wav32k.py",
         {**base, "cnhubert_base_dir": str(CNHUBERT_DIR)})
    _run("3/3 语义 token", PREP / "3-get-semantic.py",
         {**base, "pretrained_s2G": str(PRETRAINED_S2G), "s2config_path": str(S2_CONFIG)})


def write_train_yaml(exp, opt_dir, epochs, batch_size, save_every, precision="16-mixed"):
    """基于 songhao_train.yaml 模板生成本老师的 GPT 训练配置。路径均相对 GPT_INNER。"""
    rel_opt = opt_dir.relative_to(GPT_INNER).as_posix()
    yaml_text = f"""train:
  seed: 1234
  epochs: {epochs}
  batch_size: {batch_size}
  save_every_n_epoch: {save_every}
  precision: {precision}
  gradient_clip: 1.0
  if_save_latest: true
  if_save_every_weights: true
  half_weights_save_dir: GPT_weights_v2Pro
  exp_name: {exp}_gpt
optimizer:
  lr: 0.01
  lr_init: 0.00001
  lr_end: 0.0001
  warmup_steps: 2000
  decay_steps: 40000
data:
  max_eval_sample: 8
  max_sec: 54
  num_workers: 2
  pad_val: 1024
model:
  vocab_size: 1025
  phoneme_vocab_size: 732
  embedding_dim: 512
  hidden_dim: 512
  head: 16
  linear_units: 2048
  n_layer: 24
  dropout: 0
  EOS: 1024
  random_bert: 0
inference:
  top_k: 15
train_semantic_path: {rel_opt}/6-name2semantic-0.tsv
train_phoneme_path: {rel_opt}/2-name2text-0.txt
output_dir: logs/{exp}_gpt
pretrained_s1: GPT_SoVITS/pretrained_models/s1v3.ckpt
"""
    yaml_path = GS / "configs" / f"{exp}_train.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")
    print(f"[YAML] {yaml_path}")
    return yaml_path


def train_gpt(yaml_path):
    print(f"\n{'='*60}\n  GPT (s1) 微调训练\n{'='*60}")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(GS), str(GPT_INNER / "tools"), env.get("PYTHONPATH", "")])
    env["PATH"] = os.pathsep.join([str(FFMPEG_DIR), env.get("PATH", "")])
    rel_yaml = yaml_path.relative_to(GPT_INNER).as_posix()
    r = subprocess.run([PYTHON, str(GS / "s1_train.py"), "--config_file", rel_yaml],
                       cwd=str(GPT_INNER), env=env)
    if r.returncode != 0:
        sys.exit(f"[ERR] GPT 训练失败 (code {r.returncode})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exp", help="实验名，如 T001")
    ap.add_argument("--list", required=True, help="训练 list 路径")
    ap.add_argument("--wav-dir", required=True, help="切片 wav 目录 (inp_wav_dir)")
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch-size", type=int, default=4)
    ap.add_argument("--save-every", type=int, default=4)
    ap.add_argument("--skip-preprocess", action="store_true", help="跳过预处理(已做过)")
    ap.add_argument("--precision", default="16-mixed", help="训练精度，发散时改 32")
    args = ap.parse_args()

    list_path = (PROJECT_ROOT / args.list).resolve() if not os.path.isabs(args.list) else Path(args.list)
    wav_dir = (PROJECT_ROOT / args.wav_dir).resolve() if not os.path.isabs(args.wav_dir) else Path(args.wav_dir)
    opt_dir = GPT_INNER / "logs" / f"{args.exp}_v2Pro"

    if not list_path.exists():
        sys.exit(f"[ERR] list 不存在: {list_path}")

    print(f"[CFG] exp={args.exp} list={list_path}\n      wav_dir={wav_dir}\n      opt_dir={opt_dir}")

    if not args.skip_preprocess:
        preprocess(args.exp, list_path, wav_dir, opt_dir)

    yaml_path = write_train_yaml(args.exp, opt_dir, args.epochs, args.batch_size, args.save_every, args.precision)
    # 清理上次训练的 checkpoint，确保从底模全新训练（否则 lightning 会尝试 resume，
    # torch 2.11 weights_only 加载旧 ckpt 会报 UnpicklingError）
    gpt_out = GPT_INNER / "logs" / f"{args.exp}_gpt"
    if gpt_out.exists():
        shutil.rmtree(gpt_out, ignore_errors=True)
    train_gpt(yaml_path)

    ckpt_dir = GPT_INNER / "GPT_weights_v2Pro"
    ckpts = sorted(ckpt_dir.glob(f"{args.exp}_gpt-e*.ckpt"))
    print(f"\n[DONE] GPT 权重产物:")
    for c in ckpts:
        print(f"  {c}")


if __name__ == "__main__":
    main()

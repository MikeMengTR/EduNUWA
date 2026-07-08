"""
Complete training pipeline for GPT-SoVITS Song Hao voice model.
Runs: BERT/HuBERT/Semantic feature extraction → GPT training → SoVITS training.
"""
import sys
import os
import subprocess
import glob

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GPT_ROOT = os.path.join(PROJECT_ROOT, "GPT-SoVITS-v2pro")
TOOLS = os.path.join(GPT_ROOT, "tools")
sys.path.insert(0, GPT_ROOT)
sys.path.insert(0, TOOLS)

# Use runtime Python which has all GPT-SoVITS deps
RUNTIME_PYTHON = os.path.join(os.path.dirname(TOOLS), "runtime", "python.exe")

# Paths
TRAIN_LIST = os.path.join(PROJECT_ROOT, "data", "transcripts", "songhao_train.list")
WAV_DIR = os.path.join(PROJECT_ROOT, "data", "sliced_audio")
EXP_NAME = "songhao_v2Pro"
OPT_DIR = os.path.join(GPT_ROOT, "logs", EXP_NAME)

BERT_DIR = os.path.join(GPT_ROOT, "GPT_SoVITS", "pretrained_models", "chinese-roberta-wwm-ext-large")
CNHUBERT_DIR = os.path.join(GPT_ROOT, "GPT_SoVITS", "pretrained_models", "chinese-hubert-base")
PRETRAINED_S2G = os.path.join(GPT_ROOT, "GPT_SoVITS", "pretrained_models", "v2Pro", "s2Gv2Pro.pth")
S2_CONFIG = os.path.join(GPT_ROOT, "GPT_SoVITS", "configs", "s2v2Pro.json")


def run_step(step_name, script_path, env_vars):
    """Run a preprocessing step."""
    print(f"\n{'='*60}")
    print(f"  STEP: {step_name}")
    print(f"{'='*60}")

    env = os.environ.copy()
    env.update(env_vars)
    # Ensure GPT_SoVITS and tools are on PYTHONPATH
    pythonpath = GPT_ROOT
    gpt_sovits = os.path.join(GPT_ROOT, "GPT_SoVITS")
    if "PYTHONPATH" in env:
        pythonpath = f"{gpt_sovits}{os.pathsep}{TOOLS}{os.pathsep}{env['PYTHONPATH']}"
    else:
        pythonpath = f"{gpt_sovits}{os.pathsep}{TOOLS}"
    env["PYTHONPATH"] = pythonpath

    cmd = [RUNTIME_PYTHON, script_path]
    result = subprocess.run(cmd, cwd=GPT_ROOT, env=env, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"{step_name} failed with code {result.returncode}")
    print(f"  {step_name} [OK]")


def step1_extract_text():
    """Extract BERT features from training texts."""
    env = {
        "inp_text": TRAIN_LIST,
        "inp_wav_dir": WAV_DIR,
        "exp_name": EXP_NAME,
        "i_part": "0",
        "all_parts": "1",
        "opt_dir": OPT_DIR,
        "bert_pretrained_dir": BERT_DIR,
        "is_half": "True",
        "version": "v2Pro",
    }
    script = os.path.join(GPT_ROOT, "GPT_SoVITS", "prepare_datasets", "1-get-text.py")
    run_step("1/3 BERT Feature Extraction", script, env)


def step2_extract_hubert():
    """Extract HuBERT features + normalize audio."""
    env = {
        "inp_text": TRAIN_LIST,
        "inp_wav_dir": WAV_DIR,
        "exp_name": EXP_NAME,
        "i_part": "0",
        "all_parts": "1",
        "opt_dir": OPT_DIR,
        "cnhubert_base_dir": CNHUBERT_DIR,
        "is_half": "True",
    }
    script = os.path.join(GPT_ROOT, "GPT_SoVITS", "prepare_datasets", "2-get-hubert-wav32k.py")
    run_step("2/3 HuBERT Feature Extraction", script, env)


def step3_extract_semantic():
    """Extract semantic tokens from HuBERT features."""
    env = {
        "inp_text": TRAIN_LIST,
        "exp_name": EXP_NAME,
        "i_part": "0",
        "all_parts": "1",
        "opt_dir": OPT_DIR,
        "pretrained_s2G": PRETRAINED_S2G,
        "s2config_path": S2_CONFIG,
        "is_half": "True",
    }
    script = os.path.join(GPT_ROOT, "GPT_SoVITS", "prepare_datasets", "3-get-semantic.py")
    run_step("3/3 Semantic Token Extraction", script, env)


def run_preprocessing():
    """Run all 3 preprocessing steps."""
    os.makedirs(OPT_DIR, exist_ok=True)

    print(f"Training list: {TRAIN_LIST}")
    print(f"WAV directory: {WAV_DIR}")
    print(f"Output directory: {OPT_DIR}")
    print(f"Using Python: {RUNTIME_PYTHON}")

    step1_extract_text()
    step2_extract_hubert()
    step3_extract_semantic()

    print("\n[OK] All preprocessing complete!")
    print(f"  Features saved to: {OPT_DIR}")
    print(f"  2-name2text-0.txt  → text/phoneme mappings")
    print(f"  3-bert/*.pt         → BERT features")
    print(f"  4-cnhubert/*.pt     → HuBERT features")
    print(f"  5-wav32k/*.wav      → normalized audio")
    print(f"  6-name2semantic-0.tsv → semantic tokens")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["preprocess", "step1", "step2", "step3"],
                       help="Which step to run (preprocess = all 3)")
    args = parser.parse_args()

    if args.step == "preprocess":
        run_preprocessing()
    elif args.step == "step1":
        step1_extract_text()
    elif args.step == "step2":
        step2_extract_hubert()
    elif args.step == "step3":
        step3_extract_semantic()

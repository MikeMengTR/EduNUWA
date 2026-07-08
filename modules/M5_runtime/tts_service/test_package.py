"""Quick smoke test: verify tts_package/ works standalone."""
import sys, os, re

# Simulate running from tts_package/
PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))
INNER = os.path.join(PACKAGE_ROOT, "GPT-SoVITS-v2pro")
GPT_SOVITS = os.path.join(INNER, "GPT_SoVITS")
sys.path.insert(0, INNER)
sys.path.insert(0, GPT_SOVITS)  # 让 text/AR/BigVGAN 等模块可导入
os.chdir(INNER)

print("=== Import test ===")
try:
    from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
    print("[OK] inference_webui imports")
except Exception as e:
    print(f"[FAIL] inference_webui: {e}")

try:
    from config import get_weights_names
    print("[OK] config imports")
except Exception as e:
    print(f"[FAIL] config: {e}")

try:
    from process_ckpt import load_sovits_new
    print("[OK] process_ckpt imports")
except Exception as e:
    print(f"[FAIL] process_ckpt: {e}")

try:
    from tools.i18n.i18n import I18nAuto
    print("[OK] i18n imports")
except Exception as e:
    print(f"[FAIL] i18n: {e}")

try:
    from tools.assets import css
    print("[OK] assets imports")
except Exception as e:
    print(f"[FAIL] assets: {e}")

print("\n=== Critical file existence ===")
files_to_check = [
    "GPT_weights_v2Pro/songhao_gpt-e20.ckpt",
    "GPT_SoVITS/pretrained_models/v2Pro/s2Gv2ProPlus.pth",
    "GPT_SoVITS/pretrained_models/v2Pro/s2Dv2ProPlus.pth",
    "GPT_SoVITS/pretrained_models/chinese-hubert-base/pytorch_model.bin",
    "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large/pytorch_model.bin",
    "GPT_SoVITS/pretrained_models/fast_langdetect/lid.176.bin",
    "GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt",
    "weight.json",
    "config.py",
    "GPT_SoVITS/configs/s2v2ProPlus.json",
]
for f in files_to_check:
    ok = os.path.exists(f)
    print(f"  {'[OK]' if ok else '[MISS]'} {f}")

print("\n=== Path resolution in inference_webui ===")
import GPT_SoVITS.inference_webui as iw
iw_file = iw.__file__
print(f"inference_webui.py at: {iw_file}")

# Check if bert_path / cnhubert_base_path resolve
bert = os.path.join(INNER, "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large")
cnhubert = os.path.join(INNER, "GPT_SoVITS/pretrained_models/chinese-hubert-base")
print(f"  bert_path exists: {os.path.exists(bert)}")
print(f"  cnhubert_base_path exists: {os.path.exists(cnhubert)}")

# Check if pretrained_models dir exists
pretrained = os.path.join(INNER, "GPT_SoVITS/pretrained_models")
print(f"  pretrained_models dir exists: {os.path.exists(pretrained)}")

print("\n=== Path fixes needed check ===")
# Check inference_webui for relative paths that might break
with open(iw_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Look for patterns like "pretrained_models/" used as relative path
import re as re_mod
relative_refs = re_mod.findall(r'["\'](pretrained_models/[^"\']+)["\']', content)
print("References to pretrained_models/:")
for ref in relative_refs[:10]:
    full_path = os.path.join(INNER, "GPT_SoVITS", ref)
    ok = os.path.exists(full_path)
    print(f"  {'[OK]' if ok else '[MISS]'} GPT_SoVITS/{ref}")

print("\nDone!")

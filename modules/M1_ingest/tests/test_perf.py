"""M1 性能测试：视频 ASR + PPTX 提取，复用 Windows 端模型缓存"""
import sys
import os
import json
import time
import logging

_this_dir = os.path.dirname(os.path.abspath(__file__))
# _this_dir = modules/M1_ingest/tests/ → 上 3 层到项目根
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(_this_dir)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

from modules.M1_ingest import ingest_teacher_material

test_dir = os.path.join(_this_dir, "fixtures")
video_path = os.path.join(test_dir, "[3.1.1]--1.2.1数列极限的定义(视频）.mp4")
pptx_path = os.path.join(test_dir, "1.2.1 数列极限的定义.pptx")
output_dir = os.path.join(_this_dir, "test_output", "teachers", "T_TEST_001")

# Windows 端缓存路径（WSL 中通过 /mnt/c 访问）
win_cache = "/mnt/c/Users/Administrator/.cache/huggingface/hub"

print("=" * 60)
print("M1 Performance Test")
print("=" * 60)
print(f"Video: {os.path.basename(video_path)} ({os.path.getsize(video_path)//1024//1024}MB)")
print(f"PPTX:  {os.path.basename(pptx_path)} ({os.path.getsize(pptx_path)//1024}KB)")
print(f"Model cache: {win_cache}")
print()

t0 = time.time()
result = ingest_teacher_material(
    teacher_id="T_PERF_001",
    source_paths=[video_path, pptx_path],
    output_dir=output_dir,
    config={
        "enable_refine": False,
        "save_audio_samples": True,
        "asr_model": "large-v3",
        "asr_device": "cuda",
        "asr_compute_type": "float16",
        "asr_cache_dir": win_cache,
    },
)
elapsed = time.time() - t0

print(f"\n{'=' * 60}")
print(f"Elapsed: {elapsed:.1f}s ({elapsed/60:.1f}min)")
print(f"Status: {result['status']}")
print(f"Succeeded: {result['succeeded']}/{result['total_source_files']}")

for t in result["transcripts"]:
    src_type = t.get("source_type", "audio")
    chars = t.get("segments_count", 0)
    dur = t.get("duration_sec", 0)
    print(f"  {t['transcript_id']} [{src_type}]: {chars} segments, {dur:.0f}s audio")

if result.get("failed"):
    for f in result["failed"]:
        print(f"  FAILED: {os.path.basename(f['source'])} -> {f.get('error', '')[:120]}")

# 保存结果
os.makedirs(os.path.join(_this_dir, "test_output"), exist_ok=True)
summary_path = os.path.join(_this_dir, "test_output", "perf_result.json")
summary = {k: v for k, v in result.items() if k != "teacher_dirs"}
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"Saved: {summary_path}")

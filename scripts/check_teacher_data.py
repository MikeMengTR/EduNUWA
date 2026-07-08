"""
检查一批教师数据是否符合 M1 契约 + 评价模型测试需求。

用法：python scripts/check_teacher_data.py [data/Teacher_data_new]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from modules.M2_distill.metric_extractor import extract_base_metrics  # noqa: E402

TID_PAT = re.compile(r"^T_[0-9]{8}_[0-9]+$")
TR_SEG_FIELDS = {"segment_id", "start", "end", "text"}
MAN_SAMPLE_FIELDS = {"sample_id", "path", "duration_sec", "source_transcript", "source_segment", "snr_estimate"}


def check_course(course: Path) -> dict:
    trs = sorted(course.glob("transcripts/TR_*.json"))
    rep = {"name": course.name, "transcripts": len(trs)}
    if not trs:
        rep["error"] = "无 transcript"
        return rep

    tid = None
    total_chars = total_dur = total_segs = 0
    seg_ok = True
    for tr in trs:
        d = json.loads(tr.read_text(encoding="utf-8"))
        tid = d.get("teacher_id")
        segs = d.get("segments", [])
        total_segs += len(segs)
        total_chars += sum(len(s.get("text", "")) for s in segs)
        if segs and all(TR_SEG_FIELDS <= set(s) for s in segs):
            total_dur += sum(s["end"] - s["start"] for s in segs)
        else:
            seg_ok = False

    rep["teacher_id"] = tid
    rep["tid_format_ok"] = bool(TID_PAT.match(tid or ""))
    rep["seg_fields_ok"] = seg_ok
    rep["total_segments"] = total_segs
    rep["total_chars"] = total_chars
    rep["total_duration_sec"] = round(total_dur)

    # 评价模型实测：base_metrics（纯计算）
    bm = extract_base_metrics(trs[0])
    rep["base_metrics"] = bm.get("base_metrics") if bm.get("status") == "success" else bm

    # manifest + wav 存在性
    man = course / "audio_samples" / "manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        samples = m.get("samples", [])
        rep["manifest_samples"] = len(samples)
        rep["manifest_fields_ok"] = all(MAN_SAMPLE_FIELDS <= set(s) for s in samples) if samples else False
        wav_ok = sum(1 for s in samples if (course / "audio_samples" / s["path"]).exists())
        rep["wav_exist"] = f"{wav_ok}/{len(samples)}"
    else:
        rep["manifest_samples"] = "无 manifest"
    return rep


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "data" / "Teacher_data_new"
    courses = sorted([d for d in root.iterdir() if d.is_dir()])
    print(f"检查目录: {root}\n课程数: {len(courses)}\n" + "=" * 60)
    for c in courses:
        r = check_course(c)
        print(f"\n■ {r['name']}")
        if "error" in r:
            print(f"  [错误] {r['error']}"); continue
        print(f"  teacher_id: {r['teacher_id']}  →  格式合规(T_YYYYMMDD_seq): {'✅' if r['tid_format_ok'] else '❌'}")
        print(f"  转写: {r['transcripts']} 份  段: {r['total_segments']}  字: {r['total_chars']}  时长: {r['total_duration_sec']}s")
        print(f"  段字段齐全: {'✅' if r['seg_fields_ok'] else '❌'}")
        print(f"  base_metrics(真计算): {r['base_metrics']}")
        print(f"  manifest样本: {r['manifest_samples']}  字段齐全: {'✅' if r.get('manifest_fields_ok') else '❌'}  wav存在: {r.get('wav_exist','-')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

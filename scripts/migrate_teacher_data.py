"""
把 data/Teacher_data_new 的真实 M1 数据迁到规范位置 data/teachers/{teacher_id}/。

做的事：
  1. 给每门课分配合规 teacher_id（T_YYYYMMDD_seq）
  2. 复制 transcripts/ + audio_samples/ 到 data/teachers/{tid}/
  3. 改写 transcript 与 manifest 里的 teacher_id 字段（中文 → 合规）
  4. 生成最小 teacher_card.json（demo 用，标注课程/学校）

保留：transcript_id / 文件名 / manifest 引用（三者内部自洽，仅用了中文，不影响 schema）
保留：data/Teacher_data_new 原始数据不动（复制而非移动）

用法：python scripts/migrate_teacher_data.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data" / "Teacher_data_new"
DST = REPO / "data" / "teachers"
DATE = "20260604"

# 固定课程 → teacher_id 映射（按序号）
COURSES = [
    "概率论_某高校",
    "高等数学（一）_某高校",
    "机器学习_某高校",
    "思想道德与法治_某高校",
    "西方园林历史与艺术_某高校",
    "线性代数_某高校",
]


def split_course(name: str) -> tuple[str, str]:
    """'概率论_某高校' → (subject, school)。"""
    parts = name.rsplit("_", 1)
    subject = parts[0].replace("（一）", "").replace("(一)", "")
    school = parts[1] if len(parts) > 1 else ""
    return subject, school


def migrate_one(course: str, seq: int) -> dict:
    tid = f"T_{DATE}_{seq:03d}"
    subject, school = split_course(course)
    src = SRC / course
    dst = DST / tid
    dst.mkdir(parents=True, exist_ok=True)

    # 复制两个子目录
    for sub in ("transcripts", "audio_samples"):
        s = src / sub
        if s.exists():
            shutil.copytree(s, dst / sub, dirs_exist_ok=True)

    # 改写 transcript 的 teacher_id
    n_tr = 0
    for tr in (dst / "transcripts").glob("TR_*.json"):
        d = json.loads(tr.read_text(encoding="utf-8"))
        d["teacher_id"] = tid
        tr.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        n_tr += 1

    # 改写 manifest 的 teacher_id
    man = dst / "audio_samples" / "manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        m["teacher_id"] = tid
        man.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")

    # 最小 teacher_card.json（demo）
    card = {
        "teacher_id": tid,
        "display_name": f"{subject}·{school}",
        "real_name": "",
        "subject": [subject],
        "school": school,
        "_note": "demo data migrated from Teacher_data_new",
    }
    (dst / "teacher_card.json").write_text(
        json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"course": course, "tid": tid, "subject": subject, "transcripts": n_tr}


def main() -> int:
    if not SRC.exists():
        print(f"[错误] 源目录不存在: {SRC}")
        return 1
    print(f"迁移 {len(COURSES)} 门课: {SRC}  →  {DST}\n" + "=" * 60)
    for i, course in enumerate(COURSES, 1):
        r = migrate_one(course, i)
        print(f"  {r['tid']}  ←  {r['course']}  (subject={r['subject']}, {r['transcripts']} 份转写)")
    print(f"\n完成。原始 data/Teacher_data_new 保留不动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
对 6 位老师做【完整蒸馏】（走 nuwa_distill → SKILL.md 7-phase agent 流程）。

每位：合并其全部转写（截到字数上限以控时间/context）→ 完整蒸馏
      → 产出 TeacherSkill.md（7段契约）+ skill_profile.json（评价指标）到 skills/v2_full/

串行跑（claude-agent-sdk 每位起一次 CLI，串行更稳）。预计 30-45 分钟。

用法：python scripts/distill_all_full.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "modules" / "M2_distill" / "skill_distiller"))
from nuwa_distill import distill_teacher_skill  # noqa: E402

TEACHERS_DIR = REPO / "data" / "teachers"
TIDS = [f"T_20260604_{i:03d}" for i in range(1, 7)]
CHAR_LIMIT = 8000   # 每位蒸馏语料上限（已验证 5000-6000 字足够，截断控时间与 context）


def merge_transcripts(tid: str, char_limit: int = CHAR_LIMIT) -> tuple[Path, int]:
    """合并一位老师的全部转写为一个临时 transcript（seg_id 加文件前缀防冲突）。"""
    tdir = TEACHERS_DIR / tid
    trs = sorted(tdir.glob("transcripts/TR_*.json"))
    merged_segs, chars = [], 0
    for i, tr in enumerate(trs):
        d = json.loads(tr.read_text(encoding="utf-8"))
        for s in d.get("segments", []):
            if chars >= char_limit:
                break
            s2 = dict(s)
            s2["segment_id"] = f"f{i}_" + s.get("segment_id", f"seg_{len(merged_segs):04d}")
            merged_segs.append(s2)
            chars += len(s.get("text", ""))
        if chars >= char_limit:
            break
    merged = {
        "transcript_id": f"TR_{tid.replace('_','')}_merged",
        "teacher_id": tid, "language": "zh", "segments": merged_segs,
    }
    out = tdir / "_merged_for_distill.json"
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return out, chars


def main() -> int:
    print(f"完整蒸馏 {len(TIDS)} 位老师（每位语料上限 {CHAR_LIMIT} 字）")
    print("=" * 64)
    results = []
    for idx, tid in enumerate(TIDS, 1):
        card = json.loads((TEACHERS_DIR / tid / "teacher_card.json").read_text(encoding="utf-8"))
        subject = card["subject"][0]
        name = card["display_name"]
        merged, chars = merge_transcripts(tid)
        out_dir = TEACHERS_DIR / tid / "skills" / "v2_full"
        print(f"\n[{idx}/{len(TIDS)}] {name}（{subject}）合并 {chars} 字，蒸馏中 ...", flush=True)
        t0 = time.time()
        res = distill_teacher_skill(
            str(merged), str(out_dir),
            config={"teacher_name": name, "subject": subject, "timeout_sec": 700},
        )
        dt = round(time.time() - t0)
        ok = res.get("status") == "success"
        results.append({"tid": tid, "name": name, "ok": ok, "elapsed": dt,
                        "skill_md": res.get("skill_md"), "msg": res.get("message")})
        print(f"     {'✅ 成功' if ok else '❌ 失败:'+str(res.get('message'))}  ({dt}s)", flush=True)

    print("\n" + "=" * 64)
    print("完整蒸馏汇总：")
    for r in results:
        print(f"  {'✅' if r['ok'] else '❌'} {r['name']}  {r['elapsed']}s")
    n_ok = sum(1 for r in results if r["ok"])
    print(f"\n成功 {n_ok}/{len(TIDS)}")
    return 0 if n_ok == len(TIDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())

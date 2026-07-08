"""
真实闭环 demo：把 6 位【完整蒸馏】的老师接进匹配模型。

数据源：data/teachers/T_20260604_*/skills/v2_full/skill_profile.json（真实蒸馏产物）
对一组针对性自然语言需求跑匹配，看能否精准召回对味的老师。

完整链路：真转写 → 真蒸馏(TeacherSkill+评价) → 真匹配

用法：python scripts/demo_match_real.py ["自定义需求"]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from modules.M3_catalog.matching_engine.matcher import match_teachers  # noqa: E402


def load_real_teachers() -> list[dict]:
    teachers = []
    for tdir in sorted((REPO / "data" / "teachers").glob("T_20260604_*")):
        p = tdir / "skills" / "v2_full" / "skill_profile.json"
        if not p.exists():
            continue
        prof = json.loads(p.read_text(encoding="utf-8"))
        teachers.append({
            "teacher_id": prof["teacher_id"],
            "teacher_name": prof.get("teacher_name", prof["teacher_id"]),
            "subject": prof.get("attributes", {}).get("subject", ""),
            "grade": prof.get("quality", {}).get("overall_grade", "NA"),
            "style_tags": [t["text"] for t in prof.get("style_tags", [])],
            "base_metrics": {k: v.get("label", "") for k, v in prof.get("base_metrics", {}).items()},
        })
    return teachers


# 针对性需求：每条预期命中一类不同风格的老师
DEFAULT_QUERIES = [
    "我想找讲技术发展历史、把概念来龙去脉和背后人物讲清楚的老师",      # → 机器学习(以人物串讲技术史)
    "我要严谨的数学老师，定义清楚、一步步推导、用几何直觉帮助理解",      # → 线代/高数
    "我想要结合生活例子、互动提问多、节奏慢一点的老师",              # → 概率论
    "我喜欢会引经据典、正反对比讲道理、联系学生实际的老师",            # → 思政
    "我对历史背景和古今中外对比的讲法感兴趣，喜欢系统铺垫的老师",        # → 园林
    "我基础比较弱，想要从具体例子讲起、能连接中学知识的老师",          # → 线代/高数
]


def run(query: str, teachers: list[dict]) -> None:
    print(f"\n{'='*72}\n【学生需求】{query}\n{'='*72}")
    res = match_teachers(query, teachers)
    if res["status"] != "success":
        print(f"  [失败] {res['message']}")
        return
    for rank, r in enumerate(res["results"][:3], 1):
        fit = r.get("semantic_fit")
        fit_s = f"{fit:.2f}" if isinstance(fit, (int, float)) else str(fit)
        print(f"  {rank}. {r['teacher_name']}（{r['subject']}）  贴合度={fit_s}")
        print(f"     {r['reason']}")
        if r["matched_tags"]:
            print(f"     命中标签：{'、'.join(r['matched_tags'])}")
        if r["hallucinated_tags"]:
            print(f"     ⚠️ 幻觉标签(已过滤)：{'、'.join(r['hallucinated_tags'])}")


def main() -> int:
    teachers = load_real_teachers()
    if not teachers:
        print("[错误] 未找到 v2_full skill_profile，请先跑 scripts/distill_all_full.py")
        return 1
    print(f"已加载 {len(teachers)} 位【真实蒸馏】老师：")
    for t in teachers:
        print(f"  · {t['teacher_name']}（{t['subject']}）{len(t['style_tags'])}个风格标签")

    queries = [sys.argv[1]] if len(sys.argv) > 1 else DEFAULT_QUERIES
    for q in queries:
        run(q, teachers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

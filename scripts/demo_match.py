"""
评价 + 匹配 本地 demo：

1. 加载造好的 6 个老师 skill_profile
2. 对几个不同的自然语言需求跑匹配
3. 打印排序 + 推荐理由 + 防幻觉校验结果

跑法：
    python scripts/demo_match.py
    python scripts/demo_match.py "我想找个讲得慢、有耐心的高数老师"
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from modules.M3_catalog.matching_engine.matcher import load_teachers, match_teachers  # noqa: E402

FIXTURES = REPO / "modules" / "M3_catalog" / "tests" / "fixtures" / "mock_teachers"

DEFAULT_QUERIES = [
    "我想找个讲题像讲故事、轻松幽默、不那么死板的老师",
    "我要严谨的、每步推导都讲清楚、逻辑严密的老师",
    "我想要讲得慢一点、有耐心、能照顾基础差的同学的高数老师",
    "我喜欢老师多提问、引导我自己思考，而不是直接灌答案",
    "我备考时间紧，想要节奏快、直接讲考点和解题套路的老师",
]


def run(query: str, teachers: list[dict]) -> None:
    print(f"\n{'='*70}\n【学生需求】{query}\n{'='*70}")
    res = match_teachers(query, teachers)
    if res["status"] != "success":
        print(f"  [匹配失败] {res['message']}")
        return
    for rank, r in enumerate(res["results"], 1):
        fit = r.get("semantic_fit")
        fit_s = f"{fit:.2f}" if isinstance(fit, (int, float)) else str(fit)
        print(f"  {rank}. {r['teacher_name']}（{r['subject']}）  贴合度={fit_s}")
        print(f"     理由：{r['reason']}")
        if r["matched_tags"]:
            print(f"     命中标签：{'、'.join(r['matched_tags'])}")
        if r["hallucinated_tags"]:
            print(f"     ⚠️ 幻觉标签(已过滤)：{'、'.join(r['hallucinated_tags'])}")


def main() -> int:
    teachers = load_teachers(FIXTURES)
    if not teachers:
        print(f"[错误] 没加载到老师，请先跑：python scripts/gen_mock_teachers.py")
        return 1
    print(f"已加载 {len(teachers)} 个候选老师：" +
          "、".join(f"{t['teacher_name']}({t['grade']})" for t in teachers))

    queries = [sys.argv[1]] if len(sys.argv) > 1 else DEFAULT_QUERIES
    for q in queries:
        run(q, teachers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

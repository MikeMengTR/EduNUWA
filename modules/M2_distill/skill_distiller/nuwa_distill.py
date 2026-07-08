"""
EduNUWA TeacherSkill 蒸馏器。

支持两种 Skill 后端，可通过 config["skill"] 或 CLI --skill 切换:

    1. edunuwa-teacher-distiller (默认)
       本项目自有 Skill。输入: 教师转写 JSON。输出: 7 段契约 TeacherSkill.md。
       严格走本地语料，不联网。

    2. nuwa-skill (原版女娲, 对照基线)
       上游开源 Skill。同样使用本地语料模式，但产出按"人物视角"组织;
       本脚本会要求其将最终文件重命名为 TeacherSkill.md，便于与 (1) 对比。

两个 Skill 都已 vendor 在 .claude/skills/ 下，无需联网安装。

函数接口（符合 docs/api_contract.md §7.2）::

    distill_teacher_skill(transcript_path, output_dir, config) -> dict

CLI 用法（v2 路径）::

    python modules/M2_distill/skill_distiller/nuwa_distill.py \\
        --transcript data/teachers/T_legacy_001/transcripts/TR_Tlegacy001_001.json \\
        --output    data/teachers/T_legacy_001/skills/v3/ \\
        --skill     edunuwa-teacher-distiller \\
        --teacher   示例老师 \\
        --subject   高等数学
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 让脚本以两种方式运行均可: `python nuwa_distill.py` 或 `python -m ...`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    AVAILABLE_SKILLS,
    REPO_ROOT,
    load_env,
    make_options,
    run_agent_task,
)


# ============================================================
# Prompt 模板
# ============================================================
def _build_prompt_edunuwa(
    transcript_path: Path,
    output_dir: Path,
    teacher_name: str,
    subject: str,
) -> str:
    return f"""请使用项目内已 vendor 的 edunuwa-teacher-distiller Skill 完成教师讲解风格蒸馏任务。

【输入】
- 教师授课转写文件: {transcript_path}
- 教师标识: {teacher_name}
- 学科: {subject}
- 输出目录: {output_dir}

【任务】
1. 调用 edunuwa-teacher-distiller Skill。
2. 严格按 SKILL.md 中的 Phase 0 → Phase 4 顺序执行。
3. 按 docs/api_contract.md §3 的 7 段契约写入文件:
       {output_dir}/TeacherSkill.md
4. 同步生成元数据文件:
       {output_dir}/skill_profile.json
5. 全程默认批准所有工具调用，不要询问用户。
6. 完成后明确输出最终文件路径。

【硬约束】
- 不允许任何联网搜索（不调用 WebSearch / WebFetch）。
- 一切结论必须以 {transcript_path} 为唯一一手语料。
- TeacherSkill.md 必须包含全部 7 段:
  Skill Purpose / Trigger / Teaching Philosophy / Explanation Pattern /
  Blackboard Policy / Speech Policy / Output Contract
- Output Contract 中事件类型集合必须等于:
  speak / board / formula / table / pause / quiz
"""


def _build_prompt_nuwa(
    transcript_path: Path,
    output_dir: Path,
    teacher_name: str,
    subject: str,
) -> str:
    return f"""请使用项目内已 vendor 的 huashu-nuwa Skill（原版女娲），按"本地语料模式"蒸馏一位教师的讲解思维。这是与 edunuwa-teacher-distiller 的对照实验。

【输入】
- 蒸馏对象: {teacher_name}（{subject} 教师）
- 一手语料: {transcript_path}（教师授课转写 JSON）
- 输出目录: {output_dir}

【模式约束 — 重要】
- 严格走"本地语料模式"（参考 SKILL.md Phase 1 的"本地语料优先 / 纯本地语料"分支）。
- 不要执行 Phase 1 的 6-Agent 网络搜索（不要 WebSearch / WebFetch）。
- 转写文本作为最高权重的一手素材。

【输出适配 — 重要】
- 不要使用默认的 [person]-perspective/ 子目录命名。
- 直接将最终 SKILL 文件写入: {output_dir}/TeacherSkill.md
- 同步生成简短元数据文件: {output_dir}/skill_profile.json
  内容包括: 教师名、学科、转写源路径、生成时间、distiller 标识。
- 文件名必须叫 TeacherSkill.md（用于与 edunuwa-teacher-distiller 对照）。

【其他】
- 全程默认批准所有工具调用，不要询问用户。
- 完成后明确输出最终文件路径。
"""


_PROMPT_BUILDERS = {
    "edunuwa-teacher-distiller": _build_prompt_edunuwa,
    "nuwa-skill": _build_prompt_nuwa,
}


# ============================================================
# 主函数（符合 api_contract.md §7.2）
# ============================================================
def distill_teacher_skill(
    transcript_path: str | Path,
    output_dir: str | Path,
    config: dict | None = None,
) -> dict:
    """
    从教师授课转写文本蒸馏 TeacherSkill.md。

    Args:
        transcript_path: teacher_transcript.json 路径（schema 见 api_contract §2）。
        output_dir: 输出目录，TeacherSkill.md 与 skill_profile.json 落盘点。
        config: 可选配置:
            - skill (str)        : "edunuwa-teacher-distiller" | "nuwa-skill"，默认前者
            - teacher_name (str) : 教师标识，默认 "未指定"
            - subject (str)      : 学科，默认 "未指定"
            - max_turns (int)    : Agent 最大轮数，默认 40
            - timeout_sec (int)  : 超时秒数，默认 900

    Returns:
        成功::
            {
              "status": "success",
              "skill": "<skill_id>",
              "skill_md": "<path>",
              "skill_profile": "<path>"
            }
        失败::
            {
              "status": "error",
              "message": "...",
              "skill": "<skill_id>",
              ...
            }
    """
    config = dict(config or {})
    skill_id: str = config.get("skill", "edunuwa-teacher-distiller")
    teacher_name: str = config.get("teacher_name", "未指定")
    subject: str = config.get("subject", "未指定")
    max_turns: int = int(config.get("max_turns", 40))
    timeout_sec: int = int(config.get("timeout_sec", 900))

    # ---------- 1. 校验 Skill 选择 ----------
    if skill_id not in AVAILABLE_SKILLS:
        return {
            "status": "error",
            "message": f"unknown skill {skill_id!r}; available: {list(AVAILABLE_SKILLS)}",
        }
    skill_meta = AVAILABLE_SKILLS[skill_id]
    skill_dir: Path = skill_meta["dir"]
    if not skill_dir.exists():
        return {
            "status": "error",
            "message": f"skill not vendored: {skill_dir}",
            "skill": skill_id,
        }

    # ---------- 2. 校验输入 / 准备输出 ----------
    transcript_path = Path(transcript_path)
    if not transcript_path.exists():
        return {
            "status": "error",
            "message": f"transcript not found: {transcript_path}",
            "skill": skill_id,
        }

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    skill_md_path = output_dir / "TeacherSkill.md"
    skill_profile_path = output_dir / "skill_profile.json"
    debug_log = output_dir / "claude-debug.log"

    # ---------- 3. 构造 prompt ----------
    prompt = _PROMPT_BUILDERS[skill_id](
        transcript_path=transcript_path,
        output_dir=output_dir,
        teacher_name=teacher_name,
        subject=subject,
    )

    # ---------- 4. 运行 Agent ----------
    options = make_options(
        cwd=REPO_ROOT,  # 让 .claude/skills/ 被向上发现
        max_turns=max_turns,
        debug_log=debug_log,
    )

    print(f"[distill] skill        = {skill_id}  ({skill_meta['description']})")
    print(f"[distill] transcript   = {transcript_path}")
    print(f"[distill] output_dir   = {output_dir}")
    print(f"[distill] debug_log    = {debug_log}")
    print(f"[distill] teacher/sub  = {teacher_name} / {subject}")
    print()

    run_result = run_agent_task(
        prompt,
        options,
        timeout_sec=timeout_sec,
        debug_log=debug_log,
    )

    # ---------- 5. 校验产出 ----------
    if run_result.get("status") != "success":
        run_result.setdefault("skill", skill_id)
        run_result.setdefault("transcript_path", str(transcript_path))
        return run_result

    if not skill_md_path.exists():
        return {
            "status": "error",
            "message": f"agent did not produce TeacherSkill.md at {skill_md_path}",
            "skill": skill_id,
            "debug_log": str(debug_log),
        }

    # 兜底补一份 skill_profile.json（如果 Agent 没生成）
    if not skill_profile_path.exists():
        profile = {
            "skill_id": f"TeacherSkill_{datetime.now().strftime('%Y%m%dT%H%M%S')}",
            "teacher_name": teacher_name,
            "subject": subject,
            "source_transcript": str(transcript_path),
            "skill_md_path": str(skill_md_path),
            "distiller": skill_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "note": "auto-generated by distiller (agent did not write profile)",
        }
        skill_profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "status": "success",
        "skill": skill_id,
        "skill_md": str(skill_md_path),
        "skill_profile": str(skill_profile_path),
    }


# ============================================================
# CLI 入口
# ============================================================
def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nuwa_distill",
        description="EduNUWA TeacherSkill 蒸馏器（支持两种 Skill 后端）。",
    )
    parser.add_argument(
        "--transcript",
        required=True,
        help="教师转写文件路径 (teacher_transcript.json)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="输出目录 (TeacherSkill.md 与 skill_profile.json 写入此目录)",
    )
    parser.add_argument(
        "--skill",
        choices=list(AVAILABLE_SKILLS),
        default="edunuwa-teacher-distiller",
        help="选择 Skill 后端 (默认: edunuwa-teacher-distiller)",
    )
    parser.add_argument("--teacher", default="未指定", help="教师标识")
    parser.add_argument("--subject", default="未指定", help="学科")
    parser.add_argument("--max-turns", type=int, default=40, help="Agent 最大轮数")
    parser.add_argument("--timeout", type=int, default=900, help="超时秒数")
    return parser


def main() -> int:
    args = _build_cli().parse_args()
    load_env()

    result = distill_teacher_skill(
        transcript_path=args.transcript,
        output_dir=args.output,
        config={
            "skill": args.skill,
            "teacher_name": args.teacher,
            "subject": args.subject,
            "max_turns": args.max_turns,
            "timeout_sec": args.timeout,
        },
    )

    print("\n=========== distill result ===========")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())

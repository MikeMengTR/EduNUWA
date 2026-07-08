"""
modules.skill_distiller 公共基础设施。

职责:
  - 统一加载 .env
  - 构造 Claude Agent SDK 的环境变量与运行选项
  - 流式打印 SDK 各类消息
  - 同步包装 query() 调用，统一异常处理与返回格式

不直接对外暴露业务逻辑，业务脚本（nuwa_distill.py 等）调用本模块。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

# Windows 默认 GBK 控制台无法直接 print emoji / 罕见 Unicode；
# Agent 输出含 💡 ⚠️ 📝 等会触发 UnicodeEncodeError 让进程整体崩溃。
# 在导入任何打印路径之前重设 stdout/stderr 编码。
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is None:
        continue
    if getattr(_stream, "encoding", "").lower() in ("utf-8", "utf8"):
        continue
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

try:
    import anyio
    from dotenv import load_dotenv

    from claude_agent_sdk import (
        AssistantMessage,
        CLIJSONDecodeError,
        CLINotFoundError,
        ClaudeAgentOptions,
        ProcessError,
        ResultMessage,
        SystemMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        query,
    )
except ImportError as _e:  # W8: 友好提示替代裸 ImportError 栈
    _missing = getattr(_e, "name", None) or "<unknown>"
    sys.stderr.write(
        "\n[edunuwa-distiller] 缺少依赖: "
        f"{_missing}\n"
        "可能原因（按概率排序）:\n"
        "  1. 当前未激活 conda 环境。请先运行:\n"
        "         conda activate edu\n"
        "     再启动本脚本。\n"
        "  2. 依赖未安装。在 edu 环境内运行:\n"
        "         pip install -r requirements.txt\n"
        "  3. Python 解释器选错了。请用 `where python` 确认指向 edu 环境，\n"
        "     或使用绝对路径，例如:\n"
        "         D:\\anaconda3\\envs\\edu\\python.exe modules/M2_distill/skill_distiller/nuwa_distill.py ...\n"
    )
    sys.exit(2)


# ============================================================
# 路径常量
# ============================================================
THIS_DIR = Path(__file__).resolve().parent
MODULES_DIR = THIS_DIR.parent
# 修复：MODULES_DIR 实为 modules/M2_distill，仓库根需再上两级
# （skill_distiller → M2_distill → modules → <repo root>）。
# 之前误写成 MODULES_DIR.parent（=modules/），导致 .env 与 .claude/skills 找不到。
REPO_ROOT = THIS_DIR.parents[2]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

#: Skill 后端注册表。新增 Skill 在此添加即可被 distiller 选择。
AVAILABLE_SKILLS: dict[str, dict] = {
    "edunuwa-teacher-distiller": {
        "dir": SKILLS_DIR / "edunuwa-teacher-distiller",
        "trigger_name": "edunuwa-teacher-distiller",
        "description": "EduNUWA 自有教师讲解蒸馏 Skill（输出 7 段契约 + Output Contract）",
    },
    "nuwa-skill": {
        "dir": SKILLS_DIR / "nuwa-skill",
        "trigger_name": "huashu-nuwa",  # 来自上游 SKILL.md frontmatter name
        "description": "原版女娲（人物思维框架蒸馏，使用本地语料模式作为对照基线）",
    },
}


# ============================================================
# 环境变量加载
# ============================================================
_ENV_LOADED = False


def load_env(env_path: Path | None = None) -> None:
    """从仓库根 .env 加载环境变量，幂等。"""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_path = env_path or (REPO_ROOT / ".env")
    if env_path.exists():
        load_dotenv(env_path, override=False)
    _ENV_LOADED = True


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"缺少必需的环境变量 {name}。"
            f"请在 {REPO_ROOT / '.env'} 中配置（参考 .env.example）。"
        )
    return value


def build_agent_env() -> dict[str, str]:
    """
    组装传给 ClaudeAgentOptions(env=...) 的字典。

    DeepSeek 通过 Anthropic 兼容协议接入 Claude Code CLI。
    """
    load_env()
    api_key = _require("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro[1m]")
    effort = os.getenv("CLAUDE_CODE_EFFORT_LEVEL", "max")
    return {
        **os.environ,
        # DeepSeek Anthropic 兼容入口
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_API_KEY": api_key,
        # Claude Code 模型映射
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_CODE_EFFORT_LEVEL": effort,
        # ----- W2: 静默 Anthropic telemetry 上报（DeepSeek 后端不实现该端点，会刷 403）
        "OTEL_SDK_DISABLED": "true",
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        # ----- W3: 关闭 plugin marketplace 自动更新（国内 GitHub 不稳，常超时 120s）
        "DISABLE_AUTOUPDATER": "1",
    }


# ============================================================
# 消息打印
# ============================================================
def _safe_print(*args, **kwargs) -> None:
    """print 的兜底版本：即使 stdout 编码无法处理某字符，也保证不抛 UnicodeEncodeError。"""
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", "ascii") or "ascii"
        safe = [
            (a.encode(enc, errors="replace").decode(enc, errors="replace") if isinstance(a, str) else a)
            for a in args
        ]
        try:
            print(*safe, **kwargs)
        except Exception:
            pass


def print_stderr(text: str) -> None:
    _safe_print(f"[claude stderr] {text}", end="", flush=True)


def print_message(msg) -> None:
    """流式打印 SDK 消息，兼容不同消息块类型。"""
    if isinstance(msg, AssistantMessage):
        for block in msg.content:
            if isinstance(block, TextBlock):
                _safe_print(block.text, flush=True)
            elif isinstance(block, ToolUseBlock):
                _safe_print(f"\n[tool call] {block.name}", flush=True)
                _safe_print(f"[tool input] {block.input}\n", flush=True)
            elif isinstance(block, ToolResultBlock):
                _safe_print(f"\n[tool result] {getattr(block, 'content', '')}\n", flush=True)
            else:
                _safe_print(f"\n[unknown block] {block}\n", flush=True)
    elif isinstance(msg, SystemMessage):
        _safe_print(f"\n[system] {msg}\n", flush=True)
    elif isinstance(msg, ResultMessage):
        _safe_print("\n========== task finished ==========", flush=True)
        _safe_print(f"is_error   : {getattr(msg, 'is_error', None)}", flush=True)
        _safe_print(f"stop_reason: {getattr(msg, 'stop_reason', None)}", flush=True)
        _safe_print(f"num_turns  : {getattr(msg, 'num_turns', None)}", flush=True)
        result = getattr(msg, "result", None)
        if result:
            _safe_print(f"\n[final result]\n{result}", flush=True)
        errors = getattr(msg, "errors", None)
        if errors:
            _safe_print(f"\n[errors]\n{errors}", flush=True)
    else:
        _safe_print(f"\n[other] {msg}\n", flush=True)


# ============================================================
# 选项构造
# ============================================================
DEFAULT_TOOLS: tuple[str, ...] = (
    "Skill",
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "LS",
)


def make_options(
    *,
    cwd: Path | str = REPO_ROOT,
    allowed_tools: Iterable[str] | None = None,
    max_turns: int = 40,
    debug_log: Path | None = None,
) -> ClaudeAgentOptions:
    """构造一个标准 ClaudeAgentOptions，调用方可在此基础上叠加。"""
    tools = list(allowed_tools) if allowed_tools else list(DEFAULT_TOOLS)
    extra_args: dict[str, str] = {}
    if debug_log is not None:
        debug_log.parent.mkdir(parents=True, exist_ok=True)
        extra_args["debug-file"] = str(debug_log)
    return ClaudeAgentOptions(
        cwd=str(cwd),
        env=build_agent_env(),
        # user / project / local 三级 settings 都加载，
        # Skill 自动从 .claude/skills/ 发现
        setting_sources=["user", "project", "local"],
        allowed_tools=tools,
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        stderr=print_stderr,
        extra_args=extra_args,
    )


# ============================================================
# 任务执行（同步包装）
# ============================================================
async def _run_async_impl(prompt: str, options: ClaudeAgentOptions, timeout_sec: int) -> None:
    with anyio.fail_after(timeout_sec):
        async for msg in query(prompt=prompt, options=options):
            print_message(msg)


def run_agent_task(
    prompt: str,
    options: ClaudeAgentOptions,
    *,
    timeout_sec: int = 900,
    debug_log: Path | None = None,
) -> dict:
    """
    同步运行一次 Agent query，返回标准 dict。

    所有 SDK 异常都被收敛为 {"status": "error", "message": ...}，
    不向外抛栈，便于上层封装为 api_contract 风格的接口。
    """
    debug_str = str(debug_log) if debug_log else None
    try:
        anyio.run(_run_async_impl, prompt, options, timeout_sec)
        # W4: 显式终止标记，方便事后日志检索
        _safe_print("\n[run_agent_task] agent query loop finished cleanly", flush=True)
        return {"status": "success"}
    except TimeoutError:
        m = f"agent timed out after {timeout_sec}s"
        print(f"\n[timeout] {m}", flush=True)
        if debug_str:
            print(f"          debug log: {debug_str}", flush=True)
        return {"status": "error", "message": m, "debug_log": debug_str}
    except CLINotFoundError:
        m = (
            "Claude Code CLI not found. "
            "Please run: npm install -g @anthropic-ai/claude-code"
        )
        print(f"\n[error] {m}", flush=True)
        return {"status": "error", "message": m}
    except CLIJSONDecodeError as e:
        m = f"CLI returned non-JSON: {e}"
        print(f"\n[error] {m}", flush=True)
        return {"status": "error", "message": m, "debug_log": debug_str}
    except ProcessError as e:
        m = f"Claude Code subprocess failed: {e}"
        print(f"\n[error] {m}", flush=True)
        return {"status": "error", "message": m, "debug_log": debug_str}
    except KeyboardInterrupt:
        m = "interrupted by user"
        print(f"\n[interrupted] {m}", flush=True)
        return {"status": "error", "message": m}

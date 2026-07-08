# Agent 教学事件生成模块

> 入口文件: [`teaching_events.py`](teaching_events.py)
> 单元测试: [`test_teaching_events.py`](test_teaching_events.py)
> 公共基础设施复用: `../skill_distiller/_common.py`

## 模块说明

读取三份输入：
- `TeacherSkill.md`（怎么讲——风格）
- `retrieved_context.md`（讲什么——课程知识）
- 用户问题（讲哪个）

通过 Claude Agent SDK + DeepSeek 生成符合 [`docs/api_contract.md §5`](../../docs/api_contract.md) 的 `teaching_events.json`，作为驱动 TTS / Live2D / 黑板的核心文件。

## 函数接口

签名严格遵循 `api_contract.md §7.4`：

```python
from modules.agent_generator.teaching_events import generate_teaching_events

result = generate_teaching_events(
    question="什么是过拟合？",
    teacher_skill_path="data/teacher_skill/TeacherSkill.md",
    retrieved_context_path="data/retrieved_context/retrieved_context_001.md",
    output_dir="data/events/",
    config={
        "need_board": True,
        "need_formula": True,
        "need_quiz": False,
        "target_count": "8 到 16",
        "max_turns": 25,
        "timeout_sec": 600,
        "file_tag": "demo_001",
        # 可选：注入到顶层对象的元数据
        "course_id": "course_demo_001",
        "skill_id": "teacher_style_skill_001",
        "language": "zh",
    },
)
# {
#   "status": "success",
#   "events_path": "data/events/teaching_events_demo_001.json",
#   "events_count": 12
# }
```

失败时返回：
```python
{
  "status": "error",
  "message": "...",
  "question": "...",
  # 视情形可能包含: events_path / raw_dump / debug_log
}
```

## 事件 schema（来自 `api_contract.md §5`）

顶层对象：
```json
{
  "event_file_id": "teaching_events_xxx",
  "question_id":   "q_xxx",
  "language":      "zh",
  "events":        [ ... ]
}
```

事件类型集合 = `speak / board / formula / table / pause / quiz`

| 类型 | 必需字段 | 备注 |
|---|---|---|
| `speak` | `text` | 用于 TTS |
| `board` | `action` ∈ {`write_title`, `write_subtitle`, `write_bullets`, `write_steps`, `write_summary`, `clear_board`, `highlight`}; `clear_board` 外都需 `content` | 用于黑板 |
| `formula` | `latex`；自动补 `display_mode=block` | 用于公式区 |
| `table` | `columns`, `rows`（rows 中每行长度 == columns 长度）；`title` 可选 | 用于对比表 |
| `pause` | 无；自动补 `duration_ms=600` | 用于 TTS 停顿 |
| `quiz` | `question`；`options`/`answer` 可选 | 用于课堂提问 |

`event_id` (`evt_NNNN`) 与 `seq` (1 起递增) 由代码自动填充，缺失也不会报错。

## CLI 用法

### PowerShell（Windows，推荐）

```powershell
conda activate edu

python modules/agent_generator/teaching_events.py `
    --question "什么是过拟合？" `
    --skill    data/teacher_skill/TeacherSkill.md `
    --context  data/retrieved_context/retrieved_context_001.md `
    --output   data/events/
```

### 完整参数

```
--question      STR     用户问题（必填）
--skill         PATH    TeacherSkill.md 路径（必填）
--context       PATH    retrieved_context.md 路径（必填）
--output        PATH    输出目录（必填）
--need-board    / --no-board       默认开
--need-formula  / --no-formula     默认开
--need-quiz                        默认关
--target-count  STR     目标事件数（默认 "8 到 16"）
--max-turns     INT     Agent 最大轮数（默认 25）
--timeout       INT     超时秒数（默认 600）
--file-tag      STR     event_file_id 后缀（默认时间戳）
```

## 测试

### 1. 离线单元测试（不调 SDK，秒级）

```powershell
python modules/agent_generator/test_teaching_events.py
```

覆盖 35 项：JSON 提取 / dict 包装剥离 / 6 种事件 schema 校验 / demo_cases 样例兼容性 / 输入校验路径。

### 2. 端到端实跑（调 SDK，~3-10 min）

需要先准备 TeacherSkill.md（用 `modules/skill_distiller/nuwa_distill.py` 蒸馏出来）。

```powershell
python modules/agent_generator/teaching_events.py `
    --question "什么是过拟合？" `
    --skill    data/teacher_skill/TeacherSkill.md `
    --context  data/retrieved_context/retrieved_context_001.md `
    --output   data/events/ `
    --file-tag e2e_test_001
```

产物：
- `data/events/teaching_events_e2e_test_001.json` — 校验通过的最终事件流
- `data/events/teaching_events_e2e_test_001.raw.txt` — Agent 原始落盘内容（备查）
- `data/events/teaching_events_e2e_test_001.claude-debug.log` — Claude Code CLI 日志

## 环境准备

> ⚠️ 与 `skill_distiller` 共用 conda 环境与 `.env` 配置；详见 `modules/skill_distiller/README.md` "环境准备"章节。

依赖：
- `claude-agent-sdk`、`anyio`、`python-dotenv`（共享自 `requirements.txt`）
- 复用 `modules/skill_distiller/_common.py`（不重复造轮子）

## 当前状态

- [x] 已完成调研
- [x] 已实现 `generate_teaching_events()` 标准接口
- [x] 已对齐 `api_contract.md §5` schema（speak/board/formula/table/pause/quiz）
- [x] 已写离线单元测试（35 项全过）
- [x] 已与 `skill_distiller` 公共基础设施集成
- [ ] 已端到端实跑验证（待真实 ASR 转写 + 完整 TeacherSkill）
- [ ] 已接入主流程 (`run_demo_pipeline()`)

## 负责人

模块一（TeacherSkill 蒸馏与 Agent 核心逻辑）—— 教学事件生成部分。

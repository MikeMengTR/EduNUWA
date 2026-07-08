# TeacherSkill 蒸馏模块

> 入口文件: [`nuwa_distill.py`](nuwa_distill.py)
> 公共基础设施: [`_common.py`](_common.py)
> 已知问题清单: [`ISSUES.md`](ISSUES.md)

## 模块说明

将教师授课转写文本（`teacher_transcript.json`）蒸馏为讲解风格 Skill 文件（`TeacherSkill.md`），供下游 `agent_generator` 模块作为「怎么讲」的上下文使用。

输入输出格式严格遵循 [`docs/api_contract.md`](../../docs/api_contract.md)：
- 输入: §2 `teacher_transcript.json`
- 输出: §3 `TeacherSkill.md`（七段契约）+ `skill_profile.json`（元数据）

## Skill 后端选择

本模块内置两种 Skill 后端，可通过参数切换：

| 选项 | 适用场景 | 来源 |
|---|---|---|
| `edunuwa-teacher-distiller` *(默认)* | 主线场景。输出 7 段契约 + Output Contract，可直接被 `agent_generator` 消费 | 本项目自有，[详见此处](../../.claude/skills/edunuwa-teacher-distiller/SKILL.md) |
| `nuwa-skill` | 对照基线 / 实验对比。原版女娲（`huashu-nuwa`）走本地语料模式蒸馏，产出按"人物视角"组织 | 上游 [alchaincyf/nuwa-skill](https://github.com/alchaincyf/nuwa-skill)（MIT，已 vendor） |

两个 Skill 都已 vendor 在 `.claude/skills/` 下，无需联网安装。
关于本项目对女娲的范式迁移，详见 [`NOTICE.md`](../../.claude/skills/edunuwa-teacher-distiller/NOTICE.md)。

## 函数接口

签名遵循 `api_contract.md §7.2`：

```python
from modules.skill_distiller.nuwa_distill import distill_teacher_skill

result = distill_teacher_skill(
    transcript_path="data/transcripts/teacher_transcript_001.json",
    output_dir="data/teacher_skill/",
    config={
        "skill": "edunuwa-teacher-distiller",  # 或 "nuwa-skill"
        "teacher_name": "示例老师",
        "subject": "高等数学",
        # 可选: max_turns (默认 40), timeout_sec (默认 900)
    },
)
# result == {
#   "status": "success",
#   "skill": "edunuwa-teacher-distiller",
#   "skill_md": "data/teacher_skill/TeacherSkill.md",
#   "skill_profile": "data/teacher_skill/skill_profile.json",
# }
```

失败时返回：
```python
{
    "status": "error",
    "message": "<原因>",
    "skill": "<skill_id>",
    "debug_log": "<output_dir>/claude-debug.log",  # 可能存在
}
```

## CLI 用法

### PowerShell（Windows，推荐）

PowerShell 续行符是反引号 `` ` ``，不是 `\`（Bash 续行符）。

```powershell
# 使用自有 Skill (默认)
python modules/skill_distiller/nuwa_distill.py `
    --transcript data/transcripts/teacher_transcript_001.json `
    --output    data/teacher_skill/ `
    --teacher   示例老师 `
    --subject   高等数学

# 使用原版女娲作为对照
python modules/skill_distiller/nuwa_distill.py `
    --transcript data/transcripts/teacher_transcript_001.json `
    --output    data/teacher_skill_nuwa_baseline/ `
    --skill     nuwa-skill `
    --teacher   示例老师 `
    --subject   高等数学
```

如果不想分行，单行写最稳（无续行符歧义）：
```powershell
python modules/skill_distiller/nuwa_distill.py --transcript data/transcripts/teacher_transcript_001.json --output data/teacher_skill/ --teacher 示例老师 --subject 高等数学
```

### Bash / Zsh（macOS / Linux / WSL / Git Bash）

```bash
python modules/skill_distiller/nuwa_distill.py \
    --transcript data/transcripts/teacher_transcript_001.json \
    --output    data/teacher_skill/ \
    --teacher   示例老师 \
    --subject   高等数学
```

### 完整参数

```
--transcript  PATH    教师转写文件路径（必填）
--output      PATH    输出目录（必填）
--skill       NAME    edunuwa-teacher-distiller (默认) / nuwa-skill
--teacher     STR     教师标识，默认"未指定"
--subject     STR     学科，默认"未指定"
--max-turns   INT     Agent 最大轮数，默认 40
--timeout     INT     超时秒数，默认 900
```

## 环境准备

> ⚠️ **重要：每次运行前必须先激活 conda 环境，否则会立即报缺依赖。**
>
> ```powershell
> conda activate edu
> ```
>
> 这是因为后台 / IDE / CI 启动的 shell 不会自动继承用户激活的 conda env，
> 而 `claude_agent_sdk`、`dotenv` 等关键依赖只装在 `edu` 环境内。
>
> 如果一定要在未激活环境的 shell 里跑，请用绝对路径：
> ```powershell
> D:\anaconda3\envs\edu\python.exe modules/skill_distiller/nuwa_distill.py ...
> ```

### 一次性配置

1. 安装 Claude Code CLI：
   ```powershell
   npm install -g @anthropic-ai/claude-code
   claude --version
   ```
2. 创建并激活 conda 环境，安装 Python 依赖：
   ```powershell
   conda create -n edu python=3.11
   conda activate edu
   pip install -r requirements.txt
   ```
3. 配置 `.env`（参考 `.env.example`）：
   ```
   DEEPSEEK_API_KEY=sk-...
   DEEPSEEK_BASE_URL=https://api.deepseek.com/anthropic
   DEEPSEEK_MODEL=deepseek-v4-pro[1m]
   ```

## 文件结构

```
modules/skill_distiller/
├── README.md             # 本文档
├── ISSUES.md             # review 问题清单
├── _common.py            # 公共基础设施 (env / options / runner)
├── nuwa_distill.py       # 主入口 + CLI
└── teaching_events.py    # ⚠️ 待迁出：归属 modules/agent_generator/
```

## 当前状态

- [x] 已完成调研
- [x] 已 vendor edunuwa-teacher-distiller 与 nuwa-skill 至 `.claude/skills/`
- [x] 已实现 `distill_teacher_skill()` 标准接口
- [x] 已支持双 Skill 切换
- [ ] 已准备样例输入（待模块二提供 `teacher_transcript.json`）
- [ ] 已生成样例输出
- [ ] 已接入主流程 (`run_demo_pipeline()`)

## 负责人

模块一（TeacherSkill 蒸馏与 Agent 核心逻辑）。

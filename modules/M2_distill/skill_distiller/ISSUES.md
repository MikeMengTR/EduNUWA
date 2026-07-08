# skill_distiller 模块问题清单

> 范围：`modules/skill_distiller/nuwa_distill.py`、`modules/skill_distiller/teaching_events.py`
> 用途：登记代码 review 中发现的问题，方便后续逐条讨论与统一修复。
> 模板：每条问题保留 **现状 / 风险 / 建议修改**，并在末尾留 `修改决定：` 字段供你勾选。

---

## 一、严重 / 安全问题

### [S1] API Key 硬编码进仓库

- **现状**：
  - `nuwa_distill.py:38` `api_key = "sk-****（已打码，泄露的 key 已作废）"`
  - `teaching_events.py:16` `os.environ["ANTHROPIC_AUTH_TOKEN"] = "sk-****（已打码）"`
- **风险**：
  - 一旦 push 到公开仓库即泄露，DeepSeek 余额可能被盗刷。
  - `nuwa_distill.py:31-35` 的注释还在劝"不要写死"，与代码自相矛盾。
- **建议修改**：
  - 改成 `api_key = os.getenv("DEEPSEEK_API_KEY")`，脚本启动前读取环境变量。
  - 在 DeepSeek 控制台 **revoke** 当前这把 key，重新生成。
  - 在 `.gitignore` 增加 `.env`，配合 `python-dotenv` 加载。
- **修改决定**：

---

## 二、重要功能性 Bug

### [B1] `teaching_events.py:29` 的 `os.chdir(workspace)` 污染全局 cwd

- **现状**：脚本启动时直接 `os.chdir`，把整个进程工作目录切到 `nvwatry/`。
- **风险**：
  - 后续若被 `web_demo` 或 `run_demo_pipeline()` 在同一进程里调用，再调用 TTS / 黑板模块会因为 cwd 改变而找不到相对路径。
  - 与 `nuwa_distill.py` 的做法不一致（那边只通过 `cwd=str(工作区)` 传给 SDK）。
- **建议修改**：
  - 删除 `os.chdir(workspace)`。
  - SDK 已经接收 `cwd=str(workspace)`，不需要改进程级 cwd。
- **修改决定**：

---

### [B2] `teaching_events.py` 没有显式构造 `env=`

- **现状**：直接 `os.environ[...] = "..."`，依赖 SDK 默认继承父进程环境。
- **风险**：
  - 与 `nuwa_distill.py` 显式 `env=代理环境变量` 的写法不一致。
  - 在某些托管/容器场景下父进程环境被隔离，会**静默退回到默认 ANTHROPIC 服务**，造成奇怪 401 / 计费。
- **建议修改**：
  - 仿照 `nuwa_distill.py` 的写法，构造一个完整 env dict 显式传给 `ClaudeAgentOptions(env=...)`。
- **修改决定**：

---

### [B3] `teaching_events.json` 的 schema 与 `docs/api_contract.md` 不一致

- **现状**：当前每个事件强制 `{step, speak, board, formula}` 四字段。
- **文档要求**：`docs/api_contract.md` 第 5 节定义事件为
  `{event_id, type, seq, text|action|content|latex|columns|rows|...}`
  且类型分 `speak / board / formula / table / pause / quiz`。
- **风险**：
  - **当前产物不能直接喂给 TTS 与黑板模块**，下游必须再做一层格式转换。
  - 与团队其他模块的对接出现"协议割裂"。
- **建议修改**（二选一）：
  1. 改 prompt，让模型直接生成符合 `api_contract.md` 的事件流。
  2. 保留当前"行格式"，再写一个 adapter 把每行展开为：1 个 speak + 1 个 board（+ 可选 1 个 formula）。
- **修改决定**：

---

### [B4] `extract_json` 在 dict 包装多层时只取一层

- **现状**：`teaching_events.py:129-133` 仅遍历 7 个常见 key 取一次。
- **风险**：模型若输出 `{"result": {"events": [...]}}`，会拿到 `{"events": [...]}` 仍是 dict，下面 `isinstance(data, list)` 校验失败抛错。
- **建议修改**：改成 while 循环，递归向下剥包装直到拿到 list 或剥到底。
- **修改决定**：

---

## 三、健壮性 / 工程问题

### [E1] 不符合 `api_contract.md` 第 7 节的函数接口约定

- **现状**：两个文件都是一次性 `__main__` 脚本，没有暴露可被 pipeline 调用的函数。
- **文档要求**：
  ```python
  distill_teacher_skill(transcript_path, output_dir, config) -> dict   # 返回 {"status": "success" | "error", ...}
  generate_teaching_events(question, teacher_skill_path, retrieved_context_path, output_dir, config) -> dict
  ```
- **风险**：`run_demo_pipeline()` 无法串联本模块；与模块二、模块三集成困难。
- **建议修改**：
  - 把核心逻辑包成 `distill_teacher_skill()` / `generate_teaching_events()`。
  - 原本的 `main()` 只调用这些函数，作为本地 demo 入口。
  - 函数返回统一字典：成功带文件路径，失败带 `status="error"` 与 `message`。
- **修改决定**：

---

### [E2] 第一轮"安装 Skill"应改为手动 vendor，**已部分落地**

- **现状（旧）**：`nuwa_distill.py` 每次启动都让 Agent 去 GitHub clone `alchaincyf/nuwa-skill` 并按 SKILL.md 安装说明搬文件。
- **风险**：
  - 国内访问 GitHub 不稳，常出现 clone 卡死 → 触发 1200s 超时；
  - 浪费 DeepSeek tokens（Agent 要花 ~80 turns 思考"怎么安装"）；
  - 每次都重新装，结果还可能因上游变动而不一致；
  - 完全离线 / 内网环境无法运行。
- **背景判断**：
  - `nuwa-skill` 是 MIT 协议、纯文本 + Python/Bash，无编译产物；
  - Claude Code Skill 是**文件级自动发现**：把 `SKILL.md` 放进 `.claude/skills/<name>/` 即可使用，不需要任何安装命令；
  - 官方 `npx skills add` 本质就是 `git clone + 文件复制`，可手动替代。
- **已完成的 vendor 操作**（2026-05-08）：
  - 在仓库根目录 vendor 了精简版 nuwa-skill：
    ```
    EduNUWA/.claude/skills/nuwa-skill/
    ├── SKILL.md                        # 来自上游 main 分支
    ├── LICENSE                         # MIT，保留版权声明
    └── scripts/
        ├── download_subtitles.sh
        ├── srt_to_transcript.py
        ├── merge_research.py
        └── quality_check.py
    ```
  - 砍掉了 `examples/` `assets/` `references/` 与多语言 README，总大小 ~64KB。
  - **注意**：上游 SKILL.md 的 frontmatter `name: huashu-nuwa`，Slash 触发词是 `/huashu-nuwa`（目录名 `nuwa-skill` 仅作文件系统标识）。在改写 `nuwa_distill.py` 时，提示词里的"nuwa-skill"建议改成"项目内已 vendor 的 huashu-nuwa Skill"，更利于 Agent 识别。
- **后续待做**：见下方 [E2-followup]（与 E1 / B3 配合一起改）。
- **修改决定**：vendor 已完成 ✅；nuwa_distill.py 改写待定。

---

### [E2-followup] 改写 `nuwa_distill.py`：删掉第一轮安装、对齐函数接口

> 与 [E2] 配套。vendor 已落地，下一步是让脚本不再装 Skill，而是直接调用项目内已存在的 Skill。

- **目标**：
  1. 移除整个"第一轮安装 Skill"的 query 流程（含 `安装提示词`、第一次 `await 运行代理任务(...)`、超时与异常分支里跟"安装"相关的提示）。
  2. 把第二轮"调用 Skill 蒸馏"封装为符合 `docs/api_contract.md` §7.2 的函数：
     ```python
     def distill_teacher_skill(
         transcript_path: str,
         output_dir: str,
         config: dict | None = None,
     ) -> dict:
         ...
         return {
             "status": "success",
             "skill_md": "<output_dir>/TeacherSkill.md",
             "skill_profile": "<output_dir>/skill_profile.json"  # 见 [E5]
         }
     ```
  3. 工作区改名 `nvwatry/` → `output/`（详见 [L3]），并且 cwd 必须包含 `.claude/skills/nuwa-skill/` 才能让 Skill 被发现：
     - 如果工作区在仓库内（默认情况），项目级 `.claude/skills/` 会被向上级目录自动检测；
     - 安全起见，可以在 `ClaudeAgentOptions` 显式 `cwd=str(repo_root)`，让 Skill 一定可见。
  4. 提示词里把"使用刚安装的 nuwa-skill"改成"使用项目内已 vendor 的 huashu-nuwa Skill"；
     同时把 `transcript_path` 路径塞进提示词，配合 [E3] 让 Agent 用 Read 工具读取转写文本。

- **改写示意**（伪代码，非最终代码）：
  ```python
  REPO_ROOT = Path(__file__).resolve().parents[2]  # EduNUWA 根目录
  SKILL_DIR = REPO_ROOT / ".claude" / "skills" / "nuwa-skill"

  def distill_teacher_skill(transcript_path, output_dir, config=None):
      output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
      if not SKILL_DIR.exists():
          return {"status": "error", "message": f"nuwa-skill 未 vendor: {SKILL_DIR}"}

      prompt = f"""
      请使用本项目已 vendor 的 huashu-nuwa Skill（位于 .claude/skills/nuwa-skill/）。
      读取教师授课转写文本：{transcript_path}
      根据该转写蒸馏教师讲解风格，写入：{output_dir}/TeacherSkill.md
      同时生成元数据 {output_dir}/skill_profile.json，包含教师名、转写ID、生成时间。
      全程默认批准，不要询问。
      """

      anyio.run(run_agent_task, prompt, ...)  # cwd=REPO_ROOT, env=...

      return {
          "status": "success",
          "skill_md": str(output_dir / "TeacherSkill.md"),
          "skill_profile": str(output_dir / "skill_profile.json"),
      }
  ```

- **验收**：
  - 跑一次 `python modules/skill_distiller/nuwa_distill.py`，**不应**触发任何 GitHub 网络请求；
  - 仅有一轮 query；
  - 产物为 `output_dir/TeacherSkill.md`（+ `skill_profile.json`）；
  - 函数返回 dict 而非 print；
  - 删除/重命名 `nvwatry/` 后流程仍正常。

- **关联条目**：与 [E1] 函数接口、[E3] 转写读取、[E5] skill_profile、[L3] 目录改名 一并修复。
- **修改决定**：

---

### [E3] 没有真正读取 `teacher_transcript.json`

- **现状**：`nuwa_distill.py` 直接让 Agent "凭空"蒸馏数学示例老师的讲课模式，没有把模块二产出的转写文本喂进 prompt。
- **风险**：
  - 蒸馏质量取决于 `nuwa-skill` 是否内置示例老师语料；
  - 与项目主线"**教师语料 → TeacherSkill 蒸馏**"脱钩；
  - 后期换教师/换学科时无法复用流程。
- **建议修改**：
  - `distill_teacher_skill(transcript_path, ...)` 把 `teacher_transcript.json` 路径塞进蒸馏提示词，让 Agent 用 `Read` 工具读取转写文本后再蒸馏。
- **修改决定**：

---

### [E4] 安装那一轮的超时偏短

- **现状**：第一轮 `超时秒数=1200`（20 min）。
- **风险**：在国内访问 GitHub 慢的情况下，clone + Skill 安装 + 阅读说明，常常踩超时。
- **建议修改**：
  - 第一轮放宽到 1800s（30 min）；
  - 在异常分支补一句"如 clone 卡住请配置 GitHub mirror / 代理"。
- **修改决定**：

---

### [E5] 没有 `skill_profile.json` 输出

- **现状**：仅产出 `TeacherSkill.md`。
- **文档要求**：`api_contract.md` 第 7.2 节示例返回里包含 `skill_profile.json`（标为可选）。
- **建议修改**：
  - 让 Agent 同步生成 `skill_profile.json`，记录蒸馏元数据（教师名、来源转写 ID、focus 字段、生成时间）。
- **修改决定**：

---

### [E6] `teaching_events.py` 缺少异常处理

- **现状**：直接 `async for message in query(...)`，未像 `nuwa_distill.py` 那样捕获 `CLINotFoundError / ProcessError / CLIJSONDecodeError / TimeoutError`。
- **风险**：SDK 任何错误都会原样抛栈给调用方，不利于 pipeline 集成。
- **建议修改**：复用 `nuwa_distill.py` 中的 `运行代理任务()` 异常分支，或抽成公共工具。
- **修改决定**：

---

## 四、小细节 / 可选改进

### [L1] `nuwa_distill.py:22` 的 `except NameError` 是 dead code

- **现状**：脚本模式下 `__file__` 一定有；只有 REPL/`exec` 才会缺。
- **建议修改**：删掉 try/except，直接 `当前目录 = Path(__file__).resolve().parent`。
- **修改决定**：

---

### [L2] 中文 / 英文标识符混用

- **现状**：`工作区`、`运行代理任务`、`打印消息`、`代理环境变量`、`打印_stderr` 等。
- **风险**：
  - 与 `teaching_events.py` 全英文风格分裂；
  - 跨模块协作时 IDE 跳转、grep 不便。
- **建议修改**：统一英文标识符（`workspace`、`run_agent_task`、`print_message` 等）。
- **修改决定**：

---

### [L3] 工作目录名 `nvwatry` 不直观

- **现状**：两个文件都用 `nvwatry/` 作为工作区。
- **建议修改**：改成 `workspace/` 或 `output/`，并在 README 中说明。
- **修改决定**：

---

### [L4] `extract_json` 末尾代码块兜底正则较窄

- **现状**：`re.sub(r"\s*```$", "", text)` 只能去掉**最末尾**的 ``` ` ``` 。
- **风险**：如果模型在 ```` ``` ```` 之后又追加了一段文字（例如"以上共 12 个事件"），第一段正则无法清理；不过有第三段 `raw_decode` 兜底，影响不大。
- **建议修改**：可选，把整段代码块用 `re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)` 取出来再走 `json.loads`。
- **修改决定**：

---

### [L5] 两个脚本都没有 logging，全部用 `print`

- **现状**：调试信息靠 `print(..., flush=True)`。
- **建议修改**：统一改成 `logging` 模块；与 `claude-debug.log` 形成两级日志（控制台简略、文件详细）。
- **修改决定**：

---

## 五、对照 `api_contract.md` 的差距速查

| 文档要求 | 当前实现 | 差距等级 | 关联条目 |
|---|---|---|---|
| `distill_teacher_skill(transcript_path, output_dir, config) -> dict` | 仅 `main()`，无函数 | 🟠 重要 | E1 |
| 输入 `teacher_transcript.json` | 未读取 | 🟠 重要 | E3 |
| 输出 `TeacherSkill.md` + `skill_profile.json` | 仅产 `TeacherSkill.md` | 🟡 可选 | E5 |
| `teaching_events.json` schema = `{event_id, type, seq, ...}` | 当前 `{step, speak, board, formula}` | 🔴 严重 | B3 |
| 返回 `{"status": "success", ...}` | 直接 print，无返回 | 🟠 重要 | E1 |

---

## 六、推荐处理顺序

1. **立刻**：~~S1（API Key 安全）~~ ✅ 完成 (2026-05-08)。
2. **vendor 阶段** ✅ 完成 (2026-05-08)：E2 把 nuwa-skill 文件搬入 `.claude/skills/nuwa-skill/`。
3. **本周内**：
   - ~~**E2-followup**（删除第一轮安装、改用 vendor 后的 Skill）~~ ✅ 完成 (2026-05-08) —— `nuwa_distill.py` 已重写为支持双 Skill 选择的标准函数接口。
   - ~~E1（封装 `distill_teacher_skill()` 函数）~~ ✅ 完成 (2026-05-08)。
   - ~~E3（让蒸馏真正读取转写文本）~~ ✅ 完成 (2026-05-08) —— `transcript_path` 已纳入函数签名 + prompt。
   - ~~E5（兜底产出 `skill_profile.json`）~~ ✅ 完成 (2026-05-08) —— Agent 未生成时由代码补一份最小版。
   - ~~E4（超时调优）~~ ✅ 完成 (2026-05-08) —— 删第一轮后默认 900s 即足。
   - **B3、B1、B2、B4、E6、L4** 等仅涉及 `teaching_events.py`（生成教学事件） —— 该文件应迁出至 `modules/agent_generator/`，待迁移时一并修复。
4. **小细节**：~~L1（dead code）~~ ✅ ~~L2（中英标识符）~~ ✅ ~~L3（目录改名）~~ ✅ —— `nuwa_distill.py` 重写已统一英文标识、移除 `nvwatry/` 工作目录、删除 dead code。L5（logging）保留为 P2。
5. ~~**未完成**：仅剩 `teaching_events.py` 相关条目（B1/B2/B3/B4/E6/L4）~~ ✅ **完成 (2026-05-08)** —— 文件已 git mv 至 `modules/agent_generator/teaching_events.py`，按 api_contract §5/§7.4 完全重写，35 项离线单元测试全过 + 端到端实跑成功（15 个事件，包含 speak/board/formula(0)/table/pause/quiz 多种类型）。详见 §十。

---

## 七、本批次实施记录（2026-05-08）

| 项目 | 内容 |
|---|---|
| 新增 | `modules/skill_distiller/_common.py` — env / options / runner 公共基础设施 |
| 新增 | `.claude/settings.json` — 项目级共享设置（信任两个 Skill） |
| 新增 | `.env.example` — 配置模板（已对齐 .env 实际变量） |
| 重写 | `modules/skill_distiller/nuwa_distill.py` — 双 Skill 选择 + 标准函数接口 + CLI |
| 更新 | `modules/skill_distiller/README.md` — 新接口与 CLI 用法 |
| 更新 | `.gitignore` — 追加 `.claude/settings.local.json` |
| 验证 | AST 解析通过；mock 依赖后冒烟测试 5 项全过（skill 注册表 / 目录存在 / CLI 解析 / 错误分支×2） |

**未触动**：`teaching_events.py`（应迁去 agent_generator，本批次不动）。

---

## 八、运行期问题清单（2026-05-08，首次实跑发现）

> 范围：在 Windows + DeepSeek 后端 + Claude Code CLI 环境下首次实跑 `distill_teacher_skill()` 后捕获的运行时问题。
> 跑的命令: `--skill nuwa-skill --transcript .../teacher_transcript_001.json`，耗时 354s，产物正常落盘。

### [W1] Windows 下 `python3` 不存在导致 Phase 4 质量自检失败

- **现状**：日志 `13:30:07` 处 Bash 工具失败 79 ms，`Shell command failed`。出现在主产物已经落盘之后，**最可能**是 Agent 想跑 `python3 quality_check.py SKILL.md`（源自 `nuwa-skill/SKILL.md` 第 268 行的写法）。
- **风险**：Phase 4 自动质量自检被静默跳过，Skill 输出未经过自动验证；`edunuwa-teacher-distiller` 后续若引入类似自检脚本，同样会踩坑。
- **新观察**（2026-05-08 默认 Skill 实跑）：edunuwa-teacher-distiller 跑时 Agent **主动选择了 PowerShell 而非 Bash**（debug.log 显示 `tool=PowerShell` 2 次），自然绕开了 `python3` 问题。原因是 Claude Code CLI 在 Windows 下识别到 PowerShell 可用，且我们 `.claude/settings.json` 允许的工具中含 `Bash(python *)` 而非 `Bash(python3 *)`。
- **建议修改**：
  1. 我们自有的 `edunuwa-teacher-distiller/SKILL.md` 一律使用 `python` 而不是 `python3` 调用脚本；
  2. 在 `_common.py` 的 prompt 注入区或 `make_options(extra_args=...)` 里加一条提示："Windows 下没有 `python3` 命令，统一使用 `python`"；
  3. 或在 `.claude/settings.json` 里提供 PATH 别名（这条可行性较低，可放弃）。
- **修改决定**：

---

### [W2] DeepSeek 后端不实现 Anthropic 遥测端点 → 27 条 403 噪声

- **现状**：日志中 27 条 `[ERROR] 1P/3P telemetry ... status=403`，因为我们走 `DEEPSEEK_BASE_URL=https://api.deepseek.com/anthropic`，DeepSeek 没有实现 `/v1/log` 之类的 telemetry 端点。
- **风险**：纯噪声，**无业务影响**；但日志看起来"满屏 ERROR"，对新手排错有误导性。
- **修复**（已实施 ✅, 2026-05-08）：在 `_common.py` `build_agent_env()` 中追加 4 项 env：
  ```python
  "OTEL_SDK_DISABLED": "true",
  "DISABLE_TELEMETRY": "1",
  "DISABLE_ERROR_REPORTING": "1",
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
  ```
- **修改决定**：✅ 已修复。

---

### [W3] Claude Code 启动时尝试 git clone marketplace，国内常超时

- **现状**：日志 `13:30:24` 处出现 `git clone https://github.com/anthropics/claude-plugins-official.git` 超时 120 s。这是 Claude Code CLI 启动时**自动**去更新 plugin marketplace 的行为。
- **风险**：
  - 国内网络访问 GitHub 不稳，每次启动都白等 2 分钟；
  - 即使后台异步，对系统资源也是浪费；
  - 队员若没装代理/未配 SSH key 会反复看到红色 WARN，误以为我们脚本有问题。
- **修复**（已实施 ✅, 2026-05-08）：在 `_common.py` `build_agent_env()` 中追加 `DISABLE_AUTOUPDATER=1`，关闭 Claude Code CLI 的自动更新行为（含 plugin marketplace 拉取）。
- **修改决定**：✅ 已修复。

---

### [W4] 长任务结束时日志被截断，缺少明确"finished"标记

- **现状**：日志最后一行 `13:30:41` 仍在 Stream API request，没有正常的 `[INFO] task finished` 类标记。这是 Python 端 `anyio.run()` 已退出（产物已落盘 → 主任务完成）但 SDK child 进程仍在做扫尾日志，被进程退出顺手 kill。
- **风险**：
  - 看日志难以判断 Skill 是"正常完成"还是"被中断"；
  - Phase 4 / Phase 5 的执行情况不明（是没跑还是跑了一半被砍）。
- **修复**（已实施 ✅, 2026-05-08）：在 `_common.run_agent_task()` 成功路径末尾显式 print `\n[run_agent_task] agent query loop finished cleanly`，便于事后日志检索。
- **修改决定**：✅ 已修复（核心标记）。

---

### [W5] Bash 工具 input 参数未在 debug.log 中体现

- **现状**：`claude-debug.log` 中 Bash 工具调用只记录 `tool_dispatch_start tool=Bash toolUseId=...`，**不记录实际命令文本**。出错时只能看到 `Shell command failed` 字样，无法定位到具体 binary 或参数。
- **风险**：[W1] 类问题难以快速定位（我们只能"推测" Agent 跑的是 `python3`）。
- **建议修改**：这是 Claude Code CLI 自身的 debug log 行为，无法直接改；但可以：
  1. 在 `make_options()` 添加 `extra_args["debug"] = "true"` 或 `"verbose"` 看是否能拿到更详细的输入；
  2. 或自己在 `_common.print_message()` 处处理 `ToolUseBlock` 时把 `block.name == "Bash"` 时的 `block.input` 显式 print 到我们自己的日志（已经有了，但用户运行时如果只看 debug.log 不看 stdout 会漏掉）；
  3. 让 README 提示"Agent 输出请同时看 stdout，不要只看 claude-debug.log"。
- **修改决定**：

---

### [W6] 转写文件长度 < 30 segments 时 nuwa 触发"冷启动协议"

- **现状**：当前 `data/transcripts/teacher_transcript_001.json` 仅 4 segments / 28.5 秒 / 120 字。`nuwa-skill` 自身识别为"信息源匮乏"，主动降级输出（标记 dimensions_weak、quality_rating: RED）。
- **风险**：测试样例不符合实际课时长度，无法反映两种 Skill 在**充足语料**下的真实差距；评审看到 "RED" 也容易质疑系统能力。
- **建议修改**：
  1. 等模块二（ASR）产出真实课时转写（≥3000 字 / ≥3 种教学场景）；
  2. 在 `edunuwa-teacher-distiller` 中也实现类似"冷启动协议"，避免语料不足时强行编造；
  3. 在 README 里加一节"语料长度建议"。
- **修改决定**：

---

### [W7] 女娲产出与 EduNUWA Output Contract 的 schema 适配差距（**预期内**）

- **现状**：女娲生成的 Output Contract 段以"自然语言使用建议"形式呈现（含 6 种事件类型），而非 EduNUWA `api_contract.md §5` 规定的 JSON schema 字段。
- **风险**：以 `--skill nuwa-skill` 产出的 TeacherSkill.md **不能直接被 `agent_generator` 模块消费**，下游必须做适配层。
- **建议修改**：这是设计预期——`edunuwa-teacher-distiller` 就是为了消除这层差距而存在的。运行 `--skill edunuwa-teacher-distiller`（默认）的产物就符合 schema。
- **结论**：W7 不是 bug，是**对照实验的设计差异**，可作为创新点叙事的论据之一。
- **修改决定**：仅文档化，不修改。

---

### [W9] Windows GBK 控制台 print emoji 触发 UnicodeEncodeError → **进程崩溃**

- **现状**：在 `--skill edunuwa-teacher-distiller` 跑时，Agent 输出含 emoji（如 💡 U+1F4A1、⚠️、📝）。`_common.print_message()` 直接 `print(...)`，但 Windows GBK 控制台无法编码这些字符，立即抛 `UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f4a1'`，整个 Python 进程崩溃。**主产物 TeacherSkill.md 完全没机会写**（Agent 还停留在 Read + Glob 阶段就被砍）。
- **风险**：🔴 **致命**——任何 Agent 输出含罕见 Unicode 时，所有自有 Skill 调用都会失败。`nuwa-skill` 上次能跑成功是侥幸（它的输出在前几个 turn 没有 emoji）。
- **复现**：
  ```
  File "_common.py", line 147, in print_message
      print(f"\n[other] {msg}\n", flush=True)
  UnicodeEncodeError: 'gbk' codec can't encode character '\U0001f4a1'
  ```
- **修复**（已实施 ✅, 2026-05-08）：
  1. `_common.py` 顶部加 stdout/stderr `reconfigure(encoding="utf-8", errors="replace")`，把 GBK 控制台切到 UTF-8；
  2. 新增 `_safe_print()` 兜底函数：捕获 UnicodeEncodeError 后用 errors="replace" 二次降级，确保**任何字符都不会再让进程崩**；
  3. `print_message()` 全部 `print(...)` 改为 `_safe_print(...)`。
- **验证**：手工跑 `_safe_print('test 💡 ⚠️ 中文')` 输出正常。
- **修改决定**：✅ 已修复。

---

### [W8] 后台 / CI 启动场景下 conda env 不会自动激活

- **现状**：用户自己在 `(edu)` PowerShell 中跑 `python ...nuwa_distill.py` 工作正常；但同一条命令通过后台 / Bash 工具（继承的不是 edu env）启动时，立即抛 `ModuleNotFoundError: No module named 'claude_agent_sdk'`。
- **风险**：
  - CI 集成 / cron / web_demo 后端启动时会踩坑；
  - 团队成员若没装 conda 或环境名不叫 `edu`，文档不写清就跑不起来。
- **修复**（已实施 ✅, 2026-05-08）：
  1. ✅ **`_common.py` 顶部 try/except ImportError**：检测到 `claude_agent_sdk` / `dotenv` / `anyio` 任一缺失，立即用友好提示替代裸栈，列出 3 种可能原因（未激活 conda env / 未装依赖 / Python 解释器选错）+ 可执行修复命令 + 绝对路径示例，然后 `sys.exit(2)`。
  2. ✅ **`README.md` 顶部加醒目警告框**：`> ⚠️ 重要：每次运行前必须先激活 conda 环境`，并给出 `conda activate edu` 与绝对路径两种方案。
  3. **可选（待做）**：在仓库根加一个 `run.ps1` 包装脚本，自动 `conda activate edu` 再调用 Python，规避手动激活。
- **验证**：`python modules/skill_distiller/nuwa_distill.py --help`（未激活 env）现在输出 11 行友好诊断信息，退出码 2。
- **修改决定**：✅ 已修复（核心两条）。

---

### [W-summary] 优先级速查

| 编号 | 严重度 | 是否影响产物 | 建议处理时机 |
|---|---|---|---|
| W1 (python3 vs python) | 🟠 中 | Phase 4 自检被跳过 | 写 edunuwa 自检脚本时一并解决 |
| W2 (telemetry 403) | 🟢 低 | 无 | ✅ 已修复 (`OTEL_SDK_DISABLED`+ 3 项 env) |
| W3 (marketplace clone 超时) | 🟡 中 | 浪费 wall time | ✅ 已修复 (`DISABLE_AUTOUPDATER=1`) |
| W4 (日志截断) | 🟢 低 | 无 | ✅ 已修复 (run_agent_task 末尾显式标记) |
| W5 (Bash 入参不可见) | 🟢 低 | 无 | 暂搁置 |
| W6 (语料不足) | 🟠 中 | 影响产物质量 | 等模块二真实数据 |
| W7 (女娲 vs 自有契约) | — | 设计预期 | 仅文档化 |
| W8 (conda env 隔离) | 🟠 中 | CI / 后台跑会失败 | ✅ 已修复 (启动检测 + README 醒目提示) |
| W9 (GBK 编码崩溃) | 🔴 致命 | 进程崩溃，主产物丢失 | ✅ 已修复 (`_safe_print` + reconfigure) |

---

## 九、双 Skill 对照实验记录（2026-05-08）

| 项 | Baseline (`huashu-nuwa`) | Default (`edunuwa-teacher-distiller`) |
|---|---|---|
| 命令行 | `--skill nuwa-skill` | `--skill edunuwa-teacher-distiller`（默认） |
| 运行时间 | 354s | **221s**（节约 38%） |
| 工具调用总数 | **56 次**（Glob×22, Read×16, TodoWrite×10, Write×4, Bash×4） | **16 次**（Read×8, Write×4, PowerShell×2, Glob×2） |
| 调用减少幅度 | — | **−71.4%** |
| TeacherSkill.md 字节 | 13322 | **6888**（精简 48%） |
| TeacherSkill.md 行数 | 230 | 123 |
| 段落数 | 9（多出"Honest Limits"+"调研来源"两段） | **严格 7 段**（按 api_contract §3） |
| Output Contract 形式 | 表格 + 自然语言"使用建议" | bullet list + 严格 schema 引用 + board action 白名单 |
| 是否可直接驱动下游 agent_generator | ❌ 需适配层 | ✅ 直接消费 |
| skill_profile 字节 | 2144（含 `nuwa_cold_start_triggered`, `quality_rating: RED` 等女娲特色字段） | 756（按 SKILL.md 规定字段：`dimensions_covered/dimensions_weak/evidence_count/segments_used`） |
| 风格特征 | 含"内在张力"、"认知设计原理"、"nuwa 方法论注解"等元描述 | 聚焦教学维度，工程化措辞 |

**结论**：在同一份转写（4 segments / 103 字 / 28.5s）上，自有 Skill **更快、更聚焦、更易被下游消费**；女娲产物**信息量更大、含方法论叙事**，适合作创新点演示对比。两份产物**互补**而非互相替代。

**首次实跑发现的问题 → 状态**：
- ✅ W9 (GBK 编码崩溃) — 已修复
- ✅ W2 (telemetry 403) — 已修复（4 项 env 静默）
- ✅ W3 (marketplace clone) — 已修复（DISABLE_AUTOUPDATER）
- ✅ W8 (conda env 隔离) — 已修复（友好启动检测 + README 醒目提示）
- ✅ W4 (日志截断) — 已修复（run_agent_task 末尾显式标记）
- ⚠️ W1 (python3 vs python) — 实测中 Agent 自选 PowerShell 绕开了；写 `edunuwa-teacher-distiller/SKILL.md` 时仍坚持用 `python` 防御
- ⚠️ W6 (语料严重不足) — 双方都已诚实标注；待真实 ASR 转写补足
- ⚠️ W7 (女娲 vs 自有契约差异) — 设计预期，作创新点叙事
- ⚠️ W5 (Bash 入参不可见) — 低优先级，留在收尾批次

---

## 十、teaching_events.py 迁移与重写记录（2026-05-08）

> 本批次解决 ISSUES §三的 B1/B2/B3/B4 + E6 + L4，并完成模块归属调整。

### 文件变更

| 操作 | 文件 |
|---|---|
| `git mv` | `modules/skill_distiller/teaching_events.py` → `modules/agent_generator/teaching_events.py` |
| 重写 | `modules/agent_generator/teaching_events.py`（432 行，从 0 重写） |
| 新增 | `modules/agent_generator/test_teaching_events.py`（35 项离线单元测试） |
| 更新 | `modules/agent_generator/README.md`（接口/CLI/测试/状态全套） |

### 核心修复对照

| 旧（`{step,speak,board,formula}` 平铺） | 新（api_contract §5 严格 schema） |
|---|---|
| 顶层是 array | 顶层是 object: `{event_file_id, question_id, language, events:[]}` |
| 4 字段固定 | 6 种事件类型 + 各自字段约束 |
| 教学内容硬编码"大学物理第一讲" | 从 `--question` + `retrieved_context.md` 取 |
| 仅读 TeacherSkill.md | 读 TeacherSkill + retrieved_context + question 三份 |
| `os.chdir(workspace)` 污染全局 cwd | 完全删除，由 `cwd=` 参数传 |
| `os.environ[...] = ...` 隐式继承 | 显式 `env=build_agent_env()`（复用 _common.py） |
| `extract_json` dict 包装只剥一层 | `unwrap_events()` while 循环递归剥离至 list |
| 仅 `__main__` 入口 | `generate_teaching_events(...)` 标准函数 + argparse CLI |
| 直接 print 中文 emoji | 复用 `_safe_print` 兜底 |
| 无异常处理 | 所有路径返回 `{status, ...}` dict，不抛栈 |
| 无校验 | 6 种事件类型逐项 schema 校验 + 至少 1 speak/1 board 强约束 |

### 测试结果

| 阶段 | 内容 | 结果 |
|---|---|---|
| 离线单元 | 35 项（JSON 提取×6、dict 包装剥离×7、6 种事件类型校验×16、demo_cases 兼容性×3、输入校验×3） | **35/35 ✓** |
| 端到端实跑 | `--question 什么是过拟合？` + 真实 TeacherSkill.md + retrieved_context.md | **success, 15 events, exit 0** |
| 二次独立校验 | 用 `unwrap_events + validate_events` 重新校验产物 | **ALL CHECKS PASSED ✓** |

### 实跑产物事件分布（teaching_events_e2e_test_001.json）

```
speak    : 5      board     : 5      table   : 1
pause    : 3      quiz      : 1      formula : 0
```

事件流叙事正确：问题引入 → 揭露直觉谬误 → 概念定义 → 黑板对比表 → 解决方案 → 课堂提问 → 阶段总结。
所有 board action 均在白名单（write_subtitle / write_title / write_bullets / write_summary）。

### 关联条目状态

| 编号 | 原状 | 现状 |
|---|---|---|
| B1 | os.chdir 污染 cwd | ✅ 已删 |
| B2 | env 不显式 | ✅ 显式 `env=build_agent_env()` |
| B3 | schema 不对齐 api_contract | ✅ 完全对齐 §5 + §7.4 |
| B4 | dict 包装只剥一层 | ✅ while 递归剥至 list |
| E6 | 缺异常处理 | ✅ 复用 `run_agent_task` 完整异常分支 |
| L4 | 末尾 ``` 正则窄 | ✅ 改为 `re.search(...)` 双向匹配 |
| 模块归属 | 错放在 skill_distiller | ✅ 已迁至 agent_generator |

---

## 十一、充足语料端到端验证（2026-05-14）

> 用一份覆盖 6 大教学场景的 ~8 分钟样例转写，完整跑通 transcript → TeacherSkill → teaching_events，验证 W6 在有充足语料时整条链路的真实质量。

### 数据准备

构造 `data/transcripts/teacher_transcript_002.json`（示例老师讲解过拟合的 8 分钟课堂样例）：
- 37 segments / 2142 字 / 487.5 秒
- 覆盖：问题引入 / 直觉类比 / 形式定义 / 公式推导 / 例题 / 易错点 / 解决方案 / 课堂提问 / 总结

### 升级对比 (v1 → v2)

| 指标 | v1 (4 segments) | v2 (37 segments) | 改善 |
|---|---|---|---|
| 转写字数 | 120 | 2142 | **17.85×** |
| TeacherSkill 体积 (自有) | 6888 B | 16631 B | 2.4× |
| **弱维度数 (自有)** | **2** | **0** | **全 8 维度覆盖** |
| 证据数 (自有) | 8 | 48 | 6× |
| TeacherSkill 体积 (女娲) | 13322 B | 23146 B | 1.7× |
| 事件总数 | 15 | 18 | — |
| **事件类型覆盖** | **5** (缺 formula) | **6** (全类型) | speak/board/formula/table/pause/quiz |
| board action 多样性 | 4 种 | 6 种 | write_title/bullets/steps/highlight/summary |

### 最终交付物（agent 输出文件）

**核心交付**: `data/events/teaching_events_v2_final.json`
- 8.4 KB，18 个事件
- 顶层契约: `event_file_id` / `question_id` / `language` / `events`
- 类型分布: speak×7, board×6, pause×2, formula×1, table×1, quiz×1
- formula 用 LaTeX 数学符号（`\mathcal{L}_{train} \searrow`）
- table 三状态对比（欠拟合/过拟合/理想）
- quiz 含完整 options + answer
- 叙事完整：问题驱动 → 直觉类比 → 形式定义 → 公式信号 → 误区纠正 → 五板斧解决方案 → 对比表 → 课堂测验 → 总结
- **校验**: `validate_events()` 18/18 全过 ✓

### W6 状态更新

W6（语料严重不足）原标记"待真实 ASR"，本次用充足模拟样例验证：
- ✅ **链路本身完全工作**，质量瓶颈只在转写数据
- ✅ **edunuwa 在充足语料下 8 维度全覆盖**（v1 缺 analogy/formula，v2 全有）
- ⏳ 真实 ASR 转写就绪后直接换 `--transcript` 路径即可，无需改代码

---

> 修改时建议每条单独提交，commit message 引用条目编号（如 `fix(skill_distiller): [W2] silence DeepSeek-side telemetry 403 noise`）。

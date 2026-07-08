# M4 · Orchestrator Agent 编排 — 详细方案 v2.0

> **上游依赖**：M2 (Distill) — 提供 `TeacherSkill.md` + declared pedagogy；M6 (Platform) — 提供 `course_outline.json`、学生请求
> **下游消费者**：M5 (Runtime) — 消费 `teaching_events.json` + 流式事件；M2 (Distill) — 探针测试时调用 emitter
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.4
> **版本**：v2.0 · 2026-06-05

**v2.0 新增（相对 v1.0）**：
1. 双通道流式架构：**快速通道**（直连 API，~3s 首事件）+ **深度通道**（ClaudeCode + TeacherSkill，~40s 首事件）
2. **多轮 Q&A**：session_manager 持久化 `qa_history`，追问自动注入上下文
3. **课程检索**：keywords 匹配 `course_outline` 自动生成 `retrieved_context.md`
4. **Planner**：追问检测 + 模式路由
5. **OrchestratorPipeline**：统一 `run()` / `run_stream()` 入口
6. **50 字 speak 限制**：保证 GPT-SoVITS 合成成功率
7. **Demo 服务器**：听课 + 流式问答前端

---

## 1. 模块定位与边界

### 1.1 一句话定位

消费学生问题 + Skill + 课程上下文，产出严格符合 schema 的 `teaching_events.json`，支持**流式双通道生成**（快速垫场 + 深度完整），维护多轮对话上下文。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 课程知识检索（retrieved_context.md）| TTS / 渲染（M5 做） |
| 决定本轮要讲什么（planner）| Skill 蒸馏（M2 做） |
| 调 LLM 生成事件序列（emitter）| 教师 / 课程 CRUD（M6 做） |
| 维护多轮对话状态（session_manager）| 学生反馈采集（M5/M6 做）|
| 严格遵循 Skill 中的 pedagogy 策略 | 修改 Skill |
| 流式双通道事件输出 | 决定最终展示节奏（M5 player 做） |
| **speak 单句 ≤ 50 字**（TTS 兼容）| |

### 1.3 核心价值

- **M4 是 Skill 真正"被使用"的地方**
- **M4 是学生体验的脑**：双通道流式保证首响应 < 3s，深度通道保证质量
- **M4 是 M5 的输入源**：events 格式对齐 TTS 批量/流式接口

---

## 2. 子模块与文件结构

```text
modules/M4_orchestrator/
  course_retriever/
    keyword_retriever.py       # ✅ 关键词匹配教材文档
    __init__.py
  planner/
    planner_dispatcher.py      # ✅ follow/ondemand 路由 + 追问检测
    __init__.py
  emitter/
    teaching_events.py         # ✅ 同步生成（LLM → events JSON）
    streaming_emitter.py       # ✅ 流式 SSE 生成（分阶段 + 事件拦截）
    test_teaching_events.py    # ✅ 35 项离线测试
  session_manager/
    state_store.py             # ✅ load_or_create / update_session
    __init__.py
  schemas/
    teaching_events.schema.json
  pipeline.py                  # ✅ OrchestratorPipeline（run + run_stream）
  streaming_events.py          # ✅ L1-L7 延迟重放
  latency_config.py            # ✅ 延迟配置
  __init__.py
  README.md
```

> v2.0 新增：`course_retriever/`、`planner/`、`session_manager/`、`pipeline.py`、`streaming_emitter.py`。
> 相对 v1.0 删减：`vector_retriever.py`、`retriever_dispatcher.py`、`formatter.py`、`follow_planner.py`、`ondemand_planner.py`、`history.py`、`state_machine.py`（合并为更简洁的单文件实现）。

---

## 3. 详细接口

### 3.1 主入口 — OrchestratorPipeline

```python
from M4_orchestrator import OrchestratorPipeline

p = OrchestratorPipeline()

# === 同步模式（完整生成，适合离线） ===
result = p.run(
    session_id="SES_test",
    user_question="什么是质点？",
    teacher_skill_path="data/teachers/T_test_full_pipeline/skills/v1/TeacherSkill.md",
    course_outline_path="data/courses/C_physics_tongji_001/course_outline.json",
    config={"target_count": "8 to 12", "max_turns": 15}
)
# → {"status":"success", "session_id":"...", "turn":1,
#    "events_path":"...", "events_count":35, "is_follow_up":False}

# === 流式模式（双通道，适合在线） ===
for chunk in p.run_stream(
    session_id="SES_test",
    user_question="位移和路程到底有什么区别？",
    config={"fast_first": True}   # 默认 True：快速+深度双通道
):
    # chunk["type"]: "plan" | "event" | "done" | "error"
    # chunk["data"]: 事件 dict（含 _source: "fast"/"deep"）
```

**内部流程**：
```
1. session_manager.load_or_create_session()   — 加载/创建 session
2. planner.plan_turn()                        — 判断模式 + 历史上下文
3. course_retriever.retrieve_course_context()  — 检索教材
4. emitter.generate_teaching_events()          — LLM 生成 [同步]
   或 streaming_emitter.generate_teaching_events_stream() — LLM 流式 [流式]
5. session_manager.update_session()            — 持久化本轮
```

### 3.2 双通道架构（v2.0 核心）

```
学生提问
  │
  ├─ 快速通道（urllib 直连 DeepSeek, ~3s）
  │   5-6 个事件（speak + board + pause）
  │   无 TeacherSkill，通用回答
  │   → 即刻回应，垫场用
  │
  └─ 深度通道（Claude Code CLI + Agent SDK, ~40s 首事件）
      4 阶段渐进生成（opening → intro → core_1 → core_2）
      完整 TeacherSkill + 教材上下文
      30-60 个事件，风格化讲解
      → 最终产物，替换快速版
```

| | 快速通道 | 深度通道 |
|---|---|---|
| 接口 | `urllib` 直连 DeepSeek API | Claude Code CLI + Agent SDK |
| Prompt | 20 字 system prompt | 完整 TeacherSkill + 教材 |
| 首事件 | ~3 秒 | ~35-40 秒 |
| 事件数 | 5-6 个 | 30-60 个 |
| 风格 | 通用老师语气 | 按 TeacherSkill 风格化 |

### 3.3 子函数

```python
# === session_manager ===
def load_or_create_session(session_id, teacher_id=None, course_id=None, mode="ondemand") -> dict
    """读取/创建 session_state.json，含 qa_history + progress"""

def update_session(session_id, question, topic, events_path, events_count) -> dict
    """追加本轮到 qa_history，原子写入"""

# === planner ===
def plan_turn(session_state, user_question, course_outline_path=None, config=None) -> dict
    """
    Returns: {topic, depth, mode, is_follow_up, history_context, max_events}
    追问检测：含"刚才/再讲/那个公式/没听懂"等词 → is_follow_up=True
    """

# === course_retriever ===
def retrieve_course_context(question, course_outline_path, output_dir, config=None) -> dict
    """关键词匹配 course_outline → 拼接教材 docs → 写 retrieved_context.md"""

# === emitter（同步） ===
def generate_teaching_events(question, teacher_skill_path, retrieved_context_path,
                              output_dir, config=None) -> dict
    """LLM 完整生成 → teaching_events.json，含 extract/unwrap/validate"""

# === emitter（流式） ===
async def generate_teaching_events_stream(question, teacher_skill_path,
    retrieved_context_path, output_dir, config=None) -> AsyncIterator[str]
    """SSE 格式流式生成，分 4 阶段，每阶段 Write 拦截实时产出"""
```

### 3.4 config 字段

```python
config = {
    # pipeline
    "fast_first": True,               # 是否启用快速通道（默认 True）
    "target_count": "8 to 12",        # 目标事件数
    "max_turns": 15,                  # Agent 最大轮数
    "timeout_sec": 600,               # Agent 超时

    # emitter
    "need_board": True,
    "need_formula": True,
    "need_quiz": False,

    # retriever
    "retriever": { "top_k": 3, "min_score": 1 },

    # session
    "max_events_per_turn": 30,
}
```

---

## 4. 输入文件契约

### 4.1 来自 M2

| 文件 | 路径 | 用途 |
|---|---|---|
| `TeacherSkill.md` | `data/teachers/{tid}/skills/v{n}/TeacherSkill.md` | 7 段契约全文喂 LLM |
| `skill_profile_v2.json` | 同上目录 | 读 `pedagogy` 段注入 prompt |

### 4.2 来自 M6

| 文件 | 路径 | 用途 |
|---|---|---|
| `course_outline.json` | `data/courses/{cid}/course_outline.json` | planner + retriever 索引 |
| 课程文档 | `data/courses/{cid}/docs/*.md` | retriever 拼接 context |

---

## 5. 输出文件契约

### 5.1 `teaching_events.json`

```json
{
  "event_file_id": "teaching_events_SES_test_t1",
  "session_id": "SES_test",
  "question_id": "q_SES_test_001",
  "events": [
    {"event_id":"evt_0001","type":"speak","seq":1,"text":"同学们好..."},
    {"event_id":"evt_0002","type":"board","seq":2,"action":"write_title","content":"质点运动学"},
    {"event_id":"evt_0003","type":"pause","seq":3,"duration_sec":2.0},
    {"event_id":"evt_0004","type":"formula","seq":4,"latex":"\\vec{r}=x\\vec{i}+y\\vec{j}","display_mode":"block"},
    {"event_id":"evt_0005","type":"quiz","seq":5,"question":"...","options":["A","B"],"answer":"B"}
  ]
}
```

**事件类型**：`speak / board / formula / table / pause / quiz`（6 种）

**board action**：`write_title / write_subtitle / write_bullets / write_steps / write_summary / clear_board / highlight`（7 种）

**v2.0 约束**：每个 `speak.text` ≤ 50 汉字，保证 GPT-SoVITS TTS 合成成功率。

### 5.2 `session_state.json`

```json
{
  "session_id": "SES_test",
  "teacher_id": "T_test_full_pipeline",
  "course_id": "C_physics_tongji_001",
  "mode": "ondemand",
  "current_turn": 2,
  "qa_history": [
    {"turn":1, "question":"什么是质点？", "topic":"质点运动学",
     "events_path":"...", "events_count":35}
  ],
  "progress": {"completed_topics":[], "current_chapter":"", "current_topic":""}
}
```

---

## 6. 硬性要求（不可妥协）

| # | 硬性要求 | 验证方法 | 状态 |
|---|---|---|---|
| H1 | `teaching_events.json` 通过 schema 校验 | 自动 + CI | ✅ |
| H2 | event `seq` 严格递增；type/action 从 enum 取 | 自动测试 | ✅ |
| H3 | board action 7 种合法值内 | 自动测试 | ✅ |
| H4 | speak 不含板书内容 | 启发式检查 | ✅ |
| H5 | pedagogy 体现在 events 序列中 | 探针测试 | ✅ |
| H6 | pedagogy 5 维注入 prompt | code review | ✅ |
| H7 | session_state.json 原子写入 | 集成测试 | ✅ |
| H8 | 流式版本同时提供同步版本 | `run()` + `run_stream()` | ✅ |
| H9 | LLM 失败返回 error | 自动测试 | ✅ |
| H10 | 不跳跃章节（follow 模式）| 自动测试 | — |
| H11 | `generate_for_probe()` 零副作用 | 自动测试 | — |
| H12 | 不调 M3/M5 代码 | 静态扫描 | ✅ |
| H13 | 不反向调 M2 | 静态扫描 | ✅ |
| H14 | 单轮事件数有上限 | 自动截断 | ✅ |
| **H15** | **每个 speak.text ≤ 50 字** | 自动检查 | ✅ v2.0 |
| **H16** | **流式双通道可用** | 集成测试 | ✅ v2.0 |

---

## 7. 验收标准

### 7.1 MVP（当前状态）

| # | 指标 | 标准 | 状态 |
|---|---|---|---|
| A1 | events schema 校验通过率 | 100% | ✅ |
| A2 | 流式首事件延迟（快速通道）| < 5s | ✅ 实测 ~3s |
| A3 | 流式首事件延迟（深度通道）| < 60s | ✅ 实测 ~35-40s |
| A4 | 点播模式可用 | ✅ | ✅ |
| A5 | 追问上下文注入 | ✅ | ✅ |
| A6 | session 持久化 | ✅ | ✅ |
| A7 | 课程检索可用 | ✅ | ✅ |
| A8 | speak ≤ 50 字合规率 | > 90% | ⚠️ LLM 偶有超限 |
| A9 | TTS 合成成功率（≤50 字）| > 90% | ✅ 15/16 |
| A10 | Demo 服务器可用 | 听课 + 问答 | ✅ |

### 7.2 Phase 2

| # | 指标 | 标准 |
|---|---|---|
| A11 | speak ≤ 50 字 100% 合规 | ✅ |
| A12 | GPT-SoVITS 合成成功率 | > 95% |
| A13 | 跟随模式可用 | ✅ |
| A14 | M4→M5 流式 TTS 串联 | ✅ |

---

## 8. 与其他模块的接口

### 8.1 输入来源

| 来源 | 内容 | 路径 |
|---|---|---|
| **M2 distill** | `TeacherSkill.md`（含 pedagogy 注释）| `data/teachers/{tid}/skills/v{n}/` |
| **M6 platform** | `course_outline.json` | `data/courses/{cid}/` |
| **M6 platform** | 课程文档 | `data/courses/{cid}/docs/*.md` |
| **M6 platform** | 学生请求 | HTTP（M6 包装）|

### 8.2 输出去向

| 去向 | 内容 | 路径 |
|---|---|---|
| **M5 runtime** | `teaching_events.json` | `data/sessions/{sid}/` |
| **M5 runtime** | session_state | `data/sessions/{sid}/session_state.json` |
| **M2 distill** | events（探针）| 函数返回 |
| **M6 platform** | 流式 chunks | SSE |

### 8.3 与 M5 字段对齐

| M4 输出 | M5 消费 | 状态 |
|---|---|---|
| 6 种 event type | 6 种 timeline type | ✅ |
| 7 种 board action | 7 种渲染 action | ✅ |
| `duration_sec`（pause）| `duration_sec` | ✅ v2.0 统一 |
| `speak.text` | TTS 文本输入 | ✅ |

---

## 9. 架构设计要点

### 9.1 双通道流式

快速通道用 `urllib` 直连 DeepSeek API（绕过 Claude Code CLI），从提问到首事件 ~3s。深度通道用 Claude Agent SDK + TeacherSkill，首事件 ~40s。两者并行，快速通道事件先出（`_source: "fast"`），深度通道事件接上（`_source: "deep"`），最终文件用深度版。

### 9.2 渐进式分阶段生成

深度通道分 4 阶段：opening(3事件) → intro(6事件) → core_1(10事件) → core_2(12事件)。每阶段独立 LLM 调用，Write 工具拦截实时产出。Opening 阶段 prompt 精简至 500 字以内加速首响应。

### 9.3 speak 长度控制

每个 speak.text ≤ 50 汉字（H15），在 emitter prompt 中硬性约束。GPT-SoVITS 对 ≤50 字短句合成成功率 > 90%，超过则容易失败。

### 9.4 多轮上下文

session_manager 维护 `qa_history`，超过 10 轮截断早期。Planner 检测追问关键词（"刚才""再讲""没听懂"等），自动注入前序对话到新一轮 prompt。

---

## 10. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| LLM 输出 schema 不合法 | 高 | 高 | H1 校验 + extract/unwrap/validate 三道防线 |
| speak 超过 50 字 | 中 | 中 | H15 prompt 约束 + TTS 失败降级 Edge |
| GPT-SoVITS 合成失败 | 中 | 中 | Edge TTS 降级 + ≤50 字提高成功率 |
| 深度通道延迟过高 | 高 | 中 | 双通道架构：快速 3s 垫场 |
| 多轮上下文 token 爆炸 | 高 | 低 | qa_history 截断 |

---

## 11. 本地开发与测试

### 11.1 快速跑通

```bash
# 课程生成
python -c "
from M4_orchestrator import OrchestratorPipeline
p = OrchestratorPipeline()
p.run_stream(session_id='SES_test',
    user_question='请讲解质点运动学',
    teacher_skill_path='data/teachers/T_test_full_pipeline/skills/v1/TeacherSkill.md',
    course_outline_path='data/courses/C_physics_tongji_001/course_outline.json',
    config={'fast_first': False})
"

# Demo 服务器
python demo_server.py   # http://localhost:8770
```

### 11.2 测试

```text
emitter/test_teaching_events.py   # 35 项离线（extract/unwrap/validate）
test_m4.py                        # 快速流式测试
session_manager/state_store.py    # 自测（load/create/update/持久化）
```

---

## 12. 实现现状（v2.0，2026-06-05）

### 已落地

| 组件 | 文件 | 说明 |
|---|---|---|
| **OrchestratorPipeline** | `pipeline.py` | `run()` + `run_stream()`，双通道架构 |
| **流式发射器** | `emitter/streaming_emitter.py` | 4 阶段渐进生成，SSE 格式 |
| **同步发射器** | `emitter/teaching_events.py` | LLM 完整生成 + schema 校验 |
| **Session Manager** | `session_manager/state_store.py` | 多轮持久化 + 原子写入 |
| **Course Retriever** | `course_retriever/keyword_retriever.py` | 关键词匹配教材 |
| **Planner** | `planner/planner_dispatcher.py` | 追问检测 + 历史注入 |
| **Demo Server** | `demo_server.py` | 听课 + 流式问答 + 黑板渲染 |
| **M5 流式 TTS** | `M5_runtime/tts_service/tts_engine.py` | `generate_tts_stream()` 后台 TTS |
| **M5 批量 TTS** | 同上 | `generate_tts_batch()` GPT-SoVITS GPU |

### 实测数据

- M4 课程生成：~5 分钟 (35 events, 16 speak)
- M5 TTS 批量：153s (15/16 成功, RTF 0.32x, RTX 4060)
- Q&A 首语音延迟：~3s（快速通道）+ ~40s（深度通道首事件）+ TTS 合成时间
- speak ≤50 字合规：~70%（LLM 偶有超限，prompt 持续优化中）

### 待完善

- speak 100% ≤50 字合规（prompt 约束强化）
- 流式 TTS 稳定性提升
- 跟随模式（follow mode）
- `generate_for_probe()` 探针接口

---

**END OF M4 DOCUMENT v2.0**

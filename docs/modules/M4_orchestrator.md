# M4 · Orchestrator Agent 编排 — 详细方案

> **上游依赖**：M2 (Distill) — 提供 `TeacherSkill.md` + declared pedagogy；M6 (Platform) — 提供 `course_outline.json`、学生请求
> **下游消费者**：M5 (Runtime) — 消费 `teaching_events.json`；M2 (Distill) — 探针测试时调用 emitter
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.4
> **版本**：v1.0 · 2026-05-15

---

## 1. 模块定位与边界

### 1.1 一句话定位

消费学生问题 + Skill + 课程上下文，产出严格符合 schema 的 `teaching_events.json`，支持**跟随式**和**点播式**两种学习模式，并维护多轮对话上下文。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 课程知识检索（retrieved_context.md）| TTS / 渲染（M5 做） |
| 决定本轮要讲什么（planner）| Skill 蒸馏（M2 做） |
| 调 LLM 生成事件序列（emitter）| 教师 / 课程 CRUD（M6 做） |
| 维护多轮对话状态（session_manager）| 学生反馈采集（M5/M6 做）|
| 严格遵循 Skill 中的 pedagogy 策略 | 修改 Skill |
| 跟随式：跟踪课程进度 | 推荐教师（M3 做） |
| 点播式：随时插入提问 | 评测自身的 Skill 是否好（M2 做）|
| 流式 events 输出（Phase 1+）| 决定最终展示节奏（M5 player 做） |

### 1.3 核心价值

- **M4 是 Skill 真正"被使用"的地方**：再好的 Skill 如果在 M4 没被正确执行，就是空文档
- **M4 是学生体验的脑**：模式切换、上下文、连贯性全在这里

---

## 2. 子模块拆分与文件结构

```text
modules/M4_orchestrator/
  course_retriever/             # 现有，扩展
    keyword_retriever.py
    vector_retriever.py         # Phase 2
    retriever_dispatcher.py
    formatter.py                # → retrieved_context.md
  planner/                      # 新增
    follow_planner.py           # 跟随式：基于 course_outline 推进
    ondemand_planner.py         # 点播式：直接以问题为 topic
    planner_dispatcher.py
  emitter/                      # 现有 agent_generator 重组
    teaching_events.py          # 现有：generate_teaching_events()
    schema_validator.py         # 现有：events JSON schema 校验
    pedagogy_injector.py        # 新：把 declared pedagogy 注入 prompt
    prompts/
      emitter_v2.py
  session_manager/              # 新增
    state_store.py              # session_state.json 读写
    history.py                  # qa_history 维护
    state_machine.py            # follow/ondemand 切换
  schemas/
    teaching_events.schema.json # 已有 schema 移到此
    session_state.schema.json   # 新增
  README.md
  run.py                        # 本地测试入口
  tests/
    test_planner.py
    test_emitter.py
    test_session.py
    test_schema.py
    fixtures/
```

---

## 3. 详细接口

### 3.1 主函数

```python
def generate_teaching_events_v2(
    session_id: str,
    user_question: str,
    teacher_skill_path: str,
    mode: Literal["follow", "ondemand"],
    course_outline_path: str | None = None,
    output_dir: str | None = None,
    config: dict | None = None,
) -> dict:
    """
    主入口（同步版本）。
    
    Args:
        session_id: 已存在或新创建的 session ID
        user_question: 学生本轮提问
        teacher_skill_path: data/teachers/{tid}/skills/v{n}/TeacherSkill.md
        mode: follow（跟随式）/ ondemand（点播式）
        course_outline_path: follow 模式必填
        output_dir: 默认 data/sessions/{session_id}/
        config: 见 §3.5
    
    内部流程:
        1. session_manager.load_or_create(session_id)
        2. planner.plan(state, user_question, mode, outline)
        3. course_retriever.retrieve(plan.topic)
        4. emitter.generate(question, skill, context, plan, pedagogy)
        5. session_manager.update(session_id, plan, events)
    """
```

**返回**：

```json
{
  "status": "success",
  "session_id": "SES_20260515103200_a3f",
  "turn": 3,
  "events_path": "data/sessions/SES_.../events/turn_3.json",
  "session_state_path": "data/sessions/SES_.../session_state.json",
  "events_count": 12,
  "plan": {
    "topic": "过拟合",
    "depth": "intro",
    "must_cover": ["定义", "类比", "误区"]
  }
}
```

### 3.2 流式接口

```python
def generate_teaching_events_v2_stream(
    session_id: str,
    user_question: str,
    teacher_skill_path: str,
    mode: Literal["follow", "ondemand"],
    course_outline_path: str | None = None,
    output_dir: str | None = None,
    config: dict | None = None,
) -> Iterator[dict]:
    """
    流式逐 event yield。
    
    Yields:
        {"event_type": "plan", "data": {...}}              # 计划阶段
        {"event_type": "context", "data": {...}}           # 检索完成
        {"event_type": "event_chunk", "data": {evt}}       # 单个 event
        {"event_type": "done", "data": {"total": 12}}
        {"event_type": "error", "data": {"code":..., "msg":...}}
    """
```

**HTTP SSE 包装**（M6 实现）：

```
GET /api/v1/sessions/{session_id}/turns/stream
event: plan
data: {...}

event: event_chunk
data: {...}

event: done
data: {...}
```

### 3.3 子函数

```python
# course_retriever
def retrieve_course_context(
    question: str,
    course_id: str,
    output_dir: str,
    config: dict | None = None,
) -> dict:
    """与现有 retrieve_course_context() 一致，输出 retrieved_context.md"""

# planner
def plan_turn(
    state: SessionState,
    user_question: str,
    mode: str,
    course_outline_path: str | None = None,
) -> dict:
    """
    Returns:
      {
        "topic": "过拟合",
        "subtopic": "定义",
        "depth": "intro",        # intro / deep / review
        "must_cover": [...],
        "skip": [...],            # 已学过的可以跳过
        "max_events": 30
      }
    """

# emitter（现有 generate_teaching_events 升级）
def generate_events(
    user_question: str,
    teacher_skill_path: str,
    retrieved_context_path: str,
    plan: dict,
    pedagogy: dict,                 # 从 skill_profile_v2 读
    config: dict | None = None,
) -> dict:
    """生成 teaching_events.json，schema 校验"""

# session_manager
def load_or_create_session(session_id: str, ...) -> SessionState
def update_session(session_id: str, plan: dict, events_path: str) -> None
```

### 3.4 探针测试入口（给 M2 调用）

```python
# emitter/teaching_events.py
def generate_for_probe(
    probe_question: str,
    teacher_skill_path: str,
    config: dict | None = None,
) -> dict:
    """
    探针测试专用：极简 context + 单轮，无 session。
    
    M2 evaluate_skill() 通过依赖注入调用此函数。
    """
```

### 3.5 config 字段

```python
config = {
    "llm": {
        "provider": "deepseek",        # deepseek / claude
        "model": "deepseek-chat",
        "temperature": 0.3,
        "max_tokens": 4000,
    },
    "retriever": {
        "method": "keyword",           # keyword / vector
        "top_k": 3,
    },
    "planner": {
        "max_events_per_turn": 30,
        "follow_strict": True,         # follow 模式是否严格按 outline
    },
    "emitter": {
        "need_quiz": False,
        "need_formula": True,
        "honor_pedagogy_strict": True, # H6
    },
    "session": {
        "max_history_turns": 10,       # 超过的早期 turn 摘要化
    },
    "stream": False,
}
```

---

## 4. 输入文件契约

### 4.1 来自 M2

#### `TeacherSkill.md`

读取 7 段内容 + `<!-- pedagogy:declared ... -->` 注释块。

**M4 必须使用**：
- 全文（喂给 LLM）
- pedagogy 字段（解析后注入 emitter prompt）

**M4 不允许修改 Skill 文件**。

#### `skill_profile_v2.json`

只读 `pedagogy` 段（用于 `pedagogy_injector`）；其他字段 M4 不使用。

### 4.2 来自 M6

#### `course_outline.json`

```json
{
  "course_id": "C_math_001",
  "title": "机器学习入门",
  "chapters": [
    {
      "chapter_id": "ch_01",
      "title": "过拟合与泛化",
      "topics": [
        {
          "topic_id": "t_01",
          "title": "什么是过拟合",
          "doc_refs": ["topic_001.md"],
          "depends_on": []
        }
      ]
    }
  ]
}
```

**M4 必须使用**：`chapters` / `topics` / `doc_refs` / `depends_on`

### 4.3 来自 M6 上游课程文档

`data/courses/{course_id}/docs/*.md` — course_retriever 读取。

### 4.4 与 M2 / M6 的契约一致性自检

| 检查点 | 状态 |
|---|---|
| ✅ TeacherSkill.md 路径 `data/teachers/{tid}/skills/v{n}/TeacherSkill.md` | 与 M2 §5 一致 |
| ✅ pedagogy 注释块格式 `<!-- pedagogy:declared ... -->` | 与 M2 §5.1 一致 |
| ✅ pedagogy enum 取值与 M2 §6.2 一致 | 字段逐项核对 |
| ✅ course_outline.json schema 与总体方案 §5.5 一致 | 字段逐项核对 |
| ✅ course_id 命名 `C_<subject>_<seq>` | 一致 |
| ✅ session_id 命名 `SES_<YYYYMMDDHHMMSS>_<rand>` | 一致 |

---

## 5. 输出文件契约

### 5.1 `teaching_events.json`

**严格遵循** `docs/api_contract.md §5`。

**v2 新增字段**：

```json
{
  "event_file_id": "teaching_events_SES_..._t3",
  "session_id": "SES_20260515103200_a3f",
  "turn": 3,
  "question_id": "q_003",
  "question": "什么是过拟合？",
  "topic": "过拟合",
  "generated_by": "emitter_v2",
  "skill_id": "S_T20260515001_v2",
  "events": [...]
}
```

**事件类型**（不变）：`speak / board / formula / table / pause / quiz`
**board action**（不变）：`write_title / write_subtitle / write_bullets / write_steps / write_summary / clear_board / highlight`

### 5.2 `session_state.json`

按总体方案 §5.5 schema。**M4 必须**：
- 原子写入（tmp + rename）
- 每轮 update 后立刻 flush
- `qa_history` 超过 `max_history_turns` 时把早期 turn 摘要为单条

### 5.3 `retrieved_context.md`

按 `api_contract.md §4` schema。无变化。

### 5.4 输出文件目录

```text
data/sessions/{session_id}/
  session_state.json
  events/
    turn_1.json
    turn_2.json
    ...
  context/
    turn_1.md
    turn_2.md
    ...
```

---

## 6. 硬性要求（不可妥协）

| # | 硬性要求 | 验证方法 |
|---|---|---|
| H1 | `teaching_events.json` 必须通过 `schemas/teaching_events.schema.json` 校验 | 自动 + CI |
| H2 | event 中 `seq` 必须从 1 开始严格递增；type/action 必须从 enum 取 | 自动测试 |
| H3 | board action 必须在 7 种合法值内，未声明的 action 直接拒绝 | 自动测试 |
| H4 | `speak` 事件文本中**不允许嵌入板书内容**（应拆为独立 board event）| 启发式检查（含 ":" "①②" 等模式时 warning）|
| H5 | `pedagogy.concept_entry.primary` 必须真的体现在 events 序列中（如 problem-driven → 第一个 event 是提问 speak）| 探针测试验证 |
| H6 | `honor_pedagogy_strict=True` 时，pedagogy 5 维全部要在 prompt 中显式约束 | code review prompt |
| H7 | session_state.json 写入必须**原子**（tmp + rename），禁止并发损坏 | 集成测试 |
| H8 | 流式版本必须同时提供同步版本，便于调试 | 接口完整性 |
| H9 | LLM 失败时返回 `status="error"` + 上一轮 events（如有）的 fallback 引用，不让前端拿到空白 | 自动测试 |
| H10 | 跟随式模式必须基于 course_outline 推进；不允许跳跃章节（除非学生明确请求）| 自动测试 |
| H11 | 探针测试入口 `generate_for_probe()` 不写 session_state；调用零副作用 | 自动测试 |
| H12 | 不允许调用 M3/M5 代码 | 静态扫描 |
| H13 | 不允许反向调用 M2（除被注入到 M2 评测时）| 静态扫描 |
| H14 | 单轮事件数有上限（`max_events_per_turn`）防止 LLM 失控 | 自动截断 + warning |

---

## 7. 验收标准

### 7.1 MVP（Phase 1 结束时）

| # | 指标 | 标准 | 测试方法 |
|---|---|---|---|
| A1 | events schema 校验通过率 | 100% | CI |
| A2 | 单次生成延时 p95 | < 30s | 性能测试 |
| A3 | 点播模式可用 | ✅ | 集成测试 |
| A4 | session_state 多轮持久化 | ✅ | 集成测试 |
| A5 | events 中 pedagogy 落地率（observed == declared）| > 70% | M2 探针验证 |
| A6 | LLM 失败时 fallback 不让前端崩溃 | ✅ | 故障注入测试 |
| A7 | 探针接口可被 M2 调用 | ✅ | 集成测试 |

### 7.2 Phase 1 → Phase 2

| # | 指标 | 标准 |
|---|---|---|
| A2 | 生成延时 p95 | < 15s |
| A5 | pedagogy 落地率 | > 85% |
| A8 | 跟随模式可用 | ✅ |
| A9 | 多轮上下文连贯性（人评 1-5）| ≥ 4.0 |
| A10 | 流式 SSE 输出 | ✅ |

### 7.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A2 | 生成延时 p95 | < 8s |
| A5 | pedagogy 落地率 | > 95% |
| A11 | 跨 session 跨教师推荐"复习"功能 | ✅ |

---

## 8. 与其他模块的接口

### 8.1 输入来源

| 来源 | 内容 | 协议 | 路径 |
|---|---|---|---|
| **M2 distill** | `TeacherSkill.md`（含 pedagogy 注释块）| 文件读取 | `data/teachers/{tid}/skills/v{n}/TeacherSkill.md` |
| **M2 distill** | `skill_profile_v2.json` 的 pedagogy 段 | 文件读取 | 同上目录 |
| **M6 platform** | `course_outline.json` | 文件读取 | `data/courses/{cid}/course_outline.json` |
| **M6 platform** | 课程文档 | 文件读取 | `data/courses/{cid}/docs/*.md` |
| **M6 platform** | 学生请求触发 | HTTP（M6 包装）| — |

### 8.2 输出去向

| 去向 | 内容 | 协议 | 路径 |
|---|---|---|---|
| **M5 runtime** | `teaching_events.json` | 文件读取 | `data/sessions/{sid}/events/turn_{n}.json` |
| **M5 runtime** | session_state（用于 player 显示进度）| 文件读取 | `data/sessions/{sid}/session_state.json` |
| **M2 distill** | events（探针测试结果）| 函数返回 | 不持久化 |
| **M6 platform** | 流式 chunks | SSE | — |

### 8.3 接口契约一致性自检

| 检查点 | 状态 |
|---|---|
| ✅ teaching_events.json schema 与 `api_contract.md §5` 一致 | 字段核对 |
| ✅ board action 7 种枚举与 M5 渲染器期望一致 | 与 M5 同步 |
| ✅ pedagogy 字段从 M2 注释块解析；enum 与 M2 enums.py 一致 | 字段核对 |
| ✅ session_state.json schema 与总体方案 §5.5 一致 | 字段核对 |
| ✅ session_id 命名 | 与总体方案 §5.2 一致 |
| ✅ 不调用 M3/M5 代码 | 静态扫描 |
| ✅ 探针接口不引入循环依赖 | 静态扫描 |

---

## 9. 关键技术挑战与实现指导

### 9.1 pedagogy 注入 prompt（H6 核心）

```python
def build_pedagogy_constraints(pedagogy: dict) -> str:
    """把 5 维 pedagogy 转换为 LLM 可遵循的硬约束文本"""
    lines = []
    
    if pedagogy["concept_entry"]["primary"] == "problem-driven":
        lines.append("- 第一个事件必须是 speak 类型，且文本是一个引发思考的问题")
    elif pedagogy["concept_entry"]["primary"] == "definition-first":
        lines.append("- 第一个事件应是 board write_title + speak 给出定义")
    
    if pedagogy["analogy_density"]["level"] == "high":
        lines.append(f"- 每个新概念必须配 ≥ {pedagogy['analogy_density']['per_concept']} 个类比 speak 事件")
    
    if pedagogy["misconception_alert"]["mode"] == "proactive-explicit":
        lines.append("- 在定义之后必须主动插入误区提醒 speak 事件，含'注意'/'常见错误'等词")
    
    # ... 其他维度
    return "\n".join(lines)
```

把生成的约束文本插入 emitter prompt 的 SYSTEM 部分。

### 9.2 模式切换状态机

```python
# state_machine.py
def transition(state: SessionState, user_question: str, requested_mode: str) -> str:
    """
    决定本轮实际采用 follow 还是 ondemand。
    
    规则:
      - state.mode 是默认值
      - 学生提问含"我想问下..."→ 临时切 ondemand 单轮
      - ondemand 后下一轮自动回到 follow（如果 state.mode == follow）
    """
```

### 9.3 多轮上下文压缩

session 超过 10 轮后，把早期 turn 压缩为摘要：

```python
def compress_history(history: list[dict], keep_last: int = 5) -> list[dict]:
    if len(history) <= keep_last:
        return history
    
    early = history[:-keep_last]
    summary = llm_summarize(early)
    return [{"turn": "summary", "summary": summary}] + history[-keep_last:]
```

### 9.4 Event 数量上限（H14）

```python
def generate_events(...):
    raw = llm_call(...)
    events = parse(raw)
    
    if len(events) > config["max_events_per_turn"]:
        events = events[:config["max_events_per_turn"]]
        warnings.append("events_truncated")
```

### 9.5 流式 vs 同步统一实现

```python
def _generate_internal(...) -> Iterator[dict]:
    """单一内部实现，yield 中间状态"""
    yield {"event_type": "plan", ...}
    ...

def generate_teaching_events_v2(...) -> dict:
    """同步包装"""
    result = {"events": [], "plan": None}
    for chunk in _generate_internal(...):
        if chunk["event_type"] == "plan":
            result["plan"] = chunk["data"]
        elif chunk["event_type"] == "event_chunk":
            result["events"].append(chunk["data"])
    return {"status": "success", **result}

def generate_teaching_events_v2_stream(...) -> Iterator[dict]:
    return _generate_internal(...)
```

→ 满足 H8。

---

## 10. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| LLM 输出 schema 不合法 | 高 | 高 | H1 严格校验 + 自动重试（最多 3 次）+ 降级到模板 |
| pedagogy 字面写在 prompt 但 LLM 不遵守 | 高 | 高 | H5 + H6 + few-shot 强示范；M2 探针测试持续监督 |
| course_outline 与实际课程文档不一致 | 中 | 高 | retriever 找不到 doc 时报 warning，不阻塞 |
| 多轮上下文积累后 token 爆炸 | 高 | 中 | §9.3 压缩 |
| 流式与同步两份代码漂移 | 中 | 高 | §9.5 单一内部实现 |
| 探针测试反向调用 M2 形成循环 | 中 | 高 | H11 + H13 静态扫描 |
| 生成中断后 session_state 损坏 | 中 | 中 | H7 原子写 |

---

## 11. 本地开发与测试

### 11.1 快速跑通

```bash
python modules/M4_orchestrator/run.py \
  --session-id SES_test_001 \
  --question "什么是过拟合？" \
  --skill data/teachers/T_legacy_001/skills/v2/TeacherSkill.md \
  --mode ondemand \
  --output data/sessions/SES_test_001/
```

### 11.2 必须提供的测试

```text
tests/
  test_planner.py             # follow / ondemand 切换
  test_emitter.py             # H1 schema 校验
  test_pedagogy_injection.py  # H6
  test_session.py             # H7 原子写 + 多轮
  test_stream.py              # H8 流式 == 同步
  test_probe_entry.py         # H11 零副作用
  test_no_circular_dep.py     # H13
  fixtures/
    skill_v2.md               # 含 pedagogy 注释块
    outline_demo.json
    expected_events.json
```

### 11.3 CI 检查项

- teaching_events schema 校验
- pedagogy 注入 prompt 含所有 5 维约束（grep 检查）
- 静态扫描 import 不含 M3/M5

---

## 12. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | 现有 `modules/agent_generator/teaching_events.py` 移到 `modules/M4_orchestrator/emitter/` | 路径调整，import 不报错 |
| 2 | 现有 `modules/course_retriever/` 移到 `modules/M4_orchestrator/course_retriever/` | 同上 |
| 3 | 实现 `pedagogy_injector` 把 5 维约束注入现有 prompt | 探针测试体现 pedagogy |
| 4 | 实现 `session_manager` 框架（先支持单轮）| M5 能拿到 events 文件 |
| 5 | 实现 `generate_for_probe()` 提供给 M2 | M2 evaluate_skill 能跑 |
| 6 | 与 M2 owner 对齐 pedagogy 注释块解析协议 | 双方文档互引 |
| 7 | 与 M5 owner 对齐 events schema（特别是 board action） | 双方文档互引 |

---

**END OF M4 DOCUMENT**

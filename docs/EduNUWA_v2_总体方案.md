# EduNUWA v2 · 总体方案

> **文档定位**：本文是 EduNUWA 项目 v2 阶段的**总体方案**和**接口/文件规范**的单一真相源（single source of truth）。
>
> 范围：
> - 产品定位与系统架构
> - 6 个子模块的目标摘要
> - 跨模块的接口调用规范
> - 跨模块的文件传输规范
> - 双层指标体系定义
> - 阶段路线图
>
> 不在本文范围（将由各模块负责人撰写独立子文档）：
> - 各模块内部的实现细节、文件结构、单元测试方案
> - 各模块的详细验收清单与里程碑表
>
> 版本：v2.0  ·  生成日期：2026-05-15

---

## 1. 产品定位

### 1.1 一句话定位

把教师的"教学能力"从依附于个体的隐性经验，转化为**可沉淀、可量化、可被双轨发现、可复用**的数字资产；以 APP 的形式承载教师端的"能力资产化"和学生端的"风格化学习"。

### 1.2 核心价值主张

| 角色 | 价值 |
|---|---|
| **教师** | 一次上传，长期分发；教学风格被结构化保存，形成可被 AI 反复调用的个人 SKILL；保留真实姓名 + 像素化 IP 形象 |
| **学生** | 双轨发现教师（按名字 / 按风格指标），在数字人黑板课堂中以两种模式学习（跟随式 / 点播式） |
| **平台** | 同时承载名师效应和长尾发现；通过双层指标体系实现教学风格的精准匹配 |

### 1.3 与 v1 的核心区别

| 维度 | v1 | v2 |
|---|---|---|
| 教师数量 | 单 demo case（示例老师 1 人）| 多租户教师库 |
| Skill 评价 | 定性覆盖标签 `dimensions_covered` | 双层指标体系（指纹 + 教学法 + 质量分）|
| 学习模式 | 一次问答 → 一次播放 | 跟随式 + 点播式 + 多轮上下文 |
| 教师形象 | 无 | 像素 IP + 真实姓名 |
| 系统形态 | Pipeline 脚本 | 教师端 + 学生端 APP |

---

## 2. 系统架构

### 2.1 6 模块全景

```text
M1 Ingest         教师素材摄取（视频/音频/PDF → transcript）
M2 Distill        风格蒸馏 + 指标量化（transcript → Skill + profile）
M3 Catalog        教师目录 + 双轨匹配（profile → 推荐结果）
M4 Orchestrator   Agent 编排（学生问题 + Skill → events）
M5 Runtime        学习运行时（events → 数字人 + 黑板渲染）
M6 Platform       APP 外壳（账号、上传、播放、API 网关、计费）
```

### 2.2 数据流全景

```text
[教师端]                                                [学生端]
  │                                                       │
  │ 上传素材                                              │ 双轨发现
  ▼                                                       ▼
┌──────────┐  transcript  ┌──────────┐  profile  ┌──────────────┐
│ M1 摄取  │─────────────▶│ M2 蒸馏  │──────────▶│ M3 目录/匹配 │
└──────────┘              └──────────┘           └──────┬───────┘
                                                        │
                                                        │ 选定教师 + 课程
                                                        ▼
                                                ┌──────────────────┐
                                                │ M4 Agent 编排    │
                                                └────────┬─────────┘
                                                         │ teaching_events.json
                                                         ▼
                                                ┌──────────────────┐
                                                │ M5 学习运行时    │
                                                └────────┬─────────┘
                                                         │ 学生反馈
                                                         └─▶ 回流至 M2 / M3

┌──────────────────────────────────────────────────────────────────┐
│                M6 Platform（账号、API 网关、UI、文件存储）        │
│                  横跨所有模块，提供统一外壳                        │
└──────────────────────────────────────────────────────────────────┘
```

### 2.3 模块职责边界

| 模块 | 做 | 不做 |
|---|---|---|
| **M1** | ASR、文本清洗、入库到 teacher 私有目录 | 风格分析、Skill 蒸馏 |
| **M2** | 蒸馏 Skill、第一层指纹评分、第二层教学法推理、Skill 质量评测 | 教学事件生成、教师 CRUD |
| **M3** | 教师列表、双轨筛选、推荐排序 | 教师 CRUD（M6 写入，M3 只读）|
| **M4** | 课程检索、规划、生成 events、维护 session 状态 | TTS、渲染 |
| **M5** | TTS、口型同步、黑板渲染、播放控制、Live2D | events 生成、avatar 资产生产 |
| **M6** | 账号、API 网关、UI、文件存储、计费 | 业务逻辑（在 M1-M5 中）|

---

## 3. 模块目标摘要

> 注：本节只给出**高层目标**和**核心 IO**。详细实现指导、文件结构、验收清单将在每个模块的独立子文档中展开。

### 3.1 M1 · Ingest 教师素材摄取

**目标**：把教师上传的视频 / 音频 / 讲义自动处理成结构化语料。
**核心输入**：原始上传文件路径（视频 / 音频 / PDF）
**核心输出**：`teacher_transcript.json` + 原始音频片段（用于后续 TTS 训练）
**对外提供**：`ingest_teacher_material()`

### 3.2 M2 · Distill 风格蒸馏 + 指标

**目标**：把 transcript 蒸馏成 `TeacherSkill.md` + `skill_profile_v2.json`，并通过探针测试给 Skill 打 grade。
**核心输入**：teacher_id + transcript 列表
**核心输出**：`TeacherSkill.md` + `skill_profile_v2.json` + `eval_report.json`
**对外提供**：`distill_teacher_skill_v2()` / `extract_fingerprint()` / `infer_pedagogy()` / `evaluate_skill()`

### 3.3 M3 · Catalog 教师目录 + 双轨匹配

**目标**：让学生能"人找人"和"风格找人"两条路径发现教师。
**核心输入**：所有教师的 `skill_profile_v2.json` + `teacher_card.json`
**核心输出**：教师列表、详情、筛选、推荐结果（HTTP API）
**对外提供**：HTTP API（`/api/teachers/*`）

### 3.4 M4 · Orchestrator Agent 编排

**目标**：消费学生问题 + Skill + 课程上下文，产出 `teaching_events.json`，支持跟随式和点播式两种模式。
**核心输入**：session_id + 学生问题 + teacher_skill_path + mode（follow/ondemand）
**核心输出**：`teaching_events.json` + `session_state.json`
**对外提供**：`generate_teaching_events_v2()`

### 3.5 M5 · Runtime 学习运行时

**目标**：把 `teaching_events.json` 在前端真实地"演出来"——数字人讲话 + 黑板渲染。
**核心输入**：`teaching_events.json` + voice_id + avatar_id
**核心输出**：`audio_manifest.json` + `playback_data.json` + 前端渲染效果
**对外提供**：后端 `generate_tts_batch()` / `build_playback_data()`；前端 `PlayerRuntime` API

### 3.6 M6 · Platform APP 外壳

**目标**：把所有模块缝合成一个真正的产品（账号、上传、播放、API 网关）。
**核心输入**：用户请求（HTTP / WebSocket）
**核心输出**：教师端 APP + 学生端 APP + 后端 REST API
**对外提供**：HTTP API 网关、文件存储服务、认证服务

---

## 4. 接口调用规范

### 4.1 调用方式总原则

EduNUWA 系统内部存在两类接口调用：

1. **模块间内部调用**：使用 **Python 函数 + 文件路径传递**（沿用 v1 已有规范）
2. **APP 与后端的外部调用**：使用 **HTTP REST API + JSON**（M6 提供）

**核心原则**：
- 模块之间不通过内存传递大对象；通过文件路径解耦
- HTTP API 由 M6 在 Python 函数外层封装，**业务逻辑必须在 Python 函数中实现**，HTTP 层只做转发 + 鉴权 + 限流

### 4.2 Python 函数接口规范

#### 4.2.1 函数签名约定

每个模块对外暴露的主函数必须遵循以下签名形式：

```python
def 模块主函数名(
    必填业务参数: 类型,                    # 通常是 id 或文件路径
    output_dir: str,                       # 必填：输出目录
    config: dict | None = None,            # 可选：模块配置
) -> dict
```

**示例**：

```python
distill_teacher_skill_v2(
    teacher_id: str,
    transcript_paths: list[str],
    output_dir: str,
    config: dict | None = None,
) -> dict
```

#### 4.2.2 返回值约定

所有主函数统一返回 `dict`，必须包含 `status` 字段。

**成功返回**：

```json
{
  "status": "success",
  "<主要输出字段>": "<输出文件路径>",
  "<其他统计信息>": "..."
}
```

**失败返回**：

```json
{
  "status": "error",
  "message": "<可读错误原因>",
  "<相关输入字段>": "..."
}
```

**部分成功**（用于探针测试等多结果场景）：

```json
{
  "status": "partial",
  "message": "<说明>",
  "succeeded": [...],
  "failed": [...]
}
```

#### 4.2.3 配置传递约定

所有可选参数通过 `config` dict 传入，不放进函数签名：

```python
# 推荐
generate_teaching_events_v2(
    session_id="s_001",
    user_question="...",
    teacher_skill_path="...",
    mode="ondemand",
    output_dir="...",
    config={
        "model": "deepseek",
        "max_events": 30,
        "stream": False,
    }
)

# 不推荐：把可选参数全部放进签名
```

#### 4.2.4 异常处理约定

- 模块内部可以抛异常
- 主函数必须捕获常见异常并转换为 `status="error"` 返回
- 系统级异常（OOM、磁盘满）允许穿透抛出
- 所有错误信息必须**可读**，不能直接返回 stack trace

### 4.3 HTTP API 接口规范

由 M6 提供。所有 API 遵循以下规范：

#### 4.3.1 路径规范

```
/api/v1/<resource>/<action>
```

- 所有 API 加 `/api/v1/` 前缀，预留版本演进空间
- 资源名复数（`/api/v1/teachers`）
- 动作名优先用 HTTP method（GET / POST / PUT / DELETE）
- 复杂查询用 `POST /api/v1/<resource>/search`，body 传查询条件

#### 4.3.2 请求/响应格式

**请求**：JSON body（`Content-Type: application/json`），文件上传用 `multipart/form-data`

**响应**：

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

**错误响应**：

```json
{
  "code": 4001,
  "message": "teacher_id not found",
  "data": null
}
```

#### 4.3.3 状态码约定

| HTTP 状态码 | 业务 code 区段 | 含义 |
|---|---|---|
| 200 | 0 | 成功 |
| 400 | 4000-4999 | 请求参数错误 |
| 401 | 4010 | 未认证 |
| 403 | 4030 | 无权限 |
| 404 | 4040 | 资源不存在 |
| 500 | 5000-5999 | 服务器内部错误 |
| 503 | 5030 | 下游服务不可用 |

#### 4.3.4 异步任务规范

长时间任务（如上传 → ASR → 蒸馏全流程）必须异步：

```
POST /api/v1/uploads          → 返回 task_id
GET  /api/v1/tasks/{task_id}  → 查询进度
                                返回 { status, progress, result }
```

**status 取值**：`pending` / `running` / `success` / `failed` / `cancelled`
**progress 取值**：0.0–1.0

### 4.4 流式接口规范

适用于 events 生成、TTS 流式输出等场景：

- **协议**：Server-Sent Events (SSE)，路径 `/api/v1/<resource>/stream`
- **事件格式**：

```
event: event_chunk
data: {"seq": 1, "type": "speak", "text": "..."}

event: done
data: {"total": 12}

event: error
data: {"code": 5000, "message": "..."}
```

- 所有流式接口必须同时提供同步版本，便于调试

---

## 5. 文件传输规范

### 5.1 多租户目录结构

所有运行时数据按 teacher / course / session 三种维度切分，**不再使用全局单实例目录**。

```text
data/
  teachers/
    {teacher_id}/                      # 多租户根
      teacher_card.json                # 教师档案（真实姓名、avatar、tags）
      avatar/
        pixel.png                      # 像素形象
        live2d/                        # Live2D 模型资源
      transcripts/
        {transcript_id}.json           # ASR 转写结果
      audio_samples/
        {sample_id}.wav                # 原始音频片段（TTS 训练用）
      skills/
        v{n}/
          TeacherSkill.md
          skill_profile_v2.json
          eval_report.json
        latest -> v{n}                 # 软链接（或在 teacher_card 中指向）
      uploads/
        {upload_id}/                   # 原始上传文件（视频/PDF）
  courses/
    {course_id}/
      course_outline.json              # 章节结构
      docs/
        {doc_id}.md                    # 课程知识资料
  sessions/
    {session_id}/
      session_state.json               # 多轮上下文
      events/
        turn_{n}.json                  # 每轮 teaching_events
      audio/
        turn_{n}/
          audio_manifest.json
          {evt_id}.wav
      playback_data.json               # 前端播放数据
      feedback.json                    # 学生反馈
  eval_probes/
    P01_concept_explain.json
    P02_formula_derive.json
    ...
```

### 5.2 ID 命名规范

| 实体 | 格式 | 示例 |
|---|---|---|
| teacher_id | `T_<YYYYMMDD>_<seq>` | `T_20260515_001` |
| **teacher_id_compact** | teacher_id 去掉所有下划线 | `T20260515001` |
| course_id | `C_<subject>_<seq>` | `C_math_001` |
| skill_id | `S_<teacher_id_compact>_v<n>` | `S_T20260515001_v2` |
| session_id | `SES_<YYYYMMDDHHMMSS>_<rand>` | `SES_20260515103200_a3f` |
| transcript_id | `TR_<teacher_id_compact>_<seq>` | `TR_T20260515001_001` |
| upload_id | `UP_<YYYYMMDDHHMMSS>_<rand>` | `UP_20260515103200_a3f` |
| event_id | `evt_<seq:04d>` | `evt_0001` |
| task_id | `TASK_<UUID4>` | `TASK_xxx-xxx-xxx-xxx` |

**统一规则**：
- 字母开头，避免纯数字
- 不含空格、中文、特殊字符
- 时间戳用 UTC（避免跨时区歧义）
- 可读 + 可排序
- **下划线分隔规则**：所有 ID 用 `_` 作为字段分隔符。需要把 teacher_id 拼到其他 ID 中时（如 skill_id / transcript_id），必须先用 `teacher_id_compact`（去掉内部下划线），避免 `_` 作为分隔符与 teacher_id 内部 `_` 混淆造成解析歧义
- 反向解析：从 skill_id 拿 teacher_id 时，先去掉 `S_` 前缀和 `_v<n>` 后缀得到 `teacher_id_compact`；如需还原带下划线的 teacher_id，需查 db 索引（teacher_id ↔ teacher_id_compact 的映射由 M6 维护）

### 5.3 跨模块数据契约清单

| # | 文件 | 生产者 | 消费者 | 状态 | schema 文档 |
|---|---|---|---|---|---|
| 1 | `teacher_transcript.json` | M1 | M2 | 已有 | `api_contract.md §2` |
| 2 | `TeacherSkill.md` | M2 | M4 | 已有 | `api_contract.md §3` |
| 3 | `skill_profile_v2.json` | M2 | M3, M4 | 新增 | 见 §6.4 |
| 4 | `teacher_card.json` | M6 | M3 | 新增 | 见 §5.5 |
| 5 | `course_outline.json` | M6 / 教师 | M4 | 新增 | 见 §5.5 |
| 6 | `retrieved_context.md` | M4 (retriever) | M4 (emitter) | 已有 | `api_contract.md §4` |
| 7 | `session_state.json` | M4 | M4, M5 | 新增 | 见 §5.5 |
| 8 | `teaching_events.json` | M4 | M5 | 已有 | `api_contract.md §5` |
| 9 | `audio_manifest.json` | M5 (tts) | M5 (player) | 已有 | `api_contract.md §6` |
| 10 | `playback_data.json` | M5 | 前端 | 已有 | `api_contract.md §7.6` |
| 11 | `eval_report.json` | M2 (qa) | M3 | 新增 | 见 §5.5 |
| 12 | `feedback.json` | M5 | M2, M3 | 新增 | 见 §5.5 |

> 说明：原有文件的 schema 沿用 `api_contract.md`；新增文件的 schema 在本文件 §5.5 给出**入口结构**，具体字段在各模块的子文档中细化。

### 5.4 文件传递的 4 条铁律

1. **路径优先**：跨模块函数调用必须传文件路径，禁止传大段文本
2. **绝对路径**：所有路径在配置中以**项目根目录的相对路径**记录，运行时拼接为绝对路径
3. **原子写入**：先写临时文件 `xxx.tmp`，写完 rename 为 `xxx.json`，避免并发损坏
4. **不可变输出**：所有产物文件**只生成不修改**；需要更新时新建版本（如 `skills/v3/`）

### 5.5 新增文件的入口 schema

#### `teacher_card.json`

```json
{
  "teacher_id": "T_20260515_001",
  "real_name": "示例老师",
  "display_name": "示例老师",
  "subject": ["高等数学", "线性代数"],
  "bio": "...",
  "avatar": {
    "pixel_url": "...",
    "live2d_model_id": "..."
  },
  "voice_id": "...",
  "current_skill_version": 2,
  "tags": ["warmth:high", "english_term:always"],
  "created_at": "...",
  "stats": {
    "total_sessions": 0,
    "avg_rating": null
  }
}
```

#### `skill_profile_v2.json`

完整结构见本文件 §6.4。

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
        { "topic_id": "t_01", "title": "什么是过拟合", "doc_refs": ["topic_001.md"] }
      ]
    }
  ]
}
```

#### `session_state.json`

```json
{
  "session_id": "SES_20260515103200_a3f",
  "student_id": "U_xxx",
  "teacher_id": "T_20260515_001",
  "course_id": "C_math_001",
  "mode": "follow",
  "course_progress": {
    "current_chapter_id": "ch_01",
    "current_topic_id": "t_01",
    "covered_topic_ids": []
  },
  "qa_history": [
    {
      "turn": 1,
      "question": "什么是过拟合？",
      "events_path": "data/sessions/SES_.../events/turn_1.json",
      "timestamp": "..."
    }
  ],
  "started_at": "...",
  "updated_at": "..."
}
```

#### `eval_report.json`

```json
{
  "skill_id": "S_T20260515001_v2",
  "evaluated_at": "...",
  "probe_set": "default_v1",
  "probe_results": [
    { "probe_id": "P01", "events_path": "...", "observed_pedagogy": {...} }
  ],
  "consistency": {
    "declared_observed": 0.85,
    "cross_probe": 0.92,
    "cross_layer": 0.78
  },
  "overall_grade": "B+",
  "recommendations": ["..."]
}
```

#### `feedback.json`

```json
{
  "session_id": "...",
  "student_id": "...",
  "teacher_id": "...",
  "submitted_at": "...",
  "fingerprint_feedback": {
    "pace": 0.5, "interactivity": 0.7
  },
  "pedagogy_feedback": {
    "concept_entry": "problem-driven",
    "analogy_density_perceived": "high"
  },
  "rating": 4,
  "comment": "..."
}
```

---

## 6. 双层指标体系

> 本节给出指标的**最终定义**。指标的提取算法、prompt 模板、校准方法在 M2 子文档中展开。

### 6.1 第一层 · 风格指纹（6 维，给学生看）

| # | 维度 | 0 端 | 1 端 | 数据来源 |
|---|---|---|---|---|
| F1 | **Pace** | 慢 | 快 | auto 0.6 / crowd 0.4 |
| F2 | **Detail** | 精炼 | 详细 | auto 0.7 / crowd 0.3 |
| F3 | **Abstraction** | 具象 | 抽象 | auto 0.7 / crowd 0.3 |
| F4 | **Interactivity** | 单向 | 频繁提问 | auto 0.5 / crowd 0.5 |
| F5 | **Humor** | 严肃 | 幽默 | auto 0.2 / crowd 0.8 |
| F6 | **Rigor** | 启发 | 严密 | auto 0.7 / crowd 0.3 |

- 取值范围：`0.0–1.0` 两位小数
- 必须附带 `confidence`（0–1）和 `source` 列表
- 冷启动期（crowd 样本 < 30）：仅用 auto 评分
- 两端**不分好坏**，用于风格匹配

### 6.2 第二层 · 教学法策略（5 维，驱动 AI）

| # | 维度 | 取值集合 | 数据来源 |
|---|---|---|---|
| P1 | `concept_entry.primary` | problem-driven / phenomenon-driven / definition-first / contrast-driven / history-driven | Skill 测试反馈 |
| P2 | `intuition_building.order` | intuition-first / formal-first / interleaved | Skill 测试反馈 |
| P3 | `analogy_density.level` | high / medium / low / zero | Skill 测试反馈 |
| P4 | `blackboard_strategy.primary_layout` | title-bullets / derivation-flow / comparison-table / mind-map / minimal | Skill 测试反馈 |
| P5 | `misconception_alert.mode` | proactive-explicit / proactive-implicit / reactive-only / absent | Skill 测试反馈 |

- 每个维度是 **enum 而非 score**，可被 Agent prompt 直接使用
- 数据来源是探针测试：跑一组标准 probe，让 evaluator agent 从 events 中反推策略
- 详细策略字段（如 signature_phrase、timing 等）见 `skill_profile_v2.json` schema

### 6.3 Skill 质量分

| 一致性 | 含义 | 红线 |
|---|---|---|
| **declared_observed** | Skill 文档声明 vs 探针实际表现 | ≥ 0.7 |
| **cross_probe** | 不同探针下表现一致性 | ≥ 0.8 |
| **cross_layer** | 第一层指纹 vs 第二层教学法是否合理 | ≥ 0.7 |
| **overall_grade** | A / B / C / D | < B 软拒绝上架 |

软拒绝定义：低 grade 仍可发布但 catalog 默认折叠；教师可主动选择"接受低 grade 上线"。

### 6.4 `skill_profile_v2.json` 完整 schema

```json
{
  "skill_id": "S_T20260515001_v2",
  "teacher_id": "T_20260515_001",
  "teacher_name": "示例老师",
  "subject": "高等数学",
  "version": 2,
  "generated_at": "2026-05-15T...",

  "fingerprint": {
    "pace":          { "value": 0.42, "confidence": 0.78, "source": ["auto","crowd"] },
    "detail":        { "value": 0.81, "confidence": 0.85, "source": ["auto"] },
    "abstraction":   { "value": 0.25, "confidence": 0.90, "source": ["auto"] },
    "interactivity": { "value": 0.68, "confidence": 0.65, "source": ["auto","crowd"] },
    "humor":         { "value": null, "confidence": 0.30, "source": ["crowd"] },
    "rigor":         { "value": 0.72, "confidence": 0.80, "source": ["auto"] }
  },
  "fingerprint_breakdown": {
    "pace": { "auto": 0.40, "crowd": 0.45 }
  },

  "pedagogy": {
    "concept_entry":       { "primary": "problem-driven", "fallback": "phenomenon-driven", "signature_phrase": "..." },
    "intuition_building":  { "order": "intuition-first", "intuition_source": ["daily-life"], "before_formal": true },
    "analogy_density":     { "level": "high", "per_concept": 1, "domain_pool": ["生活场景"] },
    "blackboard_strategy": { "primary_layout": "title-bullets", "secondary_layout": "comparison-table", "write_timing": "after-speak", "minimal_text": true },
    "misconception_alert": { "mode": "proactive-explicit", "timing": "after-definition", "signature_phrase": "..." }
  },

  "tags": ["warmth:high", "encourage:explicit", "english_term:always"],

  "coverage": { "philosophy": true, "analogy": true, "formula": false },

  "quality": {
    "declared_observed_consistency": 0.85,
    "cross_probe_consistency":       0.92,
    "cross_layer_consistency":       0.78,
    "overall_grade": "B+",
    "eval_report_path": "data/teachers/T_.../skills/v2/eval_report.json"
  },

  "corpus_stats": {
    "transcripts_count": 3,
    "total_duration_sec": 1820.5,
    "total_text_chars": 8420
  },

  "derived_from": "edunuwa-teacher-distiller v2"
}
```

---

## 7. 阶段路线图

### Phase 0（2 周，基础改造）

- 数据目录改造为多租户结构（`data/teachers/{teacher_id}/...`）
- `skill_profile_v2.json` schema 落定并被 M2 输出
- 现有蒸馏 prompt 增加第二层 5 维 enum 输出
- M6 backend 撑起骨架（账号 + teachers 列表 / 详情）
- 各模块 README 更新，与本文档对齐

### Phase 1（4-6 周，最小闭环）

- M1 ASR 接通（30 分钟级语料能跑通）
- M2 第一层 auto 评分 + 第二层 declared 推理
- M3 双轨 catalog 上线（SQLite + 5 个种子教师）
- M4 emitter 升级支持 pedagogy + 点播模式
- M5 TTS 接 pipeline + 黑板渲染 + 简版 player
- M6 学生端走通"发现 → 学习 → 反馈"

### Phase 2（4-6 周，跟随 + 教师上传）

- M2 探针测试 + 一致性检查 + grade
- M3 推荐算法（基于 fingerprint 距离）
- M4 planner + 跟随式学习
- M5 流式 TTS + Live2D 接入
- M6 教师端完整上传流程

### Phase 3（更后期，规模化）

- 像素 IP 资产 pipeline
- crowd 反馈回流 + 加权融合
- 个性化模型微调（产品壁垒）
- 教师分成 / 订阅 / 推荐排序

---

## 8. 下一步（各模块详细文档）

完成本文档后，按以下顺序撰写各模块的子文档（每份独立 MD）：

| 优先级 | 文档 | 路径 | 负责模块 |
|---|---|---|---|
| P0 | M2 详细方案与验收 | `docs/modules/M2_distill.md` | 风格蒸馏 |
| P0 | M4 详细方案与验收 | `docs/modules/M4_orchestrator.md` | Agent 编排 |
| P0 | M5 详细方案与验收 | `docs/modules/M5_runtime.md` | 学习运行时 |
| P1 | M1 详细方案与验收 | `docs/modules/M1_ingest.md` | 素材摄取 |
| P1 | M3 详细方案与验收 | `docs/modules/M3_catalog.md` | 教师目录 |
| P1 | M6 详细方案与验收 | `docs/modules/M6_platform.md` | APP 外壳 |

每份子文档统一结构：

1. 模块定位与边界
2. 核心模块拆分与文件结构
3. 详细接口（Python 函数签名 + 字段说明）
4. 关键技术挑战与实现指导
5. 验收标准（MVP / Phase 1 / Phase 2 量化指标）
6. 与其他模块的接口（输入来源 / 输出去向）
7. 团队配置建议
8. 风险与对策

---

## 9. 配套文档维护规范

- 本文档（`docs/EduNUWA_v2_总体方案.md`）是**单一真相源**，任何架构层面的变更必须先在此文档更新
- `docs/api_contract.md` 维护**已稳定数据契约的字段级 schema**（v1 时已稳定的 5 个文件）
- 各模块子文档（`docs/modules/M*.md`）维护**模块内部细节**
- 三类文档之间不允许出现冲突；冲突时以本文档为准
- 重大变更（schema 增减字段、模块边界调整）必须在 PR 中标注 `[BREAKING]` 并通知所有模块负责人

---

**END OF DOCUMENT**

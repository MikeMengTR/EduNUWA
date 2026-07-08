# M2 · Distill 风格蒸馏 + 评价 — 详细方案 v2.0

> **上游依赖**：M1 (Ingest) — `teacher_transcript.json`；M6 (Platform) — 触发蒸馏 + 转发学生反馈
> **下游消费者**：M3 (Catalog)、M4 (Orchestrator)
> **关联文档**：`docs/EduNUWA_v2_总体方案.md` §3.2/§6、`docs/modules/skill_descriptor_matching_spec.md`（评价体系定义）、`docs/modules/M3_catalog.md` v2.0（M2 输出 = M3 输入）
> **版本**：v2.0 · 2026-06-04
>
> **v2.0 范式变更（相对 v1.0）**：
> 1. 第一层风格从「6 维 0-1 数值 fingerprint」改为「**开放形容词标签** + 预计算 embedding」（不预设维度、可自由生长）。
> 2. 新增「**基础指标层**」：少数客观可测量（语速等）用数字 + 文字对照。
> 3. 新增「**学生反馈闭环**」：M2 读 feedback.json → 提炼 crowd 标签 → 归并写 `style_tags_live.json`（跨版本累积）。
> 4. 质量层重组为 `quality.stability`（一致性三件套）+ grade + publishable。
> **继承不变**：7 段 TeacherSkill.md、第二层 pedagogy 5 维 enum、探针测试 + 依赖注入（M2↔M4）、grade 软拒绝、版本管理、原子写、不反向依赖。

---

## 1. 模块定位与边界

### 1.1 一句话定位

把 transcript 蒸馏成可被 AI Agent 调用的 `TeacherSkill.md` + 可被学生语义匹配的 `skill_profile_v2.json`（开放风格标签 + 基础指标），通过探针测试给 Skill 打质量分，并持续吸收学生反馈沉淀 crowd 标签。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 7 段契约 `TeacherSkill.md` 生成 | ASR / 语料获取（M1 做）|
| 第一层**开放风格标签**提炼（auto）+ embedding | 教学事件生成（M4 做）|
| **基础指标**测量（语速等数字 + label）| 教师 CRUD（M6 做）|
| 第二层教学法 5 维策略推理 | 推荐排序 / 语义匹配（M3 做）|
| Skill 探针测试 + 一致性 + grade | 学生反馈**采集**（M6 做）|
| 学生反馈**提炼**为 crowd 标签 + 归并 | TTS / 渲染 |
| Skill 版本管理（v1, v2, v3...）| 修改已发布版本 |

> 关键分工（与 M6）：M6 **采集**原始评价写 `feedback.json`；M2 **提炼**评价为标签写 `style_tags_live.json`。提炼是 LLM 业务逻辑，归 M2 不归 M6。

### 1.3 核心价值

- **M2 是产品壁垒**：开放标签 + 基础指标 + grade 决定"双轨匹配"和"风格化教学"的可信度。
- **M2 是质量守门员**：grade < B 的 Skill 不在 catalog 默认展示。
- **M2 是语义基座**：它产出的标签 embedding 决定 M3 语义匹配的质量。

---

## 2. 子模块与文件结构

```text
modules/M2_distill/
  skill_distiller/                    # 现有，扩展
    nuwa_distill.py                   # 蒸馏入口（Claude SDK harness）
    _common.py                        # env / options / runner（M2/M4 共享）
    prompts/
      distill_v2.py                   # v2 prompt（7段 + declared pedagogy）
      style_tagging.py                # 新：transcript → 开放风格标签
      base_metrics.py                 # 新：客观指标测量 prompt（部分纯计算）
      pedagogy_inference.py           # 探针 events → pedagogy
  metric_extractor/                   # 改造（原 fingerprint → style）
    style_tagger.py                   # 替代 fingerprint.py：产开放标签(auto)
    base_metrics.py                   # 新：语速/互动频次/信息密度 数字+label
    embedding.py                      # 新：标签向量化（与 M3 同模型，关键）
    crowd_tagger.py                   # 替代 crowd_aggregator.py：feedback→crowd标签归并
    rubric/
      base_metrics_bands.json         # 基础指标 数字↔文字对照表
  pedagogy_inferer/                   # 不变
    declared_parser.py                # TeacherSkill.md → declared_pedagogy
    observed_inferer.py               # events → observed_pedagogy
    enums.py                          # 5 维 enum（与总体方案 §6.2 一致）
  skill_qa/                           # 基本不变
    probe_runner.py                   # 跑探针生成 events（依赖注入 M4）
    consistency_checker.py            # 三类一致性
    grader.py                         # → A/B/C/D
    eval_report_writer.py
  schemas/
    skill_profile_v2.schema.json      # SSOT，本版需更新（见 §5.2）
    style_tags_live.schema.json       # 新：crowd 标签文件 schema
  README.md
  run.py
  tests/
    test_distill.py  test_style_tagger.py  test_base_metrics.py
    test_embedding.py  test_crowd_tagger.py  test_pedagogy.py  test_qa.py
    fixtures/
data/eval_probes/                     # 标准探针题库 P01-P05（不变）
```

> 相对 v1.0：`fingerprint.py` + `features/*`（6 维数值特征）→ 由 `style_tagger.py` + `base_metrics.py` 替代；新增 `embedding.py`；`crowd_aggregator.py` → `crowd_tagger.py`。

---

## 3. 详细接口

### 3.1 主函数 1：完整蒸馏流程

```python
def distill_teacher_skill_v2(
    teacher_id: str,
    transcript_paths: list[str],
    output_dir: str,                  # 必须为 data/teachers/{tid}/skills/v{n}/
    config: dict | None = None,
) -> dict:
    """
    内部流程:
      1. LLM 蒸馏 → 7 段 TeacherSkill.md（含 <!-- pedagogy:declared --> 注释）
      2. extract_style_tags()   → 开放风格标签(auto) + 每标签 embedding
      3. extract_base_metrics() → 语速/互动频次等 数字 + label
      4. parse_declared_pedagogy() → 第二层 declared
      5. (可选) evaluate_skill() → 跑探针 → observed + 一致性 + grade
      6. 原子写 skill_profile_v2.json + TeacherSkill.md
    """
```

**返回**：
```json
{
  "status": "success",
  "skill_id": "S_T20260515001_v2",
  "skill_md": "data/teachers/T_.../skills/v2/TeacherSkill.md",
  "skill_profile": "data/teachers/T_.../skills/v2/skill_profile_v2.json",
  "eval_report": "data/teachers/T_.../skills/v2/eval_report.json",
  "grade": "B+",
  "style_tags_count": 14,
  "warnings": []
}
```

### 3.2 主函数 2：开放风格标签提炼（替代 extract_fingerprint）

```python
def extract_style_tags(
    transcript_paths: list[str],
    config: dict | None = None,
) -> dict:
    """
    从转写提炼开放风格形容词标签（不预设维度、不限词表）。
    每个标签附转写证据 + 预计算 embedding。

    Returns:
      {
        "status": "success",
        "style_tags": [
          {
            "text": "娓娓道来",
            "dimension": "pace",          # 可选软归类，可为 null（开放）
            "source": "auto",
            "confidence": 0.7,            # LLM 提炼置信度（auto 不走 support 饱和，见 §9.5）
            "evidence": ["seg_0003", "seg_0011"],   # 抗操纵：必须有转写证据
            "cluster_id": null            # 全局簇归 M3，M2 写 null
            # embedding_ref 省略：MVP 现算（见 §9.1），Phase 2 才持久化
          }
        ],
        "style_embeddings_model": "bge-base-zh-v1.5" # 与 M3 查询同模型（H6, 768 维）
      }
    """
```

### 3.3 主函数 3：基础指标测量（新增）

```python
def extract_base_metrics(
    transcript_paths: list[str],
    config: dict | None = None,
) -> dict:
    """
    测量少数客观可测的基础指标，数字 + 查对照表得 label。
    纯计算为主（字数/时长/设问计数），不依赖 LLM。

    Returns:
      {
        "status": "success",
        "base_metrics": {
          "speech_rate":   { "value": 165, "unit": "字/分",     "label": "偏慢",   "polarity": "slow" },
          "question_freq": { "value": 4.2, "unit": "次/10分钟", "label": "时常提问","polarity": "mid" },
          "info_density":  { "value": 0.38,"unit": "新概念/分钟","label": "从容",   "polarity": "low" }
        }
      }
    """
```

对照表 `rubric/base_metrics_bands.json`（数字↔文字，curated 但小）：
```json
{ "speech_rate": [ {"max":180,"label":"偏慢","polarity":"slow"},
                   {"max":280,"label":"适中","polarity":"mid"},
                   {"max":null,"label":"偏快","polarity":"fast"} ] }
```

### 3.4 主函数 4：第二层教学法推理（不变）

```python
def infer_pedagogy(skill_md_path: str, events_paths: list[str] | None = None,
                   config: dict | None = None) -> dict:
    """
    events_paths==None → 仅解析 declared；!=None → 同时反推 observed。
    Returns: { "status", "declared": {5维}, "observed": {5维}|null }
    """
```

### 3.5 主函数 5：Skill 质量评测（基本不变）

```python
def evaluate_skill(skill_md_path: str, teacher_id: str, output_dir: str,
                   probe_set: str = "default_v1",
                   emit_fn: Callable = None,    # 依赖注入 M4.generate_for_probe（H13）
                   config: dict | None = None) -> dict:
    """
    跑探针 → 推 observed pedagogy → 三类一致性 → grade
    Returns:
      { "status", "eval_report": "...", "grade": "B+",
        "consistency": { "declared_observed":0.85, "cross_probe":0.92, "cross_layer":0.78 } }
    """
```

### 3.6 主函数 6：学生反馈 → crowd 标签（新增，运营期闭环）

```python
def refresh_crowd_tags(
    teacher_id: str,
    feedback_paths: list[str] | None = None,   # None=自动扫描该教师相关 session
    config: dict | None = None,
) -> dict:
    """
    批量处理学生反馈，提炼/归并 crowd 标签，写 style_tags_live.json。

    流程:
      1. 读 feedback.json 的 free_text（M6 采集的学生自由评价）
      2. LLM 提炼风格短语
      3. 每短语算 embedding → 找最近已有标签簇
         命中 → support += 1，刷新 last_seen
         无匹配 → 新建标签(source=crowd, support=1)
      4. 同一 student_hash 对同一 teacher 去重（防刷单）
      5. 原子写 data/teachers/{tid}/style_tags_live.json

    Returns:
      { "status", "tags_updated": 3, "tags_new": 1, "live_path": "..." }
    """
```

> 触发：由 M6 编排（定时 / 攒够 N 条反馈）。M2 是处理器，M6 是触发器。**实时还是批量**：批量（众包标签需 support 累积、可去重防刷单、避免频繁重写）。

### 3.7 config 字段

```python
config = {
    "skill_backend": "edunuwa-teacher-distiller",
    "teacher_name": "示例老师",
    "subject": "高等数学",
    "language": "zh",
    "llm": { "provider": "claude", "model": "claude-opus-4-7",
             "temperature": 0.2, "max_tokens": 8000 },        # temp ≤ 0.3 (H4)
    "embedding": {
        "model": "bge-base-zh-v1.5",                          # 必须与 M3 一致 (H6)
        "dim": 768,
    },
    "style": {
        "max_tags_per_skill": 16,                             # auto 标签上限
        "min_evidence_per_tag": 1,                            # 每标签≥1条转写证据 (H5)
    },
    "crowd": {                                                # Phase 2
        "dedup_by_student": True,                             # 防刷单（student_hash 绑认证账号）
        "merge_similarity_threshold": 0.82,                   # 教师内近义合并阈值
        "support_k": 5,                                       # confidence 饱和系数 (§9.5, 禁 magic number)
        "half_life_days": 180,                                # recency_decay 半衰期 (§9.5)
    },                                                        # 注：来源权重 crowd/auto 由 M3 召回侧施加，不在此
    "qa": {
        "skip_probe_eval": False,
        "probe_set": "default_v1",
        "min_grade_to_publish": "B",
    },
    "version_strategy": "auto_increment",
}
```

---

## 4. 输入文件契约

### 4.1 来自 M1 — `teacher_transcript.json`

遵循 `api_contract.md §2`。**M2 强制校验**（不通过 fail）：`transcript_id`/`language`/`segments` 存在、segments ≥ 1、`segments[*].text` 非空。总时长 < 60s 或 总字数 < 200 → warning 但允许蒸馏（标记"语料偏少"，放宽质量阈值）。`low_confidence_segments` 在提炼时降权。

### 4.2 来自 M6 — `feedback.json`（运营期，crowd 标签原料）

```json
{
  "session_id": "SES_...",
  "teacher_id": "T_20260515_001",
  "skill_id": "S_T20260515001_v2",
  "student_hash": "a3f9...",                 // 去重/防刷单（哈希保护隐私）
  "rating": 4,
  "free_text": "老师讲题像讲故事，偶尔自嘲挺有意思",   // ← crowd 标签提炼原料
  "submitted_at": "2026-06-04T..."
}
```

> M2 只读 feedback.json 的 `free_text` 提炼标签 + `student_hash` 去重 + `skill_id` 关联版本。采集由 M6 负责。

---

## 5. 输出文件契约（给 M3、M4）

### 5.1 `TeacherSkill.md`（给 M4，7 段不变）

```text
# TeacherSkill: <teacher_name>
## Skill Purpose / Trigger / Teaching Philosophy / Explanation Pattern
## Blackboard Policy / Speech Policy / Output Contract
```

`Explanation Pattern` 段后追加机器可读注释块（M4 的 declared pedagogy 来源）：
```markdown
<!-- pedagogy:declared
{ "concept_entry": {...}, "intuition_building": {...}, "analogy_density": {...},
  "blackboard_strategy": {...}, "misconception_alert": {...} }
-->
```

> 改进项（P1）：可额外产出精简的「指令版」给 M4，去掉转写证据噪声。本版先保持 7 段契约不破坏 M4。

### 5.2 `skill_profile_v2.json`（给 M3，结构大改）

```json
{
  "skill_id": "S_T20260515001_v2",
  "teacher_id": "T_20260515_001",
  "teacher_name": "示例老师",
  "version": 2,
  "generated_at": "2026-06-04T...",

  "style_tags": [                                  // ← 替代 v1.0 的 fingerprint
    { "text": "娓娓道来", "dimension": "pace", "source": "auto",
      "confidence": 0.7, "evidence": ["seg_0003"], "cluster_id": null },
    { "text": "偶尔自嘲", "dimension": "humor", "source": "auto",
      "confidence": 0.4, "evidence": ["seg_0028"], "cluster_id": null }
  ],
  // 注：MVP 不存 embedding_ref（M3 加载时按 text 现算）；source 仅 auto/self，crowd 在 style_tags_live.json
  "style_embeddings_model": "bge-base-zh-v1.5",    // 与 M3 查询同模型（H6）

  "base_metrics": {                                // ← 新增数字层
    "speech_rate":   { "value": 165, "unit": "字/分", "label": "偏慢", "polarity": "slow" },
    "question_freq": { "value": 4.2, "unit": "次/10分钟", "label": "时常提问", "polarity": "mid" }
  },

  "pedagogy": {                                    // ← 第二层 enum，不变
    "concept_entry": { "primary": "problem-driven", ... },
    "intuition_building": { "order": "intuition-first", ... },
    "analogy_density": { "level": "high", ... },
    "blackboard_strategy": { "primary_layout": "title-bullets", ... },
    "misconception_alert": { "mode": "proactive-explicit", ... }
  },

  "quality": {                                     // ← 重组
    "stability": {
      "declared_observed_consistency": 0.85,
      "cross_probe_consistency": 0.92,
      "cross_layer_consistency": 0.78
    },
    "overall_grade": "B+",
    "publishable": true,
    "eval_report_path": "data/teachers/T_.../skills/v2/eval_report.json"
  },

  "attributes": {                                  // ← 新增
    "subject": "高等数学",
    "language": "zh",
    "corpus_stats": { "transcripts_count": 3, "total_duration_sec": 1820.5, "total_text_chars": 8420 }
  }
}
```

字段约束：
- `style_tags[*].text`：开放自然语言，不限词表；`dimension` 可为 null（开放）。
- `style_tags[*].source`：skill_profile 内**只能 auto/self**，crowd 标签禁止写入此处（H14，schema 强制）。
- `style_tags[*].evidence`：auto 标签**必须 ≥1 条**转写证据（H5 抗操纵）。
- `style_tags[*].confidence`：auto 用 LLM 提炼置信度，**不走 support 饱和**（见 §9.5）。
- `style_tags[*].embedding_ref`：MVP 省略（现算）；Phase 2 才持久化。
- `style_embeddings_model`：与 M3 查询 embedding **同模型同版本**（H6）。bge-base-zh-v1.5 = **768 维**。
- `base_metrics`：仅客观可测项；主观风格一律走 style_tags，不进此处。
- `quality.overall_grade` ∈ {A,A-,B+,B,B-,C+,C,C-,D,**NA**}；`publishable = grade ≥ min_grade`。
- `quality.stability`（一致性三件套）**仅在跑探针时存在**。`skip_probe_eval=True`（如本地调试、未接 M4）时：省略 `stability`、`overall_grade="NA"`、`publishable=false`——该 skill 不入 catalog 主展示，待补探针评测后重算。schema 据此把 `stability` 设为可选。
- **零标签兜底**：若语料极少导致 0 个合格 style_tag，仍须写 `base_metrics` + grade，并在 `warnings` 标 `"zero_style_tags"`（M3 据此回退到 base_metrics + grade 排序，见 M3 §5）。

### 5.3 `style_tags_live.json`（给 M3，crowd 标签，跨版本累积）

```json
{
  "teacher_id": "T_20260515_001",
  "style_embeddings_model": "bge-base-zh-v1.5",
  "tags": [
    { "text": "讲题像讲故事", "dimension": null, "source": "crowd",
      "support": 23, "confidence": 0.95, "cluster_id": null,
      "first_seen": "2026-05-20", "last_seen": "2026-06-04" }
  ],
  "updated_at": "2026-06-04T..."
}
```

> `cluster_id=null`（M3 回填全局簇）；MVP 无 `embedding_ref`（Phase 2 持久化）；字段名 `style_embeddings_model` 与 skill_profile 及 `style_tags_live.schema.json` 统一。

> **不放进 skill_profile_v2.json**：skill_profile 是蒸馏快照（跟版本、不可变），crowd 标签是持续变的运营数据。分离存储，重蒸馏出 v3 时 crowd 标签不丢。M3 匹配时合并读两者。

### 5.4 `eval_report.json`（不变，质量审计）

含 probe_results、consistency 三件套、overall_grade、grade_reasoning、recommendations。结构同 v1.0。

---

## 6. 硬性要求（不可妥协）

| # | 硬性要求 | 验证 |
|---|---|---|
| H1 | `skill_profile_v2.json` 通过 `schemas/skill_profile_v2.schema.json` 校验 | CI |
| H2 | `TeacherSkill.md` 含 7 段且非空 | 自动检查 |
| H3 | `TeacherSkill.md` 含 `<!-- pedagogy:declared -->` 注释块 | 自动检查 |
| H4 | LLM 提炼/评分 temperature **≤ 0.3** | code review |
| H5 | 每个 auto `style_tag` **必须 ≥1 条转写证据**（evidence 非空）；无证据的标签丢弃 | 自动测试（抗操纵）|
| H6 | `style_embeddings_model` 与 M3 查询 embedding **同模型同版本**；模型版本写进 profile | 启动校验 + code review |
| H7 | grade < B 时 `warnings` 含 `"low_grade_soft_reject"`，`publishable=false` | 自动测试 |
| H8 | 蒸馏失败 fallback 到上一版 Skill（如存在），不删已有版本 | 集成测试 |
| H9 | 不调用 M3/M4/M5/M6 代码 | 静态扫描 import |
| H10 | crowd 标签抗操纵：`student_hash` 去重且绑**已认证账号**；`support_k`/`half_life_days` 从 config 读（禁 magic number）；`source=self` 标记为教师自述（来源权重由 M3 施加）| code review + 测试 |
| H11 | 写文件原子（tmp + os.replace）| code review |
| H12 | 已发布 Skill 版本只读，不可修改（v1/v2 写入即冻结）| 文件权限 + 测试 |
| H13 | 跑探针调 M4 emitter 必须**依赖注入**（`emit_fn` 参数），禁止 import M4 | 静态扫描 |
| H14 | crowd 标签写 `style_tags_live.json`，**禁止写回 skill_profile_v2.json**（快照不可变）| code review |

---

## 7. 验收标准

### 7.1 MVP（Phase 1）

| # | 指标 | 标准 |
|---|---|---|
| A1 | 蒸馏成功率（10 真实教师）| ≥ 90% |
| A2 | skill_profile_v2 schema 通过率 | 100% |
| A3 | 每个 style_tag 有转写证据（H5）| 100% |
| A4 | style_tag 提炼跨语料稳定性（同教师两份语料标签簇重合）| ≥ 0.6 |
| A5 | base_metrics 数字↔label 映射正确 | 100% |
| A6 | embedding 模型版本与 M3 一致（H6）| 校验通过 |
| A7 | declared pedagogy 注释块解析 | 100% |
| A8 | 单 Skill 蒸馏端到端（不含探针）| < 10 min |
| A9 | grade 软拒绝生效 | ✅ |

### 7.2 Phase 2

| # | 指标 | 标准 |
|---|---|---|
| A10 | crowd 反馈闭环：模拟评价 → 标签 support 正确累加/新建 | ✅ |
| A11 | crowd 防刷单：同 student_hash 重复评价去重 | ✅ |
| A12 | 蒸馏成功率 | ≥ 99% |
| A13 | declared vs observed 一致性 | > 0.85 |
| A14 | 标签提炼稳定性 | ≥ 0.8 |

### 7.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A15 | grade 分布与人工评估相关性 | > 0.7 |
| A16 | 多主题语料重蒸馏，风格标签覆盖更全 | ✅ |

---

## 8. 与其他模块的接口

### 8.1 输入

| 来源 | 内容 | 协议 | 路径 |
|---|---|---|---|
| M1 ingest | `teacher_transcript.json` | 文件读 | `data/teachers/{tid}/transcripts/*.json` |
| M6 platform | `feedback.json`（crowd 原料）| 文件读 | `data/sessions/*/feedback.json` |
| M6 platform | 触发蒸馏 / `refresh_crowd_tags` | Python 调用 | — |
| M4（注入）| `generate_for_probe` callable | 依赖注入 | — |

### 8.2 输出

| 去向 | 内容 | 路径 |
|---|---|---|
| M3 catalog | `skill_profile_v2.json`（style_tags + base_metrics + quality）| `skills/v{n}/` |
| M3 catalog | `style_tags_live.json`（crowd 标签）| `data/teachers/{tid}/` |
| M3 catalog | `eval_report.json`（grade）| `skills/v{n}/` |
| M4 orchestrator | `TeacherSkill.md` + declared pedagogy 注释 | `skills/v{n}/` |
| M6 platform | 任务进度 `query_progress(task_id)` | — |

### 8.3 契约一致性自检（重点：与 M3 v2.0）

| 检查点 | 状态 |
|---|---|
| `skill_profile.style_tags` 扁平列表结构 = M3 §4.1 消费结构 | ✅ 已统一为扁平 style_tags 列表（M2 §5.2 = M3 §4.1 = schema）|
| `style_tags_live.json` 结构 = M3 §4.2 | 一致 |
| `style_embeddings_model` = M3 查询 embedding 模型 | **必须双方文档写明同一型号**（H6 / M3 H6）|
| `base_metrics` 结构 = M3 §4.1 base_metrics | 一致 |
| `quality.overall_grade` 枚举 = M3 软拒绝 | 一致 |
| teacher_id / skill_id 命名 = 总体方案 §5.2 | 一致 |
| pedagogy 5 维 enum = 总体方案 §6.2 | 一致 |
| 异步任务进度 = 总体方案 §4.3.4 | 一致 |
| 调 M4 探针走依赖注入 | H13 |

---

## 9. 关键技术挑战与实现指导

### 9.1 开放风格标签提炼（替代 6 维评分）

- **怎么提**：LLM 读转写，提炼形容词短语，**每个必须附转写证据**（seg 引用）。不限词表、不限维度，但可给软 `dimension` 归类（pace/detail/.../humor 或 null）。
- **抗操纵**：H5 强制证据——无转写支撑的标签丢弃。这替代了 v1.0 数值的客观锚定。
- **去重**：同一 skill 内近义标签（embedding 相似度 > 阈值）合并。
- **embedding（MVP 现算，不持久化）**：MVP 不存 `embedding_ref`——M3 加载 skill_profile 时持同一模型对 `text` 现算向量即可（内存全表 < 1000 教师，batch 编码秒级）。`embedding_ref` 是 Phase 2 上向量库后的持久化句柄。M2 仍需 embedding 能力（crowd 归并要算相似度），且**模型版本必须与 M3 一致**（H6）。**部署建议**：M2/M3 共用一个轻量 embedding 微服务（单点），天然保证 H6 同模型，避免各加载一份模型 ×2 资源。

### 9.2 基础指标 vs 风格标签的分界

| 进 base_metrics（数字）| 进 style_tags（形容词）|
|---|---|
| 客观可测、有单位（语速 字/分、设问 次/10分）| 主观感受（讲故事式、亲切、自嘲）|
| 需精确筛选/排序 | 没有客观刻度 |

判断准则：**能否用 auto 纯计算出一个带单位的数？** 能 → base_metrics；不能 → style_tags。

**具体算法（避免实现歧义）**：
- `speech_rate` = 总字数 / 总有效语音时长（分钟）。字数 = 去标点去空格的中文/英文字符数；时长用 `segments[*].end - start` 之和（**不含段间停顿**，避免静音拉低语速）；多 transcript 按时长加权汇总。
- `question_freq` = 设问句数 / (总时长/10分钟)。设问判定 MVP 用规则：句末 `？` 或含疑问词（吗/呢/怎么/为什么/是不是/会不会…）；规则法有偏差但可计算、可复现，比 LLM 稳定。
- `info_density` = 不重复新概念数 / 时长（分钟）。新概念可用术语词典或简单 TF 突现，Phase 2 再精化。
- `label` 由查 `rubric/base_metrics_bands.json`（数字↔文字对照，**该文件是 label 的唯一 SSOT**，M3 facets 的档位展示也引用同一份，禁止两边各写一套）。

### 9.3 探针测试的循环依赖处理（继承 v1.0）

M2 评测需要 M4 实际生成 events 看表现，但 M2→M4→需要 Skill 形成环。**用依赖注入破环**：

```python
# good：M2 接收 M4 的函数，不 import M4
def evaluate_skill(..., emit_fn: Callable):
    events = emit_fn(probe_question, skill_md_path)   # 调用方传入 M4.generate_for_probe

# bad：禁止
from modules.M4_orchestrator import generate_for_probe   # H13 拒绝
```

### 9.4 grade 计算（继承 v1.0）

三类一致性 → 加权综合 → A/B/C/D。红线：`declared_observed ≥ 0.7`、`cross_probe ≥ 0.8`、`cross_layer ≥ 0.7`，任一不达标降档；< B 软拒绝。

### 9.5 confidence 公式：auto 与 crowd 必须分流（关键）

auto 与 crowd **不能共用同一条 confidence 公式**——auto 标签 support 恒为 1，若走 support 饱和会被系统性压低（`1-exp(-1/5)≈0.18`），叠加来源权重后冷启动新教师所有标签 confidence≈0.11，在 M3 召回里排不进 Top-K。两者分开算：

```
# auto 标签（蒸馏快照）：用 LLM 提炼置信度，不走 support 饱和
confidence_auto = llm_extraction_confidence              # 典型 0.5–0.8

# crowd 标签（学生反馈）：众包共识 + 时效衰减
confidence_crowd = (1 - exp(-support / SUPPORT_K)) × recency_decay(last_seen)
  recency_decay = 0.5 ** (days_since(last_seen) / HALF_LIFE_DAYS)
  SUPPORT_K      = config.crowd.support_k     (默认 5)
  HALF_LIFE_DAYS = config.crowd.half_life_days (默认 180)   # 禁 magic number (H10)
```

> 来源权重（crowd=1.0 / auto=0.6）由**消费侧 M3** 在召回排序时施加（M3 §5.2），不在 M2 算。即：M2 算"标签自身可信度"，M3 算"来源该信多少"。

### 9.6 crowd 标签归并（Phase 2）

```
对每条 feedback.free_text:
  phrases = LLM_extract_style_phrases(free_text)
  for p in phrases:
    if (student_hash, teacher_id, nearest_local_tag(p)) 已记录: continue   # 防刷单去重
    v = embedding(p)
    # 只在【该教师已有 crowd 标签】内找近义合并，不做全局聚类
    nearest = argmax_{t in this_teacher.tags} cosine(v, embedding(t.text))
    if cosine ≥ merge_threshold:  nearest.support += 1; 刷新 last_seen
    else:                         新建标签(source=crowd, support=1, cluster_id=null)
原子写 style_tags_live.json
```

- **防刷单**：`student_hash` 必须绑定**已认证账号**（游客不计 support，否则去重形同虚设）。
- **不写全局 cluster_id**：M2 只做该教师内近义合并，全局簇唯一归 M3（M3 §6.3），M2 一律写 `cluster_id=null`——避免 M2/M3 各算一套簇漂移。

### 9.7 SKILL.md 蒸馏脚本的对齐改造（必做）

当前 `.claude/skills/edunuwa-teacher-distiller/SKILL.md` 的 Phase 3 产出的是**旧版 skill_profile**（`dimensions_covered` 那套），与本方案的 `style_tags` + `base_metrics` 脱节。**Phase 0 必须改造 SKILL.md**：
- Phase 2 的"八维提炼" → 映射为 style_tags（带证据）+ base_metrics + declared pedagogy
- Phase 3 产出对齐本文件 §5.2 的 skill_profile_v2.json

> 这是 v1.0→v2.0 最大的实现欠账（详见对 distiller 的评估）。

### 9.8 版本管理（继承 v1.0）

`skills/v{n}/` 自增；已发布版本只读（H12）；重蒸馏出新版本，旧版保留；crowd 标签在 `style_tags_live.json` 跨版本累积不受重蒸馏影响。

---

## 10. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| embedding 模型 M2/M3 不一致 → 向量错位 | 中 | 高 | H6：模型版本写进 profile + 启动校验 |
| auto 标签编造（无证据）| 中 | 高 | H5：强制转写证据，无证据丢弃 |
| crowd 标签刷单 | 中 | 中 | H10：student_hash 去重 + source 权重 + 异常检测 |
| 单主题语料 → 标签覆盖窄 | 高 | 中 | 多主题重蒸馏（A16）；运营期 crowd 补全 |
| 标签近义爆炸 | 中 | 中 | 同 skill 内去重 + M3 周期聚类归并 |
| SKILL.md 未对齐 v2 产出 | 高 | 高 | §9.6 列为 Phase 0 必做 |

---

## 11. 本地开发与测试

### 11.1 快速跑通

```bash
python modules/M2_distill/run.py \
  --teacher_id T_legacy_001 \
  --transcript data/teachers/T_legacy_001/transcripts/TR_Tlegacy001_001.json \
  --output data/teachers/T_legacy_001/skills/v3/ \
  --teacher 示例老师 --subject 高等数学 --skip_probe_eval
```

### 11.2 必须提供的测试

```text
test_style_tagger.py    # 开放标签提炼 + 证据强制(H5)
test_base_metrics.py    # 数字↔label 对照
test_embedding.py       # 模型版本一致性(H6) + 向量产出
test_crowd_tagger.py    # feedback→标签归并 + 去重防刷单(H10)
test_pedagogy.py        # declared/observed
test_qa.py              # 一致性 + grade + 软拒绝
test_distill.py         # 端到端 + schema(H1) + 7段(H2) + 注释块(H3)
fixtures/               # 真实转写 + 模拟 feedback
```

### 11.3 CI 检查

- skill_profile_v2 schema 校验（H1）
- 每 style_tag 有 evidence（H5）
- embedding 模型版本一致性（H6）
- crowd 标签禁写回 skill_profile（H14）
- 静态扫描 import 不含 M3/M4/M5/M6（H9）

---

## 12. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | **改造 SKILL.md**：Phase 2/3 产出对齐 style_tags + base_metrics + declared pedagogy（§9.6）| 蒸馏产物含新字段 |
| 2 | 更新 `skill_profile_v2.schema.json`：fingerprint→style_tags、新增 base_metrics/attributes、quality 重组 | schema 校验通过 |
| 3 | 选定 embedding 模型（建议 bge-base-zh-v1.5），与 M3 owner 对齐版本 | 双方文档写明同型号 |
| 4 | 实现 `extract_style_tags()` + 证据强制 + embedding | 5 个 mock 转写产出带证据标签 |
| 5 | 实现 `extract_base_metrics()` + 对照表 | 语速等数字+label 正确 |
| 6 | 实现 `refresh_crowd_tags()` + 去重 | 模拟 feedback 能累加 support |
| 7 | 与 M3 owner 对齐 `skill_profile.style_tags` / `style_tags_live` / embedding 模型 | M3 §4.1 统一为扁平列表 |
| 8 | 探针测试依赖注入接口与 M4 owner 对齐 | `emit_fn` 签名一致 |

---

## 13. 实现现状（MVP 已落地，2026-06-04）

> 本节记录实际跑通的代码，区别于上文的「方案/契约」。M2 现已落地**两条产出链**：完整蒸馏（产 TeacherSkill.md）+ 评价指标提炼（产 style_tags/base_metrics）。已用 6 所高校真实课程数据验证。

### 13.1 蒸馏链 · skill_distiller（产 TeacherSkill.md + skill_profile）

| 项 | 说明 |
|---|---|
| **用途** | 教师转写 → 7 段 `TeacherSkill.md`（给 M4 讲课）+ `skill_profile.json`（评价指标）|
| **实现方式** | `nuwa_distill.py` 调 `claude-agent-sdk` → Claude Code CLI → DeepSeek，执行 vendored Skill `.claude/skills/edunuwa-teacher-distiller/SKILL.md` 的 7-phase 流程（Phase 0 校验 → 2 八维提炼 → 2.6 映射 style_tags/base_metrics/pedagogy → 3 组装 → 4 自检）|
| **代码结构** | `skill_distiller/nuwa_distill.py`（入口 `distill_teacher_skill`）+ `_common.py`（env/options/runner；**REPO_ROOT 已修**：`THIS_DIR.parents[2]`，之前误算到 `modules/` 导致找不到 skill/.env）+ `.claude/skills/edunuwa-teacher-distiller/SKILL.md`（蒸馏大脑，已改造产 v2 格式）|
| **使用方式** | 单份：`python modules/M2_distill/skill_distiller/nuwa_distill.py --transcript <tr.json> --output <dir> --teacher <名> --subject <学科>`<br>批量 6 位：`python scripts/distill_all_full.py`（合并每位转写截至 8000 字，串行完整蒸馏，约 3-6 分钟/位）|
| **实际效果** | 6 所高校真实课程蒸馏 **6/6 成功**，每位产出 11-17KB `TeacherSkill.md`（7 段齐全 + `<!-- pedagogy:declared -->` 注释块）。风格区分极显著：style_tags 两两 Jaccard **0.01**，pedagogy 5 维取值多样性 **13/25**（如园林=history-driven、机器学习=definition-first+low类比、概率论=phenomenon-driven+high类比）|
| **对接格式** | 输入 `teacher_transcript.json`（M1 产，§4.1）；输出 `TeacherSkill.md`（§5.1 七段）+ `skill_profile_v2.json`（§5.2，过 `skill_profile_v2.schema.json`）。蒸馏阶段不跑探针 → `quality.overall_grade="NA"`、省略 `stability`（schema 允许）|

### 13.2 评价链 · metric_extractor（轻量产指标，不走 agent-sdk）

| 项 | 说明 |
|---|---|
| **用途** | 转写 → `style_tags`（开放风格标签）+ `base_metrics`（客观数字）。是 13.1 的轻量替代：只产评价指标、不产 .md，快（秒级~20s）|
| **实现方式** | `base_metrics.py` 纯计算（无 LLM）；`style_tagger.py` 用 **DeepSeek OpenAI 兼容接口**（`https://api.deepseek.com/v1/chat/completions`，`requests` 直调，比 agent-sdk 轻）提炼标签 + **H5 强制转写证据**（无 seg 证据的标签丢弃）|
| **代码结构** | `metric_extractor/base_metrics.py`（`extract_base_metrics`）、`style_tagger.py`（`extract_style_tags`）、`rubric/base_metrics_bands.json`（数字↔label 对照表，**label 的唯一 SSOT**）、`__init__.py`（导出两函数）|
| **使用方式** | `from modules.M2_distill.metric_extractor import extract_base_metrics, extract_style_tags`<br>CLI：`python modules/M2_distill/metric_extractor/base_metrics.py <tr.json>` / `style_tagger.py <tr.json>` |
| **实际效果** | 6 位评价 **6/6**；实测 **5000 字就够**提炼 6-8 个带证据标签（标签数在 5000 字饱和，再多语料主要提准不增量）；base_metrics 跨 6 位有梯度（语速 131-260 字/分）|
| **对接格式** | 输入 transcript（需 `segments[].start/end` 算语速、`text` 提标签）；输出 `skill_profile` 的 `style_tags` + `base_metrics` 片段。**LLM 注意**：DeepSeek-v4-flash 是 reasoning 模型，`max_tokens` 要给足（含 reasoning_tokens），否则返回空 |

### 13.3 真实测试数据

`data/teachers/T_20260604_001..006/` —— 6 所高校真实课程（概率论·华东师大 / 高数·东北大 / 机器学习·北理工 / 思政·华南理工 / 园林·北林 / 线代·浙大），由 M1 产出后经 `scripts/migrate_teacher_data.py` 迁入规范位置（teacher_id 合规化）。每位含 `transcripts/` + `audio_samples/`（135 个 wav 全在）+ `teacher_card.json` + `skills/v1/`（评价链产物）+ `skills/v2_full/`（蒸馏链产物）。

### 13.4 配套测试/工具脚本（见 `scripts/README.md`）

`distill_all_full.py`（批量完整蒸馏）、`test_eval_system.py`（6位评价系统验证）、`analyze_style_diff.py`（风格差异分析）、`test_skill_completeness.py`（文本量充分性）、`check_teacher_data.py`（数据合规检查）、`migrate_teacher_data.py`（数据迁移）。

### 13.5 尚未落地（待后续）

- `refresh_crowd_tags()`（学生反馈 → crowd 标签，依赖 M6 反馈采集）— Phase 2
- 探针评测 `evaluate_skill()`（产真实 grade，依赖 M4 `generate_for_probe` 依赖注入）— 当前所有 skill 的 grade=NA
- 标签 embedding 持久化（MVP 现算即可）— Phase 2

---

**END OF M2 DOCUMENT v2.0**

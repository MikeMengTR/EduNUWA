# M2 · Distill 风格蒸馏 + 双层指标 — 详细方案

> **上游依赖**：M1 (Ingest) — 提供 `teacher_transcript.json`
> **下游消费者**：M3 (Catalog)、M4 (Orchestrator)
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.2、§6
> **版本**：v1.0 · 2026-05-15

---

## 1. 模块定位与边界

### 1.1 一句话定位

把 transcript 蒸馏成可被 AI Agent 直接调用的 `TeacherSkill.md` + 可被学生筛选/匹配的 `skill_profile_v2.json`，并通过探针测试给 Skill 打质量分。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 7 段契约 `TeacherSkill.md` 生成 | ASR / 语料获取（M1 做） |
| 第一层风格指纹 6 维 auto 评分 | 教学事件生成（M4 做） |
| 第二层教学法 5 维策略推理 | 教师 CRUD（M6 做） |
| Skill 探针测试 + 一致性检查 + grade | 推荐排序（M3 做） |
| Skill 版本管理（v1, v2, v3...） | 学生反馈采集（M5/M6 做） |
| crowd 反馈融合到 fingerprint（仅融合） | TTS / 渲染 |

### 1.3 核心价值

- **M2 是产品壁垒**：双层指标体系直接决定"双轨匹配"和"风格化教学"的可信度
- **M2 是质量守门员**：grade < B 的 Skill 不能在 catalog 默认展示

---

## 2. 子模块拆分与文件结构

```text
modules/M2_distill/
  skill_distiller/                    # 现有，扩展
    nuwa_distill.py                   # 现有：Claude SDK + 蒸馏入口
    _common.py                        # 现有：env / options / runner
    prompts/
      distill_v2.py                   # 新：v2 prompt (含 pedagogy 输出)
      pedagogy_inference.py           # 新：探针 events → pedagogy
      fingerprint_scoring.py          # 新：transcript → 6 维分
  metric_extractor/                   # 新增
    fingerprint.py                    # 第一层 6 维评分入口
    features/
      pace_features.py                # 字数/分钟、子点切换
      detail_features.py              # 单概念句数等
      abstraction_features.py
      interactivity_features.py
      humor_features.py               # 信号词 + LLM 复评
      rigor_features.py
    crowd_aggregator.py               # 学生反馈加权融合
  pedagogy_inferer/                   # 新增
    declared_parser.py                # TeacherSkill.md → declared_pedagogy
    observed_inferer.py               # events → observed_pedagogy
    enums.py                          # 5 维 enum 定义（与总体方案 §6.2 一致）
  skill_qa/                           # 新增
    probe_runner.py                   # 跑探针生成 events
    consistency_checker.py            # C1/C2/C3 三类一致性
    grader.py                         # 综合打分 → A/B/C/D
    eval_report_writer.py
  schemas/
    skill_profile_v2.schema.json      # 关键产物，作为 SSOT
  README.md
  run.py                              # 本地测试入口
  tests/
    test_distill.py
    test_fingerprint.py
    test_pedagogy.py
    test_qa.py
    fixtures/
data/eval_probes/                     # 标准探针题库（项目级）
  P01_concept_explain.json
  P02_formula_derive.json
  P03_misconception.json
  P04_example_walk.json
  P05_compare.json
  README.md
```

---

## 3. 详细接口

### 3.1 主函数 1：完整蒸馏流程

```python
def distill_teacher_skill_v2(
    teacher_id: str,
    transcript_paths: list[str],
    output_dir: str,
    config: dict | None = None,
) -> dict:
    """
    完整蒸馏：transcript → TeacherSkill.md + skill_profile_v2.json
    
    内部流程:
      1. 调 LLM 生成 7 段 TeacherSkill.md（含 declared pedagogy）
      2. extract_fingerprint() → 第一层 auto 分
      3. parse_declared_pedagogy() → 第二层 declared
      4. (可选) evaluate_skill() → 跑探针 → observed + grade
      5. 写出 skill_profile_v2.json + TeacherSkill.md
    
    Args:
        teacher_id: 教师 ID
        transcript_paths: 一份或多份 transcript
        output_dir: 必须为 data/teachers/{teacher_id}/skills/v{n}/
        config: 见 §3.5
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
  "warnings": []
}
```

### 3.2 主函数 2：第一层指纹评分

```python
def extract_fingerprint(
    transcript_paths: list[str],
    config: dict | None = None,
) -> dict:
    """
    返回 6 维 auto 分（不含 crowd）。
    
    Returns:
      {
        "status": "success",
        "fingerprint": {
          "pace":          { "value": 0.42, "confidence": 0.78, "source": ["auto"] },
          "detail":        { "value": 0.81, "confidence": 0.85, "source": ["auto"] },
          "abstraction":   { "value": 0.25, "confidence": 0.90, "source": ["auto"] },
          "interactivity": { "value": 0.68, "confidence": 0.65, "source": ["auto"] },
          "humor":         { "value": null, "confidence": 0.30, "source": ["auto"] },
          "rigor":         { "value": 0.72, "confidence": 0.80, "source": ["auto"] }
        },
        "features": { ... }   // 底层特征，用于审计
      }
    """
```

### 3.3 主函数 3：第二层教学法推理

```python
def infer_pedagogy(
    skill_md_path: str,
    events_paths: list[str] | None = None,
    config: dict | None = None,
) -> dict:
    """
    两种模式:
      - events_paths == None: 仅解析 TeacherSkill.md → declared
      - events_paths != None: 同时反推 observed
    
    Returns:
      {
        "status": "success",
        "declared": { ... 5 维 ... },
        "observed": { ... 5 维 ... } | null
      }
    """
```

### 3.4 主函数 4：Skill 质量评测

```python
def evaluate_skill(
    skill_md_path: str,
    teacher_id: str,
    output_dir: str,
    probe_set: str = "default_v1",
    config: dict | None = None,
) -> dict:
    """
    跑探针 → 推 observed pedagogy → 三类一致性 → 综合 grade
    
    Returns:
      {
        "status": "success",
        "eval_report": "data/teachers/T_.../skills/v2/eval_report.json",
        "grade": "B+",
        "consistency": {
          "declared_observed": 0.85,
          "cross_probe": 0.92,
          "cross_layer": 0.78
        }
      }
    """
```

### 3.5 config 字段

```python
config = {
    "skill_backend": "edunuwa-teacher-distiller",  # 或 nuwa-skill (对照基线)
    "teacher_name": "示例老师",                         # 用于 prompt 中称呼
    "subject": "高等数学",
    "llm": {
        "provider": "claude",                       # claude / deepseek
        "model": "claude-opus-4-7",
        "temperature": 0.2,                         # 必须 ≤ 0.3，见 H4
        "max_tokens": 8000,
    },
    "fingerprint": {
        "n_runs": 3,                                # LLM 评分跑 3 次取均值
        "use_llm_scoring": True,
        "use_statistical_features": True,
    },
    "pedagogy": {
        "n_runs": 3,                                # 同上，取众数
    },
    "qa": {
        "skip_probe_eval": False,                   # 跳过探针测试（仅给 declared）
        "probe_set": "default_v1",
        "min_grade_to_publish": "B",                # < B 软拒绝
    },
    "version_strategy": "auto_increment",           # 自动 v1, v2, v3
}
```

---

## 4. 输入文件契约（来自 M1）

读入 `teacher_transcript.json`，遵循 `api_contract.md §2`。

**M2 强制校验**（不通过直接 fail）：

- `transcript_id`, `language`, `segments` 字段必须存在
- `segments` 至少 1 条
- `segments[*].text` 非空
- 总时长 ≥ 60 秒（语料过短 → warning，但仍允许蒸馏）
- 总字数 ≥ 200（同上）

**与 M1 的契约一致性自检**：

- ✅ M1 输出 `data/teachers/{tid}/transcripts/TR_*.json`，M2 在此目录读取
- ✅ M1 的 `teacher_id` 字段被 M2 透传到 `skill_profile_v2.teacher_id`
- ✅ M1 标记的 `low_confidence_segments` 在 M2 评分时降权

---

## 5. 输出文件契约（给 M3、M4）

### 5.1 `TeacherSkill.md`

必须包含 7 段：

```text
# TeacherSkill: <teacher_name>

## Skill Purpose
## Trigger
## Teaching Philosophy
## Explanation Pattern
## Blackboard Policy
## Speech Policy
## Output Contract
```

**v2 新增要求**：在 `Explanation Pattern` 段后追加机器可读注释块：

```markdown
<!-- pedagogy:declared
{
  "concept_entry": { "primary": "problem-driven", ... },
  "intuition_building": { "order": "intuition-first", ... },
  "analogy_density": { "level": "high", ... },
  "blackboard_strategy": { "primary_layout": "title-bullets", ... },
  "misconception_alert": { "mode": "proactive-explicit", ... }
}
-->
```

→ `pedagogy_inferer.declared_parser` 直接从这个块解析，无需 LLM 二次处理。

### 5.2 `skill_profile_v2.json`

**严格按总体方案 §6.4 schema**。新增本模块约束：

- `fingerprint.*.value` ∈ [0.0, 1.0] 或 `null`（仅 humor 允许 null 表示未评）
- `fingerprint.*.confidence` ∈ [0.0, 1.0]
- `pedagogy.*.primary` 必须从 enum 中取（见 enums.py）
- `quality.overall_grade` ∈ {"A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D"}
- `version` 必须递增

### 5.3 `eval_report.json`

```json
{
  "skill_id": "S_T20260515001_v2",
  "evaluated_at": "2026-05-15T...",
  "probe_set": "default_v1",
  "probe_results": [
    {
      "probe_id": "P01",
      "events_path": "data/teachers/T_.../skills/v2/eval_runs/P01_run1.json",
      "observed_pedagogy": { ... },
      "n_runs": 3,
      "consistency_per_run": 0.94
    }
  ],
  "consistency": {
    "declared_observed": 0.85,
    "cross_probe": 0.92,
    "cross_layer": 0.78
  },
  "overall_grade": "B+",
  "grade_reasoning": [
    "declared_observed = 0.85 (≥ 0.7 ✅)",
    "cross_probe = 0.92 (≥ 0.8 ✅)",
    "cross_layer = 0.78 (≥ 0.7 ✅, but humor 与 declared 偏离 0.18)",
    "综合: B+"
  ],
  "recommendations": [
    "Skill 在 P03 误区提醒题上 observed != declared，建议补充对应转写语料"
  ]
}
```

---

## 6. 硬性要求（不可妥协）

> ⚠️ 以下要求是模块**入门红线**，code review 不通过的 PR 拒绝合并。

| # | 硬性要求 | 验证方法 |
|---|---|---|
| H1 | `skill_profile_v2.json` 必须通过 `schemas/skill_profile_v2.schema.json` 校验 | CI 自动跑 |
| H2 | `TeacherSkill.md` 必须包含 7 段且非空 | 自动语法检查 |
| H3 | `TeacherSkill.md` 必须含 `<!-- pedagogy:declared ... -->` 注释块 | 自动检查 |
| H4 | LLM scoring 调用 temperature **必须 ≤ 0.3** | code review |
| H5 | 第一层指纹评分 LLM 必须 **n_runs ≥ 3** 取均值；方差 > 0.15 时降低 confidence | 自动测试 |
| H6 | 第二层 pedagogy enum 必须从 `enums.py` 取，禁止硬编码字符串 | 静态扫描 |
| H7 | grade < B 时返回 `warnings` 包含 `"low_grade_soft_reject"` 标志 | 自动测试 |
| H8 | 蒸馏失败必须 fallback 到上一版 Skill（如存在），不删除已有版本 | 集成测试 |
| H9 | 不允许调用 M3/M4/M5/M6 代码 | 静态扫描 import |
| H10 | crowd 反馈融合公式: `value = auto * w_a + crowd * w_c`，权重必须从 config 读取，禁止 magic number | code review |
| H11 | 写文件原子（tmp + rename） | code review |
| H12 | 不允许修改已发布的 Skill 版本（v1, v2 一旦写入只读） | 文件权限 + 集成测试 |
| H13 | 跑探针时调 M4 emitter 必须 mock 或注入；禁止反向依赖 M4 | 静态扫描 |

---

## 7. 验收标准

### 7.1 MVP（Phase 1 结束时）

| # | 指标 | 标准 | 测试方法 |
|---|---|---|---|
| A1 | 蒸馏成功率 | ≥ 90% | 10 个真实教师 transcript 测试 |
| A2 | `skill_profile_v2.json` schema 通过率 | 100% | CI |
| A3 | 第一层评分跨语料稳定性（同教师两份语料相关性 r）| > 0.6 | 至少 5 教师 × 2 段语料 |
| A4 | 第一层评分 LLM 重复跑稳定性（n=3 标准差）| < 0.15 | 自动测试 |
| A5 | 第二层 declared 解析准确率 | 100% | 注释块格式严格 |
| A6 | 单 Skill 蒸馏端到端时长 | < 10 min | 不含探针 |
| A7 | 含探针完整评测时长 | < 20 min | |
| A8 | grade 分布合理性 | A:B:C:D 不超过 5:30:50:15 | 至少 30 教师后统计 |

### 7.2 Phase 1 → Phase 2 升级

| # | 指标 | Phase 2 标准 |
|---|---|---|
| A1 | 蒸馏成功率 | ≥ 99% |
| A3 | 跨语料稳定性 r | > 0.8 |
| A4 | LLM 重复稳定性 | < 0.10 |
| A6 | 蒸馏时长 | < 5 min |
| A9 | declared vs observed 一致性 | > 0.85 |
| A10 | crowd 反馈接入 | ✅ |

### 7.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A11 | 跨语料稳定性 r | > 0.9 |
| A12 | 蒸馏时长 | < 2 min |
| A13 | grade 分布与人工评估相关性 | > 0.7 |

---

## 8. 与其他模块的接口

### 8.1 输入来源

| 来源 | 内容 | 协议 | 文件路径 |
|---|---|---|---|
| **M1 ingest** | `teacher_transcript.json` | 文件读取 | `data/teachers/{tid}/transcripts/*.json` |
| **M5 feedback** | `feedback.json` | 文件读取（异步轮询） | `data/sessions/*/feedback.json` |
| **M6 platform** | 触发蒸馏（异步任务）| Python 函数调用 | — |

### 8.2 输出去向

| 去向 | 内容 | 协议 | 文件路径 |
|---|---|---|---|
| **M3 catalog** | `skill_profile_v2.json` | 文件读取 | `data/teachers/{tid}/skills/v{n}/skill_profile_v2.json` |
| **M3 catalog** | `eval_report.json`（grade）| 文件读取 | 同上目录 |
| **M4 orchestrator** | `TeacherSkill.md` | 文件读取 | 同上目录 |
| **M4 orchestrator** | declared pedagogy（嵌入 md 注释）| 解析 md | 同上 |
| **M6 platform** | 任务进度 | `query_progress(task_id)` | — |

### 8.3 接口契约一致性自检

| 检查点 | 状态 |
|---|---|
| ✅ 读 M1 输出路径 `data/teachers/{tid}/transcripts/` | 与 M1 §3.2 一致 |
| ✅ teacher_id 命名 `T_<YYYYMMDD>_<seq>` | 与总体方案 §5.2 一致 |
| ✅ skill_id 命名 `S_<teacher_id>_v<n>` | 与总体方案 §5.2 一致 |
| ✅ `skill_profile_v2.json` schema 与总体方案 §6.4 一致 | 字段逐项核对 |
| ✅ `pedagogy` enum 与总体方案 §6.2 一致 | 字段逐项核对 |
| ✅ 异步任务进度规范与总体方案 §4.3.4 一致 | status/progress 字段 |
| ✅ 调用 M4 emitter 跑探针：通过依赖注入，避免循环依赖 | 见 §6 H13 |

---

## 9. 关键技术挑战与实现指导

### 9.1 第一层 6 维评分的双通道设计

**通道 A：LLM Scoring**
- prompt 模板：固定结构 + few-shot examples
- 必须 n=3 取均值（H5）
- temperature ≤ 0.3（H4）
- 输出 JSON Schema 强约束（用 Anthropic 的 tool_use 或 OpenAI structured output）

**通道 B：统计特征**
- 字数/分钟、问号占比、平均句长、term-density
- 算法稳定，但表达力弱

**融合策略**：
- 主用通道 A（信号丰富）
- 通道 B 作为 sanity check：若两通道偏差 > 0.3，confidence 降权 0.5

### 9.2 第二层探针测试的循环依赖处理

**问题**：M2 要测试 Skill，需要跑 events 生成（M4 的能力）。

**解决方案**：
- M4 的 `emitter.generate()` 函数对 M2 暴露
- M2 通过依赖注入调用，不直接 import M4 模块
- 测试时用 mock emitter，避免 LLM 成本

```python
# good
def evaluate_skill(..., emitter_fn: Callable | None = None):
    emitter = emitter_fn or _default_emitter()
    ...

# bad
from modules.M4_orchestrator.emitter import emitter  # 反向依赖
```

### 9.3 grade 计算公式

```python
def compute_grade(consistency: dict) -> str:
    c1 = consistency["declared_observed"]
    c2 = consistency["cross_probe"]
    c3 = consistency["cross_layer"]
    
    # 红线检查
    if c1 < 0.7 or c2 < 0.8 or c3 < 0.7:
        if min(c1, c2, c3) < 0.5:
            return "D"
        return "C"
    
    # 综合分
    score = c1 * 0.4 + c2 * 0.4 + c3 * 0.2
    if score >= 0.93: return "A"
    if score >= 0.88: return "A-"
    if score >= 0.83: return "B+"
    if score >= 0.78: return "B"
    if score >= 0.73: return "B-"
    return "C+"
```

### 9.4 Skill 版本管理

- 触发新版本：转写新增 / crowd 反馈累积 ≥ 30 / 教师手动重训
- 自动 v1, v2, v3
- `teacher_card.current_skill_version` 指向当前默认版本
- 不可变性（H12）：旧版本只读

### 9.5 探针题库设计（必须学科可参数化）

```json
{
  "probe_id": "P01",
  "name": "concept_explain",
  "template": "请讲一下 {topic} 这个概念",
  "topic_pool": {
    "高等数学": ["极限", "导数", "积分"],
    "机器学习": ["过拟合", "梯度下降"],
    "通用": ["X"]
  },
  "expected_dimensions_to_test": ["concept_entry", "intuition_building"]
}
```

---

## 10. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| LLM 评分不稳定 | 高 | 高 | H4 低温 + H5 多次取均值；通道 B sanity check |
| 跨教师不可比（auto 分整体偏高/低）| 高 | 高 | Phase 0 用 30 个 mock transcript 校准基线分布 |
| 探针 LLM 调用成本 | 中 | 中 | 缓存：同 Skill 同 probe 不重复跑；非首次蒸馏可跳过探针 |
| Skill 蒸馏失败但旧版本被覆盖 | 高 | 高 | H8 + H12 双重保护 |
| Humor auto 评分不准 | 高 | 中 | 允许 humor.value=null + confidence:low；UI 提示 |
| crowd 刷分（教师自己刷好评）| 中 | 中 | 加权前过滤：单 IP / 单设备节流；至少完成 1 次 session 才能评 |
| 探针题库与教师学科不匹配 | 中 | 中 | topic_pool 含"通用" topic 兜底 |

---

## 11. 本地开发与测试

### 11.1 快速跑通

```bash
python modules/M2_distill/run.py \
  --teacher-id T_20260515_001 \
  --transcripts data/teachers/T_20260515_001/transcripts/TR_001.json \
  --output data/teachers/T_20260515_001/skills/v2/ \
  --teacher-name 示例老师 \
  --subject 高等数学 \
  --skip-probe-eval   # 首次开发跳过昂贵的探针
```

### 11.2 必须提供的测试

```text
tests/
  test_distill.py             # 主流程
  test_fingerprint.py         # 6 维评分（H4 H5）
  test_pedagogy.py            # declared 解析 + observed 推理
  test_qa.py                  # 一致性 + grade
  test_schema.py              # H1
  test_idempotency.py         # 同一 transcript 多次蒸馏（不同版本号）
  test_no_circular_dep.py     # H13
  fixtures/
    transcript_short.json     # 简短测试
    transcript_full.json      # 完整 30 分钟
    expected_profile.json     # 期望 skill_profile_v2 输出
```

### 11.3 CI 检查项

- skill_profile_v2.schema.json 校验
- TeacherSkill.md 7 段检查
- pedagogy 注释块解析
- 跨教师 auto 评分基线漂移监控（每周）

---

## 12. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | 编写 `schemas/skill_profile_v2.schema.json` | jsonschema 校验通过 |
| 2 | 在 `_common.py` 上扩展 prompt v2（含 pedagogy 注释块） | 现有蒸馏跑出新格式 |
| 3 | 实现 `extract_fingerprint()` 框架（先返回 dummy 分） | M3 能 mock 调用 |
| 4 | 实现 `pedagogy_inferer.declared_parser` 完整解析 | 100% 准确 |
| 5 | 创建 `data/eval_probes/` 目录 + 5 个标准 probe 题目 | M4 emitter 能跑 |
| 6 | 与 M1 owner 对齐 transcript 路径 | 双方 README 互相引用 |
| 7 | 与 M3 owner 对齐 skill_profile_v2 字段 | M3 能反序列化 |

---

**END OF M2 DOCUMENT**

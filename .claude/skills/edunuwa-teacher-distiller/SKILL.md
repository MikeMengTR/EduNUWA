---
name: edunuwa-teacher-distiller
description: |
  从教师授课转写文本中蒸馏「讲解风格」，产出符合 EduNUWA api_contract 的 TeacherSkill.md。
  输入：teacher_transcript.json 路径
  输出：TeacherSkill.md（七段契约）+ skill_profile.json（元数据）
  触发词：「蒸馏教师讲解风格」「distill teacher skill」「生成 TeacherSkill」「教师风格蒸馏」。
  适用场景：已通过 ASR 获得教师转写，需将其讲课方式提炼为可被下游 Agent 调用的 Skill 文件。
---

> **Derived from**: [huashu-nuwa](https://github.com/alchaincyf/nuwa-skill) by alchaincyf, MIT License.
> **Modifications**: 输入从「人名网络调研」改为「本地教师转写文本」；
> 提炼维度从「心智模型 / 表达 DNA / 智识谱系」改为「8 项教学维度」；
> 输出契约严格对齐 EduNUWA `docs/api_contract.md §3`。详细 diff 见 [NOTICE.md](NOTICE.md)。

# EduNUWA Teacher Distiller · 教师讲解风格蒸馏

> 「课程知识负责讲什么，TeacherSkill 负责怎么讲。」

## 核心理念

本 Skill 不复刻教师的声音、外貌或身份，而是**提炼教师讲解课程时的认知与表达模式**：

- 教师面对一个新概念时，**先讲什么、再讲什么**？（讲解流程）
- 教师如何**用类比建立直觉**？（类比方式）
- 教师**何时落笔板书、写什么不写什么**？（板书策略）
- 教师讲公式时，**先写还是先讲，逐项还是整体**？（公式讲法）
- 教师有什么**口头禅、互动方式、停顿节奏**？（口吻特征）
- 教师如何**提醒易错点**？（易错点提醒）
- 教师如何**做阶段总结**？（总结方式）
- 教师**绝不会做什么**？哪里是这个 Skill 的**诚实边界**？

**关键区分**：捕捉的是 HOW they teach，不是 WHAT they said。

---

## 执行流程

### Phase 0: 输入校验

收到调用请求后立即执行：

1. **必需输入**：
   - `transcript_path`: 转写文件路径（JSON，符合 `docs/api_contract.md §2`）
   - `output_dir`: TeacherSkill.md 输出目录
2. **可选输入**：
   - `teacher_name`: 教师标识（用于 `skill_profile.json`）
   - `subject`: 学科（数学 / 物理 / 编程 / ...）
3. **校验项**：
   - 转写文件存在且可读
   - JSON 含 `segments` 数组，每段有 `text`
   - segments 数 < 30 → 标记为「语料偏少模式」，质量验证阈值放宽
   - 总文本长度 < 3000 字 → 提醒调用方「样本不足，建议补语料」
4. **顺带统计**（供 Phase 2.6.2 base_metrics 与 attributes.corpus_stats 用）：
   - 总字数 `C`（去标点）、segments 数 `N`
   - 总语音时长 `D` = `Σ(segment.end - segment.start)`（若有时间戳；无则记 `no_timestamps`）

校验失败 → 直接返回 `{"status": "error", "message": "...", ...}`，不进入后续 Phase。

---

### Phase 1: 转写阅读与切分

读取 `teacher_transcript.json`，按教学语义将 segments 聚成若干「教学片段」：

| 片段类型 | 识别信号 |
|---|---|
| 概念引入段 | 「我们今天来看…」「先来想一个问题…」「假设…」 |
| 直觉建立段 | 类比、举例、生活化场景、画图描述 |
| 形式定义段 | 「定义为…」「记作…」「公式是…」 |
| 推导 / 解释段 | 公式逐项展开、步骤陈述、推理链 |
| 例题段 | 「来看一道题」「比如…」「举个例子」 |
| 易错点段 | 「注意」「不要…」「常见错误是」「很多同学会…」 |
| 总结段 | 「所以…」「小结一下」「记住三件事」「这一节我们学了」 |

**输出（仅内部使用，不落盘）**：标注好类型的 segments 列表 + 每个类型的频次统计 + 占比。

**目的**：让后续提炼有"证据可指"，每条结论都能引用至少 2 处转写片段。

---

### Phase 1.5: 阅读检查点

在 Phase 2 开始前展示给调用方：

```
┌──────────────────────┬──────────┬──────────────────────────┐
│ 阅读检查点           │           │                          │
├──────────────────────┼──────────┼──────────────────────────┤
│ Segments 总数         │ N        │                          │
│ 总时长（如有时间戳）   │ Xs       │                          │
│ 总文本长度            │ N 字      │                          │
│ 概念引入段            │ k        │ 占比 X%                   │
│ 直觉建立段            │ k        │ 占比 X%                   │
│ 形式定义段            │ k        │ 占比 X%                   │
│ 例题段                │ k        │ 占比 X%                   │
│ 易错点段              │ k        │ 占比 X%                   │
│ 总结段                │ k        │ 占比 X%                   │
├──────────────────────┼──────────┼──────────────────────────┤
│ 语料质量评级          │ 充足 / 偏少 / 不足                  │
└──────────────────────┴──────────┴──────────────────────────┘
```

仅在交互模式下展示；后端集成调用模式（`run_demo_pipeline()`）跳过展示直接进入 Phase 2。

---

### Phase 2: 八项教学维度提炼

逐维度提取，每条结论附 ≥2 条**转写原文证据**（用引号或行号标注）。

#### 2.1 教学哲学（Teaching Philosophy）

教师反复强调的「为什么这样讲」信念。
- 至少需要 1 条核心信念，最多 3 条
- 每条以一句话表述，附转写引证
- 例：「先建立直觉再给定义」「公式只是表达，含义才是骨架」

#### 2.2 讲解模式（Explanation Pattern）

教师讲一个新概念时的**实际**步骤序列（从转写中观察出来的，不是模板套出来的）。
- 通常 5–8 步
- 每步说明「这一步的目的」+ 「教师典型句式」
- 例：
  ```
  Step 1 提出问题 / 现象（句式：「先想一个场景…」）
  Step 2 用类比建立直觉（来源领域：日常生活 / 已学知识）
  Step 3 给出形式定义
  Step 4 解释定义中每一项的含义
  Step 5 举一道最简单的例子
  Step 6 提醒易错点
  Step 7 阶段小结
  ```

#### 2.3 类比方式（Analogy Style）

- 类比的**主要来源领域**（日常生活 / 几何图像 / 已学知识 / 编程类比 / ...）
- 类比与形式定义的**先后**关系（类比在前 vs 类比在后）
- 类比频率（粗估：每讲 N 个新概念出现 1 次）
- 至少 2 条具体类比示例（直接引用转写）

#### 2.4 板书策略（Blackboard Policy）

板书在课堂中**写什么、不写什么**：
- 必写：标题、关键定义、公式、推导关键步、对比表、易错提醒、阶段总结
- 不写：完整口播文本、闲聊、铺垫
- 时机：教师说出哪类句式时通常落笔（例如「我把它写出来」「关键是这一步」）
- 推荐 `board` 事件的常见 action：
  - `write_title` / `write_subtitle`
  - `write_bullets`（要点列表）
  - `write_steps`（推导或流程步骤）
  - `write_summary`（阶段总结）
  - `highlight`（强调易错点）
  - `clear_board`（切到下一段）

#### 2.5 公式讲法（Formula Strategy）

- 顺序偏好：**先写后讲** / **先讲后写** / **边讲边写**
- 解释方式：**逐项展开** / **整体几何意义** / **从特例到一般**
- 公式与板书的关系：是否一律入板书？是否伴随对比表？
- 至少 1 条公式讲解的转写引证

#### 2.6 口吻特征（Speech Policy）

- 口头禅 / 高频词（按出现次数排序，列前 5 个）
- 句式偏好：长句 vs 短句、陈述 vs 设问
- 互动方式：是否反问？是否设置「停下来想一想」节点？
- 停顿习惯：典型停顿前的句式（用以驱动 `pause` 事件）
- 例：
  ```
  口头禅：「我们来看」「记住一件事」「不急」
  高频反问：「你觉得这是为什么？」
  停顿信号：「先停一下」「想一想」 → 触发 pause 事件
  ```

#### 2.7 易错点提醒（Pitfall Reminder）

- 提醒模式：**显式声明**（「注意」「常见错误是」） vs **反例驱动**（先做错再纠正）
- 提醒时机：**讲完定义即提醒** vs **做完例题后回顾**
- 提醒后是否落板书（通常是）

#### 2.8 总结方式（Summary Style）

- 阶段总结 vs 整体总结的句式差异
- 总结密度（粗估：每 N 分钟 1 次阶段总结）
- 总结是否落板书（什么形式：bullets / 表格 / 一句话）

---

### Phase 2.5: 提炼确认检查点

向调用方展示提炼摘要：

```
提炼结果摘要：
- Teaching Philosophy: N 条
- Explanation Pattern: N 步
- Analogy Style: N 个示例
- Blackboard Policy: N 条规则 + N 个 action
- Formula Strategy: 顺序偏好 = …
- Speech Policy: 口头禅 = […]，反问频率 = …
- Pitfall Reminder: N 个模式
- Summary Style: N 条规则
- 引用证据条数：M（来自 K 个转写片段）
```

交互模式下等待确认；批处理模式直接推进 Phase 2.6。

---

### Phase 2.6: v2 指标产出（八维 → style_tags + base_metrics + pedagogy）

> 这是 v2.0 的核心新增。八项教学维度（Phase 2）是**原料**，本阶段把它们映射成三类下游可消费的结构。三类各司其职：**风格用开放标签、客观量用数字、教学法用 enum**（见 `docs/modules/skill_descriptor_matching_spec.md`）。

#### 2.6.1 风格标签 `style_tags`（开放形容词，给 M3 语义匹配）

把八维里**主观、描述风格**的部分提炼成**开放形容词短语**（不是照搬维度名，是凝练成"学生会用来形容这位老师"的词）。每个标签：

- `text`：自然语言形容词，不限词表（如「设问自答」「娓娓道来」「爱用生活类比」「板书极简」）
- `dimension`：可选软归类（pace / detail / abstraction / interactivity / humor / rigor / null）
- `source`：固定 `"auto"`（蒸馏来源）
- `confidence`：你对该标签的提炼置信度 0.0–1.0（**不是 support，auto 标签直接用此值**）
- `evidence`：**≥1 条转写 seg 证据**（硬约束，无证据的标签直接丢弃）

映射示例（八维 → 标签）：

| 八维来源 | 提炼出的 style_tag.text | dimension |
|---|---|---|
| Speech Policy「设问自答为主，每环节先抛问」 | 设问自答、引导思考 | interactivity |
| Speech Policy「中等偏短句、口语化」 | 节奏明快、好跟随 | pace |
| Analogy Style「生活化类比贯穿」 | 爱用生活类比、接地气 | abstraction |
| Blackboard Policy「只写骨架不写口播」 | 板书极简、重点突出 | detail |
| Pitfall Reminder「主动拦截误区」 | 主动防错、替学生踩坑 | rigor |
| Teaching Philosophy「先直觉后定义」 | 重直觉、先感受后形式 | abstraction |

**数量**：6–16 个标签，覆盖该教师最鲜明的风格特征。宁缺毋滥——每个必须有转写证据。

> 注意：**不要在这里算 embedding，也不要写 cluster_id**。embedding 由 Python 侧（M2 metric_extractor/embedding.py）在你产出 text 后统一计算；`cluster_id` 一律写 `null`（全局簇归 M3）。

#### 2.6.2 基础指标 `base_metrics`（客观数字，给精确筛选）

只放**客观可计算**的量。用 Bash/工具读转写 JSON 计算：

- `speech_rate`：总字数 ÷ 有效语音时长（分钟）。字数 = 去标点的中文/英文字符数；时长 = `Σ(segment.end - segment.start)`（不含段间停顿）。
- `question_freq`：设问句数 ÷ (总时长/10分钟)。设问判定：句末「？」或含疑问词（吗/呢/怎么/为什么/是不是/会不会）。
- `info_density`（可选）：不重复新概念数 ÷ 时长（分钟）。

每个指标产出 `{value, unit, label, polarity}`。`label`/`polarity` 查对照表（语速：<180「偏慢」slow / 180-280「适中」mid / >280「偏快」fast）。

> 若转写无时间戳（`segment.start/end` 缺失），`speech_rate` 等无法计算 → 该项省略，并在 `warnings` 标注 `"no_timestamps"`。

#### 2.6.3 教学法 `pedagogy`（5 维 enum，给 M4 当讲课指令）

从八维**反推** 5 个 enum 维度（这是给 AI 执行的离散策略，不是给学生看的）：

| pedagogy 维度 | enum 取值 | 从哪个八维推 |
|---|---|---|
| `concept_entry.primary` | problem-driven / phenomenon-driven / definition-first / contrast-driven / history-driven | Explanation Pattern 第一步 |
| `intuition_building.order` | intuition-first / formal-first / interleaved | Teaching Philosophy + Pattern 顺序 |
| `analogy_density.level` | high / medium / low / zero | Analogy Style 频率 |
| `blackboard_strategy.primary_layout` | title-bullets / derivation-flow / comparison-table / mind-map / minimal | Blackboard Policy |
| `misconception_alert.mode` | proactive-explicit / proactive-implicit / reactive-only / absent | Pitfall Reminder |

**enum 值必须从上表取，不得自创字符串。** 不确定时选最接近的，并在 confidence/warnings 标注。

---

### Phase 3: TeacherSkill.md 组装

按 `docs/api_contract.md §3` 严格组装为 7 段：

```markdown
# TeacherSkill: <teacher_name 或 generic>

## Skill Purpose
本 Skill 用于将 <teacher_name> 的讲解思维迁移到新的课程讲解任务中。
（一句话表达本 Skill 的迁移目标）

## Trigger
当用户请求概念解释、公式推导、例题讲解、知识点对比、复习总结时调用。
（可在此追加学科特化触发词）

## Teaching Philosophy
（来自 Phase 2.1，每条附转写引证）

## Explanation Pattern
（来自 Phase 2.2，分步骤列表，每步含目的 + 典型句式）

## Blackboard Policy
（来自 Phase 2.4，含「写什么 / 不写什么 / 推荐 action」三块）

## Speech Policy
（来自 Phase 2「口吻特征」子项，含口头禅、句式、互动模式、停顿信号）

## Output Contract
本 Skill 驱动的下游 Agent 必须输出结构化教学事件：
- 事件类型：`speak / board / formula / table / pause / quiz`
- 事件 schema 严格遵循 `docs/api_contract.md §5`
- speak 事件文本必须体现 Speech Policy
- board 事件 action 须从 Blackboard Policy 中的推荐列表选取
- 不得输出未声明类型的事件
- 不得在 speak 文本中嵌入 board 内容（应拆为独立事件）
```

#### 在 `Explanation Pattern` 段后追加机器可读注释块（M4 的 declared pedagogy 来源）

将 Phase 2.6.3 反推的 5 维 enum 写成注释块嵌入 `TeacherSkill.md`（紧跟 Explanation Pattern 段）：

```markdown
<!-- pedagogy:declared
{
  "concept_entry":       { "primary": "problem-driven", "signature_phrase": "好，那我们今天来看一个问题：…" },
  "intuition_building":  { "order": "intuition-first", "intuition_source": ["daily-life"], "before_formal": true },
  "analogy_density":     { "level": "high", "per_concept": 1, "domain_pool": ["生活场景"] },
  "blackboard_strategy": { "primary_layout": "title-bullets", "write_timing": "after-speak", "minimal_text": true },
  "misconception_alert": { "mode": "proactive-explicit", "timing": "after-example" }
}
-->
```

> M2 的 `pedagogy_inferer/declared_parser.py` 直接解析此块，无需二次 LLM。enum 值必须来自 Phase 2.6.3 的合法集合。

> 💡 类比方式、公式讲法、易错点提醒、总结方式作为 Explanation Pattern 与 Blackboard Policy 的子项嵌入，避免段落碎片化。

#### 同步生成 `skill_profile.json`（v2.0 结构）

> 严格对齐 `modules/M2_distill/schemas/skill_profile_v2.schema.json`。这是 M3/M4 消费的契约文件，字段名/结构不得偏离。

```json
{
  "skill_id": "S_<teacher_id_compact>_v<n>",
  "teacher_id": "<teacher_id>",
  "teacher_name": "<teacher_name>",
  "version": <n>,
  "generated_at": "<ISO8601>",

  "style_tags": [
    { "text": "设问自答", "dimension": "interactivity", "source": "auto",
      "confidence": 0.8, "evidence": ["seg_0002", "seg_0012"], "cluster_id": null },
    { "text": "爱用生活类比", "dimension": "abstraction", "source": "auto",
      "confidence": 0.85, "evidence": ["seg_0004", "seg_0005"], "cluster_id": null }
  ],
  "style_embeddings_model": "bge-base-zh-v1.5",

  "base_metrics": {
    "speech_rate":   { "value": 165, "unit": "字/分", "label": "偏慢", "polarity": "slow" },
    "question_freq": { "value": 4.2, "unit": "次/10分钟", "label": "时常提问", "polarity": "mid" }
  },

  "pedagogy": {
    "concept_entry":       { "primary": "problem-driven" },
    "intuition_building":  { "order": "intuition-first", "intuition_source": ["daily-life"], "before_formal": true },
    "analogy_density":     { "level": "high", "per_concept": 1 },
    "blackboard_strategy": { "primary_layout": "title-bullets", "write_timing": "after-speak", "minimal_text": true },
    "misconception_alert": { "mode": "proactive-explicit", "timing": "after-example" }
  },

  "quality": {
    "overall_grade": "NA",
    "publishable": false
  },

  "attributes": {
    "subject": "<subject>",
    "language": "zh",
    "corpus_stats": { "transcripts_count": <N>, "total_duration_sec": <D>, "total_text_chars": <C> }
  },

  "derived_from": "edunuwa-teacher-distiller (fork of huashu-nuwa)"
}
```

> **关于 `quality`**：本 Skill 只做蒸馏，**不跑探针**（探针属 M2 `skill_qa`，需依赖注入 M4）。所以蒸馏阶段产出 `overall_grade: "NA"`、`publishable: false`、**省略 `stability`**（schema 允许）。grade 由 M2 后续 `evaluate_skill()` 跑完探针后回填重写。
>
> **`style_embeddings_model`**：填 M2 config 指定的模型名（默认 `bge-base-zh-v1.5`）。embedding 向量本身由 Python 侧计算，本 Skill 只标注用了哪个模型。
>
> **不再产出旧字段**：`dimensions_covered` / `dimensions_weak` / `evidence_count` 等已废弃，改由 `style_tags`（带 evidence）+ `quality` 表达。

---

### Phase 4: 蒸馏内自检（轻量，非探针评测）

> **职责边界**：本 Skill 只做**蒸馏产物的结构自检**，**不做** declared-vs-observed 探针评测（那是 M2 `skill_qa` 的事，需依赖注入 M4，产出 `quality.stability` + grade）。所以这里产出的 `quality.overall_grade="NA"`。下面 4.1/4.2 是可选的轻量自检（用于交互模式给用户信心），4.3 是必做的结构校验。
>
> 自检**不要 spawn 子 agent**——直接在当前流程内做结构检查即可（spawn 子 agent 做自评上下文开销大，属反模式；真正的独立评测交给 M2 的探针）。

#### 4.1 风格一致性测试

- 从转写中随机挑 1 个概念片段
- 让带着新 Skill 的 agent 重讲这个概念
- 与原转写片段对比：讲解模式是否一致？类比类型是否同源？口头禅是否出现？

#### 4.2 跨知识点迁移测试

- 选 1 个**转写未覆盖**的新概念
- 让带着新 Skill 的 agent 讲解
- 期望：仍体现 Explanation Pattern 与 Speech Policy；不应"塌回"通用 ChatGPT 风格

#### 4.3 多模态契约一致性测试

- 调用下游 `generate_teaching_events()` 生成事件流
- 校验：
  - 全部事件类型 ∈ `{speak, board, formula, table, pause, quiz}`
  - 全部 board 事件的 action ∈ Blackboard Policy 推荐列表
  - speak 文本不夹带板书内容
  - 至少出现 1 次 `pause`（如 Speech Policy 中识别出停顿信号）

#### 4.4 通过标准（结构自检）

| 检查项 | 通过标准 | 不通过信号 |
|---|---|---|
| style_tags 证据 | 每个 style_tag 都有 ≥1 条 evidence | 出现无证据标签（必须丢弃）|
| style_tags 数量 | 6–16 个，覆盖主要风格 | < 3 个（语料不足，标 warning）|
| base_metrics | 有时间戳时 speech_rate 等已计算 | 无时间戳标 `no_timestamps` |
| pedagogy enum | 5 维全部取自合法 enum 集合 | 出现自创字符串 |
| declared 注释块 | TeacherSkill.md 含 `<!-- pedagogy:declared -->` | 缺失 |
| skill_profile schema | 通过 `skill_profile_v2.schema.json` 校验 | 字段缺失/类型错 |
| TeacherSkill.md 7 段 | 7 段齐全 | 缺段 |
| Output Contract 段 | 存在且事件类型完整 | 缺失或不全 |

迭代上限：Phase 2 → 4 最多循环 2 次。2 轮后仍有不达标项 → 在 `skill_profile.json` 的 `warnings` 标注弱项（如 `zero_style_tags` / `no_timestamps`），并在 `Speech Policy` 末尾补「诚实边界」说明，交付当前最优版本（继承上游女娲的 60 分原则）。

---

## 集成约定（与 EduNUWA 项目对接）

本 Skill 通常由后端函数调用，签名遵循 `docs/api_contract.md §7.2`：

```python
distill_teacher_skill(
    transcript_path: str,
    output_dir: str,
    config: dict | None = None,   # {"teacher_name": ..., "subject": ..., "interactive": False}
) -> dict
```

返回示例：
```json
{
  "status": "success",
  "skill_md": "data/teachers/<tid>/skills/v<n>/TeacherSkill.md",
  "skill_profile": "data/teachers/<tid>/skills/v<n>/skill_profile.json"
}
```

> 产出的 `skill_profile.json` 遵循 v2.0 结构（`style_tags` + `base_metrics` + `pedagogy` + `quality{grade:NA}` + `attributes`，见 Phase 3）。质量 grade 与 `stability` 由 M2 后续 `evaluate_skill()` 跑探针后回填。

调用方负责在 `ClaudeAgentOptions` 中通过 `cwd` 或 `add-dir` 让本 Skill 被发现。

---

## 工具调用约定（Tool Conventions, Windows 友好）

执行 Phase 4 自检脚本或任何辅助命令时，必须遵守：

- **统一用 `python` 而非 `python3`**：Windows + Anaconda 环境下没有 `python3` 命令，只有 `python`。
  - ✅ `python scripts/quality_check.py SKILL.md`
  - ❌ `python3 scripts/quality_check.py SKILL.md`
- **优先 PowerShell 而非 Bash**：本仓库 `.claude/settings.json` allowlist 显式只放行 `Bash(python *)`，调用 `Bash(python3 *)` 会被拒绝。Agent 在 Windows 下可优先选 `PowerShell` 工具，自动规避 shell 兼容差异。
- **路径使用 `${CLAUDE_SKILL_DIR}` 占位**：脚本相对路径写 `${CLAUDE_SKILL_DIR}/scripts/foo.py`，避免 hardcode 绝对路径。

---

## 诚实边界（Honest Limits）

本 Skill 的固有局限，必须如实告知用户：

1. **不能复制教师本人**：仅迁移讲解模式，不复刻声音、外貌、个人经历。
2. **不能预测教师面对全新学科的反应**：风格在熟悉学科与陌生学科之间可能漂移。
3. **公开授课 vs 私下讲解可能有差**：转写来自正式课堂，非正式辅导风格未涵盖。
4. **语料偏少时质量打折**：< 30 segments 或 < 3000 字时，多个维度可能无法稳定提取。
5. **风格相似 ≠ 教学有效**：本 Skill 优化"像不像"，不直接优化"学生学得好不好"。
6. **截至语料采集时间**：教师近期风格变化（如换教法、换教材）未反映。

---

## 绝不做的事

- 编造教师没出现过的口头禅或类比
- 把通用教学常识包装成「这位教师的独特讲法」
- 在语料不足时强行凑齐 8 个维度
- 跨学科盗用其他教师的特征（如把数学教师的几何类比塞给文科教师）
- 输出非 `api_contract.md §3` 七段结构的 TeacherSkill.md
- 输出未声明类型的教学事件

---

## 致谢

本 Skill 的方法论结构（多维度提炼、检查点确认、诚实边界、迭代上限、60 分原则）来自 [huashu-nuwa](https://github.com/alchaincyf/nuwa-skill) (MIT License, by 花叔)，在此致谢。范式迁移与教学维度重构由 EduNUWA Team 完成，详见 [NOTICE.md](NOTICE.md)。

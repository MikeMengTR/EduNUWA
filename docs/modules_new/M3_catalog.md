# M3 · Catalog 教师目录 + 双轨匹配 — 详细方案 v2.0

> **上游依赖**：M2 (Distill) — `skill_profile_v2.json`（含开放风格标签 + 基础指标 + 质量 grade）、`style_tags_live.json`（学生反馈沉淀的 crowd 标签）、`eval_report.json`；M6 (Platform) — `teacher_card.json`、账号体系
> **下游消费者**：M6 frontend_student — 调用 catalog HTTP API
> **关联文档**：`docs/EduNUWA_v2_总体方案.md` §3.3/§4.3、`docs/modules/skill_descriptor_matching_spec.md`（评价体系 = M3 匹配的数据基础）
> **版本**：v2.0 · 2026-06-04
>
> **v2.0 范式变更（相对 v1.0）**：风格匹配从「6 维 0-1 数值 + 区间过滤 + 多维距离」改为「开放形容词标签 + 向量语义召回 + LLM 精排」。学生用自然语言描述想要的老师，系统语义匹配。数值只保留在少数客观基础指标（语速等）。**继承不变**：双轨设计、不返综合评分红线、只读、teacher_card 消费、grade 软拒绝、`/api/v1/` + `{code,message,data}`。

---

## 1. 模块定位与边界

### 1.1 一句话定位

让学生通过 **"人找人"**（按真实姓名/口碑）和 **"风格找人"**（用自然语言或标签描述想要的风格）两条路径发现教师，靠**大模型语义理解**完成匹配并给出可解释的推荐理由。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 教师列表 / 详情 / 搜索 | 教师 CRUD（M6 写数据库）|
| 自然语言风格搜索（语义召回 + 精排）| Skill 蒸馏 / 标签提炼（M2 做）|
| 标签语义匹配 + 基础指标数字筛选 | 教学事件生成（M4 做）|
| 推荐排序 + 推荐理由 | 综合评分 / 排行榜（违背双轨设计）|
| grade 软拒绝（< B 默认折叠）| 修改 Skill / 写回标签（M2 做）|
| 合并读 auto 标签（快照）+ crowd 标签（实时）| 写入 `data/teachers/{tid}/`（只读）|
| 维护标签向量索引 | 学生评价采集（M6 做）|

### 1.3 核心价值

- **M3 是产品的发现入口**：决定"风格找人"路径能不能成立。
- **M3 是语义匹配层**：把学生的自然语言需求与教师的开放风格标签在同一语义空间对齐。
- **M3 是数据汇聚层**：把 M2 的 skill_profile + crowd 标签 + M6 的 teacher_card 拼成可消费视图。

---

## 2. 子模块与文件结构

```text
modules/M3_catalog/
  teacher_catalog/
    repository.py        # 聚合读取：skill_profile(auto标签) + style_tags_live(crowd) + teacher_card
    indexer.py           # 构建标签向量索引 + 基础指标结构化索引
    cache.py             # LRU 缓存
  matching_engine/
    query_parser.py      # Stage A：自然语言 → 结构化意图（LLM）
    recall.py            # Stage B：向量语义召回 + 基础指标数字筛选 + 硬过滤
    reranker.py          # Stage C：LLM 语义精排 + 生成推荐理由
    embedding.py         # embedding 客户端（查询/标签向量，与 M2 同模型）
    degrade.py           # LLM 不可用时的降级路径（标签倒排 + 数字排序）
  api/
    routes.py            # FastAPI 路由
    schemas.py           # Pydantic 模型
    serializers.py       # profile + 标签 → 前端视图（含标签分组展示）
  README.md
  run.py                 # 本地启动 catalog 服务
  tests/
    test_query_parser.py
    test_recall.py
    test_rerank.py
    test_api.py
    test_degrade.py
    test_soft_reject.py
    fixtures/mock_teachers/   # ≥ 10 个教师，含 auto + crowd 标签
```

> 相对 v1.0：`scorer.py`（数值距离）→ 删除；新增 `query_parser / recall / reranker / embedding / degrade`。

---

## 3. 详细接口

### 3.1 HTTP API 总览

所有 API 前缀 `/api/v1/`，遵循总体方案 §4.3。

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/teachers` | 教师列表（分页）|
| GET | `/api/v1/teachers/{teacher_id}` | 教师详情 |
| POST | `/api/v1/teachers/search` | 双轨搜索（核心 API）|
| GET | `/api/v1/teachers/{teacher_id}/skills` | 教师所有 Skill 版本 |
| GET | `/api/v1/catalog/facets` | 可筛选项元信息（标签簇 / 学科 / 基础指标档位）|

### 3.2 核心 API：`POST /api/v1/teachers/search`

支持**三种输入形态**，统一走一套匹配管线：

#### 形态 1 · 自然语言（风格找人的主入口）

```json
{
  "mode": "by_style",
  "query_text": "想找个讲题像讲故事、不那么死板、语速慢一点的高数老师",
  "page": 1, "page_size": 20
}
```

#### 形态 2 · 结构化（标签 + 基础指标，简化入口 / 无需 LLM 解析）

```json
{
  "mode": "by_style",
  "style_tags": ["讲故事式", "幽默"],
  "base_filter": { "speech_rate": "slow" },
  "subject": "高等数学",
  "min_grade": "B",
  "page": 1, "page_size": 20
}
```

#### 形态 3 · 人找人

```json
{ "mode": "by_name", "name": "示例老师", "page": 1, "page_size": 20 }
```

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `mode` | enum | 是 | `by_name` / `by_style` / `mixed` |
| `query_text` | string | 形态1 | 自然语言需求；触发 Stage A 解析 |
| `style_tags` | array | 否 | 学生直接选的风格标签（跳过 Stage A）|
| `base_filter` | object | 否 | 基础指标筛选，如 `{"speech_rate":"slow"}` 或 `{"speech_rate":{"max":180}}`|
| `name` | string | mode=by_name | 模糊匹配 real_name / display_name |
| `subject` | string | 否 | 学科精确匹配（硬过滤）|
| `min_grade` | enum | 否 | 默认 B |
| `include_low_grade` | bool | 否 | 默认 false |
| `page`, `page_size` | int | 否 | 默认 1, 20；max 100 |

> 不再有 `fingerprint_filter`（6 维数值区间已废弃）。风格通过 `query_text` 或 `style_tags` 表达。

#### 响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "total": 47,
    "page": 1,
    "page_size": 20,
    "parsed_intent": {
      "style_intent": ["讲故事式", "不死板"],
      "base_pref": { "speech_rate": "slow" },
      "hard_filters": { "subject": "高等数学" }
    },
    "results": [
      {
        "teacher_id": "T_20260515_001",
        "display_name": "示例老师",
        "subject": ["高等数学"],
        "avatar": { "pixel_url": "...", "live2d_model_id": "..." },
        "style_tags": [
          { "text": "讲题像讲故事", "source": "crowd", "support": 23 },
          { "text": "偶尔自嘲", "source": "crowd", "support": 11 },
          { "text": "娓娓道来", "source": "auto" }
        ],
        "base_metrics": {
          "speech_rate": { "value": 165, "label": "偏慢" },
          "question_freq": { "value": 4.2, "label": "时常提问" }
        },
        "skill_grade": "B+",
        "match": {
          "semantic_fit": 0.91,
          "reason": "这位老师被 23 位学生评价为「讲题像讲故事」，与你想要的讲故事风格高度契合，且语速偏慢。",
          "matched_tags": ["讲题像讲故事"]
        },
        "stats": { "total_sessions": 142, "avg_rating": 4.3 }
      }
    ],
    "degraded": false
  }
}
```

| 响应字段 | 说明 |
|---|---|
| `parsed_intent` | Stage A 解析结果，回显给前端（可让学生确认/微调）|
| `style_tags` | 教师的风格标签，含 source（auto/crowd）+ support，前端可标"N 位学生这么评价"|
| `base_metrics` | 基础指标数字 + 文字 label |
| `match.semantic_fit` | 对**该学生需求**的贴合度，不是教师绝对总分（守 H1）|
| `match.reason` | LLM 生成的推荐理由（H：必须引用真实标签，不许幻觉）|
| `match.matched_tags` | 命中的标签，前端可高亮 |
| `degraded` | true = LLM 不可用，本次是降级结果（纯召回排序）|

### 3.3 教师详情 API：`GET /api/v1/teachers/{teacher_id}`

```json
{
  "code": 0, "message": "ok",
  "data": {
    "teacher_id": "T_20260515_001",
    "real_name": "示例老师", "display_name": "示例老师", "bio": "...",
    "subject": ["高等数学", "线性代数"],
    "avatar": { ... }, "voice_id": "...",
    "current_skill_version": 2,
    "style_tags": {
      "by_cluster": [
        { "cluster_id": "narrative", "rep": "讲故事式",
          "tags": [ {"text":"讲题像讲故事","source":"crowd","support":23} ] },
        { "cluster_id": "pace_slow", "rep": "慢节奏",
          "tags": [ {"text":"娓娓道来","source":"auto"} ] }
      ]
    },
    "base_metrics": { "speech_rate": {"value":165,"label":"偏慢"}, ... },
    "pedagogy": { ... 5 维 enum，详情页展示用 ... },
    "quality": { "overall_grade": "B+", "stability": { ... } },
    "stats": { "total_sessions": 142, "avg_rating": 4.3, "rating_distribution": [3,5,18,56,60] }
  }
}
```

> 详情页标签**按簇分组**展示（同义标签归一），每个标签显示 source 和 support，让学生一眼看出"哪些是学生公认的、哪些是系统提炼的"。

### 3.4 元信息 API：`GET /api/v1/catalog/facets`

```json
{
  "code": 0,
  "data": {
    "popular_tag_clusters": [
      { "cluster_id": "narrative", "rep": "讲故事式", "teacher_count": 18 },
      { "cluster_id": "humor_selfdeprecating", "rep": "自嘲式幽默", "teacher_count": 7 }
    ],
    "base_metrics": [
      { "key": "speech_rate", "label": "语速",
        "bands": [ {"label":"偏慢","range":[0,180]}, {"label":"适中","range":[180,280]}, {"label":"偏快","range":[280,null]} ] }
    ],
    "subjects": ["高等数学", "线性代数", "机器学习"],
    "grades": ["A","A-","B+","B","B-","C+","C","C-","D"]
  }
}
```

> 用于前端构造筛选 UI：热门标签簇（让学生点选）+ 基础指标档位 + 学科。标签簇由 M3 周期聚类得到（见 §6）。**`base_metrics` 的 bands（数字↔label 档位）不在 M3 自定义，直接读 M2 的 `rubric/base_metrics_bands.json`（唯一 SSOT），避免 M2 算 label、M3 展示 range 两边漂移。**

### 3.5 内部 Python 接口（M6 调用）

```python
def search_teachers(query: dict) -> dict          # 对齐 POST /search
def get_teacher_detail(teacher_id: str) -> dict   # 对齐 GET /teachers/{id}
def list_teacher_skills(teacher_id: str) -> dict
def reload_index() -> dict                         # 新教师/新 Skill 入库时重建索引
def refresh_tag_clusters() -> dict                 # 周期聚类，更新标签簇 + 别名图谱
```

---

## 4. 输入文件契约

### 4.1 来自 M2 — `skill_profile_v2.json`（蒸馏快照，跟版本）

M3 **必须使用**：

```json
{
  "skill_id": "S_T20260515001_v2",
  "teacher_id": "T_20260515_001",
  "version": 2,
  "style_tags": [                          // 开放风格标签扁平列表（auto 来源）
    { "text": "娓娓道来", "dimension": "pace", "source": "auto",
      "confidence": 0.7, "evidence": ["seg_0003"], "cluster_id": null },
    { "text": "偶尔自嘲", "dimension": "humor", "source": "auto",
      "confidence": 0.4, "evidence": ["seg_0028"], "cluster_id": null }
  ],
  // ↑ M2 产出态：cluster_id=null（M3 召回后内存态才回填全局簇）；MVP 无 embedding_ref（M3 现算）
  "style_embeddings_model": "bge-base-zh-v1.5",   // 与 M3 查询同模型（H6, 768 维）
  "base_metrics": {                        // 基础指标（数字 + label）
    "speech_rate":   { "value": 165, "unit": "字/分", "label": "偏慢", "polarity": "slow" },
    "question_freq": { "value": 4.2, "unit": "次/10分钟", "label": "时常提问", "polarity": "mid" }
  },
  "pedagogy": { "...": "5 维 enum" },        // 详情页展示
  "quality": { "overall_grade": "B+", "publishable": true, "stability": { "...": "三件套" } }
}
```

> **M3 消费的是扁平 `style_tags` 列表**，与 M2 §5.2 / `skill_profile_v2.schema.json` 一致；`dimension` 是可选软归类（可为 null）。M3 加载时对 auto 标签（此处）与 crowd 标签（§4.2）的 `text` **现算 embedding**（MVP 不依赖 `embedding_ref`，见 §6.1），统一进向量索引；全局 `cluster_id` 由 M3 自己回填（§6.3），M2 文件里恒为 null。

**M3 不使用**（M2 内部审计）：`style_tags[*].evidence`（蒸馏证据，详情页 admin 可选）、`attributes.corpus_stats`。

### 4.2 来自 M2 — `style_tags_live.json`（crowd 标签，跨版本累积）

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

> M2 产出态：`cluster_id=null`（M3 回填全局簇）；MVP 无 `embedding_ref`（Phase 2 才持久化）。字段集见 `style_tags_live.schema.json`。

> **M3 合并读**：把 skill_profile 的 auto 标签 + style_tags_live 的 crowd 标签合成教师的完整标签集。crowd 优先级高（见 §5.2 confidence）。文件不存在（新老师无反馈）时只用 auto。

### 4.3 来自 M6 — `teacher_card.json`

M3 **必须使用**：`real_name`、`display_name`、`subject`、`bio`、`avatar.*`、`voice_id`、`current_skill_version`、`stats`。

### 4.4 契约一致性自检

| 检查点 | 状态 |
|---|---|
| skill_profile_v2 的 `style_tags` / `base_metrics` / `quality` 字段与 M2 schema 一致 | 字段名核对 |
| `style_embeddings_model`（顶层字符串）与 M3 查询 embedding **同模型同版本**，bge-base-zh-v1.5 = 768 维（H6）| 显式核对 |
| `style_tags_live.json` 结构与 `style_tags_live.schema.json` 一致 | schema 校验 |
| teacher_card 字段与总体方案 §5.5 一致 | 字段名核对 |
| grade 枚举 `A/A-/B+/B/B-/C+/C/C-/D` 与 M2 一致 | 一致 |
| `/api/v1/` + `{code,message,data}` | 与 §4.3 一致 |

---

## 5. 匹配引擎（核心，三阶段）

```
请求
  │
  ├─ mode=by_name → 名字模糊匹配（不走风格管线）
  │
  └─ mode=by_style / mixed:
      │
      ▼ Stage A · 意图解析（仅 query_text 形态触发；LLM 一次）
      │   query_text → { style_intent[], base_pref{}, hard_filters{} }
      │   （形态2 已是结构化，跳过）
      │
      ▼ Stage B · 召回（无 LLM，确定性）
      │   1. 硬过滤：subject / grade≥min / base_pref 数字筛选
      │   2. style_intent → embedding → 向量召回教师标签（命中一个标签=命中整簇）
      │   3. 候选分 = Σ(标签语义相似度 × 标签 confidence)
      │   → Top-K（默认 K=30）
      │
      ▼ Stage C · 精排（LLM 一次批量；不可用则降级）
      │   输入：学生原话 + K 个教师的标签 + base_metrics
      │   输出：每人 semantic_fit + reason + matched_tags
      │
      ▼ 按 semantic_fit 排序 → 分页返回
```

### 5.1 Stage A 解析（`query_parser.py`）

LLM 把自然语言拆成三部分：
- `style_intent`：风格关键词（保留学生原话，走标签语义匹配）
- `base_pref`：客观基础偏好（语速/互动等，走数字筛选）
- `hard_filters`：学科/语言/grade 等硬条件

不臆测学生没表达的维度；解析结果在响应里回显（`parsed_intent`），前端可让学生确认。

### 5.2 Stage B 召回（`recall.py`）— 替代 v1.0 的数值距离

**先硬过滤再语义召回**：
1. 硬过滤：`subject` 精确 + `grade ≥ min_grade`（软拒绝）+ `base_pref` 数字范围
2. 语义召回：`style_intent` 每个词算 embedding，与教师标签向量算余弦相似度；**相似度 ≥ `recall_threshold`（默认 0.6，config 可调）** 视为命中（MVP 无显式簇，靠余弦本身命中近义；Phase 2 有簇后命中一个=命中整簇）
3. 候选分排序（取相似度命中的标签，按下式累加），**取 Top-K（默认 K=30，config 可调）进精排**：

```
candidate_score(teacher) = Σ_over_matched_tags ( cosine_sim(intent, tag) × effective_weight(tag) )
effective_weight(tag) = source_weight[tag.source] × tag.confidence
  source_weight: crowd = 1.0, auto = 0.6, self = 0.3   # ← 来源权重在 M3 召回侧施加
                 # crowd 学生公认最高 > auto 系统提炼 > self 教师自述（不抗操纵，最低）
  tag.confidence: 由 M2 算好直接用，不重算       # auto=LLM置信度(不走support饱和)；crowd=support饱和×recency
```

> **关键（避免冷启动硬伤）**：`tag.confidence` 直接用 M2 给的值，M3 **不对 auto 标签重算 support 饱和**——否则新教师 auto 标签(support=1) confidence≈0.18×0.6≈0.11，系统性排不进 Top-K。auto/crowd 的 confidence 在 M2 §9.5 已分流算好。M3 只额外乘 `source_weight`（让 crowd 学生公认 > auto 系统提炼）。取 Top-K 进精排。

### 5.3 Stage C 精排（`reranker.py`）— MVP 可选

> **MVP 默认不调 LLM 精排**：直接用 Stage B 候选分排序 + 模板 reason（"命中标签：X、Y"）。精排作为**增强项**，在显式开启或缓存未命中时才调 LLM。这把"每次搜索调 LLM"从必走变成可选，大幅降低目录服务的延迟与并发成本。

开启精排时，LLM 批量读「学生原话 + K 个教师标签 + base_metrics」，输出每人：
- `semantic_fit` ∈ [0,1]：对**该学生需求**的贴合度
- `reason`：一句话推荐理由（展示用）
- `matched_tags`：命中的标签（**结构化字段，H9 防幻觉只校验这个**，不去 NLP 解析 reason 句子）

**精排缓存**：缓存键 = `(归一化 style_intent, 候选集标签版本)`——用 Stage A 解析出的归一化意图，**不用原始 query_text**（原文千变万化命中率极低）。

精排 prompt 硬约束：**贴合度 = 贴近学生偏好，不是找最优老师**——换不同偏好得到不同 Top（守 H1）。base_metrics 与主观标签冲突时分别陈述，不强行调和。

---

## 6. Embedding 与标签索引

### 6.1 embedding 模型（M2/M3 必须一致）

- **MVP 标签向量运行时现算**：M3 加载 skill_profile + style_tags_live 时，对每个标签 `text` 用本模型 batch 编码（内存全表 < 1000 教师，秒级）。**不依赖 M2 持久化的 `embedding_ref`**（那是 Phase 2 上向量库后的句柄）。
- 查询向量由 M3 实时计算（Stage B）。
- 模型版本来自 skill_profile 的 **`style_embeddings_model`** 字段（顶层字符串，非嵌套）。
- **硬约束（H6）**：标签向量与查询向量必须**同一 embedding 模型同一版本**，否则向量不在同一空间。MVP 选型 `bge-base-zh-v1.5`（中文、可离线、**768 维**）。**部署建议**：M2/M3 共用一个轻量 embedding 微服务（单点），天然保证同模型、省一份模型驻留资源。模型升版触发全量标签重算。

### 6.2 向量索引方案（分阶段）

| 阶段 | 教师规模 | 方案 |
|---|---|---|
| MVP | < 1000 | 内存全表：所有标签向量入内存，查询时全量余弦 |
| Phase 2 | < 10万 | FAISS 内存索引（IndexFlatIP / IVF）|
| Phase 3 | 更大 | 专用向量库（Milvus/Qdrant）+ 标签倒排混合 |

### 6.3 标签聚类（别名归并）— 全局簇唯一归 M3（Phase 2）

> **职责归属（关键）**：全局 `cluster_id` + 别名图谱**唯一由 M3 拥有**。M2 只在单个教师内做近义合并（写 `cluster_id=null`），不产全局簇——否则 M2（看单教师局部）和 M3（看全库）各算一套 cluster_id 必然语义漂移。

`refresh_tag_clusters()`（Phase 2）周期跑：对全库标签聚类（同义归一），产出 `cluster_id` + 别名图谱 + 每簇代表词，**存 M3 自己的索引/缓存**（不写回 `data/teachers/`，守 H11 只读）。用于：召回时命中一个=命中整簇；详情页按簇展示；facets 暴露热门簇。聚类是**事后归并**，不限制标签用词（守开放词汇原则）。

> MVP 不做全局聚类：召回靠 embedding 余弦相似度本身就能命中近义标签（"慢条斯理"召回"娓娓道来"），无需显式簇。聚类是 Phase 2 的展示/召回增强。

---

## 7. 降级与可用性（新增，关键）

M3 现在依赖 LLM（Stage A/C）。LLM 不可用时**不能整体不可用**，按以下降级（`degrade.py`）：

| 故障 | 降级路径 | 响应标记 |
|---|---|---|
| Stage A LLM 失败/超时 | 若有 `style_tags` 结构化输入则直接用；否则按关键词分词当 style_intent | `degraded:true` |
| Stage C LLM 失败/超时 | 跳过精排，用 Stage B 候选分排序；reason 用模板（"命中标签：X、Y"）| `degraded:true` |
| embedding 服务失败 | 退回标签**倒排索引**集合匹配（精确词命中）+ base_metrics 数字排序 | `degraded:true` |
| **教师零标签**（语料极少，M2 标 `zero_style_tags`）| 该教师 by_style 召回为空 → 回退按 `base_metrics` + grade + popularity 排序，仍可见 | — |
| **查询召回为空**（无任何标签命中）| 回退 base_metrics + grade + popularity（复用宽泛需求分支）| — |

LLM **超时**（非失败而是慢）按失败处理：超过阈值即降级，不傻等。降级结果仍可用、仍守双轨；前端据 `degraded` 提示"快速匹配模式"。

---

## 8. 硬性要求（不可妥协）

| # | 硬性要求 | 验证 |
|---|---|---|
| H1 | **不返回综合评分/排行榜**；`semantic_fit` 是"对该学生的贴合度"，换偏好结果须变 | code review + 测试 |
| H2 | 双轨 `by_name` / `by_style` 必须在**同一** search API 实现，不拆 endpoint | API review |
| H3 | 风格标签响应必须带 `source`（auto/crowd）；crowd 标签带 `support`（auto 无 support 字段，前端据 source 区分"学生公认"vs"系统提炼"）| 自动测试 |
| H4 | grade < `min_grade` 默认不返回（`include_low_grade=false`）| 自动测试 |
| H5 | 匹配必须是**语义召回 + 精排**，不得退化为对标签数量的加权求和当总分 | code review |
| H6 | 标签向量与查询向量**同 embedding 模型同版本**；模型版本写进契约 | 启动校验 + code review |
| H7 | 索引/聚类重建必须**原子**：新索引就绪后切换，不中断查询 | 集成测试 |
| H8 | LLM/embedding 不可用必须**降级可用**，并在响应标 `degraded` | 故障注入测试 |
| H9 | 防幻觉：精排输出的 **`matched_tags` 必须 ⊆ 该教师标签集**（校验结构化字段，不 NLP 解析 reason 句子）；reason 仅展示 | 自动测试（matched_tags ⊆ 标签集）|
| H10 | 标签稀疏（新老师只有少量 auto 标签）不得 crash，仍能被召回 | 自动测试 |
| H11 | 只读：禁止写 `data/teachers/{tid}/` | 文件权限 |
| H12 | 禁止反向依赖 M2/M4/M5 代码；只通过文件读 M2 输出（LLM/embedding 属外部服务，不算模块依赖）| 静态扫描 |
| H13 | 错误响应统一 `{code, message, data:null}` | 自动测试 |
| H14 | 搜索 API p95 按形态分档：①结构化形态（无 query_text，全程无 LLM）< 300ms；②自然语言形态（含 1 次 Stage A 解析 LLM）< 1.5s；③再开 Stage C 精排（+1 次 LLM）仍 < 1.5s | 性能测试 |

> H14 说明：延迟取决于走几次 LLM。**结构化形态**（form 2：直接给 style_tags/base_filter）全程无 LLM，< 300ms，与 v1.0 同级。**自然语言形态**（form 1：query_text）必走 Stage A 解析 LLM（§5.1），吃不到 300ms，目标 < 1.5s。Stage C 精排默认关（§5.3），开启或缓存未命中才再加一次 LLM。不要把 Stage A 的 LLM 成本漏算进 300ms 档。

---

## 9. 验收标准

### 9.1 MVP（Phase 1）

| # | 指标 | 标准 |
|---|---|---|
| A1 | 三种输入形态（自然语言 / 结构化 / 人找人）均可用 | ✅ |
| A2 | 自然语言"我想要讲故事式的慢节奏老师"能召回对味教师 | ✅ |
| A3 | 近义词召回：学生说"慢条斯理"能召回标"娓娓道来"的老师 | ✅ |
| A4 | crowd 标签优先于 auto（support 高的排前）| ✅ |
| A5 | 软拒绝低 grade | ✅ |
| A6 | reason 无幻觉（引用真实标签）| 自动测试 100% |
| A7 | LLM 关闭仍能降级返回结果 | ✅ |
| A8 | 详情页标签按簇分组 + source/support | ✅ |
| A9 | 索引 ≥ 100 教师；结构化形态 p95 < 300ms，自然语言形态 < 1.5s（H14 分档）| 性能测试 |
| A10 | 错误处理符合规范 | 100% |

### 9.2 Phase 2

| # | 指标 | 标准 |
|---|---|---|
| A11 | FAISS 向量索引，教师 ≥ 1000，p95 < 800ms | ✅ |
| A12 | 周期标签聚类 + 别名图谱生效 | ✅ |
| A13 | 解析准确率（30 条自然语言，意图方向正确）≥ 85% | ✅ |
| A14 | Top-30 召回率（人工标注相关教师）≥ 90% | ✅ |

### 9.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A15 | 多轮澄清（"再活泼一点"）增量调整结果 | ✅ |
| A16 | 个性化推荐（结合学习历史）| ✅ |

---

## 10. 与其他模块接口

### 10.1 输入

| 来源 | 内容 | 协议 |
|---|---|---|
| M2 distill | `skill_profile_v2.json`（含 style/embeddings/base_metrics/quality）| 文件读 |
| M2 distill | `style_tags_live.json`（crowd 标签）| 文件读 |
| M6 platform | `teacher_card.json` | 文件读 |
| M6 platform | 触发 `reload_index()` / `refresh_tag_clusters()` | Python 调用 |
| 外部 | embedding 服务（本地模型）、LLM（解析/精排）| 服务调用 |

### 10.2 输出

| 去向 | 内容 | 协议 |
|---|---|---|
| M6 frontend_student | 列表 / 详情 / 搜索结果 + 推荐理由 | HTTP REST |
| M6 frontend_student | facets 元信息 | HTTP REST |

---

## 11. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| 冷启动期教师只有 auto 标签，crowd 为空 → 匹配单薄 | 高 | 中 | auto 标签铺底；运营初期人工补标极端风格教师 |
| 标签近义爆炸 → 召回噪声 | 中 | 中 | 周期聚类归并（§6.3）；展示每簇只显代表词 |
| LLM 精排成本/延迟高 | 中 | 中 | Stage B 压到 K=30 再精排；H8 降级；结果可缓存 |
| LLM 推荐理由幻觉 | 中 | 高 | H9：reason 标签必须 ⊆ 教师标签集，自动校验 |
| embedding 模型 M2/M3 不一致 → 向量空间错位 | 中 | 高 | H6：模型版本写进契约 + 启动校验 |
| 综合分被产品方反复要求 | 高 | 高 | H1 红线 + 双轨设计文档说明 |

---

## 12. 本地开发与测试

### 12.1 快速跑通

```bash
cp -r modules/M3_catalog/tests/fixtures/mock_teachers data/teachers/
python modules/M3_catalog/run.py --port 8001

# 自然语言搜索
curl -X POST http://localhost:8001/api/v1/teachers/search \
  -H 'Content-Type: application/json' \
  -d '{"mode":"by_style","query_text":"想要讲题像讲故事、语速慢的高数老师"}'
```

### 12.2 必须提供的测试

```text
test_query_parser.py    # Stage A 解析方向正确性
test_recall.py          # Stage B 向量召回 + 硬过滤 + crowd 优先
test_rerank.py          # Stage C semantic_fit + reason 无幻觉
test_degrade.py         # H8 LLM/embedding 关闭降级
test_soft_reject.py     # H4
test_no_composite_score.py  # H1 换偏好得不同 Top
test_index_reload.py    # H7 原子
fixtures/mock_teachers/ # ≥10 教师，含 auto + crowd 标签 + base_metrics
```

### 12.3 CI 检查

- API 响应 schema 校验
- reason 标签 ⊆ 教师标签集（H9 防幻觉）
- embedding 模型版本一致性校验（H6）
- 静态扫描 import 不含 M2/M4/M5

---

## 13. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | 用 5 个含 style 标签的 mock skill_profile_v2 验证解析 | 加载不报错 |
| 2 | 选定 embedding 模型（建议 bge-base-zh-v1.5），与 M2 owner 对齐版本 | 双方文档写明同一模型 |
| 3 | 实现 `search_teachers()` 框架 + `by_name` + 结构化 `by_style`（先不接 LLM）| 能跑通 |
| 4 | 接 Stage B 向量召回（内存全表）| 自然语言近义词能召回 |
| 5 | 接 Stage A/C LLM + 降级路径 | LLM 开/关都返回结果 |
| 6 | 与 M2 owner 对齐 `style` / `style_tags_live` / `style_embeddings` 字段 | 双方文档互引 |
| 7 | 与 M6 owner 对齐 teacher_card + reload 触发 | 双方文档互引 |

---

## 14. 实现现状（MVP 已落地，2026-06-04）

> 本节记录实际跑通的匹配模型，区别于上文的「方案/契约」。MVP 走**方案 §5 的简化版**：直接 LLM 语义匹配（不做 embedding 向量召回），适合 demo 规模（几十位老师）。规模化（Phase 2）再补 embedding 召回粗筛。

### 14.1 匹配模型 · matching_engine

| 项 | 说明 |
|---|---|
| **用途** | 学生自然语言需求 → 候选老师按「风格贴合度」排序 + 每位的推荐理由 |
| **实现方式** | `matcher.py`：把学生需求 + N 位老师的 `style_tags`/`base_metrics` 一次性喂 **DeepSeek**（OpenAI 兼容接口），LLM 直接输出排序 JSON。**对应方案三阶段的简化**：MVP 把 Stage A 解析、Stage B 召回、Stage C 精排合并为一次 LLM 调用（demo 规模无需先召回粗筛）|
| **代码结构** | `matching_engine/matcher.py`：`load_teachers(dir)`（从 skill_profile 加载候选）、`match_teachers(query, teachers)`（匹配主函数）、`_call_llm`（DeepSeek 调用）、`_extract_json`（容错解析）。`__init__.py` 导出 `load_teachers`/`match_teachers` |
| **使用方式** | `from modules.M3_catalog.matching_engine import load_teachers, match_teachers`<br>真实数据 demo：`python scripts/demo_match_real.py ["自定义需求"]`（加载 6 位 v2_full）<br>mock demo：`python scripts/demo_match.py` |
| **实际效果** | 6 所高校真实老师，6 个针对性需求 **6/6 精准命中**（贴合度 0.95-1.00），且 2/3 名排序合理。**守 H1**：换不同需求得不同 Top（非排行榜）。**守 H9 防幻觉**：LLM 推荐时会脑补近义标签，`matched_tags ⊆ 老师真实标签集` 的校验自动过滤之（demo 中可见「⚠️ 幻觉标签(已过滤)」）|
| **对接格式** | 输入：`query`(str) + `teachers`(list，每位含 `teacher_id/teacher_name/subject/grade/style_tags/base_metrics`，由 `load_teachers` 从 `skill_profile_v2.json` 抽取)。输出：`{status, query, results:[{teacher_id, teacher_name, semantic_fit, reason, matched_tags, hallucinated_tags}]}`。LLM：DeepSeek `/v1/chat/completions`，flash 是 reasoning 模型需足量 `max_tokens` |

### 14.2 与方案的差异（MVP 简化项，Phase 2 补齐）

| 方案设计（§5/§6） | MVP 现状 | 补齐时机 |
|---|---|---|
| Stage A LLM 解析 + Stage B 向量召回 + Stage C 精排（三阶段）| 合并为一次 LLM 调用 | 老师数 > 几十时，加 Stage B embedding 召回粗筛 |
| bge-base-zh-v1.5 向量召回 | 未用（全量喂 LLM）| Phase 2 |
| 降级路径 `degrade.py` | 未实现（LLM 不可用即失败）| Phase 2 |
| crowd 标签合并读 | 未接（无 crowd 数据）| 依赖 M6 反馈闭环 |
| HTTP API（routes.py）| 未实现（仅 Python 函数）| **后续同学接 API/端到端** |

### 14.3 待后续同学接入

`match_teachers` 已是可直接调用的业务核心。接 API 时：在 `api/routes.py` 包一层 FastAPI，把 `POST /api/v1/teachers/search` 转发到 `match_teachers`，按 §3.2 输出 `{code,message,data}` 即可。`load_teachers` 现读 fixtures 目录，正式环境改为读 `data/teachers/*/skills/v{n}/skill_profile.json`（合并 `style_tags_live.json` 的 crowd 标签）。

---

**END OF M3 DOCUMENT v2.0**

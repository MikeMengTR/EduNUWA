# M3 · Catalog 教师目录 + 双轨匹配 — 详细方案

> **上游依赖**：M2 (Distill) — 提供 `skill_profile_v2.json` + `eval_report.json`；M6 (Platform) — 提供 `teacher_card.json`、账号体系
> **下游消费者**：M6 frontend_student — 调用 catalog HTTP API
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.3、§4.3
> **版本**：v1.0 · 2026-05-15

---

## 1. 模块定位与边界

### 1.1 一句话定位

让学生通过 **"人找人"**（按真实姓名/口碑）和 **"风格找人"**（按风格指标筛选）两条路径发现教师，并提供推荐排序。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 教师列表 / 详情 / 筛选 / 搜索 | 教师 CRUD（M6 写入数据库） |
| 风格指标多维筛选 | Skill 蒸馏（M2 做） |
| 双轨入口在 API 层支持 | 教学事件生成（M4 做） |
| 推荐排序（match_score） | 综合评分 / 排行榜（违背双轨设计） |
| Skill grade 软拒绝（< B 默认折叠） | 修改 Skill 内容 |
| 历史风格变化曲线（Phase 2） | 用户行为埋点（M6 做） |
| 雷达图渲染所需数据 | 直接渲染前端（前端在 M6） |

### 1.3 核心价值

- **M3 是产品的发现入口**：决定"风格找人" 路径能不能成立
- **M3 是数据汇聚层**：把 M2 的 profile 和 M6 的 teacher_card 拼装成可消费的视图

---

## 2. 子模块拆分与文件结构

```text
modules/M3_catalog/
  teacher_catalog/
    repository.py             # 教师数据读取（聚合 M2 profile + M6 card）
    indexer.py                # 内存索引 / SQLite 索引构建
    cache.py                  # LRU 缓存
  matching_engine/
    filter.py                 # 多维区间过滤
    scorer.py                 # match_score 计算
    ranker.py                 # 排序（无综合分）
    recommender.py            # Phase 2: 个性化推荐
  api/
    routes.py                 # FastAPI 路由（接入 M6 backend）
    schemas.py                # Pydantic 模型
    serializers.py            # profile → 雷达图数据
  README.md
  run.py                      # 本地启动 catalog 服务
  tests/
    test_filter.py
    test_scorer.py
    test_api.py
    fixtures/
      mock_teachers/
        T_001/skill_profile_v2.json
        T_001/teacher_card.json
        ...
```

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
| GET | `/api/v1/teachers/{teacher_id}/skills/{version}` | 单个 Skill 详情 |
| GET | `/api/v1/recommend` | 个性化推荐（Phase 2）|
| GET | `/api/v1/catalog/dimensions` | 返回所有可筛选维度元信息（前端构造 UI）|

### 3.2 核心 API：`POST /api/v1/teachers/search`

#### 请求

```json
{
  "mode": "by_style",
  "name": null,
  "fingerprint_filter": {
    "pace":          { "min": 0.0, "max": 0.5 },
    "abstraction":   { "min": 0.0, "max": 0.4 },
    "humor":         { "min": 0.5, "max": 1.0 }
  },
  "tags_include": ["warmth:high"],
  "tags_exclude": [],
  "subject": "高等数学",
  "min_grade": "B",
  "include_low_grade": false,
  "sort_by": "match_score",
  "page": 1,
  "page_size": 20
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `mode` | enum | 是 | `by_name` / `by_style` / `mixed` |
| `name` | string | mode=by_name 时必填 | 模糊匹配 real_name / display_name |
| `fingerprint_filter` | object | 否 | 6 维区间筛选；缺省维度不限制 |
| `tags_include` | array | 否 | tag 必须全部存在 |
| `tags_exclude` | array | 否 | tag 必须不存在 |
| `subject` | string | 否 | 学科精确匹配 |
| `min_grade` | enum | 否 | A / B / C / D，默认 B |
| `include_low_grade` | bool | 否 | 默认 false（低 grade 折叠）|
| `sort_by` | enum | 否 | `match_score` / `popularity` / `newest` / `grade` |
| `page`, `page_size` | int | 否 | 默认 1, 20；max page_size 100 |

#### 响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "total": 47,
    "page": 1,
    "page_size": 20,
    "results": [
      {
        "teacher_id": "T_20260515_001",
        "display_name": "示例老师",
        "subject": ["高等数学"],
        "avatar": { "pixel_url": "...", "live2d_model_id": "..." },
        "fingerprint": {
          "pace": 0.42, "detail": 0.81, "abstraction": 0.25,
          "interactivity": 0.68, "humor": null, "rigor": 0.72
        },
        "fingerprint_confidence": {
          "pace": 0.78, "detail": 0.85, "abstraction": 0.90,
          "interactivity": 0.65, "humor": 0.30, "rigor": 0.80
        },
        "tags": ["warmth:high", "encourage:explicit"],
        "skill_grade": "B+",
        "match_score": 0.87,
        "stats": { "total_sessions": 142, "avg_rating": 4.3 }
      }
    ]
  }
}
```

### 3.3 教师详情 API：`GET /api/v1/teachers/{teacher_id}`

#### 响应

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "teacher_id": "T_20260515_001",
    "real_name": "示例老师",
    "display_name": "示例老师",
    "bio": "...",
    "subject": ["高等数学", "线性代数"],
    "avatar": { ... },
    "voice_id": "...",
    "current_skill_version": 2,
    "skill_profile": {
      "fingerprint": { ... 6 维 + confidence + source ... },
      "pedagogy": { ... 5 维 ... },
      "tags": [...],
      "quality": { "overall_grade": "B+", ... }
    },
    "stats": {
      "total_sessions": 142,
      "avg_rating": 4.3,
      "rating_distribution": [3, 5, 18, 56, 60]
    },
    "fingerprint_history": [
      { "version": 1, "snapshot_at": "...", "fingerprint": {...} }
    ]
  }
}
```

### 3.4 维度元信息 API：`GET /api/v1/catalog/dimensions`

让前端动态构造筛选 UI（避免硬编码）：

```json
{
  "code": 0,
  "data": {
    "fingerprint_dimensions": [
      {
        "key": "pace",
        "label_zh": "节奏",
        "label_en": "Pace",
        "low_label": "慢",
        "high_label": "快",
        "range": [0.0, 1.0],
        "default_filter": [0.0, 1.0]
      }
    ],
    "available_tags": [
      { "key": "warmth:high", "label_zh": "亲和力强", "count": 12 }
    ],
    "subjects": ["高等数学", "线性代数", "机器学习"],
    "grades": ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D"]
  }
}
```

### 3.5 内部 Python 接口（M6 调用）

```python
def search_teachers(query: dict) -> dict:
    """与 POST /api/v1/teachers/search 对齐"""

def get_teacher_detail(teacher_id: str) -> dict:
    """与 GET /api/v1/teachers/{teacher_id} 对齐"""

def list_teacher_skills(teacher_id: str) -> dict:
    """所有 Skill 版本"""

def reload_index() -> dict:
    """新教师 / 新 Skill 入库时调用，重建索引"""
```

---

## 4. 输入文件契约（来自 M2 + M6）

### 4.1 来自 M2

读 `data/teachers/{tid}/skills/v{n}/skill_profile_v2.json`，**必须使用以下字段**：

```json
{
  "skill_id": "S_T20260515001_v2",
  "teacher_id": "T_20260515_001",
  "version": 2,
  "fingerprint": { ... },          // M3 用于筛选 + 雷达图
  "pedagogy": { ... },             // M3 用于详情页展示
  "tags": [...],                   // M3 用于 tag 筛选
  "quality": {
    "overall_grade": "B+",         // M3 用于软拒绝
    "declared_observed_consistency": ...,
    "cross_probe_consistency": ...,
    "cross_layer_consistency": ...
  }
}
```

**M3 不允许使用以下字段**（属于 M2 内部审计）：
- `fingerprint_breakdown`（除非详情页 admin 视图）
- `coverage`（M3 不展示）
- `corpus_stats`（M3 不展示）

### 4.2 来自 M6

读 `data/teachers/{tid}/teacher_card.json`，遵循总体方案 §5.5。

**M3 必须使用**：
- `real_name`, `display_name`, `subject`, `bio`
- `avatar.pixel_url`, `avatar.live2d_model_id`
- `voice_id`, `current_skill_version`
- `stats`

### 4.3 与 M2 / M6 的契约一致性自检

| 检查点 | 状态 |
|---|---|
| ✅ skill_profile_v2 字段使用与 §6.4 schema 一致 | 字段名核对 |
| ✅ teacher_card 字段使用与 §5.5 schema 一致 | 字段名核对 |
| ✅ teacher_id 命名 `T_<YYYYMMDD>_<seq>` | 一致 |
| ✅ grade 枚举 `A/A-/B+/B/B-/C+/C/C-/D` 与 M2 一致 | 一致 |
| ✅ HTTP API 格式（code/message/data）与总体方案 §4.3.2 一致 | 一致 |
| ✅ 路径前缀 `/api/v1/` | 一致 |
| ✅ M3 的 `current_skill_version` 取自 M6 teacher_card，不自己决定 | 字段来源明确 |

---

## 5. 硬性要求（不可妥协）

| # | 硬性要求 | 验证方法 |
|---|---|---|
| H1 | **不允许返回综合评分**（除 match_score 外不能给"教师总分"等加权综合）| code review |
| H2 | 双轨入口 `mode=by_name` 和 `mode=by_style` 必须在同一 API 中实现，不允许拆成两个 endpoint | API 设计 review |
| H3 | 教师详情必须返回 `fingerprint_confidence`，UI 才能区分"可信"vs"待校准" | 自动测试 |
| H4 | grade < `min_grade` 时，默认 `include_low_grade=false`，结果不包含；前端可手动放开 | 自动测试 |
| H5 | match_score 计算公式必须是**多维距离**而非加权和，详见 §9.1 | code review |
| H6 | 不允许写入 `data/teachers/{tid}/`（只读模式）| 文件权限 |
| H7 | 重建索引必须**原子**：新索引就绪后切换，不允许中断查询 | 集成测试 |
| H8 | 列表 / 搜索 API p95 latency < 500ms（MVP）/ < 200ms (Phase 2) | 性能测试 |
| H9 | 必须支持 `humor.value == null` 的 fingerprint，不能 crash | 自动测试 |
| H10 | 禁止反向依赖 M2/M4/M5；只允许通过文件读取 M2 输出 | 静态扫描 |
| H11 | 所有 fingerprint 数值在响应中保留 2 位小数，不要乱舍入 | 自动测试 |
| H12 | 错误响应统一 `{code, message, data: null}` 格式 | 自动测试 |

---

## 6. 验收标准

### 6.1 MVP（Phase 1 结束时）

| # | 指标 | 标准 | 测试方法 |
|---|---|---|---|
| A1 | 教师列表 API p95 latency | < 500ms | k6 / locust |
| A2 | 双轨搜索（by_name + by_style）功能可用 | ✅ | API 集成测试 |
| A3 | 6 维区间筛选可用 | ✅ | 自动测试 |
| A4 | 教师详情含完整 fingerprint + confidence | ✅ | 自动测试 |
| A5 | 软拒绝低 grade Skill | ✅ | 自动测试 |
| A6 | 索引支持 ≥ 100 教师 | ✅ | 性能测试 |
| A7 | 错误处理符合规范 | 100% | 自动测试 |

### 6.2 Phase 1 → Phase 2

| # | 指标 | 标准 |
|---|---|---|
| A1 | API p95 | < 200ms |
| A6 | 教师规模 | ≥ 1000 |
| A8 | 个性化推荐 | ✅ |
| A9 | 历史风格变化曲线 | ✅ |
| A10 | 5+ 个 tag 维度筛选 | ✅ |

### 6.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A1 | API p95 | < 100ms |
| A11 | 自然语言搜索（"我想要慢节奏的老师"）| ✅ |
| A12 | 多教师并发推荐排序 | ✅ |

---

## 7. 与其他模块的接口

### 7.1 输入来源

| 来源 | 内容 | 协议 |
|---|---|---|
| **M2 distill** | `skill_profile_v2.json`, `eval_report.json` | 文件读取 |
| **M6 platform** | `teacher_card.json` | 文件读取 |
| **M6 platform** | 触发 `reload_index()` 当新教师入库 | Python 函数调用 |
| **M5 runtime** | `feedback.json` 聚合后的 stats（avg_rating 等）| 文件读取（间接，由 M6 聚合后再来）|

### 7.2 输出去向

| 去向 | 内容 | 协议 |
|---|---|---|
| **M6 frontend_student** | 教师列表 / 详情 / 搜索结果 | HTTP REST |
| **M6 frontend_student** | 维度元信息 | HTTP REST |
| **M6 backend** | Python 函数（serverless 调用方式）| 函数调用 |

### 7.3 接口契约一致性自检（与 M1-M2-M6 三方）

| 检查点 | 状态 |
|---|---|
| ✅ skill_profile_v2 字段：6 维 fingerprint + 5 维 pedagogy + tags + quality | 字段名、类型、范围逐项核对 |
| ✅ teacher_card 字段使用 | 字段名、类型核对 |
| ✅ HTTP API 响应格式 `{code, message, data}` | 与总体方案 §4.3.2 一致 |
| ✅ 路径 `/api/v1/teachers/*` | 与总体方案 §4.3.1 一致 |
| ✅ 状态码 / 业务码 | 与总体方案 §4.3.3 一致 |
| ✅ 不调用 M2/M4/M5 代码 | 静态扫描 |

---

## 8. 关键技术挑战与实现指导

### 8.1 match_score 计算（H5）

**多维距离公式**：

```python
def match_score(user_pref: dict, teacher_fp: dict) -> float:
    """
    user_pref: { "pace": 0.3, "detail": 0.7, ... }
    teacher_fp: 同上
    
    返回: [0, 1]，1 = 完全匹配
    """
    dims = ["pace", "detail", "abstraction", "interactivity", "rigor"]
    distances = []
    for d in dims:
        if d not in user_pref:
            continue
        if teacher_fp.get(d) is None:  # humor 可能 null
            continue
        distances.append(abs(user_pref[d] - teacher_fp[d]))
    
    if not distances:
        return 0.5
    
    # 用平均距离的反向值（不是加权和）
    return 1.0 - (sum(distances) / len(distances))
```

**禁止**：
```python
# 不能这样做：综合评分会让"双轨设计"退化为"找最高分"
score = pace * 0.2 + detail * 0.2 + ... + rigor * 0.1
```

### 8.2 索引方案

**MVP（< 1000 教师）**：内存全表扫描即可

```python
class TeacherIndex:
    def __init__(self):
        self.teachers: list[TeacherView] = []
        self._lock = RLock()
    
    def reload(self) -> None:
        """原子切换索引（H7）"""
        new_list = self._scan_all_teachers()
        with self._lock:
            self.teachers = new_list
```

**Phase 2（> 1000）**：SQLite + 多维 BTree 索引（按 fingerprint 各维度分桶）

**Phase 3**：向量索引（fingerprint 6 维 → embedding，用 FAISS）

### 8.3 软拒绝逻辑（H4）

```python
GRADE_ORDER = ["D", "C-", "C", "C+", "B-", "B", "B+", "A-", "A"]

def should_show(teacher_grade: str, min_grade: str, include_low: bool) -> bool:
    if include_low:
        return True
    return GRADE_ORDER.index(teacher_grade) >= GRADE_ORDER.index(min_grade)
```

### 8.4 humor null 兼容（H9）

```python
# 筛选时
def passes_humor_filter(t_fp: dict, filt: dict) -> bool:
    if "humor" not in filt:
        return True
    h = t_fp.get("humor")
    if h is None:
        return False  # 不在筛选结果，避免误推荐
    return filt["humor"]["min"] <= h <= filt["humor"]["max"]

# 雷达图渲染时
# 前端将 null 显示为虚线/灰色，由 M6 frontend_student 处理
```

---

## 9. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| 教师都集中在 fingerprint 中段 → 风格筛选失效 | 高 | 高 | M2 校准基线 + 鼓励冷启动期人工标注极端教师 |
| 学生不知道自己想要什么 fingerprint | 高 | 中 | 提供"风格预设"（"考研路线"、"入门路线"），背后还是多维过滤 |
| 综合分被产品需求方反复要求 | 高 | 高 | H1 红线 + 文档说明双轨设计哲学 |
| Skill 频繁版本更新 → fingerprint 抖动 | 中 | 中 | 详情页展示 fingerprint_history（Phase 2）|
| 索引重建期间查询不可用 | 中 | 中 | H7 原子切换 |

---

## 10. 本地开发与测试

### 10.1 快速跑通

```bash
# 准备 mock 数据
cp -r tests/fixtures/mock_teachers data/teachers/

# 启动 catalog 服务（独立）
python modules/M3_catalog/run.py --port 8001

# 测试 API
curl -X POST http://localhost:8001/api/v1/teachers/search \
  -H 'Content-Type: application/json' \
  -d '{"mode":"by_style","fingerprint_filter":{"pace":{"min":0.0,"max":0.5}}}'
```

### 10.2 必须提供的测试

```text
tests/
  test_filter.py              # 多维区间筛选
  test_scorer.py              # H5 match_score 公式
  test_api.py                 # 全部 endpoint
  test_soft_reject.py         # H4
  test_humor_null.py          # H9
  test_index_reload.py        # H7 原子性
  test_no_composite_score.py  # H1
  fixtures/
    mock_teachers/            # ≥ 10 个教师 profile
```

### 10.3 CI 检查项

- API 响应 schema 校验
- 性能基准（500ms p95）
- 静态扫描 import 不含 M2/M4/M5

---

## 11. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | 用 5 个 mock skill_profile_v2.json 验证 schema 解析 | 加载不报错 |
| 2 | 实现 `search_teachers()` 框架 + `mode=by_name` 简单实现 | 能跑通 |
| 3 | 与 M2 owner 对齐 fingerprint / pedagogy 字段 | 双方文档互引 |
| 4 | 与 M6 owner 对齐 teacher_card schema 和 reload_index() 触发时机 | 双方文档互引 |
| 5 | 实现 `GET /api/v1/catalog/dimensions` 元信息 endpoint | 前端能拉到 |

---

**END OF M3 DOCUMENT**

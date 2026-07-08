# M3 · Catalog 教师目录 + 双轨匹配

> 📄 完整方案：[docs/modules/M3_catalog.md](../../docs/modules/M3_catalog.md)
> 📄 总体方案：[docs/EduNUWA_v2_总体方案.md](../../docs/EduNUWA_v2_总体方案.md)

## 子模块

| 子目录 | 职责 | 状态 |
|---|---|---|
| `teacher_catalog/` | 教师数据读取 + 索引构建 + 缓存 | 待开发 |
| `matching_engine/` | 多维区间过滤 + match_score + 推荐 | 待开发 |
| `api/` | FastAPI 路由 + Pydantic schema + 序列化 | 待开发 |

## 核心 HTTP API

```
GET  /api/v1/teachers
GET  /api/v1/teachers/{teacher_id}
POST /api/v1/teachers/search           # 双轨发现（mode: by_name / by_style）
GET  /api/v1/catalog/dimensions
```

详细接口、硬性要求、验收标准见 [`docs/modules/M3_catalog.md`](../../docs/modules/M3_catalog.md)。

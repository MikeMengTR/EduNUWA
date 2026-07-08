# M2 · Distill 风格蒸馏 + 双层指标

> 📄 完整方案：[docs/modules/M2_distill.md](../../docs/modules/M2_distill.md)
> 📄 总体方案：[docs/EduNUWA_v2_总体方案.md](../../docs/EduNUWA_v2_总体方案.md)

## 子模块

| 子目录 | 职责 | 状态 |
|---|---|---|
| `skill_distiller/` | 7 段契约 TeacherSkill.md 生成（Claude SDK + DeepSeek）| 已有，待扩展 v2 prompt |
| `metric_extractor/` | 第一层风格指纹 6 维评分 | 待开发 |
| `pedagogy_inferer/` | 第二层教学法 5 维 declared/observed 推理 | 待开发 |
| `skill_qa/` | 探针测试 + C1/C2/C3 一致性 + grade | 待开发 |
| `schemas/` | `skill_profile_v2.schema.json`（产物 schema 单一真相源） | 待落地 |

## 主入口

```python
distill_teacher_skill_v2(teacher_id, transcript_paths, output_dir, config) -> dict
extract_fingerprint(transcript_paths, config) -> dict
infer_pedagogy(skill_md_path, events_paths, config) -> dict
evaluate_skill(skill_md_path, teacher_id, output_dir, probe_set, config) -> dict
```

详细接口、硬性要求、验收标准见 [`docs/modules/M2_distill.md`](../../docs/modules/M2_distill.md)。

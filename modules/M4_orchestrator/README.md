# M4 · Orchestrator Agent 编排

> 📄 完整方案：[docs/modules/M4_orchestrator.md](../../docs/modules/M4_orchestrator.md)
> 📄 总体方案：[docs/EduNUWA_v2_总体方案.md](../../docs/EduNUWA_v2_总体方案.md)

## 子模块

| 子目录 | 职责 | 状态 |
|---|---|---|
| `course_retriever/` | retrieved_context.md 生成 | 已有（迁自 modules/course_retriever）|
| `planner/` | follow / ondemand 模式状态机 | 待开发 |
| `emitter/` | teaching_events.json 生成 | 已有（迁自 modules/agent_generator）|
| `session_manager/` | session_state.json + 多轮上下文 | 待开发 |
| `schemas/` | teaching_events / session_state JSON schemas | 待落地 |

## 主入口

```python
generate_teaching_events_v2(
    session_id, user_question, teacher_skill_path,
    mode, course_outline_path, output_dir, config
) -> dict

generate_teaching_events_v2_stream(...) -> Iterator[dict]    # SSE

# 探针测试入口（M2 evaluate_skill 通过依赖注入调用）
generate_for_probe(probe_question, teacher_skill_path, config) -> dict
```

详细接口、硬性要求、验收标准见 [`docs/modules/M4_orchestrator.md`](../../docs/modules/M4_orchestrator.md)。

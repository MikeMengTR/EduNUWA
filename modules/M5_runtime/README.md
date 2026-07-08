# M5 · Runtime 学习运行时

> 📄 完整方案：[docs/modules/M5_runtime.md](../../docs/modules/M5_runtime.md)
> 📄 总体方案：[docs/EduNUWA_v2_总体方案.md](../../docs/EduNUWA_v2_总体方案.md)

## 子模块

| 子目录 | 职责 | 状态 |
|---|---|---|
| `tts_service/` | GPT_SoVITS + 兜底 edge_tts | 已有（迁自 modules/tts_service）|
| `player_runtime/` | 前端时间线调度器（TS）| 待开发 |
| `blackboard_frontend/` | 黑板 7 种 action 渲染（React）| 已有（迁自 modules/blackboard_frontend）|
| `live2d_frontend/` | Live2D 数字人 + 嘴型同步 | 已有（迁自 modules/live2d_frontend）|
| `avatar_system/` | 像素 IP 资源 + Live2D 资源管理 | 待开发 |
| `build_playback/` | playback_data.json 构建器 | 待开发 |
| `schemas/` | audio_manifest / playback_data JSON schemas | 待落地 |

## 主入口

```python
generate_tts_batch(events_path, output_dir, voice_id, config) -> dict
build_playback_data(events_path, audio_manifest_path, output_dir, teacher_card_path, config) -> dict
submit_feedback(session_id, student_id, feedback) -> dict
```

```typescript
interface PlayerRuntime {
  load(playback: PlaybackData): Promise<void>;
  play(); pause(); seek(seq); setSpeed(rate);
  on(event, cb); destroy();
}
```

详细接口、硬性要求、验收标准见 [`docs/modules/M5_runtime.md`](../../docs/modules/M5_runtime.md)。

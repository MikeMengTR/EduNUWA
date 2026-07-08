# Stream Module — 流式延迟层

## 定位

在 M4（编排器）和 M5（运行时）之间建立一层"流式延迟层"，使教学事件按 L1-L7 自然节奏输出。

## L1-L7 延迟指标

| 指标 | 名称 | p50 目标 | 配置项 | 建议值 |
|------|------|----------|--------|--------|
| L1 | 首句开口延迟 | ≤ 8s | 首事件强制 board:write_title | — |
| L2 | 句间停顿 | 0.3-0.6s | `l2_sentence_gap_range_sec` | (0.3, 0.6) |
| L3 | 板书写完到接话 | 0.5-1.2s | `l3_board_to_speak_delay_sec` | 0.8s |
| L4 | 段间过渡 | 1.0-2.0s | `l4_segment_gap_sec` | 1.5s |
| L5 | 设问思考停顿 | ≥ 1.5s | `l5_pause_default_ms` | 1500 |
| L6 | 概念切换 | 2.0-3.0s | `l6_concept_switch_gap_sec` | 2.5s |
| L7 | 追问开口 | ≤ 10s | `l7_follow_up_first_utterance_sec` | 10.0s |

## CLI 用法

```bash
# 1. 流式演示 —— 逐 event 打印，显示 gap 和延迟标签
python modules/stream/run.py stream \
  --events modules/M5_runtime/demo/demo_teaching_events.json

# 2. 构建 streaming playback_data.json
python modules/stream/run.py build \
  --events modules/M5_runtime/demo/demo_teaching_events.json \
  --output data/sessions/SES_demo_20260522/ \
  --teacher-card data/teachers/T_20260515_001/teacher_card.json

# 3. 验证 playback_data.json 是否符合 L1-L7
python modules/stream/run.py verify \
  --playback data/sessions/SES_demo_20260522/playback_data.json \
  --events modules/M5_runtime/demo/demo_teaching_events.json

# 4. 自定义延迟配置
python modules/stream/run.py build \
  --events ... --output ... \
  --latency-config '{"l3_board_to_speak_delay_sec": 1.0, "l4_segment_gap_sec": 2.0}'
```

## Python API

```python
from stream import generate_teaching_events_v2_stream, LatencyConfig

# 默认配置
for chunk in generate_teaching_events_v2_stream("events.json"):
    if chunk["chunk_type"] == "event":
        item = chunk["data"]
        print(f"  [{item['start_offset_sec']:5.1f}s] {item['type']}")

# 自定义配置
config = LatencyConfig(
    l3_board_to_speak_delay_sec=1.0,
    l5_pause_default_ms=2000,
)
gen = generate_teaching_events_v2_stream("events.json", latency_config=config)
```

## 与 M5 的集成

`build_streaming_playback()` 输出与 M5 builder 完全同 schema 的 `playback_data.json`。
前端 PlayerRuntime 零改动，直接用。

## 测试

```bash
python -m pytest modules/stream/tests/ -v
```

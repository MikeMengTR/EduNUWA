# M5 · Runtime 学习运行时

EduNUWA v2 的"演出引擎"——把 AI 生成的教案变成有声音、有黑板、有数字人的完整课堂。

---

## 一、项目全局架构

EduNUWA v2 由 6 个核心模块组成：

```
modules/
├── M1_ingest/          素材摄取（音视频→文本+音频样本）
├── M2_distill/         Skill 蒸馏（教学风格提取）
├── M3_catalog/         课程目录管理
├── M4_orchestrator/    编排器（学生提问→教学事件生成）
│   └── streaming_events.py    ← 新增：流式生成器+监控模式
├── M5_runtime/         ★ 学习运行时（本模块）
├── M6_platform/        平台层（API + 前端集成）
└── stream/             新增：流式延迟层（L1-L7 节奏控制）

GPT-SoVITS-v2pro/       TTS 模型（示例老师微调权重 + 推理引擎）
data/                   数据目录（教师卡、Session、音频）
```

### M5 在架构中的位置

```
M1 (素材) ──► M2 (风格)
                  │
M3 (课程) ──► M4 (编排) ──► M5 Runtime ★ (本模块) ──► M6 (前端)
                  │                │
                  └── stream 模块 ──┘  ← L1-L7 节奏 + 监控
```

---

## 二、与其他模块的接口

### 输入（M5 消费的内容）

| 来源 | 内容 | 协议 | 路径 |
|------|------|------|------|
| **M4 Orchestrator** | `teaching_events.json`（6 种事件 + 7 种 board action） | 文件读取 | `data/sessions/{sid}/events/turn_{n}.json` |
| **M1 Ingest** | 参考音频 `*.wav`（用于 voice cloning） | 文件读取 | `data/teachers/{tid}/audio_samples/` |
| **M6 Platform** | `teacher_card.json`（voice_id, avatar） | 文件读取 | `data/teachers/{tid}/teacher_card.json` |
| **M6 frontend_student** | 嵌入 PlayerRuntime 组件 | npm package | — |

### 输出（M5 提供的内容）

| 去向 | 内容 | 协议 | 路径 |
|------|------|------|------|
| **M6 frontend_student** | `playback_data.json`（时间线+音频路径） | 文件读取 | `data/sessions/{sid}/playback_data.json` |
| **M6 frontend_student** | `.wav` 音频文件 | HTTP 静态资源 | `data/sessions/{sid}/audio/turn_{n}/*.wav` |
| **M6 backend** | `feedback.json`（学生评分+教学反馈） | 函数调用 | `data/sessions/{sid}/feedback.json` |
| **M2 Distill** | feedback 统计（间接通过 M6 聚合） | — | 同上 |

### 接口契约（Schema）

| 文件 | Schema 位置 | 说明 |
|------|------------|------|
| `teaching_events.json` | `schemas/teaching_events.schema.json` | 6 种 type 校验 |
| `audio_manifest.json` | `schemas/audio_manifest.schema.json` | TTS 输出索引 |
| `playback_data.json` | `schemas/playback_data.schema.json` | 前端时间线 |

### 流式输入自动监控

系统支持两种监控模式，自动检测新文件并触发处理流程：

**1. Stream 管道监控 (`modules/stream/pipeline.py watch`)**

```
监控 data/sessions/ 目录
  │  每 3 秒轮询
  ▼
发现新文件 data/sessions/{任意}/events/turn_{n}.json
  │
  ▼ 自动执行：
  ├─ Phase 1: 流式输出事件时间线（L1-L7 节奏，秒级完成）
  ├─ Phase 2: 后台 TTS 并行合成
  └─ Phase 3: 合并为 playback_data.json
```

```bash
python modules/stream/pipeline.py watch --dir data/sessions --poll 3
```

**2. M4 请求监控 (`modules/M4_orchestrator/streaming_events.py` watch)**

```
监控 data/requests/ 目录
  │
  ▼
发现新文件 *_request.json
  │  内容: {"user_question": "什么是过拟合？", "mode": "ondemand"}
  ▼
自动生成教学事件 → 写入 events/turn_1.json → 更新 session_state
```

```bash
python -m modules.M4_orchestrator.streaming_events watch --dir data/requests
```

**3. 多会话多批处理演示**

```bash
python modules/stream/demo/multi_session_demo.py
```

模拟 3 份 JSON 在不同时间到达不同 session，系统自动依次处理。

### Stream 模块的桥接作用

`modules/stream/` 连接 M4 和 M5：

```
M4 (教学事件) ──→ stream 模块 ──→ M5 Runtime
                    │
                    ├─ latency_config.py      L1-L7 节奏参数
                    ├─ streaming_orchestrator  逐事件产出，附带节奏标签
                    ├─ playback_builder        合并音频→playback_data
                    └─ pipeline.py / watch    文件监控，自动处理
```

---

## 三、M5 内部结构

```
modules/M5_runtime/
│
├─ tts_service/                   语音合成引擎
│  ├─ gpt_sovits_wrapper.py       GPT-SoVITS 推理封装
│  ├─ tts_engine.py               generate_tts_batch() 主入口
│  ├─ edge_tts_fallback.py        Edge TTS 降级（无 ffmpeg 依赖）
│  ├─ voice_clone.py              参考音频选择（SNR 排序 + 教师隔离）
│  └─ audio_postprocess.py        原子写入 + 时长估算
│
├─ build_playback/builder.py      build_playback_data() 时间线构建
├─ feedback/submit.py             submit_feedback() 反馈提交
├─ auto_train/pipeline.py         自动训练管道（素材→模型→注册）
├─ schemas/                       3 个 JSON Schema
├─ tests/                         30 个单元测试
├─ demo/                          演示脚本
│
└─ frontend/                      React + TypeScript 前端
   └─ src/
      ├─ player_runtime/          纯 TS 播放器
      ├─ blackboard_frontend/     React 黑板组件
      └─ live2d_frontend/         Canvas 数字人 + LipSync
```

---

## 四、已完成的工作

### 4.1 核心函数

| 函数 | 签名 | 所属文件 |
|------|------|---------|
| `generate_tts_batch()` | `(events_path, output_dir, voice_id, config) → dict` | `tts_service/tts_engine.py` |
| `build_playback_data()` | `(events_path, audio_manifest, output_dir, teacher_card, config) → dict` | `build_playback/builder.py` |
| `submit_feedback()` | `(session_id, student_id, feedback) → dict` | `feedback/submit.py` |
| `generate_teaching_events_v2_stream()` | `(events_source, latency_config, ...) → Iterator[dict]` | `stream/streaming_orchestrator.py` |

### 4.2 TTS 合成引擎 (tts_service/)

```
GPT-SoVITS → [文本预处理] → [流式切分] → [逐段合成] → [内容自检] → [WAV 输出]
                              │                 │
                         数学符号→中文        失败→edge_tts 兜底
                         保留英文字母         或调参重试×3
```

**文本预处理**：`²→平方` `√→根号` `½→二分之一`，保留英文字母（需 g2p_en + NLTK cmudict）
**流式切分**：长文本按 `.！？→；：→，` 逐级切为 ≤80 字小块，每块独立合成后拼合
**内容自检**：时长检查 + RMS 能量 + vosk ASR 语音转文字相似度 ≥ 0.85

### 4.3 TypeScript 前端 (frontend/)

```typescript
interface PlayerRuntime {
  load(playback: PlaybackData): Promise<void>;
  play(): void;
  pause(): void;
  seek(seq: number): void;
  setSpeed(rate: number): void;   // 0.75 / 1.0 / 1.25 / 1.5
  on(event: PlayerEvent, cb: Function): void;
  destroy(): void;
}
```

| 组件 | 功能 | 依赖 |
|------|------|------|
| `Player.ts` | 状态机调度器 | — |
| `AudioPlayer.ts` | Web Audio API + AnalyserNode | `AudioContext` |
| `EventScheduler.ts` | rAF + performance.now() 时钟 | — |
| `Blackboard.tsx` | 7 种板书动作 | React |
| `Formula.tsx` | KaTeX LaTeX 渲染 | `katex` |
| `LipSync.ts` | RMS 口型驱动 | AnalyserNode |
| `QuizHandler.ts` | DOM 弹窗 Quiz | — |

### 4.4 Stream 模块 (stream/)

| 文件 | 功能 |
|------|------|
| `latency_config.py` | L1-L7 延迟参数集中配置 |
| `streaming_orchestrator.py` | `generate_teaching_events_v2_stream()` 生成器 |
| `playback_builder.py` | 流式播放数据构建 |
| `pipeline.py` | 自动管道 + 文件监控 |
| `tests/` (23) | L1-L7 合规测试 |

| 指标 | 名称 | 目标 | 实测 |
|------|------|------|------|
| L1 | 首句开口 | ≤ 8s | **3.06s** |
| L2 | 句间停顿 | 0.3-0.6s | 随机化 |
| L3 | 板书→接话 | 0.5-1.2s | 0.8s |
| L4 | 段间过渡 | 1.0-2.0s | 1.5s |
| L5 | 设问思考 | ≥ 1.5s | 强制 1.5s |
| L6 | 概念切换 | 2.0-3.0s | 2.5s |
| L7 | 追问开口 | ≤ 10s | 10s |

### 4.5 M4 流式扩展

| 文件 | 说明 | 状态 |
|------|------|------|
| `modules/M4_orchestrator/streaming_events.py` | 独立流式生成器 + 管道 + 监控模式 | 新增，未改原仓库 |

### 4.6 自动训练管道

```
素材 (音频+标注) → 切片 → BERT/HuBERT/Semantic 特征 → GPT 训练 → SoVITS 训练 → 教师注册
```

---

## 五、数据流

```
M4 Orchestrator (或其他来源)
  │ teaching_events.json (6 种 type, 7 种 board action)
  ▼
Stream 模块 (L1-L7 节奏)
  │ 流式逐事件输出 + 节奏标签
  ▼
TTS 引擎
  │ generate_tts_batch() → GPT-SoVITS → 自检 → WAV
  ▼
build_playback_data()
  │ 合并 events + audio_manifest + teacher_card
  ▼
playback_data.json → 前端 PlayerRuntime
  ├── AudioPlayer → AnalyserNode → LipSync (数字人口型)
  ├── EventScheduler → Blackboard (7 种板书)
  └── QuizHandler → submit_feedback() → feedback.json
```

---

## 六、运行方式

```bash
# 1. TTS 批量合成
python modules/M5_runtime/run.py tts \
  --events data/sessions/{sid}/events/turn_1.json \
  --output data/sessions/{sid}/audio/turn_1/ \
  --voice-id songhao_teacher

# 2. 流式事件输出
python modules/stream/run.py stream \
  --events data/sessions/{sid}/events/turn_1.json

# 3. 文件监控（自动处理新文件）
python modules/stream/pipeline.py watch --dir data/sessions

# 4. 前端播放器
cd modules/M5_runtime/frontend && npm run dev

# 5. 自动训练新教师模型
python -m modules.M5_runtime.auto_train.pipeline run \
  --teacher-name "张三" --audio-dir data/teachers/raw/

# 6. 测试
python -m pytest modules/M5_runtime/tests/ -v
python -m pytest modules/stream/tests/ -v
```

---

## 七、硬性要求覆盖

| # | 要求 | 状态 | 验证方式 |
|---|------|------|---------|
| H1 | 6 种 event type，未知 type fail-loud | ✅ | `test_tts.py` |
| H2 | 7 种 board action | ✅ | `test_tts.py` |
| H3 | Schema 校验通过 | ✅ | `test_tts.py` |
| H4 | TTS 时长 ≤ session × 0.5 | ⚠️ RTF=0.62x，待 GPU 优化 | 性能测试 |
| H5 | Quiz 阻断播放 | ✅ | 前端 QuizHandler |
| H6 | Play/Pause/Seek | ✅ | 前端 Player |
| H7 | 音画同步 < 200ms | ✅ | rAF 单时钟 |
| H8 | TTS 失败降级 edge_tts | ✅ | `test_tts.py` |
| H9 | 不调用 M2/M3/M4 代码 | ✅ | 静态扫描 |
| H10 | 原子写入 (tmp+rename) | ✅ | `test_tts.py` |
| H11 | 多教师 voice_id 不串 | ✅ | `test_concurrent_tts.py` |
| H12 | rating 必填校验 | ✅ | `submit.py` |
| H13 | 参考音频按教师隔离 | ✅ | `test_clone_reference.py` |
| H14 | destroy 释放资源 | ✅ | 前端 Player |

---

## 八、部署依赖

```bash
# Python 核心
pip install torch soundfile numpy

# TTS 降级
pip install edge-tts

# 文本预处理（中英混排）
pip install g2p_en wordsegment
python -c "import nltk; nltk.download('cmudict'); nltk.download('averaged_perceptron_tagger_eng')"

# 内容验证
pip install vosk
python -c "import nltk; nltk.download('punkt')"

# 前端
cd modules/M5_runtime/frontend && npm install

# 模型文件
# GPT-SoVITS-v2pro/（约 31GB，含示例老师微调权重）
# 从网盘下载解压到项目根目录
```

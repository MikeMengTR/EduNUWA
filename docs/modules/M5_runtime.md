# M5 · Runtime 学习运行时 — 详细方案

> **上游依赖**：M4 (Orchestrator) — 提供 `teaching_events.json`；M1 (Ingest) — 提供 `audio_samples/*.wav`；M6 (Platform) — 提供 `voice_id`、`avatar_id`、Live2D 资源
> **下游消费者**：M6 frontend_student — 嵌入 player 组件；M2/M3 — 接收 `feedback.json`
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.5
> **版本**：v1.0 · 2026-05-15

---

## 1. 模块定位与边界

### 1.1 一句话定位

把 `teaching_events.json` 在前端真实地"演出来"——TTS 合成语音 + Live2D 数字人口型同步 + 黑板内容渲染 + 播放控制。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| TTS 批量合成（speak event）| events 生成（M4 做）|
| 音频时间线驱动 Live2D 嘴型 | Skill 蒸馏（M2 做）|
| 黑板渲染 7 种 action | 教师选择 / 推荐（M3 做）|
| 播放 / 暂停 / 拖进度 / 速度 | 账号 / 上传（M6 做）|
| quiz event 暂停 + 学生交互 | avatar 资产生产（设计运营做）|
| 学生反馈采集（学完后）| 反馈聚合（M6/M2 做）|
| 流式 TTS（Phase 2）| 触发下一轮 events（M4 做）|

### 1.3 核心价值

- **M5 是产品的"脸"**：90% 的用户感知质量来自 M5
- **M5 是 Skill 的最终演出舞台**：再聪明的 Skill 在烂 player 里都是失败

---

## 2. 子模块拆分与文件结构

```text
modules/M5_runtime/
  tts_service/                      # 现有 GPT_SoVITS，增加封装
    GPT_SoVITS/                     # vendored，不动
    tts_engine.py                   # generate_tts_batch() 入口
    voice_clone.py                  # 用 M1 的 audio_samples 做克隆参考
    edge_tts_fallback.py            # 兜底 TTS（免费但音色固定）
    audio_postprocess.py            # 时长估算 / 静音裁剪
  player_runtime/                   # 新增（前端 TS）
    src/
      Player.ts                     # 核心调度器
      AudioPlayer.ts
      EventScheduler.ts
      QuizHandler.ts
    package.json
  blackboard_frontend/              # 现有，开发
    src/
      Blackboard.tsx                # 主组件
      actions/
        write_title.tsx
        write_subtitle.tsx
        write_bullets.tsx
        write_steps.tsx
        write_summary.tsx
        clear_board.tsx
        highlight.tsx
      formula.tsx                   # LaTeX 渲染
      table.tsx
  live2d_frontend/                  # 现有，开发
    src/
      Live2DStage.tsx
      LipSync.ts                    # 嘴型驱动
      AvatarLoader.ts
  avatar_system/                    # 新增
    pixel_renderer.py               # 像素图生成（备用方案）
    live2d_resource_manager.py
  build_playback/                   # 新增
    builder.py                      # build_playback_data()
  schemas/
    audio_manifest.schema.json
    playback_data.schema.json
  README.md
  run.py                            # 本地启动 player demo
  tests/
    test_tts.py
    test_builder.py
    e2e/                            # 浏览器自动化
```

---

## 3. 详细接口

### 3.1 后端 Python 接口

#### TTS 批量

```python
def generate_tts_batch(
    events_path: str,
    output_dir: str,
    voice_id: str,
    config: dict | None = None,
) -> dict:
    """
    把 events 中所有 speak event 合成音频。
    
    Args:
        events_path: data/sessions/{sid}/events/turn_{n}.json
        output_dir: data/sessions/{sid}/audio/turn_{n}/
        voice_id: 教师音色 ID（来自 M6 teacher_card）
        config: 见 §3.3
    
    Returns:
      {
        "status": "success",
        "audio_manifest": "data/sessions/.../audio_manifest.json",
        "audio_count": 8,
        "tts_engine": "gpt_sovits",
        "total_duration_sec": 64.2
      }
    """
```

#### 构建播放数据

```python
def build_playback_data(
    events_path: str,
    audio_manifest_path: str,
    output_dir: str,
    teacher_card_path: str,
    config: dict | None = None,
) -> dict:
    """
    把 events + audio_manifest + teacher_card 合并为前端易消费的 playback_data.json。
    
    Returns:
      {
        "status": "success",
        "playback_data": "data/sessions/.../playback_data.json",
        "timeline_count": 12
      }
    """
```

#### 学生反馈写入

```python
def submit_feedback(
    session_id: str,
    student_id: str,
    feedback: dict,
) -> dict:
    """
    写入 data/sessions/{sid}/feedback.json
    feedback 字段见 §5.4
    """
```

### 3.2 前端 TypeScript 接口

```typescript
// player_runtime/Player.ts
interface PlaybackData { ... }   // 见 §5.3

interface PlayerRuntime {
  load(playback: PlaybackData): Promise<void>;
  play(): void;
  pause(): void;
  seek(seq: number): void;
  setSpeed(rate: number): void;     // 0.75 / 1.0 / 1.25 / 1.5
  
  on(event: PlayerEvent, cb: (data: any) => void): void;
  
  destroy(): void;
}

type PlayerEvent =
  | "speak_start"     // {seq, text}
  | "speak_end"
  | "board_update"    // {action, content}
  | "formula_render"
  | "table_render"
  | "pause_start"     // {duration_sec}
  | "quiz_open"       // {question, options}
  | "quiz_answered"   // {answer}
  | "session_end"
  | "error";
```

### 3.3 config 字段

```python
config = {
    "tts": {
        "engine": "gpt_sovits",          # gpt_sovits / edge_tts
        "voice_id": "...",
        "speed": 1.0,
        "audio_format": "wav",
        "sample_rate": 22050,
        "use_voice_clone": True,         # 用 M1 audio_samples 做参考
        "clone_reference_count": 3,
    },
    "playback": {
        "speak_pause_after_sec": 0.3,    # 句间停顿
        "board_dwell_sec": 1.5,          # 板书停留时间
    }
}
```

---

## 4. 输入文件契约

### 4.1 来自 M4

#### `teaching_events.json`

按 `api_contract.md §5` schema。**M5 必须支持**：

- 事件类型：`speak / board / formula / table / pause / quiz` 共 6 种
- board action：`write_title / write_subtitle / write_bullets / write_steps / write_summary / clear_board / highlight` 共 7 种
- formula `display_mode`：`block / inline`

**M5 不允许**：
- 修改 events 内容
- 跳过未识别的 type / action（必须 fail-loud）

### 4.2 来自 M1

`data/teachers/{tid}/audio_samples/*.wav` — 用于 voice cloning。

M1 已保证 ≥ 5 段 8-30 秒高质量音频。M5 取前 3 段作为 clone reference。

### 4.3 来自 M6

#### `teacher_card.json`

读 `voice_id`, `avatar.live2d_model_id`, `avatar.pixel_url`。

### 4.4 与 M1 / M4 / M6 的契约一致性自检

| 检查点 | 状态 |
|---|---|
| ✅ teaching_events.json schema 与 `api_contract.md §5` 一致 | 字段核对 |
| ✅ board action 7 种枚举与 M4 输出一致 | 与 M4 §6 H3 同步 |
| ✅ audio_manifest.json schema 与 `api_contract.md §6` 一致 | 字段核对 |
| ✅ playback_data.json schema 与 `api_contract.md §7.6` 一致 | 字段核对 |
| ✅ M1 audio_samples 路径 `data/teachers/{tid}/audio_samples/` | 与 M1 §3.4 一致 |
| ✅ teacher_card 字段使用 | 与总体方案 §5.5 一致 |
| ✅ session_id 命名 | 与总体方案 §5.2 一致 |

---

## 5. 输出文件契约

### 5.1 `audio_manifest.json`

按 `api_contract.md §6` schema。

```json
{
  "event_file_id": "teaching_events_SES_..._t3",
  "session_id": "SES_20260515103200_a3f",
  "turn": 3,
  "tts_engine": "gpt_sovits",
  "voice_id": "...",
  "items": [
    {
      "event_id": "evt_0001",
      "seq": 1,
      "text": "...",
      "audio_path": "data/sessions/.../turn_3/evt_0001.wav",
      "duration_sec": 3.2,
      "sample_rate": 22050
    }
  ]
}
```

### 5.2 音频文件目录

```text
data/sessions/{session_id}/audio/turn_{n}/
  audio_manifest.json
  evt_0001.wav
  evt_0003.wav     # 只对 speak event 生成
  ...
```

### 5.3 `playback_data.json`

按 `api_contract.md §7.6` schema 扩展：

```json
{
  "session_id": "SES_...",
  "turn": 3,
  "teacher_id": "T_...",
  "skill_id": "S_..._v2",
  "avatar": {
    "pixel_url": "...",
    "live2d_model_id": "..."
  },
  "voice_id": "...",
  "timeline": [
    {
      "seq": 1,
      "type": "speak",
      "event_id": "evt_0001",
      "text": "我们先来看一个现象。",
      "audio_path": "data/sessions/.../turn_3/evt_0001.wav",
      "duration_sec": 3.2,
      "start_offset_sec": 0.0
    },
    {
      "seq": 2,
      "type": "board",
      "event_id": "evt_0002",
      "action": "write_title",
      "content": "过拟合 Overfitting",
      "start_offset_sec": 3.5,
      "dwell_sec": 1.5
    },
    {
      "seq": 3,
      "type": "quiz",
      "event_id": "evt_0003",
      "question": "...",
      "options": ["A", "B"],
      "blocking": true,
      "start_offset_sec": 5.0
    }
  ],
  "total_duration_sec": 64.2
}
```

### 5.4 `feedback.json`

按总体方案 §5.5 schema：

```json
{
  "session_id": "SES_...",
  "student_id": "U_...",
  "teacher_id": "T_...",
  "skill_id": "S_..._v2",
  "submitted_at": "...",
  "fingerprint_feedback": {
    "pace": 0.5,
    "interactivity": 0.7,
    "humor": 0.3
  },
  "pedagogy_feedback": {
    "concept_entry_perceived": "problem-driven",
    "analogy_density_perceived": "high",
    "misconception_alert_perceived": "proactive-explicit"
  },
  "rating": 4,
  "comment": "...",
  "completion_pct": 1.0
}
```

---

## 6. 硬性要求（不可妥协）

| # | 硬性要求 | 验证方法 |
|---|---|---|
| H1 | 必须实现全部 6 种 event type，未识别 type 直接 fail，不允许静默跳过 | 自动测试 |
| H2 | 必须实现全部 7 种 board action | 自动测试 |
| H3 | `audio_manifest.json` / `playback_data.json` 必须通过 schema 校验 | CI |
| H4 | TTS 单 session 完成时长必须 ≤ session 真实播放时长 × 0.5（MVP）| 性能测试 |
| H5 | quiz event 必须**暂停 TTS** 等学生回答；不允许跳过 | 自动测试 |
| H6 | player 必须支持 play / pause / seek 三个最低功能 | E2E 测试 |
| H7 | 音频 / 板书时间线偏差 < 200ms（MVP）| 人工抽测 + 时间戳日志 |
| H8 | TTS 失败时必须降级到 edge_tts，不允许整个 session 不出声 | 故障注入 |
| H9 | 不允许调用 M2/M3/M4 代码 | 静态扫描 |
| H10 | 写音频文件必须**原子**（tmp + rename） | code review |
| H11 | 多教师并发学习时 voice_id 不能串号 | 集成测试 |
| H12 | feedback.json 必须经过字段校验，缺 rating 字段直接拒绝 | 自动测试 |
| H13 | clone reference 取 M1 audio_samples 前 3 段；不允许跨教师借用音色 | 集成测试 |
| H14 | player 必须可被 destroy 释放资源（避免 SPA 内存泄漏） | E2E 测试 |

---

## 7. 验收标准

### 7.1 MVP（Phase 1 结束时）

| # | 指标 | 标准 | 测试方法 |
|---|---|---|---|
| A1 | TTS 单 session 生成时长 | ≤ session 时长 × 0.5 | 性能测试 |
| A2 | TTS 自然度 MOS | ≥ 3.5 | 人工 5 评 |
| A3 | 黑板 7 种 action 全部可渲染 | 100% | E2E |
| A4 | player 播 / 停 / 拖完整 | ✅ | E2E |
| A5 | quiz 交互可用 | ✅ | E2E |
| A6 | 口型与音频同步偏差 | < 200ms | 人工抽测 |
| A7 | feedback 提交可用 | ✅ | 集成测试 |
| A8 | TTS 失败降级 | ✅ | 故障注入 |

### 7.2 Phase 1 → Phase 2

| # | 指标 | 标准 |
|---|---|---|
| A1 | TTS 时长 | ≤ session × 0.3 |
| A2 | MOS | ≥ 4.0 |
| A6 | 口型同步偏差 | < 100ms |
| A9 | Live2D 表情切换 | ✅ |
| A10 | 速度调节 0.75x / 1.5x | ✅ |
| A11 | 流式 TTS 首音 < 1s | Phase 2 末 |

### 7.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A1 | TTS 时长 | 流式实时 |
| A2 | MOS | ≥ 4.3 |
| A6 | 口型同步 | < 50ms |
| A12 | 教师手写感板书 | ✅ |
| A13 | 章节级跳转 | ✅ |

---

## 8. 与其他模块的接口

### 8.1 输入来源

| 来源 | 内容 | 协议 | 路径 |
|---|---|---|---|
| **M4 orchestrator** | `teaching_events.json` | 文件读取 | `data/sessions/{sid}/events/turn_{n}.json` |
| **M1 ingest** | `audio_samples/*.wav` | 文件读取 | `data/teachers/{tid}/audio_samples/` |
| **M6 platform** | `teacher_card.json` | 文件读取 | `data/teachers/{tid}/teacher_card.json` |
| **M6 platform** | Live2D 模型资源 | HTTP 静态资源 | `data/teachers/{tid}/avatar/live2d/` |
| **M6 frontend_student** | 嵌入 PlayerRuntime 组件 | npm package | — |

### 8.2 输出去向

| 去向 | 内容 | 协议 | 路径 |
|---|---|---|---|
| **M6 frontend_student** | 渲染好的 player UI | iframe / npm | — |
| **M6 backend** | `feedback.json` 写入触发 | 函数调用 | `data/sessions/{sid}/feedback.json` |
| **M2 distill** | feedback（间接，由 M6 聚合）| 文件读取 | 同上 |
| **M3 catalog** | feedback stats | 间接通过 M6 | — |

### 8.3 接口契约一致性自检

| 检查点 | 状态 |
|---|---|
| ✅ events schema 与 M4 输出一致 | 字段核对 |
| ✅ board action 7 种与 M4 输出一致 | 与 M4 §6 H3 同步 |
| ✅ audio_manifest.json 与 api_contract.md §6 一致 | 字段核对 |
| ✅ playback_data.json 与 api_contract.md §7.6 一致 | 字段核对 |
| ✅ feedback.json 与总体方案 §5.5 一致 | 字段核对 |
| ✅ teacher_card 字段使用 | 字段核对 |
| ✅ session 路径与 M4 写入路径一致 | `data/sessions/{sid}/audio/turn_{n}/` |
| ✅ 不调用 M2/M3/M4 代码 | 静态扫描 |

---

## 9. 关键技术挑战与实现指导

### 9.1 时间线对齐（核心难点 H7）

```typescript
// EventScheduler.ts
class EventScheduler {
  // 用单一 clock 驱动所有事件，避免 setTimeout 漂移
  private clock: number = 0;
  
  start() {
    requestAnimationFrame(this._tick);
  }
  
  private _tick = () => {
    this.clock = performance.now() - this.startedAt;
    
    for (const item of this.timeline) {
      if (!item.fired && this.clock >= item.start_offset_sec * 1000) {
        this._fire(item);
      }
    }
    
    requestAnimationFrame(this._tick);
  };
}
```

**关键**：用 `requestAnimationFrame` + `performance.now()` 而不是 `setTimeout`，避免长时间累积漂移。

### 9.2 quiz 暂停机制（H5）

```typescript
private async _fire(item: TimelineItem) {
  if (item.type === "quiz" && item.blocking) {
    this.audioPlayer.pause();
    const answer = await this.quizHandler.open(item);
    this.audioPlayer.resume();
    this._adjustClock(); // 减去 quiz 耗时，保持后续 timeline 正确
  }
}
```

### 9.3 TTS 降级（H8）

```python
def generate_tts_batch(...):
    try:
        return _gpt_sovits_batch(...)
    except (TTSEngineError, ModelLoadError) as e:
        logger.warning(f"GPT-SoVITS failed: {e}, fallback to edge_tts")
        return _edge_tts_batch(..., voice_id="zh-CN-XiaoyiNeural")
```

### 9.4 Live2D 嘴型（不要追求完美）

```typescript
// LipSync.ts
// 根据音频 RMS 驱动张嘴幅度，不解析音素
class LipSync {
  bind(audio: HTMLAudioElement, model: Live2DModel) {
    const analyser = createAnalyser(audio);
    const tick = () => {
      const rms = computeRMS(analyser);
      model.setParam("ParamMouthOpenY", rms * 1.5);
      requestAnimationFrame(tick);
    };
    tick();
  }
}
```

**关键**：MVP 阶段不要做音素级口型；用 RMS 驱动张嘴幅度，用户感知够用。

### 9.5 黑板渲染统一接口

```typescript
// blackboard_frontend/src/Blackboard.tsx
interface BoardAction {
  action: string;
  content: any;
}

const ACTION_HANDLERS: Record<string, (b: Board, c: any) => void> = {
  write_title:    (b, c) => b.appendBlock("title", c),
  write_subtitle: (b, c) => b.appendBlock("subtitle", c),
  write_bullets:  (b, c) => b.appendBlock("bullets", c),
  write_steps:    (b, c) => b.appendBlock("steps", c),
  write_summary:  (b, c) => b.appendBlock("summary", c),
  clear_board:    (b, _) => b.clear(),
  highlight:      (b, c) => b.highlight(c),
};

function applyAction(board: Board, evt: BoardAction) {
  const handler = ACTION_HANDLERS[evt.action];
  if (!handler) {
    throw new Error(`Unknown board action: ${evt.action}`);  // H1: fail-loud
  }
  handler(board, evt.content);
}
```

### 9.6 音色克隆参考（H13）

```python
def get_clone_references(teacher_id: str, count: int = 3) -> list[Path]:
    samples_dir = Path(f"data/teachers/{teacher_id}/audio_samples")
    manifest = json.loads((samples_dir / "manifest.json").read_text())
    # 按 SNR 降序取前 N
    sorted_samples = sorted(
        manifest["samples"],
        key=lambda s: s.get("snr_estimate", 0),
        reverse=True
    )
    return [samples_dir / s["path"] for s in sorted_samples[:count]]
```

---

## 10. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| GPT-SoVITS 在某些机器跑不起来 | 高 | 高 | H8 edge_tts 兜底；提供 docker 化方案 |
| Live2D 资源生产慢 | 高 | 中 | 提供 pixel 静态形象 + 嘴型摇摆作为兜底 |
| 时间线漂移 | 中 | 高 | §9.1 单 clock 驱动 |
| 浏览器自动播放策略禁止音频 | 高 | 高 | 必须有"开始学习"用户点击触发首次播放 |
| TTS 中文专业术语读错 | 高 | 中 | 提供拼音矫正字典 |
| 大量音频文件占盘 | 中 | 中 | session 完成 7 天后清理（M6 做） |
| 移动端兼容差 | 中 | 中 | MVP 只支持 desktop；移动端 Phase 3 |

---

## 11. 本地开发与测试

### 11.1 后端 TTS 跑通

```bash
python modules/M5_runtime/run.py tts \
  --events data/sessions/SES_test/events/turn_1.json \
  --output data/sessions/SES_test/audio/turn_1/ \
  --voice-id default
```

### 11.2 前端 player 跑通

```bash
cd modules/M5_runtime/player_runtime
npm install
npm run dev
# 浏览器打开 http://localhost:5173/?session=SES_test
```

### 11.3 必须提供的测试

```text
tests/
  test_tts.py                 # H1 / H2 / H8
  test_builder.py             # H3 schema
  test_concurrent_tts.py      # H11 多教师并发
  test_clone_reference.py     # H13
  e2e/
    test_player_basic.spec.ts        # H6 播停拖
    test_quiz_pause.spec.ts          # H5
    test_all_board_actions.spec.ts   # H2
    test_destroy.spec.ts             # H14
```

### 11.4 CI 检查项

- audio_manifest / playback_data schema 校验
- 静态扫描 import 不含 M2/M3/M4
- 浏览器 E2E（headless playwright）

---

## 12. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | 现有 GPT_SoVITS 能跑通 inference（命令行单段）| 出 wav |
| 2 | 实现 `generate_tts_batch()` 框架（先用 edge_tts mock）| M5 拿到 events 能产 audio_manifest |
| 3 | 实现 `build_playback_data()` | 与 M4 events 兼容 |
| 4 | 前端 player_runtime 骨架，支持 speak 和 board 两种 event | 静态 demo 跑通 |
| 5 | Live2D 模型试跑（预制模型，不接 voice clone） | 能动嘴 |
| 6 | 与 M1 owner 确认 audio_samples 路径 | 双方文档互引 |
| 7 | 与 M4 owner 确认 board action 全部 7 种 | 双方文档互引 |
| 8 | 与 M6 owner 确认 PlayerRuntime npm 集成方式 | 双方文档互引 |

---

**END OF M5 DOCUMENT**

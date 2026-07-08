# M1 · Ingest 教师素材摄取 — 详细方案

> **上游依赖**：无（系统起点）
> **下游消费者**：M2 (Distill)、M5 (TTS 训练数据)
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.1
> **版本**：v1.0 · 2026-05-15

---

## 1. 模块定位与边界

### 1.1 一句话定位

把教师上传的**任意格式素材**（视频/音频/PDF/PPT）统一处理为可被下游消费的**结构化语料**和**可复用的音频片段**。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 文件格式校验 | 风格分析 / 评分（M2 做） |
| 视频 → 音频提取 | TeacherSkill 生成（M2 做） |
| 长音频切分 | 教师 CRUD（M6 做） |
| ASR 转写 | 推送通知 / 触发 M2（由 M6 编排） |
| 文本清洗（去重叠、合并不完整段、标点修正）| 文本"风格归一化"（会污染蒸馏） |
| 原始音频片段保留 | 删除原始上传文件 |
| 多租户写入 `data/teachers/{teacher_id}/` | 跨教师数据访问 |
| 暴露异步进度查询 | 同步阻塞返回（视频可能 1 小时+）|

### 1.3 核心价值

- M1 是数据质量的第一道关：**M2 蒸馏的天花板由 M1 的转写质量决定**
- 原始音频片段是 TTS 个性化音色的训练数据，**不能省**

---

## 2. 子模块拆分与文件结构

```text
modules/M1_ingest/
  asr_pipeline/                  # 现有，保留
    whisper_runner.py            # Whisper 封装
    funasr_runner.py             # 备用 ASR
    cloud_asr_runner.py          # 云端 ASR 兜底
    asr_dispatcher.py            # 选择器
  audio_processing/
    extractor.py                 # 视频 → 音频
    segmenter.py                 # 长音频切分
    sample_picker.py             # 挑选高质量片段作为 TTS 样本
  text_cleaning/
    cleaner.py                   # 去重叠/标点/清洗
    rules.py                     # 规则集
  doc_processing/                # PDF/PPT/讲义解析（Phase 2）
    pdf_parser.py
  ingest_orchestrator/
    orchestrator.py              # 主流程编排
    task_runner.py               # 异步任务封装
    progress_tracker.py          # 进度上报
  README.md
  run.py                         # 本地测试入口
  tests/
    test_orchestrator.py
    test_cleaner.py
    fixtures/
```

---

## 3. 详细接口

### 3.1 主函数

```python
def ingest_teacher_material(
    teacher_id: str,
    upload_paths: list[str],
    output_dir: str,
    config: dict | None = None,
) -> dict:
    """
    教师素材摄取主入口。
    
    Args:
        teacher_id: 教师 ID，格式 T_<YYYYMMDD>_<seq>
        upload_paths: 上传文件路径列表，支持混合（视频+PDF）
        output_dir: 必须为 data/teachers/{teacher_id}/
        config: 可选配置，见 §3.3
    
    Returns:
        见 §3.2
    """
```

### 3.2 返回值规范

**成功**：

```json
{
  "status": "success",
  "teacher_id": "T_20260515_001",
  "transcripts": [
    "data/teachers/T_20260515_001/transcripts/TR_T20260515001_001.json",
    "data/teachers/T_20260515_001/transcripts/TR_T20260515001_002.json"
  ],
  "audio_samples": [
    "data/teachers/T_20260515_001/audio_samples/sample_001.wav"
  ],
  "stats": {
    "total_duration_sec": 1820.5,
    "segments_count": 142,
    "avg_segment_duration_sec": 12.8,
    "estimated_cer": 0.07
  },
  "warnings": []
}
```

**失败**：

```json
{
  "status": "error",
  "message": "ASR backend unavailable: whisper / funasr / cloud all failed",
  "teacher_id": "T_20260515_001",
  "failed_files": ["lec_002.mp4"]
}
```

**部分成功**：

```json
{
  "status": "partial",
  "message": "1 of 3 files failed",
  "succeeded": [...],
  "failed": [{"path": "lec_002.mp4", "reason": "..."}]
}
```

### 3.3 config 字段

```python
config = {
    "asr_backend": "auto",           # auto / whisper / funasr / cloud
    "asr_model": "large-v3",         # whisper 模型规格
    "language": "zh",
    "segment_max_duration_sec": 1800,  # 长音频切分阈值（30 min）
    "audio_sample_count": 5,         # 抽几段作为 TTS 样本
    "audio_sample_min_duration_sec": 8,  # 单条样本最短
    "save_intermediate": False,      # 是否保留临时音频
    "force_reprocess": False,        # 是否覆盖已有结果（默认幂等跳过）
}
```

### 3.4 输出文件 schema

#### `teacher_transcript.json`

**严格遵循** `docs/api_contract.md §2`，本模块新增字段：

```json
{
  "transcript_id": "TR_T20260515001_001",
  "teacher_id": "T_20260515_001",
  "source_file": "lec_001.mp4",
  "source_audio": "data/teachers/T_.../audio_samples/internal_001.wav",
  "language": "zh",
  "asr_backend": "whisper-large-v3",
  "asr_quality": {
    "estimated_cer": 0.07,
    "low_confidence_segments": 3
  },
  "ingested_at": "2026-05-15T10:30:00+08:00",
  "segments": [
    {
      "segment_id": "seg_0001",
      "start": 0.0,
      "end": 6.5,
      "text": "我们今天先来看一个问题。",
      "speaker": "teacher",
      "confidence": 0.92
    }
  ]
}
```

#### 音频样本目录

```text
data/teachers/{teacher_id}/audio_samples/
  sample_001.wav    # 8-30 秒，音质好的清晰段
  sample_002.wav
  manifest.json     # 列出所有样本及其源
```

`manifest.json`:

```json
{
  "teacher_id": "T_20260515_001",
  "samples": [
    {
      "sample_id": "sample_001",
      "path": "sample_001.wav",
      "duration_sec": 12.3,
      "source_transcript": "TR_T20260515001_001",
      "source_segment": "seg_0042",
      "snr_estimate": 28.5
    }
  ]
}
```

### 3.5 异步任务接口（与 M6 配合）

M1 不直接暴露 HTTP，由 M6 包装。但需要提供异步封装：

```python
def submit_ingest_task(
    teacher_id: str,
    upload_paths: list[str],
    output_dir: str,
    config: dict | None = None,
) -> str:
    """提交异步任务，立即返回 task_id"""

def query_ingest_progress(task_id: str) -> dict:
    """
    返回:
    {
      "task_id": "...",
      "status": "running",        # pending/running/success/failed/cancelled
      "progress": 0.45,           # 0.0-1.0
      "stage": "asr_transcribing", # 当前阶段名
      "result": null              # 完成后填 ingest_teacher_material 的返回值
    }
    """
```

**进度阶段定义**（必须按此命名，前端要展示）：

```
file_validating  → audio_extracting → audio_segmenting →
asr_transcribing → text_cleaning    → sample_picking   → done
```

---

## 4. 硬性要求（不可妥协）

> ⚠️ 以下要求是模块**入门红线**，code review 不通过的 PR 拒绝合并。

| # | 硬性要求 | 验证方法 |
|---|---|---|
| H1 | 必须保留**原始音频片段** ≥ 5 段，每段 8-30 秒，存到 `audio_samples/` | 检查 `audio_samples/manifest.json` 段数 |
| H2 | `teacher_transcript.json` 必须通过 `api_contract.md §2` schema 校验 | `scripts/validate_transcript.py` 自动运行 |
| H3 | 必须**幂等**：同一组 upload_paths 第二次运行不应产生重复 transcript（`config.force_reprocess=False` 时跳过）| `tests/test_idempotency.py` |
| H4 | 必须**多租户隔离**：禁止写入 `data/teachers/{teacher_id}/` 之外的任何路径 | code review + path assertion |
| H5 | 必须支持**异步**：单视频 > 5 分钟时必须提交后台任务返回 `task_id` | 集成测试 |
| H6 | 必须实现**至少 2 个 ASR backend**：本地（whisper）+ 兜底（云端 / funasr）| 切断网络后能切换 backend 跑通 |
| H7 | 写文件必须**原子**：临时文件 → rename，禁止边写边读 | code review |
| H8 | 失败必须返回 `status="error"` + 可读 `message`，禁止抛栈到调用方 | `tests/test_error_handling.py` |
| H9 | 不允许调用 M2/M3/M4/M5 的代码 | 静态扫描 import |
| H10 | 所有日志写到 `data/teachers/{teacher_id}/_logs/ingest_{task_id}.log` | 集成测试检查 |

---

## 5. 验收标准

### 5.1 MVP（Phase 1 结束时）

| # | 指标 | 标准 | 测试方法 |
|---|---|---|---|
| A1 | 端到端跑通率 | ≥ 80% | 10 个真实视频测试 |
| A2 | 单视频处理时长 | ≤ 视频时长 × 1.0 | 30 分钟视频应在 30 分钟内出 transcript |
| A3 | ASR 字错率 CER | < 15% | 抽样 100 段人工标注比对 |
| A4 | transcript schema 校验 | 100% 通过 | CI 自动跑 |
| A5 | 音频样本提取数 | 每教师 ≥ 5 段 | 自动检查 |
| A6 | 异步任务进度查询 | 阶段名称正确，progress 单调递增 | 集成测试 |
| A7 | 幂等性 | 重跑无副作用 | 自动测试 |

### 5.2 Phase 1 → Phase 2 升级

| # | 指标 | Phase 2 标准 |
|---|---|---|
| A1 | 端到端跑通率 | ≥ 95% |
| A2 | 处理时长 | ≤ 视频时长 × 0.5 |
| A3 | CER | < 8% |
| A8 | 支持 PDF / PPT 解析 | ✅ |
| A9 | 说话人分离（去除学生提问） | ✅ |

### 5.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A10 | 实时流式 ASR | ✅ |
| A11 | 端到端 < 视频时长 × 0.3 | ✅ |
| A12 | CER < 5% | ✅ |

---

## 6. 与其他模块的接口

### 6.1 输入来源

| 来源 | 内容 | 协议 |
|---|---|---|
| **M6 platform** | 调用 `submit_ingest_task()` 触发 | Python 函数调用 |
| **教师上传文件** | 物理文件落地到 `data/teachers/{id}/uploads/` | 文件系统 |

### 6.2 输出去向

| 去向 | 内容 | 协议 |
|---|---|---|
| **M2 distill** | 读取 `transcripts/*.json` | 文件路径 |
| **M5 tts_service** | 读取 `audio_samples/*.wav`（用于音色训练 / 克隆参考）| 文件路径 |
| **M6 platform** | 通过 `query_ingest_progress(task_id)` 上报进度 | Python 函数调用 |

### 6.3 接口契约一致性自检

- ✅ `teacher_transcript.json` 字段与 `api_contract.md §2` 一致（已对齐）
- ✅ teacher_id 命名与总体方案 §5.2 一致
- ✅ 异步任务 status 枚举与总体方案 §4.3.4 一致（pending/running/success/failed/cancelled）
- ✅ 进度阶段名前端可展示（与 M6 frontend_teacher 协议）

---

## 7. 团队配置

| 角色 | 人数 | 职责 |
|---|---|---|
| M1 owner | 1 | ASR 选型、orchestrator、整体集成 |
| (可选) ASR 调优 | 0.5 | Phase 2 才需要，做说话人分离、降噪 |

---

## 8. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| Whisper 在长视频上 OOM | 高 | 高 | H1: 强制 30 分钟切分；H2: 准备 funasr 备用 |
| 视频音轨无声 / 静音段过长 | 中 | 中 | 提取前 VAD 检测；warning 上报 |
| ASR 误识别专业术语（如"过拟合"→"过你和"）| 高 | 中 | 提供领域词典 hot-words；Phase 2 引入后修正 |
| 上传文件超大（> 2 GB） | 中 | 高 | M6 分片上传；M1 流式处理 |
| 教师上传非授课内容（噪声）| 低 | 低 | M2 蒸馏阶段标记为低质量语料 |
| 云端 ASR 限额 / 收费 | 中 | 中 | 优先本地，只在本地失败时降级 |

---

## 9. 本地开发与测试

### 9.1 快速跑通

```bash
python modules/M1_ingest/run.py \
  --teacher-id T_20260515_001 \
  --upload data/teachers/T_20260515_001/uploads/lec_001.mp4 \
  --output data/teachers/T_20260515_001/
```

### 9.2 必须提供的测试

```text
tests/
  test_orchestrator.py        # 主流程
  test_idempotency.py         # 幂等性 (H3)
  test_error_handling.py      # 错误返回 (H8)
  test_multi_tenant.py        # 多租户隔离 (H4)
  test_async_progress.py      # 异步进度
  fixtures/
    short_lecture.wav         # 60 秒测试音频
    short_lecture_truth.json  # 人工转写 ground truth
```

### 9.3 CI 检查项

- transcript schema 校验
- 音频样本数 ≥ 5
- 路径未越界（不写到其他 teacher_id）
- 函数返回值有 `status` 字段

---

## 10. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | 现有 `modules/asr_pipeline/` 移入 `modules/M1_ingest/asr_pipeline/` | 路径调整，import 不报错 |
| 2 | 数据目录改为多租户：现有 `data/transcripts/teacher_transcript_001.json` 迁到 `data/teachers/T_legacy_001/transcripts/` | 老 demo 仍能跑通 |
| 3 | 实现 `ingest_teacher_material()` 主函数空架子，返回 dummy `success` | M2 能 mock 调用 |
| 4 | 写 `teacher_transcript.json` schema 校验脚本 | 接入 CI |
| 5 | 与 M6 owner 对齐 task_id / progress 协议 | 双方 README 互相引用 |

---

**END OF M1 DOCUMENT**

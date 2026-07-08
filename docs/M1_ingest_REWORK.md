# M1 Ingest · 返工单 (REWORK-001)

> **对象**：M1 Ingest 模块 owner
> **依据**：`docs/modules/M1_ingest.md`（硬性要求 H1-H10 + 验收标准 §5.1）、`docs/EduNUWA_v2_总体方案.md`
> **基线 commit**：`89f89db`（完成 asr_pipeline 后）
> **结论**：模块内功能完成度高，代码质量好，但**未通过 MVP 验收** —— 跨模块契约未对齐，下游 M2 拿到错误类型 / 脏数据，M5 拿不到音色 manifest。
> **签发日期**：2026-05-20

---

## 0. 整体说明

M1 主链路（视频/音频/文档 → transcript）能跑通，三级 ASR、长音频切分、VLM 视觉识别都做得很扎实，`doc_processing` 甚至提前做了 Phase 2 的内容。

但当前问题集中在一句话：**"模块内完成、跨模块不可用"**。

返工目标不是重写，而是把输出对齐数据契约，让 M2 / M5 能正确消费。共 13 项，分 P0/P1/P2 三档。**P0 必须全改完才可重新验收。**

---

## P0 · 阻断下游，必须修复

### R1 · orchestrator 绕过了 ASR 调度器（H6 关键 bug）

- **位置**：`modules/M1_ingest/ingest_orchestrator/orchestrator.py:26-29`
- **现状**：
  ```python
  def _lazy_import_asr_engine():
      from ..asr_pipeline import whisper_runner as mod   # ← 直连 whisper
      return mod
  ```
  你自己写的 `asr_pipeline/CLAUDE.md` 明确要求"始终通过 dispatcher 调用"，但 orchestrator 直连了 `whisper_runner`。结果：`asr_dispatcher` 的三引擎降级（whisper→funasr→cloud）是死代码，Whisper 一旦失败整个摄取就失败。
- **改成**：
  ```python
  def _lazy_import_asr_engine():
      from ..asr_pipeline import asr_dispatcher as mod   # 走调度器，自动降级
      return mod
  ```
  `asr_dispatcher.transcribe_audio()` 与 `whisper_runner.transcribe_audio()` 签名完全一致，仅此一行。
- **验收**：断网或卸载 `faster_whisper` 后，`config={"asr_backend":"auto"}` 仍能降级到 funasr / cloud 跑通。

---

### R2 · 返回值 `transcripts` 类型错误（接口契约不符）

- **位置**：`orchestrator.py:506-509` + `:560-574`
- **现状**：`transcripts` 是 `list[dict]`（每个 dict 含 transcript_id / transcript_path / segments_count...）。
- **文档要求**（`M1_ingest.md §3.2`）：`transcripts` 是 `list[str]`，即 transcript 文件路径列表。
- **影响**：M6 编排（`M6 §3.2`）把 `ingest_result["transcripts"]` 直接传给 M2 `distill_teacher_skill_v2(teacher_id, transcript_paths, ...)`，M2 期望 `list[str]`。现在传 dict 列表 → M2 报错。
- **改成**（二选一，推荐方案 A）：
  - **方案 A**：`transcripts` 改为 `list[str]`（只放 `transcript_path`），把原来的 dict 列表另存为 `transcript_details`：
    ```python
    result = {
        ...
        "transcripts": [t["transcript_path"] for t in transcripts],
        "transcript_details": transcripts,   # 保留富信息
        ...
    }
    ```
  - **方案 B**：保持 `transcripts` 为 dict 列表，同步修改 `M1_ingest.md §3.2` 文档 —— 但 M2/M6 也要跟着改，成本更高，不推荐。
- **验收**：`result["transcripts"]` 中每个元素是字符串路径，且 `Path(p).exists()` 为真。

---

### R3 · 文档提取结果污染 M2 输入目录

- **位置**：`orchestrator.py:_process_document()` → `:347-350`
- **现状**：PDF/PPTX 视觉提取结果写进 `data/teachers/{tid}/transcripts/`，文件名也是 `TR_xxx_NNN.json`。
- **影响**：M2 §8.1 是 glob `transcripts/*.json`，无法区分"语音转写"和"幻灯片提取"。M2 会把 PPT 内容（标题、公式、`中国历史/古代文明` 之类）当成"教师讲解"来蒸馏风格 → 风格指纹和教学法策略被污染。
- **改成**：文档提取写到独立目录，不进 `transcripts/`：
  ```
  data/teachers/{tid}/materials/DOC_{teacher_compact}_{seq}.json
  ```
  - 文件名前缀用 `DOC_` 而非 `TR_`
  - `file_manager.py` 增加 `generate_doc_id(teacher_id, seq)` 和对应目录
  - 返回值中文档提取放到单独字段 `materials: list[str]`，不混进 `transcripts`
- **后续协调**：文档提取最终是否要喂给 M4 课程知识（`data/courses/{cid}/docs/`），与 M4 owner 对齐，本次返工只需先移出 `transcripts/`。
- **验收**：`transcripts/` 目录下只有语音转写；M2 glob 不会读到任何文档提取。

---

### R4 · `_refined.json` 导致 M2 重复计算

- **位置**：`orchestrator.py:204-207`、`:289-291`
- **现状**：开 `enable_refine` 时，精修结果写为 `transcripts/{transcript_id}_refined.json`，与原始 `TR_xxx_001.json` 同目录。
- **影响**：M2 glob `transcripts/*.json` 会把同一节课读两遍（原始 + 精修），语料统计翻倍。
- **改成**：精修结果写到子目录，不被顶层 glob 命中：
  ```
  data/teachers/{tid}/transcripts/_refined/{transcript_id}.json
  ```
  并在返回值中用 `refined_path` 指向新位置（字段已存在，改路径即可）。
- **后续协调**：M2 owner 决定消费原始还是精修版本（精修版质量更高，可能应作为首选输入）——本次返工只需保证两者不在同一 glob 层。
- **验收**：`transcripts/*.json`（非递归）只命中原始转写，不含 `_refined`。

---

### R5 · 缺 `audio_samples/manifest.json`，M5 取音色样本失败

- **位置**：`modules/M1_ingest/audio_processing/extractor.py:60-76`（`save_audio_sample`）
- **现状**：`save_audio_sample` 只 `shutil.copy2` 整段音频为 1 个文件，无 manifest。
- **影响**：M5 `get_clone_references()`（`M5 §9.6`）读 `audio_samples/manifest.json` 按 `snr_estimate` 排序取前 3 段。现在文件不存在 → M5 取音色样本直接失败。
- **改成**：摄取结束后在 `audio_samples/` 写 `manifest.json`，结构按 `M1_ingest.md §3.4`：
  ```json
  {
    "teacher_id": "T_...",
    "samples": [
      {
        "sample_id": "sample_001",
        "path": "sample_001.wav",
        "duration_sec": 12.3,
        "source_transcript": "TR_T..._001",
        "source_segment": "seg_0042",
        "snr_estimate": 28.5
      }
    ]
  }
  ```
- **依赖 R6**（样本必须先按 8-30 秒切片才有多个 sample 可登记）。
- **验收**：`audio_samples/manifest.json` 存在且通过结构检查，`samples` 数组非空。

---

### R6 · 多生成了 `data/teachers/teachers/` 嵌套垃圾目录

- **位置**：`orchestrator.py:443-454`
- **现状**：
  ```python
  teacher_dirs = file_manager.setup_teacher_dirs(
      teacher_id, upload_id,
      base_dir=os.path.dirname(output_dir.rstrip("/\\")) or "data",
  )
  ```
  当 `output_dir = "data/teachers/T_xxx"` 时，`base_dir` 算成 `data/teachers`，`setup_teacher_dirs` 内部又拼 `teachers/{tid}` → 实际创建了 `data/teachers/teachers/T_xxx/...` 一整套空目录，之后才被 `:448-451` 的覆盖逻辑绕过。
- **改成**：不要先用错误 base_dir 建一遍再覆盖。直接基于 `output_dir` 建目录：
  ```python
  teacher_dirs = {
      "root": output_dir,
      "transcripts": os.path.join(output_dir, "transcripts"),
      "audio_samples": os.path.join(output_dir, "audio_samples"),
      "materials": os.path.join(output_dir, "materials"),       # R3 新增
      "uploads": os.path.join(output_dir, "uploads", upload_id),
      "logs": os.path.join(output_dir, "_logs"),                # R11 新增
  }
  for d in teacher_dirs.values():
      os.makedirs(d, exist_ok=True)
  ```
  `file_manager.setup_teacher_dirs` 可保留给单元测试用，但 orchestrator 不要再传错误的 base_dir。
- **验收**：跑一次摄取后，`data/teachers/` 下**不存在** `teachers/` 子目录。

---

## P1 · 硬性要求缺失，验收必查

### R7 · H1 — 音频样本未按 8-30 秒切片

- **位置**：`extractor.py:save_audio_sample`
- **现状**：整段音频复制为 1 个 sample。
- **文档要求**（`M1_ingest.md` H1）：保留 **≥5 段、每段 8-30 秒** 的音频片段。
- **改成**：新增切片函数，从源音频里挑 ≥5 段清晰片段（建议挑非静音、能量稳定的段），每段 8-30 秒，存为 `sample_001.wav`...`sample_00N.wav`，并产出 R5 的 manifest。
  - 简单实现：等距取 5 个起点，各切 15 秒；进阶可做 VAD + SNR 排序。
  - `snr_estimate` 可先用粗略估计（如有困难允许填占位值并在 manifest 标注 `"snr_estimate": null`）。
- **验收**：单教师 `audio_samples/` 下 ≥5 个 wav，每个时长 ∈ [8, 30] 秒。

---

### R8 · H5 — 缺异步任务接口

- **位置**：`modules/M1_ingest/__init__.py`、`ingest_orchestrator/`
- **现状**：只导出同步 `ingest_teacher_material`。
- **文档要求**（`M1_ingest.md §3.5` + H5）：必须提供
  ```python
  submit_ingest_task(teacher_id, upload_paths, output_dir, config) -> str   # 返回 task_id
  query_ingest_progress(task_id) -> dict   # {task_id, status, progress, stage, result}
  ```
- **改成**：新增 `ingest_orchestrator/task_runner.py`：
  - `submit_ingest_task` 用线程 / 进程后台跑 `ingest_teacher_material`，立即返回 `task_id`（格式 `TASK_<UUID4>`）
  - 进度状态写到内存 dict 或 `data/teachers/{tid}/_logs/task_{id}.json`
  - `status` 枚举：`pending/running/success/failed/cancelled`（对齐总体方案 §4.3.4）
  - `stage` 阶段名按 `M1_ingest.md §3.5`：`file_validating → audio_extracting → audio_segmenting → asr_transcribing → text_cleaning → sample_picking → done`
  - 在 `__init__.py` 导出这两个函数
- **验收**：`submit_ingest_task` 返回 `TASK_` 开头的 id；`query_ingest_progress` 能查到 progress 单调递增、stage 名称合法。

---

### R9 · H3 — 缺幂等性

- **位置**：`orchestrator.py:ingest_teacher_material`
- **现状**：每次调用都生成新 `upload_id` 并重新处理全部文件。
- **文档要求**（H3）：`config.force_reprocess=False`（默认）时，同一组源文件第二次运行应跳过、不产生重复 transcript。
- **改成**：处理单个源文件前，按"源文件名 + 内容 hash"判断对应 transcript 是否已存在：
  - 已存在且 `force_reprocess=False` → 跳过，复用已有 transcript_path，结果里标 `"skipped": true`
  - `force_reprocess=True` → 强制重跑
  - 可在 `transcripts/` 维护一个 `_ingest_index.json` 记录 源文件 hash → transcript_id 映射
- **验收**：同一组 `upload_paths` 连续跑两次，第二次 `transcripts/` 文件数不增加。

---

### R10 · H10 — 日志未写到 `_logs/`

- **位置**：全模块（目前只用 `logging` 默认 handler）
- **文档要求**（H10）：日志写到 `data/teachers/{tid}/_logs/ingest_{task_id}.log`。
- **改成**：`ingest_teacher_material` 开头给 logger 挂一个 `FileHandler`，指向 `{output_dir}/_logs/ingest_{upload_id}.log`（或 task_id）；结束时移除该 handler 避免泄漏。
- **验收**：跑一次摄取后，`data/teachers/{tid}/_logs/` 下有对应日志文件，内容含各阶段记录。

---

## P2 · 一致性 / 小瑕疵

### R11 · 参数命名 `source_paths` vs `upload_paths`

- **位置**：`orchestrator.py:374`、`__init__.py`、`run.py`
- **现状**：实现用 `source_paths`，文档 `M1_ingest.md §3.1` 用 `upload_paths`。
- **改成**：二选一统一。**推荐**把代码参数改为 `upload_paths`（与文档、与 M6 调用方一致）。若坚持用 `source_paths`，则同步改 `M1_ingest.md §3.1` 和 §3.5。
- **验收**：文档与代码参数名一致。

---

### R12 · `source_audio` 字段悬空

- **位置**：`whisper_runner.py:87`、`orchestrator.py:_cleanup_tmp`
- **现状**：transcript 里 `source_audio` 指向 `uploads/_tmp_{id}.wav`，该临时文件在 `_cleanup_tmp` 被删 → 字段指向不存在路径。
- **改成**：`source_audio` 改为指向保留下来的音频样本目录，或指向 `uploads/{upload_id}/` 下保留的原始上传文件；不要指向会被删的 tmp 文件。
- **验收**：transcript 中 `source_audio` 路径 `Path(...).exists()` 为真。

---

### R13 · H2 — 缺 transcript schema 显式校验

- **位置**：`orchestrator.py` 写 transcript 之后
- **现状**：transcript 字段虽对齐 `api_contract.md §2`，但无显式校验步骤。
- **改成**：写 transcript 前用 `api_contract.md §2` 的 schema 做一次校验（必需字段：`transcript_id`/`source_audio`/`language`/`segments`，每个 segment 含 `segment_id`/`text`）。校验失败则该文件计入 `failed`，不写出残缺 transcript。
- **验收**：故意构造缺字段的 transcript，应被拦截并进 `failed` 列表。

---

## 验收清单（返工完成后逐项核对）

| 项 | 验收标准 | P0/P1/P2 |
|---|---|---|
| R1 | 卸载 faster_whisper 后 auto 模式能降级跑通 | P0 |
| R2 | `result["transcripts"]` 是 `list[str]` 且路径存在 | P0 |
| R3 | `transcripts/` 下无文档提取，M2 glob 干净 | P0 |
| R4 | `transcripts/*.json` 非递归 glob 不含 `_refined` | P0 |
| R5 | `audio_samples/manifest.json` 存在且结构合法 | P0 |
| R6 | 不再生成 `data/teachers/teachers/` 嵌套目录 | P0 |
| R7 | `audio_samples/` ≥5 个 wav，每个 8-30 秒 | P1 |
| R8 | `submit_ingest_task` / `query_ingest_progress` 可用 | P1 |
| R9 | 同一输入跑两次不产生重复 transcript | P1 |
| R10 | `_logs/ingest_*.log` 生成 | P1 |
| R11 | 文档与代码参数名一致 | P2 |
| R12 | `source_audio` 指向真实存在的文件 | P2 |
| R13 | 残缺 transcript 被 schema 校验拦截 | P2 |

**重新验收门槛**：P0 全部通过 + P1 至少完成 R8/R9/R10（H3/H5/H10 三条硬性要求）。

---

## 跨模块协调事项（需与其他 owner 对齐，非本人单独决定）

1. **R3 文档提取最终去向**：与 M4 owner 确认是否要把 `materials/` 的文档提取喂给 `data/courses/{cid}/docs/`。
2. **R4 精修版消费策略**：与 M2 owner 确认 M2 应消费原始转写还是 `_refined` 版本。
3. **R2 返回值结构**：若选方案 B（保留 dict 列表），需 M2 + M6 owner 共同确认并改 3 份文档。

---

**END OF REWORK TICKET**

# Third-Party Notices / 第三方组件声明

This repository contains or depends on the following third-party software.
本仓库包含或依赖以下第三方软件。

## Vendored source code / 随仓库分发的源码

### GPT-SoVITS
- **Path**: `modules/M5_runtime/tts_service/GPT_SoVITS/`
- **Upstream**: <https://github.com/RVC-Boss/GPT-SoVITS>
- **License**: MIT
- **Usage**: Few-shot voice-cloning TTS engine used by the teacher-voice
  synthesis service. Model weights are **not** distributed with this
  repository — follow the upstream instructions to download pretrained
  models, or use the edge-tts fallback which requires no local models.
  该目录为 GPT-SoVITS 推理代码副本（MIT 许可）。模型权重不随仓库分发，
  请按上游说明自行下载；无本地模型时系统自动降级为 edge-tts。

## Key runtime dependencies / 主要运行时依赖

| Component | License | Purpose |
|---|---|---|
| Flask | BSD-3-Clause | M6 backend HTTP server |
| React + Vite | MIT | M6 / M5 frontends |
| KaTeX | MIT | Formula rendering on the blackboard (`renderMath.ts`) |
| edge-tts | GPL-3.0 (CLI tool, invoked as dependency) | Fallback TTS voice (`zh-CN-YunxiNeural`) |
| faster-whisper | MIT | Local ASR (M1 ingest) |
| FunASR | MIT (model licenses vary) | ASR / VAD / punctuation models |
| PyTorch | BSD-style | Model runtime |
| matplotlib | PSF-based | Blackboard-style teaching figure generation (`scripts/media_library/`) |

Model weights (Whisper, FunASR, GPT-SoVITS pretrained/fine-tuned voices) are
downloaded separately by the user and are subject to their own licenses.
各模型权重由用户自行下载，遵循各自的许可条款。

## Data / 数据

- `data/media_library/` ships only script-generated original figures
  (`license: original (script-generated, EduNUWA)`).
  图库仅随仓库分发脚本自制的原创教学插图。
- Demo teacher profiles under `data/teachers/` are anonymized samples for
  pipeline demonstration; no real-person voice models are included.
  data/teachers/ 下为匿名化的示例教师数据，仅用于演示流水线，不含任何真人音色模型。

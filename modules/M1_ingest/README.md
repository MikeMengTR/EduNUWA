# M1 · Ingest 教师素材摄取

> 📄 完整方案：[docs/modules/M1_ingest.md](../../docs/modules/M1_ingest.md)
> 📄 总体方案：[docs/EduNUWA_v2_总体方案.md](../../docs/EduNUWA_v2_总体方案.md)

## 文件结构

```
modules/M1_ingest/
├── __init__.py                      # 包入口，导出 ingest_teacher_material
├── run.py                           # CLI 测试入口
├── start_vllm.sh                    # vLLM + Qwen2.5-VL 启动脚本（WSL2）
├── asr_pipeline/
│   ├── whisper_runner.py            # Whisper 语音转写（faster_whisper）
│   ├── funasr_runner.py             # FunASR Paraformer 本地备用
│   ├── cloud_asr_runner.py          # 阿里云百炼 DashScope 云端兜底
│   ├── asr_dispatcher.py            # 自动调度：whisper→funasr→cloud
│   ├── config.py                    # 三层合并配置 + 学科热词
│   ├── README.md                    # 子模块文档
│   ├── CLAUDE.md                    # 开发指令
│   └── __init__.py
├── audio_processing/
│   ├── extractor.py                 # 视频→音频提取 + TTS 样本保存
│   ├── segmenter.py                 # 长音频切分（30min 阈值防 OOM）
│   └── __init__.py
├── text_cleaning/
│   ├── cleaner.py                   # LLM 文本精修：口语→学术 LaTeX
│   └── __init__.py
├── doc_processing/
│   ├── pdf_parser.py                # PDF/PPTX 文本提取 + VLM 视觉识别
│   └── __init__.py
├── ingest_orchestrator/
│   ├── orchestrator.py              # 主编排器：ingest_teacher_material()
│   ├── file_manager.py              # ID 生成、多租户目录、原子写入
│   └── __init__.py
└── tests/
    ├── test_vision.py               # 视觉提取单独测试
    ├── test_perf.py                 # 端到端性能测试
    └── fixtures/                    # 测试数据
```

## 子模块状态

| 子目录 | 职责 | 状态 |
|---|---|---|
| `asr_pipeline/` | 三级 ASR 引擎 (Whisper/FunASR/Cloud) + 自动调度 | ✅ 已有 |
| `audio_processing/` | 视频→音频提取、30min 长音频切分、音频样本保留 | ✅ 已有 |
| `text_cleaning/` | LLM 学术精修（口语→LaTeX）| ✅ 已有 |
| `doc_processing/` | PDF/PPTX 文本提取 + VLM (Qwen2.5-VL) 视觉识别 | ✅ 已有 |
| `ingest_orchestrator/` | 主流程编排、ID 管理、原子写入 | ✅ 已有 |

## 主入口

```python
from modules.M1_ingest import ingest_teacher_material

result = ingest_teacher_material(
    teacher_id="T_20260515_001",
    source_paths=["lecture1.mp4", "handout.pdf"],
    output_dir="data/teachers/T_20260515_001",
    config={
        "language": "zh",
        "enable_refine": False,
        "save_audio_samples": True,
        "asr_model": "large-v3",
        "asr_device": "cuda",
        "doc_backend": "auto",         # auto|vision|pdfplumber|fitz|PyPDF2
        "segment_max_duration_sec": 1800,
    },
)
```

## 返回值

```python
{
    "status": "success",              # success|partial|error
    "message": "全部处理成功",
    "upload_id": "UP_20260518...",
    "teacher_id": "T_20260515_001",
    "transcripts": [...],
    "audio_samples": [...],
    "stats": {
        "total_duration_sec": 1820.5,
        "segments_count": 142,
        "avg_segment_duration_sec": 12.8,
        "estimated_cer": 0.07,
    },
    "warnings": [],
}
```

## CLI 快速测试

```bash
# 单文件摄取
python -m modules.M1_ingest.run \
    --teacher_id T_test_001 \
    --source ./test_data/lecture1.mp4 \
    --output ./test_output/teachers/T_test_001

# 多文件 + LLM 精修
python -m modules.M1_ingest.run \
    --teacher_id T_test_001 \
    --source ./videos/lecture1.mp4 ./handouts/slides.pdf \
    --output ./test_output/teachers/T_test_001 \
    --refine

# VLM 视觉提取测试
python modules/M1_ingest/tests/test_vision.py \
    --source "tests/fixtures/1.2.1 数列极限的定义.pptx" \
    --dpi 200
```

## VLM 视觉提取（PPTX/含公式 PDF）

```
PPTX → LibreOffice headless → PDF → PyMuPDF → PNG (200 DPI)
       → Qwen2.5-VL-7B → 中文原文 + LaTeX 公式
```

启动 vLLM 服务：
```bash
bash modules/M1_ingest/start_vllm.sh
```

## ID 命名规范

| ID 类型 | 格式 | 示例 |
|---------|------|------|
| upload_id | `UP_{YYYYMMDDHHMMSS}_{rand}` | `UP_20260518103200_a3f` |
| transcript_id | `TR_{teacher_compact}_{seq}` | `TR_T20260515001_001` |

## 环境依赖

| 组件 | 依赖 |
|---|---|
| ASR 转写 | `faster_whisper`, `funasr`, `openai` |
| 音频提取 | `moviepy` |
| 环境变量 | `python-dotenv` |
| PDF 文本提取 | `pdfplumber` / `PyMuPDF` |
| PPTX 文本提取 | `python-pptx` |
| VLM 视觉识别 | `requests` + vLLM |
| LLM 精修 | `requests` + LLM API |

详细接口、硬性要求、验收标准见 [`docs/modules/M1_ingest.md`](../../docs/modules/M1_ingest.md)。

# asr_pipeline · M1 语音转写引擎模块

> 📄 完整方案：[docs/modules/M1_ingest.md](../../../docs/modules/M1_ingest.md)
> 📄 开发指令：[CLAUDE.md](./CLAUDE.md)

## 概述

`asr_pipeline` 是 M1 Ingest 模块的 ASR 子模块，提供**三级自动降级**的语音转写能力：

```
whisper (本地首选) → funasr (本地备用) → cloud (云端兜底)
```

对外暴露统一接口 `transcribe_audio()`，调用方无需关心底层引擎切换。

## 文件结构

```
asr_pipeline/
├── __init__.py              # 包入口，导出 transcribe_audio + 配置常量
├── asr_dispatcher.py        # 调度器：按优先级自动选择引擎
├── config.py                # 三层合并配置 + 学科术语热词
├── whisper_runner.py        # faster_whisper large-v3 本地引擎
├── funasr_runner.py         # FunASR Paraformer 本地备用引擎
└── cloud_asr_runner.py      # 阿里云百炼 DashScope 云端引擎
```

## 子模块状态

| 文件 | 职责 | 状态 |
|------|------|------|
| `config.py` | 共享配置管理（BASE + 3 引擎 × 默认值）| ✅ |
| `whisper_runner.py` | faster_whisper large-v3, VAD 防幻觉 | ✅ |
| `funasr_runner.py` | FunASR Paraformer + FSMN-VAD + CT-PUNC | ✅ |
| `cloud_asr_runner.py` | DashScope fun-asr (OpenAI 兼容接口) | ✅ |
| `asr_dispatcher.py` | 自动降级调度：whisper → funasr → cloud | ✅ |

## 快速开始

```python
from modules.M1_ingest.asr_pipeline import transcribe_audio

result = transcribe_audio(
    audio_path="lecture_01.wav",
    transcript_id="TR_T20260515001_001",
    teacher_id="T_20260515_001",
    source_file="lecture_01.mp4",
    config={
        "language": "zh",
        "asr_backend": "auto",       # auto|whisper|funasr|cloud
    },
)

print(f"引擎: {result['asr_backend']}")
print(f"段落数: {len(result['segments'])}")
print(f"估算字错率: {result['asr_quality']['estimated_cer']:.2%}")
```

## 配置参考

### 通用配置 (BASE_CONFIG)

| 键 | 默认值 | 说明 |
|---|---|---|
| `language` | `"zh"` | 转写语言 |
| `device` | `"cuda"` | 推理设备 (cuda/cpu) |
| `cache_dir` | `None` | 模型缓存目录 |

### Whisper 引擎 (WHISPER_DEFAULTS)

| 键 | 默认值 | 说明 |
|---|---|---|
| `model_size` | `"large-v3"` | 模型规格 |
| `compute_type` | `"float16"` | 计算精度 |
| `beam_size` | `5` | 束搜索宽度 |
| `vad_filter` | `True` | 启用 VAD 过滤 |
| `initial_prompt` | 数学领域术语 | 引导 token 分布 |
| `compression_ratio_threshold` | `2.4` | 幻觉检测阈值 |
| `no_speech_threshold` | `0.6` | 静音过滤阈值 |

### FunASR 引擎 (FUNASR_DEFAULTS)

| 键 | 默认值 | 说明 |
|---|---|---|
| `model` | `"paraformer-zh"` | 模型名 |
| `vad_model` | `"fsmn-vad"` | VAD 模型 |
| `punc_model` | `"ct-punc"` | 标点模型 |
| `ncpu` | `16` | CPU 线程数 |
| `hotwords` | 数学关键词 | 热词加权 |

### Cloud 引擎 (CLOUD_DEFAULTS)

| 键 | 默认值 | 说明 |
|---|---|---|
| `provider` | `"aliyun"` | 云服务商 |
| `model` | `"fun-asr"` | 旗舰模型 (¥0.79/hr) |
| `base_url` | DashScope 兼容模式地址 | API 端点 |

## 云端模型选择

| 模型 | 定位 | 价格 | 适用场景 |
|------|------|------|----------|
| `fun-asr` | 旗舰 | ¥0.79/小时 | 正式使用，高精度 |
| `paraformer-v2` | 免费 | 免费 | 测试/预算受限 |
| `gummy-realtime-v1` | 多语种实时 | ¥0.79/小时 | 多语种/实时场景 |

## 返回值

所有引擎返回统一的 `teacher_transcript` schema：

```json
{
  "transcript_id": "TR_T20260515001_001",
  "teacher_id": "T_20260515_001",
  "source_file": "lecture_01.mp4",
  "source_audio": "lecture_01.wav",
  "language": "zh",
  "asr_backend": "whisper-large-v3",
  "asr_quality": {
    "estimated_cer": 0.07,
    "low_confidence_segments": 3
  },
  "ingested_at": "2026-05-19T10:30:00+08:00",
  "segments": [
    {
      "segment_id": "seg_0001",
      "start": 0.0,
      "end": 6.5,
      "text": "今天我们先来看一个问题。",
      "speaker": "teacher",
      "confidence": 0.92
    }
  ]
}
```

## 环境变量

| 变量 | 用途 | 必填 |
|------|------|------|
| `DASHSCOPE_API_KEY` | 阿里云百炼 API Key | 仅 cloud 引擎 |

Key 通过项目根目录 `.env` 文件自动加载（已 gitignored）。获取地址：https://bailian.console.aliyun.com/

## 依赖

| 引擎 | 依赖 | 安装命令 |
|------|------|----------|
| Whisper | `faster_whisper` | `pip install faster_whisper` |
| FunASR | `funasr` | `pip install funasr` |
| Cloud | `openai` | `pip install openai` |
| 环境变量 | `python-dotenv` | `pip install python-dotenv` |

## 冒烟测试

每个 runner 都可独立测试：

```bash
# 调度器降级逻辑测试
python -m modules.M1_ingest.asr_pipeline.asr_dispatcher

# 仅测 whisper（需文件存在）
python -m modules.M1_ingest.asr_pipeline.whisper_runner
```

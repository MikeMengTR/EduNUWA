# CLAUDE.md — asr_pipeline 开发指令

> 本文档为 Claude Code 在此子模块中工作提供上下文。遵循这些指令可以保持代码一致并避免常见陷阱。

## 架构

```
asr_pipeline/
├── __init__.py             ← 统一入口，导出 asr_dispatcher.transcribe_audio
├── asr_dispatcher.py       ← 选择器：auto 模式 whisper→funasr→cloud 自动降级
├── config.py               ← 三层合并配置：BASE→ENGINE_DEFAULTS→user_config
├── whisper_runner.py       ← faster_whisper large-v3 (本地首选)
├── funasr_runner.py        ← FunASR Paraformer (本地备用)
└── cloud_asr_runner.py     ← 阿里云百炼 DashScope (云端兜底)
```

## 硬性约束

- **禁止修改函数签名**。三个 runner + dispatcher 共享完全一致的签名：
  `transcribe_audio(audio_path, transcript_id, teacher_id, source_file, config) -> dict`
- **返回值必须符合 `teacher_transcript.json` schema**（9 个顶层字段 + asr_quality + segments 含 confidence）。
- **`.env` 文件绝对不能提交**。API Key 通过 `python-dotenv` 从项目根 `.env` 自动加载，`cloud_asr_runner.py` 顶部有此逻辑。
- **新增引擎无需改 dispatcher**。在 `_AUTO_PRIORITY` 列表中加入引擎名，并在 `_get_available_engine()` 添加分支即可。

## 配置体系 (config.py)

三层优先级：**user_config > ENGINE_DEFAULTS > BASE_CONFIG**

```python
BASE_CONFIG        # language, device, cache_dir (所有引擎共用)
WHISPER_DEFAULTS   # model_size, beam_size, VAD, initial_prompt...
FUNASR_DEFAULTS    # model, vad_model, punc_model, hotwords...
CLOUD_DEFAULTS     # provider, model, api_key, base_url
```

用户传入的 `config` dict 会覆盖这些默认值。引擎不认识的键被静默忽略。

## 关键参数原理

| 参数 | 设置 | 原理 |
|------|------|------|
| `beam_size=5` | Whisper | 平衡精度与速度；>5 收益递减 |
| `compression_ratio_threshold=2.4` | Whisper VAD | 检测无意义重复输出（幻觉特征） |
| `no_speech_threshold=0.6` | Whisper VAD | 高于 Log-Mel 空频谱均值 0.1，防止静音出字 |
| `condition_on_previous_text=False` | Whisper | 关键！防止前段错误传导到后段 |
| `initial_prompt=数学领域术语` | Whisper | 引导 token 分布偏向学术词汇 |
| `hotwords=数学关键词` | FunASR | 热词加权提升专业术语识别率 |
| `MAX_SEGMENT_SEC=60` | Cloud ASR | DashScope 音频接口 ~25MB 限制的安全值 |
| `estimated_cer = 1 - avg(confidence)` | 通用 | 一致的字错率估计公式 |

## 调度器降级策略 (asr_dispatcher.py)

```
config.asr_backend:
  "auto" (默认) → whisper → funasr → cloud   # 任一成功即返回
  "whisper"     → 仅 whisper, 不降级
  "funasr"      → 仅 funasr,  不降级
  "cloud"       → 仅 cloud,   不降级
```

- 依赖未安装（ImportError）→ 静默跳过
- 运行时异常 → 记录 warning 并降级到下一个
- 全部失败 → `RuntimeError` 包含完整引擎列表和错误详情
- 未知 backend 值 → 回退 `"auto"`，仅 warning 不抛异常

## Cloud ASR 模型选择

| 模型 | 定位 | 价格 |
|------|------|------|
| `fun-asr` (默认) | 旗舰，0.7B+7B LLM，幻觉率↓70% | ¥0.79/小时 |
| `paraformer-v2` | 免费，非实时 | 免费 |
| `gummy-realtime-v1` | 多语种实时 | ¥0.79/小时 |

## 安全红线

- API Key 仅存储在 `.env`，该文件已 gitignored
- 添加新引擎时，确保不将 API Key 硬编码到源码中
- `cloud_asr_runner.py` 使用 OpenAI 兼容接口，不自行实现签名/Token 逻辑
- 临时音频文件在转写完成后通过 `shutil.rmtree` 清理

## 常见陷阱

1. **修改 whisper_runner 时不要增加回条件检查**。当前 `condition_on_previous_text=False` 是经过验证的防幻觉最佳设置。
2. **新增配置键时，同时更新 `config.py` 中对应引擎的 `*_DEFAULTS` dict**，确保默认值有文档记录。
3. **FunASR 输出时间戳是毫秒**，`funasr_runner.py` 负责 `/1000.0` 转换。不要在调用方做二次转换。
4. **Cloud ASR 长音频自动切分**在第 60 秒边界；切分后的时间偏移累积由 `time_offset` 变量跟踪。
5. **不要从 runner 直接导入**——始终通过 dispatcher 调用（除非测试特定引擎的降级行为）。

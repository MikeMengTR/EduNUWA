# 模块接口规范 v0.2

本文件规定 EduNuwa 项目各模块之间的核心交接文件、推荐函数接口和本地集成方式。

当前阶段不强制采用 HTTP API 或 POST 服务调用。各模块优先通过**函数调用 + 文件路径传递**的方式完成集成。这样可以降低开发成本，便于多人并行开发，也便于后续将函数封装成后端服务。

## 1. 核心交接文件

| 文件 | 生产模块 | 消费模块 | 说明 |
|---|---|---|---|
| `teacher_transcript.json` | ASR 模块 | Skill 蒸馏模块 | 教师授课转写文本 |
| `TeacherSkill.md` | Skill 蒸馏模块 | Agent 模块 | 教师讲解方式 |
| `retrieved_context.md` | 课程知识模块 | Agent 模块 | 课程知识上下文 |
| `teaching_events.json` | Agent 模块 | TTS / 黑板模块 | 结构化教学事件 |
| `audio_manifest.json` | TTS 模块 | Live2D / 前端 | 音频文件索引 |
| `playback_data.json` | Demo 构建模块 | Web Demo / 前端 | 前端播放时间线 |

## 2. teacher_transcript.json

`teacher_transcript.json` 由 ASR 模块生成，用于记录教师授课语音的结构化转写结果。

```json
{
  "transcript_id": "teacher_transcript_001",
  "source_audio": "teacher_lecture_001.wav",
  "language": "zh",
  "segments": [
    {
      "segment_id": "seg_0001",
      "start": 0.0,
      "end": 6.5,
      "text": "我们今天先来看一个问题。",
      "speaker": "teacher"
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 是否必须 | 说明 |
|---|---|---|---|
| `transcript_id` | string | 是 | 转写文件编号 |
| `source_audio` | string | 是 | 原始音频路径或文件名 |
| `language` | string | 是 | 语言，默认 `zh` |
| `segments` | array | 是 | 分段转写结果 |
| `segment_id` | string | 是 | 分段 ID |
| `start` | number | 建议 | 起始时间，单位秒 |
| `end` | number | 建议 | 结束时间，单位秒 |
| `text` | string | 是 | 转写文本 |
| `speaker` | string | 建议 | 说话人，默认 `teacher` |

## 3. TeacherSkill.md

`TeacherSkill.md` 由 Skill 蒸馏模块生成，用于描述教师的讲解方式、教学逻辑和输出约束。

必须包含以下部分：

```text
Skill Purpose
Trigger
Teaching Philosophy
Explanation Pattern
Blackboard Policy
Speech Policy
Output Contract
```

推荐结构：

```markdown
# TeacherSkill: Teacher Style

## Skill Purpose
本 Skill 用于将教师的讲解思维迁移到新的课程讲解任务中。

## Trigger
当用户请求概念解释、公式推导、例题讲解、知识点对比、复习总结时调用。

## Teaching Philosophy
从问题或现象出发，先建立直觉，再引入定义、公式和例子。

## Explanation Pattern
1. 提出问题或场景；
2. 解释问题为什么重要；
3. 建立直觉理解；
4. 给出正式定义；
5. 展开公式、流程或结构；
6. 给出例子；
7. 提醒常见误区；
8. 总结归纳。

## Blackboard Policy
黑板只显示标题、关键词、公式、步骤、表格和总结，不复述完整口播内容。

## Speech Policy
讲解应像课堂口播，避免百科式长段文本。

## Output Contract
必须输出结构化教学事件，事件类型包括 speak、board、formula、table、pause、quiz。
```

## 4. retrieved_context.md

`retrieved_context.md` 由课程知识模块生成，用于向 Agent 提供课程事实内容。

```markdown
# Retrieved Course Context

## Query
什么是过拟合？

## Source 1
- 来源：topic_001.md
- 内容：过拟合是指模型在训练集上表现很好，但在测试集上表现较差。

## Source 2
- 来源：topic_002.md
- 内容：常见表现是训练误差下降，但测试误差上升。
```

要求：

1. 必须包含原始用户问题；
2. 每个 Source 应尽量包含来源文件或主题；
3. 内容应简洁，优先提供与问题直接相关的课程材料；
4. 初期可以手动整理，后续可替换为关键词检索或向量检索。

## 5. teaching_events.json

`teaching_events.json` 由 Agent 模块生成，是驱动 TTS、黑板和前端展示的核心文件。

```json
{
  "event_file_id": "teaching_events_001",
  "question_id": "q_001",
  "events": [
    {
      "event_id": "evt_0001",
      "type": "speak",
      "seq": 1,
      "text": "我们先来看一个现象。"
    },
    {
      "event_id": "evt_0002",
      "type": "board",
      "seq": 2,
      "action": "write_title",
      "content": "过拟合 Overfitting"
    }
  ]
}
```

### 5.1 speak 事件

用于 TTS 语音生成。

```json
{
  "event_id": "evt_0001",
  "type": "speak",
  "seq": 1,
  "text": "我们先来看一个现象。"
}
```

### 5.2 board 事件

用于黑板展示。

```json
{
  "event_id": "evt_0002",
  "type": "board",
  "seq": 2,
  "action": "write_bullets",
  "content": ["训练集表现好", "测试集表现差"]
}
```

常用 `action`：

```text
write_title
write_subtitle
write_bullets
write_steps
write_summary
clear_board
highlight
```

### 5.3 formula 事件

用于公式展示。

```json
{
  "event_id": "evt_0003",
  "type": "formula",
  "seq": 3,
  "latex": "Train\\ Loss \\downarrow,\\ Test\\ Loss \\uparrow",
  "display_mode": "block"
}
```

### 5.4 table 事件

用于表格展示。

```json
{
  "event_id": "evt_0004",
  "type": "table",
  "seq": 4,
  "title": "欠拟合与过拟合对比",
  "columns": ["类型", "训练集表现", "测试集表现"],
  "rows": [
    ["欠拟合", "差", "差"],
    ["过拟合", "好", "差"]
  ]
}
```

## 6. audio_manifest.json

`audio_manifest.json` 由 TTS 模块生成，用于记录每个 `speak` 事件对应的音频文件。

```json
{
  "event_file_id": "teaching_events_001",
  "tts_engine": "local_tts_placeholder",
  "voice_id": "anime_teacher_voice_001",
  "items": [
    {
      "event_id": "evt_0001",
      "seq": 1,
      "text": "我们先来看一个现象。",
      "audio_path": "data/audio/teaching_events_001/evt_0001.wav",
      "duration_sec": 3.2
    }
  ]
}
```

字段说明：

| 字段 | 类型 | 是否必须 | 说明 |
|---|---|---|---|
| `event_file_id` | string | 是 | 对应的教学事件文件 ID |
| `tts_engine` | string | 建议 | 使用的 TTS 引擎 |
| `voice_id` | string | 建议 | 使用的音色 ID |
| `items` | array | 是 | 音频条目列表 |
| `event_id` | string | 是 | 对应的 speak 事件 ID |
| `seq` | number | 是 | 对应的事件顺序 |
| `text` | string | 是 | 合成语音的文本 |
| `audio_path` | string | 是 | 生成的音频路径 |
| `duration_sec` | number | 建议 | 音频时长，单位秒 |

## 7. 推荐函数接口

本项目初期不使用 HTTP API 作为模块之间的强制通信方式。各模块统一暴露 Python 函数，通过文件路径传递输入输出。

统一原则：

1. 每个模块暴露一个或多个主函数；
2. 函数输入以文件路径、普通字符串和配置字典为主；
3. 函数输出统一返回 `dict`；
4. 返回值必须包含 `status` 字段；
5. 成功时返回核心输出文件路径；
6. 失败时返回 `status="error"` 和 `message`；
7. 后续如需 Web Demo 调用，可以在这些函数外层再封装 HTTP 服务。

### 7.1 ASR 转写函数

```python
transcribe_audio(
    audio_path: str,
    output_dir: str,
    config: dict | None = None
) -> dict
```

输入示例：

```python
audio_path = "data/raw_audio/teacher_lecture_001.wav"
output_dir = "data/transcripts/"
config = {
    "language": "zh",
    "speaker": "teacher",
    "save_txt": True,
    "save_json": True
}
```

返回示例：

```json
{
  "status": "success",
  "transcript_txt": "data/transcripts/teacher_transcript_001.txt",
  "transcript_json": "data/transcripts/teacher_transcript_001.json",
  "segments_count": 42
}
```

失败返回示例：

```json
{
  "status": "error",
  "message": "audio file not found",
  "audio_path": "data/raw_audio/teacher_lecture_001.wav"
}
```

### 7.2 TeacherSkill 蒸馏函数

```python
distill_teacher_skill(
    transcript_path: str,
    output_dir: str,
    config: dict | None = None
) -> dict
```

输入示例：

```python
transcript_path = "data/transcripts/teacher_transcript_001.json"
output_dir = "data/teacher_skill/"
config = {
    "skill_name": "TeacherStyleSkill",
    "target_language": "zh",
    "focus": [
        "teaching_philosophy",
        "explanation_pattern",
        "blackboard_policy",
        "speech_policy"
    ]
}
```

返回示例：

```json
{
  "status": "success",
  "skill_md": "data/teacher_skill/TeacherSkill.md",
  "skill_profile": "data/teacher_skill/skill_profile.json"
}
```

### 7.3 课程知识供给函数

```python
retrieve_course_context(
    question: str,
    course_docs_dir: str,
    output_dir: str,
    config: dict | None = None
) -> dict
```

输入示例：

```python
question = "什么是过拟合？"
course_docs_dir = "data/course_docs/clean/"
output_dir = "data/retrieved_context/"
config = {
    "top_k": 3,
    "method": "keyword",
    "course_id": "course_demo_001"
}
```

返回示例：

```json
{
  "status": "success",
  "retrieved_context_md": "data/retrieved_context/retrieved_context_001.md",
  "retrieved_context_json": "data/retrieved_context/retrieved_context_001.json",
  "results_count": 3
}
```

### 7.4 Agent 教学事件生成函数

```python
generate_teaching_events(
    question: str,
    teacher_skill_path: str,
    retrieved_context_path: str,
    output_dir: str,
    config: dict | None = None
) -> dict
```

输入示例：

```python
question = "什么是过拟合？"
teacher_skill_path = "data/teacher_skill/TeacherSkill.md"
retrieved_context_path = "data/retrieved_context/retrieved_context_001.md"
output_dir = "data/events/"
config = {
    "model": "deepseek",
    "output_schema": "teaching_events_v1",
    "need_board": True,
    "need_formula": True,
    "need_quiz": False
}
```

返回示例：

```json
{
  "status": "success",
  "events_path": "data/events/teaching_events_001.json",
  "events_count": 8
}
```

失败返回示例：

```json
{
  "status": "error",
  "message": "failed to generate valid teaching_events.json",
  "question": "什么是过拟合？"
}
```

### 7.5 TTS 批量语音生成函数

```python
generate_tts_batch(
    events_path: str,
    output_dir: str,
    config: dict | None = None
) -> dict
```

输入示例：

```python
events_path = "data/events/teaching_events_001.json"
output_dir = "data/audio/teaching_events_001/"
config = {
    "voice_id": "anime_teacher_voice_001",
    "audio_format": "wav",
    "speed": 1.0
}
```

返回示例：

```json
{
  "status": "success",
  "audio_manifest": "data/audio/teaching_events_001/audio_manifest.json",
  "audio_count": 4
}
```

### 7.6 Demo 播放数据构建函数

```python
build_demo_playback(
    events_path: str,
    audio_manifest_path: str,
    output_dir: str,
    config: dict | None = None
) -> dict
```

输入示例：

```python
events_path = "data/events/teaching_events_001.json"
audio_manifest_path = "data/audio/teaching_events_001/audio_manifest.json"
output_dir = "data/demo_cases/demo_case_001/"
config = {
    "demo_id": "demo_case_001",
    "merge_timeline": True
}
```

返回示例：

```json
{
  "status": "success",
  "playback_data": "data/demo_cases/demo_case_001/playback_data.json",
  "timeline_count": 8
}
```

`playback_data.json` 示例：

```json
{
  "demo_id": "demo_case_001",
  "question": "什么是过拟合？",
  "timeline": [
    {
      "seq": 1,
      "type": "speak",
      "text": "我们先来看一个现象。",
      "audio_path": "data/audio/teaching_events_001/evt_0001.wav",
      "duration_sec": 3.2
    },
    {
      "seq": 2,
      "type": "board",
      "action": "write_title",
      "content": "过拟合 Overfitting"
    }
  ]
}
```

### 7.7 一键 Demo 流程函数

```python
run_demo_pipeline(
    question: str,
    transcript_path: str,
    course_docs_dir: str,
    work_dir: str,
    config: dict | None = None
) -> dict
```

输入示例：

```python
question = "什么是过拟合？"
transcript_path = "data/transcripts/teacher_transcript_001.json"
course_docs_dir = "data/course_docs/clean/"
work_dir = "data/demo_cases/demo_case_001/"
config = {
    "use_existing_skill": True,
    "use_existing_context": False,
    "generate_audio": True,
    "build_playback": True
}
```

内部流程：

```text
1. 如果不存在 TeacherSkill.md，则调用 distill_teacher_skill()
2. 调用 retrieve_course_context()
3. 调用 generate_teaching_events()
4. 调用 generate_tts_batch()
5. 调用 build_demo_playback()
```

返回示例：

```json
{
  "status": "success",
  "teacher_skill": "data/teacher_skill/TeacherSkill.md",
  "retrieved_context": "data/retrieved_context/retrieved_context_001.md",
  "events_path": "data/events/teaching_events_001.json",
  "audio_manifest": "data/audio/teaching_events_001/audio_manifest.json",
  "playback_data": "data/demo_cases/demo_case_001/playback_data.json"
}
```

## 8. 函数接口开发约定

### 8.1 返回值格式统一

所有主函数统一返回字典。

成功返回：

```json
{
  "status": "success",
  "主要输出字段": "输出路径",
  "其他统计信息": "..."
}
```

失败返回：

```json
{
  "status": "error",
  "message": "错误原因",
  "相关输入字段": "..."
}
```

模块内部可以抛出异常，但主函数应捕获常见异常并返回可读错误信息，方便集成负责人定位问题。

### 8.2 文件路径优先

函数之间优先传递文件路径，而不是直接传递大段文本。

推荐：

```python
generate_teaching_events(
    question="什么是过拟合？",
    teacher_skill_path="data/teacher_skill/TeacherSkill.md",
    retrieved_context_path="data/retrieved_context/retrieved_context_001.md",
    output_dir="data/events/"
)
```

不推荐：

```python
generate_teaching_events(
    question="什么是过拟合？",
    teacher_skill="很长的 Skill 内容……",
    retrieved_context="很长的课程上下文……"
)
```

原因是文件路径更适合多人协作、调试和结果复现。

### 8.3 配置统一放在 config 中

每个函数都可以接受 `config` 参数，用于存放可选配置。

```python
config = {
    "model": "deepseek",
    "top_k": 3,
    "voice_id": "anime_teacher_voice_001",
    "output_schema": "teaching_events_v1"
}
```

不建议把大量可选参数直接放入函数签名。

### 8.4 每个模块必须提供本地测试入口

每个模块目录下应至少包含一个可运行脚本。

```text
modules/skill_distiller/run.py
modules/course_retriever/run.py
modules/agent_generator/run.py
modules/tts_service/run.py
```

运行示例：

```bash
python modules/agent_generator/run.py
```

运行后应能基于样例数据生成对应输出文件。

### 8.5 后期可再封装为服务接口

当前阶段不采用 HTTP API 作为强制接口。

后续如果 Web Demo 需要后端统一调用，可以在函数接口外层封装服务接口。例如：

```python
@app.post("/agent/generate")
def agent_generate_api(request):
    return generate_teaching_events(...)
```

也就是说：

**函数接口是核心，HTTP API 只是后期可选的外层封装。**

## 9. 推荐模块导出函数汇总

| 模块 | 推荐主函数 | 输入 | 输出 |
|---|---|---|---|
| ASR 模块 | `transcribe_audio()` | 音频路径 | `teacher_transcript.json` |
| Skill 蒸馏模块 | `distill_teacher_skill()` | 转写文件路径 | `TeacherSkill.md` |
| 课程知识模块 | `retrieve_course_context()` | 用户问题、课程资料目录 | `retrieved_context.md` |
| Agent 模块 | `generate_teaching_events()` | 问题、Skill、课程上下文 | `teaching_events.json` |
| TTS 模块 | `generate_tts_batch()` | 教学事件文件 | `audio_manifest.json` |
| Demo 构建模块 | `build_demo_playback()` | 教学事件、音频索引 | `playback_data.json` |
| 全流程脚本 | `run_demo_pipeline()` | 问题、语料、课程资料 | 完整 Demo 数据包 |

## 10. 集成阶段建议

第一阶段使用文件交接和函数调用完成本地集成。

推荐集成流程：

```text
teacher_transcript.json
  ↓ distill_teacher_skill()
TeacherSkill.md
  ↓ retrieve_course_context()
retrieved_context.md
  ↓ generate_teaching_events()
teaching_events.json
  ↓ generate_tts_batch()
audio_manifest.json
  ↓ build_demo_playback()
playback_data.json
```

在项目后期，如果需要支持 Web 页面实时调用，再统一由后端对这些函数进行封装。

## 11. 流式教学演示接口（SSE）

`POST /api/v1/chat/<teacher_id>/demo/stream`（M6，需 Authorization header）是平台
`{code, message, data}` 响应信封的**唯一例外**：流开始前的校验失败（教师不存在、
问题为空、缺 API key）仍返回标准 JSON；校验通过后返回 `text/event-stream`，
DeepSeek 边生成边推送帧：

| 帧 event | data 字段 | 时机 |
|---|---|---|
| `meta` | `session_id, teacher_id, voice_id, avatar_url, avatar_url_alt, teacher_name` | 流开始，LLM 调用前 |
| `event` | 与 teaching_events 元素同形 `{seq, type, ...}` | 每解析出一个事件 |
| `summary` | `{text}` 开场引入语（并行生成） | 可能出现在任意 event 之间或 done 前 |
| `error` | `{message, code, partial}` | LLM 流异常；`partial=true` 表示已推送的事件仍可播放 |
| `done` | `{session_id, events_count, partial}` | 终帧 |

注释帧 `: ping` 用于等待 summary 期间保活。无论正常结束还是中断，
`data/sessions/{session_id}/events.json` 都会落盘（中断时附 `"partial": true`）。

前端播放协议（M6 父页面 ↔ M5 `/runtime/?push=1&session=...` iframe，postMessage，
双方校验 `origin` 与 `session`，事件按 `seq` 去重）：

- iframe→父：`m5:ready`（监听就绪，可重复发，父对重复 ready 重发全量自愈）、`m5:end`
- 父→iframe：`m6:init {events, done}`、`m6:events {events}`、`m6:done`、`m6:error {message, partial}`

事件增量解析的实现在 `modules/M6_platform/backend/event_stream.py`
（`LineAssembler` + `DemoEventParser`），与离线全文解析 `_parse_demo_response`
逐事件等价，等价性由 `backend/test_event_stream.py` 保证——改解析规则必须跑该测试。

**对话记忆**：demo（流式与非流式）与文字 chat 共用 `data/conversations.json`
（key=`{user_id}_{teacher_id}`）。demo 生成前注入最近对话作"前情提要"，讲课结束
追加 `{role:"user"}` 问题与 `{role:"assistant", kind:"demo"}` 讲课摘要（summary +
板书提纲，截断 800 字）。消费历史调 `chat.get_history` / 写入调 `chat.append_history`
（带锁原子追加）；把历史喂给 LLM 时只保留 role/content 字段。

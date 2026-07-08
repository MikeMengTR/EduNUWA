# 系统架构说明

## 1. 总体架构

```text
教师视频 / 音频
  ↓
ASR 转写模块
  ↓
teacher_transcript.json
  ↓
TeacherSkill 蒸馏模块
  ↓
TeacherSkill.md

课程资料 + 用户问题
  ↓
课程知识供给模块
  ↓
retrieved_context.md

TeacherSkill.md + retrieved_context.md + user_question
  ↓
Agent 教学脚本生成模块
  ↓
teaching_events.json

teaching_events.json
  ├── speak 事件 → TTS → audio_manifest.json → Live2D
  └── board/formula/table 事件 → 黑板展示
```

## 2. 核心解耦

- TeacherSkill：教师讲解方式；
- Retrieved Context：课程事实知识；
- Teaching Events：多模态展示协议；
- TTS / Live2D / Blackboard：展示层。

## 3. MVP 与加分项

### MVP

- `TeacherSkill.md` 样例或半自动生成；
- 课程上下文样例；
- Agent 输出结构化教学事件；
- TTS 音频生成；
- Live2D 简单口型同步；
- 黑板内容展示。

### 加分项

- 实时流式输出；
- 分句 TTS 队列；
- 多教师 Skill 切换；
- 多课程切换；
- 更高质量音色与动作表现。

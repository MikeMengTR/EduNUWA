# M6 · Platform APP 外壳 — 当前实现状态

> **代码位置**：`Web/backend/` + `Web/frontend/`
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.6
> **状态**：MVP 功能完成，部分 Phase 1 功能待完善
> **更新日期**：2026-06-05

---

## 1. 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Flask（非 FastAPI，与规范不同，可后续迁移） |
| API 认证 | Bearer Token（非 JWT，功能等价） |
| 数据存储 | JSON 文件（`Web/data/`），未使用 ORM/数据库 |
| 前端框架 | React 18 + Vite + React Router |
| LLM 调用 | DeepSeek API（OpenAI 兼容格式） |
| 文件存储 | 本地文件系统（未抽象 storage_interface） |

---

## 2. 已实现功能

### 2.1 认证系统

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ 注册 | `POST /api/v1/auth/register` | 含 role: teacher / student |
| ✅ 登录 | `POST /api/v1/auth/login` | 返回 Bearer token |
| ✅ 获取当前用户 | `GET /api/v1/auth/me` | token 校验 |
| ✅ 角色鉴权 | — | teacher / student 权限隔离 |

### 2.2 教师管理

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ 创建教师卡片 | `POST /api/v1/teachers` | 含真实姓名、展示名、学科、简介、system_prompt |
| ✅ 编辑教师卡片 | `PUT /api/v1/teachers/{id}` | 仅自己的卡片 |
| ✅ 教师列表 | `GET /api/v1/teachers` | 学生浏览全部，教师看自己；支持学科和关键词搜索 |
| ✅ 教师详情 | `GET /api/v1/teachers/{id}` | 合并 teacher_card + skill_profile + videos |
| ✅ 我的教师 | `GET /api/v1/my/teacher` | 当前教师自己的卡片 |
| ✅ Skill 档案 | `GET /api/v1/teachers/{id}/skill` | 返回 profile + TeacherSkill.md 内容 |
| ✅ Transcripts | `GET /api/v1/teachers/{id}/transcripts` | 已处理素材列表及段落数 |
| ✅ 6 位种子教师 | — | 预置在 `data/teachers/` 中，有 transcript + Skill |

### 2.3 素材上传 + M1 集成

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ 文件上传 | `POST /api/v1/uploads` | multipart form，支持 mp4/mkv/mov/avi/wav/mp3/pdf/pptx |
| ✅ 触发 M1 | — | 上传后自动调用 `submit_ingest_task()` 异步处理 |
| ✅ 进度查询 | `GET /api/v1/tasks/{task_id}` | 返回 status（pending/running/success/failed）+ progress + stage |
| ✅ 阶段展示 | — | 前端显示：文件验证 → 音频提取 → ASR 转写 → 文本精修 → 完成 |

### 2.4 一键蒸馏 + M2 集成

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ 蒸馏触发 | `POST /api/v1/teachers/{id}/distill` | 收集所有 transcript → 调用 DeepSeek → 生成 TeacherSkill.md + skill_profile.json |
| ✅ 蒸馏状态 | `GET /api/v1/teachers/{id}/distill/status` | 返回 has_skill / transcript_count / ready_to_distill / fingerprint |
| ✅ 指纹提取 | — | 从蒸馏结果中自动解析 pace/detail/abstraction/interactivity/humor/rigor |
| ✅ 版本管理 | — | 自动递增 v1 → v2 → v3 |

### 2.5 风格匹配 + M3 集成

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ 风格匹配 | `POST /api/v1/match` | 学生输入自然语言描述 → LLM 对所有教师排序 + 推荐理由 |

### 2.6 学习会话 + M4 集成

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ 创建会话 | `POST /api/v1/sessions` | 指定 teacher_id + mode（ondemand/follow） |
| ✅ 提问 | `POST /api/v1/sessions/{id}/ask` | 调用 M4 OrchestratorPipeline 生成 teaching_events |
| ✅ 会话列表 | `GET /api/v1/sessions` | 当前学生的所有会话 |
| ✅ 会话详情 | `GET /api/v1/sessions/{id}` | session_state.json 内容 |
| ✅ 事件获取 | `GET /api/v1/sessions/{id}/events/{turn}` | 某轮的教学事件 JSON |

### 2.7 TTS + 播放数据 + M5 集成

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ TTS 生成 | `POST /api/v1/sessions/{id}/tts` | 调用 M5 `generate_tts_batch()` |
| ✅ 播放数据 | `POST /api/v1/sessions/{id}/playback` | 调用 M5 `build_playback_data()` |

### 2.8 AI 对话（Skill 驱动）

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ Skill 对话 | `POST /api/v1/chat/{teacher_id}` | 有 TeacherSkill.md → 用完整 7 段契约作 system prompt |
| ✅ 普通对话 | — | 无 Skill → 回退到 teacher_card.system_prompt |
| ✅ 对话历史 | `GET /api/v1/chat/{teacher_id}/history` | 持久化为 JSON |
| ✅ 清除历史 | `DELETE /api/v1/chat/{teacher_id}/history` | — |
| ✅ skillUsed 标记 | — | 响应中返回是否使用了蒸馏 Skill |

### 2.9 视频功能

| ✅ 功能 | 端点 | 说明 |
|---------|------|------|
| ✅ 视频上传 | `POST /api/v1/videos/upload` | 教师上传录制好的教学视频 |
| ✅ 视频列表 | `GET /api/v1/videos` | 按角色过滤 |
| ✅ 视频详情 | `GET /api/v1/videos/{id}` | — |
| ✅ 视频删除 | `DELETE /api/v1/videos/{id}` | 仅自己的视频 |
| ✅ 视频流播放 | `GET /api/v1/videos/{id}/stream` | HTTP Range 请求，支持拖动 |
| ✅ 教师视频列表 | `GET /api/v1/teachers/{id}/videos` | 某教师的所有视频 |

### 2.10 前端页面

| 路径 | 角色 | 功能 |
|------|------|------|
| `/login` | 所有人 | 登录 / 注册（选角色） |
| `/teacher` | 教师 | 教师卡片 + Skill 状态 + Transcripts 列表 + 一键蒸馏按钮 |
| `/teacher/upload` | 教师 | 上传素材 → M1 进度实时展示 |
| `/teacher/videos` | 教师 | 上传 / 删除教学视频 |
| `/student` | 学生 | 教师列表（含指纹徽章 + 质量分 + 标签） + M3 风格匹配搜索 |
| `/student/videos/:id` | 学生 | 观看某教师的教学视频 |
| `/chat/:teacherId` | 学生 | AI 对话（Skill 驱动） |

---

## 3. API 合规情况

所有已实现端点均遵循总体方案 §4.3：

| 规范项 | 状态 | 说明 |
|--------|------|------|
| `/api/v1/` 前缀 | ✅ | 全部端点 |
| 响应格式 `{code, message, data}` | ✅ | code=0 成功，非 0 失败 |
| 状态码区段 | ✅ | 4000 参数错误，4010 未认证，4030 无权限，4040 不存在，5000 服务器错误，5030 下游不可用 |
| 异步任务 status 枚举 | ✅ | pending / running / success / failed / cancelled |
| teacher_id 命名 | ✅ | `T_YYYYMMDD_seq` |

---

## 4. 与规范方案的差距

| # | 规范要求 | 当前状态 | 优先级 |
|---|---------|---------|--------|
| H1 | FastAPI 框架 | Flask | 可后续迁移 |
| H3 | JWT 鉴权 | Bearer Token（功能等价） | 低 |
| H4 | 长任务强制异步 | M1 已异步；蒸馏当前同步（可改为异步） | 中 |
| H5 | 严禁 M6 实现业务逻辑 | ⚠️ `distill.py` 中蒸馏逻辑在 M6 内实现（调用 DeepSeek） | 中 |
| H6 | 文件存储须经 storage_interface | 直接 open() 读写 | 低（MVP 可接受） |
| H10 | 断点续传 / 分片上传 | 未实现 | Phase 2 |
| H11 | 静态资源安全路由 | 视频流已鉴权；音频路径未完全隔离 | 中 |
| H12 | 优雅关闭 | 未实现 | Phase 2 |
| 数据库 | SQLite/Postgres | JSON 文件存储 | Phase 2 |
| 学生端反馈 | feedback 端点 | 未实现 | Phase 1 |
| 教师端 Skill 发布 | 低 grade 二次确认 | 蒸馏后直接保存，无发布审核 | Phase 1 |
| 课程管理 | courses CRUD | 未实现 | Phase 2 |
| 计费 | billing | 未实现 | Phase 3 |

---

## 5. 文件结构

```text
Web/
├── start.bat
├── backend/
│   ├── app.py              # Flask 主入口，加载 .env，注册路由，SPA fallback
│   ├── auth.py             # 注册/登录/token/鉴权/响应格式 ok() err()
│   ├── teachers.py         # 教师卡片 CRUD + Skill 加载 + M3 匹配
│   ├── upload.py           # 文件上传 → 触发 M1 submit_ingest_task()
│   ├── distill.py          # 一键蒸馏 → 调用 DeepSeek 生成 TeacherSkill.md
│   ├── chat.py             # AI 对话（优先使用蒸馏 Skill 作 system prompt）
│   ├── video.py            # 视频上传/列表/流播放（HTTP Range）
│   ├── pipeline.py         # M4 会话 + M5 TTS/播放数据
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api.js          # API 封装层（统一 {code,message,data} 解析）
│   │   ├── App.jsx         # 路由
│   │   ├── pages/
│   │   │   ├── LoginPage.jsx
│   │   │   ├── TeacherDashboard.jsx   # 教师主页 + 蒸馏
│   │   │   ├── UploadPage.jsx        # M1 上传
│   │   │   ├── VideoManagePage.jsx   # 视频管理
│   │   │   ├── StudentDashboard.jsx  # 教师浏览 + M3 匹配
│   │   │   ├── VideoWatchPage.jsx    # 视频观看
│   │   │   └── ChatPage.jsx          # AI 对话
│   │   ├── components/
│   │   │   ├── Navbar.jsx
│   │   │   ├── TeacherCard.jsx       # 含指纹徽章
│   │   │   ├── ChatBox.jsx
│   │   │   └── VideoPlayer.jsx
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
└── data/（运行时生成）
    ├── users.json
    ├── conversations.json
    ├── teachers/
    │   {teacher_id}/
    │       teacher_card.json
    │       transcripts/        # M1 产出
    │       audio_samples/      # M1 产出
    │       uploads/            # M1 上传缓存
    │       skills/
    │           v1/
    │               TeacherSkill.md
    │               skill_profile.json
    │       videos/
    │           {video_id}.mp4
    │           videos_manifest.json
    └── sessions/
        {session_id}/
            session_state.json
            events/
            audio/
```

---

## 6. 模块集成状态

| 模块 | 集成方式 | 状态 |
|------|---------|------|
| **M1** Ingest | `submit_ingest_task()` + `query_ingest_progress()` | ✅ |
| **M2** Distill | metric_extractor + 自研 DeepSeek 蒸馏（`distill.py`） | ✅ |
| **M3** Catalog | `match_teachers()`（LLM 风格匹配） | ✅ |
| **M4** Orchestrator | `OrchestratorPipeline().run()` | ✅ |
| **M5** Runtime | `generate_tts_batch()` + `build_playback_data()` | ✅ |
| **Stream** | `StreamingPipeline` | 待集成 |

---

## 7. 运行方式

```bash
# 后端
cd Web/backend
pip install flask flask-cors openai python-dotenv
python app.py
# → http://localhost:5000

# 前端
cd Web/frontend
npm install && npm run dev
# → http://localhost:3000
```

或双击 `Web/start.bat`。

---

## 8. 典型使用流程

### 教师端
1. 注册教师账号 → 创建教师卡片
2. 上传教学视频/音频 → 自动触发 M1 ASR 转写
3. 等待处理完成 → 点击「一键蒸馏」
4. 系统自动生成 TeacherSkill.md + skill_profile.json
5. 上传录制好的教学视频（可选）

### 学生端
1. 注册学生账号 → 浏览教师列表（看到 6 位种子教师）
2. 使用 M3 风格匹配搜索（例如："我需要讲课幽默、用例子的数学老师"）
3. 点击教师 → AI 对话（对话自动使用该教师的蒸馏风格）
4. 观看教师的教学视频

# M6 · Platform APP 外壳 — 详细方案

> **上游依赖**：M1-M5 全部
> **下游消费者**：教师 + 学生终端用户
> **关联总体方案**：`docs/EduNUWA_v2_总体方案.md` §3.6
> **版本**：v1.0 · 2026-05-15

---

## 1. 模块定位与边界

### 1.1 一句话定位

把 M1-M5 缝合成一个真正的产品，提供账号体系、API 网关、文件存储、教师端 APP、学生端 APP、计费（Phase 3）。

### 1.2 职责边界

| ✅ 必须做 | ❌ 严禁做 |
|---|---|
| 账号 + JWT 鉴权 | 业务逻辑（在 M1-M5 里） |
| HTTP API 网关（转发 M1-M5）| 重新实现 M1-M5 已有功能 |
| 教师端 APP（上传 / 预览 Skill / 发布）| Skill 蒸馏 / 评测（M2 做） |
| 学生端 APP（发现 / 学习 / 反馈）| 教学事件生成（M4 做）|
| 文件存储抽象 | 修改 M1-M5 输出文件 |
| 异步任务编排 | TTS / Live2D 渲染（M5 做）|
| `teacher_card.json` / `course_outline.json` 写入 | 蒸馏 / 编排 |
| 教师 / 课程 CRUD | 推荐排序（M3 做）|
| 学生反馈聚合到 stats（写回 teacher_card）| feedback 评分（M5 采集）|
| 计费（Phase 3）| 教师分成结算（外部财务）|

### 1.3 核心价值

- **M6 是用户视角的产品**：用户不知道 M1-M5 的存在
- **M6 是模块编排者**：触发 M1 摄取后串到 M2 蒸馏，再注册到 M3 catalog
- **M6 必须只做外壳**：业务逻辑严禁在 M6 实现

---

## 2. 子模块拆分与文件结构

```text
modules/M6_platform/
  backend/                        # 现有，重构
    main.py                       # FastAPI 入口
    config.py                     # 全局配置
    routes/
      auth.py                     # 注册 / 登录 / token
      teachers.py                 # 教师 CRUD
      uploads.py                  # 文件上传 + 触发 M1
      catalog.py                  # 转发 M3
      sessions.py                 # 学习 session 管理 + 转发 M4
      media.py                    # 静态文件（音频、avatar）
      feedback.py                 # 学生反馈
      tasks.py                    # 异步任务进度查询
    services/                     # 模块封装
      ingest_service.py           # 调 M1
      distill_service.py          # 调 M2
      catalog_service.py          # 调 M3
      orchestrator_service.py     # 调 M4
      runtime_service.py          # 调 M5
    models/                       # ORM
      user.py
      teacher.py
      course.py
      session.py
      task.py
    middleware/
      auth_middleware.py
      rate_limit.py
      cors.py
    storage/
      local_storage.py            # 文件系统（MVP）
      oss_storage.py              # 对象存储（Phase 2）
      storage_interface.py
    tasks/
      task_runner.py              # 异步任务执行器（celery 或 自研）
      orchestration.py            # M1→M2→M3 串联
  frontend_teacher/               # 新增（教师端）
    src/
      pages/
        Login.tsx
        Profile.tsx               # 个人信息
        Upload.tsx                # 上传素材
        SkillPreview.tsx          # 预览蒸馏出的 Skill
        SkillPublish.tsx          # 发布 / 软拒绝处理
        AvatarSettings.tsx
      api/                        # axios 封装
    package.json
  frontend_student/               # 现有 web_demo 升级
    src/
      pages/
        Login.tsx
        Discover.tsx              # 发现页（双轨）
        TeacherDetail.tsx         # 教师详情 + 雷达图
        Learn.tsx                 # 学习页（嵌入 M5 PlayerRuntime）
        Feedback.tsx              # 反馈页
      api/
    package.json
  scripts/
    init_db.py
    seed_demo_teachers.py
  README.md
  tests/
    test_auth.py
    test_routes.py
    test_orchestration.py
    e2e/
```

---

## 3. 详细接口

### 3.1 HTTP API 总览

所有 API `/api/v1/` 前缀，遵循总体方案 §4.3。

#### 认证（auth.py）

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register` | 注册（含 role: student/teacher）|
| POST | `/api/v1/auth/login` | 登录返回 JWT |
| POST | `/api/v1/auth/refresh` | 刷新 token |
| GET | `/api/v1/auth/me` | 当前用户 |

#### 教师（teachers.py）

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/teachers` | 创建教师（教师角色注册后自动）|
| PATCH | `/api/v1/teachers/{teacher_id}` | 更新 teacher_card |
| DELETE | `/api/v1/teachers/{teacher_id}` | 软删除 |

#### 上传（uploads.py）

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/uploads` | multipart 上传，返回 task_id；触发 M1 → M2 |
| GET | `/api/v1/tasks/{task_id}` | 查询进度 |
| POST | `/api/v1/uploads/{upload_id}/cancel` | 取消任务 |

#### 课程（courses.py）

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/courses` | 创建课程 |
| GET | `/api/v1/courses/{course_id}` | 课程详情 + outline |
| PATCH | `/api/v1/courses/{course_id}/outline` | 更新章节 |

#### 目录（catalog.py） — 转发 M3

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/teachers` | 列表（转发 M3）|
| GET | `/api/v1/teachers/{teacher_id}` | 详情（合并 teacher_card + skill_profile）|
| POST | `/api/v1/teachers/search` | 双轨搜索（转发 M3）|

#### 学习 session（sessions.py） — 转发 M4

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/sessions` | 创建 session |
| GET | `/api/v1/sessions/{session_id}` | session 详情 |
| POST | `/api/v1/sessions/{session_id}/turns` | 提问，触发 M4 + M5 |
| GET | `/api/v1/sessions/{session_id}/turns/{turn}/playback` | 拿播放数据 |
| GET | `/api/v1/sessions/{session_id}/turns/stream` | SSE 流式 events |

#### 反馈（feedback.py）

| Method | Path | 说明 |
|---|---|---|
| POST | `/api/v1/sessions/{session_id}/feedback` | 提交反馈，触发 M5.submit_feedback |

#### 媒体（media.py）

| Method | Path | 说明 |
|---|---|---|
| GET | `/static/audio/{session_id}/{turn}/{file}` | 音频静态资源 |
| GET | `/static/avatar/{teacher_id}/{file}` | avatar 资源 |

### 3.2 异步任务编排（关键流程）

```python
# tasks/orchestration.py

async def upload_and_distill(
    teacher_id: str,
    upload_paths: list[str],
) -> str:
    """
    完整链路:
      M1 ingest_teacher_material() 
      → M2 distill_teacher_skill_v2()
      → M3 reload_index()
      → 更新 teacher_card.current_skill_version
    
    Returns: task_id（立即返回，后台执行）
    """
    task_id = generate_task_id()
    asyncio.create_task(_run_pipeline(task_id, teacher_id, upload_paths))
    return task_id

async def _run_pipeline(task_id, teacher_id, upload_paths):
    try:
        update_progress(task_id, 0.0, "ingesting")
        ingest_result = await call_in_thread(
            ingest_service.ingest_teacher_material,
            teacher_id, upload_paths,
            f"data/teachers/{teacher_id}/"
        )
        if ingest_result["status"] != "success":
            update_failed(task_id, ingest_result["message"])
            return
        
        update_progress(task_id, 0.4, "distilling")
        distill_result = await call_in_thread(
            distill_service.distill_teacher_skill_v2,
            teacher_id, ingest_result["transcripts"],
            _next_skill_version_dir(teacher_id)
        )
        ...
        
        update_progress(task_id, 0.95, "reindexing")
        catalog_service.reload_index()
        
        update_done(task_id, ...)
    except Exception as e:
        update_failed(task_id, str(e))
```

### 3.3 学生学习一轮的 API 序列

```
POST /api/v1/sessions
  body: { teacher_id, course_id, mode: "ondemand" }
  → 返回 session_id

POST /api/v1/sessions/{session_id}/turns
  body: { question: "什么是过拟合？" }
  → 内部:
       1. 转发 M4.generate_teaching_events_v2() 拿到 events_path
       2. 调 M5.generate_tts_batch() 拿到 audio_manifest
       3. 调 M5.build_playback_data() 拿到 playback_data
  → 返回 { turn: 1, playback_url: "/api/v1/sessions/{sid}/turns/1/playback" }

GET /api/v1/sessions/{session_id}/turns/1/playback
  → 返回 playback_data.json（前端 player 加载）

POST /api/v1/sessions/{session_id}/feedback
  body: { rating, comment, fingerprint_feedback, pedagogy_feedback }
  → 调 M5.submit_feedback()
```

### 3.4 数据库 schema（核心表）

```sql
-- users
id (PK), username, password_hash, email, role (student/teacher), created_at

-- teachers (1:1 with user where role=teacher)
teacher_id (PK, T_xxx), user_id (FK), real_name, display_name,
subject, bio, avatar_pixel_url, live2d_model_id, voice_id,
current_skill_version, created_at, updated_at, deleted_at

-- courses
course_id (PK), title, owner_user_id, created_at

-- sessions
session_id (PK), student_user_id (FK), teacher_id (FK), course_id (FK),
mode, status (active/ended), started_at, ended_at

-- tasks
task_id (PK), task_type, owner_user_id, status, progress,
stage, result_json, error_msg, created_at, updated_at
```

---

## 4. 输入文件契约

### 4.1 上游模块输出

| 来自 | 文件 | 用途 |
|---|---|---|
| M1 | `transcripts/*.json` | 摄取后写回 task 的 result |
| M2 | `skill_profile_v2.json` | 教师端预览页展示，更新 `current_skill_version` |
| M2 | `eval_report.json` | 教师端发布页展示 grade |
| M3 | search 结果 | 转发到学生端 catalog 页 |
| M4 | `teaching_events.json` | 转发到学生端 player |
| M5 | `audio_manifest.json` + `playback_data.json` | 静态服务 |

### 4.2 与所有模块的契约一致性自检

| 检查点 | 状态 |
|---|---|
| ✅ 所有 API 路径 `/api/v1/` 前缀 | 与总体方案 §4.3.1 一致 |
| ✅ 响应格式 `{code, message, data}` | 与总体方案 §4.3.2 一致 |
| ✅ 状态码区段 | 与总体方案 §4.3.3 一致 |
| ✅ 异步任务 status 枚举 `pending/running/success/failed/cancelled` | 与总体方案 §4.3.4 一致 |
| ✅ M1 task_id 协议（progress, stage） | 与 M1 §3.5 一致 |
| ✅ teacher_id / course_id / session_id 命名 | 与总体方案 §5.2 一致 |
| ✅ teacher_card.json schema | 与总体方案 §5.5 一致 |
| ✅ course_outline.json schema | 与总体方案 §5.5 一致 |
| ✅ 调用 M3 search API 的字段 | 与 M3 §3.2 一致 |
| ✅ 调用 M4 generate_teaching_events_v2() 的参数 | 与 M4 §3.1 一致 |
| ✅ 调用 M5 generate_tts_batch() 的参数 | 与 M5 §3.1 一致 |
| ✅ 反馈 schema | 与 M5 §5.4 一致 |

---

## 5. 输出文件契约

### 5.1 M6 必须产出 / 维护

| 文件 | 路径 | 何时写入 |
|---|---|---|
| `teacher_card.json` | `data/teachers/{tid}/teacher_card.json` | 教师注册 / 资料更新 / 反馈聚合 |
| `course_outline.json` | `data/courses/{cid}/course_outline.json` | 教师创建课程 / 编辑章节 |
| 上传文件 | `data/teachers/{tid}/uploads/{upload_id}/*` | 学生上传时 |
| db 数据 | sqlite/postgres | 业务操作 |

### 5.2 M6 不允许写

| 文件 | 责任模块 |
|---|---|
| `transcripts/*.json` | M1 |
| `TeacherSkill.md` / `skill_profile_v2.json` | M2 |
| `eval_report.json` | M2 |
| `teaching_events.json` / `session_state.json` | M4 |
| `audio_manifest.json` / `playback_data.json` / 音频 | M5 |
| `feedback.json` | M5 |

---

## 6. 硬性要求（不可妥协）

| # | 硬性要求 | 验证方法 |
|---|---|---|
| H1 | 所有 API 必须 `/api/v1/` 前缀；版本必须前置 | 路由扫描 |
| H2 | 响应格式必须 `{code, message, data}`，错误也是 | middleware 强制 |
| H3 | 必须 JWT 鉴权（除 `/auth/register` `/auth/login` 外）| middleware 强制 |
| H4 | 长任务必须 **异步**（task_id 模式），同步阻塞 > 5s 视为不合规 | 性能测试 |
| H5 | M6 不允许实现业务逻辑（蒸馏 / 编排 / 渲染 / 评分等）| code review + import 扫描 |
| H6 | 文件存储必须经过 `storage_interface`，禁止裸 `open()` 写文件 | 静态扫描 |
| H7 | 严禁 M6 直接读写 M2/M4/M5 的产物文件中由它们 owns 的字段 | code review |
| H8 | 教师端必须显示 Skill grade，且 < B 的发布需二次确认 | E2E 测试 |
| H9 | 学生端必须显示 fingerprint_confidence | E2E 测试 |
| H10 | 上传必须支持断点续传 / 分片（视频可达 GB 级别）| 集成测试 |
| H11 | 文件路径返回给前端时必须经过 `/static/...` 路由，不能暴露 `data/...` 物理路径 | 安全审计 |
| H12 | 必须支持优雅关闭（接收 SIGTERM 后等待异步任务完成最多 30s）| 集成测试 |
| H13 | 数据库 migration 必须可回滚 | code review |
| H14 | 不允许在 API 处理函数中做 LLM / TTS 等长耗时调用（应转任务）| code review |

---

## 7. 验收标准

### 7.1 MVP（Phase 1 结束时）

| # | 指标 | 标准 | 测试方法 |
|---|---|---|---|
| A1 | 学生注册 → 学习 → 反馈全流程 | 100% 跑通 | E2E |
| A2 | 教师注册 → 上传 → 预览 Skill 全流程 | 100% 跑通 | E2E |
| A3 | API p95 latency（不含 LLM/TTS）| < 500ms | k6 |
| A4 | JWT 鉴权 | 必须 | 安全测试 |
| A5 | 同时在线学生 | ≥ 10 | 压力测试 |
| A6 | 异步任务进度查询 | 准确 | 集成测试 |
| A7 | 双轨发现 UI（by_name + by_style）| 都可用 | E2E |
| A8 | 学生端嵌入 M5 PlayerRuntime | ✅ | E2E |

### 7.2 Phase 1 → Phase 2

| # | 指标 | 标准 |
|---|---|---|
| A1-2 | 全流程稳定性 | 99% |
| A3 | API p95 | < 200ms |
| A5 | 同时在线 | ≥ 100 |
| A9 | 教师端编辑 Skill 多版本管理 | ✅ |
| A10 | 邮箱验证 | ✅ |
| A11 | 切对象存储 | ✅ |

### 7.3 Phase 3

| # | 指标 | 标准 |
|---|---|---|
| A3 | API p95 | < 100ms |
| A5 | 同时在线 | ≥ 1000 |
| A12 | 计费 / 订阅 | ✅ |
| A13 | OAuth 登录 | ✅ |

---

## 8. 与其他模块的接口

### 8.1 输入来源

| 来源 | 内容 | 协议 |
|---|---|---|
| **教师端** | 注册 / 上传 / 编辑 | HTTP |
| **学生端** | 注册 / 发现 / 学习 / 反馈 | HTTP |
| **M1** | task 进度 | Python 函数 |
| **M2** | task 进度 + grade | Python 函数 |
| **M3** | search 结果 | Python 函数 |
| **M4** | events / session_state | Python 函数 |
| **M5** | playback_data | Python 函数 |

### 8.2 输出去向

| 去向 | 内容 | 协议 |
|---|---|---|
| **M1** | 触发 ingest | Python 函数 |
| **M2** | 触发蒸馏 | Python 函数 |
| **M3** | 触发 reload_index | Python 函数 |
| **M4** | 触发 generate_teaching_events_v2 | Python 函数 |
| **M5** | 触发 generate_tts_batch / build_playback_data / submit_feedback | Python 函数 |

### 8.3 接口契约一致性自检（与所有模块）

详见 §4.2 表。**M6 owner 在每次模块对接时必须勾选确认。**

---

## 9. 关键技术挑战与实现指导

### 9.1 模块编排（H5 的边界守护）

```python
# good: M6 只编排
async def _run_pipeline(...):
    ingest_result = await call_in_thread(ingest_service.ingest_teacher_material, ...)
    distill_result = await call_in_thread(distill_service.distill_teacher_skill_v2, ...)

# bad: M6 实现业务
async def _run_pipeline(...):
    transcript = whisper.transcribe(...)  # ❌ 这是 M1 的事
    skill = llm.distill(...)              # ❌ 这是 M2 的事
```

### 9.2 文件存储抽象（H6）

```python
# storage/storage_interface.py
class Storage(Protocol):
    def save(self, key: str, data: bytes) -> str: ...     # 返回 url / path
    def load(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def get_url(self, key: str) -> str: ...

# MVP: LocalStorage 包装文件系统
# Phase 2: OSSStorage 包装阿里云 OSS

# 业务代码
storage = get_storage()  # 从 config 读决定哪个实现
audio_url = storage.get_url(f"audio/{session_id}/{evt}.wav")
```

### 9.3 异步任务系统选型

**MVP**：自研基于 asyncio + DB 表，简单可控
**Phase 2**：Celery + Redis broker
**禁止**：在 API handler 中直接 `await` 长任务（H14）

### 9.4 安全静态资源（H11）

```python
# routes/media.py
@router.get("/static/audio/{session_id}/{turn}/{filename}")
async def serve_audio(session_id, turn, filename, user=Depends(auth)):
    # 验证用户有权访问该 session
    if not user_can_access_session(user, session_id):
        raise HTTPException(403)
    
    path = f"data/sessions/{session_id}/audio/turn_{turn}/{filename}"
    if not Path(path).exists():
        raise HTTPException(404)
    
    return FileResponse(path)  # 不暴露 path 给前端
```

### 9.5 教师端 Skill 发布流程

```typescript
// frontend_teacher/SkillPublish.tsx
const grade = skillProfile.quality.overall_grade;

if (gradeOrder(grade) < gradeOrder("B")) {
  // 软拒绝：必须二次确认
  showConfirmDialog(`您的 Skill grade 为 ${grade}，低于推荐阈值。
    发布后将不会出现在默认 catalog。是否仍要发布？`);
}
```

---

## 10. 风险与对策

| 风险 | 概率 | 影响 | 对策 |
|---|---|---|---|
| M6 owner 把业务逻辑写进 routes | 高 | 高 | H5 + H7 + 双 owner code review |
| 大文件上传超时 | 高 | 高 | H10 分片 + 断点续传 |
| 静态文件被未授权访问 | 中 | 高 | H11 强制 auth |
| 异步任务僵死 | 中 | 中 | task_id 加超时 + 自动清理 |
| 数据库 schema 变更频繁 | 中 | 中 | H13 migration 工具（alembic） |
| 跨 session 数据串号 | 低 | 高 | 统一 user_id 注入到所有 query |
| 前后端联调阻塞 | 高 | 中 | 提前定 API mock；Phase 0 就要 |

---

## 11. 本地开发与测试

### 11.1 后端启动

```bash
cd modules/M6_platform/backend
python -m main  # uvicorn main:app --reload
# 默认 http://localhost:8000
```

### 11.2 前端启动

```bash
cd modules/M6_platform/frontend_student
npm install && npm run dev  # http://localhost:5173

cd modules/M6_platform/frontend_teacher
npm install && npm run dev  # http://localhost:5174
```

### 11.3 必须提供的测试

```text
tests/
  test_auth.py                # H3
  test_routes.py              # H1 H2
  test_async_tasks.py         # H4
  test_storage_abstraction.py # H6
  test_static_security.py     # H11
  test_no_business_logic.py   # H5 静态扫描
  e2e/
    test_student_flow.spec.ts
    test_teacher_flow.spec.ts
    test_skill_publish_low_grade.spec.ts  # H8
```

### 11.4 CI 检查项

- 所有 routes 加 /api/v1/ 前缀
- 所有 routes 含 auth dependency（除白名单）
- 静态扫描 import: M6 routes 不直接 import LLM SDK
- API schema 文档自动生成（OpenAPI）

---

## 12. Phase 0 启动清单

| # | 任务 | 完成判据 |
|---|---|---|
| 1 | 现有 `backend/main.py` 升级为带路由 / 中间件 / DB 的骨架 | 能跑且能登陆 |
| 2 | 实现 `auth.py` + JWT | 能注册 / 登录 |
| 3 | 实现 `teachers.py` (CRUD) + `teacher_card.json` 文件写入 | 教师能创建 |
| 4 | 实现 `tasks.py` 异步任务系统骨架 | 能 mock submit / poll |
| 5 | 实现 `media.py` 安全静态资源 | M5 音频可访问 |
| 6 | 教师端 / 学生端 Login + Discover 页面 | 能跑通登录到列表 |
| 7 | 与所有模块 owner 对齐 service 包装 | 6 份 README 互相引用 |

---

**END OF M6 DOCUMENT**

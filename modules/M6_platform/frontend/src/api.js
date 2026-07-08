const BASE = "/api/v1";

function headers() {
  const h = {};
  const token = localStorage.getItem("token");
  if (token) h["Authorization"] = `Bearer ${token}`;
  return h;
}

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, { ...options, headers: { ...headers(), ...options.headers } });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message || "请求失败");
  return json.data;
}

export async function register(username, password, role) {
  return request("/auth/register", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password, role }),
  });
}

export async function login(username, password) {
  return request("/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
}

export async function getMe() {
  try {
    return await request("/auth/me");
  } catch {
    return null;
  }
}

// 教师相关
export async function getTeachers(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`/teachers?${qs}`);
}

export async function getTeacher(teacherId) {
  return request(`/teachers/${teacherId}`);
}

export async function createTeacherCard(data) {
  return request("/teachers", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function updateTeacherCard(teacherId, data) {
  return request(`/teachers/${teacherId}`, {
    method: "PUT", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function getMyTeacher() {
  return request("/my/teacher");
}

// 教师头像上传（multipart）
export async function uploadTeacherAvatar(teacherId, file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/teachers/${teacherId}/avatar`, {
    method: "POST", headers: { Authorization: headers().Authorization }, body: form,
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

// 素材上传
export async function uploadMaterial(file, refine = true) {
  const form = new FormData();
  form.append("file", file);
  form.append("refine", refine ? "true" : "false");
  const res = await fetch(`${BASE}/uploads`, {
    method: "POST", headers: { Authorization: headers().Authorization }, body: form,
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

export async function queryTask(taskId) {
  return request(`/tasks/${taskId}`);
}

// 素材管理（原始件入库 + 勾选批处理）
export async function getMaterials(teacherId) {
  return request(`/teachers/${teacherId}/materials`);
}

export async function uploadRawMaterial(teacherId, file, title) {
  const form = new FormData();
  form.append("file", file);
  if (title) form.append("title", title);
  const res = await fetch(`${BASE}/teachers/${teacherId}/materials`, {
    method: "POST", headers: { Authorization: headers().Authorization }, body: form,
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

export async function processMaterials(teacherId, materialIds, enableRefine = true) {
  return request(`/teachers/${teacherId}/materials/process`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ material_ids: materialIds, enable_refine: enableRefine }),
  });
}

export async function deleteMaterial(teacherId, materialId) {
  return request(`/teachers/${teacherId}/materials/${materialId}`, { method: "DELETE" });
}

// 视频
export async function uploadVideo(file, title, description) {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("description", description);
  const res = await fetch(`${BASE}/videos/upload`, {
    method: "POST", headers: { Authorization: headers().Authorization }, body: form,
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

export async function getVideos(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return request(`/videos?${qs}`);
}

export async function getVideo(videoId) {
  return request(`/videos/${videoId}`);
}

export async function deleteVideo(videoId) {
  return request(`/videos/${videoId}`, { method: "DELETE" });
}

export async function getTeacherVideos(teacherId) {
  return request(`/teachers/${teacherId}/videos`);
}

export function getVideoStreamUrl(videoId) {
  return `${BASE}/videos/${videoId}/stream`;
}

// 聊天
export async function sendMessage(teacherId, message) {
  return request(`/chat/${teacherId}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function getChatHistory(teacherId) {
  return request(`/chat/${teacherId}/history`);
}

export async function clearChatHistory(teacherId) {
  return request(`/chat/${teacherId}/history`, { method: "DELETE" });
}

// Skill 和 Transcripts
export async function getTeacherSkill(teacherId) {
  return request(`/teachers/${teacherId}/skill`);
}

export async function getTeacherTranscripts(teacherId) {
  return request(`/teachers/${teacherId}/transcripts`);
}

export async function getTranscriptDetail(teacherId, transcriptId) {
  return request(`/teachers/${teacherId}/transcripts/${encodeURIComponent(transcriptId)}`);
}

export async function getSkillVersions(teacherId) {
  return request(`/teachers/${teacherId}/skills`);
}

export async function getSkillVersion(teacherId, versionDir) {
  return request(`/teachers/${teacherId}/skills/${encodeURIComponent(versionDir)}`);
}

export async function getDistillStatus(teacherId) {
  return request(`/teachers/${teacherId}/distill/status`);
}

export async function distillTeacher(teacherId) {
  return request(`/teachers/${teacherId}/distill`, { method: "POST" });
}

// M3 风格匹配
// 成功后把 match_id 暂存 sessionStorage：学生稍后对推荐出的老师写评价时，
// submitFeedback 会自动带上 match_id，形成「推荐→反馈→skill 进化」闭环。
const LAST_MATCH_KEY = "edunuwa_last_match";
const MATCH_TTL_MS = 30 * 60 * 1000; // 30 分钟内的评价才算可归因于本次推荐

export async function matchTeachers(query) {
  const data = await request("/match", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  try {
    if (data?.match_id) {
      sessionStorage.setItem(LAST_MATCH_KEY, JSON.stringify({
        match_id: data.match_id,
        teacher_ids: (data.rankings || []).map((r) => r.teacher_id),
        ts: Date.now(),
      }));
    }
  } catch { /* sessionStorage 不可用时静默放弃归因 */ }
  return data;
}

function getAttributableMatch(teacherId) {
  try {
    const raw = sessionStorage.getItem(LAST_MATCH_KEY);
    if (!raw) return null;
    const m = JSON.parse(raw);
    if (Date.now() - m.ts > MATCH_TTL_MS) return null;
    if (!m.teacher_ids?.includes(teacherId)) return null;
    return m.match_id;
  } catch {
    return null;
  }
}

// M4/M5 学习会话
export async function createSession(teacherId, mode = "ondemand") {
  return request("/sessions", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ teacher_id: teacherId, mode }),
  });
}

export async function sessionAsk(sessionId, question) {
  return request(`/sessions/${sessionId}/ask`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function getSession(sessionId) {
  return request(`/sessions/${sessionId}`);
}

export async function getSessionEvents(sessionId, turn) {
  return request(`/sessions/${sessionId}/events/${turn}`);
}

export async function generateSessionTTS(sessionId, turn = 1) {
  return request(`/sessions/${sessionId}/tts`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turn }),
  });
}

export async function buildSessionPlayback(sessionId, turn = 1) {
  return request(`/sessions/${sessionId}/playback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turn }),
  });
}

export async function listSessions() {
  return request("/sessions");
}

// M5 教学演示
export async function teachingDemo(teacherId, question) {
  return request(`/chat/${teacherId}/demo`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

// M5 教学演示（流式）：LLM 边生成边以 SSE 推送 events。
// 帧序列 meta → event×N → summary → done，异常发 error（partial=已有部分事件）。
// 用 fetch+ReadableStream 而非 EventSource，因为需要 POST + Authorization header。
// meta 帧之前的失败直接 throw（调用方可降级到非流式 teachingDemo）。
export async function teachingDemoStream(teacherId, question,
  { onMeta, onEvent, onSummary, onError, onDone, signal } = {}) {
  const res = await fetch(`${BASE}/chat/${teacherId}/demo/stream`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  const ctype = res.headers.get("content-type") || "";
  if (!res.ok || !ctype.includes("text/event-stream")) {
    // 流开始前的校验失败仍是标准 {code,message} JSON
    const j = await res.json().catch(() => null);
    throw new Error(j?.message || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const dispatch = (frame) => {
    let eventType = "message";
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith(":")) continue; // 保活注释帧
      if (line.startsWith("event:")) eventType = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    let payload;
    try { payload = JSON.parse(data); } catch { return; }
    if (eventType === "meta") onMeta?.(payload);
    else if (eventType === "event") onEvent?.(payload);
    else if (eventType === "summary") onSummary?.(payload);
    else if (eventType === "error") onError?.(payload);
    else if (eventType === "done") onDone?.(payload);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      if (frame.trim()) dispatch(frame);
    }
  }
}

// M5 TTS
export async function textToSpeech(text, teacherId) {
  const res = await fetch(`${BASE}/tts`, {
    method: "POST", headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify({ text, teacher_id: teacherId }),
  });
  if (!res.ok) {
    const json = await res.json();
    throw new Error(json.message || "TTS failed");
  }
  return res.blob();
}

export async function getVoices() {
  return request("/voices");
}

// 教师专属音色训练 + 多参数试听选择
export async function getVoiceStatus(teacherId) {
  return request(`/teachers/${teacherId}/voice/status`);
}

export async function startVoiceTraining(teacherId, epochs) {
  return request(`/teachers/${teacherId}/voice/train`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(epochs ? { epochs } : {}),
  });
}

export async function getVoiceTrainStatus(teacherId) {
  return request(`/teachers/${teacherId}/voice/train/status`);
}

export async function generateVoicePreviews(teacherId, text) {
  return request(`/teachers/${teacherId}/voice/previews`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(text ? { text } : {}),
  });
}

export async function chooseVoicePreview(teacherId, previewId) {
  return request(`/teachers/${teacherId}/voice/choose`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preview_id: previewId }),
  });
}

export function getAudioUrl(relPath) {
  return `${BASE}/audio/${relPath}`;
}

// 课堂预录制 / 课程
export async function createCourse(teacherId, data) {
  return request(`/teachers/${teacherId}/courses`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
}

export async function listCourses(teacherId) {
  return request(`/teachers/${teacherId}/courses`);
}

export async function getCourseDetail(teacherId, courseId) {
  return request(`/teachers/${teacherId}/courses/${courseId}`);
}

export async function publishCourse(teacherId, courseId) {
  return request(`/teachers/${teacherId}/courses/${courseId}/publish`, { method: "POST" });
}

export async function deleteCourse(teacherId, courseId) {
  return request(`/teachers/${teacherId}/courses/${courseId}`, { method: "DELETE" });
}

// 教学插图库（教师端：上传 + 一句话 LLM 扩写 + 入库 + 启停/删除）
export async function getImageSubjects() {
  return request("/images/subjects");
}

export async function listTeachingImages(mine = false) {
  return request(`/images${mine ? "?mine=1" : ""}`);
}

// 生成元数据 → {topic, keywords[], llm_desc, caption, _engine}。
// 视觉优先：传图 + 配了 DASHSCOPE_API_KEY 时后端用 Qwen-VL 直接看图；
// 否则/识图失败时退回 DeepSeek 文本扩写（需 brief）。brief 可空。
export async function annotateTeachingImage(file, brief, subject) {
  const form = new FormData();
  if (file) form.append("file", file);
  if (brief) form.append("brief", brief);
  form.append("subject", subject || "");
  const res = await fetch(`${BASE}/images/annotate`, {
    method: "POST", headers: { Authorization: headers().Authorization }, body: form,
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

// 上传 .pptx → 后端抽内嵌图 + 视觉逐张判断，SSE 流式逐张推送（边出边展示、实时计数）。
// 帧序列：meta（{total,to_process,truncated}）→ kept|dropped × N → done（{kept,dropped,total,truncated}）。
//   kept   {name, media_type, image_b64, subject, topic, keywords[], llm_desc, caption, reason}
//   dropped{name, mime, image_b64(小缩略), reason}
// 用 fetch+ReadableStream（需 POST + Authorization，不能用 EventSource）。
// 流开始前的校验失败仍是标准 {code,message} JSON，直接 throw。
export async function extractPptImagesStream(file,
  { onMeta, onKept, onDropped, onDone, onError, signal } = {}) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/images/extract-ppt`, {
    method: "POST", headers: { Authorization: headers().Authorization }, body: form, signal,
  });
  const ctype = res.headers.get("content-type") || "";
  if (!res.ok || !ctype.includes("text/event-stream")) {
    const j = await res.json().catch(() => null);
    throw new Error(j?.message || `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  const dispatch = (frame) => {
    let eventType = "message";
    let data = "";
    for (const line of frame.split("\n")) {
      if (line.startsWith(":")) continue; // 保活注释帧
      if (line.startsWith("event:")) eventType = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    let payload;
    try { payload = JSON.parse(data); } catch { return; }
    if (eventType === "meta") onMeta?.(payload);
    else if (eventType === "kept") onKept?.(payload);
    else if (eventType === "dropped") onDropped?.(payload);
    else if (eventType === "error") onError?.(payload);
    else if (eventType === "done") onDone?.(payload);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let sep;
    while ((sep = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, sep);
      buf = buf.slice(sep + 2);
      if (frame.trim()) dispatch(frame);
    }
  }
}

// 提交图片 + 最终元数据（multipart）。meta: {subject, topic, keywords, llm_desc, caption}
export async function uploadTeachingImage(file, meta) {
  const form = new FormData();
  form.append("file", file);
  form.append("subject", meta.subject || "");
  form.append("topic", meta.topic || "");
  form.append("keywords", Array.isArray(meta.keywords) ? meta.keywords.join("，") : (meta.keywords || ""));
  form.append("llm_desc", meta.llm_desc || "");
  form.append("caption", meta.caption || "");
  const res = await fetch(`${BASE}/images`, {
    method: "POST", headers: { Authorization: headers().Authorization }, body: form,
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message);
  return json.data;
}

export async function updateTeachingImage(imageId, patch) {
  return request(`/images/${imageId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
}

export async function deleteTeachingImage(imageId) {
  return request(`/images/${imageId}`, { method: "DELETE" });
}

// 评价
export async function getFeedback(teacherId) {
  return request(`/teachers/${teacherId}/feedback`);
}

export async function submitFeedback(teacherId, data) {
  // 若该老师来自 30 分钟内的一次推荐，自动附上 match_id（调用方显式传入的优先）
  const body = { ...data };
  if (!body.match_id) {
    const matchId = getAttributableMatch(teacherId);
    if (matchId) {
      body.match_id = matchId;
      if (!body.context) body.context = "match";
    }
  }
  return request(`/teachers/${teacherId}/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// 进化闭环（skill 自进化）
export async function getEvolutionStatus(teacherId) {
  return request(`/teachers/${teacherId}/evolution/status`);
}

export async function triggerEvolutionRefresh(teacherId) {
  return request(`/teachers/${teacherId}/evolution/refresh`, { method: "POST" });
}

export async function triggerRevision(teacherId) {
  return request(`/teachers/${teacherId}/evolution/revise`, { method: "POST" });
}

export async function getRevision(teacherId) {
  return request(`/teachers/${teacherId}/evolution/revision`);
}

export async function confirmRevision(teacherId) {
  return request(`/teachers/${teacherId}/evolution/revision/confirm`, { method: "POST" });
}

export async function rejectRevision(teacherId) {
  return request(`/teachers/${teacherId}/evolution/revision/reject`, { method: "POST" });
}

// ───────────────────────── 平台监控台（只读） ─────────────────────────
// 与师生账号体系隔离：不带 Authorization，改带 X-Platform-Key（独立口令）。
function platformHeaders() {
  const key = localStorage.getItem("platform_key");
  return key ? { "X-Platform-Key": key } : {};
}

async function platformRequest(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    ...options,
    headers: { ...platformHeaders(), ...options.headers },
  });
  let json;
  try { json = await res.json(); } catch { json = {}; }
  if (res.status === 403) {
    // 口令失效/被改：清掉本地口令，让壳层退回口令页
    localStorage.removeItem("platform_key");
    throw new Error(json.message || "平台口令无效");
  }
  if (json.code !== 0) throw new Error(json.message || "请求失败");
  return json.data;
}

// 校验口令（登录页入口用）；成功不抛错。
export async function platformAuth(key) {
  const res = await fetch(`${BASE}/platform/auth`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  const json = await res.json();
  if (json.code !== 0) throw new Error(json.message || "平台口令无效");
  return json.data;
}

export const getPlatformOverview = () => platformRequest("/platform/overview");
export const getPlatformUsers = (params = {}) =>
  platformRequest(`/platform/users?${new URLSearchParams(params).toString()}`);
export const getPlatformStudent = (uid) => platformRequest(`/platform/students/${uid}`);
export const getPlatformTeachers = () => platformRequest("/platform/teachers");
export const getPlatformTeacher = (tid) => platformRequest(`/platform/teachers/${tid}`);
export const getPlatformSessions = () => platformRequest("/platform/sessions");
export const getPlatformFeedback = () => platformRequest("/platform/feedback");
export const getPlatformMatches = () => platformRequest("/platform/matches");
export const getPlatformMedia = () => platformRequest("/platform/media");

// —— 管控（写操作） ——
const _pfJson = (body) => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const platformDeleteUser = (uid) => platformRequest(`/platform/users/${uid}`, { method: "DELETE" });
export const platformResetPassword = (uid, password) => platformRequest(`/platform/users/${uid}/password`, _pfJson({ password }));
export const platformSetTeacherVisibility = (tid, hidden) => platformRequest(`/platform/teachers/${tid}/visibility`, _pfJson({ hidden }));
export const platformAssignAccount = (tid) => platformRequest(`/platform/teachers/${tid}/account`, { method: "POST" });
export const platformSetCoursePublish = (tid, cid, published) => platformRequest(`/platform/courses/${tid}/${cid}/publish`, _pfJson({ published }));
export const platformDeleteCourse = (tid, cid) => platformRequest(`/platform/courses/${tid}/${cid}`, { method: "DELETE" });
export const platformDeleteFeedback = (tid, fid) => platformRequest(`/platform/feedback/${tid}/${fid}`, { method: "DELETE" });
export const platformSetMediaStatus = (id, status) => platformRequest(`/platform/media/${id}/status`, _pfJson({ status }));
export const platformDeleteMedia = (id) => platformRequest(`/platform/media/${id}`, { method: "DELETE" });

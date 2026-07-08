import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { getTeacher, sendMessage, getChatHistory, teachingDemo, teachingDemoStream, submitFeedback } from '../api'
import MiniMarkdown from '../components/MiniMarkdown'
import './VirtualClassroom.css'

// 历史里 kind==='demo' 的讲课条目归一成可回看气泡：标 isDemo、把 session_id 升为 sessionId、
// 标 done（历史即已讲完）。带 sessionId 的条目才显示「回看板书」（链接到那节课 events.json）。
function normalizeHistory(msgs) {
  return (msgs || []).map(m =>
    m.kind === 'demo'
      ? { ...m, isDemo: true, sessionId: m.session_id || m.sessionId || null, done: true }
      : m)
}

// 流式教学演示开关：false 时回退到旧的非流式 /demo 全量链路
const USE_DEMO_STREAM = true

// 冷启动引导：据学科派生 3 个示例问题（点击填入输入框，降低「不知道问什么」门槛）
function buildExampleQuestions(teacher) {
  const s = teacher?.subject
  if (s) {
    return [`${s}是什么？`, `${s}在生活中有什么用？`, `能举个例子讲讲${s}吗？`]
  }
  return ['这门课最核心的概念是什么？', '能举个生活中的例子吗？', '初学者最容易搞错什么？']
}

export default function VirtualClassroom() {
  const { teacherId } = useParams()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // 教师从工作台进入「虚拟课堂试讲」时走 /teacher/classroom：屏蔽给自己打分的课后评价条
  const isTeacherView = pathname.startsWith('/teacher')
  const [teacher, setTeacher] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState(null)
  // 固定双槽 iframe：两个元素永不换位/换 key（React 移动 iframe 节点会触发
  // 浏览器强制 reload，push 模式下会丢掉已推送的事件），只切换前后台 CSS
  const [frames, setFrames] = useState({ A: null, B: null })
  const [frontSlot, setFrontSlot] = useState('A')
  const [tags, setTags] = useState([])
  const [panelOpen, setPanelOpen] = useState(true)
  const [tagsOpen, setTagsOpen] = useState(false)   // 风格标签折叠态
  const inputRef = useRef(null)
  // 数字人浮层：可拖动 + 可隐藏到侧栏；口型由 M5 经 postMessage 回传驱动
  const [avatarHidden, setAvatarHidden] = useState(false)
  const [avatarPos, setAvatarPos] = useState(null)  // {left,top} px（相对舞台）；null=默认右下角
  const [speaking, setSpeaking] = useState(false)
  const avatarRef = useRef(null)
  const stageRef = useRef(null)
  const dragRef = useRef(null)
  // 课后评价条：讲课流结束后浮出（rate.sessionId 关联本次讲课，进化闭环用）
  const [rate, setRate] = useState(null)       // { sessionId } | null
  const [rateStars, setRateStars] = useState(0)
  const [rateText, setRateText] = useState('')
  const [rateBusy, setRateBusy] = useState(false)
  const bottomRef = useRef(null)
  const frameRefs = { A: useRef(null), B: useRef(null) }
  const framesRef = useRef(frames)
  const frontSlotRef = useRef(frontSlot)
  const streamRef = useRef(null)  // 当前流式会话状态 { sessionId, slot, buffer, done, ready, ctl, demoId }
  framesRef.current = frames
  frontSlotRef.current = frontSlot

  useEffect(() => {
    (async () => {
      try {
        const t = await getTeacher(teacherId)
        setTeacher(t)
        setTags(t.tags || [])
        localStorage.setItem('lastTeacherId', teacherId)  // 记住「上次使用的老师」
        const msgs = await getChatHistory(teacherId)
        setMessages(normalizeHistory(msgs))
      } catch (e) { navigate(isTeacherView ? '/teacher' : '/student') }
    })()
  }, [teacherId])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  // 离开页面时中断进行中的流
  useEffect(() => () => { streamRef.current?.ctl?.abort() }, [])

  // 切换老师：路由 /classroom/:teacherId 只换 param、组件被复用（不重挂载），
  // 必须手动硬停上一节课——否则旧课的 M5 iframe 仍活着、StreamingPlayer 会继续
  // 一句句向 /api/v1/tts 要音频，占满单实例 GPU TTS，把新老师的讲课（连同那条
  // DeepSeek 流式调用）拖到超时。这里中止旧流 + 卸载旧 iframe（停掉旧课 TTS 驱动）。
  const prevTeacherRef = useRef(teacherId)
  useEffect(() => {
    if (prevTeacherRef.current === teacherId) return
    prevTeacherRef.current = teacherId
    streamRef.current?.ctl?.abort()
    streamRef.current = null
    setFrames({ A: null, B: null })
    setSessionId(null)
    setSpeaking(false)
    setRate(null)
    setLoading(false)
  }, [teacherId])

  const postToSlot = (slot, msg) => {
    const st = streamRef.current
    const win = frameRefs[slot]?.current?.contentWindow
    if (!win || !st) return
    win.postMessage({ source: 'edunuwa', session: st.sessionId, ...msg }, window.location.origin)
  }

  // iframe → 父页面消息：m5:ready 握手后推送全量 buffer（重复 ready 重发全量，
  // iframe 意外 reload 时自愈；M5 侧按 seq 去重）
  useEffect(() => {
    const onMsg = (ev) => {
      if (ev.origin !== window.location.origin) return
      const msg = ev.data
      if (!msg || msg.source !== 'edunuwa') return
      const st = streamRef.current
      if (!st || msg.session !== st.sessionId) return
      if (msg.type === 'm5:ready') {
        st.ready = true
        postToSlot(st.slot, { type: 'm6:init', events: st.buffer, done: st.done })
      } else if (msg.type === 'm5:speaking') {
        setSpeaking(!!msg.value)   // 驱动浮层数字人口型动画
      } else if (msg.type === 'm5:end') {
        setSpeaking(false)
      }
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

  // 后台槽 iframe 加载完成 → 切为前台、清空旧槽（停掉旧课音频）
  const handleFrameLoad = (slot) => {
    if (!framesRef.current[slot] || frontSlotRef.current === slot) return
    setFrontSlot(slot)
    const other = slot === 'A' ? 'B' : 'A'
    setFrames(prev => ({ ...prev, [other]: null }))
  }

  const backSlot = () => (frontSlotRef.current === 'A' ? 'B' : 'A')

  const updateDemoBubble = (demoId, content) => {
    setMessages(prev => prev.map(m => (m.demoId === demoId ? { ...m, content } : m)))
  }

  // 从流式 board 事件累积「本节提纲」：write_title=主题、write_subtitle=小节
  const appendOutline = (demoId, ev) => {
    if (!ev || ev.type !== 'board') return
    if (ev.action !== 'write_title' && ev.action !== 'write_subtitle') return
    const raw = typeof ev.content === 'string'
      ? ev.content
      : Array.isArray(ev.content) ? String(ev.content[0] ?? '') : ''
    const text = raw.trim()
    if (!text) return
    setMessages(prev => prev.map(m => {
      if (m.demoId !== demoId) return m
      const outline = m.outline ? { title: m.outline.title, items: [...m.outline.items] } : { title: null, items: [] }
      if (ev.action === 'write_title') { if (!outline.title) outline.title = text }
      else {
        // 剥掉 LLM 自带的序号前缀（如 "1. " "一、" "(1)"），避免与圆形序号重复编号
        const clean = text.replace(/^\s*[（(]?\s*[0-9一二三四五六七八九十]+\s*[）).、。:：]\s*/, '').trim() || text
        if (!outline.items.includes(clean)) outline.items.push(clean)
      }
      return { ...m, outline }
    }))
  }

  // 示例问题 chip / 点击 → 填入输入框并聚焦（不直接发起，避免误触发 LLM）
  const fillQuestion = (q) => {
    setInput(q)
    setPanelOpen(true)
    requestAnimationFrame(() => inputRef.current?.focus())
  }

  // 数字人浮层拖拽：pointer capture 保证拖到 iframe 上方也不丢事件
  const startDrag = (e) => {
    const stageEl = stageRef.current, avEl = avatarRef.current
    if (!stageEl || !avEl) return
    const s = stageEl.getBoundingClientRect()
    const a = avEl.getBoundingClientRect()
    dragRef.current = { dx: e.clientX - a.left, dy: e.clientY - a.top, sl: s.left, st: s.top, sw: s.width, sh: s.height, w: a.width, h: a.height }
    try { avEl.setPointerCapture(e.pointerId) } catch { /* noop */ }
  }
  const onDrag = (e) => {
    const d = dragRef.current
    if (!d) return
    const left = Math.max(8, Math.min(e.clientX - d.sl - d.dx, d.sw - d.w - 8))
    const top = Math.max(8, Math.min(e.clientY - d.st - d.dy, d.sh - d.h - 8))
    setAvatarPos({ left, top })
  }
  const endDrag = (e) => {
    if (!dragRef.current) return
    try { avatarRef.current?.releasePointerCapture(e.pointerId) } catch { /* noop */ }
    dragRef.current = null
  }

  const buildRuntimeUrl = (meta, push) => {
    const token = localStorage.getItem('token')
    // hostAvatar=1：数字人由本页（M6）浮层渲染（可拖动/可隐藏），M5 只回传口型
    let url = push
      ? `/runtime/?push=1&stream=1&hostAvatar=1&session=${meta.session_id}&teacherId=${teacherId}&token=${token}&apiBase=/api/v1`
      : `/runtime/?events=/api/v1/audio/${meta.session_id}/events.json&hostAvatar=1&teacherId=${teacherId}&token=${token}&apiBase=/api/v1&stream=1`
    if (meta.avatar_url) {
      url += `&avatar=${encodeURIComponent(meta.avatar_url)}&teacherName=${encodeURIComponent(teacher.display_name)}`
      if (meta.avatar_url_alt) {
        url += `&avatarAlt=${encodeURIComponent(meta.avatar_url_alt)}`
      }
    }
    return url
  }

  // 历史回看：把某节已讲完课程的板书「最终态」静态铺回黑板（renderOnly，不放音频、不重新 TTS）。
  // 停掉进行中的直播流，复用固定双槽 iframe（载入后台槽→onLoad 切前台、清旧槽）。
  const replayBoard = (sid) => {
    if (!sid) return
    streamRef.current?.ctl?.abort()  // 回看会接管黑板，先中断正在生成的直播流
    streamRef.current = null
    setSpeaking(false)
    setRate(null)                    // 回看时收起课后评价条
    const token = localStorage.getItem('token')
    const slot = backSlot()
    const url = `/runtime/?renderOnly=1&hostAvatar=1&events=/api/v1/audio/${sid}/events.json&teacherId=${teacherId}&token=${token}&apiBase=/api/v1`
    setSessionId(sid)
    setFrames(prev => ({ ...prev, [slot]: url }))
  }

  // 旧的非流式演示链路（USE_DEMO_STREAM=false 或流式在 meta 前失败时降级）
  const handleDemoLegacy = async (question) => {
    try {
      const result = await teachingDemo(teacherId, question)
      const slot = backSlot()
      setFrames(prev => ({ ...prev, [slot]: buildRuntimeUrl(result, false) }))
      setSessionId(result.session_id)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: result.summary || '老师正在左侧黑板为你讲解。',
        isDemo: true, sessionId: result.session_id, done: true,
      }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `[错误] ${e.message}` }])
    } finally { setLoading(false) }
  }

  // 流式演示链路：meta 到达即装 iframe，事件边生成边经 postMessage 推入
  const handleDemoStream = async (question) => {
    streamRef.current?.ctl?.abort()  // 同一时刻只保留一条流：新问中断旧流
    setSpeaking(false)
    const ctl = new AbortController()
    const demoId = `demo_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const st = { sessionId: null, slot: null, buffer: [], done: false, ready: false, ctl, demoId, metaTimedOut: false }
    streamRef.current = st

    // meta 守门超时：流式请求若被网络层卡住（如代理劫持、连接重试），
    // 12s 内拿不到 meta 就放弃流式、自动降级非流式链路
    const metaTimer = setTimeout(() => {
      if (!st.sessionId) { st.metaTimedOut = true; ctl.abort() }
    }, 12000)

    try {
      await teachingDemoStream(teacherId, question, {
        signal: ctl.signal,
        onMeta: (meta) => {
          clearTimeout(metaTimer)
          st.sessionId = meta.session_id
          st.slot = backSlot()
          setFrames(prev => ({ ...prev, [st.slot]: buildRuntimeUrl(meta, true) }))
          setSessionId(meta.session_id)
          setMessages(prev => [...prev, {
            role: 'assistant',
            content: '老师正在备课，马上开讲…',
            isDemo: true, sessionId: meta.session_id, demoId,
          }])
          setLoading(false)  // meta 到达即解锁输入，流在后台继续
        },
        onEvent: (e) => {
          st.buffer.push(e)
          appendOutline(demoId, e)
          if (st.ready) postToSlot(st.slot, { type: 'm6:events', events: [e] })
        },
        onSummary: (s) => {
          updateDemoBubble(demoId, s.text || '老师正在左侧黑板为你讲解。')
        },
        onError: (er) => {
          updateDemoBubble(demoId, er.partial
            ? '讲解生成中断，已为你播放已生成的部分。'
            : `[错误] ${er.message || '生成失败'}`)
          if (st.ready) postToSlot(st.slot, { type: 'm6:error', message: er.message, partial: er.partial })
        },
        onDone: () => {
          st.done = true
          if (st.ready) postToSlot(st.slot, { type: 'm6:done' })
          // 讲课生成完毕：events.json 已落盘 → 本条气泡可「回看板书」
          setMessages(prev => prev.map(m => (m.demoId === demoId ? { ...m, done: true } : m)))
          // 讲课生成完毕 → 浮出课后评价条（关联本次 session）
          setRate({ sessionId: st.sessionId })
          setRateStars(0); setRateText('')
        },
      })
    } catch (e) {
      if (e.name === 'AbortError' && !st.metaTimedOut) return  // 被新提问中断，无需提示
      if (!st.sessionId) {
        // meta 之前就失败（旧版后端无此路由 / 网络层卡死超时）：自动降级非流式链路
        console.warn('[VirtualClassroom] 流式演示失败，降级非流式:', e)
        await handleDemoLegacy(question)
        return
      }
      // 流中途网络断开：让 iframe 播完已推送的部分
      updateDemoBubble(demoId, '讲解生成中断，已为你播放已生成的部分。')
      if (st.ready) postToSlot(st.slot, { type: 'm6:error', message: e.message, partial: true })
      st.done = true
    } finally {
      clearTimeout(metaTimer)
      setLoading(false)
    }
  }

  const handleSend = async (mode = 'chat') => {
    if (!input.trim() || loading) return
    const question = input.trim()
    setInput('')

    if (mode === 'demo') {
      setLoading(true)
      setMessages(prev => [...prev, { role: 'topic', content: question }, { role: 'user', content: question }])
      if (USE_DEMO_STREAM) await handleDemoStream(question)
      else await handleDemoLegacy(question)
    } else {
      setLoading(true)
      setMessages(prev => [...prev, { role: 'user', content: question }])
      try {
        const res = await sendMessage(teacherId, question)
        setMessages(prev => [...prev, { role: 'assistant', content: res.reply }])
      } catch (e) {
        setMessages(prev => [...prev, { role: 'assistant', content: `[错误] ${e.message}` }])
      } finally { setLoading(false) }
    }
  }

  if (!teacher) {
    return (
      <div className="vcx">
        <div className="vcx__stage"><div className="vcx__loading">加载中…</div></div>
      </div>
    )
  }

  const exampleQs = buildExampleQuestions(teacher)
  // 数字人两帧（闭口/张口）：pixel_url 末段替换为 images[1] 得到张口帧
  const avatarBase = teacher.avatar?.pixel_url || ''
  const avatarImgs = teacher.avatar?.images || []
  const avatarAlt = avatarBase && avatarImgs.length > 1 ? avatarBase.replace(/[^/]+$/, avatarImgs[1]) : ''
  const avatarSrc = speaking && avatarAlt ? avatarAlt : avatarBase
  const avatarLetter = teacher.display_name?.charAt(0) || '师'

  return (
    <div className={`vcx ${panelOpen ? '' : 'is-collapsed'}`}>
      {/* 主体：M5 黑板舞台（固定双槽 iframe，永不换位，只切前后台） */}
      <div className="vcx__stage" ref={stageRef}>
        {!frames.A && !frames.B && (
          // 待命：木框空黑板 + 冷启动示例问题（数字人由下方浮层呈现）
          <div className="vcx__idle">
            <div className="vcx__idle-frame">
              <div className="vcx__idle-board">
                <span className="vcx__chalk-status"><span className="vcx__chalk-dot" />待命中</span>
                <div className="vcx__idle-center">
                  <div className="vcx__idle-title">等待你的提问</div>
                  <div className="vcx__idle-cap">试试点一个问题，老师就上黑板讲</div>
                  <div className="vcx__idle-chips">
                    {exampleQs.map((q, i) => (
                      <button key={i} type="button" className="vcx__qchip"
                        style={{ animationDelay: `${0.15 + i * 0.1}s` }}
                        onClick={() => fillQuestion(q)}>{q}</button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="vcx__idle-tray"><span className="vcx__idle-chalk" /><span className="vcx__idle-eraser" /></div>
            </div>
          </div>
        )}
        {['A', 'B'].map(slot => (
          <iframe
            key={`slot-${slot}`}
            ref={frameRefs[slot]}
            src={frames[slot] || 'about:blank'}
            className={
              frames[slot] && frontSlot === slot
                ? 'vcx__frame'
                : frames[slot]
                  ? 'vcx__frame vcx__frame--behind'
                  : 'vcx__frame vcx__frame--hidden'
            }
            title={`虚拟教室-${slot}`}
            allow="autoplay"
            onLoad={() => handleFrameLoad(slot)}
          />
        ))}

        {/* 数字人浮层：可拖动 + 可隐藏到侧栏（横跨待命/讲课，状态持续） */}
        {avatarHidden ? (
          <button className="vcx__avatar-dock" onClick={() => setAvatarHidden(false)} title="显示老师">
            {avatarBase
              ? <img src={avatarBase} alt={teacher.display_name} draggable={false} />
              : <span className="vcx__avatar-letter">{avatarLetter}</span>}
          </button>
        ) : (
          <div
            ref={avatarRef}
            className={`vcx__avatar-overlay${speaking ? ' is-speaking' : ''}`}
            style={avatarPos ? { left: avatarPos.left, top: avatarPos.top, right: 'auto', bottom: 'auto' } : undefined}
            onPointerDown={startDrag}
            onPointerMove={onDrag}
            onPointerUp={endDrag}
          >
            <div className="vcx__avatar-portrait">
              {avatarBase
                ? <img src={avatarSrc} alt={teacher.display_name} draggable={false} />
                : <span className="vcx__avatar-letter">{avatarLetter}</span>}
            </div>
            <div className="vcx__avatar-tag"><span className="vcx__avatar-live" />{teacher.display_name}</div>
            <button
              className="vcx__avatar-hide"
              onPointerDown={e => e.stopPropagation()}
              onClick={() => setAvatarHidden(true)}
              title="隐藏到侧栏" aria-label="隐藏到侧栏"
            >✕</button>
          </div>
        )}
      </div>

      {/* 折叠开关 */}
      <button
        className="vcx__toggle"
        onClick={() => setPanelOpen(o => !o)}
        title={panelOpen ? '收起面板' : '展开面板'}
        aria-label={panelOpen ? '收起面板' : '展开面板'}
      >
        {panelOpen ? '⟩' : '⟨'}
      </button>

      {/* 右侧可折叠面板：教师风格标签 + 对话 */}
      <aside className="vcx__panel">
        <div className="vcx__panel-inner">
          {/* 教师页眉 */}
          <header className="vcx__teacher">
            <div className="vcx__teacher-top">
              {teacher.avatar?.pixel_url ? (
                <img src={teacher.avatar.pixel_url} alt={teacher.display_name}
                  className="vcx__avatar vcx__avatar--link" title="查看老师主页"
                  onClick={() => navigate(`/teacher/${teacherId}`)} />
              ) : (
                <div className="vcx__avatar-fallback vcx__avatar--link" title="查看老师主页"
                  onClick={() => navigate(`/teacher/${teacherId}`)}>{teacher.display_name?.charAt(0) || '师'}</div>
              )}
              <div className="vcx__teacher-id">
                <div className="vcx__teacher-name vcx__teacher-name--link" title="查看老师主页"
                  onClick={() => navigate(`/teacher/${teacherId}`)}>{teacher.display_name}</div>
                <div className="vcx__chips">
                  {teacher.subject && <span className="vcx__chip vcx__chip--subject">{teacher.subject}</span>}
                </div>
              </div>
            </div>

            <div className="vcx__tags-head">
              <span className="vcx__tags-label">风格标签</span>
              {tags.length > 4 && (
                <button className="vcx__tags-toggle" onClick={() => setTagsOpen(o => !o)}>
                  {tagsOpen ? '收起 ▴' : `展开全部 · ${Math.min(tags.length, 12)} ▾`}
                </button>
              )}
            </div>
            {tags.length > 0 ? (
              <div className={`vcx__tags ${tagsOpen ? 'vcx__tags--open' : ''}`}>
                {tags.slice(0, 12).map((t, i) => (
                  <span key={i} className="vcx__tag" style={{ animationDelay: `${i * 0.04}s` }}>
                    {typeof t === 'string' ? t : t.text || t}
                  </span>
                ))}
              </div>
            ) : (
              <div className="vcx__tags-empty">暂无风格标签</div>
            )}
          </header>

          {/* 对话流 */}
          <div className="vcx__thread">
            {messages.length === 0 && (
              <div className="vcx__empty">
                <div className="vcx__empty-glyph">✎</div>
                <h4>开始上课</h4>
                <p>输入问题，AI 将按 {teacher.display_name} 的教学风格为你讲解。</p>
              </div>
            )}
            {messages.map((msg, i) => {
              // 本节主题胶囊（每次演示开头的会话分隔）
              if (msg.role === 'topic') {
                return <div key={i} className="vcx__topic">本节主题 · <b>{msg.content}</b></div>
              }
              const hasOutline = msg.isDemo && msg.outline && (msg.outline.title || msg.outline.items.length)
              // 讲完(done)且有 sessionId 的 demo 气泡可「回看板书」（events.json 已落盘）
              const canReplay = msg.isDemo && msg.sessionId && msg.done
              return (
                <div key={i} className={`vcx__bubble vcx__bubble--${msg.role}${msg.isDemo ? ' vcx__bubble--demo' : ''}`}>
                  {msg.role === 'assistant' ? <MiniMarkdown text={msg.content} /> : msg.content}
                  {hasOutline && (
                    <div className="vcx__outline">
                      <div className="vcx__outline-h">本节提纲{msg.outline.title ? ` · ${msg.outline.title}` : ''}</div>
                      {msg.outline.items.length > 0 && (
                        <ol className="vcx__outline-list">
                          {msg.outline.items.map((it, j) => <li key={j}>{it}</li>)}
                        </ol>
                      )}
                    </div>
                  )}
                  {msg.isDemo && (
                    canReplay ? (
                      <button className="vcx__replay" onClick={() => replayBoard(msg.sessionId)}
                        title="把这节课的板书重新铺回黑板（无音频）">
                        <span className="vcx__replay-ico">▦</span> 回看这节课板书
                      </button>
                    ) : (
                      <div className="vcx__demo-note">完整讲解见左侧黑板</div>
                    )
                  )}
                </div>
              )
            })}
            {loading && (
              <div className="vcx__typing"><span /><span /><span /></div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* 课后评价条（讲课结束后浮出，反馈进入 skill 进化闭环）；教师试讲态不显示 */}
          {rate && !isTeacherView && (
            <div className="vcx__rate">
              <div className="vcx__rate-row">
                <span className="vcx__rate-label">这节课怎么样？</span>
                {[1, 2, 3, 4, 5].map(i => (
                  <button key={i} type="button"
                    className={`vcx__rate-star ${i <= rateStars ? 'on' : ''}`}
                    onClick={() => setRateStars(i)} aria-label={`${i} 星`}>★</button>
                ))}
                <button className="vcx__rate-close" onClick={() => setRate(null)} aria-label="关闭">×</button>
              </div>
              {rateStars > 0 && (
                <div className="vcx__rate-row">
                  <input className="vcx__rate-input" value={rateText}
                    onChange={e => setRateText(e.target.value)}
                    placeholder="一句话说说讲课风格（如：例子很多但语速偏快）"
                    onKeyDown={e => { if (e.key === 'Enter') e.preventDefault() }} />
                  <button className="vcx__rate-submit" disabled={rateBusy || !rateText.trim()}
                    onClick={async () => {
                      setRateBusy(true)
                      try {
                        await submitFeedback(teacherId, {
                          rating: rateStars, comment: rateText.trim(),
                          session_id: rate.sessionId, context: 'classroom',
                        })
                        setRate(null)
                      } catch { /* 失败静默，不打断课堂 */ }
                      finally { setRateBusy(false) }
                    }}>{rateBusy ? '…' : '提交'}</button>
                </div>
              )}
            </div>
          )}

          {/* 输入区 */}
          <div className="vcx__composer">
            <div className="vcx__input-row">
              <input
                ref={inputRef}
                className="vcx__input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend('demo') } }}
                placeholder="输入问题，Enter 发起教学演示…"
                disabled={loading}
              />
              <button
                className="vcx__send vcx__send--chat"
                onClick={() => handleSend('chat')}
                disabled={loading || !input.trim()}
                title="纯文字回复"
              >💬</button>
              <button
                className="vcx__send vcx__send--demo"
                onClick={() => handleSend('demo')}
                disabled={loading || !input.trim()}
              >{loading ? '…' : '演示'}</button>
            </div>
            <div className="vcx__composer-hint">💬 文字回复 · 演示 = 数字人上黑板讲解</div>
          </div>
        </div>
      </aside>
    </div>
  )
}

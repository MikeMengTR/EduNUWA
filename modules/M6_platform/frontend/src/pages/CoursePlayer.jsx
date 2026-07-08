import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { getTeacher, getCourseDetail } from '../api'
import { getCourse, adaptCourse, fmtDuration } from '../mock/courses'
import Icon from '../components/Icon'
import './CoursePlayer.css'

export default function CoursePlayer() {
  const { teacherId, courseId, chapterId } = useParams()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // 同一个播放器：教师从「课堂预录制」预览时走 /teacher/learn，内部跳转与返回都留在教师态
  const isTeacherView = pathname.startsWith('/teacher')
  const learnBase = isTeacherView ? '/teacher/learn' : '/student/learn'
  const [teacher, setTeacher] = useState(null)
  const [course, setCourse] = useState(null)
  const [panelOpen, setPanelOpen] = useState(true)
  const [tagsOpen, setTagsOpen] = useState(false)
  // 数字人浮层（仿教室页）：说话态口型、隐藏到侧栏、自由拖拽位置
  const [speaking, setSpeaking] = useState(false)
  const [avatarHidden, setAvatarHidden] = useState(false)
  const [avatarPos, setAvatarPos] = useState(null)  // {left,top} px（相对舞台）；null=默认右下角
  const stageRef = useRef(null)
  const avatarRef = useRef(null)
  const dragRef = useRef(null)

  useEffect(() => {
    (async () => {
      try {
        const t = await getTeacher(teacherId)
        setTeacher(t)
        let c = null
        try { c = adaptCourse(await getCourseDetail(teacherId, courseId)) } catch (e) { /* 非真实课程 */ }
        if (!c) c = getCourse(teacherId, t.subject, courseId)  // 回退演示课程
        setCourse(c)
        localStorage.setItem('lastTeacherId', teacherId)
      } catch (e) { navigate('/student') }
    })()
  }, [teacherId, courseId])

  // 切讲（iframe 重载）时复位说话态
  useEffect(() => { setSpeaking(false) }, [chapterId])

  // iframe → 父页面：hostAvatar=1 时 M5 只回口型，由本页浮层渲染数字人
  useEffect(() => {
    const onMsg = (ev) => {
      if (ev.origin !== window.location.origin) return
      const msg = ev.data
      if (!msg || msg.source !== 'edunuwa') return
      if (msg.type === 'm5:speaking') setSpeaking(!!msg.value)
      else if (msg.type === 'm5:end') setSpeaking(false)
    }
    window.addEventListener('message', onMsg)
    return () => window.removeEventListener('message', onMsg)
  }, [])

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

  if (!teacher || !course) {
    return <div className="cpl"><div className="cpl-stage"><div className="loading" style={{ margin: 'auto', color: '#a59c8e' }}>加载中…</div></div></div>
  }

  const idx = course.chapters.findIndex(c => c.id === chapterId)
  const chapter = course.chapters[idx] || course.chapters[0]
  const prev = idx > 0 ? course.chapters[idx - 1] : null
  const next = idx < course.chapters.length - 1 ? course.chapters[idx + 1] : null

  const token = localStorage.getItem('token')
  // 数字人两帧（闭口/张口）：pixel_url 末段替换为 images[1] 得到张口帧（说话时切换）
  const avatarBase = teacher.avatar?.pixel_url || ''
  const avatarImgs = teacher.avatar?.images || []
  const avatarAlt = avatarBase && avatarImgs.length > 1 ? avatarBase.replace(/[^/]+$/, avatarImgs[1]) : ''
  const avatarSrc = speaking && avatarAlt ? avatarAlt : avatarBase
  const avatarLetter = teacher.display_name?.charAt(0) || '师'
  const avatar = avatarBase
  // hostAvatar=1：数字人由本页浮层渲染（可拖动/可隐藏），M5 只回口型
  let src = `/runtime/?events=/api/v1/audio/${chapter.events_url}&hostAvatar=1&teacherId=${teacherId}&token=${token}&apiBase=/api/v1&stream=1`
  if (avatarBase) {
    src += `&avatar=${encodeURIComponent(avatarBase)}&teacherName=${encodeURIComponent(teacher.display_name)}`
    if (avatarAlt) src += `&avatarAlt=${encodeURIComponent(avatarAlt)}`
  }

  const go = (ch) => { if (ch) navigate(`${learnBase}/${teacherId}/${courseId}/${ch.id}`) }
  const goProfile = () => navigate(`/teacher/${teacherId}`)
  const tags = teacher.tags || []

  return (
    <div className={`cpl ${panelOpen ? '' : 'is-collapsed'}`}>
      <div className="cpl-stage" ref={stageRef}>
        <div className="cpl-bar">
          <button className="cpl-back" onClick={() => navigate(isTeacherView ? '/teacher/courses' : `/student/courses/${teacherId}`)}>
            <Icon name="chevronLeft" size={18} /> {isTeacherView ? '我的课程' : '课程目录'}
          </button>
          <span className="cpl-title">第 {chapter.index} 讲 · {chapter.title}</span>
          <div className="cpl-nav">
            <button onClick={() => go(prev)} disabled={!prev} title="上一讲"><Icon name="chevronLeft" size={18} /></button>
            <button onClick={() => go(next)} disabled={!next} title="下一讲"><Icon name="chevronRight" size={18} /></button>
          </div>
        </div>
        <iframe key={chapter.id} src={src} className="cpl-frame" title="课程" allow="autoplay" />

        {/* 数字人浮层（仿教室页）：可拖动 + 可隐藏到侧栏 */}
        {avatarHidden ? (
          <button className="cpl-av-dock" onClick={() => setAvatarHidden(false)} title="显示老师">
            {avatarBase
              ? <img src={avatarBase} alt={teacher.display_name} draggable={false} />
              : <span className="cpl-av-letter">{avatarLetter}</span>}
          </button>
        ) : (
          <div
            ref={avatarRef}
            className={`cpl-av-overlay${speaking ? ' is-speaking' : ''}`}
            style={avatarPos ? { left: avatarPos.left, top: avatarPos.top, right: 'auto', bottom: 'auto' } : undefined}
            onPointerDown={startDrag}
            onPointerMove={onDrag}
            onPointerUp={endDrag}
          >
            <div className="cpl-av-portrait">
              {avatarBase
                ? <img src={avatarSrc} alt={teacher.display_name} draggable={false} />
                : <span className="cpl-av-letter">{avatarLetter}</span>}
            </div>
            <div className="cpl-av-tag"><span className="cpl-av-live" />{teacher.display_name}</div>
            <button
              className="cpl-av-hide"
              onPointerDown={e => e.stopPropagation()}
              onClick={() => setAvatarHidden(true)}
              title="隐藏到侧栏" aria-label="隐藏到侧栏"
            >✕</button>
          </div>
        )}
      </div>

      <button className="cpl-toggle" onClick={() => setPanelOpen(o => !o)} title={panelOpen ? '收起目录' : '展开目录'}>
        {panelOpen ? '⟩' : '⟨'}
      </button>

      <aside className="cpl-panel">
        <div className="cpl-panel-inner">
          {/* 老师页眉（仿教室页）：头像 + 名字 + 学科 + 折叠风格标签 */}
          <header className="cpl-teacher">
            <div className="cpl-teacher__top">
              {avatar ? (
                <img src={avatar} alt={teacher.display_name}
                  className="cpl-teacher__avatar cpl-teacher__avatar--link" title="查看老师主页" onClick={goProfile} />
              ) : (
                <div className="cpl-teacher__avatar cpl-teacher__avatar--fallback cpl-teacher__avatar--link"
                  title="查看老师主页" onClick={goProfile}>{teacher.display_name?.charAt(0) || '师'}</div>
              )}
              <div className="cpl-teacher__id">
                <div className="cpl-teacher__name cpl-teacher__name--link" title="查看老师主页" onClick={goProfile}>{teacher.display_name}</div>
                {teacher.subject && <span className="cpl-teacher__subject">{teacher.subject}</span>}
              </div>
            </div>

            {tags.length > 0 && (
              <>
                <div className="cpl-teacher__tags-head">
                  <span className="cpl-teacher__tags-label">风格标签</span>
                  {tags.length > 4 && (
                    <button className="cpl-teacher__tags-toggle" onClick={() => setTagsOpen(o => !o)}>
                      {tagsOpen ? '收起 ▴' : `展开全部 · ${Math.min(tags.length, 12)} ▾`}
                    </button>
                  )}
                </div>
                <div className="cpl-teacher__tags">
                  {tags.slice(0, tagsOpen ? 12 : 4).map((t, i) => (
                    <span key={i} className="cpl-teacher__tag">{typeof t === 'string' ? t : t.text || t}</span>
                  ))}
                </div>
              </>
            )}
          </header>

          <div className="cpl-panel__head">
            <h3>{course.title}</h3>
            <span>{course.chapterCount} 讲 · {teacher.display_name}</span>
          </div>
          <div className="cpl-outline">
            {course.chapters.map((ch, i) => (
              <button key={ch.id}
                className={`cpl-item ${ch.id === chapter.id ? 'active' : ''} ${i < course.learned ? 'done' : ''}`}
                onClick={() => go(ch)}>
                <span className="cpl-item__idx">{i < course.learned ? <Icon name="check" size={14} /> : String(ch.index).padStart(2, '0')}</span>
                <span className="cpl-item__title">{ch.title}</span>
                <span className="cpl-item__dur">{fmtDuration(ch.durationSec)}</span>
              </button>
            ))}
          </div>
        </div>
      </aside>
    </div>
  )
}

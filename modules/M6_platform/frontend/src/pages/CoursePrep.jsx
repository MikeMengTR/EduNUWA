import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMyTeacher, listCourses, createCourse, getCourseDetail, publishCourse, deleteCourse } from '../api'
import { adaptCourse, fmtDuration } from '../mock/courses'
import Icon from '../components/Icon'
import './CoursePrep.css'

export default function CoursePrep() {
  const [teacher, setTeacher] = useState(null)
  const [courses, setCourses] = useState([])
  const [expanded, setExpanded] = useState(null)
  const [tab, setTab] = useState('outline')
  const [title, setTitle] = useState('')
  const [outline, setOutline] = useState('')
  const [transcript, setTranscript] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [arranging, setArranging] = useState(false)
  const [toast, setToast] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    (async () => {
      try {
        const t = await getMyTeacher()
        setTeacher(t)
        const cs = await listCourses(t.teacher_id)
        setCourses(cs.map(adaptCourse))
      } catch (e) { /* 还没创建卡片 */ }
    })()
  }, [])

  // 轮询正在编排的课程，实时刷新章节进度
  useEffect(() => {
    if (!teacher) return
    const pending = courses.filter(c => c.real && c.generating)
    if (pending.length === 0) return
    const timer = setTimeout(async () => {
      const updates = await Promise.all(pending.map(c =>
        getCourseDetail(teacher.teacher_id, c.id).then(adaptCourse).catch(() => null)))
      setCourses(prev => prev.map(c => updates.find(u => u && u.id === c.id) || c))
    }, 3000)
    return () => clearTimeout(timer)
  }, [courses, teacher])

  const chapterCount = tab === 'outline'
    ? outline.split('\n').filter(s => s.trim()).length
    : transcript.split(/\n{2,}/).filter(s => s.trim()).length

  const handleArrange = async () => {
    if (arranging || !teacher) return
    if (!title.trim()) { setToast('请先填写课程标题'); return }
    const chapters = tab === 'outline'
      ? outline.split('\n').map(s => s.trim()).filter(Boolean).map(t => ({ title: t, brief: t }))
      : transcript.split(/\n{2,}/).map(s => s.trim()).filter(Boolean).map(s => ({ title: s.slice(0, 28), brief: s }))
    if (chapters.length === 0) {
      setToast(tab === 'outline' ? '请输入课程大纲（每行一个知识点）' : '请粘贴讲课记录（用空行分段）')
      return
    }

    setToast(''); setArranging(true)
    try {
      const c = await createCourse(teacher.teacher_id, { title: title.trim(), source: tab, chapters })
      const ac = adaptCourse(c)
      setCourses(prev => [ac, ...prev])
      setExpanded(ac.id)
      setTitle(''); setOutline(''); setTranscript('')
      setToast(`正在编排「${ac.title}」，共 ${ac.chapterCount} 讲——下方可实时查看每讲生成进度`)
    } catch (e) {
      setToast(`编排失败：${e.message}`)
    } finally {
      setArranging(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    const f = e.dataTransfer.files?.[0]
    if (!f) return
    if (f.type.startsWith('text') || /\.(txt|md)$/i.test(f.name)) f.text().then(setTranscript)
    else setTranscript(prev => `${prev}\n[已添加讲稿：${f.name}]`)
  }

  const publish = async (c) => {
    try {
      const updated = await publishCourse(teacher.teacher_id, c.id)
      setCourses(prev => prev.map(x => x.id === c.id ? adaptCourse(updated) : x))
      setToast(`「${c.title}」已发布，学生现在可以学习`)
    } catch (e) { setToast(`发布失败：${e.message}`) }
  }

  const remove = async (c) => {
    if (!window.confirm(`确定删除课程「${c.title}」？该操作不可恢复。`)) return
    try {
      await deleteCourse(teacher.teacher_id, c.id)
      setCourses(prev => prev.filter(x => x.id !== c.id))
      setToast(`已删除「${c.title}」`)
    } catch (e) { setToast(`删除失败：${e.message}`) }
  }

  const statusBadge = (c) => {
    if (c.published) return <span className="cp-badge published">已发布</span>
    if (c.generating) return <span className="cp-badge draft">编排中 {c.readyCount}/{c.chapterCount}</span>
    if (c.courseStatus === 'partial') return <span className="cp-badge draft">部分完成 {c.readyCount}/{c.chapterCount}</span>
    if (c.courseStatus === 'error') return <span className="cp-badge draft">编排失败</span>
    return <span className="cp-badge draft">待发布</span>
  }

  const chapterIcon = (c, ch) => {
    if (ch.status === 'ready') return <button className="cp-chapter__btn" onClick={() => navigate(`/teacher/learn/${teacher.teacher_id}/${c.id}/${ch.id}`)} title="预览这一讲（学生视角）"><Icon name="play" size={15} /></button>
    if (ch.status === 'generating') return <span className="cp-chapter__state"><Icon name="spinner" size={15} className="spin" /></span>
    if (ch.status === 'error') return <span className="cp-chapter__state cp-chapter__state--err" title={ch.error || '生成失败'}><Icon name="x" size={15} /></span>
    return <span className="cp-chapter__state"><Icon name="clock" size={14} /></span>
  }

  if (!teacher) {
    return (
      <div className="container">
        <div className="page-header"><h1>课堂预录制</h1></div>
        <div className="empty-state"><h3>还未创建教师卡片</h3><p>请先在「教师主页」创建卡片并蒸馏 Skill，再来编排课程</p></div>
      </div>
    )
  }

  return (
    <div className="container">
      <div className="page-header"><h1>课堂预录制</h1></div>
      <p className="cp-lead">提供课程大纲或讲课记录，由你的数字分身自动编排为成体系的多讲课程——每一讲的板书与讲解逐条生成，学生进入即可用你的音色逐章学习。</p>

      {/* 编排工作台 */}
      <section className="cp-studio">
        <div className="cp-studio__tabs">
          <button className={tab === 'outline' ? 'active' : ''} onClick={() => setTab('outline')}><Icon name="layers" size={16} /> 课程大纲</button>
          <button className={tab === 'transcript' ? 'active' : ''} onClick={() => setTab('transcript')}><Icon name="file" size={16} /> 讲课记录</button>
        </div>

        <input className="cp-title" value={title} onChange={e => setTitle(e.target.value)} placeholder="课程标题，如「概率论 · 基础篇」" />

        {tab === 'outline' ? (
          <textarea className="cp-area" value={outline} onChange={e => setOutline(e.target.value)} rows={7}
            placeholder={'每行一个知识点 / 章节（每行成为一讲），例如：\n随机事件与样本空间\n条件概率\n全概率与贝叶斯公式\n正态分布'} />
        ) : (
          <div className={`cp-drop ${dragOver ? 'over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)} onDrop={handleDrop}>
            <textarea className="cp-area cp-area--plain" value={transcript} onChange={e => setTranscript(e.target.value)} rows={7}
              placeholder={'粘贴你的讲稿 / 讲课记录（用空行分段，每段成为一讲），或把讲稿文件拖到这里。'} />
          </div>
        )}

        <div className="cp-studio__foot">
          <span className="cp-hint">{chapterCount > 0 ? `${chapterCount} 个章节待编排` : '体系化输出，含板书与讲解'}</span>
          <button className="btn btn--accent" onClick={handleArrange} disabled={arranging}>
            {arranging ? <><Icon name="spinner" size={16} className="spin" /> 提交中…</> : <><Icon name="flask" size={16} /> 自动编排课程</>}
          </button>
        </div>
        {toast && <div className="cp-toast"><Icon name="check" size={15} /> {toast}</div>}
      </section>

      {/* 已编排课程 */}
      <h2 className="cp-section-title">我的课程</h2>
      {courses.length === 0 ? (
        <div className="empty-state"><h3>还没有课程</h3><p>用上方工作台编排你的第一门课</p></div>
      ) : (
        <div className="cp-courses">
          {courses.map(c => (
            <div key={c.id} className="cp-course">
              <div className="cp-course__head" onClick={() => setExpanded(expanded === c.id ? null : c.id)}>
                <div className="cp-course__cover">
                  {c.generating ? <Icon name="spinner" size={22} className="spin" /> : <Icon name="layers" size={22} />}
                </div>
                <div className="cp-course__meta">
                  <h3>{c.title}</h3>
                  <span className="cp-course__sub">{c.subject} · {c.chapterCount} 讲</span>
                </div>
                {statusBadge(c)}
                <Icon name={expanded === c.id ? 'chevronLeft' : 'chevronRight'} size={18} className="cp-course__chev" />
              </div>
              {expanded === c.id && (
                <div className="cp-chapters">
                  {c.chapters.map(ch => (
                    <div key={ch.id} className="cp-chapter">
                      <span className="cp-chapter__idx">{String(ch.index).padStart(2, '0')}</span>
                      <span className="cp-chapter__title">{ch.title}</span>
                      <span className="cp-chapter__dur">{ch.status === 'ready' ? fmtDuration(ch.durationSec) : ''}</span>
                      {chapterIcon(c, ch)}
                    </div>
                  ))}
                  <div className="cp-chapters__foot">
                    {c.published ? (
                      <span className="cp-published">已发布 · 学生可学习</span>
                    ) : c.generating ? (
                      <span className="cp-published"><Icon name="spinner" size={14} className="spin" /> 正在编排 {c.readyCount}/{c.chapterCount} 讲…</span>
                    ) : (
                      <button className="btn btn-sm btn--accent" onClick={() => publish(c)} disabled={c.readyCount === 0}>
                        <Icon name="check" size={15} /> 发布课程
                      </button>
                    )}
                    <button className="btn btn-sm btn--ghost" onClick={() => remove(c)}><Icon name="trash" size={15} /> 删除</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

    </div>
  )
}

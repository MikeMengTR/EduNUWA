import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeacher, getFeedback, submitFeedback } from '../api'
import Icon from '../components/Icon'
import { Eyebrow, deriveStyle, StyleSketchCard, TeachingStyleCard, StudentReviewsCard } from '../components/StyleProfile'
import './TeacherProfile.css'

export default function TeacherProfile({ user }) {
  const { teacherId } = useParams()
  const navigate = useNavigate()
  const [teacher, setTeacher] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [rating, setRating] = useState(5)
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    (async () => {
      try {
        const [t, f] = await Promise.all([getTeacher(teacherId), getFeedback(teacherId)])
        setTeacher(t)
        setFeedback(f)
      } catch (e) { navigate('/student') }
      finally { setLoading(false) }
    })()
  }, [teacherId])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!comment.trim()) return
    setSubmitting(true); setMsg('')
    try {
      await submitFeedback(teacherId, { rating, comment: comment.trim() })
      setMsg('评价提交成功！')
      setShowForm(false)
      setComment('')
      setFeedback(await getFeedback(teacherId))
    } catch (err) {
      setMsg(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="loading">加载中…</div>
  if (!teacher) return null

  const stats = feedback?.stats || { total: 0, avg_rating: 0 }
  const { rawTags } = deriveStyle(teacher)
  const subject = teacher.subject

  const reviewAction = user?.role === 'student' && (
    <button className="btn btn-sm btn--ghost" onClick={() => { setShowForm(!showForm); setMsg('') }}>
      {showForm ? '取消' : <><Icon name="edit" size={15} /> 写评价</>}
    </button>
  )
  const reviewForm = showForm && (
    <form className="review-form" onSubmit={handleSubmit}>
      <div className="review-form__stars">
        <span className="lbl">评分</span>
        {[1, 2, 3, 4, 5].map((i) => (
          <button key={i} type="button" className="star-btn" onClick={() => setRating(i)} aria-label={`${i} 星`}>
            <Icon name="star" size={24} className={`star ${i <= rating ? 'on' : ''}`} />
          </button>
        ))}
      </div>
      <div className="form-group" style={{ marginBottom: 12 }}>
        <textarea value={comment} onChange={(e) => setComment(e.target.value)}
          placeholder="分享你对这位老师的教学体验…" rows={3} />
      </div>
      <button className="btn btn-sm btn--accent" type="submit" disabled={submitting || !comment.trim()}>
        {submitting ? '提交中…' : '提交评价'}
      </button>
      {msg && <span className={`review-msg ${msg.includes('成功') ? 'ok' : 'err'}`}>{msg}</span>}
    </form>
  )

  return (
    <div className="container tp2">
      {/* 上下文头卡 */}
      <header className="tp2-card tp2-head">
        {teacher.avatar_url || teacher.avatar?.pixel_url ? (
          <img className="tp2-avatar" src={teacher.avatar_url || teacher.avatar.pixel_url} alt={teacher.display_name} />
        ) : (
          <div className="tp2-avatar tp2-avatar--fallback">{teacher.display_name?.charAt(0) || '师'}</div>
        )}
        <div className="tp2-head-main">
          <div className="tp2-head-title">
            {teacher.display_name}
            {subject && <span className="tp2-chip-subject">{subject}</span>}
          </div>
          <div className="tp2-head-stats">
            <span><Icon name="star" size={14} className="star on" /> <b>{stats.avg_rating ? Number(stats.avg_rating).toFixed(1) : '—'}</b> 平均评分</span>
            <span className="tp2-dot" />
            <span><b>{stats.total}</b> 条评价</span>
            <span className="tp2-dot" />
            <span><b>{rawTags.length}</b> 风格标签</span>
            {teacher.school && (<><span className="tp2-dot" /><span>{teacher.school}</span></>)}
          </div>
        </div>
      </header>

      <div className="tp2-cols">
        <div className="tp2-main">
          <StyleSketchCard teacher={teacher} />
          <TeachingStyleCard teacher={teacher} />
          <StudentReviewsCard feedback={feedback} action={reviewAction}>{reviewForm}</StudentReviewsCard>
        </div>

        {/* sticky 侧栏 —— 常驻 CTA */}
        <aside className="tp2-aside">
          <button className="btn btn--accent" onClick={() => navigate(`/classroom/${teacherId}`)}>
            <Icon name="cap" size={17} /> 进入虚拟教室
          </button>
          <button className="btn btn--ghost" onClick={() => navigate(`/student/courses/${teacherId}`)}>
            <Icon name="book" size={17} /> 课程
          </button>
        </aside>
      </div>
    </div>
  )
}

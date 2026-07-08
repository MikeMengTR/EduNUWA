import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeacher, listCourses } from '../api'
import { getCoursesForTeacher, adaptCourse, fmtDuration } from '../mock/courses'
import Icon from '../components/Icon'
import './CourseCatalog.css'

export default function CourseCatalog() {
  const { teacherId } = useParams()
  const navigate = useNavigate()
  const [teacher, setTeacher] = useState(null)
  const [courses, setCourses] = useState([])
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    (async () => {
      try {
        const t = await getTeacher(teacherId)
        setTeacher(t)
        let cs = []
        try { cs = (await listCourses(teacherId)).map(adaptCourse) } catch (e) { /* 无真实课程 */ }
        if (cs.length === 0) cs = getCoursesForTeacher(teacherId, t.subject)  // 老师还没编排，回退演示课程
        setCourses(cs)
        setSelected(cs[0]?.id || null)
      } catch (e) { navigate('/student') }
    })()
  }, [teacherId])

  if (!teacher) return <div className="loading">加载中…</div>
  const course = courses.find(c => c.id === selected)
  const totalMin = course ? Math.round(course.chapters.reduce((a, c) => a + c.durationSec, 0) / 60) : 0

  return (
    <div className="container cc">
      <div className="page-header">
        <h1>{teacher.display_name} 的课程</h1>
        <button className="btn btn-sm btn--ghost" onClick={() => navigate(`/classroom/${teacherId}`)}>
          <Icon name="cap" size={15} /> 进入课堂
        </button>
      </div>

      <div className="cc-layout">
        {/* 课程列表 */}
        <div className="cc-courses">
          {courses.map(c => (
            <button key={c.id} className={`cc-course ${selected === c.id ? 'active' : ''}`} onClick={() => setSelected(c.id)}>
              <div className="cc-course__cover"><span>{c.subject}</span></div>
              <div className="cc-course__body">
                <h3>{c.title}</h3>
                <p>{c.summary}</p>
                <div className="cc-course__meta">
                  <span><Icon name="book" size={13} /> {c.chapterCount} 讲</span>
                  <span><Icon name="user" size={13} /> {c.real ? '自编排课程' : `${c.enrolled} 人在学`}</span>
                </div>
                {c.learned > 0 && (
                  <div className="cc-progress">
                    <div className="cc-progress__bar"><div style={{ width: `${Math.round(c.learned / c.chapterCount * 100)}%` }} /></div>
                    <span>{c.learned}/{c.chapterCount}</span>
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>

        {/* 章节目录 */}
        {course && (
          <div className="cc-chapters">
            <div className="cc-chapters__head">
              <h2>{course.title}</h2>
              <span>{course.chapterCount} 讲 · 约 {totalMin} 分钟</span>
            </div>
            <div className="cc-list">
              {course.chapters.map((ch, i) => {
                const done = i < course.learned
                const current = i === course.learned
                return (
                  <button key={ch.id}
                    className={`cc-chapter ${done ? 'done' : ''} ${current ? 'current' : ''}`}
                    onClick={() => navigate(`/student/learn/${teacherId}/${course.id}/${ch.id}`)}>
                    <span className="cc-chapter__idx">{done ? <Icon name="check" size={15} /> : String(ch.index).padStart(2, '0')}</span>
                    <span className="cc-chapter__title">{ch.title}</span>
                    <span className="cc-chapter__dur">{fmtDuration(ch.durationSec)}</span>
                    <Icon name="play" size={16} className="cc-chapter__play" />
                  </button>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

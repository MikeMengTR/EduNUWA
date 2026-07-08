import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { matchTeachers } from '../api'
import Icon from './Icon'
import './TeacherSearch.css'

// Navbar 内联智能搜索：按钮 ↔ 搜索框变形，按风格匹配老师，横滑结果直达教室
export default function TeacherSearch() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState(null) // { rankings, summary, error }
  const inputRef = useRef(null)
  const wrapRef = useRef(null)

  useEffect(() => { if (open) inputRef.current?.focus() }, [open])

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) close() }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const close = () => { setOpen(false); setResults(null); setQuery('') }

  const handleSearch = async () => {
    if (!query.trim() || loading) return
    setLoading(true); setResults(null)
    try {
      const res = await matchTeachers(query.trim())
      setResults(res)
    } catch (e) {
      setResults({ rankings: [], summary: '', error: e.message })
    } finally { setLoading(false) }
  }

  const goClassroom = (id) => { close(); navigate(`/classroom/${id}`) }
  const goFullPage = () => { close(); navigate('/student') }

  if (!open) {
    return (
      <button className="nav-link" onClick={() => setOpen(true)}>
        <Icon name="search" size={17} /> 发现教师
      </button>
    )
  }

  return (
    <div className="tsearch" ref={wrapRef}>
      <div className="tsearch__bar">
        <Icon name="sparkles" size={16} className="tsearch__spark" />
        <input
          ref={inputRef}
          className="tsearch__input"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleSearch(); if (e.key === 'Escape') close() }}
          placeholder="描述你想要的老师风格，如：讲题快、爱举生活例子…"
        />
        <button className="tsearch__go" onClick={handleSearch} disabled={loading || !query.trim()} title="智能匹配">
          <Icon name={loading ? 'spinner' : 'arrowRight'} size={16} className={loading ? 'spin' : ''} />
        </button>
        <button className="tsearch__full" onClick={goFullPage} title="打开完整发现页">
          <Icon name="layers" size={16} />
        </button>
        <button className="tsearch__close" onClick={close} title="关闭">
          <Icon name="x" size={16} />
        </button>
      </div>

      {(loading || results) && (
        <div className="tsearch__panel">
          {loading && <div className="tsearch__hint">正在按风格匹配老师…</div>}
          {results && !loading && (
            results.error ? (
              <div className="tsearch__hint err">{results.error}</div>
            ) : results.rankings?.length ? (
              <>
                <div className="tsearch__row">
                  {results.rankings.map((r, i) => (
                    <button
                      key={r.teacher_id || i}
                      className={`tsearch__card ${i === 0 ? 'top' : ''}`}
                      onClick={() => goClassroom(r.teacher_id)}
                    >
                      <span className="tsearch__rank">{i === 0 ? '最佳匹配' : `#${i + 1}`}</span>
                      <span className="tsearch__name">{r.display_name || r.teacher_id}</span>
                      <span className="tsearch__reason">{r.reason}</span>
                      <span className="tsearch__enter">进入教室 <Icon name="arrowRight" size={14} /></span>
                    </button>
                  ))}
                </div>
                {results.summary && <div className="tsearch__summary">{results.summary}</div>}
              </>
            ) : (
              <div className="tsearch__hint">没有匹配到合适的老师，换个描述试试</div>
            )
          )}
        </div>
      )}
    </div>
  )
}

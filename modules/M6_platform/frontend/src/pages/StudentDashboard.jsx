import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getTeachers, matchTeachers } from '../api'
import TeacherCard from '../components/TeacherCard'
import Icon from '../components/Icon'
import './StudentDashboard.css'
import './student-enhance.css'  // 动态/设计感增强层（作用域 .discover-page，须最后加载以覆盖）

const SUBJECTS = ['高等数学', '线性代数', '概率论', '大学物理', '程序设计', '机器学习', '大学英语', '思政']

export default function StudentDashboard() {
  const [teachers, setTeachers] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [subject, setSubject] = useState('')
  const [matchQuery, setMatchQuery] = useState('')
  const [matching, setMatching] = useState(false)
  const [matchResult, setMatchResult] = useState(null)
  const [showAll, setShowAll] = useState(false)  // 6~12 名默认折叠
  const navigate = useNavigate()

  const load = async (opts = {}) => {
    setLoading(true)
    try {
      const params = { role: 'student' }
      const s = opts.search !== undefined ? opts.search : search
      const sub = opts.subject !== undefined ? opts.subject : subject
      if (s) params.search = s
      if (sub) params.subject = sub
      const data = await getTeachers(params)
      setTeachers(data)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleSearch = (e) => { e?.preventDefault(); load() }
  const pickSubject = (s) => { setSubject(s); load({ subject: s }) }

  // 前 3 名用金/银/铜左侧色条表示推荐程度；#1 标「最佳匹配」
  const medalClass = (i) => (i === 0 ? 'g1' : i === 1 ? 'g2' : i === 2 ? 'g3' : '')
  const renderRank = (r, i) => (
    <button key={r.teacher_id || i} className={`discover__rank ${medalClass(i)}`}
      onClick={() => navigate(`/classroom/${r.teacher_id}`)}>
      {i < 3
        ? <span className="discover__rank-badge">{i === 0 ? '最佳匹配' : `#${i + 1}`}</span>
        : <span className="discover__rank-no">{i + 1}</span>}
      <span className="discover__rank-main">
        <span className="discover__rank-name">
          {r.display_name || r.teacher_id}
          {r.subject && <span className="discover__rank-meta">{r.subject}</span>}
        </span>
        <span className="discover__rank-reason">{r.reason}</span>
      </span>
      <Icon name="arrowRight" size={17} className="discover__rank-arrow" />
    </button>
  )

  const handleMatch = async () => {
    if (!matchQuery.trim() || matching) return
    setMatching(true); setMatchResult(null); setShowAll(false)
    try {
      const result = await matchTeachers(matchQuery.trim())
      setMatchResult(result)
    } catch (e) {
      setMatchResult({ rankings: [], error: e.message })
    } finally { setMatching(false) }
  }

  return (
    <div className="container discover-page">
      <header className="discover__hero">
        <div className="discover__kick">EduTwin · 教师匹配</div>
        <h1>
          <span className="discover__hero-latin">Find the professor who teaches your way.</span>
          发现你的老师<span className="discover__hero-dot">。</span>
        </h1>
        <p className="discover__lead">用一句话说出你想要的讲课风格，我们按贴合度排出最合适的人选——选定后，直接走进他的虚拟课堂。</p>
        <div className="discover__stats">
          <span><b>{teachers.length}</b> 位在册教授</span>
          <span><b>{SUBJECTS.length}</b> 个学科</span>
          <span><span className="discover__pulse" /> AI 分身随时开课</span>
        </div>
      </header>

      {/* 智能匹配 */}
      <section className="discover__match">
        <div className="discover__match-head">
          <div className="discover__match-label"><Icon name="sparkles" size={19} /> 按风格智能匹配</div>
          <span className="discover__match-tag">NATURAL LANGUAGE → RANKED</span>
        </div>
        <p className="discover__match-hint">描述你想要的课堂——节奏、例子、板书、推导，剩下的交给匹配。</p>
        <div className="discover__match-row">
          <input
            value={matchQuery}
            onChange={e => setMatchQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleMatch()}
            placeholder="描述你理想中的老师…"
          />
          <button className="btn btn--accent" onClick={handleMatch} disabled={matching || !matchQuery.trim()}>
            <Icon name={matching ? 'spinner' : 'sparkles'} size={17} className={matching ? 'spin' : ''} />
            {matching ? '匹配中…' : 'AI 匹配'}
          </button>
        </div>

        {matchResult && (
          <div className="discover__results">
            {matchResult.error ? (
              <div className="discover__results-err">{matchResult.error}</div>
            ) : matchResult.rankings?.length ? (
              <>
                {matchResult.rankings.slice(0, 5).map((r, i) => renderRank(r, i))}
                {showAll && matchResult.rankings.slice(5).map((r, i) => renderRank(r, i + 5))}
                {matchResult.rankings.length > 5 && (
                  <button className={`discover__more ${showAll ? 'open' : ''}`} onClick={() => setShowAll(v => !v)}>
                    {showAll ? '收起' : `展开查看其余 ${matchResult.rankings.length - 5} 位`}
                    <Icon name="chevronDown" size={15} />
                  </button>
                )}
                {matchResult.summary && <p className="discover__summary">{matchResult.summary}</p>}
              </>
            ) : (
              <div className="discover__results-err">没有匹配到合适的老师，换个描述试试</div>
            )}
          </div>
        )}
      </section>

      {/* 学科浏览 */}
      <div className="discover__sec-rule">
        <span className="discover__sec-lab">按学科浏览</span>
        <span className="discover__sec-line" />
      </div>

      {/* 筛选工具条 */}
      <div className="discover__bar">
        <form className="discover__search" onSubmit={handleSearch}>
          <Icon name="search" size={18} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索教师姓名或简介…" />
        </form>
        <button className="btn btn--ghost btn-sm" onClick={handleSearch}>搜索</button>
      </div>
      <div className="discover__chips">
        <button className={`chip ${!subject ? 'active' : ''}`} onClick={() => pickSubject('')}>全部</button>
        {SUBJECTS.map(s => (
          <button key={s} className={`chip ${subject === s ? 'active' : ''}`} onClick={() => pickSubject(s)}>{s}</button>
        ))}
      </div>

      {/* 教师网格 */}
      {loading ? (
        <div className="loading">加载中…</div>
      ) : teachers.length === 0 ? (
        <div className="empty-state">
          <h3>暂无教师</h3>
          <p>换个筛选条件，或等待更多教师入驻平台</p>
        </div>
      ) : (
        <div className="agent-grid">
          {teachers.map(t => (
            <TeacherCard key={t.teacher_id} teacher={t}
              onChat={() => navigate(`/classroom/${t.teacher_id}`)}
              onWatchVideo={() => navigate(`/student/courses/${t.teacher_id}`)}
              onDetail={() => navigate(`/teacher/${t.teacher_id}`)} />
          ))}
        </div>
      )}
    </div>
  )
}

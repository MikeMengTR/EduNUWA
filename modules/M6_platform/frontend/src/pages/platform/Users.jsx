import React, { useState, useMemo } from 'react'
import { getPlatformUsers, getPlatformStudent, platformDeleteUser, platformResetPassword } from '../../api'
import { useFetch, Loader, ErrorBox, Section, Drawer, ActionBtn, confirmRun } from './ui'
import { StatCard, fmtTime } from '../../components/charts'

function StudentDetail({ uid }) {
  const { data, loading, error } = useFetch(() => getPlatformStudent(uid), [uid])
  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />
  const s = data.summary
  return (
    <>
      <div className="pf-stats pf-stats--mini">
        <StatCard label="提问" value={s.questions} />
        <StatCard label="咨询老师" value={s.teachers_consulted} accent="#5a8a72" />
        <StatCard label="评价" value={s.feedback} accent="#c8a24b" />
        <StatCard label="推荐请求" value={s.matches} accent="#b0714a" />
      </div>

      <Section title="对话记忆" desc={`与 ${data.threads.length} 位老师的会话`}>
        {data.threads.length === 0 && <div className="pf-empty">暂无对话</div>}
        {data.threads.map((th, i) => (
          <div className="pf-thread" key={i}>
            <div className="pf-thread__head">{th.teacher_name} <span>· {th.message_count} 条</span></div>
            <ul className="pf-qlist">
              {th.questions.map((q, j) => <li key={j}>{q}</li>)}
            </ul>
          </div>
        ))}
      </Section>

      <Section title="提交的评价">
        {data.feedback.length === 0 && <div className="pf-empty">暂无评价</div>}
        {data.feedback.map((f, i) => (
          <div className="pf-fb" key={i}>
            <span className="pf-stars">{'★'.repeat(f.rating)}{'☆'.repeat(5 - f.rating)}</span>
            <span className="pf-fb__c">{f.comment || '（无评论）'}</span>
            <span className="pf-fb__m">{f.teacher_name} · {fmtTime(f.created_at)}</span>
          </div>
        ))}
      </Section>

      <Section title="推荐匹配请求">
        {data.matches.length === 0 && <div className="pf-empty">暂无推荐</div>}
        {data.matches.map((m, i) => (
          <div className="pf-match" key={i}>
            <div className="pf-match__q">“{m.query}”</div>
            {m.top && <div className="pf-match__top">Top: {m.top.display_name} · 拟合 {m.top.semantic_fit}</div>}
            <div className="pf-match__t">{fmtTime(m.created_at)}</div>
          </div>
        ))}
      </Section>
    </>
  )
}

export default function Users() {
  const { data, loading, error, reload } = useFetch(getPlatformUsers, [])
  const [q, setQ] = useState('')
  const [role, setRole] = useState('')
  const [sel, setSel] = useState(null)

  const doReset = async (u) => {
    const pw = window.prompt(`为用户「${u.username}」设置新密码（至少 4 位）`)
    if (pw == null) return
    if (pw.trim().length < 4) { alert('密码至少 4 位'); return }
    try { await platformResetPassword(u.id, pw.trim()); alert('密码已重置') }
    catch (e) { alert(e.message || '操作失败') }
  }
  const doDelete = (u) =>
    confirmRun(`确认删除用户「${u.username}」？该账号将立即失效，操作不可恢复。`,
      () => platformDeleteUser(u.id), reload)

  const rows = useMemo(() => {
    if (!data) return []
    return data.users.filter(u =>
      (!role || u.role === role) &&
      (!q || (u.username || '').toLowerCase().includes(q.toLowerCase())))
  }, [data, q, role])

  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />

  const students = data.users.filter(u => u.role === 'student')
  const teachers = data.users.filter(u => u.role === 'teacher')

  return (
    <div className="pf-page">
      <h1 className="pf-h1">用户 · 学生</h1>
      <p className="pf-lead">全平台用户名册与学生学习行为。点击学生行查看其对话、评价与推荐记录。</p>

      <div className="pf-stats">
        <StatCard label="用户总数" value={data.total} />
        <StatCard label="学生" value={students.length} accent="#3e6d8e" />
        <StatCard label="教师" value={teachers.length} accent="#5a8a72" />
        <StatCard label="活跃学生" value={students.filter(s => (s.activity?.questions || 0) > 0).length}
          hint="有提问记录" accent="#c8a24b" />
      </div>

      <Section
        right={
          <div className="pf-filters">
            <input className="pf-input" placeholder="搜索用户名…" value={q} onChange={e => setQ(e.target.value)} />
            <select className="pf-input" value={role} onChange={e => setRole(e.target.value)}>
              <option value="">全部角色</option>
              <option value="student">学生</option>
              <option value="teacher">教师</option>
            </select>
          </div>
        }
      >
        <div className="pf-tablewrap">
          <table className="pf-table">
            <thead>
              <tr>
                <th>用户名</th><th>角色</th><th>提问</th><th>会话</th>
                <th>咨询老师</th><th>评价</th><th>推荐</th><th>最近活跃</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(u => {
                const a = u.activity || {}
                const clickable = u.role === 'student'
                return (
                  <tr key={u.id} className={clickable ? 'pf-row--click' : ''}
                    onClick={clickable ? () => setSel(u) : undefined}>
                    <td className="pf-strong">{u.username}</td>
                    <td><span className={`pf-tag pf-tag--${u.role}`}>{u.role === 'student' ? '学生' : '教师'}</span></td>
                    <td>{u.role === 'student' ? a.questions ?? 0 : '—'}</td>
                    <td>{u.role === 'student' ? a.conversations ?? 0 : '—'}</td>
                    <td>{u.role === 'student' ? a.teachers_consulted ?? 0 : '—'}</td>
                    <td>{u.role === 'student' ? a.feedback ?? 0 : '—'}</td>
                    <td>{u.role === 'student' ? a.matches ?? 0 : '—'}</td>
                    <td className="pf-muted">{u.role === 'student' ? fmtTime(a.last_active) : '—'}</td>
                    <td className="pf-actions">
                      <ActionBtn onClick={() => doReset(u)} title="重置密码">重置密码</ActionBtn>
                      <ActionBtn danger onClick={() => doDelete(u)} title="删除账号">删除</ActionBtn>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Section>

      <Drawer open={!!sel} onClose={() => setSel(null)}
        title={sel?.username} subtitle="学生学习档案">
        {sel && <StudentDetail uid={sel.id} />}
      </Drawer>
    </div>
  )
}

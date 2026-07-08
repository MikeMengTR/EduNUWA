import React, { useState, useMemo } from 'react'
import { getPlatformSessions } from '../../api'
import { useFetch, Loader, ErrorBox, Section } from './ui'
import { StatCard, BarsH } from '../../components/charts'

const secs = (s) => (s == null ? '—' : `${Math.floor(s / 60)}′${String(Math.round(s % 60)).padStart(2, '0')}″`)

export default function Sessions() {
  const { data, loading, error } = useFetch(getPlatformSessions, [])
  const [q, setQ] = useState('')

  const rows = useMemo(() => {
    if (!data) return []
    return data.sessions.filter(s =>
      !q || (s.session_id + (s.teacher_name || '')).toLowerCase().includes(q.toLowerCase()))
  }, [data, q])

  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />

  const totalEvents = data.sessions.reduce((a, s) => a + s.event_count, 0)
  const totalDur = data.sessions.reduce((a, s) => a + (s.duration_sec || 0), 0)

  return (
    <div className="pf-page">
      <h1 className="pf-h1">课堂会话</h1>
      <p className="pf-lead">每一次虚拟课堂讲授的事件构成与时长。</p>

      <div className="pf-stats">
        <StatCard label="会话总数" value={data.total} />
        <StatCard label="教学事件" value={totalEvents} accent="#3e6d8e" />
        <StatCard label="累计时长" value={Math.round(totalDur / 60)} hint="分钟" accent="#5a8a72" />
        <StatCard label="平均事件/会话" value={data.total ? Math.round(totalEvents / data.total) : 0} accent="#7d5a9e" />
      </div>

      <Section title="教学事件类型分布" desc="speak 讲解 / board 板书 / formula 公式 / pause 停顿 等">
        <BarsH data={data.type_total} accent="#3e6d8e" />
      </Section>

      <Section title="会话明细" right={
        <input className="pf-input" placeholder="搜索会话 / 老师…" value={q} onChange={e => setQ(e.target.value)} />
      }>
        <div className="pf-tablewrap pf-tablewrap--tall">
          <table className="pf-table">
            <thead>
              <tr><th>会话 ID</th><th>日期</th><th>教师</th><th>音色</th><th>事件</th><th>构成</th><th>时长</th></tr>
            </thead>
            <tbody>
              {rows.map(s => (
                <tr key={s.session_id}>
                  <td className="pf-mono">{s.session_id}</td>
                  <td className="pf-muted">{s.date || '—'}</td>
                  <td>{s.teacher_name || <span className="pf-muted">未关联</span>}</td>
                  <td className="pf-muted">{s.voice_id || '—'}</td>
                  <td>{s.event_count}</td>
                  <td>
                    <span className="pf-typechips">
                      {Object.entries(s.type_counts).map(([k, v]) => (
                        <span className="pf-typechip" key={k}>{k}<b>{v}</b></span>
                      ))}
                    </span>
                  </td>
                  <td className="pf-muted">{secs(s.duration_sec)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}

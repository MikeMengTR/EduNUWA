import React from 'react'
import { getPlatformFeedback, platformDeleteFeedback } from '../../api'
import { useFetch, Loader, ErrorBox, Section, ActionBtn, confirmRun } from './ui'
import { StatCard, BarsH, LineChart, fmtTime } from '../../components/charts'

export default function Feedback() {
  const { data, loading, error, reload } = useFetch(getPlatformFeedback, [])
  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />

  const five = (data.rating_dist.find(r => r.label === '5★') || {}).value || 0

  return (
    <div className="pf-page">
      <h1 className="pf-h1">反馈评价</h1>
      <p className="pf-lead">全平台课堂口碑——评分分布、趋势与逐条评论。</p>

      <div className="pf-stats">
        <StatCard label="评价总数" value={data.total} />
        <StatCard label="平均评分" value={data.avg_rating} accent="#c8a24b" />
        <StatCard label="五星好评" value={five} accent="#5a8a72" />
        <StatCard label="覆盖教师" value={data.by_teacher.length} accent="#3e6d8e" />
      </div>

      <div className="pf-grid pf-grid--2">
        <Section title="评分分布"><BarsH data={data.rating_dist} accent="#c8a24b" /></Section>
        <Section title="评价趋势"><LineChart data={data.trend} accent="#5a8a72" /></Section>
      </div>

      <Section title="教师口碑榜" desc="按评价数排序">
        <div className="pf-tablewrap">
          <table className="pf-table">
            <thead><tr><th>教师</th><th>评价数</th><th>平均分</th><th>口碑</th></tr></thead>
            <tbody>
              {data.by_teacher.map((t, i) => (
                <tr key={i}>
                  <td className="pf-strong">{t.teacher_name}</td>
                  <td>{t.count}</td>
                  <td>{t.avg}</td>
                  <td><span className="pf-stars">{'★'.repeat(Math.round(t.avg))}{'☆'.repeat(5 - Math.round(t.avg))}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="最新评价" desc={`共 ${data.total} 条`}>
        {data.items.slice(0, 60).map((f, i) => (
          <div className="pf-fb" key={i}>
            <span className="pf-stars">{'★'.repeat(f.rating)}{'☆'.repeat(5 - f.rating)}</span>
            <span className="pf-fb__c">{f.comment || '（无评论）'}</span>
            <span className="pf-fb__m">{f.user_name || '匿名'} → {f.teacher_name} · {fmtTime(f.created_at)}</span>
            <ActionBtn danger onClick={() => confirmRun(
              `删除「${f.user_name || '匿名'}」对「${f.teacher_name}」的这条评价？`,
              () => platformDeleteFeedback(f.teacher_id, f.id), reload)}>删除</ActionBtn>
          </div>
        ))}
      </Section>
    </div>
  )
}

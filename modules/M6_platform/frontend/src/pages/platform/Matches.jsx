import React from 'react'
import { getPlatformMatches } from '../../api'
import { useFetch, Loader, ErrorBox, Section } from './ui'
import { StatCard, BarsH, TagCloud, fmtTime } from '../../components/charts'

export default function Matches() {
  const { data, loading, error } = useFetch(getPlatformMatches, [])
  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />

  const avgCand = data.total
    ? Math.round(data.items.reduce((a, m) => a + (m.candidates || 0), 0) / data.total)
    : 0

  return (
    <div className="pf-page">
      <h1 className="pf-h1">推荐匹配</h1>
      <p className="pf-lead">学生「按风格找老师」的检索记录与命中效果。</p>

      <div className="pf-stats">
        <StatCard label="推荐请求" value={data.total} />
        <StatCard label="平均候选教师" value={avgCand} accent="#3e6d8e" />
        <StatCard label="命中教师数" value={data.top_hits.length} accent="#5a8a72" />
        <StatCard label="风格标签命中" value={data.tag_freq.length} accent="#7d5a9e" />
      </div>

      <div className="pf-grid pf-grid--2">
        <Section title="Top1 命中教师" desc="被排在首位的次数"><BarsH data={data.top_hits} accent="#de5e39" /></Section>
        <Section title="首位语义拟合度分布"><BarsH data={data.fit_dist} accent="#5a8a72" /></Section>
      </div>

      <Section title="命中风格标签词云" desc="推荐结果中 matched_tags 的高频词">
        <TagCloud data={data.tag_freq} />
      </Section>

      <Section title="检索明细" desc={`共 ${data.total} 条`}>
        <div className="pf-tablewrap pf-tablewrap--tall">
          <table className="pf-table">
            <thead><tr><th>学生</th><th>查询</th><th>首位教师</th><th>学科</th><th>拟合</th><th>候选</th><th>时间</th></tr></thead>
            <tbody>
              {data.items.map((m, i) => (
                <tr key={i}>
                  <td className="pf-muted">{m.user_name || '匿名'}</td>
                  <td className="pf-strong">{m.query}</td>
                  <td>{m.top?.teacher_name || '—'}</td>
                  <td className="pf-muted">{m.top?.subject || '—'}</td>
                  <td>{m.top?.semantic_fit ?? '—'}</td>
                  <td className="pf-muted">{m.candidates}</td>
                  <td className="pf-muted">{fmtTime(m.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}

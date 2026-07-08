import React from 'react'
import { getPlatformOverview } from '../../api'
import { useFetch, Loader, ErrorBox, Section } from './ui'
import { StatCard, DonutChart, BarsH, LineChart } from '../../components/charts'

export default function Overview() {
  const { data, loading, error } = useFetch(getPlatformOverview, [])
  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />
  const t = data.totals

  return (
    <div className="pf-page">
      <h1 className="pf-h1">平台总览</h1>
      <p className="pf-lead">全平台数据快照——用户、教师质量、课堂活跃、推荐与口碑。</p>

      <div className="pf-stats">
        <StatCard label="用户总数" value={t.users} hint={`学生 ${t.students} · 教师 ${t.teacher_accounts}`} />
        <StatCard label="教师档案" value={t.teacher_profiles} accent="#5a8a72" />
        <StatCard label="课堂会话" value={t.sessions} accent="#3e6d8e" />
        <StatCard label="课程 / 章节" value={t.courses} hint={`${t.chapters} 章节`} accent="#7d5a9e" />
        <StatCard label="反馈评价" value={t.feedback} hint={`均分 ${data.avg_rating}`} accent="#c8a24b" />
        <StatCard label="推荐匹配" value={t.matches} accent="#b0714a" />
        <StatCard label="转写素材" value={t.transcripts} accent="#4f9e6a" />
        <StatCard label="教学图库" value={t.media_images} accent="#3e6d8e" />
      </div>

      <div className="pf-grid pf-grid--2">
        <Section title="用户角色占比">
          <DonutChart data={data.role_dist} />
        </Section>
        <Section title="评分分布" desc="全平台课堂评价星级">
          <BarsH data={data.rating_dist} accent="#c8a24b" />
        </Section>
      </div>

      <Section title="近 21 天平台活跃" desc="反馈 + 推荐 + 课堂会话合计">
        <LineChart data={data.activity} />
      </Section>

      <Section title="学科分布" desc="按教师档案所授科目">
        <BarsH data={data.subject_dist} accent="#5a8a72" />
      </Section>
    </div>
  )
}

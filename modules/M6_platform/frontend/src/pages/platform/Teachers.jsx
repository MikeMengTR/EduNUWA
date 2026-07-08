import React, { useState } from 'react'
import {
  getPlatformTeachers, getPlatformTeacher, platformSetTeacherVisibility,
  platformSetCoursePublish, platformDeleteCourse, platformDeleteFeedback,
  platformAssignAccount,
} from '../../api'
import { useFetch, Loader, ErrorBox, Section, Drawer, ActionBtn, confirmRun } from './ui'
import { StatCard, BarsH, fmtTime, fmtDate } from '../../components/charts'
import { StyleSketchCard, TeachingStyleCard } from '../../components/StyleProfile'
import Icon from '../../components/Icon'

function TeacherDetail({ tid, onMutate }) {
  const { data, loading, error, reload } = useFetch(() => getPlatformTeacher(tid), [tid])
  const after = () => { reload(); if (onMutate) onMutate() }
  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />
  const c = data.card
  const hidden = !!c.hidden
  return (
    <>
      <div className="pf-tprofile">
        {c.avatar?.pixel_url && <img className="pf-tprofile__av" src={c.avatar.pixel_url} alt="" />}
        <div>
          <div className="pf-tprofile__name">{c.real_name || c.display_name}{hidden && <span className="pf-chip pf-chip--off" style={{ marginLeft: 8 }}>已下架</span>}</div>
          <div className="pf-tprofile__meta">{c.subject} · {c.school}</div>
          <div className="pf-chips">
            {data.account
              ? <span className="pf-chip pf-chip--ok">账号 {data.account.username}</span>
              : <span className="pf-chip pf-chip--off">⚠ 无账号</span>}
            <span className="pf-chip">均分 {(c.stats || {}).avg_rating ?? '—'}</span>
            <span className="pf-chip">反馈 {data.feedback.length}</span>
            <span className="pf-chip">{data.has_voice ? '专属音色 ✓' : '无专属音色'}</span>
            {!data.account && (
              <ActionBtn onClick={() => confirmRun(
                `为「${c.real_name || c.display_name}」创建登录账号？将自动分配下一个 t 编号，初始密码 1234。`,
                async () => { const r = await platformAssignAccount(tid); window.alert(`已分配账号：${r.username}\n初始密码：${r.password}`) },
                after)}>分配账号</ActionBtn>
            )}
            <ActionBtn danger={!hidden}
              onClick={() => confirmRun(
                `${hidden ? '上架' : '下架'}教师「${c.real_name || c.display_name}」？${hidden ? '上架后' : '下架后'}学生发现页与智能匹配${hidden ? '将重新展示' : '将不再展示'} ta。`,
                () => platformSetTeacherVisibility(tid, !hidden), after)}>
              {hidden ? '重新上架' : '下架该教师'}
            </ActionBtn>
          </div>
        </div>
      </div>

      {/* 风格速写 + 教学风格指纹：复用学生端同一组件，口径完全对齐 */}
      <div className="tp2 pf-style">
        <StyleSketchCard teacher={data.card} showCloud={false} />
        <TeachingStyleCard teacher={data.card} />
      </div>

      <Section title="评分分布">
        <BarsH data={data.rating_dist} accent="#c8a24b" />
      </Section>

      <Section title="Skill 版本演化" desc={`共 ${data.skill_versions.length} 个版本`}>
        <div className="pf-timeline">
          {data.skill_versions.map((v, i) => (
            <div className="pf-timeline__item" key={i}>
              <span className="pf-timeline__dot" />
              <div>
                <b>{v.dir}</b> <span className="pf-muted">v{v.version ?? '?'} · {v.n_tags} 标签</span>
                <div className="pf-muted pf-sm">{fmtTime(v.generated_at)}</div>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="课程" desc={`${data.courses.length} 门`}>
        {data.courses.length === 0 && <div className="pf-empty">暂无课程</div>}
        {data.courses.map((c2, i) => (
          <div className="pf-listrow" key={i}>
            <div>
              <b>{c2.title}</b>
              <span className="pf-muted"> · {c2.chapters} 章 · {Math.round((c2.duration_sec || 0) / 60)} 分钟 · {c2.published ? '已发布' : '草稿'}</span>
            </div>
            <span className="pf-actions">
              <ActionBtn onClick={() => confirmRun(
                `${c2.published ? '下架' : '上架'}课程「${c2.title}」？`,
                () => platformSetCoursePublish(tid, c2.course_id, !c2.published), after)}>
                {c2.published ? '下架' : '上架'}
              </ActionBtn>
              <ActionBtn danger onClick={() => confirmRun(
                `删除课程「${c2.title}」？该课程及其所有章节将被永久删除，不可恢复。`,
                () => platformDeleteCourse(tid, c2.course_id), after)}>删除</ActionBtn>
            </span>
          </div>
        ))}
      </Section>

      <Section title="近期反馈" desc={`转写素材 ${data.transcripts.length} 份 · 进化运行 ${data.evolution.runs_total} 次`}>
        {data.feedback.slice(0, 12).map((f, i) => (
          <div className="pf-fb" key={i}>
            <span className="pf-stars">{'★'.repeat(f.rating)}{'☆'.repeat(5 - f.rating)}</span>
            <span className="pf-fb__c">{f.comment || '（无评论）'}</span>
            <span className="pf-fb__m">{f.user_name || '匿名'} · {fmtDate(f.created_at)}</span>
            <ActionBtn danger onClick={() => confirmRun('删除这条评价？', () => platformDeleteFeedback(tid, f.id), after)}>删除</ActionBtn>
          </div>
        ))}
      </Section>
    </>
  )
}

export default function Teachers() {
  const { data, loading, error, reload } = useFetch(getPlatformTeachers, [])
  const [sel, setSel] = useState(null)
  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />

  const ratings = data.teachers.map(t => t.avg_rating).filter(r => r > 0)
  const avg = ratings.length ? (ratings.reduce((a, b) => a + b, 0) / ratings.length).toFixed(2) : '—'

  return (
    <div className="pf-page">
      <h1 className="pf-h1">教师</h1>
      <p className="pf-lead">教师档案、讲解风格指纹与质量口碑。点击卡片查看完整画像。</p>

      <div className="pf-stats">
        <StatCard label="教师档案" value={data.total} />
        <StatCard label="平均评分" value={avg} accent="#c8a24b" />
        <StatCard label="配置音色" value={data.teachers.filter(t => t.has_voice).length} accent="#5a8a72" />
        <StatCard label="开设课程" value={data.teachers.reduce((s, t) => s + t.course_count, 0)} accent="#7d5a9e" />
      </div>

      <div className="pf-tgrid">
        {data.teachers.map(t => (
          <button className="pf-tcard" key={t.teacher_id} onClick={() => setSel(t)}>
            <div className="pf-tcard__top">
              {t.avatar ? <img src={t.avatar} alt="" /> : <span className="pf-tcard__ph"><Icon name="user" size={22} /></span>}
              <div>
                <div className="pf-tcard__name">{t.real_name || t.display_name}</div>
                <div className="pf-tcard__sub">{t.subject || '—'} · {t.school || '—'}</div>
              </div>
            </div>
            {t.style_line && <div className="pf-tcard__style">“{t.style_line}”</div>}
            <div className="pf-tcard__stars">
              {'★'.repeat(Math.round(t.avg_rating || 0))}{'☆'.repeat(5 - Math.round(t.avg_rating || 0))}
              <span className="pf-muted"> {t.avg_rating || 0}</span>
            </div>
            <div className="pf-chips">
              {t.hidden && <span className="pf-chip pf-chip--off">已下架</span>}
              {!t.account_username && <span className="pf-chip pf-chip--off">⚠ 无账号</span>}
              <span className="pf-chip">反馈 {t.feedback_count}</span>
              <span className="pf-chip">版本 {t.skill_versions}</span>
              <span className="pf-chip">课程 {t.course_count}</span>
              {t.crowd_tags > 0 && <span className="pf-chip">众评 {t.crowd_tags}</span>}
              {t.has_voice && <span className="pf-chip pf-chip--ok">音色 ✓</span>}
            </div>
          </button>
        ))}
      </div>

      <Drawer open={!!sel} onClose={() => setSel(null)}
        title={sel?.real_name || sel?.display_name} subtitle="教师完整画像">
        {sel && <TeacherDetail tid={sel.teacher_id} onMutate={reload} />}
      </Drawer>
    </div>
  )
}

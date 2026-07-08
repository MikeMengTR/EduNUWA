import React, { useState, useMemo } from 'react'
import { getPlatformMedia, platformSetMediaStatus, platformDeleteMedia } from '../../api'
import { useFetch, Loader, ErrorBox, Section, ActionBtn, confirmRun } from './ui'
import { StatCard, BarsH, DonutChart } from '../../components/charts'

export default function Media() {
  const { data, loading, error, reload } = useFetch(getPlatformMedia, [])
  const [subj, setSubj] = useState('')

  const items = useMemo(() => {
    if (!data) return []
    return data.items.filter(i => !subj || i.subject === subj)
  }, [data, subj])

  if (loading) return <Loader />
  if (error) return <ErrorBox error={error} />

  return (
    <div className="pf-page">
      <h1 className="pf-h1">内容图库</h1>
      <p className="pf-lead">黑板教学插图库的学科覆盖与素材明细。</p>

      <div className="pf-stats">
        <StatCard label="图片总数" value={data.total} />
        <StatCard label="启用中" value={data.active} accent="#5a8a72" />
        <StatCard label="覆盖学科" value={data.subject_dist.length} accent="#3e6d8e" />
        <StatCard label="动图 GIF" value={(data.type_dist.find(t => t.label === 'gif') || {}).value || 0} accent="#7d5a9e" />
      </div>

      <div className="pf-grid pf-grid--2">
        <Section title="学科分布"><BarsH data={data.subject_dist} accent="#5a8a72" /></Section>
        <Section title="素材类型"><DonutChart data={data.type_dist} /></Section>
      </div>

      <Section title="素材库" right={
        <select className="pf-input" value={subj} onChange={e => setSubj(e.target.value)}>
          <option value="">全部学科</option>
          {data.subject_dist.map(s => <option key={s.label} value={s.label}>{s.label}</option>)}
        </select>
      }>
        <div className="pf-mgrid">
          {items.map(im => {
            const off = im.status !== 'active'
            return (
              <figure className={`pf-mcard ${off ? 'pf-mcard--off' : ''}`} key={im.id}>
                <img src={im.url} alt={im.caption} loading="lazy"
                  onError={e => { e.currentTarget.style.display = 'none' }} />
                <figcaption>
                  <div className="pf-mcard__topic">{im.topic || im.id}{off && <span className="pf-chip pf-chip--off" style={{ marginLeft: 6 }}>已停用</span>}</div>
                  <div className="pf-mcard__cap">{im.caption}</div>
                  <div className="pf-mcard__kw">
                    {(im.keywords || []).slice(0, 6).map((k, i) => <span key={i}>{k}</span>)}
                  </div>
                  <div className="pf-actions">
                    <ActionBtn onClick={() => confirmRun(
                      `${off ? '启用' : '停用'}图片「${im.topic || im.id}」？${off ? '启用后' : '停用后'}黑板检索${off ? '可再次调用' : '将不再调用'}它。`,
                      () => platformSetMediaStatus(im.id, off ? 'active' : 'disabled'), reload)}>
                      {off ? '启用' : '停用'}
                    </ActionBtn>
                    <ActionBtn danger onClick={() => confirmRun(
                      `删除图片「${im.topic || im.id}」？图片文件将被永久删除，不可恢复。`,
                      () => platformDeleteMedia(im.id), reload)}>删除</ActionBtn>
                  </div>
                </figcaption>
              </figure>
            )
          })}
        </div>
      </Section>
    </div>
  )
}

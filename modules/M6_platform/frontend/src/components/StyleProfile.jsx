/* =========================================================================
   教学风格可视化 —— 由 TeacherProfile 抽出的共享组件，学生端详情页与教师端
   工作台共用，保证「学生看到的」与「老师看到的自己」完全一致，不再两份漂移。
   全部沿用 .tp2 作用域样式（见 TeacherProfile.css）。
   ========================================================================= */
import { useEffect, useRef } from 'react'
import Icon from './Icon'
import '../pages/TeacherProfile.css'

/* 风格维度 → 三色分组 */
const DIM_GROUP = {
  abstraction: 'intuit', interactivity: 'style', pace: 'style',
  detail: 'form', rigor: 'form', structure: 'form',
}
const GROUPS = {
  form: { key: 'form', label: '形式 · 逻辑' },
  intuit: { key: 'intuit', label: '直觉 · 类比' },
  style: { key: 'style', label: '节奏 · 态度' },
}
const groupOf = (dim) => DIM_GROUP[dim] || 'form'
const groupColor = (g) => `var(--c-${g})`

const VALUE_ZH = {
  high: '高', mid: '中', medium: '中', low: '低',
  'phenomenon-driven': '现象驱动', 'definition-first': '定义先行', 'problem-driven': '问题驱动',
  'intuition-first': '直觉优先', 'formal-first': '形式优先',
  'proactive-explicit': '主动显式', 'proactive': '主动', 'reactive': '被动响应',
  'title-bullets': '标题要点', 'comparison-table': '对照表格', 'free-form': '自由板书',
  'with-speak': '边讲边写', 'after-speak': '讲后补写',
}
const zh = (v) => VALUE_ZH[v] || (typeof v === 'string' ? v : '')

function buildTagline(tags, teacher) {
  const top = [...tags].sort((a, b) => (b.confidence || 0) - (a.confidence || 0))[0]
  if (top) {
    const first = String(top.text || top).split(/[、，,；;]/)[0].trim()
    if (first) return first
  }
  if (teacher.subject) return `把${teacher.subject}讲清楚`
  return teacher.display_name || '教学风格'
}

function buildSketch(teacher, tags) {
  if (teacher.bio && teacher.bio.trim()) return teacher.bio
  if (!tags.length) return ''
  const top = tags.slice(0, 5).map((t) => t.text || t)
  const subj = teacher.subject ? `的${teacher.subject}课` : '课堂'
  let s = `这位老师${subj}，${top.slice(0, 3).join('、')}`
  if (top.length > 3) s += `；${top.slice(3).join('、')}`
  return s + '。'
}

function buildCloudWords(tags, liveTags) {
  const seen = new Map()
  const add = (text, weight, group) => {
    const t = String(text).trim()
    if (!t) return
    const cur = seen.get(t)
    if (cur) cur.w = Math.max(cur.w, weight)
    else seen.set(t, { t, w: weight, g: group })
  }
  const split = (s) => String(s).split(/[、，,；;。\s/]+/).filter(Boolean)
  tags.forEach((tag) => {
    const w = (tag.confidence || 0.7) * 10
    split(tag.text || tag).forEach((p) => add(p, w, groupOf(tag.dimension)))
  })
  liveTags.forEach((tag) => {
    const w = 4 + Math.min(tag.support || 1, 6)
    split(tag.text || '').forEach((p) => add(p, w, groupOf(tag.dimension)))
  })
  return Array.from(seen.values()).sort((a, b) => b.w - a.w).slice(0, 18)
}

function buildRadar(base, ped, tags) {
  const ax = []
  const clamp = (v) => Math.max(0.12, Math.min(1, v))
  if (base?.question_freq?.value != null) ax.push({ label: '设问频率', v: clamp(base.question_freq.value / 8) })
  const lvl = { high: 0.9, mid: 0.6, medium: 0.6, low: 0.3 }
  if (ped?.analogy_density?.level) ax.push({ label: '类比密度', v: clamp(lvl[ped.analogy_density.level] ?? 0.6) })
  if (ped?.intuition_building?.order) ax.push({ label: '直觉优先', v: ped.intuition_building.order === 'intuition-first' ? 0.9 : 0.4 })
  if (ped?.misconception_alert?.mode) ax.push({ label: '主动防错', v: String(ped.misconception_alert.mode).startsWith('proactive') ? 0.85 : 0.45 })
  const hasSummary = tags.some((t) => /总结|结构/.test(t.text || t))
  if (hasSummary || ped?.blackboard_strategy) ax.push({ label: '结构总结', v: hasSummary ? 0.8 : ped?.blackboard_strategy?.minimal_text ? 0.7 : 0.55 })
  const pol = { slow: 0.35, mid: 0.6, medium: 0.6, fast: 0.85 }
  if (base?.speech_rate?.polarity) ax.push({ label: '语速节奏', v: clamp(pol[base.speech_rate.polarity] ?? 0.55) })
  return ax
}

function buildAttributes(base, ped) {
  const rows = []
  if (ped?.analogy_density?.level) rows.push({ k: '类比密度', en: 'analogy density', v: zh(ped.analogy_density.level), sub: ped.analogy_density.level })
  if (ped?.concept_entry?.primary) rows.push({ k: '概念入口', en: 'concept entry', v: zh(ped.concept_entry.primary), sub: ped.concept_entry.primary })
  if (ped?.intuition_building?.order) rows.push({ k: '直觉建构', en: 'intuition building', v: zh(ped.intuition_building.order), sub: ped.intuition_building.order })
  if (ped?.misconception_alert?.mode) rows.push({ k: '防错策略', en: 'misconception alert', v: zh(ped.misconception_alert.mode), sub: ped.misconception_alert.mode })
  if (ped?.blackboard_strategy) {
    const bs = ped.blackboard_strategy
    rows.push({ k: '板书策略', en: 'blackboard strategy', v: bs.minimal_text ? '极简骨架' : zh(bs.primary_layout) || '—', sub: bs.minimal_text ? 'skeleton-only' : bs.primary_layout })
  }
  if (base?.speech_rate?.value != null) rows.push({ k: '语速', en: 'speech rate', v: base.speech_rate.label || '—', sub: `${Math.round(base.speech_rate.value)} ${base.speech_rate.unit || ''}`.trim() })
  if (base?.question_freq?.value != null) rows.push({ k: '设问频率', en: 'question freq', v: base.question_freq.label || '—', sub: `${base.question_freq.value} ${base.question_freq.unit || ''}`.trim() })
  return rows
}

/* 关键词云 —— 螺旋布局 + 错峰渐显 */
function StyleCloud({ words }) {
  const hostRef = useRef(null)
  useEffect(() => {
    const host = hostRef.current
    if (!host || !words.length) return
    const family = getComputedStyle(document.documentElement).getPropertyValue('--font-body').trim() || 'sans-serif'
    const ctx = document.createElement('canvas').getContext('2d')
    const FMIN = 15, FMAX = 40, ASPECT = 0.6, STEP = 0.15, GROWTH = 2.0, PAD = 5
    let timers = []
    const render = () => {
      timers.forEach(clearTimeout); timers = []
      const W = host.clientWidth || 640, H = host.clientHeight || 280
      host.innerHTML = ''
      const ws = words.map((x) => x.w)
      const minW = Math.min(...ws), maxW = Math.max(...ws), span = maxW - minW || 1
      const sorted = [...words].sort((a, b) => b.w - a.w)
      const placed = [], cx = W / 2, cy = H / 2, items = []
      sorted.forEach((wd) => {
        const fs = FMIN + ((wd.w - minW) / span) * (FMAX - FMIN)
        ctx.font = '600 ' + fs + 'px ' + family
        const wpx = ctx.measureText(wd.t).width + PAD * 2
        const hpx = fs * 1.18 + PAD * 2
        let box = null
        for (let t = 0; t < 5000; t += STEP) {
          const r = 4 + GROWTH * t
          const x = cx + r * Math.cos(t), y = cy + r * Math.sin(t) * ASPECT
          const b = { x: x - wpx / 2, y: y - hpx / 2, w: wpx, h: hpx }
          if (b.x < 0 || b.y < 0 || b.x + b.w > W || b.y + b.h > H) continue
          let hit = false
          for (const p of placed) {
            if (b.x < p.x + p.w && b.x + b.w > p.x && b.y < p.y + p.h && b.y + b.h > p.y) { hit = true; break }
          }
          if (!hit) { box = b; break }
        }
        if (!box) box = { x: cx - wpx / 2, y: cy - hpx / 2, w: wpx, h: hpx }
        placed.push(box); items.push({ wd, fs, box })
      })
      items.forEach((it, idx) => {
        const el = document.createElement('span')
        el.className = 'tp2-w'
        el.textContent = it.wd.t
        el.style.left = it.box.x + PAD + 'px'
        el.style.top = it.box.y + 'px'
        el.style.fontSize = it.fs + 'px'
        el.style.color = groupColor(it.wd.g)
        const finalOp = (0.6 + ((it.wd.w - minW) / span) * 0.4).toFixed(2)
        host.appendChild(el)
        const tm = setTimeout(() => { el.classList.add('in'); el.style.opacity = finalOp }, idx * 45)
        timers.push(tm)
      })
    }
    render()
    const ro = new ResizeObserver(() => render())
    ro.observe(host)
    return () => { ro.disconnect(); timers.forEach(clearTimeout) }
  }, [words])
  return <div className="tp2-cloud" ref={hostRef} role="img" aria-label="教学风格关键词云" />
}

/* 教学风格雷达图（纯 SVG） */
function StyleRadar({ axes }) {
  const S = 280, cx = 140, cy = 140, R = 92, n = axes.length
  if (n < 3) return null
  const pt = (i, rad) => {
    const a = (-90 + i * (360 / n)) * Math.PI / 180
    return [cx + rad * Math.cos(a), cy + rad * Math.sin(a)]
  }
  const rings = [0.25, 0.5, 0.75, 1].map((f) => {
    let d = ''
    for (let i = 0; i < n; i++) { const p = pt(i, R * f); d += (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1) + ' ' }
    return d + 'Z'
  })
  let area = ''
  axes.forEach((a, i) => { const p = pt(i, R * a.v); area += (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1) + ' ' })
  area += 'Z'
  return (
    <svg className="tp2-radar" viewBox={`0 0 ${S} ${S}`} width={S} height={S} xmlns="http://www.w3.org/2000/svg">
      {rings.map((d, i) => <path key={'r' + i} className="ring" d={d} />)}
      {axes.map((_, i) => { const p = pt(i, R); return <line key={'s' + i} className="spoke" x1={cx} y1={cy} x2={p[0].toFixed(1)} y2={p[1].toFixed(1)} /> })}
      <path className="area" d={area} />
      {axes.map((a, i) => { const p = pt(i, R * a.v); return <circle key={'p' + i} className="pt" cx={p[0].toFixed(1)} cy={p[1].toFixed(1)} r="3" /> })}
      {axes.map((a, i) => {
        const p = pt(i, R + 20)
        let anchor = 'middle', dy = '0.35em'
        if (p[0] > cx + 8) anchor = 'start'; else if (p[0] < cx - 8) anchor = 'end'
        if (p[1] < cy - 8) dy = '0em'; else if (p[1] > cy + 8) dy = '0.7em'
        return <text key={'t' + i} x={p[0].toFixed(1)} y={p[1].toFixed(1)} textAnchor={anchor} dy={dy}>{a.label}</text>
      })}
    </svg>
  )
}

export function Stars({ value, size = 15 }) {
  return (
    <span className="stars">
      {[1, 2, 3, 4, 5].map((i) => (
        <Icon key={i} name="star" size={size} className={`star ${i <= value ? 'on' : ''}`} />
      ))}
    </span>
  )
}

export const Eyebrow = ({ children }) => <div className="tp2-eyebrow">{children}</div>

/* 由 teacher 派生展示所需的一切（rawTags / liveTags / 各种衍生数据） */
export function deriveStyle(teacher) {
  const rawTags = Array.isArray(teacher.style_tags) && teacher.style_tags.length
    ? teacher.style_tags
    : (teacher.tags || []).map((t) => (typeof t === 'string' ? { text: t } : t))
  const liveTags = teacher.live_tags || []
  const base = teacher.base_metrics
  const ped = teacher.pedagogy
  const radarAxes = buildRadar(base, ped, rawTags)
  const attrs = buildAttributes(base, ped)
  return {
    rawTags, liveTags, base, ped,
    tagline: buildTagline(rawTags, teacher),
    sketch: buildSketch(teacher, rawTags),
    cloudWords: buildCloudWords(rawTags, liveTags),
    radarAxes, attrs,
    hasStyle: rawTags.length > 0 || liveTags.length > 0 || radarAxes.length >= 3 || attrs.length > 0,
  }
}

/* —— 风格速写 hero（tagline + 速写 + 关键词云）——
   showCloud=false 时隐藏螺旋词云（如平台监控台窄抽屉里，词云会挤乱，改由
   TeachingStyleCard 的分组标签呈现）。 */
export function StyleSketchCard({ teacher, showCloud = true }) {
  const { rawTags, liveTags, tagline, sketch, cloudWords } = deriveStyle(teacher)
  return (
    <section className="tp2-card">
      <Eyebrow>风格速写</Eyebrow>
      <h1 className="tp2-tagline">
        {tagline}
        <svg viewBox="0 0 300 14" preserveAspectRatio="none" aria-hidden="true">
          <path d="M3 9 C 70 3, 150 13, 230 6 S 295 8, 297 7" />
        </svg>
      </h1>
      {sketch && <p className="tp2-sketch">{sketch}</p>}
      {showCloud && cloudWords.length > 0 && (
        <div className="tp2-cloud-zone">
          <div className="tp2-cloud-cap">
            <span>由 {rawTags.length} 个蒸馏标签{liveTags.length ? ` 与 ${liveTags.length} 个学生众评标签` : ''}聚合 · 字号越大 = 越突出</span>
            <span className="tp2-legend"><span className="tp2-swatch" style={{ background: 'var(--c-form)' }} />形式·逻辑</span>
            <span className="tp2-legend"><span className="tp2-swatch" style={{ background: 'var(--c-intuit)' }} />直觉·类比</span>
            <span className="tp2-legend"><span className="tp2-swatch" style={{ background: 'var(--c-style)' }} />节奏·态度</span>
          </div>
          <StyleCloud words={cloudWords} />
        </div>
      )}
    </section>
  )
}

/* —— 教学风格（雷达 + 属性表 + 三色分组标签 + 众评）—— */
export function TeachingStyleCard({ teacher }) {
  const { rawTags, liveTags, radarAxes, attrs, hasStyle } = deriveStyle(teacher)
  if (!hasStyle) return null
  const grouped = { form: [], intuit: [], style: [] }
  rawTags.forEach((t) => grouped[groupOf(t.dimension)].push(t.text || t))
  return (
    <section className="tp2-card">
      <Eyebrow>教学风格</Eyebrow>
      {(radarAxes.length >= 3 || attrs.length > 0) && (
        <div className="tp2-style-grid">
          {radarAxes.length >= 3 && (
            <div className="tp2-radar-wrap">
              <StyleRadar axes={radarAxes} />
              <div className="tp2-radar-note">数值据风格标签与教学策略推算，仅作示意</div>
            </div>
          )}
          {attrs.length > 0 && (
            <div className="tp2-attrs">
              {attrs.map((a, i) => (
                <div key={i} className="tp2-attr">
                  <span className="tp2-attr-k">{a.k} · {a.en}</span>
                  <span className="tp2-attr-v">{a.v}{a.sub && <small>{a.sub}</small>}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {rawTags.length > 0 && (
        <div className="tp2-tags-block">
          {Object.values(GROUPS).map((g) =>
            grouped[g.key].length ? (
              <div key={g.key} className={`tp2-tag-grp t-${g.key}`}>
                <span className="tp2-tag-lab">{g.label}</span>
                <div className="tp2-tag-row">
                  {grouped[g.key].map((t, i) => <span key={i} className="tp2-tag">{t}</span>)}
                </div>
              </div>
            ) : null
          )}
        </div>
      )}
      {liveTags.length > 0 && (
        <div className="tp2-crowd">
          <span className="tp2-tag-lab tp2-crowd-lab">学生众评</span>
          <div className="tp2-tag-row">
            {liveTags.map((t, i) => (
              <span key={i} className="tp2-crowd-chip" title={`来自 ${t.support} 名学生的反馈`}>
                {t.text}<span className="tp2-crowd-n">{t.support} 名学生</span>
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}

/* —— 学生评价（统计头 + 可选写评价区[action/children] + 列表）—— */
export function StudentReviewsCard({ feedback, action = null, children = null }) {
  const stats = feedback?.stats || { total: 0, avg_rating: 0 }
  const list = feedback?.feedback || []
  return (
    <section className="tp2-card">
      <div className="tp2-section-head">
        <Eyebrow>学生评价 · {stats.total}</Eyebrow>
        {action}
      </div>
      {children}
      {list.length > 0 ? (
        <div className="review-list">
          {list.slice(0, 20).map((f) => (
            <div key={f.id} className="review-item">
              <div className="review-item__head">
                <Stars value={f.rating} />
                <span className="review-item__date">{new Date(f.created_at).toLocaleDateString()}</span>
              </div>
              <p>{f.comment}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="review-empty">暂无学生评价。</p>
      )}
    </section>
  )
}

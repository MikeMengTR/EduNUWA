// 平台监控台专用：零依赖手写 SVG / CSS 图表组件。
// 统一吃 {label, value}[] 类入参，纸感配色，空数据安全降级。
import React from 'react'

export const PALETTE = ['#de5e39', '#5a8a72', '#3e6d8e', '#7d5a9e', '#c8a24b', '#b0714a', '#4f9e6a', '#9e6a4f']

export const fmtNum = (n) => (n == null ? '—' : Number(n).toLocaleString('zh-CN'))
export const fmtDate = (s) => (s ? String(s).slice(0, 10) : '—')
export const fmtTime = (s) => (s ? String(s).slice(0, 16).replace('T', ' ') : '—')

// ── 数字卡 ──
export function StatCard({ label, value, hint, accent = '#de5e39' }) {
  return (
    <div className="pf-stat">
      <div className="pf-stat__val" style={{ color: accent }}>{fmtNum(value)}</div>
      <div className="pf-stat__lbl">{label}</div>
      {hint != null && <div className="pf-stat__hint">{hint}</div>}
    </div>
  )
}

// ── 横向分布条（学科/评分/标签命中/教师评分等长标签） ──
export function BarsH({ data = [], accent = '#de5e39', unit = '', max: maxProp }) {
  if (!data.length) return <div className="pf-empty">暂无数据</div>
  const max = maxProp || Math.max(...data.map(d => d.value || 0), 1)
  return (
    <div className="pf-barsh">
      {data.map((d, i) => (
        <div className="pf-barsh__row" key={d.label + i}>
          <span className="pf-barsh__lbl" title={d.label}>{d.label}</span>
          <span className="pf-barsh__track">
            <span className="pf-barsh__fill"
              style={{ width: `${Math.max((d.value / max) * 100, 1.5)}%`, background: accent }} />
          </span>
          <span className="pf-barsh__val">{fmtNum(d.value)}{unit}</span>
        </div>
      ))}
    </div>
  )
}

// ── 环形占比 ──
export function DonutChart({ data = [], size = 140, thickness = 18 }) {
  const total = data.reduce((s, d) => s + (d.value || 0), 0)
  if (!total) return <div className="pf-empty">暂无数据</div>
  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  let acc = 0
  return (
    <div className="pf-donut">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
          {data.map((d, i) => {
            const frac = (d.value || 0) / total
            const seg = c * frac
            const el = (
              <circle key={i} cx={size / 2} cy={size / 2} r={r}
                fill="none" stroke={PALETTE[i % PALETTE.length]} strokeWidth={thickness}
                strokeDasharray={`${seg} ${c - seg}`} strokeDashoffset={-acc} />
            )
            acc += seg
            return el
          })}
        </g>
        <text x="50%" y="48%" textAnchor="middle" className="pf-donut__total">{fmtNum(total)}</text>
        <text x="50%" y="62%" textAnchor="middle" className="pf-donut__cap">合计</text>
      </svg>
      <ul className="pf-legend">
        {data.map((d, i) => (
          <li key={i}>
            <span className="pf-legend__dot" style={{ background: PALETTE[i % PALETTE.length] }} />
            {d.label} <b>{fmtNum(d.value)}</b>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── 时间序列折线（活跃/趋势） ──
export function LineChart({ data = [], accent = '#de5e39', height = 120 }) {
  if (data.length < 2) return <div className="pf-empty">数据点不足</div>
  const W = 600, H = height, pad = 8
  const max = Math.max(...data.map(d => d.value || 0), 1)
  const stepX = (W - pad * 2) / (data.length - 1)
  const pts = data.map((d, i) => {
    const x = pad + i * stepX
    const y = H - pad - ((d.value || 0) / max) * (H - pad * 2)
    return [x, y]
  })
  const line = pts.map(p => p.join(',')).join(' ')
  const area = `${pad},${H - pad} ${line} ${W - pad},${H - pad}`
  return (
    <div className="pf-line">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={H}>
        <polygon points={area} fill={accent} opacity="0.08" />
        <polyline points={line} fill="none" stroke={accent} strokeWidth="2"
          strokeLinejoin="round" strokeLinecap="round" />
        {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="2.4" fill={accent} />)}
      </svg>
      <div className="pf-line__axis">
        <span>{data[0].date}</span>
        <span>峰值 {fmtNum(max)}</span>
        <span>{data[data.length - 1].date}</span>
      </div>
    </div>
  )
}

// ── 六维讲解风格雷达 ── data: [{label, value 0..1}]
export function Radar({ data = [], size = 220, accent = '#de5e39' }) {
  if (!data.length) return <div className="pf-empty">暂无指纹</div>
  const cx = size / 2, cy = size / 2, R = size / 2 - 30
  const n = data.length
  const angle = (i) => (Math.PI * 2 * i) / n - Math.PI / 2
  const pt = (i, frac) => [cx + R * frac * Math.cos(angle(i)), cy + R * frac * Math.sin(angle(i))]
  const poly = data.map((d, i) => pt(i, Math.max(0, Math.min(1, d.value || 0))).join(',')).join(' ')
  const rings = [0.25, 0.5, 0.75, 1]
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="pf-radar">
      {rings.map((f, ri) => (
        <polygon key={ri} fill="none" stroke="#d8cdb9" strokeWidth="1"
          points={data.map((_, i) => pt(i, f).join(',')).join(' ')} />
      ))}
      {data.map((_, i) => {
        const [x, y] = pt(i, 1)
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#e3dacb" strokeWidth="1" />
      })}
      <polygon points={poly} fill={accent} fillOpacity="0.22" stroke={accent} strokeWidth="2" />
      {data.map((d, i) => {
        const [x, y] = pt(i, 1.18)
        return (
          <text key={i} x={x} y={y} textAnchor="middle" dominantBaseline="middle"
            className="pf-radar__lbl">{d.label}</text>
        )
      })}
    </svg>
  )
}

// ── 标签云 ── data: [{label, value}]
export function TagCloud({ data = [], accent = '#3e6d8e' }) {
  if (!data.length) return <div className="pf-empty">暂无标签</div>
  const max = Math.max(...data.map(d => d.value || 0), 1)
  const min = Math.min(...data.map(d => d.value || 0))
  return (
    <div className="pf-cloud">
      {data.map((d, i) => {
        const t = max === min ? 0.5 : (d.value - min) / (max - min)
        const fs = 12 + t * 12
        return (
          <span key={i} className="pf-cloud__tag"
            style={{ fontSize: fs, color: accent, opacity: 0.55 + t * 0.45 }}
            title={`${d.value} 次`}>{d.label}</span>
        )
      })}
    </div>
  )
}

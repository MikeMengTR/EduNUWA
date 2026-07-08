// 平台监控台共享 UI 小件：数据获取 hook + 区块/抽屉/加载态。
import React, { useState, useEffect } from 'react'
import Icon from '../../components/Icon'

// 极简数据获取 hook：组件挂载/依赖变化时拉取，含 loading/error 与卸载保护。
// 返回 reload()：写操作成功后调用即可重拉当前数据。
export function useFetch(fn, deps = []) {
  const [tick, setTick] = useState(0)
  const [state, setState] = useState({ data: null, loading: true, error: null })
  useEffect(() => {
    let alive = true
    setState(s => ({ ...s, loading: true, error: null }))
    Promise.resolve().then(fn)
      .then(d => { if (alive) setState({ data: d, loading: false, error: null }) })
      .catch(e => { if (alive) setState({ data: null, loading: false, error: e.message || '加载失败' }) })
    return () => { alive = false }
  }, [...deps, tick]) // eslint-disable-line react-hooks/exhaustive-deps
  return { ...state, reload: () => setTick(t => t + 1) }
}

// 危险操作统一走二次确认 → 执行 → 成功回调；失败弹出错误。
export async function confirmRun(message, action, onDone) {
  if (!window.confirm(message)) return
  try { await action(); if (onDone) onDone() }
  catch (e) { alert(e.message || '操作失败') }
}

// 小号操作按钮（表格行 / 卡片内）。
export function ActionBtn({ children, onClick, danger, title }) {
  return (
    <button type="button" className={`pf-act ${danger ? 'pf-act--danger' : ''}`}
      title={title} onClick={(e) => { e.stopPropagation(); onClick(e) }}>
      {children}
    </button>
  )
}

export function Loader({ text = '加载中…' }) {
  return <div className="pf-loader"><Icon name="spinner" size={18} className="pf-spin" /> {text}</div>
}

export function ErrorBox({ error }) {
  return <div className="pf-error"><Icon name="x" size={16} /> {String(error)}</div>
}

// 卡片区块
export function Section({ title, desc, right, children, className = '' }) {
  return (
    <section className={`pf-section ${className}`}>
      {(title || right) && (
        <header className="pf-section__head">
          <div>
            {title && <h3 className="pf-section__title">{title}</h3>}
            {desc && <p className="pf-section__desc">{desc}</p>}
          </div>
          {right}
        </header>
      )}
      {children}
    </section>
  )
}

// 右侧滑出抽屉（下钻明细）
export function Drawer({ open, onClose, title, subtitle, children }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    if (open) window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open) return null
  return (
    <div className="pf-drawer__mask" onClick={onClose}>
      <aside className="pf-drawer" onClick={e => e.stopPropagation()}>
        <header className="pf-drawer__head">
          <div>
            <h3>{title}</h3>
            {subtitle && <p className="pf-drawer__sub">{subtitle}</p>}
          </div>
          <button className="pf-iconbtn" onClick={onClose} aria-label="关闭"><Icon name="x" size={18} /></button>
        </header>
        <div className="pf-drawer__body">{children}</div>
      </aside>
    </div>
  )
}

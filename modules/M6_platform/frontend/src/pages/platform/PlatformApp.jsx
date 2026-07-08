// 平台监控台外壳：独立口令守卫 + 侧边栏布局 + 子路由。
// 与师生端账号体系隔离——只认 localStorage.platform_key（X-Platform-Key 头）。
import React, { useState } from 'react'
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'
import Icon from '../../components/Icon'
import { platformAuth } from '../../api'
import './platform.css'

import Overview from './Overview'
import Users from './Users'
import Teachers from './Teachers'
import Sessions from './Sessions'
import Feedback from './Feedback'
import Matches from './Matches'
import Media from './Media'

const NAV = [
  { to: '/platform', end: true, icon: 'home', label: '总览' },
  { to: '/platform/users', icon: 'user', label: '用户 · 学生' },
  { to: '/platform/teachers', icon: 'cap', label: '教师' },
  { to: '/platform/sessions', icon: 'message', label: '课堂' },
  { to: '/platform/feedback', icon: 'star', label: '反馈评价' },
  { to: '/platform/matches', icon: 'sparkles', label: '推荐匹配' },
  { to: '/platform/media', icon: 'layers', label: '内容图库' },
]

function Gate({ onPass }) {
  const [key, setKey] = useState('')
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const submit = async (e) => {
    e.preventDefault()
    setErr(''); setLoading(true)
    try {
      await platformAuth(key.trim())
      localStorage.setItem('platform_key', key.trim())
      onPass()
    } catch (e2) {
      setErr(e2.message || '口令无效')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="pf-gate">
      <form className="pf-gate__card" onSubmit={submit}>
        <div className="pf-gate__brand"><Icon name="settings" size={22} /> 平台监控台</div>
        <h2>请输入访问口令</h2>
        <p className="pf-gate__hint">仅供运营 / 课题方查看全平台数据，与师生账号无关。</p>
        {err && <div className="pf-error"><Icon name="x" size={14} /> {err}</div>}
        <input className="pf-gate__input" type="password" value={key} autoFocus
          onChange={e => setKey(e.target.value)} placeholder="平台口令" />
        <button className="pf-gate__btn" type="submit" disabled={loading || !key.trim()}>
          {loading ? '校验中…' : '进入监控台'}
        </button>
        <button type="button" className="pf-gate__back" onClick={() => navigate('/login')}>
          ← 返回登录
        </button>
      </form>
    </div>
  )
}

export default function PlatformApp() {
  const [authed, setAuthed] = useState(!!localStorage.getItem('platform_key'))
  const navigate = useNavigate()

  if (!authed) return <Gate onPass={() => setAuthed(true)} />

  const logout = () => {
    localStorage.removeItem('platform_key')
    setAuthed(false)
    navigate('/login')
  }

  return (
    <div className="pf-shell">
      <aside className="pf-side">
        <div className="pf-side__brand">
          <span className="pf-side__mark"><Icon name="settings" size={18} /></span>
          <span className="pf-side__name">MIND · 监控台</span>
        </div>
        <nav className="pf-nav">
          {NAV.map(n => (
            <NavLink key={n.to} to={n.to} end={n.end}
              className={({ isActive }) => `pf-nav__item ${isActive ? 'on' : ''}`}>
              <Icon name={n.icon} size={18} /> <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <button className="pf-side__logout" onClick={logout}>
          <Icon name="logout" size={17} /> 退出监控台
        </button>
      </aside>

      <main className="pf-main">
        <Routes>
          <Route index element={<Overview />} />
          <Route path="users" element={<Users />} />
          <Route path="teachers" element={<Teachers />} />
          <Route path="sessions" element={<Sessions />} />
          <Route path="feedback" element={<Feedback />} />
          <Route path="matches" element={<Matches />} />
          <Route path="media" element={<Media />} />
        </Routes>
      </main>
    </div>
  )
}

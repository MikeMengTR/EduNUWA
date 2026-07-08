import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import Icon from './Icon'
import TeacherSearch from './TeacherSearch'

export default function Navbar({ user, onLogout }) {
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const userRef = useRef(null)

  // 点击菜单外部时收起下拉
  useEffect(() => {
    if (!menuOpen) return
    const onDoc = (e) => { if (userRef.current && !userRef.current.contains(e.target)) setMenuOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [menuOpen])

  const handleLogout = () => {
    setMenuOpen(false)
    onLogout?.()       // 清空 App 登录态 + 移除 token
    navigate('/login')
  }

  // 学生点 logo 回到「上次使用的老师」的课堂；无记录则进发现页
  const goHome = () => {
    if (user.role === 'teacher') return navigate('/teacher')
    const last = localStorage.getItem('lastTeacherId')
    navigate(last ? `/classroom/${last}` : '/student')
  }

  if (!user) return null

  return (
    <nav className="navbar">
      <div className="nav-brand" onClick={goHome}>
        <div className="nav-mark"><img src="/logo.svg" alt="EduTwin" /></div>
        <span className="nav-wordmark">MIND <span className="dim">|</span> EduTwin</span>
      </div>

      <div className="nav-right">
        {user.role === 'teacher' ? (
          <>
            <button className="nav-link" onClick={() => navigate('/teacher')}>
              <Icon name="book" size={17} /> 教师主页
            </button>
            <button className="nav-link" onClick={() => navigate('/teacher/upload')}>
              <Icon name="upload" size={17} /> 上传素材
            </button>
            <button className="nav-link" onClick={() => navigate('/teacher/courses')}>
              <Icon name="layers" size={17} /> 课堂预录制
            </button>
          </>
        ) : (
          <TeacherSearch />
        )}

        <div className="nav-user" ref={userRef}>
          {/* 头像 + 信息：点击展开下拉（设置 / 账号退出） */}
          <button
            className="nav-user-trigger"
            onClick={() => setMenuOpen((o) => !o)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <div className="nav-avatar">{user.username?.charAt(0)?.toUpperCase() || 'U'}</div>
            <div className="nav-userinfo">
              <span className="nav-username">{user.username}</span>
              <span className="nav-role">
                <span className={`nav-role-dot ${user.role}`} />
                {user.role === 'teacher' ? '教师' : '学生'}
              </span>
            </div>
            <Icon name="chevronDown" size={15} className={`nav-caret ${menuOpen ? 'open' : ''}`} />
          </button>

          {menuOpen && (
            <div className="nav-menu" role="menu">
              {/* 设置：占位空按钮，暂不跳转 */}
              <button className="nav-menu-item" role="menuitem" onClick={() => setMenuOpen(false)}>
                <Icon name="settings" size={16} /> 设置
              </button>
              <button className="nav-menu-item" role="menuitem" onClick={handleLogout}>
                <Icon name="logout" size={16} /> 账号退出
              </button>
            </div>
          )}

          {/* 原退出键改为：返回「选老师」发现页（仅学生） */}
          {user.role === 'student' && (
            <button
              className="nav-home"
              onClick={() => { setMenuOpen(false); navigate('/student') }}
              title="返回选老师"
              aria-label="返回选老师"
            >
              <Icon name="home" size={17} />
            </button>
          )}
        </div>
      </div>
    </nav>
  )
}

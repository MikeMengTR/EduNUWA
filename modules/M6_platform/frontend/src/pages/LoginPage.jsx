import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, register, platformAuth } from '../api'
import Icon from '../components/Icon'
import './LoginPage.css'

// 时段问候，给面板一点人味
function greeting() {
  const h = new Date().getHours()
  return h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好'
}

const LockSvg = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <rect x="4" y="10" width="16" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" />
  </svg>
)
const EyeSvg = ({ off }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    {off
      ? <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /><path d="M3 3l18 18" /></>
      : <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></>}
  </svg>
)

export default function LoginPage({ onLogin }) {
  const [mode, setMode] = useState('login')
  const [role, setRole] = useState('student')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [loading, setLoading] = useState(false)
  // 平台监控台入口（右下角低调挂载，独立口令）
  const [pfOpen, setPfOpen] = useState(false)
  const [pfKey, setPfKey] = useState('')
  const [pfErr, setPfErr] = useState('')
  const [pfLoading, setPfLoading] = useState(false)
  const navigate = useNavigate()
  const leftRef = useRef(null)
  const stageRef = useRef(null)

  const pfSubmit = async (e) => {
    e.preventDefault()
    setPfErr(''); setPfLoading(true)
    try {
      await platformAuth(pfKey.trim())
      localStorage.setItem('platform_key', pfKey.trim())
      navigate('/platform')
    } catch (err) {
      setPfErr(err.message || '口令无效')
    } finally {
      setPfLoading(false)
    }
  }

  // 光标视差：整片"讲义星系"跟随鼠标轻移，营造空间景深
  useEffect(() => {
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const left = leftRef.current, stage = stageRef.current
    if (reduce || !left || !stage) return
    let tx = 0, ty = 0, x = 0, y = 0, raf
    const onMove = (e) => {
      const r = left.getBoundingClientRect()
      tx = ((e.clientX - r.left) / r.width - 0.5) * -26
      ty = ((e.clientY - r.top) / r.height - 0.5) * -26
    }
    const onLeave = () => { tx = 0; ty = 0 }
    const loop = () => {
      x += (tx - x) * 0.06; y += (ty - y) * 0.06
      stage.style.transform = `translate(${x.toFixed(2)}px,${y.toFixed(2)}px)`
      raf = requestAnimationFrame(loop)
    }
    left.addEventListener('mousemove', onMove)
    left.addEventListener('mouseleave', onLeave)
    loop()
    return () => {
      left.removeEventListener('mousemove', onMove)
      left.removeEventListener('mouseleave', onLeave)
      cancelAnimationFrame(raf)
    }
  }, [])

  const switchMode = (m) => { setMode(m); setError(''); setNotice('') }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(''); setNotice('')
    if (!username.trim() || !password.trim()) {
      setError('请填写用户名和密码')
      return
    }
    setLoading(true)
    try {
      if (mode === 'login') {
        const data = await login(username, password)
        localStorage.setItem('token', data.token)
        onLogin(data.user)
        if (data.user.role === 'teacher') {
          navigate('/teacher')
        } else {
          // 学生回到上次使用的老师的课堂；无记录则进发现页
          const last = localStorage.getItem('lastTeacherId')
          navigate(last ? `/classroom/${last}` : '/student')
        }
      } else {
        await register(username, password, role)
        setMode('login')
        setNotice('注册成功，请登录')
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const isReg = mode === 'register'
  const brand = (cls) => <span className={cls}>MIND <span className="elogin__pipe">|</span> EduTwin</span>

  return (
    <div className="elogin">
      {/* —— 左：会动的讲义星系 —— */}
      <div className="elogin__left" ref={leftRef}>
        <div className="elogin__stage" ref={stageRef}>
          <div className="elogin__glow" />
          <div className="elogin__glow elogin__glow--cool" />
          <svg className="elogin__field" viewBox="0 0 1300 1000" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
            <g className="elogin__orbit elogin__orbit--1">
              <circle className="elogin__ring" cx="780" cy="460" r="190" />
              <circle className="elogin__node elogin__node--hot" cx="780" cy="270" r="4.5" />
            </g>
            <g className="elogin__orbit elogin__orbit--2">
              <circle className="elogin__ring" cx="780" cy="460" r="330" />
              <circle className="elogin__node" cx="780" cy="130" r="3.5" />
              <circle className="elogin__node elogin__node--brass" cx="1110" cy="460" r="3" />
            </g>
            <g className="elogin__orbit elogin__orbit--3">
              <circle className="elogin__ring" cx="780" cy="460" r="480" />
              <circle className="elogin__node" cx="300" cy="460" r="3" />
            </g>
            <g className="elogin__orbit elogin__orbit--4">
              <circle className="elogin__ring" cx="780" cy="460" r="640" />
              <circle className="elogin__node elogin__node--hot" cx="780" cy="-180" r="3.5" />
              <circle className="elogin__node" cx="140" cy="460" r="2.5" />
            </g>
          </svg>
          <span className="elogin__spark" style={{ left: '56%', top: '60%', animationDuration: '8s', animationDelay: '0s' }} />
          <span className="elogin__spark" style={{ left: '62%', top: '66%', animationDuration: '10s', animationDelay: '-3s' }} />
          <span className="elogin__spark" style={{ left: '53%', top: '70%', animationDuration: '9s', animationDelay: '-5.5s' }} />
          <span className="elogin__spark" style={{ left: '67%', top: '62%', animationDuration: '11s', animationDelay: '-7s' }} />
        </div>

        <div className="elogin__left-in">
          <div className="elogin__logo elogin__rv" style={{ animationDelay: '.1s' }}>
            <span className="elogin__mk"><img src="/logo.svg" alt="MIND EduTwin" /></span>
            {brand('elogin__wm')}
          </div>

          <h1 className="elogin__headline">
            <span className="elogin__ln elogin__rv" style={{ animationDelay: '.35s' }}>把教师的</span>
            <span className="elogin__ln elogin__rv" style={{ animationDelay: '.5s' }}>教学能力，</span>
            <span className="elogin__ln elogin__rv" style={{ animationDelay: '.65s' }}>
              <span className="elogin__ignite">蒸馏</span>为数字资产<span className="elogin__dot">。</span>
            </span>
          </h1>

          <p className="elogin__sub elogin__rv" style={{ animationDelay: '.95s' }}>
            一条数据契约驱动的流水线，将名师的讲解风格凝练成可复用的数字讲义——学生随时随地，听同一位老师，用他的方式上课。
          </p>

          <div className="elogin__feats">
            <div className="elogin__feat elogin__rv" style={{ animationDelay: '1.15s' }}>
              <Icon name="flask" size={19} /><span><b>风格蒸馏</b> <span className="elogin__m">· 把讲课方式提炼为 Skill</span></span>
            </div>
            <div className="elogin__feat elogin__rv" style={{ animationDelay: '1.28s' }}>
              <Icon name="cap" size={19} /><span><b>虚拟课堂</b> <span className="elogin__m">· 数字人 + 黑板 + 语音讲解</span></span>
            </div>
            <div className="elogin__feat elogin__rv" style={{ animationDelay: '1.41s' }}>
              <Icon name="sparkles" size={19} /><span><b>智能匹配</b> <span className="elogin__m">· 按你想要的风格找老师</span></span>
            </div>
          </div>
        </div>

        <div className="elogin__foot elogin__rv" style={{ animationDelay: '1.6s' }}>MIND · EDUTWIN PLATFORM · V2</div>
      </div>

      {/* —— 右：登录 / 注册面板（更满） —— */}
      <div className="elogin__right">
        <form className="elogin__r-in" onSubmit={handleSubmit}>
          <div className="elogin__kicker elogin__rs" style={{ animationDelay: '.45s' }}>
            <span className="elogin__kicker-fl">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2c1.5 3.5-1 5 .5 8 1-1 1.5-2.5 1-4 2 1.5 3.5 4 3.5 7a6 6 0 1 1-12 0c0-2 1-3.8 2.5-5 0 1.5.5 2.5 1.5 3-.8-2.2.5-4.5 3.5-6z" /></svg>
            </span>
            MIND · EDUTWIN
          </div>
          <div className="elogin__greet elogin__rs" style={{ animationDelay: '.55s' }}>{greeting()}</div>
          <h2 className="elogin__rs" style={{ animationDelay: '.6s' }}>{isReg ? '创建账号' : '欢迎回来'}</h2>
          <p className="elogin__hint elogin__rs" style={{ animationDelay: '.68s' }}>
            {isReg ? '加入 MIND，开启你的数字课堂' : '登录以进入你的讲义馆'}
          </p>

          <div className={`elogin__tabs elogin__rs ${isReg ? 'reg' : ''}`} style={{ animationDelay: '.78s' }}>
            <span className="elogin__pill" />
            <button type="button" className={`elogin__tab ${!isReg ? 'on' : ''}`} onClick={() => switchMode('login')}>登录</button>
            <button type="button" className={`elogin__tab ${isReg ? 'on' : ''}`} onClick={() => switchMode('register')}>注册</button>
          </div>

          {error && <div className="elogin__msg elogin__msg--err"><Icon name="x" size={14} /> {error}</div>}
          {notice && <div className="elogin__msg elogin__msg--ok"><Icon name="check" size={14} /> {notice}</div>}

          {isReg && (
            <div className="elogin__roles elogin__rs" style={{ animationDelay: '.84s' }}>
              <button type="button" className={`elogin__role ${role === 'student' ? 'on' : ''}`} onClick={() => setRole('student')}>
                <Icon name="book" size={20} />
                <span className="elogin__role-n">我是学生</span>
                <span className="elogin__role-d">发现并向名师学习</span>
                {role === 'student' && <span className="elogin__role-ck"><Icon name="check" size={13} /></span>}
              </button>
              <button type="button" className={`elogin__role ${role === 'teacher' ? 'on' : ''}`} onClick={() => setRole('teacher')}>
                <Icon name="flask" size={20} />
                <span className="elogin__role-n">我是教师</span>
                <span className="elogin__role-d">蒸馏并发布我的风格</span>
                {role === 'teacher' && <span className="elogin__role-ck"><Icon name="check" size={13} /></span>}
              </button>
            </div>
          )}

          <div className="elogin__ff elogin__rs" style={{ animationDelay: '.9s' }}>
            <span className="elogin__ic"><Icon name="user" size={18} /></span>
            <input id="el-user" value={username} onChange={e => setUsername(e.target.value)} placeholder=" " autoComplete="username" />
            <label htmlFor="el-user">用户名</label>
          </div>
          <div className="elogin__ff elogin__rs" style={{ animationDelay: '.99s' }}>
            <span className="elogin__ic"><LockSvg /></span>
            <input id="el-pw" type={showPw ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} placeholder=" " autoComplete={isReg ? 'new-password' : 'current-password'} />
            <label htmlFor="el-pw">密码</label>
            <button type="button" className="elogin__eye" onClick={() => setShowPw(s => !s)} aria-label={showPw ? '隐藏密码' : '显示密码'}>
              <EyeSvg off={showPw} />
            </button>
          </div>

          {!isReg && (
            <div className="elogin__opts elogin__rs" style={{ animationDelay: '1.05s' }}>
              <label className="elogin__cb">
                <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} />
                <span className="elogin__box"><Icon name="check" size={11} /></span>
                记住我
              </label>
              <a className="elogin__forgot" onClick={() => setNotice('如忘记密码，请联系平台管理员重置')}>忘记密码？</a>
            </div>
          )}

          <button className="elogin__submit elogin__rs" style={{ animationDelay: isReg ? '1.05s' : '1.13s' }} type="submit" disabled={loading}>
            <span>{loading ? '处理中…' : isReg ? '创建账号' : '登录'}</span>
            {!loading && <span className="elogin__ar"><Icon name="arrowRight" size={17} /></span>}
          </button>

          <p className="elogin__alt elogin__rs" style={{ animationDelay: '1.2s' }}>
            {isReg ? '已有账号？' : '还没有账号？'}
            <a onClick={() => switchMode(isReg ? 'login' : 'register')}>{isReg ? '去登录' : '去注册'}</a>
          </p>

          <div className="elogin__strip elogin__rs" style={{ animationDelay: '1.3s' }}>
            <span className="elogin__live" />名师的数字分身 · 随时在线开课
          </div>
        </form>
      </div>

      {/* —— 右下角：平台监控台入口（低调，不入布局流） —— */}
      <button className="elogin__pf" onClick={() => { setPfErr(''); setPfOpen(true) }} title="平台监控台">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="3.1" /><path d="M19.4 15a1.6 1.6 0 0 0 .32 1.77l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.6 1.6 0 0 0-2.73 1.13V21a2 2 0 0 1-4 0v-.09A1.6 1.6 0 0 0 7.43 19.4l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.6 1.6 0 0 0 3 13.6H3a2 2 0 0 1 0-4h.09A1.6 1.6 0 0 0 4.6 7.43l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.6 1.6 0 0 0 10 4.6V3a2 2 0 0 1 4 0v.09a1.6 1.6 0 0 0 2.73 1.13l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.6 1.6 0 0 0 21 9.4V10a2 2 0 0 1 0 4h-.09a1.6 1.6 0 0 0-1.51 1z" />
        </svg>
        平台监控台
      </button>

      {pfOpen && (
        <div className="elogin__pf-mask" onClick={() => setPfOpen(false)}>
          <form className="elogin__pf-card" onClick={e => e.stopPropagation()} onSubmit={pfSubmit}>
            <div className="elogin__pf-title">平台监控台 · 访问口令</div>
            <p className="elogin__pf-hint">仅供运营 / 课题方查看全平台只读数据</p>
            {pfErr && <div className="elogin__pf-err">{pfErr}</div>}
            <input className="elogin__pf-input" type="password" value={pfKey} autoFocus
              onChange={e => setPfKey(e.target.value)} placeholder="输入平台口令" />
            <div className="elogin__pf-actions">
              <button type="button" className="elogin__pf-cancel" onClick={() => setPfOpen(false)}>取消</button>
              <button type="submit" className="elogin__pf-go" disabled={pfLoading || !pfKey.trim()}>
                {pfLoading ? '校验中…' : '进入'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

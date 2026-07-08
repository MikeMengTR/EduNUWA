import Icon from './Icon'
import './TeacherCard.css'

// 学科 → 身份色 class（供 /student 增强层 student-enhance.css 上色：脊柱/头像环/学科名）
function discClass(subject = '') {
  const s = subject || ''
  if (/数学|概率|线代|线性代数|离散|微积分|复变/.test(s)) return 'disc-math'
  if (/机器学习|计算机|数据结构|程序|算法|人工智能|软件|编程/.test(s)) return 'disc-cs'
  if (/物理/.test(s)) return 'disc-physics'
  if (/哲学|思想|思政|马克思|道德|法治|政治/.test(s)) return 'disc-philo'
  if (/生物|植物|动物|生命/.test(s)) return 'disc-bio'
  if (/经济|管理|金融|会计|商科/.test(s)) return 'disc-econ'
  if (/艺术|园林|设计|美术|音乐|历史|文学/.test(s)) return 'disc-art'
  if (/食品|食/.test(s)) return 'disc-food'
  return ''
}

export default function TeacherCard({ teacher, onChat, onWatchVideo, onDetail }) {
  // 拆标题：姓名独占焦点，学科·大学降为等宽小字
  const name = teacher.real_name || String(teacher.display_name || '').split(/[-－·•]/)[0].trim() || '老师'
  const school = teacher.school || ''
  // 学科去重：个别老师无 real_name 时姓名会被解析成学科，避免元信息里重复
  const subject = teacher.subject && teacher.subject !== name ? teacher.subject : ''
  const initial = name.charAt(0) || '师'

  // 一句话风格简介：优先真实简介；否则取前 3 个风格标签拼成（首词加重、中文不用斜体）。
  // 注意：不用 description——它存的是"学科_学校"类原始元数据，非真正简介。tags 才是蒸馏出的风格。
  const bio = (teacher.bio || '').trim()
  const styleTags = (teacher.tags || [])
    .map(t => (typeof t === 'string' ? t : t?.text || '').trim())
    .filter(s => s && !s.includes('_') && s !== school && s !== teacher.subject)
    .slice(0, 3)

  return (
    <article className={`tcard ${discClass(teacher.subject)}`} onClick={() => onDetail?.()}>
      <div className="tcard__head">
        {teacher.avatar?.pixel_url ? (
          <img className="tcard__avatar" src={teacher.avatar.pixel_url} alt={name} />
        ) : (
          <div className="tcard__avatar tcard__avatar--fallback">{initial}</div>
        )}
        <div className="tcard__id">
          <h3 className="tcard__name">{name}</h3>
          {(subject || school) && (
            <div className="tcard__meta">
              {subject && <span className="tcard__meta-subject">{subject}</span>}
              {subject && school && ' · '}
              {school}
            </div>
          )}
        </div>
      </div>

      <p className="tcard__style">
        {bio ? bio : styleTags.length ? (
          <>
            <b>{styleTags[0]}</b>
            {styleTags.length > 1 && `、${styleTags.slice(1).join('、')}`}。
          </>
        ) : 'AI 分身已就绪，走进课堂即可体验其讲解风格。'}
      </p>

      <div className="tcard__foot" onClick={e => e.stopPropagation()}>
        <span className="tcard__twin"><span className="tcard__twin-dot" />AI 分身在线</span>
        <span className="tcard__actions">
          <button className="tcard__course" onClick={onWatchVideo}>课程</button>
          <button className="tcard__enter" onClick={onChat}>走进课堂 <Icon name="arrowRight" size={14} /></button>
        </span>
      </div>
    </article>
  )
}

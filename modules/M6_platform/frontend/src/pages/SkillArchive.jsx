import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMyTeacher, getSkillVersions, getSkillVersion, distillTeacher } from '../api'
import Icon from '../components/Icon'
import './SkillArchive.css'

const FP_LABEL = {
  pace: '节奏感', detail: '细致度', abstraction: '抽象度',
  interactivity: '互动性', humor: '幽默感', rigor: '严谨度',
}
// 这些段落用结构化组件单独展示，不在正文里重复渲染
const WIDGET_SECTIONS = new Set(['Fingerprint', 'Style Tags', '风格指纹', '风格标签'])

function fmtTime(sec) {
  if (sec == null) return ''
  const s = Math.floor(sec % 60), m = Math.floor(sec / 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/* 极简 markdown 渲染：标题/列表/加粗/段落；去掉 ```代码块``` */
function renderInline(text, k) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((p, i) =>
    p.startsWith('**') && p.endsWith('**')
      ? <strong key={`${k}-${i}`}>{p.slice(2, -2)}</strong>
      : <span key={`${k}-${i}`}>{p}</span>)
}

function SkillBody({ text }) {
  const clean = text.replace(/```[\s\S]*?```/g, '').trim()
  const lines = clean.split('\n')
  const out = []
  let bullets = []
  const flush = () => {
    if (bullets.length) {
      out.push(<ul key={`ul-${out.length}`}>{bullets.map((b, i) => <li key={i}>{renderInline(b, `li-${out.length}-${i}`)}</li>)}</ul>)
      bullets = []
    }
  }
  lines.forEach((raw, i) => {
    const line = raw.trim()
    if (!line) { flush(); return }
    if (/^###\s+/.test(line)) { flush(); out.push(<h4 key={`h-${i}`}>{line.replace(/^###\s+/, '')}</h4>) }
    else if (/^[-*]\s+/.test(line)) { bullets.push(line.replace(/^[-*]\s+/, '')) }
    else { flush(); out.push(<p key={`p-${i}`}>{renderInline(line, `p-${i}`)}</p>) }
  })
  flush()
  return <>{out}</>
}

function parseSections(md) {
  if (!md) return { head: '', sections: [] }
  const blocks = md.split(/^##\s+/m)
  const head = blocks[0] || ''
  const sections = blocks.slice(1).map(b => {
    const nl = b.indexOf('\n')
    return { title: (nl === -1 ? b : b.slice(0, nl)).trim(), body: nl === -1 ? '' : b.slice(nl + 1) }
  })
  return { head, sections }
}

export default function SkillArchive() {
  const [teacher, setTeacher] = useState(null)
  const [versions, setVersions] = useState([])
  const [curDir, setCurDir] = useState(null)
  const [data, setData] = useState(null)       // {skill_md, profile}
  const [loading, setLoading] = useState(true)
  const [openTag, setOpenTag] = useState(null)
  const [distilling, setDistilling] = useState(false)
  const [distillMsg, setDistillMsg] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    (async () => {
      try {
        const t = await getMyTeacher()
        setTeacher(t)
        const vs = await getSkillVersions(t.teacher_id).catch(() => [])
        setVersions(vs)
        if (vs.length) loadVersion(t.teacher_id, vs[0].dir)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const loadVersion = async (tid, dir) => {
    setCurDir(dir); setOpenTag(null)
    setData(await getSkillVersion(tid, dir).catch(() => null))
  }

  const handleDistill = async () => {
    if (!teacher || distilling) return
    setDistilling(true); setDistillMsg('')
    try {
      const r = await distillTeacher(teacher.teacher_id)
      setDistillMsg(`已生成新版本 v${r.version}（语料 ${r.corpus_size} 字，${r.files_used} 个文件）`)
      const vs = await getSkillVersions(teacher.teacher_id).catch(() => [])
      setVersions(vs)
      if (vs.length) loadVersion(teacher.teacher_id, vs[0].dir)
    } catch (e) {
      setDistillMsg(`蒸馏失败：${e.message}`)
    } finally {
      setDistilling(false)
    }
  }

  if (loading) return <div className="loading">加载中…</div>
  if (!teacher) {
    return <div className="container"><div className="empty-state">
      <h3>还未创建教师卡片</h3>
      <button className="btn btn--accent btn-sm" onClick={() => navigate('/teacher')}>去工作台</button>
    </div></div>
  }
  if (!versions.length) {
    return <div className="container"><div className="empty-state">
      <h3>还没有蒸馏出 Skill</h3>
      <p>上传教学素材并在工作台点「一键蒸馏」后，这里会展示 AI 提炼出的你的教学风格。</p>
      <button className="btn btn--accent btn-sm" onClick={() => navigate('/teacher')}>去工作台</button>
    </div></div>
  }

  const profile = data?.profile
  const fp = profile?.fingerprint || {}
  const tags = profile?.style_tags || []
  const { head, sections } = parseSections(data?.skill_md)

  return (
    <div className="container skill-archive">
      <div className="page-header">
        <div>
          <h1>Skill 档案</h1>
          <p className="sa-sub">这是 AI 从你的教学转写中提炼出的「教学风格说明书」，讲课、配课、匹配学生都依据它。每条风格标签都可点开看支撑证据。</p>
        </div>
        <button className="btn btn-sm btn--ghost" onClick={() => navigate('/teacher')}>
          <Icon name="chevronLeft" size={15} /> 返回工作台
        </button>
      </div>

      {/* 版本切换 + 蒸馏新版本 */}
      <div className="sa-versions">
        <div className="sa-versions__list">
          {versions.map(v => (
            <button key={v.dir} className={`sa-ver ${curDir === v.dir ? 'on' : ''}`}
              onClick={() => loadVersion(teacher.teacher_id, v.dir)}>
              v{v.version}{v.dir.includes('full') ? ' · full' : ''}
              {v.generated_at && <span className="sa-ver__date">{new Date(v.generated_at).toLocaleDateString()}</span>}
            </button>
          ))}
        </div>
        <button className="sa-distill" disabled={distilling} onClick={handleDistill}
          title="基于当前全部转写素材重新蒸馏，生成一个新版本（不影响旧版本）">
          {distilling
            ? <><Icon name="spinner" size={14} className="spin" /> 蒸馏中…</>
            : <><Icon name="plus" size={14} /> 蒸馏新的 Skill</>}
        </button>
      </div>
      {distillMsg && <div className={`sa-distill-msg ${distillMsg.includes('失败') ? 'err' : 'ok'}`}>{distillMsg}</div>}

      {!data ? <div className="loading">加载中…</div> : (
        <>
          {/* 指纹 */}
          {Object.keys(fp).length > 0 && (
            <section className="sa-card">
              <h3 className="sa-card__title">风格指纹</h3>
              <div className="sa-fp">
                {Object.entries(fp).map(([k, v]) => {
                  const val = typeof v === 'object' ? (v.value ?? 0) : v
                  return (
                    <div key={k} className="sa-fp__row">
                      <span className="sa-fp__k">{FP_LABEL[k] || k}</span>
                      <div className="sa-fp__bar"><div className="sa-fp__fill" style={{ width: `${Math.round(val * 100)}%` }} /></div>
                      <span className="sa-fp__v">{Number(val).toFixed(1)}</span>
                    </div>
                  )
                })}
              </div>
            </section>
          )}

          {/* 风格标签 + 证据回链 */}
          {tags.length > 0 && (
            <section className="sa-card">
              <h3 className="sa-card__title">风格标签</h3>
              <p className="sa-card__sub">AI 给你打的标签。点标签看它是根据哪几句话总结出来的。</p>
              <div className="sa-tags">
                {tags.map((t, i) => (
                  <button key={i} className={`sa-tag ${openTag === i ? 'on' : ''}`} onClick={() => setOpenTag(openTag === i ? null : i)}>
                    {t.text}
                    {t.confidence != null && <span className="sa-tag__conf">{Math.round(t.confidence * 100)}%</span>}
                  </button>
                ))}
              </div>
              {openTag != null && tags[openTag] && (
                <div className="sa-evidence">
                  <div className="sa-evidence__h">「{tags[openTag].text}」的依据：</div>
                  {(tags[openTag].evidence_text || []).length ? (
                    tags[openTag].evidence_text.map((e, j) => (
                      <div key={j} className="sa-ev">
                        <span className="sa-ev__loc">{e.transcript_id} · {fmtTime(e.start)}</span>
                        <span className="sa-ev__txt">{e.text}</span>
                      </div>
                    ))
                  ) : (
                    <div className="sa-ev__none">原始转写已变更，暂无法定位证据句（标签 evidence: {(tags[openTag].evidence || []).join(', ') || '无'}）</div>
                  )}
                </div>
              )}
            </section>
          )}

          {/* TeacherSkill.md 七段正文 */}
          <section className="sa-card sa-md">
            <h3 className="sa-card__title">教学风格说明书（TeacherSkill.md）</h3>
            {head && <div className="sa-md__head"><SkillBody text={head.replace(/^#\s+.*$/m, '').trim()} /></div>}
            {sections.filter(s => !WIDGET_SECTIONS.has(s.title)).map((s, i) => (
              <div key={i} className="sa-section">
                <h3>{s.title}</h3>
                <SkillBody text={s.body} />
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  )
}

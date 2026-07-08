import { useState, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import {
  getTeacherSkill, getTeacherTranscripts, createTeacherCard, updateTeacherCard,
  getMyTeacher, getDistillStatus, distillTeacher, getFeedback,
  getMaterials, getVoiceStatus, listCourses,
  getEvolutionStatus, triggerEvolutionRefresh, triggerRevision,
  getRevision, confirmRevision, rejectRevision, uploadTeacherAvatar,
} from '../api'
import Icon from '../components/Icon'
import { deriveStyle, StyleSketchCard, TeachingStyleCard, StudentReviewsCard } from '../components/StyleProfile'
import './TeacherDashboard.css'

/* 分区小标题 */
const Eyebrow = ({ children, hint }) => (
  <div className="tdash-eyebrow">
    <span className="tdash-eyebrow__t">{children}</span>
    <span className="tdash-eyebrow__rule" />
    {hint && <span className="tdash-eyebrow__hint">{hint}</span>}
  </div>
)

/* 统一能力磁贴：图标 + 标题 + 状态药丸 + 一句话 + 一个动作 */
function CapTile({ icon, accent, title, status, meta, children }) {
  return (
    <article className="cap-tile">
      <div className="cap-tile__top">
        <span className={`cap-tile__icon ${accent}`}><Icon name={icon} size={20} /></span>
        {status && <span className={`cap-pill ${status.tone || 'off'}`}>{status.label}</span>}
      </div>
      <h3 className="cap-tile__title">{title}</h3>
      <p className="cap-tile__meta">{meta}</p>
      <div className="cap-tile__foot">{children}</div>
    </article>
  )
}

/* Skill 自进化卡片：学生反馈 → 众评标签 → skill 修订（教师确认制） */
function EvolutionCard({ teacherId, onSkillUpdated, feedback }) {
  const [status, setStatus] = useState(null)
  const [revision, setRevision] = useState(null)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')

  const reload = async () => {
    const s = await getEvolutionStatus(teacherId).catch(() => null)
    setStatus(s)
    if (s?.has_pending_revision) {
      setRevision(await getRevision(teacherId).catch(() => null))
    } else {
      setRevision(null)
    }
  }
  useEffect(() => { reload() }, [teacherId])

  const run = async (label, fn, okMsg) => {
    setBusy(label); setMsg('')
    try {
      await fn()
      setMsg(okMsg)
      await reload()
      if (label === 'confirm') onSkillUpdated?.()
    } catch (e) {
      setMsg(`操作失败: ${e.message}`)
    } finally {
      setBusy('')
    }
  }

  if (!status) return null
  const liveTags = status.live_tags || []
  // 最新可被用于进化的反馈 = 尚未处理的反馈（按时间倒序取最近 pending_count 条，最多 5 条）
  const pending = (feedback?.feedback || [])
    .slice()
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    .slice(0, Math.min(status.pending_count || 0, 5))

  return (
    <section className="tdash-card evo-card">
      <div className="tdash-card__head">
        <span className="tdash-card__icon flask"><Icon name="refresh" size={22} /></span>
        <div>
          <h3>Skill标签进化</h3>
          <span className={`tdash-badge ${liveTags.length || status.runs_total ? 'on' : 'off'}`}>
            {status.runs_total > 0 ? `已进化 ${status.runs_total} 轮` : '等待反馈'}
          </span>
        </div>
        <div className="evo-card__count">
          <b>{status.pending_count}</b><span>/ {status.threshold} 条新反馈</span>
        </div>
      </div>

      <p className="tdash-card__sub">
        学生评价积累到 {status.threshold} 条会自动分析，提炼众评标签并酝酿 Skill 修订（教师确认才生效）。
        {status.last_run_at && ` 上次进化 ${new Date(status.last_run_at).toLocaleDateString()}。`}
      </p>

      <div className="evo-grid">
        {/* 左：可用于进化的反馈 */}
        <div className="evo-col">
          <div className="evo-col__h">最新可用于进化的反馈{pending.length ? `（${pending.length}）` : ''}</div>
          {pending.length > 0 ? (
            <div className="evo-pending">
              {pending.map((f) => (
                <div key={f.id} className="evo-pending__item">
                  <span className="evo-pending__rate">{'★'.repeat(f.rating || 0)}{'☆'.repeat(5 - (f.rating || 0))}</span>
                  <span className="evo-pending__txt">{f.comment || '（无文字评论）'}</span>
                  <span className="evo-pending__date">{f.created_at ? new Date(f.created_at).toLocaleDateString() : ''}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="evo-empty">暂无待处理反馈。学生在课堂结束后的评价会汇集到这里。</p>
          )}
        </div>

        {/* 右：众评标签 */}
        <div className="evo-col">
          <div className="evo-col__h">学生众评标签{liveTags.length ? `（${liveTags.length}）` : ''}</div>
          {liveTags.length > 0 ? (
            <div className="tags-row">
              {liveTags.map((t, i) => (
                <span key={i} className="tag-chip tag-chip--crowd" title={`来自 ${t.support} 名学生的反馈`}>
                  {t.text}<span className="tag-chip__support">{t.support}</span>
                </span>
              ))}
            </div>
          ) : (
            <p className="evo-empty">还没有从反馈中提炼出众评标签。</p>
          )}
        </div>
      </div>

      {revision && (
        <div className="evo-revision">
          <h4>待确认的 Skill 修订（基于学生反馈）</h4>
          {(revision.change_summary || []).map((c, i) => (
            <div key={i} className="evo-change">
              <div className="evo-change__section">{c.section}
                {c.supported_by_n_students ? <span className="tag-chip__support">{c.supported_by_n_students} 名学生支持</span> : null}
              </div>
              {c.before_excerpt && <div className="evo-change__before">－ {c.before_excerpt}</div>}
              {c.after_excerpt && <div className="evo-change__after">＋ {c.after_excerpt}</div>}
              <div className="evo-change__why">{c.why}</div>
            </div>
          ))}
          <div className="evo-revision__actions">
            <button className="btn btn-sm btn--accent" disabled={!!busy}
              onClick={() => run('confirm', () => confirmRevision(teacherId), '修订已生效为新版本')}>
              {busy === 'confirm' ? '生效中…' : '确认生效'}
            </button>
            <button className="btn btn-sm btn--ghost" disabled={!!busy}
              onClick={() => run('reject', () => rejectRevision(teacherId), '已拒绝该修订')}>
              拒绝
            </button>
          </div>
        </div>
      )}

      {msg && <div className={`tdash-msg ${msg.includes('失败') ? 'err' : 'ok'}`}>{msg}</div>}

      {(status.pending_count > 0 || (status.revision_ready && !status.has_pending_revision)) && (
        <div className="tdash-actions" style={{ marginTop: 14 }}>
          {status.pending_count > 0 && (
            <button className="btn btn-sm btn--ghost" disabled={!!busy}
              onClick={() => run('refresh', () => triggerEvolutionRefresh(teacherId), '标签进化完成')}>
              {busy === 'refresh' ? '分析中…' : '立即分析反馈'}
            </button>
          )}
          {status.revision_ready && !status.has_pending_revision && (
            <button className="btn btn-sm btn--accent" disabled={!!busy}
              onClick={() => run('revise', () => triggerRevision(teacherId), '修订提案已生成，请查看')}>
              {busy === 'revise' ? '生成中…' : '生成 Skill 修订'}
            </button>
          )}
        </div>
      )}
    </section>
  )
}

const SUBJECTS = ['高等数学', '线性代数', '概率论', '大学物理', '程序设计', '机器学习', '大学英语', '思政', '其他']

export default function TeacherDashboard() {
  const [teacher, setTeacher] = useState(null)
  const [skill, setSkill] = useState(null)
  const [transcripts, setTranscripts] = useState([])
  const [distillStatus, setDistillStatus] = useState(null)
  const [feedback, setFeedback] = useState(null)
  const [materials, setMaterials] = useState([])
  const [voiceStatus, setVoiceStatus] = useState(null)
  const [courses, setCourses] = useState([])
  const [tab, setTab] = useState('work')
  const [distilling, setDistilling] = useState(false)
  const [distillMsg, setDistillMsg] = useState('')
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ real_name: '', display_name: '', subject: '', bio: '', system_prompt: '' })
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [avatarUploading, setAvatarUploading] = useState(false)
  const navigate = useNavigate()

  // 上传/更换头像（仅编辑已存在的教师时可用）
  const onPickAvatar = async (e) => {
    const file = e.target.files?.[0]
    if (!file || !teacher) return
    setAvatarUploading(true); setError('')
    try {
      const res = await uploadTeacherAvatar(teacher.teacher_id, file)
      setTeacher(prev => ({ ...prev, avatar: res.avatar, avatar_url: res.avatar_url }))
    } catch (err) {
      setError(err.message)
    } finally {
      setAvatarUploading(false)
      e.target.value = ''  // 允许重复选同一文件
    }
  }

  useEffect(() => {
    (async () => {
      try {
        const t = await getMyTeacher()
        setTeacher(t)
        setForm({
          real_name: t.real_name || '', display_name: t.display_name || '',
          subject: t.subject || '', bio: t.bio || '', system_prompt: t.system_prompt || '',
        })
        const [s, tr, ds, fb, mt, vs, cs] = await Promise.all([
          getTeacherSkill(t.teacher_id).catch(() => null),
          getTeacherTranscripts(t.teacher_id).catch(() => []),
          getDistillStatus(t.teacher_id).catch(() => null),
          getFeedback(t.teacher_id).catch(() => null),
          getMaterials(t.teacher_id).catch(() => []),
          getVoiceStatus(t.teacher_id).catch(() => null),
          listCourses(t.teacher_id).catch(() => []),
        ])
        setSkill(s); setTranscripts(tr); setDistillStatus(ds); setFeedback(fb)
        setMaterials(mt || []); setVoiceStatus(vs); setCourses(cs || [])
      } catch (e) {
        // 还没有教师卡片
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    if (!form.real_name.trim()) { setError('请输入教师姓名'); return }
    setSaving(true)
    try {
      const saved = teacher
        ? await updateTeacherCard(teacher.teacher_id, form)
        : await createTeacherCard(form)
      setTeacher(saved)
      setShowForm(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDistill = async () => {
    if (!teacher || distilling) return
    setDistilling(true); setDistillMsg('')
    try {
      const result = await distillTeacher(teacher.teacher_id)
      setDistillMsg(`蒸馏完成！生成 v${result.version}，语料 ${result.corpus_size} 字，${result.files_used} 个文件`)
      const [s, ds] = await Promise.all([
        getTeacherSkill(teacher.teacher_id).catch(() => null),
        getDistillStatus(teacher.teacher_id).catch(() => null),
      ])
      setSkill(s); setDistillStatus(ds)
    } catch (err) {
      setDistillMsg(`蒸馏失败: ${err.message}`)
    } finally {
      setDistilling(false)
    }
  }

  if (loading) return <div className="loading">加载中…</div>

  const stats = feedback?.stats || { total: 0, avg_rating: 0 }
  const rawTags = teacher ? deriveStyle(teacher).rawTags : []
  const unprocessed = materials.filter(m => m.processable && m.status === 'unprocessed').length

  return (
    <div className="container tdash">
      <div className="page-header">
        <h1>我的工作台</h1>
      </div>

      {!teacher && !showForm ? (
        <div className="empty-state">
          <h3>还未创建教师卡片</h3>
          <p>创建教师卡片后即可上传教学素材、蒸馏你的讲解风格</p>
          <button className="btn btn--accent btn-sm" style={{ marginTop: 18 }} onClick={() => setShowForm(true)}>
            <Icon name="plus" size={16} /> 创建教师卡片
          </button>
        </div>
      ) : teacher && !showForm ? (
        <>
          {/* 身份头卡（与学生看到的同款样式，内置编辑入口） */}
          <div className="tp2">
            <header className="tp2-card tp2-head">
              {teacher.avatar_url || teacher.avatar?.pixel_url ? (
                <img className="tp2-avatar" src={teacher.avatar_url || teacher.avatar.pixel_url} alt={teacher.display_name} />
              ) : (
                <div className="tp2-avatar tp2-avatar--fallback">{teacher.display_name?.charAt(0) || '师'}</div>
              )}
              <div className="tp2-head-main">
                <div className="tp2-head-title">
                  {teacher.display_name}
                  {teacher.subject && <span className="tp2-chip-subject">{teacher.subject}</span>}
                </div>
                <div className="tp2-head-stats">
                  <span><Icon name="star" size={14} className="star on" /> <b>{stats.avg_rating ? Number(stats.avg_rating).toFixed(1) : '—'}</b> 平均评分</span>
                  <span className="tp2-dot" />
                  <span><b>{stats.total}</b> 条评价</span>
                  <span className="tp2-dot" />
                  <span><b>{rawTags.length}</b> 风格标签</span>
                </div>
                {teacher.bio && <p className="tp2-head-bio">{teacher.bio}</p>}
              </div>
              <button className="btn btn-sm btn--ghost tdash-hero-edit" onClick={() => setShowForm(true)}>
                <Icon name="edit" size={14} /> 编辑
              </button>
            </header>
          </div>

          {/* 标签页 */}
          <div className="tdash-tabs">
            <button className={`tdash-tab ${tab === 'work' ? 'on' : ''}`} onClick={() => setTab('work')}>能力工作台</button>
            <button className={`tdash-tab ${tab === 'profile' ? 'on' : ''}`} onClick={() => setTab('profile')}>我的主页（学生视角）</button>
          </div>

          {tab === 'work' ? (
            <>
              {/* 虚拟课堂试讲 */}
              <section className="tdash-section">
                <button className="tdash-tryout" onClick={() => navigate(`/teacher/classroom/${teacher.teacher_id}`)}>
                  <span className="tdash-tryout__icon"><Icon name="cap" size={22} /></span>
                  <span className="tdash-tryout__text">
                    <b>进入虚拟课堂试讲</b>
                    <span>以学生视角提问，亲自感受你的 AI 分身上黑板讲解、用你的音色授课的效果</span>
                  </span>
                  <span className="tdash-tryout__cta">进入试讲 <Icon name="arrowRight" size={15} /></span>
                </button>
              </section>

              {/* 教学资产 */}
              <section className="tdash-section">
                <Eyebrow hint="从素材到分身的每一步">教学资产</Eyebrow>
                {distillMsg && (
                  <div className={`tdash-msg ${distillMsg.includes('失败') ? 'err' : 'ok'}`} style={{ marginBottom: 14 }}>{distillMsg}</div>
                )}
                <div className="cap-grid">
                  <CapTile icon="layers" accent="a-blue" title="素材"
                    status={{ label: materials.length ? `${materials.length} 个` : '空', tone: materials.length ? 'on' : 'off' }}
                    meta={unprocessed > 0 ? `${unprocessed} 个待处理，可转成文字` : '原视频 / 音频 / 课件统一管理'}>
                    <button className="btn btn--ghost" onClick={() => navigate('/teacher/materials')}>
                      <Icon name="layers" size={15} /> 管理素材
                    </button>
                  </CapTile>

                  <CapTile icon="file" accent="a-teal" title="文字库"
                    status={{ label: `${transcripts.length} 份`, tone: transcripts.length ? 'on' : 'off' }}
                    meta="ASR 转写稿，蒸馏与配音的原料">
                    <button className="btn btn--ghost" disabled={!transcripts.length} onClick={() => navigate('/teacher/transcripts')}>
                      <Icon name="file" size={15} /> 审阅转写
                    </button>
                  </CapTile>

                  <CapTile icon="flask" accent="a-purple" title="风格 Skill"
                    status={{ label: skill?.profile ? `v${skill.profile.version || '?'}` : '未蒸馏', tone: skill?.profile ? 'on' : 'off' }}
                    meta={distillStatus ? `可用素材 ${distillStatus.transcript_count} 份` : '上传素材后即可蒸馏'}>
                    {distilling ? (
                      <button className="btn btn--accent" disabled><Icon name="spinner" size={15} className="spin" /> 蒸馏中…</button>
                    ) : skill?.profile ? (
                      <button className="btn btn--ghost" onClick={() => navigate('/teacher/skill')}><Icon name="file" size={15} /> Skill 档案管理</button>
                    ) : distillStatus?.ready_to_distill ? (
                      <button className="btn btn--accent" onClick={handleDistill}><Icon name="flask" size={15} /> 一键蒸馏</button>
                    ) : (
                      <button className="btn btn--ghost" onClick={() => navigate('/teacher/materials')}><Icon name="upload" size={15} /> 先上传素材</button>
                    )}
                  </CapTile>

                  <CapTile icon="mic" accent="a-orange" title="专属音色"
                    status={{ label: voiceStatus?.has_voice ? '已就绪' : '未训练', tone: voiceStatus?.has_voice ? 'on' : 'off' }}
                    meta="让 AI 讲课用你自己的嗓音">
                    <button className="btn btn--ghost" onClick={() => navigate('/teacher/voice')}>
                      <Icon name="mic" size={15} /> 音色训练
                    </button>
                  </CapTile>

                  <CapTile icon="book" accent="a-rose" title="课程"
                    status={{ label: `${courses.length} 门`, tone: courses.length ? 'on' : 'off' }}
                    meta="按大纲自动编排多讲课程">
                    <button className="btn btn--ghost" onClick={() => navigate('/teacher/courses')}>
                      <Icon name="book" size={15} /> 课程编排
                    </button>
                  </CapTile>

                  <CapTile icon="film" accent="a-teal" title="教学插图"
                    status={{ label: '可上传', tone: 'on' }}
                    meta="上传辅助图，讲课时按学生问题自动配图">
                    <button className="btn btn--ghost" onClick={() => navigate('/teacher/images')}>
                      <Icon name="film" size={15} /> 插图库
                    </button>
                  </CapTile>
                </div>
              </section>

              {/* 反馈与进化 */}
              {skill?.profile && (
                <section className="tdash-section">
                  <Eyebrow hint="学生评价驱动 Skill 自我迭代">反馈与进化</Eyebrow>
                  <EvolutionCard teacherId={teacher.teacher_id} feedback={feedback} onSkillUpdated={async () => {
                    const s = await getTeacherSkill(teacher.teacher_id).catch(() => null)
                    setSkill(s)
                  }} />
                </section>
              )}

              {/* 账户 */}
              <section className="tdash-section">
                <Eyebrow>账户</Eyebrow>
                <div className="tdash-account">
                  <div className="tdash-account__item"><label>教师 ID</label><span>{teacher.teacher_id}</span></div>
                  <div className="tdash-account__item"><label>真实姓名</label><span>{teacher.real_name}</span></div>
                  <div className="tdash-account__item tdash-account__item--wide"><label>AI 系统提示词</label>
                    <span className="prompt-preview">{teacher.system_prompt?.slice(0, 140) || '—'}{teacher.system_prompt?.length > 140 ? '…' : ''}</span>
                  </div>
                </div>
              </section>
            </>
          ) : (
            /* 我的主页（学生视角预览）—— 与学生在教师详情页看到的完全一致 */
            <div className="tp2">
              <div className="tdash-preview-note">
                <Icon name="user" size={15} /> 这是学生在你主页上看到的内容：风格速写、教学风格与学生评价。
              </div>
              <StyleSketchCard teacher={teacher} />
              <TeachingStyleCard teacher={teacher} />
              <StudentReviewsCard feedback={feedback} />
            </div>
          )}
        </>
      ) : null}

      {showForm && createPortal(
        <div className="modal-overlay" onClick={() => setShowForm(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2>{teacher ? '编辑教师卡片' : '创建教师卡片'}</h2>
            {error && <div className="error-msg"><Icon name="x" size={15} /> {error}</div>}
            <form onSubmit={handleSubmit}>
              {teacher && (
                <div className="form-group">
                  <label>头像</label>
                  <div className="tdash-avatar-row">
                    {teacher.avatar_url || teacher.avatar?.pixel_url ? (
                      <img className="tdash-avatar-preview" src={teacher.avatar_url || teacher.avatar.pixel_url} alt="头像" />
                    ) : (
                      <div className="tdash-avatar-preview tdash-avatar-preview--fallback">{teacher.display_name?.charAt(0) || '师'}</div>
                    )}
                    <label className="btn btn--ghost btn-sm tdash-avatar-btn">
                      <Icon name="upload" size={15} /> {avatarUploading ? '上传中…' : '更换头像'}
                      <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" hidden onChange={onPickAvatar} disabled={avatarUploading} />
                    </label>
                    <span className="tdash-avatar-hint">png / jpg / webp / gif，≤5MB</span>
                  </div>
                </div>
              )}
              <div className="form-group"><label>真实姓名 *</label><input value={form.real_name} onChange={e => setForm({ ...form, real_name: e.target.value })} placeholder="例如：示例老师" /></div>
              <div className="form-group"><label>展示名称</label><input value={form.display_name} onChange={e => setForm({ ...form, display_name: e.target.value })} placeholder="默认：姓名 + 老师" /></div>
              <div className="form-group"><label>学科</label>
                <select value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })}>
                  <option value="">选择学科</option>
                  {SUBJECTS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="form-group"><label>个人简介</label><input value={form.bio} onChange={e => setForm({ ...form, bio: e.target.value })} placeholder="简短描述教学经历和特点" /></div>
              <div className="form-group"><label>AI 系统提示词 *</label><textarea value={form.system_prompt} onChange={e => setForm({ ...form, system_prompt: e.target.value })} placeholder="定义 AI 助教的行为…" rows={5} /></div>
              <div className="modal-actions">
                <button type="button" className="btn btn--ghost" onClick={() => setShowForm(false)}>取消</button>
                <button type="submit" className="btn btn--accent" disabled={saving}>{saving ? '保存中…' : '保存'}</button>
              </div>
            </form>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

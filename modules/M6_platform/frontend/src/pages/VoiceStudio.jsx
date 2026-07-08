import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getMyTeacher, getVoiceStatus, startVoiceTraining, getVoiceTrainStatus,
  generateVoicePreviews, chooseVoicePreview,
} from '../api'
import Icon from '../components/Icon'
import './VoiceStudio.css'

const ACTIVE = new Set(['queued', 'asr', 'finetune', 'finalize', 'previews'])

const STAGE_LABEL = {
  queued: '排队中',
  asr: '转写切片',
  finetune: 'GPT 微调',
  finalize: '产物落地',
  previews: '生成试听',
}

export default function VoiceStudio() {
  const [teacher, setTeacher] = useState(null)
  const [status, setStatus] = useState(null)   // voice/status 返回（含 train）
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [testText, setTestText] = useState('')
  const pollRef = useRef(null)
  const navigate = useNavigate()

  const train = status?.train || { state: 'idle' }
  const isActive = ACTIVE.has(train.state)

  const loadAll = async () => {
    try {
      const t = await getMyTeacher()
      setTeacher(t)
      const s = await getVoiceStatus(t.teacher_id)
      setStatus(s)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadAll() }, [])

  // 训练/试听进行中时轮询 train/status
  useEffect(() => {
    if (!teacher) return
    if (isActive && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        try {
          const tr = await getVoiceTrainStatus(teacher.teacher_id)
          setStatus(prev => ({ ...(prev || {}), train: tr }))
        } catch { /* 轮询失败下次再试 */ }
      }, 3000)
    }
    if (!isActive && pollRef.current) {
      clearInterval(pollRef.current); pollRef.current = null
      // 结束后刷新一次完整 status（拿最新 profile 参数）
      getVoiceStatus(teacher.teacher_id).then(setStatus).catch(() => {})
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [isActive, teacher])

  const doTrain = async () => {
    if (!teacher) return
    setBusy('train'); setMsg('')
    try {
      const tr = await startVoiceTraining(teacher.teacher_id)
      setStatus(prev => ({ ...(prev || {}), train: { state: tr.state || 'queued', stage_detail: '任务已排队…', progress: 0 } }))
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  const doPreviews = async () => {
    if (!teacher) return
    setBusy('previews'); setMsg('')
    try {
      await generateVoicePreviews(teacher.teacher_id, testText.trim() || undefined)
      setStatus(prev => ({ ...(prev || {}), train: { state: 'previews', stage_detail: '正在生成试听样本…', progress: 0.3 } }))
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  const doChoose = async (previewId) => {
    if (!teacher) return
    setBusy(previewId); setMsg('')
    try {
      const r = await chooseVoicePreview(teacher.teacher_id, previewId)
      setMsg(`已选用「${r.label}」作为讲课音色`)
      const s = await getVoiceStatus(teacher.teacher_id)
      setStatus(s)
    } catch (e) {
      setMsg(e.message)
    } finally {
      setBusy('')
    }
  }

  if (loading) return <div className="loading">加载中…</div>

  if (!teacher) {
    return (
      <div className="container">
        <div className="empty-state">
          <h3>还未创建教师卡片</h3>
          <p>请先在工作台创建教师卡片</p>
          <button className="btn btn--accent btn-sm" onClick={() => navigate('/teacher')}>去工作台</button>
        </div>
      </div>
    )
  }

  const previews = train.previews || []
  const chosen = train.chosen || (status?.temperature != null
    ? (status.variants || []).find(v => v.temperature === status.temperature && v.top_p === status.top_p)?.id
    : null)

  return (
    <div className="container voice-studio">
      <div className="page-header">
        <div>
          <h1>专属音色训练</h1>
          <p className="vs-sub">用你上传的教学音频微调出专属嗓音，再试听挑一款最自然的语气作为讲课音色。</p>
        </div>
        <button className="btn btn-sm btn--ghost" onClick={() => navigate('/teacher')}>
          <Icon name="chevronLeft" size={15} /> 返回工作台
        </button>
      </div>

      {/* 概览 */}
      <section className="vs-card">
        <div className="vs-overview">
          <div className={`vs-stat ${status?.has_voice ? 'on' : 'off'}`}>
            <span className="vs-stat__k">音色状态</span>
            <span className="vs-stat__v">{status?.has_voice ? '已就绪' : '未训练'}</span>
          </div>
          <div className="vs-stat">
            <span className="vs-stat__k">可用音频切片</span>
            <span className="vs-stat__v">{status?.n_samples || 0} 条</span>
          </div>
          <div className="vs-stat">
            <span className="vs-stat__k">当前讲课语气</span>
            <span className="vs-stat__v">
              {status?.temperature != null
                ? `${(status.variants || []).find(v => v.id === chosen)?.label || '自定义'}（t=${status.temperature}）`
                : '默认'}
            </span>
          </div>
        </div>

        {!status?.has_audio_samples ? (
          <div className="vs-hint">
            还没有可用的音频切片。请先到「上传素材」上传教学音视频，系统转写时会自动留存语音切片，之后即可训练音色。
            <button className="btn btn-sm btn--ghost" style={{ marginLeft: 10 }} onClick={() => navigate('/teacher/upload')}>去上传素材</button>
          </div>
        ) : (
          <div className="vs-actions">
            <button className="btn btn--accent" onClick={doTrain} disabled={isActive || busy === 'train'}>
              <Icon name="flask" size={16} /> {status?.has_voice ? '重新训练音色' : '一键训练专属音色'}
            </button>
            {status?.has_voice && (
              <button className="btn btn--ghost" onClick={doPreviews} disabled={isActive || busy === 'previews'}>
                <Icon name="refresh" size={16} /> 重新生成试听
              </button>
            )}
          </div>
        )}
        {msg && <div className={`tdash-msg ${msg.includes('失败') || msg.includes('无') || msg.includes('错') ? 'err' : 'ok'}`}>{msg}</div>}
      </section>

      {/* 进行中：进度 */}
      {isActive && (
        <section className="vs-card vs-progress">
          <div className="vs-progress__head">
            <Icon name="spinner" size={18} className="spin" />
            <b>{STAGE_LABEL[train.state] || '处理中'}</b>
            <span className="vs-progress__detail">{train.stage_detail || ''}</span>
          </div>
          <div className="vs-bar"><div className="vs-bar__fill" style={{ width: `${Math.round((train.progress || 0) * 100)}%` }} /></div>
          <p className="vs-progress__tip">训练为 GPU 长任务（约 10~20 分钟），可离开本页，稍后回来查看；训练期间请勿同时上课，避免显存争用。</p>
        </section>
      )}

      {/* 失败 */}
      {train.state === 'error' && (
        <section className="vs-card vs-error">
          <Icon name="x" size={16} /> 任务失败：{train.message || '未知错误'}
        </section>
      )}

      {/* 试听 + 选择 */}
      {previews.length > 0 && (train.state === 'awaiting_choice' || train.state === 'done') && (
        <section className="vs-card">
          <h3 className="vs-card__title">
            {train.state === 'done' ? '试听样本（已选定，可重新挑选）' : '试听这 6 款语气，选最自然舒服的一款'}
          </h3>
          <p className="vs-card__sub">同一句话用不同合成参数生成，温度越高语气越活泼、表现力越强。选定后即作为你讲课时的音色。</p>
          <div className="vs-grid">
            {previews.map(p => (
              <article key={p.id} className={`vs-variant ${chosen === p.id ? 'chosen' : ''}`}>
                <div className="vs-variant__head">
                  <b>{p.label}</b>
                  {chosen === p.id && <span className="vs-tag">使用中</span>}
                </div>
                <p className="vs-variant__desc">{p.desc}</p>
                <div className="vs-variant__params">t={p.temperature} · top_p={p.top_p}</div>
                <audio controls preload="none" src={p.url} className="vs-audio" />
                <button
                  className={`btn btn-sm ${chosen === p.id ? 'btn--ghost' : 'btn--accent'}`}
                  disabled={!!busy}
                  onClick={() => doChoose(p.id)}>
                  {busy === p.id ? '设定中…' : chosen === p.id ? '当前在用' : '选用这款'}
                </button>
              </article>
            ))}
          </div>

          <div className="vs-retext">
            <input
              value={testText}
              onChange={e => setTestText(e.target.value)}
              placeholder="想用别的句子试听？在此输入后点「重新生成试听」（≤120 字）"
              maxLength={120}
            />
            <button className="btn btn-sm btn--ghost" onClick={doPreviews} disabled={isActive || !!busy}>
              重新生成试听
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMyTeacher, getMaterials, uploadRawMaterial, processMaterials, deleteMaterial } from '../api'
import Icon from '../components/Icon'
import './MaterialManage.css'

const KIND_ICON = { video: 'film', audio: 'volume', courseware: 'file' }
const KIND_LABEL = { video: '视频', audio: '音频', courseware: '课件' }
const STATUS = {
  unprocessed: { label: '未处理', cls: 'todo' },
  processing: { label: '处理中', cls: 'doing' },
  processed: { label: '已处理', cls: 'done' },
  error: { label: '失败', cls: 'err' },
}

function fmtSize(b) {
  if (!b) return '—'
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

export default function MaterialManage() {
  const [teacher, setTeacher] = useState(null)
  const [list, setList] = useState([])
  const [sel, setSel] = useState(new Set())
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [refine, setRefine] = useState(false)
  const [msg, setMsg] = useState('')
  const fileRef = useRef(null)
  const pollRef = useRef(null)
  const navigate = useNavigate()

  const load = async (tid) => {
    const items = await getMaterials(tid).catch(() => [])
    setList(items)
    return items
  }

  useEffect(() => {
    (async () => {
      try {
        const t = await getMyTeacher()
        setTeacher(t)
        await load(t.teacher_id)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  // 有素材处于「处理中」时轮询刷新
  const anyProcessing = list.some(m => m.status === 'processing')
  useEffect(() => {
    if (!teacher) return
    if (anyProcessing && !pollRef.current) {
      pollRef.current = setInterval(() => load(teacher.teacher_id), 3000)
    }
    if (!anyProcessing && pollRef.current) {
      clearInterval(pollRef.current); pollRef.current = null
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }
  }, [anyProcessing, teacher])

  const handleUpload = async (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length || !teacher) return
    setUploading(true); setMsg('')
    try {
      for (const f of files) await uploadRawMaterial(teacher.teacher_id, f)
      await load(teacher.teacher_id)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const toggle = (id) => {
    setSel(prev => {
      const n = new Set(prev)
      n.has(id) ? n.delete(id) : n.add(id)
      return n
    })
  }
  const selectableIds = list.filter(m => m.processable && m.status !== 'processing').map(m => m.material_id)
  const allSelected = selectableIds.length > 0 && selectableIds.every(id => sel.has(id))
  const toggleAll = () => setSel(allSelected ? new Set() : new Set(selectableIds))

  const doProcess = async () => {
    const ids = [...sel].filter(id => selectableIds.includes(id))
    if (!ids.length || !teacher) return
    setBusy(true); setMsg('')
    try {
      const r = await processMaterials(teacher.teacher_id, ids, refine)
      setMsg(`已开始处理 ${r.queued} 个素材${refine ? '（含 AI 精修）' : ''}，完成后将出现在文字库`)
      setSel(new Set())
      await load(teacher.teacher_id)
    } catch (err) {
      setMsg(err.message)
    } finally {
      setBusy(false)
    }
  }

  const doDelete = async (m) => {
    if (!confirm(`删除「${m.title}」？${m.transcript_id ? '它生成的文字稿也会一并删除。' : ''}`)) return
    try {
      await deleteMaterial(teacher.teacher_id, m.material_id)
      await load(teacher.teacher_id)
    } catch (err) {
      setMsg(err.message)
    }
  }

  if (loading) return <div className="loading">加载中…</div>
  if (!teacher) {
    return <div className="container"><div className="empty-state">
      <h3>还未创建教师卡片</h3>
      <button className="btn btn--accent btn-sm" onClick={() => navigate('/teacher')}>去工作台</button>
    </div></div>
  }

  const selCount = [...sel].filter(id => selectableIds.includes(id)).length

  return (
    <div className="container mat-manage">
      <div className="page-header">
        <div>
          <h1>素材管理</h1>
          <p className="mat-sub">放你的原视频、音频、课件。勾选音视频后点「处理」，经 ASR 转写成文字库；课件暂只存档。</p>
        </div>
        <button className="btn btn-sm btn--ghost" onClick={() => navigate('/teacher')}>
          <Icon name="chevronLeft" size={15} /> 返回工作台
        </button>
      </div>

      {/* 工具条 */}
      <section className="mat-toolbar">
        <input ref={fileRef} type="file" multiple hidden onChange={handleUpload}
          accept=".mp4,.webm,.mkv,.mov,.avi,.wav,.mp3,.m4a,.flac,.aac,.ogg,.pdf,.pptx,.ppt" />
        <button className="btn btn--accent btn-sm" disabled={uploading} onClick={() => fileRef.current?.click()}>
          {uploading ? <><Icon name="spinner" size={15} className="spin" /> 上传中…</> : <><Icon name="upload" size={15} /> 上传素材</>}
        </button>
        <div className="mat-toolbar__spacer" />
        {list.length > 0 && (
          <>
            <label className="mat-selall">
              <input type="checkbox" checked={allSelected} onChange={toggleAll} disabled={!selectableIds.length} /> 全选可处理
            </label>
            <label className="mat-selall" title="开启后用 DeepSeek 把口语 ASR 稿精修为规整文字（较慢，需配置 DEEPSEEK_API_KEY；未配置则自动跳过精修）">
              <input type="checkbox" checked={refine} onChange={e => setRefine(e.target.checked)} /> AI 精修
            </label>
            <button className="btn btn--accent btn-sm" disabled={busy || !selCount} onClick={doProcess}>
              <Icon name="flask" size={15} /> 处理选中{selCount ? `（${selCount}）` : ''}
            </button>
          </>
        )}
      </section>

      {msg && <div className={`tdash-msg ${msg.includes('失败') || msg.includes('无') || msg.includes('不') ? 'err' : 'ok'}`}>{msg}</div>}

      {list.length === 0 ? (
        <div className="empty-state">
          <h3>还没有素材</h3>
          <p>上传你的第一份教学视频 / 音频 / 课件</p>
        </div>
      ) : (
        <div className="mat-list">
          {list.map(m => {
            const st = STATUS[m.status] || STATUS.unprocessed
            const checked = sel.has(m.material_id)
            const canSelect = m.processable && m.status !== 'processing'
            return (
              <article key={m.material_id} className={`mat-row ${checked ? 'sel' : ''}`}>
                <label className="mat-row__check">
                  <input type="checkbox" checked={checked} disabled={!canSelect} onChange={() => toggle(m.material_id)} />
                </label>
                <span className={`mat-row__icon k-${m.kind}`}><Icon name={KIND_ICON[m.kind] || 'file'} size={20} /></span>
                <div className="mat-row__main">
                  <div className="mat-row__title">{m.title}</div>
                  <div className="mat-row__meta">
                    <span>{KIND_LABEL[m.kind] || m.kind}</span>
                    <span>· {fmtSize(m.file_size)}</span>
                    {m.kind === 'courseware' && <span className="mat-note">· 课件暂不处理</span>}
                    {m.error && <span className="mat-err-text">· {m.error}</span>}
                  </div>
                </div>
                <span className={`mat-status ${st.cls}`}>
                  {m.status === 'processing' && <Icon name="spinner" size={12} className="spin" />} {st.label}
                </span>
                <div className="mat-row__act">
                  {m.status === 'processed' && (
                    <button className="btn btn-sm btn--ghost" onClick={() => navigate('/teacher/transcripts')}>
                      <Icon name="file" size={14} /> 看转写
                    </button>
                  )}
                  <button className="mat-del" title="删除" disabled={m.status === 'processing'} onClick={() => doDelete(m)}>
                    <Icon name="trash" size={15} />
                  </button>
                </div>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}

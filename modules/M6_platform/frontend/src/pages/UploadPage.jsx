import { useState, useRef } from 'react'
import { uploadMaterial, queryTask } from '../api'
import Icon from '../components/Icon'
import './UploadPage.css'

const STAGES = [
  { key: 'file_validating', label: '文件验证' },
  { key: 'audio_extracting', label: '提取音频' },
  { key: 'audio_segmenting', label: '音频分段' },
  { key: 'asr_transcribing', label: 'ASR 转写' },
  { key: 'text_cleaning', label: '文本精修' },
  { key: 'sample_picking', label: '采样' },
  { key: 'done', label: '完成' },
]
const FORMATS = ['MP4', 'MKV', 'MOV', 'AVI', 'WAV', 'MP3', 'M4A', 'FLAC', 'PDF', 'PPTX']

export default function UploadPage() {
  const [file, setFile] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [taskStatus, setTaskStatus] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef(null)

  const pickFile = (f) => { if (f) { setFile(f); setError('') } }

  const handleDrop = (e) => {
    e.preventDefault(); setDragOver(false)
    pickFile(e.dataTransfer.files?.[0])
  }

  const handleUpload = async () => {
    if (!file) { setError('请选择文件'); return }
    setError(''); setMessage(''); setTaskStatus(null); setUploading(true)
    try {
      const result = await uploadMaterial(file, true)
      setMessage(`上传成功！${result.warning || ''}`)
      if (result.task_id) pollTask(result.task_id)
      else setUploading(false)
    } catch (err) {
      setError(err.message); setUploading(false)
    }
  }

  const pollTask = (tid) => {
    const interval = setInterval(async () => {
      try {
        const info = await queryTask(tid)
        setTaskStatus(info)
        if (info.status === 'success' || info.status === 'failed') {
          clearInterval(interval); setUploading(false)
          if (info.status === 'success') setMessage(`处理完成！生成 ${info.result?.transcripts?.length || 0} 个 transcript`)
          else setError(`处理失败: ${info.error || '未知错误'}`)
        }
      } catch {
        clearInterval(interval); setUploading(false)
      }
    }, 1500)
  }

  const sizeMB = file ? (file.size / 1024 / 1024).toFixed(1) : 0
  const status = taskStatus?.status
  const currentIndex = taskStatus ? STAGES.findIndex(s => s.key === taskStatus.stage) : -1

  const stepState = (i) => {
    if (status === 'success') return 'done'
    if (status === 'failed') return i < currentIndex ? 'done' : i === currentIndex ? 'err' : ''
    // running
    if (i < currentIndex) return 'done'
    if (i === currentIndex) return 'active'
    return ''
  }

  return (
    <div className="container up-wrap">
      <div className="page-header"><h1>上传教学素材</h1></div>

      <div className="up-card">
        <p className="up-intro">上传教学视频、音频或讲义，系统会自动 ASR 转写并精修文本，沉淀为可蒸馏的素材。</p>

        {error && <div className="error-msg"><Icon name="x" size={15} /> {error}</div>}
        {message && <div className="success-msg"><Icon name="check" size={15} /> {message}</div>}

        <label
          className={`up-drop ${dragOver ? 'over' : ''} ${file ? 'has' : ''}`}
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <input ref={fileRef} type="file" hidden
            accept=".mp4,.mkv,.mov,.avi,.wav,.mp3,.m4a,.flac,.pdf,.pptx"
            onChange={e => pickFile(e.target.files[0])} />
          <Icon name={file ? 'file' : 'upload'} size={40} />
          {file ? (
            <div className="up-drop__file">{file.name} <span>{sizeMB} MB</span></div>
          ) : (
            <>
              <div className="up-drop__title">拖放文件到此，或点击选择</div>
              <div className="up-drop__hint">音视频 / 讲义 · 自动转写 + 精修</div>
            </>
          )}
        </label>

        <div className="up-formats">
          {FORMATS.map(f => <span key={f} className="up-fmt">{f}</span>)}
        </div>

        <button className="btn btn--accent up-submit" onClick={handleUpload} disabled={uploading || !file}>
          {uploading ? <><Icon name="spinner" size={16} className="spin" /> 处理中…</> : <><Icon name="upload" size={16} /> 开始上传并处理</>}
        </button>

        {/* 流水线 */}
        {taskStatus && (
          <div className="up-pipe">
            {STAGES.map((s, i) => {
              const st = stepState(i)
              return (
                <div key={s.key} className={`up-step ${st}`}>
                  <span className="up-step__dot">
                    {st === 'done' ? <Icon name="check" size={15} />
                      : st === 'active' ? <Icon name="spinner" size={15} className="spin" />
                      : st === 'err' ? <Icon name="x" size={15} />
                      : i + 1}
                  </span>
                  <span className="up-step__label">{s.label}</span>
                </div>
              )
            })}
          </div>
        )}

        {status === 'running' && (
          <div className="up-progress">
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${(taskStatus.progress || 0) * 100}%` }} /></div>
            <div className="up-progress__pct">{Math.round((taskStatus.progress || 0) * 100)}%</div>
          </div>
        )}

        {status === 'success' && taskStatus.result?.transcripts?.length > 0 && (
          <div className="up-result">
            <h4><Icon name="check" size={16} /> 处理完成</h4>
            {taskStatus.result.transcripts.map((t, i) => (
              <div key={i} className="up-result__item">{typeof t === 'string' ? t : t.transcript_id || JSON.stringify(t)}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

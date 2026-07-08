import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMyTeacher, getTeacherTranscripts, getTranscriptDetail } from '../api'
import Icon from '../components/Icon'
import './TranscriptReview.css'

function fmtTime(sec) {
  if (sec == null) return '--:--'
  const s = Math.floor(sec % 60), m = Math.floor(sec / 60)
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function confClass(c) {
  if (c == null) return ''
  if (c < 0.6) return 'low'
  if (c < 0.8) return 'mid'
  return 'ok'
}

export default function TranscriptReview() {
  const [teacher, setTeacher] = useState(null)
  const [list, setList] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    (async () => {
      try {
        const t = await getMyTeacher()
        setTeacher(t)
        const tr = await getTeacherTranscripts(t.teacher_id).catch(() => [])
        setList(tr)
        if (tr.length) openOne(t.teacher_id, tr[0].transcript_id)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const openOne = async (tid, trid) => {
    setActiveId(trid); setLoadingDetail(true); setDetail(null)
    try {
      setDetail(await getTranscriptDetail(tid, trid))
    } catch (e) {
      setDetail({ _error: e.message })
    } finally {
      setLoadingDetail(false)
    }
  }

  if (loading) return <div className="loading">加载中…</div>

  if (!teacher) {
    return (
      <div className="container"><div className="empty-state">
        <h3>还未创建教师卡片</h3>
        <button className="btn btn--accent btn-sm" onClick={() => navigate('/teacher')}>去工作台</button>
      </div></div>
    )
  }

  const segs = detail?.segments || []

  return (
    <div className="container tr-review">
      <div className="page-header">
        <div>
          <h1>转写审阅台</h1>
          <p className="tr-sub">查看 AI 从你上传素材中识别出的逐句文字稿，核对识别质量。低置信度的句子已标色提示。</p>
        </div>
        <button className="btn btn-sm btn--ghost" onClick={() => navigate('/teacher')}>
          <Icon name="chevronLeft" size={15} /> 返回工作台
        </button>
      </div>

      {list.length === 0 ? (
        <div className="empty-state">
          <h3>还没有转写稿</h3>
          <p>上传教学音视频后，系统会自动转写为文字稿</p>
          <button className="btn btn--accent btn-sm" onClick={() => navigate('/teacher/upload')}>去上传素材</button>
        </div>
      ) : (
        <div className="tr-layout">
          {/* 左：转写列表 */}
          <aside className="tr-list">
            {list.map(t => (
              <button key={t.transcript_id}
                className={`tr-item ${activeId === t.transcript_id ? 'active' : ''}`}
                onClick={() => openOne(teacher.teacher_id, t.transcript_id)}>
                <div className="tr-item__name">{t.source_file || t.transcript_id}</div>
                <div className="tr-item__meta">
                  <span>{t.segments_count} 段</span>
                  {t.duration ? <span>· {fmtTime(t.duration)}</span> : null}
                  {t.estimated_cer != null && (
                    <span className={`tr-cer ${t.estimated_cer > 0.2 ? 'warn' : 'good'}`}>
                      识别误差≈{Math.round(t.estimated_cer * 100)}%
                    </span>
                  )}
                </div>
                {t.low_confidence_segments ? (
                  <div className="tr-item__warn">{t.low_confidence_segments} 段低置信，建议核对</div>
                ) : null}
              </button>
            ))}
          </aside>

          {/* 右：逐段正文 */}
          <section className="tr-detail">
            {loadingDetail ? (
              <div className="loading">加载中…</div>
            ) : detail?._error ? (
              <div className="tr-empty">加载失败：{detail._error}</div>
            ) : detail ? (
              <>
                <div className="tr-detail__head">
                  <div>
                    <h3>{detail.source_file || detail.transcript_id}</h3>
                    <div className="tr-detail__tags">
                      {detail.asr_backend && <span className="tr-chip">{detail.asr_backend}</span>}
                      {detail.asr_quality?.refined && <span className="tr-chip ok">已精修</span>}
                      {detail.language && <span className="tr-chip">{detail.language}</span>}
                      <span className="tr-chip">{segs.length} 段</span>
                    </div>
                  </div>
                </div>
                <div className="tr-segs">
                  {segs.map((sg, i) => (
                    <div key={sg.segment_id || i} className={`tr-seg ${confClass(sg.confidence)}`}>
                      <div className="tr-seg__time">
                        {fmtTime(sg.start)}–{fmtTime(sg.end)}
                        {sg.confidence != null && (
                          <span className="tr-seg__conf">{Math.round(sg.confidence * 100)}%</span>
                        )}
                      </div>
                      <div className="tr-seg__text">{sg.text}</div>
                    </div>
                  ))}
                </div>
              </>
            ) : <div className="tr-empty">从左侧选择一份转写查看</div>}
          </section>
        </div>
      )}
    </div>
  )
}

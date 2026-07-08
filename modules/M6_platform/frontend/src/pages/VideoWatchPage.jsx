import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeacher, getTeacherVideos } from '../api'
import VideoPlayer from '../components/VideoPlayer'
import Icon from '../components/Icon'
import './VideoWatchPage.css'

export default function VideoWatchPage() {
  const { teacherId } = useParams()
  const navigate = useNavigate()
  const [teacher, setTeacher] = useState(null)
  const [videos, setVideos] = useState([])
  const [currentVideo, setCurrentVideo] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const [t, v] = await Promise.all([getTeacher(teacherId), getTeacherVideos(teacherId)])
        setTeacher(t)
        setVideos(v)
        if (v.length > 0) setCurrentVideo(v[0])
      } catch (e) {
        navigate('/student')
      } finally {
        setLoading(false)
      }
    })()
  }, [teacherId])

  if (loading) return <div className="loading">加载中…</div>
  if (!teacher) return null

  const fmtSize = (b) => `${(b / 1024 / 1024).toFixed(1)} MB`

  return (
    <div className="container vwatch">
      <div className="page-header">
        <h1>{teacher.display_name} 的教学视频</h1>
        <button className="btn btn-sm btn--ghost" onClick={() => navigate(`/classroom/${teacherId}`)}>
          <Icon name="cap" size={15} /> 进入课堂
        </button>
      </div>

      {videos.length === 0 ? (
        <div className="empty-state">
          <h3>暂无教学视频</h3>
          <p>该教师还未上传教学视频</p>
        </div>
      ) : (
        <div className="vwatch__layout">
          <div className="vwatch__main">
            {currentVideo && <VideoPlayer videoId={currentVideo.video_id} />}
            {currentVideo && (
              <div className="vwatch__info">
                <h2>{currentVideo.title}</h2>
                <div className="vwatch__meta">
                  <Icon name="clock" size={13} />
                  {new Date(currentVideo.created_at).toLocaleDateString()} · {fmtSize(currentVideo.file_size)}
                </div>
                <p>{currentVideo.description || '暂无描述'}</p>
              </div>
            )}
          </div>

          <aside className="vwatch__side">
            <h3 className="vwatch__side-title">课程列表 <span>{videos.length}</span></h3>
            <div className="vwatch__list">
              {videos.map(v => (
                <button
                  key={v.video_id}
                  className={`vwatch__item ${currentVideo?.video_id === v.video_id ? 'active' : ''}`}
                  onClick={() => setCurrentVideo(v)}
                >
                  <span className="vwatch__item-thumb"><Icon name="play" size={18} /></span>
                  <span className="vwatch__item-info">
                    <span className="vwatch__item-title">{v.title}</span>
                    <span className="vwatch__item-meta">{fmtSize(v.file_size)}</span>
                  </span>
                </button>
              ))}
            </div>
          </aside>
        </div>
      )}
    </div>
  )
}

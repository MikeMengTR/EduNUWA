import { useState, useEffect, useRef } from 'react'
import { getVideos, uploadVideo, deleteVideo } from '../api'
import Icon from '../components/Icon'
import './VideoManagePage.css'

export default function VideoManagePage() {
  const [videos, setVideos] = useState([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const fileRef = useRef(null)

  const load = async () => {
    try {
      const data = await getVideos({ role: 'teacher' })
      setVideos(data)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleUpload = async () => {
    const file = fileRef.current?.files?.[0]
    if (!file) return alert('请选择视频文件')
    if (!title.trim()) return alert('请输入视频标题')
    setUploading(true)
    try {
      await uploadVideo(file, title, description)
      setTitle(''); setDescription(''); fileRef.current.value = ''
      load()
    } catch (e) {
      alert(e.message)
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id) => {
    if (!confirm('确定删除此视频？')) return
    await deleteVideo(id)
    load()
  }

  return (
    <div className="container">
      <div className="page-header"><h1>视频管理</h1></div>

      {/* 上传卡 */}
      <section className="vid-upload">
        <h3><Icon name="upload" size={18} /> 上传新视频</h3>
        <div className="vid-upload__row">
          <div className="form-group">
            <label>视频标题</label>
            <input value={title} onChange={e => setTitle(e.target.value)} placeholder="例如：高等数学第一讲" />
          </div>
          <div className="form-group">
            <label>描述（可选）</label>
            <input value={description} onChange={e => setDescription(e.target.value)} placeholder="简短的视频描述" />
          </div>
          <div className="form-group">
            <label>选择文件</label>
            <input type="file" ref={fileRef} accept=".mp4,.webm,.mkv,.mov,.avi" />
          </div>
          <button className="btn btn--accent btn-sm" onClick={handleUpload} disabled={uploading}>
            {uploading ? <><Icon name="spinner" size={15} className="spin" /> 上传中…</> : <><Icon name="plus" size={15} /> 上传</>}
          </button>
        </div>
      </section>

      {loading ? (
        <div className="loading">加载中…</div>
      ) : videos.length === 0 ? (
        <div className="empty-state">
          <h3>暂无视频</h3>
          <p>上传你的第一个教学视频</p>
        </div>
      ) : (
        <div className="vid-grid">
          {videos.map(v => (
            <article key={v.video_id} className="vid-card">
              <div className="vid-card__cover"><Icon name="film" size={34} /></div>
              <div className="vid-card__body">
                <h3>{v.title}</h3>
                {v.subject && <span className="subject-tag">{v.subject}</span>}
                <p>{v.description || '暂无描述'}</p>
                <div className="vid-card__meta">
                  <Icon name="clock" size={13} />
                  {new Date(v.created_at).toLocaleDateString()} · {(v.file_size / 1024 / 1024).toFixed(1)} MB
                </div>
              </div>
              <div className="vid-card__foot">
                <button className="btn btn-sm btn-danger" onClick={() => handleDelete(v.video_id)}>
                  <Icon name="trash" size={15} /> 删除
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

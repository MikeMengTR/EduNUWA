import { getVideoStreamUrl } from '../api'

export default function VideoPlayer({ videoId }) {
  const token = localStorage.getItem('token')
  const src = `${getVideoStreamUrl(videoId)}?token=${token}`

  return (
    <div className="vplayer">
      <video className="vplayer__video" controls src={src} preload="metadata">
        您的浏览器不支持视频播放
      </video>
    </div>
  )
}

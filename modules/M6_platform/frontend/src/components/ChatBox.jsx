import { useState, useEffect, useRef } from 'react'
import { sendMessage, getChatHistory, clearChatHistory, textToSpeech, teachingDemo } from '../api'

export default function ChatBox({ teacher }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [speaking, setSpeaking] = useState(null)  // 正在播放语音的消息索引
  const audioRef = useRef(null)
  const bottomRef = useRef(null)

  useEffect(() => { loadHistory() }, [teacher.teacher_id])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const loadHistory = async () => {
    try {
      const msgs = await getChatHistory(teacher.teacher_id)
      setMessages(msgs)
    } catch (e) { console.error(e) }
  }

  const handleSend = async () => {
    if (!input.trim() || loading) return
    const msg = input.trim()
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const res = await sendMessage(teacher.teacher_id, msg)
      setMessages(prev => [...prev, { role: 'assistant', content: res.reply }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `[错误] ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  const handleSpeak = async (text, idx) => {
    if (speaking === idx) {
      audioRef.current?.pause()
      setSpeaking(null)
      return
    }
    try {
      setSpeaking(idx)
      const blob = await textToSpeech(text, teacher.teacher_id)
      const url = URL.createObjectURL(blob)
      if (audioRef.current) {
        audioRef.current.src = url
        audioRef.current.play()
        audioRef.current.onended = () => setSpeaking(null)
      }
    } catch (e) {
      alert('TTS 生成失败: ' + e.message)
      setSpeaking(null)
    }
  }

  const [demoLoading, setDemoLoading] = useState(false)

  const handleDemo = async () => {
    if (!input.trim() || demoLoading) return
    const question = input.trim()
    setInput('')
    setDemoLoading(true)

    // 先同步打开窗口（避免浏览器拦截 await 后的 popup）
    const token = localStorage.getItem('token')
    const playerWindow = window.open('', '_blank')
    setMessages(prev => [...prev,
      { role: 'user', content: question },
      { role: 'assistant', content: '正在生成教学演示，请稍候...' },
    ])

    try {
      const result = await teachingDemo(teacher.teacher_id, question)
      const playerUrl = `/runtime/?playback=/api/v1/audio/${result.session_id}/playback_data.json&token=${token}&apiBase=/api/v1`
      if (playerWindow) {
        playerWindow.location.href = playerUrl
      } else {
        // 如果窗口被拦截，在当前页面导航
        window.location.href = playerUrl
      }
      setMessages(prev => [...prev,
        { role: 'assistant', content: `[教学演示] 已生成 ${result.events_count} 个教学事件（语音+板书+虚拟形象）。如未弹出新窗口，请允许弹窗后重试。` },
      ])
    } catch (e) {
      if (playerWindow) playerWindow.close()
      setMessages(prev => [...prev,
        { role: 'assistant', content: `[错误] 教学演示生成失败: ${e.message}` },
      ])
    } finally {
      setDemoLoading(false)
    }
  }

  const handleClear = async () => {
    await clearChatHistory(teacher.teacher_id)
    setMessages([])
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="chat-page">
      <audio ref={audioRef} style={{ display: 'none' }} />

      <div className="chat-header">
        <div>
          <h3>{teacher.display_name}</h3>
          <span style={{ fontSize: 12, color: '#999' }}>{teacher.subject} | {teacher.bio}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <span style={{ fontSize: 11, color: '#aaa' }}>
            {teacher.voice_id ? `音色: ${teacher.voice_id}` : '默认音色'}
          </span>
          <button className="btn btn-sm" style={{ background: '#999' }} onClick={handleClear}>清除对话</button>
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <h3>开始与 {teacher.display_name} 对话</h3>
            <p>发送消息开始学习 · 点击 🔊 按钮听取 AI 语音讲解</p>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div>{msg.content}</div>
            {msg.role === 'assistant' && (
              <button
                className={`speak-btn ${speaking === i ? 'speaking' : ''}`}
                onClick={() => handleSpeak(msg.content, i)}
                title={speaking === i ? '停止播放' : '播放语音'}
                style={{
                  marginTop: 6, padding: '2px 8px', fontSize: 12,
                  border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer',
                  background: speaking === i ? '#1a73e8' : '#fff',
                  color: speaking === i ? '#fff' : '#666',
                }}
              >
                {speaking === i ? '⏹ 停止' : '🔊 语音'}
              </button>
            )}
          </div>
        ))}
        {loading && <div className="typing-indicator"><span /><span /><span /></div>}
        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
          placeholder="输入消息，按 Enter 发送；点「教学演示」体验数字人讲课..." disabled={loading || demoLoading} />
        <button onClick={handleSend} disabled={loading || demoLoading || !input.trim()}>发送</button>
        <button onClick={handleDemo} disabled={loading || demoLoading || !input.trim()}
          className="btn btn-sm"
          style={{ background: (loading || demoLoading || !input.trim()) ? '#aaa' : '#27ae60', color: '#fff', whiteSpace: 'nowrap' }}
          title={!input.trim() ? '请先输入问题' : '生成TTS语音+板书+虚拟形象'}>
          {demoLoading ? '生成中...' : '🎓 教学演示'}
        </button>
      </div>
    </div>
  )
}

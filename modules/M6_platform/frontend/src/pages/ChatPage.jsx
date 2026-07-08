import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getTeacher } from '../api'
import ChatBox from '../components/ChatBox'

export default function ChatPage() {
  const { teacherId } = useParams()
  const navigate = useNavigate()
  const [teacher, setTeacher] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const t = await getTeacher(teacherId)
        if (t) {
          setTeacher(t)
        } else {
          navigate('/student')
        }
      } catch (e) {
        navigate('/student')
      } finally {
        setLoading(false)
      }
    })()
  }, [teacherId])

  if (loading) return <div className="loading">加载中...</div>
  if (!teacher) return null

  return <ChatBox teacher={teacher} />
}

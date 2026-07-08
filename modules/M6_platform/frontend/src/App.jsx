import { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { getMe } from './api'
import Navbar from './components/Navbar'
import LoginPage from './pages/LoginPage'
import TeacherDashboard from './pages/TeacherDashboard'
import StudentDashboard from './pages/StudentDashboard'
import VirtualClassroom from './pages/VirtualClassroom'
import TeacherProfile from './pages/TeacherProfile'
import UploadPage from './pages/UploadPage'
import VideoManagePage from './pages/VideoManagePage'
import MaterialManage from './pages/MaterialManage'
import VoiceStudio from './pages/VoiceStudio'
import TranscriptReview from './pages/TranscriptReview'
import SkillArchive from './pages/SkillArchive'
import CoursePrep from './pages/CoursePrep'
import ImageLibrary from './pages/ImageLibrary'
import CourseCatalog from './pages/CourseCatalog'
import CoursePlayer from './pages/CoursePlayer'
import PlatformApp from './pages/platform/PlatformApp'

export default function App() {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    (async () => {
      try {
        const u = await getMe()
        if (u) setUser(u)
      } catch (e) {
        // not logged in
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  if (loading) return <div className="loading">加载中...</div>

  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage onLogin={setUser} />} />
        <Route path="/platform/*" element={<PlatformApp />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  // 学生默认落到「上一次使用的老师」的课堂；无记录则进完整发现页
  const studentHome = () => {
    const last = localStorage.getItem('lastTeacherId')
    return last ? `/classroom/${last}` : '/student'
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('lastTeacherId')
    setUser(null)  // 清空登录态，渲染未登录路由表（含 /login）
  }

  // 平台监控台独立于师生端布局（无 Navbar），自管口令守卫；放在最外层优先匹配
  if (window.location.pathname.startsWith('/platform')) {
    return (
      <Routes>
        <Route path="/platform/*" element={<PlatformApp />} />
      </Routes>
    )
  }

  return (
    <>
      <Navbar user={user} onLogout={handleLogout} />
      <Routes>
        <Route path="/teacher" element={user.role === 'teacher' ? <TeacherDashboard /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/materials" element={user.role === 'teacher' ? <MaterialManage /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/upload" element={user.role === 'teacher' ? <UploadPage /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/videos" element={user.role === 'teacher' ? <VideoManagePage /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/voice" element={user.role === 'teacher' ? <VoiceStudio /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/transcripts" element={user.role === 'teacher' ? <TranscriptReview /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/skill" element={user.role === 'teacher' ? <SkillArchive /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/courses" element={user.role === 'teacher' ? <CoursePrep /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/images" element={user.role === 'teacher' ? <ImageLibrary /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/learn/:teacherId/:courseId/:chapterId" element={user.role === 'teacher' ? <CoursePlayer /> : <Navigate to={studentHome()} />} />
        <Route path="/teacher/classroom/:teacherId" element={user.role === 'teacher' ? <VirtualClassroom /> : <Navigate to={studentHome()} />} />
        <Route path="/student" element={user.role === 'student' ? <StudentDashboard /> : <Navigate to="/teacher" />} />
        <Route path="/student/courses/:teacherId" element={user.role === 'student' ? <CourseCatalog /> : <Navigate to="/teacher" />} />
        <Route path="/student/learn/:teacherId/:courseId/:chapterId" element={user.role === 'student' ? <CoursePlayer /> : <Navigate to="/teacher" />} />
        <Route path="/teacher/:teacherId" element={<TeacherProfile user={user} />} />
        <Route path="/classroom/:teacherId" element={user.role === 'student' ? <VirtualClassroom /> : <Navigate to="/teacher" />} />
        <Route path="*" element={<Navigate to={user.role === 'teacher' ? '/teacher' : studentHome()} replace />} />
      </Routes>
    </>
  )
}

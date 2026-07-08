// 课程 mock 数据（高保真演示）。
// 底层「Skill 自动编排」未实装；章节内容统一引用预置的真实 events（DEMO_L1/L2/L3），
// 学生观看时由 M5 黑板 iframe 以当前老师音色真实播放。
const DEMO = ['DEMO_L1', 'DEMO_L2', 'DEMO_L3']

const BLUEPRINTS = {
  概率论: [
    { key: 'base', title: '概率论 · 基础篇', summary: '从样本空间到随机变量，搭建概率论的语言体系。',
      chapters: ['随机事件与样本空间', '古典概型与几何概型', '条件概率', '全概率与贝叶斯公式', '随机变量与分布函数', '离散型随机变量', '连续型随机变量', '正态分布'] },
    { key: 'adv', title: '概率论 · 进阶篇', summary: '多维随机变量、数字特征与极限定理。',
      chapters: ['二维随机变量', '边缘分布与独立性', '数学期望', '方差与协方差', '大数定律', '中心极限定理'] },
  ],
  高等数学: [
    { key: 'd', title: '高等数学 · 微分篇', summary: '极限、连续与一元函数微分学。',
      chapters: ['函数与极限', '极限的运算', '连续与间断点', '导数的概念', '求导法则', '微分中值定理', '洛必达法则', '泰勒公式'] },
    { key: 'i', title: '高等数学 · 积分篇', summary: '不定积分、定积分及其应用。',
      chapters: ['不定积分', '换元积分法', '分部积分法', '定积分', '微积分基本定理', '定积分的应用'] },
  ],
  线性代数: [
    { key: 'core', title: '线性代数 · 核心', summary: '行列式、矩阵、向量空间与特征值。',
      chapters: ['行列式', '矩阵运算', '矩阵的逆', '向量组的线性相关性', '矩阵的秩', '线性方程组', '特征值与特征向量', '二次型'] },
  ],
  机器学习: [
    { key: 'ml', title: '机器学习 · 入门', summary: '从线性模型到神经网络的核心脉络。',
      chapters: ['机器学习概述', '线性回归', '逻辑回归', '过拟合与正则化', '支持向量机', '决策树与集成', '神经网络基础', '梯度下降'] },
  ],
}

const DEFAULT_BP = [
  { key: 'main', titleFn: (s) => `${s} · 系统精讲`, summary: '按知识体系编排的成套课程。',
    chapters: ['绪论与课程导览', '核心概念（一）', '核心概念（二）', '典型方法', '案例分析', '难点突破', '综合应用', '总结与展望'] },
]

function hash(str) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return h
}

function normalizeSubject(subject) {
  if (Array.isArray(subject)) return subject[0] || '通识'
  return subject || '通识'
}

function buildCourses(teacherId, subject) {
  const subj = normalizeSubject(subject)
  const bps = BLUEPRINTS[subj] || DEFAULT_BP
  return bps.map((bp, ci) => {
    const courseId = `${teacherId}__${bp.key}`
    const title = bp.titleFn ? bp.titleFn(subj) : bp.title
    const chapters = bp.chapters.map((t, i) => {
      const seed = hash(courseId + '#' + i)
      const demoEvents = DEMO[(i + ci) % DEMO.length]
      return {
        id: `${courseId}__${i + 1}`,
        index: i + 1,
        title: t,
        durationSec: 300 + (seed % 9) * 60, // 5~13 分钟
        demoEvents,
        events_url: `${demoEvents}/events.json`,
        status: 'ready',
      }
    })
    return {
      id: courseId,
      teacherId,
      subject: subj,
      title,
      summary: bp.summary,
      status: 'published',
      chapterCount: chapters.length,
      enrolled: 60 + (hash(courseId) % 420),
      learned: ci === 0 ? 2 + (hash(courseId) % 3) : 0, // 已学讲数(mock)
      chapters,
    }
  })
}

export function getCoursesForTeacher(teacherId, subject) {
  return buildCourses(teacherId, subject)
}

export function getCourse(teacherId, subject, courseId) {
  return buildCourses(teacherId, subject).find((c) => c.id === courseId) || null
}

export function fmtDuration(sec) {
  if (!sec) return '—'
  return `${Math.round(sec / 60)} 分钟`
}

// 把后端真实课程（course.json）归一化为与 mock 课程同形，供页面统一渲染。
export function adaptCourse(c) {
  const chapters = (c.chapters || []).map((ch) => ({
    id: ch.chapter_id,
    index: ch.index,
    title: ch.title,
    durationSec: ch.duration_sec || 0,
    events_url: ch.events_url,
    status: ch.status,
    error: ch.error,
  }))
  return {
    id: c.course_id,
    teacherId: c.teacher_id,
    subject: c.subject,
    title: c.title,
    summary: c.summary,
    real: true,
    published: !!c.published,
    generating: c.status === 'generating' || c.status === 'pending',
    courseStatus: c.status,
    status: c.published ? 'published' : 'draft',
    chapterCount: chapters.length,
    readyCount: chapters.filter((x) => x.status === 'ready').length,
    enrolled: 0,
    learned: 0,
    chapters,
  }
}

export const DEMO_EVENTS = DEMO

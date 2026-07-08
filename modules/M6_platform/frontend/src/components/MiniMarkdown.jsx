/* 极简零依赖 markdown 渲染：用于聊天气泡里 AI 回复/讲课摘要的轻量排版。
 * 支持：无序列表(- * •)、有序列表(1. 1))、加粗(**x**)、行内代码(`x`)、标题(#…)降级为强调段、段落与空行分段。
 * 不处理：表格/图片/链接/嵌套列表/数学公式（聊天气泡按约定不含 LaTeX）。
 * SkillArchive 另有一套面向 TeacherSkill.md 七段结构的渲染器，二者用途不同、各自维护。 */

function renderInline(text, k) {
  // 先按 **加粗** 与 `行内代码` 切分（两类定界互不嵌套，一次 split 即可）
  const parts = String(text).split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((p, i) => {
    if (p.startsWith('**') && p.endsWith('**')) return <strong key={`${k}-${i}`}>{p.slice(2, -2)}</strong>
    if (p.startsWith('`') && p.endsWith('`')) return <code key={`${k}-${i}`} className="mmd-code">{p.slice(1, -1)}</code>
    return <span key={`${k}-${i}`}>{p}</span>
  })
}

export default function MiniMarkdown({ text }) {
  const clean = String(text || '').replace(/```[\s\S]*?```/g, '').trim()
  if (!clean) return null

  const out = []
  let ul = []   // 待 flush 的无序列表项
  let ol = []   // 待 flush 的有序列表项
  const flushUl = () => {
    if (ul.length) {
      const items = ul
      out.push(<ul key={`ul-${out.length}`} className="mmd-ul">{items.map((b, i) => <li key={i}>{renderInline(b, `ul${out.length}-${i}`)}</li>)}</ul>)
      ul = []
    }
  }
  const flushOl = () => {
    if (ol.length) {
      const items = ol
      out.push(<ol key={`ol-${out.length}`} className="mmd-ol">{items.map((b, i) => <li key={i}>{renderInline(b, `ol${out.length}-${i}`)}</li>)}</ol>)
      ol = []
    }
  }
  const flush = () => { flushUl(); flushOl() }

  clean.split('\n').forEach((raw, i) => {
    const line = raw.trim()
    if (!line) { flush(); return }
    let m
    if (/^#{1,6}\s+/.test(line)) {
      flush()
      out.push(<p key={`h-${i}`} className="mmd-h">{renderInline(line.replace(/^#{1,6}\s+/, ''), `h${i}`)}</p>)
    } else if ((m = line.match(/^[-*•]\s+(.*)/))) {
      flushOl(); ul.push(m[1])
    } else if ((m = line.match(/^\d+[.)]\s+(.*)/))) {
      flushUl(); ol.push(m[1])
    } else {
      flush()
      out.push(<p key={`p-${i}`}>{renderInline(line, `p${i}`)}</p>)
    }
  })
  flush()
  return <>{out}</>
}

import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  getMyTeacher, getImageSubjects, listTeachingImages,
  annotateTeachingImage, uploadTeachingImage, updateTeachingImage, deleteTeachingImage,
  extractPptImagesStream,
} from '../api'
import Icon from '../components/Icon'
import './ImageLibrary.css'

const ACCEPT = ['png', 'jpg', 'jpeg', 'webp', 'gif']
const isImage = (f) => ACCEPT.includes((f.name.split('.').pop() || '').toLowerCase())
const isPptx = (f) => /\.pptx$/i.test(f.name)
const needsFix = (it) => !it.keywords.trim() || !it.caption.trim() || !it.llm_desc.trim()

const b64ToBlob = (b64, mime) => {
  const bin = atob(b64)
  const arr = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
  return new Blob([arr], { type: mime })
}

export default function ImageLibrary() {
  const [teacher, setTeacher] = useState(null)
  const [subjects, setSubjects] = useState([])
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [onlyMine, setOnlyMine] = useState(false)
  const [msg, setMsg] = useState('')

  // 批量上传：items 是待入库批次，cur 是当前查看/编辑的下标
  const [items, setItems] = useState([])
  const [cur, setCur] = useState(0)
  const [committing, setCommitting] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [dragging, setDragging] = useState(false)
  // PPT 流式进度 + 被舍弃的图（供查看）
  const [pptProgress, setPptProgress] = useState(null)   // {total,toProcess,kept,dropped,truncated,running,name}
  const [droppedImages, setDroppedImages] = useState([]) // [{id,name,src,reason}]
  const [showDropped, setShowDropped] = useState(false)
  const idRef = useRef(0)
  const itemsRef = useRef([])
  const fileRef = useRef(null)
  const navigate = useNavigate()

  const subjectLabel = (k) => subjects.find(s => s.key === k)?.label || k
  const load = async () => setList(await listTeachingImages().catch(() => []))

  useEffect(() => {
    (async () => {
      try {
        const [t, subs] = await Promise.all([getMyTeacher().catch(() => null), getImageSubjects().catch(() => [])])
        setTeacher(t); setSubjects(subs); await load()
      } finally { setLoading(false) }
    })()
  }, [])

  // 卸载时清掉所有预览 URL
  useEffect(() => { itemsRef.current = items }, [items])
  useEffect(() => () => { itemsRef.current.forEach(it => it.preview && URL.revokeObjectURL(it.preview)) }, [])

  const patchItem = (id, patch) =>
    setItems(prev => prev.map(it => it.id === id
      ? { ...it, ...(typeof patch === 'function' ? patch(it) : patch) } : it))

  // 添加即自动识图（不给任何提示，纯靠 VLM 看图）
  const runAnnotate = async (item) => {
    patchItem(item.id, { ann: 'annotating', annErr: '' })
    try {
      const m = await annotateTeachingImage(item.file, (item.brief || '').trim(), item.subject)
      patchItem(item.id, {
        ann: 'ready', engine: m._engine || '',
        subject: m.subject || 'other',
        topic: m.topic || '',
        keywords: (m.keywords || []).join('，'),
        llm_desc: m.llm_desc || '',
        caption: m.caption || '',
      })
    } catch (e) {
      patchItem(item.id, { ann: 'error', annErr: e.message })
    }
  }

  // 把若干新条目追加进批次，并把视图跳到第一张新加的
  const appendItems = (fresh) => {
    if (!fresh.length) return
    setItems(prev => { setCur(prev.length); return [...prev, ...fresh] })
  }

  // 普通图片：加入即自动识图
  const addImageItems = (files) => {
    const fresh = files.map(f => ({
      id: ++idRef.current, file: f, preview: URL.createObjectURL(f), name: f.name,
      ann: 'pending', annErr: '', engine: '', up: 'idle', upErr: '',
      subject: 'other', brief: '', topic: '', keywords: '', llm_desc: '', caption: '',
    }))
    appendItems(fresh)
    fresh.forEach(it => runAnnotate(it))   // 并发自动识图，各自更新自己的槽
  }

  // 流式追加单张（PPT 逐张冒出）：仅当批次原本为空时把视图跳到第一张，
  // 否则保持当前编辑位置不被后到的图打断。
  const appendOne = (item) =>
    setItems(prev => { if (prev.length === 0) setCur(0); return [...prev, item] })

  // PPT：后端抽图 + 视觉逐张判断，SSE 流式——每判完一张就冒出来，实时计数；
  // 被舍弃的图收进 droppedImages 供「查看被舍弃」按钮回看。
  const addFromPpt = async (pptFile) => {
    setExtracting(true)
    setShowDropped(false)
    setDroppedImages([])
    setPptProgress({ total: 0, toProcess: 0, kept: 0, dropped: 0, truncated: 0, running: true, name: pptFile.name })
    setMsg(`正在从「${pptFile.name}」提取图片并逐张判断是否适合做教学插图…`)
    try {
      await extractPptImagesStream(pptFile, {
        onMeta: (m) => setPptProgress(p => ({
          ...p, total: m.total, toProcess: m.to_process, truncated: m.truncated,
        })),
        onKept: (k) => {
          const mime = k.media_type === 'gif' ? 'image/gif' : 'image/png'
          const blob = b64ToBlob(k.image_b64, mime)
          appendOne({
            id: ++idRef.current, file: new File([blob], k.name, { type: mime }),
            preview: URL.createObjectURL(blob), name: k.name,
            ann: 'ready', annErr: '', engine: 'vision', up: 'idle', upErr: '',
            subject: k.subject || 'other', brief: '',
            topic: k.topic || '', keywords: (k.keywords || []).join('，'),
            llm_desc: k.llm_desc || '', caption: k.caption || '',
          })
          setPptProgress(p => ({ ...p, kept: p.kept + 1 }))
        },
        onDropped: (d) => {
          setDroppedImages(prev => [...prev, {
            id: ++idRef.current, name: d.name,
            src: `data:${d.mime};base64,${d.image_b64}`, reason: d.reason || '',
          }])
          setPptProgress(p => ({ ...p, dropped: p.dropped + 1 }))
        },
        onError: (e) => setMsg(`PPT 处理出错：${e.message || ''}`),
        onDone: (s) => {
          setPptProgress(p => ({ ...p, kept: s.kept, dropped: s.dropped, total: s.total, truncated: s.truncated, running: false }))
          const parts = [`PPT 处理完成：共取出 ${s.total} 张图`]
          parts.push(s.kept ? `保留 ${s.kept} 张待核对入库 ✓` : '没有适合的教学图')
          if (s.dropped) parts.push(`舍弃 ${s.dropped} 张（可点「查看被舍弃」回看）`)
          if (s.truncated) parts.push(`超 100 张上限略过 ${s.truncated} 张`)
          setMsg(parts.join('，'))
        },
      })
    } catch (e) {
      setMsg(`PPT 处理失败：${e.message}`)
      setPptProgress(p => (p ? { ...p, running: false } : p))
    } finally {
      setExtracting(false)
    }
  }

  const addFiles = async (fileList) => {
    const all = Array.from(fileList || [])
    const imgs = all.filter(isImage)
    const ppts = all.filter(isPptx)
    if (!imgs.length && !ppts.length) { setMsg('请拖入图片或 PPT（PNG / JPG / WebP / GIF / .pptx）'); return }
    setMsg('')
    if (imgs.length) addImageItems(imgs)
    for (const p of ppts) await addFromPpt(p)   // 逐个处理，避免并发刷爆视觉接口
    if (fileRef.current) fileRef.current.value = ''
  }

  const removeItem = (id) => {
    const it = items.find(x => x.id === id)
    if (it?.preview) URL.revokeObjectURL(it.preview)
    const next = items.filter(x => x.id !== id)
    setItems(next)
    setCur(c => Math.max(0, Math.min(c, next.length - 1)))
  }

  const clearAll = () => {
    items.forEach(it => it.preview && URL.revokeObjectURL(it.preview))
    setItems([]); setCur(0); setMsg('')
    setPptProgress(null); setDroppedImages([]); setShowDropped(false)
  }

  const curItem = items[cur]
  const setField = (k, v) => curItem && patchItem(curItem.id, { [k]: v })

  const commitAll = async () => {
    const pending = items.filter(it => it.up !== 'done')
    if (!pending.length) { setMsg('没有待入库的图片'); return }
    const bad = pending.filter(needsFix)
    if (bad.length) {
      setCur(items.findIndex(it => it.id === bad[0].id))
      setMsg(`有 ${bad.length} 张缺关键词/图注/描述（缩略图标红），补全后再入库`)
      return
    }
    setCommitting(true); setMsg('')
    let ok = 0, fail = 0
    const doneIds = []
    for (const it of pending) {
      patchItem(it.id, { up: 'uploading', upErr: '' })
      try {
        await uploadTeachingImage(it.file, {
          subject: it.subject, topic: it.topic, keywords: it.keywords,
          llm_desc: it.llm_desc, caption: it.caption,
        })
        patchItem(it.id, { up: 'done' }); doneIds.push(it.id); ok++
      } catch (e) {
        patchItem(it.id, { up: 'error', upErr: e.message }); fail++
      }
    }
    setCommitting(false)
    await load()
    items.filter(it => doneIds.includes(it.id)).forEach(it => it.preview && URL.revokeObjectURL(it.preview))
    setItems(prev => prev.filter(it => !doneIds.includes(it.id)))
    setCur(0)
    setMsg(fail ? `入库完成：成功 ${ok}，失败 ${fail}（失败项留在批次里，可重试）` : `全部入库成功（${ok} 张）✓`)
  }

  const onDrop = (e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }
  const onDragOver = (e) => { e.preventDefault(); if (!dragging) setDragging(true) }
  const onDragLeave = (e) => { e.preventDefault(); setDragging(false) }

  const toggleStatus = async (img) => {
    try { await updateTeachingImage(img.id, { status: img.status === 'active' ? 'disabled' : 'active' }); await load() }
    catch (e) { setMsg(e.message) }
  }
  const del = async (img) => {
    if (!confirm(`删除「${img.caption || img.id}」？此操作不可撤销。`)) return
    try { await deleteTeachingImage(img.id); await load() } catch (e) { setMsg(e.message) }
  }

  if (loading) return <div className="loading">加载中…</div>
  if (!teacher) {
    return <div className="container"><div className="empty-state">
      <h3>还未创建教师卡片</h3>
      <button className="btn btn--accent btn-sm" onClick={() => navigate('/teacher')}>去工作台</button>
    </div></div>
  }

  const myTid = teacher.teacher_id
  const shown = onlyMine ? list.filter(i => i.uploaded_by === myTid) : list
  const mineCount = list.filter(i => i.uploaded_by === myTid).length
  const pendingCount = items.filter(it => it.up !== 'done').length

  // 单条缩略图状态标记
  const itemTag = (it) => {
    if (it.up === 'done') return { cls: 'done', label: '已入库' }
    if (it.up === 'uploading') return { cls: 'doing', label: '入库中' }
    if (it.up === 'error') return { cls: 'err', label: '入库失败' }
    if (it.ann === 'annotating') return { cls: 'doing', label: '识图中' }
    if (it.ann === 'error') return { cls: 'err', label: '识图失败' }
    if (needsFix(it)) return { cls: 'warn', label: '待补全' }
    return { cls: 'ok', label: '就绪' }
  }

  return (
    <div className="container img-lib">
      <div className="page-header">
        <div>
          <h1>教学插图库</h1>
          <p className="img-sub">
            拖入或选择图片（支持多张），或<strong>直接拖入 PPT</strong>——会自动抽取其中的图片、用千问视觉模型
            <strong>判断哪些适合做教学插图</strong>（过滤掉 logo / 背景等装饰图），并对保留的自动识图填好学科 /
            关键词 / 图注。你核对或修改后统一入库，讲课时 AI 会按学生问题自动检索、在黑板上配图。
          </p>
        </div>
        <button className="btn btn-sm btn--ghost" onClick={() => navigate('/teacher')}>
          <Icon name="chevronLeft" size={15} /> 返回工作台
        </button>
      </div>

      <input ref={fileRef} type="file" hidden multiple accept=".png,.jpg,.jpeg,.webp,.gif,.pptx"
        onChange={e => addFiles(e.target.files)} />

      {items.length === 0 ? (
        /* 空批次：整块拖放区 */
        <button className={`img-dropzone ${dragging ? 'drag' : ''}`} disabled={extracting}
          onClick={() => fileRef.current?.click()}
          onDrop={onDrop} onDragOver={onDragOver} onDragLeave={onDragLeave}>
          {extracting ? (
            <><Icon name="spinner" size={28} className="spin" /><span>正在处理 PPT…</span>
              <small>抽取图片并判断是否适合做教学插图，请稍候</small></>
          ) : (
            <><Icon name="upload" size={30} />
              <span>拖入图片或 PPT，或点击选择（可多选）</span>
              <small>图片 PNG / JPG / WebP / GIF（≤5MB）· 或 .pptx 自动抽图筛选 · 加入后自动识图</small></>
          )}
        </button>
      ) : (
        <section className="img-batch" onDrop={onDrop} onDragOver={onDragOver} onDragLeave={onDragLeave}>
          {/* 批次条：缩略图导航 + 计数 + 添加更多 */}
          <div className="img-strip">
            {items.map((it, i) => {
              const t = itemTag(it)
              return (
                <button key={it.id} className={`img-thumb ${i === cur ? 'on' : ''}`} onClick={() => setCur(i)}>
                  <img src={it.preview} alt={it.name} />
                  <span className={`img-thumb__dot ${t.cls}`} />
                  <span className="img-thumb__x" title="移除" onClick={(e) => { e.stopPropagation(); removeItem(it.id) }}>
                    <Icon name="x" size={11} />
                  </span>
                </button>
              )
            })}
            <button className={`img-thumb add ${dragging ? 'drag' : ''}`} disabled={extracting}
              onClick={() => fileRef.current?.click()} title="添加更多（图片或 PPT）">
              <Icon name={extracting ? 'spinner' : 'plus'} size={18} className={extracting ? 'spin' : ''} />
            </button>
          </div>

          {curItem && (
            <div className="img-editor">
              <div className="img-editor__left">
                <div className="img-nav">
                  <button className="img-nav__btn" disabled={cur === 0} onClick={() => setCur(c => c - 1)}>
                    <Icon name="chevronLeft" size={16} />
                  </button>
                  <span className="img-nav__count">第 {cur + 1} / {items.length} 张</span>
                  <button className="img-nav__btn" disabled={cur >= items.length - 1} onClick={() => setCur(c => c + 1)}>
                    <Icon name="chevronRight" size={16} />
                  </button>
                </div>
                <div className="img-preview">
                  <img src={curItem.preview} alt={curItem.name} />
                  {curItem.ann === 'annotating' && (
                    <div className="img-preview__mask"><Icon name="spinner" size={22} className="spin" /> 识图中…</div>
                  )}
                  {(() => { const t = itemTag(curItem); return <span className={`img-badge2 ${t.cls}`}>{t.label}</span> })()}
                </div>
                <button className="img-del-cur" onClick={() => removeItem(curItem.id)}>
                  <Icon name="trash" size={14} /> 移除这张
                </button>
              </div>

              <div className="img-editor__right">
                {curItem.ann === 'error' && (
                  <div className="img-ann-err">识图失败：{curItem.annErr}。可写一句话描述后「重新识图」，或手动填写下方字段。</div>
                )}
                <div className="img-field-row">
                  <label className="img-field img-field--sm">
                    <span>学科（AI 判断·可改）</span>
                    <select value={curItem.subject} onChange={e => setField('subject', e.target.value)}>
                      {subjects.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
                    </select>
                  </label>
                  <label className="img-field img-field--grow">
                    <span>补充说明（可选，用于「重新识图」时给侧重点）</span>
                    <div className="img-brief">
                      <input value={curItem.brief} onChange={e => setField('brief', e.target.value)}
                        placeholder="可留空；或补一句侧重点后点重新识图"
                        onKeyDown={e => { if (e.key === 'Enter') runAnnotate(curItem) }} />
                      <button className="btn btn-sm btn--ghost" disabled={curItem.ann === 'annotating'} onClick={() => runAnnotate(curItem)}>
                        {curItem.ann === 'annotating' ? <Icon name="spinner" size={14} className="spin" /> : <Icon name="sparkles" size={14} />}
                        {curItem.ann === 'annotating' ? ' 识图中' : ' 重新识图'}
                      </button>
                    </div>
                  </label>
                </div>

                <div className="img-field-row">
                  <label className="img-field img-field--sm">
                    <span>知识点</span>
                    <input value={curItem.topic} onChange={e => setField('topic', e.target.value)} placeholder="如：导数" />
                  </label>
                  <label className="img-field img-field--grow">
                    <span>检索关键词（逗号分隔，决定能否被搜到）</span>
                    <input value={curItem.keywords} onChange={e => setField('keywords', e.target.value)}
                      placeholder="切线，割线，导数，斜率，几何意义" />
                  </label>
                </div>

                <label className="img-field">
                  <span>给讲课 AI 的描述（它据此决定何时展示）</span>
                  <input value={curItem.llm_desc} onChange={e => setField('llm_desc', e.target.value)}
                    placeholder="示意图：曲线上某点的切线与割线，适合讲导数几何意义" />
                </label>

                <label className="img-field">
                  <span>图注（学生在图下看到的文字）</span>
                  <input value={curItem.caption} onChange={e => setField('caption', e.target.value)}
                    placeholder="割线随 Q 逼近 P，切线斜率即该点导数" />
                </label>
              </div>
            </div>
          )}

          <div className="img-batch__actions">
            <button className="btn btn--accent" disabled={committing || !pendingCount} onClick={commitAll}>
              {committing ? <><Icon name="spinner" size={15} className="spin" /> 入库中…</> : <><Icon name="check" size={15} /> 全部入库（{pendingCount}）</>}
            </button>
            <button className="btn btn--ghost" disabled={committing} onClick={clearAll}>清空全部</button>
          </div>
        </section>
      )}

      {pptProgress && (() => {
        const processed = pptProgress.kept + pptProgress.dropped
        const pending = Math.max(0, pptProgress.toProcess - processed)
        const pct = pptProgress.toProcess > 0 ? Math.round(processed / pptProgress.toProcess * 100) : 0
        return (
          <div className="ppt-prog">
            <div className="ppt-prog__head">
              <span className="ppt-prog__title">
                {pptProgress.running
                  ? <><Icon name="spinner" size={15} className="spin" /> 正在逐张判断…（{processed}/{pptProgress.toProcess}）</>
                  : <><Icon name="check" size={15} /> PPT 处理完成</>}
              </span>
              <button className="ppt-prog__close" title="关闭" onClick={() => { setPptProgress(null); setShowDropped(false) }}>
                <Icon name="x" size={14} />
              </button>
            </div>
            <div className="ppt-prog__stats">
              <span className="ppt-stat">共 <b>{pptProgress.total}</b> 张</span>
              <span className="ppt-stat ok">可用 <b>{pptProgress.kept}</b></span>
              <span className="ppt-stat drop">舍弃 <b>{pptProgress.dropped}</b></span>
              <span className="ppt-stat pend">待处理 <b>{pending}</b></span>
              {pptProgress.truncated > 0 && <span className="ppt-stat warn">超 100 上限略过 {pptProgress.truncated}</span>}
            </div>
            {pptProgress.toProcess > 0 && (
              <div className="ppt-prog__bar"><div className="ppt-prog__fill" style={{ width: `${pct}%` }} /></div>
            )}
            {droppedImages.length > 0 && (
              <button className="btn btn-sm btn--ghost ppt-prog__view" onClick={() => setShowDropped(s => !s)}>
                <Icon name="search" size={14} /> {showDropped ? '收起被舍弃的图' : `查看被舍弃的 ${droppedImages.length} 张`}
              </button>
            )}
            {showDropped && droppedImages.length > 0 && (
              <div className="ppt-dropped">
                <p className="ppt-dropped__hint">这些图被视觉模型判定为不适合做教学插图（logo / 背景 / 装饰 / 纯文字 / 信息量低等），已自动过滤。</p>
                <div className="ppt-dropped__grid">
                  {droppedImages.map(d => (
                    <figure key={d.id} className="ppt-dropped__cell">
                      <img src={d.src} alt={d.name} loading="lazy" />
                      <figcaption>{d.reason || '不适合做教学插图'}</figcaption>
                    </figure>
                  ))}
                </div>
              </div>
            )}
          </div>
        )
      })()}

      {msg && <div className={`tdash-msg ${/失败|不能|缺|没有|请/.test(msg) ? 'err' : 'ok'}`}>{msg}</div>}

      {/* 图库网格 */}
      <div className="img-lib__bar">
        <h2>图库（{list.length}）</h2>
        <label className="img-mine-toggle">
          <input type="checkbox" checked={onlyMine} onChange={e => setOnlyMine(e.target.checked)} />
          只看我上传的（{mineCount}）
        </label>
      </div>

      {shown.length === 0 ? (
        <div className="empty-state">
          <h3>{onlyMine ? '你还没上传过图片' : '图库还是空的'}</h3>
          <p>上传第一张教学插图，讲课时就能自动配图</p>
        </div>
      ) : (
        <div className="img-grid">
          {shown.map(img => {
            const mine = img.uploaded_by === myTid
            const off = img.status !== 'active'
            return (
              <article key={img.id} className={`img-card ${off ? 'off' : ''}`}>
                <div className="img-card__thumb">
                  <img src={img.url} alt={img.caption} loading="lazy" />
                  {img.media_type === 'gif' && <span className="img-badge gif">GIF</span>}
                  {off && <span className="img-badge off">已停用</span>}
                  {mine && <span className="img-badge mine">我的</span>}
                </div>
                <div className="img-card__body">
                  <div className="img-card__caption">{img.caption || <em>（无图注）</em>}</div>
                  <div className="img-card__meta">
                    <span className="img-chip">{subjectLabel(img.subject)}</span>
                    {img.topic && <span className="img-chip ghost">{img.topic}</span>}
                  </div>
                  {img.keywords?.length > 0 && (
                    <div className="img-card__kws" title={img.keywords.join('、')}>
                      {img.keywords.slice(0, 6).join(' · ')}
                    </div>
                  )}
                </div>
                {mine ? (
                  <div className="img-card__act">
                    <button className="btn btn-sm btn--ghost" onClick={() => toggleStatus(img)}>
                      {img.status === 'active' ? '停用' : '启用'}
                    </button>
                    <button className="img-del" title="删除" onClick={() => del(img)}>
                      <Icon name="trash" size={15} />
                    </button>
                  </div>
                ) : (
                  <div className="img-card__act"><span className="img-preset">预置 · 只读</span></div>
                )}
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}

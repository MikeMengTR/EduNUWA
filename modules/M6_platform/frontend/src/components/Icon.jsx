// 统一线性图标组件 —— 替代全站 emoji，统一 24x24 stroke 风格
// 用法：<Icon name="search" size={18} />
import React from 'react'

const PATHS = {
  search: (<><circle cx="11" cy="11" r="7" /><line x1="21" y1="21" x2="16.65" y2="16.65" /></>),
  send: (<><path d="M22 2 11 13" /><path d="M22 2 15 22l-4-9-9-4 20-7Z" /></>),
  sparkles: (<><path d="M12 3l1.7 5 5 1.7-5 1.7L12 16.4l-1.7-5-5-1.7 5-1.7L12 3Z" /><path d="M19 13l.8 2.2 2.2.8-2.2.8L19 19l-.8-2.2-2.2-.8 2.2-.8L19 13Z" /></>),
  upload: (<><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /></>),
  video: (<><rect x="2" y="6" width="13" height="12" rx="2" /><path d="m15 10 6-3v10l-6-3" /></>),
  film: (<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" /></>),
  edit: (<><path d="M11 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-6" /><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5Z" /></>),
  cap: (<><path d="M22 9 12 5 2 9l10 4 10-4Z" /><path d="M6 11v5c0 1 2.7 2.5 6 2.5s6-1.5 6-2.5v-5" /><path d="M22 9v5" /></>),
  star: (<><path d="m12 3 2.9 6 6.6.9-4.8 4.5 1.2 6.5-5.9-3.1-5.9 3.1 1.2-6.5L2.5 9.9 9.1 9 12 3Z" /></>),
  volume: (<><path d="M11 5 6 9H2v6h4l5 4V5Z" /><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13" /></>),
  stop: (<><rect x="6" y="6" width="12" height="12" rx="2" /></>),
  play: (<><path d="M7 4.5v15l13-7.5-13-7.5Z" /></>),
  x: (<><path d="M18 6 6 18M6 6l12 12" /></>),
  check: (<><path d="m20 6-11 11-5-5" /></>),
  trash: (<><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M10 11v6M14 11v6" /></>),
  user: (<><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6" /></>),
  logout: (<><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5M21 12H9" /></>),
  chevronRight: (<><path d="m9 6 6 6-6 6" /></>),
  chevronLeft: (<><path d="m15 6-6 6 6 6" /></>),
  chevronDown: (<><path d="m6 9 6 6 6-6" /></>),
  home: (<><path d="M3 11.5 12 4l9 7.5" /><path d="M5 10v10h14V10" /></>),
  settings: (<><circle cx="12" cy="12" r="3.1" /><path d="M19.4 15a1.6 1.6 0 0 0 .32 1.77l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.6 1.6 0 0 0-2.73 1.13V21a2 2 0 0 1-4 0v-.09A1.6 1.6 0 0 0 7.43 19.4l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.6 1.6 0 0 0 3 13.6H3a2 2 0 0 1 0-4h.09A1.6 1.6 0 0 0 4.6 7.43l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.6 1.6 0 0 0 10 4.6V3a2 2 0 0 1 4 0v.09a1.6 1.6 0 0 0 2.73 1.13l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.6 1.6 0 0 0 21 9.4V10a2 2 0 0 1 0 4h-.09a1.6 1.6 0 0 0-1.51 1z" /></>),
  plus: (<><path d="M12 5v14M5 12h14" /></>),
  arrowRight: (<><path d="M5 12h14M13 6l6 6-6 6" /></>),
  clock: (<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>),
  award: (<><circle cx="12" cy="9" r="6" /><path d="M9 14.5 7.5 22 12 19.5 16.5 22 15 14.5" /></>),
  book: (<><path d="M12 6.5C10.5 5.2 8.5 4.5 6 4.5c-1 0-2 .1-3 .4v13c1-.3 2-.4 3-.4 2.5 0 4.5.7 6 2 1.5-1.3 3.5-2 6-2 1 0 2 .1 3 .4v-13c-1-.3-2-.4-3-.4-2.5 0-4.5.7-6 2Z" /><path d="M12 6.5v13" /></>),
  file: (<><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z" /><path d="M14 3v6h6M9 14h6M9 18h6" /></>),
  message: (<><path d="M21 12a8 8 0 0 1-11.5 7.2L3 21l1.8-6.5A8 8 0 1 1 21 12Z" /></>),
  mic: (<><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v3" /></>),
  layers: (<><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></>),
  flask: (<><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4A2 2 0 0 0 19 18l-5-9V3" /><path d="M7.5 14h9" /></>),
  spinner: (<><path d="M12 3a9 9 0 1 0 9 9" /></>),
  refresh: (<><path d="M21 12a9 9 0 1 1-2.6-6.4" /><path d="M21 3v6h-6" /></>),
}

export default function Icon({ name, size = 20, strokeWidth = 1.75, className = '', style }) {
  const body = PATHS[name]
  if (!body) return null
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      style={style}
    >
      {body}
    </svg>
  )
}

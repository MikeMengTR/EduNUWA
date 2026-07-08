// 教学插图：[image] 事件的黑板渲染。GIF 放进 <img> 即自动循环播放。
// 加载失败时隐藏整个 figure（不留破图标，讲课不中断）。
import { useState } from 'react';

interface BoardImageProps {
  src: string;
  caption?: string;
  mediaType?: string;
}

export function BoardImage({ src, caption }: BoardImageProps) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return null;

  return (
    <figure className="board-image">
      <img
        src={src}
        alt={caption || '教学插图'}
        loading="lazy"
        onError={() => setFailed(true)}
      />
      {caption && <figcaption className="board-image-caption">{caption}</figcaption>}
    </figure>
  );
}

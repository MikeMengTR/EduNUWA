import { renderMathToHtml, splitBoardItems } from '../../shared/renderMath';

export function WriteBullets({ content }: { content: string | string[] }) {
  const items = Array.isArray(content) ? content : splitBoardItems(String(content));
  return (
    <ul className="board-item board-bullets">
      {items.map((item, i) => (
        <li
          key={i}
          className="board-bullet-item"
          dangerouslySetInnerHTML={{ __html: renderMathToHtml(String(item)) }}
        />
      ))}
    </ul>
  );
}

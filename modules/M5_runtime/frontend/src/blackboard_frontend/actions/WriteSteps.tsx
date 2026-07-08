import { renderMathToHtml, splitBoardItems } from '../../shared/renderMath';

export function WriteSteps({ content }: { content: string | string[] }) {
  const items = Array.isArray(content) ? content : splitBoardItems(String(content));
  return (
    <ol className="board-item board-steps">
      {items.map((item, i) => (
        <li
          key={i}
          className="board-step-item"
          dangerouslySetInnerHTML={{ __html: renderMathToHtml(String(item)) }}
        />
      ))}
    </ol>
  );
}

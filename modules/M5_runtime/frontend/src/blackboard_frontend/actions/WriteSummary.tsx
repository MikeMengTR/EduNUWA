import { renderMathToHtml, splitBoardItems } from '../../shared/renderMath';

export function WriteSummary({ content }: { content: string | string[] }) {
  const lines = Array.isArray(content) ? content : splitBoardItems(String(content));
  return (
    <div className="board-item board-summary">
      {lines.map((line, i) => (
        <div
          key={i}
          className="board-summary-line"
          dangerouslySetInnerHTML={{ __html: renderMathToHtml(String(line)) }}
        />
      ))}
    </div>
  );
}

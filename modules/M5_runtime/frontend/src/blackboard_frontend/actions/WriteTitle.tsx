import { renderMathToHtml } from '../../shared/renderMath';

export function WriteTitle({ content }: { content: string }) {
  return (
    <h1
      className="board-item board-title"
      dangerouslySetInnerHTML={{ __html: renderMathToHtml(String(content)) }}
    />
  );
}

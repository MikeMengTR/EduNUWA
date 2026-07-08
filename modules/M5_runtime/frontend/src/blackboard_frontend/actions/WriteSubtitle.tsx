import { renderMathToHtml } from '../../shared/renderMath';

export function WriteSubtitle({ content }: { content: string }) {
  return (
    <h2
      className="board-item board-subtitle"
      dangerouslySetInnerHTML={{ __html: renderMathToHtml(String(content)) }}
    />
  );
}

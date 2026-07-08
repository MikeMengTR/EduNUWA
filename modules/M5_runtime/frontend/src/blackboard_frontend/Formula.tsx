import { renderMathToHtml } from '../shared/renderMath';

interface FormulaProps {
  latex: string;
  displayMode: 'block' | 'inline';
}

export function Formula({ latex, displayMode }: FormulaProps) {
  // latex 可能带 $$ / $ / \[ \] / \( \) 定界符（解析器历史产物会把定界符一起塞进
  // latex 字段；katex.renderToString 直接收到 $ 会报错并回退成「原始 LaTeX 文本」，
  // 这就是黑板上直接显示 $$...$$ 而非渲染结果的根因）。
  // 统一交给 renderMathToHtml：带定界符就按定界符渲染；裸 TeX 则按 display_mode 补上。
  const raw = String(latex ?? '');
  const hasDelim = /\$|\\\[|\\\(/.test(raw);
  const wrapped = hasDelim
    ? raw
    : displayMode === 'block' ? `$$${raw}$$` : `$${raw}$`;
  const html = renderMathToHtml(wrapped);

  if (displayMode === 'block') {
    return (
      <div
        className="board-item board-formula board-formula-block"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }
  return (
    <span
      className="board-formula-inline"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

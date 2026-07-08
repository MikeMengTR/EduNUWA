// 渲染含 LaTeX 的文本为 HTML：公式片段用 KaTeX 渲染，其余文本转义。
// 兼容所有常见定界符（AI 输出不统一）：$$...$$、$...$、\[...\]、\(...\)。
// 用于黑板文字组件支持内嵌公式 —— AI 常把公式直接写进 board 文本（定义/总结/要点），
// 而非独立 formula 事件，纯文本渲染会显示成原始定界符字符串。
import katex from 'katex';

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

// 非公式文本：转义 HTML 后把 markdown **粗体** 转为 <strong>
function renderText(s: string): string {
  return escapeHtml(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
}

function render(tex: string, block: boolean): string {
  return katex.renderToString(tex.trim(), {
    displayMode: block, throwOnError: false, errorColor: '#cc0000',
  });
}

// 按 | 把板书内容拆成多条要点，但跳过 $...$ / $$...$$ 内部的 |。
// LaTeX 的求值竖线（$\frac{dy}{dx}\big|_{x=x_0}$）、绝对值（$|x|$）会和板书分隔符 |
// 撞车，朴素 split('|') 会把一条公式切成两半、裸 LaTeX 片段（如 _{x=x_0}）漏到黑板上。
export function splitBoardItems(content: string): string[] {
  const out: string[] = [];
  let cur = '';
  let math: '' | '$' | '$$' = ''; // 当前所处的数学定界类型（空=不在公式内）
  for (let i = 0; i < content.length; i++) {
    if (content[i] === '$') {
      const tok = content[i + 1] === '$' ? '$$' : '$';
      if (math === '') math = tok;        // 进入公式
      else if (math === tok) math = '';   // 同类定界符闭合
      cur += tok;
      if (tok === '$$') i++;
      continue;
    }
    if (content[i] === '|' && math === '') { out.push(cur); cur = ''; continue; }
    cur += content[i];
  }
  out.push(cur);
  return out.map((s) => s.trim()).filter(Boolean);
}

export function renderMathToHtml(text: string): string {
  if (!text) return '';
  // 依次匹配：$$...$$ / \[...\]（块级），$...$ / \(...\)（行内）
  const parts = text.split(
    /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\$[^$\n]+?\$|\\\([\s\S]+?\\\))/g,
  );
  return parts
    .map((p) => {
      try {
        if (p.length > 4 && p.startsWith('$$') && p.endsWith('$$')) {
          return render(p.slice(2, -2), true);
        }
        if (p.length > 4 && p.startsWith('\\[') && p.endsWith('\\]')) {
          return render(p.slice(2, -2), true);
        }
        if (p.length > 4 && p.startsWith('\\(') && p.endsWith('\\)')) {
          return render(p.slice(2, -2), false);
        }
        if (p.length > 2 && p.startsWith('$') && p.endsWith('$')) {
          return render(p.slice(1, -1), false);
        }
      } catch {
        /* 渲染失败则退回转义文本 */
      }
      return renderText(p);
    })
    .join('');
}

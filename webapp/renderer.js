/**
 * 文档渲染器：把 AST 渲染成 HTML
 * - 公式用 KaTeX
 * - 表格/列表/标题用 HTML
 * - @plot 用 JSXGraph（在 plotter.js）
 */

import { renderPlot } from './plotter.js';
import {
  Text, InlineMath, Bold, Code, Heading, Paragraph, ListItem,
  Table, DisplayMath, PlotItemNode, Plot, BlankLine,
} from './parser.js';

/**
 * 渲染 inline 节点为 HTML
 */
function renderInline(segments) {
  return segments.map(seg => {
    if (seg instanceof Text) return seg.text;
    if (seg instanceof InlineMath) {
      try {
        return katex.renderToString(seg.latex, { throwOnError: false, displayMode: false });
      } catch (e) { return `<code>${seg.latex}</code>`; }
    }
    if (seg instanceof Bold) return `<strong>${renderInline(seg.segments)}</strong>`;
    if (seg instanceof Code) return `<code>${escapeHtml(seg.code)}</code>`;
    return '';
  }).join('');
}

function escapeHtml(s) {
  return s.split('&').join('&amp;').split('<').join('&lt;').split('>').join('&gt;');
}

/**
 * 渲染整篇文档到容器
 * @param {Array} blocks - parseDocument 返回的 Block 列表
 * @param {HTMLElement} container - 渲染目标容器
 * @param {Object} opts - { defaultWidth: 0.7 }
 */
export function renderDocument(blocks, container, opts = {}) {
  const defaultWidth = opts.defaultWidth ?? 0.7;
  // 释放所有旧 JSXGraph board，避免内存泄漏和 bbox 残留
  if (typeof JXG !== 'undefined' && JXG.boards) {
    for (const id of Object.keys(JXG.boards)) {
      try { JXG.JSXGraph.freeBoard(JXG.boards[id]); } catch (e) {}
    }
  }
  container.innerHTML = '';
  let plotIdx = 0;
  const plotContainers = [];

  // 合并相邻 ListItem
  const merged = [];
  let i = 0;
  while (i < blocks.length) {
    if (blocks[i] instanceof ListItem) {
      const items = [];
      while (i < blocks.length && blocks[i] instanceof ListItem) {
        items.push(blocks[i]); i++;
      }
      merged.push({ type: 'list', items });
    } else {
      merged.push(blocks[i]); i++;
    }
  }

  for (const block of merged) {
    if (block instanceof BlankLine) continue;

    if (block.type === 'list') {
      const ul = document.createElement('ul');
      for (const it of block.items) {
        const li = document.createElement('li');
        li.innerHTML = renderInline(it.segments);
        ul.appendChild(li);
      }
      container.appendChild(ul);
      continue;
    }

    if (block instanceof Heading) {
      const tag = block.level === 1 ? 'h1' : 'h2';
      const el = document.createElement(tag);
      el.innerHTML = renderInline(block.segments);
      container.appendChild(el);
      continue;
    }

    if (block instanceof Paragraph) {
      const p = document.createElement('p');
      p.innerHTML = renderInline(block.segments);
      container.appendChild(p);
      continue;
    }

    if (block instanceof DisplayMath) {
      const div = document.createElement('div');
      div.className = 'display-math';
      try {
        div.innerHTML = katex.renderToString(block.latex, { throwOnError: false, displayMode: true });
      } catch (e) {
        div.textContent = '$$' + block.latex + '$$';
      }
      container.appendChild(div);
      continue;
    }

    if (block instanceof Plot) {
      plotIdx++;
      const w = block.width ?? defaultWidth;
      const wrapper = document.createElement('div');
      wrapper.className = 'plot-wrapper';
      wrapper.style.width = (w * 100) + '%';
      wrapper.style.margin = '1em auto';
      const plotDiv = document.createElement('div');
      plotDiv.id = `plot-${plotIdx}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      plotDiv.className = 'plot-canvas';
      plotDiv.style.width = '100%';
      plotDiv.style.aspectRatio = '5 / 4';
      wrapper.appendChild(plotDiv);
      container.appendChild(wrapper);
      plotContainers.push({ div: plotDiv, plot: block, width: w });
      continue;
    }

    if (block instanceof Table) {
      const table = document.createElement('table');
      const thead = document.createElement('thead');
      const tr = document.createElement('tr');
      for (const cell of block.header) {
        const th = document.createElement('th');
        th.innerHTML = renderInline(cell);
        tr.appendChild(th);
      }
      thead.appendChild(tr);
      table.appendChild(thead);
      const tbody = document.createElement('tbody');
      for (const row of block.rows) {
        const tr = document.createElement('tr');
        for (const cell of row) {
          const td = document.createElement('td');
          td.innerHTML = renderInline(cell);
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      container.appendChild(table);
      continue;
    }
  }

  // 异步渲染所有 plot（KaTeX 可能还没加载）
  for (const { div, plot, width } of plotContainers) {
    try {
      renderPlot(plot, div, width);
    } catch (ex) {
      div.innerHTML = `<div style="color:#d00;padding:1em">绘图错误：${escapeHtml(ex.message)}</div>`;
    }
  }
}

/**
 * 生成 .tex 文件内容（保留 LaTeX 后端兼容性）
 */
export function generateTex(blocks, opts = {}) {
  const defaultWidth = opts.defaultWidth ?? 0.7;
  let plotIdx = 0;
  const plotPaths = new Map();

  // 先收集 plot
  for (const b of blocks) {
    if (b instanceof Plot) {
      plotIdx++;
      plotPaths.set(b, `plot-${plotIdx}.png`);
    }
  }

  const parts = [];
  parts.push(`\\documentclass[11pt,a4paper]{ctexart}
\\usepackage[margin=2.4cm]{geometry}
\\usepackage{amsmath}
\\usepackage{amssymb}
\\usepackage{graphicx}
\\usepackage{booktabs}
\\usepackage{xcolor}
\\usepackage{hyperref}
\\hypersetup{colorlinks=true,linkcolor=black,urlcolor=blue,pdfborder={0 0 0}}
\\newcommand{\\incode}[1]{\\texttt{\\small #1}}
\\title{}
\\date{}
\\begin{document}

`);

  // 合并 list
  const merged = [];
  let i = 0;
  while (i < blocks.length) {
    if (blocks[i] instanceof ListItem) {
      const items = [];
      while (i < blocks.length && blocks[i] instanceof ListItem) {
        items.push(blocks[i]); i++;
      }
      merged.push({ type: 'list', items });
    } else { merged.push(blocks[i]); i++; }
  }

  for (const block of merged) {
    if (block instanceof BlankLine) continue;
    if (block.type === 'list') {
      parts.push('\\begin{itemize}\n');
      for (const it of block.items) {
        parts.push('\\item ' + renderInlineTex(it.segments) + '\n');
      }
      parts.push('\\end{itemize}\n\n');
      continue;
    }
    if (block instanceof Heading) {
      const cmd = block.level === 1 ? 'section' : 'subsection';
      parts.push(`\\${cmd}{${renderInlineTex(block.segments)}}\n`);
      continue;
    }
    if (block instanceof Paragraph) {
      parts.push(renderInlineTex(block.segments) + '\n\n');
      continue;
    }
    if (block instanceof DisplayMath) {
      parts.push(`\\begin{equation*}\n${block.latex}\n\\end{equation*}\n\n`);
      continue;
    }
    if (block instanceof Plot) {
      const w = block.width ?? defaultWidth;
      const path = plotPaths.get(block);
      parts.push(`\\begin{figure}[h]\n\\centering\n\\noindent\\makebox[\\linewidth][c]{%\n  \\includegraphics[width=${w}\\paperwidth]{${path}}}%\n\\end{figure}\n\n`);
      continue;
    }
    if (block instanceof Table) {
      parts.push(renderTableTex(block));
      continue;
    }
  }
  parts.push('\\end{document}\n');
  return parts.join('');
}

function renderInlineTex(segments) {
  return segments.map(seg => {
    if (seg instanceof Text) return seg.text;
    if (seg instanceof InlineMath) return `$${seg.latex}$`;
    if (seg instanceof Bold) return `\\textbf{${renderInlineTex(seg.segments)}}`;
    if (seg instanceof Code) {
      let s = seg.code;
      for (const [ch, rep] of [['\\','\\textbackslash{}'],['&','\\&'],['%','\\%'],['$','\\$'],['#','\\#'],['_','\\_'],['{','\\{'],['}','\\}'],['~','\\textasciitilde{}'],['^','\\textasciicircum{}']]) {
        s = s.split(ch).join(rep);
      }
      return `\\incode{${s}}`;
    }
    return '';
  }).join('');
}

function renderTableTex(node) {
  const ncol = node.header.length;
  const spec = 'l'.repeat(ncol);
  const lines = ['\\begin{center}', `\\begin{tabular}{${spec}}`, '\\toprule'];
  lines.push(node.header.map(c => renderInlineTex(c)).join(' & ') + ' \\\\');
  lines.push('\\midrule');
  for (const row of node.rows) {
    lines.push(row.map(c => renderInlineTex(c)).join(' & ') + ' \\\\');
  }
  lines.push('\\bottomrule', '\\end{tabular}', '\\end{center}', '');
  return lines.join('\n') + '\n';
}

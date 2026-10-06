/**
 * mathtext2doc 解析器（JS 版）
 * 移植自 Python parser.py，支持：
 *   - Markdown 子集：# / ## / - / **bold** / `code` / 表格
 *   - LaTeX 公式：$...$ 行内、$$...$$ 块级
 *   - @plot{...} 绘图指令：显函数 / 隐函数 / 9 种几何图形
 *   - @plot(width=0.x){...} 图宽控制
 */

// AST 节点类型
class Node {}
class Text extends Node { constructor(t) { super(); this.text = t; } }
class InlineMath extends Node { constructor(latex) { super(); this.latex = latex; } }
class Bold extends Node { constructor(segs) { super(); this.segments = segs; } }
class Italic extends Node { constructor(segs) { super(); this.segments = segs; } }
class Code extends Node { constructor(c) { super(); this.code = c; } }
class Heading extends Node { constructor(level, segs) { super(); this.level = level; this.segments = segs; } }
class Paragraph extends Node { constructor(segs) { super(); this.segments = segs; } }
class ListItem extends Node { constructor(segs, ordered = false, orderNum = 0) { super(); this.segments = segs; this.ordered = ordered; this.orderNum = orderNum; } }
class Blockquote extends Node { constructor(blocks) { super(); this.blocks = blocks; } }
class HorizontalRule extends Node {}
class Table extends Node { constructor(header, rows) { super(); this.header = header; this.rows = rows; } }
class DisplayMath extends Node { constructor(latex) { super(); this.latex = latex; } }
class PlotItemNode extends Node {
  constructor(kind, opts = {}) {
    super();
    this.kind = kind;  // 'explicit' | 'implicit' | 'shape'
    this.expr = opts.expr || null;
    this.xRange = opts.xRange || null;
    this.yRange = opts.yRange || null;
    this.label = opts.label || null;
    this.shape = opts.shape || null;
    this.params = opts.params || {};
  }
}
class Plot extends Node {
  constructor(items, width = null) {
    super();
    this.items = items;
    this.width = width;  // null = 用全局默认
  }
}
class BlankLine extends Node {}

class ParseError extends Error {}
class PlotParseError extends ParseError {}

// ---------------------------------------------------------------------------
// LaTeX 转义
// ---------------------------------------------------------------------------
function latexEscape(s) {
  const map = [
    ['\\', '\\textbackslash{}'],
    ['&', '\\&'], ['%', '\\%'], ['$', '\\$'], ['#', '\\#'],
    ['_', '\\_'], ['{', '\\{'], ['}', '\\}'],
    ['~', '\\textasciitilde{}'], ['^', '\\textasciicircum{}'],
  ];
  for (const [ch, rep] of map) s = s.split(ch).join(rep);
  return s;
}

// ---------------------------------------------------------------------------
// @plot 正则
// ---------------------------------------------------------------------------
const PLOT_RE = /@plot(?:\(\s*width\s*=\s*([0-9]*\.?[0-9]+)\s*\))?\{([\s\S]*?)\}/g;

// ---------------------------------------------------------------------------
// 区间求值
// ---------------------------------------------------------------------------
function evalScalar(s, axis = 'x', which = '值') {
  s = s.trim();
  // ^ → **
  const expr = s.split('^').join('**');
  // 白名单：数字 . + - * / ( ) 空格 + pi + e
  const cleaned = expr.split('pi').join('').split('e').join('').split('**').join('').split('E').join('');
  const allowed = '0123456789.+-*/() \t';
  for (const ch of cleaned) {
    if (!allowed.includes(ch)) {
      throw new PlotParseError(`${axis} 区间${which} ${s} 含不允许的字符`);
    }
  }
  try {
    // 用 Function 安全求值（限定作用域）
    const fn = new Function('pi', 'e', 'E', `"use strict"; return (${expr});`);
    const val = fn(Math.PI, Math.E, Math.E);
    if (typeof val !== 'number' || !isFinite(val)) {
      throw new PlotParseError(`${axis} 区间${which} ${s} 求值结果无效`);
    }
    return val;
  } catch (ex) {
    throw new PlotParseError(`${axis} 区间${which} ${s} 求值失败：${ex.message}`);
  }
}

function parseRange(s, axis) {
  s = s.trim();
  if (!s.includes(',')) throw new PlotParseError(`区间缺少逗号：[${s}]`);
  const commaIdx = s.indexOf(',');
  const aStr = s.slice(0, commaIdx);
  const bStr = s.slice(commaIdx + 1);
  const a = evalScalar(aStr, axis, '下界');
  const b = evalScalar(bStr, axis, '上界');
  if (!(a < b)) throw new PlotParseError(`区间下界必须小于上界：[${s}]`);
  return [a, b];
}

function parsePoint(s, key, raw) {
  s = s.trim();
  if (!(s.startsWith('(') && s.endsWith(')'))) {
    throw new PlotParseError(`坐标点应为 (x, y)：${s}`);
  }
  const inner = s.slice(1, -1).trim();
  if (!inner.includes(',')) throw new PlotParseError(`坐标点缺少逗号：${s}`);
  const commaIdx = inner.indexOf(',');
  const xStr = inner.slice(0, commaIdx);
  const yStr = inner.slice(commaIdx + 1);
  return [evalScalar(xStr, key, '点 x 坐标'), evalScalar(yStr, key, '点 y 坐标')];
}

function parseShapeValue(valStr, key, raw) {
  const s = valStr.trim();
  // 点列表 [(x,y), ...]
  if (s.startsWith('[') && s.endsWith(']')) {
    const inner = s.slice(1, -1).trim();
    const parts = [];
    let buf = '', depth = 0;
    for (const ch of inner) {
      if (ch === '(') { depth++; buf += ch; }
      else if (ch === ')') { depth = Math.max(0, depth - 1); buf += ch; }
      else if (ch === ',' && depth === 0) { parts.push(buf.trim()); buf = ''; }
      else buf += ch;
    }
    if (buf.trim()) parts.push(buf.trim());
    const pts = [];
    for (const p of parts) {
      if (p) pts.push(parsePoint(p, key, raw));
    }
    if (!pts.length) throw new PlotParseError(`点列表为空`);
    return pts;
  }
  // 单点 (x, y)
  if (s.startsWith('(') && s.endsWith(')')) return parsePoint(s, key, raw);
  // 标量
  return evalScalar(s, key, `参数 ${key}`);
}

// ---------------------------------------------------------------------------
// 几何图形规格
// ---------------------------------------------------------------------------
const SHAPE_SPECS = {
  point:     { required: ['at'] },
  segment:   { required: ['from', 'to'] },
  line:      { required: ['from', 'to'] },
  circle:    { required: ['center', 'r'] },
  ellipse:   { required: ['center', 'a', 'b'] },
  polygon:   { required: ['points'] },
  rectangle: { required: ['origin', 'w', 'h'] },
  vector:    { required: ['from', 'to'] },
  parabola:  { required: ['vertex', 'p'], optional: ['direction'] },
};

// ---------------------------------------------------------------------------
// 拆分参数（跳过 [...]、(...)、"..." 内的分隔符）
// ---------------------------------------------------------------------------
function splitParams(s, sep) {
  const segs = [];
  let buf = '', inStr = false, bracket = 0, paren = 0;
  for (const ch of s) {
    if (ch === '"') { inStr = !inStr; buf += ch; }
    else if (ch === '[' && !inStr) { bracket++; buf += ch; }
    else if (ch === ']' && !inStr) { bracket = Math.max(0, bracket - 1); buf += ch; }
    else if (ch === '(' && !inStr) { paren++; buf += ch; }
    else if (ch === ')' && !inStr) { paren = Math.max(0, paren - 1); buf += ch; }
    else if (ch === sep && !inStr && bracket === 0 && paren === 0) {
      segs.push(buf.trim()); buf = '';
    } else buf += ch;
  }
  if (buf.trim()) segs.push(buf.trim());
  return segs;
}

// ---------------------------------------------------------------------------
// 解析单个绘制项
// ---------------------------------------------------------------------------
function parseOnePlotItem(s) {
  const segs = splitParams(s, ',');
  if (!segs.length) throw new PlotParseError(`空的绘图项：${s}`);
  const first = segs[0];

  // 几何图形？
  const mShape = first.match(/^shape\s*=\s*(\w+)\s*$/);
  if (mShape) return parseShapeItem(mShape[1], segs.slice(1), s);

  // 函数曲线
  const expr = first;
  let xRange = null, yRange = null, label = null;
  for (const seg of segs.slice(1)) {
    if (!seg) continue;
    let m;
    if (m = seg.match(/^x\s+in\s+\[(.*)\]\s*$/)) { xRange = parseRange(m[1], 'x'); continue; }
    if (m = seg.match(/^y\s+in\s+\[(.*)\]\s*$/)) { yRange = parseRange(m[1], 'y'); continue; }
    if (m = seg.match(/^label\s*=\s*"(.*)"\s*$/)) { label = m[1]; continue; }
    throw new PlotParseError(`无法识别的绘图参数：${seg}`);
  }
  if (!xRange) throw new PlotParseError(`绘图项缺少 x in [...] 定义域：${s}`);
  let kind;
  if (/^\s*y\s*=/.test(expr)) kind = 'explicit';
  else if (expr.includes('=')) {
    kind = 'implicit';
    if (!yRange) throw new PlotParseError(`隐函数必须指定 y in [...]：${s}`);
  } else throw new PlotParseError(`无法判定显/隐函数，缺少 '='：${s}`);
  return new PlotItemNode(kind, { expr, xRange, yRange, label });
}

function parseShapeItem(shape, paramSegs, raw) {
  shape = shape.toLowerCase();
  if (!SHAPE_SPECS[shape]) {
    throw new PlotParseError(`未知几何图形 shape=${shape}。支持：${Object.keys(SHAPE_SPECS).join(', ')}`);
  }
  const params = {};
  let label = null, xRange = null, yRange = null;
  for (const seg of paramSegs) {
    if (!seg) continue;
    let m;
    if (m = seg.match(/^x\s+in\s+\[(.*)\]\s*$/)) { xRange = parseRange(m[1], 'x'); continue; }
    if (m = seg.match(/^y\s+in\s+\[(.*)\]\s*$/)) { yRange = parseRange(m[1], 'y'); continue; }
    if (m = seg.match(/^label\s*=\s*"(.*)"\s*$/)) { label = m[1]; continue; }
    // direction 是字符串参数（up/down/left/right），不走 parseShapeValue
    if (m = seg.match(/^direction\s*=\s*(\w+)$/)) {
      params['direction'] = m[1].toLowerCase();
      continue;
    }
    if (m = seg.match(/^(\w+)\s*=\s*(.+)$/)) {
      params[m[1].toLowerCase()] = parseShapeValue(m[2], m[1].toLowerCase(), raw);
      continue;
    }
    throw new PlotParseError(`无法识别的几何参数：${seg}`);
  }
  for (const k of SHAPE_SPECS[shape].required) {
    if (!(k in params)) throw new PlotParseError(`图形 ${shape} 缺少必需参数 ${k}`);
  }
  return new PlotItemNode('shape', { shape, params, xRange, yRange, label });
}

function parsePlotItems(body) {
  const items = [];
  for (const raw of splitParams(body, ';')) {
    if (raw.trim()) items.push(parseOnePlotItem(raw.trim()));
  }
  return items;
}

// ---------------------------------------------------------------------------
// 行内解析
// ---------------------------------------------------------------------------
function parseInline(text) {
  const out = [];
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === '$') {
      const j = text.indexOf('$', i + 1);
      if (j === -1) { out.push(new Text(latexEscape(ch))); i++; continue; }
      out.push(new InlineMath(text.slice(i + 1, j)));
      i = j + 1;
    } else if (text.startsWith('**', i)) {
      const j = text.indexOf('**', i + 2);
      if (j === -1) { out.push(new Text(latexEscape('**'))); i += 2; continue; }
      out.push(new Bold(parseInline(text.slice(i + 2, j))));
      i = j + 2;
    } else if (ch === '*') {
      // *italic*（单个星号）
      const j = text.indexOf('*', i + 1);
      if (j === -1) { out.push(new Text(latexEscape(ch))); i++; continue; }
      const inner = text.slice(i + 1, j);
      if (!inner) { out.push(new Text(latexEscape('*'))); i++; continue; }
      out.push(new Italic(parseInline(inner)));
      i = j + 1;
    } else if (ch === '`') {
      const j = text.indexOf('`', i + 1);
      if (j === -1) { out.push(new Text(latexEscape(ch))); i++; continue; }
      out.push(new Code(text.slice(i + 1, j)));
      i = j + 1;
    } else {
      let k = i;
      while (k < text.length && text[k] !== '$' && text[k] !== '`' && text[k] !== '*' && !text.startsWith('**', k)) k++;
      out.push(new Text(latexEscape(text.slice(i, k))));
      i = k;
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// 表格
// ---------------------------------------------------------------------------
function isTableRow(line) { return line.trimStart().startsWith('|'); }
function splitTableRow(line) {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map(c => c.trim());
}
const TABLE_SEP_RE = /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$/;

function parseTable(lines) {
  if (lines.length < 2) throw new ParseError(`表格行数不足`);
  const headerCells = splitTableRow(lines[0]).map(parseInline);
  if (!TABLE_SEP_RE.test(lines[1])) throw new ParseError(`表格第二行应为分隔行 |---|---|`);
  const rows = [];
  for (const ln of lines.slice(2)) {
    const cells = splitTableRow(ln);
    while (cells.length < headerCells.length) cells.push('');
    cells.length = headerCells.length;
    rows.push(cells.map(parseInline));
  }
  return new Table(headerCells, rows);
}

// ---------------------------------------------------------------------------
// 主解析入口
// ---------------------------------------------------------------------------
const HEADING_RE = /^(#{1,4})\s+(.*)$/;
const LIST_RE = /^-\s+(.*)$/;
const OLIST_RE = /^(\d+)\.\s+(.*)$/;
const HR_RE = /^(-{3,}|\*{3,}|_{3,})\s*$/;
const QUOTE_RE = /^>\s?(.*)$/;

export function parseDocument(text) {
  // 1. 抽出 @plot{...}
  const plots = [];
  text = text.replace(PLOT_RE, (m, w, body) => {
    const items = parsePlotItems(body);
    let width = null;
    if (w !== undefined) {
      width = parseFloat(w);
      if (!(width > 0 && width <= 1)) {
        throw new PlotParseError(`@plot 的 width 必须在 (0, 1] 之间，得到 ${width}`);
      }
    }
    plots.push(new Plot(items, width));
    return `\n\x00PLOT${plots.length - 1}\x00\n`;
  });

  // 2. 抽出 $$...$$
  const displayMaths = [];
  text = text.replace(/\$\$([\s\S]+?)\$\$/g, (m, latex) => {
    displayMaths.push(new DisplayMath(latex.trim()));
    return `\n\x00DM${displayMaths.length - 1}\x00\n`;
  });

  // 3. 按行解析
  const lines = text.split('\n');
  const blocks = [];
  let i = 0, n = lines.length;
  while (i < n) {
    const line = lines[i];

    if (!line.trim()) { blocks.push(new BlankLine()); i++; continue; }

    // 块级公式占位符
    let m;
    if (m = line.trim().match(/^\x00DM(\d+)\x00$/)) {
      blocks.push(displayMaths[+m[1]]); i++; continue;
    }
    // @plot 占位符
    if (m = line.trim().match(/^\x00PLOT(\d+)\x00$/)) {
      blocks.push(plots[+m[1]]); i++; continue;
    }
    // 标题（1~4 级）
    if (m = line.match(HEADING_RE)) {
      blocks.push(new Heading(m[1].length, parseInline(m[2].trim())));
      i++; continue;
    }
    // 分隔线 --- *** ___
    if (HR_RE.test(line)) {
      blocks.push(new HorizontalRule());
      i++; continue;
    }
    // 引用块 > text
    if (m = line.match(QUOTE_RE)) {
      const quoteLines = [];
      while (i < n && (m = lines[i].match(QUOTE_RE))) {
        quoteLines.push(m[1]);
        i++;
      }
      const quoteText = quoteLines.join('\n');
      blocks.push(new Blockquote(parseDocument(quoteText)));
      continue;
    }
    // 无序列表项
    if (m = line.match(LIST_RE)) {
      blocks.push(new ListItem(parseInline(m[1].trim()), false, 0));
      i++; continue;
    }
    // 有序列表项 1. 2. 3.
    if (m = line.match(OLIST_RE)) {
      blocks.push(new ListItem(parseInline(m[2].trim()), true, parseInt(m[1])));
      i++; continue;
    }
    // 表格
    if (isTableRow(line)) {
      const tbl = [];
      while (i < n && isTableRow(lines[i])) { tbl.push(lines[i]); i++; }
      blocks.push(parseTable(tbl));
      continue;
    }
    // 段落
    const paraBuf = [line];
    i++;
    while (i < n) {
      const nxt = lines[i];
      if (!nxt.trim() || HEADING_RE.test(nxt) || LIST_RE.test(nxt) || OLIST_RE.test(nxt)
          || HR_RE.test(nxt) || QUOTE_RE.test(nxt) || isTableRow(nxt)
          || /^\x00DM(\d+)\x00$/.test(nxt.trim()) || /^\x00PLOT(\d+)\x00$/.test(nxt.trim())) break;
      paraBuf.push(nxt); i++;
    }
    blocks.push(new Paragraph(parseInline(paraBuf.join(' ').trim())));
  }
  return blocks;
}

export {
  Node, Text, InlineMath, Bold, Italic, Code, Heading, Paragraph, ListItem,
  Blockquote, HorizontalRule, Table, DisplayMath, PlotItemNode, Plot, BlankLine,
  ParseError, PlotParseError, latexEscape,
};

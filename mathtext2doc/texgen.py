"""LaTeX 文档生成器。

输入：parser.parse_document() 返回的 Block 列表，以及 plot PNG 路径映射。
输出：完整 .tex 文件内容。

设计：
    - 使用 ctexart 文档类（ctex 宏包提供 xeCJK 中文支持，xelatex 编译）。
    - 几何：a4paper，标准边距。
    - 包：amsmath, amssymb, graphicx, geometry, hyperref, booktabs, xcolor。
    - 函数图宽度 = 0.4\\textwidth。
    - 行内公式 $...$、块级公式用 equation* 环境。
    - 表格用 booktabs。
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from .parser import (
    BlankLine,
    Bold,
    Code,
    DisplayMath,
    Heading,
    InlineMath,
    ListItem,
    Paragraph,
    Plot,
    Table,
    Text,
)


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------

_DOCUMENT_PREAMBLE = r"""\documentclass[11pt,a4paper]{ctexart}
\usepackage[margin=2.4cm]{geometry}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{xcolor}
\usepackage{hyperref}
\hypersetup{
  colorlinks=true,
  linkcolor=black,
  urlcolor=blue,
  pdfborder={0 0 0}
}
% 行内代码样式
\newcommand{\incode}[1]{\texttt{\small #1}}

\title{}
\date{}
"""

_DOCUMENT_BEGIN = r"\begin{document}"
_DOCUMENT_END = r"\end{document}"


# ---------------------------------------------------------------------------
# Inline 节点 → LaTeX 片段
# ---------------------------------------------------------------------------

def _render_inline(segments: list) -> str:
    out = []
    for seg in segments:
        out.append(_render_inline_node(seg))
    return "".join(out)


def _render_inline_node(node) -> str:
    if isinstance(node, Text):
        return node.text  # 已在 parser 中转义
    if isinstance(node, InlineMath):
        return f"${node.latex}$"
    if isinstance(node, Bold):
        return r"\textbf{" + _render_inline(node.segments) + "}"
    if isinstance(node, Code):
        # 行内代码：把特殊字符再转义一次（parser 没有转义 code 内容）
        return r"\incode{" + _latex_escape_code(node.code) + "}"
    # 兜底
    return ""


def _latex_escape_code(s: str) -> str:
    # code 里的特殊字符也要转义，但已经在 parser.parse_inline 中可能没转义
    for ch, rep in [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]:
        s = s.replace(ch, rep)
    return s


# ---------------------------------------------------------------------------
# Block 节点 → LaTeX 片段
# ---------------------------------------------------------------------------

def _render_block(node, plot_paths: Dict[int, str], default_width: float = 0.7) -> str:
    if isinstance(node, BlankLine):
        return ""  # 段落之间已经用空行分隔
    if isinstance(node, Heading):
        cmd = "section" if node.level == 1 else "subsection"
        return f"\\{cmd}{{{_render_inline(node.segments)}}}\n"
    if isinstance(node, Paragraph):
        return _render_inline(node.segments) + "\n\n"
    if isinstance(node, ListItem):
        return r"\begin{itemize}" + "\n" + \
               r"\item " + _render_inline(node.segments) + "\n" + \
               r"\end{itemize}" + "\n"
    if isinstance(node, DisplayMath):
        return "\\begin{equation*}\n" + node.latex + "\n\\end{equation*}\n\n"
    if isinstance(node, Plot):
        path = plot_paths.get(id(node))
        if not path:
            return "% [plot 图缺失，跳过]\n"
        # 单图 width 优先，否则用全局默认
        w = node.width if node.width is not None else default_width
        # 用 \paperwidth × w 作为宽度，让图溢出正文区居中
        # \noindent\makebox[\linewidth][c]{...} 让超宽图水平居中
        include_cmd = "  \\includegraphics[width=" + str(w) + "\\paperwidth]{" + path + "}"
        return (
            "\\begin{figure}[h]\n"
            "\\centering\n"
            "\\noindent\\makebox[\\linewidth][c]{%\n"
            + include_cmd + "}%\n"
            "\\end{figure}\n\n"
        )
    if isinstance(node, Table):
        return _render_table(node) + "\n"
    return ""


def _render_table(node: Table) -> str:
    ncol = len(node.header)
    spec = "l" * ncol
    lines = []
    lines.append(r"\begin{center}")
    lines.append(r"\begin{tabular}{" + spec + "}")
    lines.append(r"\toprule")
    # 表头
    header_cells = [_render_inline(c) for c in node.header]
    lines.append(" & ".join(header_cells) + r" \\")
    lines.append(r"\midrule")
    # 数据行
    for row in node.rows:
        cells = [_render_inline(c) for c in row]
        lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{center}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def generate_tex(
    blocks: List,
    plot_paths: Dict[int, str],
    default_plot_width: float = 0.7,
) -> str:
    r"""生成完整 .tex 文件内容。

    参数：
        blocks: parse_document() 返回的 Block 列表
        plot_paths: {id(Plot 节点): PNG 文件名（不含目录，.tex 同目录）}
        default_plot_width: 全局默认图宽（相对于 \paperwidth，0~1），默认 0.7
    """
    body_parts = []
    # 合并相邻的 ListItem 为单个 itemize 环境
    i = 0
    n = len(blocks)
    while i < n:
        b = blocks[i]
        if isinstance(b, ListItem):
            items = []
            while i < n and isinstance(blocks[i], ListItem):
                items.append(blocks[i])
                i += 1
            parts = [r"\begin{itemize}"]
            for it in items:
                parts.append(r"\item " + _render_inline(it.segments))
            parts.append(r"\end{itemize}")
            body_parts.append("\n".join(parts) + "\n\n")
            continue
        body_parts.append(_render_block(b, plot_paths, default_plot_width))
        i += 1

    body = "".join(body_parts)
    return _DOCUMENT_PREAMBLE + _DOCUMENT_BEGIN + "\n\n" + body + _DOCUMENT_END + "\n"

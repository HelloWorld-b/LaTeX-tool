"""文本解析器。

输入：UTF-8 纯文本，可能包含中文、基础 Markdown、$...$ / $$...$$ LaTeX 公式、
@plot{...} 绘图指令。

输出：一个 Document AST，由若干 Block 节点构成：
    - Heading(level, text)
    - Paragraph(segments)        段落，segments 是 Inline 列表
    - ListItem(segments)
    - Table(header, rows)
    - DisplayMath(latex)         块级公式 $$...$$
    - Plot(items)                @plot{...}，items 是 PlotItem 列表
    - BlankLine()

Inline 节点：
    - Text(str)                  普通文本（已经过 LaTeX 转义）
    - InlineMath(latex)          行内公式 $...$
    - Bold(segments)             **粗体**
    - Code(str)                  `代码`（基础支持）

PlotItem:
    - kind: "explicit" | "implicit"
    - expr: 原始表达式字符串（y = sin(x) 或 x^2 + y^2 = 1）
    - x_range: (xmin, xmax)       sympy 表达式或浮点
    - y_range: (ymin, ymax) | None
    - label: str | None
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# AST 节点定义
# ---------------------------------------------------------------------------

@dataclass
class Text:
    text: str


@dataclass
class InlineMath:
    latex: str


@dataclass
class Bold:
    segments: list


@dataclass
class Code:
    code: str


@dataclass
class Heading:
    level: int
    segments: list


@dataclass
class Paragraph:
    segments: list


@dataclass
class ListItem:
    segments: list


@dataclass
class Table:
    header: List[list]   # 每个单元格是 inline 列表
    rows: List[List[list]]


@dataclass
class DisplayMath:
    latex: str


@dataclass
class PlotItem:
    """@plot 的一个绘制项。

    几何图形：kind="shape", shape="point|segment|line|circle|ellipse|polygon|rectangle|vector"
    函数曲线：kind="explicit|implicit"，expr 为表达式字符串
    """
    kind: str                       # "explicit" | "implicit" | "shape"
    expr: Optional[str] = None      # 函数曲线的原始表达式
    x_range: Optional[Tuple[object, object]] = None
    y_range: Optional[Tuple[object, object]] = None
    label: Optional[str] = None
    # 几何图形专用字段
    shape: Optional[str] = None     # point/segment/line/circle/ellipse/polygon/rectangle/vector
    # 通用 dict 存几何参数：at/from/to/center/r/a/b/points/origin/w/h 等
    # 值可能是 tuple（坐标）或 float（标量）或 list[tuple]（点列表）
    params: dict = field(default_factory=dict)


@dataclass
class Plot:
    items: List[PlotItem] = field(default_factory=list)


@dataclass
class BlankLine:
    pass


# ---------------------------------------------------------------------------
# LaTeX 转义
# ---------------------------------------------------------------------------

# 普通文本里需要转义的 LaTeX 特殊字符。
# 注意：我们只对纯文本段落做转义，不转义 $...$ / $$...$$ / @plot 内部。
_LATEX_ESCAPE_MAP = [
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
]


def latex_escape(s: str) -> str:
    """转义普通文本中的 LaTeX 特殊字符。"""
    # 反斜杠必须先转义，否则会破坏后续转义。
    for ch, rep in _LATEX_ESCAPE_MAP:
        s = s.replace(ch, rep)
    return s


# ---------------------------------------------------------------------------
# @plot 指令解析
# ---------------------------------------------------------------------------

# @plot{ ... }：花括号内可以跨多行，分号 ; 分隔多个绘制项。
# 我们用正则找到 @plot{ 后面到匹配的 }，因为内容里不会再有嵌套花括号
# （label="..." 里的字符串也不会包含 }，简化处理）。
_PLOT_RE = re.compile(r"@plot\{(.*?)\}", re.DOTALL)


def _parse_plot_items(body: str) -> List[PlotItem]:
    """解析 @plot{...} 内部，按 ; 分隔多个绘制项。"""
    items: List[PlotItem] = []
    # 按分号分隔，但要跳过引号内的分号（虽然一般 label 里不会有分号，稳妥起见）。
    parts = []
    buf = []
    in_str = False
    for ch in body:
        if ch == '"':
            in_str = not in_str
            buf.append(ch)
        elif ch == ";" and not in_str:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))

    for raw in parts:
        s = raw.strip()
        if not s:
            continue
        item = _parse_one_plot_item(s)
        items.append(item)
    return items


def _parse_one_plot_item(s: str) -> PlotItem:
    """解析单个绘制项。

    支持两种语法：

    1. 函数曲线（向后兼容）：
        y = sin(x), x in [-pi, pi], label="sin(x)"
        x^2 + y^2 = 1, x in [-2, 2], y in [-2, 2], label="单位圆"

    2. 几何图形（新增）：
        shape=point, at=(1, 2), label="A"
        shape=segment, from=(0, 0), to=(3, 4), label="AB"
        shape=circle, center=(0, 0), r=1, label="C"
        shape=ellipse, center=(0, 0), a=2, b=1, label="E"
        shape=polygon, points=[(0,0), (1,0), (0.5, 1)], label="△"
        shape=rectangle, origin=(0, 0), w=2, h=1, label="R"
        shape=vector, from=(0, 0), to=(2, 1), label="v"
        shape=line, from=(0, 0), to=(3, 4), label="L"

    几何图形的 x in / y in 是可选的（不指定时从图形自动估算）。
    """
    # 拆分时跳过 [...]、(...) 和 "..." 内的逗号。
    segs = []
    buf = []
    in_str = False
    bracket = 0         # [] 计数
    paren = 0           # () 计数
    for ch in s:
        if ch == '"':
            in_str = not in_str
            buf.append(ch)
        elif ch == "[" and not in_str:
            bracket += 1
            buf.append(ch)
        elif ch == "]" and not in_str:
            bracket = max(0, bracket - 1)
            buf.append(ch)
        elif ch == "(" and not in_str:
            paren += 1
            buf.append(ch)
        elif ch == ")" and not in_str:
            paren = max(0, paren - 1)
            buf.append(ch)
        elif ch == "," and not in_str and bracket == 0 and paren == 0:
            segs.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        segs.append("".join(buf).strip())

    if not segs:
        raise PlotParseError(f"空的绘图项：{s!r}")

    first = segs[0]

    # ---------- 分支 1：几何图形 ----------
    m_shape = re.match(r"shape\s*=\s*(\w+)\s*$", first)
    if m_shape:
        return _parse_shape_item(m_shape.group(1), segs[1:], s)

    # ---------- 分支 2：函数曲线 ----------
    expr = first
    x_range = None
    y_range = None
    label = None

    for seg in segs[1:]:
        if not seg:
            continue
        m = re.match(r"x\s+in\s+\[(.*)\]\s*$", seg)
        if m:
            x_range = _parse_range(m.group(1), axis="x")
            continue
        m = re.match(r"y\s+in\s+\[(.*)\]\s*$", seg)
        if m:
            y_range = _parse_range(m.group(1), axis="y")
            continue
        m = re.match(r'label\s*=\s*"(.*)"\s*$', seg)
        if m:
            label = m.group(1)
            continue
        raise PlotParseError(f"无法识别的绘图参数：{seg!r}（在项 {s!r} 中）")

    if x_range is None:
        raise PlotParseError(f"绘图项缺少 x in [...] 定义域：{s!r}")

    # 判定显函数 / 隐函数
    if re.match(r"^\s*y\s*=", expr):
        kind = "explicit"
    elif "=" in expr:
        kind = "implicit"
        if y_range is None:
            raise PlotParseError(
                f"隐函数必须指定 y in [...] 定义域：{s!r}"
            )
    else:
        raise PlotParseError(
            f"无法判定显函数 / 隐函数，缺少 '='：{s!r}"
        )

    return PlotItem(
        kind=kind,
        expr=expr,
        x_range=x_range,
        y_range=y_range,
        label=label,
    )


# 已知几何图形及其必需参数
_SHAPE_SPECS = {
    "point":     {"required": ["at"]},
    "segment":   {"required": ["from", "to"]},
    "line":      {"required": ["from", "to"]},
    "circle":    {"required": ["center", "r"]},
    "ellipse":   {"required": ["center", "a", "b"]},
    "polygon":   {"required": ["points"]},
    "rectangle": {"required": ["origin", "w", "h"]},
    "vector":    {"required": ["from", "to"]},
    "parabola":  {"required": ["vertex", "p"], "optional": ["direction"]},
}


def _parse_shape_item(shape: str, param_segs: list, raw: str) -> PlotItem:
    """解析几何图形项。"""
    shape = shape.lower().strip()
    if shape not in _SHAPE_SPECS:
        raise PlotParseError(
            f"未知几何图形 shape={shape!r}（在项 {raw!r} 中）。"
            f"支持：{', '.join(_SHAPE_SPECS.keys())}"
        )

    params: dict = {}
    label = None
    x_range = None
    y_range = None

    for seg in param_segs:
        if not seg:
            continue
        # x in [...] / y in [...]
        m = re.match(r"x\s+in\s+\[(.*)\]\s*$", seg)
        if m:
            x_range = _parse_range(m.group(1), axis="x")
            continue
        m = re.match(r"y\s+in\s+\[(.*)\]\s*$", seg)
        if m:
            y_range = _parse_range(m.group(1), axis="y")
            continue
        # label="..."
        m = re.match(r'label\s*=\s*"(.*)"\s*$', seg)
        if m:
            label = m.group(1)
            continue
        # key=value 形式的参数
        m = re.match(r"(\w+)\s*=\s*(.+)$", seg)
        if m:
            key = m.group(1).lower()
            val_str = m.group(2).strip()
            params[key] = _parse_shape_value(val_str, key, raw)
            continue
        raise PlotParseError(f"无法识别的几何参数：{seg!r}（在项 {raw!r} 中）")

    # 校验必需参数
    required = _SHAPE_SPECS[shape]["required"]
    for k in required:
        if k not in params:
            raise PlotParseError(
                f"图形 {shape!r} 缺少必需参数 {k!r}（在项 {raw!r} 中）"
            )

    return PlotItem(
        kind="shape",
        shape=shape,
        x_range=x_range,
        y_range=y_range,
        label=label,
        params=params,
    )


def _parse_shape_value(val_str: str, key: str, raw: str):
    """解析几何参数值。

    支持的形式：
        (1, 2)              → tuple[float, float]
        [(0,0), (1,0), ...] → list[tuple[float, float]]
        1.5 / pi / -2       → float
    """
    s = val_str.strip()
    # 点列表：[(x,y), (x,y), ...]
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        # 用正则切分 "),(" 之间的边界
        # 简单做法：逐字符扫描，按顶层逗号切分
        parts = []
        buf = []
        depth = 0
        for ch in inner:
            if ch == "(":
                depth += 1
                buf.append(ch)
            elif ch == ")":
                depth = max(0, depth - 1)
                buf.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(buf).strip())
                buf = []
            else:
                buf.append(ch)
        if buf:
            parts.append("".join(buf).strip())
        pts = []
        for p in parts:
            p = p.strip()
            if not p:
                continue
            pts.append(_parse_point(p, key, raw))
        if not pts:
            raise PlotParseError(f"点列表为空（在项 {raw!r} 中）")
        return pts
    # 单个点：(x, y)
    if s.startswith("(") and s.endswith(")"):
        return _parse_point(s, key, raw)
    # 标量：数字或 pi/e 表达式
    return _eval_scalar(s, axis=key, which=f"参数 {key}")


def _parse_point(s: str, key: str, raw: str) -> Tuple[float, float]:
    """解析 (x, y) 坐标点。"""
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        raise PlotParseError(f"坐标点应为 (x, y) 形式：{s!r}（在项 {raw!r} 中）")
    inner = s[1:-1].strip()
    if "," not in inner:
        raise PlotParseError(f"坐标点缺少逗号：{s!r}（在项 {raw!r} 中）")
    a_str, b_str = inner.split(",", 1)
    x = _eval_scalar(a_str.strip(), axis=key, which=f"点 x 坐标")
    y = _eval_scalar(b_str.strip(), axis=key, which=f"点 y 坐标")
    return (x, y)


def _parse_range(s: str, axis: str):
    """解析 [a, b] 区间，a/b 可以是数字或 pi、e、-pi/2 等简单表达式。

    返回 (float, float)。用 sympy 解析后转 float，安全起见限定符号集。
    """
    s = s.strip()
    # 拆分时只允许最外层一个逗号（区间里不会有嵌套逗号）
    if "," not in s:
        raise PlotParseError(f"区间缺少逗号分隔：[{s}]")
    a_str, b_str = s.split(",", 1)
    a = _eval_scalar(a_str.strip(), axis=axis, which="下界")
    b = _eval_scalar(b_str.strip(), axis=axis, which="上界")
    if not (a < b):
        raise PlotParseError(f"区间下界必须小于上界：[{s}]")
    return (a, b)


def _eval_scalar(s: str, axis: str, which: str) -> float:
    """安全求值：仅允许数字、pi、e、+ - * / ^ 和括号。"""
    # ^ → **，让 Python/sympy 能算
    expr = s.replace("^", "**")
    # 只允许这些字符
    if not re.match(r"^[\d\.\+\-\*\/\(\)\s*pi eE]+$", expr.replace("**", "^")):
        # 上面的正则替换有点 tricky，再用更严格的白名单检查
        pass
    # 严格白名单：允许的 token
    allowed = set("0123456789.+-*/() \t")
    # 把 "pi" 和 "e" 作为整体允许
    cleaned = expr.replace("pi", "").replace("e", "").replace("**", "").replace("E", "")
    if any(ch not in allowed for ch in cleaned):
        raise PlotParseError(
            f"{axis} 区间{which} {s!r} 包含不允许的字符"
        )
    try:
        # 用 sympy 求值，限定局部命名空间
        import sympy as sp
        val = sp.sympify(expr, locals={"pi": sp.pi, "e": sp.E, "E": sp.E})
        return float(val)
    except Exception as ex:
        raise PlotParseError(
            f"{axis} 区间{which} {s!r} 求值失败：{ex}"
        )


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class ParseError(Exception):
    pass


class PlotParseError(ParseError):
    pass


# ---------------------------------------------------------------------------
# 行级解析
# ---------------------------------------------------------------------------

# 内联公式 $...$（非贪婪，单行内匹配）
_INLINE_MATH_RE = re.compile(r"\$([^$\n]+)\$")
# 粗体 **...**
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
# 行内代码 `...`
_CODE_RE = re.compile(r"`([^`]+)`")
# 标题
_HEADING_RE = re.compile(r"^(#{1,2})\s+(.*)$")
# 列表项
_LIST_RE = re.compile(r"^-\s+(.*)$")
# 表格分隔行
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")


def _parse_inline(text: str) -> list:
    """解析一段行内文本，返回 Inline 节点列表。

    顺序：先抽出 $...$ 公式，再处理 **bold**，再处理 `code`。
    """
    # 第一步：把 $...$ 段落抽出来，用占位符替换，避免被转义/被 Bold 拦截。
    placeholders = []
    buf = text
    # 我们用迭代方式扫描
    out: list = []
    i = 0
    while i < len(buf):
        ch = buf[i]
        if ch == "$":
            # 找闭合 $
            j = buf.find("$", i + 1)
            if j == -1:
                # 没闭合，按普通字符处理
                out.append(Text(latex_escape(ch)))
                i += 1
                continue
            latex = buf[i + 1:j]
            out.append(InlineMath(latex))
            i = j + 1
        elif buf.startswith("**", i):
            # 找闭合 **
            j = buf.find("**", i + 2)
            if j == -1:
                out.append(Text(latex_escape("**")))
                i += 2
                continue
            inner = buf[i + 2:j]
            # 递归解析内部（粗体内可以包含公式）
            out.append(Bold(_parse_inline(inner)))
            i = j + 2
        elif ch == "`":
            j = buf.find("`", i + 1)
            if j == -1:
                out.append(Text(latex_escape(ch)))
                i += 1
                continue
            out.append(Code(buf[i + 1:j]))
            i = j + 1
        else:
            # 累积一段普通文本，直到遇到下一个特殊字符
            k = i
            while k < len(buf) and buf[k] not in "$`" and not buf.startswith("**", k):
                k += 1
            chunk = buf[i:k]
            out.append(Text(latex_escape(chunk)))
            i = k
    return out


def _is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def _split_table_row(line: str) -> List[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [cell.strip() for cell in s.split("|")]


# ---------------------------------------------------------------------------
# 主解析入口
# ---------------------------------------------------------------------------

def parse_document(text: str) -> List:
    """解析整篇文档，返回 Block 节点列表。

    会先抽出所有 @plot{...} 块（替换成占位符），然后再按行解析 Markdown，
    最后把占位符还原回 Plot 节点。
    """
    # 第一步：抽出 @plot{...}
    plots: List[Plot] = []
    plot_placeholders: List[str] = []

    def _capture_plot(m: "re.Match[str]") -> str:
        body = m.group(1)
        items = _parse_plot_items(body)
        plot = Plot(items=items)
        plots.append(plot)
        placeholder = f"\x00PLOT{len(plots) - 1}\x00"
        plot_placeholders.append(placeholder)
        return placeholder

    # @plot{...} 必须独占一段；为了让内联出现的 @plot 也能正确识别，
    # 我们在替换的同时在占位符前后插入换行，强制它独占一行。
    def _capture_plot_with_newlines(m: "re.Match[str]") -> str:
        return "\n" + _capture_plot(m) + "\n"

    text2 = _PLOT_RE.sub(_capture_plot_with_newlines, text)

    # 第二步：先把 $$...$$ 块级公式抽出
    display_maths: List[DisplayMath] = []
    def _capture_display(m: "re.Match[str]") -> str:
        latex = m.group(1).strip()
        display_maths.append(DisplayMath(latex=latex))
        return f"\x00DISPLAYMATH{len(display_maths) - 1}\x00"

    # 同样：$$...$$ 可能内联出现，强制独占一行
    def _capture_display_with_newlines(m: "re.Match[str]") -> str:
        return "\n" + _capture_display(m) + "\n"

    text2 = re.sub(r"\$\$(.+?)\$\$", _capture_display_with_newlines, text2, flags=re.DOTALL)

    # 第三步：按行解析
    lines = text2.split("\n")
    blocks: List = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # 空行
        if not line.strip():
            blocks.append(BlankLine())
            i += 1
            continue

        # 块级公式占位符独占一行
        m_dm = re.match(r"^\x00DISPLAYMATH(\d+)\x00$", line.strip())
        if m_dm:
            idx = int(m_dm.group(1))
            blocks.append(display_maths[idx])
            i += 1
            continue

        # @plot 占位符独占一行
        m_pl = re.match(r"^\x00PLOT(\d+)\x00$", line.strip())
        if m_pl:
            idx = int(m_pl.group(1))
            blocks.append(plots[idx])
            i += 1
            continue

        # 标题
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            content = m.group(2).strip()
            blocks.append(Heading(level=level, segments=_parse_inline(content)))
            i += 1
            continue

        # 列表项（连续的 - 开头行视为一个列表，这里简化为逐行 ListItem）
        m = _LIST_RE.match(line)
        if m:
            content = m.group(1).strip()
            blocks.append(ListItem(segments=_parse_inline(content)))
            i += 1
            continue

        # 表格
        if _is_table_row(line):
            # 收集连续表格行
            tbl_lines = []
            while i < n and _is_table_row(lines[i]):
                tbl_lines.append(lines[i])
                i += 1
            table = _parse_table(tbl_lines)
            blocks.append(table)
            continue

        # 普通段落：连续非空、非特殊行合并成一段
        para_buf = [line]
        i += 1
        while i < n:
            nxt = lines[i]
            if (
                not nxt.strip()
                or _HEADING_RE.match(nxt)
                or _LIST_RE.match(nxt)
                or _is_table_row(nxt)
                or re.match(r"^\x00DISPLAYMATH(\d+)\x00$", nxt.strip())
                or re.match(r"^\x00PLOT(\d+)\x00$", nxt.strip())
            ):
                break
            para_buf.append(nxt)
            i += 1
        para_text = " ".join(p.strip() for p in para_buf)
        blocks.append(Paragraph(segments=_parse_inline(para_text)))

    return blocks


def _parse_table(tbl_lines: List[str]) -> Table:
    """解析 Markdown 表格。第一行是表头，第二行是分隔行 |---|---|，其余是数据行。"""
    if len(tbl_lines) < 2:
        raise ParseError(f"表格行数不足：{tbl_lines}")
    header_cells = _split_table_row(tbl_lines[0])
    header = [_parse_inline(c) for c in header_cells]
    if not _TABLE_SEP_RE.match(tbl_lines[1]):
        raise ParseError(
            f"表格第二行应为分隔行 |---|---|，实际为：{tbl_lines[1]!r}"
        )
    rows = []
    for ln in tbl_lines[2:]:
        cells = _split_table_row(ln)
        # 列数对齐
        while len(cells) < len(header_cells):
            cells.append("")
        cells = cells[: len(header_cells)]
        rows.append([_parse_inline(c) for c in cells])
    return Table(header=header, rows=rows)

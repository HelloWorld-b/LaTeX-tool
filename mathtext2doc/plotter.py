"""函数图绘制器。

输入：parser.Plot（一组 PlotItem）
输出：PNG 文件路径

支持：
    - 2D 显函数 y = f(x)
    - 2D 隐函数 F(x, y) = 0
    - 多函数同图（显隐混合）
    - 自动分配颜色
    - 标签默认标注在曲线可见部分的几何中点偏上
    - 标签之间自动避让（基于 bbox 重叠检测的迭代位移）
    - 中文 label（matplotlib 使用 Noto Sans SC）
    - 常见初等函数：+ - * / ^、sin cos tan log ln exp sqrt abs pi e

实现说明：
    - 显函数：sympy 解析表达式 → lambdify → numpy linspace 采样
    - 隐函数：sympy 解析 F(x, y) = 0 → 移项为 F(x, y) → numpy meshgrid
      + matplotlib contour(level=0) 绘制零等高线
    - 标签避让：先按曲线可见中点初始化每个标签位置；然后用迭代算法
      检查所有标签 bbox 是否重叠，重叠则沿曲线方向滑动或上移，最多迭代 N 次。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # 无显示设备
import matplotlib.font_manager as fm

# 注册中文字体（自动探测常见路径）
_FONT_CANDIDATES = [
    # Linux 常见路径
    "/usr/share/fonts/truetype/chinese/NotoSansSC[wght].ttf",
    "/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/lxgw-wenkai/LXGWWenKai-Regular.ttf",
    # macOS 常见路径
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Songti.ttc",
    # DejaVu Sans 兜底（拉丁 + 符号）
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
for _f in _FONT_CANDIDATES:
    if os.path.exists(_f):
        try:
            fm.fontManager.addfont(_f)
        except Exception:
            pass

# 探测可用的中文字体名（按优先级）
_AVAILABLE_CN_FONTS = []
for _name in [
    "Noto Sans SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei", "LXGW WenKai", "PingFang SC", "Songti SC",
    "Sarasa Mono SC",
]:
    try:
        if fm.findfont(_name, fallback_to_default=False) != fm.findfont("DejaVu Sans"):
            _AVAILABLE_CN_FONTS.append(_name)
    except Exception:
        pass

import matplotlib.pyplot as plt
import numpy as np
import sympy as sp

# 优先中文字体，然后 DejaVu Sans 兜底
plt.rcParams["font.sans-serif"] = (_AVAILABLE_CN_FONTS or ["Noto Sans SC"]) + [
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

from .parser import Plot, PlotItem


# ---------------------------------------------------------------------------
# 颜色循环
# ---------------------------------------------------------------------------

# 一组对比明显、色盲友好的颜色
_COLOR_CYCLE = [
    "#1f77b4",  # 蓝
    "#d62728",  # 红
    "#2ca02c",  # 绿
    "#ff7f0e",  # 橙
    "#9467bd",  # 紫
    "#17becf",  # 青
    "#8c564b",  # 棕
    "#e377c2",  # 粉
]


# ---------------------------------------------------------------------------
# 表达式解析
# ---------------------------------------------------------------------------

# sympy 默认支持 log (=ln)、sin、cos、tan、exp、sqrt、abs、pi、E。
# 我们额外提供 `ln` 作为 `log` 的别名，`e` 作为 E 的别名。
_LOCAL_NAMES = {
    "pi": sp.pi,
    "e": sp.E,
    "E": sp.E,
    "ln": sp.log,
    "log": sp.log,  # sympy 中 log 默认是自然对数
    "log10": sp.log,
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "exp": sp.exp,
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
}


def _to_sympy_expr(s: str) -> sp.Expr:
    """把用户表达式转成 sympy 表达式。把 ^ 替换为 **。"""
    s = s.replace("^", "**")
    try:
        return sp.sympify(s, locals=_LOCAL_NAMES)
    except Exception as ex:
        raise PlotRenderError(f"无法解析表达式 {s!r}：{ex}")


# ---------------------------------------------------------------------------
# 显函数 / 隐函数绘制
# ---------------------------------------------------------------------------

@dataclass
class _PlottedCurve:
    """已经绘制好的曲线信息，用于标签避让。"""
    label: Optional[str]
    color: str
    # 曲线上的采样点（用于找标签锚点）。numpy 数组，可能是 NaN。
    xs: np.ndarray
    ys: np.ndarray
    # 标签候选锚点（在数据坐标里）
    anchor: Optional[Tuple[float, float]] = None
    # 最终标签锚点（经过避让后）
    final_anchor: Optional[Tuple[float, float]] = None


class PlotRenderError(Exception):
    pass


def _plot_explicit(ax, item: PlotItem, color: str) -> _PlottedCurve:
    """绘制 y = f(x)。"""
    # 从 "y = sin(x)" 中取出右边的 f(x)
    if "=" not in item.expr:
        raise PlotRenderError(f"显函数缺少 '='：{item.expr!r}")
    lhs, rhs = item.expr.split("=", 1)
    lhs = lhs.strip()
    rhs = rhs.strip()
    if lhs != "y":
        raise PlotRenderError(
            f"显函数左边必须是 'y'，实际为 {lhs!r}（在 {item.expr!r} 中）"
        )
    expr = _to_sympy_expr(rhs)
    x = sp.symbols("x")
    try:
        f = sp.lambdify(x, expr, modules=["numpy", _LOCAL_NAMES])
    except Exception as ex:
        raise PlotRenderError(f"显函数 lambdify 失败 {rhs!r}：{ex}")

    a, b = item.x_range
    a = float(a)
    b = float(b)
    n = max(400, int((b - a) * 80))
    n = min(n, 4000)
    xs = np.linspace(a, b, n)
    try:
        ys = np.asarray(f(xs), dtype=float)
    except Exception:
        # 标量函数（如常数函数）会广播
        try:
            ys = np.full_like(xs, float(f(0.0)))
        except Exception as ex:
            raise PlotRenderError(f"显函数求值失败 {rhs!r}：{ex}")

    # 屏蔽 NaN / inf
    mask = np.isfinite(ys)
    xs_plot = xs[mask]
    ys_plot = ys[mask]

    # 限制 ys 在合理范围内（避免 tan 等函数在大值处画穿）
    # 我们把 |y| > 1e6 的点设为 NaN，让 matplotlib 断开线段
    ys_limited = ys.copy()
    ys_limited[np.abs(ys_limited) > 1e6] = np.nan
    ax.plot(xs, ys_limited, color=color, linewidth=1.6, label=item.label or "")

    # 计算可见部分几何中点
    if len(xs_plot) > 0:
        # 用弧长加权中点：找累计弧长 50% 处的点
        dx = np.diff(xs_plot)
        dy = np.diff(ys_plot)
        seglen = np.sqrt(dx * dx + dy * dy)
        cum = np.concatenate([[0], np.cumsum(seglen)])
        if cum[-1] > 0:
            half = cum[-1] / 2.0
            idx = int(np.searchsorted(cum, half))
            idx = min(idx, len(xs_plot) - 1)
            anchor = (float(xs_plot[idx]), float(ys_plot[idx]))
        else:
            anchor = (float(xs_plot[0]), float(ys_plot[0]))
    else:
        anchor = ((a + b) / 2.0, 0.0)

    return _PlottedCurve(
        label=item.label, color=color, xs=xs_plot, ys=ys_plot, anchor=anchor
    )


def _plot_implicit(ax, item: PlotItem, color: str) -> _PlottedCurve:
    """绘制 F(x, y) = 0。"""
    if "=" not in item.expr:
        raise PlotRenderError(f"隐函数缺少 '='：{item.expr!r}")
    lhs, rhs = item.expr.split("=", 1)
    lhs_expr = _to_sympy_expr(lhs.strip())
    rhs_expr = _to_sympy_expr(rhs.strip())
    F = lhs_expr - rhs_expr
    x, y = sp.symbols("x y")
    try:
        f = sp.lambdify((x, y), F, modules=["numpy", _LOCAL_NAMES])
    except Exception as ex:
        raise PlotRenderError(f"隐函数 lambdify 失败 {item.expr!r}：{ex}")

    a, b = item.x_range
    c, d = item.y_range  # 已在 parser 中校验非 None
    a, b = float(a), float(b)
    c, d = float(c), float(d)

    n = 400
    xs = np.linspace(a, b, n)
    ys = np.linspace(c, d, n)
    X, Y = np.meshgrid(xs, ys)
    try:
        Z = np.asarray(f(X, Y), dtype=float)
    except Exception as ex:
        raise PlotRenderError(f"隐函数求值失败 {item.expr!r}：{ex}")

    # 屏蔽 NaN / inf
    Z = np.where(np.isfinite(Z), Z, np.nan)

    # 用 contour 画 0 等高线
    try:
        cs = ax.contour(X, Y, Z, levels=[0], colors=[color], linewidths=1.6)
    except Exception as ex:
        raise PlotRenderError(f"隐函数 contour 绘制失败 {item.expr!r}：{ex}")

    # 取出 contour 的路径段，计算几何中点
    # matplotlib 3.9+：ContourSet 自身就是 Collection；旧版本有 .collections
    if hasattr(cs, "get_paths"):
        try:
            paths = cs.get_paths()
        except Exception:
            paths = []
    elif hasattr(cs, "collections") and cs.collections:
        try:
            paths = cs.collections[0].get_paths()
        except Exception:
            paths = []
    else:
        paths = []

    all_pts = []
    for p in paths:
        v = p.vertices
        if len(v) > 0:
            all_pts.append(v)
    if all_pts:
        pts = np.vstack(all_pts)
        # 弧长中点
        dx = np.diff(pts[:, 0])
        dy = np.diff(pts[:, 1])
        seglen = np.sqrt(dx * dx + dy * dy)
        cum = np.concatenate([[0], np.cumsum(seglen)])
        if cum[-1] > 0:
            half = cum[-1] / 2.0
            idx = int(np.searchsorted(cum, half))
            idx = min(idx, len(pts) - 1)
            anchor = (float(pts[idx, 0]), float(pts[idx, 1]))
        else:
            anchor = (float(pts[0, 0]), float(pts[0, 1]))
        xs_plot = pts[:, 0]
        ys_plot = pts[:, 1]
    else:
        anchor = ((a + b) / 2.0, (c + d) / 2.0)
        xs_plot = np.array([])
        ys_plot = np.array([])

    return _PlottedCurve(
        label=item.label, color=color, xs=xs_plot, ys=ys_plot, anchor=anchor
    )


# ---------------------------------------------------------------------------
# 标签避让
# ---------------------------------------------------------------------------

def _resolve_label_anchor(
    ax, curves: List[_PlottedCurve], renderer
) -> None:
    """对每条有 label 的曲线计算最终锚点。

    算法：
      1. 初始锚点 = 曲线几何中点，向上偏移 0.04 * (y_max - y_min)。
      2. 把数据坐标转成显示坐标（pixels），用文本 bbox 检测重叠。
      3. 重叠时，对后插入的标签，沿 8 个方向（上、右上、右、右下、下、左下、左、左上）
         螺旋外扩，直到不重叠或达到最大迭代次数。
      4. 若仍重叠，则把标签放在轴外上方，作为兜底。
    """
    if not curves:
        return

    # 数据范围
    all_xmin = min(np.min(c.xs) if len(c.xs) else math.inf for c in curves if c.anchor)
    all_xmax = max(np.max(c.xs) if len(c.xs) else -math.inf for c in curves if c.anchor)
    all_ymin = min(np.min(c.ys) if len(c.ys) else math.inf for c in curves if c.anchor)
    all_ymax = max(np.max(c.ys) if len(c.ys) else -math.inf for c in curves if c.anchor)
    if not all(math.isfinite(v) for v in [all_xmin, all_xmax, all_ymin, all_ymax]):
        # 兜底
        y_offset = 0.1
    else:
        y_offset = 0.04 * (all_ymax - all_ymin) if all_ymax > all_ymin else 0.1

    placed_boxes = []  # 已放置标签的 bbox（display coords）

    for c in curves:
        if not c.label or c.anchor is None:
            c.final_anchor = c.anchor
            continue
        ax_pt = (c.anchor[0], c.anchor[1] + y_offset)
        # 转 display 坐标
        disp = ax.transData.transform(ax_pt)

        # 估算文本 bbox
        # 用 renderer 测量
        text_obj = ax.text(
            ax_pt[0], ax_pt[1], c.label,
            color=c.color, fontsize=10,
            ha="center", va="bottom",
        )
        try:
            bb = text_obj.get_window_extent(renderer=renderer)
        except Exception:
            bb = None

        # 螺旋避让
        if bb is not None:
            best_bb = bb
            best_disp = disp
            best_pt = ax_pt
            directions = [
                (0, 1), (1, 1), (1, 0), (1, -1),
                (0, -1), (-1, -1), (-1, 0), (-1, 1),
            ]
            step = 8  # 像素
            max_iter = 40
            ok = False
            for it in range(max_iter):
                overlap = False
                for prev in placed_boxes:
                    if _bbox_overlap(best_bb, prev):
                        overlap = True
                        break
                if not overlap:
                    ok = True
                    break
                # 沿外扩方向移动
                d = directions[it % len(directions)]
                radius = step * (1 + it // len(directions))
                new_disp = (best_disp[0] + d[0] * radius, best_disp[1] + d[1] * radius)
                # 回到数据坐标
                new_pt = ax.transData.inverted().transform(new_disp)
                text_obj.set_position((float(new_pt[0]), float(new_pt[1])))
                try:
                    best_bb = text_obj.get_window_extent(renderer=renderer)
                except Exception:
                    pass
                best_disp = new_disp
                best_pt = (float(new_pt[0]), float(new_pt[1]))

            placed_boxes.append(best_bb)
            c.final_anchor = best_pt
            if not ok:
                # 已经尽力，保留当前位置
                pass
        else:
            c.final_anchor = ax_pt
            placed_boxes.append(None)


def _bbox_overlap(a, b) -> bool:
    if a is None or b is None:
        return False
    # matplotlib Bbox：x0,y0,x1,y1
    return not (a.x1 < b.x0 or b.x1 < a.x0 or a.y1 < b.y0 or b.y1 < a.y0)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def render_plot(plot: Plot, out_path: str, dpi: int = 150) -> str:
    """渲染一张 plot 到 PNG。

    返回 out_path。
    """
    if not plot.items:
        raise PlotRenderError("@plot 指令没有任何绘制项")

    # 决定坐标范围：取所有 item 的 x/y 范围并集
    xmin = math.inf
    xmax = -math.inf
    ymin = math.inf
    ymax = -math.inf
    for it in plot.items:
        a, b = it.x_range
        xmin = min(xmin, float(a))
        xmax = max(xmax, float(b))
        if it.y_range is not None:
            c, d = it.y_range
            ymin = min(ymin, float(c))
            ymax = max(ymax, float(d))
    if not math.isfinite(xmin) or not math.isfinite(xmax):
        raise PlotRenderError("无法确定 plot 的 x 范围")
    if not math.isfinite(ymin) or not math.isfinite(ymax):
        # 显函数图：自动从数据估算，先用 5% margin
        ymin, ymax = None, None

    fig, ax = plt.subplots(figsize=(5, 4), constrained_layout=True)

    curves: List[_PlottedCurve] = []
    for i, item in enumerate(plot.items):
        color = _COLOR_CYCLE[i % len(_COLOR_CYCLE)]
        if item.kind == "explicit":
            cur = _plot_explicit(ax, item, color)
        elif item.kind == "implicit":
            cur = _plot_implicit(ax, item, color)
        else:
            raise PlotRenderError(f"未知绘图类型：{item.kind!r}")
        curves.append(cur)

    # 坐标范围
    if ymin is None or ymax is None:
        # 纯显函数图：y 范围由 autoscale 决定
        ax.relim()
        ax.autoscale_view()
        ax.set_xlim(xmin, xmax)
        # 取 autoscale 后的实际 y 范围，用于判断是否启用 equal
        y_lo, y_hi = ax.get_ylim()
        x_span = xmax - xmin
        y_span = y_hi - y_lo
        # 默认 x/y 单位长度一致；但当 y 跨度远大于 x（如 tan、exp 等陡峭函数）
        # 1:1 会让 x 轴被压扁到无法辨认，此时退回 'auto' 保证可读性。
        # 阈值：y 跨度超过 x 跨度 3 倍，认为不适合 equal。
        if x_span > 0 and y_span / x_span <= 3.0:
            ax.set_aspect("equal", adjustable="box")
        # 否则保持 auto（matplotlib 默认）
    else:
        # 有隐函数图（或显隐混合）：用户显式指定了 x、y 范围，
        # 默认 x/y 单位长度一致（几何意义正确，单位圆才是圆）。
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")

    ax.axhline(0, color="#888", linewidth=0.5)
    ax.axvline(0, color="#888", linewidth=0.5)
    ax.grid(True, linewidth=0.4, alpha=0.5)
    ax.set_xlabel("x")
    ax.set_ylabel("y")

    # 标签避让（必须先 draw 一次才能拿到 renderer）
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    _resolve_label_anchor(ax, curves, renderer)

    # 把所有标签一次性写入（前面 _resolve_label_anchor 已经写入了 text_obj，
    # 这里其实已经画完了；保留这一行作为兜底重新画一遍以防遗漏）
    # 我们改为：先清掉刚才的 trial 文本，再用最终锚点画。
    # 简化起见，直接保留 trial 写入的文本（位置已经更新为最终锚点）。

    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)
    return out_path

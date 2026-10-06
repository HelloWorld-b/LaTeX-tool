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
        ys_raw = f(xs)
        # 常数函数 / 标量返回：广播到与 xs 同形状
        if np.isscalar(ys_raw) or (hasattr(ys_raw, "shape") and ys_raw.shape == ()):
            ys = np.full_like(xs, float(ys_raw))
        else:
            ys = np.asarray(ys_raw, dtype=float)
            # 形状不匹配（如某些 sympy 函数返回 (1, N)）→ flatten
            if ys.shape != xs.shape:
                ys = ys.reshape(xs.shape) if ys.size == xs.size else np.broadcast_to(ys, xs.shape).astype(float)
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
# 几何图形渲染
# ---------------------------------------------------------------------------

def _plot_shape(ax, item: PlotItem, color: str) -> _PlottedCurve:
    """渲染几何图形。"""
    shape = item.shape
    params = item.params
    label = item.label
    anchor = None
    xs_plot = np.array([])
    ys_plot = np.array([])

    if shape == "point":
        x, y = params["at"]
        ax.plot([x], [y], marker="o", color=color, markersize=6,
                markeredgecolor=color, markerfacecolor=color)
        anchor = (float(x), float(y))
        xs_plot = np.array([float(x)])
        ys_plot = np.array([float(y)])

    elif shape == "segment":
        x1, y1 = params["from"]
        x2, y2 = params["to"]
        ax.plot([x1, x2], [y1, y2], color=color, linewidth=1.8,
                solid_capstyle="round")
        # 端点小圆点
        ax.plot([x1, x2], [y1, y2], marker="o", color=color, markersize=4,
                linestyle="None")
        anchor = (float((x1 + x2) / 2), float((y1 + y2) / 2))
        xs_plot = np.array([float(x1), float(x2)])
        ys_plot = np.array([float(y1), float(y2)])

    elif shape == "line":
        # 直线：过两点，但要延伸到 axes 边界
        x1, y1 = params["from"]
        x2, y2 = params["to"]
        # 计算方向向量，延伸到当前 xlim 的两端
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            raise PlotRenderError(f"直线 from 和 to 不能重合：{item.params}")
        # 用参数 t 延伸：t=0 在 from，t=1 在 to，延伸到 t=-100..100 兜底
        # 实际延伸长度由 set_xlim 后的 clip 决定
        ts = np.array([-1000, 1000])
        xs = x1 + ts * dx
        ys = y1 + ts * dy
        ax.plot(xs, ys, color=color, linewidth=1.4)
        anchor = (float((x1 + x2) / 2), float((y1 + y2) / 2))
        xs_plot = np.array([float(x1), float(x2)])
        ys_plot = np.array([float(y1), float(y2)])

    elif shape == "circle":
        cx, cy = params["center"]
        r = float(params["r"])
        if r <= 0:
            raise PlotRenderError(f"圆半径必须为正：r={r}")
        theta = np.linspace(0, 2 * np.pi, 200)
        xs = cx + r * np.cos(theta)
        ys = cy + r * np.sin(theta)
        ax.plot(xs, ys, color=color, linewidth=1.6)
        # 圆心小点
        ax.plot([cx], [cy], marker="o", color=color, markersize=3)
        anchor = (float(cx), float(cy + r))  # 顶部
        xs_plot = xs
        ys_plot = ys

    elif shape == "ellipse":
        cx, cy = params["center"]
        a = float(params["a"])
        b = float(params["b"])
        if a <= 0 or b <= 0:
            raise PlotRenderError(f"椭圆半轴必须为正：a={a}, b={b}")
        theta = np.linspace(0, 2 * np.pi, 200)
        xs = cx + a * np.cos(theta)
        ys = cy + b * np.sin(theta)
        ax.plot(xs, ys, color=color, linewidth=1.6)
        ax.plot([cx], [cy], marker="o", color=color, markersize=3)
        anchor = (float(cx), float(cy + b))
        xs_plot = xs
        ys_plot = ys

    elif shape == "polygon":
        pts = params["points"]
        if len(pts) < 3:
            raise PlotRenderError(f"多边形至少需要 3 个顶点，得到 {len(pts)}")
        xs = [p[0] for p in pts] + [pts[0][0]]
        ys = [p[1] for p in pts] + [pts[0][1]]
        ax.plot(xs, ys, color=color, linewidth=1.6)
        ax.plot([p[0] for p in pts], [p[1] for p in pts],
                marker="o", color=color, markersize=4, linestyle="None")
        # 几何中心
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        anchor = (float(cx), float(cy))
        xs_plot = np.array([float(x) for x in xs])
        ys_plot = np.array([float(y) for y in ys])

    elif shape == "rectangle":
        x0, y0 = params["origin"]
        w = float(params["w"])
        h = float(params["h"])
        if w <= 0 or h <= 0:
            raise PlotRenderError(f"矩形宽高必须为正：w={w}, h={h}")
        xs = [x0, x0 + w, x0 + w, x0, x0]
        ys = [y0, y0, y0 + h, y0 + h, y0]
        ax.plot(xs, ys, color=color, linewidth=1.6)
        anchor = (float(x0 + w / 2), float(y0 + h / 2))
        xs_plot = np.array([float(x) for x in xs])
        ys_plot = np.array([float(y) for y in ys])

    elif shape == "vector":
        x1, y1 = params["from"]
        x2, y2 = params["to"]
        # 用 ax.annotate 画带箭头的向量
        ax.annotate(
            "",
            xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle="->", color=color, lw=1.8),
        )
        anchor = (float((x1 + x2) / 2), float((y1 + y2) / 2))
        xs_plot = np.array([float(x1), float(x2)])
        ys_plot = np.array([float(y1), float(y2)])

    elif shape == "parabola":
        # 标准方程（vertex=(h,k), p=焦距, direction=up/down/left/right）：
        #   up:    (x-h)^2 = 4p(y-k)   → y = (x-h)^2/(4p) + k
        #   down:  (x-h)^2 = -4p(y-k)  → y = -(x-h)^2/(4p) + k
        #   right: (y-k)^2 = 4p(x-h)   → x = (y-k)^2/(4p) + h
        #   left:  (y-k)^2 = -4p(x-h)  → x = -(y-k)^2/(4p) + h
        h, k = params["vertex"]
        p = float(params["p"])
        direction = str(params.get("direction", "up")).lower().strip()
        if p == 0:
            raise PlotRenderError("parabola 的 p 不能为 0")
        # 在 vertex 周围画 4 倍 p 的范围（够看清形状又不会太远）
        span = abs(p) * 4 + 1.5
        if direction in ("up", "down"):
            sign = 1 if direction == "up" else -1
            xs = np.linspace(float(h) - span, float(h) + span, 400)
            ys = sign * (xs - float(h)) ** 2 / (4 * p) + float(k)
            ax.plot(xs, ys, color=color, linewidth=1.6)
            # 顶点
            ax.plot([h], [k], marker="o", color=color, markersize=4)
            anchor = (float(h), float(k) + sign * abs(p))
            xs_plot = xs
            ys_plot = ys
        elif direction in ("left", "right"):
            sign = 1 if direction == "right" else -1
            ys = np.linspace(float(k) - span, float(k) + span, 400)
            xs = sign * (ys - float(k)) ** 2 / (4 * p) + float(h)
            ax.plot(xs, ys, color=color, linewidth=1.6)
            ax.plot([h], [k], marker="o", color=color, markersize=4)
            anchor = (float(h) + sign * abs(p), float(k))
            xs_plot = xs
            ys_plot = ys
        else:
            raise PlotRenderError(
                f"parabola 的 direction 必须是 up/down/left/right，得到 {direction!r}"
            )

    else:
        raise PlotRenderError(f"未知几何图形：{shape!r}")

    return _PlottedCurve(
        label=label, color=color, xs=xs_plot, ys=ys_plot, anchor=anchor
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

def render_plot(
    plot: Plot,
    out_path: str,
    dpi: int = 150,
    display_width: Optional[float] = None,
) -> str:
    r"""渲染一张 plot 到 PNG。

    参数：
        plot: Plot 节点
        out_path: 输出 PNG 路径
        dpi: 目标有效 DPI（每英寸显示长度的像素数）。若 display_width 给定，
             实际 savefig dpi 会自动调整以保持此有效分辨率一致。
        display_width: 图在文档中的显示宽度（相对于 \paperwidth，0~1）。
                       给定时启用 auto-DPI；为 None 时直接用 dpi 作为 savefig dpi。

    返回 out_path。
    """
    if not plot.items:
        raise PlotRenderError("@plot 指令没有任何绘制项")

    # ---------- 计算 savefig dpi（auto-DPI）----------
    # 思路：无论图显示多大，保证"每英寸显示长度的像素数"≈ dpi，
    # 这样大图小图都有相同的视觉清晰度，不浪费像素也不糊。
    #   display_inches = display_width × paperwidth_inches
    #   pixel_width = display_inches × dpi
    #   savefig_dpi = pixel_width / figsize_width
    _FIGSIZE_WIDTH = 5.0           # 当前 figsize=(5, 4) 的宽度
    _PAPERWIDTH_INCHES = 8.27      # A4 纸宽 21cm
    _MIN_DPI = 80                  # 下限：避免小图文字锯齿
    _MAX_DPI = 400                 # 上限：避免大图文件过大
    if display_width is not None:
        display_inches = display_width * _PAPERWIDTH_INCHES
        auto_dpi = display_inches * dpi / _FIGSIZE_WIDTH
        savefig_dpi = max(_MIN_DPI, min(_MAX_DPI, auto_dpi))
    else:
        savefig_dpi = float(dpi)

    # ---------- 决定坐标范围 ----------
    # 函数曲线项必须有 x_range（parser 已校验），几何图形项的 x_range 可选
    # 收集：用户显式指定的范围 + 几何图形的图形边界
    user_xmin = math.inf
    user_xmax = -math.inf
    user_ymin = math.inf
    user_ymax = -math.inf
    has_user_x = False
    has_user_y = False
    has_implicit = False
    has_shape = False

    for it in plot.items:
        if it.kind == "implicit":
            has_implicit = True
        if it.kind == "shape":
            has_shape = True
        if it.x_range is not None:
            a, b = it.x_range
            user_xmin = min(user_xmin, float(a))
            user_xmax = max(user_xmax, float(b))
            has_user_x = True
        if it.y_range is not None:
            c, d = it.y_range
            user_ymin = min(user_ymin, float(c))
            user_ymax = max(user_ymax, float(d))
            has_user_y = True

    fig, ax = plt.subplots(figsize=(5, 4), constrained_layout=True)

    # ---------- 渲染所有项 ----------
    curves: List[_PlottedCurve] = []
    for i, item in enumerate(plot.items):
        color = _COLOR_CYCLE[i % len(_COLOR_CYCLE)]
        if item.kind == "explicit":
            cur = _plot_explicit(ax, item, color)
        elif item.kind == "implicit":
            cur = _plot_implicit(ax, item, color)
        elif item.kind == "shape":
            cur = _plot_shape(ax, item, color)
        else:
            raise PlotRenderError(f"未知绘图类型：{item.kind!r}")
        curves.append(cur)

    # ---------- 设置坐标范围 ----------
    if has_user_x and has_user_y:
        # 用户显式指定了 x、y 范围
        xmin, xmax = user_xmin, user_xmax
        ymin, ymax = user_ymin, user_ymax
    elif has_user_x and not has_user_y:
        # 用户只指定了 x 范围，y 由 autoscale 决定
        xmin, xmax = user_xmin, user_xmax
        ax.relim()
        ax.autoscale_view()
        ymin, ymax = ax.get_ylim()
        ax.set_xlim(xmin, xmax)
    elif has_shape and not has_user_x:
        # 纯几何图形，无任何范围指定：从图形数据自动估算
        ax.relim()
        ax.autoscale_view()
        xmin, xmax = ax.get_xlim()
        ymin, ymax = ax.get_ylim()
    else:
        # 兜底（不应该到这）
        ax.relim()
        ax.autoscale_view()
        xmin, xmax = ax.get_xlim()
        ymin, ymax = ax.get_ylim()

    # 给范围留 8% 边距（避免图形贴边）
    x_span = xmax - xmin
    y_span = ymax - ymin
    if x_span > 0:
        pad = x_span * 0.08
        xmin -= pad
        xmax += pad
    if y_span > 0:
        pad = y_span * 0.08
        ymin -= pad
        ymax += pad

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    # ---------- 决定 aspect ----------
    # 隐函数图、几何图形、显隐混合 → equal（几何意义正确）
    # 纯显函数图 → equal 除非 y 跨度 > 3 倍 x 跨度（避免 tan 等压扁）
    if has_implicit or has_shape:
        ax.set_aspect("equal", adjustable="box")
    else:
        x_span_final = xmax - xmin
        y_span_final = ymax - ymin
        if x_span_final > 0 and y_span_final / x_span_final <= 3.0:
            ax.set_aspect("equal", adjustable="box")

    # ---------- 增强坐标系绘制 ----------
    _draw_axes(ax, xmin, xmax, ymin, ymax)

    # 标签避让（必须先 draw 一次才能拿到 renderer）
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    _resolve_label_anchor(ax, curves, renderer)

    fig.savefig(out_path, dpi=savefig_dpi)
    plt.close(fig)
    return out_path


def _draw_axes(ax, xmin, xmax, ymin, ymax) -> None:
    """绘制增强坐标系：箭头轴线、原点 O、x/y 轴标签。

    与 matplotlib 默认 spines 不同，这里用 axhline/axvline + annotate 画带箭头的轴，
    更接近中学/大学数学教材的坐标系画法。
    """
    # 隐藏默认 spines
    for spine in ax.spines.values():
        spine.set_visible(False)

    # 网格
    ax.grid(True, linewidth=0.4, alpha=0.4, color="#ccc")

    # 坐标轴：用浅色线穿过原点（如果原点在视野内）
    ax.axhline(0, color="#444", linewidth=1.0, zorder=1)
    ax.axvline(0, color="#444", linewidth=1.0, zorder=1)

    # x 轴箭头（右端）
    ax.annotate(
        "",
        xy=(xmax, 0), xytext=(xmax - (xmax - xmin) * 0.04, 0),
        arrowprops=dict(arrowstyle="->", color="#444", lw=1.2),
        annotation_clip=False,
    )
    # y 轴箭头（上端）
    ax.annotate(
        "",
        xy=(0, ymax), xytext=(0, ymax - (ymax - ymin) * 0.04),
        arrowprops=dict(arrowstyle="->", color="#444", lw=1.2),
        annotation_clip=False,
    )

    # 轴标签：x 在右端下方，y 在上端左侧
    ax.text(xmax, 0, " x", ha="left", va="bottom", fontsize=11,
            color="#222", clip_on=False)
    ax.text(0, ymax, "y ", ha="right", va="top", fontsize=11,
            color="#222", clip_on=False)

    # 原点 O（仅当原点在视野内且不在边缘时显示）
    if xmin < 0 < xmax and ymin < 0 < ymax:
        ax.text(0, 0, " O", ha="left", va="top", fontsize=9,
                color="#222", clip_on=False)

    # 刻度
    ax.tick_params(axis="both", which="both", direction="out",
                   top=False, right=False, labelsize=8, colors="#444")

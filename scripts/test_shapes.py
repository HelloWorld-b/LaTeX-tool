"""测试几何图形渲染：8 种 shape + 增强坐标系。"""
import sys, os
sys.path.insert(0, "/home/z/my-project")
from mathtext2doc.parser import Plot, PlotItem
from mathtext2doc.plotter import render_plot, PlotRenderError

os.makedirs("/tmp/shape_test", exist_ok=True)

cases = [
    # 1. 单点
    ("01_point", Plot(items=[
        PlotItem(kind="shape", shape="point", params={"at": (1, 2)},
                 x_range=(-1, 3), y_range=(-1, 3), label="A"),
    ])),
    # 2. 线段
    ("02_segment", Plot(items=[
        PlotItem(kind="shape", shape="segment",
                 params={"from": (0, 0), "to": (3, 2)},
                 x_range=(-1, 4), y_range=(-1, 3), label="AB"),
    ])),
    # 3. 直线（延伸）
    ("03_line", Plot(items=[
        PlotItem(kind="shape", shape="line",
                 params={"from": (0, 0), "to": (1, 1)},
                 x_range=(-3, 3), y_range=(-3, 3), label="y=x"),
    ])),
    # 4. 圆
    ("04_circle", Plot(items=[
        PlotItem(kind="shape", shape="circle",
                 params={"center": (1, 1), "r": 2},
                 x_range=(-2, 4), y_range=(-2, 4), label="圆"),
    ])),
    # 5. 椭圆
    ("05_ellipse", Plot(items=[
        PlotItem(kind="shape", shape="ellipse",
                 params={"center": (0, 0), "a": 3, "b": 1},
                 x_range=(-4, 4), y_range=(-2, 2), label="椭圆"),
    ])),
    # 6. 多边形（三角形）
    ("06_triangle", Plot(items=[
        PlotItem(kind="shape", shape="polygon",
                 params={"points": [(0, 0), (2, 0), (1, 1.5)]},
                 x_range=(-1, 3), y_range=(-1, 2), label="△"),
    ])),
    # 7. 矩形
    ("07_rectangle", Plot(items=[
        PlotItem(kind="shape", shape="rectangle",
                 params={"origin": (0, 0), "w": 3, "h": 2},
                 x_range=(-1, 4), y_range=(-1, 3), label="矩形"),
    ])),
    # 8. 向量
    ("08_vector", Plot(items=[
        PlotItem(kind="shape", shape="vector",
                 params={"from": (0, 0), "to": (2, 1)},
                 x_range=(-1, 3), y_range=(-1, 2), label="v"),
    ])),
    # 9. 混合：圆 + 点 + 向量 + 函数
    ("09_mixed", Plot(items=[
        PlotItem(kind="shape", shape="circle",
                 params={"center": (0, 0), "r": 2},
                 x_range=(-3, 3), y_range=(-3, 3), label="圆"),
        PlotItem(kind="shape", shape="point",
                 params={"at": (2, 0)},
                 label="P"),
        PlotItem(kind="shape", shape="vector",
                 params={"from": (0, 0), "to": (2, 0)},
                 label="OP"),
        PlotItem(kind="explicit", expr="y = sin(x)",
                 x_range=(-3, 3), label="sin(x)"),
    ])),
    # 10. 自动范围（无 x in / y in）
    ("10_auto_range", Plot(items=[
        PlotItem(kind="shape", shape="circle",
                 params={"center": (0, 0), "r": 1}, label="单位圆"),
        PlotItem(kind="shape", shape="point",
                 params={"at": (1, 0)}, label="A"),
    ])),
    # 11. 单位圆对照：shape=circle vs 隐函数 x²+y²=1
    ("11_circle_compare", Plot(items=[
        PlotItem(kind="shape", shape="circle",
                 params={"center": (0, 0), "r": 1},
                 x_range=(-1.5, 1.5), y_range=(-1.5, 1.5),
                 label="shape=circle"),
        PlotItem(kind="implicit", expr="x^2 + y^2 = 1",
                 x_range=(-1.5, 1.5), y_range=(-1.5, 1.5),
                 label="隐函数"),
    ])),
]

for name, plot in cases:
    out = f"/tmp/shape_test/{name}.png"
    try:
        render_plot(plot, out, dpi=110)
        from PIL import Image
        img = Image.open(out)
        n_items = len(plot.items)
        print(f"✅ {name}: {img.size}  ({n_items} 项)")
    except PlotRenderError as ex:
        print(f"❌ {name}: {ex}")
    except Exception as ex:
        import traceback
        print(f"❌ {name}: {ex}")
        traceback.print_exc()

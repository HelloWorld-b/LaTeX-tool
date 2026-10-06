"""测试 auto-DPI：不同显示宽度应产生不同像素尺寸，但有效 DPI 一致。"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "python"))
from mathtext2doc.parser import Plot, PlotItem
from mathtext2doc.plotter import render_plot
from PIL import Image

os.makedirs("/tmp/dpi_test", exist_ok=True)

# 同一个 plot，用不同 display_width 渲染
def make_plot():
    return Plot(items=[
        PlotItem(kind="explicit", expr="y = sin(x)",
                 x_range=(-3.14, 3.14), label="sin(x)"),
    ])

cases = [
    ("w030", 0.30),  # 小图
    ("w050", 0.50),
    ("w070", 0.70),  # 默认
    ("w090", 0.90),  # 大图
    ("w100", 1.00),  # 全页宽
]

print(f"{'宽度':>6} | {'显示英寸':>8} | {'savefig DPI':>11} | {'像素宽':>6} | {'有效 DPI':>8}")
print("-" * 60)

results = []
for name, w in cases:
    out = f"/tmp/dpi_test/{name}.png"
    render_plot(make_plot(), out, dpi=150, display_width=w)
    img = Image.open(out)
    pixel_w = img.size[0]
    # 显示英寸 = w × 8.27 (A4)
    display_in = w * 8.27
    # 有效 DPI = 像素宽 / 显示英寸
    effective_dpi = pixel_w / display_in
    # 反推 savefig DPI = 像素宽 / figsize_width(5)
    savefig_dpi = pixel_w / 5.0
    print(f"{w:>6.2f} | {display_in:>8.2f} | {savefig_dpi:>11.1f} | {pixel_w:>6d} | {effective_dpi:>8.1f}")
    results.append((w, effective_dpi, pixel_w))

print()
# 验证：所有有效 DPI 都应接近 150（目标）
dpis = [r[1] for r in results]
print(f"有效 DPI 范围: {min(dpis):.1f} ~ {max(dpis):.1f}（目标 150）")
# 由于 savefig DPI 有 [80, 400] 的 clamp，极端值会偏离，但中间值应接近 150
mid_dpis = [r[1] for r in results if 0.4 <= r[0] <= 0.9]
print(f"中间宽度（0.4~0.9）有效 DPI: {min(mid_dpis):.1f} ~ {max(mid_dpis):.1f}")
if max(mid_dpis) - min(mid_dpis) < 5:
    print("✅ 中间宽度有效 DPI 一致（差异 < 5）")
else:
    print("❌ 中间宽度有效 DPI 差异过大")

# 验证：像素宽应随显示宽度单调递增
pixel_widths = [r[2] for r in results]
if pixel_widths == sorted(pixel_widths):
    print("✅ 像素宽随显示宽度单调递增（大图更多像素）")
else:
    print("❌ 像素宽未随显示宽度递增")

# 对比：不传 display_width 时（旧模式），所有图都是 750px
print()
print("--- 对比：旧模式（display_width=None，固定 dpi=150）---")
out_old = "/tmp/dpi_test/old_fixed.png"
render_plot(make_plot(), out_old, dpi=150, display_width=None)
img_old = Image.open(out_old)
print(f"固定 dpi=150: 像素宽 = {img_old.size[0]}（无论显示宽度）")

# 清理
import shutil
shutil.rmtree("/tmp/dpi_test")
print("\n✅ 测试完成")

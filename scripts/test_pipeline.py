"""端到端测试：解析示例输入 → 渲染 plot → 生成 .tex（不调用 LaTeX）。

这个脚本不依赖 LaTeX，仅验证前 3 步是否正常。
"""
import os
import sys

# 把项目根目录加到 sys.path
sys.path.insert(0, "/home/z/my-project")

from mathtext2doc.parser import parse_document, Plot
from mathtext2doc.plotter import render_plot
from mathtext2doc.texgen import generate_tex


def main():
    input_path = "/home/z/my-project/examples/sample_input.txt"
    out_dir = "/home/z/my-project/examples"
    base = "sample_input"

    with open(input_path, "r", encoding="utf-8") as f:
        text = f.read()

    print("=== 步骤 1：解析文档 ===")
    blocks = parse_document(text)
    print(f"解析得到 {len(blocks)} 个 Block")
    for i, b in enumerate(blocks):
        print(f"  [{i}] {type(b).__name__}: {b}")

    print("\n=== 步骤 2：渲染 plot ===")
    plot_paths = {}
    plot_idx = 0
    for b in blocks:
        if isinstance(b, Plot):
            plot_idx += 1
            png_name = f"{base}-plot{plot_idx}.png"
            png_path = os.path.join(out_dir, png_name)
            # 模拟 CLI 的 auto-DPI 行为：传 display_width
            effective_width = b.width if b.width is not None else 0.7
            print(f"  渲染第 {plot_idx} 个 plot (width={effective_width}) → {png_name}")
            render_plot(b, png_path, dpi=150, display_width=effective_width)
            plot_paths[id(b)] = png_name

    print("\n=== 步骤 3：生成 .tex ===")
    tex_content = generate_tex(blocks, plot_paths)
    tex_path = os.path.join(out_dir, base + ".tex")
    with open(tex_path, "w", encoding="utf-8") as f:
        f.write(tex_content)
    print(f"已生成 {tex_path}（{len(tex_content)} 字节）")

    print("\n=== .tex 前 60 行 ===")
    for i, line in enumerate(tex_content.split("\n")[:60], start=1):
        print(f"  {i:3d}| {line}")

    print("\n=== 测试完成 ===")


if __name__ == "__main__":
    main()

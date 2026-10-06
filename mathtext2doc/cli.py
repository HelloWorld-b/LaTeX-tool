"""mathtext2doc CLI 入口。

用法：
    python -m mathtext2doc.cli input.txt
    python -m mathtext2doc.cli input.txt --compiler xelatex --dpi 200
    python -m mathtext2doc.cli input.txt --keep-intermediates
    python -m mathtext2doc.cli input.txt --overwrite

退出码：
    0   成功
    1   解析错误
    2   绘图错误
    3   LaTeX 编译错误
    4   输入/输出错误（文件不存在、输出已存在等）
    5   其它未预期错误
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from typing import Dict, List

from . import __version__
from .parser import (
    DisplayMath,
    Heading,
    ListItem,
    Paragraph,
    ParseError,
    Plot,
    PlotParseError,
    parse_document,
)
from .plotter import PlotRenderError, render_plot
from .texgen import generate_tex
from .compiler import CompileError, compile_tex_to_png


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(input_path: str, args: argparse.Namespace) -> int:
    """主流程。返回退出码。"""
    # 0. 校验参数
    if not (0 < args.plot_width <= 1.0):
        sys.stderr.write(
            f"错误：--plot-width 必须在 (0, 1] 之间，得到 {args.plot_width}\n"
        )
        return 4

    # 1. 检查输入文件
    if not os.path.isfile(input_path):
        sys.stderr.write(f"错误：输入文件不存在：{input_path}\n")
        return 4
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as ex:
        sys.stderr.write(f"错误：读取输入文件失败：{ex}\n")
        return 4

    out_dir = os.path.dirname(os.path.abspath(input_path)) or "."
    base = os.path.splitext(os.path.basename(input_path))[0]
    tex_path = os.path.join(out_dir, base + ".tex")

    # 2. 检查输出是否已存在
    if not args.overwrite:
        if os.path.isfile(tex_path):
            sys.stderr.write(
                f"错误：输出 .tex 已存在：{tex_path}（使用 --overwrite 覆盖）\n"
            )
            return 4
        # 检查 PNG
        for fn in os.listdir(out_dir):
            if fn.startswith(base + "-") and fn.endswith(".png"):
                sys.stderr.write(
                    f"错误：输出 PNG 已存在：{os.path.join(out_dir, fn)}"
                    f"（使用 --overwrite 覆盖）\n"
                )
                return 4

    # 3. 解析文档
    try:
        blocks = parse_document(text)
    except PlotParseError as ex:
        sys.stderr.write(f"绘图指令解析错误：{ex}\n")
        return 1
    except ParseError as ex:
        sys.stderr.write(f"文档解析错误：{ex}\n")
        return 1

    # 4. 渲染所有 plot
    plot_paths: Dict[int, str] = {}
    plot_idx = 0
    for b in blocks:
        if isinstance(b, Plot):
            plot_idx += 1
            png_name = f"{base}-plot{plot_idx}.png"
            png_path = os.path.join(out_dir, png_name)
            try:
                render_plot(b, png_path, dpi=args.dpi)
            except PlotRenderError as ex:
                sys.stderr.write(f"绘图错误（第 {plot_idx} 个 @plot）：{ex}\n")
                return 2
            plot_paths[id(b)] = png_name  # .tex 中用相对名

    # 5. 生成 .tex
    try:
        tex_content = generate_tex(blocks, plot_paths, default_plot_width=args.plot_width)
    except Exception as ex:
        sys.stderr.write(f"生成 .tex 失败：{ex}\n")
        return 5
    try:
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)
    except Exception as ex:
        sys.stderr.write(f"写入 .tex 失败：{ex}\n")
        return 4

    sys.stdout.write(f"已生成 {tex_path}\n")

    # 6. 编译并产出 PNG
    try:
        result = compile_tex_to_png(
            tex_path,
            out_dir,
            compiler=args.compiler,
            dpi=args.dpi,
            overwrite=args.overwrite,
            keep_intermediates=args.keep_intermediates,
        )
    except CompileError as ex:
        sys.stderr.write(f"LaTeX 编译失败：{ex}\n")
        return 3

    # 7. 输出结果
    sys.stdout.write(f"使用编译器：{result.compiler}\n")
    if result.fallback_used:
        sys.stdout.write("（已回退到 PDF→PNG 路径）\n")
    sys.stdout.write(f"输出 PNG：\n")
    for p in result.png_paths:
        sys.stdout.write(f"  {p}\n")
    if result.pdf_path:
        sys.stdout.write(f"保留 PDF：{result.pdf_path}\n")
    if result.log_path:
        sys.stdout.write(f"保留日志：{result.log_path}\n")

    # 8. 清理 plot PNG（若不保留中间文件）
    if not args.keep_intermediates:
        for path in plot_paths.values():
            full = os.path.join(out_dir, path)
            if os.path.isfile(full):
                try:
                    os.remove(full)
                except Exception:
                    pass

    return 0


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mathtext2doc",
        description=(
            "把 AI 生成的数学文本快速转成带公式和函数图像的文档图片。"
            "支持 Markdown、$...$/$$...$$ LaTeX 公式、@plot{...} 绘图指令。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python -m mathtext2doc.cli input.txt\n"
            "  python -m mathtext2doc.cli input.txt --compiler xelatex --dpi 200\n"
            "  python -m mathtext2doc.cli input.txt --overwrite --keep-intermediates\n"
        ),
    )
    p.add_argument("input", help="输入文件路径（UTF-8 纯文本）")
    p.add_argument(
        "--compiler",
        choices=["xelatex", "lualatex", "pdflatex"],
        default=None,
        help="指定 LaTeX 编译器；不指定则自动选择（优先 xelatex）",
    )
    p.add_argument(
        "--dpi",
        type=int,
        default=150,
        help="PNG DPI，默认 150",
    )
    p.add_argument(
        "--plot-width",
        type=float,
        default=0.7,
        help="函数图在文档中的宽度（相对于页面宽度 \\paperwidth，0~1），默认 0.7",
    )
    p.add_argument(
        "--keep-intermediates",
        action="store_true",
        default=True,
        help="保留函数图 PNG 和 .log/.pdf/.aux 等中间文件（默认开启）",
    )
    p.add_argument(
        "--no-keep-intermediates",
        dest="keep_intermediates",
        action="store_false",
        help="不保留中间文件（仅保留最终 PNG 和 .tex）",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="覆盖已有输出文件",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"mathtext2doc {__version__}",
    )
    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args.input, args)
    except KeyboardInterrupt:
        sys.stderr.write("已中断\n")
        return 5
    except Exception as ex:
        sys.stderr.write(f"未预期错误：{ex}\n")
        traceback.print_exc()
        return 5


if __name__ == "__main__":
    sys.exit(main())

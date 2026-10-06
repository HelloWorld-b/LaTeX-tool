"""mathtext2doc — 把 AI 生成的数学文本快速转成带公式和函数图像的文档图片。

子模块：
    parser   — 解析 Markdown / LaTeX 公式 / @plot 指令
    plotter  — 绘制 2D 显函数 / 隐函数 / 多函数同图，输出 PNG
    texgen   — 生成完整 .tex 文件（ctex / xeCJK 中文支持）
    compiler — 调用本机 LaTeX 编译并产出 PNG
    cli      — 命令行入口

常用 API（可直接 from mathtext2doc import）：
    parse_document(text)          → 解析文本，返回 Block 列表
    render_plot(plot, out_path)   → 渲染单个 Plot 到 PNG
    generate_tex(blocks, paths)   → 生成完整 .tex 内容
    compile_tex_to_png(tex_path)  → 编译 .tex 并输出 PNG
    convert(text_file)            → 一站式：文本文件 → PNG（高层 API）
"""

__version__ = "0.1.0"

# 导出常用 API，让用户能 from mathtext2doc import parse_document 等
from .parser import (
    parse_document,
    ParseError,
    PlotParseError,
    Plot,
    PlotItem,
)
from .plotter import render_plot, PlotRenderError
from .texgen import generate_tex
from .compiler import compile_tex_to_png, CompileError

__all__ = [
    # 子模块
    "parser", "plotter", "texgen", "compiler", "cli",
    # 版本
    "__version__",
    # 核心 API
    "parse_document", "render_plot", "generate_tex", "compile_tex_to_png",
    # 异常
    "ParseError", "PlotParseError", "PlotRenderError", "CompileError",
    # AST 节点
    "Plot", "PlotItem",
]

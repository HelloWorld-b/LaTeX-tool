"""mathtext2doc — 把 AI 生成的数学文本快速转成带公式和函数图像的文档图片。

子模块：
    parser   — 解析 Markdown / LaTeX 公式 / @plot 指令
    plotter  — 绘制 2D 显函数 / 隐函数 / 多函数同图，输出 PNG
    texgen   — 生成完整 .tex 文件（ctex / xeCJK 中文支持）
    compiler — 调用本机 LaTeX 编译并产出 PNG
    cli      — 命令行入口
"""

__version__ = "0.1.0"
__all__ = ["parser", "plotter", "texgen", "compiler", "cli"]

# Changelog

本文件记录 mathtext2doc 的版本变更。格式参考 [Keep a Changelog](https://keepachangelog.com/)。

## [0.1.0] - 2026-10-06

### 首次发布

#### 核心功能
- 解析 UTF-8 纯文本，支持中文、基础 Markdown、LaTeX 公式、`@plot{...}` 绘图指令
- Markdown 子集：`#`~`####` 标题、有序/无序列表、**粗体**、*斜体*、`代码`、表格、分隔线、引用块
- LaTeX 公式：`$...$` 行内、`$$...$$` 块级
- `@plot{...}` / `@geometry{...}` 绘图：
  - 显函数 `y = f(x)`
  - 隐函数 `F(x, y) = 0`
  - 9 种几何图形：`point` / `segment` / `line` / `circle` / `ellipse` / `polygon` / `rectangle` / `vector` / `parabola`
  - 多函数同图（`;` 分隔）
  - 标签自动避让，支持 LaTeX（`$...$`）
- 选项：`@plot(width=0.5, align=left){ ... }`
- 生成完整 `.tex` 文件（ctexart + xeCJK 中文支持）
- 调用本机 xelatex 编译，输出 PNG（多页多张）
- Auto-DPI：PNG 像素尺寸随显示宽度自动调整

#### CLI 参数
- `input`（位置参数）：输入文件路径
- `--compiler`：指定 LaTeX 编译器（xelatex / lualatex / pdflatex）
- `--dpi`：目标有效 DPI（默认 150）
- `--plot-width`：全局默认图宽（默认 0.7）
- `--keep-intermediates` / `--no-keep-intermediates`：保留中间文件
- `--overwrite`：覆盖已有输出
- `--version`：版本号

#### 依赖
- matplotlib >= 3.5
- numpy >= 1.20
- sympy >= 1.10
- PyMuPDF >= 1.23
- 本机 LaTeX 发行版（TeX Live / MiKTeX / MacTeX，含 xelatex + ctex）

#### Python API
- `parse_document(text)` — 解析文本
- `render_plot(plot, out_path)` — 渲染 Plot 到 PNG
- `generate_tex(blocks, plot_paths)` — 生成 .tex 内容
- `compile_tex_to_png(tex_path, out_dir)` — 编译并输出 PNG

#### 已知限制
- 不支持 3D 绘图
- 不调用 LLM，只处理已生成文本
- 不做自动定义域推断
- Markdown 子集有限（不支持图片、链接、嵌套列表、代码块）
- LaTeX 编译需要本机安装 TeX 发行版

---
Task ID: mathtext2doc-mvp
Agent: main (Super Z)
Task: 实现一个本地 CLI 小工具 mathtext2doc，把 AI 生成的数学文本（含中文、Markdown、$...$/$$...$$ LaTeX 公式、@plot{...} 绘图指令）转成带公式和函数图像的文档 PNG。

Work Log:
- 探测环境：本机有 Python 3.12 + matplotlib 3.9 + sympy 1.14 + numpy 2.1，有中文字体（Noto Sans SC 等），有 pdftoppm/pdftocairo；本机未装 LaTeX（无 root 权限无法安装），但工具设计为在用户本机调用 LaTeX，compiler 模块对缺失情况给出清晰错误。
- 创建项目结构：/home/z/my-project/{mathtext2doc/,examples/,scripts/,README.md,pyproject.toml,requirements.txt}
- 实现 mathtext2doc/parser.py：Markdown 子集（#/##/-/**bold**/`code`/表格）+ $...$/$$...$ 公式 + @plot{...} 绘图指令解析；LaTeX 特殊字符自动转义；@plot 内部支持显函数/隐函数/多函数同图（; 分隔）；定义域强制要求（缺 x in [...] 报错，隐函数缺 y in [...] 报错）；区间支持 pi/e 等简单表达式。
- 实现 mathtext2doc/plotter.py：
  * 显函数：sympy 解析 → lambdify → numpy 采样，matplotlib 绘制
  * 隐函数：sympy 解析 F(x,y)=0 → numpy meshgrid → matplotlib contour(level=0)
  * 颜色循环自动分配
  * 标签锚点：曲线弧长中点偏上
  * 标签避让：8 方向螺旋外扩算法，基于 bbox 重叠检测
  * 中文字体自动探测（Noto Sans SC / WenQuanYi / PingFang SC 等多平台）
  * 修复 matplotlib 3.9 ContourSet.collections 废弃问题
- 实现 mathtext2doc/texgen.py：ctexart 文档类（xeCJK 中文）+ amsmath/amssymb/graphicx/booktabs/xcolor/hyperref；\plotwidth = 0.4\textwidth；表格用 booktabs；列表用 itemize；行内公式 $...$、块级公式 equation*。
- 实现 mathtext2doc/compiler.py：
  * pick_latex_compiler：优先 xelatex（中文），回退 lualatex/pdflatex
  * 优先尝试直接 PNG（latex + dvipng，仅无中文时）
  * 回退：xelatex 编译 PDF → pdftoppm/pdftocairo/convert 转 PNG
  * 多页 PDF 输出多张 PNG（base-1.png base-2.png ...）
  * 失败时保留 .log/.tex/.pdf，错误信息含日志末尾 40 行
- 实现 mathtext2doc/cli.py：argparse 参数（--compiler/--dpi/--keep-intermediates/--overwrite/--version）；退出码 0/1/2/3/4/5 分别对应成功/解析错误/绘图错误/编译错误/IO错误/未预期错误。
- 实现 mathtext2doc/__main__.py：支持 python -m mathtext2doc 调用。
- 编写 README.md：依赖安装（Python + LaTeX + PDF→PNG 工具 + 中文字体）、CLI 参数表、输入语法（Markdown 子集 + LaTeX 公式 + @plot 指令）、输出文件命名、编译策略、已知限制（11 条）、项目结构、快速验证步骤。
- 编写 examples/sample_input.txt：含中文段落、# / ## 标题、- 列表、**bold**、表格、$...$ 行内公式、$$...$$ 块级公式、3 个 @plot（sin+cos 显函数同图、单位圆隐函数、显隐混合）。
- 端到端测试（无 LaTeX 部分）：
  * parser：39 个 Block 正确解析（Heading/Paragraph/DisplayMath/Plot/ListItem/Table/BlankLine）
  * plotter：3 张 PNG 生成（750x600，58KB/33KB/58KB），无中文字体警告
  * texgen：2025 字节 .tex 文件生成，结构完整（ctexart + 所有宏包 + 中文段落 + 公式 + 列表 + 表格 + 3 个 figure）
  * CLI：--help 正常，错误路径（无定义域/隐函数缺 y/文件不存在）退出码正确（1/1/4）
  * LaTeX 缺失时给出清晰错误信息，退出码 3
- 修复迭代中发现的问题：
  1. _parse_one_plot_item 按逗号分割时误切 [a, b] 区间 → 增加 bracket 计数跳过 [...] 内的逗号
  2. 中文字体路径写死 NotoSansSC-Regular.ttf 但实际是 NotoSansSC[wght].ttf（变量字体）→ 改为多路径自动探测 + 字体名探测
  3. matplotlib 3.9 ContourSet.collections 废弃 → 用 hasattr 兼容新旧 API
  4. 内联 @plot{...} 出现在段落中间时占位符残留 → 替换时前后插入换行强制独占行

Stage Summary:
- 工具已完整实现，覆盖需求规范全部条目：
  * 解析中文/Markdown/LaTeX/@plot ✓
  * 2D 显函数/隐函数/多函数同图 ✓
  * 生成完整 .tex ✓
  * 调用本机 LaTeX 编译 ✓
  * 优先直接 PNG，失败回退 PDF→PNG ✓
  * 多页多张 PNG ✓
  * 输出目录与输入同级 ✓
  * 中文支持（xelatex + ctex）✓
  * CLI 参数（编译器/DPI/保留中间文件/覆盖）✓
  * 错误处理与退出码 ✓
  * 标签默认几何中点偏上 + 自动避让 ✓
  * 颜色自动分配 ✓
  * 定义域必须用户指定 ✓
  * 不做 3D/LLM/OCR/求解 ✓
- 本机无 LaTeX 无法完成最终 PNG 渲染验证，但所有非 LaTeX 依赖的子模块均通过测试；用户在装有 TeX Live 的机器上运行 python -m mathtext2doc examples/sample_input.txt --overwrite 即可得到完整输出。
- 产物清单：
  * /home/z/my-project/mathtext2doc/{__init__,__main__,cli,parser,plotter,texgen,compiler}.py
  * /home/z/my-project/examples/sample_input.txt
  * /home/z/my-project/README.md
  * /home/z/project/requirements.txt, pyproject.toml
  * /home/z/my-project/scripts/test_pipeline.py（测试脚本）

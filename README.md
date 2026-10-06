# mathtext2doc

把 AI 生成的数学文本快速转成带公式和函数图像的文档图片。

本工具是一个 **本地 CLI**，不调用任何 LLM，不上传用户文本。它解析一份 UTF-8 纯文本
（含中文、基础 Markdown、`$...$` / `$$...$$` LaTeX 公式、`@plot{...}` 绘图指令），
绘制其中的函数图，生成完整 `.tex` 文件，调用本机 LaTeX 发行版编译，并输出整篇文档
渲染后的 PNG（多页则多张）。

---

## 一、安装依赖

### 1. Python 依赖

要求 Python ≥ 3.10。

```bash
pip install matplotlib numpy sympy
```

### 2. LaTeX 发行版

需要本机已安装以下之一：

- **TeX Live**（推荐，Linux/macOS/Windows）：https://www.tug.org/texlive/
- **MiKTeX**（Windows）：https://miktex.org/
- **MacTeX**（macOS）：https://www.tug.org/mactex/

必须包含 **`xelatex`**（用于中文支持，搭配 `ctex` / `xeCJK` 宏包）。
TeX Live 默认安装会带上 `ctex`；MiKTeX 在首次编译时会自动下载缺少的宏包。

验证：

```bash
xelatex --version
```

### 3. PDF→PNG 转换工具（回退路径用）

LaTeX 本身通常不直接输出 PNG，所以工具会回退到 **PDF→PNG** 路径。需要本机安装以下之一：

- **poppler-utils**（推荐）：`pdftoppm` / `pdftocairo`
  - Ubuntu/Debian：`sudo apt-get install poppler-utils`
  - macOS：`brew install poppler`
  - Windows：从 https://blog.alivate.com.au/poppler-windows/ 下载并加入 PATH
- **ImageMagick**（备选）：`convert`
  - Ubuntu/Debian：`sudo apt-get install imagemagick`
  - macOS：`brew install imagemagick`
  - 注意：ImageMagick 默认会限制 PDF 读取，可能需要修改 `policy.xml`。

验证：

```bash
pdftoppm -v
# 或
pdftocairo -v
# 或
convert -version
```

### 4. 中文字体

`ctex` 默认会自动选用系统已有的中文字体。Linux 上推荐安装 Noto Sans CJK SC：

```bash
sudo apt-get install fonts-noto-cjk
```

---

## 二、CLI 参数

```
usage: mathtext2doc [-h] [--compiler {xelatex,lualatex,pdflatex}]
                    [--dpi DPI] [--keep-intermediates | --no-keep-intermediates]
                    [--overwrite] [--version]
                    input
```

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `input` | 输入文件路径（UTF-8 纯文本） | 必填 |
| `--compiler` | 指定 LaTeX 编译器：`xelatex` / `lualatex` / `pdflatex` | 自动选择（优先 `xelatex`） |
| `--dpi` | PNG DPI | `150` |
| `--plot-width` | 函数图在文档中的宽度（相对于 `\paperwidth`，0~1） | `0.7` |
| `--keep-intermediates` | 保留函数图 PNG 和 `.log`/`.pdf`/`.aux` 等中间文件 | 默认开启 |
| `--no-keep-intermediates` | 不保留中间文件（仅保留最终 PNG 和 `.tex`） | — |
| `--overwrite` | 覆盖已有输出文件 | 默认不覆盖 |
| `--version` | 打印版本号 | — |

### 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 成功 |
| 1 | 解析错误（Markdown / LaTeX / `@plot` 语法） |
| 2 | 绘图错误（表达式无法解析、定义域问题等） |
| 3 | LaTeX 编译错误 |
| 4 | 输入/输出错误（文件不存在、输出已存在等） |
| 5 | 其它未预期错误 |

### 用法示例

```bash
# 最简用法
python -m mathtext2doc input.txt

# 指定编译器和 DPI
python -m mathtext2doc input.txt --compiler xelatex --dpi 200

# 调整函数图在文档中的宽度（默认 0.7 = 页面宽度的 70%）
python -m mathtext2doc input.txt --plot-width 0.5

# 覆盖已有输出
python -m mathtext2doc input.txt --overwrite

# 仅保留最终 PNG 和 .tex，清理中间文件
python -m mathtext2doc input.txt --no-keep-intermediates
```

---

## 三、输入语法

### 1. Markdown 子集

| 语法 | 含义 |
| --- | --- |
| `# 标题` | 一级标题 → `\section{}` |
| `## 标题` | 二级标题 → `\subsection{}` |
| `- 文字` | 无序列表项 → `itemize` |
| `**文字**` | 粗体 → `\textbf{}` |
| `` `代码` `` | 行内代码 → `\texttt{}` |
| `\| a \| b \|` 表格 | 基础 Markdown 表格 → `tabular` + `booktabs` |

> 普通文本中的 LaTeX 特殊字符（`# $ % & _ { } ~ ^ \`）会自动转义；公式区域保留原样。

### 2. LaTeX 公式

- **行内公式**：`$...$`，例如 `$e^{i\pi} + 1 = 0$`
- **块级公式**：`$$...$$`，独占一段，会渲染成 `equation*` 环境

公式内容原样传给 LaTeX，不做转义。

### 3. `@plot{...}` 绘图指令

格式：`@plot{ ... }`，内部用分号 `;` 分隔多个绘制项。

可选的宽度选项：`@plot(width=0.5){ ... }`，控制图在文档中的宽度（相对于 `\paperwidth`，0~1）。不指定时用全局默认（CLI `--plot-width`，默认 `0.7`）。

**显函数**（`y = f(x)`）：

```
y = sin(x), x in [-pi, pi], label="sin(x)"
```

**隐函数**（`F(x, y) = 0`，必须指定 `y in [...]`）：

```
x^2 + y^2 = 1, x in [-2, 2], y in [-2, 2], label="单位圆"
```

**多函数同图**（用 `;` 分隔，显隐可混合）：

```
@plot{
  y = sin(x), x in [-pi, pi], label="sin(x)";
  y = cos(x), x in [-pi, pi], label="cos(x)";
  x^2 + y^2 = 1, x in [-1.5, 1.5], y in [-1.5, 1.5], label="单位圆"
}
```

**单图指定宽度**：

```
@plot(width=0.5){
  y = sin(x), x in [-pi, pi], label="sin(x)"
}
```

**几何图形**（`shape=...`）：

```
@plot{
  shape=circle, center=(0, 0), r=2, label="圆 C";
  shape=point, at=(2, 0), label="P";
  shape=segment, from=(0, 0), to=(2, 0), label="半径 r"
}
```

支持的几何图形：`point`、`segment`、`line`、`circle`、`ellipse`、`polygon`、`rectangle`、`vector`、`parabola`。详见 [SYNTAX_FOR_AI.md](./SYNTAX_FOR_AI.md) 第 4.10 节。

**规则**：

- **定义域必须由用户指定**（函数曲线）；几何图形的定义域可选（自动估算）。
- `label` 可选，支持中文。
- `label` 默认标注在曲线可见部分的几何中点（按弧长）偏上；几何图形标签锚点因形状而异。
- 多个标签之间会自动避让（基于 bbox 重叠检测的螺旋外扩算法）。
- 颜色自动按循环分配。
- 支持的初等函数 / 常量：`+ - * / ^`、`sin`、`cos`、`tan`、`log`（自然对数）、`ln`、`exp`、`sqrt`、`abs`、`pi`、`e`。
- 区间 `[a, b]` 中的 `a`、`b` 可以是数字或简单表达式（`pi`、`pi/2`、`-pi`、`2*pi` 等）。
- 图宽控制：`@plot(width=0.x)` 单图覆盖，或 CLI `--plot-width 0.x` 全局默认。

---

## 四、输出文件命名

设输入文件为 `foo.txt`，输出目录与输入同级：

| 文件 | 含义 |
| --- | --- |
| `foo.tex` | 生成的完整 LaTeX 文件 |
| `foo-plot1.png`、`foo-plot2.png` … | 各 `@plot` 的函数图（作为 `\includegraphics` 嵌入 .tex） |
| `foo.pdf` | LaTeX 编译产物（保留中间文件时） |
| `foo-1.png`、`foo-2.png` … | 最终整篇文档渲染后的 PNG（多页则多张） |
| `foo.log` | LaTeX 编译日志（保留中间文件时） |
| `foo.aux` 等 | LaTeX 其它中间文件（保留中间文件时） |

函数图默认宽度为 `0.7\paperwidth`（页面宽度的 70%），可通过 `@plot(width=0.x)` 单图覆盖或 CLI `--plot-width 0.x` 全局调整。

---

## 五、编译策略

1. **优先尝试直接 PNG 输出**：检测 `latex` + `dvipng`，若源文件不含中文，尝试 `latex` → DVI → `dvipng` PNG。该路径不依赖 `xelatex`，但**不支持中文**，所以含中文时直接跳过。
2. **回退到 PDF→PNG**：调用 `xelatex` 编译 `.tex` 生成 PDF，再用 `pdftoppm` / `pdftocairo` / ImageMagick `convert` 把 PDF 按页转 PNG。
3. **多页输出**：PDF 有几页就输出几张 PNG，命名为 `foo-1.png`、`foo-2.png` …
4. **失败处理**：编译失败时保留 `.tex`、`.log`、`.pdf`（若有），输出清晰错误信息（含编译器、文件路径、日志末尾 40 行）。

---

## 六、已知限制

1. **不支持 3D 绘图**。`@plot` 仅处理 2D 显函数和隐函数；3D 留待后续扩展。
2. **不调用 LLM**，只处理 AI 已生成的文本；不做 OCR、不做公式识别、不做符号求解。
3. **不做自动定义域推断**：用户必须在 `@plot` 中显式给出 `x in [...]`（隐函数还要 `y in [...]`）。
4. **Markdown 支持范围有限**：仅支持 `#`、`##`、`-`、`**bold**`、`` `code` ``、基础表格。不支持图片、链接、引用块、代码块、嵌套列表、有序列表等。
5. **表格列对齐**：所有列默认左对齐（`lll...`），不解析 `:---:` 等对齐语法。
6. **标签避让为启发式算法**：极端密集场景（如 10 条曲线挤在一起）可能仍有重叠；标签会尽量沿 8 个方向螺旋外扩，找不到无重叠位置时会保留最后位置。
7. **隐函数绘制基于 `contour` 等高线**：对于不可定向、自相交或非常陡峭的隐函数曲线，可能出现锯齿或断点。
8. **`xelatex` 编译较慢**：首次编译 ctex 文档可能需要 10–30 秒；后续会因 `.aux` 缓存稍快。
9. **`ImageMagick` 默认禁用 PDF 读取**：若只能用 `convert`，需手动修改 `/etc/ImageMagick-6/policy.xml` 把 `<policy domain="coder" rights="none" pattern="PDF" />` 改为 `rights="read|write"`。
10. **行内公式不能跨行**：`$...$` 必须在同一行内闭合；`$$...$$` 可以跨多行。
11. **不支持自定义 LaTeX 模板**：文档结构固定为 `ctexart` + `geometry` + `amsmath` + `graphicx` + `booktabs`。

---

## 七、项目结构

```
mathtext2doc/
├── __init__.py        # 包入口
├── __main__.py        # python -m mathtext2doc 入口
├── cli.py             # CLI 参数解析与主流程
├── parser.py          # Markdown / LaTeX / @plot 解析
├── plotter.py         # 显函数 / 隐函数 / 多函数同图 + 标签避让
├── texgen.py          # .tex 生成
└── compiler.py        # LaTeX 编译 + PDF→PNG 转换
examples/
└── sample_input.txt   # 示例输入
README.md
```

---

## 八、快速验证

```bash
# 在项目根目录下
python -m mathtext2doc examples/sample_input.txt --overwrite
```

预期输出：

```
已生成 .../examples/sample_input.tex
使用编译器：xelatex
（已回退到 PDF→PNG 路径）
输出 PNG：
  .../examples/sample_input-1.png
  .../examples/sample_input-2.png
保留 PDF：.../examples/sample_input.pdf
保留日志：.../examples/sample_input.log
```

如果本机未装 LaTeX，会得到清晰的错误提示：

```
LaTeX 编译失败：未找到任何 LaTeX 编译器。请安装 TeX Live / MiKTeX / MacTeX，...
```

# mathtext2doc

把 AI 生成的数学文本快速转成带公式和函数图像的文档图片。支持中文、基础 Markdown、LaTeX 公式、`@plot{...}` / `@geometry{...}` 绘图指令。

本仓库分三个目录：

| 目录 | 说明 | 入口 |
|---|---|---|
| [`python/`](./python/) | Python CLI 版（可发布到 PyPI） | `python -m mathtext2doc input.txt` |
| [`html/`](./html/) | 网页版（单 HTML 文件，双击即用） | `mathtext2doc-web.html` |
| [`examples/`](./examples/) | 示例输入 + 测试脚本 + 项目介绍 | `sample_input.txt` |

---

## 快速开始

### 网页版（推荐，零安装）

1. 下载 [`html/mathtext2doc-web.html`](./html/mathtext2doc-web.html)
2. 双击用浏览器打开
3. 拖入 `.txt` / `.md` 文件或直接输入

### Python CLI 版

```bash
cd python/
pip install -r requirements.txt
python -m mathtext2doc input.txt
```

详细安装与发布见 [`python/PYPI_GUIDE.md`](./python/PYPI_GUIDE.md)。

---

## 功能

- **Markdown 子集**：`#`~`####` 标题、有序/无序列表、**粗体**、*斜体*、`代码`、表格、分隔线、引用块
- **LaTeX 公式**：`$...$` 行内、`$$...$$` 块级
- **绘图指令**：
  - `@plot{...}` / `@geometry{...}`
  - 显函数 `y = f(x)`、隐函数 `F(x,y) = 0`
  - 9 种几何图形：`point` / `segment` / `line` / `circle` / `ellipse` / `polygon` / `rectangle` / `vector` / `parabola`
  - 选项：`(width=0.5, align=left)`
- **中文支持**：CLI 用 xelatex + ctex，HTML 用 KaTeX + 中文字体
- **导出**：PNG（多页）/ PDF / .tex 源码

完整语法见 [`python/SYNTAX_FOR_AI.md`](./python/SYNTAX_FOR_AI.md)（也给 AI 看的语法教学）。

---

## 许可证

MIT

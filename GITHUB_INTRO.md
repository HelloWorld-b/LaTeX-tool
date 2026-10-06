# mathtext2doc · 数学文本一键转文档图片

> 🇨🇳 [中文](#中文) ｜ 🇬🇧 [English](#english)

---

## 中文

**把 AI 生成的数学文本，一键转成带公式和函数图像的文档图片。**

`mathtext2doc` 是一个**本地运行**的命令行小工具，专为学生打造：你只需要把 AI 生成的数学笔记（中文 + Markdown + LaTeX 公式 + `@plot{...}` 绘图指令）扔给它，它就会自动解析、绘图、生成 `.tex`、调用本机 LaTeX 编译，最终吐出整篇文档渲染后的 PNG（多页则多张）。

不调用任何 LLM，不上传任何文本，全部在你自己的机器上完成。

### ✨ 特性一览

| 能力 | 说明 |
| --- | --- |
| 📝 **混合语法解析** | 中文 · 基础 Markdown（标题/列表/粗体/表格）· `$...$` 行内公式 · `$$...$$` 块级公式 |
| 📈 **2D 函数绘图** | 显函数 `y = f(x)` · 隐函数 `F(x,y) = 0` · 多函数同图（显隐可混合） |
| 🏷️ **智能标签** | 默认标注在曲线弧长中点偏上，多标签自动避让（8 方向螺旋外扩算法） |
| 🎨 **自动配色** | 色盲友好颜色循环，无需手动指定 |
| 🇨🇳 **中文友好** | 自动探测系统中文字体，`xelatex` + `ctex` 渲染，零配置 |
| 🖼️ **整页 PNG 输出** | 优先直接输出 PNG，失败自动回退 PDF → PNG（`pdftoppm` / `pdftocairo` / `convert`） |
| 📄 **多页支持** | 文档多长就输出多少张 `foo-1.png`、`foo-2.png`… |
| 🔒 **本地优先** | 全程离线，无网络请求，无 API 调用 |

### 🚀 快速上手

```bash
pip install matplotlib numpy sympy   # Python 依赖
# 确保已安装 TeX Live（含 xelatex + ctex）和 poppler-utils（pdftoppm）

python -m mathtext2doc input.txt
```

输入示例：

```text
## 三角函数与单位圆

下面同时绘制 $\sin(x)$ 与 $\cos(x)$：

@plot{
  y = sin(x), x in [-pi, pi], label="sin(x)";
  y = cos(x), x in [-pi, pi], label="cos(x)"
}

欧拉公式：$$e^{i\pi} + 1 = 0$$
```

输出（与 `input.txt` 同级）：

```
input.tex              # 生成的完整 LaTeX
input-plot1.png        # 函数图（嵌入 .tex）
input-1.png            # 整篇文档渲染后的 PNG（第 1 页）
input-2.png            # 第 2 页（若有）
```

### 📦 安装

```bash
git clone https://github.com/<your-name>/mathtext2doc.git
cd mathtext2doc
pip install -r requirements.txt
```

详见 [README.md](./README.md) 的「安装依赖」一节。

### 🎯 适用场景

- 📚 把 ChatGPT / Claude / 文心一言 生成的数学笔记转成可打印的图片
- 🖊️ 学生整理课后笔记、考前复习材料
- 👩‍🏫 教师快速生成带函数图像的讲义插图
- 🤖 AI 辅导工具的本地后处理环节

### 🚧 已知限制

- 仅支持 2D 绘图（3D 留待后续）
- 不做 OCR、公式识别、符号求解（只处理 AI 已生成文本）
- 不自动推断定义域（用户必须在 `@plot` 中显式给出 `x in [...]`）
- Markdown 子集有限（不支持图片、链接、嵌套列表、代码块）

完整限制清单见 [README.md](./README.md)。

---

## English

**Turn AI-generated math notes into document images with formulas and function plots — in one command.**

`mathtext2doc` is a **fully local** CLI tool built for students. Feed it AI-generated math notes (Chinese + Markdown + LaTeX formulas + `@plot{...}` directives), and it will parse, plot, generate `.tex`, invoke your local LaTeX distribution, and emit the fully-rendered document as PNG (one image per page).

No LLM calls. No text uploads. Everything runs on your own machine.

### ✨ Highlights

| Feature | Description |
| --- | --- |
| 📝 **Mixed-syntax parsing** | Chinese · basic Markdown (headings / lists / bold / tables) · `$...$` inline · `$$...$$` display math |
| 📈 **2D function plotting** | Explicit `y = f(x)` · implicit `F(x,y) = 0` · multi-curve on one axes (mix allowed) |
| 🏷️ **Smart labels** | Anchored at the arc-length midpoint, offset upward; multi-label collision avoidance via 8-direction spiral expansion |
| 🎨 **Auto color cycling** | Color-blind-friendly palette, no manual config |
| 🇨🇳 **CJK-friendly** | Auto-detects system CJK fonts; renders via `xelatex` + `ctex` with zero config |
| 🖼️ **Whole-page PNG** | Tries direct PNG first, falls back to PDF → PNG (`pdftoppm` / `pdftocairo` / `convert`) |
| 📄 **Multi-page** | Emits `foo-1.png`, `foo-2.png`, … — one per page |
| 🔒 **Local-first** | Fully offline, no network, no API calls |

### 🚀 Quick Start

```bash
pip install matplotlib numpy sympy   # Python deps
# Make sure TeX Live (with xelatex + ctex) and poppler-utils (pdftoppm) are installed

python -m mathtext2doc input.txt
```

Sample input:

```text
## Trig functions & unit circle

Plot $\sin(x)$ and $\cos(x)$ together:

@plot{
  y = sin(x), x in [-pi, pi], label="sin(x)";
  y = cos(x), x in [-pi, pi], label="cos(x)"
}

Euler's identity: $$e^{i\pi} + 1 = 0$$
```

Output (next to `input.txt`):

```
input.tex              # generated LaTeX
input-plot1.png        # function plot (embedded in .tex)
input-1.png            # rendered document PNG (page 1)
input-2.png            # page 2 (if any)
```

### 📦 Install

```bash
git clone https://github.com/<your-name>/mathtext2doc.git
cd mathtext2doc
pip install -r requirements.txt
```

See the [README.md](./README.md) "Installation" section for full details.

### 🎯 Use Cases

- 📚 Convert ChatGPT / Claude / Gemini math notes into printable images
- 🖊 Students organizing class notes or exam-prep materials
- 👩‍🏫 Teachers quickly generating handouts with function plots
- 🤖 Local post-processing step for AI tutoring tools

### 🚧 Known Limitations

- 2D plotting only (3D planned for later)
- No OCR, no formula recognition, no symbolic solving (only processes AI-generated text)
- No automatic domain inference (users must specify `x in [...]` in `@plot`)
- Limited Markdown subset (no images, links, nested lists, or code blocks)

Full list in [README.md](./README.md).

---

## License

MIT

## Contributing

PRs welcome! Please open an issue first to discuss what you'd like to change.

---

<sub>Built with Python · matplotlib · SymPy · LaTeX (xelatex + ctex) · poppler-utils</sub>

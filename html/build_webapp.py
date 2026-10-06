"""
构建脚本：把 webapp/ 下的 JS 模块 + libs/ 下的库 + HTML 模板
组装成单个 self-contained HTML 文件。

输出：/home/z/my-project/download/mathtext2doc-web.html
"""

import os
import re
import base64
import hashlib

# 路径基于本文件所在目录（html/），便于整体迁移
_HERE = os.path.dirname(os.path.abspath(__file__))
WEBAPP_DIR = os.path.join(_HERE, "webapp")
LIBS_DIR = os.path.join(_HERE, "webapp", "libs")
OUT_PATH = os.path.join(_HERE, "mathtext2doc-web.html")

# KaTeX 字体需要 inline 为 base64 data URL
FONTS_DIR = os.path.join(LIBS_DIR, "fonts")


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_lib(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def font_to_dataurl(font_path):
    """把字体文件转成 base64 data URL"""
    with open(font_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    return f"data:font/woff2;base64,{data}"


def patch_katex_css(css_text):
    """把 KaTeX CSS 里的 url(fonts/xxx.woff2) 替换为 base64 data URL"""
    def replacer(m):
        font_name = m.group(1)
        font_path = os.path.join(FONTS_DIR, font_name)
        if os.path.exists(font_path):
            return f"url('{font_to_dataurl(font_path)}')"
        return m.group(0)
    return re.sub(r"url\(fonts/([\w-]+\.woff2)\)", replacer, css_text)


def strip_es_module(js_text):
    """把 ES module 语法转成全局变量：
    - 去掉 `import { x } from './y.js'` 语句
    - 去掉 `export { a, b, c };` 整个块（这些名字已经是全局声明）
    - 去掉 `export ` 前缀（export function foo → function foo）
    """
    # 去掉 import 语句
    js_text = re.sub(
        r"^\s*import\s+\{[^}]+\}\s+from\s+['\"][^'\"]+['\"];?\s*$",
        "",
        js_text,
        flags=re.MULTILINE,
    )
    # 去掉 export { ... }; 块（多行）
    js_text = re.sub(
        r"^\s*export\s*\{[^}]*\};?\s*$",
        "",
        js_text,
        flags=re.MULTILINE,
    )
    # 去掉 export 前缀（export function / export class / export const 等）
    js_text = re.sub(r"^\s*export\s+", "", js_text, flags=re.MULTILINE)
    return js_text


def build():
    # 读取所有 JS 模块
    parser_js = read(os.path.join(WEBAPP_DIR, "parser.js"))
    plotter_js = read(os.path.join(WEBAPP_DIR, "plotter.js"))
    renderer_js = read(os.path.join(WEBAPP_DIR, "renderer.js"))
    exporter_js = read(os.path.join(WEBAPP_DIR, "exporter.js"))

    # 去 ES module 语法
    parser_js = strip_es_module(parser_js)
    plotter_js = strip_es_module(plotter_js)
    renderer_js = strip_es_module(renderer_js)
    exporter_js = strip_es_module(exporter_js)

    # 读取库
    katex_js = read_lib(os.path.join(LIBS_DIR, "katex.min.js"))
    katex_css = read_lib(os.path.join(LIBS_DIR, "katex.min.css"))
    auto_render_js = read_lib(os.path.join(LIBS_DIR, "auto-render.min.js"))
    jsxgraph_js = read_lib(os.path.join(LIBS_DIR, "jsxgraphcore.js"))
    jsxgraph_css = read_lib(os.path.join(LIBS_DIR, "jsxgraph.css"))
    html2canvas_js = read_lib(os.path.join(LIBS_DIR, "html2canvas.min.js"))

    # patch KaTeX CSS：字体转 base64
    katex_css = patch_katex_css(katex_css)

    # HTML 模板
    html = build_html({
        "katex_css": katex_css,
        "jsxgraph_css": jsxgraph_css,
        "katex_js": katex_js,
        "auto_render_js": auto_render_js,
        "jsxgraph_js": jsxgraph_js,
        "html2canvas_js": html2canvas_js,
        "parser_js": parser_js,
        "plotter_js": plotter_js,
        "renderer_js": renderer_js,
        "exporter_js": exporter_js,
    })

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    size_mb = os.path.getsize(OUT_PATH) / 1024 / 1024
    print(f"✅ 已生成：{OUT_PATH}")
    print(f"   体积：{size_mb:.2f} MB")


def build_html(parts):
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>mathtext2doc — 数学文本文档生成器</title>
<style>
{parts["katex_css"]}
{parts["jsxgraph_css"]}

/* 应用样式 */
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Noto Sans SC", "Microsoft YaHei", sans-serif;
  background: #f5f5f5; color: #222; line-height: 1.7;
}}
.app {{ display: flex; height: 100vh; }}
.editor-pane, .preview-pane {{ flex: 1; display: flex; flex-direction: column; overflow: hidden; }}
.editor-pane {{ position: relative; }}
.editor-pane {{ border-right: 1px solid #ddd; background: #fff; }}
.preview-pane {{ background: #e9e9e9; overflow-y: auto; }}

.toolbar {{
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  background: #2c3e50; color: #fff; flex-wrap: wrap;
}}
.toolbar h1 {{ font-size: 14px; font-weight: 500; margin-right: 16px; }}
.toolbar button {{
  background: #3498db; color: #fff; border: none; padding: 6px 14px;
  border-radius: 4px; cursor: pointer; font-size: 13px; transition: background .15s;
}}
.toolbar button:hover {{ background: #2980b9; }}
.toolbar button.success {{ background: #27ae60; }}
.toolbar button.success:hover {{ background: #229954; }}
.toolbar button.warn {{ background: #e67e22; }}
.toolbar button.warn:hover {{ background: #d35400; }}
.toolbar .spacer {{ flex: 1; }}
.toolbar label {{ font-size: 12px; opacity: .9; }}
.toolbar input[type=number], .toolbar input[type=range] {{ width: 60px; padding: 3px 6px; }}
.toolbar select {{ padding: 4px; }}

#editor {{
  flex: 1; width: 100%; border: none; padding: 16px;
  font-family: "Sarasa Mono SC", "Consolas", "Menlo", monospace;
  font-size: 14px; line-height: 1.6; resize: none; outline: none;
  tab-size: 2;
  transition: background .15s, box-shadow .15s;
}}
/* 拖拽悬浮反馈 */
#editor.dragover {{
  background: #e8f4fd;
  box-shadow: inset 0 0 0 3px #3498db;
}}
.editor-pane.dragover::before {{
  content: "📁 拖放 .txt / .md 文件到此处加载";
  position: absolute; inset: 60px 0 30px 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; color: #3498db; pointer-events: none;
  background: rgba(232, 244, 253, .9); z-index: 10;
  border: 3px dashed #3498db; margin: 8px;
}}

.preview-content {{
  background: #fff; max-width: 800px; margin: 24px auto; padding: 48px 56px;
  box-shadow: 0 2px 12px rgba(0,0,0,.1);
  min-height: calc(100vh - 96px);
  flex-shrink: 0;  /* 不被 flex 容器压缩，让背景跟随内容撑高 */
  box-sizing: border-box;
  width: 100%;     /* 配合 max-width 限制宽度 */
}}
.preview-content h1 {{ font-size: 24px; margin: 16px 0 12px; color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 6px; }}
.preview-content h2 {{ font-size: 19px; margin: 14px 0 10px; color: #34495e; }}
.preview-content h3 {{ font-size: 16px; margin: 12px 0 8px; color: #34495e; }}
.preview-content h4 {{ font-size: 14px; margin: 10px 0 6px; color: #555; font-weight: 600; }}
.preview-content p {{ margin: 8px 0; }}
.preview-content ul, .preview-content ol {{ margin: 8px 0 8px 24px; }}
.preview-content li {{ margin: 4px 0; }}
.preview-content blockquote {{ margin: 12px 0; padding: 8px 16px; border-left: 4px solid #3498db; background: #f8f9fa; color: #555; }}
.preview-content blockquote p {{ margin: 4px 0; }}
.preview-content hr {{ border: none; border-top: 1px solid #ddd; margin: 16px 0; }}
.preview-content em {{ font-style: italic; }}
.preview-content table {{ border-collapse: collapse; margin: 12px 0; width: 100%; }}
.preview-content th, .preview-content td {{ border: 1px solid #ddd; padding: 6px 12px; text-align: left; }}
.preview-content th {{ background: #f0f0f0; font-weight: 600; }}
.preview-content .display-math {{ margin: 12px 0; text-align: center; }}
.preview-content .plot-wrapper {{ margin: 16px 0; }}
.preview-content .plot-canvas {{ width: 100%; border: 1px solid #eee; }}
.preview-content code {{ background: #f4f4f4; padding: 1px 6px; border-radius: 3px; font-size: .9em; }}
.preview-content strong {{ color: #c0392b; }}

.status-bar {{
  padding: 4px 12px; background: #ecf0f1; font-size: 12px; color: #555;
  border-top: 1px solid #ddd;
}}
.error-msg {{ color: #c0392b; }}
.ok-msg {{ color: #27ae60; }}

/* 隐藏滚动条美化 */
.preview-pane::-webkit-scrollbar {{ width: 8px; }}
.preview-pane::-webkit-scrollbar-thumb {{ background: #bbb; border-radius: 4px; }}

/* 打印样式：只打印预览区 */
@media print {{
  body * {{ visibility: hidden; }}
  .preview-content, .preview-content * {{ visibility: visible; }}
  .preview-content {{
    position: absolute; left: 0; top: 0; width: 100%;
    box-shadow: none; max-width: none; margin: 0; padding: 24px;
  }}
  .toolbar, .editor-pane {{ display: none !important; }}
}}
</style>
</head>
<body>
<div class="app">
  <div class="editor-pane">
    <div class="toolbar">
      <h1>📝 mathtext2doc</h1>
      <button id="btn-render" class="success">▶ 渲染 (Ctrl+Enter)</button>
      <button id="btn-sample">📋 示例</button>
      <button id="btn-clear">🗑 清空</button>
      <div class="spacer"></div>
      <label>图宽 <input type="number" id="plot-width" value="0.7" min="0.1" max="1" step="0.1"></label>
      <label>DPI <input type="number" id="dpi" value="150" min="72" max="400" step="10"></label>
    </div>
    <textarea id="editor" spellcheck="false" placeholder="在此输入文本，或拖放 .txt / .md 文件到此处加载&#10;支持中文、Markdown、$...$ 公式、@plot{{...}} 绘图&#10;双击空白处可选择文件"></textarea>
    <div class="status-bar" id="status">就绪</div>
  </div>
  <div class="preview-pane">
    <div class="toolbar">
      <button id="btn-png" class="success">📥 下载 PNG（多页）</button>
      <button id="btn-plots" class="success">📊 导出函数图</button>
      <button id="btn-print">🖨 打印 / 存为 PDF</button>
      <button id="btn-tex" class="warn">📄 导出 .tex</button>
      <div class="spacer"></div>
      <span id="page-info"></span>
    </div>
    <div class="preview-content" id="preview"></div>
  </div>
</div>

<script>
// ====== 内联库 ======
// KaTeX
{parts["katex_js"]}
// KaTeX auto-render
{parts["auto_render_js"]}
// JSXGraph
{parts["jsxgraph_js"]}
// html2canvas
{parts["html2canvas_js"]}
</script>

<script>
// ====== 应用代码 ======
// parser.js
{parts["parser_js"]}

// plotter.js
{parts["plotter_js"]}

// renderer.js
{parts["renderer_js"]}

// exporter.js
{parts["exporter_js"]}

// ====== 主程序 ======
const editor = document.getElementById('editor');
const preview = document.getElementById('preview');
const statusBar = document.getElementById('status');
const pageInfo = document.getElementById('page-info');
let currentBlocks = null;
let renderTimer = null;

const SAMPLE = `# 三角函数与单位圆

这是一份示例文档，演示 **mathtext2doc** 的解析能力。文档同时包含中文、
基础 Markdown、LaTeX 公式和 @plot 绘图指令。

## 一、基础公式

欧拉公式描述了指数函数与三角函数之间的关系：

$$e^{{i\\pi}} + 1 = 0$$

它是数学中最优雅的等式之一，把五个基本常数 $e$、$i$、$\\pi$、$1$、$0$ 联系在一起。

## 二、三角函数图像

下面同时绘制 $\\sin(x)$ 与 $\\cos(x)$ 在 $[-\\pi, \\pi]$ 上的图像：

@plot{{
  y = sin(x), x in [-pi, pi], label="sin(x)";
  y = cos(x), x in [-pi, pi], label="cos(x)"
}}

## 三、几何图形

@plot{{
  shape=circle, center=(0, 0), r=2, label="圆 C";
  shape=point, at=(2, 0), label="P";
  shape=segment, from=(0, 0), to=(2, 0), label="半径 r"
}}

## 四、图宽控制

@plot(width=0.4){{
  y = sin(x), x in [-pi, pi], label="小图"
}}

@plot(width=0.9){{
  y = sin(x), x in [-pi, pi], label="大图"
}}

## 五、参数对比表

| 函数 | 定义域 | 值域 | 周期 |
| --- | --- | --- | --- |
| $\\sin(x)$ | $\\mathbb{{R}}$ | $[-1, 1]$ | $2\\pi$ |
| $\\cos(x)$ | $\\mathbb{{R}}$ | $[-1, 1]$ | $2\\pi$ |
`;

function setStatus(msg, isErr = false) {{
  statusBar.textContent = msg;
  statusBar.className = 'status-bar ' + (isErr ? 'error-msg' : 'ok-msg');
}}

let _rendering = false;  // 防重入锁
let _renderTimer = null;
function doRender() {{
  if (_rendering) return;  // 上一次渲染未完成，跳过
  const text = editor.value;
  if (!text.trim()) {{
    preview.innerHTML = '<p style="color:#999;text-align:center;padding:48px">在左侧输入文本即可预览</p>';
    currentBlocks = null;
    setStatus('空文档');
    return;
  }}
  _rendering = true;
  setStatus(`⏳ 渲染中...（${{text.length}} 字符）`);
  // 保险：5 秒后强制释放锁，避免异常导致永久卡死
  if (_renderTimer) clearTimeout(_renderTimer);
  _renderTimer = setTimeout(() => {{
    if (_rendering) {{
      _rendering = false;
      setStatus('✗ 渲染超时（5秒），请减少内容或检查语法', true);
    }}
  }}, 5000);
  // 用 setTimeout 让 UI 先更新状态栏，避免大文档渲染时页面无响应
  setTimeout(() => {{
    try {{
      currentBlocks = parseDocument(text);
      const defaultWidth = parseFloat(document.getElementById('plot-width').value) || 0.7;
      renderDocument(currentBlocks, preview, {{ defaultWidth }});
      setStatus(`✓ 渲染成功，共 ${{currentBlocks.length}} 个块`);
    }} catch (ex) {{
      setStatus(`✗ ${{ex.message}}`, true);
      console.error(ex);
    }} finally {{
      _rendering = false;
      if (_renderTimer) {{ clearTimeout(_renderTimer); _renderTimer = null; }}
    }}
  }}, 30);
}}

editor.addEventListener('input', () => {{
  clearTimeout(renderTimer);
  renderTimer = setTimeout(doRender, 300);
}});

editor.addEventListener('keydown', (e) => {{
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {{
    e.preventDefault(); doRender();
  }}
}});

// ====== 拖拽上传 ======
const editorPane = document.querySelector('.editor-pane');

// 全局阻止默认拖拽行为（避免浏览器打开文件导致页面导航走）
// 必须在 document 级别阻止，否则拖到非 editor 区域时 Edge 会打开文件
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => {{
  document.addEventListener(ev, (e) => {{ e.preventDefault(); e.stopPropagation(); }}, false);
}});
// editorPane 上额外阻止一次（确保 drop 能被处理）
['dragenter', 'dragover', 'drop'].forEach(ev => {{
  editorPane.addEventListener(ev, (e) => {{ e.preventDefault(); e.stopPropagation(); }}, false);
}});

// 拖进编辑器区：显示视觉反馈
editorPane.addEventListener('dragenter', (e) => {{
  editorPane.classList.add('dragover');
  editor.classList.add('dragover');
}});
editorPane.addEventListener('dragover', (e) => {{
  editorPane.classList.add('dragover');
  editor.classList.add('dragover');
  e.dataTransfer.dropEffect = 'copy';
}});
// 拖出：移除反馈（dragleave 检测离开整个 pane 才移除）
editorPane.addEventListener('dragleave', (e) => {{
  // 如果 relatedTarget 还在 pane 内，不移除
  if (!editorPane.contains(e.relatedTarget)) {{
    editorPane.classList.remove('dragover');
    editor.classList.remove('dragover');
  }}
}});

// 放下文件（用 FileReader 同步 API，避免 async/await 在 Edge 上的兼容问题）
editorPane.addEventListener('drop', (e) => {{
  // preventDefault 已在前面全局监听里调用，这里再保险一次
  e.preventDefault();
  e.stopPropagation();
  editorPane.classList.remove('dragover');
  editor.classList.remove('dragover');
  const files = e.dataTransfer.files;
  if (!files || !files.length) {{
    setStatus('✗ 未检测到文件', true);
    return;
  }}
  const file = files[0];
  const name = file.name.toLowerCase();
  const okExt = name.endsWith('.txt') || name.endsWith('.md') || name.endsWith('.markdown') || !name.includes('.');
  if (!okExt) {{
    setStatus(`✗ 不支持的文件类型：${{file.name}}（仅支持 .txt / .md）`, true);
    return;
  }}
  if (file.size > 1024 * 1024) {{
    setStatus(`✗ 文件过大（${{(file.size/1024).toFixed(0)}}KB > 1MB）`, true);
    return;
  }}
  setStatus(`⏳ 正在读取 ${{file.name}}...`);
  // 用 FileReader 读取（比 file.text() 兼容性更好）
  const reader = new FileReader();
  reader.onload = () => {{
    try {{
      let text = String(reader.result || '');
      // 规范化：去 BOM、统一换行符、去零宽字符
      text = text.replace(/^\\uFEFF/, '').replace(/\\r\\n/g, '\\n').replace(/\\r/g, '\\n');
      text = text.replace(/[\\u200B\\u200C\\u200D\\uFEFF]/g, '');
      editor.value = text;
      doRender();
    }} catch (ex) {{
      setStatus(`✗ 处理文件失败：${{ex.message}}`, true);
    }}
  }};
  reader.onerror = () => {{
    setStatus(`✗ 读取文件失败：${{reader.error && reader.error.message || '未知错误'}}`, true);
  }};
  reader.readAsText(file, 'utf-8');
}});

// 也支持点击编辑器选择文件（隐藏的 file input）
const fileInput = document.createElement('input');
fileInput.type = 'file';
fileInput.accept = '.txt,.md,.markdown,text/plain';
fileInput.style.display = 'none';
document.body.appendChild(fileInput);
fileInput.addEventListener('change', (e) => {{
  const file = e.target.files[0];
  if (!file) return;
  setStatus(`⏳ 正在读取 ${{file.name}}...`);
  const reader = new FileReader();
  reader.onload = () => {{
    try {{
      let text = String(reader.result || '');
      text = text.replace(/^\\uFEFF/, '').replace(/\\r\\n/g, '\\n').replace(/\\r/g, '\\n');
      text = text.replace(/[\\u200B\\u200C\\u200D\\uFEFF]/g, '');
      editor.value = text;
      doRender();
    }} catch (ex) {{
      setStatus(`✗ 处理文件失败：${{ex.message}}`, true);
    }}
  }};
  reader.onerror = () => {{
    setStatus(`✗ 读取文件失败`, true);
  }};
  reader.readAsText(file, 'utf-8');
}});
// 双击编辑器空白处触发文件选择
editor.addEventListener('dblclick', (e) => {{
  if (editor.value === '' || confirm('打开文件会覆盖当前内容，是否继续？')) {{
    fileInput.value = ''; fileInput.click();
  }}
}});

document.getElementById('btn-render').addEventListener('click', doRender);
document.getElementById('btn-sample').addEventListener('click', () => {{
  editor.value = SAMPLE; doRender();
}});
document.getElementById('btn-clear').addEventListener('click', () => {{
  editor.value = ''; doRender();
}});

document.getElementById('btn-tex').addEventListener('click', () => {{
  if (!currentBlocks) {{ alert('请先渲染文档'); return; }}
  const defaultWidth = parseFloat(document.getElementById('plot-width').value) || 0.7;
  const tex = generateTex(currentBlocks, {{ defaultWidth }});
  downloadText(tex, 'document.tex', 'text/x-tex');
  setStatus('✓ 已导出 .tex');
}});

document.getElementById('btn-png').addEventListener('click', async () => {{
  if (!currentBlocks) {{ alert('请先渲染文档'); return; }}
  const btn = document.getElementById('btn-png');
  btn.disabled = true; btn.textContent = '⏳ 渲染中...';
  try {{
    const dpi = parseInt(document.getElementById('dpi').value) || 150;
    const pages = await exportToPngPages(preview, {{ dpi }});
    for (let i = 0; i < pages.length; i++) {{
      downloadDataUrl(pages[i], `document-${{i+1}}.png`);
      await new Promise(r => setTimeout(r, 300));
    }}
    pageInfo.textContent = `已导出 ${{pages.length}} 张 PNG`;
    setStatus(`✓ 已导出 ${{pages.length}} 张 PNG`);
  }} catch (ex) {{
    setStatus(`✗ PNG 导出失败：${{ex.message}}。建议改用"打印"功能。`, true);
    console.error(ex);
  }} finally {{
    btn.disabled = false; btn.textContent = '📥 下载 PNG（多页）';
  }}
}});

document.getElementById('btn-plots').addEventListener('click', async () => {{
  if (!currentBlocks) {{ alert('请先渲染文档'); return; }}
  const btn = document.getElementById('btn-plots');
  btn.disabled = true; btn.textContent = '⏳ 导出中...';
  try {{
    const dpi = parseInt(document.getElementById('dpi').value) || 150;
    const canvases = await exportPlotCanvases(preview, {{ dpi }});
    for (const {{ idx, canvas }} of canvases) {{
      downloadDataUrl(canvas.toDataURL('image/png'), `plot-${{idx}}.png`);
      await new Promise(r => setTimeout(r, 300));
    }}
    setStatus(`✓ 已导出 ${{canvases.length}} 张函数图 PNG`);
  }} catch (ex) {{
    setStatus(`✗ 函数图导出失败：${{ex.message}}`, true);
  }} finally {{
    btn.disabled = false; btn.textContent = '📊 导出所有函数图';
  }}
}});

document.getElementById('btn-print').addEventListener('click', () => {{
  printDocument();
}});

// 初始化
editor.value = SAMPLE;
doRender();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()

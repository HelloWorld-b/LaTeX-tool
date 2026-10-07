/**
 * PNG 导出
 *
 * 浏览器 DOM→PNG 的现实方案：
 *   - html2canvas 在 file:// 协议下不可用（克隆 iframe 失败）
 *   - SVG foreignObject 大文档会卡死
 *   - 浏览器原生打印（Ctrl+P）最稳定
 *
 * 因此提供两种导出：
 *   1. exportPlotCanvases() — 单独导出每个 plot 为 PNG（SVG→Canvas，成熟技术）
 *   2. printDocument() — 调用浏览器打印，用户可选"保存为 PDF/PNG"
 *   3. exportToPngPages() — 尝试 foreignObject 方案（小文档可用，大文档可能失败）
 */

// ---------------------------------------------------------------------------
// SVG → dataURL（用于新页签预览，把 plot SVG 转成 <img> 避免依赖 JSXGraph）
// ---------------------------------------------------------------------------
function svgToDataUrl(svgEl, scale = 1) {
  return new Promise((resolve, reject) => {
    const rect = svgEl.getBoundingClientRect();
    const w = rect.width || 400, h = rect.height || 300;
    const clone = svgEl.cloneNode(true);
    clone.setAttribute('width', w);
    clone.setAttribute('height', h);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    // 移除 foreignObject（会导致 tainted）
    const foreigns = clone.querySelectorAll('foreignObject');
    for (const fo of foreigns) {
      const text = fo.textContent || '';
      const x = fo.getAttribute('x') || 0;
      const y = fo.getAttribute('y') || 0;
      const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      textEl.setAttribute('x', x);
      textEl.setAttribute('y', y);
      textEl.setAttribute('font-family', 'Arial, sans-serif');
      textEl.setAttribute('font-size', '12');
      textEl.setAttribute('fill', '#000');
      textEl.textContent = text;
      fo.parentNode.replaceChild(textEl, fo);
    }
    const svgData = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(w * scale));
      canvas.height = Math.max(1, Math.round(h * scale));
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL('image/png'));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('SVG 渲染失败')); };
    img.src = url;
  });
}

// ---------------------------------------------------------------------------
// 单个 SVG → Canvas（plot 导出用）
// ---------------------------------------------------------------------------
function svgToCanvas(svgEl, scale = 1) {
  return new Promise((resolve, reject) => {
    const rect = svgEl.getBoundingClientRect();
    const w = rect.width || 400, h = rect.height || 300;
    const clone = svgEl.cloneNode(true);
    clone.setAttribute('width', w);
    clone.setAttribute('height', h);
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    // 移除所有 foreignObject（会导致 canvas tainted）
    // 把 foreignObject 里的文本提取出来，转成 <text> 元素
    const foreigns = clone.querySelectorAll('foreignObject');
    for (const fo of foreigns) {
      // 提取文本内容
      const text = fo.textContent || '';
      const x = fo.getAttribute('x') || 0;
      const y = fo.getAttribute('y') || 0;
      // 创建 <text> 替代
      const textEl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      textEl.setAttribute('x', x);
      textEl.setAttribute('y', y);
      textEl.setAttribute('font-family', 'Arial, sans-serif');
      textEl.setAttribute('font-size', '12');
      textEl.setAttribute('fill', '#000');
      textEl.textContent = text;
      fo.parentNode.replaceChild(textEl, fo);
    }
    const svgData = new XMLSerializer().serializeToString(clone);
    const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(w * scale));
      canvas.height = Math.max(1, Math.round(h * scale));
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('SVG 渲染失败'));
    };
    img.src = url;
  });
}

/**
 * 导出所有 plot 为单独的 PNG
 */
export async function exportPlotCanvases(sourceEl, opts = {}) {
  const dpi = opts.dpi ?? 150;
  const scale = dpi / 96;
  const plotDivs = sourceEl.querySelectorAll('.plot-canvas');
  const canvases = [];
  for (let i = 0; i < plotDivs.length; i++) {
    const svg = plotDivs[i].querySelector('svg');
    if (!svg) continue;
    try {
      const canvas = await svgToCanvas(svg, scale);
      canvases.push({ idx: i + 1, canvas });
    } catch (e) {
      console.warn(`plot ${i+1} 导出失败:`, e);
    }
  }
  return canvases;
}

// ---------------------------------------------------------------------------
// 整篇文档 → PNG（foreignObject 方案，小文档可用）
// ---------------------------------------------------------------------------
async function domToCanvas(sourceEl, scale = 1) {
  const rect = sourceEl.getBoundingClientRect();
  const width = Math.ceil(rect.width);
  const height = Math.ceil(sourceEl.scrollHeight);

  // 把 plot SVG 转成 <img dataURL>
  const plotDivs = sourceEl.querySelectorAll('.plot-canvas');
  const plotImgs = [];
  for (const div of plotDivs) {
    const svg = div.querySelector('svg');
    if (!svg) continue;
    try {
      const canvas = await svgToCanvas(svg, scale);
      plotImgs.push({ div, dataUrl: canvas.toDataURL('image/png') });
    } catch (e) {}
  }

  // 克隆 DOM
  const clone = sourceEl.cloneNode(true);
  const cloneDivs = clone.querySelectorAll('.plot-canvas');
  for (let i = 0; i < cloneDivs.length && i < plotImgs.length; i++) {
    const div = cloneDivs[i];
    const svg = div.querySelector('svg');
    if (svg) {
      const img = document.createElement('img');
      img.src = plotImgs[i].dataUrl;
      img.style.width = '100%';
      img.style.height = 'auto';
      img.style.display = 'block';
      div.replaceChild(img, svg);
    }
  }

  // 收集样式
  let styles = '';
  for (const sheet of document.styleSheets) {
    try {
      for (const rule of sheet.cssRules) {
        styles += rule.cssText + '\n';
      }
    } catch (e) {}
  }

  const xhtml = new XMLSerializer().serializeToString(clone);
  // 限制大小，避免卡死
  if (xhtml.length > 500000) {
    throw new Error('文档过大，foreignObject 渲染会卡死浏览器。请用"打印"功能或减少内容。');
  }

  const svgStr = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}">
<foreignObject width="100%" height="100%">
<html xmlns="http://www.w3.org/1999/xhtml">
<style>${styles}</style>
<body style="margin:0;background:#fff;">${xhtml}</body>
</html>
</foreignObject>
</svg>`;

  const svgBlob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svgBlob);

  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = width * scale;
      canvas.height = height * scale;
      const ctx = canvas.getContext('2d');
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      resolve(canvas);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('文档渲染失败（可能是内容含跨域元素）'));
    };
    img.src = url;
  });
}

export async function exportToPngPages(sourceEl, opts = {}) {
  const dpi = opts.dpi ?? 150;
  const scale = dpi / 96;
  const pageW = Math.round(794 * scale);
  const pageH = Math.round(1123 * scale);

  const fullCanvas = await domToCanvas(sourceEl, scale);

  const pages = [];
  const totalH = fullCanvas.height;
  const totalPages = Math.max(1, Math.ceil(totalH / pageH));
  for (let p = 0; p < totalPages; p++) {
    const canvas = document.createElement('canvas');
    canvas.width = pageW;
    canvas.height = pageH;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, pageW, pageH);
    const sy = p * pageH;
    const sh = Math.min(pageH, totalH - sy);
    ctx.drawImage(fullCanvas, 0, sy, pageW, sh, 0, 0, pageW, sh);
    pages.push(canvas.toDataURL('image/png'));
  }
  return pages;
}

/**
 * 打印文档（调用浏览器原生打印，最稳定）
 */
export function printDocument() {
  window.print();
}

export function downloadDataUrl(dataUrl, filename) {
  const a = document.createElement('a');
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

export function downloadText(text, filename, mime = 'text/plain') {
  const blob = new Blob([text], { type: mime + ';charset=utf-8' });
  const url = URL.createObjectURL(blob);
  downloadDataUrl(url, filename);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

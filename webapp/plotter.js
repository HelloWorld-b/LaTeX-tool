/**
 * JSXGraph 绘图层
 * 渲染：显函数 y=f(x)、隐函数 F(x,y)=0、9 种几何图形
 * 移植自 Python plotter.py 的功能
 */

const COLORS = ['#1f77b4', '#d62728', '#2ca02c', '#ff7f0e', '#9467bd', '#17becf', '#8c564b', '#e377c2'];

// 全局设置：用 SVG <text> 而非 foreignObject，避免 canvas tainted
if (typeof JXG !== 'undefined' && JXG.Options && JXG.Options.text) {
  JXG.Options.text.display = 'internal';
  JXG.Options.text.fontUnit = 'px';
}

// 把用户表达式转成 JS 可执行函数
// sympy 不在浏览器端，所以我们用 new Function + Math 命名空间
function compileExpr(expr) {
  // ^ → ** , 把数学函数名映射到 Math.xxx
  let js = expr.split('^').join('**');
  // 替换函数名：sin -> Math.sin 等
  const fnMap = {
    sin: 'Math.sin', cos: 'Math.cos', tan: 'Math.tan',
    asin: 'Math.asin', acos: 'Math.acos', atan: 'Math.atan',
    exp: 'Math.exp', sqrt: 'Math.sqrt', abs: 'Math.abs',
    log: 'Math.log', ln: 'Math.log', log10: '(x=>Math.log(x)/Math.log(10))',
  };
  for (const [name, rep] of Object.entries(fnMap)) {
    const re = new RegExp(`\\b${name}\\b`, 'g');
    js = js.replace(re, rep);
  }
  // pi -> Math.PI, e -> Math.E
  js = js.replace(/\bpi\b/g, 'Math.PI').replace(/\be\b/g, 'Math.E');
  return js;
}

function makeFunction1D(expr) {
  // 显函数 y = f(x)：返回 (x) => y
  const js = compileExpr(expr);
  try {
    return new Function('x', `"use strict"; return (${js});`);
  } catch (ex) {
    throw new Error(`表达式编译失败：${expr} — ${ex.message}`);
  }
}

function makeFunction2D(expr) {
  // 隐函数 F(x,y) = 0：移项为 F(x,y) - 0，返回 (x,y) => z
  const eqIdx = expr.indexOf('=');
  if (eqIdx === -1) throw new Error(`隐函数缺少 '='：${expr}`);
  const lhs = expr.slice(0, eqIdx);
  const rhs = expr.slice(eqIdx + 1);
  const F = `(${lhs}) - (${rhs})`;
  const js = compileExpr(F);
  try {
    return new Function('x', 'y', `"use strict"; return (${js});`);
  } catch (ex) {
    throw new Error(`隐函数编译失败：${expr} — ${ex.message}`);
  }
}

/**
 * 渲染一个 Plot 到指定容器
 * @param {Plot} plot - 解析后的 Plot 节点
 * @param {HTMLElement} container - DOM 容器
 * @param {number} displayWidth - 显示宽度（0~1，相对 paperwidth）
 */
export function renderPlot(plot, container, displayWidth = 0.7) {
  if (!plot.items.length) throw new Error('@plot 没有任何绘制项');

  // 清空容器
  container.innerHTML = '';

  // 计算坐标范围
  let xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
  let hasImplicit = false, hasShape = false;
  for (const it of plot.items) {
    if (it.kind === 'implicit') hasImplicit = true;
    if (it.kind === 'shape') hasShape = true;
    if (it.xRange) {
      xmin = Math.min(xmin, it.xRange[0]);
      xmax = Math.max(xmax, it.xRange[1]);
    }
    if (it.yRange) {
      ymin = Math.min(ymin, it.yRange[0]);
      ymax = Math.max(ymax, it.yRange[1]);
    }
  }
  if (!isFinite(xmin)) {
    // 纯几何图形无范围，用默认
    xmin = -5; xmax = 5; ymin = -5; ymax = 5;
  }
  if (!isFinite(ymin)) {
    // 纯显函数，y 自动估算（JSXGraph autoscale）
    ymin = undefined; ymax = undefined;
  }

  // 8% 边距
  if (isFinite(xmax) && isFinite(xmin)) {
    const pad = (xmax - xmin) * 0.08;
    xmin -= pad; xmax += pad;
  }
  if (isFinite(ymax) && isFinite(ymin)) {
    const pad = (ymax - ymin) * 0.08;
    ymin -= pad; ymax += pad;
  }

  // 创建 JSXGraph board
  // 显函数图：y 范围先用一个合理默认，渲染后让 JSXGraph autoscale
  let yLo = ymin, yHi = ymax;
  if (yLo === undefined || !isFinite(yLo)) {
    // 显函数图：先采样估算 y 范围
    let yMin = Infinity, yMax = -Infinity;
    for (const it of plot.items) {
      if (it.kind === 'explicit' && it.xRange) {
        try {
          const fn = makeFunction1D(it.expr.split('=').slice(1).join('=').trim());
          const [a, b] = it.xRange;
          for (let k = 0; k <= 50; k++) {
            const x = a + (b - a) * k / 50;
            const y = fn(x);
            if (isFinite(y)) { yMin = Math.min(yMin, y); yMax = Math.max(yMax, y); }
          }
        } catch (e) {}
      }
    }
    if (isFinite(yMin) && isFinite(yMax)) {
      const pad = (yMax - yMin) * 0.15 || 1;
      yLo = yMin - pad; yHi = yMax + pad;
    } else {
      yLo = -3; yHi = 3;
    }
  }
  const bbox = [xmax, yHi, xmin, yLo];
  const board = JXG.JSXGraph.initBoard(container.id, {
    boundingbox: bbox,
    axis: false,
    showCopyright: false,
    showNavigation: false,
    keepaspectratio: !!(hasImplicit || hasShape),
    pan: { enabled: false },
    zoom: { enabled: false },
    grid: { majorStep: 1, strokeColor: '#ddd', strokeWidth: 0.5 },
  });

  // 画坐标轴（教材风格）
  drawAxes(board, xmin, xmax, yLo, yHi);

  // 渲染每个 item
  for (let i = 0; i < plot.items.length; i++) {
    const item = plot.items[i];
    const color = COLORS[i % COLORS.length];
    try {
      if (item.kind === 'explicit') renderExplicit(board, item, color);
      else if (item.kind === 'implicit') renderImplicit(board, item, color, xmin, xmax, ymin, ymax);
      else if (item.kind === 'shape') renderShape(board, item, color);
    } catch (ex) {
      console.warn(`绘图项 ${i} 失败:`, ex);
    }
  }

  board.fullUpdate();
  return board;
}

function drawAxes(board, xmin, xmax, ymin, ymax) {
  // x 轴（y=0 处水平线，带箭头）
  board.create('arrow', [[xmin, 0], [xmax, 0]], {
    strokeColor: '#444', strokeWidth: 1, lastArrow: true,
    highlight: false, fixed: true,
  });
  // y 轴
  board.create('arrow', [[0, ymin], [0, ymax]], {
    strokeColor: '#444', strokeWidth: 1, lastArrow: true,
    highlight: false, fixed: true,
  });
  // 轴标签
  board.create('text', [xmax - (xmax - xmin) * 0.02, -0.1 * (ymax - ymin), 'x'], {
    anchorX: 'right', anchorY: 'top', fontSize: 13, color: '#222', fixed: true,
  });
  board.create('text', [0.02 * (xmax - xmin), ymax - 0.02 * (ymax - ymin), 'y'], {
    anchorX: 'left', anchorY: 'top', fontSize: 13, color: '#222', fixed: true,
  });
  // 原点 O
  if (xmin < 0 && xmax > 0 && ymin < 0 && ymax > 0) {
    board.create('text', [0.02 * (xmax - xmin), -0.02 * (ymax - ymin), 'O'], {
      anchorX: 'left', anchorY: 'bottom', fontSize: 11, color: '#222', fixed: true,
    });
  }
  // 网格
  // JSXGrid 默认无网格，手动加
}

function renderExplicit(board, item, color) {
  const [a, b] = item.xRange;
  const expr = item.expr.split('=')[1].trim();  // y = ... → ...
  const fn = makeFunction1D(expr);
  // JSXGraph functiongraph
  const curve = board.create('functiongraph', [fn, a, b], {
    strokeColor: color, strokeWidth: 2, highlight: false,
  });
  // 标签：曲线中点
  if (item.label) {
    const midX = (a + b) / 2;
    let midY = 0;
    try { midY = fn(midX); } catch (e) {}
    board.create('text', [midX, midY + 0.2, item.label], {
      color: color, fontSize: 12, anchorX: 'middle', anchorY: 'bottom',
      fixed: true,
    });
  }
}

function renderImplicit(board, item, color, xmin, xmax, ymin, ymax) {
  const fn = makeFunction2D(item.expr);
  // JSXGraph 没有原生隐函数，用 contour 近似
  // 采样网格，找符号变化点画线段
  const n = 80;
  const dx = (xmax - xmin) / n;
  const dy = (ymax - ymin) / n;
  const points = [];
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const x1 = xmin + i * dx, x2 = x1 + dx;
      const y1 = ymin + j * dy, y2 = y1 + dy;
      try {
        const z11 = fn(x1, y1), z12 = fn(x1, y2), z21 = fn(x2, y1), z22 = fn(x2, y2);
        if (!isFinite(z11) || !isFinite(z12) || !isFinite(z21) || !isFinite(z22)) continue;
        // marching squares 简化版：找符号变化
        const segs = marchingSquares(x1, x2, y1, y2, z11, z12, z21, z22);
        for (const seg of segs) points.push(seg);
      } catch (e) {}
    }
  }
  // 画所有线段
  for (const [p1, p2] of points) {
    board.create('segment', [p1, p2], {
      strokeColor: color, strokeWidth: 2, highlight: false, fixed: true,
      lastArrow: false,
    });
  }
  // 标签
  if (item.label && points.length) {
    const mid = points[Math.floor(points.length / 2)][0];
    board.create('text', [mid[0], mid[1] + 0.2, item.label], {
      color: color, fontSize: 12, anchorX: 'middle', anchorY: 'bottom', fixed: true,
    });
  }
}

function marchingSquares(x1, x2, y1, y2, z11, z12, z21, z22) {
  // 返回符号变化处的线段端点列表
  const segs = [];
  const code = (z11 > 0 ? 1 : 0) | (z12 > 0 ? 2 : 0) | (z22 > 0 ? 4 : 0) | (z21 > 0 ? 8 : 0);
  if (code === 0 || code === 15) return segs;
  const lerp = (a, b, za, zb) => a + (b - a) * (-za / (zb - za));
  // 四条边的中点
  const top = [lerp(x1, x2, z11, z21), y2];
  const right = [x2, lerp(y2, y1, z21, z22)];
  const bottom = [lerp(x1, x2, z12, z22), y1];
  const left = [x1, lerp(y2, y1, z11, z12)];
  const cases = {
    1: [[left, top]], 2: [[top, right]], 3: [[left, right]],
    4: [[right, bottom]], 5: [[left, top], [right, bottom]],
    6: [[top, bottom]], 7: [[left, bottom]],
    8: [[left, bottom]], 9: [[top, bottom]],
    10: [[left, bottom], [top, right]], 11: [[right, bottom]],
    12: [[left, right]], 13: [[top, right]], 14: [[left, top]],
  };
  return cases[code] || segs;
}

function renderShape(board, item, color) {
  const { shape, params, label } = item;
  let anchor = null;
  const opts = { strokeColor: color, strokeWidth: 2, fillColor: color, fillOpacity: 0.1, highlight: false, fixed: true };
  const textOpts = { color, fontSize: 12, anchorX: 'middle', anchorY: 'bottom', fixed: true };

  if (shape === 'point') {
    const [x, y] = params.at;
    board.create('point', [x, y], { name: '', size: 4, fillColor: color, strokeColor: color, fixed: true });
    anchor = [x, y + 0.2];
  } else if (shape === 'segment') {
    board.create('segment', [params.from, params.to], opts);
    anchor = [(params.from[0] + params.to[0]) / 2, (params.from[1] + params.to[1]) / 2 + 0.2];
  } else if (shape === 'line') {
    board.create('line', [params.from, params.to], { ...opts, straightFirst: true, straightLast: true });
    anchor = [(params.from[0] + params.to[0]) / 2, (params.from[1] + params.to[1]) / 2 + 0.2];
  } else if (shape === 'circle') {
    board.create('circle', [params.center, params.r], opts);
    anchor = [params.center[0], params.center[1] + params.r + 0.2];
  } else if (shape === 'ellipse') {
    board.create('ellipse', [params.center, params.a, params.b], opts);
    anchor = [params.center[0], params.center[1] + params.b + 0.2];
  } else if (shape === 'polygon') {
    board.create('polygon', params.points, { ...opts, vertices: { visible: false }, borders: opts });
    for (const p of params.points) {
      board.create('point', p, { name: '', size: 3, fillColor: color, strokeColor: color, fixed: true });
    }
    const cx = params.points.reduce((s, p) => s + p[0], 0) / params.points.length;
    const cy = params.points.reduce((s, p) => s + p[1], 0) / params.points.length;
    anchor = [cx, cy + 0.2];
  } else if (shape === 'rectangle') {
    const [x0, y0] = params.origin;
    const w = params.w, h = params.h;
    const pts = [[x0, y0], [x0 + w, y0], [x0 + w, y0 + h], [x0, y0 + h]];
    board.create('polygon', pts, { ...opts, vertices: { visible: false }, borders: opts });
    anchor = [x0 + w / 2, y0 + h + 0.2];
  } else if (shape === 'vector') {
    board.create('arrow', [params.from, params.to], { ...opts, strokeWidth: 2.5, lastArrow: true });
    anchor = [(params.from[0] + params.to[0]) / 2, (params.from[1] + params.to[1]) / 2 + 0.2];
  } else if (shape === 'parabola') {
    const [h, k] = params.vertex;
    const p = params.p;
    const dir = (params.direction || 'up').toLowerCase();
    const span = Math.abs(p) * 4 + 1.5;
    if (dir === 'up' || dir === 'down') {
      const sign = dir === 'up' ? 1 : -1;
      const fn = (x) => sign * (x - h) ** 2 / (4 * p) + k;
      board.create('functiongraph', [fn, h - span, h + span], opts);
      anchor = [h, k + sign * Math.abs(p) + 0.2];
    } else {
      const sign = dir === 'right' ? 1 : -1;
      const fn = (y) => sign * (y - k) ** 2 / (4 * p) + h;
      // 用参数曲线画
      board.create('curve', [(t) => fn(t), (t) => t, k - span, k + span], opts);
      anchor = [h + sign * Math.abs(p), k];
    }
  }

  if (label && anchor) {
    board.create('text', [anchor[0], anchor[1], label], textOpts);
  }
}

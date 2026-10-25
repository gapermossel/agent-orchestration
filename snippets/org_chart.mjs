/* Org chart connectors and pan / pinch / wheel zoom, DOM + SVG only.
   Excerpt from the order-of-battle view of an internal operations dashboard
   (vanilla JS, no framework, no WebGL, strict CSP). Shown here as a
   self-contained excerpt.

   - Units are laid out by ordinary CSS (flex rows that wrap on a phone).
   - Connector lines are then measured from the DOM rects and drawn into one
     SVG in chart coordinates, so they stay correct at any zoom and wrap.
   - Children that wrap onto several rows get one bus per row, fed by a spine.
   - Pan, two-finger pinch and wheel zoom share one transform (translate + scale).

   Usage: createOrgChart({ viewport, stage, chart, svg, edges }) where edges is a
   list of [parentSelector, childrenSelector, spineOffsetPx]. */
export function createOrgChart(opts) {
  'use strict';
  var vp = opts.viewport, stage = opts.stage, chart = opts.chart, svg = opts.svg;
  var MIN_S = 0.3, MAX_S = 3;
  var st = { x: 0, y: 0, s: 1 }, segs = [];

  /* ---------- connectors (SVG in chart coordinates, computed from DOM rects) ---------- */
  function rel(el) {
    var r = el.getBoundingClientRect(), c = chart.getBoundingClientRect(), s = st.s;
    return { l: (r.left - c.left) / s, t: (r.top - c.top) / s, r: (r.right - c.left) / s, b: (r.bottom - c.top) / s,
      w: r.width / s, h: r.height / s, cx: (r.left + r.width / 2 - c.left) / s, cy: (r.top + r.height / 2 - c.top) / s };
  }
  // half-pixel offsets keep 1 px lines crisp
  function seg(x1, y1, x2, y2) { segs.push({ x1: Math.round(x1) + .5, y1: Math.round(y1) + .5, x2: Math.round(x2) + .5, y2: Math.round(y2) + .5 }); }

  // parent point (px,py) to child elements; children are grouped by wrapped row; extra rows are fed by a spine at spineX.
  function connect(px, py, kids, spineX) {
    var groups = [];
    kids.forEach(function (k) {
      var r = rel(k), G = groups.filter(function (g) { return Math.abs(g.top - r.t) < 4; })[0];
      if (!G) { G = { top: r.t, bottom: r.b, xs: [] }; groups.push(G); }
      G.xs.push(r.cx); G.bottom = Math.max(G.bottom, r.b);
    });
    groups.sort(function (a, b) { return a.top - b.top; });
    groups.forEach(function (G, i) {
      var busY = i === 0 ? py + (G.top - py) / 2 : groups[i - 1].bottom + (G.top - groups[i - 1].bottom) / 2;
      var lo = Math.min.apply(null, G.xs), hi = Math.max.apply(null, G.xs);
      if (i === 0) { seg(px, py, px, busY); lo = Math.min(lo, px); hi = Math.max(hi, px); }
      if (groups.length > 1) lo = Math.min(lo, spineX);
      if (hi - lo > 0.5) seg(lo, busY, hi, busY);
      G.xs.forEach(function (x) { seg(x, busY, x, G.top); });
      G.busY = busY;
    });
    if (groups.length > 1) seg(spineX, groups[0].busY, spineX, groups[groups.length - 1].busY);
  }

  function wire() {
    segs = [];
    var cr = rel(chart);
    opts.edges.forEach(function (e) {
      var parent = chart.querySelector(e[0]), kids = [].slice.call(chart.querySelectorAll(e[1]));
      if (!parent || !kids.length) return;
      var p = rel(parent);
      connect(p.cx, p.b, kids, cr.l + (e[2] || 8));
    });
    var W = Math.ceil(cr.w), H = Math.ceil(cr.h);
    svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
    svg.innerHTML = segs.map(function (g) { return '<path d="M' + g.x1 + ' ' + g.y1 + 'L' + g.x2 + ' ' + g.y2 + '"/>'; }).join('');
  }

  /* ---------- transform ---------- */
  var natW = 0, natH = 0, raf = 0;
  function apply() { stage.style.transform = 'translate(' + st.x.toFixed(2) + 'px,' + st.y.toFixed(2) + 'px) scale(' + st.s.toFixed(4) + ')'; }
  function schedule() { if (!raf) raf = requestAnimationFrame(function () { raf = 0; apply(); }); }
  function clampPan() {   // never let the chart leave the viewport entirely
    var vw = vp.clientWidth, vh = vp.clientHeight, w = natW * st.s, h = natH * st.s, m = 80;
    st.x = Math.min(vw - m, Math.max(m - w, st.x)); st.y = Math.min(vh - m, Math.max(m - h, st.y));
  }
  function layout() {     // measure at scale 1, draw wires, then restore the view
    var held = { x: st.x, y: st.y, s: st.s }; st.s = 1; apply();
    natW = chart.offsetWidth; natH = chart.offsetHeight;
    wire();
    st = held; apply();
  }
  function fit() {
    var vw = vp.clientWidth, vh = vp.clientHeight, s = Math.min(1, vw / natW, vh / natH);
    st.s = s; st.x = (vw - natW * s) / 2; st.y = natH * s < vh ? (vh - natH * s) / 2 : 0; apply();
  }
  function zoomAt(px, py, f) {   // zoom about a screen point so it stays under the cursor
    var s2 = Math.min(MAX_S, Math.max(MIN_S, st.s * f)), k = s2 / st.s;
    st.x = px - (px - st.x) * k; st.y = py - (py - st.y) * k; st.s = s2;
    clampPan(); schedule();
  }

  /* ---------- pointer: pan with one finger or mouse, pinch with two ---------- */
  var ptrs = new Map(), g = null;
  function vpPt(e) { var r = vp.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  function two() { var it = ptrs.values(); return [it.next().value, it.next().value]; }
  vp.addEventListener('pointerdown', function (e) {
    if (e.button && e.button !== 0) return;
    if (e.isPrimary) ptrs.clear();           // a new primary pointer means earlier contacts ended, even if pointerup was lost
    ptrs.set(e.pointerId, vpPt(e));
    try { vp.setPointerCapture(e.pointerId); } catch (x) { /* ignore */ }
    if (ptrs.size === 1) g = { mode: 'pan', start: vpPt(e), x0: st.x, y0: st.y, moved: false };
    else if (ptrs.size === 2) {
      var p = two();
      g = { mode: 'pinch', d0: Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1, s0: st.s, x0: st.x, y0: st.y,
        m0: { x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 } };
    }
  });
  vp.addEventListener('pointermove', function (e) {
    if (!ptrs.has(e.pointerId) || !g) return;
    ptrs.set(e.pointerId, vpPt(e));
    if (g.mode === 'pan' && ptrs.size === 1) {
      var p = ptrs.get(e.pointerId), dx = p.x - g.start.x, dy = p.y - g.start.y;
      if (!g.moved && Math.hypot(dx, dy) > 6) g.moved = true;     // small jitter is still a tap
      if (g.moved) { st.x = g.x0 + dx; st.y = g.y0 + dy; clampPan(); schedule(); }
    } else if (g.mode === 'pinch' && ptrs.size === 2) {
      var q = two(), d = Math.hypot(q[0].x - q[1].x, q[0].y - q[1].y), m = { x: (q[0].x + q[1].x) / 2, y: (q[0].y + q[1].y) / 2 };
      var s2 = Math.min(MAX_S, Math.max(MIN_S, g.s0 * d / g.d0)), wx = (g.m0.x - g.x0) / g.s0, wy = (g.m0.y - g.y0) / g.s0;
      st.s = s2; st.x = m.x - wx * s2; st.y = m.y - wy * s2; clampPan(); schedule();
    }
  });
  function endPtr(e) { if (ptrs.delete(e.pointerId)) g = null; }
  vp.addEventListener('pointerup', endPtr);
  vp.addEventListener('pointercancel', endPtr);
  vp.addEventListener('wheel', function (e) { e.preventDefault(); var p = vpPt(e); zoomAt(p.x, p.y, Math.exp(-e.deltaY * 0.0015)); }, { passive: false });

  var rt = 0;
  window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(function () { layout(); fit(); }, 120); });
  layout(); fit();
  return { layout: layout, fit: fit, zoomAt: zoomAt, state: function () { return { x: st.x, y: st.y, s: st.s }; } };
}

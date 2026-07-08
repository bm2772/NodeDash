// Obsidian-style force-directed graph on a Canvas. No dependencies.
// Departments are glowing dots; workflows are edges. Supports pan / zoom /
// drag / hover, and fires onNodeClick when a dot is clicked.

const COLORS = {
  internal: "#5c6bc0", // Muted canvas blue
  external: "#66bb6a", // Muted canvas green
  edge: "#444444",
  edgeHi: "#888888",
  label: "#888888",
  labelHi: "#e0e0e0",
  bg: "#1e1e1e",
};

// physics
const REPULSION = 80000;
const LINK_DIST = 350;
const SPRING = 0.001; 
const GRAVITY = 0.01;
const FRICTION = 0.9;

export class ForceGraph {
  constructor(canvas, { onNodeClick } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onNodeClick = onNodeClick || (() => {});
    this.nodes = [];
    this.edges = [];
    this.adj = new Map();

    this.scale = 1;
    this.offsetX = 0;
    this.offsetY = 0;
    this.alpha = 1;
    this.hoverId = null;
    this.centered = false;

    this._raf = null;
    this._pointer = null;      // active gesture
    this._bind();
  }

  setData(nodes, edges) {
    const R = (deg) => Math.max(7, Math.min(16, 7 + deg * 2));
    const degree = {};
    edges.forEach((e) => {
      degree[e.source] = (degree[e.source] || 0) + 1;
      degree[e.target] = (degree[e.target] || 0) + 1;
    });
    const n = nodes.length;
    this.nodes = nodes.map((nd, i) => {
      const ang = (i / Math.max(1, n)) * Math.PI * 2;
      return {
        ...nd,
        x: Math.cos(ang) * 400 + (Math.random() - 0.5) * 50,
        y: Math.sin(ang) * 400 + (Math.random() - 0.5) * 50,
        vx: 0, vy: 0, fixed: false,
        w: 180, h: 64, // Obsidian card dimensions
      };
    });
    this.edges = edges.slice();
    this.adj = new Map(this.nodes.map((nd) => [nd.id, new Set()]));
    edges.forEach((e) => {
      this.adj.get(e.source)?.add(e.target);
      this.adj.get(e.target)?.add(e.source);
    });
    this.alpha = 1;
    this.centered = false;
  }

  start() {
    if (this._raf) return;
    const loop = () => {
      this._tick();
      this._draw();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }
  stop() { if (this._raf) cancelAnimationFrame(this._raf); this._raf = null; }
  destroy() { this.stop(); this._unbind(); }

  // ---- geometry ----
  _resize() {
    const dpr = window.devicePixelRatio || 1;
    // Measure the PARENT (stable), never the canvas itself — sizing the canvas
    // buffer from its own rect creates a ResizeObserver feedback loop that grows
    // the element without bound.
    const host = this.canvas.parentElement || this.canvas;
    const rect = host.getBoundingClientRect();
    const w = Math.max(1, Math.round(rect.width));
    const h = Math.max(1, Math.round(rect.height));
    this.cssW = w; this.cssH = h;
    this.canvas.style.width = w + "px";
    this.canvas.style.height = h + "px";
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
    this.dpr = dpr;
    if (!this.centered && this.cssW > 0) {
      this.offsetX = this.cssW / 2;
      this.offsetY = this.cssH / 2;
      this.centered = true;
    }
  }
  _toWorld(sx, sy) { return { x: (sx - this.offsetX) / this.scale, y: (sy - this.offsetY) / this.scale }; }
  _nodeAt(sx, sy) {
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const nd = this.nodes[i];
      const hw = (nd.w / 2) * this.scale;
      const hh = (nd.h / 2) * this.scale;
      const nx = nd.x * this.scale + this.offsetX;
      const ny = nd.y * this.scale + this.offsetY;
      if (sx >= nx - hw && sx <= nx + hw && sy >= ny - hh && sy <= ny + hh) {
        return nd;
      }
    }
    return null;
  }

  // ---- physics ----
  _tick() {
    const nodes = this.nodes;
    if (!nodes.length) return;
    const fx = new Float64Array(nodes.length);
    const fy = new Float64Array(nodes.length);

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        let dx = nodes[i].x - nodes[j].x;
        let dy = nodes[i].y - nodes[j].y;
        let d2 = dx * dx + dy * dy || 0.01;
        const d = Math.sqrt(d2);
        const f = REPULSION / d2;
        const ux = dx / d, uy = dy / d;
        fx[i] += ux * f; fy[i] += uy * f;
        fx[j] -= ux * f; fy[j] -= uy * f;

        // strict rectangular collision
        const pad = 60;
        const minDx = (nodes[i].w + nodes[j].w) / 2 + pad;
        const minDy = (nodes[i].h + nodes[j].h) / 2 + pad;
        if (Math.abs(dx) < minDx && Math.abs(dy) < minDy) {
          const overlapX = minDx - Math.abs(dx);
          const overlapY = minDy - Math.abs(dy);
          if (overlapX < overlapY) {
            const push = overlapX * (dx > 0 ? 1 : -1);
            if (!nodes[i].fixed && !nodes[j].fixed) { nodes[i].x += push/2; nodes[j].x -= push/2; }
            else if (!nodes[i].fixed) nodes[i].x += push;
            else if (!nodes[j].fixed) nodes[j].x -= push;
          } else {
            const push = overlapY * (dy > 0 ? 1 : -1);
            if (!nodes[i].fixed && !nodes[j].fixed) { nodes[i].y += push/2; nodes[j].y -= push/2; }
            else if (!nodes[i].fixed) nodes[i].y += push;
            else if (!nodes[j].fixed) nodes[j].y -= push;
          }
        }
      }
    }
    const idx = new Map(nodes.map((n, i) => [n.id, i]));
    for (const e of this.edges) {
      const s = idx.get(e.source), t = idx.get(e.target);
      if (s === undefined || t === undefined) continue;
      let dx = nodes[t].x - nodes[s].x;
      let dy = nodes[t].y - nodes[s].y;
      const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const diff = ((d - LINK_DIST) / d) * SPRING;
      fx[s] += dx * diff; fy[s] += dy * diff;
      fx[t] -= dx * diff; fy[t] -= dy * diff;
    }
    for (let i = 0; i < nodes.length; i++) {
      fx[i] -= GRAVITY * nodes[i].x;
      fy[i] -= GRAVITY * nodes[i].y;
    }
    for (let i = 0; i < nodes.length; i++) {
      const nd = nodes[i];
      if (nd.fixed) { nd.vx = 0; nd.vy = 0; continue; }
      nd.vx = (nd.vx + fx[i] * this.alpha) * FRICTION;
      nd.vy = (nd.vy + fy[i] * this.alpha) * FRICTION;
      nd.x += nd.vx;
      nd.y += nd.vy;
    }
    if (this.alpha > 0.02) this.alpha *= 0.99;
  }
  _reheat() { this.alpha = Math.max(this.alpha, 0.5); }

  // ---- rendering ----
  _draw() {
    const ctx = this.ctx;
    if (!this.cssW) this._resize();
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.clearRect(0, 0, this.cssW, this.cssH);
    ctx.translate(this.offsetX, this.offsetY);
    ctx.scale(this.scale, this.scale);

    const pos = new Map(this.nodes.map((n) => [n.id, n]));
    const hi = this.hoverId;
    const nbrs = hi ? this.adj.get(hi) : null;

    // edges
    for (const e of this.edges) {
      const s = pos.get(e.source), t = pos.get(e.target);
      if (!s || !t) continue;
      const active = hi && (e.source === hi || e.target === hi);
      ctx.strokeStyle = active ? "#aaaaaa" : "#555555";
      ctx.lineWidth = active ? 3 : 1.5;
      
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      
      const sweep = Math.max(Math.abs(dx) * 0.5, Math.abs(dy) * 0.5, 120);
      
      let sx, sy, tx, ty, cp1x, cp1y, cp2x, cp2y, angle;
      if (Math.abs(dx) > Math.abs(dy)) {
        if (dx > 0) { sx = s.x + s.w/2; tx = t.x - t.w/2; angle = 0; }
        else { sx = s.x - s.w/2; tx = t.x + t.w/2; angle = Math.PI; }
        sy = s.y; ty = t.y;
        cp1x = sx + sweep * (dx > 0 ? 1 : -1); cp1y = sy;
        cp2x = tx - sweep * (dx > 0 ? 1 : -1); cp2y = ty;
      } else {
        if (dy > 0) { sy = s.y + s.h/2; ty = t.y - t.h/2; angle = Math.PI/2; }
        else { sy = s.y - s.h/2; ty = t.y + t.h/2; angle = -Math.PI/2; }
        sx = s.x; tx = t.x;
        cp1x = sx; cp1y = sy + sweep * (dy > 0 ? 1 : -1);
        cp2x = tx; cp2y = ty - sweep * (dy > 0 ? 1 : -1);
      }

      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, tx, ty);
      ctx.stroke();

      // Arrowhead
      ctx.fillStyle = ctx.strokeStyle;
      ctx.beginPath();
      ctx.translate(tx, ty);
      ctx.rotate(angle);
      ctx.moveTo(0, 0);
      ctx.lineTo(-10, -5);
      ctx.lineTo(-10, 5);
      ctx.closePath();
      ctx.fill();
      ctx.rotate(-angle);
      ctx.translate(-tx, -ty);

      const text = e.action_type || "";
      if (text) {
        const mx = 0.125*sx + 0.375*cp1x + 0.375*cp2x + 0.125*tx;
        const my = 0.125*sy + 0.375*cp1y + 0.375*cp2y + 0.125*ty;
        ctx.font = '11px "JetBrains Mono", monospace';
        const tw = ctx.measureText(text).width;
        
        ctx.fillStyle = COLORS.bg;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(mx - tw/2 - 8, my - 10, tw + 16, 20, 10);
        else ctx.rect(mx - tw/2 - 8, my - 10, tw + 16, 20);
        ctx.fill();
        
        ctx.strokeStyle = "rgba(255,255,255,0.15)";
        ctx.lineWidth = 1;
        ctx.stroke();

        ctx.fillStyle = active ? COLORS.labelHi : COLORS.label;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(text, mx, my);
      }
    }

    // nodes
    for (const nd of this.nodes) {
      const isHi = hi === nd.id;
      const dim = hi && !isHi && !(nbrs && nbrs.has(nd.id));
      const accent = COLORS[nd.type] || COLORS.internal;
      
      ctx.globalAlpha = dim ? 0.35 : 1;
      
      const hw = nd.w / 2;
      const hh = nd.h / 2;
      
      // Obsidian Card bg
      ctx.fillStyle = COLORS.bg;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(nd.x - hw, nd.y - hh, nd.w, nd.h, 6);
      } else {
        ctx.rect(nd.x - hw, nd.y - hh, nd.w, nd.h);
      }
      ctx.fill();
      
      // Border/Accent
      ctx.strokeStyle = isHi ? accent : "#333333";
      ctx.lineWidth = isHi ? 2 : 1;
      ctx.stroke();

      // Top colored bar / indicator (Obsidian style accent)
      ctx.fillStyle = accent;
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(nd.x - hw, nd.y - hh, nd.w, 4, {tl: 6, tr: 6, bl: 0, br: 0});
      } else {
        ctx.rect(nd.x - hw, nd.y - hh, nd.w, 4);
      }
      ctx.fill();

      // Title
      ctx.fillStyle = COLORS.labelHi;
      ctx.font = `500 13px "JetBrains Mono", monospace`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(nd.name, nd.x, nd.y);
      
      ctx.globalAlpha = 1;
    }
  }

  // ---- interaction ----
  _bind() {
    this._ro = new ResizeObserver(() => this._resize());
    this._ro.observe(this.canvas.parentElement || this.canvas);
    this._onDown = (ev) => this._down(ev);
    this._onMove = (ev) => this._move(ev);
    this._onUp = (ev) => this._up(ev);
    this._onWheel = (ev) => this._wheel(ev);
    this.canvas.addEventListener("pointerdown", this._onDown);
    window.addEventListener("pointermove", this._onMove);
    window.addEventListener("pointerup", this._onUp);
    this.canvas.addEventListener("wheel", this._onWheel, { passive: false });
  }
  _unbind() {
    this._ro?.disconnect();
    this.canvas.removeEventListener("pointerdown", this._onDown);
    window.removeEventListener("pointermove", this._onMove);
    window.removeEventListener("pointerup", this._onUp);
    this.canvas.removeEventListener("wheel", this._onWheel);
  }
  _rel(ev) {
    const rect = this.canvas.getBoundingClientRect();
    return { x: ev.clientX - rect.left, y: ev.clientY - rect.top };
  }
  _down(ev) {
    const p = this._rel(ev);
    const node = this._nodeAt(p.x, p.y);
    this._pointer = { startX: p.x, startY: p.y, lastX: p.x, lastY: p.y, node, moved: false };
    if (node) { node.fixed = true; this._reheat(); }
  }
  _move(ev) {
    const p = this._rel(ev);
    if (!this._pointer) {
      const node = this._nodeAt(p.x, p.y);
      const id = node ? node.id : null;
      if (id !== this.hoverId) { this.hoverId = id; this.canvas.style.cursor = id ? "pointer" : "grab"; }
      return;
    }
    const g = this._pointer;
    const dx = p.x - g.lastX, dy = p.y - g.lastY;
    if (Math.abs(p.x - g.startX) + Math.abs(p.y - g.startY) > 4) g.moved = true;
    if (g.node) {
      const w = this._toWorld(p.x, p.y);
      g.node.x = w.x; g.node.y = w.y; this._reheat();
    } else {
      this.offsetX += dx; this.offsetY += dy;
      this.canvas.style.cursor = "grabbing";
    }
    g.lastX = p.x; g.lastY = p.y;
  }
  _up(ev) {
    const g = this._pointer;
    if (!g) return;
    this._pointer = null;
    if (g.node) {
      g.node.fixed = false;
      if (!g.moved) this.onNodeClick(g.node);
    }
    this.canvas.style.cursor = this.hoverId ? "pointer" : "grab";
  }
  _wheel(ev) {
    ev.preventDefault();
    const p = this._rel(ev);
    const factor = ev.deltaY < 0 ? 1.1 : 1 / 1.1;
    const newScale = Math.max(0.3, Math.min(3, this.scale * factor));
    const w = this._toWorld(p.x, p.y);
    this.scale = newScale;
    this.offsetX = p.x - w.x * this.scale;
    this.offsetY = p.y - w.y * this.scale;
  }
}

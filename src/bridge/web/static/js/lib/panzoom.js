/* Zoom and move for an SVG picture, like a map: scroll to zoom around the pointer, drag the background to move,
   buttons for zoom in, zoom out and "fit everything". Used by the memory map and the helper graph. */

export class PanZoom {
  /**
   * svg: the <svg>; skip: CSS selector of things that handle their own pointer (nodes, ports);
   * min/max/maxFit: zoom limits. The drawing code calls setViewport(g, {w, h}) after each draw.
   */
  constructor(svg, { skip = "", min = 0.25, max = 2.5, maxFit = 1.2 } = {}) {
    this.svg = svg;
    this.skip = skip;
    this.min = min;
    this.max = max;
    this.maxFit = maxFit;
    this.view = { k: 1, x: 10, y: 10 };
    this.size = { w: 0, h: 0 };
    this.vp = null;
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      this.zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });
    svg.addEventListener("pointerdown", (e) => this.#startPan(e));
  }

  /** Tell the zoomer which <g> holds the drawing and how big the drawing is, then apply the current view. */
  setViewport(g, size) {
    this.vp = g;
    this.size = size || this.size;
    this.apply();
  }

  apply() {
    if (this.vp) this.vp.setAttribute("transform", `translate(${this.view.x} ${this.view.y}) scale(${this.view.k})`);
  }

  fit() {
    const r = this.svg.getBoundingClientRect();
    if (!r.width || !this.size.w) return;
    const k = Math.min((r.width - 20) / this.size.w, (r.height - 20) / this.size.h, this.maxFit);
    this.view = { k, x: Math.max(10, (r.width - this.size.w * k) / 2), y: 10 };
    this.apply();
  }

  /** Fit now, and again after the page has settled (the first measure can be taken before layout). */
  fitSoon() {
    this.fit();
    requestAnimationFrame(() => this.fit());
    setTimeout(() => this.fit(), 250);
  }

  zoomAt(factor, px, py) {
    const k2 = Math.min(this.max, Math.max(this.min, this.view.k * factor)), s = k2 / this.view.k;
    this.view = { k: k2, x: px - (px - this.view.x) * s, y: py - (py - this.view.y) * s };
    this.apply();
  }

  zoomCentre(factor) {
    const r = this.svg.getBoundingClientRect();
    this.zoomAt(factor, r.width / 2, r.height / 2);
  }

  /** A pointer event's position in the drawing's own coordinates (what the zoom undoes). */
  toDrawing(e) {
    const r = this.svg.getBoundingClientRect();
    return { x: (e.clientX - r.left - this.view.x) / this.view.k, y: (e.clientY - r.top - this.view.y) / this.view.k };
  }

  /** Wire three buttons: ids for zoom in, zoom out and fit. */
  bindButtons(zin, zout, fit) {
    zin.onclick = () => this.zoomCentre(1.25);
    zout.onclick = () => this.zoomCentre(1 / 1.25);
    fit.onclick = () => this.fit();
  }

  #startPan(e) {
    if (this.skip && e.target.closest && e.target.closest(this.skip)) return;
    const sx = e.clientX, sy = e.clientY, ox = this.view.x, oy = this.view.y;
    this.svg.style.cursor = "grabbing";
    const move = (ev) => { this.view.x = ox + ev.clientX - sx; this.view.y = oy + ev.clientY - sy; this.apply(); };
    const up = () => {
      this.svg.style.cursor = "";
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  }
}

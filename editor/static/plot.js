// Minimal multi-series SVG line plot for simulation results.
//
// No charting library, for the same reason there is no flow-canvas library: a
// few dozen lines of SVG beats a toolchain for what this needs. It draws what
// `/api/simulate` returns — already decimated server-side, so there is never
// more here than a plot can resolve.

const SVG_NS = "http://www.w3.org/2000/svg";

const PALETTE = [
  "#1f77b4", "#d62728", "#2ca02c", "#ff7f0e",
  "#9467bd", "#17becf", "#8c564b", "#e377c2",
];

const PAD = { left: 54, right: 12, top: 10, bottom: 26 };

function svg(tag, attrs = {}, text = "") {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text) node.textContent = text;
  return node;
}

/** A readable tick value near `v` (1, 2 or 5 times a power of ten). */
function nice(v) {
  if (v === 0) return "0";
  const abs = Math.abs(v);
  if (abs >= 1e4 || abs < 1e-3) return v.toExponential(1);
  return String(Number(v.toPrecision(3)));
}

export function colourFor(index) {
  return PALETTE[index % PALETTE.length];
}

/**
 * Draw `keys` from a `/api/simulate` response into `root` (an <svg>).
 * Returns the y-range actually drawn, which the caller reports and the tests
 * assert on.
 */
export function renderPlot(root, result, keys, size) {
  root.replaceChildren();
  // Render in the element's own pixel coordinates. A fixed viewBox stretched to
  // the container with preserveAspectRatio="none" scaled the horizontal axis far
  // more than the vertical one on a wide plot, which smeared the tick-label
  // glyphs. Matching the viewBox to the measured box keeps one user unit equal
  // to one CSS pixel, so text is drawn at its true aspect ratio (Simulink draws
  // scope tick labels at a fixed size independent of the plot-area shape).
  if (!size) {
    size = { width: root.clientWidth || 720, height: root.clientHeight || 260 };
  }
  root.setAttribute("viewBox", `0 0 ${size.width} ${size.height}`);

  const t = result.t || [];
  const series = keys
    .map((key, i) => ({ key, values: result.signals?.[key], colour: colourFor(i) }))
    .filter((s) => Array.isArray(s.values) && s.values.length === t.length);

  if (!t.length || !series.length) {
    root.appendChild(
      svg("text", {
        x: size.width / 2, y: size.height / 2,
        class: "plot-empty", "text-anchor": "middle",
      }, "no signals selected")
    );
    return null;
  }

  const flat = series.flatMap((s) => s.values);
  let lo = Math.min(...flat);
  let hi = Math.max(...flat);
  if (lo === hi) { lo -= 1; hi += 1; }            // a constant signal still needs a band
  const span = hi - lo;
  lo -= span * 0.06;
  hi += span * 0.06;

  const t0 = t[0];
  const t1 = t[t.length - 1];
  const px = (v) => PAD.left + ((v - t0) / (t1 - t0 || 1)) *
    (size.width - PAD.left - PAD.right);
  const py = (v) => size.height - PAD.bottom -
    ((v - lo) / (hi - lo)) * (size.height - PAD.top - PAD.bottom);

  // axes
  root.appendChild(svg("line", {
    x1: PAD.left, y1: size.height - PAD.bottom,
    x2: size.width - PAD.right, y2: size.height - PAD.bottom, class: "axis",
  }));
  root.appendChild(svg("line", {
    x1: PAD.left, y1: PAD.top, x2: PAD.left, y2: size.height - PAD.bottom, class: "axis",
  }));

  // a zero line, when zero is inside the range — the reference for a controller
  if (lo < 0 && hi > 0) {
    root.appendChild(svg("line", {
      x1: PAD.left, y1: py(0), x2: size.width - PAD.right, y2: py(0), class: "axis-zero",
    }));
  }

  for (const [value, anchor, dy] of [[hi, "end", 4], [lo, "end", 4]]) {
    root.appendChild(svg("text", {
      x: PAD.left - 6, y: py(value) + dy, class: "tick", "text-anchor": anchor,
    }, nice(value)));
  }
  for (const [value, anchor] of [[t0, "start"], [t1, "end"]]) {
    root.appendChild(svg("text", {
      x: px(value), y: size.height - PAD.bottom + 16, class: "tick",
      "text-anchor": anchor,
    }, `${nice(value)} s`));
  }

  for (const s of series) {
    const d = s.values
      .map((v, i) => `${i ? "L" : "M"} ${px(t[i]).toFixed(2)} ${py(v).toFixed(2)}`)
      .join(" ");
    root.appendChild(
      svg("path", { d, class: "series", stroke: s.colour, "data-series": s.key })
    );
  }

  attachCursor(root, { series, t, px, py, size, lo, hi });
  return { lo, hi, t0, t1, drawn: series.length };
}

/**
 * A data cursor, the way a MATLAB figure has one: hover and the plot tells you
 * the value under the pointer, snapped to a real sample rather than interpolated
 * off the pixel position.
 *
 * Reading a number off a curve by eye is the thing a static plot cannot do, and
 * it is the interaction people actually reach for — ahead of zoom, which the
 * axis controls already cover.
 */
function attachCursor(root, geom) {
  // An <svg> root only hit-tests where something is painted, so a pointer over
  // empty plot area reaches nothing. A transparent rect over the plotting
  // rectangle gives every position something to hit, and events bubble to root.
  root.appendChild(svg("rect", {
    x: PAD.left, y: PAD.top,
    width: Math.max(0, geom.size.width - PAD.left - PAD.right),
    height: Math.max(0, geom.size.height - PAD.top - PAD.bottom),
    class: "cursor-catcher",
  }));

  const layer = svg("g", { class: "cursor", "data-testid": "plot-cursor" });
  layer.setAttribute("visibility", "hidden");
  const rule = svg("line", { class: "cursor-rule", y1: PAD.top,
                             y2: geom.size.height - PAD.bottom });
  layer.appendChild(rule);
  const dots = geom.series.map((s) =>
    layer.appendChild(svg("circle", { r: 3, class: "cursor-dot", fill: s.colour })));
  const box = svg("g", { class: "cursor-readout" });
  const plate = svg("rect", { rx: 3, class: "cursor-plate" });
  const label = svg("text", { class: "cursor-label" });
  box.append(plate, label);
  layer.appendChild(box);
  root.appendChild(layer);

  const nearest = (x) => {
    // Binary search rather than a scan: a decimated run is still 1400 samples
    // and this runs on every pointer move.
    let lo = 0, hi = geom.t.length - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (geom.px(geom.t[mid]) < x) lo = mid; else hi = mid;
    }
    return Math.abs(geom.px(geom.t[lo]) - x) <= Math.abs(geom.px(geom.t[hi]) - x)
      ? lo : hi;
  };

  root.addEventListener("pointerleave", () => layer.setAttribute("visibility", "hidden"));
  root.addEventListener("pointermove", (event) => {
    const rect = root.getBoundingClientRect();
    // The plot is drawn in its own pixel coordinates, so the viewBox and the
    // element agree up to this one scale factor.
    const x = (event.clientX - rect.left) * (geom.size.width / rect.width);
    if (x < PAD.left || x > geom.size.width - PAD.right) {
      return layer.setAttribute("visibility", "hidden");
    }
    const i = nearest(x);
    const cx = geom.px(geom.t[i]);
    layer.setAttribute("visibility", "visible");
    layer.dataset.index = String(i);
    layer.dataset.t = String(geom.t[i]);
    rule.setAttribute("x1", cx);
    rule.setAttribute("x2", cx);

    label.replaceChildren();
    const rows = [`t = ${nice(geom.t[i])} s`,
                  ...geom.series.map((s) => `${s.key} = ${nice(s.values[i])}`)];
    rows.forEach((text, r) => {
      const line = svg("tspan", { x: 0, dy: r ? 12 : 0 }, text);
      if (r) line.setAttribute("fill", geom.series[r - 1].colour);
      label.appendChild(line);
    });
    geom.series.forEach((s, k) => {
      dots[k].setAttribute("cx", cx);
      dots[k].setAttribute("cy", geom.py(s.values[i]));
    });

    // Flip the readout to the other side of the rule near the right edge, so it
    // never runs off the plot.
    const w = 8.2 * Math.max(...rows.map((r) => r.length)) + 12;
    const left = cx + 10 + w > geom.size.width ? cx - 10 - w : cx + 10;
    box.setAttribute("transform", `translate(${left} ${PAD.top + 12})`);
    plate.setAttribute("x", -6);
    plate.setAttribute("y", -12);
    plate.setAttribute("width", w);
    plate.setAttribute("height", rows.length * 12 + 8);
  });
}

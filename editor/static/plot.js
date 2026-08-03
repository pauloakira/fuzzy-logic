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
export function renderPlot(root, result, keys, size = { width: 720, height: 260 }) {
  root.replaceChildren();
  root.setAttribute("viewBox", `0 0 ${size.width} ${size.height}`);
  root.setAttribute("preserveAspectRatio", "none");

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

  return { lo, hi, t0, t1, drawn: series.length };
}

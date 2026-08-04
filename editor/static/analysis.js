// SVG renderers for the linear-analysis charts: a Bode plot (magnitude and
// phase against log frequency) and a pole-zero map (the s-plane). They consume
// what `POST /api/analyze` returns and, like plot.js, draw raw SVG in the
// element's own pixel coordinates so the tick labels are never stretched.
//
// See docs/implementation-output-charts.md.

import { colourFor } from "/static/plot.js";

const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, text = "") {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== "") node.textContent = text;
  return node;
}

/** A readable tick value near `v` (three significant figures, compact). */
function nice(v) {
  if (v === 0) return "0";
  const abs = Math.abs(v);
  if (abs >= 1e4 || abs < 1e-3) return v.toExponential(1);
  return String(Number(v.toPrecision(3)));
}

/** `size`, from an explicit argument or the element's measured pixel box. */
function boxOf(root, size) {
  return size || { width: root.clientWidth || 720, height: root.clientHeight || 260 };
}

function emptyMessage(root, size, text) {
  root.appendChild(svg("text", {
    x: size.width / 2, y: size.height / 2,
    class: "plot-empty", "text-anchor": "middle",
  }, text));
}

/**
 * Draw an in-SVG legend, one row per entry. `marker` picks the sample glyph so a
 * row reads as what it labels: a curve, a pole (x) or a zero (o).
 */
function legend(root, entries, x, y) {
  entries.forEach((e, i) => {
    const yy = y + i * 14;
    if (e.marker === "pole") {
      root.appendChild(cross(x + 8, yy, 4, e.colour));
    } else if (e.marker === "zero") {
      root.appendChild(svg("circle", {
        cx: x + 8, cy: yy, r: 4, class: "pz-zero", stroke: e.colour,
      }));
    } else {
      root.appendChild(svg("line", {
        x1: x, y1: yy, x2: x + 16, y2: yy, class: "series", stroke: e.colour,
      }));
    }
    root.appendChild(svg("text", {
      x: x + 20, y: yy + 3.5, class: "tick", "text-anchor": "start",
    }, e.label));
  });
}

/** Width to reserve for a legend, from its longest label at the 11px tick size. */
function legendWidth(labels) {
  const longest = labels.reduce((n, l) => Math.max(n, String(l).length), 0);
  return 24 + longest * 6.2;
}

function cross(x, y, m, colour, attrs = {}) {
  const g = svg("g", attrs);
  g.appendChild(svg("line", {
    x1: x - m, y1: y - m, x2: x + m, y2: y + m, class: "pz-pole", stroke: colour,
  }));
  g.appendChild(svg("line", {
    x1: x - m, y1: y + m, x2: x + m, y2: y - m, class: "pz-pole", stroke: colour,
  }));
  return g;
}

/**
 * Every system's channels flattened into one list, each with a colour taken
 * from its position in that list.
 *
 * Both charts index this same list, so a colour means the same *channel* in the
 * Bode plot and on the s-plane. They used to disagree — the Bode plot coloured
 * per channel while the pole-zero map coloured per system — which drew the
 * velocity channel's zero in the position channel's colour.
 */
function channelsOf(systems) {
  const out = [];
  (systems || []).forEach((s) => {
    (s.channels || []).forEach((c) => {
      out.push({ ...c, system: s.name, omega: s.omega, colour: colourFor(out.length) });
    });
  });
  return out;
}

// ---- Bode ------------------------------------------------------------------

/**
 * Draw the Bode plot of every channel of every system into `root` (an <svg>).
 * Two stacked panels — magnitude [dB] and phase [deg] — over a shared log-ω
 * axis. Returns the number of channels drawn.
 */
export function renderBode(root, systems, size) {
  root.replaceChildren();
  size = boxOf(root, size);
  root.setAttribute("viewBox", `0 0 ${size.width} ${size.height}`);

  const channels = channelsOf(systems);

  if (!channels.length) {
    emptyMessage(root, size, "no LTI plant to analyse");
    return 0;
  }

  const PAD = { left: 52, right: 12, top: 12, bottom: 30 };
  const gap = 22;                       // between the two panels
  const plotW = size.width - PAD.left - PAD.right;
  const panelH = (size.height - PAD.top - PAD.bottom - gap) / 2;
  const magTop = PAD.top;
  const phaseTop = PAD.top + panelH + gap;

  // shared log-frequency range
  const lgx = (w) => Math.log10(w);
  let xlo = Infinity, xhi = -Infinity;
  for (const c of channels) {
    xlo = Math.min(xlo, lgx(c.omega[0]));
    xhi = Math.max(xhi, lgx(c.omega[c.omega.length - 1]));
  }
  const px = (w) => PAD.left + ((lgx(w) - xlo) / (xhi - xlo || 1)) * plotW;

  // Folded rather than spread: `Math.min(...vals)` passes every sample as an
  // argument, and `n_omega` reaches 4000 per channel, which overruns the
  // argument limit on a plant with enough channels.
  const range = (key) => {
    let lo = Infinity, hi = -Infinity;
    for (const c of channels) {
      for (const v of c[key]) {
        if (!Number.isFinite(v)) continue;   // a pole on the axis gives null
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
    if (!Number.isFinite(lo)) { lo = -1; hi = 1; }
    if (lo === hi) { lo -= 1; hi += 1; }
    const s = (hi - lo) * 0.06;
    return [lo - s, hi + s];
  };
  const [magLo, magHi] = range("mag_db");
  const [phLo, phHi] = range("phase_deg");

  const panel = (top, lo, hi, key, unit) => {
    const py = (v) => top + panelH - ((v - lo) / (hi - lo || 1)) * panelH;

    // frame
    root.appendChild(svg("line", { x1: PAD.left, y1: top, x2: PAD.left, y2: top + panelH, class: "axis" }));
    root.appendChild(svg("line", { x1: PAD.left, y1: top + panelH, x2: PAD.left + plotW, y2: top + panelH, class: "axis" }));

    // decade gridlines + x labels (only under the lower panel)
    const klo = Math.ceil(xlo), khi = Math.floor(xhi);
    for (let k = klo; k <= khi; k++) {
      const x = px(10 ** k);
      root.appendChild(svg("line", { x1: x, y1: top, x2: x, y2: top + panelH, class: "grid" }));
      if (key === "phase_deg") {
        root.appendChild(svg("text", {
          x, y: top + panelH + 14, class: "tick", "text-anchor": "middle",
        }, nice(10 ** k)));
      }
    }

    // y ticks (min, mid, max) and a zero reference line when in range
    for (const v of [hi, (lo + hi) / 2, lo]) {
      root.appendChild(svg("line", { x1: PAD.left, y1: py(v), x2: PAD.left + plotW, y2: py(v), class: "grid" }));
      root.appendChild(svg("text", {
        x: PAD.left - 6, y: py(v) + 3.5, class: "tick", "text-anchor": "end",
      }, nice(v)));
    }
    if (lo < 0 && hi > 0) {
      root.appendChild(svg("line", { x1: PAD.left, y1: py(0), x2: PAD.left + plotW, y2: py(0), class: "axis-zero" }));
    }
    root.appendChild(svg("text", { x: PAD.left, y: top - 2, class: "tick", "text-anchor": "start" }, unit));

    for (const c of channels) {
      const w = c.omega;
      const yv = c[key];
      const d = yv.map((v, i) =>
        `${i ? "L" : "M"} ${px(w[i]).toFixed(2)} ${py(Number.isFinite(v) ? v : hi).toFixed(2)}`
      ).join(" ");
      root.appendChild(svg("path", {
        d, class: "series", stroke: c.colour, "data-channel": c.label,
      }));
    }
  };

  panel(magTop, magLo, magHi, "mag_db", "magnitude [dB]");
  panel(phaseTop, phLo, phHi, "phase_deg", "phase [deg]");

  root.appendChild(svg("text", {
    x: PAD.left + plotW / 2, y: size.height - 4, class: "tick", "text-anchor": "middle",
  }, "frequency [rad/s]"));

  legend(root, channels.map((c) => ({ colour: c.colour, label: c.label })),
         PAD.left + plotW - legendWidth(channels.map((c) => c.label)), magTop + 8);
  return channels.length;
}

// ---- Pole-zero map ---------------------------------------------------------

/**
 * Draw the s-plane map of poles (×) and zeros (○) into `root`. Axes cross at the
 * origin with equal scale on both, so distances read true. Returns the number of
 * systems drawn.
 *
 * Poles belong to the *system* — they are the eigenvalues of `A`, shared by
 * every channel — so they are drawn once, in the neutral foreground. Zeros
 * belong to a single input/output *channel* and are drawn in that channel's Bode
 * colour: an SDOF plant's velocity channel has a zero at the origin while its
 * position channel has none, and the map has to say which is which.
 */
export function renderPoleZero(root, systems, size) {
  root.replaceChildren();
  size = boxOf(root, size);
  root.setAttribute("viewBox", `0 0 ${size.width} ${size.height}`);

  const channels = channelsOf(systems);
  const poleSets = (systems || []).map((s) => ({
    name: s.name, poles: s.poles || [],
  }));
  const all = [
    ...poleSets.flatMap((s) => s.poles),
    ...channels.flatMap((c) => c.zeros || []),
  ];
  if (!all.length) {
    emptyMessage(root, size, "no LTI plant to analyse");
    return 0;
  }

  const PAD = { left: 42, right: 12, top: 12, bottom: 28 };
  const w = size.width - PAD.left - PAD.right;
  const h = size.height - PAD.top - PAD.bottom;

  // symmetric, equal-scale range about the origin
  let r = 0;
  for (const [re, im] of all) r = Math.max(r, Math.abs(re), Math.abs(im));
  r = (r || 1) * 1.2;
  const s = Math.min(w, h) / (2 * r);        // one scale for both axes
  const cx = PAD.left + w / 2;
  const cy = PAD.top + h / 2;
  const X = (re) => cx + re * s;
  const Y = (im) => cy - im * s;

  // axes through the origin
  root.appendChild(svg("line", { x1: PAD.left, y1: cy, x2: PAD.left + w, y2: cy, class: "axis" }));
  root.appendChild(svg("line", { x1: cx, y1: PAD.top, x2: cx, y2: PAD.top + h, class: "axis" }));

  // a couple of ticks per axis
  const step = 10 ** Math.floor(Math.log10(r));
  for (let v = -Math.floor(r / step) * step; v <= r; v += step) {
    if (Math.abs(v) < step / 2) continue;
    root.appendChild(svg("text", { x: X(v), y: cy + 12, class: "tick", "text-anchor": "middle" }, nice(v)));
    root.appendChild(svg("text", { x: cx - 5, y: Y(v) + 3.5, class: "tick", "text-anchor": "end" }, nice(v)));
  }
  root.appendChild(svg("text", { x: PAD.left + w, y: cy - 4, class: "tick", "text-anchor": "end" }, "Re"));
  root.appendChild(svg("text", { x: cx + 4, y: PAD.top + 8, class: "tick", "text-anchor": "start" }, "Im"));

  const m = 5;  // marker half-size
  for (const g of poleSets) {
    for (const [re, im] of g.poles) {
      root.appendChild(
        cross(X(re), Y(im), m, "var(--fg)", { "data-pole": g.name })
      );
    }
  }
  for (const c of channels) {
    for (const [re, im] of c.zeros || []) {
      root.appendChild(svg("circle", {
        cx: X(re), cy: Y(im), r: m, class: "pz-zero", stroke: c.colour,
        "data-zero": c.label,
      }));
    }
  }

  // Only channels that actually have a zero earn a legend row; listing the rest
  // would promise markers that are not on the map.
  const entries = poleSets.map((g) => ({
    colour: "var(--fg)", label: `${g.name} poles`, marker: "pole",
  }));
  for (const c of channels) {
    if ((c.zeros || []).length) {
      entries.push({ colour: c.colour, label: `${c.label} zeros`, marker: "zero" });
    }
  }
  legend(root, entries, PAD.left + 6, PAD.top + 8);
  return poleSets.length;
}

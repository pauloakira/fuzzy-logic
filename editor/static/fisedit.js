// Fuzzy controller editor: membership functions, rule grid, control surface.
//
// This is the step the whole declarative-FIS work was for. A term used to be a
// Python closure; because it is now data, it can be dragged.
//
// All numerics come from `/api/fis/preview`. The membership functions are simple
// enough to reimplement here, but Mamdani inference is not, and curves drawn by
// one implementation beside a surface computed by another is how an editor ends
// up disagreeing with the simulator.

const SVG_NS = "http://www.w3.org/2000/svg";

const TERM_COLOURS = [
  "#d62728", "#ff7f0e", "#1f77b4", "#2ca02c", "#9467bd",
  "#17becf", "#8c564b", "#e377c2", "#7f7f7f",
];

const MF = { width: 320, height: 96, pad: { l: 26, r: 10, t: 8, b: 16 } };

/** Which parameters of each kind are x-positions that can be dragged. */
const DRAGGABLE = {
  triangular: [0, 1, 2],
  trapezoidal: [0, 1, 2, 3],
  left_shoulder: [0, 1],
  right_shoulder: [0, 1],
  gaussian: [0, 1], // 0 is the centre; 1 is shown as centre + sigma
};

function svg(tag, attrs = {}, text = "") {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text) node.textContent = text;
  return node;
}

function el(tag, attrs = {}, text = "") {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text) node.textContent = text;
  return node;
}

/** Handle x-position for parameter `i`: gaussian's sigma is drawn as c + sigma. */
export function handleX(kind, params, i) {
  if (kind === "gaussian") return i === 0 ? params[0] : params[0] + params[1];
  return params[i];
}

/** Inverse of `handleX` — what to store when a handle lands at `x`. */
export function paramFromX(kind, params, i, x) {
  if (kind === "gaussian") {
    return i === 0 ? x : Math.max(1e-6, x - params[0]);
  }
  return x;
}

/**
 * Keep parameters legal while dragging. `Term` rejects out-of-order breakpoints
 * outright, so clamping here is what makes a drag feel continuous instead of
 * snapping back on a rejected edit.
 */
export function clampParams(kind, params, i, value, low, high) {
  const next = [...params];
  if (kind === "gaussian") {
    next[i] = i === 0 ? value : Math.max((high - low) * 1e-3, value);
    return next;
  }
  const lo = i === 0 ? low : params[i - 1];
  const hi = i === params.length - 1 ? high : params[i + 1];
  if (kind.endsWith("shoulder")) {
    // b > a strictly; a hair of separation keeps it out of the divide-by-zero.
    const eps = (high - low) * 1e-4;
    next[i] = i === 0
      ? Math.min(Math.max(value, low), params[1] - eps)
      : Math.max(Math.min(value, high), params[0] + eps);
    return next;
  }
  next[i] = Math.min(Math.max(value, lo), hi);
  return next;
}

function mfPlot(varName, data, onChange) {
  const { l, r, t, b } = MF.pad;
  const root = svg("svg", {
    class: "mf-plot",
    "data-testid": `mf-${varName}`,
    "data-variable": varName,
    viewBox: `0 0 ${MF.width} ${MF.height}`,
    preserveAspectRatio: "none",
  });

  const px = (v) =>
    l + ((v - data.low) / (data.high - data.low)) * (MF.width - l - r);
  const py = (mu) => MF.height - b - mu * (MF.height - t - b);
  const toValue = (clientX) => {
    const rect = root.getBoundingClientRect();
    const frac = (clientX - rect.left) / rect.width;          // 0..1 across the svg
    const vx = frac * MF.width;                                // into viewBox units
    return data.low +
      ((vx - l) / (MF.width - l - r)) * (data.high - data.low);
  };

  root.append(
    svg("line", { x1: l, y1: py(0), x2: MF.width - r, y2: py(0), class: "axis" }),
    svg("line", { x1: l, y1: py(0), x2: l, y2: py(1), class: "axis" }),
    svg("text", { x: l - 4, y: py(1) + 4, class: "tick", "text-anchor": "end" }, "1"),
    svg("text", { x: l, y: MF.height - 3, class: "tick", "text-anchor": "start" },
        String(Number(data.low.toPrecision(3)))),
    svg("text", { x: MF.width - r, y: MF.height - 3, class: "tick",
                  "text-anchor": "end" },
        String(Number(data.high.toPrecision(3)))),
  );

  Object.entries(data.terms).forEach(([name, term], i) => {
    const colour = TERM_COLOURS[i % TERM_COLOURS.length];
    const d = term.mu
      .map((mu, k) => `${k ? "L" : "M"} ${px(data.grid[k]).toFixed(2)} ${py(mu).toFixed(2)}`)
      .join(" ");
    root.appendChild(
      svg("path", { d, class: "mf-curve", stroke: colour, "data-term": name })
    );

    if (!onChange) return;
    (DRAGGABLE[term.kind] || []).forEach((pi) => {
      const x = handleX(term.kind, term.params, pi);
      const mu = term.kind === "gaussian" && pi === 1 ? Math.exp(-0.5) : (pi === 0 ? 0 : 1);
      const peak = term.kind === "triangular" ? [1] :
                   term.kind === "trapezoidal" ? [1, 2] :
                   term.kind === "left_shoulder" ? [0] :
                   term.kind === "right_shoulder" ? [1] : [];
      const yv = term.kind === "gaussian" ? mu : (peak.includes(pi) ? 1 : 0);
      const handle = svg("circle", {
        cx: px(x), cy: py(yv), r: 5,
        class: "mf-handle", fill: colour,
        "data-handle": `${varName}.${name}.${pi}`,
        tabindex: "0",
      });
      handle.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        event.stopPropagation();
        handle.setPointerCapture(event.pointerId);
        // `term.params` is the snapshot this plot was rendered from. Writing it
        // back on release would undo the drag, so the running value is tracked
        // here and the release commits *that*.
        let latest = [...term.params];
        const move = (e) => {
          const raw = paramFromX(term.kind, latest, pi, toValue(e.clientX));
          latest = clampParams(term.kind, latest, pi, raw, data.low, data.high);
          handle.setAttribute("cx", String(px(handleX(term.kind, latest, pi))));
          onChange(varName, name, latest, { live: true });
        };
        const up = () => {
          handle.releasePointerCapture(event.pointerId);
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", up);
          onChange(varName, name, latest, { live: false });
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
      });
      root.appendChild(handle);
    });
  });

  return root;
}

function ruleGrid(fis, preview, onRuleChange) {
  const names = Object.keys(preview.inputs);
  const wrap = el("div", { "data-testid": "rule-grid" });

  if (names.length !== 2) {
    // A grid only makes sense for two inputs; anything else lists its rules.
    const list = el("ul", { class: "rule-list" });
    for (const rule of preview.rules) {
      const clauses = Object.entries(rule.if).map(([v, t]) => `${v} IS ${t}`);
      list.appendChild(el("li", {}, `IF ${clauses.join(" AND ")} THEN ${rule.then}`));
    }
    wrap.appendChild(list);
    return wrap;
  }

  const [colVar, rowVar] = names;
  const cols = Object.keys(preview.inputs[colVar].terms);
  const rows = Object.keys(preview.inputs[rowVar].terms);
  const lookup = new Map(
    preview.rules.map((r) => [`${r.if[rowVar]}|${r.if[colVar]}`, r.then])
  );

  const table = el("table", { class: "rules" });
  const head = el("tr");
  head.appendChild(el("th", {}, `${rowVar} \\ ${colVar}`));
  for (const c of cols) head.appendChild(el("th", {}, c));
  table.appendChild(head);

  for (const rt of rows) {
    const tr = el("tr");
    tr.appendChild(el("th", {}, rt));
    for (const ct of cols) {
      const td = el("td");
      const select = el("select", { "data-rule": `${rt}|${ct}` });
      select.appendChild(el("option", { value: "" }, "—"));
      for (const ot of preview.output_terms) {
        select.appendChild(el("option", { value: ot }, ot));
      }
      select.value = lookup.get(`${rt}|${ct}`) ?? "";
      if (!select.value) td.classList.add("missing");
      select.addEventListener("change", () =>
        onRuleChange({ [rowVar]: rt, [colVar]: ct }, select.value)
      );
      td.appendChild(select);
      table.appendChild(tr).appendChild(td);
    }
  }
  wrap.appendChild(table);
  return wrap;
}

/** Diverging red-to-blue through the background, centred on zero. */
function surfaceColour(value, extent) {
  if (!extent) return "transparent";
  const t = Math.max(-1, Math.min(1, value / extent));
  const [r, g, b] = t >= 0
    ? [31 + (1 - t) * 180, 119 + (1 - t) * 90, 180 + (1 - t) * 40]
    : [214 + (1 + t) * 0, 39 + (1 + t) * 170, 40 + (1 + t) * 180];
  return `rgb(${r.toFixed(0)} ${g.toFixed(0)} ${b.toFixed(0)})`;
}

function surfacePlot(surface) {
  const cell = 12;
  const cols = surface.x.length;
  const rowsN = surface.z.length;
  const root = svg("svg", {
    class: "surface",
    "data-testid": "fis-surface",
    viewBox: `0 0 ${cols * cell} ${rowsN * cell}`,
    preserveAspectRatio: "xMidYMid meet",
    role: "img",
    "aria-label": `control surface over ${surface.axes.join(" and ")}`,
  });
  const flat = surface.z.flat();
  const extent = Math.max(...flat.map(Math.abs)) || 1;
  root.dataset.extent = extent.toFixed(4);

  surface.z.forEach((row, j) => {
    row.forEach((v, i) => {
      root.appendChild(svg("rect", {
        // rows run bottom-up so the second input increases upwards, as a
        // phase-plane plot is normally read
        x: i * cell, y: (rowsN - 1 - j) * cell, width: cell, height: cell,
        fill: surfaceColour(v, extent), "data-cell": `${i},${j}`,
      }));
    });
  });
  return root;
}

/**
 * Replace only the control surface, leaving the membership plots alone.
 *
 * A full re-render mid-drag would destroy the handle holding the pointer
 * capture and end the drag — the same trap as dragging a node on the canvas.
 * The surface is the thing worth watching live; the curves catch up on release.
 */
export function updateSurface(container, preview) {
  if (!preview.surface) return;
  const existing = container.querySelector(".surface");
  if (!existing) return;
  existing.replaceWith(surfacePlot(preview.surface));
}

/**
 * Render the whole controller editor into `container`.
 * `handlers.onTerm(variable, term, params)` and `handlers.onRule(antecedents, then)`.
 */
export function renderFisEditor(container, preview, handlers = {}) {
  container.replaceChildren();

  const problems = el("ul", { "data-testid": "fis-problems", class: "problems" });
  for (const p of preview.problems || []) problems.appendChild(el("li", {}, p));
  container.appendChild(problems);

  const vars = el("div", { "data-testid": "fis-variables", class: "mf-grid" });
  for (const [name, data] of Object.entries(preview.inputs)) {
    const box = el("div", { class: "mf-box" });
    box.appendChild(el("h3", {}, name));
    box.appendChild(mfPlot(name, data, handlers.onTerm));
    vars.appendChild(box);
  }
  const outBox = el("div", { class: "mf-box" });
  outBox.appendChild(el("h3", {}, "output"));
  outBox.appendChild(mfPlot("__output__", preview.output, handlers.onTerm));
  vars.appendChild(outBox);
  container.appendChild(vars);

  container.appendChild(el("h3", {}, "Rules"));
  container.appendChild(ruleGrid(preview, preview, handlers.onRule));

  if (preview.surface) {
    container.appendChild(el("h3", {}, "Control surface"));
    container.appendChild(surfacePlot(preview.surface));
    const axes = el("p", { class: "surface-axes" },
      `horizontal: ${preview.surface.axes[0]} · vertical: ${
        preview.surface.axes[1] ?? "—"}`);
    container.appendChild(axes);
  }
}

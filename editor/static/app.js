// Block editor front end.
//
// Plain ES modules, no build step: the repo stays installable with
// `pip install -e .` alone, with nothing to compile and no node_modules.
//
// The spec document is the single source of truth, in the browser exactly as on
// disk (§2 of the design note). Every edit mutates `state.spec` and re-renders
// from it; the canvas holds no position or wiring state of its own.
//
// Elements the end-to-end tests assert on carry `data-testid`, so the tests key
// off stable hooks rather than markup structure.

import {
  enablePanZoom,
  fitView,
  highlightProblems,
  renderDiagram,
  zoomBy,
} from "/static/canvas.js";
import { renderFisEditor, updateSurface } from "/static/fisedit.js";
import { colourFor, renderPlot } from "/static/plot.js";
import { renderBode, renderPoleZero } from "/static/analysis.js";

const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw await problem(r, path);
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok && r.status !== 200) {
      const parsed = await r.clone().json().catch(() => null);
      if (parsed && parsed.detail) throw await problem(r, path);
    }
    return r.json();
  },
};

async function problem(response, path) {
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail || {};
  const err = new Error(detail.error || `${path} -> ${response.status}`);
  err.block = detail.block;
  err.status = response.status;
  return err;
}

const el = (tag, attrs = {}, text = "") => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text) node.textContent = text;
  return node;
};
const byId = (id) => document.getElementById(id);
const set = (testid, value) => {
  document.querySelector(`[data-testid="${testid}"]`).textContent = String(value);
};

const state = {
  path: null,
  spec: null,
  ports: {},
  palette: {},
  selected: null, // {kind: "block"|"wire", value}
  dirty: false,
  result: null,   // the last /api/simulate response
  shown: [],      // which of its signals are plotted
  analysis: null, // the last /api/analyze response ({systems}), or null
  fisBlock: null, // name of the FISBlock whose editor is open
};

// ----- palette and diagram list ----------------------------------------------

async function loadPalette() {
  const { blocks } = await api.get("/api/palette");
  state.palette = blocks;
  window.__palette = blocks;

  const list = byId("palette");
  list.replaceChildren();
  const chooser = byId("add-block");
  chooser.replaceChildren(el("option", { value: "" }, "block…"));

  for (const [name, meta] of Object.entries(blocks)) {
    const required = meta.params.filter((p) => p.required).map((p) => p.name);
    const item = el("li", { "data-block-type": name });
    item.appendChild(el("strong", {}, name));
    item.appendChild(
      el("span", { class: "params" },
        meta.params.length
          ? ` ${meta.params.map((p) => p.name).join(", ")}`
          : " (no parameters)")
    );
    if (required.length) {
      item.appendChild(
        el("span", { class: "required" }, `required: ${required.join(", ")}`)
      );
    }
    list.appendChild(item);
    chooser.appendChild(el("option", { value: name }, name));
  }
  return Object.keys(blocks).length;
}

async function loadDiagramList() {
  const { diagrams } = await api.get("/api/diagrams");
  const list = byId("diagrams");
  list.replaceChildren();
  for (const path of diagrams) {
    const button = el("button", { type: "button", "data-diagram-path": path }, path);
    button.addEventListener("click", () => openDiagram(path));
    list.appendChild(el("li")).appendChild(button);
  }
  return diagrams;
}

// ----- editing ----------------------------------------------------------------

function markDirty(dirty = true) {
  state.dirty = dirty;
  byId("dirty").hidden = !dirty;
  document.body.dataset.dirty = String(dirty);
}

/** Apply a change to the spec, then revalidate and redraw from it. */
async function mutate(change) {
  change(state.spec);
  markDirty(true);
  set("save-status", "");
  await refresh();
}

function uniqueName(base) {
  const taken = new Set(state.spec.blocks.map((b) => b.name));
  if (!taken.has(base)) return base;
  for (let i = 2; ; i += 1) if (!taken.has(`${base}${i}`)) return `${base}${i}`;
}

function defaultParams(type) {
  const params = {};
  for (const p of state.palette[type]?.params || []) {
    // A required parameter has no default the palette can offer; 0 is a
    // placeholder the user must replace, and validation will say so if not.
    params[p.name] = p.default ?? (p.required ? 0 : null);
  }
  return params;
}

function addBlock(type) {
  const name = uniqueName(type.toLowerCase());
  const xs = state.spec.blocks.map((b) => b.layout?.x ?? 0);
  mutate((spec) => {
    spec.blocks.push({
      type,
      name,
      params: defaultParams(type),
      layout: { x: Math.max(0, ...xs) + 170, y: 40 },
    });
  });
}

function deleteSelected() {
  const sel = state.selected;
  if (!sel) return;
  if (sel.kind === "block") {
    const name = sel.value.name;
    mutate((spec) => {
      spec.blocks = spec.blocks.filter((b) => b.name !== name);
      // Wires to a deleted block would be dangling references, which the API
      // rejects outright — remove them with it.
      spec.connections = spec.connections.filter(
        (c) => c.from[0] !== name && c.to[0] !== name
      );
    });
  } else {
    const { from, to } = sel.value;
    mutate((spec) => {
      spec.connections = spec.connections.filter(
        (c) => !(c.from[0] === from[0] && c.from[1] === from[1] &&
                 c.to[0] === to[0] && c.to[1] === to[1])
      );
    });
  }
  clearSelection();
}

function connect(conn) {
  mutate((spec) => {
    // An input takes one source; replacing is friendlier than an error here,
    // since the API would reject the second wire anyway.
    spec.connections = spec.connections.filter(
      (c) => !(c.to[0] === conn.to[0] && c.to[1] === conn.to[1])
    );
    spec.connections.push(conn);
  });
}

// ----- selection panel --------------------------------------------------------

function clearSelection() {
  state.selected = null;
  state.fisBlock = null;
  byId("selection").hidden = true;
  byId("fis-editor").hidden = true;
  byId("delete-selected").disabled = true;
}

function selectBlock(block) {
  state.selected = { kind: "block", value: block };
  byId("delete-selected").disabled = false;
  byId("selection").hidden = false;
  set("selected-name", block.name);
  set("selected-type", block.type);

  if (block.type === "FISBlock") {
    openFisEditor(block.name);
  } else {
    state.fisBlock = null;
    byId("fis-editor").hidden = true;
  }

  const dl = document.querySelector('[data-testid="selected-params"]');
  dl.replaceChildren();
  for (const [key, value] of Object.entries(block.params || {})) {
    dl.appendChild(el("dt", {}, key));
    const dd = el("dd");
    dd.appendChild(paramField(block, key, value));
    dl.appendChild(dd);
  }
}

function selectWire(conn) {
  state.selected = { kind: "wire", value: conn };
  byId("delete-selected").disabled = false;
  byId("selection").hidden = false;
  set("selected-name", `${conn.from.join(".")} → ${conn.to.join(".")}`);
  set("selected-type", "connection");
  document.querySelector('[data-testid="selected-params"]').replaceChildren();
}

/**
 * One editor per parameter. Scalars get a typed input; anything structured — a
 * matrix, or a whole FIS — gets JSON, which is honest about what it is rather
 * than pretending a nested document fits in a form field.
 */
function paramField(block, key, value) {
  const scalar = value === null || ["number", "string", "boolean"].includes(typeof value);
  const field = scalar
    ? el("input", {
        type: typeof value === "number" ? "number" : "text",
        step: "any",
        value: value === null ? "" : String(value),
        "data-param": key,
      })
    : el("textarea", { rows: "3", "data-param": key });
  if (!scalar) field.value = JSON.stringify(value);

  field.addEventListener("change", () => {
    let parsed;
    if (scalar && typeof value === "number") {
      parsed = field.value === "" ? null : Number(field.value);
      if (parsed !== null && Number.isNaN(parsed)) return invalid(field);
    } else if (scalar && typeof value === "boolean") {
      parsed = field.value === "true";
    } else if (scalar) {
      parsed = field.value;
    } else {
      try {
        parsed = JSON.parse(field.value);
      } catch {
        return invalid(field);
      }
    }
    field.removeAttribute("data-invalid");
    mutate((spec) => {
      spec.blocks.find((b) => b.name === block.name).params[key] = parsed;
    });
  });
  return field;
}

function invalid(field) {
  field.setAttribute("data-invalid", "true");
  set("save-status", "fix the highlighted field");
}

// ----- render -----------------------------------------------------------------

async function refresh() {
  const report = await api.post("/api/validate", { spec: state.spec });
  state.ports = report.ports || {};

  const canvas = byId("canvas");
  const drawn = renderDiagram(canvas, state.spec, state.ports, {
    onSelect: selectBlock,
    onWireSelect: selectWire,
    onConnect: connect,
    // The canvas moves the node itself during the drag; this fires once, at the
    // end, when the new position has been written into the spec. Re-render so
    // the viewBox refits — without it, a node dragged past the original bounds
    // stays clipped.
    onMoveEnd: () => {
      markDirty(true);
      refresh();
    },
  });
  canvas.dataset.nodes = String(drawn.nodes);
  canvas.dataset.wires = String(drawn.wires);
  enablePanZoom(canvas, showZoom);
  showZoom();

  set("block-count", state.spec.blocks.length);
  set("connection-count", state.spec.connections.length);
  set("state-count", report.n_states ?? 0);
  byId("summary-name").textContent = state.spec.name || state.path;

  const advice = byId("advice");
  advice.replaceChildren();
  for (const line of report.advice || []) advice.appendChild(el("li", {}, line));

  const validity = byId("validity");
  if (report.ok) {
    validity.textContent = "valid";
    validity.dataset.ok = "true";
  } else {
    const first = report.problems[0] || {};
    validity.textContent = `invalid: ${first.error || "unknown problem"}`;
    validity.dataset.ok = "false";
    validity.dataset.block = first.block || "";
  }
  // Structured problem references exist so the canvas can point at the offending
  // node rather than describe it.
  highlightProblems(canvas, report.problems || []);

  byId("summary").hidden = false;
  byId("toolbar").hidden = false;
  byId("runbar").hidden = false;
  window.__lastSpec = state.spec;
}

async function openDiagram(path) {
  const status = byId("status");
  status.textContent = `loading ${path}…`;
  try {
    const { spec, ports } = await api.get(
      `/api/diagram?path=${encodeURIComponent(path)}`
    );
    state.path = path;
    state.spec = spec;
    state.ports = ports;
    clearSelection();
    markDirty(false);
    byId("save-path").value = path.replace(/\.json$/, ".draft.json");
    set("save-status", "");
    byId("canvas-empty").hidden = true;
    delete byId("canvas").dataset.userView;  // frame each diagram when opened
    state.shown = [];
    state.fisBlock = null;
    clearResults();
    byId("fis-editor").hidden = true;
    await refresh();
    status.textContent = "ready";
    status.dataset.ready = "true";
  } catch (err) {
    // A spec can name a block type this build does not have, or be malformed.
    byId("canvas").replaceChildren();
    byId("canvas-empty").hidden = false;
    byId("canvas-empty").textContent =
      err.block ? `${err.message} (block: ${err.block})` : err.message;
    byId("summary").hidden = true;
    byId("toolbar").hidden = true;
    byId("runbar").hidden = true;
    clearResults();
    byId("fis-editor").hidden = true;
    clearSelection();
    status.textContent = `could not open ${path}`;
    status.dataset.ready = "error";
  }
}

async function save() {
  const path = byId("save-path").value.trim();
  set("save-status", "saving…");
  try {
    let r = await fetch("/api/diagram", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ path, spec: state.spec }),
    });
    if (r.status === 409) {
      // Overwriting an existing file is deliberate, never incidental.
      if (!window.confirm(`${path} exists. Replace it?`)) {
        set("save-status", "not saved");
        return;
      }
      r = await fetch("/api/diagram", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ path, spec: state.spec, overwrite: true }),
      });
    }
    if (!r.ok) throw await problem(r, "/api/diagram");
    const body = await r.json();
    markDirty(false);
    set("save-status", `saved ${body.bytes} bytes to ${body.path}`);
    document.body.dataset.saved = body.path;
    await loadDiagramList();
  } catch (err) {
    set("save-status", `not saved: ${err.message}`);
  }
}

// ----- fuzzy controller editor --------------------------------------------------

function fisDoc(name = state.fisBlock) {
  return state.spec?.blocks.find((b) => b.name === name)?.params?.fis || null;
}

let previewToken = 0;

/** Redraw the controller editor from a fresh server-side preview. */
async function refreshFisEditor() {
  const doc = fisDoc();
  if (!doc) return;
  // A drag-time refresh may still be armed from the last pointermove. It would
  // fire after this one and replace the settled surface with a coarse one.
  clearTimeout(previewTimer);
  const mine = ++previewToken;
  let preview;
  try {
    const r = await fetch("/api/fis/preview", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fis: doc }),
    });
    if (!r.ok) throw await problem(r, "/api/fis/preview");
    preview = await r.json();
  } catch (err) {
    byId("fis-body").replaceChildren(el("p", { class: "problems" }, err.message));
    return;
  }
  // A slower earlier request must not overwrite a newer one.
  if (mine !== previewToken) return;
  window.__lastPreview = preview;

  // Tests (and a human watching) need to know when a redraw has landed; the
  // surface arrives asynchronously after every edit.
  byId("fis-editor").dataset.revision = String(mine);

  renderFisEditor(byId("fis-body"), preview, {
    onTerm: (variable, term, params, { live }) => {
      const doc = fisDoc();
      const target = variable === "__output__"
        ? doc.output.terms[term]
        : doc.inputs[variable].terms[term];
      target.params = params;
      markDirty(true);
      // While dragging, refresh the surface only — a full re-render would
      // destroy the handle under the pointer. The curves redraw on release.
      if (live) scheduleSurfaceRefresh();
      else refreshFisEditor();
    },
    onRule: (antecedents, then) => {
      const doc = fisDoc();
      const key = JSON.stringify(antecedents);
      const idx = doc.rules.findIndex(
        (r) => JSON.stringify(sortKeys(r.if)) === JSON.stringify(sortKeys(antecedents))
      );
      if (!then) {
        if (idx >= 0) doc.rules.splice(idx, 1);
      } else if (idx >= 0) {
        doc.rules[idx].then = then;
      } else {
        doc.rules.push({ if: antecedents, then });
      }
      void key;
      markDirty(true);
      refreshFisEditor();
      refresh();
    },
  });
}

function sortKeys(obj) {
  return Object.fromEntries(Object.entries(obj).sort(([a], [b]) => a.localeCompare(b)));
}

let previewTimer = null;
function scheduleSurfaceRefresh() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const doc = fisDoc();
    if (!doc) return;
    // Shares `previewToken` with the settled refresh, so a coarse surface in
    // flight when the drag ends loses to the full-resolution one that follows.
    const mine = ++previewToken;
    const r = await fetch("/api/fis/preview", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fis: doc, surface_resolution: 17 }),
    });
    if (!r.ok) return;  // an intermediate drag state can be briefly invalid
    const preview = await r.json();
    if (mine !== previewToken) return;
    window.__lastPreview = preview;
    updateSurface(byId("fis-body"), preview);
  }, 50);
}

function openFisEditor(name) {
  state.fisBlock = name;
  byId("fis-editor").hidden = false;
  set("fis-block-name", name);
  refreshFisEditor();
}

// ----- running ----------------------------------------------------------------

/** Signals worth plotting by default: the plant's outputs and the control command. */
function defaultSignals(available) {
  const preferred = available.filter(
    (k) => k.startsWith("plant.") || k.startsWith("actuator.") ||
           k.endsWith(".u") || k.startsWith("controller.")
  );
  return (preferred.length ? preferred : available).slice(0, 4);
}

function renderSignalToggles() {
  const list = byId("signals");
  list.replaceChildren();
  const available = Object.keys(state.result?.signals || {}).sort();
  available.forEach((key) => {
    const on = state.shown.includes(key);
    const label = el("label", { "data-signal": key });
    const box = el("input", { type: "checkbox", "data-signal-toggle": key });
    box.checked = on;
    box.addEventListener("change", () => {
      state.shown = box.checked
        ? [...state.shown, key]
        : state.shown.filter((k) => k !== key);
      drawResult();
    });
    const swatch = el("span", { class: "swatch" });
    swatch.style.background = on ? colourFor(state.shown.indexOf(key)) : "transparent";
    label.append(box, swatch, document.createTextNode(key));
    list.appendChild(label);
  });
}

function drawResult() {
  const range = renderPlot(byId("plot"), state.result, state.shown);
  // `data-series` is the per-path key; the count needs its own name or the
  // selector picks up the <svg> itself.
  byId("plot").dataset.seriesCount = String(range?.drawn ?? 0);
  renderSignalToggles();
}

/**
 * Drop the last run and everything drawn from it.
 *
 * `#analysis` is a sibling of `#results`, not a child, so hiding the one leaves
 * the other on screen — opening a second diagram used to keep showing the first
 * one's Bode plot and poles.
 */
function clearResults() {
  state.result = null;
  state.analysis = null;
  byId("results").hidden = true;
  byId("analysis").hidden = true;
}

/** Render the Bode and pole-zero charts, or hide the panel when the diagram has
 *  no LTI plant to analyse. */
function drawAnalysis() {
  const systems = state.analysis?.systems ?? [];
  const has = systems.length > 0;
  byId("analysis").hidden = false;          // a run happened; explain either way
  byId("analysis-charts").hidden = !has;
  byId("analysis-note").hidden = has;
  if (!has) {
    byId("analysis-note").textContent =
      "No frequency response or pole–zero map: this diagram has no linear " +
      "(state-space) plant. These charts are defined only for an LTI plant, so a " +
      "nonlinear plant such as the motor has neither. Open a diagram with a " +
      "StateSpacePlant — the SDOF vibration exercise, for one — to see them.";
    return;
  }
  byId("bode").dataset.systemCount = String(renderBode(byId("bode"), systems));
  byId("pzmap").dataset.systemCount = String(renderPoleZero(byId("pzmap"), systems));
}

async function run() {
  const t_max = Number(byId("t-max").value);
  const dt_control = Number(byId("dt").value);
  set("run-status", "running…");
  byId("run").disabled = true;
  try {
    const r = await fetch("/api/simulate", {
      method: "POST",
      headers: { "content-type": "application/json" },
      // Ask for roughly two samples per device pixel — more is invisible and
      // just makes the response bigger.
      body: JSON.stringify({
        spec: state.spec,
        t_max,
        dt_control,
        max_points: Math.min(
          4000, Math.max(400, Math.round((byId("plot").clientWidth || 700) * 2))
        ),
      }),
    });
    if (!r.ok) throw await problem(r, "/api/simulate");
    state.result = await r.json();
    window.__lastResult = state.result;

    const available = Object.keys(state.result.signals).sort();
    // Keep the user's selection across runs; fall back to a sensible default.
    const kept = state.shown.filter((k) => available.includes(k));
    state.shown = kept.length ? kept : defaultSignals(available);

    const warnings = byId("run-warnings");
    warnings.replaceChildren();
    // The transient-window and RK4 stability guards are usually the most useful
    // thing on the screen; showing them beats a plot that silently lies.
    for (const w of state.result.warnings || []) {
      warnings.appendChild(el("li", {}, w));
    }

    byId("results").hidden = false;
    drawResult();
    set("run-status",
        `${state.result.n_samples} samples, showing ${state.result.returned}`);

    // Linear analysis (Bode, poles/zeros) of the diagram's LTI plants. The spec
    // just simulated, so it builds; a failure here should not sink the run, only
    // hide the analysis panel.
    try {
      const a = await fetch("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ spec: state.spec }),
      });
      state.analysis = a.ok ? await a.json() : null;
    } catch {
      state.analysis = null;
    }
    drawAnalysis();
  } catch (err) {
    byId("results").hidden = false;
    byId("run-warnings").replaceChildren(el("li", {}, err.message));
    byId("plot").replaceChildren();
    state.analysis = null;
    byId("analysis").hidden = true;
    set("run-status", "failed");
  } finally {
    byId("run").disabled = false;
  }
}

// ----- wiring up --------------------------------------------------------------

function showZoom() {
  const zoom = Number(byId("canvas").dataset.zoom || 1);
  set("zoom-level", `${Math.round(zoom * 100)}%`);
}

function bindToolbar() {
  byId("zoom-in").addEventListener("click", () => {
    zoomBy(byId("canvas"), 1 / 1.15);
    showZoom();
  });
  byId("zoom-out").addEventListener("click", () => {
    zoomBy(byId("canvas"), 1.15);
    showZoom();
  });
  byId("zoom-fit").addEventListener("click", () => {
    fitView(byId("canvas"), state.spec);
    showZoom();
  });
  byId("add-block").addEventListener("change", (e) => {
    if (e.target.value) {
      addBlock(e.target.value);
      e.target.value = "";
    }
  });
  byId("delete-selected").addEventListener("click", deleteSelected);
  byId("save").addEventListener("click", save);
  byId("run").addEventListener("click", run);
  document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName);
    if (typing || !state.spec) return;
    if ((e.key === "Delete" || e.key === "Backspace") && state.selected) {
      e.preventDefault();
      deleteSelected();
    } else if (e.key === "+" || e.key === "=") {
      zoomBy(byId("canvas"), 1 / 1.15);
      showZoom();
    } else if (e.key === "-") {
      zoomBy(byId("canvas"), 1.15);
      showZoom();
    } else if (e.key === "0") {
      fitView(byId("canvas"), state.spec);
      showZoom();
    }
  });
  window.addEventListener("beforeunload", (e) => {
    if (state.dirty) e.preventDefault();
  });
  // The plot is fluid-width, but its viewBox is fixed at draw time. Re-draw when
  // the element resizes so the viewBox stays matched to the pixel box and the
  // tick labels never stretch — the way a Simulink scope repaints on resize.
  if (typeof ResizeObserver !== "undefined") {
    let raf = 0;
    new ResizeObserver(() => {
      if (!state.result || byId("results").hidden) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        drawResult();
        if (!byId("analysis").hidden) drawAnalysis();
      });
    }).observe(byId("plot"));
  }
}

async function main() {
  const status = byId("status");
  try {
    bindToolbar();
    const [count, diagrams] = await Promise.all([loadPalette(), loadDiagramList()]);
    status.textContent = `ready — ${count} block types, ${diagrams.length} diagrams`;
    status.dataset.ready = "true";
  } catch (err) {
    status.textContent = `error: ${err.message}`;
    status.dataset.ready = "false";
  }
}

main();

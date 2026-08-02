// Block editor front end.
//
// Plain ES modules, no build step: the repo stays installable with
// `pip install -e .` alone, with nothing to compile and no node_modules.
//
// Every element the end-to-end tests assert on carries a `data-testid`, so the
// tests key off stable hooks rather than markup structure or CSS classes.

import { highlightProblems, renderDiagram } from "/static/canvas.js";

const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) {
      // The API answers failures with a structured detail object; surface what
      // it says rather than a bare status code.
      const detail = await r.json().catch(() => ({}));
      const err = new Error(detail?.detail?.error || `${path} -> ${r.status}`);
      err.block = detail?.detail?.block;
      throw err;
    }
    return r.json();
  },
  async post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    return r.json();
  },
};

function el(tag, attrs = {}, text = "") {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text) node.textContent = text;
  return node;
}

function set(testid, value) {
  document.querySelector(`[data-testid="${testid}"]`).textContent = String(value);
}

let palette = {};

async function renderPalette() {
  const { blocks } = await api.get("/api/palette");
  palette = blocks;
  window.__palette = blocks;  // handle for the end-to-end tests
  const list = document.getElementById("palette");
  list.replaceChildren();
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
  }
  return Object.keys(blocks).length;
}

async function renderDiagramList() {
  const { diagrams } = await api.get("/api/diagrams");
  const list = document.getElementById("diagrams");
  list.replaceChildren();
  for (const path of diagrams) {
    const button = el("button", { type: "button", "data-diagram-path": path }, path);
    button.addEventListener("click", () => openDiagram(path));
    list.appendChild(el("li")).appendChild(button);
  }
  return diagrams;
}

function showSelection(block) {
  document.getElementById("selection").hidden = false;
  set("selected-name", block.name);
  set("selected-type", block.type);
  const dl = document.querySelector('[data-testid="selected-params"]');
  dl.replaceChildren();
  for (const [key, value] of Object.entries(block.params || {})) {
    dl.appendChild(el("dt", {}, key));
    // A FIS or a matrix is not a one-line value; summarise rather than dump it.
    const text =
      value && typeof value === "object" && !Array.isArray(value)
        ? `{${Object.keys(value).join(", ")}}`
        : JSON.stringify(value);
    dl.appendChild(el("dd", {}, text.length > 60 ? `${text.slice(0, 57)}…` : text));
  }
}

async function openDiagram(path) {
  const status = document.getElementById("status");
  status.textContent = `loading ${path}\u2026`;
  try {
    await loadDiagram(path);
    status.textContent = "ready";
    status.dataset.ready = "true";
  } catch (err) {
    // A spec can name a block type this build does not have, or be malformed.
    // Say so, name the block if the API named one, and leave no stale drawing.
    document.getElementById("canvas").replaceChildren();
    document.getElementById("canvas-empty").hidden = false;
    document.getElementById("canvas-empty").textContent =
      err.block ? `${err.message} (block: ${err.block})` : err.message;
    document.getElementById("summary").hidden = true;
    document.getElementById("selection").hidden = true;
    status.textContent = `could not open ${path}`;
    status.dataset.ready = "error";
  }
}

async function loadDiagram(path) {
  const { spec, ports } = await api.get(
    `/api/diagram?path=${encodeURIComponent(path)}`
  );
  const report = await api.post("/api/validate", { spec });

  // Ports come resolved per block instance from the API — Sum's depend on its
  // `ports` parameter and FISBlock's on the FIS, so the class cannot supply them.
  const canvas = document.getElementById("canvas");
  const drawn = renderDiagram(canvas, spec, ports, showSelection);
  document.getElementById("canvas-empty").hidden = true;
  canvas.dataset.nodes = String(drawn.nodes);
  canvas.dataset.wires = String(drawn.wires);

  document.getElementById("summary-name").textContent = spec.name || path;
  set("block-count", spec.blocks.length);
  set("connection-count", spec.connections.length);
  set("state-count", report.n_states);

  const advice = document.getElementById("advice");
  advice.replaceChildren();
  for (const line of report.advice || []) advice.appendChild(el("li", {}, line));

  const validity = document.getElementById("validity");
  if (report.ok) {
    validity.textContent = "valid";
    validity.dataset.ok = "true";
  } else {
    const first = report.problems[0] || {};
    validity.textContent = `invalid: ${first.error || "unknown problem"}`;
    validity.dataset.ok = "false";
    validity.dataset.block = first.block || "";
  }
  // Structured problem references exist precisely so the canvas can point at
  // the offending node rather than describe it.
  highlightProblems(canvas, report.problems || []);

  document.getElementById("summary").hidden = false;
  document.getElementById("selection").hidden = true;
  window.__lastSpec = spec;
}

async function main() {
  const status = document.getElementById("status");
  try {
    const [count, diagrams] = await Promise.all([renderPalette(), renderDiagramList()]);
    status.textContent = `ready — ${count} block types, ${diagrams.length} diagrams`;
    status.dataset.ready = "true";
  } catch (err) {
    status.textContent = `error: ${err.message}`;
    status.dataset.ready = "false";
  }
}

main();

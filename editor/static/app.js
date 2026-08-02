// Block editor front end.
//
// Plain ES modules, no build step: the repo stays installable with
// `pip install -e .` alone, with nothing to compile and no node_modules. The
// canvas (step 7c) renders into this same page.
//
// Every element the end-to-end tests assert on carries a `data-testid`, so the
// tests key off stable hooks rather than markup structure or CSS classes.

const api = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${path} -> ${r.status}`);
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

async function renderPalette() {
  const { blocks } = await api.get("/api/palette");
  const list = document.getElementById("palette");
  list.replaceChildren();
  for (const [name, params] of Object.entries(blocks)) {
    const required = params.filter((p) => p.required).map((p) => p.name);
    const item = el("li", { "data-block-type": name });
    item.appendChild(el("strong", {}, name));
    item.appendChild(
      el("span", { class: "params" },
        params.length ? ` ${params.map((p) => p.name).join(", ")}` : " (no parameters)")
    );
    if (required.length) {
      item.appendChild(el("span", { class: "required" }, ` required: ${required.join(", ")}`));
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

async function openDiagram(path) {
  const status = document.getElementById("status");
  status.textContent = `loading ${path}…`;

  const { spec } = await api.get(`/api/diagram?path=${encodeURIComponent(path)}`);
  const report = await api.post("/api/validate", { spec });

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
    // Problems carry structured block/port references, so once the canvas
    // exists this is where a node gets highlighted rather than described.
    const first = report.problems[0] || {};
    validity.textContent = `invalid: ${first.error || "unknown problem"}`;
    validity.dataset.ok = "false";
    validity.dataset.block = first.block || "";
  }

  document.getElementById("summary").hidden = false;
  status.textContent = "ready";
  window.__lastSpec = spec; // handle for the end-to-end tests
}

function set(testid, value) {
  document.querySelector(`[data-testid="${testid}"]`).textContent = String(value);
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

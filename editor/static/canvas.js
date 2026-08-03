// SVG block-diagram canvas.
//
// Renders a spec document: nodes at their `layout` coordinates, ports on the
// node edges, wires between them. No dependencies and no build step — the shapes
// are a few dozen lines of SVG, which is cheaper than a flow-canvas library and
// its toolchain for the ten block types this project has.
//
// The node shapes mirror `Diagram.to_mermaid()` so the interactive view and the
// figure in the reports read the same way: sources are skewed, sampled
// (zero-order-held) blocks are rounded, continuous blocks are square.

const SVG_NS = "http://www.w3.org/2000/svg";

export const NODE = { width: 132, height: 52, portRadius: 4.5, gap: 14 };

/** Block types that are sampled at the control rate; drawn rounded. */
const SAMPLED = new Set(["FISBlock", "PIDBlock", "StateFeedback"]);

function svg(tag, attrs = {}, text = "") {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text) node.textContent = text;
  return node;
}

/**
 * Port names per side. The spec does not carry them — they belong to the block —
 * and for `Sum` they depend on its `ports` parameter while `FISBlock`'s come from
 * the FIS, so the class cannot supply them either. `/api/diagram` resolves them
 * per block *name* from the instantiated diagram; the type is a fallback for
 * callers that only have palette data.
 */
function portsOf(block, ports) {
  const meta = ports?.[block.name] || ports?.[block.type] || {};
  return { inputs: meta.inputs || [], outputs: meta.outputs || [] };
}

/** Where a port sits, in diagram coordinates. */
export function portPosition(block, side, index, count) {
  const { x, y } = block._pos;
  const span = NODE.height / (count + 1);
  return {
    x: side === "inputs" ? x : x + NODE.width,
    y: y + span * (index + 1),
  };
}

/**
 * Assign positions, falling back to a simple grid for blocks the spec does not
 * place. A diagram authored by hand has no layout at all, and it must still draw.
 */
function positions(spec) {
  let unplaced = 0;
  for (const block of spec.blocks) {
    if (block.layout && Number.isFinite(block.layout.x)) {
      block._pos = { x: block.layout.x, y: block.layout.y, placed: true };
    } else {
      const col = unplaced % 4;
      const row = Math.floor(unplaced / 4);
      block._pos = {
        x: 40 + col * (NODE.width + 80),
        y: 40 + row * (NODE.height + 70),
        placed: false,
      };
      unplaced += 1;
    }
  }
  return unplaced;
}

function nodePath(block) {
  const { x, y } = block._pos;
  const { width: w, height: h } = NODE;
  const isSource = !(block._ports.inputs.length);
  if (isSource) {
    const skew = 10; // parallelogram, matching the Mermaid source shape
    return svg("polygon", {
      points: `${x + skew},${y} ${x + w},${y} ${x + w - skew},${y + h} ${x},${y + h}`,
      class: "node-shape",
    });
  }
  return svg("rect", {
    x, y, width: w, height: h,
    rx: SAMPLED.has(block.type) ? h / 2 : 4,
    class: "node-shape",
  });
}

/** Convert a pointer event to diagram coordinates. */
function toDiagram(root, event) {
  const ctm = root.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const p = root.createSVGPoint ? root.createSVGPoint() : new DOMPoint();
  p.x = event.clientX;
  p.y = event.clientY;
  const q = p.matrixTransform(ctm.inverse());
  return { x: q.x, y: q.y };
}

// Sharp corners, as every block-diagram tool draws them: the whole point of
// orthogonal routing is that a wire's direction is unambiguous at a glance.
export const ROUTING = { stub: 16, lane: 26, laneStep: 12, corner: 0 };

/**
 * Corner points for a wire, orthogonal throughout — the convention every block
 * diagram tool uses, and the reason a Simulink sheet stays readable where
 * diagonal splines turn into spaghetti.
 *
 * Forward (destination to the right): out horizontally, one vertical leg at the
 * midpoint, in horizontally.
 * Backward (a feedback wire): out to the right, down into a lane clear of both
 * blocks, back across, then up into the input — rather than cutting diagonally
 * through whatever lies between.
 */
export function routePoints(from, to, src, dst, lane = 0) {
  const { stub, laneStep } = ROUTING;

  // Forward or backward is decided on the ports themselves. Deciding it on the
  // stubbed positions misroutes any short forward hop whose gap is narrower than
  // two stubs — it looks like feedback and gets sent on a detour.
  if (to.x >= from.x) {
    if (Math.abs(from.y - to.y) < 0.5) return [from, to];   // straight run
    const mid = (from.x + to.x) / 2;
    return [from, { x: mid, y: from.y }, { x: mid, y: to.y }, to];
  }

  const a = { x: from.x + stub, y: from.y };
  const b = { x: to.x - stub, y: to.y };

  // Feedback: drop below the lower of the two blocks it joins, so the lane stays
  // local instead of sweeping under the whole diagram. The rubber-band ghost
  // drawn while wiring has no blocks yet, so it falls back to the ports.
  const below = src?._pos && dst?._pos
    ? Math.max(src._pos.y, dst._pos.y) + NODE.height
    : Math.max(from.y, to.y);
  const y = below + ROUTING.lane + lane * laneStep;
  return [from, a, { x: a.x, y }, { x: b.x, y }, b, to];
}

/** An SVG path through `points`, with corners eased by a small radius. */
export function polylinePath(points, radius = ROUTING.corner) {
  const pts = points.filter(
    (p, i) => i === 0 || Math.hypot(p.x - points[i - 1].x, p.y - points[i - 1].y) > 0.01
  );
  if (pts.length < 2) return "";
  let d = `M ${pts[0].x.toFixed(2)} ${pts[0].y.toFixed(2)}`;
  if (radius <= 0) {
    return d + pts.slice(1)
      .map((p) => ` L ${p.x.toFixed(2)} ${p.y.toFixed(2)}`).join("");
  }
  for (let i = 1; i < pts.length - 1; i += 1) {
    const prev = pts[i - 1];
    const cur = pts[i];
    const next = pts[i + 1];
    const rIn = Math.min(radius, Math.hypot(cur.x - prev.x, cur.y - prev.y) / 2);
    const rOut = Math.min(radius, Math.hypot(next.x - cur.x, next.y - cur.y) / 2);
    const inUnit = unit(prev, cur);
    const outUnit = unit(cur, next);
    const p1 = { x: cur.x - inUnit.x * rIn, y: cur.y - inUnit.y * rIn };
    const p2 = { x: cur.x + outUnit.x * rOut, y: cur.y + outUnit.y * rOut };
    d += ` L ${p1.x.toFixed(2)} ${p1.y.toFixed(2)}`;
    d += ` Q ${cur.x.toFixed(2)} ${cur.y.toFixed(2)} ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
  }
  const last = pts[pts.length - 1];
  return `${d} L ${last.x.toFixed(2)} ${last.y.toFixed(2)}`;
}

function unit(a, b) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const n = Math.hypot(dx, dy) || 1;
  return { x: dx / n, y: dy / n };
}

function wirePath(from, to, src, dst, lane = 0) {
  return polylinePath(routePoints(from, to, src, dst, lane));
}

/**
 * Draw `spec` into `root` (an <svg>). Returns a small report the caller and the
 * tests can assert on.
 */
export function renderDiagram(root, spec, ports = {}, handlers = {}) {
  root.replaceChildren();
  const unplaced = positions(spec);
  const byName = new Map();
  for (const block of spec.blocks) {
    block._ports = portsOf(block, ports);
    byName.set(block.name, block);
  }

  const defs = svg("defs");
  const marker = svg("marker", {
    id: "wire-arrow", viewBox: "0 0 8 8", refX: 7, refY: 4,
    markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse",
  });
  marker.appendChild(svg("path", { d: "M 0 1 L 7 4 L 0 7 z", class: "wire-arrow" }));
  defs.appendChild(marker);
  root.appendChild(defs);

  const wireLayer = svg("g", { class: "wires", "data-testid": "wires" });
  const nodeLayer = svg("g", { class: "nodes", "data-testid": "nodes" });
  root.append(wireLayer, nodeLayer);

  let drawnWires = 0;
  let feedbackLanes = 0;
  for (const conn of spec.connections) {
    const [srcName, srcPort] = conn.from;
    const [dstName, dstPort] = conn.to;
    const src = byName.get(srcName);
    const dst = byName.get(dstName);
    if (!src || !dst) continue; // a dangling wire is the API's problem to report

    const si = Math.max(0, src._ports.outputs.indexOf(srcPort));
    const di = Math.max(0, dst._ports.inputs.indexOf(dstPort));
    const a = portPosition(src, "outputs", si, src._ports.outputs.length || 1);
    const b = portPosition(dst, "inputs", di, dst._ports.inputs.length || 1);

    // Each feedback wire gets its own lane so two of them do not overlap.
    const backward = b.x < a.x;
    const lane = backward ? feedbackLanes++ : 0;
    wireLayer.appendChild(
      svg("path", {
        d: wirePath(a, b, src, dst, lane),
        "marker-end": "url(#wire-arrow)",
        class: "wire",
        "data-wire": `${srcName}.${srcPort}->${dstName}.${dstPort}`,
        "data-from": srcName,
        "data-to": dstName,
        "data-lane": lane,
        tabindex: "0",
      })
    );
    const path = wireLayer.lastChild;
    const pick = () => {
      for (const w of root.querySelectorAll(".wire[data-selected]")) {
        w.removeAttribute("data-selected");
      }
      path.setAttribute("data-selected", "true");
      handlers.onWireSelect?.(conn);
    };
    path.addEventListener("click", pick);
    path.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
    });
    drawnWires += 1;
  }

  for (const block of spec.blocks) {
    const { x, y } = block._pos;
    const g = svg("g", {
      class: "node",
      "data-block": block.name,
      "data-type": block.type,
      "data-x": x,
      "data-y": y,
      tabindex: "0",
      role: "button",
      "aria-label": `${block.name}, ${block.type}`,
    });
    if (!block._pos.placed) g.setAttribute("data-auto-placed", "true");

    g.appendChild(nodePath(block));
    g.appendChild(
      svg("text", { x: x + NODE.width / 2, y: y + 21, class: "node-name" }, block.name)
    );
    g.appendChild(
      svg("text", { x: x + NODE.width / 2, y: y + 37, class: "node-type" }, block.type)
    );

    for (const side of ["inputs", "outputs"]) {
      const names = block._ports[side];
      names.forEach((port, i) => {
        const p = portPosition(block, side, i, names.length);
        const dot = svg("circle", {
          cx: p.x, cy: p.y, r: NODE.portRadius,
          class: `port port-${side}`,
          "data-port": `${block.name}.${port}`,
          "data-side": side,
        });
        if (side === "outputs" && handlers.onConnect) {
          dot.addEventListener("pointerdown", (event) => {
            event.preventDefault();
            event.stopPropagation();  // not a node drag
            startWire(root, block, port, p, handlers);
          });
        }
        g.appendChild(dot);
      });
    }

    const select = () => {
      for (const other of root.querySelectorAll(".node[data-selected]")) {
        other.removeAttribute("data-selected");
      }
      g.setAttribute("data-selected", "true");
      handlers.onSelect?.(block);
    };
    g.addEventListener("click", select);
    g.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(); }
    });

    // Drag to reposition. The move is written into the spec's `layout`, which is
    // the only place position lives — the canvas owns no state of its own.
    g.addEventListener("pointerdown", (event) => {
      if (event.target.classList.contains("port")) return; // that starts a wire
      event.preventDefault();
      select();
      const start = toDiagram(root, event);
      const origin = { x: block._pos.x, y: block._pos.y };
      let moved = false;
      g.setPointerCapture(event.pointerId);

      const onMove = (e) => {
        const now = toDiagram(root, e);
        const dx = now.x - start.x;
        const dy = now.y - start.y;
        if (!moved && Math.hypot(dx, dy) < 3) return; // ignore click jitter
        moved = true;
        // Move by transform and redraw only the wires that touch this node.
        // Re-rendering the canvas mid-drag would destroy the very element
        // holding the pointer capture, ending the drag after one frame.
        block._pos.x = origin.x + dx;
        block._pos.y = origin.y + dy;
        g.setAttribute("transform", `translate(${dx} ${dy})`);
        redrawWiresFor(root, spec, byName, block.name);
      };
      const onUp = () => {
        g.releasePointerCapture(event.pointerId);
        g.removeEventListener("pointermove", onMove);
        g.removeEventListener("pointerup", onUp);
        if (!moved) return;
        // Position lives in the spec and nowhere else.
        block.layout = { x: Math.round(block._pos.x), y: Math.round(block._pos.y) };
        handlers.onMoveEnd?.(block);
      };
      g.addEventListener("pointermove", onMove);
      g.addEventListener("pointerup", onUp);
    });

    nodeLayer.appendChild(g);
  }

  fitViewBox(root, spec);
  return { nodes: spec.blocks.length, wires: drawnWires, unplaced };
}

/** Recompute the `d` of every wire touching `name`, from current positions. */
function redrawWiresFor(root, spec, byName, name) {
  for (const conn of spec.connections) {
    const [srcName, srcPort] = conn.from;
    const [dstName, dstPort] = conn.to;
    if (srcName !== name && dstName !== name) continue;
    const src = byName.get(srcName);
    const dst = byName.get(dstName);
    if (!src || !dst) continue;
    const path = root.querySelector(
      `[data-wire="${srcName}.${srcPort}->${dstName}.${dstPort}"]`
    );
    if (!path) continue;
    const si = Math.max(0, src._ports.outputs.indexOf(srcPort));
    const di = Math.max(0, dst._ports.inputs.indexOf(dstPort));
    const a = portPosition(src, "outputs", si, src._ports.outputs.length || 1);
    const b = portPosition(dst, "inputs", di, dst._ports.inputs.length || 1);
    path.setAttribute("d", wirePath(a, b, src, dst, Number(path.dataset.lane || 0)));
  }
}

/** Drag from an output port; drop on an input port to connect. */
function startWire(root, srcBlock, srcPort, from, handlers) {
  const ghost = svg("path", { class: "wire wire-ghost", "data-testid": "wire-ghost" });
  root.appendChild(ghost);

  const move = (e) => {
    const to = toDiagram(root, e);
    ghost.setAttribute("d", wirePath(from, to));
  };
  const up = (e) => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    ghost.remove();
    const target = document.elementFromPoint(e.clientX, e.clientY);
    const port = target?.closest?.(".port-inputs")?.dataset?.port;
    if (!port) return;                       // dropped on nothing; no-op
    const [dstName, dstPort] = splitPort(port);
    if (dstName === srcBlock.name) return;   // no self-connection
    handlers.onConnect({
      from: [srcBlock.name, srcPort],
      to: [dstName, dstPort],
    });
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

/** `"block.port"` -> `["block", "port"]`, splitting on the *last* dot so block
 *  names containing dots still resolve. */
function splitPort(id) {
  const i = id.lastIndexOf(".");
  return [id.slice(0, i), id.slice(i + 1)];
}

/** Size the viewBox to the drawn content, with a margin. */
function fitViewBox(root, spec) {
  const xs = spec.blocks.map((b) => b._pos.x);
  const ys = spec.blocks.map((b) => b._pos.y);
  const pad = 28;
  const minX = Math.min(...xs, 0) - pad;
  const minY = Math.min(...ys, 0) - pad;
  const width = Math.max(...xs) + NODE.width + pad - minX;
  const height = Math.max(...ys) + NODE.height + pad - minY;
  root.setAttribute("viewBox", `${minX} ${minY} ${width} ${height}`);
  root.setAttribute("preserveAspectRatio", "xMidYMid meet");
  // Block diagrams are wide and flat; a fixed-height box letterboxes them badly
  // and shrinks the labels. Let the element take its content's aspect ratio,
  // bounded by CSS so a tall diagram cannot run off the screen.
  root.style.aspectRatio = `${width} / ${height}`;
}

/** Mark the blocks a validation problem points at. Used once 7d lands. */
export function highlightProblems(root, problems = []) {
  for (const node of root.querySelectorAll(".node[data-problem]")) {
    node.removeAttribute("data-problem");
  }
  for (const problem of problems) {
    for (const name of [problem.block, ...(problem.blocks || [])]) {
      if (!name) continue;
      root.querySelector(`.node[data-block="${name}"]`)?.setAttribute("data-problem", "true");
    }
  }
}

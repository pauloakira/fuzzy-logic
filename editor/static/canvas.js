// SVG block-diagram canvas.
//
// Renders a spec document: nodes at their `layout` coordinates, ports on the
// node edges, wires between them. No dependencies and no build step — the shapes
// are a few dozen lines of SVG, which is cheaper than a flow-canvas library and
// its toolchain for the ten block types this project has.
//
// The node shapes follow Simulink's conventions rather than the Mermaid figure
// in the reports: the outline says what kind of block it is (a gain is a
// triangle, a sum is a circle, everything else a rectangle), the face carries
// the icon or equation it implements, and the block's *name* sits underneath.

const SVG_NS = "http://www.w3.org/2000/svg";

export const NODE = { width: 100, height: 52, portRadius: 4, labelGap: 14 };

/** Blocks sampled at the control rate. Simulink annotates sample time rather
 *  than changing the shape, so these get a small `Ts` tag in the corner. */
const SAMPLED = new Set(["FISBlock", "PIDBlock", "StateFeedback"]);

/**
 * How each block draws itself, following Simulink's conventions: the outline
 * says what *kind* of thing it is (a gain is a triangle, a sum is a circle) and
 * the face carries an icon or the equation it implements — `1/s`, `x' = Ax+Bu`.
 * The block's *name* goes underneath, not inside.
 *
 * Sources: mathworks.com/help/simulink/ug/configure-model-element-names-and-labels.html
 *          mathworks.com/help/simulink/slref/sum.html
 */
const SHAPE = { Gain: "triangle", StateFeedback: "triangle", Sum: "circle" };

function num(v, digits = 3) {
  if (typeof v !== "number") return String(v ?? "");
  if (!Number.isFinite(v)) return v > 0 ? "\u221e" : "-\u221e";
  return String(Number(v.toPrecision(digits)));
}

/** What goes on the block face. */
function icon(block) {
  const p = block.params || {};
  switch (block.type) {
    case "Gain": return { text: Array.isArray(p.k) ? "K" : num(p.k) };
    case "StateFeedback": return { text: "-K\u00b7x" };
    case "Constant":
      return { text: Array.isArray(p.value) ? "c" : num(p.value) };
    case "Select": return { text: `u[${p.index ?? 0}]` };
    case "Harmonic": return { glyph: "sine" };
    case "Step": return { glyph: "step" };
    case "Saturation": return { glyph: "saturation" };
    case "Sum": return { text: "" };  // the port signs are the icon
    case "StateSpacePlant": return { lines: ["x' = Ax+Bu", "y = Cx+Du"] };
    case "MotorPlant": return { lines: ["\u03c9' = k\u00b7V - \u03c9", "V' = u"] };
    case "Observer": return { lines: ["x\u0302' = Ax\u0302+Bu", "+ L(y-Cx\u0302)"] };
    case "PIDBlock": return { text: "PID" };
    case "FISBlock": return { text: "FIS", sub: "Mamdani" };
    default: return { text: block.type };
  }
}

/** Small line drawings, the way Simulink draws its source and nonlinearity icons. */
const GLYPHS = {
  sine: (w, h) => {
    const pts = [];
    for (let i = 0; i <= 24; i += 1) {
      const t = i / 24;
      pts.push(`${(t * w).toFixed(1)},${(h / 2 - Math.sin(t * Math.PI * 2) * h * 0.34).toFixed(1)}`);
    }
    return `M ${pts.join(" L ")}`;
  },
  step: (w, h) => `M 0 ${h * 0.78} L ${w * 0.42} ${h * 0.78} L ${w * 0.42} ${h * 0.22} L ${w} ${h * 0.22}`,
  saturation: (w, h) =>
    `M 0 ${h * 0.82} L ${w * 0.3} ${h * 0.82} L ${w * 0.7} ${h * 0.18} L ${w} ${h * 0.18}`,
};

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
  const { width: w, height: h } = NODE;
  const py = y + (h / (count + 1)) * (index + 1);
  if (SHAPE[block.type] === "circle") {
    // Sit on the circle itself, not on the bounding box, or the wire would end
    // in mid-air beside a round sum block.
    const r = Math.min(w, h) / 2;
    const dx = Math.sqrt(Math.max(r * r - (py - y - h / 2) ** 2, 0));
    return { x: x + w / 2 + (side === "inputs" ? -dx : dx), y: py };
  }
  return { x: side === "inputs" ? x : x + w, y: py };
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
  switch (SHAPE[block.type]) {
    case "triangle":
      // A gain points in the direction of signal flow, as Simulink draws it.
      return svg("polygon", {
        points: `${x},${y} ${x + w},${y + h / 2} ${x},${y + h}`,
        class: "node-shape",
      });
    case "circle":
      return svg("circle", {
        cx: x + w / 2, cy: y + h / 2, r: Math.min(w, h) / 2, class: "node-shape",
      });
    default:
      return svg("rect", { x, y, width: w, height: h, class: "node-shape" });
  }
}

/** The face of the block: an icon, an equation, or a value. */
function nodeIcon(block) {
  const { x, y } = block._pos;
  const { width: w, height: h } = NODE;
  const g = svg("g", { class: "node-icon" });
  const spec = icon(block);
  const cx = SHAPE[block.type] === "triangle" ? x + w * 0.38 : x + w / 2;

  if (spec.glyph) {
    const pad = { x: w * 0.2, y: h * 0.26 };
    const path = svg("path", {
      d: GLYPHS[spec.glyph](w - pad.x * 2, h - pad.y * 2),
      class: "glyph",
      transform: `translate(${x + pad.x} ${y + pad.y})`,
    });
    g.appendChild(path);
    return g;
  }
  if (spec.lines) {
    spec.lines.forEach((line, i) => {
      g.appendChild(svg("text", {
        x: cx, y: y + h / 2 + (i - (spec.lines.length - 1) / 2) * 12 + 4,
        class: "node-eq",
      }, line));
    });
    return g;
  }
  if (spec.text) {
    g.appendChild(svg("text", {
      x: cx, y: y + h / 2 + (spec.sub ? -1 : 4), class: "node-face",
    }, spec.text));
    if (spec.sub) {
      g.appendChild(svg("text", { x: cx, y: y + h / 2 + 13, class: "node-sub" }, spec.sub));
    }
  }
  return g;
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
  // A wired input is marked by the arrowhead, as in Simulink; its port dot would
  // only cover the arrow up. Unwired inputs keep theirs, as the drop hint.
  const wiredInputs = new Set(
    spec.connections.map((c) => `${c.to[0]}.${c.to[1]}`)
  );
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
    g.appendChild(nodeIcon(block));
    // The name sits under the block, which is where Simulink puts it — the face
    // is for the icon.
    g.appendChild(
      svg("text", {
        x: x + NODE.width / 2, y: y + NODE.height + NODE.labelGap, class: "node-name",
      }, block.name)
    );
    if (SAMPLED.has(block.type)) {
      // Inside the outline, which for a triangle means well short of its corner.
      const tx = x + NODE.width * (SHAPE[block.type] === "triangle" ? 0.42 : 1) - 4;
      g.appendChild(svg("text", { x: tx, y: y + 11, class: "node-ts" }, "Ts"));
    }

    for (const side of ["inputs", "outputs"]) {
      const names = block._ports[side];
      names.forEach((port, i) => {
        const p = portPosition(block, side, i, names.length);
        // A Sum block's signs are its icon, drawn beside each input port.
        if (block.type === "Sum" && side === "inputs") {
          const sign = (block.params?.signs || [])[i];
          g.appendChild(svg("text", {
            x: p.x + 11, y: p.y + 4, class: "port-sign",
          }, sign < 0 ? "\u2212" : "+"));
        }
        const dot = svg("circle", {
          cx: p.x, cy: p.y, r: NODE.portRadius,
          class: `port port-${side}`,
          "data-port": `${block.name}.${port}`,
          "data-side": side,
        });
        if (side === "inputs" && wiredInputs.has(`${block.name}.${port}`)) {
          dot.setAttribute("data-wired", "true");
        }
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

  // An edit must not throw away the user's pan or zoom.
  if (root.dataset.userView === "true") {
    root.dataset.baseWidth = String(contentBox(spec).w);
  } else {
    fitView(root, spec);
  }
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

export const ZOOM = { min: 0.15, max: 6, step: 1.15 };

/** The current viewBox as an object. */
export function getView(root) {
  const [x, y, w, h] = (root.getAttribute("viewBox") || "0 0 100 100")
    .split(/\s+/).map(Number);
  return { x, y, w, h };
}

export function setView(root, view) {
  // Four decimals, not two: the viewBox is the only place the view is stored, so
  // rounding it is a lossy read-modify-write and the error accumulates over a
  // sequence of zooms until the aspect ratio visibly drifts.
  root.setAttribute("viewBox",
    `${view.x.toFixed(4)} ${view.y.toFixed(4)} ${view.w.toFixed(4)} ${view.h.toFixed(4)}`);
  const base = Number(root.dataset.baseWidth) || view.w;
  root.dataset.zoom = (base / view.w).toFixed(3);
}

/** The bounding box of the drawn content, with a margin. */
function contentBox(spec) {
  const xs = spec.blocks.map((b) => b._pos.x);
  const ys = spec.blocks.map((b) => b._pos.y);
  const pad = 28;
  const x = Math.min(...xs, 0) - pad;
  const y = Math.min(...ys, 0) - pad;
  return {
    x, y,
    w: Math.max(...xs) + NODE.width + pad - x,
    h: Math.max(...ys) + NODE.height + NODE.labelGap + pad - y,
  };
}

/**
 * Frame the whole diagram and clear any pan or zoom.
 *
 * Block diagrams are wide and flat, so the element takes its content's aspect
 * ratio (bounded by CSS) rather than sitting letterboxed in a fixed-height box.
 * Keeping the viewBox aspect equal to the element's is also what stops zooming
 * from distorting or letterboxing later.
 */
export function fitView(root, spec) {
  const box = contentBox(spec);
  root.setAttribute("preserveAspectRatio", "xMidYMid meet");
  root.style.aspectRatio = `${box.w} / ${box.h}`;
  root.dataset.baseWidth = String(box.w);
  delete root.dataset.userView;
  setView(root, box);
}

/**
 * Wheel to zoom about the cursor, drag the background to pan.
 *
 * Once the user has moved the view it is theirs: `renderDiagram` stops refitting
 * on every edit, or the diagram would snap back to fit on each keystroke.
 */
export function enablePanZoom(root, onChange = null) {
  if (root.dataset.panzoom === "true") return;
  root.dataset.panzoom = "true";

  root.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomBy(root, event.deltaY > 0 ? ZOOM.step : 1 / ZOOM.step, event);
    onChange?.();
  }, { passive: false });

  root.addEventListener("pointerdown", (event) => {
    // Only the empty background pans; nodes, wires and ports have their own drags.
    if (event.target.closest(".node, .wire, .port")) return;
    event.preventDefault();
    root.setPointerCapture(event.pointerId);
    root.dataset.panning = "true";
    const start = { x: event.clientX, y: event.clientY };
    const from = getView(root);

    const move = (e) => {
      // Convert the screen delta with the current scale, so a pan tracks the
      // cursor exactly at any zoom level.
      const scale = from.w / (root.clientWidth || 1);
      root.dataset.userView = "true";
      setView(root, {
        ...from,
        x: from.x - (e.clientX - start.x) * scale,
        y: from.y - (e.clientY - start.y) * scale,
      });
    };
    const up = () => {
      root.releasePointerCapture(event.pointerId);
      delete root.dataset.panning;
      root.removeEventListener("pointermove", move);
      root.removeEventListener("pointerup", up);
      onChange?.();
    };
    root.addEventListener("pointermove", move);
    root.addEventListener("pointerup", up);
  });
}

/** Zoom by `factor`, keeping the point under `event` (or the centre) fixed. */
export function zoomBy(root, factor, event = null) {
  const view = getView(root);
  const base = Number(root.dataset.baseWidth) || view.w;
  const nextW = Math.min(
    base / ZOOM.min, Math.max(base / ZOOM.max, view.w * factor)
  );
  const applied = nextW / view.w;
  const anchor = event ? toDiagram(root, event)
                       : { x: view.x + view.w / 2, y: view.y + view.h / 2 };
  root.dataset.userView = "true";
  setView(root, {
    x: anchor.x - (anchor.x - view.x) * applied,
    y: anchor.y - (anchor.y - view.y) * applied,
    w: view.w * applied,
    h: view.h * applied,
  });
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

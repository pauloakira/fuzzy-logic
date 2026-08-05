"""HTTP API for the block-diagram editor.

Deliberately headless: this module serves JSON and nothing else, so the whole
backend is exercisable with `TestClient` under the same CI as the library. The
canvas (step 7c onward) is a client of these endpoints, not a prerequisite for
testing them.

The spec file stays the source of truth — every endpoint speaks the same
`fuzzy.spec` documents that a human can write by hand, and none of them can
express something a spec file cannot.

    uvicorn editor.api:app --reload

Endpoints
---------
`GET  /api/palette`   every registered block type with its editable parameters
`GET  /api/diagrams`  spec files discoverable under the repository root
`GET  /api/diagram`   load one spec file
`POST /api/validate`  structural problems in a posted spec, as data
`POST /api/simulate`  run a posted spec and return decimated signals
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from fuzzy.fis import FISValidationError
from fuzzy.membership import TermError
from fuzzy.rules import RuleError
from fuzzy.sim import AlgebraicLoopError, Diagram, WiringError, simulate
from fuzzy.spec import SpecError, from_spec, palette, to_spec

REPO_ROOT = Path(__file__).resolve().parents[1]

MAX_T_MAX = 1000.0
"""Longest simulation the API will run. A browser should not be able to wedge
the server with an unbounded horizon."""

MAX_POINTS = 4000
"""Decimation target. A 40 s run at dt=5 ms is 8001 samples per signal, which is
megabytes of JSON for a plot that cannot resolve it."""

STATIC_DIR = Path(__file__).resolve().parent / "static"

MEDIA_TYPES = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}

app = FastAPI(title="fuzzy-logic block editor", version="0.1.0")


def _stamped(text: str) -> str:
    """Rewrite every `/static/x.y` reference to carry the file's mtime.

    With no bundler there is no content hash in the filenames, and browsers cache
    ES modules and stylesheets hard enough that an edited file keeps running the
    old code through a reload — a changed rule or function silently does nothing.

    Stamping has to cover *module imports too*, not just the tags in the page:
    `app.js` imports `canvas.js` by absolute path, so versioning only what the
    HTML references leaves the deepest modules stale, which is exactly the trap
    this walked into once already.
    """
    for asset in sorted(STATIC_DIR.iterdir()):
        if asset.suffix in MEDIA_TYPES:
            stamp = int(asset.stat().st_mtime)
            text = text.replace(
                f"/static/{asset.name}", f"/static/{asset.name}?v={stamp}"
            )
    return text


@app.get("/")
def index() -> HTMLResponse:
    """The editor page. Plain ES modules — nothing is built or bundled."""
    return HTMLResponse(_stamped((STATIC_DIR / "index.html").read_text()))


@app.get("/static/{name}")
def static_asset(name: str) -> Response:
    """Serve one front-end file, with its own references stamped."""
    path = (STATIC_DIR / name).resolve()
    if path.parent != STATIC_DIR or not path.is_file():
        raise HTTPException(404, detail={"error": f"no such asset: {name}"})
    media = MEDIA_TYPES.get(path.suffix, "application/octet-stream")
    body: str | bytes = (
        _stamped(path.read_text())
        if path.suffix in MEDIA_TYPES
        else path.read_bytes()
    )
    return Response(body, media_type=media)


@app.middleware("http")
async def _no_store(request: Any, call_next: Any) -> Any:
    """Never cache the front end.

    With no bundler there is no content hash in the filenames, and browsers cache
    ES modules aggressively enough that an edited module keeps running the old
    code through a reload. For a local editor, correctness beats the cache.
    """
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    return response


# ----- request models ---------------------------------------------------------


class SpecPayload(BaseModel):
    spec: dict[str, Any]


class SavePayload(SpecPayload):
    path: str
    overwrite: bool = False


class FISPreviewPayload(BaseModel):
    fis: dict[str, Any]
    resolution: int = Field(default=201, ge=11, le=1001)
    surface_resolution: int = Field(default=25, ge=5, le=61)


class SimulatePayload(SpecPayload):
    t_max: float = Field(default=10.0, gt=0.0, le=MAX_T_MAX)
    dt_control: float = Field(default=0.005, gt=0.0)
    n_substeps: int = Field(default=1, ge=1, le=64)
    max_points: int = Field(default=MAX_POINTS, ge=2, le=20000)


class OperatingPoint(BaseModel):
    """Where to linearize one block: its state, and its inputs by port name."""

    x: list[float] | None = None
    u: dict[str, Any] | None = None


class AnalyzePayload(SpecPayload):
    n_omega: int = Field(default=400, ge=32, le=4000)
    # Per block name. A block not named here is linearized about its own initial
    # state with zero on every input.
    operating_point: dict[str, OperatingPoint] | None = None
    # Also linearize the diagram as a whole, keyed `__diagram__` in
    # `operating_point`. Its poles are the closed-loop poles.
    closed_loop: bool = True
    # Break the loop here and return L(s) with its stability margins. `""`
    # disables it; `None` picks the wire feeding the first stateful block.
    loop_break: str | None = None
    n_locus: int = Field(default=200, ge=20, le=2000)


# ----- helpers ----------------------------------------------------------------


def _resolve(path: str) -> Path:
    """Resolve a request path inside the repository, or refuse.

    The editor is a local tool, but "local" is not a reason to let a URL read
    anything on the filesystem.
    """
    candidate = (REPO_ROOT / path).resolve()
    if not candidate.is_relative_to(REPO_ROOT):
        raise HTTPException(
            400, detail={"error": f"path escapes the repository: {path}"}
        )
    if not candidate.is_file():
        raise HTTPException(404, detail={"error": f"no such file: {path}"})
    return candidate


def _problem(exc: Exception) -> dict[str, Any]:
    """Render a library exception as structured data the canvas can act on.

    This is what phases 7a and §11.4 were for: the client gets the offending
    block, port, or rule list, not just a sentence to display.
    """
    out: dict[str, Any] = {"error": str(exc), "type": type(exc).__name__}
    for attr in ("block", "port", "related", "blocks", "problems"):
        value = getattr(exc, attr, None)
        if value:
            out[attr] = value
    return out


def _ports(diagram: Diagram) -> dict[str, dict[str, list[str]]]:
    """Resolved port names per block.

    A spec does not carry port names — they belong to the block type. But for
    `Sum` they depend on the `ports` parameter and for `FISBlock` on the FIS's
    input variables, so they cannot be read off the class either. Resolving them
    from the instantiated diagram is the only way to be right for every block.
    """
    return {
        b.name: {"inputs": list(b.inputs), "outputs": list(b.outputs)}
        for b in diagram.blocks
    }


def _build(spec: dict[str, Any]) -> Diagram:
    try:
        return from_spec(spec)
    except (SpecError, WiringError, FISValidationError, TermError, RuleError) as exc:
        raise HTTPException(422, detail=_problem(exc)) from exc


def _decimate(values: np.ndarray, max_points: int) -> list:
    """Keep at most `max_points` samples, always including the last one."""
    n = len(values)
    if n <= max_points:
        return np.asarray(values).tolist()
    idx = np.unique(np.linspace(0, n - 1, max_points).astype(int))
    return np.asarray(values)[idx].tolist()


# ----- endpoints --------------------------------------------------------------


@app.get("/api/palette")
def get_palette() -> dict[str, Any]:
    """Every registered block type and its editable parameters.

    Introspected from each block's `__init__`, so a newly registered block shows
    up here without the editor being changed.
    """
    def entry(p: Any) -> dict[str, Any]:
        default = p.default
        # PIDBlock defaults lo/hi to +/-inf, which strict JSON cannot express.
        if isinstance(default, float) and not np.isfinite(default):
            default = None
        return {
            "name": p.name,
            "default": default,
            "annotation": p.annotation,
            "required": p.required,
        }

    from fuzzy.spec import REGISTRY

    def sides(type_name: str) -> dict[str, list[str]]:
        target = REGISTRY[type_name]
        cls = target if isinstance(target, type) else None
        return {
            "inputs": list(getattr(cls, "inputs", ()) or ()),
            "outputs": list(getattr(cls, "outputs", ()) or ()),
        }

    return {
        "blocks": {
            name: {"params": [entry(p) for p in params], **sides(name)}
            for name, params in palette().items()
        }
    }


@app.get("/api/diagrams")
def list_diagrams() -> dict[str, Any]:
    """Spec files discoverable in the repository, for an Open dialog."""
    # `diagram*.json` rather than the exact name, so drafts saved by the editor
    # are reopenable — otherwise saving produces a file you cannot get back to.
    found = sorted(
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("diagram*.json")
        if ".claude" not in p.parts and "venv" not in p.parts
    )
    return {"diagrams": found}


@app.get("/api/diagram")
def get_diagram(path: str) -> dict[str, Any]:
    """Load one spec file. Round-tripped through the library, so what the canvas
    receives is exactly what the simulator would build."""
    import json

    resolved = _resolve(path)
    try:
        raw = json.loads(resolved.read_text())
    except json.JSONDecodeError as exc:
        raise HTTPException(422, detail={"error": f"invalid JSON: {exc}"}) from exc
    diagram = _build(raw)
    return {"path": path, "spec": to_spec(diagram), "ports": _ports(diagram)}


@app.post("/api/diagram")
def save_diagram(payload: SavePayload) -> dict[str, Any]:
    """Write a spec to disk.

    Two guards, both deliberate:

    - The spec must build before anything is written. Saving a document that
      cannot be loaded back turns an editing mistake into a broken file.
    - Overwriting an existing file requires `overwrite`. The committed
      `diagram.json` files are generated artefacts that integration tests assert
      against, so an editor must not clobber one by accident. The client defaults
      to a `.draft.json` path; replacing the original is a deliberate act.
    """
    import json

    if not payload.path.endswith(".json"):
        raise HTTPException(400, detail={"error": "path must end in .json"})

    target = (REPO_ROOT / payload.path).resolve()
    if not target.is_relative_to(REPO_ROOT):
        raise HTTPException(
            400, detail={"error": f"path escapes the repository: {payload.path}"}
        )
    if not target.parent.is_dir():
        raise HTTPException(
            400, detail={"error": f"no such directory: {target.parent.name}"}
        )
    if target.exists() and not payload.overwrite:
        raise HTTPException(
            409,
            detail={
                "error": f"{payload.path} already exists; pass overwrite to replace it",
                "path": payload.path,
            },
        )

    diagram = _build(payload.spec)  # 422 with structured detail if it will not load
    normalised = to_spec(diagram)
    target.write_text(json.dumps(normalised, indent=2) + "\n")
    return {
        "path": payload.path,
        "bytes": target.stat().st_size,
        "spec": normalised,
        "ports": _ports(diagram),
    }


@app.post("/api/validate")
def post_validate(payload: SpecPayload) -> dict[str, Any]:
    """Structural problems in a spec, as data.

    Returns 200 with `ok: false` rather than an error status: a half-finished
    diagram on a canvas is an expected state, not a failed request.
    """
    try:
        diagram = from_spec(payload.spec)
    except (SpecError, WiringError, FISValidationError, TermError, RuleError) as exc:
        return {"ok": False, "problems": [_problem(exc)]}

    problems: list[dict[str, Any]] = []
    try:
        diagram.evaluate(0.0, diagram.initial_state())
    except (WiringError, AlgebraicLoopError) as exc:
        problems.append(_problem(exc))

    # Non-fatal advice the canvas should surface rather than hide.
    advice: list[str] = []
    limit = diagram.stability_limit()
    if limit is not None:
        advice.append(f"RK4 stability limit for this diagram: dt <= {limit:.4g} s")
    tau = diagram.slowest_tau()
    if tau is not None:
        advice.append(f"slowest time constant: {tau:.4g} s (settle >= {4 * tau:.4g} s)")

    return {
        "ok": not problems,
        "problems": problems,
        "advice": advice,
        "n_states": diagram.n_states,
        "blocks": [b.name for b in diagram.blocks],
        "ports": _ports(diagram),
    }


@app.post("/api/fis/preview")
def fis_preview(payload: FISPreviewPayload) -> dict[str, Any]:
    """Membership curves, the control surface, and validation for one controller.

    All the numerics stay on this side. The membership functions are simple
    enough to reimplement in JavaScript, but Mamdani inference is not, and having
    the curves and the surface come from *different* implementations is exactly
    how an editor ends up drawing something the simulator does not agree with.
    """
    from fuzzy.fis import FISSpec

    try:
        spec = FISSpec.from_spec(payload.fis)
    except (TermError, RuleError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, detail=_problem(exc)) from exc

    def curves(var: Any) -> dict[str, Any]:
        grid = var.universe(payload.resolution)
        return {
            "low": var.low,
            "high": var.high,
            "grid": grid.tolist(),
            "terms": {
                name: {
                    "kind": term.kind,
                    "params": list(term.params),
                    "mu": np.asarray(term(grid), dtype=float).tolist(),
                }
                for name, term in var.terms.items()
            },
            "partition_error": var.partition_error(),
        }

    body: dict[str, Any] = {
        "inputs": {name: curves(var) for name, var in spec.inputs.items()},
        "output": curves(spec.output),
        "output_terms": list(spec.output.terms),
        "rules": spec.rules.to_spec(),
        "problems": spec.validate(),
    }

    # A control surface only means something for two inputs; a one-input
    # controller gets a curve instead, and anything else gets neither.
    names = list(spec.inputs)
    if len(names) in (1, 2):
        engine = spec.build(strict=False)
        n = payload.surface_resolution
        axes = [spec.inputs[k].universe(n).tolist() for k in names]
        if len(names) == 1:
            z = [[engine.evaluate({names[0]: float(a)}) for a in axes[0]]]
        else:
            z = [
                [engine.evaluate({names[0]: float(a), names[1]: float(b)})
                 for a in axes[0]]
                for b in axes[1]
            ]
        body["surface"] = {"axes": names, "x": axes[0],
                           "y": axes[1] if len(names) == 2 else [0.0], "z": z}
    return body


@app.post("/api/simulate")
def post_simulate(payload: SimulatePayload) -> dict[str, Any]:
    """Run a spec and return decimated signals, plus any warnings it raised.

    Vector signals are split per component (`plant.y[0]`, `plant.y[1]`) because
    that is what a plot consumes. Warnings — the transient-window guard and the
    RK4 stability guard — are returned rather than swallowed; they are usually
    the most useful thing on the screen.
    """
    diagram = _build(payload.spec)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            log = simulate(
                diagram,
                t_max=payload.t_max,
                dt_control=payload.dt_control,
                n_substeps=payload.n_substeps,
            )
        except (WiringError, AlgebraicLoopError) as exc:
            raise HTTPException(422, detail=_problem(exc)) from exc

    signals: dict[str, list] = {}
    for key, values in log.signals.items():
        arr = np.asarray(values, dtype=float)
        if arr.ndim == 1:
            signals[key] = _decimate(arr, payload.max_points)
        else:
            for i in range(arr.shape[1]):
                signals[f"{key}[{i}]"] = _decimate(arr[:, i], payload.max_points)

    return {
        "t": _decimate(log.t, payload.max_points),
        "signals": signals,
        "operating_point": _operating_point(diagram, log),
        "n_samples": int(len(log.t)),
        "returned": len(_decimate(log.t, payload.max_points)),
        "warnings": [str(w.message) for w in caught],
    }


def _operating_point(diagram: Diagram, log: Any) -> dict[str, Any]:
    """Where each stateful block ended up, ready to hand to `/api/analyze`.

    The settled state of a run is a far better place to linearize than `t = 0`:
    `MotorPlant` starts at (0 rpm, 0 V), which is both of its lower clamps at
    once, so the Jacobian there is a corner-average with every gain halved. The
    same motor after 800 s sits at (577 rpm, 57.7 V), well inside its envelope,
    where the linearization is exact.
    """
    if not log.z_final.size:
        return {}
    t_final = float(log.t[-1])
    _, ins = diagram.evaluate(t_final, log.z_final)
    by_name = {b.name: b for b in diagram.blocks}
    out: dict[str, Any] = {}
    for name, span in diagram.state_slices().items():
        u = {
            port: (value.tolist() if isinstance(value, np.ndarray) else float(value))
            for port, value in ins[by_name[name]].items()
        }
        out[name] = {"x": log.z_final[span].tolist(), "u": u}
    # The whole state vector, for the closed-loop linearization.
    out["__diagram__"] = {"x": log.z_final.tolist(), "u": {}}
    return out


@app.post("/api/analyze")
def post_analyze(payload: AnalyzePayload) -> dict[str, Any]:
    """Bode data, poles, and zeros for every block of the diagram that carries state.

    A `StateSpacePlant` is already `(A, B, C, D)` and is analysed as it stands.
    Any other stateful block — `MotorPlant`, say — is **linearized** about an
    operating point first (Ogata §2-7), and the system it yields is marked
    `linearized: true` and carries the `warnings` from that linearization. Those
    warnings are not decoration: a plant linearized where a limiter is active
    produces a Bode plot that looks entirely reasonable and describes nothing.

    The operating point defaults to the block's own initial state with zero on
    every input; `operating_point` overrides it per block. Each output/input
    channel becomes one labelled curve, matching the `plant.y[i]` split the time
    plot already uses.
    """
    from fuzzy.analysis import (
        frequency_grid,
        frequency_response,
        gain_sweep,
        margins,
        root_locus,
    )
    from fuzzy.analysis import poles as _poles
    from fuzzy.analysis import zeros as _zeros
    from fuzzy.blocks import StateSpacePlant
    from fuzzy.linearize import (
        LinearizationError,
        linearize,
        linearize_diagram,
        loop_transfer,
    )

    diagram = _build(payload.spec)
    systems: list[dict[str, Any]] = []

    def points(vals: NDArray[np.complex128]) -> list[list[float]]:
        return [[float(v.real), float(v.imag)] for v in vals]

    def emit(
        name: str,
        A: NDArray[np.float64],
        B: NDArray[np.float64],
        C: NDArray[np.float64],
        D: NDArray[np.float64],
        labels: list[str],
        linearized: bool,
        warns: list[str],
        kind: str,
    ) -> None:
        """Poles, zeros and Bode data for one `(A, B, C, D)`."""
        if not A.size or not B.size:
            return
        n_out, n_in = C.shape[0], B.shape[1]
        pol = _poles(A)
        chan_zeros: dict[tuple[int, int], NDArray[np.complex128]] = {}
        critical = list(pol)
        for i in range(n_out):
            for j in range(n_in):
                z = _zeros(A, B[:, j], C[i], D[i, j])
                chan_zeros[(i, j)] = z
                critical.extend(z)

        omega = frequency_grid(np.asarray(critical), n=payload.n_omega)
        H = frequency_response(A, B, C, D, omega)
        channels = []
        for i in range(n_out):
            for j in range(n_in):
                h = H[:, i, j]
                label = labels[i] if i < len(labels) else f"{name}.y[{i}]"
                if n_in > 1:
                    label += f"<-{j}"
                mag = np.abs(h)
                channels.append({
                    "label": label,
                    "mag_db": (20.0 * np.log10(np.maximum(mag, 1e-12))).tolist(),
                    "phase_deg": np.degrees(np.unwrap(np.angle(h))).tolist(),
                    "zeros": points(chan_zeros[(i, j)]),
                })
        systems.append({
            "name": name, "omega": omega.tolist(), "poles": points(pol),
            "channels": channels, "linearized": linearized,
            "warnings": warns, "kind": kind,
        })

    def default_break(d: Diagram) -> str | None:
        """The wire feeding the first stateful block — a plant's input.

        Any cut around a single loop gives the same `L(s)`, so this is a matter
        of picking a readable one rather than a correct one.
        """
        for b in d.blocks:
            if b.n_states and b.inputs:
                src = d.connections_into(b.name)
                if src:
                    return src[0]
        return None

    # The open loop, with the margins that are the whole reason to compute it.
    loop_at = payload.loop_break
    if loop_at is None:
        loop_at = default_break(diagram)
    if loop_at and diagram.n_states:
        try:
            # The same operating point as the closed loop, or the two models
            # describe different machines: on exercise 1 the diagram's initial
            # state is the motor's clamps, and L(s) taken there is a corner.
            whole = (payload.operating_point or {}).get("__diagram__")
            L = loop_transfer(
                diagram,
                at=loop_at,
                z0=None if whole is None or whole.x is None else np.asarray(whole.x),
            )
            critical = list(_poles(L.A))
            critical.extend(_zeros(L.A, L.B[:, 0], L.C[0], L.D[0, 0]))
            grid = frequency_grid(np.asarray(critical), n=payload.n_omega)
            H = frequency_response(L.A, L.B, L.C, L.D, grid)[:, 0, 0]
            emit(
                f"L(s) broken at {loop_at}",
                L.A, L.B, L.C, L.D, [f"L(s) @ {loop_at}"],
                True, list(L.warnings), "loop",
            )
            if systems and systems[-1].get("kind") == "loop":
                gains, roots = root_locus(
                    L.A, L.B, L.C, L.D, gain_sweep(n=payload.n_locus)
                )
                systems[-1].update({
                    "margins": margins(grid, H),
                    "loop_break": loop_at,
                    # L(jw) on the complex plane, for the Nyquist chart. Sent as
                    # points rather than reconstructed from dB and degrees in the
                    # browser, which would be a lossy round trip for no reason.
                    "nyquist": [[float(v.real), float(v.imag)] for v in H],
                    "locus": {
                        "gains": gains.tolist(),
                        # column-major: one polyline per branch
                        "branches": [
                            [[float(v.real), float(v.imag)] for v in roots[:, j]]
                            for j in range(roots.shape[1])
                        ],
                    },
                })
        except (LinearizationError, KeyError, ValueError, TypeError) as exc:
            systems.append({
                "name": f"L(s) broken at {loop_at}", "omega": [], "poles": [],
                "channels": [], "linearized": True, "failed": str(exc),
                "warnings": [], "kind": "loop",
            })

    # The closed loop: its poles are the ones that say whether this
    # controller stabilizes this plant, which no per-block model can answer.
    if payload.closed_loop and diagram.n_states:
        at = (payload.operating_point or {}).get("__diagram__")
        try:
            loop = linearize_diagram(
                diagram,
                z0=None if at is None or at.x is None else np.asarray(at.x),
                outputs=[
                    f"{b.name}.{p}"
                    for b in diagram.blocks if b.n_states for p in b.outputs
                ],
            )
            emit(
                f"{diagram.name} (closed loop)",
                loop.A, loop.B, loop.C, loop.D,
                [f"{diagram.name}:{lbl}" for lbl in loop.outputs],
                True, list(loop.warnings), "diagram",
            )
        except (LinearizationError, KeyError, ValueError, TypeError) as exc:
            systems.append({
                "name": f"{diagram.name} (closed loop)", "omega": [], "poles": [],
                "channels": [], "linearized": True, "failed": str(exc),
                "warnings": [], "kind": "diagram",
            })

    for block in diagram.blocks:
        warnings: list[str] = []
        linearized = False
        if isinstance(block, StateSpacePlant):
            A, B, C, D = block.A, block.B, block.C, block.D
        elif block.n_states:
            at = (payload.operating_point or {}).get(block.name)
            try:
                lin = linearize(
                    block,
                    x0=None if at is None or at.x is None else np.asarray(at.x),
                    u0=None if at is None else at.u,
                )
            except (LinearizationError, KeyError, ValueError, TypeError) as exc:
                # One block that will not linearize must not sink the others.
                systems.append({
                    "name": block.name, "omega": [], "poles": [], "channels": [],
                    "linearized": True, "failed": str(exc), "warnings": [],
                })
                continue
            A, B, C, D = lin.A, lin.B, lin.C, lin.D
            warnings = list(lin.warnings)
            linearized = True
        else:
            continue

        if not A.size or not B.size:
            continue  # nothing with dynamics to plot

        n_out, n_in = C.shape[0], B.shape[1]
        pol = _poles(A)

        chan_zeros: dict[tuple[int, int], NDArray[np.complex128]] = {}
        critical = list(pol)
        for i in range(n_out):
            for j in range(n_in):
                z = _zeros(A, B[:, j], C[i], D[i, j])
                chan_zeros[(i, j)] = z
                critical.extend(z)

        omega = frequency_grid(np.asarray(critical), n=payload.n_omega)
        H = frequency_response(A, B, C, D, omega)

        channels = []
        for i in range(n_out):
            for j in range(n_in):
                h = H[:, i, j]
                label = f"{block.name}.y[{i}]" if n_out > 1 else f"{block.name}.y"
                if n_in > 1:
                    label += f"<-u[{j}]"
                # Guard log10(0); a true zero of |H| is -inf dB, which JSON and
                # a plot both dislike, so it is floored well below any real curve.
                mag = np.abs(h)
                channels.append({
                    "label": label,
                    "mag_db": (20.0 * np.log10(np.maximum(mag, 1e-12))).tolist(),
                    "phase_deg": np.degrees(np.unwrap(np.angle(h))).tolist(),
                    "zeros": points(chan_zeros[(i, j)]),
                })

        systems.append({
            "name": block.name,
            "omega": omega.tolist(),
            "poles": points(pol),
            "channels": channels,
            "linearized": linearized,
            "warnings": warnings,
            "kind": "block",
        })

    return {"systems": systems}


@app.exception_handler(HTTPException)
def _http_exception_handler(_request: Any, exc: HTTPException) -> JSONResponse:
    """Keep the error shape uniform: always a JSON object under `detail`."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})

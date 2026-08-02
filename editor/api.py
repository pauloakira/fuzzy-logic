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
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
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

app = FastAPI(title="fuzzy-logic block editor", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    """The editor page. Plain ES modules — nothing is built or bundled."""
    return FileResponse(STATIC_DIR / "index.html")


# ----- request models ---------------------------------------------------------


class SpecPayload(BaseModel):
    spec: dict[str, Any]


class SavePayload(SpecPayload):
    path: str
    overwrite: bool = False


class SimulatePayload(SpecPayload):
    t_max: float = Field(default=10.0, gt=0.0, le=MAX_T_MAX)
    dt_control: float = Field(default=0.005, gt=0.0)
    n_substeps: int = Field(default=1, ge=1, le=64)
    max_points: int = Field(default=MAX_POINTS, ge=2, le=20000)


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
        "n_samples": int(len(log.t)),
        "returned": len(_decimate(log.t, payload.max_points)),
        "warnings": [str(w.message) for w in caught],
    }


@app.exception_handler(HTTPException)
def _http_exception_handler(_request: Any, exc: HTTPException) -> JSONResponse:
    """Keep the error shape uniform: always a JSON object under `detail`."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})

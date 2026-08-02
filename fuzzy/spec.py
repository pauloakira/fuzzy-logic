"""Declarative diagram specs — the representation a graphical editor loads and saves.

A spec is plain JSON-compatible data:

```python
{
  "version": 1,
  "name": "sdof_fuzzy",
  "blocks": [
    {"type": "sdof_plant", "name": "plant",
     "params": {"m": 1.0, "c": 0.4, "k": 100.0}, "layout": {"x": 320, "y": 140}},
  ],
  "connections": [{"from": ["force", "y"], "to": ["total", "ext"]}],
}
```

The spec stays the source of truth: it is git-diffable, reviewable, and equally
authorable by hand, by script, or by canvas. `simulate()` never imports this module,
so headless runs are unaffected.

Parameters are discovered from each block's `__init__` signature, so registering a
block is enough to make it fully editable — there is no per-block schema to maintain.
The one exception is a parameter holding a live object that cannot yet be described as
data (today: `FISBlock.fis`, a `MamdaniFIS` whose terms are closures). Those serialise
as a `{"$provide": "<block>.<param>"}` placeholder and must be supplied at load time
via `from_spec(..., objects=...)`. Phase 4 of the design note removes that exception by
making membership functions and rule bases declarative.
"""

from __future__ import annotations

import inspect
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from fuzzy.blocks import (
    Block,
    Constant,
    FISBlock,
    Gain,
    Harmonic,
    Observer,
    PIDBlock,
    Saturation,
    Select,
    StateFeedback,
    StateSpacePlant,
    Step,
    Sum,
    sdof_plant,
)
from fuzzy.sim import Diagram

SPEC_VERSION = 1

Factory = Callable[..., Block]


class SpecError(ValueError):
    """The spec is malformed, or references an unknown block type or object.

    `.block` names the offending block when one is identifiable, so an editor
    can highlight that node rather than reporting a whole-file failure.
    """

    def __init__(self, message: str, block: str | None = None) -> None:
        super().__init__(message)
        self.block = block


# ----- registry --------------------------------------------------------------

REGISTRY: dict[str, Factory] = {}


def register(target: Factory, name: str | None = None) -> Factory:
    """Add a block class or factory to the palette. Usable as a decorator."""
    key = name or getattr(target, "__name__", None)
    if not key:
        raise SpecError("cannot register an anonymous factory without a name")
    REGISTRY[key] = target
    return target


for _t in (
    Constant,
    Step,
    Harmonic,
    Gain,
    Sum,
    Select,
    Saturation,
    StateSpacePlant,
    FISBlock,
    PIDBlock,
    StateFeedback,
    Observer,
):
    register(_t)

# Convenience factory: pleasant to author, normalised to StateSpacePlant on save.
register(sdof_plant)


# ----- parameter introspection ----------------------------------------------


@dataclass(frozen=True)
class Param:
    """One editable parameter of a block type."""

    name: str
    default: Any
    annotation: str
    required: bool


def param_schema(type_name: str) -> list[Param]:
    """Editable parameters of a registered block type, for a UI property panel."""
    try:
        target = REGISTRY[type_name]
    except KeyError:
        raise SpecError(f"unknown block type {type_name!r}") from None
    sig = inspect.signature(target)
    out = []
    for p in sig.parameters.values():
        if p.name in ("self", "name") or p.kind in (
            p.VAR_POSITIONAL,
            p.VAR_KEYWORD,
        ):
            continue
        out.append(
            Param(
                name=p.name,
                default=None if p.default is inspect.Parameter.empty else p.default,
                annotation=(
                    "" if p.annotation is inspect.Parameter.empty else str(p.annotation)
                ),
                required=p.default is inspect.Parameter.empty,
            )
        )
    return out


def palette() -> dict[str, list[Param]]:
    """Every registered block type with its parameters."""
    return {name: param_schema(name) for name in sorted(REGISTRY)}


# ----- JSON coercion ---------------------------------------------------------


class _Opaque(Exception):
    """A value that cannot be represented as data."""


def _jsonify(value: Any) -> Any:
    # Rich objects that can describe themselves as data (FISSpec, Variable, Term,
    # RuleBase) serialise through their own `to_spec`. The owning block coerces
    # the dict back to the rich type in its constructor.
    to_spec = getattr(value, "to_spec", None)
    if callable(to_spec):
        return _jsonify(to_spec())
    if isinstance(value, np.ndarray):
        return _jsonify(value.tolist())
    if isinstance(value, (np.floating, np.integer)):
        return _jsonify(value.item())
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        # JSON has no Infinity/NaN; tag them so a JS client can round-trip too.
        return value if math.isfinite(value) else {"$float": repr(value)}
    if isinstance(value, (list, tuple)):
        return [_jsonify(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonify(v) for k, v in value.items()}
    raise _Opaque(value)


def _unjsonify(value: Any) -> Any:
    if isinstance(value, Mapping):
        if "$float" in value:
            return float(value["$float"])
        if "$provide" in value:
            return value  # resolved later, against `objects`
        return {k: _unjsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unjsonify(v) for v in value]
    return value


# ----- diagram <-> spec ------------------------------------------------------


def block_to_spec(block: Block, layout: Mapping[str, float] | None = None) -> dict:
    """One block as spec data. Opaque params become `$provide` placeholders."""
    type_name = type(block).__name__
    params: dict[str, Any] = {}
    for p in param_schema(type_name):
        if not hasattr(block, p.name):
            raise SpecError(
                f"{type_name}.{p.name} is a constructor parameter but not an "
                f"attribute, so it cannot be serialised"
            )
        try:
            params[p.name] = _jsonify(getattr(block, p.name))
        except _Opaque:
            params[p.name] = {"$provide": f"{block.name}.{p.name}"}
    entry: dict[str, Any] = {"type": type_name, "name": block.name, "params": params}
    if layout:
        entry["layout"] = dict(layout)
    return entry


def to_spec(diagram: Diagram) -> dict:
    """Serialise a diagram to spec data."""
    return {
        "version": SPEC_VERSION,
        "name": diagram.name,
        "blocks": [
            block_to_spec(b, diagram.layout.get(b.name)) for b in diagram.blocks
        ],
        "connections": [
            {"from": list(src), "to": list(dst)} for src, dst in diagram.connections()
        ],
    }


def from_spec(
    spec: Mapping[str, Any], objects: Mapping[str, Any] | None = None
) -> Diagram:
    """Build a diagram from spec data.

    `objects` supplies values for `$provide` placeholders, keyed `"<block>.<param>"`.
    """
    version = spec.get("version", SPEC_VERSION)
    if version != SPEC_VERSION:
        raise SpecError(f"unsupported spec version {version!r}")
    supplied = dict(objects or {})

    d = Diagram(name=str(spec.get("name", "diagram")))
    for entry in spec.get("blocks", []):
        try:
            type_name, block_name = entry["type"], entry["name"]
        except KeyError as exc:
            raise SpecError(f"block entry missing {exc.args[0]!r}") from None
        if type_name not in REGISTRY:
            raise SpecError(
                f"unknown block type {type_name!r}; registered: {sorted(REGISTRY)}",
                block=block_name,
            )
        kwargs = {}
        for key, raw in (entry.get("params") or {}).items():
            value = _unjsonify(raw)
            if isinstance(value, Mapping) and "$provide" in value:
                ref = value["$provide"]
                if ref not in supplied:
                    raise SpecError(
                        f"{block_name}.{key} needs a provided object; pass "
                        f"objects={{{ref!r}: ...}} to from_spec()"
                    )
                value = supplied[ref]
            kwargs[key] = value
        try:
            d.add(REGISTRY[type_name](name=block_name, **kwargs))
        except SpecError:
            raise
        except Exception as exc:
            raise SpecError(
                f"block {block_name!r} ({type_name}): {exc}", block=block_name
            ) from exc
        if entry.get("layout"):
            d.layout[block_name] = dict(entry["layout"])

    for conn in spec.get("connections", []):
        try:
            (sb, sp), (db, dp) = conn["from"], conn["to"]
        except (KeyError, ValueError) as exc:
            raise SpecError(f"malformed connection {conn!r}: {exc}") from None
        for ref in (sb, db):
            if ref not in {b.name for b in d.blocks}:
                # A canvas produces this constantly: delete a block, leave its
                # wires. It must be a structured error, not a bare KeyError.
                raise SpecError(
                    f"connection references unknown block {ref!r}", block=ref
                )
        d.connect((d.block(sb), sp), (d.block(db), dp))
    return d


# ----- files -----------------------------------------------------------------


def save(diagram: Diagram, path: str | Path, indent: int = 2) -> Path:
    """Write a diagram to a `.json` spec file."""
    p = Path(path)
    p.write_text(json.dumps(to_spec(diagram), indent=indent) + "\n")
    return p


def load(path: str | Path, objects: Mapping[str, Any] | None = None) -> Diagram:
    """Read a diagram from a `.json` spec file."""
    return from_spec(json.loads(Path(path).read_text()), objects=objects)

"""Unit tests for the declarative spec layer."""

from __future__ import annotations

import json

import numpy as np
import pytest

from fuzzy.blocks import Harmonic, PIDBlock, Saturation, Select, Sum, sdof_plant
from fuzzy.sim import Diagram, simulate
from fuzzy.spec import (
    REGISTRY,
    SpecError,
    from_spec,
    load,
    palette,
    param_schema,
    save,
    to_spec,
)

M, C, K = 1.0, 0.4, 100.0


def pid_diagram() -> Diagram:
    d = Diagram(name="sdof_pid")
    plant = sdof_plant(M, C, K, x0=0.1, name="plant")
    force = Harmonic(amplitude=1.0, omega=10.0, name="force")
    total = Sum(("ext", "ctrl"), name="total")
    pid = PIDBlock(30.0, 5.0, 10.0, lo=-3.0, hi=3.0, dt=0.005, name="pid")
    pos, vel = Select(0, name="pos"), Select(1, name="vel")
    sat = Saturation(-3.0, 3.0, name="sat")
    d.connect(force, (total, "ext"))
    d.connect(total, plant)
    d.connect(plant, pos)
    d.connect(plant, vel)
    d.connect(pos, (pid, "x"))
    d.connect(vel, (pid, "x_dot"))
    d.connect(pid, sat)
    d.connect(sat, (total, "ctrl"))
    d.layout["plant"] = {"x": 320.0, "y": 140.0}
    return d


# ----- registry and schema ----------------------------------------------------


def test_registry_covers_the_implemented_blocks():
    for name in ("Harmonic", "Sum", "Select", "Saturation", "PIDBlock", "sdof_plant"):
        assert name in REGISTRY


def test_param_schema_reads_the_constructor():
    names = [p.name for p in param_schema("Harmonic")]
    assert names == ["amplitude", "omega", "phase"]  # `name` is excluded


def test_param_schema_marks_required_and_defaults():
    by_name = {p.name: p for p in param_schema("PIDBlock")}
    assert by_name["kp"].required and by_name["kp"].default is None
    assert not by_name["Tt"].required and by_name["Tt"].default == 1.0


def test_param_schema_rejects_unknown_type():
    with pytest.raises(SpecError, match="unknown block type"):
        param_schema("Nope")


def test_palette_is_complete_and_introspectable():
    p = palette()
    assert set(p) == set(REGISTRY)
    assert [q.name for q in p["Select"]] == ["index"]


# ----- round-trip -------------------------------------------------------------


def test_round_trip_preserves_structure():
    original = pid_diagram()
    rebuilt = from_spec(to_spec(original))
    assert [b.name for b in rebuilt.blocks] == [b.name for b in original.blocks]
    assert sorted(rebuilt.connections()) == sorted(original.connections())


def test_round_trip_preserves_layout():
    rebuilt = from_spec(to_spec(pid_diagram()))
    assert rebuilt.layout["plant"] == {"x": 320.0, "y": 140.0}


def test_round_trip_preserves_simulation_results():
    """The real test: a rebuilt diagram must produce identical trajectories."""
    original = pid_diagram()
    rebuilt = from_spec(to_spec(original))
    a = simulate(original, t_max=3.0, dt_control=0.005)
    b = simulate(rebuilt, t_max=3.0, dt_control=0.005)
    assert np.allclose(a.col("plant.y", 0), b.col("plant.y", 0), atol=1e-15)
    assert np.allclose(a["pid.u"], b["pid.u"], atol=1e-15)


def test_factory_normalises_to_its_class():
    """`sdof_plant` is authoring sugar; it saves as an explicit StateSpacePlant."""
    spec = to_spec(pid_diagram())
    plant = next(b for b in spec["blocks"] if b["name"] == "plant")
    assert plant["type"] == "StateSpacePlant"
    assert plant["params"]["A"] == [[0.0, 1.0], [-100.0, -0.4]]


def test_spec_is_json_serialisable(tmp_path):
    path = save(pid_diagram(), tmp_path / "d.json")
    text = path.read_text()
    json.loads(text)  # must be strict JSON — no bare Infinity/NaN
    assert "Infinity" not in text and "NaN" not in text
    rebuilt = load(path)
    assert sorted(rebuilt.connections()) == sorted(pid_diagram().connections())


def test_non_finite_floats_round_trip():
    """An unsaturated PID defaults to +/-inf, which strict JSON cannot express."""
    d = Diagram(name="unsat")
    pid = PIDBlock(1.0, 0.0, 0.0, name="pid")
    pos, vel = Select(0, name="pos"), Select(1, name="vel")
    plant = sdof_plant(M, C, K, name="plant")
    d.connect(plant, pos)
    d.connect(plant, vel)
    d.connect(pos, (pid, "x"))
    d.connect(vel, (pid, "x_dot"))
    d.connect(pid, plant)

    spec = to_spec(d)
    params = next(b for b in spec["blocks"] if b["name"] == "pid")["params"]
    assert params["lo"] == {"$float": "-inf"}
    json.dumps(spec)  # strict JSON, no bare -Infinity

    rebuilt = from_spec(spec)
    assert rebuilt.block("pid").lo == float("-inf")
    assert rebuilt.block("pid").hi == float("inf")


# ----- opaque parameters ------------------------------------------------------


def fis_diagram():
    import sys

    sys.path.insert(
        0,
        str(
            __import__("pathlib").Path(__file__).resolve().parents[2]
            / "exercises"
            / "exercicio2_sdof_vibration_control"
        ),
    )
    import sdof_vibration as S

    from fuzzy.blocks import FISBlock

    d = Diagram(name="sdof_fuzzy")
    plant = sdof_plant(S.M, S.C, S.K, name="plant")
    fis = FISBlock(S.build_fis(), name="fis")
    pos, vel = Select(0, name="pos"), Select(1, name="vel")
    d.connect(plant, pos)
    d.connect(plant, vel)
    d.connect(pos, (fis, "deslocamento"))
    d.connect(vel, (fis, "velocidade"))
    d.connect(fis, plant)
    return d, S


def test_opaque_param_becomes_a_provide_placeholder():
    d, _ = fis_diagram()
    spec = to_spec(d)
    entry = next(b for b in spec["blocks"] if b["name"] == "fis")
    assert entry["params"]["fis"] == {"$provide": "fis.fis"}
    json.dumps(spec)  # still strict JSON


def test_missing_provided_object_raises_with_the_key_to_pass():
    d, _ = fis_diagram()
    with pytest.raises(SpecError, match=r"objects=\{'fis.fis'"):
        from_spec(to_spec(d))


def test_fis_spec_serialises_fully_with_no_placeholder():
    """A FISSpec-backed controller needs nothing supplied at load time."""
    from fuzzy.blocks import FISBlock
    from fuzzy.fis import FISSpec
    from fuzzy.membership import Variable
    from fuzzy.rules import RuleBase

    terms = ["NG", "Z", "PG"]
    fspec = FISSpec(
        inputs={"e": Variable.partition("e", -1.0, 1.0, terms)},
        output=Variable.partition("u", -1.0, 1.0, terms),
        rules=RuleBase.from_table("e", "e", terms, terms, [[t] * 3 for t in terms]),
    )
    d = Diagram(name="fis_spec")
    block = FISBlock(fspec, name="fis")
    d.connect(sdof_plant(M, C, K, name="plant"), Select(0, name="pos"))
    d.connect(d.block("pos"), (block, "e"))
    d.connect(block, d.block("plant"))

    spec = to_spec(d)
    assert "$provide" not in json.dumps(spec)

    rebuilt = from_spec(spec)  # no objects= needed
    loaded = rebuilt.block("fis")
    for x in (-0.9, -0.2, 0.0, 0.4, 0.8):
        args = {"e": x}
        assert loaded._engine.evaluate(args) == block._engine.evaluate(args)


def test_fis_block_accepts_a_plain_dict():
    """Loading a spec hands the block a dict; it coerces to FISSpec itself."""
    from fuzzy.blocks import FISBlock
    from fuzzy.fis import FISSpec
    from fuzzy.membership import Variable
    from fuzzy.rules import RuleBase

    terms = ["NG", "Z", "PG"]
    fspec = FISSpec(
        inputs={"e": Variable.partition("e", -1.0, 1.0, terms)},
        output=Variable.partition("u", -1.0, 1.0, terms),
        rules=RuleBase.from_table("e", "e", terms, terms, [[t] * 3 for t in terms]),
    )
    from_dict = FISBlock(fspec.to_spec(), name="fis")
    assert isinstance(from_dict.fis, FISSpec)
    assert from_dict._engine.evaluate({"e": 0.5}) == fspec.build().evaluate({"e": 0.5})


def test_provided_object_completes_the_round_trip():
    d, S = fis_diagram()
    rebuilt = from_spec(to_spec(d), objects={"fis.fis": S.build_fis()})
    a = simulate(d, t_max=2.0, dt_control=0.005)
    b = simulate(rebuilt, t_max=2.0, dt_control=0.005)
    assert np.allclose(a["fis.u"], b["fis.u"], atol=1e-15)


# ----- error handling ---------------------------------------------------------


def test_block_construction_failure_names_the_offending_block():
    """The canvas needs to know which node to highlight, not just that a load failed."""
    from fuzzy.fis import FISSpec
    from fuzzy.membership import Variable
    from fuzzy.rules import RuleBase

    terms = ["NG", "Z", "PG"]
    fspec = FISSpec(
        inputs={"e": Variable.partition("e", -1.0, 1.0, terms)},
        output=Variable.partition("u", -1.0, 1.0, terms),
        rules=RuleBase.from_table("e", "e", terms, terms, [[t] * 3 for t in terms]),
    )
    data = fspec.to_spec()
    data["inputs"]["e"]["terms"]["NG"]["kind"] = "sigmoid"
    spec = {
        "version": 1,
        "blocks": [{"type": "FISBlock", "name": "ctrl", "params": {"fis": data}}],
        "connections": [],
    }
    with pytest.raises(SpecError) as exc:
        from_spec(spec)
    assert exc.value.block == "ctrl"
    assert "ctrl" in str(exc.value) and "sigmoid" in str(exc.value)


def test_unknown_block_type_attributes_the_block():
    with pytest.raises(SpecError) as exc:
        from_spec({"version": 1, "blocks": [{"type": "Wat", "name": "w"}]})
    assert exc.value.block == "w"


def test_unknown_block_type_lists_the_palette():
    with pytest.raises(SpecError, match="registered:"):
        from_spec({"version": 1, "blocks": [{"type": "Wat", "name": "w"}]})


def test_unsupported_version_raises():
    with pytest.raises(SpecError, match="unsupported spec version"):
        from_spec({"version": 99, "blocks": []})


def test_block_entry_missing_name_raises():
    with pytest.raises(SpecError, match="missing 'name'"):
        from_spec({"version": 1, "blocks": [{"type": "Harmonic"}]})


def test_connection_to_a_deleted_block_is_structured():
    """The commonest canvas edit: remove a block, leave its wires behind."""
    spec = {
        "version": 1,
        "blocks": [{"type": "Gain", "name": "g", "params": {"k": 1.0}}],
        "connections": [{"from": ["ghost", "y"], "to": ["g", "u"]}],
    }
    with pytest.raises(SpecError, match="unknown block 'ghost'") as exc:
        from_spec(spec)
    assert exc.value.block == "ghost"


def test_malformed_connection_raises():
    spec = {
        "version": 1,
        "blocks": [
            {"type": "Harmonic", "name": "src", "params": {}},
            {"type": "Select", "name": "s", "params": {"index": 0}},
        ],
        "connections": [{"from": ["src", "y"]}],
    }
    with pytest.raises(SpecError, match="malformed connection"):
        from_spec(spec)

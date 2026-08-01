"""Unit tests for declarative terms, variables, rule bases, and FIS specs."""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.fis import FISSpec, FISValidationError
from fuzzy.membership import (
    Term,
    TermError,
    Variable,
    left_shoulder,
    triangular,
)
from fuzzy.rules import Rule, RuleBase, RuleError

TERMS = ["NG", "NP", "Z", "PP", "PG"]
TABLE = [
    ["PG", "PG", "PG", "PP", "Z"],
    ["PG", "PP", "PP", "Z", "NP"],
    ["PG", "PP", "Z", "NP", "NG"],
    ["PP", "Z", "NP", "NP", "NG"],
    ["Z", "NP", "NG", "NG", "NG"],
]


def demo_spec() -> FISSpec:
    return FISSpec(
        inputs={
            "deslocamento": Variable.partition("deslocamento", -0.3, 0.3, TERMS),
            "velocidade": Variable.partition("velocidade", -3.0, 3.0, TERMS),
        },
        output=Variable.partition("forca", -3.0, 3.0, TERMS),
        rules=RuleBase.from_table(
            "velocidade", "deslocamento", TERMS, TERMS, TABLE
        ),
    )


# ----- Term -------------------------------------------------------------------


def test_term_matches_the_raw_membership_function():
    x = np.linspace(-1.0, 1.0, 101)
    tri = Term("triangular", (-1.0, 0.0, 1.0))
    left = Term("left_shoulder", (-1.0, 0.0))
    assert np.array_equal(tri(x), triangular(x, -1, 0, 1))
    assert np.array_equal(left(x), left_shoulder(x, -1, 0))


def test_term_rejects_unknown_kind_and_lists_known_ones():
    with pytest.raises(TermError, match="gaussian"):
        Term("wat", (0.0,))


def test_term_rejects_wrong_arity():
    with pytest.raises(TermError, match="takes 3 parameters, got 2"):
        Term("triangular", (0.0, 1.0))


def test_term_round_trips():
    t = Term("gaussian", (0.5, 2.0))
    assert Term.from_spec(t.to_spec()) == t


def test_term_spec_missing_key():
    with pytest.raises(TermError, match="missing 'params'"):
        Term.from_spec({"kind": "triangular"})


@pytest.mark.parametrize(
    ("kind", "params", "match"),
    [
        ("triangular", (1.0, 0.0, -1.0), "a <= b <= c"),
        ("triangular", (0.5, -0.5, 1.0), "a <= b <= c"),
        ("trapezoidal", (1.0, 0.5, -0.5, -1.0), "a <= b <= c <= d"),
        ("left_shoulder", (0.0, 0.0), "b > a"),
        ("left_shoulder", (1.0, 0.0), "b > a"),
        ("right_shoulder", (0.0, 0.0), "b > a"),
        ("gaussian", (0.0, 0.0), "sigma > 0"),
        ("gaussian", (0.0, -0.5), "sigma > 0"),
    ],
)
def test_term_rejects_parameters_that_violate_its_precondition(kind, params, match):
    """Dragging a breakpoint past its neighbour must fail loudly.

    A shoulder with `a == b` divides by zero and yields NaN at one input. That
    NaN then propagates into inference *and* hides from the strong-partition
    check, since every comparison against NaN is False — a corrupt controller
    that validates clean and simulates plausibly.
    """
    with pytest.raises(TermError, match=match):
        Term(kind, params)


def test_term_allows_documented_degenerate_shapes():
    """`triangular` explicitly permits a == b or b == c (one-sided shapes)."""
    Term("triangular", (0.0, 0.0, 1.0))
    Term("triangular", (0.0, 1.0, 1.0))


def test_partition_error_reports_non_finite_as_infinite():
    """Defence in depth: a NaN membership must not slip past as 'no deviation'."""
    class Rogue:
        def __call__(self, x):
            return np.full_like(np.asarray(x, dtype=float), np.nan)

    v = Variable("v", -1.0, 1.0, {"bad": Rogue()})
    assert v.partition_error() == float("inf")


# ----- Variable ---------------------------------------------------------------


@pytest.mark.parametrize("n", [3, 5, 7, 9])
def test_partition_sums_to_one_for_any_term_count(n):
    v = Variable.partition("v", -2.0, 2.0, [f"t{i}" for i in range(n)])
    assert v.partition_error() == pytest.approx(0.0, abs=1e-12)


def test_partition_reproduces_the_hand_built_five_term_layout():
    """Matches the breakpoints exercise 2 used before terms became data.

    Compared with a tolerance, not exactly: `partition` spaces centres with
    `linspace` (`low + step*i`) where the old code used `high - quarter`, and the
    two disagree by one ulp (2.8e-17) on the `PP` breakpoint. That propagates to
    ~1e-15 in the control surface and to nothing at all in the closed loop.
    """
    v = Variable.partition("x", -0.3, 0.3, TERMS)
    assert v["NG"].kind == "left_shoulder"
    assert v["NG"].params == pytest.approx((-0.3, -0.15))
    assert v["Z"].kind == "triangular"
    assert v["Z"].params == pytest.approx((-0.15, 0.0, 0.15))
    assert v["PG"].kind == "right_shoulder"
    assert v["PG"].params == pytest.approx((0.15, 0.3))


def test_partition_needs_three_terms():
    with pytest.raises(TermError, match="at least three terms"):
        Variable.partition("v", 0.0, 1.0, ["a", "b"])


def test_partition_error_detects_a_gap():
    """A hand-edited term set that leaves a hole is caught, not silently wrong."""
    broken = Variable(
        "v", -1.0, 1.0,
        {"a": Term("left_shoulder", (-1.0, -0.5)),
         "b": Term("right_shoulder", (0.5, 1.0))},
    )
    assert broken.partition_error() > 0.9


def test_variable_unknown_term_lists_available():
    with pytest.raises(TermError, match="has: \\['NG'"):
        Variable.partition("x", -1.0, 1.0, TERMS)["nope"]


def test_variable_rejects_inverted_universe():
    with pytest.raises(TermError, match="`high` must exceed `low`"):
        Variable("v", 1.0, 0.0, {"a": Term("gaussian", (0.0, 1.0))})


def test_variable_round_trips():
    v = Variable.partition("x", -0.3, 0.3, TERMS)
    assert Variable.from_spec(v.to_spec()) == v


# ----- Rule and RuleBase ------------------------------------------------------


def test_from_table_builds_the_full_cross_product():
    rb = RuleBase.from_table("velocidade", "deslocamento", TERMS, TERMS, TABLE)
    assert len(rb) == 25
    assert rb.coverage({"deslocamento": TERMS, "velocidade": TERMS}) == 1.0


def test_table_round_trips():
    rb = RuleBase.from_table("velocidade", "deslocamento", TERMS, TERMS, TABLE)
    assert rb.as_table("velocidade", "deslocamento", TERMS, TERMS) == TABLE


def test_as_table_marks_missing_cells_as_none():
    rb = RuleBase([Rule({"v": "NG", "x": "NG"}, "PG")])
    grid = rb.as_table("v", "x", ["NG", "Z"], ["NG", "Z"])
    assert grid[0][0] == "PG"
    assert grid[0][1] is None and grid[1][0] is None


def test_from_table_rejects_a_ragged_table():
    with pytest.raises(RuleError, match="row 0 has 2 entries"):
        RuleBase.from_table("v", "x", ["a"], ["p", "q", "r"], [["1", "2"]])


def test_from_table_rejects_wrong_row_count():
    with pytest.raises(RuleError, match="1 rows but 2 row terms"):
        RuleBase.from_table("v", "x", ["a", "b"], ["p"], [["1"]])


def test_validate_reports_every_problem_not_just_the_first():
    rb = RuleBase([
        Rule({"nope": "NG"}, "PG"),
        Rule({"v": "WAT"}, "PG"),
        Rule({"v": "NG"}, "BAD"),
    ])
    problems = rb.validate({"v": ["NG"]}, ["PG"])
    assert len(problems) == 3
    assert any("unknown input variable" in p for p in problems)
    assert any("no term 'WAT'" in p for p in problems)
    assert any("unknown consequent term 'BAD'" in p for p in problems)


def test_coverage_below_one_for_an_incomplete_base():
    rb = RuleBase([Rule({"v": "NG", "x": "NG"}, "PG")])
    assert rb.coverage({"v": ["NG", "Z"], "x": ["NG", "Z"]}) == 0.25


def test_rule_describe():
    r = Rule({"deslocamento": "NG", "velocidade": "PG"}, "Z")
    assert r.describe("forca") == (
        "IF deslocamento IS NG AND velocidade IS PG THEN forca IS Z"
    )


def test_rule_base_round_trips():
    rb = RuleBase.from_table("velocidade", "deslocamento", TERMS, TERMS, TABLE)
    assert RuleBase.from_spec(rb.to_spec()).rules == rb.rules


def test_rule_unpacks_like_the_tuple_mamdanifis_expects():
    """MamdaniFIS iterates `for antecedents, consequent in rules`."""
    antecedents, consequent = Rule({"v": "NG"}, "PG")
    assert antecedents == {"v": "NG"} and consequent == "PG"


# ----- FISSpec ----------------------------------------------------------------


def test_spec_validates_clean():
    assert demo_spec().validate() == []


def test_spec_builds_a_working_fis():
    fis = demo_spec().build()
    u = fis.evaluate({"deslocamento": -0.3, "velocidade": -3.0})
    assert u > 0  # both inputs NG -> force PG, pushing back


def test_build_strict_raises_on_a_bad_rule():
    spec = demo_spec()
    spec.rules.rules.append(Rule({"deslocamento": "NOPE"}, "PG"))
    with pytest.raises(FISValidationError, match="no term 'NOPE'"):
        spec.build()


def test_validation_error_carries_every_problem_as_data():
    """An editor consumes `.problems`; it should not have to parse the message."""
    spec = demo_spec()
    spec.rules.rules.append(Rule({"deslocamento": "NOPE"}, "ALSO_NOPE"))
    with pytest.raises(FISValidationError) as exc:
        spec.build()
    assert len(exc.value.problems) == 2
    assert any("no term 'NOPE'" in p for p in exc.value.problems)
    assert any("ALSO_NOPE" in p for p in exc.value.problems)
    # the summary line must stand alone: a canvas may show only the first line
    assert str(exc.value).splitlines()[0] == "invalid rule base: 2 problems"


def test_build_non_strict_skips_validation():
    spec = demo_spec()
    spec.rules.rules.append(Rule({"deslocamento": "NOPE"}, "PG"))
    spec.build(strict=False)  # must not raise


def test_validate_flags_incomplete_coverage():
    spec = demo_spec()
    spec.rules = RuleBase(spec.rules.rules[:5])
    assert any("covers 20%" in p for p in spec.validate())


def test_validate_flags_a_broken_partition():
    spec = demo_spec()
    spec.inputs["deslocamento"] = Variable(
        "deslocamento", -0.3, 0.3,
        {"NG": Term("left_shoulder", (-0.3, -0.2)),
         "NP": Term("triangular", (-0.3, -0.15, 0.0)),
         "Z": Term("triangular", (-0.15, 0.0, 0.15)),
         "PP": Term("triangular", (0.0, 0.15, 0.3)),
         "PG": Term("right_shoulder", (0.15, 0.3))},
    )
    assert any("not a strong partition" in p for p in spec.validate())


def test_spec_round_trip_reproduces_identical_inference():
    original = demo_spec()
    rebuilt = FISSpec.from_spec(original.to_spec())
    a, b = original.build(), rebuilt.build()
    for x in np.linspace(-0.3, 0.3, 13):
        for v in np.linspace(-3.0, 3.0, 13):
            args = {"deslocamento": float(x), "velocidade": float(v)}
            assert a.evaluate(args) == b.evaluate(args)


def test_resolution_controls_the_output_grid():
    assert len(demo_spec().build().output_universe) == 401
    spec = demo_spec()
    spec.resolution = 101
    assert len(spec.build().output_universe) == 101


def test_every_registered_mf_kind_round_trips_and_stays_finite():
    """Each palette entry must survive spec -> JSON -> build -> evaluate.

    `trapezoidal` and `gaussian` are reachable from the editor palette but are
    used by no exercise, so nothing else exercises them.
    """
    import json

    from fuzzy.membership import MF_REGISTRY

    samples = {
        "triangular": (-1.0, 0.0, 1.0),
        "trapezoidal": (-1.0, -0.5, 0.5, 1.0),
        "left_shoulder": (-1.0, 0.0),
        "right_shoulder": (0.0, 1.0),
        "gaussian": (0.0, 0.4),
    }
    assert set(samples) == set(MF_REGISTRY), "a palette entry is untested"

    for kind, params in samples.items():
        spec = FISSpec(
            inputs={
                "e": Variable(
                    "e", -1.0, 1.0,
                    {"LO": Term("left_shoulder", (-1.0, 0.0)),
                     "MID": Term(kind, params),
                     "HI": Term("right_shoulder", (0.0, 1.0))},
                )
            },
            output=Variable.partition("u", -1.0, 1.0, ["N", "Z", "P"]),
            rules=RuleBase([Rule({"e": "LO"}, "P"), Rule({"e": "MID"}, "Z"),
                            Rule({"e": "HI"}, "N")]),
        )
        rebuilt = FISSpec.from_spec(json.loads(json.dumps(spec.to_spec())))
        a, b = spec.build(), rebuilt.build()
        for x in np.linspace(-1.0, 1.0, 21):
            va = a.evaluate({"e": float(x)})
            assert va == b.evaluate({"e": float(x)}), kind
            assert np.isfinite(va), kind


def test_randomised_controllers_round_trip_exactly():
    """Seeded fuzz over term kinds and counts — the editor will produce variety."""
    import json
    import random

    rng = random.Random(0)
    arity = {"triangular": 3, "trapezoidal": 4, "left_shoulder": 2,
             "right_shoulder": 2, "gaussian": 2}
    for _ in range(50):
        kind = rng.choice(list(arity))
        if kind == "gaussian":
            params = (rng.uniform(-1, 1), rng.uniform(0.05, 2.0))
        else:
            params = tuple(sorted(rng.uniform(-2, 2) for _ in range(arity[kind])))
            if kind.endswith("shoulder") and params[0] == params[1]:
                continue
        names = [f"t{i}" for i in range(rng.choice([3, 4, 5, 7]))]
        base = Variable.partition("e", -2.0, 2.0, names)
        var = Variable("e", -2.0, 2.0, {**base.terms, "extra": Term(kind, params)})
        spec = FISSpec(
            inputs={"e": var},
            output=Variable.partition("u", -1.0, 1.0, ["N", "Z", "P"]),
            rules=RuleBase([
                Rule({"e": t}, rng.choice(["N", "Z", "P"]))
                for t in [*names, "extra"]
            ]),
        )
        rebuilt = FISSpec.from_spec(json.loads(json.dumps(spec.to_spec())))
        a, b = spec.build(), rebuilt.build()
        for x in np.linspace(-2.0, 2.0, 9):
            va = a.evaluate({"e": float(x)})
            assert va == b.evaluate({"e": float(x)})
            assert np.isfinite(va)

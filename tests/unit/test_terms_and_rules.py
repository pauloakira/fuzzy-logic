"""Unit tests for declarative terms, variables, rule bases, and FIS specs."""

from __future__ import annotations

import numpy as np
import pytest

from fuzzy.fis import FISSpec
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
    with pytest.raises(ValueError, match="no term 'NOPE'"):
        spec.build()


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

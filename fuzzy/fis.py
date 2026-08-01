"""Fuzzy inference systems: Mamdani (currently), Sugeno and Tsukamoto to come."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from fuzzy.defuzz import centroid
from fuzzy.membership import Variable
from fuzzy.rules import RuleBase

MembershipFn = Callable[[ArrayLike], NDArray[np.float64]]
Antecedents = Mapping[str, str]
Rule = tuple[Antecedents, str]


@dataclass
class MamdaniFIS:
    """Mamdani fuzzy inference system.

    Uses `min` t-norm for AND across antecedents, `max` aggregation across
    rules, Mamdani implication (clip the consequent MF at the rule's firing
    strength), and centroid defuzzification on a fixed output universe grid.

    Attributes:
        inputs: {input_var: {term_name: mf_callable}}
        output_terms: {term_name: mf_callable} for the single output variable
        output_universe: 1D array — discretized output universe of discourse
        rules: list of (antecedents, consequent_term)
            antecedents: {input_var: term_name}
            consequent_term: name of an output term
    """

    inputs: Mapping[str, Mapping[str, MembershipFn]]
    output_terms: Mapping[str, MembershipFn]
    output_universe: np.ndarray
    rules: Sequence[Rule]

    def fuzzify(self, values: Mapping[str, float]) -> dict[str, dict[str, float]]:
        return {
            var: {term: float(mf(values[var])) for term, mf in terms.items()}
            for var, terms in self.inputs.items()
        }

    def evaluate(self, values: Mapping[str, float]) -> float:
        crisp, _, _, _ = self.evaluate_full(values)
        return crisp

    def evaluate_full(
        self, values: Mapping[str, float]
    ) -> tuple[
        float,
        NDArray[np.float64],
        dict[str, dict[str, float]],
        list[float],
    ]:
        """Run inference and return (crisp, aggregated_mu, fuzzified, strengths)."""
        memberships = self.fuzzify(values)
        aggregated = np.zeros_like(self.output_universe, dtype=float)
        strengths: list[float] = []
        for antecedents, consequent in self.rules:
            strength = min(
                memberships[var][term] for var, term in antecedents.items()
            )
            cons_mu = self.output_terms[consequent](self.output_universe)
            clipped = np.minimum(strength, cons_mu)
            aggregated = np.maximum(aggregated, clipped)
            strengths.append(float(strength))
        crisp = centroid(self.output_universe, aggregated)
        return crisp, aggregated, memberships, strengths


class FISValidationError(ValueError):
    """A controller failed validation. `.problems` holds every problem found.

    Carried as data so an editor can highlight all offending rules at once
    rather than parsing them back out of the message.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        n = len(self.problems)
        super().__init__(
            f"invalid rule base: {n} problem{'s' if n != 1 else ''}\n  "
            + "\n  ".join(self.problems)
        )


@dataclass
class FISSpec:
    """A complete Mamdani controller described as data.

    `MamdaniFIS` holds membership *callables*, which is right for inference but
    cannot be saved, inspected, or edited. `FISSpec` holds `Variable`s and a
    `RuleBase` instead, and `build()` turns it into a `MamdaniFIS`. Because
    `Term` is callable and `Rule` is a `(antecedents, consequent)` NamedTuple,
    the built FIS is indistinguishable from a hand-wired one.
    """

    inputs: Mapping[str, Variable]
    output: Variable
    rules: RuleBase
    resolution: int = 401

    def term_names(self) -> dict[str, list[str]]:
        return {name: list(var.terms) for name, var in self.inputs.items()}

    def validate(self) -> list[str]:
        """Problems with this controller; empty means valid.

        Covers rule references, rule-base completeness, and whether each variable
        is a strong partition — the three things a hand-edited controller most
        often gets wrong.
        """
        problems = self.rules.validate(self.term_names(), list(self.output.terms))
        covered = self.rules.coverage(self.term_names())
        if covered < 1.0:
            problems.append(
                f"rule base covers {covered:.0%} of input term combinations; "
                f"uncovered inputs fall back to the universe midpoint"
            )
        for var in (*self.inputs.values(), self.output):
            err = var.partition_error()
            if err > 1e-9:
                problems.append(
                    f"{var.name!r} is not a strong partition "
                    f"(memberships deviate from 1 by up to {err:.3f})"
                )
        return problems

    def build(self, strict: bool = True) -> MamdaniFIS:
        """Instantiate the inference system. `strict` raises on any problem."""
        if strict:
            problems = self.rules.validate(
                self.term_names(), list(self.output.terms)
            )
            if problems:
                raise FISValidationError(problems)
        return MamdaniFIS(
            inputs={n: dict(v.terms) for n, v in self.inputs.items()},
            output_terms=dict(self.output.terms),
            output_universe=self.output.universe(self.resolution),
            rules=list(self.rules),
        )

    def to_spec(self) -> dict[str, Any]:
        return {
            "inputs": {n: v.to_spec() for n, v in self.inputs.items()},
            "output": self.output.to_spec(),
            "rules": self.rules.to_spec(),
            "resolution": self.resolution,
        }

    @classmethod
    def from_spec(cls, data: Mapping[str, Any]) -> FISSpec:
        return cls(
            inputs={
                n: Variable.from_spec(v) for n, v in data["inputs"].items()
            },
            output=Variable.from_spec(data["output"]),
            rules=RuleBase.from_spec(data["rules"]),
            resolution=int(data.get("resolution", 401)),
        )

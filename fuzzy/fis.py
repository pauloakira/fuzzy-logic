"""Fuzzy inference systems: Mamdani (currently), Sugeno and Tsukamoto to come."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np
from numpy.typing import ArrayLike, NDArray

from fuzzy.defuzz import centroid

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

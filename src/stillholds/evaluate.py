"""
evaluate.py — the algorithm that decides whether a conclusion "still holds".

Pure layer (operates on two Effects, no I/O). Fully implemented alongside
effect.py, because it is the defensible core of the project and can be tested
entirely with synthetic Effects, without real data.

It is a transparent, configurable heuristic over confidence intervals, NOT a
formal statistical equivalence test. That honesty is deliberate.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .effect import Effect


class Verdict(str, Enum):
    HOLDS = "HOLDS"
    REGRESSED = "REGRESSED"
    IMPROVED = "IMPROVED"


@dataclass(frozen=True)
class Tolerances:
    max_shrink: float = 0.50        # regress if the effect loses >50% of its magnitude
    max_width_ratio: float = 2.0    # regress if the CI widens >2x
    improve_margin: float = 0.20    # IMPROVED if it grows >20% without losing precision


@dataclass(frozen=True)
class Evaluation:
    verdict: Verdict
    reason: str


def _relative_shrink(b: Effect, c: Effect) -> float:
    if b.value == 0:
        return 0.0
    return max(0.0, 1.0 - (abs(c.value) / abs(b.value)))


def _strictly_worse(b: Effect, c: Effect) -> bool:
    if b.resolved_direction == "increase":
        return c.ci[1] < b.ci[0]
    return c.ci[0] > b.ci[1]


def _materially_stronger(b: Effect, c: Effect, cfg: Tolerances) -> bool:
    stronger = abs(c.value) >= (1 + cfg.improve_margin) * abs(b.value)
    tighter = c.ci_width <= b.ci_width
    return stronger and tighter and not c.crosses_zero


def evaluate(
    baseline: Effect,
    current: Effect,
    cfg: Tolerances | None = None,
    *,
    precision_guard: bool = True,
) -> Evaluation:
    """
    Compara `current` contra `baseline`. Devuelve el primer veredicto que aplica.

    precision_guard=False disables Test 3 (precision stability). Used in the
    counterfactual mode, where only whether the VALUE moved matters, not whether
    precision changed (n changes by construction when mixing old/new data).
    """
    cfg = cfg or Tolerances()
    b, c = baseline, current

    # --- Test 1: direction preservation ---
    # The direction the conclusion CLAIMS is the baseline's. We check it
    # contra el SIGNO REAL del valor actual, no contra la etiqueta declarada del
    # (which inherits direction= and would not reflect a reversal).
    claimed_direction = b.resolved_direction
    actual_sign = "increase" if c.value >= 0 else "decrease"

    # 1a. sign reversal (checked first: the most qualitative failure)
    if claimed_direction != actual_sign and not c.crosses_zero:
        return Evaluation(Verdict.REGRESSED, "effect reversed direction")
    # 1b. the effect is no longer distinguishable from zero
    if not b.crosses_zero and c.crosses_zero:
        return Evaluation(Verdict.REGRESSED, "effect is no longer distinguishable from zero")

    # --- Test 3: precision stability (guard against false greens) ---
    if precision_guard and c.ci_width > cfg.max_width_ratio * b.ci_width:
        return Evaluation(
            Verdict.REGRESSED,
            f"precision collapsed: the CI widened {c.ci_width / b.ci_width:.1f}x "
            f"(n {b.n}\u2192{c.n})",
        )

    # --- Test 2: compatibilidad de magnitud ---
    shrink = _relative_shrink(b, c)
    if shrink > cfg.max_shrink:
        return Evaluation(
            Verdict.REGRESSED,
            f"magnitude dropped {shrink:.0%} vs. the baseline "
            f"({b.value:+.3f} \u2192 {c.value:+.3f})",
        )
    if _strictly_worse(b, c):
        return Evaluation(
            Verdict.REGRESSED, "confidence intervals no longer overlap (worse)"
        )

    # --- Did it materially improve? ---
    if _materially_stronger(b, c, cfg):
        return Evaluation(
            Verdict.IMPROVED,
            f"the effect strengthened ({b.value:+.3f} \u2192 {c.value:+.3f}, "
            f"CI {b.ci_width:.3f} \u2192 {c.ci_width:.3f})",
        )

    return Evaluation(Verdict.HOLDS, "within the equivalence band")

"""
Tests for the evaluate() algorithm. Pure layer -> must PASS already. Each test
isolates ONE branch of the decision tree with synthetic Effects. These tests ARE
the executable specification of what "still holds" means.
"""
import pytest

from stillholds.effect import Effect
from stillholds.evaluate import Tolerances, Verdict, evaluate


# A canonical baseline: positive effect, clearly distinct from zero.
BASE = Effect(value=0.14, ci=(0.08, 0.20), n=2104, direction="increase")


class TestHolds:
    def test_identical_holds(self):
        assert evaluate(BASE, BASE).verdict == Verdict.HOLDS

    def test_small_change_within_band_holds(self):
        # +14% -> +13%, tiny, same precision: holds
        cur = Effect(0.13, (0.07, 0.19), 2200, direction="increase")
        assert evaluate(BASE, cur).verdict == Verdict.HOLDS

    def test_more_data_tighter_ci_same_value_holds(self):
        # the demo's PR#1 case: more data, stable effect, tighter CI
        cur = Effect(0.135, (0.10, 0.17), 5900, direction="increase")
        assert evaluate(BASE, cur).verdict == Verdict.HOLDS


class TestRegressedByDirection:
    def test_effect_now_crosses_zero_regresses(self):
        # el caso PR#2 de la demo: +14% -> +1.8%, CI ahora incluye el cero
        cur = Effect(0.018, (-0.034, 0.070), 5916, direction="increase")
        ev = evaluate(BASE, cur)
        assert ev.verdict == Verdict.REGRESSED
        assert "distinguishable from zero" in ev.reason

    def test_effect_flips_sign_regresses(self):
        cur = Effect(-0.12, (-0.18, -0.06), 2000, direction="increase")
        ev = evaluate(BASE, cur)
        assert ev.verdict == Verdict.REGRESSED
        assert "reversed" in ev.reason


class TestRegressedByMagnitude:
    def test_magnitude_halved_regresses(self):
        # still positive and significant, but lost >50% of its magnitude
        cur = Effect(0.05, (0.02, 0.08), 2104, direction="increase")
        ev = evaluate(BASE, cur)
        assert ev.verdict == Verdict.REGRESSED
        assert "magnitude" in ev.reason

    def test_strictly_worse_intervals_regresses(self):
        # CI nuevo enteramente por debajo del piso del CI viejo
        cur = Effect(0.065, (0.055, 0.075), 3000, direction="increase")
        ev = evaluate(BASE, cur)
        assert ev.verdict == Verdict.REGRESSED


class TestRegressedByPrecision:
    def test_ci_blows_up_regresses(self):
        # same value, CI blew up >2x but WITHOUT crossing zero: isolates the
        # precision guard (if it crossed zero, Test 1 would win, a different thing).
        # base width = 0.12; este width = 0.28 (2.33x) y el piso sigue > 0.
        cur = Effect(0.14, (0.01, 0.29), 90, direction="increase")
        ev = evaluate(BASE, cur)
        assert ev.verdict == Verdict.REGRESSED
        assert "precision" in ev.reason

    def test_precision_guard_disabled_ignores_width(self):
        # in counterfactual mode only the value matters, not precision
        cur = Effect(0.14, (-0.02, 0.30), 90, direction="increase")
        ev = evaluate(BASE, cur, precision_guard=False)
        # without the precision guard, and value intact -> no regression by width
        assert ev.verdict != Verdict.REGRESSED or "precision" not in ev.reason


class TestImproved:
    def test_stronger_and_tighter_improves(self):
        # bigger AND more precise effect: not an alarm, it's IMPROVED
        cur = Effect(0.20, (0.16, 0.24), 4000, direction="increase")
        assert evaluate(BASE, cur).verdict == Verdict.IMPROVED

    def test_stronger_but_wider_is_not_improved(self):
        # bigger but less precise: does not qualify as a clean improvement
        cur = Effect(0.20, (0.02, 0.38), 500, direction="increase")
        assert evaluate(BASE, cur).verdict != Verdict.IMPROVED


class TestTolerancesConfigurable:
    def test_stricter_shrink_tolerance_flags_smaller_drop(self):
        cur = Effect(0.10, (0.05, 0.15), 2104, direction="increase")
        lenient = evaluate(BASE, cur, Tolerances(max_shrink=0.50))
        strict = evaluate(BASE, cur, Tolerances(max_shrink=0.20))
        assert lenient.verdict == Verdict.HOLDS
        assert strict.verdict == Verdict.REGRESSED

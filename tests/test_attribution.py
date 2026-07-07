"""
Counterfactual tests: each attribution path (CODE, DATA, INTERACTION), the
code-snapshot import, and the INCONCLUSIVE case. These tests ARE the executable
specification of the project's defensible thesis.
"""
import numpy as np
import pandas as pd
import pytest

from stillholds.attribution import (
    Attribution, Cause, attribute, import_analysis_from_snapshot,
)
from stillholds.claim import Claim
from stillholds.effect import Effect
from stillholds.evaluate import Tolerances

RNG = np.random.default_rng(12345)


def _mean_diff(events: pd.DataFrame) -> Effect:
    a = events[events.g == "A"].y.astype(float)
    b = events[events.g == "B"].y.astype(float)
    d = b.mean() - a.mean()
    se = ((a.var(ddof=1) / len(a)) + (b.var(ddof=1) / len(b))) ** 0.5
    return Effect(float(d), (float(d - 1.96 * se), float(d + 1.96 * se)),
                  int(len(events)), direction="increase", unit="absolute")


def _make(effect_size: float, n: int = 4000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    g = rng.choice(["A", "B"], n)
    y = (g == "B") * effect_size + rng.normal(0, 1, n)
    return pd.DataFrame({"g": g, "y": y})


class TestAttributionPaths:
    def test_code_change_attributed_to_code(self):
        # same data; the new code "breaks" (divides the effect by 10)
        data = {"events": _make(0.5, seed=1)}
        strong = Claim("c", _mean_diff, "")

        def weak_analysis(events):
            e = _mean_diff(events)
            return Effect(e.value / 10, (e.ci[0] / 10, e.ci[1] / 10), e.n,
                          direction="increase", unit="absolute")
        weak = Claim("c", weak_analysis, "")

        base = _mean_diff(data["events"])
        cur = weak_analysis(data["events"])
        attr = attribute(claim_name="c", baseline_effect=base, current_effect=cur,
                         new_data=data, old_data=data,
                         new_claim=weak, old_claim=strong, tolerances=Tolerances())
        assert attr.cause == Cause.CODE

    def test_data_change_attributed_to_data(self):
        # same code; new data with a near-zero effect
        old_data = {"events": _make(0.5, seed=2)}
        new_data = {"events": _make(0.03, seed=3)}
        claim = Claim("c", _mean_diff, "")
        base = _mean_diff(old_data["events"])
        cur = _mean_diff(new_data["events"])
        attr = attribute(claim_name="c", baseline_effect=base, current_effect=cur,
                         new_data=new_data, old_data=old_data,
                         new_claim=claim, old_claim=claim, tolerances=Tolerances())
        assert attr.cause == Cause.DATA

    def test_interaction_when_neither_alone_reproduces(self):
        # CLEAN, DETERMINISTIC INTERACTION. The reported effect depends on a
        # a data flag ('mode') AND a code constant at the same time:
        #   value = base_effect  si (mode=="wide" o multiplier==1.0)
        #   value = base_effect*0.1 (colapsa) SOLO si mode=="narrow" Y multiplier==0.1
        # - old data: mode="wide"     -> with any code, does not collapse.
        # - datos nuevos: mode="narrow".
        # - old code: multiplier=1.0  -> with any data, does not collapse.
        # - new code: multiplier=0.1.
        # Only new-data(narrow) + new-code(0.1) collapses -> INTERACTION.
        old_data = {"events": pd.DataFrame({"mode": ["wide"] * 100, "val": [1.0] * 100})}
        new_data = {"events": pd.DataFrame({"mode": ["narrow"] * 100, "val": [1.0] * 100})}

        def make_analysis(multiplier: float):
            def analysis(events):
                mode = events["mode"].iloc[0]
                collapse = (mode == "narrow") and (multiplier == 0.1)
                v = 0.05 * (0.1 if collapse else 1.0)
                # CI angosto y determinista alrededor de v
                return Effect(v, (v - 0.005, v + 0.005), 100,
                              direction="increase", unit="absolute")
            return analysis

        old_claim = Claim("c", make_analysis(1.0), "")   # multiplier viejo = 1.0
        new_claim = Claim("c", make_analysis(0.1), "")   # multiplier nuevo = 0.1

        base = make_analysis(1.0)(old_data["events"])     # wide + 1.0  -> 0.05
        cur = make_analysis(0.1)(new_data["events"])      # narrow + 0.1 -> 0.005 (colapsa)
        attr = attribute(claim_name="c", baseline_effect=base, current_effect=cur,
                         new_data=new_data, old_data=old_data,
                         new_claim=new_claim, old_claim=old_claim, tolerances=Tolerances())
        # new data + old code: narrow + 1.0 -> 0.05 (no collapse)
        # old data + new code: wide + 0.1   -> 0.05 (no collapse)
        # ninguno solo reproduce -> INTERACTION
        assert attr.cause == Cause.INTERACTION

    def test_inconclusive_when_a_corner_fails(self):
        data = {"events": _make(0.5, seed=6)}
        good = Claim("c", _mean_diff, "")

        def broken(events):
            raise RuntimeError("boom")
        broken_claim = Claim("c", broken, "")

        base = _mean_diff(data["events"])
        cur = _mean_diff(data["events"])
        # new code (broken) raises -> the old-data+new-code corner fails
        attr = attribute(claim_name="c", baseline_effect=base, current_effect=cur,
                         new_data=data, old_data=data,
                         new_claim=broken_claim, old_claim=good, tolerances=Tolerances())
        assert attr.cause == Cause.INCONCLUSIVE
        assert "failed to run" in attr.detail


class TestEnvWarning:
    def test_env_warning_propagates_into_attribution(self):
        data = {"events": _make(0.5, seed=7)}
        strong = Claim("c", _mean_diff, "")

        def weak(events):
            e = _mean_diff(events)
            return Effect(e.value / 10, (e.ci[0] / 10, e.ci[1] / 10), e.n,
                          direction="increase", unit="absolute")
        weak_claim = Claim("c", weak, "")
        base = _mean_diff(data["events"])
        cur = weak(data["events"])
        attr = attribute(claim_name="c", baseline_effect=base, current_effect=cur,
                         new_data=data, old_data=data,
                         new_claim=weak_claim, old_claim=strong,
                         tolerances=Tolerances(), env_warning=True)
        assert attr.env_warning is True


class TestSnapshotImport:
    def test_import_analysis_from_snapshot(self, tmp_path):
        # write an analysis module and re-import it in isolation
        code = (
            "import stillholds as sh\n"
            "@sh.claim('my_claim')\n"
            "def my_claim(events):\n"
            "    return sh.Effect(0.1, (0.05, 0.15), 100, unit='absolute')\n"
        )
        snap = tmp_path / "snap.py"
        snap.write_text(code)
        old_claim = import_analysis_from_snapshot(snap, "my_claim")
        assert old_claim.name == "my_claim"
        # and the global registry was not contaminated with 'my_claim'
        from stillholds.claim import get_registry
        assert "my_claim" not in get_registry()

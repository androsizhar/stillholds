"""Tests del reporting (texto puro)."""
from stillholds.attribution import Attribution, Cause
from stillholds.effect import Effect
from stillholds.evaluate import Evaluation, Verdict
from stillholds.report import (
    fmt_effect, render_holds, render_regressed, render_attribution_text,
)

BASE = Effect(0.0477, (0.0265, 0.0689), 3811, direction="increase", unit="absolute", label="pp")
CUR_HOLD = Effect(0.056, (0.039, 0.073), 5828, direction="increase", unit="absolute", label="pp")
CUR_REG = Effect(0.0205, (0.006, 0.035), 7216, direction="increase", unit="absolute", label="pp")


class TestFormat:
    def test_pp_label_scales_to_points(self):
        assert "+4.77pp" in fmt_effect(BASE)

    def test_relative_scales_to_percent(self):
        e = Effect(0.14, (0.08, 0.20), 100, unit="relative")
        assert "+14.0%" in fmt_effect(e)


class TestHolds:
    def test_holds_mentions_claim_and_holds(self):
        out = render_holds("ab", BASE, CUR_HOLD, Evaluation(Verdict.HOLDS, "dentro de la banda"))
        assert "ab" in out and "still holds" in out.lower() and "❌" not in out

    def test_improved_reads_as_improvement(self):
        strong = Effect(0.09, (0.07, 0.11), 6000, direction="increase", unit="absolute", label="pp")
        out = render_holds("ab", BASE, strong, Evaluation(Verdict.IMPROVED, "stronger"))
        assert "improved" in out.lower()


class TestRegressed:
    def test_regressed_has_reason_and_table(self):
        out = render_regressed("ab", BASE, CUR_REG, Evaluation(Verdict.REGRESSED, "dropped 57%"))
        assert "regression" in out.lower() and "dropped 57%" in out and "Baseline" in out

    def test_code_attribution_named(self):
        attr = Attribution(Cause.CODE, BASE, CUR_REG, env_warning=False)
        out = render_regressed("ab", BASE, CUR_REG, Evaluation(Verdict.REGRESSED, "x"), attribution=attr)
        assert "analysis file" in out.lower()

    def test_attribution_states_file_only_scope(self):
        # the report must be honest that it snapshots the analysis file only
        attr = Attribution(Cause.CODE, BASE, CUR_REG, env_warning=False)
        out = render_regressed("ab", BASE, CUR_REG, Evaluation(Verdict.REGRESSED, "x"), attribution=attr)
        assert "analysis file only" in out.lower()

    def test_env_warning_surfaces(self):
        attr = Attribution(Cause.CODE, BASE, CUR_REG, env_warning=True)
        out = render_regressed("ab", BASE, CUR_REG, Evaluation(Verdict.REGRESSED, "x"), attribution=attr)
        assert "environment" in out.lower()

    def test_interaction_text(self):
        attr = Attribution(Cause.INTERACTION, BASE, CUR_REG, env_warning=False)
        txt = render_attribution_text("ab", BASE, CUR_REG, Evaluation(Verdict.REGRESSED, "x"), attr)
        assert "INTERACTION" in txt.upper()

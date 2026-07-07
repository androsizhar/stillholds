"""
Tests for the atomic unit Effect. Pure layer -> these tests must PASS already
(not stubs). They define the validation contract and invariants.
"""
import pytest

from stillholds.effect import Effect


class TestEffectValidation:
    def test_valid_effect_constructs(self):
        e = Effect(value=0.14, ci=(0.08, 0.20), n=2104)
        assert e.value == 0.14

    def test_ci_low_greater_than_high_rejected(self):
        with pytest.raises(ValueError, match="malformed CI"):
            Effect(value=0.14, ci=(0.20, 0.08), n=100)

    def test_value_outside_own_ci_rejected(self):
        # the most common and most poisonous error: a miscalculated CI
        with pytest.raises(ValueError, match="outside its own CI"):
            Effect(value=0.50, ci=(0.08, 0.20), n=100)

    def test_nonpositive_n_rejected(self):
        with pytest.raises(ValueError, match="n must be positive"):
            Effect(value=0.14, ci=(0.08, 0.20), n=0)

    def test_bad_direction_rejected(self):
        with pytest.raises(ValueError, match="direction"):
            Effect(value=0.14, ci=(0.08, 0.20), n=100, direction="up")

    def test_bad_unit_rejected(self):
        with pytest.raises(ValueError, match="unit"):
            Effect(value=0.14, ci=(0.08, 0.20), n=100, unit="percent")


class TestEffectProperties:
    def test_ci_width(self):
        assert Effect(0.14, (0.08, 0.20), 100).ci_width == pytest.approx(0.12)

    def test_resolved_direction_auto_positive(self):
        assert Effect(0.14, (0.08, 0.20), 100).resolved_direction == "increase"

    def test_resolved_direction_auto_negative(self):
        assert Effect(-0.14, (-0.20, -0.08), 100).resolved_direction == "decrease"

    def test_resolved_direction_explicit_overrides(self):
        e = Effect(0.14, (0.08, 0.20), 100, direction="decrease")
        assert e.resolved_direction == "decrease"

    def test_crosses_zero_true(self):
        assert Effect(0.02, (-0.03, 0.07), 100).crosses_zero is True

    def test_crosses_zero_false(self):
        assert Effect(0.14, (0.08, 0.20), 100).crosses_zero is False


class TestEffectSerialization:
    def test_roundtrip(self):
        e = Effect(0.032, (0.018, 0.046), 8400, direction="increase", unit="absolute",
                   label="B-A")
        assert Effect.from_dict(e.to_dict()) == e

    def test_to_dict_ci_is_list(self):
        # JSON no tiene tuplas; el dict serializable debe usar lista
        assert isinstance(Effect(0.14, (0.08, 0.20), 100).to_dict()["ci"], list)

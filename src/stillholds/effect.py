"""
effect.py — the atomic unit of StillHolds.

An Effect is a scalar effect size WITH quantifiable uncertainty. Uncertainty is
mandatory: without it there is no honest way to tell noise from a regression.
This is the pure layer of the system (no I/O, no pandas): that's why it is fully
implemented and thoroughly tested from day one.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class Effect:
    value: float
    ci: tuple[float, float]
    n: int
    ci_level: float = 0.95
    direction: str = "auto"        # "increase" | "decrease" | "auto"
    unit: str = "relative"         # "relative" | "absolute"
    label: str | None = None

    def __post_init__(self) -> None:
        lo, hi = self.ci
        if lo > hi:
            raise ValueError(f"malformed CI: low ({lo}) > high ({hi})")
        if not (lo <= self.value <= hi):
            raise ValueError(
                f"value ({self.value}) falls outside its own CI {self.ci}; "
                "the CI was probably computed incorrectly"
            )
        if self.n <= 0:
            raise ValueError(f"n must be positive, got {self.n}")
        if self.direction not in ("increase", "decrease", "auto"):
            raise ValueError(f"invalid direction: {self.direction!r}")
        if self.unit not in ("relative", "absolute"):
            raise ValueError(f"invalid unit: {self.unit!r}")

    @property
    def ci_width(self) -> float:
        return self.ci[1] - self.ci[0]

    @property
    def resolved_direction(self) -> str:
        if self.direction != "auto":
            return self.direction
        return "increase" if self.value >= 0 else "decrease"

    @property
    def crosses_zero(self) -> bool:
        return self.ci[0] <= 0 <= self.ci[1]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["ci"] = list(self.ci)  # JSON no tiene tuplas
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Effect":
        return cls(
            value=d["value"],
            ci=tuple(d["ci"]),
            n=d["n"],
            ci_level=d.get("ci_level", 0.95),
            direction=d.get("direction", "auto"),
            unit=d.get("unit", "relative"),
            label=d.get("label"),
        )

"""
StillHolds — CI for analytical claims.

Register an analytical conclusion, store a reproducible baseline, and on every
change verify whether the conclusion STILL holds within a reasonable band of
uncertainty. If not, isolate — by counterfactual re-run — whether the change
came from the data, the code, or their interaction.

    from stillholds import claim, Effect
"""
from __future__ import annotations

from .claim import claim
from .effect import Effect
from .evaluate import Evaluation, Tolerances, Verdict, evaluate

__version__ = "0.1.1"

__all__ = [
    "claim", "Effect", "evaluate", "Evaluation", "Verdict", "Tolerances",
]

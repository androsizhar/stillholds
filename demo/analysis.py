"""
A/B test demo for StillHolds.

The claim: variant B increases the signup rate relative to variant A.
The marked line is the one PR#2 will break (cohort filter change).
"""
import pandas as pd
from scipy.stats import norm

import stillholds as sh


@sh.claim("ab_test_signup_lift")
def ab_test_signup_lift(events: pd.DataFrame) -> sh.Effect:
    # NOTA: recibimos `events` como argumento para que StillHolds controle
    # which data it injects into the counterfactual (old vs new data).
    cohort = events[events.is_active == True]        # <-- PR#2 changes this line

    a = cohort[cohort.variant == "A"].signed_up.astype(float)
    b = cohort[cohort.variant == "B"].signed_up.astype(float)

    diff = b.mean() - a.mean()
    se = ((a.var(ddof=1) / len(a)) + (b.var(ddof=1) / len(b))) ** 0.5
    z = norm.ppf(0.975)

    return sh.Effect(
        value=float(diff),
        ci=(float(diff - z * se), float(diff + z * se)),
        n=int(len(cohort)),
        direction="increase",
        unit="absolute",
        label="diferencia de tasa de registro B - A (puntos)",
    )

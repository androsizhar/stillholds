# StillHolds

[![PyPI version](https://img.shields.io/pypi/v/stillholds.svg)](https://pypi.org/project/stillholds/)
[![Python](https://img.shields.io/pypi/pyversions/stillholds.svg)](https://pypi.org/project/stillholds/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**CI for analytical claims.** Does your conclusion *still hold* after the data,
the code, or the config changed?

StillHolds doesn't check that your CSV is clean (Great Expectations and dbt
tests already do that). It checks that the **claim** — "variant B improves
signup", "the campaign lifted sales in the North" — still has evidence
comparable to when you approved it, with a **semantic verdict** (holds /
improved / regressed) instead of a brittle threshold assert. And when a
regression is isolable, it runs a **counterfactual** to point at data vs. the
analysis file — a hint backed by re-execution, not a `git diff`.

> Designed for **deterministic analyses on file-scoped code**. Outside that
> envelope (unseeded randomness, logic spread across imported modules) verdicts
> and attribution can mislead — see [Limitations](#limitations-v01-honest).

```python
import stillholds as sh
import pandas as pd
from scipy.stats import norm

@sh.claim("ab_test_signup_lift")
def ab_test_signup_lift(events: pd.DataFrame) -> sh.Effect:
    cohort = events[events.is_active == True]
    a = cohort[cohort.variant == "A"].signed_up.astype(float)
    b = cohort[cohort.variant == "B"].signed_up.astype(float)
    diff = b.mean() - a.mean()
    se = ((a.var() / len(a)) + (b.var() / len(b))) ** 0.5
    z = norm.ppf(0.975)
    return sh.Effect(value=diff, ci=(diff - z*se, diff + z*se),
                     n=len(cohort), unit="absolute")
```

```
stillholds approve    # snapshot data + code, store the baseline
stillholds check      # compare; exit 1 if the claim regressed (for CI)
stillholds explain    # if it regressed, run the counterfactual and attribute the cause
stillholds list       # verdict per claim
```

## Why this isn't just a pytest assertion

An `assert lift > 0.10` tells you a number crossed a threshold. That's brittle
(why 0.10?) and blind to uncertainty. StillHolds does two things an assert can't:

1. **Semantic, not textual, comparison.** It doesn't ask "did the number
   change?" but "is the effect still in the same direction, of comparable
   magnitude, without precision collapsing?". +13.1pp → +15.1pp with more data
   is *not* a regression (it's an improvement); +13.1pp → +5.3pp is.

2. **Executable counterfactual attribution (when isolable).** When something
   regresses, it re-runs the *snapshotted analysis file* under controlled
   conditions (old data + new file, new data + old file) and measures which one
   reproduces the regression — a hint distinguishing "the data changed" from
   "the analysis file changed", backed by re-execution rather than temporal
   correlation. It says INCONCLUSIVE when a corner can't run, and (by design)
   only snapshots the analysis file, so logic in imported modules isn't isolated
   — treat attribution as a strong hint, not proof.

## PR comments (real demo output)

When the conclusion holds (more data arrived, the effect is stable):

> ###  `ab_test_signup_lift` — still holds
> Inputs changed, but the claim stays within the accepted band.
>
> | | Baseline | Current |
> |---|---|---|
> | Effect | +13.06pp (95% CI [+9.80pp, +16.33pp], n=2,441) | +15.12pp (95% CI [+13.13pp, +17.11pp], n=6,376) |

When it regresses (someone changed the cohort filter, data identical):

> ###  `ab_test_signup_lift` — insight regression detected
>
> | | Baseline | Current |
> |---|---|---|
> | Effect | +13.06pp (95% CI [+9.80pp, +16.33pp], n=2,441) | +5.25pp (95% CI [+3.57pp, +6.94pp], n=5,845) |
>
> **Why:** magnitude dropped 60% vs. the baseline
>
> **Attributed cause (by counterfactual re-run):**
>  Analysis **code** changed — data unchanged (verified by re-running the old code on the new data).

## Install

```bash
pip install stillholds
# or, from a clone: pip install -e .
```

Requires Python ≥ 3.10 and pandas. `scipy` is only needed by the demo analysis,
not by StillHolds itself.

## Quickstart

Three files: your analysis, a config, and your data.

```python
# analysis.py
import pandas as pd
from scipy.stats import norm
import stillholds as sh

@sh.claim("conversion_lift")
def conversion_lift(events: pd.DataFrame) -> sh.Effect:
    a = events[events.variant == "A"].converted.astype(float)
    b = events[events.variant == "B"].converted.astype(float)
    diff = b.mean() - a.mean()
    se = ((a.var(ddof=1)/len(a)) + (b.var(ddof=1)/len(b))) ** 0.5
    z = norm.ppf(0.975)
    return sh.Effect(float(diff), (float(diff-z*se), float(diff+z*se)),
                     int(len(events)), unit="absolute", label="pp")
```

```toml
# stillholds.toml
analysis_module = "analysis"

[data]
events = "events.csv"

[tolerances]              # optional; these are the defaults
max_shrink = 0.50         # regress if the effect loses >50% of its magnitude
max_width_ratio = 2.0     # regress if the CI widens >2x (precision collapse)
improve_margin = 0.20     # IMPROVED if it grows >20% without losing precision
```

```bash
stillholds approve    # baseline
stillholds check      # -> HOLDS (exit 0)
```

StillHolds works with or without git. If the project is a git repo, the code
snapshot is tagged with the current commit (better traceability); if not, it is
stored under `nogit` and everything else works the same.

## Try the demo

```bash
cd demo
stillholds approve                                       # baseline: +13pp
cp events_more_data.csv events.csv && stillholds check   # PR#1 -> HOLDS (exit 0)
git checkout events.csv                                  # restore
# PR#2: change is_active to is_registered in analysis.py, then:
stillholds check                                         # -> REGRESSED (exit 1)
stillholds explain ab_test_signup_lift                   # -> cause: CODE
```

## GitHub Actions

`demo/.github/workflows/stillholds.yml` runs `check` on every PR, and when a
claim regresses it runs `explain` and posts the verdict + attribution as a PR
comment (failing the job so the regression is visible).

## How it works

- **Effect** — the atomic unit: a scalar effect size with its confidence
  interval and n. Uncertainty is mandatory; without it there's no honest way to
  tell noise from a real regression.
- **Baseline** — stores the effect plus a content-hash and a recoverable
  snapshot of both the input data and the analysis source. The hash *detects*
  change; the snapshot makes the *counterfactual* possible.
- **evaluate** — a transparent, configurable heuristic over intervals with three
  tests (direction, magnitude, precision) yielding HOLDS / IMPROVED / REGRESSED.
- **attribute** — on regression, re-imports the code snapshot and runs the four
  corners (old/new data × old/new code) to isolate CODE / DATA / INTERACTION.

## Exit codes

| code | meaning |
|---|---|
| 0 | all good (HOLDS / IMPROVED) |
| 1 | at least one claim REGRESSED |
| 2 | usage error (unknown claim, missing baseline for a requested claim) |
| 3 | nothing to check (no claim has a baseline yet) |
| 4 | configuration or analysis-execution error |

## Tests

```bash
pip install -e ".[dev]"
pytest                     # 54 tests: pure layer, persistence, counterfactual, CLI e2e
```

## Limitations (v0.1, honest)

StillHolds is designed for **deterministic analyses on file-scoped code**. Inside
that envelope it's reliable; outside it, the failure modes below are real, so
they're stated up front rather than discovered in production.

- **Deterministic analyses only.** A claim must return the same `Effect` for the
  same code and data. If your analysis uses unseeded randomness (bootstrap,
  sampling, `train_test_split`, some parallel reductions), the baseline captures
  one random realization and later checks compare noise against noise. The
  practical consequence: **phantom regressions** (a REGRESSED verdict when
  nothing changed) and **unreliable attribution**. `approve` runs your claim
  twice and prints a loud warning if it detects this — seed your randomness
  (e.g. `np.random.default_rng(SEED)`) to make the baseline meaningful.
- **Attribution snapshots the analysis *file*, not its imports.** The
  counterfactual copies the file where the `@claim` function lives. If your
  logic also lives in imported project modules (`from helpers import ...`),
  changes there are **not** isolated: the "old" re-run imports the *current*
  helper, so a code change in a helper can be mis-attributed (often as
  "BOTH independently"). Keep the analysis self-contained, or read the
  attribution as a hint, not proof. The PR/terminal report states this scope
  inline.
- **The data hash is row-order sensitive.** The content hash changes if rows are
  reordered. If you read from a source without a stable `ORDER BY` (a database
  query, a non-deterministic `groupby`), the same logical dataset can hash
  differently and be reported as "data changed" (and attributed to DATA). Sort
  your inputs deterministically before the claim if order is not meaningful.
- Datasets must fit in the CI runner (snapshotted whole, as CSV + dtypes).
- A claim is a single scalar with uncertainty — no tables, distributions, or plots.
- "still holds" is a transparent, configurable heuristic over intervals, **not**
  a formal statistical equivalence test.
- Attribution assumes an equivalent environment; if key packages change it warns
  but does not isolate the environment as a separate cause.

## Roadmap

- Three-way counterfactual: isolate config too, not only data vs. code.
- Real environment isolation (each corner in its own venv).
- Optional parquet snapshots (`pip install stillholds[parquet]`) for large data.
- From "data or code?" toward sensitivity analysis over analytical decisions
  (multiverse territory, applied to a single versioned conclusion in CI).

## License

MIT — see [LICENSE](LICENSE).

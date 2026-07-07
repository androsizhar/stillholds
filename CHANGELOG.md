# Changelog

All notable changes to StillHolds are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.1.0] — 2026-07-06

First public release. CI for analytical claims.

### Added
- `@sh.claim` decorator to register an analytical conclusion that returns an
  `Effect` (value + confidence interval + n).
- `stillholds approve` — snapshots the data (content-hashed, deduplicated) and
  the analysis source (per commit), and stores a reproducible baseline.
- `stillholds check` — semantic comparison against the baseline with a
  three-way verdict (HOLDS / IMPROVED / REGRESSED). Exit 1 on regression for CI.
- `stillholds explain` — counterfactual attribution: re-runs the four corners
  (old/new data × old/new code) to isolate whether a regression came from the
  DATA, the CODE, or their INTERACTION.
- `stillholds list` — current verdict per claim.
- GitHub Action workflow that comments the verdict (and attribution) on PRs.
- A/B test demo with two scenarios: more data (holds) and a broken cohort
  filter (regresses, attributed to code).

### Known limitations (v0.1)
- **Deterministic analyses only.** Unseeded randomness makes the baseline a
  random realization, causing phantom regressions and unreliable attribution.
  `approve` runs the claim twice and warns if it looks non-deterministic.
- **Attribution snapshots the analysis file only**, not imported project
  modules; changes in helpers can be mis-attributed. The report states this scope.
- **The data hash is row-order sensitive**; sort inputs deterministically if row
  order is not meaningful.
- Datasets must fit in the CI runner (snapshotted whole, as CSV + dtypes).
- A claim is a single scalar with uncertainty — no tables, distributions, or plots.
- The "still holds" comparison is a transparent, configurable heuristic over
  intervals, not a formal statistical equivalence test.
- Attribution assumes an equivalent environment; if key packages change, it
  warns but does not isolate the environment as a separate cause.

# StillHolds — v0.1 (release-ready)

CI for analytical claims. Checks that a **conclusion still holds** after data,
code, or config changes, and if not, **isolates the cause** by counterfactual
re-run.

## Status: complete, polished, English-consistent, publishable. 54 tests green. 0 stubs.

| Module | Responsibility |
|---|---|
| effect.py | atomic unit Effect (pure layer) |
| evaluate.py | HOLDS/REGRESSED/IMPROVED algorithm (pure) |
| report.py | terminal output + PR markdown |
| provenance.py | git, environment, environment guard |
| config.py | stillholds.toml loader |
| claim.py | @claim decorator, discovery, runner |
| baseline.py | baseline JSON + data/code snapshots |
| attribution.py | 4-corner counterfactual |
| cli.py | approve / check / explain / list |

## Public API (candidate for freeze)

- `stillholds.claim(name)` — decorator.
- `stillholds.Effect(value, ci, n, ci_level=0.95, direction="auto", unit="relative", label=None)`
  with properties `ci_width`, `crosses_zero`, `resolved_direction` and
  `to_dict`/`from_dict`.
- `stillholds.evaluate(baseline, current, cfg=None, *, precision_guard=True)`.
- `stillholds.Verdict` (HOLDS/REGRESSED/IMPROVED), `stillholds.Tolerances`,
  `stillholds.Evaluation`.
- CLI: `approve`, `check`, `explain`, `list`; global `--version`, `--help`.
- Stable exit codes: 0 ok · 1 regressed · 2 usage · 3 nothing-to-check · 4 error.

## Verified end-to-end

- From a clean clone, from an independent project, and WITHOUT git configured.
- approve → snapshot data (content-hash, dedup, faithful round-trip incl. datetime)
  + code snapshot (per commit or `nogit`).
- check → verdict + CI exit-code contract; no false-green when nothing has a baseline.
- explain → counterfactual attribution CODE/DATA/BOTH/INTERACTION/INCONCLUSIVE.
- Demo: PR#1 (more data)→HOLDS, PR#2 (broken filter)→REGRESSED cause CODE.

## This closing pass (language + polish only, no scope change)

- Translated ALL user-visible text and ALL source (docstrings, comments, tests,
  demo, config, Action) to English. `grep` for Spanish across the publishable
  repo now returns nothing (except the `×` math sign).
- Made the quickstart git-optional (removed the `git init && commit` requirement
  that failed for users without a configured git identity); documented that
  StillHolds works with or without git.
- Confirmed the public API surface is minimal and coherent; proposing it frozen for v1.

## Honest limitations of v0.1 (in README + CHANGELOG)

- Datasets must fit in the CI runner (snapshotted whole as CSV + dtypes).
- Analysis must live in an importable, self-contained module.
- A claim = one scalar with uncertainty. No tables/distributions/plots.
- "still holds" is a transparent heuristic over intervals, not a formal
  equivalence test.
- Attribution assumes an equivalent environment; warns on package changes but
  does not isolate the environment as a separate cause.

## Roadmap (out of v0.1 scope)

Three-way counterfactual (config), real env isolation per corner, optional
parquet snapshots, sensitivity analysis over analytical decisions.

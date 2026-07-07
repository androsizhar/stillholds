"""
attribution.py — the counterfactual attribution. The defensible core.

When evaluate() returns REGRESSED, we run the FOUR CORNERS:
    r_old_old = baseline (given)
    r_new_new = current  (given, it's the regression)
    r_new_old = new data + old code   (re-run)
    r_old_new = old data + new code   (re-run)

Attribution rule (same equivalence notion as evaluate, but with
precision_guard=False, because n changes by construction):
  A corner "reproduces the regression" if it is NOT equivalent to the baseline
  (evaluate(baseline, corner) != HOLDS/IMPROVED).
    - only new-code (r_old_new) reproduces -> CODE
    - only new-data (r_new_old) reproduces -> DATA
    - both reproduce                        -> BOTH_INDEPENDENT
    - neither alone reproduces              -> INTERACTION
    - a corner failed to run                -> INCONCLUSIVE

Re-running the old code: import the .py SNAPSHOT via importlib, NOT git checkout
nor cloudpickle. Honest environment guard.
"""
from __future__ import annotations

import importlib.util
import sys
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pandas as pd

from .claim import Claim, run_claim
from .effect import Effect
from .evaluate import Tolerances, Verdict, evaluate


class Cause(str, Enum):
    CODE = "CODE"
    DATA = "DATA"
    BOTH_INDEPENDENT = "BOTH_INDEPENDENT"
    INTERACTION = "INTERACTION"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class Attribution:
    cause: Cause
    r_new_old: Effect | None    # new data + old code
    r_old_new: Effect | None    # old data + new code
    env_warning: bool
    detail: str = ""


def import_analysis_from_snapshot(snapshot_path: Path, claim_name: str) -> Claim:
    """
    Import the analysis function from the .py snapshot as an isolated module
    (unique name to avoid colliding with the currently-loaded analysis module).
    Returns the Claim reconstructed from that module.
    """
    # NOTE: stillholds/__init__.py does `from .claim import claim`, so the
    # `stillholds.claim` attribute points to the FUNCTION, not the module. We
    # take the real module from sys.modules by its full name.
    claim_mod = sys.modules["stillholds.claim"]

    saved = dict(claim_mod._REGISTRY)
    claim_mod._REGISTRY.clear()
    try:
        mod_name = f"_stillholds_snapshot_{claim_name}_{uuid.uuid4().hex[:8]}"
        spec = importlib.util.spec_from_file_location(mod_name, snapshot_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"could not load snapshot {snapshot_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        if claim_name not in claim_mod._REGISTRY:
            raise ImportError(
                f"snapshot {snapshot_path} did not register claim '{claim_name}'"
            )
        old_claim = claim_mod._REGISTRY[claim_name]
        return old_claim
    finally:
        claim_mod._REGISTRY.clear()
        claim_mod._REGISTRY.update(saved)


def _reproduces_regression(baseline: Effect, corner: Effect, tol: Tolerances) -> bool:
    """
    True if `corner` departs from the baseline the way a regression does.
    We use precision_guard=False: in the counterfactual, n changes by
    construction, so we only care whether the VALUE/direction moved.
    """
    ev = evaluate(baseline, corner, tol, precision_guard=False)
    return ev.verdict == Verdict.REGRESSED


def attribute(
    *,
    claim_name: str,
    baseline_effect: Effect,
    current_effect: Effect,
    new_data: dict[str, pd.DataFrame],
    old_data: dict[str, pd.DataFrame],
    new_claim: Claim,
    old_claim: Claim,
    tolerances: Tolerances | None = None,
    env_warning: bool = False,
) -> Attribution:
    """
    Corre las dos esquinas faltantes y atribuye la causa.

    new_claim/old_claim: the Claims with the new code and the old code
    (the latter reconstructed with import_analysis_from_snapshot).
    """
    tol = tolerances or Tolerances()

    # corner: new data + old code
    try:
        r_new_old = run_claim(old_claim, new_data)
    except Exception as e:
        return Attribution(Cause.INCONCLUSIVE, None, None, env_warning,
                           detail=f"the new-data+old-code corner failed to run: {e}")

    # corner: old data + new code
    try:
        r_old_new = run_claim(new_claim, old_data)
    except Exception as e:
        return Attribution(Cause.INCONCLUSIVE, r_new_old, None, env_warning,
                           detail=f"the old-data+new-code corner failed to run: {e}")

    data_reproduces = _reproduces_regression(baseline_effect, r_new_old, tol)
    code_reproduces = _reproduces_regression(baseline_effect, r_old_new, tol)

    if code_reproduces and not data_reproduces:
        cause = Cause.CODE
    elif data_reproduces and not code_reproduces:
        cause = Cause.DATA
    elif code_reproduces and data_reproduces:
        cause = Cause.BOTH_INDEPENDENT
    else:
        cause = Cause.INTERACTION

    return Attribution(cause, r_new_old, r_old_new, env_warning)

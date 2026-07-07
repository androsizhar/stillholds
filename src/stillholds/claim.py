"""
claim.py — the @claim decorator, the registry, and the runner that executes a claim.

The decorated function must:
  - receive the input data as argument(s) by logical name (so the framework
    controls WHICH data it injects: the key to the counterfactual),
  - return an Effect.
"""
from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

from .effect import Effect

AnalysisFn = Callable[..., Effect]


@dataclass
class Claim:
    name: str
    fn: AnalysisFn
    source_file: str = ""


_REGISTRY: dict[str, Claim] = {}


def claim(name: str) -> Callable[[AnalysisFn], AnalysisFn]:
    """Register an analysis function as a uniquely-named claim."""
    def decorator(fn: AnalysisFn) -> AnalysisFn:
        if name in _REGISTRY:
            raise ValueError(f"claim duplicado: {name!r}")
        source_file = inspect.getsourcefile(fn) or ""
        _REGISTRY[name] = Claim(name=name, fn=fn, source_file=source_file)
        return fn
    return decorator


def get_registry() -> dict[str, Claim]:
    return dict(_REGISTRY)


def clear_registry() -> None:
    """For tests only: clear the registry between cases."""
    _REGISTRY.clear()


def discover_claims(module_name: str, root: Path | None = None) -> dict[str, Claim]:
    """
    Import the analysis module declared in config to populate the registry
    (like pytest imports test_*.py). Returns the resulting registry.
    """
    import sys
    root = root or Path.cwd()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    # clean reload in case it was already imported with another code version
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])
    else:
        importlib.import_module(module_name)
    return get_registry()


def _select_inputs(fn: AnalysisFn, data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Inject only the datasets the function declares by parameter name."""
    params = inspect.signature(fn).parameters
    return {name: data[name] for name in params if name in data}


def run_claim(claim_obj: Claim, data: dict[str, pd.DataFrame]) -> Effect:
    """Run the claim with the given data and validate it returns an Effect."""
    kwargs = _select_inputs(claim_obj.fn, data)
    result = claim_obj.fn(**kwargs)
    if not isinstance(result, Effect):
        raise TypeError(
            f"claim '{claim_obj.name}' returned {type(result).__name__}, "
            "it must return a stillholds.Effect"
        )
    return result


def check_determinism(claim_obj: Claim, data: dict[str, pd.DataFrame],
                      rel_tol: float = 1e-9) -> str | None:
    """
    Run the claim a second time on the SAME data and compare the two Effects.

    StillHolds assumes deterministic analyses: the same code on the same data
    must yield the same Effect. If it doesn't (unseeded bootstrap, sampling,
    train/test split, etc.), the baseline captures one random realization and
    later checks compare noise against noise, producing phantom regressions.

    Returns None if the claim looks deterministic, or a human-readable string
    describing the discrepancy if it does not. This DOES NOT fix the problem —
    it just surfaces it instead of failing silently.
    """
    first = run_claim(claim_obj, data)
    second = run_claim(claim_obj, data)

    def _close(x: float, y: float) -> bool:
        scale = max(abs(x), abs(y), 1e-12)
        return abs(x - y) <= rel_tol * scale

    if (_close(first.value, second.value)
            and _close(first.ci[0], second.ci[0])
            and _close(first.ci[1], second.ci[1])
            and first.n == second.n):
        return None

    return (f"value {first.value:.6g} vs {second.value:.6g}, "
            f"n {first.n} vs {second.n}")

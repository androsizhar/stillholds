"""
provenance.py — context capture: git, environment, and environment verification.

Responsibility: collect "which code and which environment produced this", and
detect when the environment changed (an honest guard for the counterfactual: if
the environment differs, cause attribution warns instead of feigning certainty).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

# Libraries whose version change CAN alter a numeric computation.
KEY_PACKAGES = ("pandas", "numpy", "scipy")


def _run_git(args: list[str], cwd: str | None = None) -> str | None:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=cwd or str(Path.cwd()),
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_git_commit() -> str:
    """Commit HEAD actual (corto), o 'nogit' si no hay repo."""
    commit = _run_git(["rev-parse", "--short", "HEAD"])
    return commit if commit else "nogit"


def is_git_dirty() -> bool:
    """True if there are uncommitted changes in the working tree."""
    status = _run_git(["status", "--porcelain"])
    return bool(status)


def _package_version(name: str) -> str | None:
    try:
        import importlib.metadata as im
        return im.version(name)
    except Exception:
        try:
            mod = __import__(name)
            return getattr(mod, "__version__", None)
        except Exception:
            return None


def capture_env() -> dict[str, Any]:
    """Environment relevant to reproducibility: python + key package versions."""
    key = {}
    for pkg in KEY_PACKAGES:
        v = _package_version(pkg)
        if v is not None:
            key[pkg] = v
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "key_packages": key,
    }


def env_differs(baseline_env: dict[str, Any], current_env: dict[str, Any]) -> bool:
    """True si difieren las versiones de key_packages (o de python)."""
    b_key = baseline_env.get("key_packages", {})
    c_key = current_env.get("key_packages", {})
    if baseline_env.get("python") != current_env.get("python"):
        return True
    if set(b_key) != set(c_key):
        return True
    return any(b_key[p] != c_key[p] for p in b_key)


def describe_env_diff(baseline_env: dict[str, Any], current_env: dict[str, Any]) -> str:
    """Human-readable text of what changed in the environment, for the report."""
    b_key = baseline_env.get("key_packages", {})
    c_key = current_env.get("key_packages", {})
    diffs = []
    if baseline_env.get("python") != current_env.get("python"):
        diffs.append(f"python {baseline_env.get('python')}\u2192{current_env.get('python')}")
    for p in sorted(set(b_key) | set(c_key)):
        bv, cv = b_key.get(p), c_key.get(p)
        if bv != cv:
            diffs.append(f"{p} {bv}\u2192{cv}")
    return ", ".join(diffs) if diffs else "no changes"

"""
config.py — reading stillholds.toml (the user's project file).

Declares which module to import to discover claims, where the input data lives,
and the algorithm tolerances.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from .evaluate import Tolerances


@dataclass
class ProjectConfig:
    analysis_module: str
    data: dict[str, str]                 # logical_name -> file path
    tolerances: Tolerances
    root: Path

    @property
    def data_paths(self) -> dict[str, Path]:
        return {name: (self.root / p) for name, p in self.data.items()}


def load_config(root: Path | None = None) -> ProjectConfig:
    root = root or Path.cwd()
    path = root / "stillholds.toml"
    if not path.exists():
        raise FileNotFoundError(f"stillholds.toml not found in {root}")
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    tol_raw = raw.get("tolerances", {})
    tol = Tolerances(
        max_shrink=tol_raw.get("max_shrink", 0.50),
        max_width_ratio=tol_raw.get("max_width_ratio", 2.0),
        improve_margin=tol_raw.get("improve_margin", 0.20),
    )
    return ProjectConfig(
        analysis_module=raw["analysis_module"],
        data=raw.get("data", {}),
        tolerances=tol,
        root=root,
    )

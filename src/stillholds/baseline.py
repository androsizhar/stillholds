"""
baseline.py — baseline and snapshot persistence.

Design reminder: the hash DETECTS change; the snapshot makes the COUNTERFACTUAL
possible. We need both, so the baseline stores hash + pointer.

Data snapshot format: CSV + a sidecar dtypes JSON, for a faithful round-trip
without depending on pyarrow/parquet (an explicit v0.1 decision). If the content
was already snapshotted (same hash), it is reused (dedup).
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

import pandas as pd

from .effect import Effect

SCHEMA_VERSION = 1
STILLHOLDS_DIR = ".stillholds"


# --------------------------- estructuras ---------------------------

@dataclass
class InputSnapshot:
    name: str
    sha256: str
    snapshot: str        # ruta relativa dentro de .stillholds/
    rows: int
    cols: int


@dataclass
class Provenance:
    analysis_fn: str
    code_snapshot: str
    code_dirty: bool
    inputs: list[InputSnapshot]
    config: dict[str, Any]
    env: dict[str, Any]


@dataclass
class Baseline:
    claim: str
    approved_at: str
    approved_commit: str
    effect: Effect
    provenance: Provenance
    schema_version: int = SCHEMA_VERSION

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "claim": self.claim,
            "approved_at": self.approved_at,
            "approved_commit": self.approved_commit,
            "effect": self.effect.to_dict(),
            "provenance": {
                "analysis_fn": self.provenance.analysis_fn,
                "code_snapshot": self.provenance.code_snapshot,
                "code_dirty": self.provenance.code_dirty,
                "inputs": [asdict(i) for i in self.provenance.inputs],
                "config": self.provenance.config,
                "env": self.provenance.env,
            },
        }

    @classmethod
    def from_json_dict(cls, d: dict[str, Any]) -> "Baseline":
        p = d["provenance"]
        return cls(
            claim=d["claim"],
            approved_at=d["approved_at"],
            approved_commit=d["approved_commit"],
            effect=Effect.from_dict(d["effect"]),
            provenance=Provenance(
                analysis_fn=p["analysis_fn"],
                code_snapshot=p["code_snapshot"],
                code_dirty=p["code_dirty"],
                inputs=[InputSnapshot(**i) for i in p["inputs"]],
                config=p.get("config", {}),
                env=p.get("env", {}),
            ),
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )


# --------------------------- rutas ---------------------------

def _root(root: Path | None) -> Path:
    base = (root or Path.cwd()) / STILLHOLDS_DIR
    (base / "baselines").mkdir(parents=True, exist_ok=True)
    (base / "data").mkdir(parents=True, exist_ok=True)
    (base / "code").mkdir(parents=True, exist_ok=True)
    return base


# --------------------------- hashing ---------------------------

def hash_dataframe(df: pd.DataFrame) -> str:
    """
    SHA256 estable del contenido de un DataFrame. Estable = mismo contenido da
    the same hash across runs and machines. We use a canonical serialization
    (ordered columns + values + dtypes) instead of pd.util.hash_pandas_object
    so the hash is reproducible and independent of version details.
    """
    h = hashlib.sha256()
    # estructura: nombres y dtypes de columnas en orden
    for col in df.columns:
        h.update(str(col).encode("utf-8"))
        h.update(str(df[col].dtype).encode("utf-8"))
    # content: canonical CSV (row order as-is, no index)
    h.update(df.to_csv(index=False).encode("utf-8"))
    return h.hexdigest()


# --------------------------- snapshots de datos ---------------------------

def snapshot_data(df: pd.DataFrame, name: str, root: Path | None = None) -> InputSnapshot:
    """
    Store data/<name>@<hash>.csv (+ .dtypes.json) for faithful round-trip.
    Dedup: if the same content is already snapshotted, it is not rewritten.
    """
    base = _root(root)
    digest = hash_dataframe(df)
    short = digest[:12]
    rel = f"data/{name}@{short}.csv"
    path = base / rel
    if not path.exists():
        df.to_csv(path, index=False)
        dtypes = {str(c): str(df[c].dtype) for c in df.columns}
        (base / f"data/{name}@{short}.dtypes.json").write_text(json.dumps(dtypes))
    return InputSnapshot(name=name, sha256=digest, snapshot=rel,
                         rows=int(len(df)), cols=int(df.shape[1]))


def load_snapshot_data(snap: InputSnapshot, root: Path | None = None) -> pd.DataFrame:
    """Recover the exact snapshotted DataFrame (for the counterfactual)."""
    base = _root(root)
    path = base / snap.snapshot
    dtypes_path = base / snap.snapshot.replace(".csv", ".dtypes.json")
    df = pd.read_csv(path)
    if dtypes_path.exists():
        dtypes = json.loads(dtypes_path.read_text())
        for c, dt in dtypes.items():
            if c in df.columns:
                try:
                    df[c] = df[c].astype(dt)
                except (ValueError, TypeError):
                    pass  # dtype not reconstructible; left as read
    return df


# --------------------------- code snapshots ---------------------------

def snapshot_code(source_file: str, claim_name: str, commit: str,
                  root: Path | None = None) -> str:
    """
    Copy the source .py to code/<claim>@<commit>.py. Transparent and
    re-importable via importlib (NOT cloudpickle, NOT git checkout).
    """
    base = _root(root)
    rel = f"code/{claim_name}@{commit}.py"
    dest = base / rel
    shutil.copy2(source_file, dest)
    return rel


# --------------------------- baseline I/O ---------------------------

def save_baseline(baseline: Baseline, root: Path | None = None) -> Path:
    base = _root(root)
    path = base / "baselines" / f"{baseline.claim}.json"
    path.write_text(json.dumps(baseline.to_json_dict(), indent=2, ensure_ascii=False))
    return path


def load_baseline(claim_name: str, root: Path | None = None) -> Baseline:
    base = _root(root)
    path = base / "baselines" / f"{claim_name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"no baseline for '{claim_name}'. Run `stillholds approve {claim_name}` first."
        )
    return Baseline.from_json_dict(json.loads(path.read_text()))


def baseline_exists(claim_name: str, root: Path | None = None) -> bool:
    base = (root or Path.cwd()) / STILLHOLDS_DIR / "baselines" / f"{claim_name}.json"
    return base.exists()

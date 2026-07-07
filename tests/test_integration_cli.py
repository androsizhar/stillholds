"""
End-to-end CLI integration test: sets up a temporary project
(analysis.py + datos + stillholds.toml), corre approve, luego check en tres
scenarios (no change, more data, broken filter) and explain over the regression.

Verifica el CONTRATO de exit codes (0 = HOLDS/IMPROVED, 1 = REGRESSED), que es
lo que enlaza con GitHub Actions.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPO_SRC = Path(__file__).resolve().parent.parent / "src"


def _write_project(root: Path, filter_col: str = "is_active") -> None:
    analysis = textwrap.dedent(f"""
        import pandas as pd
        from scipy.stats import norm
        import stillholds as sh

        @sh.claim("ab")
        def ab(events):
            cohort = events[events.{filter_col} == True]
            a = cohort[cohort.variant == "A"].signed_up.astype(float)
            b = cohort[cohort.variant == "B"].signed_up.astype(float)
            diff = b.mean() - a.mean()
            se = ((a.var(ddof=1)/len(a)) + (b.var(ddof=1)/len(b))) ** 0.5
            z = norm.ppf(0.975)
            return sh.Effect(float(diff), (float(diff-z*se), float(diff+z*se)),
                             int(len(cohort)), direction="increase", unit="absolute",
                             label="pp")
    """)
    (root / "analysis.py").write_text(analysis)
    (root / "stillholds.toml").write_text(
        'analysis_module = "analysis"\n\n[data]\nevents = "events.csv"\n'
    )


def _make_events(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    variant = rng.choice(["A", "B"], n)
    # Contraste ROBUSTO a cualquier seed (verificado sobre 10 seeds):
    # - ACTIVE (~40%): large B-A effect (+15pp), clear signal.
    # - INACTIVE (~60%): very low conversion (5%) and NO variant effect.
    # is_registered pulls in 95% of the inactive -> massive dilution that breaks
    # the conclusion. is_active keeps it.
    is_active = rng.random(n) < 0.40
    is_registered = is_active | ((~is_active) & (rng.random(n) < 0.95))
    p = np.where(is_active, np.where(variant == "B", 0.30, 0.15), 0.05)
    signed_up = (rng.random(n) < p).astype(int)
    return pd.DataFrame({"variant": variant, "is_active": is_active,
                         "is_registered": is_registered, "signed_up": signed_up})


def _run(root: Path, *args) -> subprocess.CompletedProcess:
    env = {"PYTHONPATH": str(REPO_SRC), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    import os
    env = {**os.environ, "PYTHONPATH": str(REPO_SRC)}
    return subprocess.run(
        [sys.executable, "-m", "stillholds.cli", *args],
        cwd=root, capture_output=True, text=True, env=env,
    )


@pytest.fixture
def project(tmp_path):
    _write_project(tmp_path, "is_active")
    _make_events(4000, seed=1).to_csv(tmp_path / "events.csv", index=False)
    # git init so the code snapshot has a commit
    import subprocess as sp
    sp.run(["git", "init", "-q"], cwd=tmp_path)
    sp.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path)
    sp.run(["git", "config", "user.name", "t"], cwd=tmp_path)
    sp.run(["git", "add", "-A"], cwd=tmp_path)
    sp.run(["git", "commit", "-qm", "init"], cwd=tmp_path)
    return tmp_path


class TestEndToEnd:
    def test_approve_creates_baseline_and_snapshots(self, project):
        r = _run(project, "approve")
        assert r.returncode == 0, r.stderr
        assert (project / ".stillholds" / "baselines" / "ab.json").exists()
        data_snaps = list((project / ".stillholds" / "data").glob("events@*.csv"))
        assert len(data_snaps) == 1
        code_snaps = list((project / ".stillholds" / "code").glob("ab@*.py"))
        assert len(code_snaps) == 1

    def test_check_no_change_holds_exit_0(self, project):
        assert _run(project, "approve").returncode == 0
        r = _run(project, "check")
        assert r.returncode == 0
        assert "HOLDS" in r.stdout

    def test_check_more_data_holds_exit_0(self, project):
        assert _run(project, "approve").returncode == 0
        _make_events(13000, seed=2).to_csv(project / "events.csv", index=False)
        r = _run(project, "check")
        # more data that does not break the conclusion: exit 0. Can be HOLDS or
        # IMPROVED (if the effect strengthened); both mean "did not regress".
        assert r.returncode == 0, r.stdout + r.stderr
        assert "HOLDS" in r.stdout or "IMPROVED" in r.stdout

    def test_check_broken_filter_regresses_exit_1(self, project):
        assert _run(project, "approve").returncode == 0
        # PR#2: change the filter (identical data)
        _write_project(project, "is_registered")
        r = _run(project, "check")
        assert r.returncode == 1
        assert "REGRESSED" in r.stdout

    def test_explain_attributes_to_code(self, project):
        assert _run(project, "approve").returncode == 0
        _write_project(project, "is_registered")
        r = _run(project, "explain", "ab")
        assert r.returncode == 0, r.stderr
        assert "ANALYSIS FILE" in r.stdout

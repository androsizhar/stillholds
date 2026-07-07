"""
Tests de persistencia: baseline round-trip, snapshots de datos (dedup + round-
faithful round-trip), code snapshot. Require pandas.
"""
import json
from pathlib import Path

import pandas as pd
import pytest

from stillholds.baseline import (
    Baseline, InputSnapshot, Provenance,
    hash_dataframe, snapshot_data, load_snapshot_data,
    snapshot_code, save_baseline, load_baseline, baseline_exists,
)
from stillholds.effect import Effect


def _dummy_baseline() -> Baseline:
    return Baseline(
        claim="c", approved_at="2026-07-06T18:30:00-06:00", approved_commit="abc1234",
        effect=Effect(0.05, (0.02, 0.08), 4000, direction="increase", unit="absolute"),
        provenance=Provenance(
            analysis_fn="analysis::c", code_snapshot="code/c@abc1234.py",
            code_dirty=False,
            inputs=[InputSnapshot("events", "deadbeef", "data/events@deadbeef.csv", 4000, 3)],
            config={}, env={"python": "3.12.3", "key_packages": {"pandas": "3.0.2"}},
        ),
    )


class TestBaselineRoundtrip:
    def test_json_roundtrip_preserves_effect(self, tmp_path):
        b = _dummy_baseline()
        save_baseline(b, root=tmp_path)
        loaded = load_baseline("c", root=tmp_path)
        assert loaded.effect == b.effect
        assert loaded.approved_commit == "abc1234"
        assert loaded.provenance.inputs[0].sha256 == "deadbeef"

    def test_load_missing_baseline_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_baseline("nope", root=tmp_path)

    def test_baseline_exists(self, tmp_path):
        assert not baseline_exists("c", root=tmp_path)
        save_baseline(_dummy_baseline(), root=tmp_path)
        assert baseline_exists("c", root=tmp_path)


class TestDataSnapshot:
    def test_hash_stable_same_content(self):
        df1 = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        df2 = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        assert hash_dataframe(df1) == hash_dataframe(df2)

    def test_hash_changes_with_content(self):
        df1 = pd.DataFrame({"a": [1, 2, 3]})
        df2 = pd.DataFrame({"a": [1, 2, 4]})
        assert hash_dataframe(df1) != hash_dataframe(df2)

    def test_snapshot_dedups_by_hash(self, tmp_path):
        df = pd.DataFrame({"a": [1, 2, 3]})
        s1 = snapshot_data(df, "events", root=tmp_path)
        s2 = snapshot_data(df, "events", root=tmp_path)
        assert s1.sha256 == s2.sha256
        assert s1.snapshot == s2.snapshot  # mismo archivo, no duplicado

    def test_snapshot_roundtrip_preserves_dtypes(self, tmp_path):
        df = pd.DataFrame({"i": [1, 2], "f": [1.5, 2.5], "b": [True, False], "s": ["a", "b"]})
        snap = snapshot_data(df, "events", root=tmp_path)
        loaded = load_snapshot_data(snap, root=tmp_path)
        assert list(loaded.dtypes) == list(df.dtypes)
        pd.testing.assert_frame_equal(loaded, df)

    def test_snapshot_roundtrip_with_datetime(self, tmp_path):
        # the counterfactual depends on FAITHFUL round-trip; datetime is the fragile case
        df = pd.DataFrame({
            "v": [1.0, 2.0],
            "when": pd.to_datetime(["2026-01-01", "2026-07-06"]),
        })
        snap = snapshot_data(df, "events", root=tmp_path)
        loaded = load_snapshot_data(snap, root=tmp_path)
        assert str(loaded["when"].dtype).startswith("datetime64")
        pd.testing.assert_frame_equal(loaded, df)


class TestCodeSnapshot:
    def test_code_snapshot_copies_source(self, tmp_path):
        src = tmp_path / "analysis.py"
        src.write_text("# hola\nX = 1\n")
        rel = snapshot_code(str(src), "c", "abc1234", root=tmp_path)
        dest = tmp_path / ".stillholds" / rel
        assert dest.exists()
        assert "X = 1" in dest.read_text()


class TestDeterminismGuard:
    def test_deterministic_claim_passes(self):
        from stillholds.claim import Claim, check_determinism
        from stillholds.effect import Effect
        import pandas as pd

        def analysis(events):
            return Effect(float(events.y.mean()),
                          (float(events.y.mean() - 0.1), float(events.y.mean() + 0.1)),
                          len(events), unit="absolute")
        data = {"events": pd.DataFrame({"y": [1.0, 2.0, 3.0]})}
        assert check_determinism(Claim("c", analysis, ""), data) is None

    def test_nondeterministic_claim_flagged(self):
        from stillholds.claim import Claim, check_determinism
        from stillholds.effect import Effect
        import numpy as np
        import pandas as pd

        def analysis(events):
            # unseeded randomness -> different value each call
            m = float(np.random.default_rng().normal(0, 1))
            return Effect(m, (m - 1.0, m + 1.0), len(events), unit="absolute")
        data = {"events": pd.DataFrame({"y": [1.0, 2.0, 3.0]})}
        result = check_determinism(Claim("c", analysis, ""), data)
        assert result is not None
        assert "vs" in result  # describes the discrepancy

"""
cli.py — commands: approve, check, explain, list.

  stillholds approve [claim]   -> run, store baseline + snapshots
  stillholds check   [claim]   -> run, compare; exit 0 if HOLDS/IMPROVED,
                                  exit 1 if REGRESSED (CI contract),
                                  exit 3 if there was NOTHING to check
  stillholds explain <claim>   -> run the counterfactual, print the attribution
  stillholds list              -> claims and their latest verdict

check is fast (evaluate only). explain is expensive (counterfactual) and separate.

Exit codes (stable contract):
  0  all good (HOLDS / IMPROVED / successful operation)
  1  at least one claim REGRESSED
  2  usage error (unknown claim, missing baseline for the requested claim)
  3  nothing to check (no claim has a baseline yet)
  4  configuration or analysis-execution error
"""
from __future__ import annotations

import argparse
import datetime
import sys
from pathlib import Path

import pandas as pd

from . import __version__
from . import baseline as bl
from . import provenance as prov
from . import report
from .attribution import attribute, import_analysis_from_snapshot
from .claim import check_determinism, discover_claims, run_claim
from .config import load_config
from .evaluate import Verdict, evaluate

# named exit codes, so the code reads for itself
EXIT_OK = 0
EXIT_REGRESSED = 1
EXIT_USAGE = 2
EXIT_NOTHING = 3
EXIT_ERROR = 4


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _err(msg: str) -> None:
    print(f"stillholds: {msg}", file=sys.stderr)


def _load_config_or_exit():
    try:
        return load_config()
    except FileNotFoundError as e:
        _err(str(e))
        _err("create a stillholds.toml (see `stillholds --help` or the README).")
        raise SystemExit(EXIT_ERROR)


def _load_data_or_exit(cfg) -> dict[str, pd.DataFrame]:
    data = {}
    for name, path in cfg.data_paths.items():
        if not path.exists():
            _err(f"data file '{name}' not found: {path}")
            raise SystemExit(EXIT_ERROR)
        try:
            data[name] = pd.read_csv(path)
        except Exception as e:
            _err(f"could not read '{name}' ({path}): {e}")
            raise SystemExit(EXIT_ERROR)
    return data


def _discover_or_exit(cfg):
    try:
        return discover_claims(cfg.analysis_module, cfg.root)
    except ModuleNotFoundError:
        _err(f"could not import analysis module '{cfg.analysis_module}'.")
        _err("check 'analysis_module' in stillholds.toml.")
        raise SystemExit(EXIT_ERROR)
    except Exception as e:
        _err(f"error importing '{cfg.analysis_module}': {e}")
        raise SystemExit(EXIT_ERROR)


def _run_claim_or_exit(claim_obj, data):
    try:
        return run_claim(claim_obj, data)
    except Exception as e:
        _err(f"analysis for claim '{claim_obj.name}' failed to run: {e}")
        raise SystemExit(EXIT_ERROR)


def _resolve_claims(cfg, registry, claim_name: str | None):
    if claim_name:
        if claim_name not in registry:
            known = ", ".join(sorted(registry)) or "(none)"
            _err(f"unknown claim: '{claim_name}'. Available claims: {known}")
            raise SystemExit(EXIT_USAGE)
        return {claim_name: registry[claim_name]}
    if not registry:
        _err("no claims discovered. Did you define a function with @sh.claim?")
        raise SystemExit(EXIT_ERROR)
    return registry


# ------------------------------- approve -------------------------------

def cmd_approve(args) -> int:
    cfg = _load_config_or_exit()
    data = _load_data_or_exit(cfg)
    registry = _discover_or_exit(cfg)
    claims = _resolve_claims(cfg, registry, args.claim)
    commit = prov.get_git_commit()
    dirty = prov.is_git_dirty()
    env = prov.capture_env()

    if commit == "nogit":
        _err("warning: no git detected; the code snapshot will be stored under "
             "commit 'nogit'. For full traceability, version-control the project.")

    for name, claim_obj in claims.items():
        effect = _run_claim_or_exit(claim_obj, data)

        # Non-determinism guard: a baseline only makes sense if the same code on
        # the same data yields the same Effect. If not, warn loudly (but don't
        # block: the user may know what they're doing). StillHolds cannot tell a
        # real regression from run-to-run noise for a non-deterministic claim.
        try:
            discrepancy = check_determinism(claim_obj, data)
        except Exception:
            discrepancy = None  # never let the guard itself break approve
        if discrepancy is not None:
            _err(f"warning: claim '{name}' appears NON-DETERMINISTIC "
                 f"({discrepancy}).")
            _err("  StillHolds assumes deterministic analyses. Seed your "
                 "randomness (e.g. np.random.default_rng(SEED)), or expect "
                 "phantom regressions and unreliable attribution.")

        inputs = [bl.snapshot_data(data[dn], dn, root=cfg.root)
                  for dn in cfg.data if dn in data]
        code_rel = bl.snapshot_code(claim_obj.source_file, name, commit, root=cfg.root)
        baseline = bl.Baseline(
            claim=name,
            approved_at=_now(),
            approved_commit=commit,
            effect=effect,
            provenance=bl.Provenance(
                analysis_fn=f"{cfg.analysis_module}::{name}",
                code_snapshot=code_rel,
                code_dirty=dirty,
                inputs=inputs,
                config={},
                env=env,
            ),
        )
        bl.save_baseline(baseline, root=cfg.root)
        dirty_note = "  ⚠ (with uncommitted changes)" if dirty else ""
        print(f"✓ baseline approved — {name}: {report.fmt_effect(effect)}{dirty_note}")
    return EXIT_OK


# ------------------------------- check -------------------------------

def cmd_check(args) -> int:
    cfg = _load_config_or_exit()
    data = _load_data_or_exit(cfg)
    registry = _discover_or_exit(cfg)
    claims = _resolve_claims(cfg, registry, args.claim)
    markdown = args.format == "markdown"

    any_regressed = False
    checked = 0
    skipped = []
    chunks = []

    for name, claim_obj in claims.items():
        if not bl.baseline_exists(name, root=cfg.root):
            skipped.append(name)
            continue
        checked += 1
        baseline = bl.load_baseline(name, root=cfg.root)
        current = _run_claim_or_exit(claim_obj, data)
        ev = evaluate(baseline.effect, current, cfg.tolerances)

        if ev.verdict == Verdict.REGRESSED:
            any_regressed = True
            chunks.append(report.render_regressed(name, baseline.effect, current, ev))
        else:
            chunks.append(report.render_holds(name, baseline.effect, current, ev))

        if not markdown:
            icon = {"HOLDS": "✓", "IMPROVED": "↑", "REGRESSED": "✗"}[ev.verdict.value]
            print(f"{icon} {name}: {ev.verdict.value} — {ev.reason}")

    if markdown and chunks:
        print("\n\n".join(chunks))

    # False-green guard: if NOT a single claim was checked, it is not "all good".
    if checked == 0:
        _err("no baseline approved yet; nothing to check.")
        _err(f"run `stillholds approve` first (claims without baseline: "
             f"{', '.join(skipped) or 'none'}).")
        return EXIT_NOTHING

    if skipped and not markdown:
        _err(f"skipped (no baseline): {', '.join(skipped)}")

    return EXIT_REGRESSED if any_regressed else EXIT_OK


# ------------------------------- explain -------------------------------

def cmd_explain(args) -> int:
    cfg = _load_config_or_exit()
    new_data = _load_data_or_exit(cfg)
    registry = _discover_or_exit(cfg)
    name = args.claim
    if name not in registry:
        known = ", ".join(sorted(registry)) or "(none)"
        _err(f"unknown claim: '{name}'. Available claims: {known}")
        return EXIT_USAGE
    if not bl.baseline_exists(name, root=cfg.root):
        _err(f"no baseline for '{name}'. Run `stillholds approve {name}` first.")
        return EXIT_USAGE

    baseline = bl.load_baseline(name, root=cfg.root)
    new_claim = registry[name]
    current = _run_claim_or_exit(new_claim, new_data)
    ev = evaluate(baseline.effect, current, cfg.tolerances)

    if ev.verdict != Verdict.REGRESSED:
        print(f"'{name}' is not regressed ({ev.verdict.value}); nothing to attribute.")
        return EXIT_OK

    # reconstruir datos viejos desde los snapshots
    old_data = {}
    for snap in baseline.provenance.inputs:
        old_data[snap.name] = bl.load_snapshot_data(snap, root=cfg.root)

    # reconstruct the old code from the snapshot
    code_path = cfg.root / bl.STILLHOLDS_DIR / baseline.provenance.code_snapshot
    if not code_path.exists():
        _err(f"code snapshot not found: {code_path}")
        _err("cannot attribute without the baseline code. Re-approve the claim.")
        return EXIT_ERROR
    old_claim = import_analysis_from_snapshot(code_path, name)

    env_warning = prov.env_differs(baseline.provenance.env, prov.capture_env())
    attr = attribute(
        claim_name=name,
        baseline_effect=baseline.effect,
        current_effect=current,
        new_data=new_data,
        old_data=old_data,
        new_claim=new_claim,
        old_claim=old_claim,
        tolerances=cfg.tolerances,
        env_warning=env_warning,
    )

    if args.format == "markdown":
        print(report.render_regressed(name, baseline.effect, current, ev, attribution=attr))
    else:
        print(report.render_attribution_text(name, baseline.effect, current, ev, attr))
    return EXIT_OK


# ------------------------------- list -------------------------------

def cmd_list(args) -> int:
    cfg = _load_config_or_exit()
    data = _load_data_or_exit(cfg)
    registry = _discover_or_exit(cfg)
    if not registry:
        print("no claims discovered.")
        return EXIT_OK

    icons = {"HOLDS": "✓", "IMPROVED": "↑", "REGRESSED": "✗"}
    for name, claim_obj in registry.items():
        if not bl.baseline_exists(name, root=cfg.root):
            print(f"  ○ {name}: no baseline (run `stillholds approve {name}`)")
            continue
        baseline = bl.load_baseline(name, root=cfg.root)
        current = _run_claim_or_exit(claim_obj, data)
        ev = evaluate(baseline.effect, current, cfg.tolerances)
        icon = icons[ev.verdict.value]
        print(f"  {icon} {name}: {ev.verdict.value}  "
              f"(baseline {report.fmt_effect(baseline.effect)})")
    return EXIT_OK


# ------------------------------- parser -------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stillholds",
        description="CI for analytical claims — does your conclusion still hold?",
    )
    p.add_argument("--version", action="version", version=f"stillholds {__version__}")
    sub = p.add_subparsers(dest="command", required=True, metavar="{approve,check,explain,list}")

    a = sub.add_parser("approve", help="approve the current result as the baseline")
    a.add_argument("claim", nargs="?", default=None, help="specific claim (default: all)")
    a.set_defaults(func=cmd_approve)

    c = sub.add_parser("check", help="compare against baseline (exit 1 on regression)")
    c.add_argument("claim", nargs="?", default=None)
    c.add_argument("--format", choices=["text", "markdown"], default="text",
                   help="output format (markdown for PR comments)")
    c.set_defaults(func=cmd_check)

    e = sub.add_parser("explain", help="attribute the cause of a regression (counterfactual)")
    e.add_argument("claim")
    e.add_argument("--format", choices=["text", "markdown"], default="text")
    e.set_defaults(func=cmd_explain)

    l = sub.add_parser("list", help="list claims and their latest verdict")
    l.set_defaults(func=cmd_list)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit as e:
        return int(e.code) if e.code is not None else EXIT_OK
    except KeyboardInterrupt:
        _err("interrupted.")
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())

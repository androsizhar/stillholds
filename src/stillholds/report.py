"""
report.py — generates the terminal report and the PR markdown comment.

Pure text, no I/O -> fully implemented and testable with string snapshots. It is
the visible face of the product; clarity matters as much as the algorithm.
"""
from __future__ import annotations

from .effect import Effect
from .evaluate import Evaluation, Verdict


def fmt_effect(e: Effect) -> str:
    """
    Format an Effect readably according to its unit.
    - relative: fraction -> percentage (0.14 -> "+14.0%").
    - absolute: if the label asks for percentage points ("pp"/"point"), scale to
      pp; if the value is small (|v|<1, typical of rates) use 3 decimals;
      otherwise 2 decimals for large magnitudes ($, counts, etc.).
    """
    if e.unit == "relative":
        return _fmt_scaled(e, scale=100, suffix="%", prec=1)
    label = (e.label or "").lower()
    if "pp" in label or "punto" in label or "point" in label:
        return _fmt_scaled(e, scale=100, suffix="pp", prec=2)
    prec = 3 if abs(e.value) < 1 else 2
    return _fmt_scaled(e, scale=1, suffix="", prec=prec)


def _fmt_scaled(e: Effect, *, scale: float, suffix: str, prec: int) -> str:
    return (
        f"{e.value * scale:+.{prec}f}{suffix} "
        f"(95% CI [{e.ci[0] * scale:+.{prec}f}{suffix}, {e.ci[1] * scale:+.{prec}f}{suffix}], "
        f"n={e.n:,})"
    )


def _table(baseline: Effect, current: Effect) -> str:
    return (
        "| | Baseline | Current |\n"
        "|---|---|---|\n"
        f"| Effect | {fmt_effect(baseline)} | {fmt_effect(current)} |\n"
    )


def render_holds(claim: str, baseline: Effect, current: Effect, ev: Evaluation) -> str:
    if ev.verdict == Verdict.IMPROVED:
        icon, head, note = "", "improved", "The claim is now *stronger* than the approved baseline."
    else:
        icon, head, note = "", "still holds", "Inputs changed, but the claim stays within the accepted band."
    return (
        f"### {icon} `{claim}` — {head}\n\n"
        f"> {note}\n\n"
        f"{_table(baseline, current)}\n"
        f"_{ev.reason}._\n"
    )


def render_regressed(claim: str, baseline: Effect, current: Effect,
                     ev: Evaluation, attribution=None) -> str:
    body = (
        f"###  `{claim}` — insight regression detected\n\n"
        f"{_table(baseline, current)}\n"
        f"**Why:** {ev.reason}\n\n"
    )
    if attribution is not None:
        body += _render_attribution_md(attribution)
    return body


def _render_attribution_md(attr) -> str:
    from .attribution import Cause
    labels = {
        Cause.CODE: " The **analysis file** changed — data unchanged (re-ran the snapshotted analysis file on the new data; it reproduced the baseline).",
        Cause.DATA: " The **data** changed — analysis file unchanged (re-ran the current analysis file on the old data; it reproduced the baseline).",
        Cause.BOTH_INDEPENDENT: " Both data **and** the analysis file changed; each one alone reproduces the regression.",
        Cause.INTERACTION: " Neither data nor the analysis file alone reproduces it — the cause is their **interaction**.",
        Cause.INCONCLUSIVE: " Could not isolate the cause — a counterfactual re-run failed.",
    }
    out = ["**Attributed cause (by counterfactual re-run of the analysis file):**\n", labels.get(attr.cause, str(attr.cause))]
    if attr.detail:
        out.append(f"\n_{attr.detail}_")
    if attr.env_warning:
        out.append(
            "\n\n>  **Note:** key packages changed since the baseline, so this "
            "attribution may be affected by the environment, not only data/code."
        )
    # Honest scope note: the snapshot is the analysis FILE only, not its imports.
    out.append(
        "\n\n>  Attribution snapshots the analysis file only. If your analysis "
        "imports project code from other files, changes there are not isolated "
        "and may be mis-attributed."
    )
    return "\n".join(out) + "\n"


def render_attribution_text(claim: str, baseline: Effect, current: Effect,
                            ev: Evaluation, attr) -> str:
    """Terminal version (no markdown)."""
    from .attribution import Cause
    lines = [
        f"Insight regression: {claim}",
        f"  baseline: {fmt_effect(baseline)}",
        f"  current:  {fmt_effect(current)}",
        f"  why:      {ev.reason}",
    ]
    if attr.r_new_old is not None:
        lines.append(f"  [new data + old analysis file] -> {fmt_effect(attr.r_new_old)}")
    if attr.r_old_new is not None:
        lines.append(f"  [old data + new analysis file] -> {fmt_effect(attr.r_old_new)}")
    cause_txt = {
        Cause.CODE: "ANALYSIS FILE (data does not explain the regression)",
        Cause.DATA: "DATA (analysis file does not explain the regression)",
        Cause.BOTH_INDEPENDENT: "BOTH independently",
        Cause.INTERACTION: "INTERACTION (not isolable to a single factor)",
        Cause.INCONCLUSIVE: "INCONCLUSIVE",
    }
    lines.append(f"  cause:    {cause_txt.get(attr.cause, attr.cause)}")
    if attr.env_warning:
        lines.append("  note:     the environment changed; attribution may be affected")
    lines.append("  scope:    snapshots the analysis file only; imported project "
                 "code is not isolated")
    return "\n".join(lines)

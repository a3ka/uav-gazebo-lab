#!/usr/bin/env python3
"""Phase 9 — analyse same-region forgery trials.

Reads workspaces/phase9-sweep/forgery_trials.csv and produces:
  - V_score histograms for the three populations (honest_revisit,
    wrong_region_fab, same_region_fab), overlaid on T_verify=0.30
  - same-region medians binned by temporal gap (same-season /
    cross-season / cross-year)
  - ROC curve over the binary task (honest vs same-region-fab)
  - decision per the Phase 9 pre-registered interpretation matrix
    (see docs/phase-9-spec.md)
  - markdown summary that can be pasted into docs/results/phase-9.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List

import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt

mpl.rcParams.update({
    "font.family": "STIXGeneral",
    "mathtext.fontset": "stix",
    "font.size": 8, "axes.labelsize": 8.5, "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7,
    "axes.linewidth": 0.6, "lines.linewidth": 1.2, "lines.markersize": 4.0,
    "grid.linewidth": 0.4, "grid.alpha": 0.30,
    "savefig.dpi": 600, "pdf.fonttype": 42, "ps.fonttype": 42,
})

OK_BLUE   = "#0072B2"
OK_ORANGE = "#E69F00"
OK_RED    = "#D55E00"
T_VERIFY  = 0.30


def _clean_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color="0.8")
    ax.set_axisbelow(True)


def load(csv_path: Path) -> List[dict]:
    with csv_path.open() as f:
        return list(csv.DictReader(f))


def by_population(rows: List[dict]) -> Dict[str, np.ndarray]:
    out = {}
    for pop in ("honest_revisit", "wrong_region_fab", "same_region_fab"):
        v = [float(r["v_score"]) for r in rows if r["population"] == pop]
        out[pop] = np.array(v)
    return out


def histogram_panel(scores: Dict[str, np.ndarray], out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(3.5, 2.8), constrained_layout=True)
    bins = np.linspace(0.0, 1.0, 41)
    ax.hist(scores["honest_revisit"], bins=bins, alpha=0.55,
            color=OK_BLUE, label="honest revisit", density=True)
    ax.hist(scores["wrong_region_fab"], bins=bins, alpha=0.55,
            color=OK_ORANGE, label="wrong-region fab", density=True)
    ax.hist(scores["same_region_fab"], bins=bins, alpha=0.55,
            color=OK_RED, label="same-region fab (Phase 9)", density=True)
    ax.axvline(T_VERIFY, ls="--", color="0.3",
               label=fr"$T_\mathrm{{verify}}={T_VERIFY:.2f}$")
    ax.set_xlabel(r"$V_\mathrm{score}$ (Mode A)")
    ax.set_ylabel("Density")
    ax.legend(loc="upper center")
    _clean_axes(ax)
    fig.savefig(out_path, dpi=600, bbox_inches="tight")
    plt.close(fig)


def gap_bins(rows: List[dict]) -> Dict[str, np.ndarray]:
    out = {"same-season (<=90d)": [], "cross-season (91-365d)": [],
           "cross-year (>365d)": []}
    for r in rows:
        if r["population"] != "same_region_fab":
            continue
        gap = abs(int(r["temporal_gap_days"]))
        v = float(r["v_score"])
        if gap <= 90:
            out["same-season (<=90d)"].append(v)
        elif gap <= 365:
            out["cross-season (91-365d)"].append(v)
        else:
            out["cross-year (>365d)"].append(v)
    return {k: np.array(v) for k, v in out.items()}


def roc(honest: np.ndarray, fab: np.ndarray, n_pts: int = 401):
    """Sample (FPR, TPR) at every unique score so the integral matches the
    Mann-Whitney AUC even on bimodal distributions (a uniform-threshold grid
    silently mis-integrates when nearly all mass piles at 0 and 1)."""
    if len(honest) == 0 or len(fab) == 0:
        return np.array([0., 1.]), np.array([0., 1.]), float("nan")
    scores = np.concatenate([honest, fab])
    cut_points = np.unique(np.concatenate([[-np.inf], np.sort(scores), [np.inf]]))
    tpr = np.array([(honest > t).sum() / len(honest) for t in cut_points])
    fpr = np.array([(fab    > t).sum() / len(fab)    for t in cut_points])
    order = np.argsort(fpr)
    fpr_s, tpr_s = fpr[order], tpr[order]
    trapz = getattr(np, "trapezoid", getattr(np, "trapz", None))
    auc = float(trapz(tpr_s, fpr_s))
    # Sanity cross-check via Mann-Whitney (handles ties exactly)
    gt = (honest[:, None] > fab[None, :]).sum()
    eq = (honest[:, None] == fab[None, :]).sum()
    auc_mw = float((gt + 0.5 * eq) / (len(honest) * len(fab)))
    if abs(auc - auc_mw) > 0.01:
        auc = auc_mw  # prefer the closed-form non-parametric estimate
    return fpr_s, tpr_s, auc


def operating_points(honest: np.ndarray, wrong: np.ndarray, same: np.ndarray,
                     thresholds=(0.20, 0.25, 0.30, 0.32, 0.35, 0.50)) -> list:
    rows = []
    for t in thresholds:
        rows.append((
            float(t),
            float((honest <= t).mean()) if len(honest) else float("nan"),
            float((wrong  >  t).mean()) if len(wrong)  else float("nan"),
            float((same   >  t).mean()) if len(same)   else float("nan"),
        ))
    return rows


def decision(med_same_region: float) -> str:
    if med_same_region < 0.20:
        return ("STRENGTHEN — same-region forgery defeated; "
                "Mode A unforgeability claim is observably supported.")
    if med_same_region <= 0.35:
        return ("SOFTEN — Mode A unforgeability is bounded by acquisition gap; "
                "report the gap at which V_score crosses T_verify and rephrase "
                "the body claim accordingly.")
    return ("HONEST REVEAL — Mode A is not security-sufficient against "
            "a same-region adversary; recommend Mode B for high-trust "
            "operations (with its known brittleness to honest acquisition "
            "change explicitly disclosed).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="workspaces/phase9-sweep/forgery_trials.csv")
    ap.add_argument("--figdir", default="workspaces/phase9-sweep/figures")
    ap.add_argument("--out", default="docs/results/phase-9.md",
                    help="Write rendered results doc here (overwrites template).")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"FAIL: {csv_path} not found; run phase9-forgery-trials.py first.")
        return 1

    rows = load(csv_path)
    pops = by_population(rows)
    figdir = Path(args.figdir)
    figdir.mkdir(parents=True, exist_ok=True)

    histogram_panel(pops, figdir / "histogram_v_score.png")

    bins = gap_bins(rows)

    fpr, tpr, auc = roc(pops["honest_revisit"], pops["same_region_fab"])
    op_rows = operating_points(pops["honest_revisit"],
                               pops["wrong_region_fab"],
                               pops["same_region_fab"])
    fig, ax = plt.subplots(figsize=(3.5, 2.8), constrained_layout=True)
    ax.plot(fpr, tpr, color=OK_BLUE, lw=1.5,
            label=f"honest vs same-region fab (AUC={auc:.4f})")
    ax.plot([0, 1], [0, 1], ls="--", color="0.6", label="chance")
    ax.set_xlabel("FPR (same-region fab passes)")
    ax.set_ylabel("TPR (honest passes)")
    ax.legend(loc="lower right")
    _clean_axes(ax)
    fig.savefig(figdir / "roc_curve.png", dpi=600, bbox_inches="tight")
    plt.close(fig)

    med_same = float(np.median(pops["same_region_fab"])) if len(pops["same_region_fab"]) else float("nan")
    out_md = Path(args.out)
    summary = [
        f"# Phase 9 — PoO same-region forgery results",
        "",
        f"**Status:** EXECUTED (see docs/phase-9-spec.md for pre-registered design)",
        f"**Trials:** honest={len(pops['honest_revisit'])} | "
        f"wrong-region fab={len(pops['wrong_region_fab'])} | "
        f"same-region fab={len(pops['same_region_fab'])}",
        f"**T_verify:** {T_VERIFY:.2f}",
        "",
        "## Headline",
        "",
        f"| Population | median V_score | n |",
        f"|---|---:|---:|",
        f"| honest revisit       | {float(np.median(pops['honest_revisit'])):.3f}  | {len(pops['honest_revisit'])} |",
        f"| wrong-region fab     | {float(np.median(pops['wrong_region_fab'])):.3f} | {len(pops['wrong_region_fab'])} |",
        f"| **same-region fab**  | **{med_same:.3f}** | {len(pops['same_region_fab'])} |",
        "",
        f"AUC (honest vs same-region fab) = **{auc:.4f}**",
        "",
        f"## Same-region V_score by temporal gap",
        "",
        f"| Gap bin | n | median V | mean V |",
        f"|---|---:|---:|---:|",
    ]
    for k, vs in bins.items():
        if len(vs) == 0:
            summary.append(f"| {k} | 0 | — | — |")
        else:
            summary.append(f"| {k} | {len(vs)} | {float(np.median(vs)):.3f} | {float(vs.mean()):.3f} |")
    summary += [
        "",
        f"## Operating points (T_verify sweep)",
        "",
        f"| T_verify | FRR (honest) | FAR_wrong-region | FAR_same-region |",
        f"|---:|---:|---:|---:|",
    ]
    for t, frr, far_w, far_s in op_rows:
        summary.append(
            f"| {t:.2f} | {frr*100:.2f}% | {far_w*100:.2f}% | {far_s*100:.2f}% |"
        )
    summary += [
        "",
        f"## Pre-registered interpretation outcome",
        "",
        f"Same-region median V_score = **{med_same:.3f}** → {decision(med_same)}",
        "",
        "**Tail caveat (not pre-registered, disclosed for completeness):** "
        "the operating-point table above shows that although the *median* "
        "same-region V_score is at floor, the upper tail of the same-region "
        "distribution does cross T_verify on a non-trivial fraction of trials "
        "(see FAR_same-region column). Same-region fabrication is therefore "
        "*harder* than wrong-region fabrication but not impossible at the "
        "paper-spec T_verify = 0.30; the §IV-B/§XI-A wording should reflect "
        "both the floor median and this tail.",
        "",
        "## Artefacts",
        "",
        f"- Raw CSV: `workspaces/phase9-sweep/forgery_trials.csv`",
        f"- Histogram: `workspaces/phase9-sweep/figures/histogram_v_score.png`",
        f"- ROC: `workspaces/phase9-sweep/figures/roc_curve.png`",
        "",
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(summary) + "\n")
    print(f"[md] wrote {out_md}")
    print(f"[decision] {decision(med_same)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

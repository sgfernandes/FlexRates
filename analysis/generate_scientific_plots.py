#!/usr/bin/env python3
"""Generate shared scientific plots for DELTa deck and papers.

Also generates question-specific statistical figures used in the ML paper.
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
from matplotlib import rcParams


ROOT = Path(__file__).resolve().parent.parent
SUMMARY_JSON = ROOT / "analysis" / "delta_exploratory_summary.json"
STATE_CSV = ROOT / "analysis" / "delta_state_risk_scores.csv"
DOCKET_CSV = ROOT / "analysis" / "delta_top15_dockets.csv"
SRC_CSV = ROOT / "DELTa_2026-03-31-Public-Update.csv"
FIG_DIR = ROOT / "analysis" / "figures"
OUT_STATS_JSON = ROOT / "analysis" / "delta_policy_question_stats.json"


FINANCIAL_KEYWORDS = (
    "collateral",
    "letter of credit",
    "credit",
    "deposit",
    "ciac",
    "guarant",
    "security",
    "upfront capacity",
    "surety",
    "contribution",
    "advance",
)

TRANSITION_KEYWORDS = (
    "clean energy",
    "renewable",
    "transition",
    "interruptible",
    "demand response",
    "tou",
    "environmental improvement",
    "storage",
    "carbon-free",
    "clean transition",
)


def configure_style() -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    rcParams.update(
        {
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "figure.dpi": 220,
        }
    )


def load_summary() -> dict:
    return json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))


def load_state_scores() -> list[dict]:
    rows = []
    with STATE_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_dockets() -> list[dict]:
    rows = []
    with DOCKET_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def normalize(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").split())


def parse_float(value: str) -> float | None:
    if not value:
        return None
    text = str(value).strip().upper()
    if text in {"", "N/A", "NA", "NO", "NOT SPECIFIED", "REDACTED IN PROPOSAL"}:
        return None
    m = re.search(r"\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def has_signal(value: str) -> bool:
    text = normalize(value).lower()
    if not text:
        return False
    return text not in {
        "not specified",
        "no",
        "n/a",
        "na",
        "tariff pending",
        "service rules pending",
    }


def extract_first_number(value: str) -> float | None:
    nums = re.findall(r"\d+(?:\.\d+)?", value or "")
    return float(nums[0]) if nums else None


def clean_status(value: str) -> str:
    t = normalize(value)
    lo = t.lower()
    if lo.startswith("approved"):
        return "Approved"
    if "pending" in lo or "proposed" in lo:
        return "Proposed / Pending"
    return t or "Unknown"


def is_pending(status: str) -> bool:
    lo = (status or "").lower()
    return "pending" in lo or "proposed" in lo


def contains_any(value: str, keywords: tuple[str, ...]) -> bool:
    text = normalize(value).lower()
    if not has_signal(text):
        return False
    return any(k in text for k in keywords)


def split_dockets(text: str) -> list[str]:
    t = normalize(text)
    if not t or t.lower() in {"docket not included", "not specified"}:
        return ["Unspecified Docket"]
    return [x for x in re.split(r"\s*[;,]\s*", t) if x]


def parse_delta_rows() -> list[dict]:
    with SRC_CSV.open("r", encoding="utf-8", newline="") as f:
        lines = f.readlines()

    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("State,Utility,Tariff or Service Rule"):
            header_idx = i
            break

    reader = csv.DictReader(lines[header_idx:])
    rows = []
    for r in reader:
        rows.append(
            {
                "state": normalize(r.get("State", "")),
                "status": clean_status(r.get("Status", "")),
                "minDemandMw": parse_float(r.get("Minimum Demand (MW)", "")),
                "contractTerm": normalize(r.get("Contract Term", "")),
                "minBill": normalize(r.get("Minimum Bill as a % of Contract Capacity", "")),
                "financial": normalize(r.get("Financial Assurance & Contributions", "")),
                "transition": normalize(r.get("Energy Transition Provisions", "")),
                "docket": normalize(r.get("Docket(s) Link", "")),
            }
        )
    return rows


def style_axes(ax):
    ax.grid(True, axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)


def ci95_proportion(p: float, n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.96 * math.sqrt((p * (1.0 - p)) / n)


def plot_status(summary: dict):
    counts = summary["statusCounts"]
    total = int(summary["totals"]["rows"])
    labels = ["Approved", "Proposed/Pending"]
    raw_values = [counts.get("Approved", 0), counts.get("Proposed / Pending", 0)]
    values = [100.0 * v / total for v in raw_values]
    errors = [100.0 * ci95_proportion(v / total, total) for v in raw_values]
    colors = ["#2ca02c", "#ff7f0e"]

    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(labels, values, color=colors, yerr=errors, capsize=5, ecolor="#333333")
    style_axes(ax)
    ax.set_ylabel("Share of records (%)")
    ax.set_ylim(0, 100)
    ax.set_title("DELTa Status Distribution (with 95% CI)")
    for b, pct, cnt in zip(bars, values, raw_values):
        ax.text(
            b.get_x() + b.get_width() / 2.0,
            pct + 1.2,
            f"{pct:.1f}% (n={cnt})",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.text(0.02, -0.18, f"Sample size: n={total}", transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "status_distribution.png", dpi=320)
    plt.close(fig)


def plot_regions(summary: dict):
    region_counts = summary["marketRegionCounts"]
    total = int(summary["totals"]["rows"])
    order = ["PJM", "SPP", "CAISO", "MISO", "NYISO", "ERCOT"]
    raw_values = [region_counts.get(k, 0) for k in order]
    values = [100.0 * v / total for v in raw_values]

    fig, ax = plt.subplots(figsize=(8, 4.8))
    bars = ax.bar(order, values, color="#1f77b4")
    style_axes(ax)
    ax.set_ylabel("Share of DELTa records (%)")
    ax.set_title("ISO/RTO Linkage Coverage in DELTa")
    for b, pct, cnt in zip(bars, values, raw_values):
        ax.text(b.get_x() + b.get_width() / 2.0, pct + 0.4, f"{pct:.1f}%\n(n={cnt})", ha="center", va="bottom", fontsize=8)
    ax.text(0.02, -0.18, "Note: categories are not mutually exclusive.", transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "region_linkage.png", dpi=320)
    plt.close(fig)


def plot_themes(summary: dict):
    total = int(summary["totals"]["rows"])
    items = list(summary["themeCounts"].items())[:6]
    labels = [k for k, _ in items][::-1]
    raw_values = [v for _, v in items][::-1]
    values = [100.0 * v / total for v in raw_values]

    fig, ax = plt.subplots(figsize=(9, 5.2))
    bars = ax.barh(labels, values, color="#9467bd")
    style_axes(ax)
    ax.set_xlabel("Share of records (%)")
    ax.set_title("Most Frequent Rate-Design Themes in DELTa")
    for b, pct, cnt in zip(bars, values, raw_values):
        ax.text(pct + 0.4, b.get_y() + b.get_height() / 2.0, f"{pct:.1f}% (n={cnt})", va="center", fontsize=9)
    ax.text(0.02, -0.12, f"Sample size: n={total}", transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "top_themes.png", dpi=320)
    plt.close(fig)


def plot_state_risk(states: list[dict]):
    top = states[:10]
    labels = [r["state"] for r in top]
    values = [float(r["entryFrictionRiskScore"]) for r in top]

    fig, ax = plt.subplots(figsize=(10, 4.8))
    bars = ax.bar(labels, values, color="#d62728")
    style_axes(ax)
    ax.set_ylabel("Risk score (0-100)")
    ax.set_ylim(0, 100)
    ax.set_title("Top 10 States by Entry-Friction Risk Score")
    ax.tick_params(axis="x", rotation=25)
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2.0, v + 0.8, f"{v:.1f}", ha="center", va="bottom", fontsize=9)
    ax.text(0.02, -0.18, "Composite index from demand threshold, minimum bill, assurance, term, exit controls, and transition offsets.", transform=ax.transAxes, fontsize=8.8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "state_risk_scores.png", dpi=320)
    plt.close(fig)


def plot_top_dockets(dockets: list[dict]):
    top = dockets[:10]
    labels = [d["docket"] for d in top]
    short_labels = [lb if len(lb) <= 38 else lb[:35] + "..." for lb in labels]
    values = [float(d["impactScore"]) for d in top]

    fig, ax = plt.subplots(figsize=(10, 5.4))
    bars = ax.barh(short_labels[::-1], values[::-1], color="#17becf")
    style_axes(ax)
    ax.set_xlabel("Consequence score")
    ax.set_xlim(0, max(values) + 8)
    ax.set_title("Top 10 Consequential Dockets")
    for b, v in zip(bars, values[::-1]):
        ax.text(v + 0.4, b.get_y() + b.get_height() / 2.0, f"{v:.1f}", va="center", fontsize=9)
    ax.text(0.02, -0.12, "Score combines footprint, threshold scale, pending uncertainty, and policy-control breadth.", transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "top_dockets.png", dpi=320)
    plt.close(fig)


def top_states_high_min_demand(rows: list[dict], min_records: int = 2) -> list[dict]:
    by_state: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        v = row["minDemandMw"]
        if v is not None and row["state"]:
            by_state[row["state"]].append(float(v))

    stats = []
    for state, values in by_state.items():
        n = len(values)
        if n < min_records:
            continue
        med = float(median(values))
        share_50 = 100.0 * sum(1 for x in values if x >= 50.0) / n
        stats.append(
            {
                "state": state,
                "recordsWithThreshold": n,
                "medianMinDemandMw": round(med, 2),
                "shareAtLeast50Pct": round(share_50, 1),
            }
        )
    stats.sort(key=lambda x: (-x["medianMinDemandMw"], -x["recordsWithThreshold"], x["state"]))
    if len(stats) < 8 and min_records > 1:
        return top_states_high_min_demand(rows, min_records=1)
    return stats


def plot_high_min_demand_states(stats: list[dict]) -> None:
    top = stats[:10]
    labels = [r["state"] for r in top][::-1]
    values = [r["medianMinDemandMw"] for r in top][::-1]
    samples = [r["recordsWithThreshold"] for r in top][::-1]
    shares = [r["shareAtLeast50Pct"] for r in top][::-1]

    fig, ax = plt.subplots(figsize=(9.8, 5.4))
    bars = ax.barh(labels, values, color="#1f77b4")
    style_axes(ax)
    ax.set_xlabel("Median minimum-demand threshold (MW)")
    ax.set_title("Q1. States Imposing the Highest Minimum-Demand Thresholds")
    for b, mw, n, s50 in zip(bars, values, samples, shares):
        ax.text(mw + 1.0, b.get_y() + b.get_height() / 2.0, f"{mw:.1f} MW | n={n} | >=50 MW: {s50:.0f}%", va="center", fontsize=8.8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "q1_high_min_demand_states.png", dpi=320)
    plt.close(fig)


def state_share(rows: list[dict], key_fn, min_records: int = 1) -> list[dict]:
    total = Counter()
    hit = Counter()
    for row in rows:
        state = row["state"]
        if not state:
            continue
        total[state] += 1
        if key_fn(row):
            hit[state] += 1

    out = []
    for state, n in total.items():
        if n < min_records:
            continue
        h = hit[state]
        out.append({"state": state, "records": n, "hits": h, "sharePct": round(100.0 * h / n, 1)})
    out.sort(key=lambda x: (-x["sharePct"], -x["records"], x["state"]))
    return out


def plot_financial_protections(stats: list[dict]) -> None:
    top = stats[:12]
    labels = [r["state"] for r in top][::-1]
    values = [r["sharePct"] for r in top][::-1]
    samples = [r["records"] for r in top][::-1]
    hits = [r["hits"] for r in top][::-1]

    fig, ax = plt.subplots(figsize=(10, 5.8))
    bars = ax.barh(labels, values, color="#d62728")
    style_axes(ax)
    ax.set_xlabel("Share of records with financial protections (%)")
    ax.set_xlim(0, 100)
    ax.set_title("Q2. Where Utilities Require Collateral, CIAC, Deposits, or Similar")
    for b, pct, n, h in zip(bars, values, samples, hits):
        ax.text(pct + 1.0, b.get_y() + b.get_height() / 2.0, f"{pct:.1f}% (n={h}/{n})", va="center", fontsize=8.8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "q2_financial_protections_by_state.png", dpi=320)
    plt.close(fig)


def plot_contract_and_min_bill(rows: list[dict]) -> dict:
    n = len(rows)
    long_term = 0
    min_bill = 0
    both = 0

    for row in rows:
        years = extract_first_number(row["contractTerm"])
        is_long = years is not None and years >= 10.0
        has_min_bill = has_signal(row["minBill"])
        long_term += 1 if is_long else 0
        min_bill += 1 if has_min_bill else 0
        both += 1 if (is_long and has_min_bill) else 0

    either = long_term + min_bill - both
    labels = [">=10-year term", "Minimum bill", "Both", "Either"]
    counts = [long_term, min_bill, both, either]
    pcts = [100.0 * c / n for c in counts]

    fig, ax = plt.subplots(figsize=(9.2, 5.2))
    bars = ax.bar(labels, pcts, color=["#4c78a8", "#f58518", "#54a24b", "#b279a2"])
    style_axes(ax)
    ax.set_ylabel("Share of DELTa records (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Q3. Prevalence of Long Terms and Minimum-Bill Requirements")
    for b, pct, c in zip(bars, pcts, counts):
        ax.text(b.get_x() + b.get_width() / 2.0, pct + 1.0, f"{pct:.1f}%\n(n={c})", ha="center", va="bottom", fontsize=9)
    ax.text(0.02, -0.16, f"Sample size: n={n}", transform=ax.transAxes, fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "q3_contract_term_min_bill_prevalence.png", dpi=320)
    plt.close(fig)

    return {
        "totalRows": n,
        "longTermPct": round(pcts[0], 1),
        "minimumBillPct": round(pcts[1], 1),
        "bothPct": round(pcts[2], 1),
        "eitherPct": round(pcts[3], 1),
        "longTermN": long_term,
        "minimumBillN": min_bill,
        "bothN": both,
        "eitherN": either,
    }


def plot_transition_options(stats: list[dict]) -> None:
    top = stats[:12]
    labels = [r["state"] for r in top][::-1]
    values = [r["sharePct"] for r in top][::-1]
    samples = [r["records"] for r in top][::-1]
    hits = [r["hits"] for r in top][::-1]

    fig, ax = plt.subplots(figsize=(10, 5.8))
    bars = ax.barh(labels, values, color="#2ca02c")
    style_axes(ax)
    ax.set_xlabel("Share of records with transition or clean-energy provisions (%)")
    ax.set_xlim(0, 100)
    ax.set_title("Q4. Jurisdictions Pairing Large-Load Tariffs with Transition Options")
    for b, pct, n, h in zip(bars, values, samples, hits):
        ax.text(pct + 1.0, b.get_y() + b.get_height() / 2.0, f"{pct:.1f}% (n={h}/{n})", va="center", fontsize=8.8)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "q4_transition_clean_by_state.png", dpi=320)
    plt.close(fig)


def docket_pending_stats(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(lambda: {"total": 0, "pending": 0})
    for row in rows:
        pending = is_pending(row["status"])
        for docket in split_dockets(row["docket"]):
            grouped[docket]["total"] += 1
            grouped[docket]["pending"] += 1 if pending else 0

    out = []
    for docket, s in grouped.items():
        if s["pending"] <= 0:
            continue
        out.append(
            {
                "docket": docket,
                "total": s["total"],
                "pending": s["pending"],
                "nonPending": s["total"] - s["pending"],
                "pendingSharePct": round(100.0 * s["pending"] / s["total"], 1),
            }
        )
    out.sort(key=lambda x: (-x["pending"], -x["pendingSharePct"], -x["total"], x["docket"]))
    return out


def plot_pending_dockets(stats: list[dict]) -> None:
    top = stats[:12]
    labels_full = [d["docket"] for d in top]
    labels = [lb if len(lb) <= 36 else lb[:33] + "..." for lb in labels_full][::-1]
    pending = [d["pending"] for d in top][::-1]
    non_pending = [d["nonPending"] for d in top][::-1]
    share = [d["pendingSharePct"] for d in top][::-1]

    fig, ax = plt.subplots(figsize=(10.4, 6.2))
    ax.barh(labels, non_pending, color="#9ecae1", label="Non-pending records")
    ax.barh(labels, pending, left=non_pending, color="#ff7f0e", label="Pending records")
    style_axes(ax)
    ax.set_xlabel("Records mapped to docket")
    ax.set_title("Q5. Dockets with Active Policy Uncertainty (Pending Status)")
    ax.legend(loc="lower right")
    for i, (npv, pv, sp) in enumerate(zip(non_pending, pending, share)):
        ax.text(npv + pv + 0.05, i, f"pending: {pv} ({sp:.0f}%)", va="center", fontsize=8.6)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "q5_pending_dockets_uncertainty.png", dpi=320)
    plt.close(fig)


def build_policy_question_outputs(rows: list[dict]) -> dict:
    q1 = top_states_high_min_demand(rows, min_records=2)
    plot_high_min_demand_states(q1)

    q2 = state_share(rows, lambda r: contains_any(r["financial"], FINANCIAL_KEYWORDS), min_records=2)
    if len(q2) < 8:
        q2 = state_share(rows, lambda r: contains_any(r["financial"], FINANCIAL_KEYWORDS), min_records=1)
    plot_financial_protections(q2)

    q3 = plot_contract_and_min_bill(rows)

    q4 = state_share(rows, lambda r: contains_any(r["transition"], TRANSITION_KEYWORDS), min_records=2)
    if len(q4) < 8:
        q4 = state_share(rows, lambda r: contains_any(r["transition"], TRANSITION_KEYWORDS), min_records=1)
    plot_transition_options(q4)

    q5 = docket_pending_stats(rows)
    plot_pending_dockets(q5)

    financial_n = sum(1 for r in rows if contains_any(r["financial"], FINANCIAL_KEYWORDS))
    transition_n = sum(1 for r in rows if contains_any(r["transition"], TRANSITION_KEYWORDS))
    pending_n = sum(1 for r in rows if is_pending(r["status"]))

    out = {
        "totalRows": len(rows),
        "uniqueStates": len({r["state"] for r in rows if r["state"]}),
        "q1_topStatesByMedianMinDemand": q1[:10],
        "q2_financialProtection": {
            "rowsWithProtectionN": financial_n,
            "rowsWithProtectionPct": round(100.0 * financial_n / len(rows), 1),
            "topStatesByShare": q2[:12],
        },
        "q3_longTermAndMinimumBill": q3,
        "q4_transitionAndClean": {
            "rowsWithTransitionN": transition_n,
            "rowsWithTransitionPct": round(100.0 * transition_n / len(rows), 1),
            "statesWithAtLeastOne": len([x for x in q4 if x["hits"] > 0]),
            "topStatesByShare": q4[:12],
        },
        "q5_pendingDockets": {
            "pendingRowsN": pending_n,
            "pendingRowsPct": round(100.0 * pending_n / len(rows), 1),
            "docketsWithPendingN": len(q5),
            "topPendingDockets": q5[:12],
        },
    }
    OUT_STATS_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def main() -> None:
    configure_style()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    summary = load_summary()
    states = load_state_scores()
    dockets = load_dockets()
    delta_rows = parse_delta_rows()

    plot_status(summary)
    plot_regions(summary)
    plot_themes(summary)
    plot_state_risk(states)
    plot_top_dockets(dockets)
    build_policy_question_outputs(delta_rows)

    print(f"Wrote plots to {FIG_DIR}")
    print(f"Wrote question stats to {OUT_STATS_JSON}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate figures for the third industrial load flexibility practices paper."""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
from analyze_delta_dataset import extract_theme_counts, infer_regions, parse_rows  # noqa: E402

OUT = ROOT / "analysis" / "figures"
OUT.mkdir(exist_ok=True)


def save_methodology_flow():
    fig, ax = plt.subplots(figsize=(8.8, 2.9))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    boxes = [
        ("DELTa records\n(n=77)", 0.10, 0.67, "#e8f1fb"),
        ("Header detection\nand schema cleanup", 0.30, 0.67, "#e8f1fb"),
        ("Column-level\nfeature coding", 0.50, 0.67, "#fff1dd"),
        ("Counts, shares,\nand state groups", 0.70, 0.67, "#fff1dd"),
        ("Coding-rule\naudit", 0.30, 0.28, "#fff8d8"),
        ("Research-question\nfigures", 0.50, 0.28, "#e4f7e4"),
        ("Policy\ninterpretation", 0.70, 0.28, "#e4f7e4"),
    ]
    box_width = 0.17
    box_height = 0.18
    for text, x, y, color in boxes:
        rect = plt.Rectangle(
            (x - box_width / 2, y - box_height / 2),
            box_width,
            box_height,
            facecolor=color,
            edgecolor="#222222",
            linewidth=0.9,
            joinstyle="round",
        )
        ax.add_patch(rect)
        ax.text(x, y, text, ha="center", va="center", fontsize=9.5)

    arrows = [
        ((0.185, 0.67), (0.215, 0.67)),
        ((0.385, 0.67), (0.415, 0.67)),
        ((0.585, 0.67), (0.615, 0.67)),
        ((0.70, 0.58), (0.53, 0.37)),
        ((0.585, 0.28), (0.615, 0.28)),
        ((0.415, 0.28), (0.385, 0.28)),
        ((0.30, 0.37), (0.30, 0.58)),
    ]
    for start, end in arrows:
        ax.annotate(
            "",
            xy=end,
            xytext=start,
            arrowprops={"arrowstyle": "-|>", "lw": 1.3, "color": "#222222", "shrinkA": 0, "shrinkB": 0},
        )

    fig.tight_layout(pad=0.2)
    fig.savefig(OUT / "third_paper_methodology.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def pct(value: int, total: int) -> float:
    return 100.0 * value / total if total else 0.0


def presence(text: str) -> bool:
    return bool(text) and text.strip().lower() not in {"", "not specified", "no", "na", "n/a"}


def save_aspects(rows):
    counts = extract_theme_counts(rows)
    items = list(counts.items())[:8]
    labels = [k for k, _ in items][::-1]
    vals = [v for _, v in items][::-1]

    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    ax.barh(labels, vals, color="#4c78a8")
    ax.set_xlabel("Records with feature/theme")
    ax.set_title("Key aspects of emerging industrial rates and programs")
    ax.grid(axis="x", alpha=0.25)
    for y, v in enumerate(vals):
        ax.text(v + 0.8, y, f"{v} ({pct(v, len(rows)):.0f}%)", va="center", fontsize=8)
    ax.set_xlim(0, max(vals) + 9)
    fig.tight_layout()
    fig.savefig(OUT / "third_paper_key_aspects.png", dpi=180)
    plt.close(fig)


def save_state_distribution(rows):
    by_state = defaultdict(Counter)
    for row in rows:
        by_state[row.state][row.status] += 1
    top = sorted(by_state.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:15]
    states = [s for s, _ in top][::-1]
    approved = [c.get("Approved", 0) for _, c in top][::-1]
    pending = [c.get("Proposed / Pending", 0) for _, c in top][::-1]

    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.barh(states, approved, color="#54a24b", label="Approved")
    ax.barh(states, pending, left=approved, color="#f58518", label="Proposed / Pending")
    ax.set_xlabel("DELTa records")
    ax.set_title("Overall dataset distribution by state (top 15 states)")
    ax.grid(axis="x", alpha=0.25)
    ax.legend(loc="lower right", frameon=False)
    for y, (a, p) in enumerate(zip(approved, pending)):
        total = a + p
        ax.text(total + 0.1, y, str(total), va="center", fontsize=8)
    ax.set_xlim(0, max(a + p for a, p in zip(approved, pending)) + 1.5)
    fig.tight_layout()
    fig.savefig(OUT / "third_paper_state_distribution.png", dpi=180)
    plt.close(fig)


def save_feature_design(rows):
    n = len(rows)
    metrics = [
        ("Participation", "Transition / clean-energy", sum(presence(r.transition) for r in rows)),
        ("Participation", "Interruptibility or DR", sum("interrupt" in (r.narrative + r.transition).lower() or "demand response" in (r.narrative + r.transition).lower() for r in rows)),
        ("Performance", "Minimum load factor", sum(r.min_load_factor_pct is not None for r in rows)),
        ("Performance", "Load ramp period", sum(presence(r.load_ramp) for r in rows)),
        ("Scalability", "Financial assurance", sum(presence(r.financial_assurance) for r in rows)),
        ("Scalability", "Contract modification", sum(presence(r.modification) for r in rows)),
        ("Scalability", "Minimum bill", sum(presence(r.min_bill) for r in rows)),
        ("Scalability", "Study-cost recovery", sum(presence(r.study_costs) for r in rows)),
    ]
    labels = [m[1] for m in metrics][::-1]
    vals = [pct(m[2], n) for m in metrics][::-1]
    colors = [{"Participation": "#4c78a8", "Performance": "#f58518", "Scalability": "#54a24b"}[m[0]] for m in metrics][::-1]

    fig, ax = plt.subplots(figsize=(7.6, 4.3))
    ax.barh(labels, vals, color=colors)
    ax.set_xlabel("Share of DELTa records (%)")
    ax.set_title("Design features linked to participation, performance, and scalability")
    ax.grid(axis="x", alpha=0.25)
    for y, (v, metric) in enumerate(zip(vals, metrics[::-1])):
        ax.text(v + 1.2, y, f"{v:.1f}% (n={metric[2]})", va="center", fontsize=8)
    ax.set_xlim(0, max(vals) + 14)
    handles = [plt.Line2D([0], [0], color=c, lw=8) for c in ["#4c78a8", "#f58518", "#54a24b"]]
    ax.legend(handles, ["Participation", "Performance", "Scalability"], loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "third_paper_design_features.png", dpi=180)
    plt.close(fig)


def save_actor_segments(rows):
    utility_types = Counter(r.utility_type or "Unknown" for r in rows)
    sectors = Counter(r.sector or "Unknown" for r in rows)
    regions = Counter()
    explicit_aggregator_mentions = 0
    for row in rows:
        for region in infer_regions(row.iso_rto):
            regions[region] += 1
        text = (row.narrative + " " + row.transition + " " + row.modification).lower()
        if "aggregator" in text or "aggregation" in text:
            explicit_aggregator_mentions += 1

    fig, axes = plt.subplots(3, 1, figsize=(8.2, 7.2))
    panels = [
        (axes[0], utility_types.most_common(5), "Utility types represented"),
        (axes[1], regions.most_common(6), "ISO/RTO or market-region linkages"),
        (axes[2], sectors.most_common(4) + [("Explicit aggregator mentions", explicit_aggregator_mentions)], "Industrial customer segments"),
    ]
    panel_colors = ["#4c78a8", "#f58518", "#54a24b"]
    for ax, items, title in panels:
        labels = [k.replace("General Commercial & Industrial Customers", "General C&I Customers") for k, _ in items][::-1]
        vals = [v for _, v in items][::-1]
        color = panel_colors[list(axes).index(ax)]
        ax.barh(labels, vals, color=color, alpha=0.9)
        ax.set_title(title, fontsize=10, loc="left", pad=4)
        ax.grid(axis="x", alpha=0.22)
        ax.set_axisbelow(True)
        for y, v in enumerate(vals):
            ax.text(v + max(vals) * 0.015 + 0.2, y, str(v), va="center", fontsize=8.5)
        ax.set_xlim(0, max(vals) + max(4, max(vals) * 0.12))
        ax.tick_params(axis="y", labelsize=8.5)
        ax.tick_params(axis="x", labelsize=8)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
    axes[-1].set_xlabel("DELTa records or text mentions")
    fig.suptitle("Actors, market regions, and industrial customer segments represented in DELTa", y=0.995, fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.965], h_pad=1.35)
    fig.savefig(OUT / "third_paper_actor_segments.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def main():
    rows = parse_rows()
    save_methodology_flow()
    save_aspects(rows)
    save_state_distribution(rows)
    save_feature_design(rows)
    save_actor_segments(rows)
    for name in [
        "third_paper_methodology.png",
        "third_paper_key_aspects.png",
        "third_paper_state_distribution.png",
        "third_paper_design_features.png",
        "third_paper_actor_segments.png",
    ]:
        print(OUT / name)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate paper figures from FlexDC and NAICS analysis outputs."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS = ROOT / "analysis"
FIG_DIR = ANALYSIS / "figures"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def currency_k(x: float) -> float:
    return x / 1000.0


def fig1_regional_midpoint_bar(earnings: dict) -> None:
    rows = earnings["rows"]
    regions = [r["regionId"] for r in rows]
    mids = [currency_k(r["annualValueMidpoint"]) for r in rows]

    plt.figure(figsize=(8.5, 4.8))
    bars = plt.bar(regions, mids, color="#2A9D8F")
    plt.ylabel("Annual midpoint earnings (thousand USD)")
    plt.title("Baseline calibrated annual midpoint earnings by region")
    plt.grid(axis="y", alpha=0.2)
    for b, v in zip(bars, mids):
        plt.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.1f}", ha="center", va="bottom", fontsize=8)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "fig1_regional_midpoint_bar.png", dpi=220)
    plt.close()


def fig2_regional_range(earnings: dict) -> None:
    rows = earnings["rows"]
    regions = [r["regionId"] for r in rows]
    low = [currency_k(r["annualValueLow"]) for r in rows]
    high = [currency_k(r["annualValueHigh"]) for r in rows]
    mid = [currency_k(r["annualValueMidpoint"]) for r in rows]

    plt.figure(figsize=(8.7, 5.0))
    y = range(len(regions))
    plt.hlines(y=y, xmin=low, xmax=high, color="#264653", linewidth=3)
    plt.plot(mid, y, "o", color="#E76F51")
    plt.yticks(y, regions)
    plt.xlabel("Annual gross earnings (thousand USD)")
    plt.title("Regional low-high earnings ranges with midpoint markers")
    plt.grid(axis="x", alpha=0.2)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "fig2_regional_range_lh.png", dpi=220)
    plt.close()


def fig3_scenario_metrics(flex: dict) -> None:
    scenarios = flex["scenarios"]
    names = list(scenarios.keys())
    deliverability = [scenarios[s]["simMetrics"]["deliverabilityFactor"] * 100 for s in names]
    qos = [scenarios[s]["simMetrics"]["qosViolationRateByType"] * 100 for s in names]

    plt.figure(figsize=(7.2, 4.8))
    x = range(len(names))
    width = 0.35
    plt.bar([i - width / 2 for i in x], deliverability, width=width, label="Deliverability (%)", color="#457B9D")
    plt.bar([i + width / 2 for i in x], qos, width=width, label="QoS violation ratio (%)", color="#E63946")
    plt.xticks(list(x), names)
    plt.ylabel("Percent")
    plt.title("Scenario calibration metrics (FlexDC-Sim)")
    plt.legend()
    plt.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "fig3_scenario_metrics.png", dpi=220)
    plt.close()


def fig4_top10_naics(naics: dict) -> None:
    top10 = naics["top10"]
    labels = [f"{r['naics']}" for r in top10]
    values = [currency_k(r["bestRegionAnnualMidpointUSD"]) for r in top10]

    plt.figure(figsize=(9.0, 5.2))
    plt.bar(labels, values, color="#8AB17D")
    plt.xticks(rotation=35, ha="right")
    plt.ylabel("Best-region annual midpoint (thousand USD)")
    plt.title("Top-10 NAICS large-load opportunities")
    plt.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "fig4_top10_naics.png", dpi=220)
    plt.close()


def fig5_segment_avg(naics: dict) -> None:
    rows = naics["allRows"]
    df = pd.DataFrame(rows)
    grp = (
        df.groupby("segment", as_index=False)["bestRegionAnnualMidpointUSD"]
        .mean()
        .sort_values("bestRegionAnnualMidpointUSD", ascending=False)
    )

    plt.figure(figsize=(9.0, 5.2))
    plt.bar(grp["segment"], grp["bestRegionAnnualMidpointUSD"].apply(currency_k), color="#F4A261")
    plt.xticks(rotation=30, ha="right")
    plt.ylabel("Average best-region midpoint (thousand USD)")
    plt.title("Average midpoint earnings by NAICS segment")
    plt.grid(axis="y", alpha=0.2)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "fig5_segment_avg.png", dpi=220)
    plt.close()


def fig6_flexible_mw_scatter(naics: dict) -> None:
    rows = naics["allRows"]
    x = [r["effectiveFlexibleMW"] for r in rows]
    y = [currency_k(r["bestRegionAnnualMidpointUSD"]) for r in rows]

    plt.figure(figsize=(7.4, 5.2))
    plt.scatter(x, y, c="#6D597A", alpha=0.8)
    plt.xlabel("Effective flexible MW")
    plt.ylabel("Best-region midpoint (thousand USD)")
    plt.title("NAICS opportunity scaling with effective flexible MW")
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(FIG_DIR / "fig6_flexible_mw_scatter.png", dpi=220)
    plt.close()


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    flex = load_json(ANALYSIS / "flexdc_region_results.json")
    earnings = load_json(ANALYSIS / "data_center_earnings_summary.json")
    naics = load_json(ANALYSIS / "naics_large_load_results.json")

    fig1_regional_midpoint_bar(earnings)
    fig2_regional_range(earnings)
    fig3_scenario_metrics(flex)
    fig4_top10_naics(naics)
    fig5_segment_avg(naics)
    fig6_flexible_mw_scatter(naics)

    print("Wrote figures:")
    for p in sorted(FIG_DIR.glob("fig*.png")):
        print(p)


if __name__ == "__main__":
    main()

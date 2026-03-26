#!/usr/bin/env python3
"""Run NAICS large-load earnings screening from calibrated regional results."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FLEX_RESULTS = ROOT / "analysis" / "flexdc_region_results.json"
SHORTLIST = ROOT / "analysis" / "naics_large_load_shortlist.json"
OUT_JSON = ROOT / "analysis" / "naics_large_load_results.json"
OUT_CSV = ROOT / "analysis" / "naics_large_load_results.csv"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    flex = load_json(FLEX_RESULTS)
    shortlist = load_json(SHORTLIST)

    scenario = flex.get("currentScenario", "baseline")
    scenario_payload = flex["scenarios"][scenario]
    regions = scenario_payload["regions"]

    region_midpoint_per_mw = {}
    for region_id, region_data in regions.items():
        low = float(region_data["annualValueLow"])
        high = float(region_data["annualValueHigh"])
        midpoint = (low + high) / 2.0
        # FlexDC baseline model is normalized to a 10 MW portfolio
        region_midpoint_per_mw[region_id] = midpoint / 10.0

    rows = []
    for code in shortlist["codes"]:
        base_mw = float(code["typical_load_mw"])
        flex_factor = float(code["flexibility_factor"])
        participation = float(code["participation_factor"])
        effective_mw = base_mw * flex_factor * participation

        by_region = {}
        for region_id, per_mw in region_midpoint_per_mw.items():
            annual_midpoint = per_mw * effective_mw
            by_region[region_id] = round(annual_midpoint, 2)

        best_region, best_value = max(by_region.items(), key=lambda kv: kv[1])

        rows.append(
            {
                "naics": code["naics"],
                "title": code["title"],
                "segment": code["segment"],
                "typicalLoadMW": base_mw,
                "effectiveFlexibleMW": round(effective_mw, 3),
                "bestRegion": best_region,
                "bestRegionAnnualMidpointUSD": round(best_value, 2),
                "regionalAnnualMidpointUSD": by_region,
            }
        )

    rows.sort(key=lambda r: r["bestRegionAnnualMidpointUSD"], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx

    top10 = rows[:10]

    result = {
        "method": "NAICS large-load shortlist screening using FlexDC-calibrated regional midpoint earnings",
        "scenario": scenario,
        "shortlistCount": len(shortlist["codes"]),
        "assumptions": {
            "regionalMidpointPerMWDerivedFrom": "analysis/flexdc_region_results.json earningsSummary (baseline calibrated)",
            "effectiveFlexibleMW": "typical_load_mw * flexibility_factor * participation_factor",
        },
        "top10": top10,
        "allRows": rows,
    }

    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
        f.write("\n")

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "naics",
                "title",
                "segment",
                "typical_load_mw",
                "effective_flexible_mw",
                "best_region",
                "best_region_annual_midpoint_usd",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r["rank"],
                    r["naics"],
                    r["title"],
                    r["segment"],
                    r["typicalLoadMW"],
                    r["effectiveFlexibleMW"],
                    r["bestRegion"],
                    r["bestRegionAnnualMidpointUSD"],
                ]
            )

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")
    print("Top 10 NAICS opportunities:")
    for r in top10:
        print(
            f"{r['rank']}. {r['naics']} {r['title']} | best={r['bestRegion']} | "
            f"mid=${r['bestRegionAnnualMidpointUSD']:.0f}"
        )


if __name__ == "__main__":
    main()

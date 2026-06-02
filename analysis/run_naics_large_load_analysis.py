#!/usr/bin/env python3
"""Run NAICS large-load earnings screening from market program rates."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
RATES_FILE = ROOT / "data" / "rates.json"
SHORTLIST = ROOT / "analysis" / "naics_large_load_shortlist.json"
OUT_JSON = ROOT / "analysis" / "naics_large_load_results.json"
OUT_CSV = ROOT / "analysis" / "naics_large_load_results.csv"


# Annualized market exposure assumptions used to convert published rate units.
DEFAULT_ANNUAL_HOURS = {
    "ancillary": 350,
    "energy": 550,
    "emergency": 60,
    "capacityDays": 25,
    "capacityMonths": 12,
}

# Reflects that all categories generally cannot be fully stacked simultaneously.
DEFAULT_STACKABILITY_FACTOR = 0.65


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def estimate_program_annual_value(
    program: dict[str, Any],
    effective_flexible_mw: float,
    annual_hours: dict[str, float],
) -> tuple[float, float]:
    category = str(program.get("marketCategory") or "energy")
    rate_min = float(program.get("rate_min") or 0)
    rate_max = float(program.get("rate_max") or rate_min)
    unit = str(program.get("rate_unit") or "").lower()

    if effective_flexible_mw <= 0 or (rate_min <= 0 and rate_max <= 0):
        return 0.0, 0.0

    if "/mwh" in unit or "/mw-hr" in unit or "/mw per hour" in unit:
        hours = float(annual_hours.get(category, 0))
        return rate_min * effective_flexible_mw * hours, rate_max * effective_flexible_mw * hours
    if "/mw-day" in unit:
        days = float(annual_hours.get("capacityDays", 0))
        return rate_min * effective_flexible_mw * days, rate_max * effective_flexible_mw * days
    if "/kw-month" in unit:
        months = float(annual_hours.get("capacityMonths", 0))
        return rate_min * effective_flexible_mw * 1000 * months, rate_max * effective_flexible_mw * 1000 * months
    return 0.0, 0.0


def compute_region_annual_midpoint(
    region: dict[str, Any],
    effective_flexible_mw: float,
    annual_hours: dict[str, float],
    stackability_factor: float,
) -> float:
    best_by_category: dict[str, dict[str, Any]] = {}

    for program in region.get("programs", []):
        min_size_kw = float(program.get("minSize_kW") or 0)
        if min_size_kw > 0 and effective_flexible_mw * 1000 < min_size_kw:
            continue

        low, high = estimate_program_annual_value(program, effective_flexible_mw, annual_hours)
        midpoint = (low + high) / 2.0
        if midpoint <= 0:
            continue

        category = str(program.get("marketCategory") or "other")
        existing = best_by_category.get(category)
        if existing is None or midpoint > existing["midpoint"]:
            best_by_category[category] = {
                "midpoint": midpoint,
                "programName": str(program.get("name") or "Unknown"),
            }

    gross_midpoint = sum(item["midpoint"] for item in best_by_category.values())
    return gross_midpoint * stackability_factor


def main() -> None:
    rates = load_json(RATES_FILE)
    shortlist = load_json(SHORTLIST)

    region_data = rates.get("regions", {})
    regions = sorted(region_data.keys())

    rows = []
    for code in shortlist["codes"]:
        base_mw = float(code["typical_load_mw"])
        flex_factor = float(code["flexibility_factor"])
        participation = float(code["participation_factor"])
        effective_mw = base_mw * flex_factor * participation

        by_region: dict[str, float] = {}
        for region_id in regions:
            region = region_data.get(region_id, {})
            annual_midpoint = compute_region_annual_midpoint(
                region,
                effective_mw,
                DEFAULT_ANNUAL_HOURS,
                DEFAULT_STACKABILITY_FACTOR,
            )
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

    rows.sort(key=lambda row: row["bestRegionAnnualMidpointUSD"], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row["rank"] = idx

    top10 = rows[:10]

    result = {
        "method": "NAICS large-load shortlist screening using market-program annualized earnings from rates.json",
        "usesFlexDCSimDirectlyPerNAICS": False,
        "flexdcUsage": "None: region values are computed directly from market program rates, units, eligibility thresholds, and annualized exposure assumptions.",
        "scenario": "market-derived",
        "shortlistCount": len(shortlist["codes"]),
        "assumptions": {
            "sourceRates": "data/rates.json region programs",
            "effectiveFlexibleMW": "typical_load_mw * flexibility_factor * participation_factor",
            "annualHours": DEFAULT_ANNUAL_HOURS,
            "stackabilityFactor": DEFAULT_STACKABILITY_FACTOR,
            "categorySelection": "highest midpoint annual value program per marketCategory, then stacked",
            "eligibility": "program included only when effectiveFlexibleMW * 1000 >= minSize_kW",
        },
        "top10": top10,
        "allRows": rows,
    }

    with OUT_JSON.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")

    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
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
        for row in rows:
            writer.writerow(
                [
                    row["rank"],
                    row["naics"],
                    row["title"],
                    row["segment"],
                    row["typicalLoadMW"],
                    row["effectiveFlexibleMW"],
                    row["bestRegion"],
                    row["bestRegionAnnualMidpointUSD"],
                ]
            )

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")
    print("Top 10 NAICS opportunities:")
    for row in top10:
        print(
            f"{row['rank']}. {row['naics']} {row['title']} | best={row['bestRegion']} | "
            f"mid=${row['bestRegionAnnualMidpointUSD']:.0f}"
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build dashboard-ready DELTa summary JSON from the public update CSV."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SRC_CSV = ROOT / "DELTa_2026-03-31-Public-Update.csv"
OUT_JSON = ROOT / "data" / "delta_summary.json"

REGION_KEYWORDS = {
    "CAISO": ["CAISO"],
    "PJM": ["PJM"],
    "ERCOT": ["ERCOT"],
    "MISO": ["MISO"],
    "ISONE": ["ISO-NE", "ISO NE", "ISONE", "NEW ENGLAND ISO"],
    "NYISO": ["NYISO"],
    "SPP": ["SPP", "SOUTHWEST POWER POOL"],
}


def parse_float(value: str) -> float | None:
    if not value:
        return None
    text = value.strip().upper()
    if text in {"NOT SPECIFIED", "NO", "", "N/A", "NA"}:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def infer_regions(iso_rto: str) -> list[str]:
    text = (iso_rto or "").upper()
    matched = []
    for region_id, keywords in REGION_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            matched.append(region_id)
    return matched


def clean_status(value: str) -> str:
    text = (value or "").strip()
    if text.lower().startswith("approved"):
        return "Approved"
    if "pending" in text.lower() or "proposed" in text.lower():
        return "Proposed / Pending"
    return text or "Unknown"


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def main() -> None:
    rows = []
    with SRC_CSV.open("r", encoding="utf-8", newline="") as handle:
        lines = handle.readlines()

    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("State,Utility,Tariff or Service Rule"):
            header_idx = i
            break

    filtered_text = "".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(filtered_text))
    for raw in reader:
        status = clean_status(raw.get("Status", ""))
        min_demand = parse_float(raw.get("Minimum Demand (MW)", ""))
        load_factor = parse_float(raw.get("Minimum Load Factor", ""))
        regions = infer_regions(raw.get("ISO/RTO", ""))

        rows.append(
            {
                "state": (raw.get("State") or "").strip(),
                "utility": (raw.get("Utility") or "").strip(),
                "tariff": (raw.get("Tariff or Service Rule") or "").strip(),
                "status": status,
                "year": int(parse_float(raw.get("Year", "")) or 0),
                "lastUpdated": (raw.get("Last Updated in DELTa") or "").strip(),
                "sector": (raw.get("Sector or Segment") or "").strip(),
                "minimumDemandMw": min_demand,
                "minimumLoadFactorPct": load_factor,
                "utilityType": (raw.get("Utility Type") or "").strip(),
                "isoRto": (raw.get("ISO/RTO") or "").strip(),
                "regions": regions,
                "contractTerm": (raw.get("Contract Term") or "").strip(),
                "energyTransitionProvisions": (raw.get("Energy Transition Provisions") or "").strip(),
            }
        )

    status_counter = Counter(row["status"] for row in rows)
    year_counter = Counter(row["year"] for row in rows if row["year"])
    state_counter = Counter(row["state"] for row in rows if row["state"])

    by_region_counts = defaultdict(lambda: {"count": 0, "approved": 0, "pending": 0, "minDemandValues": []})
    for row in rows:
        for region in row["regions"]:
            stats = by_region_counts[region]
            stats["count"] += 1
            if row["status"] == "Approved":
                stats["approved"] += 1
            elif row["status"] == "Proposed / Pending":
                stats["pending"] += 1
            if row["minimumDemandMw"] is not None:
                stats["minDemandValues"].append(row["minimumDemandMw"])

    by_region = []
    for region_id, stats in sorted(by_region_counts.items()):
        med = median(stats["minDemandValues"])
        by_region.append(
            {
                "regionId": region_id,
                "count": stats["count"],
                "approved": stats["approved"],
                "pending": stats["pending"],
                "medianMinimumDemandMw": round(med, 2) if med is not None else None,
            }
        )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCsv": str(SRC_CSV.name),
        "totals": {
            "rows": len(rows),
            "approved": status_counter.get("Approved", 0),
            "pending": status_counter.get("Proposed / Pending", 0),
        },
        "byStatus": [
            {"status": status, "count": count}
            for status, count in status_counter.most_common()
        ],
        "byYear": [
            {"year": int(year), "count": count}
            for year, count in sorted(year_counter.items())
        ],
        "topStates": [
            {"state": state, "count": count}
            for state, count in state_counter.most_common(12)
        ],
        "byRegion": by_region,
        "rows": rows,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    print(f"Wrote {OUT_JSON}")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()

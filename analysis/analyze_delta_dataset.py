#!/usr/bin/env python3
"""Exploratory statistical + docket narrative analysis for DELTa public update CSV."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent.parent
SRC_CSV = ROOT / "DELTa_2026-03-31-Public-Update.csv"
OUT_JSON = ROOT / "analysis" / "delta_exploratory_summary.json"
OUT_MD = ROOT / "analysis" / "delta_exploratory_summary.md"


REGION_KEYWORDS = {
    "CAISO": ["CAISO", "WEIM"],
    "PJM": ["PJM"],
    "ERCOT": ["ERCOT"],
    "MISO": ["MISO"],
    "ISONE": ["ISO-NE", "ISO NE", "ISONE", "NEW ENGLAND ISO"],
    "NYISO": ["NYISO"],
    "SPP": ["SPP", "SOUTHWEST POWER POOL", "MARKETS+"],
}


THEME_KEYWORDS = {
    "Minimum Bill": ["minimum bill", "minimum billing demand", "minimum demand charge"],
    "Collateral or Credit": ["collateral", "letter of credit", "credit rating", "security", "deposit"],
    "CIAC and Cost Recovery": ["ciac", "contribution", "cost of new facilities", "upfront capacity"],
    "Study Cost Recovery": ["study cost", "interconnection study", "system impact", "engineering"],
    "Exit and Modification": ["exit fee", "notice to change", "contract capacity", "capacity reassignment"],
    "Clean Energy or Transition": ["clean energy", "renewable", "carbon-free", "transition"],
    "Interruptibility": ["interruptible", "curtail", "interruption"],
    "Load Ramp": ["load ramp", "ramp-up", "ramp period"],
}


@dataclass
class Row:
    state: str
    utility: str
    tariff: str
    status: str
    year: int | None
    sector: str
    min_demand_mw: float | None
    min_load_factor_pct: float | None
    utility_type: str
    iso_rto: str
    narrative: str
    docket: str
    contract_term: str
    load_ramp: str
    min_bill: str
    financial_assurance: str
    study_costs: str
    modification: str
    transition: str


def parse_float(value: str) -> float | None:
    if not value:
        return None
    text = str(value).strip().upper()
    if text in {"", "N/A", "NA", "NO", "NOT SPECIFIED", "REDACTED IN PROPOSAL"}:
        return None
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def clean_status(value: str) -> str:
    text = (value or "").strip()
    lower = text.lower()
    if lower.startswith("approved"):
        return "Approved"
    if "pending" in lower or "proposed" in lower:
        return "Proposed / Pending"
    return text or "Unknown"


def normalize_cell(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").split())


def infer_regions(iso_rto: str) -> list[str]:
    text = (iso_rto or "").upper()
    out = []
    for rid, keywords in REGION_KEYWORDS.items():
        if any(k in text for k in keywords):
            out.append(rid)
    return out


def split_docket(value: str) -> list[str]:
    text = normalize_cell(value)
    if not text or text.lower() in {"docket not included", "not specified"}:
        return ["Unspecified Docket"]
    parts = re.split(r"\s*[;,]\s*", text)
    return [p for p in parts if p]


def parse_rows() -> list[Row]:
    with SRC_CSV.open("r", encoding="utf-8", newline="") as f:
        lines = f.readlines()

    header_idx = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("State,Utility,Tariff or Service Rule"):
            header_idx = i
            break

    text = "".join(lines[header_idx:])
    reader = csv.DictReader(io.StringIO(text))
    rows: list[Row] = []

    for raw in reader:
        year_val = parse_float(raw.get("Year", ""))
        rows.append(
            Row(
                state=normalize_cell(raw.get("State", "")),
                utility=normalize_cell(raw.get("Utility", "")),
                tariff=normalize_cell(raw.get("Tariff or Service Rule", "")),
                status=clean_status(raw.get("Status", "")),
                year=int(year_val) if year_val else None,
                sector=normalize_cell(raw.get("Sector or Segment", "")),
                min_demand_mw=parse_float(raw.get("Minimum Demand (MW)", "")),
                min_load_factor_pct=parse_float(raw.get("Minimum Load Factor", "")),
                utility_type=normalize_cell(raw.get("Utility Type", "")),
                iso_rto=normalize_cell(raw.get("ISO/RTO", "")),
                narrative=normalize_cell(raw.get("Narrative Highlights", "")),
                docket=normalize_cell(raw.get("Docket(s) Link", "")),
                contract_term=normalize_cell(raw.get("Contract Term", "")),
                load_ramp=normalize_cell(raw.get("Load Ramp-Up Period", "")),
                min_bill=normalize_cell(raw.get("Minimum Bill as a % of Contract Capacity", "")),
                financial_assurance=normalize_cell(raw.get("Financial Assurance & Contributions", "")),
                study_costs=normalize_cell(raw.get("Customer Pays Utility Study Costs", "")),
                modification=normalize_cell(raw.get("Contract Modification Provisions", "")),
                transition=normalize_cell(raw.get("Energy Transition Provisions", "")),
            )
        )
    return rows


def pct(part: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(100.0 * part / total, 1)


def count_field_presence(rows: list[Row], attr: str) -> int:
    n = 0
    for row in rows:
        text = getattr(row, attr)
        if text and text.lower() not in {"not specified", "no", "na", "n/a"}:
            n += 1
    return n


def extract_theme_counts(rows: list[Row]) -> dict[str, int]:
    counts = Counter()
    for row in rows:
        hay = " ".join(
            [
                row.narrative.lower(),
                row.contract_term.lower(),
                row.load_ramp.lower(),
                row.min_bill.lower(),
                row.financial_assurance.lower(),
                row.study_costs.lower(),
                row.modification.lower(),
                row.transition.lower(),
            ]
        )
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in hay for k in kws):
                counts[theme] += 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


def summarize_dockets(rows: list[Row]) -> list[dict]:
    grouped: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        for docket in split_docket(row.docket):
            grouped[docket].append(row)

    out = []
    for docket, rs in grouped.items():
        statuses = Counter(r.status for r in rs)
        sectors = Counter(r.sector for r in rs if r.sector)
        demands = [r.min_demand_mw for r in rs if r.min_demand_mw is not None]
        utilities = sorted({r.utility for r in rs if r.utility})
        states = sorted({r.state for r in rs if r.state})

        theme_hits = Counter()
        for r in rs:
            hay = " ".join([r.narrative, r.financial_assurance, r.modification, r.transition]).lower()
            for theme, kws in THEME_KEYWORDS.items():
                if any(k in hay for k in kws):
                    theme_hits[theme] += 1

        out.append(
            {
                "docket": docket,
                "records": len(rs),
                "states": states,
                "utilities": utilities,
                "statusBreakdown": dict(statuses),
                "topSector": sectors.most_common(1)[0][0] if sectors else "Unknown",
                "medianMinDemandMw": round(median(demands), 2) if demands else None,
                "keyThemes": [k for k, _ in theme_hits.most_common(3)],
            }
        )

    return sorted(out, key=lambda d: (-d["records"], d["docket"]))


def build_summary(rows: list[Row]) -> dict:
    total = len(rows)
    status_counts = Counter(r.status for r in rows)
    sector_counts = Counter(r.sector for r in rows if r.sector)
    utility_type_counts = Counter(r.utility_type for r in rows if r.utility_type)
    year_counts = Counter(r.year for r in rows if r.year)

    min_demand_vals = [r.min_demand_mw for r in rows if r.min_demand_mw is not None]
    load_factor_vals = [r.min_load_factor_pct for r in rows if r.min_load_factor_pct is not None]

    by_region = Counter()
    for row in rows:
        for region in infer_regions(row.iso_rto):
            by_region[region] += 1

    docket_summaries = summarize_dockets(rows)
    theme_counts = extract_theme_counts(rows)

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": SRC_CSV.name,
        "totals": {
            "rows": total,
            "approved": status_counts.get("Approved", 0),
            "proposedPending": status_counts.get("Proposed / Pending", 0),
            "approvedPct": pct(status_counts.get("Approved", 0), total),
        },
        "statusCounts": dict(status_counts),
        "sectorTop10": sector_counts.most_common(10),
        "utilityTypeCounts": dict(utility_type_counts),
        "yearCounts": dict(sorted(year_counts.items())),
        "marketRegionCounts": dict(by_region),
        "numericStats": {
            "minDemandMw": {
                "count": len(min_demand_vals),
                "median": round(median(min_demand_vals), 2) if min_demand_vals else None,
                "min": round(min(min_demand_vals), 2) if min_demand_vals else None,
                "max": round(max(min_demand_vals), 2) if min_demand_vals else None,
            },
            "minLoadFactorPct": {
                "count": len(load_factor_vals),
                "median": round(median(load_factor_vals), 2) if load_factor_vals else None,
                "min": round(min(load_factor_vals), 2) if load_factor_vals else None,
                "max": round(max(load_factor_vals), 2) if load_factor_vals else None,
            },
        },
        "fieldCoverage": {
            "contractTermSpecified": count_field_presence(rows, "contract_term"),
            "loadRampSpecified": count_field_presence(rows, "load_ramp"),
            "minimumBillSpecified": count_field_presence(rows, "min_bill"),
            "financialAssuranceSpecified": count_field_presence(rows, "financial_assurance"),
            "studyCostRecoverySpecified": count_field_presence(rows, "study_costs"),
            "contractModificationSpecified": count_field_presence(rows, "modification"),
            "energyTransitionSpecified": count_field_presence(rows, "transition"),
        },
        "themeCounts": theme_counts,
        "dockets": docket_summaries,
    }
    return summary


def write_markdown(summary: dict) -> None:
    total = summary["totals"]["rows"]
    approved = summary["totals"]["approved"]
    pending = summary["totals"]["proposedPending"]
    approved_pct = summary["totals"]["approvedPct"]

    lines = []
    lines.append("# DELTa Exploratory Analysis and Docket Synthesis")
    lines.append("")
    lines.append(f"Generated: {summary['generatedAt']}")
    lines.append(f"Source: {summary['source']}")
    lines.append("")
    lines.append("## Statistical Summary")
    lines.append("")
    lines.append(f"- Records: {total}")
    lines.append(f"- Approved: {approved} ({approved_pct}%)")
    lines.append(f"- Proposed/Pending: {pending}")
    lines.append("")
    lines.append("### Numeric Highlights")
    lines.append("")
    md = summary["numericStats"]["minDemandMw"]
    lf = summary["numericStats"]["minLoadFactorPct"]
    lines.append(
        f"- Minimum demand (MW): n={md['count']}, median={md['median']}, range={md['min']} to {md['max']}"
    )
    lines.append(
        f"- Minimum load factor (%): n={lf['count']}, median={lf['median']}, range={lf['min']} to {lf['max']}"
    )
    lines.append("")
    lines.append("### Top Themes")
    lines.append("")
    for theme, count in list(summary["themeCounts"].items())[:8]:
        lines.append(f"- {theme}: {count} records")

    lines.append("")
    lines.append("## LLM-Style Docket Synthesis")
    lines.append("")
    lines.append(
        "This section provides a compact docket-by-docket synthesis for analyst review, emphasizing status, thresholds, and contractual risk controls."
    )
    lines.append("")

    for d in summary["dockets"]:
        status = ", ".join(f"{k}: {v}" for k, v in d["statusBreakdown"].items())
        states = ", ".join(d["states"][:4]) + (" ..." if len(d["states"]) > 4 else "")
        utilities = ", ".join(d["utilities"][:3]) + (" ..." if len(d["utilities"]) > 3 else "")
        themes = ", ".join(d["keyThemes"]) if d["keyThemes"] else "General tariff structuring"
        lines.append(f"### {d['docket']}")
        lines.append(f"- Records: {d['records']}")
        lines.append(f"- Status: {status}")
        lines.append(f"- States: {states if states else 'N/A'}")
        lines.append(f"- Utilities: {utilities if utilities else 'N/A'}")
        lines.append(f"- Median minimum demand (MW): {d['medianMinDemandMw']}")
        lines.append(f"- Dominant themes: {themes}")
        lines.append("")

    lines.append("## Key Rate Trends")
    lines.append("")
    coverage = summary["fieldCoverage"]
    lines.append(
        f"- Risk-transfer design is prevalent: financial assurance appears in {coverage['financialAssuranceSpecified']} records and study-cost recovery in {coverage['studyCostRecoverySpecified']} records."
    )
    lines.append(
        f"- Contractual commitment is common: contract term is specified in {coverage['contractTermSpecified']} records, with frequent minimum bill structures ({coverage['minimumBillSpecified']} records)."
    )
    lines.append(
        f"- Flexibility controls are rising: contract modification clauses appear in {coverage['contractModificationSpecified']} records and load-ramp provisions in {coverage['loadRampSpecified']} records."
    )
    lines.append(
        f"- Energy transition linkage remains selective: explicit transition provisions appear in {coverage['energyTransitionSpecified']} records."
    )

    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = parse_rows()
    summary = build_summary(rows)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    write_markdown(summary)

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {OUT_MD}")
    print(f"Rows analyzed: {summary['totals']['rows']}")
    print(f"Approved share: {summary['totals']['approvedPct']}%")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate region-level flexibility analysis calibrated by FlexDC-Sim output."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate regional flexibility analysis with FlexDC-Sim metrics.")
    parser.add_argument(
        "--rates",
        default="data/rates.json",
        help="Path to rates.json",
    )
    parser.add_argument(
        "--sim-dir",
        default=None,
        help="Backward-compatible single scenario path (same as --scenario baseline=<dir>)",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Named scenario in the form name=/path/to/sim_output_dir. Repeat for multiple scenarios.",
    )
    parser.add_argument(
        "--output",
        default="analysis/flexdc_region_results.json",
        help="Path to write summary results JSON",
    )
    return parser.parse_args()


def read_tracking_error(sim_dir: Path) -> float:
    tracking_path = sim_dir / "tracking_error_90th.csv"
    with tracking_path.open("r", encoding="utf-8") as handle:
        lines = [line.strip() for line in handle if line.strip()]
    # Expected shape:
    # Tracking Error 90th Percentile
    # 0.301
    return float(lines[-1])


def read_qos_metrics(sim_dir: Path) -> tuple[float, float]:
    qos_path = sim_dir / "qos_summary.csv"
    with qos_path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    violations = 0
    slowdown_values: list[float] = []
    for row in rows:
        qos_90th = float(row["qos_90th"])
        qos_threshold = float(row["qos_threshold"])
        slowdown_values.append(float(row["mean_exec_slowdown"]))
        if qos_90th > qos_threshold:
            violations += 1

    violation_rate = violations / len(rows) if rows else 0.0
    mean_slowdown = average(slowdown_values)
    return violation_rate, mean_slowdown


def get_flexible_mw_for_category(category: str, profile: dict[str, Any]) -> float:
    battery = float(profile["portfolioMW"].get("battery", 0))
    cooling = float(profile["portfolioMW"].get("cooling", 0))
    generator = float(profile["portfolioMW"].get("generator", 0))
    if category == "ancillary":
        return battery + cooling * 0.25
    if category == "energy":
        return battery * 0.5 + cooling
    if category == "emergency":
        return battery + generator * 0.6
    if category == "capacity":
        return battery + cooling + generator * 0.4
    return battery + cooling


def estimate_program_annual_value(program: dict[str, Any], profile: dict[str, Any]) -> tuple[float, float]:
    category = program.get("marketCategory", "energy")
    rate_min = float(program.get("rate_min") or 0)
    rate_max = float(program.get("rate_max") or rate_min)
    unit = str(program.get("rate_unit", "")).lower()
    flexible_mw = get_flexible_mw_for_category(category, profile)
    multiplier = float(profile.get("marketMultipliers", {}).get(category, 1))

    if flexible_mw <= 0 or (rate_min <= 0 and rate_max <= 0):
        return 0.0, 0.0

    annual = profile.get("annualHours", {})
    if "/mwh" in unit or "/mw-hr" in unit or "/mw per hour" in unit:
        hours = float(annual.get(category, 0))
        return rate_min * flexible_mw * hours * multiplier, rate_max * flexible_mw * hours * multiplier
    if "/mw-day" in unit:
        days = float(annual.get("capacityDays", 0))
        return rate_min * flexible_mw * days * multiplier, rate_max * flexible_mw * days * multiplier
    if "/kw-month" in unit:
        months = float(annual.get("capacityMonths", 0))
        return (
            rate_min * flexible_mw * 1000 * months * multiplier,
            rate_max * flexible_mw * 1000 * months * multiplier,
        )
    return 0.0, 0.0


def compute_region_result(region_id: str, region: dict[str, Any], profile: dict[str, Any], base_deliverability: float) -> dict[str, Any]:
    target_flex = float(profile.get("targets", {}).get("flexibility", 4))
    prog_tolerance = float(profile.get("targets", {}).get("programmaticTolerance", 2))
    weights = profile.get("weights", {"economic": 0.4, "flexibility": 0.35, "programmatic": 0.25})

    program_results = []
    for program in region.get("programs", []):
        typology = program.get("typology", {})
        econ = float(typology.get("economic", {}).get("score", 3))
        flex = float(typology.get("flexibility", {}).get("score", 2))
        prog = float(typology.get("programmatic", {}).get("score", 3))

        flexibility_fit = clamp(5 - abs(flex - target_flex), 1, 5)
        programmatic_fit = clamp(5 - max(0, prog - prog_tolerance), 1, 5)

        base_score = (
            econ * float(weights.get("economic", 0.4))
            + flexibility_fit * float(weights.get("flexibility", 0.35))
            + programmatic_fit * float(weights.get("programmatic", 0.25))
        )

        strictness = (flex - 1) / 4.0  # 0 to 1
        deliverability = clamp(base_deliverability * (1 - 0.35 * strictness), 0.05, 1.0)

        raw_low, raw_high = estimate_program_annual_value(program, profile)
        annual_low = raw_low * deliverability
        annual_high = raw_high * deliverability

        program_results.append(
            {
                "program": program,
                "economicFit": econ,
                "flexibilityFit": flexibility_fit,
                "programmaticFit": programmatic_fit,
                "baseScore": base_score,
                "deliverability": deliverability,
                "annualLow": annual_low,
                "annualHigh": annual_high,
            }
        )

    by_category: dict[str, dict[str, Any]] = {}
    for item in program_results:
        category = item["program"].get("marketCategory", "other")
        current = by_category.get(category)
        if current is None or item["annualHigh"] > current["annualHigh"]:
            by_category[category] = item

    selected = list(by_category.values())
    stackability = float(profile.get("stackabilityFactor", 0.65))
    annual_low = sum(item["annualLow"] for item in selected) * stackability
    annual_high = sum(item["annualHigh"] for item in selected) * stackability

    econ_fit = average([item["economicFit"] for item in program_results])
    flex_fit = average([item["flexibilityFit"] for item in program_results])
    prog_fit = average([item["programmaticFit"] for item in program_results])
    weighted_fit = (
        econ_fit * float(weights.get("economic", 0.4))
        + flex_fit * float(weights.get("flexibility", 0.35))
        + prog_fit * float(weights.get("programmatic", 0.25))
    )
    overall_score = clamp(weighted_fit * (0.6 + 0.4 * base_deliverability), 1, 5)

    top_program = max(program_results, key=lambda x: x["baseScore"], default=None)
    best_category = top_program["program"].get("marketCategory", "energy") if top_program else "energy"

    selected_sorted = sorted(selected, key=lambda x: x["annualHigh"], reverse=True)
    best_programs_summary = " | ".join(
        f"{item['program'].get('marketCategory', 'other').capitalize()}: {item['program'].get('name', 'Unknown')}"
        for item in selected_sorted
    ) or "No program data"

    return {
        "regionId": region_id,
        "economicFit": round(econ_fit, 3),
        "flexibilityFit": round(flex_fit, 3),
        "programmaticFit": round(prog_fit, 3),
        "overallScore": round(overall_score, 3),
        "annualValueLow": round(annual_low, 2),
        "annualValueHigh": round(annual_high, 2),
        "bestCategoryLabel": best_category.capitalize(),
        "bestProgramsSummary": best_programs_summary,
        "topProgram": top_program["program"].get("name", "N/A") if top_program else "N/A",
        "simDeliverabilityFactor": round(base_deliverability, 4),
    }


def main() -> None:
    args = parse_args()
    rates_path = Path(args.rates)
    output_path = Path(args.output)

    scenarios: list[tuple[str, Path]] = []
    for item in args.scenario:
        if "=" not in item:
            raise ValueError(f"Invalid --scenario value '{item}'. Expected name=/path/to/output_dir")
        name, path = item.split("=", 1)
        name = name.strip()
        if not name:
            raise ValueError("Scenario name cannot be empty")
        scenarios.append((name, Path(path.strip())))
    if args.sim_dir:
        scenarios.insert(0, ("baseline", Path(args.sim_dir)))
    if not scenarios:
        raise ValueError("Provide --sim-dir or at least one --scenario name=/path")

    with rates_path.open("r", encoding="utf-8") as handle:
        rates = json.load(handle)

    profile = rates.get("sectorProfiles", {}).get("dataCenters")
    if not profile:
        raise RuntimeError("rates.json does not contain sectorProfiles.dataCenters")

    scenario_payloads: dict[str, dict[str, Any]] = {}
    for scenario_name, sim_dir in scenarios:
        tracking_error_90 = read_tracking_error(sim_dir)
        qos_violation_rate, mean_exec_slowdown = read_qos_metrics(sim_dir)

        tracking_score = clamp(1 - tracking_error_90, 0, 1)
        qos_compliance = clamp(1 - qos_violation_rate, 0, 1)
        slowdown_score = clamp(1 - mean_exec_slowdown, 0, 1)
        base_deliverability = clamp(
            0.55 * tracking_score + 0.35 * qos_compliance + 0.10 * slowdown_score,
            0.05,
            1.0,
        )

        region_results = {}
        for region_id, region in rates.get("regions", {}).items():
            region_results[region_id] = compute_region_result(region_id, region, profile, base_deliverability)

        ranking = sorted(region_results.values(), key=lambda item: item["overallScore"], reverse=True)
        scenario_payloads[scenario_name] = {
            "simulationRun": str(sim_dir),
            "simMetrics": {
                "trackingError90": round(tracking_error_90, 4),
                "qosViolationRateByType": round(qos_violation_rate, 4),
                "meanExecSlowdown": round(mean_exec_slowdown, 4),
                "deliverabilityFactor": round(base_deliverability, 4),
            },
            "regions": region_results,
            "ranking": [item["regionId"] for item in ranking],
        }

    primary_name = scenarios[0][0]
    primary = scenario_payloads[primary_name]

    comparisons = {}
    if len(scenarios) >= 2:
        other_name = scenarios[1][0]
        other = scenario_payloads[other_name]
        deltas = {}
        for region_id, region_result in primary["regions"].items():
            other_result = other["regions"].get(region_id, {})
            deltas[region_id] = {
                "overallScoreDelta": round(region_result["overallScore"] - float(other_result.get("overallScore", 0)), 3),
                "annualValueHighDelta": round(region_result["annualValueHigh"] - float(other_result.get("annualValueHigh", 0)), 2),
            }
        comparisons[f"{primary_name}_vs_{other_name}"] = {
            "leftScenario": primary_name,
            "rightScenario": other_name,
            "regionDeltas": deltas,
        }

    analysis_payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceRepo": "https://github.com/sgfernandes/flexdc-sim",
        "simulationRun": primary["simulationRun"],
        "method": "FlexDC-Sim calibrated regional valuation",
        "currentScenario": primary_name,
        "simMetrics": primary["simMetrics"],
        "regions": primary["regions"],
        "ranking": primary["ranking"],
        "scenarios": scenario_payloads,
        "comparisons": comparisons,
    }

    rates.setdefault("analysis", {})["flexdcSim"] = analysis_payload

    rates["lastUpdated"] = datetime.now(timezone.utc).date().isoformat()
    with rates_path.open("w", encoding="utf-8") as handle:
        json.dump(rates, handle, indent=2)
        handle.write("\n")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(analysis_payload, handle, indent=2)
        handle.write("\n")

    print(f"Wrote analysis to {output_path}")
    for scenario_name, scenario in scenario_payloads.items():
        print(f"Regional ranking ({scenario_name}):")
        ranking_rows = sorted(scenario["regions"].values(), key=lambda item: item["overallScore"], reverse=True)
        for idx, item in enumerate(ranking_rows, start=1):
            print(f"{idx}. {item['regionId']} score={item['overallScore']:.3f} value_high=${item['annualValueHigh']:.0f}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Two-stage interpretable typology model for DELTa large-load records.

Stage 1: rule-derived typology labels (T1-T4) over engineered features.
Stage 2: gradient-boosted classifier trained on those features/labels with
leave-one-out cross-validation, plus SHAP per-feature attributions.

Outputs:
    analysis/typology_predictions.csv
    analysis/typology_summary.json
    analysis/figures/typology_distribution.png
    analysis/figures/shap_summary.png
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import shap
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import balanced_accuracy_score, f1_score
from sklearn.model_selection import LeaveOneOut
from sklearn.preprocessing import OrdinalEncoder

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis"))
from analyze_delta_dataset import parse_rows, Row  # noqa: E402

OUT_CSV = ROOT / "analysis" / "typology_predictions.csv"
OUT_JSON = ROOT / "analysis" / "typology_summary.json"
FIG_DIR = ROOT / "analysis" / "figures"
FIG_DIR.mkdir(exist_ok=True)

TYPOLOGY = {
    "T1": "Pending / under construction",
    "T2": "Risk-transfer (collateral-heavy)",
    "T3": "Light-touch / minimal",
    "T4": "Flexibility-coupled",
}

FINANCIAL_KEYWORDS = [
    "collateral", "letter of credit", "deposit", "ciac", "guaranty",
    "surety", "security", "upfront capacity", "contribution", "advance",
]
TRANSITION_KEYWORDS = [
    "clean energy", "renewable", "transition", "interruptible",
    "demand response", "time-of-use", "environmental improvement",
    "storage", "carbon-free", "curtail",
]
EXIT_KEYWORDS = [
    "exit fee", "notice to change", "capacity reassignment",
    "capacity changes", "notice to exit",
]


def hay(row: Row) -> str:
    return " ".join([
        row.narrative, row.financial_assurance, row.modification,
        row.transition, row.min_bill, row.contract_term,
    ]).lower()


def has_any(text: str, kws: list[str]) -> int:
    return int(any(k in text for k in kws))


def parse_years(text: str) -> float:
    m = re.search(r"\d+(?:\.\d+)?", text or "")
    return float(m.group(0)) if m else 0.0


def featurize(rows: list[Row]) -> tuple[np.ndarray, list[str], list[dict]]:
    feats = []
    raw = []
    for r in rows:
        h = hay(r)
        min_demand = r.min_demand_mw or 0.0
        contract_years = parse_years(r.contract_term)
        load_factor = r.min_load_factor_pct or 0.0
        fa = has_any(h, FINANCIAL_KEYWORDS)
        tr = has_any(h, TRANSITION_KEYWORDS)
        ex = has_any(h, EXIT_KEYWORDS)
        mb = int(bool(r.min_bill) and r.min_bill.lower() not in {"not specified", "no", "n/a", ""})
        is_pending = int("pending" in r.status.lower() or "proposed" in r.status.lower())
        feats.append([min_demand, contract_years, load_factor, fa, tr, ex, mb, is_pending])
        raw.append({
            "state": r.state, "utility": r.utility, "tariff": r.tariff,
            "status": r.status, "docket": r.docket,
        })
    cols = [
        "min_demand_mw", "contract_term_years", "load_factor_pct",
        "financial_assurance", "transition_clean", "exit_control",
        "minimum_bill", "is_pending",
    ]
    return np.array(feats, dtype=float), cols, raw


def assign_typology(x: np.ndarray) -> str:
    min_demand, term, _lf, fa, tr, ex, mb, pending = x
    if pending:
        return "T1"
    if tr or ex:
        return "T4"
    if fa or (min_demand >= 50 and term >= 10) or (term >= 10 and mb):
        return "T2"
    return "T3"


def main() -> None:
    rows = parse_rows()
    X, cols, raw = featurize(rows)
    y = np.array([assign_typology(x) for x in X])
    labels = sorted(TYPOLOGY)

    enc = OrdinalEncoder().fit(y.reshape(-1, 1))
    y_idx = enc.transform(y.reshape(-1, 1)).ravel().astype(int)

    loo = LeaveOneOut()
    preds = np.empty_like(y_idx)
    for tr_idx, te_idx in loo.split(X):
        clf = HistGradientBoostingClassifier(max_depth=4, max_iter=200, random_state=0)
        clf.fit(X[tr_idx], y_idx[tr_idx])
        preds[te_idx] = clf.predict(X[te_idx])

    macro_f1 = f1_score(y_idx, preds, average="macro", zero_division=0)
    bal_acc = balanced_accuracy_score(y_idx, preds)

    # Fit final model on full data for SHAP and exported predictions.
    final = HistGradientBoostingClassifier(max_depth=4, max_iter=200, random_state=0)
    final.fit(X, y_idx)
    proba = final.predict_proba(X)
    pred_labels = enc.inverse_transform(final.predict(X).reshape(-1, 1)).ravel()

    # SHAP attributions (multi-class -> mean |phi| across classes/records).
    explainer = shap.TreeExplainer(final)
    shap_values = explainer.shap_values(X)  # shape (n, k) or list of (n, k)
    if isinstance(shap_values, list):
        stacked = np.stack(shap_values, axis=0)  # (classes, n, k)
        mean_abs = np.mean(np.abs(stacked), axis=(0, 1))
    else:
        arr = np.asarray(shap_values)
        if arr.ndim == 3:
            mean_abs = np.mean(np.abs(arr), axis=(0, 1)) if arr.shape[0] != len(rows) \
                else np.mean(np.abs(arr), axis=(0, 2))
        else:
            mean_abs = np.mean(np.abs(arr), axis=0)
    order = np.argsort(mean_abs)[::-1]
    shap_summary = [(cols[i], float(mean_abs[i])) for i in order]

    # Counts.
    label_counts = Counter(y.tolist())
    summary = {
        "n_records": int(len(rows)),
        "typology_definitions": TYPOLOGY,
        "label_counts": {k: int(label_counts.get(k, 0)) for k in labels},
        "label_share_pct": {k: round(100.0 * label_counts.get(k, 0) / len(rows), 1) for k in labels},
        "metrics": {
            "leave_one_out_macro_f1": round(float(macro_f1), 3),
            "leave_one_out_balanced_accuracy": round(float(bal_acc), 3),
        },
        "shap_mean_abs_contribution": [
            {"feature": f, "mean_abs_phi": round(v, 4)} for f, v in shap_summary
        ],
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2))

    # Per-record predictions CSV.
    lines = ["record_idx,state,utility,tariff,status,rule_label,model_pred," +
             ",".join(f"p_{l}" for l in labels)]
    for i, r in enumerate(raw):
        probs = ",".join(f"{p:.3f}" for p in proba[i])
        lines.append(
            f"{i},\"{r['state']}\",\"{r['utility']}\",\"{r['tariff'].replace(chr(34), '')}\","
            f"\"{r['status']}\",{y[i]},{pred_labels[i]},{probs}"
        )
    OUT_CSV.write_text("\n".join(lines) + "\n")

    # Figure: typology distribution with T4 highlighted.
    fig, ax = plt.subplots(figsize=(7, 3.6))
    counts = [label_counts.get(k, 0) for k in labels]
    colors = ["#4c78a8" if k != "T4" else "#e45756" for k in labels]
    bars = ax.bar(labels, counts, color=colors)
    for b, c in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.4,
                f"{c}\n({round(100.0*c/len(rows),0):.0f}%)",
                ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Record count (n=77)")
    ax.set_title("Typology distribution (T4 = Flexibility-coupled, highlighted)")
    ax.set_ylim(0, max(counts) + 6)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "typology_distribution.png", dpi=160)
    plt.close(fig)

    # Figure: SHAP mean |phi| summary.
    fig, ax = plt.subplots(figsize=(7, 3.6))
    feat_names = [f for f, _ in shap_summary]
    vals = [v for _, v in shap_summary]
    ax.barh(feat_names[::-1], vals[::-1], color="#54a24b")
    ax.set_xlabel("Mean |SHAP| contribution")
    ax.set_title("Global feature importance (typology classifier)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "shap_summary.png", dpi=160)
    plt.close(fig)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

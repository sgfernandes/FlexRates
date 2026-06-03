#!/usr/bin/env python3
"""Generate a static methodology pipeline figure for the DELTa ML paper."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "analysis" / "figures" / "methodology_pipeline.png"
OUT.parent.mkdir(exist_ok=True)


def add_box(ax, xy, text, color, width=1.42, height=0.56):
    x, y = xy
    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.045,rounding_size=0.055",
        linewidth=1.1,
        edgecolor="#333333",
        facecolor=color,
    )
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=8.2)


def add_diamond(ax, xy, text, color, width=0.95, height=0.66):
    x, y = xy
    points = [(x, y + height / 2), (x + width / 2, y), (x, y - height / 2), (x - width / 2, y)]
    patch = Polygon(points, closed=True, linewidth=1.1, edgecolor="#333333", facecolor=color)
    ax.add_patch(patch)
    ax.text(x, y, text, ha="center", va="center", fontsize=8.2)


def arrow(ax, start, end, text=None, text_xy=None, rad=0.0):
    patch = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=1.15,
        color="#333333",
        connectionstyle=f"arc3,rad={rad}",
    )
    ax.add_patch(patch)
    if text and text_xy:
        ax.text(*text_xy, text, fontsize=7.4, ha="center", va="center")


def poly_arrow(ax, points, text=None, text_xy=None):
    for start, end in zip(points[:-2], points[1:-1]):
        ax.plot([start[0], end[0]], [start[1], end[1]], color="#333333", linewidth=1.15)
    arrow(ax, points[-2], points[-1])
    if text and text_xy:
        ax.text(*text_xy, text, fontsize=7.4, ha="center", va="center")


def main():
    fig, ax = plt.subplots(figsize=(8.6, 3.65))
    ax.set_xlim(0.1, 8.8)
    ax.set_ylim(0.0, 3.85)
    ax.axis("off")

    blue = "#edf4fb"
    orange = "#fff1df"
    green = "#eef8ee"
    red = "#fdecec"
    yellow = "#fff7ce"

    positions = {
        "csv": (0.95, 3.05),
        "ingest": (2.55, 3.05),
        "normalize": (4.15, 3.05),
        "features": (5.75, 3.05),
        "typology": (2.55, 2.02),
        "ranking": (4.15, 2.02),
        "shap": (5.75, 2.02),
        "revise": (4.15, 1.02),
        "qa": (5.75, 1.02),
        "publish": (7.45, 1.02),
        "next": (0.95, 0.55),
    }

    add_box(ax, positions["csv"], "DELTa CSV\nrelease r", blue)
    add_box(ax, positions["ingest"], "Ingestion &\nschema check", blue)
    add_box(ax, positions["normalize"], "Normalization\n& coding", blue)
    add_box(ax, positions["features"], "Feature build\ntariff features", blue)
    add_box(ax, positions["typology"], "Typology model\nGBM classifier", orange)
    add_box(ax, positions["ranking"], "Docket ranking\ncomposite score", orange)
    add_box(ax, positions["shap"], "Explainability\nSHAP", orange)
    add_diamond(ax, positions["qa"], "QA\npass?", yellow)
    add_box(ax, positions["revise"], "Revise coding\nor thresholds", red)
    add_box(ax, positions["publish"], "Publish artifacts\nfigures, tables, paper", green)
    add_box(ax, positions["next"], "Next DELTa\nrelease r+1", blue, width=1.52, height=0.52)

    # Main ingestion and modeling flow.
    arrow(ax, (1.67, 3.05), (1.83, 3.05))
    arrow(ax, (3.27, 3.05), (3.43, 3.05))
    arrow(ax, (4.87, 3.05), (5.03, 3.05))
    poly_arrow(ax, [(5.75, 2.77), (5.75, 2.46), (2.55, 2.46), (2.55, 2.30)])
    arrow(ax, (3.27, 2.02), (3.43, 2.02))
    arrow(ax, (4.87, 2.02), (5.03, 2.02))
    arrow(ax, (5.75, 1.74), (5.75, 1.36))

    # QA branches and revision loop.
    arrow(ax, (5.28, 1.02), (4.88, 1.02), text="no", text_xy=(5.06, 1.18))
    arrow(ax, (6.22, 1.02), (6.73, 1.02), text="yes", text_xy=(6.47, 1.18))
    arrow(ax, (3.65, 1.30), (3.05, 1.74), rad=0.0)

    # Publication and refresh loop routed around the outside.
    poly_arrow(ax, [(7.45, 0.74), (7.45, 0.18), (1.72, 0.18), (1.72, 0.55)])
    arrow(ax, (0.95, 0.83), (0.95, 2.77))

    # Light visual grouping labels.
    ax.text(5.75, 3.62, "Data preparation", ha="center", va="center", fontsize=8.5, color="#555555")
    ax.text(4.15, 2.58, "Interpretable analytics", ha="center", va="bottom", fontsize=8.5, color="#555555")
    ax.text(5.75, 0.40, "Quality gate", ha="center", va="center", fontsize=8.5, color="#555555")
    ax.text(3.45, 0.01, "Refresh loop", ha="center", va="bottom", fontsize=8.5, color="#555555")

    fig.tight_layout(pad=0.25)
    fig.savefig(OUT, dpi=220, bbox_inches="tight")
    print(OUT)


if __name__ == "__main__":
    main()

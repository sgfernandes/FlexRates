# FlexRates

Interactive GIS dashboard for industrial load flexibility and demand response rate structures across the major U.S. ISOs and RTOs.

## Features

- Leaflet-based GIS map for CAISO, PJM, ERCOT, MISO, ISO-NE, NYISO, and SPP
- Choropleth views for energy, capacity, emergency, and ancillary rate ranges
- Region comparison mode with Chart.js summaries
- Time-series trend charts for 2020-2025 rate history
- Search and filter for market programs
- Flask API for editing and persisting rate data locally
- Program typology classification across Economic, Flexibility, and Programmatic dimensions
- JSON and CSV export

## Repository Structure

- [index.html](index.html): main UI shell
- [app.js](app.js): frontend logic for map, charts, filters, edit flows, and exports
- [server.py](server.py): Flask backend and REST API
- [data/rates.json](data/rates.json): rate dataset and typology metadata
- [data/regions.geojson](data/regions.geojson): GIS boundaries
- [DELTa_2026-03-31-Public-Update.csv](DELTa_2026-03-31-Public-Update.csv): public DELTa large-load tariff and program update used by the DELTa analysis papers
- [analysis/](analysis/): reproducible scripts and generated outputs for DELTa, FlexDC-Sim, and sector analyses
- [papers/](papers/): LaTeX manuscripts generated from the analysis outputs
- [requirements.txt](requirements.txt): Python dependencies

## Local Run

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Start the Flask server:

```bash
python server.py
```

Open:

```text
http://localhost:5000
```

## Data Model

The dataset in [data/rates.json](data/rates.json) is region-centric and includes:

- `numericRates`: numeric min/max values for map coloring and comparisons
- `rateHistory`: annual series for energy, emergency, and capacity values
- `programs`: per-program market details, sizes, timing, and typology
- `typology`: three-dimensional classification for each program

Typology fields use this structure:

```json
{
  "typology": {
    "economic": {
      "score": 3,
      "label": "Market-linked",
      "notes": "Revenue tracks clearing price or LMP and can move materially."
    },
    "flexibility": {
      "score": 1,
      "label": "Scheduled",
      "notes": "Best for loads that can plan shifts into market schedules."
    },
    "programmatic": {
      "score": 3,
      "label": "Moderate complexity",
      "notes": "Expect regular metering, baseline, or aggregation administration."
    }
  }
}
```

Interpretation:

- Higher `economic` score: stronger upside or greater rate volatility
- Higher `flexibility` score: faster or more operationally demanding load response
- Higher `programmatic` score: heavier compliance, telemetry, or settlement burden

## API Endpoints

Served by [server.py](server.py):

- `GET /api/rates`
- `PUT /api/rates`
- `GET /api/rates/regions/<region_id>`
- `PUT /api/rates/regions/<region_id>/summary`
- `PUT /api/rates/regions/<region_id>/numericRates`
- `GET /api/rates/regions/<region_id>/programs`
- `POST /api/rates/regions/<region_id>/programs`
- `PUT /api/rates/regions/<region_id>/programs/<idx>`
- `DELETE /api/rates/regions/<region_id>/programs/<idx>`
- `GET /api/geojson`

## GitHub Pages

GitHub Pages can host the static frontend, but it does not run Flask.

That means:

- map, charts, comparisons, and exports work
- static JSON fallback works
- in-browser edits do not persist unless the Flask backend is hosted elsewhere

For full editing support, deploy the Flask backend on a Python host such as Render, Railway, Fly.io, or PythonAnywhere.

## Future Extensions

- NAICS-based sector compatibility scoring
- typology filters in the toolbar
- typology comparison charts by region
- scheduled data refresh via GitHub Actions

## DELTa Large-Load Rate Analysis Workflow

This repository includes a reproducible analysis workflow for the 2026-03-31 DELTa public update dataset. The workflow is designed so other researchers can trace every figure and table back to the source CSV and rerun the analysis after a future DELTa release.

### Source data

- [DELTa_2026-03-31-Public-Update.csv](DELTa_2026-03-31-Public-Update.csv): source large-load tariff, program, and service-rule records.
- Rows cover 77 records across 36 states.
- Core fields include state, utility, tariff or service rule, status, sector, minimum demand, load factor, utility type, ISO/RTO linkage, narrative highlights, docket reference, contract term, load-ramp provisions, minimum-bill provisions, financial assurance, study-cost responsibility, contract-modification provisions, and energy-transition provisions.

### Analysis scripts

- [analysis/analyze_delta_dataset.py](analysis/analyze_delta_dataset.py): parses the DELTa CSV, auto-detects the canonical header row, normalizes records, extracts themes from text fields, summarizes state/utility/sector/region coverage, and writes exploratory JSON/Markdown outputs.
- [analysis/generate_scientific_plots.py](analysis/generate_scientific_plots.py): generates the main DELTa policy-question figures used by the ML/ranking paper, including threshold, financial-protection, long-term/minimum-bill, transition, and pending-docket charts.
- [analysis/run_typology_classifier.py](analysis/run_typology_classifier.py): builds an optional interpretable typology layer over engineered DELTa features and exports typology predictions, summary metrics, and SHAP-style feature-importance figures.
- [analysis/generate_methodology_pipeline.py](analysis/generate_methodology_pipeline.py): generates the methodology pipeline figure used in the ML/ranking paper.
- [analysis/generate_third_paper_figures.py](analysis/generate_third_paper_figures.py): generates the four figures for the emerging industrial load flexibility practices paper: key design aspects, state distribution, participation/performance/scalability features, and actors/regions/customer segments.

### Generated DELTa outputs

- [analysis/delta_exploratory_summary.json](analysis/delta_exploratory_summary.json): machine-readable summary of totals, status counts, field coverage, themes, market-region linkage, and docket summaries.
- [analysis/delta_exploratory_summary.md](analysis/delta_exploratory_summary.md): human-readable exploratory summary.
- [analysis/delta_policy_question_stats.json](analysis/delta_policy_question_stats.json): statistics for the five DELTa policy questions.
- [analysis/delta_state_risk_scores.csv](analysis/delta_state_risk_scores.csv): state-level risk-score export.
- [analysis/delta_top15_dockets.csv](analysis/delta_top15_dockets.csv): ranked docket export.
- [analysis/typology_predictions.csv](analysis/typology_predictions.csv) and [analysis/typology_summary.json](analysis/typology_summary.json): optional typology model outputs.
- [analysis/figures/](analysis/figures/): generated PNG figures consumed by the LaTeX papers.

### Papers

- [papers/ml_delta_market_ranking/paper.tex](papers/ml_delta_market_ranking/paper.tex): paper focused on interpretable DELTa feature coding, typology/ranking, and policy-question outputs.
- [papers/emerging_industrial_load_flexibility/paper.tex](papers/emerging_industrial_load_flexibility/paper.tex): descriptive paper identifying emerging industrial load flexibility practices in large-load rates and programs.

### Reproduce the DELTa analysis

Create and activate a Python environment, then install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run the exploratory DELTa summary:

```bash
python analysis/analyze_delta_dataset.py
```

Generate the policy-question figures and statistics:

```bash
python analysis/generate_scientific_plots.py
```

Generate the emerging-practices paper figures:

```bash
python analysis/generate_third_paper_figures.py
```

Optionally run the typology classifier layer:

```bash
python analysis/run_typology_classifier.py
```

The LaTeX papers use relative `figures/` links inside each paper folder. Those folders are symlinked to [analysis/figures/](analysis/figures/) so the papers and figures remain connected to the generated analysis outputs.

## FlexDC-Sim Regional Analysis Workflow

This repo now includes a simulator-calibrated regional analysis path using:

- https://github.com/sgfernandes/flexdc-sim

### What was added

- `analysis/policy_flexdc_w2.ini`: policy config used for the baseline simulator run
- `analysis/policy_flexdc_w2_nodr.ini`: policy config used for the NoDR-style comparison scenario
- `analysis/run_flexdc_region_analysis.py`: script that converts FlexDC-Sim output into all-region calibrated scores/value ranges
- `analysis/flexdc_region_results.json`: generated results snapshot
- `analysis/data_center_earnings_summary.json`: ranked earnings summary for the active calibrated scenario
- `analysis/data_center_earnings_by_region.csv`: tabular earnings export by region
- `data/rates.json`: now stores simulator-derived analysis under `analysis.flexdcSim`

### Reproduce the analysis

1. Clone FlexDC-Sim into this workspace (already done in `external/flexdc-sim`).
2. Run a baseline simulation:

```bash
cd external/flexdc-sim/src/peacsim
source ../../../venv/bin/activate
export PYTHONPATH=..
python run_simulator.py \
  --experiment-config ../../configs/experiment/exp_low_util.ini \
  --cluster-config ../../configs/cluster/cluster.ini \
  --policy-config /absolute/path/to/analysis/policy_flexdc_w2.ini \
  --job-config ../../configs/workload/W2-short-qos3445.ini \
  --output-dir energy_rates_regional_baseline \
  --convert-from-normalized-PR
```

2b. Run a NoDR-style comparison scenario:

```bash
python run_simulator.py \
  --experiment-config ../../configs/experiment/exp_low_util.ini \
  --cluster-config ../../configs/cluster/cluster.ini \
  --policy-config /absolute/path/to/analysis/policy_flexdc_w2_nodr.ini \
  --job-config ../../configs/workload/W2-short-qos3445.ini \
  --output-dir energy_rates_regional_nodr \
  --convert-from-normalized-PR
```

3. Calibrate all regions and update the dashboard dataset:

```bash
cd /path/to/energy-rates-gis
source venv/bin/activate
python analysis/run_flexdc_region_analysis.py \
  --scenario baseline=external/flexdc-sim/src/peacsim/output/simulation/<baseline_output_dir> \
  --scenario nodr=external/flexdc-sim/src/peacsim/output/simulation/<nodr_output_dir>
```

After this, the app uses `analysis.flexdcSim` from `data/rates.json` in the Data Center analysis panel. The panel now includes:

- mode selector: `Calibrated (FlexDC-Sim)` vs `Heuristic (Local)`
- scenario selector: choose among calibrated scenarios (e.g., `baseline`, `nodr`)
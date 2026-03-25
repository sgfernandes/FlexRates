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
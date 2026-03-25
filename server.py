"""
Flask backend for the Energy Rates GIS Dashboard.
Provides REST API for reading and updating rates data,
persisting changes to data/rates.json on disk.
"""
import json
import os
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

DATA_DIR = Path(__file__).parent / "data"
RATES_FILE = DATA_DIR / "rates.json"


def read_rates():
    with open(RATES_FILE, "r") as f:
        return json.load(f)


def write_rates(data):
    data["lastUpdated"] = date.today().isoformat()
    with open(RATES_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ── Static files ──────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


# ── API: Rates ────────────────────────────────────────

@app.route("/api/rates", methods=["GET"])
def get_rates():
    return jsonify(read_rates())


@app.route("/api/rates", methods=["PUT"])
def put_rates():
    """Replace the entire rates dataset."""
    data = request.get_json()
    if not data or "regions" not in data:
        return jsonify({"error": "Invalid payload — must include 'regions'"}), 400
    write_rates(data)
    return jsonify(read_rates())


# ── API: Region ───────────────────────────────────────

@app.route("/api/rates/regions/<region_id>", methods=["GET"])
def get_region(region_id):
    data = read_rates()
    region = data["regions"].get(region_id)
    if not region:
        return jsonify({"error": f"Region '{region_id}' not found"}), 404
    return jsonify(region)


@app.route("/api/rates/regions/<region_id>/summary", methods=["PUT"])
def update_summary(region_id):
    """Update a region's summary rates."""
    data = read_rates()
    if region_id not in data["regions"]:
        return jsonify({"error": f"Region '{region_id}' not found"}), 404
    body = request.get_json()
    if not body:
        return jsonify({"error": "Empty payload"}), 400
    data["regions"][region_id]["summary"] = body
    write_rates(data)
    return jsonify(data["regions"][region_id]["summary"])


@app.route("/api/rates/regions/<region_id>/numericRates", methods=["PUT"])
def update_numeric_rates(region_id):
    """Update a region's numeric rates for choropleth."""
    data = read_rates()
    if region_id not in data["regions"]:
        return jsonify({"error": f"Region '{region_id}' not found"}), 404
    body = request.get_json()
    if not body:
        return jsonify({"error": "Empty payload"}), 400
    data["regions"][region_id]["numericRates"] = body
    write_rates(data)
    return jsonify(data["regions"][region_id]["numericRates"])


# ── API: Programs ─────────────────────────────────────

@app.route("/api/rates/regions/<region_id>/programs", methods=["GET"])
def get_programs(region_id):
    data = read_rates()
    if region_id not in data["regions"]:
        return jsonify({"error": f"Region '{region_id}' not found"}), 404
    return jsonify(data["regions"][region_id]["programs"])


@app.route("/api/rates/regions/<region_id>/programs", methods=["POST"])
def add_program(region_id):
    """Add a new program to a region."""
    data = read_rates()
    if region_id not in data["regions"]:
        return jsonify({"error": f"Region '{region_id}' not found"}), 404
    body = request.get_json()
    if not body or "name" not in body:
        return jsonify({"error": "Program must have a 'name'"}), 400
    data["regions"][region_id]["programs"].append(body)
    write_rates(data)
    return jsonify(body), 201


@app.route("/api/rates/regions/<region_id>/programs/<int:idx>", methods=["PUT"])
def update_program(region_id, idx):
    """Update an existing program by index."""
    data = read_rates()
    if region_id not in data["regions"]:
        return jsonify({"error": f"Region '{region_id}' not found"}), 404
    programs = data["regions"][region_id]["programs"]
    if idx < 0 or idx >= len(programs):
        return jsonify({"error": f"Program index {idx} out of range"}), 404
    body = request.get_json()
    if not body:
        return jsonify({"error": "Empty payload"}), 400
    programs[idx] = body
    write_rates(data)
    return jsonify(body)


@app.route("/api/rates/regions/<region_id>/programs/<int:idx>", methods=["DELETE"])
def delete_program(region_id, idx):
    """Delete a program by index."""
    data = read_rates()
    if region_id not in data["regions"]:
        return jsonify({"error": f"Region '{region_id}' not found"}), 404
    programs = data["regions"][region_id]["programs"]
    if idx < 0 or idx >= len(programs):
        return jsonify({"error": f"Program index {idx} out of range"}), 404
    removed = programs.pop(idx)
    write_rates(data)
    return jsonify({"removed": removed["name"]})


# ── API: GeoJSON ──────────────────────────────────────

@app.route("/api/geojson", methods=["GET"])
def get_geojson():
    with open(DATA_DIR / "regions.geojson", "r") as f:
        return jsonify(json.load(f))


# ── Run ───────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

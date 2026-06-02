// ══════════════════════════════════════════════════════
//  Energy Rates GIS Dashboard — app.js (v0.7)
//  Choropleth · Compare · Time-Series · Typology · Sector Analysis · API
// ══════════════════════════════════════════════════════

// ── Configuration ─────────────────────────────────────
const API_BASE = window.location.origin + '/api';
const USE_API = true; // set false to fall back to static files

const REGION_COLORS = {
    CAISO: '#38bdf8', PJM: '#a78bfa', ERCOT: '#f97316',
    MISO: '#facc15', ISONE: '#4ade80', NYISO: '#f472b6', SPP: '#fb923c'
};

const CATEGORY_CLASSES = {
    energy: 'cat-energy', capacity: 'cat-capacity',
    emergency: 'cat-emergency', ancillary: 'cat-ancillary'
};

// ── State ─────────────────────────────────────────────
let ratesData = null;
let geoData = null;
let geoLayer = null;
let labelMarkers = [];
let selectedRegion = null;
let choroplethMetric = 'none';
let compareMode = false;
let compareRegions = []; // max 3
let dataCenterAnalysisMode = 'calibrated';
let selectedFlexScenario = 'baseline';
let deltaPolicyData = null;

// Chart instances
let chartEnergy = null;
let chartEmergency = null;
let chartCapacity = null;
let compareChart = null;
let chartDataCenters = null;
let chartPolicyStatus = null;
let chartPolicyRegion = null;

// ── Map setup ─────────────────────────────────────────
const map = L.map('map', {
    center: [39.5, -96.5],
    zoom: 4,
    minZoom: 3,
    maxZoom: 10,
    zoomControl: true
});

L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    subdomains: 'abcd',
    maxZoom: 19
}).addTo(map);

// ── Data loading ──────────────────────────────────────
async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status} from ${url}`);
    return resp.json();
}

async function init() {
    try {
        if (USE_API) {
            [ratesData, geoData] = await Promise.all([
                fetchJSON(API_BASE + '/rates'),
                fetchJSON(API_BASE + '/geojson')
            ]);
        } else {
            [ratesData, geoData] = await Promise.all([
                fetchJSON('data/rates.json'),
                fetchJSON('data/regions.geojson')
            ]);
        }
    } catch {
        // Fallback to static files if API unreachable
        [ratesData, geoData] = await Promise.all([
            fetchJSON('data/rates.json'),
            fetchJSON('data/regions.geojson')
        ]);
    }

    try {
        deltaPolicyData = await fetchJSON('data/delta_summary.json');
    } catch {
        deltaPolicyData = null;
    }

    normalizeRatesData(ratesData);

    const scenarios = ratesData.analysis?.flexdcSim?.scenarios || {};
    const hasScenarios = Object.keys(scenarios).length > 0;
    if (!hasScenarios) dataCenterAnalysisMode = 'heuristic';
    selectedFlexScenario = ratesData.analysis?.flexdcSim?.currentScenario || Object.keys(scenarios)[0] || 'baseline';

    document.getElementById('last-updated').textContent = 'Last updated: ' + ratesData.lastUpdated;

    // URL hash state
    const hash = window.location.hash.replace('#', '');
    if (hash && ratesData.regions[hash]) {
        selectedRegion = hash;
    }

    renderMap();
    setupEventListeners();
    renderDataCenterAnalysis();
    renderPolicyIntelligence();

    if (selectedRegion) {
        showRegionDetail(selectedRegion);
        showTrends(selectedRegion);
    }
}

// ── Map rendering ─────────────────────────────────────
function renderMap() {
    if (geoLayer) map.removeLayer(geoLayer);
    labelMarkers.forEach(m => map.removeLayer(m));
    labelMarkers = [];

    geoLayer = L.geoJSON(geoData, {
        style: feature => styleFeature(feature),
        onEachFeature: (feature, layer) => {
            const id = feature.properties.id;
            const region = ratesData.regions[id];
            if (!region) return;

            layer.bindTooltip(
                `<strong>${escapeHtml(region.name)}</strong><br>` +
                `<span style="font-size:11px">${region.type} · ${region.programs.length} programs</span>` +
                (choroplethMetric !== 'none' ? `<br><span style="font-size:11px;color:#4ade80;">${getChoroplethTooltip(id)}</span>` : ''),
                { className: 'region-tooltip', sticky: true }
            );

            layer.on('click', () => handleRegionClick(id));
        }
    }).addTo(map);

    // Center labels
    geoData.features.forEach(f => {
        const id = f.properties.id;
        const bounds = L.geoJSON(f).getBounds();
        const center = bounds.getCenter();
        const marker = L.marker(center, {
            icon: L.divIcon({
                className: 'region-label',
                html: `<div style="
                    color:${choroplethMetric === 'none' ? REGION_COLORS[id] : '#fff'};
                    font-weight:700; font-size:13px;
                    text-shadow: 0 0 6px rgba(0,0,0,0.9);
                    white-space:nowrap; pointer-events:none;
                ">${id}</div>`,
                iconSize: [60, 20],
                iconAnchor: [30, 10]
            })
        }).addTo(map);
        labelMarkers.push(marker);
    });

    updateChoroplethLegend();
}

function styleFeature(feature) {
    const id = feature.properties.id;
    const isSelected = selectedRegion === id;
    const isCompared = compareRegions.includes(id);

    if (choroplethMetric !== 'none') {
        const val = getChoroplethValue(id);
        const color = val !== null ? getHeatColor(val, getChoroplethRange()) : '#334155';
        return {
            color: isSelected || isCompared ? '#ffffff' : '#475569',
            weight: isSelected || isCompared ? 3 : 1,
            fillColor: color,
            fillOpacity: 0.65,
            dashArray: ''
        };
    }

    return {
        color: isSelected || isCompared ? '#ffffff' : REGION_COLORS[id] || '#64748b',
        weight: isSelected || isCompared ? 3 : 1.5,
        fillColor: REGION_COLORS[id] || '#64748b',
        fillOpacity: isSelected || isCompared ? 0.45 : 0.25,
        dashArray: isSelected || isCompared ? '' : '4 4'
    };
}

// ── Choropleth helpers ────────────────────────────────
function getChoroplethValue(regionId) {
    const nr = ratesData.regions[regionId]?.numericRates;
    if (!nr) return null;
    const key = { energy: 'energy_max_MWh', capacity: 'capacity_max_kW_month', emergency: 'emergency_max_MWh', ancillary: 'ancillary_max_MWh' }[choroplethMetric];
    return nr[key];
}

function getChoroplethRange() {
    let min = Infinity, max = -Infinity;
    for (const regionId of Object.keys(ratesData.regions)) {
        const v = getChoroplethValue(regionId);
        if (v !== null && v !== undefined) {
            min = Math.min(min, v);
            max = Math.max(max, v);
        }
    }
    return { min: min === Infinity ? 0 : min, max: max === -Infinity ? 1 : max };
}

function getChoroplethTooltip(regionId) {
    const v = getChoroplethValue(regionId);
    if (v === null || v === undefined) return 'N/A';
    const labels = { energy: '$/MWh', capacity: '$/kW-mo', emergency: '$/MWh', ancillary: '$/MWh' };
    return `$${v} ${labels[choroplethMetric] || ''}`;
}

function getHeatColor(value, range) {
    const t = range.max === range.min ? 0.5 : (value - range.min) / (range.max - range.min);
    // Blue → Yellow → Red
    const r = Math.round(t < 0.5 ? t * 2 * 255 : 255);
    const g = Math.round(t < 0.5 ? 200 + t * 110 : 255 * (1 - (t - 0.5) * 2));
    const b = Math.round(t < 0.5 ? 255 * (1 - t * 2) : 0);
    return `rgb(${r},${g},${b})`;
}

function updateChoroplethLegend() {
    const el = document.getElementById('choropleth-legend');
    if (choroplethMetric === 'none') { el.style.display = 'none'; return; }
    el.style.display = 'block';
    const range = getChoroplethRange();
    const labels = { energy: 'Energy Rate ($/MWh)', capacity: 'Capacity Rate ($/kW-mo)', emergency: 'Emergency Rate ($/MWh)', ancillary: 'Ancillary Rate ($/MWh)' };
    document.getElementById('choro-title').textContent = labels[choroplethMetric];
    document.getElementById('choro-gradient').style.background = 'linear-gradient(to right, rgb(0,200,255), rgb(255,255,0), rgb(255,0,0))';
    document.getElementById('choro-min').textContent = '$' + range.min;
    document.getElementById('choro-max').textContent = '$' + range.max;
}

// ── Region click handler ──────────────────────────────
function handleRegionClick(id) {
    if (compareMode) {
        if (compareRegions.includes(id)) {
            compareRegions = compareRegions.filter(r => r !== id);
        } else if (compareRegions.length < 3) {
            compareRegions.push(id);
        }
        renderMap();
        renderCompare();
        return;
    }

    selectedRegion = id;
    window.location.hash = id;
    renderMap();
    showRegionDetail(id);
    showTrends(id);
    renderDataCenterAnalysis();
    renderPolicyIntelligence();

    // Switch to detail tab
    activateTab('detail');
}

// ── Tabs ──────────────────────────────────────────────
function activateTab(name) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === 'panel-' + name));
}

// ── Region detail panel ───────────────────────────────
function showRegionDetail(regionId) {
    const region = ratesData.regions[regionId];
    if (!region) return;

    document.getElementById('empty-state').style.display = 'none';
    const el = document.getElementById('region-detail');
    el.style.display = 'block';

    const s = region.summary;
    const nr = region.numericRates;
    const regionTypology = summarizeRegionTypology(region);
    const search = document.getElementById('search-input').value.toLowerCase();
    const filterMarket = document.getElementById('filter-market').value;
    const filterKw = parseInt(document.getElementById('filter-kw').value) || 0;

    let filteredPrograms = region.programs.filter((p, i) => {
        if (search && !p.name.toLowerCase().includes(search) && !p.market.toLowerCase().includes(search)) return false;
        if (filterMarket && p.marketCategory !== filterMarket) return false;
        if (filterKw > 0 && p.minSize_kW > filterKw) return false;
        return true;
    });

    el.innerHTML = `
        <div class="region-card">
            <h2>${escapeHtml(region.name)}</h2>
            <span class="type-badge ${region.type}">${region.type}</span>
            <span style="font-size:11px;color:#94a3b8;margin-left:8px;">${region.states.join(', ')}</span>
            <div class="rate-grid">
                <div class="rate-box">
                    <div class="label">Energy Rate</div>
                    <div class="value">${escapeHtml(s.energyRate)}</div>
                    ${nr.energy_max_MWh ? `<div class="numeric">$${nr.energy_min_MWh}–$${nr.energy_max_MWh}/MWh</div>` : ''}
                </div>
                <div class="rate-box">
                    <div class="label">Capacity Rate</div>
                    <div class="value">${escapeHtml(s.capacityRate)}</div>
                    ${nr.capacity_max_kW_month ? `<div class="numeric">$${nr.capacity_min_kW_month}–$${nr.capacity_max_kW_month}/kW-mo</div>` : ''}
                </div>
                <div class="rate-box">
                    <div class="label">Emergency Rate</div>
                    <div class="value">${escapeHtml(s.emergencyRate)}</div>
                    ${nr.emergency_max_MWh ? `<div class="numeric">$${nr.emergency_min_MWh}–$${nr.emergency_max_MWh}/MWh</div>` : ''}
                </div>
                <div class="rate-box">
                    <div class="label">Ancillary Rate</div>
                    <div class="value">${escapeHtml(s.ancillaryRate)}</div>
                    ${nr.ancillary_max_MWh ? `<div class="numeric">$${nr.ancillary_min_MWh}–$${nr.ancillary_max_MWh}/MWh</div>` : ''}
                </div>
            </div>
            <button class="btn btn-primary" onclick="openEditSummary('${regionId}')" style="width:100%;margin-bottom:12px;">
                ✏️ Edit Summary Rates
            </button>
            <div>
                <h3 style="font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;">Typology Snapshot</h3>
                <div class="typology-grid">
                    ${renderTypologyBox('Economic', regionTypology.economic)}
                    ${renderTypologyBox('Flexibility', regionTypology.flexibility)}
                    ${renderTypologyBox('Programmatic', regionTypology.programmatic)}
                </div>
                <p class="section-caption">Average program-level typology scores for this market. Higher economic means stronger upside; higher flexibility and programmatic mean more demanding operationally or administratively.</p>
            </div>
        </div>

        <div class="programs-section">
            <h3>Programs (${filteredPrograms.length} of ${region.programs.length})</h3>
            ${filteredPrograms.map((p) => {
                const realIdx = region.programs.indexOf(p);
                return `
                <div class="program-row" onclick="openEditProgram('${regionId}', ${realIdx})">
                    <div class="pname">${escapeHtml(p.name)}</div>
                    <div class="pdetails">${escapeHtml(p.market)} · Min ${p.minSize_kW} kW · ${escapeHtml(p.notificationTime)}</div>
                    <div class="prate">${escapeHtml(p.rateRange)}${p.rate_min != null ? ` <span style="color:#94a3b8;font-weight:400;">(${p.rate_min}–${p.rate_max} ${escapeHtml(p.rate_unit)})</span>` : ''}</div>
                    <div class="program-meta">
                        <div class="program-type-col">
                            <span class="pcategory ${CATEGORY_CLASSES[p.marketCategory] || ''}">${escapeHtml(p.marketCategory || 'other')}</span>
                            ${renderProgramTypologyPills(p)}
                        </div>
                    </div>
                </div>`;
            }).join('')}
            <button class="btn-add" onclick="openAddProgram('${regionId}')">+ Add Program</button>
        </div>
    `;
}

// ── Time-series charts ────────────────────────────────
function showTrends(regionId) {
    const region = ratesData.regions[regionId];
    if (!region || !region.rateHistory) return;

    document.getElementById('trends-empty').style.display = 'none';
    document.getElementById('trends-content').style.display = 'block';

    const h = region.rateHistory;
    const years = h.energy_avg_MWh.map(d => d.year);

    const chartOpts = {
        responsive: true,
        plugins: {
            legend: { display: false },
            tooltip: { mode: 'index', intersect: false }
        },
        scales: {
            x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
            y: { ticks: { color: '#94a3b8', callback: v => '$' + v }, grid: { color: '#1e293b' }, beginAtZero: true }
        }
    };

    if (chartEnergy) chartEnergy.destroy();
    if (chartEmergency) chartEmergency.destroy();
    if (chartCapacity) chartCapacity.destroy();

    chartEnergy = new Chart(document.getElementById('chart-energy'), {
        type: 'line',
        data: {
            labels: years,
            datasets: [{
                label: 'Energy avg $/MWh',
                data: h.energy_avg_MWh.map(d => d.value),
                borderColor: '#4ade80', backgroundColor: 'rgba(74,222,128,0.1)',
                fill: true, tension: 0.3, pointRadius: 4
            }]
        },
        options: chartOpts
    });

    chartEmergency = new Chart(document.getElementById('chart-emergency'), {
        type: 'line',
        data: {
            labels: years,
            datasets: [{
                label: 'Emergency avg $/MWh',
                data: h.emergency_avg_MWh.map(d => d.value),
                borderColor: '#f87171', backgroundColor: 'rgba(248,113,113,0.1)',
                fill: true, tension: 0.3, pointRadius: 4
            }]
        },
        options: chartOpts
    });

    const capData = h.capacity_avg_kW_month.map(d => d.value);
    const hasCapacity = capData.some(v => v !== null);
    chartCapacity = new Chart(document.getElementById('chart-capacity'), {
        type: 'line',
        data: {
            labels: years,
            datasets: [{
                label: 'Capacity avg $/kW-mo',
                data: hasCapacity ? capData : [],
                borderColor: '#a78bfa', backgroundColor: 'rgba(167,139,250,0.1)',
                fill: true, tension: 0.3, pointRadius: 4
            }]
        },
        options: {
            ...chartOpts,
            plugins: {
                ...chartOpts.plugins,
                title: hasCapacity ? {} : { display: true, text: 'No capacity market data', color: '#64748b' }
            }
        }
    });
}

// ── Compare mode ──────────────────────────────────────
function renderCompare() {
    const selEl = document.getElementById('compare-selections');
    selEl.innerHTML = compareRegions.length === 0
        ? '<p style="font-size:12px;color:#64748b;">No regions selected. Click regions on the map.</p>'
        : compareRegions.map(id => `
            <span style="display:inline-flex;align-items:center;gap:4px;background:${REGION_COLORS[id]};color:#000;
                padding:3px 10px;border-radius:6px;font-size:12px;font-weight:600;margin-right:6px;">
                ${id}
                <span style="cursor:pointer;margin-left:4px;" onclick="removeCompare('${id}')">&times;</span>
            </span>
        `).join('');

    if (compareRegions.length < 2) {
        document.getElementById('compare-content').innerHTML = '<p style="font-size:12px;color:#64748b;">Select at least 2 regions to compare.</p>';
        document.getElementById('compare-chart-wrap').style.display = 'none';
        return;
    }

    // Comparison bar chart
    document.getElementById('compare-chart-wrap').style.display = 'block';
    if (compareChart) compareChart.destroy();

    const metrics = ['energy_max_MWh', 'emergency_max_MWh', 'ancillary_max_MWh'];
    const metricLabels = ['Energy ($/MWh)', 'Emergency ($/MWh)', 'Ancillary ($/MWh)'];

    compareChart = new Chart(document.getElementById('compare-chart'), {
        type: 'bar',
        data: {
            labels: metricLabels,
            datasets: compareRegions.map(id => ({
                label: id,
                data: metrics.map(m => ratesData.regions[id]?.numericRates?.[m] ?? 0),
                backgroundColor: REGION_COLORS[id] + 'cc',
                borderColor: REGION_COLORS[id],
                borderWidth: 1
            }))
        },
        options: {
            responsive: true,
            plugins: {
                legend: { labels: { color: '#e2e8f0', font: { size: 11 } } }
            },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                y: { ticks: { color: '#94a3b8', callback: v => '$' + v }, grid: { color: '#1e293b' }, beginAtZero: true }
            }
        }
    });

    // Side-by-side cards
    const content = document.getElementById('compare-content');
    content.innerHTML = compareRegions.map(id => {
        const r = ratesData.regions[id];
        const nr = r.numericRates;
        return `
            <div class="compare-card" style="border-left: 3px solid ${REGION_COLORS[id]};">
                <h4 style="color:${REGION_COLORS[id]}">${escapeHtml(r.name)}</h4>
                <div class="compare-row"><span class="compare-label">Type</span><span class="compare-value">${r.type}</span></div>
                <div class="compare-row"><span class="compare-label">Programs</span><span class="compare-value">${r.programs.length}</span></div>
                <div class="compare-row"><span class="compare-label">Energy Max</span><span class="compare-value">${nr.energy_max_MWh != null ? '$' + nr.energy_max_MWh + '/MWh' : 'N/A'}</span></div>
                <div class="compare-row"><span class="compare-label">Capacity Max</span><span class="compare-value">${nr.capacity_max_kW_month != null ? '$' + nr.capacity_max_kW_month + '/kW-mo' : 'N/A'}</span></div>
                <div class="compare-row"><span class="compare-label">Emergency Max</span><span class="compare-value">${nr.emergency_max_MWh != null ? '$' + nr.emergency_max_MWh + '/MWh' : 'N/A'}</span></div>
                <div class="compare-row"><span class="compare-label">Ancillary Max</span><span class="compare-value">${nr.ancillary_max_MWh != null ? '$' + nr.ancillary_max_MWh + '/MWh' : 'N/A'}</span></div>
            </div>`;
    }).join('');
}

function removeCompare(id) {
    compareRegions = compareRegions.filter(r => r !== id);
    renderMap();
    renderCompare();
}

// ── API persistence helpers ───────────────────────────
async function apiPut(path, body) {
    if (!USE_API) return;
    try {
        const resp = await fetch(API_BASE + path, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!resp.ok) console.error('API error:', await resp.text());
    } catch (e) {
        console.warn('API unreachable, changes saved locally only');
    }
}

async function apiPost(path, body) {
    if (!USE_API) return;
    try {
        await fetch(API_BASE + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
    } catch (e) { console.warn('API unreachable'); }
}

async function apiDelete(path) {
    if (!USE_API) return;
    try {
        await fetch(API_BASE + path, { method: 'DELETE' });
    } catch (e) { console.warn('API unreachable'); }
}

// ── Edit summary modal ────────────────────────────────
function openEditSummary(regionId) {
    const region = ratesData.regions[regionId];
    const s = region.summary;
    const nr = region.numericRates;
    openModal(`
        <h2>Edit Rates — ${escapeHtml(region.name)}</h2>
        <div class="form-group"><label>Energy Rate (text)</label><input id="ed-energy" value="${escapeAttr(s.energyRate)}"></div>
        <div class="form-row">
            <div class="form-group"><label>Energy Min ($/MWh)</label><input id="ed-nrEmin" type="number" value="${nr.energy_min_MWh ?? ''}"></div>
            <div class="form-group"><label>Energy Max ($/MWh)</label><input id="ed-nrEmax" type="number" value="${nr.energy_max_MWh ?? ''}"></div>
        </div>
        <div class="form-group"><label>Capacity Rate (text)</label><input id="ed-capacity" value="${escapeAttr(s.capacityRate)}"></div>
        <div class="form-row">
            <div class="form-group"><label>Cap. Min ($/kW-mo)</label><input id="ed-nrCmin" type="number" step="0.01" value="${nr.capacity_min_kW_month ?? ''}"></div>
            <div class="form-group"><label>Cap. Max ($/kW-mo)</label><input id="ed-nrCmax" type="number" step="0.01" value="${nr.capacity_max_kW_month ?? ''}"></div>
        </div>
        <div class="form-group"><label>Emergency Rate (text)</label><input id="ed-emergency" value="${escapeAttr(s.emergencyRate)}"></div>
        <div class="form-row">
            <div class="form-group"><label>Emerg. Min ($/MWh)</label><input id="ed-nrXmin" type="number" value="${nr.emergency_min_MWh ?? ''}"></div>
            <div class="form-group"><label>Emerg. Max ($/MWh)</label><input id="ed-nrXmax" type="number" value="${nr.emergency_max_MWh ?? ''}"></div>
        </div>
        <div class="form-group"><label>Ancillary Rate (text)</label><input id="ed-ancillary" value="${escapeAttr(s.ancillaryRate)}"></div>
        <div class="form-row">
            <div class="form-group"><label>Ancil. Min ($/MWh)</label><input id="ed-nrAmin" type="number" value="${nr.ancillary_min_MWh ?? ''}"></div>
            <div class="form-group"><label>Ancil. Max ($/MWh)</label><input id="ed-nrAmax" type="number" value="${nr.ancillary_max_MWh ?? ''}"></div>
        </div>
        <div class="btn-row">
            <button class="btn btn-primary" onclick="saveSummary('${regionId}')">Save Changes</button>
            <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    `);
}

async function saveSummary(regionId) {
    const summary = {
        energyRate: document.getElementById('ed-energy').value,
        capacityRate: document.getElementById('ed-capacity').value,
        emergencyRate: document.getElementById('ed-emergency').value,
        ancillaryRate: document.getElementById('ed-ancillary').value
    };
    const numericRates = {
        energy_min_MWh: parseNum('ed-nrEmin'), energy_max_MWh: parseNum('ed-nrEmax'),
        capacity_min_kW_month: parseNum('ed-nrCmin'), capacity_max_kW_month: parseNum('ed-nrCmax'),
        emergency_min_MWh: parseNum('ed-nrXmin'), emergency_max_MWh: parseNum('ed-nrXmax'),
        ancillary_min_MWh: parseNum('ed-nrAmin'), ancillary_max_MWh: parseNum('ed-nrAmax')
    };

    ratesData.regions[regionId].summary = summary;
    ratesData.regions[regionId].numericRates = numericRates;
    ratesData.lastUpdated = todayStr();
    document.getElementById('last-updated').textContent = 'Last updated: ' + ratesData.lastUpdated;

    await apiPut(`/rates/regions/${regionId}/summary`, summary);
    await apiPut(`/rates/regions/${regionId}/numericRates`, numericRates);

    closeModal();
    showRegionDetail(regionId);
    renderMap();
    renderDataCenterAnalysis();
    showToast('Summary rates updated');
}

// ── Edit program modal ────────────────────────────────
function openEditProgram(regionId, idx) {
    const p = ratesData.regions[regionId].programs[idx];
    openModal(`
        <h2>Edit Program — ${escapeHtml(p.name)}</h2>
        <div class="form-group"><label>Program Name</label><input id="ep-name" value="${escapeAttr(p.name)}"></div>
        <div class="form-group"><label>Compensation Type</label><input id="ep-comp" value="${escapeAttr(p.compensation)}"></div>
        <div class="form-group"><label>Rate Range (text)</label><input id="ep-rate" value="${escapeAttr(p.rateRange)}"></div>
        <div class="form-row">
            <div class="form-group"><label>Rate Min</label><input id="ep-rmin" type="number" step="0.01" value="${p.rate_min ?? ''}"></div>
            <div class="form-group"><label>Rate Max</label><input id="ep-rmax" type="number" step="0.01" value="${p.rate_max ?? ''}"></div>
            <div class="form-group"><label>Unit</label><input id="ep-runit" value="${escapeAttr(p.rate_unit || '')}"></div>
        </div>
        <div class="form-group"><label>Market</label><input id="ep-market" value="${escapeAttr(p.market)}"></div>
        <div class="form-group"><label>Market Category</label>
            <select id="ep-mcat">
                <option value="energy" ${p.marketCategory === 'energy' ? 'selected' : ''}>Energy</option>
                <option value="capacity" ${p.marketCategory === 'capacity' ? 'selected' : ''}>Capacity</option>
                <option value="emergency" ${p.marketCategory === 'emergency' ? 'selected' : ''}>Emergency</option>
                <option value="ancillary" ${p.marketCategory === 'ancillary' ? 'selected' : ''}>Ancillary</option>
            </select>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Min Size (kW)</label><input id="ep-minsize" type="number" value="${p.minSize_kW}"></div>
            <div class="form-group"><label>Notification Time</label><input id="ep-notif" value="${escapeAttr(p.notificationTime)}"></div>
        </div>
        ${renderTypologyFields(p.typology)}
        <div class="btn-row">
            <button class="btn btn-primary" onclick="saveProgram('${regionId}', ${idx})">Save</button>
            <button class="btn btn-danger" onclick="deleteProgram('${regionId}', ${idx})">Delete</button>
            <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    `);
}

function buildProgramFromForm() {
    return {
        name: document.getElementById('ep-name').value,
        compensation: document.getElementById('ep-comp').value,
        rateRange: document.getElementById('ep-rate').value,
        market: document.getElementById('ep-market').value,
        marketCategory: document.getElementById('ep-mcat').value,
        minSize_kW: parseInt(document.getElementById('ep-minsize').value, 10) || 0,
        notificationTime: document.getElementById('ep-notif').value,
        rate_min: parseNum('ep-rmin'),
        rate_max: parseNum('ep-rmax'),
        rate_unit: document.getElementById('ep-runit')?.value || '',
        typology: readTypologyFields('ep')
    };
}

async function saveProgram(regionId, idx) {
    const prog = buildProgramFromForm();
    ratesData.regions[regionId].programs[idx] = prog;
    ratesData.lastUpdated = todayStr();
    await apiPut(`/rates/regions/${regionId}/programs/${idx}`, prog);
    closeModal();
    showRegionDetail(regionId);
    renderDataCenterAnalysis();
    showToast('Program updated');
}

async function deleteProgram(regionId, idx) {
    if (!confirm('Remove this program?')) return;
    ratesData.regions[regionId].programs.splice(idx, 1);
    ratesData.lastUpdated = todayStr();
    await apiDelete(`/rates/regions/${regionId}/programs/${idx}`);
    closeModal();
    showRegionDetail(regionId);
    renderDataCenterAnalysis();
    showToast('Program removed');
}

// ── Add program modal ─────────────────────────────────
function openAddProgram(regionId) {
    openModal(`
        <h2>Add Program — ${escapeHtml(ratesData.regions[regionId].name)}</h2>
        <div class="form-group"><label>Program Name</label><input id="ep-name" placeholder="e.g., Economic Demand Response"></div>
        <div class="form-group"><label>Compensation Type</label><input id="ep-comp" placeholder="e.g., LMP-based"></div>
        <div class="form-group"><label>Rate Range (text)</label><input id="ep-rate" placeholder="e.g., $50-$100/MWh"></div>
        <div class="form-row">
            <div class="form-group"><label>Rate Min</label><input id="ep-rmin" type="number" step="0.01" placeholder="50"></div>
            <div class="form-group"><label>Rate Max</label><input id="ep-rmax" type="number" step="0.01" placeholder="100"></div>
            <div class="form-group"><label>Unit</label><input id="ep-runit" placeholder="$/MWh"></div>
        </div>
        <div class="form-group"><label>Market</label><input id="ep-market" placeholder="e.g., Day-Ahead & Real-Time Energy"></div>
        <div class="form-group"><label>Market Category</label>
            <select id="ep-mcat">
                <option value="energy">Energy</option>
                <option value="capacity">Capacity</option>
                <option value="emergency">Emergency</option>
                <option value="ancillary">Ancillary</option>
            </select>
        </div>
        <div class="form-row">
            <div class="form-group"><label>Min Size (kW)</label><input id="ep-minsize" type="number" placeholder="100"></div>
            <div class="form-group"><label>Notification Time</label><input id="ep-notif" placeholder="e.g., 30 minutes"></div>
        </div>
        ${renderTypologyFields(getDefaultTypology())}
        <div class="btn-row">
            <button class="btn btn-primary" onclick="addProgram('${regionId}')">Add Program</button>
            <button class="btn btn-secondary" onclick="closeModal()">Cancel</button>
        </div>
    `);
}

async function addProgram(regionId) {
    const name = document.getElementById('ep-name').value;
    if (!name) { alert('Program name is required'); return; }
    const prog = buildProgramFromForm();
    ratesData.regions[regionId].programs.push(prog);
    ratesData.lastUpdated = todayStr();
    await apiPost(`/rates/regions/${regionId}/programs`, prog);
    closeModal();
    showRegionDetail(regionId);
    renderDataCenterAnalysis();
    showToast('Program added');
}

// ── Export ─────────────────────────────────────────────
function exportJSON() {
    downloadBlob(JSON.stringify(ratesData, null, 2), 'energy_rates_' + ratesData.lastUpdated + '.json', 'application/json');
    showToast('JSON exported');
}

function exportCSV() {
    const rows = [[
        'Region', 'Program', 'Market', 'Category', 'Compensation', 'RateRange', 'RateMin', 'RateMax', 'Unit',
        'MinSize_kW', 'NotificationTime',
        'EconomicScore', 'EconomicLabel', 'EconomicNotes',
        'FlexibilityScore', 'FlexibilityLabel', 'FlexibilityNotes',
        'ProgrammaticScore', 'ProgrammaticLabel', 'ProgrammaticNotes'
    ]];
    for (const [id, region] of Object.entries(ratesData.regions)) {
        for (const p of region.programs) {
            const typology = ensureProgramTypology(p);
            rows.push([
                id, p.name, p.market, p.marketCategory || '', p.compensation,
                p.rateRange, p.rate_min ?? '', p.rate_max ?? '', p.rate_unit || '',
                p.minSize_kW, p.notificationTime,
                typology.economic.score, typology.economic.label, typology.economic.notes,
                typology.flexibility.score, typology.flexibility.label, typology.flexibility.notes,
                typology.programmatic.score, typology.programmatic.label, typology.programmatic.notes
            ]);
        }
    }
    const csv = rows.map(r => r.map(c => '"' + String(c).replace(/"/g, '""') + '"').join(',')).join('\n');
    downloadBlob(csv, 'energy_rates_' + ratesData.lastUpdated + '.csv', 'text/csv');
    showToast('CSV exported');
}

function downloadBlob(content, filename, mime) {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
}

// ── Event listeners ───────────────────────────────────
function setupEventListeners() {
    // Choropleth selector
    document.getElementById('choropleth-metric').addEventListener('change', e => {
        choroplethMetric = e.target.value;
        renderMap();
    });

    // Compare toggle
    document.getElementById('compare-toggle').addEventListener('click', () => {
        compareMode = !compareMode;
        document.getElementById('compare-toggle').classList.toggle('active', compareMode);
        if (compareMode) {
            activateTab('compare');
            renderCompare();
        } else {
            compareRegions = [];
            renderMap();
        }
    });

    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => activateTab(btn.dataset.tab));
    });

    // Search + filter
    document.getElementById('search-input').addEventListener('input', () => { if (selectedRegion) showRegionDetail(selectedRegion); });
    document.getElementById('filter-market').addEventListener('change', () => { if (selectedRegion) showRegionDetail(selectedRegion); });
    document.getElementById('filter-kw').addEventListener('input', () => { if (selectedRegion) showRegionDetail(selectedRegion); });

    // Data center analysis mode + scenario
    const modeSelect = document.getElementById('dc-analysis-mode');
    const scenarioSelect = document.getElementById('dc-scenario-select');
    if (modeSelect) {
        modeSelect.addEventListener('change', e => {
            dataCenterAnalysisMode = e.target.value;
            renderDataCenterAnalysis();
        });
    }
    if (scenarioSelect) {
        scenarioSelect.addEventListener('change', e => {
            selectedFlexScenario = e.target.value;
            renderDataCenterAnalysis();
        });
    }

    const policyStatus = document.getElementById('policy-status-filter');
    const policyScope = document.getElementById('policy-scope-filter');
    if (policyStatus) policyStatus.addEventListener('change', renderPolicyIntelligence);
    if (policyScope) policyScope.addEventListener('change', renderPolicyIntelligence);

    // Modal backdrop
    document.getElementById('edit-modal').addEventListener('click', e => { if (e.target.id === 'edit-modal') closeModal(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
}

// ── Utilities ─────────────────────────────────────────
function openModal(html) {
    document.getElementById('modal-body').innerHTML = html;
    document.getElementById('edit-modal').classList.add('active');
}

function closeModal() {
    document.getElementById('edit-modal').classList.remove('active');
}

function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = '✓ ' + msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function parseNum(id) {
    const v = document.getElementById(id)?.value;
    if (v === '' || v === undefined || v === null) return null;
    const n = parseFloat(v);
    return isNaN(n) ? null : n;
}

function todayStr() {
    return new Date().toISOString().split('T')[0];
}

function normalizeRatesData(data) {
    data.schemaVersion = data.schemaVersion || '0.7';
    if (!data.typologySchema) {
        data.typologySchema = {
            economic: 'Higher score means stronger upside or volatility in compensation.',
            flexibility: 'Higher score means faster or more demanding operational response from load.',
            programmatic: 'Higher score means more complex telemetry, baseline, aggregation, or compliance burden.'
        };
    }
    data.sectorProfiles = normalizeSectorProfiles(data.sectorProfiles);
    for (const region of Object.values(data.regions || {})) {
        region.programs = (region.programs || []).map(program => ({
            ...program,
            typology: ensureProgramTypology(program)
        }));
    }
}

function getFilteredPolicyRows() {
    if (!deltaPolicyData?.rows?.length) return [];
    const statusFilter = document.getElementById('policy-status-filter')?.value || 'all';
    const scopeFilter = document.getElementById('policy-scope-filter')?.value || 'all';
    return deltaPolicyData.rows.filter(row => {
        if (statusFilter !== 'all' && row.status !== statusFilter) return false;
        if (scopeFilter === 'selected' && selectedRegion) {
            return Array.isArray(row.regions) && row.regions.includes(selectedRegion);
        }
        if (scopeFilter === 'selected' && !selectedRegion) return false;
        return true;
    });
}

function renderPolicyIntelligence() {
    const kpiEl = document.getElementById('policy-kpis');
    const tableEl = document.getElementById('policy-table-body');
    const emptyEl = document.getElementById('policy-empty-state');
    if (!kpiEl || !tableEl) return;

    if (!deltaPolicyData?.rows?.length) {
        kpiEl.innerHTML = '<div class="policy-kpi"><div class="label">DELTa</div><div class="value">Unavailable</div><div class="meta">Run analysis/build_delta_dashboard_data.py</div></div>';
        tableEl.innerHTML = '<tr><td colspan="6" style="color:#94a3b8;">No DELTa records loaded.</td></tr>';
        if (chartPolicyStatus) chartPolicyStatus.destroy();
        if (chartPolicyRegion) chartPolicyRegion.destroy();
        if (emptyEl) {
            emptyEl.style.display = 'block';
            emptyEl.textContent = 'DELTa summary data is unavailable.';
        }
        return;
    }

    const filtered = getFilteredPolicyRows();
    const statusFilter = document.getElementById('policy-status-filter')?.value || 'all';
    const scopeFilter = document.getElementById('policy-scope-filter')?.value || 'all';

    if (!filtered.length) {
        kpiEl.innerHTML = `
            <div class="policy-kpi"><div class="label">Records</div><div class="value">0</div><div class="meta">No rows match current filters</div></div>
            <div class="policy-kpi"><div class="label">Approval Rate</div><div class="value">N/A</div><div class="meta">Try broader filters</div></div>
            <div class="policy-kpi"><div class="label">Median Min Demand</div><div class="value">N/A</div><div class="meta">No comparable rows</div></div>
        `;
        tableEl.innerHTML = '<tr><td colspan="6" style="color:#94a3b8;">No records match current filters. Try Status=All and Scope=All regions.</td></tr>';

        if (chartPolicyStatus) chartPolicyStatus.destroy();
        if (chartPolicyRegion) chartPolicyRegion.destroy();

        const statusCanvas = document.getElementById('chart-policy-status');
        const regionCanvas = document.getElementById('chart-policy-region');
        if (statusCanvas) {
            chartPolicyStatus = new Chart(statusCanvas, {
                type: 'bar',
                data: { labels: ['No data'], datasets: [{ label: 'Records', data: [0], backgroundColor: ['#334155'] }] },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                        y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } }
                    }
                }
            });
        }
        if (regionCanvas) {
            chartPolicyRegion = new Chart(regionCanvas, {
                type: 'bar',
                data: { labels: ['No data'], datasets: [{ label: 'DELTa entries', data: [0], backgroundColor: ['#334155'] }] },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                        y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } }
                    }
                }
            });
        }

        if (emptyEl) {
            emptyEl.style.display = 'block';
            emptyEl.textContent = `No DELTa rows for Status=${statusFilter} and Scope=${scopeFilter === 'selected' ? 'Selected map region' : 'All regions'}.`;
        }
        return;
    }

    if (emptyEl) {
        emptyEl.style.display = 'none';
        emptyEl.textContent = '';
    }

    const minDemandValues = filtered.map(row => Number(row.minimumDemandMw)).filter(v => Number.isFinite(v));
    const approved = filtered.filter(row => row.status === 'Approved').length;
    const pending = filtered.filter(row => row.status === 'Proposed / Pending').length;
    const medianDemand = medianNumber(minDemandValues);

    kpiEl.innerHTML = `
        <div class="policy-kpi"><div class="label">Records</div><div class="value">${filtered.length}</div><div class="meta">Filtered DELTa entries</div></div>
        <div class="policy-kpi"><div class="label">Approval Rate</div><div class="value">${filtered.length ? ((approved / filtered.length) * 100).toFixed(1) : '0.0'}%</div><div class="meta">Approved ${approved} · Pending ${pending}</div></div>
        <div class="policy-kpi"><div class="label">Median Min Demand</div><div class="value">${medianDemand === null ? 'N/A' : medianDemand.toFixed(1) + ' MW'}</div><div class="meta">From rows with specified threshold</div></div>
    `;

    const topRows = filtered.slice(0, 80);
    tableEl.innerHTML = topRows.map(row => {
        const statusClass = row.status === 'Approved' ? 'approved' : 'pending';
        return `
            <tr>
                <td>${escapeHtml(row.state || 'N/A')}</td>
                <td>${escapeHtml(row.utility || 'N/A')}</td>
                <td>${escapeHtml(row.tariff || 'N/A')}</td>
                <td><span class="policy-tag ${statusClass}">${escapeHtml(row.status || 'Unknown')}</span></td>
                <td>${row.minimumDemandMw === null || row.minimumDemandMw === undefined ? 'N/S' : Number(row.minimumDemandMw).toFixed(1)}</td>
                <td>${escapeHtml(row.isoRto || 'N/A')}</td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="6" style="color:#94a3b8;">No records match current filter.</td></tr>';

    const statusAgg = new Map();
    for (const row of filtered) {
        const key = row.status || 'Unknown';
        statusAgg.set(key, (statusAgg.get(key) || 0) + 1);
    }

    const regionAgg = new Map();
    for (const row of filtered) {
        const rowRegions = Array.isArray(row.regions) ? row.regions : [];
        if (!rowRegions.length) {
            regionAgg.set('Other', (regionAgg.get('Other') || 0) + 1);
            continue;
        }
        for (const regionId of rowRegions) {
            regionAgg.set(regionId, (regionAgg.get(regionId) || 0) + 1);
        }
    }

    const statusCanvas = document.getElementById('chart-policy-status');
    const regionCanvas = document.getElementById('chart-policy-region');
    if (statusCanvas) {
        if (chartPolicyStatus) chartPolicyStatus.destroy();
        chartPolicyStatus = new Chart(statusCanvas, {
            type: 'bar',
            data: {
                labels: Array.from(statusAgg.keys()),
                datasets: [{
                    label: 'Records',
                    data: Array.from(statusAgg.values()),
                    backgroundColor: ['#4ade80', '#fbbf24', '#94a3b8']
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                    y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } }
                }
            }
        });
    }

    if (regionCanvas) {
        if (chartPolicyRegion) chartPolicyRegion.destroy();
        const regionLabels = Array.from(regionAgg.keys());
        chartPolicyRegion = new Chart(regionCanvas, {
            type: 'bar',
            data: {
                labels: regionLabels,
                datasets: [{
                    label: 'DELTa entries',
                    data: Array.from(regionAgg.values()),
                    backgroundColor: regionLabels.map(label => REGION_COLORS[label] || '#64748b')
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                    y: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } }
                }
            }
        });
    }
}

function medianNumber(values) {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    if (sorted.length % 2) return sorted[mid];
    return (sorted[mid - 1] + sorted[mid]) / 2;
}

function ensureProgramTypology(program) {
    const fallback = inferTypologyFromProgram(program);
    const existing = program.typology || {};
    return {
        economic: normalizeTypologyDimension(existing.economic, fallback.economic),
        flexibility: normalizeTypologyDimension(existing.flexibility, fallback.flexibility),
        programmatic: normalizeTypologyDimension(existing.programmatic, fallback.programmatic)
    };
}

function normalizeTypologyDimension(existing, fallback) {
    return {
        score: Number.isFinite(existing?.score) ? existing.score : fallback.score,
        label: existing?.label || fallback.label,
        notes: existing?.notes || fallback.notes
    };
}

function inferTypologyFromProgram(program = {}) {
    const rateMax = Number(program.rate_max) || 0;
    const notification = String(program.notificationTime || '').toLowerCase();
    const market = String(program.market || '').toLowerCase();
    const compensation = String(program.compensation || '').toLowerCase();
    const minSize = Number(program.minSize_kW) || 0;

    let economic = { score: 2, label: 'Moderate upside', notes: 'Moderate settlement range or capacity value.' };
    if (rateMax >= 1000) economic = { score: 5, label: 'High upside', notes: 'Scarcity or emergency settlements can be very large but volatile.' };
    else if (rateMax >= 200) economic = { score: 4, label: 'Strong upside', notes: 'Meaningful revenue potential with market or event variability.' };
    else if (rateMax >= 50) economic = { score: 3, label: 'Market-linked', notes: 'Revenue tracks clearing price or LMP and can move materially.' };
    else if (rateMax > 0 && rateMax < 15) economic = { score: 1, label: 'Limited upside', notes: 'Payments are generally modest relative to emergency products.' };

    let flexibility = { score: 2, label: 'Day-ahead / event', notes: 'Operational response is planned or relatively slow.' };
    if (notification.includes('5-minute') || notification.includes('real-time')) flexibility = { score: 5, label: 'Real-time', notes: 'Requires near-continuous dispatchability or very fast response.' };
    else if (notification.includes('10')) flexibility = { score: 4, label: 'Fast response', notes: 'Suitable only for loads that can move on short notice.' };
    else if (notification.includes('30')) flexibility = { score: 3, label: 'Short notice', notes: 'Program expects sub-hour operational flexibility.' };
    else if (notification.includes('market-scheduled') || notification.includes('scheduled')) flexibility = { score: 1, label: 'Scheduled', notes: 'Best for loads that can plan shifts into market schedules.' };

    let complexityScore = 1;
    if (minSize >= 500) complexityScore += 1;
    if (minSize >= 1000) complexityScore += 1;
    if (market.includes('ancillary') || compensation.includes('lmp') || compensation.includes('auction') || compensation.includes('market clearing')) complexityScore += 1;
    if (market.includes('capacity') || market.includes('real-time')) complexityScore += 1;
    complexityScore = Math.max(1, Math.min(complexityScore, 5));
    const complexityLabels = {
        1: ['Low complexity', 'Enrollment and settlement requirements are relatively light.'],
        2: ['Light complexity', 'Some qualification and settlement requirements apply.'],
        3: ['Moderate complexity', 'Expect regular metering, baseline, or aggregation administration.'],
        4: ['High complexity', 'Program likely needs telemetry, aggregation discipline, or market operations support.'],
        5: ['Very high complexity', 'Operational and compliance burden is significant for direct participation.']
    };

    return {
        economic,
        flexibility,
        programmatic: {
            score: complexityScore,
            label: complexityLabels[complexityScore][0],
            notes: complexityLabels[complexityScore][1]
        }
    };
}

function getDefaultTypology() {
    return {
        economic: { score: 3, label: 'Market-linked', notes: 'Revenue follows the underlying market or procurement signal.' },
        flexibility: { score: 2, label: 'Day-ahead / event', notes: 'Operational response is planned or relatively slow.' },
        programmatic: { score: 3, label: 'Moderate complexity', notes: 'Program requires some settlement, metering, or registration effort.' }
    };
}

function getDefaultSectorProfiles() {
    return {
        dataCenters: {
            name: 'Data Centers',
            description: 'Default profile for a battery-backed large data center with flexible cooling, limited emergency generation use, and strict uptime obligations for core compute load.',
            portfolioMW: {
                battery: 3,
                cooling: 2,
                generator: 5
            },
            annualHours: {
                ancillary: 120,
                energy: 80,
                emergency: 10,
                capacityDays: 20,
                capacityMonths: 6
            },
            targets: {
                flexibility: 4,
                programmaticTolerance: 2
            },
            weights: {
                economic: 0.4,
                flexibility: 0.35,
                programmatic: 0.25
            },
            stackabilityFactor: 0.65,
            marketMultipliers: {
                ancillary: 1,
                energy: 0.75,
                emergency: 0.55,
                capacity: 0.85
            }
        }
    };
}

function normalizeSectorProfiles(existingProfiles = {}) {
    const defaults = getDefaultSectorProfiles();
    const dataCenters = existingProfiles.dataCenters || {};
    return {
        ...defaults,
        ...existingProfiles,
        dataCenters: {
            ...defaults.dataCenters,
            ...dataCenters,
            portfolioMW: {
                ...defaults.dataCenters.portfolioMW,
                ...(dataCenters.portfolioMW || {})
            },
            annualHours: {
                ...defaults.dataCenters.annualHours,
                ...(dataCenters.annualHours || {})
            },
            targets: {
                ...defaults.dataCenters.targets,
                ...(dataCenters.targets || {})
            },
            weights: {
                ...defaults.dataCenters.weights,
                ...(dataCenters.weights || {})
            },
            marketMultipliers: {
                ...defaults.dataCenters.marketMultipliers,
                ...(dataCenters.marketMultipliers || {})
            }
        }
    };
}

function getDataCenterProfile() {
    return ratesData?.sectorProfiles?.dataCenters || getDefaultSectorProfiles().dataCenters;
}

function summarizeRegionTypology(region) {
    const dimensions = ['economic', 'flexibility', 'programmatic'];
    const summary = {};
    for (const dimension of dimensions) {
        const scores = region.programs
            .map(program => ensureProgramTypology(program)[dimension]?.score)
            .filter(score => Number.isFinite(score));
        const avg = scores.length ? Math.round((scores.reduce((total, score) => total + score, 0) / scores.length) * 10) / 10 : null;
        const exemplar = region.programs.length ? ensureProgramTypology(region.programs[0])[dimension] : getDefaultTypology()[dimension];
        summary[dimension] = {
            score: avg ?? exemplar.score,
            label: exemplar.label,
            notes: exemplar.notes
        };
    }
    return summary;
}

function getSelectedCalibratedScenario() {
    const flexdc = ratesData?.analysis?.flexdcSim;
    if (!flexdc?.scenarios) return null;
    if (selectedFlexScenario && flexdc.scenarios[selectedFlexScenario]) return selectedFlexScenario;
    return flexdc.currentScenario || Object.keys(flexdc.scenarios)[0] || null;
}

function renderDataCenterAnalysis() {
    if (!ratesData?.regions) return;
    const profile = getDataCenterProfile();
    const flexdc = ratesData.analysis?.flexdcSim || null;
    const scenarioName = getSelectedCalibratedScenario();
    const selectedScenario = scenarioName ? flexdc?.scenarios?.[scenarioName] : null;
    const useCalibrated = dataCenterAnalysisMode === 'calibrated' && !!selectedScenario;
    const calibratedResults = useCalibrated ? selectedScenario.regions : null;

    const analyses = calibratedResults
        ? Object.entries(calibratedResults)
            .map(([id, result]) => ({
                id,
                region: ratesData.regions[id],
                ...result
            }))
            .sort((a, b) => b.overallScore - a.overallScore)
        : Object.entries(ratesData.regions)
            .map(([id, region]) => ({ id, region, ...computeDataCenterRegionAnalysis(id, region, profile) }))
            .sort((a, b) => b.overallScore - a.overallScore);

    const profileEl = document.getElementById('data-center-profile');
    const contentEl = document.getElementById('data-center-content');
    const modeSelect = document.getElementById('dc-analysis-mode');
    const scenarioSelect = document.getElementById('dc-scenario-select');
    const metricsEl = document.getElementById('dc-sim-metrics');
    if (!profileEl || !contentEl) return;

    if (modeSelect) {
        modeSelect.value = useCalibrated ? 'calibrated' : 'heuristic';
    }
    if (scenarioSelect) {
        const options = Object.keys(flexdc?.scenarios || {});
        scenarioSelect.innerHTML = options.map(name => `<option value="${escapeAttr(name)}">${escapeHtml(name)}</option>`).join('');
        scenarioSelect.disabled = !options.length || !useCalibrated;
        if (options.length && scenarioName) scenarioSelect.value = scenarioName;
    }
    if (metricsEl) {
        if (useCalibrated && selectedScenario?.simMetrics) {
            const m = selectedScenario.simMetrics;
            metricsEl.style.display = 'block';
            metricsEl.innerHTML = `
                <strong>Scenario:</strong> ${escapeHtml(scenarioName)} ·
                <strong>Deliverability:</strong> ${(Number(m.deliverabilityFactor) * 100).toFixed(1)}% ·
                <strong>Tracking p90:</strong> ${Number(m.trackingError90).toFixed(3)} ·
                <strong>QoS violation ratio:</strong> ${(Number(m.qosViolationRateByType) * 100).toFixed(1)}%
            `;
        } else {
            metricsEl.style.display = 'none';
            metricsEl.textContent = '';
        }
    }

    profileEl.innerHTML = `
        <h3>${escapeHtml(profile.name)} Flexibility Lens</h3>
        <p>${escapeHtml(profile.description)}</p>
        <div class="assumption-grid">
            <div class="assumption-box"><div class="label">Battery / UPS</div><div class="value">${formatMw(profile.portfolioMW.battery)}</div></div>
            <div class="assumption-box"><div class="label">Cooling Flex</div><div class="value">${formatMw(profile.portfolioMW.cooling)}</div></div>
            <div class="assumption-box"><div class="label">Generator-backed MW</div><div class="value">${formatMw(profile.portfolioMW.generator)}</div></div>
            <div class="assumption-box"><div class="label">Annual Hours Assumed</div><div class="value">A:${profile.annualHours.ancillary} E:${profile.annualHours.energy} X:${profile.annualHours.emergency}</div></div>
        </div>
        <p class="section-caption">Scores reflect market attractiveness for a default battery-backed data center portfolio. Estimated annual value is a scenario-based gross range, not a market guarantee.${useCalibrated ? ' Results are calibrated by FlexDC-Sim outputs for the selected scenario.' : ''}</p>
    `;

    contentEl.innerHTML = analyses.map((analysis, index) => `
        <div class="sector-rank-card ${selectedRegion === analysis.id ? 'active' : ''}">
            <div class="sector-rank-head">
                <h4>${index + 1}. ${escapeHtml(analysis.region.name)} <span style="font-size:11px;color:#94a3b8;">(${analysis.id})</span></h4>
                <div class="sector-rank-score">${analysis.overallScore.toFixed(1)}/5</div>
            </div>
            <div class="sector-rank-meta">Estimated gross annual value: ${formatCurrencyRange(analysis.annualValueLow, analysis.annualValueHigh)} · Best category: ${escapeHtml(analysis.bestCategoryLabel)}</div>
            <div class="sector-rank-grid">
                <div class="sector-mini-box"><div class="label">Economic Fit</div><div class="value">${analysis.economicFit.toFixed(1)}/5</div></div>
                <div class="sector-mini-box"><div class="label">Flexibility Fit</div><div class="value">${analysis.flexibilityFit.toFixed(1)}/5</div></div>
                <div class="sector-mini-box"><div class="label">Programmatic Fit</div><div class="value">${analysis.programmaticFit.toFixed(1)}/5</div></div>
            </div>
            <div class="sector-best-program"><strong>Best programs:</strong> ${escapeHtml(analysis.bestProgramsSummary)}</div>
        </div>
    `).join('');

    renderDataCenterChart(analyses);
}

function computeDataCenterRegionAnalysis(regionId, region, profile) {
    const programAnalyses = region.programs.map(program => computeDataCenterProgramAnalysis(program, profile));
    const dimensionAverage = key => average(programAnalyses.map(item => item[key]));
    const economicFit = dimensionAverage('economicFit');
    const flexibilityFit = dimensionAverage('flexibilityFit');
    const programmaticFit = dimensionAverage('programmaticFit');
    const overallScore = (
        economicFit * profile.weights.economic +
        flexibilityFit * profile.weights.flexibility +
        programmaticFit * profile.weights.programmatic
    );

    const bestByCategory = {};
    for (const item of programAnalyses) {
        const key = item.program.marketCategory || 'other';
        if (!bestByCategory[key] || item.score > bestByCategory[key].score) {
            bestByCategory[key] = item;
        }
    }

    const selectedPrograms = Object.values(bestByCategory);
    const annualValueLow = selectedPrograms.reduce((sum, item) => sum + item.annualLow, 0) * profile.stackabilityFactor;
    const annualValueHigh = selectedPrograms.reduce((sum, item) => sum + item.annualHigh, 0) * profile.stackabilityFactor;
    const bestOverallProgram = [...programAnalyses].sort((a, b) => b.score - a.score)[0];
    const bestCategory = bestOverallProgram?.program.marketCategory || 'energy';
    const bestProgramsSummary = selectedPrograms
        .sort((a, b) => b.score - a.score)
        .map(item => `${capitalize(item.program.marketCategory || 'other')}: ${item.program.name}`)
        .join(' · ');

    return {
        regionId,
        economicFit,
        flexibilityFit,
        programmaticFit,
        overallScore,
        annualValueLow,
        annualValueHigh,
        bestCategoryLabel: capitalize(bestCategory),
        bestProgramsSummary: bestProgramsSummary || 'No program data',
        topProgram: bestOverallProgram?.program?.name || 'N/A'
    };
}

function computeDataCenterProgramAnalysis(program, profile) {
    const typology = ensureProgramTypology(program);
    const economicFit = typology.economic.score;
    const flexibilityFit = clamp(5 - Math.abs(typology.flexibility.score - profile.targets.flexibility), 1, 5);
    const programmaticFit = clamp(5 - Math.max(0, typology.programmatic.score - profile.targets.programmaticTolerance), 1, 5);
    const score = (
        economicFit * profile.weights.economic +
        flexibilityFit * profile.weights.flexibility +
        programmaticFit * profile.weights.programmatic
    );
    const { low, high } = estimateProgramAnnualValue(program, profile);
    return {
        program,
        economicFit,
        flexibilityFit,
        programmaticFit,
        score,
        annualLow: low,
        annualHigh: high
    };
}

function estimateProgramAnnualValue(program, profile) {
    const category = program.marketCategory || 'energy';
    const rateMin = Number(program.rate_min) || 0;
    const rateMax = Number(program.rate_max) || rateMin;
    const unit = String(program.rate_unit || '').toLowerCase();
    const flexibleMw = getFlexibleMwForCategory(category, profile);
    const multiplier = profile.marketMultipliers[category] ?? 1;
    let low = 0;
    let high = 0;

    if (!flexibleMw || (!rateMin && !rateMax)) {
        return { low: 0, high: 0 };
    }

    if (unit.includes('/mwh') || unit.includes('/mw-hr') || unit.includes('/mw per hour')) {
        const hours = profile.annualHours[category] || 0;
        low = rateMin * flexibleMw * hours * multiplier;
        high = rateMax * flexibleMw * hours * multiplier;
    } else if (unit.includes('/mw-day')) {
        const days = profile.annualHours.capacityDays || 0;
        low = rateMin * flexibleMw * days * multiplier;
        high = rateMax * flexibleMw * days * multiplier;
    } else if (unit.includes('/kw-month')) {
        const months = profile.annualHours.capacityMonths || 0;
        low = rateMin * flexibleMw * 1000 * months * multiplier;
        high = rateMax * flexibleMw * 1000 * months * multiplier;
    }

    return { low, high };
}

function getFlexibleMwForCategory(category, profile) {
    const battery = Number(profile.portfolioMW.battery) || 0;
    const cooling = Number(profile.portfolioMW.cooling) || 0;
    const generator = Number(profile.portfolioMW.generator) || 0;
    if (category === 'ancillary') return battery + cooling * 0.25;
    if (category === 'energy') return battery * 0.5 + cooling;
    if (category === 'emergency') return battery + generator * 0.6;
    if (category === 'capacity') return battery + cooling + generator * 0.4;
    return battery + cooling;
}

function renderDataCenterChart(analyses) {
    const canvas = document.getElementById('chart-data-centers');
    if (!canvas) return;
    if (chartDataCenters) chartDataCenters.destroy();
    chartDataCenters = new Chart(canvas, {
        type: 'bar',
        data: {
            labels: analyses.map(item => item.id),
            datasets: [
                {
                    label: 'Data center fit score',
                    data: analyses.map(item => Number(item.overallScore.toFixed(2))),
                    backgroundColor: analyses.map(item => (REGION_COLORS[item.id] || '#38bdf8') + 'cc'),
                    borderColor: analyses.map(item => REGION_COLORS[item.id] || '#38bdf8'),
                    borderWidth: 1,
                    yAxisID: 'y'
                },
                {
                    label: 'Annual value high ($k)',
                    data: analyses.map(item => Math.round(item.annualValueHigh / 1000)),
                    type: 'line',
                    borderColor: '#f8fafc',
                    backgroundColor: '#f8fafc',
                    pointRadius: 4,
                    tension: 0.25,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            plugins: { legend: { labels: { color: '#e2e8f0' } } },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                y: { min: 0, max: 5, ticks: { color: '#94a3b8' }, grid: { color: '#1e293b' } },
                y1: {
                    position: 'right',
                    ticks: { color: '#cbd5e1', callback: value => '$' + value + 'k' },
                    grid: { drawOnChartArea: false }
                }
            }
        }
    });
}

function renderTypologyBox(title, dimension) {
    return `
        <div class="typology-box">
            <div class="label">${escapeHtml(title)}</div>
            <div class="value">${escapeHtml(String(dimension.score ?? 'N/A'))}/5</div>
            <div class="meta">${escapeHtml(dimension.label || 'Unclassified')}</div>
            <div class="notes">${escapeHtml(dimension.notes || '')}</div>
        </div>
    `;
}

function renderProgramTypologyPills(program) {
    const typology = ensureProgramTypology(program);
    const dimensions = [
        ['economic', 'E', typology.economic],
        ['flexibility', 'F', typology.flexibility],
        ['programmatic', 'P', typology.programmatic]
    ];
    return `
        <div class="typology-pills">
            ${dimensions.map(([key, shortLabel, dimension]) => `
                <span class="typology-pill ${key}" title="${escapeAttr(dimension.notes || '')}">${shortLabel} ${escapeHtml(String(dimension.score))}/5 · ${escapeHtml(dimension.label)}</span>
            `).join('')}
        </div>
    `;
}

function renderTypologyFields(typology) {
    const safeTypology = {
        economic: typology?.economic || getDefaultTypology().economic,
        flexibility: typology?.flexibility || getDefaultTypology().flexibility,
        programmatic: typology?.programmatic || getDefaultTypology().programmatic
    };
    return `
        <div class="form-group" style="margin-top:18px;">
            <label style="font-size:13px;color:#f8fafc;">Typology</label>
            <p class="section-caption">Use 1-5 scores. Higher economic means more upside; higher flexibility and programmatic mean more demanding operating and compliance requirements.</p>
        </div>
        ${renderTypologyFieldGroup('Economic', 'eco', safeTypology.economic)}
        ${renderTypologyFieldGroup('Flexibility', 'flex', safeTypology.flexibility)}
        ${renderTypologyFieldGroup('Programmatic', 'prog', safeTypology.programmatic)}
    `;
}

function renderTypologyFieldGroup(title, prefix, dimension) {
    return `
        <div class="form-group">
            <label>${escapeHtml(title)}</label>
            <div class="form-row">
                <div class="form-group"><label>Score</label><input id="ep-${prefix}-score" type="number" min="1" max="5" value="${dimension.score ?? ''}"></div>
                <div class="form-group"><label>Label</label><input id="ep-${prefix}-label" value="${escapeAttr(dimension.label || '')}"></div>
            </div>
            <div class="form-group"><label>Notes</label><input id="ep-${prefix}-notes" value="${escapeAttr(dimension.notes || '')}"></div>
        </div>
    `;
}

function readTypologyFields(prefix) {
    return {
        economic: readTypologyDimension(prefix, 'eco', getDefaultTypology().economic),
        flexibility: readTypologyDimension(prefix, 'flex', getDefaultTypology().flexibility),
        programmatic: readTypologyDimension(prefix, 'prog', getDefaultTypology().programmatic)
    };
}

function readTypologyDimension(prefix, shortPrefix, fallback) {
    const scoreValue = parseInt(document.getElementById(`${prefix}-${shortPrefix}-score`)?.value, 10);
    return {
        score: Number.isFinite(scoreValue) ? Math.max(1, Math.min(scoreValue, 5)) : fallback.score,
        label: document.getElementById(`${prefix}-${shortPrefix}-label`)?.value || fallback.label,
        notes: document.getElementById(`${prefix}-${shortPrefix}-notes`)?.value || fallback.notes
    };
}

function average(values) {
    const filtered = values.filter(value => Number.isFinite(value));
    if (!filtered.length) return 0;
    return filtered.reduce((sum, value) => sum + value, 0) / filtered.length;
}

function clamp(value, min, max) {
    return Math.max(min, Math.min(value, max));
}

function capitalize(value) {
    return String(value || '').charAt(0).toUpperCase() + String(value || '').slice(1);
}

function formatMw(value) {
    return `${Number(value || 0).toFixed(1)} MW`;
}

function formatCurrencyRange(low, high) {
    return `${formatCurrency(low)}-${formatCurrency(high)}`;
}

function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 0
    }).format(Number(value || 0));
}

// ── Init ──────────────────────────────────────────────
init();

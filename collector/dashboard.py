"""
Generates docs/index.html — an editorial-style dashboard the user can serve
via GitHub Pages. Reads the CSVs and produces a self-contained HTML file
with charts rendered by Chart.js (loaded from CDN).

Includes an in-page editor panel that commits searches.yaml back to the
GitHub repo via the REST API using the user's personal access token
(stored in browser localStorage).
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime

from collector import storage

ROOT = os.path.dirname(os.path.dirname(__file__))
DOCS_DIR = os.path.join(ROOT, "docs")
OUT_PATH = os.path.join(DOCS_DIR, "index.html")
SEARCHES_PATH = os.path.join(ROOT, "searches.yaml")


def _group_min_per_day(rows: list[dict], price_key: str = "price") -> dict:
    """For each search_id, get min price per UTC date."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        sid = r["search_id"]
        try:
            p = float(r[price_key])
        except (KeyError, ValueError):
            continue
        ts = r.get("timestamp", "")
        day = ts[:10] if len(ts) >= 10 else ""
        if not day:
            continue
        cur = out[sid].get(day)
        if cur is None or p < cur:
            out[sid][day] = p
    return out


def _series_payload(rows: list[dict]) -> list[dict]:
    grouped = _group_min_per_day(rows)
    meta: dict[str, dict] = {}
    for r in rows:
        sid = r["search_id"]
        if sid not in meta:
            meta[sid] = {
                "nickname": r.get("nickname", sid),
                "currency": r.get("currency", ""),
            }

    series = []
    for sid, days in grouped.items():
        sorted_days = sorted(days.items())
        prices = [p for _, p in sorted_days]
        latest = prices[-1] if prices else None
        prev = prices[-2] if len(prices) >= 2 else None
        all_time_min = min(prices) if prices else None
        all_time_max = max(prices) if prices else None
        delta_pct = None
        if latest is not None and prev is not None and prev > 0:
            delta_pct = (latest - prev) / prev * 100

        series.append({
            "id": sid,
            "nickname": meta[sid]["nickname"],
            "currency": meta[sid]["currency"],
            "labels": [d for d, _ in sorted_days],
            "data": prices,
            "latest": latest,
            "prev": prev,
            "delta_pct": delta_pct,
            "min": all_time_min,
            "max": all_time_max,
            "samples": len(prices),
        })
    series.sort(key=lambda s: s["nickname"].lower())
    return series


def _read_searches_yaml_text() -> str:
    try:
        with open(SEARCHES_PATH, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Travel Price Tracker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/js-yaml@4.1.0/dist/js-yaml.min.js"></script>
<style>
  :root {
    --ink: #1a1410; --paper: #f4ede0; --paper-dark: #ebe0cc; --rule: #1a1410;
    --accent: #c8401c; --accent-soft: #e8a48e; --good: #2d5a2d; --bad: #c8401c;
    --muted: #6b5d4e;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; padding: 0; background: var(--paper); color: var(--ink);
    font-family: 'Fraunces', Georgia, serif;
  }
  body {
    background-image:
      radial-gradient(circle at 20% 10%, rgba(200,64,28,.04) 0%, transparent 40%),
      radial-gradient(circle at 80% 80%, rgba(45,90,45,.04) 0%, transparent 40%);
    min-height: 100vh; padding: 0 0 6rem 0;
  }
  .masthead {
    border-bottom: 3px double var(--rule);
    padding: 2.4rem 3rem 1.2rem 3rem;
    display: flex; align-items: baseline; justify-content: space-between;
    flex-wrap: wrap; gap: 1rem;
  }
  .masthead h1 {
    font-size: clamp(2.5rem, 6vw, 4.5rem); font-weight: 800; letter-spacing: -0.03em;
    margin: 0; line-height: 0.95; font-style: italic;
  }
  .masthead .meta {
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    text-transform: uppercase; letter-spacing: 0.15em; color: var(--muted);
    text-align: right;
  }
  .container { padding: 0 3rem; max-width: 1400px; margin: 0 auto; }
  .section-rule {
    display: flex; align-items: center; gap: 1.5rem;
    margin: 3rem 0 1.5rem 0;
  }
  .section-rule h2 {
    font-size: 0.85rem; font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase; letter-spacing: 0.2em; margin: 0; white-space: nowrap;
  }
  .section-rule .line { flex: 1; height: 1px; background: var(--rule); }
  .section-rule button.btn-text {
    background: var(--ink); color: var(--paper); border: 1.5px solid var(--ink);
    padding: 0.4rem 0.9rem; font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.15em;
    cursor: pointer; transition: all 0.15s;
  }
  .section-rule button.btn-text:hover { background: var(--accent); border-color: var(--accent); }
  .grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 1.5rem;
  }
  .card {
    background: var(--paper); border: 1.5px solid var(--ink);
    padding: 1.5rem; position: relative; transition: transform 0.15s ease;
  }
  .card:hover { transform: translateY(-2px); }
  .card .nickname {
    font-size: 1.4rem; font-weight: 600; line-height: 1.15;
    margin: 0 0 0.25rem 0; font-style: italic;
  }
  .card .id {
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.1em;
    color: var(--muted); margin-bottom: 1rem;
  }
  .stats {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 0;
    border-top: 1px solid var(--ink); border-bottom: 1px solid var(--ink);
    margin: 1rem 0;
  }
  .stat { padding: 0.7rem 0.5rem; border-right: 1px solid var(--ink); text-align: center; }
  .stat:last-child { border-right: none; }
  .stat-label {
    font-family: 'JetBrains Mono', monospace; font-size: 0.6rem;
    text-transform: uppercase; letter-spacing: 0.15em;
    color: var(--muted); margin-bottom: 0.25rem;
  }
  .stat-value { font-size: 1.15rem; font-weight: 600; }
  .stat-value.good { color: var(--good); } .stat-value.bad { color: var(--bad); }
  .chart-wrap { position: relative; height: 180px; margin-top: 0.5rem; }
  .empty {
    text-align: center; padding: 4rem 2rem;
    border: 1px dashed var(--rule); color: var(--muted);
  }
  .empty h3 { font-style: italic; font-weight: 600; font-size: 1.5rem; }
  footer {
    text-align: center; margin-top: 4rem; padding-top: 2rem;
    border-top: 1px solid var(--rule);
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.15em; color: var(--muted);
  }
  .delta-arrow { font-size: 0.85em; margin-right: 0.15em; }

  /* ============ EDITOR PANEL ============ */
  #editor-overlay {
    position: fixed; inset: 0; background: rgba(26,20,16,0.55);
    backdrop-filter: blur(4px); z-index: 100; display: none;
    overflow-y: auto; padding: 2rem;
  }
  #editor-overlay.open { display: block; }
  .editor-panel {
    background: var(--paper); max-width: 900px; margin: 1rem auto;
    border: 2px solid var(--ink); box-shadow: 12px 12px 0 var(--ink);
    padding: 2rem;
  }
  .editor-panel h2 {
    font-style: italic; font-weight: 800; font-size: 2.2rem;
    margin: 0 0 0.25rem 0; letter-spacing: -0.02em;
  }
  .editor-panel .subhead {
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.15em;
    color: var(--muted); margin-bottom: 1.5rem;
  }
  .editor-panel .toolbar {
    display: flex; gap: 0.5rem; justify-content: flex-end;
    margin-bottom: 1.5rem; flex-wrap: wrap;
  }
  .editor-panel .toolbar button {
    background: var(--paper); color: var(--ink);
    border: 1.5px solid var(--ink); padding: 0.5rem 1rem;
    font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
    text-transform: uppercase; letter-spacing: 0.12em;
    cursor: pointer; transition: all 0.15s;
  }
  .editor-panel .toolbar button:hover { background: var(--ink); color: var(--paper); }
  .editor-panel .toolbar button.primary {
    background: var(--accent); color: white; border-color: var(--accent);
  }
  .editor-panel .toolbar button.primary:hover { background: var(--ink); border-color: var(--ink); }
  .editor-panel .toolbar button:disabled { opacity: 0.4; cursor: not-allowed; }

  .token-section {
    background: var(--paper-dark); border: 1.5px solid var(--ink);
    padding: 1rem; margin-bottom: 1.5rem; font-size: 0.95rem;
  }
  .token-section.has-token {
    background: rgba(45,90,45,0.08); border-color: var(--good);
  }
  .token-section label {
    display: block; font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.12em;
    margin-bottom: 0.4rem;
  }
  .token-section input[type=password] {
    width: 100%; padding: 0.55rem; border: 1.5px solid var(--ink);
    background: var(--paper); font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
  }
  .token-section .hint {
    font-size: 0.85rem; color: var(--muted);
    margin-top: 0.5rem; line-height: 1.4;
  }
  .token-section .hint a { color: var(--accent); }

  .ed-section-title {
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    text-transform: uppercase; letter-spacing: 0.18em;
    margin: 1.5rem 0 0.75rem 0;
    border-bottom: 1px solid var(--ink); padding-bottom: 0.4rem;
  }
  .ed-row {
    border: 1.5px solid var(--ink); padding: 1rem;
    margin-bottom: 0.75rem; background: var(--paper); position: relative;
  }
  .ed-row .row-head {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 0.7rem; padding-bottom: 0.5rem;
    border-bottom: 1px dashed var(--rule);
  }
  .ed-row .row-head .row-id {
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted);
  }
  .ed-row .row-head button.del {
    background: transparent; border: 1px solid var(--bad); color: var(--bad);
    padding: 0.2rem 0.6rem; font-family: 'JetBrains Mono', monospace;
    font-size: 0.65rem; text-transform: uppercase; cursor: pointer;
    letter-spacing: 0.12em;
  }
  .ed-row .row-head button.del:hover { background: var(--bad); color: white; }
  .ed-grid {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.6rem 0.8rem;
  }
  .ed-grid .field { display: flex; flex-direction: column; }
  .ed-grid .field.wide { grid-column: span 2; }
  .ed-grid label {
    font-family: 'JetBrains Mono', monospace; font-size: 0.62rem;
    text-transform: uppercase; letter-spacing: 0.12em;
    color: var(--muted); margin-bottom: 0.2rem;
  }
  .ed-grid input, .ed-grid select {
    padding: 0.4rem 0.55rem; border: 1px solid var(--ink); background: var(--paper);
    font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; color: var(--ink);
  }
  .ed-grid input:focus, .ed-grid select:focus {
    outline: 2px solid var(--accent); outline-offset: -1px;
  }

  .add-btn {
    width: 100%; padding: 0.7rem; background: var(--paper); color: var(--ink);
    border: 1.5px dashed var(--ink); font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em;
    cursor: pointer; margin-top: 0.5rem; transition: all 0.15s;
  }
  .add-btn:hover { background: var(--ink); color: var(--paper); border-style: solid; }

  .save-status {
    margin-top: 1rem; padding: 0.8rem; border: 1.5px solid var(--ink);
    font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
    display: none; white-space: pre-wrap;
  }
  .save-status.show { display: block; }
  .save-status.ok {
    background: rgba(45,90,45,0.12); border-color: var(--good); color: var(--good);
  }
  .save-status.err {
    background: rgba(200,64,28,0.12); border-color: var(--bad); color: var(--bad);
  }

  .save-banner {
    background: var(--ink); color: var(--paper); padding: 0.75rem 1rem;
    margin-top: 1rem; font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem; line-height: 1.5;
  }
  .save-banner a { color: var(--accent-soft); }

  @media (max-width: 600px) {
    .masthead, .container { padding-left: 1.25rem; padding-right: 1.25rem; }
    .grid { grid-template-columns: 1fr; }
    .editor-panel { padding: 1.25rem; box-shadow: 6px 6px 0 var(--ink); }
    #editor-overlay { padding: 0.5rem; }
  }
</style>
</head>
<body>

<header class="masthead">
  <h1>Travel<br/>Price Tracker</h1>
  <div class="meta">
    Vol. 01 &middot; Issue {issue}<br/>
    Updated {updated}<br/>
    {flight_count} flights &middot; {hotel_count} hotels
  </div>
</header>

<div class="container">

  <div class="section-rule">
    <h2>✈ Flights</h2>
    <div class="line"></div>
    <button class="btn-text" onclick="openEditor()">Edit searches</button>
  </div>

  {flights_section}

  <div class="section-rule">
    <h2>🏨 Hotels</h2>
    <div class="line"></div>
  </div>

  {hotels_section}

  <footer>
    Generated by collector &middot; Data via SerpAPI
  </footer>
</div>

<!-- ============ EDITOR PANEL ============ -->
<div id="editor-overlay" onclick="if(event.target===this)closeEditor()">
  <div class="editor-panel">
    <h2>Edit your searches</h2>
    <div class="subhead">Changes commit to <code>searches.yaml</code> in your GitHub repo</div>

    <div id="token-section" class="token-section">
      <label for="gh-token">GitHub Personal Access Token</label>
      <input type="password" id="gh-token" placeholder="github_pat_..." autocomplete="off" />
      <div class="hint">
        One-time setup &mdash; saved in this browser only.
        Token needs <strong>Contents: Read &amp; Write</strong> on this repo.
        <a href="https://github.com/settings/personal-access-tokens/new" target="_blank">Create one here</a>
        (Repository access &rarr; Only select repositories &rarr; pick <code>{repo_name}</code>;
        under Repository permissions, set Contents to Read and write).
      </div>
    </div>

    <div class="ed-section-title">Flights</div>
    <div id="flights-list"></div>
    <button class="add-btn" onclick="addFlight()">+ Add flight search</button>

    <div class="ed-section-title">Hotels</div>
    <div id="hotels-list"></div>
    <button class="add-btn" onclick="addHotel()">+ Add hotel search</button>

    <div class="toolbar" style="margin-top:1.5rem;">
      <button onclick="forgetToken()" id="btn-forget" style="display:none;">Forget token</button>
      <button onclick="closeEditor()">Cancel</button>
      <button class="primary" onclick="saveSearches()" id="btn-save">Save &amp; commit</button>
    </div>

    <div id="save-status" class="save-status"></div>

    <div class="save-banner">
      💡 After saving, your changes are live in the repo immediately,
      but new prices are only collected on the next scheduled run (daily at 09:00 IST).
      To see new searches in action right away, go to your repo's
      <a href="https://github.com/{repo_full}/actions" target="_blank">Actions tab</a>
      and trigger the workflow manually.
    </div>
  </div>
</div>

<script>
const flightSeries = {flights_json};
const hotelSeries = {hotels_json};
const REPO_FULL = "{repo_full}";
const CURRENT_YAML = {current_yaml_json};
const TOKEN_KEY = "tpt_github_token_v1";

function renderChart(canvasId, series, accentColor) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: series.labels,
      datasets: [{
        data: series.data, borderColor: accentColor,
        backgroundColor: accentColor + '20', borderWidth: 2,
        fill: true, tension: 0.25, pointRadius: 3,
        pointBackgroundColor: accentColor, pointBorderColor: '#f4ede0',
        pointBorderWidth: 1.5,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a1410',
          titleFont: { family: 'JetBrains Mono', size: 11 },
          bodyFont: { family: 'JetBrains Mono', size: 11 },
          padding: 8,
          callbacks: { label: ctx => ctx.parsed.y.toLocaleString() + ' ' + series.currency }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { family: 'JetBrains Mono', size: 9 }, color: '#6b5d4e', maxRotation: 0 }, border: { color: '#1a1410' } },
        y: { grid: { color: 'rgba(26,20,16,0.08)' }, ticks: { font: { family: 'JetBrains Mono', size: 9 }, color: '#6b5d4e', callback: v => v.toLocaleString() }, border: { display: false } }
      }
    }
  });
}
flightSeries.forEach(s => renderChart('chart-f-' + s.id, s, '#c8401c'));
hotelSeries.forEach(s => renderChart('chart-h-' + s.id, s, '#2d5a2d'));

let editorState = { flights: [], hotels: [] };

function loadCurrentSearches() {
  try {
    const parsed = jsyaml.load(CURRENT_YAML) || {};
    editorState.flights = (parsed.flights || []).map(f => normalizeFlight(f));
    editorState.hotels  = (parsed.hotels  || []).map(h => normalizeHotel(h));
  } catch (e) {
    console.error("Could not parse current searches.yaml:", e);
    editorState = { flights: [], hotels: [] };
  }
}
function toIsoDate(v) {
  // Convert Date or 'YYYY-MM-DD' string to YYYY-MM-DD
  if (!v) return '';
  if (v instanceof Date) return v.toISOString().slice(0, 10);
  return String(v);
}
function normalizeFlight(f) {
  return {
    id: f.id || '', nickname: f.nickname || '',
    departure_id: f.departure_id || '', arrival_id: f.arrival_id || '',
    outbound_date: toIsoDate(f.outbound_date), return_date: toIsoDate(f.return_date),
    adults: f.adults ?? 1, travel_class: f.travel_class || 'ECONOMY',
    currency: f.currency || 'INR',
    alert_below: f.alert_below ?? 0, max_results: f.max_results ?? 5,
  };
}
function normalizeHotel(h) {
  return {
    id: h.id || '', nickname: h.nickname || '', query: h.query || '',
    check_in: toIsoDate(h.check_in), check_out: toIsoDate(h.check_out),
    adults: h.adults ?? 2, currency: h.currency || 'INR',
    alert_below: h.alert_below ?? 0, max_results: h.max_results ?? 10,
  };
}

function openEditor() {
  loadCurrentSearches(); renderEditor();
  document.getElementById('editor-overlay').classList.add('open');
  refreshTokenUI();
}
function closeEditor() {
  document.getElementById('editor-overlay').classList.remove('open');
  document.getElementById('save-status').className = 'save-status';
}
function refreshTokenUI() {
  const token = localStorage.getItem(TOKEN_KEY) || '';
  document.getElementById('gh-token').value = token;
  document.getElementById('token-section').classList.toggle('has-token', !!token);
  document.getElementById('btn-forget').style.display = token ? '' : 'none';
}
function forgetToken() {
  if (!confirm('Remove the saved token from this browser?')) return;
  localStorage.removeItem(TOKEN_KEY); refreshTokenUI();
}
function addFlight() {
  editorState.flights.push(normalizeFlight({
    id: 'new-flight-' + Date.now().toString(36),
    nickname: 'New flight search',
  }));
  renderEditor();
}
function addHotel() {
  editorState.hotels.push(normalizeHotel({
    id: 'new-hotel-' + Date.now().toString(36),
    nickname: 'New hotel search',
  }));
  renderEditor();
}
function deleteFlight(idx) {
  if (!confirm('Delete this flight search? Existing price history is kept.')) return;
  editorState.flights.splice(idx, 1); renderEditor();
}
function deleteHotel(idx) {
  if (!confirm('Delete this hotel search? Existing price history is kept.')) return;
  editorState.hotels.splice(idx, 1); renderEditor();
}

function inputField(label, value, onchange, opts) {
  opts = opts || {};
  const wide = opts.wide ? ' wide' : '';
  const type = opts.type || 'text';
  const placeholder = opts.placeholder || '';
  const escVal = String(value == null ? '' : value).replace(/&/g,'&amp;').replace(/"/g,'&quot;');
  return '<div class="field' + wide + '"><label>' + label + '</label>' +
    '<input type="' + type + '" value="' + escVal + '" placeholder="' + placeholder + '" oninput="' + onchange + '" /></div>';
}
function selectField(label, value, options, onchange) {
  const opts = options.map(o => '<option value="'+o+'"'+(o===value?' selected':'')+'>'+o+'</option>').join('');
  return '<div class="field"><label>'+label+'</label><select onchange="'+onchange+'">'+opts+'</select></div>';
}

function renderEditor() {
  const fHost = document.getElementById('flights-list');
  fHost.innerHTML = editorState.flights.map((f, i) =>
    '<div class="ed-row">' +
      '<div class="row-head">' +
        '<span class="row-id">' + (f.id || '(no id)') + '</span>' +
        '<button class="del" onclick="deleteFlight(' + i + ')">Delete</button>' +
      '</div>' +
      '<div class="ed-grid">' +
        inputField('ID (no spaces)', f.id, 'editorState.flights[' + i + '].id=this.value') +
        inputField('Nickname', f.nickname, 'editorState.flights[' + i + '].nickname=this.value', {wide:true}) +
        inputField('From (IATA)', f.departure_id, 'editorState.flights[' + i + '].departure_id=this.value.toUpperCase()', {placeholder:'BOM'}) +
        inputField('To (IATA)', f.arrival_id, 'editorState.flights[' + i + '].arrival_id=this.value.toUpperCase()', {placeholder:'DXB'}) +
        inputField('Outbound', f.outbound_date, 'editorState.flights[' + i + '].outbound_date=this.value', {type:'date'}) +
        inputField('Return', f.return_date, 'editorState.flights[' + i + '].return_date=this.value', {type:'date'}) +
        inputField('Adults', f.adults, 'editorState.flights[' + i + '].adults=parseInt(this.value)||1', {type:'number'}) +
        selectField('Class', f.travel_class || 'ECONOMY', ['ECONOMY','PREMIUM_ECONOMY','BUSINESS','FIRST'], 'editorState.flights[' + i + '].travel_class=this.value') +
        inputField('Currency', f.currency, 'editorState.flights[' + i + '].currency=this.value.toUpperCase()', {placeholder:'INR'}) +
        inputField('Alert below', f.alert_below, 'editorState.flights[' + i + '].alert_below=parseFloat(this.value)||0', {type:'number'}) +
        inputField('Max results', f.max_results, 'editorState.flights[' + i + '].max_results=parseInt(this.value)||5', {type:'number'}) +
      '</div>' +
    '</div>'
  ).join('') || '<p style="color:var(--muted);font-style:italic;">No flight searches. Add one below.</p>';

  const hHost = document.getElementById('hotels-list');
  hHost.innerHTML = editorState.hotels.map((h, i) =>
    '<div class="ed-row">' +
      '<div class="row-head">' +
        '<span class="row-id">' + (h.id || '(no id)') + '</span>' +
        '<button class="del" onclick="deleteHotel(' + i + ')">Delete</button>' +
      '</div>' +
      '<div class="ed-grid">' +
        inputField('ID (no spaces)', h.id, 'editorState.hotels[' + i + '].id=this.value') +
        inputField('Nickname', h.nickname, 'editorState.hotels[' + i + '].nickname=this.value', {wide:true}) +
        inputField('Query', h.query, 'editorState.hotels[' + i + '].query=this.value', {wide:true, placeholder:'hotels in Goa, India'}) +
        inputField('Check-in', h.check_in, 'editorState.hotels[' + i + '].check_in=this.value', {type:'date'}) +
        inputField('Check-out', h.check_out, 'editorState.hotels[' + i + '].check_out=this.value', {type:'date'}) +
        inputField('Adults', h.adults, 'editorState.hotels[' + i + '].adults=parseInt(this.value)||2', {type:'number'}) +
        inputField('Currency', h.currency, 'editorState.hotels[' + i + '].currency=this.value.toUpperCase()', {placeholder:'INR'}) +
        inputField('Alert below', h.alert_below, 'editorState.hotels[' + i + '].alert_below=parseFloat(this.value)||0', {type:'number'}) +
        inputField('Max results', h.max_results, 'editorState.hotels[' + i + '].max_results=parseInt(this.value)||10', {type:'number'}) +
      '</div>' +
    '</div>'
  ).join('') || '<p style="color:var(--muted);font-style:italic;">No hotel searches. Add one below.</p>';
}

function validateState() {
  const errs = [];
  const ids = new Set();
  const isDate = s => /^\\d{4}-\\d{2}-\\d{2}$/.test(s || '');
  const checkId = (id, kind, idx) => {
    if (!id || /\\s/.test(id)) errs.push(kind + ' #' + (idx+1) + ': id required, no spaces');
    if (ids.has(id)) errs.push('Duplicate id: ' + id);
    else ids.add(id);
  };
  editorState.flights.forEach((f, i) => {
    checkId(f.id, 'Flight', i);
    if (!f.departure_id) errs.push('Flight ' + f.id + ': From (IATA) required');
    if (!f.arrival_id)   errs.push('Flight ' + f.id + ': To (IATA) required');
    if (!isDate(f.outbound_date)) errs.push('Flight ' + f.id + ': outbound date invalid');
    if (f.return_date && !isDate(f.return_date)) errs.push('Flight ' + f.id + ': return date invalid');
  });
  editorState.hotels.forEach((h, i) => {
    checkId(h.id, 'Hotel', i);
    if (!h.query) errs.push('Hotel ' + h.id + ': query required');
    if (!isDate(h.check_in))  errs.push('Hotel ' + h.id + ': check-in date invalid');
    if (!isDate(h.check_out)) errs.push('Hotel ' + h.id + ': check-out date invalid');
  });
  return errs;
}

function buildYaml() {
  const flights = editorState.flights.map(f => {
    const o = Object.assign({}, f);
    if (!o.return_date) delete o.return_date;
    return o;
  });
  const obj = { flights, hotels: editorState.hotels };
  return jsyaml.dump(obj, { lineWidth: 120, noRefs: true, sortKeys: false, quotingType: '"' });
}

function setStatus(msg, kind) {
  const el = document.getElementById('save-status');
  el.textContent = msg;
  el.className = 'save-status show ' + (kind || '');
}

async function saveSearches() {
  const tokenInput = document.getElementById('gh-token').value.trim();
  if (tokenInput) localStorage.setItem(TOKEN_KEY, tokenInput);
  refreshTokenUI();
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) { setStatus('Paste your GitHub token first.', 'err'); return; }

  const errs = validateState();
  if (errs.length) { setStatus('Fix these first:\\n  ' + errs.join('\\n  '), 'err'); return; }

  const yamlText = buildYaml();
  const fullText = '# Edited from dashboard at ' + new Date().toISOString() + '\\n' + yamlText;

  const btn = document.getElementById('btn-save');
  btn.disabled = true; btn.textContent = 'Saving...';
  setStatus('Talking to GitHub...');

  try {
    const meta = await fetch(
      'https://api.github.com/repos/' + REPO_FULL + '/contents/searches.yaml',
      { headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' } }
    );
    if (!meta.ok) throw new Error('GET failed: ' + meta.status + ' ' + (await meta.text()));
    const sha = (await meta.json()).sha;

    const b64 = btoa(unescape(encodeURIComponent(fullText)));
    const put = await fetch(
      'https://api.github.com/repos/' + REPO_FULL + '/contents/searches.yaml',
      {
        method: 'PUT',
        headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
        body: JSON.stringify({
          message: 'Update searches.yaml from dashboard editor',
          content: b64, sha,
        })
      }
    );
    if (!put.ok) throw new Error('PUT failed: ' + put.status + ' ' + (await put.text()));

    setStatus('Saved! New searches will be tracked starting on the next collector run.', 'ok');
  } catch (e) {
    console.error(e);
    setStatus('Save failed: ' + e.message, 'err');
  } finally {
    btn.disabled = false; btn.textContent = 'Save & commit';
  }
}
</script>
</body>
</html>
"""


def _format_price(p, cur):
    if p is None:
        return "—"
    return f"{p:,.0f} {cur}"


def _delta_html(delta):
    if delta is None:
        return '<span class="stat-value">—</span>'
    if abs(delta) < 0.05:
        return '<span class="stat-value">±0%</span>'
    arrow = "▼" if delta < 0 else "▲"
    cls = "good" if delta < 0 else "bad"
    return f'<span class="stat-value {cls}"><span class="delta-arrow">{arrow}</span>{abs(delta):.1f}%</span>'


def _render_card(s, prefix):
    cur = s["currency"]
    return f"""
    <div class="card">
      <p class="nickname">{s["nickname"]}</p>
      <div class="id">{s["id"]} &middot; {s["samples"]} sample{'s' if s['samples'] != 1 else ''}</div>
      <div class="stats">
        <div class="stat"><div class="stat-label">Latest</div><div class="stat-value">{_format_price(s["latest"], cur)}</div></div>
        <div class="stat"><div class="stat-label">Vs prev</div>{_delta_html(s["delta_pct"])}</div>
        <div class="stat"><div class="stat-label">All-time min</div><div class="stat-value">{_format_price(s["min"], cur)}</div></div>
      </div>
      <div class="chart-wrap"><canvas id="chart-{prefix}-{s['id']}"></canvas></div>
    </div>
    """


def _section(series, prefix, empty_msg):
    if not series:
        return f'<div class="empty"><h3>No data yet.</h3><p>{empty_msg}</p></div>'
    return '<div class="grid">' + "\n".join(_render_card(s, prefix) for s in series) + '</div>'


def _detect_repo() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo:
        return repo
    try:
        import subprocess
        url = subprocess.check_output(
            ["git", "-C", ROOT, "config", "--get", "remote.origin.url"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if url.startswith("git@"):
            url = url.split(":", 1)[1]
        else:
            url = url.split("github.com/", 1)[-1]
        if url.endswith(".git"):
            url = url[:-4]
        return url
    except Exception:
        return "OWNER/REPO"


def generate() -> str:
    os.makedirs(DOCS_DIR, exist_ok=True)
    flights = storage.read_flights()
    hotels = storage.read_hotels()
    f_series = _series_payload(flights)
    h_series = _series_payload(hotels)

    def js_safe(series_list):
        return [{"id": s["id"], "labels": s["labels"], "data": s["data"], "currency": s["currency"]} for s in series_list]

    flight_count = len({r["search_id"] for r in flights})
    hotel_count = len({r["search_id"] for r in hotels})

    now = datetime.utcnow()
    issue = now.strftime("%Y.%j")

    repo_full = _detect_repo()
    repo_name = repo_full.split("/")[-1] if "/" in repo_full else repo_full

    replacements = {
        "{issue}": issue,
        "{updated}": now.strftime("%Y-%m-%d %H:%M UTC"),
        "{flight_count}": str(flight_count),
        "{hotel_count}": str(hotel_count),
        "{flights_section}": _section(f_series, "f", "Add flight searches in <code>searches.yaml</code> and wait for the next collector run."),
        "{hotels_section}": _section(h_series, "h", "Add hotel searches in <code>searches.yaml</code> and wait for the next collector run."),
        "{flights_json}": json.dumps(js_safe(f_series)),
        "{hotels_json}": json.dumps(js_safe(h_series)),
        "{repo_full}": repo_full,
        "{repo_name}": repo_name,
        "{current_yaml_json}": json.dumps(_read_searches_yaml_text()),
    }
    html = HTML
    for token, value in replacements.items():
        html = html.replace(token, value)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    return OUT_PATH


if __name__ == "__main__":
    print("Wrote", generate())

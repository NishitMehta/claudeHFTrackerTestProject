"""
Generates docs/index.html — an editorial-style dashboard the user can serve
via GitHub Pages. Reads the CSVs and produces a self-contained HTML file
with charts rendered by Chart.js (loaded from CDN).
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
    """Build the JS-friendly per-search series for charting."""
    grouped = _group_min_per_day(rows)
    # nicknames + currency
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
<style>
  :root {
    --ink: #1a1410;
    --paper: #f4ede0;
    --paper-dark: #ebe0cc;
    --rule: #1a1410;
    --accent: #c8401c;
    --accent-soft: #e8a48e;
    --good: #2d5a2d;
    --bad: #c8401c;
    --muted: #6b5d4e;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0;
    padding: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: 'Fraunces', Georgia, serif;
    font-feature-settings: "ss01", "ss02";
  }
  body {
    background-image:
      radial-gradient(circle at 20% 10%, rgba(200,64,28,.04) 0%, transparent 40%),
      radial-gradient(circle at 80% 80%, rgba(45,90,45,.04) 0%, transparent 40%);
    min-height: 100vh;
    padding: 0 0 6rem 0;
  }
  .masthead {
    border-bottom: 3px double var(--rule);
    padding: 2.4rem 3rem 1.2rem 3rem;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 1rem;
  }
  .masthead h1 {
    font-size: clamp(2.5rem, 6vw, 4.5rem);
    font-weight: 800;
    letter-spacing: -0.03em;
    margin: 0;
    line-height: 0.95;
    font-style: italic;
  }
  .masthead .meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--muted);
    text-align: right;
  }
  .container {
    padding: 0 3rem;
    max-width: 1400px;
    margin: 0 auto;
  }
  .section-rule {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    margin: 3rem 0 1.5rem 0;
  }
  .section-rule h2 {
    font-size: 0.85rem;
    font-family: 'JetBrains Mono', monospace;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    margin: 0;
    white-space: nowrap;
  }
  .section-rule .line {
    flex: 1;
    height: 1px;
    background: var(--rule);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
    gap: 1.5rem;
  }
  .card {
    background: var(--paper);
    border: 1.5px solid var(--ink);
    padding: 1.5rem;
    position: relative;
    transition: transform 0.15s ease;
  }
  .card:hover { transform: translateY(-2px); }
  .card .nickname {
    font-size: 1.4rem;
    font-weight: 600;
    line-height: 1.15;
    margin: 0 0 0.25rem 0;
    font-style: italic;
  }
  .card .id {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin-bottom: 1rem;
  }
  .stats {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    border-top: 1px solid var(--ink);
    border-bottom: 1px solid var(--ink);
    margin: 1rem 0;
  }
  .stat {
    padding: 0.7rem 0.5rem;
    border-right: 1px solid var(--ink);
    text-align: center;
  }
  .stat:last-child { border-right: none; }
  .stat-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.6rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--muted);
    margin-bottom: 0.25rem;
  }
  .stat-value {
    font-size: 1.15rem;
    font-weight: 600;
  }
  .stat-value.good { color: var(--good); }
  .stat-value.bad { color: var(--bad); }
  .chart-wrap {
    position: relative;
    height: 180px;
    margin-top: 0.5rem;
  }
  .empty {
    text-align: center;
    padding: 4rem 2rem;
    border: 1px dashed var(--rule);
    color: var(--muted);
  }
  .empty h3 {
    font-style: italic;
    font-weight: 600;
    font-size: 1.5rem;
  }
  footer {
    text-align: center;
    margin-top: 4rem;
    padding-top: 2rem;
    border-top: 1px solid var(--rule);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    color: var(--muted);
  }
  .delta-arrow { font-size: 0.85em; margin-right: 0.15em; }
  @media (max-width: 600px) {
    .masthead, .container { padding-left: 1.25rem; padding-right: 1.25rem; }
    .grid { grid-template-columns: 1fr; }
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
  </div>

  {flights_section}

  <div class="section-rule">
    <h2>🏨 Hotels</h2>
    <div class="line"></div>
  </div>

  {hotels_section}

  <footer>
    Generated by collector &middot; Data via Amadeus
  </footer>
</div>

<script>
const flightSeries = {flights_json};
const hotelSeries = {hotels_json};

function renderChart(canvasId, series, accentColor) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: series.labels,
      datasets: [{
        data: series.data,
        borderColor: accentColor,
        backgroundColor: accentColor + '20',
        borderWidth: 2,
        fill: true,
        tension: 0.25,
        pointRadius: 3,
        pointBackgroundColor: accentColor,
        pointBorderColor: '#f4ede0',
        pointBorderWidth: 1.5,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a1410',
          titleFont: { family: 'JetBrains Mono', size: 11 },
          bodyFont: { family: 'JetBrains Mono', size: 11 },
          padding: 8,
          callbacks: {
            label: function(ctx) {
              return ctx.parsed.y.toLocaleString() + ' ' + series.currency;
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'JetBrains Mono', size: 9 }, color: '#6b5d4e', maxRotation: 0 },
          border: { color: '#1a1410' }
        },
        y: {
          grid: { color: 'rgba(26,20,16,0.08)' },
          ticks: {
            font: { family: 'JetBrains Mono', size: 9 },
            color: '#6b5d4e',
            callback: v => v.toLocaleString()
          },
          border: { display: false }
        }
      }
    }
  });
}

flightSeries.forEach(s => renderChart('chart-f-' + s.id, s, '#c8401c'));
hotelSeries.forEach(s => renderChart('chart-h-' + s.id, s, '#2d5a2d'));
</script>
</body>
</html>
"""


def _format_price(p: float | None, cur: str) -> str:
    if p is None:
        return "—"
    return f"{p:,.0f} {cur}"


def _delta_html(delta: float | None) -> str:
    if delta is None:
        return '<span class="stat-value">—</span>'
    if abs(delta) < 0.05:
        return f'<span class="stat-value">±0%</span>'
    arrow = "▼" if delta < 0 else "▲"
    cls = "good" if delta < 0 else "bad"
    return f'<span class="stat-value {cls}"><span class="delta-arrow">{arrow}</span>{abs(delta):.1f}%</span>'


def _render_card(s: dict, prefix: str) -> str:
    cur = s["currency"]
    return f"""
    <div class="card">
      <p class="nickname">{s["nickname"]}</p>
      <div class="id">{s["id"]} &middot; {s["samples"]} sample{'s' if s['samples'] != 1 else ''}</div>
      <div class="stats">
        <div class="stat">
          <div class="stat-label">Latest</div>
          <div class="stat-value">{_format_price(s["latest"], cur)}</div>
        </div>
        <div class="stat">
          <div class="stat-label">Vs prev</div>
          {_delta_html(s["delta_pct"])}
        </div>
        <div class="stat">
          <div class="stat-label">All-time min</div>
          <div class="stat-value">{_format_price(s["min"], cur)}</div>
        </div>
      </div>
      <div class="chart-wrap">
        <canvas id="chart-{prefix}-{s['id']}"></canvas>
      </div>
    </div>
    """


def _section(series: list[dict], prefix: str, empty_msg: str) -> str:
    if not series:
        return f'<div class="empty"><h3>No data yet.</h3><p>{empty_msg}</p></div>'
    cards = "\n".join(_render_card(s, prefix) for s in series)
    return f'<div class="grid">{cards}</div>'


def generate() -> str:
    os.makedirs(DOCS_DIR, exist_ok=True)

    flights = storage.read_flights()
    hotels = storage.read_hotels()

    f_series = _series_payload(flights)
    h_series = _series_payload(hotels)

    # Strip non-essentials for JSON to keep payload small
    def js_safe(series_list: list[dict]) -> list[dict]:
        return [{
            "id": s["id"],
            "labels": s["labels"],
            "data": s["data"],
            "currency": s["currency"],
        } for s in series_list]

    flight_count = len({r["search_id"] for r in flights})
    hotel_count = len({r["search_id"] for r in hotels})

    now = datetime.utcnow()
    issue = now.strftime("%Y.%j")  # year + day-of-year

    replacements = {
        "{issue}": issue,
        "{updated}": now.strftime("%Y-%m-%d %H:%M UTC"),
        "{flight_count}": str(flight_count),
        "{hotel_count}": str(hotel_count),
        "{flights_section}": _section(f_series, "f", "Add flight searches in <code>searches.yaml</code> and wait for the next collector run."),
        "{hotels_section}": _section(h_series, "h", "Add hotel searches in <code>searches.yaml</code> and wait for the next collector run."),
        "{flights_json}": json.dumps(js_safe(f_series)),
        "{hotels_json}": json.dumps(js_safe(h_series)),
    }
    html = HTML
    for token, value in replacements.items():
        html = html.replace(token, value)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    return OUT_PATH


if __name__ == "__main__":
    p = generate()
    print(f"Wrote {p}")

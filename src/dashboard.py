import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_metrics(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"metrics.json not found at {path}. "
            "Run 'uv run src/main.py analyze' first."
        )
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def generate_dashboard(
    metrics_path: str = "data/metrics.json",
    output_path: str = "data/dashboard.html",
) -> str:
    m = _load_metrics(metrics_path)

    versions = m.get("versions_seen", [])
    by_ver = m.get("pass_rates", {}).get("by_version", {})
    overall = m.get("pass_rates", {}).get("overall", {})
    by_cat_ver = m.get("pass_rates", {}).get("by_category_version", {})
    gc = m.get("guardrail_consistency", {})
    ft = m.get("failure_taxonomy", {})
    pt = m.get("per_prompt_tracking", {})
    lat = m.get("latency", {})
    lon = m.get("longitudinal", {})
    models = m.get("models", {}).get("by_model", {})
    ver_hashes = m.get("version_hashes", {})
    generated_at = m.get("generated_at", "")[:19].replace("T", " ")

    warnings_html = ""
    for v, info in ver_hashes.items():
        if info.get("silent_edits_detected"):
            hashes = ", ".join(info.get("hashes", []))
            warnings_html += (
                f'<div class="warning-banner">'
                f'Version <strong>{v}</strong> was silently edited '
                f'(multiple hashes detected: <code>{hashes}</code>). '
                f'Results for {v} may mix two distinct prompt texts.'
                f'</div>'
            )

    def pct(r): return f"{r*100:.1f}%" if r is not None else "N/A"

    ver_rows = ""
    for i, v in enumerate(versions):
        vd = by_ver.get(v, {})
        rate = vd.get("pass_rate")
        passed = vd.get("passed", 0)
        total = vd.get("total", 0)
        if i > 0:
            prev_rate = by_ver.get(versions[i - 1], {}).get("pass_rate")
            if rate is not None and prev_rate is not None:
                delta = (rate - prev_rate) * 100
                sign = "+" if delta >= 0 else ""
                delta_color = "var(--green)" if delta >= 0 else "var(--red)"
                delta_cell = f'<td style="color:{delta_color};font-weight:600">{sign}{delta:.1f}pp</td>'
            else:
                delta_cell = "<td>—</td>"
        else:
            delta_cell = "<td>—</td>"
        ver_rows += (
            f"<tr>"
            f"<td style='font-weight:600'>{v}</td>"
            f"<td>{pct(rate)}</td>"
            f"<td style='color:var(--muted)'>{passed}/{total}</td>"
            f"{delta_cell}"
            f"</tr>"
        )
    versions_card = (
        '<div class="stat-card" style="flex:1.5;min-width:200px;padding:14px 16px">'
        '<div class="stat-label" style="margin-bottom:8px">Pass Rate by Version</div>'
        '<div style="overflow-y:auto;max-height:130px">'
        '<table style="font-size:0.8rem;width:100%">'
        '<thead><tr>'
        '<th style="color:var(--muted);font-size:0.68rem;padding:3px 8px">Ver</th>'
        '<th style="color:var(--muted);font-size:0.68rem;padding:3px 8px">Rate</th>'
        '<th style="color:var(--muted);font-size:0.68rem;padding:3px 8px">n</th>'
        '<th style="color:var(--muted);font-size:0.68rem;padding:3px 8px">Δ prev</th>'
        '</tr></thead>'
        f'<tbody>{ver_rows}</tbody>'
        '</table></div></div>'
    )

    improvements = pt.get("improvement_count", 0)
    regressions = pt.get("regression_count", 0)
    consistency = gc.get("consistency_score")
    flaky_count = len(gc.get("flaky_prompts", []))

    ver_labels = json.dumps(versions)
    ver_pass_rates = json.dumps([
        round((by_ver.get(v, {}).get("pass_rate") or 0) * 100, 1)
        for v in versions
    ])

    categories = sorted(by_cat_ver.keys())
    cat_datasets = []
    palette = ["#818cf8", "#4ade80", "#f472b6", "#fb923c", "#38bdf8"]
    for i, v in enumerate(versions):
        data = [
            round((by_cat_ver.get(cat, {}).get(v, {}).get("pass_rate") or 0) * 100, 1)
            for cat in categories
        ]
        cat_datasets.append({
            "label": v,
            "data": data,
            "backgroundColor": palette[i % len(palette)],
            "borderRadius": 4,
        })

    top_fail = ft.get("top_failure_categories", [])[:10]
    fail_labels = json.dumps([x["category"] for x in top_fail])
    fail_counts = json.dumps([x["count"] for x in top_fail])

    sev_map = ft.get("severity_distribution", {})
    sev_order = ["CRITICAL", "HIGH", "MEDIUM-HIGH", "MEDIUM", "LOW", "null"]
    sev_colors = {
        "CRITICAL": "#ef4444", "HIGH": "#f97316", "MEDIUM-HIGH": "#f59e0b",
        "MEDIUM": "#eab308", "LOW": "#84cc16", "null": "#64748b",
    }
    sev_labels = json.dumps([s for s in sev_order if s in sev_map])
    sev_values = json.dumps([sev_map[s] for s in sev_order if s in sev_map])
    sev_colors_js = json.dumps([sev_colors[s] for s in sev_order if s in sev_map])

    lat_by_ver = lat.get("by_version", {})
    lat_means = json.dumps([round(lat_by_ver.get(v, {}).get("mean") or 0, 2) for v in versions])
    lat_p95s  = json.dumps([round(lat_by_ver.get(v, {}).get("p95") or 0, 2) for v in versions])
    lat_overall = lat.get("overall", {})

    trend = lon.get("score_over_time", [])
    trend_labels = json.dumps([e.get("session_id", "")[-6:] for e in trend])
    trend_values = json.dumps([round((e.get("pass_rate") or 0) * 100, 1) for e in trend])
    trend_vers   = json.dumps([e.get("version", "?") for e in trend])

    matrix = pt.get("prompt_pass_matrix", {})
    session_order = [e["session_id"] for e in trend]
    all_sids_in_matrix = sorted({sid for v in matrix.values() for sid in v})
    for sid in all_sids_in_matrix:
        if sid not in session_order:
            session_order.append(sid)

    prompt_keys = sorted(matrix.keys())
    matrix_rows_html = ""
    for pk in prompt_keys:
        sessions = matrix[pk]
        cat, pid = pk.split("|", 1)
        short_cat = cat[:3].upper()
        cells = ""
        for sid in session_order:
            if sid in sessions:
                val = sessions[sid]
                cls = "cell-pass" if val else "cell-fail"
                label = "P" if val else "F"
            else:
                cls = "cell-skip"
                label = "-"
            cells += f'<td class="matrix-cell {cls}" title="{sid}">{label}</td>'
        matrix_rows_html += (
            f'<tr><td class="matrix-label">{short_cat} {pid}</td>{cells}</tr>'
        )

    session_headers = "".join(
        f'<th class="matrix-th" title="{sid}">{sid[-6:]}</th>'
        for sid in session_order
    )

    fail_by_ver = ft.get("failure_category_counts_by_version", {})
    all_fail_cats = sorted({c for d in fail_by_ver.values() for c in d})
    fail_table_header = "".join(f"<th>{v}</th>" for v in versions)
    fail_table_rows = ""
    for cat in all_fail_cats:
        cells = "".join(
            f'<td>{fail_by_ver.get(v, {}).get(cat, 0)}</td>'
            for v in versions
        )
        fail_table_rows += f"<tr><td>{cat}</td>{cells}</tr>"

    flaky_html = ""
    for fp in gc.get("flaky_prompts", []):
        results_str = " ".join("v" if r else "x" for r in fp["results"])
        flaky_html += (
            f'<tr><td>{fp["version"]}</td>'
            f'<td>{fp["category"]}</td>'
            f'<td>{fp["prompt_id"]}</td>'
            f'<td class="mono">{results_str}</td></tr>'
        )

    model_rows = ""
    for model, d in sorted(models.items()):
        r = d.get("pass_rate")
        model_rows += (
            f'<tr><td class="mono">{model}</td>'
            f'<td>{d["passed"]}/{d["total"]}</td>'
            f'<td>{pct(r)}</td></tr>'
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ProjectC Evaluation Metrics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.4/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg:       #0f172a;
    --surface:  #1e293b;
    --border:   #334155;
    --text:     #e2e8f0;
    --muted:    #94a3b8;
    --accent:   #818cf8;
    --green:    #4ade80;
    --red:      #f87171;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 14px; line-height: 1.6;
  }}
  a {{ color: var(--accent); }}
  .header {{
    background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 60%);
    border-bottom: 1px solid var(--border);
    padding: 24px 32px;
  }}
  .header h1 {{ font-size: 1.5rem; font-weight: 700; color: #fff; letter-spacing: -0.02em; }}
  .header .meta {{ color: var(--muted); font-size: 0.8rem; margin-top: 4px; }}
  .main {{ padding: 24px 32px; max-width: 1400px; margin: 0 auto; }}
  .warning-banner {{
    background: #422006; border: 1px solid #854d0e; border-radius: 8px;
    padding: 10px 16px; margin-bottom: 16px; color: #fde68a; font-size: 0.85rem;
  }}
  .warning-banner code {{ background: #713f12; padding: 1px 4px; border-radius: 3px; }}
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 20px;
  }}
  .card-title {{
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: var(--muted); margin-bottom: 14px;
  }}
  .stat-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }}
  .stat-card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px 20px; flex: 1; min-width: 140px;
  }}
  .stat-label {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }}
  .stat-value {{ font-size: 2rem; font-weight: 700; line-height: 1.2; margin: 4px 0; }}
  .stat-sub   {{ font-size: 0.78rem; color: var(--muted); }}
  .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  .grid-4 {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  @media (max-width: 900px) {{
    .grid-2, .grid-3, .grid-4 {{ grid-template-columns: 1fr 1fr; }}
  }}
  @media (max-width: 600px) {{
    .grid-2, .grid-3, .grid-4 {{ grid-template-columns: 1fr; }}
  }}
  .chart-wrap {{ position: relative; width: 100%; }}
  .chart-wrap canvas {{ width: 100% !important; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; }}
  th, td {{ padding: 7px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 600; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}
  .mono {{ font-family: monospace; letter-spacing: 0.08em; }}
  .matrix-wrap {{ overflow-x: auto; }}
  .matrix-wrap table {{ width: auto; }}
  .matrix-label {{ white-space: nowrap; font-size: 0.75rem; color: var(--muted); padding-right: 16px; font-family: monospace; }}
  .matrix-th {{ font-size: 0.65rem; background: var(--bg); position: sticky; top: 0; }}
  .matrix-cell {{
    width: 28px; height: 28px; text-align: center; font-size: 0.7rem;
    font-weight: 700; border-radius: 4px; border: none; padding: 0;
  }}
  .cell-pass {{ background: #166534; color: #86efac; }}
  .cell-fail {{ background: #7f1d1d; color: #fca5a5; }}
  .cell-skip {{ background: #1e293b; color: #475569; }}
  .section-gap {{ margin-bottom: 16px; }}
</style>
</head>
<body>

<div class="header">
  <h1>ProjectC Evaluation Metrics</h1>
  <div class="meta">Generated {generated_at} · {overall.get("total", 0)} total evaluations · Versions: {", ".join(versions) or "unknown"}</div>
</div>

<div class="main">

{warnings_html}

<div class="stat-row">
  <div class="stat-card">
    <div class="stat-label">Overall Pass Rate</div>
    <div class="stat-value">{pct(overall.get("pass_rate"))}</div>
    <div class="stat-sub">{overall.get("passed",0)}/{overall.get("total",0)} prompts</div>
  </div>
  {versions_card}
  <div class="stat-card">
    <div class="stat-label">Guardrail Consistency</div>
    <div class="stat-value">{pct(consistency)}</div>
    <div class="stat-sub">{flaky_count} flaky prompt·version groups</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Improvements v→v</div>
    <div class="stat-value" style="color:var(--green)">+{improvements}</div>
    <div class="stat-sub" style="color:var(--red)">−{regressions} regressions</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Latency (mean / p95)</div>
    <div class="stat-value" style="font-size:1.4rem">{lat_overall.get("mean","?")}<span style="font-size:.9rem">s</span></div>
    <div class="stat-sub">p95 = {lat_overall.get("p95","?")}s · max {lat_overall.get("max","?")}s</div>
  </div>
</div>

<div class="grid-3 section-gap">
  <div class="card">
    <div class="card-title">Pass Rate by Version</div>
    <div class="chart-wrap" style="height:220px">
      <canvas id="chartVersions"></canvas>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Pass Rate by Category × Version</div>
    <div class="chart-wrap" style="height:220px">
      <canvas id="chartCategories"></canvas>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Score Over Time</div>
    <div class="chart-wrap" style="height:220px">
      <canvas id="chartTrend"></canvas>
    </div>
  </div>
</div>

<div class="grid-3 section-gap">
  <div class="card" style="grid-column: span 1">
    <div class="card-title">Top Failure Categories</div>
    <div class="chart-wrap" style="height:220px">
      <canvas id="chartFailures"></canvas>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Severity Distribution</div>
    <div class="chart-wrap" style="height:220px">
      <canvas id="chartSeverity"></canvas>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Latency by Version</div>
    <div class="chart-wrap" style="height:220px">
      <canvas id="chartLatency"></canvas>
    </div>
  </div>
</div>

<div class="card section-gap">
  <div class="card-title">Prompt Pass Matrix (P=pass F=fail -=not run)</div>
  <div class="matrix-wrap">
    <table>
      <thead><tr>
        <th class="matrix-th">Prompt</th>
        {session_headers}
      </tr></thead>
      <tbody>{matrix_rows_html}</tbody>
    </table>
  </div>
</div>

<div class="grid-3 section-gap">
  <div class="card">
    <div class="card-title">Failure Category Counts by Version</div>
    <table>
      <thead><tr><th>Category</th>{fail_table_header}</tr></thead>
      <tbody>{fail_table_rows}</tbody>
    </table>
  </div>

  <div class="card">
    <div class="card-title">Flaky Prompt Groups</div>
    <table>
      <thead><tr><th>Ver</th><th>Category</th><th>Prompt</th><th>Results</th></tr></thead>
      <tbody>{flaky_html if flaky_html else '<tr><td colspan="4">None</td></tr>'}</tbody>
    </table>
  </div>

  <div class="card">
    <div class="card-title">Model Breakdown</div>
    <table>
      <thead><tr><th>Model</th><th>Pass</th><th>Rate</th></tr></thead>
      <tbody>{model_rows}</tbody>
    </table>
  </div>
</div>

</div>

<script>
const VERSIONS = {ver_labels};
const CATEGORIES = {json.dumps(categories)};

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.font.size = 11;

const gridLines = {{
  color: '#334155', drawBorder: false,
}};

const VERSION_PALETTE = ['#818cf8','#4ade80','#f472b6','#fb923c','#38bdf8','#a78bfa','#34d399','#f59e0b','#e879f9','#60a5fa'];
const paletteMap = Object.fromEntries(VERSIONS.map((v, i) => [v, VERSION_PALETTE[i % VERSION_PALETTE.length]]));

function barOpts() {{
  return {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y + '%' }} }} }},
    scales: {{
      x: {{ grid: gridLines }},
      y: {{ grid: gridLines, min: 0, max: 100, ticks: {{ callback: v => v + '%' }} }},
    }},
  }};
}}

new Chart(document.getElementById('chartVersions'), {{
  type: 'bar',
  data: {{
    labels: VERSIONS,
    datasets: [{{
      data: {ver_pass_rates},
      backgroundColor: VERSION_PALETTE.slice(0, VERSIONS.length),
      borderRadius: 6,
    }}],
  }},
  options: {{
    ...barOpts(),
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y + '%' }} }},
    }},
  }},
}});

new Chart(document.getElementById('chartCategories'), {{
  type: 'bar',
  data: {{
    labels: CATEGORIES,
    datasets: {json.dumps(cat_datasets)},
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 8 }} }} }},
    scales: {{
      x: {{ grid: gridLines }},
      y: {{ grid: gridLines, min: 0, max: 100, ticks: {{ callback: v => v + '%' }} }},
    }},
  }},
}});

const trendVersions = {trend_vers};
const trendColors = trendVersions.map(v => paletteMap[v] || '#94a3b8');
new Chart(document.getElementById('chartTrend'), {{
  type: 'line',
  data: {{
    labels: {trend_labels},
    datasets: [{{
      data: {trend_values},
      borderColor: '#818cf8',
      backgroundColor: 'rgba(129,140,248,0.15)',
      tension: 0.35,
      pointBackgroundColor: trendColors,
      pointRadius: 5,
      pointHoverRadius: 7,
      fill: true,
    }}],
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{ callbacks: {{ label: ctx => ctx.parsed.y + '% (' + trendVersions[ctx.dataIndex] + ')' }} }},
    }},
    scales: {{
      x: {{ grid: gridLines }},
      y: {{ grid: gridLines, min: 0, max: 100, ticks: {{ callback: v => v + '%' }} }},
    }},
  }},
}});

// 4. Failure categories (horizontal bar)
new Chart(document.getElementById('chartFailures'), {{
  type: 'bar',
  data: {{
    labels: {fail_labels},
    datasets: [{{ data: {fail_counts}, backgroundColor: '#f87171', borderRadius: 4 }}],
  }},
  options: {{
    indexAxis: 'y',
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{
      x: {{ grid: gridLines, ticks: {{ stepSize: 1 }} }},
      y: {{ grid: {{ display: false }} }},
    }},
  }},
}});

// 5. Severity donut
new Chart(document.getElementById('chartSeverity'), {{
  type: 'doughnut',
  data: {{
    labels: {sev_labels},
    datasets: [{{
      data: {sev_values},
      backgroundColor: {sev_colors_js},
      borderWidth: 2,
      borderColor: '#1e293b',
    }}],
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    cutout: '60%',
    plugins: {{
      legend: {{ position: 'right', labels: {{ boxWidth: 10, padding: 10 }} }},
    }},
  }},
}});

// 6. Latency grouped bar (mean vs p95)
new Chart(document.getElementById('chartLatency'), {{
  type: 'bar',
  data: {{
    labels: VERSIONS,
    datasets: [
      {{ label: 'Mean (s)', data: {lat_means}, backgroundColor: '#38bdf8', borderRadius: 4 }},
      {{ label: 'p95 (s)',  data: {lat_p95s},  backgroundColor: '#818cf8', borderRadius: 4 }},
    ],
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 10, padding: 8 }} }} }},
    scales: {{
      x: {{ grid: gridLines }},
      y: {{ grid: gridLines, ticks: {{ callback: v => v + 's' }} }},
    }},
  }},
}});
</script>
</body>
</html>
"""

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    logger.info(f"Dashboard written to {output_path}")
    return output_path

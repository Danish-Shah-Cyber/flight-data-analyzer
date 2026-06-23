from __future__ import annotations

import html
import json
from pathlib import Path

from .analysis import FlightSummary
from .diagnostics import analyze_fuel_flow, analyze_gps_health
from .insights import InsightReport
from .model import FlightSample
from .quality import DataQualityReport, assess_data_quality


def _polyline(samples: list[FlightSample], field: str, width: int = 900, height: int = 180) -> str:
    values = [float(getattr(sample, field)) for sample in samples]
    low, high = min(values), max(values)
    span = high - low or 1.0
    time_start, time_end = samples[0].time_s, samples[-1].time_s
    time_span = time_end - time_start or 1.0
    points = []
    for sample, value in zip(samples, values):
        x = (sample.time_s - time_start) / time_span * width
        y = height - (value - low) / span * (height - 20) - 10
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)


def _chart(title: str, field: str, unit: str, color: str, samples: list[FlightSample]) -> str:
    return f"""<div class="plot">
      <div class="plot-head"><span>{html.escape(title)}</span><span>{html.escape(unit)}</span></div>
      <svg viewBox="0 0 900 180" role="img" aria-label="{html.escape(title)} plot">
        <line x1="0" y1="170" x2="900" y2="170" class="axis"/>
        <polyline points="{_polyline(samples, field)}" stroke="{color}"/>
      </svg>
    </div>"""


def _list(items: list[str], empty: str) -> str:
    if not items:
        return f"<p class=\"muted\">{html.escape(empty)}</p>"
    return "<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def _diagnostic_cards(findings) -> str:
    if not findings:
        return "<p class=\"muted\">No diagnostic finding was generated.</p>"
    return "".join(
        f"""<article class="finding {html.escape(item.severity)}">
          <div class="finding-head"><strong>{html.escape(item.title)}</strong><span>{html.escape(item.severity.upper())}</span></div>
          <p><b>Evidence:</b> {html.escape('; '.join(item.evidence))}</p>
          <p><b>Recommended check:</b> {html.escape(item.recommendation)}</p>
        </article>"""
        for item in findings
    )


def _module_templates(
    samples: list[FlightSample],
    summary: FlightSummary,
    insights: InsightReport | None,
    quality: DataQualityReport,
) -> str:
    fuel = analyze_fuel_flow(samples)
    gps = analyze_gps_health(samples)
    event_rows = "".join(
        f"<tr><td>{event.time_s:.1f}</td><td>{html.escape(event.kind)}</td>"
        f"<td>{html.escape(event.description)}</td></tr>"
        for event in summary.events
    ) or "<tr><td colspan=\"3\">No events detected</td></tr>"

    signal_rows = "".join(
        f"<tr><td>{html.escape(signal.name)}</td><td>{'Yes' if signal.present else 'No'}</td>"
        f"<td>{signal.coverage_pct:.0f}%</td><td>{html.escape('; '.join(signal.notes) or 'OK')}</td></tr>"
        for signal in quality.signals
    )

    finding_cards = ""
    if insights is not None:
        finding_cards = "".join(
            f"""<article class="finding {html.escape(item.severity)}">
              <div class="finding-head"><strong>{html.escape(item.title)}</strong><span>{html.escape(item.severity.upper())}</span></div>
              <div class="muted">{item.start_s:.1f}-{item.end_s:.1f} s | {html.escape(item.confidence)} confidence</div>
              <p><b>Evidence:</b> {html.escape('; '.join(item.evidence))}</p>
              <p><b>Possible causes:</b> {html.escape('; '.join(item.possible_causes))}</p>
              <p><b>Recommended check:</b> {html.escape(item.recommendation)}</p>
            </article>"""
            for item in insights.findings
        )

    modules = {
        "charts": {
            "title": "Flight Trends",
            "html": "".join(
                [
                    _chart("Altitude", "relative_altitude_m", "m", "#2382d9", samples),
                    _chart("Ground speed", "groundspeed_m_s", "m/s", "#c47b10", samples),
                    _chart("Battery remaining", "battery_remaining_pct", "%", "#178f61", samples),
                ]
            ),
        },
        "assessment": {
            "title": "Flight Assessment",
            "html": (
                f"<div class=\"assessment\">{html.escape(insights.status if insights else 'Assessment unavailable')}</div>"
                + (finding_cards or "<p class=\"muted\">No assessment details available.</p>")
            ),
        },
        "quality": {
            "title": "Data Quality",
            "html": f"""<div class="quality-hero">
              <div><span class="score">{quality.score:.0f}</span><span class="muted">/100</span></div>
              <div><strong>{html.escape(quality.grade)}</strong><p class="muted">Signal coverage, gaps, timestamps, and impossible values.</p></div>
            </div>
            <table><thead><tr><th>Signal</th><th>Present</th><th>Coverage</th><th>Notes</th></tr></thead><tbody>{signal_rows}</tbody></table>
            <h4>Warnings</h4>{_list(quality.warnings, 'No quality warnings detected.')}
            <h4>Limitations</h4>{_list(quality.limitations, 'No major data limitations detected.')}""",
        },
        "events": {
            "title": "Event Timeline",
            "html": f"<table><thead><tr><th>Time (s)</th><th>Type</th><th>Description</th></tr></thead><tbody>{event_rows}</tbody></table>",
        },
        "power": {
            "title": "Power Review",
            "html": "".join(
                [
                    _chart("Battery voltage", "battery_voltage_v", "V", "#7a6ff0", samples),
                    _chart("Battery current", "battery_current_a", "A", "#c4517c", samples),
                ]
            ),
        },
        "fuel": {
            "title": "Fuel Flow",
            "html": f"""<div class="mini-grid">
              <div class="mini"><span class="muted">Status</span><strong>{html.escape(fuel.status)}</strong></div>
              <div class="mini"><span class="muted">Used</span><strong>{fuel.total_used_l:.2f} L</strong></div>
              <div class="mini"><span class="muted">Peak flow</span><strong>{fuel.peak_flow_l_h:.2f} L/h</strong></div>
              <div class="mini"><span class="muted">Endurance</span><strong>{fuel.estimated_endurance_min:.0f} min</strong></div>
            </div>
            {_chart("Fuel flow", "fuel_flow_l_h", "L/h", "#0b8f8f", samples)}
            {_chart("Fuel used", "fuel_used_l", "L", "#9a6b00", samples)}
            {_diagnostic_cards(fuel.findings)}
            <h4>Limitations</h4>{_list(fuel.limitations, 'No major fuel-analysis limitations detected.')}""",
        },
        "gps": {
            "title": "GPS Health",
            "html": f"""<div class="mini-grid">
              <div class="mini"><span class="muted">Status</span><strong>{html.escape(gps.status)}</strong></div>
              <div class="mini"><span class="muted">Min fix</span><strong>{gps.minimum_fix_type:.0f}</strong></div>
              <div class="mini"><span class="muted">Min satellites</span><strong>{gps.minimum_satellites:.0f}</strong></div>
              <div class="mini"><span class="muted">Max HDOP</span><strong>{gps.maximum_hdop:.2f}</strong></div>
            </div>
            {_chart("GPS satellites", "gps_satellites", "count", "#1769c2", samples)}
            {_chart("GPS HDOP", "gps_hdop", "ratio", "#c47b10", samples)}
            {_diagnostic_cards(gps.findings)}
            <h4>Limitations</h4>{_list(gps.limitations, 'No major GPS-health limitations detected.')}""",
        },
        "attitude": {
            "title": "Attitude Review",
            "html": "".join(
                [
                    _chart("Roll", "roll_deg", "deg", "#0b8f8f", samples),
                    _chart("Pitch", "pitch_deg", "deg", "#9a6b00", samples),
                    _chart("Yaw", "yaw_deg", "deg", "#7357c8", samples),
                ]
            ),
        },
        "limitations": {
            "title": "Analysis Limits",
            "html": (
                _list(insights.limitations if insights else [], "No assessment limitations were generated.")
                + "<p class=\"muted\">Conclusions are bounded by the recorded signals. The tool should label weak evidence instead of filling gaps with guesses.</p>"
            ),
        },
        "ai": {
            "title": "AI Analyst Placeholder",
            "html": "<p class=\"muted\">Future module: explain deterministic findings, answer questions, and compare flights without changing raw measurements.</p>",
        },
    }
    templates = []
    for module_id, module in modules.items():
        templates.append(
            f"""<template id="template-{html.escape(module_id)}">
              <section class="module" data-module="{html.escape(module_id)}" draggable="true">
                <div class="module-head">
                  <h2>{html.escape(module["title"])}</h2>
                  <div>
                    <button class="icon-button drag-handle" type="button" title="Drag module">Move</button>
                    <button class="icon-button remove-module" type="button" title="Remove module">Remove</button>
                  </div>
                </div>
                {module["html"]}
              </section>
            </template>"""
        )
    return "\n".join(templates)


def write_html_report(
    path: str | Path,
    samples: list[FlightSample],
    summary: FlightSummary,
    insights: InsightReport | None = None,
    quality: DataQualityReport | None = None,
) -> None:
    quality = quality or assess_data_quality(samples)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    default_modules = ["quality", "charts", "assessment", "events"]
    module_library = [
        ("quality", "Data Quality", "Signal coverage, gaps, and confidence"),
        ("charts", "Flight Trends", "Altitude, speed, and battery plots"),
        ("assessment", "Flight Assessment", "Rule-based findings and evidence"),
        ("events", "Event Timeline", "Detected flight events"),
        ("power", "Power Review", "Voltage and current behaviour"),
        ("fuel", "Fuel Flow", "Fuel burn, flow spikes, and endurance"),
        ("gps", "GPS Health", "Fix type, satellites, and HDOP"),
        ("attitude", "Attitude Review", "Roll, pitch, and yaw"),
        ("limitations", "Analysis Limits", "What this report cannot prove"),
        ("ai", "AI Analyst", "Future narrative and Q&A assistant"),
    ]
    library_html = "".join(
        f"""<button class="library-item" type="button" draggable="true" data-module="{module_id}">
          <span>{html.escape(title)}</span><small>{html.escape(description)}</small>
        </button>"""
        for module_id, title, description in module_library
    )
    upload_card = f"""<section class="upload-card">
      <h2>Analyze Log</h2>
      <form method="post" enctype="multipart/form-data" action="/analyze">
        <label class="upload-drop">
          <span>Upload .tlog or .BIN</span>
          <input required type="file" name="flight_log" accept=".tlog,.bin">
        </label>
        <button class="primary" type="submit">Analyze</button>
      </form>
      <p class="muted">Available when viewed from the local dashboard server.</p>
    </section>"""
    default_json = json.dumps(default_modules)
    templates = _module_templates(samples, summary, insights, quality)
    warnings = quality.warnings or ["No quality warnings detected"]
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Flight Data Dashboard</title><style>
:root {{
  color-scheme: light;
  --bg: #f5f7fb; --panel: #ffffff; --panel-2: #eef2f7; --text: #18202b; --muted: #657184;
  --line: #d9e0ea; --accent: #1769c2; --accent-2: #0f8f72; --danger: #bf3145; --warn: #b36b00;
  --shadow: 0 12px 36px rgba(29, 39, 58, .11);
}}
[data-theme="dark"] {{
  color-scheme: dark;
  --bg: #0e131b; --panel: #151d29; --panel-2: #101722; --text: #edf3fb; --muted: #98a7ba;
  --line: #263447; --accent: #65a9ff; --accent-2: #43c49b; --danger: #ff6678; --warn: #f0a43c;
  --shadow: 0 16px 40px rgba(0, 0, 0, .28);
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 Inter, Segoe UI, Arial, sans-serif; }}
button {{ font: inherit; }}
.app {{ min-height: 100vh; display: grid; grid-template-columns: minmax(260px, 320px) minmax(0, 1fr); }}
.sidebar {{ position: sticky; top: 0; height: 100vh; overflow: auto; border-right: 1px solid var(--line); padding: 22px; background: var(--panel); }}
.brand h1 {{ font-family: D-DIN-Bold, "D DIN", "Arial Narrow", Arial, sans-serif; letter-spacing: 0; font-size: 30px; line-height: 1.05; margin: 0 0 8px; }}
.muted, small {{ color: var(--muted); }}
.toolbar {{ display: flex; gap: 8px; margin: 18px 0 20px; }}
.toggle, .ghost, .library-item, .icon-button {{ border: 1px solid var(--line); background: var(--panel-2); color: var(--text); border-radius: 8px; cursor: pointer; }}
.primary {{ border: 0; background: var(--accent); color: #fff; border-radius: 8px; cursor: pointer; padding: 10px 12px; font-weight: 700; width: 100%; }}
.toggle, .ghost {{ padding: 9px 11px; }}
.upload-card {{ border: 1px solid var(--line); background: var(--panel-2); border-radius: 8px; padding: 13px; margin: 18px 0; }}
.upload-card h2 {{ font-size: 15px; margin: 0 0 10px; }}
.upload-drop {{ display: grid; gap: 8px; border: 1px dashed var(--line); border-radius: 8px; padding: 11px; margin-bottom: 10px; cursor: pointer; }}
.upload-drop input {{ max-width: 100%; font-size: 13px; }}
.library {{ display: grid; gap: 10px; margin-top: 12px; }}
.library-item {{ display: grid; gap: 2px; text-align: left; padding: 12px; }}
.library-item:hover, .drop-target {{ border-color: var(--accent); }}
.main {{ padding: 26px; min-width: 0; }}
.topbar {{ display: flex; justify-content: space-between; gap: 18px; align-items: start; margin-bottom: 18px; }}
.topbar h2 {{ margin: 0; font-size: 18px; }}
.essentials {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 12px; margin-bottom: 18px; }}
.metric, .module {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; box-shadow: var(--shadow); }}
.metric {{ padding: 15px; min-height: 92px; }}
.metric strong {{ display: block; font-size: 24px; line-height: 1.1; margin-top: 10px; }}
.mini-grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 10px; margin-bottom: 12px; }}
.mini {{ background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 11px; min-height: 74px; }}
.mini strong {{ display: block; margin-top: 5px; font-size: 17px; }}
.status-strip {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 18px; }}
.pill {{ border: 1px solid var(--line); background: var(--panel); border-radius: 999px; padding: 7px 10px; color: var(--muted); }}
.workspace {{ display: grid; gap: 14px; }}
.module {{ padding: 16px; overflow: hidden; }}
.module.dragging {{ opacity: .5; }}
.module-head {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }}
.module-head h2 {{ font-size: 17px; margin: 0; }}
.icon-button {{ padding: 7px 9px; margin-left: 6px; font-size: 13px; }}
.plot {{ margin: 12px 0; }}
.plot-head {{ display: flex; justify-content: space-between; color: var(--muted); margin-bottom: 7px; }}
svg {{ width: 100%; height: auto; background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; }}
polyline {{ fill: none; stroke-width: 3; stroke-linejoin: round; }}
.axis {{ stroke: var(--line); }}
table {{ width: 100%; border-collapse: collapse; }}
th, td {{ padding: 9px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
.assessment {{ font-size: 21px; font-weight: 750; margin-bottom: 12px; }}
.finding {{ border-left: 4px solid var(--line); background: var(--panel-2); padding: 12px; margin: 10px 0; border-radius: 7px; }}
.finding-head {{ display: flex; justify-content: space-between; gap: 12px; }}
.critical {{ border-left-color: var(--danger); }} .warning {{ border-left-color: var(--warn); }} .notice {{ border-left-color: var(--accent); }} .positive {{ border-left-color: var(--accent-2); }}
.quality-hero {{ display: flex; gap: 18px; align-items: center; margin-bottom: 12px; }}
.score {{ font-size: 46px; font-weight: 800; color: var(--accent); line-height: 1; }}
ul {{ padding-left: 20px; }}
@media (max-width: 900px) {{
  .app {{ grid-template-columns: 1fr; }}
  .sidebar {{ position: relative; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }}
  .essentials {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .mini-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .topbar {{ display: block; }}
}}
</style></head>
<body><div class="app">
  <aside class="sidebar">
    <div class="brand"><h1>Flight Data Dashboard</h1><p class="muted">{len(samples)} samples analyzed.</p></div>
    <div class="toolbar">
      <button class="toggle" id="themeToggle" type="button">Toggle theme</button>
      <button class="ghost" id="resetLayout" type="button">Reset</button>
    </div>
    {upload_card}
    <h2>Insight Library</h2>
    <div class="library">{library_html}</div>
  </aside>
  <main class="main">
    <div class="topbar">
      <div><h2>Essential Overview</h2><p class="muted">Core flight facts and signal confidence.</p></div>
      <div class="pill">Quality: {quality.grade} ({quality.score:.0f}/100)</div>
    </div>
    <section class="essentials" aria-label="Essential flight metrics">
      <div class="metric"><span class="muted">Duration</span><strong>{summary.duration_s:.0f} s</strong></div>
      <div class="metric"><span class="muted">Distance</span><strong>{summary.distance_km:.2f} km</strong></div>
      <div class="metric"><span class="muted">Max altitude</span><strong>{summary.max_altitude_m:.1f} m</strong></div>
      <div class="metric"><span class="muted">Max speed</span><strong>{summary.max_groundspeed_m_s:.1f} m/s</strong></div>
      <div class="metric"><span class="muted">Min battery</span><strong>{summary.minimum_battery_pct:.1f}%</strong></div>
    </section>
    <div class="status-strip">{''.join(f'<span class="pill">{html.escape(item)}</span>' for item in warnings[:4])}</div>
    <section id="workspace" class="workspace" aria-label="Analysis workspace"></section>
  </main>
</div>
{templates}
<script>
const defaultModules = {default_json};
const workspace = document.getElementById("workspace");
const storageKey = "flight-dashboard-layout";
const themeKey = "flight-dashboard-theme";
let draggedModule = null;

function createModule(id) {{
  const template = document.getElementById(`template-${{id}}`);
  if (!template) return null;
  const node = template.content.firstElementChild.cloneNode(true);
  node.querySelector(".remove-module").addEventListener("click", () => {{
    node.remove();
    saveLayout();
  }});
  node.addEventListener("dragstart", event => {{
    draggedModule = node;
    node.classList.add("dragging");
    event.dataTransfer.setData("text/plain", id);
  }});
  node.addEventListener("dragend", () => {{
    node.classList.remove("dragging");
    draggedModule = null;
    saveLayout();
  }});
  return node;
}}

function addModule(id) {{
  const node = createModule(id);
  if (!node) return;
  workspace.appendChild(node);
  saveLayout();
}}

function loadLayout() {{
  workspace.innerHTML = "";
  const saved = JSON.parse(localStorage.getItem(storageKey) || "null");
  const modules = Array.isArray(saved) && saved.length ? saved : defaultModules;
  modules.forEach(id => {{
    const node = createModule(id);
    if (node) workspace.appendChild(node);
  }});
}}

function saveLayout() {{
  const ids = [...workspace.querySelectorAll(".module")].map(node => node.dataset.module);
  localStorage.setItem(storageKey, JSON.stringify(ids));
}}

workspace.addEventListener("dragover", event => {{
  event.preventDefault();
  workspace.classList.add("drop-target");
  const after = [...workspace.querySelectorAll(".module:not(.dragging)")].find(child => {{
    const box = child.getBoundingClientRect();
    return event.clientY < box.top + box.height / 2;
  }});
  if (draggedModule) workspace.insertBefore(draggedModule, after || null);
}});
workspace.addEventListener("dragleave", () => workspace.classList.remove("drop-target"));
workspace.addEventListener("drop", event => {{
  event.preventDefault();
  workspace.classList.remove("drop-target");
  const id = event.dataTransfer.getData("text/plain");
  if (!draggedModule && id) addModule(id);
  saveLayout();
}});

document.querySelectorAll(".library-item").forEach(item => {{
  item.addEventListener("click", () => addModule(item.dataset.module));
  item.addEventListener("dragstart", event => event.dataTransfer.setData("text/plain", item.dataset.module));
}});
document.getElementById("resetLayout").addEventListener("click", () => {{
  localStorage.removeItem(storageKey);
  loadLayout();
}});
document.getElementById("themeToggle").addEventListener("click", () => {{
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem(themeKey, next);
}});
document.documentElement.dataset.theme = localStorage.getItem(themeKey) || "light";
loadLayout();
</script></body></html>"""
    destination.write_text(document, encoding="utf-8")

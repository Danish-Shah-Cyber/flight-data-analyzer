from __future__ import annotations

import html
from pathlib import Path

from .analysis import FlightSummary
from .insights import InsightReport
from .model import FlightSample


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


def write_html_report(
    path: str | Path, samples: list[FlightSample], summary: FlightSummary,
    insights: InsightReport | None = None,
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    charts = [
        ("Altitude", "relative_altitude_m", "m", "#56b4e9"),
        ("Ground speed", "groundspeed_m_s", "m/s", "#e69f00"),
        ("Battery remaining", "battery_remaining_pct", "%", "#009e73"),
    ]
    chart_html = "".join(
        f"""<section><h2>{title} ({unit})</h2>
        <svg viewBox="0 0 900 180" role="img" aria-label="{title} plot">
          <line x1="0" y1="170" x2="900" y2="170" class="axis"/>
          <polyline points="{_polyline(samples, field)}" stroke="{color}"/>
        </svg></section>"""
        for title, field, unit, color in charts
    )
    rows = "".join(
        f"<tr><td>{event.time_s:.1f}</td><td>{html.escape(event.kind)}</td>"
        f"<td>{html.escape(event.description)}</td></tr>"
        for event in summary.events
    )
    insight_html = ""
    if insights is not None:
        finding_cards = "".join(
            f"""<article class="finding {html.escape(item.severity)}">
            <div class="finding-head"><strong>{html.escape(item.title)}</strong><span>{html.escape(item.severity.upper())}</span></div>
            <div class="muted">{item.start_s:.1f}–{item.end_s:.1f} s · {html.escape(item.confidence)} confidence</div>
            <p><b>Evidence:</b> {html.escape('; '.join(item.evidence))}</p>
            <p><b>Possible causes:</b> {html.escape('; '.join(item.possible_causes))}</p>
            <p><b>Recommended check:</b> {html.escape(item.recommendation)}</p></article>"""
            for item in insights.findings
        )
        limitations = "".join(f"<li>{html.escape(item)}</li>" for item in insights.limitations)
        limitation_html = f"<h3>Analysis limitations</h3><ul>{limitations}</ul>" if limitations else ""
        insight_html = f"""<section><h2>Flight assessment</h2>
        <div class="assessment">{html.escape(insights.status)}</div>{finding_cards}{limitation_html}
        <p class="muted">Engineering aid only: findings depend on configured thresholds and recorded data.</p></section>"""
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Flight Data Report</title><style>
body{{font:15px system-ui;background:#0d1726;color:#eaf2ff;max-width:1000px;margin:auto;padding:28px}}
h1{{margin-bottom:4px}} .muted{{color:#9fb0c8}} .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:24px 0}}
.card,section{{background:#15243a;border:1px solid #263b59;border-radius:12px;padding:16px}} .value{{font-size:26px;font-weight:700}}
svg{{width:100%;height:auto;background:#101d30;border-radius:8px}} polyline{{fill:none;stroke-width:3;stroke-linejoin:round}} .axis{{stroke:#52657e}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:9px;border-bottom:1px solid #263b59;text-align:left}}
.assessment{{font-size:22px;font-weight:700;margin:8px 0 18px}} .finding{{border-left:5px solid #6c7f99;background:#101d30;padding:14px;margin:12px 0;border-radius:7px}}
.finding-head{{display:flex;justify-content:space-between;gap:16px}} .finding p{{margin:8px 0}} .critical{{border-left-color:#ff4d5e}} .warning{{border-left-color:#f0a43c}} .notice{{border-left-color:#56b4e9}} .positive{{border-left-color:#34c98b}}
</style></head><body><h1>Flight Data Report</h1><div class="muted">{len(samples)} samples analyzed</div>
<div class="cards">
<div class="card"><div class="muted">Duration</div><div class="value">{summary.duration_s:.0f} s</div></div>
<div class="card"><div class="muted">Distance</div><div class="value">{summary.distance_km:.2f} km</div></div>
<div class="card"><div class="muted">Max altitude</div><div class="value">{summary.max_altitude_m:.1f} m</div></div>
<div class="card"><div class="muted">Max ground speed</div><div class="value">{summary.max_groundspeed_m_s:.1f} m/s</div></div>
<div class="card"><div class="muted">Minimum battery</div><div class="value">{summary.minimum_battery_pct:.1f}%</div></div>
</div>{insight_html}{chart_html}<section><h2>Detected events</h2><table><thead><tr><th>Time (s)</th><th>Type</th><th>Description</th></tr></thead><tbody>{rows}</tbody></table></section>
</body></html>"""
    destination.write_text(document, encoding="utf-8")

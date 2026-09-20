"""Standalone HTML rendering of a resilience report.

The output embeds all styles and draws its figures as inline SVG so the file can be
opened from disk without the platform, a network connection or any script.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from reslab_core.duration import format_duration, format_mission_time
from reslab_core.report.model import ResilienceReport
from reslab_core.states import ComponentState
from reslab_core.topology import DOMAIN_ORDER

_TEMPLATES = Path(__file__).parent / "templates"

STATE_COLORS: dict[ComponentState, str] = {
    ComponentState.NOMINAL: "#2fbf71",
    ComponentState.OPERATIONAL: "#2fbf71",
    ComponentState.RECOVERED: "#2fbf71",
    ComponentState.DEGRADED: "#e0a52a",
    ComponentState.UNAVAILABLE: "#d9534f",
    ComponentState.FAILED: "#c0392b",
    ComponentState.RECOVERING: "#e08a2a",
    ComponentState.UNKNOWN: "#5d6b7a",
}


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["duration"] = lambda v: format_duration(float(v)) if v is not None else "n/a"
    env.filters["mission_time"] = lambda v: format_mission_time(float(v))
    env.filters["pct"] = lambda v: f"{float(v) * 100:.1f}%" if v is not None else "n/a"
    env.filters["state_color"] = lambda s: STATE_COLORS.get(ComponentState(str(s)), "#5d6b7a")
    return env


def _path_svg(report: ResilienceReport, width: int = 520, height: int = 360) -> str:
    planned = report.planned_path.waypoints if report.planned_path else []
    actual = report.actual_path
    xs = [p.x for p in planned] + [p.x for p in actual] + [0.0]
    ys = [p.y for p in planned] + [p.y for p in actual] + [0.0]
    if not actual and not planned:
        return ""
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span = max(max_x - min_x, max_y - min_y, 1.0) * 1.15
    cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
    scale = min(width, height) / span

    def sx(x: float) -> float:
        return width / 2 + (x - cx) * scale

    def sy(y: float) -> float:
        return height / 2 - (y - cy) * scale

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        'aria-label="Planned versus actual trajectory (top view)">',
        f'<rect width="{width}" height="{height}" fill="#0b1118" rx="6"/>',
    ]
    step = 50.0
    grid_x = min_x - (min_x % step)
    while grid_x <= max_x + step:
        parts.append(
            f'<line x1="{sx(grid_x):.1f}" y1="0" x2="{sx(grid_x):.1f}" y2="{height}" '
            'stroke="#182230" stroke-width="1"/>'
        )
        grid_x += step
    grid_y = min_y - (min_y % step)
    while grid_y <= max_y + step:
        parts.append(
            f'<line x1="0" y1="{sy(grid_y):.1f}" x2="{width}" y2="{sy(grid_y):.1f}" '
            'stroke="#182230" stroke-width="1"/>'
        )
        grid_y += step
    if planned:
        points = " ".join(f"{sx(p.x):.1f},{sy(p.y):.1f}" for p in planned)
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#4aa3df" stroke-width="1.5" '
            'stroke-dasharray="6 4"/>'
        )
        for i, p in enumerate(planned):
            parts.append(
                f'<circle cx="{sx(p.x):.1f}" cy="{sy(p.y):.1f}" r="4" fill="#0b1118" '
                'stroke="#4aa3df" stroke-width="1.5"/>'
                f'<text x="{sx(p.x) + 7:.1f}" y="{sy(p.y) - 6:.1f}" fill="#8fb8d8" '
                f'font-size="10" font-family="ui-monospace, monospace">WP{i + 1}</text>'
            )
    if actual:
        points = " ".join(f"{sx(p.x):.1f},{sy(p.y):.1f}" for p in actual)
        parts.append(f'<polyline points="{points}" fill="none" stroke="#e6edf3" stroke-width="2"/>')
        last = actual[-1]
        parts.append(f'<circle cx="{sx(last.x):.1f}" cy="{sy(last.y):.1f}" r="5" fill="#2fbf71"/>')
    parts.append(
        f'<text x="12" y="{height - 12}" fill="#8b9bab" font-size="11" '
        'font-family="ui-monospace, monospace">dashed: planned  solid: actual  grid: 50 m</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _timeline_svg(report: ResilienceReport, width: int = 900) -> str:
    duration = max(report.run.simulation_duration, 1.0)
    subsystems: list[str] = []
    for domain in DOMAIN_ORDER:
        for component in report.topology.components:
            if component.domain == domain and component.id not in subsystems:
                subsystems.append(component.id)
    intervals_by_subsystem: dict[str, list] = {}
    for interval in report.subsystem_timeline:
        intervals_by_subsystem.setdefault(interval.subsystem, []).append(interval)
    subsystems = [s for s in subsystems if s in intervals_by_subsystem]
    row_h = 22
    label_w = 190
    height = row_h * len(subsystems) + 30
    plot_w = width - label_w - 20

    def sx(t: float) -> float:
        return label_w + (t / duration) * plot_w

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
        'aria-label="Subsystem state timeline">',
        f'<rect width="{width}" height="{height}" fill="#0b1118" rx="6"/>',
    ]
    tick = 15.0 if duration <= 200 else 60.0
    t = 0.0
    while t <= duration:
        parts.append(
            f'<line x1="{sx(t):.1f}" y1="18" x2="{sx(t):.1f}" y2="{height - 8}" '
            'stroke="#182230" stroke-width="1"/>'
            f'<text x="{sx(t) + 2:.1f}" y="13" fill="#6d7f90" font-size="10" '
            f'font-family="ui-monospace, monospace">{format_mission_time(t)}</text>'
        )
        t += tick
    for row, subsystem in enumerate(subsystems):
        y = 20 + row * row_h
        name = report.topology.component(subsystem).name
        parts.append(
            f'<text x="8" y="{y + 15}" fill="#c9d4de" font-size="11" '
            f'font-family="Inter, system-ui, sans-serif">{name}</text>'
        )
        for interval in intervals_by_subsystem[subsystem]:
            x1, x2 = sx(interval.start), sx(interval.end)
            color = STATE_COLORS.get(interval.state, "#5d6b7a")
            parts.append(
                f'<rect x="{x1:.1f}" y="{y + 5}" width="{max(x2 - x1, 1.0):.1f}" height="12" '
                f'fill="{color}" opacity="0.85"><title>{name}: {interval.state.value} '
                f"{format_mission_time(interval.start)} - {format_mission_time(interval.end)}"
                "</title></rect>"
            )
    for event in report.events:
        if event.kind.value in ("INJECTION_APPLIED",):
            x = sx(event.simulation_time)
            parts.append(
                f'<line x1="{x:.1f}" y1="18" x2="{x:.1f}" y2="{height - 8}" stroke="#e6edf3" '
                'stroke-width="1" stroke-dasharray="2 3" opacity="0.7"/>'
            )
    parts.append("</svg>")
    return "".join(parts)


def render_html_report(report: ResilienceReport) -> str:
    env = _env()
    template = env.get_template("report.html.j2")
    return template.render(
        report=report,
        path_svg=_path_svg(report),
        timeline_svg=_timeline_svg(report),
        state_colors={k.value: v for k, v in STATE_COLORS.items()},
        domain_order=[d.value for d in DOMAIN_ORDER],
    )

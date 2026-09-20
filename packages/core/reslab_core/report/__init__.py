"""Canonical resilience report (JSON) and standalone HTML rendering."""

from reslab_core.report.builder import build_report
from reslab_core.report.html import render_html_report
from reslab_core.report.model import ReportArtifact, ReportSummary, ResilienceReport

__all__ = [
    "ReportArtifact",
    "ReportSummary",
    "ResilienceReport",
    "build_report",
    "render_html_report",
]

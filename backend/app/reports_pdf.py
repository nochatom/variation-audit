"""Render a variation review report (build_report dict) to PDF bytes.

Pure-Python via reportlab — no native deps, works in any AU-region container.
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _aud(n) -> str:
    return f"${n:,.0f}" if n is not None else "—"


def render_report_pdf(report: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Variation Review Report",
                            topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    flow = []

    project = report.get("project", {})
    summary = report.get("summary", {})
    baseline = report.get("baseline") or {}

    flow.append(Paragraph("Variation Review Report", styles["Title"]))
    flow.append(Paragraph(
        f"Project: <b>{project.get('name', '')}</b> &nbsp;|&nbsp; "
        f"State: {project.get('state') or 'N/A'} &nbsp;|&nbsp; "
        f"Showing: {report.get('status_filter', '')} variations",
        styles["Normal"]))
    flow.append(Paragraph(f"Generated: {report.get('generated_at', '')}", styles["Normal"]))
    flow.append(Spacer(1, 6 * mm))

    # Summary box
    flow.append(Paragraph(
        f"<b>Recoverable total: {_aud(summary.get('recoverable_total'))} "
        f"{summary.get('currency', 'AUD')}</b> &nbsp; "
        f"across {summary.get('variation_count', 0)} variation(s); "
        f"{summary.get('time_bar_at_risk', 0)} with time-bar risk.",
        styles["Normal"]))
    if baseline:
        flow.append(Paragraph(
            f"SoP regime: {baseline.get('sop_regime') or 'N/A'} &nbsp;|&nbsp; "
            f"Notice clause: {baseline.get('notice_clause') or 'N/A'} &nbsp;|&nbsp; "
            f"Time-bar: {baseline.get('time_bar_days') if baseline.get('time_bar_days') is not None else 'N/A'} days",
            styles["Italic"]))
    flow.append(Spacer(1, 6 * mm))

    # Variations table
    head = ["Variation", "Confidence", "Time-bar", "Est. value (AUD)", "Basis", "Evidence"]
    rows = [head]
    for v in report.get("variations", []):
        val = v.get("value") or {}
        rows.append([
            Paragraph(v.get("title", ""), styles["Normal"]),
            f"{v.get('confidence_band') or ''} ({v.get('confidence_score', 0):.2f})",
            "YES" if v.get("time_bar_risk") else "no",
            _aud(val.get("amount")),
            (val.get("basis_quality") or "—"),
            str(v.get("evidence_count", 0)),
        ])

    table = Table(rows, colWidths=[60 * mm, 28 * mm, 18 * mm, 30 * mm, 22 * mm, 18 * mm],
                  repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(table)
    flow.append(Spacer(1, 6 * mm))
    flow.append(Paragraph(
        "<i>Estimates only — every figure requires commercial-team confirmation before "
        "submission. Not legal advice.</i>", styles["Italic"]))

    doc.build(flow)
    return buf.getvalue()

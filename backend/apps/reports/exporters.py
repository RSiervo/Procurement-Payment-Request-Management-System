import csv
import io
from datetime import date
from decimal import Decimal

from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.models import SystemConfig


def _safe(value):
    """Neutralise spreadsheet formula injection in user-entered text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _text(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return value.isoformat() if isinstance(value, date) else str(value)


def _attachment(content, content_type, filename):
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def as_csv(title, headers, rows, filename):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows([_safe(_text(cell)) for cell in row] for row in rows)
    # BOM so Excel opens UTF-8 names and symbols correctly.
    return _attachment("﻿" + buffer.getvalue(), "text/csv; charset=utf-8", f"{filename}.csv")


def as_xlsx(title, headers, rows, filename):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([float(c) if isinstance(c, Decimal) else _safe(c) for c in row])
    for index, header in enumerate(headers, start=1):
        longest = max([len(str(header))] + [len(_text(r[index - 1])) for r in rows[:200]])
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = min(longest + 2, 50)
    sheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return _attachment(buffer.getvalue(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"{filename}.xlsx")


def as_pdf(title, headers, rows, filename):
    from apps.requests.pdf import _load_fonts

    regular, bold, _ = _load_fonts()
    config = SystemConfig.load()
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = regular
    cell_style = styles["BodyText"].clone("cell", fontSize=8, leading=10)

    def cell(value):
        text = f"{value:,.2f}" if isinstance(value, Decimal) else _text(value)
        return Paragraph(text.replace("&", "&amp;").replace("<", "&lt;"), cell_style)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=title)
    table = Table([[cell(h) for h in headers]] + [[cell(c) for c in row] for row in rows], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9aa3af")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0f3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    heading = styles["Heading2"].clone("heading", fontName=bold)
    generated = timezone.localtime().strftime("%B %d, %Y %I:%M %p")
    doc.build([Paragraph(f"{config.company_name} — {title}".replace("&", "&amp;"), heading),
               Paragraph(f"Generated {generated} · {len(rows)} row(s)", styles["BodyText"]),
               Spacer(1, 4 * mm), table])
    return _attachment(buffer.getvalue(), "application/pdf", f"{filename}.pdf")


EXPORTERS = {"csv": as_csv, "xlsx": as_xlsx, "pdf": as_pdf}

"""The printable purchase order OPS issues to a supplier from an approved requisition."""

import io

from django.conf import settings
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.approvals import timeline
from apps.approvals.models import StepStatus
from apps.core.models import SystemConfig
from apps.core.utils import format_date, format_quantity

from .pdf import _load_fonts

GREY = colors.HexColor("#5b6675")
LINE = colors.HexColor("#9aa3af")


def _escape(value):
    return str(value or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_purchase_order(req):
    regular, bold, unicode_ok = _load_fonts()
    config = SystemConfig.load()
    symbol = config.currency_symbol if unicode_ok else f"{config.currency_code} "
    money = lambda amount: f"{symbol}{amount:,.2f}"  # noqa: E731

    body = ParagraphStyle("body", fontName=regular, fontSize=9, leading=12)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10, textColor=GREY)
    label = ParagraphStyle("label", parent=small, fontName=bold, textColor=GREY)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    title = ParagraphStyle("title", fontName=bold, fontSize=16, leading=20, alignment=TA_RIGHT)

    # Header: company on the left, document title and number on the right.
    company = [Paragraph(f"<font name='{bold}' size='12'>{_escape(config.company_name)}</font>", body)]
    company += [Paragraph(_escape(row.strip()), small) for row in config.company_address.splitlines()[:3]]
    if config.logo:
        try:
            company.insert(0, Image(config.logo.path, width=28 * mm, height=14 * mm, kind="proportional", hAlign="LEFT"))
        except Exception:
            pass  # a broken logo file must not block printing
    heading = [
        Paragraph("PURCHASE ORDER", title),
        Paragraph(f"<font name='{bold}'>No. {_escape(req.po_number)}</font>", right),
        Paragraph(f"Date: {format_date(req.po_date)}", right),
        Paragraph(f"Requisition: {_escape(req.number)}", right),
    ]
    header = Table([[company, heading]], colWidths=[100 * mm, 86 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))

    supplier = [Paragraph("SUPPLIER", label), Paragraph(f"<font name='{bold}'>{_escape(req.payable_to)}</font>", body)]
    if req.vendor_id:
        if req.vendor.address:
            supplier.append(Paragraph(_escape(req.vendor.address), small))
        if req.vendor.tin:
            supplier.append(Paragraph(f"TIN: {_escape(req.vendor.tin)}", small))
    deliver = [
        Paragraph("DELIVER TO", label),
        Paragraph(f"<font name='{bold}'>{_escape(req.department.name)}</font>", body),
        Paragraph(f"Attention: {_escape(req.requester.display_name)}", small),
        Paragraph(f"Needed by: {format_date(req.date_needed) if req.date_needed else 'not stated'}", small),
    ]
    parties = Table([[supplier, deliver]], colWidths=[93 * mm, 93 * mm])
    parties.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 0.5, LINE), ("BOX", (1, 0), (1, 0), 0.5, LINE),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 6),
                                 ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))

    rows = [[Paragraph(f"<font name='{bold}'>{text}</font>", body if index < 3 else right)
             for index, text in enumerate(("#", "Qty", "Description", "Unit cost", "Amount"))]]
    for number, line in enumerate(req.lines.all(), start=1):
        description = _escape(line.description) + (f"<br/><font size='7.5' color='#5b6675'>{_escape(line.remarks)}</font>" if line.remarks else "")
        rows.append([
            Paragraph(str(number), body), Paragraph(format_quantity(line.quantity), body), Paragraph(description, body),
            Paragraph(money(line.unit_cost) if line.unit_cost is not None else "-", right),
            Paragraph(money(line.amount) if line.unit_cost is not None else "-", right),
        ])
    rows.append(["", "", Paragraph(f"<font name='{bold}'>TOTAL</font>", right), "",
                 Paragraph(f"<font name='{bold}'>{money(req.total_amount)}</font>", right)])
    items = Table(rows, colWidths=[9 * mm, 17 * mm, 102 * mm, 28 * mm, 30 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -2), 0.4, LINE), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0f3")),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    approvers = [f"{step.name}: {step.acted_by.display_name}" for step in timeline.approval_records(req)
                 if step.status == StepStatus.APPROVED and step.acted_by_id]
    issued_by = req.po_issued_by.display_name if req.po_issued_by_id else "OPS"
    code = QrCodeWidget(f"{settings.FRONTEND_URL}/verify/{req.id}", barLevel="M")
    left, bottom, right_edge, top = code.getBounds()
    size = 20 * mm
    qr = Drawing(size, size, transform=[size / (right_edge - left), 0, 0, size / (top - bottom), 0, 0])
    qr.add(code)
    closing = Table([[
        [Paragraph("TERMS", label), Paragraph(_escape(req.po_terms) or "As agreed.", body), Spacer(1, 4 * mm),
         Paragraph("ISSUED BY", label), Paragraph(f"<font name='{bold}'>{_escape(issued_by)}</font>", body),
         Paragraph("Operations", small), Spacer(1, 3 * mm),
         Paragraph("REQUISITION APPROVED BY", label), Paragraph(_escape("; ".join(approvers)) or "-", small)],
        [qr, Paragraph("Scan to verify", small)],
    ]], colWidths=[160 * mm, 26 * mm])
    closing.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=f"Purchase Order {req.po_number}", author=config.company_name)
    doc.build([header, Spacer(1, 6 * mm), parties, Spacer(1, 6 * mm), items, Spacer(1, 8 * mm), closing,
               Spacer(1, 6 * mm),
               Paragraph("This purchase order was generated from an approved requisition in the Procurement & Payment "
                         "Portal. Prices are those recorded on the requisition; quote this PO number on the invoice.", small)])
    return buffer.getvalue()

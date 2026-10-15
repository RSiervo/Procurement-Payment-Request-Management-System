"""Printable versions of the company's paper forms.

Two layouts, drawn to match the pre-printed originals:

* Request for Payment - also used for reimbursements.
* Purchase Requisition.

Each form occupies the top half of an A4 sheet (the size of the paper originals), with
a cut guide across the middle. Long requests continue on further sheets. Each signature
box carries the signer's own uploaded e-signature - the copy kept at the moment they
submitted or approved - with their name, position and the time it was applied.
"""

import io
import math
import os
import re

from django.conf import settings
from django.utils import timezone
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from apps.approvals import timeline
from apps.approvals.models import StepStatus
from apps.core.models import SystemConfig
from apps.core.utils import format_date, format_datetime, format_quantity
from apps.workflows.models import ApproverType

from .models import FormKind

# A Unicode font is needed for currency symbols such as the peso sign.
_FONT_CANDIDATES = [
    (os.environ.get("PDF_FONT_PATH", ""), os.environ.get("PDF_FONT_BOLD_PATH", "")),
    (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
]
_fonts = None


def _load_fonts():
    """Return (regular, bold, supports_unicode), registering a TrueType pair once."""
    global _fonts
    if _fonts is None:
        _fonts = ("Helvetica", "Helvetica-Bold", False)
        for regular, bold in _FONT_CANDIDATES:
            if regular and bold and os.path.exists(regular) and os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("Form", regular))
                pdfmetrics.registerFont(TTFont("Form-Bold", bold))
                _fonts = ("Form", "Form-Bold", True)
                break
    return _fonts


PAGE_W, PAGE_H = A4
MARGIN = 10 * mm                 # left and right
WIDTH = PAGE_W - 2 * MARGIN      # 190 mm
TOP = PAGE_H - 8 * mm            # top edge of the form
SERIF_BOLD = "Times-Bold"        # the company name on the paper forms is a bold serif
GREY = colors.HexColor("#555555")
RED = colors.HexColor("#b01217")

# Department tick boxes pre-printed on the Request for Payment form, with their
# positions in mm from the left edge of the box.
DEPT_BOXES = [("ADM-A", 15), ("ADM-B", 34), ("MKTG.", 53), ("BRC", 71), ("FIN", 86), ("P. SECTOR", 100),
              ("FSI", 124), ("MRD", 138)]
DEPT_OTHER_AT = 153


def _key(text):
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


class _Form:
    """Shared drawing helpers. Distances are in mm, measured from the form's top-left corner."""

    def __init__(self, req):
        self.req = req
        self.config = SystemConfig.load()
        self.regular, self.bold, unicode_ok = _load_fonts()
        self.currency = self.config.currency_symbol if unicode_ok else f"{self.config.currency_code} "
        self.steps = timeline.approval_records(req)
        self.c = None

    # -- coordinates and primitives --
    @staticmethod
    def x(d):
        return MARGIN + d * mm

    @staticmethod
    def y(d):
        return TOP - d * mm

    def line(self, x1, y1, x2, y2, width=0.8):
        self.c.setLineWidth(width)
        self.c.line(self.x(x1), self.y(y1), self.x(x2), self.y(y2))

    def box(self, x, y, w, h, width=0.8):
        self.c.setLineWidth(width)
        self.c.rect(self.x(x), self.y(y + h), w * mm, h * mm, stroke=1, fill=0)

    def text(self, x, y, value, size=8, bold=False, align="left", color=colors.black, font=None):
        font = font or (self.bold if bold else self.regular)
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        draw = {"left": self.c.drawString, "right": self.c.drawRightString, "center": self.c.drawCentredString}[align]
        draw(self.x(x), self.y(y), str(value))
        self.c.setFillColor(colors.black)

    def fit(self, x, y, value, width, size=8, min_size=5, **kwargs):
        """One line of text, shrunk (then cut with an ellipsis) so it never leaves its box."""
        value = str(value or "")
        font = kwargs.get("font") or (self.bold if kwargs.get("bold") else self.regular)
        while size > min_size and pdfmetrics.stringWidth(value, font, size) > width * mm:
            size -= 0.25
        while len(value) > 1 and pdfmetrics.stringWidth(value, font, size) > width * mm:
            value = value[:-2].rstrip() + "…"
        self.text(x, y, value, size=size, **kwargs)

    def wrap(self, value, width, size=8, bold=False):
        return simpleSplit(str(value or ""), self.bold if bold else self.regular, size, width * mm)

    def tick_box(self, x, y, ticked, size=2.6):
        self.box(x, y, size, size, width=0.7)
        if ticked:
            self.line(x + 0.4, y + 0.4, x + size - 0.4, y + size - 0.4, width=1.1)
            self.line(x + size - 0.4, y + 0.4, x + 0.4, y + size - 0.4, width=1.1)

    def money(self, amount):
        return f"{self.currency}{amount:,.2f}"

    # -- shared sections --
    def header(self):
        """Logo on the left; company name and address centred, as on the pre-printed forms."""
        if self.config.logo:
            try:
                image = ImageReader(self.config.logo.path)
                iw, ih = image.getSize()
                height = 15 * mm
                width = min(height * iw / ih, 32 * mm)
                self.c.drawImage(image, self.x(3), self.y(15.5), width=width, height=height,
                                 preserveAspectRatio=True, anchor="sw", mask="auto")
            except Exception:
                pass  # a broken logo file must not block printing the form
        name = self.config.company_name.upper()
        size = 12.5
        while size > 8 and pdfmetrics.stringWidth(name, SERIF_BOLD, size) > 118 * mm:
            size -= 0.25
        self.text(95, 6, name, size=size, align="center", font=SERIF_BOLD)
        for index, row in enumerate(self.config.company_address.splitlines()[:2]):
            self.text(95, 10 + index * 3.4, row.strip(), size=8, align="center", font="Times-Roman")

    def verify_code(self):
        """QR code that opens the verification page, so a paper copy can be checked against the record."""
        if not self.req.number:
            return
        size = 11.5 * mm
        code = QrCodeWidget(f"{settings.FRONTEND_URL}/verify/{self.req.id}", barLevel="M")
        left, bottom, right, top = code.getBounds()
        drawing = Drawing(size, size, transform=[size / (right - left), 0, 0, size / (top - bottom), 0, 0])
        drawing.add(code)
        renderPDF.draw(drawing, self.c, self.x(178.5), self.y(16.4))
        self.text(184.25, 18.1, "Scan to verify", size=4.5, align="center", color=GREY)

    def record(self, step):
        """(name, position, when) for a signature box; name is empty when nobody has acted."""
        if step is None:
            return "", "", ""
        if step.status == StepStatus.APPROVED:
            return step.acted_by.display_name, step.acted_by_position, f"e-approved {format_datetime(step.acted_at)}"
        if step.status in (StepStatus.REJECTED, StepStatus.RETURNED):
            return (step.acted_by.display_name, step.acted_by_position,
                    f"{step.get_status_display()} {format_datetime(step.acted_at)}")
        if step.status == StepStatus.PENDING:
            return "", "", "Pending approval"
        if step.status == StepStatus.SKIPPED:
            return "", "", "Not applicable"
        return "", "", ""

    def assign(self, slots):
        """Place the workflow's approval steps into the form's fixed signature boxes.

        Workflows are configurable, the paper boxes are not, so steps are matched by what
        they are (department head, finance, "verified", "approved") and anything left
        over takes the next empty box. Returns (placed, leftover_steps).
        """
        placed, remaining = {}, []
        for step in self.steps:
            name = step.name.lower()
            role = step.role.code if step.role_id else ""
            if "verif" in name:
                want = "verified"
            elif step.approver_type == ApproverType.DEPARTMENT_HEAD or "head" in name or "noted" in name:
                want = "head"
            elif role == "FINANCE" or "finance" in name:
                want = "finance"
            elif "approv" in name or "management" in name:
                want = "approved"
            else:
                want = None
            if want in slots and want not in placed:
                placed[want] = step
            else:
                remaining.append(step)
        # The last step of the route is the final approval.
        if "approved" not in placed and remaining:
            placed["approved"] = remaining.pop()
        for slot in slots:
            if slot not in placed and slot != "finance" and remaining:
                placed[slot] = remaining.pop(0)
        return placed, remaining

    def stamp(self, field, x, y, width, height):
        """Draw a stored e-signature inside the box (x, y, width, height), keeping its proportions."""
        if not field:
            return False
        try:
            image = ImageReader(field.path)
            iw, ih = image.getSize()
            scale = min(width * mm / iw, height * mm / ih)
            self.c.drawImage(image, self.x(x), self.y(y + height), width=iw * scale, height=ih * scale, mask="auto")
            return True
        except Exception:
            return False  # a missing or unreadable image must not block printing the form

    def half_signature(self, x, top, width, step, name_y, when_y):
        """A signature in a half-height box: the e-signature sits to the right of the name."""
        name, _, when = self.record(step)
        if name:
            inked = step.status == StepStatus.APPROVED and self.stamp(step.signature, x + width - 15, top + 0.8, 15, 6.2)
            self.fit(x, name_y, name, width - (16 if inked else 0), size=6.5, bold=True)
        if when:
            self.fit(x, when_y, when, width, size=5.5, color=GREY)

    def signature(self, x, y, width, step, name_size=7, compact=False, ink=0):
        """E-signature (in a strip `ink` mm tall), then name, position and approval line, top-down from y."""
        name, position, when = self.record(step)
        if ink:
            if step is not None and step.status == StepStatus.APPROVED:
                self.stamp(step.signature, x, y, width, ink)
            y += ink + 3
        if name:
            self.fit(x, y, name, width, size=name_size, bold=True)
            y += 2.5 if compact else 3
            if position and not compact:
                self.fit(x, y, position, width, size=6, color=GREY)
                y += 2.6
        if when:
            self.fit(x, y, when, width, size=5.5, color=GREY)

    def footnotes(self, y, notes, page, pages):
        """Small print under the form: leftovers the paper layout has no box for, and provenance."""
        req = self.req
        tail = f"{req.display_number} · {req.get_status_display()} · Generated {format_datetime(timezone.now())}"
        if pages > 1:
            tail += f" · Sheet {page} of {pages}"
        notes = [*notes, tail + " · E-signatures were applied by the signers themselves through the "
                               "Procurement & Payment Portal, which keeps the full approval record."]
        for note in notes:
            for row in self.wrap(note, 190, size=5.5)[:2]:
                self.text(0, y, row, size=5.5, color=GREY)
                y += 2.4

    def other_approvals(self, leftover):
        notes = []
        for step in leftover:
            name, _, when = self.record(step)
            if name or when:
                notes.append(f"{step.name}: {name} {when}".replace("  ", " ").strip())
        return ["Other approvals — " + "; ".join(notes)] if notes else []

    def cut_guide(self):
        self.c.saveState()
        self.c.setDash(1, 3)
        self.c.setStrokeColor(colors.HexColor("#999999"))
        self.c.setLineWidth(0.4)
        self.c.line(0, PAGE_H / 2, PAGE_W, PAGE_H / 2)
        self.c.restoreState()

    def render(self):
        buffer = io.BytesIO()
        self.c = Canvas(buffer, pagesize=A4)
        self.c.setTitle(f"{self.req.request_type.name} {self.req.display_number}")
        self.c.setAuthor(self.config.company_name)
        sheets = self.paginate() or [[]]
        for index, rows in enumerate(sheets, start=1):
            self.header()
            self.verify_code()
            self.draw(rows, index, len(sheets))
            self.cut_guide()
            self.c.showPage()
        self.c.save()
        return buffer.getvalue()


class _PaymentForm(_Form):
    """REQUEST FOR PAYMENT - also printed for reimbursements."""

    TABLE_TOP = 44
    HEAD_H = 6
    BODY_H = 38
    LEADING = 3.7
    AMOUNT_X = 140   # the AMOUNT column starts here; PARTICULARS is to its left

    def paginate(self):
        req, expense = self.req, self.req.request_type.form_kind == FormKind.EXPENSE
        rows = []
        for line in req.lines.select_related("category"):
            if expense:
                lead = " · ".join(x for x in (format_date(line.expense_date), line.category.name if line.category_id else "") if x)
                text = f"{lead} — {line.description}" if lead else line.description
            else:
                text = f"{line.description} — {line.remarks}" if line.remarks else line.description
            rows.append((self.wrap(text, self.AMOUNT_X - 4, size=8), self.money(line.amount)))
        if req.purpose.strip():
            rows.append((self.wrap(f"Purpose: {req.purpose.strip()}", self.AMOUNT_X - 4, size=7.5), ""))

        capacity = int((self.BODY_H - 2) / self.LEADING)
        sheets, current, used = [], [], 0
        for text, amount in rows:
            text = text[:capacity]
            if current and used + len(text) > capacity:
                sheets.append(current)
                current, used = [], 0
            current.append((text, amount))
            used += len(text)
        if current:
            sheets.append(current)
        return sheets

    def draw(self, rows, page, pages):
        req = self.req
        self.text(190, 3.5, f"No. {req.display_number}", size=8.5, bold=True, align="right", color=RED)
        self.text(95, 22, "REQUEST FOR PAYMENT", size=10.5, align="center", font=SERIF_BOLD)
        subtitle = {"CA": "(CASH ADVANCE)", "LIQ": "(LIQUIDATION OF CASH ADVANCE)"}.get(
            req.request_type.code, "(REIMBURSEMENT)" if req.request_type.form_kind == FormKind.EXPENSE else "")
        if subtitle:
            self.text(95, 25.4, subtitle, size=7, align="center")

        # Payable / date
        self.text(1, 31.5, "PAYABLE:", size=8.5, font=SERIF_BOLD)
        self.line(18, 32, 116, 32, width=0.6)
        self.fit(19.5, 31, req.payable_to, 95, size=9)
        self.text(121, 31.5, "DATE:", size=8.5, font=SERIF_BOLD)
        self.line(132, 32, 190, 32, width=0.6)
        self.text(133.5, 31, format_date(timezone.localtime(req.submitted_at or req.created_at).date()), size=9)

        # Department tick boxes
        self.box(0, 34.5, 190, 6.5)
        self.text(1.5, 38.9, "DEPT.:", size=8.5, font=SERIF_BOLD)
        department = req.department
        matched = False
        for label, at in DEPT_BOXES:
            ticked = _key(label) in (_key(department.code), _key(department.name))
            matched = matched or ticked
            self.tick_box(at, 36.4, ticked)
            self.text(at + 3.6, 38.8, label, size=7.5, font="Times-Roman")
        self.tick_box(DEPT_OTHER_AT, 36.4, not matched)
        self.line(DEPT_OTHER_AT + 3.6, 39.2, 188.5, 39.2, width=0.5)
        if not matched:
            self.fit(DEPT_OTHER_AT + 4, 38.6, department.name, 188 - DEPT_OTHER_AT - 4, size=7, min_size=4.5)

        # Particulars / amount
        top, head, body = self.TABLE_TOP, self.HEAD_H, self.BODY_H
        refs_y, total_y = top + head + body, top + head + body + 5
        bottom = total_y + 5.5
        self.box(0, top, 190, bottom - top)
        self.line(0, top + head, 190, top + head)
        self.line(self.AMOUNT_X, top, self.AMOUNT_X, bottom)
        self.text(self.AMOUNT_X / 2, top + 4.3, "PARTICULARS", size=9, align="center", font=SERIF_BOLD)
        self.text((self.AMOUNT_X + 190) / 2, top + 4.3, "AMOUNT", size=9, align="center", font=SERIF_BOLD)

        y = top + head + 4
        for text, amount in rows:
            if amount:
                self.text(188, y, amount, size=8.5, align="right")
            for row in text:
                self.text(2, y, row, size=8)
                y += self.LEADING

        self.line(0, refs_y, self.AMOUNT_X, refs_y, width=0.5)
        pr = req.source_request.number if req.source_request_id else req.pr_reference
        first_label = "CA#" if req.request_type.code == "LIQ" else "PR#"
        for label, value, at, room in ((first_label, pr, 1.5, 28), ("PO#", req.po_number, 37, 28),
                                       ("RIR#", req.rr_number, 73, 26), ("INV#", req.invoice_number, 108, 23)):
            self.text(at, refs_y + 3.6, label, size=7.5, font="Times-Roman")
            self.fit(at + 7.5, refs_y + 3.6, value, room, size=7.5, bold=True)
        self.line(0, total_y, 190, total_y)
        self.text(1.5, total_y + 3.9, "Posted:", size=7.5, font="Times-Roman")
        self.tick_box(13.5, total_y + 1.4, req.posted is True)
        self.text(17.3, total_y + 3.9, "YES", size=7.5, font="Times-Roman")
        self.tick_box(26, total_y + 1.4, req.posted is False)
        self.text(29.8, total_y + 3.9, "NO", size=7.5, font="Times-Roman")
        self.text(self.AMOUNT_X - 2, total_y + 4, "TOTAL", size=9, align="right", font=SERIF_BOLD)
        if page == pages:
            self.text(188, total_y + 4, self.money(req.total_amount), size=9.5, bold=True, align="right")
        else:
            self.text(188, total_y + 4, "continued", size=7.5, align="right", color=GREY)

        # Signature boxes
        placed, leftover = self.assign(["head", "finance", "verified", "approved"])
        sig, height, col = bottom + 3, 26, 38
        self.box(0, sig, 190, height)
        for index in range(1, 5):
            self.line(index * col, sig, index * col, sig + height)
        for index, label in enumerate(("Prepared By:", "Requested By:", "Noted By:", "Verified By:", "Approved By:")):
            self.text(index * col + 1.5, sig + 3.4, label, size=7.5, font=SERIF_BOLD)

        submitted = format_datetime(req.submitted_at) if req.submitted_at else ""
        ink = 8.4  # height of the e-signature strip under each box label
        self.stamp(req.requester_signature, 1.5, sig + 4.6, col - 3, ink)
        self.fit(1.5, sig + 16, req.prepared_by.display_name, col - 3, size=7, bold=True)
        self.fit(1.5, sig + 19, req.prepared_by.position, col - 3, size=6, color=GREY)
        self.text(1.5, sig + height - 1.6, "Date:", size=7, font="Times-Roman")
        self.fit(9, sig + height - 1.6, submitted, col - 10.5, size=6)
        self.stamp(req.requester_signature, col + 1.5, sig + 4.6, col - 3, ink)
        self.fit(col + 1.5, sig + 16, req.requester.display_name, col - 3, size=7, bold=True)
        self.fit(col + 1.5, sig + 19, req.requester.position, col - 3, size=6, color=GREY)
        if submitted:
            self.fit(col + 1.5, sig + 21.6, f"e-submitted {submitted}", col - 3, size=5.5, color=GREY)

        # "Noted By" is split: department head above, finance below.
        half = sig + height / 2
        self.line(2 * col, half, 3 * col, half, width=0.6)
        self.half_signature(2 * col + 1.5, sig, col - 3, placed.get("head"), name_y=sig + 6.6, when_y=sig + 9.5)
        self.text(2.5 * col, half - 1, "Department Head", size=6.5, align="center", font="Times-Roman")
        self.half_signature(2 * col + 1.5, half, col - 3, placed.get("finance"), name_y=half + 3.4, when_y=half + 8.7)
        self.text(2.5 * col, sig + height - 1.4, "Finance", size=7, align="center", font=SERIF_BOLD)
        self.signature(3 * col + 1.5, sig + 4.6, col - 3, placed.get("verified"), ink=ink)
        self.signature(4 * col + 1.5, sig + 4.6, col - 3, placed.get("approved"), ink=ink)

        note = sig + height + 2.6
        self.text(0.5, note, "Note: Approving officers whose signature appears above assumes full responsibility "
                             "for this payment.", size=6, font="Times-Roman")
        notes = self.other_approvals(leftover)
        if req.request_type.code == "LIQ" and req.source_request_id:
            advanced, spent = req.source_request.total_amount, req.total_amount
            balance = (f"to be returned by the employee {self.money(advanced - spent)}" if advanced > spent
                       else f"to be reimbursed to the employee {self.money(spent - advanced)}" if spent > advanced
                       else "fully accounted for")
            notes.insert(0, f"Cash advance {req.source_request.number}: {self.money(advanced)} · "
                            f"Spent: {self.money(spent)} · Balance: {balance}")
        self.footnotes(note + 3, notes, page, pages)


class _RequisitionForm(_Form):
    """PURCHASE REQUISITION: eight ruled rows, then the date / requester / approval strip."""

    TABLE_TOP = 19
    HEAD_H = 8
    ROW_H = 8.5
    ROWS = 8
    COLS = (0, 17, 97, 190)                 # quantity | description | purpose / remarks
    STRIP = (0, 22, 60, 94, 120, 155, 190)  # date | requested by | dept. | date needed | noted by | approved by

    def paginate(self):
        """Each ruled row holds two lines of text; a long item simply runs on into the next row."""
        slots = []
        for line in self.req.lines.all():
            description = self.wrap(line.description, self.COLS[2] - self.COLS[1] - 3, size=7.5)
            remarks = self.wrap(line.remarks, self.COLS[3] - self.COLS[2] - 3, size=7.5)
            for part in range(max(1, math.ceil(max(len(description), len(remarks)) / 2))):
                slots.append((format_quantity(line.quantity) if part == 0 else "",
                              description[part * 2:part * 2 + 2], remarks[part * 2:part * 2 + 2]))
        return [slots[start:start + self.ROWS] for start in range(0, len(slots), self.ROWS)]

    def draw(self, rows, page, pages):
        req = self.req
        top, head, row_h = self.TABLE_TOP, self.HEAD_H, self.ROW_H
        body_bottom = top + head + self.ROWS * row_h
        strip_h = 22
        bottom = body_bottom + strip_h

        self.box(0, top, 190, bottom - top, width=1)
        self.line(0, top + head, 190, top + head, width=1)
        for at in self.COLS[1:3]:
            self.line(at, top, at, body_bottom)
        self.text(1.5, top + 3.4, "QUANTITY", size=7, bold=True)
        self.text((self.COLS[1] + self.COLS[2]) / 2, top + 5.2, "DESCRIPTION", size=8, align="center")
        self.text((self.COLS[2] + self.COLS[3]) / 2, top + 5.2, "SPECIFY PURPOSE/REMARKS", size=8, align="center")
        for index in range(1, self.ROWS + 1):
            self.line(0, top + head + index * row_h, 190, top + head + index * row_h, width=1 if index == self.ROWS else 0.6)

        for index, (quantity, description, remarks) in enumerate(rows):
            y = top + head + index * row_h
            if quantity:
                self.text(self.COLS[1] / 2, y + 5.3, quantity, size=8.5, align="center")
            for offset, row in enumerate(description):
                self.text(self.COLS[1] + 1.5, y + 3.7 + offset * 3.5, row, size=7.5)
            for offset, row in enumerate(remarks):
                self.text(self.COLS[2] + 1.5, y + 3.7 + offset * 3.5, row, size=7.5)

        # Date / requester / approvals strip
        placed, leftover = self.assign(["head", "approved"])
        for at in self.STRIP[1:-1]:
            self.line(at, body_bottom, at, bottom)
        labels = ("DATE:", "REQUESTED BY:", "DEPT.", "DATE NEEDED:", "NOTED BY:", "APPROVED BY:")
        for label, at in zip(labels, self.STRIP):
            self.text(at + 1.2, body_bottom + 3, label, size=6.5)
        width = lambda index: self.STRIP[index + 1] - self.STRIP[index] - 2.4  # noqa: E731
        y = body_bottom + 6.8
        self.fit(self.STRIP[0] + 1.2, y, format_date(timezone.localtime(req.submitted_at or req.created_at).date()), width(0), size=7)
        ink = 7.2
        self.stamp(req.requester_signature, self.STRIP[1] + 1.2, body_bottom + 3.8, width(1), ink)
        self.fit(self.STRIP[1] + 1.2, body_bottom + 14, req.requester.display_name, width(1), size=7, bold=True)
        self.fit(self.STRIP[1] + 1.2, body_bottom + 17, req.requester.position, width(1), size=5.5, color=GREY)
        for offset, row in enumerate(self.wrap(req.department.name, width(2), size=6)[:3]):
            self.text(self.STRIP[2] + 1.2, y - 0.6 + offset * 2.5, row, size=6)
        self.fit(self.STRIP[3] + 1.2, y, format_date(req.date_needed), width(3), size=7)
        self.signature(self.STRIP[4] + 1.2, body_bottom + 3.8, width(4), placed.get("head"), name_size=6.5, ink=ink)
        self.signature(self.STRIP[5] + 1.2, body_bottom + 3.8, width(5), placed.get("approved"), name_size=6.5, ink=ink)

        self.text(1, bottom + 4, "HEAD OFFICE:", size=6.5)
        self.text(190, bottom + 5.5, req.display_number, size=11, bold=True, align="right", color=RED)
        number_width = pdfmetrics.stringWidth(req.display_number, self.bold, 11) / mm
        self.text(190 - number_width - 2, bottom + 5.5, "Purchase Requisition  No.", size=8.5, bold=True, align="right")

        notes = []
        if req.purpose.strip():
            notes.append(f"Purpose: {req.purpose.strip()}")
        if req.total_amount:
            notes.append(f"Estimated total: {self.money(req.total_amount)}")
        self.footnotes(bottom + 10, [*notes, *self.other_approvals(leftover)], page, pages)


def render_request_pdf(req):
    form = _RequisitionForm if req.request_type.form_kind == FormKind.ITEMS else _PaymentForm
    return form(req).render()

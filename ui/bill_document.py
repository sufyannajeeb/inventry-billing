"""Rendering + sharing helpers for a bill.

Turns a BillDTO into:
  * HTML -> rendered by QTextDocument for the on-screen preview, PDF and print
  * text -> caption shared through WhatsApp
and exposes actions: send the bill PDF on WhatsApp, open WhatsApp, download a
PDF, and print.
"""

import os
import re
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

from PySide6.QtCore import Qt, QMarginsF, QStandardPaths, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QImage, QPageLayout, QPageSize, QPainter,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from services.settings_service import get_template

load_dotenv()


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
         "Eighty", "Ninety"]


def money(value):
    return f"Rs. {value:,.2f}"


def _safe_color(value, default="#2563EB"):
    """Keep a bad colour setting from breaking the whole PDF."""
    color = QColor(value or "")
    return color.name() if color.isValid() else default


def _fallback_logo(template, size=240):
    """Draw a monogram when no logo image has been chosen."""
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    brand = _safe_color(template.get("accent_color"))
    painter.setBrush(QColor(brand))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, size, size, size * 0.22, size * 0.22)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", int(size * 0.34), QFont.Bold)
    painter.setFont(font)
    words = (template.get("shop_name") or "Shop").split()
    initials = "".join(word[0] for word in words[:2]).upper() or "S"
    painter.drawText(image.rect(), Qt.AlignCenter, initials)
    painter.end()
    return image


def load_logo_image(template=None):
    """Return the logo chosen in the template page, or a drawn monogram."""
    template = template or get_template()
    path = template.get("logo_path") or ""
    if path and Path(path).is_file():
        image = QImage(str(path))
        if not image.isNull():
            return image
    return _fallback_logo(template)


def _two_digits(number):
    if number < 20:
        return _ONES[number]
    return _TENS[number // 10] + (" " + _ONES[number % 10] if number % 10 else "")


def _three_digits(number):
    if number < 100:
        return _two_digits(number)
    rest = number % 100
    return _ONES[number // 100] + " Hundred" + (" " + _two_digits(rest) if rest else "")


def amount_in_words(amount):
    """Indian numbering: crore / lakh / thousand."""
    amount = float(amount or 0)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))

    if rupees == 0 and paise == 0:
        return "Zero Rupees Only"

    crore, rupees = divmod(rupees, 10_000_000)
    lakh, rupees = divmod(rupees, 100_000)
    thousand, hundreds = divmod(rupees, 1_000)

    parts = []
    if crore:
        parts.append(_three_digits(crore) + " Crore")
    if lakh:
        parts.append(_three_digits(lakh) + " Lakh")
    if thousand:
        parts.append(_three_digits(thousand) + " Thousand")
    if hundreds:
        parts.append(_three_digits(hundreds))

    text = (" ".join(parts).strip() + " Rupees") if parts else "Zero Rupees"
    if paise:
        text += f" and {_two_digits(paise)} Paise"
    return text + " Only"


def _format_date(value):
    if isinstance(value, datetime):
        return value.strftime("%d-%b-%Y %I:%M %p")
    return datetime.now().strftime("%d-%b-%Y %I:%M %p")


def normalize_phone(phone):
    """Return an international, digits-only number suitable for wa.me."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    digits = digits.lstrip("0")
    country_code = re.sub(r"\D", "", os.getenv("WHATSAPP_COUNTRY_CODE", ""))
    if country_code and not digits.startswith(country_code):
        digits = country_code + digits
    return digits


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def build_bill_html(bill, template=None):
    """Full invoice layout; every visible value comes from the template settings."""
    template = template or get_template()
    accent = _safe_color(template.get("accent_color"))
    tint = QColor(accent).lighter(93).name()

    created = bill.created_at or datetime.now()
    date_text = created.strftime("%d %b %Y")
    time_text = created.strftime("%I:%M %p")
    is_draft = bill.bill_number == "DRAFT"

    subtotal = sum(i.line_total for i in bill.items) or (bill.subtotal or 0)
    grand_total = bill.total if bill.total is not None else subtotal
    total_qty = sum(i.quantity for i in bill.items)

    rows = []
    for index, item in enumerate(bill.items, start=1):
        bg = "#FFFFFF" if index % 2 else "#F7F8FC"
        rows.append(f"""
        <tr bgcolor="{bg}">
          <td align="center" style="padding:7px;">{index}</td>
          <td style="padding:7px;">{escape(str(item.product_name))}</td>
          <td align="center" style="padding:7px;">{item.quantity}</td>
          <td align="right" style="padding:7px;">{money(item.price)}</td>
          <td align="right" style="padding:7px;"><b>{money(item.line_total)}</b></td>
        </tr>""")

    shop_lines = [escape(template.get("shop_address") or "")]
    contact = " | ".join(
        value for value in (template.get("shop_phone"), template.get("shop_email")) if value
    )
    if contact:
        shop_lines.append(escape(contact))
    if template.get("shop_gstin"):
        shop_lines.append("GSTIN: " + escape(template["shop_gstin"]))
    shop_lines = [line for line in shop_lines if line]

    tagline = escape(template.get("shop_tagline") or "")
    tagline_html = (
        f'<span style="font-size:9pt; color:#6B7280;"><i>{tagline}</i></span><br/>'
        if tagline else ""
    )
    upi = template.get("upi_id") or ""
    upi_html = (
        f'<p style="font-size:9pt; color:#4B5563;">Pay via UPI: <b>{escape(upi)}</b></p>'
        if upi else ""
    )
    draft_html = (
        '<p style="color:#B45309;"><b>DRAFT - not saved</b></p>' if is_draft else ""
    )

    terms = [line.strip() for line in (template.get("terms") or "").splitlines() if line.strip()]
    items_html = "".join(f"<li>{escape(line)}</li>" for line in terms)
    terms_html = f"""
      <tr>
        <td width="60%" valign="top">
          <span style="font-size:8pt; color:{accent};"><b>TERMS &amp; CONDITIONS</b></span>
          <ul style="font-size:8.5pt; color:#6B7280; margin-top:2px;">{items_html}</ul>
        </td>
        <td width="40%" align="center" valign="bottom">
          <br/><br/>
          ______________________<br/>
          <span style="font-size:9pt;">Authorised Signatory</span><br/>
          <span style="font-size:8pt; color:#6B7280;">for {escape(template.get("shop_name") or "")}</span>
        </td>
      </tr>"""

    footer = escape(template.get("footer_note") or "")

    return f"""
    <html><body style="font-family:'Segoe UI',Arial,sans-serif; font-size:10pt; color:#1F2937;">

    <table width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td width="14%" valign="middle"><img src="logo" width="70" height="70"/></td>
        <td width="52%" valign="middle">
          <span style="font-size:20pt; color:{accent};"><b>{escape(template.get("shop_name") or "")}</b></span><br/>
          {tagline_html}
          <span style="font-size:8.5pt; color:#4B5563;">{'<br/>'.join(shop_lines)}</span>
        </td>
        <td width="34%" align="right" valign="top">
          <span style="font-size:24pt; color:{accent};"><b>{escape(template.get("invoice_title") or "INVOICE")}</b></span><br/>
          <span style="font-size:9.5pt;">Bill No: <b>{escape(bill.bill_number)}</b></span><br/>
          <span style="font-size:9.5pt;">Date: {date_text}</span><br/>
          <span style="font-size:9.5pt;">Time: {time_text}</span>
          {draft_html}
        </td>
      </tr>
    </table>

    <table width="100%" cellspacing="0" cellpadding="0"><tr><td bgcolor="{accent}" height="4"></td></tr></table>
    <br/>

    <table width="100%" cellspacing="0" cellpadding="10">
      <tr bgcolor="{tint}">
        <td width="50%" valign="top">
          <span style="font-size:8pt; color:{accent};"><b>BILL TO</b></span><br/>
          <span style="font-size:12pt;"><b>{escape(bill.customer_name or "Walk-in Customer")}</b></span><br/>
          <span style="color:#4B5563;">Phone: {escape(bill.customer_phone or "-")}</span>
        </td>
        <td width="50%" align="right" valign="top">
          <span style="font-size:8pt; color:{accent};"><b>SUMMARY</b></span><br/>
          Items: <b>{len(bill.items)}</b> &nbsp; Total Qty: <b>{total_qty}</b><br/>
          Payment: <b>{'Pending' if is_draft else 'Paid / Received'}</b>
        </td>
      </tr>
    </table>
    <br/>

    <table width="100%" cellspacing="0" cellpadding="0" border="0">
      <tr bgcolor="{accent}" style="color:#FFFFFF;">
        <th width="7%" style="padding:8px; color:#FFFFFF;">#</th>
        <th width="43%" align="left" style="padding:8px; color:#FFFFFF;">Item Description</th>
        <th width="10%" style="padding:8px; color:#FFFFFF;">Qty</th>
        <th width="18%" align="right" style="padding:8px; color:#FFFFFF;">Rate</th>
        <th width="22%" align="right" style="padding:8px; color:#FFFFFF;">Amount</th>
      </tr>
      {''.join(rows)}
    </table>
    <table width="100%" cellspacing="0" cellpadding="0"><tr><td bgcolor="#D1D5DB" height="1"></td></tr></table>
    <br/>

    <table width="100%" cellspacing="0" cellpadding="0">
      <tr>
        <td width="55%" valign="top">
          <span style="font-size:8pt; color:{accent};"><b>AMOUNT IN WORDS</b></span><br/>
          <span style="font-size:9.5pt;"><i>{escape(amount_in_words(grand_total))}</i></span>
          <br/><br/>{upi_html}
        </td>
        <td width="45%" valign="top">
          <table width="100%" cellspacing="0" cellpadding="0">
            <tr>
              <td align="right" style="padding:4px;">Subtotal</td>
              <td align="right" style="padding:4px;">{money(subtotal)}</td>
            </tr>
            <tr bgcolor="{accent}">
              <td align="right" style="padding:9px; color:#FFFFFF;"><b>GRAND TOTAL</b></td>
              <td align="right" style="padding:9px; color:#FFFFFF; font-size:12pt;"><b>{money(grand_total)}</b></td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
    <br/><br/>

    <table width="100%" cellspacing="0" cellpadding="0">
      {terms_html}
    </table>
    <br/>
    <table width="100%" cellspacing="0" cellpadding="0"><tr><td bgcolor="#D1D5DB" height="1"></td></tr></table>
    <p align="center" style="font-size:10pt; color:{accent};"><b>{footer}</b></p>

    </body></html>
    """


def build_bill_text(bill, template=None):
    """Short caption used for the WhatsApp message that carries the PDF."""
    template = template or get_template()
    name = template.get("shop_name") or "My Store"
    return (
        f"*{name}*\n"
        f"Bill No: {bill.bill_number}\n"
        f"Customer: {bill.customer_name or 'Walk-in Customer'}\n"
        f"*Total: {money(bill.total)}*\n\n"
        "Please find the bill PDF attached."
    )


def _make_document(bill, template=None):
    template = template or get_template()
    document = QTextDocument()
    document.addResource(
        QTextDocument.ImageResource, QUrl("logo"), load_logo_image(template)
    )
    document.setDefaultFont(QFont("Segoe UI", 10))
    document.setHtml(build_bill_html(bill, template=template))
    return document


# --------------------------------------------------------------------------- #
# PDF / printing
# --------------------------------------------------------------------------- #
PAGE_MARGIN_MM = 14


def _make_printer(output_path=None):
    """An A4 printer with comfortable margins, shared by PDF and paper output."""
    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageMargins(
        QMarginsF(PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM, PAGE_MARGIN_MM),
        QPageLayout.Millimeter,
    )
    if output_path is not None:
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(output_path))
    return printer


def _print_document(document, printer):
    """Print a document with an opaque white page background.

    QTextDocument.print_() leaves the page margins transparent, which looks
    like a broken/black page in dark-themed PDF viewers, so every page is
    painted white first and the content is drawn on top.

    The transform is re-applied on every page because QPrinter.newPage()
    resets the painter's world transform.
    """
    layout = printer.pageLayout()
    full = layout.fullRect(QPageLayout.Point)
    paint = layout.paintRect(QPageLayout.Point)

    document.setPageSize(paint.size())
    page_height = paint.size().height()
    page_width = paint.size().width()
    offset_x = full.x() - paint.x()
    offset_y = full.y() - paint.y()
    scale = printer.resolution() / 72.0

    painter = QPainter(printer)
    try:
        for index in range(document.pageCount()):
            if index:
                printer.newPage()
            painter.save()
            painter.resetTransform()
            painter.scale(scale, scale)
            painter.fillRect(
                offset_x, offset_y, full.width(), full.height(), QColor("#FFFFFF"),
            )
            painter.translate(0, -index * page_height)
            painter.setClipRect(0, index * page_height, page_width, page_height)
            document.drawContents(painter)
            painter.restore()
    finally:
        painter.end()


def _render_pdf(bill, path, template=None):
    printer = _make_printer(path)
    _print_document(_make_document(bill, template=template), printer)
    return path


def export_bill_pdf(bill, directory=None, template=None):
    """Write the bill PDF to a folder (no dialog) and return the path."""
    if directory is None:
        base = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        base = base or os.path.expanduser("~")
        directory = Path(base) / "BillingSoftware" / "Bills"
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"Bill_{bill.bill_number}.pdf"
    return _render_pdf(bill, str(path), template=template)


def save_bill_pdf(bill, parent=None, template=None):
    """Ask the user where to save the PDF."""
    default_name = f"Bill_{bill.bill_number}.pdf"
    path, _ = QFileDialog.getSaveFileName(
        parent, "Save Bill as PDF", default_name, "PDF Files (*.pdf)"
    )
    if not path:
        return None
    if not path.lower().endswith(".pdf"):
        path += ".pdf"

    _render_pdf(bill, path, template=template)
    QMessageBox.information(parent, "Downloaded", f"Bill saved to:\n{path}")
    return path


def preview_bill_pdf(bill, parent=None, template=None):
    """Render the bill and open it in the default PDF viewer."""
    base = QStandardPaths.writableLocation(QStandardPaths.TempLocation)
    base = base or os.path.expanduser("~")
    path = export_bill_pdf(
        bill, directory=Path(base) / "BillingSoftware", template=template
    )
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path


def print_bill(bill, parent=None, template=None):
    printer = _make_printer()

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle("Print Bill")
    if dialog.exec() != QDialog.Accepted:
        return False

    _print_document(_make_document(bill, template=template), printer)
    return True


# --------------------------------------------------------------------------- #
# WhatsApp
# --------------------------------------------------------------------------- #
def _copy_file_to_clipboard(path):
    """Put a file on the clipboard so it can be pasted into a chat.

    Qt's QClipboard double-frees a Python-owned QMimeData on this build, so we
    write CF_HDROP to the native Windows clipboard directly.
    """
    path = os.path.abspath(str(path))

    if os.name != "nt":
        return False

    import ctypes
    from ctypes import wintypes

    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002

    class DROPFILES(ctypes.Structure):
        _fields_ = [
            ("pFiles", wintypes.DWORD),
            ("pt", wintypes.POINT),
            ("fNC", wintypes.BOOL),
            ("fWide", wintypes.BOOL),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.EmptyClipboard.argtypes = []
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.CloseClipboard.argtypes = []

    # Double-null-terminated UTF-16 file list.
    file_bytes = (path + "\0\0").encode("utf-16-le")

    dropfiles = DROPFILES()
    dropfiles.pFiles = ctypes.sizeof(DROPFILES)
    dropfiles.pt = wintypes.POINT(0, 0)
    dropfiles.fNC = False
    dropfiles.fWide = True

    total = ctypes.sizeof(DROPFILES) + len(file_bytes)
    handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, total)
    if not handle:
        return False

    pointer = kernel32.GlobalLock(handle)
    if not pointer:
        return False
    ctypes.memmove(pointer, ctypes.byref(dropfiles), ctypes.sizeof(DROPFILES))
    ctypes.memmove(pointer + ctypes.sizeof(DROPFILES), file_bytes, len(file_bytes))
    kernel32.GlobalUnlock(handle)

    if not user32.OpenClipboard(None):
        return False
    try:
        user32.EmptyClipboard()
        # Ownership of `handle` transfers to the clipboard on success.
        user32.SetClipboardData(CF_HDROP, handle)
    finally:
        user32.CloseClipboard()
    return True


def send_bill_pdf_to_whatsapp(bill, parent=None):
    """Export the bill PDF, copy it to the clipboard and open the chat.

    wa.me links cannot carry attachments, so we prepare everything: the PDF is
    generated and placed on the clipboard, then the customer's chat opens where
    the user just presses Ctrl+V and Send.
    """
    phone = normalize_phone(bill.customer_phone)
    if not phone:
        QMessageBox.warning(
            parent, "Phone Number Required",
            "Add the customer's phone number before sending on WhatsApp.",
        )
        return False

    try:
        path = export_bill_pdf(bill)
    except Exception as error:  # noqa: BLE001
        QMessageBox.critical(parent, "PDF Error", f"Could not create the PDF:\n{error}")
        return False

    _copy_file_to_clipboard(path)

    caption = quote(build_bill_text(bill))
    QDesktopServices.openUrl(QUrl(f"https://wa.me/{phone}?text={caption}"))

    QMessageBox.information(
        parent, "Bill PDF Ready",
        f"PDF saved to:\n{path}\n\n"
        "WhatsApp is opening the customer's chat.\n\n"
        "Press Ctrl+V in the chat to attach the PDF, then Send.",
    )
    return True


def open_whatsapp(parent=None):
    """Open the WhatsApp app, falling back to WhatsApp Web."""
    if QDesktopServices.openUrl(QUrl("whatsapp://")):
        return True
    if QDesktopServices.openUrl(QUrl("https://web.whatsapp.com")):
        return True
    QMessageBox.warning(parent, "WhatsApp", "Could not open WhatsApp on this system.")
    return False

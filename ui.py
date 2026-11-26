# ui.py  -  Billing software (Tkinter + SQLite), single-file replacement
import sqlite3, os, sys, tempfile, webbrowser, math, shutil, zlib
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime, date, timedelta
from urllib.parse import quote
from pathlib import Path

try:
    from PySide6.QtCore import QMarginsF, QRectF, Qt
    from PySide6.QtGui import (
        QBrush, QColor, QFont, QImage, QPageLayout, QPageSize, QPainter, QPen,
    )
    from PySide6.QtPrintSupport import QPrinter
    from PySide6.QtWidgets import QApplication
except ImportError:  # keep the app usable if Qt is not installed
    (QMarginsF, QRectF, Qt, QBrush, QColor, QFont, QImage, QPageLayout,
     QPageSize, QPainter, QPen, QPrinter, QApplication) = [None] * 13

if getattr(sys, "frozen", False):
    # Installed build: keep the database in a writable per-user folder so it
    # survives shortcuts, updates and read-only install locations.
    _data = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
                 or Path.home()) / "BillingSoftware"
    _data.mkdir(parents=True, exist_ok=True)
    DB_PATH = str(_data / "billing.db")
else:
    DB_PATH = "billing.db"  # source checkout / development

DATA_DIR = Path(DB_PATH).resolve().parent
LOGO_FILE = DATA_DIR / "assets" / "bill-logo.png"

# ---------- design tokens ----------
FONT, ICON_FONT = "Segoe UI", "Segoe UI Emoji"
SIDEBAR, SIDEBAR_HOVER, ACCENT, ACCENT_HOVER = "#0f172a", "#1e293b", "#2563eb", "#1d4ed8"
BG, CARD, TEXT, MUTED, BORDER = "#f1f5f9", "#ffffff", "#0f172a", "#64748b", "#e2e8f0"
GOOD, WARN, BAD = "#16a34a", "#d97706", "#dc2626"
SOFT, NAV_MUTED = "#f8fafc", "#94a3b8"
NAV_ACTIVE_BG, NAV_ACTIVE_BAR = "#172554", "#60a5fa"
TINT = {  # tone -> (strong colour, soft background)
    "blue": (ACCENT, "#dbeafe"), "violet": ("#7c3aed", "#ede9fe"),
    "green": (GOOD, "#dcfce7"), "amber": (WARN, "#fef3c7"), "red": (BAD, "#fee2e2"),
}
PALETTE = [ACCENT, "#7c3aed", GOOD, WARN, BAD, "#0891b2"]


# ---------- database ----------
def db(sql, args=()):
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.execute(sql, args)
    rows = cur.fetchall()
    con.commit()
    con.close()
    return rows


def db_insert(sql, args=()):
    """INSERT helper that returns the new row id from the same connection."""
    con = sqlite3.connect(DB_PATH)
    cur = con.execute(sql, args)
    new_id = cur.lastrowid
    con.commit()
    con.close()
    return new_id


def find_party(kind, name):
    """Find a party by name (case-insensitive), or return None."""
    text = str(name or "").strip()
    if not text:
        return None
    for row in db("SELECT * FROM parties WHERE kind=?", (kind,)):
        if str(row["name"] or "").strip().casefold() == text.casefold():
            return row
    return None


def resolve_party(kind, name, phone="", gstin="", address=""):
    """Use the existing party id for a typed name, creating the party if new."""
    text = str(name or "").strip()
    if not text or text.casefold() == "walk-in":
        return None
    existing = find_party(kind, text)
    if existing:
        # Fill in details the user typed only where the saved record is blank.
        updates, args = [], []
        for key, value in (("phone", phone), ("gstin", gstin), ("address", address)):
            if value and not str(existing[key] or "").strip():
                updates.append(f"{key}=?")
                args.append(str(value).strip())
        if updates:
            args.append(existing["id"])
            db(f"UPDATE parties SET {', '.join(updates)} WHERE id=?", tuple(args))
        return existing["id"]
    return db_insert(
        "INSERT INTO parties(kind,name,phone,address,gstin) VALUES(?,?,?,?,?)",
        (kind, text, str(phone or "").strip(), str(address or "").strip(),
         str(gstin or "").strip()))


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT, sku TEXT UNIQUE, name TEXT NOT NULL,
        unit TEXT DEFAULT 'pcs', price REAL DEFAULT 0, cost REAL DEFAULT 0,
        gst REAL DEFAULT 0, stock REAL DEFAULT 0, reorder REAL DEFAULT 5);
    CREATE TABLE IF NOT EXISTS parties(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, name TEXT NOT NULL,
        phone TEXT, address TEXT, gstin TEXT);
    CREATE TABLE IF NOT EXISTS sales(
        id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_no TEXT, date TEXT, party_id INTEGER,
        subtotal REAL, tax REAL, discount REAL, total REAL, paid REAL, mode TEXT);
    CREATE TABLE IF NOT EXISTS sale_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER, product_id INTEGER,
        name TEXT, qty REAL, price REAL, gst REAL, amount REAL);
    CREATE TABLE IF NOT EXISTS purchases(
        id INTEGER PRIMARY KEY AUTOINCREMENT, bill_no TEXT, date TEXT, party_id INTEGER,
        subtotal REAL, tax REAL, total REAL, paid REAL);
    CREATE TABLE IF NOT EXISTS purchase_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT, purchase_id INTEGER, product_id INTEGER,
        name TEXT, qty REAL, cost REAL, gst REAL, amount REAL);
    CREATE TABLE IF NOT EXISTS payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref_id INTEGER,
        amount REAL, mode TEXT, date TEXT, note TEXT);
    """)
    defaults = {"shop_name": "My Shop", "shop_tagline": "", "shop_address": "",
                "shop_phone": "", "shop_gstin": "", "upi_id": "", "logo_path": "",
                "footer_note": "Thank you for your business!", "accent_color": ACCENT,
                "prefix": "INV-", "currency": "₹"}
    for k, v in defaults.items():
        con.execute("INSERT OR IGNORE INTO settings VALUES(?,?)", (k, v))
    con.commit()
    con.close()


def setting(key, default=""):
    r = db("SELECT value FROM settings WHERE key=?", (key,))
    return r[0]["value"] if r else default


def money(x):
    return f"{float(x or 0):,.2f}"


def _pdf_rgb(value):
    """Convert #RRGGBB to PDF float components, or None when invalid."""
    text = str(value or "").lstrip("#")
    if len(text) != 6:
        return None
    try:
        parts = [int(text[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    except ValueError:
        return None
    return " ".join(f"{p:.3f}" for p in parts)


def load_logo_data():
    """Return (flate-compressed RGB bytes, width, height) for the logo."""
    if QImage is None:
        return None
    path = Path(setting("logo_path") or str(LOGO_FILE))
    if not path.is_file():
        return None
    image = QImage(str(path))
    if image.isNull():
        return None
    # PDF images have no alpha here: paint the logo on white first.
    canvas = QImage(image.size(), QImage.Format_RGB32)
    canvas.fill(QColor("white"))
    painter = QPainter(canvas)
    painter.drawImage(0, 0, image)
    painter.end()
    rgb = canvas.convertToFormat(QImage.Format_RGB888)
    raw = bytearray()
    for y in range(rgb.height()):
        raw += bytes(rgb.constScanLine(y)[:rgb.width() * 3])
    return zlib.compress(bytes(raw), 9), rgb.width(), rgb.height()


def short(x):
    """Compact number for chart axes (K / L / Cr)."""
    x = float(x or 0)
    for div, suf in ((1e7, "Cr"), (1e5, "L"), (1e3, "K")):
        if abs(x) >= div:
            return f"{x / div:.1f}".rstrip("0").rstrip(".") + suf
    return f"{x:g}"


def num(s, default=0.0):
    try:
        return float(str(s).strip() or default)
    except ValueError:
        return None


# ---------- invoice (keeps `from ui import bill_document` working) ----------
def _pdf_safe(text):
    """Built-in PDF fonts are Latin-1 only; transliterate common symbols."""
    s = str(text or "")
    for a, b in (("₹", "Rs."), ("–", "-"), ("—", "-"), ("’", "'"),
                 ("“", '"'), ("”", '"'), ("•", "-")):
        s = s.replace(a, b)
    return "".join(ch if 32 <= ord(ch) <= 126 else "?" for ch in s)


def _pdf_escape(text):
    return _pdf_safe(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_cell(text, width):
    return _pdf_safe(text)[:width].ljust(width)


def _write_pdf(pages, path, logo=None):
    """Minimal multi-page PDF writer with text, colour blocks and a logo image."""
    objs = {}
    objs[1] = "<< /Type /Catalog /Pages 2 0 R >>"
    page_ids = [3 + i * 2 for i in range(len(pages))]
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objs[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>"
    font_regular = 3 + len(pages) * 2
    font_bold = font_regular + 1
    image_id = font_bold + 1 if logo else None
    objs[font_regular] = "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    objs[font_bold] = "<< /Type /Font /Subtype /Type1 /BaseFont /Courier-Bold /Encoding /WinAnsiEncoding >>"
    if logo:
        data, width, height = logo
        objs[image_id] = (
            f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
            f"/Length {len(data)} >>\nstream\n".encode("latin-1")
            + data + b"\nendstream"
        )

    resources = f"<< /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >>"
    if logo:
        resources += f" /XObject << /ImLogo {image_id} 0 R >>"
    resources += " >>"

    for i, lines in enumerate(pages):
        pid = page_ids[i]
        parts = []
        image_cmd = None
        insert_after = 0
        if i == 0 and logo:
            _, width, height = logo
            scale = min(40 / width, 40 / height)
            w, h = width * scale, height * scale
            # Draw after the header band so the coloured bar cannot cover it.
            image_cmd = f"q {w:.2f} 0 0 {h:.2f} 44 796 cm /ImLogo Do Q"
            for pos, candidate in enumerate(lines):
                if len(candidate) == 2 and candidate[0] == "__raw__":
                    insert_after = pos
                    break
        for pos, item in enumerate(lines):
            if len(item) == 2 and item[0] == "__raw__":
                parts.append(item[1])
                if image_cmd and pos == insert_after:
                    parts.append(image_cmd)
                continue
            text, bold, size, y = item[:4]
            rgb = _pdf_rgb(item[4]) if len(item) > 4 and item[4] else None
            colour = f"{rgb} rg " if rgb else ""
            parts.append(
                f"BT {colour}/{'F2' if bold else 'F1'} {size} Tf 42 {y} Td "
                f"({_pdf_escape(text)}) Tj ET"
            )
            if image_cmd and pos == insert_after:
                parts.append(image_cmd)
        stream = "\n".join(parts).encode("latin-1", "replace")
        objs[pid] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                     f"/Resources {resources} /Contents {pid + 1} 0 R >>")
        objs[pid + 1] = (f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
                          + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objs):
        offsets[num] = len(out)
        body = objs[num]
        out += f"{num} 0 obj\n".encode("latin-1")
        out += body if isinstance(body, bytes) else body.encode("latin-1")
        out += b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("latin-1")
    for num in sorted(objs):
        out += f"{offsets[num]:010d} 00000 n \n".encode("latin-1")
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n").encode("latin-1")
    with open(path, "wb") as f:
        f.write(out)


_QT_APP = None


def _qt_app():
    """Qt is bundled for PDF rendering; create its app object only when needed."""
    global _QT_APP
    if QApplication is None:
        raise RuntimeError("Qt support is unavailable in this build.")
    if _QT_APP is None:
        _QT_APP = QApplication.instance() or QApplication([])
    return _QT_APP


# Canvas is A4 in units of 0.1 mm; font sizes use the same units.
W, H = 2100, 2970
MARGIN = 140
RIGHT = W - MARGIN
CONTENT_W = RIGHT - MARGIN
TEXT_COLOR, MUTED_COLOR = TEXT, MUTED
LINE_COLOR, ZEBRA_COLOR = BORDER, SOFT

_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
         "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
         "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_thousand(n):
    words = []
    if n >= 100:
        words.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else ""))
    elif n > 0:
        words.append(_ONES[n])
    return " ".join(words)


def amount_in_words(amount):
    """Indian numbering system (lakh / crore)."""
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))
    if paise == 100:
        rupees, paise = rupees + 1, 0
    if rupees == 0 and paise == 0:
        return "Zero Rupees Only"

    parts = []
    crore, rem = divmod(rupees, 10_000_000)
    lakh, rem = divmod(rem, 100_000)
    thousand, rem = divmod(rem, 1000)
    if crore:
        parts.append(_below_thousand(crore) + " Crore")
    if lakh:
        parts.append(_below_thousand(lakh) + " Lakh")
    if thousand:
        parts.append(_below_thousand(thousand) + " Thousand")
    if rem:
        parts.append(_below_thousand(rem))

    text = " ".join(parts) + " Rupees" if parts else ""
    if paise:
        text += (" and " if text else "") + _below_thousand(paise) + " Paise"
    return text + " Only"


def _flag_value(flag):
    value = getattr(flag, "value", None)
    return value if value is not None else int(flag)


def _flags(*items):
    value = 0
    for item in items:
        value |= _flag_value(item)
    return value


def _font(size, bold=False, italic=False):
    font = QFont()
    font.setFamilies(["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"])
    font.setPixelSize(size)
    font.setBold(bold)
    font.setItalic(italic)
    return font


def _pale(accent, ratio=0.88):
    """A pale tint of the accent colour, used for panel backgrounds."""
    text = str(accent or ACCENT).lstrip("#")
    try:
        r, g, b = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, IndexError):
        return "#EEF2FF"
    mix = lambda c: int(c * (1 - ratio) + 255 * ratio)
    return "#{:02X}{:02X}{:02X}".format(mix(r), mix(g), mix(b))


def _load_logo_image():
    """Return (image, source file) for the chosen logo or a drawn monogram."""
    if QImage is None:
        return None, None
    _qt_app()
    path = Path(setting("logo_path") or str(LOGO_FILE))
    if path.is_file():
        image = QImage(str(path))
        if not image.isNull():
            return image, str(path)

    size = 240
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QBrush(QColor(ACCENT)))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI")
    font.setPixelSize(int(size * 0.42))
    font.setBold(True)
    painter.setFont(font)
    initials = "".join(w[0] for w in (setting("shop_name") or "Shop").split()[:2]).upper() or "S"
    painter.drawText(image.rect(), int(Qt.AlignCenter.value), initials)
    painter.end()

    target = DATA_DIR / "assets" / "bill-monogram.png"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(target), "PNG")
        return image, str(target)
    except OSError:
        return image, None


def _number(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def bill_context(sale_id):
    """One shared data model for the Tk preview and the PDF renderer."""
    found = db("""SELECT s.*, p.name AS cname, p.phone AS cphone, p.gstin AS cgstin
                  FROM sales s LEFT JOIN parties p ON p.id=s.party_id WHERE s.id=?""",
               (sale_id,))
    if not found:
        raise ValueError("Sale not found")
    s = found[0]
    items = [dict(row) for row in db(
        "SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,))]

    accent = setting("accent_color", ACCENT) or ACCENT
    if QImage is not None and not QColor(accent).isValid():
        accent = ACCENT
    logo, logo_path = _load_logo_image()

    raw_date = str(s["date"] or "")
    try:
        date_text = datetime.strptime(raw_date, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        date_text = raw_date or "-"

    subtotal = _number(s["subtotal"])
    tax = _number(s["tax"])
    discount = _number(s["discount"])
    total = _number(s["total"])
    paid = _number(s["paid"])

    shop_lines = []
    if setting("shop_address"):
        shop_lines.append(str(setting("shop_address")))
    if setting("shop_phone"):
        shop_lines.append("Phone:  " + str(setting("shop_phone")))
    if setting("shop_gstin"):
        shop_lines.append("GSTIN:  " + str(setting("shop_gstin")))

    context = {
        "sale": s,
        "items": items,
        "invoice_no": s["invoice_no"] or "-",
        "date_text": date_text,
        "customer_name": s["cname"] or "Walk-in",
        "customer_phone": s["cphone"] or "-",
        "customer_gstin": s["cgstin"] or "-",
        "mode": s["mode"] or "-",
        "subtotal": subtotal,
        "tax": tax,
        "discount": discount,
        "total": total,
        "paid": paid,
        "balance": total - paid,
        "total_qty": sum(_number(i["qty"]) for i in items),
        "words": amount_in_words(total),
        "currency": setting("currency", "₹") or "₹",
        "footer": setting("footer_note") or "Thank you for your business!",
        "upi": setting("upi_id") or "",
        "terms": [line.strip() for line in (setting("terms") or "").splitlines() if line.strip()],
        "accent": accent,
        "tint": _pale(accent),
        "logo": logo,
        "logo_path": logo_path,
        "shop": {
            "name": setting("shop_name") or "My Shop",
            "tagline": setting("shop_tagline") or "",
            "lines": shop_lines,
        },
    }
    return context


def _ctx_money(context, value):
    return f"{context['currency']}{_number(value):,.2f}"


class _Invoice:
    """Advanced A4 invoice layout shared by PDF printing and the in-app preview."""

    def __init__(self, painter, printer, context):
        self.p = painter
        self.printer = printer
        self.b = context
        self.page = 1
        # (x, width, title, alignment)
        self.cols = [
            (MARGIN, 80, "#", "c"),
            (MARGIN + 80, 720, "Item Description", "l"),
            (MARGIN + 800, 170, "Qty", "c"),
            (MARGIN + 970, 270, "Rate", "r"),
            (MARGIN + 1240, 180, "GST%", "c"),
            (MARGIN + 1420, 400, "Amount", "r"),
        ]

    # ---- drawing primitives ------------------------------------------ #
    def text(self, x, y, w, h, value, size, color=TEXT_COLOR, bold=False,
             italic=False, align="l", wrap=False):
        h_align = {"l": Qt.AlignLeft, "c": Qt.AlignHCenter, "r": Qt.AlignRight}[align]
        flags = _flags(h_align, Qt.AlignVCenter if not wrap else Qt.AlignTop)
        if wrap:
            flags |= _flag_value(Qt.TextWordWrap)
        self.p.setFont(_font(size, bold, italic))
        self.p.setPen(QColor(color))
        self.p.drawText(QRectF(x, y, w, h), flags, str(value))

    def measure(self, w, value, size, bold=False):
        self.p.setFont(_font(size, bold))
        flags = _flags(Qt.AlignLeft, Qt.AlignTop) | _flag_value(Qt.TextWordWrap)
        return self.p.boundingRect(QRectF(0, 0, w, 10000), flags, str(value)).height()

    def rect(self, x, y, w, h, fill, radius=0):
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(QBrush(QColor(fill)))
        if radius:
            self.p.drawRoundedRect(QRectF(x, y, w, h), radius, radius)
        else:
            self.p.drawRect(QRectF(x, y, w, h))

    def line(self, y, color=LINE_COLOR, width=2):
        self.p.setPen(QPen(QColor(color), width))
        self.p.drawLine(MARGIN, int(y), RIGHT, int(y))

    # ---- sections ----------------------------------------------------- #
    def header(self):
        self.rect(0, 0, W, 45, self.b["accent"])

        logo = self.b["logo"]
        box = 170
        if logo is not None:
            scale = min(box / logo.width(), box / logo.height())
            lw, lh = logo.width() * scale, logo.height() * scale
            self.p.drawImage(QRectF(MARGIN, 110 + (box - lh) / 2, lw, lh), logo)

        x = MARGIN + box + 40
        self.text(x, 105, 900, 60, self.b["shop"]["name"], 50,
                  self.b["accent"], bold=True)
        if self.b["shop"]["tagline"]:
            self.text(x, 165, 900, 36, self.b["shop"]["tagline"], 24,
                      MUTED_COLOR, italic=True)
        y = 205
        for row in self.b["shop"]["lines"]:
            self.text(x, y, 900, 32, row, 22, "#4B5563")
            y += 32

        rx, rw = 1250, RIGHT - 1250
        self.text(rx, 100, rw, 80, "INVOICE", 64, self.b["accent"], bold=True, align="r")
        self.text(rx, 190, rw, 40, f"Bill No:  {self.b['invoice_no']}", 28,
                  bold=True, align="r")
        self.text(rx, 232, rw, 40, f"Date:  {self.b['date_text']}", 26, align="r")

        self.rect(MARGIN, 300, CONTENT_W, 5, self.b["accent"])
        return 345

    def mini_header(self):
        self.rect(0, 0, W, 45, self.b["accent"])
        self.text(MARGIN, 90, 1200, 50, self.b["shop"]["name"], 36,
                  self.b["accent"], bold=True)
        self.text(MARGIN, 90, CONTENT_W, 50,
                  f"Invoice {self.b['invoice_no']} (continued)", 26,
                  MUTED_COLOR, align="r")
        self.line(155, self.b["accent"], 3)
        return 190

    def bill_to(self, y):
        h = 200
        self.rect(MARGIN, y, CONTENT_W, h, self.b["tint"], radius=14)
        self.rect(MARGIN, y, 10, h, self.b["accent"])

        pad = 40
        self.text(MARGIN + pad, y + 18, 800, 30, "BILL TO", 22,
                  self.b["accent"], bold=True)
        self.text(MARGIN + pad, y + 55, 900, 50, self.b["customer_name"], 40, bold=True)
        self.text(MARGIN + pad, y + 112, 900, 36,
                  "Phone:  " + self.b["customer_phone"], 26, "#4B5563")

        rx = 1150
        rw = RIGHT - rx - pad
        self.text(rx, y + 18, rw, 30, "SUMMARY", 22, self.b["accent"], bold=True, align="r")
        self.text(rx, y + 55, rw, 40,
                  f"Items: {len(self.b['items'])}     Total Qty: {self.b['total_qty']:g}",
                  28, align="r")
        status = "Pending" if self.b["balance"] > 0 else "Paid / Received"
        self.text(rx, y + 108, rw, 40, "Payment:  " + status, 28, bold=True, align="r")
        return y + h + 45

    def table_header(self, y):
        self.rect(MARGIN, y, CONTENT_W, 70, self.b["accent"], radius=8)
        for x, w, title, align in self.cols:
            pad = 20 if align != "c" else 0
            self.text(x + pad, y, w - 2 * pad if align != "c" else w, 70,
                      title, 26, "#FFFFFF", bold=True, align=align)
        return y + 70

    def footer(self):
        self.line(2800, LINE_COLOR, 2)
        self.text(MARGIN, 2810, 1200, 40, self.b["shop"]["name"], 20, MUTED_COLOR)
        self.text(MARGIN, 2810, CONTENT_W, 40, f"Page {self.page}", 20,
                  MUTED_COLOR, align="r")

    def new_page(self):
        self.footer()
        self.printer.newPage()
        self.page += 1
        y = self.mini_header()
        return self.table_header(y)

    def items_table(self, y):
        y = self.table_header(y)
        for index, item in enumerate(self.b["items"], start=1):
            name_w = self.cols[1][1] - 40
            name_h = self.measure(name_w, item["name"], 28)
            row_h = max(68, name_h + 34)
            if y + row_h > 2740:
                y = self.new_page()
            if index % 2 == 0:
                self.rect(MARGIN, y, CONTENT_W, row_h, ZEBRA_COLOR)

            cx, cw, _, _ = self.cols[0]
            self.text(cx, y, cw, row_h, index, 26, align="c")

            cx, cw, _, _ = self.cols[1]
            self.text(cx + 20, y + (row_h - name_h) / 2, name_w, name_h + 4,
                      item["name"], 28, wrap=True)

            cx, cw, _, _ = self.cols[2]
            self.text(cx, y, cw, row_h, f"{_number(item['qty']):g}", 28, align="c")

            cx, cw, _, _ = self.cols[3]
            self.text(cx + 20, y, cw - 40, row_h, _ctx_money(self.b, item["price"]),
                      26, align="r")

            cx, cw, _, _ = self.cols[4]
            self.text(cx, y, cw, row_h, f"{_number(item['gst']):g}%", 26, align="c")

            cx, cw, _, _ = self.cols[5]
            self.text(cx + 20, y, cw - 40, row_h, _ctx_money(self.b, item["amount"]),
                      28, bold=True, align="r")
            y += row_h

        self.line(y, LINE_COLOR, 2)
        return y + 40

    def totals_and_notes(self, y):
        # Keep totals, terms and signature together on one page.
        if y + 720 > 2740:
            y = self.new_page() - 70 + 20

        left_w = 900
        self.text(MARGIN, y, left_w, 30, "AMOUNT IN WORDS", 22,
                  self.b["accent"], bold=True)
        words_h = self.measure(left_w, self.b["words"], 28)
        self.text(MARGIN, y + 40, left_w, words_h + 6, self.b["words"], 28,
                  italic=True, wrap=True)
        left_end = y + 40 + words_h + 20
        if self.b["upi"]:
            self.text(MARGIN, left_end, left_w, 40,
                      "Pay via UPI:  " + self.b["upi"], 26, bold=True)
            left_end += 50

        rx, rw = 1180, RIGHT - 1180
        ty = y
        for label, value in (("Subtotal", self.b["subtotal"]),
                             ("GST", self.b["tax"])):
            self.text(rx + 20, ty, rw - 320, 60, label, 28, "#4B5563", align="r")
            self.text(rx + rw - 300, ty, 280, 60, _ctx_money(self.b, value),
                      28, align="r")
            ty += 62
        self.text(rx + 20, ty, rw - 320, 60, "Discount", 28, "#4B5563", align="r")
        self.text(rx + rw - 300, ty, 280, 60,
                  "-" + _ctx_money(self.b, self.b["discount"]), 28, align="r")
        ty += 62
        self.rect(rx, ty, rw, 100, self.b["accent"], radius=12)
        self.text(rx + 25, ty, 330, 100, "GRAND TOTAL", 28, "#FFFFFF", bold=True)
        self.text(rx + 300, ty, rw - 325, 100, _ctx_money(self.b, self.b["total"]),
                  38, "#FFFFFF", bold=True, align="r")
        ty += 112
        for label, value in (("Paid", self.b["paid"]), ("Balance", self.b["balance"])):
            self.text(rx + 20, ty, rw - 320, 50, label, 26, "#4B5563", align="r")
            self.text(rx + rw - 300, ty, 280, 50, _ctx_money(self.b, value),
                      26, bold=True, align="r")
            ty += 52
        right_end = ty

        y = max(left_end, right_end) + 70
        if self.b["terms"]:
            self.text(MARGIN, y, 1050, 30, "TERMS & CONDITIONS", 22,
                      self.b["accent"], bold=True)
            ty = y + 42
            for term in self.b["terms"]:
                self.text(MARGIN, ty, 1050, 34, "-  " + term, 22, MUTED_COLOR)
                ty += 36

        sx = 1450
        sw = RIGHT - sx
        sy = y + 120
        self.p.setPen(QPen(QColor(TEXT_COLOR), 2))
        self.p.drawLine(sx, int(sy), RIGHT, int(sy))
        self.text(sx, sy + 8, sw, 34, "Authorised Signatory", 24, align="c")
        self.text(sx, sy + 42, sw, 30, "for " + self.b["shop"]["name"], 20,
                  MUTED_COLOR, align="c")

        self.text(MARGIN, 2690, CONTENT_W, 60, self.b["footer"], 32,
                  self.b["accent"], bold=True, align="c")

    def run(self):
        y = self.header()
        y = self.bill_to(y)
        y = self.items_table(y)
        self.totals_and_notes(y)
        self.footer()


def _render_invoice(context, printer):
    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Could not start the printer / PDF writer.")
    try:
        area = printer.pageLayout().paintRectPixels(printer.resolution())
        painter.setViewport(0, 0, area.width(), area.height())
        painter.setWindow(0, 0, W, H)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        _Invoice(painter, printer, context).run()
    finally:
        painter.end()


def render_bill_pdf(sale_id, path):
    """Render the advanced invoice into an A4 PDF file."""
    _qt_app()
    context = bill_context(sale_id)
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)
    _render_invoice(context, printer)
    return Path(path)


def bill_whatsapp_text(sale_id):
    context = bill_context(sale_id)
    cur = context["currency"]
    lines = [context["shop"]["name"],
             f"Invoice: {context['invoice_no']}   Date: {context['date_text']}",
             f"Customer: {context['customer_name']}",
             f"Phone: {context['customer_phone']}", "", "Items:"]
    for item in context["items"]:
        lines.append(f"- {item['name']}  {_number(item['qty']):g} x "
                     f"{cur}{_number(item['price']):,.2f} = "
                     f"{cur}{_number(item['amount']):,.2f}")
    lines += ["", f"Subtotal: {cur}{context['subtotal']:,.2f}",
              f"GST: {cur}{context['tax']:,.2f}",
              f"Discount: {cur}{context['discount']:,.2f}",
              f"*Total: {cur}{context['total']:,.2f}*",
              f"Paid: {cur}{context['paid']:,.2f}",
              f"Balance: {cur}{context['balance']:,.2f}",
              "", context["footer"]]
    return "\n".join(lines)


def bill_document(sale_id, open_in_browser=True):
    """Create the printable PDF invoice and optionally open it."""
    context = bill_context(sale_id)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in str(context["invoice_no"] or f"sale{sale_id}"))
    fd, path = tempfile.mkstemp(prefix=safe + "_", suffix=".pdf",
                                dir=tempfile.gettempdir())
    os.close(fd)
    render_bill_pdf(sale_id, path)
    if open_in_browser:
        if os.name == "nt":
            os.startfile(path)
        else:
            webbrowser.open("file://" + path)
    return path


# ---------- custom widgets ----------
class Btn(tk.Label):
    """Flat button with hover state. kind: primary | secondary | danger | success."""
    KINDS = {
        "primary": (ACCENT, ACCENT_HOVER, "white", ACCENT),
        "secondary": (CARD, "#f1f5f9", TEXT, "#cbd5e1"),
        "danger": ("#fef2f2", "#fee2e2", BAD, "#fecaca"),
        "success": (GOOD, "#15803d", "white", GOOD),
    }

    def __init__(self, parent, text, command=None, kind="secondary", **kw):
        bg, hover, fg, border = self.KINDS[kind]
        super().__init__(parent, text=text, bg=bg, fg=fg, font=(FONT, 10, "bold"),
                         padx=16, pady=8, cursor="hand2", highlightthickness=1,
                         highlightbackground=border, highlightcolor=border, **kw)
        self._bg, self._hover, self._cmd = bg, hover, command
        self.bind("<Enter>", lambda e: self.config(bg=self._hover))
        self.bind("<Leave>", lambda e: self.config(bg=self._bg))
        self.bind("<Button-1>", lambda e: self.invoke())

    def invoke(self):
        if self._cmd:
            self._cmd()


class BarChart(tk.Canvas):
    """Simple vertical bar chart. data = [(label, value), ...]; last bar is highlighted."""

    def __init__(self, parent, height=230):
        super().__init__(parent, bg=CARD, height=height, width=200, highlightthickness=0, bd=0)
        self.data = []
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, data):
        self.data = list(data)
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 80:
            return
        if not self.data or not any(v for _, v in self.data):
            self.create_text(w / 2, h / 2, text="No sales in this period yet",
                             fill=MUTED, font=(FONT, 10))
            return
        left, right, top, bottom = 52, 14, 18, 28
        peak = max(v for _, v in self.data) or 1
        exp = 10 ** math.floor(math.log10(peak))
        nice = next(m * exp for m in (1, 2, 2.5, 5, 10) if peak <= m * exp)
        plot_h = h - top - bottom
        for i in range(5):
            y = top + plot_h * i / 4
            self.create_line(left, y, w - right, y, fill=BORDER)
            self.create_text(left - 8, y, text=short(nice * (4 - i) / 4), anchor="e",
                             fill=MUTED, font=(FONT, 8))
        n = len(self.data)
        slot = (w - left - right) / n
        bw = min(48, slot * 0.58)
        for i, (lab, v) in enumerate(self.data):
            x0 = left + slot * i + (slot - bw) / 2
            y1 = top + plot_h * (1 - v / nice)
            color = ACCENT if i == n - 1 else "#93c5fd"
            if v > 0:
                self.create_rectangle(x0, y1, x0 + bw, top + plot_h, fill=color, outline=color)
                if n <= 12:
                    self.create_text(x0 + bw / 2, y1 - 8, text=short(v), fill=TEXT, font=(FONT, 8, "bold"))
            self.create_text(x0 + bw / 2, h - bottom + 14, text=lab, fill=MUTED, font=(FONT, 8))


class HBars(tk.Canvas):
    """Horizontal share bars. data = [(label, value), ...]."""

    def __init__(self, parent, height=230):
        super().__init__(parent, bg=CARD, height=height, width=200, highlightthickness=0, bd=0)
        self.data = []
        self.bind("<Configure>", lambda e: self.draw())

    def set(self, data):
        self.data = list(data)
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 80 or h < 60:
            return
        if not self.data:
            self.create_text(w / 2, h / 2, text="No sales this month", fill=MUTED, font=(FONT, 10))
            return
        total = sum(v for _, v in self.data) or 1
        rows = self.data[:6]
        step = min(40, (h - 10) / len(rows))
        for i, (lab, v) in enumerate(rows):
            y = 14 + i * step
            self.create_text(4, y, text=lab, anchor="w", fill=TEXT, font=(FONT, 10, "bold"))
            self.create_text(w - 4, y, text=f"{v / total * 100:.0f}%", anchor="e", fill=MUTED, font=(FONT, 9))
            self.create_rectangle(4, y + 12, w - 4, y + 19, fill=SOFT, outline=BORDER)
            self.create_rectangle(4, y + 12, 4 + (w - 8) * v / total, y + 19,
                                  fill=PALETTE[i % len(PALETTE)], outline="")


# ---------- UI helpers ----------
RIGHT_COLS = {"#", "Qty", "Rate", "GST%", "Amount", "ID", "Price", "Cost", "Stock",
              "Reorder", "Total", "Paid", "Due", "Qty Sold", "Revenue", "Bills"}


def draw_grid(tree):
    """Draw thin rules between rows and columns (Tk has no native gridlines)."""
    area = getattr(tree, "_grid_area", None)
    if area is None or not area.winfo_exists():
        return
    for line in tree._grid_lines:
        line.destroy()
    tree._grid_lines.clear()

    x = 0
    cols = list(tree["columns"])
    for c in cols[:-1]:
        x += int(tree.column(c, "width"))
        sep = ttk.Separator(area, orient="vertical", style="Grid.TSeparator")
        sep.place(x=x, y=0, width=1, relheight=1)
        tree._grid_lines.append(sep)

    for item in tree.get_children():
        box = tree.bbox(item, cols[0])
        if not box:
            continue
        sep = ttk.Separator(area, orient="horizontal", style="Grid.TSeparator")
        sep.place(x=0, y=box[1], relwidth=1, height=1)
        tree._grid_lines.append(sep)


def make_tree(parent, cols, widths, height=12):
    f = ttk.Frame(parent, style="TreeWrap.TFrame")
    area = ttk.Frame(f, style="TreeWrap.TFrame")
    area.pack(side="left", fill="both", expand=True)
    t = ttk.Treeview(area, columns=cols, show="headings", selectmode="browse", height=height)
    main_col = widths.index(max(widths))  # only this column absorbs extra width
    for i, (c, w) in enumerate(zip(cols, widths)):
        anchor = "e" if c in RIGHT_COLS else "w"
        t.heading(c, text=c, anchor=anchor)
        t.column(c, width=w, minwidth=max(40, w // 2), anchor=anchor, stretch=(i == main_col))
    sb = ttk.Scrollbar(f, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    t.tag_configure("odd", background=SOFT)
    t.tag_configure("low", foreground=BAD)
    t.tag_configure("warn", foreground=WARN)

    t._grid_area, t._grid_lines = area, []
    area.bind("<Configure>", lambda e: t.after_idle(draw_grid, t))
    t.after_idle(draw_grid, t)
    return f, t


def fill_tree(tree, rows, tags=None):
    """Zebra striping plus an optional per-row tag ('low' red, 'warn' amber)."""
    tree.delete(*tree.get_children())
    for i, r in enumerate(rows):
        t = []
        if i % 2:
            t.append("odd")
        if tags:
            x = tags(r)
            if x:
                t.append(x)
        tree.insert("", "end", values=r, tags=tuple(t))
    tree.after_idle(draw_grid, tree)


def scroll_area(parent):
    """Vertical scroll container; the inner frame stretches to fill the page height."""
    container = ttk.Frame(parent, style="Page.TFrame")
    canvas = tk.Canvas(container, bg=BG, highlightthickness=0, bd=0)
    bar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    inner = ttk.Frame(canvas, style="Page.TFrame")
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=bar.set)
    canvas.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")

    def fit(_=None):
        canvas.itemconfigure(window, width=canvas.winfo_width(),
                             height=max(canvas.winfo_height(), inner.winfo_reqheight()))
        canvas.configure(scrollregion=canvas.bbox("all"))

    inner.bind("<Configure>", fit)
    canvas.bind("<Configure>", fit)
    container.canvas = canvas
    return container, inner


def card(parent, title=None, padding=16, **pack_kw):
    """White surface with a hairline border and optional heading. Returns the inner frame."""
    outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    outer.pack(**(pack_kw or {"fill": "x"}))
    inner = ttk.Frame(outer, style="Card.TFrame", padding=padding)
    inner.pack(fill="both", expand=True)
    if title:
        ttk.Label(inner, text=title, style="CardTitle.TLabel").pack(anchor="w", pady=(0, 12))
    return inner


def form_frame(parent, weights):
    f = ttk.Frame(parent, style="Card.TFrame")
    f.pack(fill="x")
    for col, w in enumerate(weights):
        f.columnconfigure(col, weight=w)
    return f


def stat_card(parent, label, icon, tone):
    """KPI tile with coloured edge and icon badge. Returns (outer, value_label, caption_label)."""
    color, tint = TINT[tone]
    outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    inner = tk.Frame(outer, bg=CARD)
    inner.pack(fill="both", expand=True)
    tk.Frame(inner, bg=color, width=4).pack(side="left", fill="y")
    body = tk.Frame(inner, bg=CARD)
    body.pack(side="left", fill="both", expand=True, padx=(14, 12), pady=12)
    top = tk.Frame(body, bg=CARD)
    top.pack(fill="x")
    tk.Label(top, text=label, bg=CARD, fg=MUTED, font=(FONT, 10)).pack(side="left")
    tk.Label(top, text=icon, bg=tint, fg=color, font=(ICON_FONT, 11), width=3).pack(side="right")
    val = tk.Label(body, text="0", bg=CARD, fg=TEXT, font=(FONT, 17, "bold"))
    val.pack(anchor="w", pady=(8, 0))
    cap = tk.Label(body, text="", bg=CARD, fg=MUTED, font=(FONT, 9))
    cap.pack(anchor="w")
    return outer, val, cap


def field(parent, label, var, row, col=0, width=18, **kw):
    ttk.Label(parent, text=label, style="CardMuted.TLabel").grid(
        row=row, column=col, sticky="w", padx=(4, 10), pady=(6, 2))
    e = ttk.Entry(parent, textvariable=var, width=width, **kw)
    e.grid(row=row + 1, column=col, sticky="we", padx=(4, 10), pady=(0, 6))
    return e


def combo(parent, label, var, row, col=0, width=28, values=(), **kw):
    ttk.Label(parent, text=label, style="CardMuted.TLabel").grid(
        row=row, column=col, sticky="w", padx=(4, 10), pady=(6, 2))
    c = ttk.Combobox(parent, textvariable=var, width=width, values=values, **kw)
    c.grid(row=row + 1, column=col, sticky="we", padx=(4, 10), pady=(0, 6))
    return c


# ---------- In-app invoice preview ----------
class InvoicePreview(tk.Toplevel):
    """Shows a saved bill inside the app before Print / WhatsApp actions."""

    def __init__(self, parent, sale_id):
        super().__init__(parent)
        self.parent_page = parent
        self.app = getattr(parent, "app", None)
        found = db("""SELECT s.*, p.name AS cname, p.phone AS cphone, p.gstin AS cgstin
                      FROM sales s LEFT JOIN parties p ON p.id=s.party_id WHERE s.id=?""", (sale_id,))
        if not found:
            self.destroy()
            raise ValueError("Sale not found")
        self.sale = found[0]
        self.sale_id = sale_id
        self.items = db("SELECT * FROM sale_items WHERE sale_id=? ORDER BY id", (sale_id,))

        self.title(f"Invoice Preview - {self.sale['invoice_no'] or sale_id}")
        self.geometry("880x650")
        self.minsize(720, 520)
        self.configure(bg=BG)
        self.transient(parent.winfo_toplevel())
        self.lift()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Control-s>", lambda e: "break")
        self.bind("<MouseWheel>", self._wheel)
        self.bind("<Button-4>", self._wheel)
        self.bind("<Button-5>", self._wheel)

        bar = tk.Frame(self, bg=BG)
        bar.pack(side="bottom", fill="x", padx=24, pady=(0, 16))
        Btn(bar, "🖨  Print", self.print_bill, "primary").pack(side="left", padx=(0, 8))
        Btn(bar, "💬  Share on WhatsApp", self.whatsapp, "success").pack(side="left", padx=4)
        Btn(bar, "📄  Open PDF", self.open_pdf).pack(side="left", padx=4)
        tk.Label(bar, text="Preview first - nothing prints until you choose Print",
                 bg=BG, fg=MUTED, font=(FONT, 9)).pack(side="right", padx=8)
        Btn(bar, "✕  Close", self.destroy).pack(side="right", padx=(8, 0))

        holder, inner = scroll_area(self)
        holder.pack(fill="both", expand=True)
        self._canvas = holder.canvas
        paper = card(inner, padding=22, fill="both", expand=True, padx=24, pady=16)
        self._build_paper(paper)

    def _wheel(self, event):
        canvas = getattr(self, "_canvas", None)
        if canvas is not None and canvas.yview() != (0.0, 1.0):
            upwards = event.num == 4 or getattr(event, "delta", 0) > 0
            canvas.yview_scroll(-2 if upwards else 2, "units")
        return "break"  # keep the main app page from scrolling underneath

    def _build_paper(self, paper):
        """Tk mirror of the advanced A4 invoice layout used by the PDF."""
        b = bill_context(self.sale_id)
        accent, tint = b["accent"], b["tint"]

        # Top brand strip.
        tk.Frame(paper, bg=accent, height=6).pack(fill="x")

        # Header: shop identity on the left, invoice identity on the right.
        head = tk.Frame(paper, bg=CARD)
        head.pack(fill="x")
        left = tk.Frame(head, bg=CARD)
        left.pack(side="left", fill="x", expand=True, anchor="n")
        right = tk.Frame(head, bg=CARD)
        right.pack(side="right", anchor="ne", padx=(12, 0))

        if b["logo_path"]:
            try:
                photo = tk.PhotoImage(file=b["logo_path"])
                factor = max(1, int(max(photo.width() / 110, photo.height() / 60)))
                if factor > 1:
                    photo = photo.subsample(factor)
                self._logo_photo = photo
                tk.Label(left, image=photo, bg=CARD).pack(anchor="w", pady=(0, 4))
            except tk.TclError:
                pass
        tk.Label(left, text=b["shop"]["name"], bg=CARD, fg=accent,
                 font=(FONT, 18, "bold")).pack(anchor="w")
        if b["shop"]["tagline"]:
            tk.Label(left, text=b["shop"]["tagline"], bg=CARD, fg=MUTED,
                     font=(FONT, 9, "italic")).pack(anchor="w")
        for line in b["shop"]["lines"]:
            tk.Label(left, text=line, bg=CARD, fg="#4B5563",
                     font=(FONT, 9)).pack(anchor="w")

        tk.Label(right, text="INVOICE", bg=CARD, fg=accent,
                 font=(FONT, 22, "bold")).pack(anchor="e")
        tk.Label(right, text="Bill No:  " + b["invoice_no"], bg=CARD,
                 font=(FONT, 10, "bold")).pack(anchor="e")
        tk.Label(right, text="Date:  " + b["date_text"], bg=CARD,
                 font=(FONT, 10)).pack(anchor="e")

        tk.Frame(paper, bg=accent, height=3).pack(fill="x", pady=(10, 10))

        # BILL TO / SUMMARY panel.
        panel = tk.Frame(paper, bg=tint)
        panel.pack(fill="x", pady=(0, 10))
        tk.Frame(panel, bg=accent, width=4).pack(side="left", fill="y")
        pbody = tk.Frame(panel, bg=tint)
        pbody.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        pleft = tk.Frame(pbody, bg=tint)
        pleft.pack(side="left", fill="x", expand=True)
        pright = tk.Frame(pbody, bg=tint)
        pright.pack(side="right", anchor="ne")
        tk.Label(pleft, text="BILL TO", bg=tint, fg=accent,
                 font=(FONT, 9, "bold")).pack(anchor="w")
        tk.Label(pleft, text=b["customer_name"], bg=tint,
                 font=(FONT, 14, "bold")).pack(anchor="w")
        tk.Label(pleft, text="Phone:  " + b["customer_phone"], bg=tint,
                 fg="#4B5563", font=(FONT, 10)).pack(anchor="w")
        tk.Label(pright, text="SUMMARY", bg=tint, fg=accent,
                 font=(FONT, 9, "bold")).pack(anchor="e")
        tk.Label(pright, text=f"Items: {len(b['items'])}     Total Qty: {b['total_qty']:g}",
                 bg=tint, font=(FONT, 10)).pack(anchor="e")
        status = "Pending" if b["balance"] > 0 else "Paid / Received"
        tk.Label(pright, text="Payment:  " + status, bg=tint,
                 font=(FONT, 10, "bold")).pack(anchor="e")

        # Items table.
        f, tree = make_tree(paper, ("#", "Item", "Qty", "Rate", "GST%", "Amount"),
                            (45, 300, 70, 100, 70, 120), height=8)
        f.pack(fill="both", expand=True, pady=(0, 8))
        fill_tree(tree, [(i + 1, it["name"], f"{_number(it['qty']):g}",
                          _ctx_money(b, it["price"]), f"{_number(it['gst']):g}%",
                          _ctx_money(b, it["amount"]))
                         for i, it in enumerate(b["items"])])
        self.tree = tree
        tk.Frame(paper, bg=BORDER, height=1).pack(fill="x")

        # Words / terms on the left, totals on the right.
        bottom = tk.Frame(paper, bg=CARD)
        bottom.pack(fill="x", pady=(10, 0))
        bleft = tk.Frame(bottom, bg=CARD)
        bleft.pack(side="left", fill="x", expand=True)
        bright = tk.Frame(bottom, bg=CARD)
        bright.pack(side="right", anchor="ne")

        tk.Label(bleft, text="AMOUNT IN WORDS", bg=CARD, fg=accent,
                 font=(FONT, 9, "bold")).pack(anchor="w")
        tk.Label(bleft, text=b["words"], bg=CARD, fg=TEXT, font=(FONT, 10, "italic"),
                 wraplength=330, justify="left").pack(anchor="w")
        if b["upi"]:
            tk.Label(bleft, text="Pay via UPI:  " + b["upi"], bg=CARD, fg=accent,
                     font=(FONT, 9, "bold")).pack(anchor="w", pady=(6, 0))
        if b["terms"]:
            tk.Label(bleft, text="TERMS & CONDITIONS", bg=CARD, fg=accent,
                     font=(FONT, 9, "bold")).pack(anchor="w", pady=(8, 0))
            for term in b["terms"]:
                tk.Label(bleft, text="-  " + term, bg=CARD, fg=MUTED,
                         font=(FONT, 8), wraplength=330,
                         justify="left").pack(anchor="w")

        def total_row(row, label, value, strong=False, large=False):
            font = (FONT, 12 if large else 10, "bold" if strong or large else "normal")
            tk.Label(bright, text=label, bg=CARD, fg="#4B5563", font=font).grid(
                row=row, column=0, sticky="w", padx=(0, 24), pady=3)
            shown = ("-" + _ctx_money(b, -value)) if value < 0 else _ctx_money(b, value)
            tk.Label(bright, text=shown, bg=CARD,
                     fg=TEXT if not large else "#FFFFFF", font=font).grid(
                row=row, column=1, sticky="e", pady=3)

        total_row(0, "Subtotal", b["subtotal"])
        total_row(1, "GST", b["tax"])
        total_row(2, "Discount", -b["discount"])
        total_row(3, "Paid", b["paid"])
        total_row(4, "Balance", b["balance"], True)

        grand = tk.Frame(bright, bg=accent)
        grand.grid(row=5, column=0, columnspan=2, sticky="we", pady=(6, 0))
        tk.Label(grand, text="GRAND TOTAL", bg=accent, fg="#FFFFFF",
                 font=(FONT, 11, "bold")).pack(side="left", padx=10, pady=6)
        tk.Label(grand, text=_ctx_money(b, b["total"]), bg=accent,
                 fg="#FFFFFF", font=(FONT, 12, "bold")).pack(side="right", padx=10, pady=6)

        # Authorised signature and footer.
        tk.Label(paper, text="______________________\nAuthorised Signatory\nfor "
                 + b["shop"]["name"], bg=CARD, fg=MUTED, font=(FONT, 9),
                 justify="right").pack(anchor="e", pady=(14, 0))
        tk.Frame(paper, bg=BORDER, height=1).pack(fill="x", pady=(14, 0))
        foot = tk.Frame(paper, bg=CARD)
        foot.pack(fill="x")
        tk.Label(foot, text=b["shop"]["name"], bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side="left")
        tk.Label(foot, text="Page 1", bg=CARD, fg=MUTED,
                 font=(FONT, 8)).pack(side="right")
        tk.Label(paper, text=b["footer"], bg=CARD, fg=accent,
                 font=(FONT, 11, "bold")).pack(anchor="center", pady=(8, 0))


    def _notify(self, msg, kind="ok"):
        if self.app is not None:
            self.app.toast(msg, kind)
        else:
            messagebox.showinfo("Invoice", msg, parent=self)

    def _make_pdf(self):
        try:
            return bill_document(self.sale_id, False)
        except Exception as exc:
            messagebox.showerror("PDF error", f"Could not create the PDF invoice.\n{exc}", parent=self)
            return None

    def print_bill(self):
        path = self._make_pdf()
        if not path:
            return
        if os.name == "nt":
            try:
                os.startfile(path, "print")
                self._notify("Invoice sent to print")
            except OSError:
                os.startfile(path)
                self._notify("PDF opened - choose Print in your viewer", "info")
        else:
            webbrowser.open("file://" + path)
            self._notify("PDF opened - choose Print in your viewer", "info")

    def open_pdf(self):
        path = self._make_pdf()
        if not path:
            return
        if os.name == "nt":
            try:
                os.startfile(path)
            except OSError as exc:
                messagebox.showerror("PDF error", str(exc), parent=self)
        else:
            webbrowser.open("file://" + path)

    def whatsapp(self):
        s, cur = self.sale, setting("currency", "₹")
        lines = [setting("shop_name") or "My Shop",
                 f"Invoice: {s['invoice_no'] or '-'}   Date: {s['date'] or '-'}",
                 f"Customer: {s['cname'] or 'Walk-in'}"]
        if s["cphone"]:
            lines.append(f"Phone: {s['cphone']}")
        lines += ["", "Items:"]
        for it in self.items:
            lines.append(f"- {it['name']}  {it['qty']:g} x {cur}{money(it['price'])}"
                         f" = {cur}{money(it['amount'])}")
        lines += ["", f"Subtotal: {cur}{money(s['subtotal'])}",
                  f"GST: {cur}{money(s['tax'])}",
                  f"Discount: {cur}{money(s['discount'])}",
                  f"*Total: {cur}{money(s['total'])}*",
                  f"Paid: {cur}{money(s['paid'])}",
                  f"Balance: {cur}{money(s['total'] - s['paid'])}",
                  "", "Thank you for your business!"]
        text = "\n".join(str(x) for x in lines)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except tk.TclError:
            pass
        webbrowser.open("https://wa.me/?text=" + quote(text))
        self._notify("Bill copied - WhatsApp opened with the message ready")


class Page(ttk.Frame):
    title = ""
    subtitle = ""

    def __init__(self, parent, app):
        super().__init__(parent, style="Page.TFrame")
        self.app = app
        self.container, self.body = scroll_area(self)
        self.canvas = self.container.canvas
        self.container.pack(fill="both", expand=True, padx=28, pady=(22, 24))
        self.build()

    def toast(self, msg, kind="ok"):
        self.app.toast(msg, kind)

    def build(self): pass
    def refresh(self): pass


# ---------- Dashboard ----------
class Dashboard(Page):
    title = "Dashboard"
    subtitle = "Your store at a glance"

    def build(self):
        self.greet = ttk.Label(self.body, text="", style="Greet.TLabel")
        self.greet.pack(anchor="w")
        ttk.Label(self.body, text="Here is what is happening in your store today.",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 16))

        row = ttk.Frame(self.body, style="Page.TFrame")
        row.pack(fill="x")
        self.cards = {}
        specs = [("today", "Today's Sales", "💰", "blue"), ("month", "This Month", "📅", "violet"),
                 ("stock", "Stock Value", "📦", "green"), ("low", "Low Stock Items", "⚠️", "amber"),
                 ("due", "Customer Dues", "🧾", "red")]
        for i, (key, label, icon, tone) in enumerate(specs):
            row.columnconfigure(i, weight=1, uniform="stat")
            outer, val, cap = stat_card(row, label, icon, tone)
            outer.grid(row=0, column=i, sticky="nsew", padx=(0, 0 if i == len(specs) - 1 else 12))
            self.cards[key] = (val, cap)

        mid = ttk.Frame(self.body, style="Page.TFrame")
        mid.pack(fill="x", pady=(16, 0))
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=1)
        left = ttk.Frame(mid, style="Page.TFrame")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        right = ttk.Frame(mid, style="Page.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        c1 = card(left, "Sales — last 7 days", fill="both", expand=True)
        self.chart = BarChart(c1)
        self.chart.pack(fill="both", expand=True)
        c2 = card(right, "Payment modes — this month", fill="both", expand=True)
        self.modes = HBars(c2)
        self.modes.pack(fill="both", expand=True)

        ttk.Label(self.body, text="Recent Sales", style="Sub.TLabel").pack(anchor="w", pady=(20, 8))
        c = card(self.body, padding=12, fill="both", expand=True)
        f, self.recent = make_tree(c, ("Invoice", "Date", "Customer", "Total", "Paid"),
                                   (140, 110, 260, 120, 120), height=8)
        f.pack(fill="both", expand=True)

        ttk.Label(self.body, text="Low Stock Alerts", style="Sub.TLabel").pack(anchor="w", pady=(16, 8))
        c2 = card(self.body, padding=12, fill="x")
        f2, self.low = make_tree(c2, ("SKU", "Item", "Stock", "Reorder level"), (120, 300, 100, 130), height=5)
        f2.pack(fill="x")

    def refresh(self):
        today = date.today()
        iso, month = today.isoformat(), today.isoformat()[:7]
        g = lambda sql, a=(): (db(sql, a)[0][0] or 0)
        cur, set_ = setting("currency", "₹"), lambda k, v, c: (
            self.cards[k][0].config(text=v), self.cards[k][1].config(text=c))
        hour = datetime.now().hour
        hello = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
        self.greet.config(text=f"{hello}, welcome to {setting('shop_name', 'your shop')}")

        n_today = g("SELECT COUNT(*) FROM sales WHERE date=?", (iso,))
        n_month = g("SELECT COUNT(*) FROM sales WHERE date LIKE ?", (month + "%",))
        n_prod = g("SELECT COUNT(*) FROM products")
        n_due = g("SELECT COUNT(*) FROM sales WHERE total-paid>0.005")
        set_("today", f"{cur}{money(g('SELECT SUM(total) FROM sales WHERE date=?', (iso,)))}", f"{n_today:g} bills today")
        set_("month", f"{cur}{money(g('SELECT SUM(total) FROM sales WHERE date LIKE ?', (month + '%',)))}", f"{n_month:g} bills")
        set_("stock", f"{cur}{money(g('SELECT SUM(stock*cost) FROM products'))}", f"{n_prod:g} products")
        n_low = g("SELECT COUNT(*) FROM products WHERE stock<=reorder")
        set_("low", f"{n_low:g}", "need reorder" if n_low else "all stocked")
        set_("due", f"{cur}{money(g('SELECT SUM(total-paid) FROM sales'))}", f"{n_due:g} pending bills")

        start = (today - timedelta(days=6)).isoformat()
        by_day = {r["date"]: r["t"] for r in db(
            "SELECT date, SUM(total) t FROM sales WHERE date>=? GROUP BY date", (start,))}
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        self.chart.set([(d.strftime("%a %d"), by_day.get(d.isoformat(), 0)) for d in days])
        self.modes.set([(r["mode"] or "Other", r["t"]) for r in db(
            "SELECT mode, SUM(total) t FROM sales WHERE date LIKE ? GROUP BY mode ORDER BY t DESC",
            (month + "%",))])

        fill_tree(self.recent, [(r["invoice_no"], r["date"], r["cname"] or "Walk-in", money(r["total"]), money(r["paid"]))
                                for r in db("""SELECT s.*, p.name cname FROM sales s LEFT JOIN parties p
                                               ON p.id=s.party_id ORDER BY s.id DESC LIMIT 8""")])
        fill_tree(self.low, [(r["sku"] or "", r["name"], f"{r['stock']:g}", f"{r['reorder']:g}")
                             for r in db("SELECT * FROM products WHERE stock<=reorder ORDER BY stock LIMIT 10")],
                  tags=lambda r: "low" if float(r[2]) <= 0 else "warn")


# ---------- shared logic for Billing / Purchase ----------
class CartPage(Page):
    """Base for New Bill and Stock Purchase pages."""
    party_kind = "customer"
    price_col = "price"
    save_label = "Save"

    def build(self):
        self.cart, self.prod_map, self.party_map = [], {}, {}
        customer = self.party_kind == "customer"

        # --- bill / purchase details -------------------------------------
        c = card(self.body, "Bill details" if customer else "Purchase details", fill="x", pady=(0, 12))
        top = form_frame(c, (4, 2, 2, 2))
        self.party, self.ref, self.prod = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.c_phone, self.c_gstin = tk.StringVar(), tk.StringVar()
        self._selected_party_name = ""
        self.qty, self.rate, self.gst = tk.StringVar(value="1"), tk.StringVar(), tk.StringVar(value="0")

        self.party_cb = combo(top, "Customer" if customer else "Supplier", self.party, 0, 0, 36)
        field(top, "Notes / Reference", self.ref, 0, 1, 24)
        field(top, "Phone (optional)", self.c_phone, 2, 0, 24)
        field(top, "GSTIN (optional)", self.c_gstin, 2, 1, 24)
        self.party_cb.bind("<<ComboboxSelected>>", self.pick_customer)
        self.party_cb.bind("<KeyRelease>", self.filter_customers)
        self.party_cb.bind("<FocusOut>", self.commit_customer)
        self.prod_cb = combo(top, "Product (type to search)", self.prod, 4, 0, 36)
        self._suggestions_open = False
        self.prod_cb.bind("<<ComboboxSelected>>", self.pick_product)
        self.prod_cb.bind("<KeyRelease>", self.filter_products)
        self.prod_cb.bind("<Return>", self.product_enter)
        self.prod_cb.bind("<Escape>", lambda e: setattr(self, "_suggestions_open", False))
        self.prod_cb.bind("<FocusOut>", lambda e: setattr(self, "_suggestions_open", False))
        self.qty_entry = field(top, "Qty", self.qty, 4, 1, 10)
        rate_entry = field(top, "Rate", self.rate, 4, 2, 12)
        gst_entry = field(top, "GST %", self.gst, 4, 3, 10)
        for e in (self.qty_entry, rate_entry, gst_entry):
            e.bind("<Return>", lambda ev: self.add_item())
        Btn(top, "＋  Add item", self.add_item, "primary").grid(
            row=6, column=0, sticky="we", padx=(4, 10), pady=(6, 2))
        self.info = ttk.Label(
            top,
            text="New customers save automatically  ·  Enter in Qty / Rate / GST adds an item.",
            style="CardMuted.TLabel")
        self.info.grid(row=6, column=1, columnspan=3, sticky="w", padx=(4, 10))

        # --- cart + summary ----------------------------------------------
        mid = ttk.Frame(self.body, style="Page.TFrame")
        mid.pack(fill="both", expand=True)
        items = card(mid, "Items", padding=12, side="left", fill="both", expand=True)
        f, self.tree = make_tree(items, ("#", "Item", "Qty", "Rate", "GST%", "Amount"),
                                 (45, 320, 80, 100, 80, 120))
        f.pack(fill="both", expand=True)
        self.count_lbl = ttk.Label(items, text="0 items", style="CardMuted.TLabel")
        self.count_lbl.pack(anchor="w", pady=(8, 0))

        side = card(mid, "Summary", padding=16, side="right", fill="y", padx=(12, 0))
        self.lbl = {}
        rows = ["Subtotal", "GST"] + (["Discount"] if customer else [])
        for k in rows:
            r = ttk.Frame(side, style="Card.TFrame")
            r.pack(fill="x", pady=3)
            ttk.Label(r, text=k, style="CardMuted.TLabel").pack(side="left")
            self.lbl[k] = ttk.Label(r, text="0.00", style="Card.TLabel")
            self.lbl[k].pack(side="right")

        tp = tk.Frame(side, bg=ACCENT)
        tp.pack(fill="x", pady=(10, 6))
        tk.Label(tp, text="TOTAL PAYABLE", bg=ACCENT, fg="#bfdbfe", font=(FONT, 9, "bold")).pack(
            anchor="w", padx=14, pady=(10, 0))
        self.total_big = tk.Label(tp, text="0.00", bg=ACCENT, fg="white", font=(FONT, 22, "bold"))
        self.total_big.pack(anchor="w", padx=14, pady=(0, 10))

        br = ttk.Frame(side, style="Card.TFrame")
        br.pack(fill="x", pady=(2, 8))
        ttk.Label(br, text="Balance due", style="CardMuted.TLabel").pack(side="left")
        self.bal_lbl = ttk.Label(br, text="0.00", style="Card.TLabel")
        self.bal_lbl.pack(side="right")
        tk.Frame(side, bg=BORDER, height=1).pack(fill="x", pady=(0, 8))

        controls = ttk.Frame(side, style="Card.TFrame")
        controls.pack(fill="x")
        controls.columnconfigure(0, weight=1)
        self.discount, self.paid = tk.StringVar(value="0"), tk.StringVar(value="")
        self.mode = tk.StringVar(value="Cash")
        r = 0
        if customer:
            field(controls, "Discount", self.discount, r, 0, 26)
            r += 2
        field(controls, "Amount paid (blank = auto)", self.paid, r, 0, 26)
        r += 2
        combo(controls, "Payment mode", self.mode, r, 0, 26,
              ("Cash", "UPI", "Card", "Bank", "Credit"), state="readonly")
        r += 2
        for var in (self.discount, self.paid, self.mode):
            var.trace_add("write", lambda *a: self.totals())
        Btn(controls, self.save_label, self.save, "primary").grid(
            row=r, column=0, sticky="we", padx=(4, 10), pady=(10, 4))
        Btn(controls, "Remove selected", self.remove_item).grid(
            row=r + 1, column=0, sticky="we", padx=(4, 10), pady=2)
        Btn(controls, "Clear all", self.clear, "danger").grid(
            row=r + 2, column=0, sticky="we", padx=(4, 10), pady=2)

    def load_lists(self):
        self.prods = db("SELECT * FROM products ORDER BY name")
        self.prod_map = {f"{p['sku'] or p['id']} - {p['name']}": p for p in self.prods}
        self.prod_cb["values"] = list(self.prod_map)
        ps = db("SELECT * FROM parties WHERE kind=? ORDER BY name", (self.party_kind,))
        self.party_map = {p["name"]: p["id"] for p in ps}
        names = list(self.party_map)
        self.party_cb["values"] = (["Walk-in"] + names) if self.party_kind == "customer" else names
        if not self.party.get() and self.party_kind == "customer":
            self.party.set("Walk-in")

    def _customer_names(self):
        names = list(self.party_map)
        return (["Walk-in"] + names) if self.party_kind == "customer" else names

    def filter_customers(self, event=None):
        """Filter the customer dropdown as the user types a name."""
        if event is not None and event.keysym in {
                "Up", "Down", "Return", "Escape", "Tab", "Left", "Right",
                "Home", "End", "Prior", "Next", "Shift_L", "Shift_R",
                "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock"}:
            return
        typed = self.party.get().strip()
        if typed != self._selected_party_name:
            # A different name means the previous customer's details no longer apply.
            self.c_phone.set("")
            self.c_gstin.set("")
            self._selected_party_name = typed
        names = self._customer_names()
        if typed:
            names = [n for n in names if typed.lower() in n.lower()] or names
        self.party_cb["values"] = names

    def pick_customer(self, _=None):
        """Load saved phone/GSTIN when an existing customer is chosen."""
        self._selected_party_name = self.party.get().strip()
        row = find_party(self.party_kind, self.party.get())
        self.c_phone.set((row["phone"] or "") if row else "")
        self.c_gstin.set((row["gstin"] or "") if row else "")

    def commit_customer(self, _=None):
        """Auto-save a newly typed customer, or reuse the existing one's id."""
        if self.party_kind != "customer":
            return
        name = self.party.get().strip()
        self._selected_party_name = name
        if not name or name.casefold() == "walk-in":
            return
        pid = resolve_party("customer", name, self.c_phone.get(), self.c_gstin.get())
        self.party_map[name] = pid

    def refresh(self):
        self.load_lists()
        self.totals()

    def filter_products(self, event=None):
        if event is not None and event.keysym in {
                "Up", "Down", "Return", "Escape", "Tab", "Left", "Right",
                "Home", "End", "Prior", "Next", "Shift_L", "Shift_R",
                "Control_L", "Control_R", "Alt_L", "Alt_R", "Caps_Lock"}:
            return
        typed = self.prod.get().strip().lower()
        matches = [k for k in self.prod_map if typed in k.lower()]
        self.prod_cb["values"] = matches
        if matches and typed and not self._suggestions_open:
            self._suggestions_open = True
            self.prod_cb.after_idle(self.prod_cb.event_generate, "<Down>")

    def product_enter(self, _=None):
        if self.prod.get() in self.prod_map:
            self.pick_product()
            self.qty_entry.focus_set()
            self.qty_entry.select_range(0, "end")

    def pick_product(self, _=None):
        self._suggestions_open = False
        p = self.prod_map.get(self.prod.get())
        if p:
            self.rate.set(f"{p[self.price_col]:g}")
            self.gst.set(f"{p['gst']:g}")
            low = p["stock"] <= p["reorder"]
            self.info.config(text=f"In stock: {p['stock']:g} {p['unit']}" + ("  (low)" if low else ""),
                             foreground=BAD if low else MUTED)

    def check_stock(self, p, qty):
        return True

    def add_item(self):
        p = self.prod_map.get(self.prod.get())
        qty, rate, gst = num(self.qty.get()), num(self.rate.get()), num(self.gst.get())
        if not p or None in (qty, rate, gst) or qty <= 0:
            return self.toast("Select a product and enter a valid qty / rate / GST.", "warn")
        already = sum(i["qty"] for i in self.cart if i["pid"] == p["id"])
        if not self.check_stock(p, qty + already):
            return
        self.cart.append(dict(pid=p["id"], name=p["name"], qty=qty, rate=rate, gst=gst))
        self.prod.set("")
        self.prod_cb["values"] = list(self.prod_map)
        self._suggestions_open = False
        self.qty.set("1")
        self.rate.set("")
        self.info.config(text="Item added.", foreground=GOOD)
        self.redraw()
        self.prod_cb.focus_set()

    def remove_item(self):
        sel = self.tree.selection()
        if sel:
            del self.cart[self.tree.index(sel[0])]
            self.redraw()

    def clear(self):
        self.cart.clear()
        self.paid.set("")
        self.discount.set("0")
        self.redraw()

    def calc(self):
        sub = sum(i["qty"] * i["rate"] for i in self.cart)
        tax = sum(i["qty"] * i["rate"] * i["gst"] / 100 for i in self.cart)
        disc = num(self.discount.get()) or 0
        return sub, tax, disc, sub + tax - disc

    def paid_amount(self, total):
        s = self.paid.get().strip()
        if s:
            return num(s)
        return 0.0 if self.mode.get() == "Credit" else total

    def totals(self):
        if not hasattr(self, "bal_lbl"):
            return
        cur = setting("currency", "₹")
        sub, tax, disc, total = self.calc()
        self.lbl["Subtotal"].config(text=money(sub))
        self.lbl["GST"].config(text=money(tax))
        if "Discount" in self.lbl:
            self.lbl["Discount"].config(text="-" + money(disc))
        self.total_big.config(text=f"{cur}{money(total)}")
        paid = self.paid_amount(total)
        bal = max(total - (paid or 0), 0)
        self.bal_lbl.config(text=f"{cur}{money(bal)}", foreground=BAD if bal > 0.004 else GOOD)
        qty = sum(i["qty"] for i in self.cart)
        self.count_lbl.config(text=f"{len(self.cart)} items  ·  {qty:g} total qty")

    def redraw(self):
        fill_tree(self.tree, [(n + 1, i["name"], f"{i['qty']:g}", money(i["rate"]), f"{i['gst']:g}",
                               money(i["qty"] * i["rate"])) for n, i in enumerate(self.cart)])
        self.totals()

    def save(self):
        raise NotImplementedError


class BillingPage(CartPage):
    title = "New Bill"
    subtitle = "Create an invoice and reduce stock automatically"
    party_kind = "customer"
    price_col = "price"
    save_label = "💾  Save Bill"

    def check_stock(self, p, qty):
        if qty > p["stock"]:
            return messagebox.askyesno("Low stock", f"Only {p['stock']:g} in stock. Add anyway?")
        return True

    def save(self):
        if not self.cart:
            return self.toast("Add at least one item first.", "warn")
        sub, tax, disc, total = self.calc()
        paid = self.paid_amount(total)
        if paid is None:
            return self.toast("Invalid paid amount.", "warn")
        if paid > total + 0.004:
            return self.toast("Paid amount is more than the bill total.", "warn")
        pid = resolve_party("customer", self.party.get(),
                            self.c_phone.get(), self.c_gstin.get())
        con = sqlite3.connect(DB_PATH)
        cur = con.execute("INSERT INTO sales(date,party_id,subtotal,tax,discount,total,paid,mode) VALUES(?,?,?,?,?,?,?,?)",
                          (date.today().isoformat(), pid, sub, tax, disc, total, paid, self.mode.get()))
        sid = cur.lastrowid
        con.execute("UPDATE sales SET invoice_no=? WHERE id=?", (f"{setting('prefix', 'INV-')}{sid:05d}", sid))
        for i in self.cart:
            con.execute("INSERT INTO sale_items(sale_id,product_id,name,qty,price,gst,amount) VALUES(?,?,?,?,?,?,?)",
                        (sid, i["pid"], i["name"], i["qty"], i["rate"], i["gst"], i["qty"] * i["rate"]))
            con.execute("UPDATE products SET stock=stock-? WHERE id=?", (i["qty"], i["pid"]))
        con.commit()
        con.close()
        self.clear()
        self.load_lists()
        self.toast(f"Bill saved  ·  {money(total)}")
        InvoicePreview(self, sid)


class PurchasePage(CartPage):
    title = "Stock Purchase"
    subtitle = "Record supplier purchases and add to stock"
    party_kind = "supplier"
    price_col = "cost"
    save_label = "💾  Save Purchase"

    def save(self):
        if not self.cart:
            return self.toast("Add at least one item first.", "warn")
        if not self.party_map.get(self.party.get()):
            return self.toast("Select a supplier (add one under Suppliers).", "warn")
        sub, tax, _, total = self.calc()
        paid = self.paid_amount(total)
        if paid is None:
            return self.toast("Invalid paid amount.", "warn")
        if paid > total + 0.004:
            return self.toast("Paid amount is more than the purchase total.", "warn")
        con = sqlite3.connect(DB_PATH)
        cur = con.execute("INSERT INTO purchases(bill_no,date,party_id,subtotal,tax,total,paid) VALUES(?,?,?,?,?,?,?)",
                          (self.ref.get(), date.today().isoformat(), self.party_map[self.party.get()], sub, tax, total, paid))
        pid = cur.lastrowid
        for i in self.cart:
            con.execute("INSERT INTO purchase_items(purchase_id,product_id,name,qty,cost,gst,amount) VALUES(?,?,?,?,?,?,?)",
                        (pid, i["pid"], i["name"], i["qty"], i["rate"], i["gst"], i["qty"] * i["rate"]))
            con.execute("UPDATE products SET stock=stock+?, cost=? WHERE id=?", (i["qty"], i["rate"], i["pid"]))
        con.commit()
        con.close()
        self.clear()
        self.ref.set("")
        self.load_lists()
        self.toast(f"Purchase saved, stock updated  ·  {money(total)}")


# ---------- Products ----------
class ProductsPage(Page):
    title = "Products & Inventory"
    subtitle = "Manage items, prices and stock levels"
    FIELDS = [("sku", "SKU / Code"), ("name", "Name"), ("unit", "Unit"), ("price", "Sell Price"),
              ("cost", "Cost Price"), ("gst", "GST %"), ("stock", "Opening Stock"), ("reorder", "Reorder Level")]

    def build(self):
        c = card(self.body, fill="x", pady=(0, 12))
        self.form_title = ttk.Label(c, text="Add product", style="CardTitle.TLabel")
        self.form_title.pack(anchor="w", pady=(0, 6))
        form = form_frame(c, (2, 3, 2, 2))
        self.v = {k: tk.StringVar() for k, _ in self.FIELDS}
        for n, (k, label) in enumerate(self.FIELDS):
            field(form, label, self.v[k], (n // 4) * 2, n % 4, 22)
        bar = ttk.Frame(c, style="Card.TFrame")
        bar.pack(fill="x", padx=4, pady=(6, 0))
        Btn(bar, "Save / Update", self.save, "primary").pack(side="left", padx=(0, 6))
        Btn(bar, "Delete", self.delete, "danger").pack(side="left", padx=6)
        Btn(bar, "Clear", self.clear).pack(side="left", padx=6)
        self.search = tk.StringVar()
        ttk.Entry(bar, textvariable=self.search, width=28).pack(side="right")
        ttk.Label(bar, text="Search", style="CardMuted.TLabel").pack(side="right", padx=(30, 8))
        self.search.trace_add("write", lambda *a: self.refresh())

        listing = card(self.body, "Inventory", padding=12, fill="both", expand=True)
        f, self.tree = make_tree(listing, ("ID", "SKU", "Name", "Unit", "Price", "Cost", "GST%", "Stock", "Reorder", "Status"),
                                 (45, 110, 250, 70, 100, 100, 70, 90, 90, 110))
        f.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load)
        self.sel = None

    def refresh(self):
        t = f"%{self.search.get()}%"
        rows = db("SELECT * FROM products WHERE name LIKE ? OR sku LIKE ? ORDER BY name", (t, t))

        def status(r):
            return "Out of stock" if r["stock"] <= 0 else "Low stock" if r["stock"] <= r["reorder"] else "In stock"

        fill_tree(self.tree, [(r["id"], r["sku"] or "", r["name"], r["unit"], money(r["price"]), money(r["cost"]),
                               f"{r['gst']:g}", f"{r['stock']:g}", f"{r['reorder']:g}", status(r)) for r in rows],
                  tags=lambda r: {"Out of stock": "low", "Low stock": "warn"}.get(r[-1], ""))

    def load(self, _=None):
        s = self.tree.selection()
        if not s:
            return
        pid = self.tree.item(s[0])["values"][0]
        r = db("SELECT * FROM products WHERE id=?", (pid,))
        if not r:
            return
        r = r[0]
        self.sel = pid
        for k, _lbl in self.FIELDS:
            v = r[k]
            self.v[k].set("" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)))
        self.form_title.config(text=f"Edit product  ·  {r['name']}")

    def clear(self):
        self.sel = None
        for var in self.v.values():
            var.set("")
        self.form_title.config(text="Add product")

    def save(self):
        d = {k: v.get().strip() for k, v in self.v.items()}
        nums = {k: num(d[k]) for k in ("price", "cost", "gst", "stock", "reorder")}
        if not d["name"] or None in nums.values():
            return self.toast("Name is required and numeric fields must be numbers.", "warn")
        d["sku"] = d["sku"] or None
        try:
            if self.sel:
                db("UPDATE products SET sku=?,name=?,unit=?,price=?,cost=?,gst=?,stock=?,reorder=? WHERE id=?",
                   (d["sku"], d["name"], d["unit"] or "pcs", nums["price"], nums["cost"], nums["gst"],
                    nums["stock"], nums["reorder"] or 5, self.sel))
            else:
                db("INSERT INTO products(sku,name,unit,price,cost,gst,stock,reorder) VALUES(?,?,?,?,?,?,?,?)",
                   (d["sku"], d["name"], d["unit"] or "pcs", nums["price"], nums["cost"], nums["gst"],
                    nums["stock"], nums["reorder"] or 5))
        except sqlite3.IntegrityError:
            return self.toast("That SKU already exists.", "bad")
        self.clear()
        self.refresh()
        self.toast("Product saved.")

    def delete(self):
        if self.sel and messagebox.askyesno("Delete", "Delete this product?"):
            db("DELETE FROM products WHERE id=?", (self.sel,))
            self.clear()
            self.refresh()
            self.toast("Product deleted.", "info")


# ---------- Customers / Suppliers ----------
class PartiesPage(Page):
    kind = "customer"

    def build(self):
        noun = "customer" if self.kind == "customer" else "supplier"
        self.noun = noun
        c = card(self.body, fill="x", pady=(0, 12))
        self.form_title = ttk.Label(c, text=f"Add {noun}", style="CardTitle.TLabel")
        self.form_title.pack(anchor="w", pady=(0, 6))
        form = form_frame(c, (2, 2, 4, 2))
        self.v = {k: tk.StringVar() for k in ("name", "phone", "address", "gstin")}
        field(form, "Name", self.v["name"], 0, 0, 28)
        field(form, "Phone", self.v["phone"], 0, 1, 18)
        field(form, "Address", self.v["address"], 0, 2, 38)
        field(form, "GSTIN", self.v["gstin"], 0, 3, 20)
        bar = ttk.Frame(c, style="Card.TFrame")
        bar.pack(fill="x", padx=4, pady=(6, 0))
        Btn(bar, "Save / Update", self.save, "primary").pack(side="left", padx=(0, 6))
        Btn(bar, "Delete", self.delete, "danger").pack(side="left", padx=6)
        Btn(bar, "Clear", self.clear).pack(side="left", padx=6)

        listing = card(self.body, "Records", padding=12, fill="both", expand=True)
        f, self.tree = make_tree(listing, ("ID", "Name", "Phone", "Address", "GSTIN", "Balance Due"),
                                 (45, 240, 130, 300, 170, 130))
        f.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.load)
        self.sel = None

    def refresh(self):
        tbl = "sales" if self.kind == "customer" else "purchases"
        rows = db(f"""SELECT p.*, COALESCE((SELECT SUM(total-paid) FROM {tbl} WHERE party_id=p.id),0) due
                      FROM parties p WHERE kind=? ORDER BY name""", (self.kind,))
        fill_tree(self.tree, [(r["id"], r["name"], r["phone"] or "", r["address"] or "", r["gstin"] or "",
                               money(r["due"])) for r in rows],
                  tags=lambda r: "low" if float(r[5].replace(",", "")) > 0.005 else "")

    def load(self, _=None):
        s = self.tree.selection()
        if not s:
            return
        pid = self.tree.item(s[0])["values"][0]
        r = db("SELECT * FROM parties WHERE id=?", (pid,))
        if not r:
            return
        r = r[0]
        self.sel = pid
        for k in self.v:
            self.v[k].set(r[k] or "")
        self.form_title.config(text=f"Edit {self.noun}  ·  {r['name']}")

    def clear(self):
        self.sel = None
        for v in self.v.values():
            v.set("")
        self.form_title.config(text=f"Add {self.noun}")

    def save(self):
        d = {k: v.get().strip() for k, v in self.v.items()}
        if not d["name"]:
            return self.toast("Name is required.", "warn")
        if self.sel:
            db("UPDATE parties SET name=?,phone=?,address=?,gstin=? WHERE id=?",
               (d["name"], d["phone"], d["address"], d["gstin"], self.sel))
        else:
            db("INSERT INTO parties(kind,name,phone,address,gstin) VALUES(?,?,?,?,?)",
               (self.kind, d["name"], d["phone"], d["address"], d["gstin"]))
        self.clear()
        self.refresh()
        self.toast(f"{self.noun.capitalize()} saved.")

    def delete(self):
        if self.sel and messagebox.askyesno("Delete", "Delete this record?"):
            db("DELETE FROM parties WHERE id=?", (self.sel,))
            self.clear()
            self.refresh()
            self.toast("Record deleted.", "info")


class CustomersPage(PartiesPage):
    title, kind = "Customers", "customer"
    subtitle = "People you sell to, with outstanding balances"


class SuppliersPage(PartiesPage):
    title, kind = "Suppliers", "supplier"
    subtitle = "People you buy stock from, with amounts payable"


# ---------- Sales history ----------
class HistoryPage(Page):
    title = "Sales History"
    subtitle = "Search, reprint or delete past invoices"

    def build(self):
        c = card(self.body, "Find a sale", fill="x", pady=(0, 12))
        bar = ttk.Frame(c, style="Card.TFrame")
        bar.pack(fill="x")
        bar.columnconfigure(0, weight=1)
        self.search = tk.StringVar()
        ttk.Label(bar, text="Invoice / customer", style="CardMuted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(4, 10))
        ttk.Entry(bar, textvariable=self.search, width=36).grid(row=1, column=0, sticky="we", padx=(4, 10))
        Btn(bar, "Delete (restock)", self.delete, "danger").grid(row=1, column=1, padx=8)
        Btn(bar, "Open Invoice", self.open, "primary").grid(row=1, column=2, padx=(8, 4))
        self.search.trace_add("write", lambda *a: self.refresh())

        listing = card(self.body, "All sales", padding=12, fill="both", expand=True)
        f, self.tree = make_tree(listing, ("ID", "Invoice", "Date", "Customer", "Total", "Paid", "Due", "Mode", "Status"),
                                 (45, 140, 110, 240, 110, 110, 110, 80, 100))
        f.pack(fill="both", expand=True)
        self.summary = ttk.Label(listing, text="", style="CardMuted.TLabel")
        self.summary.pack(anchor="w", pady=(8, 0))

    def refresh(self):
        t = f"%{self.search.get()}%"
        rows = db("""SELECT s.*, p.name cname FROM sales s LEFT JOIN parties p ON p.id=s.party_id
                     WHERE s.invoice_no LIKE ? OR p.name LIKE ? ORDER BY s.id DESC""", (t, t))

        def status(r):
            due = r["total"] - r["paid"]
            return "Paid" if due <= 0.005 else "Partial" if r["paid"] > 0 else "Due"

        fill_tree(self.tree, [(r["id"], r["invoice_no"], r["date"], r["cname"] or "Walk-in", money(r["total"]),
                               money(r["paid"]), money(r["total"] - r["paid"]), r["mode"], status(r)) for r in rows],
                  tags=lambda r: {"Due": "low", "Partial": "warn"}.get(r[-1], ""))
        cur = setting("currency", "₹")
        self.summary.config(text=f"{len(rows)} sales  ·  total {cur}{money(sum(r['total'] for r in rows))}"
                                 f"  ·  outstanding {cur}{money(sum(r['total'] - r['paid'] for r in rows))}")

    def current(self):
        s = self.tree.selection()
        return self.tree.item(s[0])["values"][0] if s else None

    def open(self):
        sid = self.current()
        if sid:
            InvoicePreview(self, sid)
        else:
            self.toast("Select a sale first.", "warn")

    def delete(self):
        sid = self.current()
        if not sid:
            return self.toast("Select a sale first.", "warn")
        if messagebox.askyesno("Delete", "Delete this sale and return items to stock?"):
            for it in db("SELECT * FROM sale_items WHERE sale_id=?", (sid,)):
                db("UPDATE products SET stock=stock+? WHERE id=?", (it["qty"], it["product_id"]))
            db("DELETE FROM sale_items WHERE sale_id=?", (sid,))
            db("DELETE FROM sales WHERE id=?", (sid,))
            self.refresh()
            self.toast("Sale deleted and stock restored.", "info")


# ---------- Payments & Dues ----------
class DuesPage(Page):
    title = "Payments & Dues"
    subtitle = "Settle customer receivables and supplier stock payables"

    def _context(self):
        sale = self.kind.get().startswith("Customer")
        return sale, ("sales" if sale else "purchases"), ("invoice_no" if sale else "bill_no")

    def build(self):
        top = card(self.body, "Outstanding amounts", padding=16, fill="x", pady=(0, 12))
        form = form_frame(top, (3, 2, 2, 1))
        self.kind = tk.StringVar(value="Customers (money to receive)")
        self.party = tk.StringVar(value="All")
        self.amount = tk.StringVar()
        self.mode = tk.StringVar(value="Cash")
        self.kind_cb = combo(form, "Show", self.kind, 0, 0, 34,
                             ("Customers (money to receive)", "Suppliers (stock to pay)"))
        self.party_cb = combo(form, "Party", self.party, 0, 1, 26)
        field(form, "Amount / new due", self.amount, 0, 2, 16)
        combo(form, "Mode", self.mode, 0, 3, 14,
              ("Cash", "UPI", "Card", "Bank", "Credit"))

        self.summary = ttk.Label(form, text="", style="CardMuted.TLabel")
        self.summary.grid(row=2, column=0, columnspan=4, sticky="w", padx=4, pady=(2, 0))
        bar = ttk.Frame(form, style="Card.TFrame")
        bar.grid(row=3, column=0, columnspan=4, sticky="w", padx=4, pady=(10, 0))
        Btn(bar, "Record Payment", self.record, "primary").pack(side="left", padx=(0, 8))
        Btn(bar, "Set Due Manually", self.set_due).pack(side="left", padx=4)
        Btn(bar, "Payment History", self.history).pack(side="left", padx=4)

        self.kind.trace_add("write", lambda *a: self.refresh())
        self.party.trace_add("write", lambda *a: self.refresh())

        listing = card(self.body, "Bills with a balance", padding=12, fill="both", expand=True)
        f, self.tree = make_tree(
            listing, ("ID", "Type", "Party", "Bill / Invoice", "Date", "Total", "Paid", "Due"),
            (45, 90, 220, 150, 110, 110, 110, 110))
        f.pack(fill="both", expand=True)
        self.rows = []

    def refresh(self):
        if getattr(self, "_loading", False):
            return
        selected = self.current()
        self._loading = True
        sale, tbl, ref = self._context()
        names = db("SELECT name FROM parties WHERE kind=? ORDER BY name",
                   ("customer" if sale else "supplier",))
        values = ["All"] + (["Walk-in"] if sale else []) + [r["name"] for r in names]
        self.party_cb["values"] = values
        if self.party.get() not in values:
            self.party.set("All")
        self._loading = False

        where, args = ["x.total > x.paid + 0.004"], []
        if self.party.get() != "All":
            where.append("COALESCE(p.name,'Walk-in')=?")
            args.append(self.party.get())
        rows = db(f"""SELECT x.id, COALESCE(p.name,'Walk-in') AS party, x.{ref} AS ref,
                             x.date, x.total, x.paid
                      FROM {tbl} x LEFT JOIN parties p ON p.id=x.party_id
                      WHERE {' AND '.join(where)}
                      ORDER BY x.date DESC, x.id DESC""", args)
        self.rows = rows
        fill_tree(self.tree,
                  [(r["id"], "Sale" if sale else "Purchase", r["party"], r["ref"] or "-", r["date"],
                    money(r["total"]), money(r["paid"]), money(r["total"] - r["paid"])) for r in rows],
                  tags=lambda v: "warn")
        if selected is not None:
            for item in self.tree.get_children():
                if self.rows[self.tree.index(item)]["id"] == selected:
                    self.tree.selection_set(item)
                    self.tree.see(item)
                    break
        label = "Receivable" if sale else "Payable"
        total = sum(r["total"] - r["paid"] for r in rows)
        self.summary.config(text=f"{label}: {setting('currency', '₹')}{money(total)} across {len(rows)} bill(s)")

    def current(self):
        sel = self.tree.selection()
        if not sel:
            return None
        idx = self.tree.index(sel[0])
        return self.rows[idx]["id"] if idx < len(self.rows) else None

    def record(self):
        sid = self.current()
        if not sid:
            return self.toast("Select a bill with a balance first", "warn")
        amount = num(self.amount.get())
        if amount is None or amount <= 0:
            return self.toast("Enter a valid payment amount", "warn")
        sale, tbl, _ = self._context()
        r = db(f"SELECT total, paid FROM {tbl} WHERE id=?", (sid,))[0]
        due = r["total"] - r["paid"]
        if amount > due + 0.004 and not messagebox.askyesno(
                "Overpayment", f"Only {money(due)} is due. Apply {money(amount)} anyway?"):
            return
        db(f"UPDATE {tbl} SET paid=paid+? WHERE id=?", (amount, sid))
        if sale:
            db("UPDATE sales SET mode=? WHERE id=?", (self.mode.get(), sid))
        db("INSERT INTO payments(kind,ref_id,amount,mode,date,note) VALUES(?,?,?,?,?,?)",
           ("sale" if sale else "purchase", sid, amount, self.mode.get(),
            date.today().isoformat(), "Payment received" if sale else "Payment made"))
        self.amount.set("")
        self.refresh()
        self.toast(f"Payment of {money(amount)} recorded")

    def set_due(self):
        sid = self.current()
        if not sid:
            return self.toast("Select a bill to adjust first", "warn")
        if not self.amount.get().strip():
            return self.toast("Enter the new due amount (0 clears it)", "warn")
        new_due = num(self.amount.get())
        if new_due is None or new_due < 0:
            return self.toast("Enter a valid due amount (0 clears it)", "warn")
        sale, tbl, _ = self._context()
        r = db(f"SELECT total, paid FROM {tbl} WHERE id=?", (sid,))[0]
        new_paid = r["total"] - new_due
        if new_paid < 0:
            return self.toast("Due cannot be greater than the bill total", "warn")
        db(f"UPDATE {tbl} SET paid=? WHERE id=?", (new_paid, sid))
        db("INSERT INTO payments(kind,ref_id,amount,mode,date,note) VALUES(?,?,?,?,?,?)",
           ("sale" if sale else "purchase", sid, new_paid - r["paid"],
            "Adjustment", date.today().isoformat(), "Due adjusted manually"))
        self.amount.set("")
        self.refresh()
        self.toast(f"Due set to {money(new_due)}")

    def history(self):
        win = tk.Toplevel(self)
        win.title("Payment history")
        win.geometry("760x420")
        win.transient(self.winfo_toplevel())
        f, t = make_tree(win, ("Date", "Type", "Bill / Invoice", "Amount", "Mode", "Note"),
                         (110, 90, 150, 110, 100, 200), height=15)
        f.pack(fill="both", expand=True, padx=12, pady=12)
        rows = db("""SELECT p.*, COALESCE(s.invoice_no, pu.bill_no) AS ref FROM payments p
                     LEFT JOIN sales s ON p.kind='sale' AND s.id=p.ref_id
                     LEFT JOIN purchases pu ON p.kind='purchase' AND pu.id=p.ref_id
                     ORDER BY p.id DESC LIMIT 200""")
        fill_tree(t, [(r["date"], r["kind"], r["ref"] or "-", money(r["amount"]),
                       r["mode"], r["note"]) for r in rows])


# ---------- Reports ----------
class ReportsPage(Page):
    title = "Reports"
    subtitle = "Sales, GST, profit and trends for any date range"

    def build(self):
        c = card(self.body, "Date range", fill="x")
        bar = ttk.Frame(c, style="Card.TFrame")
        bar.pack(fill="x")
        self.d1 = tk.StringVar(value=date.today().replace(day=1).isoformat())
        self.d2 = tk.StringVar(value=date.today().isoformat())
        field(bar, "From (YYYY-MM-DD)", self.d1, 0, 0, 16)
        field(bar, "To (YYYY-MM-DD)", self.d2, 0, 1, 16)
        Btn(bar, "Generate report", self.refresh, "primary").grid(row=1, column=2, padx=(10, 4), pady=(0, 6))
        presets = ttk.Frame(c, style="Card.TFrame")
        presets.pack(fill="x", pady=(6, 0))
        for text, key in (("Today", "today"), ("This month", "month"), ("Last 30 days", "30"), ("This year", "year")):
            Btn(presets, text, lambda k=key: self.preset(k)).pack(side="left", padx=(4, 8))

        grid_f = ttk.Frame(self.body, style="Page.TFrame")
        grid_f.pack(fill="x", pady=(16, 0))
        self.vals = {}
        specs = [("Sales", "💰", "blue"), ("Purchases", "📦", "violet"), ("GST Collected", "🧾", "green"),
                 ("GST Paid", "🧮", "amber"), ("Net GST Payable", "🏛️", "red"), ("Gross Profit (est.)", "📈", "green"),
                 ("Receivable", "📥", "amber"), ("Payable", "📤", "red")]
        for n, (k, icon, tone) in enumerate(specs):
            grid_f.columnconfigure(n % 4, weight=1, uniform="rep")
            outer, val, cap = stat_card(grid_f, k, icon, tone)
            outer.grid(row=n // 4, column=n % 4, sticky="nsew", padx=(0, 0 if n % 4 == 3 else 12), pady=(0, 12))
            self.vals[k] = (val, cap)

        cc = card(self.body, "Sales trend", fill="x", pady=(4, 0))
        self.chart = BarChart(cc)
        self.chart.pack(fill="both", expand=True)

        row = ttk.Frame(self.body, style="Page.TFrame")
        row.pack(fill="both", expand=True, pady=(16, 0))
        row.columnconfigure(0, weight=1, uniform="tbl")
        row.columnconfigure(1, weight=1, uniform="tbl")
        row.rowconfigure(0, weight=1)
        cl = ttk.Frame(row, style="Page.TFrame")
        cl.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        cr = ttk.Frame(row, style="Page.TFrame")
        cr.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        a = card(cl, "Top selling items", padding=12, fill="both", expand=True)
        f, self.top = make_tree(a, ("Item", "Qty Sold", "Revenue"), (240, 90, 120), height=8)
        f.pack(fill="both", expand=True)
        b = card(cr, "Top customers", padding=12, fill="both", expand=True)
        f2, self.cust = make_tree(b, ("Customer", "Bills", "Revenue"), (240, 90, 120), height=8)
        f2.pack(fill="both", expand=True)

    def preset(self, key):
        t = date.today()
        a = {"today": t, "month": t.replace(day=1), "30": t - timedelta(days=29), "year": date(t.year, 1, 1)}[key]
        self.d1.set(a.isoformat())
        self.d2.set(t.isoformat())
        self.refresh()

    def refresh(self):
        try:
            d1, d2 = date.fromisoformat(self.d1.get().strip()), date.fromisoformat(self.d2.get().strip())
        except ValueError:
            return self.toast("Dates must be in YYYY-MM-DD format.", "warn")
        if d1 > d2:
            return self.toast("'From' date is after 'To' date.", "warn")
        a, b = d1.isoformat(), d2.isoformat()
        g = lambda sql: (db(sql, (a, b))[0][0] or 0)
        s = g("SELECT SUM(total) FROM sales WHERE date BETWEEN ? AND ?")
        n_s = g("SELECT COUNT(*) FROM sales WHERE date BETWEEN ? AND ?")
        p = g("SELECT SUM(total) FROM purchases WHERE date BETWEEN ? AND ?")
        n_p = g("SELECT COUNT(*) FROM purchases WHERE date BETWEEN ? AND ?")
        gc = g("SELECT SUM(tax) FROM sales WHERE date BETWEEN ? AND ?")
        gp = g("SELECT SUM(tax) FROM purchases WHERE date BETWEEN ? AND ?")
        rev = g("""SELECT SUM(si.amount) FROM sale_items si JOIN sales s ON s.id=si.sale_id
                   WHERE s.date BETWEEN ? AND ?""")
        profit = g("""SELECT SUM(si.amount - si.qty*COALESCE(pr.cost,0)) FROM sale_items si
                      JOIN sales s ON s.id=si.sale_id LEFT JOIN products pr ON pr.id=si.product_id
                      WHERE s.date BETWEEN ? AND ?""")
        recv = g("SELECT SUM(total-paid) FROM sales WHERE date BETWEEN ? AND ?")
        pay = g("SELECT SUM(total-paid) FROM purchases WHERE date BETWEEN ? AND ?")
        net = gc - gp
        data = {
            "Sales": (s, f"{n_s:g} bills"), "Purchases": (p, f"{n_p:g} bills"),
            "GST Collected": (gc, "output tax"), "GST Paid": (gp, "input tax"),
            "Net GST Payable": (net, "to pay" if net >= 0 else "credit available"),
            "Gross Profit (est.)": (profit, f"{(profit / rev * 100) if rev else 0:.1f}% margin"),
            "Receivable": (recv, "unpaid sales"), "Payable": (pay, "unpaid purchases"),
        }
        for k, (v, cap) in data.items():
            self.vals[k][0].config(text=money(v))
            self.vals[k][1].config(text=cap)

        if (d2 - d1).days <= 31:
            by_day = {r["date"]: r["t"] for r in db(
                "SELECT date, SUM(total) t FROM sales WHERE date BETWEEN ? AND ? GROUP BY date", (a, b))}
            days = [d1 + timedelta(days=i) for i in range((d2 - d1).days + 1)]
            fmt = "%d %b" if len(days) <= 12 else "%d"
            series = [(d.strftime(fmt), by_day.get(d.isoformat(), 0)) for d in days]
        else:
            rows = db("""SELECT substr(date,1,7) m, SUM(total) t FROM sales
                         WHERE date BETWEEN ? AND ? GROUP BY m ORDER BY m""", (a, b))
            series = [(datetime.strptime(r["m"], "%Y-%m").strftime("%b %y"), r["t"]) for r in rows]
        self.chart.set(series)

        rows = db("""SELECT si.name, SUM(si.qty) q, SUM(si.amount) a FROM sale_items si
                     JOIN sales s ON s.id=si.sale_id WHERE s.date BETWEEN ? AND ?
                     GROUP BY si.name ORDER BY a DESC LIMIT 10""", (a, b))
        fill_tree(self.top, [(r["name"], f"{r['q']:g}", money(r["a"])) for r in rows])
        rows = db("""SELECT COALESCE(p.name,'Walk-in') n, COUNT(*) c, SUM(s.total) a FROM sales s
                     LEFT JOIN parties p ON p.id=s.party_id WHERE s.date BETWEEN ? AND ?
                     GROUP BY n ORDER BY a DESC LIMIT 10""", (a, b))
        fill_tree(self.cust, [(r["n"], f"{r['c']:g}", money(r["a"])) for r in rows])


# ---------- Settings ----------
class SettingsPage(Page):
    title = "Settings"
    subtitle = "Shop details, invoice styling and data backup"
    KEYS = [("shop_name", "Shop Name"), ("shop_tagline", "Tagline"),
            ("shop_phone", "Phone"), ("shop_address", "Address"),
            ("shop_gstin", "GSTIN"), ("upi_id", "UPI ID"),
            ("footer_note", "Footer Note"), ("accent_color", "Accent Colour"),
            ("prefix", "Invoice Prefix"), ("currency", "Currency Symbol")]

    def build(self):
        c = card(self.body, "Shop details", padding=20, fill="x", pady=(0, 12))
        form = form_frame(c, (1, 1))
        self.v = {k: tk.StringVar() for k, _ in self.KEYS}
        self.v["logo_path"] = tk.StringVar()
        for n, (k, label) in enumerate(self.KEYS):
            field(form, label, self.v[k], (n // 2) * 2, n % 2, 40)

        logo_row = tk.Frame(c, bg=CARD)
        self.logo_preview = tk.Label(logo_row, text="No logo", bg=SOFT, fg=MUTED,
                                     font=(FONT, 8), width=12, height=3)
        self.logo_preview.pack(side="left", padx=(4, 10))
        Btn(logo_row, "Choose Logo…", self.choose_logo).pack(side="left")
        Btn(logo_row, "Clear Logo", self.clear_logo).pack(side="left", padx=(6, 0))
        tk.Label(logo_row, text="Shown on the bill PDF and invoice preview",
                 bg=CARD, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=(12, 0))
        logo_row.pack(anchor="w", padx=4, pady=(10, 0))

        Btn(c, "Save Settings", self.save, "primary").pack(anchor="w", padx=4, pady=(10, 0))

        d = card(self.body, "Data & backup", padding=20, fill="x")
        ttk.Label(d, text=f"All data is stored in {DB_PATH}. Save a copy regularly.",
                  style="CardMuted.TLabel").pack(anchor="w", pady=(0, 10))
        Btn(d, "Backup database…", self.backup).pack(anchor="w", padx=4)

    def refresh(self):
        for k, v in self.v.items():
            v.set(setting(k))
        self._show_logo()

    def _show_logo(self):
        self._logo_photo = None
        path = Path(self.v["logo_path"].get() or str(LOGO_FILE))
        if path.is_file():
            try:
                photo = tk.PhotoImage(file=str(path))
                factor = max(1, int(max(photo.width() / 160, photo.height() / 70)))
                if factor > 1:
                    photo = photo.subsample(factor)
                self._logo_photo = photo
                self.logo_preview.config(image=photo, text="")
                return
            except tk.TclError:
                pass
        self.logo_preview.config(image="", text="No logo")

    def choose_logo(self):
        if QImage is None:
            messagebox.showerror("Logo", "Image support is unavailable in this build.", parent=self)
            return
        path = filedialog.askopenfilename(
            parent=self, title="Choose bill logo",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")])
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            messagebox.showerror("Logo", "That file could not be opened as an image.", parent=self)
            return
        try:
            LOGO_FILE.parent.mkdir(parents=True, exist_ok=True)
            if not image.save(str(LOGO_FILE), "PNG"):
                raise OSError("Qt could not write the logo file.")
        except Exception as error:
            messagebox.showerror("Logo", f"Could not save the logo:\n{error}", parent=self)
            return
        self.v["logo_path"].set(str(LOGO_FILE))
        self._show_logo()
        self.toast("Logo chosen - click Save Settings to apply.")

    def clear_logo(self):
        self.v["logo_path"].set("")
        if LOGO_FILE.exists():
            try:
                LOGO_FILE.unlink()
            except OSError:
                pass
        self._show_logo()

    def save(self):
        for k, v in self.v.items():
            db("INSERT OR REPLACE INTO settings VALUES(?,?)", (k, v.get().strip()))
        self.app.set_brand()
        self.toast("Settings updated.")

    def backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".db", initialfile=f"billing-backup-{date.today().isoformat()}.db",
            filetypes=[("SQLite database", "*.db")])
        if path:
            shutil.copyfile(DB_PATH, path)
            self.toast("Backup saved.")


# ---------- App shell ----------
class App(tk.Tk):
    NAV = [
        ("OVERVIEW", [("📊", "Dashboard", Dashboard, "")]),
        ("TRANSACTIONS", [("🧾", "New Bill", BillingPage, "F1"), ("📦", "Stock Purchase", PurchasePage, "F2"),
                          ("📚", "Sales History", HistoryPage, "F3"),
                          ("💳", "Payments & Dues", DuesPage, "F4")]),
        ("MASTER DATA", [("🏷️", "Products", ProductsPage, ""), ("👥", "Customers", CustomersPage, ""),
                         ("🚚", "Suppliers", SuppliersPage, "")]),
        ("INSIGHTS", [("📈", "Reports", ReportsPage, ""), ("⚙️", "Settings", SettingsPage, "")]),
    ]

    def __init__(self):
        super().__init__()
        init_db()
        self.title("Billing Software")
        self.geometry("1340x800")
        self.minsize(1120, 680)
        self.configure(bg=BG)
        self.styles()
        self._toast, self.current = None, None

        # ----- sidebar -----
        side = tk.Frame(self, bg=SIDEBAR, width=240)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=SIDEBAR)
        brand.pack(fill="x")
        tk.Label(brand, text="◈", bg=SIDEBAR, fg=ACCENT, font=(FONT, 26, "bold")).pack(
            side="left", padx=(20, 10), pady=(20, 0))
        names = tk.Frame(brand, bg=SIDEBAR)
        names.pack(side="left", pady=(22, 0))
        self.brand_name = tk.Label(names, text="", bg=SIDEBAR, fg="white", font=(FONT, 14, "bold"), anchor="w")
        self.brand_name.pack(anchor="w")
        tk.Label(names, text="BILLING  /  POS", bg=SIDEBAR, fg=NAV_MUTED, font=(FONT, 9, "bold"),
                 anchor="w").pack(anchor="w")
        self.set_brand()
        tk.Frame(side, bg=SIDEBAR_HOVER, height=1).pack(fill="x", padx=20, pady=(18, 6))

        # ----- main area: header + page content -----
        main = tk.Frame(self, bg=BG)
        main.pack(side="right", fill="both", expand=True)
        header = tk.Frame(main, bg=CARD, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Frame(main, bg=BORDER, height=1).pack(fill="x")
        left = tk.Frame(header, bg=CARD)
        left.pack(side="left", padx=28, pady=12)
        self.h_title = tk.Label(left, bg=CARD, fg=TEXT, font=(FONT, 17, "bold"), anchor="w")
        self.h_title.pack(anchor="w")
        self.h_sub = tk.Label(left, bg=CARD, fg=MUTED, font=(FONT, 9), anchor="w")
        self.h_sub.pack(anchor="w")
        Btn(header, "＋  New Bill   F1", lambda: self.show("New Bill"), "primary").pack(side="right", padx=(8, 28))
        Btn(header, "Stock Purchase   F2", lambda: self.show("Stock Purchase")).pack(side="right", padx=4)
        self.clock = tk.Label(header, bg=CARD, fg=MUTED, font=(FONT, 10))
        self.clock.pack(side="right", padx=18)

        self.content = ttk.Frame(main, style="Page.TFrame")
        self.content.pack(fill="both", expand=True)

        # ----- navigation -----
        self.pages, self.nav = {}, {}
        for group, items in self.NAV:
            tk.Label(side, text=group, bg=SIDEBAR, fg=NAV_MUTED, font=(FONT, 8, "bold"),
                     anchor="w").pack(fill="x", padx=24, pady=(12, 4))
            for icon, label, cls, key in items:
                self.add_nav(side, icon, label, key)
                self.pages[label] = cls(self.content, self)

        foot = tk.Frame(side, bg=SIDEBAR)
        foot.pack(side="bottom", fill="x", pady=(0, 16))
        tk.Label(foot, text="Ctrl+S  Save current form", bg=SIDEBAR, fg=NAV_MUTED,
                 font=(FONT, 9), anchor="w").pack(anchor="w", padx=24)

        self.bind("<F1>", lambda e: self.show("New Bill"))
        self.bind("<F2>", lambda e: self.show("Stock Purchase"))
        self.bind("<F3>", lambda e: self.show("Sales History"))
        self.bind("<F4>", lambda e: self.show("Payments & Dues"))
        self.bind("<Control-s>", lambda e: getattr(self.current, "save", lambda: None)())
        self.bind_all("<MouseWheel>", self.wheel)
        self.bind_all("<Button-4>", self.wheel)
        self.bind_all("<Button-5>", self.wheel)
        self.tick()
        self.show("Dashboard")

    # --- navigation helpers ---
    def add_nav(self, side, icon, label, key):
        row = tk.Frame(side, bg=SIDEBAR, cursor="hand2")
        row.pack(fill="x")
        ind = tk.Frame(row, bg=SIDEBAR, width=4)
        ind.pack(side="left", fill="y")
        ic = tk.Label(row, text=icon, bg=SIDEBAR, fg="#cbd5e1", font=(ICON_FONT, 12), width=2)
        ic.pack(side="left", padx=(16, 4), pady=9)
        lab = tk.Label(row, text=label, bg=SIDEBAR, fg="#cbd5e1", anchor="w", font=(FONT, 11))
        lab.pack(side="left", fill="x", expand=True)
        kb = tk.Label(row, text=key, bg=SIDEBAR, fg=NAV_MUTED, font=(FONT, 8))
        kb.pack(side="right", padx=14)
        self.nav[label] = dict(row=row, ind=ind, parts=[ic, lab, kb], active=False)
        for w in (row, ic, lab, kb):
            w.bind("<Button-1>", lambda e, l=label: self.show(l))
            w.bind("<Enter>", lambda e, l=label: self.hover(l, True))
            w.bind("<Leave>", lambda e, l=label: self.hover(l, False))

    def paint(self, label, mode):
        n = self.nav[label]
        bg, fg, bar = {"idle": (SIDEBAR, "#cbd5e1", SIDEBAR), "hover": (SIDEBAR_HOVER, "white", SIDEBAR_HOVER),
                       "active": (NAV_ACTIVE_BG, "white", NAV_ACTIVE_BAR)}[mode]
        n["row"].config(bg=bg)
        n["ind"].config(bg=bar)
        for i, w in enumerate(n["parts"]):
            w.config(bg=bg)
            if i < 2:
                w.config(fg=fg)

    def hover(self, label, inside):
        if not self.nav[label]["active"]:
            self.paint(label, "hover" if inside else "idle")

    def show(self, label):
        for key, n in self.nav.items():
            n["active"] = key == label
            self.paint(key, "active" if n["active"] else "idle")
        for p in self.pages.values():
            p.pack_forget()
        page = self.pages[label]
        page.pack(fill="both", expand=True)
        self.current = page
        self.h_title.config(text=page.title)
        self.h_sub.config(text=page.subtitle)
        page.refresh()

    def set_brand(self):
        self.brand_name.config(text=setting("shop_name", "My Shop")[:18])

    def tick(self):
        self.clock.config(text=datetime.now().strftime("%a, %d %b %Y   •   %I:%M %p"))
        self.after(20000, self.tick)

    def wheel(self, e):
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            return
        if w is None or w.winfo_class() in ("Treeview", "TCombobox", "Listbox") or self.current is None:
            return
        canvas = self.current.canvas
        if canvas.yview() == (0.0, 1.0):
            return
        up = e.num == 4 or getattr(e, "delta", 0) > 0
        canvas.yview_scroll(-2 if up else 2, "units")

    # --- toast notifications ---
    def toast(self, msg, kind="ok", ms=2600):
        colors = {"ok": GOOD, "warn": WARN, "bad": BAD, "info": ACCENT}
        icons = {"ok": "✔", "warn": "!", "bad": "✖", "info": "i"}
        if self._toast is not None and self._toast.winfo_exists():
            self._toast.destroy()
        t = tk.Label(self, text=f"  {icons[kind]}   {msg}  ", bg=colors[kind], fg="white",
                     font=(FONT, 11, "bold"), padx=14, pady=11)
        t.place(relx=1.0, rely=1.0, x=-28, y=-28, anchor="se")
        t.lift()
        self._toast = t
        self.after(ms, lambda: t.winfo_exists() and t.destroy())

    # --- ttk styling ---
    def styles(self):
        self.option_add("*TCombobox*Listbox.font", (FONT, 10))
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "white")
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", font=(FONT, 10), foreground=TEXT, background=BG)
        s.configure("TFrame", background=BG)
        s.configure("Page.TFrame", background=BG)
        s.configure("TreeWrap.TFrame", background=CARD)
        s.configure("Grid.TSeparator", background=BORDER)
        s.configure("Card.TFrame", background=CARD)

        s.configure("Greet.TLabel", background=BG, foreground=TEXT, font=(FONT, 16, "bold"))
        s.configure("Sub.TLabel", background=BG, foreground=TEXT, font=(FONT, 12, "bold"))
        s.configure("Muted.TLabel", background=BG, foreground=MUTED, font=(FONT, 10))
        s.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=(FONT, 12, "bold"))
        s.configure("CardMuted.TLabel", background=CARD, foreground=MUTED, font=(FONT, 10))
        s.configure("Card.TLabel", background=CARD, foreground=TEXT, font=(FONT, 11, "bold"))
        s.configure("TLabel", background=BG)

        field_look = dict(fieldbackground="#ffffff", bordercolor="#cbd5e1",
                          lightcolor="#cbd5e1", darkcolor="#cbd5e1", padding=7)
        s.configure("TEntry", font=(FONT, 10), insertcolor=TEXT, **field_look)
        s.configure("TCombobox", font=(FONT, 10), background=SOFT, arrowcolor=MUTED, arrowsize=14, **field_look)
        focus = [("focus", ACCENT)]
        for st in ("TEntry", "TCombobox"):
            s.map(st, bordercolor=focus, lightcolor=focus, darkcolor=focus)
        s.map("TCombobox", fieldbackground=[("readonly", "#ffffff")], background=[("active", "#e2e8f0")])

        s.configure("TScrollbar", background="#cbd5e1", troughcolor=SOFT, bordercolor=SOFT,
                    arrowcolor=MUTED, relief="flat")
        s.map("TScrollbar", background=[("active", NAV_MUTED)])

        s.configure("Treeview", rowheight=34, font=(FONT, 10), background=CARD,
                    fieldbackground=CARD, bordercolor=BORDER, relief="solid", borderwidth=1)
        s.configure("Treeview.Heading", font=(FONT, 10, "bold"), background=SOFT,
                    foreground=MUTED, padding=(10, 8), relief="flat")
        s.map("Treeview.Heading", background=[("active", "#e2e8f0")])
        s.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", TEXT)])


if __name__ == "__main__":
    App().mainloop()
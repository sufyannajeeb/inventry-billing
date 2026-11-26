"""Persistence for the customisable bill template.

Values live in the `settings` table as key/value pairs. Environment variables
seed the defaults so an existing .env keeps working, but once the user saves the
template page the database wins.
"""

import os

from dotenv import load_dotenv

from database.database import get_session
from database.models import Setting

load_dotenv()

DEFAULTS = {
    "shop_name": os.getenv("SHOP_NAME", "My Store"),
    "shop_tagline": os.getenv("SHOP_TAGLINE", "Quality products, trusted service"),
    "shop_address": os.getenv("SHOP_ADDRESS", ""),
    "shop_phone": os.getenv("SHOP_PHONE", ""),
    "shop_email": os.getenv("SHOP_EMAIL", ""),
    "shop_gstin": os.getenv("SHOP_GSTIN", ""),
    "upi_id": os.getenv("UPI_ID", ""),
    "logo_path": os.getenv("LOGO_PATH", ""),
    "invoice_title": os.getenv("INVOICE_TITLE", "INVOICE"),
    "accent_color": os.getenv("ACCENT_COLOR", "#2563EB"),
    "footer_note": os.getenv("FOOTER_NOTE", "Thank you for your business!"),
    "terms": os.getenv("TERMS", ""),
}


def get_template():
    """Return the full template dict (defaults overridden by saved values)."""
    template = dict(DEFAULTS)
    session = get_session()
    try:
        for row in session.query(Setting).all():
            if row.key in template and row.value is not None:
                template[row.key] = row.value
    finally:
        session.close()
    return template


def save_template(values):
    session = get_session()
    try:
        for key, value in values.items():
            if key not in DEFAULTS:
                continue
            row = session.query(Setting).filter(Setting.key == key).first()
            if row:
                row.value = value
            else:
                session.add(Setting(key=key, value=value))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

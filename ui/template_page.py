from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import (
    QColor, QImage, QPixmap, QTextDocument,
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton,
    QLabel, QFrame, QGraphicsDropShadowEffect, QPlainTextEdit, QTextBrowser,
    QColorDialog, QFileDialog, QMessageBox,
)

from app_paths import data_dir
from services.bill_service import BillDTO, BillItemDTO
from services.settings_service import get_template, save_template
from ui import bill_document

# The chosen logo is copied here so the PDF keeps working from a frozen build.
LOGO_FILE = data_dir() / "assets" / "bill-logo.png"


class TemplatePage(QWidget):
    """Lets the user customise what the bill PDF looks like."""

    def __init__(self):
        super().__init__()
        self.logo_path = ""
        self.accent_color = "#2563EB"
        self.init_ui()
        self.load_template()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(18)

        header = QLabel("Bill Template")
        header.setObjectName("PageTitle")
        subheader = QLabel("Customise the details shown on the bill PDF and preview it live")
        subheader.setObjectName("PageSubtitle")
        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        header_box.addWidget(header)
        header_box.addWidget(subheader)
        outer.addLayout(header_box)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        columns.addWidget(self.build_form_card(), 1)
        columns.addWidget(self.build_preview_card(), 1)
        outer.addLayout(columns, 1)

    def make_shadow(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 30))
        return shadow

    def build_form_card(self):
        card = QFrame()
        card.setObjectName("Card")
        card.setGraphicsEffect(self.make_shadow())

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Template Details")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.shop_name_input = QLineEdit()
        self.tagline_input = QLineEdit()
        self.shop_address_input = QPlainTextEdit()
        self.shop_address_input.setFixedHeight(70)
        self.shop_phone_input = QLineEdit()
        self.shop_email_input = QLineEdit()
        self.gstin_input = QLineEdit()
        self.upi_input = QLineEdit()
        self.invoice_title_input = QLineEdit()

        self.logo_preview = QLabel("No logo")
        self.logo_preview.setFixedSize(64, 64)
        self.logo_preview.setAlignment(Qt.AlignCenter)
        self.logo_preview.setStyleSheet(
            "border:1px solid #CBD5E1; border-radius:8px; background:#F8FAFC;"
            "color:#94A3B8; font-size:9px;"
        )
        self.logo_button = QPushButton("Choose Image")
        self.logo_button.setObjectName("SecondaryButton")
        self.logo_button.clicked.connect(self.choose_logo)
        self.remove_logo_button = QPushButton("Remove")
        self.remove_logo_button.setObjectName("SecondaryButton")
        self.remove_logo_button.clicked.connect(self.remove_logo)

        logo_row = QWidget()
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(8)
        logo_layout.addWidget(self.logo_preview)
        logo_layout.addWidget(self.logo_button)
        logo_layout.addWidget(self.remove_logo_button)
        logo_layout.addStretch()

        self.color_button = QPushButton("Choose Colour")
        self.color_button.setObjectName("SecondaryButton")
        self.color_button.clicked.connect(self.choose_color)
        self._paint_color_button()

        self.footer_input = QLineEdit()
        self.terms_input = QPlainTextEdit()
        self.terms_input.setFixedHeight(90)

        form.addRow("Shop Name", self.shop_name_input)
        form.addRow("Tagline", self.tagline_input)
        form.addRow("Address", self.shop_address_input)
        form.addRow("Phone", self.shop_phone_input)
        form.addRow("Email", self.shop_email_input)
        form.addRow("GSTIN", self.gstin_input)
        form.addRow("UPI ID", self.upi_input)
        form.addRow("Logo Image", logo_row)
        form.addRow("Invoice Title", self.invoice_title_input)
        form.addRow("Accent Colour", self.color_button)
        form.addRow("Footer Note", self.footer_input)
        form.addRow("Terms", self.terms_input)
        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch()
        reset_btn = QPushButton("Reset")
        reset_btn.setObjectName("SecondaryButton")
        reset_btn.clicked.connect(self.load_template)
        save_btn = QPushButton("Save Template")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.save)
        button_row.addWidget(reset_btn)
        button_row.addWidget(save_btn)
        layout.addLayout(button_row)

        # live preview while typing
        for field in (
            self.shop_name_input, self.tagline_input, self.shop_phone_input,
            self.shop_email_input, self.gstin_input, self.upi_input,
            self.invoice_title_input, self.footer_input,
        ):
            field.textChanged.connect(self.update_preview)
        self.shop_address_input.textChanged.connect(self.update_preview)
        self.terms_input.textChanged.connect(self.update_preview)

        return card

    def build_preview_card(self):
        card = QFrame()
        card.setObjectName("Card")
        card.setGraphicsEffect(self.make_shadow())

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Live Preview")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        self.preview = QTextBrowser()
        self.preview.setObjectName("Preview")
        self.preview.setOpenExternalLinks(False)
        layout.addWidget(self.preview)
        return card

    # ------------------------------------------------------------------ #
    # Behaviour
    # ------------------------------------------------------------------ #
    def _paint_color_button(self):
        self.color_button.setText(self.accent_color)
        self.color_button.setStyleSheet(
            f"background-color:{self.accent_color}; color:white; border:none;"
            f"border-radius:8px; padding:9px 22px; font-weight:600;"
        )

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.accent_color), self, "Accent Colour")
        if color.isValid():
            self.accent_color = color.name()
            self._paint_color_button()
            self.update_preview()

    def choose_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Bill Logo", "", "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            QMessageBox.warning(self, "Invalid Image", "That file could not be opened as an image.")
            return
        try:
            LOGO_FILE.parent.mkdir(parents=True, exist_ok=True)
            if not image.save(str(LOGO_FILE), "PNG"):
                raise OSError("Qt could not write the logo file.")
        except Exception as error:
            QMessageBox.critical(self, "Error", f"Could not save the logo:\n{error}")
            return
        self.logo_path = str(LOGO_FILE)
        self._show_logo()
        self.update_preview()

    def remove_logo(self):
        self.logo_path = ""
        if LOGO_FILE.exists():
            try:
                LOGO_FILE.unlink()
            except OSError:
                pass
        self._show_logo()
        self.update_preview()

    def _show_logo(self):
        if self.logo_path and Path(self.logo_path).is_file():
            pixmap = QPixmap(self.logo_path)
            if not pixmap.isNull():
                self.logo_preview.setPixmap(
                    pixmap.scaled(
                        self.logo_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )
                return
        self.logo_preview.setPixmap(QPixmap())
        self.logo_preview.setText("No logo")

    def form_values(self):
        return {
            "shop_name": self.shop_name_input.text().strip(),
            "shop_tagline": self.tagline_input.text().strip(),
            "shop_address": self.shop_address_input.toPlainText().strip(),
            "shop_phone": self.shop_phone_input.text().strip(),
            "shop_email": self.shop_email_input.text().strip(),
            "shop_gstin": self.gstin_input.text().strip(),
            "upi_id": self.upi_input.text().strip(),
            "logo_path": self.logo_path,
            "invoice_title": self.invoice_title_input.text().strip() or "INVOICE",
            "accent_color": self.accent_color,
            "footer_note": self.footer_input.text().strip(),
            "terms": self.terms_input.toPlainText().strip(),
        }

    def load_template(self):
        template = get_template()
        self.shop_name_input.setText(template.get("shop_name", ""))
        self.tagline_input.setText(template.get("shop_tagline", ""))
        self.shop_address_input.setPlainText(template.get("shop_address", ""))
        self.shop_phone_input.setText(template.get("shop_phone", ""))
        self.shop_email_input.setText(template.get("shop_email", ""))
        self.gstin_input.setText(template.get("shop_gstin", ""))
        self.upi_input.setText(template.get("upi_id", ""))
        self.logo_path = template.get("logo_path", "") or ""
        if self.logo_path and not Path(self.logo_path).is_file():
            self.logo_path = ""
        self._show_logo()
        self.invoice_title_input.setText(template.get("invoice_title", "INVOICE"))
        self.accent_color = template.get("accent_color", "#2563EB")
        self._paint_color_button()
        self.footer_input.setText(template.get("footer_note", ""))
        self.terms_input.setPlainText(template.get("terms", ""))
        self.update_preview()

    def save(self):
        try:
            save_template(self.form_values())
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return
        self.update_preview()
        QMessageBox.information(self, "Saved", "Bill template saved.")

    def update_preview(self):
        sample = BillDTO(
            id=None, bill_number="INV-00001", customer_name="Sample Customer",
            customer_phone="9876543210", created_at=datetime.now(),
            subtotal=1350.0, total=1350.0,
            items=[
                BillItemDTO(1, "Basmati Rice 5kg", 2, 500.0, 1000.0),
                BillItemDTO(2, "Sunflower Oil 1L", 1, 350.0, 350.0),
            ],
        )
        values = self.form_values()
        self.preview.document().addResource(
            QTextDocument.ImageResource, QUrl("logo"),
            bill_document.load_logo_image(values),
        )
        self.preview.setHtml(bill_document.build_bill_html(sample, template=values))

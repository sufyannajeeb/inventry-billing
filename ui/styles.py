"""Central stylesheet for the whole application.

Applied once on the QApplication so every page, the sidebar and dialogs share
the same look. Individual pages no longer carry their own stylesheets.
"""

APP_STYLESHEET = """
QWidget {
    background-color: #F4F6F9;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
    color: #1F2937;
}

/* ---------- Sidebar ---------- */
#Sidebar {
    background-color: #111827;
    border: none;
}
#Sidebar QLabel {
    color: #9CA3AF;
    background: transparent;
}
#BrandTitle {
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 700;
}
#BrandSubtitle {
    color: #6B7280;
    font-size: 11px;
}
#NavButton {
    background-color: transparent;
    color: #D1D5DB;
    border: none;
    border-radius: 8px;
    padding: 11px 14px;
    text-align: left;
    font-size: 13.5px;
    font-weight: 500;
}
#NavButton:hover {
    background-color: #1F2937;
    color: #FFFFFF;
}
#NavButton:checked {
    background-color: #2563EB;
    color: #FFFFFF;
    font-weight: 600;
}

/* ---------- Page headers ---------- */
#PageTitle {
    font-size: 22px;
    font-weight: 700;
    color: #111827;
    background: transparent;
}
#PageSubtitle {
    font-size: 13px;
    color: #6B7280;
    background: transparent;
}

/* ---------- Cards ---------- */
#Card {
    background-color: #FFFFFF;
    border-radius: 12px;
    border: 1px solid #E5E7EB;
}
#CardTitle {
    font-size: 15px;
    font-weight: 600;
    color: #111827;
    padding-bottom: 4px;
    background: transparent;
}

/* ---------- Inputs ---------- */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QPlainTextEdit {
    background-color: #F9FAFB;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    padding: 8px 10px;
    min-height: 20px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus {
    border: 1.5px solid #2563EB;
    background-color: #FFFFFF;
}

#Preview {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 12px;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    selection-background-color: #EFF6FF;
    selection-color: #111827;
    outline: none;
}
QLabel {
    color: #374151;
    background: transparent;
}

/* ---------- Buttons ---------- */
#PrimaryButton {
    background-color: #2563EB;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 22px;
    font-weight: 600;
}
#PrimaryButton:hover {
    background-color: #1D4ED8;
}
#PrimaryButton:pressed {
    background-color: #1E40AF;
}

#SecondaryButton {
    background-color: #F3F4F6;
    color: #374151;
    border: 1px solid #D1D5DB;
    border-radius: 8px;
    padding: 9px 22px;
    font-weight: 500;
}
#SecondaryButton:hover {
    background-color: #E5E7EB;
}

#WhatsAppButton {
    background-color: #25D366;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 9px 22px;
    font-weight: 600;
}
#WhatsAppButton:hover {
    background-color: #1EBE57;
}
#WhatsAppButton:pressed {
    background-color: #17A34A;
}

#EditButton {
    background-color: #EFF6FF;
    color: #2563EB;
    border: 1px solid #BFDBFE;
    border-radius: 6px;
    padding: 4px 12px;
    font-weight: 500;
}
#EditButton:hover {
    background-color: #DBEAFE;
}

#DeleteButton {
    background-color: #FEF2F2;
    color: #DC2626;
    border: 1px solid #FECACA;
    border-radius: 6px;
    padding: 4px 12px;
    font-weight: 500;
}
#DeleteButton:hover {
    background-color: #FEE2E2;
}

/* ---------- Billing summary ---------- */
#TotalCaption {
    font-size: 13px;
    color: #6B7280;
    background: transparent;
}
#TotalValue {
    font-size: 24px;
    font-weight: 700;
    color: #111827;
    background: transparent;
}
#HintLabel {
    font-size: 12px;
    color: #9CA3AF;
    background: transparent;
}

/* ---------- Tables ---------- */
QTableWidget {
    background-color: #FFFFFF;
    border: none;
    gridline-color: #F3F4F6;
    selection-background-color: #EFF6FF;
    selection-color: #111827;
}
QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #F3F4F6;
}
QTableWidget::item:alternate {
    background-color: #FAFBFC;
}
QHeaderView::section {
    background-color: #F9FAFB;
    color: #6B7280;
    font-weight: 600;
    padding: 10px 6px;
    border: none;
    border-bottom: 1px solid #E5E7EB;
}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {
    background: #F4F6F9;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #D1D5DB;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #9CA3AF;
}
QScrollBar:horizontal {
    background: #F4F6F9;
    height: 10px;
    border-radius: 5px;
}
QScrollBar::handle:horizontal {
    background: #D1D5DB;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #9CA3AF;
}
"""

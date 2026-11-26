from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox, QInputDialog,
    QDoubleSpinBox, QSpinBox, QLabel, QHeaderView, QFrame, QComboBox,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from services.product_service import (
    get_all_products, get_all_categories, add_category,
    add_product, update_product, delete_product,
)

UNITS = ["pcs", "kg", "g", "ltr", "ml", "box", "packet", "dozen", "bottle", "bag"]


class ProductPage(QWidget):
    def __init__(self):
        super().__init__()
        self.editing_product_id = None
        self.init_ui()
        self.load_categories()
        self.load_products()

    def init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(24, 24, 24, 24)
        outer_layout.setSpacing(18)

        # ---- Header ----
        header = QLabel("Inventory")
        header.setObjectName("PageTitle")
        subheader = QLabel("Add, edit and manage your product catalog")
        subheader.setObjectName("PageSubtitle")

        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        header_box.addWidget(header)
        header_box.addWidget(subheader)
        outer_layout.addLayout(header_box)

        # ---- Form Card ----
        form_card = QFrame()
        form_card.setObjectName("Card")
        form_card.setGraphicsEffect(self.make_shadow())

        form_card_layout = QVBoxLayout(form_card)
        form_card_layout.setContentsMargins(20, 20, 20, 20)
        form_card_layout.setSpacing(14)

        form_title = QLabel("Product Details")
        form_title.setObjectName("CardTitle")
        form_card_layout.addWidget(form_title)

        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        form_layout.setLabelAlignment(Qt.AlignRight)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Basmati Rice 5kg")

        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Optional")

        self.hsn_input = QLineEdit()
        self.hsn_input.setPlaceholderText("Optional")

        self.price_input = QDoubleSpinBox()
        self.price_input.setMaximum(1_000_000)
        self.price_input.setPrefix("Rs. ")
        self.price_input.setButtonSymbols(QDoubleSpinBox.NoButtons)

        self.purchase_input = QDoubleSpinBox()
        self.purchase_input.setMaximum(1_000_000)
        self.purchase_input.setPrefix("Rs. ")
        self.purchase_input.setButtonSymbols(QDoubleSpinBox.NoButtons)

        self.gst_input = QDoubleSpinBox()
        self.gst_input.setMaximum(100)
        self.gst_input.setSuffix(" %")
        self.gst_input.setButtonSymbols(QDoubleSpinBox.NoButtons)

        self.stock_input = QSpinBox()
        self.stock_input.setMaximum(1_000_000)
        self.stock_input.setButtonSymbols(QSpinBox.NoButtons)

        self.unit_input = QComboBox()
        self.unit_input.setEditable(True)
        self.unit_input.addItems(UNITS)

        # Category row: combo + "Add" button
        category_row = QWidget()
        category_layout = QHBoxLayout(category_row)
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.setSpacing(8)
        self.category_input = QComboBox()
        add_category_btn = QPushButton("Add")
        add_category_btn.setObjectName("EditButton")
        add_category_btn.clicked.connect(self.create_category)
        category_layout.addWidget(self.category_input, 1)
        category_layout.addWidget(add_category_btn)

        form_layout.addRow("Product Name", self.name_input)
        form_layout.addRow("Barcode", self.barcode_input)
        form_layout.addRow("Category", category_row)
        form_layout.addRow("HSN Code", self.hsn_input)
        form_layout.addRow("Selling Price", self.price_input)
        form_layout.addRow("Purchase Price", self.purchase_input)
        form_layout.addRow("GST", self.gst_input)
        form_layout.addRow("Stock Quantity", self.stock_input)
        form_layout.addRow("Unit", self.unit_input)

        form_card_layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("SecondaryButton")
        self.clear_btn.clicked.connect(self.clear_form)

        self.save_btn = QPushButton("Add Product")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_product)

        btn_layout.addWidget(self.clear_btn)
        btn_layout.addWidget(self.save_btn)
        form_card_layout.addLayout(btn_layout)

        outer_layout.addWidget(form_card)

        # ---- Table Card ----
        table_card = QFrame()
        table_card.setObjectName("Card")
        table_card.setGraphicsEffect(self.make_shadow())

        table_card_layout = QVBoxLayout(table_card)
        table_card_layout.setContentsMargins(20, 20, 20, 20)
        table_card_layout.setSpacing(12)

        table_title = QLabel("All Products")
        table_title.setObjectName("CardTitle")
        table_card_layout.addWidget(table_title)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "Barcode", "Category", "Price", "Stock", "Actions"]
        )
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(44)

        table_card_layout.addWidget(self.table)
        outer_layout.addWidget(table_card)

    def make_shadow(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 30))
        return shadow

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #
    def load_categories(self, select_id=None):
        self.category_input.clear()
        self.category_input.addItem("(No Category)", None)
        for category in get_all_categories():
            self.category_input.addItem(category.name, category.id)
        if select_id is not None:
            index = self.category_input.findData(select_id)
            if index >= 0:
                self.category_input.setCurrentIndex(index)

    def load_products(self):
        products = get_all_products()
        self.table.setRowCount(len(products))

        for row, p in enumerate(products):
            self.table.setItem(row, 0, QTableWidgetItem(str(p.id)))
            self.table.setItem(row, 1, QTableWidgetItem(p.name))
            self.table.setItem(row, 2, QTableWidgetItem(p.barcode or "-"))
            self.table.setItem(
                row, 3, QTableWidgetItem(p.category.name if p.category else "-")
            )
            self.table.setItem(row, 4, QTableWidgetItem(f"Rs. {p.price:,.2f}"))

            stock_item = QTableWidgetItem(str(p.stock_quantity))
            if p.stock_quantity <= 5:
                stock_item.setForeground(QColor("#DC2626"))
            self.table.setItem(row, 5, stock_item)

            for col in [0, 4, 5]:
                self.table.item(row, col).setTextAlignment(Qt.AlignCenter)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(8, 4, 8, 4)
            action_layout.setSpacing(6)

            edit_btn = QPushButton("Edit")
            edit_btn.setObjectName("EditButton")
            edit_btn.clicked.connect(lambda checked, prod=p: self.load_for_edit(prod))

            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("DeleteButton")
            delete_btn.clicked.connect(lambda checked, prod=p: self.confirm_delete(prod))

            action_layout.addWidget(edit_btn)
            action_layout.addWidget(delete_btn)
            self.table.setCellWidget(row, 6, action_widget)

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def create_category(self):
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if not ok or not name.strip():
            return
        try:
            category_id = add_category(name)
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return
        self.load_categories(select_id=category_id)

    def save_product(self):
        name = self.name_input.text().strip()
        barcode = self.barcode_input.text().strip()
        hsn = self.hsn_input.text().strip()
        price = self.price_input.value()
        purchase = self.purchase_input.value()
        gst = self.gst_input.value()
        stock = self.stock_input.value()
        unit = self.unit_input.currentText().strip() or "pcs"
        category_id = self.category_input.currentData()

        if not name:
            QMessageBox.warning(self, "Missing Info", "Product name is required.")
            return

        try:
            if self.editing_product_id:
                update_product(
                    self.editing_product_id, name=name, price=price,
                    stock_quantity=stock, barcode=barcode, category_id=category_id,
                    purchase_price=purchase, gst_percent=gst, unit=unit,
                    hsn_code=hsn,
                )
                QMessageBox.information(self, "Updated", "Product updated successfully.")
            else:
                add_product(
                    name=name, price=price, stock_quantity=stock, barcode=barcode,
                    category_id=category_id, purchase_price=purchase,
                    gst_percent=gst, unit=unit, hsn_code=hsn,
                )
                QMessageBox.information(self, "Added", "Product added successfully.")

            self.clear_form()
            self.load_products()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def load_for_edit(self, product):
        self.editing_product_id = product.id
        self.name_input.setText(product.name)
        self.barcode_input.setText(product.barcode or "")
        self.hsn_input.setText(product.hsn_code or "")
        self.price_input.setValue(product.price or 0.0)
        self.purchase_input.setValue(product.purchase_price or 0.0)
        self.gst_input.setValue(product.gst_percent or 0.0)
        self.stock_input.setValue(product.stock_quantity or 0)
        self.unit_input.setCurrentText(product.unit or "pcs")
        index = self.category_input.findData(product.category_id)
        self.category_input.setCurrentIndex(index if index >= 0 else 0)
        self.save_btn.setText("Update Product")

    def confirm_delete(self, product):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete '{product.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            delete_product(product.id)
            self.load_products()

    def clear_form(self):
        self.editing_product_id = None
        self.name_input.clear()
        self.barcode_input.clear()
        self.hsn_input.clear()
        self.price_input.setValue(0)
        self.purchase_input.setValue(0)
        self.gst_input.setValue(0)
        self.stock_input.setValue(0)
        self.unit_input.setCurrentText("pcs")
        self.category_input.setCurrentIndex(0)
        self.save_btn.setText("Add Product")

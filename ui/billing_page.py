from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox, QSpinBox,
    QDoubleSpinBox, QLabel, QHeaderView, QFrame, QGraphicsDropShadowEffect,
)

from services.product_service import get_all_products
from services.bill_service import (
    BillDTO, BillItemDTO, create_bill, get_all_bills, delete_bill,
)
from ui import bill_document


class BillingPage(QWidget):
    def __init__(self):
        super().__init__()
        self.cart = []              # list of {product_id, product_name, quantity, price}
        self.current_bill = None    # BillDTO that the action buttons operate on
        self._products = []
        self.init_ui()
        self.reload_data()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def init_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(18)

        header = QLabel("Billing")
        header.setObjectName("PageTitle")
        subheader = QLabel("Create a bill, then send it on WhatsApp, download or print it")
        subheader.setObjectName("PageSubtitle")
        header_box = QVBoxLayout()
        header_box.setSpacing(2)
        header_box.addWidget(header)
        header_box.addWidget(subheader)
        outer.addLayout(header_box)

        outer.addWidget(self._build_customer_card())
        outer.addWidget(self._build_items_card())
        outer.addWidget(self._build_actions_card())
        outer.addWidget(self._build_history_card(), 1)

    def make_shadow(self):
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 30))
        return shadow

    def _card(self):
        card = QFrame()
        card.setObjectName("Card")
        card.setGraphicsEffect(self.make_shadow())
        return card

    def _build_customer_card(self):
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Customer Details")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.customer_name_input = QLineEdit()
        self.customer_name_input.setPlaceholderText("Walk-in Customer")
        self.customer_phone_input = QLineEdit()
        self.customer_phone_input.setPlaceholderText("e.g. 9876543210 (used for WhatsApp)")

        form.addRow("Customer Name", self.customer_name_input)
        form.addRow("Phone Number", self.customer_phone_input)
        layout.addLayout(form)
        return card

    def _build_items_card(self):
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Bill Items")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        add_row = QHBoxLayout()
        add_row.setSpacing(10)

        self.product_combo = QComboBox()
        self.product_combo.setMinimumWidth(240)
        self.product_combo.currentIndexChanged.connect(self.on_product_changed)

        self.qty_input = QSpinBox()
        self.qty_input.setRange(1, 1_000_000)
        self.qty_input.setButtonSymbols(QSpinBox.NoButtons)
        self.qty_input.setPrefix("Qty  ")

        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 1_000_000)
        self.price_input.setPrefix("Rs. ")
        self.price_input.setButtonSymbols(QDoubleSpinBox.NoButtons)

        add_btn = QPushButton("Add Item")
        add_btn.setObjectName("PrimaryButton")
        add_btn.clicked.connect(self.add_item)

        add_row.addWidget(self.product_combo, 3)
        add_row.addWidget(self.qty_input, 1)
        add_row.addWidget(self.price_input, 1)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self.stock_hint = QLabel("")
        self.stock_hint.setObjectName("HintLabel")
        layout.addWidget(self.stock_hint)

        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(5)
        self.cart_table.setHorizontalHeaderLabels(
            ["Item", "Qty", "Price", "Line Total", "Actions"]
        )
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cart_table.setAlternatingRowColors(True)
        self.cart_table.setShowGrid(False)
        self.cart_table.verticalHeader().setDefaultSectionSize(42)
        self.cart_table.setMinimumHeight(150)
        layout.addWidget(self.cart_table)

        total_row = QHBoxLayout()
        total_row.addStretch()
        caption = QLabel("Total")
        caption.setObjectName("TotalCaption")
        self.total_value = QLabel("Rs. 0.00")
        self.total_value.setObjectName("TotalValue")
        total_row.addWidget(caption)
        total_row.addWidget(self.total_value)
        layout.addLayout(total_row)

        return card

    def _build_actions_card(self):
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        self.save_btn = QPushButton("Save Bill")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_bill)

        self.new_btn = QPushButton("New Bill")
        self.new_btn.setObjectName("SecondaryButton")
        self.new_btn.clicked.connect(self.new_bill)

        self.whatsapp_btn = QPushButton("Send PDF on WhatsApp")
        self.whatsapp_btn.setObjectName("WhatsAppButton")
        self.whatsapp_btn.clicked.connect(self.send_whatsapp)

        self.open_whatsapp_btn = QPushButton("Open WhatsApp")
        self.open_whatsapp_btn.setObjectName("SecondaryButton")
        self.open_whatsapp_btn.clicked.connect(self.open_whatsapp)

        self.download_btn = QPushButton("Download PDF")
        self.download_btn.setObjectName("SecondaryButton")
        self.download_btn.clicked.connect(self.download_pdf)

        self.print_btn = QPushButton("Print")
        self.print_btn.setObjectName("SecondaryButton")
        self.print_btn.clicked.connect(self.print_bill)

        self.preview_btn = QPushButton("Preview PDF")
        self.preview_btn.setObjectName("SecondaryButton")
        self.preview_btn.clicked.connect(self.preview_pdf)

        # Two tidy rows so the buttons never get squeezed together.
        row_one = QHBoxLayout()
        row_one.setSpacing(10)
        row_one.addWidget(self.save_btn)
        row_one.addWidget(self.new_btn)
        row_one.addWidget(self.preview_btn)
        row_one.addStretch()

        row_two = QHBoxLayout()
        row_two.setSpacing(10)
        row_two.addWidget(self.whatsapp_btn)
        row_two.addWidget(self.download_btn)
        row_two.addWidget(self.print_btn)
        row_two.addWidget(self.open_whatsapp_btn)
        row_two.addStretch()

        layout.addLayout(row_one)
        layout.addLayout(row_two)
        return card

    def _build_history_card(self):
        card = self._card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Recent Bills")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(
            ["Bill No", "Customer", "Phone", "Total", "Date", "Actions"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setShowGrid(False)
        self.history_table.verticalHeader().setDefaultSectionSize(44)
        self.history_table.setMinimumHeight(150)
        layout.addWidget(self.history_table)
        return card

    # ------------------------------------------------------------------ #
    # Data loading
    # ------------------------------------------------------------------ #
    def reload_data(self):
        self.load_products()
        self.load_history()

    def load_products(self):
        self._products = get_all_products()
        self.product_combo.blockSignals(True)
        self.product_combo.clear()
        for product in self._products:
            self.product_combo.addItem(product.name, product.id)
        self.product_combo.blockSignals(False)
        self.on_product_changed()

    def load_history(self):
        bills = get_all_bills()
        self.history_table.setRowCount(len(bills))
        for row, bill in enumerate(bills):
            self.history_table.setItem(row, 0, QTableWidgetItem(bill.bill_number))
            self.history_table.setItem(row, 1, QTableWidgetItem(bill.customer_name))
            self.history_table.setItem(row, 2, QTableWidgetItem(bill.customer_phone or "-"))
            self.history_table.setItem(row, 3, QTableWidgetItem(f"Rs. {bill.total:,.2f}"))
            created = bill.created_at.strftime("%d-%b-%Y %I:%M %p") if bill.created_at else "-"
            self.history_table.setItem(row, 4, QTableWidgetItem(created))

            for col in [0, 3, 4]:
                self.history_table.item(row, col).setTextAlignment(Qt.AlignCenter)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(8, 4, 8, 4)
            action_layout.setSpacing(6)

            open_btn = QPushButton("Open")
            open_btn.setObjectName("EditButton")
            open_btn.clicked.connect(lambda checked, b=bill: self.open_bill(b))

            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("DeleteButton")
            delete_btn.clicked.connect(lambda checked, b=bill: self.confirm_delete(b))

            action_layout.addWidget(open_btn)
            action_layout.addWidget(delete_btn)
            self.history_table.setCellWidget(row, 5, action_widget)

    # ------------------------------------------------------------------ #
    # Cart handling
    # ------------------------------------------------------------------ #
    def on_product_changed(self):
        product = self.selected_product()
        if not product:
            self.stock_hint.setText("")
            return
        self.price_input.setValue(product.price or 0.0)
        self.qty_input.setValue(1)
        self.stock_hint.setText(
            f"In stock: {product.stock_quantity} {product.unit or 'pcs'}"
        )

    def selected_product(self):
        product_id = self.product_combo.currentData()
        for product in self._products:
            if product.id == product_id:
                return product
        return None

    def add_item(self):
        product = self.selected_product()
        if not product:
            QMessageBox.warning(self, "No Product", "Add products in Inventory first.")
            return

        quantity = self.qty_input.value()
        price = self.price_input.value()

        if quantity > (product.stock_quantity or 0):
            QMessageBox.warning(
                self, "Not Enough Stock",
                f"Only {product.stock_quantity} {product.unit or 'pcs'} of "
                f"'{product.name}' available.",
            )
            return

        for item in self.cart:
            if item["product_id"] == product.id and item["price"] == price:
                item["quantity"] += quantity
                break
        else:
            self.cart.append({
                "product_id": product.id,
                "product_name": product.name,
                "quantity": quantity,
                "price": price,
            })

        self.current_bill = None
        self.refresh_cart()

    def refresh_cart(self):
        self.cart_table.setRowCount(len(self.cart))
        total = 0.0
        for row, item in enumerate(self.cart):
            line_total = item["quantity"] * item["price"]
            total += line_total

            self.cart_table.setItem(row, 0, QTableWidgetItem(item["product_name"]))
            qty_item = QTableWidgetItem(str(item["quantity"]))
            qty_item.setTextAlignment(Qt.AlignCenter)
            self.cart_table.setItem(row, 1, qty_item)
            price_item = QTableWidgetItem(f"Rs. {item['price']:,.2f}")
            price_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.cart_table.setItem(row, 2, price_item)
            total_item = QTableWidgetItem(f"Rs. {line_total:,.2f}")
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.cart_table.setItem(row, 3, total_item)

            remove_btn = QPushButton("Remove")
            remove_btn.setObjectName("DeleteButton")
            remove_btn.clicked.connect(
                lambda checked, index=row: self.remove_item(index)
            )
            wrapper = QWidget()
            wrapper_layout = QHBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(8, 4, 8, 4)
            wrapper_layout.addWidget(remove_btn)
            self.cart_table.setCellWidget(row, 4, wrapper)

        self.total_value.setText(f"Rs. {total:,.2f}")

    def remove_item(self, index):
        if 0 <= index < len(self.cart):
            del self.cart[index]
            self.current_bill = None
            self.refresh_cart()

    # ------------------------------------------------------------------ #
    # Actions
    # ------------------------------------------------------------------ #
    def save_bill(self):
        if not self.cart:
            QMessageBox.warning(self, "Empty Bill", "Add at least one item.")
            return
        try:
            bill = create_bill(
                self.customer_name_input.text().strip(),
                self.customer_phone_input.text().strip(),
                self.cart,
            )
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return

        self.current_bill = bill
        self.cart = []
        self.refresh_cart()
        self.load_products()
        self.load_history()
        QMessageBox.information(
            self, "Bill Saved", f"Bill {bill.bill_number} saved successfully."
        )

    def _bill_for_action(self):
        """The saved/opened bill, or a temporary one built from the cart."""
        if self.current_bill:
            return self.current_bill
        if not self.cart:
            return None
        subtotal = sum(i["quantity"] * i["price"] for i in self.cart)
        return BillDTO(
            id=None,
            bill_number="DRAFT",
            customer_name=self.customer_name_input.text().strip() or "Walk-in Customer",
            customer_phone=self.customer_phone_input.text().strip(),
            created_at=None,
            subtotal=subtotal,
            total=subtotal,
            items=[
                BillItemDTO(
                    product_id=i["product_id"],
                    product_name=i["product_name"],
                    quantity=i["quantity"],
                    price=i["price"],
                    line_total=i["quantity"] * i["price"],
                )
                for i in self.cart
            ],
        )

    def send_whatsapp(self):
        bill = self._bill_for_action()
        if not bill:
            QMessageBox.warning(self, "Nothing to Send", "Add items to the bill first.")
            return
        bill_document.send_bill_pdf_to_whatsapp(bill, self)

    def open_whatsapp(self):
        bill_document.open_whatsapp(self)

    def download_pdf(self):
        bill = self._bill_for_action()
        if not bill:
            QMessageBox.warning(self, "Nothing to Save", "Add items to the bill first.")
            return
        bill_document.save_bill_pdf(bill, self)

    def preview_pdf(self):
        bill = self._bill_for_action()
        if not bill:
            QMessageBox.warning(self, "Nothing to Preview", "Add items to the bill first.")
            return
        bill_document.preview_bill_pdf(bill, self)

    def print_bill(self):
        bill = self._bill_for_action()
        if not bill:
            QMessageBox.warning(self, "Nothing to Print", "Add items to the bill first.")
            return
        bill_document.print_bill(bill, self)

    def open_bill(self, bill):
        self.current_bill = bill
        QMessageBox.information(
            self, "Bill Selected",
            f"Bill {bill.bill_number} selected.\n\n"
            "Use Send to WhatsApp, Download PDF or Print to share it.",
        )

    def confirm_delete(self, bill):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete bill {bill.bill_number}? Stock will be restored.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            delete_bill(bill.id)
        except Exception as error:
            QMessageBox.critical(self, "Error", str(error))
            return
        if self.current_bill and self.current_bill.id == bill.id:
            self.current_bill = None
        self.load_products()
        self.load_history()

    def new_bill(self):
        self.cart = []
        self.current_bill = None
        self.customer_name_input.clear()
        self.customer_phone_input.clear()
        self.refresh_cart()

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QStackedWidget, QFrame, QScrollArea,
)

from ui.billing_page import BillingPage
from ui.product_page import ProductPage
from ui.template_page import TemplatePage


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Billing Software")
        self.resize(1280, 840)
        self.setMinimumSize(1000, 640)
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self.build_sidebar())

        self.stack = QStackedWidget()
        self.billing_page = BillingPage()
        self.inventory_page = ProductPage()
        self.template_page = TemplatePage()

        self.stack.addWidget(self.scrollable(self.billing_page))
        self.stack.addWidget(self.scrollable(self.inventory_page))
        self.stack.addWidget(self.scrollable(self.template_page))
        layout.addWidget(self.stack, 1)

        self.select_page(0)

    def scrollable(self, page):
        """Wrap a page in a scroll area so content never overlaps or clips."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setWidget(page)
        return area

    def build_sidebar(self):
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 24, 16, 24)
        layout.setSpacing(6)

        brand = QLabel("Billing Software")
        brand.setObjectName("BrandTitle")
        tagline = QLabel("Point of Sale")
        tagline.setObjectName("BrandSubtitle")
        layout.addWidget(brand)
        layout.addWidget(tagline)
        layout.addSpacing(24)

        self.nav_buttons = [
            QPushButton("Billing"),
            QPushButton("Inventory"),
            QPushButton("Bill Template"),
        ]
        for index, button in enumerate(self.nav_buttons):
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked, i=index: self.select_page(i))
            layout.addWidget(button)

        layout.addStretch()
        return sidebar

    def select_page(self, index):
        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)
        self.stack.setCurrentIndex(index)

        # Refresh the page being shown so stock, bills and template stay in sync.
        if index == 0:
            self.billing_page.reload_data()
        elif index == 1:
            self.inventory_page.load_products()
        else:
            self.template_page.load_template()

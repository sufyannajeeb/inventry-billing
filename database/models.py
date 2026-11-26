from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    barcode = Column(String(50), unique=True, nullable=True)
    hsn_code = Column(String(20), nullable=True)

    price = Column(Float, nullable=False, default=0.0)
    purchase_price = Column(Float, nullable=True, default=0.0)
    gst_percent = Column(Float, nullable=True, default=0.0)

    stock_quantity = Column(Integer, default=0)
    unit = Column(String(20), default="pcs")

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    category = relationship("Category", back_populates="products")

    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<Product(id={self.id}, name='{self.name}', stock={self.stock_quantity})>"


class Setting(Base):
    """Simple key/value store used for the customisable bill template."""

    __tablename__ = "settings"

    key = Column(String(50), primary_key=True)
    value = Column(String(2000), nullable=True)

    def __repr__(self):
        return f"<Setting(key='{self.key}')>"


class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    bill_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_name = Column(String(150), nullable=True, default="Walk-in Customer")
    customer_phone = Column(String(30), nullable=True, default="")

    subtotal = Column(Float, nullable=False, default=0.0)
    total = Column(Float, nullable=False, default=0.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship(
        "BillItem", back_populates="bill", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Bill(id={self.id}, number='{self.bill_number}', total={self.total})>"


class BillItem(Base):
    __tablename__ = "bill_items"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)

    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(150), nullable=False)

    quantity = Column(Integer, nullable=False, default=1)
    price = Column(Float, nullable=False, default=0.0)
    line_total = Column(Float, nullable=False, default=0.0)

    bill = relationship("Bill", back_populates="items")

    def __repr__(self):
        return f"<BillItem(name='{self.product_name}', qty={self.quantity})>"
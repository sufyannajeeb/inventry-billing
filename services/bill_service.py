"""Bill repository: all database access for bills lives here.

The UI never touches SQLAlchemy directly. Every function returns plain
data-transfer objects (DTOs) so the widgets can hold on to a bill after the
database session has been closed.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import joinedload

from database.database import get_session
from database.models import Bill, BillItem, Product


@dataclass
class BillItemDTO:
    product_id: int | None
    product_name: str
    quantity: int
    price: float
    line_total: float


@dataclass
class BillDTO:
    id: int | None
    bill_number: str
    customer_name: str
    customer_phone: str
    created_at: datetime | None
    subtotal: float
    total: float
    items: list[BillItemDTO] = field(default_factory=list)


def _to_dto(bill):
    items = [
        BillItemDTO(
            product_id=item.product_id,
            product_name=item.product_name,
            quantity=item.quantity,
            price=item.price,
            line_total=item.line_total,
        )
        for item in bill.items
    ]
    return BillDTO(
        id=bill.id,
        bill_number=bill.bill_number,
        customer_name=bill.customer_name or "Walk-in Customer",
        customer_phone=bill.customer_phone or "",
        created_at=bill.created_at,
        subtotal=bill.subtotal,
        total=bill.total,
        items=items,
    )


def generate_bill_number(session):
    """Sequential, human friendly bill number: INV-00001."""
    last = session.query(Bill).order_by(Bill.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    return f"INV-{next_id:05d}"


def create_bill(customer_name, customer_phone, items):
    """Persist a bill, deduct stock and return a BillDTO.

    `items` is a list of dicts: {product_id, product_name, quantity, price}.
    """
    session = get_session()
    try:
        if not items:
            raise ValueError("Cannot create a bill without any items.")

        bill = Bill(
            bill_number=generate_bill_number(session),
            customer_name=(customer_name or "").strip() or "Walk-in Customer",
            customer_phone=(customer_phone or "").strip(),
            subtotal=0.0,
            total=0.0,
        )

        subtotal = 0.0
        for row in items:
            quantity = int(row["quantity"])
            price = float(row["price"])
            line_total = quantity * price
            subtotal += line_total

            bill.items.append(
                BillItem(
                    product_id=row.get("product_id"),
                    product_name=row["product_name"],
                    quantity=quantity,
                    price=price,
                    line_total=line_total,
                )
            )

            product_id = row.get("product_id")
            if product_id:
                product = (
                    session.query(Product).filter(Product.id == product_id).first()
                )
                if product:
                    product.stock_quantity = max(
                        0, (product.stock_quantity or 0) - quantity
                    )

        bill.subtotal = subtotal
        bill.total = subtotal

        session.add(bill)
        session.commit()
        session.refresh(bill)
        return _to_dto(bill)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_all_bills():
    session = get_session()
    try:
        bills = (
            session.query(Bill)
            .options(joinedload(Bill.items))
            .order_by(Bill.id.desc())
            .all()
        )
        return [_to_dto(b) for b in bills]
    finally:
        session.close()


def get_bill(bill_id):
    session = get_session()
    try:
        bill = (
            session.query(Bill)
            .options(joinedload(Bill.items))
            .filter(Bill.id == bill_id)
            .first()
        )
        return _to_dto(bill) if bill else None
    finally:
        session.close()


def delete_bill(bill_id):
    """Delete a bill and put its quantities back into stock."""
    session = get_session()
    try:
        bill = session.query(Bill).filter(Bill.id == bill_id).first()
        if not bill:
            return
        for item in bill.items:
            if item.product_id:
                product = (
                    session.query(Product)
                    .filter(Product.id == item.product_id)
                    .first()
                )
                if product:
                    product.stock_quantity = (
                        product.stock_quantity or 0
                    ) + item.quantity
        session.delete(bill)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

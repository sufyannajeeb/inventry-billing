from sqlalchemy.orm import joinedload

from database.database import get_session
from database.models import Product, Category


def get_all_products():
    session = get_session()
    try:
        return (
            session.query(Product)
            .options(joinedload(Product.category))
            .filter(Product.is_active == True)
            .all()
        )
    finally:
        session.close()


def get_all_categories():
    session = get_session()
    try:
        return session.query(Category).order_by(Category.name).all()
    finally:
        session.close()


def add_category(name):
    session = get_session()
    try:
        name = (name or "").strip()
        if not name:
            raise ValueError("Category name is required.")
        existing = session.query(Category).filter(Category.name == name).first()
        if existing:
            return existing.id
        category = Category(name=name)
        session.add(category)
        session.commit()
        return category.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def add_product(name, price, stock_quantity, barcode=None, category_id=None,
                 purchase_price=0.0, gst_percent=0.0, unit="pcs", hsn_code=None):
    session = get_session()
    try:
        product = Product(
            name=name,
            price=price,
            stock_quantity=stock_quantity,
            barcode=barcode if barcode else None,
            category_id=category_id,
            purchase_price=purchase_price,
            gst_percent=gst_percent,
            unit=unit,
            hsn_code=hsn_code,
        )
        session.add(product)
        session.commit()
        return product.id
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def update_product(product_id, name, price, stock_quantity, barcode=None,
                    category_id=None, purchase_price=0.0, gst_percent=0.0,
                    unit="pcs", hsn_code=None):
    session = get_session()
    try:
        product = session.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError("Product not found")
        product.name = name
        product.price = price
        product.stock_quantity = stock_quantity
        product.barcode = barcode if barcode else None
        product.category_id = category_id
        product.purchase_price = purchase_price
        product.gst_percent = gst_percent
        product.unit = unit
        product.hsn_code = hsn_code
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def delete_product(product_id):
    """Soft delete - marks inactive instead of removing the row."""
    session = get_session()
    try:
        product = session.query(Product).filter(Product.id == product_id).first()
        if product:
            product.is_active = False
            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()
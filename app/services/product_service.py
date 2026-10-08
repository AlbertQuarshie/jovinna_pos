from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.db.database import SessionLocal
from app.db.models import Category, Product

# EAN-13 codes starting with 200-299 are reserved for in-store use, so they won't clash with
# manufacturer barcodes already printed on stock.
INTERNAL_PREFIX = "200"


class ProductError(Exception):
    pass


def list_categories() -> list[Category]:
    with SessionLocal() as session:
        return list(session.scalars(select(Category).order_by(Category.name)))


def get_or_create_category(name: str) -> int | None:
    name = name.strip()
    if not name:
        return None
    with SessionLocal() as session, session.begin():
        cat = session.scalar(select(Category).where(Category.name == name))
        if cat is None:
            cat = Category(name=name)
            session.add(cat)
            session.flush()
        return cat.id


def search_products(text: str = "", include_inactive: bool = False) -> list[Product]:
    with SessionLocal() as session:
        stmt = select(Product).options(joinedload(Product.category)).order_by(Product.name)
        if text.strip():
            like = f"%{text.strip()}%"
            stmt = stmt.where(or_(Product.name.ilike(like), Product.barcode.ilike(like)))
        if not include_inactive:
            stmt = stmt.where(Product.is_active.is_(True))
        return list(session.scalars(stmt))


def ean13_check_digit(first12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)


def generate_internal_barcode() -> str:
    """Next unused in-store EAN-13 code, e.g. 2000000000015."""
    with SessionLocal() as session:
        existing = session.scalars(
            select(Product.barcode).where(Product.barcode.like(f"{INTERNAL_PREFIX}%"))
        ).all()
    used = {int(code[3:12]) for code in existing if len(code) == 13 and code.isdigit()}
    seq = max(used, default=0) + 1
    first12 = f"{INTERNAL_PREFIX}{seq:09d}"
    return first12 + ean13_check_digit(first12)


def save_product(product_id: int | None, *, barcode: str, name: str, category_name: str,
                 cost_price: Decimal, selling_price: Decimal, stock_qty: int,
                 reorder_level: int) -> None:
    barcode, name = barcode.strip(), name.strip()
    if not barcode or not name:
        raise ProductError("Barcode and name are required.")
    if selling_price <= 0:
        raise ProductError("Selling price must be greater than zero.")
    if selling_price < cost_price:
        raise ProductError("Selling price is below cost price.")

    category_id = get_or_create_category(category_name)
    with SessionLocal() as session, session.begin():
        clash = session.scalar(select(Product).where(Product.barcode == barcode))
        if clash and clash.id != product_id:
            raise ProductError(f"Barcode {barcode} is already used by '{clash.name}'.")

        product = session.get(Product, product_id) if product_id else Product()
        product.barcode = barcode
        product.name = name
        product.category_id = category_id
        product.cost_price = cost_price
        product.selling_price = selling_price
        product.stock_qty = stock_qty
        product.reorder_level = reorder_level
        product.is_active = True
        session.add(product)


def add_stock(product_id: int, qty: int) -> None:
    if qty <= 0:
        raise ProductError("Quantity must be greater than zero.")
    with SessionLocal() as session, session.begin():
        session.get(Product, product_id).stock_qty += qty


def set_active(product_id: int, active: bool) -> None:
    with SessionLocal() as session, session.begin():
        session.get(Product, product_id).is_active = active

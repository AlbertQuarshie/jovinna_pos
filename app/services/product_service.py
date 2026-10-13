from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload

from app import config
from app.db.database import SessionLocal
from app.db.models import Category, Product
from app.services.image_service import delete_image

KEEP = object()  # save_product(image=KEEP) leaves the current photo unchanged

# EAN-13 codes starting with 200-299 are reserved for in-store use, so they won't clash with
# manufacturer barcodes already printed on stock.
INTERNAL_PREFIX = "200"


class ProductError(Exception):
    pass



def main_categories() -> list[str]:
    """Only the shop's main categories (Accessories, Stationery)."""
    return list(config.MAIN_CATEGORIES)


def category_tree() -> dict[str, list[str]]:
    """{"Accessories": ["Chargers", "Earphones"], "Stationery": [...]}, mains in shop order."""
    with SessionLocal() as session:
        mains = session.scalars(select(Category).options(selectinload(Category.children))
                                .where(Category.parent_id.is_(None))).all()
        tree = {m.name: sorted((c.name for c in m.children), key=str.lower) for m in mains}
    return {name: tree.get(name, []) for name in config.MAIN_CATEGORIES}


def _category_id(session, main: str, sub: str) -> int | None:
    """Id of `sub` under `main` (or of `main` itself when sub is blank), creating them if new."""
    main, sub = main.strip(), sub.strip()
    if main not in config.MAIN_CATEGORIES:
        raise ProductError(f"Choose a category: {' or '.join(config.MAIN_CATEGORIES)}.")
    parent = session.scalar(select(Category).where(Category.name == main, Category.parent_id.is_(None)))
    if parent is None:
        parent = Category(name=main)
        session.add(parent)
        session.flush()
    if not sub:
        return parent.id
    # Match existing subcategories ignoring capitals, so "chargers" doesn't create a second "Chargers"
    child = session.scalar(select(Category).where(Category.parent_id == parent.id,
                                                  func.lower(Category.name) == sub.lower()))
    if child is None:
        child = Category(name=sub, parent_id=parent.id)
        session.add(child)
        session.flush()
    return child.id


def search_products(text: str = "", include_inactive: bool = False) -> list[Product]:
    with SessionLocal() as session:
        stmt = (select(Product).options(joinedload(Product.category).joinedload(Category.parent))
                .order_by(Product.name))
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


def save_product(product_id: int | None, *, barcode: str, name: str, main_category: str,
                 subcategory: str = "",
                 selling_price: Decimal, stock_qty: int,
                 reorder_level: int, image: str | None | object = KEEP) -> None:
    """image: new photo file name (from image_service.import_image), None to remove it, or KEEP."""
    barcode, name = barcode.strip(), name.strip()
    if not barcode or not name:
        raise ProductError("Barcode and name are required.")
    if selling_price <= 0:
        raise ProductError("Selling price must be greater than zero.")

    with SessionLocal() as session, session.begin():
        category_id = _category_id(session, main_category, subcategory)
        clash = session.scalar(select(Product).where(Product.barcode == barcode))
        if clash and clash.id != product_id:
            raise ProductError(f"Barcode {barcode} is already used by '{clash.name}'.")

        product = session.get(Product, product_id) if product_id else Product()
        product.barcode = barcode
        product.name = name
        product.category_id = category_id
        if product.cost_price is None:
            product.cost_price = Decimal("0")  # cost prices aren't tracked
        product.selling_price = selling_price
        product.stock_qty = stock_qty
        product.reorder_level = reorder_level
        product.is_active = True
        old_image = product.image_path
        if image is not KEEP:
            product.image_path = image
        session.add(product)

    if image is not KEEP and old_image and old_image != image:
        delete_image(old_image)


def add_stock(product_id: int, qty: int) -> None:
    if qty <= 0:
        raise ProductError("Quantity must be greater than zero.")
    with SessionLocal() as session, session.begin():
        session.get(Product, product_id).stock_qty += qty


def set_active(product_id: int, active: bool) -> None:
    with SessionLocal() as session, session.begin():
        session.get(Product, product_id).is_active = active

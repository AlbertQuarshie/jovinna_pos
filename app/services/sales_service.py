from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.database import SessionLocal
from app.db.models import Category, Product, Sale, SaleItem


@dataclass
class CartLine:
    product_id: int
    barcode: str
    name: str
    unit_price: Decimal
    unit_cost: Decimal
    quantity: int
    stock_qty: int

    @property
    def line_total(self) -> Decimal:
        return self.unit_price * self.quantity


class SaleError(Exception):
    pass


def find_product(code: str) -> Product | None:
    """Look up an active product by exact barcode."""
    with SessionLocal() as session:
        return session.scalar(
            select(Product).options(joinedload(Product.category).joinedload(Category.parent))
            .where(Product.barcode == code.strip(), Product.is_active.is_(True))
        )


def complete_sale(cart: list[CartLine], amount_paid: Decimal, payment_method: str = "cash",
                  discount: Decimal = Decimal("0"), user_id: int | None = None) -> Sale:
    if not cart:
        raise SaleError("Cart is empty.")

    subtotal = sum((line.line_total for line in cart), Decimal("0"))
    total = subtotal - discount
    if amount_paid < total:
        raise SaleError(f"Amount paid ({amount_paid}) is less than total ({total}).")

    with SessionLocal() as session, session.begin():
        sale = Sale(
            user_id=user_id, subtotal=subtotal, discount=discount, total=total,
            payment_method=payment_method, amount_paid=amount_paid, change_given=amount_paid - total,
        )
        for line in cart:
            product = session.get(Product, line.product_id)
            if product.stock_qty < line.quantity:
                raise SaleError(f"Not enough stock for {product.name} (only {product.stock_qty} left).")
            product.stock_qty -= line.quantity
            sale.items.append(SaleItem(
                product_id=product.id, quantity=line.quantity, unit_price=line.unit_price,
                unit_cost=line.unit_cost, line_total=line.line_total,
            ))
        session.add(sale)
    return sale

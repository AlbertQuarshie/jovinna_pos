"""Sales and stock reports for a date range. All ranges are [start, end) — end is exclusive."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, func, select

from app.db.database import SessionLocal
from app.db.models import Product, Sale, SaleItem, User

MONEY = Numeric(12, 2)


def _d(value) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


@dataclass
class Summary:
    sales_count: int
    items_sold: int
    gross: Decimal       # before discounts
    discounts: Decimal
    revenue: Decimal     # money actually taken
    cost: Decimal
    profit: Decimal

    @property
    def average_sale(self) -> Decimal:
        return self.revenue / self.sales_count if self.sales_count else Decimal("0")

    @property
    def margin_pct(self) -> Decimal:
        return self.profit / self.revenue * 100 if self.revenue else Decimal("0")


def _in_range(start: datetime, end: datetime):
    return (Sale.created_at >= start, Sale.created_at < end)


def summary(start: datetime, end: datetime) -> Summary:
    with SessionLocal() as session:
        count, gross, discounts, revenue = session.execute(
            select(func.count(Sale.id), func.sum(Sale.subtotal, type_=MONEY),
                   func.sum(Sale.discount, type_=MONEY), func.sum(Sale.total, type_=MONEY))
            .where(*_in_range(start, end))
        ).one()
        items, cost = session.execute(
            select(func.sum(SaleItem.quantity), func.sum(SaleItem.quantity * SaleItem.unit_cost, type_=MONEY))
            .join(Sale).where(*_in_range(start, end))
        ).one()
    revenue, cost = _d(revenue), _d(cost)
    return Summary(count or 0, items or 0, _d(gross), _d(discounts), revenue, cost, revenue - cost)


def by_payment_method(start: datetime, end: datetime) -> list[tuple[str, int, Decimal]]:
    with SessionLocal() as session:
        rows = session.execute(
            select(Sale.payment_method, func.count(Sale.id), func.sum(Sale.total, type_=MONEY))
            .where(*_in_range(start, end)).group_by(Sale.payment_method).order_by(Sale.payment_method)
        ).all()
    return [(m, n, _d(t)) for m, n, t in rows]


def by_cashier(start: datetime, end: datetime) -> list[tuple[str, int, Decimal]]:
    with SessionLocal() as session:
        rows = session.execute(
            select(User.full_name, func.count(Sale.id), func.sum(Sale.total, type_=MONEY))
            .select_from(Sale).outerjoin(User, Sale.user_id == User.id)
            .where(*_in_range(start, end)).group_by(Sale.user_id).order_by(func.sum(Sale.total).desc())
        ).all()
    return [(name or "(before logins)", n, _d(t)) for name, n, t in rows]


def top_products(start: datetime, end: datetime, limit: int = 50) -> list[tuple[str, str, int, Decimal, Decimal]]:
    """(barcode, name, qty sold, revenue, profit) — best sellers first."""
    revenue = func.sum(SaleItem.line_total, type_=MONEY)
    cost = func.sum(SaleItem.quantity * SaleItem.unit_cost, type_=MONEY)
    qty = func.sum(SaleItem.quantity)
    with SessionLocal() as session:
        rows = session.execute(
            select(Product.barcode, Product.name, qty, revenue, cost)
            .select_from(SaleItem).join(Sale).join(Product)
            .where(*_in_range(start, end)).group_by(Product.id).order_by(qty.desc(), revenue.desc()).limit(limit)
        ).all()
    return [(b, n, q, _d(r), _d(r) - _d(c)) for b, n, q, r, c in rows]


def sales_list(start: datetime, end: datetime) -> list[tuple[int, datetime, str, int, Decimal, str]]:
    """(sale id, time, cashier, items, total, payment method) — newest first."""
    items = (select(SaleItem.sale_id, func.sum(SaleItem.quantity).label("qty"))
             .group_by(SaleItem.sale_id).subquery())
    with SessionLocal() as session:
        rows = session.execute(
            select(Sale.id, Sale.created_at, User.full_name, items.c.qty, Sale.total, Sale.payment_method)
            .outerjoin(User, Sale.user_id == User.id).join(items, items.c.sale_id == Sale.id)
            .where(*_in_range(start, end)).order_by(Sale.id.desc())
        ).all()
    return [(i, t, name or "—", q, _d(total), m) for i, t, name, q, total, m in rows]


def low_stock() -> list[Product]:
    with SessionLocal() as session:
        return list(session.scalars(
            select(Product).where(Product.is_active.is_(True), Product.stock_qty <= Product.reorder_level)
            .order_by(Product.stock_qty, Product.name)
        ))

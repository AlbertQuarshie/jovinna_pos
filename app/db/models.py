from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Category(Base):
    """Two levels: main categories (parent_id is NULL, e.g. Accessories) and their
    subcategories (e.g. Chargers). A product belongs to a subcategory, or directly to a main one."""
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("parent_id", "name"),)  # "Others" may exist under both mains

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), default=None)

    parent: Mapped["Category | None"] = relationship(remote_side="Category.id", back_populates="children")
    children: Mapped[list["Category"]] = relationship(back_populates="parent")
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    stock_qty: Mapped[int] = mapped_column(default=0)
    reorder_level: Mapped[int] = mapped_column(default=5)
    is_active: Mapped[bool] = mapped_column(default=True)
    image_path: Mapped[str | None] = mapped_column(String(255), default=None)  # file name in DATA_DIR/product_images

    category: Mapped[Category | None] = relationship(back_populates="products")

    # Load with joinedload(Product.category).joinedload(Category.parent) before using these
    @property
    def main_category(self) -> str:
        if self.category is None:
            return ""
        return self.category.parent.name if self.category.parent else self.category.name

    @property
    def sub_category(self) -> str:
        return self.category.name if self.category and self.category.parent else ""

    @property
    def category_label(self) -> str:
        """e.g. "Accessories › Chargers", or just "Accessories"."""
        return " › ".join(x for x in (self.main_category, self.sub_category) if x)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="cashier")  # admin | cashier
    is_active: Mapped[bool] = mapped_column(default=True)


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[str] = mapped_column(String(20), default="cash")  # cash | mobile | card
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    change_given: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    user: Mapped[User | None] = relationship()


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()

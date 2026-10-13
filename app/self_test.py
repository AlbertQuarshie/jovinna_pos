"""`JovinnaPOS.exe --self-test`: checks a build works end to end, using a throwaway data folder.

Exercises the parts most likely to break when packaged: the database, a sale, receipt and label
PDFs (ReportLab fonts), icons (qtawesome fonts), app fonts and photo import (Qt image plugins).
Writes the result to self_test.log in the throwaway folder's parent and returns 0 if all passed.
"""
import os
import sys
import traceback
from pathlib import Path


def run() -> int:
    # main.py points JOVINNA_DATA_DIR at a throwaway folder before anything else is imported
    if "JOVINNA_DATA_DIR" not in os.environ:
        raise RuntimeError("Run the self-test through main.py --self-test")
    work = Path(os.environ["JOVINNA_DATA_DIR"]).parent
    work.mkdir(parents=True, exist_ok=True)
    log_lines = []

    def check(label, fn):
        try:
            result = fn()
            log_lines.append(f"PASS {label}{f'  ({result})' if result else ''}")
            return True
        except Exception:  # noqa: BLE001
            log_lines.append(f"FAIL {label}\n{traceback.format_exc()}")
            return False

    from decimal import Decimal

    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    from app import config
    from app.ui import theme

    ok = True
    ok &= check("data folder is the test folder", lambda: str(config.DATA_DIR))
    ok &= check("fonts and theme", lambda: (theme.apply(app), f"{theme.FONT_TEXT} / {theme.FONT_MONO}")[1])
    def icons():
        assert not theme.icon("shopping-cart").pixmap(24, 24).isNull(), "icon font didn't load"
    ok &= check("icons", icons)
    ok &= check("app icon file", lambda: (config.BASE_DIR / "assets" / "icon.ico").stat().st_size)

    from app.db.database import engine, init_db
    ok &= check("database", init_db)

    from app.services import auth_service, image_service, label_service, product_service, receipt_service
    from app.services.backup_service import daily_backup
    from app.services.sales_service import CartLine, complete_sale, find_product

    def sale():
        user = auth_service.create_user("selftest", "Self Test", "test1234", "admin")
        product_service.save_product(None, barcode="2000000000015", name="Test Item", main_category="Stationery", subcategory="Test",
                                     selling_price=Decimal("50"), stock_qty=5, reorder_level=1)
        p = find_product("2000000000015")
        s = complete_sale([CartLine(p.id, p.barcode, p.name, Decimal(50), Decimal(0), 2, 5)],
                          Decimal("100"), "cash", user_id=user.id)
        assert find_product("2000000000015").stock_qty == 3
        return f"receipt #{s.id}"
    ok &= check("sale", sale)
    ok &= check("receipt PDF", lambda: receipt_service.create_receipt_pdf(1).stat().st_size)
    ok &= check("label PDF", lambda: label_service.create_labels_pdf(
        [label_service.LabelItem("2000000000015", "Test Item", Decimal(50), 3)]).stat().st_size)

    def photo():
        src = work / "photo.png"
        img = QImage(1200, 800, QImage.Format.Format_RGB32)
        img.fill(QColor("#336699"))
        img.save(str(src))
        return image_service.import_image(src)
    ok &= check("photo import", photo)
    ok &= check("backup", lambda: daily_backup().name)
    engine.dispose()

    log_lines.append("ALL PASSED" if ok else "SOME CHECKS FAILED")
    (work / "self_test.log").write_text("\n".join(log_lines), encoding="utf-8")
    print("\n".join(log_lines))
    print(f"Log: {work / 'self_test.log'}")
    return 0 if ok else 1

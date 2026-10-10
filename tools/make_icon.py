"""Build assets/icon.ico and assets/icon.png from assets/icon.svg.

Run from the project folder:  .venv\\Scripts\\python.exe tools\\make_icon.py
"""
import io
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]  # everything Windows asks for (taskbar, desktop, Explorer)


def render(renderer: QSvgRenderer, size: int) -> Image.Image:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(p)
    p.end()
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


def main():
    QGuiApplication([])
    renderer = QSvgRenderer(str(ASSETS / "icon.svg"))
    images = {s: render(renderer, s) for s in SIZES}
    images[256].save(ASSETS / "icon.png")
    images[256].save(ASSETS / "icon.ico", sizes=[(s, s) for s in SIZES],
                     append_images=[images[s] for s in SIZES if s != 256])
    print(f"Wrote {ASSETS / 'icon.ico'} ({', '.join(map(str, SIZES))} px) and icon.png")


if __name__ == "__main__":
    main()

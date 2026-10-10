"""Product photos: shrink and store a copy in the data folder, so big phone photos stay fast."""
import uuid
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QImageReader, QPainter

from app import config

IMAGES_DIR = config.DATA_DIR / "product_images"
MAX_SIZE = 480  # pixels on the longest side — plenty for a grid tile
SUPPORTED = "Images (*.jpg *.jpeg *.png *.webp *.bmp)"


class ImageError(Exception):
    pass


def image_file(name: str | None) -> Path | None:
    if not name:
        return None
    path = IMAGES_DIR / name
    return path if path.exists() else None


def import_image(source: str | Path) -> str:
    """Copy a photo into the shop's image folder (resized, as JPEG) and return its file name."""
    reader = QImageReader(str(source))
    reader.setAutoTransform(True)  # respect phone rotation (EXIF)
    image = reader.read()
    if image.isNull():
        raise ImageError(f"Couldn't open that picture: {reader.errorString()}")

    if max(image.width(), image.height()) > MAX_SIZE:
        image = image.scaled(MAX_SIZE, MAX_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    if image.hasAlphaChannel():  # JPEG has no transparency: put PNGs on white
        flat = QImage(image.size(), QImage.Format.Format_RGB32)
        flat.fill(Qt.GlobalColor.white)
        p = QPainter(flat)
        p.drawImage(0, 0, image)
        p.end()
        image = flat

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.jpg"
    if not image.save(str(IMAGES_DIR / name), "JPG", 85):
        raise ImageError("Couldn't save the picture.")
    return name


def delete_image(name: str | None) -> None:
    path = image_file(name)
    if path:
        path.unlink(missing_ok=True)

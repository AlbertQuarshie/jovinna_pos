# PyInstaller build recipe for Jovinna POS.
# Build:  .venv\Scripts\pyinstaller JovinnaPOS.spec --noconfirm
# Output: dist\JovinnaPOS\JovinnaPOS.exe (+ its _internal folder), which installer.iss packages.
import re

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

config_src = open("app/config.py", encoding="utf-8").read()
setting = lambda name: re.search(rf'^{name} = "(.+?)"', config_src, re.M).group(1)
APP_NAME, APP_VERSION, PUBLISHER = setting("APP_NAME"), setting("APP_VERSION"), setting("PUBLISHER")
version_tuple = tuple(int(x) for x in APP_VERSION.split(".")) + (0,) * (4 - len(APP_VERSION.split(".")))

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", PUBLISHER),
            StringStruct("FileDescription", APP_NAME),
            StringStruct("FileVersion", APP_VERSION),
            StringStruct("InternalName", "JovinnaPOS"),
            StringStruct("LegalCopyright", f"© {PUBLISHER}"),
            StringStruct("OriginalFilename", "JovinnaPOS.exe"),
            StringStruct("ProductName", APP_NAME),
            StringStruct("ProductVersion", APP_VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    ["main.py"],
    pathex=[],
    datas=[
        ("assets/fonts", "assets/fonts"),
        ("assets/icon.ico", "assets"),
        ("assets/icon.png", "assets"),
        *collect_data_files("qtawesome"),  # icon fonts
        *collect_data_files("reportlab"),  # PDF fonts used by receipts and labels
    ],
    # ReportLab loads barcode types and renderers by name at runtime, so list them explicitly
    hiddenimports=collect_submodules("reportlab.graphics.barcode") + collect_submodules("reportlab.pdfbase"),
    excludes=[
        "tkinter", "PyQt5", "PyQt6", "PySide2", "matplotlib", "numpy",  # (Pillow stays: ReportLab needs it)
        # Qt parts the app doesn't use (it only needs QtCore, QtGui and QtWidgets)
        "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
        "PySide6.QtPdf", "PySide6.QtNetwork", "PySide6.QtSvg",
    ],
    noarchive=False,
)

# Trim large files the app never needs: software OpenGL fallback, Qt Quick/QML, PDF viewer, and
# Qt's translations (the app's text is its own English).
UNUSED = ("opengl32sw.dll", "qt6quick", "qt6qml", "qt6pdf", "qt6opengl", "qt6network", "qt6svg",
          "qt6virtualkeyboard")
a.binaries = [b for b in a.binaries if not any(u in b[0].lower().replace("\\", "/") for u in UNUSED)]
a.datas = [d for d in a.datas if "translations" not in d[0].replace("\\", "/").split("/")]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JovinnaPOS",
    icon="assets/icon.ico",
    version=version_info,
    console=False,  # no black terminal window
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="JovinnaPOS")

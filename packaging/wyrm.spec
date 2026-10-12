# PyInstaller spec for Wyrm. Build with:  powershell -File packaging\build.ps1
from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "launch.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "wyrm" / "drivers" / "sinowealth" / "models"), "wyrm/drivers/sinowealth/models")],
    hiddenimports=["hid"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtPdf",
              "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtBluetooth"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Wyrm",
    icon=str(ROOT / "packaging" / "wyrm.ico"),
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Wyrm")

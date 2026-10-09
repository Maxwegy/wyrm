"""Render the Wyrm logo to packaging/wyrm.ico (multi-size)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from wyrm.ui.theme import logo_svg, render_svg  # noqa: E402


def png_bytes(size: int) -> bytes:
    pm = render_svg(logo_svg(), size, 1.0)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(ba)


def main(out: Path) -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [png_bytes(s) for s in sizes]
    header = (0).to_bytes(2, "little") + (1).to_bytes(2, "little") + len(sizes).to_bytes(2, "little")
    entries, offset = b"", 6 + 16 * len(sizes)
    for s, data in zip(sizes, images):
        dim = 0 if s >= 256 else s
        entries += bytes([dim, dim, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
        entries += len(data).to_bytes(4, "little") + offset.to_bytes(4, "little")
        offset += len(data)
    out.write_bytes(header + entries + b"".join(images))
    print("wrote", out)


if __name__ == "__main__":
    main(Path(__file__).resolve().parent / "wyrm.ico")

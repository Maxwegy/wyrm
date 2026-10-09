"""Wyrm's look: charcoal surfaces, one hot accent, soft corners.

Everything (palette, QSS, logo, icons) is generated here so the app ships
no third-party art.
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ACCENTS = {
    "ember":    ("#ff5a1f", "#ffb547", "Ember"),
    "frost":    ("#2fa8ff", "#8be9ff", "Frost"),
    "venom":    ("#2ed47a", "#c6ff6b", "Venom"),
    "amethyst": ("#9b5cff", "#ff7ad9", "Amethyst"),
    "blood":    ("#e0263a", "#ff7a59", "Bloodmoon"),
    "gold":     ("#e8a317", "#fff0a8", "Hoard"),
}


@dataclass
class Palette:
    bg: str = "#0c0a09"
    side: str = "#100d0c"
    surface: str = "#161211"
    surface2: str = "#1e1917"
    surface3: str = "#28211e"
    border: str = "#2e2623"
    text: str = "#f4ece7"
    muted: str = "#a29089"
    dim: str = "#6b5d57"
    accent: str = "#ff5a1f"
    accent2: str = "#ffb547"
    ok: str = "#3ddc97"
    warn: str = "#ffc247"
    bad: str = "#ff4d5e"


PAL = Palette()


def set_accent(name: str) -> None:
    a, b, _ = ACCENTS.get(name, ACCENTS["ember"])
    PAL.accent, PAL.accent2 = a, b


def qc(hexstr: str, alpha: int | None = None) -> QColor:
    c = QColor(hexstr)
    if alpha is not None:
        c.setAlpha(alpha)
    return c


def rgba(hexstr: str, a: float) -> str:
    c = QColor(hexstr)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


def app_font() -> QFont:
    f = QFont("Segoe UI Variable Text")
    if not f.exactMatch():
        f = QFont("Segoe UI")
    f.setPointSizeF(10)
    f.setStyleStrategy(QFont.PreferAntialias)
    return f


def stylesheet() -> str:
    p = PAL
    return f"""
* {{ outline: none; }}
QWidget {{ color: {p.text}; background: transparent; font-size: 10pt; }}
QMainWindow, #Root {{ background: {p.bg}; }}
#Sidebar {{ background: {p.side}; border-right: 1px solid {p.border}; }}
#Brand {{ font-size: 17pt; font-weight: 700; letter-spacing: 1px; }}
#BrandSub {{ color: {p.dim}; font-size: 8pt; letter-spacing: 2px; }}
QPushButton#Nav {{
    text-align: left; padding: 10px 14px; border-radius: 10px; border: none;
    color: {p.muted}; font-weight: 600; background: transparent;
}}
QPushButton#Nav:hover {{ background: {p.surface2}; color: {p.text}; }}
QPushButton#Nav:checked {{ background: {rgba(p.accent, 0.14)}; color: {p.text}; }}
#PageTitle {{ font-size: 20pt; font-weight: 700; }}
#PageSub {{ color: {p.muted}; }}
#Card {{ background: {p.surface}; border: 1px solid {p.border}; border-radius: 16px; }}
#CardTitle {{ font-size: 11pt; font-weight: 700; }}
#Muted {{ color: {p.muted}; }}
#Dim {{ color: {p.dim}; font-size: 9pt; }}
#Big {{ font-size: 26pt; font-weight: 700; }}
#Huge {{ font-size: 34pt; font-weight: 800; }}
#Accent {{ color: {p.accent2}; }}
#Warn {{ color: {p.warn}; }}
#Bad {{ color: {p.bad}; }}
#Ok {{ color: {p.ok}; }}
#Chip {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 11px;
    padding: 3px 10px; color: {p.muted}; font-size: 9pt; font-weight: 600;
}}
#ChipAccent {{
    background: {rgba(p.accent, 0.16)}; border: 1px solid {rgba(p.accent, 0.45)}; border-radius: 11px;
    padding: 3px 10px; color: {p.accent2}; font-size: 9pt; font-weight: 700;
}}
#ChipWarn {{
    background: {rgba(p.warn, 0.12)}; border: 1px solid {rgba(p.warn, 0.4)}; border-radius: 11px;
    padding: 3px 10px; color: {p.warn}; font-size: 9pt; font-weight: 700;
}}
QPushButton {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px;
    padding: 8px 16px; font-weight: 600; color: {p.text};
}}
QPushButton:hover {{ background: {p.surface3}; border-color: {rgba(p.accent, 0.5)}; }}
QPushButton:pressed {{ background: {p.surface}; }}
QPushButton:disabled {{ color: {p.dim}; border-color: {p.border}; background: {p.surface}; }}
QPushButton#Primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p.accent}, stop:1 {p.accent2});
    border: none; color: #140b06; font-weight: 700;
}}
QPushButton#Primary:hover {{ background: {p.accent2}; }}
QPushButton#Primary:disabled {{ background: {p.surface3}; color: {p.dim}; }}
QPushButton#Ghost {{ background: transparent; border: 1px solid transparent; color: {p.muted}; }}
QPushButton#Ghost:hover {{ color: {p.text}; background: {p.surface2}; }}
QPushButton#Danger {{ background: transparent; border: 1px solid {rgba(p.bad, 0.45)}; color: {p.bad}; }}
QPushButton#Danger:hover {{ background: {rgba(p.bad, 0.12)}; }}
QPushButton#Seg {{ border-radius: 9px; padding: 7px 14px; background: {p.surface2}; color: {p.muted}; }}
QPushButton#Seg:checked {{
    background: {rgba(p.accent, 0.18)}; border: 1px solid {rgba(p.accent, 0.7)}; color: {p.text};
}}
QPushButton#SlotRow {{
    text-align: left; padding: 9px 12px; border-radius: 10px; background: {p.surface2};
    border: 1px solid {p.border}; font-weight: 500;
}}
QPushButton#SlotRow:hover {{ border-color: {rgba(p.accent, 0.6)}; }}
QPushButton#SlotRow:checked {{ border-color: {p.accent}; background: {rgba(p.accent, 0.10)}; }}
QPushButton#EffectCard {{
    border-radius: 14px; padding: 0; background: {p.surface2}; border: 1px solid {p.border};
}}
QPushButton#EffectCard:checked {{ border: 2px solid {p.accent}; }}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 9px;
    padding: 7px 10px; selection-background-color: {p.accent}; selection-color: #120a06;
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {p.accent}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 8px; padding: 4px;
    selection-background-color: {rgba(p.accent, 0.25)};
}}
QSlider::groove:horizontal {{ height: 6px; background: {p.surface3}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p.accent}, stop:1 {p.accent2});
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {p.text}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
    border: 3px solid {p.accent};
}}
QSlider::handle:horizontal:hover {{ border-color: {p.accent2}; }}
QSlider::groove:horizontal:disabled {{ background: {p.surface2}; }}
QSlider::sub-page:horizontal:disabled {{ background: {p.dim}; }}
QListWidget, QTableWidget {{
    background: {p.surface}; border: 1px solid {p.border}; border-radius: 12px; padding: 4px;
    gridline-color: {p.border};
}}
QListWidget::item {{ border-radius: 9px; padding: 8px; margin: 2px; }}
QListWidget::item:hover {{ background: {p.surface2}; }}
QListWidget::item:selected {{ background: {rgba(p.accent, 0.16)}; color: {p.text}; }}
QTableWidget::item {{ padding: 4px; }}
QTableWidget::item:selected {{ background: {rgba(p.accent, 0.18)}; color: {p.text}; }}
QHeaderView::section {{
    background: {p.surface}; color: {p.dim}; border: none; border-bottom: 1px solid {p.border};
    padding: 6px; font-weight: 700; font-size: 8pt; text-transform: uppercase;
}}
QTableCornerButton::section {{ background: {p.surface}; border: none; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ width: 8px; background: transparent; margin: 4px 1px; }}
QScrollBar::handle:vertical {{ background: {p.surface3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p.dim}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 8px; background: transparent; }}
QScrollBar::handle:horizontal {{ background: {p.surface3}; border-radius: 4px; }}
QMenu {{
    background: {p.surface2}; border: 1px solid {p.border}; border-radius: 10px; padding: 6px;
}}
QMenu::item {{ padding: 7px 26px 7px 14px; border-radius: 7px; }}
QMenu::item:selected {{ background: {rgba(p.accent, 0.22)}; }}
QMenu::item:disabled {{ color: {p.muted}; }}
QMenu::separator {{ height: 1px; background: {p.border}; margin: 5px 8px; }}
QMenu::indicator {{ width: 14px; height: 14px; }}
QToolTip {{
    background: {p.surface3}; color: {p.text}; border: 1px solid {p.border};
    border-radius: 6px; padding: 5px 8px;
}}
QDialog {{ background: {p.bg}; }}
QMessageBox {{ background: {p.bg}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QRadioButton::indicator {{
    width: 14px; height: 14px; border-radius: 9px; border: 2px solid {p.dim}; background: {p.surface2};
}}
QRadioButton::indicator:checked {{
    border: 2px solid {p.accent};
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                stop:0 {p.accent2}, stop:0.45 {p.accent2}, stop:0.55 {p.surface2}, stop:1 {p.surface2});
}}
QRadioButton::indicator:hover {{ border-color: {p.accent2}; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px; border: 1px solid {p.dim}; background: {p.surface2};
}}
QCheckBox::indicator:checked {{ background: {p.accent}; border-color: {p.accent}; }}
QProgressBar {{
    background: {p.surface3}; border: none; border-radius: 4px; height: 8px; text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {p.accent}, stop:1 {p.accent2});
}}
"""


# --- art ----------------------------------------------------------------------
def logo_svg(accent: str | None = None, accent2: str | None = None, mono: bool = False) -> str:
    a = accent or PAL.accent
    b = accent2 or PAL.accent2
    if mono:
        a = b = "#8a7d77"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs>
 <radialGradient id="iris" cx="50%" cy="50%" r="55%">
  <stop offset="0" stop-color="{b}"/><stop offset="0.65" stop-color="{a}"/><stop offset="1" stop-color="#3a0f04"/>
 </radialGradient>
 <linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{b}"/><stop offset="1" stop-color="{a}"/>
 </linearGradient>
</defs>
<path d="M32 3 L57 17.5 L57 46.5 L32 61 L7 46.5 L7 17.5 Z" fill="#140f0d" stroke="url(#rim)" stroke-width="3"
      stroke-linejoin="round"/>
<path d="M9 32 C19 15 45 15 55 32 C45 49 19 49 9 32 Z" fill="url(#iris)"/>
<path d="M32 15.5 C27.5 24 27.5 40 32 48.5 C36.5 40 36.5 24 32 15.5 Z" fill="#0b0605"/>
<ellipse cx="38.5" cy="26" rx="3.2" ry="2.2" fill="#fff6e8" opacity="0.85"/>
</svg>"""


ICONS = {
    "dashboard": '<rect x="3" y="3" width="7" height="9" rx="1.8"/><rect x="14" y="3" width="7" height="5" rx="1.8"/>'
                 '<rect x="14" y="12" width="7" height="9" rx="1.8"/><rect x="3" y="16" width="7" height="5" rx="1.8"/>',
    "profiles": '<path d="M12 2.5 2.5 7.5 12 12.5l9.5-5z"/><path d="m2.5 12 9.5 5 9.5-5"/><path d="m2.5 16.5 9.5 5 9.5-5"/>',
    "performance": '<path d="M3.5 17.5a8.5 8.5 0 1 1 17 0"/><path d="m12 17.5 4.2-6"/><circle cx="12" cy="17.5" r="1.6"/>',
    "buttons": '<rect x="6" y="2.5" width="12" height="19" rx="6"/><path d="M12 2.5v6.5"/><path d="M6.2 9h11.6"/>',
    "lighting": '<circle cx="12" cy="12" r="3.8"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6'
                'M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/>',
    "macros": '<rect x="2.5" y="5.5" width="19" height="13" rx="2.5"/><path d="M6 9.5h1.5M10 9.5h1.5M14 9.5h1.5M18 9.5h0'
              'M6 13h12M8.5 16h7"/>',
    "settings": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/>'
                '<circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "trash": '<path d="M4 7h16M9 7V4.5h6V7M6.5 7l1 13h9l1-13"/>',
    "copy": '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9'
            'A1.5 1.5 0 0 0 5.5 16H8"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "bolt": '<path d="M13 2.5 4.5 13.5H12l-1 8 8.5-11H12z"/>',
    "record": '<circle cx="12" cy="12" r="6.5"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>',
    "up": '<path d="m6 14 6-6 6 6"/>',
    "down": '<path d="m6 10 6 6 6-6"/>',
    "app": '<rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M3 8.5h18"/>',
    "folder": '<path d="M3 7.5V18a1.5 1.5 0 0 0 1.5 1.5h15A1.5 1.5 0 0 0 21 18V9a1.5 1.5 0 0 0-1.5-1.5H12L9.5 5h-5A1.5 1.5'
              ' 0 0 0 3 6.5z"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
    "wave": '<path d="M2.5 12c2-4 4-4 6 0s4 4 6 0 4-4 6 0"/>',
}


def svg_icon(name: str, color: str | None = None, size: int = 20) -> QIcon:
    return QIcon(svg_pixmap(name, color or PAL.muted, size))


def svg_pixmap(name: str, color: str, size: int = 20) -> QPixmap:
    body = ICONS[name]
    fill = "currentColor" if name in ("record", "star", "bolt") else "none"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="{fill}" stroke="currentColor" '
           f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{body}</svg>').replace(
        "currentColor", color)
    return render_svg(svg, size)


def render_svg(svg: str, size: int, ratio: float = 2.0) -> QPixmap:
    r = QSvgRenderer(QByteArray(svg.encode()))
    px = int(size * ratio)
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p, QRectF(0, 0, px, px))
    p.end()
    pm = QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ratio)
    return pm


def logo_icon(mono: bool = False) -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(render_svg(logo_svg(mono=mono), s, 1.0))
    return icon

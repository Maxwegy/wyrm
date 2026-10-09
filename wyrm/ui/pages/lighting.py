from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QWidget

from ...core.model import EFFECT_LABELS, EFFECTS, Lighting
from ...hid.codec.settings import VERIFIED_EFFECTS
from ..theme import PAL, qc
from ..widgets import Card, ColorSwatch, button, chip, hrow, label
from .base import Page

PRESET_COLORS = [(255, 0, 0), (255, 90, 31), (255, 181, 71), (255, 255, 0), (0, 255, 0), (0, 255, 255),
                 (0, 0, 255), (155, 92, 255), (255, 0, 255), (255, 255, 255)]
RAINBOW = [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (255, 0, 255)]


def effect_color(lt: Lighting, t: float, phase: float = 0.0) -> QColor:
    """What the LEDs look like at time t (seconds) for a preview."""
    e = lt.effect
    speed = 0.25 + lt.speed * 0.35
    bright = lt.brightness / 4 if lt.brightness else 0.0
    if e == "off":
        return QColor(0, 0, 0)
    if e == "steady":
        c = lt.color
    elif e == "breathing":
        cols = lt.colors or RAINBOW
        cyc = t * speed * 0.5
        c = cols[int(cyc) % len(cols)]
        bright *= 0.5 - 0.5 * math.cos(2 * math.pi * (cyc % 1))
    elif e in ("colorful_steady",):
        c = RAINBOW[int(phase * 6.99) % 7]
    elif e == "flicker":
        c = RAINBOW[int(t * speed * 3) % 7] if int(t * speed * 6) % 2 == 0 else (0, 0, 0)
    elif e == "stars":
        r = math.sin(t * speed * 7 + phase * 40) * 0.5 + 0.5
        c = RAINBOW[int(phase * 13 + t) % 7]
        bright *= r ** 3
    elif e == "neon":
        hue = (t * speed * 60) % 360
        q = QColor.fromHsv(int(hue), 255, 255)
        c = (q.red(), q.green(), q.blue())
    else:  # streaming, tail, wave
        hue = (t * speed * 90 + phase * 360) % 360
        q = QColor.fromHsv(int(hue), 255, 255)
        c = (q.red(), q.green(), q.blue())
    return QColor(int(c[0] * bright), int(c[1] * bright), int(c[2] * bright))


class EffectPreview(QWidget):
    """A glowing mouse silhouette that plays the chosen effect."""

    def __init__(self, small: bool = False, parent=None):
        super().__init__(parent)
        self.lt = Lighting()
        self.small = small
        self.setMinimumSize(QSize(120, 80) if small else QSize(260, 300))
        self._t0 = time.monotonic()
        self.timer = QTimer(self, interval=40)
        self.timer.timeout.connect(self.update)

    def set(self, lt: Lighting):
        self.lt = lt
        self.update()

    def showEvent(self, e):
        self.timer.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = time.monotonic() - self._t0
        w, h = self.width(), self.height()
        if self.small:
            # LED strip
            n = 12
            for i in range(n):
                c = effect_color(self.lt, t, i / n)
                x = 10 + i * (w - 20) / n
                rr = QRectF(x, h / 2 - 7, (w - 20) / n - 3, 14)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(rr, 4, 4)
            return
        s = min(w / 260, h / 300)
        cx, cy = w / 2, h / 2
        body = QPainterPath(QPointF(cx, cy - 130 * s))
        body.cubicTo(QPointF(cx + 105 * s, cy - 130 * s), QPointF(cx + 95 * s, cy + 40 * s),
                     QPointF(cx + 80 * s, cy + 95 * s))
        body.cubicTo(QPointF(cx + 65 * s, cy + 140 * s), QPointF(cx - 65 * s, cy + 140 * s),
                     QPointF(cx - 80 * s, cy + 95 * s))
        body.cubicTo(QPointF(cx - 95 * s, cy + 40 * s), QPointF(cx - 105 * s, cy - 130 * s),
                     QPointF(cx, cy - 130 * s))
        # glow
        glow = effect_color(self.lt, t, 0.0)
        g = QRadialGradient(QPointF(cx, cy + 40 * s), 170 * s)
        gc = QColor(glow)
        gc.setAlpha(150)
        g.setColorAt(0, gc)
        g.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy + 40 * s), 170 * s, 170 * s)
        p.setBrush(qc(PAL.surface2))
        p.setPen(QPen(qc(PAL.border), 1.5))
        p.drawPath(body)
        # side LED strips (segmented so wave/tail effects read as motion)
        for side in (-1, 1):
            for i in range(10):
                f = i / 10
                c = effect_color(self.lt, t, f if side < 0 else 1 - f)
                y = cy - 40 * s + i * 14 * s
                x = cx + side * (88 - i * 0.6) * s
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRectF(x - 3 * s, y, 6 * s, 11 * s), 3 * s, 3 * s)
        # logo
        c = effect_color(self.lt, t, 0.5)
        p.setBrush(c)
        p.drawEllipse(QPointF(cx, cy + 70 * s), 12 * s, 12 * s)


class LightingPage(Page):
    title = "Lighting"
    subtitle = "Effects, brightness and colour"
    icon = "lighting"
    edits_profile = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        row.setSpacing(16)
        prev_card = Card()
        self.preview = EffectPreview()
        prev_card.add(self.preview)
        self.keep = button("Leave lighting as it is", "Ghost")
        self.keep.setToolTip("This profile won't touch the LEDs")
        self.keep.clicked.connect(lambda: self._set_lighting(None))
        prev_card.add(self.keep)
        row.addWidget(prev_card, 3)

        col = QVBoxLayout()
        col.setSpacing(16)
        fx = Card("Effect")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.group = QButtonGroup(self)
        self.cards = {}
        for i, e in enumerate(EFFECTS):
            b = QPushButton()
            b.setObjectName("EffectCard")
            b.setCheckable(True)
            b.setMinimumSize(128, 86)
            inner = QVBoxLayout(b)
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(4)
            mini = EffectPreview(small=True)
            mini.setMinimumSize(QSize(100, 30))
            mini.setAttribute(Qt.WA_TransparentForMouseEvents)
            mini.set(Lighting(e, 4, 3, colors=RAINBOW))
            inner.addWidget(mini)
            beta = (f' <span style="color:{PAL.warn}; font-size:7pt; font-weight:700">BETA</span>'
                    if e not in VERIFIED_EFFECTS else "")
            name = label(EFFECT_LABELS[e] + beta)
            name.setTextFormat(Qt.RichText)
            inner.addWidget(name)
            for w in b.findChildren(QWidget):
                w.setAttribute(Qt.WA_TransparentForMouseEvents)
            self.group.addButton(b, i)
            grid.addWidget(b, i // 4, i % 4)
            self.cards[e] = b
        self.group.idClicked.connect(lambda i: self._edit(effect=EFFECTS[i]))
        fx.add(grid)
        self.beta_note = label("", "Warn", wrap=True)
        fx.add(self.beta_note)
        col.addWidget(fx)

        tune = Card("Tune")
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(0, 4)
        self.bright.setPageStep(1)
        self.bright.valueChanged.connect(lambda v: self._edit(brightness=v))
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(0, 4)
        self.speed.setPageStep(1)
        self.speed.valueChanged.connect(lambda v: self._edit(speed=v))
        tune.add(hrow(label("Brightness"), self.bright))
        tune.add(hrow(label("Speed      "), self.speed))
        self.color_row = QHBoxLayout()
        self.color_row.setSpacing(8)
        self.color_lbl = label("Colour", "Dim")
        tune.add(self.color_lbl)
        self.presets = []
        for c in PRESET_COLORS:
            sw = ColorSwatch(c, 26, editable=False)
            sw.clicked.connect(lambda _=False, c=c: self._edit(color=c))
            self.presets.append(sw)
            self.color_row.addWidget(sw)
        self.custom = ColorSwatch((255, 255, 255), 26)
        self.custom.setToolTip("Custom colour")
        self.custom.colorChanged.connect(lambda c: self._edit(color=c))
        self.custom_lbl = label("  Custom", "Dim")
        self.color_row.addWidget(self.custom_lbl)
        self.color_row.addWidget(self.custom)
        self.color_row.addStretch(1)
        tune.add(self.color_row)
        self.palette_lbl = label("Breathing colours (click to change)", "Dim")
        tune.add(self.palette_lbl)
        self.pal_row = QHBoxLayout()
        self.pal = []
        for i in range(7):
            sw = ColorSwatch((255, 0, 0), 26)
            sw.colorChanged.connect(lambda c, i=i: self._set_pal(i, c))
            self.pal.append(sw)
            self.pal_row.addWidget(sw)
        self.pal_row.addStretch(1)
        tune.add(self.pal_row)
        col.addWidget(tune)
        col.addStretch(1)
        row.addLayout(col, 7)
        self.lay.addLayout(row)
        self.lay.addStretch(1)
        ctx.config_changed.connect(lambda: self.isVisible() and self.refresh())

    def _lighting(self):
        p = self.ctx.editing()
        if not p:
            return None
        if p.lighting:
            return p.lighting
        st = self.ctx.state
        return st["settings"]["lighting"] if st else Lighting()

    def refresh(self):
        p = self.ctx.editing()
        lt = self._lighting()
        if lt is None:
            return
        self.preview.set(lt)
        for w in (self.bright, self.speed):
            w.blockSignals(True)
        self.bright.setValue(lt.brightness)
        self.speed.setValue(lt.speed)
        for w in (self.bright, self.speed):
            w.blockSignals(False)
        if p.lighting:
            self.cards[lt.effect].setChecked(True)
        else:
            self.group.setExclusive(False)
            for b in self.group.buttons():
                b.setChecked(False)
            self.group.setExclusive(True)
        self.keep.setEnabled(p.lighting is not None)
        steady = lt.effect == "steady"
        breathing = lt.effect == "breathing"
        self.speed.setEnabled(lt.effect not in ("steady", "off", "colorful_steady"))
        self.bright.setEnabled(lt.effect != "off")
        for w in self.presets + [self.custom, self.color_lbl, self.custom_lbl]:
            w.setVisible(steady)
        if steady:
            self.custom.setColor(lt.color)
        self.palette_lbl.setVisible(breathing)
        for i, sw in enumerate(self.pal):
            sw.setVisible(breathing)
            if i < len(lt.colors):
                sw.setColor(lt.colors[i])
        allow = self.ctx.allow()
        beta = lt.effect not in VERIFIED_EFFECTS
        unlocked = "*" in allow or "effects" in allow
        if p.lighting is None:
            self.beta_note.setText("This profile leaves the lighting alone. Pick an effect to take control.")
        elif beta and not unlocked:
            self.beta_note.setText(f"{EFFECT_LABELS[lt.effect]} hasn't been verified on the M811 PRO yet, so Wyrm "
                                   "won't send it. Turn on experimental writes in Settings to try it.")
        elif beta:
            self.beta_note.setText("Experimental effect. If it looks wrong, pick another one.")
        else:
            self.beta_note.setText("")

    def _set_lighting(self, lt):
        self.ctx.edit(lambda p: setattr(p, "lighting", lt), self)
        self.refresh()

    def _edit(self, **kw):
        cur = self._lighting()
        if cur is None:
            return
        import copy
        lt = copy.deepcopy(cur)
        for k, v in kw.items():
            setattr(lt, k, tuple(v) if k == "color" else v)
        self._set_lighting(lt)

    def _set_pal(self, i, c):
        cur = self._lighting()
        import copy
        lt = copy.deepcopy(cur)
        cols = list(lt.colors) or list(RAINBOW)
        while len(cols) <= i:
            cols.append((255, 255, 255))
        cols[i] = tuple(c)
        lt.colors = cols
        self._set_lighting(lt)

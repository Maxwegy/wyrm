"""Clickable top + side view of the M811 PRO.

Slot indices match the firmware's button block:
0 Left, 1 Right, 2 Middle, 3 Back, 4 Forward, 5 DPI+, 6 DPI-, 7 Profile, 8..15 side keys 1..8.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from .theme import PAL, qc

SLOT_NAMES = ["Left", "Right", "Middle", "Back", "Forward", "DPI +", "DPI −", "Profile",
              "Side 1", "Side 2", "Side 3", "Side 4", "Side 5", "Side 6", "Side 7", "Side 8"]


class MouseDiagram(QWidget):
    slotClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(470, 380)
        self.selected: int | None = None
        self.hover: int | None = None
        self.labels: list[str] = [""] * 16
        self.glow = (255, 90, 31)
        self._spots: dict[int, QPainterPath] = {}
        self._body_top = QPainterPath()
        self._body_side = QPainterPath()

    def set_labels(self, labels: list[str]):
        self.labels = labels + [""] * (16 - len(labels))
        self.update()

    def set_selected(self, i: int | None):
        self.selected = i
        self.update()

    # --- geometry ---------------------------------------------------------------
    def _layout(self):
        W, H = self.width(), self.height()
        s = min(W / 470, H / 380)
        ox, oy = (W - 470 * s) / 2, (H - 380 * s) / 2

        def P(x, y):
            return QPointF(ox + x * s, oy + y * s)

        def R(x, y, w, h):
            return QRectF(ox + x * s, oy + y * s, w * s, h * s)

        # top view body (egg), centred at x=110
        cx, top, bot, hw = 110, 20, 360, 92
        body = QPainterPath(P(cx, top))
        body.cubicTo(P(cx + hw * 1.18, top), P(cx + hw * 1.05, top + 190), P(cx + hw * 0.92, top + 270))
        body.cubicTo(P(cx + hw * 0.78, bot), P(cx - hw * 0.78, bot), P(cx - hw * 0.92, top + 270))
        body.cubicTo(P(cx - hw * 1.05, top + 190), P(cx - hw * 1.18, top), P(cx, top))
        self._body_top = body
        spots = {}
        split = 145
        left = QPainterPath()
        left.addRect(R(0, 0, cx - 4, split))
        right = QPainterPath()
        right.addRect(R(cx + 4, 0, 200, split))
        spots[0] = body.intersected(left)
        spots[1] = body.intersected(right)
        wheel = QPainterPath()
        wheel.addRoundedRect(R(cx - 10, 52, 20, 50), 9 * s, 9 * s)
        spots[2] = wheel
        for i, y in ((5, 112), (6, 140)):
            pth = QPainterPath()
            pth.addRoundedRect(R(cx - 8, y, 16, 22), 6 * s, 6 * s)
            spots[i] = pth
        prof = QPainterPath()
        prof.addEllipse(R(cx - 9, 176, 18, 18))
        spots[7] = prof

        # side view
        sx, sy = 238, 70
        side = QPainterPath(P(sx, sy + 120))
        side.cubicTo(P(sx - 6, sy + 40), P(sx + 60, sy - 6), P(sx + 130, sy))
        side.cubicTo(P(sx + 190, sy + 6), P(sx + 236, sy + 50), P(sx + 226, sy + 120))
        side.cubicTo(P(sx + 220, sy + 170), P(sx + 20, sy + 182), P(sx, sy + 120))
        self._body_side = side
        for i, x in ((4, sx + 54), (3, sx + 112)):   # forward is nearer the front (left)
            pth = QPainterPath()
            pth.addRoundedRect(R(x, sy + 22, 50, 18), 8 * s, 8 * s)
            spots[i] = pth
        k = 0
        for row in range(2):
            for col in range(4):
                pth = QPainterPath()
                pth.addRoundedRect(R(sx + 40 + col * 38, sy + 58 + row * 40, 32, 32), 7 * s, 7 * s)
                spots[8 + k] = pth
                k += 1
        self._spots = spots
        self._scale = s
        self._side_caption = R(sx, sy + 196, 230, 20)
        self._top_caption = R(20, 362, 180, 18)

    def resizeEvent(self, e):
        self._layout()
        super().resizeEvent(e)

    # --- paint ------------------------------------------------------------------
    def paintEvent(self, _):
        if not self._spots:
            self._layout()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for body in (self._body_top, self._body_side):
            br = body.boundingRect()
            g = QLinearGradient(br.topLeft(), br.bottomRight())
            g.setColorAt(0, qc(PAL.surface3))
            g.setColorAt(1, qc(PAL.surface))
            p.setPen(QPen(qc(PAL.border), 1.5))
            p.setBrush(g)
            p.drawPath(body)
        # accent glow line under the top shell
        r = self._body_top.boundingRect()
        p.setPen(QPen(qc(PAL.accent, 140), 2.2))
        p.drawLine(QPointF(r.left() + r.width() * 0.22, r.bottom() - 22 * self._scale),
                   QPointF(r.right() - r.width() * 0.22, r.bottom() - 22 * self._scale))

        f = QFont(self.font())
        f.setPointSizeF(max(7.0, 8.5 * self._scale))
        f.setWeight(QFont.Bold)
        p.setFont(f)
        for i, path in self._spots.items():
            sel, hov = i == self.selected, i == self.hover
            fill = qc(PAL.accent, 120 if sel else (70 if hov else 26))
            pen = QPen(qc(PAL.accent if sel else (PAL.accent2 if hov else PAL.border)), 2 if sel else 1.2)
            p.setPen(pen)
            p.setBrush(fill)
            p.drawPath(path)
            if i >= 8:
                p.setPen(qc(PAL.text if sel or hov else PAL.muted))
                p.drawText(path.boundingRect(), Qt.AlignCenter, str(i - 7))
        p.setPen(qc(PAL.dim))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.drawText(self._top_caption, Qt.AlignCenter, "TOP")
        p.drawText(self._side_caption, Qt.AlignCenter, "LEFT SIDE")

    # --- input -------------------------------------------------------------------
    def _hit(self, pos) -> int | None:
        for i, path in self._spots.items():
            if path.contains(QPointF(pos)):
                return i
        return None

    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        if h != self.hover:
            self.hover = h
            self.setCursor(Qt.PointingHandCursor if h is not None else Qt.ArrowCursor)
            self.update()
            if h is not None:
                QToolTip.showText(e.globalPosition().toPoint(), f"{SLOT_NAMES[h]} → {self.labels[h]}", self)
            else:
                QToolTip.hideText()

    def leaveEvent(self, _):
        self.hover = None
        self.update()

    def mousePressEvent(self, e):
        h = self._hit(e.position())
        if h is not None:
            self.set_selected(h)
            self.slotClicked.emit(h)

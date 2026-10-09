from __future__ import annotations

from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ..context import AppContext


class Page(QWidget):
    title = ""
    subtitle = ""
    icon = "dashboard"
    edits_profile = False   # show the "editing profile" selector in the header

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("Root")
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(28, 8, 28, 28)
        self.lay.setSpacing(16)
        self.scroll.setWidget(inner)
        outer.addWidget(self.scroll)
        if self.edits_profile:
            ctx.editing_changed.connect(self._on_editing)

    def _on_editing(self, profile, source):
        if source is not self and self.isVisible():
            self.refresh()

    def showEvent(self, e):
        self.refresh()
        super().showEvent(e)

    def refresh(self):
        pass

from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QMessageBox, QPushButton, QWidget

from ...core.describe import describe
from ...drivers import default_buttons
from ..action_picker import ActionPicker
from ..devices import InheritBanner
from ..mouse_diagram import MouseDiagram
from ..widgets import Card, button, hrow, label
from .base import Page

DIAGRAMS = {"m811pro": MouseDiagram}


class ButtonsPage(Page):
    title = "Buttons"
    subtitle = "Click a button on the mouse or in the list to change what it does"
    icon = "buttons"
    edits_profile = True
    edits_device = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.banner = InheritBanner(ctx)
        self.lay.addWidget(self.banner)
        self.notice, self.notice_text = self.notice_card()
        self.lay.addWidget(self.notice)
        self.body = QWidget()
        row = QHBoxLayout(self.body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        self.left = Card()
        self.diagram = MouseDiagram()
        self.diagram.slotClicked.connect(self._edit)
        self.left.add(self.diagram)
        row.addWidget(self.left, 5)

        right = Card("Assignments")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(6)
        right.add(self.grid)
        self.group = QButtonGroup(self)
        self.rows: list[QPushButton] = []
        self.names: list[str] = []
        self.note = label("", "Muted", wrap=True)
        right.add(self.note)
        self.reset = button("Restore defaults", "Ghost")
        self.reset.clicked.connect(self._defaults)
        right.add(hrow(None, self.reset))
        row.addWidget(right, 6)
        self.lay.addWidget(self.body)
        self.lay.addStretch(1)
        ctx.state_changed.connect(lambda _: self.isVisible() and self.refresh())

    def _build_rows(self, names: list[str]):
        if names == self.names:
            return
        self.names = list(names)
        for b in self.rows:
            self.group.removeButton(b)
            b.deleteLater()
        self.rows = []
        per_col = (len(names) + 1) // 2 if len(names) > 8 else len(names)
        for i, _name in enumerate(names):
            b = QPushButton()
            b.setObjectName("SlotRow")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=i: self._edit(i))
            self.group.addButton(b, i)
            self.grid.addWidget(b, i % per_col, i // per_col)
            self.rows.append(b)

    def refresh(self):
        self.banner.refresh()
        dev, caps = self.ctx.current(), self.ctx.caps()
        s, _ = self.ctx.device_settings()
        if dev is None or not caps.buttons or s is None:
            self.notice_text.setText(
                "Plug in a mouse Wyrm can configure to change its buttons." if dev is None else
                f"Wyrm can't remap the {dev.short_name}'s buttons yet." if not caps.buttons else
                f"Waiting to read the {dev.short_name}'s current settings. Move it to wake it up.")
            self.notice.show()
            self.body.hide()
            return
        self.notice.hide()
        self.body.show()
        self._build_rows(caps.buttons)
        self.left.setVisible(dev.diagram in DIAGRAMS)
        acts = self.ctx.effective_buttons(s)
        labels = [describe(a, self.ctx.store.macros) for a in acts]
        self.diagram.set_labels(labels, caps.buttons)
        for i, b in enumerate(self.rows):
            b.setText(f"{caps.buttons[i]}   ·   {labels[i]}")
        self.reset.setVisible(bool(default_buttons(dev)))
        if not s.buttons:
            self.note.setText("This profile leaves the buttons as they are on the mouse. "
                              "Change one and the profile starts managing all of them.")
        elif any(a.kind in ("profile_next", "profile_prev") for a in acts):
            self.note.setText("Profile buttons cycle Wyrm profiles while Wyrm is running (in the tray).")
        else:
            self.note.setText("Tip: give one button \"Switch profile\" so you can change profiles mid-game.")

    def _edit(self, i: int):
        self.diagram.set_selected(i)
        if i < len(self.rows):
            self.rows[i].setChecked(True)
        s, _ = self.ctx.device_settings()
        if s is None or i >= len(self.names):
            return
        acts = self.ctx.effective_buttons(s)
        dlg = ActionPicker(self.names[i], acts[i], self.ctx.store.macros, self)
        if not dlg.exec():
            return
        acts[i] = dlg.result_action()
        if not any(a.kind == "mouse" and a.mouse_mask & 1 for a in acts):
            QMessageBox.warning(self, "Keep a left click",
                                "At least one button has to stay Left click, or you couldn't click anything.")
            return
        self.ctx.edit_device(lambda st: setattr(st, "buttons", acts), self)
        self.refresh()

    def _defaults(self):
        dev = self.ctx.current()
        if dev is None:
            return
        acts = default_buttons(dev)
        if not acts or QMessageBox.question(
                self, "Restore defaults",
                f"Reset all {len(acts)} buttons of the {dev.short_name} in this profile to Wyrm's defaults?") \
                != QMessageBox.Yes:
            return
        self.ctx.edit_device(lambda st: setattr(st, "buttons", acts), self)
        self.refresh()

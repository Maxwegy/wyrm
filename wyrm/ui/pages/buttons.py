from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QGridLayout, QHBoxLayout, QMessageBox, QPushButton

from ...core.describe import describe
from ...core.model import ButtonAction
from ..action_picker import ActionPicker
from ..mouse_diagram import SLOT_NAMES, MouseDiagram
from ..widgets import Card, button, hrow, label
from .base import Page


def default_layout() -> list[ButtonAction]:
    keys = [0x1E + i for i in range(8)]          # 1..8
    return ([ButtonAction.mouse(1), ButtonAction.mouse(2), ButtonAction.mouse(4), ButtonAction.mouse(8),
             ButtonAction.mouse(0x10), ButtonAction("dpi_up"), ButtonAction("dpi_down"),
             ButtonAction("profile_next")] + [ButtonAction.key(u) for u in keys])


class ButtonsPage(Page):
    title = "Buttons"
    subtitle = "Click a button on the mouse or in the list to change what it does"
    icon = "buttons"
    edits_profile = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        row.setSpacing(16)
        left = Card()
        self.diagram = MouseDiagram()
        self.diagram.slotClicked.connect(self._edit)
        left.add(self.diagram)
        row.addWidget(left, 5)

        right = Card("Assignments")
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        self.group = QButtonGroup(self)
        self.rows: list[QPushButton] = []
        for i, name in enumerate(SLOT_NAMES):
            b = QPushButton()
            b.setObjectName("SlotRow")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, i=i: self._edit(i))
            self.group.addButton(b, i)
            grid.addWidget(b, i % 8, i // 8)
            self.rows.append(b)
        right.add(grid)
        self.note = label("", "Muted", wrap=True)
        right.add(self.note)
        reset = button("Restore defaults", "Ghost")
        reset.clicked.connect(self._defaults)
        right.add(hrow(None, reset))
        row.addWidget(right, 6)
        self.lay.addLayout(row)
        self.lay.addStretch(1)
        ctx.state_changed.connect(lambda _: self.isVisible() and self.refresh())

    def refresh(self):
        p = self.ctx.editing()
        if not p:
            return
        acts = self.ctx.effective_buttons(p)
        labels = [describe(a, self.ctx.store.macros) for a in acts]
        self.diagram.set_labels(labels)
        for i, b in enumerate(self.rows):
            b.setText(f"{SLOT_NAMES[i]}   ·   {labels[i]}")
        if not p.buttons:
            self.note.setText("This profile leaves the buttons as they are on the mouse. "
                              "Change one and the profile starts managing all of them.")
        elif any(a.kind == "profile_next" or a.kind == "profile_prev" for a in acts):
            self.note.setText("Profile buttons cycle Wyrm profiles while Wyrm is running (in the tray).")
        else:
            self.note.setText("Tip: give one button \"Switch profile\" so you can change profiles mid-game.")

    def _edit(self, i: int):
        self.diagram.set_selected(i)
        self.rows[i].setChecked(True)
        p = self.ctx.editing()
        if not p:
            return
        acts = self.ctx.effective_buttons(p)
        dlg = ActionPicker(SLOT_NAMES[i], acts[i], self.ctx.store.macros, self)
        if not dlg.exec():
            return
        new = dlg.result_action()
        acts[i] = new
        if not any(a.kind == "mouse" and a.mouse_mask & 1 for a in acts):
            QMessageBox.warning(self, "Keep a left click",
                                "At least one button has to stay Left click, or you couldn't click anything.")
            return

        def fn(prof):
            prof.buttons = acts
        self.ctx.edit(fn, self)
        self.refresh()

    def _defaults(self):
        if QMessageBox.question(self, "Restore defaults",
                                "Reset all 16 buttons for this profile to Wyrm's defaults?") != QMessageBox.Yes:
            return
        self.ctx.edit(lambda p: setattr(p, "buttons", default_layout()), self)
        self.refresh()

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
                               QHeaderView, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from ...core import winapi
from ...core.model import AppRule
from ..theme import PAL, svg_icon
from ..widgets import Card, ColorSwatch, button, chip, hrow, label
from .base import Page

PROFILE_COLORS = ["#ff5a1f", "#ffb547", "#e0263a", "#ff7ad9", "#9b5cff", "#2fa8ff", "#2ed47a", "#c6ff6b", "#e8e1dc"]


class AppChooser(QDialog):
    """Pick a running app (by window)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Link a running app")
        self.setMinimumSize(520, 460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 14)
        lay.addWidget(label("Pick an app that's open right now", "CardTitle"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter…")
        lay.addWidget(self.search)
        self.list = QListWidget()
        for exe, title, _path in winapi.visible_apps():
            it = QListWidgetItem(f"{exe}\n{title[:80]}")
            it.setData(Qt.UserRole, exe)
            self.list.addItem(it)
        lay.addWidget(self.list, 1)
        self.search.textChanged.connect(self._filter)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _filter(self, text):
        t = text.lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(t not in it.text().lower())

    def exe(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None


class ProfilesPage(Page):
    title = "Profiles"
    subtitle = "One per activity. Link apps and Wyrm switches for you."
    icon = "profiles"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        row.setSpacing(16)
        self.lay.addLayout(row, 1)

        # --- list -------------------------------------------------------------
        left = Card()
        left.setFixedWidth(340)
        self.list = QListWidget()
        self.list.setMinimumHeight(360)
        self.list.currentRowChanged.connect(self._select)
        left.add(self.list)
        new = button("New", "Primary", "plus")
        new.clicked.connect(self._new)
        dup = button("", "Ghost", "copy", "Duplicate")
        dup.clicked.connect(self._dup)
        up = button("", "Ghost", "up", "Move up")
        up.clicked.connect(lambda: self._move(-1))
        down = button("", "Ghost", "down", "Move down")
        down.clicked.connect(lambda: self._move(1))
        left.add(hrow(new, dup, up, down, None))
        row.addWidget(left)

        # --- details --------------------------------------------------------
        right = QVBoxLayout()
        right.setSpacing(16)
        det = Card("Profile")
        self.name = QLineEdit()
        self.name.setPlaceholderText("Profile name")
        self.name.editingFinished.connect(self._rename)
        det.add(self.name)
        self.colors = QHBoxLayout()
        self.colors.setSpacing(8)
        self.swatches = []
        for c in PROFILE_COLORS:
            q = QColor(c)
            sw = ColorSwatch((q.red(), q.green(), q.blue()), 26, editable=False)
            sw.setCheckable(True)
            sw.clicked.connect(lambda _=False, col=c: self._set_color(col))
            self.swatches.append((c, sw))
            self.colors.addWidget(sw)
        self.colors.addStretch(1)
        det.add(self.colors)
        self.badges = QHBoxLayout()
        det.add(self.badges)
        self.activate = button("Activate now", "Primary", "bolt")
        self.activate.clicked.connect(self._activate)
        self.default = button("Make default", None, "star", "Used when no linked app is in front")
        self.default.clicked.connect(self._make_default)
        self.delete = button("Delete", "Danger", "trash")
        self.delete.clicked.connect(self._delete)
        det.add(hrow(self.activate, self.default, None, self.delete))
        right.addWidget(det)

        rules = Card("Linked apps", "When one of these is the foreground window, this profile turns on. "
                                    "Use * as a wildcard, e.g. *steam*.exe. Add a title filter to be picky "
                                    "(e.g. chrome.exe only when the title contains \"Figma\").")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["App (.exe)", "Window title contains", "Priority"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(220)
        self.table.itemChanged.connect(self._rules_edited)
        rules.add(self.table)
        add = button("Link app", "Primary", "plus")
        menu = QMenu(add)
        menu.addAction(svg_icon("app"), "From open windows…", self._add_running)
        menu.addAction(svg_icon("folder"), "Browse for an .exe…", self._add_browse)
        menu.addAction("Type a name…", self._add_typed)
        add.setMenu(menu)
        rm = button("Remove", "Ghost", "trash")
        rm.clicked.connect(self._remove_rule)
        rules.add(hrow(add, rm, None))
        right.addWidget(rules, 1)
        row.addLayout(right, 1)

        ctx.manager.profiles_changed.connect(self._reload_keep)
        ctx.manager.active_changed.connect(lambda *_: self._reload_keep())
        self._loading = False

    # --- list --------------------------------------------------------------------
    def refresh(self):
        self._reload_keep()

    def _reload_keep(self):
        cur = self._current()
        self._reload(cur.id if cur else (self.ctx.editing().id if self.ctx.editing() else None))

    def _reload(self, select_id=None):
        m = self.ctx.manager
        self.list.blockSignals(True)
        self.list.clear()
        active, default = m.active(), m.default()
        row = 0
        for i, p in enumerate(m.profiles()):
            tags = []
            if active and p.id == active.id:
                tags.append("● active")
            if default and p.id == default.id:
                tags.append("★ default")
            n = len(p.rules)
            sub = f"{n} linked app{'s' if n != 1 else ''}" + (("   " + "  ".join(tags)) if tags else "")
            it = QListWidgetItem(f"{p.name}\n{sub}")
            it.setData(Qt.UserRole, p.id)
            it.setIcon(svg_icon("record", p.accent, 14))
            self.list.addItem(it)
            if p.id == select_id:
                row = i
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(row)
            self._select(row)

    def _current(self):
        it = self.list.currentItem()
        return self.ctx.manager.get(it.data(Qt.UserRole)) if it else None

    def _select(self, _row):
        p = self._current()
        if not p:
            return
        self._loading = True
        self.name.setText(p.name)
        for c, sw in self.swatches:
            sw.setChecked(c.lower() == p.accent.lower())
            sw.update()
        while self.badges.count():
            w = self.badges.takeAt(0).widget()
            if w:
                w.deleteLater()
        m = self.ctx.manager
        is_active = m.active() and m.active().id == p.id
        is_default = m.default() and m.default().id == p.id
        if is_active:
            self.badges.addWidget(chip("Active", "ChipAccent"))
        if is_default:
            self.badges.addWidget(chip("Default", "Chip"))
        self.badges.addStretch(1)
        self.activate.setEnabled(not is_active)
        self.default.setEnabled(not is_default)
        self.delete.setEnabled(len(m.profiles()) > 1)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for r in p.rules:
            self._append_rule_row(r)
        self.table.blockSignals(False)
        self._loading = False

    def _append_rule_row(self, r: AppRule):
        i = self.table.rowCount()
        self.table.insertRow(i)
        self.table.setItem(i, 0, QTableWidgetItem(r.exe_name))
        self.table.setItem(i, 1, QTableWidgetItem(r.title_contains))
        sp = QSpinBox()
        sp.setRange(-99, 99)
        sp.setValue(r.priority)
        sp.valueChanged.connect(lambda *_: self._rules_edited())
        self.table.setCellWidget(i, 2, sp)

    # --- actions -------------------------------------------------------------------
    def _save(self, p):
        self.ctx.manager.update_profile(p, apply=False)

    def _new(self):
        name, ok = QInputDialog.getText(self, "New profile", "Name (e.g. Gaming, Work, Editing):")
        if ok and name.strip():
            base = self.ctx.manager.active()
            p = self.ctx.manager.create(name.strip(), base)
            used = {q.accent for q in self.ctx.manager.profiles()}
            p.accent = next((c for c in PROFILE_COLORS if c not in used), PROFILE_COLORS[0])
            self._save(p)
            self._reload(p.id)

    def _dup(self):
        p = self._current()
        if p:
            q = self.ctx.manager.create(f"{p.name} copy", p)
            self._reload(q.id)

    def _move(self, d):
        p = self._current()
        if p:
            self.ctx.manager.move(p.id, d)
            self._reload(p.id)

    def _rename(self):
        p = self._current()
        if p and not self._loading and self.name.text().strip() and self.name.text().strip() != p.name:
            p.name = self.name.text().strip()
            self._save(p)

    def _set_color(self, c):
        p = self._current()
        if p:
            p.accent = c
            self._save(p)
            self._select(self.list.currentRow())

    def _activate(self):
        p = self._current()
        if p:
            self.ctx.manager.switch(p.id, "manual")

    def _make_default(self):
        p = self._current()
        if p:
            self.ctx.manager.set_default(p.id)

    def _delete(self):
        p = self._current()
        if not p:
            return
        if QMessageBox.question(self, "Delete profile", f"Delete \"{p.name}\"? This can't be undone.") \
                == QMessageBox.Yes:
            self.ctx.manager.delete(p.id)

    # --- rules -----------------------------------------------------------------
    def _rules_from_table(self):
        out = []
        for i in range(self.table.rowCount()):
            exe = (self.table.item(i, 0).text() if self.table.item(i, 0) else "").strip()
            title = (self.table.item(i, 1).text() if self.table.item(i, 1) else "").strip()
            pr = self.table.cellWidget(i, 2).value() if self.table.cellWidget(i, 2) else 0
            if exe:
                out.append(AppRule(exe, title, pr))
        return out

    def _rules_edited(self, *_):
        if self._loading:
            return
        p = self._current()
        if p:
            p.rules = self._rules_from_table()
            self._save(p)

    def _add_rule(self, exe: str):
        p = self._current()
        if not p or not exe:
            return
        for q in self.ctx.manager.profiles():
            if q.id != p.id and any(r.exe_name.lower() == exe.lower() and not r.title_contains for r in q.rules):
                QMessageBox.information(self, "Already linked",
                                        f"{exe} is already linked to \"{q.name}\". The higher priority wins.")
        p.rules.append(AppRule(exe))
        self._save(p)
        self._select(self.list.currentRow())

    def _add_running(self):
        d = AppChooser(self)
        if d.exec() and d.exe():
            self._add_rule(d.exe())

    def _add_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose the game or app", "C:/", "Programs (*.exe)")
        if path:
            self._add_rule(os.path.basename(path))

    def _add_typed(self):
        exe, ok = QInputDialog.getText(self, "Link app", "Executable name (e.g. cs2.exe):")
        if ok and exe.strip():
            self._add_rule(exe.strip())

    def _remove_rule(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        if rows:
            self._rules_edited()

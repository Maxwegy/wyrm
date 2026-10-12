from __future__ import annotations

import copy
import time

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView, QInputDialog,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from ...core.keys import HID_NAMES, MOUSE_BUTTONS, VK_TO_HID
from ...core.model import Macro, MacroEvent
from ...drivers import macro_event_count
from ..theme import PAL, qc
from ..widgets import Card, Toggle, button, hrow, label
from .base import Page

QT_BUTTONS = {Qt.LeftButton: 0x01, Qt.RightButton: 0x02, Qt.MiddleButton: 0x04,
              Qt.BackButton: 0x08, Qt.ForwardButton: 0x10}
TYPE_LABEL = {"key_down": "Key down", "key_up": "Key up", "btn_down": "Button down", "btn_up": "Button up"}


def uses_macro(p, macro_id: str) -> bool:
    return bool(p) and any(a.kind == "macro" and a.macro_id == macro_id for s in p.devices.values() for a in s.buttons)


def event_name(e: MacroEvent) -> str:
    if e.type.startswith("key"):
        return HID_NAMES.get(e.code, f"{e.code:#04x}")
    return dict(MOUSE_BUTTONS).get(e.code, f"Button {e.code:#04x}")


class CapturePad(QFrame):
    """Records keys and clicks *only while it has focus*. No global hooks."""
    recorded = Signal(object)   # MacroEvent with delay placeholder, plus timestamp attr

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(110)
        self.recording = False
        self.setCursor(Qt.CrossCursor)

    def event(self, e):
        if self.recording and e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.keyPressEvent(e)
            return True
        return super().event(e)

    def _emit(self, typ, code):
        if self.recording:
            self.recorded.emit((typ, code, time.perf_counter()))

    def keyPressEvent(self, e):
        if not self.recording or e.isAutoRepeat():
            return super().keyPressEvent(e)
        u = VK_TO_HID.get(e.nativeVirtualKey())
        if u is not None:
            self._emit("key_down", u)

    def keyReleaseEvent(self, e):
        if not self.recording or e.isAutoRepeat():
            return super().keyReleaseEvent(e)
        u = VK_TO_HID.get(e.nativeVirtualKey())
        if u is not None:
            self._emit("key_up", u)

    def mousePressEvent(self, e):
        self.setFocus()
        b = QT_BUTTONS.get(e.button())
        if b:
            self._emit("btn_down", b)

    def mouseReleaseEvent(self, e):
        b = QT_BUTTONS.get(e.button())
        if b:
            self._emit("btn_up", b)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2)
        col = qc(PAL.bad) if self.recording else qc(PAL.border)
        pen = QPen(col, 2, Qt.DashLine if not self.recording else Qt.SolidLine)
        p.setPen(pen)
        p.setBrush(qc(PAL.bad, 22) if self.recording else qc(PAL.surface2))
        p.drawRoundedRect(r, 14, 14)
        p.setPen(qc(PAL.text if self.recording else PAL.muted))
        txt = ("● Recording: type and click inside this box" if self.recording else
               "Press Record, then type and click inside this box")
        p.drawText(r, Qt.AlignCenter, txt)


class MacrosPage(Page):
    title = "Macros"
    subtitle = "Record key and click sequences, then put them on a button"
    icon = "macros"
    edits_device = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        row = QHBoxLayout()
        row.setSpacing(16)
        left = Card()
        left.setFixedWidth(300)
        self.list = QListWidget()
        self.list.setMinimumHeight(380)
        self.list.currentRowChanged.connect(lambda _: self._load())
        left.add(self.list)
        new = button("New", "Primary", "plus")
        new.clicked.connect(self._new)
        ren = button("", "Ghost", "copy", "Rename")
        ren.clicked.connect(self._rename)
        rm = button("", "Ghost", "trash", "Delete")
        rm.clicked.connect(self._delete)
        left.add(hrow(new, ren, rm, None))
        row.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(16)
        rec = Card("Recorder")
        self.pad = CapturePad()
        self.pad.recorded.connect(self._on_recorded)
        rec.add(self.pad)
        self.rec_btn = button("Record", "Primary", "record")
        self.rec_btn.clicked.connect(self._toggle_record)
        self.use_timing = Toggle(True)
        self.fixed = QSpinBox()
        self.fixed.setRange(1, 60000)
        self.fixed.setValue(30)
        self.fixed.setSuffix(" ms")
        rec.add(hrow(self.rec_btn, None, label("Keep real timing"), self.use_timing, label("  else"), self.fixed))
        right.addWidget(rec)

        ev = Card("Steps")
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Action", "Key / button", "Then wait (ms)"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(240)
        self.table.itemChanged.connect(self._table_edited)
        ev.add(self.table)
        self.add_type = QComboBox()
        for k, v in TYPE_LABEL.items():
            self.add_type.addItem(v, k)
        self.add_code = QComboBox()
        self.add_code.setMinimumWidth(150)
        self.add_type.currentIndexChanged.connect(self._fill_codes)
        self._fill_codes()
        add = button("Add step", None, "plus")
        add.clicked.connect(self._add_step)
        dele = button("Remove", "Ghost", "trash")
        dele.clicked.connect(self._remove_steps)
        up = button("", "Ghost", "up")
        up.clicked.connect(lambda: self._move(-1))
        dn = button("", "Ghost", "down")
        dn.clicked.connect(lambda: self._move(1))
        clear = button("Clear", "Danger")
        clear.clicked.connect(self._clear)
        ev.add(hrow(self.add_type, self.add_code, add, None, up, dn, dele, clear))
        self.cap = QProgressBar()
        self.cap_lbl = label("", "Dim")
        ev.add(hrow(self.cap_lbl, self.cap))
        self.cap_note = label("", "Muted", wrap=True)
        ev.add(self.cap_note)
        right.addWidget(ev, 1)
        row.addLayout(right, 1)
        self.lay.addLayout(row)
        self._recording: list = []
        self._loading = False

    # --- list ------------------------------------------------------------------------
    def refresh(self):
        cur = self._current()
        self.list.blockSignals(True)
        self.list.clear()
        sel = 0
        for i, m in enumerate(sorted(self.ctx.store.macros.values(), key=lambda m: m.name.lower())):
            it = QListWidgetItem(f"{m.name}\n{len(m.events)} steps")
            it.setData(Qt.UserRole, m.id)
            self.list.addItem(it)
            if cur and m.id == cur.id:
                sel = i
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(sel)
        self._load()

    def _current(self) -> Macro | None:
        it = self.list.currentItem()
        return self.ctx.store.macros.get(it.data(Qt.UserRole)) if it else None

    def _new(self):
        name, ok = QInputDialog.getText(self, "New macro", "Name:")
        if ok and name.strip():
            m = Macro(name=name.strip())
            self.ctx.store.save_macro(m)
            self.refresh()
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) == m.id:
                    self.list.setCurrentRow(i)

    def _rename(self):
        m = self._current()
        if m:
            name, ok = QInputDialog.getText(self, "Rename macro", "Name:", text=m.name)
            if ok and name.strip():
                m.name = name.strip()
                self._save(m)

    def _delete(self):
        m = self._current()
        if not m:
            return
        used = [p.name for p in self.ctx.manager.profiles() if uses_macro(p, m.id)]
        extra = f"\n\nIt's on a button in: {', '.join(used)}. Those buttons will be disabled." if used else ""
        if QMessageBox.question(self, "Delete macro", f"Delete \"{m.name}\"?{extra}") == QMessageBox.Yes:
            self.ctx.store.delete_macro(m.id)
            self.refresh()
            self.ctx.manager.apply_active(user=True)

    def _save(self, m: Macro):
        self.ctx.store.save_macro(m)
        # macros live on the mouse per button: re-apply if the active profile uses it
        p = self.ctx.manager.active()
        if p and (uses_macro(p, m.id) or uses_macro(self.ctx.manager.default(), m.id)):
            self.ctx.manager.update_profile(p)
        it = self.list.currentItem()
        if it:
            it.setText(f"{m.name}\n{len(m.events)} steps")

    # --- table ------------------------------------------------------------------------
    def _load(self):
        m = self._current()
        self._loading = True
        self.table.setRowCount(0)
        for e in (m.events if m else []):
            self._append_row(e)
        self._loading = False
        self._update_capacity(m)
        for w in (self.pad, self.rec_btn, self.table):
            w.setEnabled(m is not None)

    def _append_row(self, e: MacroEvent):
        i = self.table.rowCount()
        self.table.insertRow(i)
        a = QTableWidgetItem(TYPE_LABEL[e.type])
        a.setFlags(a.flags() & ~Qt.ItemIsEditable)
        b = QTableWidgetItem(event_name(e))
        b.setFlags(b.flags() & ~Qt.ItemIsEditable)
        c = QTableWidgetItem(str(e.delay_ms))
        a.setData(Qt.UserRole, (e.type, e.code))
        self.table.setItem(i, 0, a)
        self.table.setItem(i, 1, b)
        self.table.setItem(i, 2, c)

    def _events_from_table(self) -> list[MacroEvent]:
        out = []
        for i in range(self.table.rowCount()):
            typ, code = self.table.item(i, 0).data(Qt.UserRole)
            try:
                d = max(1, min(60000, int(self.table.item(i, 2).text())))
            except ValueError:
                d = 10
            out.append(MacroEvent(typ, code, d))
        return out

    def _table_edited(self, *_):
        if self._loading:
            return
        m = self._current()
        if m:
            m.events = self._events_from_table()
            self._save(m)
            self._update_capacity(m)

    def _update_capacity(self, m):
        dev = self.ctx.current()
        room = dev.caps.macro_max_events if dev else 0
        for w in (self.cap, self.cap_lbl):
            w.setVisible(bool(room))
        self.cap_note.setText("" if room else
                              f"The {dev.short_name} can't store macros, so they can't go on its buttons yet. "
                              "They stay in your library for mice that can." if dev else
                              "Macros are stored on the mouse. Plug in one that supports them to put them on buttons.")
        self.cap_note.setVisible(not room)
        if room:
            n = macro_event_count(dev, m.events) if m and m.events else 0
            self.cap.setRange(0, room)
            self.cap.setValue(min(n, room))
            self.cap_lbl.setText(f"{n} / {room} slots on the {dev.short_name}")

    def _fill_codes(self):
        self.add_code.clear()
        if self.add_type.currentData().startswith("key"):
            for u, n in sorted(HID_NAMES.items()):
                self.add_code.addItem(n, u)
        else:
            for bit, n in MOUSE_BUTTONS:
                self.add_code.addItem(n, bit)

    def _add_step(self):
        m = self._current()
        if not m:
            return
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        at = rows[-1] + 1 if rows else len(m.events)
        m.events.insert(at, MacroEvent(self.add_type.currentData(), self.add_code.currentData(), 30))
        self._save(m)
        self._load()
        self.table.selectRow(at)

    def _remove_steps(self):
        m = self._current()
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if m and rows:
            for r in rows:
                del m.events[r]
            self._save(m)
            self._load()

    def _move(self, d):
        m = self._current()
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        if not m or len(rows) != 1:
            return
        i, j = rows[0], rows[0] + d
        if 0 <= j < len(m.events):
            m.events[i], m.events[j] = m.events[j], m.events[i]
            self._save(m)
            self._load()
            self.table.selectRow(j)

    def _clear(self):
        m = self._current()
        if m and m.events and QMessageBox.question(self, "Clear", "Remove every step?") == QMessageBox.Yes:
            m.events = []
            self._save(m)
            self._load()

    # --- recording ------------------------------------------------------------------
    def _toggle_record(self):
        m = self._current()
        if not m:
            return
        if not self.pad.recording:
            self._recording = []
            self._loading = True
            self.table.setRowCount(0)
            self._loading = False
            self.pad.recording = True
            self.pad.setFocus()
            self.rec_btn.setText("Stop")
        else:
            self.pad.recording = False
            self.rec_btn.setText("Record")
            evs = []
            for k, (typ, code, ts) in enumerate(self._recording):
                if self.use_timing.isChecked() and k + 1 < len(self._recording):
                    d = int(round((self._recording[k + 1][2] - ts) * 1000))
                else:
                    d = self.fixed.value()
                evs.append(MacroEvent(typ, code, max(1, d)))
            if evs:
                m.events = evs
                self._save(m)
            self._load()
        self.pad.update()

    def _on_recorded(self, item):
        self._recording.append(item)
        typ, code, _ = item
        self._loading = True
        self._append_row(MacroEvent(typ, code, 0))
        self._loading = False
        self.table.scrollToBottom()


__all__ = ["MacrosPage", "copy"]

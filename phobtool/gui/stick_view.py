"""Affichage d'un stick : gate, encoches, position live, cible et traînée."""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..calibration import notch_target_xy

RANGE = 128.0  # unités brutes (-128..127)


class StickView(QWidget):
    def __init__(self, title: str, color: str = "#b9a6ff", parent=None):
        super().__init__(parent)
        self.title = title
        self.color = QColor(color)
        self.pos: Optional[tuple[float, float]] = None
        self.target: Optional[tuple[float, float]] = None
        self.highlight_notch: Optional[int] = None
        self.trail: deque = deque(maxlen=90)
        self.subtitle = ""
        self.setMinimumSize(240, 270)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_state(self, pos: Optional[tuple[float, float]], target=None, highlight=None, subtitle=""):
        self.pos = pos
        self.target = target
        self.highlight_notch = highlight
        self.subtitle = subtitle
        if pos is not None:
            self.trail.append(pos)
        self.update()

    def clear_trail(self):
        self.trail.clear()
        self.update()

    # ------------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        top = 26
        bottom = 30
        size = min(w, h - top - bottom) - 8
        cx, cy = w / 2, top + (h - top - bottom) / 2
        rad = size / 2

        def to_px(x: float, y: float) -> QPointF:
            return QPointF(cx + x / RANGE * rad, cy - y / RANGE * rad)

        pal = self.palette()
        fg = pal.windowText().color()
        dim = QColor(fg)
        dim.setAlpha(60)

        # titre
        p.setPen(fg)
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, w, top), Qt.AlignCenter, self.title)

        # fond + gate octogonale théorique (encoches à ±100 unités firmware)
        p.setPen(QPen(dim, 1))
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        gate = QPainterPath()
        for i in range(0, 16, 2):
            pt = to_px(*notch_target_xy(i))
            gate.moveTo(pt) if i == 0 else gate.lineTo(pt)
        gate.closeSubpath()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(dim, 1.5))
        p.drawPath(gate)
        p.drawLine(to_px(-RANGE, 0), to_px(RANGE, 0))
        p.drawLine(to_px(0, -RANGE), to_px(0, RANGE))

        # encoches
        for i in range(16):
            pt = to_px(*notch_target_xy(i))
            r = 4 if i % 2 == 0 else 2.5
            if self.highlight_notch == i:
                p.setPen(QPen(QColor("#ffd34d"), 2))
                p.setBrush(QColor(255, 211, 77, 90))
                r = 9
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(dim)
            p.drawEllipse(pt, r, r)

        # traînée
        if len(self.trail) > 1:
            col = QColor(self.color)
            n = len(self.trail)
            for i, (a, b) in enumerate(zip(list(self.trail)[:-1], list(self.trail)[1:])):
                col.setAlpha(int(20 + 120 * i / n))
                p.setPen(QPen(col, 2))
                p.drawLine(to_px(*a), to_px(*b))

        # cible
        if self.target is not None:
            t = to_px(*self.target)
            p.setPen(QPen(QColor("#ffd34d"), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(t, 11, 11)
            p.drawLine(QPointF(t.x() - 16, t.y()), QPointF(t.x() + 16, t.y()))
            p.drawLine(QPointF(t.x(), t.y() - 16), QPointF(t.x(), t.y() + 16))

        # position
        if self.pos is not None:
            pt = to_px(*self.pos)
            p.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
            p.setBrush(self.color)
            p.drawEllipse(pt, 7, 7)

        # légende
        p.setPen(fg)
        p.setFont(self.font())
        if self.pos is not None:
            x, y = self.pos
            ang = math.degrees(math.atan2(y, x)) % 360
            mag = math.hypot(x, y)
            txt = f"x {x:+4.0f}   y {y:+4.0f}   {ang:5.1f}°   r {mag:3.0f}"
        else:
            txt = "—"
        if self.subtitle:
            txt = f"{txt}\n{self.subtitle}" if self.pos is not None else self.subtitle
        p.drawText(QRectF(0, h - bottom, w, bottom), Qt.AlignCenter, txt)
        p.end()


class TriggerBar(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.label = label
        self.value = 0
        self.digital = False
        self.setMinimumSize(36, 120)

    def set_value(self, v: int, digital: bool):
        self.value, self.digital = v, digital
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        fg = self.palette().windowText().color()
        bar = QRectF(w / 2 - 9, 18, 18, h - 40)
        p.setPen(QPen(fg, 1))
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRoundedRect(bar, 4, 4)
        fill = bar.height() * self.value / 255
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffd34d") if self.digital else QColor("#8f7bea"))
        p.drawRoundedRect(QRectF(bar.left(), bar.bottom() - fill, bar.width(), fill), 4, 4)
        p.setPen(fg)
        p.drawText(QRectF(0, 0, w, 16), Qt.AlignCenter, self.label)
        p.drawText(QRectF(0, h - 20, w, 20), Qt.AlignCenter, str(self.value))
        p.end()

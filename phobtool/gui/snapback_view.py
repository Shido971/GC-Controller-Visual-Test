"""Graphe temporel d'un test de snapback (façon oscilloscope GTS)."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..snapback import MELEE_DEADZONE, TRIGGER_RANGE, SnapbackResult

GOOD = QColor("#5fd38d")
BAD = QColor("#ff6b6b")
MAIN = QColor("#b9a6ff")
OTHER = QColor(255, 211, 77, 110)


class SnapbackPlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: Optional[SnapbackResult] = None
        self.placeholder = "Pousse le stick à fond, maintiens, puis lâche-le d'un coup."
        self.setMinimumSize(420, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_result(self, r: Optional[SnapbackResult]):
        self.result = r
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fg = self.palette().windowText().color()
        dim = QColor(fg)
        dim.setAlpha(70)
        w, h = self.width(), self.height()
        left, right, top, bottom = 46, 12, 12, 30
        plot = QRectF(left, top, w - left - right, h - top - bottom)

        p.setPen(QPen(dim, 1))
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawRect(plot)

        def y_px(v: float) -> float:
            return plot.center().y() - v / 128.0 * plot.height() / 2

        # zones et seuils
        dz = QRectF(plot.left(), y_px(MELEE_DEADZONE + 0.5), plot.width(),
                    y_px(-MELEE_DEADZONE - 0.5) - y_px(MELEE_DEADZONE + 0.5))
        p.fillRect(dz, QColor(95, 211, 141, 28))
        small = QFont(self.font())
        small.setPointSizeF(max(7.0, small.pointSizeF() - 1))
        p.setFont(small)
        for v, col, style in ((0, dim, Qt.SolidLine),
                              (23, GOOD, Qt.DashLine), (-23, GOOD, Qt.DashLine),
                              (TRIGGER_RANGE, dim, Qt.DotLine), (-TRIGGER_RANGE, dim, Qt.DotLine),
                              (80, dim, Qt.DotLine), (-80, dim, Qt.DotLine)):
            p.setPen(QPen(col, 1, style))
            p.drawLine(QPointF(plot.left(), y_px(v)), QPointF(plot.right(), y_px(v)))
            p.setPen(col if v else fg)
            p.drawText(QRectF(0, y_px(v) - 8, left - 6, 16), Qt.AlignRight | Qt.AlignVCenter, f"{v:+d}" if v else "0")

        r = self.result
        if not r or len(r.samples) < 2:
            p.setPen(fg)
            p.setFont(self.font())
            p.drawText(plot, Qt.AlignCenter | Qt.TextWordWrap, self.placeholder)
            p.end()
            return

        t_start = r.samples[0].t
        t_end = r.samples[-1].t
        span = max(t_end - t_start, 1e-3)

        def x_px(t: float) -> float:
            return plot.left() + (t - t_start) / span * plot.width()

        # graduation temporelle (ms depuis le début du retour)
        p.setPen(dim)
        step = 10 if span * 1000 <= 150 else 25 if span * 1000 <= 400 else 100
        ms = -int(((r.t0 - t_start) * 1000) // step) * step
        while ms <= (t_end - r.t0) * 1000:
            x = x_px(r.t0 + ms / 1000)
            if plot.left() <= x <= plot.right():
                p.setPen(QPen(dim, 1, Qt.DotLine))
                p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
                p.setPen(fg)
                p.drawText(QRectF(x - 30, plot.bottom() + 2, 60, 14), Qt.AlignCenter, f"{ms:d} ms")
            ms += step

        # instant du lâcher
        p.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.DashLine))
        p.drawLine(QPointF(x_px(r.t0), plot.top()), QPointF(x_px(r.t0), plot.bottom()))

        other_axis = "y" if r.axis == "x" else "x"
        for axis, col, width in ((other_axis, OTHER, 1.5), (r.axis, MAIN, 2.2)):
            vals = r.values(axis)
            path = QPainterPath()
            for i, (s, v) in enumerate(zip(r.samples, vals)):
                pt = QPointF(x_px(s.t), y_px(v))
                path.moveTo(pt) if i == 0 else path.lineTo(pt)
            p.setPen(QPen(col, width))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
            if axis == r.axis and len(vals) <= 400:
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                for s, v in zip(r.samples, vals):
                    p.drawEllipse(QPointF(x_px(s.t), y_px(v)), 2.2, 2.2)

        # pic de rebond
        if r.overshoot:
            vals = r.values()
            i = vals.index(r.overshoot)
            pt = QPointF(x_px(r.samples[i].t), y_px(r.overshoot))
            col = GOOD if r.passed else BAD
            p.setPen(QPen(col, 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(pt, 7, 7)
            p.setPen(col)
            f = QFont(self.font())
            f.setBold(True)
            p.setFont(f)
            off = 14 if r.overshoot < 0 else -26
            p.drawText(QRectF(pt.x() - 60, pt.y() + off, 120, 14), Qt.AlignCenter, f"rebond {r.overshoot:+d}")

        # légende
        p.setFont(small)
        p.setPen(MAIN)
        p.drawText(QRectF(plot.right() - 200, plot.top() + 4, 194, 14), Qt.AlignRight,
                   f"axe {r.axis.upper()} (lâcher)")
        p.setPen(OTHER)
        p.drawText(QRectF(plot.right() - 200, plot.top() + 18, 194, 14), Qt.AlignRight,
                   f"axe {other_axis.upper()}")
        p.end()

"""Decorative divider: ink line with a small wax-red diamond in the middle."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QWidget

from . import theme


class Ornament(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, mid = self.width(), self.height() / 2
        ink = QColor(theme.MUTED)
        for x0, x1 in ((8, w / 2 - 14), (w / 2 + 14, w - 8)):
            g = QLinearGradient(x0, 0, x1, 0)
            faded = QColor(ink)
            faded.setAlpha(0)
            ink.setAlpha(170)
            left_side = x0 < w / 2
            g.setColorAt(0, faded if left_side else ink)
            g.setColorAt(1, ink if left_side else faded)
            p.setPen(QPen(g, 1))
            p.drawLine(QPointF(x0, mid), QPointF(x1, mid))
        c = QPointF(w / 2, mid)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.ACCENT))
        p.drawPolygon(QPolygonF([c + QPointF(0, -5), c + QPointF(5, 0), c + QPointF(0, 5), c + QPointF(-5, 0)]))
        p.setBrush(QColor(theme.MUTED))
        for dx in (-10, 10):
            p.drawEllipse(c + QPointF(dx, 0), 1.6, 1.6)
        p.end()

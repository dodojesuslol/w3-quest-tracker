"""Container widget painted as an unrolled parchment scroll on a dark desk."""

from __future__ import annotations

import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from . import theme

ROLL_H = 36          # diameter of the rolled ends
SIDE = 26            # desk visible left/right of the sheet
KNOB_W = 18          # wooden knob sticking out of each roll end


class ScrollFrame(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._texture = QPixmap(str(theme.TEXTURE))
        rng = random.Random(7)  # deterministic ragged edge
        self._edge = [rng.uniform(-1, 1) for _ in range(64)]
        self.setContentsMargins(SIDE + 30, ROLL_H + 16, SIDE + 30, ROLL_H + 14)
        self.setAttribute(Qt.WA_StyledBackground, False)

    # ------------------------------------------------------------------ paint

    def _ragged(self, t: float, amp: float) -> float:
        """Smooth pseudo-random offset along an edge, t in [0, 1]."""
        x = t * (len(self._edge) - 1)
        i = int(x)
        f = x - i
        a = self._edge[i]
        b = self._edge[min(i + 1, len(self._edge) - 1)]
        f = f * f * (3 - 2 * f)
        return (a + (b - a) * f) * amp + math.sin(t * 37) * amp * 0.25

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # desk
        desk = QRadialGradient(QPointF(w / 2, h / 2), max(w, h) * 0.75)
        desk.setColorAt(0, QColor("#3a2c1f"))
        desk.setColorAt(1, QColor("#1c150f"))
        p.fillRect(self.rect(), desk)

        top = ROLL_H * 0.55
        bottom = h - ROLL_H * 0.55
        left, right = SIDE, w - SIDE

        # sheet with slightly ragged left/right edges
        path = QPainterPath()
        path.moveTo(left, top)
        steps = 40
        path.lineTo(right, top)
        for s in range(steps + 1):
            t = s / steps
            path.lineTo(right + self._ragged(t, 2.5), top + (bottom - top) * t)
        path.lineTo(left, bottom)
        for s in range(steps, -1, -1):
            t = s / steps
            path.lineTo(left + self._ragged(1 - t, 2.5), top + (bottom - top) * t)
        path.closeSubpath()

        # drop shadow
        p.save()
        p.translate(4, 6)
        p.fillPath(path, QColor(0, 0, 0, 90))
        p.restore()

        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(left - 4, top, right - left + 8, bottom - top), QBrush(self._texture))
        # burnt / aged edges: darken towards the border
        edge = 60
        for x0, x1, flip in ((left - 4, left + edge, False), (right - edge, right + 4, True)):
            g = QLinearGradient(x0, 0, x1, 0)
            c_out, c_in = QColor(92, 58, 22, 150), QColor(92, 58, 22, 0)
            g.setColorAt(0, c_in if flip else c_out)
            g.setColorAt(1, c_out if flip else c_in)
            p.fillRect(QRectF(x0, top, x1 - x0, bottom - top), g)
        for y0, y1, flip in ((top, top + 40, False), (bottom - 40, bottom, True)):
            g = QLinearGradient(0, y0, 0, y1)
            c_out, c_in = QColor(70, 45, 18, 120), QColor(70, 45, 18, 0)
            g.setColorAt(0, c_in if flip else c_out)
            g.setColorAt(1, c_out if flip else c_in)
            p.fillRect(QRectF(left - 4, y0, right - left + 8, y1 - y0), g)
        # a few soft stains
        rng = random.Random(3)
        for _ in range(5):
            cx, cy = rng.uniform(left, right), rng.uniform(top, bottom)
            r = rng.uniform(40, 120)
            stain = QRadialGradient(QPointF(cx, cy), r)
            stain.setColorAt(0, QColor(140, 100, 50, 22))
            stain.setColorAt(1, QColor(140, 100, 50, 0))
            p.fillRect(QRectF(cx - r, cy - r, 2 * r, 2 * r), stain)
        p.restore()

        self._paint_roll(p, left - 6, right + 6, 0)
        self._paint_roll(p, left - 6, right + 6, h - ROLL_H)
        p.end()

    def _paint_roll(self, p: QPainter, x0: float, x1: float, y: float) -> None:
        rect = QRectF(x0, y, x1 - x0, ROLL_H)
        g = QLinearGradient(0, y, 0, y + ROLL_H)
        g.setColorAt(0.0, QColor("#8f7448"))
        g.setColorAt(0.25, QColor("#f0e2bf"))
        g.setColorAt(0.5, QColor("#d9c193"))
        g.setColorAt(0.85, QColor("#9b7d4d"))
        g.setColorAt(1.0, QColor("#5c4425"))
        p.setPen(QPen(QColor("#4a361d"), 1))
        p.setBrush(g)
        p.drawRoundedRect(rect, ROLL_H / 2, ROLL_H / 2)
        # paper layers on the roll
        p.setPen(QPen(QColor(90, 65, 30, 70), 1))
        for k in (0.35, 0.62):
            p.drawLine(QPointF(x0 + ROLL_H / 2, y + ROLL_H * k), QPointF(x1 - ROLL_H / 2, y + ROLL_H * k))
        # wooden knobs
        for kx in (x0 - KNOB_W + 4, x1 - 4):
            kr = QRectF(kx, y + 3, KNOB_W, ROLL_H - 6)
            wood = QLinearGradient(0, kr.top(), 0, kr.bottom())
            wood.setColorAt(0, QColor("#7a4a22"))
            wood.setColorAt(0.4, QColor("#b07a43"))
            wood.setColorAt(1, QColor("#3d230e"))
            p.setPen(QPen(QColor("#2a180a"), 1))
            p.setBrush(wood)
            p.drawRoundedRect(kr, 5, 5)

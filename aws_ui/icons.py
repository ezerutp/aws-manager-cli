"""Icons drawn at runtime, so the app ships no binary assets.

El glifo son dos unidades de rack apiladas: es lo que gestiona esta app (bastiones
EC2) y se lee igual a 16 px que a 256, sin depender de detalle fino.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)

from .theme import Palette


CANVAS = 64
ICON_SIZES = (16, 22, 24, 32, 48, 64)

# Las dos unidades del rack, en coordenadas del canvas de 64x64.
UNITS = (QRectF(17, 20, 30, 11), QRectF(17, 36, 30, 11))
LED_RADIUS = 2.4


def _render(size: int, palette: Palette) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = size / CANVAS
    painter.scale(scale, scale)

    frame = QRectF(3, 3, CANVAS - 6, CANVAS - 6)
    gradient = QLinearGradient(QPointF(frame.left(), frame.top()),
                               QPointF(frame.right(), frame.bottom()))
    gradient.setColorAt(0.0, QColor(palette.accent))
    gradient.setColorAt(1.0, QColor(palette.success))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(frame, 17, 17)

    stroke = QColor("#ffffff")
    pen = QPen(stroke)
    pen.setWidthF(4.5)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for unit in UNITS:
        painter.drawRoundedRect(unit, 3.5, 3.5)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(stroke)
    for unit in UNITS:
        center = QPointF(unit.left() + 7.5, unit.center().y())
        painter.drawEllipse(center, LED_RADIUS, LED_RADIUS)

    painter.end()
    return pixmap


def app_icon(palette: Palette) -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(_render(size, palette))
    return icon


def icon_pixmap(palette: Palette, size: int) -> QPixmap:
    """Rendered at exactly `size`; QIcon.pixmap() would not scale past 64 px."""
    return _render(size, palette)

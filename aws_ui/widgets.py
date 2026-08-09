"""Small custom widgets: status dots, pills, cards, sidebar rows and progress.

Casi todo viene de la UI de proxy-local. Lo que no está es el `ToggleSwitch`: acá
no hay ningún estado booleano que encender y apagar, así que sería código muerto.
Lo que se agrega son las filas de dos niveles del árbol de entornos y el panel de
progreso, que ese CLI no necesitaba porque ninguna operación duraba más de 5 s.
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import MONO_FONTS, Palette


class StatusDot(QWidget):
    """A dot that glows when whatever it describes is live."""

    def __init__(
        self,
        palette: Palette,
        diameter: int = 9,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._diameter = diameter
        self._active = False
        self._tone = "success"
        span = diameter + 8
        self.setFixedSize(span, span)

    def apply_palette(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_active(self, active: bool, tone: str = "success") -> None:
        if active != self._active or tone != self._tone:
            self._active = active
            self._tone = tone
            self.update()

    def _color(self) -> QColor:
        return QColor({
            "success": self._palette.success,
            "warning": self._palette.warning,
            "danger": self._palette.danger,
            "accent": self._palette.accent,
        }.get(self._tone, self._palette.success))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.width() / 2
        radius = self._diameter / 2

        if self._active:
            halo = self._color()
            halo.setAlpha(55)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QRectF(center - radius - 4, center - radius - 4,
                                       self._diameter + 8, self._diameter + 8))
            painter.setBrush(self._color())
            painter.drawEllipse(QRectF(center - radius, center - radius,
                                       self._diameter, self._diameter))
            return

        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = painter.pen()
        pen.setColor(QColor(self._palette.faint))
        pen.setWidthF(1.4)
        painter.setPen(pen)
        painter.drawEllipse(QRectF(center - radius, center - radius,
                                   self._diameter, self._diameter))


class Pill(QLabel):
    """Small status label. `tone` drives the colors from the stylesheet."""

    def __init__(self, text: str = "", tone: str = "off", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class ElidingLabel(QLabel):
    """A label that elides its middle instead of stretching the layout."""

    def __init__(
        self,
        text: str = "",
        object_name: str = "FieldValue",
        selectable: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        if selectable:
            # Selectable text swallows clicks, so it is opt-out for labels that sit
            # inside something clickable.
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.set_full_text(text)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text if text else "")
        self._update_elided()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._update_elided()

    def _update_elided(self) -> None:
        metrics = QFontMetrics(self.font())
        available = max(self.width() - 2, 40)
        super().setText(
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideMiddle, available)
        )


class Card(QFrame):
    """Bordered surface with an optional uppercase title."""

    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 16)
        outer.setSpacing(12)
        if title:
            label = QLabel(title)
            label.setObjectName("CardTitle")
            outer.addWidget(label)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        # El cuerpo se queda con el alto sobrante; si no, una tarjeta con stretch
        # crece pero su contenido se queda en el tamaño mínimo.
        outer.addLayout(self.body, 1)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)


def field_row(
    label_text: str,
    value: str,
    *,
    muted: bool = False,
    trailing: QWidget | None = None,
) -> tuple[QWidget, ElidingLabel]:
    """A `label  value` line, optionally with a control at the right end."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(14)

    label = QLabel(label_text)
    label.setObjectName("FieldLabel")
    label.setFixedWidth(104)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    value_label = ElidingLabel(
        value,
        object_name="FieldValueMuted" if muted else "FieldValue",
    )
    layout.addWidget(label)
    layout.addWidget(value_label, 1)
    if trailing is not None:
        layout.addWidget(trailing, 0)
    return row, value_label


def separator() -> QFrame:
    line = QFrame()
    line.setObjectName("Separator")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


class _ClickableRow(QFrame):
    """Base for sidebar rows: one hit target, no dead zones."""

    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarItem")
        self.key = key
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _claim_clicks(self, *children: QWidget) -> None:
        # The whole row is one hit target: no child may keep a click for itself.
        for child in children:
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class SidebarGroup(_ClickableRow):
    """A parent environment: a header that folds its types away."""

    toggled = Signal(str)

    def __init__(self, key: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(key, parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 10, 6)
        layout.setSpacing(7)

        self.chevron = QLabel("▾")
        self.chevron.setObjectName("Chevron")
        self.chevron.setFixedWidth(11)
        self.title = QLabel(title.upper())
        self.title.setObjectName("SidebarGroupTitle")
        self.count = QLabel("")
        self.count.setObjectName("SidebarItemSubtitle")

        layout.addWidget(self.chevron)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.count)
        self._claim_clicks(self.chevron, self.title, self.count)
        self.set_selected(False)

    def update_content(self, expanded: bool, type_count: int) -> None:
        self.chevron.setText("▾" if expanded else "▸")
        self.count.setText(str(type_count))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggled.emit(self.key)
        super().mousePressEvent(event)


class SidebarItem(_ClickableRow):
    """One row in the sidebar: status dot, title and subtitle."""

    clicked = Signal(str)

    def __init__(
        self,
        key: str,
        title: str,
        palette: Palette,
        *,
        indent: int = 10,
        show_dot: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(key, parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(indent, 7, 10, 7)
        layout.setSpacing(8)

        self.dot = StatusDot(palette, diameter=8)
        self.dot.setVisible(show_dot)
        layout.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)
        self.title = QLabel(title)
        self.title.setObjectName("SidebarItemTitle")
        self.subtitle = ElidingLabel(
            "", object_name="SidebarItemSubtitle", selectable=False
        )
        self.subtitle.hide()
        text_column.addWidget(self.title)
        text_column.addWidget(self.subtitle)
        layout.addLayout(text_column, 1)

        self._claim_clicks(self.dot, self.title, self.subtitle)
        self.set_selected(False)

    def apply_palette(self, palette: Palette) -> None:
        self.dot.apply_palette(palette)

    def update_content(self, subtitle: str, active: bool, tone: str = "success") -> None:
        self.subtitle.set_full_text(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self.dot.set_active(active, tone)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)


class Banner(QFrame):
    """Dismissable error strip shown above the detail panel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Banner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(10)
        self._label = QLabel("")
        self._label.setObjectName("BannerText")
        self._label.setWordWrap(True)
        close = QPushButton("✕")
        close.setObjectName("Ghost")
        close.setFixedWidth(28)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self.hide)
        layout.addWidget(self._label, 1)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        self.hide()

    def show_message(self, message: str) -> None:
        self._label.setText(message)
        self.show()


class Notice(QFrame):
    """Persistent explanation strip: why remote actions are unavailable."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Notice")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 9, 14, 9)
        layout.setSpacing(10)
        self._label = QLabel("")
        self._label.setObjectName("NoticeText")
        self._label.setWordWrap(True)
        self.action = QPushButton("")
        self.action.setObjectName("Ghost")
        self.action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.action.hide()
        layout.addWidget(self._label, 1)
        layout.addWidget(self.action, 0)
        self.hide()

    def show_message(self, message: str, action_text: str = "") -> None:
        self._label.setText(message)
        self.action.setText(action_text)
        self.action.setVisible(bool(action_text))
        self.show()


class ProgressPanel(QWidget):
    """Bar, throughput text and a cancel button for a long operation."""

    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        self.bar.setFixedHeight(8)

        self.text = QLabel("")
        self.text.setObjectName("ProgressText")
        self.text.setMinimumWidth(230)
        self.text.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.cancel = QPushButton("Cancelar")
        self.cancel.setObjectName("Danger")
        self.cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel.clicked.connect(self.cancel_requested.emit)

        layout.addWidget(self.bar, 1)
        layout.addWidget(self.text, 0)
        layout.addWidget(self.cancel, 0)
        self.hide()

    def start(self, cancellable: bool = True) -> None:
        # Un porcentaje desconocido (dump .gz, tamaño remoto ilegible) se muestra
        # como barra indeterminada en vez de fingir un 0 % que no avanza.
        self.bar.setRange(0, 0)
        self.text.setText("")
        self.cancel.setVisible(cancellable)
        self.cancel.setEnabled(cancellable)
        self.show()

    def update_progress(self, percent: float | None, done_mb: float, speed_mb_s: float) -> None:
        if percent is None:
            self.bar.setRange(0, 0)
            self.text.setText(f"{done_mb:.1f} MB · {speed_mb_s:.1f} MB/s")
            return
        self.bar.setRange(0, 100)
        self.bar.setValue(int(max(0.0, min(100.0, percent))))
        self.text.setText(f"{percent:5.1f}% · {done_mb:.1f} MB · {speed_mb_s:.1f} MB/s")

    def finish(self) -> None:
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.text.setText("")
        self.hide()


def data_table(headers: Sequence[str], right_aligned: Sequence[int] = ()) -> QTableWidget:
    """A read-only row-selectable table with the first column stretching.

    Qt centra las cabeceras por omisión, lo que las deja desalineadas respecto de
    sus propias columnas: acá cada cabecera sigue la alineación de sus celdas.
    """
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.verticalHeader().setVisible(False)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    header = table.horizontalHeader()
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for column in range(1, len(headers)):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
    for column in range(len(headers)):
        item = table.horizontalHeaderItem(column)
        if item is not None:
            item.setTextAlignment(_alignment(column in right_aligned))
    return table


def set_table_row(
    table: QTableWidget,
    row: int,
    values: Sequence[str],
    right_aligned: Sequence[int] = (),
) -> None:
    for column, text in enumerate(values):
        item = QTableWidgetItem(text)
        item.setTextAlignment(_alignment(column in right_aligned))
        table.setItem(row, column, item)


def _alignment(right: bool) -> Qt.AlignmentFlag:
    horizontal = Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft
    return horizontal | Qt.AlignmentFlag.AlignVCenter


def mono_family() -> str:
    return MONO_FONTS[0]

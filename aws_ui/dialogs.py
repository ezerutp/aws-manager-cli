"""Dialogs: MFA, remote dump picker, config info and confirmations."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QIntValidator
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .core import Backend, RemoteDump, Session
from .theme import CELL_PADDING_H, CELL_PADDING_V
from .widgets import data_table, set_table_row


class MfaDialog(QDialog):
    """The six digits, asked once at start or when the session runs out.

    `MFAAuthenticator` leía el código con `input()`; acá se pide con este diálogo y
    se le pasa como parámetro, que es lo que permite usarlo sin terminal.
    """

    LOCAL_ONLY = 2  # código de retorno propio: seguir sin MFA, solo local

    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Autenticación MFA")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Autenticación MFA")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        reason = {
            "none": "Las operaciones sobre AWS necesitan una sesión MFA.",
            "active": "La sesión MFA expiró. Ingresá un código nuevo.",
            "inherited": "Hay una sesión heredada del entorno. Podés renovarla acá.",
        }.get(session.state, "Ingresá el código de tu dispositivo MFA.")
        subtitle = QLabel(reason + "\nSe autentica una vez y vale para toda la sesión.")
        subtitle.setObjectName("FieldHint")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.code = QLineEdit()
        self.code.setObjectName("MfaCode")
        self.code.setMaxLength(6)
        self.code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code.setPlaceholderText("······")
        self.code.setValidator(QIntValidator(0, 999999, self))
        layout.addWidget(self.code)

        self.error = QLabel("")
        self.error.setObjectName("FieldError")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        local = QPushButton("Solo local")
        local.setToolTip("Sigue sin MFA: solo operaciones que corren en esta máquina.")
        local.clicked.connect(lambda: self.done(self.LOCAL_ONLY))
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.accept_button = QPushButton("Autenticar")
        self.accept_button.setObjectName("Primary")
        self.accept_button.setDefault(True)
        self.accept_button.setEnabled(False)
        self.accept_button.clicked.connect(self.accept)
        buttons.addWidget(local)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(self.accept_button)
        layout.addLayout(buttons)

        self.code.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        complete = len(text) == 6 and text.isdigit()
        self.accept_button.setEnabled(complete)
        self.code.setProperty("invalid", "true" if text and not text.isdigit() else "false")
        self.code.style().unpolish(self.code)
        self.code.style().polish(self.code)
        if complete:
            self.error.hide()

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.code.selectAll()
        self.code.setFocus()

    def value(self) -> str:
        return self.code.text().strip()


class RemoteDumpDialog(QDialog):
    """Pick one of the dumps sitting on the bastion.

    `get_remote_dumps_list` ya devuelve nombre, tamaño y fecha, así que no hay que
    escribir el nombre del archivo a mano ni adivinar cuál es el último.
    """

    # Márgenes alrededor del botón de cada fila: izq, arriba, der, abajo.
    ACTION_MARGINS = (6, 3, 8, 3)

    def __init__(
        self,
        dumps: Sequence[RemoteDump],
        environment_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Descargar dump")
        self.setModal(True)
        self.setMinimumSize(680, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Dumps disponibles")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        subtitle = QLabel(f"En el servidor de {environment_label}, bajo ~/")
        subtitle.setObjectName("FieldHint")
        layout.addWidget(subtitle)

        self.table = data_table(
            ["ARCHIVO", "TAMAÑO", "FECHA", ""], right_aligned=(1, 2)
        )
        self.table.setRowCount(len(dumps))
        self._row_buttons: list[QPushButton] = []
        for row, dump in enumerate(dumps):
            set_table_row(self.table, row, (dump.name, dump.size, dump.date),
                          right_aligned=(1, 2))
            # Un botón por fila: no hace falta descubrir que la fila se
            # selecciona para poder bajar el dump que se está mirando.
            self.table.setCellWidget(row, 3, self._row_button(row))

        self._size_actions_column()

        self._dumps = list(dumps)
        if dumps:
            self.table.selectRow(0)
        self.table.doubleClicked.connect(lambda _: self._accept_if_selected())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, 1)

        self.hint = QLabel("")
        self.hint.setObjectName("FieldHint")
        layout.addWidget(self.hint)

        # Sin botón de descarga acá abajo: la acción vive en cada fila, y repetirla
        # obligaba a mirar dos lugares para saber qué se iba a bajar.
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cerrar")
        cancel.setDefault(True)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self._on_selection_changed()

    def keyPressEvent(self, event) -> None:
        """Enter sobre la lista baja la fila elegida.

        Antes lo hacía el botón `Descargar` por ser el `default` del diálogo; sin
        ese botón hay que atender la tecla, o el teclado se queda sin la acción.
        """
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and self.table.hasFocus()):
            self._accept_if_selected()
            return
        super().keyPressEvent(event)

    def _size_actions_column(self) -> None:
        """Darle a la columna de botones el ancho y alto que el botón necesita.

        `ResizeToContents` mide los items de la tabla, no los widgets de celda:
        la columna quedaría en cero y el botón, recortado. El tamaño se pide
        después de `ensurePolished()`, porque el padding sale de la hoja de
        estilos y antes de aplicarla el botón se mide más chico de lo que es.
        """
        if not self._row_buttons:
            return

        for button in self._row_buttons:
            button.ensurePolished()
        hints = [button.sizeHint() for button in self._row_buttons]
        left, top, right, bottom = self.ACTION_MARGINS
        # Qt le descuenta a la celda el padding del item, así que el botón se
        # quedaría corto si la columna midiera solo el botón más sus márgenes.
        width = (max(hint.width() for hint in hints) + left + right
                 + 2 * CELL_PADDING_H)
        height = (max(hint.height() for hint in hints) + top + bottom
                  + 2 * CELL_PADDING_V)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, width)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, height)

    def _row_button(self, row: int) -> QWidget:
        """El botón de una fila, dentro de un contenedor que le da aire."""
        button = QPushButton("Descargar")
        button.setObjectName("RowAction")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _=False, index=row: self._accept_row(index))
        self._row_buttons.append(button)

        holder = QWidget()
        holder_layout = QHBoxLayout(holder)
        holder_layout.setContentsMargins(*self.ACTION_MARGINS)
        holder_layout.addWidget(button)
        return holder

    def selected(self) -> RemoteDump | None:
        row = self.table.currentRow()
        if 0 <= row < len(self._dumps):
            return self._dumps[row]
        return None

    def _on_selection_changed(self) -> None:
        chosen = self.selected()
        if chosen is None:
            self.hint.setText("No hay dumps en el servidor de este entorno.")
            return
        self.hint.setText(
            f"{chosen.name} ({chosen.size}) — usá su botón Descargar, "
            "doble clic o Enter."
        )

    def _accept_row(self, row: int) -> None:
        """Bajar el dump de esa fila, sin depender de cuál esté seleccionada."""
        if 0 <= row < len(self._dumps):
            self.table.selectRow(row)
            self.accept()

    def _accept_if_selected(self) -> None:
        if self.selected() is not None:
            self.accept()


class ConfigDialog(QDialog):
    """Which files are in use and where, the equivalent of `--config`."""

    def __init__(self, backend: Backend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configuración")
        self.setModal(True)
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Archivos en uso")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        for label, filename, path in backend.config_files():
            layout.addLayout(self._path_row(label, path, filename))

        layout.addLayout(self._path_row("Dumps", backend.config.get_dump_directory()))
        layout.addLayout(self._path_row("Logs", backend.logs_directory()))

        note = QLabel(
            "Si hay varias copias, gana la primera de: ~/.config/aws-manager, la "
            "carpeta del ejecutable, el directorio actual."
        )
        note.setObjectName("FieldHint")
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton("Cerrar")
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _path_row(self, label: str, path: Path | None, missing_name: str = "") -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        caption = QLabel(label)
        caption.setObjectName("FieldLabel")
        caption.setFixedWidth(160)

        value = QLabel(str(path) if path else f"{missing_name} · no encontrado")
        value.setObjectName("FieldValue" if path else "FieldValueMuted")
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        row.addWidget(caption)
        row.addWidget(value, 1)

        if path is not None:
            folder = path if path.is_dir() else path.parent
            button = QPushButton("Abrir")
            button.setObjectName("Ghost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, target=folder: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(target))
                )
            )
            row.addWidget(button)
        return row


def confirm(
    parent: QWidget | None,
    title: str,
    message: str,
    accept_text: str,
    informative: str = "",
    destructive: bool = False,
) -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.NoIcon)
    box.setText(message)
    if informative:
        box.setInformativeText(informative)
    box.setTextFormat(Qt.TextFormat.PlainText)
    accept = box.addButton(accept_text, QMessageBox.ButtonRole.AcceptRole)
    accept.setObjectName("Danger" if destructive else "Primary")
    box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is accept

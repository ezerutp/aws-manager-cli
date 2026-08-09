"""La ventana de configuración: credenciales, conexión, entornos y paquetes.

Regla que atraviesa todo este archivo: **un secreto no se muestra nunca**. Se
muestra su estado (puesto o no, enmascarado, de dónde sale) y se ofrece
reemplazarlo. El campo para escribir el valor nuevo arranca vacío, así que un
secreto guardado no vuelve a pasar por la pantalla ni por el portapapeles.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .core import Backend, CoreError, parse_databases, validate_environments
from .dialogs import confirm
from .widgets import Card, ElidingLabel, Pill, data_table, separator, set_table_row


class SecretField(QWidget):
    """Estado de un secreto y, si se pide, un campo para reemplazarlo.

    `value()` devuelve `None` mientras no se toque, que el Backend interpreta
    como "dejá el que estaba". El valor guardado no se carga en el campo: esta
    pantalla no lo conoce y no tiene por qué.
    """

    changed = Signal()

    def __init__(self, label: str, hint: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        title = QLabel(label)
        title.setObjectName("FieldLabel")
        title.setFixedWidth(140)
        self.status = ElidingLabel("", object_name="FieldValueMuted")
        self.pill = Pill("sin definir", tone="off")
        self.edit_button = QPushButton("Cambiar")
        self.edit_button.setObjectName("Ghost")
        self.edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_button.clicked.connect(self._start_editing)
        header.addWidget(title)
        header.addWidget(self.status, 1)
        header.addWidget(self.pill)
        header.addWidget(self.edit_button)
        layout.addLayout(header)

        self.editor = QWidget()
        editor_layout = QHBoxLayout(self.editor)
        editor_layout.setContentsMargins(140, 0, 0, 0)
        editor_layout.setSpacing(8)
        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.input.setPlaceholderText(hint or "valor nuevo")
        self.input.textChanged.connect(lambda _: self.changed.emit())
        self.reveal = QPushButton("ver")
        self.reveal.setObjectName("Chip")
        self.reveal.setCheckable(True)
        self.reveal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reveal.setToolTip("Mostrar lo que estás escribiendo, para revisarlo")
        self.reveal.toggled.connect(self._on_reveal)
        cancel = QPushButton("✕")
        cancel.setObjectName("Ghost")
        cancel.setFixedWidth(28)
        cancel.setToolTip("Dejar el valor actual")
        cancel.clicked.connect(self._stop_editing)
        editor_layout.addWidget(self.input, 1)
        editor_layout.addWidget(self.reveal)
        editor_layout.addWidget(cancel)
        self.editor.hide()
        layout.addWidget(self.editor)

    def set_status(self, present: bool, text: str, source: str = "") -> None:
        self.status.set_full_text(text)
        if present:
            self.pill.setText("definido" if source != "entorno" else "en el entorno")
            self.pill.set_tone("on" if source != "entorno" else "warn")
        else:
            self.pill.setText("sin definir")
            self.pill.set_tone("off")

    def _start_editing(self) -> None:
        self.editor.show()
        self.input.setFocus()
        self.edit_button.setEnabled(False)
        self.changed.emit()

    def _stop_editing(self) -> None:
        self.input.clear()
        self.reveal.setChecked(False)
        self.editor.hide()
        self.edit_button.setEnabled(True)
        self.changed.emit()

    def _on_reveal(self, revealed: bool) -> None:
        self.input.setEchoMode(
            QLineEdit.EchoMode.Normal if revealed else QLineEdit.EchoMode.Password
        )

    def value(self) -> Optional[str]:
        if self.editor.isHidden():
            return None
        return self.input.text().strip()


class KeyField(QWidget):
    """Ruta de una llave SSH, con verificación que no lee la llave."""

    changed = Signal()

    def __init__(self, label: str = "llave privada", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._backend: Optional[Backend] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        caption = QLabel(label)
        caption.setObjectName("FieldLabel")
        caption.setFixedWidth(140)
        self.input = QLineEdit()
        self.input.setPlaceholderText("~/.ssh/mi-llave.pem")
        self.input.textChanged.connect(self._on_text_changed)
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self._browse)
        row.addWidget(caption)
        row.addWidget(self.input, 1)
        row.addWidget(browse)
        layout.addLayout(row)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(140, 0, 0, 0)
        status_row.setSpacing(8)
        self.status = ElidingLabel("", object_name="FieldValueMuted")
        self.fix_button = QPushButton("Corregir permisos")
        self.fix_button.setObjectName("Ghost")
        self.fix_button.clicked.connect(self._fix_permissions)
        self.fix_button.hide()
        status_row.addWidget(self.status, 1)
        status_row.addWidget(self.fix_button)
        layout.addLayout(status_row)

    def attach(self, backend: Backend) -> None:
        self._backend = backend
        self.refresh()

    def text(self) -> str:
        return self.input.text().strip()

    def set_text(self, value: str) -> None:
        self.input.setText(value or "")
        self.refresh()

    def _on_text_changed(self, _text: str) -> None:
        self.refresh()
        self.changed.emit()

    def refresh(self) -> None:
        if self._backend is None:
            return
        path = self.text()
        if not path:
            self.status.set_full_text("sin definir · se usará la llave general")
            self.fix_button.hide()
            return
        status = self._backend.key_status(path)
        self.status.set_full_text(status.text)
        # Los permisos abiertos los rechaza el propio ssh, así que se ofrece
        # arreglarlos acá en vez de mandar al usuario a la terminal.
        self.fix_button.setVisible(status.exists and not status.permissions_ok)

    def _browse(self) -> None:
        start = Path(self.text()).expanduser().parent if self.text() else Path.home() / ".ssh"
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir llave privada", str(start),
            "Llaves (*.pem *.key id_*);;Todos los archivos (*)",
        )
        if path:
            self.set_text(path)

    def _fix_permissions(self) -> None:
        if self._backend is None:
            return
        try:
            self._backend.fix_key_permissions(self.text())
        except CoreError as error:
            self.status.set_full_text(str(error))
            return
        self.refresh()


class SettingsDialog(QDialog):
    """Toda la configuración editable, en pestañas."""

    def __init__(self, backend: Backend, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.backend = backend
        self.config = backend.config_snapshot()
        self.environments = backend.environments_snapshot()
        self.changed = False
        self._current: Optional[tuple[int, Optional[int]]] = None
        self._loading = False

        self.setWindowTitle("Configuración")
        self.setModal(True)
        self.setMinimumSize(860, 640)
        self.resize(960, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title = QLabel("Configuración")
        title.setObjectName("DialogTitle")
        layout.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_credentials_tab(), "Credenciales")
        self.tabs.addTab(self._build_connection_tab(), "Conexión")
        self.tabs.addTab(self._build_environments_tab(), "Entornos")
        self.tabs.addTab(self._build_bundle_tab(), "Exportar / importar")
        layout.addWidget(self.tabs, 1)

        self.feedback = QLabel("")
        self.feedback.setObjectName("FieldHint")
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(8)
        buttons.addStretch(1)
        close = QPushButton("Cerrar")
        close.clicked.connect(self._close_if_saved)
        self.save_button = QPushButton("Guardar cambios")
        self.save_button.setObjectName("Primary")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)
        buttons.addWidget(close)
        buttons.addWidget(self.save_button)
        layout.addLayout(buttons)

        self._load()

    # ---- credenciales -----------------------------------------------------

    def _build_credentials_tab(self) -> QWidget:
        page = _scrollable()
        layout = page.body

        card = Card("CREDENCIALES AWS")
        note = QLabel(
            "Los valores guardados no se muestran. Se puede ver si están puestos, "
            "cómo terminan, y comprobar contra AWS que funcionan."
        )
        note.setObjectName("FieldHint")
        note.setWordWrap(True)
        card.add(note)

        self.access_key_field = SecretField("access_key", "AKIA…")
        self.secret_key_field = SecretField("secret_key", "40 caracteres")
        card.add(self.access_key_field)
        card.add(self.secret_key_field)
        card.add(separator())

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        self.region_input = QLineEdit()
        self.region_input.setPlaceholderText("us-east-1")
        self.rule_input = QLineEdit()
        self.rule_input.setPlaceholderText("Tu nombre, para la regla del Security Group")
        form.addRow(_label("region"), self.region_input)
        form.addRow(_label("rule_description"), self.rule_input)
        card.add_layout(form)

        verify_row = QHBoxLayout()
        verify_row.setContentsMargins(0, 0, 0, 0)
        verify = QPushButton("Verificar con AWS")
        verify.setToolTip("Ejecuta `aws sts get-caller-identity` y muestra con qué identidad estás")
        verify.clicked.connect(self._verify_credentials)
        self.identity_label = ElidingLabel("", object_name="FieldValueMuted")
        verify_row.addWidget(verify)
        verify_row.addWidget(self.identity_label, 1)
        card.add_layout(verify_row)
        layout.addWidget(card)

        env_card = Card("VARIABLES DE ENTORNO")
        env_note = QLabel(
            "Lo que hay en el entorno de este proceso. Si una credencial está acá, "
            "gana sobre la del archivo: es lo primero que mira la autenticación.\n"
            "Lanzada desde el menú del escritorio la app no hereda lo que exporta "
            "tu .zshrc, así que se le pregunta al shell de login."
        )
        env_note.setObjectName("FieldHint")
        env_note.setWordWrap(True)
        env_card.add(env_note)

        self.environment_table = data_table(["VARIABLE", "ESTADO", "ORIGEN", "VALOR"])
        env_card.add(self.environment_table)

        shell_row = QHBoxLayout()
        shell_row.setContentsMargins(0, 0, 0, 0)
        shell_row.setSpacing(8)
        reread = QPushButton("Releer del shell")
        reread.setToolTip("Vuelve a preguntarle al shell de login por las variables AWS_*")
        reread.clicked.connect(self._reread_shell)
        self.shell_label = QLabel("")
        self.shell_label.setObjectName("FieldHint")
        shell_row.addWidget(reread)
        shell_row.addWidget(self.shell_label, 1)
        env_card.add_layout(shell_row)
        layout.addWidget(env_card)

        self.mfa_checkbox = QCheckBox("Requerir MFA para las operaciones remotas")
        layout.addWidget(self.mfa_checkbox)
        layout.addStretch(1)
        return page

    def _reread_shell(self) -> None:
        imported = self.backend.adopt_shell_environment()
        self._load()
        if imported:
            self.feedback.setText(
                "✓ Del shell de login: " + ", ".join(imported)
            )
        else:
            self.feedback.setText(
                f"El shell ({self.backend.shell_name()}) no aportó variables nuevas. "
                "Si las definís en un archivo que solo lee un shell interactivo, "
                "revisá que estén con `export`."
            )

    def _verify_credentials(self) -> None:
        self.identity_label.set_full_text("consultando…")
        try:
            message = self.backend.verify_credentials()
        except CoreError as error:
            self.identity_label.set_full_text(str(error))
            return
        self.identity_label.set_full_text(message)

    # ---- conexion ---------------------------------------------------------

    def _build_connection_tab(self) -> QWidget:
        page = _scrollable()
        layout = page.body

        key_card = Card("LLAVE SSH GENERAL")
        key_note = QLabel(
            "La que se usa para todos los entornos que no definan una propia. "
            "Se verifica que exista y tenga permisos 600; la huella confirma cuál es."
        )
        key_note.setObjectName("FieldHint")
        key_note.setWordWrap(True)
        key_card.add(key_note)
        self.key_field = KeyField("key_path")
        # Cambiar la llave general se refleja en la pestaña de entornos.
        self.key_field.changed.connect(self._refresh_general_key_label)
        key_card.add(self.key_field)
        layout.addWidget(key_card)

        ssh_card = Card("SSH")
        ssh_form = QFormLayout()
        ssh_form.setContentsMargins(0, 0, 0, 0)
        ssh_form.setSpacing(10)
        self.ssh_user_input = QLineEdit()
        self.ssh_port_input = QLineEdit()
        self.ssh_port_input.setValidator(QIntValidator(1, 65535, self))
        self.ssh_timeout_input = QLineEdit()
        self.ssh_timeout_input.setValidator(QIntValidator(1, 600, self))
        self.strict_host_checkbox = QCheckBox("Verificar la clave del host (StrictHostKeyChecking)")
        ssh_form.addRow(_label("user"), self.ssh_user_input)
        ssh_form.addRow(_label("port"), self.ssh_port_input)
        ssh_form.addRow(_label("connect_timeout"), self.ssh_timeout_input)
        ssh_card.add_layout(ssh_form)
        ssh_card.add(self.strict_host_checkbox)
        layout.addWidget(ssh_card)

        mysql_card = Card("MYSQL LOCAL")
        mysql_form = QFormLayout()
        mysql_form.setContentsMargins(0, 0, 0, 0)
        mysql_form.setSpacing(10)
        self.mysql_user_input = QLineEdit()
        self.mysql_host_input = QLineEdit()
        self.mysql_protocol_input = QComboBox()
        self.mysql_protocol_input.addItems(["tcp", "socket", "pipe", "memory"])
        mysql_form.addRow(_label("user"), self.mysql_user_input)
        mysql_form.addRow(_label("host"), self.mysql_host_input)
        mysql_form.addRow(_label("protocol"), self.mysql_protocol_input)
        mysql_card.add_layout(mysql_form)

        databases_label = QLabel("Bases disponibles, una por línea (clave = nombre real)")
        databases_label.setObjectName("FieldHint")
        mysql_card.add(databases_label)
        self.databases_input = QLineEdit()
        self.databases_input.setPlaceholderText("ops=ensolvers_ops, hirelens=hirelens")
        mysql_card.add(self.databases_input)
        layout.addWidget(mysql_card)

        paths_card = Card("RUTAS")
        paths_form = QFormLayout()
        paths_form.setContentsMargins(0, 0, 0, 0)
        paths_form.setSpacing(10)
        dump_row = QWidget()
        dump_layout = QHBoxLayout(dump_row)
        dump_layout.setContentsMargins(0, 0, 0, 0)
        dump_layout.setSpacing(8)
        self.dump_directory_input = QLineEdit()
        self.dump_directory_input.setPlaceholderText("vacío = ~/db_dump")
        pick = QPushButton("Elegir…")
        pick.clicked.connect(self._pick_dump_directory)
        dump_layout.addWidget(self.dump_directory_input, 1)
        dump_layout.addWidget(pick)
        paths_form.addRow(_label("dump_directory"), dump_row)
        paths_card.add_layout(paths_form)
        layout.addWidget(paths_card)
        layout.addStretch(1)
        return page

    def _pick_dump_directory(self) -> None:
        current = self.dump_directory_input.text().strip()
        start = current or str(self.backend.config.get_dump_directory())
        path = QFileDialog.getExistingDirectory(self, "Carpeta de dumps", start)
        if path:
            self.dump_directory_input.setText(path)

    # ---- entornos ---------------------------------------------------------

    def _build_environments_tab(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setMinimumWidth(240)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.currentItemChanged.connect(self._on_tree_selection)
        left.addWidget(self.tree, 1)

        tree_buttons = QHBoxLayout()
        tree_buttons.setSpacing(6)
        add_parent = QPushButton("＋ Entorno")
        add_parent.clicked.connect(self._add_parent)
        add_type = QPushButton("＋ Tipo")
        add_type.clicked.connect(self._add_type)
        self.remove_button = QPushButton("Eliminar")
        self.remove_button.setObjectName("Danger")
        self.remove_button.clicked.connect(self._remove_selected)
        tree_buttons.addWidget(add_parent)
        tree_buttons.addWidget(add_type)
        tree_buttons.addWidget(self.remove_button)
        left.addLayout(tree_buttons)
        layout.addLayout(left)

        self.environment_stack = QStackedWidget()
        self.environment_stack.addWidget(self._build_parent_form())
        self.environment_stack.addWidget(self._build_type_form())
        self.environment_stack.addWidget(self._build_environment_placeholder())
        layout.addWidget(self.environment_stack, 1)
        return page

    def _build_parent_form(self) -> QWidget:
        card = Card("ENTORNO PADRE")
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        self.parent_id_input = QLineEdit()
        self.parent_id_input.setPlaceholderText("ops")
        self.parent_name_input = QLineEdit()
        self.parent_name_input.setPlaceholderText("OPS")
        for widget in (self.parent_id_input, self.parent_name_input):
            widget.textChanged.connect(self._commit_current)
        form.addRow(_label("id"), self.parent_id_input)
        form.addRow(_label("name"), self.parent_name_input)
        card.add_layout(form)
        hint = QLabel(
            "El id agrupa los dumps descargados y no debería cambiar si ya hay "
            "descargas hechas con él."
        )
        hint.setObjectName("FieldHint")
        hint.setWordWrap(True)
        card.add(hint)
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(card)
        wrapper_layout.addStretch(1)
        return wrapper

    def _build_type_form(self) -> QWidget:
        page = _scrollable()
        layout = page.body

        card = Card("TIPO DE ENTORNO")
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        self.type_inputs: dict[str, QLineEdit] = {}
        for name, placeholder in (
            ("id", "ops_prod"),
            ("name", "PROD"),
            ("env_type", "prod"),
            ("instance_id", "i-0123456789abcdef0"),
            ("security_group_id", "sg-0123456789abcdef0"),
            ("dns", "vacío = DNS dinámico"),
            ("instance_name", "Bastion-PROD-OPS"),
        ):
            widget = QLineEdit()
            widget.setPlaceholderText(placeholder)
            widget.textChanged.connect(self._commit_current)
            self.type_inputs[name] = widget
            form.addRow(_label(name), widget)
        card.add_layout(form)
        layout.addWidget(card)

        key_card = Card("LLAVE SSH DE ESTE ENTORNO")
        self.key_mode = QComboBox()
        self.key_mode.setObjectName("TextCombo")
        self.key_mode.addItem("Usar la llave general", "general")
        self.key_mode.addItem("Usar una llave propia", "own")
        self.key_mode.currentIndexChanged.connect(self._on_key_mode_changed)
        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(14)
        mode_row.addWidget(_label("llave"))
        mode_row.addWidget(self.key_mode, 1)
        key_card.add_layout(mode_row)

        self.type_key_field = KeyField("key_path")
        self.type_key_field.changed.connect(self._commit_current)
        key_card.add(self.type_key_field)

        self.general_key_label = QLabel("")
        self.general_key_label.setObjectName("FieldHint")
        self.general_key_label.setWordWrap(True)
        key_card.add(self.general_key_label)
        layout.addWidget(key_card)
        layout.addStretch(1)
        return page

    def _build_environment_placeholder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        label = QLabel("Elegí un entorno o un tipo de la lista")
        label.setObjectName("EmptyBody")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        layout.addStretch(1)
        return page

    def _refresh_general_key_label(self) -> None:
        general = self.key_field.text() or "(sin definir)"
        self.general_key_label.setText(f"Se usará la llave general: {general}")

    def _on_key_mode_changed(self) -> None:
        own = self.key_mode.currentData() == "own"
        self.type_key_field.setVisible(own)
        self.general_key_label.setVisible(not own)
        if not own:
            self.type_key_field.input.blockSignals(True)
            self.type_key_field.input.clear()
            self.type_key_field.input.blockSignals(False)
        self._commit_current()

    # ---- arbol de entornos ------------------------------------------------

    def _rebuild_tree(self, select: Optional[tuple[int, Optional[int]]] = None) -> None:
        self._loading = True
        self.tree.clear()
        for parent_index, parent in enumerate(self.environments):
            node = QTreeWidgetItem([parent.get("name") or parent.get("id") or "(sin nombre)"])
            node.setData(0, Qt.ItemDataRole.UserRole, (parent_index, None))
            self.tree.addTopLevelItem(node)
            for type_index, env_type in enumerate(parent.get("types", [])):
                child = QTreeWidgetItem([env_type.get("name") or env_type.get("id") or "(sin nombre)"])
                child.setData(0, Qt.ItemDataRole.UserRole, (parent_index, type_index))
                node.addChild(child)
            node.setExpanded(True)
        self._loading = False

        if select is not None:
            self._select_path(select)
        elif self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        else:
            self._current = None
            self.environment_stack.setCurrentIndex(2)

    def _select_path(self, path: tuple[int, Optional[int]]) -> None:
        for index in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(index)
            if node.data(0, Qt.ItemDataRole.UserRole) == path:
                self.tree.setCurrentItem(node)
                return
            for child_index in range(node.childCount()):
                child = node.child(child_index)
                if child.data(0, Qt.ItemDataRole.UserRole) == path:
                    self.tree.setCurrentItem(child)
                    return

    def _on_tree_selection(self, current: QTreeWidgetItem, _previous) -> None:
        if self._loading:
            return
        if current is None:
            self._current = None
            self.environment_stack.setCurrentIndex(2)
            return
        self._current = current.data(0, Qt.ItemDataRole.UserRole)
        self._load_current()

    def _load_current(self) -> None:
        if self._current is None:
            self.environment_stack.setCurrentIndex(2)
            return
        parent_index, type_index = self._current
        self._loading = True
        try:
            parent = self.environments[parent_index]
            if type_index is None:
                self.parent_id_input.setText(str(parent.get("id", "")))
                self.parent_name_input.setText(str(parent.get("name", "")))
                self.environment_stack.setCurrentIndex(0)
            else:
                env_type = parent["types"][type_index]
                for name, widget in self.type_inputs.items():
                    widget.setText(str(env_type.get(name, "") or ""))
                own_key = str(env_type.get("key_path", "") or "").strip()
                self.key_mode.setCurrentIndex(1 if own_key else 0)
                self.type_key_field.set_text(own_key)
                self.type_key_field.setVisible(bool(own_key))
                self.general_key_label.setVisible(not own_key)
                self._refresh_general_key_label()
                self.environment_stack.setCurrentIndex(1)
        except (IndexError, KeyError):
            self._current = None
            self.environment_stack.setCurrentIndex(2)
        finally:
            self._loading = False

    def _commit_current(self) -> None:
        """Vuelca el formulario al modelo en memoria, en cada tecla."""
        if self._loading or self._current is None:
            return
        parent_index, type_index = self._current
        try:
            parent = self.environments[parent_index]
        except IndexError:
            return

        if type_index is None:
            parent["id"] = self.parent_id_input.text().strip()
            parent["name"] = self.parent_name_input.text().strip()
            label = parent["name"] or parent["id"] or "(sin nombre)"
        else:
            try:
                env_type = parent["types"][type_index]
            except (IndexError, KeyError):
                return
            for name, widget in self.type_inputs.items():
                env_type[name] = widget.text().strip()
            env_type["key_path"] = (
                self.type_key_field.text() if self.key_mode.currentData() == "own" else ""
            )
            label = env_type["name"] or env_type["id"] or "(sin nombre)"

        item = self.tree.currentItem()
        if item is not None and item.text(0) != label:
            item.setText(0, label)
        self.changed = True

    def _add_parent(self) -> None:
        self.environments.append({"id": "", "name": "Nuevo entorno", "types": []})
        self.changed = True
        self._rebuild_tree(select=(len(self.environments) - 1, None))

    def _add_type(self) -> None:
        if self._current is None:
            if not self.environments:
                self.feedback.setText("Primero creá un entorno padre.")
                return
            parent_index = 0
        else:
            parent_index = self._current[0]
        parent = self.environments[parent_index]
        parent.setdefault("types", []).append({
            "id": "", "name": "NUEVO", "env_type": "", "instance_id": "",
            "security_group_id": "", "dns": "", "instance_name": "", "key_path": "",
        })
        self.changed = True
        self._rebuild_tree(select=(parent_index, len(parent["types"]) - 1))

    def _remove_selected(self) -> None:
        if self._current is None:
            return
        parent_index, type_index = self._current
        parent = self.environments[parent_index]
        if type_index is None:
            if not confirm(
                self, "Eliminar entorno",
                f"Eliminar '{parent.get('name') or parent.get('id')}' y sus "
                f"{len(parent.get('types', []))} tipo(s)?",
                "Eliminar", destructive=True,
                informative="Los dumps ya descargados no se tocan.",
            ):
                return
            self.environments.pop(parent_index)
            target = (max(parent_index - 1, 0), None) if self.environments else None
        else:
            env_type = parent["types"][type_index]
            if not confirm(
                self, "Eliminar tipo",
                f"Eliminar '{env_type.get('name') or env_type.get('id')}'?",
                "Eliminar", destructive=True,
            ):
                return
            parent["types"].pop(type_index)
            target = (parent_index, None)
        self.changed = True
        self._rebuild_tree(select=target)

    # ---- exportar / importar ---------------------------------------------

    def _build_bundle_tab(self) -> QWidget:
        page = _scrollable()
        layout = page.body

        export_card = Card("EXPORTAR")
        export_note = QLabel(
            "Genera un .zip con la configuración, los entornos y, si se pide, las "
            "llaves privadas. Sirve para llevar todo a otra máquina: las rutas de "
            "las llaves se reescriben para que funcionen allá."
        )
        export_note.setObjectName("FieldHint")
        export_note.setWordWrap(True)
        export_card.add(export_note)

        self.include_keys_checkbox = QCheckBox("Incluir las llaves privadas SSH")
        self.include_keys_checkbox.setChecked(True)
        self.include_secrets_checkbox = QCheckBox("Incluir las credenciales AWS (access_key y secret_key)")
        export_card.add(self.include_keys_checkbox)
        export_card.add(self.include_secrets_checkbox)

        warning = QLabel(
            "⚠ Un paquete con llaves o credenciales da acceso a tu infraestructura. "
            "Se escribe con permisos 600; tratalo como tratarías la llave privada."
        )
        warning.setObjectName("FieldError")
        warning.setWordWrap(True)
        export_card.add(warning)

        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 0, 0, 0)
        export_button = QPushButton("Exportar…")
        export_button.setObjectName("Primary")
        export_button.clicked.connect(self._export)
        export_row.addWidget(export_button)
        export_row.addStretch(1)
        export_card.add_layout(export_row)
        layout.addWidget(export_card)

        import_card = Card("IMPORTAR")
        import_note = QLabel(
            "Lee un paquete y reemplaza la configuración actual. Antes de escribir "
            "nada se muestra qué trae y se pide confirmación. Las llaves se copian "
            "a ~/.config/aws-manager/keys/ con permisos 600."
        )
        import_note.setObjectName("FieldHint")
        import_note.setWordWrap(True)
        import_card.add(import_note)

        import_row = QHBoxLayout()
        import_row.setContentsMargins(0, 0, 0, 0)
        import_button = QPushButton("Importar…")
        import_button.clicked.connect(self._import)
        import_row.addWidget(import_button)
        import_row.addStretch(1)
        import_card.add_layout(import_row)
        layout.addWidget(import_card)
        layout.addStretch(1)
        return page

    def _export(self) -> None:
        if self.changed and not confirm(
            self, "Hay cambios sin guardar",
            "Se exportará la configuración guardada, no lo que está en pantalla.",
            "Exportar igual",
            informative="Guardá primero si querés incluir los cambios.",
        ):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar paquete", str(Path.home() / "aws-manager-config.zip"),
            "Paquetes (*.zip)",
        )
        if not path:
            return
        try:
            message = self.backend.export_configuration(
                Path(path),
                include_secrets=self.include_secrets_checkbox.isChecked(),
                include_keys=self.include_keys_checkbox.isChecked(),
            )
        except CoreError as error:
            self.feedback.setText(f"✗ {error}")
            return
        self.feedback.setText(f"✓ {message} → {path}")

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir paquete", str(Path.home()), "Paquetes (*.zip);;Todos (*)"
        )
        if not path:
            return
        try:
            contents = self.backend.inspect_configuration(Path(path))
        except CoreError as error:
            self.feedback.setText(f"✗ {error}")
            return

        details = [contents.summary]
        if contents.created_at:
            details.append(f"creado {contents.created_at}")
        if contents.source_host:
            details.append(f"en {contents.source_host}")
        if not confirm(
            self, "Importar configuración",
            "Reemplazar la configuración actual con la del paquete?",
            "Importar", destructive=True,
            informative=(
                " · ".join(details)
                + "\n\nSe sobrescriben config.json y config-environment.json."
                + ("\nLas credenciales AWS actuales se conservan." if not contents.includes_secrets else "")
            ),
        ):
            return

        try:
            message = self.backend.import_configuration(Path(path))
        except CoreError as error:
            self.feedback.setText(f"✗ {error}")
            return

        # Lo importado es ahora la verdad: se recarga el formulario entero.
        self.config = self.backend.config_snapshot()
        self.environments = self.backend.environments_snapshot()
        self.changed = False
        self._load()
        self.feedback.setText(f"✓ {message}")

    # ---- carga y guardado -------------------------------------------------

    def _load(self) -> None:
        self._loading = True
        credentials = self.config.get("credentials", {})
        access, secret = self.backend.secret_status()
        self.access_key_field.set_status(access.present, access.text, access.source)
        self.secret_key_field.set_status(secret.present, secret.text, secret.source)
        self.region_input.setText(str(credentials.get("region", "")))
        self.rule_input.setText(str(credentials.get("rule_description", "")))
        self.mfa_checkbox.setChecked(bool(self.config.get("mfa", {}).get("required", True)))

        rows = self.backend.environment_variables()
        self.environment_table.setRowCount(len(rows))
        for row, (name, present, shown, origin) in enumerate(rows):
            set_table_row(self.environment_table, row,
                          (name, "definida" if present else "sin definir",
                           origin or "—", shown or "—"))
        # La tabla se ajusta a su contenido: si tuviera scroll propio, quedaría
        # anidado dentro del scroll de la pestaña, que es incómodo de usar.
        _fit_to_contents(self.environment_table)
        self.shell_label.setText(f"shell de login: {self.backend.shell_name()}")

        self.key_field.attach(self.backend)
        self.key_field.set_text(str(credentials.get("key_path", "")))
        self.type_key_field.attach(self.backend)

        ssh = self.config.get("ssh", {})
        self.ssh_user_input.setText(str(ssh.get("user", "ubuntu")))
        self.ssh_port_input.setText(str(ssh.get("port", 22)))
        self.ssh_timeout_input.setText(str(ssh.get("connect_timeout", 10)))
        self.strict_host_checkbox.setChecked(bool(ssh.get("strict_host_key_checking", False)))

        mysql = self.config.get("mysql", {})
        self.mysql_user_input.setText(str(mysql.get("user", "root")))
        self.mysql_host_input.setText(str(mysql.get("host", "127.0.0.1")))
        protocol = str(mysql.get("protocol", "tcp"))
        index = self.mysql_protocol_input.findText(protocol)
        if index < 0:
            self.mysql_protocol_input.addItem(protocol)
            index = self.mysql_protocol_input.findText(protocol)
        self.mysql_protocol_input.setCurrentIndex(index)
        self.databases_input.setText(
            ", ".join(f"{key}={value}" for key, value in mysql.get("databases", {}).items())
        )

        self.dump_directory_input.setText(str(self.config.get("paths", {}).get("dump_directory", "")))
        self._loading = False
        self._rebuild_tree()

    def save(self) -> None:
        problem = validate_environments(self.environments)
        if problem:
            self.tabs.setCurrentIndex(2)
            self.feedback.setText(f"✗ {problem}")
            return

        # Se parte de lo que hay en disco, así que los secretos que esta pantalla
        # nunca vio siguen intactos y las claves ajenas no se pierden.
        data = self.backend.config_snapshot()
        credentials = data.setdefault("credentials", {})
        credentials["region"] = self.region_input.text().strip()
        credentials["rule_description"] = self.rule_input.text().strip()
        credentials["key_path"] = self.key_field.text()
        # `None` en un secreto significa "no lo toques": el diálogo nunca lo tuvo.
        access = self.access_key_field.value()
        if access is not None:
            credentials["access_key"] = access
        secret = self.secret_key_field.value()
        if secret is not None:
            credentials["secret_key"] = secret

        data.setdefault("mfa", {})["required"] = self.mfa_checkbox.isChecked()
        data.setdefault("ssh", {}).update({
            "user": self.ssh_user_input.text().strip() or "ubuntu",
            "port": int(self.ssh_port_input.text() or 22),
            "connect_timeout": int(self.ssh_timeout_input.text() or 10),
            "strict_host_key_checking": self.strict_host_checkbox.isChecked(),
        })
        data.setdefault("mysql", {}).update({
            "user": self.mysql_user_input.text().strip() or "root",
            "host": self.mysql_host_input.text().strip() or "127.0.0.1",
            "protocol": self.mysql_protocol_input.currentText(),
            "databases": parse_databases(self.databases_input.text()),
        })
        data.setdefault("paths", {})["dump_directory"] = self.dump_directory_input.text().strip()

        try:
            self.backend.save_configuration(data)
            message = self.backend.save_environments(copy.deepcopy(self.environments))
        except (CoreError, ValueError) as error:
            self.feedback.setText(f"✗ {error}")
            return

        self.changed = False
        self.config = self.backend.config_snapshot()
        self._load()
        self.feedback.setText(f"✓ Configuración guardada · {message}")

    def _close_if_saved(self) -> None:
        if self.changed and not confirm(
            self, "Cambios sin guardar",
            "Hay cambios en los entornos que no se guardaron.",
            "Descartar", destructive=True,
        ):
            return
        self.accept()


def _fit_to_contents(table) -> None:
    """Deja la tabla del alto exacto de sus filas, sin barra de desplazamiento."""
    height = table.horizontalHeader().height() + 2 * table.frameWidth()
    for row in range(table.rowCount()):
        height += table.rowHeight(row)
    table.setFixedHeight(height)


def _label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    label.setFixedWidth(140)
    return label


class _ScrollPage(QScrollArea):
    """Una pestaña que puede crecer más que la ventana."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        self.body = QVBoxLayout(container)
        self.body.setContentsMargins(2, 12, 8, 12)
        self.body.setSpacing(14)
        self.setWidget(container)


def _scrollable() -> _ScrollPage:
    return _ScrollPage()

"""Main window: the environment tree in a sidebar, the selection in detail."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .core import (
    CODENAME,
    VERSION,
    Backend,
    CoreError,
    DumpFilter,
    EnvironmentType,
    SecurityGroupPlan,
    Snapshot,
    format_size,
    missing_tools,
)
from .dialogs import ConfigDialog, MfaDialog, RemoteDumpDialog, confirm
from .settings import SettingsDialog
from .icons import app_icon
from .theme import Palette
from .widgets import (
    Banner,
    Card,
    ElidingLabel,
    Notice,
    Pill,
    ProgressPanel,
    SidebarGroup,
    SidebarItem,
    StatusDot,
    data_table,
    field_row,
    separator,
    set_table_row,
)


POLL_INTERVAL_MS = 1500
LOG_LIMIT = 800

PAGE_ENVIRONMENT = 0
PAGE_DATABASE = 1
PAGE_HISTORY = 2
PAGE_EMPTY = 3


class _TaskSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(object, float, float)


class _Task(QRunnable):
    """Runs one backend call off the UI thread.

    Acá hace falta más que en proxy-local: un `scp` puede tardar 30 minutos y un
    import de MySQL, más. Nunca se tocan widgets desde este hilo: solo señales.
    """

    def __init__(self, work: Callable[[], Any], signals: _TaskSignals) -> None:
        super().__init__()
        self.work = work
        self.signals = signals

    def run(self) -> None:
        try:
            self.signals.finished.emit(self.work())
        except CoreError as error:
            self.signals.failed.emit(str(error))
        except Exception as error:  # keep the UI alive on anything unexpected
            self.signals.failed.emit(f"Error inesperado: {error}")


class MainWindow(QMainWindow):
    snapshot_changed = Signal(object)
    quit_requested = Signal()
    log_line = Signal(str)

    def __init__(self, backend: Backend, palette: Palette) -> None:
        super().__init__()
        self.backend = backend
        self.palette_tokens = palette
        self.snapshot = Snapshot()
        self.busy = False

        # ("environment", type_id) | ("local", "database") | ("local", "history")
        self.selection: tuple[str, str] = ("local", "database")
        self._fingerprint: tuple | None = None
        self._groups: dict[str, SidebarGroup] = {}
        self._items: dict[str, SidebarItem] = {}
        self._collapsed: set[str] = set()
        self._access: dict[str, SecurityGroupPlan] = {}
        self._dump_filters: tuple[DumpFilter, ...] = ()
        self._chosen_dump: Optional[Path] = None
        self._cancel = threading.Event()
        self._then: Optional[Callable[[Any], None]] = None
        self._pool = QThreadPool.globalInstance()

        self.setWindowTitle("aws-manager")
        self.setMinimumSize(980, 700)
        self.resize(1120, 760)

        self._build()
        self._build_shortcuts()

        self.log_line.connect(self._append_log)
        self.backend.set_output(self.log_line.emit)

        self._poll = QTimer(self)
        self._poll.setInterval(POLL_INTERVAL_MS)
        self._poll.timeout.connect(self.refresh)
        self._poll.start()

        # La configuración la carga quien construye el Backend: si la ventana la
        # recargara, pisaría una configuración elegida a propósito.
        self.refresh(force=True)
        # Avisar recién cuando la ventana ya pintó.
        QTimer.singleShot(60, self._warn_about_environment)

    # ---- construccion -----------------------------------------------------

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_detail(), 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(258)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(12)

        brand = QHBoxLayout()
        brand.setContentsMargins(4, 0, 0, 0)
        brand.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(app_icon(self.palette_tokens).pixmap(30, 30))
        brand.addWidget(mark)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)
        name = QLabel("aws-manager")
        name.setObjectName("BrandName")
        subtitle = QLabel(f"{CODENAME} v{VERSION}")
        subtitle.setObjectName("BrandSubtitle")
        titles.addWidget(name)
        titles.addWidget(subtitle)
        brand.addLayout(titles, 1)

        paths_button = QPushButton("ⓘ")
        paths_button.setObjectName("IconButton")
        paths_button.setToolTip("Qué archivos de configuración se están usando")
        paths_button.setFixedSize(26, 30)
        paths_button.setCursor(Qt.CursorShape.PointingHandCursor)
        paths_button.clicked.connect(self.open_config)
        brand.addWidget(paths_button, 0, Qt.AlignmentFlag.AlignTop)

        settings_button = QPushButton("⚙")
        settings_button.setObjectName("IconButton")
        settings_button.setToolTip("Configuración (Ctrl+,)")
        settings_button.setFixedSize(30, 30)
        settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_button.clicked.connect(self.open_settings)
        brand.addWidget(settings_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(brand)

        self.mfa_row = SidebarItem("mfa", "MFA", self.palette_tokens, indent=8)
        self.mfa_row.setToolTip("Autenticar, o renovar la sesión")
        self.mfa_row.clicked.connect(lambda _: self.authenticate())
        layout.addWidget(self.mfa_row)

        section = QLabel("ENTORNOS")
        section.setObjectName("SidebarSection")
        layout.addWidget(section)

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self._list_container)
        layout.addWidget(scroll, 1)

        layout.addWidget(separator())

        local_section = QLabel("LOCAL")
        local_section.setObjectName("SidebarSection")
        layout.addWidget(local_section)

        local_box = QWidget()
        local_layout = QVBoxLayout(local_box)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(2)
        self.local_items: dict[str, SidebarItem] = {}
        for key, title in (("database", "Base de datos"), ("history", "Historial")):
            item = SidebarItem(key, title, self.palette_tokens, indent=8, show_dot=False)
            item.clicked.connect(self.select_local)
            self.local_items[key] = item
            local_layout.addWidget(item)
        layout.addWidget(local_box)

        self.footer = QLabel("")
        self.footer.setObjectName("FooterText")
        layout.addWidget(self.footer)
        return sidebar

    def _build_detail(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(26, 22, 26, 18)
        layout.setSpacing(14)

        self.banner = Banner()
        layout.addWidget(self.banner)

        self.notice = Notice()
        self.notice.action.clicked.connect(lambda: self.authenticate())
        layout.addWidget(self.notice)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_environment_page())
        self.stack.addWidget(self._build_database_page())
        self.stack.addWidget(self._build_history_page())
        self.stack.addWidget(self._build_empty_page())
        layout.addWidget(self.stack, 1)

        layout.addWidget(self._build_log_card())

        self.progress = ProgressPanel()
        self.progress.cancel_requested.connect(self.cancel_operation)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setObjectName("FooterText")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        return panel

    def _build_environment_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        self.header_dot = StatusDot(self.palette_tokens, diameter=11)
        header.addWidget(self.header_dot, 0, Qt.AlignmentFlag.AlignVCenter)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(2)
        self.env_title = QLabel("")
        self.env_title.setObjectName("DetailTitle")
        self.env_subtitle = ElidingLabel("", object_name="DetailSubtitle")
        titles.addWidget(self.env_title)
        titles.addWidget(self.env_subtitle)
        header.addLayout(titles, 1)

        self.env_pill = Pill("", tone="off")
        header.addWidget(self.env_pill, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)
        layout.addWidget(separator())

        card = Card("CONEXIÓN")
        instance_row, self.value_instance = field_row("instancia", "")
        dns_row, self.value_dns = field_row("dns", "")
        sg_row, self.value_sg = field_row("security group", "")

        self.check_button = QPushButton("Comprobar")
        self.check_button.setObjectName("Ghost")
        self.check_button.setToolTip(
            "Resuelve el DNS y consulta si tu IP ya está autorizada. No cambia nada."
        )
        self.check_button.clicked.connect(self.check_access)
        access_row, self.value_access = field_row("tu IP", "—", trailing=self.check_button)

        for row in (instance_row, dns_row, sg_row, access_row):
            card.add(row)
        layout.addWidget(card)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        self.ssh_button = QPushButton("Abrir SSH")
        self.ssh_button.setObjectName("Primary")
        self.ssh_button.clicked.connect(self.open_ssh)
        self.dump_button = QPushButton("Descargar dump")
        self.dump_button.clicked.connect(self.download_dump)
        self.authorize_button = QPushButton("Autorizar mi IP")
        self.authorize_button.clicked.connect(lambda: self.authorize_ip())
        actions.addWidget(self.ssh_button)
        actions.addWidget(self.dump_button)
        actions.addStretch(1)
        actions.addWidget(self.authorize_button)
        layout.addLayout(actions)
        layout.addStretch(1)
        return page

    def _build_database_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel("Base de datos local")
        title.setObjectName("DetailTitle")
        layout.addWidget(title)
        subtitle = QLabel("Opera sobre el MySQL de esta máquina. No necesita MFA.")
        subtitle.setObjectName("DetailSubtitle")
        layout.addWidget(subtitle)
        layout.addWidget(separator())

        card = Card("DESTINO")
        picker = QWidget()
        picker_layout = QHBoxLayout(picker)
        picker_layout.setContentsMargins(0, 0, 0, 0)
        picker_layout.setSpacing(14)
        label = QLabel("base")
        label.setObjectName("FieldLabel")
        label.setFixedWidth(104)
        self.database_combo = QComboBox()
        self.connect_button = QPushButton("Abrir sesión MySQL")
        self.connect_button.clicked.connect(self.open_local_database)
        picker_layout.addWidget(label)
        picker_layout.addWidget(self.database_combo, 1)
        picker_layout.addWidget(self.connect_button)
        card.add(picker)
        layout.addWidget(card)

        dumps_card = Card()
        dumps_header = QHBoxLayout()
        dumps_header.setContentsMargins(0, 0, 0, 0)
        dumps_header.setSpacing(8)
        dumps_title = QLabel("DUMPS LOCALES")
        dumps_title.setObjectName("CardTitle")
        # De qué entorno es cada dump lo dice el índice, no el nombre del archivo.
        self.dump_filter_combo = QComboBox()
        self.dump_filter_combo.setObjectName("TextCombo")
        self.dump_filter_combo.setToolTip("Mostrar solo los dumps de un entorno")
        self.dump_filter_combo.currentIndexChanged.connect(self._on_dump_filter_changed)
        open_dumps = QPushButton("Abrir carpeta")
        open_dumps.setObjectName("Ghost")
        open_dumps.clicked.connect(self.open_dump_folder)
        dumps_header.addWidget(dumps_title)
        dumps_header.addStretch(1)
        dumps_header.addWidget(self.dump_filter_combo)
        dumps_header.addWidget(open_dumps)
        dumps_card.add_layout(dumps_header)

        self.dumps_table = data_table(
            ["ARCHIVO", "ENTORNO", "TAMAÑO", "MODIFICADO"], right_aligned=(2, 3)
        )
        self.dumps_table.setMinimumHeight(124)
        self.dumps_table.doubleClicked.connect(lambda _: self.recreate_database())
        self.dumps_table.itemSelectionChanged.connect(self._on_dump_row_selected)
        dumps_card.add(self.dumps_table, stretch=1)

        self.dumps_empty = QLabel("")
        self.dumps_empty.setObjectName("FieldHint")
        self.dumps_empty.hide()
        dumps_card.add(self.dumps_empty)

        # Un archivo elegido a mano puede estar fuera de la carpeta de dumps, así
        # que no aparece en la tabla: se muestra acá para que se vea cuál es.
        self.chosen_row = QWidget()
        chosen_layout = QHBoxLayout(self.chosen_row)
        chosen_layout.setContentsMargins(0, 0, 0, 0)
        chosen_layout.setSpacing(8)
        chosen_caption = QLabel("archivo elegido")
        chosen_caption.setObjectName("FieldLabel")
        chosen_caption.setFixedWidth(104)
        self.chosen_label = ElidingLabel("", object_name="FieldValue")
        clear_chosen = QPushButton("✕")
        clear_chosen.setObjectName("Ghost")
        clear_chosen.setFixedWidth(28)
        clear_chosen.setToolTip("Volver a usar la lista")
        clear_chosen.clicked.connect(self.clear_chosen_dump)
        chosen_layout.addWidget(chosen_caption)
        chosen_layout.addWidget(self.chosen_label, 1)
        chosen_layout.addWidget(clear_chosen)
        self.chosen_row.hide()
        dumps_card.add(self.chosen_row)

        recreate_row = QHBoxLayout()
        recreate_row.setContentsMargins(0, 0, 0, 0)
        recreate_row.setSpacing(8)
        self.browse_button = QPushButton("Elegir archivo…")
        self.browse_button.setToolTip(
            "Importar un .sql o .sql.gz de cualquier carpeta, esté o no en la lista"
        )
        self.browse_button.clicked.connect(self.browse_for_dump)
        recreate_row.addWidget(self.browse_button)
        recreate_row.addStretch(1)
        self.recreate_button = QPushButton("Recrear base")
        self.recreate_button.setObjectName("Primary")
        self.recreate_button.clicked.connect(self.recreate_database)
        recreate_row.addWidget(self.recreate_button)
        dumps_card.add_layout(recreate_row)

        layout.addWidget(dumps_card, 1)
        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Historial de operaciones")
        title.setObjectName("DetailTitle")
        self.history_subtitle = QLabel("")
        self.history_subtitle.setObjectName("DetailSubtitle")
        titles.addWidget(title)
        titles.addWidget(self.history_subtitle)
        header.addLayout(titles, 1)
        open_logs = QPushButton("Abrir carpeta")
        open_logs.setObjectName("Ghost")
        open_logs.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.backend.logs_directory()))
            )
        )
        header.addWidget(open_logs)
        layout.addLayout(header)
        layout.addWidget(separator())

        # Los logs ya son JSON por línea, así que van a una tabla sin parsear texto.
        self.history_table = data_table(
            ["CUÁNDO", "OPERACIÓN", "DUMP", "ENTORNO / BASE", "DURACIÓN", "TAMAÑO"],
            right_aligned=(4, 5),
        )
        layout.addWidget(self.history_table, 1)
        return page

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(10)
        layout.addStretch(1)

        self.empty_title = QLabel("No se pudo cargar la configuración")
        self.empty_title.setObjectName("EmptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_body = QLabel("")
        self.empty_body.setObjectName("EmptyBody")
        self.empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_body.setWordWrap(True)

        row = QHBoxLayout()
        row.addStretch(1)
        retry = QPushButton("Reintentar")
        retry.setObjectName("Primary")
        retry.clicked.connect(self.reload_config)
        row.addWidget(retry)
        row.addStretch(1)

        layout.addWidget(self.empty_title)
        layout.addWidget(self.empty_body)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    def _build_log_card(self) -> QWidget:
        card = Card()
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title = QLabel("LOG")
        title.setObjectName("CardTitle")
        self.follow_check = QPushButton("seguir")
        self.follow_check.setObjectName("Chip")
        self.follow_check.setCheckable(True)
        self.follow_check.setChecked(True)
        self.follow_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.follow_check.setToolTip("Mantener el log pegado al final")
        clear = QPushButton("Limpiar")
        clear.setObjectName("Ghost")
        clear.clicked.connect(lambda: self.log_view.setPlainText(""))
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.follow_check)
        header.addWidget(clear)
        card.add_layout(header)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("LogView")
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(LOG_LIMIT)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Alto flexible: fijarlo dejaba la pagina de BD sin espacio y los
        # widgets se solapaban en vez de encogerse.
        self.log_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.log_view.setMinimumHeight(84)
        self.log_view.setMaximumHeight(120)
        card.add(self.log_view)
        return card

    def _build_shortcuts(self) -> None:
        for sequence, handler in (
            ("Ctrl+,", self.open_settings),
            ("Ctrl+M", lambda: self.authenticate()),
            ("Ctrl+R", lambda: self.refresh(force=True)),
            ("Ctrl+Q", self.close),
            ("Ctrl+W", self.close),
        ):
            QShortcut(QKeySequence(sequence), self, activated=handler)

    # ---- paleta -----------------------------------------------------------

    def apply_palette(self, palette: Palette) -> None:
        self.palette_tokens = palette
        self.header_dot.apply_palette(palette)
        self.mfa_row.apply_palette(palette)
        for item in self._items.values():
            item.apply_palette(palette)

    # ---- estado -----------------------------------------------------------

    def refresh(self, force: bool = False) -> None:
        if not force:
            fingerprint = self.backend.fingerprint()
            if fingerprint == self._fingerprint:
                return
            self._fingerprint = fingerprint
        else:
            self._fingerprint = self.backend.fingerprint()

        self.snapshot = self.backend.snapshot()
        self._sync_sidebar()
        self._sync_notice()
        self._sync_page()
        self.snapshot_changed.emit(self.snapshot)

    def _sync_sidebar(self) -> None:
        session = self.snapshot.session
        tone = {"active": "success", "inherited": "warning", "not_required": "accent"}.get(
            session.state, "danger"
        )
        self.mfa_row.update_content(session.text, session.usable, tone)

        wanted_groups = {env.id for env in self.snapshot.environments}
        wanted_items = {t.id for env in self.snapshot.environments for t in env.types}
        for key, group in list(self._groups.items()):
            if key not in wanted_groups:
                self._list_layout.removeWidget(group)
                group.deleteLater()
                del self._groups[key]
        for key, item in list(self._items.items()):
            if key not in wanted_items:
                self._list_layout.removeWidget(item)
                item.deleteLater()
                del self._items[key]

        position = 0
        for env in self.snapshot.environments:
            group = self._groups.get(env.id)
            if group is None:
                group = SidebarGroup(env.id, env.name)
                group.toggled.connect(self.toggle_group)
                self._groups[env.id] = group
            expanded = env.id not in self._collapsed
            group.update_content(expanded, len(env.types))
            self._list_layout.insertWidget(position, group)
            position += 1

            for env_type in env.types:
                item = self._items.get(env_type.id)
                if item is None:
                    item = SidebarItem(
                        env_type.id, env_type.name, self.palette_tokens, indent=26
                    )
                    item.clicked.connect(self.select_environment)
                    self._items[env_type.id] = item
                self._list_layout.insertWidget(position, item)
                position += 1
                item.setVisible(expanded)
                plan = self._access.get(env_type.id)
                item.update_content(
                    env_type.instance_name or env_type.instance_id,
                    plan is not None and plan.up_to_date,
                )
                item.set_selected(self.selection == ("environment", env_type.id))

        for key, item in self.local_items.items():
            item.set_selected(self.selection == ("local", key))

        self.footer.setText(
            f"{len(self.snapshot.environments)} entornos · {self.snapshot.type_count} tipos"
            if self.snapshot.loaded
            else "sin configuración"
        )

    def _sync_notice(self) -> None:
        session = self.snapshot.session
        if not self.snapshot.loaded:
            self.notice.hide()
            return
        if session.usable:
            if session.state == "inherited":
                self.notice.show_message(
                    "Usando una sesión AWS heredada del entorno: no se sabe cuándo caduca.",
                    "Renovar",
                )
            else:
                self.notice.hide()
            return
        self.notice.show_message(
            "Sin sesión MFA válida: SSH, dumps y Security Groups están deshabilitados.",
            "Autenticar",
        )

    def _sync_page(self) -> None:
        if not self.snapshot.loaded:
            self.empty_body.setText(self.snapshot.error or "Revisá los archivos de configuración.")
            self.stack.setCurrentIndex(PAGE_EMPTY)
            self._set_controls_enabled()
            return

        kind, key = self.selection
        if kind == "environment":
            env_type = self.snapshot.find_type(key)
            if env_type is None:
                self.selection = ("local", "database")
                kind, key = self.selection
            else:
                self._sync_environment(env_type)
                self.stack.setCurrentIndex(PAGE_ENVIRONMENT)

        if kind == "local":
            if key == "database":
                self._sync_database()
                self.stack.setCurrentIndex(PAGE_DATABASE)
            else:
                self._sync_history()
                self.stack.setCurrentIndex(PAGE_HISTORY)

        self._set_controls_enabled()

    def _sync_environment(self, env_type: EnvironmentType) -> None:
        self.env_title.setText(env_type.label)
        self.env_subtitle.set_full_text(env_type.instance_name or "sin nombre de instancia")
        self.env_pill.setText(env_type.env_type.upper() or env_type.name)
        self.env_pill.set_tone("warn" if env_type.env_type.lower() == "prod" else "info")

        self.value_instance.set_full_text(env_type.instance_id or "—")
        dns = self.backend.known_dns(env_type)
        self.value_dns.set_full_text(dns or "— (dinámico, se resuelve al conectar)")
        self.value_sg.set_full_text(env_type.security_group_id or "— (sin security group)")

        plan = self._access.get(env_type.id)
        if plan is None:
            self.value_access.set_full_text("—")
        else:
            self.value_access.set_full_text(f"{plan.current_ip} · {plan.summary}")
        self.header_dot.set_active(plan is not None and plan.up_to_date)

    def _sync_database(self) -> None:
        current = self.database_combo.currentData()
        self.database_combo.blockSignals(True)
        self.database_combo.clear()
        for key, name in self.snapshot.databases:
            self.database_combo.addItem(name, key)
        if current is not None:
            index = self.database_combo.findData(current)
            if index >= 0:
                self.database_combo.setCurrentIndex(index)
        self.database_combo.blockSignals(False)

        self._sync_dump_filters()
        self._sync_dumps_table()

    def _sync_dump_filters(self) -> None:
        filters = self.backend.dump_filters()
        current = self.dump_filter_combo.currentData()
        if [f.key for f in filters] == [f.key for f in self._dump_filters]:
            return

        self._dump_filters = filters
        self.dump_filter_combo.blockSignals(True)
        self.dump_filter_combo.clear()
        for dump_filter in filters:
            self.dump_filter_combo.addItem(dump_filter.label, dump_filter.key)
        index = self.dump_filter_combo.findData(current)
        self.dump_filter_combo.setCurrentIndex(max(index, 0))
        self.dump_filter_combo.blockSignals(False)

    def _visible_dumps(self) -> tuple:
        key = self.dump_filter_combo.currentData()
        chosen = next((f for f in self._dump_filters if f.key == key), None)
        if chosen is None:
            return self.snapshot.dumps
        return tuple(dump for dump in self.snapshot.dumps if chosen.matches(dump))

    def _sync_dumps_table(self) -> None:
        dumps = self._visible_dumps()
        selected = self._selected_dump_name()

        self.dumps_table.blockSignals(True)
        self.dumps_table.setRowCount(len(dumps))
        for row, dump in enumerate(dumps):
            set_table_row(
                self.dumps_table, row,
                (dump.name, dump.origin, format_size(dump.size_mb), dump.modified_text),
                right_aligned=(2, 3),
            )
        if dumps:
            names = [dump.name for dump in dumps]
            index = names.index(selected) if selected in names else 0
            self.dumps_table.selectRow(index)
        self.dumps_table.blockSignals(False)

        if dumps:
            self.dumps_empty.hide()
        else:
            label = self.dump_filter_combo.currentText().strip()
            self.dumps_empty.setText(
                f"Ningún dump de «{label}» en {self.snapshot.dump_directory}."
                if self.dump_filter_combo.currentData() not in (None, "all")
                else f"No hay dumps en {self.snapshot.dump_directory}."
            )
            self.dumps_empty.show()

    def _on_dump_filter_changed(self) -> None:
        self._sync_dumps_table()
        self._set_controls_enabled()

    def _on_dump_row_selected(self) -> None:
        # Elegir de la lista descarta el archivo externo: si no, no se sabría cuál
        # de los dos se va a importar.
        if self._chosen_dump is not None and self.dumps_table.currentRow() >= 0:
            self.clear_chosen_dump()

    def _sync_history(self) -> None:
        entries = self.backend.history()
        self.history_subtitle.setText(f"{len(entries)} operaciones registradas")
        self.history_table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            operation = "descarga" if entry.kind == "dump" else "recrear BD"
            target = entry.database or entry.environment
            size = format_size(entry.size_mb) if entry.size_mb else ""
            set_table_row(
                self.history_table, row,
                (entry.when, operation, entry.dump_name, target, entry.duration, size),
                right_aligned=(4, 5),
            )

    def _selected_dump_name(self) -> Optional[str]:
        row = self.dumps_table.currentRow()
        item = self.dumps_table.item(row, 0) if row >= 0 else None
        return item.text() if item is not None else None

    def _dump_to_recreate(self) -> Optional[tuple[Path, float]]:
        """El archivo que se importaría: el elegido a mano, o el de la lista."""
        if self._chosen_dump is not None:
            try:
                return self._chosen_dump, self._chosen_dump.stat().st_size / (1024 * 1024)
            except OSError:
                return None
        name = self._selected_dump_name()
        if not name:
            return None
        dump = next((d for d in self._visible_dumps() if d.name == name), None)
        return (dump.path, dump.size_mb) if dump is not None else None

    def browse_for_dump(self) -> None:
        """Elegir un .sql o .sql.gz de cualquier carpeta, no solo de la lista."""
        start = self.snapshot.dump_directory or Path.home()
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Elegir dump SQL",
            str(start),
            "Dumps SQL (*.sql *.sql.gz);;Todos los archivos (*)",
        )
        if not path:
            return
        self._chosen_dump = Path(path)
        self.chosen_label.set_full_text(path)
        self.chosen_row.show()
        self.dumps_table.clearSelection()
        self._set_controls_enabled()

    def clear_chosen_dump(self) -> None:
        self._chosen_dump = None
        self.chosen_row.hide()
        self.chosen_label.set_full_text("")
        self._set_controls_enabled()

    def _set_controls_enabled(self) -> None:
        idle = not self.busy
        remote = idle and self.snapshot.session.usable and self.snapshot.loaded
        env_type = self._current_environment()
        has_sg = env_type is not None and bool(env_type.security_group_id)

        self.ssh_button.setEnabled(remote)
        self.dump_button.setEnabled(remote)
        self.check_button.setEnabled(remote and has_sg)
        self.authorize_button.setEnabled(remote and has_sg)
        self.recreate_button.setEnabled(idle and self._dump_to_recreate() is not None)
        self.browse_button.setEnabled(idle)
        self.connect_button.setEnabled(idle and self.database_combo.count() > 0)
        self.mfa_row.setEnabled(idle)

        reason = "" if remote else "Necesita una sesión MFA válida."
        for button in (self.ssh_button, self.dump_button):
            button.setToolTip(reason)
        for button in (self.check_button, self.authorize_button):
            button.setToolTip(
                reason if reason else
                ("" if has_sg else "Este entorno no tiene security_group_id configurado.")
            )

    def _current_environment(self) -> Optional[EnvironmentType]:
        kind, key = self.selection
        if kind != "environment":
            return None
        return self.snapshot.find_type(key)

    # ---- navegacion -------------------------------------------------------

    def select_environment(self, type_id: str) -> None:
        if self.selection == ("environment", type_id):
            return
        self.selection = ("environment", type_id)
        self.banner.hide()
        self._sync_sidebar()
        self._sync_page()

    def select_local(self, key: str) -> None:
        if self.selection == ("local", key):
            return
        self.selection = ("local", key)
        self.banner.hide()
        self._sync_sidebar()
        self._sync_page()

    def toggle_group(self, env_id: str) -> None:
        if env_id in self._collapsed:
            self._collapsed.discard(env_id)
        else:
            self._collapsed.add(env_id)
        self._sync_sidebar()

    # ---- log --------------------------------------------------------------

    def _append_log(self, line: str) -> None:
        scrollbar = self.log_view.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 4
        self.log_view.appendPlainText(line)
        if self.follow_check.isChecked() or at_bottom:
            scrollbar.setValue(scrollbar.maximum())

    # ---- ejecucion --------------------------------------------------------

    def _start(
        self,
        work: Callable[[], Any],
        signals: _TaskSignals,
        pending: str,
        then: Optional[Callable[[Any], None]] = None,
        cancellable: bool = False,
    ) -> None:
        if self.busy:
            return
        self.busy = True
        self._cancel.clear()
        self._then = then
        self.status_label.setText(pending)
        self.banner.hide()
        self._set_controls_enabled()
        if cancellable:
            self.progress.start(cancellable=True)

        signals.finished.connect(self._on_finished)
        signals.failed.connect(self._on_failed)
        signals.progress.connect(self.progress.update_progress)
        self._pool.start(_Task(work, signals))

    def _run(
        self,
        work: Callable[[], Any],
        pending: str,
        then: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self._start(work, _TaskSignals(), pending, then)

    def _run_with_progress(
        self,
        build: Callable[[Callable[..., None], Callable[[], bool]], Callable[[], Any]],
        pending: str,
        then: Optional[Callable[[Any], None]] = None,
    ) -> None:
        signals = _TaskSignals()
        work = build(signals.progress.emit, self._cancel.is_set)
        self._start(work, signals, pending, then, cancellable=True)

    def _on_finished(self, result: Any) -> None:
        self.busy = False
        self.progress.finish()
        if isinstance(result, str) and result:
            self.status_label.setText(result)
        then, self._then = self._then, None
        self.refresh(force=True)
        if then is not None:
            then(result)

    def _on_failed(self, message: str) -> None:
        self.busy = False
        self._then = None
        self.progress.finish()
        self.status_label.setText("")
        self.banner.show_message(message)
        self.refresh(force=True)

    def cancel_operation(self) -> None:
        self._cancel.set()
        self.progress.cancel.setEnabled(False)
        self.status_label.setText("Cancelando…")

    # ---- acciones ---------------------------------------------------------

    def authenticate(self, then: Optional[Callable[[Any], None]] = None) -> None:
        if self.busy:
            return
        self.show_window()
        dialog = MfaDialog(self.snapshot.session, self)
        if dialog.exec() != MfaDialog.DialogCode.Accepted:
            return
        code = dialog.value()
        self._run(lambda: self.backend.authenticate(code), "Autenticando con MFA…", then)

    def check_access(self) -> None:
        env_type = self._current_environment()
        if env_type is None:
            return
        self._run(
            lambda: self._probe(env_type),
            f"Comprobando acceso a {env_type.label}…",
        )

    def _probe(self, env_type: EnvironmentType) -> str:
        """DNS plus Security Group status, without changing anything in AWS."""
        dns = self.backend.resolve_dns(env_type)
        plan = self.backend.security_group_plan(env_type)
        self._access[env_type.id] = plan
        return f"{dns} · {plan.summary}"

    def authorize_ip(self, then: Optional[Callable[[Any], None]] = None) -> None:
        env_type = self._current_environment()
        if env_type is None:
            return
        self._run(
            lambda: self.backend.security_group_plan(env_type),
            f"Consultando el Security Group de {env_type.label}…",
            lambda plan: self._confirm_authorize(env_type, plan, then),
        )

    def _confirm_authorize(
        self,
        env_type: EnvironmentType,
        plan: SecurityGroupPlan,
        then: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self._access[env_type.id] = plan
        if plan.up_to_date:
            self.status_label.setText(f"{plan.current_ip} ya está autorizada.")
            self._sync_page()
            if then is not None:
                then(None)
            return

        # Autorizar revoca la regla vieja: desde una GUI es fácil hacer click sin
        # leer, así que se dice antes qué se revoca y qué se autoriza.
        revoked = (
            f"Se revoca la regla actual {plan.existing_rule_ip}\n"
            if plan.existing_rule_ip else ""
        )
        accepted = confirm(
            self,
            "Modificar Security Group",
            f"Autorizar tu IP en {plan.security_group_id}?",
            "Autorizar",
            informative=(
                f"{revoked}"
                f"Se autoriza {plan.current_ip}/32 en el puerto 22\n"
                f"Descripción de la regla: {plan.description or '(vacía)'}\n"
                f"Entorno: {env_type.label}"
            ),
        )
        if not accepted:
            return
        self._run(
            lambda: self.backend.authorize_ip(env_type),
            f"Autorizando {plan.current_ip} en {plan.security_group_id}…",
            lambda _result: self._after_authorize(env_type, then),
        )

    def _after_authorize(
        self, env_type: EnvironmentType, then: Optional[Callable[[Any], None]]
    ) -> None:
        self._access[env_type.id] = SecurityGroupPlan(
            security_group_id=env_type.security_group_id,
            current_ip=self._access[env_type.id].current_ip,
            description=self._access[env_type.id].description,
            already_authorized=True,
        )
        self._sync_page()
        if then is not None:
            then(None)

    def _with_access(self, action: Callable[[], None]) -> None:
        """Make sure the IP is authorized, then run the remote action."""
        env_type = self._current_environment()
        if env_type is None:
            return
        if not env_type.security_group_id:
            # Sin SG configurado no hay nada que autorizar: se intenta igual, que es
            # lo que hace el CLI, y el error de red será el que explique.
            action()
            return
        plan = self._access.get(env_type.id)
        if plan is not None and plan.up_to_date:
            action()
            return
        self.authorize_ip(then=lambda _result: action())

    def open_ssh(self) -> None:
        env_type = self._current_environment()
        if env_type is None:
            return
        self._with_access(
            lambda: self._run(
                lambda: self.backend.open_ssh(env_type),
                f"Abriendo SSH a {env_type.label}…",
            )
        )

    def download_dump(self) -> None:
        env_type = self._current_environment()
        if env_type is None:
            return
        self._with_access(
            lambda: self._run(
                lambda: self.backend.remote_dumps(env_type),
                f"Listando dumps en {env_type.label}…",
                lambda dumps: self._pick_dump(env_type, dumps),
            )
        )

    def _pick_dump(self, env_type: EnvironmentType, dumps: tuple) -> None:
        if not dumps:
            self.banner.show_message(
                f"No se encontraron archivos ~/dump*.sql.gz en {env_type.label}."
            )
            return
        dialog = RemoteDumpDialog(dumps, env_type.label, self)
        if dialog.exec() != RemoteDumpDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected()
        if chosen is None:
            return

        # Siempre se confirma antes de bajar: una descarga puede ser de varios GB
        # y tarda. Si además pisa un archivo, la confirmación lo dice y se marca
        # como destructiva.
        destination = self.backend.local_path_for(env_type, chosen.name)
        overwrites = destination.exists()
        details = (
            f"Entorno: {env_type.label}\n"
            f"Tamaño: {chosen.size}\n"
            f"Destino: {destination}"
        )
        if not confirm(
            self,
            "El archivo ya existe" if overwrites else "Descargar dump",
            f"Ya hay un {destination.name} descargado. ¿Sobrescribirlo?" if overwrites
            else f"¿Descargar {chosen.name}?",
            "Sobrescribir" if overwrites else "Descargar",
            informative=details,
            destructive=overwrites,
        ):
            return

        self._run_with_progress(
            lambda report, cancelled: (
                lambda: self.backend.download_dump(
                    env_type, chosen.name, on_progress=report, should_cancel=cancelled
                )
            ),
            f"Descargando {chosen.name} ({chosen.size})…",
        )

    def recreate_database(self) -> None:
        if self.busy:
            return
        database = self.database_combo.currentText()
        target = self._dump_to_recreate()
        if not database or target is None:
            return
        path, size_mb = target

        accepted = confirm(
            self,
            "Recrear base de datos",
            f"Recrear '{database}' desde {path.name}?",
            "Recrear",
            informative=(
                f"Se ejecuta DROP DATABASE {database} y se importa el dump completo.\n"
                f"Los datos actuales de '{database}' se pierden.\n"
                f"Archivo: {path}\n"
                f"Tamaño: {format_size(size_mb)}"
            ),
            destructive=True,
        )
        if not accepted:
            return

        self._run_with_progress(
            lambda report, _cancelled: (
                lambda: self.backend.recreate_database(database, path, on_progress=report)
            ),
            f"Recreando '{database}' desde {path.name}…",
        )

    def open_local_database(self) -> None:
        database = self.database_combo.currentText()
        if not database:
            return
        self._run(
            lambda: self.backend.open_local_database(database),
            f"Abriendo MySQL en {database}…",
        )

    def open_dump_folder(self) -> None:
        directory = self.snapshot.dump_directory
        if directory is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def open_config(self) -> None:
        """Solo lectura: qué archivos se están usando y dónde."""
        self.show_window()
        ConfigDialog(self.backend, self).exec()

    def open_settings(self) -> None:
        if self.busy:
            self.status_label.setText(
                "Hay una operación en curso: esperá a que termine para editar la configuración."
            )
            return
        self.show_window()
        SettingsDialog(self.backend, self).exec()
        # La configuración pudo cambiar entera (incluso por una importación):
        # se descartan los datos derivados y se vuelve a leer todo.
        self._access.clear()
        self._dump_filters = ()
        self.refresh(force=True)

    def reload_config(self) -> None:
        self.backend.load()
        self._access.clear()
        self.refresh(force=True)

    def _warn_about_environment(self) -> None:
        missing = missing_tools()
        if missing:
            self.banner.show_message(
                "Faltan herramientas requeridas: " + ", ".join(missing)
            )
        if not self.snapshot.loaded and self.snapshot.error:
            self.log_line.emit(self.snapshot.error)

    # ---- ciclo de vida ----------------------------------------------------

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.refresh(force=True)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Cerrar la ventana termina el proceso. No hay segundo plano.

        Es una decisión de seguridad: las credenciales temporales de la sesión MFA
        viven en el entorno de este proceso, así que dejarlo corriendo escondido
        las mantendría disponibles por horas sin nada en pantalla que lo recuerde.
        """
        if self.busy and not confirm(
            self,
            "Operación en curso",
            "Hay una operación corriendo.",
            "Salir igual",
            informative=(
                "Salir la interrumpe. Una descarga a medias se descarta; un import "
                "de MySQL cortado deja la base incompleta."
            ),
            destructive=True,
        ):
            event.ignore()
            return

        # Aunque el proceso esté por terminar, el token se borra explícitamente:
        # deja de estar en el entorno de cualquier terminal que hayamos lanzado.
        self.backend.sign_out()
        event.accept()
        self.quit_requested.emit()



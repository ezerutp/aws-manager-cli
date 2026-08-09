"""Application entry point: theme, single instance and window.

La app no corre en segundo plano: no hay icono de bandeja y cerrar la
ventana termina el proceso. Es deliberado — ver `closeEvent` en window.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .core import CODENAME, VERSION, Backend
from .icons import app_icon, icon_pixmap
from .theme import DARK, LIGHT, UI_FONTS, Palette, stylesheet
from .window import MainWindow


# Qt deriva el app id de Wayland del nombre del archivo .desktop, y ese id es
# también el WM class de la ventana. Si el lanzador declara otro, el shell
# muestra la ventana como una app desconocida, separada de su icono.
APP_ID = "aws-manager-ui"
DESKTOP_FILE = f"{APP_ID}.desktop"
EXEC_ENV = "AWS_MANAGER_UI_EXEC"
APPLICATIONS_DIR_ENV = "AWS_MANAGER_UI_APPLICATIONS_DIR"
ICON_DIR_ENV = "AWS_MANAGER_UI_ICON_DIR"


def applications_dir() -> Path:
    override = os.environ.get(APPLICATIONS_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "applications"


def icon_dir() -> Path:
    override = os.environ.get(ICON_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aws-manager-ui",
        description="Interfaz gráfica para aws-manager: entornos AWS, dumps y BD local.",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="store_true",
        help="Muestra la versión y sale.",
    )
    parser.add_argument(
        "--install-desktop-entry",
        action="store_true",
        help="Crea el lanzador en ~/.local/share/applications y sale.",
    )
    return parser


def palette_for(app: QApplication) -> Palette:
    return DARK if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else LIGHT


def install_desktop_entry() -> int:
    """Write a launcher so the app shows up in the applications list."""
    applications = applications_dir()
    icons = icon_dir()
    applications.mkdir(parents=True, exist_ok=True)
    icons.mkdir(parents=True, exist_ok=True)

    # Dibujar el icono necesita una QGuiApplication; offscreen la mantiene headless.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication(sys.argv[:1])
    icon_path = icons / f"{APP_ID}.png"
    icon_pixmap(DARK, 256).save(str(icon_path), "PNG")

    # El instalador conoce el lanzador que escribió y lo pasa acá. Si no, se deduce
    # de cómo arrancó este proceso: con `python -m aws_ui`, argv[0] es un módulo
    # que nadie puede ejecutar.
    command = os.environ.get(EXEC_ENV, "")
    if not command:
        launcher = Path(sys.argv[0]).resolve()
        if launcher.suffix == ".py" or launcher.name.startswith("python"):
            command = f"{sys.executable} -m aws_ui"
        else:
            command = str(launcher)

    entry = applications / DESKTOP_FILE
    entry.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=aws-manager\n"
        "Comment=Entornos AWS, dumps SQL y bases de datos locales\n"
        f"Exec={command}\n"
        f"Icon={APP_ID}\n"
        "Terminal=false\n"
        # Una sola categoría principal: dos pueden listar la app dos veces.
        "Categories=Development;\n"
        "Keywords=aws;ec2;ssh;mysql;dump;bastion;\n"
        "StartupNotify=true\n"
        f"StartupWMClass={APP_ID}\n",
        encoding="utf-8",
    )
    print(f"Lanzador creado en {entry}")
    print(f"Icono creado en {icon_path}")
    del app
    return 0


def _claim_single_instance(name: str) -> QLocalServer | None:
    """Return the listening server, or None when another instance answered."""
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(300):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(300)
        probe.disconnectFromServer()
        return None

    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)
    return server


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(f'AWS Manager UI v{VERSION} "{CODENAME}"')
        return 0
    if args.install_desktop_entry:
        return install_desktop_entry()

    QApplication.setApplicationName("aws-manager")
    QApplication.setApplicationDisplayName("aws-manager")
    # Reclamar un archivo .desktop que nunca se instaló hace que el portal se
    # queje en cada arranque, así que solo se anuncia si ya existe.
    if (applications_dir() / DESKTOP_FILE).exists():
        QApplication.setDesktopFileName(APP_ID)
    # A Qt solo le va el nombre del programa: nuestros flags ya están parseados y
    # tomaría algunos como propios.
    app = QApplication(sys.argv[:1])
    # Sin ventanas no queda nada corriendo. `closeEvent` ya pide salir de
    # forma explícita; esto es la red por si ese camino no se recorre.
    app.setQuitOnLastWindowClosed(True)

    server = _claim_single_instance(f"aws-manager-ui-{os.getuid()}")
    if server is None:
        print("aws-manager ya está corriendo; se pidió mostrar su ventana.")
        return 0

    font = QFont()
    font.setFamilies(UI_FONTS)
    font.setPointSize(10)
    app.setFont(font)

    palette = palette_for(app)
    app.setStyleSheet(stylesheet(palette))
    app.setWindowIcon(app_icon(palette))

    backend = Backend()
    window = MainWindow(backend, palette)
    # La carga va despues de construir la ventana: es ahi donde el Backend
    # engancha su salida al panel de log, y si no, las lineas de arranque
    # ("Configuracion cargada desde...") se perderian.
    #
    # Lanzada desde el menu del escritorio, la app no hereda lo que exporta
    # `.zshrc`: systemd le pasa su propio entorno. Se le pregunta al shell de
    # login antes de mirar la configuracion, que es cuando importa.
    backend.adopt_shell_environment()
    backend.load()
    window.refresh(force=True)

    window.quit_requested.connect(app.quit)
    server.newConnection.connect(lambda: _handle_new_connection(server, window))

    def on_scheme_changed() -> None:
        new_palette = palette_for(app)
        app.setStyleSheet(stylesheet(new_palette))
        app.setWindowIcon(app_icon(new_palette))
        window.apply_palette(new_palette)

    app.styleHints().colorSchemeChanged.connect(on_scheme_changed)

    window.show()
    return app.exec()


def _handle_new_connection(server: QLocalServer, window: MainWindow) -> None:
    connection = server.nextPendingConnection()
    if connection is not None:
        connection.disconnected.connect(connection.deleteLater)
    window.show_window()


if __name__ == "__main__":
    raise SystemExit(main())

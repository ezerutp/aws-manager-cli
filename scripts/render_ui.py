#!/usr/bin/env python3
"""Render the window offscreen to PNG, in both themes.

Sirve para revisar el diseño sin abrir la app. En proxy-local este render encontró
cuatro defectos visuales antes de correrla una sola vez.

    python3 scripts/render_ui.py [directorio-de-salida]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from aws_ui.core import Backend  # noqa: E402
from aws_ui.theme import DARK, LIGHT, UI_FONTS, stylesheet  # noqa: E402
from aws_ui.settings import SettingsDialog  # noqa: E402
from aws_ui.window import PAGE_DATABASE, PAGE_HISTORY, MainWindow  # noqa: E402


VIEWS = (
    ("entorno", lambda window: window.select_environment(_first_type_id(window))),
    ("bd-local", lambda window: window.select_local("database")),
    ("historial", lambda window: window.select_local("history")),
)


def _first_type_id(window: MainWindow) -> str:
    for environment in window.snapshot.environments:
        for env_type in environment.types:
            return env_type.id
    return ""


def render(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    font = QFont()
    font.setFamilies(UI_FONTS)
    font.setPointSize(10)
    app.setFont(font)

    written = []
    for palette in (DARK, LIGHT):
        app.setStyleSheet(stylesheet(palette))
        backend = Backend()
        window = MainWindow(backend, palette)
        backend.load()
        window.refresh(force=True)
        window.resize(1120, 740)
        window.show()

        for name, select in VIEWS:
            select(window)
            app.processEvents()
            path = output / f"{name}-{palette.name}.png"
            window.grab().save(str(path))
            written.append(path)

        # La configuración es un diálogo: se renderiza pestaña por pestaña.
        settings = SettingsDialog(backend, window)
        settings.resize(960, 720)
        settings.show()
        for index in range(settings.tabs.count()):
            settings.tabs.setCurrentIndex(index)
            if index == 2:
                settings._select_path((0, 0))  # un tipo, para ver el form completo
            app.processEvents()
            path = output / f"config{index}-{palette.name}.png"
            settings.grab().save(str(path))
            written.append(path)
        settings.close()

        window.close()
        del window

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/ui-render")
    raise SystemExit(render(target))

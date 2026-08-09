"""Tests that do need PySide6. El resto del suite corre sin el extra [ui]."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import (
        QApplication,
        QLineEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    from aws_ui.core import Backend, RemoteDump
    from aws_ui.dialogs import RemoteDumpDialog
    from aws_ui.theme import DARK, LIGHT, stylesheet
    from aws_ui.widgets import (
        ElidingLabel,
        Pill,
        ProgressPanel,
        SidebarGroup,
        SidebarItem,
        data_table,
        set_table_row,
    )
    from aws_ui.settings import SecretField, SettingsDialog
    from aws_ui.window import PAGE_DATABASE, PAGE_ENVIRONMENT, PAGE_HISTORY, MainWindow

    HAS_QT = True
except ImportError:  # pragma: no cover - depende de si el extra esta instalado
    HAS_QT = False

from tests.test_aws_ui import _write_config  # noqa: E402
from awsm_cli.config import ConfigManager  # noqa: E402


def _application() -> "QApplication":
    return QApplication.instance() or QApplication(sys.argv[:1])


@unittest.skipUnless(HAS_QT, "PySide6 hace falta para las pruebas de widgets")
class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _application()

    def test_a_sidebar_row_has_no_dead_click_zones(self):
        """Un label seleccionable se come el click y deja franjas muertas."""
        item = SidebarItem("prod", "PROD", DARK)
        item.resize(220, 44)
        for x in (6, 40, 110, 210):
            for y in (4, 22, 40):
                self.assertIsNone(
                    item.childAt(QPoint(x, y)),
                    f"({x}, {y}) lo captura un hijo en vez de la fila",
                )

    def test_clicking_a_row_emits_its_key(self):
        item = SidebarItem("ops_prod", "PROD", DARK)
        seen: list[str] = []
        item.clicked.connect(seen.append)
        item.mousePressEvent(_left_click(item))
        self.assertEqual(seen, ["ops_prod"])

    def test_a_group_row_reports_its_own_key(self):
        group = SidebarGroup("ops", "OPS")
        seen: list[str] = []
        group.toggled.connect(seen.append)
        group.mousePressEvent(_left_click(group))
        self.assertEqual(seen, ["ops"])
        group.update_content(expanded=False, type_count=2)
        self.assertEqual(group.chevron.text(), "▸")
        group.update_content(expanded=True, type_count=2)
        self.assertEqual(group.chevron.text(), "▾")

    def test_pill_tone_survives_a_repolish(self):
        pill = Pill("PROD", tone="off")
        pill.set_tone("warn")
        self.assertEqual(pill.property("tone"), "warn")

    def test_eliding_label_keeps_the_full_text_in_the_tooltip(self):
        dns = "ec2-3-87-86-55.compute-1.amazonaws.com"
        # Qt no entrega resizeEvent a un widget oculto, así que la elisión se
        # comprueba dentro de un contenedor mostrado, como en la ventana real.
        host = QWidget()
        layout = QVBoxLayout(host)
        label = ElidingLabel(dns)
        layout.addWidget(label)
        host.resize(90, 40)
        host.show()
        self.app.processEvents()
        try:
            self.assertLess(len(label.text()), len(dns))
            self.assertEqual(label.full_text(), dns)
            self.assertEqual(label.toolTip(), dns)
        finally:
            host.close()

    def test_unknown_progress_shows_an_indeterminate_bar(self):
        panel = ProgressPanel()
        panel.start()
        # Un .sql.gz no tiene tamaño descomprimido conocido: fingir 0 % sería peor.
        panel.update_progress(None, 12.5, 3.4)
        self.assertEqual((panel.bar.minimum(), panel.bar.maximum()), (0, 0))
        self.assertIn("12.5 MB", panel.text.text())

        panel.update_progress(42.0, 50.0, 5.0)
        self.assertEqual(panel.bar.maximum(), 100)
        self.assertEqual(panel.bar.value(), 42)

        panel.finish()
        self.assertTrue(panel.isHidden())

    def test_progress_is_clamped_to_the_bar_range(self):
        panel = ProgressPanel()
        panel.update_progress(140.0, 1.0, 1.0)
        self.assertEqual(panel.bar.value(), 100)
        panel.update_progress(-5.0, 1.0, 1.0)
        self.assertEqual(panel.bar.value(), 0)

    def test_table_headers_follow_the_alignment_of_their_column(self):
        table = data_table(["ARCHIVO", "TAMAÑO"], right_aligned=(1,))
        self.assertTrue(
            table.horizontalHeaderItem(0).textAlignment() & Qt.AlignmentFlag.AlignLeft
        )
        self.assertTrue(
            table.horizontalHeaderItem(1).textAlignment() & Qt.AlignmentFlag.AlignRight
        )
        table.setRowCount(1)
        set_table_row(table, 0, ("dump.sql.gz", "8.4 MB"), right_aligned=(1,))
        self.assertTrue(table.item(0, 1).textAlignment() & Qt.AlignmentFlag.AlignRight)

    def test_both_palettes_produce_a_stylesheet(self):
        for palette in (DARK, LIGHT):
            sheet = stylesheet(palette)
            self.assertIn(palette.accent, sheet)
            self.assertIn("QProgressBar", sheet)

    def test_a_selected_row_does_not_look_like_an_unselected_one(self):
        """La selección se pintaba con `elevated`.

        En el tema claro `elevated` y `surface` son el mismo blanco, así que
        elegir una fila no se veía y la lista parecía no responder.
        """
        for palette in (DARK, LIGHT):
            sheet = stylesheet(palette)
            selected = sheet.split("QTableWidget::item:selected")[1].split("}")[0]
            self.assertIn(palette.accent, selected)
            self.assertNotIn(f"background: {palette.elevated}", selected)


@unittest.skipUnless(HAS_QT, "PySide6 hace falta para las pruebas de widgets")
class RemoteDumpDialogTests(unittest.TestCase):
    """El diálogo desde el que se elige qué dump bajar."""

    @classmethod
    def setUpClass(cls):
        cls.app = _application()
        cls.app.setStyleSheet(stylesheet(DARK))

    def _dialog(self, count: int = 3) -> "RemoteDumpDialog":
        dumps = tuple(
            RemoteDump(name=f"dump_{i}.sql.gz", size=f"{i} MB", date="2026-08-08")
            for i in range(count)
        )
        dialog = RemoteDumpDialog(dumps, "ProjectX PROD")
        self.addCleanup(dialog.deleteLater)
        return dialog

    def test_it_opens_with_the_first_dump_already_chosen(self):
        dialog = self._dialog()
        self.assertEqual(dialog.selected().name, "dump_0.sql.gz")

    def test_choosing_a_row_changes_what_will_be_downloaded(self):
        dialog = self._dialog()
        dialog.table.selectRow(2)
        self.assertEqual(dialog.selected().name, "dump_2.sql.gz")
        self.assertIn("dump_2.sql.gz", dialog.hint.text())

    def test_the_only_download_button_is_the_one_in_the_row(self):
        """Un botón abajo repetía la acción de la fila y era una fuente más de
        verdad sobre qué se iba a bajar."""
        dialog = self._dialog()
        labels = [
            button.text()
            for button in dialog.findChildren(QPushButton)
            if button not in dialog._row_buttons
        ]
        self.assertEqual(labels, ["Cerrar"])

    def test_enter_downloads_the_selected_row(self):
        """Sin el botón `default`, la tecla tiene que hacer el trabajo."""
        dialog = self._dialog()
        dialog.show()
        dialog.table.setFocus()
        dialog.table.selectRow(1)
        self.app.processEvents()
        QTest.keyClick(dialog.table, Qt.Key.Key_Return)
        self.assertEqual(dialog.result(), RemoteDumpDialog.DialogCode.Accepted)
        self.assertEqual(dialog.selected().name, "dump_1.sql.gz")

    def test_every_row_has_its_own_download_button(self):
        dialog = self._dialog()
        self.assertEqual(len(dialog._row_buttons), 3)
        for row in range(dialog.table.rowCount()):
            self.assertIsNotNone(dialog.table.cellWidget(row, 3))

    def test_the_button_of_a_row_downloads_that_row(self):
        """El botón no depende de cuál fila esté seleccionada."""
        dialog = self._dialog()
        dialog.table.selectRow(0)
        dialog._row_buttons[2].click()
        self.assertEqual(dialog.result(), RemoteDumpDialog.DialogCode.Accepted)
        self.assertEqual(dialog.selected().name, "dump_2.sql.gz")

    def test_the_actions_column_is_wide_enough_for_its_button(self):
        """Con `ResizeToContents` la columna quedaba en cero: Qt no mide los
        widgets de celda, solo los items."""
        dialog = self._dialog()
        dialog.show()
        self.app.processEvents()
        button = dialog._row_buttons[0]
        self.assertGreaterEqual(dialog.table.columnWidth(3), button.sizeHint().width())
        self.assertGreaterEqual(button.width(), button.sizeHint().width())
        self.assertGreaterEqual(button.height(), button.sizeHint().height())
        dialog.close()

    def test_an_empty_listing_leaves_nothing_to_download(self):
        dialog = self._dialog(count=0)
        self.assertIsNone(dialog.selected())
        self.assertEqual(dialog._row_buttons, [])
        self.assertIn("No hay dumps", dialog.hint.text())


@unittest.skipUnless(HAS_QT, "PySide6 hace falta para las pruebas de widgets")
class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _application()

    def setUp(self):
        ConfigManager.reset()
        self._temporary = tempfile.TemporaryDirectory()
        directory = Path(self._temporary.name)
        config_path, environments_path = _write_config(directory)
        self.backend = Backend()
        self.backend.load(config_path, environments_path)
        self.window = MainWindow(self.backend, DARK)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        ConfigManager.reset()
        self._temporary.cleanup()

    def test_the_tree_renders_both_levels(self):
        self.assertEqual(set(self.window._groups), {"example_one"})
        self.assertEqual(
            set(self.window._items), {"example_one_prod", "example_one_qa"}
        )

    def test_collapsing_a_parent_hides_its_types(self):
        self.window.toggle_group("example_one")
        self.assertTrue(self.window._items["example_one_prod"].isHidden())
        self.window.toggle_group("example_one")
        self.assertFalse(self.window._items["example_one_prod"].isHidden())

    def test_remote_actions_are_disabled_with_a_visible_reason(self):
        self.window.select_environment("example_one_prod")
        self.assertEqual(self.window.stack.currentIndex(), PAGE_ENVIRONMENT)
        self.assertFalse(self.window.ssh_button.isEnabled())
        self.assertFalse(self.window.dump_button.isEnabled())
        self.assertIn("MFA", self.window.ssh_button.toolTip())
        self.assertFalse(self.window.notice.isHidden())

    def test_local_actions_stay_available_without_mfa(self):
        self.window.select_local("database")
        self.assertEqual(self.window.stack.currentIndex(), PAGE_DATABASE)
        self.assertTrue(self.window.connect_button.isEnabled())

    def test_switching_to_history_loads_the_table(self):
        self.window.select_local("history")
        self.assertEqual(self.window.stack.currentIndex(), PAGE_HISTORY)
        self.assertIn("operaciones", self.window.history_subtitle.text())

    def test_backend_output_reaches_the_log_panel(self):
        self.backend.log("una línea de prueba")
        self.app.processEvents()
        self.assertIn("una línea de prueba", self.window.log_view.toPlainText())

    def test_a_failed_operation_shows_the_banner_and_frees_the_ui(self):
        self.window.busy = True
        self.window._on_failed("No se pudo obtener el DNS.")
        self.assertFalse(self.window.busy)
        self.assertFalse(self.window.banner.isHidden())

    def test_applying_the_other_palette_does_not_raise(self):
        self.window.apply_palette(LIGHT)
        self.window.select_environment("example_one_prod")
        self.app.processEvents()

    def test_prod_and_qa_get_different_pill_tones(self):
        self.window.select_environment("example_one_prod")
        self.assertEqual(self.window.env_pill.property("tone"), "warn")
        self.window.select_environment("example_one_qa")
        self.assertEqual(self.window.env_pill.property("tone"), "info")

    def test_an_environment_without_a_security_group_disables_authorizing(self):
        self.window.select_environment("example_one_qa")
        self.assertFalse(self.window.authorize_button.isEnabled())

    def _make_dump(self, relative: str) -> Path:
        path = self.backend.config.get_dump_directory() / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 1024)
        return path

    def test_the_dump_filter_lists_every_environment(self):
        self.window.select_local("database")
        keys = [
            self.window.dump_filter_combo.itemData(i)
            for i in range(self.window.dump_filter_combo.count())
        ]
        self.assertEqual(
            keys, ["all", "example_one", "example_one_prod", "example_one_qa", "unknown"]
        )

    def test_filtering_narrows_the_table_to_that_environment(self):
        prod = self._make_dump("example_one_prod/dump_prod.sql.gz")
        self.backend.dumps.record_download(
            self.backend.snapshot().find_type("example_one_prod").as_dict(),
            prod, "dump_prod.sql.gz", 0.001,
        )
        qa = self._make_dump("example_one_qa/dump_qa.sql.gz")
        self.backend.dumps.record_download(
            self.backend.snapshot().find_type("example_one_qa").as_dict(),
            qa, "dump_qa.sql.gz", 0.001,
        )
        self.window.refresh(force=True)
        self.window.select_local("database")

        self.assertEqual(self.window.dumps_table.rowCount(), 2)

        combo = self.window.dump_filter_combo
        combo.setCurrentIndex(combo.findData("example_one_prod"))
        self.assertEqual(self.window.dumps_table.rowCount(), 1)
        self.assertEqual(self.window.dumps_table.item(0, 0).text(), "dump_prod.sql.gz")
        # La columna de entorno sale del índice, no del nombre del archivo.
        self.assertEqual(self.window.dumps_table.item(0, 1).text(), "Example One · PROD")

        # El padre se queda con los dos tipos.
        combo.setCurrentIndex(combo.findData("example_one"))
        self.assertEqual(self.window.dumps_table.rowCount(), 2)

    def test_an_empty_filter_says_so_instead_of_showing_nothing(self):
        self.window.select_local("database")
        combo = self.window.dump_filter_combo
        combo.setCurrentIndex(combo.findData("example_one_qa"))
        self.assertEqual(self.window.dumps_table.rowCount(), 0)
        self.assertFalse(self.window.dumps_empty.isHidden())

    def test_a_file_chosen_by_hand_becomes_the_target(self):
        outside = Path(self._temporary.name) / "fuera_de_la_carpeta.sql"
        outside.write_bytes(b"y" * 2048)

        self.window.select_local("database")
        self.window._chosen_dump = outside
        self.window.chosen_label.set_full_text(str(outside))
        self.window.chosen_row.show()
        self.window._set_controls_enabled()

        target = self.window._dump_to_recreate()
        self.assertIsNotNone(target)
        self.assertEqual(target[0], outside)
        self.assertTrue(self.window.recreate_button.isEnabled())

        self.window.clear_chosen_dump()
        self.assertTrue(self.window.chosen_row.isHidden())
        self.assertIsNone(self.window._dump_to_recreate())

    def _download_after_picking(self, answer: bool) -> list:
        """Elegir el primer dump del diálogo y contestar `answer` a la confirmación."""
        env_type = self.window.snapshot.environments[0].types[0]
        dumps = (RemoteDump(name="dump_0.sql.gz", size="120 MB", date="2026-08-08"),)
        started: list = []
        with mock.patch.object(
            RemoteDumpDialog, "exec",
            return_value=RemoteDumpDialog.DialogCode.Accepted,
        ), mock.patch("aws_ui.window.confirm", return_value=answer) as asked, \
                mock.patch.object(
                    self.window, "_run_with_progress",
                    side_effect=lambda *a, **k: started.append(a)):
            self.window._pick_dump(env_type, dumps)
        self.assertTrue(asked.called, "no se pidió confirmación")
        return started

    def test_a_download_is_confirmed_before_starting(self):
        """Bajar un dump puede tardar y son varios GB: primero se pregunta."""
        self.assertEqual(self._download_after_picking(answer=False), [])

    def test_confirming_starts_the_download(self):
        self.assertEqual(len(self._download_after_picking(answer=True)), 1)

    def test_recreate_is_disabled_when_there_is_nothing_to_import(self):
        self.window.select_local("database")
        self.assertEqual(self.window.dumps_table.rowCount(), 0)
        self.assertFalse(self.window.recreate_button.isEnabled())
        self.assertTrue(self.window.browse_button.isEnabled())

    def test_closing_quits_instead_of_hiding(self):
        """La app no puede quedar en segundo plano: cerrar termina el proceso."""
        quits: list[bool] = []
        self.window.quit_requested.connect(lambda: quits.append(True))

        self.assertTrue(self.window.close())
        self.assertEqual(quits, [True])
        self.assertTrue(self.window.isHidden())

    def test_closing_clears_the_temporary_session_token(self):
        os.environ["AWS_SESSION_TOKEN"] = "token-de-prueba"
        try:
            self.window.close()
            self.assertNotIn("AWS_SESSION_TOKEN", os.environ)
        finally:
            os.environ.pop("AWS_SESSION_TOKEN", None)

    def test_there_is_no_way_back_from_a_hidden_window(self):
        # Guardas contra que vuelva a colarse un modo segundo plano.
        for forbidden in ("hide_to_tray", "toggle_window", "hidden_to_tray",
                          "tray_available"):
            self.assertFalse(
                hasattr(self.window, forbidden),
                f"{forbidden} volvió: la app no debe poder esconderse",
            )

    def test_the_window_survives_losing_its_configuration(self):
        self.backend._loaded = False
        self.window.refresh(force=True)
        self.assertEqual(self.window.stack.currentIndex(), 3)


@unittest.skipUnless(HAS_QT, "PySide6 hace falta para las pruebas de widgets")
class SecretFieldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _application()

    def test_an_untouched_field_asks_for_no_change(self):
        field = SecretField("access_key")
        self.assertIsNone(field.value())

    def test_the_input_starts_hidden_and_masked(self):
        field = SecretField("secret_key")
        self.assertTrue(field.editor.isHidden())
        self.assertEqual(field.input.echoMode(), QLineEdit.EchoMode.Password)

    def test_editing_returns_the_new_value(self):
        field = SecretField("access_key")
        field._start_editing()
        field.input.setText("  AKIANUEVA  ")
        self.assertEqual(field.value(), "AKIANUEVA")

    def test_cancelling_goes_back_to_leaving_it_alone(self):
        field = SecretField("access_key")
        field._start_editing()
        field.input.setText("AKIANUEVA")
        field._stop_editing()
        self.assertIsNone(field.value())
        self.assertEqual(field.input.text(), "")

    def test_revealing_is_opt_in_and_reversible(self):
        field = SecretField("access_key")
        field._start_editing()
        field.reveal.setChecked(True)
        self.assertEqual(field.input.echoMode(), QLineEdit.EchoMode.Normal)
        field.reveal.setChecked(False)
        self.assertEqual(field.input.echoMode(), QLineEdit.EchoMode.Password)

    def test_the_status_line_shows_where_the_value_comes_from(self):
        field = SecretField("access_key")
        field.set_status(True, "AKIA••••MPLE  (20 caracteres)", source="entorno")
        self.assertEqual(field.pill.text(), "en el entorno")
        field.set_status(False, "sin definir")
        self.assertEqual(field.pill.text(), "sin definir")


@unittest.skipUnless(HAS_QT, "PySide6 hace falta para las pruebas de widgets")
class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _application()

    def setUp(self):
        ConfigManager.reset()
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        config_path, environments_path = _write_config(self.directory)
        self.config_path = config_path
        self.backend = Backend(on_output=lambda _: None)
        self.backend.load(config_path, environments_path)
        self.dialog = SettingsDialog(self.backend)

    def tearDown(self):
        self.dialog.close()
        self.dialog.deleteLater()
        self.app.processEvents()
        ConfigManager.reset()
        self._temporary.cleanup()

    def test_it_loads_what_is_on_disk(self):
        self.assertEqual(self.dialog.region_input.text(), "us-east-1")
        self.assertEqual(self.dialog.ssh_user_input.text(), "ubuntu")
        self.assertEqual(self.dialog.mysql_user_input.text(), "root")

    def test_the_tree_shows_parents_and_their_types(self):
        self.assertEqual(self.dialog.tree.topLevelItemCount(), 1)
        self.assertEqual(self.dialog.tree.topLevelItem(0).childCount(), 2)

    def test_saving_writes_a_changed_field_to_disk(self):
        self.dialog.region_input.setText("sa-east-1")
        self.dialog.save()
        written = json.loads(Path(self.config_path).read_text(encoding="utf-8"))
        self.assertEqual(written["credentials"]["region"], "sa-east-1")

    def test_saving_does_not_wipe_a_secret_that_was_not_touched(self):
        self.backend.save_credentials({"access_key": "AKIAIOSFODNN7EXAMPLE"})
        self.dialog.region_input.setText("eu-west-1")
        self.dialog.save()
        credentials = self.backend.config_snapshot()["credentials"]
        self.assertEqual(credentials["access_key"], "AKIAIOSFODNN7EXAMPLE")

    def test_adding_a_type_lands_under_its_parent(self):
        self.dialog._select_path((0, None))
        self.dialog._add_type()
        self.assertEqual(self.dialog.tree.topLevelItem(0).childCount(), 3)

    def test_adding_a_parent_appends_it(self):
        self.dialog._add_parent()
        self.assertEqual(self.dialog.tree.topLevelItemCount(), 2)

    def test_editing_a_type_reaches_the_model(self):
        self.dialog._select_path((0, 0))
        self.dialog.type_inputs["instance_name"].setText("Bastion-Nuevo")
        self.assertEqual(
            self.dialog.environments[0]["types"][0]["instance_name"], "Bastion-Nuevo"
        )

    def test_choosing_a_private_key_stores_it_only_for_that_type(self):
        self.dialog._select_path((0, 0))
        self.dialog.key_mode.setCurrentIndex(1)  # llave propia
        self.dialog.type_key_field.set_text("/tmp/solo-prod.pem")
        self.dialog._commit_current()
        types = self.dialog.environments[0]["types"]
        self.assertEqual(types[0]["key_path"], "/tmp/solo-prod.pem")
        # El otro tipo no se toca: sin key_path, o vacío, ambos significan
        # "usar la general", que es lo que se comprueba.
        self.assertFalse(self.backend.config.uses_own_key(types[1]))

    def test_going_back_to_the_general_key_clears_the_private_one(self):
        self.dialog._select_path((0, 0))
        self.dialog.key_mode.setCurrentIndex(1)
        self.dialog.type_key_field.set_text("/tmp/solo-prod.pem")
        self.dialog._commit_current()
        self.dialog.key_mode.setCurrentIndex(0)  # volver a la general
        self.assertEqual(self.dialog.environments[0]["types"][0]["key_path"], "")

    def test_saving_a_broken_tree_is_refused_with_a_reason(self):
        self.dialog._select_path((0, 0))
        self.dialog.type_inputs["id"].setText("")
        self.dialog.save()
        self.assertIn("sin id", self.dialog.feedback.text())
        # Y la pestaña que tiene el problema queda a la vista.
        self.assertEqual(self.dialog.tabs.currentIndex(), 2)

    def test_the_environment_variables_table_is_populated(self):
        from awsm_cli.utils.shell_env import AWS_VARIABLES

        self.assertEqual(self.dialog.environment_table.rowCount(), len(AWS_VARIABLES))
        names = [self.dialog.environment_table.item(row, 0).text()
                 for row in range(self.dialog.environment_table.rowCount())]
        self.assertIn("AWS_ACCESS_KEY_ID", names)
        self.assertIn("AWS_SESSION_TOKEN", names)

    def test_exporting_and_importing_round_trips_through_the_dialog(self):
        destination = self.directory / "paquete.zip"
        self.backend.export_configuration(destination, include_secrets=False,
                                          include_keys=False)
        contents = self.backend.inspect_configuration(destination)
        self.assertEqual(contents.environment_count, 1)
        self.assertEqual(contents.type_count, 2)


def _left_click(widget):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    position = QPointF(4, 4)
    return QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


if __name__ == "__main__":
    unittest.main()

"""Pruebas de la configuración editable: secretos, llaves y paquetes. Sin Qt."""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from awsm_cli.config import ConfigManager  # noqa: E402
from awsm_cli.config.bundle import (  # noqa: E402
    BundleError,
    export_bundle,
    import_bundle,
    inspect_bundle,
)
from awsm_cli.utils.secrets import (  # noqa: E402
    describe_secret,
    describe_ssh_key,
    is_set,
    mask_secret,
    scrub_secrets,
)
from aws_ui.core import (  # noqa: E402
    Backend,
    CoreError,
    parse_databases,
    validate_environments,
)
from tests.test_aws_ui import _write_config  # noqa: E402


ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"
SECRET_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


class MaskingTests(unittest.TestCase):
    def test_the_ends_survive_so_the_key_is_recognisable(self):
        masked = mask_secret(ACCESS_KEY)
        self.assertTrue(masked.startswith("AKIA"))
        self.assertTrue(masked.endswith("MPLE"))
        self.assertNotIn("IOSFODNN7EXA", masked)
        self.assertEqual(len(masked), len(ACCESS_KEY))

    def test_a_short_value_is_covered_whole(self):
        # Mostrar 4 de 6 caracteres no seria enmascarar nada.
        masked = mask_secret("abc123")
        self.assertNotIn("abc", masked)
        self.assertNotIn("123", masked)

    def test_an_empty_value_masks_to_nothing(self):
        self.assertEqual(mask_secret(""), "")
        self.assertEqual(mask_secret("   "), "")

    def test_is_set_ignores_whitespace(self):
        self.assertFalse(is_set("   "))
        self.assertTrue(is_set(" x "))


class SecretStatusTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("PRUEBA_AWS_KEY", None)

    def test_a_missing_secret_says_so_without_inventing_a_mask(self):
        status = describe_secret("access_key", "", "PRUEBA_AWS_KEY")
        self.assertFalse(status.present)
        self.assertEqual(status.masked, "")
        self.assertEqual(status.text, "sin definir")

    def test_the_environment_wins_over_the_file(self):
        """Es el orden que usa la autenticación: mostrar el del archivo mentiría."""
        os.environ["PRUEBA_AWS_KEY"] = ACCESS_KEY
        status = describe_secret("access_key", "OTRA-CLAVE-DEL-ARCHIVO", "PRUEBA_AWS_KEY")
        self.assertEqual(status.source, "entorno")
        self.assertTrue(status.masked.endswith("MPLE"))

    def test_the_file_is_used_when_the_environment_is_empty(self):
        status = describe_secret("access_key", ACCESS_KEY, "PRUEBA_AWS_KEY")
        self.assertEqual(status.source, "config")
        self.assertEqual(status.length, len(ACCESS_KEY))

    def test_the_status_never_contains_the_whole_secret(self):
        status = describe_secret("secret_key", SECRET_KEY, "")
        self.assertNotIn(SECRET_KEY, status.text)
        self.assertNotIn(SECRET_KEY[4:-4], status.text)


class ScrubTests(unittest.TestCase):
    def test_an_access_key_inside_an_aws_error_gets_covered(self):
        message = f"An error occurred: The security token for {ACCESS_KEY} is invalid"
        cleaned = scrub_secrets(message)
        self.assertNotIn(ACCESS_KEY, cleaned)
        self.assertIn("AKIA", cleaned)

    def test_a_message_without_keys_is_left_alone(self):
        message = "Could not connect to the endpoint URL"
        self.assertEqual(scrub_secrets(message), message)


class KeyStatusTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)

    def tearDown(self):
        self._temporary.cleanup()

    def test_a_missing_key_is_reported_not_guessed(self):
        status = describe_ssh_key(str(self.directory / "no-existe.pem"))
        self.assertFalse(status.exists)
        self.assertFalse(status.ok)
        self.assertEqual(status.text, "el archivo no existe")

    def test_an_empty_path_is_not_an_error(self):
        self.assertEqual(describe_ssh_key("").text, "sin definir")

    def test_open_permissions_are_flagged(self):
        key = self.directory / "abierta.pem"
        key.write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
        os.chmod(key, 0o644)
        status = describe_ssh_key(str(key))
        self.assertTrue(status.exists)
        self.assertFalse(status.permissions_ok)
        self.assertIn("600", status.text)

    def test_correct_permissions_pass(self):
        key = self.directory / "cerrada.pem"
        key.write_text("-----BEGIN PRIVATE KEY-----\n", encoding="utf-8")
        os.chmod(key, 0o600)
        status = describe_ssh_key(str(key))
        self.assertTrue(status.permissions_ok)

    def test_the_status_never_contains_the_key_material(self):
        key = self.directory / "llave.pem"
        key.write_text("-----BEGIN PRIVATE KEY-----\nMATERIAL-SECRETO\n", encoding="utf-8")
        os.chmod(key, 0o600)
        self.assertNotIn("MATERIAL-SECRETO", describe_ssh_key(str(key)).text)


class ValidationTests(unittest.TestCase):
    def test_a_healthy_tree_passes(self):
        self.assertEqual(validate_environments([
            {"id": "ops", "name": "OPS", "types": [
                {"id": "ops_prod", "name": "PROD", "instance_id": "i-1"},
            ]},
        ]), "")

    def test_a_duplicate_type_id_is_refused(self):
        problem = validate_environments([
            {"id": "a", "name": "A", "types": [
                {"id": "x", "name": "X", "instance_id": "i-1"},
                {"id": "x", "name": "Y", "instance_id": "i-2"},
            ]},
        ])
        self.assertIn("repetido", problem)

    def test_a_duplicate_parent_id_is_refused(self):
        problem = validate_environments([
            {"id": "a", "name": "A", "types": []},
            {"id": "a", "name": "B", "types": []},
        ])
        self.assertIn("repetido", problem)

    def test_missing_pieces_are_named(self):
        self.assertIn("sin id", validate_environments([{"id": "", "name": "A"}]))
        self.assertIn("nombre", validate_environments([{"id": "a", "name": ""}]))
        self.assertIn("instance_id", validate_environments([
            {"id": "a", "name": "A", "types": [{"id": "x", "name": "X"}]},
        ]))


class DatabaseParsingTests(unittest.TestCase):
    def test_pairs_and_bare_names_both_work(self):
        self.assertEqual(
            parse_databases("ops=ensolvers_ops, hirelens"),
            {"ops": "ensolvers_ops", "hirelens": "hirelens"},
        )

    def test_blanks_and_stray_commas_are_ignored(self):
        self.assertEqual(parse_databases("  ,, a=b ,"), {"a": "b"})
        self.assertEqual(parse_databases(""), {})

    def test_newlines_work_as_separators_too(self):
        self.assertEqual(parse_databases("a=1\nb=2"), {"a": "1", "b": "2"})


class ConfigWriteTests(unittest.TestCase):
    def setUp(self):
        ConfigManager.reset()
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.config_path, self.environments_path = _write_config(self.directory)
        self.config = ConfigManager(on_output=lambda _: None)
        self.config.load_config(self.config_path)
        self.config.load_environments(self.environments_path)

    def tearDown(self):
        ConfigManager.reset()
        self._temporary.cleanup()

    def test_saving_writes_back_to_the_file_it_loaded(self):
        data = self.config.config_data
        data["credentials"]["region"] = "sa-east-1"
        self.assertTrue(self.config.save_config(data))
        written = json.loads(Path(self.config_path).read_text(encoding="utf-8"))
        self.assertEqual(written["credentials"]["region"], "sa-east-1")

    def test_the_config_file_is_not_world_readable(self):
        """Puede tener claves de AWS: no debería quedar legible por el sistema."""
        self.config.save_config(self.config.config_data)
        mode = stat.S_IMODE(Path(self.config_path).stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_no_temporary_file_survives_the_write(self):
        self.config.save_config(self.config.config_data)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_saving_environments_keeps_the_wrapper_key(self):
        self.config.save_environments([{"id": "x", "name": "X", "types": []}])
        written = json.loads(Path(self.environments_path).read_text(encoding="utf-8"))
        self.assertIn("environments", written)
        self.assertEqual(len(written["environments"]), 1)

    def test_saving_paths_releases_the_cached_dump_directory(self):
        first = self.config.get_dump_directory()
        data = self.config.config_data
        data["paths"]["dump_directory"] = str(self.directory / "otra-carpeta")
        self.config.save_config(data)
        self.assertNotEqual(self.config.get_dump_directory(), first)

    def test_an_environment_without_its_own_key_falls_back_to_the_general_one(self):
        general = self.config.get_key_path()
        self.assertEqual(self.config.get_key_path_for({"id": "x"}), general)
        self.assertEqual(self.config.get_key_path_for({"id": "x", "key_path": ""}), general)
        self.assertFalse(self.config.uses_own_key({"id": "x", "key_path": "   "}))

    def test_an_environment_with_its_own_key_wins(self):
        environment = {"id": "x", "key_path": "/tmp/propia.pem"}
        self.assertEqual(self.config.get_key_path_for(environment), "/tmp/propia.pem")
        self.assertTrue(self.config.uses_own_key(environment))


class BundleTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.keys = self.directory / "llaves-destino"

        self.general_key = self.directory / "general.pem"
        self.general_key.write_text("LLAVE-GENERAL", encoding="utf-8")
        self.own_key = self.directory / "solo-prod.pem"
        self.own_key.write_text("LLAVE-PROD", encoding="utf-8")

        self.config = {
            "credentials": {
                "access_key": ACCESS_KEY,
                "secret_key": SECRET_KEY,
                "region": "us-east-1",
                "key_path": str(self.general_key),
            },
            "ssh": {"user": "ubuntu", "port": 22},
        }
        self.environments = [{
            "id": "ops", "name": "OPS", "types": [
                {"id": "ops_prod", "name": "PROD", "instance_id": "i-1",
                 "key_path": str(self.own_key)},
                {"id": "ops_qa", "name": "QA", "instance_id": "i-2", "key_path": ""},
            ],
        }]

    def tearDown(self):
        self._temporary.cleanup()

    def _export(self, **kwargs) -> Path:
        destination = self.directory / "paquete.zip"
        export_bundle(destination, self.config, self.environments, **kwargs)
        return destination

    def test_secrets_stay_out_unless_they_are_asked_for(self):
        path = self._export(include_secrets=False)
        with zipfile.ZipFile(path) as archive:
            config = json.loads(archive.read("config.json").decode("utf-8"))
        self.assertEqual(config["credentials"]["access_key"], "")
        self.assertEqual(config["credentials"]["secret_key"], "")
        # Lo que no es secreto sí viaja.
        self.assertEqual(config["credentials"]["region"], "us-east-1")

    def test_secrets_travel_when_asked_for(self):
        path = self._export(include_secrets=True)
        with zipfile.ZipFile(path) as archive:
            config = json.loads(archive.read("config.json").decode("utf-8"))
        self.assertEqual(config["credentials"]["access_key"], ACCESS_KEY)

    def test_keys_are_stored_with_portable_paths(self):
        path = self._export()
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            config = json.loads(archive.read("config.json").decode("utf-8"))
            environments = json.loads(
                archive.read("config-environment.json").decode("utf-8")
            )["environments"]
        self.assertTrue(any(n.startswith("keys/") for n in names))
        # Una ruta /home/ezer/... no existiría en la otra máquina.
        self.assertFalse(config["credentials"]["key_path"].startswith("/"))
        self.assertTrue(config["credentials"]["key_path"].startswith("keys/"))
        self.assertTrue(environments[0]["types"][0]["key_path"].startswith("keys/"))

    def test_without_keys_the_stale_paths_are_cleared(self):
        path = self._export(include_keys=False)
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            config = json.loads(archive.read("config.json").decode("utf-8"))
        self.assertFalse(any(n.startswith("keys/") for n in names))
        self.assertEqual(config["credentials"]["key_path"], "")

    def test_the_bundle_is_not_world_readable(self):
        path = self._export(include_secrets=True)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_a_missing_key_is_skipped_with_a_warning_not_a_crash(self):
        self.own_key.unlink()
        warnings: list[str] = []
        destination = self.directory / "parcial.zip"
        export_bundle(destination, self.config, self.environments,
                      on_output=warnings.append)
        self.assertTrue(any("no existe" in line for line in warnings))
        self.assertTrue(destination.exists())

    def test_a_round_trip_restores_working_key_paths(self):
        path = self._export(include_secrets=True)
        config, environments, contents = import_bundle(path, self.keys)

        restored = Path(config["credentials"]["key_path"])
        self.assertTrue(restored.is_file())
        self.assertEqual(restored.read_text(encoding="utf-8"), "LLAVE-GENERAL")
        own = Path(environments[0]["types"][0]["key_path"])
        self.assertEqual(own.read_text(encoding="utf-8"), "LLAVE-PROD")
        # El tipo que usaba la general sigue sin llave propia.
        self.assertEqual(environments[0]["types"][1]["key_path"], "")
        self.assertTrue(contents.includes_secrets)

    def test_imported_keys_get_private_permissions(self):
        """Con permisos abiertos, ssh rechaza la llave y el error es críptico."""
        path = self._export()
        config, _environments, _contents = import_bundle(path, self.keys)
        mode = stat.S_IMODE(Path(config["credentials"]["key_path"]).stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_inspect_describes_the_bundle_without_writing(self):
        path = self._export(include_secrets=False)
        contents = inspect_bundle(path)
        self.assertEqual(contents.environment_count, 1)
        self.assertEqual(contents.type_count, 2)
        self.assertFalse(contents.includes_secrets)
        self.assertTrue(contents.includes_keys)
        self.assertIn("2 tipos", contents.summary)
        self.assertFalse(self.keys.exists())

    def test_a_file_that_is_not_a_bundle_is_refused_clearly(self):
        stray = self.directory / "cualquier-cosa.zip"
        with zipfile.ZipFile(stray, "w") as archive:
            archive.writestr("hola.txt", "nada que ver")
        with self.assertRaises(BundleError) as raised:
            inspect_bundle(stray)
        self.assertIn("no parece un paquete", str(raised.exception))

    def test_a_file_that_is_not_a_zip_is_refused(self):
        stray = self.directory / "texto.zip"
        stray.write_text("esto no es un zip", encoding="utf-8")
        with self.assertRaises(BundleError):
            inspect_bundle(stray)

    def test_a_key_entry_cannot_escape_the_destination_folder(self):
        """Un zip hostil no debe poder escribir fuera de la carpeta de llaves."""
        path = self._export()
        hostile = self.directory / "hostil.zip"
        with zipfile.ZipFile(path) as origin, zipfile.ZipFile(hostile, "w") as target:
            for item in origin.namelist():
                data = origin.read(item)
                if item.startswith("keys/"):
                    target.writestr("keys/../../escapada.pem", data)
                else:
                    target.writestr(item, data)

        import_bundle(hostile, self.keys)
        self.assertFalse((self.directory.parent / "escapada.pem").exists())
        self.assertTrue((self.keys / "escapada.pem").exists())

    def test_one_key_shared_by_several_environments_is_stored_once(self):
        self.environments[0]["types"][1]["key_path"] = str(self.own_key)
        path = self._export()
        with zipfile.ZipFile(path) as archive:
            keys = [n for n in archive.namelist() if n.startswith("keys/")]
        self.assertEqual(len(keys), 2)  # la general y la compartida


class BackendConfigTests(unittest.TestCase):
    def setUp(self):
        ConfigManager.reset()
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.config_path, self.environments_path = _write_config(self.directory)
        self.backend = Backend(on_output=lambda _: None)
        self.backend.load(self.config_path, self.environments_path)

    def tearDown(self):
        ConfigManager.reset()
        self._temporary.cleanup()

    def test_an_untouched_secret_is_left_exactly_as_it_was(self):
        """El diálogo nunca ve el secreto, así que no puede reenviarlo."""
        self.backend.save_credentials({"access_key": ACCESS_KEY, "secret_key": SECRET_KEY})
        self.backend.save_credentials({"region": "sa-east-1"})  # sin tocar secretos
        credentials = self.backend.config_snapshot()["credentials"]
        self.assertEqual(credentials["access_key"], ACCESS_KEY)
        self.assertEqual(credentials["region"], "sa-east-1")

    def test_an_explicit_empty_string_does_clear_a_secret(self):
        self.backend.save_credentials({"access_key": ACCESS_KEY})
        self.backend.save_credentials({"access_key": ""})
        self.assertEqual(self.backend.config_snapshot()["credentials"]["access_key"], "")

    def test_saving_broken_environments_is_refused_before_writing(self):
        original = json.loads(Path(self.environments_path).read_text(encoding="utf-8"))
        with self.assertRaises(CoreError):
            self.backend.save_environments([
                {"id": "a", "name": "A", "types": [{"id": "", "name": "X"}]},
            ])
        self.assertEqual(
            json.loads(Path(self.environments_path).read_text(encoding="utf-8")), original
        )

    def test_saved_environments_come_back_in_the_snapshot(self):
        self.backend.save_environments([
            {"id": "nuevo", "name": "Nuevo", "types": [
                {"id": "nuevo_prod", "name": "PROD", "instance_id": "i-9",
                 "security_group_id": "", "dns": "", "instance_name": "",
                 "key_path": "/tmp/propia.pem"},
            ]},
        ])
        snapshot = self.backend.snapshot()
        env_type = snapshot.find_type("nuevo_prod")
        self.assertIsNotNone(env_type)
        self.assertEqual(env_type.key_path, "/tmp/propia.pem")
        self.assertEqual(self.backend.key_for(env_type), "/tmp/propia.pem")

    def test_a_type_without_its_own_key_uses_the_general_one(self):
        env_type = self.backend.snapshot().find_type("example_one_prod")
        self.assertEqual(env_type.key_path, "")
        self.assertEqual(self.backend.key_for(env_type), self.backend.config.get_key_path())

    def test_importing_a_bundle_without_secrets_keeps_the_current_ones(self):
        self.backend.save_credentials({"access_key": ACCESS_KEY, "secret_key": SECRET_KEY})
        destination = self.directory / "sin-secretos.zip"
        self.backend.export_configuration(destination, include_secrets=False,
                                          include_keys=False)

        self.backend.import_configuration(destination)
        credentials = self.backend.config_snapshot()["credentials"]
        self.assertEqual(credentials["access_key"], ACCESS_KEY)
        self.assertEqual(credentials["secret_key"], SECRET_KEY)

    def test_a_full_round_trip_through_the_backend_keeps_the_environments(self):
        destination = self.directory / "todo.zip"
        self.backend.export_configuration(destination, include_secrets=True,
                                          include_keys=False)
        before = [env.id for env in self.backend.snapshot().environments]
        self.backend.import_configuration(destination)
        self.assertEqual([env.id for env in self.backend.snapshot().environments], before)

    def test_importing_something_that_is_not_a_bundle_raises_core_error(self):
        stray = self.directory / "no-es.zip"
        stray.write_text("cualquier cosa", encoding="utf-8")
        with self.assertRaises(CoreError):
            self.backend.inspect_configuration(stray)

    def test_environment_variables_are_reported_masked(self):
        os.environ["AWS_ACCESS_KEY_ID"] = ACCESS_KEY
        try:
            rows = dict((name, shown) for name, _present, shown, _origin in
                        self.backend.environment_variables())
            self.assertNotEqual(rows["AWS_ACCESS_KEY_ID"], ACCESS_KEY)
            self.assertTrue(rows["AWS_ACCESS_KEY_ID"].startswith("AKIA"))
        finally:
            os.environ.pop("AWS_ACCESS_KEY_ID", None)


if __name__ == "__main__":
    unittest.main()

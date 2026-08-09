"""Tests for the UI backend. Ninguna necesita PySide6: `core.py` no importa Qt."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aws_ui import core  # noqa: E402
from aws_ui.core import (  # noqa: E402
    Backend,
    CoreError,
    Environment,
    EnvironmentType,
    HistoryEntry,
    LocalDump,
    SecurityGroupPlan,
    Session,
    Snapshot,
    format_duration,
    format_size,
    terminal_command,
)
from awsm_cli.auth.mfa_auth import AWSCredentials  # noqa: E402
from awsm_cli.config import ConfigManager  # noqa: E402


CONFIG = {
    "credentials": {
        "region": "us-east-1",
        "rule_description": "Tester",
        "key_path": "/tmp/no-such-key.pem",
    },
    "mysql": {
        "user": "root",
        "host": "127.0.0.1",
        "protocol": "tcp",
        "databases": {"beta": "beta_db", "alpha": "alpha_db"},
    },
    "ssh": {"user": "ubuntu", "port": 22},
    "mfa": {"required": True},
    "paths": {"dump_directory": ""},
}

ENVIRONMENTS = {
    "environments": [
        {
            "id": "example_one",
            "name": "Example One",
            "types": [
                {
                    "id": "example_one_prod",
                    "name": "PROD",
                    "env_type": "prod",
                    "instance_id": "i-aaa",
                    "security_group_id": "sg-aaa",
                    "dns": "prod.example.com",
                    "instance_name": "Bastion-PROD",
                },
                {
                    "id": "example_one_qa",
                    "name": "QA",
                    "env_type": "qa",
                    "instance_id": "i-bbb",
                    "security_group_id": "",
                    "dns": "",
                    "instance_name": "Bastion-QA",
                },
            ],
        }
    ]
}


def _write_config(directory: Path) -> tuple[str, str]:
    config = directory / "config.json"
    environments = directory / "config-environment.json"
    payload = json.loads(json.dumps(CONFIG))
    payload["paths"]["dump_directory"] = str(directory / "dumps")
    config.write_text(json.dumps(payload), encoding="utf-8")
    environments.write_text(json.dumps(ENVIRONMENTS), encoding="utf-8")
    return str(config), str(environments)


class FormattingTests(unittest.TestCase):
    def test_duration_uses_the_largest_useful_unit(self):
        self.assertEqual(format_duration(43200), "12h 00m")
        self.assertEqual(format_duration(95), "1m 35s")
        self.assertEqual(format_duration(9), "9s")

    def test_duration_never_goes_negative(self):
        self.assertEqual(format_duration(-500), "0s")

    def test_size_switches_to_gigabytes(self):
        self.assertEqual(format_size(8.4), "8.4 MB")
        self.assertEqual(format_size(1536), "1.50 GB")


class SessionTests(unittest.TestCase):
    def test_no_session_is_not_usable(self):
        session = Session(state="none")
        self.assertFalse(session.usable)
        self.assertEqual(session.text, "sin sesión")

    def test_inherited_session_is_usable_but_has_no_deadline(self):
        session = Session(state="inherited")
        self.assertTrue(session.usable)
        self.assertIsNone(session.seconds_left)

    def test_active_session_reports_the_remaining_time(self):
        session = Session(state="active", seconds_left=3600)
        self.assertTrue(session.usable)
        self.assertIn("1h", session.text)

    def test_expired_session_is_not_usable(self):
        session = Session(state="active", seconds_left=-1)
        self.assertFalse(session.usable)
        self.assertEqual(session.text, "sesión expirada")

    def test_mfa_not_required_is_usable(self):
        self.assertTrue(Session(state="not_required").usable)


class CredentialsTests(unittest.TestCase):
    """El CLI descartaba el `Expiration` que devuelve STS; ahora se guarda."""

    def test_expiration_is_parsed_from_the_sts_response(self):
        moment = datetime.now(timezone.utc) + timedelta(hours=6)
        credentials = AWSCredentials("ak", "sk", "token", moment.isoformat())
        self.assertIsNotNone(credentials.seconds_left())
        self.assertGreater(credentials.seconds_left(), 5 * 3600)
        self.assertFalse(credentials.is_expired())

    def test_zulu_suffix_is_accepted(self):
        moment = datetime.now(timezone.utc) - timedelta(minutes=1)
        stamp = moment.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.assertTrue(AWSCredentials("ak", "sk", "t", stamp).is_expired())

    def test_missing_expiration_is_unknown_not_expired(self):
        credentials = AWSCredentials("ak", "sk", "token")
        self.assertIsNone(credentials.seconds_left())
        self.assertFalse(credentials.is_expired())

    def test_unparseable_expiration_does_not_raise(self):
        self.assertIsNone(AWSCredentials("ak", "sk", "t", "no es fecha").expires_at())


class SecurityGroupPlanTests(unittest.TestCase):
    def test_matching_rule_needs_no_change(self):
        plan = SecurityGroupPlan("sg-1", "1.2.3.4", "Tester", existing_rule_ip="1.2.3.4/32")
        self.assertTrue(plan.up_to_date)
        self.assertIn("ya autorizada", plan.summary)

    def test_stale_rule_is_reported_as_a_revoke_and_an_authorize(self):
        plan = SecurityGroupPlan("sg-1", "1.2.3.4", "Tester", existing_rule_ip="9.9.9.9/32")
        self.assertFalse(plan.up_to_date)
        self.assertIn("revoca 9.9.9.9/32", plan.summary)
        self.assertIn("autoriza 1.2.3.4/32", plan.summary)

    def test_first_time_only_authorizes(self):
        plan = SecurityGroupPlan("sg-1", "1.2.3.4", "Tester")
        self.assertFalse(plan.up_to_date)
        self.assertEqual(plan.summary, "autoriza 1.2.3.4/32")

    def test_ip_authorized_by_another_rule_counts(self):
        plan = SecurityGroupPlan("sg-1", "1.2.3.4", "Tester", already_authorized=True)
        self.assertTrue(plan.up_to_date)


class EnvironmentTests(unittest.TestCase):
    def _env_type(self) -> EnvironmentType:
        return EnvironmentType(
            id="one_prod", name="PROD", env_type="prod", instance_id="i-aaa",
            security_group_id="sg-aaa", dns="", instance_name="Bastion",
            parent_id="one", parent_name="Example One",
        )

    def test_label_joins_both_levels(self):
        self.assertEqual(self._env_type().label, "Example One · PROD")

    def test_as_dict_matches_what_the_cli_expects(self):
        raw = self._env_type().as_dict()
        self.assertEqual(raw["security_group_id"], "sg-aaa")
        self.assertEqual(raw["instance_id"], "i-aaa")
        # `awsm_cli` usa 'name' para los mensajes, y ahí conviene el nombre completo.
        self.assertEqual(raw["name"], "Example One · PROD")

    def test_snapshot_finds_a_type_across_parents(self):
        snapshot = Snapshot(
            environments=(Environment("one", "Example One", (self._env_type(),)),)
        )
        self.assertEqual(snapshot.type_count, 1)
        self.assertIsNotNone(snapshot.find_type("one_prod"))
        self.assertIsNone(snapshot.find_type("no_existe"))


class TerminalTests(unittest.TestCase):
    def test_command_keeps_the_window_open_after_the_session(self):
        command = terminal_command(["ssh", "user@host"], "ssh · prod")
        self.assertIn("bash", command)
        script = command[-1]
        self.assertIn("ssh user@host", script)
        # Sin el `read` final, un error de conexión se pierde al cerrarse la ventana.
        self.assertIn("read _", script)

    def test_arguments_with_spaces_are_quoted(self):
        script = terminal_command(["ssh", "-i", "/ruta con espacio/k.pem", "u@h"])[-1]
        self.assertIn("'/ruta con espacio/k.pem'", script)

    def test_missing_emulator_is_reported_not_silent(self):
        original = core.TERMINALS
        core.TERMINALS = (("no-existe-este-terminal", "--"),)
        try:
            with self.assertRaises(CoreError) as raised:
                terminal_command(["ssh", "host"])
            self.assertIn("emulador de terminal", str(raised.exception))
        finally:
            core.TERMINALS = original


class HistoryTests(unittest.TestCase):
    def test_entries_come_from_the_json_lines_without_parsing_text(self):
        entry = core._entry_to_history({
            "_log_type": "recreate",
            "timestamp": "2026-08-05T15:01:02.123456",
            "nombre_dump": "ops_dump.sql.gz",
            "base_datos": "ops",
            "duracion_legible": "4m 53s",
            "tamaño_mb": 8.43,
        })
        self.assertEqual(entry.kind, "recreate")
        self.assertEqual(entry.when, "2026-08-05 15:01")
        self.assertEqual(entry.database, "ops")

    def test_a_broken_timestamp_falls_back_to_the_raw_value(self):
        self.assertEqual(HistoryEntry("dump", "roto", "", "", "", "", None).when, "roto")


class LocalDumpTests(unittest.TestCase):
    def test_name_and_date_come_from_the_path_and_mtime(self):
        dump = LocalDump(Path("/tmp/ops_dump.sql.gz"), 8.4, 1754400000.0)
        self.assertEqual(dump.name, "ops_dump.sql.gz")
        self.assertRegex(dump.modified_text, r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


class BackendTests(unittest.TestCase):
    def setUp(self):
        # ConfigManager es un singleton: sin resetear, una prueba se lleva puesta
        # la configuración de la siguiente.
        ConfigManager.reset()
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.config_path, self.environments_path = _write_config(self.directory)
        self.lines: list[str] = []
        self.backend = Backend(on_output=self.lines.append)

    def tearDown(self):
        ConfigManager.reset()
        self._temporary.cleanup()

    def test_load_builds_the_two_level_tree(self):
        self.assertTrue(self.backend.load(self.config_path, self.environments_path))
        snapshot = self.backend.snapshot()
        self.assertTrue(snapshot.loaded)
        self.assertEqual([env.id for env in snapshot.environments], ["example_one"])
        self.assertEqual(
            [t.id for t in snapshot.environments[0].types],
            ["example_one_prod", "example_one_qa"],
        )
        self.assertEqual(snapshot.type_count, 2)

    def test_output_goes_to_the_sink_instead_of_stdout(self):
        self.backend.load(self.config_path, self.environments_path)
        self.assertTrue(any("Configuración cargada" in line for line in self.lines))

    def test_databases_are_sorted_for_a_stable_picker(self):
        self.backend.load(self.config_path, self.environments_path)
        self.assertEqual(
            self.backend.snapshot().databases,
            (("alpha", "alpha_db"), ("beta", "beta_db")),
        )

    def test_a_missing_config_is_an_error_in_the_snapshot_not_an_exception(self):
        missing = str(self.directory / "no-existe.json")
        self.assertFalse(self.backend.load(missing, self.environments_path))
        snapshot = self.backend.snapshot()
        self.assertFalse(snapshot.loaded)
        self.assertIn("config.json", snapshot.error)

    def test_local_dumps_are_listed_newest_first(self):
        self.backend.load(self.config_path, self.environments_path)
        dump_directory = self.backend.config.get_dump_directory()
        old = dump_directory / "viejo.sql"
        new = dump_directory / "nuevo.sql.gz"
        old.write_bytes(b"x" * 1024)
        new.write_bytes(b"y" * 2048)
        import os
        os.utime(old, (1_600_000_000, 1_600_000_000))
        os.utime(new, (1_700_000_000, 1_700_000_000))
        names = [dump.name for dump in self.backend.local_dumps()]
        self.assertEqual(names, ["nuevo.sql.gz", "viejo.sql"])

    def test_the_dump_keeps_its_remote_name_inside_an_environment_folder(self):
        self.backend.load(self.config_path, self.environments_path)
        env_type = self.backend.snapshot().find_type("example_one_prod")
        path = self.backend.local_path_for(env_type, "dump_prod_2026-08-05.sql.gz")
        # El nombre no se toca; la carpeta es la que separa los entornos.
        self.assertEqual(path.name, "dump_prod_2026-08-05.sql.gz")
        self.assertEqual(path.parent.name, "example_one_prod")

    def test_two_environments_can_hold_the_same_dump_name(self):
        self.backend.load(self.config_path, self.environments_path)
        snapshot = self.backend.snapshot()
        remote = "dump_prod_2026-08-05.sql.gz"
        prod = self.backend.local_path_for(snapshot.find_type("example_one_prod"), remote)
        qa = self.backend.local_path_for(snapshot.find_type("example_one_qa"), remote)
        self.assertNotEqual(prod, qa)

    def test_dumps_are_attributed_from_the_index_not_from_the_name(self):
        self.backend.load(self.config_path, self.environments_path)
        env_type = self.backend.snapshot().find_type("example_one_prod")
        path = self.backend.local_path_for(env_type, "dump_prod_2026-08-05.sql.gz")
        path.write_bytes(b"x" * 2048)
        self.backend.dumps.record_download(
            env_type.as_dict(), path, "dump_prod_2026-08-05.sql.gz", 0.002
        )

        dump = next(d for d in self.backend.local_dumps() if d.path == path)
        self.assertEqual(dump.environment_id, "example_one_prod")
        self.assertEqual(dump.environment_label, "Example One · PROD")

    def test_old_prefixed_dumps_are_still_attributed(self):
        """Los dumps anteriores al índice llevan el entorno en el prefijo."""
        self.backend.load(self.config_path, self.environments_path)
        legacy = self.backend.config.get_dump_directory() / "example_one_qa_dump_2026-01-01.sql"
        legacy.write_bytes(b"y" * 512)

        dump = next(d for d in self.backend.local_dumps() if d.path == legacy)
        self.assertEqual(dump.environment_id, "example_one_qa")

    def test_a_dump_from_nowhere_has_no_environment(self):
        self.backend.load(self.config_path, self.environments_path)
        stray = self.backend.config.get_dump_directory() / "backup_suelto.sql"
        stray.write_bytes(b"z" * 64)

        dump = next(d for d in self.backend.local_dumps() if d.path == stray)
        self.assertEqual(dump.environment_id, "")
        self.assertEqual(dump.origin, "—")

    def test_filters_cover_all_parents_types_and_the_leftovers(self):
        self.backend.load(self.config_path, self.environments_path)
        keys = [f.key for f in self.backend.dump_filters()]
        self.assertEqual(
            keys,
            ["all", "example_one", "example_one_prod", "example_one_qa", "unknown"],
        )

    def test_the_parent_filter_takes_every_type_under_it(self):
        self.backend.load(self.config_path, self.environments_path)
        filters = {f.key: f for f in self.backend.dump_filters()}
        prod = LocalDump(Path("/x/a.sql"), 1.0, 0.0, environment_id="example_one_prod")
        qa = LocalDump(Path("/x/b.sql"), 1.0, 0.0, environment_id="example_one_qa")
        stray = LocalDump(Path("/x/c.sql"), 1.0, 0.0)

        self.assertTrue(filters["example_one"].matches(prod))
        self.assertTrue(filters["example_one"].matches(qa))
        self.assertFalse(filters["example_one"].matches(stray))

        self.assertTrue(filters["example_one_prod"].matches(prod))
        self.assertFalse(filters["example_one_prod"].matches(qa))

        self.assertTrue(filters["unknown"].matches(stray))
        self.assertFalse(filters["unknown"].matches(prod))

        for dump in (prod, qa, stray):
            self.assertTrue(filters["all"].matches(dump))

    def test_a_short_mfa_code_is_rejected_before_calling_aws(self):
        self.backend.load(self.config_path, self.environments_path)
        with self.assertRaises(CoreError):
            self.backend.authenticate("123")
        with self.assertRaises(CoreError):
            self.backend.authenticate("abcdef")

    def test_remote_actions_are_refused_without_a_session(self):
        self.backend.load(self.config_path, self.environments_path)
        self.assertEqual(self.backend.session().state, "none")
        with self.assertRaises(CoreError) as raised:
            self.backend.require_session()
        self.assertIn("MFA", str(raised.exception))

    def test_an_environment_without_a_security_group_says_so(self):
        self.backend.load(self.config_path, self.environments_path)
        self.backend._inherited = True  # una sesión heredada alcanza para consultar
        env_type = self.backend.snapshot().find_type("example_one_qa")
        with self.assertRaises(CoreError) as raised:
            self.backend.security_group_plan(env_type)
        self.assertIn("security_group_id", str(raised.exception))

    def test_static_dns_is_known_without_calling_aws(self):
        self.backend.load(self.config_path, self.environments_path)
        snapshot = self.backend.snapshot()
        self.assertEqual(
            self.backend.known_dns(snapshot.find_type("example_one_prod")),
            "prod.example.com",
        )
        self.assertEqual(self.backend.known_dns(snapshot.find_type("example_one_qa")), "")

    def test_recreate_refuses_a_file_that_is_not_there(self):
        self.backend.load(self.config_path, self.environments_path)
        with self.assertRaises(CoreError):
            self.backend.recreate_database("alpha_db", self.directory / "no-existe.sql")

    def test_fingerprint_only_changes_when_the_render_would(self):
        self.backend.load(self.config_path, self.environments_path)
        first = self.backend.fingerprint()
        self.assertEqual(first, self.backend.fingerprint())
        (self.backend.config.get_dump_directory() / "otro.sql").write_bytes(b"z")
        self.assertNotEqual(first, self.backend.fingerprint())

    def test_reload_picks_up_an_environment_added_on_disk(self):
        self.backend.load(self.config_path, self.environments_path)
        payload = json.loads(json.dumps(ENVIRONMENTS))
        payload["environments"].append({"id": "otro", "name": "Otro", "types": []})
        Path(self.environments_path).write_text(json.dumps(payload), encoding="utf-8")
        # reload() usa el orden de búsqueda normal, así que se recarga explícito.
        self.backend.load(self.config_path, self.environments_path)
        self.assertEqual(len(self.backend.snapshot().environments), 2)


if __name__ == "__main__":
    unittest.main()

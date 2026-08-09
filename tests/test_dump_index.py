"""Pruebas del índice de dumps. Sin Qt: esto es del CLI, no de la UI."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from awsm_cli.operations.dump_index import (  # noqa: E402
    INDEX_NAME,
    DumpIndex,
    guess_environment_from_filename,
    normalize_environment_name,
)


ENVIRONMENT = {
    "id": "ops_prod",
    "name": "OPS · PROD",
    "parent_id": "ops",
}


class NormalizeTests(unittest.TestCase):
    def test_spaces_and_symbols_become_a_safe_folder_name(self):
        self.assertEqual(normalize_environment_name("Example One"), "example_one")
        self.assertEqual(normalize_environment_name("proj/x:1"), "projx1")

    def test_an_empty_id_still_yields_something_usable(self):
        self.assertEqual(normalize_environment_name("   "), "entorno")


class GuessTests(unittest.TestCase):
    """El prefijo sigue siendo el único dato de los dumps viejos."""

    def test_the_longest_matching_prefix_wins(self):
        ids = ["ops", "ops_prod"]
        self.assertEqual(
            guess_environment_from_filename("ops_prod_dump_2026-08-05.sql.gz", ids),
            "ops_prod",
        )

    def test_a_name_without_a_known_prefix_matches_nothing(self):
        self.assertEqual(
            guess_environment_from_filename("dump_prod_2026-08-05.sql.gz", ["ops_prod"]),
            "",
        )

    def test_a_partial_prefix_is_not_a_match(self):
        # 'opsx_dump...' no es del entorno 'ops': falta el separador.
        self.assertEqual(guess_environment_from_filename("opsx_dump.sql", ["ops"]), "")


class DumpIndexTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self._temporary.name)
        self.index = DumpIndex(self.directory, on_output=lambda _: None)

    def tearDown(self):
        self._temporary.cleanup()

    def _dump(self, relative: str) -> Path:
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"sql")
        return path

    def test_a_missing_index_reads_as_empty(self):
        self.assertEqual(self.index.load(), {})
        self.assertIsNone(self.index.get(self.directory / "nada.sql"))

    def test_recording_survives_a_reload(self):
        path = self._dump("ops_prod/dump_prod_2026-08-05.sql.gz")
        self.assertTrue(
            self.index.record(path, ENVIRONMENT, "dump_prod_2026-08-05.sql.gz", 8.43)
        )

        fresh = DumpIndex(self.directory, on_output=lambda _: None)
        record = fresh.get(path)
        self.assertIsNotNone(record)
        self.assertEqual(record.environment_id, "ops_prod")
        self.assertEqual(record.parent_id, "ops")
        self.assertEqual(record.environment_label, "OPS · PROD")
        self.assertEqual(record.remote_name, "dump_prod_2026-08-05.sql.gz")
        self.assertEqual(record.size_mb, 8.43)

    def test_the_key_is_the_path_relative_to_the_dump_folder(self):
        path = self._dump("ops_prod/dump.sql.gz")
        self.assertEqual(self.index.relative_key(path), "ops_prod/dump.sql.gz")

    def test_the_same_remote_name_in_two_environments_stays_separate(self):
        prod = self._dump("ops_prod/dump_prod.sql.gz")
        qa = self._dump("ops_qa/dump_prod.sql.gz")
        self.index.record(prod, ENVIRONMENT, "dump_prod.sql.gz", 1.0)
        self.index.record(qa, {"id": "ops_qa", "name": "OPS · QA", "parent_id": "ops"},
                          "dump_prod.sql.gz", 2.0)

        self.assertEqual(self.index.get(prod).environment_id, "ops_prod")
        self.assertEqual(self.index.get(qa).environment_id, "ops_qa")

    def test_environment_for_falls_back_to_the_prefix(self):
        legacy = self._dump("ops_qa_dump_2026-01-01.sql")
        self.assertEqual(
            self.index.environment_for(legacy, ["ops_prod", "ops_qa"]), "ops_qa"
        )

    def test_the_index_wins_over_the_prefix(self):
        # Un archivo cuyo nombre dice una cosa y el índice otra: manda el índice.
        path = self._dump("ops_qa_dump.sql")
        self.index.record(path, ENVIRONMENT, "dump.sql", 1.0)
        self.assertEqual(
            self.index.environment_for(path, ["ops_prod", "ops_qa"]), "ops_prod"
        )

    def test_forget_removes_only_that_entry(self):
        first = self._dump("ops_prod/a.sql")
        second = self._dump("ops_prod/b.sql")
        self.index.record(first, ENVIRONMENT, "a.sql", 1.0)
        self.index.record(second, ENVIRONMENT, "b.sql", 1.0)

        self.assertTrue(self.index.forget(first))
        self.assertIsNone(self.index.get(first))
        self.assertIsNotNone(self.index.get(second))
        self.assertFalse(self.index.forget(first))

    def test_prune_drops_entries_whose_file_is_gone(self):
        path = self._dump("ops_prod/a.sql")
        self.index.record(path, ENVIRONMENT, "a.sql", 1.0)
        path.unlink()
        self.assertEqual(self.index.prune(), 1)
        self.assertEqual(self.index.load(), {})

    def test_a_corrupt_index_does_not_take_the_app_down(self):
        (self.directory / INDEX_NAME).write_text("{ esto no es json", encoding="utf-8")
        warnings: list[str] = []
        index = DumpIndex(self.directory, on_output=warnings.append)
        self.assertEqual(index.load(), {})
        self.assertTrue(any("índice" in line for line in warnings))

    def test_the_written_file_is_readable_json(self):
        path = self._dump("ops_prod/a.sql")
        self.index.record(path, ENVIRONMENT, "a.sql", 1.0)
        payload = json.loads((self.directory / INDEX_NAME).read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertIn("ops_prod/a.sql", payload["dumps"])

    def test_no_temporary_file_is_left_behind(self):
        path = self._dump("ops_prod/a.sql")
        self.index.record(path, ENVIRONMENT, "a.sql", 1.0)
        self.assertEqual(list(self.directory.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

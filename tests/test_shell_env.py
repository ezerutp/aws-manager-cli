"""Pruebas del lector de variables del shell de login. Sin Qt.

El caso que motiva todo esto: la app lanzada desde el menú del escritorio no
hereda lo que exporta `.zshrc`, porque ese archivo lo lee solo un shell
interactivo. Desde una terminal las variables aparecen y desde el menú no.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from awsm_cli.utils.shell_env import (  # noqa: E402
    AWS_VARIABLES,
    BEGIN,
    END,
    RECORD,
    _build_script,
    _parse,
    import_missing_variables,
    is_fish,
    login_shell,
    missing_after_import,
    read_shell_variables,
)


BASH = shutil.which("bash")


class ShellDetectionTests(unittest.TestCase):
    def test_the_users_shell_is_what_counts(self):
        original = os.environ.get("SHELL")
        os.environ["SHELL"] = "/usr/bin/zsh"
        try:
            self.assertEqual(login_shell(), "/usr/bin/zsh")
        finally:
            if original is None:
                os.environ.pop("SHELL", None)
            else:
                os.environ["SHELL"] = original

    def test_without_shell_there_is_a_sane_fallback(self):
        original = os.environ.pop("SHELL", None)
        try:
            self.assertEqual(login_shell(), "/bin/sh")
        finally:
            if original is not None:
                os.environ["SHELL"] = original

    def test_fish_is_recognised_by_its_name(self):
        self.assertTrue(is_fish("/usr/bin/fish"))
        self.assertTrue(is_fish("fish"))
        self.assertFalse(is_fish("/usr/bin/zsh"))
        self.assertFalse(is_fish("/bin/bash"))
        self.assertFalse(is_fish(""))


class ScriptTests(unittest.TestCase):
    def test_posix_and_fish_get_different_syntax(self):
        """fish no entiende `if [ ... ]; then ... fi`."""
        posix = _build_script(["AWS_REGION"])
        fish = _build_script(["AWS_REGION"], fish=True)
        self.assertIn("then", posix)
        self.assertIn("fi", posix)
        self.assertIn("set -q", fish)
        self.assertIn("end", fish)
        self.assertNotIn("then", fish)

    def test_only_the_requested_names_are_emitted(self):
        script = _build_script(["AWS_REGION"])
        self.assertIn("AWS_REGION", script)
        self.assertNotIn("PATH", script)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", script)

    def test_a_name_that_is_not_a_valid_identifier_is_dropped(self):
        # No debería poder colarse nada raro en un script de shell.
        script = _build_script(["AWS_REGION", "rm -rf /; echo"])
        self.assertNotIn("rm -rf", script)
        self.assertIn("AWS_REGION", script)


class ParseTests(unittest.TestCase):
    def test_noise_around_the_markers_is_ignored(self):
        """Un `.zshrc` con plugins escupe cosas antes y después."""
        output = (
            "bienvenido a tu shell\n"
            f"{BEGIN}AWS_REGION=us-east-1{RECORD}{END}"
            "\nP10k: instalado"
        )
        self.assertEqual(_parse(output, ["AWS_REGION"]), {"AWS_REGION": "us-east-1"})

    def test_output_without_markers_yields_nothing(self):
        self.assertEqual(_parse("cualquier cosa", ["AWS_REGION"]), {})

    def test_a_value_with_an_equals_sign_survives(self):
        output = f"{BEGIN}AWS_SECRET_ACCESS_KEY=abc=def/ghi+{RECORD}{END}"
        self.assertEqual(
            _parse(output, ["AWS_SECRET_ACCESS_KEY"]),
            {"AWS_SECRET_ACCESS_KEY": "abc=def/ghi+"},
        )

    def test_a_name_outside_the_whitelist_is_discarded(self):
        """Aunque el shell lo imprima, si no se pidió no entra."""
        output = f"{BEGIN}PATH=/malicioso{RECORD}AWS_REGION=us-east-1{RECORD}{END}"
        self.assertEqual(_parse(output, ["AWS_REGION"]), {"AWS_REGION": "us-east-1"})


@unittest.skipUnless(BASH, "hace falta bash para esta prueba")
class RealShellTests(unittest.TestCase):
    """Con un shell de verdad y su archivo de configuración."""

    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.home = Path(self._temporary.name)
        # `.bashrc` lo lee bash cuando es interactivo, igual que zsh con .zshrc.
        (self.home / ".bashrc").write_text(
            'export AWS_ACCESS_KEY_ID="AKIADESDEELRCFILE123"\n'
            'export AWS_DEFAULT_REGION="sa-east-1"\n',
            encoding="utf-8",
        )
        self._environment = {
            **os.environ, "HOME": str(self.home), "SHELL": BASH,
        }
        for name in AWS_VARIABLES:
            self._environment.pop(name, None)

    def tearDown(self):
        self._temporary.cleanup()

    def _run(self, snippet: str) -> str:
        result = subprocess.run(
            [sys.executable, "-c", snippet],
            env=self._environment, capture_output=True, text=True,
            cwd=str(Path(__file__).resolve().parent.parent), timeout=60,
        )
        return (result.stdout or result.stderr).strip()

    def test_variables_exported_only_in_the_rc_file_are_recovered(self):
        output = self._run(
            "import sys; sys.path.insert(0, '.');"
            "from awsm_cli.utils.shell_env import read_shell_variables;"
            "found = read_shell_variables(['AWS_ACCESS_KEY_ID', 'AWS_DEFAULT_REGION']);"
            "print(sorted(found), found.get('AWS_DEFAULT_REGION'))"
        )
        self.assertIn("AWS_ACCESS_KEY_ID", output)
        self.assertIn("sa-east-1", output)

    def test_a_non_interactive_shell_would_not_have_seen_them(self):
        """La prueba de que el problema es real: sin -i no aparecen."""
        result = subprocess.run(
            [BASH, "-c", 'echo "[${AWS_ACCESS_KEY_ID}]"'],
            env=self._environment, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.stdout.strip(), "[]")

    def test_import_only_fills_what_is_missing(self):
        environment = {"AWS_DEFAULT_REGION": "eu-west-1"}
        imported = import_missing_variables(
            names=("AWS_ACCESS_KEY_ID", "AWS_DEFAULT_REGION"),
            environment=environment,
            shell=BASH,
        )
        # La que ya estaba puesta a propósito no se pisa.
        self.assertEqual(environment["AWS_DEFAULT_REGION"], "eu-west-1")
        self.assertNotIn("AWS_DEFAULT_REGION", imported)

    def test_nothing_to_do_costs_nothing(self):
        environment = {name: "ya-esta" for name in AWS_VARIABLES}
        self.assertEqual(import_missing_variables(environment=environment), ())


class ImportTests(unittest.TestCase):
    def test_a_shell_that_does_not_exist_is_not_an_error(self):
        environment: dict[str, str] = {}
        imported = import_missing_variables(
            names=("AWS_REGION",), environment=environment,
            shell="/no/existe/este/shell",
        )
        self.assertEqual(imported, ())
        self.assertEqual(environment, {})

    def test_the_log_line_names_variables_but_never_values(self):
        lines: list[str] = []
        environment: dict[str, str] = {}
        import_missing_variables(
            names=("AWS_REGION",), environment=environment,
            shell="/no/existe", on_output=lines.append,
        )
        # Sin nada que importar no se dice nada.
        self.assertEqual(lines, [])

    def test_missing_after_import_lists_what_is_still_absent(self):
        environment = {"AWS_ACCESS_KEY_ID": "x"}
        missing = missing_after_import(
            ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"), environment
        )
        self.assertEqual(missing, ("AWS_SECRET_ACCESS_KEY",))


if __name__ == "__main__":
    unittest.main()

"""Recuperar variables de entorno del shell de login.

El problema que resuelve este módulo: una app lanzada desde el menú del
escritorio **no ve lo que exporta `.zshrc`**. Ese archivo lo lee solo un shell
*interactivo*, y una app del menú la arranca systemd, que le pasa su propio
entorno. Desde una terminal la misma app sí las ve, y esa diferencia es
desconcertante: "las variables están, ¿por qué no las toma?".

La solución es preguntarle al shell del usuario, corriéndolo como shell de login
e interactivo, que es la combinación que lee `.zprofile` y `.zshrc`.

**Solo se importan las variables de una lista blanca.** Traerse el entorno entero
sería una forma cómoda de que un `.zshrc` cambie el `PATH` o el `LD_PRELOAD` de
este proceso, y no hay ninguna razón para necesitar eso: las únicas variables que
le importan a esta app son las de AWS.
"""
import os
import re
import subprocess
from typing import Callable, Dict, Iterable, Optional, Sequence, Tuple


# Lo único que se importa del shell. Nada de PATH, LD_*, ni comodines.
AWS_VARIABLES: Tuple[str, ...] = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_DEFAULT_REGION",
    "AWS_REGION",
    "AWS_PROFILE",
)

BEGIN = "__AWSM_ENV_BEGIN__"
END = "__AWSM_ENV_END__"
# Separador de registros. Un valor que lo contenga es, en la práctica, imposible.
RECORD = "\x1e"

_SAFE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Un shell interactivo puede tardar si el .zshrc hace cosas (plugins, prompts).
DEFAULT_TIMEOUT = 12


def login_shell() -> str:
    """El shell del usuario. `$SHELL` es lo que dice su cuenta que usa."""
    return os.environ.get("SHELL") or "/bin/sh"


def is_fish(shell: str) -> bool:
    return os.path.basename(shell or "") == "fish"


def _build_script(names: Sequence[str], fish: bool = False) -> str:
    """Un script que imprime solo las variables pedidas, entre marcadores.

    Los marcadores hacen que el ruido que escupa el `.zshrc` (mensajes de
    plugins, banners) no se confunda con datos.

    Hay dos versiones porque fish no entiende `if [ ... ]; then ... fi`. El resto
    (zsh, bash, dash, ksh) comparte la sintaxis POSIX. El separador se emite como
    carácter literal, no como escape, para no depender de qué escapes soporta el
    `printf` de cada shell.
    """
    lines = [f"printf '%s' '{BEGIN}'"]
    for name in names:
        # Los nombres vienen de la lista blanca, pero se validan igual antes de
        # interpolarlos en un script de shell.
        if not _SAFE_NAME.match(name):
            continue
        if fish:
            lines.append(
                f"if set -q {name}; printf '{name}=%s{RECORD}' \"${name}\"; end"
            )
        else:
            lines.append(
                f'if [ -n "${{{name}+x}}" ]; then printf \'{name}=%s{RECORD}\' "${name}"; fi'
            )
    lines.append(f"printf '%s' '{END}'")
    return "; ".join(lines)


def _parse(output: str, names: Sequence[str]) -> Dict[str, str]:
    if BEGIN not in output or END not in output:
        return {}
    payload = output.split(BEGIN, 1)[1].rsplit(END, 1)[0]
    allowed = set(names)
    found: Dict[str, str] = {}
    for record in payload.split(RECORD):
        if "=" not in record:
            continue
        name, value = record.split("=", 1)
        name = name.strip()
        if name in allowed:
            found[name] = value
    return found


def read_shell_variables(
    names: Sequence[str] = AWS_VARIABLES,
    shell: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, str]:
    """Lo que el shell de login del usuario tiene para estas variables.

    Se prueban varios modos porque no todos los shells aceptan `-i` sin una
    terminal: primero login+interactivo (que es el que lee `.zshrc`), después
    solo login, y por último a secas.
    """
    shell = shell or login_shell()
    script = _build_script(names, fish=is_fish(shell))

    # Los flags van separados: `-lic` junto no lo aceptan todos los shells, y
    # `-l -i -c` sí lo entienden zsh, bash y fish por igual.
    for flags in (("-l", "-i", "-c"), ("-l", "-c"), ("-i", "-c"), ("-c",)):
        try:
            result = subprocess.run(
                [shell, *flags, script],
                capture_output=True,
                text=True,
                timeout=timeout,
                # Sin esto, un `.zshrc` que lea algo dejaría el proceso colgado.
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            continue

        found = _parse(result.stdout or "", names)
        if found:
            return found
    return {}


def import_missing_variables(
    names: Sequence[str] = AWS_VARIABLES,
    environment: Optional[Dict[str, str]] = None,
    shell: Optional[str] = None,
    on_output: Optional[Callable[[str], None]] = None,
) -> Tuple[str, ...]:
    """Trae del shell las variables que falten y las aplica al proceso.

    Solo las que faltan: una variable puesta a propósito al arrancar la app le
    gana a la del `.zshrc`. Devuelve los nombres importados — **nunca los
    valores**, que no tienen por qué pasar por un log.
    """
    target = os.environ if environment is None else environment
    missing = [name for name in names if not target.get(name)]
    if not missing:
        return ()

    found = read_shell_variables(missing, shell=shell)
    imported = []
    for name, value in found.items():
        if value:
            target[name] = value
            imported.append(name)

    if on_output is not None and imported:
        on_output(
            f"✓ Variables tomadas del shell de login: {', '.join(sorted(imported))}"
        )
    return tuple(sorted(imported))


def missing_after_import(
    names: Iterable[str] = AWS_VARIABLES,
    environment: Optional[Dict[str, str]] = None,
) -> Tuple[str, ...]:
    target = os.environ if environment is None else environment
    return tuple(name for name in names if not target.get(name))

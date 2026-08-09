"""Mostrar y verificar secretos sin revelarlos.

La regla acá es que un valor sensible nunca se devuelve entero: se devuelve
enmascarado, o se devuelve un veredicto sobre él. Lo que se puede contestar es
"¿está puesto?", "¿es el que creo?" y "¿funciona?", que es lo que hace falta para
configurar sin tener el secreto en pantalla.
"""
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


BULLET = "•"


def mask_secret(value: str, lead: int = 4, tail: int = 4) -> str:
    """`AKIAIOSFODNN7EXAMPLE` -> `AKIA••••••••••••MPLE`.

    Se conservan las puntas porque son lo que permite reconocer *cuál* clave es
    sin revelarla. Un valor corto se tapa entero: mostrar 4 de 6 caracteres no
    sería enmascarar nada.
    """
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= lead + tail + 4:
        return BULLET * max(len(value), 8)
    hidden = BULLET * (len(value) - lead - tail)
    return f"{value[:lead]}{hidden}{value[-tail:]}"


def is_set(value: Optional[str]) -> bool:
    return bool((value or "").strip())


@dataclass(frozen=True)
class SecretStatus:
    """Qué se puede decir de un secreto sin mostrarlo."""

    name: str
    present: bool
    masked: str = ""
    length: int = 0
    source: str = ""  # "config" | "entorno" | ""

    @property
    def text(self) -> str:
        if not self.present:
            return "sin definir"
        origin = f" · desde {self.source}" if self.source else ""
        return f"{self.masked}  ({self.length} caracteres{origin})"


def describe_secret(name: str, config_value: str, environment_variable: str = "") -> SecretStatus:
    """El estado de un secreto, mirando la config y el entorno.

    El entorno gana, porque es lo que `MFAAuthenticator.setup_aws_credentials`
    mira primero: mostrar el de la config cuando el proceso va a usar otro sería
    mentir.
    """
    from_environment = os.environ.get(environment_variable, "") if environment_variable else ""
    value = from_environment or (config_value or "")
    if not is_set(value):
        return SecretStatus(name=name, present=False)
    return SecretStatus(
        name=name,
        present=True,
        masked=mask_secret(value),
        length=len(value.strip()),
        source="entorno" if from_environment else "config",
    )


@dataclass(frozen=True)
class KeyStatus:
    """El estado de una llave privada SSH, sin leer su contenido."""

    path: str
    exists: bool = False
    permissions: str = ""
    permissions_ok: bool = False
    fingerprint: str = ""
    problem: str = ""

    @property
    def ok(self) -> bool:
        return self.exists and self.permissions_ok and not self.problem

    @property
    def text(self) -> str:
        if not self.path:
            return "sin definir"
        if not self.exists:
            return "el archivo no existe"
        details = [f"permisos {self.permissions}"]
        if not self.permissions_ok:
            details.append("deberían ser 600")
        if self.fingerprint:
            details.append(self.fingerprint)
        if self.problem:
            details.append(self.problem)
        return " · ".join(details)


def describe_ssh_key(key_path: str) -> KeyStatus:
    """Verifica una llave privada sin mostrarla: existe, permisos, huella.

    La huella (`ssh-keygen -lf`) identifica la llave de forma única y es pública
    por naturaleza, así que se puede mostrar entera: sirve para confirmar que la
    llave configurada es la que uno cree, sin exponer nada.
    """
    key_path = (key_path or "").strip()
    if not key_path:
        return KeyStatus(path="")

    path = Path(key_path).expanduser()
    if not path.exists():
        return KeyStatus(path=key_path, exists=False)
    if path.is_dir():
        return KeyStatus(path=key_path, exists=True, problem="es un directorio")

    try:
        mode = path.stat().st_mode & 0o777
    except OSError as e:
        return KeyStatus(path=key_path, exists=True, problem=str(e))

    return KeyStatus(
        path=key_path,
        exists=True,
        permissions=oct(mode)[2:],
        permissions_ok=mode in (0o400, 0o600),
        fingerprint=_fingerprint(path),
    )


def _fingerprint(path: Path) -> str:
    try:
        result = subprocess.run(
            ['ssh-keygen', '-lf', str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return ""
        # "2048 SHA256:abc... comentario (RSA)" -> nos quedamos con la huella y el tipo.
        parts = result.stdout.strip().split()
        if len(parts) >= 2:
            kind = parts[-1].strip("()") if parts[-1].startswith("(") else ""
            return f"{parts[1]}{f' ({kind})' if kind else ''}"
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def fix_key_permissions(key_path: str) -> bool:
    try:
        os.chmod(Path(key_path).expanduser(), 0o600)
        return True
    except OSError:
        return False


def verify_aws_identity(timeout: int = 15) -> tuple[bool, str]:
    """¿Las credenciales actuales sirven? Pregunta a AWS, no adivina.

    Devuelve el ARN, que no es secreto: es la forma de confirmar *con qué
    identidad* se está trabajando sin mostrar ninguna clave.
    """
    try:
        result = subprocess.run(
            ['aws', 'sts', 'get-caller-identity', '--query', 'Arn', '--output', 'text'],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, "AWS CLI no está instalado."
    except subprocess.TimeoutExpired:
        return False, "AWS no respondió a tiempo."
    except OSError as e:
        return False, str(e)

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip().splitlines()
        return False, _scrub(message[-1] if message else "Credenciales rechazadas.")
    return True, result.stdout.strip()


# Un mensaje de error de AWS puede traer el access key adentro; no debe llegar
# entero a la pantalla ni al panel de log.
_ACCESS_KEY = re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{4})[0-9A-Z]{8}([0-9A-Z]{4})\b")


def _scrub(message: str) -> str:
    return _ACCESS_KEY.sub(lambda m: f"{m.group(1)}{BULLET * 8}{m.group(2)}", message)


scrub_secrets = _scrub

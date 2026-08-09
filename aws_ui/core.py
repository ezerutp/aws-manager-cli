"""Bridge between the UI and `awsm_cli`, with no Qt anywhere.

A diferencia de proxy-local, acá no se maneja el CLI por `subprocess`: el menú de
`awsm_cli` lee de `stdin`, no tiene un flag por operación, y automatizar sus
prompts sería fragilísimo. Las clases de `awsm_cli` se usan como librería, en
proceso, y `MenuManager` se reemplaza entero por la ventana.

Este módulo no importa Qt a propósito: es lo único que se puede probar sin GUI.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

# `awsm_cli` vive al lado de este paquete; instalado, ya está en el path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from awsm_cli import __codename__, __version__  # noqa: E402
from awsm_cli.auth import MFAAuthenticator  # noqa: E402
from awsm_cli.aws import EC2Manager, SecurityGroupManager  # noqa: E402
from awsm_cli.config import ConfigManager  # noqa: E402
from awsm_cli.operations import DatabaseOperations, DumpOperations, SSHOperations  # noqa: E402
from awsm_cli.operations.dump_index import (  # noqa: E402
    DumpIndex,
    guess_environment_from_filename,
)
from awsm_cli.utils import OperationsLogger  # noqa: E402
from awsm_cli.utils.shell_env import (  # noqa: E402
    AWS_VARIABLES,
    import_missing_variables,
    login_shell,
)
from awsm_cli.utils.secrets import (  # noqa: E402
    KeyStatus,
    SecretStatus,
    describe_secret,
    describe_ssh_key,
    fix_key_permissions,
    mask_secret,
    scrub_secrets,
    verify_aws_identity,
)
from awsm_cli.config.bundle import (  # noqa: E402
    BundleContents,
    BundleError,
    export_bundle,
    import_bundle,
    inspect_bundle,
)


VERSION = __version__
CODENAME = __codename__

# El flag para pasarle un comando varía entre emuladores. `--` en los de GNOME,
# `-e` en los viejos. Se prueban en este orden y se avisa si no hay ninguno.
TERMINALS: tuple[tuple[str, str], ...] = (
    ("ptyxis", "--"),
    ("kgx", "--"),
    ("gnome-terminal", "--"),
    ("konsole", "-e"),
    ("x-terminal-emulator", "-e"),
    ("xterm", "-e"),
)

REQUIRED_TOOLS = (
    ("aws", "AWS CLI", True),
    ("ssh", "SSH client", True),
    ("scp", "SCP", True),
    ("mysql", "MySQL client", False),
)


class CoreError(Exception):
    """An operation failed. The message is what the backend reported."""


# --------------------------------------------------------------------------- #
# Vistas: lo que la ventana renderiza, ya normalizado.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class EnvironmentType:
    """A PROD/QA entry inside a parent environment."""

    id: str
    name: str
    env_type: str
    instance_id: str
    security_group_id: str
    dns: str
    instance_name: str
    parent_id: str
    parent_name: str
    # Vacío significa "usar la llave general de config.json".
    key_path: str = ""

    @property
    def label(self) -> str:
        return f"{self.parent_name} · {self.name}"

    def as_dict(self) -> dict[str, str]:
        """The shape that `awsm_cli` expects: the raw entry from the JSON."""
        return {
            "id": self.id,
            "name": self.label,
            "env_type": self.env_type,
            "instance_id": self.instance_id,
            "security_group_id": self.security_group_id,
            "dns": self.dns,
            "instance_name": self.instance_name,
            "key_path": self.key_path,
            # Extra sobre el JSON: lo usa el índice de dumps para anotar de qué
            # entorno padre vino cada archivo.
            "parent_id": self.parent_id,
        }


@dataclass(frozen=True, slots=True)
class Environment:
    id: str
    name: str
    types: tuple[EnvironmentType, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RemoteDump:
    name: str
    size: str
    date: str


@dataclass(frozen=True, slots=True)
class LocalDump:
    """Un dump en disco, con el entorno del que salió.

    `environment_id` sale del índice de dumps, no de parsear el nombre: el
    archivo conserva el nombre que tenía en el servidor.
    """

    path: Path
    size_mb: float
    modified: float
    environment_id: str = ""
    environment_label: str = ""
    relative: str = ""

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def origin(self) -> str:
        return self.environment_label or self.environment_id or "—"

    @property
    def modified_text(self) -> str:
        return datetime.fromtimestamp(self.modified).strftime("%Y-%m-%d %H:%M")


@dataclass(frozen=True, slots=True)
class DumpFilter:
    """Una opción del filtro de entorno de la lista de dumps."""

    key: str  # "all" | "unknown" | id de un entorno padre o de un tipo
    label: str
    environment_ids: tuple[str, ...] = ()

    def matches(self, dump: LocalDump) -> bool:
        if self.key == "all":
            return True
        if self.key == "unknown":
            return not dump.environment_id
        return dump.environment_id in self.environment_ids


@dataclass(frozen=True, slots=True)
class Session:
    """MFA state. `inherited` es una sesión que ya venía en el entorno."""

    state: str = "none"  # none | inherited | active | not_required
    seconds_left: Optional[float] = None

    @property
    def usable(self) -> bool:
        if self.state in ("inherited", "not_required"):
            return True
        return self.state == "active" and not self.expired

    @property
    def expired(self) -> bool:
        return self.seconds_left is not None and self.seconds_left <= 0

    @property
    def text(self) -> str:
        if self.state == "not_required":
            return "MFA no requerido"
        if self.state == "inherited":
            return "sesión heredada"
        if self.state == "none":
            return "sin sesión"
        if self.expired:
            return "sesión expirada"
        if self.seconds_left is None:
            return "sesión activa"
        return f"{format_duration(self.seconds_left)} restantes"


@dataclass(frozen=True, slots=True)
class SecurityGroupPlan:
    """What authorizing this environment would actually change in AWS."""

    security_group_id: str
    current_ip: str
    description: str
    existing_rule_ip: Optional[str] = None
    already_authorized: bool = False

    @property
    def up_to_date(self) -> bool:
        return self.already_authorized or self.existing_rule_ip == f"{self.current_ip}/32"

    @property
    def summary(self) -> str:
        if self.up_to_date:
            return f"{self.current_ip} ya autorizada"
        if self.existing_rule_ip:
            return f"revoca {self.existing_rule_ip} · autoriza {self.current_ip}/32"
        return f"autoriza {self.current_ip}/32"


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    kind: str  # dump | recreate
    timestamp: str
    dump_name: str
    environment: str
    database: str
    duration: str
    size_mb: Optional[float]

    @property
    def when(self) -> str:
        try:
            return datetime.fromisoformat(self.timestamp).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return self.timestamp


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Everything the window needs for one render."""

    environments: tuple[Environment, ...] = field(default_factory=tuple)
    databases: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    dumps: tuple[LocalDump, ...] = field(default_factory=tuple)
    session: Session = field(default_factory=Session)
    dump_directory: Optional[Path] = None
    loaded: bool = False
    error: Optional[str] = None

    @property
    def type_count(self) -> int:
        return sum(len(env.types) for env in self.environments)

    def find_type(self, type_id: str) -> Optional[EnvironmentType]:
        for env in self.environments:
            for env_type in env.types:
                if env_type.id == type_id:
                    return env_type
        return None


# --------------------------------------------------------------------------- #
# Helpers puros
# --------------------------------------------------------------------------- #


def format_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_size(mb: float) -> str:
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.1f} MB"


def parse_databases(text: str) -> dict[str, str]:
    """`ops=ensolvers_ops, hirelens` -> `{"ops": "ensolvers_ops", "hirelens": "hirelens"}`.

    Un nombre suelto es su propia clave, que es el caso normal: la clave solo se
    separa cuando el alias del menú y el nombre real de la base no coinciden.
    """
    databases: dict[str, str] = {}
    for chunk in text.replace("\n", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" in chunk:
            key, value = chunk.split("=", 1)
            key, value = key.strip(), value.strip()
        else:
            key = value = chunk
        if key:
            databases[key] = value or key
    return databases


def validate_environments(environments: Sequence[dict]) -> str:
    """Qué impide guardar estos entornos. Cadena vacía si están bien.

    Los ids son la clave de todo lo demás — el índice de dumps, el filtro, el
    acceso directo con `--env` — así que un id repetido o vacío rompe cosas lejos
    de acá y conviene atajarlo antes de escribir.
    """
    seen_parents: set[str] = set()
    seen_types: set[str] = set()

    for parent in environments:
        parent_id = str(parent.get("id", "")).strip()
        if not parent_id:
            return "Hay un entorno padre sin id."
        if parent_id in seen_parents:
            return f"El id de entorno '{parent_id}' está repetido."
        seen_parents.add(parent_id)
        if not str(parent.get("name", "")).strip():
            return f"El entorno '{parent_id}' no tiene nombre."

        for env_type in parent.get("types", []):
            type_id = str(env_type.get("id", "")).strip()
            if not type_id:
                return f"Hay un tipo sin id en '{parent_id}'."
            if type_id in seen_types:
                return f"El id de tipo '{type_id}' está repetido."
            seen_types.add(type_id)
            if not str(env_type.get("name", "")).strip():
                return f"El tipo '{type_id}' no tiene nombre."
            if not str(env_type.get("instance_id", "")).strip():
                return f"El tipo '{type_id}' no tiene instance_id."
    return ""


def find_terminal() -> Optional[tuple[str, str]]:
    """The first installed terminal emulator, with the flag it wants."""
    for name, flag in TERMINALS:
        path = shutil.which(name)
        if path:
            return path, flag
    return None


def missing_tools() -> tuple[str, ...]:
    """Required tools that are not on PATH. `mysql` is optional and excluded."""
    return tuple(
        label for command, label, required in REQUIRED_TOOLS
        if required and shutil.which(command) is None
    )


def terminal_command(inner: Sequence[str], title: str = "") -> list[str]:
    """Wrap a command so it runs in a terminal window and does not vanish.

    Sin el `read` final, el emulador cierra la ventana en cuanto ssh termina y un
    error de conexión se pierde antes de poder leerlo.
    """
    terminal = find_terminal()
    if terminal is None:
        raise CoreError(
            "No se encontró ningún emulador de terminal. Instalá alguno de: "
            + ", ".join(name for name, _ in TERMINALS)
        )
    executable, flag = terminal
    banner = f"echo {shlex.quote(title)}; " if title else ""
    script = (
        f"{banner}{shlex.join(inner)}; status=$?; "
        'printf "\\n[sesión terminada, código %s] Enter para cerrar." "$status"; read _'
    )
    return [executable, flag, "bash", "-c", script]


def _entry_to_history(entry: dict[str, Any]) -> HistoryEntry:
    return HistoryEntry(
        kind=entry.get("_log_type", ""),
        timestamp=str(entry.get("timestamp", "")),
        dump_name=str(entry.get("nombre_dump", "")),
        environment=str(entry.get("entorno_origen", "")),
        database=str(entry.get("base_datos", "")),
        duration=str(entry.get("duracion_legible", "")),
        size_mb=entry.get("tamaño_mb"),
    )


# --------------------------------------------------------------------------- #
# Backend
# --------------------------------------------------------------------------- #


class Backend:
    """Facade over `awsm_cli`. Every call here can block: run it off the UI thread."""

    def __init__(self, on_output: Optional[Callable[[str], None]] = None) -> None:
        self._sink: Optional[Callable[[str], None]] = on_output
        self.config = ConfigManager(on_output=self._emit)
        self.mfa = MFAAuthenticator(self.config, on_output=self._emit)
        self.ec2 = EC2Manager(self.config, on_output=self._emit)
        self.sg = SecurityGroupManager(self.config, on_output=self._emit)
        self.ssh = SSHOperations(self.config, self.ec2, self.sg, on_output=self._emit)
        self.dumps = DumpOperations(self.config, self.ec2, on_output=self._emit)
        self.db = DatabaseOperations(self.config, on_output=self._emit)
        self.logger = OperationsLogger(on_output=self._emit)

        self._loaded = False
        self._load_error: Optional[str] = None
        # Una sesión que ya venía en el entorno (un `aws sts` previo en la shell)
        # sirve, pero su caducidad no está registrada en ningún lado.
        self._inherited = bool(os.environ.get("AWS_SESSION_TOKEN"))
        # Qué variables salieron del shell de login y no del entorno propio.
        self._shell_imported: set[str] = set()
        self._resolved_dns: dict[str, str] = {}

    # ---- salida -----------------------------------------------------------

    def set_output(self, sink: Optional[Callable[[str], None]]) -> None:
        self._sink = sink

    def _emit(self, *parts: Any, **_ignored: Any) -> None:
        """Stand-in for `print` inside `awsm_cli`; kwargs like end/flush are dropped."""
        if self._sink is None:
            return
        message = " ".join(str(part) for part in parts).rstrip("\n")
        for line in message.split("\n"):
            self._sink(line)

    def log(self, message: str) -> None:
        self._emit(message)

    # ---- carga ------------------------------------------------------------

    def load(
        self,
        config_path: Optional[str] = None,
        environments_path: Optional[str] = None,
    ) -> bool:
        """Read both configuration files. Never raises: the error goes in the snapshot.

        Sin rutas explícitas se usa el orden de búsqueda del CLI. Pasarlas sirve
        para las pruebas y para apuntar a una configuración alternativa.
        """
        self._load_error = None
        if not self.config.load_config(config_path):
            self._load_error = (
                "No se encontró config.json. Se buscó en:\n  "
                + "\n  ".join(str(p) for p in self.config.get_search_paths("config.json"))
            )
            self._loaded = False
            return False
        if not self.config.load_environments(environments_path):
            self._load_error = (
                "No se encontró config-environment.json. Se buscó en:\n  "
                + "\n  ".join(
                    str(p) for p in self.config.get_search_paths("config-environment.json")
                )
            )
            self._loaded = False
            return False
        self._loaded = True
        return True

    def reload(self) -> str:
        """Re-read the configuration after it was edited outside the app."""
        self._resolved_dns.clear()
        if not self.config.reload():
            raise CoreError(self._load_error or "No se pudo releer la configuración.")
        self._loaded = True
        return "Configuración recargada."

    def config_files(self) -> tuple[tuple[str, str, Optional[Path]], ...]:
        return tuple(
            (label, filename, self.config.find_config_file(filename))
            for filename, label in (
                ("config.json", "Configuración principal"),
                ("config-environment.json", "Configuración de entornos"),
            )
        )

    def logs_directory(self) -> Path:
        return self.logger.get_logs_directory()

    def keys_directory(self) -> Path:
        """Donde aterrizan las llaves importadas de un paquete."""
        return ConfigManager.USER_CONFIG_DIR / "keys"

    # ---- configuracion ----------------------------------------------------

    def config_snapshot(self) -> dict:
        """Copia editable de config.json. Los secretos van tal cual: quien la
        recibe es el diálogo, que se encarga de no mostrarlos."""
        import copy

        return copy.deepcopy(self.config.config_data)

    def environments_snapshot(self) -> list:
        import copy

        return copy.deepcopy(self.config.get_all_environments())

    def secret_status(self) -> tuple[SecretStatus, SecretStatus]:
        """Estado de las credenciales AWS, sin devolver su valor."""
        credentials = self.config.config_data.get("credentials", {})
        return (
            describe_secret("access_key", credentials.get("access_key", ""),
                            "AWS_ACCESS_KEY_ID"),
            describe_secret("secret_key", credentials.get("secret_key", ""),
                            "AWS_SECRET_ACCESS_KEY"),
        )

    def adopt_shell_environment(self) -> tuple[str, ...]:
        """Trae del shell de login las variables de AWS que falten.

        Lanzada desde el menú del escritorio, la app no hereda lo que exporta
        `.zshrc`: ese archivo lo lee solo un shell interactivo. Desde una terminal
        las variables aparecen y desde el menú no, que es exactamente el tipo de
        diferencia que vuelve loco a cualquiera.
        """
        imported = import_missing_variables(on_output=self._emit)
        if imported:
            self._shell_imported = set(imported)
            # Una sesión heredada pudo haber llegado recién ahora.
            self._inherited = bool(os.environ.get("AWS_SESSION_TOKEN"))
        return imported

    def environment_variables(self) -> tuple[tuple[str, bool, str, str], ...]:
        """Qué variables de AWS hay en el entorno del proceso, enmascaradas.

        Es lo que `MFAAuthenticator.setup_aws_credentials` mira antes que la
        configuración, así que conviene poder verlo: explica por qué la app usa
        una identidad y no la que dice el archivo. El origen distingue las que ya
        venían de las que se leyeron del shell.
        """
        rows = []
        for name in AWS_VARIABLES:
            value = os.environ.get(name, "")
            # La región y el perfil no son secretos y sirve verlos enteros.
            shown = value if name.endswith(("REGION", "PROFILE")) else mask_secret(value)
            if not value:
                origin = ""
            elif name in self._shell_imported:
                origin = "shell de login"
            else:
                origin = "proceso"
            rows.append((name, bool(value), shown, origin))
        return tuple(rows)

    def shell_name(self) -> str:
        return login_shell()

    def key_status(self, key_path: str = "") -> KeyStatus:
        return describe_ssh_key(key_path or self.config.get_key_path())

    def fix_key_permissions(self, key_path: str) -> str:
        if not fix_key_permissions(key_path):
            raise CoreError(f"No se pudieron corregir los permisos de {key_path}.")
        return f"Permisos de {Path(key_path).name} ajustados a 600."

    def verify_credentials(self) -> str:
        """Pregunta a AWS con qué identidad estamos trabajando."""
        ok, message = verify_aws_identity()
        if not ok:
            raise CoreError(scrub_secrets(message))
        return f"Credenciales válidas · {message}"

    def save_credentials(self, credentials: dict) -> str:
        """Guarda la sección `credentials`, respetando los secretos sin tocar.

        Un valor `None` significa "dejá el que estaba": el diálogo nunca ve el
        secreto actual, así que no puede reenviarlo.
        """
        data = self.config_snapshot()
        current = data.setdefault("credentials", {})
        for name, value in credentials.items():
            if value is None:
                continue
            current[name] = value
        if not self.config.save_config(data):
            raise CoreError("No se pudo guardar config.json.")
        return "Credenciales guardadas."

    def save_configuration(self, data: dict) -> str:
        """Escribe config.json de una sola vez.

        Guardar sección por sección serían varias escrituras, y un fallo a mitad
        dejaría la configuración medio vieja y medio nueva.
        """
        if not self.config.save_config(data):
            raise CoreError("No se pudo guardar config.json.")
        self._resolved_dns.clear()
        return "Configuración guardada."

    def save_section(self, section: str, values: dict) -> str:
        data = self.config_snapshot()
        data.setdefault(section, {}).update(values)
        if not self.config.save_config(data):
            raise CoreError("No se pudo guardar config.json.")
        self._resolved_dns.clear()
        return f"Sección '{section}' guardada."

    def save_environments(self, environments: list) -> str:
        problem = validate_environments(environments)
        if problem:
            raise CoreError(problem)
        if not self.config.save_environments(environments):
            raise CoreError("No se pudo guardar config-environment.json.")
        self._resolved_dns.clear()
        return f"{len(environments)} entorno(s) guardados."

    # ---- exportar / importar ---------------------------------------------

    def export_configuration(
        self, destination: Path, include_secrets: bool, include_keys: bool
    ) -> str:
        try:
            contents = export_bundle(
                Path(destination),
                self.config.config_data,
                self.config.get_all_environments(),
                include_secrets=include_secrets,
                include_keys=include_keys,
                on_output=self._emit,
            )
        except BundleError as error:
            raise CoreError(str(error)) from error
        return f"Paquete exportado · {contents.summary}"

    def inspect_configuration(self, source: Path) -> BundleContents:
        try:
            return inspect_bundle(Path(source))
        except BundleError as error:
            raise CoreError(str(error)) from error

    def import_configuration(self, source: Path) -> str:
        try:
            config, environments, contents = import_bundle(
                Path(source), self.keys_directory(), on_output=self._emit
            )
        except BundleError as error:
            raise CoreError(str(error)) from error

        # Un paquete sin credenciales no debe borrar las que ya había.
        if not contents.includes_secrets:
            existing = self.config.config_data.get("credentials", {})
            credentials = config.setdefault("credentials", {})
            for name in ("access_key", "secret_key"):
                if not credentials.get(name) and existing.get(name):
                    credentials[name] = existing[name]

        if not self.config.save_config(config):
            raise CoreError("No se pudo guardar la configuración importada.")
        if not self.config.save_environments(environments):
            raise CoreError("No se pudieron guardar los entornos importados.")
        self._resolved_dns.clear()
        self._loaded = True
        return f"Configuración importada · {contents.summary}"

    # ---- lectura ----------------------------------------------------------

    def session(self) -> Session:
        if not self.config.is_mfa_required():
            return Session(state="not_required")
        credentials = self.mfa.credentials
        if credentials is not None and credentials.is_valid():
            return Session(state="active", seconds_left=credentials.seconds_left())
        if self._inherited:
            return Session(state="inherited")
        return Session(state="none")

    def environments(self) -> tuple[Environment, ...]:
        """The environment tree from config. In memory, so it is cheap to poll."""
        if not self._loaded:
            return ()
        environments = []
        for raw in self.config.get_all_environments():
            parent_id = str(raw.get("id", ""))
            parent_name = str(raw.get("name", parent_id))
            types = tuple(
                EnvironmentType(
                    id=str(item.get("id", "")),
                    name=str(item.get("name", "")),
                    env_type=str(item.get("env_type", "")),
                    instance_id=str(item.get("instance_id", "")),
                    security_group_id=str(item.get("security_group_id", "")),
                    dns=str(item.get("dns", "")),
                    instance_name=str(item.get("instance_name", "")),
                    key_path=str(item.get("key_path", "") or ""),
                    parent_id=parent_id,
                    parent_name=parent_name,
                )
                for item in raw.get("types", [])
            )
            environments.append(Environment(id=parent_id, name=parent_name, types=types))
        return tuple(environments)

    def snapshot(self) -> Snapshot:
        if not self._loaded:
            return Snapshot(session=self.session(), loaded=False, error=self._load_error)
        return Snapshot(
            environments=self.environments(),
            databases=tuple(sorted(self.config.get_all_databases().items())),
            dumps=self.local_dumps(),
            session=self.session(),
            dump_directory=self.config.get_dump_directory(),
            loaded=True,
        )

    def fingerprint(self) -> tuple:
        """Cheap value that changes whenever the rendered state would change."""
        session = self.session()
        # Los segundos se redondean a minuto: si no, el fingerprint cambia en cada
        # tick y la ventana se reconstruye una vez por segundo sin motivo.
        remaining = None if session.seconds_left is None else int(session.seconds_left // 60)
        dumps = tuple((d.name, d.size_mb) for d in self.local_dumps())
        environments = tuple(
            (env.id, tuple(t.id for t in env.types)) for env in self.environments()
        )
        return (self._loaded, session.state, remaining, environments, dumps)

    def dump_index(self) -> DumpIndex:
        return DumpIndex(self.config.get_dump_directory(), on_output=self._emit)

    def local_dumps(self) -> tuple[LocalDump, ...]:
        if not self._loaded:
            return ()

        index = self.dump_index()
        records = index.load()
        environments = self.environments()
        labels = {
            env_type.id: env_type.label
            for env in environments for env_type in env.types
        }
        known_ids = list(labels)

        found: list[LocalDump] = []
        for path in self.db.get_sql_files_in_directory():
            try:
                stat = path.stat()
            except OSError:
                continue

            key = index.relative_key(path)
            record = records.get(key)
            if record is not None and record.environment_id:
                environment_id = record.environment_id
                label = record.environment_label or labels.get(environment_id, environment_id)
            else:
                # Dumps anteriores al índice: el entorno iba en el prefijo.
                environment_id = guess_environment_from_filename(path.name, known_ids)
                label = labels.get(environment_id, environment_id)

            found.append(
                LocalDump(
                    path=path,
                    size_mb=round(stat.st_size / (1024 * 1024), 2),
                    modified=stat.st_mtime,
                    environment_id=environment_id,
                    environment_label=label,
                    relative=key,
                )
            )
        found.sort(key=lambda dump: dump.modified, reverse=True)
        return tuple(found)

    def dump_filters(self) -> tuple[DumpFilter, ...]:
        """Las opciones del filtro: todos, cada entorno padre, cada tipo, y sueltos."""
        filters = [DumpFilter(key="all", label="Todos los entornos")]
        for env in self.environments():
            type_ids = tuple(env_type.id for env_type in env.types)
            if type_ids:
                filters.append(DumpFilter(key=env.id, label=env.name, environment_ids=type_ids))
            for env_type in env.types:
                filters.append(
                    DumpFilter(
                        key=env_type.id,
                        label=f"    {env_type.name}",
                        environment_ids=(env_type.id,),
                    )
                )
        filters.append(DumpFilter(key="unknown", label="Sin entorno conocido"))
        return tuple(filters)

    def history(self, limit: Optional[int] = None) -> tuple[HistoryEntry, ...]:
        entries = OperationsLogger.get_all_logs()
        entries.sort(key=lambda item: item.get("timestamp", ""), reverse=True)
        if limit:
            entries = entries[:limit]
        return tuple(_entry_to_history(entry) for entry in entries)

    # ---- autenticacion ----------------------------------------------------

    def authenticate(self, mfa_code: str) -> str:
        if not mfa_code.isdigit() or len(mfa_code) != 6:
            raise CoreError("El código MFA debe ser 6 dígitos.")
        if not self.mfa.perform_authentication(mfa_code):
            raise CoreError(
                "Autenticación MFA fallida. Verificá el código y que el "
                "dispositivo MFA esté asociado a estas credenciales."
            )
        self._inherited = False
        session = self.session()
        if session.seconds_left is not None:
            return f"Sesión MFA establecida · {format_duration(session.seconds_left)} restantes."
        return "Sesión MFA establecida."

    def sign_out(self) -> str:
        self.mfa.cleanup()
        self.mfa.credentials = None
        self._inherited = False
        return "Sesión cerrada."

    def require_session(self) -> None:
        session = self.session()
        if not session.usable:
            raise CoreError(
                "No hay una sesión MFA válida. Autenticate antes de operar sobre AWS."
            )

    # ---- AWS --------------------------------------------------------------

    def resolve_dns(self, env_type: EnvironmentType) -> str:
        self.require_session()
        dns = self.ec2.get_instance_dns(env_type.instance_id, env_type.dns)
        if not dns:
            raise CoreError(
                f"No se pudo obtener el DNS de {env_type.instance_id}. "
                "Verificá que la instancia esté corriendo."
            )
        self._resolved_dns[env_type.id] = dns
        return dns

    def known_dns(self, env_type: EnvironmentType) -> str:
        """The DNS already resolved this session, or the static one from config."""
        return self._resolved_dns.get(env_type.id, env_type.dns)

    def public_ip(self) -> str:
        ip = self.sg.get_current_public_ip()
        if not ip:
            raise CoreError("No se pudo obtener tu IP pública.")
        return ip

    def security_group_plan(self, env_type: EnvironmentType) -> SecurityGroupPlan:
        """What would change in the Security Group, without changing anything."""
        self.require_session()
        if not env_type.security_group_id:
            raise CoreError(
                f"'{env_type.label}' no tiene security_group_id en la configuración."
            )
        current_ip = self.public_ip()
        description = self.config.get_rule_description()
        data = self.sg.get_security_group_info(env_type.security_group_id)
        if not data:
            raise CoreError(
                f"No se pudo leer el Security Group {env_type.security_group_id}."
            )
        existing, already = self.sg.find_existing_rules(data, current_ip, description)
        return SecurityGroupPlan(
            security_group_id=env_type.security_group_id,
            current_ip=current_ip,
            description=description,
            existing_rule_ip=existing,
            already_authorized=bool(already),
        )

    def authorize_ip(self, env_type: EnvironmentType) -> str:
        """Revoke the stale rule and authorize the current IP, port 22."""
        self.require_session()
        if not self.sg.update_security_group(env_type.as_dict()):
            raise CoreError("No se pudo actualizar el Security Group.")
        return f"Security Group de {env_type.label} al día."

    # ---- SSH y MySQL interactivos ----------------------------------------

    def key_for(self, env_type: EnvironmentType) -> str:
        return self.config.get_key_path_for(env_type.as_dict())

    def ssh_command(self, env_type: EnvironmentType, dns: str) -> list[str]:
        return [
            "ssh",
            "-i", self.key_for(env_type),
            "-p", str(self.config.get_ssh_port()),
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"{self.config.get_ssh_user()}@{dns}",
        ]

    def open_ssh(self, env_type: EnvironmentType) -> str:
        """Resolve the DNS and hand the session to a terminal emulator.

        Una GUI no tiene terminal que heredar, así que la sesión interactiva se
        abre afuera. Lo que sí se hace acá, con feedback, es validar la clave y
        resolver el DNS.
        """
        self.require_session()
        key_path = self.key_for(env_type)
        if not self.ssh.validate_ssh_key(key_path):
            raise CoreError(f"La clave SSH no es usable: {key_path}")

        dns = self.resolve_dns(env_type)
        command = self.ssh_command(env_type, dns)
        self._launch_terminal(command, f"ssh · {env_type.label} · {dns}")
        return f"Sesión SSH abierta en una terminal: {dns}"

    def open_local_database(self, database: str) -> str:
        command = [
            "mysql",
            f"-u{self.config.get_mysql_user()}",
            f"--protocol={self.config.get_mysql_protocol()}",
            database,
        ]
        if shutil.which("mysql") is None:
            raise CoreError("MySQL client no está instalado o no está en PATH.")
        self._launch_terminal(command, f"mysql · {database}")
        return f"Sesión MySQL abierta en una terminal: {database}"

    def _launch_terminal(self, command: Sequence[str], title: str) -> None:
        wrapped = terminal_command(command, title)
        self._emit(f"Abriendo terminal: {shlex.join(command)}")
        try:
            # start_new_session evita que cerrar la UI se lleve puesta la terminal.
            subprocess.Popen(wrapped, start_new_session=True)
        except OSError as error:
            raise CoreError(f"No se pudo abrir la terminal: {error}") from error

    # ---- dumps ------------------------------------------------------------

    def remote_dumps(self, env_type: EnvironmentType) -> tuple[RemoteDump, ...]:
        self.require_session()
        dns = self.resolve_dns(env_type)
        listing = self.dumps.get_remote_dumps_list(
            self.key_for(env_type), self.config.get_ssh_user(), dns
        )
        return tuple(RemoteDump(name=name, size=size, date=date) for name, size, date in listing)

    def local_path_for(self, env_type: EnvironmentType, remote_name: str) -> Path:
        """`<dumps>/<entorno>/<nombre remoto>`, la misma ruta que usa el CLI."""
        return self.dumps.local_path_for(env_type.as_dict(), remote_name)

    def download_dump(
        self,
        env_type: EnvironmentType,
        remote_name: str,
        on_progress: Optional[Callable[[Optional[float], float, float], None]] = None,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> str:
        self.require_session()
        key_path = self.key_for(env_type)
        ssh_user = self.config.get_ssh_user()
        dns = self.resolve_dns(env_type)
        local_path = self.local_path_for(env_type, remote_name)

        total = self.dumps.get_remote_file_size(key_path, ssh_user, dns, remote_name)
        if total:
            self._emit(f"Tamaño remoto: {format_size(total / (1024 * 1024))}")
        else:
            self._emit("No se pudo leer el tamaño remoto: el avance va sin porcentaje.")

        self._emit(f"Archivo remoto: ~/{remote_name}")
        self._emit(f"Archivo local:  {local_path}")

        ok = self.dumps.download_file_scp(
            key_path, ssh_user, dns, remote_name, str(local_path),
            on_progress=on_progress,
            should_cancel=should_cancel,
            total_bytes=total,
        )
        if not ok:
            if should_cancel is not None and should_cancel():
                raise CoreError("Descarga cancelada. El archivo parcial se descartó.")
            raise CoreError(f"No se pudo descargar {remote_name}.")

        size_mb = self.dumps.get_file_size_mb(str(local_path))
        # El índice es lo que después permite filtrar por entorno sin mirar el nombre.
        self.dumps.record_download(env_type.as_dict(), local_path, remote_name, size_mb)
        self._emit(f"✓ Dump descargado: {local_path}")
        return f"{local_path.name} · {format_size(size_mb or 0.0)}"

    # ---- base de datos local ---------------------------------------------

    def recreate_database(
        self,
        database: str,
        sql_file: Path | str,
        on_progress: Optional[Callable[[Optional[float], float, float], None]] = None,
    ) -> str:
        if shutil.which("mysql") is None:
            raise CoreError("MySQL client no está instalado o no está en PATH.")
        path = Path(sql_file)
        if not path.exists():
            raise CoreError(f"El archivo no existe: {path}")
        if not self.db.recreate_database(database, str(path), on_progress=on_progress):
            raise CoreError(f"No se pudo recrear '{database}' desde {path.name}.")
        return f"Base '{database}' recreada desde {path.name}."

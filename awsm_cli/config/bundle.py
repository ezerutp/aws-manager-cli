"""Exportar e importar la configuración completa, con las llaves SSH.

Un paquete es un `.zip` con esta forma:

    manifest.json              qué trae y de cuándo
    config.json                credenciales, ssh, mysql, rutas
    config-environment.json    entornos y tipos
    keys/<nombre>.pem          las llaves privadas, si se pidió incluirlas

Al exportar, las rutas de las llaves dentro de `config.json` y de los entornos se
reescriben a `keys/<nombre>.pem`. Al importar se hace el camino inverso: las
llaves se copian a `~/.config/aws-manager/keys/` y las rutas apuntan ahí. Así el
paquete funciona en otra máquina, donde `/home/otro/...` no existiría.

**Un paquete con secretos es material sensible**: trae claves privadas SSH y, si
se incluyen, las credenciales de AWS. Se escribe con permisos 0600 y quien lo
exporta tiene que pedir explícitamente cada parte.
"""
import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


BUNDLE_VERSION = 1
MANIFEST_NAME = "manifest.json"
CONFIG_NAME = "config.json"
ENVIRONMENTS_NAME = "config-environment.json"
KEYS_DIR = "keys"

SECRET_FIELDS = ("access_key", "secret_key")


class BundleError(Exception):
    """El paquete no se pudo escribir o leer."""


@dataclass
class BundleContents:
    """Qué trae un paquete, para poder decirlo antes de importarlo."""

    version: int = 0
    created_at: str = ""
    includes_secrets: bool = False
    includes_keys: bool = False
    environment_count: int = 0
    type_count: int = 0
    key_names: List[str] = field(default_factory=list)
    source_host: str = ""

    @property
    def summary(self) -> str:
        parts = [f"{self.environment_count} entornos", f"{self.type_count} tipos"]
        parts.append(
            f"{len(self.key_names)} llave(s)" if self.key_names else "sin llaves"
        )
        parts.append("con credenciales AWS" if self.includes_secrets else "sin credenciales")
        return " · ".join(parts)


def _key_targets(config: Dict, environments: List[Dict]) -> List[Tuple[str, str]]:
    """Todas las llaves referenciadas: (etiqueta, ruta).

    La etiqueta es lo que nombra el archivo dentro del paquete. `general` es la
    llave de `config.json`; las propias de un entorno llevan su id.
    """
    targets: List[Tuple[str, str]] = []
    general = str(config.get('credentials', {}).get('key_path', '') or '').strip()
    if general:
        targets.append(("general", general))
    for parent in environments:
        for env_type in parent.get('types', []):
            own = str(env_type.get('key_path', '') or '').strip()
            if own:
                targets.append((str(env_type.get('id', 'entorno')), own))
    return targets


def _safe_name(label: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in label)
    return cleaned or "llave"


def export_bundle(
    destination: Path,
    config: Dict,
    environments: List[Dict],
    include_secrets: bool = False,
    include_keys: bool = True,
    on_output: Optional[Callable[[str], None]] = None,
) -> BundleContents:
    """Escribe el paquete. Devuelve lo que quedó adentro."""
    out = on_output or (lambda _message: None)
    destination = Path(destination).expanduser()

    exported_config = json.loads(json.dumps(config))
    exported_environments = json.loads(json.dumps(environments))

    if not include_secrets:
        credentials = exported_config.setdefault('credentials', {})
        for name in SECRET_FIELDS:
            if credentials.get(name):
                credentials[name] = ""
        out("Las credenciales AWS se excluyeron del paquete.")

    stored_keys: List[str] = []
    key_files: List[Tuple[str, Path]] = []
    if include_keys:
        used: Dict[str, str] = {}
        for label, source in _key_targets(config, environments):
            path = Path(source).expanduser()
            if not path.is_file():
                out(f"⚠ La llave de '{label}' no existe y se omite: {source}")
                continue
            # La misma llave usada por varios entornos se guarda una sola vez.
            if source in used:
                archive_name = used[source]
            else:
                archive_name = f"{_safe_name(label)}{path.suffix or '.pem'}"
                suffix = 2
                while any(archive_name == name for name, _ in key_files):
                    archive_name = f"{_safe_name(label)}_{suffix}{path.suffix or '.pem'}"
                    suffix += 1
                key_files.append((archive_name, path))
                used[source] = archive_name
                stored_keys.append(archive_name)

            relative = f"{KEYS_DIR}/{archive_name}"
            if label == "general":
                exported_config.setdefault('credentials', {})['key_path'] = relative
            else:
                for parent in exported_environments:
                    for env_type in parent.get('types', []):
                        if str(env_type.get('id', '')) == label:
                            env_type['key_path'] = relative
    else:
        # Sin llaves, las rutas del origen no sirven en otra máquina y confunden.
        exported_config.setdefault('credentials', {})['key_path'] = ""
        for parent in exported_environments:
            for env_type in parent.get('types', []):
                if env_type.get('key_path'):
                    env_type['key_path'] = ""

    contents = BundleContents(
        version=BUNDLE_VERSION,
        created_at=datetime.now().isoformat(timespec='seconds'),
        includes_secrets=include_secrets,
        includes_keys=bool(stored_keys),
        environment_count=len(exported_environments),
        type_count=sum(len(p.get('types', [])) for p in exported_environments),
        key_names=stored_keys,
        source_host=os.uname().nodename if hasattr(os, 'uname') else "",
    )

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + '.tmp')
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_NAME, json.dumps({
                'version': contents.version,
                'created_at': contents.created_at,
                'includes_secrets': contents.includes_secrets,
                'includes_keys': contents.includes_keys,
                'environment_count': contents.environment_count,
                'type_count': contents.type_count,
                'keys': contents.key_names,
                'source_host': contents.source_host,
            }, ensure_ascii=False, indent=2))
            archive.writestr(CONFIG_NAME,
                             json.dumps(exported_config, ensure_ascii=False, indent=2))
            archive.writestr(ENVIRONMENTS_NAME,
                             json.dumps({'environments': exported_environments},
                                        ensure_ascii=False, indent=2))
            for archive_name, path in key_files:
                archive.write(path, f"{KEYS_DIR}/{archive_name}")
        # El paquete puede traer llaves privadas: no debe nacer legible por otros.
        os.chmod(temporary, 0o600)
        temporary.replace(destination)
    except (OSError, zipfile.BadZipFile) as e:
        raise BundleError(f"No se pudo escribir el paquete: {e}") from e

    out(f"✓ Paquete exportado: {destination}")
    return contents


def inspect_bundle(source: Path) -> BundleContents:
    """Qué trae un paquete, sin escribir nada. Para poder avisar antes."""
    source = Path(source).expanduser()
    try:
        with zipfile.ZipFile(source) as archive:
            names = archive.namelist()
            if CONFIG_NAME not in names or ENVIRONMENTS_NAME not in names:
                raise BundleError(
                    "El archivo no parece un paquete de aws-manager: "
                    f"le faltan {CONFIG_NAME} o {ENVIRONMENTS_NAME}."
                )
            manifest = {}
            if MANIFEST_NAME in names:
                manifest = json.loads(archive.read(MANIFEST_NAME).decode('utf-8'))
            environments = json.loads(
                archive.read(ENVIRONMENTS_NAME).decode('utf-8')
            ).get('environments', [])
            config = json.loads(archive.read(CONFIG_NAME).decode('utf-8'))
            keys = [n for n in names if n.startswith(f"{KEYS_DIR}/") and not n.endswith('/')]
    except zipfile.BadZipFile as e:
        raise BundleError("El archivo no es un zip válido.") from e
    except (OSError, json.JSONDecodeError, KeyError) as e:
        raise BundleError(f"No se pudo leer el paquete: {e}") from e

    credentials = config.get('credentials', {})
    return BundleContents(
        version=int(manifest.get('version', 0)),
        created_at=str(manifest.get('created_at', '')),
        includes_secrets=any(credentials.get(name) for name in SECRET_FIELDS),
        includes_keys=bool(keys),
        environment_count=len(environments),
        type_count=sum(len(p.get('types', [])) for p in environments),
        key_names=[Path(n).name for n in keys],
        source_host=str(manifest.get('source_host', '')),
    )


def import_bundle(
    source: Path,
    keys_directory: Path,
    on_output: Optional[Callable[[str], None]] = None,
) -> Tuple[Dict, List[Dict], BundleContents]:
    """Lee un paquete y deja las llaves en disco.

    Devuelve `(config, environments, contenido)` con las rutas ya apuntando a las
    llaves copiadas. **No escribe la configuración**: eso lo decide quien llama,
    después de confirmar.
    """
    out = on_output or (lambda _message: None)
    source = Path(source).expanduser()
    contents = inspect_bundle(source)
    keys_directory = Path(keys_directory).expanduser()

    try:
        with zipfile.ZipFile(source) as archive:
            config = json.loads(archive.read(CONFIG_NAME).decode('utf-8'))
            environments = json.loads(
                archive.read(ENVIRONMENTS_NAME).decode('utf-8')
            ).get('environments', [])

            extracted: Dict[str, str] = {}
            for name in archive.namelist():
                if not name.startswith(f"{KEYS_DIR}/") or name.endswith('/'):
                    continue
                # Nunca se confía en la ruta que trae el zip: solo el nombre.
                safe = Path(name).name
                if not safe or safe in ('.', '..'):
                    continue
                target = keys_directory / safe
                keys_directory.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as origin, open(target, 'wb') as destination:
                    shutil.copyfileobj(origin, destination)
                # Una llave privada con permisos abiertos la rechaza el propio ssh.
                os.chmod(target, 0o600)
                extracted[name] = str(target)
                out(f"✓ Llave importada: {target}")
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as e:
        raise BundleError(f"No se pudo importar el paquete: {e}") from e

    def resolve(value: str) -> str:
        value = str(value or '').strip()
        if not value:
            return ""
        if value in extracted:
            return extracted[value]
        # Ruta absoluta de otra máquina: se deja como está y se avisa al validar.
        return value

    credentials = config.setdefault('credentials', {})
    credentials['key_path'] = resolve(credentials.get('key_path', ''))
    for parent in environments:
        for env_type in parent.get('types', []):
            if env_type.get('key_path'):
                env_type['key_path'] = resolve(env_type['key_path'])

    return config, environments, contents

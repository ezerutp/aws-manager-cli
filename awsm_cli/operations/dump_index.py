"""Metadata de los dumps descargados: de qué entorno vino cada archivo.

Antes esto se deducía del prefijo que se le agregaba al nombre del archivo. Eso
obligaba a renombrar el dump y a adivinar el entorno parseando el nombre, que se
rompe en cuanto un id de entorno contiene un guión bajo o alguien renombra algo.

Ahora el dump conserva el nombre que tenía en el servidor, se guarda en una
subcarpeta por entorno (dos entornos pueden tener un `dump_prod_2026-08-05.sql.gz`
cada uno) y la procedencia vive en este índice.

El índice es un archivo JSON al lado de los dumps. Si se borra, no se pierde nada
crítico: los dumps siguen ahí y la carpeta que los contiene sigue diciendo de qué
entorno son.
"""
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence


INDEX_NAME = ".aws-manager-dumps.json"
INDEX_VERSION = 1


def normalize_environment_name(env_name: str) -> str:
    """Normaliza un id de entorno a un nombre de carpeta seguro."""
    normalized = env_name.strip().lower().replace(' ', '_')
    normalized = re.sub(r'[^a-z0-9_-]', '', normalized)
    return normalized or 'entorno'


@dataclass(frozen=True)
class DumpRecord:
    """Lo que se sabe de un dump descargado."""

    relative_path: str
    environment_id: str = ""
    parent_id: str = ""
    environment_label: str = ""
    remote_name: str = ""
    downloaded_at: str = ""
    size_mb: Optional[float] = None

    def to_json(self) -> dict:
        return {
            'environment_id': self.environment_id,
            'parent_id': self.parent_id,
            'environment_label': self.environment_label,
            'remote_name': self.remote_name,
            'downloaded_at': self.downloaded_at,
            'size_mb': self.size_mb,
        }

    @staticmethod
    def from_json(relative_path: str, data: dict) -> "DumpRecord":
        return DumpRecord(
            relative_path=relative_path,
            environment_id=str(data.get('environment_id', '')),
            parent_id=str(data.get('parent_id', '')),
            environment_label=str(data.get('environment_label', '')),
            remote_name=str(data.get('remote_name', '')),
            downloaded_at=str(data.get('downloaded_at', '')),
            size_mb=data.get('size_mb'),
        )


def guess_environment_from_filename(name: str, environment_ids: Sequence[str]) -> str:
    """De qué entorno es un dump que no está en el índice.

    Los dumps descargados antes de que existiera este índice llevan el id del
    entorno como prefijo del nombre. Se busca el prefijo más largo que coincida,
    para que un id `ops_prod` le gane a un id `ops`.
    """
    matches = [
        env_id for env_id in environment_ids
        if name.startswith(f"{normalize_environment_name(env_id)}_")
    ]
    if not matches:
        return ""
    return max(matches, key=lambda env_id: len(normalize_environment_name(env_id)))


class DumpIndex:
    """Lee y escribe el índice de dumps de una carpeta."""

    def __init__(self, dump_directory: Path,
                 on_output: Optional[Callable[[str], None]] = None):
        self.dump_directory = Path(dump_directory)
        self._out: Callable[[str], None] = on_output or print

    @property
    def path(self) -> Path:
        return self.dump_directory / INDEX_NAME

    def relative_key(self, dump_path: Path) -> str:
        """La clave de un dump: su ruta relativa a la carpeta de dumps."""
        dump_path = Path(dump_path)
        try:
            return dump_path.resolve().relative_to(
                self.dump_directory.resolve()
            ).as_posix()
        except ValueError:
            # Un archivo elegido de otra carpeta no tiene entrada posible.
            return dump_path.name

    def load(self) -> Dict[str, DumpRecord]:
        """Todo el índice. Un archivo ilegible se trata como índice vacío."""
        if not self.path.exists():
            return {}
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            self._out(f"⚠ No se pudo leer el índice de dumps: {e}")
            return {}

        dumps = payload.get('dumps', {}) if isinstance(payload, dict) else {}
        if not isinstance(dumps, dict):
            return {}
        return {
            key: DumpRecord.from_json(key, value)
            for key, value in dumps.items()
            if isinstance(value, dict)
        }

    def get(self, dump_path: Path) -> Optional[DumpRecord]:
        return self.load().get(self.relative_key(dump_path))

    def environment_for(self, dump_path: Path,
                        environment_ids: Sequence[str] = ()) -> str:
        """El id del entorno de un dump: del índice, o del prefijo si es viejo."""
        record = self.get(dump_path)
        if record is not None and record.environment_id:
            return record.environment_id
        return guess_environment_from_filename(Path(dump_path).name, environment_ids)

    def record(self, dump_path: Path, environment: dict,
               remote_name: str = "", size_mb: Optional[float] = None) -> bool:
        """Anota de qué entorno vino un dump recién descargado."""
        entry = DumpRecord(
            relative_path=self.relative_key(dump_path),
            environment_id=str(environment.get('id', '')),
            parent_id=str(environment.get('parent_id', '')),
            environment_label=str(environment.get('name', '')),
            remote_name=remote_name or Path(dump_path).name,
            downloaded_at=datetime.now().isoformat(),
            size_mb=size_mb,
        )
        dumps = self.load()
        dumps[entry.relative_path] = entry
        return self._write(dumps)

    def forget(self, dump_path: Path) -> bool:
        dumps = self.load()
        if dumps.pop(self.relative_key(dump_path), None) is None:
            return False
        return self._write(dumps)

    def prune(self) -> int:
        """Saca del índice los dumps que ya no están en disco."""
        dumps = self.load()
        gone = [
            key for key in dumps
            if not (self.dump_directory / key).exists()
        ]
        if not gone:
            return 0
        for key in gone:
            del dumps[key]
        self._write(dumps)
        return len(gone)

    def _write(self, dumps: Dict[str, DumpRecord]) -> bool:
        payload = {
            'version': INDEX_VERSION,
            'dumps': {key: record.to_json() for key, record in sorted(dumps.items())},
        }
        try:
            self.dump_directory.mkdir(parents=True, exist_ok=True)
            # Escritura atómica: un índice a medias es peor que uno viejo.
            temporary = self.path.with_suffix('.json.tmp')
            with open(temporary, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            temporary.replace(self.path)
            return True
        except OSError as e:
            self._out(f"⚠ No se pudo guardar el índice de dumps: {e}")
            return False

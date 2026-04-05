"""Command-line argument parsing utilities."""
import argparse
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CliOptions:
    """Holds parsed CLI options."""
    local_mode: bool = False
    show_config: bool = False
    show_environments: bool = False
    show_logs: bool = False
    show_version: bool = False
    env_id: Optional[str] = None


def parse_cli_args(argv: List[str]) -> CliOptions:
    """Parse CLI arguments and return structured options."""
    parser = argparse.ArgumentParser(add_help=True)

    parser.add_argument(
        '--local',
        '-l',
        dest='local_mode',
        action='store_true',
        help='Ejecuta en modo local (sin MFA) mostrando solo operaciones locales.'
    )

    parser.add_argument(
        '--config',
        '-c',
        dest='show_config',
        action='store_true',
        help='Muestra qué archivos de configuración se están usando y permite abrir su carpeta.'
    )

    parser.add_argument(
        '--environments',
        '-e',
        dest='show_environments',
        action='store_true',
        help='Muestra todos los entornos disponibles y sus tipos.'
    )

    parser.add_argument(
        '--env',
        '-id',
        dest='env_id',
        type=str,
        metavar='ID',
        help='Acceso directo al entorno por ID (ej: projectx_prod).'
    )

    parser.add_argument(
        '--logs',
        dest='show_logs',
        action='store_true',
        help='Muestra el historial de operaciones de dump y recreate ordenados de más reciente a más antiguo.'
    )

    parser.add_argument(
        '--version',
        '-v',
        dest='show_version',
        action='store_true',
        help='Muestra la versión del binario y termina.'
    )

    args = parser.parse_args(argv)
    return CliOptions(
        local_mode=args.local_mode,
        show_config=args.show_config,
        show_environments=args.show_environments,
        show_logs=args.show_logs,
        show_version=args.show_version,
        env_id=args.env_id
    )

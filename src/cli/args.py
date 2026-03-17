"""Command-line argument parsing utilities."""
import argparse
from dataclasses import dataclass
from typing import List


@dataclass
class CliOptions:
    """Holds parsed CLI options."""
    local_mode: bool = False


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

    args = parser.parse_args(argv)
    return CliOptions(local_mode=args.local_mode)

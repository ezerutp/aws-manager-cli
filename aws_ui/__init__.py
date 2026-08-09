"""Interfaz gráfica de aws-manager (PySide6)."""

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from .app import main as _main

    return _main(argv)

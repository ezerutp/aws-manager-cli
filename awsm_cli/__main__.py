"""Punto de entrada del CLI: `python3 -m awsm_cli` y el binario `aws-manager`."""
import sys

from .main import main


def run() -> int:
    try:
        return main()
    except KeyboardInterrupt:
        print("\n\n✗ Programa interrumpido por el usuario.")
        return 0
    except Exception as e:
        print(f"\n✗ Error fatal: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(run())

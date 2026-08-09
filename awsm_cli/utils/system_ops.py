"""System-level helpers for desktop and shell operations."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def open_folder(folder: Path) -> bool:
    """Open a folder using the OS default file manager."""
    if sys.platform.startswith('linux'):
        opener = 'xdg-open'
    elif sys.platform == 'darwin':
        opener = 'open'
    elif os.name == 'nt':
        opener = 'explorer'
    else:
        print("No se pudo determinar cómo abrir carpetas en este sistema.")
        return False

    if shutil.which(opener) is None:
        print(f"No se encontró el comando '{opener}'.")
        return False

    try:
        subprocess.run([opener, str(folder)], check=False)
        return True
    except Exception as e:
        print(f"No se pudo abrir la carpeta: {e}")
        return False
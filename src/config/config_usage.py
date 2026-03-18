"""Helpers to inspect and display active configuration files."""
from .config_manager import ConfigManager
from src.utils import open_folder


def show_config_usage(config: ConfigManager) -> int:
    """Show resolved configuration files and optionally open container folder."""
    files_to_check = [
        ("config.json", "Configuración principal"),
        ("config-environment.json", "Configuración de entornos"),
    ]

    print("\n=== Archivos de configuración en uso ===")

    resolved_paths = []
    for filename, label in files_to_check:
        resolved = config.find_config_file(filename)
        print(f"\n{label} ({filename})")

        if resolved is not None:
            print(f"✓ En uso: {resolved}")
            resolved_paths.append(resolved)
            continue

        print("✗ No encontrado")
        print("  Buscado en:")
        for search_path in config.get_search_paths(filename):
            print(f"   - {search_path}")

    if not resolved_paths:
        return 0

    # Conservamos el orden de prioridad y removemos repetidos.
    folders = []
    for path in resolved_paths:
        parent = path.parent
        if parent not in folders:
            folders.append(parent)

    response = input("\n¿Deseas abrir la carpeta contenedora? [s/N]: ").strip().lower()
    if response not in ('s', 'si', 'sí', 'y', 'yes'):
        return 0

    target_folder = folders[0]
    if len(folders) > 1:
        print("\nSe encontraron múltiples carpetas:")
        for index, folder in enumerate(folders, start=1):
            print(f"  {index}. {folder}")

        selection = input(f"Selecciona una carpeta [1-{len(folders)}] (Enter = 1): ").strip()
        if selection:
            try:
                selected_index = int(selection)
                if 1 <= selected_index <= len(folders):
                    target_folder = folders[selected_index - 1]
                else:
                    print("Selección fuera de rango. Se abrirá la primera carpeta.")
            except ValueError:
                print("Selección inválida. Se abrirá la primera carpeta.")

    print(f"\nAbriendo: {target_folder}")
    open_folder(target_folder)
    return 0
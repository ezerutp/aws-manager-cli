"""Menu and UI Management Module"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from .. import __version__


class MenuManager:
    """Handles all menu display and user input"""
    
    def __init__(self, config_manager, db_operations):
        self.config = config_manager
        self.db_ops = db_operations
    
    @staticmethod
    def clear_screen():
        """Clear terminal screen"""
        os.system('clear' if os.name != 'nt' else 'cls')
    
    @staticmethod
    def wait_for_enter():
        """Wait for user to press Enter"""
        input("\nPresiona Enter para continuar...")
    
    @staticmethod
    def display_app_header():
        """Display main application header"""
        from .. import __version__
        print("╔════════════════════════════════════════════╗")
        print(f"║  AWS Environment Manager (Python v{__version__})   ║")
        print("╚════════════════════════════════════════════╝")
    
    @staticmethod
    def display_menu_header(subtitle: str = ""):
        """Display menu header with optional subtitle
        
        Args:
            subtitle: Optional subtitle (e.g., 'Python Edition', 'Modo Local')
        """
        from .. import __version__
        print("\n╔════════════════════════════════════════════╗")
        print(f"║  AWS Environment Manager (Python v{__version__})   ║")
        if subtitle:
            # Center subtitle
            padding = (44 - len(subtitle)) // 2
            subtitle_line = " " * padding + subtitle
            print(f"║{subtitle_line:<44}║")
        print("╚════════════════════════════════════════════╝")
    
    @staticmethod
    def display_section_header(title: str):
        """Display section header
        
        Args:
            title: Title of the section
        """
        width = max(len(title) + 4, 40)
        border = "═" * (width - 2)
        padding = (width - 2 - len(title)) // 2
        title_line = " " * padding + title + " " * (width - 2 - len(title) - padding)
        
        print(f"\n╔{border}╗")
        print(f"║{title_line}║")
        print(f"╚{border}╝")
    
    def display_main_menu(self) -> Dict:
        """Display main menu and return user selection
        
        Returns:
            dict with keys: 'action', 'environment', 'operation'
            action can be: 'ssh', 'dump', 'recreate_db', 'connect_local_db', 'snippets_coming_soon', 'exit'
        """
        environments = self.config.get_all_environments()
        
        self.display_menu_header("Python Edition")
        print("\nSelecciona una opción:\n")
        
        # Dynamic environment options
        menu_options = []
        option_num = 1
        
        for env in environments:
            env_name = env.get('name', '')
            
            # SSH option
            menu_options.append({
                'number': option_num,
                'action': 'ssh',
                'environment': env,
                'label': f"{env_name} - SSH"
            })
            print(f"{option_num}) {env_name} - SSH")
            option_num += 1
            
            # Dump option
            menu_options.append({
                'number': option_num,
                'action': 'dump',
                'environment': env,
                'label': f"{env_name} - Descargar SQL Dump"
            })
            print(f"{option_num}) {env_name} - Descargar SQL Dump")
            option_num += 1
        
        # Recreate DB option
        recreate_option = option_num
        print(f"\n{option_num}) Recrear Base de Datos (local)")
        option_num += 1

        # Connect local DB option
        connect_local_db_option = option_num
        print(f"{option_num}) Conectarse a BD local (consultas manuales)")
        option_num += 1

        # Snippets option (disabled for now)
        snippets_option = option_num
        print(f"{option_num}) Ejecutar snippets (Coming Soon - Deshabilitado)")
        option_num += 1
        
        # Exit option
        print(f"{option_num}) Salir")
        print("\n" + "="*40)
        
        # Get user input
        try:
            choice = input(f"Opción [1-{option_num}]: ").strip()
            
            if not choice.isdigit():
                print("✗ Opción inválida.")
                self.wait_for_enter()
                return {'action': 'invalid'}
            
            choice_num = int(choice)
            
            # Check if it's exit
            if choice_num == option_num:
                return {'action': 'exit'}
            
            # Check if it's recreate DB
            if choice_num == recreate_option:
                return {'action': 'recreate_db'}

            # Check if it's connect local DB
            if choice_num == connect_local_db_option:
                return {'action': 'connect_local_db'}

            # Check if it's snippets (disabled)
            if choice_num == snippets_option:
                return {'action': 'snippets_coming_soon'}
            
            # Check if it's a valid environment option
            for opt in menu_options:
                if opt['number'] == choice_num:
                    return {
                        'action': opt['action'],
                        'environment': opt['environment']
                    }
            
            print("✗ Opción inválida.")
            self.wait_for_enter()
            return {'action': 'invalid'}
            
        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada por el usuario.")
            return {'action': 'exit'}
        except Exception as e:
            print(f"\n✗ Error: {e}")
            self.wait_for_enter()
            return {'action': 'invalid'}

    def display_local_menu(self) -> Dict:
        """Display local-only menu and return user selection.

        Returns:
            dict with keys: 'action'
            action can be: 'recreate_db', 'connect_local_db', 'snippets_coming_soon', 'exit'
        """
        self.display_menu_header("Modo Local")
        print("\nSelecciona una opción:\n")

        print("1) Recrear Base de Datos (local)")
        print("2) Conectarse a BD local (consultas manuales)")
        print("3) Ejecutar snippets (Coming Soon - Deshabilitado)")
        print("4) Salir")
        print("\n" + "=" * 40)

        try:
            choice = input("Opción [1-4]: ").strip()

            if not choice.isdigit():
                print("✗ Opción inválida.")
                self.wait_for_enter()
                return {'action': 'invalid'}

            choice_num = int(choice)

            if choice_num == 1:
                return {'action': 'recreate_db'}
            if choice_num == 2:
                return {'action': 'connect_local_db'}
            if choice_num == 3:
                return {'action': 'snippets_coming_soon'}
            if choice_num == 4:
                return {'action': 'exit'}

            print("✗ Opción inválida.")
            self.wait_for_enter()
            return {'action': 'invalid'}

        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada por el usuario.")
            return {'action': 'exit'}
        except Exception as e:
            print(f"\n✗ Error: {e}")
            self.wait_for_enter()
            return {'action': 'invalid'}
    
    def select_database(self) -> Optional[str]:
        """Show database selection menu
        
        Returns:
            Database name or None if cancelled
        """
        print("\n=== Seleccionar Base de Datos ===")
        
        databases = self.config.get_all_databases()
        
        if not databases:
            print("✗ No hay bases de datos configuradas.")
            return None
        
        db_list = list(databases.items())
        
        print("\n¿Qué base de datos deseas recrear?\n")
        for i, (key, db_name) in enumerate(db_list, 1):
            print(f"{i}) {db_name}")
        
        print("0) Volver atrás")
        
        try:
            choice = input(f"\nOpción [0-{len(db_list)}]: ").strip()
            
            if not choice.isdigit():
                print("✗ Opción inválida.")
                return None
            
            choice_num = int(choice)
            
            if choice_num == 0:
                return None
            
            if 1 <= choice_num <= len(db_list):
                _, db_name = db_list[choice_num - 1]
                return db_name
            
            print("✗ Opción inválida.")
            return None
            
        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada.")
            return None
        except Exception as e:
            print(f"\n✗ Error: {e}")
            return None
    
    def select_sql_file(self) -> Optional[str]:
        """Show SQL file selection menu
        
        Returns:
            Path to SQL file or None if cancelled
        """
        print("\n=== Seleccionar Archivo SQL ===")
        
        sql_files = self.db_ops.get_sql_files_in_directory()
        
        if sql_files:
            print("\nArchivos SQL encontrados:\n")
            for i, sql_file in enumerate(sql_files, 1):
                size_bytes = sql_file.stat().st_size
                display_name = str(sql_file)
                if size_bytes >= 1024 ** 3:
                    size_str = f"{size_bytes / (1024 ** 3):.1f} GB"
                elif size_bytes >= 1024 ** 2:
                    size_str = f"{size_bytes / (1024 ** 2):.0f} MB"
                elif size_bytes >= 1024:
                    size_str = f"{size_bytes / 1024:.0f} KB"
                else:
                    size_str = f"{size_bytes} B"
                print(f"{i}) {display_name} [{size_str}]")
            
            print(f"{len(sql_files) + 1}) Ingresar ruta manual")
            print("0) Volver atrás")
            
            try:
                choice = input(f"\nOpción [0-{len(sql_files) + 1}]: ").strip()
                
                if not choice.isdigit():
                    print("✗ Opción inválida.")
                    return None
                
                choice_num = int(choice)
                
                if choice_num == 0:
                    return None
                
                if 1 <= choice_num <= len(sql_files):
                    return str(sql_files[choice_num - 1])
                
                if choice_num == len(sql_files) + 1:
                    # Manual path input
                    manual_path = input("\nIngresa la ruta del archivo SQL: ").strip()
                    if manual_path:
                        return manual_path
                    return None
                
                print("✗ Opción inválida.")
                return None
                
            except KeyboardInterrupt:
                print("\n\n✗ Operación cancelada.")
                return None
            except Exception as e:
                print(f"\n✗ Error: {e}")
                return None
        else:
            # No SQL files found, ask for manual input
            print("\nNo se encontraron archivos SQL en el directorio actual.")
            manual_path = input("Ingresa la ruta del archivo SQL (o Enter para cancelar): ").strip()
            
            if manual_path:
                return manual_path
            return None
    
    def display_header(self):
        """Display application header"""
        self.display_app_header()

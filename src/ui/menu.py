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
        from .. import __version__, __codename__
        print("╔════════════════════════════════════════════════╗")
        print(f"║  AWS Environment Manager ({__codename__} v{__version__})      ║")
        print("╚════════════════════════════════════════════════╝")
    
    @staticmethod
    def display_menu_header(subtitle: str = ""):
        """Display menu header with optional subtitle
        
        Args:
            subtitle: Optional subtitle (e.g., 'Python Edition', 'Modo Local')
        """
        from .. import __version__, __codename__
        print("\n╔════════════════════════════════════════════════╗")
        print(f"║  AWS Environment Manager ({__codename__} v{__version__})      ║")
        if subtitle:
            # Center subtitle
            padding = (48 - len(subtitle)) // 2
            subtitle_line = " " * padding + subtitle
            print(f"║{subtitle_line:<48}║")
        print("╚════════════════════════════════════════════════╝")
    
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
    
    def select_environment_parent(self) -> Optional[Dict]:
        """Select parent environment (projectx , projecty, etc.)
        
        Returns:
            Parent environment dict or None if cancelled
        """
        environments = self.config.get_all_environments()
        
        if not environments:
            print("✗ No hay entornos configurados.")
            self.wait_for_enter()
            return None
        
        self.display_menu_header("Python Edition")
        print("\n=== Seleccionar Entorno ===\n")
        
        for i, env in enumerate(environments, 1):
            print(f"{i}) {env.get('name', 'Sin nombre')}")
        
        print("\n--- Acciones Locales ---")
        recreate_db_option = len(environments) + 1
        print(f"{recreate_db_option}) Recrear Base de Datos (local)")
        
        connect_db_option = len(environments) + 2
        print(f"{connect_db_option}) Conectarse a BD local (consultas manuales)")
        
        view_logs_option = len(environments) + 3
        print(f"{view_logs_option}) Ver logs de operaciones")
        
        snippets_option = len(environments) + 4
        print(f"{snippets_option}) Ejecutar snippets (Coming Soon - Deshabilitado)")
        
        exit_option = len(environments) + 5
        print(f"\n{exit_option}) Salir")
        print("\n" + "="*48)
        
        try:
            choice = input(f"Opción [1-{exit_option}]: ").strip()
            
            if not choice.isdigit():
                print("✗ Opción inválida.")
                self.wait_for_enter()
                return None
            
            choice_num = int(choice)
            
            # Check environment selection
            if 1 <= choice_num <= len(environments):
                return environments[choice_num - 1]
            
            # Check local actions
            if choice_num == recreate_db_option:
                return {'_special_action': 'recreate_db'}
            
            if choice_num == connect_db_option:
                return {'_special_action': 'connect_local_db'}
            
            if choice_num == view_logs_option:
                return {'_special_action': 'view_logs'}
            
            if choice_num == snippets_option:
                return {'_special_action': 'snippets_coming_soon'}
            
            # Exit
            if choice_num == exit_option:
                return {'_special_action': 'exit'}
            
            print("✗ Opción inválida.")
            self.wait_for_enter()
            return None
            
        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada por el usuario.")
            return {'_special_action': 'exit'}
        except Exception as e:
            print(f"\n✗ Error: {e}")
            self.wait_for_enter()
            return None
    
    def select_environment_type(self, parent_env: Dict) -> Optional[Dict]:
        """Select environment type (PROD, QA, etc.) from parent environment
        
        Returns:
            Environment type dict or None if cancelled
        """
        types = parent_env.get('types', [])
        
        if not types:
            print("✗ No hay tipos de entorno configurados.")
            self.wait_for_enter()
            return None
        
        self.clear_screen()
        self.display_menu_header(f"{parent_env.get('name', '')} - Tipo de Entorno")
        print(f"\n=== Seleccionar Tipo para {parent_env.get('name', '')} ===\n")
        
        for i, env_type in enumerate(types, 1):
            print(f"{i}) {env_type.get('name', 'Sin nombre')}")
        
        print("0) Volver atrás")
        print("\n" + "="*48)
        
        try:
            choice = input(f"Opción [0-{len(types)}]: ").strip()
            
            if not choice.isdigit():
                print("✗ Opción inválida.")
                self.wait_for_enter()
                return None
            
            choice_num = int(choice)
            
            if choice_num == 0:
                return None
            
            if 1 <= choice_num <= len(types):
                return types[choice_num - 1]
            
            print("✗ Opción inválida.")
            self.wait_for_enter()
            return None
            
        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada por el usuario.")
            return None
        except Exception as e:
            print(f"\n✗ Error: {e}")
            self.wait_for_enter()
            return None
    
    def select_action(self, parent_env: Dict, env_type: Dict) -> Optional[Dict]:
        """Select action for the chosen environment type
        
        Returns:
            Action dict with 'action' and 'environment' keys, or None if cancelled
        """
        self.clear_screen()
        parent_name = parent_env.get('name', '')
        type_name = env_type.get('name', '')
        self.display_menu_header(f"{parent_name} - {type_name}")
        print(f"\n=== Acciones Disponibles para {parent_name} {type_name} ===\n")
        
        print("1) SSH - Conectarse al servidor")
        print("2) Descargar SQL Dump")
        print("\n0) Volver atrás")
        print("\n" + "="*48)
        
        try:
            choice = input("Opción [0-2]: ").strip()
            
            if not choice.isdigit():
                print("✗ Opción inválida.")
                self.wait_for_enter()
                return None
            
            choice_num = int(choice)
            
            if choice_num == 0:
                return None
            
            if choice_num == 1:
                return {
                    'action': 'ssh',
                    'environment': env_type
                }
            
            if choice_num == 2:
                return {
                    'action': 'dump',
                    'environment': env_type
                }
            
            print("✗ Opción inválida.")
            self.wait_for_enter()
            return None
            
        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada por el usuario.")
            return None
        except Exception as e:
            print(f"\n✗ Error: {e}")
            self.wait_for_enter()
            return None
    
    def display_main_menu(self) -> Dict:
        """Display hierarchical menu and return user selection
        
        Returns:
            dict with keys: 'action', 'environment'
            action can be: 'ssh', 'dump', 'recreate_db', 'connect_local_db', 'snippets_coming_soon', 'exit', 'invalid'
        """
        while True:
            self.clear_screen()
            
            # Level 1: Select parent environment
            parent_env = self.select_environment_parent()
            
            if not parent_env:
                return {'action': 'invalid'}
            
            # Check for special actions
            if '_special_action' in parent_env:
                return {'action': parent_env['_special_action']}
            
            # Level 2: Select environment type
            while True:
                env_type = self.select_environment_type(parent_env)
                
                if not env_type:
                    # Go back to level 1
                    break
                
                # Level 3: Select action
                while True:
                    result = self.select_action(parent_env, env_type)
                    
                    if not result:
                        # Go back to level 2
                        break
                    
                    # Return the selected action
                    return result

    def display_local_menu(self) -> Dict:
        """Display local-only menu and return user selection.

        Returns:
            dict with keys: 'action'
            action can be: 'recreate_db', 'connect_local_db', 'view_logs', 'snippets_coming_soon', 'exit'
        """
        self.display_menu_header("Modo Local")
        print("\nSelecciona una opción:\n")

        print("1) Recrear Base de Datos (local)")
        print("2) Conectarse a BD local (consultas manuales)")
        print("3) Ver logs de operaciones")
        print("4) Ejecutar snippets (Coming Soon - Deshabilitado)")
        print("5) Salir")
        print("\n" + "=" * 40)

        try:
            choice = input("Opción [1-5]: ").strip()

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
                return {'action': 'view_logs'}
            if choice_num == 4:
                return {'action': 'snippets_coming_soon'}
            if choice_num == 5:
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
    
    def display_env_menu(self, env_id: str, environment: Dict) -> Dict:
        """Display environment-specific menu with SSH, dump and local operations.
        
        Args:
            env_id: Environment ID (e.g., 'projectx_prod')
            environment: Environment configuration dict
        
        Returns:
            dict with keys: 'action', 'environment'
            action can be: 'ssh', 'dump', 'recreate_db', 'connect_local_db', 
                          'snippets_coming_soon', 'exit', 'invalid'
        """
        parent_name = environment.get('_parent_name', '')
        env_name = environment.get('name', '')
        display_name = f"{parent_name} {env_name}" if parent_name else env_name
        
        self.display_menu_header(f"Entorno: {env_id}")
        print(f"\n=== Acciones para {display_name} ===\n")
        
        print("--- Acciones Remotas ---")
        print("1) SSH - Conectarse al servidor")
        print("2) Descargar SQL Dump")
        
        print("\n--- Acciones Locales ---")
        print("3) Recrear Base de Datos (local)")
        print("4) Conectarse a BD local (consultas manuales)")
        print("5) Ver logs de operaciones")
        print("6) Ejecutar snippets (Coming Soon - Deshabilitado)")
        
        print("\n7) Salir")
        print("\n" + "=" * 48)
        
        try:
            choice = input("Opción [1-7]: ").strip()
            
            if not choice.isdigit():
                print("✗ Opción inválida.")
                self.wait_for_enter()
                return {'action': 'invalid'}
            
            choice_num = int(choice)
            
            if choice_num == 1:
                return {'action': 'ssh', 'environment': environment}
            if choice_num == 2:
                return {'action': 'dump', 'environment': environment}
            if choice_num == 3:
                return {'action': 'recreate_db'}
            if choice_num == 4:
                return {'action': 'connect_local_db'}
            if choice_num == 5:
                return {'action': 'view_logs'}
            if choice_num == 6:
                return {'action': 'snippets_coming_soon'}
            if choice_num == 7:
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

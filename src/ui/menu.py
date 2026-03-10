"""Menu and UI Management Module"""
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Tuple


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
    
    def display_main_menu(self) -> Dict:
        """Display main menu and return user selection
        
        Returns:
            dict with keys: 'action', 'environment', 'operation'
            action can be: 'ssh', 'dump', 'recreate_db', 'exit'
        """
        environments = self.config.get_all_environments()
        
        print("\n╔════════════════════════════════════╗")
        print("║  AWS Environment Manager v2.0      ║")
        print("║  Python Edition                    ║")
        print("╚════════════════════════════════════╝")
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
                print(f"{i}) {sql_file.name}")
            
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
        print("\n╔════════════════════════════════════════╗")
        print("║  AWS Environment Manager (Python v2.0) ║")
        print("╚════════════════════════════════════════╝")

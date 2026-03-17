#!/usr/bin/env python3
"""
AWS Environment Manager - Python Edition
Version 2.0

Migrated from shell scripts and C++ to Python for better maintainability.
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.config import ConfigManager
from src.auth import MFAAuthenticator
from src.aws import EC2Manager, SecurityGroupManager
from src.operations import SSHOperations, DumpOperations, DatabaseOperations
from src.ui import MenuManager
from src.cli import parse_cli_args


def check_prerequisites() -> bool:
    """Check if required tools are installed"""
    print("Verificando prerrequisitos...")
    
    checks = {
        'aws': 'AWS CLI',
        'ssh': 'SSH client',
        'scp': 'SCP (SSH copy)',
        'mysql': 'MySQL client (para recrear BD y consultas manuales)'
    }
    
    all_ok = True
    for cmd, name in checks.items():
        result = os.system(f"command -v {cmd} > /dev/null 2>&1")
        if result == 0:
            if cmd != 'mysql':  # MySQL is optional
                print(f"✓ {name} instalado.")
        else:
            if cmd == 'mysql':
                print(f"⚠ {name} no está instalado (necesario solo para recrear BD).")
            else:
                print(f"✗ {name} no está instalado.")
                all_ok = False
    
    return all_ok


def main():
    """Main application entry point"""
    cli_options = parse_cli_args(sys.argv[1:])

    # Display header
    print("╔════════════════════════════════════════╗")
    print("║  AWS Environment Manager (Python v2.0) ║")
    print("╚════════════════════════════════════════╝")

    if cli_options.local_mode:
        print("Modo local activado: se omite MFA y se muestran solo opciones locales.")
    
    # Check prerequisites
    if not check_prerequisites():
        print("\n✗ Faltan herramientas requeridas. Por favor instálalas antes de continuar.")
        return 1
    
    print()
    
    # Load configuration
    config = ConfigManager()
    
    print("Cargando configuración...")
    if not config.load_config():
        print("✗ Error al cargar configuración.")
        return 1
    
    if not config.load_environments():
        print("✗ Error al cargar entornos.")
        return 1
    
    print()
    
    # Initialize managers
    mfa_auth = MFAAuthenticator(config)
    ec2_manager = EC2Manager(config)
    sg_manager = SecurityGroupManager(config)
    ssh_ops = SSHOperations(config, ec2_manager, sg_manager)
    dump_ops = DumpOperations(config, ec2_manager)
    db_ops = DatabaseOperations(config)
    menu_manager = MenuManager(config, db_ops)
    
    if not cli_options.local_mode:
        # Perform MFA authentication once at the start (normal mode)
        print("=== Autenticación Inicial ===")
        if not mfa_auth.perform_authentication():
            print("\n✗ Error en autenticación. No se puede continuar.")
            return 1

        print("\n✓ Sistema listo. Presiona Enter para continuar...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada.")
            return 0
    
    menu_manager.clear_screen()
    
    # Main loop
    while True:
        try:
            # Display menu according to mode and get choice
            if cli_options.local_mode:
                choice = menu_manager.display_local_menu()
            else:
                choice = menu_manager.display_main_menu()
            action = choice.get('action')
            
            if action == 'exit':
                menu_manager.clear_screen()
                print("Saliendo del sistema...")
                print("\n✓ Sesión finalizada.")
                if not cli_options.local_mode:
                    mfa_auth.cleanup()
                return 0
            
            if action == 'invalid':
                menu_manager.clear_screen()
                continue
            
            menu_manager.clear_screen()
            
            # Handle SSH connection
            if action == 'ssh':
                if cli_options.local_mode:
                    print("\n✗ Esta operación no está disponible en modo local.")
                    menu_manager.wait_for_enter()
                    menu_manager.clear_screen()
                    continue

                environment = choice.get('environment')
                ssh_ops.connect_ssh(environment)
                print("\n✓ Sesión SSH finalizada.")
                menu_manager.wait_for_enter()
                menu_manager.clear_screen()
                continue
            
            # Handle SQL dump download
            if action == 'dump':
                if cli_options.local_mode:
                    print("\n✗ Esta operación no está disponible en modo local.")
                    menu_manager.wait_for_enter()
                    menu_manager.clear_screen()
                    continue

                environment = choice.get('environment')
                dump_ops.download_dump(environment)
                menu_manager.wait_for_enter()
                menu_manager.clear_screen()
                continue
            
            # Handle database recreation
            if action == 'recreate_db':
                # Select database
                db_name = menu_manager.select_database()
                if not db_name:
                    menu_manager.clear_screen()
                    continue
                
                menu_manager.clear_screen()
                
                # Select SQL file
                sql_file = menu_manager.select_sql_file()
                if not sql_file:
                    menu_manager.clear_screen()
                    continue
                
                menu_manager.clear_screen()
                
                # Recreate database
                db_ops.recreate_database(db_name, sql_file)
                menu_manager.wait_for_enter()
                menu_manager.clear_screen()
                continue

            # Handle local database interactive connection
            if action == 'connect_local_db':
                db_name = menu_manager.select_database()
                if not db_name:
                    menu_manager.clear_screen()
                    continue

                menu_manager.clear_screen()
                db_ops.connect_to_local_database(db_name)
                menu_manager.wait_for_enter()
                menu_manager.clear_screen()
                continue

            # Handle disabled snippets option
            if action == 'snippets_coming_soon':
                print("\n⚠ Esta opción estará disponible próximamente (Coming Soon).")
                print("Por ahora está deshabilitada.")
                menu_manager.wait_for_enter()
                menu_manager.clear_screen()
                continue
        
        except KeyboardInterrupt:
            print("\n\n✗ Operación interrumpida.")
            menu_manager.clear_screen()
            continue
        except Exception as e:
            print(f"\n✗ Error inesperado: {e}")
            menu_manager.wait_for_enter()
            menu_manager.clear_screen()
            continue


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n✗ Programa interrumpido por el usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error fatal: {e}")
        sys.exit(1)

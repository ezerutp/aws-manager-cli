"""Database Recreation Operations Module"""
import subprocess
from pathlib import Path
from typing import List, Optional


class DatabaseOperations:
    """Handles local database recreation operations"""
    
    def __init__(self, config_manager):
        self.config = config_manager
    
    def get_sql_files_in_directory(self, directory: str = ".") -> List[Path]:
        """Get all SQL files in directory"""
        try:
            path = Path(directory)
            sql_files = sorted(path.glob("*.sql"))
            return sql_files
        except Exception as e:
            print(f"✗ Error al listar archivos SQL: {e}")
            return []
    
    def execute_mysql_command(self, command: str, database: str = "") -> bool:
        """Execute MySQL command"""
        mysql_user = self.config.get_mysql_user()
        mysql_protocol = self.config.get_mysql_protocol()
        
        cmd = [
            'mysql',
            f'-u{mysql_user}',
            f'--protocol={mysql_protocol}'
        ]
        
        if database:
            cmd.append(database)
        
        cmd.extend(['-e', command])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            print("✗ Timeout al ejecutar comando MySQL.")
            return False
        except Exception as e:
            print(f"✗ Error al ejecutar MySQL: {e}")
            return False
    
    def import_sql_file(self, database: str, sql_file: str) -> bool:
        """Import SQL file into database"""
        mysql_user = self.config.get_mysql_user()
        mysql_protocol = self.config.get_mysql_protocol()
        
        try:
            # Open SQL file and pipe to MySQL
            with open(sql_file, 'r') as f:
                result = subprocess.run(
                    ['mysql',
                     f'-u{mysql_user}',
                     f'--protocol={mysql_protocol}',
                     database],
                    stdin=f,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minutes for large files
                )
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout al importar archivo SQL (>10 minutos).")
            return False
        except FileNotFoundError:
            print(f"✗ Archivo no encontrado: {sql_file}")
            return False
        except Exception as e:
            print(f"✗ Error al importar archivo SQL: {e}")
            return False
    
    def recreate_database(self, db_name: str, sql_file: str) -> bool:
        """Recreate database with SQL file"""
        print("\n=== Recreando Base de Datos ===")
        
        # Verify SQL file exists
        if not Path(sql_file).exists():
            print(f"✗ Error: Archivo no existe: {sql_file}")
            return False
        
        print(f"Base de datos: {db_name}")
        print(f"Archivo SQL:   {sql_file}")
        
        # Drop database
        print("\nEliminando base de datos existente...")
        if not self.execute_mysql_command(f"DROP DATABASE IF EXISTS {db_name};"):
            print("⚠ Advertencia: No se pudo eliminar la base de datos (puede no existir).")
        
        # Create database
        print("Creando base de datos...")
        if not self.execute_mysql_command(f"CREATE DATABASE {db_name};"):
            print("✗ Error: No se pudo crear la base de datos.")
            return False
        
        print("✓ Base de datos creada.")
        
        # Import SQL file
        print("Importando datos desde archivo SQL...")
        print("(Esto puede tomar varios minutos para archivos grandes)")
        
        if not self.import_sql_file(db_name, sql_file):
            print("✗ Error al importar datos.")
            return False
        
        print(f"✓ Base de datos '{db_name}' recreada exitosamente.")
        return True

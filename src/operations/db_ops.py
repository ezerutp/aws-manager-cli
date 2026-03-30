"""Database Recreation Operations Module"""
import gzip
import subprocess
import time
from pathlib import Path
from typing import List
from ..utils import OperationsLogger


class DatabaseOperations:
    """Handles local database recreation operations"""

    def __init__(self, config_manager):
        self.config = config_manager
        self.logger = OperationsLogger()

    def get_sql_files_in_directory(self, directory: str = ".") -> List[Path]:
        """Get all SQL and SQL.GZ files from directory, prioritizing db_dump."""
        try:
            search_paths = []

            if directory == ".":
                dump_dir = self.config.get_dump_directory()
                search_paths = [dump_dir, Path(".")]
            else:
                search_paths = [Path(directory)]

            sql_files = []
            seen = set()

            for path in search_paths:
                if not path.exists() or not path.is_dir():
                    continue

                for file_path in sorted(list(path.glob("*.sql")) + list(path.glob("*.sql.gz"))):
                    resolved = str(file_path.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        sql_files.append(file_path)

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

    def connect_to_local_database(self, database: str) -> bool:
        """Open interactive MySQL session for manual queries."""
        mysql_user = self.config.get_mysql_user()
        mysql_protocol = self.config.get_mysql_protocol()

        cmd = [
            'mysql',
            f'-u{mysql_user}',
            f'--protocol={mysql_protocol}',
            database
        ]

        print("\n=== Conexión a BD Local ===")
        print(f"Base de datos: {database}")
        print("Ingresa tus consultas SQL manuales.")
        print("Escribe 'exit' o 'quit' para volver al menú.")

        try:
            result = subprocess.run(cmd)
            if result.returncode != 0:
                print("✗ No se pudo abrir la sesión de MySQL.")
                return False
            return True
        except FileNotFoundError:
            print("✗ MySQL client no está instalado o no está en PATH.")
            return False
        except KeyboardInterrupt:
            print("\n✗ Sesión de MySQL interrumpida.")
            return False
        except Exception as e:
            print(f"✗ Error al conectar a MySQL local: {e}")
            return False

    def import_sql_file(self, database: str, sql_file: str) -> bool:
        """Import SQL/SQL.GZ file into database using streaming with progress"""
        mysql_user = self.config.get_mysql_user()
        mysql_protocol = self.config.get_mysql_protocol()
        file_path = Path(sql_file)

        try:
            if not file_path.exists():
                print(f"✗ Archivo no encontrado: {sql_file}")
                return False

            is_gz_file = file_path.suffix.lower() == '.gz'
            total_bytes = file_path.stat().st_size if not is_gz_file else None
            source_file = gzip.open(file_path, 'rb') if is_gz_file else open(file_path, 'rb')

            process = subprocess.Popen(
                [
                    'mysql',
                    f'-u{mysql_user}',
                    f'--protocol={mysql_protocol}',
                    database
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )

            bytes_sent = 0
            chunk_size = 1024 * 1024
            start_time = time.time()
            last_update = start_time

            with source_file:
                while True:
                    chunk = source_file.read(chunk_size)
                    if not chunk:
                        break

                    if process.stdin is None:
                        raise RuntimeError("No se pudo abrir stdin del proceso mysql")

                    process.stdin.write(chunk)
                    bytes_sent += len(chunk)

                    now = time.time()
                    if now - last_update >= 1:
                        elapsed = max(now - start_time, 0.001)
                        speed_mb_s = (bytes_sent / (1024 * 1024)) / elapsed

                        if total_bytes:
                            percent = (bytes_sent / total_bytes) * 100
                            print(
                                f"\rProgreso import: {percent:6.2f}% "
                                f"({bytes_sent / (1024 * 1024):.1f} MB / {total_bytes / (1024 * 1024):.1f} MB) "
                                f"- {speed_mb_s:.2f} MB/s",
                                end='',
                                flush=True
                            )
                        else:
                            print(
                                f"\rProgreso import: {bytes_sent / (1024 * 1024):.1f} MB enviados "
                                f"- {speed_mb_s:.2f} MB/s",
                                end='',
                                flush=True
                            )

                        last_update = now

            if process.stdin is not None:
                process.stdin.close()

            return_code = process.wait()
            stderr_output = ""
            if process.stderr is not None:
                stderr_output = process.stderr.read().decode(errors='replace').strip()

            total_time = max(time.time() - start_time, 0.001)
            final_speed = (bytes_sent / (1024 * 1024)) / total_time

            if total_bytes:
                print(
                    f"\rProgreso import: 100.00% ({bytes_sent / (1024 * 1024):.1f} MB / {total_bytes / (1024 * 1024):.1f} MB) "
                    f"- {final_speed:.2f} MB/s"
                )
            else:
                print(
                    f"\rProgreso import: {bytes_sent / (1024 * 1024):.1f} MB enviados "
                    f"- {final_speed:.2f} MB/s"
                )

            if return_code != 0:
                if stderr_output:
                    print(f"✗ MySQL reportó error: {stderr_output}")
                return False

            print(f"Tiempo total de importación: {total_time:.1f} segundos")
            return True

        except BrokenPipeError:
            print("\n✗ Se perdió la conexión con el proceso MySQL durante la importación.")
            return False
        except FileNotFoundError:
            print(f"✗ Archivo no encontrado: {sql_file}")
            return False
        except Exception as e:
            print(f"✗ Error al importar archivo SQL: {e}")
            return False

    def _extract_environment_from_filename(self, filename: str) -> str:
        """Extract environment name from dump filename"""
        try:
            # Get just the filename without path
            name = Path(filename).name
            
            # Common patterns:
            # example_one_prod_dump_2024-01-01.sql.gz
            # aws_dev_dump_2024-01-01.sql.gz
            # entorno_dump_production_2024-01-01.sql.gz
            
            # Try to extract the environment prefix before '_dump_'
            if '_dump_' in name.lower():
                # Split by '_dump_' and take everything before it
                prefix = name.lower().split('_dump_')[0]
                return prefix
            
            # Fallback: check for 'dump' without full pattern
            if 'dump' in name.lower():
                parts = name.split('_')
                if len(parts) > 0:
                    # Return the first part as environment
                    return parts[0]
            
            # If no pattern matches, return 'desconocido'
            return 'desconocido'
        except Exception:
            return 'desconocido'
    
    def _get_file_size_mb(self, filepath: str) -> float:
        """Get file size in MB"""
        try:
            path = Path(filepath)
            if path.exists():
                size_bytes = path.stat().st_size
                size_mb = size_bytes / (1024 * 1024)
                return round(size_mb, 2)
        except Exception:
            pass
        return 0.0

    def recreate_database(self, db_name: str, sql_file: str) -> bool:
        """Recreate database with SQL file"""
        print("\n=== Recreando Base de Datos ===")
        
        # Start timing
        start_time = time.time()

        if not Path(sql_file).exists():
            print(f"✗ Error: Archivo no existe: {sql_file}")
            return False

        print(f"Base de datos: {db_name}")
        print(f"Archivo SQL:   {sql_file}")

        print("\nEliminando base de datos existente...")
        if not self.execute_mysql_command(f"DROP DATABASE IF EXISTS {db_name};"):
            print("⚠ Advertencia: No se pudo eliminar la base de datos (puede no existir).")

        print("Creando base de datos...")
        if not self.execute_mysql_command(f"CREATE DATABASE {db_name};"):
            print("✗ Error: No se pudo crear la base de datos.")
            return False

        print("✓ Base de datos creada.")
        print("Importando datos desde archivo SQL...")

        if not self.import_sql_file(db_name, sql_file):
            print("✗ Error al importar datos.")
            return False

        print(f"✓ Base de datos '{db_name}' recreada exitosamente.")
        
        # Calculate total time
        end_time = time.time()
        duration = end_time - start_time
        
        # Extract environment and file info
        dump_filename = Path(sql_file).name
        environment = self._extract_environment_from_filename(dump_filename)
        file_size_mb = self._get_file_size_mb(sql_file)
        
        # Log the operation
        self.logger.log_database_recreate(
            dump_name=dump_filename,
            database_name=db_name,
            environment=environment,
            duration_seconds=duration,
            file_size_mb=file_size_mb
        )
        
        return True

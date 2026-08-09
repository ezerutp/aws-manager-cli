"""SQL Dump Download Operations Module"""
import subprocess
import time
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional
import re
from ..utils import OperationsLogger
from .dump_index import DumpIndex, normalize_environment_name


class DumpOperations:
    """Handles SQL dump download operations"""

    def __init__(self, config_manager, ec2_manager,
                 on_output: Optional[Callable[[str], None]] = None):
        self.config = config_manager
        self.ec2 = ec2_manager
        self._out: Callable[[str], None] = on_output or print
        self.logger = OperationsLogger(on_output=on_output)
    
    def check_remote_file_exists(self, key_path: str, ssh_user: str, 
                                  dns: str, filename: str) -> bool:
        """Check if dump file exists on remote server"""
        self._out("\nVerificando archivo en servidor remoto...")
        
        try:
            result = subprocess.run(
                ['ssh', '-i', key_path,
                 '-o', 'StrictHostKeyChecking=no',
                 '-o', 'UserKnownHostsFile=/dev/null',
                 f'{ssh_user}@{dns}',
                 f'[ -f ~/{filename} ]'],
                capture_output=True,
                timeout=15
            )
            
            return result.returncode == 0
            
        except Exception as e:
            self._out(f"✗ Error al verificar archivo remoto: {e}")
            return False
    
    def get_remote_dumps_list(self, key_path: str, ssh_user: str, dns: str) -> list:
        """Get list of available dump files on remote server
        
        Returns:
            List of tuples (filename, size, date) or empty list if error
        """
        try:
            result = subprocess.run(
                ['ssh', '-i', key_path,
                 '-o', 'StrictHostKeyChecking=no',
                 '-o', 'UserKnownHostsFile=/dev/null',
                 f'{ssh_user}@{dns}',
                 'ls -lh ~/dump*.sql.gz 2>/dev/null | awk \'{print $9"|"$5"|"$6" "$7" "$8}\''],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode != 0 or not result.stdout.strip():
                return []
            
            dumps = []
            for line in result.stdout.strip().split('\n'):
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) == 3:
                        filename = parts[0].strip().replace(f'/home/{ssh_user}/', '').replace('~/', '')
                        size = parts[1].strip()
                        date = parts[2].strip()
                        dumps.append((filename, size, date))
            
            return dumps
            
        except Exception as e:
            self._out(f"✗ Error al obtener lista de dumps: {e}")
            return []
    
    def list_remote_dumps(self, key_path: str, ssh_user: str, dns: str):
        """List available dump files on remote server"""
        self._out("\nArchivos disponibles:")
        
        try:
            result = subprocess.run(
                ['ssh', '-i', key_path,
                 '-o', 'StrictHostKeyChecking=no',
                 '-o', 'UserKnownHostsFile=/dev/null',
                 f'{ssh_user}@{dns}',
                 'ls -lh ~/dump*.sql.gz 2>/dev/null || echo "No se encontraron archivos dump"'],
                timeout=15
            )
        except Exception as e:
            self._out(f"✗ Error al listar archivos: {e}")
    
    def select_dump_from_list(self, dumps: list) -> Optional[str]:
        """Display dumps list and let user select one
        
        Args:
            dumps: List of tuples (filename, size, date)
            
        Returns:
            Selected filename or None if cancelled
        """
        if not dumps:
            self._out("\n✗ No se encontraron archivos dump en el servidor.")
            return None
        
        self._out("\n=== Archivos dump disponibles ===\n")
        
        for i, (filename, size, date) in enumerate(dumps, 1):
            self._out(f"{i}) {filename:40} {size:>8}  {date}")
        
        self._out("\n0) Cancelar")
        self._out("\n" + "="*70)
        
        try:
            choice = input(f"Selecciona el archivo a descargar [0-{len(dumps)}]: ").strip()
            
            if not choice.isdigit():
                self._out("✗ Opción inválida.")
                return None
            
            choice_num = int(choice)
            
            if choice_num == 0:
                self._out("Operación cancelada.")
                return None
            
            if 1 <= choice_num <= len(dumps):
                return dumps[choice_num - 1][0]  # Return filename
            
            self._out("✗ Opción inválida.")
            return None
            
        except KeyboardInterrupt:
            self._out("\n\n✗ Operación cancelada por el usuario.")
            return None
        except Exception as e:
            self._out(f"\n✗ Error: {e}")
            return None
    
    def get_remote_file_size(self, key_path: str, ssh_user: str,
                             dns: str, remote_file: str) -> Optional[int]:
        """Exact size in bytes of a remote file, or None if it cannot be read."""
        try:
            result = subprocess.run(
                ['ssh', '-i', key_path,
                 '-o', 'StrictHostKeyChecking=no',
                 '-o', 'UserKnownHostsFile=/dev/null',
                 f'{ssh_user}@{dns}',
                 f'stat -c%s ~/{remote_file}'],
                capture_output=True,
                text=True,
                timeout=15
            )
            if result.returncode != 0:
                return None
            return int(result.stdout.strip())
        except (ValueError, Exception):
            return None

    def download_file_scp(self, key_path: str, ssh_user: str,
                          dns: str, remote_file: str, local_file: str,
                          on_progress: Optional[Callable[[Optional[float], float, float], None]] = None,
                          should_cancel: Optional[Callable[[], bool]] = None,
                          total_bytes: Optional[int] = None) -> bool:
        """Download file using SCP.

        `scp` solo dibuja su barra cuando stdout es una terminal, así que en una GUI
        no hay nada que capturar. El progreso se mide del lado local: el tamaño del
        archivo que se está escribiendo contra el tamaño remoto, que se consulta
        antes de arrancar.
        """
        self._out("\nDescargando SQL dump...")

        command = ['scp', '-i', key_path,
                   '-o', 'StrictHostKeyChecking=no',
                   '-o', 'UserKnownHostsFile=/dev/null',
                   f'{ssh_user}@{dns}:~/{remote_file}',
                   local_file]

        if on_progress is None and should_cancel is None:
            try:
                result = subprocess.run(command, timeout=1800)  # 30 min para archivos grandes
                return result.returncode == 0
            except subprocess.TimeoutExpired:
                self._out("✗ Timeout al descargar archivo (>30 minutos).")
                return False
            except Exception as e:
                self._out(f"✗ Error al descargar archivo: {e}")
                return False

        path = Path(local_file)
        deadline = time.time() + 1800
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Exception as e:
            self._out(f"✗ Error al iniciar la descarga: {e}")
            return False

        start_time = time.time()
        try:
            while process.poll() is None:
                if should_cancel is not None and should_cancel():
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    # Un .sql.gz truncado parece válido hasta que falla el import,
                    # así que el archivo a medias se borra y se dice que se borró.
                    removed = self._discard_partial(path)
                    self._out("✗ Descarga cancelada." + (f" Se descartó {path.name}." if removed else ""))
                    return False

                if time.time() > deadline:
                    process.kill()
                    self._discard_partial(path)
                    self._out("✗ Timeout al descargar archivo (>30 minutos).")
                    return False

                if on_progress is not None:
                    written = path.stat().st_size if path.exists() else 0
                    elapsed = max(time.time() - start_time, 0.001)
                    percent = (written / total_bytes) * 100 if total_bytes else None
                    on_progress(percent, written / (1024 * 1024),
                                (written / (1024 * 1024)) / elapsed)

                time.sleep(0.4)
        except Exception as e:
            process.kill()
            self._out(f"✗ Error al descargar archivo: {e}")
            return False

        stderr_output = ""
        if process.stderr is not None:
            stderr_output = process.stderr.read().decode(errors='replace').strip()

        if process.returncode != 0:
            if stderr_output:
                self._out(f"✗ scp reportó error: {stderr_output}")
            self._discard_partial(path)
            return False

        if on_progress is not None:
            written = path.stat().st_size if path.exists() else 0
            elapsed = max(time.time() - start_time, 0.001)
            on_progress(100.0 if total_bytes else None, written / (1024 * 1024),
                        (written / (1024 * 1024)) / elapsed)
        return True

    def _discard_partial(self, path: Path) -> bool:
        """Delete a half-written download. Returns whether something was removed."""
        try:
            if path.exists():
                path.unlink()
                return True
        except OSError as e:
            self._out(f"⚠ No se pudo borrar el archivo parcial {path}: {e}")
        return False


    def get_file_size_mb(self, filepath: str) -> Optional[float]:
        """Get file size in MB"""
        try:
            path = Path(filepath)
            if path.exists():
                size_bytes = path.stat().st_size
                size_mb = size_bytes / (1024 * 1024)
                return round(size_mb, 2)
        except Exception:
            pass
        return None

    # Se mantiene como método de la clase porque era parte de su API pública;
    # la implementación vive con el índice, que es quien la necesita.
    normalize_environment_name = staticmethod(normalize_environment_name)
    
    def download_dump(self, environment: dict) -> bool:
        """Download SQL dump from environment"""
        env_name = environment.get('name', '')
        env_id = environment.get('id', '')
        self._out(f"\n=== Descargando SQL Dump de {env_name} ===")
        
        key_path = self.config.get_key_path_for(environment)
        ssh_user = self.config.get_ssh_user()

        # Get DNS
        instance_id = environment.get('instance_id', '')
        static_dns = environment.get('dns', '')
        dns = self.ec2.get_instance_dns(instance_id, static_dns)
        
        if not dns:
            self._out("✗ Error al obtener DNS.")
            return False
        
        # Get list of available dumps
        self._out("\nObteniendo lista de dumps disponibles...")
        dumps = self.get_remote_dumps_list(key_path, ssh_user, dns)
        
        # Let user select from list
        dump_filename = self.select_dump_from_list(dumps)
        
        if not dump_filename:
            return False
        
        local_file_path = self.local_path_for(environment, dump_filename)

        self._out(f"\nArchivo remoto: ~/{dump_filename}")
        self._out(f"Archivo local:  {local_file_path}")

        # Download file
        if not self.download_file_scp(key_path, ssh_user, dns, dump_filename, str(local_file_path)):
            self._out("✗ Error al descargar archivo.")
            return False

        # Show success and file size
        self._out(f"✓ SQL dump descargado exitosamente: {local_file_path}")

        size_mb = self.get_file_size_mb(str(local_file_path))
        if size_mb:
            self._out(f"Tamaño del archivo: {size_mb} MB")

        self.record_download(environment, local_file_path, dump_filename, size_mb)
        return True

    def local_path_for(self, environment: dict, remote_name: str) -> Path:
        """Dónde se guarda un dump: una subcarpeta por entorno.

        El archivo conserva el nombre que tenía en el servidor. La subcarpeta es
        lo que evita que dos entornos con un dump del mismo nombre se pisen, y
        de qué entorno es cada uno lo dice el índice.
        """
        dump_dir = self.config.get_dump_directory()
        folder = dump_dir / normalize_environment_name(environment.get('id', ''))
        folder.mkdir(parents=True, exist_ok=True)
        return folder / remote_name

    def record_download(self, environment: dict, local_file_path: Path,
                        remote_name: str, size_mb: Optional[float]) -> None:
        """Anota la descarga en el índice de dumps y en el log de operaciones."""
        index = DumpIndex(self.config.get_dump_directory(), on_output=self._out)
        index.record(local_file_path, environment, remote_name, size_mb)

        # En el log se guarda la ruta relativa: con nombres remotos repetidos,
        # el nombre suelto ya no alcanza para saber de qué dump se habla.
        self.logger.log_dump_download(
            dump_name=index.relative_key(local_file_path),
            environment=environment.get('id', ''),
            file_size_mb=size_mb
        )

"""SQL Dump Download Operations Module"""
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional
import re
from ..utils import OperationsLogger


class DumpOperations:
    """Handles SQL dump download operations"""
    
    def __init__(self, config_manager, ec2_manager):
        self.config = config_manager
        self.ec2 = ec2_manager
        self.logger = OperationsLogger()
    
    def check_remote_file_exists(self, key_path: str, ssh_user: str, 
                                  dns: str, filename: str) -> bool:
        """Check if dump file exists on remote server"""
        print("\nVerificando archivo en servidor remoto...")
        
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
            print(f"✗ Error al verificar archivo remoto: {e}")
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
            print(f"✗ Error al obtener lista de dumps: {e}")
            return []
    
    def list_remote_dumps(self, key_path: str, ssh_user: str, dns: str):
        """List available dump files on remote server"""
        print("\nArchivos disponibles:")
        
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
            print(f"✗ Error al listar archivos: {e}")
    
    def select_dump_from_list(self, dumps: list) -> Optional[str]:
        """Display dumps list and let user select one
        
        Args:
            dumps: List of tuples (filename, size, date)
            
        Returns:
            Selected filename or None if cancelled
        """
        if not dumps:
            print("\n✗ No se encontraron archivos dump en el servidor.")
            return None
        
        print("\n=== Archivos dump disponibles ===\n")
        
        for i, (filename, size, date) in enumerate(dumps, 1):
            print(f"{i}) {filename:40} {size:>8}  {date}")
        
        print("\n0) Cancelar")
        print("\n" + "="*70)
        
        try:
            choice = input(f"Selecciona el archivo a descargar [0-{len(dumps)}]: ").strip()
            
            if not choice.isdigit():
                print("✗ Opción inválida.")
                return None
            
            choice_num = int(choice)
            
            if choice_num == 0:
                print("Operación cancelada.")
                return None
            
            if 1 <= choice_num <= len(dumps):
                return dumps[choice_num - 1][0]  # Return filename
            
            print("✗ Opción inválida.")
            return None
            
        except KeyboardInterrupt:
            print("\n\n✗ Operación cancelada por el usuario.")
            return None
        except Exception as e:
            print(f"\n✗ Error: {e}")
            return None
    
    def download_file_scp(self, key_path: str, ssh_user: str, 
                          dns: str, remote_file: str, local_file: str) -> bool:
        """Download file using SCP"""
        print("\nDescargando SQL dump...")
        
        try:
            result = subprocess.run(
                ['scp', '-i', key_path,
                 '-o', 'StrictHostKeyChecking=no',
                 '-o', 'UserKnownHostsFile=/dev/null',
                 f'{ssh_user}@{dns}:~/{remote_file}',
                 local_file],
                timeout=1800  # 30 minutes timeout for large files
            )
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout al descargar archivo (>30 minutos).")
            return False
        except Exception as e:
            print(f"✗ Error al descargar archivo: {e}")
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

    @staticmethod
    def normalize_environment_name(env_name: str) -> str:
        """Normalize environment name to a filesystem-safe prefix."""
        normalized = env_name.strip().lower().replace(' ', '_')
        normalized = re.sub(r'[^a-z0-9_-]', '', normalized)
        return normalized or 'entorno'
    
    def download_dump(self, environment: dict) -> bool:
        """Download SQL dump from environment"""
        env_name = environment.get('name', '')
        env_id = environment.get('id', '')
        print(f"\n=== Descargando SQL Dump de {env_name} ===")
        
        key_path = self.config.get_key_path()
        ssh_user = self.config.get_ssh_user()
        
        # Get DNS
        instance_id = environment.get('instance_id', '')
        static_dns = environment.get('dns', '')
        dns = self.ec2.get_instance_dns(instance_id, static_dns)
        
        if not dns:
            print("✗ Error al obtener DNS.")
            return False
        
        # Get list of available dumps
        print("\nObteniendo lista de dumps disponibles...")
        dumps = self.get_remote_dumps_list(key_path, ssh_user, dns)
        
        # Let user select from list
        dump_filename = self.select_dump_from_list(dumps)
        
        if not dump_filename:
            return False
        
        dump_dir = self.config.get_dump_directory()

        env_prefix = self.normalize_environment_name(env_id)
        local_filename = f"{env_prefix}_{dump_filename}"
        local_file_path = dump_dir / local_filename
        
        print(f"\nArchivo remoto: ~/{dump_filename}")
        print(f"Archivo local:  {local_file_path}")
        
        # Download file
        if not self.download_file_scp(key_path, ssh_user, dns, dump_filename, str(local_file_path)):
            print("✗ Error al descargar archivo.")
            return False
        
        # Show success and file size
        print(f"✓ SQL dump descargado exitosamente: {local_file_path}")
        
        size_mb = self.get_file_size_mb(str(local_file_path))
        if size_mb:
            print(f"Tamaño del archivo: {size_mb} MB")
        
        # Log the operation
        self.logger.log_dump_download(
            dump_name=local_filename,
            environment=env_id,
            file_size_mb=size_mb
        )
        
        return True

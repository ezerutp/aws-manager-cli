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
                timeout=300  # 5 minutes timeout for large files
            )
            
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout al descargar archivo (>5 minutos).")
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
        
        # Get DNS
        instance_id = environment.get('instance_id', '')
        static_dns = environment.get('dns', '')
        dns = self.ec2.get_instance_dns(instance_id, static_dns)
        
        if not dns:
            print("✗ Error al obtener DNS.")
            return False
        
        # Generate suggested filename
        # Use environment ID for more specific naming
        date_str = datetime.now().strftime('%Y-%m-%d')
        suggested_filename = f"dump_{date_str}.sql.gz"
        
        # Ask user for filename
        print(f"\nNombre del archivo en servidor [{suggested_filename}]: ", end='')
        user_input = input().strip()
        dump_filename = user_input if user_input else suggested_filename

        dump_dir = self.config.get_dump_directory()

        env_prefix = self.normalize_environment_name(env_id)
        local_filename = f"{env_prefix}_{dump_filename}"
        local_file_path = dump_dir / local_filename
        
        print(f"\nArchivo remoto: ~/{dump_filename}")
        print(f"Archivo local:  {local_file_path}")
        
        ssh_user = self.config.get_ssh_user()
        
        # Check if file exists on remote
        if not self.check_remote_file_exists(key_path, ssh_user, dns, dump_filename):
            print(f"✗ Archivo no encontrado en servidor: ~/{dump_filename}")
            self.list_remote_dumps(key_path, ssh_user, dns)
            return False
        
        print("✓ Archivo encontrado. Descargando...")
        
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

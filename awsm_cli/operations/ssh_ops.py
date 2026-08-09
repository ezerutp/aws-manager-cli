"""SSH Operations Module"""
import os
import subprocess
from pathlib import Path
from typing import Optional


class SSHOperations:
    """Handles SSH connection operations"""
    
    def __init__(self, config_manager, ec2_manager, sg_manager):
        self.config = config_manager
        self.ec2 = ec2_manager
        self.sg = sg_manager
    
    def validate_ssh_key(self, key_path: str) -> bool:
        """Validate SSH key exists and has correct permissions"""
        path = Path(key_path)
        
        if not path.exists():
            print(f"✗ Error: La clave SSH no existe en: {key_path}")
            return False
        
        print("✓ Clave SSH encontrada.")
        
        # Check permissions (Unix only)
        try:
            stat_info = path.stat()
            mode = stat_info.st_mode & 0o777
            
            if mode not in [0o400, 0o600]:
                print("⚠ Permisos incorrectos en la clave.")
                print("  Intentando corregir a 600...")
                return self.fix_ssh_key_permissions(key_path)
            
            print("✓ Permisos de clave correctos.")
            return True
            
        except Exception as e:
            print(f"⚠ No se pudieron verificar permisos: {e}")
            return True  # Continue anyway on Windows or if check fails
    
    def fix_ssh_key_permissions(self, key_path: str) -> bool:
        """Fix SSH key permissions to 600"""
        try:
            os.chmod(key_path, 0o600)
            print("✓ Permisos corregidos.")
            return True
        except Exception as e:
            print(f"✗ Error al corregir permisos: {e}")
            print(f"  Intenta manualmente: chmod 600 {key_path}")
            return False
    
    def connect_ssh(self, environment: dict) -> bool:
        """Connect to EC2 instance via SSH"""
        env_name = environment.get('name', '')
        print(f"\n=== Conectando a {env_name} ===")
        
        key_path = self.config.get_key_path()
        
        # Validate SSH key
        if not self.validate_ssh_key(key_path):
            print("\n⚠ Diagnóstico SSH:")
            print(f"  1. Verifica que la ruta es correcta: {key_path}")
            print(f"  2. Asegúrate que los permisos son 600: chmod 600 {key_path}")
            print("  3. Verifica que la clave privada coincide con la pública en EC2")
            return False
        
        # Update Security Group (skip if not configured)
        sg_id = environment.get('security_group_id')
        if sg_id:
            if not self.sg.update_security_group(environment):
                print("✗ Error al actualizar Security Group.")
                return False
        else:
            print("\n⚠ Security Group ID no proporcionado - omitiendo actualización de reglas.")
            print("  Asegúrate de que tu IP está autorizada en el Security Group de la instancia.")
        
        # Get DNS
        instance_id = environment.get('instance_id', '')
        static_dns = environment.get('dns', '')
        dns = self.ec2.get_instance_dns(instance_id, static_dns)
        
        if not dns:
            print("✗ Error al obtener DNS.")
            return False
        
        # SSH configuration
        ssh_user = self.config.get_ssh_user()
        ssh_port = self.config.get_ssh_port()
        instance_name = environment.get('instance_name', instance_id)
        
        # Display connection details
        from ..ui.menu import MenuManager
        MenuManager.display_section_header("SSH Connection Details")
        print(f"\nEnvironment: {env_name}")
        print(f"Instance:    {instance_name}")
        print(f"Host:        {dns}")
        print(f"User:        {ssh_user}")
        print(f"Port:        {ssh_port}")
        
        # Build SSH command
        ssh_cmd = [
            'ssh',
            '-i', key_path,
            '-p', str(ssh_port),
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            f'{ssh_user}@{dns}'
        ]
        
        print("\nConectando...")
        
        try:
            # Execute SSH (interactive)
            result = subprocess.run(ssh_cmd)
            return result.returncode == 0
        except KeyboardInterrupt:
            print("\n\n✓ Conexión SSH interrumpida por el usuario.")
            return True
        except Exception as e:
            print(f"\n✗ Error al conectar SSH: {e}")
            return False

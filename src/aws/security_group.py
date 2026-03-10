"""Security Group Management Module"""
import subprocess
import json
import requests
from typing import Optional


class SecurityGroupManager:
    """Manages AWS Security Group operations"""
    
    def __init__(self, config_manager):
        self.config = config_manager
    
    def get_current_public_ip(self) -> Optional[str]:
        """Get current public IP address"""
        print("Obteniendo IP pública...")
        
        try:
            response = requests.get('https://checkip.amazonaws.com', timeout=10)
            if response.status_code == 200:
                ip = response.text.strip()
                print(f"Tu IP pública: {ip}")
                return ip
            else:
                print("✗ Error al obtener IP pública.")
                return None
        except requests.RequestException as e:
            print(f"✗ Error al obtener IP pública: {e}")
            return None
    
    def get_security_group_info(self, sg_id: str) -> Optional[dict]:
        """Get security group information"""
        try:
            result = subprocess.run(
                ['aws', 'ec2', 'describe-security-groups',
                 '--group-ids', sg_id,
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode != 0:
                print("✗ Error al obtener información del Security Group.")
                return None
            
            sg_data = json.loads(result.stdout)
            return sg_data
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout al obtener Security Group.")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Error al parsear respuesta: {e}")
            return None
        except Exception as e:
            print(f"✗ Error al obtener Security Group: {e}")
            return None
    
    def find_existing_rules(self, sg_data: dict, current_ip: str, rule_description: str) -> tuple:
        """Find existing SSH rules in security group
        
        Returns:
            tuple: (existing_rule_ip, ip_already_exists)
        """
        existing_rule_ip = None
        ip_already_exists = None
        
        try:
            security_groups = sg_data.get('SecurityGroups', [])
            if not security_groups:
                return existing_rule_ip, ip_already_exists
            
            ip_permissions = security_groups[0].get('IpPermissions', [])
            
            for perm in ip_permissions:
                if perm.get('ToPort') != 22:
                    continue
                
                ip_ranges = perm.get('IpRanges', [])
                for ip_range in ip_ranges:
                    cidr = ip_range.get('CidrIp', '')
                    desc = ip_range.get('Description', '')
                    
                    # Check if this is our rule
                    if desc == rule_description:
                        existing_rule_ip = cidr
                    
                    # Check if IP already authorized
                    if cidr == f"{current_ip}/32":
                        ip_already_exists = cidr
            
            return existing_rule_ip, ip_already_exists
            
        except Exception as e:
            print(f"✗ Error al analizar reglas: {e}")
            return None, None
    
    def revoke_security_group_rule(self, sg_id: str, cidr: str) -> bool:
        """Revoke an ingress rule from security group"""
        print(f"Action: Revocando regla antigua ({cidr})...")
        
        try:
            result = subprocess.run(
                ['aws', 'ec2', 'revoke-security-group-ingress',
                 '--group-id', sg_id,
                 '--protocol', 'tcp',
                 '--port', '22',
                 '--cidr', cidr],
                capture_output=True,
                timeout=15
            )
            
            if result.returncode == 0:
                print("✓ Regla revocada.")
                return True
            else:
                print("⚠ No se pudo revocar la regla.")
                return False
                
        except Exception as e:
            print(f"✗ Error al revocar regla: {e}")
            return False
    
    def authorize_security_group_rule(self, sg_id: str, ip: str, description: str) -> bool:
        """Authorize an ingress rule in security group"""
        print("Action: Autorizando nueva IP en SG...")
        
        try:
            ip_permissions = json.dumps([{
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{
                    "CidrIp": f"{ip}/32",
                    "Description": description
                }]
            }])
            
            result = subprocess.run(
                ['aws', 'ec2', 'authorize-security-group-ingress',
                 '--group-id', sg_id,
                 '--ip-permissions', ip_permissions],
                capture_output=True,
                timeout=15
            )
            
            if result.returncode == 0:
                print("✓ Security Group actualizado.")
                return True
            else:
                print("⚠ No se pudo autorizar (puede ser que ya lo esté).")
                return True  # Not a critical error
                
        except Exception as e:
            print(f"✗ Error al autorizar regla: {e}")
            return False
    
    def update_security_group(self, environment: dict) -> bool:
        """Update security group with current IP (idempotent)"""
        print("\n=== Actualizando Security Group ===")
        
        sg_id = environment.get('security_group_id')
        if not sg_id:
            print("✗ Error: Security Group ID no encontrado en configuración.")
            return False
        
        rule_description = self.config.get_rule_description()
        
        # Get current public IP
        current_ip = self.get_current_public_ip()
        if not current_ip:
            return False
        
        # Get security group info
        sg_data = self.get_security_group_info(sg_id)
        if not sg_data:
            return False
        
        # Find existing rules
        existing_rule_ip, ip_already_exists = self.find_existing_rules(
            sg_data, current_ip, rule_description
        )
        
        # Check if update is needed
        if existing_rule_ip == f"{current_ip}/32":
            print(f"Status: Regla de Security Group ya actualizada.")
            return True
        
        if ip_already_exists:
            print(f"Status: IP ya autorizada en el SG (vía otra regla).")
            return True
        
        # Revoke old rule if exists
        if existing_rule_ip:
            self.revoke_security_group_rule(sg_id, existing_rule_ip)
        
        # Authorize new IP
        return self.authorize_security_group_rule(sg_id, current_ip, rule_description)

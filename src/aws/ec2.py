"""EC2 Operations Module"""
import subprocess
import json
from typing import Optional, Dict


class EC2Manager:
    """Manages EC2 instance operations"""
    
    def __init__(self, config_manager):
        self.config = config_manager
    
    def get_instance_dns(self, instance_id: str, static_dns: str = "") -> Optional[str]:
        """Get public DNS of an EC2 instance"""
        # Use static DNS if provided
        if static_dns:
            print(f"Usando DNS estático: {static_dns}")
            return static_dns
        
        print("Obteniendo DNS dinámico...")
        
        try:
            result = subprocess.run(
                ['aws', 'ec2', 'describe-instances',
                 '--instance-ids', instance_id,
                 '--query', 'Reservations[0].Instances[0].PublicDnsName',
                 '--output', 'text'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode != 0:
                print("✗ Error al ejecutar comando AWS.")
                return None
            
            dns = result.stdout.strip()
            
            if not dns or dns == 'None':
                print("✗ Error: No se pudo obtener el DNS de la instancia.")
                print(f"  Verifica que la instancia está corriendo: {instance_id}")
                return None
            
            print(f"✓ DNS obtenido: {dns}")
            return dns
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout al obtener DNS de instancia.")
            return None
        except Exception as e:
            print(f"✗ Error al obtener DNS: {e}")
            return None
    
    def get_instance_details(self, instance_id: str) -> Optional[Dict]:
        """Get detailed information about an EC2 instance"""
        print(f"Obteniendo detalles de instancia {instance_id}...")
        
        try:
            result = subprocess.run(
                ['aws', 'ec2', 'describe-instances',
                 '--instance-ids', instance_id,
                 '--query', 'Reservations[0].Instances[0].{Dns:PublicDnsName,Name:Tags[?Key==`Name`].Value|[0]}',
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if result.returncode != 0:
                print("✗ Error al obtener detalles de instancia.")
                return None
            
            details = json.loads(result.stdout)
            return details
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout al obtener detalles de instancia.")
            return None
        except json.JSONDecodeError as e:
            print(f"✗ Error al parsear respuesta: {e}")
            return None
        except Exception as e:
            print(f"✗ Error al obtener detalles: {e}")
            return None

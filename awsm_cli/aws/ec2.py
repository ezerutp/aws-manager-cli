"""EC2 Operations Module"""
import subprocess
import json
from typing import Callable, Optional, Dict


class EC2Manager:
    """Manages EC2 instance operations"""

    def __init__(self, config_manager, on_output: Optional[Callable[[str], None]] = None):
        self.config = config_manager
        # Una GUI no tiene stdout que mostrar: recibe la salida por callback.
        self._out: Callable[[str], None] = on_output or print
    
    def get_instance_dns(self, instance_id: str, static_dns: str = "") -> Optional[str]:
        """Get public DNS of an EC2 instance"""
        # Use static DNS if provided
        if static_dns:
            self._out(f"Usando DNS estático: {static_dns}")
            return static_dns
        
        self._out("Obteniendo DNS dinámico...")
        
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
                self._out("✗ Error al ejecutar comando AWS.")
                return None
            
            dns = result.stdout.strip()
            
            if not dns or dns == 'None':
                self._out("✗ Error: No se pudo obtener el DNS de la instancia.")
                self._out(f"  Verifica que la instancia está corriendo: {instance_id}")
                return None
            
            self._out(f"✓ DNS obtenido: {dns}")
            return dns
            
        except subprocess.TimeoutExpired:
            self._out("✗ Timeout al obtener DNS de instancia.")
            return None
        except Exception as e:
            self._out(f"✗ Error al obtener DNS: {e}")
            return None
    
    def get_instance_details(self, instance_id: str) -> Optional[Dict]:
        """Get detailed information about an EC2 instance"""
        self._out(f"Obteniendo detalles de instancia {instance_id}...")
        
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
                self._out("✗ Error al obtener detalles de instancia.")
                return None
            
            details = json.loads(result.stdout)
            return details
            
        except subprocess.TimeoutExpired:
            self._out("✗ Timeout al obtener detalles de instancia.")
            return None
        except json.JSONDecodeError as e:
            self._out(f"✗ Error al parsear respuesta: {e}")
            return None
        except Exception as e:
            self._out(f"✗ Error al obtener detalles: {e}")
            return None

"""Configuration Manager - Loads and manages configuration from JSON files"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional


class ConfigManager:
    """Singleton class to manage configuration"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.config_data = {}
        self.environments_data = []
        self.loaded_config_path: Optional[Path] = None
        self.loaded_environments_path: Optional[Path] = None
        # No usamos _base_path, buscaremos en múltiples ubicaciones

    def _get_search_paths(self, filename: str) -> List[Path]:
        """Construye el orden de búsqueda para un archivo de configuración."""
        return [
            # 1. Directorio de configuración de usuario
            Path.home() / ".config" / "aws-manager" / filename,
            # 2. Directorio del ejecutable/script
            Path(sys.executable if getattr(sys, 'frozen', False) else __file__).parent.parent.parent / filename,
            # 3. Directorio de trabajo actual
            Path.cwd() / filename,
        ]
    
    def _find_config_file(self, filename: str) -> Optional[Path]:
        """Busca un archivo de configuración en múltiples ubicaciones"""
        search_paths = self._get_search_paths(filename)
        
        for path in search_paths:
            if path.exists():
                return path
        
        return None

    def get_search_paths(self, filename: str) -> List[Path]:
        """Devuelve las rutas que se revisan para encontrar un archivo de configuración."""
        return self._get_search_paths(filename)

    def find_config_file(self, filename: str) -> Optional[Path]:
        """Devuelve la ruta resuelta para un archivo de configuración si existe."""
        return self._find_config_file(filename)
    
    def load_config(self, config_path: Optional[str] = None) -> bool:
        """Load main configuration from config.json"""
        if config_path is None:
            config_path = self._find_config_file("config.json")
            if config_path is None:
                print("✗ Error: No se encontró config.json en:")
                print("   - ~/.config/aws-manager/config.json")
                print("   - Directorio del ejecutable")
                print("   - Directorio actual")
                return False
        else:
            config_path = Path(config_path)
        
        try:
            if not config_path.exists():
                print(f"✗ Error: No se encontró el archivo de configuración: {config_path}")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            self.loaded_config_path = Path(config_path)
            
            print(f"✓ Configuración cargada desde: {config_path}")
            return True
        except json.JSONDecodeError as e:
            print(f"✗ Error al parsear JSON: {e}")
            return False
        except Exception as e:
            print(f"✗ Error al cargar configuración: {e}")
            return False
    
    def load_environments(self, env_path: Optional[str] = None) -> bool:
        """Load environment configuration from config-environment.json"""
        if env_path is None:
            env_path = self._find_config_file("config-environment.json")
            if env_path is None:
                print("✗ Error: No se encontró config-environment.json en:")
                print("   - ~/.config/aws-manager/config-environment.json")
                print("   - Directorio del ejecutable")
                print("   - Directorio actual")
                return False
        else:
            env_path = Path(env_path)
        
        try:
            if not env_path.exists():
                print(f"✗ Error: No se encontró el archivo de entornos: {env_path}")
                return False
            
            with open(env_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.environments_data = data.get('environments', [])
            self.loaded_environments_path = Path(env_path)
            
            print(f"✓ Configuración de entornos cargada: {len(self.environments_data)} entornos disponibles")
            return True
        except json.JSONDecodeError as e:
            print(f"✗ Error al parsear JSON de entornos: {e}")
            return False
        except Exception as e:
            print(f"✗ Error al cargar entornos: {e}")
            return False
    
    # === Credentials ===
    
    def get_access_key(self) -> str:
        return self.config_data.get('credentials', {}).get('access_key', '')
    
    def get_secret_key(self) -> str:
        return self.config_data.get('credentials', {}).get('secret_key', '')
    
    def get_region(self) -> str:
        return self.config_data.get('credentials', {}).get('region', 'us-east-1')
    
    def get_key_path(self) -> str:
        return self.config_data.get('credentials', {}).get('key_path', '')
    
    def get_rule_description(self) -> str:
        return self.config_data.get('credentials', {}).get('rule_description', '')
    
    # === MySQL ===
    
    def get_mysql_user(self) -> str:
        return self.config_data.get('mysql', {}).get('user', 'root')
    
    def get_mysql_host(self) -> str:
        return self.config_data.get('mysql', {}).get('host', '127.0.0.1')
    
    def get_mysql_protocol(self) -> str:
        return self.config_data.get('mysql', {}).get('protocol', 'tcp')
    
    def get_database_name(self, db_key: str) -> str:
        return self.config_data.get('mysql', {}).get('databases', {}).get(db_key, db_key)
    
    def get_all_databases(self) -> Dict[str, str]:
        """Get all configured databases"""
        return self.config_data.get('mysql', {}).get('databases', {})
    
    # === SSH ===
    
    def get_ssh_user(self) -> str:
        return self.config_data.get('ssh', {}).get('user', 'ubuntu')
    
    def get_ssh_port(self) -> int:
        return self.config_data.get('ssh', {}).get('port', 22)
    
    def get_ssh_strict_host_key_checking(self) -> bool:
        return self.config_data.get('ssh', {}).get('strict_host_key_checking', False)
    
    def get_ssh_connect_timeout(self) -> int:
        return self.config_data.get('ssh', {}).get('connect_timeout', 10)
    
    # === MFA ===
    
    def is_mfa_required(self) -> bool:
        return self.config_data.get('mfa', {}).get('required', True)
    
    # === Environments ===
    
    def get_all_environments(self) -> List[Dict]:
        """Get all configured environments"""
        return self.environments_data
    
    def get_environment_by_id(self, env_id: str) -> Optional[Dict]:
        """Get specific environment by ID"""
        for env in self.environments_data:
            if env.get('id') == env_id:
                return env
        return None
    
    def get_environment_by_index(self, index: int) -> Optional[Dict]:
        """Get environment by index (0-based)"""
        if 0 <= index < len(self.environments_data):
            return self.environments_data[index]
        return None

"""Configuration Manager - Loads and manages configuration from JSON files"""
import json
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional


class ConfigManager:
    """Singleton class to manage configuration"""

    _instance = None

    def __new__(cls, on_output: Optional[Callable[[str], None]] = None):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, on_output: Optional[Callable[[str], None]] = None):
        if self._initialized:
            # El singleton ya existe: solo se actualiza a dónde va la salida, para
            # que una GUI pueda adoptar la instancia que creó el CLI.
            if on_output is not None:
                self._out = on_output
            return

        self._initialized = True
        self._out: Callable[[str], None] = on_output or print
        self.config_data = {}
        self.environments_data = []
        self.loaded_config_path: Optional[Path] = None
        self.loaded_environments_path: Optional[Path] = None
        self._dump_directory: Optional[Path] = None
        # No usamos _base_path, buscaremos en múltiples ubicaciones

    @classmethod
    def reset(cls) -> None:
        """Olvida el singleton, para que el próximo ConfigManager() relea todo.

        La config se cachea entera (incluido _dump_directory), así que editarla en
        disco no se nota hasta que la instancia se descarta.
        """
        cls._instance = None

    def reload(self) -> bool:
        """Vuelve a leer los dos archivos de configuración desde disco."""
        self._dump_directory = None
        self.config_data = {}
        self.environments_data = []
        return self.load_config() and self.load_environments()

    # === Escritura ===

    USER_CONFIG_DIR = Path.home() / ".config" / "aws-manager"

    def config_write_path(self) -> Path:
        """Dónde se guarda config.json: donde se cargó, o el directorio de usuario."""
        return self.loaded_config_path or (self.USER_CONFIG_DIR / "config.json")

    def environments_write_path(self) -> Path:
        return self.loaded_environments_path or (
            self.USER_CONFIG_DIR / "config-environment.json"
        )

    def save_config(self, data: Optional[Dict] = None) -> bool:
        """Guarda config.json. Escribe sobre el archivo que se cargó."""
        if data is not None:
            self.config_data = data
        path = self.config_write_path()
        if not self._write_json(path, self.config_data):
            return False
        self.loaded_config_path = path
        # El directorio de dumps se cachea al resolverlo: si cambió, hay que soltarlo.
        self._dump_directory = None
        self._out(f"✓ Configuración guardada en: {path}")
        return True

    def save_environments(self, environments: Optional[List[Dict]] = None) -> bool:
        """Guarda config-environment.json."""
        if environments is not None:
            self.environments_data = environments
        path = self.environments_write_path()
        if not self._write_json(path, {"environments": self.environments_data}):
            return False
        self.loaded_environments_path = path
        self._out(f"✓ Entornos guardados en: {path}")
        return True

    def _write_json(self, path: Path, payload) -> bool:
        """Escritura atómica y con permisos privados.

        La configuración puede tener claves de AWS, así que el archivo no debería
        ser legible por el resto del sistema. Y un archivo a medias es peor que
        uno viejo: se escribe a un temporal y se reemplaza de una.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + '.tmp')
            with open(temporary, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.chmod(temporary, 0o600)
            temporary.replace(path)
            return True
        except OSError as e:
            self._out(f"✗ No se pudo guardar {path}: {e}")
            return False

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
                self._out("✗ Error: No se encontró config.json en:")
                self._out("   - ~/.config/aws-manager/config.json")
                self._out("   - Directorio del ejecutable")
                self._out("   - Directorio actual")
                return False
        else:
            config_path = Path(config_path)
        
        try:
            if not config_path.exists():
                self._out(f"✗ Error: No se encontró el archivo de configuración: {config_path}")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
            self.loaded_config_path = Path(config_path)
            
            self._out(f"✓ Configuración cargada desde: {config_path}")
            return True
        except json.JSONDecodeError as e:
            self._out(f"✗ Error al parsear JSON: {e}")
            return False
        except Exception as e:
            self._out(f"✗ Error al cargar configuración: {e}")
            return False
    
    def load_environments(self, env_path: Optional[str] = None) -> bool:
        """Load environment configuration from config-environment.json"""
        if env_path is None:
            env_path = self._find_config_file("config-environment.json")
            if env_path is None:
                self._out("✗ Error: No se encontró config-environment.json en:")
                self._out("   - ~/.config/aws-manager/config-environment.json")
                self._out("   - Directorio del ejecutable")
                self._out("   - Directorio actual")
                return False
        else:
            env_path = Path(env_path)
        
        try:
            if not env_path.exists():
                self._out(f"✗ Error: No se encontró el archivo de entornos: {env_path}")
                return False
            
            with open(env_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.environments_data = data.get('environments', [])
            self.loaded_environments_path = Path(env_path)
            
            self._out(f"✓ Configuración de entornos cargada: {len(self.environments_data)} entornos disponibles")
            return True
        except json.JSONDecodeError as e:
            self._out(f"✗ Error al parsear JSON de entornos: {e}")
            return False
        except Exception as e:
            self._out(f"✗ Error al cargar entornos: {e}")
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

    def get_key_path_for(self, environment: Optional[Dict]) -> str:
        """La llave de un entorno: la propia si la tiene, si no la general.

        Un `key_path` vacío o ausente en el entorno significa "usar la general",
        que es lo que hacían todos los entornos antes de que esto existiera.
        """
        specific = str((environment or {}).get('key_path', '') or '').strip()
        return specific or self.get_key_path()

    def uses_own_key(self, environment: Optional[Dict]) -> bool:
        return bool(str((environment or {}).get('key_path', '') or '').strip())
    
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
        """Get all configured parent environments"""
        return self.environments_data
    
    def get_environment_by_id(self, env_id: str) -> Optional[Dict]:
        """Get specific parent environment by ID"""
        for env in self.environments_data:
            if env.get('id') == env_id:
                return env
        return None
    
    def get_environment_by_index(self, index: int) -> Optional[Dict]:
        """Get parent environment by index (0-based)"""
        if 0 <= index < len(self.environments_data):
            return self.environments_data[index]
        return None
    
    def get_environment_types(self, parent_env_id: str) -> List[Dict]:
        """Get all types (PROD, QA, etc.) for a parent environment"""
        parent_env = self.get_environment_by_id(parent_env_id)
        if parent_env:
            return parent_env.get('types', [])
        return []
    
    def get_environment_type_by_id(self, parent_env_id: str, type_id: str) -> Optional[Dict]:
        """Get specific environment type by ID"""
        types = self.get_environment_types(parent_env_id)
        for env_type in types:
            if env_type.get('id') == type_id:
                return env_type
        return None
    
    def find_environment_by_type_id(self, type_id: str) -> Optional[Dict]:
        """Find environment type across all parent environments by its ID.
        
        Searches through all parent environments and their types to find
        a match for type_id (e.g., 'projectx_prod', 'projectx_qa').
        
        Args:
            type_id: The ID of the environment type to find
            
        Returns:
            Environment type dict if found, None otherwise
        """
        for parent_env in self.environments_data:
            types = parent_env.get('types', [])
            for env_type in types:
                if env_type.get('id') == type_id:
                    # Add parent name for context
                    env_type_copy = env_type.copy()
                    env_type_copy['_parent_name'] = parent_env.get('name', '')
                    return env_type_copy
        return None
    
    # === Paths ===
    
    def get_dump_directory(self) -> Path:
        """Get the dump directory path, creating it if needed.
        
        Returns the configured dump directory path. If not configured or empty,
        defaults to '~/db_dump' in the user's home directory.
        """
        if self._dump_directory is not None:
            return self._dump_directory
        
        # Get configured path, use ~/db_dump as default if empty or not set
        dump_path_str = self.config_data.get('paths', {}).get('dump_directory', '').strip()
        
        if not dump_path_str:
            # Default to ~/db_dump if empty or not configured
            dump_path = Path.home() / 'db_dump'
        else:
            dump_path = Path(dump_path_str).expanduser()
            
            # If relative path, make it relative to config file location
            if not dump_path.is_absolute():
                if self.loaded_config_path:
                    # Relative to config file directory
                    dump_path = (self.loaded_config_path.parent / dump_path).resolve()
                else:
                    # Fallback to user's home directory
                    dump_path = Path.home() / dump_path
        
        # Create directory if it doesn't exist
        dump_path.mkdir(parents=True, exist_ok=True)
        
        # Cache the resolved path
        self._dump_directory = dump_path
        return self._dump_directory

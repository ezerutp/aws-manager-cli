"""MFA Authentication Module"""
import os
import json
import subprocess
from datetime import datetime, timezone
from typing import Callable, Optional, Dict


class AWSCredentials:
    """Container for AWS credentials with session token"""

    def __init__(self, access_key: str = "", secret_key: str = "", session_token: str = "",
                 expiration: str = ""):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
        # `aws sts get-session-token` devuelve cuándo caduca la sesión. El menú lo
        # ignoraba; una GUI puede mostrar cuánto falta.
        self.expiration = expiration

    def is_valid(self) -> bool:
        """Check if credentials are valid (not empty)"""
        return bool(self.access_key and self.secret_key)

    def expires_at(self) -> Optional[datetime]:
        """Parse the ISO-8601 expiration reported by STS, if there is one."""
        if not self.expiration:
            return None
        try:
            return datetime.fromisoformat(self.expiration.replace('Z', '+00:00'))
        except ValueError:
            return None

    def seconds_left(self) -> Optional[float]:
        """Seconds until the session expires, or None if it is unknown."""
        moment = self.expires_at()
        if moment is None:
            return None
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return (moment - datetime.now(timezone.utc)).total_seconds()

    def is_expired(self) -> bool:
        left = self.seconds_left()
        return left is not None and left <= 0


    def apply_to_environment(self):
        """Apply credentials to environment variables"""
        os.environ['AWS_ACCESS_KEY_ID'] = self.access_key
        os.environ['AWS_SECRET_ACCESS_KEY'] = self.secret_key
        if self.session_token:
            os.environ['AWS_SESSION_TOKEN'] = self.session_token
    
    @staticmethod
    def clear_session_token():
        """Clear session token from environment"""
        if 'AWS_SESSION_TOKEN' in os.environ:
            del os.environ['AWS_SESSION_TOKEN']


class MFAAuthenticator:
    """Handles MFA authentication for AWS"""
    
    def __init__(self, config_manager, on_output: Optional[Callable[[str], None]] = None):
        self.config = config_manager
        self._out: Callable[[str], None] = on_output or print
        self.credentials: Optional[AWSCredentials] = None
    
    def setup_aws_credentials(self) -> bool:
        """Setup AWS credentials from environment or config"""
        # Check environment variables first
        aws_key = os.environ.get('AWS_ACCESS_KEY_ID')
        aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY')
        
        if aws_key and aws_secret:
            self._out("✓ Credenciales AWS obtenidas de variables de entorno.")
            if not os.environ.get('AWS_DEFAULT_REGION'):
                os.environ['AWS_DEFAULT_REGION'] = self.config.get_region()
            return True
        
        # Try config file
        config_key = self.config.get_access_key()
        config_secret = self.config.get_secret_key()
        
        if config_key and config_secret:
            os.environ['AWS_ACCESS_KEY_ID'] = config_key
            os.environ['AWS_SECRET_ACCESS_KEY'] = config_secret
            os.environ['AWS_DEFAULT_REGION'] = self.config.get_region()
            self._out("✓ Credenciales AWS cargadas desde configuración.")
            return True
        
        # Try AWS CLI configured credentials
        self._out("Credenciales AWS no encontradas en variables de entorno o configuración.")
        self._out("Intentando usar credenciales configuradas en AWS CLI...")
        
        try:
            result = subprocess.run(
                ['aws', 'sts', 'get-caller-identity'],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                self._out("✓ Credenciales AWS detectadas en CLI.")
                return True
        except Exception as e:
            pass
        
        self._out("✗ Error: No se encontraron credenciales AWS.")
        self._out("  Configure las variables de entorno:")
        self._out("    export AWS_ACCESS_KEY_ID='your-access-key'")
        self._out("    export AWS_SECRET_ACCESS_KEY='your-secret-key'")
        return False
    
    def get_mfa_device(self) -> Optional[str]:
        """Discover MFA device ARN"""
        self._out("Identificando dispositivo MFA...")
        
        try:
            result = subprocess.run(
                ['aws', 'iam', 'list-mfa-devices', '--query', 
                 'MFADevices[0].SerialNumber', '--output', 'text'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                self._out("✗ Error al obtener dispositivo MFA.")
                return None
            
            device_arn = result.stdout.strip()
            
            if not device_arn or device_arn == 'None':
                self._out("✗ Error: No se encontró dispositivo MFA.")
                return None
            
            self._out(f"✓ Dispositivo MFA encontrado: {device_arn}")
            return device_arn
            
        except subprocess.TimeoutExpired:
            self._out("✗ Timeout al obtener dispositivo MFA.")
            return None
        except Exception as e:
            self._out(f"✗ Error al obtener dispositivo MFA: {e}")
            return None
    
    def authenticate_with_mfa(self, mfa_code: Optional[str] = None) -> AWSCredentials:
        """Perform MFA authentication and return temporary credentials.

        Con `mfa_code` no se lee nada de stdin, que es lo que permite usar esto
        desde una GUI. Sin él se mantiene el prompt interactivo del menú.
        """
        credentials = AWSCredentials()

        # Get MFA device
        mfa_device = self.get_mfa_device()
        if not mfa_device:
            return credentials

        if mfa_code is None:
            # Display MFA prompt
            from ..ui.menu import MenuManager
            MenuManager.display_section_header("MFA Authentication Required")

            # Request MFA code
            mfa_code = input("\nIngresa tu código MFA de 6 dígitos: ").strip()
        else:
            mfa_code = mfa_code.strip()

        # Validate input
        if len(mfa_code) != 6 or not mfa_code.isdigit():
            self._out("✗ Error: El código MFA debe ser 6 dígitos.")
            return credentials
        
        self._out("\nAutenticando con MFA...")
        
        try:
            # Get session token
            result = subprocess.run(
                ['aws', 'sts', 'get-session-token',
                 '--serial-number', mfa_device,
                 '--token-code', mfa_code,
                 '--output', 'json'],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self._out("✗ Error: Autenticación MFA fallida. Verifica el código.")
                return credentials
            
            # Parse response
            response = json.loads(result.stdout)
            credentials.access_key = response['Credentials']['AccessKeyId']
            credentials.secret_key = response['Credentials']['SecretAccessKey']
            credentials.session_token = response['Credentials']['SessionToken']
            credentials.expiration = str(response['Credentials'].get('Expiration', ''))

            self._out("✓ Sesión MFA establecida.")
            return credentials
            
        except subprocess.TimeoutExpired:
            self._out("✗ Timeout durante autenticación MFA.")
            return credentials
        except json.JSONDecodeError as e:
            self._out(f"✗ Error al parsear respuesta MFA: {e}")
            return credentials
        except Exception as e:
            self._out(f"✗ Error durante autenticación MFA: {e}")
            return credentials
    
    def perform_authentication(self, mfa_code: Optional[str] = None) -> bool:
        """Main authentication flow"""
        # Setup basic credentials first
        if not self.setup_aws_credentials():
            return False

        # If MFA is not required, we're done
        if not self.config.is_mfa_required():
            self._out("MFA no requerido según configuración.")
            return True

        # Perform MFA authentication
        self._out("\n=== Autenticación MFA ===")
        self.credentials = self.authenticate_with_mfa(mfa_code)

        if not self.credentials.is_valid():
            self._out("✗ Error: Autenticación MFA fallida.")
            return False
        
        # Apply credentials to environment
        self.credentials.apply_to_environment()
        self._out("✓ MFA autenticado. Credenciales válidas para toda la sesión.")
        
        return True
    
    def cleanup(self):
        """Clean up session token"""
        AWSCredentials.clear_session_token()
        self._out("Token de sesión temporal eliminado.")

"""MFA Authentication Module"""
import os
import json
import subprocess
from typing import Optional, Dict


class AWSCredentials:
    """Container for AWS credentials with session token"""
    
    def __init__(self, access_key: str = "", secret_key: str = "", session_token: str = ""):
        self.access_key = access_key
        self.secret_key = secret_key
        self.session_token = session_token
    
    def is_valid(self) -> bool:
        """Check if credentials are valid (not empty)"""
        return bool(self.access_key and self.secret_key)
    
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
    
    def __init__(self, config_manager):
        self.config = config_manager
        self.credentials: Optional[AWSCredentials] = None
    
    def setup_aws_credentials(self) -> bool:
        """Setup AWS credentials from environment or config"""
        # Check environment variables first
        aws_key = os.environ.get('AWS_ACCESS_KEY_ID')
        aws_secret = os.environ.get('AWS_SECRET_ACCESS_KEY')
        
        if aws_key and aws_secret:
            print("✓ Credenciales AWS obtenidas de variables de entorno.")
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
            print("✓ Credenciales AWS cargadas desde configuración.")
            return True
        
        # Try AWS CLI configured credentials
        print("Credenciales AWS no encontradas en variables de entorno o configuración.")
        print("Intentando usar credenciales configuradas en AWS CLI...")
        
        try:
            result = subprocess.run(
                ['aws', 'sts', 'get-caller-identity'],
                capture_output=True,
                timeout=10
            )
            if result.returncode == 0:
                print("✓ Credenciales AWS detectadas en CLI.")
                return True
        except Exception as e:
            pass
        
        print("✗ Error: No se encontraron credenciales AWS.")
        print("  Configure las variables de entorno:")
        print("    export AWS_ACCESS_KEY_ID='your-access-key'")
        print("    export AWS_SECRET_ACCESS_KEY='your-secret-key'")
        return False
    
    def get_mfa_device(self) -> Optional[str]:
        """Discover MFA device ARN"""
        print("Identificando dispositivo MFA...")
        
        try:
            result = subprocess.run(
                ['aws', 'iam', 'list-mfa-devices', '--query', 
                 'MFADevices[0].SerialNumber', '--output', 'text'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                print("✗ Error al obtener dispositivo MFA.")
                return None
            
            device_arn = result.stdout.strip()
            
            if not device_arn or device_arn == 'None':
                print("✗ Error: No se encontró dispositivo MFA.")
                return None
            
            print(f"✓ Dispositivo MFA encontrado: {device_arn}")
            return device_arn
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout al obtener dispositivo MFA.")
            return None
        except Exception as e:
            print(f"✗ Error al obtener dispositivo MFA: {e}")
            return None
    
    def authenticate_with_mfa(self) -> AWSCredentials:
        """Perform MFA authentication and return temporary credentials"""
        credentials = AWSCredentials()
        
        # Get MFA device
        mfa_device = self.get_mfa_device()
        if not mfa_device:
            return credentials
        
        # Display MFA prompt
        print("\n╔════════════════════════════════╗")
        print("║   MFA Authentication Required  ║")
        print("╚════════════════════════════════╝")
        
        # Request MFA code
        mfa_code = input("\nIngresa tu código MFA de 6 dígitos: ").strip()
        
        # Validate input
        if len(mfa_code) != 6 or not mfa_code.isdigit():
            print("✗ Error: El código MFA debe ser 6 dígitos.")
            return credentials
        
        print("\nAutenticando con MFA...")
        
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
                print("✗ Error: Autenticación MFA fallida. Verifica el código.")
                return credentials
            
            # Parse response
            response = json.loads(result.stdout)
            credentials.access_key = response['Credentials']['AccessKeyId']
            credentials.secret_key = response['Credentials']['SecretAccessKey']
            credentials.session_token = response['Credentials']['SessionToken']
            
            print("✓ Sesión MFA establecida.")
            return credentials
            
        except subprocess.TimeoutExpired:
            print("✗ Timeout durante autenticación MFA.")
            return credentials
        except json.JSONDecodeError as e:
            print(f"✗ Error al parsear respuesta MFA: {e}")
            return credentials
        except Exception as e:
            print(f"✗ Error durante autenticación MFA: {e}")
            return credentials
    
    def perform_authentication(self) -> bool:
        """Main authentication flow"""
        # Setup basic credentials first
        if not self.setup_aws_credentials():
            return False
        
        # If MFA is not required, we're done
        if not self.config.is_mfa_required():
            print("MFA no requerido según configuración.")
            return True
        
        # Perform MFA authentication
        print("\n=== Autenticación MFA ===")
        self.credentials = self.authenticate_with_mfa()
        
        if not self.credentials.is_valid():
            print("✗ Error: Autenticación MFA fallida.")
            return False
        
        # Apply credentials to environment
        self.credentials.apply_to_environment()
        print("✓ MFA autenticado. Credenciales válidas para toda la sesión.")
        
        return True
    
    def cleanup(self):
        """Clean up session token"""
        AWSCredentials.clear_session_token()
        print("Token de sesión temporal eliminado.")

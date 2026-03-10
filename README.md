# AWS Manager CLI

Herramienta CLI para gestionar conexiones SSH, descargas de dumps SQL y recreación de bases de datos en entornos AWS.




## Características

- 🔐 **Autenticación MFA única** - Autentica una vez al inicio, las credenciales se reutilizan en toda la sesión
- 🌍 **Entornos dinámicos** - Configura múltiples entornos sin límites y sin hardcodear
- 🔧 **Modular** - Código organizado en módulos independientes y reutilizables
- 🐍 **Python** - Migrado de shell scripts y C++ a Python para mejor mantenibilidad
- 📝 **Configuración JSON** - Fácil de editar y mantener

## Estructura del proyecto

```
aws-manager-cli/
├── config.json                    # Credenciales AWS, MySQL, SSH, MFA
├── config-environment.json        # Entornos (dinámico, sin límites)
├── main.py                        # Punto de entrada
├── setup.sh                       # Script de configuración inicial
├── install.sh                     # Script de instalación de binario
├── build.sh                       # Script de construcción
├── requirements.txt               # Dependencias Python
├── aws-manager.spec               # Especificación PyInstaller para compilación
└── src/
    ├── config/
    │   └── config_manager.py     # Gestión de configuración
    ├── auth/
    │   └── mfa_auth.py           # Autenticación MFA
    ├── aws/
    │   ├── ec2.py                # Operaciones EC2
    │   └── security_group.py    # Gestión Security Groups
    ├── operations/
    │   ├── ssh_ops.py            # Conexiones SSH
    │   ├── dump_ops.py           # Descarga de dumps
    │   └── db_ops.py             # Recreación de BD
    └── ui/
        └── menu.py               # Menús dinámicos
```

## Requisitos del sistema

### Herramientas requeridas

1. **Python 3.8+**
2. **AWS CLI** - Para interactuar con AWS
3. **SSH/SCP** - Para conexiones y transferencias
4. **MySQL Client** - Solo para recreación de bases de datos (opcional)

### Instalación de dependencias

#### Ubuntu/Debian
```bash
sudo apt update
sudo apt install python3 python3-pip awscli openssh-client mysql-client
```

## Scripts de Automatización

El proyecto incluye tres scripts para facilitar la instalación y distribución:

### setup.sh - Preparación del entorno de desarrollo

Prepara el entorno Python para ejecutar el proyecto directamente desde el código fuente.

**Qué hace:**
- ✓ Verifica que Python 3 y pip3 estén instalados
- ✓ Instala dependencias Python desde `requirements.txt`
- ✓ Verifica herramientas del sistema (AWS CLI, SSH, MySQL)
- ✓ Crea archivos de configuración desde los ejemplos
- ✓ Hace ejecutable `main.py`

**Uso:**
```bash
./setup.sh
```

**Resultado:** Entorno listo para ejecutar con `./main.py` o `python3 main.py`

---

### build.sh - Compilación del binario standalone

Compila el proyecto Python en un ejecutable único que no requiere Python instalado.

**Qué hace:**
- ✓ Verifica PyInstaller y UPX estén instalados
- ✓ Limpia builds anteriores (`build/`, `dist/`)
- ✓ Compila con PyInstaller usando `aws-manager.spec`
- ✓ Genera binario optimizado en `dist/aws-manager`

**Uso:**
```bash
./build.sh
```

**Resultado:** Ejecutable standalone en `dist/aws-manager` que puede distribuirse sin Python

---

### install.sh - Instalación del binario en el sistema

Instala el binario compilado en el sistema para uso global.

**Qué hace:**
- ✓ Copia `dist/aws-manager` a `/usr/local/bin/` (requiere sudo)
- ✓ Crea directorio `~/.config/aws-manager/` para configuración
- ✓ Copia archivos de configuración al directorio del usuario
- ✓ Asigna permisos correctos (evita usar root como propietario)
- ✓ Verifica dependencias del sistema

**Uso:**
```bash
sudo ./install.sh
```

**Resultado:** Comando `aws-manager` disponible globalmente en el sistema

---

### Flujo completo de trabajo

**Para desarrollo:**
```bash
./setup.sh           # Una vez: preparar entorno
./main.py            # Ejecutar desde código fuente
```

**Para producción:**
```bash
./build.sh           # Compilar binario
sudo ./install.sh    # Instalar en el sistema
aws-manager          # Ejecutar desde cualquier lugar
```

## Configuración

### 1. Configurar credenciales AWS (config.json)

Edita `config.json` con tus credenciales:

```json
{
    "credentials": {
        "access_key": "",              // Opcional si usas AWS CLI configurado
        "secret_key": "",              // Opcional si usas AWS CLI configurado
        "region": "us-east-1",
        "rule_description": "Tu Nombre",
        "key_path": "/ruta/a/tu/llave.pem"
    },
    "mysql": {
        "user": "root",
        "host": "127.0.0.1",
        "protocol": "tcp",
        "databases": {
            "db_1": "db_1",
            "db_2": "db_2"
        }
    },
    "ssh": {
        "user": "ubuntu",
        "port": 22,
        "strict_host_key_checking": false,
        "connect_timeout": 10
    },
    "mfa": {
        "required": true
    }
}
```

### 2. Configurar entornos (config-environment.json)

Agrega tantos entornos como necesites:

```json
{
    "environments": [
        {
            "id": "example_one_qa",
            "name": "QA (Example One)",
            "app": "example_one",
            "env_type": "qa",
            "instance_id": "i-xxxxxxxxx",
            "security_group_id": "sg-xxxxxxxxx",
            "dns": "",                              // Vacío = DNS dinámico
            "instance_name": "Bastion-QA"
        },
        {
            "id": "example_one_prod",
            "name": "PROD (Example One)",
            "app": "example_one",
            "env_type": "prod",
            "instance_id": "i-xxxxxxxxx",
            "security_group_id": "sg-xxxxxxxxx",
            "dns": "ec2-xx-xx-xx-xx.compute-1.amazonaws.com",  // DNS estático
            "instance_name": "Bastion-PROD"
        }
    ]
}
```

### 3. Configurar AWS CLI (Alternativa)

Si no quieres poner las credenciales en `config.json`:

```bash
aws configure
```

O usar variables de entorno:

```bash
export AWS_ACCESS_KEY_ID='your-access-key'
export AWS_SECRET_ACCESS_KEY='your-secret-key'
export AWS_DEFAULT_REGION='us-east-1'
```

## Uso

### Ejecutar el Programa

```bash
python3 main.py
```

### Flujo de Uso

1. **Autenticación MFA** - Se solicita una sola vez al inicio
2. **Menú Principal** - Opciones dinámicas basadas en entornos configurados:
   - **Entorno X - SSH** - Conectarse vía SSH
   - **Entorno X - Descargar SQL Dump** - Descargar dump de base de datos
   - **Recrear Base de Datos (local)** - Importar dump a MySQL local
   - **Salir** - Cerrar el programa

## Licencia

Uso interno

## Autor

Ezer Vidarte

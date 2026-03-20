# AWS Manager CLI

**Versión 2.0.0 "Phoenix"** 🔥

Herramienta CLI para gestionar conexiones SSH, descargas de dumps SQL y recreación de bases de datos en entornos AWS.

## Características

- 🔐 **Autenticación MFA única** - Autentica una vez al inicio, las credenciales se reutilizan en toda la sesión
- 🌍 **Entornos dinámicos** - Configura múltiples entornos sin límites y sin hardcodear
- 🔧 **Modular** - Código organizado en módulos independientes y reutilizables
- 🐍 **Python** - Migrado de shell scripts y C++ a Python para mejor mantenibilidad
- 📝 **Configuración JSON** - Fácil de editar y mantener
- 📊 **Progreso de importación BD** - Muestra avance en tiempo real durante recreación local
- 🗜️ **Soporte `.sql.gz`** - Permite importar dumps comprimidos directamente
- 📁 **Gestión centralizada de dumps** - Carpeta configurable para almacenar todos los dumps SQL (por defecto `~/db_dump`)

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

# Directorio de dumps (creado automáticamente)
~/db_dump/                         # Ubicación predeterminada de dumps SQL
```

**Nota:** La carpeta `~/db_dump` se crea automáticamente al descargar el primer dump y es configurable en `config.json`.

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
    "access_key": "", // Opcional si usas AWS CLI configurado
    "secret_key": "", // Opcional si usas AWS CLI configurado
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
  },
  "paths": {
    "dump_directory": ""
  }
}
```

**Opciones de configuración:**

- **paths.dump_directory**: Directorio donde se guardarán los dumps SQL descargados. 
  - **Por defecto**: `~/db_dump` (en el directorio home del usuario) si está vacío o no se especifica
  - **Ruta absoluta**: se usa tal cual (ej: `/home/user/backups/dumps`)
  - **Ruta relativa**: se resuelve desde la ubicación del archivo `config.json` (ej: `./backups` → `~/.config/aws-manager/backups`)
  - **Tilde expansion**: soporta `~` para el home del usuario (ej: `~/backups/sql`)
  - El directorio se creará automáticamente si no existe
  - La carpeta se resuelve al iniciar la aplicación y se mantiene consistente sin importar desde dónde ejecutes el programa

**Ejemplos de configuración:**

```json
// Usar la ubicación predeterminada (~/db_dump)
"dump_directory": ""

// Carpeta personalizada en el home
"dump_directory": "~/backups/aws-dumps"

// Ruta absoluta en otro disco
"dump_directory": "/mnt/backups/sql-dumps"

// Ruta relativa al config.json
"dump_directory": "./dumps"
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
      "dns": "", // Vacío = DNS dinámico
      "instance_name": "Bastion-QA"
    },
    {
      "id": "example_one_prod",
      "name": "PROD (Example One)",
      "app": "example_one",
      "env_type": "prod",
      "instance_id": "i-xxxxxxxxx",
      "security_group_id": "sg-xxxxxxxxx",
      "dns": "ec2-xx-xx-xx-xx.compute-1.amazonaws.com", // DNS estático
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

### Opciones CLI

- `--local` / `-l`: Ejecuta en modo local (sin MFA), mostrando solo operaciones locales.
- `--config` / `-c`: Muestra qué archivos de configuración está usando la aplicación y pregunta si deseas abrir la carpeta contenedora.

### Flujo de Uso

1. **Autenticación MFA** - Se solicita una sola vez al inicio
2. **Menú Principal** - Opciones dinámicas basadas en entornos configurados:
   - **Entorno X - SSH** - Conectarse vía SSH
   - **Entorno X - Descargar SQL Dump** - Descargar dump de base de datos
   - **Recrear Base de Datos (local)** - Importar dump `.sql` o `.sql.gz` a MySQL local con progreso en pantalla
   - **Conectarse a BD local** - Abre una sesión interactiva de MySQL para ejecutar consultas manuales
   - **Ejecutar snippets** _(Coming Soon — actualmente deshabilitado)_
   - **Salir** - Cerrar el programa

### Descarga de SQL Dumps

#### Ubicación de archivos

Al descargar un dump, el archivo se guarda en el directorio configurado en `paths.dump_directory`. Si no se especifica, usa `~/db_dump` en el home del usuario. 

**Ventajas de la ubicación centralizada:**
- 📁 Todos los dumps en un solo lugar, fácil de encontrar
- 🔄 Consistente sin importar desde dónde ejecutes el programa
- 🗂️ Fácil de respaldar o sincronizar
- 🧹 Fácil de limpiar archivos antiguos

El directorio se crea automáticamente si no existe.

#### Nomenclatura de archivos

El nombre del archivo local lleva como prefijo el nombre del entorno normalizado, seguido del nombre del archivo remoto:

```
~/db_dump/qa_example_one_dump_qa_2026-03-17.sql.gz
          ──────────────────  ───────────────────────────────
          prefijo (entorno)   nombre del archivo en el servidor
```

Esto permite identificar fácilmente de qué entorno proviene cada dump cuando hay múltiples descargas.

#### Resolución de rutas

El directorio de dumps se resuelve de manera inteligente:

| Configuración | Resultado | Ejemplo |
|--------------|-----------|----------|
| Vacío o no especificado | `~/db_dump` | `/home/ezer/db_dump` |
| Ruta absoluta | Se usa tal cual | `/var/backups/dumps` → `/var/backups/dumps` |
| Con tilde `~` | Expande al home | `~/backups` → `/home/ezer/backups` |
| Ruta relativa | Relativa al config.json | `./dumps` → `~/.config/aws-manager/dumps` |

**Importante:** La ruta se resuelve al cargar la configuración, por lo que puedes ejecutar el programa desde cualquier directorio y los dumps siempre irán al mismo lugar.

### Recreación de Base de Datos Local

Al recrear una base de datos, el programa busca automáticamente archivos `.sql` y `.sql.gz` en:

1. **Primero**: En el directorio de dumps configurado (ej: `~/db_dump`)
2. **Después**: En el directorio actual (`.`)

Esto significa que tus dumps descargados aparecerán automáticamente en el menú de selección de archivos, sin necesidad de especificar rutas manualmente.

## Preguntas Frecuentes (FAQ)

### 💾 ¿Dónde se guardan mis dumps SQL?

Por defecto en `~/db_dump` (en tu directorio home). Puedes cambiar esto en `config.json`:

```json
"paths": {
    "dump_directory": "~/mis-backups"  // o cualquier otra ruta
}
```

## Licencia

Uso interno

## Autor

Ezer Vidarte

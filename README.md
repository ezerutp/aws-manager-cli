# AWS Manager

**Versión 2.1.0 "Phoenix"** 🔥

Herramienta para gestionar conexiones SSH, descargas de dumps SQL y recreación de
bases de datos en entornos AWS, con autenticación MFA y Security Groups.

Son dos piezas sobre el mismo núcleo y la misma configuración: **lo que hagas en
una lo ve la otra.** Cada una tiene su propio README.

| | Qué es | README |
| --- | --- | --- |
| **`awsm_cli`** | El núcleo y la CLI: MFA, EC2, Security Groups, SSH, dumps y base de datos local, con menú de terminal. Es el binario `aws-manager`, chico y sin Qt | [`awsm_cli/README.md`](awsm_cli/README.md) |
| **`aws_ui`** | La interfaz gráfica de escritorio (PySide6/Qt), opcional. Llama a los mismos módulos de `awsm_cli` | [`aws_ui/README.md`](aws_ui/README.md) |

La interfaz gráfica no es una reimplementación: los módulos del núcleo aceptan un
`on_output` opcional al que le mandan sus mensajes, así que la misma lógica sirve
para la terminal y para la ventana.

## Instalación rápida

```bash
# La CLI, desde el código fuente
./setup.sh
python3 -m awsm_cli

# La CLI, como binario
./build.sh
sudo ./install.sh          # o ./install-local.sh, sin sudo, en ~/.local/bin
aws-manager

# La interfaz gráfica (opcional, ~110 MB de Qt en su propio virtualenv)
./scripts/install_ui.sh
aws-manager-ui
```

El detalle de cada script está en el [README de la CLI](awsm_cli/README.md#scripts-de-automatización)
y en el [de la interfaz](aws_ui/README.md).

## Configuración

Dos archivos, compartidos por las dos piezas:

| Archivo | Qué tiene |
| --- | --- |
| `config.json` | Credenciales AWS, MySQL, SSH, MFA y rutas |
| `config-environment.json` | Los entornos y sus tipos (PROD, QA, …) |

Se buscan, en orden, en `~/.config/aws-manager/`, en el directorio del ejecutable
y en el directorio actual. `aws-manager --config` dice cuáles están en uso. El
formato completo está en el [README de la CLI](awsm_cli/README.md#configuración);
desde la interfaz gráfica se editan sin tocar JSON a mano.

## Pruebas

```bash
python3 -m unittest discover -s tests -t .
```

Las pruebas de la interfaz se saltan solas si PySide6 no está instalado.

## Estructura del proyecto

```
aws-manager-cli/
├── config.json                    # Credenciales AWS, MySQL, SSH, MFA
├── config-environment.json        # Entornos (dinámico, sin límites)
├── setup.sh                       # Script de configuración inicial
├── install.sh                     # Script de instalación de binario
├── build.sh                       # Script de construcción
├── requirements.txt               # Dependencias Python
├── pyproject.toml                 # Paquete, entry points y extra [ui]
├── aws-manager.spec               # Especificación PyInstaller (CLI, sin Qt)
│
├── awsm_cli/                      # ─── El CLI ───────────────────────
│   ├── main.py                    # Punto de entrada (bucle de menús)
│   ├── __main__.py                # `python3 -m awsm_cli`
│   ├── config/
│   │   ├── config_manager.py      # Gestión y guardado de configuración
│   │   ├── config_usage.py        # Inspección de config y entornos
│   │   └── bundle.py              # Exportar/importar configuración y llaves
│   ├── auth/
│   │   └── mfa_auth.py            # Autenticación MFA
│   ├── aws/
│   │   ├── ec2.py                 # Operaciones EC2
│   │   └── security_group.py      # Gestión Security Groups
│   ├── operations/
│   │   ├── ssh_ops.py             # Conexiones SSH
│   │   ├── dump_ops.py            # Descarga de dumps
│   │   ├── dump_index.py          # Índice: de qué entorno es cada dump
│   │   └── db_ops.py              # Recreación de BD
│   ├── cli/
│   │   └── args.py                # Parseo de argumentos
│   ├── ui/
│   │   └── menu.py                # Menús dinámicos de terminal
│   └── utils/
│       ├── logger.py              # Registro de operaciones
│       ├── secrets.py             # Enmascarar y verificar secretos
│       ├── shell_env.py           # Leer variables del shell de login
│       └── system_ops.py          # Helpers del sistema
│
├── aws_ui/                        # ─── La interfaz gráfica ──────────
│   ├── core.py                    # Puente a awsm_cli, sin Qt
│   ├── theme.py                   # Tokens de color y QSS
│   ├── widgets.py                 # Widgets propios
│   ├── icons.py                   # Iconos dibujados en runtime
│   ├── dialogs.py                 # MFA, dumps remotos, rutas en uso
│   ├── settings.py                # Ventana de configuración completa
│   ├── window.py                  # Ventana principal
│   └── app.py                     # Entry point
│
├── scripts/
│   ├── install_ui.sh              # Instalación de la UI en ~/.local (sin sudo)
│   └── render_ui.py               # Render offscreen de la UI a PNG, ambos temas
├── tests/                         # Pruebas (corren con y sin PySide6)
└── docs/
    ├── ui.md                      # Diseño e implementación de la UI
    └── ui-guia.md                 # Guía de la que salió la UI

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


## Documentación

| Documento | Qué cubre |
| --- | --- |
| [`awsm_cli/README.md`](awsm_cli/README.md) | La CLI: comandos, configuración, flujos, scripts de build e instalación |
| [`aws_ui/README.md`](aws_ui/README.md) | La interfaz gráfica: instalación, qué agrega, configuración desde la ventana |
| [`docs/ui.md`](docs/ui.md) | Diseño e implementación de la interfaz |
| [`docs/ui-guia.md`](docs/ui-guia.md) | La guía de la que salió la interfaz |

## Licencia

Uso interno

## Autor

Ezer Vidarte

# Guia para construir la interfaz grafica

> **Nota (documento historico).** Esta guia se escribio *antes* de construir la
> UI y se conserva como el razonamiento de partida. La UI ya existe: lo que se
> construyo, y donde se aparto de esta guia, esta en [`ui.md`](ui.md).
>
> Un cambio de nombres posterior: lo que aca se llama `src/` hoy es el paquete
> `awsm_cli/`, y `main.py` es `awsm_cli/main.py` (`python3 -m awsm_cli`).

Este documento existe para que una sesion futura pueda construir la UI de
`aws-manager` sin volver a investigar nada. Describe el stack, el sistema de
diseno y la arquitectura de la UI de **proxy-local** (`~/repos/proxy-local`,
paquete `redirect_ui/`), que es la referencia a replicar, y detalla **que hay
que hacer distinto** aca, porque los dos CLIs no se parecen tanto como parece.

Leelo entero antes de escribir codigo. La seccion mas importante es
[Adaptacion a aws-manager](#adaptacion-a-aws-manager): copiar la arquitectura de
proxy-local tal cual **no funciona** en este repo.

---

## 1. Stack y dependencias

| Que | Eleccion | Por que |
| --- | --- | --- |
| Toolkit | **PySide6** (Qt 6), extra opcional `PySide6-Essentials>=6.6` | Unico toolkit de Python con tray icon nativo y control total del estilo en el mismo proceso |
| Instalado y probado | PySide6 6.11.1, wheel `cp310-abi3`, Python 3.14 | El wheel `abi3` instala sin compilar en cualquier Python >= 3.10 |
| Assets | ninguno | Los iconos se dibujan en runtime con `QPainter` |
| Estilos | QSS (hoja de estilos de Qt) generada desde tokens | Un solo lugar para los colores, tema claro/oscuro sin duplicar reglas |

En proxy-local la UI es un **extra opcional** del mismo paquete, no una
dependencia del CLI:

```toml
[project.optional-dependencies]
ui = ["PySide6-Essentials>=6.6"]

[project.scripts]
redirect = "redirect.cli:main"
redirect-ui = "redirect_ui.app:main"
```

`PySide6-Essentials` pesa ~110 MB. Usar `-Essentials` y no `PySide6` completo:
el paquete completo agrega WebEngine, 3D y multimedia, que no se usan.

En este repo hoy no hay `pyproject.toml` (solo `requirements.txt` y un `.spec`
de PyInstaller). Ver [seccion 8](#8-empaquetado) para como encajar la UI.

---

## 2. Estructura de archivos

`redirect_ui/` son 10 modulos, ~2700 lineas. La separacion importa:

| Archivo | Lineas | Responsabilidad |
| --- | --- | --- |
| `core.py` | 350 | Puente al backend. **No importa Qt.** Es lo unico testeable sin GUI |
| `theme.py` | 497 | Tokens de color y la funcion que genera el QSS |
| `widgets.py` | 376 | Widgets propios: switch animado, dot de estado, pill, card, item de lista |
| `icons.py` | 103 | Iconos dibujados con `QPainter`, sin archivos binarios |
| `dialogs.py` | 373 | Formularios modales con validacion en vivo |
| `window.py` | 698 | La ventana principal: sidebar, detalle, log, acciones |
| `tray.py` | 79 | Icono de la barra de notificaciones y su menu |
| `app.py` | 225 | Entry point: tema, instancia unica, wiring, lanzador de escritorio |
| `__init__.py` / `__main__.py` | 14 | `python -m redirect_ui` |

**La regla que mas rinde:** `core.py` no importa Qt. Toda la logica de hablar
con el backend, leer estado y construir comandos vive ahi, y por eso 27 de las
29 pruebas de la UI corren sin PySide6 instalado.

---

## 3. Sistema de diseno

### Tokens

Una `dataclass` congelada con 17 campos, dos instancias (`DARK` y `LIGHT`):

```python
@dataclass(frozen=True, slots=True)
class Palette:
    name: str
    background: str      # fondo de la ventana
    surface: str         # sidebar y cards
    elevated: str        # hover, botones secundarios
    border: str
    border_strong: str
    text: str
    muted: str           # texto secundario
    faint: str           # texto terciario, placeholders
    accent: str
    accent_hover: str
    accent_text: str
    success: str         # proxy activo
    danger: str          # errores, eliminar
    warning: str         # modo unsafe
    track: str           # fondo del switch apagado
    shadow: str
```

Valores exactos, para copiar:

| Token | DARK | LIGHT |
| --- | --- | --- |
| `background` | `#13151a` | `#f5f6f8` |
| `surface` | `#191c23` | `#ffffff` |
| `elevated` | `#20242d` | `#ffffff` |
| `border` | `#2a2f3a` | `#e3e6eb` |
| `border_strong` | `#39404e` | `#cfd4dd` |
| `text` | `#e8ebf2` | `#181b21` |
| `muted` | `#949cac` | `#666e7d` |
| `faint` | `#6b7382` | `#8b93a1` |
| `accent` | `#6c8cff` | `#3b6ef6` |
| `accent_hover` | `#8099ff` | `#2c5be0` |
| `accent_text` | `#ffffff` | `#ffffff` |
| `success` | `#3fcf8e` | `#0f9d63` |
| `danger` | `#ff6b6b` | `#d94848` |
| `warning` | `#ffb84d` | `#b0730c` |
| `track` | `#333a47` | `#d7dbe2` |

Radios: `RADIUS = 12` para cards y contenedores, `RADIUS_SMALL = 8` para botones
e inputs.

### Tipografia

Listas de fallback, sin depender de que una fuente este instalada:

```python
UI_FONTS   = ["Inter", "Cantarell", "Noto Sans", "DejaVu Sans", "sans-serif"]
MONO_FONTS = ["JetBrains Mono", "Fira Code", "Source Code Pro", "DejaVu Sans Mono", "monospace"]
```

Tamano base 10 pt. La mono se usa para todo lo que sea un valor tecnico: rutas,
IDs de instancia, DNS, nombres de archivo. Eso solo ya hace que la app se vea
mas seria.

### La hoja de estilos

`stylesheet(palette)` devuelve un f-string gigante con el QSS. Se aplica entero
con `app.setStyleSheet(...)`. Los widgets se seleccionan por `objectName`:

```python
boton.setObjectName("Primary")   # -> QPushButton#Primary { background: accent }
label.setObjectName("FieldLabel")
```

Y las variantes por propiedad dinamica, que permite cambiar de estilo sin tocar
codigo de pintado:

```python
pill.setProperty("tone", "on")       # -> #Pill[tone="on"] { color: success }
pill.style().unpolish(pill)          # <-- imprescindible, si no, no repinta
pill.style().polish(pill)
```

`objectName`s que ya existen y conviene reusar: `Root`, `Sidebar`, `BrandName`,
`BrandSubtitle`, `SidebarSection`, `SidebarItem`, `SidebarItemTitle`,
`SidebarItemSubtitle`, `DetailTitle`, `DetailSubtitle`, `Card`, `CardTitle`,
`FieldLabel`, `FieldValue`, `FieldValueMuted`, `FieldHint`, `FieldError`,
`Separator`, `Pill`, `Primary`, `Danger`, `Ghost`, `IconButton`, `Chip`,
`LogView`, `Banner`, `BannerText`, `EmptyTitle`, `EmptyBody`, `FooterText`,
`DialogTitle`.

### Widgets propios

| Widget | Base | Detalle |
| --- | --- | --- |
| `ToggleSwitch` | `QAbstractButton` | Knob animado con `QPropertyAnimation`, 170 ms, `OutCubic`. Acepta `tone="success"` o `"warning"` |
| `StatusDot` | `QWidget` | Relleno con halo cuando esta activo, hueco cuando no |
| `Pill` | `QLabel` | Etiqueta chica de estado, con `tone` |
| `ElidingLabel` | `QLabel` | Elide por el medio en vez de estirar el layout. Tiene `selectable` |
| `Card` | `QFrame` | Superficie con borde y titulo en mayusculas |
| `SidebarItem` | `QFrame` | Fila de la lista: dot + titulo + subtitulo |
| `Banner` | `QFrame` | Franja de error descartable |
| `field_row()` | funcion | Fila `etiqueta  valor` con ancho de etiqueta fijo (104 px) |

**Dos trampas ya pagadas en proxy-local, no repetirlas:**

1. **`setChecked()` programatico pelea con la animacion.** Si el codigo hace
   `switch.setChecked(estado_real)` en cada refresco, la animacion arranca y el
   valor se pisa, dejando el knob a mitad de camino. Solucion: `setChecked()`
   salta directo al estado final y silencia la animacion; solo anima el click
   del usuario.

2. **Un label con texto seleccionable se come el click.** Si el subtitulo de una
   fila clickeable tiene `TextSelectableByMouse`, esa franja de la fila deja de
   responder. Solucion: `selectable=False` en los labels que viven dentro de algo
   clickeable, y ademas
   `child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)`
   en todos los hijos de la fila, para que sea un unico blanco de click.

### Iconos

Sin archivos binarios en el repo. `icons.py` dibuja con `QPainter` sobre un
canvas de 64x64 y escala:

```python
def tray_icon(palette, active) -> QIcon:   # relleno con degradado si hay algo activo,
                                           # hueco y gris si no
def app_icon(palette) -> QIcon
def icon_pixmap(palette, size) -> QPixmap  # para el PNG del lanzador
```

Un `QIcon` con varios tamanos (16, 22, 24, 32, 48, 64) para que el tray elija.
**Ojo:** `QIcon.pixmap(256, 256)` no escala hacia arriba; para el icono del
lanzador hay que renderizar directo al tamano pedido.

---

## 4. Arquitectura de la UI

```
app.py          instancia unica, tema del sistema, wiring
  |
  +-- window.py   MainWindow: sidebar + detalle + log
  |     |
  |     +-- core.py    Backend: habla con el CLI/libreria, sin Qt
  |     +-- dialogs.py formularios
  |
  +-- tray.py     icono de barra, refleja el estado
```

### Trabajo fuera del hilo de UI

Toda llamada que pueda bloquear va a un `QRunnable` en el `QThreadPool` global,
y vuelve por senales:

```python
class _Task(QRunnable):
    def __init__(self, work): ...
    def run(self):
        try:    self.signals.finished.emit(self.work() or "")
        except CoreError as e: self.signals.failed.emit(str(e))
        except Exception as e: self.signals.failed.emit(f"Error inesperado: {e}")
```

Mientras hay una tarea en vuelo, `self.busy = True` y los controles se
deshabilitan. **Nunca** tocar widgets desde el hilo de trabajo: solo emitir
senales.

### Refresco

`QTimer` de 1500 ms que compara un *fingerprint* barato (una tupla con los
campos que se renderizan) y solo reconstruye si cambio. Asi los cambios hechos
por fuera de la UI aparecen solos, sin parpadeo.

### Instancia unica

`QLocalServer` / `QLocalSocket` con un nombre por usuario:

```python
probe = QLocalSocket(); probe.connectToServer(f"redirect-ui-{os.getuid()}")
if probe.waitForConnected(300):   # ya hay una corriendo
    probe.write(b"show"); ...; return 0
```

La segunda invocacion le pide a la primera que muestre la ventana y termina.

### Tema del sistema

```python
def palette_for(app):
    return DARK if app.styleHints().colorScheme() == Qt.ColorScheme.Dark else LIGHT

app.styleHints().colorSchemeChanged.connect(on_scheme_changed)  # cambia en caliente
```

### Barra de notificaciones

`QSystemTrayIcon` + `QMenu` reconstruido en cada snapshot. El menu permite
operar sin abrir la ventana. Cerrar la ventana la esconde (`closeEvent` con
`event.ignore()`), no cierra la app.

**GNOME no tiene bandeja propia**: necesita la extension *AppIndicator and
KStatusNotifierItem Support*. Ya esta instalada en esta maquina. Si no
estuviera, `QSystemTrayIcon.isSystemTrayAvailable()` da `False` y hay que hacer
que el boton de cerrar cierre de verdad, para no dejar un proceso inalcanzable.

---

## 5. Adaptacion a aws-manager

Aca esta lo que **no** se puede copiar. Los dos CLIs son muy distintos:

| | proxy-local | aws-manager |
| --- | --- | --- |
| Forma del CLI | flags one-shot (`--set`, `--enable`) | **menu interactivo** que lee de `stdin` en loop |
| Estado en disco | `config.json` + `state.json` con PIDs | solo config; **no hay estado de runtime** |
| Duracion de las operaciones | < 5 s | SSH interactivo, `scp` hasta 30 min, import de MySQL de GB |
| Autenticacion | ninguna | **MFA**, codigo de 6 digitos, sesion en variables de entorno |
| Efectos remotos | ninguno | **modifica Security Groups de AWS** (revoke + authorize) |
| Salida | valores de retorno y stderr | `print()` a stdout en todos lados |

### Decision de arquitectura: importar, no subprocess

proxy-local maneja el CLI por `subprocess` porque **tiene un flag para cada
mutacion**. Aca no: `main.py` es un loop que dibuja menus y hace `input()`. No
se puede manejar por linea de comandos, y automatizar sus prompts escribiendo en
`stdin` seria fragilisimo.

**La UI tiene que importar `src/` como libreria, en proceso.** Es viable y es
lo correcto:

- Todo `src/` son clases sin estado global salvo el singleton `ConfigManager`.
- La unica dependencia externa es `requests`.
- `MenuManager` **no se usa**: la UI lo reemplaza entero. Las que se reusan son
  `ConfigManager`, `MFAAuthenticator`, `EC2Manager`, `SecurityGroupManager`,
  `SSHOperations`, `DumpOperations`, `DatabaseOperations`, `OperationsLogger`.

Igual conviene un `redirect_ui/core.py` equivalente — llamalo `aws_ui/core.py` —
que envuelva esas clases y **no importe Qt**, para poder testear sin GUI.

### Los seis problemas concretos, con solucion

**1. Todo el codigo hace `print()`.** La UI necesita esa salida en su panel de
log. Dos caminos:

- *Pragmatico:* envolver cada operacion con `contextlib.redirect_stdout` hacia
  un buffer que se vuelca al panel. **Trampa:** `redirect_stdout` cambia
  `sys.stdout` a nivel de proceso y **no es thread-safe**. Si las operaciones
  corren en un `QRunnable` y hay dos a la vez, se mezclan. Solucion: permitir
  una sola operacion en vuelo (que es lo que hace proxy-local con `self.busy`).
- *Limpio:* agregar a las clases de `src/` un callback opcional
  `on_output: Callable[[str], None]` que por defecto sea `print`. Es mas trabajo
  pero elimina la trampa. **Recomendado si se va a tocar `src/` igual.**

**2. MFA necesita un codigo de 6 digitos a mitad del flujo.**
`MFAAuthenticator.authenticate_with_mfa()` hace `input()` directo
(`src/auth/mfa_auth.py:133`). Hay que refactorizarlo para que reciba el codigo
como parametro: `authenticate_with_mfa(mfa_code: str)`. La UI pide el codigo con
un dialogo modal al arrancar, o cuando la sesion expira.

Ademas: **la sesion MFA no tiene expiracion registrada en ningun lado**. Las
credenciales van a `os.environ` y ahi quedan (`AWSCredentials.apply_to_environment`).
`aws sts get-session-token` da 12 h por defecto, pero el codigo no guarda el
`Expiration` que devuelve la respuesta. La UI deberia guardarlo y mostrar cuanto
falta — es justo el tipo de cosa que una GUI hace mejor que un menu.

**3. SSH es una sesion interactiva de terminal.** `SSHOperations.connect_ssh()`
hace `subprocess.run(['ssh', ...])` heredando la terminal. Una GUI no tiene
terminal. Opciones:

- **Lanzar el emulador de terminal del sistema** con el comando ssh armado.
  Es lo mas simple y lo que espera el usuario. En esta maquina (Fedora 44 +
  GNOME) el que hay instalado es **`ptyxis`**: `ptyxis -- ssh -i ... user@dns`.
  Hay que detectar cual existe, en orden: `ptyxis`, `kgx`, `gnome-terminal`,
  `konsole`, `x-terminal-emulator`, `xterm`; y avisar si no hay ninguno en vez
  de fallar en silencio. Ojo que la sintaxis del flag varia (`--` en ptyxis y
  gnome-terminal, `-e` en konsole y xterm).
- Embeber una terminal: `QTermWidget` no viene en PySide6-Essentials. Descartado.

Lo mismo aplica a `DatabaseOperations.connect_to_local_database()`, que abre un
`mysql` interactivo.

**Importante:** antes de lanzar la terminal hay que correr igual la
actualizacion del Security Group, que es la parte que si tiene sentido hacer
desde la UI (con feedback visual).

**4. Las operaciones largas necesitan progreso real.**
`DatabaseOperations.import_sql_file()` ya calcula porcentaje, MB y MB/s, pero
los imprime con `\r` (`src/operations/db_ops.py:161`). Refactorizar para que
acepte `on_progress: Callable[[float, float, float], None]` y que la UI lo
muestre en una `QProgressBar`.

El `scp` del dump (`DumpOperations.download_file_scp`) **no reporta progreso**:
deja que scp escriba en la terminal. Para la UI hay que capturar su salida
(`stdout=PIPE`, leer por lineas) y parsear el porcentaje, o usar `scp -v`. Es un
archivo que puede tardar 30 minutos: sin barra de progreso la UI parece colgada.

**5. Modificar Security Groups es una accion remota con efecto.**
`SecurityGroupManager.update_security_group()` **revoca** la regla vieja y
autoriza la nueva. Desde una GUI, donde es facil hacer click sin leer, conviene
mostrar antes que IP se va a autorizar y que regla se va a revocar, y pedir
confirmacion. Es el equivalente al dialogo de "origin ocupado" de proxy-local.

**6. `ConfigManager` es un singleton** (`__new__` con `_instance`). Funciona en
una GUI, pero recargar la config despues de editarla requiere cuidado: hay que
resetear `_instance` o agregar un metodo `reload()`. Ademas cachea
`_dump_directory`.

### Lo que si se copia tal cual

- El sistema de tokens y el QSS completo (`theme.py` casi sin cambios).
- Todos los widgets de `widgets.py`.
- El patron `QRunnable` + senales, el `QTimer` de refresco, la instancia unica,
  el seguimiento del tema del sistema, el tray.
- La estructura de modulos y la regla de que `core.py` no importa Qt.
- El script de instalacion (`scripts/install_ui.sh`), adaptando nombres.

---

## 6. Diseno de pantallas propuesto

El layout **sidebar + detalle** de proxy-local encaja bien, porque la jerarquia
de este CLI (entorno padre → tipo → acciones) es exactamente un arbol:

```
┌────────────────────┬──────────────────────────────────────────────┐
│ aws-manager     ⚙  │  Example One · PROD              ● conectado │
│ Phoenix v2.1.0     │  ──────────────────────────────────────────  │
│ ────────────────   │  CONEXION                                    │
│ MFA  ● 11:32 rest. │  instancia   i-0abc123  (Bastion-PROD)       │
│                    │  dns         ec2-xx-xx.compute-1.aws.com     │
│ ENTORNOS           │  security    sg-0def456                      │
│ ▾ Example One      │  tu IP       190.x.x.x   [autorizar]         │
│   ● PROD           │  ──────────────────────────────────────────  │
│   ○ QA             │  [ Abrir SSH ]  [ Descargar dump ]           │
│ ▸ Example Two      │                                              │
│                    │  LOG                          [seguir][abrir]│
│ ────────────────   │  ✓ DNS obtenido: ec2-xx-xx...                │
│ LOCAL              │  ✓ Security Group actualizado.               │
│ Recrear BD         │                                              │
│ Conectar a BD      │                                              │
│ Historial          │                                              │
│                    │                                              │
│ 4 entornos         │                                              │
└────────────────────┴──────────────────────────────────────────────┘
```

Pantallas / dialogos necesarios:

| Pantalla | Contenido |
| --- | --- |
| **MFA** (modal al arrancar) | 6 digitos, validacion en vivo, mensaje de error del CLI. Con opcion "modo local" que la saltea, como `--local` |
| **Detalle de entorno** | datos de conexion + acciones remotas |
| **Descargar dump** | lista de dumps remotos (`get_remote_dumps_list` ya devuelve nombre/tamano/fecha) + barra de progreso |
| **Recrear BD** | elegir base + elegir archivo `.sql`/`.sql.gz` + barra de progreso con MB/s |
| **Historial** | los logs de `OperationsLogger`, que ya son JSON por linea: se renderizan en tabla sin parsear texto |
| **Config** | que archivos se estan usando y donde (equivale a `--config`) |

Estado que la UI puede mostrar y el menu no:

- Cuanto le queda a la sesion MFA.
- Si tu IP publica actual ya esta autorizada en cada Security Group.
- Tamano y fecha de los dumps locales ya descargados.
- Progreso real de descarga e import.

---

## 7. Pruebas

proxy-local tiene 66 pruebas, de las cuales 29 son de la UI: 27 sobre `core.py`
sin Qt, y 2 de widgets que si lo necesitan. El patron:

```python
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    ...
    HAS_QT = True
except ImportError:
    HAS_QT = False

@unittest.skipUnless(HAS_QT, "PySide6 is needed for the widget tests")
class ...
```

Asi el suite corre igual sin el extra `[ui]` instalado.

Ademas, para revisar el diseno sin ver la pantalla, un script que renderiza la
ventana **offscreen** a PNG en ambos temas:

```python
os.environ["QT_QPA_PLATFORM"] = "offscreen"
window.grab().save("ventana-dark.png")
```

Vale mucho la pena: en proxy-local ese render encontro cuatro defectos visuales
antes de correr la app una sola vez.

---

## 8. Empaquetado

proxy-local instala la UI con `scripts/install_ui.sh`, todo bajo `~/.local` y
sin root:

1. corre las pruebas
2. crea un virtualenv propio en `~/.local/share/redirect-ui/venv`
3. instala el paquete con el extra `[ui]` (no en modo editable, para que la app
   no dependa del checkout)
4. escribe el comando `~/.local/bin/redirect-ui`
5. registra el `.desktop` con su icono y refresca las caches del escritorio
6. verifica que el comando arranque

Mas `--uninstall`, que borra las cuatro rutas y deja la config intacta.

### Para aws-manager

Este repo ya empaqueta con **PyInstaller** (`aws-manager.spec` + `build.sh` +
`install-local.sh`), no con Briefcase. Dos opciones:

- **Recomendado:** un `install_ui.sh` con virtualenv propio, como proxy-local.
  Es mas simple y no pelea con el `.spec` existente.
- Un segundo `.spec` de PyInstaller para la UI. Posible, pero empaquetar Qt con
  PyInstaller trae complicaciones (plugins de plataforma, `QT_QPA_PLATFORM_PLUGIN_PATH`)
  y el binario pasa de ~10 MB a ~150 MB.

Notar que el `.spec` actual **excluye `tkinter`** y varias libs; eso no afecta a
la UI de Qt, pero conviene no tocar ese spec: el binario del CLI debe seguir
siendo chico y sin Qt.

### El `.desktop`

Dos detalles que costaron tiempo en proxy-local:

```ini
[Desktop Entry]
Type=Application
Name=aws-manager
Exec=/home/USUARIO/.local/bin/aws-manager-ui
Icon=aws-manager-ui
Terminal=false
Categories=Development;
Keywords=aws;ec2;ssh;mysql;dump;
StartupNotify=true
StartupWMClass=aws-manager-ui
```

- **`StartupWMClass` tiene que coincidir con el app id que usa Qt**, que se
  deriva del nombre del archivo `.desktop` (sin `.desktop`). Si no coincide, el
  shell muestra la ventana como una app desconocida, separada de su icono.
- **Una sola categoria principal.** `Development;Network;` hace que la app
  aparezca dos veces en el menu; `desktop-file-validate` lo avisa.

Validar siempre con `desktop-file-validate` antes de dar por hecho que quedo bien.

---

## 9. Orden de trabajo sugerido

1. **`pyproject.toml`** con el extra `[ui]` y los entry points, sin romper
   `requirements.txt` ni el `.spec`.
2. **`aws_ui/core.py`**: envolver `src/` sin Qt. Con pruebas. Aca se decide como
   se captura la salida y como se reporta el progreso.
3. **Refactors minimos en `src/`**, cada uno en su commit:
   - `authenticate_with_mfa(mfa_code)` en vez de `input()`
   - `on_progress` en `import_sql_file`
   - guardar el `Expiration` de las credenciales MFA
   - opcional: `on_output` en vez de `print` directo
4. **`theme.py` + `widgets.py`**: copiar de proxy-local casi tal cual.
5. **Ventana**: sidebar con el arbol de entornos, detalle, log.
6. **Dialogos**: MFA, dump, recrear BD.
7. **Tray + instancia unica + tema**.
8. **`scripts/install_ui.sh`** y el `.desktop`.

Los pasos 2 y 3 son los que tienen riesgo real; del 4 en adelante es copiar y
adaptar.

---

## 10. Cosas para verificar antes de dar por terminado

- [ ] La app arranca sin warnings en stderr (`nohup ... > log 2>&1`).
- [ ] El tray icon se registra: `busctl --user get-property org.kde.StatusNotifierWatcher /StatusNotifierWatcher org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems`
- [ ] Una segunda invocacion no abre otra ventana.
- [ ] `desktop-file-validate ~/.local/share/applications/*.desktop` sin observaciones.
- [ ] `gtk-launch aws-manager-ui` abre la app (es el camino real del click en el menu).
- [ ] Render offscreen en tema claro **y** oscuro, revisando ambos.
- [ ] Ninguna fila clickeable tiene zonas muertas (`item.childAt(punto)` debe dar `None`).
- [ ] Con una operacion larga en curso, la ventana sigue respondiendo.
- [ ] Cancelar a mitad de una descarga no deja el archivo a medias sin avisar.
- [ ] Sin MFA valida, las acciones remotas se deshabilitan con un motivo visible.
- [ ] El suite corre con y sin PySide6 instalado.

---

## Referencias

- Codigo de la UI de referencia: `~/repos/proxy-local/redirect_ui/`
- Su documentacion: `~/repos/proxy-local/docs/ui.md`
- Su instalador: `~/repos/proxy-local/scripts/install_ui.sh`
- Sus pruebas: `~/repos/proxy-local/tests/test_redirect_ui.py` y
  `test_redirect_ui_widgets.py`

# La interfaz gráfica

Este documento describe la UI que **existe**, en `aws_ui/`. La guía de la que
salió está en [`ui-guia.md`](ui-guia.md); acá está lo que se construyó, dónde se
apartó de esa guía y por qué.

```bash
./scripts/install_ui.sh     # instala en ~/.local, sin root
aws-manager-ui              # o desde el menú de aplicaciones, como "aws-manager"
./scripts/install_ui.sh --uninstall
```

El CLI no cambia: `aws-manager` sigue siendo el binario chico de PyInstaller, sin
Qt. La UI es un extra opcional (`pip install .[ui]`) con su propio virtualenv.

---

## 1. Estructura

| Archivo | Responsabilidad |
| --- | --- |
| `core.py` | Puente a `awsm_cli/`. **No importa Qt.** Es lo único testeable sin GUI |
| `theme.py` | Tokens de color y el QSS generado desde ellos |
| `widgets.py` | Widgets propios: dot de estado, pill, card, filas del árbol, progreso, tablas |
| `icons.py` | Iconos dibujados con `QPainter`, sin archivos binarios |
| `dialogs.py` | MFA, selector de dumps remotos, rutas en uso, confirmaciones |
| `settings.py` | La ventana de configuración: credenciales, conexión, entornos, paquetes |
| `window.py` | La ventana: sidebar, páginas de detalle, log, ejecución fuera del hilo de UI |
| `app.py` | Entry point: tema, instancia única, wiring, lanzador de escritorio |

`core.py` no importa Qt: por eso 38 de las 58 pruebas corren sin PySide6
instalado.

## 2. Decisión central: importar `awsm_cli/`, no lanzar el CLI

`awsm_cli/main.py` es un bucle que dibuja menús y hace `input()`. No tiene un flag por
operación, así que no se puede manejar por línea de comandos y automatizar sus
prompts escribiendo en `stdin` sería fragilísimo.

La UI importa `awsm_cli` como librería, en proceso. `MenuManager` **no se usa**: la
ventana lo reemplaza entero. Se reusan `ConfigManager`, `MFAAuthenticator`,
`EC2Manager`, `SecurityGroupManager`, `SSHOperations`, `DumpOperations`,
`DatabaseOperations` y `OperationsLogger`.

## 3. Los seis problemas de la guía, y cómo quedaron

**1. Todo el CLI hacía `print()`.** Se tomó el camino limpio, no
`redirect_stdout`: cada clase acepta `on_output: Callable[[str], None]` que por
omisión es `print`. El CLI no cambia de comportamiento y la UI no depende de un
`sys.stdout` global, que no es thread-safe y se mezclaría entre operaciones.

`Backend._emit` recibe esa salida y la reenvía por una señal Qt, así que el panel
de log se escribe siempre desde el hilo de UI.

**2. MFA necesitaba un código a mitad del flujo.**
`authenticate_with_mfa(mfa_code=None)`: con código no toca `stdin`, sin código
mantiene el prompt del menú. `perform_authentication(mfa_code=None)` igual.

Además, `AWSCredentials` ahora guarda el `Expiration` que devuelve
`aws sts get-session-token` y expone `seconds_left()` / `is_expired()`. El
sidebar muestra cuánto le queda a la sesión; el menú no podía.

**3. SSH es una sesión interactiva de terminal.** La UI resuelve el DNS y valida
la clave con feedback visual, y después le pasa la sesión al emulador de terminal
del sistema. Se prueban en orden `ptyxis`, `kgx`, `gnome-terminal`, `konsole`,
`x-terminal-emulator`, `xterm`, respetando que el flag es `--` en unos y `-e` en
otros; si no hay ninguno se avisa en vez de fallar en silencio. El comando va
envuelto en un `read` final: sin eso el emulador cierra la ventana en cuanto ssh
termina y un error de conexión se pierde antes de poder leerlo.

Lo mismo aplica al `mysql` interactivo.

**4. Progreso real en las operaciones largas.**
`import_sql_file` acepta `on_progress(percent, mb, mb_s)` y la UI lo pinta en una
`QProgressBar`. Para `.sql.gz` el porcentaje es `None` (no se conoce el tamaño
descomprimido) y la barra se muestra indeterminada, que es más honesto que un
0 % que no avanza.

Para el `scp` la guía sugería parsear su salida. No se hizo: `scp` solo dibuja su
barra cuando stdout es una terminal, así que capturado por pipe no imprime nada.
El progreso se mide del lado local, comparando el tamaño del archivo que se está
escribiendo contra el tamaño remoto, que se consulta antes con `stat -c%s`.
Cancelar mata el `scp` y **borra el archivo parcial**, avisando que lo borró: un
`.sql.gz` truncado parece válido hasta que falla el import.

**5. Modificar un Security Group es una acción remota con efecto.** El detalle
del entorno tiene un botón *Comprobar* que resuelve el DNS y consulta el estado
del SG **sin cambiar nada**. Antes de autorizar, un diálogo dice exactamente qué
regla se revoca, qué CIDR se autoriza, en qué puerto y con qué descripción. SSH y
la descarga de dumps pasan por ese mismo paso si la IP todavía no está
autorizada.

**6. `ConfigManager` es un singleton.** Se le agregaron `reset()` (olvida la
instancia) y `reload()` (relee los dos archivos y descarta el `_dump_directory`
cacheado). `reset()` además es lo que permite que las pruebas no se lleven puesta
la configuración de la siguiente.

## 4. Las pantallas

```
┌────────────────────┬──────────────────────────────────────────────┐
│ aws-manager     ⚙  │  OPS · PROD                             PROD │
│ Phoenix v2.1.0     │  ──────────────────────────────────────────  │
│ ○ MFA              │  CONEXIÓN                                    │
│   11h 32m restantes│  instancia   i-09588fe8128509378             │
│                    │  dns         ec2-3-87-86-55.compute-1.aws    │
│ ENTORNOS           │  security…   sg-033d2fa0ae608324a            │
│ ▾ OPS            2 │  tu IP       190.x.x.x · ya autorizada       │
│   ● PROD           │  ──────────────────────────────────────────  │
│   ○ QA             │  [Abrir SSH] [Descargar dump]  [Autorizar IP] │
│ ▸ HIRELENS       2 │                                              │
│                    │  LOG                        [seguir][limpiar]│
│ ────────────────   │  ✓ DNS obtenido: ec2-3-87-86-55…             │
│ LOCAL              │  ✓ Security Group actualizado.               │
│ Base de datos      │                                              │
│ Historial          │  ▓▓▓▓▓▓▓░░░░  42.3% · 231 MB · 8.4 MB/s [✕]  │
│ 2 entornos·4 tipos │  Descargando ops_prod_dump…                  │
└────────────────────┴──────────────────────────────────────────────┘
```

| Pantalla | Contenido |
| --- | --- |
| **MFA** (modal) | 6 dígitos, validación en vivo, error del CLI, y *Solo local* para seguir sin MFA |
| **Detalle de entorno** | instancia, DNS, SG, tu IP y su estado; SSH, dump, autorizar |
| **Descargar dump** | los dumps del servidor con nombre, tamaño y fecha, y barra de progreso |
| **Base de datos** | elegir base, abrir MySQL interactivo, y recrear desde un dump: lista filtrable por entorno o un archivo de cualquier carpeta |
| **Historial** | los logs de `OperationsLogger`, que ya son JSON por línea, en tabla |
| **Rutas** (ⓘ) | qué archivos se usan y dónde, con botón para abrir cada carpeta |
| **Configuración** (⚙, `Ctrl+,`) | credenciales, conexión, entornos y paquetes — ver sección 5 ter |

Estado que la UI muestra y el menú no puede: cuánto le queda a la sesión MFA, si
tu IP ya está autorizada en cada Security Group, tamaño y fecha de los dumps
locales, y progreso real de descarga e import.

## 5. Cómo corre el trabajo

Toda llamada que pueda bloquear va a un `QRunnable` en el `QThreadPool` global y
vuelve por señales (`finished`, `failed`, `progress`). Mientras hay algo en
vuelo, `self.busy = True` y los controles se deshabilitan. Nunca se toca un
widget desde el hilo de trabajo.

Un `QTimer` de 1500 ms compara un *fingerprint* barato y solo reconstruye si
cambió, así los cambios hechos por fuera aparecen solos y sin parpadeo. Los
segundos de la sesión MFA se redondean a minuto dentro del fingerprint: si no, la
ventana se reconstruiría una vez por segundo sin motivo.

Sin sesión MFA válida, SSH, dumps y Security Groups quedan deshabilitados, con la
razón visible en una franja y en el tooltip de cada botón. Las operaciones
locales siguen disponibles: es el equivalente de `--local`.

### La app no corre en segundo plano

Cerrar la ventana **termina el proceso**. No hay icono de bandeja, no hay modo
minimizado y no hay forma de esconder la ventana.

Es una decisión de seguridad, y es la diferencia más grande con proxy-local, que
vive en la bandeja. Acá la sesión MFA deja las credenciales temporales en el
entorno del proceso (`AWSCredentials.apply_to_environment`), y `aws sts
get-session-token` las da por 12 horas. Un proceso escondido en la bandeja
mantendría esas credenciales vivas y usables durante todo ese tiempo, sin nada en
pantalla que lo recuerde. Un proceso que se cierra cuando se cierra su ventana es
lo que hace que "ya terminé" signifique algo.

Consecuencias concretas:

- `closeEvent` acepta el cierre, borra el token de sesión y emite `quit_requested`.
- `setQuitOnLastWindowClosed(True)` es la red por si ese camino no se recorre.
- `Ctrl+W` y `Ctrl+Q` hacen lo mismo: cerrar.
- Con una operación en curso se pide confirmación antes de salir, porque salir la
  interrumpe: una descarga a medias se descarta y un import cortado deja la base
  incompleta.
- La instancia única se conserva: una segunda invocación le pide a la primera que
  muestre su ventana en vez de abrir otra.
- Hay una prueba que falla si vuelven a aparecer `hide_to_tray`,
  `toggle_window`, `hidden_to_tray` o `tray_available`.

## 5 bis. De qué entorno es cada dump

Antes, la procedencia de un dump se codificaba en el nombre del archivo: se le
pegaba adelante el id del entorno. Eso obligaba a renombrar el dump y a adivinar
el entorno parseando el nombre, que se rompe en cuanto un id contiene un guión
bajo o alguien renombra algo.

Ahora el dump **conserva el nombre que tenía en el servidor** y va a una
subcarpeta por entorno (`~/db_dump/ops_prod/dump_prod_2026-08-05.sql.gz`). La
subcarpeta es lo que impide que dos entornos con un dump del mismo nombre se
pisen; el dato de a qué entorno pertenece vive en `.aws-manager-dumps.json`, al
lado de los dumps, y lo escribe `awsm_cli/operations/dump_index.py`.

Eso es lo que hace exacto el filtro por entorno de la pantalla *Base de datos*:
compara ids, no prefijos de nombre. El filtro ofrece todos los entornos, cada
entorno padre (que agrupa sus tipos), cada tipo, y una opción para los dumps que
no pertenecen a ninguno.

Tres cosas que el índice tiene que aguantar, y aguanta:

- **Dumps anteriores al índice.** Si un archivo no está en el índice se cae al
  prefijo del nombre, con el prefijo más largo ganando para que `ops_prod` le
  gane a `ops`. Los dumps viejos siguen clasificados sin mover nada.
- **Un índice corrupto o borrado.** Se trata como índice vacío, se avisa y la app
  sigue: los dumps no se pierden y la carpeta que los contiene sigue diciendo de
  qué entorno son. La escritura es atómica (archivo temporal y `replace`), así
  que una interrupción no deja un índice a medias.
- **Un archivo elegido de otra carpeta.** El botón *Elegir archivo…* acepta
  cualquier `.sql`/`.sql.gz`; no está en el índice y se importa igual, sin
  entorno asociado.

## 5 ter. Configurar sin ver los secretos

La guía no cubría esto: la configuración se editaba a mano en JSON. La ventana de
`settings.py` la reemplaza, con una regla que atraviesa todo el archivo — **un
secreto no se muestra nunca**.

Lo que sí se puede contestar sobre un secreto es "¿está puesto?", "¿cuál es?" y
"¿funciona?", y eso alcanza para configurar:

- **Enmascarado con las puntas visibles** (`AKIA••••••••••••MPLE`). Las puntas son
  lo que permite reconocer *cuál* clave es sin revelarla; un valor corto se tapa
  entero, porque mostrar 4 de 6 caracteres no sería enmascarar nada.
- **De dónde sale.** Si la credencial está en el entorno del proceso, gana sobre
  la del archivo — es el orden que usa `MFAAuthenticator.setup_aws_credentials`,
  así que mostrar la del archivo mentiría. La pestaña tiene además una tabla con
  las variables `AWS_*` del proceso, enmascaradas.
- **Verificar es preguntar, no revelar.** El botón corre
  `aws sts get-caller-identity` y muestra el ARN, que no es secreto. Los mensajes
  de error de AWS pasan por `scrub_secrets`, porque a veces traen el access key
  adentro y ese texto va al panel de log.
- **El campo para cambiar arranca vacío.** `SecretField.value()` devuelve `None`
  mientras no se toque, y el Backend lo interpreta como "dejá el que estaba". Un
  secreto guardado no vuelve a pasar por la pantalla ni por el portapapeles.

Con la llave SSH, igual: `describe_ssh_key` no lee el contenido. Comprueba que
exista, mira los permisos (y ofrece corregirlos a 600, porque con permisos
abiertos el error que da ssh es críptico) y muestra la huella SHA256, que es
pública por naturaleza y confirma cuál es la llave.

### Las variables del shell

Un problema que solo aparece con una GUI: **una app lanzada desde el menú del
escritorio no ve lo que exporta `.zshrc`**. Ese archivo lo lee únicamente un shell
*interactivo*, y a la app la arranca systemd con su propio entorno. Desde una
terminal las variables están y desde el menú no, que es el tipo de diferencia que
vuelve loco a cualquiera — y fue exactamente el síntoma reportado.

`awsm_cli/utils/shell_env.py` lo resuelve preguntándole al shell del usuario,
corriéndolo como login **e** interactivo, que es la combinación que lee
`.zprofile` y `.zshrc`. Detalles que importan:

- **Lista blanca.** Solo se importan variables `AWS_*`. Traerse el entorno entero
  sería una forma cómoda de que un `.zshrc` le cambiara el `PATH` o el
  `LD_PRELOAD` a este proceso, y no hay ninguna razón para necesitarlo.
- **Solo lo que falta.** Una variable puesta a propósito al arrancar la app le
  gana a la del `.zshrc`.
- **Marcadores alrededor de la salida.** Un `.zshrc` con plugins escupe banners y
  mensajes; sin marcadores ese ruido se confundiría con datos.
- **Cualquier shell.** Los flags van separados (`-l -i -c`), que entienden zsh,
  bash y fish por igual, y hay una variante del script para fish, que no entiende
  `if [ ... ]; then ... fi`. Si el shell es algo más exótico, no importa nada y la
  app sigue: no es un error.
- **Nunca se registran valores.** La línea de log nombra las variables
  importadas, no su contenido.

La pestaña de credenciales muestra el origen de cada variable —"proceso" o "shell
de login"— y tiene un botón *Releer del shell* para cuando se edita el `.zshrc`
con la app abierta.

### Llave general o llave propia

Cada tipo de entorno puede tener su `key_path`. Vacío o ausente significa "usar la
general", que es exactamente como se comportaban todos los entornos antes, así que
no hay que migrar nada. `ConfigManager.get_key_path_for()` resuelve la elección en
un solo lugar y `SSHOperations`, `DumpOperations` y el Backend de la UI la usan.

### Paquetes

`awsm_cli/config/bundle.py` exporta un `.zip` con la configuración, los entornos y
las llaves. El detalle que lo hace útil: las rutas de las llaves se reescriben a
`keys/<nombre>.pem` al exportar y, al importar, se copian a
`~/.config/aws-manager/keys/` con permisos 600 y las rutas apuntan ahí. Sin eso el
paquete traería `/home/ezer/...`, que no existe en la otra máquina.

Cosas que el importador aguanta, y que están probadas:

- **Un zip hostil.** De cada entrada de `keys/` se usa solo el nombre, nunca la
  ruta: una entrada `keys/../../escapada.pem` aterriza dentro de la carpeta de
  llaves, no fuera.
- **Un paquete sin credenciales no borra las que había.** Es el caso por omisión
  (exportar secretos es opt-in), y sería una sorpresa desagradable.
- **Una llave que ya no existe** se omite con un aviso, en vez de abortar todo.
- **Un archivo que no es un paquete** se rechaza diciendo qué le falta.

El zip se escribe con permisos 0600, igual que `config.json`, que puede tener
credenciales.

## 6. Dónde se apartó de la guía

- **`ToggleSwitch` no se portó.** En proxy-local enciende y apaga proxies; acá no
  hay ningún estado booleano que alternar, así que sería código muerto.
- **Los tres accesos locales del menú son dos pantallas.** *Recrear BD* y
  *Conectar a BD* operan sobre el mismo MySQL y necesitan el mismo selector de
  base, así que comparten la pantalla *Base de datos*.
- **El progreso del `scp` no se parsea**, se mide por tamaño de archivo. Ver el
  punto 4.
- **Los dumps ya no llevan el entorno en el nombre.** La guía daba por dado el
  prefijo; se reemplazó por un índice con metadata, ver la sección 5 bis.
- **La configuración se edita desde la app.** La guía la daba por editada a
  mano en JSON; ahora hay una ventana entera, ver la sección 5 ter.
- **No hay bandeja ni segundo plano.** La guía daba por portado el tray de
  proxy-local; acá se quitó por seguridad, ver la sección 5.
- **Se agregó el estado de sesión "heredada"**: si ya hay `AWS_SESSION_TOKEN` en
  el entorno, sirve para operar, pero su caducidad no está registrada en ningún
  lado y la UI lo dice en vez de fingir que sabe.

## 7. Pruebas y revisión visual

```bash
python3 -m unittest discover -s tests -t .    # 58 pruebas; 20 se saltan sin PySide6
python3 scripts/render_ui.py                  # PNG de cada pantalla en los dos temas
```

`render_ui.py` renderiza la ventana **offscreen** a PNG en tema claro y oscuro.
Vale la pena: encontró tres defectos antes de abrir la app una sola vez — el
botón *Recrear base* se dibujaba encima de la tabla porque el layout estaba
sobrerrestringido, las cabeceras de tabla iban centradas contra columnas
alineadas a la izquierda, y el pill de PROD en rojo se leía como un error en vez
de como una advertencia.

## 8. Verificado en esta máquina (Fedora 44, GNOME/Wayland)

- [x] Arranca sin nada en stderr salvo avisos de `qt.qpa.wayland.textinput`, que
      son del plugin de Wayland de Qt, no de la app.
- [x] Cerrar la ventana termina el proceso: no queda nada en segundo plano.
- [x] Ningún secreto llega entero a la pantalla, al log ni a un paquete que no
      lo haya pedido, con pruebas que lo verifican.
- [x] Una segunda invocación no abre otra ventana: le pide a la primera que se
      muestre y termina.
- [x] `desktop-file-validate` sin observaciones.
- [x] `gtk-launch aws-manager-ui` abre la app (el camino real del click).
- [x] Render offscreen revisado en tema claro y oscuro.
- [x] Ninguna fila clickeable tiene zonas muertas (`childAt()` da `None`, con
      prueba que lo verifica).
- [x] El suite corre con y sin PySide6 instalado.
- [x] Sin MFA válida, las acciones remotas se deshabilitan con un motivo visible.
- [x] Cancelar una descarga borra el archivo parcial y lo dice.
- [ ] **Sin probar contra AWS de verdad**: autenticación MFA, resolución de DNS,
      modificación de Security Groups, descarga por `scp` e import a MySQL no se
      ejecutaron contra la infraestructura real. Todo eso depende de credenciales
      y de un dispositivo MFA.

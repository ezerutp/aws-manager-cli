# aws_ui — la interfaz gráfica

Una app de escritorio (PySide6/Qt) sobre el mismo núcleo que la CLI: usa los
módulos de [`awsm_cli/`](../awsm_cli/README.md) y la misma configuración, así que
lo que hacés en una se ve en la otra.

El binario `aws-manager` **no cambia**: sigue siendo el ejecutable chico de
PyInstaller, sin Qt. La interfaz es un extra opcional, con su propio virtualenv.

```bash
./scripts/install_ui.sh     # instala en ~/.local, sin sudo (descarga ~110 MB de Qt)
aws-manager-ui              # o desde el menú de aplicaciones, como "aws-manager"
./scripts/install_ui.sh --uninstall
```

Para desarrollo, sin instalar nada en `~/.local`:

```bash
pip install -e '.[ui]'
python3 -m aws_ui
python3 scripts/render_ui.py salida/   # dibuja la ventana a PNG, en ambos temas
```

`core.py` es el puente con el núcleo y **no importa Qt**: es la parte que se
puede probar sin levantar una ventana. El resto de los módulos son la capa
visual (`theme.py`, `widgets.py`, `icons.py`, `dialogs.py`, `settings.py`,
`window.py`, `app.py`).

**Qué agrega sobre el menú de terminal:**

- ⏱️ **Cuánto le queda a la sesión MFA** — el CLI descartaba el `Expiration` que
  devuelve STS; ahora se guarda y se muestra
- 🔐 **Si tu IP ya está autorizada** en el Security Group de cada entorno, y qué
  regla exacta se revocaría y cuál se autorizaría antes de tocar nada
- 📊 **Progreso real** de la descarga (`scp`) y del import a MySQL, con MB/s
- ⏹️ **Cancelar una descarga** sin quedarte con un `.sql.gz` truncado
- 🌳 **El árbol de entornos completo a la vista**, en vez de navegar tres niveles
- 🗂️ **Filtro de dumps por entorno**, exacto porque sale del índice y no de
  parsear el nombre del archivo, más un selector para importar uno de
  cualquier otra carpeta
- ⚙️ **Configuración editable** — credenciales, SSH, MySQL, rutas y el árbol de
  entornos completo, sin editar JSON a mano
- 🙈 **Secretos que no se muestran** — se ve si están puestos, cómo terminan y de
  dónde salen; para verificarlos se pregunta a AWS, no se revelan
- 🔑 **Una llave SSH por entorno** — cada tipo puede usar la general o la suya
- 📦 **Exportar e importar** la configuración con las llaves, para mudarse de
  máquina sin rearmar nada
- 📋 **Historial en tabla**, leído de los mismos logs JSON que `--logs`

SSH y el `mysql` interactivo se abren en el emulador de terminal del sistema
(`ptyxis`, `kgx`, `gnome-terminal`, `konsole`, `xterm`…), porque son sesiones de
terminal de verdad. La actualización del Security Group sí ocurre dentro de la
UI, con confirmación y feedback.

Sin sesión MFA válida, las acciones remotas quedan deshabilitadas con el motivo a
la vista; las operaciones locales siguen disponibles, igual que `--local`.

### Configuración desde la interfaz

El engranaje (`Ctrl+,`) abre la configuración completa, en cuatro pestañas:

| Pestaña | Qué tiene |
| --- | --- |
| **Credenciales** | `access_key` y `secret_key` enmascaradas, region, `rule_description`, verificación contra AWS y las variables de entorno del proceso |
| **Conexión** | la llave SSH general (con permisos y huella), SSH, MySQL local y la carpeta de dumps |
| **Entornos** | el árbol de entornos padre y sus tipos, editable, con la llave de cada uno |
| **Exportar / importar** | paquetes `.zip` con la configuración y las llaves |

**Las variables de entorno se detectan aunque estén en tu `.zshrc`.** Una app
lanzada desde el menú del escritorio *no* hereda lo que exporta ese archivo: lo
lee solo un shell interactivo, y a la app la arranca systemd con su propio
entorno. Por eso la app le pregunta al shell de login (`$SHELL -l -i -c`) por las
variables `AWS_*` que le falten, al arrancar y también con el botón *Releer del
shell*. Funciona con zsh, bash, dash y ksh, y tiene una variante para fish, que
usa otra sintaxis.

Solo se importan las variables de una lista blanca (`AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`, `AWS_DEFAULT_REGION`, `AWS_REGION`,
`AWS_PROFILE`). Traerse el entorno entero sería una forma cómoda de que un
`.zshrc` cambiara el `PATH` de la app. Una variable ya definida al arrancar no se
pisa, y la tabla dice de dónde salió cada una.

**Los secretos no se muestran nunca.** Se ve si están puestos, cómo terminan
(`AKIA••••••••••••MPLE`), cuántos caracteres tienen y si salen del archivo o del
entorno. Para comprobar que funcionan se ejecuta `aws sts get-caller-identity` y
se muestra el ARN, que no es secreto. El campo para cambiarlos arranca vacío: un
valor guardado no vuelve a pasar por la pantalla.

Con la llave SSH pasa lo mismo: no se lee su contenido. Se verifica que exista,
que tenga permisos 600 (con un botón para corregirlos) y se muestra su huella
SHA256, que es pública y sirve para confirmar cuál es.

**Llave por entorno.** Cada tipo puede usar la llave general o una propia. Un
`key_path` vacío o ausente significa "usar la general", que es como se comportaban
todos los entornos antes de que esto existiera, así que no hay que tocar nada.

**Exportar e importar.** El paquete es un `.zip` con `config.json`,
`config-environment.json` y las llaves. Las rutas de las llaves se reescriben a
rutas relativas al paquete y, al importar, se copian a `~/.config/aws-manager/keys/`
con permisos 600 — así funciona en otra máquina, donde `/home/otro/...` no existe.
Incluir las credenciales AWS es opcional y está desmarcado por omisión; si el
paquete no las trae, importar **no borra** las que ya tenías.

> ⚠ Un paquete con llaves o credenciales da acceso a tu infraestructura. Se
> escribe con permisos 600, pero tratalo como tratarías la llave privada.

**La aplicación no corre en segundo plano.** No hay icono de bandeja: cerrar la
ventana termina el proceso y borra el token de sesión temporal. Es deliberado —
las credenciales MFA viven en el entorno del proceso, y dejarlo corriendo
escondido las mantendría disponibles durante horas sin nada en pantalla que lo
recuerde. Si hay una operación en curso, se avisa antes de salir.

### Descargar un dump

`Descargar dump` lista lo que hay en el servidor del entorno. Cada fila trae su
propio botón **Descargar**, que baja *esa* fila sin importar cuál esté
seleccionada; también sirven el doble clic y Enter sobre la fila elegida, que se
pinta con el color de acento. No hay un botón de descarga abajo: repetía la
acción y obligaba a mirar dos lugares para saber qué se iba a bajar.

Antes de empezar se pide confirmación, con el tamaño y la ruta de destino: una
descarga puede ser de varios GB y tarda. Si el archivo ya existe, la
confirmación lo dice y se marca como destructiva, porque lo va a pisar.

Los detalles de diseño e implementación están en [`docs/ui.md`](../docs/ui.md);
la guía de la que salió, en [`docs/ui-guia.md`](../docs/ui-guia.md).

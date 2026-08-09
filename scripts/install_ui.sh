#!/usr/bin/env bash
# Instala aws-manager-ui para el usuario actual: su propio virtualenv bajo
# ~/.local/share, un comando `aws-manager-ui` en ~/.local/bin y un lanzador en la
# lista de aplicaciones. Sin root y sin tocar nada fuera de ~/.local.
#
# No se toca aws-manager.spec: el binario del CLI debe seguir siendo chico y sin
# Qt. Empaquetar Qt con PyInstaller lo llevaria de ~10 MB a ~150 MB.
set -Eeuo pipefail

APP_NAME="aws-manager-ui"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
APP_INSTALL_DIR="${APP_INSTALL_DIR:-$HOME/.local/share/$APP_NAME}"
APPLICATIONS_DIR="${APPLICATIONS_DIR:-$HOME/.local/share/applications}"
ICON_DIR="${ICON_DIR:-$HOME/.local/share/icons/hicolor/256x256/apps}"
CONFIG_DIR="${CONFIG_DIR:-$HOME/.config/aws-manager}"
SKIP_TESTS="${SKIP_TESTS:-0}"

VENV="$APP_INSTALL_DIR/venv"
LAUNCHER="$INSTALL_DIR/$APP_NAME"
DESKTOP_FILE="$APPLICATIONS_DIR/$APP_NAME.desktop"
ICON_FILE="$ICON_DIR/$APP_NAME.png"

log() {
  printf '\n==> %s\n' "$*"
}

warn() {
  printf 'aviso: %s\n' "$*" >&2
}

refresh_desktop_caches() {
  if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
  fi
  if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -tq "$(dirname "$(dirname "$ICON_DIR")")" >/dev/null 2>&1 || true
  fi
}

uninstall() {
  log "Quitando $APP_NAME"
  pkill -f "$VENV/bin/$APP_NAME" 2>/dev/null || true
  rm -rf "$APP_INSTALL_DIR"
  rm -f "$LAUNCHER" "$DESKTOP_FILE" "$ICON_FILE"
  refresh_desktop_caches
  printf '\nEliminado:\n  %s\n  %s\n  %s\n  %s\n' \
    "$APP_INSTALL_DIR" "$LAUNCHER" "$DESKTOP_FILE" "$ICON_FILE"
  printf '\nLa configuracion en %s y los dumps quedaron intactos.\n' "$CONFIG_DIR"
  printf 'El CLI `aws-manager` no se toca.\n'
}

ensure_python() {
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    printf 'No se encontro el interprete %s. Defini PYTHON_BIN.\n' "$PYTHON_BIN" >&2
    exit 1
  fi
  if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    printf '%s es anterior al Python 3.10 requerido.\n' "$PYTHON_BIN" >&2
    exit 1
  fi
}

check_tools() {
  local missing=()
  for tool in aws ssh scp; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    warn "faltan herramientas requeridas: ${missing[*]}"
  fi
  command -v mysql >/dev/null 2>&1 || \
    warn "mysql no esta instalado: hace falta solo para recrear bases locales"

  # La UI no tiene terminal propia: SSH y el mysql interactivo se abren en una.
  local terminal=""
  for candidate in ptyxis kgx gnome-terminal konsole x-terminal-emulator xterm; do
    if command -v "$candidate" >/dev/null 2>&1; then
      terminal="$candidate"
      break
    fi
  done
  if [ -z "$terminal" ]; then
    warn "no hay ningun emulador de terminal: SSH y el mysql interactivo no van a abrir"
  else
    printf '  terminal para sesiones interactivas: %s\n' "$terminal"
  fi
}

install_app() {
  log "Usando $("$PYTHON_BIN" -c 'import sys; print(sys.executable, sys.version.split()[0])')"

  if [ "$SKIP_TESTS" != "1" ]; then
    log "Corriendo las pruebas"
    (cd "$PROJECT_ROOT" && env PYTHONDONTWRITEBYTECODE=1 \
      "$PYTHON_BIN" -m unittest discover -s tests -t .)
  fi

  log "Verificando dependencias del sistema"
  check_tools

  # Un virtualenv propio mantiene Qt fuera del camino de cualquier otro entorno y
  # hace que la instalacion no dependa del checkout.
  log "Creando el virtualenv en $VENV"
  mkdir -p "$APP_INSTALL_DIR"
  rm -rf "$VENV"
  "$PYTHON_BIN" -m venv "$VENV"
  "$VENV/bin/python" -m pip install --upgrade pip --quiet

  # setuptools deja su staging en build/lib y lo reutiliza entre builds, pero no
  # borra los paquetes que dejaron de existir: sin esto, un paquete renombrado se
  # cuela en el wheel con su nombre viejo. No se toca el resto de build/, que es
  # la cache de PyInstaller.
  log "Limpiando el staging de setuptools"
  rm -rf "$PROJECT_ROOT/build/lib" "$PROJECT_ROOT/build/bdist."* \
         "$PROJECT_ROOT"/*.egg-info

  log "Instalando $APP_NAME y PySide6 (descarga ~110 MB)"
  "$VENV/bin/python" -m pip install --quiet "$PROJECT_ROOT[ui]"

  log "Escribiendo el lanzador en $LAUNCHER"
  mkdir -p "$INSTALL_DIR"
  cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec "$VENV/bin/$APP_NAME" "\$@"
EOF
  chmod +x "$LAUNCHER"

  log "Registrando la aplicacion en el menu"
  mkdir -p "$APPLICATIONS_DIR" "$ICON_DIR"
  AWS_MANAGER_UI_APPLICATIONS_DIR="$APPLICATIONS_DIR" \
  AWS_MANAGER_UI_ICON_DIR="$ICON_DIR" \
  AWS_MANAGER_UI_EXEC="$LAUNCHER" \
    "$VENV/bin/$APP_NAME" --install-desktop-entry
  refresh_desktop_caches

  if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$DESKTOP_FILE" && printf '  .desktop valido\n'
  fi

  log "Verificando el comando instalado"
  "$LAUNCHER" --version
  "$VENV/bin/python" -c 'import PySide6; print("PySide6", PySide6.__version__)'
}

report() {
  printf '\nInstalado:\n'
  printf '  comando   %s\n' "$LAUNCHER"
  printf '  lanzador  %s\n' "$DESKTOP_FILE"
  printf '  app       %s\n' "$VENV"

  case ":$PATH:" in
    *":$INSTALL_DIR:"*) ;;
    *)
      printf '\nAgrega esto a tu perfil de shell para que `%s` resuelva:\n' "$APP_NAME"
      printf '  export PATH="%s:$PATH"\n' "$INSTALL_DIR"
      ;;
  esac

  if [ ! -f "$CONFIG_DIR/config.json" ]; then
    printf '\nNo hay %s todavia.\n' "$CONFIG_DIR/config.json"
    printf 'La UI busca la configuracion en el mismo orden que el CLI:\n'
    printf '  1. %s\n  2. la carpeta del ejecutable\n  3. el directorio actual\n' "$CONFIG_DIR"
  fi

  printf '\nCorrelo con `%s`, o desde el menu como "aws-manager".\n' "$APP_NAME"
  printf 'Desinstalalo con `%s --uninstall`.\n' "$0"
}

main() {
  case "${1:-}" in
    --uninstall)
      uninstall
      return 0
      ;;
    -h|--help)
      printf 'uso: %s [--uninstall]\n\n' "$0"
      printf 'Entorno: PYTHON_BIN, INSTALL_DIR, APP_INSTALL_DIR,\n'
      printf '         APPLICATIONS_DIR, ICON_DIR, CONFIG_DIR, SKIP_TESTS=1\n'
      return 0
      ;;
    "") ;;
    *)
      printf 'Argumento desconocido: %s\n' "$1" >&2
      return 1
      ;;
  esac

  ensure_python
  install_app
  report
}

main "$@"

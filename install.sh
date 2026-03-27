#!/bin/bash
# Installation script for aws-manager CLI binary

set -e

BINARY_NAME="aws-manager"
INSTALL_DIR="/usr/local/bin"

# Lista de comandos prohibidos para evitar conflictos
FORBIDDEN_NAMES=("aws" "ssh" "mysql" "docker" "kubectl" "git" "python" "pip" "sudo" "bash" "sh")

# Función para validar el nombre del alias
validate_alias_name() {
    local name=$1
    
    # Verificar que no esté vacío
    if [ -z "$name" ]; then
        return 1
    fi
    
    # Verificar que no sea un comando prohibido
    for forbidden in "${FORBIDDEN_NAMES[@]}"; do
        if [ "$name" = "$forbidden" ]; then
            echo "✗ Error: '$name' es un comando del sistema. Elige otro nombre."
            return 1
        fi
    done
    
    # Verificar que no contenga espacios o caracteres especiales
    if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo "✗ Error: El nombre solo puede contener letras, números, guiones y guiones bajos."
        return 1
    fi
    
    # Verificar si el comando ya existe en el sistema
    if command -v "$name" &> /dev/null; then
        echo "⚠ Advertencia: El comando '$name' ya existe en el sistema."
        read -p "¿Deseas sobrescribirlo? (s/N): " overwrite
        if [[ ! "$overwrite" =~ ^[sS]$ ]]; then
            return 1
        fi
    fi
    
    return 0
}

# Detectar el usuario real incluso cuando se ejecuta con sudo
if [ -n "$SUDO_USER" ]; then
    REAL_USER="$SUDO_USER"
    REAL_HOME=$(eval echo ~$SUDO_USER)
else
    REAL_USER="$USER"
    REAL_HOME="$HOME"
fi

CONFIG_DIR="$REAL_HOME/.config/aws-manager"

echo "╔════════════════════════════════════════╗"
echo "║  AWS Manager CLI - Instalador          ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check if binary exists
if [ ! -f "dist/$BINARY_NAME" ]; then
    echo "✗ Error: Binario no encontrado en dist/$BINARY_NAME"
    echo "  Ejecuta primero: ./build.sh"
    exit 1
fi

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then
    echo "✗ Error: Este script necesita permisos de sudo para copiar a $INSTALL_DIR"
    echo "  Ejecuta con: sudo ./install.sh"
    exit 1
fi

echo "Usuario real: $REAL_USER"
echo "Directorio home: $REAL_HOME"
echo ""

# Install binary
echo "Instalando binario en $INSTALL_DIR..."
cp "dist/$BINARY_NAME" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/$BINARY_NAME"
echo "✓ Binario instalado: $INSTALL_DIR/$BINARY_NAME"

# Ask for custom alias
echo ""
echo "═══════════════════════════════════════"
echo "  Configuración de Alias Personalizado"
echo "═══════════════════════════════════════"
echo ""
echo "Puedes crear un alias/symlink con un nombre personalizado."
echo "El binario '$BINARY_NAME' seguirá disponible con su nombre original."
echo ""
echo "Ejemplos: awsm, ops-manager, my-aws, etc."
echo "Nota: No uses nombres de comandos del sistema (aws, ssh, docker, etc.)"
echo ""

ALIAS_NAME=""
while true; do
    read -p "Nombre del alias (Enter para omitir): " ALIAS_NAME
    
    # Si el usuario presiona Enter sin escribir nada, omitir
    if [ -z "$ALIAS_NAME" ]; then
        echo "✓ Alias omitido. Usa '$BINARY_NAME' para ejecutar el programa."
        break
    fi
    
    # Validar el nombre
    if validate_alias_name "$ALIAS_NAME"; then
        # Crear symlink
        ln -sf "$INSTALL_DIR/$BINARY_NAME" "$INSTALL_DIR/$ALIAS_NAME"
        echo "✓ Alias creado: $ALIAS_NAME -> $BINARY_NAME"
        break
    fi
    
    echo "Intenta con otro nombre..."
done

# Create config directory
echo ""
echo "Creando directorio de configuración..."
mkdir -p "$CONFIG_DIR"
chown "$REAL_USER:$REAL_USER" "$CONFIG_DIR"
echo "✓ Directorio creado: $CONFIG_DIR"

# Copy config files if they don't exist
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    if [ -f "config.json" ]; then
        echo "Copiando config.json..."
        cp config.json "$CONFIG_DIR/"
        chown "$REAL_USER:$REAL_USER" "$CONFIG_DIR/config.json"
        echo "✓ config.json copiado"
    else
        echo "⚠ config.json no encontrado, usa config.example.json como plantilla"
    fi
else
    echo "✓ config.json ya existe en $CONFIG_DIR"
fi

if [ ! -f "$CONFIG_DIR/config-environment.json" ]; then
    if [ -f "config-environment.json" ]; then
        echo "Copiando config-environment.json..."
        cp config-environment.json "$CONFIG_DIR/"
        chown "$REAL_USER:$REAL_USER" "$CONFIG_DIR/config-environment.json"
        echo "✓ config-environment.json copiado"
    else
        echo "⚠ config-environment.json no encontrado"
    fi
else
    echo "✓ config-environment.json ya existe en $CONFIG_DIR"
fi

# Check system dependencies
echo ""
echo "Verificando dependencias del sistema..."

if command -v aws &> /dev/null; then
    echo "✓ AWS CLI instalado"
else
    echo "⚠ AWS CLI no está instalado"
    echo "  Instala con: sudo apt install awscli"
fi

if command -v ssh &> /dev/null; then
    echo "✓ SSH instalado"
else
    echo "⚠ SSH no está instalado"
    echo "  Instala con: sudo apt install openssh-client"
fi

echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Instalación Completada                ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Para usar el programa, ejecuta:"
echo "  $BINARY_NAME"
if [ -n "$ALIAS_NAME" ]; then
    echo "  $ALIAS_NAME  (alias personalizado)"
fi
echo ""
echo "Archivos de configuración en:"
echo "  $CONFIG_DIR"
echo ""

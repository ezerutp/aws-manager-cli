#!/bin/bash
# Local installation script for aws-manager CLI binary (no sudo required)

set -e

BINARY_NAME="aws-manager"
INSTALL_DIR="$HOME/.local/bin"
CONFIG_DIR="$HOME/.config/aws-manager"

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

echo "╔════════════════════════════════════════╗"
echo "║  AWS Manager CLI - Instalador Local   ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Instalación sin permisos de sudo"
echo "Directorio de instalación: $INSTALL_DIR"
echo ""

# Check if binary exists
if [ ! -f "dist/$BINARY_NAME" ]; then
    echo "✗ Error: Binario no encontrado en dist/$BINARY_NAME"
    echo "  Ejecuta primero: ./build.sh"
    exit 1
fi

# Create install directory if it doesn't exist
echo "Preparando directorio de instalación..."
mkdir -p "$INSTALL_DIR"
echo "✓ Directorio listo: $INSTALL_DIR"

# Install binary
echo ""
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
echo "✓ Directorio creado: $CONFIG_DIR"

# Copy config files if they don't exist
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    if [ -f "config.json" ]; then
        echo "Copiando config.json..."
        cp config.json "$CONFIG_DIR/"
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
        echo "✓ config-environment.json copiado"
    else
        echo "⚠ config-environment.json no encontrado"
    fi
else
    echo "✓ config-environment.json ya existe en $CONFIG_DIR"
fi

# Check if .local/bin is in PATH
echo ""
echo "Verificando configuración de PATH..."
if [[ ":$PATH:" == *":$INSTALL_DIR:"* ]]; then
    echo "✓ $INSTALL_DIR ya está en PATH"
else
    echo "⚠ $INSTALL_DIR no está en PATH"
    echo ""
    echo "Para agregar $INSTALL_DIR a tu PATH, ejecuta:"
    echo ""
    
    # Detect shell
    if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ] || [ "$SHELL" = "/usr/bin/zsh" ]; then
        SHELL_RC="$HOME/.zshrc"
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc"
        echo "  source ~/.zshrc"
    elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "/bin/bash" ] || [ "$SHELL" = "/usr/bin/bash" ]; then
        SHELL_RC="$HOME/.bashrc"
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
        echo "  source ~/.bashrc"
    else
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.profile"
        echo "  source ~/.profile"
    fi
    
    echo ""
    read -p "¿Deseas agregar automáticamente $INSTALL_DIR a tu PATH? (s/N): " add_path
    if [[ "$add_path" =~ ^[sS]$ ]]; then
        # Detect shell config file
        if [ -n "$ZSH_VERSION" ] || [ "$SHELL" = "/bin/zsh" ] || [ "$SHELL" = "/usr/bin/zsh" ]; then
            SHELL_RC="$HOME/.zshrc"
        elif [ -n "$BASH_VERSION" ] || [ "$SHELL" = "/bin/bash" ] || [ "$SHELL" = "/usr/bin/bash" ]; then
            SHELL_RC="$HOME/.bashrc"
        else
            SHELL_RC="$HOME/.profile"
        fi
        
        # Add to PATH if not already there
        if ! grep -q "\.local/bin" "$SHELL_RC" 2>/dev/null; then
            echo "" >> "$SHELL_RC"
            echo "# Added by aws-manager installer" >> "$SHELL_RC"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
            echo "✓ PATH actualizado en $SHELL_RC"
            echo "  Ejecuta: source $SHELL_RC"
        else
            echo "✓ PATH ya contiene .local/bin en $SHELL_RC"
        fi
    fi
fi

# Check system dependencies
echo ""
echo "Verificando dependencias del sistema..."

if command -v aws &> /dev/null; then
    echo "✓ AWS CLI instalado"
else
    echo "⚠ AWS CLI no está instalado"
    echo "  Instala desde: https://aws.amazon.com/cli/"
fi

if command -v ssh &> /dev/null; then
    echo "✓ SSH instalado"
else
    echo "⚠ SSH no está instalado"
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

# Si PATH no está configurado, mostrar advertencia
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo "⚠ IMPORTANTE: Recuerda ejecutar 'source' en tu shell config"
    echo "   para que el comando esté disponible en nuevas terminales."
    echo ""
fi

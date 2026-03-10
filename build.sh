#!/bin/bash
# Build script for aws-manager CLI using PyInstaller
# Target: Linux x64

set -e  # Exit on error

echo "╔════════════════════════════════════════╗"
echo "║  AWS Manager CLI - Build Script        ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "✗ PyInstaller no está instalado."
    echo "  Instala con: pip3 install pyinstaller"
    exit 1
fi
echo "✓ PyInstaller disponible: $(pyinstaller --version)"

# Check if UPX is installed (optional but recommended)
if ! command -v upx &> /dev/null; then
    echo "⚠ UPX no está instalado (recomendado para reducir tamaño)."
    echo "  Instala con: sudo apt install upx"
    echo "  Continuando sin compresión UPX..."
    # Modify spec to disable UPX
    sed -i 's/upx=True/upx=False/' aws-manager.spec
else
    echo "✓ UPX disponible: $(upx --version | head -n1)"
fi

# Clean previous builds
echo ""
echo "Limpiando builds anteriores..."
rm -rf build/ dist/ __pycache__
find src -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
echo "✓ Limpieza completada"

# Build with PyInstaller
echo ""
echo "Compilando binario..."
echo "Esto puede tomar 1-2 minutos..."
echo ""
pyinstaller \
    --clean \
    --noconfirm \
    aws-manager.spec

# Check if build was successful
if [ -f "dist/aws-manager" ]; then
    echo ""
    echo "╔════════════════════════════════════════╗"
    echo "║  Build Exitoso                         ║"
    echo "╚════════════════════════════════════════╝"
    echo ""
    
    # Get file size
    SIZE=$(du -h dist/aws-manager | cut -f1)
    echo "✓ Binario creado: dist/aws-manager"
    echo "✓ Tamaño: $SIZE"
    
    # Make executable
    chmod +x dist/aws-manager
    
    echo ""
    echo "  Próximos pasos:"
    echo ""
    echo "1. Para instalar en el sistema (recomendado):"
    echo "   sudo ./install.sh"
    echo ""
    echo "   Esto instalará:"
    echo "   • El binario en /usr/local/bin/aws-manager"
    echo "   • Configuración en ~/.config/aws-manager/"
    echo ""
    echo "2. O prueba el binario localmente:"
    echo "   cd dist && ./aws-manager"
    echo ""
    echo "¡Listo!"
    
else
    echo ""
    echo "✗ Error: No se pudo crear el binario."
    echo "  Revisa los mensajes de error arriba."
    exit 1
fi

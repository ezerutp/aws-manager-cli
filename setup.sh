#!/bin/bash
# Quick setup script for AWS Manager CLI

echo "╔════════════════════════════════════════╗"
echo "║  AWS Manager CLI - Setup               ║"
echo "╚════════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "✗ Python 3 no está instalado."
    echo "  Instala con: sudo apt install python3 python3-pip"
    exit 1
fi
echo "✓ Python 3 instalado: $(python3 --version)"

# Check pip
if ! command -v pip3 &> /dev/null; then
    echo "✗ pip3 no está instalado."
    echo "  Instala con: sudo apt install python3-pip"
    exit 1
fi
echo "✓ pip3 instalado"

# Install Python dependencies
echo ""
echo "Instalando dependencias Python..."
pip3 install -r requirements.txt

# Check system tools
echo ""
echo "Verificando herramientas del sistema..."

if command -v aws &> /dev/null; then
    echo "✓ AWS CLI instalado: $(aws --version 2>&1 | head -n1)"
else
    echo "⚠ AWS CLI no está instalado."
    echo "  Instala con: sudo apt install awscli"
    echo "  O visita: https://aws.amazon.com/cli/"
fi

if command -v ssh &> /dev/null; then
    echo "✓ SSH instalado"
else
    echo "✗ SSH no está instalado."
    echo "  Instala con: sudo apt install openssh-client"
fi

if command -v mysql &> /dev/null; then
    echo "✓ MySQL client instalado"
else
    echo "⚠ MySQL client no está instalado (solo necesario para recrear BD)."
    echo "  Instala con: sudo apt install mysql-client"
fi

# Setup config files
echo ""
echo "Configurando archivos..."

if [ ! -f "config.json" ]; then
    echo "✓ Creando config.json desde ejemplo..."
    cp config.example.json config.json
    echo "  ⚠ IMPORTANTE: Edita config.json con tus credenciales"
else
    echo "✓ config.json ya existe"
fi

if [ ! -f "config-environment.json" ]; then
    echo "✓ Creando config-environment.json desde ejemplo..."
    cp config-environment.example.json config-environment.json
    echo "  ⚠ IMPORTANTE: Edita config-environment.json con tus entornos"
else
    echo "✓ config-environment.json ya existe"
fi

# Make main.py executable
chmod +x main.py
echo "✓ main.py es ejecutable"

echo ""
echo "╔════════════════════════════════════════╗"
echo "║  Setup Completado                      ║"
echo "╚════════════════════════════════════════╝"
echo ""
echo "Pasos siguientes:"
echo "1. Edita config.json con tus credenciales AWS"
echo "2. Edita config-environment.json con tus entornos"
echo "3. Ejecuta: ./main.py o python3 main.py"
echo ""

"""Script de entrada para PyInstaller.

PyInstaller ejecuta este archivo como script de nivel superior, no como parte del
paquete, asi que los imports tienen que ser absolutos: `__main__.py` usa imports
relativos y ahi fallarian con "attempted relative import with no known parent
package".

Para `python3 -m awsm_cli` y para el entry point `aws-manager` instalado con pip,
el que manda es `__main__.py`; este archivo existe solo para el binario.
"""
import sys

from awsm_cli.__main__ import run

if __name__ == '__main__':
    sys.exit(run())

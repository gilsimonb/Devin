"""Inicializa la base de datos SQLite local.

Uso:
    python database/init_db.py

Crea ``database/finanzas.db`` con el esquema de la aplicación. Si el archivo
ya existe, únicamente agrega las tablas que falten; nunca borra información.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import Config  # noqa: E402
from database.db import inicializar_base_datos  # noqa: E402


def main() -> None:
    ruta = Config.DATABASE_PATH
    existia = ruta.exists()
    inicializar_base_datos(ruta)
    if existia:
        print(f"Base de datos verificada: {ruta}")
    else:
        print(f"Base de datos creada: {ruta}")
    print("Al abrir la aplicación por primera vez se te pedirá crear tu usuario.")


if __name__ == "__main__":
    main()

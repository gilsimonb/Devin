"""Acceso a la base de datos SQLite local."""

import sqlite3
from pathlib import Path

from flask import current_app, g

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def conectar(ruta) -> sqlite3.Connection:
    """Abre una conexión a la base de datos indicada."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(
        str(ruta), detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None
    )
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.execute("PRAGMA journal_mode = WAL")
    return conexion


def crear_esquema(conexion: sqlite3.Connection) -> None:
    """Crea las tablas si no existen."""
    conexion.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def inicializar_base_datos(ruta) -> None:
    """Crea el archivo de base de datos y su esquema."""
    conexion = conectar(ruta)
    try:
        crear_esquema(conexion)
    finally:
        conexion.close()


def get_db() -> sqlite3.Connection:
    """Devuelve la conexión asociada a la petición actual."""
    if "db" not in g:
        g.db = conectar(current_app.config["DATABASE_PATH"])
    return g.db


def cerrar_db(_exc=None) -> None:
    conexion = g.pop("db", None)
    if conexion is not None:
        conexion.close()


def init_app(app) -> None:
    app.teardown_appcontext(cerrar_db)
    inicializar_base_datos(app.config["DATABASE_PATH"])

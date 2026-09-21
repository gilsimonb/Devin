"""Respaldo y restauración local de la base de datos SQLite.

Los respaldos se guardan únicamente en la carpeta ``backups/`` del equipo.
"""

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from flask import current_app

from database.db import cerrar_db, conectar, crear_esquema, get_db
from models import usuario as modelo
from services import auth_service

_CABECERA_SQLITE = b"SQLite format 3\x00"
_TABLAS_REQUERIDAS = {"usuarios", "auditoria_seguridad"}
_PREFIJO = "finanzas_"


@dataclass
class Respaldo:
    nombre: str
    ruta: Path
    fecha: datetime
    tamano: int


def _directorio() -> Path:
    ruta = Path(current_app.config["BACKUPS_PATH"])
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def listar_respaldos() -> List[Respaldo]:
    resultado = []
    for archivo in sorted(_directorio().glob(f"{_PREFIJO}*.db"), reverse=True):
        stat = archivo.stat()
        resultado.append(
            Respaldo(
                nombre=archivo.name,
                ruta=archivo,
                fecha=datetime.fromtimestamp(stat.st_mtime).replace(microsecond=0),
                tamano=stat.st_size,
            )
        )
    return resultado


def crear_respaldo(usuario_id: int, sufijo: str = "") -> Respaldo:
    """Copia consistente de la base de datos usando la API de respaldo de SQLite."""
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre = f"{_PREFIJO}{marca}{sufijo}.db"
    destino = _directorio() / nombre

    origen = conectar(current_app.config["DATABASE_PATH"])
    copia = sqlite3.connect(str(destino))
    try:
        origen.backup(copia)
    finally:
        copia.close()
        origen.close()

    modelo.registrar_evento(usuario_id, auth_service.RESPALDO_CREADO, nombre)
    stat = destino.stat()
    return Respaldo(nombre, destino, datetime.fromtimestamp(stat.st_mtime), stat.st_size)


def validar_archivo_respaldo(ruta: Path) -> Optional[str]:
    """Devuelve un mensaje de error si el archivo no es un respaldo válido."""
    if not ruta.exists() or ruta.stat().st_size < 100:
        return "El archivo está vacío o no existe."
    with ruta.open("rb") as f:
        if f.read(16) != _CABECERA_SQLITE:
            return "El archivo no es una base de datos SQLite válida."

    try:
        conexion = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    except sqlite3.Error:
        return "No fue posible abrir el archivo como base de datos."
    try:
        integridad = conexion.execute("PRAGMA integrity_check").fetchone()
        if not integridad or integridad[0] != "ok":
            return "La base de datos del respaldo está dañada."
        tablas = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        if not _TABLAS_REQUERIDAS.issubset(tablas):
            return "El archivo no corresponde a un respaldo de Mis Finanzas."
        columnas = {
            fila[1] for fila in conexion.execute("PRAGMA table_info(usuarios)").fetchall()
        }
        if not {"usuario", "password_hash"}.issubset(columnas):
            return "El respaldo tiene una estructura de usuarios incompatible."
        total = conexion.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if total < 1:
            return "El respaldo no contiene ningún usuario."
    except sqlite3.Error:
        return "No fue posible leer el contenido del respaldo."
    finally:
        conexion.close()
    return None


def restaurar_respaldo(usuario_id: int, ruta_archivo: Path, nombre_original: str) -> Optional[str]:
    """Valida y restaura un respaldo. Antes de reemplazar la base de datos
    actual se crea una copia de seguridad automática. Devuelve un mensaje de
    error o ``None`` si todo salió bien."""
    error = validar_archivo_respaldo(ruta_archivo)
    if error:
        modelo.registrar_evento(usuario_id, auth_service.RESPALDO_RECHAZADO, error)
        return error

    crear_respaldo(usuario_id, sufijo="_antes_de_restaurar")

    destino = Path(current_app.config["DATABASE_PATH"])
    # Cerrar la conexión de la petición antes de reemplazar el archivo.
    cerrar_db()
    for extra in ("-wal", "-shm"):
        residual = destino.with_name(destino.name + extra)
        if residual.exists():
            residual.unlink()
    shutil.copyfile(ruta_archivo, destino)
    crear_esquema(get_db())

    # El evento se registra ya sobre la base de datos restaurada. El usuario
    # puede no existir en ella, por lo que se guarda sin usuario_id en ese caso.
    restaurado = modelo.obtener_por_id(usuario_id)
    modelo.registrar_evento(
        restaurado.id if restaurado else None,
        auth_service.RESPALDO_RESTAURADO,
        nombre_original,
    )
    return None

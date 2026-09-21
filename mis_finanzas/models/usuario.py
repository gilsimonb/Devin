"""Acceso a datos de usuarios, auditoría y configuración.

Todas las consultas están parametrizadas. Este módulo no contiene lógica de
negocio: eso corresponde a ``services``.
"""

from datetime import datetime
from typing import Optional

from database.db import get_db

FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"


def _a_texto(fecha: Optional[datetime]) -> Optional[str]:
    return fecha.strftime(FORMATO_FECHA) if fecha else None


def _a_fecha(valor) -> Optional[datetime]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor
    return datetime.strptime(str(valor)[:19], FORMATO_FECHA)


class Usuario:
    """Representa una fila de la tabla ``usuarios``."""

    def __init__(self, fila):
        self.id: int = fila["id"]
        self.usuario: str = fila["usuario"]
        self.nombre: str = fila["nombre"] or fila["usuario"]
        self.password_hash: str = fila["password_hash"]
        self.recovery_code_hash: Optional[str] = fila["recovery_code_hash"]
        self.recovery_code_used: bool = bool(fila["recovery_code_used"])
        self.activo: bool = bool(fila["activo"])
        self.intentos_fallidos: int = fila["intentos_fallidos"]
        self.bloqueado_hasta: Optional[datetime] = _a_fecha(fila["bloqueado_hasta"])
        self.ultimo_acceso: Optional[datetime] = _a_fecha(fila["ultimo_acceso"])
        self.version_sesion: int = fila["version_sesion"]
        self.fecha_creacion: Optional[datetime] = _a_fecha(fila["fecha_creacion"])

    def esta_bloqueado(self, ahora: datetime) -> bool:
        return self.bloqueado_hasta is not None and self.bloqueado_hasta > ahora


# --------------------------------------------------------------------------
# Usuarios
# --------------------------------------------------------------------------

def contar_usuarios() -> int:
    fila = get_db().execute("SELECT COUNT(*) AS total FROM usuarios").fetchone()
    return int(fila["total"])


def obtener_por_id(usuario_id: int) -> Optional[Usuario]:
    fila = get_db().execute(
        "SELECT * FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    return Usuario(fila) if fila else None


def obtener_por_usuario(usuario: str) -> Optional[Usuario]:
    fila = get_db().execute(
        "SELECT * FROM usuarios WHERE usuario = ? COLLATE NOCASE", (usuario,)
    ).fetchone()
    return Usuario(fila) if fila else None


def listar_con_codigo_recuperacion() -> list:
    filas = get_db().execute(
        "SELECT * FROM usuarios WHERE activo = 1 AND recovery_code_hash IS NOT NULL "
        "AND recovery_code_used = 0"
    ).fetchall()
    return [Usuario(f) for f in filas]


def listar_con_codigo_usado() -> list:
    filas = get_db().execute(
        "SELECT * FROM usuarios WHERE recovery_code_hash IS NOT NULL AND recovery_code_used = 1"
    ).fetchall()
    return [Usuario(f) for f in filas]


def crear(usuario: str, nombre: str, password_hash: str, recovery_code_hash: str) -> Usuario:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO usuarios (usuario, nombre, password_hash, recovery_code_hash) "
        "VALUES (?, ?, ?, ?)",
        (usuario, nombre, password_hash, recovery_code_hash),
    )
    return obtener_por_id(cursor.lastrowid)


def registrar_intento_fallido(usuario_id: int, bloqueado_hasta: Optional[datetime]) -> int:
    db = get_db()
    db.execute(
        "UPDATE usuarios SET intentos_fallidos = intentos_fallidos + 1, "
        "bloqueado_hasta = COALESCE(?, bloqueado_hasta) WHERE id = ?",
        (_a_texto(bloqueado_hasta), usuario_id),
    )
    fila = db.execute(
        "SELECT intentos_fallidos FROM usuarios WHERE id = ?", (usuario_id,)
    ).fetchone()
    return int(fila["intentos_fallidos"])


def bloquear_hasta(usuario_id: int, hasta: datetime) -> None:
    get_db().execute(
        "UPDATE usuarios SET bloqueado_hasta = ? WHERE id = ?",
        (_a_texto(hasta), usuario_id),
    )


def registrar_acceso_correcto(usuario_id: int, ahora: datetime) -> None:
    get_db().execute(
        "UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, "
        "ultimo_acceso = ? WHERE id = ?",
        (_a_texto(ahora), usuario_id),
    )


def actualizar_password(usuario_id: int, password_hash: str) -> None:
    """Cambia el hash de contraseña e invalida las sesiones existentes."""
    get_db().execute(
        "UPDATE usuarios SET password_hash = ?, version_sesion = version_sesion + 1, "
        "intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = ?",
        (password_hash, usuario_id),
    )


def marcar_codigo_recuperacion_usado(usuario_id: int) -> None:
    get_db().execute(
        "UPDATE usuarios SET recovery_code_used = 1 WHERE id = ?", (usuario_id,)
    )


def establecer_codigo_recuperacion(usuario_id: int, recovery_code_hash: str) -> None:
    get_db().execute(
        "UPDATE usuarios SET recovery_code_hash = ?, recovery_code_used = 0 WHERE id = ?",
        (recovery_code_hash, usuario_id),
    )


def invalidar_sesiones(usuario_id: int) -> None:
    get_db().execute(
        "UPDATE usuarios SET version_sesion = version_sesion + 1 WHERE id = ?",
        (usuario_id,),
    )


# --------------------------------------------------------------------------
# Auditoría de seguridad
# --------------------------------------------------------------------------

def registrar_evento(usuario_id: Optional[int], evento: str, detalle: Optional[str] = None) -> None:
    get_db().execute(
        "INSERT INTO auditoria_seguridad (usuario_id, evento, detalle) VALUES (?, ?, ?)",
        (usuario_id, evento, detalle),
    )


def listar_eventos(usuario_id: int, limite: int = 20) -> list:
    return get_db().execute(
        "SELECT evento, detalle, fecha FROM auditoria_seguridad "
        "WHERE usuario_id = ? ORDER BY fecha DESC, id DESC LIMIT ?",
        (usuario_id, limite),
    ).fetchall()


# --------------------------------------------------------------------------
# Configuración por usuario
# --------------------------------------------------------------------------

def obtener_configuracion(usuario_id: int, clave: str) -> Optional[str]:
    fila = get_db().execute(
        "SELECT valor FROM configuracion_usuario WHERE usuario_id = ? AND clave = ?",
        (usuario_id, clave),
    ).fetchone()
    return fila["valor"] if fila else None


def guardar_configuracion(usuario_id: int, clave: str, valor: str) -> None:
    get_db().execute(
        "INSERT INTO configuracion_usuario (usuario_id, clave, valor) VALUES (?, ?, ?) "
        "ON CONFLICT(usuario_id, clave) DO UPDATE SET valor = excluded.valor",
        (usuario_id, clave, valor),
    )


# --------------------------------------------------------------------------
# Estado interno de la aplicación
# --------------------------------------------------------------------------

def obtener_estado(clave: str) -> Optional[str]:
    fila = get_db().execute(
        "SELECT valor FROM estado_aplicacion WHERE clave = ?", (clave,)
    ).fetchone()
    return fila["valor"] if fila else None


def guardar_estado(clave: str, valor: Optional[str]) -> None:
    get_db().execute(
        "INSERT INTO estado_aplicacion (clave, valor) VALUES (?, ?) "
        "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor",
        (clave, valor),
    )

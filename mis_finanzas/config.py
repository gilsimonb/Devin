"""Configuración centralizada de Mis Finanzas.

Toda la aplicación funciona de manera local. No existen credenciales ni
claves escritas en el código: la clave secreta de Flask se genera la primera
vez que se ejecuta la aplicación y se guarda en ``instance/secret_key``.
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DATABASE_DIR = BASE_DIR / "database"
BACKUPS_DIR = BASE_DIR / "backups"


def _cargar_secret_key() -> str:
    """Devuelve la clave secreta local, creándola si todavía no existe."""
    variable = os.environ.get("MIS_FINANZAS_SECRET_KEY")
    if variable:
        return variable

    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    ruta = INSTANCE_DIR / "secret_key"
    if ruta.exists():
        return ruta.read_text(encoding="utf-8").strip()

    clave = secrets.token_hex(32)
    ruta.write_text(clave, encoding="utf-8")
    try:
        os.chmod(ruta, 0o600)
    except OSError:
        pass
    return clave


class Config:
    APP_NAME = "Mis Finanzas"
    APP_SUBTITULO = "Tu dinero, en orden"
    APP_VERSION = "0.1.0"

    HOST = "127.0.0.1"
    PORT = 5000
    DEBUG = False

    SECRET_KEY = _cargar_secret_key()

    DATABASE_PATH = Path(
        os.environ.get("MIS_FINANZAS_DB", DATABASE_DIR / "finanzas.db")
    )
    BACKUPS_PATH = BACKUPS_DIR

    # Cookies de sesión
    SESSION_COOKIE_NAME = "mis_finanzas_sesion"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False  # HTTP local (127.0.0.1)

    # Cookie que recuerda únicamente el nombre de usuario (nunca la contraseña)
    REMEMBER_USER_COOKIE = "mis_finanzas_usuario"
    REMEMBER_USER_DAYS = 30

    # Reglas de contraseña
    PASSWORD_MIN_LENGTH = 10

    # Protección contra intentos fallidos
    MAX_INTENTOS_FALLIDOS = 5
    BLOQUEO_MINUTOS = 5

    # Protección de la recuperación de acceso
    MAX_INTENTOS_RECUPERACION = 5
    BLOQUEO_RECUPERACION_MINUTOS = 15

    # Bloqueo automático por inactividad (valor predeterminado, configurable
    # desde Configuración → Seguridad)
    INACTIVIDAD_MINUTOS_DEFAULT = 30
    INACTIVIDAD_OPCIONES = (5, 10, 15, 30, 60)
    # Segundos de aviso antes del bloqueo automático
    INACTIVIDAD_AVISO_SEGUNDOS = 60

    # Límite de tamaño para restaurar respaldos (50 MB)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024


class TestConfig(Config):
    """Configuración para pruebas automatizadas (la ruta de la BD se
    sobreescribe en cada prueba con un archivo temporal)."""

    TESTING = True
    SECRET_KEY = "clave-solo-para-pruebas"
    BLOQUEO_MINUTOS = 5

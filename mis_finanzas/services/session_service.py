"""Gestión de la sesión de Flask, CSRF y protección de rutas privadas.

La sesión sólo guarda identificadores y marcas de tiempo. Nunca contiene
contraseñas, códigos de recuperación ni información financiera.
"""

import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional
from urllib.parse import urlparse

from flask import abort, current_app, g, redirect, request, session, url_for

from models import usuario as modelo
from services import auth_service

_K_USUARIO = "usuario_id"
_K_VERSION = "version_sesion"
_K_BLOQUEADA = "bloqueada"
_K_ACTIVIDAD = "ultima_actividad"
_K_RETORNO = "ruta_retorno"
_K_CSRF = "csrf_token"
_K_CODIGO_TOKEN = "codigo_token"

FORMATO = "%Y-%m-%dT%H:%M:%S"


# --------------------------------------------------------------------------
# Almacén temporal en memoria para el código de recuperación (se muestra una
# sola vez y nunca viaja en la cookie de sesión).
# --------------------------------------------------------------------------

class AlmacenTemporal:
    def __init__(self, segundos: int = 600):
        self._datos = {}
        self._segundos = segundos
        self._lock = threading.Lock()

    def guardar(self, valor: str) -> str:
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._limpiar()
            self._datos[token] = (valor, time.monotonic() + self._segundos)
        return token

    def leer(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        with self._lock:
            self._limpiar()
            entrada = self._datos.get(token)
        return entrada[0] if entrada else None

    def eliminar(self, token: Optional[str]) -> None:
        if token:
            with self._lock:
                self._datos.pop(token, None)

    def _limpiar(self) -> None:
        ahora = time.monotonic()
        caducados = [k for k, (_, exp) in self._datos.items() if exp < ahora]
        for k in caducados:
            del self._datos[k]


_codigos_pendientes = AlmacenTemporal()


def guardar_codigo_pendiente(codigo: str) -> None:
    session[_K_CODIGO_TOKEN] = _codigos_pendientes.guardar(codigo)


def leer_codigo_pendiente() -> Optional[str]:
    return _codigos_pendientes.leer(session.get(_K_CODIGO_TOKEN))


def descartar_codigo_pendiente() -> None:
    _codigos_pendientes.eliminar(session.pop(_K_CODIGO_TOKEN, None))


# --------------------------------------------------------------------------
# CSRF
# --------------------------------------------------------------------------

def csrf_token() -> str:
    token = session.get(_K_CSRF)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_K_CSRF] = token
    return token


def validar_csrf() -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    esperado = session.get(_K_CSRF)
    recibido = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not esperado or not recibido or not hmac.compare_digest(esperado, recibido):
        abort(400, description="La solicitud no es válida. Recarga la página e inténtalo de nuevo.")


# --------------------------------------------------------------------------
# Ciclo de vida de la sesión
# --------------------------------------------------------------------------

def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def iniciar_sesion(cuenta: modelo.Usuario) -> None:
    csrf = session.get(_K_CSRF)
    session.clear()
    if csrf:
        session[_K_CSRF] = csrf
    session[_K_USUARIO] = cuenta.id
    session[_K_VERSION] = cuenta.version_sesion
    session[_K_BLOQUEADA] = False
    session[_K_ACTIVIDAD] = _ahora().strftime(FORMATO)
    session.permanent = False
    g.usuario_actual = cuenta


def cerrar_sesion() -> None:
    descartar_codigo_pendiente()
    session.clear()
    g.usuario_actual = None


def esta_bloqueada() -> bool:
    return bool(session.get(_K_BLOQUEADA))


def bloquear(ruta_retorno: Optional[str] = None) -> None:
    session[_K_BLOQUEADA] = True
    if ruta_retorno and es_ruta_local(ruta_retorno):
        session[_K_RETORNO] = ruta_retorno


def desbloquear() -> str:
    session[_K_BLOQUEADA] = False
    session[_K_ACTIVIDAD] = _ahora().strftime(FORMATO)
    destino = session.pop(_K_RETORNO, None)
    return destino if destino and es_ruta_local(destino) else url_for("main.inicio")


def es_ruta_local(ruta: str) -> bool:
    if not ruta or not ruta.startswith("/") or ruta.startswith("//"):
        return False
    return urlparse(ruta).netloc == ""


def usuario_actual() -> Optional[modelo.Usuario]:
    return getattr(g, "usuario_actual", None)


def cargar_usuario_actual() -> Optional[modelo.Usuario]:
    """Carga el usuario de la sesión y verifica que ésta siga siendo válida.

    Devuelve ``None`` (y limpia la sesión) si el usuario no existe, está
    inactivo o la versión de sesión cambió (contraseña cambiada/recuperada).
    """
    g.usuario_actual = None
    g.sesion_invalidada = False
    usuario_id = session.get(_K_USUARIO)
    if usuario_id is None:
        return None
    cuenta = modelo.obtener_por_id(int(usuario_id))
    if cuenta is None or not cuenta.activo or cuenta.version_sesion != session.get(_K_VERSION):
        cerrar_sesion()
        g.sesion_invalidada = True
        return None

    minutos = auth_service.obtener_inactividad_minutos(cuenta.id)
    ultima = session.get(_K_ACTIVIDAD)
    if ultima:
        try:
            momento = datetime.strptime(ultima, FORMATO)
        except ValueError:
            momento = None
        if momento and _ahora() - momento > timedelta(minutes=minutos):
            auth_service.registrar_sesion_expirada(cuenta.id)
            cerrar_sesion()
            g.sesion_expirada = True
            return None

    session[_K_ACTIVIDAD] = _ahora().strftime(FORMATO)
    g.usuario_actual = cuenta
    g.inactividad_minutos = minutos
    return cuenta


# --------------------------------------------------------------------------
# Decoradores
# --------------------------------------------------------------------------

def login_required(vista):
    """Exige sesión válida. Si la aplicación está bloqueada, envía a /bloquear."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is None:
            if getattr(g, "sesion_expirada", False):
                return redirect(url_for("auth.sesion_expirada"))
            return redirect(url_for("auth.login"))
        if esta_bloqueada():
            if request.method == "GET":
                session[_K_RETORNO] = request.full_path.rstrip("?")
            return redirect(url_for("auth.bloquear"))
        return vista(*args, **kwargs)

    return envoltura


def login_required_aunque_bloqueada(vista):
    """Exige sesión válida pero permite el acceso con la aplicación bloqueada
    (pantalla de bloqueo, desbloqueo y cierre de sesión)."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is None:
            if getattr(g, "sesion_expirada", False):
                return redirect(url_for("auth.sesion_expirada"))
            return redirect(url_for("auth.login"))
        return vista(*args, **kwargs)

    return envoltura


def solo_anonimos(vista):
    """Redirige a /inicio a los usuarios ya autenticados."""

    @wraps(vista)
    def envoltura(*args, **kwargs):
        if usuario_actual() is not None:
            if esta_bloqueada():
                return redirect(url_for("auth.bloquear"))
            return redirect(url_for("main.inicio"))
        return vista(*args, **kwargs)

    return envoltura


def sin_cache(respuesta):
    """Evita que las páginas privadas queden en la caché del navegador."""
    respuesta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    respuesta.headers["Pragma"] = "no-cache"
    respuesta.headers["Expires"] = "0"
    return respuesta


def cabeceras_seguridad(respuesta):
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "same-origin")
    respuesta.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'",
    )
    if not request.path.startswith(current_app.static_url_path or "/static"):
        sin_cache(respuesta)
    return respuesta

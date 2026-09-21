"""Lógica de autenticación y seguridad.

Este módulo no conoce la sesión de Flask ni las peticiones HTTP: recibe
datos ya extraídos de los formularios y devuelve resultados. Las rutas se
encargan de traducir esos resultados a redirecciones y mensajes.
"""

import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from flask import current_app
from werkzeug.security import check_password_hash, generate_password_hash

from models import usuario as modelo

# Eventos de auditoría
LOGIN_CORRECTO = "LOGIN_CORRECTO"
LOGIN_FALLIDO = "LOGIN_FALLIDO"
CUENTA_BLOQUEADA = "CUENTA_BLOQUEADA"
LOGOUT = "LOGOUT"
CAMBIO_PASSWORD = "CAMBIO_PASSWORD"
APLICACION_BLOQUEADA = "APLICACION_BLOQUEADA"
APLICACION_DESBLOQUEADA = "APLICACION_DESBLOQUEADA"
SESION_EXPIRADA = "SESION_EXPIRADA"
RECUPERACION_ACCESO = "RECUPERACION_ACCESO"
RECUPERACION_FALLIDA = "RECUPERACION_FALLIDA"
USUARIO_CREADO = "USUARIO_CREADO"
CODIGO_RECUPERACION_REGENERADO = "CODIGO_RECUPERACION_REGENERADO"
CONFIGURACION_ACTUALIZADA = "CONFIGURACION_ACTUALIZADA"
RESPALDO_CREADO = "RESPALDO_CREADO"
RESPALDO_RESTAURADO = "RESPALDO_RESTAURADO"
RESPALDO_RECHAZADO = "RESPALDO_RECHAZADO"

# Mensajes (siempre genéricos: no revelan si un usuario existe)
MSG_USUARIO_OBLIGATORIO = "El usuario es obligatorio."
MSG_PASSWORD_OBLIGATORIA = "La contraseña es obligatoria."
MSG_PASSWORDS_NO_COINCIDEN = "Las contraseñas no coinciden."
MSG_CREDENCIALES = "Usuario o contraseña incorrectos."
MSG_BLOQUEO_TEMPORAL = "No es posible iniciar sesión temporalmente. Intenta de nuevo más tarde."
MSG_SESION_EXPIRADA = "Tu sesión ha expirado."
MSG_PASSWORD_ACTUAL_INCORRECTA = "La contraseña actual es incorrecta."
MSG_CODIGO_INVALIDO = "El código de recuperación no es válido."
MSG_CODIGO_USADO = "El código de recuperación ya fue utilizado."
MSG_RECUPERACION_BLOQUEADA = "No es posible recuperar el acceso temporalmente. Intenta de nuevo más tarde."
MSG_USUARIO_EXISTE = "No es posible utilizar ese nombre de usuario."
MSG_PASSWORD_IGUAL_USUARIO = "La contraseña no puede ser igual al usuario."
MSG_PASSWORD_IGUAL_ANTERIOR = "La nueva contraseña debe ser diferente a la actual."

# Código de recuperación: 16 caracteres sin símbolos ambiguos (0/O, 1/I/L)
_ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_PATRON_USUARIO = re.compile(r"^[\w.\-@]{3,40}$", re.UNICODE)

CLAVE_INACTIVIDAD = "inactividad_minutos"
ESTADO_REC_INTENTOS = "recuperacion_intentos"
ESTADO_REC_BLOQUEO = "recuperacion_bloqueada_hasta"


@dataclass
class Resultado:
    ok: bool
    errores: List[str] = field(default_factory=list)
    usuario: Optional[modelo.Usuario] = None
    codigo_recuperacion: Optional[str] = None
    bloqueado: bool = False

    @classmethod
    def error(cls, *mensajes: str, **extra) -> "Resultado":
        return cls(ok=False, errores=list(mensajes), **extra)


def ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


# --------------------------------------------------------------------------
# Validaciones
# --------------------------------------------------------------------------

def _min_len() -> int:
    return int(current_app.config["PASSWORD_MIN_LENGTH"])


def validar_password(password: str, usuario: str = "") -> List[str]:
    errores = []
    if not password:
        errores.append(MSG_PASSWORD_OBLIGATORIA)
        return errores
    if len(password) < _min_len():
        errores.append(f"La contraseña debe tener al menos {_min_len()} caracteres.")
    if usuario and password.strip().lower() == usuario.strip().lower():
        errores.append(MSG_PASSWORD_IGUAL_USUARIO)
    return errores


def validar_confirmacion(password: str, confirmacion: str) -> List[str]:
    if not confirmacion:
        return ["Confirma la contraseña."]
    if password != confirmacion:
        return [MSG_PASSWORDS_NO_COINCIDEN]
    return []


def normalizar_usuario(usuario: Optional[str]) -> str:
    return (usuario or "").strip()


def normalizar_codigo(codigo: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (codigo or "").upper())


def formatear_codigo(codigo: str) -> str:
    return "-".join(codigo[i:i + 4] for i in range(0, len(codigo), 4))


def generar_codigo_recuperacion() -> str:
    bruto = "".join(secrets.choice(_ALFABETO_CODIGO) for _ in range(16))
    return formatear_codigo(bruto)


# --------------------------------------------------------------------------
# Primera ejecución / creación de usuario
# --------------------------------------------------------------------------

def existen_usuarios() -> bool:
    return modelo.contar_usuarios() > 0


def crear_usuario(usuario: str, nombre: str, password: str, confirmacion: str) -> Resultado:
    usuario = normalizar_usuario(usuario)
    nombre = (nombre or "").strip()
    errores: List[str] = []

    if not usuario:
        errores.append(MSG_USUARIO_OBLIGATORIO)
    elif not _PATRON_USUARIO.match(usuario):
        errores.append(
            "El usuario debe tener entre 3 y 40 caracteres (letras, números, punto, guion, @ o _)."
        )
    if not nombre:
        errores.append("El nombre es obligatorio.")
    elif len(nombre) > 80:
        errores.append("El nombre es demasiado largo.")

    errores += validar_password(password, usuario)
    if password:
        errores += validar_confirmacion(password, confirmacion)
    if errores:
        return Resultado.error(*errores)

    if modelo.obtener_por_usuario(usuario) is not None:
        return Resultado.error(MSG_USUARIO_EXISTE)

    codigo = generar_codigo_recuperacion()
    nuevo = modelo.crear(
        usuario=usuario,
        nombre=nombre,
        password_hash=generate_password_hash(password),
        recovery_code_hash=generate_password_hash(normalizar_codigo(codigo)),
    )
    modelo.guardar_configuracion(
        nuevo.id, CLAVE_INACTIVIDAD, str(current_app.config["INACTIVIDAD_MINUTOS_DEFAULT"])
    )
    modelo.registrar_evento(nuevo.id, USUARIO_CREADO)
    return Resultado(ok=True, usuario=nuevo, codigo_recuperacion=codigo)


# --------------------------------------------------------------------------
# Inicio de sesión
# --------------------------------------------------------------------------

def _fallo_generico(password_ficticio: bool = True) -> Resultado:
    # Igualar tiempos de respuesta cuando el usuario no existe.
    if password_ficticio:
        check_password_hash(generate_password_hash("relleno-constante"), "otro")
    return Resultado.error(MSG_CREDENCIALES)


def autenticar(usuario: str, password: str) -> Resultado:
    """Verifica credenciales aplicando la protección contra intentos fallidos."""
    usuario = normalizar_usuario(usuario)
    errores = []
    if not usuario:
        errores.append(MSG_USUARIO_OBLIGATORIO)
    if not password:
        errores.append(MSG_PASSWORD_OBLIGATORIA)
    if errores:
        return Resultado.error(*errores)

    cuenta = modelo.obtener_por_usuario(usuario)
    if cuenta is None or not cuenta.activo:
        modelo.registrar_evento(None, LOGIN_FALLIDO, "usuario desconocido")
        return _fallo_generico()

    momento = ahora()
    if cuenta.esta_bloqueado(momento):
        modelo.registrar_evento(cuenta.id, LOGIN_FALLIDO, "cuenta bloqueada temporalmente")
        return Resultado.error(MSG_BLOQUEO_TEMPORAL, bloqueado=True)

    if not check_password_hash(cuenta.password_hash, password):
        maximo = int(current_app.config["MAX_INTENTOS_FALLIDOS"])
        intentos = modelo.registrar_intento_fallido(cuenta.id, None)
        modelo.registrar_evento(cuenta.id, LOGIN_FALLIDO, f"intento {intentos} de {maximo}")
        if intentos >= maximo:
            hasta = momento + timedelta(minutes=int(current_app.config["BLOQUEO_MINUTOS"]))
            modelo.bloquear_hasta(cuenta.id, hasta)
            modelo.registrar_evento(
                cuenta.id, CUENTA_BLOQUEADA, f"hasta {hasta.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return Resultado.error(MSG_BLOQUEO_TEMPORAL, bloqueado=True)
        return Resultado.error(MSG_CREDENCIALES)

    modelo.registrar_acceso_correcto(cuenta.id, momento)
    modelo.registrar_evento(cuenta.id, LOGIN_CORRECTO)
    return Resultado(ok=True, usuario=modelo.obtener_por_id(cuenta.id))


def verificar_password(cuenta: modelo.Usuario, password: str) -> bool:
    """Comprueba la contraseña de un usuario ya autenticado (desbloqueo,
    cambio de contraseña, operaciones sensibles). No cuenta como intento de
    login, pero sí se audita cuando falla."""
    if not password or not check_password_hash(cuenta.password_hash, password):
        return False
    return True


# --------------------------------------------------------------------------
# Bloqueo / desbloqueo / cierre de sesión
# --------------------------------------------------------------------------

def registrar_bloqueo(usuario_id: int, motivo: str = "manual") -> None:
    modelo.registrar_evento(usuario_id, APLICACION_BLOQUEADA, motivo)


def desbloquear(cuenta: modelo.Usuario, password: str) -> Resultado:
    if not password:
        return Resultado.error(MSG_PASSWORD_OBLIGATORIA)
    if not verificar_password(cuenta, password):
        modelo.registrar_evento(cuenta.id, LOGIN_FALLIDO, "desbloqueo")
        return Resultado.error("Contraseña incorrecta.")
    modelo.registrar_evento(cuenta.id, APLICACION_DESBLOQUEADA)
    return Resultado(ok=True, usuario=cuenta)


def registrar_logout(usuario_id: int) -> None:
    modelo.registrar_evento(usuario_id, LOGOUT)


def registrar_sesion_expirada(usuario_id: int) -> None:
    modelo.registrar_evento(usuario_id, SESION_EXPIRADA, "inactividad")


# --------------------------------------------------------------------------
# Cambio de contraseña
# --------------------------------------------------------------------------

def cambiar_password(cuenta: modelo.Usuario, actual: str, nueva: str, confirmacion: str) -> Resultado:
    errores: List[str] = []
    if not actual:
        errores.append("La contraseña actual es obligatoria.")
    errores += validar_password(nueva, cuenta.usuario)
    if nueva:
        errores += validar_confirmacion(nueva, confirmacion)
    if errores:
        return Resultado.error(*errores)

    if not verificar_password(cuenta, actual):
        modelo.registrar_evento(cuenta.id, LOGIN_FALLIDO, "cambio de contraseña")
        return Resultado.error(MSG_PASSWORD_ACTUAL_INCORRECTA)
    if actual == nueva:
        return Resultado.error(MSG_PASSWORD_IGUAL_ANTERIOR)

    modelo.actualizar_password(cuenta.id, generate_password_hash(nueva))
    modelo.registrar_evento(cuenta.id, CAMBIO_PASSWORD)
    return Resultado(ok=True, usuario=modelo.obtener_por_id(cuenta.id))


# --------------------------------------------------------------------------
# Recuperación de acceso mediante código local
# --------------------------------------------------------------------------

def _recuperacion_bloqueada(momento: datetime) -> bool:
    hasta = modelo.obtener_estado(ESTADO_REC_BLOQUEO)
    if not hasta:
        return False
    return datetime.strptime(hasta, modelo.FORMATO_FECHA) > momento


def _registrar_recuperacion_fallida(momento: datetime, usuario_id: Optional[int], detalle: str) -> None:
    intentos = int(modelo.obtener_estado(ESTADO_REC_INTENTOS) or 0) + 1
    modelo.guardar_estado(ESTADO_REC_INTENTOS, str(intentos))
    modelo.registrar_evento(usuario_id, RECUPERACION_FALLIDA, detalle)
    if intentos >= int(current_app.config["MAX_INTENTOS_RECUPERACION"]):
        hasta = momento + timedelta(minutes=int(current_app.config["BLOQUEO_RECUPERACION_MINUTOS"]))
        modelo.guardar_estado(ESTADO_REC_BLOQUEO, hasta.strftime(modelo.FORMATO_FECHA))
        modelo.guardar_estado(ESTADO_REC_INTENTOS, "0")
        modelo.registrar_evento(usuario_id, CUENTA_BLOQUEADA, "recuperación de acceso")


def recuperar_acceso(codigo: str, nueva: str, confirmacion: str) -> Resultado:
    codigo_normalizado = normalizar_codigo(codigo)
    errores: List[str] = []
    if not codigo_normalizado:
        errores.append("El código de recuperación es obligatorio.")
    errores += validar_password(nueva)
    if nueva:
        errores += validar_confirmacion(nueva, confirmacion)
    if errores:
        return Resultado.error(*errores)

    momento = ahora()
    if _recuperacion_bloqueada(momento):
        return Resultado.error(MSG_RECUPERACION_BLOQUEADA, bloqueado=True)

    # La aplicación es local y tiene muy pocos usuarios: se compara el código
    # contra los hashes vigentes. Nunca se guarda el código en texto plano.
    for cuenta in modelo.listar_con_codigo_recuperacion():
        if check_password_hash(cuenta.recovery_code_hash, codigo_normalizado):
            if validar_password(nueva, cuenta.usuario):
                return Resultado.error(MSG_PASSWORD_IGUAL_USUARIO)
            modelo.marcar_codigo_recuperacion_usado(cuenta.id)
            modelo.actualizar_password(cuenta.id, generate_password_hash(nueva))
            modelo.guardar_estado(ESTADO_REC_INTENTOS, "0")
            modelo.registrar_evento(cuenta.id, RECUPERACION_ACCESO)
            return Resultado(ok=True, usuario=modelo.obtener_por_id(cuenta.id))

    # Código ya utilizado: mensaje específico (no revela usuarios, sólo el
    # estado del código que el propio usuario introdujo).
    for cuenta in modelo.listar_con_codigo_usado():
        if check_password_hash(cuenta.recovery_code_hash, codigo_normalizado):
            _registrar_recuperacion_fallida(momento, cuenta.id, "código ya utilizado")
            return Resultado.error(MSG_CODIGO_USADO)

    _registrar_recuperacion_fallida(momento, None, "código inválido")
    return Resultado.error(MSG_CODIGO_INVALIDO)


def regenerar_codigo_recuperacion(cuenta: modelo.Usuario, password: str) -> Resultado:
    if not verificar_password(cuenta, password):
        modelo.registrar_evento(cuenta.id, LOGIN_FALLIDO, "regenerar código")
        return Resultado.error(MSG_PASSWORD_ACTUAL_INCORRECTA)
    codigo = generar_codigo_recuperacion()
    modelo.establecer_codigo_recuperacion(
        cuenta.id, generate_password_hash(normalizar_codigo(codigo))
    )
    modelo.registrar_evento(cuenta.id, CODIGO_RECUPERACION_REGENERADO)
    return Resultado(ok=True, usuario=cuenta, codigo_recuperacion=codigo)


# --------------------------------------------------------------------------
# Configuración de seguridad
# --------------------------------------------------------------------------

def obtener_inactividad_minutos(usuario_id: int) -> int:
    valor = modelo.obtener_configuracion(usuario_id, CLAVE_INACTIVIDAD)
    try:
        minutos = int(valor)
    except (TypeError, ValueError):
        minutos = int(current_app.config["INACTIVIDAD_MINUTOS_DEFAULT"])
    return minutos if minutos > 0 else int(current_app.config["INACTIVIDAD_MINUTOS_DEFAULT"])


def guardar_inactividad_minutos(usuario_id: int, valor: str) -> Resultado:
    try:
        minutos = int(valor)
    except (TypeError, ValueError):
        return Resultado.error("El tiempo de inactividad no es válido.")
    if minutos not in current_app.config["INACTIVIDAD_OPCIONES"]:
        return Resultado.error("El tiempo de inactividad no es válido.")
    modelo.guardar_configuracion(usuario_id, CLAVE_INACTIVIDAD, str(minutos))
    modelo.registrar_evento(usuario_id, CONFIGURACION_ACTUALIZADA, f"inactividad={minutos} min")
    return Resultado(ok=True)

"""Rutas de autenticación y seguridad."""

from datetime import timedelta
from urllib.parse import urlparse

from flask import (
    Blueprint,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from services import auth_service, session_service
from services.session_service import (
    login_required,
    login_required_aunque_bloqueada,
    solo_anonimos,
)

auth_bp = Blueprint("auth", __name__)


def _flash_errores(resultado: auth_service.Resultado) -> None:
    for mensaje in resultado.errores:
        flash(mensaje, "error")


def _ruta_referencia() -> str:
    referencia = urlparse(request.referrer or "")
    ruta = referencia.path or ""
    if referencia.query:
        ruta += "?" + referencia.query
    return ruta


# --------------------------------------------------------------------------
# Raíz / primera ejecución
# --------------------------------------------------------------------------

@auth_bp.route("/")
def raiz():
    if not auth_service.existen_usuarios():
        return redirect(url_for("auth.crear_usuario"))
    if session_service.usuario_actual() is not None:
        if session_service.esta_bloqueada():
            return redirect(url_for("auth.bloquear"))
        return redirect(url_for("main.inicio"))
    return redirect(url_for("auth.login"))


@auth_bp.route("/crear-usuario", methods=["GET", "POST"])
def crear_usuario():
    if auth_service.existen_usuarios():
        flash("Ya existe un usuario configurado. Inicia sesión.", "info")
        return redirect(url_for("auth.login"))

    valores = {"usuario": "", "nombre": ""}
    if request.method == "POST":
        valores["usuario"] = auth_service.normalizar_usuario(request.form.get("usuario"))
        valores["nombre"] = (request.form.get("nombre") or "").strip()
        resultado = auth_service.crear_usuario(
            valores["usuario"],
            valores["nombre"],
            request.form.get("password") or "",
            request.form.get("confirmar_password") or "",
        )
        if resultado.ok:
            session_service.guardar_codigo_pendiente(resultado.codigo_recuperacion)
            return redirect(url_for("auth.codigo_recuperacion"))
        _flash_errores(resultado)

    return render_template(
        "crear_usuario.html",
        valores=valores,
        min_password=current_app.config["PASSWORD_MIN_LENGTH"],
    )


@auth_bp.route("/codigo-recuperacion")
def codigo_recuperacion():
    codigo = session_service.leer_codigo_pendiente()
    if not codigo:
        return redirect(url_for("auth.raiz"))
    return render_template("codigo_recuperacion.html", codigo=codigo)


@auth_bp.route("/codigo-recuperacion/continuar", methods=["POST"])
def codigo_recuperacion_continuar():
    session_service.descartar_codigo_pendiente()
    if session_service.usuario_actual() is not None:
        return redirect(url_for("main.configuracion_seguridad"))
    flash("Tu cuenta fue creada. Inicia sesión para continuar.", "success")
    return redirect(url_for("auth.login"))


# --------------------------------------------------------------------------
# Inicio y cierre de sesión
# --------------------------------------------------------------------------

@auth_bp.route("/login", methods=["GET", "POST"])
@solo_anonimos
def login():
    if not auth_service.existen_usuarios():
        return redirect(url_for("auth.crear_usuario"))

    cookie_usuario = current_app.config["REMEMBER_USER_COOKIE"]
    usuario_recordado = request.cookies.get(cookie_usuario, "")
    valores = {"usuario": usuario_recordado, "recordar": bool(usuario_recordado)}

    if request.method == "POST":
        valores["usuario"] = auth_service.normalizar_usuario(request.form.get("usuario"))
        valores["recordar"] = request.form.get("recordar") == "1"
        resultado = auth_service.autenticar(valores["usuario"], request.form.get("password") or "")

        if resultado.ok:
            session_service.iniciar_sesion(resultado.usuario)
            respuesta = make_response(redirect(url_for("main.inicio")))
            if valores["recordar"]:
                respuesta.set_cookie(
                    cookie_usuario,
                    resultado.usuario.usuario,
                    max_age=int(timedelta(days=current_app.config["REMEMBER_USER_DAYS"]).total_seconds()),
                    httponly=True,
                    samesite="Lax",
                    secure=current_app.config["SESSION_COOKIE_SECURE"],
                )
            else:
                respuesta.delete_cookie(cookie_usuario)
            return respuesta

        _flash_errores(resultado)

    return render_template("login.html", valores=valores)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    cuenta = session_service.usuario_actual()
    if cuenta is not None:
        auth_service.registrar_logout(cuenta.id)
    session_service.cerrar_sesion()
    flash("Cerraste sesión correctamente.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/sesion-expirada")
def sesion_expirada():
    if session_service.usuario_actual() is not None:
        return redirect(url_for("main.inicio"))
    return render_template("sesion_expirada.html")


# --------------------------------------------------------------------------
# Bloqueo / desbloqueo
# --------------------------------------------------------------------------

@auth_bp.route("/bloquear", methods=["GET", "POST"])
@login_required_aunque_bloqueada
def bloquear():
    cuenta = session_service.usuario_actual()
    if request.method == "POST":
        if not session_service.esta_bloqueada():
            motivo = "inactividad" if request.form.get("motivo") == "inactividad" else "manual"
            session_service.bloquear(request.form.get("retorno") or _ruta_referencia())
            auth_service.registrar_bloqueo(cuenta.id, motivo)
        return redirect(url_for("auth.bloquear"))

    if not session_service.esta_bloqueada():
        return redirect(url_for("main.inicio"))
    return render_template("bloqueo.html", cuenta=cuenta)


@auth_bp.route("/desbloquear", methods=["POST"])
@login_required_aunque_bloqueada
def desbloquear():
    cuenta = session_service.usuario_actual()
    if not session_service.esta_bloqueada():
        return redirect(url_for("main.inicio"))
    resultado = auth_service.desbloquear(cuenta, request.form.get("password") or "")
    if resultado.ok:
        destino = session_service.desbloquear()
        return redirect(destino)
    _flash_errores(resultado)
    return redirect(url_for("auth.bloquear"))


# --------------------------------------------------------------------------
# Cambio de contraseña
# --------------------------------------------------------------------------

@auth_bp.route("/cambiar-password", methods=["GET", "POST"])
@login_required
def cambiar_password():
    cuenta = session_service.usuario_actual()
    if request.method == "POST":
        resultado = auth_service.cambiar_password(
            cuenta,
            request.form.get("password_actual") or "",
            request.form.get("password_nueva") or "",
            request.form.get("confirmar_password") or "",
        )
        if resultado.ok:
            session_service.cerrar_sesion()
            flash("Tu contraseña fue actualizada. Inicia sesión nuevamente.", "success")
            return redirect(url_for("auth.login"))
        _flash_errores(resultado)
    return render_template(
        "cambiar_password.html",
        seccion="configuracion",
        min_password=current_app.config["PASSWORD_MIN_LENGTH"],
    )


# --------------------------------------------------------------------------
# Recuperación de acceso
# --------------------------------------------------------------------------

@auth_bp.route("/recuperar-acceso", methods=["GET", "POST"])
@solo_anonimos
def recuperar_acceso():
    if not auth_service.existen_usuarios():
        return redirect(url_for("auth.crear_usuario"))

    if request.method == "POST":
        resultado = auth_service.recuperar_acceso(
            request.form.get("codigo") or "",
            request.form.get("password_nueva") or "",
            request.form.get("confirmar_password") or "",
        )
        if resultado.ok:
            session.clear()
            flash("La contraseña fue actualizada correctamente. Inicia sesión nuevamente.", "success")
            return redirect(url_for("auth.login"))
        _flash_errores(resultado)

    return render_template(
        "recuperar_acceso.html",
        min_password=current_app.config["PASSWORD_MIN_LENGTH"],
    )

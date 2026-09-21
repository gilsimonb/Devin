"""Rutas privadas: pantalla de inicio y configuración."""

import tempfile
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from models import usuario as modelo
from services import auth_service, backup_service, session_service
from services.session_service import login_required

main_bp = Blueprint("main", __name__)

# Estructura de navegación preparada para los módulos financieros futuros.
MODULOS = [
    {"clave": "inicio", "nombre": "Inicio", "icono": "home", "endpoint": "main.inicio", "disponible": True},
    {"clave": "cuentas", "nombre": "Mis cuentas", "icono": "bank", "disponible": False,
     "hijos": ["Bancos", "Efectivo", "Cuentas digitales"]},
    {"clave": "tarjetas", "nombre": "Tarjetas", "icono": "card", "disponible": False},
    {"clave": "inversiones", "nombre": "Inversiones", "icono": "chart", "disponible": False,
     "hijos": ["CETES", "Fintual", "BRIQ", "SOFIPOs", "Otros"]},
    {"clave": "movimientos", "nombre": "Movimientos", "icono": "swap", "disponible": False},
    {"clave": "metas", "nombre": "Metas", "icono": "target", "disponible": False},
    {"clave": "calendario", "nombre": "Calendario", "icono": "calendar", "disponible": False},
    {"clave": "reportes", "nombre": "Reportes", "icono": "report", "disponible": False},
    {"clave": "configuracion", "nombre": "Configuración", "icono": "settings",
     "endpoint": "main.configuracion_seguridad", "disponible": True},
]


@main_bp.context_processor
def _modulos():
    return {"MODULOS": MODULOS}


@main_bp.route("/inicio")
@login_required
def inicio():
    cuenta = session_service.usuario_actual()
    return render_template("inicio.html", cuenta=cuenta, seccion="inicio")


# --------------------------------------------------------------------------
# Configuración → Seguridad
# --------------------------------------------------------------------------

@main_bp.route("/configuracion")
@login_required
def configuracion():
    return redirect(url_for("main.configuracion_seguridad"))


@main_bp.route("/configuracion/seguridad")
@login_required
def configuracion_seguridad():
    cuenta = session_service.usuario_actual()
    return render_template(
        "configuracion_seguridad.html",
        cuenta=cuenta,
        seccion="configuracion",
        inactividad_actual=auth_service.obtener_inactividad_minutos(cuenta.id),
        inactividad_opciones=current_app.config["INACTIVIDAD_OPCIONES"],
        eventos=modelo.listar_eventos(cuenta.id, limite=15),
        respaldos=backup_service.listar_respaldos()[:10],
        ruta_db=str(current_app.config["DATABASE_PATH"]),
        ruta_backups=str(current_app.config["BACKUPS_PATH"]),
    )


@main_bp.route("/configuracion/inactividad", methods=["POST"])
@login_required
def configuracion_inactividad():
    cuenta = session_service.usuario_actual()
    resultado = auth_service.guardar_inactividad_minutos(cuenta.id, request.form.get("minutos"))
    if resultado.ok:
        flash("Tiempo de inactividad actualizado.", "success")
    else:
        for e in resultado.errores:
            flash(e, "error")
    return redirect(url_for("main.configuracion_seguridad"))


@main_bp.route("/configuracion/codigo-recuperacion", methods=["POST"])
@login_required
def regenerar_codigo():
    cuenta = session_service.usuario_actual()
    resultado = auth_service.regenerar_codigo_recuperacion(cuenta, request.form.get("password") or "")
    if resultado.ok:
        session_service.guardar_codigo_pendiente(resultado.codigo_recuperacion)
        return redirect(url_for("auth.codigo_recuperacion"))
    for e in resultado.errores:
        flash(e, "error")
    return redirect(url_for("main.configuracion_seguridad"))


# --------------------------------------------------------------------------
# Respaldos locales
# --------------------------------------------------------------------------

@main_bp.route("/respaldos/crear", methods=["POST"])
@login_required
def crear_respaldo():
    cuenta = session_service.usuario_actual()
    try:
        respaldo = backup_service.crear_respaldo(cuenta.id)
    except OSError:
        flash("No fue posible crear el respaldo.", "error")
        return redirect(url_for("main.configuracion_seguridad"))
    flash(f"Respaldo creado: {respaldo.nombre}", "success")
    return redirect(url_for("main.configuracion_seguridad"))


@main_bp.route("/respaldos/<nombre>/descargar")
@login_required
def descargar_respaldo(nombre):
    directorio = Path(current_app.config["BACKUPS_PATH"]).resolve()
    ruta = (directorio / secure_filename(nombre)).resolve()
    if ruta.parent != directorio or not ruta.exists() or ruta.suffix != ".db":
        flash("El respaldo no existe.", "error")
        return redirect(url_for("main.configuracion_seguridad"))
    return send_file(ruta, as_attachment=True, download_name=ruta.name)


@main_bp.route("/respaldos/restaurar", methods=["POST"])
@login_required
def restaurar_respaldo():
    cuenta = session_service.usuario_actual()
    archivo = request.files.get("archivo")
    if archivo is None or not archivo.filename:
        flash("Selecciona un archivo de respaldo.", "error")
        return redirect(url_for("main.configuracion_seguridad"))
    if not auth_service.verificar_password(cuenta, request.form.get("password") or ""):
        modelo.registrar_evento(cuenta.id, auth_service.LOGIN_FALLIDO, "restaurar respaldo")
        flash(auth_service.MSG_PASSWORD_ACTUAL_INCORRECTA, "error")
        return redirect(url_for("main.configuracion_seguridad"))

    with tempfile.TemporaryDirectory() as temporal:
        ruta_temporal = Path(temporal) / "respaldo_subido.db"
        archivo.save(ruta_temporal)
        error = backup_service.restaurar_respaldo(cuenta.id, ruta_temporal, secure_filename(archivo.filename))

    if error:
        flash(error, "error")
        return redirect(url_for("main.configuracion_seguridad"))

    # Los datos cambiaron por completo: se cierra la sesión por seguridad.
    session_service.cerrar_sesion()
    flash("El respaldo se restauró correctamente. Inicia sesión nuevamente.", "success")
    return redirect(url_for("auth.login"))

"""Pruebas obligatorias de la primera etapa (sección 29 del proyecto)."""

import io
from datetime import datetime, timedelta

import pytest

from tests.conftest import (
    NOMBRE,
    PASSWORD,
    PASSWORD_NUEVA,
    PATRON_CODIGO,
    USUARIO,
    continuar_codigo,
    crear_app,
    crear_usuario,
    csrf_de,
    eventos,
    html,
    login,
    post,
)
from database.db import conectar
from services import session_service


# ==========================================================================
# Primera ejecución
# ==========================================================================

def test_sin_usuarios_redirige_a_crear_usuario(client):
    r = client.get("/")
    assert r.status_code == 302 and r.headers["Location"].endswith("/crear-usuario")
    r = client.get("/login")
    assert r.status_code == 302 and r.headers["Location"].endswith("/crear-usuario")
    pagina = html(client.get("/crear-usuario"))
    assert "Crear usuario local" in pagina
    assert "Mis Finanzas" in pagina and "Tu dinero, en orden" in pagina


def test_crear_usuario_genera_codigo_y_lo_muestra_una_sola_vez(client, app):
    codigo = crear_usuario(client)
    assert PATRON_CODIGO.fullmatch(codigo)

    # Sigue visible mientras no se confirma
    assert codigo in html(client.get("/codigo-recuperacion"))
    continuar_codigo(client)

    # Después de continuar ya no puede verse
    r = client.get("/codigo-recuperacion")
    assert r.status_code == 302
    assert codigo not in html(client.get("/login"))

    # En la BD sólo hay hashes; nunca el código ni la contraseña
    with conectar(app.config["DATABASE_PATH"]) as cx:
        fila = cx.execute("SELECT * FROM usuarios").fetchone()
        assert fila["usuario"] == USUARIO
        assert fila["nombre"] == NOMBRE
        assert PASSWORD not in fila["password_hash"]
        assert fila["password_hash"].startswith(("scrypt:", "pbkdf2:"))
        assert codigo.replace("-", "") not in fila["recovery_code_hash"]
        assert fila["recovery_code_used"] == 0
    assert len(eventos(app, "USUARIO_CREADO")) == 1


def test_crear_usuario_bloqueado_cuando_ya_existe(client, usuario_creado):
    r = client.get("/crear-usuario")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    r = client.post("/crear-usuario", data={"csrf_token": csrf_de(client, "/login"),
                                            "usuario": "otro", "nombre": "Otro",
                                            "password": "Contrasena123!", "confirmar_password": "Contrasena123!"})
    assert r.status_code == 302
    with conectar(client.application.config["DATABASE_PATH"]) as cx:
        assert cx.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 1


@pytest.mark.parametrize(
    "datos, mensaje",
    [
        ({"usuario": "   ", "nombre": "X", "password": "Contrasena123!", "confirmar_password": "Contrasena123!"},
         "El usuario es obligatorio."),
        ({"usuario": "ana", "nombre": "Ana", "password": "corta", "confirmar_password": "corta"},
         "La contraseña debe tener al menos 10 caracteres."),
        ({"usuario": "ana", "nombre": "Ana", "password": "Contrasena123!", "confirmar_password": "Otra"},
         "Las contraseñas no coinciden."),
        ({"usuario": "ana", "nombre": "Ana", "password": "", "confirmar_password": ""},
         "La contraseña es obligatoria."),
        ({"usuario": "MiUsuario123", "nombre": "Ana", "password": "MiUsuario123", "confirmar_password": "MiUsuario123"},
         "La contraseña no puede ser igual al usuario."),
    ],
)
def test_validaciones_crear_usuario(client, datos, mensaje):
    r = post(client, "/crear-usuario", "/crear-usuario", **datos)
    assert mensaje in html(r)
    with conectar(client.application.config["DATABASE_PATH"]) as cx:
        assert cx.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0


def test_usuario_se_recorta(client):
    crear_usuario(client, usuario="  espacios  ")
    with conectar(client.application.config["DATABASE_PATH"]) as cx:
        assert cx.execute("SELECT usuario FROM usuarios").fetchone()[0] == "espacios"


# ==========================================================================
# Login
# ==========================================================================

def test_login_correcto(client, usuario_creado, app):
    r = login(client)
    pagina = html(r)
    assert f"Hola, {NOMBRE}" in pagina
    assert "Tu sesión está activa" in pagina
    assert len(eventos(app, "LOGIN_CORRECTO")) == 1


def test_login_pagina_muestra_identidad_local(client, usuario_creado):
    pagina = html(client.get("/login"))
    assert "Mis Finanzas" in pagina and "Tu dinero, en orden" in pagina
    assert "¿Olvidaste tu contraseña?" in pagina
    assert "Recordar mi usuario" in pagina
    assert "únicamente en este equipo" in pagina
    assert "Aplicación local" in pagina


@pytest.mark.parametrize(
    "usuario, password, mensaje",
    [
        ("", PASSWORD, "El usuario es obligatorio."),
        (USUARIO, "", "La contraseña es obligatoria."),
        (USUARIO, "incorrecta-123", "Usuario o contraseña incorrectos."),
        ("noexiste", PASSWORD, "Usuario o contraseña incorrectos."),
    ],
)
def test_login_incorrecto(client, usuario_creado, usuario, password, mensaje):
    r = login(client, usuario=usuario, password=password)
    pagina = html(r)
    assert mensaje in pagina
    assert "El usuario no existe" not in pagina
    assert client.get("/inicio").status_code == 302


def test_recordar_usuario_solo_guarda_el_nombre(client, usuario_creado):
    r = login(client, recordar=True, follow=False)
    cookies = "\n".join(r.headers.getlist("Set-Cookie"))
    assert "mis_finanzas_usuario=" + USUARIO in cookies
    assert PASSWORD not in cookies
    client.get("/logout")
    assert f'value="{USUARIO}"' in html(client.get("/login"))


# ==========================================================================
# Intentos fallidos y bloqueo temporal
# ==========================================================================

def test_cinco_intentos_bloquean_cinco_minutos(client, usuario_creado, app):
    for _ in range(4):
        assert "Usuario o contraseña incorrectos." in html(login(client, password="mala-mala-1"))
    # Quinto intento: bloqueo
    assert "No es posible iniciar sesión temporalmente" in html(login(client, password="mala-mala-1"))
    assert len(eventos(app, "LOGIN_FALLIDO")) >= 5
    assert len(eventos(app, "CUENTA_BLOQUEADA")) == 1

    # Con la contraseña correcta, durante el bloqueo, no entra
    r = login(client)
    assert "No es posible iniciar sesión temporalmente" in html(r)
    assert client.get("/inicio").status_code == 302

    with conectar(app.config["DATABASE_PATH"]) as cx:
        hasta = cx.execute("SELECT bloqueado_hasta FROM usuarios").fetchone()[0]
        fin = datetime.strptime(hasta, "%Y-%m-%d %H:%M:%S")
        assert timedelta(minutes=4, seconds=30) < fin - datetime.now() <= timedelta(minutes=5)
        # Simular que pasaron los 5 minutos
        cx.execute("UPDATE usuarios SET bloqueado_hasta = ?",
                   ((datetime.now() - timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S"),))
        cx.commit()

    assert f"Hola, {NOMBRE}" in html(login(client))
    with conectar(app.config["DATABASE_PATH"]) as cx:
        fila = cx.execute("SELECT intentos_fallidos, bloqueado_hasta FROM usuarios").fetchone()
        assert fila[0] == 0 and fila[1] is None


# ==========================================================================
# Sesión, logout y caché
# ==========================================================================

def test_ruta_privada_sin_login_redirige(client, usuario_creado):
    for ruta in ("/inicio", "/configuracion/seguridad", "/cambiar-password", "/bloquear"):
        r = client.get(ruta)
        assert r.status_code == 302, ruta
        assert r.headers["Location"].endswith("/login"), ruta


def test_logout_protege_y_evita_cache(client, sesion_iniciada, app):
    r = client.get("/inicio")
    assert r.status_code == 200
    assert "no-store" in r.headers["Cache-Control"]
    assert r.headers["X-Frame-Options"] == "DENY"

    r = client.get("/logout", follow_redirects=True)
    assert "Cerraste sesión" in html(r)
    assert len(eventos(app, "LOGOUT")) == 1

    # Botón "Atrás": la petición vuelve al servidor y sigue protegida
    r = client.get("/inicio")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_cookie_de_sesion_segura_y_sin_datos_sensibles(client, usuario_creado):
    r = login(client, follow=False)
    cookie = [c for c in r.headers.getlist("Set-Cookie") if c.startswith("mis_finanzas_sesion=")][0]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert PASSWORD not in cookie
    with client.session_transaction() as s:
        assert set(s.keys()) <= {"usuario_id", "version_sesion", "bloqueada", "ultima_actividad",
                                 "csrf_token", "_permanent"}


def test_post_sin_csrf_es_rechazado(client, usuario_creado):
    r = client.post("/login", data={"usuario": USUARIO, "password": PASSWORD})
    assert r.status_code == 400
    assert client.get("/inicio").status_code == 302


# ==========================================================================
# Bloqueo manual, desbloqueo e inactividad
# ==========================================================================

def test_bloqueo_manual_y_desbloqueo(client, sesion_iniciada, app):
    r = post(client, "/bloquear", "/inicio", retorno="/configuracion/seguridad")
    assert "Aplicación bloqueada" in html(r)
    assert len(eventos(app, "APLICACION_BLOQUEADA")) == 1

    # Bloqueada: las rutas privadas envían a /bloquear (la sesión sigue viva)
    r = client.get("/configuracion/seguridad")
    assert r.status_code == 302 and r.headers["Location"].endswith("/bloquear")

    # Contraseña incorrecta
    r = post(client, "/desbloquear", "/bloquear", password="incorrecta-99")
    assert "Contraseña incorrecta." in html(r)
    assert client.get("/configuracion/seguridad").status_code == 302

    # Contraseña correcta: regresa a la pantalla que estaba abierta
    r = client.post("/desbloquear", data={"csrf_token": csrf_de(client, "/bloquear"), "password": PASSWORD})
    assert r.status_code == 302 and r.headers["Location"].endswith("/configuracion/seguridad")
    assert client.get("/inicio").status_code == 200
    assert len(eventos(app, "APLICACION_DESBLOQUEADA")) == 1


def test_logout_desde_pantalla_bloqueada(client, sesion_iniciada):
    post(client, "/bloquear", "/inicio")
    client.get("/logout")
    assert client.get("/bloquear").headers["Location"].endswith("/login")


def test_bloqueo_automatico_por_inactividad(client, sesion_iniciada, app):
    assert 'data-inactividad-minutos="30"' in html(client.get("/inicio"))

    # El JS envía motivo=inactividad al agotarse el tiempo
    post(client, "/bloquear", "/inicio", motivo="inactividad")
    assert eventos(app, "APLICACION_BLOQUEADA")[0]["detalle"] == "inactividad"


def test_sesion_expira_en_servidor_sin_actividad(client, sesion_iniciada, app):
    antigua = (datetime.now() - timedelta(minutes=31)).strftime(session_service.FORMATO)
    with client.session_transaction() as s:
        s["ultima_actividad"] = antigua
    r = client.get("/inicio")
    assert r.status_code == 302 and r.headers["Location"].endswith("/sesion-expirada")
    assert "Tu sesión ha expirado" in html(client.get("/sesion-expirada"))
    assert len(eventos(app, "SESION_EXPIRADA")) == 1
    assert client.get("/inicio").headers["Location"].endswith("/login")


def test_tiempo_inactividad_configurable(client, sesion_iniciada, app):
    r = post(client, "/configuracion/inactividad", "/configuracion/seguridad", minutos="10")
    assert "Tiempo de inactividad actualizado" in html(r)
    assert 'data-inactividad-minutos="10"' in html(client.get("/inicio"))
    r = post(client, "/configuracion/inactividad", "/configuracion/seguridad", minutos="7")
    assert "no es válido" in html(r)
    with conectar(app.config["DATABASE_PATH"]) as cx:
        fila = cx.execute("SELECT valor FROM configuracion_usuario WHERE clave='inactividad_minutos'").fetchone()
        assert fila[0] == "10"


# ==========================================================================
# Cambio de contraseña
# ==========================================================================

def test_cambio_de_password(client, sesion_iniciada, app):
    r = post(client, "/cambiar-password", "/cambiar-password",
             password_actual=PASSWORD, password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    pagina = html(r)
    assert "Tu contraseña fue actualizada" in pagina
    assert len(eventos(app, "CAMBIO_PASSWORD")) == 1

    # La sesión se invalidó
    assert client.get("/inicio").status_code == 302

    # Contraseña anterior ya no sirve; la nueva sí
    assert "Usuario o contraseña incorrectos." in html(login(client, password=PASSWORD))
    assert f"Hola, {NOMBRE}" in html(login(client, password=PASSWORD_NUEVA))


@pytest.mark.parametrize(
    "actual, nueva, confirmacion, mensaje",
    [
        ("incorrecta-000", PASSWORD_NUEVA, PASSWORD_NUEVA, "La contraseña actual es incorrecta."),
        (PASSWORD, "corta", "corta", "La contraseña debe tener al menos 10 caracteres."),
        (PASSWORD, PASSWORD_NUEVA, "Diferente123!", "Las contraseñas no coinciden."),
        (PASSWORD, PASSWORD, PASSWORD, "La nueva contraseña debe ser diferente a la actual."),
    ],
)
def test_cambio_de_password_invalido(client, sesion_iniciada, actual, nueva, confirmacion, mensaje):
    r = post(client, "/cambiar-password", "/cambiar-password",
             password_actual=actual, password_nueva=nueva, confirmar_password=confirmacion)
    assert mensaje in html(r)
    # Sigue autenticado y la contraseña no cambió
    assert client.get("/inicio").status_code == 200
    client.get("/logout")
    assert f"Hola, {NOMBRE}" in html(login(client))


def test_cambio_password_invalida_otras_sesiones(app, client, usuario_creado):
    otro = app.test_client()
    login(client)
    login(otro)
    assert otro.get("/inicio").status_code == 200
    post(client, "/cambiar-password", "/cambiar-password",
         password_actual=PASSWORD, password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    r = otro.get("/inicio")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


# ==========================================================================
# Recuperación de acceso
# ==========================================================================

def test_recuperacion_codigo_incorrecto(client, usuario_creado, app):
    r = post(client, "/recuperar-acceso", "/recuperar-acceso",
             codigo="AAAA-BBBB-CCCC-DDDD", password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    assert "El código de recuperación no es válido." in html(r)
    assert len(eventos(app, "RECUPERACION_FALLIDA")) == 1
    assert f"Hola, {NOMBRE}" in html(login(client))  # contraseña intacta


def test_recuperacion_correcta_y_codigo_de_un_solo_uso(app, client, usuario_creado):
    codigo = usuario_creado
    otro = app.test_client()
    login(otro)
    assert otro.get("/inicio").status_code == 200

    r = post(client, "/recuperar-acceso", "/recuperar-acceso",
             codigo=codigo.lower(), password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    assert "La contraseña fue actualizada correctamente. Inicia sesión nuevamente." in html(r)
    assert len(eventos(app, "RECUPERACION_ACCESO")) == 1

    # Sesiones existentes invalidadas
    assert otro.get("/inicio").status_code == 302

    # Contraseña anterior no sirve; la nueva sí
    assert "Usuario o contraseña incorrectos." in html(login(client, password=PASSWORD))
    assert f"Hola, {NOMBRE}" in html(login(client, password=PASSWORD_NUEVA))
    client.get("/logout")

    # Segundo uso del mismo código
    r = post(client, "/recuperar-acceso", "/recuperar-acceso",
             codigo=codigo, password_nueva="TerceraClave2025!", confirmar_password="TerceraClave2025!")
    assert "El código de recuperación ya fue utilizado." in html(r)
    assert f"Hola, {NOMBRE}" in html(login(client, password=PASSWORD_NUEVA))


def test_recuperacion_valida_nueva_password(client, usuario_creado):
    r = post(client, "/recuperar-acceso", "/recuperar-acceso",
             codigo=usuario_creado, password_nueva="corta", confirmar_password="corta")
    assert "La contraseña debe tener al menos 10 caracteres." in html(r)
    r = post(client, "/recuperar-acceso", "/recuperar-acceso",
             codigo=usuario_creado, password_nueva=PASSWORD_NUEVA, confirmar_password="otra")
    assert "Las contraseñas no coinciden." in html(r)
    # El código sigue vigente porque no se consumió
    assert f"Hola, {NOMBRE}" in html(login(client))


def test_regenerar_codigo_desde_configuracion(client, sesion_iniciada, app):
    r = post(client, "/configuracion/codigo-recuperacion", "/configuracion/seguridad", password="mala-mala-1")
    assert "La contraseña actual es incorrecta." in html(r)

    r = post(client, "/configuracion/codigo-recuperacion", "/configuracion/seguridad", password=PASSWORD)
    nuevo = PATRON_CODIGO.search(html(r)).group(0)
    assert nuevo != sesion_iniciada
    assert len(eventos(app, "CODIGO_RECUPERACION_REGENERADO")) == 1
    continuar_codigo(client)
    client.get("/logout")

    # El código anterior deja de funcionar; el nuevo sí
    r = post(client, "/recuperar-acceso", "/recuperar-acceso",
             codigo=sesion_iniciada, password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    assert "El código de recuperación no es válido." in html(r)
    r = post(client, "/recuperar-acceso", "/recuperar-acceso",
             codigo=nuevo, password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    assert "La contraseña fue actualizada correctamente" in html(r)


# ==========================================================================
# Auditoría
# ==========================================================================

def test_auditoria_no_guarda_secretos(client, sesion_iniciada, app):
    client.get("/logout")
    login(client, password="mala-mala-1")
    login(client)
    post(client, "/cambiar-password", "/cambiar-password",
         password_actual=PASSWORD, password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    with conectar(app.config["DATABASE_PATH"]) as cx:
        filas = cx.execute("SELECT evento, detalle FROM auditoria_seguridad").fetchall()
    texto = " ".join(f"{f[0]} {f[1] or ''}" for f in filas)
    for secreto in (PASSWORD, PASSWORD_NUEVA, "mala-mala-1", sesion_iniciada):
        assert secreto not in texto
    assert {"USUARIO_CREADO", "LOGIN_CORRECTO", "LOGIN_FALLIDO", "CAMBIO_PASSWORD"} <= {f[0] for f in filas}


def test_configuracion_muestra_auditoria(client, sesion_iniciada):
    pagina = html(client.get("/configuracion/seguridad"))
    assert "LOGIN_CORRECTO" in pagina
    assert "Cambiar contraseña" in pagina


# ==========================================================================
# Respaldos
# ==========================================================================

def test_crear_y_restaurar_respaldo(client, sesion_iniciada, app):
    r = post(client, "/respaldos/crear", "/configuracion/seguridad")
    assert "Respaldo creado" in html(r)
    respaldos = list(app.config["BACKUPS_PATH"].glob("*.db"))
    assert len(respaldos) == 1
    assert len(eventos(app, "RESPALDO_CREADO")) == 1

    r = client.get(f"/respaldos/{respaldos[0].name}/descargar")
    assert r.status_code == 200 and r.data[:16] == b"SQLite format 3\x00"

    # Archivo inválido: rechazado
    r = client.post(
        "/respaldos/restaurar",
        data={"csrf_token": csrf_de(client, "/configuracion/seguridad"), "password": PASSWORD,
              "archivo": (io.BytesIO(b"no soy sqlite " * 20), "falso.db")},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert "no es una base de datos SQLite válida" in html(r)
    assert len(eventos(app, "RESPALDO_RECHAZADO")) == 1
    assert client.get("/inicio").status_code == 200

    # Cambiamos la contraseña y restauramos el respaldo: vuelve la anterior
    post(client, "/cambiar-password", "/cambiar-password",
         password_actual=PASSWORD, password_nueva=PASSWORD_NUEVA, confirmar_password=PASSWORD_NUEVA)
    login(client, password=PASSWORD_NUEVA)
    r = client.post(
        "/respaldos/restaurar",
        data={"csrf_token": csrf_de(client, "/configuracion/seguridad"), "password": PASSWORD_NUEVA,
              "archivo": (open(respaldos[0], "rb"), respaldos[0].name)},
        content_type="multipart/form-data", follow_redirects=True,
    )
    assert "se restauró correctamente" in html(r)
    assert client.get("/inicio").status_code == 302
    assert f"Hola, {NOMBRE}" in html(login(client, password=PASSWORD))
    # Se creó un respaldo automático previo a la restauración
    assert len(list(app.config["BACKUPS_PATH"].glob("*.db"))) == 2


# ==========================================================================
# Persistencia
# ==========================================================================

def test_persistencia_tras_reiniciar(tmp_path):
    app1 = crear_app(tmp_path)
    c1 = app1.test_client()
    crear_usuario(c1)
    continuar_codigo(c1)
    login(c1)
    post(c1, "/configuracion/inactividad", "/configuracion/seguridad", minutos="15")
    del c1, app1

    # "Reinicio": nueva instancia de la aplicación sobre el mismo archivo
    app2 = crear_app(tmp_path)
    c2 = app2.test_client()
    assert c2.get("/").headers["Location"].endswith("/login")
    pagina = html(login(c2))
    assert f"Hola, {NOMBRE}" in pagina
    assert 'data-inactividad-minutos="15"' in pagina
    with conectar(tmp_path / "finanzas_test.db") as cx:
        assert cx.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 1
        assert cx.execute("SELECT COUNT(*) FROM auditoria_seguridad").fetchone()[0] >= 3

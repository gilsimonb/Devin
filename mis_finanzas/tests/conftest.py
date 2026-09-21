import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app import create_app  # noqa: E402
from config import TestConfig  # noqa: E402

USUARIO = "gilberto"
NOMBRE = "Gilberto"
PASSWORD = "ClaveSegura2024!"
PASSWORD_NUEVA = "OtraClaveSegura99#"

PATRON_CODIGO = re.compile(r"[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}")


def crear_app(tmp_path):
    class _Config(TestConfig):
        DATABASE_PATH = tmp_path / "finanzas_test.db"
        BACKUPS_PATH = tmp_path / "backups"

    return create_app(_Config)


@pytest.fixture
def app(tmp_path):
    return crear_app(tmp_path)


@pytest.fixture
def client(app):
    return app.test_client()


def html(respuesta) -> str:
    return respuesta.get_data(as_text=True)


def csrf_de(client, ruta: str) -> str:
    """Obtiene un token CSRF válido visitando una página con formulario."""
    pagina = html(client.get(ruta))
    match = re.search(r'name="csrf_token" value="([^"]+)"', pagina)
    assert match, f"No se encontró token CSRF en {ruta}"
    return match.group(1)


def crear_usuario(client, usuario=USUARIO, password=PASSWORD, nombre=NOMBRE) -> str:
    """Crea el primer usuario y devuelve el código de recuperación mostrado."""
    token = csrf_de(client, "/crear-usuario")
    r = client.post(
        "/crear-usuario",
        data={
            "csrf_token": token,
            "usuario": usuario,
            "nombre": nombre,
            "password": password,
            "confirmar_password": password,
        },
        follow_redirects=True,
    )
    pagina = html(r)
    match = PATRON_CODIGO.search(pagina)
    assert match, "El código de recuperación no se mostró"
    return match.group(0)


def continuar_codigo(client):
    token = csrf_de(client, "/codigo-recuperacion")
    return client.post("/codigo-recuperacion/continuar", data={"csrf_token": token}, follow_redirects=True)


def login(client, usuario=USUARIO, password=PASSWORD, recordar=False, follow=True):
    token = csrf_de(client, "/login")
    datos = {"csrf_token": token, "usuario": usuario, "password": password}
    if recordar:
        datos["recordar"] = "1"
    return client.post("/login", data=datos, follow_redirects=follow)


def post(client, ruta, ruta_csrf, **datos):
    datos["csrf_token"] = csrf_de(client, ruta_csrf)
    return client.post(ruta, data=datos, follow_redirects=True)


def eventos(app, evento: str):
    from database.db import conectar

    with conectar(app.config["DATABASE_PATH"]) as cx:
        return cx.execute(
            "SELECT * FROM auditoria_seguridad WHERE evento = ?", (evento,)
        ).fetchall()


@pytest.fixture
def usuario_creado(client):
    """Primer usuario creado y código de recuperación confirmado."""
    codigo = crear_usuario(client)
    continuar_codigo(client)
    return codigo


@pytest.fixture
def sesion_iniciada(client, usuario_creado):
    login(client)
    return usuario_creado

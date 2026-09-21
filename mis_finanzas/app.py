"""Punto de entrada de Mis Finanzas.

Ejecutar con:
    python app.py

y abrir http://127.0.0.1:5000 en el navegador.
"""

import sys
from pathlib import Path

from flask import Flask, g, render_template

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config  # noqa: E402
from database import db  # noqa: E402
from routes.auth import auth_bp  # noqa: E402
from routes.main import main_bp  # noqa: E402
from services import session_service  # noqa: E402


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_object)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    @app.before_request
    def _preparar_peticion():
        session_service.cargar_usuario_actual()
        session_service.validar_csrf()

    @app.after_request
    def _cabeceras(respuesta):
        return session_service.cabeceras_seguridad(respuesta)

    app.jinja_env.globals["csrf_token"] = session_service.csrf_token

    @app.context_processor
    def _contexto():
        return {
            "usuario_actual": session_service.usuario_actual(),
            "app_bloqueada": session_service.esta_bloqueada(),
            "inactividad_minutos": getattr(g, "inactividad_minutos", None),
            "APP_NAME": app.config["APP_NAME"],
            "APP_SUBTITULO": app.config["APP_SUBTITULO"],
            "APP_VERSION": app.config["APP_VERSION"],
            "AVISO_SEGUNDOS": app.config["INACTIVIDAD_AVISO_SEGUNDOS"],
        }

    @app.errorhandler(400)
    def _error_400(error):
        return render_template("error.html", codigo=400, mensaje=error.description), 400

    @app.errorhandler(404)
    def _error_404(_error):
        return render_template("error.html", codigo=404, mensaje="La página no existe."), 404

    @app.errorhandler(413)
    def _error_413(_error):
        return render_template("error.html", codigo=413, mensaje="El archivo es demasiado grande."), 413

    @app.errorhandler(500)
    def _error_500(_error):
        return render_template("error.html", codigo=500, mensaje="Ocurrió un error inesperado."), 500

    return app


if __name__ == "__main__":
    aplicacion = create_app()
    print(f"{Config.APP_NAME} — {Config.APP_SUBTITULO}")
    print(f"Abre http://{Config.HOST}:{Config.PORT} en tu navegador. Ctrl+C para detener.")
    aplicacion.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)

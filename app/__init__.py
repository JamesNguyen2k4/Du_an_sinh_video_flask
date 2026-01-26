# app/__init__.py
from flask import Flask

def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )

    # Register blueprints
    from app.routes.web import web
    from app.routes.api import api
    from app.routes.media import media

    app.register_blueprint(web)
    app.register_blueprint(api)
    app.register_blueprint(media)

    # Basic config
    app.config["JSON_AS_ASCII"] = False
    app.config["TEMPLATES_AUTO_RELOAD"] = True

    return app

# app/__init__.py
from flask import Flask
from app.routes.api import api


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(api)
    return app

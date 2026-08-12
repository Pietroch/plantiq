# app/src/plantiq/web/app.py

from flask import Flask

from plantiq.web.views import home, rooms, sites


def create_app() -> Flask:
    flask_app = Flask(__name__)
    flask_app.register_blueprint(home.bp)
    flask_app.register_blueprint(sites.bp)
    flask_app.register_blueprint(rooms.bp)
    return flask_app


app = create_app()

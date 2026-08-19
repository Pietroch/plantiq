# app/src/plantiq/web/app.py

from flask import Flask

from plantiq.web.views import (
    care,
    equipment,
    home,
    notifications,
    plants,
    rooms,
    runs,
    sites,
    species,
    weather,
)


def create_app() -> Flask:
    flask_app = Flask(__name__)
    for module in (home, sites, rooms, species, equipment, plants, care, weather, notifications, runs):
        flask_app.register_blueprint(module.bp)
    return flask_app


app = create_app()

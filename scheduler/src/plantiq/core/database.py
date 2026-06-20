# scheduler/src/plantiq/core/database.py

from sqlalchemy import create_engine

from plantiq.core.config import DATABASE_URL

engine = create_engine(DATABASE_URL)

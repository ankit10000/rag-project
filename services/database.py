import os
import psycopg

from dotenv import load_dotenv
from pgvector.psycopg import register_vector

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing")

    conn = psycopg.connect(DATABASE_URL)

    register_vector(conn)

    return conn
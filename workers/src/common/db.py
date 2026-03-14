import psycopg2
from contextlib import contextmanager
from src.common.config import DATABASE_URL


@contextmanager
def get_connection():
    """Yield a psycopg2 connection that auto-closes."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(conn):
    """Yield a cursor that auto-closes."""
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()

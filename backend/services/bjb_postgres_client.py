import psycopg2
import os

def get_connection():
    return psycopg2.connect(
        dbname=os.getenv("BJB_DB_NAME"),
        user=os.getenv("BJB_DB_USER"),
        password=os.getenv("BJB_DB_PASSWORD"),
        host=os.getenv("BJB_DB_HOST"),
        port=os.getenv("BJB_DB_PORT", 5432)
    )

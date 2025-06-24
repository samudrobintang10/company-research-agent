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

def get_recommended_products(institution_id: int):
    conn = get_connection()
    cur = conn.cursor()

    query = """
        SELECT id, name, description, note, priority, link
        FROM products
        WHERE deleted_at IS NULL AND id NOT IN (
            SELECT product_id FROM recommendations
            WHERE institution_id = %s AND deleted_at IS NULL
        )
        ORDER BY priority DESC NULLS LAST
        LIMIT 5;
    """
    cur.execute(query, (institution_id,))
    rows = cur.fetchall()
    conn.close()

    return [
        {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "note": row[3],
            "priority": row[4],
            "link": row[5],
        }
        for row in rows
    ]

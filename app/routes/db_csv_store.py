# db_csv_store.py
import pickle
import secrets
from datetime import datetime, timedelta
from flask import g

def _cleanup():
    with g.db_manager.get_cursor(dictionary=True, commit=True) as cursor:
        cursor.execute(
            "DELETE FROM csv_import_temp WHERE created_at < %s",
            (datetime.utcnow() - timedelta(hours=1),)
        )

def save(user_id, data):
    _cleanup()
    key = secrets.token_urlsafe(32)
    pickled = pickle.dumps(data)
    with g.db_manager.get_cursor(dictionary=True, commit=True) as cursor:
        cursor.execute(
            "INSERT INTO csv_import_temp (id, user_id, data) VALUES (%s, %s, %s)",
            (key, user_id, pickled)
        )
    return key

def load(key, user_id):
    _cleanup()
    with g.db_manager.get_cursor(dictionary=True, commit=False) as cursor:
        cursor.execute(
            "SELECT data FROM csv_import_temp WHERE id = %s AND user_id = %s",
            (key, user_id)
        )
        row = cursor.fetchone()
        if row:
            return pickle.loads(row['data'])  # ✅ row['data'] car dictionary=True
    return None
def update(key, user_id, data):
    """Met à jour les données existantes"""
    pickled = pickle.dumps(data)
    with g.db_manager.get_cursor(dictionary=True, commit=True) as cursor:
        cursor.execute(
            "UPDATE csv_import_temp SET data = %s WHERE id = %s AND user_id = %s",
            (pickled, key, user_id)
        )

def delete(key):
    with g.db_manager.get_cursor(dictionary=True, commit=True) as cursor:
        cursor.execute("DELETE FROM csv_import_temp WHERE id = %s", (key,))
# db_csv_store.py
import pickle
import secrets
from datetime import datetime, timedelta
from flask import g

def _get_cursor(commit=False):
    """Utilise votre méthode existante pour obtenir un curseur"""
    return g.db_manager.get_cursor(dictionary=False, commit=commit)

def _cleanup():
    with _get_cursor(commit=True) as cursor:
        cursor.execute(
            "DELETE FROM csv_import_temp WHERE created_at < %s",
            (datetime.utcnow() - timedelta(hours=1),)
        )

def save(user_id, data):
    _cleanup()
    key = secrets.token_urlsafe(32)
    pickled = pickle.dumps(data)
    with _get_cursor(commit=True) as cursor:
        cursor.execute(
            "INSERT INTO csv_import_temp (id, user_id, data) VALUES (%s, %s, %s)",
            (key, user_id, pickled)
        )
    return key

def load(key, user_id):
    _cleanup()
    with _get_cursor(commit=False) as cursor:
        cursor.execute(
            "SELECT data FROM csv_import_temp WHERE id = %s AND user_id = %s",
            (key, user_id)
        )
        row = cursor.fetchone()
        if row:
            return pickle.loads(row[0])  # row[0] car dictionary=False
    return None

def delete(key):
    with _get_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM csv_import_temp WHERE id = %s", (key,))
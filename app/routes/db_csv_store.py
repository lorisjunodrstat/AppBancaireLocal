# db_csv_store.py
import pickle
import secrets
from datetime import datetime, timedelta
from flask import g

def _cleanup():
    # Supprime les entrées > 1 heure
    g.db_manager.execute(
        "DELETE FROM csv_import_temp WHERE created_at < %s",
        (datetime.utcnow() - timedelta(hours=1),)
    )

def save(user_id, data):
    _cleanup()
    key = secrets.token_urlsafe(32)
    pickled = pickle.dumps(data)
    g.db_manager.execute(
        "INSERT INTO csv_import_temp (id, user_id, data) VALUES (%s, %s, %s)",
        (key, user_id, pickled)
    )
    return key

def load(key, user_id):
    _cleanup()
    row = g.db_manager.fetch_one(
        "SELECT data FROM csv_import_temp WHERE id = %s AND user_id = %s",
        (key, user_id)
    )
    if row:
        return pickle.loads(row['data'])
    return None

def delete(key):
    g.db_manager.execute("DELETE FROM csv_import_temp WHERE id = %s", (key,))
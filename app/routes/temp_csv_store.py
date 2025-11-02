# temp_csv_store.py
import uuid
from datetime import datetime, timedelta
from threading import Lock

# Stockage simple en mémoire (thread-safe basique)
_store = {}
_lock = Lock()
MAX_AGE = 3600  # 1 heure

def _cleanup():
    now = datetime.utcnow()
    with _lock:
        to_delete = [
            key for key, val in _store.items()
            if (now - val['created_at']).total_seconds() > MAX_AGE
        ]
        for key in to_delete:
            del _store[key]

def save(user_id, data):
    _cleanup()
    key = str(uuid.uuid4())
    with _lock:
        _store[key] = {
            'user_id': user_id,
            'data': data,
            'created_at': datetime.utcnow()
        }
    return key

def load(key, user_id):
    _cleanup()
    with _lock:
        entry = _store.get(key)
    if not entry or entry['user_id'] != user_id:
        return None
    return entry['data']

def delete(key):
    with _lock:
        _store.pop(key, None)
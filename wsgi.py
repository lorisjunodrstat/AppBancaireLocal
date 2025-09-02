import sys
import os
from dotenv import load_dotenv, find_dotenv

# Charger les variables d'environnement au démarrage de WSGI
# Nous utilisons find_dotenv() pour localiser le fichier .env de manière plus robuste
load_dotenv(find_dotenv())

# Ajouter le répertoire racine au chemin Python
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from app import app as application

# L'initialisation de la base de données doit être appelée manuellement,
# pas lors du déploiement via WSGI.
# if __name__ == "__main__":
#     from app import init_database
#     init_database()

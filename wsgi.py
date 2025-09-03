import sys
import os
from dotenv import load_dotenv, find_dotenv

# Chargez les variables d'environnement au démarrage de WSGI de manière robuste.
# find_dotenv() cherche de manière récursive le fichier .env
load_dotenv(find_dotenv())

# Ajoutez le répertoire racine au chemin Python
# Cela permet à l'application d'importer ses modules correctement.
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Importez l'application Flask
from app import app as application

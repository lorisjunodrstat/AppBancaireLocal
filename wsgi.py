import sys
import os

# Ajouter le répertoire racine au chemin Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as application

# Initialisation de la base de données
if __name__ == "__main__":
    from app import init_database
    init_database()
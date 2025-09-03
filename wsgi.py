import sys
import os

# Ajoutez le répertoire racine du projet au chemin de recherche Python
# Remplacez '/var/www/webroot/ROOT' par le chemin absolu de votre répertoire racine
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Importez dotenv et chargez les variables d'environnement
from dotenv import load_dotenv
load_dotenv()

from app import app as application

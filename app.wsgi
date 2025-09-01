#!/usr/bin/python
import sys
import os

# Ajouter le chemin de votre projet au Python Path
sys.path.insert(0, os.path.dirname(__file__))

# Définir le répertoire de l'application
os.chdir(os.path.dirname(__file__))

# Charger les variables d'environnement
from dotenv import load_dotenv
load_dotenv()

# Importer votre application Flask
from app import app as application

# Optionnel: Initialiser la base de données
if os.environ.get('FLASK_ENV') == 'development':
    from app.models import init_db
    init_db()
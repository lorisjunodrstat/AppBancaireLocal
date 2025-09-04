#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fichier d'entrée WSGI pour l'application Flask.
Ce fichier est utilisé par le serveur web (Apache, Gunicorn, etc.).
"""

import sys
import os
from dotenv import load_dotenv

# Ajoutez le répertoire racine au chemin Python pour les imports absolus.
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Charge les variables d'environnement du fichier .env
load_dotenv(os.path.join(project_root, '.env'))

# Importe l'instance de l'application Flask
from app import app as application

# L'initialisation de Flask-Login est déjà faite dans __init__.py,
# donc pas besoin d'appeler init_login_manager ici.
if __name__ == '__main__':
    # Ce bloc ne sera pas exécuté en mode WSGI
    application.run()

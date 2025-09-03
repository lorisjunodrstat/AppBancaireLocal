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
# Ceci est nécessaire pour que le serveur web trouve votre application.
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Charge les variables d'environnement du fichier .env
# avant d'importer l'application.
load_dotenv(os.path.join(project_root, '.env'))

# Importe l'instance de l'application Flask
from app import app as application
from app import init_login_manager

# Initialise Flask-Login après que l'application a été importée.
init_login_manager(application)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Initialisation Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'votre-cle-secrete-tres-longue-et-complexe')

# Configuration de la base de données
DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'node184712-env-9328605.jcloud.ik-server.com'),  # À adapter
    'port': int(os.environ.get('DB_PORT', 3306)),  # Port MySQL standard
    'database': os.environ.get('DB_NAME', 'banking2'),
    'user': os.environ.get('DB_USER', 'root'),  # Remplacez par votre utilisateur
    'password': os.environ.get('DB_PASSWORD', 'PTXlqh31192'),  # Remplacez par votre mot de passe
    'charset': 'utf8mb4',
    'use_unicode': True,
    'autocommit': True
}

# Configuration Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# Import des modèles et routes
from app import models
from app.routes import auth, admin, banking

# Enregistrement des blueprints
app.register_blueprint(auth.bp)
app.register_blueprint(admin.bp)
app.register_blueprint(banking.bp)

# Filtres de template
@app.template_filter('format_date')
def format_date_filter(value, format='%d.%m.%Y'):
    if isinstance(value, str):
        return value
    return value.strftime(format)

@app.template_filter('month_name')
def month_name_filter(month_num):
    month_names = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 
        'Mai', 'Juin', 'Juillet', 'Août', 
        'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]
    return month_names[month_num] if 1 <= month_num <= 12 else ''

# Context processor
@app.context_processor
def utility_processor():
    def get_month_name(month_num):
        months = {
            1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
            5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
            9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
        }
        return months.get(month_num, "")
    
    return dict(get_month_name=get_month_name)

# Initialisation de la base de données
def init_database():
    from app.models import init_db
    init_db()

# Point d'entrée pour l'exécution directe
if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5053)
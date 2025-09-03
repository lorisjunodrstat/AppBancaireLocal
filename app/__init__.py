#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
import sys
from flask import Flask, g
from flask_login import LoginManager
from dotenv import load_dotenv
from pathlib import Path
import pymysql
import pymysql.cursors
import logging

# Charge les variables d'environnement avec chemin absolu
env_path = Path('/var/www/webroot/ROOT') / '.env'
load_dotenv(dotenv_path=env_path)

# Configuration de la journalisation
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/webroot/ROOT/app.log'),
        logging.StreamHandler()
    ]
)

# Initialisation Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'votre-cle-secrete-tres-longue-et-complexe')

# Configuration de la base de données avec PyMySQL
app.config['DB_CONFIG'] = {
    'host': os.environ.get('DB_HOST'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'database': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'charset': 'utf8mb4',
    'autocommit': True,
    'cursorclass': pymysql.cursors.DictCursor,
    'auth_plugin': 'mysql_native_password'
}

# Configuration Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# Fonction de chargement d'utilisateur pour Flask-Login
@login_manager.user_loader
def load_user(user_id):
    from app.models import Utilisateur
    return Utilisateur.get_by_id(user_id)

# Import des routes (APRES la création de l'app)
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

# Initialisation des gestionnaires de modèles
@app.before_request
def before_request_hook():
    if not hasattr(g, 'db_manager'):
        from app.models import DatabaseManager, ModelManager
        g.db_manager = DatabaseManager(app.config['DB_CONFIG'])
        g.model_manager = ModelManager(g.db_manager)

# Point d'entrée pour l'exécution directe (UNIQUEMENT pour le développement)
if __name__ == '__main__':
    # Ajoutez le répertoire racine au chemin Python pour les imports absolus
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        
    app.run(debug=True)

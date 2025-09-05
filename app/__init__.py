#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
import sys
from flask import Flask, g, request
from flask_login import LoginManager
from dotenv import load_dotenv
from pathlib import Path
import pymysql
import pymysql.cursors
import logging
from logging.handlers import RotatingFileHandler
# L'import de 'psycopg2' a été retiré car il n'est pas compatible avec PyMySQL.

# Charge les variables d'environnement avec chemin absolu
env_path = Path('/var/www/webroot/ROOT') / '.env'
load_dotenv(dotenv_path=env_path)

# --- Configuration de la journalisation ---
log_dir = os.path.join('/var/www/webroot/ROOT', 'logs')
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'app.log'),
    maxBytes=1024 * 1024 * 10,  # 10 Mo
    backupCount=10
)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.addHandler(file_handler)
root_logger.setLevel(logging.INFO)

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
    'cursorclass': pymysql.cursors.DictCursor
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
    from app.models import Utilisateur, DatabaseManager
    db_manager = DatabaseManager(app.config['DB_CONFIG'])
    return Utilisateur.get_by_id(user_id, db_manager)

# Import des routes (APRES la création de l'app)
from app.routes import auth, admin, banking
@app.route('/')
    def index_redirect():
        return redirect(url_for('auth.login'))
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
    from app.models import DatabaseManager, ModelManager
    try:
        g.db_manager = DatabaseManager(app.config['DB_CONFIG'])
        g.model_manager = ModelManager(g.db_manager)
    except Exception as e:
        logging.error(f"Failed to establish database connection: {e}")
        g.db_manager = None
        g.model_manager = None

@app.after_request
def after_request_hook(response):
    if hasattr(g, 'db_manager') and g.db_manager is not None:
        g.db_manager.close_connection()
    return response

# Point d'entrée pour l'exécution directe (UNIQUEMENT pour le développement)
if __name__ == '__main__':
    # Ajoutez le répertoire racine au chemin Python pour les imports absolus
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    app.run(debug=True)

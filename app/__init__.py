#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
from flask import Flask, g
from flask_login import LoginManager
from dotenv import load_dotenv
import pymysql.cursors
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# --- Configuration de la journalisation ---
log_dir = '/var/www/webroot/ROOT/logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Handler pour le fichier de log
file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'app.log'),
    maxBytes=1024 * 1024 * 10,  # 10 MB
    backupCount=10
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# Handler pour la console
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.INFO)

# Configurer le logger racine pour utiliser les deux handlers
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(stream_handler)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# --- Initialisation de l'application Flask ---
env_path = Path('/var/www/webroot/ROOT') / '.env'
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'votre-cle-secrete-tres-longue-et-complexe')

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

# --- Initialisation Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# Import des modèles pour la fonction de chargement d'utilisateur
from app.models import Utilisateur, DatabaseManager, ModelManager

@login_manager.user_loader
def load_user(user_id):
    db_manager = DatabaseManager(app.config['DB_CONFIG'])
    return Utilisateur.get_by_id(user_id, db_manager)

# --- Hooks de l'application ---
@app.before_request
def before_request_hook():
    """Crée une instance de DatabaseManager et de ModelManager pour chaque requête."""
    if not hasattr(g, 'db_manager'):
        g.db_manager = DatabaseManager(app.config['DB_CONFIG'])
    if not hasattr(g, 'model_manager'):
        g.model_manager = ModelManager(g.db_manager)

@app.teardown_appcontext
def teardown_db(exception):
    """Ferme la connexion à la base de données à la fin du contexte de l'application."""
    if hasattr(g, 'db_manager') and g.db_manager.conn:
        g.db_manager.close_connection()
        logging.info("Connexion à la base de données fermée pour cette requête.")

# --- Import des routes et blueprints ---
from app.routes import auth, admin, banking
app.register_blueprint(auth.bp)
app.register_blueprint(admin.bp)
app.register_blueprint(banking.bp)

# --- Filtres de template et context processor ---
@app.template_filter('format_date')
def format_date_filter(value, format='%d.%m.%Y'):
    if isinstance(value, str):
        return value
    return value.strftime(format)

@app.template_filter('month_name')
def month_name_filter(month_num):
    month_names = ['', 'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']
    return month_names[month_num] if 1 <= month_num <= 12 else ''

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

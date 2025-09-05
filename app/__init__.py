#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
import sys
from flask import Flask, g, request, redirect, url_for, request_started, request_finished
from flask_login import LoginManager
from dotenv import load_dotenv
from pathlib import Path
import pymysql
import pymysql.cursors
import logging
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager

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

# --- Début des modifications ---

# Remplacer la fonction before_request par un signal
def create_managers_on_request_start(sender, **extra):
    from app.models import DatabaseManager, ModelManager
    try:
        g.db_manager = DatabaseManager(sender.config['DB_CONFIG'])
        # CORRECTION ICI: utilisez "g.models" pour correspondre au reste de votre code
        g.models = ModelManager(g.db_manager)
    except Exception as e:
        logging.error(f"Failed to establish database connection: {e}")
        g.db_manager = None
        # CORRECTION ICI: utilisez "g.models" pour la cohérence
        g.models = None

# Connecter la fonction au signal request_started de l'application
request_started.connect(create_managers_on_request_start, app)

# Fermeture des ressources après chaque requête
def close_managers_on_request_finish(sender, response, **extra):
    # Vérifie si l'attribut db_manager existe dans l'objet g et n'est pas None.
    if hasattr(g, 'db_manager') and g.db_manager:
        try:
            # Tente de fermer le pool de connexions si la méthode existe.
            # Le nom de la méthode dépend de votre implémentation.
            if hasattr(g.db_manager, 'pool'):
                # Si votre DatabaseManager a un attribut 'pool'
                g.db_manager.pool.close()
            elif hasattr(g.db_manager, 'close'):
                # Si la méthode de fermeture est simplement 'close'
                g.db_manager.close()
        except Exception as e:
            logging.error(f"Erreur lors de la fermeture du gestionnaire de DB : {e}")
    return response
# Connecter la fonction au signal request_finished de l'application
request_finished.connect(close_managers_on_request_finish, app)


# --- Fin des modifications ---

# Point d'entrée pour l'exécution directe (UNIQUEMENT pour le développement)
if __name__ == '__main__':
    # Ajoutez le répertoire racine au chemin Python pour les imports absolus
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    app.run(debug=True)

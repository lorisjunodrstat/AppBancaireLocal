#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
import sys
from flask import Flask, g, redirect, url_for, request_started, request_finished, current_app
from flask_login import LoginManager, current_user
from dotenv import load_dotenv
from pathlib import Path
import pymysql
import pymysql.cursors
import logging
from logging.handlers import RotatingFileHandler

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
# --- Chemins d'upload ---
UPLOAD_FOLDER_LOGOS = os.path.join(app.static_folder, 'uploads', 'logos')
os.makedirs(UPLOAD_FOLDER_LOGOS, exist_ok=True)
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
    if not user_id or not current_app:
        return None
        
    try:
        # Connexion directe sans utiliser DatabaseManager pour éviter la récursion
        config_db = current_app.config.get('DB_CONFIG')
        if not config_db:
            return None
            
        connection = pymysql.connect(
            host=config_db['host'],
            port=config_db['port'],
            user=config_db['user'],
            password=config_db['password'],
            database=config_db['database'],
            charset=config_db['charset'],
            cursorclass=pymysql.cursors.DictCursor
        )
        
        user = None
        try:
            with connection.cursor() as cursor:
                query = "SELECT id, nom, prenom, email, mot_de_passe FROM utilisateurs WHERE id = %s"
                cursor.execute(query, (user_id,))
                row = cursor.fetchone()
                if row:
                    # Import local pour éviter la dépendance circulaire
                    from app.models import Utilisateur
                    user = Utilisateur(
                        id=row['id'],
                        nom=row['nom'],
                        prenom=row['prenom'],
                        email=row['email'],
                        mot_de_passe=row['mot_de_passe']
                    )
        finally:
            connection.close()
            
        return user
    except Exception as e:
        logging.error(f"Erreur dans load_user: {e}")
        return None


# Import des routes (APRES la création de l'app)
from app.routes import auth, admin, banking, db_csv_store

# Route racine redirigeant vers la page appropriée
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.liste_utilisateurs'))
        else:
            return redirect(url_for('banking.dashboard'))
    return redirect(url_for('auth.login'))
# Sécurité : bloquer les extensions dangereuses dans /static/uploads
@app.route('/static/uploads/<path:filename>')
def secure_uploads(filename):
    dangerous_ext = {'.py', '.env', '.sh', '.exe', '.php', '.html', '.js', '.sql'}
    if any(filename.lower().endswith(ext) for ext in dangerous_ext):
        from flask import abort
        abort(403)
    from flask import send_from_directory
    return send_from_directory(os.path.join(app.static_folder, 'uploads'), filename)
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

# Context processor GLOBAL pour injecter les comptes utilisateur dans tous les templates
@app.context_processor
def inject_user_comptes():
    from flask_login import current_user
    try:
        if current_user.is_authenticated:
            # Retourne simplement un dict vide sans essayer de récupérer des comptes
            # Évite l'erreur de table 'comptes' qui n'existe pas
            return dict(user_comptes=[], user_id=current_user.id)
        else:
            return dict(user_comptes=[], user_id=None)
    except Exception as e:
        logging.error(f"Erreur dans inject_user_comptes: {e}")
        return dict(user_comptes=[], user_id=None)
# Remplacer la fonction before_request par un signal
@app.before_request
def before_request():
    # Initialise g.db_manager pour la requête
    try:
        from app.models import DatabaseManager
        config_db = current_app.config.get('DB_CONFIG')
        if config_db:
            g.db_manager = DatabaseManager(config_db)
        else:
            g.db_manager = None
    except Exception as e:
        logging.error(f"Erreur lors de la création de DatabaseManager: {e}")
        g.db_manager = None

@app.teardown_request
def teardown_request(exception=None):
    # Ferme la connexion à la base de données
    if hasattr(g, 'db_manager') and g.db_manager is not None:
        try:
            if hasattr(g.db_manager, 'close_connection'):
                g.db_manager.close_connection()
            elif hasattr(g.db_manager, 'close'):
                g.db_manager.close()
        except Exception as e:
            logging.error(f"Erreur lors de la fermeture de la connexion: {e}")
# Point d'entrée pour l'exécution directe (UNIQUEMENT pour le développement)
if __name__ == '__main__':
    # Ajoutez le répertoire racine au chemin Python pour les imports absolus
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    app.run(debug=True)

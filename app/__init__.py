#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
import sys
from flask import Flask, jsonify, redirect, url_for
from flask_login import LoginManager, current_user
# from dotenv import load_dotenv  # <-- Suppression de cette ligne

# Ajoutez le répertoire racine au chemin Python pour les imports absolus
# Cela est nécessaire lorsque le fichier est exécuté directement.
if __name__ == '__main__':
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Initialisation Flask
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'votre-cle-secrete-tres-longue-et-complexe')

# Configuration de la base de données (NE PAS METTRE LES INFOS EN DUR)
db_config = {
    'host': os.environ.get('DB_HOST'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'database': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'charset': 'utf8mb4',
    'use_unicode': True,
    'autocommit': True
}

# Assurez-vous d'importer les classes ModelManager, DatabaseManager et Utilisateur
from app.models import DatabaseManager, ModelManager, Utilisateur

# Initialiser les gestionnaires de modèles avec la configuration de la base de données
# Le bloc with app.app_context() est nécessaire si le ModelManager a besoin de current_app
with app.app_context():
    app.config['DB_CONFIG'] = db_config
    db_manager = DatabaseManager(app.config['DB_CONFIG'])
    app.model_manager = ModelManager(db_manager)

# Configuration Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# Fonction user_loader requise par Flask-Login
@login_manager.user_loader
def load_user(user_id):
    # Charge un utilisateur depuis la base de données via l'ID
    return Utilisateur.get(user_id)

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

# --- NOUVEAU --- Route d'accueil pour éviter la page blanche
@app.route('/')
def index():
    if current_user.is_authenticated:
        # Redirige vers la page d'accueil si l'utilisateur est déjà connecté
        return redirect(url_for('admin.accueil'))
    # Sinon, redirige vers la page de connexion
    return redirect(url_for('auth.login'))
# --- FIN NOUVEAU ---

# Import des modèles et routes (APRES la création de l'app)
from app.routes import auth, admin, banking

# Enregistrement des blueprints
app.register_blueprint(auth.bp, url_prefix='/auth')
app.register_blueprint(admin.bp)
app.register_blueprint(banking.bp)

# Route de débogage temporaire pour vérifier les variables d'environnement
@app.route('/debug-env')
def debug_env():
    return jsonify(os.environ.copy())

# Initialisation de la base de données
def init_database():
    from app.models import init_db
    with app.app_context():
        init_db()

# Point d'entrée pour l'exécution directe (UNIQUEMENT pour le développement)
if __name__ == '__main__':
    init_database()
    app.run(debug=True)

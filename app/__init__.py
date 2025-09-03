#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask - Fichier d'initialisation principal
"""

import os
import sys
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv

# Ajoutez le répertoire racine au chemin Python pour les imports absolus
# Cela est nécessaire lorsque le fichier est exécuté directement.
if __name__ == '__main__':
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Charger les variables d'environnement
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

# Assurez-vous d'importer les classes ModelManager et DatabaseManager
from app.models import DatabaseManager, ModelManager

# Initialiser les gestionnaires de modèles avec la configuration de la base de données
# Le bloc with app.app_context() est nécessaire si le ModelManager a besoin de current_app
with app.app_context():
    app.config['DB_CONFIG'] = db_config  # Ajoutez cette ligne pour que 'DB_CONFIG' soit accessible
    db_manager = DatabaseManager(app.config['DB_CONFIG'])
    app.model_manager = ModelManager(db_manager)

# Configuration Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

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

# Import des modèles et routes (APRES la création de l'app)
from app.routes import auth, admin, banking

# Enregistrement des blueprints
app.register_blueprint(auth.bp)
app.register_blueprint(admin.bp)
app.register_blueprint(banking.bp)

# Initialisation de la base de données
def init_database():
    from app.models import init_db
    with app.app_context():
        init_db()

# Point d'entrée pour l'exécution directe (UNIQUEMENT pour le développement)
if __name__ == '__main__':
    init_database()
    app.run(debug=True)

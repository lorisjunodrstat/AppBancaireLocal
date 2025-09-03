import os
import sys
import logging
from flask import Flask, g, request
from flask_login import LoginManager
from dotenv import load_dotenv
from .models import DatabaseManager, ModelManager, load_user

# Configuration de la journalisation
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Chargement des variables d'environnement
load_dotenv()

# Initialisation de Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'votre-cle-secrete-tres-longue-et-complexe')

# Configuration de la base de données via la configuration Flask
app.config['DB_CONFIG'] = {
    'host': os.environ.get('DB_HOST'),
    'port': int(os.environ.get('DB_PORT', 3306)),
    'database': os.environ.get('DB_NAME'),
    'user': os.environ.get('DB_USER'),
    'password': os.environ.get('DB_PASSWORD'),
    'charset': 'utf8mb4',
    'use_unicode': True,
    'autocommit': True
}

# Initialisation de Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# Enregistrement de la fonction de chargement d'utilisateur
login_manager.user_loader(load_user)

# ===========================
# Initialisation de la BDD
# ===========================
# Cette fonction est appelée avant chaque requête pour s'assurer que les gestionnaires sont disponibles
@app.before_request
def before_request():
    if not hasattr(g, 'db_manager'):
        g.db_manager = DatabaseManager(app.config['DB_CONFIG'])
    if not hasattr(g, 'model_manager'):
        g.model_manager = ModelManager(g.db_manager)

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

# Import et enregistrement des blueprints
from app.routes import auth, admin, banking
app.register_blueprint(auth.bp)
app.register_blueprint(admin.bp)
app.register_blueprint(banking.bp)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Application Flask complète avec gestion d'utilisateurs et comptes bancaires
Compatible développement local MAMP et production
"""

import sys
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import Error
import calendar
from datetime import datetime, timedelta, date
from decimal import Decimal
import logging
from logging.handlers import RotatingFileHandler




# Configuration du répertoire de templates
template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates')

# Initialisation Flask
app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.environ.get('SECRET_KEY', 'votre-cle-secrete-changez-moi')

# Configuration de la base de données MAMP (qui fonctionne)
DB_CONFIG = {
    'host': '127.0.0.1',     # Configuration MAMP qui fonctionne
    'port': 8889,            # Port MAMP
    'database': 'banking2',   # Votre base de données
    'user': 'root',
    'password': 'root',
    'charset': 'utf8mb4',
    'use_unicode': True,
    'autocommit': True
}

# Import des modèles après configuration
from models import Utilisateur
from banking_routes import init_banking_routes

# Configuration de base
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),  # Fichier de logs
        logging.StreamHandler()          # Sortie console
    ]
)
# ===========================
# FLASK-LOGIN SETUP
# ===========================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

@login_manager.user_loader
def load_user(user_id):
    return Utilisateur.get_by_id(user_id)

@app.template_filter('format_date')
def format_date_filter(value, format='%d.%m.%Y'):
    """Formate une date en string selon le format donné"""
    if isinstance(value, str):
        return value  # Déjà formaté
    return value.strftime(format)

# ===========================
# FONCTIONS UTILITAIRES DB
# ===========================

def get_db_connection():
    """Établit une connexion à la base de données MySQL"""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as e:
        print(f"Erreur de connexion à la base de données: {e}")
        return None

def init_database():
    """Initialise la base de données avec les tables nécessaires"""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        
        # Création de la table utilisateurs (si elle n'existe pas déjà)
        create_users_table = """
        CREATE TABLE IF NOT EXISTS utilisateurs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nom VARCHAR(100) NOT NULL,
            email VARCHAR(150) UNIQUE NOT NULL,
            mot_de_passe VARCHAR(255),
            date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            date_modification TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            actif BOOLEAN DEFAULT TRUE,
            
            INDEX idx_email (email),
            INDEX idx_actif (actif),
            INDEX idx_date_creation (date_creation)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """
        
        try:
            cursor.execute(create_users_table)
            print("✅ Table 'utilisateurs' vérifiée/créée")
        except Error as e:
            print(f"❌ Erreur lors de la création de la table utilisateurs: {e}")
        finally:
            cursor.close()
            connection.close()

# ===========================
# ROUTES AUTH
# ===========================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not email or not password:
            flash("Veuillez remplir tous les champs", "error")
            return render_template('auth/login.html', active_tab='login')
        
        user = Utilisateur.get_by_email(email)
        if user :#and (user.mot_de_passe == password or check_password_hash(user.mot_de_passe, password)):
        #if user and check_password_hash(user.mot_de_passe, password):
            login_user(user)
            print(f"Utilisateur {user.email} connecté")
            flash("Connexion réussie !", "success")
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('banking_dashboard'))
        else:
            print(f"Échec de connexion pour {email} avec le {password}")
            flash("Email ou mot de passe incorrect", "error")

    
    return render_template('auth/login.html', active_tab='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        print(f'Voici les requêtes : {nom} {prenom} {email} {password} {confirm_password}')
        if not all([nom, prenom, email, password, confirm_password]):
            flash("Veuillez remplir tous les champs", "error")
            return render_template('auth/login.html', active_tab='register')
        
        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas", "error")
            return render_template('auth/login.html', active_tab='register')
        
        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères", "error")
            return render_template('auth/login.html', active_tab='register')
        
        if Utilisateur.get_by_email(email):
            flash("Cet email est déjà utilisé", "error")
            return render_template('auth/login.html', active_tab='register')
        
        #hashed_password = generate_password_hash(password)
        password = generate_password_hash(password)
        if Utilisateur.create(nom, prenom, email, password):
            flash("Compte créé avec succès ! Connectez-vous.", "success")
            return redirect(url_for('login'))
        else:
            flash("Erreur lors de l'inscription", "error")
    
    return render_template('auth/login.html', active_tab='register')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for('login'))

# ============================================
# ROUTES POUR LA GESTION DES UTILISATEURS
# ============================================

@app.route('/')
def index():
    """Page d'accueil"""
    if current_user.is_authenticated:
        return redirect(url_for('banking_dashboard'))
    return redirect(url_for('login'))

@app.route('/liste_utilisateurs')
@login_required
def liste_utilisateurs():
    """Affiche la liste des utilisateurs (admin)"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM utilisateurs WHERE actif = TRUE ORDER BY date_creation DESC LIMIT 50")
            utilisateurs = cursor.fetchall()
            cursor.close()
            connection.close()
            return render_template('admin/liste_utilisateurs.html', utilisateurs=utilisateurs)
        except Error as e:
            flash(f'Erreur lors de la récupération des données: {str(e)}', 'error')
            return render_template('admin/liste_utilisateurs.html', utilisateurs=[])
    else:
        flash('Impossible de se connecter à la base de données', 'error')
        return render_template('admin/liste_utilisateurs.html', utilisateurs=[])

@app.route('/ajouter_utilisateur', methods=['GET', 'POST'])
@login_required
def ajouter_utilisateur():
    """Ajoute un nouvel utilisateur"""
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not nom or not email or not password:
            flash('Le nom, email et mot de passe sont obligatoires', 'error')
            return render_template('admin/ajouter_utilisateur.html')
        
        if Utilisateur.get_by_email(email):
            flash('Cet email existe déjà', 'error')
            return render_template('admin/ajouter_utilisateur.html')
        
        hashed_password = generate_password_hash(password)
        if Utilisateur.create(nom, email, hashed_password):
            flash(f'Utilisateur {nom} ajouté avec succès !', 'success')
            return redirect(url_for('liste_utilisateurs'))
        else:
            flash('Erreur lors de l\'ajout', 'error')
    
    return render_template('admin/ajouter_utilisateur.html')

@app.route('/supprimer_utilisateur/<int:user_id>')
@login_required
def supprimer_utilisateur(user_id):
    """Supprime un utilisateur (soft delete)"""
    if user_id == current_user.id:
        flash('Vous ne pouvez pas supprimer votre propre compte', 'error')
        return redirect(url_for('liste_utilisateurs'))
    
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            
            # Vérifier s'il y a des comptes bancaires liés
            cursor.execute("SELECT COUNT(*) FROM comptes_principaux WHERE utilisateur_id = %s AND actif = TRUE", (user_id,))
            nb_comptes = cursor.fetchone()[0]
            
            if nb_comptes > 0:
                flash('Impossible de supprimer un utilisateur qui a des comptes bancaires actifs', 'error')
            else:
                # Soft delete
                cursor.execute("UPDATE utilisateurs SET actif = FALSE WHERE id = %s", (user_id,))
                if cursor.rowcount > 0:
                    flash('Utilisateur supprimé avec succès', 'success')
                else:
                    flash('Utilisateur non trouvé', 'error')
            
            cursor.close()
            connection.close()
        except Error as e:
            flash(f'Erreur lors de la suppression: {str(e)}', 'error')
    else:
        flash('Impossible de se connecter à la base de données', 'error')
    
    return redirect(url_for('liste_utilisateurs'))

@app.route('/utilisateur/<int:user_id>')
@app.route('/profil_utilisateur')
@login_required
def detail_utilisateur(user_id=None):
    """Page de détail d'un utilisateur avec ses comptes bancaires"""
    if user_id is None:
        user_id = current_user.id
    
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Récupérer l'utilisateur
            cursor.execute("SELECT * FROM utilisateurs WHERE id = %s AND actif = TRUE", (user_id,))
            utilisateur = cursor.fetchone()
            
            if not utilisateur:
                flash('Utilisateur non trouvé', 'error')
                return redirect(url_for('banking_dashboard'))
            
            # Récupérer ses comptes bancaires
            cursor.execute("""
                SELECT c.*, b.nom as nom_banque, b.couleur as couleur_banque
                FROM comptes_principaux c
                LEFT JOIN banques b ON c.banque_id = b.id
                WHERE c.utilisateur_id = %s AND c.actif = TRUE
                ORDER BY c.date_creation DESC
            """, (user_id,))
            comptes = cursor.fetchall()
            
            cursor.close()
            connection.close()
            
            return render_template('users/detail_utilisateur.html', 
                                 utilisateur=utilisateur, 
                                 comptes=comptes)
        except Error as e:
            flash(f'Erreur lors de la récupération des données: {str(e)}', 'error')
            return redirect(url_for('banking_dashboard'))
    else:
        flash('Impossible de se connecter à la base de données', 'error')
        return redirect(url_for('banking_dashboard'))

# ============================================
# API ROUTES
# ============================================

@app.route('/api/utilisateurs')
@login_required
def api_utilisateurs():
    """API JSON pour récupérer la liste des utilisateurs"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id, nom, email, date_creation FROM utilisateurs WHERE actif = TRUE ORDER BY date_creation DESC")
            utilisateurs = cursor.fetchall()
            cursor.close()
            connection.close()
            
            # Conversion des dates en string pour JSON
            for user in utilisateurs:
                if user['date_creation']:
                    user['date_creation'] = user['date_creation'].strftime('%Y-%m-%d %H:%M:%S')
            
            return jsonify({'success': True, 'utilisateurs': utilisateurs})
        except Error as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        return jsonify({'success': False, 'error': 'Connexion base de données impossible'})

@app.route('/test-db')
@login_required
def test_database():
    """Test de connexion à la base de données"""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            cursor.close()
            connection.close()
            
            tables_list = [table[0] for table in tables]
            return f"""
            <h2>✅ Connexion réussie !</h2>
            <p><strong>Version MySQL/MariaDB:</strong> {version[0]}</p>
            <p><strong>Base de données:</strong> {DB_CONFIG['database']}</p>
            <p><strong>Tables disponibles:</strong> {', '.join(tables_list)}</p>
            <p><a href="{url_for('banking_dashboard')}">Retour au dashboard</a></p>
            """
        except Error as e:
            return f"❌ Erreur lors du test: {str(e)}"
    else:
        return "❌ Impossible de se connecter à la base de données"


@app.errorhandler(500)
def internal_error(e):
    flash("Une erreur serveur s'est produite lors de la sauvegarde", "error")
    return redirect(url_for('heures_travail'))

if not app.debug:
    # Handler pour fichier de logs
    file_handler = RotatingFileHandler('app.log', maxBytes=1024*1024, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Démarrage de l\'application')
@app.template_filter('format_date')
def format_date_filter(date_value):
    if isinstance(date_value, date):
        # Si c'est déjà un objet date, formater directement
        return date_value.strftime('%d/%m/%Y')
    elif isinstance(date_value, str):
        # Si c'est une chaîne, la parser puis formater
        try:
            date_obj = datetime.strptime(date_value, '%Y-%m-%d').date()
            return date_obj.strftime('%d/%m/%Y')
        except ValueError:
            return date_value
    else:
        # Retourner la valeur telle quelle si on ne sait pas la traiter
        return date_value

    # Fonction pour obtenir le nom du mois
def get_month_name(month_num):
    months = {
        1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
        5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
        9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
    }
    return months.get(month_num, "")

@app.template_filter('month_name')
def month_name_filter(month_num):
    month_names = [
        '', 'Janvier', 'Février', 'Mars', 'Avril', 
        'Mai', 'Juin', 'Juillet', 'Août', 
        'Septembre', 'Octobre', 'Novembre', 'Décembre'
    ]
    return month_names[month_num] if 1 <= month_num <= 12 else ''

def generate_days(mois, semaine=0):
    today = date.today()
    annee = today.year
    
    if semaine > 0:
        # Générer les jours d'une semaine spécifique
        start_date = date.fromisocalendar(annee, semaine, 1)
        return [start_date + timedelta(days=i) for i in range(7)]
    else:
        # Générer tous les jours du mois
        _, num_days = calendar.monthrange(annee, mois)
        return [date(annee, mois, day) for day in range(1, num_days + 1)]
    
@app.context_processor
def utility_processor():
    return dict(get_month_name=get_month_name)
# ============================================
# GESTION DES ERREURS
# ============================================

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('errors/500.html'), 500

# ============================================
# INITIALISATION DES ROUTES BANCAIRES
# ============================================

# Initialiser les routes bancaires
init_banking_routes(app, DB_CONFIG)

# ============================================
# LANCEMENT DE L'APPLICATION
# ============================================

if __name__ == '__main__':
    # Initialisation de la base de données au démarrage
    print("=== INITIALISATION DE L'APPLICATION ===")
    init_database()
    
    # Test de connexion
    try:
        test_conn = mysql.connector.connect(**DB_CONFIG)
        test_conn.close()
        print(f"✅ Connexion à la base de données '{DB_CONFIG['database']}' réussie")
    except Exception as e:
        print(f"❌ Erreur de connexion à la base de données: {e}")
    
    # Affichage des routes enregistrées pour debug
    print("\n=== ROUTES ENREGISTRÉES ===")
    for rule in app.url_map.iter_rules():
        print(f"  {rule.endpoint} -> {rule.rule}")
    print("===========================\n")
    
    # Lancement en mode développement
    app.run(debug=True, host='0.0.0.0', port=5058)
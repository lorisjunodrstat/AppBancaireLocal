from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
from pymysql import Error, MySQLError
from ..models import Utilisateur
import logging

# Créez le Blueprint avec un préfixe d'URL '/auth'
bp = Blueprint('auth', __name__, url_prefix='/auth')

# ===========================
# ROUTES D'AUTHENTIFICATION
# ===========================

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            flash("Veuillez remplir tous les champs", "error")
            return render_template('auth/login.html', active_tab='login')

        config_db = current_app.config.get('DB_CONFIG')
        
        if not config_db:
            flash("Erreur de configuration de la base de données", "error")
            return render_template('auth/login.html', active_tab='login')

        try:
            connection = pymysql.connect(
                host=config_db['host'],
                port=config_db['port'],
                user=config_db['user'],
                password=config_db['password'],
                database=config_db['database'],
                charset=config_db['charset'],
                cursorclass=pymysql.cursors.DictCursor
            )
            
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, nom, prenom, email, mot_de_passe FROM utilisateurs WHERE email = %s",
                        (email,)
                    )
                    row = cursor.fetchone()
                    
                    if row and check_password_hash(row['mot_de_passe'], password):
                        from app.models import Utilisateur
                        user = Utilisateur(
                            id=row['id'],
                            nom=row['nom'],
                            prenom=row['prenom'],
                            email=row['email'],
                            mot_de_passe=row['mot_de_passe']
                        )
                        login_user(user, remember=True)  # Ajoutez remember=True pour maintenir la session
                        logging.info(f"Utilisateur {user.email} connecté")
                        flash("Connexion réussie !", "success")
                        
                        # REDIRECTION IMMÉDIATE ET FORCÉE
                        return redirect(url_for('banking.banking_dashboard'))
                    else:
                        logging.warning(f"Échec de connexion pour {email}")
                        flash("Email ou mot de passe incorrect", "error")
            finally:
                connection.close()
                
        except Exception as e:
            logging.error(f"Erreur lors de la connexion: {e}")
            flash("Erreur lors de la connexion", "error")

    return render_template('auth/login.html', active_tab='login')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        prenom = request.form.get('prenom', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if not all([nom, prenom, email, password, confirm_password]):
            flash("Veuillez remplir tous les champs", "error")
            return render_template('auth/login.html', active_tab='register')
        
        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas", "error")
            return render_template('auth/login.html', active_tab='register')
        
        if len(password) < 6:
            flash("Le mot de passe doit contenir au moins 6 caractères", "error")
            return render_template('auth/login.html', active_tab='register')
        
        # Ajoutez g.db_manager comme paramètre
        if Utilisateur.get_by_email(email, g.db_manager):
            flash("Cet email est déjà utilisé", "error")
            return render_template('auth/login.html', active_tab='register')
        
        hashed_password = generate_password_hash(password)
        # Ajoutez g.db_manager comme paramètre
        if Utilisateur.create(nom, prenom, email, hashed_password, g.db_manager):
            flash("Compte créé avec succès ! Connectez-vous.", "success")
            return redirect(url_for('auth.login'))
        else:
            flash("Erreur lors de l'inscription", "error")
    
    return render_template('auth/login.html', active_tab='register')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Vous avez été déconnecté.", "info")
    return redirect(url_for('auth.login'))

@bp.route('/change-password')
@login_required
def change_password():
    # Ajoutez ici la logique de changement de mot de passe
    return "Page de changement de mot de passe"

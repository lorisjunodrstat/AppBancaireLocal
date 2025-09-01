from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
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

        user = Utilisateur.get_by_email(email)
        if user and check_password_hash(user.mot_de_passe, password):
            login_user(user)
            logging.info(f"Utilisateur {user.email} connecté")
            flash("Connexion réussie !", "success")
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('banking.dashboard'))
        else:
            logging.warning(f"Échec de connexion pour {email}")
            flash("Email ou mot de passe incorrect", "error")

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
        
        if Utilisateur.get_by_email(email):
            flash("Cet email est déjà utilisé", "error")
            return render_template('auth/login.html', active_tab='register')
        
        hashed_password = generate_password_hash(password)
        if Utilisateur.create(nom, prenom, email, hashed_password):
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

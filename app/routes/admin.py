from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from ..models import Utilisateur
from mysql.connector import Error

# Créez le Blueprint avec le nom 'admin' et un préfixe d'URL
bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.before_request
@login_required
def before_request_check_admin():
    """
    Vérifie si l'utilisateur est un administrateur avant chaque requête.
    Redirige vers le dashboard si ce n'est pas le cas.
    """
    if not current_user.is_admin:
        flash("Accès non autorisé.", "error")
        return redirect(url_for('banking.dashboard'))

@bp.route('/utilisateurs')
def liste_utilisateurs():
    """Affiche la liste des utilisateurs."""
    utilisateurs = []
    try:
        # Utilisez g.db_manager passé en paramètre
        utilisateurs = Utilisateur.get_all(g.db_manager)
    except Exception as e:
        flash(f"Erreur lors de la récupération des utilisateurs : {str(e)}", 'error')
    return render_template('admin/liste_utilisateurs.html', utilisateurs=utilisateurs)

@bp.route('/ajouter_utilisateur', methods=['GET', 'POST'])
def ajouter_utilisateur():
    """Ajoute un nouvel utilisateur."""
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        
        if not nom or not email or not password:
            flash('Le nom, email et mot de passe sont obligatoires.', 'error')
            return render_template('admin/ajouter_utilisateur.html')
        
        try:
            # Utilisez g.db_manager passé en paramètre
            if Utilisateur.get_by_email(email, g.db_manager):
                flash("Cet email est déjà utilisé.", 'error')
                return render_template('admin/ajouter_utilisateur.html')
            
            hashed_password = generate_password_hash(password)
            # Utilisez g.db_manager passé en paramètre
            if Utilisateur.create(nom=nom, prenom="", email=email, mot_de_passe=hashed_password, db_manager=g.db_manager):
                flash(f"Utilisateur {nom} ajouté avec succès !", 'success')
                return redirect(url_for('admin.liste_utilisateurs'))
            else:
                flash("Erreur lors de l'ajout.", 'error')
        except Exception as e:
            flash(f"Erreur lors de l'ajout de l'utilisateur : {str(e)}", 'error')
    
    return render_template('admin/ajouter_utilisateur.html')

@bp.route('/supprimer_utilisateur/<int:user_id>')
def supprimer_utilisateur(user_id):
    """Supprime un utilisateur (soft delete)."""
    if user_id == current_user.id:
        flash('Vous ne pouvez pas supprimer votre propre compte.', 'error')
        return redirect(url_for('admin.liste_utilisateurs'))
    
    try:
        # Utilisez g.db_manager au lieu de db
        with g.db_manager.get_cursor(dictionary=True) as cursor:
            cursor.execute("SELECT COUNT(*) FROM comptes_principaux WHERE utilisateur_id = %s AND actif = TRUE", (user_id,))
            nb_comptes = cursor.fetchone()['COUNT(*)']
            
            if nb_comptes > 0:
                flash("Impossible de supprimer un utilisateur qui a des comptes bancaires actifs.", 'error')
            else:
                cursor.execute("UPDATE utilisateurs SET actif = FALSE WHERE id = %s", (user_id,))
                if cursor.rowcount > 0:
                    flash("Utilisateur supprimé avec succès.", 'success')
                else:
                    flash("Utilisateur non trouvé.", 'error')
    except Error as e:
        flash(f"Erreur lors de la suppression : {str(e)}", 'error')
    
    return redirect(url_for('admin.liste_utilisateurs'))

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import Utilisateur, get_db_connection

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/utilisateurs')
@login_required
def liste_utilisateurs():
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

# Ajoutez ici les autres routes admin...
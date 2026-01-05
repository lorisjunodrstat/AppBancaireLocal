from typing import Optional
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, current_app, g, session, abort, send_file
from flask_login import login_required, current_user
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, date, time
from calendar import monthrange
from app.models import DatabaseManager, Banque, ComptePrincipal, SousCompte, TransactionFinanciere, StatistiquesBancaires, PlanComptable, EcritureComptable, HeureTravail, Salaire, SyntheseHebdomadaire, SyntheseMensuelle, Contrat, Contacts, ContactCompte, ComptePrincipalRapport, CategorieComptable, Employe, Equipe, Planning, Competence, PlanningRegles
from io import StringIO
import os
from werkzeug.utils import secure_filename
import csv as csv_mod
import secrets
from io import BytesIO
from flask import send_file
import io
import traceback
import random
from collections import defaultdict
from . import db_csv_store
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from ..utils.pdf_salaire import generer_pdf_salaire
# --- DÉBUT DES AJOUTS (8 lignes) ---
from flask import _app_ctx_stack



# Création du blueprint
bp = Blueprint('heures', __name__)

# Configuration du logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Création des handlers
file_handler = logging.FileHandler('app.log')
stream_handler = logging.StreamHandler()

# Format des logs
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

# Ajout des handlers au logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
# Partie heures et salaires 


## ----- gestion des employés

@bp.route('/employes/dashboard')
@login_required
def dashboard_employes():
    current_user_id = current_user.id

    # Vérifier si l'utilisateur a déjà défini des types de cotisations ou indemnités
    contrat_model = g.models.contrat_model
    if not contrat_model.user_has_types_cotisation_or_indemnite(current_user_id):
        flash("Avant de gérer des employés, veuillez définir vos cotisations et indemnités dans la section Entreprise.", "info")
        return redirect(url_for('banking.gestion_entreprise'))

    # Sinon, continuer normalement
    employes = g.models.employe_model.get_all_by_user(current_user_id)
    all_employes = len(employes)
    
    maintenant = datetime.now()
    mois_request = request.args.get('mois')  # ← utiliser args (GET), pas form (POST)
    annee_request = request.args.get('annee')
    
    if mois_request and annee_request:
        mois = int(mois_request)
        annee = int(annee_request)
    else:
        mois = maintenant.month
        annee = maintenant.year

    heures_total_mois = 0
    salaire_total_mois = 0
    for employe in employes:
        heures = g.models.heure_model.get_heures_employe_mois(employe['id'], annee, mois)
        salaire = g.models.salaire_model.get_salaire_employe_mois(employe['id'], annee, mois)
        heures_total_mois += heures
        salaire_total_mois += salaire

    return render_template(
        'employes/dashboard.html',
        today=date.today(),
        all_employes=all_employes,
        heures_total_mois=heures_total_mois,
        salaire_total_mois=salaire_total_mois,
        employes=employes,
        mois=mois,
        annee=annee
    )
# --- Types de cotisation ---
@bp.route('/cotisations/types')
@login_required
def liste_types_cotisation():
    current_user_id = current_user.id
    types = g.models.type_cotisation_model.get_all_by_user(current_user_id)
    return render_template('cotisations/types_list.html', types=types)

@bp.route('/cotisations/types/nouveau', methods=['GET', 'POST'])
@bp.route('/cotisations/types/<int:type_id>/editer', methods=['GET', 'POST'])
@login_required
def editer_type_cotisation(type_id=None):
    current_user_id = current_user.id
    type_cotisation = None

    if type_id:
        types = g.models.type_cotisation_model.get_all_by_user(current_user_id)
        type_cotisation = next((t for t in types if t['id'] == type_id), None)
        if not type_cotisation:
            abort(404)

    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        description = request.form.get('description', '').strip()
        est_obligatoire = bool(request.form.get('est_obligatoire'))

        if not nom:
            flash("Le nom du type de cotisation est requis.", "error")
        else:
            data = {'nom': nom, 'description': description, 'est_obligatoire': est_obligatoire}
            if type_id:
                if g.models.type_cotisation_model.update(type_id, current_user_id, data):
                    flash("Type de cotisation mis à jour.", "success")
                else:
                    flash("Aucune modification effectuée.", "warning")
            else:
                if g.models.type_cotisation_model.create(current_user_id, nom, description, est_obligatoire):
                    flash("Nouveau type de cotisation créé.", "success")
                else:
                    flash("Erreur lors de la création.", "error")
            return redirect(url_for('banking.liste_types_cotisation'))

    return render_template('cotisations/type_form.html', type=type_cotisation)

@bp.route('/cotisations/types/<int:type_id>/supprimer', methods=['POST'])
@login_required
def supprimer_type_cotisation(type_id):
    current_user_id = current_user.id
    if g.models.type_cotisation_model.delete(type_id, current_user_id):
        flash("Type de cotisation supprimé.", "success")
    else:
        flash("Impossible de supprimer ce type.", "error")
    return redirect(url_for('banking.liste_types_cotisation'))


# --- Types d'indemnité ---
@bp.route('/indemnites/types')
@login_required
def liste_types_indemnite():
    current_user_id = current_user.id
    types = g.models.type_indemnite_model.get_all_by_user(current_user_id)
    return render_template('indemnites/types_list.html', types=types)

@bp.route('/indemnites/types/nouveau', methods=['GET', 'POST'])
@bp.route('/indemnites/types/<int:type_id>/editer', methods=['GET', 'POST'])
@login_required
def editer_type_indemnite(type_id=None):
    current_user_id = current_user.id
    type_indemnite = None

    if type_id:
        types = g.models.type_indemnite_model.get_all_by_user(current_user_id)
        type_indemnite = next((t for t in types if t['id'] == type_id), None)
        if not type_indemnite:
            abort(404)

    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        description = request.form.get('description', '').strip()
        est_obligatoire = bool(request.form.get('est_obligatoire'))

        if not nom:
            flash("Le nom du type d'indemnité est requis.", "error")
        else:
            data = {'nom': nom, 'description': description, 'est_obligatoire': est_obligatoire}
            if type_id:
                if g.models.type_indemnite_model.update(type_id, current_user_id, data):
                    flash("Type d'indemnité mis à jour.", "success")
                else:
                    flash("Aucune modification effectuée.", "warning")
            else:
                if g.models.type_indemnite_model.create(current_user_id, nom, description, est_obligatoire):
                    flash("Nouveau type d'indemnité créé.", "success")
                else:
                    flash("Erreur lors de la création.", "error")
            return redirect(url_for('banking.liste_types_indemnite'))

    return render_template('indemnites/type_form.html', type=type_indemnite)

@bp.route('/indemnites/types/<int:type_id>/supprimer', methods=['POST'])
@login_required
def supprimer_type_indemnite(type_id):
    current_user_id = current_user.id
    if g.models.type_indemnite_model.delete(type_id, current_user_id):
        flash("Type d'indemnité supprimé.", "success")
    else:
        flash("Impossible de supprimer ce type.", "error")
    return redirect(url_for('banking.liste_types_indemnite'))

@bp.route('/employes/liste')
@login_required
def liste_employe(user_id):
    current_user_id = current_user.id
    employes = g.models.employe_model.get_all_by_user(current_user_id)
    return render_template('employes/liste.html', employes=employes)


@bp.route('/dashboard/nouvel_employe', methods=['GET', 'POST'])
@login_required
def create_employe():
    current_user_id = current_user.id
    if request.method == 'GET':
        return render_template('employes/creer_employe.html')
    elif request.method == 'POST':
        try:
            data = {
                'user_id': current_user_id,
                'nom': request.form.get('nom'),
                'prenom': request.form.get('prenom'),
                'email': request.form.get('email'),
                'telephone': request.form.get('telephone'),
                'rue': request.form.get('rue'),
                'code_postal': request.form.get('code_postal'),
                'commune': request.form.get('commune'),
                'date_de_naissance': request.form.get('date_de_naissance'),
                'No_AVS': request.form.get('No_AVS')
            }
            mandatory_fields = ('nom', 'prenom', 'No_AVS')
            if not all(field in data and data[field] for field in mandatory_fields) :
                flash("Le nom, le prénom et le numéro AVS sont oblîgatoires")
                return render_template('employed/creer_employe.html')
            success = g.models.employe_model.create(data)
            if success:
                flash("Nouvel employà créé avec succès", "success")
                return redirect(url_for('liste_employe'))
            else: 
                flash("Erreur lors de la création de l'employe avec les données suivantes : {data}", "error")
                return render_template('employes/creer_employe.html', form_data=data)
        except Exception as e:
            logging.error("Erreur lors de la creation employe: {e}")
            flash(f'Erreur lors de la création : {str(e)}', 'error')        
            return render_template('employes/creer_employe.html')

@bp.route('/dashboard/modifier_employe')
@login_required
def modifier_employe(employe_id, user_id):
    employe = g.models.employe_model.get_by_id(employe_id, user_id)
    if not employe:
        flash(f"Employe avec id={employe_id} non trouvé", "error")
        return redirect(url_for('liste_employes'))
    if request.method == "POST":
        try:
            data= {
                'user_id': user_id,
                'nom': request.form.get('nom'),
                'prenom': request.form.get('prenom'),
                'email': request.form.get('email'),
                'telephone': request.form.get('telephone'),
                'rue': request.form.get('rue'),
                'code_postal': request.form.get('code_postal'),
                'commune': request.form.get('commune'),
                'date_de_naissance': request.form.get('date_de_naissance'),
                'No_AVS': request.form.get('No_AVS')
            }
            success = g.models.employe_model.update(employe_id, user_id, data)
            if success:
                flash("Les informations de l'employé ont été mises à jour avec succès", "success")
                return redirect(url_for('liste_employes'))
            else:
                flash("Erreur lors de la mise à jour des informations de l'employé", "error")
                return render_template('employes/modifier_employe.html', employe=employe, form_data=data)
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de l'employé: {e}")
            flash(f'Erreur lors de la mise à jour : {str(e)}', 'error')
            return render_template('employes/modifier_employe.html', employe=employe)

@bp.route('/employes/detail_employe/<int:employe_id>', methods=['GET'])
@login_required
def detail_employe(employe_id):
    employe = g.models.employe_model.get_by_id(employe_id, current_user.id)
    if not employe:
        flash("Employé non trouvé.", "error")
        return redirect(url_for('banking.liste_employe'))

    # Contrats liés à cet employé
    contrats = []
    tous_contrats = g.models.contrat_model.get_all_contrats(current_user.id)
    for c in tous_contrats:
        if c.get('employe_id') == employe_id:
            contrats.append(c)

    # Statistiques du mois actuel
    maintenant = datetime.now()
    annee = int(request.args.get('annee', maintenant.year))
    mois = int(request.args.get('mois', maintenant.month))

    heures_mois = g.models.heure_model.get_total_heures_mois(
        user_id=current_user.id,
        employeur=employe.get('employeur', ''),
        id_contrat=employe.get('id_contrat'),
        annee=annee,
        mois=mois
    )

    salaires = g.models.salaire_model.get_by_user_and_month(
        user_id=current_user.id,
        employeur=employe.get('employeur', ''),
        id_contrat=employe.get('id_contrat'),
        annee=annee,
        mois=mois
    )
    salaire_net = sum(s.get('salaire_net', 0) for s in salaires)

    return render_template(
        'employes/detail_employe.html',
        employe=employe,
        contrats=contrats,
        annee=annee,
        mois=mois,
        heures_mois=heures_mois,
        salaire_net=salaire_net
    )

@bp.route('/employes/contrat/<int:employe_id>/contrats')
@login_required
def gestion_contrats_employe(employe_id):
    employe = g.models.employe_model.get_by_id(employe_id, current_user.id)
    if not employe:
        flash("Employé non trouvé.", "error")
        return redirect(url_for('banking.liste_employe'))

    # Tous les contrats de l'utilisateur
    contrats = g.models.contrat_model.get_all_contrats(current_user.id)
    return render_template('employes/gestion_contrat.html', employe=employe, contrats=contrats)

@bp.route('/employes/<int:employe_id>/contrat/nouveau', methods=['GET', 'POST'])
@login_required
def creer_contrat_employe(employe_id):
    employe = g.models.employe_model.get_by_id(employe_id, current_user.id)
    if not employe:
        flash("Employé non trouvé.", "error")
        return redirect(url_for('banking.liste_employe'))

    if request.method == 'GET':
        return render_template('employes/creer_contrat_employe.html', employe=employe)

    # POST
    data = request.form.to_dict()
    data['user_id'] = current_user.id
    data['employe_id'] = employe_id  # ⬅️ Important !

    try:
        # Convertir les champs numériques
        for key in ['heures_hebdo', 'salaire_horaire']:
            if data.get(key):
                data[key] = float(data[key])
        for key in ['versement_10', 'versement_25']:
            data[key] = data.get(key) == 'on'

        success = g.models.contrat_model.create_or_update(data)
        if success:
            flash("Contrat créé avec succès.", "success")
            return redirect(url_for('banking.gestion_contrats_employe', employe_id=employe_id))
        else:
            flash("Erreur lors de la création du contrat.", "error")
            return render_template('employes/creer_contrat_employe.html', employe=employe, form_data=data)
    except Exception as e:
        logging.error(f"Erreur création contrat: {e}")
        flash(f"Erreur : {e}", "error")
        return render_template('employes/creer_contrat_employe.html', employe=employe)
    
@bp.route('/contrats/<int:contrat_id>/cotisations', methods=['GET', 'POST'])
@login_required
def gestion_cotisations_contrat(contrat_id):
    contrat = g.models.contrat_model.get_contrat_for_employe(current_user.id, contrat_id)
    if not contrat:
        flash("Contrat non trouvé.", "error")
        return redirect(url_for('banking.liste_employe'))

    annee = int(request.args.get('annee', datetime.now().year))

    if request.method == 'POST':
        # Sauvegarde des cotisations et indemnités
        data = {
            'annee': annee,
            'cotisations': [],
            'indemnites': []
        }
        # Exemple de données POST :
        # cotisation_type_1=taux&cotisation_base_1=brut → à parser
        # Pour simplifier, tu peux utiliser un formulaire avec listes :
        cotis = request.form.getlist('cotis_type[]')
        taux_c = request.form.getlist('cotis_taux[]')
        base_c = request.form.getlist('cotis_base[]')
        for i in range(len(cotis)):
            if cotis[i] and taux_c[i]:
                data['cotisations'].append({
                    'type_id': int(cotis[i]),
                    'taux': float(taux_c[i]),
                    'base': base_c[i] if base_c[i] else 'brut'
                })

        indem = request.form.getlist('indem_type[]')
        val_i = request.form.getlist('indem_valeur[]')
        for i in range(len(indem)):
            if indem[i] and val_i[i]:
                data['indemnites'].append({
                    'type_id': int(indem[i]),
                    'valeur': float(val_i[i])
                })

        g.models.contrat_model.sauvegarder_cotisations_et_indemnites(contrat_id, current_user.id, data)
        flash("Cotisations et indemnités sauvegardées.", "success")
        return redirect(url_for('banking.gestion_cotisations_contrat', contrat_id=contrat_id, annee=annee))

    # GET
    types_cotis = g.models.type_cotisation_model.get_all_by_user(current_user.id)
    types_indem = g.models.type_indemnite_model.get_all_by_user(current_user.id)
    cotis_actuelles = g.models.cotisations_contrat_model.get_for_contrat_and_annee(contrat_id, annee)
    indem_actuelles = g.models.indemnites_contrat_model.get_for_contrat_and_annee(contrat_id, annee)

    return render_template(
        'contrats/gestion_cotisations.html',
        contrat=contrat,
        annee=annee,
        types_cotis=types_cotis,
        types_indem=types_indem,
        cotis_actuelles=cotis_actuelles,
        indem_actuelles=indem_actuelles
    )

@bp.route('/employes/<int_employe_id>/supprimer_employe', methods = ['POST'])
@login_required
def supprimer_employe(employe_id, user_id):
    try:
        success = g.models.employe_model.delete(employe_id, user_id)
        if success:
            flash("Employé supprimer avec succès", "success")
        else:
            flash("Erreur lors de la suppression de l'employe", "error")
    except Exception as e:
        logging.error(f'Erreur lors de la suppression employe {employe_id} : {e}')
        flash(f"Erreur lors de la suppresion : {str(e)}")
    return redirect(url_for('banking.liste_employes'))

@bp.route('/employes/<int:employe_id>/planning')
@login_required
def planning_employe(employe_id):
    employe = g.models.employe_model.get_by_id(employe_id, current_user.id)
    if not employe:
        flash("Employé non trouvé.", "error")
        return redirect(url_for('banking.liste_employe'))

    annee = int(request.args.get('annee', datetime.now().year))
    mois = int(request.args.get('mois', datetime.now().month))

    # Récupérer les heures avec plages
    heures = g.models.heure_model.get_h1d_h2f_for_period(
        user_id=current_user.id,
        employeur="TBD",  # ⚠️ Problème : ton modèle `HeureTravail` exige employeur/contrat
        id_contrat=1,     # → à revoir dans la DB
        annee=annee,
        mois=mois
    )

    return render_template(
        'planning/planning_employe.html',
        employe=employe,
        heures=heures,
        annee=annee,
        mois=mois
    )
def get_semaine_from_date(date_str: str):
    """
    Retourne les 7 jours de la semaine (lundi à dimanche)
    contenant la date donnée.
    """
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    # Trouver le lundi de la semaine
    lundi = date - timedelta(days=date.weekday())
    return [lundi + timedelta(days=i) for i in range(7)]
@bp.route('/employes/planning-employes')
@login_required
def planning_employes():
    user_id = current_user.id
    date_ref = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    semaine = get_semaine_from_date(date_ref)  # [lundi, mardi, ..., dimanche]

    # Charger équipes + employés
    equipes = g.models.equipe_model.get_all_by_user(user_id)
    for equipe in equipes:
        equipe['membres'] = g.models.employe_model.get_by_equipe(equipe['id'])

    # Charger tous les shifts de la semaine
    all_shifts = g.models.heure_model.get_shifts_for_week(user_id, semaine[0], semaine[-1])
    
    # Indexer par employe → jour → liste shifts
    shifts_by_employe_jour = defaultdict(lambda: defaultdict(list))
    for s in all_shifts:
        s['duree'] = s['heure_fin'] - s['heure_debut']
        s['valide'] = g.models.planning_validator.est_valide(s)
        key = s['date'].strftime('%Y-%m-%d')
        shifts_by_employe_jour[s['employe_id']][key].append(s)

    return render_template(
        'planning/planning.html',
        week_dates=semaine,
        equipes=equipes,
        shifts_by_employe_jour=shifts_by_employe_jour,
        prev_week=semaine[0] - timedelta(weeks=1),
        next_week=semaine[0] + timedelta(weeks=1)
    )

@bp.route('/planning/supprimer_jour', methods=['POST'])
@login_required
def planning_supprimer_jour():
    user_id = current_user.id
    date_str = request.form['date']
    employeur = request.form['employeur']
    id_contrat = int(request.form['id_contrat'])
    
    success = g.models.heure_model.delete_by_date(date_str, user_id, employeur, id_contrat)
    flash("Jour supprimé." if success else "Rien à supprimer.", "warning")
    return redirect(request.referrer or url_for('banking.planning_employes'))

# Exemple : copier → réutilise TON handle_copier_jour
@bp.route('/planning/copier_jour', methods=['POST'])
@login_required
def planning_copier_jour():
    return handle_copier_jour(request, current_user.id, 'planning', request.form['employeur'], int(request.form['id_contrat']))

# Exemple : simulation → réutilise TON handle_simulation
@bp.route('/planning/simulation_semaine', methods=['POST'])
@login_required
def planning_simulation_semaine():
    return handle_simulation(
        request,
        user_id=current_user.id,
        annee=int(request.form['annee']),
        mois=int(request.form['mois']),
        semaine=int(request.form['semaine']),
        mode='planning',
        employeur=request.form['employeur'],
        id_contrat=int(request.form['id_contrat'])
    )

# Réinitialisation semaine → réutilise TON handle_reset_all
@bp.route('/planning/reset_semaine', methods=['POST'])
@login_required
def planning_reset_semaine():
    return handle_reset_all(
        request,
        user_id=current_user.id,
        annee=int(request.form['annee']),
        mois=int(request.form['mois']),
        semaine=int(request.form['semaine']),
        mode='planning',
        employeur=request.form['employeur'],
        id_contrat=int(request.form['id_contrat'])
    )

# Modifier jour → charge les données et affiche le formulaire
@bp.route('/planning/modifier_jour', methods=['POST'])
@login_required
def planning_modifier_jour():
    user_id = current_user.id
    date_str = request.form['date']
    employe_id = request.form['employe_id']
    # ... autres params
    
    data = g.models.heure_model.get_by_date(date_str, user_id, request.form['employeur'], int(request.form['id_contrat']))
    if not data:
        data = {'plages': [], 'vacances': False}
    
    return render_template('planning/form_modifier_jour.html',
        date=date_str,
        employe_id=employe_id,
        data=data,
        annee=request.form['annee'],
        mois=request.form['mois'],
        semaine=request.form['semaine'],
        mode='planning',
        employeur=request.form['employeur'],
        id_contrat=request.form['id_contrat']
    )

# Sauvegarder jour → crée/écrase avec type_heures='simulees'
@bp.route('/planning/sauvegarder_jour', methods=['POST'])
@login_required
def planning_sauvegarder_jour():
    user_id = current_user.id
    date_str = request.form['date']
    employeur = request.form['employeur']
    id_contrat = int(request.form['id_contrat'])

    plages = []
    for i in [1, 2]:
        debut = request.form.get(f'plage{i}_debut')
        fin = request.form.get(f'plage{i}_fin')
        if debut and fin:
            plages.append({'debut': debut, 'fin': fin})

    payload = {
        'date': date_str,
        'user_id': user_id,
        'employeur': employeur,
        'id_contrat': id_contrat,
        'plages': plages,
        'vacances': bool(request.form.get('vacances')),
        'type_heures': 'simulees'  # ← CRUCIAL pour le planning
    }

    success = g.models.heure_model.create_or_update(payload)
    flash("Jour mis à jour." if success else "Erreur.", "success" if success else "error")
    
    return redirect(url_for('banking.planning_employes',
        annee=request.form['annee'],
        mois=request.form['mois'],
        semaine=request.form['semaine'],
        mode='planning',
        employeur=employeur,
        id_contrat=id_contrat
    ))
@bp.route('/synthese/mensuelle')
@login_required
def synthese_mensuelle():
    annee = int(request.args.get('annee', datetime.now().year))
    synthese = g.models.synthese_mensuelle_model.get_by_user_and_year(current_user.id, annee)
    employeurs = g.models.synthese_mensuelle_model.get_employeurs_distincts(current_user.id)
    
    # Préparer le SVG
    svg_data = g.models.synthese_mensuelle_model.prepare_svg_data_mensuel(current_user.id, annee)

    return render_template(
        'employes/mensuelle.html',
        annee=annee,
        synthese=synthese,
        employeurs=employeurs,
        svg_data=svg_data
    )


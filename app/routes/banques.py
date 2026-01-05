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
bp = Blueprint('banking', __name__)

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


@bp.route('/banques', methods=['GET'])
@login_required
def liste_banques():
    banques = g.models.banque_model.get_all()
    return render_template('banking/liste.html', banques=banques)

@bp.route('/banques/nouvelle', methods=['GET', 'POST'])
@login_required
def creer_banque():
    if request.method == 'POST':
        nom = request.form.get('nom')
        code_banque = request.form.get('code_banque')
        pays = request.form.get('pays')
        couleur = request.form.get('couleur')
        site_web = request.form.get('site_web')
        logo_url = request.form.get('logo_url')

        if nom and code_banque:
            success = g.models.banque_model.create_banque(nom, code_banque, pays, couleur, site_web, logo_url)
            if success:
                flash('Banque créée avec succès !', 'success')
                print(f'Banque créée: {nom} ({code_banque})')
                return redirect(url_for('liste_banques'))
            else:
                flash('Erreur lors de la création de la banque.', 'danger')
        else:
            flash('Veuillez remplir au moins le nom et le code banque.', 'warning')

    return render_template('banking/creer.html')

@bp.route('/banques/<int:banque_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_banque(banque_id):
    banque = g.models.banque_model.get_by_id(banque_id)
    if not banque:
        flash("Banque introuvable.", "danger")
        return redirect(url_for('banking.liste_banques'))

    if request.method == 'POST':
        nom = request.form.get('nom')
        code_banque = request.form.get('code_banque')
        pays = request.form.get('pays')
        couleur = request.form.get('couleur')
        site_web = request.form.get('site_web')
        logo_url = request.form.get('logo_url')

        success = g.models.banque_model.update_banque(banque_id, nom, code_banque, pays, couleur, site_web, logo_url)
        if success:
            flash("Banque modifiée avec succès.", "success")
            print(f'Banque modifiée: {nom} ({code_banque}) avec les données suivantes : {pays}, {couleur}, {site_web}, {logo_url}')
            return redirect(url_for('banking.liste_banques'))
        else:
            flash("Erreur lors de la modification.", "danger")

    return render_template('banking/edit.html', banque=banque)

@bp.route('/banques/<int:banque_id>/delete', methods=['POST'])
@login_required
def delete_banque(banque_id):
    success = g.models.banque_model.delete_banque(banque_id)
    if success:
        flash("Banque supprimée (désactivée) avec succès.", "success")
    else:
        flash("Erreur lors de la suppression.", "danger")
    return redirect(url_for('banking.liste_banques'))
    
@bp.route('/banking/compte/nouveau', methods=['GET', 'POST'])
@login_required
def banking_nouveau_compte():
    if request.method == 'POST':
        try:
            # Validation des données
            if not request.form['banque_id'] or not request.form['banque_id'].isdigit():
                flash('Veuillez sélectionner une banque valide', 'error')
                return redirect(url_for('banking.banking_nouveau_compte'))
            
            if not request.form['nom_compte'].strip():
                flash('Le nom du compte est obligatoire', 'error')
                return redirect(url_for('banking.banking_nouveau_compte'))
                
            if not request.form['numero_compte'].strip():
                flash('Le numéro de compte est obligatoire', 'error')
                return redirect(url_for('banking.banking_nouveau_compte'))
            
            # Préparation des données
            data = {
                'utilisateur_id': current_user.id,
                'banque_id': int(request.form['banque_id']),
                'nom_compte': request.form['nom_compte'].strip(),
                'numero_compte': request.form['numero_compte'].strip(),
                'iban': request.form.get('iban', '').strip(),
                'bic': request.form.get('bic', '').strip(),
                'type_compte': request.form['type_compte'],
                'solde': Decimal(request.form.get('solde', '0')),
                'solde_initial': Decimal(request.form.get('solde_initial', '0')),
                'devise': request.form.get('devise', 'CHF'),
                'date_ouverture': datetime.strptime(
                    request.form['date_ouverture'], '%Y-%m-%d'
                ).date() if request.form.get('date_ouverture') else datetime.now().date()
            }
            
            # Création du compte
            if g.models.compte_model.create(data):
                flash(f'Compte "{data["nom_compte"]}" créé avec succès!', 'success')
                return redirect(url_for('banking.banking_dashboard'))
            else:
                flash('Erreur lors de la création du compte. Vérifiez que la banque existe.', 'error')
        except ValueError as e:
            flash('Données invalides: veuillez vérifier les valeurs saisies', 'error')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'error')
    
    # Récupération des banques pour le formulaire
    banques = g.models.banque_model.get_all()
    return render_template('banking/nouveau_compte.html', banques=banques)

@bp.route('/banking/sous-compte/nouveau/<int:compte_id>', methods=['GET', 'POST'])
@login_required
def banking_nouveau_sous_compte(compte_id):
    user_id = current_user.id
    compte = g.models.compte_model.get_by_id(compte_id)
    if not compte or compte['utilisateur_id'] != user_id:
        flash('Compte principal non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))
    
    if request.method == 'POST':
        try:
            data = {
                'compte_principal_id': compte_id,
                'nom_sous_compte': request.form['nom_sous_compte'].strip(),
                'description': request.form.get('description', '').strip(),
                'objectif_montant': Decimal(request.form['objectif_montant']) if request.form.get('objectif_montant') else None,
                'couleur': request.form.get('couleur', '#28a745'),
                'icone': request.form.get('icone', 'piggy-bank'),
                'date_objectif': datetime.strptime(
                    request.form['date_objectif'], '%Y-%m-%d'
                ).date() if request.form.get('date_objectif') else None,
                'utilisateur_id': user_id
            }
            if  g.models.sous_compte_model.create(data):
                flash(f'Sous-compte "{data["nom_sous_compte"]}" créé avec succès!', 'success')
                return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
            flash('Erreur lors de la création du sous-compte', 'error')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'error')
    
    return render_template('banking/nouveau_sous_compte.html', compte=compte)

@bp.route('/banking')
@login_required
def banking_dashboard():
    user_id = current_user.id
    logger.debug(f'Accès au dashboard bancaire pour l\'utilisateur {user_id}')
    stats = g.models.stats_model.get_resume_utilisateur(user_id)
    logger.debug(f'Stats récupérées: {stats}')
    repartition = g.models.stats_model.get_repartition_par_banque(user_id)
    comptes = get_comptes_utilisateur(user_id)
    logger.debug(f'Dashboard - 247 - Comptes récupérés: {len(comptes)} pour l\'utilisateur {user_id}')
        
    # Ajout des stats comptables
    now = datetime.now()
    first_day = now.replace(day=1)
    last_day = (first_day.replace(month=first_day.month % 12 + 1, year=first_day.year + first_day.month // 12) - timedelta(days=1))
    
    stats_comptables = g.models.ecriture_comptable_model.get_stats_by_categorie(
        user_id=user_id,
        date_from=first_day.strftime('%Y-%m-%d'),
        date_to=last_day.strftime('%Y-%m-%d')
    )
    les_comptes = []
    for c in comptes:
        c = les_comptes.append(g.models.compte_model.get_by_id(c['id']))
    recettes_mois = sum(s['total_recettes'] or 0 for s in stats_comptables)
    depenses_mois = sum(s['total_depenses'] or 0 for s in stats_comptables)
    
    return render_template('banking/dashboard.html', 
                        comptes=comptes, 
                        stats=stats, 
                        repartition=repartition,
                        recettes_mois=recettes_mois,
                        depenses_mois=depenses_mois,
                        les_comptes=les_comptes)

@bp.route('/banking/compte/<int:compte_id>')
@login_required
def banking_compte_detail(compte_id):
    user_id = current_user.id
    compte = g.models.compte_model.get_by_id(compte_id)

    if not compte or compte['utilisateur_id'] != user_id:
        flash('Compte non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))
    
    pf = g.models.periode_favorite_model.get_by_user_and_compte(user_id, compte_id, 'principal')
    if pf:
        date_debut_str = pf['date_debut'].strftime('%Y-%m-%d')
        date_fin_str = pf['date_fin'].strftime('%Y-%m-%d')
    
    # Paramètre de filtrage et tri
    sort = request.args.get('sort', 'date_desc')
    filter_type = request.args.get('filter_type', 'tous')
    filter_min_amount = request.args.get('filter_min_amount')
    filter_max_amount = request.args.get('filter_max_amount')
    search_query = request.args.get('search', '').strip()
    filter_categorie = request.args.get('filter_categorie', 'tous')
    toutes_categories = g.models.categorie_transaction_model.get_categories_utilisateur(user_id)
    # Gestion de la période sélectionnée
    periode = request.args.get('periode', 'mois')
    
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')
    mois_select = request.args.get('mois_select')
    annee_select = request.args.get('annee_select')
    
    # Calcul des dates selon la période
    maintenant = datetime.now()
    debut = None
    fin = None
    libelle_periode = "période personnalisée"
    
    if periode == 'personnalisee' and date_debut_str and date_fin_str:
        try:
            debut = datetime.strptime(date_debut_str, '%Y-%m-%d')
            fin = datetime.strptime(date_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            flash('Dates personnalisées invalides', 'error')
            return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
    elif periode == 'mois_annee' and mois_select and annee_select:
        try:
            mois = int(mois_select)
            annee = int(annee_select)
            debut = datetime(annee, mois, 1)
            fin = (debut + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            fin = fin.replace(hour=23, minute=59, second=59)
            libelle_periode = debut.strftime('%B %Y')
        except ValueError:
            flash('Mois/Année invalides', 'error')
            return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
    elif periode == 'annee':
        debut = maintenant.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        fin = maintenant.replace(month=12, day=31, hour=23, minute=59, second=59)
        libelle_periode = "Cette année"
    elif periode == 'trimestre':
        trimestre = (maintenant.month - 1) // 3 + 1
        debut = maintenant.replace(month=(trimestre-1)*3+1, day=1, hour=0, minute=0, second=0, microsecond=0)
        fin_mois = (debut.replace(month=debut.month+3, day=1) - timedelta(days=1))
        fin = fin_mois.replace(hour=23, minute=59, second=59)
        libelle_periode = f"{['1er', '2ème', '3ème', '4ème'][trimestre-1]} trimestre"
    else:  # mois par défaut
        if pf:
            if isinstance(pf['date_debut'], datetime):
                debut = pf['date_debut'].replace(hour=0, minute=0, second=0, microsecond=0)
                fin = pf['date_fin'].replace(hour=23, minute=59, second=59, microsecond=0)
            else:
                debut = datetime.combine(pf['date_debut'], time.min)
                fin = datetime.combine(pf['date_fin'], time.max).replace(microsecond=0)
            libelle_periode = f"Période favorite : {pf['nom']}"
            periode = 'favorite'
        else:
            debut = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            fin_mois = (debut.replace(month=debut.month+1, day=1) - timedelta(days=1))
            fin = fin_mois.replace(hour=23, minute=59, second=59)
            libelle_periode = "Ce mois"
            periode = 'mois'
    
    # Récupération des mouvements avec la nouvelle classe unifiée
    mouvements = g.models.transaction_financiere_model.get_historique_compte(
        compte_type='compte_principal',
        compte_id=compte_id,
        user_id=user_id,
        date_from=debut.strftime('%Y-%m-%d'),
        date_to=fin.strftime('%Y-%m-%d'),
        limit=200
    )
    
    # 🔥 NOUVEAU : Récupérer les catégories pour chaque transaction
    categories_par_transaction = {}
    for mouvement in mouvements:
        categories = g.models.categorie_transaction_model.get_categories_transaction(
            mouvement['id'], 
            user_id
        )
        categories_par_transaction[mouvement['id']] = categories
    
    # Utiliser les statistiques corrigées plutôt que le calcul manuel
    stats_compte = g.models.transaction_financiere_model.get_statistiques_compte(
        compte_type='compte_principal',
        compte_id=compte_id,
        user_id=user_id,
        date_debut=debut.strftime('%Y-%m-%d'),
        date_fin=fin.strftime('%Y-%m-%d')
    )
    
    # Filtrer les mouvements
    filtred_mouvements = mouvements
    if filter_type != 'tous':
        if filter_type == 'entree':
            filtred_mouvements = [m for m in filtred_mouvements if m['type_transaction'] in ['depot', 'transfert_entrant', 'transfert_sous_vers_compte', 'recredit_annulation']]
        elif filter_type == 'sortie':
            filtred_mouvements = [m for m in filtred_mouvements if m['type_transaction'] in ['retrait', 'transfert_sortant', 'transfert_externe', 'transfert_compte_vers_sous']]
        elif filter_type == 'transfert':
            filtred_mouvements = [m for m in filtred_mouvements if 'transfert' in m['type_transaction']]
        elif filter_type == 'Transfert_Compte_Vers_Sous':
            filtred_mouvements = [m for m in filtred_mouvements if m['type_transaction']  in ['transfert_compte_vers_sous' ]]
        elif filter_type == 'Transfert_Sous_Vers_Compte':
            filtred_mouvements = [m for m in filtred_mouvements if m['type_transaction']  in ['transfert_sous_vers_compte' ]]
        elif filter_type == 'Transfert_intra_compte':
            filtred_mouvements = [m for m in filtred_mouvements if m['type_transaction']  in ['transfert_compte_vers_sous', 'transfert_sous_vers_compte' ]]

    if filter_min_amount:
        try:
            min_amount = Decimal(filter_min_amount)
            filtred_mouvements = [m for m in filtred_mouvements if m['montant'] >= min_amount]
        except InvalidOperation:
            flash('Montant minimum invalide', 'error')
    if filter_max_amount:
        try:
            max_amount = Decimal(filter_max_amount)
            filtred_mouvements = [m for m in filtred_mouvements if m['montant'] <= max_amount]
        except InvalidOperation:
            flash('Montant maximum invalide', 'error')
    if search_query:
        search_lower = search_query.lower()
        filtred_mouvements = [
            m for m in filtred_mouvements 
            if (m.get('description','') and search_lower in m['description'].lower()) 
            or (m.get('categorie', '') and search_lower in m['categorie'].lower())
            or (m.get('reference', '') and search_lower in m['reference'].lower())
            or (m.get('beneficiaire', '') and search_lower in m['beneficiaire'].lower())
        ]
    if filter_categorie != 'tous':
        try:
            categorie_id = int(filter_categorie)
            # Filtrer les mouvements : ne garder que ceux qui ont cette catégorie
            filtred_mouvements = [m for m in filtred_mouvements 
                                  if any(cat['id'] == categorie_id for cat in categories_par_transaction.get(m['id'], []))]
        except ValueError:
            # Si la conversion en entier échoue, on ignore le filtre
            pass

    # Correction des totaux - utilisation des statistiques plutôt que du calcul manuel
    total_recettes = Decimal(str(stats_compte.get('total_entrees', 0))) if stats_compte else Decimal('0')
    total_depenses = Decimal(str(stats_compte.get('total_sorties', 0))) if stats_compte else Decimal('0')

    # Récupération des données existantes
    sous_comptes = g.models.sous_compte_model.get_by_compte_principal_id(compte_id)
    solde_total = g.models.compte_model.get_solde_total_avec_sous_comptes(compte_id)
    
    # Préparation des données pour le template
    tresorerie_data = {
        'labels': ['Recettes', 'Dépenses'],
        'datasets': [{
            'data': [float(total_recettes), float(total_depenses)],
            'backgroundColor': ['#28a745', '#dc3545']
        }]
    }
    
    ecritures_non_liees = g.models.ecriture_comptable_model.get_ecritures_non_synchronisees(
        compte_id=compte_id,
        user_id=current_user.id
    )
    
    nb_jours_periode = (fin - debut).days
    transferts_externes_pending = g.models.transaction_financiere_model.get_transferts_externes_pending(user_id)
    
    # Appel de la fonction (inchangé, car elle gère maintenant le report de solde)
    soldes_quotidiens = g.models.transaction_financiere_model.get_evolution_soldes_quotidiens_compte(
        compte_id=compte_id, 
        user_id=user_id, 
        date_debut=debut.strftime('%Y-%m-%d'),
        date_fin=fin.strftime('%Y-%m-%d')
    )

    # Préparation des données pour le graphique SVG
    largeur_svg = 800
    hauteur_svg = 400
    graphique_svg = None

    if soldes_quotidiens:
        soldes_values = [s['solde_apres'] for s in soldes_quotidiens]
        min_solde = min(soldes_values) if soldes_values else 0.0
        max_solde = max(soldes_values) if soldes_values else 0.0

        if min_solde == max_solde:
            if min_solde == 0:
                min_solde = -50.0
                max_solde = 50.0
            else:
                y_padding = abs(min_solde) * 0.1
                min_solde -= y_padding
                max_solde += y_padding
        else:
            y_padding = (max_solde - min_solde) * 0.05
            min_solde -= y_padding
            max_solde += y_padding

        n = len(soldes_quotidiens)
        points = []
        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8
        
        x_interval = plot_width / (n - 1) if n > 1 else 0
        solde_range = max_solde - min_solde

        for i, solde in enumerate(soldes_quotidiens):
            solde_float = solde['solde_apres']
            x = margin_x + i * x_interval if n > 1 else margin_x + plot_width / 2
            if solde_range != 0:
                y = margin_y + plot_height - ((solde_float - min_solde) / solde_range) * plot_height
            else:
                y = margin_y + plot_height / 2
            points.append(f"{x},{y}")

        graphique_svg = {
            'points': points,
            'min_solde': min_solde,
            'max_solde': max_solde,
            'dates': [s['date'].strftime('%d/%m/%Y') for s in soldes_quotidiens],
            'soldes': soldes_values,
            'nb_points': n,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height
        }
    liste_categories = g.models.categorie_transaction_model.get_categories_utilisateur(current_user.id)
    return render_template('banking/compte_detail.html',
                        compte=compte,
                        liste_categories=liste_categories,
                        sous_comptes=sous_comptes,
                        mouvements=filtred_mouvements,
                        filtred_mouvements=filtred_mouvements,
                        solde_total=solde_total,
                        tresorerie_data=tresorerie_data,
                        periode_selectionnee=periode,
                        libelle_periode=libelle_periode,
                        total_recettes=total_recettes,
                        total_depenses=total_depenses,
                        ecritures_non_liees=ecritures_non_liees,
                        transferts_externes_pending=transferts_externes_pending,
                        today=date.today(),
                        graphique_svg=graphique_svg,
                        date_debut_selected=date_debut_str,
                        date_fin_selected=date_fin_str,
                        mois_selected=mois_select,
                        annee_selected=annee_select,
                        nb_jours_periode=nb_jours_periode,
                        largeur_svg=largeur_svg,
                        hauteur_svg=hauteur_svg,
                        sort=sort,
                        pf=pf,
                        categories_par_transaction=categories_par_transaction,
                        toutes_categories=toutes_categories)  # 🔥 NOUVEAU : Passer les catégories



@bp.route('/banking/compte/<int:compte_id>/rapport')
@login_required
def banking_compte_rapport(compte_id):
    user_id = current_user.id


    # Vérifier l'appartenance du compte
    compte = g.models.compte_model.get_by_id(compte_id)
    if not compte or compte['utilisateur_id'] != user_id:
        flash('Compte non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))

    # Récupérer les paramètres de la requête (période)
    periode = request.args.get('periode', 'mensuel') # Valeur par défaut
    date_ref_str = request.args.get('date_ref') # Date de référence optionnelle
    
    if date_ref_str:
        try:
            date_ref = datetime.strptime(date_ref_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Format de date invalide.', 'error')
    else:
        date_ref = date.today()
            # On continuera avec la date par défaut (today)

    # Déterminer la plage de dates selon la période
    if periode == "hebdo":
        debut = date_ref - timedelta(days=date_ref.weekday())
        fin = debut + timedelta(days=6)
        titre_periode = f"Semaine du {debut.strftime('%d.%m.%Y')}"
    elif periode == "annuel":
        debut = date(date_ref.year, 1, 1)
        fin = date(date_ref.year, 12, 31)
        titre_periode = f"{date_ref.year}"
    else: # 'mensuel' par défaut
        debut = date_ref.replace(day=1)
        if date_ref.month == 12:
            fin = date(date_ref.year + 1, 1, 1) - timedelta(days=1)
        else:
            fin = date(date_ref.year, date_ref.month + 1, 1) - timedelta(days=1)
        titre_periode = f"{debut.strftime('%B %Y')}"

    # --- Données du Rapport ---

    # 1. Statistiques de base
    stats = g.models.transaction_financiere_model.get_statistiques_compte(
        compte_type='compte_principal',
        compte_id=compte_id,
        user_id=user_id,
        date_debut=debut.isoformat(),
        date_fin=fin.isoformat()
    )
    solde_initial = g.models.transaction_financiere_model._get_solde_avant_periode(compte_id, user_id, debut)
    solde_final = g.models.transaction_financiere_model.get_solde_courant('compte_principal', compte_id, user_id)

    # 2. Répartition par catégories (y compris 'Non catégorisé')
    # On réutilise la logique de `get_categories_par_type` mais en la modifiant pour inclure les transactions non catégorisées
    mapping_categories = {
        'depot': 'Dépôts',
        'retrait': 'Retraits',
        'transfert_entrant': 'Transferts entrants',
        'transfert_sortant': 'Transferts sortants',
        'transfert_compte_vers_sous': 'Transferts vers sous-comptes',
        'transfert_sous_vers_compte': 'Transferts depuis sous-comptes',
        'transfert_externe': 'Transferts externes',
        'recredit_annulation': 'Annulations / Recrédits'
    }

    # Récupérer TOUTES les transactions de la période
    tx_avec_cats, _ = g.models.transaction_financiere_model.get_all_user_transactions(
        user_id=user_id,
        date_from=debut.isoformat(),
        date_to=fin.isoformat(),
        #compte_source_id=compte_id,
        #compte_dest_id=compte_id,
        per_page=20000 # Récupérer toutes les transactions de la période
    )

    # Agréger les montants par catégorie ou par "Non catégorisé"
    repartition_cats = {}
    transactions_non_categorisees = []
    for tx in tx_avec_cats:
        tx_cats = g.models.categorie_transaction_model.get_categories_transaction(tx['id'], user_id)
        if not tx_cats:
            cat_name = "Non catégorisé"
            transactions_non_categorisees.append(tx)
        else:
            # Si une transaction a plusieurs catégories, on peut choisir la première ou agréger différemment
            # Pour simplifier, on prend la première.
            cat_name = tx_cats[0]['nom']
        repartition_cats[cat_name] = repartition_cats.get(cat_name, Decimal('0')) + Decimal(str(tx['montant']))

    # 3. Lien vers le comparatif
    lien_comparatif = url_for('banking.banking_comparaison', compte1_id=compte_id, periode=periode, date_ref=date_ref.isoformat())

    # 4. Générer un graphique SVG basique (exemple avec les catégories)
    # On peut réutiliser la logique de ton `generer_graphique_top_comptes_echanges` ou en créer un dédié
    # Pour l'instant, on va créer un graphique simple en barres horizontales
    def generer_graphique_categories_svg(cats_data):
        if not cats_data:
            return "<svg width='600' height='300'><text x='10' y='20'>Aucune donnée</text></svg>"
        
        # Trier les catégories par montant décroissant et limiter à 10
        items = sorted(cats_data.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Convertir TOUT en float dès le départ
        items_float = [(nom, float(montant)) for nom, montant in items]
        noms = [item[0] for item in items_float]
        montants = [item[1] for item in items_float]
        total = sum(montants) or 1.0  # float

        h_svg = max(300, len(noms) * 30)
        w_svg = 700
        ml, mr, mt, mb = 200, 40, 30, 30
        graph_w = w_svg - ml - mr
        graph_h = h_svg - mt - mb

        svg = f'<svg width="{w_svg}" height="{h_svg}" xmlns="http://www.w3.org/2000/svg">\n'
        for i, (nom, montant) in enumerate(items_float):  # ← utilise items_float ici
            y = mt + i * (graph_h / len(items_float))
            largeur = (montant / total) * graph_w
            couleur = f"hsl({360 * i / len(items_float)}, 60%, 50%)"
            svg += f'<rect x="{ml}" y="{y}" width="{largeur}" height="{graph_h/len(items_float)*0.8}" fill="{couleur}"/>\n'
            svg += f'<text x="{ml-10}" y="{y + graph_h/len(items_float)*0.4}" text-anchor="end">{nom[:20]}</text>\n'
            svg += f'<text x="{ml+largeur+10}" y="{y + graph_h/len(items_float)*0.4}">{montant:.2f}</text>\n'
        svg += '</svg>'
        return svg

    graphique_svg = generer_graphique_categories_svg(repartition_cats)
    liste_categories = g.models.categorie_transaction_model.get_categories_utilisateur(user_id)
    # --- Contexte pour le template ---
    context = {
        "compte": compte,
        "periode": periode,
        "titre_periode": titre_periode,
        "date_debut": debut,
        "date_fin": fin,
        'date_ref': date_ref,
        "resume": {
            "solde_initial": float(solde_initial),
            "solde_final": float(solde_final),
            "variation": float(solde_final - solde_initial),
            "total_entrees": stats.get('total_entrees', 0.0),
            "total_sorties": stats.get('total_sorties', 0.0),
        },
        "repartition_par_categories": repartition_cats,
        "all_transaxtions": tx_avec_cats,
        "transactions_non_categorisees": transactions_non_categorisees,
        "liste_categories": g.models.categorie_transaction_model.get_categories_utilisateur(user_id),
        "lien_comparatif": lien_comparatif,
        "graphique_svg": graphique_svg, # Ajout du graphique SVG
    }

    return render_template("banking/rapport_compte.html", **context)

@bp.route('/banking/comparaison')
@login_required
def banking_comparaison():
    user_id = current_user.id

    # Récupérer les paramètres de la requête
    compte1_id = request.args.get('compte1_id', type=int)
    periode = request.args.get('periode', 'mensuel') # Valeur par défaut
    date_ref_str = request.args.get('date_ref') # Date de référence optionnelle
    date_ref = date.today()
    if date_ref_str:
        try:
            date_ref = datetime.strptime(date_ref_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Format de date invalide.', 'error')
            # On continuera avec la date par défaut (today)

    # Vérifier que compte1_id est fourni
    if not compte1_id:
        flash('Compte 1 non spécifié pour la comparaison.', 'error')
        return redirect(url_for('banking.banking_dashboard'))

    # Récupérer le compte 1
    compte1 = g.models.compte_model.get_by_id(compte1_id)
    if not compte1 or compte1['utilisateur_id'] != user_id:
        flash('Compte 1 non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))

    # Déterminer la plage de dates selon la période (identique à la page rapport)
    if periode == "hebdo":
        debut = date_ref - timedelta(days=date_ref.weekday())
        fin = debut + timedelta(days=6)
        titre_periode = f"Semaine du {debut.strftime('%d.%m.%Y')}"
    elif periode == "annuel":
        debut = date(date_ref.year, 1, 1)
        fin = date(date_ref.year, 12, 31)
        titre_periode = f"{date_ref.year}"
    else: # 'mensuel' par défaut
        debut = date_ref.replace(day=1)
        if date_ref.month == 12:
            fin = date(date_ref.year + 1, 1, 1) - timedelta(days=1)
        else:
            fin = date(date_ref.year, date_ref.month + 1, 1) - timedelta(days=1)
        titre_periode = f"{debut.strftime('%B %Y')}"

    # Récupérer la liste des comptes de l'utilisateur pour le second sélecteur
    tous_les_comptes = g.models.compte_model.get_by_user_id(user_id)

    # Récupérer le compte 2 à partir des arguments GET ou POST (s'il est sélectionné)
    compte2_id = request.args.get('compte2_id', type=int)
    compte2 = None
    donnees_comparaison = {}
    graphique_svg = None
    if compte2_id:
        compte2 = g.models.compte_model.get_by_id(compte2_id)
        if not compte2 or compte2['utilisateur_id'] != user_id:
            flash('Compte 2 non trouvé ou non autorisé', 'error')
            compte2 = None # Réinitialiser
        else:
            # --- Générer les données de comparaison ---
            # Ici, tu peux réutiliser les méthodes de `transaction_model` que tu as déjà
            # Par exemple, `get_solde_courant`, `_get_daily_balances`, etc.
            # Et la méthode `compare_comptes_soldes_barres` que tu as aussi.
            # Exemple d'utilisation (à adapter selon tes besoins) :
            # soldes_compte1 = transaction_model._get_daily_balances(compte1_id, debut, fin, 'total')
            # soldes_compte2 = transaction_model._get_daily_balances(compte2_id, debut, fin, 'total')
            # graphique_svg = transaction_model.compare_comptes_soldes_barres(
            #     compte1_id, compte2_id, debut, fin, 'total', 'total'
            # )

            # Pour l'instant, on met un SVG vide ou un message
            graphique_svg = "<svg width='600' height='400'><text x='10' y='20'>Comparaison en cours de développement...</text></svg>"

            # Passer les données au template
            donnees_comparaison = {
                "compte1": compte1,
                "compte2": compte2,
                "periode": periode,
                "titre_periode": titre_periode,
                "date_debut": debut,
                "date_fin": fin,
                # ... autres données de comparaison ...
            }

    # Contexte pour le template
    context = {
        "tous_les_comptes": tous_les_comptes,
        "compte1_selectionne": compte1,
        "compte2_selectionne": compte2,
        "periode": periode,
        "date_ref": date_ref,
        "donnees_comparaison": donnees_comparaison,
        "graphique_svg": graphique_svg,
        # Pour les filtres de la page
        "titre_periode": titre_periode,
        "date_debut": debut,
        "date_fin": fin,
    }

    return render_template("banking/comparaison.html", **context)

@bp.route('/banking/compte/<int:compte_id>/comparer_soldes', methods=['GET', 'POST'])
@login_required
def banking_comparer_soldes(compte_id):
    logging.info("Début de la route banking_comparer_soldes")
    """Affiche la page de sélection pour la comparaison des soldes et génère le graphique."""
    user_id = current_user.id

    # Vérifier que le compte_id appartient à l'utilisateur (pour le bouton de retour)
    compte = g.models.compte_model.get_by_id(compte_id)
    if not compte or compte['utilisateur_id'] != user_id:
        flash('Compte non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))

    logging.info(f"Utilisateur connecté: {user_id}, Compte de référence: {compte_id}")

    try:
        logging.info("Récupération des comptes de l'utilisateur...")
        comptes = g.models.compte_model.get_by_user_id(user_id)
        logging.info(f'banking 557 Comptes récupérés pour la comparaison des soldes: {len(comptes)} pour l\'utilisateur {user_id}')
    except Exception as e:
        logging.error(f"Erreur lors de la récupération des comptes: {e}")
        flash("Erreur lors du chargement des comptes.", 'error')
        # Passer 'compte' ici aussi en cas d'erreur
        return render_template('banking/comparer_soldes.html', compte=compte, comptes=[], form_data={}, svg_code=None)

    # Initialisation des variables pour le template
    svg_code = None
    form_data = {
        'compte_id_1': '',
        'compte_id_2': '',
        'type_1': 'total',
        'type_2': 'total',
        'date_debut': '',
        'date_fin': '',
        'couleur_1_recette': '#0000FF',
        'couleur_1_depense': '#FF0000',
        'couleur_2_recette': '#00FF00',
        'couleur_2_depense': '#FF00FF'
    }
    logging.info("Variables initiales définies.")

    if request.method == 'POST':
        logging.info("Requête POST reçue.")
        # Récupérer les données du formulaire
        form_data = {
            'compte_id_1': request.form.get('compte_id_1', ''),
            'compte_id_2': request.form.get('compte_id_2', ''),
            'type_1': request.form.get('type_1', 'total'),
            'type_2': request.form.get('type_2', 'total'),
            'date_debut': request.form.get('date_debut', ''),
            'date_fin': request.form.get('date_fin', ''),
            'couleur_1_recette': request.form.get('couleur_1_recette', '#0000FF'),
            'couleur_1_depense': '#FF0000', # Fixé car on n'utilise qu'une couleur par compte-type
            'couleur_2_recette': request.form.get('couleur_2_recette', '#00FF00'),
            'couleur_2_depense': '#FF00FF',  # Fixé car on n'utilise qu'une couleur par compte-type
        }
        logging.info(f"Données du formulaire récupérées: {form_data}")

        # Validation de base
        if not all([form_data['compte_id_1'], form_data['compte_id_2'], form_data['date_debut'], form_data['date_fin']]):
            logging.warning("Formulaire incomplet.")
            flash('Veuillez remplir tous les champs obligatoires.', 'error')
        else:
            logging.info("Formulaire complet, début du traitement...")
            try:
                logging.info("Conversion des IDs et des dates...")
                compte_id_1 = int(form_data['compte_id_1'])
                compte_id_2 = int(form_data['compte_id_2'])
                date_debut = date.fromisoformat(form_data['date_debut'])
                date_fin = date.fromisoformat(form_data['date_fin'])
                logging.info(f"IDs et dates convertis. C1: {compte_id_1}, C2: {compte_id_2}, Du: {date_debut}, Au: {date_fin}")

                if date_debut > date_fin:
                    logging.error("Erreur: La date de début est postérieure à la date de fin.")
                    raise ValueError("La date de début ne peut pas être postérieure à la date de fin.")

                # Vérifier que les comptes appartiennent à l'utilisateur
                logging.info("Vérification de l'appartenance des comptes...")
                compte_1 = g.models.compte_model.get_by_id(compte_id_1)
                compte_2 = g.models.compte_model.get_by_id(compte_id_2)
                if not compte_1 or not compte_2 or compte_1['utilisateur_id'] != user_id or compte_2['utilisateur_id'] != user_id:
                    logging.error("Erreur: Un ou plusieurs comptes sont invalides ou non autorisés.")
                    raise ValueError("Un ou plusieurs comptes sont invalides ou non autorisés.")

                # Générer le graphique SVG en barres
                logging.info("Appel de la méthode compare_comptes_soldes_barres...")
                svg_code = g.models.transaction_financiere_model.compare_comptes_soldes_barres(
                    compte_id_1, compte_id_2,
                    date_debut, date_fin,
                    form_data['type_1'], form_data['type_2'],
                    form_data['couleur_1_recette'], form_data['couleur_2_recette'] # On passe les couleurs des recettes
                )
                logging.info("Graphique SVG généré avec succès.")

            except (ValueError, Exception) as e:
                logging.error(f"Erreur lors de la génération du graphique: {e}", exc_info=True) # exc_info=True pour avoir la stack trace
                flash(f"Erreur: {str(e)}", 'error')

    # Pré-remplir les dates si elles ne viennent pas du formulaire
    if not form_data['date_fin']:
        form_data['date_fin'] = date.today().isoformat()
        logging.info(f"Date de fin par défaut: {form_data['date_fin']}")
    if not form_data['date_debut']:
        form_data['date_debut'] = (date.today() - timedelta(days=30)).isoformat()
        logging.info(f"Date de début par défaut: {form_data['date_debut']}")

    logging.info("Rendu du template comparer_soldes.html.")
    try:
        return render_template('banking/comparer_soldes.html',
                            compte=compte, # <-- Ajouté ici
                            comptes=comptes,
                            form_data=form_data,
                            svg_code=svg_code)
    except Exception as e:
        logging.error(f"Erreur lors du rendu du template: {e}", exc_info=True)
        # Retourner une page d'erreur simple ou un message
        flash("Une erreur est survenue lors de l'affichage de la page.", 'error')
        # Passer 'compte' ici aussi
        return render_template('banking/comparer_soldes.html', compte=compte, comptes=[], form_data={}, svg_code=None)

@bp.route('/banking/compte/<int:compte_id>/top_echanges', methods=['GET', 'POST'])
@login_required
def banking_compte_top_echanges(compte_id):
    """Affiche les top comptes avec lesquels le compte a échangé de l'argent."""
    user_id = current_user.id
    compte = g.models.compte_model.get_by_id(compte_id)
    if not compte or compte['utilisateur_id'] != user_id:
        flash('Compte non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))

    # Valeurs par défaut
    date_debut = (date.today() - timedelta(days=90)).isoformat()
    date_fin = date.today().isoformat()
    direction = 'tous'
    limite = 40

    svg_code = None
    if request.method == 'POST':
        date_debut = request.form.get('date_debut', date_debut)
        date_fin = request.form.get('date_fin', date_fin)
        direction = request.form.get('direction', 'tous')
        limite = int(request.form.get('limite', 40))

    # Récupérer les données
    donnees = g.models.transaction_financiere_model.get_top_comptes_echanges(
        compte_id, user_id, date_debut, date_fin, direction, limite
    )

    # Générer le graphique
    if donnees:
        svg_code = g.models.transaction_financiere_model.generer_graphique_top_comptes_echanges(donnees)

    return render_template('banking/compte_top_echanges.html',
                         compte=compte,
                         svg_code=svg_code,
                         date_debut=date_debut,
                         date_fin=date_fin,
                         direction=direction,
                         limite=limite)

@bp.route('/banking/compte/<int:compte_id>/evolution_echanges', methods=['GET', 'POST'])
@login_required
def banking_compte_evolution_echanges(compte_id):
    user_id = current_user.id
    compte_source = g.models.compte_model.get_by_id(compte_id)
    if not compte_source or compte_source['utilisateur_id'] != user_id:
        flash('Compte non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))

    # Récupérer la liste des comptes avec lesquels il a échangé
    ##top_comptes = g.models.transaction_financiere_model.get_top_comptes_echanges(
    #    compte_id, user_id,
    #    (date.today() - timedelta(days=365)).isoformat(),
    #    date.today().isoformat(),
    #    'tous',
    #    100
    #)
    #logging.info(f"banking 726 Comptes cibles {len(top_comptes)} possibles pour le compte {compte_id} : {top_comptes} poir")
    #comptes_cibles_possibles = top_comptes
    #logging.info(f"banking 728 {len(comptes_cibles_possibles)} Comptes cibles possibles pour le compte {compte_id} : {comptes_cibles_possibles}")
    # Valeurs par défaut
    all_comptes = g.models.compte_model.get_all_accounts()
    comptes_cibles_possibles = [
        {'compte_id': compte['id'], 'nom_compte': compte['nom_compte']} 
        for compte in all_comptes
        if compte['id'] != compte_id # Exclure le compte source
        ]
    logging.info(f"banking XXX Comptes cibles {len(comptes_cibles_possibles)} possibles pour le compte {compte_id} (tous les comptes actifs de l'utilisateur sauf le compte source) : {comptes_cibles_possibles} ")
    date_debut = (date.today() - timedelta(days=90)).isoformat()
    date_fin = date.today().isoformat()
    comptes_cibles_ids = []
    type_graphique = 'lignes'
    couleur = '#4e79a7'  # Couleur par défaut pour le cumul
    cumuler = False

    svg_code = None
    if request.method == 'POST':
        date_debut = request.form.get('date_debut', date_debut)
        date_fin = request.form.get('date_fin', date_fin)
        comptes_cibles_ids = request.form.getlist('comptes_cibles')
        type_graphique = request.form.get('type_graphique', 'lignes')
        couleur = request.form.get('couleur', '#4e79a7')
        cumuler = request.form.get('cumuler') == 'on'

        if comptes_cibles_ids:
            # Récupérer les données brutes
            donnees_brutes = g.models.transaction_financiere_model.get_transactions_avec_comptes(
                compte_id, user_id, comptes_cibles_ids, date_debut, date_fin
            )
            # Structurer les données
            donnees_struct = g.models.transaction_financiere_model._structurer_donnees_pour_graphique(
                donnees_brutes, cumuler=cumuler
            )

            # Gestion des couleurs
            couleurs_a_utiliser = None
            if not cumuler and donnees_struct['series']: # Si non cumulé et qu'il y a des séries
                couleurs_a_utiliser = []
                # On suppose que les clés de 'series' sont les noms des comptes dans l'ordre
                # où ils ont été sélectionnés (ce n'est pas garanti par un dictionnaire, mais c'est souvent le cas en Python 3.7+)
                # Pour plus de fiabilité, on pourrait trier les clés par ordre d'apparition dans la liste initiale
                # Mais pour Flask/Jinja, on peut aussi envoyer les couleurs dans l'ordre des noms de série.
                noms_series = list(donnees_struct['series'].keys())
                for nom_serie in noms_series:
                    # Trouver l'ID du compte à partir du nom (nécessite une correspondance avec top_comptes)
                    # On va associer les couleurs dans l'ordre de sélection
                    # On récupère les couleurs envoyées via le formulaire
                    # On suppose que les couleurs sont envoyées dans l'ordre des IDs sélectionnés
                    couleur_envoyee = request.form.get(f'couleur_compte_{next((c["id"] for c in all_comptes if c["nom_compte"] == nom_serie), "unknown")}', None)
                    if couleur_envoyee:
                        couleurs_a_utiliser.append(couleur_envoyee)
                    else:
                        # Si aucune couleur spécifique n'est envoyée pour ce compte, utiliser une par défaut
                        couleurs_a_utiliser.append('#000000') # ou une couleur par défaut dynamique

            # Générer le graphique avec les nouvelles méthodes
            if type_graphique == 'barres':
                svg_code = g.models.transaction_financiere_model.generer_graphique_echanges_temporel_barres(
                    donnees_struct, couleurs_a_utiliser
                )
            else: # lignes
                svg_code = g.models.transaction_financiere_model.generer_graphique_echanges_temporel_lignes(
                    donnees_struct, couleurs_a_utiliser
                )

    return render_template('banking/compte_evolution_echanges.html',
                        compte_source=compte_source,
                        all_comptes=all_comptes,
                        comptes_cibles_possibles=comptes_cibles_possibles,
                        svg_code=svg_code,
                        date_debut=date_debut,
                        date_fin=date_fin,
                        comptes_cibles_ids=comptes_cibles_ids,
                        type_graphique=type_graphique,
                        couleur=couleur,
                        cumuler=cumuler)

@bp.route("/compte/<int:compte_id>/set_periode_favorite", methods=["POST"])
@login_required
def create_periode_favorite(compte_id):
    user_id = current_user.id
    compte = g.models.compte_model.get_by_id(compte_id)
    if compte:
        compte_type = 'principal'
    else:
        sous_compte = g.models.sous_compte_model.get_by_id(compte_id)
        if not sous_compte:
            flash("❌ Compte ou sous-compte introuvable.", "error")
            return redirect(url_for("banking.banking_comptes"))
        compte_type = 'sous_compte'
    nom = request.form.get("periode_nom")
    date_debut = request.form.get("date_debut")
    date_fin = request.form.get("date_fin")
    statut = request.form.get("statut", "active")
    logging.debug(f"banking 531 Création période favorite pour user {user_id}, compte {compte_id} ({compte_type}), nom: {nom}, début: {date_debut}, fin: {date_fin}, statut: {statut}")
    # Mettre à jour / insérer la période favorite
    nouveau_of = g.models.periode_favorite_model.create(
        user_id=user_id,
        compte_id=compte_id,
        compte_type=compte_type,
        nom=nom,
        date_debut=date_debut if date_debut else None,
        date_fin=date_fin if date_fin else None,
        statut='active'
    )
    if not nouveau_of:
        flash("❌ Erreur lors de la création de la période favorite pour {user_id}, compte {compte_id} ({compte_type}), nom: {nom}, début: {date_debut}, fin: {date_fin}, statut: {statut}", "error")
        return redirect(url_for("banking.banking_compte_detail", compte_id=compte_id))
    
    flash("✅ Période favorite mise à jour avec succès", "success")
    return redirect(url_for("banking.banking_compte_detail", compte_id=compte_id))

@bp.route("/compte/<int:compte_id>/modifier_periode_favorite/<int:periode_favorite_id>", methods=["POST"])
@login_required
def update_periode_favorite(compte_id, periode_favorite_id):
    user_id = current_user.id
    
    # Déterminer le type de compte
    compte = g.models.compte_model.get_by_id(compte_id)
    if compte:
        compte_type = 'principal'
    else:
        sous_compte = g.models.sous_compte_model.get_by_id(compte_id)
        if not sous_compte:
            flash("❌ Compte ou sous-compte introuvable.", "error")
            return redirect(url_for("banking.banking_comptes"))
        compte_type = 'sous_compte'

    # Récupérer la période favorite existante → c'est un dict
    pf = g.models.periode_favorite_model.get_by_user_and_compte(
        user_id=user_id,
        compte_id=compte_id,
        compte_type=compte_type
    )
    if not pf or pf['id'] != periode_favorite_id:
        flash("❌ Période favorite introuvable.", "error")
        return redirect(url_for("banking.banking_compte_detail", compte_id=compte_id))

    # Récupérer les valeurs du formulaire OU conserver les anciennes
    nom = request.form.get("nouveau_nom") or pf['nom']
    date_debut_str = request.form.get("nouveau_debut")
    date_fin_str = request.form.get("nouveau_fin")
    statut = request.form.get("nouveau_statut") or pf.get('statut') or "active"

    # Conserver les anciennes dates si non fournies
    date_debut = date_debut_str if date_debut_str else pf['date_debut']
    date_fin = date_fin_str if date_fin_str else pf['date_fin']

    # Vérifier que les dates ne sont pas None (la DB l'interdit)
    if date_debut is None or date_fin is None:
        flash("❌ Les dates de début et de fin sont obligatoires.", "error")
        return redirect(url_for("banking.banking_compte_detail", compte_id=compte_id))

    # Mettre à jour
    success = g.models.periode_favorite_model.update(
        periode_id=periode_favorite_id,
        user_id=user_id,
        nom=nom,
        date_debut=date_debut,
        date_fin=date_fin,
        statut=statut
    )

    if not success:
        flash("❌ Erreur lors de la mise à jour de la période favorite.", "error")
    else:
        flash("✅ Période favorite mise à jour avec succès.", "success")

    return redirect(url_for("banking.banking_compte_detail", compte_id=compte_id))

@bp.route('/banking/sous-compte/<int:sous_compte_id>')
@login_required
def banking_sous_compte_detail(sous_compte_id):
    user_id = current_user.id
    # Récupérer les comptes de l'utilisateur
    comptes_ = g.models.compte_model.get_by_user_id(user_id)
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')
    mois_select = request.args.get('mois_select')
    annee_select = request.args.get('annee_select')
    libelle_periode = "période personnalisée "
    maintenant = datetime.now()
    periode = request.args.get('periode', 'mois')  # Valeurs possibles: mois, trimestre, annee
    debut = None
    fin = None
    if periode == 'personnalisee' and date_debut_str and date_fin_str:
        try:
            debut = datetime.strptime(date_debut_str, '%Y-%m-%d')
            fin = datetime.strptime(date_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            flash('Dates personnalisées invalides', 'error')
            return redirect(url_for('banking.banking_sous_compte_detail', sous_compte_id=sous_compte_id))
    elif periode == 'mois_annee' and mois_select and annee_select:
        try:
            mois = int(mois_select)
            annee = int(annee_select)
            debut = datetime(annee, mois, 1)
            fin = (debut + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            fin = fin.replace(hour=23, minute=59, second=59)
            libelle_periode =debut.strftime('%B %Y')
        except ValueError:
            flash('Mois/Année invalides', 'error')
            return redirect(url_for('banking.banking_sous_compte_detail', sous_compte_id=sous_compte_id))
    elif periode == 'annee':
        debut = maintenant.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        fin = maintenant.replace(month=12, day=31, hour=23, minute=59, second=59)
        libelle_periode = "Cette année"
    elif periode == 'trimestre':
        trimestre = (maintenant.month - 1) // 3 + 1
        debut = maintenant.replace(month=(trimestre-1)*3+1, day=1, hour=0, minute=0, second=0, microsecond=0)
        fin_mois = (debut.replace(month=debut.month+3, day=1) - timedelta(days=1))
        fin = fin_mois.replace(hour=23, minute=59, second=59)
        libelle_periode = f"{['1er', '2ème', '3ème', '4ème'][trimestre-1]} trimestre"
    else:  # mois par défaut
        # Récupérer tous les sous-comptes de l'utilisateur
        debut = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        fin_mois = (debut.replace(month=debut.month+1, day=1) - timedelta(days=1))
        fin = fin_mois.replace(hour=23, minute=59, second=59)
        libelle_periode = "Ce mois"
    sous_comptes_ = g.models.sous_compte_model.get_all_sous_comptes_by_user_id(user_id)

    # Convertir les IDs en entiers
    for sous_compte in sous_comptes_:
        sous_compte['id'] = int(sous_compte['id'])
        sous_compte['compte_principal_id'] = int(sous_compte['compte_principal_id'])
    
    sous_compte = g.models.sous_compte_model.get_by_id(sous_compte_id)
    if not sous_compte:
        flash('Sous-compte introuvable', 'error')
        return redirect(url_for('banking.banking_dashboard'))

    # Vérifie que le sous-compte appartient bien à l'utilisateur
    compte_principal = g.models.compte_model.get_by_id(sous_compte['compte_principal_id'])
    if not compte_principal or compte_principal['utilisateur_id'] != user_id:
        flash('Sous-compte non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))
        
    mouvements = g.models.transaction_financiere_model.get_historique_compte(
        compte_type='sous_compte',
        compte_id=sous_compte_id,
        user_id=user_id,
        date_from=debut.strftime('%Y-%m-%d %H:%M:%S'),
        date_to=fin.strftime('%Y-%m-%d %H:%M:%S'),
        limit=50)
    logger.debug(f'{len(mouvements)} Mouvements récupérés pour le sous-compte {sous_compte_id}: {mouvements}')
    logger.debug(f'{len(mouvements)} Mouvements après filtrage pour le sous-compte {sous_compte_id}: {mouvements}')
        
    # Ajouter les statistiques du sous-compte
    stats_sous_compte = g.models.transaction_financiere_model.get_statistiques_compte(
        compte_type='sous_compte',
        compte_id=sous_compte_id,
        user_id=user_id,
        date_debut=debut.strftime('%Y-%m-%d'),
        date_fin=fin.strftime('%Y-%m-%d')
    )
    
    solde = g.models.sous_compte_model.get_solde(sous_compte_id)
    
    # Ajout du pourcentage calculé
    if sous_compte['objectif_montant'] and Decimal(str(sous_compte['objectif_montant'])) > 0:
        sous_compte['pourcentage_objectif'] = round((Decimal(str(sous_compte['solde'])) / Decimal(str(sous_compte['objectif_montant']))) * 100, 1)
    else:
        sous_compte['pourcentage_objectif'] = 0
    
    # Récupération de l'évolution des soldes quotidiens pour les 30 derniers jours
    soldes_quotidiens = g.models.transaction_financiere_model.get_evolution_soldes_quotidiens_sous_compte(
        sous_compte_id=sous_compte_id, 
        user_id=user_id, 
        nb_jours=30
    )
    logger.debug(f'{len(soldes_quotidiens)} Soldes quotidiens récupérés: {soldes_quotidiens}')
    soldes_quotidiens_len = len(soldes_quotidiens)
    # Préparation des données pour le graphique SVG
    graphique_svg = None
    largeur_svg = 500
    hauteur_svg = 200

    if soldes_quotidiens:
        soldes_values = [float(s['solde_apres']) for s in soldes_quotidiens]
        min_solde = min(soldes_values) if soldes_values else 0.0
        max_solde = max(soldes_values) if soldes_values else 0.0

        # Si un objectif est défini, on l'utilise comme référence
        objectif = float(sous_compte['objectif_montant']) if sous_compte.get('objectif_montant') else None

        # Limiter l'axe Y à 150% de l'objectif si défini
        if objectif and objectif > 0:
            max_affichage = objectif * 1.5
            min_affichage = 0.0  # On part de 0 pour plus de clarté visuelle
            # On ajuste max_solde pour ne pas dépasser max_affichage
            if max_solde > max_affichage:
                max_solde = max_affichage
            # On garde min_solde à 0 sauf s'il y a des valeurs négatives (rare pour un objectif)
            if min_solde < 0:
                min_affichage = min_solde  # On conserve les négatifs si présents
        else:
            # Pas d'objectif → on garde les valeurs min/max réelles, avec marge
            if min_solde == max_solde:
                if min_solde == 0:
                    max_solde = 100.0
                else:
                    min_solde *= 0.9
                    max_solde *= 1.1
            min_affichage = min_solde
            max_affichage = max_solde

        n = len(soldes_quotidiens)
        points = []
        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        for i, solde in enumerate(soldes_quotidiens):
            solde_float = float(solde['solde_apres'])
            x = margin_x + (i / (n - 1)) * plot_width if n > 1 else margin_x + plot_width / 2
            # Calcul de y en fonction de min_affichage / max_affichage
            y = margin_y + plot_height - ((solde_float - min_affichage) / (max_affichage - min_affichage)) * plot_height if max_affichage != min_affichage else margin_y + plot_height / 2
            points.append(f"{x},{y}")

        # Ajouter l'objectif au contexte graphique s'il existe
        objectif_y = None
        if objectif and max_affichage != min_affichage:
            # Position Y de la ligne d'objectif
            objectif_y = margin_y + plot_height - ((objectif - min_affichage) / (max_affichage - min_affichage)) * plot_height

        graphique_svg = {
            'points': points,
            'min_solde': min_affichage,
            'max_solde': max_affichage,
            'dates': [s['date'].strftime('%d/%m/%Y') for s in soldes_quotidiens],
            'soldes': soldes_values,
            'nb_points': n,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'objectif': objectif,
            'objectif_y': objectif_y  # Position Y pour tracer la ligne
        }
        
    return render_template(
        'banking/sous_compte_detail.html',
        sous_compte=sous_compte,
        comptes_=comptes_,
        sous_comptes_=sous_comptes_,
        compte=compte_principal,
        libelle_periode=libelle_periode,
        mouvements=mouvements,
        solde=solde,
        stats_sous_compte=stats_sous_compte,
        graphique_svg=graphique_svg,
        soldes_quotidiens=soldes_quotidiens,
        soldes_quotidiens_len=soldes_quotidiens_len,
        largeur_svg=largeur_svg,
        hauteur_svg=hauteur_svg,
        date_debut_selected=date_debut_str,
        date_fin_selected=date_fin_str,
        mois_selected=mois_select,
        annee_selected=annee_select
    )


@bp.route('/banking/compte/<int:compte_id>/reparer_soldes', methods=['POST'])
@login_required
def reparer_soldes_compte(compte_id):
    """
    Route pour déclencher la réparation manuelle des soldes d'un compte.
    """
    user_id = current_user.id

    # Récupérer le compte pour déterminer son type
    compte = g.models.compte_model.get_by_id(compte_id)
    if not compte:
        flash('Compte non trouvé', 'danger')
        return redirect(url_for('banking.banking_dashboard'))
    if  compte.get('utilisateur_id') != user_id:
        flash('Compte non autorisé', 'danger')
        return redirect(url_for('banking.banking_dashboard'))

    # Déterminer le type de compte
    compte_type = 'compte_principal' if compte.get('compte_principal_id') is None else 'sous_compte'
    # Appeler la méthode de réparation
    logging.info(f"banking 820 Appel reparation avec compte_type='{compte_type}', compte_id={compte_id}")
    success, message = g.models.transaction_financiere_model.reparer_soldes_compte(
        compte_type=compte_type,
        compte_id=compte_id,
        user_id=user_id
    )

    if success:
        flash(f"✅ {message}", "success")
    else:
        flash(f"❌ {message}", "danger")

    # Rediriger vers la page de détail du compte
    return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))

def est_transfert_valide(compte_source_id, compte_dest_id, user_id, comptes, sous_comptes):
    """
    Vérifie si un transfert entre deux comptes est valide avec les restrictions spécifiées:
    - Un sous-compte ne peut recevoir de l'argent que de son compte parent
    - Un sous-compte ne peut donner de l'argent qu'à son compte parent
    - Aucune restriction entre comptes principaux
    Args:
        compte_source_id: ID du compte source
        compte_dest_id: ID du compte destination
        user_id: ID de l'utilisateur
        comptes: Liste des comptes principaux de l'utilisateur
        sous_comptes: Liste des sous-comptes de l'utilisateur
    Returns:
        Tuple (bool, str, str, str): (est_valide, message_erreur, source_type, dest_type)
    """
    # Convertir les IDs en entiers pour éviter les problèmes de type
    try:
        compte_source_id = int(compte_source_id)
        compte_dest_id = int(compte_dest_id)
    except (ValueError, TypeError):
        return False, "IDs de comptes invalides", None, None
    
    # Vérifier si les comptes existent et appartiennent à l'utilisateur
    source_type = None
    dest_type = None
    compte_source = None
    compte_dest = None
    
    # Vérifier le compte source
    for c in comptes:
        if c['id'] == compte_source_id:
            source_type = 'compte_principal'
            compte_source = c
            break
    
    if not source_type:
        for sc in sous_comptes:
            if sc['id'] == compte_source_id:
                source_type = 'sous_compte'
                compte_source = sc
                break
    
    if not source_type:
        return False, "Compte source non trouvé ou non autorisé", None, None
    
    # Vérifier le compte destination
    for c in comptes:
        if c['id'] == compte_dest_id:
            dest_type = 'compte_principal'
            compte_dest = c
            break
    
    if not dest_type:
        for sc in sous_comptes:
            if sc['id'] == compte_dest_id:
                dest_type = 'sous_compte'
                compte_dest = sc
                break
    
    if not dest_type:
        return False, "Compte destination non trouvé ou non autorisé", None, None
    
    # Vérifier que les comptes sont différents
    if source_type == dest_type and compte_source_id == compte_dest_id:
        return False, "Les comptes source et destination doivent être différents", None, None
    
    # Appliquer les restrictions spécifiques
    # 1. Si la source est un sous-compte, elle ne peut transférer que vers son compte parent
    if source_type == 'sous_compte':
        parent_id = compte_source['compte_principal_id']
        if dest_type != 'compte_principal' or compte_dest_id != parent_id:
            # Récupérer le nom du compte parent pour le message d'erreur
            compte_parent = next((c for c in comptes if c['id'] == parent_id), None)
            nom_parent = compte_parent['nom_compte'] if compte_parent else "compte parent"
            return False, f"Un sous-compte ne peut transférer que vers son compte parent ({nom_parent})", None, None
    
    # 2. Si la destination est un sous-compte, elle ne peut recevoir que de son compte parent
    if dest_type == 'sous_compte':
        parent_id = compte_dest['compte_principal_id']
        if source_type != 'compte_principal' or compte_source_id != parent_id:
            # Récupérer le nom du compte parent pour le message d'erreur
            compte_parent = next((c for c in comptes if c['id'] == parent_id), None)
            nom_parent = compte_parent['nom_compte'] if compte_parent else "compte parent"
            return False, f"Un sous-compte ne peut recevoir que de son compte parent ({nom_parent})", None, None
    
    # 3. Aucune restriction entre comptes principaux (déjà couvert par les règles ci-dessus)
    
    return True, "Transfert valide", source_type, dest_type

# Routes pour les dépôts
@bp.route('/depot', methods=['GET', 'POST'])
@login_required
def depot():
    user_id = current_user.id
    comptes = g.models.compte_model.get_by_user_id(user_id)
    print(f'Voici les comptes de l\'utilisateur {user_id} : {comptes}')
    all_comptes = g.models.compte_model.get_all_accounts()
    
    if request.method == 'POST':
        # Récupération des données du formulaire
        compte_id = int(request.form['compte_id'])
        user_id = user_id
        montant = Decimal(request.form['montant'])
        description = request.form.get('description', '')
        compte_type = request.form['compte_type']
        
        if montant <= 0:
            flash("Le montant doit être positif", 'error')
            return render_template('banking/depot.html', 
                                comptes=comptes, 
                                all_comptes=all_comptes, 
                                form_data=request.form, 
                                now=datetime.now())
        # Gestion de la date de transaction
        date_transaction_str = request.form.get('date_transaction')
        if date_transaction_str:
            try:
                date_transaction = datetime.strptime(date_transaction_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash("Format de date invalide", 'error')
                return render_template('banking/depot.html', comptes=comptes, all_comptes=all_comptes, form_data=request.form)
        else:
            date_transaction = datetime.now()
        
        # Appel de la fonction create_depot avec la date
        success, message = g.models.transaction_financiere_model.create_depot(
            compte_id, 
            user_id, 
            montant, 
            description, 
            compte_type, 
            date_transaction)
        
        if success:
            flash(message, 'success')
            return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
        else:
            flash(message, 'error')
            return render_template('banking/depot.html', 
                                comptes=comptes, 
                                all_comptes=all_comptes, 
                                form_data=request.form,
                                now=datetime.now())
    
    return render_template('banking/depot.html', 
                        comptes=comptes, 
                        all_comptes=all_comptes, now=datetime.now())

# Routes pour les retraits
@bp.route('/retrait', methods=['GET', 'POST'])
@login_required
def retrait():
    user_id = current_user.id
    comptes = g.models.compte_model.get_by_user_id(user_id)
    print(f'Voici les comptes de l\'utilisateur {user_id} : {comptes}')
    all_comptes = g.models.compte_model.get_all_accounts()
    
    if request.method == 'POST':
        # Récupération des données du formulaire
        compte_id = int(request.form['compte_id'])
        user_id = user_id
        montant = Decimal(request.form['montant'])
        description = request.form.get('description', '')
        compte_type = request.form['compte_type']
        
        # Gestion de la date de transaction
        date_transaction_str = request.form.get('date_transaction')
        if date_transaction_str:
            try:
                date_transaction = datetime.strptime(date_transaction_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash("Format de date invalide", 'error')
                return render_template('banking/retrait.html', comptes=comptes, all_comptes=all_comptes, form_data=request.form)
        else:
            date_transaction = datetime.now()
        
        # Appel de la fonction create_retrait avec la date
        success, message = g.models.transaction_financiere_model.create_retrait(
            compte_id, user_id, montant, description, compte_type, date_transaction
        )
        
        if success:
            flash(message, 'success')
            print(f'Retrait effectué avec succès: {message} pour le compte {compte_id} de type {compte_type} pour {montant}')
            return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
        else:
            flash(message, 'error')
            print('Erreur lors du retrait:', message)
            return render_template('banking/retrait.html', comptes=comptes, all_comptes=all_comptes, form_data=request.form)
    
    return render_template('banking/retrait.html', comptes=comptes, all_comptes=all_comptes, now=datetime.now())

@bp.route('/banking/')
@bp.route('/banking/transfert', methods=['GET', 'POST'])
@login_required
def banking_transfert():
    user_id = current_user.id
    comptes = g.models.compte_model.get_by_user_id(user_id)
    print(f'Voici les comptes de l\'utilisateur {user_id} : {comptes}')

    # Convertir les IDs en entiers pour éviter les problèmes de comparaison
    for compte in comptes:
        compte['id'] = int(compte['id'])
    
    # Récupérer TOUS les comptes pour le transfert global
    all_comptes_global = g.models.compte_model.get_all_accounts()
    
    # Sous-comptes de l'utilisateur
    sous_comptes = []
    for c in comptes:
        subs = g.models.sous_compte_model.get_by_compte_principal_id(c['id'])
        for sub in subs:
            sub['id'] = int(sub['id'])
        sous_comptes += subs

    # Comptes externes (autres utilisateurs) pour transfert "externe"
    all_comptes = [c for c in all_comptes_global if c['utilisateur_id'] != user_id]

    #all_comptes = [c for c in g.models.compte_model.get_all_accounts() if c['utilisateur_id'] != user_id]
    
    if request.method == "POST":
        step = request.form.get('step')

        if step == 'select_type':
            transfert_type = request.form.get('transfert_type')
            if not transfert_type:
                flash("Veuillez sélectionner un type de transfert", "danger")
                return redirect(url_for("banking.banking_transfert"))
            return render_template(
                "banking/transfert.html",
                comptes=comptes,
                sous_comptes=sous_comptes,
                all_comptes=all_comptes,
                all_comptes_global=all_comptes_global,
                transfert_type=transfert_type,
                now=datetime.now()
            )

        elif step == 'confirm':
            transfert_type = request.form.get('transfert_type')
            
            try:
                # Montant
                montant_str = request.form.get('montant', '').replace(',', '.').strip()
                if not montant_str:
                    flash("Montant manquant", "danger")
                    return redirect(url_for("banking.banking_transfert"))
                
                try:
                    montant = Decimal(montant_str)
                    if montant <= 0:
                        flash("Le montant doit être positif", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                except (InvalidOperation, ValueError):
                    flash("Format de montant invalide. Utilisez un nombre avec maximum 2 décimales", "danger")
                    return redirect(url_for("banking.banking_transfert"))
                
                # Date de transaction
                date_transaction_str = request.form.get('date_transaction')
                if date_transaction_str:
                    try:
                        date_transaction = datetime.strptime(date_transaction_str, '%Y-%m-%dT%H:%M')
                    except ValueError:
                        flash("Format de date invalide", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                else:
                    date_transaction = datetime.now()

                success = False
                message = ""

                if transfert_type == 'interne':
                    # Vérification et conversion des IDs de compte
                    source_id_str = request.form.get('compte_source')
                    dest_id_str = request.form.get('compte_dest')
                    
                    if not source_id_str or not dest_id_str:
                        flash("Compte source ou destination manquant", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    
                    try:
                        source_id = int(source_id_str)
                        dest_id = int(dest_id_str)
                    except (ValueError, TypeError) as e:
                        flash("Identifiant de compte invalide", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    
                    # Vérification que les IDs sont valides
                    if source_id <= 0 or dest_id <= 0:
                        flash("Les IDs de comptes doivent être positifs", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    
                    # Déterminer le type de compte source
                    source_type = None
                    if any(c['id'] == source_id for c in comptes):
                        source_type = 'compte_principal'
                    elif any(sc['id'] == source_id for sc in sous_comptes):
                        source_type = 'sous_compte'
                    else:
                        flash("Compte source non valide", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    
                    # Déterminer le type de compte destination
                    dest_type = None
                    if any(c['id'] == dest_id for c in comptes):
                        dest_type = 'compte_principal'
                    elif any(sc['id'] == dest_id for sc in sous_comptes):
                        dest_type = 'sous_compte'
                    else:
                        flash('Compte destination non valide', "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    
                    # Vérification que le compte source appartient à l'utilisateur
                    if not any(c['id'] == source_id for c in comptes + sous_comptes):
                        flash("Vous ne pouvez pas transférer depuis ce compte", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    # Vérification interne : comptes différents
                    if source_id == dest_id and source_type == dest_type:
                        flash("Le compte source et le compte destination doivent être différents", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    
                    # Vérification spécifique pour les sous-comptes
                    if source_type == 'sous_compte':
                        # Récupérer le sous-compte source
                        sous_compte_source = next((sc for sc in sous_comptes if sc['id'] == source_id), None)
                        if sous_compte_source and sous_compte_source['compte_principal_id'] != dest_id:
                            flash("Un sous-compte ne peut être transféré que vers son compte principal", "danger")
                            return redirect(url_for("banking.banking_transfert"))
                    
                    if dest_type == 'sous_compte':
                        # Récupérer le sous-compte destination
                        sous_compte_dest = next((sc for sc in sous_comptes if sc['id'] == dest_id), None)
                        if sous_compte_dest and sous_compte_dest['compte_principal_id'] != source_id:
                            flash("Un sous-compte ne peut recevoir des fonds que depuis son compte principal", "danger")
                            return redirect(url_for("banking.banking_transfert"))
                    
                    # Exécution du transfert interne
                    commentaire = request.form.get('commentaire', '').strip()

                    success, message = g.models.transaction_financiere_model.create_transfert_interne(
                        source_type=source_type,
                        source_id=source_id,
                        dest_type=dest_type,
                        dest_id=dest_id,
                        user_id=user_id,
                        montant=montant,
                        description=commentaire,
                        date_transaction=date_transaction
                    )
                                            
                elif transfert_type == 'externe':
                    # Récupérer compte source (doit appartenir à l'utilisateur)
                    source_id_str = request.form.get('compte_source')
                    if not source_id_str:
                        flash("Compte source manquant", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    
                    try:
                        source_id = int(source_id_str)
                    except (ValueError, TypeError):
                        flash("Identifiant de compte invalide", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    # Vérifier que le compte source appartient à l'utilisateur
                    source_compte = next((c for c in comptes + sous_comptes if c['id'] == source_id), None)
                    if not source_compte:
                        flash("Vous ne pouvez transférer que depuis vos propres comptes", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    # Déterminer type de compte source
                    source_type = 'compte_principal' if any(c['id'] == source_id for c in comptes) else 'sous_compte'

                    # Récupérer infos externes
                    iban_dest = request.form.get('iban_dest', '').strip()
                    bic_dest = request.form.get('bic_dest', '').strip()
                    nom_dest = request.form.get('nom_dest', '').strip()
                    devise = request.form.get('devise', 'CHF')

                    if not iban_dest:
                        flash("IBAN destination requis", "danger")
                        return redirect(url_for("banking.banking_transfert"))
                    if not nom_dest:
                        flash("Nom du bénéficiaire requis", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    commentaire = request.form.get('commentaire', '').strip()

                    success, message = g.models.transaction_financiere_model.create_transfert_externe(
                        source_type=source_type,
                        source_id=source_id,
                        user_id=user_id,
                        iban_dest=iban_dest,
                        bic_dest=bic_dest,
                        nom_dest=nom_dest,
                        montant=montant,
                        devise=devise,
                        description=commentaire,
                        date_transaction=date_transaction
                    )

                elif transfert_type == 'global':
                    # Récupérer et valider les IDs
                    source_id_str = request.form.get('compte_source_global')
                    dest_id_str = request.form.get('compte_dest_global')

                    if not source_id_str or not dest_id_str:
                        flash("Compte source ou destination manquant", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    try:
                        source_id = int(source_id_str)
                        dest_id = int(dest_id_str)
                    except (ValueError, TypeError):
                        flash("Identifiant de compte invalide", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    # Vérifier que les comptes existent et sont actifs
                    source_compte = g.models.compte_model.get_by_id(source_id)
                    dest_compte = g.models.compte_model.get_by_id(dest_id)

                    if not source_compte:
                        flash("Le compte source n'existe pas ou est inactif", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    if not dest_compte:
                        flash("Le compte destinataire n'existe pas ou est inactif", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    if source_id == dest_id:
                        flash("Le compte source et destination doivent être différents", "danger")
                        return redirect(url_for("banking.banking_transfert"))

                    # Exécuter le transfert global
                    commentaire = request.form.get('commentaire', '').strip()
                    commentaire = f"[GLOBAL] {commentaire}"

                    success, message = g.models.transaction_financiere_model.create_transfert_interne(
                        source_type='compte_principal',
                        source_id=source_id,
                        dest_type='compte_principal',
                        dest_id=dest_id,
                        user_id=user_id,
                        montant=montant,
                        description=commentaire,
                        date_transaction=date_transaction
                    )

                else:
                    flash("Type de transfert non reconnu", "danger")
                    return redirect(url_for("banking.banking_transfert"))

                if success:
                    flash(message, "success")
                else:
                    flash(message, "danger")

                return redirect(url_for("banking.banking_transfert"))

            except Exception as e:
                flash(f"Erreur lors du transfert: {str(e)}", "danger")
                return redirect(url_for("banking.banking_transfert"))

    return render_template(
        "banking/transfert.html",
        comptes=comptes,
        sous_comptes=sous_comptes,
        all_comptes=all_comptes,
        all_comptes_global=all_comptes_global,  # <-- Ajouté
        now=datetime.now()
    )

@bp.route('/banking/transfert_compte_sous_compte', methods=['GET', 'POST'])
@login_required
def banking_transfert_compte_sous_compte():    
    user_id = current_user.id

        # Récupérer les comptes de l'utilisateur
    comptes = g.models.compte_model.get_by_user_id(user_id)
    print(f"DEBUG: Comptes de l'utilisateur {user_id}: {comptes}")
        
        # Récupérer tous les sous-comptes de l'utilisateur en une seule requête
    sous_comptes = g.models.sous_compte_model.get_all_sous_comptes_by_user_id(user_id)
    print(f"DEBUG: Tous les sous-comptes: {sous_comptes}")
        
        # Convertir les IDs en entiers
        # Vérifier d'abord si sous_comptes est une liste
    if isinstance(sous_comptes, list):
        for sous_compte in sous_comptes:
            sous_compte['id'] = int(sous_compte['id'])
            sous_compte['compte_principal_id'] = int(sous_compte['compte_principal_id'])
            print(f'Voici un sous-compte: {sous_compte}')
    else:
            # Si ce n'est pas une liste, convertir en liste
        sous_comptes = [sous_comptes] if sous_comptes else []
        for sous_compte in sous_comptes:
            sous_compte['id'] = int(sous_compte['id'])
            sous_compte['compte_principal_id'] = int(sous_compte['compte_principal_id'])
            print(f'Voici un sous-compte (converti): {sous_compte}')

    if request.method == "POST":
        try:
            # Récupération des données
            compte_id = int(request.form.get('compte_id'))
            sous_compte_id = int(request.form.get('sous_compte_id'))
            montant_str = request.form.get('montant', '').replace(',', '.').strip()
            direction = request.form.get('direction')  # 'compte_vers_sous' ou 'sous_vers_compte'
            commentaire = request.form.get('commentaire', '').strip()
            date_transaction_str = request.form.get('date_transaction')
            if date_transaction_str:
                try:
                    date_transaction = datetime.strptime(date_transaction_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash("Format de date invalide", 'error')
                    return redirect(url_for("banking.banking_transfert_compte_sous_compte"))
            # Validation du montant
            try:
                montant = Decimal(montant_str)
                if montant <= 0:
                    flash("Le montant doit être positif", "danger")
                    return redirect(url_for("banking.banking_transfert_compte_sous_compte"))
            except (InvalidOperation, ValueError):
                flash("Format de montant invalide", "danger")
                return redirect(url_for("banking.banking_transfert_compte_sous_compte"))

            # Vérification que les comptes appartiennent à l'utilisateur
            compte_valide = any(c['id'] == compte_id for c in comptes)
            sous_compte_valide = any(sc['id'] == sous_compte_id and sc['compte_principal_id'] == compte_id for sc in sous_comptes)
            
            if not compte_valide or not sous_compte_valide:
                flash("Compte ou sous-compte invalide", "danger")
                return redirect(url_for("banking.banking_transfert_compte_sous_compte"))

            # Exécution du transfert
            if direction == 'compte_vers_sous':
                success, message = g.models.transaction_financiere_model.transfert_compte_vers_sous_compte(
                    compte_id, sous_compte_id, montant, user_id, commentaire, date_transaction
                )
                logger.debug(f'voici les données envoyées : {compte_id}, {sous_compte_id}, {montant}, {user_id}, {date_transaction}')
            else:
                success, message = g.models.transaction_financiere_model.transfert_sous_compte_vers_compte(
                    sous_compte_id, compte_id, montant, user_id, commentaire, date_transaction
                )
                logger.debug(f'voici les données envoyées : {compte_id}, {sous_compte_id}, {montant}, {user_id}, {date_transaction}')


            if success:
                flash(message, "success")
            else:
                flash(message, "danger")

            return redirect(url_for("banking.banking_transfert_compte_sous_compte"))

        except Exception as e:
            flash(f"Erreur lors du transfert: {str(e)}", "danger")
            return redirect(url_for("banking.banking_transfert_compte_sous_compte"))

    return render_template(
        "banking/transfert_compte_sous_compte.html",
        comptes=comptes,
        sous_comptes=sous_comptes,
        now=datetime.now()
    )

@bp.route('/banking/annuler_transfert_externe/<int:transfert_id>', methods=['POST'])
@login_required
def annuler_transfert_externe(transfert_id):
    success, message = g.models.transaction_financiere_model.annuler_transfert_externe(
        transfert_externe_id=transfert_id,
        user_id=current_user.id)
    if success:
        flash(message, "success")
    else:
        flash(message, "danger")     
    return redirect(url_for('banking.banking_dashboard'))

@bp.route('/banking/modifier_transfert/<int:transfert_id>', methods=['GET', 'POST'])
@login_required
def modifier_transfert(transfert_id):
    user_id = current_user.id

    transaction = g.models.transaction_financiere_model.get_transaction_by_id(transfert_id)
    if not transaction or transaction.get('owner_user_id') != user_id:
        flash("Transaction non trouvée ou non autorisée", "danger")
        return redirect(url_for('banking.banking_dashboard'))

    # Récupérer le compte pour la devise
    compte_id = transaction.get('compte_principal_id') or transaction.get('sous_compte_id')
    compte = None
    if transaction.get('compte_principal_id'):
        compte = g.models.compte_model.get_by_id(transaction.get('compte_principal_id'))
    elif transaction.get('sous_compte_id'):
        sous_compte = g.models.sous_compte_model.get_by_id(transaction.get('sous_compte_id'))
        if sous_compte:
            compte = g.models.compte_model.get_by_id(sous_compte['compte_principal_id'])

    if request.method == 'POST':
        # 🔑 Récupérer l'URL de retour
        return_to = request.form.get('return_to')
        # 🔒 Sécurité : s'assurer que c'est une URL interne
        if not return_to or not return_to.startswith('/'):
            return_to = url_for('banking.banking_compte_detail', compte_id=compte_id)

        action = request.form.get('action')

        if action == 'supprimer':
            success, message = g.models.transaction_financiere_model.supprimer_transaction(transfert_id, user_id)
            if success:
                flash(f"La transaction {transfert_id} a été supprimée avec succès", "success")
            else:
                flash(message, "danger")
            return redirect(return_to)

        elif action == 'modifier':
            try:
                nouveau_montant = Decimal(request.form.get('nouveau_montant', '0'))
                nouvelle_date_str = request.form.get('nouvelle_date')
                nouvelle_description = request.form.get('nouvelle_description', '').strip()
                nouvelle_reference = request.form.get('nouvelle_reference', '').strip()

                if not nouvelle_date_str:
                    flash("La date est obligatoire", "danger")
                    # ❌ Ne pas faire render_template ici !
                    return redirect(return_to)

                nouvelle_date = datetime.fromisoformat(nouvelle_date_str)

                success, message = g.models.transaction_financiere_model.modifier_transaction(
                    transaction_id=transfert_id,
                    user_id=user_id,
                    nouveau_montant=nouveau_montant,
                    nouvelle_description=nouvelle_description,
                    nouvelle_date=nouvelle_date,
                    nouvelle_reference=nouvelle_reference
                )

                if success:
                    flash(f"La transaction {transfert_id} a été modifiée avec succès", "success")
                else:
                    flash(message, "danger")

                return redirect(return_to)

            except Exception as e:
                flash(f"Erreur de validation : {str(e)}", "danger")
                return redirect(return_to)

    # ❌ Cette ligne NE DOIT PAS ÊTRE ATTEINTE en usage normal
    # Car le modal est inclus dans une page, pas ouvert via GET
    flash("Accès direct au modal impossible", "warning")
    return redirect(url_for('banking.banking_dashboard'))

@bp.route('/banking/supprimer_transfert/<int:transfert_id>', methods=['POST'])
@login_required
def supprimer_transfert(transfert_id):
    user_id = current_user.id

    # Récupérer la transaction pour vérification
    transaction = g.models.transaction_financiere_model.get_transaction_by_id(transfert_id)
    if not transaction or transaction.get('owner_user_id') != user_id:
        flash("Transaction non trouvée ou non autorisée", "danger")
        return redirect(url_for('banking.banking_dashboard'))

    # Déterminer le type et l'ID du compte pour la réparation des soldes
    compte_type = 'compte_principal' if transaction.get('compte_principal_id') else 'sous_compte'
    compte_id = transaction.get('compte_principal_id') or transaction.get('sous_compte_id')

    # Récupérer l'URL de retour
    return_to = request.form.get('return_to')
    if not return_to or not return_to.startswith('/'):
        # Fallback sécurisé si return_to absent ou invalide
        return_to = url_for('banking.banking_dashboard')

    # Supprimer la transaction
    success, message = g.models.transaction_financiere_model.supprimer_transaction(
        transaction_id=transfert_id,
        user_id=user_id
    )

    if success:
        # Réparer les soldes du compte concerné
        success_rep, message_rep = g.models.transaction_financiere_model.reparer_soldes_compte(
            compte_type=compte_type,
            compte_id=compte_id,
            user_id=user_id
        )

        if success_rep:
            flash(f"Transaction {transfert_id} supprimée et soldes réparés avec succès", "success")
        else:
            flash(f"Transaction {transfert_id} supprimée mais erreur lors de la réparation des soldes : {message_rep}", "warning")
    else:
        flash(message, "danger")

    return redirect(return_to)
@bp.route('/banking/liste_transferts', methods=['GET'])
@login_required
def liste_transferts():
    user_id = current_user.id
    # Récupération de tous les paramètres de filtrage possibles
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    compte_source_id = request.args.get('compte_id')
    compte_dest_id = request.args.get('compte_dest_id')
    sous_compte_source_id = request.args.get('sous_compte_id')
    sous_compte_dest_id = request.args.get('sous_compte_dest_id')
    type_transfert = request.args.get('type_transfert') # Nom unifié
    statut = request.args.get('statut')
    page = int(request.args.get('page', 1))
    q = request.args.get('text_search', '').strip()
    ref_filter = request.args.get('ref_filter', '').strip()
    per_page = 20
    #type_transfert = type_transfert if type_transfert in ['interne', 'externe', 'global'] else None
    #statut= request.args.get('statut')
    #statut = statut if statut in ['completed', 'pending'] else None
    #montant_min = request.args.get('montant_min')
    #montant_max = request.args.get('montant_max')
    #compte_ou_sous_compte_id = request.args.get('compte_ou_sous_compte_id')
    # Récupération des comptes et sous-comptes pour les filtres
    comptes = g.models.compte_model.get_by_user_id(user_id)
    sous_comptes = []
    for c in comptes:
        sous_comptes += g.models.sous_compte_model.get_by_compte_principal_id(c['id'])

    # Récupération des mouvements financiers avec filtres
    mouvements, total = g.models.transaction_financiere_model.get_all_user_transactions(
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        compte_source_id=compte_source_id,      # ← maintenant bien nommé
        compte_dest_id=compte_dest_id,
        sous_compte_source_id=sous_compte_source_id,
        sous_compte_dest_id=sous_compte_dest_id,
        reference=ref_filter,
        q=q,
        page=page,
        per_page=per_page)

    pages = (total + per_page - 1) // per_page

        # Export CSV
    if request.args.get('export') == 'csv':
        mouv, _ = g.models.transaction_financiere_model.get_all_user_transactions(
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            compte_source_id=compte_source_id,
            compte_dest_id=compte_dest_id,
            sous_compte_source_id=sous_compte_source_id,
            sous_compte_dest_id=sous_compte_dest_id,
            reference=ref_filter,
            q=q,
            page=None,
            per_page=None
        )
        si = StringIO()
        cw = csv.writer(si, delimiter=';')
        cw.writerow(['Date', 'Type', 'Description', 'Source', 'Destination', 'Montant'])
        
        for t in mouv:  # ✅ utilise 'mouv', pas 'mouvements'
            # Source
            source = ""
            if t['compte_principal_id']:  # ✅ bon nom de champ
                source = t.get('nom_compte_source', 'N/A')
                if t.get('sous_compte_id'):  # ✅ bon nom
                    source += f" ({t.get('nom_sous_compte_source', 'N/A')})"
            else:
                source = t.get('nom_source_externe', 'Externe')

            # Destination
            destination = ""
            if t['compte_destination_id']:  # ✅ bon nom
                destination = t.get('nom_compte_dest', 'N/A')
                if t.get('sous_compte_destination_id'):  # ✅ bon nom
                    destination += f" ({t.get('nom_sous_compte_dest', 'N/A')})"
            else:
                destination = t.get('nom_dest_externe', 'Externe')

            # Type de transfert
            type_transfert = "N/A"
            cp_src = t['compte_principal_id']
            cp_dst = t['compte_destination_id']
            sc_src = t['sous_compte_id']
            sc_dst = t['sous_compte_destination_id']

            if (cp_src or sc_src) and (cp_dst or sc_dst):
                type_transfert = "interne"
            elif (cp_src or sc_src) and not (cp_dst or sc_dst):
                type_transfert = "externe"
            elif not (cp_src or sc_src) and (cp_dst or sc_dst):
                type_transfert = "externe"
            elif not (cp_src or sc_src) and not (cp_dst or sc_dst):
                type_transfert = "global"

            cw.writerow([
                t['date_transaction'].strftime("%Y-%m-%d %H:%M"),  # ✅ bon champ
                t['type_transaction'],
                t.get('description'),
                source,
                destination,
                f"{t['montant']:.2f}"
            ])
        
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=mouvements.csv"
        output.headers["Content-Type"] = "text/csv; charset=utf-8"
        return output


    # Rendu de la page unifiée
    return render_template(
        'banking/liste_transactions.html', # Nom de la nouvelle page unifiée
        transactions=mouvements, # Renommé pour correspondre à la page HTML
        comptes=comptes,
        sous_comptes=sous_comptes,
        page=page,
        pages=pages,
        date_from=date_from,
        date_to=date_to,
        compte_source_filter=compte_source_id,
        compte_dest_filter=compte_dest_id,
        sc_filter=sous_compte_source_id,
        dest_sc_filter=sous_compte_dest_id,
        sc_whdest_filter=sous_compte_dest_id,
        type_filter=type_transfert,
        statut_filter=statut,
        ref_filter=ref_filter,
        q=q,
        total=total
    )


@bp.route('/banking/transaction/<int:transaction_id>/manage', methods=['GET', 'POST'])
@login_required
def manage_transaction(transaction_id):
    user_id = current_user.id

    # Récupérer la transaction
    transaction = g.models.transaction_financiere_model.get_transaction_by_id(transaction_id)
    if not transaction or transaction.get('owner_user_id') != user_id:
        flash("Transaction non trouvée ou non autorisée", "danger")
        return redirect(url_for('banking.banking_compte_detail', compte_id=request.args.get('compte_id')))

    # Récupérer le compte pour la devise
    compte_id = transaction.get('compte_principal_id') or transaction.get('sous_compte_id')
    compte = g.models.compte_model.get_by_id(compte_id) if transaction.get('compte_principal_id') else None

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'supprimer':
            success, message = g.models.transaction_financiere_model.supprimer_transaction(transaction_id, user_id)
            if success:
                flash("Transaction supprimée avec succès", "success")
            else:
                flash(message, "danger")
            return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))

        elif action == 'modifier':
            try:
                nouveau_montant = Decimal(request.form.get('nouveau_montant', '0'))
                nouvelle_date_str = request.form.get('nouvelle_date')
                nouvelle_description = request.form.get('nouvelle_description', '').strip()
                nouvelle_reference = request.form.get('nouvelle_reference', '').strip()

                if not nouvelle_date_str:
                    flash("La date est obligatoire", "danger")
                    return render_template('banking/transaction_modal.html', transaction=transaction, compte=compte)

                nouvelle_date = datetime.fromisoformat(nouvelle_date_str)

                success, message = g.models.transaction_financiere_model.modifier_transaction(
                    transaction_id=transaction_id,
                    user_id=user_id,
                    nouveau_montant=nouveau_montant,
                    nouvelle_description=nouvelle_description,
                    nouvelle_date=nouvelle_date,
                    nouvelle_reference=nouvelle_reference
                )

                if success:
                    flash("Transaction modifiée avec succès", "success")
                    return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
                else:
                    flash(message, "danger")

            except Exception as e:
                flash(f"Erreur de validation : {str(e)}", "danger")

    # Pour GET ou en cas d'erreur de validation
    return render_template('banking/transaction_modal.html', transaction=transaction, compte=compte)

# ---- APIs ----

@bp.route('/import/csv', methods=['GET', 'POST'])
@login_required
def import_csv_upload():
    
    if request.method == 'GET':
        return render_template('banking/import_csv_upload.html')
    
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash("Veuillez uploader un fichier CSV.", "danger")
        return redirect(url_for('banking.import_csv_upload'))

    # Lire le CSV
    stream = io.TextIOWrapper(file.stream, encoding='utf-8')
    raw_lines = stream.read().splitlines()
    if not raw_lines:
        flash("Fichier vide", "danger")
        return redirect(url_for('banking.import_csv_upload'))
    import csv as csv_mod
    # Détecter le délimiteur
    sample = '\n'.join(raw_lines[:5])  # Prendre un échantillon
    try:
        delimiter = csv_mod.Sniffer().sniff(sample, delimiters=";,|\t").delimiter
    except:
        delimiter = ';'  # Fallback pour les exports bancaires suisses

    reader_raw = csv_mod.reader(raw_lines, delimiter=delimiter)
    headers_raw = next(reader_raw)
    headers = [h.strip().strip('"') for h in headers_raw]
    rows = []
    logging.error('changement')
    for row_raw in reader_raw:
        row_dict = {}
        for i, h in enumerate(headers):
            value = row_raw[i].strip().strip('"') if i < len(row_raw) else ''
            row_dict[h] = value
        rows.append(row_dict)
    rows = rows



    # Sauvegarder dans la session
    session['csv_headers'] = headers
    session['csv_rows'] = rows

    # Récupérer les comptes de l'utilisateur
    user_id = current_user.id
    comptes = g.models.compte_model.get_all_accounts()
    sous_comptes = g.models.sous_compte_model.get_all_sous_comptes_by_user_id(user_id)

    comptes_possibles = []
    for c in comptes:
        comptes_possibles.append({
            'id': c['id'],
            'nom': c['nom_compte'],
            'type': 'compte_principal'
        })
    for sc in sous_comptes:
        comptes_possibles.append({
            'id': sc['id'],
            'nom': sc['nom_sous_compte'],
            'type': 'sous_compte'
        })

    session['comptes_possibles'] = comptes_possibles
    comptes_possibles.sort(key=lambda x: x['nom'])

    return redirect(url_for('banking.import_csv_map'))


@bp.route('/import/csv/map', methods=['GET'])
@login_required
def import_csv_map():
    if 'csv_headers' not in session:
        return redirect(url_for('banking.import_csv_upload'))
    return render_template('banking/import_csv_map.html')


@bp.route('/import/csv/confirm', methods=['POST'])
@login_required
def import_csv_confirm():
    user_id = current_user.id
    mapping = {
        'date': request.form['col_date'],
        'montant': request.form['col_montant'],
        'type': request.form['col_type'],
        'description': request.form.get('col_description') or None,
        'source': request.form['col_source'],
        'dest': request.form.get('col_dest') or None,
    }
    session['column_mapping'] = mapping

    # === 🔁 TRIER LES LIGNES DÈS MAINTENANT ===
    csv_rows = session.get('csv_rows', [])
    print("=== CONTENU DE csv_rows ===")
    for i, row in enumerate(csv_rows):
        print(f"Ligne {i}: {row}")
    type_col = mapping['type']
    date_col = mapping['date']

    # Ajouter le type à chaque ligne + trier
    enriched_rows = []
    for row in csv_rows:
        tx_type = row.get(type_col, '').strip().lower()
        if tx_type not in ('depot', 'retrait', 'transfert'):
            tx_type = 'inconnu'
        enriched_rows.append({**row, '_tx_type': tx_type})

    def parse_date_for_sort(row):
        d = row.get(date_col, '').strip()
        if not d:
            return datetime.max
        # Formats supportés : ISO + format suisse (jj.mm.yy HH:MM)
        for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%d.%m.%y %H:%M'):
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
        return datetime.max

    enriched_rows_sorted = sorted(enriched_rows, key=parse_date_for_sort)
    session['csv_rows_with_type'] = enriched_rows_sorted  # <-- on remplace par la version triée

    # Préparer les lignes avec options de sélection (dans le nouvel ordre)
    rows_for_template = []
    for i, row in enumerate(enriched_rows_sorted):
        source_val = row.get(mapping['source'], '').strip()
        dest_val = row.get(mapping['dest'], '').strip() if mapping['dest'] else ''
        rows_for_template.append({
            'index': i,
            'tx_type': row['_tx_type'],
            'source_val': source_val,
            'dest_val': dest_val,
        })
    comptes_possibles = session.get('comptes_possibles', [])
    comptes_possibles = sorted(comptes_possibles, key=lambda x: x.get('nom', ''))
    return render_template('banking/import_csv_confirm.html', rows=rows_for_template, comptes_possibles=comptes_possibles)


@bp.route('/import/csv/final', methods=['POST'])
@login_required
def import_csv_final():
    user_id = current_user.id
    mapping = session.get('column_mapping')
    csv_rows = session.get('csv_rows_with_type', [])
    comptes_possibles = {str(c['id']) + '|' + c['type']: c for c in session.get('comptes_possibles', [])}

    if not mapping or not csv_rows:
        flash("Données d'import manquantes. Veuillez recommencer.", "danger")
        return redirect(url_for('banking.import_csv_upload'))

    success_count = 0
    errors = []

    for i, row in enumerate(csv_rows):
        try:
            # Extraction
            date_str = row[mapping['date']].strip()
            montant_str = row[mapping['montant']].strip().replace(',', '.')
            tx_type = row[mapping['type']].lower().strip()
            desc = row.get(mapping['description'], '').strip() if mapping['description'] else ''

            # Conversion
            try:
                montant = Decimal(montant_str)
                if montant <= 0:
                    raise ValueError("Montant doit être > 0")
            except (InvalidOperation, ValueError) as e:
                errors.append(f"Ligne {i+1}: montant invalide ({montant_str})")
                continue

            date_tx = None
            for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%d.%m.%y %H:%M'):
                try:
                    date_tx = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue

            if date_tx is None:
                errors.append(f"Ligne {i+1}: date invalide ({date_str})")
                continue

            # Récupérer les choix utilisateur
            source_key = request.form.get(f'row_{i}_source')
            dest_key = request.form.get(f'row_{i}_dest')

            if not source_key or source_key not in comptes_possibles:
                errors.append(f"Ligne {i+1}: compte source invalide")
                continue

            source_info = comptes_possibles[source_key]
            source_id = source_info['id']
            source_type = source_info['type']

            if tx_type in ['depot', 'retrait']:
                if tx_type == 'depot':
                    ok, msg = g.models.transaction_financiere_model.create_depot(
                        compte_id=source_id,
                        user_id=user_id,
                        montant=montant,
                        description=desc,
                        compte_type=source_type,
                        date_transaction=date_tx
                    )
                else:  # retrait
                    ok, msg = g.models.transaction_financiere_model.create_retrait(
                        compte_id=source_id,
                        user_id=user_id,
                        montant=montant,
                        description=desc,
                        compte_type=source_type,
                        date_transaction=date_tx
                    )
                if ok:
                    success_count += 1
                else:
                    errors.append(f"Ligne {i+1}: {msg}")

            elif tx_type == 'transfert':
                if not dest_key or dest_key not in comptes_possibles:
                    errors.append(f"Ligne {i+1}: compte destination requis pour transfert")
                    continue
                dest_info = comptes_possibles[dest_key]
                dest_id = dest_info['id']
                dest_type = dest_info['type']

                # Vérifier que les comptes sont différents
                if source_id == dest_id and source_type == dest_type:
                    errors.append(f"Ligne {i+1}: source et destination identiques")
                    continue

                ok, msg = g.models.transaction_financiere_model.create_transfert_interne(
                    source_type=source_type,
                    source_id=source_id,
                    dest_type=dest_type,
                    dest_id=dest_id,
                    user_id=user_id,
                    montant=montant,
                    description=desc,
                    date_transaction=date_tx
                )
                if ok:
                    success_count += 1
                else:
                    errors.append(f"Ligne {i+1}: {msg}")

            else:
                errors.append(f"Ligne {i+1}: type inconnu '{tx_type}' (attendu: depot, retrait, transfert)")

        except Exception as e:
            errors.append(f"Ligne {i+1}: erreur inattendue ({str(e)})")

    # Nettoyer la session
    session.pop('csv_headers', None)
    session.pop('csv_rows', None)
    session.pop('comptes_possibles', None)
    session.pop('column_mapping', None)

    flash(f"✅ Import terminé : {success_count} transaction(s) créée(s).", "success")
    for err in errors[:5]:  # Limiter les messages d'erreur affichés
        flash(f"❌ {err}", "danger")

    return redirect(url_for('banking.banking_dashboard'))

@bp.route('/import/csv/distinct_confirm', methods=['POST'])
@login_required
def import_csv_distinct_confirm():
    mapping = {
        'date': request.form['col_date'],
        'montant': request.form['col_montant'],
        'type': request.form['col_type'],
        'description': request.form.get('col_description') or None,
        'source': request.form['col_source'],
        'dest': request.form.get('col_dest') or None,
    }
    print("=== MAPPING ===")
    print("source =", mapping['source'])
    print("dest =", mapping.get('dest'))
    session['column_mapping'] = mapping

    csv_rows = session.get('csv_rows', [])
    print("=== CONTENU DE csv_rows ===")
    for i, row in enumerate(csv_rows):
        print(f"Ligne {i}: {row}")
    if not csv_rows:
        flash("Aucune donnée à traiter.", "danger")
        return redirect(url_for('banking.import_csv_upload'))

    # 🔥 Extraire TOUTES les valeurs uniques de source ET destination
    compte_names = set()

    source_col = mapping['source']
    for row in csv_rows:
        val = row.get(source_col, '').strip()
        if val:
            compte_names.add(val)

    dest_col = mapping.get('dest')
    if dest_col:
        for row in csv_rows:
            val = row.get(dest_col, '').strip()
            if val:
                compte_names.add(val)

    compte_names = sorted(compte_names)

    session['distinct_compte_names'] = compte_names
    session['csv_rows_raw'] = csv_rows

    comptes_possibles = sorted(
        session.get('comptes_possibles', []),
        key=lambda x: x.get('nom', '')
    )

    return render_template(
        'banking/import_csv_distinct_confirm_temp.html',
        compte_names=compte_names,
        comptes_possibles=comptes_possibles
    )


@bp.route('/import/csv/final_distinct', methods=['POST'])
@login_required
def import_csv_final_distinct():
    user_id = current_user.id
    mapping = session.get('column_mapping')
    csv_rows = session.get('csv_rows_raw', [])
    comptes_possibles = {str(c['id']) + '|' + c['type']: c for c in session.get('comptes_possibles', [])}

    if not mapping or not csv_rows:
        flash("Données d'import manquantes.", "danger")
        return redirect(url_for('banking.import_csv_upload'))

    # 🔥 Construire un mapping GLOBAL : nom → compte
    global_mapping = {}
    i = 0
    while f'compte_name_{i}' in request.form:
        name = request.form[f'compte_name_{i}']
        key = request.form[f'account_{i}']
        if key and key in comptes_possibles:
            global_mapping[name] = key
        i += 1

    success_count = 0
    errors = []

    for idx, row in enumerate(csv_rows):
        try:
            date_str = row[mapping['date']].strip()
            montant_str = row[mapping['montant']].strip().replace(',', '.')
            tx_type = row[mapping['type']].lower().strip()
            desc = row.get(mapping['description'], '').strip() if mapping.get('description') else ''

            try:
                montant = Decimal(montant_str)
                if montant <= 0:
                    raise ValueError("Montant doit être > 0")
            except (InvalidOperation, ValueError):
                errors.append(f"Ligne {idx+1}: montant invalide ({montant_str})")
                continue

            try:
                date_tx = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                try:
                    date_tx = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    errors.append(f"Ligne {idx+1}: date invalide ({date_str})")
                    continue

            # 🔥 Récupérer les comptes via le mapping global UNIQUE
            source_val = row.get(mapping['source'], '').strip()
            source_key = global_mapping.get(source_val)

            if tx_type in ('depot', 'retrait'):
                if not source_key:
                    errors.append(f"Ligne {idx+1}: compte non associé pour '{source_val}'")
                    continue
            elif tx_type == 'transfert':
                dest_val = row.get(mapping['dest'], '').strip() if mapping.get('dest') else ''
                dest_key = global_mapping.get(dest_val) if dest_val else None
                if not source_key or not dest_key:
                    errors.append(f"Ligne {idx+1}: compte(s) non associé(s) (source: '{source_val}', dest: '{dest_val}')")
                    continue
                if source_key == dest_key:
                    errors.append(f"Ligne {idx+1}: source et destination identiques")
                    continue
            else:
                errors.append(f"Ligne {idx+1}: type inconnu '{tx_type}'")
                continue

            # --- Logique métier ---
            source_info = comptes_possibles[source_key]
            source_id = source_info['id']
            source_type = source_info['type']

            if tx_type == 'depot':
                ok, msg = g.models.transaction_financiere_model.create_depot(
                    compte_id=source_id, user_id=user_id, montant=montant,
                    description=desc, compte_type=source_type, date_transaction=date_tx
                )
            elif tx_type == 'retrait':
                ok, msg = g.models.transaction_financiere_model.create_retrait(
                    compte_id=source_id, user_id=user_id, montant=montant,
                    description=desc, compte_type=source_type, date_transaction=date_tx
                )
            elif tx_type == 'transfert':
                dest_info = comptes_possibles[dest_key]
                dest_id = dest_info['id']
                dest_type = dest_info['type']
                ok, msg = g.models.transaction_financiere_model.create_transfert_interne(
                    source_type=source_type, source_id=source_id,
                    dest_type=dest_type, dest_id=dest_id,
                    user_id=user_id, montant=montant, description=desc, date_transaction=date_tx
                )

            if ok:
                success_count += 1
            else:
                errors.append(f"Ligne {idx+1}: {msg}")

        except Exception as e:
            errors.append(f"Ligne {idx+1}: erreur inattendue ({str(e)})")

    # Nettoyer la session
    for key in ['csv_headers', 'csv_rows', 'comptes_possibles', 'column_mapping',
                'distinct_compte_names', 'csv_rows_raw']:
        session.pop(key, None)

    flash(f"✅ Import terminé : {success_count} transaction(s) créée(s).", "success")
    for err in errors[:5]:
        flash(f"❌ {err}", "danger")

    return redirect(url_for('banking.banking_dashboard'))

### Méthodes avec fichiers temp 


@bp.route('/import/temp/csv', methods=['GET', 'POST'])
@login_required
def import_csv_upload_temp():
    if request.method == 'GET':
        return render_template('banking/import_csv_upload.html')
    
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash("Veuillez uploader un fichier CSV.", "danger")
        return redirect(url_for('banking.import_csv_upload_temp'))

    stream = io.TextIOWrapper(file.stream, encoding='utf-8')
    raw_lines = stream.read().splitlines()
    if not raw_lines:
        flash("Fichier vide", "danger")
        return redirect(url_for('banking.import_csv_upload_temp'))

    sample = '\n'.join(raw_lines[:5])
    try:
        delimiter = csv_mod.Sniffer().sniff(sample, delimiters=";,|\t").delimiter
    except:
        delimiter = ';'

    reader_raw = csv_mod.reader(raw_lines, delimiter=delimiter)
    headers_raw = next(reader_raw)
    headers = [h.strip().strip('"') for h in headers_raw]
    rows = []
    for row_raw in reader_raw:
        row_dict = {}
        for i, h in enumerate(headers):
            value = row_raw[i].strip().strip('"') if i < len(row_raw) else ''
            row_dict[h] = value
        rows.append(row_dict)

    user_id = current_user.id
    comptes = g.models.compte_model.get_all_accounts()
    sous_comptes = g.models.sous_compte_model.get_all_sous_comptes_by_user_id(user_id)

    comptes_possibles = []
    for c in comptes:
        comptes_possibles.append({'id': c['id'], 'nom': c['nom_compte'], 'type': 'compte_principal'})
    for sc in sous_comptes:
        comptes_possibles.append({'id': sc['id'], 'nom': sc['nom_sous_compte'], 'type': 'sous_compte'})

    csv_data = {
        'csv_headers': headers,
        'csv_rows': rows,
        'comptes_possibles': sorted(comptes_possibles, key=lambda x: x['nom'])
    }
    temp_key = db_csv_store.save(user_id, csv_data)  # ✅ user_id = entier
    session['csv_temp_key'] = temp_key

    return redirect(url_for('banking.import_csv_map_temp'))


@bp.route('/import/temp/csv/map', methods=['GET'])
@login_required
def import_csv_map_temp():
    temp_key = session.get('csv_temp_key')
    if not temp_key:
        flash("Données manquantes.", "warning")
        return redirect(url_for('banking.import_csv_upload_temp'))

    csv_data = db_csv_store.load(temp_key, current_user.id)
    if not csv_data:
        flash("Données expirées.", "warning")
        return redirect(url_for('banking.import_csv_upload_temp'))

    headers = csv_data.get('csv_headers', [])
    if not headers:
        flash("Aucune colonne trouvée.", "danger")
        return redirect(url_for('banking.import_csv_upload_temp'))

    return render_template('banking/import_csv_map_temp.html', csv_headers=headers)


@bp.route('/import/temp/csv/confirm', methods=['POST'])
@login_required
def import_csv_confirm_temp():
    user_id = current_user.id
    temp_key = session.get('csv_temp_key')
    csv_data = db_csv_store.load(temp_key, user_id)
    if not csv_data:
        flash("Données expirées.", "danger")
        return redirect(url_for('banking.import_csv_upload_temp'))

    mapping = {
        'date': request.form['col_date'],
        'montant': request.form['col_montant'],
        'type': request.form['col_type'],
        'description': request.form.get('col_description') or None,
        'source': request.form['col_source'],
        'dest': request.form.get('col_dest') or None,
    }
    session['column_mapping'] = mapping

    csv_rows = csv_data['csv_rows']
    type_col = mapping['type']
    date_col = mapping['date']

    enriched_rows = []
    for row in csv_rows:
        tx_type = row.get(type_col, '').strip().lower()
        if tx_type not in ('depot', 'retrait', 'transfert'):
            tx_type = 'inconnu'
        enriched_rows.append({**row, '_tx_type': tx_type})

    def parse_date_for_sort(row):
        d = row.get(date_col, '').strip()
        if not d:
            return datetime.max
        for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%d.%m.%y %H:%M'):  # ✅ format suisse ajouté
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
        return datetime.max

    enriched_rows_sorted = sorted(enriched_rows, key=parse_date_for_sort)

    rows_for_template = []
    for i, row in enumerate(enriched_rows_sorted):
        source_val = row.get(mapping['source'], '').strip()
        dest_val = row.get(mapping['dest'], '').strip() if mapping['dest'] else ''
        rows_for_template.append({
            'index': i,
            'tx_type': row['_tx_type'],
            'source_val': source_val,
            'dest_val': dest_val,
        })

    comptes_possibles = csv_data['comptes_possibles']
    # ❌ PLUS DE db_csv_store.save() ICI
    return render_template('banking/import_csv_confirm.html', rows=rows_for_template, comptes_possibles=comptes_possibles)


@bp.route('/import/temp/csv/final', methods=['POST'])
@login_required
def import_csv_final_temp():
    user_id = current_user.id
    temp_key = session.get('csv_temp_key')
    csv_data = db_csv_store.load(temp_key, user_id) if temp_key else None
    mapping = session.get('column_mapping')

    if not mapping or not csv_data:
        flash("Données manquantes.", "danger")
        return redirect(url_for('banking.import_csv_upload_temp'))

    # ✅ RECONSTRUIRE enriched_rows_sorted ICI (pas stocké)
    csv_rows = csv_data['csv_rows']
    type_col = mapping['type']
    date_col = mapping['date']

    enriched_rows = []
    for row in csv_rows:
        tx_type = row.get(type_col, '').strip().lower()
        if tx_type not in ('depot', 'retrait', 'transfert'):
            tx_type = 'inconnu'
        enriched_rows.append({**row, '_tx_type': tx_type})

    def parse_date_for_sort(row):
        d = row.get(date_col, '').strip()
        if not d:
            return datetime.max
        for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%d.%m.%y %H:%M'):
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
        return datetime.max

    enriched_rows_sorted = sorted(enriched_rows, key=parse_date_for_sort)
    csv_rows = enriched_rows_sorted  # utiliser cette liste

    comptes_possibles = {str(c['id']) + '|' + c['type']: c for c in csv_data['comptes_possibles']}
    success_count = 0
    errors = []

    for i, row in enumerate(csv_rows):
        try:
            date_str = row[mapping['date']].strip()
            montant_str = row[mapping['montant']].strip().replace(',', '.')
            tx_type = row[mapping['type']].lower().strip()
            desc = row.get(mapping['description'], '').strip() if mapping['description'] else ''

            try:
                montant = Decimal(montant_str)
                if montant <= 0:
                    raise ValueError("Montant doit être > 0")
            except (InvalidOperation, ValueError):
                errors.append(f"Ligne {i+1}: montant invalide ({montant_str})")
                continue

            date_tx = None
            for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%d.%m.%y %H:%M'):
                try:
                    date_tx = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            if date_tx is None:
                errors.append(f"Ligne {i+1}: date invalide ({date_str})")
                continue

            source_key = request.form.get(f'row_{i}_source')
            dest_key = request.form.get(f'row_{i}_dest')

            if not source_key or source_key not in comptes_possibles:
                errors.append(f"Ligne {i+1}: compte source invalide")
                continue

            source_info = comptes_possibles[source_key]
            source_id = source_info['id']
            source_type = source_info['type']

            if tx_type == 'depot':
                ok, msg = g.models.transaction_financiere_model.create_depot(
                    compte_id=source_id, user_id=user_id, montant=montant,
                    description=desc, compte_type=source_type, date_transaction=date_tx
                )
            elif tx_type == 'retrait':
                ok, msg = g.models.transaction_financiere_model.create_retrait(
                    compte_id=source_id, user_id=user_id, montant=montant,
                    description=desc, compte_type=source_type, date_transaction=date_tx
                )
            elif tx_type == 'transfert':
                if not dest_key or dest_key not in comptes_possibles:
                    errors.append(f"Ligne {i+1}: compte destination requis")
                    continue
                dest_info = comptes_possibles[dest_key]
                dest_id = dest_info['id']
                dest_type = dest_info['type']
                if source_id == dest_id and source_type == dest_type:
                    errors.append(f"Ligne {i+1}: source et destination identiques")
                    continue
                ok, msg = g.models.transaction_financiere_model.create_transfert_interne(
                    source_type=source_type, source_id=source_id,
                    dest_type=dest_type, dest_id=dest_id,
                    user_id=user_id, montant=montant, description=desc, date_transaction=date_tx
                )
            else:
                errors.append(f"Ligne {i+1}: type inconnu '{tx_type}'")
                continue

            if ok:
                success_count += 1
            else:
                errors.append(f"Ligne {i+1}: {msg}")

        except Exception as e:
            errors.append(f"Ligne {i+1}: erreur inattendue ({str(e)})")

    if temp_key:
        db_csv_store.delete(temp_key)
    session.pop('csv_temp_key', None)
    session.pop('column_mapping', None)

    flash(f"✅ Import terminé : {success_count} transaction(s) créée(s).", "success")
    for err in errors[:5]:
        flash(f"❌ {err}", "danger")

    return redirect(url_for('banking.banking_dashboard'))


@bp.route('/import/temp/csv/distinct_confirm', methods=['POST'])
@login_required
def import_csv_distinct_confirm_temp():
    user_id = current_user.id
    temp_key = session.get('csv_temp_key')
    csv_data = db_csv_store.load(temp_key, user_id)
    if not csv_data:
        flash("Données expirées.", "danger")
        return redirect(url_for('banking.import_csv_upload_temp'))

    mapping = {
        'date': request.form['col_date'],
        'montant': request.form['col_montant'],
        'type': request.form['col_type'],
        'description': request.form.get('col_description') or None,
        'source': request.form['col_source'],
        'dest': request.form.get('col_dest') or None,
    }
    session['column_mapping'] = mapping

    csv_rows = csv_data['csv_rows']
    compte_names = set()
    source_col = mapping['source']
    for row in csv_rows:
        val = row.get(source_col, '').strip()
        if val:
            compte_names.add(val)
    dest_col = mapping.get('dest')
    if dest_col:
        for row in csv_rows:
            val = row.get(dest_col, '').strip()
            if val:
                compte_names.add(val)

    compte_names = sorted(compte_names)
    comptes_possibles = sorted(csv_data['comptes_possibles'], key=lambda x: x.get('nom', ''))

    # ❌ PLUS DE db_csv_store.save() ICI
    return render_template(
        'banking/import_csv_distinct_confirm_temp.html',
        compte_names=compte_names,
        comptes_possibles=comptes_possibles
    )


@bp.route('/import/temp/csv/final_distinct', methods=['POST'])
@login_required
def import_csv_final_distinct_temp():
    user_id = current_user.id
    temp_key = session.get('csv_temp_key')
    csv_data = db_csv_store.load(temp_key, user_id) if temp_key else None
    mapping = session.get('column_mapping')

    if not mapping or not csv_data:
        flash("Données manquantes.", "danger")
        return redirect(url_for('banking.import_csv_upload_temp'))

    csv_rows = csv_data['csv_rows']  # ✅ données brutes
    comptes_possibles = {str(c['id']) + '|' + c['type']: c for c in csv_data['comptes_possibles']}

    global_mapping = {}
    i = 0
    while f'compte_name_{i}' in request.form:
        name = request.form[f'compte_name_{i}']
        key = request.form[f'account_{i}']
        if key and key in comptes_possibles:
            global_mapping[name] = key
        i += 1

    success_count = 0
    errors = []

    for idx, row in enumerate(csv_rows):
        try:
            date_str = row[mapping['date']].strip()
            montant_str = row[mapping['montant']].strip().replace(',', '.')
            tx_type = row[mapping['type']].lower().strip()
            desc = row.get(mapping['description'], '').strip() if mapping.get('description') else ''

            try:
                montant = Decimal(montant_str)
                if montant <= 0:
                    raise ValueError("Montant doit être > 0")
            except (InvalidOperation, ValueError):
                errors.append(f"Ligne {idx+1}: montant invalide ({montant_str})")
                continue

            date_tx = None
            for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%dT%H:%M', '%Y-%m-%d', '%d.%m.%y %H:%M'):
                try:
                    date_tx = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            if date_tx is None:
                errors.append(f"Ligne {idx+1}: date invalide ({date_str})")
                continue

            source_val = row.get(mapping['source'], '').strip()
            source_key = global_mapping.get(source_val)

            if tx_type in ('depot', 'retrait'):
                if not source_key:
                    errors.append(f"Ligne {idx+1}: compte non associé pour '{source_val}'")
                    continue
            elif tx_type == 'transfert':
                dest_val = row.get(mapping['dest'], '').strip() if mapping.get('dest') else ''
                dest_key = global_mapping.get(dest_val) if dest_val else None
                if not source_key or not dest_key:
                    errors.append(f"Ligne {idx+1}: compte(s) non associé(s) (source: '{source_val}', dest: '{dest_val}')")
                    continue
                if source_key == dest_key:
                    errors.append(f"Ligne {idx+1}: source et destination identiques")
                    continue
            else:
                errors.append(f"Ligne {idx+1}: type inconnu '{tx_type}'")
                continue

            source_info = comptes_possibles[source_key]
            source_id = source_info['id']
            source_type = source_info['type']

            if tx_type == 'depot':
                ok, msg = g.models.transaction_financiere_model.create_depot(
                    compte_id=source_id, user_id=user_id, montant=montant,
                    description=desc, compte_type=source_type, date_transaction=date_tx
                )
            elif tx_type == 'retrait':
                ok, msg = g.models.transaction_financiere_model.create_retrait(
                    compte_id=source_id, user_id=user_id, montant=montant,
                    description=desc, compte_type=source_type, date_transaction=date_tx
                )
            elif tx_type == 'transfert':
                dest_info = comptes_possibles[dest_key]
                dest_id = dest_info['id']
                dest_type = dest_info['type']
                ok, msg = g.models.transaction_financiere_model.create_transfert_interne(
                    source_type=source_type, source_id=source_id,
                    dest_type=dest_type, dest_id=dest_id,
                    user_id=user_id, montant=montant, description=desc, date_transaction=date_tx
                )

            if ok:
                success_count += 1
            else:
                errors.append(f"Ligne {idx+1}: {msg}")

        except Exception as e:
            errors.append(f"Ligne {idx+1}: erreur inattendue ({str(e)})")

    if temp_key:
        db_csv_store.delete(temp_key)
    session.pop('csv_temp_key', None)
    session.pop('column_mapping', None)

    flash(f"✅ Import terminé : {success_count} transaction(s) créée(s).", "success")
    for err in errors[:5]:
        flash(f"❌ {err}", "danger")

    return redirect(url_for('banking.banking_dashboard'))

##### API comptes

@bp.route('/api/banking/sous-comptes/<int:compte_id>')
@login_required
def api_sous_comptes(compte_id):
    return jsonify({'success': True,
                    'sous_comptes': g.models.sous_compte_model.get_by_compte_principal_id(compte_id)})

@bp.route("/statistiques")
@login_required
def banking_statistiques():
    user_id = current_user.id
    #statistiques_bancaires_model = StatistiquesBancaires(g.db_manager)
    
    # Récupérer la période (en mois) depuis la requête GET, valeur par défaut : 6
    nb_mois = request.args.get("period", 6)
    try:
        nb_mois = int(nb_mois)
    except ValueError:
        nb_mois = 6

    # Récupérer les stats globales
    stats = g.models.stats_model.get_resume_utilisateur(user_id)
    print("Stats globales:", stats)
    
    # Répartition par banque
    repartition = g.models.stats_model.get_repartition_par_banque(user_id)
    print("Répartition par banque:", repartition)
    
    # Préparer les données pour le graphique de répartition
    repartition_labels = [item['nom_banque'] for item in repartition]
    repartition_values = [float(item['montant_total']) for item in repartition]
    
    # Utiliser les couleurs des banques si disponibles, sinon générer des couleurs aléatoires
    repartition_colors = []
    for item in repartition:
        if 'couleur' in item and item['couleur']:
            repartition_colors.append(item['couleur'])
        else:
            repartition_colors.append(f"#{random.randint(0, 0xFFFFFF):06x}")

    # Évolution épargne (avec filtre nb_mois)
    evolution = g.models.stats_model.get_evolution_epargne(user_id, nb_mois)
    print("Évolution épargne:", evolution)
    
    # Préparer les données pour le graphique d'évolution
    evolution_labels = []
    evolution_values = []
    
    if evolution:
        evolution_labels = [item['mois'] for item in evolution][::-1]  # Inverser pour ordre chronologique
        evolution_values = [float(item['epargne_mensuelle']) for item in evolution][::-1]

    return render_template(
        "banking/statistiques.html",
        stats=stats,
        repartition_labels=repartition_labels,
        repartition_values=repartition_values,
        repartition_colors=repartition_colors,
        evolution_labels=evolution_labels,
        evolution_values=evolution_values,
        selected_period=nb_mois
    )
@bp.route("/statistiques/dashboard")
@login_required
def banking_statistique_dashboard():
    user_id = current_user.id
    #statistiques_bancaires_model = StatistiquesBancaires(g.db_manager)
    
    # Récupérer la période depuis la requête
    nb_mois = request.args.get("period", 6)
    try:
        nb_mois = int(nb_mois)
    except ValueError:
        nb_mois = 6
    
    # Récupérer les statistiques en utilisant les nouvelles fonctions
    stats = g.models.stats_model.get_resume_utilisateur(user_id)
    print("Stats globales:", stats)
    # Répartition par banque
    repartition = g.models.stats_model.get_repartition_par_banque(user_id)
    repartition_labels = [item['nom_banque'] for item in repartition]
    print(repartition_labels)
    repartition_values = [float(item['montant_total']) for item in repartition]
    print(repartition_values)
    repartition_colors = [item.get('couleur', f"#{random.randint(0, 0xFFFFFF):06x}") for item in repartition]

    total = sum(repartition_values) or 1
    repartition_dict = {label: round((val / total) * 100, 2) for label, val in zip(repartition_labels, repartition_values)}

    print(repartition_dict)
    print(f'Voici la {repartition_dict} avec {len(repartition_dict)} élements')
    # Évolution épargne
    evolution = g.models.stats_model.get_evolution_epargne(user_id, nb_mois)
    evolution_labels = [item['mois'] for item in evolution]
    evolution_values = [float(item['epargne_mensuelle']) for item in evolution]
    
    return render_template(
        "banking/dashboard_statistique.html",
        stats=stats,
        repartition_labels=repartition_labels,
        repartition_values=repartition_values,
        repartition_colors=repartition_colors,
        evolution_labels=evolution_labels,
        evolution_values=evolution_values,
        selected_period=nb_mois,
        repartition=repartition,
        repartition_dict=repartition_dict
    )

@bp.route('/api/banking/repartition')
@login_required
def api_repartition_banques():
    return jsonify({'success': True,
                    'repartition': g.models.stats_model.get_repartition_par_banque(current_user.id)})

@bp.route('/banking/sous-compte/supprimer/<int:sous_compte_id>')
@login_required
def banking_supprimer_sous_compte(sous_compte_id):
    sous_compte = g.models.sous_compte_model.get_by_id(sous_compte_id)
    if not sous_compte:
        flash('Sous-compte non trouvé', 'error')
        return redirect(url_for('banking.banking_dashboard'))    
    compte_id = sous_compte['compte_principal_id']
    if g.models.sous_compte_model.delete(sous_compte_id):
        flash(f'Sous-compte "{sous_compte["nom_sous_compte"]}" supprimé avec succès', 'success')
    else:
        flash('Impossible de supprimer un sous-compte avec un solde positif', 'error')    
    return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
##### Partie comptabilité
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, current_app, g, session, abort, send_file
from flask_login import login_required, current_user
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, date, time
from calendar import monthrange
from app.models import DatabaseManager, Banque, ComptePrincipal, SousCompte, TransactionFinanciere, StatistiquesBancaires, PlanComptable, EcritureComptable, HeureTravail, Salaire, SyntheseHebdomadaire, SyntheseMensuelle, Contrat, Contacts, ContactCompte, ComptePrincipalRapport, CategorieComptable
from io import StringIO
import os
import csv as csv_mod

import io
import traceback
import random
from collections import defaultdict
from . import db_csv_store

# --- DÉBUT DES AJOUTS (8 lignes) ---
from flask import _app_ctx_stack

#class ModelManager:
#    def __getattr__(self, name):
#        ctx = _app_ctx_stack.top
#        if not hasattr(ctx, 'banking_models'):
#            db_config = current_app.config.get('DB_CONFIG')
#            g.db_manager = DatabaseManager(db_config)
#            ctx.banking_models = {
#                'banque_model': Banque(g.db_manager),
#                'compte_model': ComptePrincipal(g.db_manager),
#                'sous_compte_model': SousCompte(g.db_manager),
#                'transaction_financiere_model': TransactionFinanciere(g.db_manager),
#                'stats_model': StatistiquesBancaires(g.db_manager),
#                'plan_comptable_model': PlanComptable(g.db_manager),
#                'ecriture_comptable_model': EcritureComptable(g.db_manager),
#                'contact_model': Contacts(g.db_manager),
#                'heure_model': HeureTravail(g.db_manager),
#                'contrat_model': Contrat(g.db_manager)
#            }
#        return ctx.banking_g.models.get(name)

#models = ModelManager()
# --- FIN DES AJOUTS ---

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


    # ---- Fonctions utilitaires ----
def get_comptes_utilisateur(user_id):
        """Retourne les comptes avec sous-comptes et soldes"""
        try:
            comptes = g.models.compte_model.get_by_user_id(user_id)
            for compte in comptes:
                compte['sous_comptes'] = g.models.sous_compte_model.get_by_compte_principal_id(compte['id'])
                compte['solde_total'] = g.models.compte_model.get_solde_total_avec_sous_comptes(compte['id'])
            logging.info(f"banking 70 Comptes sous la liste -comptes- détaillés pour l'utilisateur {user_id}: {len(comptes)}")
            return comptes
        except Exception as e:
            logging.error(f" banking73Erreur lors de la récupération des comptes pour l'utilisateur {user_id}: {e}")
            return []




    # ---- ROUTES ----
@bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.liste_utilisateurs'))
        else:
            return redirect(url_for('banking.dashboard'))
    return redirect(url_for('auth.login'))
     

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
    
    return render_template('banking/compte_detail.html',
                        compte=compte,
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
    limite = 10

    svg_code = None
    if request.method == 'POST':
        date_debut = request.form.get('date_debut', date_debut)
        date_fin = request.form.get('date_fin', date_fin)
        direction = request.form.get('direction', 'tous')
        limite = int(request.form.get('limite', 10))

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
    top_comptes = g.models.transaction_financiere_model.get_top_comptes_echanges(
        compte_id, user_id,
        (date.today() - timedelta(days=365)).isoformat(),
        date.today().isoformat(),
        'tous',
        50
    )
    comptes_cibles_possibles = top_comptes

    # Valeurs par défaut
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
                    couleur_envoyee = request.form.get(f'couleur_compte_{next((c["compte_id"] for c in top_comptes if c["nom_compte"] == nom_serie), "unknown")}', None)
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

@bp.route('/comptabilite/statistiques')
@login_required
def statistiques_comptables():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to') 
    stats = g.models.ecriture_comptable_model.get_stats_by_categorie(
        user_id=current_user.id,
        date_from=date_from,
        date_to=date_to
    )
    # Calcul des totaux
    total_depenses = sum(s['total_depenses'] or 0 for s in stats)
    total_recettes = sum(s['total_recettes'] or 0 for s in stats)
    resultat = total_recettes - total_depenses
    return render_template('comptabilite/statistiques.html',
                        stats=stats,
                        total_depenses=total_depenses,
                        total_recettes=total_recettes,
                        resultat=resultat,
                        date_from=date_from,
                        date_to=date_to)

### Partie comptabilité 
@bp.route('/comptabilite/categories')
@login_required
def liste_categories_comptables():
    #plan_comptable = PlanComptable(g.db_manager)
    categories = g.models.categorie_comptable_model.get_all_categories()
    return render_template('comptabilite/categories.html', categories=categories)

@bp.route('/comptabilite/categories/nouvelle', methods=['GET', 'POST'])
@login_required
def nouvelle_categorie():
    """Crée une nouvelle catégorie comptable"""
    #plan_comptable = PlanComptable(g.db_manager)
    if request.method == 'POST':
        try:
            data = {
                'numero': request.form['numero'],
                'nom': request.form['nom'],
                'type_compte': request.form['type'],
                'parent_id': request.form.get('parent_id') or None
            }         
            if g.models.categorie_comptable_model.create(data):
                flash('Catégorie créée avec succès', 'success')
                return redirect(url_for('banking.liste_categories_comptables'))
            else:
                flash('Erreur lors de la création', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    categories = g.models.categorie_comptable_model.get_all_categories()
    return render_template('comptabilite/edit_categorie.html', 
                        categories=categories,
                        categorie=None)

@bp.route('/comptabilite/categories/<int:categorie_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_categorie(categorie_id):
    """Modifie une catégorie comptable existante"""
    #plan_comptable = PlanComptable(g.db_manager)
    categorie = g.models.categorie_comptable_model.get_by_id(categorie_id)
    if not categorie:
        flash('Catégorie introuvable', 'danger')
        return redirect(url_for('banking.liste_categories_comptables'))
    if request.method == 'POST':
        try:
            data = {
                'numero': request.form['numero'],
                'nom': request.form['nom'],
                'type_compte': request.form['type_compte'],
                'parent_id': request.form.get('groupe') or None
            }
            if g.models.categorie_comptable_model.update(categorie_id, data):
                flash('Catégorie mise à jour avec succès', 'success')
                return redirect(url_for('banking.liste_categories_comptables'))
            else:
                flash('Erreur lors de la mise à jour', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    categories = g.models.categorie_comptable_model.get_all_categories()
    types_compte = ['Actif', 'Passif', 'Charge', 'Revenus']
    types_tva = ['', 'taux_plein', 'taux_reduit', 'taux_zero', 'exonere']
    return render_template('comptabilite/edit_categorie.html', 
                        categories=categories,
                        categorie=categorie,
                        types_compte=types_compte,
                        types_tva=types_tva)

@bp.route('/comptabilite/categories/import-csv', methods=['POST'])
@login_required
def import_plan_comptable_csv():
    """Importe le plan comptable depuis un fichier CSV"""
    #plan_comptable = PlanComptable(g.db_manager)
    try:
        # Vérifier si un fichier a été uploadé
        if 'csv_file' not in request.files:
            flash('Aucun fichier sélectionné', 'danger')
            return redirect(url_for('banking.liste_categories_comptables'))  
        file = request.files['csv_file']
        if file.filename == '':
            flash('Aucun fichier sélectionné', 'danger')
            return redirect(url_for('banking.liste_categories_comptables'))
        if file and file.filename.endswith('.csv'):
            # Lire le fichier CSV
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv_mod.reader(stream)
            # Sauter l'en-tête
            next(csv_input)
            connection = g.models.g.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Vider la table existante
            cursor.execute("DELETE FROM categories_comptables")
            
            # Insérer les nouvelles données
            for row in csv_input:
                if len(row) >= 7:  # Vérifier qu'il y a assez de colonnes
                    cursor.execute("""
                        INSERT INTO categories_comptables 
                        (numero, nom, groupe, type_compte, compte_systeme, compte_associe, type_tva, actif)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row[0], row[1], 
                        int(row[2]) if row[2] else None, 
                        row[3], 
                        row[4] if row[4] else None, 
                        row[5] if row[5] else None, 
                        row[6] if row[6] else None,
                        True
                    ))
            connection.commit()
            cursor.close()
            connection.close()
            flash('Plan comptable importé avec succès depuis le CSV', 'success')
        else:
            flash('Format de fichier non supporté. Veuillez uploader un fichier CSV.', 'danger')
    except Exception as e:
        flash(f'Erreur lors de l\'importation: {str(e)}', 'danger')
    return redirect(url_for('banking.liste_categories_comptables'))

@bp.route('/comptabilite/categories/<int:categorie_id>/delete', methods=['POST'])
@login_required
def delete_categorie(categorie_id):
    """Supprime une catégorie comptable"""
    if g.models.categorie_comptable_model.delete(categorie_id):
        flash('Catégorie supprimée avec succès', 'success')
    else:
        flash('Erreur lors de la suppression', 'danger')
    
    return redirect(url_for('banking.liste_categories_comptables'))

@bp.route('/comptabilite/nouveau-contact', methods=['GET', 'POST'])
@login_required
def nouveau_contact_comptable():
    if request.method == 'POST':
        try:
            data = {
                'nom': request.form['nom'],
                'email': request.form.get('email', ''),
                'telephone': request.form.get('telephone', ''),
                'adresse': request.form.get('adresse', ''),
                'code_postal': request.form.get('code_postal', ''),
                'ville': request.form.get('ville', ''),
                'pays': request.form.get('pays', ''),
                'utilisateur_id': current_user.id
            }
                # Debug: afficher les données
            print(f"Données à insérer: {data}")
            if g.models.contact_model.create(data):
                flash('Contact créé avec succès', 'success')
                return redirect(url_for('banking.liste_contacts_comptables'))
            else:
                flash('Erreur lors de la création du contact', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger') 
    # Pour les requêtes GET, on affiche le modal via la page liste_contacts_comptables
    redirect_to = request.form.get('redirect_to', url_for('banking.liste_ecritures'))
    return redirect(redirect_to)


@bp.route('/comptabilite/contacts/<int:contact_id>/delete', methods=['POST'])
@login_required
def delete_contact_comptable(contact_id):
    """Supprime un contact comptable"""
    if g.models.contact_model.delete(contact_id, current_user.id):
        flash('Contact supprimé avec succès', 'success')
    else:
        flash('Erreur lors de la suppression du contact', 'danger')
    
    return redirect(url_for('banking.liste_contacts_comptables'))


@bp.route('/comptabilite/contacts')
@login_required
def liste_contacts_comptables():
    """
    Affiche la liste des contacts comptables.
    Gère aussi l'affichage conditionnel du modal de liaison contact ↔ compte.
    """
    # Récupérer tous les contacts
    contacts = g.models.contact_model.get_all(current_user.id)

    # Variables pour le modal de liaison (désactivé par défaut)
    show_link_compte_modal = False
    contact = None
    comptes_interagis = []
    comptes_lies = []
    ids_lies = set()

    # Vérifier si on demande d'afficher le modal de liaison
    if request.args.get('link_compte') == '1':
        contact_id = request.args.get('contact_id', type=int)
        if contact_id:
            contact = g.models.contact_model.get_by_id(contact_id, current_user.id)
            if contact:
                show_link_compte_modal = True
                # Récupérer TOUS les comptes avec qui l'utilisateur interagit
                comptes_interagis = g.models.transaction_financiere_model.get_comptes_interagis(current_user.id)
                print(f'Comptes interagis: {comptes_interagis}')
                # Récupérer les comptes déjà liés à ce contact
                comptes_lies = g.models.contact_compte_model.get_comptes_for_contact(contact_id, current_user.id)
                ids_lies = {c['id'] for c in comptes_lies}

    # --- Préparer la liste enrichie pour le template (avec info de liaison) ---
    contacts_enrichis = []
    for c in contacts:
        comptes_lies_contact = g.models.contact_compte_model.get_comptes_for_contact(c['id_contact'], current_user.id)
        contacts_enrichis.append({
            'contact': c,
            'comptes_lies': comptes_lies_contact,
            'a_des_comptes_lies': len(comptes_lies_contact) > 0
        })

    return render_template(
        'comptabilite/liste_contacts.html',
        contacts=contacts_enrichis,
        show_link_compte_modal=show_link_compte_modal,
        contact=contact,
        comptes_interagis=comptes_interagis,
        comptes_lies=comptes_lies,
        ids_lies=ids_lies
    )

@bp.route('/comptabilite/contacts/<int:contact_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_contact_comptable(contact_id):
    """Modifie un contact comptable existant"""
    #contact_model = Contacts(g.db_manager)
    contact = g.models.contact_model.get_by_id(contact_id, current_user.id)
    print(f'voici les données du contact: {contact}')
    if not contact:
        flash('Contact introuvable', 'danger')
        return redirect(url_for('banking.liste_contacts_comptables'))
    if request.method == 'POST':
        try:
            data = {
                'nom': request.form['nom'],
                'email': request.form.get('email', ''),
                'telephone': request.form.get('telephone', ''),
                'adresse': request.form.get('adresse', ''),
                'code_postal': request.form.get('code_postal', ''),
                'ville': request.form.get('ville', ''),
                'pays': request.form.get('pays', '')
            }
            # Correction: utiliser current_user.id comme dernier paramètre
            if g.models.contact_model.update(contact_id, data, current_user.id):
                print(f'Contact mis à jour avec les données: {data}')
                flash('Contact mis à jour avec succès', 'success')
                return redirect(url_for('banking.liste_contacts_comptables'))
            else:
                flash('Erreur lors de la mise à jour du contact', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    return render_template('comptabilite/nouveau_contact.html', contact=contact)

@bp.route('/comptabilite/contacts/<int:contact_id>/link-compte', methods=['POST'])
@login_required
def link_contact_to_compte(contact_id):
    """Traite uniquement la liaison (pas d'affichage)."""
    contact = g.models.contact_model.get_by_id(contact_id, current_user.id)
    if not contact:
        flash("Contact introuvable", "danger")
        return redirect(url_for('banking.liste_contacts_comptables'))

    compte_id = request.form.get('compte_id', type=int)
    if not compte_id:
        flash("Veuillez sélectionner un compte", "warning")
    else:
        success = g.models.contact_compte_model.link_to_compte(
            contact_id=contact_id,
            compte_id=compte_id,
            utilisateur_id=current_user.id
        )
        if success:
            flash(f"Le contact « {contact['nom']} » a été lié au compte sélectionné", "success")
        else:
            flash("Erreur lors de la liaison", "danger")

    return redirect(url_for('banking.liste_contacts_comptables'))

@bp.route('/comptabilite/ecritures')
@login_required
def liste_ecritures():
    """Affiche la liste des écritures comptables avec filtrage par statut"""
    # Récupération des paramètres de filtrage
    compte_id = request.args.get('compte_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    categorie_id = request.args.get('categorie_id')
    id_contact = request.args.get('id_contact')
    statut = request.args.get('statut', 'tous')
    
    # Statuts pour le template
    statuts_disponibles = [
        {'value': 'tous', 'label': 'Tous les statuts'},
        {'value': 'pending', 'label': 'En attente'},
        {'value': 'validée', 'label': 'Validées'},
        {'value': 'rejetée', 'label': 'Rejetées'}
    ]
    
    # Préparer les filtres pour la méthode
    filtres = {
        'user_id': current_user.id,
        'date_from': date_from,
        'date_to': date_to,
        'statut': statut if statut != 'tous' else None,
        'id_contact': int(id_contact) if id_contact else None,
        'compte_id': int(compte_id) if compte_id else None,
        'categorie_id': int(categorie_id) if categorie_id else None,
        'limit': 1000  # Ou la limite que vous souhaitez
    }
    
    # Utiliser la nouvelle méthode de filtrage
    ecritures = g.models.ecriture_comptable_model.get_with_filters(**filtres)
    print(f"Ecritures récupérées avec filtres {filtres}: {ecritures}")
    # Récupérer les données supplémentaires
    comptes = g.models.compte_model.get_by_user_id(current_user.id)
    contacts = g.models.contact_model.get_all(current_user.id)
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    contact_map = {c['id_contact']: c['nom'] for c in contacts}

    # Gestion du modal de liaison (identique à votre code original)
    show_link_modal = request.args.get('show_link_modal') == '1'
    ecriture_link = None
    transactions_eligibles = []

    if show_link_modal:
        eid = request.args.get('ecriture_id', type=int)
        ecriture_link = g.models.ecriture_comptable_model.get_by_id(eid)
        if ecriture_link and ecriture_link['utilisateur_id'] == current_user.id:
            date_tx = ecriture_link['date_ecriture']
            all_tx = g.models.transaction_financiere_model.get_all_user_transactions(
                user_id=current_user.id,
                date_from=date_tx,
                date_to=date_tx
            )[0]
            for tx in all_tx:
                full_tx = g.models.transaction_financiere_model.get_transaction_with_ecritures_total(
                    tx['id'], current_user.id
                )
                if full_tx:
                    transactions_eligibles.append(full_tx)

    # Gestion du modal de détail de transaction (identique)
    show_transaction_modal = request.args.get('show_transaction_modal') == '1'
    transaction_detail = None

    if show_transaction_modal:
        tid = request.args.get('transaction_id', type=int)
        if tid:
            transaction_detail = g.models.transaction_financiere_model.get_transaction_by_id(tid)
            if not (transaction_detail and transaction_detail.get('owner_user_id') == current_user.id):
                transaction_detail = None

    return render_template('comptabilite/ecritures.html',
        ecritures=ecritures,
        comptes=comptes,
        categories=categories,  # Nouveau
        compte_selectionne=compte_id,
        statuts_disponibles=statuts_disponibles,
        statut_selectionne=statut,
        contacts=contacts,
        contact_selectionne=id_contact,
        date_from=date_from,
        date_to=date_to,
        categorie_id=categorie_id,  # Important pour préserver la sélection
        show_link_modal=show_link_modal,
        ecriture_link=ecriture_link,
        transactions_eligibles=transactions_eligibles,
        contact_map=contact_map,
        show_transaction_modal=show_transaction_modal,
        transaction_detail=transaction_detail
    )

@bp.route('/comptabilite/ecritures/by-contact/<int:contact_id>', methods=['GET'])
@login_required
def liste_ecritures_par_contact(contact_id):
    """Affiche les écritures associées à un contact spécifique"""
    contact = g.models.contact_model.get_by_id(contact_id, current_user.id)
    if not contact:
        flash('Contact introuvable', 'danger')
        return redirect(url_for('banking.liste_contacts_comptables'))
    
    ecritures = g.models.ecriture_comptable_model.get_by_contact_id(contact_id, utilisateur_id=current_user.id)
    comptes = g.models.compte_model.get_by_user_id(current_user.id)

    # Modal de liaison
    show_link_modal = request.args.get('show_link_modal') == '1'
    ecriture_link = None
    transactions_eligibles = []

    if show_link_modal:
        eid = request.args.get('ecriture_id', type=int)
        ecriture_link = g.models.ecriture_comptable_model.get_by_id(eid)
        if ecriture_link and ecriture_link['utilisateur_id'] == current_user.id:
            date_tx = ecriture_link['date_ecriture']
            # 🔥 CORRECTION : Récupérer TOUTES les transactions de l'utilisateur à cette date
            transactions_all, _ = g.models.transaction_financiere_model.get_all_user_transactions(
                user_id=current_user.id,
                date_from=date_tx.strftime('%Y-%m-%d'),
                date_to=date_tx.strftime('%Y-%m-%d')
            )
            # 🔥 CORRECTION : Ne garder que celles qui ont un solde cohérent avec le montant de l'écriture
            montant_ecriture = Decimal(str(ecriture_link['montant']))
            for tx in transactions_all:
                montant_tx = Decimal(str(tx.get('montant', 0)))
                if abs(montant_tx - montant_ecriture) <= Decimal('0.02'):  # tolérance de 2 centimes
                    # Récupérer total des écritures liées à cette transaction
                    total_ecritures = g.models.ecriture_comptable_model.get_total_ecritures_for_transaction(
                        tx['id'], current_user.id
                    )
                    if total_ecritures + montant_ecriture <= montant_tx:
                        transactions_eligibles.append(tx)

    # 🔥 AJOUT : Gestion du modal de détail de transaction
    show_transaction_modal = request.args.get('show_transaction_modal') == '1'
    transaction_detail = None

    if show_transaction_modal:
        tid = request.args.get('transaction_id', type=int)
        if tid:
            transaction_detail = g.models.transaction_financiere_model.get_transaction_by_id(tid)
            if not (transaction_detail and transaction_detail.get('owner_user_id') == current_user.id):
                transaction_detail = None

    return render_template('comptabilite/ecritures_par_contact.html',
        ecritures=ecritures,
        contact=contact,
        comptes=comptes,
        show_link_modal=show_link_modal,
        ecriture_link=ecriture_link,
        transactions_eligibles=transactions_eligibles,  # 🔥 CORRECTION : Cette variable doit être définie
        show_transaction_modal=show_transaction_modal,
        transaction_detail=transaction_detail
    )
@bp.route('/comptabilite/ecritures/update_statut/<int:ecriture_id>', methods=['POST'])
@login_required
def update_statut_ecriture(ecriture_id):
    """Met à jour uniquement le statut d'une écriture via modal"""
    nouveau_statut = request.form.get('statut')
    commentaire = request.form.get('commentaire', '')
    
    if nouveau_statut not in ['pending', 'validée', 'rejetée']:
        flash('Statut invalide', 'error')
        return redirect(request.referrer or url_for('banking.liste_ecritures'))
    
    try:
        success = g.models.ecriture_comptable_model.update_statut(
            ecriture_id, current_user.id, nouveau_statut
        )
        
        if success:
            if commentaire:
                logging.info(f"Statut écriture {ecriture_id} changé: {commentaire}")
            flash(f"Statut mis à jour: {nouveau_statut}", 'success')
        else:
            flash("Erreur lors de la mise à jour", 'error')
            
    except Exception as e:
        logging.error(f"Erreur mise à jour statut: {e}")
        flash("Erreur lors de la mise à jour", 'error')
    
    return redirect(request.referrer or url_for('banking.liste_ecritures'))

##### Fichier dans transactions 
@bp.route('/comptabilite/ecritures/upload_fichier/<int:ecriture_id>', methods=['POST'])
@login_required
def upload_fichier_ecriture(ecriture_id):
    """Upload un fichier pour une écriture"""
    logging.info(f"Route upload appelée - Écriture: {ecriture_id}, Utilisateur: {current_user.id}")
    if 'fichier' not in request.files:
        flash('Aucun fichier sélectionné', 'error')
        return redirect(request.referrer or url_for('banking.liste_ecritures'))
    
    fichier = request.files['fichier']
    logging.info(f"Fichier reçu - Nom: {fichier.filename}, Type: {fichier.content_type}")
    success, message = g.models.ecriture_comptable_model.ajouter_fichier(
        ecriture_id, current_user.id, fichier
    )
    logging.info(f"Résultat upload: {success} - {message}")
    if success:
        flash(message, 'success')
        flash(f'Fichier uploadé avec succès {fichier.filename} à {ecriture_id} sur {fichier.content_type}', 'success')
    else:
        flash(message, 'error')
    
    return redirect(request.referrer or url_for('banking.liste_ecritures'))

@bp.route('/test_upload')
@login_required
def test_upload():
    """Route de test pour vérifier le dossier d'upload"""
 # Importez votre classe
    
    # Créer une instance du modèle

    # Tester le dossier
    result = g.models.ecriture_comptable_model.test_dossier_upload()
    
    return f"Test terminé - Vérifiez les logs pour les résultats détaillés: {result}"
@bp.route('/comptabilite/ecritures/download_fichier/<int:ecriture_id>')
@login_required
def download_fichier_ecriture(ecriture_id):
    """Télécharge le fichier joint d'une écriture"""
    fichier_info = g.models.ecriture_comptable_model.get_fichier(ecriture_id, current_user.id)
    
    if not fichier_info:
        flash('Fichier non trouvé', 'error')
        return redirect(request.referrer or url_for('banking.liste_ecritures'))
    
    try:
        return send_file(
            fichier_info['chemin_complet'],
            as_attachment=True,
            download_name=fichier_info['nom_original'],
            mimetype=fichier_info['type_mime']
        )
    except Exception as e:
        logging.error(f"Erreur téléchargement fichier: {e}")
        flash('Erreur lors du téléchargement du fichier', 'error')
        return redirect(request.referrer or url_for('banking.liste_ecritures'))

@bp.route('/comptabilite/ecritures/view_fichier/<int:ecriture_id>')
@login_required
def view_fichier_ecriture(ecriture_id):
    """Affiche le fichier joint dans le navigateur"""
    logging.info(f"📍 Route view_fichier appelée - Écriture: {ecriture_id}")
    
    fichier_info = g.models.ecriture_comptable_model.get_fichier(ecriture_id, current_user.id)
    
    if not fichier_info:
        logging.error(f"❌ Fichier non trouvé pour l'écriture {ecriture_id}")
        flash('Fichier non trouvé', 'error')
        return redirect(request.referrer or url_for('banking.liste_ecritures'))
    
    logging.info(f"📍 Fichier info: {fichier_info}")
    
    try:
        # Vérifications supplémentaires
        if not os.path.exists(fichier_info['chemin_complet']):
            logging.error(f"❌ Fichier manquant sur le disk: {fichier_info['chemin_complet']}")
            flash('Fichier manquant sur le serveur', 'error')
            return redirect(request.referrer or url_for('banking.liste_ecritures'))
        
        logging.info(f"📍 Envoi du fichier: {fichier_info['chemin_complet']}")
        
        return send_file(
            fichier_info['chemin_complet'],
            as_attachment=False,
            download_name=fichier_info['nom_original'],
            mimetype=fichier_info['type_mime']
        )
    except Exception as e:
        logging.error(f"❌ Erreur send_file: {str(e)}")
        logging.error(f"❌ Traceback complète: {traceback.format_exc()}")
        flash('Erreur lors de l\'affichage du fichier', 'error')
        return redirect(request.referrer or url_for('banking.liste_ecritures'))
@bp.route('/comptabilite/ecritures/supprimer_fichier/<int:ecriture_id>', methods=['POST'])
@login_required
def supprimer_fichier_ecriture(ecriture_id):
    """Supprime le fichier joint d'une écriture"""
    success, message = g.models.ecriture_comptable_model.supprimer_fichier(
        ecriture_id, current_user.id
    )
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(request.referrer or url_for('banking.liste_ecritures'))
#### Catégorie des transactions
# routes_categories

    
@bp.route('/gestion_categorie')
@login_required
def gestion_categories():
    """Page principale de gestion des catégories"""
    try:
        categories = g.models.categorie_transaction_model.get_categories_utilisateur(current_user.id)
        logging.info(f"Catégories récupérées pour utilisateur {current_user.id} : {categories}")
        statistiques = g.models.categorie_transaction_model.get_statistiques_categories(current_user.id)
        logging.info(f"Statistiques des catégories pour utilisateur {current_user.id} : {statistiques}")
        # Séparer par type pour l'affichage
        categories_revenus = [c for c in categories if c['type_categorie'] == 'Revenu']
        logging.info(f"Catégories de revenus pour utilisateur {current_user.id} : {categories_revenus}")
        categories_depenses = [c for c in categories if c['type_categorie'] == 'Dépense']
        logging
        categories_transferts = [c for c in categories if c['type_categorie'] == 'Transfert']
        logging.info(f"Chargement page catégories pour utilisateur {current_user.id} : {categories}")
        return render_template(
            'categories/old-gestion_categories.html',
            categories=categories,
            categories_revenus=categories_revenus,
            categories_depenses=categories_depenses,
            categories_transferts=categories_transferts,
            statistiques=statistiques
        )
    except Exception as e:
        logging.error(f"Erreur chargement page catégories: {e}")
        flash("Erreur lors du chargement des catégories", "error")
        return redirect(url_for('banking.banking_dashboard'))

@bp.route('/categorie/creer', methods=['GET', 'POST'])
@login_required
def creer_categorie():
    """Créer une nouvelle catégorie"""
    if request.method == 'POST':
        try:
            nom = request.form.get('nom', '').strip()
            type_categorie = request.form.get('type_categorie', 'Dépense')
            description = request.form.get('description', '').strip()
            couleur = request.form.get('couleur', '')
            icone = request.form.get('icone', '')
            budget_mensuel = request.form.get('budget_mensuel', 0)
            if not nom:
                flash("Le nom de la catégorie est obligatoire", "error")
                return render_template('categories/creer_categorie.html')
            if len(nom) > 100:
                flash("Le nom de la catégorie ne peut pas dépasser 100 caractères", "error")
                return render_template('categories/creer_categorie.html')
            
            # 🔥 VALIDATION : Budget mensuel
            try:
                if budget_mensuel:
                    budget_mensuel = float(budget_mensuel)
                    if budget_mensuel < 0:
                        flash("Le budget mensuel ne peut pas être négatif", "error")
                        return render_template('categories/creer_categorie.html')
            except ValueError:
                flash("Le budget mensuel doit être un nombre valide", "error")
                return render_template('categories/creer_categorie.html')

            success, message = g.models.categorie_transaction_model.creer_categorie(
                current_user.id, nom, type_categorie, description, couleur, icone, budget_mensuel
            )
            
            if success:
                flash(message, "success")
                return redirect(url_for('banking.gestion_categories'))
            else:
                flash(message, "error")
                
        except Exception as e:
            logging.error(f"Erreur création catégorie: {e}")
            flash("Erreur lors de la création de la catégorie", "error")
    
    return render_template('categories/creer_categorie.html')

@bp.route('/categorie/<int:categorie_id>/modifier', methods=['GET', 'POST'])
@login_required
def modifier_categorie(categorie_id):
    """Modifier une catégorie existante"""
    categorie = g.models.categorie_transaction_model.get_categorie_par_id(categorie_id, current_user.id)
    
    if not categorie:
        flash("Catégorie non trouvée", "error")
        return redirect(url_for('banking.gestion_categories'))
    
    if request.method == 'POST':
        try:
            nom = request.form.get('nom', '').strip()
            description = request.form.get('description', '').strip()
            couleur = request.form.get('couleur', '')
            icone = request.form.get('icone', '')
            budget_mensuel = request.form.get('budget_mensuel', 0)
            
            updates = {}
            if nom and nom != categorie['nom']:
                updates['nom'] = nom
            if description != categorie.get('description', ''):
                updates['description'] = description
            if couleur and couleur != categorie.get('couleur', ''):
                updates['couleur'] = couleur
            if icone != categorie.get('icone', ''):
                updates['icone'] = icone
            if budget_mensuel:
                try:
                    budget_value = float(budget_mensuel) if budget_mensuel else 0
                    if budget_value < 0:
                        flash("Le budget mensuel ne peut pas être négatif", "error")
                        return render_template('categories/modifier_categorie.html', categorie=categorie)
                    updates['budget_mensuel'] = budget_value
                except ValueError:
                    flash("Le budget mensuel doit être un nombre valide", "error")
                    return render_template('categories/modifier_categorie.html', categorie=categorie)
            
            if updates:
                success, message = g.models.categorie_transaction_model.modifier_categorie(
                    categorie_id, current_user.id, **updates
                )
                
                if success:
                    flash(message, "success")
                    return redirect(url_for('categories.gestion_categories'))
                else:
                    flash(message, "error")
            else:
                flash("Aucune modification apportée", "info")
                
        except Exception as e:
            logging.error(f"Erreur modification catégorie: {e}")
            flash("Erreur lors de la modification de la catégorie", "error")
    
    return render_template('categories/modifier_categorie.html', categorie=categorie)

@bp.route('/categorie/<int:categorie_id>/supprimer', methods=['POST'])
@login_required
def supprimer_categorie(categorie_id):
    """Supprimer une catégorie"""
    try:
        # 🔥 AJOUT : Vérification supplémentaire
        categorie = g.models.categorie_transaction_model.get_categorie_par_id(categorie_id, current_user.id)
        if not categorie:
            flash("Catégorie non trouvée", "error")
            return redirect(url_for('banking.gestion_categories'))
        
        success, message = g.models.categorie_transaction_model.supprimer_categorie(categorie_id, current_user.id)
        
        if success:
            flash(message, "success")
        else:
            flash(message, "error")
            
    except Exception as e:
        logging.error(f"Erreur suppression catégorie: {e}")
        flash("Erreur lors de la suppression de la catégorie", "error")
    
    return redirect(url_for('banking.gestion_categories'))

@bp.route('/categorie/<int:categorie_id>/transactions')
@login_required
def transactions_par_categorie(categorie_id):
    """Affiche les transactions d'une catégorie spécifique"""
    try:
        categorie = g.models.categorie_transaction_model.get_categorie_par_id(categorie_id, current_user.id)
        if not categorie:
            flash("Catégorie non trouvée", "error")
            return redirect(url_for('banking.gestion_categories'))
        
        date_debut = request.args.get('date_debut')
        date_fin = request.args.get('date_fin')
        
        transactions = g.models.categorie_transaction_model.get_transactions_par_categorie(
            categorie_id, current_user.id, date_debut, date_fin
        )
        
        return render_template(
            'categories/transactions_par_categorie.html',
            categorie=categorie,
            transactions=transactions,
            date_debut=date_debut,
            date_fin=date_fin
        )
        
    except Exception as e:
        logging.error(f"Erreur chargement transactions par catégorie: {e}")
        flash("Erreur lors du chargement des transactions", "error")
        return redirect(url_for('banking.gestion_categories'))
    
# API endpoints pour AJAX
@bp.route('/api/categories', methods=['GET'])
@login_required
def api_get_categories():
    """API pour récupérer les catégories (AJAX)"""
    try:
        type_categorie = request.args.get('type')
        categories = g.models.categorie_transaction_model.get_categories_utilisateur(current_user.id, type_categorie)
        return jsonify({'success': True, 'categories': categories})
    except Exception as e:
        logging.error(f"Erreur API catégories: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/api/categorie/associer', methods=['POST'])
@login_required
def api_associer_categorie():
    """API pour associer une catégorie à une transaction (AJAX)"""
    try:
        data = request.get_json()
        transaction_id = data.get('transaction_id')
        categorie_id = data.get('categorie_id')
        
        if not transaction_id or not categorie_id:
            return jsonify({'success': False, 'error': 'Données manquantes'}), 400
        
        success, message = g.models.categorie_transaction_model.associer_categorie_transaction(
            transaction_id, categorie_id, current_user.id
        )
        
        return jsonify({'success': success, 'message': message})
        
    except Exception as e:
        logging.error(f"Erreur association catégorie: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




#### ecritures comptables automatiques

@bp.route('/comptabilite/transactions-sans-ecritures')
@login_required
def transactions_sans_ecritures():
    """Affiche la liste des transactions sans écritures comptables filtrées par compte"""
    # Récupération des paramètres de filtrage
    compte_id = request.args.get('compte_id', type=int)
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    statut_comptable = request.args.get('statut_comptable', 'a_comptabiliser')
    
    # Statuts comptables disponibles
    statuts_comptables = [
        {'value': 'a_comptabiliser', 'label': 'À comptabiliser'},
        {'value': 'comptabilise', 'label': 'Comptabilisé'},
        {'value': 'ne_pas_comptabiliser', 'label': 'Ne pas comptabiliser'}
    ]
    
    # Récupérer les comptes de l'utilisateur
    comptes = g.models.compte_model.get_by_user_id(current_user.id)
    
    # Récupérer les transactions sans écritures
    transactions = []
    if compte_id:
        transactions = g.models.transaction_financiere_model.get_transactions_sans_ecritures_par_compte(
            compte_id=compte_id,
            user_id=current_user.id,
            date_from=date_from,
            date_to=date_to,
            statut_comptable=statut_comptable
        )
    
    # 🔥 NOUVEAU : Pour chaque transaction, récupérer le contact lié au compte
    transactions_avec_contacts = []
    for transaction in transactions:
        contact_lie = None
        if transaction.get('compte_principal_id'):
            contact_lie = g.models.contact_compte_model.get_contact_by_compte(
                transaction['compte_principal_id'], 
                current_user.id
            )
        # Ajouter le contact_lie à la transaction
        transaction_dict = dict(transaction)  # Convertir en dict si nécessaire
        transaction_dict['contact_lie'] = contact_lie
        transactions_avec_contacts.append(transaction_dict)
    
    total_transactions = []

    for i in comptes:
        txs = g.models.transaction_financiere_model.get_transactions_sans_ecritures_par_compte(
            compte_id=i['id'],
            user_id=current_user.id,
            date_from=i['date_ouverture'],
            date_to=date.today().strftime('%Y-%m-%d'),
            statut_comptable=statut_comptable
        )
        total_transactions.extend(txs)
    
    total_a_comptabiliser = sum(tx['montant'] for tx in total_transactions if tx['statut_comptable'] == 'a_comptabiliser')
    total_a_comptabiliser_len = len([tx for tx in total_transactions if tx['statut_comptable'] == 'a_comptabiliser'])
    
    # CORRECTION : Utilisez get_all_categories() au lieu de get_all()
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    contacts = g.models.contact_model.get_all(current_user.id)
    
    return render_template('comptabilite/transactions_sans_ecritures.html',
        transactions=transactions_avec_contacts,  # 🔥 Utiliser la nouvelle liste avec contacts
        comptes=comptes,
        compte_selectionne=compte_id,
        statuts_comptables=statuts_comptables,
        statut_comptable_selectionne=statut_comptable,
        date_from=date_from,
        date_to=date_to,
        categories=categories,
        total_a_comptabiliser=total_a_comptabiliser,
        total_a_comptabiliser_len=total_a_comptabiliser_len, 
        contacts=contacts
    )


@bp.route('/comptabilite/ecritures/nouvelle/from_selected', methods=['GET', 'POST'])
@login_required
def nouvelle_ecriture_from_selected():
    """Affiche le formulaire de création d'écritures pour transactions sélectionnées"""
    
    if request.method == 'POST':
        # 🔥 CHANGEMENT : Lire 'selected_transaction_ids' au lieu de 'selected_transactions'
        selected_transaction_ids = request.form.getlist('selected_transaction_ids')
        logging.info(f"Transactions sélectionnées pour création d'écritures: {selected_transaction_ids}")   
        if not selected_transaction_ids:
            flash("Aucune transaction sélectionnée", "warning")
            # 🔥 CHANGEMENT : Retourner vers la page des transactions filtrées
            return redirect(url_for('banking.transactions_sans_ecritures',
                                    compte_id=request.form.get('compte_id'),
                                    date_from=request.form.get('date_from'),
                                    date_to=request.form.get('date_to'),
                                    statut_comptable=request.form.get('statut_comptable')))

        # Stocker les IDs en session pour les récupérer après
        session['selected_transaction_ids'] = selected_transaction_ids
        return redirect(url_for('banking.nouvelle_ecriture_from_selected'))
    
    # Récupérer les transactions sélectionnées depuis la session
    transaction_ids = session.get('selected_transaction_ids', [])
    logging.info(f"Transactions récupérées de la session get pour création d'écritures: {transaction_ids}")
    if not transaction_ids:
        flash("Aucune transaction sélectionnée", "warning")
        # 🔥 CHANGEMENT : Retourner vers la page des transactions filtrées
        return redirect(url_for('banking.transactions_sans_ecritures'))
    
    # Récupérer les transactions
    transactions = []
    for transaction_id in transaction_ids:
        transaction = g.models.transaction_financiere_model.get_transaction_with_ecritures_total(
            int(transaction_id), current_user.id
        )
        if transaction:
            transactions.append(transaction)
    
    if not transactions:
        flash("Aucune transaction valide sélectionnée", "warning")
        # 🔥 CHANGEMENT : Retourner vers la page des transactions filtrées
        return redirect(url_for('banking.transactions_sans_ecritures'))
    
    # Récupérer les données pour les formulaires
    comptes = g.models.compte_model.get_all(current_user.id) # Vérifiez que cette fonction est correcte
    categories = g.models.categorie_model.get_all(current_user.id) # Vérifiez que cette fonction est correcte
    contacts = g.models.contact_model.get_all(current_user.id)
    
    return render_template('comptabilite/creer_ecritures_groupées.html',
                        transactions=transactions,
                        comptes=comptes,
                        categories=categories,
                        contacts=contacts,
                        today=datetime.now().strftime('%Y-%m-%d'))


@bp.route('/comptabilite/update_statut_comptable/<int:transaction_id>', methods=['POST'])
@login_required
def update_statut_comptable(transaction_id):
    """Met à jour le statut comptable d'une transaction"""
    nouveau_statut = request.form.get('statut_comptable')
    
    if nouveau_statut not in ['a_comptabiliser', 'comptabilise', 'ne_pas_comptabiliser']:
        flash('Statut invalide', 'error')
        return redirect(request.referrer or url_for('banking.transactions_sans_ecritures'))
    
    success, message = g.models.transaction_financiere_model.update_statut_comptable(
        transaction_id, current_user.id, nouveau_statut
    )
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(request.referrer or url_for('banking.transactions_sans_ecritures'))

@bp.route('/comptabilite/creer_ecriture_automatique/<int:transaction_id>', methods=['POST'])
@login_required
def creer_ecriture_automatique(transaction_id):
    """Crée une écriture comptable simple pour une transaction avec statut 'pending'"""
    try:
        # Récupérer la transaction avec vérification de propriété
        transaction = g.models.transaction_financiere_model.get_transaction_with_ecritures_total(
            transaction_id, current_user.id
        )
        
        if not transaction:
            flash("Transaction non trouvée ou non autorisée", "error")
            return redirect(url_for('banking.transactions_sans_ecritures'))
        
        categorie_id = request.form.get('categorie_id', type=int)
        
        if not categorie_id:
            flash("Veuillez sélectionner une catégorie comptable", "error")
            return redirect(url_for('banking.transactions_sans_ecritures'))
        
        # 🔥 MODIFICATION : Récupérer le contact depuis le formulaire OU le contact lié au compte
        contact_id_form = request.form.get('contact_id', type=int)
        id_contact = None
        
        # Priorité au contact sélectionné dans le formulaire
        if contact_id_form:
            id_contact = contact_id_form
        # Sinon, chercher le contact lié au compte
        elif transaction.get('compte_principal_id'):
            contact_lie = g.models.contact_compte_model.get_contact_by_compte(
                transaction['compte_principal_id'], 
                current_user.id
            )
            if contact_lie:
                id_contact = contact_lie['contact_id']
        
        # Déterminer le type d'écriture
        type_ecriture = 'depense' if transaction['type_transaction'] in ['retrait', 'transfert_sortant', 'transfert_externe'] else 'recette'
        
        # Créer l'écriture comptable
        ecriture_data = {
            'date_ecriture': transaction['date_transaction'],
            'compte_bancaire_id': transaction['compte_principal_id'],
            'categorie_id': categorie_id,
            'montant': Decimal(str(transaction['montant'])),
            'devise': 'CHF',
            'description': transaction['description'],
            'type_ecriture': type_ecriture,
            'utilisateur_id': current_user.id,
            'statut': 'pending',  # Statut en attente
            'transaction_id': transaction_id,
            'id_contact': id_contact  # 🔥 Contact du formulaire OU lié au compte
        }
        
        if g.models.ecriture_comptable_model.create(ecriture_data):
            # Marquer la transaction comme comptabilisée
            g.models.transaction_financiere_model.update_statut_comptable(
                transaction_id, current_user.id, 'comptabilise'
            )
            
            # Message de confirmation avec info contact
            message = "Écriture créée avec succès avec statut 'En attente'"
            if id_contact:
                contact_info = g.models.contact_model.get_by_id(id_contact, current_user.id)
                if contact_info:
                    message += f" - Contact: {contact_info['nom']}"
            flash(message, "success")
        else:
            flash("Erreur lors de la création de l'écriture", "error")
            
    except Exception as e:
        logging.error(f"Erreur création écriture automatique: {e}")
        flash(f"Erreur lors de la création de l'écriture: {str(e)}", "error")
    
    return redirect(url_for('banking.transactions_sans_ecritures',
                           compte_id=request.args.get('compte_id'),
                           date_from=request.args.get('date_from'),
                           date_to=request.args.get('date_to')))

@bp.app_template_filter('datetimeformat')
def datetimeformat(value, format='%d.%m.%Y'):
    """Filtre pour formater les dates dans les templates"""
    if value is None:
        return ""
    if isinstance(value, str):
        # Si c'est une chaîne, la convertir en datetime
        from datetime import datetime
        value = datetime.strptime(value, '%Y-%m-%d')
    return value.strftime(format)


@bp.app_template_filter('month_french')
def month_french_filter(value):
    """Convertit le nom du mois en français"""
    if isinstance(value, str):
        value = datetime.strptime(value, '%Y-%m')
    
    months_fr = {
        'January': 'JANVIER', 'February': 'FÉVRIER', 'March': 'MARS',
        'April': 'AVRIL', 'May': 'MAI', 'June': 'JUIN',
        'July': 'JUILLET', 'August': 'AOÛT', 'September': 'SEPTEMBRE',
        'October': 'OCTOBRE', 'November': 'NOVEMBRE', 'December': 'DÉCEMBRE'
    }
    
    month_english = value.strftime('%B')
    return months_fr.get(month_english, month_english.upper())


@bp.route('/comptabilite/ecritures/nouvelle', methods=['GET', 'POST'])
@login_required
def nouvelle_ecriture():
    if request.method == 'POST':
        try:
            # 🔥 NOUVEAU : Récupérer le contact lié au compte si pas de contact spécifié
            id_contact_form = int(request.form['id_contact']) if request.form.get('id_contact') else None
            compte_bancaire_id = int(request.form['compte_bancaire_id'])
            
            id_contact = id_contact_form
            if not id_contact_form and compte_bancaire_id:
                # Si pas de contact spécifié, chercher le contact lié au compte
                contact_lie = g.models.contact_compte_model.get_contact_by_compte(
                    compte_bancaire_id, 
                    current_user.id
                )
                if contact_lie:
                    id_contact = contact_lie['contact_id']
            
            data = {
                'date_ecriture': request.form['date_ecriture'],
                'compte_bancaire_id': compte_bancaire_id,
                'categorie_id': int(request.form['categorie_id']),
                'montant': Decimal(request.form['montant']),
                'description': request.form.get('description', ''),
                'id_contact': id_contact,  # 🔥 Utilise le contact du formulaire ou celui lié au compte
                'reference': request.form.get('reference', ''),
                'type_ecriture': request.form['type_ecriture'],
                'tva_taux': Decimal(request.form['tva_taux']) if request.form.get('tva_taux') else None,
                'utilisateur_id': current_user.id,
                'statut': request.form.get('statut', 'pending')
            }
            
            if data['tva_taux']:
                data['tva_montant'] = data['montant'] * data['tva_taux'] / 100
                
            if g.models.ecriture_comptable_model.create(data):
                flash('Écriture enregistrée avec succès', 'success')
                transaction_id = request.form.get('transaction_id')
                if transaction_id:
                    g.models.transaction_financiere_model.link_to_ecriture(transaction_id, g.models.ecriture_comptable_model.last_insert_id)
                return redirect(url_for('banking.liste_ecritures'))
            else:
                flash('Erreur lors de l\'enregistrement', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    
    elif request.method == 'GET':
        comptes = g.models.compte_model.get_all(current_user.id)
        categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
        contacts = g.models.contact_model.get_all(current_user.id)
        transactions_sans_ecritures = g.models.transaction_financiere_model.get_transactions_sans_ecritures_par_utilisateur(current_user.id)
        return render_template('comptabilite/nouvelle_ecriture.html',
            comptes=comptes,
            categories=categories,
            contacts=contacts,
            transactions_sans_ecritures=transactions_sans_ecritures,
            today=datetime.now().strftime('%Y-%m-%d'))

@bp.route('/comptabilite/ecritures/multiple/nouvelle', methods=['GET', 'POST'])
@login_required
def nouvelle_ecriture_multiple():
    if request.method == 'POST':
        dates = request.form.getlist('date_ecriture[]')
        types = request.form.getlist('type_ecriture[]')
        comptes_ids = request.form.getlist('compte_bancaire_id[]')
        categories_ids = request.form.getlist('categorie_id[]')
        montants = request.form.getlist('montant[]')
        tva_taux = request.form.getlist('tva_taux[]')
        descriptions = request.form.getlist('description[]')
        references = request.form.getlist('reference[]')
        statuts = request.form.getlist('statut[]')
        
        # 🔥 NOUVEAU : Récupérer le contact principal (pour toute la transaction)
        id_contact_principal = int(request.form['id_contact']) if request.form.get('id_contact') else None
        
        succes_count = 0
        for i in range(len(dates)):
            try:
                if not all([dates[i], types[i], comptes_ids[i], categories_ids[i], montants[i]]):
                    flash(f"Écriture {i+1}: Tous les champs obligatoires doivent être remplis", "warning")
                    continue
                
                montant = float(montants[i])
                taux_tva = float(tva_taux[i]) if tva_taux[i] and tva_taux[i] != '' else None
                statut = statuts[i] if i < len(statuts) and statuts[i] else 'pending'
                compte_id = int(comptes_ids[i])
                
                # 🔥 NOUVEAU : Déterminer le contact pour cette ligne
                id_contact_ligne = id_contact_principal
                if not id_contact_ligne and compte_id:
                    # Si pas de contact principal, chercher le contact lié au compte de cette ligne
                    contact_lie = g.models.contact_compte_model.get_contact_by_compte(
                        compte_id, 
                        current_user.id
                    )
                    if contact_lie:
                        id_contact_ligne = contact_lie['contact_id']

                data = {
                    'date_ecriture': dates[i],
                    'compte_bancaire_id': compte_id,
                    'categorie_id': int(categories_ids[i]),
                    'montant': Decimal(str(montant)),
                    'description': descriptions[i] if i < len(descriptions) else '',
                    'id_contact': id_contact_ligne,  # 🔥 Contact principal ou lié au compte
                    'reference': references[i] if i < len(references) else '',
                    'type_ecriture': types[i],
                    'tva_taux': Decimal(str(taux_tva)) if taux_tva else None,
                    'utilisateur_id': current_user.id,
                    'statut': statut
                }
                
                if data['tva_taux']:
                    data['tva_montant'] = data['montant'] * data['tva_taux'] / 100

                if g.models.ecriture_comptable_model.create(data):
                    succes_count += 1
                else:
                    flash(f"Écriture {i+1}: Erreur lors de l'enregistrement", "error")
            except ValueError as e:
                flash(f"Écriture {i+1}: Erreur de format - {str(e)}", "error")
                continue
            except Exception as e:
                flash(f"Écriture {i+1}: Erreur inattendue - {str(e)}", "error")
                continue
                
        if succes_count > 0:
            flash(f"{succes_count} écriture(s) enregistrée(s) avec succès!", "success")
        else:
            flash("Aucune écriture n'a pu être enregistrée", "warning")
        return redirect(url_for('banking.liste_ecritures'))
    
    # GET request processing (reste inchangé)
    elif request.method == 'GET':
        comptes = g.models.compte_model.get_all(current_user.id)
        categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
        contacts = g.models.contact_model.get_all(current_user.id)
        return render_template('comptabilite/nouvelle_ecriture_multiple.html',
            comptes=comptes,
            categories=categories,
            contacts=contacts,
            today=datetime.now().strftime('%Y-%m-%d'))

@bp.route('/comptabilite/creer_ecritures_multiple_auto/<int:transaction_id>', methods=['POST'])
@login_required
def creer_ecritures_multiple_auto(transaction_id):
    """Crée plusieurs écritures comptables pour une transaction avec statut 'pending'"""
    try:
        # Récupérer la transaction avec vérification de propriété
        transaction = g.models.transaction_financiere_model.get_transaction_with_ecritures_total(
            transaction_id, current_user.id
        )
        
        if not transaction:
            flash("Transaction non trouvée ou non autorisée", "error")
            return redirect(url_for('banking.transactions_sans_ecritures'))
        
        # Vérifier si la transaction a déjà des écritures
        if transaction.get('nb_ecritures', 0) > 0:
            flash("Cette transaction a déjà des écritures associées", "warning")
            return redirect(url_for('banking.transactions_sans_ecritures'))
        
        # Le reste du code reste identique...
        categories_ids = request.form.getlist('categorie_id[]')
        montants = request.form.getlist('montant[]')
        tva_taux = request.form.getlist('tva_taux[]')
        descriptions = request.form.getlist('description[]')
        
        if len(categories_ids) != len(montants):
            flash("Le nombre de catégories et de montants doit correspondre", "error")
            return redirect(url_for('banking.transactions_sans_ecritures'))
        total_montants = sum(float(m) for m in montants)
        if total_montants != Decimal(str(transaction['montant'])):
            flash("La somme des montants ne correspond pas au montant de la transaction", "error")
        success_count = 0
        for i in range(len(categories_ids)):
            try:
                if not categories_ids[i] or not montants[i]:
                    flash(f"Écriture {i+1}: Tous les champs obligatoires doivent être remplis", "warning")
                    continue
                data = {
                    'date_ecriture': transaction['date_transaction'],
                    'compte_bancaire_id': transaction['compte_principal_id'],
                    'categorie_id': int(categories_ids[i]),
                    'montant': Decimal(str(montants[i])),
                    'description': descriptions[i] if i < len(descriptions) and descriptions[i] else transaction['description'],
                    'id_contact': transaction.get('id_contact'),
                    'reference': transaction.get('reference', ''),
                    'type_ecriture': 'debit' if Decimal(str(montants[i])) < 0 else 'credit',
                    'tva_taux': Decimal(str(tva_taux[i])) if i < len(tva_taux) and tva_taux[i] else None,
                    'utilisateur_id': current_user.id,
                    'statut': 'pending'
                }
                if data['tva_taux']:
                    data['tva_montant'] = data['montant'] * data['tva_taux'] / 100
                if g.models.ecriture_comptable_model.create(data):
                    ecriture_id = g.models.ecriture_comptable_model.last_insert_id
                    g.models.transaction_financiere_model.link_to_ecriture(transaction_id, ecriture_id)
                    success_count += 1
            
            except Exception as e:
                logging.error(f"Erreur création écritures multiples: {e}")
                flash(f"Erreur lors de la création des écritures: {str(e)}", "error")
        if success_count > 0:
            flash(f"{success_count} écriture(s) créée(s) avec succès avec statut 'En attente'", "success")
        else:
            flash("Aucune écriture n'a pu être créée", "error")
    except Exception as e:
        logging.error(f"Erreur création écritures multiples: {e}")
        flash(f"Erreur lors de la création des écritures: {str(e)}", "error")
            
    return redirect(url_for('banking.transactions_sans_ecritures',
                           compte_id=request.args.get('compte_id'),
                           date_from=request.args.get('date_from'),
                           date_to=request.args.get('date_to')))


@bp.route('/comptabilite/ecritures/nouvelle/from_transactions', methods=['GET', 'POST'])
@login_required
def nouvelle_ecriture_from_transactions():
    """Crée des écritures pour TOUTES les transactions filtrées"""
    
    if request.method == 'POST':
        try:
            # Récupérer les IDs des transactions depuis les champs cachés
            transaction_ids = request.form.getlist('transaction_ids[]')
            dates = request.form.getlist('date_ecriture[]')
            types = request.form.getlist('type_ecriture[]')
            comptes_ids = request.form.getlist('compte_bancaire_id[]')
            categories_ids = request.form.getlist('categorie_id[]')
            montants = request.form.getlist('montant[]')
            tva_taux = request.form.getlist('tva_taux[]')
            descriptions = request.form.getlist('description[]')
            references = request.form.getlist('reference[]')
            statuts = request.form.getlist('statut[]')
            contacts_ids = request.form.getlist('id_contact[]')
            
            if not transaction_ids:
                flash("Aucune transaction à traiter", "warning")
                return redirect(url_for('banking.transactions_sans_ecritures'))
            logging.info(f'voici les transactions : {transaction_ids}')
            succes_count = 0
            errors = []
            
            for i in range(len(transaction_ids)):
                try:
                    if not all([dates[i], types[i], comptes_ids[i], categories_ids[i], montants[i]]):
                        errors.append(f"Transaction {i+1}: Champs obligatoires manquants")
                        continue
                    
                    data = {
                        'date_ecriture': dates[i],
                        'compte_bancaire_id': int(comptes_ids[i]),
                        'categorie_id': int(categories_ids[i]),
                        'montant': Decimal(str(montants[i])),
                        'description': descriptions[i] if i < len(descriptions) and descriptions[i] else '',
                        'id_contact': int(contacts_ids[i]) if i < len(contacts_ids) and contacts_ids[i] else None,
                        'reference': references[i] if i < len(references) and references[i] else '',
                        'type_ecriture': types[i],
                        'tva_taux': Decimal(str(tva_taux[i])) if i < len(tva_taux) and tva_taux[i] else None,
                        'utilisateur_id': current_user.id,
                        'statut': statuts[i] if i < len(statuts) and statuts[i] else 'pending'
                    }
                    
                    if data['tva_taux']:
                        data['tva_montant'] = data['montant'] * data['tva_taux'] / 100

                    if g.models.ecriture_comptable_model.create(data):
                        ecriture_id = g.models.ecriture_comptable_model.last_insert_id
                        # Lier l'écriture à la transaction
                        g.models.transaction_financiere_model.link_to_ecriture(transaction_ids[i], ecriture_id)
                        succes_count += 1
                    else:
                        errors.append(f"Transaction {i+1}: Erreur lors de l'enregistrement")
                        
                except Exception as e:
                    errors.append(f"Transaction {i+1}: {str(e)}")
                    continue
            
            # Gestion des retours
            if errors:
                for error in errors:
                    flash(error, "error")
            
            if succes_count > 0:
                flash(f"{succes_count} écriture(s) créée(s) avec succès pour {len(transaction_ids)} transaction(s)", "success")
                # 🔥 NOUVEAU : Retour à la page des transactions sans écritures
                return redirect(url_for('banking.transactions_sans_ecritures',
                                    compte_id=request.args.get('compte_id'),
                                    date_from=request.args.get('date_from'), 
                                    date_to=request.args.get('date_to')))
            else:
                flash("Aucune écriture n'a pu être créée", "error")
                # 🔥 NOUVEAU : Reste sur la même page pour correction
                return redirect(url_for('banking.nouvelle_ecriture_from_transactions',
                                    compte_id=request.args.get('compte_id'),
                                    date_from=request.args.get('date_from'),
                                    date_to=request.args.get('date_to')))
            
        except Exception as e:
            flash(f"Erreur lors de la création des écritures: {str(e)}", "error")
            return redirect(url_for('banking.transactions_sans_ecritures'))
    
    # PARTIE GET - Afficher le formulaire pour TOUTES les transactions filtrées
    compte_id = request.args.get('compte_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    # Récupérer les transactions avec les mêmes filtres
    transactions = g.models.transaction_financiere_model.get_transactions_sans_ecritures(
        current_user.id, 
        date_from=date_from,
        date_to=date_to
    )
    logging.info(f'Filtrage des transactions pour compte_id={compte_id}, date_from={date_from}, date_to={date_to}')
    logging.info(f' route nouvelle_ecriture_from_transaction Transactions récupérées avant filtrage: {transactions}')
    if compte_id and compte_id != '':
        transactions = [t for t in transactions if t.get('compte_bancaire_id') == int(compte_id)]
    
    if not transactions:
        flash("Aucune transaction à comptabiliser avec les filtres actuels", "warning")
        return redirect(url_for('banking.transactions_sans_ecritures'))
    
    # Récupérer les données pour les formulaires
    comptes = g.models.compte_model.get_all_accounts()
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    contacts = g.models.contact_model.get_all(current_user.id)
    
    return render_template('comptabilite/creer_ecritures_groupées.html',
                         transactions=transactions,
                         comptes=comptes,
                         categories=categories,
                         contacts=contacts,
                         compte_id=compte_id,
                         date_from=date_from,
                         date_to=date_to,
                         today=datetime.now().strftime('%Y-%m-%d'))


@bp.route('/comptabilite/ecritures/<int:ecriture_id>/statut', methods=['POST'])
@login_required
def modifier_statut_ecriture(ecriture_id):
    contacts = g.models.contact_model.get_all(current_user.id)
    ecriture = g.models.ecriture_comptable_model.get_by_id(ecriture_id)
    if not ecriture or ecriture['utilisateur_id'] != current_user.id:
        flash('Écriture non trouvée', 'danger')
        return redirect(url_for('banking.liste_ecritures'))
    nouveau_statut = request.form.get('statut')
    if nouveau_statut not in ['pending', 'validée', 'rejetée']:
        flash('Statut invalide', 'danger')
        return redirect(url_for('banking.liste_ecritures'))
    if g.models.ecriture_comptable_model.update_statut(ecriture_id, current_user.id, nouveau_statut):
        flash(f'Statut modifié en "{nouveau_statut}"', 'success')
    else:
        flash('Erreur lors de la modification du statut', 'danger')
    return redirect(url_for('banking.liste_ecritures'), contacts=contacts)

@bp.route('/comptabilite/ecritures/<int:ecriture_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_ecriture(ecriture_id):
    """Modifie une écriture comptable existante"""
    ecriture = g.models.ecriture_comptable_model.get_by_id(ecriture_id)
    if not ecriture or ecriture['utilisateur_id'] != current_user.id:
        flash('Écriture introuvable ou non autorisée', 'danger')
        return redirect(url_for('banking.liste_ecritures'))
    show_modal = request.args.get('show_modal') == 'liaison'
    contact = None
    comptes_lies = []
    transactions_camdidats = []
    tous_comptes = []
    if show_modal and ecriture.get('id_contact'):
        contact = g.models.contact_model.get_by_id(ecriture['id_contact'], current_user.id)
        if contact:
            comptes_lies = g.models.contact_compte_model.get_comptes_for_contact(ecriture['id_contact'], current_user.id)    
    if request.method == 'POST':
        try:
            id_contact_str = request.form.get('id_contact', '')
            id_contact = int(id_contact_str) if id_contact_str.strip() else None
            data = {
            'date_ecriture': request.form['date_ecriture'],
            'compte_bancaire_id': int(request.form['compte_bancaire_id']),
            'categorie_id': int(request.form['categorie_id']),
            'montant': Decimal(request.form['montant']),
            'description': request.form.get('description', ''),
            'id_contact': id_contact,  # Utiliser la valeur convertie
            'reference': request.form.get('reference', ''),
            'type_ecriture': request.form['type_ecriture'],
            'tva_taux': Decimal(request.form['tva_taux']) if request.form.get('tva_taux') else None,
            'utilisateur_id': current_user.id,
            'statut': request.form.get('statut', 'pending')
        } 
            if data['tva_taux']:
                data['tva_montant'] = data['montant'] * data['tva_taux'] / 100   
            if g.models.ecriture_comptable_model.update(ecriture_id, data):
                flash('Écriture mise à jour avec succès', 'success')
                return redirect(url_for('banking.liste_ecritures'))
            else:
                flash('Erreur lors de la mise à jour', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    comptes = g.models.compte_model.get_by_user_id(current_user.id)
    categories = g.models.categorie_comptable_model.get_all_categories()
    contacts = g.models.contact_model.get_all(current_user.id)
    # CORRECTION: Utiliser 'contacts' au lieu de 'Contacts'
    print(contacts)
    # Ajout des statuts disponibles pour le template
    statuts_disponibles = [
        {'value': 'pending', 'label': 'En attente'},
        {'value': 'validée', 'label': 'Validée'},
        {'value': 'rejetée', 'label': 'Rejetée'}
    ]
    return render_template('comptabilite/nouvelle_ecriture.html', 
                        comptes=comptes, 
                        categories=categories,
                        ecriture=ecriture,
                        statuts_disponibles=statuts_disponibles,
                        transaction_data={},
                        transaction_id=None,
                        # CORRECTION: Utiliser 'contacts' au lieu de 'Contacts'
                        contacts=contacts)

#@bp.route('/comptabilite/ecritures/<int:ecriture_id>/delete', methods=['POST'])
#@login_required
#def delete_ecriture(ecriture_id):
#    """Supprime une écriture comptable"""
#   ecriture = g.models.ecriture_comptable_model.get_by_id(ecriture_id)
#    if not ecriture or ecriture['utilisateur_id'] != current_user.id:
#        flash('Écriture introuvable ou non autorisée', 'danger')
#        return redirect(url_for('banking.liste_ecritures'))  
#    if g.models.ecriture_comptable_model.delete(ecriture_id):
#        flash('Écriture supprimée avec succès', 'success')
#    else:
#        flash('Erreur lors de la suppression', 'danger')    
#    return redirect(url_for('banking.liste_ecritures'))

# Route pour la suppression normale (soft delete)
@bp.route('/comptabilite/ecritures/<int:ecriture_id>/delete', methods=['POST'])
@login_required
def delete_ecriture(ecriture_id):
    """Supprime une écriture comptable (soft delete)"""
    success, message = g.models.ecriture_comptable_model.delete_soft(ecriture_id, current_user.id, soft_delete=True)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('banking.liste_ecritures'))

# Route pour la suppression définitive (hard delete)
@bp.route('/comptabilite/ecritures/<int:ecriture_id>/delete/hard', methods=['POST'])
@login_required
def hard_delete_ecriture(ecriture_id):
    """Supprime définitivement une écriture comptable"""
    success, message = g.models.ecriture_comptable_model.delete_hard(ecriture_id, current_user.id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('banking.liste_ecritures'))
# Ajouter une route pour lier une transaction à une écriture
@bp.route('/banking/link_transaction_to_ecritures', methods=['POST'])
@login_required
def link_transaction_to_ecritures():
    transaction_id = request.form.get('transaction_id', type=int)
    ecriture_id = request.form.getlist('ecriture_id')  # Liste d'IDs

    # Vérifier la transaction
    
    if not transaction or transaction['owner_user_id'] != current_user.id:
        flash("Transaction non trouvée ou non autorisée", "danger")
        return redirect(url_for('banking.banking_dashboard'))
    ecriture = g.models.ecriture_comptable_model.get_by_id(ecriture_id)
    if not ecriture or ecriture['utilisateur_id'] != current_user.id:
        flash("Écriture non autorisée", "danger")
        return redirect(url_for('banking.liste_ecritures'))
    transaction = g.models.transaction_financiere_model.get_transaction_by_id(transaction_id)
    if not transaction or transaction['owner_user_id'] != current_user.id:
        flash("Transaction non trouvée ou non autorisée", "danger")
        return redirect(url_for('banking.banking_dashboard'))
    
    total_actuel = g.models.ecriture_comptable_model.get_total_ecritures_for_transaction(transaction_id, current_user.id)
    nouveau_total = total_actuel + Decimal(str(ecriture['montant']))
    montant_transaction = Decimal(str(transaction['montant']))
    if nouveau_total > montant_transaction:
        flash(f"⚠️ Impossible : le total des écritures ({nouveau_total:.2f} CHF) dépasserait le montant de la transaction ({montant_transaction} CHF).", "warning")
        return redirect(request.referrer or url_for('banking.banking_dashboard'))
    if g.models.ecriture_comptable_model.link_ecriture_to_transaction(ecriture_id, transaction_id, current_user.id):
        flash("Écriture reliée à la transaction.", "success")
    else:
        flash("Erreur lors du lien.", "danger")
    return redirect(request.referrer or url_for('banking.banking_dashboard'))

    
@bp.route('/banking/unlink_ecriture', methods=['POST'])
@login_required
def unlink_ecriture():
    ecriture_id = request.form.get('ecriture_id', type=int)
    if g.models.ecriture_comptable_model.unlink_from_transaction(ecriture_id, current_user.id):
        flash("Lien supprimé avec succès.", "success")
    else:
        flash("Impossible de supprimer le lien.", "danger")
    return redirect(request.referrer or url_for('dashboard'))

@bp.route('/banking/relink_ecriture', methods=['POST'])
@login_required
def relink_ecriture():
    ecriture_id = request.form.get('ecriture_id', type=int)
    new_transaction_id = request.form.get('new_transaction_id', type=int)
    
    # Récupérer l'écriture et la transaction
    ecriture = g.models.ecriture_comptable_model.get_by_id(ecriture_id)
    if not ecriture or ecriture['utilisateur_id'] != current_user.id:
        flash("Écriture non autorisée", "danger")
        return redirect(request.referrer)
    
    tx = g.models.transaction_financiere_model.get_transaction_with_ecritures_total(
        new_transaction_id, current_user.id
    )
    if not tx:
        flash("Transaction introuvable", "danger")
        return redirect(request.referrer)
    
    # Calculer le nouveau total si on ajoute cette écriture
    nouveau_total = (tx['total_ecritures'] or 0) + ecriture['montant']
    if nouveau_total > tx['montant']:
        flash(f"⚠️ Impossible : le total des écritures ({nouveau_total:.2f} CHF) dépasserait le montant de la transaction ({tx['montant']} CHF).", "warning")
        return redirect(request.referrer)
    
    # Lier
    if g.models.ecriture_comptable_model.link_ecriture_to_transaction(ecriture_id, new_transaction_id, current_user.id):
        flash("Écriture reliée à la transaction.", "success")
    else:
        flash("Erreur lors du lien.", "danger")
    return redirect(request.referrer)

## Route pour la création des plans comptables

@bp.route('/plans')
@login_required
def liste_plans():
    plans = g.models.plan_comptable_model.get_all_plans(current_user.id)
    return render_template('plans/liste.html', plans=plans)

@bp.route('/plans/creer', methods=['GET', 'POST'])
@login_required
def creer_plan():
    if request.method == 'POST':
        data = request.form.to_dict()
        data['utilisateur_id'] = current_user.id
        plan_id = g.models.plan_comptable_model.create_plan(data)
        if plan_id:
            return redirect(url_for('editer_plan', plan_id=plan_id))
    return render_template('plans/creer_plan.html', action='creer')

@bp.route('/plans/<int:plan_id>/editer', methods=['GET', 'POST'])
@login_required
def editer_plan(plan_id):
    plan = g.models.plan_comptable_model.get_plan_with_categories(plan_id, current_user.id)
    if not plan:
        abort(404)

    if request.method == 'POST':
        data = request.form.to_dict()
        updated = g.models.plan_comptable_model.modifier_plan(
            plan_id=plan_id,
            data=data,
            utilisateur_id=current_user.id
        )
        if updated:
            flash("Plan comptable mis à jour avec succès.", "success")
            return redirect(url_for('plans.editer_plan', plan_id=plan_id))
        else:
            flash("Erreur lors de la mise à jour.", "danger")

    return render_template('plans/editer_plan.html', plan=plan)
@bp.route('/plans2/<int:plan_id>/editer', methods=['GET', 'POST'])
@login_required
def editer_plan2(plan_id):
    plan = g.models.plan_comptable_model.get_plan_with_categories(plan_id, current_user.id)
    if not plan:
        abort(404)
    if request.method == 'POST':
        # Mise à jour + gestion des catégories via formulaires <select>
        pass
    categories_dispo = g.models.plan_comptable_model.categorie_comptable.get_all_categories(current_user.id)
    return render_template('plans/form.html', plan=plan, categories_dispo=categories_dispo)

@bp.route('/plans/<int:plan_id>/supprimer', methods=['POST'])
@login_required
def supprimer_plan(plan_id):
    # Implémente delete_plan (soft/hard)
    return redirect(url_for('liste_plans'))


## routes pour les comptes de résultats


@bp.route('/test-compte-resultat')
@login_required
def test_compte_resultat():
    """Route de test pour debug"""
    print(f"DEBUG: Test route - User: {current_user.id}")
    stats = g.models.ecriture_comptable_model.get_compte_de_resultat(
        user_id=current_user.id,
        date_from="2025-01-01",
        date_to="2025-12-31"
    ) 
    return jsonify(stats)

@bp.route('/banking/compte/<int:compte_id>/contact/<int:contact_id>/transactions')
@login_required
def transactions_by_contact_and_compte(compte_id: int, contact_id: int):
    # Vérifier que le compte appartient à l'utilisateur
    compte = g.models.compte_principal_model.get_by_id(compte_id)
    if not compte or compte['utilisateur_id'] != current_user.id:
        abort(403)

    # Vérifier que le contact existe et appartient à l'utilisateur (si tu gères des contacts par utilisateur)
    contact = g.models.contact_model.get_by_id(contact_id)
    if not contact or contact['utilisateur_id'] != current_user.id:
        abort(404)

    transactions = g.models.transaction_financiere_model.get_transactions_by_contact_and_compte(
        contact_id=contact_id,
        compte_id=compte_id,
        user_id=current_user.id
    )

    return render_template(
        'banking/transactions_par_contact.html',
        compte=compte,
        contact=contact,
        transactions=transactions
    )

@bp.route('/comptabilite/compte-de-resultat')
@login_required
def compte_de_resultat():
    """Génère le compte de résultat avec filtres"""
    print(f"DEBUG: User {current_user.id} accède au compte de résultat")
    try:
        # Récupération des paramètres avec conversion sécurisée
        annee_str = request.args.get('annee', '')
        if annee_str and annee_str.isdigit():
            annee = int(annee_str)
        else:
            annee = datetime.now().year
        date_from = f"{annee}-01-01"
        date_to = f"{annee}-12-31"
        # Récupération des données
        stats = g.models.ecriture_comptable_model.get_compte_de_resultat(
            user_id=current_user.id,
            date_from=date_from,
            date_to=date_to
        )  
        # Debug: Afficher le nombre d'écritures trouvées
        print(f"DEBUG: {len(stats.get('produits', [])) + len(stats.get('charges', []))} éléments dans le compte de résultat")
        # Vérification des écritures pour l'année sélectionnée
        toutes_ecritures = g.models.ecriture_comptable_model.get_by_user_period(
            user_id=current_user.id,
            date_from=date_from,
            date_to=date_to
        )
        print(f"DEBUG: {len(toutes_ecritures)} écritures trouvées pour {annee}")
        # Préparation des données pour le template
        annees_disponibles = g.models.ecriture_comptable_model.get_annees_disponibles(current_user.id)
        return render_template('comptabilite/compte_de_resultat.html',
                            stats=stats,
                            annee_selectionnee=annee,
                            annees_disponibles=annees_disponibles)  
    except Exception as e:
        flash(f"Erreur lors de la génération du compte de résultat: {str(e)}", "danger")
        return redirect(url_for('banking.banking_dashboard'))

bp.route('/comptabilite/ecritures/detail/<string:type>/<categorie_id>')
@login_required
def detail_ecritures_categorie(type, categorie_id):
    """Affiche le détail des écritures d'une catégorie"""
    try:
        annee = request.args.get('annee', datetime.now().year)
        date_from = f"{annee}-01-01"
        date_to = f"{annee}-12-31"
        
        # Utiliser la méthode de la classe EcritureComptable
        ecritures, total, titre = g.models.ecriture_comptable_model.get_ecritures_by_categorie_period(
            user_id=current_user.id,
            type_categorie=type,
            categorie_id=categorie_id,
            date_from=date_from,
            date_to=date_to,
            statut='validée'
        )
        
        logging.info(f"INFO: {len(ecritures)} écritures récupérées pour le détail")
        
        return render_template('comptabilite/detail_ecritures.html',
                            ecritures=ecritures,
                            total=total,
                            titre=titre,
                            annee=annee,
                            type=type)
    
    except Exception as e:
        logging.error(f"Erreur lors du chargement des détails: {e}")
        flash(f"Erreur lors du chargement des détails: {str(e)}", "danger")
        return redirect(url_for('banking.compte_de_resultat'))

@bp.route('/comptabilite/ecritures/compte-resultat')
@login_required
def get_ecritures_compte_resultat():
    """Retourne les écritures pour le compte de résultat (AJAX)"""
    try:
        annee = request.args.get('annee', datetime.now().year)
        type_ecriture = request.args.get('type', '')  # 'produit' ou 'charge'
        categorie_id = request.args.get('categorie_id', '')
        
        date_from = f"{annee}-01-01"
        date_to = f"{annee}-12-31"
        # Construire la requête en fonction des paramètres
        query = """
            SELECT 
                e.date_ecriture,
                e.description,
                e.id_contact,
                e.reference,
                e.montant,
                e.statut,
                c.nom as categorie_nom,
                c.numero as categorie_numero
            FROM ecritures_comptables e
            JOIN categories_comptables c ON e.categorie_id = c.id
            JOIN contacts ct ON e.id_contact = ct.id
            WHERE e.utilisateur_id = %s
            AND e.date_ecriture BETWEEN %s AND %s
            AND e.statut = 'validée'
        """
        
        params = [current_user.id, date_from, date_to]
        
        if type_ecriture == 'produit':
            query += " AND c.type_compte = 'Revenus'"
        elif type_ecriture == 'charge':
            query += " AND c.type_compte = 'Charge'"
        
        if categorie_id and categorie_id != 'all':
            query += " AND e.categorie_id = %s"
            params.append(int(categorie_id))
        query += " ORDER BY e.date_ecriture DESC"
        ecritures = g.models.ecriture_comptable_model.db.execute_query(query, params)
        return jsonify({
            'ecritures': ecritures,
            'count': len(ecritures),
            'total': sum(float(e['montant']) for e in ecritures)
        })
    except Exception as e:
        print(f"Erreur récupération écritures compte de résultat: {e}")
        return jsonify({'ecritures': [], 'count': 0, 'total': 0})

@bp.route('/comptabilite/compte-de-resultat/export')
@login_required
def export_compte_de_resultat():
    """Exporte le compte de résultat"""
    format_export = request.args.get('format', 'pdf')
    annee = request.args.get('annee', datetime.now().year)
    
    # Récupération des données
    #ecriture_model = EcritureComptable(g.db_manager)
    stats = g.models.ecriture_comptable_model.get_compte_de_resultat(
        user_id=current_user.id,
        date_from=f"{annee}-01-01",
        date_to=f"{annee}-12-31"
    )
    if format_export == 'excel':
        # Génération Excel
        output = generate_excel(stats, annee)
        response = make_response(output)
        response.headers["Content-Disposition"] = f"attachment; filename=compte_de_resultat_{annee}.xlsx"
        response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return response
    else:
        # Génération PDF
        pdf = generate_pdf(stats, annee)
        response = make_response(pdf)
        response.headers["Content-Disposition"] = f"attachment; filename=compte_de_resultat_{annee}.pdf"
        response.headers["Content-type"] = "application/pdf"
        return response

@bp.route('/')
def journal_comptable():
    # Récupérer les années disponibles
    annees = g.models.ecriture_comptable_model.get_annees_disponibles(user_id=1)  # À adapter avec le vrai user_id
    # Récupérer les catégories comptables
    categories = g.models.categorie_comptable_model.get_all_categories()
    # Paramètres par défaut
    annee_courante = datetime.now().year
    date_from = f"{annee_courante}-01-01"
    date_to = f"{annee_courante}-12-31"
    # Récupérer les écritures
    ecritures = g.models.ecriture_comptable_model.get_by_compte_bancaire(
        compte_id=None,  # Tous les comptes
        user_id=1,      # À adapter
        date_from=date_from,
        date_to=date_to,
        limit=100
    )
    # Préparer les données pour le template
    context = {
        'annees': annees,
        'annee_courante': annee_courante,
        'categories': categories,
        'ecritures': ecritures,
        'date_from': date_from,
        'date_to': date_to
    }
    return render_template('comptabilite/journal_comptable.html', **context)

@bp.route('/api/ecritures')
@login_required
def api_ecritures():
    # Récupérer les paramètres de filtrage
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    categorie_id = request.args.get('categorie_id')
    type_ecriture = request.args.get('type_ecriture')
    
    # Récupérer les écritures filtrées
    if categorie_id:
        ecritures = g.models.ecriture_comptable_model.get_by_categorie(
            categorie_id=int(categorie_id),
            user_id=1,  # À adapter
            date_from=date_from,
            date_to=date_to  # Fixed: changed from date_from=date_to to date_to=date_to
        )
    else:
        ecritures = g.models.ecriture_comptable_model.get_by_compte_bancaire(
            compte_id=None,  # Tous les comptes
            user_id=1,      # À adapter
            date_from=date_from,
            date_to=date_to,
            limit=1000
        )
    # Filtrer par type si nécessaire
    if type_ecriture:
        ecritures = [e for e in ecritures if e['type_ecriture'] == type_ecriture]
    return jsonify(ecritures)

@bp.route('/api/compte_resultat')
@login_required
def api_compte_resultat():
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    resultat = g.models.ecriture_comptable_model.get_compte_de_resultat(
        user_id=1,  # À adapter
        date_from=date_from,
        date_to=date_to
    )
    return jsonify(resultat)


### Partie heures et salaires 

# --- Routes heures et salaires ---

@bp.route('/heures-travail', methods=['GET', 'POST'])
@login_required
def heures_travail():
    current_user_id = current_user.id
    #employeur = contrat['employeur'] if contrat else 'Non spécifié'
    now = datetime.now()
    # Récupérer mois, semaine, mode selon méthode HTTP
    if request.method == 'POST':
        annee = int(request.form.get('annee', now.year))
        mois = int(request.form.get('mois', now.month))
        semaine = int(request.form.get('semaine', 0))
        current_mode = request.form.get('mode', 'reel')
        selected_employeur = request.form.get('employeur')
    else:
        annee = int(request.args.get('annee', now.year))
        mois = int(request.args.get('mois', now.month))
        semaine = int(request.args.get('semaine', 0))
        current_mode = request.args.get('mode', 'reel')
        selected_employeur = request.args.get('employeur')
    logging.debug(f"DEBUG 2950 : Requête de tous les contrats pour user_id={current_user.id}")
    try:
        tous_contrats = g.models.contrat_model.get_all_contrats(current_user_id)
        logging.error(f"DEBUG 2953: Tous les contrats pour l'utilisateur {current_user_id}: {tous_contrats}")
    except Exception as e:
        logging.exception(f"🚨 ERREUR dans get_all_contrats pour user_id={current_user_id}: {e}")
        tous_contrats = []
    logging.debug(f"DEBUG2 2957: Contrats récupérés: {tous_contrats}")
    logging.debug(f"DEBUG 2958: Mois={mois}, Semaine={semaine}, Mode={current_mode}, Employeur sélectionné={selected_employeur} avec tous_contrats={len(tous_contrats)}")
    logging.error(f"DEBUG 2959: Tous les contrats pour l'utilisateur {current_user_id}: {tous_contrats}")
    employeurs_unique = sorted({c['employeur'] for c in tous_contrats if c.get('employeur')})
    logging.debug(f"DEBUG 2956 : Employeurs uniques trouvés: {employeurs_unique}")
    if not selected_employeur:
        if employeurs_unique:
            contrat_actuel = g.models.contrat_model.get_contrat_actuel(current_user_id)
            if contrat_actuel:
                selected_employeur = contrat_actuel['employeur']
            else:
                selected_employeur = None
                for emp in employeurs_unique:
                    contrats_pour_emp = [c for c in tous_contrats if c['employeur'] == emp]
                    if not contrats_pour_emp:
                        continue
                    contrat_candidat = None
                    for c in contrats_pour_emp:
                        if c['date_fin'] is None or c['date_fin'] >= date.today():
                            contrat_candidat = c
                            break
                    if not contrat_candidat:
                        contrat_candidat = max(contrats_pour_emp, key=lambda x: x['date_fin'] or date(1900, 1, 1))

                    if g.models.heure_model.has_hours_for_employeur_and_contrat(current_user_id, emp, contrat_candidat['id']):
                        selected_employeur = emp
                        break
                if not selected_employeur:
                        selected_employeur = employeurs_unique[0]
        else:
            selected_employeur = None

    contrat = None
    id_contrat = None
    logging.debug(f"banking 2973 DEBUG: Recherche du contrat pour l'employeur sélectionné: {selected_employeur}")
    if selected_employeur:
        for c in tous_contrats:
            if c['employeur'] == selected_employeur and (c['date_fin'] is None or c['date_fin'] >= date.today()):
                contrat = c
                break
        if contrat is None:
            candidats = [c for c in tous_contrats if c['employeur'] == selected_employeur]
            if candidats:
                contrat = max(candidats, key=lambda x: x['date_fin'])
       
    id_contrat = contrat['id'] if contrat else None
    heures_hebdo_contrat = contrat['heures_hebdo'] if contrat else 38.0
    # Actions POST
    if request.method == 'POST':
        annee = int(request.form.get('annee', now.year))
        if 'save_line' in request.form:
            return handle_save_line(request, current_user_id, annee, mois, semaine, current_mode, selected_employeur, id_contrat)
        elif 'reset_line' in request.form:
            return handle_reset_line(request, current_user_id, annee,  mois, semaine, current_mode, selected_employeur, id_contrat)
        elif 'reset_all' in request.form:
            return handle_reset_all(request, current_user_id, annee, mois, semaine, current_mode, selected_employeur, id_contrat)
        elif request.form.get('action') == 'simuler':
            return handle_simulation(request, current_user_id, annee, mois, semaine, current_mode, selected_employeur, id_contrat)
        # Dans heures_travail() → section POST
        elif request.form.get('action') == 'copier_jour':
            return handle_copier_jour(request, current_user_id, current_mode, selected_employeur, id_contrat)
        elif request.form.get('action') == 'copier_semaine':
            return handle_copier_semaine(request, current_user_id, current_mode, selected_employeur, id_contrat)        
        else:
            return handle_save_all(request, current_user_id, annee, mois, semaine, current_mode, selected_employeur, id_contrat)

    # Traitement GET : affichage des heures
    semaines = {}
    for day_date in generate_days(annee, mois, semaine):
        date_str = day_date.isoformat()
        jour_data_default = {
            'date': date_str,
            'h1d': '',
            'h1f': '',
            'h2d': '',
            'h2f': '',
            'vacances': False,
            'total_h': 0.0
        }
        if contrat:
            jour_data = g.models.heure_model.get_by_date(date_str, current_user_id, selected_employeur, contrat['id']) or jour_data_default 
        else:
            jour_data = jour_data_default
        logging.debug(f"banking 3012 DEBUG: Données pour le {date_str}: {jour_data}")
        # CORRECTION : Toujours recalculer total_h pour assurer la cohérence
        if not jour_data['vacances'] and any([jour_data['h1d'], jour_data['h1f'], jour_data['h2d'], jour_data['h2f']]):
            calculated_total = g.models.heure_model.calculer_heures(
                jour_data['h1d'] or '', jour_data['h1f'] or '',
                jour_data['h2d'] or '', jour_data['h2f'] or ''
            )
            # Mise à jour si différence significative (tolérance de 0.01h = 36 secondes)
            if abs(jour_data['total_h'] - calculated_total) > 0.01:
                jour_data['total_h'] = calculated_total
        elif jour_data['vacances']:
            jour_data['total_h'] = 0.0
        # Nom du jour en français
        jours_semaine_fr = {
            'Monday': 'Lundi', 'Tuesday': 'Mardi', 'Wednesday': 'Mercredi',
            'Thursday': 'Jeudi', 'Friday': 'Vendredi', 'Saturday': 'Samedi', 'Sunday': 'Dimanche'
        }
        jour_data['nom_jour'] = jours_semaine_fr.get(day_date.strftime('%A'), day_date.strftime('%A'))

        # Regroupement par semaine
        semaine_annee = day_date.isocalendar()[1]
        if semaine_annee not in semaines:
            semaines[semaine_annee] = {'jours': [], 'total': 0.0, 'solde': 0.0}
        semaines[semaine_annee]['jours'].append(jour_data)
        semaines[semaine_annee]['total'] += jour_data['total_h']

    # Calcul des soldes
    for semaine_data in semaines.values():
        semaine_data['solde'] = semaine_data['total'] - heures_hebdo_contrat
    
    total_general = sum(s['total'] for s in semaines.values())
    logging.debug(f"banking 3043 DEBUG: Total général des heures: {total_general}")
    semaines = dict(sorted(semaines.items()))
    logging.debug(f"banking 3045 DEBUG: Semaines préparées pour le rendu: {semaines.keys()}")

    return render_template('salaires/heures_travail.html',
                        semaines=semaines,
                        total_general=total_general,
                        heures_hebdo_contrat=heures_hebdo_contrat,
                        current_mois=mois,
                        current_semaine=semaine,
                        current_annee=annee,
                        current_mode=current_mode,
                        now = datetime.now(),
                        tous_contrats=tous_contrats,
                        employeurs_unique=employeurs_unique,
                        selected_employeur=selected_employeur)

def has_hours_for_employeur_and_contrat(self, user_id, employeur, id_contrat):
    """Vérifie si l'utilisateur a des heures enregistrées pour un employeur donné"""
    try:
        with self.db.get_cursor() as cursor:
            query = "SELECT 1 FROM heures_travail WHERE user_id = %s AND employeur = %s AND id_contrat = %s LIMIT 1"
            cursor.execute(query, (user_id, employeur, id_contrat))
            result = cursor.fetchone()
            return result is not None
    except Exception as e:
        current_app.logger.error(f"Erreur has_hours_for_employeur_and_contrat: {e}")
        return False

def is_valid_time(time_str):
    """Validation renforcée du format d'heure"""
    if not time_str or time_str.strip() == '':
        return True  # Champ vide est acceptable 
    time_str = time_str.strip()
    try:
        # Vérifier le format HH:MM
        time_obj = datetime.strptime(time_str, '%H:%M')
        # Vérifier que les heures et minutes sont dans des plages valides
        if 0 <= time_obj.hour <= 23 and 0 <= time_obj.minute <= 59:
            return True
        return False
    except ValueError:
        return False

def get_vacances_value(request, date_str):
    """Fonction utilitaire pour récupérer la valeur des vacances de manière cohérente"""
    return request.form.get(f'vacances_{date_str}') == 'on'

def validate_day_data(request, date_str):
    errors = []
    
    h1d = request.form.get(f'h1d_{date_str}', '').strip()
    h1f = request.form.get(f'h1f_{date_str}', '').strip()
    h2d = request.form.get(f'h2d_{date_str}', '').strip()
    h2f = request.form.get(f'h2f_{date_str}', '').strip()
    
    # Validation format des heures
    for field_name, time_str in [('h1d', h1d), ('h1f', h1f), ('h2d', h2d), ('h2f', h2f)]:
        if not is_valid_time(time_str):
            errors.append(f"Format d'heure invalide pour {field_name}: '{time_str}'")
    
    # MODIFICATION : Permettre les demi-journées et heures simples
    # Ne pas bloquer si seulement une période est remplie
    if not errors:
        # Vérifier la cohérence par période
        if (h1d and not h1f) or (not h1d and h1f):
            errors.append("Heure de début et fin de matin incohérentes")
        if (h2d and not h2f) or (not h2d and h2f):
            errors.append("Heure de début et fin d'après-midi incohérentes")
            
        # Vérifier l'ordre chronologique si les deux périodes sont présentes
        if h1d and h1f and h2d and h2f:
            try:
                t1d = datetime.strptime(h1d, '%H:%M').time()
                t1f = datetime.strptime(h1f, '%H:%M').time()
                t2d = datetime.strptime(h2d, '%H:%M').time()
                t2f = datetime.strptime(h2f, '%H:%M').time()
                
                if not (t1d <= t1f and t1f <= t2d and t2d <= t2f):
                    errors.append("L'ordre chronologique des heures n'est pas respecté")
            except ValueError:
                pass
    
    return errors

def create_day_payload(request, user_id, date_str, employeur, id_contrat):
    """Crée le payload pour une journée en gérant correctement les valeurs vides"""
    # Récupération des valeurs du formulaire avec conversion des chaînes vides en None
    def get_time_field(field_name):
        value = request.form.get(f'{field_name}_{date_str}', '').strip()
        return value if value else None
    
    h1d = get_time_field('h1d')
    h1f = get_time_field('h1f')
    h2d = get_time_field('h2d')
    h2f = get_time_field('h2f')
    vacances = get_vacances_value(request, date_str)
    
    # Conversion des valeurs temporelles vides en None
    time_fields = [h1d, h1f, h2d, h2f]
    for i, value in enumerate(time_fields):
        if value == '':
            time_fields[i] = None
    
    # Calcul du total uniquement si nécessaire
    total_h = 0.0
    if not vacances and any(time_fields):
        # Utilisation de la méthode statique pour éviter l'instanciation inutile
        total_h = HeureTravail.calculer_heures_static(
            h1d or '', 
            h1f or '',
            h2d or '',
            h2f or ''
        )
    
    return {
        'date': date_str,
        'user_id': user_id,
        'employeur': employeur,
        'id_contrat': id_contrat,
        'h1d': h1d,
        'h1f': h1f,
        'h2d': h2d,
        'h2f': h2f,
        'vacances': vacances,
        'total_h': total_h,
        # Les champs suivants seront recalculés par create_or_update
        # On ne les inclut pas pour éviter les incohérences
    }

def save_day_transaction(cursor, payload):
    try:
        # Utiliser directement la classe HeureTravail pour la sauvegarde

        # Transmettre le curseur à la méthode create_or_update
        success = g.models.heure_model.create_or_update(payload, cursor)
        
        if success:
            logger.debug(f"Sauvegarde réussie pour {payload['date']}")
            return True, None
        else:
            error_msg = f"Échec de la sauvegarde pour {payload['date']}"
            logger.error(error_msg)
            return False, error_msg
            
    except Exception as e:
        error_msg = f"Erreur sauvegarde jour {payload.get('date', 'INCONNUE')}: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback complet:\n{traceback.format_exc()}")
        return False, error_msg

def process_day(request, user_id, date_str, annee, mois, semaine, mode, employeur, id_contrat, flash_message=True):
    errors = validate_day_data(request, date_str)
    if errors:
        for error in errors:
            flash(f"Erreur {format_date(date_str)}: {error}", "error")
        return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))
    
    payload = create_day_payload(request, user_id, date_str, employeur, id_contrat)
    
    # Utiliser la méthode sécurisée de HeureTravail
    success = g.models.heure_model.create_or_update(payload)
    
    if success:
        if flash_message:
            flash(f"Heures du {format_date(date_str)} enregistrées", "success")
    else:
        flash(f"Échec de la sauvegarde pour {format_date(date_str)}", "error")
    
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))

def format_date(date_str):
    return datetime.fromisoformat(date_str).strftime('%d/%m/%Y')

def format_date(date_str):
    return date.fromisoformat(date_str).strftime('%d/%m/%Y')

def generate_days(annee: int, mois: int, semaine: int) -> list[date]:
    if semaine > 0:
        try:
            start_date = datetime.fromisocalendar(annee, semaine, 1).date()
            return [start_date + timedelta(days=i) for i in range(7)]
        except ValueError:
            start_date = date(annee, 1, 1)
            return [start_date + timedelta(days=i) for i in range(7)]
    elif mois > 0:
        _, num_days = monthrange(annee, mois)
        return [date(annee, mois, day) for day in range(1, num_days + 1)]
    else:
        now = datetime.now()
        _, num_days = monthrange(now.year, now.month)
        return [date(now.year, now.month, day) for day in range(1, num_days + 1)]
def handle_save_line(request, user_id, annee, mois, semaine, mode, employeur, id_contrat):
    date_str = request.form['save_line']
    return process_day(request, user_id, date_str, annee, mois, semaine, mode, employeur, id_contrat)

def handle_reset_line(request, user_id, annee, mois, semaine, mode, employeur, id_contrat):
    date_str = request.form['reset_line']
    try:
        # Utiliser l'instance globale déjà configurée
        success = g.models.heure_model.delete_by_date(date_str, user_id, employeur, id_contrat)
        if success:
            flash(f"Les heures du {format_date(date_str)} ont été réinitialisées", "warning")
        else:
            flash(f"Impossible de réinitialiser les heures du {format_date(date_str)}", "error")
            logger.warning(f"Échec silencieux de delete_by_date pour {date_str}")
    except Exception as e:
        logger.exception(f"Erreur dans handle_reset_line pour {date_str}: {e}")  # ← .exception pour le traceback complet
        flash(f"Erreur lors de la réinitialisation du {format_date(date_str)}", "error")
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))

def handle_reset_all(request, user_id, annee, mois, semaine, mode, employeur, id_contrat):
    days = generate_days(annee, mois, semaine)
    errors = []
    for day in days:
        try:
            g.models.heure_model.delete_by_date(day.isoformat(), user_id, employeur, id_contrat)
        except Exception as e:
            logger.error(f"Erreur reset jour {day}: {str(e)}")
            errors.append(format_date(day.isoformat()))
    if errors:
        flash(f"Erreur lors de la réinitialisation des jours: {', '.join(errors)}", "error")
    else:
        flash("Toutes les heures ont été réinitialisées", "warning")
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))

def handle_simulation(request, user_id, annee,mois, semaine, mode, employeur, id_contrat):
    days = generate_days(annee, mois, semaine)
    errors = []
    success_count = 0
    for day in days:
        date_str = day.isoformat()
        vacances = get_vacances_value(request, date_str)
        if not vacances:
            try:
                total_h = g.models.heure_model.calculer_heures('08:00', '12:00', '13:00', '17:00')
                payload = {
                    'date': date_str,
                    'h1d': '08:00',
                    'h1f': '12:00',
                    'h2d': '13:00',
                    'h2f': '17:00',
                    'vacances': False,
                    'total_h': total_h,
                    'user_id': user_id,
                    'employeur': employeur,
                    'id_contrat': id_contrat,
                    'jour_semaine': day.strftime('%A'),
                    'semaine_annee': day.isocalendar()[1],
                    'mois': day.month
                }
                g.models.heure_model.create_or_update(payload)
                success_count += 1
            except Exception as e:
                logger.error(f"Erreur simulation jour {date_str}: {str(e)}")
                errors.append(format_date(date_str))
    if errors:
        flash(f"Erreur simulation pour les jours: {', '.join(errors)}", "error")
    if success_count > 0:
        flash(f"Heures simulées appliquées pour {success_count} jour(s)", "info")
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))

def handle_save_all(request, user_id, annee, mois, semaine, mode, employeur, id_contrat):
    days = generate_days(annee, mois, semaine)
    has_errors = False
    
    for day in days:
        date_str = day.isoformat()
        payload = create_day_payload(request, user_id, date_str, employeur, id_contrat)
        
        if not g.models.heure_model.create_or_update(payload):
            has_errors = True
            logger.error(f"Erreur traitement jour {date_str}")
    
    if not has_errors:
        flash("Toutes les heures ont été enregistrées avec succès", "success")
    
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))



def handle_copier_jour(request, user_id, mode, employeur, id_contrat):
    source = request.form.get('source_date')
    target = request.form.get('target_date')
    
    if not source:
        flash("Veuillez indiquer une date source.", "error")
        return redirect(request.url)
    if not target:
        flash("Veuillez indiquer une date cible.", "error")
        return redirect(request.url)

    try:
        target_date = date.fromisoformat(target)
        source_date = date.fromisoformat(source)  # optionnel, mais bon pour cohérence
    except ValueError:
        flash("Format de date invalide. Utilisez le sélecteur de date.", "error")
        return redirect(request.url)

    src_data = g.models.heure_model.get_by_date(source, user_id, employeur, id_contrat)
    if not src_data:
        flash(f"Aucune donnée à copier pour le {format_date(source)}.", "warning")
        return redirect(request.url)

    payload = {
        'date': target,
        'user_id': user_id,
        'employeur': employeur,
        'id_contrat': id_contrat,
        'h1d': src_data.get('h1d'),
        'h1f': src_data.get('h1f'),
        'h2d': src_data.get('h2d'),
        'h2f': src_data.get('h2f'),
        'vacances': src_data.get('vacances', False),
        'total_h': src_data.get('total_h', 0.0)
    }

    if g.models.heure_model.create_or_update(payload):
        flash(f"Heures copiées du {format_date(source)} au {format_date(target)}.", "success")
    else:
        flash(f"Échec de la copie vers le {format_date(target)}.", "error")

    return redirect(url_for(
        'banking.heures_travail',
        annee=target_date.year,
        mois=target_date.month,
        semaine=0,
        mode=mode,
        employeur=employeur
    ))

def handle_copier_semaine(request, user_id, mode, employeur, id_contrat):
    src_start = request.form.get('source_week_start')
    tgt_start = request.form.get('target_week_start')
    
    if not src_start or not tgt_start:
        flash("Veuillez indiquer les lundis des semaines source et cible.", "error")
        return redirect(request.url)

    try:
        tgt_monday = date.fromisoformat(tgt_start)
        if tgt_monday.weekday() != 0:
            flash("La date cible doit être un lundi.", "error")
            return redirect(request.url)
    except ValueError:
        flash("Date cible invalide. Utilisez AAAA-MM-JJ.", "error")
        return redirect(request.url)

    copied = 0
    for i in range(7):
        src_day = (date.fromisoformat(src_start) + timedelta(days=i)).isoformat()
        tgt_day = (tgt_monday + timedelta(days=i)).isoformat()

        src_data = g.models.heure_model.get_by_date(src_day, user_id, employeur, id_contrat)
        if not src_data:
            continue

        payload = {
            'date': tgt_day,
            'user_id': user_id,
            'employeur': employeur,
            'id_contrat': id_contrat,
            'h1d': src_data.get('h1d'),
            'h1f': src_data.get('h1f'),
            'h2d': src_data.get('h2d'),
            'h2f': src_data.get('h2f'),
            'vacances': src_data.get('vacances', False),
            'total_h': src_data.get('total_h', 0.0)
        }

        if g.models.heure_model.create_or_update(payload):
            copied += 1

    flash(f"{copied} jour(s) copié(s) vers la semaine du {tgt_monday.strftime('%d/%m/%Y')}.", "success")

    return redirect(url_for(
        'banking.heures_travail',
        annee=tgt_monday.year,
        mois=0,
        semaine=tgt_monday.isocalendar()[1],
        mode=mode,
        employeur=employeur
    ))
# --- Routes salaires ---

@bp.route('/salaires', methods=['GET'])
@login_required
def salaires():
    current_user_id = current_user.id
    now = datetime.now()
    annee = request.args.get('annee', now.year, type=int)
    mois = request.args.get('mois', now.month, type=int)
    selected_employeur = request.args.get('employeur', '')

    logger.info(f"Affichage des salaires pour utilisateur {current_user_id}, année={annee}")
    tous_contrats = g.models.contrat_model.get_all_contrats(current_user_id)
    logging.info(f"banking 3320 {len(tous_contrats)} Contrats récupérés: {tous_contrats} ")
    employeurs_unique = sorted({c['employeur'] for c in tous_contrats})
    
    # Structure : salaires_par_mois[mois] = { 'employeurs': { 'Nom Employeur': données_salaire, ... }, 'totaux_mois': {...} }
    salaires_par_mois = {}
    
    # Initialiser tous les mois de l'année
    for m in range(1, 13):
        salaires_par_mois[m] = {
            'employeurs': {},
            'totaux_mois': {
                'heures_reelles': 0.0,
                'salaire_calcule': 0.0,
                'salaire_net': 0.0,
                'salaire_verse': 0.0,
                'acompte_25': 0.0,
                'acompte_10': 0.0,
                'acompte_25_estime': 0.0,
                'acompte_10_estime': 0.0,
                'difference': 0.0,
            }
        }

    # Sélection automatique de l'employeur si non spécifié
    if not selected_employeur and employeurs_unique:
        contrat_actuel = g.models.contrat_model.get_contrat_actuel(current_user_id)
        if contrat_actuel:
            selected_employeur = contrat_actuel['employeur']
        else:
            selected_employeur = employeurs_unique[0]

    # Pour chaque mois de l'année
    for m in range(1, 13):
        date_mois_str = f"{annee}-{m:02d}-01"
        date_mois = date.fromisoformat(date_mois_str)

        # Traiter chaque employeur sélectionné ou tous les employeurs
        employeurs_a_traiter = [selected_employeur] if selected_employeur else employeurs_unique
        
        for employeur in employeurs_a_traiter:
            # Trouver le contrat actif pour cet employeur ce mois-ci
            contrat = None
            for c in tous_contrats:
                if c['employeur'] == employeur and c['date_debut'] <= date_mois and (c['date_fin'] is None or c['date_fin'] >= date_mois):
                    contrat = c
                    break
            
            if contrat:
                id_contrat = contrat['id']
                salaire_horaire = float(contrat.get('salaire_horaire', 24.05))
                jour_estimation = int(contrat.get('jour_estimation_salaire', 15))

                # Récupérer les heures réelles pour cet employeur ce mois-ci
                heures_reelles = g.models.heure_model.get_total_heures_mois(current_user_id, employeur, id_contrat, annee, m) or 0.0
                heures_reelles = round(heures_reelles, 2)

                # Vérifier si un salaire existe déjà en base POUR CET EMPLOYEUR ET CE CONTRAT
                salaires_existants = g.models.salaire_model.get_by_mois_annee(current_user_id, annee, m, employeur, id_contrat)
                salaire_existant = salaires_existants[0] if salaires_existants else None

                # Valeurs par défaut
                #salaire_calcule = 0.0
                #salaire_net = 0.0
                salaire_verse = 0.0
                acompte_10 = 0.0
                acompte_25 = 0.0
                #acompte_25_estime = 0.0
                #acompte_10_estime = 0.0

                if salaire_existant :
                    # Utiliser les valeurs stockées en base
                    salaire_verse = salaire_existant.get('salaire_verse', 0.0)
                    acompte_25 = salaire_existant.get('acompte_25', 0.0)
                    acompte_10 = salaire_existant.get('acompte_10', 0.0)

                # Nouveau mois : calculer à la volée
                acompte_25_estime = 0.0
                acompte_10_estime = 0.0
                if heures_reelles > 0:
                    try:

                        # Recalcul des acomptes estimés
                        if contrat.get('versement_25'):
                            acompte_25_estime = g.models.salaire_model.calculer_acompte_25(
                                current_user_id, annee, m, salaire_horaire, employeur, id_contrat, jour_estimation)
                        if contrat.get('versement_10'):
                            acompte_10_estime = g.models.salaire_model.calculer_acompte_10(
                                current_user_id, annee, m, salaire_horaire, employeur, id_contrat, jour_estimation)
                        acompte_25_estime = round(float(acompte_25_estime), 2)
                        acompte_10_estime = round(float(acompte_10_estime), 2)
                    except Exception as e:
                        logger.error(f"Erreur calcul acomptes estimés mois {m}: {e}")
                    try:
                        result = g.models.salaire_model.calculer_salaire_net_avec_details(
                            heures_reelles, contrat, current_user_id, annee, m, jour_estimation)
                        logger.info(f"Structure de result pour mois {m}: {result}")
                        details = result
                        salaire_net = result.get('salaire_net', 0.0)
                        salaire_calcule = result.get('details', {}).get('salaire_brut', 0.0)
                        versements = result.get('details', {}).get('versements', {})
                        acompte_25_estime = versements.get('acompte_25', {}).get('montant', 0.0)
                        acompte_10_estime = versements.get('acompte_10', {}).get('montant', 0.0)
                    except Exception as e:
                        logger.error(f"Erreur calcul salaire mois {m}, employeur {employeur}: {e}")
                        details = {'erreur': f'Erreur calcul: {str(e)}'}
                        salaire_net = 0.0
                        salaire_calcule = 0.0
                        acompte_10_estime = 0.0
                        acompte_25_estime = 0.0
                else:
                    details = {
                        'erreur': 'Aucune heure saisie pour ce mois',
                        'heures_reelles': 0.0,
                        'taux_horaire': salaire_horaire,
                        'salaire_brut': 0.0,
                        'versements': {
                            'acompte_25': {'montant': 0.0},
                            'acompte_10': {'montant': 0.0}
                        }
                    }
                    salaire_net = 0.0
                    salaire_calcule = 0.0
                    acompte_25_estime = 0.0
                    acompte_10_estime = 0.0

                # Préparer les données à sauvegarder / afficher
                salaire_data = {
                    'mois': m,
                    'annee': annee,
                    'user_id': current_user_id,
                    'employeur': employeur,
                    'id_contrat': id_contrat,
                    'heures_reelles': heures_reelles,
                    'salaire_horaire': salaire_horaire,
                    'salaire_calcule': salaire_calcule,
                    'salaire_net': salaire_net,
                    'salaire_verse': salaire_verse,
                    'acompte_25': acompte_25,
                    'acompte_10': acompte_10,
                    'acompte_25_estime': acompte_25_estime,
                    'acompte_10_estime': acompte_10_estime,
                    'difference': 0.0,
                    'difference_pourcent': 0.0,
                    'details' : details}

                # Calculer la différence si salaire versé existe
                if salaire_data['salaire_verse'] is not None and salaire_data['salaire_calcule']:
                    diff, diff_pct = g.models.salaire_model.calculer_differences(
                        salaire_data['salaire_calcule'],
                        salaire_data['salaire_verse']
                    )
                    salaire_data['difference'] = diff
                    salaire_data['difference_pourcent'] = diff_pct

                # Créer en base si c'est un nouveau mois et qu'il y a des heures
                if not salaire_existant and heures_reelles > 0:
                    success = g.models.salaire_model.create(salaire_data)
                    if success:
                        # Récupérer l'ID après création
                        salaires_apres = g.models.salaire_model.get_by_mois_annee(current_user_id, annee, m, employeur, id_contrat)
                        if salaires_apres:
                            salaire_data['id'] = salaires_apres[0]['id']

                # Stocker dans la structure d'affichage
                salaires_par_mois[m]['employeurs'][employeur] = salaire_data

                # Ajouter aux totaux du mois (seulement pour l'employeur sélectionné ou tous)
                if not selected_employeur or employeur == selected_employeur:
                    totaux = salaires_par_mois[m]['totaux_mois']
                    totaux['heures_reelles'] += heures_reelles
                    totaux['salaire_calcule'] += salaire_calcule
                    totaux['salaire_net'] += salaire_net
                    totaux['salaire_verse'] += salaire_data['salaire_verse']
                    totaux['acompte_25'] += salaire_data['acompte_25']
                    totaux['acompte_10'] += salaire_data['acompte_10']
                    totaux['acompte_25_estime'] += acompte_25_estime
                    totaux['acompte_10_estime'] += acompte_10_estime
                    totaux['difference'] += salaire_data['difference']

    # Calcul des totaux annuels
    totaux_annuels = {
        'total_heures_reelles': 0.0,
        'total_salaire_calcule': 0.0,
        'total_salaire_net': 0.0,
        'total_salaire_verse': 0.0,
        'total_acompte_25': 0.0,
        'total_acompte_10': 0.0,
        'total_acompte_25_estime': 0.0,
        'total_acompte_10_estime': 0.0,
        'total_difference': 0.0,
    }

    for m in range(1, 13):
        mois_totaux = salaires_par_mois[m]['totaux_mois']
        for key in totaux_annuels:
            base_key = key.replace('total_', '')
            totaux_annuels[key] += mois_totaux.get(base_key, 0.0)

    for key in totaux_annuels:
        totaux_annuels[key] = round(totaux_annuels[key], 2)

    # =============== PRÉPARATION DES DONNÉES POUR LES GRAPHIQUES SVG ===============

    largeur_svg = 800
    hauteur_svg = 400
    margin_x = largeur_svg * 0.1
    margin_y = hauteur_svg * 0.1
    plot_width = largeur_svg * 0.8
    plot_height = hauteur_svg * 0.8

    # === GRAPHIQUE 1 ===
    salaire_estime_vals = []
    salaire_verse_vals = []
    acompte_10_vals = []
    acompte_25_vals = []
    mois_labels = []

    for m in range(1, 13):
        mois_data = salaires_par_mois[m]['employeurs'].get(selected_employeur, {})
        if mois_data:
            salaire_estime_vals.append(float(mois_data.get('salaire_calcule', 0)))
            salaire_verse_vals.append(float(mois_data.get('salaire_verse', 0)))
            acompte_10_vals.append(float(mois_data.get('acompte_10', 0)))
            acompte_25_vals.append(float(mois_data.get('acompte_25', 0)))
        else:
            salaire_estime_vals.append(0.0)
            salaire_verse_vals.append(0.0)
            acompte_10_vals.append(0.0)
            acompte_25_vals.append(0.0)
        mois_labels.append(f"{m:02d}/{annee}")

    all_vals = salaire_estime_vals + salaire_verse_vals + acompte_10_vals + acompte_25_vals
    min_val = min(all_vals) if all_vals else 0.0
    max_val = max(all_vals) if all_vals else 100.0
    if min_val == max_val:
        max_val = min_val + 100.0 if min_val == 0 else min_val * 1.1

    # === CALCUL DES TICKS POUR L'AXE Y (GRAPHIQUE 1) ===
    # On arrondit min_val vers le bas au multiple de 200 le plus proche
    # et max_val vers le haut au multiple de 1000 le plus proche (ou 200 si petit)
        # === CALCUL DES TICKS POUR L'AXE Y (GRAPHIQUE 1) ===
    import math

    tick_step_minor = 200
    tick_step_major = 1000

    # Étendre légèrement les bornes pour inclure des multiples de 200
    y_axis_min = math.floor(min_val / tick_step_minor) * tick_step_minor
    y_axis_max = math.ceil(max_val / tick_step_minor) * tick_step_minor

    # S'assurer qu'on a au moins 2 ticks
    if y_axis_max <= y_axis_min:
        y_axis_max = y_axis_min + tick_step_major

    # Option : plafonner y_axis_max à un multiple de 1000 si max_val est petit
    # (évite d'aller à 1000 si max_val = 300)
    if max_val < tick_step_major:
        y_axis_max = tick_step_major

    ticks = []
    y_val = y_axis_min
    while y_val <= y_axis_max:
        # Ne garder que les ticks dans une plage "raisonnable"
        if y_val >= y_axis_min and y_val <= y_axis_max:
            is_major = (y_val % tick_step_major == 0)
            # Conversion en coordonnée SVG
            y_px = margin_y + plot_height - ((y_val - min_val) / (max_val - min_val)) * plot_height
            ticks.append({
                'value': int(y_val),
                'y_px': y_px,
                'is_major': is_major
            })
        y_val += tick_step_minor

    def y_coord(val):
        return margin_y + plot_height - ((val - min_val) / (max_val - min_val)) * plot_height

    colonnes_svg = []
    bar_width = plot_width / 12 * 0.6
    for i in range(12):
        x = margin_x + (i + 0.5) * (plot_width / 12) - bar_width / 2
        y_top = y_coord(salaire_estime_vals[i])
        height = plot_height - (y_top - margin_y)
        colonnes_svg.append({'x': x, 'y': y_top, 'width': bar_width, 'height': height})

    points_verse = [f"{margin_x + (i + 0.5) * (plot_width / 12)},{y_coord(salaire_verse_vals[i])}" for i in range(12)]
    points_acompte_10 = [f"{margin_x + (i + 0.5) * (plot_width / 12)},{y_coord(acompte_10_vals[i])}" for i in range(12)]
    points_acompte_25 = [f"{margin_x + (i + 0.5) * (plot_width / 12)},{y_coord(acompte_25_vals[i])}" for i in range(12)]

    graphique1_svg = {
        'colonnes': colonnes_svg,
        'ligne_verse': points_verse,
        'points_acompte_10': points_acompte_10,
        'points_acompte_25': points_acompte_25,
        'min_val': min_val,
        'max_val': max_val,
        'mois_labels': mois_labels,
        'largeur_svg': largeur_svg,
        'hauteur_svg': hauteur_svg,
        'margin_x': margin_x,
        'margin_y': margin_y,
        'plot_width': plot_width,
        'plot_height': plot_height,
        'ticks': ticks
    }

    # === GRAPHIQUE 2 ===
    total_verse_vals = [float(salaires_par_mois[m]['totaux_mois']['salaire_verse']) for m in range(1, 13)]
    total_estime_vals = [float(salaires_par_mois[m]['totaux_mois']['salaire_calcule']) for m in range(1, 13)]

    all_vals2 = total_verse_vals + total_estime_vals
    min_val2 = min(all_vals2) if all_vals2 else 0.0
    max_val2 = max(all_vals2) if all_vals2 else 100.0
    if min_val2 == max_val2:
        max_val2 = min_val2 + 100.0 if min_val2 == 0 else min_val2 * 1.1

    def y_coord2(val):
        return margin_y + plot_height - ((val - min_val2) / (max_val2 - min_val2)) * plot_height

    colonnes2_svg = []
    for i in range(12):
        x = margin_x + (i + 0.5) * (plot_width / 12) - bar_width / 2
        y_top = y_coord2(total_verse_vals[i])
        height = plot_height - (y_top - margin_y)
        colonnes2_svg.append({'x': x, 'y': y_top, 'width': bar_width, 'height': height})

    points_estime2 = [f"{margin_x + (i + 0.5) * (plot_width / 12)},{y_coord2(total_estime_vals[i])}" for i in range(12)]

    graphique2_svg = {
        'colonnes': colonnes2_svg,
        'ligne_estime': points_estime2,
        'min_val': min_val2,
        'max_val': max_val2,
        'mois_labels': mois_labels,
        'largeur_svg': largeur_svg,
        'hauteur_svg': hauteur_svg,
        'margin_x': margin_x,
        'margin_y': margin_y,
        'plot_width': plot_width,
        'plot_height': plot_height
    }

    return render_template(
        'salaires/calcul_salaires.html',
        salaires_par_mois=salaires_par_mois,
        totaux=totaux_annuels,
        annee_courante=annee,
        tous_contrats=tous_contrats,
        employeurs_unique=employeurs_unique,
        selected_employeur=selected_employeur,
        contrat_actuel=contrat,
        margin_x=margin_x,
        margin_y=margin_y,
        plot_width=plot_width,
        plot_height=plot_height,
        graphique1_svg=graphique1_svg,
        graphique2_svg=graphique2_svg,
        largeur_svg=largeur_svg,
        hauteur_svg=hauteur_svg
    )

@bp.route('/api/details_calcul_salaire')
@login_required
def details_calcul_salaire():
    try:
        # Récupération des paramètres
        mois = request.args.get('mois', type=int)
        annee = request.args.get('annee', type=int)
        employeur = request.args.get('employeur')
        if mois is None or annee is None or not employeur:
            return jsonify({'erreur': 'Mois, année et employeur requis'}), 400
        # Récupération du contrat actuel

        current_user_id = current_user.id
        date_str = f'{annee}-{mois:02d}-01'
        contrat = g.models.contrat_model.get_contrat_for_date(current_user_id, employeur, date_str)
    
        if not contrat:
            return jsonify({'erreur': 'Aucun contrat trouvé pour cette période'}), 404
        
        # Récupération des heures réelles
        heures_reelles = g.models.heure_model.get_total_heures_mois(current_user_id, employeur, contrat['id'], annee, mois) or 0.0
        
        # Calcul avec détails
        resultats = g.models.salaire_model.calculer_salaire_net_avec_details(heures_reelles, 
                                                                            contrat, user_id=current_user_id, annee=annee, mois=mois)
        
        # Ajout du mois et de l'année aux résultats
        resultats['mois'] = mois
        resultats['annee'] = annee
        return jsonify(resultats)
    except Exception as e:
        return jsonify({'erreur': f'Erreur serveur: {str(e)}'}), 500

@bp.route('/update_salaire', methods=['POST'])
@login_required
def update_salaire():
    mois_str = request.form.get('mois')
    annee_str = request.form.get('annee')
    employeur = request.form.get('employeur')
    current_user_id = current_user.id
    annee_now = datetime.now().year

    # Validation et conversion sécurisée
    try:
        mois = int(mois_str) if mois_str and mois_str.strip() else None
        annee = int(annee_str) if annee_str and annee_str.strip() else None
        salaire_verse = float(request.form.get('salaire_verse') or 0.0)
        acompte_25 = float(request.form.get('acompte_25') or 0.0)
        acompte_10 = float(request.form.get('acompte_10') or 0.0)

        if mois is None or annee is None:
            flash("Mois et année sont requis", "error")
            return redirect(url_for('banking.salaires', annee=annee_now))
    except (ValueError, TypeError):
        flash("Format de données invalide", "error")
        return redirect(url_for('banking.salaires', annee=annee_now))

    # Récupération du contrat actif pour ce mois/employeur
    date_ref = f"{annee}-{mois:02d}-01"
    contrat = g.models.contrat_model.get_contrat_for_date(current_user_id, employeur, date_ref)
    if not contrat:
        flash("Aucun contrat trouvé pour cet employeur et cette période", "error")
        return redirect(url_for('banking.salaires', annee=annee))

    id_contrat = contrat['id']
    salaire_horaire = float(contrat.get('salaire_horaire', 24.05))
    jour_estimation = int(contrat.get('jour_estimation_salaire', 15))

    # Heures réelles
    heures_reelles = g.models.heure_model.get_total_heures_mois(
        current_user_id, employeur, id_contrat, annee, mois
    ) or 0.0

    # Recherche d'une entrée existante
    existing = g.models.salaire_model.get_by_mois_annee(
        current_user_id, annee, mois, employeur, id_contrat
    )
    salaire_existant = next((s for s in existing if s.get('employeur') == employeur), None)

    # Calcul du salaire théorique
    salaire_calcule = g.models.salaire_model.calculer_salaire(heures_reelles, salaire_horaire)

    # Différence
    difference, difference_pourcent = g.models.salaire_model.calculer_differences(
        salaire_calcule, salaire_verse
    )

    # === Étape 1 : Sauvegarder les valeurs saisies (création ou mise à jour) ===
    if salaire_existant:
        salaire_id = salaire_existant['id']
        # ⚠️ Correction : 'salaire_verse' (sans accent)
        g.models.salaire_model.update(salaire_id, {
            'salaire_verse': salaire_verse,
            'acompte_25': acompte_25,
            'acompte_10': acompte_10,
            'heures_reelles': heures_reelles,  # au cas où les heures ont changé
            'salaire_horaire': salaire_horaire,
            'salaire_calcule': salaire_calcule,
            'difference': difference,
            'difference_pourcent': difference_pourcent,
        })
        success = True
    else:
        full_data = {
            'mois': mois,
            'annee': annee,
            'user_id': current_user_id,
            'employeur': employeur,
            'id_contrat': id_contrat,
            'heures_reelles': heures_reelles,
            'salaire_horaire': salaire_horaire,
            'salaire_calcule': salaire_calcule,
            'salaire_verse': salaire_verse,
            'acompte_25': acompte_25,
            'acompte_10': acompte_10,
            'acompte_25_estime': 0.0,  # temporaire
            'acompte_10_estime': 0.0,  # temporaire
            'difference': difference,
            'difference_pourcent': difference_pourcent,
        }
        success = g.models.salaire_model.create(full_data)
        # Récupérer l'ID après création
        existing = g.models.salaire_model.get_by_mois_annee(current_user_id, annee, mois, employeur, id_contrat)
        salaire_existant = next((s for s in existing if s.get('employeur') == employeur), None)
        salaire_id = salaire_existant['id'] if salaire_existant else None

    # === Étape 2 : Recalculer les champs ESTIMÉS et NET, puis mettre à jour ===
    if success and salaire_id:
        # Recalculer les acomptes estimés avec la logique précise
        acompte_25_estime = 0.0
        acompte_10_estime = 0.0
        if contrat.get('versement_25'):
            acompte_25_estime = g.models.salaire_model.calculer_acompte_25(
                current_user_id, annee, mois, salaire_horaire, employeur, id_contrat, jour_estimation
            )
        if contrat.get('versement_10'):
            acompte_10_estime = g.models.salaire_model.calculer_acompte_10(
                current_user_id, annee, mois, salaire_horaire, employeur, id_contrat, jour_estimation
            )

        # Recalculer le salaire net proprement
        salaire_net = g.models.salaire_model.calculer_salaire_net(heures_reelles, contrat)

        # Mettre à jour les champs calculés (sans toucher aux saisies manuelles)
        g.models.salaire_model.update(salaire_id, {
            'acompte_25_estime': round(acompte_25_estime, 2),
            'acompte_10_estime': round(acompte_10_estime, 2),
            'salaire_net': round(salaire_net, 2),
        })

    if success:
        flash("Les valeurs ont été mises à jour avec succès", "success")
    else:
        flash("Erreur lors de la mise à jour des données", "error")

    return redirect(url_for('banking.salaires', annee=annee))

@bp.route('/recalculer_salaires', methods=['POST'])
@login_required
def recalculer_salaires():
    annee = request.form.get('annee', type=int)
    employeur = request.form.get('employeur', '').strip()
    current_user_id = current_user.id
    logging.info(f'demande de recalcul des salaires pour {current_user_id} et {employeur}')
    if not annee or not employeur:
        flash("Année et employeur requis pour le recalcul", "error")
        return redirect(url_for('banking.salaires', annee=annee or datetime.now().year))

    # Récupérer un contrat valide pour cet employeur
    date_ref = f"{annee}-06-01"
    contrat = g.models.contrat_model.get_contrat_for_date(current_user_id, employeur, date_ref)
    if not contrat:
        # Essayer de trouver n'importe quel contrat pour cet employeur
        tous_contrats = g.models.contrat_model.get_all_contrats(current_user_id)
        contrat = next((c for c in tous_contrats if c['employeur'] == employeur), None)
    
    if not contrat:
        flash(f"Aucun contrat trouvé pour l'employeur '{employeur}' en {annee}", "error")
        return redirect(url_for('banking.salaires', annee=annee))

    id_contrat = contrat['id']

    # Récupérer tous les salaires de cette année pour cet employeur/contrat
    salaires = g.models.salaire_model.get_by_user_and_month(
        user_id=current_user_id,
        employeur=employeur,
        id_contrat=id_contrat,
        annee=annee
    )

    count = 0
    for sal in salaires:
        if g.models.salaire_model.recalculer_salaire(sal['id'], contrat):
            count += 1
            logging.info(f'salaire corrigé : {salaires} - {sal}')

    flash(f"✅ {count} salaires ont été recalculés avec succès pour {employeur} en {annee}.", "success")
    return redirect(url_for('banking.salaires', annee=annee, employeur=employeur))

@bp.route('/synthese-hebdo', methods=['GET'])
@login_required
def synthese_hebdomadaire():
    user_id = current_user.id
    annee = int(request.args.get('annee', datetime.now().year))
    semaine = request.args.get('semaine')
    
    # Déterminer la semaine courante si non fournie
    if semaine is None or not semaine.isdigit():
        semaine = datetime.now().isocalendar()[1]
    else:
        semaine = int(semaine)

    # Données de la semaine sélectionnée
    synthese_list = g.models.synthese_hebdo_model.get_by_user_and_week(
        user_id=user_id, annee=annee, semaine=semaine
    )
    
    # Calcul des totaux pour la semaine
    total_heures = sum(float(s.get('heures_reelles', 0)) for s in synthese_list)
    total_simule = sum(float(s.get('heures_simulees', 0)) for s in synthese_list)

    # Préparer le graphique SVG pour l'année entière
    graphique_svg = g.models.synthese_hebdo_model.prepare_svg_data_hebdo(user_id, annee)

    return render_template('salaires/synthese_hebdo.html',
                        syntheses=synthese_list,
                        total_heures=round(total_heures, 2),
                        total_simule=round(total_simule, 2),
                        current_annee=annee,
                        current_semaine=semaine,
                        graphique_svg=graphique_svg,  # <-- ajouté
                        now=datetime.now())

@bp.route('/synthese-hebdo/generer', methods=['POST'])
@login_required
def generer_syntheses_hebdomadaires():
    user_id = current_user.id
    annee = int(request.form.get('annee', datetime.now().year))
    
    # Générer les 53 semaines → uniquement si aucune synthèse n'existe pour cette semaine
    for semaine in range(1, 54):
        # Vérifier si des synthèses existent déjà pour cette semaine (au moins une ligne)
        synthese_list = g.models.synthese_hebdo_model.get_by_user_and_week(
            user_id=user_id, annee=annee, semaine=semaine
        )
        if not synthese_list:
            # Calculer et enregistrer les synthèses par contrat
            data_list = g.models.synthese_hebdo_model.calculate_for_week_by_contrat(user_id, annee, semaine)
            for data in data_list:
                g.models.synthese_hebdo_model.create_or_update_batch([data])
    
    flash(f"Synthèses hebdomadaires générées pour l'année {annee}.", "success")
    return redirect(url_for('banking.synthese_heures', annee=annee))
@bp.route('/synthese-heures')
@login_required
def synthese_heures():
    user_id = current_user.id
    annee = int(request.args.get('annee', datetime.now().year))
    
    # Récupérer TOUTES les synthèses de l'année (pour le tableau)
    semaines = g.models.synthese_hebdo_model.get_by_user_and_year(user_id, annee)
    
    # Générer le graphique SVG global
    graphique_svg = g.models.synthese_hebdo_model.prepare_svg_data_hebdo(user_id, annee)
    
    # Liste des employeurs pour les filtres (optionnel)
    try:
        with g.models.synthese_hebdo_model.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT employeur 
                FROM synthese_hebdo 
                WHERE user_id = %s AND employeur IS NOT NULL
                ORDER BY employeur
            """, (user_id,))
            employeurs = [row['employeur'] for row in cursor.fetchall()]
    except Exception as e:
        logging.error(f"Erreur employeurs: {e}")
        employeurs = []

    return render_template('salaires/synthese_heures.html',
                        semaines=semaines,
                        graphique_svg=graphique_svg,
                        annee=annee,
                        employeurs=employeurs,
                        now=datetime.now())
@bp.route('/synthese-mensuelle/generer', methods=['POST'])
@login_required
def generer_syntheses_mensuelles():
    user_id = current_user.id
    annee = int(request.form.get('annee', datetime.now().year))
    
    # Supprimer les anciennes synthèses de l'année pour éviter les doublons
    g.models.synthese_mensuelle_model.delete_by_user_and_year(user_id, annee)
    
    # Générer les 12 mois → une synthèse PAR CONTRAT
    for mois in range(1, 13):
        data_list = g.models.synthese_mensuelle_model.calculate_for_month_by_contrat(user_id, annee, mois)
        for data in data_list:
            g.models.synthese_mensuelle_model.create_or_update(data)
    
    flash(f"Synthèses mensuelles générées par contrat pour l'année {annee} (en CHF).", "success")
    return redirect(url_for('banking.synthese_mensuelle', annee=annee))

@bp.route('/synthese-mensuelle', methods=['GET'])
@login_required
def synthese_mensuelle():
    user_id = current_user.id
    annee = int(request.args.get('annee', datetime.now().year))
    mois = request.args.get('mois')
    employeur = request.args.get('employeur')
    contrat_id = request.args.get('contrat')
    
    mois = int(mois) if mois and mois.isdigit() else None
    contrat_id = int(contrat_id) if contrat_id and contrat_id.isdigit() else None

    synthese_list = g.models.synthese_mensuelle_model.get_by_user_and_filters(
        user_id=user_id,
        annee=annee,
        mois=mois,
        employeur=employeur,
        contrat_id=contrat_id
    )

    # ✅ Préparer le graphique SVG (toujours pour l'année entière)
    graphique_svg = g.models.synthese_mensuelle_model.prepare_svg_data_mensuel(user_id, annee)

    employeurs = g.models.synthese_mensuelle_model.get_employeurs_distincts(user_id)
    contrats = g.models.contrat_model.get_all_contrats(user_id)

    return render_template('salaires/synthese_mensuelle.html',
                        syntheses=synthese_list,
                        graphique_svg=graphique_svg,  # ← ajouté
                        current_annee=annee,
                        current_mois=mois,
                        selected_employeur=employeur,
                        selected_contrat=contrat_id,
                        employeurs_disponibles=employeurs,
                        contrats_disponibles=contrats,
                        now=datetime.now())

@bp.route('/contrat', methods=['GET', 'POST'])
@login_required
def gestion_contrat():
    current_user_id = current_user.id
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save':
            try:
                data = {
                    'id': request.form.get('contrat_id') or None,
                    'user_id': current_user_id,
                    'employeur': request.form.get('employeur'),
                    'heures_hebdo': float(request.form.get('heures_hebdo')),
                    'salaire_horaire': float(request.form.get('salaire_horaire')),
                    'date_debut': request.form.get('date_debut'),
                    'date_fin': request.form.get('date_fin') or None,
                    'jour_estimation_salaire': int(request.form.get('jour_estimation_salaire')),
                    'versement_10': 'versement_10' in request.form,
                    'versement_25': 'versement_25' in request.form,
                    'indemnite_vacances_tx': float(request.form.get('indemnite_vacances_tx') or 0),
                    'indemnite_jours_feries_tx': float(request.form.get('indemnite_jours_feries_tx') or 0),
                    'indemnite_jour_conges_tx': float(request.form.get('indemnite_jour_conges_tx') or 0),
                    'indemnite_repas_tx': float(request.form.get('indemnite_repas_tx') or 0),
                    'indemnite_retenues_tx': float(request.form.get('indemnite_retenues_tx') or 0),
                    'cotisation_avs_tx': float(request.form.get('cotisation_avs_tx') or 0),
                    'cotisation_ac_tx': float(request.form.get('cotisation_ac_tx') or 0),
                    'cotisation_accident_n_prof_tx': float(request.form.get('cotisation_accident_n_prof_tx') or 0),
                    'cotisation_assurance_indemnite_maladie_tx': float(request.form.get('cotisation_assurance_indemnite_maladie_tx') or 0),
                    'cotisation_cap_tx': float(request.form.get('cotisation_cap_tx') or 0),
                }
                print(f'Voici les données du contrat à sauvegarder: {data}')
            except ValueError:
                flash("Certaines valeurs numériques sont invalides.", "danger")
                return redirect(url_for('banking.gestion_contrat'))
            
            g.models.contrat_model.create_or_update(data)
            flash('Contrat enregistré avec succès!', 'success')
        
        elif action == 'delete':
            contrat_id = request.form.get('contrat_id')
            if contrat_id:
                g.models.contrat_model.delete(contrat_id)
                flash('Contrat supprimé avec succès!', 'success')
            else:
                flash("Aucun contrat sélectionné pour suppression.", "warning")
        
        return redirect(url_for('banking.gestion_contrat'))
    
    # En GET, on récupère les contrats
    contrat_actuel = g.models.contrat_model.get_contrat_actuel(current_user_id)
    contrats = g.models.contrat_model.get_all_contrats(current_user_id)
    for contrat in contrats:
        contrat['data_id'] = contrat['id']
    return render_template('salaires/contrat.html', 
                        contrat_actuel=contrat_actuel,
                        contrats=contrats,
                        today=date.today())
    
@bp.route('/nouveau_contrat', methods=['GET', 'POST'])
@login_required
def nouveau_contrat():
    current_user_id = current_user.id
    contrat = {}
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'save_new':
            try:
                data = {
                    'id': request.form.get('contrat_id') or None,
                    'user_id': current_user_id,
                    'employeur': request.form.get('employeur'),
                    'heures_hebdo': float(request.form.get('heures_hebdo')),
                    'salaire_horaire': float(request.form.get('salaire_horaire')),
                    'date_debut': request.form.get('date_debut'),
                    'date_fin': request.form.get('date_fin') or None,
                    'jour_estimation_salaire': int(request.form.get('jour_estimation_salaire')),
                    'versement_10': 'versement_10' in request.form,
                    'versement_25': 'versement_25' in request.form,
                    'indemnite_vacances_tx': float(request.form.get('indemnite_vacances_tx') or 0),
                    'indemnite_jours_feries_tx': float(request.form.get('indemnite_jours_feries_tx') or 0),
                    'indemnite_jour_conges_tx': float(request.form.get('indemnite_jour_conges_tx') or 0),
                    'indemnite_repas_tx': float(request.form.get('indemnite_repas_tx') or 0),
                    'indemnite_retenues_tx': float(request.form.get('indemnite_retenues_tx') or 0),
                    'cotisation_avs_tx': float(request.form.get('cotisation_avs_tx') or 0),
                    'cotisation_ac_tx': float(request.form.get('cotisation_ac_tx') or 0),
                    'cotisation_accident_n_prof_tx': float(request.form.get('cotisation_accident_n_prof_tx') or 0),
                    'cotisation_assurance_indemnite_maladie_tx': float(request.form.get('cotisation_assurance_indemnite_maladie_tx') or 0),
                    'cotisation_cap_tx': float(request.form.get('cotisation_cap_tx') or 0),
                }
                logging.debug(f'banking 3807 Voici les données du contrat à sauvegarder: {data}')
            except ValueError:
                flash("Certaines valeurs numériques sont invalides.", "danger")
                return redirect(url_for('banking.nouveau_contrat'))

            nouveau_contrat = g.models.contrat_model.create_or_update(data)
            if nouveau_contrat:
                flash('Nouveau contrat enregistré avec succès!', 'success')
            else:
                flash("Erreur lors de la création du contrat.", "danger")
            return redirect(url_for('banking.gestion_contrat'))

    return render_template('salaires/nouveau_contrat.html', today=date.today(), contrat=contrat)
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, current_app, g
from flask_login import login_required, current_user
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, date
from calendar import monthrange
from app.models import DatabaseManager, Banque, ComptePrincipal, SousCompte, TransactionFinanciere, StatistiquesBancaires, PlanComptable, EcritureComptable, HeureTravail, Salaire, SyntheseHebdomadaire, SyntheseMensuelle, Contrat, Contacts
from io import StringIO
import csv
import io
import traceback
import random
from collections import defaultdict

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
        comptes = g.models.compte_model.get_by_user_id(user_id)
        for compte in comptes:
            compte['sous_comptes'] = g.models.sous_compte_model.get_by_compte_principal_id(compte['id'])
            compte['solde_total'] = g.models.compte_model.get_solde_total_avec_sous_comptes(compte['id'])
        return comptes

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
                'solde_initial': Decimal(request.form.get('solde_initial,0')),
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
                ).date() if request.form.get('date_objectif') else None
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
    logger.debug(f'Comptes récupérés: {comptes}')
        
    # Ajout des stats comptables
    now = datetime.now()
    first_day = now.replace(day=1)
    last_day = (first_day.replace(month=first_day.month % 12 + 1, year=first_day.year + first_day.month // 12) - timedelta(days=1))
    
    stats_comptables = g.models.ecriture_comptable_model.get_stats_by_categorie(
        user_id=user_id,
        date_from=first_day.strftime('%Y-%m-%d'),
        date_to=last_day.strftime('%Y-%m-%d')
    )
    
    recettes_mois = sum(s['total_recettes'] or 0 for s in stats_comptables)
    depenses_mois = sum(s['total_depenses'] or 0 for s in stats_comptables)
    
    return render_template('banking/dashboard.html', 
                        comptes=comptes, 
                        stats=stats, 
                        repartition=repartition,
                        recettes_mois=recettes_mois,
                        depenses_mois=depenses_mois)


@bp.route('/banking/compte/<int:compte_id>')
@login_required
def banking_compte_detail(compte_id):
    user_id = current_user.id
    compte = g.models.compte_model.get_by_id(compte_id)
    if not compte or compte['utilisateur_id'] != user_id:
        flash('Compte non trouvé ou non autorisé', 'error')
        return redirect(url_for('banking.banking_dashboard'))
    #Paramètre de filtrage et tri
    sort = request.args.get('sort', 'date_desc')  # Valeurs possibles: date_asc, date_desc, montant_asc, montant_desc
    filter_type = request.args.get('filter_type', 'tous')  # Valeurs possibles: tous, entree, sortie, transfert 
    filter_min_amount = request.args.get('filter_min_amount')
    filter_max_amount = request.args.get('filter_max_amount')
    search_query = request.args.get('search', '').strip()

    # Gestion de la période sélectionnée
    periode = request.args.get('periode', 'mois')  # Valeurs possibles: mois, trimestre, annee
    
    date_debut_str = request.args.get('date_debut')
    date_fin_str = request.args.get('date_fin')
    mois_seletct = request.args.get('mois_select')
    annee_select = request.args.get('annee_select')
    # Calcul des dates selon la période
    maintenant = datetime.now()
    debut = None
    fin = None
    libelle_periode = "période personnalisée "
    
    if periode == 'personnalisee' and date_debut_str and date_fin_str:
        try:
            debut = datetime.strptime(date_debut_str, '%Y-%m-%d')
            fin = datetime.strptime(date_fin_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
        except ValueError:
            flash('Dates personnalisées invalides', 'error')
            return redirect(url_for('banking.banking_compte_detail', compte_id=compte_id))
    elif periode == 'mois_annee' and mois_seletct and annee_select:
        try:
            mois = int(mois_seletct)
            annee = int(annee_select)
            debut = datetime(annee, mois, 1)
            fin = (debut + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            fin = fin.replace(hour=23, minute=59, second=59)
            libelle_periode =f'{debut.strftime('%B %Y')}'
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
        debut = maintenant.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        fin_mois = (debut.replace(month=debut.month+1, day=1) - timedelta(days=1))
        fin = fin_mois.replace(hour=23, minute=59, second=59)
        libelle_periode = "Ce mois"
    
    # Récupération des mouvements avec la nouvelle classe unifiée
    mouvements = g.models.transaction_financiere_model.get_historique_compte(
        compte_type='compte_principal',
        compte_id=compte_id,
        user_id=user_id,
        date_from=debut.strftime('%Y-%m-%d'),
        date_to=fin.strftime('%Y-%m-%d'),
        limit=200  # Augmenter la limite pour la période
    )
    
    # Utiliser les statistiques corrigées plutôt que le calcul manuel
    stats_compte = g.models.transaction_financiere_model.get_statistiques_compte(
        compte_type='compte_principal',
        compte_id=compte_id,
        user_id=user_id,
        periode_jours=(fin - debut).days
    )
    filtred_mouvements = mouvements
    if filter_type!='tous':
        filtred_mouvements
    if filter_min_amount:
        try:
            min_amount = Decimal(filter_min_amount)
            filtred_mouvements = [m for m in filtred_mouvements if m['montant'] >= min_amount]
        except InvalidOperation:
            flash('Montant minimum invalide', 'error')
    if filter_max_amount:
        search_lower = search_query.lower()
        filtred_mouvements = [
            m for m in filtred_mouvements if (m.get('description','') and search_lower in m['description'].lower()) or
            (m.get('categorie','') and search_lower in m['categorie'].lower())
        ]
        try:
            max_amount = Decimal(filter_max_amount)
            filtred_mouvements = [m for m in filtred_mouvements if m['montant'] <= max_amount]
        except InvalidOperation:
            flash('Montant maximum invalide', 'error')
    if search_query:
        filtred_mouvements = [m for m in filtred_mouvements if search_query.lower() in (m.get('description','') or '').lower() or search_query.lower() in (m.get('categorie','') or '').lower()]

    total_recettes = Decimal(str(stats_compte.get('total_entrees', 0)))
    total_depenses = Decimal(str(stats_compte.get('total_sorties', 0)))

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
    soldes_quotidiens = g.models.transaction_financiere_model.get_evolution_soldes_quotidiens_compte(
        compte_id=compte_id, 
        user_id=user_id, 
        nb_jours=nb_jours_periode
        )

    # Préparation des données pour le graphique SVG
    if soldes_quotidiens:
        # Convertir toutes les valeurs Decimal en float pour les calculs
        soldes_values = [float(s['solde_apres']) for s in soldes_quotidiens]
        min_solde = min(soldes_values) if soldes_values else 0.0
        max_solde = max(soldes_values) if soldes_values else 0.0
        
        # Ajuster l'échelle pour éviter les problèmes de division par zéro
        if min_solde == max_solde:
            if min_solde == 0:
                max_solde = 100.0  # Valeur par défaut si tous les soldes sont à zéro
            else:
                min_solde = min_solde * 0.9  # Réduire de 10% pour avoir une échelle
                max_solde = max_solde * 1.1  # Augmenter de 10%
        
        # Préparer les points pour le graphique
        points = []
        for i, solde in enumerate(soldes_quotidiens):
            solde_float = float(solde['solde_apres'])  # Convertir en float pour le calcul
            x = i * (350 / (len(soldes_quotidiens) - 1)) if len(soldes_quotidiens) > 1 else 175
            y = 150 - ((solde_float - min_solde) / (max_solde - min_solde)) * 130 if max_solde != min_solde else 85
            points.append(f"{x},{y}")
        
        graphique_svg = {
            'points': points,
            'min_solde': min_solde,
            'max_solde': max_solde,
            'dates': [s['date'].strftime('%d/%m/%Y') for s in soldes_quotidiens],
            'soldes': soldes_values
        }
    else:
        graphique_svg = None
    return render_template('banking/compte_detail.html',
                        compte=compte,
                        sous_comptes=sous_comptes,
                        mouvements=mouvements,
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
                        mois_seletcted=mois_seletct,
                        annee_selected=annee_select,
                        nb_jours_periode=nb_jours_periode)

@bp.route('/banking/sous-compte/<int:sous_compte_id>')
@login_required
def banking_sous_compte_detail(sous_compte_id):
    user_id = current_user.id
    # Récupérer les comptes de l'utilisateur
    comptes_ = g.models.compte_model.get_by_user_id(user_id)
    
    # Récupérer tous les sous-comptes de l'utilisateur
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
        limit=50)
        
    # Ajouter les statistiques du sous-compte
    stats_sous_compte = g.models.transaction_financiere_model.get_statistiques_compte(
        compte_type='sous_compte',
        compte_id=sous_compte_id,
        user_id=user_id,
        periode_jours=30
    )
    
    solde = g.models.sous_compte_model.get_solde(sous_compte_id)
    
    # Ajout du pourcentage calculé
    if sous_compte['objectif_montant'] and sous_compte['objectif_montant'] > 0:
        sous_compte['pourcentage_objectif'] = round((sous_compte['solde'] / sous_compte['objectif_montant']) * 100, 1)
    else:
        sous_compte['pourcentage_objectif'] = 0
    
        # Récupération de l'évolution des soldes quotidiens pour les 30 derniers jours
    soldes_quotidiens = g.models.transaction_financiere_model.get_evolution_soldes_quotidiens_sous_compte(
        sous_compte_id=sous_compte_id, 
        user_id=user_id, 
        nb_jours=30
    )

    # Préparation des données pour le graphique SVG (même code que pour le compte principal)
    if soldes_quotidiens:
        soldes_values = [s['solde_apres'] for s in soldes_quotidiens]
        min_solde = min(int(soldes_values)) if soldes_values else 0
        max_solde = max(int(soldes_values)) if soldes_values else 0
        
        if min_solde == max_solde:
            if min_solde == 0:
                max_solde = 100
            else:
                min_solde = min_solde * 0.9
                max_solde = max_solde * 1.1
        
        points = []
        for i, solde in enumerate(soldes_quotidiens):
            x = i * (350 / (len(soldes_quotidiens) - 1)) if len(soldes_quotidiens) > 1 else 175
            y = 150 - ((solde['solde_apres'] - min_solde) / (max_solde - min_solde)) * 130 if max_solde != min_solde else 85
            points.append(f"{x},{y}")
        
        graphique_svg = {
            'points': points,
            'min_solde': min_solde,
            'max_solde': max_solde,
            'dates': [s['date'].strftime('%d/%m') for s in soldes_quotidiens],
            'soldes': soldes_values
        }
    else:
        graphique_svg = None
    return render_template(
        'banking/sous_compte_detail.html',
        sous_compte=sous_compte,
        comptes_=comptes_,
        sous_comptes_=sous_comptes_,
        compte=compte_principal,
        mouvements=mouvements,
        solde=solde,
        stats_sous_compte=stats_sous_compte,  # Ajouter les stats au contexte
        graphique_svg=graphique_svg
    )
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
    all_comptes = g.models.compte_model.get_all_accounts(g.db_manager)
    
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
                return render_template('banking/depot.html', comptes=comptes, all_comptes=all_comptes, form_data=request.form)
        else:
            date_transaction = datetime.now()
        
        # Appel de la fonction create_depot avec la date
        success, message = g.models.transaction_financiere_model.create_depot(
            compte_id, user_id, montant, description, compte_type, date_transaction
        )
        
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
    all_comptes = g.models.compte_model.get_all_accounts(g.db_manager)
    
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


@bp.route('/banking/transfert', methods=['GET', 'POST'])
@login_required
def banking_transfert():
    user_id = current_user.id
    comptes = g.models.compte_model.get_by_user_id(user_id)
    print(f'Voici les comptes de l\'utilisateur {user_id} : {comptes}')

    # Convertir les IDs en entiers pour éviter les problèmes de comparaison
    for compte in comptes:
        compte['id'] = int(compte['id'])
    
    all_comptes = g.models.compte_model.get_all_accounts(g.db_manager)
    sous_comptes = []
    
    for c in comptes:
        subs = g.models.sous_compte_model.get_by_compte_principal_id(c['id'])
        for sub in subs:
            sub['id'] = int(sub['id'])  # Convertir les IDs en entiers
        sous_comptes += subs

    all_comptes = [c for c in g.models.compte_model.get_all_accounts(g.db_manager) if c['utilisateur_id'] != user_id]
    
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
                                            
                else:  # transfert externe
                    # [Code pour le transfert externe reste inchangé]
                    pass

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
                    compte_id, sous_compte_id, montant, user_id, commentaire
                )
            else:
                success, message = g.models.transaction_financiere_model.transfert_sous_compte_vers_compte(
                    sous_compte_id, compte_id, montant, user_id, commentaire
                )

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
        sous_comptes=sous_comptes
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
    if request.method == 'POST':
        nouveau_montant = Decimal(request.form.get('montant'))
        nouvelle_description = request.form.get('description', '').strip()
        
        success, message = g.models.transaction_financiere_model.modifier_transaction(
            transaction_id=transfert_id,
            user_id=current_user.id,
            nouveau_montant=nouveau_montant,
            nouvelle_description=nouvelle_description)
        if success:
            flash(message, "success")
        else:
            flash(message, "danger")        
        return redirect(request.referrer or url_for('banking.banking_dashboard'))
    # Méthode GET - afficher le formulaire de modification
    # (à implémenter selon vos besoins)
    flash("Fonctionnalité non implémentée", "warning")
    return redirect(url_for('banking.banking_dashboard'))

@bp.route('/banking/supprimer_transfert/<int:transfert_id>', methods=['POST'])
@login_required
def supprimer_transfert(transfert_id):
    success, message = g.models.transaction_financiere_model.supprimer_transaction(
        transaction_id=transfert_id,
        user_id=current_user.id)
    if success:
        flash(message, "success")
    else:
        flash(message, "danger")        
    return redirect(request.referrer or url_for('banking.banking_dashboard'))

@bp.route('/banking/liste_transferts', methods=['GET'])
@login_required
def liste_transferts():
    user_id = current_user.id
    # Récupération de tous les paramètres de filtrage possibles
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    compte_source_id = request.args.get('compte_source_id')
    compte_dest_id = request.args.get('compte_dest_id')
    sous_compte_source_id = request.args.get('sous_compte_source_id')
    sous_compte_dest_id = request.args.get('sous_compte_dest_id')
    type_transfert = request.args.get('type_transfert') # Nom unifié
    statut = request.args.get('statut')
    page = int(request.args.get('page', 1))
    per_page = 20

    # Récupération des comptes et sous-comptes pour les filtres
    comptes = g.models.compte_model.get_by_user_id(user_id)
    sous_comptes = []
    for c in comptes:
        sous_comptes += g.models.sous_compte_model.get_by_compte_principal_id(c['id'])

    # Récupération des mouvements financiers avec filtres
    filters = {
        'date_from': date_from,
        'date_to': date_to,
        'compte_source_id': compte_source_id,
        'compte_dest_id': compte_dest_id,
        'sous_compte_source_id': sous_compte_source_id,
        'sous_compte_dest_id': sous_compte_dest_id,
        'type_transfert': type_transfert,
        'statut': statut,
        'user_id': user_id,
        'page': page,
        'per_page': per_page
    }
    # Utilisez une méthode unifiée qui peut récupérer à la fois les transactions et les transferts
    # NOTE: Cette méthode est une hypothèse, elle doit être implémentée dans votre modèle
    # transaction_financiere_model.
    mouvements = g.models.transaction_financiere_model.get_by_filters(filters)
    total_mouvements = g.models.transaction_financiere_model.count_by_filters(filters)
    pages = (total_mouvements + per_page - 1) // per_page

    # Export CSV
    if request.args.get('export') == 'csv':
        si = StringIO()
        cw = csv.writer(si, delimiter=';')
        # Entêtes de colonne unifiées
        cw.writerow(['Date', 'Type', 'Description', 'Source', 'Destination', 'Montant', 'Statut'])
        for t in mouvements:
            # Logique pour déterminer la source et la destination
            source = ""
            if t['compte_source_id']:
                source = t.get('nom_compte_source', 'N/A')
                if t.get('sous_compte_source_id'):
                    source += f" ({t.get('nom_sous_compte_source', 'N/A')})"
            else:
                source = t.get('nom_source_externe', 'Externe')

            destination = ""
            if t['compte_dest_id']:
                destination = t.get('nom_compte_dest', 'N/A')
                if t.get('sous_compte_dest_id'):
                    destination += f" ({t.get('nom_sous_compte_dest', 'N/A')})"
            else:
                destination = t.get('nom_dest_externe', 'Externe')

            # Gestion du statut pour tous les types de mouvements
            statut_display = 'Complété' if t.get('statut') == 'completed' else 'En attente' if t.get('statut') == 'pending' else 'N/A'

            cw.writerow([
                t['date_mouvement'].strftime("%Y-%m-%d %H:%M"), # Utiliser un champ de date générique
                t['type_transaction'],
                t.get('description', ''),
                source,
                destination,
                f"{t['montant']:.2f}",
                statut_display
            ])
        
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = "attachment; filename=mouvements.csv"
        output.headers["Content-Type"] = "text/csv; charset=utf-8"
        return output

    # Rendu de la page unifiée
    return render_template(
        'banking/liste_transferts.html', # Nom de la nouvelle page unifiée
        transactions=mouvements, # Renommé pour correspondre à la page HTML
        comptes=comptes,
        sous_comptes=sous_comptes,
        page=page,
        pages=pages,
        date_from=date_from,
        date_to=date_to,
        compte_source_filter=compte_source_id,
        compte_dest_filter=compte_dest_id,
        sc_source_filter=sous_compte_source_id,
        sc_dest_filter=sous_compte_dest_id,
        type_filter=type_transfert,
        statut_filter=statut
    )

# ---- APIs ----
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


@bp.route('/comptabilite/categories')
@login_required
def liste_categories_comptables():
    #plan_comptable = PlanComptable(g.db_manager)
    categories = g.models.plan_comptable_model.get_all_categories()
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
                'type': request.form['type'],
                'parent_id': request.form.get('parent_id') or None
            }         
            if g.models.plan_comptable_model.create(data):
                flash('Catégorie créée avec succès', 'success')
                return redirect(url_for('banking.liste_categories_comptables'))
            else:
                flash('Erreur lors de la création', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    categories = g.models.plan_comptable_model.get_all_categories()
    return render_template('comptabilite/edit_categorie.html', 
                        categories=categories,
                        categorie=None)

@bp.route('/comptabilite/categories/<int:categorie_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_categorie(categorie_id):
    """Modifie une catégorie comptable existante"""
    #plan_comptable = PlanComptable(g.db_manager)
    categorie = g.models.plan_comptable_model.get_by_id(categorie_id)
    if not categorie:
        flash('Catégorie introuvable', 'danger')
        return redirect(url_for('banking.liste_categories_comptables'))
    if request.method == 'POST':
        try:
            data = {
                'numero': request.form['numero'],
                'nom': request.form['nom'],
                'type': request.form['type'],
                'parent_id': request.form.get('parent_id') or None
            }
            if g.models.plan_comptable_model.update(categorie_id, data):
                flash('Catégorie mise à jour avec succès', 'success')
                return redirect(url_for('banking.liste_categories_comptables'))
            else:
                flash('Erreur lors de la mise à jour', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    categories = g.models.plan_comptable_model.get_all_categories()
    return render_template('comptabilite/edit_categorie.html', 
                        categories=categories,
                        categorie=categorie)

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
            csv_input = csv.reader(stream)
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
    if g.models.plan_comptable_model.delete(categorie_id):
        flash('Catégorie supprimée avec succès', 'success')
    else:
        flash('Erreur lors de la suppression', 'danger')
    
    return redirect(url_for('banking.liste_categories_comptables'))

@bp.route('/comptabilite/nouveau-contact', methods=['GET', 'POST'])
@login_required
def nouveau_contact_comptable():
    """Crée un nouveau contact pour la comptabilité"""
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
    """Affiche la liste des contacts comptables"""
    #contact_model = Contacts(g.db_manager)
    contacts = g.models.contact_model.get_all(current_user.id)
    
    # Debug: afficher la structure du premier contact
    if contacts:
        print("Structure du premier contact:", contacts[0])
        print("Clés disponibles:", contacts[0].keys())
    
    return render_template('comptabilite/liste_contacts.html', contacts=contacts)
    
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
    statut = request.args.get('statut', 'tous')  # Nouveau paramètre statut
    
    # Définir les statuts disponibles pour le template
    statuts_disponibles = [
        {'value': 'tous', 'label': 'Tous les statuts'},
        {'value': 'pending', 'label': 'En attente'},
        {'value': 'validée', 'label': 'Validées'},
        {'value': 'rejetée', 'label': 'Rejetées'}
    ]
    
    # Préparer les paramètres pour la requête
    filtres = {
        'user_id': current_user.id,
        'date_from': date_from,
        'date_to': date_to,
        'statut': statut if statut != 'tous' else None,
        'contact_id': int(id_contact) if id_contact else None
    }
    if categorie_id:
        ecritures = g.models.ecriture_comptable_model.get_by_categorie(
            categorie_id=int(categorie_id),
            **filtres
        )
    elif compte_id:
        ecritures = g.models.ecriture_comptable_model.get_by_compte_bancaire(
            compte_id=int(compte_id),
            **filtres
        )
    elif id_contact:
        ecritures = g.models.ecriture_comptable_model.get_by_contact_id(
            contact_id=int(id_contact),
            **filtres
        )   
    else:
        # Si aucun filtre spécifique, récupérer toutes les écritures avec les filtres
        ecritures = g.models.ecriture_comptable_model.get_by_statut(
            user_id=current_user.id,
            statut=filtres['statut'],
            date_from=date_from,
            date_to=date_to
        ) if filtres['statut'] else g.models.ecriture_comptable_model.get_all(
            user_id=current_user.id,
            date_from=date_from,
            date_to=date_to
        )
    comptes = g.models.compte_model.get_by_user_id(current_user.id)
    contacts=g.models.contact_model.get_all(current_user.id)
    return render_template('comptabilite/ecritures.html', 
                        ecritures=ecritures, 
                        comptes=comptes,
                        compte_selectionne=compte_id,
                        statuts_disponibles=statuts_disponibles,
                        statut_selectionne=statut,
                        contacts=contacts,
                        contact_selectionne=id_contact,
                        date_from=date_from,
                        date_to=date_to,
                        categorie_id=categorie_id)

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

from datetime import datetime

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

@bp.route('/comptabilite/ecritures/by-contact/<int:contact_id>', methods=['GET'])
@login_required
def liste_ecritures_par_contact(contact_id):
    """Affiche les écritures associées à un contact spécifique"""
    current_user_id = current_user.id
    contact = g.models.contact_model.get_by_id(contact_id, current_user_id)
    
    contact = g.models.contact_model.get_by_id(contact_id, current_user_id)
    if not contact:
        flash('Contact introuvable', 'danger')
        return redirect(url_for('banking.liste_contacts_comptables'))
    ecritures = g.models.ecriture_comptable_model.get_by_contact_id(contact_id, utilisateur_id=current_user_id)
    print(ecritures)
    comptes = g.models.compte_model.get_by_user_id(current_user_id)
    return render_template('comptabilite/ecritures_par_contact.html', 
                        ecritures=ecritures, 
                        contact=contact,
                        comptes=comptes)

@bp.route('/comptabilite/ecritures/nouvelle', methods=['GET', 'POST'])
@login_required
def nouvelle_ecriture():
    if request.method == 'POST':
        try:
            data = {
                'date_ecriture': request.form['date_ecriture'],
                'compte_bancaire_id': int(request.form['compte_bancaire_id']),
                'categorie_id': int(request.form['categorie_id']),
                'montant': Decimal(request.form['montant']),
                'description': request.form.get('description', ''),
                'id_contact': int(request.form['id_contact']) if request.form.get('id_contact') else None,
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
    # GET request processing
    transaction_id = request.args.get('transaction_id')
    transaction_data = {}
    if transaction_id:
        transaction = g.models.transaction_financiere_model.get_by_id(transaction_id)
        if transaction and transaction['utilisateur_id'] == current_user.id:
            transaction_data = {
                'date_ecriture': transaction['date_transaction'].strftime('%Y-%m-%d'),
                'montant': abs(transaction['montant']),
                'type_ecriture': 'depot' if transaction['type_transaction'] == 'depot' else 'depense',
                'description': transaction['description'],
                'compte_bancaire_id': transaction['compte_principal_id']
            }  
    comptes = g.models.compte_model.get_by_user_id(current_user.id)   
    # CORRECTION: Utiliser l'instance existante plan_comptable
    categories = g.models.plan_comptable_model.get_all_categories()        
    contacts = g.models.contact_model.get_all(current_user.id)
    statuts_disponibles = [
        {'value': 'pending', 'label': 'En attente'},
        {'value': 'validée', 'label': 'Validée'},
        {'value': 'rejetée', 'label': 'Rejetée'}
    ]    
    return render_template('comptabilite/nouvelle_ecriture.html', 
                        comptes=comptes, 
                        categories=categories,
                        ecriture=None,
                        transaction_data=transaction_data,
                        transaction_id=transaction_id,
                        statuts_disponibles=statuts_disponibles,
                        contacts=contacts)

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
        id_contacts = request.form.getlist('id_contact[]')
        references = request.form.getlist('reference[]')
        statuts = request.form.getlist('statut[]')
        succes_count = 0
        for i in range(len(dates)):
            try:
                if not all([dates[i], types[i], comptes_ids[i], categories_ids[i], montants[i]]):
                    flash(f"Écriture {i+1}: Tous les champs obligatoires doivent être remplis", "warning")
                    continue
                montant = float(montants[i])
                taux_tva = float(tva_taux[i]) if tva_taux[i] and tva_taux[i] != '' else None
                statut = statuts[i] if i < len(statuts) and statuts[i] else 'pending'

                data = {
                    'date_ecriture': dates[i],
                    'compte_bancaire_id': int(comptes_ids[i]),
                    'categorie_id': int(categories_ids[i]),
                    'montant': Decimal(str(montant)),
                    'description': descriptions[i] if i < len(descriptions) else '',
                    'id_contact': int(request.form['id_contact']) if request.form.get('id_contact') else None,
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
    # GET request processing
    comptes = g.models.compte_model.get_by_user_id(current_user.id)
    categories = g.models.plan_comptable_model.get_all_categories()
    contacts = g.models.contact_model.get_all(current_user.id)
    statuts_disponibles = [
        {'value': 'pending', 'label': 'En attente'},
        {'value': 'validée', 'label': 'Validée'},
        {'value': 'rejetée', 'label': 'Rejetée'}
    ]   
    return render_template(
        'comptabilite/nouvelle_ecriture_multiple.html',
        comptes=comptes,
        categories=categories,
        statuts_disponibles=statuts_disponibles,
        current_date=datetime.now().strftime('%Y-%m-%d'), contacts=contacts)
    

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
    categories = g.models.plan_comptable_model.get_all_categories()
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

@bp.route('/comptabilite/ecritures/<int:ecriture_id>/delete', methods=['POST'])
@login_required
def delete_ecriture(ecriture_id):
    """Supprime une écriture comptable"""
    ecriture = g.models.ecriture_comptable_model.get_by_id(ecriture_id)
    if not ecriture or ecriture['utilisateur_id'] != current_user.id:
        flash('Écriture introuvable ou non autorisée', 'danger')
        return redirect(url_for('banking.liste_ecritures'))  
    if g.models.ecriture_comptable_model.delete(ecriture_id):
        flash('Écriture supprimée avec succès', 'success')
    else:
        flash('Erreur lors de la suppression', 'danger')    
    return redirect(url_for('banking.liste_ecritures'))

# Ajouter une route pour lier une transaction à une écriture
@bp.route('/banking/link_transaction', methods=['POST'])
@login_required
def link_transaction_to_ecriture():
    transaction_id = request.form.get('transaction_id')
    ecriture_id = request.form.get('ecriture_id')
    transaction = g.models.transaction_financiere_model.get_by_id(transaction_id)
    if not transaction or transaction['utilisateur_id'] != current_user.id:
        flash('Transaction non trouvée ou non autorisée', 'danger')
        return redirect(url_for('banking.banking_dashboard'))
    if g.models.transaction_financiere_model.link_to_ecriture(transaction_id, ecriture_id):
        flash('Transaction liée avec succès', 'success')
    else:
        flash('Erreur lors du lien', 'danger')
    return redirect(url_for('banking.banking_compte_detail', compte_id=transaction['compte_principal_id']))


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
        return redirect(url_for('banking.index'))

@bp.route('/comptabilite/ecritures/detail/<string:type>/<categorie_id>')
@login_required
def detail_ecritures_categorie(type, categorie_id):
    """Affiche le détail des écritures d'une catégorie"""
    try:
        annee = request.args.get('annee', datetime.now().year)
        date_from = f"{annee}-01-01"
        date_to = f"{annee}-12-31"
        connection = g.models.ecriture_comptable_model.db.get_connection()
        if not connection:
            flash("Erreur de connexion à la base de données", "danger")
            return redirect(url_for('banking.compte_de_resultat'))
        try:
            cursor = connection.cursor(dictionary=True)
            # Construire la requête avec une jointure LEFT pour les contacts
            query = """
                SELECT 
                    e.date_ecriture,
                    e.description,
                    e.reference,
                    e.montant,
                    e.statut,
                    e.id_contact,
                    c.nom as categorie_nom,
                    c.numero as categorie_numero,
                    ct.nom as contact_nom
                FROM ecritures_comptables e
                JOIN categories_comptables c ON e.categorie_id = c.id
                LEFT JOIN contacts ct ON e.id_contact = ct.id_contact
                WHERE e.utilisateur_id = %s
                AND e.date_ecriture BETWEEN %s AND %s
                AND e.statut = 'validée'
            """
            params = [current_user.id, date_from, date_to]
            if type == 'produit':
                query += " AND c.type_compte = 'Revenus'"
            elif type == 'charge':
                query += " AND c.type_compte = 'Charge'"
            
            if categorie_id != 'all':
                query += " AND e.categorie_id = %s"
                params.append(int(categorie_id))
            query += " ORDER BY e.date_ecriture DESC"
            cursor.execute(query, tuple(params))
            ecritures = cursor.fetchall()
            # Calculer le total
            total = sum(float(e['montant']) for e in ecritures)
            # Titre de la page
            if categorie_id == 'all':
                titre = f"Tous les {type}s - {annee}"
            else:
                # Récupérer le nom de la catégorie depuis la première écriture ou depuis la base
                if ecritures:
                    categorie_nom = ecritures[0]['categorie_nom']
                    categorie_numero = ecritures[0]['categorie_numero']  # Récupérer aussi le numéro depuis les écritures
                else:
                    # Si pas d'écritures, récupérer le nom de la catégorie directement
                    cursor.execute("SELECT nom, numero FROM categories_comptables WHERE id = %s", (int(categorie_id),))  # Correction ici
                    categorie = cursor.fetchone()
                    categorie_nom = categorie['nom'] if categorie else "Catégorie inconnue"
                    categorie_numero = categorie['numero'] if categorie else "Numéro inconnu"
                titre = f"{categorie_numero} : {categorie_nom} - {annee}"
            cursor.close()
            connection.close()
            return render_template('comptabilite/detail_ecritures.html',
                                ecritures=ecritures,
                                total=total,
                                titre=titre,
                                annee=annee,
                                type=type)
        
        except Exception as e:
            print(f"Erreur lors du chargement des détails: {e}")
            flash(f"Erreur lors du chargement des détails: {str(e)}", "danger")
            return redirect(url_for('banking.compte_de_resultat'))
        finally:
            if connection:
                connection.close()
    
    except Exception as e:
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
    categories = g.models.plan_comptable_model.get_all_categories()
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
    contrat = g.models.contrat_model.get_contrat_actuel(current_user_id)
    heures_hebdo_contrat = contrat['heures_hebdo'] if contrat else 38.0
    now = datetime.now()
    # Récupérer mois, semaine, mode selon méthode HTTP
    if request.method == 'POST':
        annee = int(request.form.get('annee', now.year))
        mois = int(request.form.get('mois', now.month))
        semaine = int(request.form.get('semaine', 0))
        current_mode = request.form.get('mode', 'reel')
    else:
        annee = int(request.args.get('annee', now.year))
        mois = int(request.args.get('mois', now.month))
        semaine = int(request.args.get('semaine', 0))
        current_mode = request.args.get('mode', 'reel')
    
    # Actions POST
    if request.method == 'POST':
        annee = int(request.form.get('annee', now.year))
        if 'save_line' in request.form:
            return handle_save_line(request, current_user_id, annee, mois, semaine, current_mode)
        elif 'reset_line' in request.form:
            return handle_reset_line(request, current_user_id, annee,  mois, semaine, current_mode)
        elif 'reset_all' in request.form:
            return handle_reset_all(request, current_user_id, annee, mois, semaine, current_mode)
        elif request.form.get('action') == 'simuler':
            return handle_simulation(request, current_user_id, annee, mois, semaine, current_mode)
        else:
            return handle_save_all(request, current_user_id, annee, mois, semaine, current_mode)

    # Traitement GET : affichage des heures
    semaines = {}
    for day_date in generate_days(annee, mois, semaine):
        date_str = day_date.isoformat()
        jour_data = g.models.heure_model.get_by_date(date_str, current_user_id) or {
            'date': date_str,
            'h1d': '',
            'h1f': '',
            'h2d': '',
            'h2f': '',
            'vacances': False,
            'total_h': 0.0
        }
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
    semaines = dict(sorted(semaines.items()))
    return render_template('salaires/heures_travail.html',
                        semaines=semaines,
                        total_general=total_general,
                        heures_hebdo_contrat=heures_hebdo_contrat,
                        current_mois=mois,
                        current_semaine=semaine,
                        current_annee=annee,
                        current_mode=current_mode,
                        now = datetime.now())

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

def create_day_payload(request, user_id, date_str):
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

def process_day(request, user_id, date_str, annee, mois, semaine, mode, flash_message=True):
    errors = validate_day_data(request, date_str)
    if errors:
        for error in errors:
            flash(f"Erreur {format_date(date_str)}: {error}", "error")
        return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode))
    
    payload = create_day_payload(request, user_id, date_str)
    
    # Utiliser la méthode sécurisée de HeureTravail
    success = g.models.heure_model.create_or_update(payload)
    
    if success:
        if flash_message:
            flash(f"Heures du {format_date(date_str)} enregistrées", "success")
    else:
        flash(f"Échec de la sauvegarde pour {format_date(date_str)}", "error")
    
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode))

def format_date(date_str):
    return datetime.fromisoformat(date_str).strftime('%d/%m/%Y')

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
def handle_save_line(request, user_id, annee, mois, semaine, mode):
    date_str = request.form['save_line']
    return process_day(request, user_id, date_str, annee, mois, semaine, mode)

def handle_reset_line(request, user_id, annee, mois, semaine, mode):
    date_str = request.form['reset_line']
    heure_model = HeureTravail(g.db_manager)
    try:
        heure_model.delete_by_date(date_str, user_id)
        flash(f"Les heures du {format_date(date_str)} ont été réinitialisées", "warning")
    except Exception as e:
        logger.error(f"Erreur reset_line pour {date_str}: {str(e)}")
        flash(f"Erreur lors de la réinitialisation du {format_date(date_str)}", "error")
    return redirect(url_for('banking.heures_travail', annee=annee,mois=mois, semaine=semaine, mode=mode))

def handle_reset_all(request, user_id, annee, mois, semaine, mode):
    days = generate_days(annee, mois, semaine)
    errors = []
    for day in days:
        try:
            g.models.heure_model.delete_by_date(day.isoformat(), user_id)
        except Exception as e:
            logger.error(f"Erreur reset jour {day}: {str(e)}")
            errors.append(format_date(day.isoformat()))
    if errors:
        flash(f"Erreur lors de la réinitialisation des jours: {', '.join(errors)}", "error")
    else:
        flash("Toutes les heures ont été réinitialisées", "warning")
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode))

def handle_simulation(request, user_id, annee,mois, semaine, mode):
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
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode))

def handle_save_all(request, user_id, annee, mois, semaine, mode):
    days = generate_days(annee, mois, semaine)
    has_errors = False
    
    for day in days:
        date_str = day.isoformat()
        payload = create_day_payload(request, user_id, date_str)
        
        if not g.models.heure_model.create_or_update(payload):
            has_errors = True
            logger.error(f"Erreur traitement jour {date_str}")
    
    if not has_errors:
        flash("Toutes les heures ont été enregistrées avec succès", "success")
    
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode))
# --- Routes salaires ---

@bp.route('/salaires', methods=['GET'])
@login_required
def salaires():
    # Récupération des paramètres d'année et de mois
    now = datetime.now()
    annee = request.args.get('annee', now.year, type=int)
    mois = request.args.get('mois', now.month, type=int)
    logger.info(f"Données reçues: mois={mois}, annee={annee}")

    # Initialisation des modèles
    current_user_id = current_user.id
    
    # Structure des données par mois
    salaires_par_mois = {}
    
    # Pour chaque mois de l'année
    for m in range(1, 13):
        # Récupération du contrat actif pour ce mois spécifique
        date_mois = f"{annee}-{m:02d}-01"
        contrat = g.models.contrat_model.get_contrat_for_date(current_user_id, date_mois)
        
        jour_estimation = contrat['jour_estimation_salaire'] if contrat else 15
        salaire_horaire = 24.05  # Valeur par défaut
        
        if contrat:
            try:
                # Conversion explicite en float
                salaire_horaire = float(contrat.get('salaire_horaire', 24.05))
            except (TypeError, ValueError) as e:
                logger.error(f"Erreur conversion salaire horaire: {e}")
                salaire_horaire = 24.05
        
        # Récupération des heures réelles travaillées
        heures_reelles = g.models.heure_model.get_total_heures_mois(current_user_id, annee, m) or 0.0
        heures_reelles = round(heures_reelles, 2)
        
        
        # Calcul des acomptes estimés
        salaire_acompte_25_estime = 0.0
        salaire_acompte_10_estime = 0.0
        salaire_calcule = 0.0
        salaire_net = 0.0
        details = {'erreur': 'Pas de données ou contrat manquant'}
        if heures_reelles > 0 and contrat:
            try:
                # Calcul acompte du 25 estimé
                details = g.models.salaire_model.calculer_salaire_net_avec_details(
                    heures_reelles, contrat, 
                    user_id=current_user_id, annee=annee, mois=m)
                
                # EXTRACTION DES VALEURS APRÈS le calcul
                versements = details.get('details', {}).get('versements', {})
                salaire_acompte_25_estime = versements.get('acompte_25', {}).get('montant', 0)
                salaire_acompte_10_estime = versements.get('acompte_10', {}).get('montant', 0)
                
                salaire_net = details.get('salaire_net', 0.0)
                salaire_calcule = details.get('details', {}).get('salaire_brut', 0.0)
                
                # DEBUG
                print(f"Mois {m}: Acomptes extraits -> 25: {salaire_acompte_25_estime}, 10: {salaire_acompte_10_estime}")
                
            except Exception as e:
                logger.error(f"Erreur calcul détails pour mois {m}: {e}")
                details = {'erreur': f'Erreur calcul détails: {str(e)}'}

        
        # Vérifier si un salaire existe en base pour ce mois
        salaire_existant = g.models.salaire_model.get_by_mois_annee(current_user_id, annee, m)
        
        if salaire_existant:
            update_data = {
                'heures_reelles': heures_reelles,
                'salaire_calcule': salaire_calcule,
                'salaire_net': salaire_net,
                'acompte_25_estime': salaire_acompte_25_estime,
                'acompte_10_estime': salaire_acompte_10_estime
            }
            print(f"DEBUG - Mois {m}:")
            print(f"  salaire_acompte_25_estime = {salaire_acompte_25_estime}")
            print(f"  salaire_acompte_10_estime = {salaire_acompte_10_estime}")
            g.models.salaire_model.update(salaire_existant[0]['id'], update_data)
            salaires_par_mois[m] = {**salaire_existant[0], **update_data, 'details': details}
        else:
            # Créer une nouvelle entrée en BASE DE DONNÉES
            new_salaire = {
                'mois': m,
                'annee': annee,
                'user_id': current_user_id,
                'heures_reelles': heures_reelles,
                'salaire_calcule': salaire_calcule,
                'salaire_net': salaire_net,
                'salaire_verse': 0.0,
                'acompte_25': 0.0,
                'acompte_10': 0.0,
                'acompte_25_estime': salaire_acompte_25_estime,
                'acompte_10_estime': salaire_acompte_10_estime,
                'difference': 0.0,
                'difference_pourcent': 0.0,
                'salaire_horaire': salaire_horaire,
                'details': details
            }
            salaire_id = g.models.salaire_model.create(new_salaire)
            new_salaire['id'] = salaire_id
            salaires_par_mois[m] = new_salaire

    # Calcul des totaux annuels
    totaux = {
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

    for m, mois_data in salaires_par_mois.items():
        totaux['total_heures_reelles'] += mois_data.get('heures_reelles', 0) or 0
        totaux['total_salaire_calcule'] += mois_data.get('salaire_calcule', 0) or 0
        totaux['total_salaire_net'] += mois_data.get('salaire_net', 0) or 0
        totaux['total_salaire_verse'] += mois_data.get('salaire_verse', 0) or 0
        totaux['total_acompte_25'] += mois_data.get('acompte_25', 0) or 0
        totaux['total_acompte_10'] += mois_data.get('acompte_10', 0) or 0
        totaux['total_acompte_25_estime'] += mois_data.get('acompte_25_estime', 0) or 0
        totaux['total_acompte_10_estime'] += mois_data.get('acompte_10_estime', 0) or 0
        totaux['total_difference'] += mois_data.get('difference', 0) or 0

    # Formatage des valeurs pour l'affichage
    for key in totaux:
        if isinstance(totaux[key], float):
            totaux[key] = round(totaux[key], 2)

    # Récupération du contrat actuel pour l'affichage global
    contrat_actuel = g.models.contrat_model.get_contrat_actuel(current_user_id)

    return render_template('salaires/calcul_salaires.html',
                        salaires_par_mois=salaires_par_mois,
                        totaux=totaux,
                        annee_courante=annee,
                        contrat_actuel=contrat_actuel)

@bp.route('/api/details_calcul_salaire')
@login_required
def details_calcul_salaire():
    try:
        # Récupération des paramètres
        mois = request.args.get('mois', type=int)
        annee = request.args.get('annee', type=int)
        contrat = g.models.contrat_model.get_contrat_for_date(current_user_id, f"{annee}-{mois:02d}-01")
    
        if not contrat:
            return jsonify({'erreur': 'Aucun contrat trouvé pour cette période'}), 404
        
        if not mois or not annee:
            return jsonify({'erreur': 'Mois et année requis'}), 400
        
        # Récupération du contrat actuel
        current_user_id = current_user.id
        contrat = g.models.contrat_model.get_contrat_actuel(current_user_id)
        
        if not contrat:
            return jsonify({'erreur': 'Aucun contrat trouvé'}), 404
        
        # Récupération des heures réelles
        heures_reelles = g.models.heure_model.get_total_heures_mois(current_user_id, annee, mois) or 0.0
        
        # Calcul avec détails
        resultats = g.models.salaire_model.calculer_salaire_net_avec_details(heures_reelles, contrat)
        
        # Ajout du mois et de l'année aux résultats
        resultats['mois'] = mois
        resultats['annee'] = annee
        return jsonify(resultats)
    except Exception as e:
        return jsonify({'erreur': f'Erreur serveur: {str(e)}'}), 500

@bp.route('/update_salaire', methods=['POST'])
@login_required
def update_salaire():
    # Récupération des données du formulaire en tant que chaînes (sans conversion automatique)
    mois_str = request.form.get('mois')
    annee_str = request.form.get('annee')
    salaire_verse_str = request.form.get('salaire_verse')
    acompte_25_str = request.form.get('acompte_25')
    acompte_10_str = request.form.get('acompte_10')

    annee_now = datetime.now().year
    
    # Conversion unique et sécurisée pour toutes les variables
    try:
        mois = int(mois_str) if mois_str and mois_str.strip() else None
        annee = int(annee_str) if annee_str and annee_str.strip() else None
        
        # Le reste des conversions
        salaire_verse = float(salaire_verse_str) if salaire_verse_str and salaire_verse_str.strip() else 0.0
        acompte_25 = float(acompte_25_str) if acompte_25_str and acompte_25_str.strip() else 0.0
        acompte_10 = float(acompte_10_str) if acompte_10_str and acompte_10_str.strip() else 0.0

        if mois is None or annee is None:
            flash("Mois et année sont requis", "error")
            return redirect(url_for('banking.salaires', annee=annee_now))
    except (ValueError, TypeError):
        flash("Format de données invalide", "error")
        return redirect(url_for('salaires', annee=annee_now))
    current_user_id = current_user.id
    
    # Récupération du contrat
    contrat = g.models.contrat_model.get_contrat_actuel(current_user_id)
    try:
        salaire_horaire = float(contrat.get('salaire_horaire', 24.05))
    except (TypeError, ValueError):
        salaire_horaire = 24.05
        current_app.logger.warning(f"Valeur salaire horaire invalide: {contrat.get('salaire_horaire')}")
    jour_estimation = int(contrat['jour_estimation_salaire']) if contrat and 'jour_estimation_salaire' in contrat else 15
    
    # Récupération des heures réelles
    heures_reelles = g.models.heure_model.get_total_heures_mois(current_user_id, annee, mois) or 0.0
    
    # Récupération de l'entrée existante
    existing = g.models.salaire_model.get_by_mois_annee(current_user_id, annee, mois)
    
    # Calcul du salaire théorique
    try:
        salaire_calcule = g.models.salaire_model.calculer_salaire(heures_reelles, salaire_horaire)
    except Exception as e:
        current_app.logger.error(f"Erreur calcul salaire pour {mois}/{annee}: {str(e)}")
        salaire_calcule = 0.0
    try:
    # Création d'une date de référence
        date_ref = datetime(annee, mois, 1)
    
    # Calcul du nombre de jours dans le mois
        if mois == 12:
            next_month = datetime(annee+1, 1, 1)
        else:
            next_month = datetime(annee, mois+1, 1)
        jours_dans_mois = (next_month - date_ref).days
    
    # Calcul du ratio pour le premier acompte
        ratio_premier_acompte = min(jour_estimation / jours_dans_mois, 1.0)
    
    # Calcul des acomptes estimés
        acompte_25_estime = salaire_calcule * ratio_premier_acompte
        acompte_10_estime = salaire_calcule * (1 - ratio_premier_acompte)
    except Exception as e:
        print(f"Erreur calcul acomptes estimés: {e}")
        acompte_25_estime, acompte_10_estime = 0.0, 0.0
        
    # Calcul des différences
    difference, difference_pourcent = g.models.salaire_model.calculer_differences(
        salaire_calcule, 
        salaire_verse
    )
    
    # Préparation des données de mise à jour
    update_data = {
        'salaire_verse': salaire_verse,
        'acompte_25': acompte_25,
        'acompte_10': acompte_10,
        'salaire_calcule': salaire_calcule,
        'difference': difference,
        'difference_pourcent': difference_pourcent
    }
    
    if existing:
        # Mettre à jour l'entrée existante EN BASE
        salaire_id = existing[0]['id']
        success = g.models.salaire_model.update(salaire_id, update_data)
    else:
        # Créer une nouvelle entrée EN BASE
        full_data = {
            'mois': mois,
            'annee': annee,
            'user_id': current_user_id,
            'heures_reelles': heures_reelles,
            'salaire_horaire': salaire_horaire,
            'acompte_25_estime': acompte_25_estime,
            'acompte_10_estime': acompte_10_estime,
            **update_data
        }
        success = g.models.salaire_model.create(full_data)
    
    if success:
        flash("Les valeurs ont été mises à jour avec succès", "success")
    else:
        flash("Erreur lors de la mise à jour des données", "error")
    return redirect(url_for('banking.salaires', annee=annee))

@bp.route('/synthese-hebdo', methods=['GET'])
@login_required
def synthese_hebdomadaire():
    current_user_id = current_user.id

    annee = int(request.args.get('annee', datetime.now().year))
    semaine = int(request.args.get('semaine', 0))

    synthese = g.models.synthese_model.get_by_user_and_week(current_user_id, annee, semaine)
    if synthese:
        synthese_data = synthese
    else:
        synthese_data = {'heures_total': 0.0, 'montant_total': 0.0}

    return render_template('salaires/synthese_mensuelle.html',
                        synthese=synthese_data,
                        current_annee=annee,
                        current_semaine=semaine)


@bp.route('/synthese-mensuelle', methods=['GET'])
@login_required
def synthese_mensuelle():
    current_user_id = current_user.id
    annee = int(request.args.get('annee', datetime.now().year))
    mois = int(request.args.get('mois', datetime.now().month))
    synthese = g.models.synthese_model.get_by_user_and_month(current_user_id, annee, mois)
    if synthese:
        synthese_data = synthese
    else:
        synthese_data = {'heures_total': 0.0, 'montant_total': 0.0}
    return render_template('salaires/synthese_mensuelle.html',
                        synthese=synthese_data,
                        current_annee=annee,
                        current_mois=mois)

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
                    '   ': float(request.form.get('indemnite_repas_tx') or 0),
                    'indemnite_retenues_tx': float(request.form.get('indemnite_retenues_tx') or 0),
                    'cotisation_avs_tx': float(request.form.get('cotisation_avs_tx') or 0),
                    'cotisation_ac_tx': float(request.form.get('cotisation_ac_tx') or 0),
                    'cotisation_accident_n_prof_tx': float(request.form.get('cotisation_accident_n_prof_tx') or 0),
                    'cotisation_assurance_indemnite_maladie_tx': float(request.form.get('asscotisation_assurance_indemnite_maladie_txurance_indemnite_maladie_tx') or 0),
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
    


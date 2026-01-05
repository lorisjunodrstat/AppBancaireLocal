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
bp = Blueprint('compta', __name__)

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

##### Partie comptabilité


@bp.route('/comptabilite/dashboard')
@login_required
def comptabilite_dashboard():
    # Récupération de l'année depuis les paramètres, ou année en cours par défaut
    annee = request.args.get('annee', datetime.now().year, type=int)
    date_from = f"{annee}-01-01"
    date_to = f"{annee}-12-31"

    # Calcul des KPIs
    stats = g.models.ecriture_comptable_model.get_stats_by_categorie(
        user_id=current_user.id,
        date_from=date_from,
        date_to=date_to
    )
    total_recettes = sum(s['total_recettes'] or 0 for s in stats)
    total_depenses = sum(s['total_depenses'] or 0 for s in stats)
    resultat_net = total_recettes - total_depenses

    # Nombre de transactions à comptabiliser
    comptes = g.models.compte_model.get_by_user_id(current_user.id) # Utilise la méthode correcte
    transactions_a_comptabiliser = []
    for compte in comptes:
        # Appel correct de la méthode avec les arguments nommés pour éviter les ambiguités
        txs = g.models.transaction_financiere_model.get_transactions_sans_ecritures_par_compte(
            compte_id=compte['id'], # Premier argument : compte_id
            user_id=current_user.id, # Deuxième argument : user_id
            # Pas besoin de spécifier date_from/date_to ici, on veut pour l'année entière
            # On peut ajouter date_from et date_to si le filtre par année est important pour cette requête
            # date_from=date_from, date_to=date_to
            statut_comptable='a_comptabiliser'
        )
        transactions_a_comptabiliser.extend(txs)
    nb_a_comptabiliser = len(transactions_a_comptabiliser)

    # Préparer les données pour le template
    annees_disponibles = g.models.ecriture_comptable_model.get_annees_disponibles(current_user.id)

    return render_template('comptabilite/dashboard.html',
                        total_recettes=total_recettes,
                        total_depenses=total_depenses,
                        resultat_net=resultat_net,
                        nb_a_comptabiliser=nb_a_comptabiliser,
                        annee_selectionnee=annee,
                        annees_disponibles=annees_disponibles)
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
                'parent_id': request.form.get('groupe') or None,
                'categorie_complementaire_id': request.form.get('categorie_complementaire') or None,
                'type_ecriture_complementaire': request.form.get('type_ecriture_complementaire') or None
            }
            if g.models.categorie_comptable_model.update(categorie_id, data):
                flash('Catégorie mise à jour avec succès', 'success')
                return redirect(url_for('banking.liste_categories_comptables'))
            else:
                flash('Erreur lors de la mise à jour', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    
    # Récupérer toutes les catégories (y compris avec les informations complémentaires)
    categories = g.models.categorie_comptable_model.get_all_categories()
    types_compte = ['Actif', 'Passif', 'Charge', 'Revenus']
    types_tva = ['', 'taux_plein', 'taux_reduit', 'taux_zero', 'exonere']
    types_ecriture = ['', 'depense', 'recette']  # Valeurs possibles pour le champ enum
    
    return render_template('comptabilite/edit_categorie.html', 
                        categories=categories,
                        categorie=categorie,
                        types_compte=types_compte,
                        types_tva=types_tva,
                        types_ecriture=types_ecriture)

@bp.route('/comptabilite/categories/import-csv', methods=['POST'])
@login_required
def import_plan_comptable_csv():
    """Importe le plan comptable depuis un fichier CSV"""
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
                if len(row) >= 9:  # Mise à jour : 9 colonnes au minimum
                    cursor.execute("""
                        INSERT INTO categories_comptables 
                        (numero, nom, parent_id, type_compte, compte_systeme, compte_associe, type_tva, categorie_complementaire_id, type_ecriture_complementaire, actif)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        row[0], row[1], 
                        int(row[2]) if row[2] else None,  # parent_id (ancien groupe)
                        row[3], 
                        row[4] if row[4] else None, 
                        row[5] if row[5] else None, 
                        row[6] if row[6] else None,
                        int(row[7]) if row[7] and row[7].strip() != '' else None,  # categorie_complementaire_id
                        row[8] if row[8] and row[8].strip() != '' else None,       # type_ecriture_complementaire
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
    """Affiche la liste des écritures comptables avec filtrage avancé"""
    # Récupération des paramètres de filtrage
    compte_id = request.args.get('compte_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    categorie_id = request.args.get('categorie_id')
    id_contact = request.args.get('id_contact')
    statut = request.args.get('statut', 'tous')
    type_ecriture = request.args.get('type_ecriture', 'tous')
    type_ecriture_comptable = request.args.get('type_ecriture_comptable', 'tous')
    
    # Définition des options disponibles
    types_ecriture_disponibles = [
        {'value': 'tous', 'label': 'Tous les types'},
        {'value': 'recette', 'label': 'Recettes'},
        {'value': 'depense', 'label': 'Dépenses'}
    ]
    
    type_ecriture_comptable_disponibles = [
        {'value': 'tous', 'label': 'Tous les types'},
        {'value': 'principale', 'label': 'Écritures principales'},
        {'value': 'complementaire', 'label': 'Écritures complémentaires'}
    ]
    
    statuts_disponibles = [
        {'value': 'tous', 'label': 'Tous les statuts'},
        {'value': 'pending', 'label': 'En attente'},
        {'value': 'validée', 'label': 'Validées'},
        {'value': 'rejetée', 'label': 'Rejetées'},
        {'value': 'supprimee', 'label': 'Archivées'}
    ]
    
    # Préparer les filtres pour la méthode
    filtres = {
        'user_id': current_user.id,
        'date_from': date_from,
        'date_to': date_to,
        'statut': statut if statut != 'tous' else None,
        'id_contact': int(id_contact) if id_contact and id_contact.isdigit() else None,
        'compte_id': int(compte_id) if compte_id and compte_id.isdigit() else None,
        'categorie_id': int(categorie_id) if categorie_id and categorie_id.isdigit() else None,
        'type_ecriture': type_ecriture if type_ecriture != 'tous' else None,
        'type_ecriture_comptable': type_ecriture_comptable if type_ecriture_comptable != 'tous' else None,
        'limit': 1000
    }
    
    # Récupérer les écritures avec filtres
    ecritures = g.models.ecriture_comptable_model.get_with_filters(**filtres)
    
    # Récupérer les données supplémentaires
    comptes = g.models.compte_model.get_by_user_id(current_user.id)
    contacts = g.models.contact_model.get_all(current_user.id)
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    contact_map = {c['id_contact']: c['nom'] for c in contacts}

    # Gestion du modal de liaison
    show_link_modal = request.args.get('show_link_modal') == '1'
    ecriture_link = None
    transactions_eligibles = []

    if show_link_modal:
        eid = request.args.get('ecriture_id', type=int)
        if eid:
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

    # Gestion du modal de détail de transaction
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
        categories=categories,
        compte_selectionne=compte_id,
        statuts_disponibles=statuts_disponibles,
        types_ecriture_disponibles=types_ecriture_disponibles,
        type_ecriture_selectionne=type_ecriture,
        type_ecriture_comptable_disponibles=type_ecriture_comptable_disponibles,
        type_ecriture_comptable_selectionne=type_ecriture_comptable,
        statut_selectionne=statut,
        contacts=contacts,
        contact_selectionne=id_contact,
        date_from=date_from,
        date_to=date_to,
        categorie_id=categorie_id,
        show_link_modal=show_link_modal,
        ecriture_link=ecriture_link,
        transactions_eligibles=transactions_eligibles,
        contact_map=contact_map,
        show_transaction_modal=show_transaction_modal,
        transaction_detail=transaction_detail
    )

# Route pour l'export
@bp.route('/comptabilite/ecritures/export')
@login_required
def export_ecritures():
    """Exporte les écritures selon les filtres actuels en CSV"""
    # Récupérer les mêmes paramètres que la liste
    compte_id = request.args.get('compte_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    categorie_id = request.args.get('categorie_id')
    id_contact = request.args.get('id_contact')
    statut = request.args.get('statut', 'tous')
    type_ecriture = request.args.get('type_ecriture', 'tous')
    type_ecriture_comptable = request.args.get('type_ecriture_comptable', 'tous')
    
    filtres = {
        'user_id': current_user.id,
        'date_from': date_from,
        'date_to': date_to,
        'statut': statut if statut != 'tous' else None,
        'id_contact': int(id_contact) if id_contact and id_contact.isdigit() else None,
        'compte_id': int(compte_id) if compte_id and compte_id.isdigit() else None,
        'categorie_id': int(categorie_id) if categorie_id and categorie_id.isdigit() else None,
        'type_ecriture': type_ecriture if type_ecriture != 'tous' else None,
        'type_ecriture_comptable': type_ecriture_comptable if type_ecriture_comptable != 'tous' else None,
        'limit': None  # Pas de limite pour l'export
    }
    
    ecritures = g.models.ecriture_comptable_model.get_with_filters(**filtres)
    
    import csv
    from io import StringIO
    
    output = StringIO()
    writer = csv.writer(output)
    
    if ecritures:
        # En-têtes
        headers = list(ecritures[0].keys()) if isinstance(ecritures[0], dict) else [f"col_{i}" for i in range(len(ecritures[0]))]
        writer.writerow(headers)
        
        # Données
        for ecriture in ecritures:
            if isinstance(ecriture, dict):
                row = [ecriture.get(header, "") for header in headers]
            else:
                row = list(ecriture)
            writer.writerow(row)
    
    output.seek(0)
    filename = f"ecritures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return send_file(
        StringIO(output.getvalue()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
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
    ecritures_avec_secondaires = []
    for ecriture in ecritures:
        ecriture_dict = dict(ecriture)
        if ecriture.get('type_ecriture_comptable') == 'principale' or not ecriture.get('ecriture_principale_id'):
            secondaires = g.models.ecriture_comptable_model.get_ecritures_complementaires(ecriture['id'], current_user.id)
            ecriture_dict['ecritures_secondaires'] = secondaires
        ecritures_avec_secondaires.append(ecriture_dict)
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
        ecritures=ecritures_avec_secondaires,
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
                    elif budget_mensuel is None:
                        budget_mensuel = 0
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
            categorie_complementaire_id = request.form.get('categorie_complementaire_id', None)
            type_ecriture_complementaire = request.form.get('type_ecriture_complementaire', None)
            couleur = request.form.get('couleur', '')
            icone = request.form.get('icone', '')
            budget_mensuel = request.form.get('budget_mensuel', 0)
            
            updates = {}
            if nom and nom != categorie['nom']:
                updates['nom'] = nom
            if description != categorie.get('description', ''):
                updates['description'] = description
            if categorie_complementaire_id != str(categorie.get('categorie_complementaire_id', '')):
                updates['categorie_complementaire_id'] = categorie_complementaire_id
            if type_ecriture_complementaire != categorie.get('type_ecriture_complementaire', ''):
                updates['type_ecriture_complementaire'] = type_ecriture_complementaire
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

#@bp.route('/categorie/associer', methods=['POST'])
#@login_required
#def associer_categorie_transaction():
#    transaction_id = request.form.get('transaction_id', type=int)
#    categorie_id = request.form.get('categorie_id', type=int)
#    
#    if not transaction_id or not categorie_id:
#        flash("Données manquantes", "error")
#        return redirect(request.referrer or url_for('banking.banking_dashboard'))#
#
#    success, message = g.models.categorie_transaction_model.associer_categorie_transaction(
#        transaction_id, categorie_id, current_user.id
#    )
#    if not success:
#        flash(message, "error")
#    else:
#        flash("Catégorie associée avec succès", "success")
#    
#    return redirect(request.referrer)

@bp.route('/categorie/associer-transaction', methods=['POST'])
@login_required
def associer_categorie_transaction():
    """Associe une catégorie à une transaction via formulaire HTML classique."""
    transaction_id = request.form.get('transaction_id', type=int)
    categorie_id = request.form.get('categorie_id', type=int)
    
    if not transaction_id or not categorie_id:
        flash("Veuillez sélectionner une transaction et une catégorie.", "warning")
        return redirect(request.referrer or url_for('banking.banking_dashboard'))

    # Vérifier que la transaction existe et appartient à l'utilisateur
    tx = g.models.transaction_financiere_model.get_transaction_by_id(transaction_id)
    if not tx or tx.get('owner_user_id') != current_user.id:
        flash("Transaction non trouvée ou non autorisée.", "error")
        return redirect(request.referrer or url_for('banking.banking_dashboard'))

    success, message = g.models.categorie_transaction_model.associer_categorie_transaction(
        transaction_id, categorie_id, current_user.id
    )
    
    if success:
        flash("Catégorie associée avec succès.", "success")
    else:
        flash(message, "error")
    
    return redirect(request.referrer)
@bp.route('/categorie/associer-transaction-multiple', methods=['POST'])
@login_required
def associer_categorie_transaction_multiple():
    """Associe une même catégorie à toutes les transactions non catégorisées d'une période."""
    compte_id = request.form.get('compte_id', type=int)
    date_debut_str = request.form.get('date_debut')
    date_fin_str = request.form.get('date_fin')
    categorie_id = request.form.get('categorie_id', type=int)

    if not all([compte_id, date_debut_str, date_fin_str, categorie_id]):
        flash("Données incomplètes pour la catégorisation multiple.", "warning")
        return redirect(request.referrer or url_for('banking.banking_dashboard'))

    try:
        date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
        date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Dates invalides.", "error")
        return redirect(request.referrer)

    # Vérifier que le compte appartient à l'utilisateur
    compte = g.models.compte_model.get_by_id(compte_id)
    if not compte or compte['utilisateur_id'] != current_user.id:
        flash("Compte non autorisé.", "error")
        return redirect(url_for('banking.banking_dashboard'))

    # Récupérer les transactions non catégorisées dans la période
    transactions_non_cat, _ = g.models.transaction_financiere_model.get_all_user_transactions(
        user_id=current_user.id,
        date_from=date_debut.isoformat(),
        date_to=date_fin.isoformat(),
        compte_source_id=compte_id,
        compte_dest_id=compte_id,
        per_page=10000
    )

    # Filtrer celles qui n'ont aucune catégorie
    transactions_a_categoriser = []
    for tx in transactions_non_cat:
        cats = g.models.categorie_transaction_model.get_categories_transaction(tx['id'], current_user.id)
        if not cats:
            transactions_a_categoriser.append(tx['id'])

    if not transactions_a_categoriser:
        flash("Aucune transaction non catégorisée dans cette période.", "info")
        return redirect(request.referrer)

    # Associer la catégorie à chacune
    erreurs = 0
    for tx_id in transactions_a_categoriser:
        try:
            g.models.categorie_transaction_model.associer_categorie_transaction(
                tx_id, categorie_id, current_user.id
            )
        except Exception as e:
            logging.error(f"Erreur catégorisation multiple TX {tx_id}: {e}")
            erreurs += 1

    if erreurs == 0:
        flash(f"Catégorie appliquée à {len(transactions_a_categoriser)} transactions.", "success")
    else:
        flash(f"Catégorie appliquée partiellement ({len(transactions_a_categoriser) - erreurs} / {len(transactions_a_categoriser)}).", "warning")

    return redirect(request.referrer)
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
    
    # Pour chaque transaction, récupérer le contact lié au compte
    transactions_avec_contacts = []
    for transaction in transactions:
        contact_lie = None
        if transaction.get('compte_principal_id'):
            contact_lie = g.models.contact_compte_model.get_contact_by_compte(
                transaction['compte_principal_id'], 
                current_user.id
            )
        # Ajouter le contact_lie à la transaction
        transaction_dict = dict(transaction)
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
    
    # Récupérer les catégories et celles avec complémentaires
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    categories_avec_complementaires = g.models.categorie_comptable_model.get_categories_avec_complementaires(current_user.id)
    
    # 🔥 NOUVEAU : Créer un set des IDs de catégories qui ont des écritures secondaires
    categories_avec_complementaires_ids = set()
    for cat in categories_avec_complementaires:
        if cat.get('categorie_complementaire_id'):
            categories_avec_complementaires_ids.add(cat['id'])
    
    contacts = g.models.contact_model.get_all(current_user.id)
    
    return render_template('comptabilite/transactions_sans_ecritures.html',
        transactions=transactions_avec_contacts,
        comptes=comptes,
        compte_selectionne=compte_id,
        statuts_comptables=statuts_comptables,
        statut_comptable_selectionne=statut_comptable,
        date_from=date_from,
        date_to=date_to,
        categories=categories,
        categories_avec_complementaires_ids=categories_avec_complementaires_ids,  # 🔥 NOUVEAU
        total_a_comptabiliser=total_a_comptabiliser,
        total_a_comptabiliser_len=total_a_comptabiliser_len, 
        contacts=contacts
    )

@bp.route('/comptabilite/ecritures/nouvelle/from_selected', methods=['GET', 'POST'])
@login_required
def nouvelle_ecriture_from_selected():
    """Affiche le formulaire de création d'écritures pour transactions sélectionnées"""
    
    if request.method == 'POST':
        # Traitement des écritures sélectionnées
        selected_transaction_ids = request.form.getlist('transaction_ids[]')
        dates = request.form.getlist('date_ecriture[]')
        types_ecriture = request.form.getlist('type_ecriture[]')
        comptes_ids = request.form.getlist('compte_bancaire_id[]')
        categories_ids = request.form.getlist('categorie_id[]')
        montants = request.form.getlist('montant[]')
        tva_taux = request.form.getlist('tva_taux[]')
        # 🔥 RÉCUPÉRER LE MONTANT HTVA CALCULÉ PAR LE SERVEUR (ou pas, on le calcule)
        # montants_htva = request.form.getlist('montant_htva[]') # Ce champ est readonly ou hidden
        descriptions = request.form.getlist('description[]')
        references = request.form.getlist('reference[]')
        statuts = request.form.getlist('statut[]')
        contacts_ids = request.form.getlist('id_contact[]')
        
        if not selected_transaction_ids:
            flash("Aucune transaction sélectionnée", "warning")
            return redirect(url_for('banking.transactions_sans_ecritures'))

        succes_count = 0
        secondary_count = 0
        errors = []

        for i in range(len(selected_transaction_ids)):
            try:
                if not all([dates[i], types_ecriture[i], comptes_ids[i], categories_ids[i], montants[i]]):
                    errors.append(f"Transaction {i+1}: Tous les champs obligatoires doivent être remplis")
                    continue

                montant_ttc = Decimal(str(montants[i]))
                taux_tva = Decimal(str(tva_taux[i])) if tva_taux[i] and tva_taux[i] != '' else Decimal('0')

                # 🔥 CALCUL DU MONTANT HTVA CÔTÉ SERVEUR
                if taux_tva > 0:
                    montant_htva_calcule = montant_ttc / (1 + taux_tva / Decimal('100'))
                else:
                    montant_htva_calcule = montant_ttc # Si pas de TVA, HTVA = TTC

                data = {
                    'date_ecriture': dates[i],
                    'compte_bancaire_id': int(comptes_ids[i]),
                    'categorie_id': int(categories_ids[i]),
                    'montant': montant_ttc,
                    # 🔥 UTILISER LE MONTANT HTVA CALCULÉ CÔTÉ SERVEUR
                    'montant_htva': montant_htva_calcule,
                    'description': descriptions[i] if i < len(descriptions) and descriptions[i] else '',
                    'id_contact': int(contacts_ids[i]) if i < len(contacts_ids) and contacts_ids[i] else None,
                    'reference': references[i] if i < len(references) and references[i] else '',
                    'type_ecriture': types_ecriture[i],
                    'tva_taux': taux_tva,
                    'utilisateur_id': current_user.id,
                    'statut': statuts[i] if i < len(statuts) and statuts[i] else 'pending',
                    'devise': 'CHF',
                    'type_ecriture_comptable': 'principale'
                }

                # 🔥 CORRECTION : Calcul TVA cohérent (déjà fait ci-dessus)
                if data['tva_taux'] > 0:
                    data['tva_montant'] = data['montant'] - data['montant_htva']
                else:
                    data['tva_montant'] = Decimal('0')

                if g.models.ecriture_comptable_model.create(data):
                    succes_count += 1
                    ecriture_id = g.models.ecriture_comptable_model.last_insert_id
                    
                    # 🔥 COMPTAGE DES ÉCRITURES SECONDAIRES
                    secondaires = g.models.ecriture_comptable_model.get_ecritures_complementaires(ecriture_id, current_user.id)
                    secondary_count += len(secondaires)
                    
                    # Lier l'écriture à la transaction
                    transaction_id = int(selected_transaction_ids[i])
                    g.models.ecriture_comptable_model.link_ecriture_to_transaction(transaction_id, ecriture_id, current_user.id)
                else:
                    errors.append(f"Transaction {i+1}: Erreur lors de l'enregistrement")
                    
            except Exception as e:
                errors.append(f"Transaction {i+1}: Erreur - {str(e)}")
                continue

        # Gestion des messages
        for error in errors:
            flash(error, "warning")
                
        if succes_count > 0:
            message = f"{succes_count} écriture(s) créée(s) avec succès"
            if secondary_count > 0:
                message += f" ({secondary_count} écriture(s) secondaire(s) générée(s) automatiquement)"
            flash(message, "success")
        else:
            flash("Aucune écriture n'a pu être créée", "error")
            
        compte_id = request.form.get('compte_id', type=int)
        date_from = request.form.get('date_from')
        date_to = request.form.get('date_to')
        statut_comptable = request.form.get('statut_comptable')

        return redirect(url_for('banking.transactions_sans_ecritures',
                               compte_id=compte_id,
                               date_from=date_from,
                               date_to=date_to,
                               statut_comptable=statut_comptable))
    
    # GET - Afficher le formulaire
    # Récupérer les transactions sélectionnées depuis la session
    transaction_ids = session.get('selected_transaction_ids', [])
    if not transaction_ids:
        flash("Aucune transaction sélectionnée", "warning")
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
        return redirect(url_for('banking.transactions_sans_ecritures'))
    
    # Récupérer les données pour les formulaires
    comptes = g.models.compte_model.get_all_accounts()
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    contacts = g.models.contact_model.get_all(current_user.id)
    
    # 🔥 NOUVEAU : Récupérer les catégories avec écritures secondaires
    categories_avec_complementaires = g.models.categorie_comptable_model.get_categories_avec_complementaires(current_user.id)
    categories_avec_complementaires_ids = set()
    for cat in categories_avec_complementaires:
        if cat.get('categorie_complementaire_id'):
            categories_avec_complementaires_ids.add(cat['id'])
    
    return render_template('comptabilite/creer_ecritures_groupées.html',
                        transactions=transactions,
                        comptes=comptes,
                        categories=categories,
                        categories_avec_complementaires_ids=categories_avec_complementaires_ids,
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
    
    success, message = g.models.ecriture_comptable_model.update_statut_comptable(
        transaction_id, current_user.id, nouveau_statut
    )
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'error')
    
    return redirect(request.referrer or url_for('banking.transactions_sans_ecritures'))

# app/routes/banking.py

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
            # 🔥 PRÉSERVER LES FILTRES
            compte_id = request.form.get('compte_id', type=int)
            date_from = request.form.get('date_from')
            date_to = request.form.get('date_to')
            statut_comptable = request.form.get('statut_comptable')
            return redirect(url_for('banking.transactions_sans_ecritures',
                                   compte_id=compte_id,
                                   date_from=date_from,
                                   date_to=date_to,
                                   statut_comptable=statut_comptable))

        categorie_id = request.form.get('categorie_id', type=int)
        # 🔥 RÉCUPÉRER LE TAUX DE TVA
        taux_tva_form = request.form.get('tva_taux', '0.0')
        taux_tva = Decimal(str(taux_tva_form)) if taux_tva_form else Decimal('0')

        if not categorie_id:
            flash("Veuillez sélectionner une catégorie comptable", "error")
            # 🔥 PRÉSERVER LES FILTRES
            compte_id = request.form.get('compte_id', type=int)
            date_from = request.form.get('date_from')
            date_to = request.form.get('date_to')
            statut_comptable = request.form.get('statut_comptable')
            return redirect(url_for('banking.transactions_sans_ecritures',
                                   compte_id=compte_id,
                                   date_from=date_from,
                                   date_to=date_to,
                                   statut_comptable=statut_comptable))

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

        # 🔥 CALCUL DU MONTANT HTVA CÔTÉ SERVEUR
        montant_ttc = Decimal(str(transaction['montant']))
        if taux_tva > 0:
            montant_htva_calcule = montant_ttc / (1 + taux_tva / Decimal('100'))
        else:
            montant_htva_calcule = montant_ttc # Si pas de TVA, HTVA = TTC

        # Créer l'écriture comptable
        ecriture_data = {
            'date_ecriture': transaction['date_transaction'],
            'compte_bancaire_id': transaction['compte_principal_id'],
            'categorie_id': categorie_id,
            'montant': montant_ttc,
            # 🔥 AJOUTER LE MONTANT HTVA CALCULÉ
            'montant_htva': montant_htva_calcule,
            'devise': 'CHF',
            'description': transaction['description'],
            'type_ecriture': type_ecriture,
            'tva_taux': taux_tva, # Sauvegarder le taux fourni
            # 🔥 CALCULER LE MONTANT DE LA TVA
            'tva_montant': montant_ttc - montant_htva_calcule if taux_tva > 0 else Decimal('0'),
            'utilisateur_id': current_user.id,
            'statut': 'pending',  # Statut en attente
            'transaction_id': transaction_id,
            'id_contact': id_contact  # 🔥 Contact du formulaire OU lié au compte
        }

        if g.models.ecriture_comptable_model.create(ecriture_data):
            # Marquer la transaction comme comptabilisée
            g.models.ecriture_comptable_model.update_statut_comptable(
                transaction_id, current_user.id, 'comptabilise'
            )

            # Message de confirmation avec info contact
            message = "Écriture créée avec succès avec statut 'En attente'"
            if id_contact:
                contact_info = g.models.contact_model.get_by_id(id_contact, current_user.id)
                if contact_info:
                    message += f" - Contact: {contact_info['nom']}"
            # 🔥 AJOUTER INFO TVA AU MESSAGE
            if taux_tva > 0:
                 message += f" - TVA {taux_tva}% appliquée ({ecriture_data['tva_montant']} CHF)"
            flash(message, "success")
        else:
            flash("Erreur lors de la création de l'écriture", "error")

    except Exception as e:
        logging.error(f"Erreur création écriture automatique: {e}")
        flash(f"Erreur lors de la création de l'écriture: {str(e)}", "error")

    # 🔥 PRÉSERVER LES FILTRES
    compte_id = request.form.get('compte_id', type=int)
    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')
    statut_comptable = request.form.get('statut_comptable')
    return redirect(url_for('banking.transactions_sans_ecritures',
                           compte_id=compte_id,
                           date_from=date_from,
                           date_to=date_to,
                           statut_comptable=statut_comptable))
                           # OU simplement redirect(request.referrer or url_for('banking.transactions_sans_ecritures'))
                           # mais cela peut conserver des anciens paramètres GET si le referrer est la page filtrée.
                           # La méthode ci-dessus avec request.form est plus fiable pour conserver les filtres actuels.
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
                'montant_htva':Decimal(request.form.get('montant_htva', request.form['montant'])),
                'description': request.form.get('description', ''),
                'id_contact': id_contact,  # 🔥 Utilise le contact du formulaire ou celui lié au compte
                'reference': request.form.get('reference', ''),
                'type_ecriture': request.form['type_ecriture'],
                'tva_taux': Decimal(request.form['tva_taux']) if request.form.get('tva_taux') else None,
                'utilisateur_id': current_user.id,
                'statut': request.form.get('statut', 'pending'),
                'devise': request.form.get('devise', 'CHF'),
                'type_ecriture_comptable' : 'principale'
            }
            
            if data['tva_taux']:
                if 'montant_htva' in request.form and request.form['montant_htva']:
                    data['montant_htva'] = Decimal(request.form['montant_htva'])
                    data['tva_montant'] = data['montant'] - data['montant_htva']
                else:
                    data['montant_htva'] = data['montant'] / ( + data['tva_taux'] /100)
                    data['tva_montant'] = data['montant'] - data['montant_htva']
            else:
                data['montant_htva'] = data['montant']
                data['tva_montant'] = 0
                
            if g.models.ecriture_comptable_model.create(data):
                flash('Écriture enregistrée avec succès', 'success')
                ecriture_id = g.models.ecriture_comptable_model.last_insert_id
                secondaires = g.models.ecriture_comptable_model.get_ecritures_complementaires(ecriture_id, current_user.id)
                if secondaires:
                    flash(f'{len(secondaires)} écriture(s) secondaires créée(s) automatiquement', 'info')

                transaction_id = request.form.get('transaction_id')
                if transaction_id:
                    g.models.ecriture_comptable_model.link_ecriture_to_transaction(transaction_id, g.models.ecriture_comptable_model.last_insert_id, current_user.id)
                return redirect(url_for('banking.liste_ecritures'))
            else:
                flash('Erreur lors de l\'enregistrement', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    
    elif request.method == 'GET':
        comptes = g.models.compte_model.get_all_accounts()
        categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
        contacts = g.models.contact_model.get_all(current_user.id)
        categories_avec_complementaires = g.models.categorie_comptable_model.get_categories_avec_complementaires(current_user.id)
        return render_template('comptabilite/nouvelle_ecriture.html',
            comptes=comptes,
            categories=categories,
            categories_avec_complementaires=categories_avec_complementaires,
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
        secondary_count = 0
        errors = []
        for i in range(len(dates)):
            try:
                if not all([dates[i], types[i], comptes_ids[i], categories_ids[i], montants[i]]):
                    errors.append(f"écritures {i + 1} : Tous les champs obligatoires doivent être remplis.")
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
                    'montant_htva': Decimal(str(request.form.getlist('montant_htva[]')[i]))
                    if i < len(request.form.getlist('montant_htva[]')) and request.form.getlist('montant_htva[]')[i] else Decimal(str(montant)), 
                    'description': descriptions[i] if i < len(descriptions) else '',
                    'id_contact': id_contact_ligne,  # 🔥 Contact principal ou lié au compte
                    'reference': references[i] if i < len(references) else '',
                    'type_ecriture': types[i],
                    'tva_taux': Decimal(str(taux_tva)) if taux_tva else None,
                    'utilisateur_id': current_user.id,
                    'statut': statut,
                    'devise': 'CHF',
                    'type_ecriture_comptable' : 'principale'
                }
                
                if data['tva_taux']:
                    if data['montant_htva'] != data['montant']:
                        data['tva_montant'] = data['montant'] - data['montant_htva']
                    else:
                        data['montant_htva'] = data['montant'] / (1 + data['tva_taux'] / 100)
                        data['tva_montant'] = data['montant'] - data['montant_htva']
                else:
                    data['tva_montant'] = 0

                if g.models.ecriture_comptable_model.create(data):
                    succes_count += 1
                    ecriture_id = g.models.ecriture_comptable_model.last_insert_id
                    secondaires = g.models.ecriture_comptable_model.get_ecritures_complementaires[ecriture_id, current_user.id]
                    secondary_count += len(secondaires)
                else:
                    errors.append(f"Ecriture {i + 1} : Erreur lors de l'enregistrement.")
                    flash(f"Écriture {i+1}: Erreur lors de l'enregistrement", "error")
            except ValueError as e:
                flash(f"Écriture {i+1}: Erreur de format - {str(e)}", "error")
                continue
            except Exception as e:
                flash(f"Écriture {i+1}: Erreur inattendue - {str(e)}", "error")
                continue

        for error in errors:
            flash(error, "warning")
                
        if succes_count > 0:
            flash(f"{succes_count} écriture(s) enregistrée(s) avec succès!", "success")
            if secondary_count > 0:
                message += f"({secondary_count} écrtures(s) secondaires créée(s))"
        else:
            flash("Aucune écriture n'a pu être enregistrée", "warning")
        return redirect(url_for('banking.liste_ecritures'))
    
    # GET request processing (reste inchangé)
    elif request.method == 'GET':
        comptes = g.models.compte_model.get_all_accounts()
        categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
        contacts = g.models.contact_model.get_all(current_user.id)
        categories_avec_conplementaires = g.models.categorie_comptable_model.get_categories_avec_complementaires(current_user.id)

        return render_template('comptabilite/nouvelle_ecriture_multiple.html',
            comptes=comptes,
            categories=categories,
            categories_avec_conplementaires=categories_avec_conplementaires,
            contacts=contacts,
            today=datetime.now().strftime('%Y-%m-%d'))

# app/routes/banking.py

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
            # 🔥 PRÉSERVER LES FILTRES
            compte_id = request.form.get('compte_id', type=int)
            date_from = request.form.get('date_from')
            date_to = request.form.get('date_to')
            statut_comptable = request.form.get('statut_comptable')
            return redirect(url_for('banking.transactions_sans_ecritures',
                                   compte_id=compte_id,
                                   date_from=date_from,
                                   date_to=date_to,
                                   statut_comptable=statut_comptable))

        # Vérifier si la transaction a déjà des écritures
        if transaction.get('nb_ecritures', 0) > 0:
            flash("Cette transaction a déjà des écritures associées", "warning")
            # 🔥 PRÉSERVER LES FILTRES
            compte_id = request.form.get('compte_id', type=int)
            date_from = request.form.get('date_from')
            date_to = request.form.get('date_to')
            statut_comptable = request.form.get('statut_comptable')
            return redirect(url_for('banking.transactions_sans_ecritures',
                                   compte_id=compte_id,
                                   date_from=date_from,
                                   date_to=date_to,
                                   statut_comptable=statut_comptable))

        categories_ids = request.form.getlist('categorie_id[]')
        montants = request.form.getlist('montant[]')
        # 🔥 RÉCUPÉRER LES TAUX DE TVA POUR CHAQUE LIGNE
        tva_taux_list = request.form.getlist('tva_taux[]')
        descriptions = request.form.getlist('description[]')

        if len(categories_ids) != len(montants):
            flash("Le nombre de catégories et de montants doit correspondre", "error")
            # 🔥 PRÉSERVER LES FILTRES
            compte_id = request.form.get('compte_id', type=int)
            date_from = request.form.get('date_from')
            date_to = request.form.get('date_to')
            statut_comptable = request.form.get('statut_comptable')
            return redirect(url_for('banking.transactions_sans_ecritures',
                                   compte_id=compte_id,
                                   date_from=date_from,
                                   date_to=date_to,
                                   statut_comptable=statut_comptable))

        total_montants = sum(Decimal(str(m)) for m in montants)
        if total_montants != Decimal(str(transaction['montant'])):
            flash("La somme des montants ne correspond pas au montant de la transaction", "error")
            # 🔥 PRÉSERVER LES FILTRES
            compte_id = request.form.get('compte_id', type=int)
            date_from = request.form.get('date_from')
            date_to = request.form.get('date_to')
            statut_comptable = request.form.get('statut_comptable')
            return redirect(url_for('banking.transactions_sans_ecritures',
                                   compte_id=compte_id,
                                   date_from=date_from,
                                   date_to=date_to,
                                   statut_comptable=statut_comptable))

        success_count = 0
        for i in range(len(categories_ids)):
            try:
                if not categories_ids[i] or not montants[i]:
                    flash(f"Écriture {i+1}: Tous les champs obligatoires doivent être remplis", "warning")
                    continue

                montant_ttc = Decimal(str(montants[i]))
                # 🔥 RÉCUPÉRER LE TAUX DE TVA POUR CETTE LIGNE
                taux_tva_str = tva_taux_list[i] if i < len(tva_taux_list) else '0.0'
                taux_tva = Decimal(str(taux_tva_str)) if taux_tva_str else Decimal('0')

                # 🔥 CALCUL DU MONTANT HTVA CÔTÉ SERVEUR POUR CETTE LIGNE
                if taux_tva > 0:
                    montant_htva_calcule = montant_ttc / (1 + taux_tva / Decimal('100'))
                else:
                    montant_htva_calcule = montant_ttc # Si pas de TVA, HTVA = TTC

                data = {
                    'date_ecriture': transaction['date_transaction'],
                    'compte_bancaire_id': transaction['compte_principal_id'],
                    'categorie_id': int(categories_ids[i]),
                    'montant': montant_ttc,
                    # 🔥 AJOUTER LE MONTANT HTVA CALCULÉ POUR CETTE LIGNE
                    'montant_htva': montant_htva_calcule,
                    'description': descriptions[i] if i < len(descriptions) and descriptions[i] else transaction['description'],
                    'id_contact': transaction.get('id_contact'), # Contact principal du modal
                    'reference': transaction.get('reference', ''),
                    'type_ecriture': 'depense' if montant_ttc < 0 else 'recette', # Ou utiliser la logique de map_type_transaction_to_ecriture
                    'tva_taux': taux_tva, # Sauvegarder le taux fourni
                    # 🔥 CALCULER LE MONTANT DE LA TVA POUR CETTE LIGNE
                    'tva_montant': montant_ttc - montant_htva_calcule if taux_tva > 0 else Decimal('0'),
                    'utilisateur_id': current_user.id,
                    'statut': 'pending',
                    'devise': 'CHF',
                    'type_ecriture_comptable' : 'principale'
                }

                if g.models.ecriture_comptable_model.create(data):
                    ecriture_id = g.models.ecriture_comptable_model.last_insert_id
                    g.models.ecriture_comptable_model.link_ecriture_to_transaction(transaction_id, ecriture_id, current_user.id)
                    success_count += 1
                else:
                    flash(f"Erreur lors de la création de l'écriture {i+1}", "error")

            except Exception as e:
                logging.error(f"Erreur création écritures multiples (ligne {i+1}): {e}")
                flash(f"Erreur lors de la création de l'écriture {i+1}: {str(e)}", "error")

        if success_count > 0:
            flash(f"{success_count} écriture(s) créée(s) avec succès avec statut 'En attente'", "success")
        else:
            flash("Aucune écriture n'a pu être créée", "error")

    except Exception as e:
        logging.error(f"Erreur création écritures multiples: {e}")
        flash(f"Erreur lors de la création des écritures: {str(e)}", "error")

    # 🔥 PRÉSERVER LES FILTRES
    compte_id = request.form.get('compte_id', type=int)
    date_from = request.form.get('date_from')
    date_to = request.form.get('date_to')
    statut_comptable = request.form.get('statut_comptable')
    return redirect(url_for('banking.transactions_sans_ecritures',
                           compte_id=compte_id,
                           date_from=date_from,
                           date_to=date_to,
                           statut_comptable=statut_comptable))
# 🔥 NOUVELLES ROUTES POUR LA GESTION DES ÉCRITURES SECONDAIRES

@bp.route('/comptabilite/ecritures/<int:ecriture_id>/secondaires')
@login_required
def details_ecriture_secondaires(ecriture_id):
    """Affiche le détail d'une écriture avec ses écritures secondaires"""
    ecriture_complete = g.models.ecriture_comptable_model.get_ecriture_avec_secondaires(ecriture_id, current_user.id)
    
    if not ecriture_complete:
        flash('Écriture non trouvée ou non autorisée', 'danger')
        return redirect(url_for('banking.liste_ecritures'))
    
    return render_template('comptabilite/detail_ecriture_secondaires.html',
        ecriture=ecriture_complete['principale'],
        ecritures_secondaires=ecriture_complete['secondaires'])

@bp.route('/comptabilite/ecritures/secondaire/<int:ecriture_secondaire_id>')
@login_required
def detail_ecriture_secondaire(ecriture_secondaire_id):
    """Affiche le détail d'une écriture secondaire"""
    ecriture_secondaire = g.models.ecriture_comptable_model.get_by_id(ecriture_secondaire_id)
    ecriture_principale = None
    
    if ecriture_secondaire and ecriture_secondaire['utilisateur_id'] == current_user.id:
        if ecriture_secondaire.get('ecriture_principale_id'):
            ecriture_principale = g.models.ecriture_comptable_model.get_ecriture_principale(
                ecriture_secondaire_id, current_user.id
            )
    
    if not ecriture_secondaire or ecriture_secondaire['utilisateur_id'] != current_user.id:
        flash('Écriture non trouvée ou non autorisée', 'danger')
        return redirect(url_for('banking.liste_ecritures'))
    
    return render_template('comptabilite/detail_ecriture_secondaire.html',
        ecriture_secondaire=ecriture_secondaire,
        ecriture_principale=ecriture_principale)

@bp.route('/api/ecritures/<int:categorie_id>/info-complementaire')
@login_required
def api_info_categorie_complementaire(categorie_id):
    """API pour récupérer les informations de catégorie complémentaire (AJAX)"""
    try:
        # Récupérer les catégories complémentaires configurées
        categories_complementaires = g.models.categorie_comptable_model.get_categories_avec_complementaires(current_user.id)
        
        categorie_info = None
        for cat in categories_complementaires:
            if cat['id'] == categorie_id and cat.get('categorie_complementaire_id'):
                categorie_info = {
                    'a_complement': True,
                    'type_complement': cat.get('type_complement', 'tva'),
                    'taux': float(cat.get('taux', 0)),
                    'categorie_complementaire_nom': cat.get('comp_nom', ''),
                    'categorie_complementaire_numero': cat.get('comp_numero', '')
                }
                break
        
        return jsonify({
            'success': True,
            'categorie_info': categorie_info or {'a_complement': False}
        })
    except Exception as e:
        logging.error(f"Erreur API info catégorie complémentaire: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@bp.route('/comptabilite/ecritures/nouvelle/from_transactions', methods=['GET', 'POST'])
@login_required
def nouvelle_ecriture_from_transactions():
    """Crée des écritures pour TOUTES les transactions filtrées"""

    def map_type_transaction_to_ecriture(type_transaction):
        """
        Convertit le type de transaction bancaire en type d'écriture comptable.
        """
        mapping = {
            'depot': 'recette',
            'retrait': 'depense',
            'transfert_entrant': 'recette',
            'transfert_sortant': 'depense',
            'transfert_externe': 'depense',
            'recredit_annulation': 'depense',
            'transfert_compte_vers_sous': 'depense',
            'transfert_sous_vers_compte': 'recette',
        }
        return mapping.get(type_transaction, 'depense')  # 'depense' par défaut en cas d'inconnu

    if request.method == 'POST':
        try:
            # Récupérer les listes des champs du formulaire
            transaction_ids = request.form.getlist('transaction_ids[]')
            dates = request.form.getlist('date_ecriture[]')
            # 🔥 ON NE DOIT PLUS SE BASER SUR CE 'type_ecriture[]' du formulaire
            # types = request.form.getlist('type_ecriture[]') # Valeurs du formulaire : 'debit', 'credit'
            comptes_ids = request.form.getlist('compte_bancaire_id[]')
            categories_ids = request.form.getlist('categorie_id[]')
            montants = request.form.getlist('montant[]')
            tva_taux = request.form.getlist('tva_taux[]')
            descriptions = request.form.getlist('description[]')
            references = request.form.getlist('reference[]')
            statuts = request.form.getlist('statut[]')
            contacts_ids = request.form.getlist('id_contact[]') # Peut contenir des chaînes vides

            if not transaction_ids:
                flash("Aucune transaction à traiter", "warning")
                return redirect(url_for('banking.transactions_sans_ecritures'))

            logging.info(f'voici les transactions : {transaction_ids}')
            success_count = 0
            errors = []

            # 🔥 RÉCUPÉRER LES TRANSACTIONS ORIGINALES POUR AVOIR LEUR type_transaction
            # On suppose que les IDs dans transaction_ids[] correspondent à des transactions existantes
            transactions_originales = []
            for tid in transaction_ids:
                trans = g.models.transaction_financiere_model.get_transaction_with_ecritures_total(int(tid), current_user.id)
                if trans:
                    transactions_originales.append(trans)
                else:
                    # Si une transaction n'est pas trouvée, on ne peut pas continuer
                    errors.append(f"Transaction {tid} introuvable ou non autorisée.")
                    break
            if errors:
                for error in errors:
                    flash(error, "error")
                return redirect(url_for('banking.nouvelle_ecriture_from_transactions', compte_id=request.args.get('compte_id'), date_from=request.args.get('date_from'), date_to=request.args.get('date_to')))

            for i in range(len(transaction_ids)):
                try:
                    if not all([dates[i], comptes_ids[i], categories_ids[i], montants[i]]):
                        errors.append(f"Transaction {i+1}: Champs obligatoires manquants")
                        continue

                    # 🔥 RÉCUPÉRER LE type_transaction DE LA TRANSACTION ORIGINALE
                    type_transaction_bancaire = transactions_originales[i]['type_transaction']
                    # 🔥 MAPPER CE type_transaction VERS LE type_ecriture COMPTABLE
                    type_ecriture_db = map_type_transaction_to_ecriture(type_transaction_bancaire)

                    # Récupérer l'ID du contact, en gérant les chaînes vides
                    contact_id_val = None
                    if i < len(contacts_ids) and contacts_ids[i]: # Gestion des chaînes vides
                        contact_id_val = int(contacts_ids[i])

                    montant_ttc = Decimal(str(montants[i]))
                    taux_tva = Decimal(str(tva_taux[i])) if i < len(tva_taux) and tva_taux[i] else Decimal('0')

                    # 🔥 CALCUL DU MONTANT HTVA CÔTÉ SERVEUR (comme dans nouvelle_ecriture_from_selected)
                    if taux_tva > 0:
                        montant_htva_calcule = montant_ttc / (1 + taux_tva / Decimal('100'))
                    else:
                        montant_htva_calcule = montant_ttc # Si pas de TVA, HTVA = TTC

                    data = {
                        'date_ecriture': dates[i],
                        'compte_bancaire_id': int(comptes_ids[i]),
                        'categorie_id': int(categories_ids[i]),
                        'montant': montant_ttc, # Montant TTC
                        'montant_htva': montant_htva_calcule, # Montant HTVA calculé
                        'description': descriptions[i] if i < len(descriptions) and descriptions[i] else '',
                        'id_contact': contact_id_val, # Utiliser la valeur traitée
                        'reference': references[i] if i < len(references) and references[i] else '',
                        # 🔥 UTILISER LA VALEUR CONVERTIE À PARTIR DE type_transaction
                        'type_ecriture': type_ecriture_db,
                        'tva_taux': taux_tva, # Le taux fourni
                        'utilisateur_id': current_user.id,
                        'statut': statuts[i] if i < len(statuts) and statuts[i] else 'pending',
                        'devise': 'CHF', # Ajout de la devise
                        'type_ecriture_comptable': 'principale' # Ajout du type d'écriture comptable
                    }

                    # 🔥 CORRECTION : Calcul TVA cohérent (comme dans nouvelle_ecriture_from_selected)
                    if data['tva_taux'] > 0:
                        data['tva_montant'] = data['montant'] - data['montant_htva']
                    else:
                        data['tva_montant'] = Decimal('0')

                    if g.models.ecriture_comptable_model.create(data):
                        ecriture_id = g.models.ecriture_comptable_model.last_insert_id
                        # Lier l'écriture à la transaction
                        g.models.ecriture_comptable_model.link_ecriture_to_transaction(int(transaction_ids[i]), ecriture_id, current_user.id) # Convertir en int
                        success_count += 1
                    else:
                        errors.append(f"Transaction {i+1}: Erreur lors de l'enregistrement dans le modèle")

                except (ValueError, IndexError) as ve: # Gestion des erreurs de conversion et d'index
                    logging.error(f"Erreur conversion/index pour la transaction {i+1} (ID {transaction_ids[i]}): {ve}")
                    errors.append(f"Transaction {i+1} (ID {transaction_ids[i]}): Données invalides - {ve}")
                    continue # Passer à la transaction suivante
                except Exception as e: # Gestion des autres erreurs
                    logging.error(f"Erreur inattendue pour la transaction {i+1} (ID {transaction_ids[i]}): {e}")
                    errors.append(f"Transaction {i+1} (ID {transaction_ids[i]}): Erreur interne - {e}")
                    continue # Passer à la transaction suivante

            # Gestion des messages de retour
            if errors:
                for error in errors:
                    flash(error, "error") # Utilisez "error" pour les erreurs critiques

            if success_count > 0:
                flash(f"{success_count} écriture(s) créée(s) avec succès pour {len(transaction_ids)} transaction(s)", "success")
                # REDIRECTION CORRIGEE : Utiliser la bonne route pour revenir à la liste filtrée
                return redirect(url_for('banking.transactions_sans_ecritures',
                                    compte_id=request.args.get('compte_id'),
                                    date_from=request.args.get('date_from'),
                                    date_to=request.args.get('date_to')))
            else:
                # Si aucune écriture n'a été créée avec succès, mais qu'il y avait des transactions à traiter
                flash("Aucune écriture n'a pu être créée", "error")
                # Retourner vers la page des transactions sans écritures pour réessayer
                return redirect(url_for('banking.nouvelle_ecriture_from_transactions',
                                    compte_id=request.args.get('compte_id'),
                                    date_from=request.args.get('date_from'),
                                    date_to=request.args.get('date_to')))

        except Exception as e:
            logging.error(f"Erreur générale lors de la création des écritures: {e}")
            flash(f"Erreur critique lors de la création des écritures: {str(e)}", "error")
            return redirect(url_for('banking.transactions_sans_ecritures'))

    # PARTIE GET - Afficher le formulaire pour TOUTES les transactions filtrées
    compte_id = request.args.get('compte_id', type=int) # Correction : type=int
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    # Récupérer les transactions avec les mêmes filtres
    transactions = g.models.transaction_financiere_model.get_transactions_sans_ecritures(
        current_user.id,
        date_from=date_from,
        date_to=date_to
    )
    logging.info(f'Filtrage des transactions pour compte_id={compte_id}, date_from={date_from}, date_to={date_to}')
    logging.info(f' route nouvelle_ecriture_from_transaction Transactions récupérées avant filtrage: {len(transactions)}') # Info plus claire
    if compte_id is not None: # Correction : Tester None explicitement
        transactions = [t for t in transactions if t.get('compte_bancaire_id') == compte_id]

    if not transactions:
        flash("Aucune transaction à comptabiliser avec les filtres actuels", "warning")
        return redirect(url_for('banking.transactions_sans_ecritures'))

    # Récupérer les données pour les formulaires
    # Assurez-vous que ces fonctions existent et retournent les bonnes données
    comptes = g.models.compte_model.get_all_accounts()
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    contacts = g.models.contact_model.get_all(current_user.id)

    # 🔥 NOUVEAU : Récupérer les catégories avec écritures secondaires (comme dans nouvelle_ecriture_from_selected)
    categories_avec_complementaires = g.models.categorie_comptable_model.get_categories_avec_complementaires(current_user.id)
    categories_avec_complementaires_ids = set()
    for cat in categories_avec_complementaires:
        if cat.get('categorie_complementaire_id'):
            categories_avec_complementaires_ids.add(cat['id'])

    return render_template('comptabilite/creer_ecritures_groupées.html',
                        transactions=transactions,
                        comptes=comptes,
                        categories=categories,
                        categories_avec_complementaires_ids=categories_avec_complementaires_ids, # 🔥 PASSER CETTE INFO AU TEMPLATE
                        contacts=contacts,
                        compte_id=compte_id, # Passer les filtres au template
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
    if nouveau_statut not in ['pending', 'validée', 'rejetée', 'supprimée']:
        flash('Statut invalide', 'danger')
        return redirect(url_for('banking.liste_ecritures'))

    # 🔥 CORRECTION : Appeler la méthode sur le bon modèle
    if g.models.ecriture_comptable_model.update_statut(ecriture_id, current_user.id, nouveau_statut):
        flash(f'Statut modifié en "{nouveau_statut}"', 'success')
    else:
        flash('Erreur lors de la modification du statut', 'danger')
    # 🔥 CORRECTION : Retirer le paramètre incorrect de redirect
    return redirect(url_for('banking.liste_ecritures')) # Ne pas passer contacts=contacts ici


@bp.route('/comptabilite/ecritures/<int:ecriture_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_ecriture(ecriture_id):
    """Modifie une écriture comptable existante"""
    ecriture = g.models.ecriture_comptable_model.get_by_id(ecriture_id)

    if not ecriture or ecriture['utilisateur_id'] != current_user.id:
        flash('Écriture introuvable ou non autorisée', 'danger')
        return redirect(url_for('banking.liste_ecritures'))
    ecritures_secondaires = []
    if ecriture.get('type_ecriture_comptable') == 'principale' or not ecriture.get('ecriture_principale_id'):
        ecritures_secondaires = g.models.ecriture_comptable_model.get_ecritures_complementaires(ecriture_id, current_user.id)
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
            'montant_htva': Decimal(request.form.get('montant_htva', request.form['montant'])),
            'description': request.form.get('description', ''),
            'id_contact': id_contact,  # Utiliser la valeur convertie
            'reference': request.form.get('reference', ''),
            'type_ecriture': request.form['type_ecriture'],
            'type_ecriture_comptable': request.form.get('type_ecriture_comptable', ''),
            'tva_taux': Decimal(request.form['tva_taux']) if request.form.get('tva_taux') else None,
            'utilisateur_id': current_user.id,
            'statut': request.form.get('statut', 'pending'),
            'devise': 'CHF'
        } 
            if data['tva_taux']:
                if data['montant_htva'] != data['montant']:
                    data['tva_montant'] = data['montant'] - data['montant_htva']
                else:
                    data['montant_htva'] = data['montant'] / (1 + data['tva_taux'] / 100)
                    data['tva_montant'] = data['montant'] - data['montant_htva']
            else:
                data['tva_montant'] = 0
                data['montant_htva'] = data['montant']

            if g.models.ecriture_comptable_model.update(ecriture_id, data):
                flash('Écriture mise à jour avec succès', 'success')
                return redirect(url_for('banking.liste_ecritures'))
            else:
                flash('Erreur lors de la mise à jour', 'danger')
        except Exception as e:
            flash(f'Erreur: {str(e)}', 'danger')
    comptes = g.models.compte_model.get_by_user_id(current_user.id)
    categories = g.models.categorie_comptable_model.get_all_categories(current_user.id)
    categories_avec_complementaires = g.models.categorie_comptable_model.get_categories_avec_complementaires(current_user.id)
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
                        categories_avec_complementaires=categories_avec_complementaires,
                        ecriture=ecriture,
                        statuts_disponibles=statuts_disponibles,
                        transaction_data={},
                        transaction_id=None,
                        # CORRECTION: Utiliser 'contacts' au lieu de 'Contacts'
                        contacts=contacts)

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

@bp.route('/comptabilite/ecritures/detail/<string:type>/<categorie_id>')
@login_required
def detail_ecritures_categorie(type, categorie_id):
    """Affiche le détail des écritures d'une catégorie avec leurs écritures secondaires"""
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
        
        # Récupérer les écritures secondaires pour chaque écriture principale
        ecritures_avec_secondaires = []
        for ecriture in ecritures:
            ecriture_dict = dict(ecriture)
            
            # Si c'est une écriture principale, récupérer ses écritures secondaires
            if ecriture_dict.get('type_ecriture_comptable') == 'principale' or not ecriture_dict.get('ecriture_principale_id'):
                secondaires = g.models.ecriture_comptable_model.get_ecritures_complementaires(
                    ecriture_dict['id'], 
                    current_user.id
                )
                ecriture_dict['ecritures_secondaires'] = secondaires
                ecriture_dict['has_secondaires'] = len(secondaires) > 0
            else:
                ecriture_dict['ecritures_secondaires'] = []
                ecriture_dict['has_secondaires'] = False
            
            ecritures_avec_secondaires.append(ecriture_dict)
        
        logging.info(f"INFO: {len(ecritures_avec_secondaires)} écritures récupérées pour le détail")
        
        return render_template('comptabilite/detail_ecritures.html',
                            ecritures=ecritures_avec_secondaires,
                            total=total,
                            titre=titre,
                            annee=annee,
                            type=type,
                            categorie_id=categorie_id)
    
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


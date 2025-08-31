#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Routes Flask optimisées pour la gestion bancaire avec Flask-Login
"""

from flask import render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import login_required, current_user
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, date
from calendar import monthrange
from models import DatabaseManager, Banque, ComptePrincipal, SousCompte, Transaction, StatistiquesBancaires, Transfert, PlanComptable, EcritureComptable, HeureTravail, Salaire, SyntheseHebdomadaire, SyntheseMensuelle, Contrat
from io import StringIO
import csv
import random
from collections import defaultdict

def init_banking_routes(app, db_config):
    """Initialise les routes bancaires dans l'application Flask"""
    
    # Initialisation des modèles
    db_manager = DatabaseManager(db_config)
    banque_model = Banque(db_manager)
    compte_model = ComptePrincipal(db_manager)
    sous_compte_model = SousCompte(db_manager)
    transaction_model = Transaction(db_manager)
    transfert_model = Transfert(db_manager)
    stats_model = StatistiquesBancaires(db_manager)
    plan_comptable_model = PlanComptable(db_manager)
    ecriture_comptable_model = EcritureComptable(db_manager)

    # ---- Fonctions utilitaires ----
    def get_comptes_utilisateur(user_id):
        """Retourne les comptes avec sous-comptes et soldes"""
        comptes = compte_model.get_by_user_id(user_id)
        for compte in comptes:
            compte['sous_comptes'] = sous_compte_model.get_by_compte_principal_id(compte['id'])
            compte['solde_total'] = compte_model.get_solde_total_avec_sous_comptes(compte['id'])
        return comptes

    # ---- ROUTES ----
    #@app.route('/banking')
    #@login_required
    #def banking_dashboard():
    #    user_id = current_user.id
    #    stats = stats_model.get_resume_utilisateur(user_id)
    #    repartition = stats_model.get_repartition_par_banque(user_id)
    #    comptes = get_comptes_utilisateur(user_id)
    #    
    #    return render_template('banking/dashboard.html', 
    #                           comptes=comptes, stats=stats, repartition=repartition)
    #
        # Modifier la route du dashboard pour inclure les stats comptables
    @app.route('/banking')
    @login_required
    def banking_dashboard():
        user_id = current_user.id
        stats = stats_model.get_resume_utilisateur(user_id)
        repartition = stats_model.get_repartition_par_banque(user_id)
        comptes = get_comptes_utilisateur(user_id)
        
        # Ajout des stats comptables
        ecriture_model = EcritureComptable(db_manager)
        now = datetime.now()
        first_day = now.replace(day=1)
        last_day = (first_day.replace(month=first_day.month % 12 + 1, year=first_day.year + first_day.month // 12) - timedelta(days=1))
        
        stats_comptables = ecriture_model.get_stats_by_categorie(
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

    @app.route('/banques', methods=['GET'])
    @login_required
    def liste_banques():
        banque_model = Banque(db_manager)
        banques = banque_model.get_all()
        return render_template('banking/liste.html', banques=banques)

    @app.route('/banques/nouvelle', methods=['GET', 'POST'])
    @login_required
    def creer_banque():
        banque_model = Banque(db_manager)

        if request.method == 'POST':
            nom = request.form.get('nom')
            code_banque = request.form.get('code_banque')
            pays = request.form.get('pays')
            couleur = request.form.get('couleur')
            site_web = request.form.get('site_web')
            logo_url = request.form.get('logo_url')

            if nom and code_banque:
                success = banque_model.create_banque(nom, code_banque, pays, couleur, site_web, logo_url)
                if success:
                    flash('Banque créée avec succès !', 'success')
                    return redirect(url_for('liste_banques'))
                else:
                    flash('Erreur lors de la création de la banque.', 'danger')
            else:
                flash('Veuillez remplir au moins le nom et le code banque.', 'warning')

        return render_template('banking/creer.html')
    
    @app.route('/banques/<int:banque_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_banque(banque_id):
        banque_model = Banque(db_manager)
        banque = banque_model.get_by_id(banque_id)
        if not banque:
            flash("Banque introuvable.", "danger")
            return redirect(url_for('liste_banques'))

        if request.method == 'POST':
            nom = request.form.get('nom')
            code_banque = request.form.get('code_banque')
            pays = request.form.get('pays')
            couleur = request.form.get('couleur')
            site_web = request.form.get('site_web')
            logo_url = request.form.get('logo_url')

            success = banque_model.update_banque(banque_id, nom, code_banque, pays, couleur, site_web, logo_url)
            if success:
                flash("Banque modifiée avec succès.", "success")
                return redirect(url_for('liste_banques'))
            else:
                flash("Erreur lors de la modification.", "danger")

        return render_template('banking/edit.html', banque=banque)
    @app.route('/banques/<int:banque_id>/delete', methods=['POST'])
    @login_required
    def delete_banque(banque_id):
        banque_model = Banque(db_manager)
        success = banque_model.delete_banque(banque_id)
        if success:
            flash("Banque supprimée (désactivée) avec succès.", "success")
        else:
            flash("Erreur lors de la suppression.", "danger")
        return redirect(url_for('liste_banques'))
        

    @app.route('/banking/compte/<int:compte_id>')
    @login_required
    def banking_compte_detail(compte_id):
        user_id = current_user.id
        compte = compte_model.get_by_id(compte_id)
        if not compte or compte['utilisateur_id'] != user_id:
            flash('Compte non trouvé ou non autorisé', 'error')
            return redirect(url_for('banking_dashboard'))

        # Gestion de la période sélectionnée
        periode = request.args.get('periode', 'mois')  # Valeurs possibles: mois, trimestre, annee
        
        # Calcul des dates selon la période
        maintenant = datetime.now()
        
        if periode == 'annee':
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
        
        # Récupération des transactions
        transactions_periode = transaction_model.get_by_compte_id(
            compte_id=compte_id,
            user_id=user_id,
            date_from=debut.strftime('%Y-%m-%d'),
            date_to=fin.strftime('%Y-%m-%d')
        )
        print(f"Transactions trouvées: {len(transactions_periode)}")
        
        # Récupération des transferts - NOUVEAU SCHÉMA
        # Il faut récupérer les transferts où ce compte est source OU destination
        transferts_periode = []
        
        # Transferts où ce compte est la source (sortants)
        transferts_sortants = transfert_model.get_transferts_by_source_compte(
            compte_id=compte_id,
            date_from=debut.strftime('%Y-%m-%d'),
            date_to=fin.strftime('%Y-%m-%d')
        )
        
        # Transferts où ce compte est la destination (entrants)
        transferts_entrants = transfert_model.get_transferts_by_dest_compte(
            compte_id=compte_id,
            date_from=debut.strftime('%Y-%m-%d'),
            date_to=fin.strftime('%Y-%m-%d')
        )
        
        transferts_periode = transferts_sortants + transferts_entrants
        print(f"Transferts trouvés: {len(transferts_periode)}")
        
        # Fusionner les transactions et transferts pour l'affichage
        mouvements = []
        
        # Ajouter les transactions
        for t in transactions_periode:
            mouvements.append({
                'type': 'transaction',
                'id': t['id'],
                'type_mouvement': t['type_transaction'],
                'montant': Decimal(str(t['montant'])),
                'description': t['description'],
                'date': t['date_transaction'],
                'sous_compte': t.get('nom_sous_compte'),
                'sous_compte_destination': t.get('nom_sous_compte_destination'),
                'reference': f"TXN-{t['id']}"
            })
        
        # Ajouter les transferts - ADAPTÉ AU NOUVEAU SCHÉMA
        for t in transferts_periode:
            # Déterminer si c'est sortant ou entrant selon le nouveau schéma
            est_sortant = False
            est_entrant = False
            
            # Vérifier si ce compte est la source
            if (t.get('compte_source_id') == 'compte_principal' and t.get('source_id') == compte_id):
                est_sortant = True
            elif (t.get('compte_source_id') == 'sous_compte'):
                # Vérifier si le sous-compte appartient à ce compte principal
                sous_compte_source = sous_compte_model.get_by_id(t.get('source_id'))
                if sous_compte_source and sous_compte_source.get('compte_principal_id') == compte_id:
                    est_sortant = True
            
            # Vérifier si ce compte est la destination
            if (t.get('destination_type') == 'compte_principal' and t.get('compte_dest_id') == compte_id):
                est_entrant = True
            elif (t.get('destination_type') == 'sous_compte'):
                # Vérifier si le sous-compte de destination appartient à ce compte principal
                sous_compte_dest = sous_compte_model.get_by_id(t.get('compte_dest_id'))
                if sous_compte_dest and sous_compte_dest.get('compte_principal_id') == compte_id:
                    est_entrant = True
            
            # Déterminer le type de mouvement et le montant
            if est_sortant and not est_entrant:
                type_mouvement = 'transfert_sortant'
                montant = -Decimal(str(t['montant']))
                description = f"Vers {t.get('nom_dest', 'Compte externe')}"
            elif est_entrant and not est_sortant:
                type_mouvement = 'transfert_entrant'
                montant = Decimal(str(t['montant']))
                # Récupérer le nom du compte source
                if t.get('compte_source_id') == 'compte_principal':
                    compte_source = compte_model.get_by_id(t.get('source_id'))
                    nom_source = compte_source.get('nom_compte', 'Compte externe') if compte_source else 'Compte externe'
                else:
                    sous_compte_source = sous_compte_model.get_by_id(t.get('source_id'))
                    nom_source = sous_compte_source.get('nom_sous_compte', 'Sous-compte externe') if sous_compte_source else 'Sous-compte externe'
                description = f"Depuis {nom_source}"
            else:
                # Transfert interne (même compte principal)
                type_mouvement = 'transfert_interne'
                montant = Decimal('0')  # Neutre pour les transferts internes
                description = f"Transfert interne"
            
            mouvements.append({
                'type': 'transfert',
                'id': t['id'],
                'type_mouvement': type_mouvement,
                'montant': montant,
                'description': t.get('commentaire', description),
                'date_transfert': t['date_transfert'],
                'compte_source': t.get('nom_compte_source'),
                'compte_dest': t.get('nom_dest'),
                'sous_compte_source': t.get('nom_sous_compte_source'),
                'sous_compte_dest': t.get('nom_sous_compte_dest'),
                'reference': f"TFR-{t['id']}",
                'statut': t.get('statut', 'completed'),
                'est_externe': not (est_sortant and est_entrant)
            })
        
        # Trier les mouvements par date (du plus récent au plus ancien)
        mouvements.sort(key=lambda x: x['date_transfert'], reverse=True)
        print(mouvements)
        # Limiter à 20 pour l'affichage récent
        mouvements_recents = mouvements[:20]
        
        # Calcul des totaux pour la période
        total_recettes = Decimal('0')
        total_depenses = Decimal('0')
        
        for m in mouvements:
            if m['montant'] > 0:
                total_recettes += m['montant']
            elif m['montant'] < 0:
                total_depenses += abs(m['montant'])
        
        # Récupération des données existantes
        sous_comptes = sous_compte_model.get_by_compte_principal_id(compte_id)
        solde_total = compte_model.get_solde_total_avec_sous_comptes(compte_id)
        
        # Préparation des données pour le template
        tresorerie_data = {
            'labels': ['Recettes', 'Dépenses'],
            'datasets': [{
                'data': [float(total_recettes), float(total_depenses)],
                'backgroundColor': ['#28a745', '#dc3545']
            }]
        }
        
        ecriture_model = EcritureComptable(db_manager)
        ecritures_non_liees = ecriture_model.get_ecritures_non_synchronisees(
            compte_id=compte_id,
            user_id=current_user.id
        )
        
        return render_template('banking/compte_detail.html',
                            compte=compte,
                            sous_comptes=sous_comptes,
                            mouvements=mouvements_recents,
                            mouvements_complets=mouvements,  # Pour d'éventuels exports
                            solde_total=solde_total,
                            tresorerie_data=tresorerie_data,
                            periode_selectionnee=periode,
                            libelle_periode=libelle_periode,
                            total_recettes=total_recettes,
                            total_depenses=total_depenses,
                            ecritures_non_liees=ecritures_non_liees,
                            transferts_sortants=transferts_sortants,
                            transferts_entrants=transferts_entrants,
                            today=date.today())
    @app.route('/banking/sous-compte/<int:sous_compte_id>')
    @login_required
    def banking_sous_compte_detail(sous_compte_id):
        user_id = current_user.id
        sous_compte = sous_compte_model.get_by_id(sous_compte_id)
        if not sous_compte:
            flash('Sous-compte introuvable', 'error')
            return redirect(url_for('banking_dashboard'))

    # Vérifie que le sous-compte appartient bien à l'utilisateur
        compte_principal = compte_model.get_by_id(sous_compte['compte_principal_id'])
        if not compte_principal or compte_principal['utilisateur_id'] != user_id:
            flash('Sous-compte non autorisé', 'error')
            return redirect(url_for('banking_dashboard'))

        transferts = transfert_model.get_by_sous_compte_id(sous_compte_id, 20)
        solde = sous_compte_model.get_solde(sous_compte_id)
        transactions = transaction_model.get_by_sous_compte_id(sous_compte_id, user_id, limit=20)


        #        Ajout du pourcentage calculé
        if sous_compte['objectif_montant'] and sous_compte['objectif_montant'] > 0:
            sous_compte['pourcentage_objectif'] = round((sous_compte['solde'] / sous_compte['objectif_montant']) * 100, 1)
        else:
            sous_compte['pourcentage_objectif'] = 0
        return render_template(
            'banking/sous_compte_detail.html',
            sous_compte=sous_compte,
            compte=compte_principal,
            transferts=transferts,
            transactions=transactions,
            solde=solde
        )


    @app.route('/banking/compte/nouveau', methods=['GET', 'POST'])
    @login_required
    def banking_nouveau_compte():
        if request.method == 'POST':
            try:
                data = {
                    'utilisateur_id': current_user.id,
                    'banque_id': int(request.form['banque_id']),
                    'nom_compte': request.form['nom_compte'].strip(),
                    'numero_compte': request.form['numero_compte'].strip(),
                    'iban': request.form.get('iban', '').strip(),
                    'bic': request.form.get('bic', '').strip(),
                    'type_compte': request.form['type_compte'],
                    'solde': Decimal(request.form.get('solde', '0')),
                    'devise': request.form.get('devise', 'CHF'),
                    'date_ouverture': datetime.strptime(
                        request.form['date_ouverture'], '%Y-%m-%d'
                    ).date() if request.form.get('date_ouverture') else None
                }
                if compte_model.create(data):
                    flash(f'Compte "{data["nom_compte"]}" créé avec succès!', 'success')
                    return redirect(url_for('banking_dashboard'))
                flash('Erreur lors de la création du compte', 'error')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'error')
        
        banques = banque_model.get_all()
        return render_template('banking/nouveau_compte.html', banques=banques)

    @app.route('/banking/sous-compte/nouveau/<int:compte_id>', methods=['GET', 'POST'])
    @login_required
    def banking_nouveau_sous_compte(compte_id):
        user_id = current_user.id
        compte = compte_model.get_by_id(compte_id)
        if not compte or compte['utilisateur_id'] != user_id:
            flash('Compte principal non trouvé ou non autorisé', 'error')
            return redirect(url_for('banking_dashboard'))
        
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
                if sous_compte_model.create(data):
                    flash(f'Sous-compte "{data["nom_sous_compte"]}" créé avec succès!', 'success')
                    return redirect(url_for('banking_compte_detail', compte_id=compte_id))
                flash('Erreur lors de la création du sous-compte', 'error')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'error')
        
        return render_template('banking/nouveau_sous_compte.html', compte=compte)


    @app.route('/banking/transaction', methods=['GET', 'POST'])
    @login_required
    def banking_transaction():
        user_id = current_user.id
        comptes = get_comptes_utilisateur(user_id)

        if request.method == 'POST':
            try:
                compte_id = int(request.form['compte_id'])
                type_transaction = request.form['type_transaction'].lower()
                montant = Decimal(request.form['montant'])
                description = request.form.get('description', '').strip()

                if montant <= 0:
                    flash('Le montant doit être positif', 'error')
                    return redirect(url_for('banking_transaction'))

                compte = compte_model.get_by_id(compte_id)
                if not compte:
                    flash('Compte introuvable', 'error')
                    return redirect(url_for('banking_transaction'))

                solde_actuel = compte.get('solde')
                if not isinstance(solde_actuel, Decimal):
                    flash('Solde non disponible ou format incorrect', 'error')
                    return redirect(url_for('banking_transaction'))

                if type_transaction == 'depot':
                    solde_apres = solde_actuel + montant
                elif type_transaction == 'retrait':
                    solde_apres = solde_actuel - montant
                else:
                    flash(f'Type de transaction invalide : {type_transaction}', 'error')
                    return redirect(url_for('banking_transaction'))

                if type_transaction == 'retrait' and solde_apres < Decimal('0'):
                    flash(
                        f"Erreur : solde insuffisant ! Solde actuel : {solde_actuel:.2f} CHF, "
                        f"solde après tentative : {solde_apres:.2f} CHF",
                        'error'
                    )
                    return redirect(url_for('banking_transaction'))

                success = transaction_model.create_depot_retrait(compte_id, montant, type_transaction, description)
                if success:
                    # si create_depot_retrait fait déjà update_solde, inutile de le refaire
                    flash(
                        f"{type_transaction.capitalize()} de {montant:.2f} CHF effectué ! "
                        f"Solde avant : {solde_actuel:.2f} CHF, nouveau solde : {solde_apres:.2f} CHF",
                        'success'
                    )
                    return redirect(url_for('banking_compte_detail', compte_id=compte_id))
                else:
                    flash(
                        f"Erreur lors de la transaction. Solde actuel : {solde_actuel:.2f} CHF, "
                        f"solde prévu : {solde_apres:.2f} CHF",
                        'error'
                    )
                    return redirect(url_for('banking_transaction'))

            except Exception as e:
                flash(f'Erreur : {e}', 'error')
                return redirect(url_for('banking_transaction'))

        # GET ou en cas d’erreur on rend la page avec les comptes
        return render_template('banking/transaction.html', comptes=comptes)
    
    @app.route('/banking/edit_transaction', methods=['POST'])
    @login_required
    def edit_transaction():
        user_id = current_user.id
        transaction_id = request.form.get('transaction_id')
        data = {
            'type_transaction': request.form['type_transaction'],
            'montant': float(request.form['montant']),
            'description': request.form.get('description', ''),
            'reference': request.form.get('reference', ''),
            'compte_principal_id': request.form.get('compte_id'),
            'sous_compte_id': request.form.get('sous_compte_id') or None,
            'compte_destination_id': request.form.get('compte_dest_id') or None,
            'sous_compte_destination_id': request.form.get('sous_compte_dest_id') or None,
            'utilisateur_id': user_id
        }

        if transaction_id:  # Mise à jour
            success = transaction_model.update(transaction_id, data)
        else:  # Création
            success = transaction_model.create(data)

        if success:
            flash('Transaction enregistrée avec succès', 'success')
        else:
            flash('Erreur lors de l\'enregistrement de la transaction', 'danger')

        return redirect(url_for('liste_transactions'))



    @app.route("/transfert", methods=["GET", "POST"])
    @login_required
    def banking_transfert():
        user_id = current_user.id
        compte_model = ComptePrincipal(db_manager)
        comptes = compte_model.get_by_user_id(user_id)
        sous_comptes = []
        for c in comptes:
            sous_comptes += sous_compte_model.get_by_compte_principal_id(c['id'])

        all_comptes = [c for c in ComptePrincipal.get_all_accounts(db_manager) if c['utilisateur_id'] != user_id]

        if request.method == "POST":
            step = request.form.get('step')

            # Étape 1 : choix type transfert
            if step == 'select_type':
                transfert_type = request.form.get('transfert_type')
                if not transfert_type:
                    flash("Veuillez sélectionner un type de transfert", "danger")
                    return redirect(url_for("banking_transfert"))
                return render_template(
                    "banking/transfert.html",
                    comptes=comptes,
                    sous_comptes=sous_comptes,
                    all_comptes=all_comptes,
                    transfert_type=transfert_type,
                    now=datetime.now()
                )

            # Étape 2 : exécution transfert
            elif step == 'confirm':
                transfert_type = request.form.get('transfert_type')
                if not transfert_type:
                    flash("Type de transfert manquant", "danger")
                    return redirect(url_for("banking_transfert"))

                try:
                    # ✅ Montant
                    montant_str = request.form.get('montant', '').replace(',', '.').strip()
                    try:
                        montant = Decimal(montant_str)
                        if montant <= 0:
                            flash("Le montant doit être positif", "danger")
                            return redirect(url_for("banking_transfert"))
                    except (InvalidOperation, ValueError):
                        flash("Format de montant invalide. Utilisez un nombre avec maximum 2 décimales", "danger")
                        return redirect(url_for("banking_transfert"))

                    # ✅ Validation des comptes
                    if transfert_type == 'interne':
                        source_id = request.form.get('compte_source')
                        dest_id = request.form.get('compte_dest')
                        source_type = 'compte_principal'
                        dest_type = 'compte_principal'
                    else:
                        source_id = request.form.get('compte_source_externe')
                        dest_id = request.form.get('compte_dest_externe')
                        source_type = 'compte_principal'
                        dest_type = 'compte_principal'

                    if not source_id or not source_id.isdigit() or not dest_id or not dest_id.isdigit():
                        flash("Veuillez sélectionner des comptes valides", "danger")
                        return redirect(url_for("banking_transfert"))

                    source_id = int(source_id)
                    dest_id = int(dest_id)

                    # ✅ Vérif interne : comptes différents
                    if transfert_type == 'interne' and source_id == dest_id:
                        flash("Le compte source et le compte destination doivent être différents", "danger")
                        return redirect(url_for("banking_transfert"))

                    # ✅ Vérification que le compte source appartient à l'utilisateur
                    if not any(int(c['id']) == source_id for c in comptes + sous_comptes):
                        flash("Vous ne pouvez pas transférer depuis ce compte", "danger")
                        return redirect(url_for("banking_transfert"))

                    # ✅ Préparation des données pour INSERT
                    transfert_data = {
                        'utilisateur_id': user_id,
                        'montant': float(montant),
                        'devise': 'CHF',
                        'compte_source_id': source_type,   # ENUM
                        'source_id': source_id,           # ID réel
                        'destination_type': dest_type,    # ENUM
                        'compte_dest_id': dest_id,        # ID réel
                        'commentaire': request.form.get('commentaire', '')
                    }

                    # ✅ Récupérer la date, la référence et le commentaire pour tous les transferts
                    date_transfert = request.form.get('date_transfert')
                    reference = request.form.get('reference', '').strip()
                    commentaire = request.form.get('commentaire', '').strip()

                    if not date_transfert:
                        flash("Veuillez indiquer une date de transfert", "danger")
                        return redirect(url_for("banking_transfert"))

                    transfert_data.update({
                        'date_transfert': date_transfert,
                        'reference': reference,
                        'commentaire': commentaire
                    })

                    if transfert_type == 'externe':
                        compte_dest = next((c for c in all_comptes if c['id'] == dest_id), None)
                        if compte_dest:
                            transfert_data.update({
                                'nom_dest': compte_dest['nom_compte'],
                                'iban_dest': compte_dest.get('iban', ''),
                                'destinataire_id': compte_dest['utilisateur_id']
                            })

                    # ✅ Exécution
                    success, message = transfert_model.create(transfert_data)

                    if success:
                        flash(message, "success")
                        if transfert_type == 'externe' and 'destinataire_id' in transfert_data:
                            Notification(db_manager).create(
                                user_id=transfert_data['destinataire_id'],
                                titre="Nouveau transfert reçu",
                                message=f"Transfert de {montant} CHF reçu",
                                type_notif="transaction",
                                lien=f"/compte/{transfert_data['compte_dest_id']}"
                            )
                    else:
                        flash(message, "danger")

                    return redirect(url_for("banking_transfert"))

                except Exception as e:
                    flash(f"Erreur lors du transfert: {str(e)}", "danger")
                    return redirect(url_for("banking_transfert"))

        return render_template(
            "banking/transfert.html",
            comptes=comptes,
            sous_comptes=sous_comptes,
            all_comptes=all_comptes,
            now=datetime.now()
        )


    

    # ---- APIs ----
    @app.route('/api/banking/sous-comptes/<int:compte_id>')
    @login_required
    def api_sous_comptes(compte_id):
        return jsonify({'success': True,
                        'sous_comptes': sous_compte_model.get_by_compte_principal_id(compte_id)})

    @app.route("/statistiques")
    @login_required
    def banking_statistiques():
        user_id = current_user.id

        # ✅ Récupérer la période (en mois) depuis la requête GET, valeur par défaut : 6
        nb_mois = request.args.get("period", 6)
        try:
            nb_mois = int(nb_mois)
        except ValueError:
            nb_mois = 6

        # ✅ Récupérer les stats globales
        stats = stats_model.get_resume_utilisateur(user_id)

        # ✅ Répartition par banque
        repartition = stats_model.get_repartition_par_banque(user_id)
        repartition_labels = [item['nom_banque'] for item in repartition]
        repartition_values = [item['montant_total'] for item in repartition]
        repartition_colors = [f"#{random.randint(0, 0xFFFFFF):06x}" for _ in repartition_labels]

        # ✅ Évolution épargne (avec filtre nb_mois)
        evolution = stats_model.get_evolution_epargne(user_id, nb_mois)
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





    @app.route('/api/banking/repartition')
    @login_required
    def api_repartition_banques():
        return jsonify({'success': True,
                        'repartition': stats_model.get_repartition_par_banque(current_user.id)})

    @app.route('/banking/sous-compte/supprimer/<int:sous_compte_id>')
    @login_required
    def banking_supprimer_sous_compte(sous_compte_id):
        sous_compte = sous_compte_model.get_by_id(sous_compte_id)
        if not sous_compte:
            flash('Sous-compte non trouvé', 'error')
            return redirect(url_for('banking_dashboard'))
        
        compte_id = sous_compte['compte_principal_id']
        if sous_compte_model.delete(sous_compte_id):
            flash(f'Sous-compte "{sous_compte["nom_sous_compte"]}" supprimé avec succès', 'success')
        else:
            flash('Impossible de supprimer un sous-compte avec un solde positif', 'error')
        
        return redirect(url_for('banking_compte_detail', compte_id=compte_id))
    

    @app.route('/banking/liste_transactions', methods=['GET'])
    @login_required
    def liste_transactions():
        user_id = current_user.id
        
        # Récupération des paramètres de filtrage
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        compte_id = request.args.get('compte_id')
        sous_compte_id = request.args.get('sous_compte_id')
        dest_sc_id = request.args.get('sous_compte_destination_id')
        compte_dest_id = request.args.get('compte_dest_id')
        reference = request.args.get('reference')
        text_search = request.args.get('q')
        sort_by = request.args.get('sort_by', 'date')
        order = request.args.get('order', 'desc')
        page = int(request.args.get('page', 1))
        per_page = 20

        # Initialisation du modèle
        transaction_model = Transaction(db_manager)
        compte_model = ComptePrincipal(db_manager)
        sous_compte_model = SousCompte(db_manager)

        # Récupération des transactions avec filtres
        filters = {
            'date_from': date_from,
            'date_to': date_to,
            'compte_id': compte_id,
            'sous_compte_id': sous_compte_id,
            'sous_compte_destination_id': dest_sc_id,
            'compte_dest_id': compte_dest_id,
            'reference': reference,
            'text_search': text_search
        }

        if compte_id:
            transactions = transaction_model.get_by_compte_id(compte_id, user_id, per_page)
        elif sous_compte_id:
            transactions = transaction_model.get_by_sous_compte_id(sous_compte_id, user_id, per_page)
        else:
            # Récupération de tous les comptes de l'utilisateur pour afficher toutes les transactions
            comptes = compte_model.get_by_user_id(user_id)
            all_transactions = []
            for compte in comptes:
                compte_transactions = transaction_model.get_by_compte_id(compte['id'], user_id, per_page)
                all_transactions.extend(compte_transactions)
            # Tri et pagination manuelle (simplifiée)
            transactions = sorted(all_transactions, 
                                key=lambda x: x['date_transaction'], 
                                reverse=(order.lower() == 'desc'))[:per_page]

        # Préparation des données pour les filtres
        comptes = compte_model.get_by_user_id(user_id)
        sous_comptes = []
        for c in comptes:
            sous_comptes += sous_compte_model.get_by_compte_principal_id(c['id'])

        # Export CSV
        if request.args.get('export') == 'csv':
            si = StringIO()
            cw = csv.writer(si, delimiter=';')
            cw.writerow(['ID','Type','Montant','Description','Référence','Date',
                        'Sous orig','Sous dest','Compte dest'])
            for t in transactions:
                cw.writerow([
                    t['id'], 
                    t['type_transaction'], 
                    f"{t['montant']:.2f}",
                    t.get('description',''), 
                    t.get('reference',''),
                    t['date_transaction'].strftime("%Y-%m-%d %H:%M"),
                    t.get('nom_sous_compte') or '', 
                    t.get('nom_sous_compte_destination') or '',
                    t.get('nom_compte_destination') or ''
                ])
            output = make_response(si.getvalue())
            output.headers["Content-Disposition"] = "attachment; filename=transactions.csv"
            output.headers["Content-Type"] = "text/csv; charset=utf-8"
            return output

        return render_template(
            'banking/liste_transactions.html',
            transactions=transactions,
            comptes=comptes,
            sous_comptes=sous_comptes,
            page=page,
            pages=1,  # Simplification - à adapter pour une vraie pagination
            date_from=date_from,
            date_to=date_to,
            compte_filter=compte_id,
            sc_filter=sous_compte_id,
            dest_sc_filter=dest_sc_id,
            compte_dest_filter=compte_dest_id,
            ref_filter=reference,
            text_search=text_search,
            sort_by=sort_by,
            order=order
        )

    @app.route('/banking/liste_transferts', methods=['GET'])
    @login_required
    def liste_transferts():
        user_id = current_user.id
        
        # Récupération des paramètres de filtrage
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        compte_source_id = request.args.get('compte_source_id')
        compte_dest_id = request.args.get('compte_dest_id')
        sous_compte_source_id = request.args.get('sous_compte_source_id')
        sous_compte_dest_id = request.args.get('sous_compte_dest_id')
        type_transfert = request.args.get('type_transfert')
        statut = request.args.get('statut')
        page = int(request.args.get('page', 1))
        per_page = 20

        # Initialisation des modèles
        transfert_model = Transfert(db_manager)
        compte_model = ComptePrincipal(db_manager)
        sous_compte_model = SousCompte(db_manager)

        # Récupération des comptes et sous-comptes pour les filtres
        comptes = compte_model.get_by_user_id(user_id)
        sous_comptes = []
        for c in comptes:
            sous_comptes += sous_compte_model.get_by_compte_principal_id(c['id'])

        # Récupération des transferts avec filtres
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
        
        transferts = transfert_model.get_by_filters(filters)
        print(len(transferts))
        total_transferts = transfert_model.count_by_filters(filters)
        pages = (total_transferts + per_page - 1) // per_page

        # Export CSV
        if request.args.get('export') == 'csv':
            si = StringIO()
            cw = csv.writer(si, delimiter=';')
            cw.writerow(['Date', 'Type', 'Source', 'Destination', 'Montant', 'Statut'])
            for t in transferts:
                source = ""
                if t['compte_source_id']:
                    source = t['nom_compte_source']
                    if t['sous_compte_source_id']:
                        source += f" ({t['nom_sous_compte_source']})"
                elif t['sous_compte_source_id']:
                    source = f"{t['nom_sous_compte_source']} (sous-compte)"
                else:
                    source = t['nom_dest'] or 'Externe'

                destination = ""
                if t['compte_dest_id']:
                    destination = t['nom_compte_dest']
                    if t['sous_compte_dest_id']:
                        destination += f" ({t['nom_sous_compte_dest']})"
                elif t['sous_compte_dest_id']:
                    destination = f"{t['nom_sous_compte_dest']} (sous-compte)"
                else:
                    destination = t['nom_dest'] or 'Externe'

                cw.writerow([
                    t['date_transfert'].strftime("%Y-%m-%d %H:%M"),
                    t['type_transfert'],
                    source,
                    destination,
                    f"{t['montant']:.2f}",
                    'Complété' if t['statut'] == 'completed' else 'En attente'
                ])
            
            output = make_response(si.getvalue())
            output.headers["Content-Disposition"] = "attachment; filename=transferts.csv"
            output.headers["Content-Type"] = "text/csv; charset=utf-8"
            return output

        return render_template(
            'banking/liste_transferts.html',
            transferts=transferts,
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

    @app.route('/banking/annuler_transfert', methods=['POST'])
    @login_required
    def annuler_transfert():
        data = request.json
        transfert_id = data.get('transfert_id')
        user_id = current_user.id

        transfert_model = Transfert(db_manager)
        success, message = transfert_model.annuler(transfert_id, user_id)
        
        return jsonify({'success': success, 'message': message})

  

    @app.route('/comptabilite/statistiques')
    @login_required
    def statistiques_comptables():
        ecriture_model = EcritureComptable(db_manager)
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        stats = ecriture_model.get_stats_by_categorie(
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
    
    
    @app.route('/comptabilite/categories')
    @login_required
    def liste_categories_comptables():
        plan_comptable = PlanComptable(db_manager)
        categories = plan_comptable.get_all_categories()
        return render_template('comptabilite/categories.html', categories=categories)
    

    @app.route('/comptabilite/categories/nouvelle', methods=['GET', 'POST'])
    @login_required
    def nouvelle_categorie():
        """Crée une nouvelle catégorie comptable"""
        plan_comptable = PlanComptable(db_manager)
        
        if request.method == 'POST':
            try:
                data = {
                    'numero': request.form['numero'],
                    'nom': request.form['nom'],
                    'type': request.form['type'],
                    'parent_id': request.form.get('parent_id') or None
                }
                
                if plan_comptable.create(data):
                    flash('Catégorie créée avec succès', 'success')
                    return redirect(url_for('liste_categories_comptables'))
                else:
                    flash('Erreur lors de la création', 'danger')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'danger')
        
        categories = plan_comptable.get_all_categories()
        return render_template('comptabilite/edit_categorie.html', 
                            categories=categories,
                            categorie=None)

    @app.route('/comptabilite/categories/<int:categorie_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_categorie(categorie_id):
        """Modifie une catégorie comptable existante"""
        plan_comptable = PlanComptable(db_manager)
        categorie = plan_comptable.get_by_id(categorie_id)
        
        if not categorie:
            flash('Catégorie introuvable', 'danger')
            return redirect(url_for('liste_categories_comptables'))
        
        if request.method == 'POST':
            try:
                data = {
                    'numero': request.form['numero'],
                    'nom': request.form['nom'],
                    'type': request.form['type'],
                    'parent_id': request.form.get('parent_id') or None
                }
                
                if plan_comptable.update(categorie_id, data):
                    flash('Catégorie mise à jour avec succès', 'success')
                    return redirect(url_for('liste_categories_comptables'))
                else:
                    flash('Erreur lors de la mise à jour', 'danger')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'danger')
        
        categories = plan_comptable.get_all_categories()
        return render_template('comptabilite/edit_categorie.html', 
                            categories=categories,
                            categorie=categorie)

    @app.route('/comptabilite/categories/<int:categorie_id>/delete', methods=['POST'])
    @login_required
    def delete_categorie(categorie_id):
        """Supprime une catégorie comptable"""
        plan_comptable = PlanComptable(db_manager)
        
        if plan_comptable.delete(categorie_id):
            flash('Catégorie supprimée avec succès', 'success')
        else:
            flash('Erreur lors de la suppression', 'danger')
        
        return redirect(url_for('liste_categories_comptables'))

    @app.route('/comptabilite/ecritures')
    @login_required
    def liste_ecritures():
        """Affiche la liste des écritures comptables"""
        ecriture_model = EcritureComptable(db_manager)
        compte_model = ComptePrincipal(db_manager)
        
        compte_id = request.args.get('compte_id')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        categorie_id = request.args.get('categorie_id')
        
        if categorie_id:
            ecritures = ecriture_model.get_by_categorie(
                categorie_id=int(categorie_id),
                user_id=current_user.id,
                date_from=date_from,
                date_to=date_to
            )
        elif compte_id:
            ecritures = ecriture_model.get_by_compte_bancaire(
                compte_id=int(compte_id),
                user_id=current_user.id,
                date_from=date_from,
                date_to=date_to
            )
        else:
            ecritures = []
        
        comptes = compte_model.get_by_user_id(current_user.id)
        return render_template('comptabilite/ecritures.html', 
                            ecritures=ecritures, 
                            comptes=comptes,
                            compte_selectionne=compte_id)
    
    #@app.route('/comptabilite/ecritures')
    #@login_required
    #def liste_ecritures():
    #    ecriture_model = EcritureComptable(db_manager)
    #    compte_id = request.args.get('compte_id')
    #    date_from = request.args.get('date_from')
    #    date_to = request.args.get('date_to')
        
    #    if compte_id:
    #        ecritures = ecriture_model.get_by_compte_bancaire(
    #            compte_id=int(compte_id),
    #            user_id=current_user.id,
    #            date_from=date_from,
    #            date_to=date_to
    #        )
    #    else:
    #        ecritures = []
    #    
    #    comptes = compte_model.get_by_user_id(current_user.id)
    #    return render_template('comptabilite/ecritures.html', 
    #                        ecritures=ecritures, 
    #                        comptes=comptes,
    #                        compte_selectionne=compte_id)

    @app.route('/comptabilite/ecritures/nouvelle', methods=['GET', 'POST'])
    @login_required
    def nouvelle_ecriture():

        plan_comptable = PlanComptable(db_manager)
        ecriture_model = EcritureComptable(db_manager)
        compte_model = ComptePrincipal(db_manager)
        
        if request.method == 'POST':
            try:
                data = {
                    'date_ecriture': request.form['date_ecriture'],
                    'compte_bancaire_id': int(request.form['compte_bancaire_id']),
                    'categorie_id': int(request.form['categorie_id']),
                    'montant': Decimal(request.form['montant']),
                    'description': request.form.get('description', ''),
                    'reference': request.form.get('reference', ''),
                    'type_ecriture': request.form['type_ecriture'],
                    'tva_taux': Decimal(request.form['tva_taux']) if request.form.get('tva_taux') else None,
                    'utilisateur_id': current_user.id
                }
                
                if data['tva_taux']:
                    data['tva_montant'] = data['montant'] * data['tva_taux'] / 100
                
                if ecriture_model.create(data):
                    flash('Écriture enregistrée avec succès', 'success')
                    
                    # Optionnel: lier à une transaction bancaire si l'ID est fourni
                    transaction_id = request.form.get('transaction_id')
                    if transaction_id:
                        transaction_model = Transaction(db_manager)
                        transaction_model.link_to_ecriture(transaction_id, ecriture_model.last_insert_id)
                    
                    return redirect(url_for('liste_ecritures'))
                else:
                    flash('Erreur lors de l\'enregistrement', 'danger')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'danger')
        
        # Pré-remplir depuis une transaction bancaire si transaction_id est dans les paramètres
        transaction_id = request.args.get('transaction_id')
        transaction_data = {}
        if transaction_id:
            transaction_model = Transaction(db_manager)
            transaction = transaction_model.get_by_id(transaction_id)
            if transaction and transaction['utilisateur_id'] == current_user.id:
                transaction_data = {
                    'date_ecriture': transaction['date_transaction'].strftime('%Y-%m-%d'),
                    'montant': abs(transaction['montant']),
                    'type_ecriture': 'depot' if transaction['type_transaction'] == 'depot' else 'depense',
                    'description': transaction['description'],
                    'compte_bancaire_id': transaction['compte_principal_id']
                }
        
        comptes = compte_model.get_by_user_id(current_user.id)
        categories = plan_comptable.get_all_categories()
        return render_template('comptabilite/nouvelle_ecriture.html', 
                            comptes=comptes, 
                            categories=categories,
                            ecriture=None,
                            transaction_data=transaction_data,
                            transaction_id=transaction_id)
    @app.route('/nouvelle_ecriture_multiple', methods=['GET', 'POST'])
    def nouvelle_ecriture_multiple():
        plan_comptable = PlanComptable(db_manager)
        ecriture_model = EcritureComptable(db_manager)
        compte_model = ComptePrincipal(db_manager)

        if request.method == 'POST':
            # Récupération des données sous forme de listes
            dates = request.form.getlist('date_ecriture[]')
            types = request.form.getlist('type_ecriture[]')
            comptes_ids = request.form.getlist('compte_bancaire_id[]')
            categories_ids = request.form.getlist('categorie_id[]')
            montants = request.form.getlist('montant[]')
            tva_taux = request.form.getlist('tva_taux[]')
            descriptions = request.form.getlist('description[]')
            references = request.form.getlist('reference[]')

            # Validation et traitement de chaque écriture
            succes_count = 0
            for i in range(len(dates)):
                try:
                    # Validation des données requises
                    if not all([dates[i], types[i], comptes_ids[i], categories_ids[i], montants[i]]):
                        flash(f"Écriture {i+1}: Tous les champs obligatoires doivent être remplis", "warning")
                        continue

                    # Conversion des types
                    montant = float(montants[i])
                    taux_tva = float(tva_taux[i]) if tva_taux[i] else 7.7  # Valeur par défaut

                    # Création de l'écriture
                    nouvelle_ecriture = EcritureComptable(
                        date_ecriture=datetime.strptime(dates[i], '%Y-%m-%d').date(),
                        type_ecriture=types[i],
                        compte_bancaire_id=int(comptes_ids[i]),
                        categorie_id=int(categories_ids[i]),
                        montant=montant,
                        tva_taux=taux_tva,
                        description=descriptions[i],
                        reference=references[i],
                        user_id=current_user.id
                    )

                    # Sauvegarde en base de données
                    db.session.add(nouvelle_ecriture)
                    succes_count += 1

                except ValueError as e:
                    flash(f"Écriture {i+1}: Erreur de format - {str(e)}", "error")
                    continue
                except Exception as e:
                    flash(f"Écriture {i+1}: Erreur inattendue - {str(e)}", "error")
                    continue

            try:
                db.session.commit()
                flash(f"{succes_count} écriture(s) enregistrée(s) avec succès!", "success")
                return redirect(url_for('liste_ecritures'))
            
            except Exception as e:
                db.session.rollback()
                flash(f"Erreur lors de l'enregistrement final: {str(e)}", "error")

        # GET: Afficher le formulaire avec les listes déroulantes
        comptes = compte_model.get_by_user_id(current_user.id)
        categories = plan_comptable.get_all_categories()
        
        return render_template(
            'comptabilite/nouvelle_ecriture_multiple.html',
            comptes=comptes,
            categories=categories,
            current_date=datetime.now().strftime('%Y-%m-%d')
        )
    
    #@app.route('/comptabilite/nouvelle', methods=['GET', 'POST'])
    #@login_required
    #def nouvelle_ecriture():
    #    plan_comptable = PlanComptable(db_manager)
    #    ecriture_model = EcritureComptable(db_manager)
    #    
    #    if request.method == 'POST':
    #        try:
    #            data = {
    #                'date_ecriture': request.form['date_ecriture'],
    #                'compte_bancaire_id': int(request.form['compte_bancaire_id']),
    #                'categorie_id': int(request.form['categorie_id']),
    #                'montant': Decimal(request.form['montant']),
    #                'description': request.form.get('description', ''),
    #                'type_ecriture': request.form['type_ecriture'],
    #                'reference': request.form.get('reference', ''),
    #                'tva_taux': Decimal(request.form['tva_taux']) if request.form.get('tva_taux') else None,
    #                'utilisateur_id': current_user.id
    #            }
                
    #            if data['tva_taux']:
    #                data['tva_montant'] = data['montant'] * data['tva_taux'] / 100
                
    #            if ecriture_model.create(data):
    #                flash('Écriture enregistrée avec succès', 'success')
    #                return redirect(url_for('liste_ecritures'))
    #            else:
    #                flash('Erreur lors de l\'enregistrement', 'danger')
    #        except Exception as e:
    #            flash(f'Erreur: {str(e)}', 'danger')
    #    
    #    comptes = compte_model.get_by_user_id(current_user.id)
    #    categories = plan_comptable.get_all_categories()
    #    return render_template('comptabilite/nouvelle_ecriture.html', 
    #                        comptes=comptes, 
    #                        categories=categories)

    @app.route('/comptabilite/ecritures/<int:ecriture_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_ecriture(ecriture_id):
        """Modifie une écriture comptable existante"""
        plan_comptable = PlanComptable(db_manager)
        ecriture_model = EcritureComptable(db_manager)
        compte_model = ComptePrincipal(db_manager)
        
        ecriture = ecriture_model.get_by_id(ecriture_id)
        if not ecriture or ecriture['utilisateur_id'] != current_user.id:
            flash('Écriture introuvable ou non autorisée', 'danger')
            return redirect(url_for('liste_ecritures'))
        
        if request.method == 'POST':
            try:
                data = {
                    'date_ecriture': request.form['date_ecriture'],
                    'compte_bancaire_id': int(request.form['compte_bancaire_id']),
                    'categorie_id': int(request.form['categorie_id']),
                    'montant': Decimal(request.form['montant']),
                    'description': request.form.get('description', ''),
                    'reference': request.form.get('reference', ''),
                    'type_ecriture': request.form['type_ecriture'],
                    'tva_taux': Decimal(request.form['tva_taux']) if request.form.get('tva_taux') else None,
                    'utilisateur_id': current_user.id
                }
                
                if data['tva_taux']:
                    data['tva_montant'] = data['montant'] * data['tva_taux'] / 100
                
                if ecriture_model.update(ecriture_id, data):
                    flash('Écriture mise à jour avec succès', 'success')
                    return redirect(url_for('liste_ecritures'))
                else:
                    flash('Erreur lors de la mise à jour', 'danger')
            except Exception as e:
                flash(f'Erreur: {str(e)}', 'danger')
        
        comptes = compte_model.get_by_user_id(current_user.id)
        categories = plan_comptable.get_all_categories()
        return render_template('comptabilite/nouvelle_ecriture.html', 
                            comptes=comptes, 
                            categories=categories,
                            ecriture=ecriture)

    @app.route('/comptabilite/ecritures/<int:ecriture_id>/delete', methods=['POST'])
    @login_required
    def delete_ecriture(ecriture_id):
        """Supprime une écriture comptable"""
        ecriture_model = EcritureComptable(db_manager)
        
        ecriture = ecriture_model.get_by_id(ecriture_id)
        if not ecriture or ecriture['utilisateur_id'] != current_user.id:
            flash('Écriture introuvable ou non autorisée', 'danger')
            return redirect(url_for('liste_ecritures'))
        
        if ecriture_model.delete(ecriture_id):
            flash('Écriture supprimée avec succès', 'success')
        else:
            flash('Erreur lors de la suppression', 'danger')
        
        return redirect(url_for('liste_ecritures'))

    #@app.route('/comptabilite/statistiques')
    #@login_required
    #def statistiques_comptables():
    #    """Affiche les statistiques comptables"""
    #    ecriture_model = EcritureComptable(db_manager)
    #    date_from = request.args.get('date_from')
    #    date_to = request.args.get('date_to')
    #    
    #    stats = ecriture_model.get_stats_by_categorie(
    #        user_id=current_user.id,
    #        date_from=date_from,
    #        date_to=date_to
    #    )
        
    #    total_depenses = sum(s['total_depenses'] or 0 for s in stats)
    #    # Calcul des totaux
    #    total_recettes = sum(s['total_recettes'] or 0 for s in stats)
    #    resultat = total_recettes - total_depenses
        
    #    return render_template('comptabilite/statistiques.html',
    #                        stats=stats,
    #                        total_depenses=total_depenses,
    #                        total_recettes=total_recettes,
    #                        resultat=resultat,
    #                        date_from=date_from,
    #                        date_to=date_to)




    # Ajouter une route pour lier une transaction à une écriture
    @app.route('/banking/link_transaction', methods=['POST'])
    @login_required
    def link_transaction_to_ecriture():
        transaction_id = request.form.get('transaction_id')
        ecriture_id = request.form.get('ecriture_id')
        
        transaction_model = Transaction(db_manager)
        transaction = transaction_model.get_by_id(transaction_id)
        
        if not transaction or transaction['utilisateur_id'] != current_user.id:
            flash('Transaction non trouvée ou non autorisée', 'danger')
            return redirect(url_for('banking_dashboard'))
        
        if transaction_model.link_to_ecriture(transaction_id, ecriture_id):
            flash('Transaction liée avec succès', 'success')
        else:
            flash('Erreur lors du lien', 'danger')
        
        return redirect(url_for('banking_compte_detail', compte_id=transaction['compte_principal_id']))




    @app.route('/comptabilite/compte-de-resultat')
    @login_required
    def compte_de_resultat():
        """Génère le compte de résultat avec filtres"""
        # Récupération des paramètres
        annee = request.args.get('annee', datetime.now().year)
        date_from = f"{annee}-01-01"
        date_to = f"{annee}-12-31"
        
        # Récupération des données
        ecriture_model = EcritureComptable(db_manager)
        stats = ecriture_model.get_compte_de_resultat(
            user_id=current_user.id,
            date_from=date_from,
            date_to=date_to
        )
        
        # Préparation des données pour le template
        annees_disponibles = ecriture_model.get_annees_disponibles(current_user.id)
        
        return render_template('comptabilite/compte_de_resultat.html',
                            stats=stats,
                            annee_selectionnee=int(annee),
                            annees_disponibles=annees_disponibles)

    @app.route('/comptabilite/compte-de-resultat/export')
    @login_required
    def export_compte_de_resultat():
        """Exporte le compte de résultat"""
        format_export = request.args.get('format', 'pdf')
        annee = request.args.get('annee', datetime.now().year)
        
        # Récupération des données
        ecriture_model = EcritureComptable(db_manager)
        stats = ecriture_model.get_compte_de_resultat(
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

    @app.route('/')
    def journal_comptable():
        # Récupérer les années disponibles
        annees = ecriture_comptable.get_annees_disponibles(user_id=1)  # À adapter avec le vrai user_id
        
        # Récupérer les catégories comptables
        categories = plan_comptable.get_all_categories()
        
        # Paramètres par défaut
        annee_courante = datetime.now().year
        date_from = f"{annee_courante}-01-01"
        date_to = f"{annee_courante}-12-31"
        
        # Récupérer les écritures
        ecritures = ecriture_comptable.get_by_compte_bancaire(
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
        
        return render_template('journal_comptable.html', **context)

    @app.route('/api/ecritures')
    @login_required
    def api_ecritures():
        # Récupérer les paramètres de filtrage
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        categorie_id = request.args.get('categorie_id')
        type_ecriture = request.args.get('type_ecriture')
        
        # Récupérer les écritures filtrées
        if categorie_id:
            ecritures = ecriture_comptable.get_by_categorie(
                categorie_id=int(categorie_id),
                user_id=1,  # À adapter
                date_from=date_from,
                date_to=date_to  # Fixed: changed from date_from=date_to to date_to=date_to
            )
        else:
            ecritures = ecriture_comptable.get_by_compte_bancaire(
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

    @app.route('/api/compte_resultat')
    @login_required
    def api_compte_resultat():
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        resultat = ecriture_comptable.get_compte_de_resultat(
            user_id=1,  # À adapter
            date_from=date_from,
            date_to=date_to
        )
        
        return jsonify(resultat)
    
    
### Partie heures et salaires 

    @app.route('/heures-travail', methods=['GET', 'POST'])
    @login_required
    def heures_travail():
        heure_model = HeureTravail(db_manager)
        current_user_id = current_user.id

        contrat_model = Contrat(db_manager)
        contrat = contrat_model.get_contrat_actuel(current_user_id)
        heures_hebdo_contrat = contrat['heures_hebdo'] if contrat else 38.0

        # Récupérer mois, semaine, mode selon méthode HTTP
        if request.method == 'POST':
            mois = int(request.form.get('mois', datetime.now().month))
            semaine = int(request.form.get('semaine', 0))
            current_mode = request.form.get('mode', 'reel')
        else:
            mois = int(request.args.get('mois', datetime.now().month))
            semaine = int(request.args.get('semaine', 0))
            current_mode = request.args.get('mode', 'reel')

        # Traitement POST : actions spécifiques
        if request.method == 'POST':
            if 'save_line' in request.form:
                date_str = request.form['save_line']
                # process_day renvoie un redirect pour recharger la page
                print(process_day(request, current_user_id, date_str, mois, semaine, current_mode, flash_message=True, do_redirect=True))
                return process_day(request, current_user_id, date_str, mois, semaine, current_mode, flash_message=True, do_redirect=True)

            elif 'reset_line' in request.form:
                date_str = request.form['reset_line']
                heure_model.delete_by_date(date_str, current_user_id)
                flash(f"Les heures du {format_date(date_str)} ont été réinitialisées", "warning")
                return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=current_mode))

            elif 'reset_all' in request.form:
                days = generate_days(mois, semaine)
                for day in days:
                    heure_model.delete_by_date(day.isoformat(), current_user_id)
                flash("Toutes les heures ont été réinitialisées", "warning")
                return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=current_mode))

            elif request.form.get('action') == 'simuler':
                days = generate_days(mois, semaine)
                for day in days:
                    date_str = day.isoformat()
                    vacances = bool(request.form.get(f'vacances_{date_str}', False))

                    if not vacances:
                        payload = {
                            'date': date_str,
                            'h1d': '08:00',
                            'h1f': '12:00',
                            'h2d': '13:00',
                            'h2f': '17:00',
                            'vacances': False,
                            'total_h': heure_model.calculer_heures('08:00', '12:00', '13:00', '17:00'),
                            'user_id': current_user_id,
                            'jour_semaine': day.strftime('%A'),
                            'semaine_annee': day.isocalendar()[1],
                            'mois': day.month
                        }
                        heure_model.create_or_update(payload)

                flash("Heures simulées appliquées", "info")
                return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=current_mode))

            else:
                # Enregistrer toutes les heures (formulaire standard)
                days = generate_days(mois, semaine)
                for day in days:
                    # Pas de flash/message ou redirect intermédiaire
                    process_day(request, current_user_id, day.isoformat(), mois, semaine, current_mode, flash_message=False, do_redirect=False)

                flash("Toutes les heures ont été enregistrées", "success")
                return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=current_mode))

        # Traitement GET : récupération et préparation des données pour affichage
        semaines = {}

        for day_date in generate_days(mois, semaine):
            date_str = day_date.isoformat()
            jour_data = heure_model.get_by_date(date_str, current_user_id) or {
                'date': date_str,
                'h1d': '',
                'h1f': '',
                'h2d': '',
                'h2f': '',
                'vacances': False,
                'total_h': 0.0
            }
            print(jour_data)

            # S’assurer que date est en string ISO si nécessaire
            if isinstance(jour_data['date'], date):
                jour_data['date'] = jour_data['date'].isoformat()

            # Calcul total_h si besoin
            if jour_data['total_h'] == 0 and any([jour_data['h1d'], jour_data['h1f'], jour_data['h2d'], jour_data['h2f']]):
                jour_data['total_h'] = heure_model.calculer_heures(
                    jour_data['h1d'] or '', jour_data['h1f'] or '',
                    jour_data['h2d'] or '', jour_data['h2f'] or ''
                )

            # Nom jour en français
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

        # Total général
        total_general = sum(s['total'] for s in semaines.values())

        # Tri des semaines
        semaines = dict(sorted(semaines.items()))

        return render_template('salaires/heures_travail.html',
                            semaines=semaines,
                            total_general=total_general,
                            heures_hebdo_contrat=heures_hebdo_contrat,
                            current_mois=mois,
                            current_semaine=semaine,
                            current_mode=current_mode)

    def process_day(request, user_id, date_str, mois, semaine, mode, flash_message=True, do_redirect=True):
        heure_model = HeureTravail(db_manager)

        h1d = request.form.get(f'h1d_{date_str}', '')
        h1f = request.form.get(f'h1f_{date_str}', '')
        h2d = request.form.get(f'h2d_{date_str}', '')
        h2f = request.form.get(f'h2f_{date_str}', '')
        vacances = bool(request.form.get(f'vacances_{date_str}', False))

        total_h = 0.0
        if not vacances and (h1d or h1f or h2d or h2f):
            total_h = heure_model.calculer_heures(h1d, h1f, h2d, h2f)

        day_date = datetime.fromisoformat(date_str)
        payload = {
            'date': date_str,
            'h1d': h1d,
            'h1f': h1f,
            'h2d': h2d,
            'h2f': h2f,
            'vacances': vacances,
            'total_h': total_h,
            'user_id': user_id,
            'jour_semaine': day_date.strftime('%A'),
            'semaine_annee': day_date.isocalendar()[1],
            'mois': day_date.month
        }

        heure_model.create_or_update(payload)

        if flash_message:
            flash(f"Heures du {format_date(date_str)} enregistrées", "success")

        if do_redirect:
            return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=mode))

    def format_date(date_str):
        return datetime.fromisoformat(date_str).strftime('%d/%m/%Y')

    def generate_days(mois: int, semaine: int) -> list[date]:
        """Génère les jours du mois ou de la semaine demandée"""
        today = datetime.now()
        year = today.year

        if semaine > 0:
            try:
                start_date = datetime.fromisocalendar(year, semaine, 1).date()
            except ValueError:
                # Si la semaine n'existe pas, fallback sur début du mois courant
                start_date = date(year, today.month, 1)
            return [start_date + timedelta(days=i) for i in range(7)]
        elif mois > 0:
            _, num_days = monthrange(year, mois)
            return [date(year, mois, day) for day in range(1, num_days + 1)]
        else:
            # Par défaut mois courant
            _, num_days = monthrange(year, today.month)
            return [date(year, today.month, day) for day in range(1, num_days + 1)]

# Fonctions de gestion des actions
    def handle_save_line(request, user_id, mois, semaine, mode):
        date_str = request.form['save_line']
        return process_day(request, user_id, date_str, mois, semaine, mode)

    def handle_reset_line(request, user_id, mois, semaine, mode):
        date_str = request.form['reset_line']
        heure_model = HeureTravail(db_manager)
        heure_model.delete_by_date(date_str, user_id)
        flash(f"Les heures du {format_date(date_str)} ont été réinitialisées", "warning")
        return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=mode))

    def handle_reset_all(request, user_id, mois, semaine, mode):
        heure_model = HeureTravail(db_manager)
        days = generate_days(mois, semaine)
        for day in days:
            heure_model.delete_by_date(day.isoformat(), user_id)
        flash("Toutes les heures ont été réinitialisées", "warning")
        return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=mode))

    def handle_simulation(request, user_id, mois, semaine, mode):
        heure_model = HeureTravail(db_manager)
        days = generate_days(mois, semaine)
        
        for day in days:
            date_str = day.isoformat()
            vacances = bool(request.form.get(f'vacances_{date_str}', False))
            
            if not vacances:
                payload = {
                    'date': date_str,
                    'h1d': '08:00',
                    'h1f': '12:00',
                    'h2d': '13:00',
                    'h2f': '17:00',
                    'vacances': False,
                    'total_h': heure_model.calculer_heures('08:00', '12:00', '13:00', '17:00'),
                    'user_id': user_id,
                    'jour_semaine': day.strftime('%A'),
                    'semaine_annee': day.isocalendar()[1],
                    'mois': day.month
                }
                heure_model.create_or_update(payload)
        
        flash("Heures simulées appliquées", "info")
        return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=mode))

    def handle_save_all(request, user_id, mois, semaine, mode):
        heure_model = HeureTravail(db_manager)
        days = generate_days(mois, semaine)
        
        for day in days:
            date_str = day.isoformat()
            process_day(request, user_id, date_str, mois, semaine, mode, False)
        
        flash("Toutes les heures ont été enregistrées", "success")
        return redirect(url_for('heures_travail', mois=mois, semaine=semaine, mode=mode))

    @app.route('/synthese-heures')
    @login_required
    def synthese_heures():
        synthese_hebdo_model = SyntheseHebdomadaire(db_manager)
        synthese_mensuelle_model = SyntheseMensuelle(db_manager)
        current_user_id = current_user.id
        
        # Récupérer les données de synthèse
        semaines = synthese_hebdo_model.get_by_user(current_user_id)
        mois_data = synthese_mensuelle_model.get_by_user(current_user_id)
        
        # Préparer les données pour le graphique
        mois_labels = []
        heures_reelles = []
        heures_simulees = []
        
        for mois in mois_data:
            mois_labels.append(f"{get_month_name(mois['mois'])} {mois['annee']}")
            heures_reelles.append(mois['heures_reelles'])
            heures_simulees.append(mois['heures_simulees'])
        
        return render_template('salaires/synthese_heures.html',
                            semaines=semaines,
                            mois_labels=mois_labels,
                            heures_reelles=heures_reelles,
                            heures_simulees=heures_simulees)
    
    @app.route('/synthese_mensuelle')
    @login_required
    def afficher_synthese_mensuelle():
        user_id = current_user.id
        salaire_model = Salaire(db_manager)
        synthese_model = SyntheseMensuelle(db_manager)

        salaires = salaire_model.get_all(user_id)
        syntheses = synthese_model.get_by_user(user_id, limit=12)

        return render_template('salaires/synthese_mensuelle.html', 
                            salaires=salaires,
                            syntheses=syntheses)
    
    @app.route('/calcul-salaires')
    @login_required
    def calcul_salaires():
        annee_courante = request.args.get('annee', default=datetime.now().year, type=int)

        salaire_model = Salaire(db_manager)
        contrats_model = Contrat(db_manager)
        heure_model = HeureTravail(db_manager)

        contrat_actuel = contrats_model.get_contrat_actuel(current_user.id)
        salaires = salaire_model.get_all(current_user.id)

        salaires_par_mois = {mois: None for mois in range(1, 13)}

        total_heures = 0.0
        total_salaire_calcule = 0.0
        total_salaire_verse = 0.0
        total_acompte_25 = 0.0
        total_acompte_10 = 0.0
        total_acompte_25_estime = 0.0
        total_acompte_10_estime = 0.0

        annees_disponibles = set()

        # Taux horaire depuis le contrat (par défaut 27.12 CHF si absent)
        taux_horaire = contrat_actuel.get('taux_horaire', 27.12) if contrat_actuel else 27.12

        for salaire in salaires:
            annee = salaire.get('annee')
            if annee:
                annees_disponibles.add(annee)

            if annee == annee_courante:
                mois = salaire.get('mois')
                if not mois:
                    continue

                # Heures réelles
                heures_reelles = heure_model.get_total_heures_mois(current_user.id, annee_courante, mois)
                salaire['heures_reelles'] = heures_reelles

                # Si des heures existent -> recalcul du salaire
                if heures_reelles and contrat_actuel:
                    salaire_calcule = salaire_model.calculer_salaire(heures_reelles, taux_horaire)
                    salaire_verse = salaire.get('salaire_verse') or 0

                    difference, difference_pourcent = salaire_model.calculer_differences(salaire_calcule, salaire_verse)

                    # Mise à jour en base
                    salaire_model.update(salaire['id'], {
                        # 'heures_reelles': heures_reelles,  # à commenter si colonne absente en base
                        'salaire_calcule': salaire_calcule,
                        'difference': difference,
                        'difference_pourcent': difference_pourcent
                    })

                    # Mise à jour du dict local
                    salaire['salaire_calcule'] = salaire_calcule
                    salaire['difference'] = difference
                    salaire['difference_pourcent'] = difference_pourcent

                salaires_par_mois[mois] = salaire

                total_heures += heures_reelles or 0
                total_salaire_calcule += salaire.get('salaire_calcule') or 0
                total_salaire_verse += salaire.get('salaire_verse') or 0
                total_acompte_25 += salaire.get('acompte_25') or 0
                total_acompte_10 += salaire.get('acompte_10') or 0
                total_acompte_25_estime += salaire.get('acompte_25_estime') or 0
                total_acompte_10_estime += salaire.get('acompte_10_estime') or 0

        # Si certains mois n'ont pas de salaire mais ont des heures, on crée les lignes
        for mois in range(1, 13):
            if salaires_par_mois[mois] is None:
                heures_reelles = heure_model.get_total_heures_mois(current_user.id, annee_courante, mois)
                if heures_reelles and contrat_actuel:
                    salaire_calcule = salaire_model.calculer_salaire(heures_reelles, taux_horaire)
                    salaire_model.create({
                        'mois': mois,
                        'annee': annee_courante,
                        'heures_reelles': heures_reelles,
                        'salaire_calcule': salaire_calcule,
                        'salaire_horaire': taux_horaire,
                        'user_id': current_user.id
                    })
                    # Mettre à jour la structure locale
                    salaires_par_mois[mois] = {
                        'mois': mois,
                        'annee': annee_courante,
                        'heures_reelles': heures_reelles,
                        'salaire_calcule': salaire_calcule,
                        'salaire_verse': 0,
                        'difference': 0,
                        'difference_pourcent': 0
                    }
                    total_heures += heures_reelles
                    total_salaire_calcule += salaire_calcule

        annees_disponibles = sorted(annees_disponibles, reverse=True)
        if not annees_disponibles:
            annees_disponibles = [annee_courante]

        totaux = {
            "total_heures": sum((data.get('heures_reelles', 0) if data else 0) for data in salaires_par_mois.values()),
            "total_calcule": sum((data.get('salaire_calcule', 0) if data else 0) for data in salaires_par_mois.values()),
            "total_verse": sum((data.get('salaire_verse', 0) if data else 0) for data in salaires_par_mois.values()),
            "total_difference": sum((data.get('difference', 0) if data else 0) for data in salaires_par_mois.values())
        }

        return render_template('salaires/calcul_salaires.html',
            salaires_par_mois=salaires_par_mois,
            total_heures=round(total_heures, 2),
            total_salaire_calcule=round(total_salaire_calcule, 2),
            total_salaire_verse=round(total_salaire_verse, 2),
            total_acompte_25=round(total_acompte_25, 2),
            total_acompte_10=round(total_acompte_10, 2),
            total_acompte_25_estime=round(total_acompte_25_estime, 2),
            total_acompte_10_estime=round(total_acompte_10_estime, 2),
            contrat_actuel=contrat_actuel,
            years=annees_disponibles,
            annee_courante=annee_courante,
            totaux=totaux
        )


    @app.route('/contrat', methods=['GET', 'POST'])
    @login_required
    def gestion_contrat():
        contrat_model = Contrat(db_manager)
        current_user_id = current_user.id
        print(current_user_id)
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'save':
                # Création ou mise à jour du contrat
                data = {
                    'id': request.form.get('contrat_id') or None,
                    'user_id': current_user_id,
                    'heures_hebdo': float(request.form.get('heures_hebdo')),
                    'date_debut': request.form.get('date_debut'),
                    'date_fin': request.form.get('date_fin') or None
                }
                contrat_model.create_or_update(data)
                flash('Contrat enregistré avec succès!', 'success')
            
            elif action == 'delete':
                contrat_id = request.form.get('contrat_id')
                if contrat_id:
                    contrat_model.delete(contrat_id)
                    flash('Contrat supprimé avec succès!', 'success')
            
            return redirect(url_for('gestion_contrat'))
        
        # Récupérer le contrat actuel et tous les contrats
        
        contrat_actuel = contrat_model.get_contrat_actuel(current_user_id)
        print(contrat_actuel)
        contrats = contrat_model.get_all_contrats(current_user_id)
        print(contrats)
        return render_template('salaires/contrat.html', 
                            contrat_actuel=contrat_actuel,
                            contrats=contrats,
                            today=date.today())
    
    return app

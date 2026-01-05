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
            'date' : date_str,
            'plages':[],
            'vacances': False,
            'total_h': 0.0
        }
        #   jour_data_default = {    
        #    'date': date_str,
        #    'h1d': '',
        #    'h1f': '',
        #    'h2d': '',
        #    'h2f': '',
        #    'vacances': False,
        #    'total_h': 0.0
        #}
        if contrat:
            jour_data = g.models.heure_model.get_by_date(date_str, current_user_id, selected_employeur, contrat['id']) or jour_data_default 
        else:
            jour_data = jour_data_default
        logging.debug(f"banking 3012 DEBUG: Données pour le {date_str}: {jour_data}")
        # CORRECTION : Toujours recalculer total_h pour assurer la cohérence
        #if not jour_data['vacances'] and any([jour_data['h1d'], jour_data['h1f'], jour_data['h2d'], jour_data['h2f']]):
        #    calculated_total = g.models.heure_model.calculer_heures(
        #        jour_data['h1d'] or '', jour_data['h1f'] or '',
        #        jour_data['h2d'] or '', jour_data['h2f'] or ''
        #    )
        #    # Mise à jour si différence significative (tolérance de 0.01h = 36 secondes)
        #    if abs(jour_data['total_h'] - calculated_total) > 0.01:
        #        jour_data['total_h'] = calculated_total
        #elif jour_data['vacances']:
        #    jour_data['total_h'] = 0.0
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

#def has_hours_for_employeur_and_contrat(self, user_id, employeur, id_contrat):
#    """Vérifie si l'utilisateur a des heures enregistrées pour un employeur donné"""
#    try:
#        with self.db.get_cursor() as cursor:
#            query = "SELECT 1 FROM heures_travail WHERE user_id = %s AND employeur = %s AND id_contrat = %s LIMIT 1"
#            cursor.execute(query, (user_id, employeur, id_contrat))
#            result = cursor.fetchone()
#            return result is not None
#    except Exception as e:
#        current_app.logger.error(f"Erreur has_hours_for_employeur_and_contrat: {e}")
#        return False

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

#def validate_day_data(request, date_str):
#    errors = []
#    
#    h1d = request.form.get(f'h1d_{date_str}', '').strip()
#    h1f = request.form.get(f'h1f_{date_str}', '').strip()
#    h2d = request.form.get(f'h2d_{date_str}', '').strip()
#    h2f = request.form.get(f'h2f_{date_str}', '').strip()
#    
    # Validation format des heures
#    for field_name, time_str in [('h1d', h1d), ('h1f', h1f), ('h2d', h2d), ('h2f', h2f)]:
#        if not is_valid_time(time_str):
#            errors.append(f"Format d'heure invalide pour {field_name}: '{time_str}'")
    
    # MODIFICATION : Permettre les demi-journées et heures simples
    # Ne pas bloquer si seulement une période est remplie
#    if not errors:
#        # Vérifier la cohérence par période
#        if (h1d and not h1f) or (not h1d and h1f):
#            errors.append("Heure de début et fin de matin incohérentes")
#        if (h2d and not h2f) or (not h2d and h2f):
#            errors.append("Heure de début et fin d'après-midi incohérentes")
            
        # Vérifier l'ordre chronologique si les deux périodes sont présentes
#        if h1d and h1f and h2d and h2f:
#            try:
#                t1d = datetime.strptime(h1d, '%H:%M').time()
#                t1f = datetime.strptime(h1f, '%H:%M').time()
#                t2d = datetime.strptime(h2d, '%H:%M').time()
#                t2f = datetime.strptime(h2f, '%H:%M').time()
                
#                if not (t1d <= t1f and t1f <= t2d and t2d <= t2f):
#                    errors.append("L'ordre chronologique des heures n'est pas respecté")
#            except ValueError:
#                pass
#    
#    return errors

def create_day_payload(request, user_id, date_str, employeur, id_contrat):
    """Crée le payload pour une journée en gérant correctement les valeurs vides"""
    # Récupération des valeurs du formulaire avec conversion des chaînes vides en None
    def get_time_field(field_name):
        value = request.form.get(f'{field_name}_{date_str}', '').strip()
        return value if value else None
    plages = []
    for i in range(5):
        debut = request.form.get(f'plage_{i}_debut_{date_str}', '').strip() or None
        fin = request.form.get(f'plage_{i}_fin_{date_str}', '').strip() or None
        if debut or fin:
            plages.append({'debut': debut, 'fin': fin})
    vacances = get_vacances_value(request, date_str)

    #h1d = get_time_field('h1d')
    #h1f = get_time_field('h1f')
    #h2d = get_time_field('h2d')
    #h2f = get_time_field('h2f')
    #vacances = get_vacances_value(request, date_str)
    
    # Conversion des valeurs temporelles vides en None
    #time_fields = [h1d, h1f, h2d, h2f]
    #for i, value in enumerate(time_fields):
    #    if value == '':
    #        time_fields[i] = None
    
    # Calcul du total uniquement si nécessaire
    #total_h = 0.0
    #if not vacances and any(time_fields):
        # Utilisation de la méthode statique pour éviter l'instanciation inutile
    #    total_h = HeureTravail.calculer_heures_static(
    #        h1d or '', 
    #        h1f or '',
    #        h2d or '',
    #        h2f or ''
    #    )
    
    return {
        'date': date_str,
        'user_id': user_id,
        'employeur': employeur,
        'id_contrat': id_contrat,
        'plages': plages,
    #    'h1d': h1d,
    #    'h1f': h1f,
    #    'h2d': h2d,
    #    'h2f': h2f,
        'vacances': vacances,
        'type_heures': 'reelles'
    #    'total_h': total_h,
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
    #errors = validate_day_data(request, date_str)
    #if errors:
    #    for error in errors:
    #        flash(f"Erreur {format_date(date_str)}: {error}", "error")
    #    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))
    
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
                payload = {
                    'date': date_str,
                    'user_id': user_id,
                    'employeur': employeur,
                    'id_contrat': id_contrat,
                    'plages': [
                        {'debut': '08:00', 'fin': '12:00'},
                        {'debut': '13:00', 'fin': '17:00'}
                    ],                    
                    'vacances': False,
                    'type_heures': 'simulees'

                }
                if g.models.heure_model.create_or_update(payload):
                    success_count += 1
    if success_count > 0:
        flash(f'heures simulées appliquées pour {success_count} jours', 'info')
    return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))


            #try:
            #    total_h = g.models.heure_model.calculer_heures('08:00', '12:00', '13:00', '17:00')
            #    payload = {
            #        'date': date_str,
            #        'h1d': '08:00',
            #        'h1f': '12:00',
            #        'h2d': '13:00',
            #        'h2f': '17:00',
            #        'vacances': False,
            #        'total_h': total_h,
            #        'user_id': user_id,
            #        'employeur': employeur,
            #        'id_contrat': id_contrat,
            #        'jour_semaine': day.strftime('%A'),
            #        'semaine_annee': day.isocalendar()[1],
            #        'mois': day.month
            #    }
            #    g.models.heure_model.create_or_update(payload)
            #    success_count += 1
            #except Exception as e:
            #    logger.error(f"Erreur simulation jour {date_str}: {str(e)}")
            #    errors.append(format_date(date_str))
    #if errors:
    #    flash(f"Erreur simulation pour les jours: {', '.join(errors)}", "error")
    #if success_count > 0:
    #    flash(f"Heures simulées appliquées pour {success_count} jour(s)", "info")
    #return redirect(url_for('banking.heures_travail', annee=annee, mois=mois, semaine=semaine, mode=mode, employeur=employeur, id_contrat=id_contrat))

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
        'plages': src_data.get('plages', []),
        #'h1d': src_data.get('h1d'),
        #'h1f': src_data.get('h1f'),
        #'h2d': src_data.get('h2d'),
        #'h2f': src_data.get('h2f'),
        'vacances': src_data.get('vacances', False),
        'type_heures': src_data.get('type_heures', 'reelles')
        #'total_h': src_data.get('total_h', 0.0)
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
            'plages': src_data.get('plages', []),
            #'h1d': src_data.get('h1d'),
            #'h1f': src_data.get('h1f'),
            #'h2d': src_data.get('h2d'),
            #'h2f': src_data.get('h2f'),
            'vacances': src_data.get('vacances', False),
            'type_heures': src_data.get('type_heures', 'reelles')
            #'total_h': src_data.get('total_h', 0.0)
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

    ### Détail entreprise

# Constantes
UPLOAD_FOLDER_LOGOS = 'static/uploads/logos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 Mo

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def ensure_upload_dir():
    os.makedirs(UPLOAD_FOLDER_LOGOS, exist_ok=True)

@bp.route('/entreprise', methods=['GET', 'POST'])
@login_required
def gestion_entreprise():
    current_user_id = current_user.id
    ensure_upload_dir()

    if request.method == 'POST':
        data = {
            'nom': request.form.get('nom', '').strip(),
            'rue': request.form.get('rue', '').strip(),
            'code_postal': request.form.get('code_postal', '').strip(),
            'commune': request.form.get('commune', '').strip(),
            'email': request.form.get('email', '').strip(),
            'telephone': request.form.get('telephone', '').strip(),
            'logo_path': None
        }

        # Gestion du logo
        logo_path = None
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename != '' and allowed_file(file.filename):
                # Vérifier taille
                file.seek(0, os.SEEK_END)
                size = file.tell()
                file.seek(0)
                if size > MAX_FILE_SIZE:
                    flash("Le fichier est trop volumineux (max. 2 Mo).", "error")
                    return redirect(request.url)

                # Générer un nom unique
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"user_{current_user_id}_logo_{secrets.token_urlsafe(8)}.{ext}"
                filepath = os.path.join(UPLOAD_FOLDER_LOGOS, filename)

                # Supprimer l’ancien logo
                ancien_logo = g.models.entreprise_model.get_logo_path(current_user_id)
                if ancien_logo:
                    ancien_path = os.path.join(current_app.static_folder, ancien_logo)
                    if os.path.exists(ancien_path):
                        os.remove(ancien_path)

                # Sauvegarder nouveau
                file.save(filepath)
                logo_path = os.path.join('uploads', 'logos', filename).replace('\\', '/')

        if logo_path:
            data['logo_path'] = logo_path

        # Mise à jour base
        if g.models.entreprise_model.update(current_user_id, data):
            flash("Informations de l'entreprise mises à jour.", "success")
        else:
            flash("Aucune modification effectuée.", "warning")
        return redirect(url_for('banking.gestion_entreprise'))

    entreprise = g.models.entreprise_model.get_or_create_for_user(current_user_id)
    return render_template('entreprise/gestion.html', entreprise=entreprise)


### ---- Routes heures travail pour employées
def prepare_svg_heures_employes(data_employes, jours_semaine, seuil_heure):
    largeur_svg = 900
    hauteur_svg = 500
    margin = 60
    plot_width = largeur_svg - 2 * margin
    plot_height = hauteur_svg - 2 * margin

    # Y-axis : 6h (haut) à 22h (bas) → 16h d’écart = 960 minutes
    min_heure = 6
    max_heure = 22
    total_minutes = (max_heure - min_heure) * 60  # 960

    def heure_to_y(heure_str):
        if not heure_str:
            return None
        h, m = map(int, heure_str.split(':'))
        total = h * 60 + m
        # Si < 6h → ramener à 6h (ou gérer nuit)
        total_clipped = max(total, min_heure * 60)
        # Position depuis le haut
        minutes_from_min = total_clipped - (min_heure * 60)
        y_px = margin + (minutes_from_min / total_minutes) * plot_height
        return y_px

    rectangles = []
    couleur_par_employe = {}
    couleurs = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6']
    
    for idx, emp in enumerate(data_employes):
        couleur = couleurs[idx % len(couleurs)]
        couleur_par_employe[emp['employeur']] = couleur
        for plage in emp['plages']:
            jour = plage['date']
            x = margin + jours_semaine.index(jour) * (plot_width / 7) + (plot_width / 7) * 0.1
            largeur = (plot_width / 7) * 0.8
            y1 = heure_to_y(plage['debut'])
            y2 = heure_to_y(plage['fin'])
            if y1 is not None and y2 is not None:
                hauteur = y2 - y1
                depasse_seuil = False
                # Vérifier si la plage dépasse le seuil
                if plage['fin']:
                    h_fin, m_fin = map(int, plage['fin'].split(':'))
                    if h_fin + m_fin/60 > seuil_heure:
                        depasse_seuil = True
                rectangles.append({
                    'x': x,
                    'y': y1,
                    'width': largeur,
                    'height': max(hauteur, 2),
                    'color': couleur if not depasse_seuil else '#F87171',
                    'employeur': emp['employeur'],
                    'debut': plage['debut'],
                    'fin': plage['fin']
                })

    # Ligne seuil
    seuil_y = heure_to_y(f"{int(seuil_heure):02d}:{int((seuil_heure % 1)*60):02d}")

    # Labels Y (6h, 10h, 14h, 18h, 22h)
    labels_y = []
    for h in range(min_heure, max_heure + 1, 2):
        y = heure_to_y(f"{h:02d}:00")
        labels_y.append({'heure': f"{h}h", 'y': y})

    return {
        'largeur': largeur_svg,
        'hauteur': hauteur_svg,
        'margin': margin,
        'rectangles': rectangles,
        'seuil_y': seuil_y,
        'labels_y': labels_y,
        'jours': [d.strftime('%a %d') for d in jours_semaine],
        'couleurs': couleur_par_employe
    }

@bp.route('/heures-employes', methods=['GET'])
@login_required
def heures_employes():
    user_id = current_user.id
    now = datetime.now()
    annee = int(request.args.get('annee', now.year))
    semaine = int(request.args.get('semaine', now.isocalendar()[1]))
    seuil_heure = float(request.args.get('seuil', 18.0))  # ex: 18h

    # Récupérer tous les employés distincts pour lesquels vous avez des heures
    with g.models.heure_model.db.get_cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT employeur, id_contrat
            FROM heures_travail
            WHERE user_id = %s
        """, (user_id,))
        employes = [{'employeur': row['employeur'], 'id_contrat': row['id_contrat']} for row in cursor.fetchall()]

    # Pour chaque employé, récupérer les données de la semaine
    data_employes = []
    jours_semaine = [datetime.fromisocalendar(annee, semaine, d).date() for d in range(1, 8)]

    for emp in employes:
        plages_semaine = []
        total_heures = 0.0
        for jour in jours_semaine:
            jour_data = g.models.heure_model.get_by_date(
                jour.isoformat(), user_id, emp['employeur'], emp['id_contrat']
            )
            if jour_data and not jour_data.get('vacances'):
                plages = jour_data.get('plages', [])
                for plage in plages:
                    if plage.get('debut') and plage.get('fin'):
                        plages_semaine.append({
                            'date': jour,
                            'debut': plage['debut'],
                            'fin': plage['fin']
                        })
                total_heures += jour_data.get('total_h', 0)
        data_employes.append({
            'employeur': emp['employeur'],
            'id_contrat': emp['id_contrat'],
            'plages': plages_semaine,
            'total_heures': round(total_heures, 2)
        })

    # Préparer les données SVG
    svg_data = prepare_svg_heures_employes(data_employes, jours_semaine, seuil_heure)

    return render_template(
        'salaires/heures_employes.html',
        annee=annee,
        semaine=semaine,
        seuil_heure=seuil_heure,
        employes=data_employes,
        svg_data=svg_data,
        jours_semaine=jours_semaine
    )

EMPLOYE_SESSION_KEY = 'employe_salaire_session'

@bp.route('/employe/login', methods=['GET', 'POST'])
def employe_login():
    if request.method == 'POST':
        try:
            employe_id = int(request.form.get('employe_id', 0))
            code = request.form.get('code', '').strip()
        except (ValueError, TypeError):
            flash("Identifiant invalide.", "error")
            return render_template('employe/login.html')

        # Vérifier le code
        employe = g.models.employe_model.verifier_code_acces(employe_id, code)
        if employe:
            # Stocker en session (sans utiliser `current_user`)
            session[EMPLOYE_SESSION_KEY] = {
                'employe_id': employe['id'],
                'user_id': employe['user_id'],
                'prenom': employe['prenom'],
                'nom': employe['nom']
            }
            return redirect(url_for('banking.employe_salaire_view'))
        else:
            flash("Numéro d'employé ou code d'accès invalide.", "error")
    
    return render_template('employe/login.html')

@bp.route('/salaires/pdf/<int:mois>/<int:annee>')
@login_required
def salaire_pdf(mois: int, annee: int):
    user_id = current_user.id
    selected_employeur = request.args.get('employeur')

    # Récupérer les données comme dans /salaires
    contrat = g.models.contrat_model.get_contrat_for_date(user_id, selected_employeur, f"{annee}-{mois:02d}-01")
    if not contrat:
        abort(404)

    heures_reelles = g.models.heure_model.get_total_heures_mois(user_id, selected_employeur, contrat['id'], annee, mois) or 0.0
    salaires_db = g.models.salaire_model.get_by_mois_annee(user_id, annee, mois, selected_employeur, contrat['id'])
    salaire_data = salaires_db[0] if salaires_db else None

    result = g.models.salaire_model.calculer_salaire_net_avec_details(
        heures_reelles=heures_reelles,
        contrat=contrat,
        contrat_id=contrat['id'],
        annee=annee,
        mois=mois,
        user_id=user_id,
        jour_estimation=contrat.get('jour_estimation_salaire', 15)
    )
    details = result.get('details', {})

    # Récupérer infos entreprise
    entreprise = g.models.entreprise_model.get_or_create_for_user(user_id)

    # === GÉNÉRATION PDF ===
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=14,
        alignment=1  # center
    )

    # En-tête entreprise
    if entreprise.get('logo_path') and os.path.exists(os.path.join(current_app.static_folder, entreprise['logo_path'])):
        logo_path = os.path.join(current_app.static_folder, entreprise['logo_path'])
        img = Image(logo_path, width=1.5*inch, height=1.5*inch)
        elements.append(img)
        elements.append(Spacer(1, 12))

    elements.append(Paragraph(entreprise.get('nom', 'Votre entreprise'), title_style))
    elements.append(Paragraph(f"{entreprise.get('rue', '')}", styles['Normal']))
    elements.append(Paragraph(f"{entreprise.get('code_postal', '')} {entreprise.get('commune', '')}", styles['Normal']))
    elements.append(Spacer(1, 24))

    # Titre du document
    mois_noms = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    elements.append(Paragraph(f"Fiche de salaire – {mois_noms[mois]} {annee}", styles['Heading1']))
    if selected_employeur:
        elements.append(Paragraph(f"Employeur : {selected_employeur}", styles['Normal']))
    elements.append(Spacer(1, 18))

    # Tableau de synthèse
    data = [
        ["Élément", "Montant (CHF)"],
        ["Heures réelles", f"{heures_reelles:.2f} h"],
        ["Salaire brut", f"{details.get('salaire_brut', 0):.2f}"],
        ["+ Indemnités", f"+{details.get('total_indemnites', 0):.2f}"],
        ["- Cotisations", f"-{details.get('total_cotisations', 0):.2f}"],
        ["= Salaire net", f"{result.get('salaire_net', 0):.2f}"],
    ]
    table = Table(data, colWidths=[3*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 24))

    # Signature
    elements.append(Paragraph("_________________________", styles['Normal']))
    elements.append(Paragraph("Signature employeur", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)

    filename = f"salaire_{selected_employeur or 'perso'}_{annee}_{mois:02d}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )


@bp.route('/salaires/employe/<int:employe_id>/pdf/<int:annee>/<int:mois>')
def salaire_employe_pdf(employe_id: int, annee: int, mois: int):
    code = request.args.get('code')
    if not code:
        abort(403)

    employe = g.models.employe_model.get_employe_by_code(employe_id, code)
    if not employe:
        abort(403)

    user_id = employe['user_id']
    contrat = g.models.contrat_model.get_contrat_for_employe(user_id, employe_id)
    if not contrat:
        abort(404)

    employeur = contrat['employeur']
    heures_reelles = g.models.heure_model.get_total_heures_mois(user_id, employeur, contrat['id'], annee, mois) or 0.0
    result = g.models.salaire_model.calculer_salaire_net_avec_details(
        heures_reelles=heures_reelles,
        contrat=contrat,
        contrat_id=contrat['id'],
        annee=annee,
        mois=mois,
        user_id=user_id,
        jour_estimation=contrat.get('jour_estimation_salaire', 15)
    )
    details = result.get('details', {})
    entreprise = g.models.entreprise_model.get_or_create_for_user(user_id)

    buffer = generer_pdf_salaire(
        entreprise=entreprise,
        employe_info={
            'prenom': employe['prenom'],
            'nom': employe['nom'],
            'employeur': employeur
        },
        mois=mois,
        annee=annee,
        heures_reelles=heures_reelles,
        result=result,
        details=details
    )

    filename = f"salaire_{employe['prenom']}_{employe['nom']}_{annee}_{mois:02d}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')

@bp.route('/employe/mon-salaire')
def employe_salaire_view():
    employe_session = session.get(EMPLOYE_SESSION_KEY)
    if not employe_session:
        return redirect(url_for('banking.employe_login'))

    employe_id = employe_session['employe_id']
    user_id = employe_session['user_id']
    annee = request.args.get('annee', datetime.now().year, type=int)

    # Trouver le contrat de l'employé
    contrat = g.models.contrat_model.get_contrat_for_employe(user_id, employe_id)
    if not contrat:
        flash("Aucun contrat trouvé pour votre compte.", "error")
        return render_template('employe/salaire.html', employe=employe_session, salaires_par_mois={})

    id_contrat = contrat['id']
    employeur = contrat['employeur']
    salaire_horaire = float(contrat.get('salaire_horaire', 24.05))
    jour_estimation = int(contrat.get('jour_estimation_salaire', 15))

    # Structure identique à /salaires
    salaires_par_mois = {}
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

    # Récupérer les salaires existants
    salaires_db = g.models.salaire_model.get_by_user_and_month_with_employe(
        user_id=user_id, annee=annee, mois=None, employe_id=employe_id
    )
    salaires_db_dict = {s['mois']: s for s in salaires_db}

    # Calculer mois par mois
    for m in range(1, 13):
        # Heures réelles
        heures_reelles = g.models.heure_model.get_total_heures_mois(
            user_id, employeur, id_contrat, annee, m
        ) or 0.0
        heures_reelles = round(heures_reelles, 2)

        # Valeurs de base
        salaire_verse = 0.0
        acompte_25 = 0.0
        acompte_10 = 0.0

        salaire_existant = salaires_db_dict.get(m)
        if salaire_existant:
            salaire_verse = salaire_existant.get('salaire_verse', 0.0)
            acompte_25 = salaire_existant.get('acompte_25', 0.0)
            acompte_10 = salaire_existant.get('acompte_10', 0.0)

        # Calculs dynamiques
        if heures_reelles > 0:
            # 1. Salaire net + détails
            result = g.models.salaire_model.calculer_salaire_net_avec_details(
                heures_reelles=heures_reelles,
                contrat=contrat,
                contrat_id=id_contrat,
                annee=annee,
                user_id=user_id,
                mois=m,
                jour_estimation=jour_estimation
            )
            salaire_net = result.get('salaire_net', 0.0)
            salaire_calcule = result.get('details', {}).get('salaire_brut', 0.0)
            details = result

            # 2. Acompte 25 = heures(1–15)
            acompte_25_estime = 0.0
            if contrat.get('versement_25'):
                acompte_25_estime = g.models.salaire_model.calculer_acompte_25(
                    user_id, annee, m, salaire_horaire, employeur, id_contrat, jour_estimation
                )
                acompte_25_estime = round(acompte_25_estime, 2)

            # 3. Acompte 10 = salaire_net − acompte_25_estime
            acompte_10_estime = round(salaire_net - acompte_25_estime, 2)

            # 4. Injecter dans le détails pour le modal
            if 'versements' not in details.get('details', {}):
                details['details']['versements'] = {}
            details['details']['versements']['acompte_25'] = {
                'nom': 'Acompte du 25',
                'actif': True,
                'montant': acompte_25_estime,
                'taux': 25
            }
            details['details']['versements']['acompte_10'] = {
                'nom': 'Acompte du 10',
                'actif': True,
                'montant': acompte_10_estime,
                'taux': 10
            }
            details['details']['total_versements'] = round(acompte_25_estime + acompte_10_estime, 2)
            details['details']['calcul_final']['moins_versements'] = round(salaire_net - (acompte_25_estime + acompte_10_estime), 2)

        else:
            salaire_net = salaire_calcule = acompte_25_estime = acompte_10_estime = 0.0
            details = {
                'erreur': 'Aucune heure saisie',
                'details': {
                    'heures_reelles': 0.0,
                    'salaire_horaire': salaire_horaire,
                    'salaire_brut': 0.0,
                    'indemnites': {},
                    'cotisations': {},
                    'versements': {
                        'acompte_25': {'montant': 0.0},
                        'acompte_10': {'montant': 0.0}
                    },
                    'calcul_final': {
                        'brut': 0.0,
                        'plus_indemnites': 0.0,
                        'moins_cotisations': 0.0,
                        'moins_versements': 0.0
                    }
                }
            }

        # Données du mois
        salaire_data = {
            'mois': m,
            'annee': annee,
            'user_id': user_id,
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
            'details': details
        }

        # Différence
        if salaire_calcule and salaire_verse:
            diff, diff_pct = g.models.salaire_model.calculer_differences(salaire_calcule, salaire_verse)
            salaire_data['difference'] = diff
            salaire_data['difference_pourcent'] = diff_pct

        # Stocker
        salaires_par_mois[m]['employeurs'][employeur] = salaire_data

        # Ajouter aux totaux (un seul employeur ici)
        totaux = salaires_par_mois[m]['totaux_mois']
        for key in totaux:
            if key == 'heures_reelles':
                totaux[key] = heures_reelles
            elif key == 'salaire_calcule':
                totaux[key] = salaire_calcule
            elif key == 'salaire_net':
                totaux[key] = salaire_net
            elif key == 'salaire_verse':
                totaux[key] = salaire_verse
            elif key == 'acompte_25':
                totaux[key] = acompte_25
            elif key == 'acompte_10':
                totaux[key] = acompte_10
            elif key == 'acompte_25_estime':
                totaux[key] = acompte_25_estime
            elif key == 'acompte_10_estime':
                totaux[key] = acompte_10_estime
            elif key == 'difference':
                totaux[key] = salaire_data['difference']

    # Totaux annuels
    totaux_annuels = {
        f"total_{k}": round(sum(salaires_par_mois[m]['totaux_mois'][k] for m in range(1,13)), 2)
        for k in salaires_par_mois[1]['totaux_mois'].keys()
    }

    # Préparer données SVG (optionnel — tu peux l’ajouter si besoin)
    graphique1_svg = None
    graphique2_svg = None

    return render_template(
        'employe/salaire.html',  # ← même template que /salaires, mais allégé
        salaires_par_mois=salaires_par_mois,
        totaux=totaux_annuels,
        annee_courante=annee,
        selected_employeur=employeur,
        employe=employe_session,
        graphique1_svg=graphique1_svg,
        graphique2_svg=graphique2_svg,
        largeur_svg=800,
        hauteur_svg=400
    )

@bp.route('/employe/logout')
def employe_logout():
    session.pop(EMPLOYE_SESSION_KEY, None)
    return redirect(url_for('banking.employe_login'))

# --- Routes salaires ---

@bp.route('/salaires', methods=['GET'])
@login_required
def salaires():
    current_user_id = current_user.id
    now = datetime.now()
    annee = request.args.get('annee', now.year, type=int)
    mois = request.args.get('mois', now.month, type=int)
    selected_employeur = request.args.get('employeur', '').strip()

    tous_contrats = g.models.contrat_model.get_all_contrats(current_user_id)
    employeurs_unique = sorted({c['employeur'] for c in tous_contrats if c.get('employeur')})

    # Sélection automatique de l'employeur
    if not selected_employeur and employeurs_unique:
        contrat_actuel = g.models.contrat_model.get_contrat_actuel(current_user_id)
        selected_employeur = contrat_actuel['employeur'] if contrat_actuel else employeurs_unique[0]

    # Initialiser structure
    salaires_par_mois = {}
    for m in range(1, 13):
        salaires_par_mois[m] = {
            'employeurs': {},
            'totaux_mois': {k: 0.0 for k in [
                'heures_reelles', 'salaire_calcule', 'salaire_net', 'salaire_verse',
                'acompte_25', 'acompte_10', 'acompte_25_estime', 'acompte_10_estime', 'difference'
            ]}
        }

    # Traiter chaque mois
    for m in range(1, 13):
        date_mois = date(annee, m, 1)
        employeurs_a_traiter = [selected_employeur] if selected_employeur else employeurs_unique

        for employeur in employeurs_a_traiter:
            # Trouver contrat actif ce mois-ci
            contrat = next((
                c for c in tous_contrats
                if c['employeur'] == employeur
                and c['date_debut'] <= date_mois
                and (c['date_fin'] is None or c['date_fin'] >= date_mois)
            ), None)

            if not contrat:
                continue

            id_contrat = contrat['id']
            salaire_horaire = float(contrat.get('salaire_horaire', 24.05))
            jour_estimation = int(contrat.get('jour_estimation_salaire', 15))

            # Heures réelles
            heures_reelles = g.models.heure_model.get_total_heures_mois(
                current_user_id, employeur, id_contrat, annee, m
            ) or 0.0
            heures_reelles = round(heures_reelles, 2)

            # Salaire existant ?
            salaires_existants = g.models.salaire_model.get_by_mois_annee(
                current_user_id, annee, m, employeur, id_contrat
            )
            salaire_existant = salaires_existants[0] if salaires_existants else None

            # Valeurs saisies manuellement
            salaire_verse = salaire_existant.get('salaire_verse', 0.0) if salaire_existant else 0.0
            acompte_25 = salaire_existant.get('acompte_25', 0.0) if salaire_existant else 0.0
            acompte_10 = salaire_existant.get('acompte_10', 0.0) if salaire_existant else 0.0

            # Calculs dynamiques SI heures > 0
            if heures_reelles > 0:
                # 1. Salaire net + détails (via nouvelles tables)
                result = g.models.salaire_model.calculer_salaire_net_avec_details(
                    heures_reelles=heures_reelles,
                    contrat=contrat,
                    contrat_id=id_contrat,
                    annee=annee,
                    user_id=current_user_id,
                    mois=m,
                    jour_estimation=jour_estimation
                )
                salaire_net = result.get('salaire_net', 0.0)
                salaire_calcule = result.get('details', {}).get('salaire_brut', 0.0)
                details = result

                # 2. Acompte 25 = heures(1–15) × salaire_horaire
                acompte_25_estime = 0.0
                if contrat.get('versement_25'):
                    acompte_25_estime = g.models.salaire_model.calculer_acompte_25(
                        current_user_id, annee, m, salaire_horaire, employeur, id_contrat, jour_estimation
                    )
                    acompte_25_estime = round(acompte_25_estime, 2)

                # 3. Acompte 10 = salaire_net − acompte_25_estime
                acompte_10_estime = round(salaire_net - acompte_25_estime, 2)

            else:
                salaire_net = salaire_calcule = acompte_25_estime = acompte_10_estime = 0.0
                details = {'erreur': 'Aucune heure saisie'}

            # Préparer données
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
                'details': details
            }

            # Différence
            if salaire_calcule and salaire_verse is not None:
                diff, diff_pct = g.models.salaire_model.calculer_differences(salaire_calcule, salaire_verse)
                salaire_data['difference'] = diff
                salaire_data['difference_pourcent'] = diff_pct

            # Création auto si nouveau
            if not salaire_existant and heures_reelles > 0:
                g.models.salaire_model.create(salaire_data)

            # Stocker
            salaires_par_mois[m]['employeurs'][employeur] = salaire_data

            # Ajouter aux totaux (si employeur sélectionné ou mode global)
            if not selected_employeur or employeur == selected_employeur:
                totaux = salaires_par_mois[m]['totaux_mois']
                for key in ['heures_reelles', 'salaire_calcule', 'salaire_net', 'salaire_verse',
                            'acompte_25', 'acompte_10', 'acompte_25_estime', 'acompte_10_estime', 'difference']:
                    totaux[key] += salaire_data[key]

    # Totaux annuels
    totaux_annuels = {f"total_{k}": round(sum(salaires_par_mois[m]['totaux_mois'][k] for m in range(1,13)), 2)
                      for k in salaires_par_mois[1]['totaux_mois'].keys()}

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
    id_contrat_filtre = request.args.get('id_contrat')
    employeur_filtre = request.args.get('employeur')
    seuil_h2f_heure = request.args.get('seuil_h2f', '20.0')
    try:
        seuil_h2f_heure = float(seuil_h2f_heure)
    except (ValueError, TypeError):
        seuil_h2f_heure = 20.0
    seuil_h2f_minutes = int(round(seuil_h2f_heure * 60))  # ← entier en minutes

    # Déterminer la semaine courante si non fournie
    if semaine is None or not semaine.isdigit():
        semaine = datetime.now().isocalendar()[1]
    else:
        semaine = int(semaine)

    # Calculer et sauvegarder les synthèses par contrat pour la semaine si nécessaire
    data_list = g.models.synthese_hebdo_model.calculate_for_week_by_contrat(user_id, annee, semaine)
    for data in data_list:
        g.models.synthese_hebdo_model.create_or_update_batch([data])

    # Données de la semaine sélectionnée
    synthese_list = g.models.synthese_hebdo_model.get_by_user_and_filters(
        user_id=user_id, annee=annee, semaine=semaine,
        employeur=employeur_filtre, contrat_id=id_contrat_filtre
    )
    
    # Calcul des totaux pour la semaine
    total_heures = sum(float(s.get('heures_reelles', 0)) for s in synthese_list)
    total_simule = sum(float(s.get('heures_simulees', 0)) for s in synthese_list)

    # --- NOUVEAU : Calcul des stats h2f pour l'année ---
  

    if employeur_filtre and id_contrat_filtre:
        stats_h2f = g.models.synthese_hebdo_model.calculate_h2f_stats(
            user_id, employeur_filtre, int(id_contrat_filtre), annee, seuil_h2f_minutes)
        moyenne_hebdo_h2f = stats_h2f['moyennes_hebdo'].get(semaine, 0.0)
        moyenne_mobile_h2f = stats_h2f['moyennes_mobiles'].get(semaine, 0.0)
    else:
        stats_h2f = g.models.synthese_hebdo_model.calculate_h2f_stats(user_id, None, None, annee, seuil_h2f_minutes)
        # On récupère la moyenne pour la semaine affichée
        moyenne_hebdo_h2f = stats_h2f['moyennes_hebdo'].get(semaine, 0.0)
        moyenne_mobile_h2f = stats_h2f['moyennes_mobiles'].get(semaine, 0.0)

    # --- NOUVEAU : Préparation des données SVG pour le graphique horaire de la semaine ---
    # Pour simplifier, on suppose que l'employeur et le contrat sont connus ou qu'on veut les combiner.
    # Ici, on va chercher les données brutes pour la semaine et on les affiche ensemble.
    # ATTENTION : Si tu as plusieurs contrats/employeurs, tu devras peut-être itérer ou agréger.
    # Pour cet exemple, on prend le premier contrat trouvé pour la semaine, ou None.
    id_contrat_exemple = synthese_list[0]['id_contrat'] if synthese_list else None
    employeur_exemple = synthese_list[0]['employeur'] if synthese_list else None
    id_contrat_svg = id_contrat_filtre if id_contrat_filtre else (synthese_list[0]['id_contrat'])
    employeur_svg = employeur_filtre if employeur_filtre else synthese_list[0]['employeur']

    svg_horaire_data = None
    if id_contrat_exemple and employeur_exemple:
        svg_horaire_data = g.models.synthese_hebdo_model.prepare_svg_data_horaire_jour(
            user_id, employeur_exemple, id_contrat_exemple, annee, semaine, seuil_h2f_heure
        )
    elif id_contrat_svg and employeur_svg:
        svg_horaire_data = g.models.synthese_hebdo_model.prepare_svg_data_horaire_jour(
            user_id, employeur_svg, id_contrat_svg, annee, semaine, seuil_h2f_heure)

    # Si pas de contrat trouvé, svg_horaire_data restera None, gère-le dans ton template.

    # Préparer le graphique SVG pour l'année entière (heures totales)
    graphique_svg = g.models.synthese_hebdo_model.prepare_svg_data_hebdo(user_id, annee)
    employeurs_disponibles = g.models.contrat_model.get_all_contrats(user_id)
    contrats_disponibles = g.models.contrat_model.get_all_contrats(user_id)
    return render_template('salaires/synthese_hebdo.html',
                        syntheses=synthese_list,
                        total_heures=round(total_heures, 2),
                        total_simule=round(total_simule, 2),
                        current_annee=annee,
                        current_semaine=semaine,
                        selected_contrat = id_contrat_filtre,
                        selected_employeur = employeur_filtre,
                        stats_h2f=stats_h2f,
                        moyenne_hebdo_h2f=moyenne_hebdo_h2f,
                        moyenne_mobile_h2f=moyenne_mobile_h2f,
                        seuil_h2f_heure=seuil_h2f_heure,
                        svg_horaire_data=svg_horaire_data,
                        graphique_svg=graphique_svg,
                        now=datetime.now(),
                        employeurs_disponibles=employeurs_disponibles,
                        contrats_disponibles=contrats_disponibles)

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
    employeurs = g.models.synthese_mensuelle_model.get_employeurs_distincts(user_id)
    logging.info(f'liste des employeurs : {employeurs}')
    contrats = g.models.contrat_model.get_all_contrats(user_id)
    employeurs_default = employeurs[0] if employeurs else None
    logging.info(f'employeur par defaut : {employeurs_default}')
    contrats_default = contrats[0]['id'] if contrats else None
    logging.info(f'contrat par défaut : {contrats_default}')
    
    annee = int(request.args.get('annee', datetime.now().year))
    mois = request.args.get('mois')
    employeur = request.args.get('employeur', employeurs_default)
    contrat_id_raw = request.args.get('contrat', contrats_default)
    contrat_id = None
    if contrat_id_raw is not None:
        try:
            contrat_id = int(contrat_id_raw)
        except (ValueError, TypeError):
            contrat_id = None
    
    mois = int(mois) if mois and mois.isdigit() else None

    synthese_list = g.models.synthese_mensuelle_model.get_by_user_and_filters(
        user_id=user_id,
        annee=annee,
        mois=mois,
        employeur=employeur,
        contrat_id=contrat_id
    )
    logging.info(f'voici la synthese list : {synthese_list}')
   
        
        
    # ✅ Préparer le graphique SVG (toujours pour l'année entière, en CHF)
    graphique_svg = g.models.synthese_mensuelle_model.prepare_svg_data_mensuel(user_id, annee)
    logging.info(f'Voici les données graphiques {graphique_svg} ')
    # --- NOUVEAU : Calcul des stats h2f pour le mois ---
    seuil_h2f_heure_input = request.args.get('seuil_h2f', '20.0')
    if seuil_h2f_heure_input:
        try:
            seuil_h2f_heure = float(seuil_h2f_heure_input)
        except (ValueError, TypeError):
            flash("La valeur du seuil est invalide.", "danger")
            return redirect(url_for('banking.synthese_mensuelle')) 
    else:
        seuil_h2f_heure = 20.0
    seuil_h2f_minutes = int(round(seuil_h2f_heure * 60))  # ← entier en minutes
    logging.info(f'Voici le seuil : {seuil_h2f_minutes} pour {seuil_h2f_heure_input}')

    seuil_h2f_minutes = int(round(seuil_h2f_heure * 60))  # ✅ garantit un int
    graphique_h2f_annuel = None
    if employeur and contrat_id:
        graphique_h2f_annuel = g.models.synthese_mensuelle_model.prepare_svg_data_h2f_annuel(
            user_id, employeur, contrat_id, annee, seuil_h2f_minutes, 900, 400)
    elif synthese_list:
        graphique_h2f_annuel = g.models.synthese_mensuelle_model.prepare_svg_data_h2f_annuel(
            user_id, employeur_exemple, id_contrat_exemple, annee, seuil_h2f_minutes, 900, 400)
    stats_h2f_mois = None
    svg_horaire_mois_data = None
    if mois: # Si un mois est spécifié
        # Comme synthese_mensuelle est par contrat, on suppose un seul contrat est affiché ou on prend un exemple.
        id_contrat_exemple = synthese_list[0]['id_contrat'] if synthese_list else None
        employeur_exemple = synthese_list[0]['employeur'] if synthese_list else None

        if contrat_id and employeur :
            stats_h2f_mois = g.models.synthese_mensuelle_model.calculate_h2f_stats_mensuel(
                user_id, employeur, contrat_id, annee, mois, seuil_h2f_minutes)
            svg_horaire_mois_data = g.models.synthese_mensuelle_model.prepare_svg_data_horaire_mois(
                user_id, employeur, contrat_id, annee, mois)
        elif id_contrat_exemple and employeur_exemple:
            stats_h2f_mois = g.models.synthese_mensuelle_model.calculate_h2f_stats_mensuel(
                user_id, employeur_exemple, id_contrat_exemple, annee, mois, seuil_h2f_minutes)
            # --- NOUVEAU : Préparation des données SVG pour le graphique horaire du mois ---
            svg_horaire_mois_data = g.models.synthese_mensuelle_model.prepare_svg_data_horaire_mois(
                user_id, employeur_exemple, id_contrat_exemple, annee, mois)
            logging.info(f'Voici les données pour {mois} : {svg_horaire_mois_data}')
    # --- NOUVEAU : Graphique hebdomadaire du dépassement de seuil DANS le mois ---
    graphique_h2f_semaines = None
    if mois and synthese_list:
        id_contrat_exemple = synthese_list[0]['id_contrat']
        employeur_exemple = synthese_list[0]['employeur']
        
        donnees_semaines = g.models.synthese_mensuelle_model.calculate_h2f_stats_weekly_for_month(
            user_id, employeur_exemple, id_contrat_exemple, annee, mois, seuil_h2f_minutes
        )
        logging.info(f'voici les données pour {mois}: {donnees_semaines}')

        # Préparer les données SVG (barres + ligne)
        semaines = donnees_semaines['semaines']
        depassements = donnees_semaines['jours_depassement']
        moyennes_mobiles = donnees_semaines['moyenne_mobile']

        if semaines:
            largeur_svg = 800
            hauteur_svg = 400
            n = len(semaines)
            margin_x = 50
            margin_y = 30
            plot_width = largeur_svg - margin_x - 50
            plot_height = hauteur_svg - margin_y - 50

            max_val = max(max(depassements or [0]), max(moyennes_mobiles or [0])) or 1

            # Barres
            barres = []
            for i in range(n):
                x = margin_x + i * (plot_width / n) + (plot_width / n) * 0.1
                largeur_barre = (plot_width / n) * 0.8
                hauteur_barre = (depassements[i] / max_val) * plot_height
                y = hauteur_svg - margin_y - hauteur_barre
                barres.append({
                    'x': x,
                    'y': y,
                    'width': largeur_barre,
                    'height': hauteur_barre,
                    'value': depassements[i]
                })

            # Ligne (moyenne mobile)
            points_ligne = []
            for i in range(n):
                x = margin_x + (i + 0.5) * (plot_width / n)
                y = hauteur_svg - margin_y - (moyennes_mobiles[i] / max_val) * plot_height
                points_ligne.append(f"{x},{y}")

            graphique_h2f_semaines = {
                'barres': barres,
                'ligne': points_ligne,
                'semaines': [f"S{num}" for num in semaines],
                'largeur_svg': largeur_svg,
                'hauteur_svg': hauteur_svg,
                'margin_x': margin_x,
                'margin_y': margin_y,
                'plot_width': plot_width,
                'plot_height': plot_height,
                'max_val': max_val
            }
    

    return render_template('salaires/synthese_mensuelle.html',
                        syntheses=synthese_list,
                        graphique_svg=graphique_svg,
                        graphique_h2f_annuel=graphique_h2f_annuel,
                        graphique_h2f_semaines=graphique_h2f_semaines,
                        current_annee=annee,
                        current_mois=mois,
                        selected_employeur=employeur,
                        selected_contrat=contrat_id,
                        employeurs_disponibles=employeurs,
                        contrats_disponibles=contrats,
                        # --- NOUVEAU : Ajouter les données pour le template ---
                        stats_h2f_mois=stats_h2f_mois,
                        seuil_h2f_heure=seuil_h2f_heure,
                        svg_horaire_mois_data=svg_horaire_mois_data,
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

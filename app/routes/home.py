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
    # Sinon, afficher la landing page publique pour présenter l'application
    return render_template('home2.html')
     

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modèles de données pour la gestion bancaire
Classes pour manipuler les banques, comptes et sous-comptes
"""
import statistics
from dbutils.pooled_db import PooledDB
import pymysql
from pymysql import Error, MySQLError
from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
import csv
import json
import os
import uuid
import time
import math
from collections import defaultdict

from typing import List, Dict, Optional, Tuple, TypedDict, Any
import traceback
from contextlib import contextmanager
from flask_login import UserMixin
import logging
 
import secrets

logger = logging.getLogger(__name__)



class Utilisateur(UserMixin):
    def __init__(self, id, nom=None, prenom=None, email=None, mot_de_passe=None):
        self.id = id
        self.nom = nom
        self.prenom = prenom
        self.email = email
        self.mot_de_passe = mot_de_passe

    # Méthodes requises par Flask-Login
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    @staticmethod
    def get_by_id(user_id: int, db):
        try:
            with db.get_cursor(dictionary=True) as cursor:
                query = "SELECT id, nom, prenom, email, mot_de_passe FROM utilisateurs WHERE id = %s"
                cursor.execute(query, (user_id,))
                row = cursor.fetchone()
                if row:
                    # On envoie l'ID en premier pour correspondre au nouveau __init__
                    return Utilisateur(row['id'], row['nom'], row['prenom'], row['email'], row['mot_de_passe'])
                return None
        except Exception as e:
            # Note: évite logger ici pour ne pas relancer la récursion
            print(f"Erreur lors de la récupération de l'utilisateur: {e}")
            return None

    @staticmethod
    def get_by_email(email: str, db):
        """
        Récupère un utilisateur par email.
        :param email: l'email de l'utilisateur
        :param db: instance de DatabaseManager (ou objet avec méthode get_cursor())
        :return: instance Utilisateur ou None
        """
        if db is None:
            return None
        try:
            with db.get_cursor(dictionary=True) as cursor:
                cursor.execute(
                    "SELECT id, nom, prenom, email, mot_de_passe FROM utilisateurs WHERE email = %s",
                    (email,)
                )
                row = cursor.fetchone()
                if row:
                    return Utilisateur(
                        row['id'],
                        row['nom'],
                        row['prenom'],
                        row['email'],
                        row['mot_de_passe']
                    )
                return None
        except Exception as e:
            print(f"Erreur lors de la récupération de l'utilisateur par email: {e}")
            return None

    @staticmethod
    def create(nom: str, prenom: str, email: str, mot_de_passe: str, db):
        """
        Crée un nouvel utilisateur dans la base de données.
        """
        if db is None:
            return False
        try:
            with db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO utilisateurs (nom, prenom, email, mot_de_passe)
                    VALUES (%s, %s, %s, %s)
                """, (nom, prenom, email, mot_de_passe))
                user_id = cursor.lastrowid
                logger.info(f"Utilisateur créé avec ID: {user_id}")
            return user_id
        except Exception as e:
            logger.error(f"Erreur création utilisateur : {e}")
            return False

class DatabaseManager:
    """
    Gère la connexion à la base de données en utilisant un pool de connexions
    pour une gestion plus robuste et performante, avec la bibliothèque pymysql.
    """
    def __init__(self, db_config):
        self.db_config = db_config
        self._connection_pool = None


    def _get_connection_pool(self):
        """Initialise et retourne le pool de connexions avec DBUtils."""
        if self._connection_pool is None:
            logger.info("Initialisation du pool de connexions avec DBUtils...")
            try:
                self._connection_pool = PooledDB(
                    creator=pymysql,
                    maxconnections=5,
                    mincached=2,
                    maxcached=5,
                    maxshared=0,
                    blocking=True,
                    maxusage=None,
                    setsession=None,
                    reset=True,
                    failures=None,
                    ping=1,
                    **self.db_config
                )
                logger.info("Pool de connexions DBUtils initialisé avec succès.")
            except Error as err:
                logger.error(f"Erreur lors de l'initialisation du pool de connexions : {err}")
                self._connection_pool = None
        return self._connection_pool
    def close_connection(self):
        """
        Ferme le pool de connexions.
        Cette méthode est optionnelle car DBUtils gère normalement la fermeture automatiquement.
        """
        if self._connection_pool is not None:
            self._connection_pool.close()
            self._connection_pool = None
            logger.info("Pool de connexions fermé")
    
    def close(self):
        """Alias pour close_connection pour compatibilité"""
        self.close_connection()
    @contextmanager
    def get_cursor(self, dictionary=False, commit=True):
        """
        Fournit un curseur de base de données depuis le pool.
        Gère automatiquement la connexion et la fermeture des ressources.

        :param dictionary: Si True, retourne un curseur de type dictionnaire
        :param commit: Si True, commit la transaction après l'exécution
        """
        connection = None
        cursor = None
        try:
            pool = self._get_connection_pool()
            if not pool:
                raise RuntimeError("Impossible d'obtenir une connexion à la base de données.")

            # Obtient une connexion du pool
            connection = pool.connection()

            # Crée un curseur (dictionnaire si nécessaire)
            cursor = connection.cursor(pymysql.cursors.DictCursor) if dictionary else connection.cursor()

            yield cursor

            # Commit la transaction après une exécution réussie si commit=True
            if commit:
                connection.commit()
        except Exception as e:
            logger.error(f"Erreur dans le gestionnaire de curseur : {e}", exc_info=True)
            if connection:
                try:
                    connection.rollback()  # Annule les changements en cas d'erreur
                except Exception as rollback_error:
                    logger.error(f"Erreur lors du rollback : {rollback_error}", exc_info=True)
            raise  # Relance l'exception
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception as close_error:
                    logger.error(f"Erreur lors de la fermeture du curseur : {close_error}", exc_info=True)
            if connection:
                try:
                    connection.close()  # Retourne la connexion au pool
                except Exception as close_error:
                    logger.error(f"Erreur lors de la fermeture de la connexion : {close_error}", exc_info=True)

    def create_tables(self):
        """
        Crée toutes les tables de la base de données si elles n'existent pas.
        """
        logger.info("Vérification et création des tables de la base de données...")
        try:
            # Utilisation du gestionnaire de contexte pour la création des tables.
            with self.get_cursor() as cursor:

                # Table utilisateurs
                create_users_table_query = """
                CREATE TABLE IF NOT EXISTS utilisateurs (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nom VARCHAR(255) NOT NULL,
                    prenom VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    mot_de_passe VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
                cursor.execute(create_users_table_query)

                # Table PeriodeFavorite
                create_periode_favorite_table_query = """
                CREATE TABLE IF NOT EXISTS periode_favorite (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    compte_id INT NOT NULL,
                    compte_type ENUM('principal','sous_compte') NOT NULL,
                    nom VARCHAR(255) NOT NULL,
                    date_debut DATE NOT NULL,
                    date_fin DATE NOT NULL,
                    statut ENUM('active','inactive') DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_periode_favorite_table_query)

                # Table banques
                create_banques_table_query = """
                CREATE TABLE IF NOT EXISTS banques (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nom VARCHAR(255) NOT NULL,
                    code_banque VARCHAR(50) UNIQUE,
                    pays VARCHAR(100) DEFAULT 'Suisse',
                    couleur VARCHAR(7) DEFAULT '#3498db',
                    site_web VARCHAR(255),
                    logo_url VARCHAR(255),
                    actif BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
                cursor.execute(create_banques_table_query)

                # Table comptes_principaux
                create_comptes_table_query = """
                CREATE TABLE IF NOT EXISTS comptes_principaux (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    utilisateur_id INT NOT NULL,
                    banque_id INT NOT NULL,
                    nom_compte VARCHAR(255) NOT NULL,
                    numero_compte VARCHAR(255),
                    iban VARCHAR(34),
                    bic VARCHAR(11),
                    type_compte ENUM('courant', 'epargne', 'compte_jeune', 'autre') DEFAULT 'courant',
                    solde DECIMAL(15,2) DEFAULT 0.00,
                    devise VARCHAR(3) DEFAULT 'CHF',
                    date_ouverture DATE,
                    actif BOOLEAN DEFAULT TRUE,
                    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id),
                    FOREIGN KEY (banque_id) REFERENCES banques(id)
                );
                """
                cursor.execute(create_comptes_table_query)

                # Table sous_comptes
                create_sous_comptes_table_query = """
                CREATE TABLE IF NOT EXISTS sous_comptes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    compte_principal_id INT NOT NULL,
                    nom_sous_compte VARCHAR(255) NOT NULL,
                    description TEXT,
                    objectif_montant DECIMAL(15,2),
                    solde DECIMAL(15,2) DEFAULT 0.00,
                    couleur VARCHAR(7) DEFAULT '#28a745',
                    icone VARCHAR(50) DEFAULT 'piggy-bank',
                    date_objectif DATE,
                    actif BOOLEAN DEFAULT TRUE,
                    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (compte_principal_id) REFERENCES comptes_principaux(id)
                );
                """
                cursor.execute(create_sous_comptes_table_query)

                # Table transactions
                create_transactions_table_query = """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    compte_principal_id INT,
                    sous_compte_id INT,
                    compte_source_id INT,
                    sous_compte_source_id INT,
                    compte_destination_id INT,
                    sous_compte_destination_id INT,
                    type_transaction ENUM('depot', 'retrait', 'transfert_entrant', 'transfert_sortant', 'transfert_externe', 'recredit_annulation', 'transfert_compte_vers_sous', 'transfert_sous_vers_compte') NOT NULL,
                    montant DECIMAL(15,2) NOT NULL,
                    description TEXT,
                    reference VARCHAR(100),
                    utilisateur_id INT NOT NULL,
                    date_transaction DATETIME NOT NULL,
                    solde_apres DECIMAL(15,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (compte_principal_id) REFERENCES comptes_principaux(id),
                    FOREIGN KEY (sous_compte_id) REFERENCES sous_comptes(id),
                    FOREIGN KEY (compte_source_id) REFERENCES comptes_principaux(id),
                    FOREIGN KEY (sous_compte_source_id) REFERENCES sous_comptes(id),
                    FOREIGN KEY (compte_destination_id) REFERENCES comptes_principaux(id),
                    FOREIGN KEY (sous_compte_destination_id) REFERENCES sous_comptes(id),
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_transactions_table_query)

                # Table categories_transactions
                create_categories_table_query = """
                CREATE TABLE IF NOT EXISTS categories_transactions (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    utilisateur_id INT NOT NULL,
                    nom VARCHAR(100) NOT NULL,
                    description TEXT,
                    type_categorie ENUM('Revenu', 'Dépense', 'Transfert') NOT NULL DEFAULT 'Dépense',
                    couleur VARCHAR(7) DEFAULT '#007bff',
                    icone VARCHAR(50),
                    budget_mensuel DECIMAL(15,2) DEFAULT 0,
                    actif BOOLEAN DEFAULT TRUE,
                    date_creation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id),
                    UNIQUE KEY unique_categorie_user (utilisateur_id, nom, type_categorie)
                );
                """
                cursor.execute(create_categories_table_query)

                # table transactions_categories
                create_transactions_categories_table_query = """
                CREATE TABLE IF NOT EXISTS transaction_categories (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    transaction_id INT NOT NULL,
                    categorie_id INT NOT NULL,
                    utilisateur_id INT NOT NULL,
                    date_association TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
                    FOREIGN KEY (categorie_id) REFERENCES categories_transactions(id) ON DELETE CASCADE,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id),
                    UNIQUE KEY unique_transaction_categorie (transaction_id, categorie_id)
                );
                """
                cursor.execute(create_transactions_categories_table_query)
                # Table transferts_externes
                create_transferts_externes_table_query = """
                CREATE TABLE IF NOT EXISTS transferts_externes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    transaction_id INT NOT NULL,
                    iban_dest VARCHAR(34) NOT NULL,
                    bic_dest VARCHAR(11),
                    nom_dest VARCHAR(255) NOT NULL,
                    montant DECIMAL(15,2) NOT NULL,
                    devise VARCHAR(3) DEFAULT 'EUR',
                    statut ENUM('pending', 'processed', 'cancelled') DEFAULT 'pending',
                    date_demande TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    date_traitement TIMESTAMP NULL,
                    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
                );
                """
                cursor.execute(create_transferts_externes_table_query)

                # Table categories_comptables
                create_categories_table_query = """
                CREATE TABLE IF NOT EXISTS categories_comptables (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    numero VARCHAR(10) NOT NULL UNIQUE,
                    nom VARCHAR(255) NOT NULL,
                    parent_id INT,
                    type_compte ENUM('Actif', 'Passif', 'Charge', 'Revenus') NOT NULL,
                    compte_systeme BOOLEAN DEFAULT FALSE,
                    compte_associe VARCHAR(10),
                    type_tva ENUM('taux_plein', 'taux_reduit', 'taux_zero', 'exonere') DEFAULT 'taux_plein',
                    actif BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                );
                """
                cursor.execute(create_categories_table_query)

                # Table contacts
                create_contacts_table_query = """
                CREATE TABLE IF NOT EXISTS contacts (
                    id_contact INT AUTO_INCREMENT PRIMARY KEY,
                    nom VARCHAR(255) NOT NULL,
                    email VARCHAR(255),
                    telephone VARCHAR(20),
                    adresse TEXT,
                    code_postal VARCHAR(10),
                    ville VARCHAR(100),
                    pays VARCHAR(100),
                    utilisateur_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_contacts_table_query)


                # Table contact plan
                create_contact_plans_table_query = """
                CREATE TABLE IF NOT EXISTS contact_plans(
                contact_id INT NOT NULL,
                plan_id INT NOT NULL,
                PRIMARY KEY (contact_id, plan_id),
                FOREIGN KEY (contact_id) REFERENCES contacts(id_contact) ON DELETE CASCADE,
                FOREIGN KEY (plan_id) REFERENCES plans_comptables(id) ON DELETE CASCADE
                )
                """
                cursor.execute(create_contact_plans_table_query)


                #Table ecritures_comptables
                create_ecritures_table_query = """
                CREATE TABLE IF NOT EXISTS ecritures_comptables (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date_ecriture DATE NOT NULL,
                    compte_bancaire_id INT NOT NULL,
                    sous_compte_id INT,
                    categorie_id INT NOT NULL,
                    montant DECIMAL(15,2) NOT NULL,
                    montant_htva DECIMAL(15,2) NOT NULL,
                    devise VARCHAR(3) DEFAULT 'CHF',
                    description TEXT,
                    id_contact INT,
                    reference VARCHAR(100),
                    type_ecriture ENUM('depense', 'recette') NOT NULL,
                    tva_taux DECIMAL(5,2),
                    tva_montant DECIMAL(15,2),
                    utilisateur_id INT NOT NULL,
                    justificatif_url VARCHAR(255),
                    statut ENUM('pending', 'validée', 'rejetée') DEFAULT 'pending',
                    date_validation TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (compte_bancaire_id) REFERENCES comptes_principaux(id),
                    FOREIGN KEY (sous_compte_id) REFERENCES sous_comptes(id),
                    FOREIGN KEY (categorie_id) REFERENCES categories_comptables(id),
                    FOREIGN KEY (id_contact) REFERENCES contacts(id_contact),
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_ecritures_table_query)

                # Table Plan comptable
                create_plan_comptable_table_query = """
                CREATE TABLE IF NOT EXISTS plans_comptables (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    nom VARCHAR(100) NOT NULL,
                    description TEXT,
                    devise VARCHAR(3) DEFAULT 'CHF',
                    utilisateur_id INT NOT NULL,
                    actif TINYINT(1) DEFAULT 1,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
                );
                """
                cursor.execute(create_plan_comptable_table_query)

                # Table plan_category
                create_plan_categorie_table_query = """
                CREATE TABLE IF NOT EXISTS plan_categorie (
                    plan_id INT NOT NULL,
                    categorie_id INT NOT NULL,
                    PRIMARY KEY (plan_id, categorie_id),
                    FOREIGN KEY (plan_id) REFERENCES plans_comptables(id) ON DELETE CASCADE,
                    FOREIGN KEY (categorie_id) REFERENCES categories_comptables(id) ON DELETE CASCADE
                );
                """
                cursor.execute(create_plan_categorie_table_query)


                # Table contactCompte
                create_contact_compte_table_query = """
                CREATE TABLE IF NOT EXISTS contact_comptes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    contact_id INT NOT NULL,
                    compte_id INT NOT NULL,
                    utilisateur_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    -- Clés étrangères
                    FOREIGN KEY (contact_id) REFERENCES contacts(id_contact) ON DELETE CASCADE,
                    FOREIGN KEY (compte_id) REFERENCES comptes_principaux(id) ON DELETE CASCADE,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id) ON DELETE CASCADE,

                    -- Contrainte d'unicité : un utilisateur ne peut lier un contact à un compte qu'une seule fois
                    UNIQUE KEY unique_contact_compte_user (contact_id, compte_id, utilisateur_id),

                    -- Index pour les recherches fréquentes
                    INDEX idx_contact_user (contact_id, utilisateur_id),
                    INDEX idx_compte_user (compte_id, utilisateur_id)
                );
                """
                cursor.execute(create_contact_compte_table_query)

                # Table parametres_utilisateur
                create_parametres_table_query = """
                CREATE TABLE IF NOT EXISTS parametres_utilisateur (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    utilisateur_id INT NOT NULL UNIQUE,
                    devise_principale VARCHAR(3) DEFAULT 'CHF',
                    theme ENUM('clair', 'sombre') DEFAULT 'clair',
                    notifications_email BOOLEAN DEFAULT TRUE,
                    alertes_solde BOOLEAN DEFAULT TRUE,
                    seuil_alerte_solde DECIMAL(15,2) DEFAULT 500.00,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_parametres_table_query)

                # Table heures_travail
                create_heures_travail_table_query = """
                CREATE TABLE IF NOT EXISTS heures_travail (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date DATE NOT NULL,
                    user_id INT NOT NULL,
                    employe_id INT NULL,
                    h1d TIME,
                    h1f TIME,
                    h2d TIME,
                    h2f TIME,
                    total_h DECIMAL(5,2),
                    type_heures ENUM('reelles', 'simulees') NOT NULL DEFAULT 'reelles',
                    vacances BOOLEAN DEFAULT FALSE,
                    jour_semaine VARCHAR(10),
                    semaine_annee INT,
                    mois INT,
                    employeur VARCHAR(255),
                    id_contrat INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_date_user_contrat_employe (date, user_id, id_contrat, employe_id),
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id) ON DELETE CASCADE,
                    FOREIGN KEY (employe_id) REFERENCES employes(id) ON DELETE SET NULL,
                    FOREIGN KEY (id_contrat) REFERENCES contrats(id) ON DELETE CASCADE
                );
                """
                cursor.execute(create_heures_travail_table_query)

                # Table heures_simules
                create_heures_simules_table_query = """
                CREATE TABLE heures_simulees (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                employe_id INT NOT NULL,
                equipe_id INT NULL,
                date DATE NOT NULL,
                h1d TIME,            -- heure début
                h2f TIME,            -- heure fin
                total_h FLOAT,       -- heures totales
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (employe_id) REFERENCES employes(id),
                FOREIGN KEY (equipe_id) REFERENCES equipes(id)
                );"""
                cursor.execute(create_heures_simules_table_query)

                # Table salaires
                create_salaires_table_query = """
                CREATE TABLE IF NOT EXISTS salaires (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    mois INT NOT NULL,
                    annee INT NOT NULL,
                    heures_reelles DECIMAL(7,2),
                    salaire_horaire DECIMAL(7,2) DEFAULT 24.05,
                    salaire_calcule DECIMAL(10,2),
                    salaire_net DECIMAL(10,2),
                    salaire_verse DECIMAL(10,2),
                    acompte_25 DECIMAL(10,2),
                    acompte_10 DECIMAL(10,2),
                    acompte_25_estime DECIMAL(10,2),
                    acompte_10_estime DECIMAL(10,2),
                    difference DECIMAL(10,2),
                    difference_pourcent DECIMAL(5,2),
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_salaires_table_query)

                # Table synthese_hebdo
                create_synthese_hebdo_table_query = """
                CREATE TABLE IF NOT EXISTS synthese_hebdo (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    semaine_numero INT NOT NULL,
                    annee INT NOT NULL,
                    heures_reelles DECIMAL(7,2),
                    heures_simulees DECIMAL(7,2),
                    difference DECIMAL(7,2),
                    moyenne_mobile DECIMAL(7,2),
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_synthese_hebdo_table_query)

                # Table synthese_mensuelle
                create_synthese_mensuelle_table_query = """
                CREATE TABLE IF NOT EXISTS synthese_mensuelle (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    mois INT NOT NULL,
                    annee INT NOT NULL,
                    heures_reelles DECIMAL(7,2),
                    heures_simulees DECIMAL(7,2),
                    salaire_reel DECIMAL(10,2),
                    salaire_simule DECIMAL(10,2),
                    user_id INT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_synthese_mensuelle_table_query)

                # Table contrats
                create_contrats_table_query = """
                CREATE TABLE IF NOT EXISTS contrats (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    heures_hebdo DECIMAL(4,2) NOT NULL,
                    date_debut DATE NOT NULL,
                    date_fin DATE,
                    salaire_horaire DECIMAL(7,2) DEFAULT 24.05,
                    jour_estimation_salaire INT DEFAULT 15,
                    versement_10 BOOLEAN DEFAULT TRUE,
                    versement_25 BOOLEAN DEFAULT TRUE,
                    indemnite_vacances_tx DECIMAL(5,2),
                    indemnite_jours_feries_tx DECIMAL(5,2),
                    indemnite_jour_conges_tx DECIMAL(5,2),
                    indemnite_repas_tx DECIMAL(5,2),
                    indemnite_retenues_tx DECIMAL(5,2),
                    cotisation_avs_tx DECIMAL(5,2),
                    cotisation_ac_tx DECIMAL(5,2),
                    cotisation_accident_n_prof_tx DECIMAL(5,2),
                    cotisation_assurance_indemnite_maladie_tx DECIMAL(5,2),
                    cotisation_cap_tx DECIMAL(5,2),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
                );
                """
                cursor.execute(create_contrats_table_query)

                # Tables types_cotisation 
                create_types_cotisation_table_query = """
                CREATE TABLE IF NOT EXISTS types_cotisation (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                nom VARCHAR(100) NOT NULL,
                description TEXT,
                est_obligatoire BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
                );"""
                cursor.execute(create_types_cotisation_table_query)

                # Tables types_indemnite 
                create_types_indemnite_table_query = """
                CREATE TABLE IF NOT EXISTS types_indemnite (
                id INT PRIMARY KEY AUTO_INCREMENT,
                user_id INT NOT NULL,
                nom VARCHAR(100) NOT NULL,
                description TEXT,
                est_obligatoire BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
              );"""
                cursor.execute(create_types_indemnite_table_query)

                # cotisations_contrat
                create_cotisations_contrat_table_query = """
                CREATE TABLE IF NOT EXISTS cotisations_contrat (
                id INT PRIMARY KEY AUTO_INCREMENT,
                contrat_id INT NOT NULL,
                type_cotisation_id INT NOT NULL,
                taux DECIMAL(10,4) NOT NULL, -- peut être % ou montant fixe
                base_calcul ENUM('brut', 'brut_tot') DEFAULT 'brut',
                annee YEAR NOT NULL,
                actif BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_contrat_type_annee (contrat_id, type_cotisation_id, annee),
                FOREIGN KEY (contrat_id) REFERENCES contrats(id) ON DELETE CASCADE,
                FOREIGN KEY (type_cotisation_id) REFERENCES types_cotisation(id) ON DELETE CASCADE
               );
                """
                cursor.execute(create_cotisations_contrat_table_query)

                 # indemnites_contrat
                create_indemnites_contrat_table_query = """
                CREATE TABLE IF NOT EXISTS indemnites_contrat (
                id INT PRIMARY KEY AUTO_INCREMENT,
                contrat_id INT NOT NULL,
                type_indemnite_id INT NOT NULL,
                taux DECIMAL(10,4) NOT NULL, -- interprété comme % du brut
                base_calcul ENUM('brut', 'brut_tot') DEFAULT 'brut',
                annee YEAR NOT NULL,
                actif BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_contrat_type_annee (contrat_id, type_indemnite_id, annee),
                FOREIGN KEY (contrat_id) REFERENCES contrats(id) ON DELETE CASCADE,
                FOREIGN KEY (type_indemnite_id) REFERENCES types_indemnite(id) ON DELETE CASCADE
                );
                """
                cursor.execute(create_indemnites_contrat_table_query)
                # regles_cotisation

                create_regles_cotisations_table_query = """
                CREATE TABLE IF NOT EXISTS regles_cotisation (
                id INT AUTO_INCREMENT PRIMARY KEY,
                type_cotisation_id INT NOT NULL,
                seuil_min DECIMAL(10,2) DEFAULT 0.00,   -- salaire mensuel brut minimum inclus
                seuil_max DECIMAL(10,2) DEFAULT NULL,   -- NULL = sans limite
                montant_fixe DECIMAL(10,2) DEFAULT 0.00,
                taux DECIMAL(5,2) DEFAULT 0.00,         -- à utiliser si montant non fixe
                type_valeur ENUM('taux','fixe') NOT NULL DEFAULT 'fixe',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (type_cotisation_id) REFERENCES types_cotisation(id) ON DELETE CASCADE
                );"""
                cursor.execute(create_regles_cotisations_table_query)
                 # baremes_indemnite

                create_baremes_indemnite_table_query = """
                CREATE TABLE IF NOT EXISTS baremes_indemnite (
                id INT AUTO_INCREMENT PRIMARY KEY,
                type_indemnite_id INT NOT NULL,
                seuil_min DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                seuil_max DECIMAL(10,2) DEFAULT NULL,
                montant_fixe DECIMAL(10,2) NOT NULL DEFAULT 0.00,
                taux DECIMAL(5,2) NOT NULL DEFAULT 0.00,
                type_valeur ENUM('taux','fixe') NOT NULL DEFAULT 'fixe',
                ordre INT NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (type_indemnite_id) REFERENCES types_indemnite(id) ON DELETE CASCADE
                 );"""
                cursor.execute(create_baremes_indemnite_table_query)

                #plages_horaires
                create_plages_horaires_table_query = """
                CREATE TABLE IF NOT EXISTS plages_horaires (
                id INT PRIMARY KEY AUTO_INCREMENT,
                heure_travail_id INT NOT NULL,
                ordre TINYINT NOT NULL,
                debut TIME,
                fin TIME,
                FOREIGN KEY (heure_travail_id) REFERENCES heures_travail(id) ON DELETE CASCADE,
                UNIQUE KEY unique_heure_travail_ordre (heure_travail_id, ordre)
                );
                """
                cursor.execute(create_plages_horaires_table_query)


                # Table employe
                create_employes_table_query = """
                CREATE TABLE IF NOT EXISTS employes (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL,
                    nom VARCHAR(100) NOT NULL,
                    prenom VARCHAR(100) NOT NULL,
                    email VARCHAR(150),
                    telephone VARCHAR(20),
                    rue VARCHAR(255),
                    code_postal VARCHAR(10),
                    commune VARCHAR(100),
                    genre ENUM('M', 'F') NOT NULL,
                    date_de_naissance DATE NOT NULL,
                    code_acces_salaire VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
                );"""
                cursor.execute(create_employes_table_query)

                #Table equipes
                create_equipes_table_query = """
                CREATE TABLE IF NOT EXISTS equipes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                nom VARCHAR(100) NOT NULL,
                description VARCHAR(255) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
                );"""
                cursor.execute(create_equipes_table_query)


                #Table equipes_employes
                create_equipes_employes_table_query = """
                CREATE TABLE IF NOT EXISTS equipes_employes (
                equipe_id INT,
                employe_id INT,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (equipe_id, employe_id),
                FOREIGN KEY (equipe_id) REFERENCES equipes(id) ON DELETE CASCADE,
                FOREIGN KEY (employe_id) REFERENCES employes(id) ON DELETE CASCADE
                );"""
                cursor.execute(create_equipes_employes_table_query)

                #Table competences
                create_competences_table_query = """
                CREATE TABLE IF NOT EXISTS competences (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                nom VARCHAR(100) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
                );
                """
                cursor.execute(create_competences_table_query)

                #Table employes_competences
                create_equipes_competences_table_query = """
                CREATE TABLE IF NOT EXISTS employes_competences (
                competence_id INT,
                employe_id INT,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (competence_id, employe_id),
                FOREIGN KEY (competence_id) REFERENCES competences(id) ON DELETE CASCADE,
                FOREIGN KEY (employe_id) REFERENCES employes(id) ON DELETE CASCADE
                );"""
                cursor.execute(create_equipes_competences_table_query)




                # #Table equipes_competences_requises
                create_equipes_competences_requises_table_query = """
                CREATE TABLE IF NOT EXISTS equipes_competences_requises (
                equipe_id INT,
                competence_id INT,
                quantite_min INT DEFAULT 1,
                PRIMARY KEY (equipe_id, competence_id),
                FOREIGN KEY (equipe_id) REFERENCES equipes(id) ON DELETE CASCADE,
                FOREIGN KEY (competence_id) REFERENCES competences(id) ON DELETE CASCADE
                );
                """
                cursor.execute(create_equipes_competences_requises_table_query)

                #Table palnning regles
                create_planning_regles_table_query = """
                CREATE TABLE IF NOT EXISTS planning_regles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                nom VARCHAR(150) NOT NULL,
                type_regle VARCHAR(50) NOT NULL,
                params_json JSON NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
                );"""
                cursor.execute(create_planning_regles_table_query)

                # Table entreprise
                create_entreprise_table_query = """
                CREATE TABLE IF NOT EXISTS entreprise (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL UNIQUE,
                nom VARCHAR(255) NOT NULL,
                rue VARCHAR(255),
                code_postal VARCHAR(20),
                commune VARCHAR(100),
                email VARCHAR(255),
                telephone VARCHAR(50),
                logo_path VARCHAR(255),  -- ex: 'uploads/logos/user_123.png'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );"""
                cursor.execute(create_entreprise_table_query)



            logger.info("Toutes les tables ont été vérifiées/créées avec succès.")

        except Exception as e:
            logger.error(f"Erreur lors de la création des tables : {e}")

class PeriodeFavorite:
    def __init__(self, db):
        self.db = db

    def get_by_user_id(self, user_id: int) -> List[Dict]:
        """Récupère toutes les périodes favorites d'un utilisateur"""
        periodes = []
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT id, user_id, compte_id, compte_type, nom, date_debut, date_fin
                    FROM periode_favorite
                    WHERE user_id = %s AND statut = 'active'
                    ORDER BY date_debut DESC
                    """
                cursor.execute(query, (user_id,))
                periodes = cursor.fetchall()
                return periodes
        except Error as e:
            logger.error(f"Erreur lors de la récupération des périodes favorites: {e}")
            return []
        return periodes

    def create(self, user_id: int, compte_id: int, compte_type: str, nom: str, date_debut: date, date_fin: date, statut: str) -> bool:
        """Crée une nouvelle période favorite."""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO periode_favorite (user_id, compte_id, compte_type, nom, date_debut, date_fin, statut)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (user_id, compte_id, compte_type, nom, date_debut, date_fin, statut))
                return True
        except Error as e:
            logger.error(f"Erreur lors de la création de la période favorite: {e}")
            return False

    def update(self, user_id: int, periode_id: int, nom: str, date_debut: date, date_fin: date, statut: str) -> bool:
        """Met à jour une période favorite existante."""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE periode_favorite
                SET nom = %s, date_debut = %s, date_fin = %s, statut = %s
                WHERE id = %s AND user_id = %s
                """
                cursor.execute(query, (nom, date_debut, date_fin, statut, periode_id, user_id))
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour de la période favorite: {e}")
            return False

    def delete(self, user_id: int, periode_id: int) -> bool:
        """Supprime une période favorite par son ID."""
        try:
            with self.db.get_cursor() as cursor:
                query = "DELETE FROM periode_favorite WHERE id = %s AND user_id = %s"
                cursor.execute(query, (periode_id, user_id))
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur lors de la suppression de la période favorite: {e}")
            return False
    def get_by_user_and_compte(self, user_id: int, compte_id: int, compte_type: str) -> Optional[Dict]:
        """Récupère une période favorite par utilisateur et compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT id, user_id, compte_id, compte_type, nom, date_debut, date_fin, statut
                FROM periode_favorite
                WHERE user_id = %s AND compte_id = %s AND compte_type = %s AND statut = 'active'
                ORDER BY date_debut DESC
                LIMIT 1
                """
                cursor.execute(query, (user_id, compte_id, compte_type))
                periode = cursor.fetchone()
                return periode
        except Error as e:
            logger.error(f"Erreur lors de la récupération de la période favorite: {e}")
            return None

class Banque:
    """Modèle pour les banques - nettoyé de toute logique transactionnelle"""

    def __init__(self, db):
        self.db = db
    def get_all(self) -> List[Dict]:
        """Récupère toutes les banques actives"""
        banques = []
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT id, nom, code_banque, pays, couleur, site_web, logo_url
                    FROM banques
                    WHERE actif = TRUE
                    ORDER BY nom
                    """
                cursor.execute(query)
                banques = cursor.fetchall()
                return banques
        except Error as e:
            logger.error(f"Erreur lors de la récupération des banques: {e}")
            return []
        return banques

    def get_by_id(self, banque_id: int) -> Optional[Dict]:
        """Récupère une banque par son ID"""
        banque = []
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM banques WHERE id = %s AND actif = TRUE"
                cursor.execute(query, (banque_id,))
                banque = cursor.fetchone()
                return banque
        except Error as e:
            logger.error(f"Erreur lors de la récupération de la banque: {e}")
            return None

    def create_banque(self, nom: str, code_banque: str, pays: str, couleur: str, site_web: str, logo_url: str) -> bool:
        """Crée une nouvelle banque."""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO banques (nom, code_banque, pays, couleur, site_web, logo_url, actif)
                VALUES (%s, %s, %s, %s, %s, %s, TRUE)
                """
                cursor.execute(query, (nom, code_banque, pays, couleur, site_web, logo_url))
                return True
        except Error as e:
            logger.error(f"Erreur lors de la création de la banque: {e}")
            return False

    def update_banque(self, banque_id: int, nom: str, code_banque: str, pays: str, couleur: str, site_web: str, logo_url: str) -> bool:
        """Met à jour une banque existante."""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE banques
                SET nom = %s, code_banque = %s, pays = %s, couleur = %s, site_web = %s, logo_url = %s
                WHERE id = %s
                """
                cursor.execute(query, (nom, code_banque, pays, couleur, site_web, logo_url, banque_id))
                return cursor.rowcount > 0 # Returns True if at least one row was updated
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour de la banque: {e}")
            return False

    def delete_banque(self, banque_id: int) -> bool:
        """Désactive (supprime logiquement) une banque par son ID."""
        try:
            with self.db.get_cursor() as cursor:
                query = "UPDATE banques SET actif = FALSE WHERE id = %s"
                cursor.execute(query, (banque_id,))
                return cursor.rowcount > 0 # Returns True if the row was found and updated
        except Error as e:
            logger.error(f"Erreur lors de la suppression de la banque: {e}")
            return False

class ComptePrincipal:
    """Modèle pour les comptes principaux"""

    def __init__(self, db):
        self.db = db

    def get_by_user_id(self, user_id: int) -> List[Dict]:
        """Récupère tous les comptes d'un utilisateur"""
        try:
            with self.db.get_cursor() as cursor:
                # La ligne "cursor = connection.cursor()" est redondante et incorrecte.
                # L'objet 'cursor' est déjà fourni par le gestionnaire de contexte.
                query = """
                SELECT
                    c.id, c.banque_id, c.nom_compte, c.numero_compte, c.iban, c.bic,
                    c.type_compte, c.solde, c.solde_initial, c.devise, c.date_ouverture,
                    c.actif, c.date_creation,
                    b.id as banque_id, b.nom as nom_banque, b.code_banque, b.couleur as couleur_banque,
                    b.logo_url
                FROM comptes_principaux c
                JOIN banques b ON c.banque_id = b.id
                WHERE c.utilisateur_id = %s AND c.actif = TRUE
                ORDER BY c.date_creation DESC
                """
                cursor.execute(query, (user_id,))
                comptes = cursor.fetchall() # N'oubliez pas de récupérer les données
                logger.info(f"models 710 - Comptes récupérés - comptes - pour l'utilisateur {user_id}: {len(comptes)}")
                return comptes
        except Error as e:
            logger.error(f"713 Erreur lors de la récupération des comptes: {e}")
            return []

    def get_by_id(self, compte_id: int) -> Optional[Dict]:
        """Récupère un compte par son ID"""
        try:
            # Correction de la syntaxe 'with self.db.get.cursor() as cursor;'
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    c.*,
                    b.nom as nom_banque, b.code_banque, b.couleur as couleur_banque,
                    u.nom as nom_utilisateur
                FROM comptes_principaux c
                JOIN banques b ON c.banque_id = b.id
                JOIN utilisateurs u ON c.utilisateur_id = u.id
                WHERE c.id = %s AND c.actif = TRUE
                """
                cursor.execute(query, (compte_id,))
                compte = cursor.fetchone() # N'oubliez pas de récupérer la donnée
                return compte
        except Error as e:
            logger.error(f"Erreur lors de la récupération du compte: {e}")
            return None

    def create(self, data: Dict) -> bool:
        """Crée un nouveau compte principal"""
        try:
            # Correction de la syntaxe 'with self.db.get.cursor()'
            with self.db.get_cursor() as cursor:
                # Ces vérifications sont des requêtes SELECT, elles n'ont pas besoin d'être dans une transaction.
                cursor.execute("SELECT id FROM utilisateurs WHERE id = %s", (data['utilisateur_id'],))
                if not cursor.fetchone():
                    logger.error(f"746 Erreur: Utilisateur avec ID {data['utilisateur_id']} n'existe pas")
                    return False

                cursor.execute("SELECT id FROM banques WHERE id = %s", (data['banque_id'],))
                if not cursor.fetchone():
                    logger.error(f"Erreur: Banque avec ID {data['banque_id']} n'existe pas")
                    return False

                query = """
                INSERT INTO comptes_principaux
                (utilisateur_id, banque_id, nom_compte, numero_compte, iban, bic,
                type_compte, solde, solde_initial, devise, date_ouverture)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    data['utilisateur_id'], data['banque_id'], data['nom_compte'],
                    data['numero_compte'], data.get('iban', ''), data.get('bic', ''),
                    data['type_compte'], data.get('solde', 0), data.get('solde_initial', 0), data.get('devise', 'CHF'),
                    data.get('date_ouverture')
                )
                cursor.execute(query, values)
                return True
        except Error as e:
            logger.error(f"769 Erreur lors de la création du compte: {e}")
            return False

    def update_solde(self, compte_id: int, nouveau_solde: Decimal) -> bool:
        """Met à jour le solde d'un compte"""
        try:
            # Correction de la syntaxe 'with self.db.get.cursor()'
            with self.db.get_cursor() as cursor:
                query = "UPDATE comptes_principaux SET solde = %s WHERE id = %s"
                cursor.execute(query, (nouveau_solde, compte_id))
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"781 Erreur lors de la mise à jour du solde: {e}")
            return False

    def get_solde_total_avec_sous_comptes(self, compte_id: int) -> Decimal:
        """
        Calcule le solde total d'un compte principal, en incluant ses sous-comptes.
        """
        try:
            # Note: J'ai remplacé self.db par self.db pour plus de cohérence.
            with self.db.get_cursor() as cursor:
                # Utilisation d'une requête SQL directe pour éviter une fonction de base de données.
                query = """
                SELECT
                    (SELECT COALESCE(SUM(solde), 0) FROM sous_comptes WHERE compte_principal_id = %s) +
                    (SELECT solde FROM comptes_principaux WHERE id = %s) as solde_total
                """
                cursor.execute(query, (compte_id, compte_id))
                result = cursor.fetchone()

                # Le curseur retourne un dictionnaire, donc nous vérifions si 'solde_total' est présent.
                # L'ancienne version retournait une erreur si le résultat était vide.
                if result and 'solde_total' in result:
                    return Decimal(str(result['solde_total']))
                else:
                    return Decimal('0')
        except MySQLError as e:
            # J'ai remplacé "Error" par "MySQLError" pour gérer spécifiquement les erreurs de base de données.
            logger.error(f"808 Erreur lors du calcul du solde total pour le compte {compte_id}: {e}")
            return Decimal('0')

    def get_solde_avec_ecritures(self, compte_id: int, date_jusqua: date = None) -> Decimal:
        try:
            # Correction de la syntaxe 'with self.db.get.cursor()'
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s", (compte_id,))
                result = cursor.fetchone()
                solde = Decimal(str(result[0])) if result and result[0] else Decimal('0')

                query = """
                SELECT SUM(CASE
                    WHEN type_ecriture = 'recette' THEN montant
                    WHEN type_ecriture = 'depense' THEN -montant
                    ELSE 0
                END)
                FROM ecritures_comptables
                WHERE compte_bancaire_id = %s AND synchronise = FALSE
                """
                params = [compte_id]
                if date_jusqua:
                    query += " AND date_ecriture <= %s"
                    params.append(date_jusqua)
                cursor.execute(query, tuple(params))
                result = cursor.fetchone()
                ajustement = Decimal(str(result[0])) if result and result[0] else Decimal('0')

                # Suppression des fermetures de connexion/curseur inutiles
                return solde + ajustement
        except Error as e:
            logger.error(f"839Erreur lors du calcul du solde avec écritures: {e}")
            return Decimal('0')

    def get_all_accounts(self) -> List[Dict]:
        # Cette méthode de classe n'est pas cohérente avec les autres méthodes d'instance.
        # Il est préférable de la rendre une méthode d'instance si possible.
        # Si vous devez la garder en l'état, voici la correction.
        comptes = []
        try:
            # Correction de l'utilisation de db
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    c.id, c.utilisateur_id, c.banque_id, c.nom_compte, c.numero_compte,
                    c.iban, c.bic, c.type_compte, c.solde, c.solde_initial, c.devise, c.date_ouverture, c.actif,
                    b.nom as banque_nom, b.code_banque, b.couleur as banque_couleur,
                    u.nom as utilisateur_nom, u.prenom as utilisateur_prenom
                FROM comptes_principaux c
                JOIN banques b ON c.banque_id = b.id
                JOIN utilisateurs u ON c.utilisateur_id = u.id
                WHERE c.actif = TRUE
                ORDER BY b.nom, c.nom_compte
                """
                cursor.execute(query)
                comptes = cursor.fetchall()
                return comptes if comptes else []
        except Error as e:
            logger.error(f"Erreur SQL: {e}")
            return []


class ComptePrincipalRapport:
    def __init__(self, db):
        """
        Initialise le générateur de rapports.
        :param db: Instance de connexion à la base de données.
        :param transaction_model: Instance de TransactionFinanciere pour accéder aux méthodes existantes.
        """
        self.db = db
        self.categorie_comptable_model = CategorieComptable(self.db)
    def _get_solde_avant_periode(self, compte_id: int, user_id: int, debut_periode: date) -> Decimal:
        """Retourne le solde juste avant le début de la période."""
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT solde_apres
                FROM transactions
                WHERE compte_principal_id = %s AND date_transaction < %s
                ORDER BY date_transaction DESC, id DESC
                LIMIT 1
            """, (compte_id, debut_periode))
            result = cursor.fetchone()
            if result:
                return Decimal(str(result['solde_apres']))
            else:
                # Aucune transaction → solde initial du compte
                cursor.execute("SELECT solde_initial FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                               (compte_id, user_id))
                result = cursor.fetchone()
                return Decimal(str(result['solde_initial'])) if result else Decimal('0')

    def generer_rapport_periode(self, compte_id: int, user_id: int,
                                periode: str = 'mensuel',
                                date_reference: date = None) -> Dict:
        """
        Génère un rapport détaillé pour un compte sur une période donnée.
        :param compte_id: ID du compte principal.
        :param user_id: ID de l'utilisateur (vérification de propriété).
        :param periode: 'hebdomadaire', 'mensuel' ou 'annuel'.
        :param date_reference: Date de référence pour la période (ex: 15/03/2025 → mars 2025).
        :return: Dictionnaire structuré avec données, graphiques SVG, et métadonnées.
        """
        if date_reference is None:
            date_reference = date.today()

        # 1. Déterminer la plage de dates selon la période
        if periode == 'hebdomadaire':
            debut = date_reference - timedelta(days=date_reference.weekday())  # Lundi
            fin = debut + timedelta(days=6)
            titre = f"Rapport Hebdomadaire - Semaine du {debut.strftime('%d.%m.%Y')}"
        elif periode == 'mensuel':
            debut = date_reference.replace(day=1)
            if date_reference.month == 12:
                fin = date(date_reference.year + 1, 1, 1) - timedelta(days=1)
            else:
                fin = date(date_reference.year, date_reference.month + 1, 1) - timedelta(days=1)
            titre = f"Rapport Mensuel - {debut.strftime('%B %Y')}"
        elif periode == 'annuel':
            debut = date(date_reference.year, 1, 1)
            fin = date(date_reference.year, 12, 31)
            titre = f"Rapport Annuel - {date_reference.year}"
        else:
            raise ValueError("Période doit être 'hebdomadaire', 'mensuel' ou 'annuel'.")

        # 2. Récupérer les statistiques de base
        stats = self.categorie_comptable_model.get_statistiques_compte('compte_principal', compte_id, user_id,
                                                      date_debut=debut.strftime('%Y-%m-%d'),
                                                      date_fin=fin.strftime('%Y-%m-%d'))

        # 3. Récupérer le solde au début et à la fin de la période
        solde_initial = self._get_solde_avant_periode(compte_id, user_id, debut)
        solde_final = self.categorie_comptable_model.get_solde_courant('compte_principal', compte_id, user_id)

        # 4. Récupérer les transactions
        transactions, _ = self.tx_model.get_all_user_transactions(
            user_id=user_id,
            date_from=debut.strftime('%Y-%m-%d'),
            date_to=fin.strftime('%Y-%m-%d'),
            compte_source_id=compte_id,
            compte_dest_id=compte_id,
            per_page=1000  # Assure la récupération de tout
        )

        # 5. Catégorisation des transactions
        categories = self.categorie_comptable_model.get_categories_par_type('compte_principal', compte_id, user_id,
                                                           date_debut=debut.strftime('%Y-%m-%d'),
                                                           date_fin=fin.strftime('%Y-%m-%d'))

        # 6. Génération des graphiques SVG
        graph_flux = self._generer_graphique_flux_journalier(compte_id, user_id, debut, fin)
        graph_categories = self._generer_graphique_categories(categories)

        return {
            "meta": {
                "compte_id": compte_id,
                "periode": periode,
                "date_debut": debut.isoformat(),
                "date_fin": fin.isoformat(),
                "titre": titre,
                "generated_at": datetime.now().isoformat()
            },
            "resume": {
                "solde_initial": float(solde_initial),
                "solde_final": float(solde_final),
                "variation": float(solde_final - solde_initial),
                "total_recettes": stats.get('total_entrees', 0.0),
                "total_depenses": stats.get('total_sorties', 0.0),
                "nb_transactions": len(transactions)
            },
            "categories": {k: float(v) for k, v in categories.items()},
            "graphiques": {
                "flux_journalier_svg": graph_flux,
                "categories_svg": graph_categories
            },
            # Optionnel: inclure les transactions brutes pour export CSV
            "transactions": [
                {
                    "id": t['id'],
                    "date": t['date_transaction'].isoformat() if t['date_transaction'] else None,
                    "type": t['type_transaction'],
                    "montant": float(t['montant']),
                    "solde_apres": float(t['solde_apres']),
                    "description": t.get('description', '')
                }
                for t in transactions
            ]
        }


    def _generer_graphique_flux_journalier(self, compte_id: int, user_id: int, debut: date, fin: date) -> str:
        """Génère un graphique SVG en barres des flux quotidiens."""

        # Récupérer recettes et dépenses quotidiennes
        recettes = self.categorie_comptable_model._get_daily_balances(compte_id, debut, fin, 'recette')
        depenses = self.categorie_comptable_model._get_daily_balances(compte_id, debut, fin, 'depense')

        dates = sorted(set(recettes.keys()) | set(depenses.keys()))
        if not dates:
            return "<svg width='600' height='300'><text x='10' y='20'>Aucune donnée</text></svg>"

        # Valeurs
        vals_recette = [float(recettes.get(d, 0)) for d in dates]
        vals_depense = [float(depenses.get(d, 0)) for d in dates]
        vals_net = [r - d for r, d in zip(vals_recette, vals_depense)]

        # Échelle
        max_abs = max(max(vals_recette), max(vals_depense), max(abs(v) for v in vals_net)) or 1

        # Dimensions SVG
        w, h = 700, 350
        ml, mr, mt, mb = 60, 40, 40, 60
        graph_w = w - ml - mr
        graph_h = h - mt - mb

        # Génération SVG
        svg = f'<svg width="{w}" height="{h}" xmlns="http://www.w3.org/2000/svg">\n'
        svg += '<style>text { font-family: Arial, sans-serif; font-size: 10px; }</style>\n'

        # Axes
        y0 = mt + graph_h / 2
        svg += f'<line x1="{ml}" y1="{y0}" x2="{ml+graph_w}" y2="{y0}" stroke="#000" stroke-dasharray="2"/>\n'

        # Barres
        nb = len(dates)
        for i, dt in enumerate(dates):
            x = ml + (i + 0.5) * (graph_w / nb)
            rec = vals_recette[i]
            dep = vals_depense[i]

            # Barre recette (haut)
            h_rec = (rec / max_abs) * (graph_h / 2)
            svg += f'<rect x="{x-6}" y="{y0 - h_rec}" width="12" height="{h_rec}" fill="#4CAF50"/>\n'
            # Barre dépense (bas)
            h_dep = (dep / max_abs) * (graph_h / 2)
            svg += f'<rect x="{x-6}" y="{y0}" width="12" height="{h_dep}" fill="#F44336"/>\n'

            # Label date
            svg += f'<text x="{x}" y="{mt+graph_h+15}" text-anchor="middle" transform="rotate(45,{x},{mt+graph_h+15})">{dt.strftime("%d.%m")}</text>\n'

        # Légende
        svg += f'<rect x="{ml}" y="{mt-20}" width="12" height="6" fill="#4CAF50"/><text x="{ml+15}" y="{mt-12}">Recettes</text>\n'
        svg += f'<rect x="{ml+80}" y="{mt-20}" width="12" height="6" fill="#F44336"/><text x="{ml+95}" y="{mt-12}">Dépenses</text>\n'

        svg += '</svg>'
        return svg

    def _generer_graphique_categories(self, categories: Dict[str, Decimal]) -> str:
        """Génère un graphique en camembert ou en barres horizontales selon le nombre de catégories."""
        if not categories:
            return "<svg width='500' height='300'><text x='10' y='20'>Aucune catégorie</text></svg>"

        # Trier et limiter à 10 catégories principales
        items = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]
        noms = [item[0] for item in items]
        montants = [float(item[1]) for item in items]
        total = sum(montants) or 1

        # Graphique en barres horizontales (plus lisible)
        h_svg = max(300, len(noms) * 30)
        w_svg = 600
        ml, mr, mt, mb = 200, 40, 30, 30
        graph_w = w_svg - ml - mr
        graph_h = h_svg - mt - mb

        svg = f'<svg width="{w_svg}" height="{h_svg}" xmlns="http://www.w3.org/2000/svg">\n'
        for i, (nom, montant) in enumerate(items):
            y = mt + i * (graph_h / len(items))
            largeur = (montant / total) * graph_w
            couleur = f"hsl({360 * i / len(items)}, 60%, 50%)"
            svg += f'<rect x="{ml}" y="{y}" width="{largeur}" height="{graph_h/len(items)*0.8}" fill="{couleur}"/>\n'
            svg += f'<text x="{ml-10}" y="{y + graph_h/len(items)*0.4}" text-anchor="end">{nom[:20]}</text>\n'
            svg += f'<text x="{ml+largeur+10}" y="{y + graph_h/len(items)*0.4}">{montant:.2f}</text>\n'
        svg += '</svg>'
        return svg

class SousCompte:
    """Modèle pour les sous-comptes d'épargne"""

    def __init__(self, db):
        self.db = db

    def get_by_compte_principal_id(self, compte_principal_id: int) -> List[Dict]:
        """Récupère tous les sous-comptes d'un compte principal"""
        logger.debug(f"Récupération des sous-comptes pour le compte principal {compte_principal_id}")

        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    id, nom_sous_compte, description, objectif_montant, solde,
                    couleur, icone, date_objectif, date_creation,
                    CASE
                        WHEN objectif_montant > 0 THEN
                            ROUND((solde / objectif_montant) * 100, 2)
                        ELSE 0
                    END as pourcentage_objectif
                FROM sous_comptes
                WHERE compte_principal_id = %s AND actif = TRUE
                ORDER BY date_creation DESC
                """
                cursor.execute(query, (compte_principal_id,))
                result = cursor.fetchall()

                logger.debug(f"Résultat de la requête: {result}")
                return result

        except Error as e:
            logger.error(f"Erreur lors de la récupération des sous-comptes: {e}")
            return []

    def get_all_sous_comptes_by_user_id(self, user_id) -> List:
        """Récupère tous les sous-comptes d'un utilisateur"""
        logger.debug(f"Récupération de tous les sous-comptes pour l'utilisateur {user_id}")

        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT sc.*, cp.nom_compte as nom_compte_principal
                FROM sous_comptes sc
                JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                WHERE cp.utilisateur_id = %s
                """
                cursor.execute(query, (user_id,))
                result = cursor.fetchall()

                return result
        except Error as e:
            logger.error(f"Erreur lors de la récupération des sous-comptes: {e}")
            return []

    def get_by_id(self, sous_compte_id: int) -> Optional[Dict]:
        """Récupère un sous-compte par son ID"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT sc.*, cp.nom_compte as nom_compte_principal
                FROM sous_comptes sc
                JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                WHERE sc.id = %s AND sc.actif = TRUE
                """
                cursor.execute(query, (sous_compte_id,))
                sous_compte = cursor.fetchone()
                logger.debug(f'voici le resultat de get_by_id {sous_compte}')
                return sous_compte
        except Error as e:
            logger.error(f"Erreur lors de la récupération du sous-compte: {e}")
            return None

    def create(self, data: Dict) -> bool:
        """Crée un nouveau sous-compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO sous_comptes
                (compte_principal_id, nom_sous_compte, description, objectif_montant,
                 couleur, icone, date_objectif, utilisateur_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    data['compte_principal_id'], data['nom_sous_compte'],
                    data.get('description', ''), data.get('objectif_montant'),
                    data.get('couleur', '#28a745'), data.get('icone', 'piggy-bank'),
                    data.get('date_objectif'),
                    data.get('utilisateur_id')
                )
                cursor.execute(query, values)
                return True
        except Error as e:
            logger.error(f"Erreur lors de la création du sous-compte: {e}")
            return False

    def update(self, sous_compte_id: int, data: Dict) -> bool:
        """Met à jour un sous-compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE sous_comptes
                SET nom_sous_compte = %s, description = %s, objectif_montant = %s,
                    couleur = %s, icone = %s, date_objectif = %s
                WHERE id = %s
                """
                values = (
                    data['nom_sous_compte'], data.get('description', ''),
                    data.get('objectif_montant'), data.get('couleur', '#28a745'),
                    data.get('icone', 'piggy-bank'), data.get('date_objectif', data.get('utilisateur_id')),
                    sous_compte_id
                )
                cursor.execute(query, values)
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour du sous-compte: {e}")
            return False

    def delete(self, sous_compte_id: int) -> bool:
        """Supprime un sous-compte (soft delete)"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier si le sous-compte a un solde
                cursor.execute("SELECT solde FROM sous_comptes WHERE id = %s", (sous_compte_id,))
                result = cursor.fetchone()

                if result and Decimal(str(result['solde'])) > 0:
                    logger.warning(f"Impossible de supprimer le sous-compte {sous_compte_id} car son solde n'est pas nul.")
                    return False

                # Soft delete
                cursor.execute("UPDATE sous_comptes SET actif = FALSE WHERE id = %s", (sous_compte_id,))
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur lors de la suppression du sous-compte: {e}")
            return False

    def update_solde(self, sous_compte_id: int, nouveau_solde: float) -> bool:
        """Met à jour le solde d'un sous-compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = "UPDATE sous_comptes SET solde = %s WHERE id = %s"
                cursor.execute(query, (nouveau_solde, sous_compte_id))
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour du solde: {e}")
            return False

    def get_solde(self, sous_compte_id: int) -> float:
        """Retourne le solde d'un sous-compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT solde FROM sous_comptes WHERE id = %s"
                cursor.execute(query, (sous_compte_id,))
                result = cursor.fetchone()
                return float(result['solde']) if result and 'solde' in result else 0.0
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du solde : {e}")
            return 0.0

class TransactionFinanciere:
    """
    Classe unifiée pour gérer toutes les transactions financières avec optimisation des soldes
    """
    def __init__(self, db):
        self.db = db
    # ===== VALIDATION ET UTILITAIRES =====

    def _valider_solde_suffisant(self, compte_type: str, compte_id: int, montant: Decimal) -> Tuple[bool, Decimal]:
        """Vérifie si le solde est suffisant pour l'opération"""
        logger.debug(f"Vérification du solde pour {compte_type} ID {compte_id}")

        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s", (compte_id,))
                elif compte_type == 'sous_compte':
                    cursor.execute("SELECT solde FROM sous_comptes WHERE id = %s", (compte_id,))
                else:
                    logger.error(f"Type de compte invalide: {compte_type}")
                    return False, Decimal('0')

                result = cursor.fetchone()
                if not result or 'solde' not in result:
                    logger.warning(f"Aucun solde trouvé pour {compte_type} ID {compte_id}")
                    return False, Decimal('0')

                solde_actuel = Decimal(str(result['solde']))
                return solde_actuel >= montant, solde_actuel
        except Error as e:
            logger.error(f"Erreur validation solde: {e}")
            return False, Decimal('0')

    def _get_previous_transaction(self, compte_type: str, compte_id: int, date_transaction: datetime) -> Optional[Dict]:
        """Trouve la transaction précédente la plus proche pour un compte donné"""
        logger.debug(f"Recherche de la transaction précédente pour {compte_type} ID {compte_id}")

        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    condition = "compte_principal_id = %s"
                else:
                    condition = "sous_compte_id = %s"

                query = f"""
                SELECT id, date_transaction, solde_apres
                FROM transactions
                WHERE {condition} AND date_transaction <= %s
                ORDER BY date_transaction DESC, id DESC
                LIMIT 1
                """

                cursor.execute(query, (compte_id, date_transaction))
                return cursor.fetchone()
        except Error as e:
            logger.error(f"Erreur recherche transaction précédente: {e}")
            return None

    def _get_solde_initial(self, compte_type: str, compte_id: int) -> Decimal:
        """Récupère le solde initial d'un compte"""
        logger.debug(f"Récupération du solde initial pour {compte_type} ID {compte_id}")

        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    cursor.execute("SELECT solde_initial FROM comptes_principaux WHERE id = %s", (compte_id,))
                else:
                    cursor.execute("SELECT solde_initial FROM sous_comptes WHERE id = %s", (compte_id,))

                result = cursor.fetchone()
                return Decimal(str(result['solde_initial'])) if result and 'solde_initial' in result else Decimal('0')
        except Error as e:
            logger.error(f"Erreur récupération solde initial: {e}")
            return Decimal('0')

    def _update_subsequent_transactions(self, cursor, compte_type: str, compte_id: int,
                                      date_transaction: datetime, transaction_id: int,
                                      solde_apres_insere: Decimal) -> Optional[Decimal]:
        """Met à jour les soldes des transactions suivantes après une insertion ou modification"""
        logger.debug("Mise à jour des transactions suivantes")

        if compte_type == 'compte_principal':
            condition = "compte_principal_id = %s"
        else:
            condition = "sous_compte_id = %s"

        # Récupérer les transactions suivantes
        query = f"""
        SELECT id, type_transaction, montant, date_transaction
        FROM transactions
        WHERE {condition} AND (date_transaction > %s OR (date_transaction = %s AND id > %s))
        ORDER BY date_transaction ASC, id ASC
        """

        cursor.execute(query, (compte_id, date_transaction, transaction_id))
        subsequent_transactions = cursor.fetchall()

        solde_courant = solde_apres_insere
        dernier_solde = None

        for transaction in subsequent_transactions:
            montant = Decimal(str(transaction['montant']))
            if transaction['type_transaction'] in ['depot', 'transfert_entrant', 'recredit_annulation']:
                solde_courant += montant
            else:
                solde_courant -= montant

            update_query = "UPDATE transactions SET solde_apres = %s WHERE id = %s"
            cursor.execute(update_query, (solde_courant, transaction['id'])) #cursor.execute(update_query, (float(solde_courant), transaction['id']))
            dernier_solde = solde_courant

        return dernier_solde

    def _inserer_transaction(self, compte_type: str, compte_id: int, type_transaction: str,
                            montant: Decimal, description: str, user_id: int,
                            date_transaction: datetime, validate_balance: bool = True) -> Tuple[bool, str, Optional[int]]:
        """Insère une transaction avec calcul intelligent du solde et mise à jour des transactions suivantes"""
        logger.info(f"Insertion de la transaction de type '{type_transaction}'")
        try:
            with self.db.get_cursor() as cursor:
                # Trouver la transaction précédente
                previous = self._get_previous_transaction(compte_type, compte_id, date_transaction)
                # Calculer le solde_avant
                if previous:
                    solde_avant = Decimal(str(previous['solde_apres']))
                else:
                    solde_initial = self._get_solde_initial(compte_type, compte_id)
                    solde_avant = solde_initial
                # Pour les transactions de débit, vérifier le solde suffisant si demandé
                if validate_balance and type_transaction in ['retrait', 'transfert_sortant', 'transfert_externe']:
                    if solde_avant < montant:
                        return False, "Solde insuffisant", None
                # Calculer le nouveau solde
                if type_transaction in ['depot', 'transfert_entrant', 'recredit_annulation']:
                    solde_apres = solde_avant + montant
                else:
                    solde_apres = solde_avant - montant
                reference_transfert = f"TRF_{int(time.time())}_{user_id}_{secrets.token_hex(6)}"
                # Insérer la transaction
                if compte_type == 'compte_principal':
                    query = """
                    INSERT INTO transactions
                    (compte_principal_id, type_transaction, montant, description, utilisateur_id, date_transaction, solde_apres, reference_transfert)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(query, (compte_id, type_transaction, float(montant),
                                        description, user_id, date_transaction, float(solde_apres), reference_transfert))
                else:
                    query = """
                    INSERT INTO transactions
                    (sous_compte_id, type_transaction, montant, description, utilisateur_id, date_transaction, solde_apres, referreference_transfert)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(query, (compte_id, type_transaction, float(montant),
                                        description, user_id, date_transaction, float(solde_apres), reference_transfert))

                transaction_id = cursor.lastrowid

                # Mettre à jour les transactions suivantes
                dernier_solde = self._update_subsequent_transactions(
                    cursor, compte_type, compte_id, date_transaction, transaction_id, solde_apres
                )

                # Mettre à jour le solde du compte
                solde_final = dernier_solde if dernier_solde is not None else solde_apres
                if not self._mettre_a_jour_solde(compte_type, compte_id, solde_final):
                    raise Exception("Erreur lors de la mise à jour du solde")

                return True, "Transaction insérée avec succès", transaction_id
        except Exception as e:
            logger.error(f"Erreur insertion transaction: {e}")
            return False, f"Erreur lors de l'insertion: {str(e)}", None

    def _recalculer_soldes_apres_date(self, compte_type: str, compte_id: int, date_modification: datetime) -> bool:
        """Recalcule tous les soldes_apres des transactions postérieures à une date"""
        logger.info("Recalcul des soldes après modification")
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer toutes les transactions à partir de la date de modification, triées chronologiquement
                if compte_type == 'compte_principal':
                    condition_compte = "compte_principal_id = %s"
                else:
                    condition_compte = "sous_compte_id = %s"
                query = f"""
                SELECT id, montant, type_transaction, date_transaction
                FROM transactions
                WHERE {condition_compte} AND date_transaction >= %s
                ORDER BY date_transaction, id
                """
                cursor.execute(query, (compte_id, date_modification))
                transactions = cursor.fetchall()
                if not transactions:
                    return True
                # Trouver la transaction précédente pour obtenir le solde initial
                premiere_transaction = transactions[0]
                previous = self._get_previous_transaction(compte_type, compte_id, premiere_transaction['date_transaction'])
                if previous:
                    solde_courant = Decimal(str(previous['solde_apres']))
                else:
                    solde_initial = self._get_solde_initial(compte_type, compte_id)
                    solde_courant = solde_initial

                for transaction in transactions:
                    montant = Decimal(str(transaction['montant']))
                    if transaction['type_transaction'] in ['depot', 'transfert_entrant', 'recredit_annulation']:
                        solde_courant += montant
                    elif transaction['type_transaction'] in ['retrait', 'transfert_sortant', 'transfert_externe']:
                        solde_courant -= montant

                    cursor.execute("""
                        UPDATE transactions
                        SET solde_apres = %s
                        WHERE id = %s
                    """, (float(solde_courant), transaction['id']))

                if not self._mettre_a_jour_solde(compte_type, compte_id, solde_courant):
                    raise Exception("Erreur lors de la mise à jour du solde")

                return True
        except Exception as e:
            logger.error(f"Erreur recalcul soldes: {e}")
            return False

    def _recalculer_soldes_apres_date_with_cursor(self, cursor, compte_type: str, compte_id: int, date_modification: datetime) -> bool:
        """Recalcule tous les soldes_apres des transactions postérieures à une date — version avec curseur existant"""
        logger.info("Recalcul des soldes après modification")
        try:
            # Récupérer toutes les transactions à partir de la date de modification, triées chronologiquement
            if compte_type == 'compte_principal':
                condition_compte = "compte_principal_id = %s"
            else:
                condition_compte = "sous_compte_id = %s"

            query = f"""
            SELECT id, montant, type_transaction, date_transaction
            FROM transactions
            WHERE {condition_compte} AND date_transaction >= %s
            ORDER BY date_transaction, id
            """
            cursor.execute(query, (compte_id, date_modification))
            transactions = cursor.fetchall()
            if not transactions:
                return True

            # Trouver la transaction précédente pour obtenir le solde initial
            premiere_transaction = transactions[0]
            previous = self._get_previous_transaction_with_cursor(cursor, compte_type, compte_id, premiere_transaction['date_transaction'])
            if previous:
                solde_courant = Decimal(str(previous[2]))  # previous[2] = solde_apres
            else:
                solde_initial = self._get_solde_initial_with_cursor(cursor, compte_type, compte_id)
                solde_courant = solde_initial

            for transaction in transactions:
                montant = Decimal(str(transaction['montant']))
                if transaction['type_transaction'] in ['depot', 'transfert_entrant', 'recredit_annulation', 'transfert_sous_vers_compte']:
                    solde_courant += montant
                elif transaction['type_transaction'] in ['retrait', 'transfert_sortant', 'transfert_externe', 'transfert_compte_vers_sous']:
                    solde_courant -= montant
                cursor.execute("""
                    UPDATE transactions
                    SET solde_apres = %s
                    WHERE id = %s
                """, (float(solde_courant), transaction['id']))

            # Mettre à jour le solde final du compte
            if not self._mettre_a_jour_solde_with_cursor(cursor, compte_type, compte_id, solde_courant):
                raise Exception("Erreur lors de la mise à jour du solde")

            return True
        except Exception as e:
            logger.error(f"Erreur recalcul soldes: {e}")
            return False

    def get_solde_historique(self, compte_type: str, compte_id: int, user_id: int,
                        date_debut: str = None, date_fin: str = None) -> List[Dict]:
        """Récupère l'évolution historique du solde d'un compte"""
        if not self._verifier_appartenance_compte(compte_type, compte_id, user_id):
            return []
        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    condition_compte = "compte_principal_id = %s"
                else:
                    condition_compte = "sous_compte_id = %s"
                query = f"""
                SELECT
                    date_transaction,
                    type_transaction,
                    montant,
                    description,
                    solde_apres,
                    reference
                FROM transactions
                WHERE {condition_compte}
                """
                params = [compte_id]
                if date_debut:
                    query += " AND date_transaction >= %s"
                    params.append(date_debut)
                if date_fin:
                    query += " AND date_transaction <= %s"
                    params.append(date_fin)
                query += " ORDER BY date_transaction DESC, id DESC"
                cursor.execute(query, params)
                return cursor.fetchall()
        except Error as e:
            logger.error(f"Erreur récupération solde historique: {e}")
            return []

    def _mettre_a_jour_solde(self, compte_type: str, compte_id: int, nouveau_solde: Decimal) -> bool:
        """Met à jour le solde d'un compte"""
        logger.info(f"Mise à jour solde {compte_type} ID {compte_id} -> {nouveau_solde}")
        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    query = "UPDATE comptes_principaux SET solde = %s WHERE id = %s"
                else:
                    query = "UPDATE sous_comptes SET solde = %s WHERE id = %s"
                cursor.execute(query, (float(nouveau_solde), compte_id))
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur mise à jour solde: {e}")
            return False

    def modifier_transaction(self, transaction_id: int, user_id: int,
                        nouveau_montant: Decimal,
                        nouvelle_description: str,
                        nouvelle_date: datetime,
                        nouvelle_reference: str ) -> Tuple[bool, str]:
        """Modifie une transaction existante et recalcule les soldes suivants si le montant ou la date change"""
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer la transaction originale
                cursor.execute("""
                    SELECT t.*,
                        COALESCE(cp.utilisateur_id, (
                            SELECT cp2.utilisateur_id
                            FROM sous_comptes sc
                            JOIN comptes_principaux cp2 ON sc.compte_principal_id = cp2.id
                            WHERE sc.id = t.sous_compte_id
                        )) as owner_user_id
                    FROM transactions t
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    WHERE t.id = %s
                """, (transaction_id,))
                transaction = cursor.fetchone()
                if not transaction:
                    return False, "Transaction non trouvée"
                if transaction['owner_user_id'] != user_id:
                    return False, "Non autorisé à modifier cette transaction"
                type_tx = transaction['type_transaction']
                est_transfert = type_tx in ['transfert_entrant', 'transfert_sortant']

                compte_type = 'compte_principal' if transaction['compte_principal_id'] else 'sous_compte'
                compte_id = transaction['compte_principal_id'] or transaction['sous_compte_id']
                ancien_montant = Decimal(str(transaction['montant']))
                ancienne_date = transaction['date_transaction']
                ancien_type = transaction['type_transaction'] # On garde l'ancien type pour la logique


                # Préparer les champs à mettre à jour
                update_fields = []
                update_params = []
                # Vérifier et ajouter le montant
                if nouveau_montant is not None and nouveau_montant != ancien_montant and nouveau_montant >= 0:
                    update_fields.append("montant = %s")
                    update_params.append(float(nouveau_montant))
                # Vérifier et ajouter la description
                if nouvelle_description is not None and nouvelle_description != transaction.get('description', ''):
                    update_fields.append("description = %s")
                    update_params.append(nouvelle_description)
                # Vérifier et ajouter la date
                if nouvelle_date is not None and nouvelle_date != ancienne_date:
                    if nouvelle_date > datetime.now() + timedelta(days=365):
                        return False, "La date ne peut pas être dans le futur lointain"
                    update_fields.append("date_transaction = %s")
                    update_params.append(nouvelle_date)
                # Vérifier et ajouter la référence
                if nouvelle_reference is not None and nouvelle_reference != transaction.get('reference', ''):
                    update_fields.append("reference = %s")
                    update_params.append(nouvelle_reference)
                # Si rien n'a changé, on ne fait rien
                if not update_fields:
                    return True, "Aucune modification nécessaire"

                # Construire et exécuter la requête de mise à jour
                update_params.append(transaction_id)
                query = f"UPDATE transactions SET {', '.join(update_fields)} WHERE id = %s"
                cursor.execute(query, update_params)

                # Déterminer si un recalcul des soldes est nécessaire
                recalcul_necessaire = (
                    (nouveau_montant is not None and nouveau_montant != ancien_montant) or
                    (nouvelle_date is not None and nouvelle_date != ancienne_date)
                )
                if est_transfert:
                    reference_transfert = transaction.get('reference_transfert')
                    if not reference_transfert:
                        return False, "Transfert corrompu : référence manquante"
                    cursor.execute("""
                        SELECT id, type_transaction
                        FROM transactions
                        WHERE reference_transfert = %s AND id != %s
                    """, (reference_transfert, transaction_id))
                    autre_tx = cursor.fetchone()
                    if not autre_tx:
                        return False, "Transfert corrompu : transaction liée introuvable"
                    update_params_autre = update_params[:-1]  # Même modifications sauf l'ID
                    update_params_autre.append(autre_tx['id'])
                    cursor.execute(query, update_params_autre)


                if recalcul_necessaire:
                    # Déterminer la date de référence pour le recalcul
                    # Si la date a changé, on prend la plus ancienne pour être sûr de tout recalculer
                    if nouvelle_date is not None:
                        ancienne_dt = ancienne_date if isinstance(ancienne_date, datetime) else datetime.combine(ancienne_date, datetime.min.time())
                        nouvelle_dt = nouvelle_date if isinstance(nouvelle_date, datetime) else datetime.combine(nouvelle_date, datetime.min.time())
                        date_reference = min(ancienne_dt, nouvelle_dt)
                    else:
                        # Si seule le montant change, on garde l'ancienne date (qui est aussi la nouvelle)
                        date_reference = ancienne_date if isinstance(ancienne_date, datetime) else datetime.combine(ancienne_date, datetime.min.time())

                    compte_type = 'compte_principal' if transaction['compte_principal_id'] else 'sous_compte'
                    compte_id = transaction['compte_principal_id'] or transaction['sous_compte_id']
                    success1 = self._recalculer_soldes_apres_date_with_cursor(cursor, compte_type, compte_id, date_reference)
                    if not success1:
                        raise Exception("Erreur lors du recalcul des soldes des transactions suivantes")
                    else:
                        logger.info("Recalcul des soldes réussi de la transaction après modification")
                    if est_transfert and autre_tx:
                        # Recalculer aussi pour l'autre transaction du transfert
                        cursor.execute("""
                            SELECT compte_principal_id, sous_compte_id
                            FROM transactions WHERE id = %s
                        """, (autre_tx['id'],))
                        autre_details = cursor.fetchone()
                        if autre_details:
                            autre_compte_type = 'compte_principal' if autre_details['compte_principal_id'] else 'sous_compte'
                            autre_compte_id = autre_details['compte_principal_id'] or autre_details['sous_compte_id']
                            success2 = self._recalculer_soldes_apres_date_with_cursor(cursor, autre_compte_type, autre_compte_id, date_reference)
                            if not success2:
                                raise Exception("Erreur lors du recalcul des soldes de l'autre transaction du transfert")
                            else:
                                logger.info("Recalcul des soldes réussi de l'autre transaction du transfert après modification")
                return True, "Transaction modifiée avec succès"

        except Exception as e:
            logger.error(f"Erreur modification transaction: {e}")
            return False, f"Erreur lors de la modification: {str(e)}"

    def supprimer_transaction(self, transaction_id: int, user_id: int) -> Tuple[bool, str]:
        """Supprime une transaction. Si c'est un transfert, supprime les deux transactions liées."""
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer la transaction AVANT de la supprimer
                cursor.execute("""
                    SELECT t.*,
                        COALESCE(cp.utilisateur_id, (
                            SELECT cp2.utilisateur_id
                            FROM sous_comptes sc
                            JOIN comptes_principaux cp2 ON sc.compte_principal_id = cp2.id
                            WHERE sc.id = t.sous_compte_id
                        )) as owner_user_id
                    FROM transactions t
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    WHERE t.id = %s
                """, (transaction_id,))
                transaction = cursor.fetchone()

                if not transaction:
                    return False, "Transaction non trouvée"
                    logger.info(f'Transaction {transaction_id} non trouvée pour suppression')
                if transaction['owner_user_id'] != user_id:
                    logger.info(f'Utilisateur {user_id} non autorisé à supprimer cette transaction')
                    return False, "Non autorisé à supprimer cette transaction"

                type_tx = transaction['type_transaction']
                compte_type = 'compte_principal' if transaction['compte_principal_id'] else 'sous_compte'
                compte_id = transaction['compte_principal_id'] or transaction['sous_compte_id']
                date_transaction = transaction['date_transaction']

                # === CAS SPÉCIAL : TRANSFERT INTERNE (entrant/sortant) ===
                if type_tx in ['transfert_entrant', 'transfert_sortant']:
                    reference_transfert = transaction.get('reference_transfert')
                    if not reference_transfert:
                        logger.error(f"Transfert corrompu : référence manquante pour la transaction {transaction_id}")
                        return False, "Transfert corrompu : référence manquante"

                    # Récupérer les deux transactions liées
                    cursor.execute("""
                        SELECT id, type_transaction, compte_principal_id, sous_compte_id, date_transaction
                        FROM transactions
                        WHERE reference_transfert = %s
                    """, (reference_transfert,))
                    transactions_liees = cursor.fetchall()

                    if len(transactions_liees) != 2:
                        return False, f"Transfert invalide : {len(transactions_liees)} transactions trouvées"

                    # Identifier la transaction source (sortante) pour vérifier la propriété
                    tx_source = next((tx for tx in transactions_liees if tx['type_transaction'] == 'transfert_sortant'), None)
                    if not tx_source:
                        return False, "Transfert mal formé : transaction source manquante"

                    # Vérifier que l'utilisateur est propriétaire du compte source
                    if tx_source['compte_principal_id']:
                        cursor.execute("SELECT utilisateur_id FROM comptes_principaux WHERE id = %s",
                                    (tx_source['compte_principal_id'],))
                    else:
                        cursor.execute("""
                            SELECT cp.utilisateur_id
                            FROM sous_comptes sc
                            JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                            WHERE sc.id = %s
                        """, (tx_source['sous_compte_id'],))
                    owner_row = cursor.fetchone()
                    if not owner_row or owner_row['utilisateur_id'] != user_id:
                        return False, "Non autorisé à annuler ce transfert"

                    # Supprimer les deux transactions
                    cursor.execute("DELETE FROM transactions WHERE reference_transfert = %s", (reference_transfert,))

                    # Recalculer les soldes pour chaque compte impliqué
                    for tx in transactions_liees:
                        tx_compte_type = 'compte_principal' if tx['compte_principal_id'] else 'sous_compte'
                        tx_compte_id = tx['compte_principal_id'] or tx['sous_compte_id']
                        tx_date = tx['date_transaction']

                        # On ne recalcule que si l'utilisateur est propriétaire (sécurité)
                        if not self._verifier_appartenance_compte_with_cursor(cursor, tx_compte_type, tx_compte_id, user_id):
                            continue

                        success = self._recalculer_soldes_apres_date_with_cursor(
                            cursor, tx_compte_type, tx_compte_id, tx_date
                        )
                        if not success:
                            raise Exception(f"Échec du recalcul du solde pour le compte {tx_compte_type} ID {tx_compte_id}")

                    return True, "Transfert annulé avec succès"

                # === CAS NORMAL : transaction simple (dépôt, retrait, etc.) ===
                else:
                    # Supprimer la transaction unique
                    cursor.execute("DELETE FROM transactions WHERE id = %s", (transaction_id,))
                    logger.info(f"Demande de suppression de la Transaction {transaction_id} supprimée avec succès")
                    cursor.execute("SELECT * FROM transactions WHERE id = %s", (transaction_id,))
                    logger.info(f"Vérification post-suppression: {cursor.fetchone()} (devrait être None)")
                    # Recalculer les soldes à partir de la date de la transaction
                    success = self._recalculer_soldes_apres_date_with_cursor(
                        cursor, compte_type, compte_id, date_transaction
                    )
                    logger.info(f"Recalcul des soldes après suppression de la transaction {transaction_id} du compte {compte_id} en date du {date_transaction} {'réussi' if success else 'échoué'}")
                    if not success:
                        raise Exception("Erreur lors du recalcul des soldes")

                    return True, "Transaction supprimée avec succès"

        except Exception as e:
            logger.error(f"Erreur lors de la suppression de la transaction {transaction_id}: {e}", exc_info=True)
            return False, f"Erreur lors de la suppression : {str(e)}"

    def reparer_soldes_compte(self, compte_type: str, compte_id: int, user_id: int) -> Tuple[bool, str]:
        """
        Script de réparation : Recalcule TOUTES les transactions d'un compte depuis le solde initial.
        À utiliser UNIQUEMENT pour corriger les données corrompues.
        """
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer le solde initial
                solde_initial = self._get_solde_initial_with_cursor(cursor, compte_type, compte_id)
                solde_courant = solde_initial
                # Vérifier que l'utilisateur est bien propriétaire du compte
                if not self._verifier_appartenance_compte_with_cursor(cursor, compte_type, compte_id, user_id):
                    return False, "Non autorisé"
                logger.info(f"🔧 Réparation des soldes pour {compte_type} ID {compte_id}. Solde initial: {solde_initial}")
                # Récupérer TOUTES les transactions du compte, triées par date
                if compte_type == 'compte_principal':
                    condition = "compte_principal_id = %s"
                else:
                    condition = "sous_compte_id = %s"

                query = f"""
                SELECT id, type_transaction, montant, date_transaction
                FROM transactions
                WHERE {condition}
                ORDER BY date_transaction ASC, id ASC
                """
                cursor.execute(query, (compte_id,))
                transactions = cursor.fetchall()

                # Mettre à jour le solde_apres de chaque transaction
                for tx in transactions:
                    montant = Decimal(str(tx['montant']))
                    if tx['type_transaction'] in ['depot', 'transfert_entrant', 'recredit_annulation', 'transfert_sous_vers_compte']:
                        solde_courant += montant
                    elif tx['type_transaction'] in ['retrait', 'transfert_sortant', 'transfert_externe', 'transfert_compte_vers_sous']:
                        solde_courant -= montant

                    cursor.execute(
                        "UPDATE transactions SET solde_apres = %s WHERE id = %s",
                        (solde_courant, tx['id'])#(float(solde_courant), tx['id'])
                    )
                    logger.info(f"  - Transaction ID {tx['id']} ({tx['type_transaction']} {montant} le {tx['date_transaction']}): solde_apres mis à jour à {solde_courant}")

                # Mettre à jour le solde final du compte
                if not self._mettre_a_jour_solde_with_cursor(cursor, compte_type, compte_id, solde_courant):
                    logger.error(f"Échec de la mise à jour du solde {solde_courant} du compte {compte_id} de type {compte_type}après réparation")
                    raise Exception("Échec de la mise à jour du solde du compte")

                logger.info(f"✅ Soldes du {compte_type} ID {compte_id} réparés avec succès. Nouveau solde: {solde_courant}")
                return True, "Soldes réparés avec succès"

        except Exception as e:
            logger.error(f"Erreur lors de la réparation des soldes: {e}")
            return False, f"Erreur: {str(e)}"

    def _verifier_appartenance_compte(self, compte_type: str, compte_id: int, user_id: int) -> bool:
        """Vérifie que le compte appartient à l'utilisateur"""
        logger.debug(f"Vérification appartenance: {compte_type} ID {compte_id} pour user {user_id}")
        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    cursor.execute("SELECT utilisateur_id FROM comptes_principaux WHERE id = %s", (compte_id,))
                elif compte_type == 'sous_compte':
                    cursor.execute("""
                        SELECT cp.utilisateur_id
                        FROM sous_comptes sc
                        JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                        WHERE sc.id = %s
                    """, (compte_id,))
                else:
                    logger.error("Type de compte invalide")
                    return False

                result = cursor.fetchone()
                appartenance = result and result['utilisateur_id'] == user_id
                logger.debug(f"Résultat vérification appartenance: {appartenance}")
                return appartenance
        except Error as e:
            logger.error(f"Erreur vérification appartenance: {e}")
            return False

    def get_by_compte_id(self, compte_id: int, user_id: int, limit: int = 100) -> List[Dict]:
        """
        Récupère les transactions d'un compte principal avec pagination
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier d'abord que le compte appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                    (compte_id, user_id)
                )
                if not cursor.fetchone():
                    return []

                # Récupérer les transactions
                query = """
                SELECT
                    t.id,
                    t.type_transaction,
                    t.montant,
                    t.description,
                    t.reference,
                    t.date_transaction,
                    t.solde_apres,
                    t.referece_transfert,
                    sc.nom_sous_compte as sous_compte_source,
                    sc_dest.nom_sous_compte as sous_compte_dest
                FROM transactions t
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                LEFT JOIN sous_comptes sc_dest ON t.sous_compte_destination_id = sc_dest.id
                WHERE t.compte_principal_id = %s
                ORDER BY t.date_transaction DESC

                """

                cursor.execute(query, (compte_id, limit))
                transactions = cursor.fetchall()

                # Convertir les montants en Decimal pour une manipulation plus précise
                for transaction in transactions:
                    transaction['montant'] = Decimal(str(transaction['montant']))
                    transaction['solde_apres'] = Decimal(str(transaction['solde_apres']))

                return transactions

        except Exception as e:
            logger.error(f"Erreur récupération transactions par compte: {e}")
            return []

    def get_all_user_transactions(self,
                                user_id: int,
                                date_from: str = None,
                                date_to: str = None,
                                compte_source_id: int = None,
                                compte_dest_id: int = None,
                                sous_compte_source_id: int = None,
                                sous_compte_dest_id: int = None,
                                reference: str = None,
                                q: str = None,
                                page: int = 1,
                                per_page: int = 20
                            ) -> Tuple[List[Dict], int]:
        """
        Récupère toutes les transactions d'un utilisateur avec filtres avancés.
        Retourne (liste_de_transactions, total).
        """
        try:
            with self.db.get_cursor() as cursor:
                # Construire la requête avec jointures pour récupérer les noms
                base_query = """
                SELECT
                    t.id,
                    t.type_transaction,
                    t.montant,
                    t.description,
                    t.reference,
                    t.date_transaction,
                    t.solde_apres,
                    t.compte_principal_id,
                    t.sous_compte_id,
                    t.compte_destination_id,
                    t.sous_compte_destination_id,
                    cp.nom_compte as nom_compte_source,
                    cp_dest.nom_compte as nom_compte_dest,
                    sc.nom_sous_compte as nom_sous_compte_source,
                    sc_dest.nom_sous_compte as nom_sous_compte_dest
                FROM transactions t
                LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                LEFT JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                LEFT JOIN sous_comptes sc_dest ON t.sous_compte_destination_id = sc_dest.id
                WHERE (
                    cp.utilisateur_id = 6
                    OR cp_dest.utilisateur_id = 6
                )
                """
                #WHERE (
                #    (cp.utilisateur_id = %(user_id)s) OR
                #    (sc.compte_principal_id IN (
                #        SELECT id FROM comptes_principaux WHERE utilisateur_id = %(user_id)s
                #    )) OR
                #    (cp_dest.utilisateur_id = %(user_id)s) OR
                #    (sc_dest.compte_principal_id IN (
                #        SELECT id FROM comptes_principaux WHERE utilisateur_id = %(user_id)s
                #    ))
                #)
                count_query = "SELECT COUNT(*) as total FROM (" + base_query + ") AS filtered"

                # Préparer les paramètres
                params = {'user_id': user_id}

                # === Filtres ===
                if date_from:
                    base_query += " AND DATE(t.date_transaction) >= %(date_from)s"
                    params['date_from'] = date_from

                if date_to:
                    base_query += " AND DATE(t.date_transaction) <= %(date_to)s"
                    params['date_to'] = date_to

                if compte_source_id:
                    base_query += " AND t.compte_principal_id = %(compte_source_id)s"
                    params['compte_source_id'] = compte_source_id

                if compte_dest_id:
                    base_query += " AND t.compte_destination_id = %(compte_dest_id)s"
                    params['compte_dest_id'] = compte_dest_id

                if sous_compte_source_id:
                    base_query += " AND t.sous_compte_id = %(sous_compte_source_id)s"
                    params['sous_compte_source_id'] = sous_compte_source_id

                if sous_compte_dest_id:
                    base_query += " AND t.sous_compte_destination_id = %(sous_compte_dest_id)s"
                    params['sous_compte_dest_id'] = sous_compte_dest_id

                if reference:
                    base_query += " AND t.reference = %(reference)s"
                    params['reference'] = reference

                if q and q.strip():
                    q_clean = f"%{q.strip()}%"
                    base_query += """ AND (
                        COALESCE(t.description, '') LIKE %(q)s OR
                        COALESCE(t.reference, '') LIKE %(q)s OR
                        COALESCE(cp.nom_compte, '') LIKE %(q)s OR
                        COALESCE(cp_dest.nom_compte, '') LIKE %(q)s OR
                        COALESCE(sc.nom_sous_compte, '') LIKE %(q)s OR
                        COALESCE(sc_dest.nom_sous_compte, '') LIKE %(q)s
                    )"""
                    params['q'] = q_clean

                # === Compter le total ===
                cursor.execute(count_query, params)
                total = cursor.fetchone()['total']

                # === Ajouter l'ordre et la pagination ===
                base_query += " ORDER BY t.date_transaction DESC, t.id DESC"
                if page and per_page:
                    offset = (page - 1) * per_page
                    base_query += " LIMIT %(limit)s OFFSET %(offset)s"
                    params['limit'] = per_page
                    params['offset'] = offset

                cursor.execute(base_query, params)
                transactions = cursor.fetchall()

                # Convertir les montants en Decimal (optionnel mais cohérent avec le reste)
                for tx in transactions:
                    if 'montant' in tx and tx['montant'] is not None:
                        tx['montant'] = Decimal(str(tx['montant']))
                    if 'solde_apres' in tx and tx['solde_apres'] is not None:
                        tx['solde_apres'] = Decimal(str(tx['solde_apres']))

                return list(transactions), total

        except Exception as e:
            logger.error(f"Erreur dans get_all_user_transactions: {e}", exc_info=True)
            return [], 0

   # ===== DÉPÔTS ET RETRAITS =====

    def create_depot(self, compte_id: int, user_id: int, montant: Decimal,
                    description: str = "", compte_type: str = 'compte_principal',
                    date_transaction: datetime = None) -> Tuple[bool, str]:
        """Crée un dépôt sur un compte"""

        if montant <= 0:
            return False, "Le montant doit être positif"

        if not self._verifier_appartenance_compte(compte_type, compte_id, user_id):
            return False, "Compte non trouvé ou non autorisé"

        if date_transaction is None:
            date_transaction = datetime.now()

        try:
            with self.db.get_cursor(dictionary=True, commit=True) as cursor:
                compte_destination_id = None
                sous_compte_destinatin_id = None

                if compte_type == 'compte_principal':
                    compte_destination_id = compte_id
                elif compte_type == 'sous_compte':
                    sous_compte_destination_id = compte_id
                success, message, _ = self._inserer_transaction_with_cursor(
                    cursor, compte_type, compte_id, 'depot', montant,
                    description, user_id, date_transaction, False,
                    compte_destination_id=compte_destination_id,
                    sous_compte_destination_id=sous_compte_destinatin_id
                )
                return success, message
        except Exception as e:
            logger.error(f"Erreur création dépôt: {e}")
            return False, f"Erreur lors de la création du dépôt: {str(e)}"

    def create_retrait(self, compte_id: int, user_id: int, montant: Decimal,
                    description: str = "", compte_type: str = 'compte_principal',
                    date_transaction: datetime = None) -> Tuple[bool, str]:
        """Crée un retrait sur un compte"""
        if montant <= 0:
            return False, "Le montant doit être positif"
        if not self._verifier_appartenance_compte(compte_type, compte_id, user_id):
            return False, "Compte non trouvé ou non autorisé"
        if date_transaction is None:
            date_transaction = datetime.now()
        solde_suffisant, _ = self._valider_solde_suffisant(compte_type, compte_id, montant)
        if not solde_suffisant:
            return False, "Solde insuffisant"
        try:
            with self.db.get_cursor(dictionary=True, commit=True) as cursor:
                success, message, _ = self._inserer_transaction_with_cursor(cursor,
                                                                            compte_type, compte_id, 'retrait', montant, description, user_id, date_transaction, False)
            return success, message
        except Exception as e:
            logger.error(f"Erreur création retrait: {e}")
            return False, f"Erreur lors de la création du retrait: {str(e)}"

    def _valider_solde_suffisant_with_cursor(self, cursor, compte_type: str, compte_id: int, montant: Decimal) -> Tuple[bool, Decimal]:
        """
        Vérifie si le solde d'un compte est suffisant pour une opération.
        Cette fonction utilise un curseur de base de données déjà ouvert.

        Args:
            cursor: Le curseur de la base de données.
            compte_type (str): 'compte_principal' ou 'sous_compte'.
            compte_id (int): L'identifiant du compte.
            montant (Decimal): Le montant à vérifier.

        Returns:
            Tuple[bool, Decimal]: Un tuple contenant un booléen (True si le solde est suffisant)
                                et le solde actuel du compte.
        """
        try:
            if compte_type == 'compte_principal':
                cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s", (compte_id,))
            elif compte_type == 'sous_compte':
                cursor.execute("SELECT solde FROM sous_comptes WHERE id = %s", (compte_id,))
            else:
                # Type de compte inconnu
                return False, Decimal('0')

            result = cursor.fetchone()
            if not result:
                # Compte non trouvé
                return False, Decimal('0')

            # Assurer la précision décimale en convertissant le résultat de la requête
            solde_actuel = Decimal(str(result['solde']))
            return solde_actuel >= montant, solde_actuel
        except Exception as e:
            logger.error(f"Erreur lors de la validation du solde: {e}")
            return False, Decimal('0')

# ===== TRANSFERTS INTERNES =====

    def _get_solde_compte(self, compte_type: str, compte_id: int) -> Decimal:
        """
        Récupère le solde actuel d'un compte.
        Cette fonction ouvre et ferme sa propre connexion.

        Args:
            compte_type (str): 'compte_principal' ou 'sous_compte'.
            compte_id (int): L'identifiant du compte.

        Returns:
            Decimal: Le solde du compte, ou 0 si une erreur survient.
        """
        logger.error(f"Récupération solde pour {compte_type} ID {compte_id}")

        if compte_type == 'compte_principal':
            query = "SELECT solde FROM comptes_principaux WHERE id = %s"
        else: # Supposant que le seul autre type est 'sous_compte'
            query = "SELECT solde FROM sous_comptes WHERE id = %s"

        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (compte_id,))
                result = cursor.fetchone()
                solde = Decimal(result['solde']) if result  and 'solde' in result else Decimal('0')
                logger.error(f"Solde trouvé: {solde}")
                return solde
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du solde: {e}")
            return Decimal('0')

    def _get_transaction_effect(self, transaction_type: str, compte_type: str) -> str:
        """
        Détermine si une transaction est un crédit ou un débit pour un type de compte donné.
        Retourne 'credit' ou 'debit'.
        """
        credit_types = ['depot', 'transfert_entrant', 'recredit_annulation']
        debit_types = ['retrait', 'transfert_sortant', 'transfert_externe']

        # Types spéciaux qui dépendent du type de compte
        if transaction_type == 'transfert_compte_vers_sous':
            return 'debit' if compte_type == 'compte_principal' else 'credit'
        elif transaction_type == 'transfert_sous_vers_compte':
            return 'debit' if compte_type == 'sous_compte' else 'credit'

        # Types normaux
        if transaction_type in credit_types:
            return 'credit'
        elif transaction_type in debit_types:
            return 'debit'

        return 'unknown'

    def _verifier_appartenance_compte_with_cursor(self, cursor, compte_type: str, compte_id: int, user_id: int) -> bool:
        """
        Vérifie si un compte appartient à un utilisateur donné.
        Utilise un curseur de base de données déjà ouvert.

        Args:
            cursor: Le curseur de la base de données.
            compte_type (str): 'compte_principal' ou 'sous_compte'.
            compte_id (int): L'identifiant du compte.
            user_id (int): L'identifiant de l'utilisateur.

        Returns:
            bool: True si le compte appartient à l'utilisateur, False sinon.
        """
        try:
            if compte_type == 'compte_principal':
                cursor.execute(
                    "SELECT id FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                    (compte_id, user_id)
                )
                result = cursor.fetchone()
                return result is not None
            elif compte_type == 'sous_compte':
            # Jointure pour vérifier la propriété du sous-compte via le compte principal
                cursor.execute(
                    """SELECT sc.id
                    FROM sous_comptes sc
                    JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                    WHERE sc.id = %s AND cp.utilisateur_id = %s""",
                    (compte_id, user_id)
                )
                result = cursor.fetchone()
                return result is not None
            else:
                return False
        except Exception as e:
            logger.error(f"Erreur lors de la vérification de l'appartenance du compte: {e}")
            return False

    def _get_solde_compte_with_cursor(self, cursor, compte_type: str, compte_id: int) -> Decimal:
        """
        Récupère le solde d'un compte en utilisant un curseur existant.

        Args:
            cursor: Le curseur de la base de données.
            compte_type (str): 'compte_principal' ou 'sous_compte'.
            compte_id (int): L'identifiant du compte.

        Returns:
            Decimal: Le solde du compte, ou 0 si une erreur ou un compte non trouvé.
        """
        try:
            if compte_type == 'compte_principal':
                cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s", (compte_id,))
                result = cursor.fetchone()
                return Decimal(str(result['solde'])) if result and 'solde' in result else Decimal('0')
            elif compte_type == 'sous_compte':
                cursor.execute("SELECT solde FROM sous_comptes WHERE id = %s", (compte_id,))
                result = cursor.fetchone()
                return Decimal(str(result['solde'])) if result and 'solde' in result else Decimal('0')
            else:
                return Decimal('0')
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du solde : {e}", exc_info=True)
            return Decimal('0')

    def valider_transfert_sous_compte(sous_compte_id, compte_principal_id, sous_comptes):
        """
        Valide qu'un sous-compte appartient bien à un compte principal.

        Args:
            sous_compte_id (int): L'identifiant du sous-compte.
            compte_principal_id (int): L'identifiant du compte principal.
            sous_comptes (list): Une liste de sous-comptes, typiquement des dictionnaires.

        Returns:
            bool: True si le sous-compte appartient au compte principal, False sinon.
        """
        sous_compte = next((sc for sc in sous_comptes if sc['id'] == sous_compte_id), None)
        return sous_compte is not None and sous_compte['compte_principal_id'] == compte_principal_id

    def _inserer_transaction_with_cursor(self, cursor, compte_type: str, compte_id: int, type_transaction: str,
                    montant: Decimal, description: str, user_id: int,
                    date_transaction: datetime, validate_balance: bool = True, reference_transfert: str = None,
                    compte_destination_id: int = None, sous_compte_destination_id: int = None) -> Tuple[bool, str, Optional[int]]:
        """
        Insère une transaction dans la base de données et met à jour les soldes.
        """
        try:
            # Trouver la transaction précédente pour calculer le solde_avant
            previous = self._get_previous_transaction_with_cursor(cursor, compte_type, compte_id, date_transaction)

            # Calculer le solde_avant
            if previous:
                solde_avant = Decimal(str(previous[2]))
            else:
                # Si aucune transaction précédente, utiliser le solde initial du compte
                solde_initial = self._get_solde_initial_with_cursor(cursor, compte_type, compte_id)
                solde_avant = solde_initial

            # Pour les transactions de débit, vérifier le solde suffisant si demandé
            if validate_balance and type_transaction in ['retrait', 'transfert_sortant', 'transfert_externe', 'transfert_compte_vers_sous']:
                if solde_avant < montant:
                    return False, "Solde insuffisant", None

            # Calculer le nouveau solde
            if type_transaction in ['depot', 'transfert_entrant', 'recredit_annulation']:
                solde_apres = solde_avant + montant
            elif type_transaction in ['retrait', 'transfert_sortant', 'transfert_externe']:
                solde_apres = solde_avant - montant
            elif type_transaction == 'transfert_compte_vers_sous':
                # Ce type est utilisé pour le compte principal (débit) ET le sous-compte (crédit)
                if compte_type == 'compte_principal':
                    solde_apres = solde_avant - montant   # Débit sur le compte principal
                else:  # compte_type == 'sous_compte'
                    solde_apres = solde_avant + montant   # Crédit sur le sous-compte
            elif type_transaction == 'transfert_sous_vers_compte':
                # Ce type est utilisé pour le sous-compte (débit) ET le compte principal (crédit)
                if compte_type == 'sous_compte':
                    solde_apres = solde_avant - montant   # Débit sur le sous-compte
                else:  # compte_type == 'compte_principal'
                    solde_apres = solde_avant + montant   # Crédit sur le compte principal
            else:
                return False, f"Type de transaction non reconnu: {type_transaction}", None

            if reference_transfert is None:
                reference_transfert = f"TRF_{int(time.time())}_{user_id}_{secrets.token_hex(6)}"

            # Déterminer les IDs source et destination
            compte_principal_id = None
            sous_compte_id = None
            compte_source_id = None
            sous_compte_source_id = None

            # Pour les colonnes source
            if compte_type == 'compte_principal':
                compte_principal_id = compte_id
                compte_source_id = compte_id
            else:  # sous_compte
                sous_compte_id = compte_id
                sous_compte_source_id = compte_id

            # Pour les colonnes destination - si non fournies, utiliser les mêmes que la source pour les dépôts
            if compte_destination_id is None and sous_compte_destination_id is None:
                if type_transaction == 'depot':
                    # Pour un dépôt, la destination est le même compte
                    if compte_type == 'compte_principal':
                        compte_destination_id = compte_id
                    else:
                        sous_compte_destination_id = compte_id

            # Insérer la transaction avec toutes les colonnes
            query = """
            INSERT INTO transactions
            (compte_principal_id, sous_compte_id, type_transaction, montant, description,
            utilisateur_id, date_transaction, solde_apres, reference_transfert,
            compte_destination_id, sous_compte_destination_id,
            compte_source_id, sous_compte_source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            cursor.execute(query, (
                compte_principal_id, sous_compte_id, type_transaction, float(montant),
                description, user_id, date_transaction, float(solde_apres), reference_transfert,
                compte_destination_id, sous_compte_destination_id,
                compte_source_id, sous_compte_source_id
            ))

            transaction_id = cursor.lastrowid

            # Mettre à jour les transactions suivantes
            dernier_solde = self._update_subsequent_transactions_with_cursor(
                cursor, compte_type, compte_id, date_transaction, transaction_id, solde_apres
            )

            # Mettre à jour le solde final du compte principal/sous-compte
            solde_final = dernier_solde if dernier_solde is not None else solde_apres
            if not self._mettre_a_jour_solde_with_cursor(cursor, compte_type, compte_id, solde_final):
                return False, "Erreur lors de la mise à jour du solde", None

            return True, "Transaction insérée avec succès", transaction_id

        except Exception as e:
            logger.error(f"Erreur lors de l'insertion de la transaction: {e}", exc_info=True)
            return False, f"Erreur lors de l'insertion: {str(e)}", None

    def _get_previous_transaction_with_cursor(self, cursor, compte_type: str, compte_id: int, date_transaction: datetime) -> Optional[tuple]:
        """
        Trouve la transaction précédente la plus proche pour un compte donné.
        Utilise un curseur de base de données déjà ouvert.
        """
        try:
            if compte_type == 'compte_principal':
                condition = "compte_principal_id = %s"
            else:
                condition = "sous_compte_id = %s"

            query_simple = f"""
            SELECT id, date_transaction, solde_apres
            FROM transactions
            WHERE {condition} AND date_transaction < %s
            ORDER BY date_transaction DESC, id DESC
            LIMIT 1
            """

            cursor.execute(query_simple, (compte_id, date_transaction))
            result = cursor.fetchone()
            if result:
                return (result['id'], result['date_transaction'], result['solde_apres'])
            return None

        except Exception as e:
            logger.error(f"Erreur lors de la recherche de la transaction précédente: {e}")
            return None

    def _get_solde_initial_with_cursor(self, cursor, compte_type: str, compte_id: int) -> Decimal:
        """
        Récupère le solde initial d'un compte en utilisant un curseur existant.
        """
        try:
            if compte_type == 'compte_principal':
                cursor.execute("SELECT solde_initial FROM comptes_principaux WHERE id = %s", (compte_id,))
            else:
                cursor.execute("SELECT solde_initial FROM sous_comptes WHERE id = %s", (compte_id,))

            result = cursor.fetchone()
            return Decimal(str(result['solde_initial'])) if result and 'solde_initial' in result else Decimal('0')

        except Exception as e:
            logger.error(f"Erreur lors de la récupération du solde initial: {e}")
            return Decimal('0')

    def _mettre_a_jour_solde_with_cursor(self, cursor, compte_type: str, compte_id: int, nouveau_solde: Decimal) -> bool:
        """
        Met à jour le solde d'un compte en utilisant un curseur existant.
        """
        try:
            logger.info(f"➡️ Mise à jour solde: compte_type={compte_type}, compte_id={compte_id}, solde={nouveau_solde} (type={type(nouveau_solde)})")

            if compte_type == 'compte_principal':
                query = "UPDATE comptes_principaux SET solde = %s WHERE id = %s"
            else:
                query = "UPDATE sous_comptes SET solde = %s WHERE id = %s"

            cursor.execute(query, (nouveau_solde, compte_id))#cursor.execute(query, (float(nouveau_solde), compte_id))
            if cursor.rowcount > 0:
                logger.info(f"✅ Nombre de lignes mises à jour : {cursor.rowcount}")
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du solde: {e}")
            return False

    def _update_subsequent_transactions_with_cursor(self, cursor, compte_type: str, compte_id: int,
                                                date_transaction: datetime, transaction_id: int,
                                                solde_apres_insere: Decimal) -> Optional[Decimal]:
        """
        Met à jour les soldes des transactions suivantes après une insertion.
        Utilise un curseur de base de données déjà ouvert.
        """
        if compte_type == 'compte_principal':
            condition = "compte_principal_id = %s"
        else:
            condition = "sous_compte_id = %s"

        query = f"""
        SELECT id, type_transaction, montant, date_transaction
        FROM transactions
        WHERE {condition} AND (
            date_transaction > %s OR
            (date_transaction = %s AND id > %s)
        )
        ORDER BY date_transaction ASC, id ASC
        """

        cursor.execute(query, (compte_id, date_transaction, date_transaction, transaction_id))
        subsequent_transactions = cursor.fetchall()

        solde_courant = solde_apres_insere
        dernier_solde = None

        for transaction in subsequent_transactions:
            montant_val = Decimal(str(transaction['montant']))
            type_transaction_val = transaction['type_transaction']

            # Gestion de tous les types de transactions
            if type_transaction_val in ['depot', 'transfert_entrant', 'recredit_annulation', 'transfert_sous_vers_compte']:
                solde_courant += montant_val
            elif type_transaction_val in ['retrait', 'transfert_sortant', 'transfert_externe', 'transfert_compte_vers_sous']:
                solde_courant -= montant_val
            else:
                logger.warning(f"Type de transaction non reconnu: {type_transaction_val}")
                continue
            logger.info(f"Solde final à enregistrer pour {transaction['id']}: {solde_courant} (type: {type(solde_courant)})")
            update_query = "UPDATE transactions SET solde_apres = %s WHERE id = %s"
            cursor.execute(update_query, (solde_courant, transaction['id'])) #cursor.execute(update_query, (float(solde_courant), transaction['id']))
            dernier_solde = solde_courant

        return dernier_solde

    def create_transfert_interne(self, source_type: str, source_id: int,
                                dest_type: str, dest_id: int, user_id: int,
                                montant: Decimal, description: str = "",
                                date_transaction: datetime = None) -> Tuple[bool, str]:
        """
        Exécute un transfert interne entre deux comptes gérés.

        Args:
            source_type (str): Le type du compte source ('compte_principal' ou 'sous_compte').
            source_id (int): L'ID du compte source.
            dest_type (str): Le type du compte de destination ('compte_principal' ou 'sous_compte').
            dest_id (int): L'ID du compte de destination.
            user_id (int): L'ID de l'utilisateur effectuant le transfert.
            montant (Decimal): Le montant à transférer.
            description (str): Une description optionnelle pour la transaction.
            date_transaction (datetime): Date et heure de la transaction (maintenant par défaut).

        Returns:
            Tuple[bool, str]: Un tuple indiquant le succès (True/False) et un message.
        """
        logger.info(f"=== DÉBUT TRANSFERT INTERNE ===")
        logger.info(f"Source: {source_type} ID {source_id}")
        logger.info(f"Destination: {dest_type} ID {dest_id}")
        logger.info(f"Utilisateur: {user_id}, Montant: {montant}")

        # Validations initiales
        if montant <= 0:
            logger.warning("❌ Échec: Le montant doit être positif")
            return False, "Le montant doit être positif"

        if source_type == dest_type and source_id == dest_id:
            logger.warning("❌ Échec: Les comptes source et destination doivent être différents")
            return False, "Les comptes source et destination doivent être différents"

        if date_transaction is None:
            date_transaction = datetime.now()

        try:
            with self.db.get_cursor() as cursor:
                # Vérifier l'appartenance des comptes
                if not self._verifier_appartenance_compte_with_cursor(cursor, source_type, source_id, user_id):
                    return False, "Compte source non trouvé ou non autorisé"

                #if not self._verifier_appartenance_compte_with_cursor(cursor, dest_type, dest_id, user_id):
                #    return False, "Compte destination non trouvé ou non autorisé"

                # Récupérer les soldes
                solde_source = self._get_solde_compte_with_cursor(cursor, source_type, source_id)
                solde_dest = self._get_solde_compte_with_cursor(cursor, dest_type, dest_id)

                # Vérifier le solde source
                if solde_source < montant:
                    return False, "Solde insuffisant sur le compte source"

                # Générer une référence unique
                timestamp = int(time.time())
                reference = f"TRF_{timestamp}_{source_type}_{source_id}_{dest_type}_{dest_id}"

                # Créer la description complète
                desc_complete = f"{description} (Réf: {reference})"

                # 1. Transaction de DÉBIT sur le compte source
                success, message, debit_tx_id = self._inserer_transaction_with_cursor(
                    cursor, source_type, source_id, 'transfert_sortant', montant,
                    desc_complete, user_id, date_transaction, True
                )

                if not success:
                    return False, f"Erreur transaction débit: {message}"

                # 2. Transaction de CRÉDIT sur le compte destination
                success, message, credit_tx_id = self._inserer_transaction_with_cursor(
                    cursor, dest_type, dest_id, 'transfert_entrant', montant,
                    desc_complete, user_id, date_transaction,  False
                )

                if not success:
                    return False, f"Erreur transaction crédit: {message}"

                # Déterminer les IDs de source et de destination pour les liens
                source_compte_id = source_id if source_type == 'compte_principal' else None
                source_sous_compte_id = source_id if source_type == 'sous_compte' else None

                dest_compte_id = dest_id if dest_type == 'compte_principal' else None
                dest_sous_compte_id = dest_id if dest_type == 'sous_compte' else None

                # Mettre à jour les deux transactions avec les liens bidirectionnels
                update_query = """
                UPDATE transactions
                SET
                    compte_source_id = %s,
                    sous_compte_source_id = %s,
                    compte_destination_id = %s,
                    sous_compte_destination_id = %s
                WHERE id IN (%s, %s)
                """
                cursor.execute(update_query, (
                    source_compte_id, source_sous_compte_id,
                    dest_compte_id, dest_sous_compte_id,
                    debit_tx_id, credit_tx_id
                ))

                # Optionnel : loguer les IDs des transactions créées
                logger.info(f"✅ Transfert interne réussi : débit={debit_tx_id}, crédit={credit_tx_id}")

                # Le commit est automatique à la sortie du bloc 'with'
                return True, "Transfert interne effectué avec succès"

        except Exception as e:
            logger.error(f"❌ Erreur lors du transfert interne: {e}", exc_info=True)
            return False, f"Erreur lors du transfert: {str(e)}"

    def transfert_compte_vers_sous_compte(self, compte_id, sous_compte_id, montant, user_id, description="", date_transaction = datetime.now(), reference_transfert=None):
        """
        Transfert d'un compte principal vers un sous-compte.
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le sous-compte appartient au compte
                cursor.execute(
                    "SELECT id FROM sous_comptes WHERE id = %s AND compte_principal_id = %s",
                    (sous_compte_id, compte_id)
                )
                if not cursor.fetchone():
                    return False, "Le sous-compte n'appartient pas à ce compte"

                # Vérifier le solde du compte
                cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s", (compte_id,))
                result = cursor.fetchone()
                if not result:
                    return False, "Compte non trouvé"
                solde_compte = Decimal(str(result['solde']))
                if solde_compte < montant:
                    return False, "Solde insuffisant sur le compte"

                # Générer référence et description
                timestamp = int(time.time())
                reference = f"TRF_CP_SC_{timestamp}"
                desc_complete = f"{description} (Réf: {reference})"
                reference_transfert = f"TRF_{int(time.time())}_{user_id}_{secrets.token_hex(6)}"
                if date_transaction is None:
                    date_transaction = datetime.now()

                # ⚠️ UTILISER _inserer_transaction_with_cursor pour DÉBIT sur le compte principal
                success, message, debit_transaction_id = self._inserer_transaction_with_cursor(
                    cursor,
                    compte_type='compte_principal',
                    compte_id=compte_id,
                    type_transaction='transfert_compte_vers_sous',
                    montant=montant,
                    description=desc_complete,
                    user_id=user_id,
                    date_transaction=date_transaction,
                    validate_balance=True,  # Vérifie le solde
                    reference_transfert=reference_transfert
                )
                if not success:
                    return False, f"Erreur débit compte principal: {message}"

                # ⚠️ UTILISER _inserer_transaction_with_cursor pour CRÉDIT sur le sous-compte
                success, message, credit_transaction_id = self._inserer_transaction_with_cursor(
                    cursor,
                    compte_type='sous_compte',
                    compte_id=sous_compte_id,
                    type_transaction='transfert_compte_vers_sous',  # Même type : c’est une seule opération logique
                    montant=montant,
                    description=desc_complete,
                    user_id=user_id,
                    date_transaction=date_transaction,
                    validate_balance=False,  # Pas besoin de vérifier ici — on vient de débiter
                    reference_transfert=reference_transfert
                )
                if not success:
                    return False, f"Erreur crédit sous-compte: {message}"

                # Mettre à jour les relations entre les deux transactions
                update_query = """
                UPDATE transactions SET
                    compte_source_id = %s,
                    sous_compte_destination_id = %s
                WHERE id IN (%s, %s)
                """
                cursor.execute(update_query, (
                    compte_id, sous_compte_id, debit_transaction_id, credit_transaction_id
                ))

                return True, "Transfert effectué avec succès"

        except Exception as e:
            logger.error(f"Erreur transfert compte → sous-compte: {e}")
            return False, f"Erreur lors du transfert: {str(e)}"

    def transfert_sous_compte_vers_compte(self, sous_compte_id, compte_id, montant, user_id, description="", date_transaction = datetime.now()):
        """
        Transfert d'un sous-compte vers un compte principal.
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le sous-compte appartient au compte
                cursor.execute(
                    "SELECT id FROM sous_comptes WHERE id = %s AND compte_principal_id = %s",
                    (sous_compte_id, compte_id)
                )
                if not cursor.fetchone():
                    return False, "Le sous-compte n'appartient pas à ce compte"

                # Vérifier le solde du sous-compte
                cursor.execute("SELECT solde FROM sous_comptes WHERE id = %s", (sous_compte_id,))
                result = cursor.fetchone()
                if not result:
                    return False, "Sous-compte non trouvé"
                solde_sous_compte = Decimal(str(result['solde']))
                if solde_sous_compte < montant:
                    return False, "Solde insuffisant sur le sous-compte"

                # Générer référence et description
                timestamp = int(time.time())
                reference = f"TRF_SC_CP_{timestamp}"
                reference_transfert = f"TRF_{int(time.time())}_{user_id}_{secrets.token_hex(6)}"
                desc_complete = f"{description} (Réf: {reference})"
                if date_transaction is None:
                    date_transaction = datetime.now()

                # ⚠️ UTILISER _inserer_transaction_with_cursor pour DÉBIT sur le sous-compte
                success, message, debit_transaction_id = self._inserer_transaction_with_cursor(
                    cursor,
                    compte_type='sous_compte',
                    compte_id=sous_compte_id,
                    type_transaction='transfert_sous_vers_compte',
                    montant=montant,
                    description=desc_complete,
                    user_id=user_id,
                    date_transaction=date_transaction,
                    validate_balance=True,
                    reference_transfert=reference_transfert
                )
                if not success:
                    return False, f"Erreur débit sous-compte: {message}"

                # ⚠️ UTILISER _inserer_transaction_with_cursor pour CRÉDIT sur le compte principal
                success, message, credit_transaction_id = self._inserer_transaction_with_cursor(
                    cursor,
                    compte_type='compte_principal',
                    compte_id=compte_id,
                    type_transaction='transfert_sous_vers_compte',  # Même type
                    montant=montant,
                    description=desc_complete,
                    user_id=user_id,
                    date_transaction=date_transaction,
                    validate_balance=False,
                    reference_transfert=reference_transfert
                )
                if not success:
                    return False, f"Erreur crédit compte principal: {message}"

                # Mettre à jour les relations
                update_query = """
                UPDATE transactions SET
                    sous_compte_source_id = %s,
                    compte_destination_id = %s
                WHERE id IN (%s, %s)
                """
                cursor.execute(update_query, (
                    sous_compte_id, compte_id, debit_transaction_id, credit_transaction_id
                ))

                return True, "Transfert effectué avec succès"

        except Exception as e:
            logger.error(f"Erreur transfert sous-compte → compte: {e}")
            return False, f"Erreur lors du transfert: {str(e)}"

    # ===== TRANSFERTS EXTERNES =====

    def create_transfert_externe(self, source_type: str, source_id: int, user_id: int,
                                iban_dest: str, bic_dest: str, nom_dest: str,
                                montant: Decimal, devise: str = 'EUR',
                                description: str = "", date_transaction: datetime = None) -> Tuple[bool, str]:
        """
        Crée un transfert vers un compte externe (IBAN).
        Utilise une seule transaction pour débiter le compte et créer l'ordre de transfert.
        """
        # Validations
        if montant <= 0:
            return False, "Le montant doit être positif"

        if not iban_dest or len(iban_dest.strip()) < 15:
            return False, "IBAN destination invalide"

        # Utiliser la date actuelle si non spécifiée
        if date_transaction is None:
            date_transaction = datetime.now()

        try:
            # L'ensemble de l'opération est géré dans une seule transaction 'with'
            with self.db.get_cursor() as cursor:
                # Vérifier l'appartenance du compte
                if not self._verifier_appartenance_compte_with_cursor(cursor, source_type, source_id, user_id):
                    return False, "Compte source non trouvé ou non autorisé"

                # Insérer la transaction de débit
                success, message, transaction_id = self._inserer_transaction_with_cursor(
                    cursor, source_type, source_id, 'transfert_externe', montant,
                    description, user_id, date_transaction, True
                )

                if not success:
                    return False, message

                # Créer l'ordre de transfert externe
                query_ordre = """
                INSERT INTO transferts_externes (
                    transaction_id, iban_dest, bic_dest, nom_dest,
                    montant, devise, statut, date_demande
                ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                """
                cursor.execute(query_ordre, (
                    transaction_id, iban_dest.strip().upper(),
                    bic_dest.strip().upper() if bic_dest else '',
                    nom_dest.strip(), float(montant), devise
                ))

                return True, "Ordre de transfert externe créé avec succès"

        except Exception as e:
            # Le rollback est géré automatiquement par le bloc 'with'
            logger.error(f"Erreur transfert externe: {e}")
            return False, f"Erreur lors du transfert externe: {str(e)}"

    def get_historique_compte(self, compte_type: str, compte_id: int, user_id: int,
                            date_from: str = None, date_to: str = None,
                            limit: int = 50) -> List[Dict]:
        """Récupère l'historique des transactions d'un compte"""

        try:
            with self.db.get_cursor() as cursor:
                if not self._verifier_appartenance_compte_with_cursor(cursor, compte_type, compte_id, user_id):
                    return []

                # Requête pour compte principal
                if compte_type == 'compte_principal':
                    query = """
                    SELECT
                    t.id,
                    t.type_transaction,
                    t.montant,
                    t.description,
                    t.reference,
                    t.date_transaction,
                    t.solde_apres,
                    -- Sous-comptes
                    sc.nom_sous_compte as sous_compte_source,
                    sc_dest.nom_sous_compte as sous_compte_dest,
                    -- Comptes principaux source/destination
                    cp_source.nom_compte as compte_source_nom,
                    cp_dest.nom_compte as compte_dest_nom,
                    -- Transferts externes
                    te.iban_dest,
                    te.nom_dest,
                    te.statut as statut_externe,
                    CASE
                        WHEN t.type_transaction = 'transfert_compte_vers_sous' THEN 'Débit'
                        WHEN t.type_transaction = 'transfert_sous_vers_compte' THEN 'Crédit'
                        ELSE NULL
                    END as sens_operation
                FROM transactions t
                -- Sous-comptes
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                LEFT JOIN sous_comptes sc_dest ON t.sous_compte_destination_id = sc_dest.id
                -- Comptes principaux (à adapter selon vos colonnes réelles)
                LEFT JOIN comptes_principaux cp_source ON t.compte_source_id = cp_source.id
                LEFT JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                -- Transferts externes
                LEFT JOIN transferts_externes te ON t.id = te.transaction_id
                WHERE t.compte_principal_id = %s
                    """

                # Requête pour sous-compte
                else:
                    query = """
                    SELECT
                        t.id,
                        t.type_transaction,
                        t.montant,
                        t.description,
                        t.reference,
                        t.date_transaction,
                        t.solde_apres,
                        cp.nom_compte as compte_principal_lie,
                        cp_dest.nom_compte as compte_principal_dest,
                        CASE
                            WHEN t.type_transaction = 'transfert_compte_vers_sous' THEN 'Crédit'
                            WHEN t.type_transaction = 'transfert_sous_vers_compte' THEN 'Débit'
                            ELSE NULL
                        END as sens_operation
                    FROM transactions t
                    LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                    LEFT JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                    LEFT JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                    WHERE t.sous_compte_id = %s OR t.sous_compte_destination_id = %s
                    """

                params = [compte_id] if compte_type == 'compte_principal' else [compte_id, compte_id]

                # Filtres de date
                if date_from:
                    query += " AND DATE(t.date_transaction) >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND DATE(t.date_transaction) <= %s"
                    params.append(date_to)

                query += " ORDER BY t.date_transaction DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, params)
                transactions = cursor.fetchall()

                # Formatage des résultats
                for transaction in transactions:
                    transaction['montant'] = float(transaction['montant'])
                    #transaction['date_transaction'] = transaction['date_transaction'].isoformat()

                return transactions

        except Exception as e:
            logger.error(f"Erreur récupération historique: {e}")
            return []

    def get_statistiques_compte(self, compte_type: str, compte_id: int, user_id: int, date_debut: str = None, date_fin: str = None) -> Dict:
        """Récupère les statistiques d'un compte sur une période personnalisée"""
        try:
            with self.db.get_cursor() as cursor:
                if not self._verifier_appartenance_compte_with_cursor(cursor, compte_type, compte_id, user_id):
                    return {}

                if compte_type == 'compte_principal':
                    condition_compte = "t.compte_principal_id = %s"
                else:
                    condition_compte = "t.sous_compte_id = %s"

                query = f"""
                SELECT
                    SUM(CASE
                        WHEN t.type_transaction IN ('depot', 'transfert_entrant', 'transfert_sous_vers_compte', 'recredit_annulation')
                        THEN t.montant ELSE 0 END) as total_entrees,
                    SUM(CASE
                        WHEN t.type_transaction IN ('retrait', 'transfert_sortant', 'transfert_externe', 'transfert_compte_vers_sous')
                        THEN t.montant ELSE 0 END) as total_sorties,
                    COUNT(*) as nombre_transactions,
                    AVG(t.montant) as montant_moyen
                FROM transactions t
                WHERE {condition_compte}
                AND t.date_transaction BETWEEN %s AND %s
                """

                cursor.execute(query, (compte_id, date_debut, date_fin))
                stats = cursor.fetchone()

                if stats:
                    return {
                        'total_entrees': float(stats['total_entrees'] or 0),
                        'total_sorties': float(stats['total_sorties'] or 0),
                        'solde_variation': float((stats['total_entrees'] or 0) - (stats['total_sorties'] or 0)),
                        'nombre_transactions': int(stats['nombre_transactions'] or 0),
                        'montant_moyen': float(stats['montant_moyen'] or 0)
                    }
                return {}
        except Exception as e:
            logger.error(f"Erreur récupération statistiques: {e}")
            return {}

    def get_transferts_externes_pending(self, user_id: int) -> List[Dict]:
        """Récupère les transferts externes en attente pour un utilisateur"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    te.id, te.iban_dest, te.bic_dest, te.nom_dest,
                    te.montant, te.devise, te.statut, te.date_demande,
                    t.description, t.reference,
                    CASE
                        WHEN t.compte_principal_id IS NOT NULL THEN cp.nom_compte
                        WHEN t.sous_compte_id IS NOT NULL THEN sc.nom_sous_compte
                    END as nom_compte_source
                FROM transferts_externes te
                JOIN transactions t ON te.transaction_id = t.id
                LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                WHERE t.utilisateur_id = %s AND te.statut = 'pending'
                ORDER BY te.date_demande DESC
                """
                cursor.execute(query, (user_id,))
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Erreur récupération transferts externes: {e}")
            return []

    def annuler_transfert_externe(self, transfert_externe_id: int, user_id: int) -> Tuple[bool, str]:
        """Annule un transfert externe en attente et recrédite le compte"""
        try:
            # L'ensemble de l'opération est géré dans une seule transaction 'with'
            with self.db.get_cursor() as cursor:
                # Récupérer les détails du transfert externe
                query = """
                SELECT te.*, t.compte_principal_id, t.sous_compte_id, t.utilisateur_id
                FROM transferts_externes te
                JOIN transactions t ON te.transaction_id = t.id
                WHERE te.id = %s AND te.statut = 'pending'
                """
                cursor.execute(query, (transfert_externe_id,))
                transfert = cursor.fetchone()

                if not transfert:
                    return False, "Transfert externe non trouvé ou déjà traité"

                if transfert['utilisateur_id'] != user_id:
                    return False, "Non autorisé à annuler ce transfert"

                # Déterminer le type et l'ID du compte source
                if transfert['compte_principal_id']:
                    compte_type = 'compte_principal'
                    compte_id = transfert['compte_principal_id']
                else:
                    compte_type = 'sous_compte'
                    compte_id = transfert['sous_compte_id']

                # Recréditer le compte source
                montant = Decimal(str(transfert['montant']))

                # Utiliser la méthode d'insertion pour créer une transaction de recrédit
                success, message, _ = self._inserer_transaction_with_cursor(
                    cursor, compte_type, compte_id, 'recredit_annulation', montant,
                    f"Annulation transfert externe vers {transfert['iban_dest']}",
                    user_id, datetime.now(), False
                )

                if not success:
                    return False, f"Erreur lors du recrédit: {message}"

                # Marquer le transfert comme annulé
                cursor.execute("UPDATE transferts_externes SET statut = 'cancelled' WHERE id = %s",
                            (transfert_externe_id,))

                return True, "Transfert externe annulé et compte recrédité"

        except Exception as e:
            # Le rollback est géré automatiquement par le bloc 'with'
            logger.error(f"Erreur annulation transfert externe: {e}")
            return False, f"Erreur lors de l'annulation: {str(e)}"

    def get_evolution_soldes_quotidiens_compte(self, compte_id: int, user_id: int, date_debut: str = None, date_fin: str = None) -> List[Dict]:
        """
        Récupère l'évolution quotidienne des soldes d'un compte,
        en remplissant les jours sans transaction par le solde du jour précédent.
        """
        try:
            with self.db.get_cursor() as cursor:

                # 1. Vérification d'appartenance (simplifiée)
                cursor.execute("SELECT id, solde_initial FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s", (compte_id, user_id))
                row = cursor.fetchone()
                if not row:
                    logger.warning(f"Tentative d'accès non autorisé ou compte inexistant: compte={compte_id}, user={user_id}")
                    return []
                solde_initial = Decimal(str(row['solde_initial'] or '0.00'))

                # 2. Préparation des dates
                debut_dt = datetime.strptime(date_debut, '%Y-%m-%d').date()
                fin_dt = datetime.strptime(date_fin, '%Y-%m-%d').date() # On travaille avec des objets date simples

                # 3. Requête SQL (pour récupérer le DERNIER solde APRES transaction pour chaque jour où il y a eu une activité)
                query = """
                    SELECT date_transaction, solde_apres
                    FROM (
                        SELECT
                            date_transaction,
                            solde_apres,
                            ROW_NUMBER() OVER (
                                PARTITION BY DATE(date_transaction)
                                ORDER BY id DESC
                            ) as rn
                        FROM transactions
                        WHERE compte_principal_id = %s
                        AND date_transaction >= %s
                        AND date_transaction <= %s
                    ) ranked
                    WHERE rn = 1
                    ORDER BY date_transaction;
                """
                cursor.execute(query, (compte_id, date_debut, date_fin))
                transactions_par_jour = cursor.fetchall()

                # Si aucune transaction n'est trouvée dans la période, on renvoie une liste vide (ou l'initialisation)
                if not transactions_par_jour:
                    return []

                # --- 4. Logique de Remplissage des Jours Manquants (Report de Solde) ---

                # Map des soldes de fin de journée pour un accès rapide
                soldes_fin_journee = {t['date_transaction'].date(): Decimal(str(t['solde_apres'])) for t in transactions_par_jour}

                # Déterminer le solde APRES la dernière transaction AVANT date_debut
                # C'est nécessaire pour initialiser le report sur date_debut si aucune transaction n'a eu lieu ce jour-là
                cursor.execute("""
                    SELECT solde_apres FROM transactions
                    WHERE compte_principal_id = %s AND date_transaction < %s
                    ORDER BY date_transaction DESC, id DESC LIMIT 1
                """, (compte_id, date_debut))
                solde_initial_report = Decimal(str(cursor.fetchone()['solde_apres'])) if cursor.rowcount else solde_initial

                jours_complets = []
                current_solde = solde_initial_report
                current_date = debut_dt

                while current_date <= fin_dt:
                    # 1. Si une transaction a eu lieu ce jour, utiliser le solde de fin de journée
                    if current_date in soldes_fin_journee:
                        current_solde = soldes_fin_journee[current_date]
                    # 2. Sinon (jour sans transaction), le solde est simplement reporté (current_solde est inchangé)

                    jours_complets.append({
                        'date': current_date,
                        'solde_apres': float(current_solde) # Convertir en float pour l'utilisation dans la vue
                    })

                    current_date += timedelta(days=1)

                return jours_complets

        except Exception as e:
            logger.error(f"Erreur récupération évolution soldes compte: {e}")
            return []


    def get_evolution_soldes_quotidiens_sous_compte(self, sous_compte_id: int, user_id: int, nb_jours: int = 30) -> List[Dict]:
        """
        Récupère l'évolution quotidienne des soldes d'un sous-compte,
        en remplissant les jours sans transaction par le solde du jour précédent.
        """
        try:
            with self.db.get_cursor() as cursor:

                # --- 1. Définition de la période ---
                date_fin_dt = date.today()
                date_debut_dt = date_fin_dt - timedelta(days=nb_jours - 1)

                # Conversion au format string pour la requête SQL
                date_debut_str = date_debut_dt.strftime('%Y-%m-%d')
                date_fin_str = date_fin_dt.strftime('%Y-%m-%d')

                # NOTE: Il faudrait idéalement une vérification d'appartenance du sous-compte au user_id ici.

                # --- 2. Requête SQL (Récupération des soldes de fin de journée pour les jours AVEC transaction) ---

                # Nous utilisons la méthode ROW_NUMBER() plus moderne comme dans la version compte principal
                query = """
                    SELECT date_transaction, solde_apres
                    FROM (
                        SELECT
                            date_transaction,
                            solde_apres,
                            ROW_NUMBER() OVER (
                                PARTITION BY DATE(date_transaction)
                                ORDER BY id DESC
                            ) as rn
                        FROM transactions
                        WHERE sous_compte_id = %s
                        AND date_transaction >= %s
                        AND date_transaction <= %s
                    ) ranked
                    WHERE rn = 1
                    ORDER BY date_transaction;
                """
                cursor.execute(query, (sous_compte_id, date_debut_str, date_fin_str))
                transactions_par_jour = cursor.fetchall()

                if not transactions_par_jour:
                    return []

                # --- 3. Logique de Remplissage des Jours Manquants (Report de Solde) ---

                soldes_fin_journee = {t['date_transaction'].date(): Decimal(str(t['solde_apres'])) for t in transactions_par_jour}

                # Déterminer le solde APRES la dernière transaction AVANT date_debut
                cursor.execute("""
                    SELECT solde_apres FROM transactions
                    WHERE sous_compte_id = %s AND date_transaction < %s
                    ORDER BY date_transaction DESC, id DESC LIMIT 1
                """, (sous_compte_id, date_debut_str))

                # Dans un sous-compte, on part souvent de 0.0 si aucune transaction passée n'est trouvée.
                solde_initial_report = Decimal(str(cursor.fetchone()['solde_apres'])) if cursor.rowcount else Decimal('0.00')

                jours_complets = []
                current_solde = solde_initial_report
                current_date = date_debut_dt

                while current_date <= date_fin_dt:
                    if current_date in soldes_fin_journee:
                        # Mise à jour avec le solde réel de fin de journée
                        current_solde = soldes_fin_journee[current_date]
                    # Sinon, le solde est reporté (current_solde reste inchangé)

                    jours_complets.append({
                        'date': current_date,
                        'solde_apres': float(current_solde)
                    })

                    current_date += timedelta(days=1)

                return jours_complets

        except Exception as e:
            logger.error(f"Erreur récupération évolution soldes sous-compte: {e}")
            return []

    def get_transaction_by_id(self, transaction_id: int) -> Optional[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    t.*,
                    COALESCE(cp.utilisateur_id, (
                        SELECT cp2.utilisateur_id
                        FROM sous_comptes sc
                        JOIN comptes_principaux cp2 ON sc.compte_principal_id = cp2.id
                        WHERE sc.id = t.sous_compte_id
                    )) as owner_user_id,
                    -- Compte principal + banque
                    cp.nom_compte as compte_principal_nom,
                    b1.nom as compte_principal_banque,
                    sc.nom_sous_compte as sous_compte_nom,
                    -- Compte destination + banque
                    cp_dest.nom_compte as compte_destination_nom,
                    b2.nom as compte_destination_banque,
                    -- Compte source + banque
                    cp_src.nom_compte as compte_source_nom,
                    b3.nom as compte_source_banque
                FROM transactions t
                -- Compte principal
                LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                LEFT JOIN banques b1 ON cp.banque_id = b1.id
                -- Sous-compte
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                -- Compte destination
                LEFT JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                LEFT JOIN banques b2 ON cp_dest.banque_id = b2.id
                -- Compte source
                LEFT JOIN comptes_principaux cp_src ON t.compte_source_id = cp_src.id
                LEFT JOIN banques b3 ON cp_src.banque_id = b3.id
                WHERE t.id = %s
                """
                cursor.execute(query, (transaction_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur récupération transaction: {e}")
            return None

    def get_solde_courant(self, compte_type: str, compte_id: int, user_id: int) -> Decimal:
        """Récupère le solde courant d'un compte"""
        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                                (compte_id, user_id))
                else:
                    cursor.execute("""
                        SELECT sc.solde
                        FROM sous_comptes sc
                        JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                        WHERE sc.id = %s AND cp.utilisateur_id = %s
                    """, (compte_id, user_id))

                result = cursor.fetchone()
                return Decimal(str(result['solde'])) if result and 'solde' in result else Decimal('0')
        except Exception as e:
            logger.error(f"Erreur récupération solde courant: {e}")
            return Decimal('0')

    def get_solde_total_avec_sous_comptes(self, compte_principal_id: int, user_id: int) -> Decimal:
        """Calcule le solde total d'un compte principal incluant ses sous-comptes"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le compte principal appartient à l'utilisateur
                cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                            (compte_principal_id, user_id))
                result = cursor.fetchone()
                if not result:
                    return Decimal('0')

                solde_total = Decimal(str(result['solde']))

                # Ajouter les soldes des sous-comptes
                cursor.execute("""
                    SELECT solde FROM sous_comptes
                    WHERE compte_principal_id = %s
                """, (compte_principal_id,))

                sous_comptes = cursor.fetchall()
                for sc in sous_comptes:
                    solde_total += Decimal(str(sc['solde']))

                return solde_total
        except Exception as e:
            logger.error(f"Erreur calcul solde total: {e}")
            return Decimal('0')

    def get_categories_par_type(self, compte_type: str, compte_id: int, user_id: int, date_debut: str, date_fin: str) -> Dict[str, Decimal]:
        """
        Récupère la répartition des transactions par catégorie pour un compte donné sur une période.

        Args:
            compte_type (str): 'compte_principal' ou 'sous_compte'
            compte_id (int): ID du compte
            user_id (int): ID de l'utilisateur
            date_debut (str): Date de début au format 'YYYY-MM-DD'
            date_fin (str): Date de fin au format 'YYYY-MM-DD'

        Returns:
            Dict[str, Decimal]: Dictionnaire {catégorie: montant_total}
        """
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

        try:
            with self.db.get_cursor() as cursor:
                # Vérifier l'appartenance du compte
                if not self._verifier_appartenance_compte_with_cursor(cursor, compte_type, compte_id, user_id):
                    logger.warning(f"Tentative d'accès non autorisé aux catégories: user={user_id}, compte={compte_id} ({compte_type})")
                    return {}

                # Construire la condition selon le type de compte
                if compte_type == 'compte_principal':
                    condition_compte = "compte_principal_id = %s"
                else:
                    condition_compte = "sous_compte_id = %s"

                query = f"""
                SELECT
                    type_transaction,
                    SUM(montant) as total
                FROM transactions
                WHERE {condition_compte}
                AND date_transaction BETWEEN %s AND %s
                GROUP BY type_transaction
                ORDER BY total DESC
                """
                cursor.execute(query, (compte_id, date_debut, date_fin))
                rows = cursor.fetchall()

                result = {}
                for row in rows:
                    type_tx = row['type_transaction']
                    montant = Decimal(str(row['total'] or '0'))

                    # Inclure dans la catégorie correspondante
                    cat = mapping_categories.get(type_tx, 'Autres')
                    result[cat] = result.get(cat, Decimal('0')) + montant

                return result

        except Exception as e:
            logger.error(f"Erreur dans get_categories_par_type: {e}", exc_info=True)
            return {}

    def get_categories_par_type_complet(self, user_id: int, date_debut: str, date_fin: str) -> Dict[str, Decimal]:
        """
        Récupère la répartition des transactions par catégorie pour **tous les comptes** de l'utilisateur.
        """
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

        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    t.type_transaction,
                    SUM(t.montant) as total
                FROM transactions t
                JOIN comptes_principaux cp ON (
                    t.compte_principal_id = cp.id
                    OR t.compte_principal_id IN (
                        SELECT sc2.compte_principal_id
                        FROM sous_comptes sc2
                        WHERE sc2.id = t.sous_compte_id
                    )
                )
                WHERE cp.utilisateur_id = %s
                AND t.date_transaction BETWEEN %s AND %s
                GROUP BY t.type_transaction
                """
                cursor.execute(query, (user_id, date_debut, date_fin))
                rows = cursor.fetchall()

                result = {}
                for row in rows:
                    type_tx = row['type_transaction']
                    montant = Decimal(str(row['total'] or '0'))
                    cat = mapping_categories.get(type_tx, 'Autres')
                    result[cat] = result.get(cat, Decimal('0')) + montant

                return result

        except Exception as e:
            logger.error(f"Erreur dans get_categories_par_type_complet: {e}", exc_info=True)
            return {}

    def get_categories_par_type_sous_compte(self, sous_compte_id: int, user_id: int, date_debut: str, date_fin: str) -> Dict[str, Decimal]:
        """
        Récupère la répartition des transactions par catégorie pour un **sous-compte** donné.
        """
        mapping_categories = {
            'transfert_compte_vers_sous': 'Crédits (compte → sous-compte)',
            'transfert_sous_vers_compte': 'Débits (sous-compte → compte)',
            'depot': 'Dépôts directs',
            'retrait': 'Retraits directs',
            # Tu peux adapter selon ce qui est pertinent pour les sous-comptes
        }

        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le sous-compte appartient à l'utilisateur
                cursor.execute("""
                    SELECT sc.id
                    FROM sous_comptes sc
                    JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                    WHERE sc.id = %s AND cp.utilisateur_id = %s
                """, (sous_compte_id, user_id))
                if not cursor.fetchone():
                    logger.warning(f"Accès refusé au sous-compte {sous_compte_id} pour user {user_id}")
                    return {}

                query = """
                SELECT
                    type_transaction,
                    SUM(montant) as total
                FROM transactions
                WHERE sous_compte_id = %s
                AND date_transaction BETWEEN %s AND %s
                GROUP BY type_transaction
                """
                cursor.execute(query, (sous_compte_id, date_debut, date_fin))
                rows = cursor.fetchall()

                result = {}
                for row in rows:
                    type_tx = row['type_transaction']
                    montant = Decimal(str(row['total'] or '0'))
                    cat = mapping_categories.get(type_tx, 'Autres')
                    result[cat] = result.get(cat, Decimal('0')) + montant

                return result

        except Exception as e:
            logger.error(f"Erreur dans get_categories_par_type_sous_compte: {e}", exc_info=True)
            return {}

    def get_transaction_with_ecritures_total(self, transaction_id: int, user_id: int) -> Optional[Dict]:
        """Récupère une transaction + le total des écritures liées avec vérification de propriété complète"""
        try:
            with self.db.get_cursor() as cursor:
                # Requête améliorée avec toutes les vérifications de propriété
                cursor.execute("""
                    SELECT
                        t.*,
                        COALESCE(SUM(e.montant), 0) as total_ecritures,
                        COUNT(e.id) as nb_ecritures,
                        -- Informations de propriété
                        COALESCE(cp.utilisateur_id, (
                            SELECT cp2.utilisateur_id
                            FROM sous_comptes sc
                            JOIN comptes_principaux cp2 ON sc.compte_principal_id = cp2.id
                            WHERE sc.id = t.sous_compte_id
                        )) as owner_user_id,
                        -- Informations du compte
                        cp.nom_compte as compte_principal_nom,
                        sc.nom_sous_compte as sous_compte_nom
                    FROM transactions t
                    LEFT JOIN ecritures_comptables e ON t.id = e.transaction_id
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                    WHERE t.id = %s
                    GROUP BY t.id, cp.utilisateur_id, cp.nom_compte, sc.nom_sous_compte
                """, (transaction_id,))

                tx = cursor.fetchone()
                if not tx:
                    return None

                # Vérification de propriété améliorée
                owner_id = tx.get('owner_user_id')
                if not owner_id or owner_id != user_id:
                    # Vérification supplémentaire pour les transactions liées à des sous-comptes
                    if tx.get('sous_compte_id'):
                        cursor.execute("""
                            SELECT cp.utilisateur_id
                            FROM sous_comptes sc
                            JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                            WHERE sc.id = %s
                        """, (tx['sous_compte_id'],))
                        sous_compte_owner = cursor.fetchone()
                        if not sous_compte_owner or sous_compte_owner['utilisateur_id'] != user_id:
                            return None
                    else:
                        return None

                return tx
        except Exception as e:
            logger.error(f"Erreur get_transaction_with_ecritures_total: {e}")
            return None

    def _check_transaction_ownership(self, transaction_id: int, user_id: int) -> bool:
        """Vérifie si l'utilisateur est propriétaire de la transaction"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT
                        COALESCE(cp.utilisateur_id, (
                            SELECT cp2.utilisateur_id
                            FROM sous_comptes sc
                            JOIN comptes_principaux cp2 ON sc.compte_principal_id = cp2.id
                            WHERE sc.id = t.sous_compte_id
                        )) as owner_user_id
                    FROM transactions t
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    WHERE t.id = %s
                """, (transaction_id,))

                result = cursor.fetchone()
                return result and result['owner_user_id'] == user_id
        except Exception as e:
            logger.error(f"Erreur vérification propriété transaction: {e}")
            return False

    def get_contacts_avec_transactions(self, user_id: int) -> List[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT
                    c.id_contact,
                    c.nom,
                    c.iban_dest,   -- si tu stockes l'IBAN dans contacts
                    te.iban_dest as iban_transaction
                FROM ecritures_comptables e
                JOIN contacts c ON e.id_contact = c.id_contact
                LEFT JOIN transactions t ON e.transaction_id = t.id
                LEFT JOIN transferts_externes te ON t.id = te.transaction_id
                WHERE e.utilisateur_id = %s
            """, (user_id,))
            return cursor.fetchall()

    def get_comptes_interagis(self, user_id: int) -> List[Dict]:
        """
        Récupère TOUS les comptes bancaires avec lesquels l'utilisateur a interagi :
        - Ses propres comptes,
        - Les comptes externes liés à des contacts,
        - Les comptes apparaissant comme source ou destination dans ses transactions.
        """
        try:
            with self.db.get_cursor() as cursor:
                # 1. Mes propres comptes
                query_internes = """
                    SELECT
                        c.id,
                        c.nom_compte,
                        c.iban,
                        c.bic,
                        c.type_compte,
                        c.solde,
                        c.devise,
                        c.date_ouverture,
                        'interne' AS type_compte_origine
                    FROM comptes_principaux c
                    WHERE c.utilisateur_id = %s
                """
                cursor.execute(query_internes, (user_id,))
                comptes = {row['id']: row for row in cursor.fetchall()}

                # 2. Comptes liés à des contacts (externes)
                query_contacts = """
                    SELECT DISTINCT
                        cp.id,
                        cp.nom_compte,
                        cp.iban,
                        cp.bic,
                        cp.type_compte,
                        0.00 AS solde,
                        cp.devise,
                        cp.date_ouverture,
                        'externe' AS type_compte_origine
                    FROM contact_comptes cc
                    JOIN comptes_principaux cp ON cc.compte_id = cp.id
                    WHERE cc.utilisateur_id = %s
                """
                cursor.execute(query_contacts, (user_id,))
                for row in cursor.fetchall():
                    if row['id'] not in comptes:
                        comptes[row['id']] = row

                # 3. Comptes apparaissant dans les transactions (source ou destination)
                query_transactions = """
                    SELECT DISTINCT
                        cp.id,
                        cp.nom_compte,
                        cp.iban,
                        cp.bic,
                        cp.type_compte,
                        cp.solde,
                        cp.devise,
                        cp.date_ouverture,
                        'transaction' AS type_compte_origine
                    FROM transactions t
                    JOIN comptes_principaux cp ON (
                        cp.id = t.compte_destination_id OR
                        cp.id = t.compte_source_id
                    )
                    WHERE t.utilisateur_id = %s
                    AND cp.id IS NOT NULL
                """
                cursor.execute(query_transactions, (user_id,))
                for row in cursor.fetchall():
                    if row['id'] not in comptes:
                        # Marquer comme 'externe' si ce n’est pas l’un de mes comptes
                        if row.get('type_compte_origine') == 'transaction' and row['id'] not in [
                            c['id'] for c in comptes.values() if c.get('type_compte_origine') == 'interne'
                        ]:
                            row['type_compte_origine'] = 'externe'
                        comptes[row['id']] = row

                # Retourner la liste finale
                return list(comptes.values())

        except Exception as e:
            logger.error(f"Erreur dans get_comptes_interagis: {e}", exc_info=True)
            return []

    def get_transactions_sans_ecritures(self, user_id: int, date_from: str = None, date_to: str = None,
                                  statut_comptable: str = None, limit: int = 100) -> List[Dict]:
        """Récupère les transactions sans écritures comptables associées"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    t.*,
                    cp.nom_compte as compte_principal_nom,
                    sc.nom_sous_compte as sous_compte_nom,
                    COUNT(e.id) as nb_ecritures_liees,
                    COALESCE(SUM(e.montant), 0) as total_ecritures
                FROM transactions t
                LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                LEFT JOIN ecritures_comptables e ON t.id = e.transaction_id
                WHERE (cp.utilisateur_id = %s OR sc.compte_principal_id IN (
                    SELECT id FROM comptes_principaux WHERE utilisateur_id = %s
                ))
                AND t.id NOT IN (
                    SELECT DISTINCT transaction_id
                    FROM ecritures_comptables
                    WHERE transaction_id IS NOT NULL
                )
                """
                params = [user_id, user_id]

                # Filtres optionnels
                if date_from:
                    query += " AND DATE(t.date_transaction) >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND DATE(t.date_transaction) <= %s"
                    params.append(date_to)
                if statut_comptable:
                    query += " AND t.statut_comptable = %s"
                    params.append(statut_comptable)

                query += """
                GROUP BY t.id
                HAVING nb_ecritures_liees = 0
                ORDER BY t.date_transaction DESC
                LIMIT %s
                """
                params.append(limit)

                cursor.execute(query, params)
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Erreur récupération transactions sans écritures: {e}")
            return []



    def get_stats_transactions_comptables(self, user_id: int) -> Dict:
        """Retourne les statistiques des transactions par statut comptable"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    statut_comptable,
                    COUNT(*) as nb_transactions,
                    SUM(montant) as total_montant,
                    AVG(montant) as moyenne_montant
                FROM transactions t
                LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                WHERE cp.utilisateur_id = %s OR sc.compte_principal_id IN (
                    SELECT id FROM comptes_principaux WHERE utilisateur_id = %s
                )
                GROUP BY statut_comptable
                """
                cursor.execute(query, (user_id, user_id))
                stats = cursor.fetchall()

                return {
                    'statistiques': stats,
                    'total_transactions': sum(s['nb_transactions'] for s in stats),
                    'total_montant': sum(float(s['total_montant'] or 0) for s in stats)
                }

        except Exception as e:
            logger.error(f"Erreur statistiques transactions comptables: {e}")
            return {}

    def creer_ecriture_automatique(self, transaction_id: int, user_id: int, categorie_id: int = None) -> Tuple[bool, str]:
        """Crée automatiquement une écriture comptable pour une transaction avec statut 'pending'"""
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer les détails de la transaction
                transaction = self.get_transaction_by_id(transaction_id)
                if not transaction or transaction.get('owner_user_id') != user_id:
                    return False, "Transaction non trouvée ou non autorisée"

                # Déterminer le type d'écriture basé sur le type de transaction
                type_ecriture = self._determiner_type_ecriture(transaction['type_transaction'])

                # Déterminer la catégorie par défaut si non fournie
                if not categorie_id:
                    categorie_id = self._get_categorie_par_defaut(type_ecriture, user_id)
                    if not categorie_id:
                        return False, "Aucune catégorie par défaut trouvée"

                # Créer l'écriture comptable avec statut 'pending'
                ecriture_data = {
                    'date_ecriture': transaction['date_transaction'],
                    'compte_bancaire_id': transaction['compte_principal_id'],
                    'categorie_id': categorie_id,
                    'montant': transaction['montant'],
                    'devise': 'CHF',
                    'description': f"Auto: {transaction['description']}",
                    'type_ecriture': type_ecriture,
                    'utilisateur_id': user_id,
                    'statut': 'pending',  # Statut en attente par défaut
                    'transaction_id': transaction_id
                }

                # Utiliser votre modèle d'écriture comptable existant
                success = self.ecriture_model.create(ecriture_data)

                if success:
                    # Marquer la transaction comme comptabilisée
                    self.update_statut_comptable(transaction_id, user_id, 'comptabilise')
                    return True, "Écriture créée automatiquement avec statut 'en attente'"
                else:
                    return False, "Erreur lors de la création de l'écriture"

        except Exception as e:
            logger.error(f"Erreur création écriture automatique: {e}")
            return False, f"Erreur: {str(e)}"

    def _determiner_type_ecriture(self, type_transaction: str) -> str:
        """Détermine le type d'écriture basé sur le type de transaction"""
        types_depense = ['retrait', 'transfert_sortant', 'transfert_externe']
        types_recette = ['depot', 'transfert_entrant', 'recredit_annulation']

        if type_transaction in types_depense:
            return 'depense'
        elif type_transaction in types_recette:
            return 'recette'
        else:
            return 'depense'  # par défaut

    def _get_categorie_par_defaut(self, type_ecriture: str, user_id: int) -> int:
        """Récupère la catégorie par défaut selon le type d'écriture"""
        try:
            with self.db.get_cursor() as cursor:
                if type_ecriture == 'depense':
                    cursor.execute("""
                        SELECT id FROM categories_comptables
                        WHERE utilisateur_id = %s AND nom LIKE '%divers%' OR nom LIKE '%autres%'
                        LIMIT 1
                    """, (user_id,))
                else:
                    cursor.execute("""
                        SELECT id FROM categories_comptables
                        WHERE utilisateur_id = %s AND type_compte = 'Revenus'
                        LIMIT 1
                    """, (user_id,))

                result = cursor.fetchone()
                return result['id'] if result else None
        except Exception as e:
            logger.error(f"Erreur récupération catégorie par défaut: {e}")
            return None

    def get_transactions_sans_ecritures_par_compte(self, compte_id: int, user_id: int,
                                                date_from: str = None, date_to: str = None,
                                                statut_comptable: str = None) -> List[Dict]:
        """Récupère les transactions sans écritures comptables pour un compte spécifique"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le compte appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                    (compte_id, user_id)
                )
                if not cursor.fetchone():
                    return []

                query = """
                SELECT
                    t.*,
                    cp.nom_compte as compte_principal_nom,
                    cp_dest.nom_compte as compte_destination_nom,
                    sc.nom_sous_compte as sous_compte_nom,
                    COUNT(e.id) as nb_ecritures_liees,
                    COALESCE(SUM(e.montant), 0) as total_ecritures
                FROM
                    transactions t
                LEFT JOIN
                    comptes_principaux cp
                    ON t.compte_principal_id = cp.id
                LEFT JOIN
                    comptes_principaux cp_dest
                    ON t.compte_destination_id = cp_dest.id
                LEFT JOIN
                    sous_comptes sc
                    ON t.sous_compte_id = sc.id
                LEFT JOIN
                    ecritures_comptables e
                    ON t.id = e.transaction_id
                WHERE
                    t.compte_principal_id = %s
                    AND t.id NOT IN (
                        SELECT DISTINCT transaction_id
                        FROM ecritures_comptables
                        WHERE transaction_id IS NOT NULL
                    )
                """
                params = [compte_id]

                # Filtres optionnels
                if date_from:
                    query += " AND DATE(t.date_transaction) >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND DATE(t.date_transaction) <= %s"
                    params.append(date_to)
                if statut_comptable:
                    query += " AND t.statut_comptable = %s"
                    params.append(statut_comptable)

                query += """
                GROUP BY t.id
                HAVING nb_ecritures_liees = 0
                ORDER BY t.date_transaction DESC
                """

                cursor.execute(query, params)
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Erreur récupération transactions sans écritures par compte: {e}")
            return []

    def _get_daily_balances(self, compte_id: int, date_debut: date, date_fin: date,
                            type_transaction: str = 'total') -> Dict[date, Decimal]:
            """
            Retourne les soldes ou flux quotidiens d'un compte principal.
            type_transaction:
            - 'total'   → solde journalier (solde_final après chaque jour)
            - 'recette' → total des recettes quotidiennes
            - 'depense' → total des dépenses quotidiennes
            """
            try:
                with self.db.get_cursor() as cursor:
                    # 1. Récupérer le solde initial
                    cursor.execute("SELECT solde_initial FROM comptes_principaux WHERE id = %s", (compte_id,))
                    row = cursor.fetchone()
                    solde_initial = Decimal(str(row['solde_initial'])) if row and row['solde_initial'] is not None else Decimal('0')

                    # 2. Récupérer TOUTES les transactions du compte dans la période
                    cursor.execute("""
                        SELECT date_transaction, montant, type_transaction
                        FROM transactions
                        WHERE compte_principal_id = %s
                        AND date_transaction >= %s
                        AND date_transaction <= %s
                        ORDER BY date_transaction ASC
                    """, (compte_id, date_debut, date_fin))
                    txns = cursor.fetchall()

                    # 3. Préparer structure par date
                    recettes_par_jour = {}
                    depenses_par_jour = {}
                    solde_par_jour = {}

                    # Initialiser le solde courant
                    solde_courant = solde_initial

                    # Si on demande 'total', le solde_initial s'applique à date_debut
                    if type_transaction == 'total':
                        solde_par_jour[date_debut] = solde_initial

                    # 4. Parcourir les transactions
                    for tx in txns:
                        tx_date = tx['date_transaction'].date()
                        montant = Decimal(str(tx['montant']))
                        tx_type = tx['type_transaction']

                        # Classifier la transaction
                        if tx_type in ['depot', 'transfert_entrant', 'recredit_annulation', 'transfert_sous_vers_compte']:
                            # → Recette
                            recettes_par_jour[tx_date] = recettes_par_jour.get(tx_date, Decimal('0')) + montant
                            solde_courant += montant
                        elif tx_type in ['retrait', 'transfert_sortant', 'transfert_externe', 'transfert_compte_vers_sous']:
                            # → Dépense
                            depenses_par_jour[tx_date] = depenses_par_jour.get(tx_date, Decimal('0')) + montant
                            solde_courant -= montant
                        else:
                            logger.warning(f"Type de transaction inconnu : {tx_type}")
                            continue

                        # Enregistrer le solde à cette date
                        if type_transaction == 'total':
                            solde_par_jour[tx_date] = solde_courant

                    # 5. Remplir les jours manquants (report de solde ou zéro pour flux)
                    current = date_debut
                    result = {}
                    last_solde = solde_initial

                    while current <= date_fin:
                        if type_transaction == 'total':
                            if current in solde_par_jour:
                                last_solde = solde_par_jour[current]
                            result[current] = last_solde
                        elif type_transaction == 'recette':
                            result[current] = recettes_par_jour.get(current, Decimal('0'))
                        elif type_transaction == 'depense':
                            result[current] = depenses_par_jour.get(current, Decimal('0'))
                        else:
                            result[current] = Decimal('0')
                        current += timedelta(days=1)

                    return result

            except Exception as e:
                logger.error(f"Erreur dans _get_daily_balances (compte {compte_id}): {e}")
                return {}

    def compare_comptes_soldes_barres_horizontales(self, compte_id_1: int, compte_id_2: int,
                                    date_debut: date, date_fin: date,
                                    type_1: str, type_2: str,
                                    couleur_1: str = "#0000FF", couleur_2: str = "#00FF00") -> str:
        """
        Génère un graphique en BARRES SVG comparant l'évolution des soldes de deux comptes.
        """
        from datetime import timedelta

        # Récupérer les soldes quotidiens pour chaque compte et type
        soldes_1 = self._get_daily_balances(compte_id_1, date_debut, date_fin, type_1)
        soldes_2 = self._get_daily_balances(compte_id_2, date_debut, date_fin, type_2)

        # Trier les dates
        toutes_dates = sorted(set(soldes_1.keys()) | set(soldes_2.keys()))
        if not toutes_dates:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"

        # Obtenir les valeurs
        valeurs_1 = [soldes_1.get(dt, Decimal('0')) for dt in toutes_dates]
        valeurs_2 = [soldes_2.get(dt, Decimal('0')) for dt in toutes_dates]

        # Calculer les valeurs absolues pour l'échelle Y
        toutes_valeurs = valeurs_1 + valeurs_2
        if not toutes_valeurs:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"

        max_val = max(abs(float(v)) for v in toutes_valeurs)
        if max_val == 0:
            max_val = 1  # Éviter la division par zéro

        # --- Paramètres du graphique ---
        largeur_svg, hauteur_svg = 900, 500
        marge_gauche, marge_droite = 80, 40
        marge_haut, marge_bas = 40, 80
        largeur_graph = largeur_svg - marge_gauche - marge_droite
        hauteur_graph = hauteur_svg - marge_haut - marge_bas

        # Échelle pour les valeurs (axe Y)
        echelle_y = hauteur_graph / (2 * max_val)  # Pour couvrir -max à +max

        # Échelle pour les dates (axe X)
        nb_dates = len(toutes_dates)
        if nb_dates <= 1:
            largeur_barre = largeur_graph * 0.8
            espacement = 0
        else:
            largeur_barre = largeur_graph / nb_dates * 0.4  # 40% de la place pour la barre
            espacement = largeur_graph / nb_dates - largeur_barre

        svg_content = f'<svg width="{largeur_svg}" height="{hauteur_svg}" xmlns="http://www.w3.org/2000/svg">\n'

        # Ligne centrale (valeur 0 sur l'axe Y)
        y_zero = marge_haut + hauteur_graph / 2
        svg_content += f'<line x1="{marge_gauche}" y1="{y_zero}" x2="{marge_gauche + largeur_graph}" y2="{y_zero}" stroke="#000" stroke-dasharray="4" />\n'

        # Dessiner les barres pour chaque date
        for i, (dt, val_1, val_2) in enumerate(zip(toutes_dates, valeurs_1, valeurs_2)):
            # Position X centrale pour ce groupe de barres
            x_centre = marge_gauche + (i * (largeur_barre + espacement)) + (largeur_barre + espacement) / 2

            # Barre Compte 1
            hauteur_1 = abs(float(val_1)) * echelle_y
            if val_1 >= 0:
                y_1 = y_zero - hauteur_1
            else:
                y_1 = y_zero
                hauteur_1 = abs(hauteur_1) # Assure que la hauteur est positive
            svg_content += f'<rect x="{x_centre - largeur_barre}" y="{y_1}" width="{largeur_barre/2}" height="{hauteur_1}" fill="{couleur_1}" />\n'

            # Barre Compte 2
            hauteur_2 = abs(float(val_2)) * echelle_y
            if val_2 >= 0:
                y_2 = y_zero - hauteur_2
            else:
                y_2 = y_zero
                hauteur_2 = abs(hauteur_2)
            svg_content += f'<rect x="{x_centre - largeur_barre/2}" y="{y_2}" width="{largeur_barre/2}" height="{hauteur_2}" fill="{couleur_2}" />\n'

        # Ajouter les labels des dates sur l'axe X
        for i, dt in enumerate(toutes_dates):
            x_centre = marge_gauche + (i * (largeur_barre + espacement)) + (largeur_barre + espacement) / 2
            # Rotation pour les labels longs
            svg_content += f'<text x="{x_centre}" y="{marge_haut + hauteur_graph + 20}" text-anchor="middle" font-size="10" transform="rotate(45, {x_centre}, {marge_haut + hauteur_graph + 20})">{dt.strftime("%d.%m")}</text>\n'

        # Ajouter une légende simple
        svg_content += f'<rect x="{marge_gauche}" y="{marge_haut - 25}" width="15" height="10" fill="{couleur_1}" />\n'
        svg_content += f'<text x="{marge_gauche + 20}" y="{marge_haut - 15}" font-size="12">Compte 1 ({type_1})</text>\n'
        svg_content += f'<rect x="{marge_gauche + 150}" y="{marge_haut - 25}" width="15" height="10" fill="{couleur_2}" />\n'
        svg_content += f'<text x="{marge_gauche + 170}" y="{marge_haut - 15}" font-size="12">Compte 2 ({type_2})</text>\n'

        svg_content += '</svg>'
        return svg_content

    def compare_comptes_soldes_horizontales(self, compte_id_1: int, compte_id_2: int,
                               date_debut: date, date_fin: date,
                               type_1: str, type_2: str,
                               couleur_1_recette: str = "#0000FF", couleur_1_depense: str = "#FF0000",
                               couleur_2_recette: str = "#00FF00", couleur_2_depense: str = "#FF00FF") -> str:
        """
        Génère un graphique SVG comparant l'évolution des soldes de deux comptes.
        """


        # Récupérer les soldes quotidiens pour chaque compte et type
        soldes_1 = self._get_daily_balances(compte_id_1, date_debut, date_fin, type_1)
        soldes_2 = self._get_daily_balances(compte_id_2, date_debut, date_fin, type_2)

        # Trier les dates pour l'axe Y (axe des ordonnées)
        toutes_dates = sorted(set(soldes_1.keys()) | set(soldes_2.keys()))
        if not toutes_dates:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"

        # Déterminer les valeurs max pour l'échelle de l'axe X
        all_values = list(soldes_1.values()) + list(soldes_2.values())
        if not all_values:
             return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"
        max_val = max(abs(v) for v in all_values)
        if max_val == 0: max_val = 1 # Éviter la division par zéro

        # Dimensions du graphique
        largeur_svg, hauteur_svg = 800, 400
        marge_gauche, marge_droite = 50, 50
        marge_haut, marge_bas = 30, 30
        largeur_graph = largeur_svg - marge_gauche - marge_droite
        hauteur_graph = hauteur_svg - marge_haut - marge_bas

        # Echelle pour les valeurs (axe X)
        echelle_x = largeur_graph / (2 * max_val) # 2 * max_val pour couvrir -max à +max

        # Echelle pour les dates (axe Y)
        # On inverse l'axe Y : la date la plus ancienne (0) est en bas, la plus récente (len-1) en haut
        nb_dates = len(toutes_dates)
        if nb_dates <= 1:
            pas_y = 0
        else:
            pas_y = hauteur_graph / (nb_dates - 1) if nb_dates > 1 else hauteur_graph

        # Générer le SVG
        svg_content = f'<svg width="{largeur_svg}" height="{hauteur_svg}" xmlns="http://www.w3.org/2000/svg">\n'

        # Ligne centrale (valeur 0)
        x_zero = marge_gauche + largeur_graph / 2
        svg_content += f'<line x1="{x_zero}" y1="{marge_haut}" x2="{x_zero}" y2="{marge_haut + hauteur_graph}" stroke="#000" stroke-dasharray="4" />\n'

        # Dessiner les points pour chaque date
        for i, dt in enumerate(toutes_dates):
            y_pos = marge_haut + hauteur_graph - (i * pas_y) # Inverser l'axe Y

            # Valeurs pour les deux comptes à cette date
            val_1 = soldes_1.get(dt, Decimal('0'))
            val_2 = soldes_2.get(dt, Decimal('0'))

            # Calculer les positions X
            x_1 = marge_gauche + (largeur_graph / 2) + float(val_1) * echelle_x
            x_2 = marge_gauche + (largeur_graph / 2) + float(val_2) * echelle_x

            # Choisir la couleur en fonction du type
            color_1 = couleur_1_recette if type_1 == 'recette' else couleur_1_depense
            color_2 = couleur_2_recette if type_2 == 'recette' else couleur_2_depense

            # Dessiner les points
            svg_content += f'<circle cx="{x_1}" cy="{y_pos}" r="3" fill="{color_1}" />\n'
            svg_content += f'<circle cx="{x_2}" cy="{y_pos}" r="3" fill="{color_2}" />\n'

            # Optionnel : Lier les points des deux comptes pour la même date
            svg_content += f'<line x1="{x_1}" y1="{y_pos}" x2="{x_2}" y2="{y_pos}" stroke="#ccc" stroke-dasharray="2" />\n'

        # Ajouter les labels des dates sur l'axe Y
        for i, dt in enumerate(toutes_dates):
            y_pos = marge_haut + hauteur_graph - (i * pas_y)
            svg_content += f'<text x="{marge_gauche - 10}" y="{y_pos + 4}" text-anchor="end" font-size="10">{dt.strftime("%d.%m")}</text>\n'

        # Ajouter une légende simple
        svg_content += f'<rect x="{largeur_svg - 120}" y="{10}" width="10" height="10" fill="{color_1}" />\n'
        svg_content += f'<text x="{largeur_svg - 105}" y="20" font-size="12">Compte 1</text>\n'
        svg_content += f'<rect x="{largeur_svg - 120}" y="{25}" width="10" height="10" fill="{color_2}" />\n'
        svg_content += f'<text x="{largeur_svg - 105}" y="35" font-size="12">Compte 2</text>\n'

        svg_content += '</svg>'

        return svg_content

    def old_compare_comptes_soldes_barres(self, compte_id_1: int, compte_id_2: int,
                                    date_debut: date, date_fin: date,
                                    type_1: str, type_2: str,
                                    couleur_1: str = "#0000FF", couleur_2: str = "#00FF00") -> str:
        """
        Génère un graphique en BARRES SVG comparant l'évolution des soldes de deux comptes.
        Axe X horizontal : valeurs des soldes (compte 1 à gauche, compte 2 à droite, axe Y au centre)
        Axe Y vertical descendant : dates (sur le côté gauche)
        """
        from datetime import timedelta

        # Récupérer les soldes quotidiens pour chaque compte et type
        soldes_1 = self._get_daily_balances(compte_id_1, date_debut, date_fin, type_1)
        soldes_2 = self._get_daily_balances(compte_id_2, date_debut, date_fin, type_2)

        # Trier les dates
        toutes_dates = sorted(set(soldes_1.keys()) | set(soldes_2.keys()))
        if not toutes_dates:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"

        # Obtenir les valeurs
        valeurs_1 = [soldes_1.get(dt, Decimal('0')) for dt in toutes_dates]
        valeurs_2 = [soldes_2.get(dt, Decimal('0')) for dt in toutes_dates]

        # Calculer les valeurs absolues pour l'échelle X
        toutes_valeurs = valeurs_1 + valeurs_2
        if not toutes_valeurs:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"

        max_val = max(abs(float(v)) for v in toutes_valeurs)
        if max_val == 0:
            max_val = 1  # Éviter la division par zéro

        # --- Paramètres du graphique ---
        largeur_svg, hauteur_svg = 900, 500
        marge_gauche, marge_droite = 120, 40  # Augmenter la marge gauche pour les labels de dates
        marge_haut, marge_bas = 40, 40
        largeur_graph = largeur_svg - marge_gauche - marge_droite
        hauteur_graph = hauteur_svg - marge_haut - marge_bas

        # Échelle pour les valeurs (axe X)
        echelle_x = largeur_graph / (2 * max_val)  # Pour couvrir -max à +max

        # Échelle pour les dates (axe Y)
        nb_dates = len(toutes_dates)
        if nb_dates <= 1:
            hauteur_barre = hauteur_graph * 0.8
            espacement = 0
        else:
            hauteur_barre = hauteur_graph / nb_dates * 0.8  # 80% de la place pour la barre
            espacement = hauteur_graph / nb_dates - hauteur_barre

        svg_content = f'<svg width="{largeur_svg}" height="{hauteur_svg}" xmlns="http://www.w3.org/2000/svg">\n'

        # Ligne centrale (valeur 0 sur l'axe X)
        x_zero = marge_gauche + largeur_graph / 2
        svg_content += f'<line x1="{x_zero}" y1="{marge_haut}" x2="{x_zero}" y2="{marge_haut + hauteur_graph}" stroke="#000" stroke-dasharray="4" />\n'

        # Dessiner les barres pour chaque date
        for i, (dt, val_1, val_2) in enumerate(zip(toutes_dates, valeurs_1, valeurs_2)):
            # Position Y centrale pour ce groupe de barres
            y_centre = marge_haut + (i * (hauteur_barre + espacement)) + (hauteur_barre + espacement) / 2

            # Barre Compte 1 (à gauche de l'axe Y)
            largeur_1 = abs(float(val_1)) * echelle_x
            if val_1 >= 0:
                x_1 = x_zero # Commence à l'axe Y
                largeur_1 = -largeur_1 # Barre vers la gauche
            else:
                x_1 = x_zero + float(val_1) * echelle_x # Commence à la position négative
            svg_content += f'<rect x="{x_1 + largeur_1}" y="{y_centre - hauteur_barre/2}" width="{abs(largeur_1)}" height="{hauteur_barre}" fill="{couleur_1}" />\n'

            # Barre Compte 2 (à droite de l'axe Y)
            largeur_2 = abs(float(val_2)) * echelle_x
            if val_2 >= 0:
                x_2 = x_zero # Commence à l'axe Y
            else:
                x_2 = x_zero + float(val_2) * echelle_x # Commence à la position négative
                largeur_2 = -largeur_2 # Barre vers la gauche
            svg_content += f'<rect x="{x_2}" y="{y_centre - hauteur_barre/2}" width="{abs(largeur_2)}" height="{hauteur_barre}" fill="{couleur_2}" />\n'

        # Ajouter les labels des dates sur l'axe Y (à gauche)
        for i, dt in enumerate(toutes_dates):
            y_centre = marge_haut + (i * (hauteur_barre + espacement)) + (hauteur_barre + espacement) / 2
            svg_content += f'<text x="{marge_gauche - 10}" y="{y_centre}" text-anchor="end" dominant-baseline="middle" font-size="10">{dt.strftime("%d.%m")}</text>\n'

        # Ajouter une légende simple
        svg_content += f'<rect x="{marge_gauche}" y="{marge_haut - 25}" width="15" height="10" fill="{couleur_1}" />\n'
        svg_content += f'<text x="{marge_gauche + 20}" y="{marge_haut - 15}" font-size="12">Compte 1 ({type_1})</text>\n'
        svg_content += f'<rect x="{marge_gauche + 150}" y="{marge_haut - 25}" width="15" height="10" fill="{couleur_2}" />\n'
        svg_content += f'<text x="{marge_gauche + 170}" y="{marge_haut - 15}" font-size="12">Compte 2 ({type_2})</text>\n'

        svg_content += '</svg>'
        return svg_content

    def compare_comptes_soldes_barres(self, compte_id_1: int, compte_id_2: int,
                                date_debut: date, date_fin: date,
                                type_1: str, type_2: str,
                                couleur_1: str = "#0000FF", couleur_2: str = "#00FF00") -> str:
        """
        Génère un graphique en BARRES SVG comparant l'évolution des soldes de deux comptes.
        Axes épais, quadrillage fin, et graduations automatiques.
        """
        from datetime import timedelta

        # Récupérer les soldes quotidiens pour chaque compte et type
        soldes_1 = self._get_daily_balances(compte_id_1, date_debut, date_fin, type_1)
        soldes_2 = self._get_daily_balances(compte_id_2, date_debut, date_fin, type_2)

        # Trier les dates
        toutes_dates = sorted(set(soldes_1.keys()) | set(soldes_2.keys()))
        if not toutes_dates:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"

        # Obtenir les valeurs
        valeurs_1 = [soldes_1.get(dt, Decimal('0')) for dt in toutes_dates]
        valeurs_2 = [soldes_2.get(dt, Decimal('0')) for dt in toutes_dates]

        # Calculer les valeurs absolues pour l'échelle X
        toutes_valeurs = valeurs_1 + valeurs_2
        if not toutes_valeurs:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée pour les dates sélectionnées.</text></svg>"

        max_val = max(abs(float(v)) for v in toutes_valeurs)
        if max_val == 0:
            max_val = 1  # Éviter la division par zéro

        # --- Paramètres du graphique ---
        largeur_svg, hauteur_svg = 900, 500
        marge_gauche, marge_droite = 120, 40
        marge_haut, marge_bas = 40, 40
        largeur_graph = largeur_svg - marge_gauche - marge_droite
        hauteur_graph = hauteur_svg - marge_haut - marge_bas

        # Échelle pour les valeurs (axe X)
        echelle_x = largeur_graph / (2 * max_val)

        # Échelle pour les dates (axe Y)
        nb_dates = len(toutes_dates)
        if nb_dates <= 1:
            hauteur_barre = hauteur_graph * 0.8
            espacement = 0
        else:
            hauteur_barre = hauteur_graph / nb_dates * 0.8
            espacement = hauteur_graph / nb_dates - hauteur_barre

        svg_content = f'<svg width="{largeur_svg}" height="{hauteur_svg}" xmlns="http://www.w3.org/2000/svg">\n'

        # === AXES PRINCIPAUX (plus épais) ===
        x_zero = marge_gauche + largeur_graph / 2
        y_haut = marge_haut
        y_bas = marge_haut + hauteur_graph
        # Axe Y (vertical central)
        svg_content += f'<line x1="{x_zero}" y1="{y_haut}" x2="{x_zero}" y2="{y_bas}" stroke="#000" stroke-width="2" />\n'
        # Axe X (horizontal du haut)
        svg_content += f'<line x1="{marge_gauche}" y1="{y_haut}" x2="{marge_gauche + largeur_graph}" y2="{y_haut}" stroke="#000" stroke-width="2" />\n'
        # Axe X (horizontal du bas)
        svg_content += f'<line x1="{marge_gauche}" y1="{y_bas}" x2="{marge_gauche + largeur_graph}" y2="{y_bas}" stroke="#000" stroke-width="2" />\n'

        # === QUADRILLAGE FIN ===
        svg_content += '<g stroke="#ddd" stroke-width="0.5">\n'
        # Lignes horizontales (une par date)
        for i in range(nb_dates):
            y_pos = marge_haut + (i * (hauteur_barre + espacement)) + (hauteur_barre + espacement) / 2
            svg_content += f'  <line x1="{marge_gauche}" y1="{y_pos}" x2="{marge_gauche + largeur_graph}" y2="{y_pos}" />\n'
        svg_content += '</g>\n'

        # === GRADUATIONS SUR L'AXE X (valeurs) ===
        def trouver_pas_gravitation(max_val):
            """Détermine un pas de graduation lisible."""
            if max_val >= 5000:
                return 1000
            elif max_val >= 1000:
                return 500
            elif max_val >= 500:
                return 100
            elif max_val >= 100:
                return 50
            elif max_val >= 50:
                return 25
            elif max_val >= 20:
                return 10
            elif max_val >= 10:
                return 5
            else:
                return 1

        pas = trouver_pas_gravitation(max_val)
        # Générer les marques et labels
        svg_content += '<g font-size="10" fill="#000">\n'
        # Côté positif (droite de l'axe Y)
        current_val = pas
        while current_val <= max_val + pas:
            x_pos = x_zero + (current_val * echelle_x)
            if x_pos <= marge_gauche + largeur_graph:
                svg_content += f'  <line x1="{x_pos}" y1="{y_haut}" x2="{x_pos}" y2="{y_bas}" stroke="#ccc" stroke-width="0.8" />\n'
                svg_content += f'  <text x="{x_pos}" y="{y_bas + 15}" text-anchor="middle">{int(current_val)}</text>\n'
            current_val += pas

        # Côté négatif (gauche de l'axe Y)
        current_val = pas
        while current_val <= max_val + pas:
            x_pos = x_zero - (current_val * echelle_x)
            if x_pos >= marge_gauche:
                svg_content += f'  <line x1="{x_pos}" y1="{y_haut}" x2="{x_pos}" y2="{y_bas}" stroke="#ccc" stroke-width="0.8" />\n'
                svg_content += f'  <text x="{x_pos}" y="{y_bas + 15}" text-anchor="middle">-{int(current_val)}</text>\n'
            current_val += pas
        svg_content += '</g>\n'

        # === BARRES DE DONNÉES ===
        for i, (dt, val_1, val_2) in enumerate(zip(toutes_dates, valeurs_1, valeurs_2)):
            y_centre = marge_haut + (i * (hauteur_barre + espacement)) + (hauteur_barre + espacement) / 2

            # Barre Compte 1 (gauche)
            largeur_1 = abs(float(val_1)) * echelle_x
            if val_1 >= 0:
                x_1 = x_zero
                largeur_1 = -largeur_1
            else:
                x_1 = x_zero + float(val_1) * echelle_x
            svg_content += f'<rect x="{x_1 + largeur_1}" y="{y_centre - hauteur_barre/2}" width="{abs(largeur_1)}" height="{hauteur_barre}" fill="{couleur_1}" />\n'

            # Barre Compte 2 (droite)
            largeur_2 = abs(float(val_2)) * echelle_x
            if val_2 >= 0:
                x_2 = x_zero
            else:
                x_2 = x_zero + float(val_2) * echelle_x
                largeur_2 = -largeur_2
            svg_content += f'<rect x="{x_2}" y="{y_centre - hauteur_barre/2}" width="{abs(largeur_2)}" height="{hauteur_barre}" fill="{couleur_2}" />\n'

        # === LABELS DES DATES (Axe Y à gauche) ===
        for i, dt in enumerate(toutes_dates):
            y_centre = marge_haut + (i * (hauteur_barre + espacement)) + (hauteur_barre + espacement) / 2
            svg_content += f'<text x="{marge_gauche - 10}" y="{y_centre}" text-anchor="end" dominant-baseline="middle" font-size="10">{dt.strftime("%d.%m")}</text>\n'

        # === LÉGENDE ===
        svg_content += f'<rect x="{marge_gauche}" y="{marge_haut - 25}" width="15" height="10" fill="{couleur_1}" />\n'
        svg_content += f'<text x="{marge_gauche + 20}" y="{marge_haut - 15}" font-size="12">Compte 1 ({type_1})</text>\n'
        svg_content += f'<rect x="{marge_gauche + 150}" y="{marge_haut - 25}" width="15" height="10" fill="{couleur_2}" />\n'
        svg_content += f'<text x="{marge_gauche + 170}" y="{marge_haut - 15}" font-size="12">Compte 2 ({type_2})</text>\n'

        svg_content += '</svg>'
        return svg_content

    def get_top_comptes_echanges(self, compte_principal_id: int, user_id: int,
                           date_debut: str, date_fin: str,
                           direction: str = 'tous',
                           limite: int = 50) -> List[Dict]:
        """
        Récupère les comptes avec lesquels un compte a le plus échangé de l'argent.

        Args:
            compte_principal_id (int): ID du compte principal source.
            user_id (int): ID de l'utilisateur (pour vérification).
            date_debut (str): Date de début (format 'YYYY-MM-DD').
            date_fin (str): Date de fin (format 'YYYY-MM-DD').
            direction (str): 'envoye', 'recu', ou 'tous'.
            limite (int): Nombre maximum de comptes à retourner.

        Returns:
            List[Dict]: Liste triée de dictionnaires avec clés 'compte_id', 'nom_compte', 'total_montant', 'direction'
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le compte appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                    (compte_principal_id, user_id)
                )
                if not cursor.fetchone():
                    return []

                # Construire la requête selon la direction
                if direction == 'envoye':
                    # Transferts sortants vers d'autres comptes principaux
                    query = """
                    SELECT
                        cp_dest.id as compte_id,
                        cp_dest.nom_compte,
                        SUM(t.montant) as total_montant,
                        'envoye' as direction
                    FROM transactions t
                    JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                    WHERE t.compte_principal_id = %s
                    AND t.type_transaction = 'transfert_sortant'
                    AND t.date_transaction BETWEEN %s AND %s
                    GROUP BY cp_dest.id, cp_dest.nom_compte
                    ORDER BY total_montant DESC
                    LIMIT %s
                    """
                elif direction == 'recu':
                    # Transferts entrants depuis d'autres comptes principaux
                    query = """
                    SELECT
                        cp_src.id as compte_id,
                        cp_src.nom_compte,
                        SUM(t.montant) as total_montant,
                        'recu' as direction
                    FROM transactions t
                    JOIN comptes_principaux cp_src ON t.compte_source_id = cp_src.id
                    WHERE t.compte_principal_id = %s
                    AND t.type_transaction = 'transfert_entrant'
                    AND t.date_transaction BETWEEN %s AND %s
                    GROUP BY cp_src.id, cp_src.nom_compte
                    ORDER BY total_montant DESC
                    LIMIT %s
                    """
                else: # 'tous'
                    # Combiner les deux directions
                    query = """
                    SELECT
                        compte_id,
                        nom_compte,
                        SUM(total_montant) as total_montant,
                        'tous' as direction
                    FROM (
                        -- Transferts ENVOYES
                        SELECT
                            cp_dest.id as compte_id,
                            cp_dest.nom_compte,
                            SUM(t.montant) as total_montant
                        FROM transactions t
                        JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                        WHERE t.compte_principal_id = %s
                        AND t.type_transaction = 'transfert_sortant'
                        AND t.date_transaction BETWEEN %s AND %s
                        GROUP BY cp_dest.id, cp_dest.nom_compte

                        UNION ALL

                        -- Transferts RECUS
                        SELECT
                            cp_src.id as compte_id,
                            cp_src.nom_compte,
                            SUM(t.montant) as total_montant
                        FROM transactions t
                        JOIN comptes_principaux cp_src ON t.compte_source_id = cp_src.id
                        WHERE t.compte_principal_id = %s
                        AND t.type_transaction = 'transfert_entrant'
                        AND t.date_transaction BETWEEN %s AND %s
                        GROUP BY cp_src.id, cp_src.nom_compte
                    ) AS combined
                    GROUP BY compte_id, nom_compte
                    ORDER BY total_montant DESC
                    LIMIT %s
                    """
                    # Pour 'tous', on a 3 fois les paramètres
                    params = [compte_principal_id, date_debut, date_fin,
                            compte_principal_id, date_debut, date_fin,
                            limite]
                    logger.info(f'models 4459 voici les params : {params}')
                if direction in ['envoye', 'recu']:
                    params = [compte_principal_id, date_debut, date_fin, limite]

                cursor.execute(query, params)
                logger.debug(f"Requête get_top_comptes_echanges exécutée avec params: {params}")
                resultats = cursor.fetchall()
                logger.debug(f"{len(resultats)} Résultats obtenus: {resultats}")
                return [dict(row) for row in resultats]

        except Exception as e:
            logger.error(f"Erreur dans get_top_comptes_echanges: {e}")
            return []

    def generer_graphique_top_comptes_echanges(self, donnees: List[Dict],
                                            couleur_barre: str = "#4e79a7") -> str:
        """
        Génère un graphique en barres horizontales SVG pour les top comptes d'échange.
        La barre la plus longue (montant le plus élevé) est en haut.
        """
        if not donnees:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée disponible.</text></svg>"

        # Trouver le montant maximum pour l'échelle
        max_montant = max(row['total_montant'] for row in donnees)
        if max_montant == 0:
            max_montant = 1

        # Paramètres du graphique
        largeur_svg = 800
        hauteur_svg = max(400, len(donnees) * 40)  # Hauteur dynamique
        marge_gauche = 250  # Pour laisser de la place au nom des comptes
        marge_droite = 40
        marge_haut = 30
        marge_bas = 30
        largeur_graph = largeur_svg - marge_gauche - marge_droite
        hauteur_graph = hauteur_svg - marge_haut - marge_bas

        # Hauteur d'une barre
        hauteur_barre = hauteur_graph / len(donnees) * 0.8
        espacement = hauteur_graph / len(donnees) * 0.2

        svg_content = f'<svg width="{largeur_svg}" height="{hauteur_svg}" xmlns="http://www.w3.org/2000/svg">\n'

        # Dessiner les barres
        for i, row in enumerate(donnees):
            y_pos = marge_haut + i * (hauteur_barre + espacement)
            largeur = (row['total_montant'] / max_montant) * largeur_graph

            # Barre
            svg_content += f'<rect x="{marge_gauche}" y="{y_pos}" width="{largeur}" height="{hauteur_barre}" fill="{couleur_barre}" />\n'
            # Label du montant (à droite de la barre)
            svg_content += f'<text x="{marge_gauche + largeur + 10}" y="{y_pos + hauteur_barre/2 + 4}" font-size="12" dominant-baseline="middle">{row["total_montant"]:,.2f}</text>\n'
            # Label du nom du compte (à gauche de la barre)
            svg_content += f'<text x="{marge_gauche - 10}" y="{y_pos + hauteur_barre/2 + 4}" font-size="12" dominant-baseline="middle" text-anchor="end">{row["nom_compte"]}</text>\n'

        svg_content += '</svg>'
        return svg_content

    def _trouver_pas_gravitation(self, max_val: float) -> int:
        """Détermine un pas de graduation lisible pour l'axe Y."""
        if max_val >= 5000:
            return 1000
        elif max_val >= 1000:
            return 500
        elif max_val >= 500:
            return 100
        elif max_val >= 100:
            return 50
        elif max_val >= 50:
            return 25
        elif max_val >= 20:
            return 10
        elif max_val >= 10:
            return 5
        else:
            return 1

    def get_transactions_avec_comptes(self, compte_principal_id: int, user_id: int,
                                    comptes_cibles_ids: List[int],
                                    date_debut: str, date_fin: str) -> List[Dict]:
        """
        Récupère la liste des transactions entre un compte principal et une liste de comptes cibles.
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le compte source appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                    (compte_principal_id, user_id)
                )
                if not cursor.fetchone():
                    return []

                if not comptes_cibles_ids:
                    return []

                # Préparer la liste des IDs pour la requête
                placeholders = ','.join(['%s'] * len(comptes_cibles_ids))
                params = [compte_principal_id, date_debut, date_fin] + comptes_cibles_ids

                # Requête pour récupérer les transactions sortantes ET entrantes
                query = f"""
                (
                    -- Transferts SORTANTS vers les comptes cibles
                    SELECT
                        t.date_transaction,
                        t.montant,
                        cp_dest.id as compte_cible_id,
                        cp_dest.nom_compte as nom_compte_cible,
                        'sortant' as direction
                    FROM transactions t
                    JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                    WHERE t.compte_principal_id = %s
                      AND t.type_transaction = 'transfert_sortant'
                      AND t.date_transaction BETWEEN %s AND %s
                      AND cp_dest.id IN ({placeholders})
                )
                UNION ALL
                (
                    -- Transferts ENTRANTS depuis les comptes cibles
                    SELECT
                        t.date_transaction,
                        t.montant,
                        cp_src.id as compte_cible_id,
                        cp_src.nom_compte as nom_compte_cible,
                        'entrant' as direction
                    FROM transactions t
                    JOIN comptes_principaux cp_src ON t.compte_source_id = cp_src.id
                    WHERE t.compte_principal_id = %s
                      AND t.type_transaction = 'transfert_entrant'
                      AND t.date_transaction BETWEEN %s AND %s
                      AND cp_src.id IN ({placeholders})
                )
                ORDER BY date_transaction ASC
                """
                # Pour UNION ALL, on a besoin de répéter les paramètres
                params = [compte_principal_id, date_debut, date_fin] + comptes_cibles_ids + [compte_principal_id, date_debut, date_fin] + comptes_cibles_ids

                cursor.execute(query, params)
                resultats = cursor.fetchall()
                return [dict(row) for row in resultats]

        except Exception as e:
            logger.error(f"Erreur dans get_transactions_avec_comptes: {e}")
            return []

    def _structurer_donnees_pour_graphique(self, donnees_brutes: List[Dict], cumuler: bool = False) -> Dict:
        """
        Transforme une liste plate de transactions en une structure utilisable pour le graphique.
        Si cumuler=True, toutes les transactions sont fusionnées en une seule série.
        Si cumuler=False, les transactions sont regroupées par compte cible.
        """
        if not donnees_brutes:
            return {}

        # Trier par date
        donnees_triees = sorted(donnees_brutes, key=lambda x: x['date_transaction'])
        dates_uniques = sorted(set(d['date_transaction'] for d in donnees_triees))

        if cumuler:
            # Mode cumulé : une seule série
            serie_cumulee = []
            for dt in dates_uniques:
                total_jour = sum(d['montant'] for d in donnees_triees if d['date_transaction'] == dt)
                serie_cumulee.append(total_jour)
            return {
                'dates': dates_uniques,
                'series': {
                    'Tous les comptes': serie_cumulee
                }
            }
        else:
            # Mode séparé : une série par compte cible
            series = {}
            for d in donnees_triees:
                nom_compte = d['nom_compte_cible']
                if nom_compte not in series:
                    series[nom_compte] = [0] * len(dates_uniques)
                # Trouver l'index de la date
                idx = dates_uniques.index(d['date_transaction'])
                series[nom_compte][idx] += d['montant']

            return {
                'dates': dates_uniques,
                'series': series
            }

    def generer_graphique_echanges_temporel_lignes(self, donnees_structurees: Dict,
                                                  couleurs: List[str] = None) -> str:
        """
        Génère un graphique en lignes SVG avec axes Y améliorés.
        """
        if not donnees_structurees or not donnees_structurees['series']:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée disponible.</text></svg>"

        dates = donnees_structurees['dates']
        series = donnees_structurees['series']
        n_series = len(series)

        # Gérer les couleurs
        default_colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]
        if couleurs is None or len(couleurs) < n_series:
            couleurs = (couleurs or []) + default_colors[len(couleurs or []):]
        couleurs = couleurs[:n_series]

        # Paramètres du graphique
        largeur_svg = 800
        hauteur_svg = 400
        marge_gauche = 60
        marge_droite = 40
        marge_haut = 40
        marge_bas = 60
        largeur_graph = largeur_svg - marge_gauche - marge_droite
        hauteur_graph = hauteur_svg - marge_haut - marge_bas

        # Trouver le max global pour l'échelle Y
        max_montant = max(max(vals) for vals in series.values()) if series else 1
        if max_montant == 0:
            max_montant = 1

        svg = f'<svg width="{largeur_svg}" height="{hauteur_svg}" xmlns="http://www.w3.org/2000/svg">\n'

        # === AXES PRINCIPAUX ===
        svg += f'<line x1="{marge_gauche}" y1="{marge_haut}" x2="{marge_gauche}" y2="{marge_haut + hauteur_graph}" stroke="black" stroke-width="2" />\n'
        svg += f'<line x1="{marge_gauche}" y1="{marge_haut + hauteur_graph}" x2="{largeur_svg - marge_droite}" y2="{marge_haut + hauteur_graph}" stroke="black" stroke-width="2" />\n'

        # === QUADRILLAGE ET GRADUATIONS (Y) ===
        pas = self._trouver_pas_gravitation(max_montant)
        current_val = pas
        while current_val <= max_montant + pas:
            y_pos = marge_haut + hauteur_graph - (current_val / max_montant) * hauteur_graph
            if y_pos >= marge_haut:
                # Ligne de quadrillage
                svg += f'<line x1="{marge_gauche}" y1="{y_pos}" x2="{largeur_svg - marge_droite}" y2="{y_pos}" stroke="#ddd" stroke-width="0.5" />\n'
                # Label de graduation
                svg += f'<text x="{marge_gauche - 10}" y="{y_pos + 4}" text-anchor="end" font-size="10">{int(current_val)}</text>\n'
            current_val += pas

        # === TRACER LES SÉRIES ===
        for idx, (nom_serie, valeurs) in enumerate(series.items()):
            couleur = couleurs[idx]
            points = []
            for i, montant in enumerate(valeurs):
                x = marge_gauche + (i / (len(dates) - 1 if len(dates) > 1 else 1)) * largeur_graph
                y = marge_haut + hauteur_graph - (montant / max_montant) * hauteur_graph
                points.append(f"{x},{y}")
                # On peut dessiner des points ici aussi
                svg += f'<circle cx="{x}" cy="{y}" r="2" fill="{couleur}" />\n'

            if len(points) > 1:
                svg += f'<polyline points="{" ".join(points)}" fill="none" stroke="{couleur}" stroke-width="2" />\n'

        # === LABELS DES DATES (X) ===
        for i, dt in enumerate(dates):
            if i % max(1, len(dates)//10) == 0:
                x = marge_gauche + (i / (len(dates) - 1 if len(dates) > 1 else 1)) * largeur_graph
                svg += f'<text x="{x}" y="{marge_haut + hauteur_graph + 20}" text-anchor="middle" font-size="10">{dt.strftime("%d.%m")}</text>\n'

        # === LÉGENDE ===
        if n_series > 1 or list(series.keys())[0] != 'Tous les comptes':
            for idx, nom_serie in enumerate(series.keys()):
                y_leg = marge_haut + idx * 20
                svg += f'<rect x="{largeur_svg - 120}" y="{y_leg}" width="15" height="10" fill="{couleurs[idx]}" />\n'
                # Tronquer le nom de la série si trop long
                nom_affiche = nom_serie[:15] + "..." if len(nom_serie) > 15 else nom_serie
                svg += f'<text x="{largeur_svg - 100}" y="{y_leg + 8}" font-size="12">{nom_affiche}</text>\n'

        svg += '</svg>'
        return svg

    def generer_graphique_echanges_temporel_barres(self, donnees_structurees: Dict,
                                                  couleurs: List[str] = None) -> str:
        """
        Génère un graphique en barres SVG avec axes Y améliorés.
        """
        if not donnees_structurees or not donnees_structurees['series']:
            return "<svg width='800' height='400'><text x='10' y='20'>Aucune donnée disponible.</text></svg>"

        dates = donnees_structurees['dates']
        series = donnees_structurees['series']
        n_series = len(series)
        n_dates = len(dates)

        default_colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"]
        if couleurs is None or len(couleurs) < n_series:
            couleurs = (couleurs or []) + default_colors[len(couleurs or []):]
        couleurs = couleurs[:n_series]

        largeur_svg = 800
        hauteur_svg = 400
        marge_gauche = 60
        marge_droite = 40
        marge_haut = 40
        marge_bas = 60
        largeur_graph = largeur_svg - marge_gauche - marge_droite
        hauteur_graph = hauteur_svg - marge_haut - marge_bas

        max_montant = max(max(vals) for vals in series.values()) if series else 1
        if max_montant == 0:
            max_montant = 1

        svg = f'<svg width="{largeur_svg}" height="{hauteur_svg}" xmlns="http://www.w3.org/2000/svg">\n'

        # === AXES PRINCIPAUX ===
        svg += f'<line x1="{marge_gauche}" y1="{marge_haut}" x2="{marge_gauche}" y2="{marge_haut + hauteur_graph}" stroke="black" stroke-width="2" />\n'
        svg += f'<line x1="{marge_gauche}" y1="{marge_haut + hauteur_graph}" x2="{largeur_svg - marge_droite}" y2="{marge_haut + hauteur_graph}" stroke="black" stroke-width="2" />\n'

        # === QUADRILLAGE ET GRADUATIONS (Y) ===
        pas = self._trouver_pas_gravitation(max_montant)
        current_val = pas
        while current_val <= max_montant + pas:
            y_pos = marge_haut + hauteur_graph - (current_val / max_montant) * hauteur_graph
            if y_pos >= marge_haut:
                svg += f'<line x1="{marge_gauche}" y1="{y_pos}" x2="{largeur_svg - marge_droite}" y2="{y_pos}" stroke="#ddd" stroke-width="0.5" />\n'
                svg += f'<text x="{marge_gauche - 10}" y="{y_pos + 4}" text-anchor="end" font-size="10">{int(current_val)}</text>\n'
            current_val += pas

        # === DESSINER LES BARRES (Groupées par date) ===
        if n_dates <= 1:
            largeur_groupe = largeur_graph * 0.5
            espacement = 0
        else:
            largeur_groupe = largeur_graph / n_dates * 0.9
            espacement = largeur_graph / n_dates - largeur_groupe

        for i, dt in enumerate(dates):
            x_groupe = marge_gauche + i * (largeur_groupe + espacement)
            # Largeur d'une barre unitaire dans le groupe
            largeur_barre_unitaire = largeur_groupe / n_series if n_series > 0 else largeur_groupe

            for j, (nom_serie, valeurs) in enumerate(series.items()):
                montant = valeurs[i] if i < len(valeurs) else 0 # Protection si la série est plus courte
                hauteur = (montant / max_montant) * hauteur_graph
                y = marge_haut + hauteur_graph - hauteur
                x = x_groupe + j * largeur_barre_unitaire

                svg += f'<rect x="{x}" y="{y}" width="{largeur_barre_unitaire}" height="{hauteur}" fill="{couleurs[j]}" />\n'

        # === LABELS DES DATES (X) ===
        for i, dt in enumerate(dates):
            if i % max(1, n_dates//10) == 0:
                x = marge_gauche + (i / (n_dates - 1 if n_dates > 1 else 1)) * largeur_graph
                svg += f'<text x="{x}" y="{marge_haut + hauteur_graph + 20}" text-anchor="middle" font-size="10">{dt.strftime("%d.%m")}</text>\n'

        # === LÉGENDE ===
        if n_series > 1 or list(series.keys())[0] != 'Tous les comptes':
            for idx, nom_serie in enumerate(series.keys()):
                y_leg = marge_haut + idx * 20
                svg += f'<rect x="{largeur_svg - 120}" y="{y_leg}" width="15" height="10" fill="{couleurs[idx]}" />\n'
                nom_affiche = nom_serie[:15] + "..." if len(nom_serie) > 15 else nom_serie
                svg += f'<text x="{largeur_svg - 100}" y="{y_leg + 8}" font-size="12">{nom_affiche}</text>\n'

        svg += '</svg>'
        return svg

    def _get_solde_avant_periode(self, compte_id: int, user_id: int, debut_periode: date) -> Decimal:
        """
        Retourne le solde juste avant le début de la période, pour un compte principal.
        Cela correspond au solde_apres de la dernière transaction avant cette date,
        ou au solde_initial du compte si aucune transaction n'existe avant.
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le compte appartient à l'utilisateur
                cursor.execute(
                    "SELECT id, solde_initial FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s",
                    (compte_id, user_id)
                )
                if not cursor.fetchone():
                    logger.warning(f"Tentative d'accès non autorisé ou compte inexistant: compte={compte_id}, user={user_id}")
                    return Decimal('0')

                # Récupérer la dernière transaction avant la date de début de la période
                cursor.execute("""
                    SELECT solde_apres
                    FROM transactions
                    WHERE compte_principal_id = %s AND date_transaction < %s
                    ORDER BY date_transaction DESC, id DESC
                    LIMIT 1
                """, (compte_id, debut_periode))
                result = cursor.fetchone()

                if result and result['solde_apres'] is not None:
                    # Retourner le solde après la dernière transaction avant la période
                    return Decimal(str(result['solde_apres']))
                else:
                    # Aucune transaction avant la période, retourner le solde initial du compte
                    cursor.execute(
                        "SELECT solde_initial FROM comptes_principaux WHERE id = %s",
                        (compte_id,)
                    )
                    initial_result = cursor.fetchone()
                    if initial_result and initial_result['solde_initial'] is not None:
                        return Decimal(str(initial_result['solde_initial']))
                    else:
                        # Si le solde_initial n'est pas non plus défini, retourner 0
                        return Decimal('0')
        except Exception as e:
            logger.error(f"Erreur dans _get_solde_avant_periode (compte {compte_id}, date {debut_periode}): {e}")
            return Decimal('0')

class CategorieTransaction:
    """Classe pour gérer les catégories de transactions"""

    def __init__(self, db):
        self.db = db

    def get_categories_utilisateur(self, user_id: int, type_categorie: str = None) -> List[Dict]:
        """Récupère les catégories de transactions pour un utilisateur donné"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT id, nom, description, couleur, icone, type_categorie, budget_mensuel
                    FROM categories_transactions
                    WHERE utilisateur_id = %s AND actif = TRUE
                """
                params = [user_id]

                if type_categorie:
                    query += " AND type_categorie = %s"
                    params.append(type_categorie)

                query += " ORDER BY type_categorie, nom ASC"

                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération catégories: {e}")
            return []

    def creer_categorie(self, user_id: int, nom: str, type_categorie: str = "Dépense",
                        description: str = '', couleur: str = None, icone: str = None, budget_mensuel: float = 0.0) -> Tuple[bool, str]:
        """Crée une nouvelle catégorie de transaction pour un utilisateur"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier si la catégorie existe déjà
                cursor.execute("""
                    SELECT id FROM categories_transactions
                    WHERE utilisateur_id = %s AND nom = %s AND type_categorie = %s
                """, (user_id, nom, type_categorie))

                if cursor.fetchone():
                    return False, "Cette catégorie existe déjà"

                # Couleur par défaut si non fournie
                if not couleur:
                    couleur = self._generer_couleur_aleatoire()

                cursor.execute("""
                    INSERT INTO categories_transactions
                    (utilisateur_id, nom, description, type_categorie, couleur, icone, budget_mensuel)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (user_id, nom, description, type_categorie, couleur, icone, budget_mensuel))

                return True, "Catégorie créée avec succès"
        except Exception as e:
            logger.error(f"Erreur création catégorie: {e}")
            return False, f"Erreur: {str(e)}"

    def modifier_categorie(self, categorie_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        """Met à jour une catégorie de transaction existante"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que la catégorie appartient à l'utilisateur
                cursor.execute("""
                    SELECT id FROM categories_transactions
                    WHERE id = %s AND utilisateur_id = %s
                """, (categorie_id, user_id))

                if not cursor.fetchone():
                    return False, "Catégorie non trouvée ou non autorisée"

                # Construire la requête dynamiquement
                champs = []
                valeurs = []
                for champ, valeur in kwargs.items():
                    if valeur is not None:
                        champs.append(f"{champ} = %s")
                        valeurs.append(valeur)

                if not champs:
                    return False, "Aucune modification spécifiée"

                valeurs.extend([categorie_id, user_id])
                query = f"""
                    UPDATE categories_transactions
                    SET {', '.join(champs)}
                    WHERE id = %s AND utilisateur_id = %s
                """

                cursor.execute(query, valeurs)
                return True, "Catégorie modifiée avec succès"
        except Exception as e:
            logger.error(f"Erreur mise à jour catégorie: {e}")
            return False, f"Erreur: {str(e)}"

    #def get_categorie_complementaire(self, categorie_id: int, user_id: int) -> Optional[Dict]:
    #    """Récupère la catégorie complémentaire associée à une catégorie donnée"""
    #    try:
    #        with self.db.get_cursor() as cursor:
    #            cursor.execute("""
    #                SELECT ct2.id, ct2.nom, ct2.description, ct2.couleur, ct2.icone, ct2.type_categorie, ct2.budget_mensuel
    #                FROM categories_transactions ct1
    #                JOIN categories_transactions ct2 ON ct1.categorie_complementaire_id = ct2.id
    #                WHERE ct1.id = %s AND ct1.utilisateur_id = %s AND ct2.actif = TRUE
    #            """, (categorie_id, user_id))
    #            return cursor.fetchone()
    #    except Exception as e:
    #        logger.error(f"Erreur récupération catégorie complémentaire: {e}")
    #        return None

    def supprimer_categorie(self, categorie_id: int, user_id: int) -> Tuple[bool, str]:
        """Supprime une catégorie de transaction (soft delete)"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier s'il y a des transactions utilisant cette catégorie
                cursor.execute("""
                    SELECT COUNT(*) as count
                    FROM transaction_categories
                    WHERE categorie_id = %s
                """, (categorie_id,))
                result = cursor.fetchone()

                if result and result['count'] > 0:
                    return False, "Impossible de supprimer : catégorie utilisée dans des transactions"

                # Soft delete
                cursor.execute("""
                    UPDATE categories_transactions
                    SET actif = FALSE
                    WHERE id = %s AND utilisateur_id = %s
                """, (categorie_id, user_id))

                if cursor.rowcount > 0:
                    return True, "Catégorie supprimée avec succès"
                else:
                    return False, "Catégorie non trouvée ou non autorisée"
        except Exception as e:
            logger.error(f"Erreur suppression catégorie: {e}")
            return False, f"Erreur: {str(e)}"

    def associer_categorie_transaction(self, transaction_id: int, categorie_id: int, user_id: int) -> Tuple[bool, str]:
        """Associe une catégorie à une transaction (évite les doublons)"""
        try:
            with self.db.get_cursor() as cursor:
                # ... vérifications de permissions existantes ...

                # Vérifier si l'association existe déjà
                cursor.execute("""
                    SELECT id FROM transaction_categories
                    WHERE transaction_id = %s AND categorie_id = %s AND utilisateur_id = %s
                """, (transaction_id, categorie_id, user_id))

                if cursor.fetchone():
                    return False, "Cette catégorie est déjà associée à la transaction"

                # Créer la nouvelle association
                cursor.execute("""
                    INSERT INTO transaction_categories (transaction_id, categorie_id, utilisateur_id)
                    VALUES (%s, %s, %s)
                """, (transaction_id, categorie_id, user_id))

                return True, "Catégorie associée avec succès"
        except Exception as e:
            logger.error(f"Erreur association catégorie à transaction: {e}")
            return False, f"Erreur: {str(e)}"

    def dissocier_categorie_transaction(self, transaction_id: int, user_id: int) -> Tuple[bool, str]:
        """Dissocie une catégorie d'une transaction"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier les permissions
                cursor.execute("""
                    SELECT tc.id
                    FROM transaction_categories tc
                    JOIN transactions t ON tc.transaction_id = t.id
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                    WHERE tc.transaction_id = %s AND tc.utilisateur_id = %s
                    AND (
                        cp.utilisateur_id = %s OR
                        sc.compte_principal_id IN (
                            SELECT id FROM comptes_principaux WHERE utilisateur_id = %s
                        )
                    )
                """, (transaction_id, user_id, user_id, user_id))

                if not cursor.fetchone():
                    return False, "Association non trouvée ou non autorisée"

                cursor.execute("""
                    DELETE FROM transaction_categories
                    WHERE transaction_id = %s AND utilisateur_id = %s
                """, (transaction_id, user_id))

                return True, "Catégorie dissociée avec succès"
        except Exception as e:
            logger.error(f"Erreur dissociation catégorie de transaction: {e}")
            return False, f"Erreur: {str(e)}"

    def get_categorie_par_id(self, categorie_id: int, user_id: int) -> Optional[Dict]:
        """Récupère une catégorie par son ID pour un utilisateur donné"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT id, nom, description, couleur, icone, type_categorie, budget_mensuel
                    FROM categories_transactions
                    WHERE id = %s AND utilisateur_id = %s AND actif = TRUE
                """, (categorie_id, user_id))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur récupération catégorie par ID: {e}")
            return None

    def get_transactions_par_categorie(self, categorie_id: int, user_id: int,
                                     date_debut: str = None, date_fin: str = None) -> List[Dict]:
        """Récupère toutes les transactions associées à une catégorie"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT
                        t.*,
                        cp.nom_compte as nom_compte_principal,
                        sc.nom_sous_compte as nom_sous_compte
                    FROM transaction_categories tc
                    JOIN transactions t ON tc.transaction_id = t.id
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                    WHERE tc.categorie_id = %s AND tc.utilisateur_id = %s
                """
                params = [categorie_id, user_id]

                if date_debut and date_fin:
                    query += " AND DATE(t.date_transaction) BETWEEN %s AND %s"
                    params.extend([date_debut, date_fin])

                query += " ORDER BY t.date_transaction DESC"

                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération transactions par catégorie: {e}")
            return []

    def get_statistiques_categories(self, user_id: int, date_debut: str = None, date_fin: str = None) -> List[Dict]:
        """Récupère des statistiques sur les catégories de transactions"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT
                        c.id,
                        c.nom,
                        c.type_categorie,
                        c.couleur,
                        c.icone,
                        COUNT(tc.transaction_id) AS nb_transactions,
                        SUM(t.montant) AS total_montant,
                        AVG(t.montant) AS moyenne_montant,
                        c.budget_mensuel,
                        CASE
                            WHEN c.budget_mensuel > 0 THEN
                                ROUND((SUM(t.montant) / c.budget_mensuel) * 100, 2)
                            ELSE 0
                        END as pourcentage_budget
                    FROM categories_transactions c
                    LEFT JOIN transaction_categories tc ON c.id = tc.categorie_id
                    LEFT JOIN transactions t ON tc.transaction_id = t.id
                    WHERE c.utilisateur_id = %s AND c.actif = TRUE
                """
                params = [user_id]

                if date_debut and date_fin:
                    query += " AND t.date_transaction BETWEEN %s AND %s"
                    params.extend([date_debut, date_fin])

                query += """
                    GROUP BY c.id, c.nom, c.type_categorie, c.couleur, c.icone, c.budget_mensuel
                    ORDER BY c.type_categorie, total_montant DESC
                """

                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération statistiques catégories: {e}")
            return []

    def _generer_couleur_aleatoire(self) -> str:
        """Génère une couleur hexadécimale aléatoire"""
        import random
        return f"#{random.randint(0, 0xFFFFFF):06x}"

    def get_categories_transaction(self, transaction_id: int, user_id: int) -> List[Dict]:
        """Récupère TOUTES les catégories d'une transaction spécifique"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT c.id, c.nom, c.description, c.couleur, c.icone, c.type_categorie
                    FROM transaction_categories tc
                    JOIN categories_transactions c ON tc.categorie_id = c.id
                    WHERE tc.transaction_id = %s AND tc.utilisateur_id = %s
                """, (transaction_id, user_id))
                return cursor.fetchall()  # Retourne une LISTE
        except Exception as e:
            logger.error(f"Erreur récupération catégories transaction: {e}")
            return []
    def dissocier_categorie_transaction(self, transaction_id: int, categorie_id: int, user_id: int) -> Tuple[bool, str]:
        """Dissocie une catégorie spécifique d'une transaction"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM transaction_categories
                    WHERE transaction_id = %s AND categorie_id = %s AND utilisateur_id = %s
                """, (transaction_id, categorie_id, user_id))

                if cursor.rowcount > 0:
                    return True, "Catégorie dissociée avec succès"
                else:
                    return False, "Association non trouvée"
        except Exception as e:
            logger.error(f"Erreur dissociation catégorie de transaction: {e}")
            return False, f"Erreur: {str(e)}"

    def dissocier_toutes_categories_transaction(self, transaction_id: int, user_id: int) -> Tuple[bool, str]:
        """Dissocie TOUTES les catégories d'une transaction"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM transaction_categories
                    WHERE transaction_id = %s AND utilisateur_id = %s
                """, (transaction_id, user_id))
                return True, "Toutes les catégories ont été dissociées"
        except Exception as e:
            logger.error(f"Erreur dissociation catégories de transaction: {e}")
            return False, f"Erreur: {str(e)}"

class StatistiquesBancaires:
    """Classe pour générer des statistiques bancaires"""

    def __init__(self, db):
        # L'instance 'db' doit avoir une méthode get_cursor()
        self.db = db

    def get_resume_utilisateur(self, user_id: int, statut: str = 'validée') -> Dict:
        """Résumé financier complet en utilisant les classes existantes"""
        try:
            # Récupérer les comptes principaux en utilisant la classe existante
            compte_model = ComptePrincipal(self.db)
            comptes = compte_model.get_by_user_id(user_id)

            # Calculer les totaux des comptes principaux
            nb_comptes = len(comptes)
            noms_banques = set(compte['nom_banque'] for compte in comptes)
            nb_banques = len(noms_banques)
            solde_total_principal = sum(Decimal(str(compte['solde'])) for compte in comptes)

            # Récupérer et calculer les totaux des sous-comptes
            sous_compte_model = SousCompte(self.db)
            nb_sous_comptes = 0
            epargne_totale = Decimal('0')
            objectifs_totaux = Decimal('0')

            for compte in comptes:
                sous_comptes = sous_compte_model.get_by_compte_principal_id(compte['id'])
                nb_sous_comptes += len(sous_comptes)
                epargne_totale += sum(Decimal(str(sc['solde'])) for sc in sous_comptes)
                objectifs_totaux += sum(Decimal(str(sc['objectif_montant'] or '0')) for sc in sous_comptes)

            # Calculer le patrimoine total
            patrimoine_total = solde_total_principal + epargne_totale

            # Récupérer les transactions du mois en utilisant TransactionFinanciere
            transaction_model = TransactionFinanciere(self.db)
            nb_transactions_mois = 0

            # Pour chaque compte, compter les transactions du mois
            for compte in comptes:
                transactions = transaction_model.get_historique_compte(
                    'compte_principal', compte['id'], user_id,
                    date_from=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                    date_to=datetime.now().strftime('%Y-%m-%d')
                )
                nb_transactions_mois += len(transactions)

            # Pour les sous-comptes
            for compte in comptes:
                sous_comptes = sous_compte_model.get_by_compte_principal_id(compte['id'])
                for sous_compte in sous_comptes:
                    transactions = transaction_model.get_historique_compte(
                        'sous_compte', sous_compte['id'], user_id,
                        date_from=(datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'),
                        date_to=datetime.now().strftime('%Y-%m-%d')
                    )
                    nb_transactions_mois += len(transactions)

            # Pour les écritures comptables, nous utilisons une requête directe
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    COUNT(*) as nb_ecritures_mois,
                    SUM(CASE WHEN type_ecriture = 'depense' THEN montant ELSE 0 END) as total_depenses,
                    SUM(CASE WHEN type_ecriture = 'recette' THEN montant ELSE 0 END) as total_recettes
                FROM ecritures_comptables
                WHERE utilisateur_id = %s
                AND statut = %s
                AND date_ecriture >= DATE_SUB(NOW(), INTERVAL 1 MONTH)
                """
                cursor.execute(query, (user_id, statut))
                stats_ecritures = cursor.fetchone()

            nb_ecritures_mois = stats_ecritures['nb_ecritures_mois'] or 0
            total_depenses = Decimal(str(stats_ecritures['total_depenses'] or '0'))
            total_recettes = Decimal(str(stats_ecritures['total_recettes'] or '0'))
            solde_mois = total_recettes - total_depenses

            # Calculer la progression de l'épargne
            progression_epargne = Decimal('0')
            if objectifs_totaux and objectifs_totaux > 0:
                progression_epargne = (epargne_totale / objectifs_totaux) * 100

            return {
                'nb_comptes': nb_comptes,
                'nb_banques': nb_banques,
                'nb_sous_comptes': nb_sous_comptes,
                'solde_total_principal': float(solde_total_principal),
                'epargne_totale': float(epargne_totale),
                'patrimoine_total': float(patrimoine_total),
                'objectifs_totaux': float(objectifs_totaux),
                'nb_transactions_mois': nb_transactions_mois,
                'nb_ecritures_mois': nb_ecritures_mois,
                'total_depenses_mois': float(total_depenses),
                'total_recettes_mois': float(total_recettes),
                'solde_mois': float(solde_mois),
                'progression_epargne': float(round(progression_epargne, 2)),
                'statut_utilise': statut
            }

        except Exception as e:
            logger.error(f"Erreur lors du calcul des statistiques: {e}")
            # Retourner des valeurs par défaut en cas d'erreur
            return {
                'nb_comptes': 0,
                'nb_banques': 0,
                'nb_sous_comptes': 0,
                'solde_total_principal': 0.0,
                'epargne_totale': 0.0,
                'patrimoine_total': 0.0,
                'objectifs_totaux': 0.0,
                'nb_transactions_mois': 0,
                'nb_ecritures_mois': 0,
                'total_depenses_mois': 0.0,
                'total_recettes_mois': 0.0,
                'solde_mois': 0.0,
                'progression_epargne': 0.0,
                'statut_utilise': statut
            }

    def get_repartition_par_banque(self, user_id: int) -> List[Dict]:
        """Répartition du patrimoine par banque"""
        try:
            compte_model = ComptePrincipal(self.db)
            comptes = compte_model.get_by_user_id(user_id)
            sous_compte_model = SousCompte(self.db)
            repartition = {}

            for compte in comptes:
                banque_nom = compte['nom_banque']
                banque_couleur = compte.get('couleur_banque', '#3498db')

                if banque_nom not in repartition:
                    repartition[banque_nom] = {
                        'nom_banque': banque_nom,
                        'couleur': banque_couleur,
                        'montant_total': Decimal('0'),
                        'nb_comptes': 0
                    }

                repartition[banque_nom]['montant_total'] += Decimal(str(compte['solde']))
                repartition[banque_nom]['nb_comptes'] += 1

                sous_comptes = sous_compte_model.get_by_compte_principal_id(compte['id'])
                for sous_compte in sous_comptes:
                    repartition[banque_nom]['montant_total'] += Decimal(str(sous_compte['solde']))

            result = list(repartition.values())
            result.sort(key=lambda x: x['montant_total'], reverse=True)

            return result
        except Exception as e:
            logger.error(f"Erreur lors du calcul de la répartition par banque: {e}")
            return []

    def get_evolution_epargne(self, user_id: int, nb_mois: int = 6, statut: str = 'validée') -> List[Dict]:
        """Évolution de l'épargne sur les derniers mois"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    DATE_FORMAT(t.date_transaction, '%Y-%m') as mois,
                    SUM(CASE
                        WHEN t.type_transaction IN ('transfert_compte_vers_sous', 'depot')
                        THEN t.montant ELSE 0 END) as epargne_mensuelle
                FROM transactions t
                JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                WHERE cp.utilisateur_id = %s
                    AND t.date_transaction >= DATE_SUB(NOW(), INTERVAL %s MONTH)
                    AND t.type_transaction IN ('transfert_compte_vers_sous', 'depot')
                GROUP BY DATE_FORMAT(t.date_transaction, '%Y-%m')
                ORDER BY mois DESC
                """
                cursor.execute(query, (user_id, nb_mois))
                evolution = cursor.fetchall()
                return evolution
        except Exception as e:
            logger.error(f"Erreur lors du calcul de l'évolution: {e}")
            return []

    def get_evolution_soldes_quotidiens(self, user_id: int, nb_jours: int = 30) -> Dict[str, List]:
        """Récupère l'évolution quotidienne des soldes pour tous les comptes"""
        try:
            with self.db.get_cursor() as cursor:
                # Pour les comptes principaux - utiliser les transactions
                query_comptes = """
                SELECT
                    DATE(t.date_transaction) as date,
                    cp.nom_compte,
                    t.solde_apres as solde_quotidien
                FROM transactions t
                JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                WHERE cp.utilisateur_id = %s
                    AND t.date_transaction >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    AND t.id IN (
                        SELECT MAX(t2.id)
                        FROM transactions t2
                        WHERE t2.compte_principal_id = cp.id
                        AND DATE(t2.date_transaction) = DATE(t.date_transaction)
                        GROUP BY DATE(t2.date_transaction)
                    )
                ORDER BY date, cp.nom_compte
                """
                cursor.execute(query_comptes, (user_id, nb_jours))
                evolution_comptes = cursor.fetchall()

                # Pour les sous-comptes - utiliser les transactions
                query_sous_comptes = """
                SELECT
                    DATE(t.date_transaction) as date,
                    sc.nom_sous_compte,
                    t.solde_apres as solde_quotidien
                FROM transactions t
                JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                JOIN comptes_principaux cp ON sc.compte_principal_id = cp.id
                WHERE cp.utilisateur_id = %s
                    AND t.date_transaction >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    AND t.id IN (
                        SELECT MAX(t2.id)
                        FROM transactions t2
                        WHERE t2.sous_compte_id = sc.id
                        AND DATE(t2.date_transaction) = DATE(t.date_transaction)
                        GROUP BY DATE(t2.date_transaction)
                    )
                ORDER BY date, sc.nom_sous_compte
                """
                cursor.execute(query_sous_comptes, (user_id, nb_jours))
                evolution_sous_comptes = cursor.fetchall()

                return {
                    'comptes_principaux': evolution_comptes,
                    'sous_comptes': evolution_sous_comptes,
                    'total': []  # On ne calcule pas le total ici
                }
        except Error as e:
            logger.error(f"Erreur lors du calcul de l'évolution quotidienne: {e}")
            return {'comptes_principaux': [], 'sous_comptes': [], 'total': []}

    def preparer_svg_tresorie(self, user_id: int, compte_id: int, date_debut: date, date_fin : date):
        pass
    def preparer_graphique_solde_quotidien(self, user_id: int, compte_id: int, date_debut: date, date_fin: date) -> Optional[Dict]:
        """Prépare les données pour un graphique SVG de l'évolution quotidienne du solde."""
        try:
            tx_model = TransactionFinanciere(self.db)
            soldes = tx_model.get_evolution_soldes_quotidiens_compte(
                compte_id=compte_id,
                user_id=user_id,
                date_debut=date_debut.strftime('%Y-%m-%d'),
                date_fin=date_fin.strftime('%Y-%m-%d')
            )
            if not soldes:
                return None

            dates = [s['date'].strftime('%d/%m') for s in soldes]
            valeurs = [float(s['solde_apres']) for s in soldes]
            min_val = min(valeurs)
            max_val = max(valeurs)

            # Éviter division par zéro
            if min_val == max_val:
                if min_val == 0:
                    max_val = 100.0
                else:
                    min_val *= 0.9
                    max_val *= 1.1

            return {
                'type': 'line',
                'titre': 'Évolution du solde',
                'labels': dates,
                'valeurs': valeurs,
                'min': min_val,
                'max': max_val,
                'unite': 'CHF'
            }
        except Exception as e:
            logger.error(f"Erreur préparation graphique solde quotidien: {e}")
            return None

    def preparer_graphique_tresorerie(self, user_id: int, compte_id: int, date_debut: date, date_fin: date) -> Optional[Dict]:
        """Prépare les données pour un graphique en barres ou camembert des recettes/dépenses."""
        try:
            tx_model = TransactionFinanciere(self.db)
            stats = tx_model.get_statistiques_compte(
                compte_type='compte_principal',
                compte_id=compte_id,
                user_id=user_id,
                date_debut=date_debut.strftime('%Y-%m-%d'),
                date_fin=date_fin.strftime('%Y-%m-%d')
            )
            if not stats:
                return None

            recettes = stats.get('total_entrees', 0.0)
            depenses = stats.get('total_sorties', 0.0)

            return {
                'type': 'bar',
                'titre': 'Trésorerie',
                'labels': ['Recettes', 'Dépenses'],
                'valeurs': [recettes, depenses],
                'couleurs': ['#28a745', '#dc3545'],
                'unite': 'CHF'
            }
        except Exception as e:
            logger.error(f"Erreur préparation graphique trésorerie: {e}")
            return None

    def preparer_graphique_tresorerie_cumulee(self, user_id: int, compte_id: int, date_debut: date, date_fin: date) -> Optional[Dict]:
        """Prépare les données pour un graphique du solde cumulé (flux de trésorerie)."""
        try:
            tx_model = TransactionFinanciere(self.db)
            # Récupérer TOUTES les transactions dans la période, triées
            transactions = tx_model.get_historique_compte(
                compte_type='compte_principal',
                compte_id=compte_id,
                user_id=user_id,
                date_from=date_debut.strftime('%Y-%m-%d'),
                date_to=date_fin.strftime('%Y-%m-%d'),
                limit=1000  # assez grand
            )
            if not transactions:
                return None

            # Trier par date (au cas où)
            transactions.sort(key=lambda x: x['date_transaction'])

            # Récupérer le solde initial AVANT la période
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT COALESCE(solde_initial, 0) as solde_initial
                    FROM comptes_principaux WHERE id = %s
                """, (compte_id,))
                row = cursor.fetchone()
                solde_initial = float(row['solde_initial']) if row else 0.0

            # Calculer le solde cumulé JOUR PAR JOUR

            daily_net = defaultdict(float)
            for tx in transactions:
                date_key = tx['date_transaction'].date()
                montant = float(tx['montant'])
                if tx['type_transaction'] in ['depot', 'transfert_entrant', 'recredit_annulation', 'transfert_sous_vers_compte']:
                    daily_net[date_key] += montant
                else:
                    daily_net[date_key] -= montant

            # Générer série complète de dates
            current = date_debut
            dates = []
            soldes_cumules = []
            solde_courant = solde_initial

            while current <= date_fin:
                dates.append(current.strftime('%d/%m'))
                if current in daily_net:
                    solde_courant += daily_net[current]
                soldes_cumules.append(solde_courant)
                current += timedelta(days=1)

            return {
                'type': 'line',
                'titre': 'Trésorerie cumulée',
                'labels': dates,
                'valeurs': soldes_cumules,
                'min': min(soldes_cumules),
                'max': max(soldes_cumules),
                'unite': 'CHF'
            }
        except Exception as e:
            logger.error(f"Erreur préparation trésorerie cumulée: {e}")
            return None

    def preparer_graphique_categories(self, user_id: int, compte_id: int, date_debut: date, date_fin: date) -> Optional[Dict]:
        tx_model = TransactionFinanciere(self.db)
        categories = tx_model.get_categories_par_type(
            'compte_principal', compte_id, user_id,
            date_debut.strftime('%Y-%m-%d'),
            date_fin.strftime('%Y-%m-%d')
        )
        if not categories:
            return None
        return {
            'type': 'bar',
            'titre': 'Répartition des opérations',
            'labels': list(categories.keys()),
            'valeurs': [float(v) for v in categories.values()],
            'unite': 'CHF'
        }

    def preparer_graphique_tresorerie_compare(self, user_id: int, compte_id: int, date_debut: date, date_fin: date) -> Optional[Dict]:
        """
        Prépare les données pour un graphique en barres côte à côte :
        - Recettes (positive, en vert)
        - Dépenses (positive, en rouge)
        Les deux sont affichées au-dessus de 0 pour faciliter la comparaison visuelle.
        """
        try:
            tx_model = TransactionFinanciere(self.db)
            stats = tx_model.get_statistiques_compte(
                compte_type='compte_principal',
                compte_id=compte_id,
                user_id=user_id,
                date_debut=date_debut.strftime('%Y-%m-%d'),
                date_fin=date_fin.strftime('%Y-%m-%d')
            )
            if not stats:
                return None

            recettes = float(stats.get('total_entrees', 0.0))
            depenses = float(stats.get('total_sorties', 0.0))

            return {
                'type': 'bar_compare',
                'titre': 'Recettes vs Dépenses',
                'labels': ['Recettes', 'Dépenses'],
                'valeurs': [recettes, depenses],
                'couleurs': ['#28a745', '#dc3545'],  # vert, rouge
                'unite': 'CHF'
            }
        except Exception as e:
            logger.error(f"Erreur préparation graphique comparaison trésorerie: {e}")
            return None

class PlanComptable:
    """Modèle pour gérer le plan comptable"""

    def __init__(self, db):
        self.db = db

    def create_plan(self, data: Dict) -> Optional[int]:
        """Crée un nouveau plan comptable"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO plans_comptables (nom, description, devise, utilisateur_id)
                VALUES (%s, %s, %s, %s)
                """
                values = (
                    data['nom'],
                    data.get('description', ''),
                    data.get('devise', 'CHF'),
                    data['utilisateur_id']
                )
                cursor.execute(query, values)
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Erreur création plan comptable: {e}")
            return None

    def modifier_plan(self, plan_id: int, data: Dict) -> bool:
        pass
    def supprimer_plan(self, plan_id: int, data: Dict) -> bool:
        pass

    def get_all_plans(self, utilisateur_id: int) -> List[Dict]:
        """Liste tous les plans de l'utilisateur"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT id, nom, description, devise, created_at
                    FROM plans_comptables
                    WHERE utilisateur_id = %s AND actif = 1
                    ORDER BY nom
                """, (utilisateur_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur liste plans: {e}")
            return []

    def get_plan_with_categories(self, plan_id: int, utilisateur_id: int) -> Optional[Dict]:
        """Récupère un plan + ses catégories"""
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer le plan
                cursor.execute("""
                    SELECT * FROM plans_comptables
                    WHERE id = %s AND utilisateur_id = %s
                """, (plan_id, utilisateur_id))
                plan = cursor.fetchone()
                if not plan:
                    return None

                # Récupérer les catégories liées
                cursor.execute("""
                    SELECT c.*
                    FROM plan_categorie pc
                    JOIN categories_comptables c ON pc.categorie_id = c.id
                    WHERE pc.plan_id = %s AND c.utilisateur_id = %s
                    ORDER BY c.numero
                """, (plan_id, utilisateur_id))
                plan['categories'] = cursor.fetchall()
                return plan
        except Exception as e:
            logger.error(f"Erreur plan + catégories: {e}")
            return None

    def add_categorie_to_plan(self, plan_id: int, categorie_id: int, utilisateur_id: int) -> bool:
        """Ajoute une catégorie à un plan"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que les deux existent et appartiennent à l'utilisateur
                cursor.execute("SELECT id FROM plans_comptables WHERE id = %s AND utilisateur_id = %s", (plan_id, utilisateur_id))
                if not cursor.fetchone():
                    return False
                cursor.execute("SELECT id FROM categories_comptables WHERE id = %s AND utilisateur_id = %s", (categorie_id, utilisateur_id))
                if not cursor.fetchone():
                    return False

                cursor.execute("""
                    INSERT IGNORE INTO plan_categorie (plan_id, categorie_id)
                    VALUES (%s, %s)
                """, (plan_id, categorie_id))
                return True
        except Exception as e:
            logger.error(f"Erreur ajout catégorie au plan: {e}")
            return False

    def remove_categorie_from_plan(self, plan_id: int, categorie_id: int) -> bool:
        """Retire une catégorie d’un plan"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM plan_categorie
                    WHERE plan_id = %s AND categorie_id = %s
                """, (plan_id, categorie_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur retrait catégorie du plan: {e}")
            return False
    def get_categories_for_plan(self, plan_id: int, utilisateur_id: int) -> List[Dict]:
        """Récupère uniquement les catégories d’un plan"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT c.*
                    FROM plan_categorie pc
                    JOIN categories_comptables c ON pc.categorie_id = c.id
                    WHERE pc.plan_id = %s AND c.utilisateur_id = %s
                    ORDER BY c.numero
                """, (plan_id, utilisateur_id))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur catégories du plan: {e}")
            return []


class CategorieComptable:
    def __init__(self, db):
        self.db = db
    def create(self, data: Dict) -> bool:
        """Crée une nouvelle catégorie comptable"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO categories_comptables
                (numero, nom, parent_id, type_compte, compte_systeme, compte_associe, type_tva, actif)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    data['numero'],
                    data['nom'],
                    data.get('parent_id'),
                    data['type_compte'],
                    data.get('compte_systeme'),
                    data.get('compte_associe'),
                    data.get('type_tva'),
                    data.get('actif', True)
                )
                cursor.execute(query, values)
                # Le commit est géré par le context manager dans la classe DatabaseManager
            return True
        except Error as e:
            logger.error(f"Erreur lors de la création de la catégorie comptable: {e}")
            return False

    def modifier_plan(self, plan_id: int, data: Dict, utilisateur_id: int) -> bool:
        """Met à jour un plan comptable"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que le plan existe et appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM plans_comptables WHERE id = %s AND utilisateur_id = %s",
                    (plan_id, utilisateur_id)
                )
                if not cursor.fetchone():
                    return False

                query = """
                UPDATE plans_comptables
                SET nom = %s, description = %s, devise = %s
                WHERE id = %s AND utilisateur_id = %s
                """
                values = (
                    data['nom'],
                    data.get('description', ''),
                    data.get('devise', 'CHF'),
                    plan_id,
                    utilisateur_id
                )
                cursor.execute(query, values)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur mise à jour plan comptable: {e}")
            return False

    def update(self, categorie_id: int, data: Dict) -> bool:
        """Met à jour une catégorie comptable"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE categories_comptables
                SET numero = %s, nom = %s, parent_id = %s, type_compte = %s,
                    compte_systeme = %s, compte_associe = %s, type_tva = %s, actif = %s
                WHERE id = %s
                """
                values = (
                    data['numero'],
                    data['nom'],
                    data.get('parent_id'),
                    data['type_compte'],
                    data.get('compte_systeme'),
                    data.get('compte_associe'),
                    data.get('type_tva'),
                    data.get('actif', True),
                    categorie_id
                )
                cursor.execute(query, values)
                # Le commit est géré par le context manager
            return True
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour de la catégorie comptable: {e}")
            return False

    def delete(self, categorie_id: int) -> bool:
        """Supprime une catégorie comptable (soft delete)"""
        try:
            with self.db.get_cursor() as cursor:
                query = "UPDATE categories_comptables SET actif = FALSE WHERE id = %s"
                cursor.execute(query, (categorie_id,))
                # Le commit est géré par le context manager
            return True
        except Error as e:
            logger.error(f"Erreur lors de la suppression de la catégorie comptable: {e}")
            return False

    def get_by_id(self, categorie_id: int) -> Optional[Dict]:
        """Récupère une catégorie par son ID"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM categories_comptables WHERE id = %s"
                cursor.execute(query, (categorie_id,))
                categorie = cursor.fetchone()
            return categorie
        except Error as e:
            logger.error(f"Erreur lors de la récupération de la catégorie comptable: {e}")
            return None

    def get_all_categories(self, utilisateur_id: int = None) -> List[Dict]:
        """Récupère toutes les catégories avec info sur le parent"""
        try:
            with self.db.get_cursor() as cursor:
                if utilisateur_id:
                    query = """
                    SELECT
                        c1.id, c1.numero, c1.nom, c1.parent_id, c1.type_compte,
                        c1.compte_systeme, c1.compte_associe, c1.type_tva, c1.actif,
                        c1.categorie_complementaire_id,
                        c1.type_ecriture_complementaire,
                        c2.numero as parent_numero, c2.nom as parent_nom,
                        c3.numero as categorie_complementaire_numero,
                        c3.nom as categorie_complementaire_nom
                    FROM categories_comptables c1
                    LEFT JOIN categories_comptables c2 ON c1.parent_id = c2.id
                    LEFT JOIN categories_comptables c3 ON c1.categorie_complementaire_id = c3.id
                    WHERE c1.utilisateur_id = %s
                    ORDER BY c1.numero
                    """
                    cursor.execute(query, (utilisateur_id,))
                else:
                    query = """
                    SELECT
                        c1.id, c1.numero, c1.nom, c1.parent_id, c1.type_compte,
                        c1.compte_systeme, c1.compte_associe, c1.type_tva, c1.actif,
                        c1.categorie_complementaire_id,
                        c1.type_ecriture_complementaire,
                        c2.numero as parent_numero, c2.nom as parent_nom,
                        c3.numero as categorie_complementaire_numero,
                        c3.nom as categorie_complementaire_nom
                    FROM categories_comptables c1
                    LEFT JOIN categories_comptables c2 ON c1.parent_id = c2.id
                    LEFT JOIN categories_comptables c3 ON c1.categorie_complementaire_id = c3.id
                    ORDER BY c1.numero
                    """
                    cursor.execute(query)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur get_all_categories: {e}")
            return []

    def get_by_numero(self, numero: str, utilisateur_id: int) -> Optional[Dict]:
        """Récupère une catégorie par son numéro"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM categories_comptables WHERE numero = %s AND utilisateur_id = %s"
                cursor.execute(query, (numero, utilisateur_id))
                categorie = cursor.fetchone()
            return categorie
        except Error as e:
            logger.error(f"Erreur lors de la récupération de la catégorie comptable: {e}")
            return None

    def get_by_type(self, type_compte: str, utilisateur_id: int) -> List[Dict]:
        """Récupère les catégories par type de compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM categories_comptables WHERE type_compte = %s AND utilisateur_id = %s ORDER BY numero"
                cursor.execute(query, (type_compte, utilisateur_id))
                categories = cursor.fetchall()
            return categories
        except Error as e:
            logger.error(f"Erreur lors de la récupération des catégories comptables: {e}")
            return []

    def get_categories_avec_complementaires(self, utilisateur_id: int) -> List[Dict]:
        """Récupère les catégories comptables avec leurs configurations de complémentaires (TVA, etc.)"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    c.id,
                    c.numero,
                    c.nom,
                    c.parent_id,
                    c.type_compte,
                    c.compte_systeme,
                    c.compte_associe,
                    -- 🔥 CORRIGÉ : La colonne categorie_complementaire_id appartient à c (categories_comptables)
                    c.categorie_complementaire_id,
                    c.type_ecriture_complementaire,
                    c.type_tva,
                    -- On récupère aussi les infos de la catégorie complémentaire si elle existe
                    cc.numero as comp_numero,
                    cc.nom as comp_nom
                FROM categories_comptables c
                -- 🔥 CORRIGÉ : Jointure avec categories_comptables (cc) pour les infos de la catégorie complémentaire
                LEFT JOIN categories_comptables cc ON c.categorie_complementaire_id = cc.id
                WHERE c.utilisateur_id = %s AND c.actif = TRUE
                ORDER BY c.numero
                """
                # Il y a 1 seul placeholder '%s' dans la requête corrigée.
                cursor.execute(query, (utilisateur_id,)) # On passe 1 seul argument.
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur get_categories_avec_complementaires: {e}")
            return []

    def ajouter_categorie_complementaire(self, categorie_id: int, categorie_complementaire_id: int,
                                       utilisateur_id: int, type_complement: str = 'tva',
                                       taux: float = 0.0) -> bool:
        """Ajoute une relation de catégorie complémentaire"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO categories_transactions
                (categorie_id, categorie_complementaire_id, utilisateur_id, type_complement, taux)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                type_complement = VALUES(type_complement),
                taux = VALUES(taux),
                actif = TRUE
                """
                cursor.execute(query, (categorie_id, categorie_complementaire_id, utilisateur_id, type_complement, taux))
                return True
        except Exception as e:
            logger.error(f"Erreur ajouter_categorie_complementaire: {e}")
            return False

    def has_categorie_complementaire(self, categorie_id: int, utilisateur_id: int) -> bool:
        """Vérifie si une catégorie a une catégorie complémentaire configurée."""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT COUNT(*) as count
                FROM categories_comptables
                WHERE id = %s
                AND utilisateur_id = %s
                AND categorie_complementaire_id IS NOT NULL
                AND actif = TRUE
                """
                cursor.execute(query, (categorie_id, utilisateur_id))
                result = cursor.fetchone()
                has_complementaire = result['count'] > 0
                logger.info(f"Catégorie ID {categorie_id} a une catégorie complémentaire: {has_complementaire}")
                return has_complementaire
        except Exception as e:
            logger.error(f"Erreur dans has_categorie_complementaire: {e}")
            return False
    def get_categorie_complementaire(self, categorie_id: int, utilisateur_id: int)-> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT ct.id, ct.numero, ct.nom, ct.categorie_complementaire_id as id_complementaire, ct2.numero as numero_complementaire, ct2.nom as nom_complementaire
                FROM categories_comptables ct
                JOIN categories_comptables ct2 ON ct.categorie_complementaire_id = ct2.id
                WHERE ct.id = %s AND ct.utilisateur_id = %s;

                """
                cursor.execute(query, (categorie_id, utilisateur_id))
                result = cursor.fetchall()
                logger.info(f'La categorie avec id {categorie_id} a : {result}')
                return result
        except Exception as e:
            logger.error(f'Erreur dans la recherche de catégorie complémentaire: {e}')
            return None

class EcritureComptable:
    """Modèle pour gérer les écritures comptables"""

    def __init__(self, db):
        self.db = db

    
    @property
    def upload_folder(self):
        """Fournit le dossier d'upload à la demande, sans effet de bord à l'initialisation"""
        return os.path.join(os.path.dirname(__file__), 'uploads', 'justificatifs')

    def ensure_upload_folder(self):
        """À appeler explicitement quand nécessaire (ex: dans une route)"""
        folder = self.upload_folder
        os.makedirs(folder, exist_ok=True)
        return folder

    def _get_file_path(self, filename):
        """Génère le chemin complet du fichier"""
        return os.path.join(self.upload_folder, filename)
    def test_dossier_upload(self):
        """Teste l'accès au dossier d'upload"""
        print(f"=== TEST DOSSIER UPLOAD ===")
        print(f"Chemin absolu: {os.path.abspath(self.upload_folder)}")
        print(f"Dossier existe: {os.path.exists(self.upload_folder)}")

        if os.path.exists(self.upload_folder):
            print(f"Permissions lecture: {os.access(self.upload_folder, os.R_OK)}")
            print(f"Permissions écriture: {os.access(self.upload_folder, os.W_OK)}")

            # Test d'écriture
            test_file = os.path.join(self.upload_folder, 'test.txt')
            try:
                with open(test_file, 'w') as f:
                    f.write('test écriture')
                print("✓ Test écriture réussi")

                # Lire pour vérifier
                with open(test_file, 'r') as f:
                    content = f.read()
                print(f"✓ Contenu lu: {content}")

                os.remove(test_file)
                print("✓ Test suppression réussi")
                return True
            except Exception as e:
                print(f"✗ Erreur écriture: {e}")
                return False
        else:
            print("❌ Dossier n'existe pas")
            return False

    def create(self, categorie_comptable_model, data: Dict) -> bool:
        """Crée une nouvelle écriture comptable"""
        # Validation du lien catégorie ↔ plan comptable du compte
        if data.get('id_contact'):
            if not self._is_categorie_valid_for_contact(
                data['id_contact'],
                data['categorie_id'],
                data['utilisateur_id']
            ):
                logger.warning("Catégorie non autorisée pour ce contact.")
                return False
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO ecritures_comptables
                (date_ecriture, compte_bancaire_id, categorie_id, montant, montant_htva, devise,
                description, reference, type_ecriture, tva_taux, tva_montant,
                utilisateur_id, justificatif_url, statut, id_contact, type_ecriture_comptable)
                VALUES (%s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s)
                """
                values = (
                    data['date_ecriture'],
                    data['compte_bancaire_id'],
                    data['categorie_id'],
                    data['montant'],
                    data['montant_htva'],
                    data.get('devise', 'CHF'),
                    data.get('description', ''),
                    data.get('reference', ''),
                    data['type_ecriture'],  # 'depense' ou 'recette'
                    data.get('tva_taux'),
                    data.get('tva_montant'),
                    data['utilisateur_id'],
                    data.get('justificatif_url'),
                    data.get('statut', 'pending'),  # 'pending', 'validée', 'rejetée'
                    data.get('id_contact'),
                    data.get('type_ecriture_comptable', 'principale')  # Toujours 'principale' au départ
                )

                cursor.execute(query, values)
                ecriture_principale_id = cursor.lastrowid
                logger.info(f"Écriture principale créée avec ID: {ecriture_principale_id}")

                # 🔥 Vérifier si la catégorie a une catégorie complémentaire
                categorie_id = data['categorie_id']
                utilisateur_id = data['utilisateur_id']

                if categorie_comptable_model:
                    has_complementaire = categorie_comptable_model.has_categorie_complementaire(
                        categorie_id, utilisateur_id
                    )
                    if has_complementaire:
                        logger.info(f"La catégorie ID {categorie_id} a une catégorie complémentaire. Création d'écritures secondaires.")
                        self._create_secondary_ecritures(cursor, ecriture_principale_id, data)
                    else:
                        logger.info(f"La catégorie ID {categorie_id} n'a pas de catégorie complémentaire. Aucune écriture secondaire.")
                else:
                    logger.warning("Modèle CategorieComptable non disponible pour la vérification.")
            return True
        except Error as e:
            logger.error(f"Erreur lors de la création de l'écriture comptable: {e}")
            return False

    def _create_secondary_ecritures(self, cursor, ecriture_principale_id: int,  data: Dict):
        """Crée les écritures secondaires (TVA, taxes, etc.)"""
        try:
            logger.info(f"Début de la vérification des écritures secondaires pour l'écriture principale ID: {ecriture_principale_id}")

            categorie_id = data['categorie_id']
            utilisateur_id = data['utilisateur_id']

            query = """
            SELECT
                cc.categorie_complementaire_id,
                cc.type_ecriture_complementaire,
                cc.type_tva,  -- ❌ Cela peut être NULL
                cc.nom as categorie_nom,
                cc.numero as categorie_numero,
                cc_comp.nom as categorie_complementaire_nom,
                cc_comp.numero as categorie_complementaire_numero
            FROM categories_comptables cc
            LEFT JOIN categories_comptables cc_comp ON cc.categorie_complementaire_id = cc_comp.id
            WHERE cc.id = %s
            AND cc.utilisateur_id = %s
            AND cc.actif = TRUE
            AND cc.categorie_complementaire_id IS NOT NULL
            """

            cursor.execute(query, (categorie_id, utilisateur_id))
            result = cursor.fetchone()

            if not result:
                logger.info(f"Aucune catégorie complémentaire configurée pour la catégorie ID {categorie_id}.")
                return

            categorie_complementaire_id = result['categorie_complementaire_id']
            type_ecriture_complementaire = result['type_ecriture_complementaire']
            type_tva_config = result['type_tva']  # Peut être None
            categorie_nom = result['categorie_nom']
            categorie_numero = result['categorie_numero']
            categorie_complementaire_nom = result.get('categorie_complementaire_nom', 'N/A')
            categorie_complementaire_numero = result.get('categorie_complementaire_numero', 'N/A')

            logger.info(
                f"Catégorie '{categorie_numero} - {categorie_nom}' a une catégorie complémentaire "
                f"'{categorie_complementaire_numero} - {categorie_complementaire_nom}' "
                f"(ID: {categorie_complementaire_id}) avec type '{type_ecriture_complementaire}'."
            )

            # 🔥 RÉCUPÉRER LE TAUX RÉEL à partir de la configuration ou de data
            # Selon votre logique, le taux peut venir de type_tva OU de data['tva_taux']
            if type_ecriture_complementaire == 'tva':
                montant_secondaire = data.get('tva_montant', 0.0)
                taux_secondaire = data.get('tva_taux', 0.0)  # ✅ On garde le taux de la principale
            else:
                # 🔥 RÉCUPÉRER LE TAUX RÉEL à partir de la configuration ou de data
                taux_reel = type_tva_config if type_tva_config is not None else data.get('tva_taux', 0)
                taux_secondaire = taux_reel  # ✅ On garde ce taux pour les autres types
                # ✅ Maintenant on envoie le bon taux
                montant_secondaire = self._calculate_secondary_amount(
                    data, type_ecriture_complementaire, taux_reel
                )

            if abs(montant_secondaire) > 0.01:
                comp_cat_simulated = {
                    'categorie_complementaire_id': categorie_complementaire_id,
                    'type_complement': type_ecriture_complementaire,
                    'taux': taux_secondaire  # ✅ aussi ici
                }
                self._create_secondary_ecriture(
                    cursor, ecriture_principale_id, data, comp_cat_simulated, montant_secondaire)
                logger.info(f"Écriture secondaire de {montant_secondaire:.2f} CHF créée pour la catégorie complémentaire ID {categorie_complementaire_id}.")
            else:
                logger.info(f"Montant secondaire négligeable ({montant_secondaire:.2f} CHF), pas de création d'écriture.")

        except Exception as e:
            logger.error(f"Erreur lors de la création des écritures secondaires pour écriture ID {ecriture_principale_id}: {e}")
            raise

    def has_secondary_ecritures(self, ecriture_id: int, user_id: int) -> bool:
        """Vérifie si une écriture a des écritures secondaires"""
        try:
            secondaires = self.get_ecritures_complementaires(ecriture_id, user_id)
            return len(secondaires) > 0
        except Exception as e:
            logger.error(f"Erreur vérification écritures secondaires: {e}")
            return False

    def _calculate_secondary_amount(self, data: Dict, type_complement: str, taux: float) -> float:
        """Calcule le montant pour l'écriture secondaire"""
        montant_principal = data['montant']
        montant_htva = data.get('montant_htva', montant_principal)
        tva_taux = data.get('tva_taux', 0)

        if type_complement == 'tva':
            # Logique de calcul TVA
            if data.get('tva_montant') is not None:
                return data['tva_montant']
            elif tva_taux and tva_taux > 0:
                base_calcul = montant_htva if montant_htva != montant_principal else montant_principal
                return base_calcul * (tva_taux / 100)
            else:
                return 0

        elif type_complement == 'taxe':
            # Calcul pour autres taxes
            return montant_principal * (taux / 100)

        else:
            return montant_principal * (taux / 100)

    def _get_secondary_type(self, type_principal: str, type_complement: str) -> str:
        """Détermine le type d'écriture pour la secondaire"""
        if type_complement == 'tva':
            # La TVA est généralement une dette (passif) donc recette pour le compte TVA
            return 'recette' if type_principal == 'depense' else 'depense'
        else:
            return type_principal

    def _create_secondary_ecriture(self, cursor, ecriture_principale_id: int, data: Dict, comp_cat: Dict, montant_secondaire: float):
        """Crée une écriture secondaire individuelle"""
        try:
            # 🔥 Déterminer le type d'écriture pour la secondaire
            type_ecriture_secondaire = self._get_secondary_type(data['type_ecriture'], comp_cat['type_complement'])

            logger.info(
                f"Création d'une écriture secondaire de type '{type_ecriture_secondaire}' "
                f"pour la catégorie complémentaire ID {comp_cat['categorie_complementaire_id']}, "
                f"montant: {montant_secondaire:.2f} CHF."
            )

            query = """
            INSERT INTO ecritures_comptables(
                date_ecriture, compte_bancaire_id, categorie_id, montant, montant_htva, devise,
                description, reference, type_ecriture, tva_taux, tva_montant,
                utilisateur_id, justificatif_url, statut, id_contact,
                ecriture_principale_id, type_ecriture_comptable
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'complementaire')
            """

            values = (
                data['date_ecriture'],
                data['compte_bancaire_id'],  # Ou un compte spécifique pour les taxes
                comp_cat['categorie_complementaire_id'],
                abs(montant_secondaire),  # Valeur absolue, le sens dépend du type
                abs(montant_secondaire),
                data.get('devise', 'CHF'),
                f"{data.get('description', '')} ({comp_cat['type_complement'].upper()})",
                data.get('reference', ''),
                type_ecriture_secondaire,
                comp_cat.get('taux', 0),  # Pas de TVA sur la TVA
                0,
                data['utilisateur_id'],
                data.get('justificatif_url'),
                data.get('statut', 'pending'),
                data.get('id_contact'),
                ecriture_principale_id
            )

            cursor.execute(query, values)
            logger.info(f"Écriture secondaire insérée dans la base de données avec succès.")

        except Exception as e:
            logger.error(f"Erreur lors de la création de l'écriture secondaire: {e}")
            raise


    def get_ecriture_avec_secondaires(self, ecriture_id: int, user_id: int) -> Dict:
        """Récupère une écriture principale avec toutes ses écritures secondaires"""
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer l'écriture principale
                cursor.execute("""
                    SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                        cb.nom_compte as compte_bancaire_nom
                    FROM ecritures_comptables e
                    LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                    LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                    WHERE e.id = %s AND e.utilisateur_id = %s
                """, (ecriture_id, user_id))
                ecriture_principale = cursor.fetchone()

                if not ecriture_principale:
                    return None

                # Récupérer les écritures secondaires
                ecritures_secondaires = self.get_ecritures_complementaires(ecriture_id, user_id)

                return {
                    'principale': ecriture_principale,
                    'secondaires': ecritures_secondaires
                }
        except Exception as e:
            logger.error(f"Erreur get_ecriture_avec_secondaires: {e}")
            return None

    def update_statut_comptable(self, ecriture_id: int, user_id: int, statut_comptable: str) -> Tuple[bool, str]:
        """Met à jour le statut comptable d'une transaction"""
        try:
            with self.db.get_cursor() as cursor:
                ecritures_secondaires = self.get_ecritures_complementaires(ecriture_id, user_id)
                # Vérifier que l'utilisateur peut accéder à cette transaction
                if ecritures_secondaires:
                    query = """
                    UPDATE ecritures_comptables
                    SET statut = %s
                    WHERE (id = %s OR ecriture_principale_id = %s)
                    AND utilisateur_id = %s
                    """
                    cursor.execute(query, (statut_comptable, ecriture_id, ecriture_id, user_id))
                else:
                    query = """
                    UPDATE ecritures_comptables
                    SET statut = %s
                    WHERE id = %s AND utilisateur_id = %s
                    """
                    cursor.execute(query, (statut_comptable, ecriture_id, user_id))
            return True, "Statut comptable mis à jour avec succès"
        except Exception as e:
            logger.error(f"Erreur mise à jour statut comptable: {e}")
            return False, f"Erreur: {str(e)}"

    def get_solde_tva_par_periode(self, user_id: int, date_debut: str, date_fin: str) -> Dict:
        """Calcule le solde TVA pour une période donnée"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT
                        SUM(CASE WHEN e.type_ecriture = 'recette' THEN e.montant ELSE 0 END) as tva_collectee,
                        SUM(CASE WHEN e.type_ecriture = 'depense' THEN e.montant ELSE 0 END) as tva_deductible,
                        (SUM(CASE WHEN e.type_ecriture = 'recette' THEN e.montant ELSE 0 END) -
                        SUM(CASE WHEN e.type_ecriture = 'depense' THEN e.montant ELSE 0 END)) as solde_tva
                    FROM ecritures_comptables e
                    JOIN categories_comptables c ON e.categorie_id = c.id
                    WHERE e.utilisateur_id = %s
                    AND e.date_ecriture BETWEEN %s AND %s
                    AND e.statut = 'validée'
                    AND c.type_compte = 'TVA'  -- Supposant que vous avez une catégorie TVA
                """, (user_id, date_debut, date_fin))

                return cursor.fetchone() or {'tva_collectee': 0, 'tva_deductible': 0, 'solde_tva': 0}
        except Exception as e:
            logger.error(f"Erreur get_solde_tva_par_periode: {e}")
            return {'tva_collectee': 0, 'tva_deductible': 0, 'solde_tva': 0}

    def _create_ecriture_liee(self, cursor, data: Dict):
        """Méthode interne pour créer une écriture liée"""
        try:
            query = """
            INSERT INTO ecritures_comptables(
                date_ecriture, compte_bancaire_id, categorie_id, montant, montant_htva, devise,
                description, reference, type_ecriture, tva_taux, tva_montant,
                utilisateur_id, justificatif_url, statut, id_contact,
                ecriture_principale_id, type_ecriture_comptable
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                data['date_ecriture'],
                data['compte_bancaire_id'],
                data['categorie_id'],
                data['montant'],
                data['montant_htva'],
                data.get('devise', 'CHF'),
                data.get('description', ''),
                data.get('reference', ''),
                data['type_ecriture'],
                data.get('tva_taux'),
                data.get('tva_montant'),
                data['utilisateur_id'],
                data.get('justificatif_url'),
                data.get('statut', 'pending'),
                data.get('id_contact'),
                data.get('ecriture_principale_id'),
                data.get('type_ecriture_comptable', 'complementaire')
            )
            cursor.execute(query, values)
            logger.info(f"Écriture liée créée avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de la création de l'écriture liée: {e}")
            raise

    # *** MÉTHODE POUR RÉCUPÉRER LES ÉCRITURES COMPLÉMENTAIRES D'UNE ÉCRITURE PRINCIPALE ***
    def get_ecritures_complementaires(self, ecriture_principale_id: int, user_id: int) -> List[Dict]:
        """
        Récupère les écritures complémentaires directement liées à une écriture principale spécifique.
        """
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                           cb.nom_compte as compte_bancaire_nom
                    FROM ecritures_comptables e
                    LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                    LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                    WHERE e.ecriture_principale_id = %s AND e.utilisateur_id = %s
                    AND e.type_ecriture_comptable = 'complementaire' -- S'assurer que c'est une complémentaire
                """, (ecriture_principale_id, user_id))
                ecritures = cursor.fetchall()
                return ecritures
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des écritures complémentaires: {e}")
            return []

    # *** MÉTHODE POUR RÉCUPÉRER L'ÉCRITURE PRINCIPALE D'UNE ÉCRITURE COMPLÉMENTAIRE ***
    def get_ecriture_principale(self, ecriture_complementaire_id: int, user_id: int) -> Optional[Dict]:
        """
        Récupère l'écriture principale liée à une écriture complémentaire spécifique.
        """
        try:
            with self.db.get_cursor() as cursor:
                # Version simplifiée et optimisée en une seule requête
                cursor.execute("""
                    SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                        cb.nom_compte as compte_bancaire_nom
                    FROM ecritures_comptables e
                    LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                    LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                    WHERE e.id = (
                        SELECT ecriture_principale_id
                        FROM ecritures_comptables
                        WHERE id = %s AND utilisateur_id = %s AND type_ecriture_comptable = 'complementaire'
                    )
                    AND e.utilisateur_id = %s
                """, (ecriture_complementaire_id, user_id, user_id))

                return cursor.fetchone()

        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'écriture principale: {e}")
            return None
    # *** MÉTHODE POUR METTRE À JOUR UNE ÉCRITURE PRINCIPALE ET SES COMPLÉMENTAIRES ***
    def update_principale_et_complementaires(self, ecriture_principale_id: int, user_id: int, **kwargs) -> Tuple[bool, str]:
        """
        Met à jour une écriture principale et éventuellement ses écritures complémentaires
        en fonction des modifications (par exemple, recalcul de la TVA si le montant change).
        """
        try:
            with self.db.get_cursor() as cursor:
                # 1. Récupérer l'écriture principale avant modification
                cursor.execute("""
                    SELECT * FROM ecritures_comptables
                    WHERE id = %s AND utilisateur_id = %s AND type_ecriture_comptable = 'principale'
                """, (ecriture_principale_id, user_id))
                ecriture_principale_avant = cursor.fetchone()
                if not ecriture_principale_avant:
                    return False, "Écriture principale non trouvée ou non autorisée"

                # 2. Mettre à jour l'écriture principale
                champs = []
                valeurs = []
                for champ, valeur in kwargs.items():
                    if valeur is not None and champ not in ['id', 'utilisateur_id', 'ecriture_principale_id', 'type_ecriture_comptable']:
                        champs.append(f"{champ} = %s")
                        valeurs.append(valeur)

                if not champs:
                    return False, "Aucune modification valide spécifiée pour l'écriture principale"

                # Ajouter les conditions pour la mise à jour
                valeurs.extend([ecriture_principale_id, user_id])
                query_update_principale = f"""
                    UPDATE ecritures_comptables
                    SET {', '.join(champs)}
                    WHERE id = %s AND utilisateur_id = %s AND type_ecriture_comptable = 'principale'
                """
                cursor.execute(query_update_principale, valeurs)
                if cursor.rowcount == 0:
                    return False, "Aucune ligne mise à jour pour l'écriture principale (vérifiez les permissions ou l'existence)"

                # 3. Vérifier si des champs impactant les écritures complémentaires ont changé
                montant_change = 'montant' in kwargs and kwargs['montant'] != ecriture_principale_avant['montant']
                tva_taux_change = 'tva_taux' in kwargs and kwargs['tva_taux'] != ecriture_principale_avant['tva_taux']

                if montant_change or tva_taux_change:
                    # 4. Récupérer les écritures complémentaires
                    ecritures_complementaires = self.get_ecritures_complementaires(ecriture_principale_id, user_id)

                    # 5. Mettre à jour chaque écriture complémentaire
                    for ecriture_comp in ecritures_complementaires:
                        # Exemple de logique de mise à jour : recalculer la TVA si le montant principal change
                        # Cela dépend de votre logique métier précise.
                        # Ici, on suppose que le montant de la complémentaire (TVA) doit être recalculé.
                        ancien_montant_principal = ecriture_principale_avant['montant']
                        ancien_taux_tva = ecriture_principale_avant['tva_taux'] or 0
                        nouveau_montant_principal = kwargs.get('montant', ancien_montant_principal)
                        nouveau_taux_tva = kwargs.get('tva_taux', ancien_taux_tva) or 0

                        # Exemple de recalcul de la TVA
                        # ATTENTION : La logique réelle peut être plus complexe (TVA sur le prix HT, etc.)
                        # Ici, on fait un recalcul simple basé sur le nouveau montant et le nouveau taux
                        # par rapport à l'ancien. Il faut affiner selon votre besoin.
                        # Ancienne TVA = ancien_montant_principal * (ancien_taux_tva / 100)
                        # Nouvelle TVA = nouveau_montant_principal * (nouveau_taux_tva / 100)
                        if montant_change or tva_taux_change:
                            ancien_montant_tva = ecriture_comp['montant'] # Ancien montant de la complémentaire (TVA)
                            ancienne_base = ancien_montant_principal
                            nouveau_montant_tva = (nouveau_montant_principal * nouveau_taux_tva) / 100.0
                            # Si ancien_taux_tva est 0, on ne peut pas recalculer proprement, on garde l'ancien montant_tva ou on le met à 0.
                            # Une logique plus robuste est nécessaire ici.
                            # Pour l'exemple, on met à jour avec le nouveau calcul si les deux changent ou si le taux change.
                            # Si seul le montant change et que le taux est inchangé, on recalcule proportionnellement.
                            if tva_taux_change:
                                # Recalcul complet
                                nouveau_montant_tva_calc = (nouveau_montant_principal * nouveau_taux_tva) / 100.0
                            elif montant_change and ancien_taux_tva != 0:
                                # Recalcul proportionnel si le taux n'a pas changé
                                nouveau_montant_tva_calc = (ancien_montant_tva / ancienne_base) * nouveau_montant_principal
                            else:
                                # Aucun changement de taux, montant changé mais taux à 0, donc TVA devrait rester à 0
                                nouveau_montant_tva_calc = 0.0

                            cursor.execute("""
                                UPDATE ecritures_comptables
                                SET montant = %s, montant_htva = %s -- Mettre à jour le montant de la complémentaire
                                WHERE id = %s AND utilisateur_id = %s AND type_ecriture_comptable = 'complementaire'
                            """, (nouveau_montant_tva_calc, nouveau_montant_tva_calc, ecriture_comp['id'], user_id))
                            logger.info(f"Écriture complémentaire {ecriture_comp['id']} mise à jour en fonction de la modification de la principale {ecriture_principale_id}.")

                return True, "Écriture principale mise à jour, complémentaires recalculées si nécessaire."
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour de l'écriture (principale ou complémentaire): {e}")
            return False, f"Erreur: {str(e)}"

    def update(self, ecriture_id: int, data: Dict) -> bool:
        # Validation du lien catégorie ↔ plan comptable du compte
        try:
            if data.get('id_contact'):
                if not self._is_categorie_valid_for_contact(
                    data['id_contact'],
                    data['categorie_id'],
                    data['utilisateur_id']
                ):
                    logger.warning("Catégorie non autorisée pour ce contact.")
                    return False
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE ecritures_comptables
                SET date_ecriture = %s, compte_bancaire_id = %s, categorie_id = %s,
                    montant = %s, montant_htva = %s, devise = %s, description = %s, id_contact = %s, reference = %s,
                    type_ecriture = %s, tva_taux = %s, tva_montant = %s,
                    justificatif_url = %s, statut = %s
                WHERE id = %s AND utilisateur_id = %s
                """
                values = (
                    data['date_ecriture'],
                    data['compte_bancaire_id'],
                    data['categorie_id'],
                    data['montant'],
                    data['montant_htva'],
                    data.get('devise', 'CHF'),
                    data.get('description', ''),
                    data.get('id_contact'),
                    data.get('reference', ''),
                    data['type_ecriture'],
                    data.get('tva_taux'),
                    data.get('tva_montant'),
                    data.get('justificatif_url'),
                    data.get('statut', 'pending'),
                    ecriture_id,
                    data['utilisateur_id']
                )

                cursor.execute(query, values)
                return cursor.rowcount > 0
            return True
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour de l'écriture comptable: {e}")
            return False

    def delete_hard(self, ecriture_id: int, user_id: int) -> Tuple[bool, str]:
        """
        Supprime une écriture comptable après avoir délié sa transaction.
        Gère également la suppression des écritures secondaires associées.

        Args:
            ecriture_id: ID de l'écriture à supprimer
            user_id: ID de l'utilisateur pour vérification de propriété

        Returns:
            Tuple (succès, message)
        """
        try:
            with self.db.get_cursor() as cursor:
                # 1. Vérifier que l'écriture existe et appartient à l'utilisateur
                cursor.execute(
                    "SELECT id, transaction_id, type_ecriture_comptable, ecriture_principale_id FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                    (ecriture_id, user_id)
                )
                ecriture = cursor.fetchone()

                if not ecriture:
                    return False, "Écriture non trouvée ou non autorisée"

                # 2. Délier la transaction si elle existe
                if ecriture['transaction_id']:
                    cursor.execute(
                        "UPDATE ecritures_comptables SET transaction_id = NULL WHERE id = %s",
                        (ecriture_id,)
                    )
                    logger.info(f"Écriture {ecriture_id} déliée de la transaction {ecriture['transaction_id']}")

                # 3. Gestion des écritures secondaires
                ecritures_secondaires_ids = []

                if ecriture['type_ecriture_comptable'] == 'principale':
                    # Si c'est une écriture principale, récupérer ses écritures secondaires
                    secondaires = self.get_ecritures_complementaires(ecriture_id, user_id)
                    ecritures_secondaires_ids = [sec['id'] for sec in secondaires]
                elif ecriture.get('ecriture_principale_id'):
                    # Si c'est une écriture secondaire, on peut aussi supprimer la principale si souhaité
                    # Pour l'instant, on ne supprime que la secondaire
                    pass

                # 4. Supprimer d'abord les écritures secondaires (si elles existent)
                for sec_id in ecritures_secondaires_ids:
                    cursor.execute(
                        "DELETE FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                        (sec_id, user_id)
                    )
                    if cursor.rowcount > 0:
                        logger.info(f"Écriture secondaire {sec_id} supprimée avec succès")

                # 5. Supprimer l'écriture principale
                cursor.execute(
                    "DELETE FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                    (ecriture_id, user_id)
                )

                if cursor.rowcount > 0:
                    message = f"Écriture {ecriture_id} supprimée avec succès"
                    if ecritures_secondaires_ids:
                        message += f" ainsi que {len(ecritures_secondaires_ids)} écriture(s) secondaire(s)"
                    logger.info(message)
                    return True, message
                else:
                    return False, "Erreur lors de la suppression de l'écriture"

        except Exception as e:
            logger.error(f"Erreur lors de la suppression de l'écriture {ecriture_id}: {e}")
            return False, f"Erreur lors de la suppression: {str(e)}"

    def delete_soft(self, ecriture_id: int, user_id: int, soft_delete: bool = True) -> Tuple[bool, str]:
        """
        Supprime une écriture comptable (soft delete par défaut).
        Gère également le soft delete des écritures secondaires associées.
        Args:
            ecriture_id: ID de l'écriture à supprimer
            user_id: ID de l'utilisateur pour vérification de propriété
            soft_delete: Si True, marque comme supprimée au lieu de supprimer définitivement
        Returns:
            Tuple (succès, message)
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que l'écriture existe et appartient à l'utilisateur
                cursor.execute(
                    "SELECT id, transaction_id, type_ecriture_comptable, ecriture_principale_id FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                    (ecriture_id, user_id)
                )
                ecriture = cursor.fetchone()

                if not ecriture:
                    return False, "Écriture non trouvée ou non autorisée"

                # Délier la transaction si elle existe
                if ecriture['transaction_id']:
                    cursor.execute(
                        "UPDATE ecritures_comptables SET transaction_id = NULL WHERE id = %s",
                        (ecriture_id,)
                    )
                    logger.info(f"Écriture {ecriture_id} déliée de la transaction {ecriture['transaction_id']}")

                # Gestion des écritures secondaires
                ecritures_secondaires_ids = []

                if ecriture['type_ecriture_comptable'] == 'principale':
                    # Si c'est une écriture principale, récupérer ses écritures secondaires
                    secondaires = self.get_ecritures_complementaires(ecriture_id, user_id)
                    ecritures_secondaires_ids = [sec['id'] for sec in secondaires]
                elif ecriture.get('ecriture_principale_id'):
                    # Si c'est une écriture secondaire, on peut aussi soft delete la principale si souhaité
                    pass

                if soft_delete:
                    # SOFT DELETE: marquer comme supprimée l'écriture principale et ses secondaires
                    success_count = 0

                    # Marquer les écritures secondaires d'abord
                    for sec_id in ecritures_secondaires_ids:
                        cursor.execute("""
                            UPDATE ecritures_comptables
                            SET statut = 'supprimee', date_suppression = NOW()
                            WHERE id = %s AND utilisateur_id = %s
                        """, (sec_id, user_id))
                        if cursor.rowcount > 0:
                            success_count += 1
                            logger.info(f"Écriture secondaire {sec_id} marquée comme supprimée")

                    # Marquer l'écriture principale
                    cursor.execute("""
                        UPDATE ecritures_comptables
                        SET statut = 'supprimee', date_suppression = NOW()
                        WHERE id = %s AND utilisateur_id = %s
                    """, (ecriture_id, user_id))

                    if cursor.rowcount > 0:
                        success_count += 1
                        logger.info(f"Écriture {ecriture_id} marquée comme supprimée")

                    if success_count > 0:
                        message = f"Écriture {ecriture_id} marquée comme supprimée"
                        if ecritures_secondaires_ids:
                            message += f" ainsi que {len(ecritures_secondaires_ids)} écriture(s) secondaire(s)"
                        return True, message
                    else:
                        return False, "Erreur lors du marquage des écritures comme supprimées"

                else:
                    # HARD DELETE: suppression définitive
                    # Supprimer d'abord les écritures secondaires
                    for sec_id in ecritures_secondaires_ids:
                        cursor.execute(
                            "DELETE FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                            (sec_id, user_id)
                        )
                        if cursor.rowcount > 0:
                            logger.info(f"Écriture secondaire {sec_id} supprimée définitivement")

                    # Supprimer l'écriture principale
                    cursor.execute(
                        "DELETE FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                        (ecriture_id, user_id)
                    )

                    if cursor.rowcount > 0:
                        message = f"Écriture {ecriture_id} supprimée définitivement"
                        if ecritures_secondaires_ids:
                            message += f" ainsi que {len(ecritures_secondaires_ids)} écriture(s) secondaire(s)"
                        logger.info(message)
                        return True, message
                    else:
                        return False, "Erreur lors de la suppression de l'écriture"

        except Exception as e:
            logger.error(f"Erreur lors de la suppression de l'écriture {ecriture_id}: {e}")
            return False, f"Erreur lors de la suppression: {str(e)}"

    def get_by_id(self, ecriture_id: int) -> Optional[Dict]:
        """Récupère une écriture par son ID"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                cb.nom_compte as compte_bancaire_nom
                FROM ecritures_comptables e
                LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                WHERE e.id = %s
                """
                cursor.execute(query, (ecriture_id,))
                ecriture = cursor.fetchone()
            return ecriture
        except Error as e:
            logger.error(f"Erreur lors de la récupération de l'écriture comptable: {e}")
            return None

    def get_by_compte_bancaire(self, compte_id: int, user_id: int,
                            date_from: str = None, date_to: str = None,
                            limit: int = 100, statut: str = None) -> List[Dict]:
        """Récupère les écritures d'un compte bancaire avec filtrage par statut"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom
                FROM ecritures_comptables e
                LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                WHERE e.compte_bancaire_id = %s AND e.utilisateur_id = %s
                """
                params = [compte_id, user_id]

                if statut:
                    query += " AND e.statut = %s"
                    params.append(statut)

                if date_from:
                    query += " AND e.date_ecriture >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND e.date_ecriture <= %s"
                    params.append(date_to)

                query += " ORDER BY e.date_ecriture DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, tuple(params))
                ecritures = cursor.fetchall()
            return ecritures
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures: {e}")
            return []

    def get_ecritures_non_synchronisees(self, compte_id: int, user_id: int):
        return self.get_by_compte_bancaire(
            compte_id=compte_id,
            user_id=user_id,
            date_from=None,
            date_to=None,
            limit=100
        )

    def get_by_categorie(self, categorie_id: int, user_id: int,
                        date_from: str = None, date_to: str = None,
                        statut: str = None) -> List[Dict]:
        """Récupère les écritures d'une catégorie avec filtrage par statut"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, cb.nom_compte as compte_bancaire_nom
                FROM ecritures_comptables e
                LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                WHERE e.categorie_id = %s AND e.utilisateur_id = %s
                """
                params = [categorie_id, user_id]

                if statut:
                    query += " AND e.statut = %s"
                    params.append(statut)

                if date_from:
                    query += " AND e.date_ecriture >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND e.date_ecriture <= %s"
                    params.append(date_to)

                query += " ORDER BY e.date_ecriture DESC"

                cursor.execute(query, tuple(params))
                ecritures = cursor.fetchall()
            return ecritures
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures par catégorie: {e}")
            return []

    def get_stats_by_categorie(self, user_id: int, date_from: str = None,
                          date_to: str = None, statut: str = 'validée') -> List[Dict]:
        """Récupère les statistiques par catégorie avec filtrage par statut"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    c.id as categorie_id,
                    c.numero as categorie_numero,
                    c.nom as categorie_nom,
                    c.type_compte as categorie_type,
                    SUM(CASE WHEN e.type_ecriture = 'depense' AND e.statut = %s THEN e.montant ELSE 0 END) as total_depenses,
                    SUM(CASE WHEN e.type_ecriture = 'depense' AND e.statut = %s THEN e.montant_htva ELSE 0 END) as total_depenses_htva,
                    SUM(CASE WHEN e.type_ecriture = 'recette' AND e.statut = %s THEN e.montant ELSE 0 END) as total_recettes,
                    SUM(CASE WHEN e.type_ecriture = 'recette' AND e.statut = %s THEN e.montant_htva ELSE 0 END) as total_recettes_htva,
                    COUNT(e.id) as nb_ecritures
                FROM categories_comptables c
                LEFT JOIN ecritures_comptables e ON c.id = e.categorie_id AND e.utilisateur_id = %s
                """
                # Il y a 5 placeholders dans la requête ci-dessus : 4 pour 'statut', 1 pour 'user_id'.
                # Donc params doit contenir 5 valeurs initiales.
                params = [statut, statut, statut, statut, user_id] # Valeurs pour les 4 'statut' et 1 'user_id'

                if date_from:
                    query += " AND e.date_ecriture >= %s"
                    params.append(date_from) # Valeur 6
                if date_to:
                    query += " AND e.date_ecriture <= %s"
                    params.append(date_to) # Valeur 7

                query += """
                WHERE c.actif = TRUE
                GROUP BY c.id, c.numero, c.nom, c.type_compte
                ORDER BY c.numero
                """

                cursor.execute(query, tuple(params)) # Le nombre de placeholders et de paramètres correspond maintenant.
                stats = cursor.fetchall()
            return stats
        except Error as e:
            logger.error(f"Erreur lors de la récupération des statistiques par catégorie: {e}")
            return []

    def _validate_date(date_str: str) -> bool:
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def _fetch_ecritures_by_type(self, user_id: int, date_from: str, date_to: str, type_ecriture: str) -> List[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT
                    c.numero,
                    c.nom AS categorie_nom,
                    c.id AS categorie_id,
                    COUNT(e.id) AS nombre_ecritures,
                    SUM(COALESCE(e.montant, 0)) AS montant,
                    SUM(COALESCE(e.montant_htva, 0)) AS montant_htva
                FROM ecritures_comptables e
                JOIN categories_comptables c ON e.categorie_id = c.id
                WHERE e.utilisateur_id = %s
                AND e.date_ecriture BETWEEN %s AND %s
                AND e.type_ecriture = %s
                AND e.statut = 'validée'
                GROUP BY c.id, c.numero, c.nom
                ORDER BY c.numero
            """, (user_id, date_from, date_to, type_ecriture))
            return cursor.fetchall()

    def get_compte_de_resultat(self, user_id: int, date_from: str, date_to: str) -> Dict:
        if not (self._validate_date(date_from) and self._validate_date(date_to)):
            logger.error("Format de date invalide dans get_compte_de_resultat")
            return {}

        try:
            produits = self._fetch_ecritures_by_type(user_id, date_from, date_to, 'recette')
            charges = self._fetch_ecritures_by_type(user_id, date_from, date_to, 'depense')

            total_produits = sum(p['montant'] for p in produits)
            total_produits_htva = sum(p['montant_htva'] for p in produits)
            total_charges = sum(c['montant'] for c in charges)
            total_charges_htva = sum(c['montant_htva'] for c in charges)
            resultat = total_produits - total_charges

            return {
                'produits': produits,
                'charges': charges,
                'total_produits': total_produits,
                'total_produits_htva': total_produits_htva,
                'total_charges': total_charges,
                'total_charges_htva': total_charges_htva,
                'resultat': resultat,
                'date_from': date_from,
                'date_to': date_to
            }
        except Exception as e:
            logger.error(f"Erreur génération compte de résultat: {e}")
            return {}

    def get_bilan(self, user_id: int, date_bilan: str) -> Dict:
        """
        Génère le bilan à une date donnée (solde cumulé jusqu'à date_bilan inclus).
        """
        if not self._validate_date(date_bilan):
            logger.error("Format de date invalide pour le bilan")
            return {}

        try:
            with self.db.get_cursor() as cursor:
                # Récupérer TOUTES les écritures validées jusqu'à la date du bilan
                # On les regroupe par catégorie pour calculer les soldes
                cursor.execute("""
                    SELECT
                        c.id AS categorie_id,
                        c.numero,
                        c.nom AS categorie_nom,
                        c.type_compte,
                        SUM(
                            CASE
                                WHEN e.type_ecriture = 'recette' THEN e.montant
                                WHEN e.type_ecriture = 'depense' THEN -e.montant
                                ELSE 0
                            END
                        ) AS solde
                    FROM categories_comptables c
                    LEFT JOIN ecritures_comptables e
                        ON c.id = e.categorie_id
                        AND e.utilisateur_id = %s
                        AND e.date_ecriture <= %s
                        AND e.statut = 'validée'
                    WHERE c.utilisateur_id = %s
                    AND c.actif = TRUE
                    AND c.type_compte IN ('Actif', 'Passif', 'Capitaux propres')
                    GROUP BY c.id, c.numero, c.nom, c.type_compte
                    ORDER BY c.numero
                """, (user_id, date_bilan, user_id))

                lignes = cursor.fetchall()

            # Répartir entre actif, passif, capitaux
            actif = []
            passif = []
            capitaux = []

            total_actif = 0.0
            total_passif = 0.0
            total_capitaux = 0.0

            for ligne in lignes:
                solde = float(ligne['solde'] or 0.0)
                item = {
                    'categorie_id': ligne['categorie_id'],
                    'numero': ligne['numero'],
                    'nom': ligne['categorie_nom'],
                    'solde': solde
                }

                if ligne['type_compte'] == 'Actif':
                    actif.append(item)
                    total_actif += solde
                elif ligne['type_compte'] == 'Passif':
                    passif.append(item)
                    total_passif += solde
                elif ligne['type_compte'] in ('Capitaux propres', 'Capital', 'Fonds propres'):
                    capitaux.append(item)
                    total_capitaux += solde

            total_passif_et_capitaux = total_passif + total_capitaux
            écart = total_actif - total_passif_et_capitaux

            return {
                'actif': actif,
                'passif': passif,
                'capitaux': capitaux,
                'total_actif': total_actif,
                'total_passif': total_passif,
                'total_capitaux': total_capitaux,
                'total_passif_et_capitaux': total_passif_et_capitaux,
                'écart': écart,  # doit être ~0
                'date_bilan': date_bilan
            }

        except Exception as e:
            logger.error(f"Erreur génération bilan: {e}")
            return {}

    def get_ecritures_by_categorie_period(self, user_id: int, type_categorie: str = None,
                                            categorie_id: int = None, date_from: str = None,
                                            date_to: str = None, statut: str = 'validée') -> Tuple[List[Dict], float, str]:
            """
            Récupère les écritures par catégorie et période avec calcul du total et génération du titre

            Returns:
                Tuple: (ecritures, total, titre)
            """
            try:
                with self.db.get_cursor() as cursor:
                    # Construire la requête avec une jointure LEFT pour les contacts
                    query = """
                        SELECT
                            e.id,
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
                        AND e.statut = %s
                    """
                    params = [user_id, date_from, date_to, statut]

                    if type_categorie == 'produit':
                        query += " AND c.type_compte = 'Revenus' OR c.type_compte = 'Actif'"
                    elif type_categorie == 'charge':
                        query += " AND c.type_compte = 'Charge' OR c.type_compte = 'Passif'"

                    if categorie_id and categorie_id != 'all':
                        query += " AND e.categorie_id = %s"
                        params.append(int(categorie_id))

                    query += " ORDER BY e.date_ecriture DESC"
                    cursor.execute(query, tuple(params))
                    ecritures = cursor.fetchall()

                    # Calculer le total
                    total = sum(float(e['montant']) for e in ecritures) if ecritures else 0

                    # Générer le titre
                    titre = self._generate_titre_detail(cursor, type_categorie, categorie_id, ecritures, date_from[:4])

                    return ecritures, total, titre

            except Exception as e:
                logger.error(f"Erreur lors de la récupération des écritures par catégorie: {e}")
                return [], 0, ""

    def _generate_titre_detail(self, cursor, type_categorie: str, categorie_id: str,
                            ecritures: List[Dict], annee: str) -> str:
        """Génère le titre pour la page de détail"""
        if categorie_id == 'all':
            return f"Tous les {type_categorie}s - {annee}"
        else:
            # Récupérer le nom de la catégorie depuis la première écriture ou depuis la base
            if ecritures:
                categorie_nom = ecritures[0]['categorie_nom']
                categorie_numero = ecritures[0]['categorie_numero']
            else:
                # Si pas d'écritures, récupérer le nom de la catégorie directement
                cursor.execute("SELECT nom, numero FROM categories_comptables WHERE id = %s", (int(categorie_id),))
                categorie = cursor.fetchone()
                categorie_nom = categorie['nom'] if categorie else "Catégorie inconnue"
                categorie_numero = categorie['numero'] if categorie else "Numéro inconnu"
            return f"{categorie_numero} : {categorie_nom} - {annee}"

    def update_statut(self, ecriture_id: int, user_id: int, statut: str) -> bool:
        """Met à jour uniquement le statut d'une écriture"""
        try:
            with self.db.get_cursor() as cursor:
                secondary_ecriture = self.get_ecritures_complementaires(ecriture_id, user_id)
                if secondary_ecriture:
                    query = """
                    UPDATE ecritures_comptables
                    SET statut = %s
                    WHERE (id = %s OR ecriture_principale_id = %s)
                    AND utilisateur_id = %s
                    """
                    cursor.execute(query, (statut, ecriture_id, ecriture_id, user_id))
                else:
                    # Mettre à jour le statut de l'écriture principale et de ses complémentaires
                    query = """UPDATE ecritures_comptables
                    SET statut = %s
                    WHERE id = %s
                    AND utilisateur_id = %s"""
                    cursor.execute(query, (statut, ecriture_id, user_id))
            return True
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour du statut: {e}")
            return False

    def get_by_statut(self, user_id: int, statut: str, date_from: str = None,
                  date_to: str = None, limit: int = 100) -> List[Dict]:
        """Récupère les écritures par statut avec filtres optionnels"""
        ecritures = []
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                    cb.nom_compte as compte_bancaire_nom
                FROM ecritures_comptables e
                LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                WHERE e.utilisateur_id = %s AND e.statut = %s
                """

                params = [user_id, statut]

                if date_from:
                    query += " AND e.date_ecriture >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND e.date_ecriture <= %s"
                    params.append(date_to)

                query += " ORDER BY e.date_ecriture DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, tuple(params))
                ecritures = cursor.fetchall()
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures par statut: {e}")

        return ecritures

    def get_statistiques_par_statut(self, user_id: int) -> Dict:
        """Retourne les statistiques regroupées par statut"""
        try:
            with self.db.get_cursor() as cursor:
                # Statistiques par statut
                query = """
                SELECT
                    statut,
                    COUNT(*) as nb_ecritures,
                    SUM(CASE WHEN type_ecriture = 'depense' THEN montant ELSE 0 END) as total_depenses,
                    SUM(CASE WHEN type_ecriture = 'depense' THEN montant_htva ELSE 0 END) as total_depenses_htva,
                    SUM(CASE WHEN type_ecriture = 'recette' THEN montant ELSE 0 END) as total_recettes,
                    SUM(CASE WHEN type_ecriture = 'recette' THEN montant_htva ELSE 0 END) as total_recettes_htva,
                    AVG(CASE WHEN type_ecriture = 'depense' THEN montant ELSE NULL END) as moyenne_depenses,
                    AVG(CASE WHEN type_ecriture = 'depense' THEN montant_htva ELSE NULL END) as moyenne_depenses_htva,
                    AVG(CASE WHEN type_ecriture = 'recette' THEN montant ELSE NULL END) as moyenne_recettes,
                    AVG(CASE WHEN type_ecriture = 'recette' THEN montant_htva ELSE NULL END) as moyenne_recettes_htva
                FROM ecritures_comptables
                WHERE utilisateur_id = %s
                GROUP BY statut
                ORDER BY statut
                """
                cursor.execute(query, (user_id,))
                stats_par_statut = cursor.fetchall()

                # Dernières écritures par statut
                cursor.execute("""
                SELECT statut, COUNT(*) as nb_ecritures_30j
                FROM ecritures_comptables
                WHERE utilisateur_id = %s
                AND date_ecriture >= DATE_SUB(NOW(), INTERVAL 30 DAY)
                GROUP BY statut
                """, (user_id,))
                stats_recentes = cursor.fetchall()

            return {
                'statistiques_par_statut': stats_par_statut,
                'statistiques_recentes': stats_recentes
            }

        except Error as e:
            logger.error(f"Erreur lors du calcul des statistiques par statut: {e}")
            return {}

    def get_alertes_statut(self, user_id: int) -> List[Dict]:
        """Retourne les alertes concernant les statuts"""
        try:
            with self.db.get_cursor() as cursor:
                # Écritures en attente depuis plus de 7 jours
                query = """
                SELECT
                    COUNT(*) as nb_ecritures_attente,
                    MIN(date_ecriture) as plus_ancienne_attente,
                    DATEDIFF(NOW(), MIN(date_ecriture)) as jours_attente
                FROM ecritures_comptables
                WHERE utilisateur_id = %s
                AND statut = 'pending'
                AND date_ecriture <= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """
                cursor.execute(query, (user_id,))
                alertes = cursor.fetchall()

                # Écritures rejetées récentes
                cursor.execute("""
                SELECT COUNT(*) as nb_ecritures_rejetees_7j
                FROM ecritures_comptables
                WHERE utilisateur_id = %s
                AND statut = 'rejetée'
                AND date_ecriture >= DATE_SUB(NOW(), INTERVAL 7 DAY)
                """, (user_id,))
                rejetees_recentes = cursor.fetchone()

            resultat = []
            if alertes and alertes[0]['nb_ecritures_attente'] > 0:
                resultat.append({
                    'type': 'attente_longue',
                    'message': f"{alertes[0]['nb_ecritures_attente']} écriture(s) en attente depuis plus de 7 jours",
                    'niveau': 'warning'
                })

            if rejetees_recentes and rejetees_recentes['nb_ecritures_rejetees_7j'] > 0:
                resultat.append({
                    'type': 'rejet_recent',
                    'message': f"{rejetees_recentes['nb_ecritures_rejetees_7j']} écriture(s) rejetée(s) cette semaine",
                    'niveau': 'danger'
                })

            return resultat

        except Error as e:
            logger.error(f"Erreur lors de la récupération des alertes: {e}")
            return []

    def get_indicateurs_performance(self, user_id: int, statut: str = 'validée') -> Dict:
        """Retourne des indicateurs de performance financière"""
        try:
            with self.db.get_cursor() as cursor:
                # Taux de validation
                cursor.execute("""
                SELECT
                    COUNT(*) as total_ecritures,
                    SUM(CASE WHEN statut = 'validée' THEN 1 ELSE 0 END) as ecritures_validees,
                    SUM(CASE WHEN statut = 'pending' THEN 1 ELSE 0 END) as ecritures_attente,
                    SUM(CASE WHEN statut = 'rejetée' THEN 1 ELSE 0 END) as ecritures_rejetees,
                    ROUND((SUM(CASE WHEN statut = 'validée' THEN 1 ELSE 0 END) / COUNT(*) * 100), 2) as taux_validation
                FROM ecritures_comptables
                WHERE utilisateur_id = %s
                """, (user_id,))
                taux_validation = cursor.fetchone()

                # Temps moyen de traitement
                cursor.execute("""
                SELECT
                    AVG(DATEDIFF(date_validation, date_ecriture)) as temps_traitement_moyen
                FROM ecritures_comptables
                WHERE utilisateur_id = %s
                AND statut = 'validée'
                AND date_validation IS NOT NULL
                """, (user_id,))
                temps_traitement = cursor.fetchone()

            return {
                'taux_validation': taux_validation,
                'temps_traitement_moyen': temps_traitement['temps_traitement_moyen'] if temps_traitement else 0,
                'statut_reference': statut
            }

        except Error as e:
            logger.error(f"Erreur lors du calcul des indicateurs de performance: {e}")
            return {}

    def get_annees_disponibles(self, user_id):
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT DISTINCT YEAR(date_ecriture) AS annee
                    FROM ecritures_comptables
                    WHERE utilisateur_id = %s
                    ORDER BY annee DESC
                """
                cursor.execute(query, (user_id,))
                annees = [row['annee'] for row in cursor.fetchall()]
                return annees
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des années disponibles : {e}")
            return []

    def get_all(self, user_id: int, date_from: str = None, date_to: str = None, limit: int = 100) -> List[Dict]:
        """Récupère toutes les écritures avec filtres optionnels"""
        ecritures = []
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                    cb.nom_compte as compte_bancaire_nom
                FROM ecritures_comptables e
                LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                WHERE e.utilisateur_id = %s
                """
                params = [user_id]

                if date_from:
                    query += " AND e.date_ecriture >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND e.date_ecriture <= %s"
                    params.append(date_to)

                query += " ORDER BY e.date_ecriture DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, tuple(params))
                ecritures = cursor.fetchall()

                return ecritures
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures: {e}")
            return []

    def get_with_filters(self, user_id: int, date_from: str = None, date_to: str = None,
                        statut: str = None, id_contact: int = None, compte_id: int = None,
                        categorie_id: int = None, type_ecriture: str = None, type_ecriture_comptable: str = None,
                        limit: int = 100) -> List[Dict]:
        """Récupère les écritures avec tous les filtres combinés"""
        ecritures = []
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                    cb.nom_compte as compte_bancaire_nom
                FROM ecritures_comptables e
                LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                WHERE e.utilisateur_id = %s
                """
                params = [user_id]

                if date_from:
                    query += " AND e.date_ecriture >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND e.date_ecriture <= %s"
                    params.append(date_to)
                if statut:
                    query += " AND e.statut = %s"
                    params.append(statut)
                if id_contact:
                    query += " AND e.id_contact = %s"
                    params.append(id_contact)
                if compte_id:
                    query += " AND e.compte_bancaire_id = %s"
                    params.append(compte_id)
                if categorie_id:
                    query += " AND e.categorie_id = %s"
                    params.append(categorie_id)
                if type_ecriture:
                    query += " AND e.type_ecriture = %s"
                    params.append(type_ecriture)
                if type_ecriture_comptable:
                    query += " AND e.type_ecriture_comptable = %s"
                    params.append(type_ecriture_comptable)


                query += " ORDER BY e.date_ecriture DESC LIMIT %s"
                params.append(limit)

                cursor.execute(query, tuple(params))
                ecritures = cursor.fetchall()

                return ecritures
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures avec filtres: {e}")
            return []

    def get_by_user_period(self, user_id, date_from, date_to):
        """Récupère toutes les écritures pour une période donnée"""
        ecritures =[]
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                    cb.nom_compte as compte_bancaire_nom
                FROM ecritures_comptables e
                LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                WHERE e.utilisateur_id = %s AND e.date_ecriture BETWEEN %s AND %s
                ORDER BY e.date_ecriture DESC
                """
                params = [user_id, date_from, date_to]
                cursor.execute(query, tuple(params))
                ecritures = cursor.fetchall()
                return ecritures
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures par période: {e}")
            return []

    def get_by_contact_id(self, contact_id: int, utilisateur_id: int) -> List[Dict]:
        """Récupère toutes les écritures liées à un contact"""
        ecritures = []
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT ec.*, cp.nom_compte
                FROM ecritures_comptables ec
                LEFT JOIN comptes_principaux cp ON ec.compte_bancaire_id = cp.id
                WHERE ec.id_contact = %s AND ec.utilisateur_id = %s
                ORDER BY ec.date_ecriture DESC
                """
                cursor.execute(query, (contact_id, utilisateur_id))
                ecritures = cursor.fetchall()
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures: {e}")
        return ecritures

    def get_synthese_statuts(self, user_id: int, date_from: str, date_to: str) -> Dict:
        """Retourne une synthèse des écritures par statut"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT
                    statut,
                    COUNT(*) as nombre,
                    SUM(CASE WHEN type_ecriture = 'depense' THEN montant ELSE 0 END) as total_depenses,
                    SUM(CASE WHEN type_ecriture = 'depense' THEN montant_htva ELSE 0 END) as total_depenses_htva,
                    SUM(CASE WHEN type_ecriture = 'recette' THEN montant ELSE 0 END) as total_recettes,
                    SUM(CASE WHEN type_ecriture = 'recette' THEN montant_htva ELSE 0 END) as total_recettes_htva
                FROM ecritures_comptables
                WHERE utilisateur_id = %s AND date_ecriture BETWEEN %s AND %s
                GROUP BY statut
                """
                cursor.execute(query, (user_id, date_from, date_to))
                synthese = cursor.fetchall()
                return {
                    'synthese_statuts': synthese,
                    'date_debut': date_from,
                    'date_fin': date_to
                }
        except Error as e:
            logger.error(f"Erreur lors de la récupération de la synthèse des statuts: {e}")
            return {}

    def get_by_contact(self, contact_id: int, user_id: int) -> List[Dict]:
        """Récupère les écritures associées à un contact spécifique"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*, c.numero as categorie_numero, c.nom as categorie_nom,
                    cb.nom_compte as compte_bancaire_nom
                FROM ecritures_comptables e
                LEFT JOIN categories_comptables c ON e.categorie_id = c.id
                LEFT JOIN comptes_principaux cb ON e.compte_bancaire_id = cb.id
                WHERE e.utilisateur_id = %s AND e.id_contact = %s
                ORDER BY e.date_ecriture DESC
                """
                cursor.execute(query, (user_id, contact_id))
                ecritures = cursor.fetchall()
                return ecritures
        except Error as e:
            logger.error(f"Erreur lors de la récupération des écritures par contact: {e}")
            return []

    def link_to_transaction(self, ecriture_id: int, transaction_id: int, user_id: int) -> bool:
        """Lie une écriture comptable à une transaction bancaire"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que l'écriture appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                    (ecriture_id, user_id)
                )
                if not cursor.fetchone():
                    return False

                # Vérifier que la transaction existe et appartient à l'utilisateur
                cursor.execute("""
                    SELECT t.id
                    FROM transactions t
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    WHERE t.id = %s AND (cp.utilisateur_id = %s OR t.utilisateur_id = %s)
                """, (transaction_id, user_id, user_id))
                if not cursor.fetchone():
                    return False

                # Lier l'écriture à la transaction
                cursor.execute(
                    "UPDATE ecritures_comptables SET transaction_id = %s WHERE id = %s",
                    (transaction_id, ecriture_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur lien écriture-transaction : {e}")
            return False

    def get_ecritures_by_transaction(self, transaction_id: int, user_id: int) -> List[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT e.*
                FROM ecritures_comptables e
                WHERE e.transaction_id = %s AND e.utilisateur_id = %s
                ORDER BY e.date_ecriture
            """, (transaction_id, user_id))
            return cursor.fetchall()

    def get_total_ecritures_for_transaction(self, transaction_id: int, user_id: int) -> Decimal:
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT SUM(montant) as total
                FROM ecritures_comptables
                WHERE transaction_id = %s AND utilisateur_id = %s
            """, (transaction_id, user_id))
            row = cursor.fetchone()
            return Decimal(str(row['total'])) if row and row['total'] else Decimal('0')

    def unlink_from_transaction(self, ecriture_id: int, user_id: int) -> bool:
        """
        Supprime le lien entre une écriture comptable et sa transaction associée.
        Ne supprime ni l'écriture, ni la transaction.
        """
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que l'écriture appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                    (ecriture_id, user_id)
                )
                if not cursor.fetchone():
                    return False

                cursor.execute(
                    "UPDATE ecritures_comptables SET transaction_id = NULL WHERE id = %s",
                    (ecriture_id,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur lors du délien de l'écriture {ecriture_id}: {e}")
            return False

    def link_ecriture_to_transaction(self, ecriture_id: int, transaction_id: int, user_id: int) -> bool:
        """
        Lie (ou relie à nouveau) une écriture à une transaction.
        Remplace tout lien existant.
        """
        try:
            with self.db.get_cursor() as cursor:
                # 1. Vérifier que l'écriture existe et appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                    (ecriture_id, user_id)
                )
                if not cursor.fetchone():
                    return False

                # 2. Vérifier que la transaction existe et appartient à l'utilisateur
                cursor.execute("""
                    SELECT t.id
                    FROM transactions t
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    WHERE t.id = %s AND (
                        cp.utilisateur_id = %s
                        OR t.utilisateur_id = %s
                    )
                """, (transaction_id, user_id, user_id))
                if not cursor.fetchone():
                    return False

                # 3. Mettre à jour le lien
                cursor.execute(
                    "UPDATE ecritures_comptables SET transaction_id = %s WHERE id = %s",
                    (transaction_id, ecriture_id)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur lors du lien écriture {ecriture_id} → transaction {transaction_id}: {e}")
            return False

    def unlink_all_ecritures_from_transaction(self, transaction_id: int, user_id: int) -> int:
        """
        Supprime tous les liens entre une transaction et les écritures de l'utilisateur.
        Retourne le nombre d'écritures mises à jour.
        """
        try:
            with self.db.get_cursor() as cursor:
                # S'assurer que la transaction appartient à l'utilisateur
                cursor.execute("""
                    SELECT t.id
                    FROM transactions t
                    LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                    WHERE t.id = %s AND (
                        cp.utilisateur_id = %s
                        OR t.utilisateur_id = %s
                    )
                """, (transaction_id, user_id, user_id))
                if not cursor.fetchone():
                    return 0

                cursor.execute(
                    "UPDATE ecritures_comptables SET transaction_id = NULL WHERE transaction_id = %s AND utilisateur_id = %s",
                    (transaction_id, user_id)
                )
                return cursor.rowcount
        except Exception as e:
            logger.error(f"Erreur lors du délien de toutes les écritures de la transaction {transaction_id}: {e}")
            return 0

    def _is_categorie_valid_for_contact(self, contact_id: int, categorie_id: int, utilisateur_id: int) -> bool:
        if not contact_id:
            return True
        try:
            with self.db.get_cursor() as cursor:
                # Récupérer tous les plans du contact
                cursor.execute("""
                    SELECT plan_id FROM contact_plans
                    WHERE contact_id = %s
                """, (contact_id,))
                plans = cursor.fetchall()
                if not plans:
                    return True  # pas de plan → tout autorisé
                plan_ids = [p['plan_id'] for p in plans]
                # Vérifier si la catégorie est dans l’un de ces plans
                placeholders = ','.join(['%s'] * len(plan_ids))
                cursor.execute(f"""
                    SELECT 1 FROM plan_categorie
                    WHERE plan_id IN ({placeholders}) AND categorie_id = %s
                """, plan_ids + [categorie_id])
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Erreur validation catégorie pour contact {contact_id}: {e}")
            return False

    ## Gestion fichiers


    def _get_file_path(self, filename):
        """Génère le chemin complet du fichier"""
        return os.path.join(self.upload_folder, filename)

    def _generate_filename(self, ecriture_id, original_filename, user_id):
        """
        Génère un nom de fichier unique et significatif
        Format: YYYYMMDD_HHMMSS_ecritureID_userID_contact_extension
        """
        # Récupérer les infos de l'écriture pour le nom
        ecriture = self.get_by_id(ecriture_id)
        date_part = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Partie contact
        contact_part = ""
        if ecriture and ecriture.get('id_contact'):
            contact_part = f"_contact{ecriture['id_contact']}"

        # Extension du fichier
        file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''

        # Nom final
        filename = f"{date_part}_ecriture{ecriture_id}_user{user_id}{contact_part}.{file_extension}"

        return filename

    def _allowed_file(self, filename):
        """Vérifie si le type de fichier est autorisé"""
        allowed_extensions = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in allowed_extensions

    def ajouter_fichier(self, ecriture_id: int, user_id: int, fichier) -> Tuple[bool, str]:
        """Ajoute un fichier joint à une écriture comptable (stockage filesystem)."""
        try:
            # Vérifications de base
            if not fichier or fichier.filename == '':
                return False, "Aucun fichier sélectionné"

            logger.info(f"Tentative d'upload - Fichier: {fichier.filename}, Taille: {fichier.content_length}")

            # Vérifier le dossier d'upload
            logger.info(f"Chemin upload folder: {self.upload_folder}")
            logger.info(f"Dossier existe: {os.path.exists(self.upload_folder)}")

            if not os.path.exists(self.upload_folder):
                try:
                    os.makedirs(self.upload_folder, exist_ok=True)
                    logger.info(f"Dossier créé: {self.upload_folder}")
                except Exception as e:
                    logger.error(f"Erreur création dossier: {e}")
                    return False, f"Erreur création dossier: {str(e)}"

            # Vérifier les permissions
            if not os.access(self.upload_folder, os.W_OK):
                logger.error(f"Pas de permission d'écriture dans: {self.upload_folder}")
                return False, "Pas de permission d'écriture"

            if not self._allowed_file(fichier.filename):
                return False, "Type de fichier non autorisé"

            # Lire le fichier
            fichier_data = fichier.read()
            logger.info(f"Fichier lu - Taille données: {len(fichier_data)} bytes")

            if len(fichier_data) == 0:
                return False, "Fichier vide"

            max_size = 10 * 1024 * 1024
            if len(fichier_data) > max_size:
                return False, "Fichier trop volumineux (max 10MB)"

            with self.db.get_cursor() as cursor:
                # Vérifier que l'écriture appartient à l'utilisateur
                cursor.execute(
                    "SELECT id FROM ecritures_comptables WHERE id = %s AND utilisateur_id = %s",
                    (ecriture_id, user_id)
                )
                if not cursor.fetchone():
                    return False, "Écriture non trouvée ou non autorisée"

                # Générer un nom de fichier unique
                nouveau_nom = self._generate_filename(ecriture_id, fichier.filename, user_id)
                file_path = self._get_file_path(nouveau_nom)

                logger.info(f"Chemin complet du fichier: {file_path}")
                logger.info(f"Nom généré: {nouveau_nom}")

                # Sauvegarder le fichier sur le filesystem
                try:
                    with open(file_path, 'wb') as f:
                        f.write(fichier_data)
                    logger.info(f"Fichier sauvegardé avec succès: {file_path}")

                    # Vérifier que le fichier a bien été écrit
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        logger.info(f"Fichier vérifié - Taille sur disk: {file_size} bytes")
                    else:
                        logger.error("Fichier non trouvé après écriture!")
                        return False, "Erreur lors de l'écriture du fichier"

                except Exception as e:
                    logger.error(f"Erreur écriture fichier: {e}")
                    return False, f"Erreur écriture fichier: {str(e)}"

                # Mettre à jour la base de données
                cursor.execute("""
                    UPDATE ecritures_comptables
                    SET nom_fichier = %s, justificatif_url = %s, type_mime = %s, taille_fichier = %s
                    WHERE id = %s AND utilisateur_id = %s
                """, (
                    fichier.filename,
                    nouveau_nom,
                    fichier.content_type,
                    len(fichier_data),
                    ecriture_id,
                    user_id
                ))

                logger.info(f"Base de données mise à jour pour écriture {ecriture_id}")
                return True, "Fichier joint ajouté avec succès"

        except Exception as e:
            logger.error(f"Erreur ajout fichier écriture {ecriture_id}: {e}")
            return False, f"Erreur lors de l'ajout du fichier: {str(e)}"

    def get_fichier(self, ecriture_id: int, user_id: int) -> Optional[Dict]:
        """
        Récupère les informations du fichier joint d'une écriture.
        """
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT nom_fichier, justificatif_url, type_mime, taille_fichier, fichier_joint
                    FROM ecritures_comptables
                    WHERE id = %s AND utilisateur_id = %s AND (justificatif_url IS NOT NULL OR fichier_joint IS NOT NULL)
                """, (ecriture_id, user_id))

                result = cursor.fetchone()
                if not result:
                    return None
                if result['justificatif_url']:
                    file_path = self._get_file_path(result['justificatif_url'])


                    # Vérifier que le fichier existe physiquement
                    if os.path.exists(file_path):
                        return {
                            'nom_original': result['nom_fichier'],
                            'chemin_physique': result['justificatif_url'],
                            'type_mime': result['type_mime'],
                            'taille': result['taille_fichier'],
                            'chemin_complet': file_path,
                            'stockage': 'filesystem'
                        }
                    else:
                        logger.warning(f"Fichier manquant sur le disk: {file_path}")
                        return None
                elif result['fichier_joint']:
                    return {
                    'nom_original': result['nom_fichier'],
                    'contenu_blob': result['fichier_joint'],
                    'type_mime': result['type_mime'],
                    'taille': result['taille_fichier'],
                    'stockage': 'blob'
                }
                return None
        except Exception as e:
            logger.error(f"Erreur récupération fichier écriture {ecriture_id}: {e}")
            return None

    def supprimer_fichier(self, ecriture_id: int, user_id: int) -> Tuple[bool, str]:
        """
        Supprime le fichier joint d'une écriture (physiquement et en base).
        """
        try:
            logger.info(f"📍 Début suppression fichier - Écriture: {ecriture_id}, User: {user_id}")

            with self.db.get_cursor() as cursor:
                # Récupérer les infos du fichier avant suppression
                cursor.execute("""
                    SELECT nom_fichier, justificatif_url, fichier_joint
                    FROM ecritures_comptables
                    WHERE id = %s AND utilisateur_id = %s
                """, (ecriture_id, user_id))

                result = cursor.fetchone()
                if not result:
                    logger.error(f"❌ Écriture {ecriture_id} non trouvée pour l'utilisateur {user_id}")
                    return False, "Écriture non trouvée ou non autorisée"

                fichier_supprime = False
                message_suppression = ""

                # Supprimer le fichier physique s'il existe (justificatif_url)
                if result['justificatif_url']:
                    file_path = self._get_file_path(result['justificatif_url'])
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                            fichier_supprime = True
                            message_suppression = f"Fichier physique supprimé: {file_path}"
                            logger.info(f"✓ {message_suppression}")
                        except Exception as e:
                            logger.error(f"❌ Erreur suppression fichier physique: {e}")
                            return False, f"Erreur suppression fichier: {str(e)}"
                    else:
                        logger.warning(f"⚠️ Fichier physique non trouvé: {file_path}")

                # Mettre à jour la base de données
                cursor.execute("""
                    UPDATE ecritures_comptables
                    SET nom_fichier = NULL,
                        justificatif_url = NULL,
                        type_mime = NULL,
                        taille_fichier = NULL,
                        fichier_joint = NULL
                    WHERE id = %s AND utilisateur_id = %s
                """, (ecriture_id, user_id))

                if cursor.rowcount > 0:
                    if fichier_supprime:
                        message = f"Fichier '{result['nom_fichier']}' supprimé avec succès"
                    else:
                        message = f"Informations fichier supprimées (fichier physique non trouvé)"

                    logger.info(f"✓ Suppression réussie: {message}")
                    return True, message
                else:
                    logger.error(f"❌ Aucune ligne mise à jour dans la base")
                    return False, "Erreur lors de la suppression en base de données"

        except Exception as e:
            logger.error(f"❌ Erreur suppression fichier écriture {ecriture_id}: {e}")
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return False, f"Erreur lors de la suppression: {str(e)}"

    def get_chemin_fichier_physique(self, ecriture_id: int, user_id: int) -> Optional[str]:
        """
        Retourne le chemin physique du fichier pour le téléchargement.
        """
        fichier_info = self.get_fichier(ecriture_id, user_id)
        return fichier_info['chemin_complet'] if fichier_info else None

class ContactPlan:
    def __init__(self, db):
        self.db = db

    def get_plans_for_contact(self, contact_id: int, user_id: int) -> List[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT p.*
                FROM contact_plans cp
                JOIN plans_comptables p ON cp.plan_id = p.id
                WHERE cp.contact_id = %s AND p.utilisateur_id = %s
                ORDER BY p.nom
            """, (contact_id, user_id))
            return cursor.fetchall()

    def get_contacts_for_plan(self, plan_id: int, user_id: int) -> List[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT c.*
                FROM contact_plans cp
                JOIN contacts c ON cp.contact_id = c.id_contact
                WHERE cp.plan_id = %s AND c.utilisateur_id = %s
                ORDER BY c.nom
            """, (plan_id, user_id))
            return cursor.fetchall()

    def assign_plan_to_contact(self, contact_id: int, plan_id: int, user_id: int) -> bool:
        # Vérifier propriété
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT 1 FROM contacts WHERE id_contact = %s AND utilisateur_id = %s", (contact_id, user_id))
            if not cursor.fetchone(): return False
            cursor.execute("SELECT 1 FROM plans_comptables WHERE id = %s AND utilisateur_id = %s", (plan_id, user_id))
            if not cursor.fetchone(): return False
            cursor.execute("INSERT IGNORE INTO contact_plans (contact_id, plan_id) VALUES (%s, %s)", (contact_id, plan_id))
            return True

class Contacts:
    def __init__(self, db):
        self.db = db

    def create(self, data: Dict) -> bool:
        """
        Crée un nouveau contact.
        La colonne 'id_contact' est en AUTO_INCREMENT et ne doit pas être incluse.
        """
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO contacts
                (nom, email, telephone, adresse, code_postal, ville, pays, utilisateur_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    data['nom'],
                    data.get('email', ''),
                    data.get('telephone', ''),
                    data.get('adresse', ''),
                    data.get('code_postal', ''),
                    data.get('ville', ''),
                    data.get('pays', ''),
                    data['utilisateur_id']
                )
                cursor.execute(query, values)
                return True
        except Error as e:
            # Utilisez un logger au lieu de logger.error pour un environnement de production
            logger.error(f"Erreur lors de la création du contact: {e}")
            return False

    def update(self, contact_id: int, data: Dict, utilisateur_id: int) -> bool:
        """Met à jour un contact existant."""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE contacts
                SET nom = %s, email = %s, telephone = %s, adresse = %s,
                    code_postal = %s, ville = %s, pays = %s
                WHERE id_contact = %s AND utilisateur_id = %s
                """
                values = (
                    data['nom'],
                    data.get('email', ''),
                    data.get('telephone', ''),
                    data.get('adresse', ''),
                    data.get('code_postal', ''),
                    data.get('ville', ''),
                    data.get('pays', ''),
                    contact_id,
                    utilisateur_id
                )

                # Utilisez le logger de l'application Flask
                logger.debug(f"[update] Query: {query} avec params: {values}")

                cursor.execute(query, values)
                # Le commit est géré par la classe DatabaseManager (autocommit)
                # ou via une transaction si vous l'avez configurée.
                return cursor.rowcount > 0 # Vérifie si une ligne a été modifiée
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour du contact: {e}")
            return False

    def get_all(self, utilisateur_id: int) -> List[Dict]:
        """Récupère tous les contacts d'un utilisateur."""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM contacts WHERE utilisateur_id = %s ORDER BY nom"
                cursor.execute(query, (utilisateur_id,))
                contacts = cursor.fetchall()
                return contacts
        except Error as e:
            logger.error(f"Erreur lors de la récupération des contacts: {e}")
            return []

    def get_by_id(self, contact_id: int, utilisateur_id: int) -> Optional[Dict]:
        """Récupère un contact par son ID (id_contact)."""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM contacts WHERE id_contact = %s AND utilisateur_id = %s"
                cursor.execute(query, (contact_id, utilisateur_id))
                contact = cursor.fetchone()
                return contact
        except Error as e:
            logger.error(f"Erreur lors de la récupération du contact: {e}")
            return None

    def delete(self, contact_id: int, utilisateur_id: int) -> bool:
        """Supprime un contact par son ID (id_contact)."""
        try:
            with self.db.get_cursor() as cursor:
                query = "DELETE FROM contacts WHERE id_contact = %s AND utilisateur_id = %s"
                cursor.execute(query, (contact_id, utilisateur_id))
                # Le commit est géré par la classe DatabaseManager
                return cursor.rowcount > 0 # Vérifie si une ligne a été supprimée
        except Error as e:
            logger.error(f"Erreur lors de la suppression du contact: {e}")
            return False

    def get_last_insert_id(self) -> Optional[int]:
        """Récupère le dernier ID auto-généré après une insertion."""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT LAST_INSERT_ID()")
                result = cursor.fetchone()
                # Le résultat est un dictionnaire car vous utilisez DictCursor
                # Il faut donc y accéder avec la clé 'LAST_INSERT_ID()'
                return result['LAST_INSERT_ID()'] if result else None
        except Error as e:
            logger.error(f"Erreur lors de la récupération du dernier ID: {e}")
            return None

    def get_by_name(self, nom: str, utilisateur_id: int) -> List[Dict]:
        """Récupère les contacts par nom."""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM contacts WHERE nom LIKE %s AND utilisateur_id = %s ORDER BY nom"
                cursor.execute(query, (f"%{nom}%", utilisateur_id))
                contacts = cursor.fetchall()
                return contacts
        except Error as e:
            logger.error(f"Erreur lors de la recherche de contacts: {e}")
            return []

class ContactCompte:
    def __init__(self, db):
        self.db = db

    def link_to_compte(self, contact_id: int, compte_id: int, utilisateur_id: int) -> bool:
        """Lie un contact à un compte bancaire"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier que les entités existent et appartiennent à l'utilisateur
                cursor.execute("""
                            SELECT id_contact
                            FROM contacts
                            WHERE id_contact = %s AND utilisateur_id = %s
                            """, (contact_id, utilisateur_id))
                if not cursor.fetchone():
                    logger.warning(f'Tentative de liason avec un contact non autorisé: contact_id={contact_id}, user={utilisateur_id}')
                    return False
                cursor.execute("""
                            SELECT id
                            FROM comptes_principaux
                            WHERE id = %s
                            """, (compte_id))
                if not cursor.fetchone():
                    logger.warning(f'Tentative de liason avec un compte non existant: compte_id = {compte_id}')
                    return False

                cursor.execute("""
                    INSERT IGNORE INTO contact_comptes (contact_id, compte_id, utilisateur_id)
                    VALUES (%s, %s, %s)
                """, (contact_id, compte_id, utilisateur_id))
                return True
        except Error as e:
            logger.error(f"Erreur SQL dans link_to_compte : {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur liaison contact-compte : {e}")
            return False

    def unlink_from_compte(self, contact_id: int, compte_id: int, utilisateur_id: int) -> bool:
        """Supprime la liaison entre un contact et un compte"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    DELETE FROM contact_comptes
                    WHERE contact_id = %s AND compte_id = %s AND utilisateur_id = %s
                """, (contact_id, compte_id, utilisateur_id))
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur SQL dans unlink_from_compte : {e}")
            return False
        except Exception as e:
            logger.error(f"Erreur déliaison contact-compte : {e}")
            return False

    def get_comptes_for_contact(self, contact_id: int, utilisateur_id: int) -> List[Dict]:
        """Récupère les comptes liés à un contact"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT cp.id, cp.nom_compte, cp.iban, cp.utilisateur_id AS compte_utilisateur_id,
                               u.nom AS titulaire_nom,
                               u.prenom AS titulaire_prenom
                    FROM contact_comptes cc
                    JOIN comptes_principaux cp ON cc.compte_id = cp.id
                    JOIN utilisateurs u ON cp.utilisateur_id = u.id
                    WHERE cc.contact_id = %s AND cc.utilisateur_id = %s
                    ORDER by cp.nom_compte
                """, (contact_id, utilisateur_id))
                return cursor.fetchall()
        except Error as e:
            logger.error(f"Erreur SQL dans get_comptes_for_contact : {e}")
            return []
        except Exception as e:
            logger.error(f"Erreur récupération comptes pour contact : {e}")
            return []

    def get_contacts_for_compte(self, compte_id: int, utilisateur_id: int) -> List[Dict]:
        """Récupère TOUS les contacts liés à un compte"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT c.id_contact, c.nom, c.email, c.telephone, c.adresse, c.ville
                    FROM contact_comptes cc
                    JOIN contacts c ON cc.contact_id = c.id_contact  # ✅ Jointure corrigée
                    WHERE cc.compte_id = %s AND cc.utilisateur_id = %s
                    ORDER BY c.nom
                """, (compte_id, utilisateur_id))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération contacts pour compte : {e}")
            return []

    def get_contact_by_compte(self, compte_id: int, utilisateur_id: int) -> Optional[Dict]:
        """Récupère le PREMIER contact lié à un compte (pour écriture automatique)"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT cc.contact_id, c.nom, c.email
                    FROM contact_comptes cc
                    INNER JOIN contacts c ON cc.contact_id = c.id_contact  # ✅ Jointure corrigée
                    WHERE cc.compte_id = %s AND cc.utilisateur_id = %s
                    LIMIT 1
                """, (compte_id, utilisateur_id))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur récupération contact par compte : {e}")
            return None

class Rapport:
    def __init__(self, db):
        self.db = db

    def generate_rapport_mensuel(self, ecriture_comptable, user_id: int, annee: int, mois: int, statut: str = 'validée') -> Dict:
        """Génère un rapport mensuel avec filtrage par statut"""
        date_debut = date(annee, mois, 1)
        date_fin = date(annee, mois + 1, 1) if mois < 12 else date(annee + 1, 1, 1)
        date_fin = date_fin - timedelta(days=1)

        # Utilisez EcritureComptable pour obtenir les données
        ecritures = ecriture_comptable.get_stats_by_categorie(
            user_id,
            str(date_debut),
            str(date_fin),
            statut
        )

        # Les appels aux autres classes doivent être faits ici si nécessaire
        # Exemple: stats = StatistiquesBancaires(self.db).get_resume_utilisateur(user_id)
        # exemple: repartition = StatistiquesBancaires(self.db).get_repartition_par_banque(user_id)

        return {
            'periode': f"{mois}/{annee}",
            'date_debut': date_debut,
            'date_fin': date_fin,
            # 'stats': stats,
            # 'repartition_banques': repartition,
            'ecritures_par_categorie': ecritures,
            'statut': statut
        }

    def generate_rapport_annuel(self, user_id: int, annee: int, statut: str = 'validée') -> Dict:
        """Génère un rapport annuel avec filtrage par statut"""
        date_debut = date(annee, 1, 1)
        date_fin = date(annee, 12, 31)

        donnees_mensuelles = []
        for mois in range(1, 13):
            donnees_mensuelles.append(
                self.generate_rapport_mensuel(user_id, annee, mois, statut))

        ecriture_comptable = EcritureComptable(self.db)
        compte_resultat = ecriture_comptable.get_compte_de_resultat(
            user_id, str(date_debut), str(date_fin))

        return {
            'annee': annee,
            'donnees_mensuelles': donnees_mensuelles,
            'compte_resultat': compte_resultat,
            'statut': statut
        }

    def generate_rapport_comparatif(self, user_id: int, annee: int) -> Dict:
        """Génère un rapport comparatif avec différents statuts"""
        rapport_valide = self.generate_rapport_annuel(user_id, annee, 'validée')
        rapport_pending = self.generate_rapport_annuel(user_id, annee, 'pending')
        rapport_rejetee = self.generate_rapport_annuel(user_id, annee, 'rejetée')

        return {
            'annee': annee,
            'rapport_valide': rapport_valide,
            'rapport_pending': rapport_pending,
            'rapport_rejetee': rapport_rejetee,
            'comparaison': self._comparer_rapports(rapport_valide, rapport_pending, rapport_rejetee)
        }

    def _comparer_rapports(self, *rapports):
        """Compare les différents rapports pour analyse"""
        comparison = {}
        # Implémentation de la comparaison entre rapports
        return comparison

    def get_rapport_par_statut(self, user_id: int, date_from: str, date_to: str, statut: str) -> Dict:
        """Génère un rapport personnalisé par plage de dates et statut"""
        ecriture_comptable = EcritureComptable(self.db)
        ecritures = ecriture_comptable.get_stats_by_categorie(
            user_id, date_from, date_to, statut
        )

        total_depenses = sum(item['total_depenses'] or 0 for item in ecritures)
        total_recettes = sum(item['total_recettes'] or 0 for item in ecritures)

        return {
            'periode': f"{date_from} à {date_to}",
            'date_debut': date_from,
            'date_fin': date_to,
            'statut': statut,
            'ecritures_par_categorie': ecritures,
            'total_depenses': total_depenses,
            'total_recettes': total_recettes,
            'solde': total_recettes - total_depenses,
            'nombre_ecritures': sum(item['nb_ecritures'] or 0 for item in ecritures)
        }

class BaremeCotisation:
    def __init__(self, db):
        self.db = db

    def modifier_bareme(self, type_cotisation_id: int, tranches: List[Dict]) -> bool:
        """
        Remplace entièrement le barème associé à un type de cotisation.
        `tranches` est une liste de dict avec :
            - seuil_min (float)
            - seuil_max (float ou None)
            - montant_fixe (float, utilisé si type_valeur='fixe')
            - taux (float, utilisé si type_valeur='taux')
            - type_valeur ('taux' ou 'fixe')
        """
        try:
            with self.db.get_cursor() as cursor:
                # Supprimer les anciennes tranches
                cursor.execute("DELETE FROM baremes_cotisation WHERE type_cotisation_id = %s", (type_cotisation_id,))

                # Insérer les nouvelles
                query = """
                INSERT INTO baremes_cotisation 
                (type_cotisation_id, seuil_min, seuil_max, montant_fixe, taux, type_valeur, ordre)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                for i, t in enumerate(tranches):
                    seuil_min = float(t.get('seuil_min', 0))
                    seuil_max = t.get('seuil_max')
                    if seuil_max is not None:
                        seuil_max = float(seuil_max)
                    montant_fixe = float(t.get('montant_fixe', 0))
                    taux = float(t.get('taux', 0))
                    type_valeur = t.get('type_valeur', 'fixe')
                    if type_valeur not in ('taux', 'fixe'):
                        type_valeur = 'fixe'

                    cursor.execute(query, (
                        type_cotisation_id,
                        seuil_min,
                        seuil_max,
                        montant_fixe,
                        taux,
                        type_valeur,
                        i
                    ))
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la modification du barème pour type_cotisation {type_cotisation_id}: {e}")
            return False

    def get_bareme(self, type_cotisation_id: int) -> List[Dict]:
        """Récupère toutes les tranches d’un barème, triées par seuil_min"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT seuil_min, seuil_max, montant_fixe, taux, type_valeur
                    FROM baremes_cotisation
                    WHERE type_cotisation_id = %s
                    ORDER BY seuil_min
                """, (type_cotisation_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération barème type {type_cotisation_id}: {e}")
            return []

    def has_bareme(self, type_cotisation_id: int) -> bool:
        """Vérifie si un barème existe pour ce type"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT 1 FROM baremes_cotisation WHERE type_cotisation_id = %s LIMIT 1", (type_cotisation_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Erreur vérification barème: {e}")
            return False
        
class BaremeIndemnite:
    def __init__(self, db):
        self.db = db

    def modifier_bareme(self, type_indemnite_id: int, tranches: List[Dict]) -> bool:
        """
        Remplace entièrement le barème associé à un type d'indemnité.
        `tranches` est une liste de dict avec :
            - seuil_min (float)
            - seuil_max (float ou None)
            - montant_fixe (float, utilisé si type_valeur='fixe')
            - taux (float, utilisé si type_valeur='taux')
            - type_valeur ('taux' ou 'fixe')
        """
        try:
            with self.db.get_cursor() as cursor:
                # Supprimer les anciennes tranches
                cursor.execute("DELETE FROM baremes_indemnite WHERE type_indemnite_id = %s", (type_indemnite_id,))

                # Insérer les nouvelles
                query = """
                INSERT INTO baremes_indemnite
                (type_indemnite_id, seuil_min, seuil_max, montant_fixe, taux, type_valeur, ordre)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                for i, t in enumerate(tranches):
                    seuil_min = float(t.get('seuil_min', 0))
                    seuil_max = t.get('seuil_max')
                    if seuil_max is not None:
                        seuil_max = float(seuil_max)
                    montant_fixe = float(t.get('montant_fixe', 0))
                    taux = float(t.get('taux', 0))
                    type_valeur = t.get('type_valeur', 'fixe')
                    if type_valeur not in ('taux', 'fixe'):
                        type_valeur = 'fixe'

                    cursor.execute(query, (
                        type_indemnite_id,
                        seuil_min,
                        seuil_max,
                        montant_fixe,
                        taux,
                        type_valeur,
                        i
                    ))
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la modification du barème pour type_indemnite {type_indemnite_id}: {e}")
            return False

    def get_bareme(self, type_indemnite_id: int) -> List[Dict]:
        """Récupère toutes les tranches d’un barème, triées par seuil_min"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                cursor.execute("""
                    SELECT seuil_min, seuil_max, montant_fixe, taux, type_valeur
                    FROM baremes_indemnite
                    WHERE type_indemnite_id = %s
                    ORDER BY seuil_min
                """, (type_indemnite_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération barème type indemnité {type_indemnite_id}: {e}")
            return []

    def has_bareme(self, type_indemnite_id: int) -> bool:
        """Vérifie si un barème existe pour ce type d'indemnité"""
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT 1 FROM baremes_indemnite WHERE type_indemnite_id = %s LIMIT 1", (type_indemnite_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Erreur vérification barème indemnité: {e}")
            return False
        
class TypeCotisation:
    def __init__(self, db):
        self.db = db
    def create(self, user_id: int, nom: str, description: str ="", est_obligatoire: bool = False)-> int:
        """Crée un type de cotisation"""
        try:
            with self.db.get_cursor as cursor:
                query = """
                INSERT INTO types_cotisation (user_id, nom, description, est_obligatoire
                VALUES (%s, %s, %s, %s)"""
                cursor.execute(query, (user_id, nom, description, est_obligatoire))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Erreur création type_cotisation {e}")
    def get_all_by_user(self, user_id: int)-> List[Dict]:
        """récupère toutes les cotisations de l'utilisateur"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT *
                FROM types_cotisation
                WHERE user_id = %s
                ORDER BY nom"""
                cursor.execute(query, (user_id))
                return cursor.fetchall
        except Exception as e:
            logger.error(f"Erreur récupération types_cotisation : {e}")
            return []
    def update(self, type_id: int, user_id:int, data: Dict)-> bool:
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        params = list(data.values()) + [type_id, user_id]
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE types_cotisation SET {set_clause}
                WHERE id = %s AND user_id=%s"""
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except Exception as e:
            logger(f"Erreur mise à jour type cotisation : {e}")
    def delete(self, type_id:int, user_id:int)-> bool:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("DELETE FROM types_cotisation WHERE id = %s AND user_id = %s",
                    (type_id, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur suppression type cotisation: {e}")
            return False

class TypeIndemnite:
    def __init__(self, db):
        self.db = db
    def create(self, user_id: int, nom: str, description: str ="", est_obligatoire: bool = False)-> int:
        """Crée un type d'indemnité"""
        try:
            with self.db.get_cursor as cursor:
                query = """
                INSERT INTO types_indemnite (user_id, nom, description, est_obligatoire
                VALUES (%s, %s, %s, %s)"""
                cursor.execute(query, (user_id, nom, description, est_obligatoire))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Erreur création type_cotisation {e}")
    def get_all_by_user(self, user_id: int)-> List[Dict]:
        """récupère toutes les indemnités de l'utilisateur"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT *
                FROM types_indemnite
                WHERE user_id = %s
                ORDER BY nom"""
                cursor.execute(query, (user_id))
                return cursor.fetchall
        except Exception as e:
            logger.error(f"Erreur récupération types_indemnite : {e}")
            return []
    def update(self, type_id: int, user_id:int, data: Dict)-> bool:
        set_clause = ", ".join([f"{k} = %s" for k in data.keys()])
        params = list(data.values()) + [type_id, user_id]
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE types_indemnite SET {set_clause}
                WHERE id = %s AND user_id=%s"""
                cursor.execute(query, params)
                return cursor.rowcount > 0
        except Exception as e:
            logger(f"Erreur mise à jour type indemnite : {e}")
    def delete(self, type_id:int, user_id:int)-> bool:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("DELETE FROM types_indemnite WHERE id = %s AND user_id = %s",
                    (type_id, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur suppression type indemnite: {e}")
            return False

class CotisationContrat:
    def __init__(self, db):
        self.db = db

    def calculer_montant_cotisation(self, bareme_cotisation_model, type_cotisation_id: int, base_montant: float, taux_fallback: float = 0.0) -> float:
        """
        Calcule le montant d'une cotisation :
        - Si barème → utilise le barème avec base_montant (salaire brut ou brut_tot)
        - Sinon → utilise taux_fallback (issu de cotisations_contrat)
        """
        if bareme_cotisation_model.has_bareme(type_cotisation_id):
            tranches = bareme_cotisation_model.get_bareme(type_cotisation_id)
            for tranche in tranches:
                min_s = tranche['seuil_min']
                max_s = tranche['seuil_max']
                if base_montant >= min_s and (max_s is None or base_montant <= max_s):
                    if tranche['type_valeur'] == 'fixe':
                        return float(tranche['montant_fixe'])
                    else:
                        return float(base_montant * (tranche['taux'] / 100))
            return 0.0
        else:
            # Ancien comportement
            if taux_fallback >= 10:
                return float(taux_fallback)  # montant fixe
            else:
                return float(base_montant * (taux_fallback / 100))
            
    def assigner_a_contrat(self, contrat_id: int, type_cotisation_id: int, taux:float, annee: int, base_calcul : str = "brut")-> bool:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO cotisations_contrat (contrat_id, type_cotisation_id, taux, base_calcul, annee)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE taux = VALUES(taux), base_calcul = VALUES(base_calcul), actif = TRUE
                """
                cursor.execute(query, (contrat_id, type_cotisation_id, taux, base_calcul, annee))
                return True
        except Exception as e:
            logger.error(f"Erreur assignation cotisation : {e}")
            return False
    def get_for_contrat(self, contrat_id: int)-> List[Dict]:
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT cc.*, tc.nom AS nom_cotisation
                FROM cotisations_contrat cc
                JOIN types_cotisation tc ON cc.type_cotisation_id = tc.id
                WHERE cc.contrat_id = %s AND cc.actif = TRUE
                """
                cursor.execute(query,(contrat_id))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération cotisation contrat : {e}")
            return []
    def get_for_contrat_and_annee(self, contrat_id: int, annee: int) -> List[Dict]:
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT cc.*, tc.nom AS nom_cotisation, tc.description
                FROM cotisations_contrat cc
                JOIN types_cotisation tc ON cc.type_cotisation_id = tc.id
                WHERE cc.contrat_id = %s AND cc.annee = %s
                """
                cursor.execute(query,(contrat_id, annee))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération cotisation contrat {contrat_id} pour annee {annee} : {e}")
            return []
    def get_total_cotisations_par_mois(self, bareme_cotisation_model, user_id: int, annee: int, mois: int) -> List[Dict]:
        """
        Retourne le détail des cotisations par contrat pour un mois donné.
        Inclut le montant calculé selon la base (brut ou brut_tot) et le taux.
        """
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT
                    cc.contrat_id,
                    c.employeur,
                    c.employe_id,
                    c.salaire_horaire,
                    tc.nom AS nom_cotisation,
                    cc.taux,
                    cc.base_calcul
                FROM cotisations_contrat cc
                JOIN contrats c ON cc.contrat_id = c.id
                JOIN types_cotisation tc ON cc.type_cotisation_id = tc.id
                WHERE c.user_id = %s AND cc.annee = %s
                """
                cursor.execute(query, (user_id, annee))
                cotisations = cursor.fetchall()

                # Récupérer les heures réelles par contrat pour le mois
                heures_par_contrat = {}
                for item in cotisations:
                    contrat_id = item['contrat_id']
                    if contrat_id not in heures_par_contrat:
                        total_h = self.db.get_cursor().connection  # ❌ Pas possible → on va faire autrement

                # → On précharge toutes les heures dans un dict
                heures_query = """
                SELECT id_contrat, SUM(total_h) AS total_heures
                FROM heures_travail
                WHERE user_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
                GROUP BY id_contrat
                """
                cursor.execute(heures_query, (user_id, annee, mois))
                heures_rows = cursor.fetchall()
                heures_par_contrat = {row['id_contrat']: float(row['total_heures']) for row in heures_rows}

                # Calcul final
                result = []
                for item in cotisations:
                    contrat_id = item['contrat_id']
                    heures = heures_par_contrat.get(contrat_id, 0.0)
                    salaire_horaire = float(item['salaire_horaire'])
                    brut = heures * salaire_horaire

                    # Pour simplifier, on suppose "base_calcul = brut"
                    # (une version avancée devrait inclure indemnités → nécessite appel à IndemniteContrat)
                    type_cotisation_id = item['type_cotisation_id']
                    montant = 0.0

                    # 1. Vérifier si un barème existe pour ce type
                    if bareme_cotisation_model.has_bareme(type_cotisation_id):
                        tranches = bareme_cotisation_model.get_bareme(type_cotisation_id)
                        for tranche in tranches:
                            min_s = tranche['seuil_min']
                            max_s = tranche['seuil_max']
                            if brut >= min_s and (max_s is None or brut <= max_s):
                                if tranche['type_valeur'] == 'fixe':
                                    montant = tranche['montant_fixe']
                                else:
                                    montant = brut * (tranche['taux'] / 100)
                                break
                    else:
                        # 2. Sinon, utiliser l’ancien système (depuis cotisations_contrat)
                        if item['taux'] >= 10:
                            montant = item['taux']  # montant fixe absolu
                        else:
                            montant = brut * (item['taux'] / 100)  # pourcentage

                    result.append({
                        'contrat_id': contrat_id,
                        'employeur': item['employeur'],
                        'employe_id': item['employe_id'],
                        'nom_cotisation': item['nom_cotisation'],
                        'taux': item['taux'],
                        'base_calcul': item['base_calcul'],
                        'heures': heures,
                        'brut': round(brut, 2),
                        'montant': round(montant, 2)
                    })
                return result
        except Exception as e:
            logger.error(f"Erreur get_total_cotisations_par_mois: {e}")
            return []

    def prepare_svg_cotisations_mensuelles(self, user_id: int, annee: int, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        """
        Prépare les données SVG pour un graphique en barres des cotisations mensuelles totales.
        """
        # 1. Récupérer les cotisations mois par mois
        montants_mensuels = []
        for mois in range(1, 13):
            total = sum(
                c['montant']
                for c in self.get_total_cotisations_par_mois(user_id, annee, mois)
            )
            montants_mensuels.append(round(total, 2))

        # 2. Calcul des bornes
        min_val = min(montants_mensuels) if montants_mensuels else 0.0
        max_val = max(montants_mensuels) if montants_mensuels else 1.0
        if min_val == max_val:
            max_val = min_val + (10.0 if min_val == 0 else min_val * 0.1)

        # 3. Dimensions SVG
        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        def y_coord(val):
            return margin_y + plot_height - ((val - min_val) / (max_val - min_val)) * plot_height

        # 4. Ticks Y (tous les 50 CHF, ajustable)
        ticks = []
        step = 50
        y_val = math.floor(min_val / step) * step
        while y_val <= max_val + step:
            if y_val >= 0:
                ticks.append({
                    'value': int(y_val),
                    'y_px': y_coord(y_val)
                })
            y_val += step

        # 5. Barres SVG
        colonnes_svg = []
        bar_width = plot_width / 12 * 0.7
        for i, montant in enumerate(montants_mensuels):
            x = margin_x + (i + 0.5) * (plot_width / 12) - bar_width / 2
            y_top = y_coord(montant)
            height = plot_height - (y_top - margin_y)
            if height < 0:
                height = 0
                y_top = margin_y + plot_height
            colonnes_svg.append({
                'x': x,
                'y': y_top,
                'width': bar_width,
                'height': height
            })

        # 6. Labels mois
        mois_labels = [f"{m:02d}/{annee}" for m in range(1, 13)]

        return {
            'colonnes': colonnes_svg,
            'mois_labels': mois_labels,
            'valeurs': montants_mensuels,
            'total_annuel': round(sum(montants_mensuels), 2),
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'ticks': ticks,
            'min_val': min_val,
            'max_val': max_val,
            'annee': annee
        }
    def get_all_by_user(self, user_id: int) -> List[Dict]:
        """Récupère toutes les cotisations pour les contrats d'un utilisateur"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT cc.*, c.employeur, c.employe_id, tc.nom AS type_cotisation_nom
                FROM cotisations_contrat cc
                JOIN contrats c ON cc.contrat_id = c.id
                JOIN types_cotisation tc ON cc.type_cotisation_id = tc.id
                WHERE c.user_id = %s
                ORDER BY c.employeur, tc.nom
                """
                cursor.execute(query, (user_id,))
                rows = cursor.fetchall()
                return rows
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des cotisations pour user_id={user_id}: {e}", exc_info=True)
            return []

    # Dans la classe CotisationContrat
    def prepare_svg_cotisations_mensuelles_employe(self, employe_model, user_id: int, employe_id: int, annee: int, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        montants_mensuels = []
        for mois in range(1, 13):
            total = sum(
                c['montant']
                for c in self.get_total_cotisations_par_mois(user_id, annee, mois)
                if c.get('employe_id') == employe_id
            )
            montants_mensuels.append(round(total, 2))

        min_val = min(montants_mensuels) if montants_mensuels else 0.0
        max_val = max(montants_mensuels) if montants_mensuels else 1.0
        if min_val == max_val:
            max_val = min_val + (10.0 if min_val == 0 else min_val * 0.1)

        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        def y_coord(val):
            return margin_y + plot_height - ((val - min_val) / (max_val - min_val)) * plot_height

        ticks = []
        step = 20
        y_val = math.floor(min_val / step) * step
        while y_val <= max_val + step:
            if y_val >= 0:
                ticks.append({'value': int(y_val), 'y_px': y_coord(y_val)})
            y_val += step

        colonnes_svg = []
        bar_width = plot_width / 12 * 0.7
        for i, montant in enumerate(montants_mensuels):
            x = margin_x + (i + 0.5) * (plot_width / 12) - bar_width / 2
            y_top = y_coord(montant)
            height = plot_height - (y_top - margin_y)
            if height < 0:
                height = 0
                y_top = margin_y + plot_height
            colonnes_svg.append({'x': x, 'y': y_top, 'width': bar_width, 'height': height})

        mois_labels = [f"{m:02d}/{annee}" for m in range(1, 13)]
        
        # Récupérer le nom de l'employé (optionnel, pour le titre)
        employe = employe_model.get_by_id(employe_id, user_id)
        employe_nom = f"{employe['prenom']} {employe['nom']}" if employe else "Employé inconnu"

        return {
            'colonnes': colonnes_svg,
            'mois_labels': mois_labels,
            'valeurs': montants_mensuels,
            'total_annuel': round(sum(montants_mensuels), 2),
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'ticks': ticks,
            'min_val': min_val,
            'max_val': max_val,
            'annee': annee,
            'employe_id': employe_id,
            'employe_nom': employe_nom,
            'type': 'cotisations_employe'
        }

class IndemniteContrat:
    def __init__(self, db):
        self.db = db


    def calculer_montant_indemnite(self, bareme_indemnite_model, type_indemnite_id: int, base_montant: float, taux_fallback: float = 0.0) -> float:
        """
        Calcule le montant d'une indemnité :
        - Si barème → utilise le barème avec base_montant
        - Sinon → utilise taux_fallback (issu de indemnites_contrat)
        """
        if bareme_indemnite_model.has_bareme(type_indemnite_id):
            tranches = bareme_indemnite_model.get_bareme(type_indemnite_id)
            for tranche in tranches:
                min_s = tranche['seuil_min']
                max_s = tranche['seuil_max']
                if base_montant >= min_s and (max_s is None or base_montant <= max_s):
                    if tranche['type_valeur'] == 'fixe':
                        return float(tranche['montant_fixe'])
                    else:
                        return float(base_montant * (tranche['taux'] / 100))
            return 0.0
        else:
            # Ancien comportement : toujours en % du brut
            return float(base_montant * (taux_fallback / 100))
    
    def assigner_a_contrat(self, contrat_id: int, type_indemnite_id: int, taux:float, annee: int, base_calcul : str = "brut")-> bool:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO indemnites_contrat (contrat_id, type_indemnite_id, taux, base_calcul, annee)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE taux = VALUES(taux), base_calcul = VALUES(base_calcul), actif = TRUE
                """
                cursor.execute(query, (contrat_id, type_indemnite_id, taux, base_calcul, annee))
                return True
        except Exception as e:
            logger.error(f"Erreur assignation cotisation : {e}")
            return False
    def get_for_contrat(self, contrat_id: int)-> List[Dict]:
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT ic.*, ti.nom AS nom_indemnite, ti.description
                FROM indemnites_contrat ic
                JOIN types_indemnite ti ON ic.type_indemnite_id = ti.id
                WHERE ic.contrat_id = %s AND ic.actif = TRUE
                """
                cursor.execute(query,(contrat_id))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération indemnite contrat : {e}")
            return []
    def get_for_contrat_and_annee(self, contrat_id: int, annee: int) -> List[Dict]:
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT ic.*, ti.nom AS nom_indemnite, ti.description
                FROM indemnites_contrat ic
                JOIN types_indemnite ti ON ic.type_indemnite_id = ti.id
                WHERE ic.contrat_id = %s AND ic.annee = %s
                """
                cursor.execute(query,(contrat_id, annee))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération indemnite contrat {contrat_id} pour annee {annee} : {e}")
            return []

    def get_total_indemnites_par_mois(self, user_id: int, annee: int, mois: int) -> List[Dict]:
        """
        Retourne le détail des indemnités par contrat pour un mois donné.
        Inclut le montant calculé selon la base (brut ou brut_tot).
        Attention : cette version utilise uniquement le salaire BRUT comme base.
        Pour une version complète avec brut_tot, il faudrait charger aussi les cotisations → à implémenter dans Salaire.
        """
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                # Étape 1 : récupérer toutes les indemnités définies pour l'année
                query_indem = """
                SELECT
                    ic.contrat_id,
                    c.employeur,
                    c.employe_id,
                    c.salaire_horaire,
                    ti.nom AS nom_indemnite,
                    ic.taux,
                    ic.base_calcul
                FROM indemnites_contrat ic
                JOIN contrats c ON ic.contrat_id = c.id
                JOIN types_indemnite ti ON ic.type_indemnite_id = ti.id
                WHERE c.user_id = %s AND ic.annee = %s
                """
                cursor.execute(query_indem, (user_id, annee))
                indemnites = cursor.fetchall()

                # Étape 2 : précharger les heures réelles par contrat pour le mois
                heures_query = """
                SELECT id_contrat, SUM(total_h) AS total_heures
                FROM heures_travail
                WHERE user_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
                GROUP BY id_contrat
                """
                cursor.execute(heures_query, (user_id, annee, mois))
                heures_rows = cursor.fetchall()
                heures_par_contrat = {row['id_contrat']: float(row['total_heures']) for row in heures_rows}

                # Étape 3 : calculer les montants
                result = []
                for item in indemnites:
                    contrat_id = item['contrat_id']
                    heures = heures_par_contrat.get(contrat_id, 0.0)
                    salaire_horaire = float(item['salaire_horaire'])
                    brut = heures * salaire_horaire
                    montant = self.calculer_montant_indemnite(
                        type_indemnite_id=item['type_indemnite_id'],
                        base_montant=brut,
                        taux_fallback=item['taux']
                    )
                    montant = round(montant, 2)

                    result.append({
                        'contrat_id': contrat_id,
                        'employeur': item['employeur'],
                        'employe_id': item['employe_id'],
                        'nom_indemnite': item['nom_indemnite'],
                        'taux': item['taux'],
                        'base_calcul': item['base_calcul'],
                        'heures': heures,
                        'brut': round(brut, 2),
                        'montant': montant
                    })
                return result
        except Exception as e:
            logger.error(f"Erreur get_total_indemnites_par_mois: {e}")
            return []
    
    def prepare_svg_indemnites_mensuelles(self, user_id: int, annee: int, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        """
        Prépare les données SVG pour un graphique en barres des indemnités mensuelles totales.
        """
        # 1. Récupérer les indemnités mois par mois
        montants_mensuels = []
        for mois in range(1, 13):
            total = sum(
                i['montant']
                for i in self.get_total_indemnites_par_mois(user_id, annee, mois)
            )
            montants_mensuels.append(round(total, 2))

        # 2. Calcul des bornes
        min_val = min(montants_mensuels) if montants_mensuels else 0.0
        max_val = max(montants_mensuels) if montants_mensuels else 1.0
        if min_val == max_val:
            max_val = min_val + (10.0 if min_val == 0 else min_val * 0.1)

        # 3. Dimensions SVG
        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        def y_coord(val):
            return margin_y + plot_height - ((val - min_val) / (max_val - min_val)) * plot_height

        # 4. Ticks Y (tous les 50 CHF, ajustable)
        ticks = []
        step = 50
        y_val = math.floor(min_val / step) * step
        while y_val <= max_val + step:
            if y_val >= 0:
                ticks.append({
                    'value': int(y_val),
                    'y_px': y_coord(y_val)
                })
            y_val += step

        # 5. Barres SVG
        colonnes_svg = []
        bar_width = plot_width / 12 * 0.7
        for i, montant in enumerate(montants_mensuels):
            x = margin_x + (i + 0.5) * (plot_width / 12) - bar_width / 2
            y_top = y_coord(montant)
            height = plot_height - (y_top - margin_y)
            if height < 0:
                height = 0
                y_top = margin_y + plot_height
            colonnes_svg.append({
                'x': x,
                'y': y_top,
                'width': bar_width,
                'height': height
            })

        # 6. Labels mois
        mois_labels = [f"{m:02d}/{annee}" for m in range(1, 13)]

        return {
            'colonnes': colonnes_svg,
            'mois_labels': mois_labels,
            'valeurs': montants_mensuels,
            'total_annuel': round(sum(montants_mensuels), 2),
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'ticks': ticks,
            'min_val': min_val,
            'max_val': max_val,
            'annee': annee
        }
    def get_all_by_user(self, user_id: int) -> List[Dict]:
        """Récupère toutes les cotisations pour les contrats d'un utilisateur"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT cc.*, c.employeur, c.employe_id, ti.nom AS type_indemnite_nom
                FROM cotisations_contrat cc
                JOIN contrats c ON cc.contrat_id = c.id
                JOIN types_indemnite ti ON cc.type_indemnite_id = ti.id
                WHERE c.user_id = %s
                ORDER BY c.employeur, ti.nom
                """
                cursor.execute(query, (user_id,))
                rows = cursor.fetchall()
                return rows
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des indemnites pour user_id={user_id}: {e}", exc_info=True)
            return []
    # Dans la classe CotisationContrat
    def prepare_svg_indemnites_mensuelles_employe(self, employe_model, user_id: int, employe_id: int, annee: int, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        montants_mensuels = []
        for mois in range(1, 13):
            total = sum(
                c['montant']
                for c in self.get_total_indemnites_par_mois(user_id, annee, mois)
                if c.get('employe_id') == employe_id
            )
            montants_mensuels.append(round(total, 2))

        min_val = min(montants_mensuels) if montants_mensuels else 0.0
        max_val = max(montants_mensuels) if montants_mensuels else 1.0
        if min_val == max_val:
            max_val = min_val + (10.0 if min_val == 0 else min_val * 0.1)

        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        def y_coord(val):
            return margin_y + plot_height - ((val - min_val) / (max_val - min_val)) * plot_height

        ticks = []
        step = 20
        y_val = math.floor(min_val / step) * step
        while y_val <= max_val + step:
            if y_val >= 0:
                ticks.append({'value': int(y_val), 'y_px': y_coord(y_val)})
            y_val += step

        colonnes_svg = []
        bar_width = plot_width / 12 * 0.7
        for i, montant in enumerate(montants_mensuels):
            x = margin_x + (i + 0.5) * (plot_width / 12) - bar_width / 2
            y_top = y_coord(montant)
            height = plot_height - (y_top - margin_y)
            if height < 0:
                height = 0
                y_top = margin_y + plot_height
            colonnes_svg.append({'x': x, 'y': y_top, 'width': bar_width, 'height': height})

        mois_labels = [f"{m:02d}/{annee}" for m in range(1, 13)]
        
        # Récupérer le nom de l'employé (optionnel, pour le titre)
        employe = employe_model.get_by_id(employe_id, user_id)
        employe_nom = f"{employe['prenom']} {employe['nom']}" if employe else "Employé inconnu"

        return {
            'colonnes': colonnes_svg,
            'mois_labels': mois_labels,
            'valeurs': montants_mensuels,
            'total_annuel': round(sum(montants_mensuels), 2),
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'ticks': ticks,
            'min_val': min_val,
            'max_val': max_val,
            'annee': annee,
            'employe_id': employe_id,
            'employe_nom': employe_nom,
            'type': 'cotisations_employe'
        }
    
class Contrat:
    def __init__(self, db):
        self.db = db
        
    def user_has_types_cotisation_or_indemnite(self, user_id: int, cotisations_contrat_model, indemnites_contrat_model) -> bool:
        cotisations = cotisations_contrat_model.get_all_by_user(user_id)
        indemnites = indemnites_contrat_model.get_all_by_user(user_id)
        return len(cotisations) > 0 or len(indemnites) > 0

    def create_or_update(self, data: Dict) -> bool:
        required_fields = {'user_id', 'employeur', 'heures_hebdo', 'date_debut'}
        if not required_fields.issubset(data.keys()):
            logger.error("Champs requis manquants pour créer/mettre à jour un contrat. Données reçues: {}")
            return None
        try:
            with self.db.get_cursor() as cursor:
                user_id = int(data['user_id'])
                employe_id = int(data['employe_id']) if data.get('employe_id') is not None else None
                employeur = str(data['employeur']).strip()
                heures_hebdo = float(data['heures_hebdo'])
                date_debut = data['date_debut']
                date_fin = data.get('date_fin') or None  # NULL si non fourni
                salaire_horaire = float(data.get('salaire_horaire', 24.05))
                jour_estimation_salaire = int(data.get('jour_estimation_salaire', 15))
                versement_10 = bool(data.get('versement_10', True))
                versement_25 = bool(data.get('versement_25', True))
                if 'id' in data and data['id']:
                    # Mise à jour
                    query = """
                        UPDATE contrats SET
                            user_id = %s,
                            employe_id = %s,
                            employeur = %s,
                            heures_hebdo = %s,
                            date_debut = %s,
                            date_fin = %s,
                            salaire_horaire = %s,
                            jour_estimation_salaire = %s,
                            versement_10 = %s,
                            versement_25 = %s
                        WHERE id = %s
                    """
                    params = (
                        user_id, employe_id, employeur, heures_hebdo,
                        date_debut, date_fin, salaire_horaire,
                        jour_estimation_salaire, versement_10, versement_25,
                        data['id']
                        )
                    cursor.execute(query, params)
                    contrat_id = data['id']
                else:
                    query = """
                    INSERT INTO contrats (
                        user_id, employe_id, employeur, heures_hebdo,
                        date_debut, date_fin, salaire_horaire,
                        jour_estimation_salaire, versement_10, versement_25
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                    params = (
                    user_id, employe_id, employeur, heures_hebdo,
                    date_debut, date_fin, salaire_horaire,
                    jour_estimation_salaire, versement_10, versement_25
                    )
                    cursor.execute(query, params)
                    contrat_id = cursor.lastrowid
            return contrat_id

        except Exception as e:
            logger.error(f"Erreur lors de la création/mise à jour du contrat: {e}")
            return False

    def get_contrat_actuel(self, user_id: int) -> Optional[Dict]:
        """Récupère le contrat en cours pour l'utilisateur (fin null ou future)"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                    SELECT * FROM contrats
                    WHERE user_id = %s
                    AND (date_fin IS NULL OR date_fin >= CURDATE())
                    ORDER BY date_debut ASC
                    LIMIT 1
                """
                cursor.execute(query, (user_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du contrat: {e}")
            return None

    def get_by_id(self, contrat_id: int) -> Optional[Dict]:
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT * FROM contrats WHERE id = %s", (contrat_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur get_by_id contrat {contrat_id}: {e}")
            return None
    def get_all_contrats(self, user_id: int) -> List[Dict]:
        """Liste tous les contrats de l'utilisateur, du plus récent au plus ancien."""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = "SELECT * FROM contrats WHERE user_id = %s ORDER BY date_debut ASC;"
                logger.debug(f"SQL: {query} | Params: {user_id}")
                cursor.execute(query, (user_id,))  # ← CORRIGÉ : virgule ajoutée
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des contrats: {e}")
            return []

    def delete(self, contrat_id: int) -> bool:
        """Supprime un contrat par son id."""
        try:
            with self.db.get_cursor() as cursor:
                query = "DELETE FROM contrats WHERE id = %s;"
                cursor.execute(query, (contrat_id,))
                return True
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du contrat: {e}")
            return False

    def get_contrat_for_date(self, user_id: int, employeur: str, date_str: str) -> Optional[Dict]:
        """Récupère le contrat actif pour une date spécifique"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT * FROM contrats
                WHERE user_id = %s
                AND employeur = %s
                AND date_debut <= %s
                AND (date_fin IS NULL OR date_fin >= %s)
                ORDER BY date_debut DESC
                LIMIT 1
                """
                cursor.execute(query, (user_id, employeur, date_str, date_str))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du contrat pour la date {date_str}: {e}")
            return None

    def get_contrats_actifs(self, user_id: int) -> List[Dict]:
        """Récupère tous les contrats actifs pour un utilisateur"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT * FROM contrats
                WHERE user_id = %s
                AND (date_fin IS NULL OR date_fin >= CURDATE())
                ORDER BY date_debut DESC
                """
                cursor.execute(query, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des contrats actifs: {e}")
            return []

    def get_contrat_for_employe(self, user_id: int, id_employe: int) -> Optional[Dict]:
        """Récupère le contrat associé à un employé spécifique"""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                SELECT c.* FROM contrats c
                JOIN employes e ON c.id = e.id_contrat
                WHERE c.user_id = %s AND e.id_employe = %s
                LIMIT 1
                """
                cursor.execute(query, (user_id, id_employe))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du contrat pour l'employé {id_employe}: {e}")
            return None
    
    def sauvegarder_cotisations_et_indemnites(self, cotisations_contrat_model, indemnites_contrat_model, contrat_id: int, user_id: int, data: Dict)-> bool:
        annee = data.get('annee')
        if not annee:
            raise ValueError("L'annee est requise pour sauvegarder cotisations/indemnites")

        with self.db.get_cursor() as cursor:
            cursor.execute("DELETE FROM cotisations_contrat WHERE contrat_id = %s AND annee = %s", (contrat_id, annee))
            cursor.execute("DELETE FROM indemnites_contrat WHERE contrat_id = %s AND annee = %s", (contrat_id, annee))
            for c in data.get('cotisations', []):
                cotisations_contrat_model.assigner_a_contrat(
                    contrat_id=contrat_id,
                    type_cotisation_id=c['type_id'],
                    taux=c['taux'],
                    annee=annee,
                    base_calcul=c.get('base', 'brut')
                )
            for i in data.get('indemnites', []):
                indemnites_contrat_model.assigner_a_contrat(
                    contrat_id=contrat_id,
                    type_indemnite_id=i['type_id'],
                    valeur=i['valeur'],
                    annee=annee,
                    unite=i.get('unite', 'taux')
                )
            return True

class Employe:

    def __init__(self, db):
        self.db = db
        self.heure_model = HeureTravail(self.db)
      

    def create(self, data: Dict) -> bool:
        """
        créé un employé
        data doit contenir :
        - user_id (int): ID de l'utilisateur propriétaire
        - nom (str)
        - prenom (str)
        - email (str, optionnel)
        - telephone
        - rue
        - code_postal
        - commune
        - genre
        - date_de_naissance
        """
        required = ('user_id', 'nom', 'prenom', 'genre', 'date_de_naissance')
        if not required.issubset(data.keys()):
            raise ValueError("Champs manquants : 'user_id', 'nom', 'prenom', 'genre', 'date_de_naissance', requis")
        try:
            with self.db.get_cursor(commit=True) as cursor:
                query = """
                INSERT INTO employes
                (user_id, nom, prenom, email, telephone, rue, code_postal, commune, genre, date_de_naissance, created_at)
                VALUES (%s, %s, %s, %s,%s, %s, %s, %s, %s, %s, NOW())
                """
                values = (
                    data['user_id'],
                    data['nom'],
                    data['prenom'],
                    data.get('email'),
                    data.get('telephone'),
                    data.get('rue'),
                    data.get('code_postal'),
                    data.get('commune'),
                    data['genre'],
                    data['date_de_naissance']
                )
                cursor.execute(query, values)
            return True
        except Error as e:
            logger.error(f"Erreur lors de création fr l'employe: {e}")
            return False


    def get_all_by_user(self, user_id: int) -> List[Dict]:
        """
        Récupère les employés lié à un utilisateur
        """
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT * FROM employes
                WHERE user_id = %s
                ORDER BY nom, prenom
                """
                cursor.execute(query, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f'Erreur de récupération des employées pour user_id {user_id}: {e}')

    def get_by_id(self, employe_id: int, user_id : int) -> Optional[Dict]:
        """
        récupère un employe avec vérification de sécurité"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT * FROM employes
                WHERE id = %s AND user_id = %s
                """
                cursor.execute(query, (employe_id, user_id))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f'Erreur de récupération employe ID {employe_id} de user_id {user_id}: {e}')
            return None

    def update(self, employe_id : int, user_id : int, data: dict) -> bool:
        """
        Met à jour les données d'un employé (en vérifiant son appartenance à un user_id)
        """
        allowed = {'nom', 'prenom', 'email', 'telephone', 'rue', 'code_postal', 'commune', 'genre', 'date_de_naissance'}
        update_fields = {k: v for k, v in data.items() if k in allowed}
        if not update_fields:
            return False

        set_clause = ", ".join([f"{k} = %s" for k in update_fields])
        params = list(update_fields.values()) + [employe_id, user_id]
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(f"""
                        UPDATE employes
                        SET {set_clause}
                        WHERE id = %s AND user_id = %s
                        """, params)
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f'Erreur lors de la mise à jour employe {employe_id} pour {data}: {e}')
            return False

    def delete(self, employe_id: int, user_id: int) -> bool:
        """
        supprime un employe avec vérification
        """
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                            DELETE FROM employes
                            WHERE id = %s AND user_id = %s
                            """, (employe_id, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f'Erreur dans la suppresion employe {employe_id} de user {user_id}; {e}')
            return False

    def get_heures_mois(self, annee: int, mois: int) -> float:
        """
        Récupère le total des heures travaillées pour un employé sur un mois donné
        """
        if not hasattr(self, 'id'):
            raise ValueError("L'instance Employe n'a pas d'ID. Utilisez get_by_id() pour charger un employé.")
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT SUM(total_h) AS total_heures
                FROM heures_travail
                WHERE employe_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
                """
                cursor.execute(query, (self.id, annee, mois))
                result = cursor.fetchone()
                return float(result['total_heures']) if result and result['total_heures'] else 0.0
        except Exception as e:
            logger.error(f'Erreur récupération heures mois {annee}-{mois} : {e}')
            return 0.0
    def get_salaire_mois(self, annee: int, mois: int) -> dict:
        """
        Récupère le salaire total pour un employé sur un mois donné
        """
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT SUM(montant) AS total_salaire, SUM(retentions) AS total
                FROM salaires
                WHERE EXTRACT(YEAR FROM date_paiement) = %s AND EXTRACT(MONTH FROM date_paiement) = %s
                """
                cursor.execute(query, (annee, mois))
                result = cursor.fetchone()
                return {
                    'total_salaire': float(result['total_salaire']) if result and result['total_salaire'] else 0.0,
                    'total_retentions': float(result['total']) if result and result['total'] else 0.0
                }
        except Exception as e:
            logger.error(f'Erreur récupération salaire mois {annee}-{mois} : {e}')
            return {'total_salaire': 0.0, 'total_retentions': 0.0}

    def recalculer_salaire_mois(self, annee: int, mois: int) -> bool:
        """
        Recalcule les salaires pour un employé sur un mois donné
        """
        try:
            heures_travail = self.get_heures_mois(annee, mois)
            salaire_info = self.get_salaire_mois(annee, mois)
            # Logique de recalcul ici (exemple simple)
            salaire_net = salaire_info['total_salaire'] - salaire_info['total_retentions']
            # Mettre à jour la synthèse mensuelle
            #   ...
            # Pour l'instant, on retourne simplement True
            #
            #
            return True
        except Exception as e:
            logger.error(f'Erreur recalcul salaire mois {annee}-{mois} : {e}')
            return False
    def get_contrats_actifs(self) -> list:
        """
        Récupère les contrats actifs pour un employé
        """
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT * FROM contrats
                WHERE employe_id = %s AND actif = TRUE
                """
                cursor.execute(query, (self.id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f'Erreur récupération contrats actifs pour employe {self.id} : {e}')
            return []
    def get_employe_by_id_and_code(self, employe_id: int, code: str) -> Optional[Dict]:
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                SELECT * FROM employes
                WHERE id = %s AND code_acces_salaire = %s
            """, (employe_id, code))
            return cursor.fetchone()
    def verifier_code_acces(self, employe_id: int, code: str) -> Optional[Dict]:
        """
        Retourne les infos de l'employé si le couple (id, code) est valide.
        """
        if not employe_id or not code:
            return None
        with self.db.get_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT id, user_id, prenom, nom, code_acces_salaire
                FROM employes
                WHERE id = %s AND code_acces_salaire = %s
            """, (employe_id, code))
            return cursor.fetchone()


class HeureTravail:
    def __init__(self, db):
        self.db = db

    def create_or_update(self, data: dict, cursor=None) -> bool:
        """Version améliorée acceptant un curseur externe"""
        if cursor:
            # Utiliser le curseur fourni
            return self._execute_create_or_update(data, cursor)
        else:
            # Gérer sa propre connexion comme avant, mais avec le gestionnaire de contexte
            try:
                with self.db.get_cursor(commit=True) as new_cursor:
                    success = self._execute_create_or_update(data, new_cursor)
                    return success
            except Exception as e:
                logger.error(f"Impossible d'obtenir une connexion ou erreur d'exécution: {str(e)}")
                return False

    def _execute_create_or_update(self, data: dict, cursor) -> bool:
        """Logique centrale de création/mise à jour"""
        try:
            cleaned_data = self._clean_data(data)
            date_obj = datetime.fromisoformat(cleaned_data['date']).date()

            # Vérifier si l'enregistrement existe déjà
            cursor.execute(
                """
                SELECT * FROM heures_travail
                WHERE date = %s 
                    AND user_id = %s 
                    AND employeur = %s 
                    AND id_contrat = %s
                    AND (
                        (employe_id IS NULL AND %s IS NULL)
                        OR (employe_id = %s) 
                    AND type_heures = %s
                """,
                date_obj,
                cleaned_data['user_id'],
                cleaned_data['employeur'],
                cleaned_data['id_contrat'],
                cleaned_data['employe_id'],
                cleaned_data['employe_id'],
                cleaned_data['type_heures']
            )
            existing = cursor.fetchone()
            if existing:
                heure_travail_id = existing['id']
            else:
                heure_travail_id = None
            # Préparer les valeurs avec fallback
            values = {
                'date': date_obj,
                'user_id': cleaned_data['user_id'],
                'employe_id' : cleaned_data['employe_id'],
                'employeur': cleaned_data['employeur'],
                'id_contrat': cleaned_data.get('id_contrat'),
                'vacances': cleaned_data.get('vacances', False),
                'type_heures': cleaned_data['type_heures'],
                'jour_semaine': date_obj.strftime('%A'),
                'semaine_annee': date_obj.isocalendar()[1],
                'mois': date_obj.month  # Calculé plus tard
            }
            if heure_travail_id:
                cursor.execute("""
                UPDATE heures_travail
                SET type_heures = %(type_heures)s,
                    vacances = %(vacances)s,
                    jour_semaine = %(jour_semaine)s,
                    semaine_annee = %(semaine_annee)s,
                    mois = %(mois)s
                    WHERE id = %(id)s
                """, {**values, 'id': heure_travail_id})
            else:
                cursor.execute("""
                            INSERT INTO heures_travail
                            (date, user_id, employe_id, employeur, id_contrat, type_heures, vacances, jour_semaine, semaine_annee, mois)
                            VALUES (%(date)s, %(user_id)s, %(employe_id)s, %(employeur)s, %(id_contrat)s, %(type_heures)s, %(vacances)s, %(jour_semaine)s, %(semaine_annee)s, %(mois)s)
                            """, values)
                heure_travail_id = cursor.lastrowid
            self._update_plages_horaires(cursor, heure_travail_id, cleaned_data.get('plages', []))
            total_h = self.calculer_total_heures(heure_travail_id, cursor)
            cursor.execute(
                """
                UPDATE heures_travail SET total_h = %s WHERE id = %s
                """,(total_h, heure_travail_id)
            )
            return True
        except Exception as e:
            logger.error(f"Erreur _execute_create_or_update: {str(e)}")
            return False

            # Gestion des champs horaires avec protection
            #for field in ['h1d', 'h1f', 'h2d', 'h2f']:
            #    if field in cleaned_data:
            #        values[field] = cleaned_data[field]
            #    elif existing:
            #        values[field] = existing.get(field)
            #    else:
            #        values[field] = None

            # Calculer le total
            #values['total_h'] = self.calculer_heures(
            #    values.get('h1d'),
            #    values.get('h1f'),
            #    values.get('h2d'),
            #    values.get('h2f')
            #)

            # Requête UPSERT unique
            #upsert_query = """
            #INSERT INTO heures_travail
            #(date, user_id, employe_id, employeur, id_contrat, h1d, h1f, h2d, h2f, total_h, type_heures, vacances, jour_semaine, semaine_annee, mois)
            #VALUES (%(date)s, %(user_id)s, %(employe_id)s, %(employeur)s, %(id_contrat)s, %(h1d)s, %(h1f)s, %(h2d)s, %(h2f)s, %(total_h)s, %(type_heures)s, %(vacances)s, %(jour_semaine)s, %(semaine_annee)s, %(mois)s)
            #ON DUPLICATE KEY UPDATE
            #    h1d = COALESCE(VALUES(h1d), h1d),
            #    h1f = COALESCE(VALUES(h1f), h1f),
            #    h2d = COALESCE(VALUES(h2d), h2d),
            #    h2f = COALESCE(VALUES(h2f), h2f),
            #    total_h = VALUES(total_h),
            #    type_heures = VALUES(type_heures),         -- ✅
            #    vacances = COALESCE(VALUES(vacances), vacances),
            #    jour_semaine = VALUES(jour_semaine),
            #    semaine_annee = VALUES(semaine_annee),
            #    mois = VALUES(mois);
            #"""

            # Ajouter les métadonnées calculées
            #values.update({
            #    'jour_semaine': date_obj.strftime('%A'),
            #    'semaine_annee': date_obj.isocalendar()[1],
            #    'mois': date_obj.month
            #})

            #cursor.execute(upsert_query, values)
            #return True

        #except Exception as e:
        #    logger.error(f"Erreur _execute_create_or_update: {str(e)}")
        #    return False

    def _update_plages_horaires(self, cursor, heure_travail_id: int, plages: List[Dict]) -> None:
        """Met à jour les plages horaires associées à un enregistrement de travail"""
        try:
            # 1. Supprimer les anciennes plages
            cursor.execute("DELETE FROM plages_horaires WHERE heure_travail_id = %s", (heure_travail_id,))

            # 2. Insérer les nouvelles plages
            for index, plage in enumerate(plages):
                debut = plage.get('debut')
                fin = plage.get('fin')
                if debut and fin:
                    cursor.execute("""
                        INSERT INTO plages_horaires (heure_travail_id, ordre, debut, fin)
                        VALUES (%s, %s, %s, %s)
                    """, (heure_travail_id, index + 1, debut, fin))
        except Exception as e:
            logger.error(f"Erreur _update_plages_horaires: {str(e)}")
            raise

    def _clean_data(self, data: dict) -> dict:
        cleaned = data.copy()

        if 'plages' in cleaned:
            plages_nettoyees = []
            for plage in cleaned['plages']:
                plage_clean = {
                    'debut': str(plage.get('debut', '')).strip() or None,
                    'fin': str(plage.get('fin', '')).strip() or None
                }
                if plage_clean['debut'] or plage_clean['fin']:
                    plages_nettoyees.append(plage_clean)
            cleaned['plages'] = plages_nettoyees
        if 'plages' not in cleaned or not cleaned['plages']:
            cleaned['plages'] = []
            time_fields = ['h1d', 'h1f', 'h2d', 'h2f']
            field_values = {}
            for field in time_fields:
                field_values[field] = str(cleaned.get(field, '')).strip() or None
            if field_values['h1d'] or field_values['h1f']:
                cleaned['plages'].append({
                    'debut': field_values['h1d'],
                    'fin': field_values['h1f']
                })
            if field_values['h2d'] or field_values['h2f']:
                cleaned['plages'].append({
                    'debut': field_values['h2d'],
                    'fin' : field_values['h2f']
                })
        if 'vacances' in cleaned:
            cleaned['vacances'] = bool(cleaned['vacances'])
        if 'employe_id' in cleaned:
            if cleaned['employe_id'] is not None:
                cleaned['employe_id'] = int(cleaned['employe_id'])
        else:
            cleaned['employe_id'] = None
        cleaned['type_heures'] = cleaned.get('type_heures', 'reelles')
        if cleaned['type_heures'] not in ('reelles', 'simulees'):
            cleaned['type_heures'] = 'reelles'
        required_fields = ['user_id', 'date', 'employeur', 'id_contrat']
        for field in required_fields:
            if field not in cleaned or not cleaned[field]:
                raise ValueError(f"{field} manquant dans les données")
        return cleaned

        # Nettoyer uniquement les champs time présents
        #time_fields = ['h1d', 'h1f', 'h2d', 'h2f']
        #for field in time_fields:
        #    if field in cleaned:
        #        value = str(cleaned[field]).strip()
        #        cleaned[field] = value if value else None

        # Normaliser le champ vacances si présent
        #if 'vacances' in cleaned:
        #    cleaned['vacances'] = bool(cleaned['vacances'])
        #if 'employe_id' in cleaned:
        # Accepte None ou un entier
        #    if cleaned['employe_id'] is not None:
        #        cleaned['employe_id'] = int(cleaned['employe_id'])
        #else:
        #    cleaned['employe_id'] = None

        # type_heures : 'reelles' ou 'simulees'
        #cleaned['type_heures'] = cleaned.get('type_heures', 'reelles')
        #if cleaned['type_heures'] not in ('reelles', 'simulees'):
        #    cleaned['type_heures'] = 'reelles'

        # Validation des champs obligatoires
        #if 'user_id' not in cleaned or cleaned['user_id'] is None:
        #    raise ValueError("user_id manquant dans les données")

        #if 'date' not in cleaned or not cleaned['date']:
        #    raise ValueError("date manquante dans les données")
        #if 'employeur' not in cleaned or not cleaned['employeur']:
        #    raise ValueError("employeur manquant dans les données")
        #if 'id_contrat' not in cleaned or cleaned['id_contrat'] is None:
        #    raise ValueError("id_contrat manquant dans les données")

        #return cleaned

    def calculer_total_heures(self, heure_travail_id: int, cursor)-> float:
        """Calcule le total des heures à partir des plages"""
        def time_to_seconds(t: time) -> int:
            return t.hour * 3600 + t.minute * 60 + t.second
        query = """
            SELECT debut, fin
            FROM plages_horaires
            WHERE heure_travail_id = %s
            ORDER BY ordre"""
        cursor.execute(query, (heure_travail_id,))
        plages = cursor.fetchall()
        total = 0.0

        for plage in plages:
            debut = plage['debut']
            fin = plage['fin']
            if debut and fin:
                debut_seconds = time_to_seconds(debut)
                fin_seconds = time_to_seconds(fin)
                if fin_seconds < debut_seconds:
                    fin_seconds += 24 *3600
                total += (fin_seconds - debut_seconds) / 3600
        return round(total,2)

    def get_by_date(self, date_str: str, user_id: int, employeur: str, id_contrat: int) -> Optional[Dict]:
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = """
                    SELECT ht.*,
                        JSON_ARRAYAGG(
                            JSON_OBJECT('ordre', ph.ordre, 'debut', ph.debut, 'fin', ph.fin)
                        ) AS plages
                    FROM heures_travail ht
                    LEFT JOIN plages_horaires ph ON ht.id = ph.heure_travail_id
                    WHERE ht.date = %s AND ht.user_id = %s AND ht.employeur = %s AND ht.id_contrat = %s
                    GROUP BY ht.id
                """
                cursor.execute(query, (date_str, user_id, employeur, id_contrat))
                jour = cursor.fetchone()

                if not jour:
                    return None

                plages_json = jour.get('plages')
                if plages_json and plages_json != 'null':
                    try:
                        jour['plages'] = json.loads(plages_json)
                    except (json.JSONDecodeError, TypeError):
                        jour['plages'] = []
                else:
                    jour['plages'] = []

                return jour

        except Exception as e:
            logger.error(f"Erreur get_by_date pour {date_str}: {str(e)}")
            return None
        
    def get_jour_travail(self, mois:int, semaine:int, user_id: int, employeur: str, id_contrat: int) -> List[Dict]:
        """ récupère les jours de travauk avec plages"""
        try:
            with self.db.get_cursor() as cursor:
                if semaine > 0:
                    query = """
                    SELECT ht.*,
                            JSON_ARRAYAGG(
                                    JSON_OBJECT('ordre', ph.ordre, 'debut', ph.debut, 'fin', ph.fin)
                            ) as plages
                        FROM heures_travail ht
                        LEFT JOIN plages_horaires ph ON ht.id = ph.heure_travail_id
                        WHERE ht.semaine_annee = %s AND ht.user_id = %s AND ht.employeur = %s AND ht.id_contrat = %s
                        GROUP BY ht.id
                        ORDER BY ht.date
                    """
                    params = (semaine, user_id, employeur, id_contrat)
                else:
                    query =  """
                        SELECT ht.*,

                            JSON_ARRAYAGG(
                               JSON_OBJECT('ordre', ph.ordre, 'debut', ph.debut, 'fin', ph.fin)
                           ) as plages
                        FROM heures_travail ht
                        LEFT JOIN plages_horaires ph ON ht.id = ph.heure_travail_id
                        WHERE ht.mois = %s AND ht.user_id = %s AND ht.employeur = %s AND ht.id_contrat = %s
                        GROUP BY ht.id
                        ORDER BY ht.date
                    """
                    params = (mois, user_id, employeur, id_contrat)
                cursor.execute(query, params)
                jours = cursor.fetchall()

                for jour in jours:
                    if jour['plages'] and jour['plages'][0] is not None:
                        try:
                            jour['plages'] = json.loads(jour['plages'])
                            for plage in jour['plages']:
                                for field in ['debut', 'fin']:
                                    if plage.get(field) and hasattr(plage[field], 'total_seconds'):
                                        total_seconds = plage[field].total_seconds
                                        hours = int(total_seconds // 3600)
                                        minutes  = int((total_seconds % 3600) // 60)
                                        plage[field] = f"{hours:02d}:{minutes:02d}"
                        except Exception:
                            jour['plages'] = []
                    else:
                        jour['plages'] = []
                return jours
        except Exception as e:
            logger.error(f"Erreur get_jour_travail: {str(e)}")
            return []

    def calculer_heures(self, h1d: str, h1f: str, h2d: str, h2f: str) -> float:
        """Calcule le nombre d'heures total"""
        def diff_heures(debut, fin):
            if debut and fin:
                start = datetime.strptime(debut, '%H:%M')
                end = datetime.strptime(fin, '%H:%M')
                delta = end - start
                return max(delta.total_seconds() / 3600, 0)
            return 0.0

        total = diff_heures(h1d, h1f) + diff_heures(h2d, h2f)
        return round(total, 2)

    #def get_by_date(self, date_str: str, user_id: int, employeur: str, id_contrat: int) -> Optional[Dict]:
    #    """Récupère les données pour une date et un utilisateur donnés"""
    #    try:
    #        with self.db.get_cursor() as cursor:
    #            query = "SELECT * FROM heures_travail WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s"
    #            logger.debug(f"[get_by_date] Query: {query} avec params: ({date_str}, {user_id}, {employeur}, {id_contrat})")
    #
    #            cursor.execute(query, (date_str, user_id, employeur, id_contrat))
    #            jour = cursor.fetchone()
    #
    #            if jour:
    #                logger.debug(f"[get_by_date] Données trouvées pour {date_str}, user_id: {user_id}, employeur: {employeur}, id_contrat: {id_contrat}  ")
    #                self._convert_timedelta_fields(jour, ['h1d', 'h1f', 'h2d', 'h2f'])
    #            else:
    #               logger.debug(f"[get_by_date] Aucune donnée trouvée pour {date_str}, user_id: {user_id}, employeur: {employeur}, id_contrat: {id_contrat}  ")
    #
    #            return jour
    #
    #    except Exception as e:
    #        logger.error(f"Erreur get_by_date pour {date_str}: {str(e)}")
    #        return []]

    def get_jours_travail(self, mois: int, semaine: int, user_id: int, employeur: str, id_contrat: int) -> List[Dict]:
        """Récupère les jours de travail pour une période"""
        try:
            with self.db.get_cursor() as cursor:
                if semaine > 0:
                    query = "SELECT * FROM heures_travail WHERE semaine_annee = %s AND user_id = %s AND employeur = %s AND id_contrat = %s ORDER BY date"
                    params = (semaine, user_id, employeur, id_contrat)
                else:
                    query = "SELECT * FROM heures_travail WHERE mois = %s AND user_id = %s AND employeur = %s AND id_contrat = %s ORDER BY date"
                    params = (mois, user_id, employeur, id_contrat)

                logger.debug(f"[get_jours_travail] Query: {query} avec params: {params}")
                cursor.execute(query, params)
                jours = cursor.fetchall()

                logger.debug(f"[get_jours_travail] {len(jours)} jours trouvés")

                for jour in jours:
                    self._convert_timedelta_fields(jour, ['h1d', 'h1f', 'h2d', 'h2f'])

                return jours

        except Exception as e:
            logger.error(f"Erreur get_jours_travail: {str(e)}")
            return []

    def delete_by_date(self, date_str: str, user_id: int, employeur: str, id_contrat: int) -> bool:
        """Supprime les données pour une date et un utilisateur donnés"""
        try:
            with self.db.get_cursor(commit=True) as cursor:
                query = "DELETE FROM heures_travail WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s"
                logger.debug(f"[delete_by_date] Query: {query} avec params: ({date_str}, {user_id}, {employeur}, {id_contrat})")

                cursor.execute(query, (date_str, user_id, employeur, id_contrat))
                rows_affected = cursor.rowcount

                logger.debug(f"[delete_by_date] {rows_affected} ligne(s) supprimée(s) pour {date_str}")
                return True

        except Exception as e:
            logger.error(f"Erreur delete_by_date pour {date_str}: {str(e)}")
            return False

    def _convert_timedelta_fields(self, record: dict, fields: list) -> None:
        """Convertit les champs timedelta en chaîne HH:MM dans un dictionnaire"""
        for field in fields:
            val = record.get(field)
            if val:
                if hasattr(val, 'total_seconds'):
                    total_seconds = val.total_seconds()
                    hours = int(total_seconds // 3600)
                    minutes = int((total_seconds % 3600) // 60)
                    record[field] = f"{hours:02d}:{minutes:02d}"
                else:
                    record[field] = str(val)
            else:
                record[field] = ''

    def get_total_heures_mois(self, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int) -> float:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT SUM(total_h) FROM heures_travail
                WHERE user_id = %s AND employeur = %s AND id_contrat = %s AND YEAR(date) = %s AND MONTH(date) = %s
                """
                cursor.execute(query, (user_id, employeur, id_contrat, annee, mois))
                result = cursor.fetchone()
                total = float(result['SUM(total_h)']) if result and result['SUM(total_h)'] else 0.0
                logger.info(f"get_total_heures_mois → user={user_id}, mois={mois}/{annee}, employeur={employeur}, contrat={id_contrat} → total={total}")
                return total
        except Exception as e:
            logger.error(f"Erreur get_total_heures_mois: {e}")
            return 0.0

    def get_heures_periode(self, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int, start_day: int, end_day: int) -> float:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT SUM(total_h) FROM heures_travail
                WHERE user_id = %s AND employeur = %s AND id_contrat = %s
                AND YEAR(date) = %s
                AND MONTH(date) = %s
                AND DAY(date) BETWEEN %s AND %s
                """
                cursor.execute(query, (user_id, employeur, id_contrat, annee, mois, start_day, end_day))
                result = cursor.fetchone()
                total = float(result['SUM(total_h)']) if result and result['SUM(total_h)'] else 0.0
                logger.info(f"get_heures_periode → user={user_id}, mois={mois}/{annee}, jours={start_day}-{end_day}, employeur={employeur}, contrat={id_contrat} → total={total}")
                return total
        except Exception as e:
            logger.error(f"Erreur get_heures_periode: {e}")
            return 0.0

    def importer_depuis_csv(self, fichier_csv: str, user_id: int) -> int:
        """
        Importer les heures depuis un fichier CSV
        - Ne remplace pas les valeurs existantes par NULL
        - Conserve les anciennes heures si la cellule est vide
        """
        lignes_importees = 0
        try:
            with self.db.get_cursor(commit=True) as cursor:
                with open(fichier_csv, newline='', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)

                    for row in reader:
                        date_str = row.get('date')
                        employeur = row.get('employeur')
                        id_contrat = row.get('id_contrat')
                        if id_contrat is None:
                            logger.warning(f"[Import CSV] id_contrat manquant pour la ligne avec date : {row}. Ligne ignorée.")
                            continue
                        try:
                            id_contrat = int(id_contrat)
                        except ValueError:
                            logger.warning(f"[Import CSV] id_contrat invalide pour la ligne avec date : {id_contrat}")
                            continue
                        if not date_str or not employeur:
                            continue

                        try:
                            date_obj = datetime.fromisoformat(date_str).date()
                        except ValueError:
                            logger.warning(f"[Import CSV] Date invalide ignorée : {date_str}")
                            continue

                        h1d = row.get('h1d') or None
                        h1f = row.get('h1f') or None
                        h2d = row.get('h2d') or None
                        h2f = row.get('h2f') or None
                        vacances = True if str(row.get('vacances')).strip().lower() in ('1', 'true', 'oui') else False

                        cursor.execute(
                            "SELECT * FROM heures_travail WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s",
                            (date_obj, user_id, employeur, id_contrat)
                        )
                        existing = cursor.fetchone()

                        if existing:
                            h1d = h1d or existing.get('h1d')
                            h1f = h1f or existing.get('h1f')
                            h2d = h2d or existing.get('h2d')
                            h2f = h2f or existing.get('h2f')
                            vacances = vacances if row.get('vacances') else existing.get('vacances')
                            total_h = self.calculer_heures(h1d, h1f, h2d, h2f)

                            cursor.execute("""
                                UPDATE heures_travail
                                SET h1d = %s, h1f = %s, h2d = %s, h2f = %s,
                                    total_h = %s, vacances = %s,
                                    jour_semaine = %s, semaine_annee = %s, mois = %s
                                WHERE id = %s
                            """, (
                                h1d, h1f, h2d, h2f, total_h, vacances,
                                date_obj.strftime('%A'), date_obj.isocalendar()[1], date_obj.month,
                                existing['id']
                            ))
                        else:
                            total_h = self.calculer_heures(h1d, h1f, h2d, h2f)
                            cursor.execute("""
                                INSERT INTO heures_travail
                                (date, jour_semaine, semaine_annee, mois,
                                h1d, h1f, h2d, h2f, total_h, vacances, user_id, employeur, id_contrat)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """, (
                                date_obj, date_obj.strftime('%A'), date_obj.isocalendar()[1], date_obj.month,
                                h1d, h1f, h2d, h2f, total_h, vacances, user_id, employeur, id_contrat
                            ))
                        lignes_importees += 1

            logger.info(f"[Import CSV] {lignes_importees} lignes importées avec succès")
            return lignes_importees

        except Exception as e:
            logger.error(f"[Import CSV] Erreur : {e}")
            return 0

    def get_heures_employe_mois(self, employe_id: int, annee: int, mois: int) -> float:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT SUM(total_h) FROM heures_travail
                    WHERE employe_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
                """
                cursor.execute(query, (employe_id, annee, mois))
                result = cursor.fetchone()
                return float(result['SUM(total_h)']) if result and result['SUM(total_h)'] else 0.0
        except Exception as e:
            logger.error(f"Erreur get_heures_employe_mois: {e}")
            return 0.0

    def get_heures_par_employe_mois(self, employe_id: int, annee: int, mois: int) -> List[Dict]:
        with self.db.get_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT date, total_h, vacances, plages
                FROM heures_travail
                WHERE employe_id = %s AND YEAR(date) = %s AND MONTH(date) = %s
                ORDER BY date
            """, (employe_id, annee, mois))
            return cursor.fetchall()

    @staticmethod
    def calculer_heures_static(h1d: str, h1f: str, h2d: str, h2f: str) -> float:
        """Version statique de calculer_heures pour utilisation hors instance"""
        def diff_heures(debut, fin):
            if debut and fin:
                start = datetime.strptime(debut, '%H:%M')
                end = datetime.strptime(fin, '%H:%M')
                delta = end - start
                return max(delta.total_seconds() / 3600, 0)
            return 0.0

        total = diff_heures(h1d, h1f) + diff_heures(h2d, h2f)
        return round(total, 2)

    def has_hours_for_employeur_and_contrat(self, user_id: int, employeur: str, id_contrat: int) -> bool:
        """Vérifie si l'utilisateur a des heures enregistrées pour un employeur donné"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT 1
                    FROM heures_travail
                    WHERE user_id = %s AND employeur = %s AND id_contrat = %s
                    LIMIT 1
                """
                cursor.execute(query, (user_id, employeur, id_contrat))
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            logger.error(f"Erreur has_hours_for_employeur: {e}")
            return False

    def get_h1d_h2f_for_period(self, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int = None, semaine: int = None) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                if semaine is not None:
                    query = """
                        SELECT ht.date,
                            MIN(ph.debut) as h1d,
                            MAX(ph.fin) as h2f
                        FROM heures_travail ht
                        LEFT JOIN plages_horaires ph ON ht.id = ph.heure_travail_id
                        WHERE ht.user_id = %s AND ht.employeur = %s AND ht.id_contrat = %s
                        AND YEAR(ht.date) = %s AND ht.semaine_annee = %s
                        GROUP BY ht.date
                        ORDER BY ht.date
                        """
                    params = (user_id, employeur, id_contrat, annee, semaine)
                elif mois is not None:
                    query = """
                            SELECT ht.date,
                                MIN(ph.debut) as h1d,
                                MAX(ph.fin) as h2f
                                FROM heures_travail ht
                                LEFT JOIN plages_horaires ph ON ht.id = ph.heure_travail_id
                                WHERE ht.user_id = %s AND ht.employeur = %s AND ht.id_contrat = %s
                                AND YEAR(date) = %s AND ht.mois = %s
                                GROUP BY ht.date
                                ORDER BY ht.date
                                """
                    params = (user_id, employeur, id_contrat, annee, mois)
                else:
                    raise ValueError("Vous devez spéciier soit 'mois', soit 'semaine'.")
                cursor.execute(query, params)
                rows = cursor.fetchall()

                for row in rows:
                    self._convert_timedelta_fields(row, ['h1d', 'h2f'])
            return rows
        except Exception as e:
            logger.error("Erreur get_h1d_h2f_for period: {e}")
            return []







    #def get_h1d_h2f_for_period(self, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int = None, semaine: int = None) -> List[Dict]:
    #    """
    #    Récupère les heures de début (h1d) et de fin (h2f) pour une période donnée.
    #    Si 'mois' est spécifié, récupère les données du mois.
    #    Si 'semaine' est spécifiée, récupère les données de la semaine.
    #    """
    #    try:
    #        with self.db.get_cursor() as cursor:
    #            if semaine is not None:
    #                query = """
    #                SELECT date, h1d, h2f
    #                FROM heures_travail
    #                WHERE user_id = %s AND employeur = %s AND id_contrat = %s
    #                AND YEAR(date) = %s AND semaine_annee = %s
    #                ORDER BY date
    #                """
    #                params = (user_id, employeur, id_contrat, annee, semaine)
    #            elif mois is not None:
    #                query = """
    #                SELECT date, h1d, h2f
    #                FROM heures_travail
    #                WHERE user_id = %s AND employeur = %s AND id_contrat = %s
    #                AND YEAR(date) = %s AND mois = %s
    #                ORDER BY date
    #                """
    #                params = (user_id, employeur, id_contrat, annee, mois)
    #            else:
    #                # Si ni mois ni semaine n'est spécifié, on pourrait récupérer l'année entière
    #                # ou lever une erreur. Ici, on lève une erreur.
    #                raise ValueError("Vous devez spécifier soit 'mois', soit 'semaine'.")
#
    #            cursor.execute(query, params)
    #            rows = cursor.fetchall()
#
    #            # Convertir les timedelta en HH:MM pour l'affichage
    #            for row in rows:
    #                self._convert_timedelta_fields(row, ['h1d', 'h2f'])
#
    #            return rows
    #    except Exception as e:
    #        logger.error(f"Erreur get_h1d_h2f_for_period: {e}")
    #        return []

    #def get_jour_travaille(self, date_str: str, user_id: int, employeur: str, id_contrat: int) -> Optional[Dict]:
    #    """
    #    Récupère les heures de début (h1d) et de fin (h2f) pour une date spécifique.
    #    """
    #    try:
    #        with self.db.get_cursor() as cursor:
    #            query = """
    #            SELECT date, h1d, h2f
    #            FROM heures_travail
    #            WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s
    #            """
    #            cursor.execute(query, (date_str, user_id, employeur, id_contrat))
    #            jour = cursor.fetchone()
    #            if jour:
    #                self._convert_timedelta_fields(jour, ['h1d', 'h2f'])
    #            return jour
    #    except Exception as e:
    #        logger.error(f"Erreur get_jour_travaille pour {date_str}: {e}")
    #        return None

    def time_to_minutes(self, time_str: str) -> int:
        """
        Convertit une chaîne 'HH:MM' en minutes depuis minuit.
        Retourne -1 si la chaîne est vide ou invalide.
        """
        if not time_str or time_str == '':
            return -1
        try:
            parts = time_str.split(':')
            if len(parts) != 2:
                return -1
            hours = int(parts[0])
            minutes = int(parts[1])
            return hours * 60 + minutes
        except (ValueError, AttributeError):
            return -1

    def get_h1d_h2f_for_period_with_employe(self, contrat_model, user_id: int, annee: int,mois: Optional[int] = None,semaine: Optional[int] = None, employe_id: Optional[int] = None ) -> List[Dict]:
        # On récupère d’abord les contrats de l’utilisateur
        contrats = contrat_model.get_all_contrats(user_id)
        if not contrats:
            return []

        # Extraire les paires (employeur, id_contrat)
        conditions = []
        params = [user_id, annee]
        if employe_id is not None:
            params.append(employe_id)
            employeur_clause = "AND ht.employe_id = %s"
        else:
            employeur_clause = "AND ht.employe_id IS NULL"

        if semaine is not None:
            time_clause = "AND ht.semaine_annee = %s"
            params.append(semaine)
        elif mois is not None:
            time_clause = "AND ht.mois = %s"
            params.append(mois)
        else:
            raise ValueError("Spécifiez mois ou semaine")

        query = f"""
            SELECT ht.date, MIN(ph.debut) as h1d, MAX(ph.fin) as h2f
            FROM heures_travail ht
            LEFT JOIN plages_horaires ph ON ht.id = ph.heure_travail_id
            WHERE ht.user_id = %s
            {employeur_clause}
            AND YEAR(ht.date) = %s
            {time_clause}
            GROUP BY ht.date
            ORDER BY ht.date
        """
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                self._convert_timedelta_fields(row, ['h1d', 'h2f'])
            return rows

class Salaire:
    def __init__(self, db):
        self.db = db



    def create(self, data: dict) -> bool:
        try:
            with self.db.get_cursor() as cursor:
                if not cursor:
                    return False

                query = """
                INSERT INTO salaires
                (employe_id, mois, annee, heures_reelles, salaire_horaire,
                salaire_calcule, salaire_net, salaire_verse, acompte_25, acompte_10,
                acompte_25_estime, acompte_10_estime, difference, difference_pourcent, user_id, employeur, id_contrat)
                VALUES (%s, %s, %s, %s, %s, %s, %s,%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """
                values = (
                    data.get('employe_id'),
                    data['mois'], data['annee'], data['heures_reelles'],
                    data.get('salaire_horaire', 27.12),
                    data.get('salaire_calcule'),
                    data.get('salaire_net'),
                    data.get('salaire_verse'),
                    data.get('acompte_25'),
                    data.get('acompte_10'),
                    data.get('acompte_25_estime'),
                    data.get('acompte_10_estime'),
                    data.get('difference'),
                    data.get('difference_pourcent'),
                    data['user_id'],
                    data['employeur'],
                    data.get('id_contrat')
                )
                cursor.execute(query, values)
            return True
        except Exception as e:
            logger.error(f"Erreur création salaire: {e}")
            return False

    def update(self, salaire_id: int, data: dict) -> bool:
        allowed_fields = {
            'mois', 'annee', 'heures_reelles', 'salaire_horaire',
            'salaire_calcule', 'salaire_net', 'salaire_verse',
            'acompte_25', 'acompte_10', 'acompte_25_estime',
            'acompte_10_estime', 'difference', 'difference_pourcent'
        }

        # Filtrer les champs autorisés
        update_data = {k: v for k, v in data.items() if k in allowed_fields}

        if not update_data:
            return False

        set_clauses = ", ".join([f"{k} = %s" for k in update_data.keys()])
        values = list(update_data.values()) + [salaire_id]

        try:
            with self.db.get_cursor() as cursor:
                query = f"UPDATE salaires SET {set_clauses} WHERE id = %s"
                cursor.execute(query, values)
            return True
        except Exception as e:
            logger.error(f"Erreur mise à jour salaire: {e}")
            return False

    def delete(self, salaire_id: int) -> bool:
        try:
            with self.db.get_cursor() as cursor:
                if not cursor:
                    return False
                query = "DELETE FROM salaires WHERE id = %s"
                cursor.execute(query, (salaire_id,))
            return True
        except Exception as e:
            logger.error(f"Erreur suppression salaire: {e}")
            return False

    def get_by_id(self, salaire_id: int) -> Optional[Dict]:
        with self.db.get_cursor() as cursor:
            if not cursor:
                return None
            cursor.execute("SELECT * FROM salaires WHERE id = %s", (salaire_id,))
            return cursor.fetchone()

    def get_all(self, user_id: int) -> List[Dict]:
        with self.db.get_cursor() as cursor:
            if not cursor:
                return []
            query = "SELECT * FROM salaires WHERE user_id = %s ORDER BY annee DESC, mois DESC"
            cursor.execute(query, (user_id,))
            return cursor.fetchall()

    def get_by_mois_annee(self, user_id: int, annee: int, mois: int, employeur: str, id_contrat: int) -> List[Dict]:
        """Récupère les salaires par mois et année avec gestion de connexion sécurisée."""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM salaires WHERE user_id = %s AND employeur = %s AND id_contrat = %s AND annee = %s AND mois = %s"
                cursor.execute(query, (user_id, employeur, id_contrat, annee, mois))
                result = cursor.fetchall()
                logger.info(f'ligne 4785 salaire selectionné: {result}')
                return result
        except Exception as e:
            logger.error(f"Erreur récupération salaire par mois/année: {e}")
            return []

    def get_cotisations_indemnites_mois(self, cotisations_contrat_model, indemnites_contrat_model, user_id: int, annee: int, mois: int) -> Dict:
        cotis = cotisations_contrat_model.get_total_cotisations_par_mois(user_id, annee, mois)
        indem = indemnites_contrat_model.get_total_indemnites_par_mois(user_id, annee, mois)

        # Agréger par employé ou global
        total_cotisations = sum(item['total_cotisations'] for item in cotis)
        total_indemnites = sum(item['total_indemnites'] for item in indem)

        return {
            'cotisations_par_contrat': cotis,
            'indemnites_par_contrat': indem,
            'total_cotisations': round(total_cotisations, 2),
            'total_indemnites': round(total_indemnites, 2)
        }
    
    def calculer_salaire(self, heures_reelles: float, salaire_horaire: float) -> float:
        try:
            heures_reelles = round(heures_reelles, 2)
            return round(heures_reelles * float(salaire_horaire), 2)
        except Exception as e:
            logger.error(f"Erreur calcul salaire: {e}")
            return 0.0

    def calculer_salaire_net(self, heures_reelles: float, contrat: Dict) -> float:
        try:
            if not contrat or heures_reelles <= 0:
                return 0.0

            sh = float(contrat.get('salaire_horaire', 24.05))
            brut = heures_reelles * sh

            # Fonction helper pour obtenir les taux
            def get_taux(key, default=0.0):
                val = contrat.get(key, default)
                return float(val) if val else default

            # Calcul des additions
            additions = sum([
                brut * (get_taux('indemnite_vacances_tx') / 100),
                brut * (get_taux('indemnite_jours_feries_tx') / 100),
                brut * (get_taux('indemnite_jour_conges_tx') / 100)
            ])
            brut_tot = round(brut + additions, 2)

            # Calcul des soustractions
            soustractions = sum([
                brut_tot * (get_taux('cotisation_avs_tx') / 100),
                brut_tot * (get_taux('cotisation_ac_tx') / 100),
                brut_tot * (get_taux('cotisation_accident_n_prof_tx') / 100),
                brut_tot * (get_taux('assurance_indemnite_maladie_tx') / 100),
                get_taux('cap_tx')
            ])

            return round(brut + additions - soustractions, 2)
        except Exception as e:
            logger.error(f"Erreur calcul salaire net: {e}")
            return 0.0


    def calculer_salaire_net_avec_details(self, heures_reelles: float, contrat: Dict, contrat_id: int, annee: int, user_id: Optional[int] = None, 
                                        mois: Optional[int] = None, jour_estimation: int = 15) -> Dict:
        """
        Calcule le salaire net et retourne tous les détails du calcul pour affichage
        avec des noms explicites pour chaque élément
        cotisations_contrat = g.models.cotisations_contrat_model.get_for_contrat_and_annee(contrat_id, annee)
        """
    
        try:
            if not contrat or heures_reelles <= 0:
                return {
                    'salaire_net': 0.0,
                    'erreur': 'Paramètres invalides',
                    'details': {}
                }

           # Conversion du salaire horaire
            salaire_horaire = float(contrat.get('salaire_horaire', 24.05))
            salaire_brut = round(heures_reelles * salaire_horaire, 2)

             # Récupérer cotisations et indemnités dynamiques
            cotisations_contrat = self.cotisations_contrat_model.get_for_contrat_and_annee(contrat_id, annee)
            indemnites_contrat = self.indemnites_contrat_model.get_for_contrat_and_annee(contrat_id, annee)

            # Calcul des indemnités
            indemnites_detail = {}
            total_indemnites = 0.0
            for item in indemnites_contrat:
                montant = self.indemnites_contrat_model.calculer_montant_indemnite(
                    type_indemnite_id=item['type_indemnite_id'],
                    base_montant=salaire_brut,
                    taux_fallback=item['taux']
                )
            salaire_brut_tot = round(salaire_brut + total_indemnites, 2)


            # Calcul des cotisations
            cotisations_detail = {}
            total_cotisations = 0.0
            for item in cotisations_contrat:
                base = item.get('base_calcul', 'brut')
                base_montant = salaire_brut_tot if base == 'brut_tot' else salaire_brut
                montant = self.cotisations_contrat_model.calculer_montant_cotisation(
                    type_cotisation_id=item['type_cotisation_id'],
                    base_montant=base_montant,
                    taux_fallback=item['taux']
                )
                montant = round(montant, 2)
                total_cotisations += montant
                cotisations_detail[item['nom_cotisation']] = {
                    'taux': item['taux'],
                    'montant': montant,
                    'base': base
                }

            salaire_net = round(salaire_brut_tot - total_cotisations, 2)

# Acomptes
            versements = {}
            total_versements = 0.0
            if user_id is not None and mois is not None:
                if contrat.get('versement_25', False):
                    acompte_25 = self.calculer_acompte_25(
                        user_id=user_id,
                        annee=annee,
                        mois=mois,
                        salaire_horaire=salaire_horaire,
                        employeur=contrat['employeur'],
                        id_contrat=contrat_id,
                        jour_estimation=contrat.get('jour_estimation_salaire', 15)
                    )
                    versements['acompte_25'] = {
                        'nom': 'Acompte du 25',
                        'actif': True,
                        'montant': round(acompte_25, 2),
                        'taux': 25
                    }
                    total_versements += acompte_25

                if contrat.get('versement_10', False):
                    acompte_10 = self.calculer_acompte_10(
                        user_id=user_id,
                        annee=annee,
                        mois=mois,
                        salaire_horaire=salaire_horaire,
                        employeur=contrat['employeur'],
                        id_contrat=contrat_id,
                        jour_estimation=contrat.get('jour_estimation_salaire', 15)
                    )
                    versements['acompte_10'] = {
                        'nom': 'Acompte du 10',
                        'actif': True,
                        'montant': round(acompte_10, 2),
                        'taux': 10
                    }
                    total_versements += acompte_10

            return {
                'salaire_net': salaire_net,
                'erreur': None,
                'details': {
                    'heures_reelles': heures_reelles,
                    'salaire_horaire': salaire_horaire,
                    'salaire_brut': salaire_brut,
                    'indemnites': indemnites_detail,
                    'total_indemnites': total_indemnites,
                    'cotisations': cotisations_detail,
                    'total_cotisations': total_cotisations,
                    'versements': versements,
                    'total_versements': total_versements,
                    'brut_tot': salaire_brut_tot,
                    'calcul_final': {
                        'brut': salaire_brut,
                        'plus_indemnites': salaire_brut_tot,
                        'moins_cotisations': salaire_net,
                        'moins_versements': round(salaire_net - total_versements, 2)
                    }
                }
            }

        except Exception as e:
            logger.error(f"Erreur dans calculer_salaire_net_avec_details: {str(e)}")
            return {
                'salaire_net': 0.0,
                'erreur': str(e),
                'details': {}
            }
    
    def calculer_differences(self, salaire_calcule: float, salaire_verse: float) -> Tuple[float, float]:
        if salaire_verse is None:
            return 0.0, 0.0
        difference = salaire_verse - salaire_calcule
        difference_pourcent = (difference / salaire_calcule * 100) if salaire_calcule else 0.0
        return round(difference, 2), round(difference_pourcent, 2)

    def importer_depuis_csv(self, fichier_csv: str, user_id: int) -> bool:
        """Importe les salaires depuis un fichier CSV avec gestion de connexion sécurisée."""
        import csv

        mois_nom_to_num = {
            'Janvier': 1, 'Février': 2, 'Mars': 3, 'Avril': 4,
            'Mai': 5, 'Juin': 6, 'Juillet': 7, 'Août': 8,
            'Septembre': 9, 'Octobre': 10, 'Novembre': 11, 'Décembre': 12
        }

        try:
            with self.db.get_cursor(commit=True) as cursor:
                with open(fichier_csv, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=',')
                    for row in reader:
                        if not row.get('Mois'):
                            continue
                        mois_num = mois_nom_to_num.get(row['Mois'])
                        if not mois_num:
                            continue
                        id_contrat = row.get('id_contrat')
                        employeur = row.get('employeur', 'Inconnu')
                        if id_contrat is None:
                            try:
                                id_contrat = int(id_contrat)
                            except ValueError:
                                id_contrat = None

                        def clean_value(val):
                            if val is None or val.strip() == '':
                                return None
                            return float(val.replace("'", "").replace(" CHF", "").strip())

                        heures_reelles = clean_value(row.get('Heures'))
                        salaire_calcule = clean_value(row.get('Salaire'))
                        salaire_verse = clean_value(row.get('Salaire versé'))
                        acompte_25 = clean_value(row.get('Acompte du 25'))
                        acompte_10 = clean_value(row.get('Acompte du 10'))

                        difference, difference_pourcent = self.calculer_differences(
                            salaire_calcule or 0, salaire_verse
                        )

                        annee = int(row.get('Année', 2025))

                        query = """
                        INSERT INTO salaires
                        (mois, annee, heures_reelles, salaire_calcule, salaire_verse,
                        acompte_25, acompte_10, difference, difference_pourcent, user_id, employeur, id_contrat)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        values = (
                            mois_num, annee,
                            heures_reelles, salaire_calcule, salaire_verse,
                            acompte_25, acompte_10,
                            difference, difference_pourcent,
                            user_id, employeur, id_contrat
                        )
                        cursor.execute(query, values)
            return True
        except Exception as e:
            logger.error(f"Erreur import salaires: {e}")
            return False

    def get_by_user_and_month(self, user_id: int, employeur: str, id_contrat: int, mois: int = None, annee: int = None) -> List[Dict]:
        with self.db.get_cursor() as cursor:
            if not cursor:
                return []
            query = "SELECT * FROM salaires WHERE user_id = %s AND employeur = %s AND id_contrat = %s"
            params = [user_id, employeur, id_contrat]
            if mois is not None:
                query += " AND mois = %s"
                params.append(mois)
            if annee is not None:
                query += " AND annee = %s"
                params.append(annee)
            query += " ORDER BY annee DESC, mois DESC"
            cursor.execute(query, tuple(params))
            return cursor.fetchall()

    def calculer_acompte_25(self, user_id: int, annee: int, mois: int, salaire_horaire: float, employeur: str, id_contrat: int, jour_estimation: int = 15) -> float:
        if not self.heure_model:
            raise ValueError("HeureTravail manager non initialisé")

        heures = self.heure_model.get_heures_periode(
            user_id, employeur, id_contrat, annee, mois, 1, jour_estimation
        )
        # Protection contre les valeurs négatives ou None
        heures = max(0.0, heures or 0.0)
        return round(max(0.0, heures or 0.0) * salaire_horaire, 2)

    def calculer_acompte_10(self, user_id: int, annee: int, mois: int, salaire_horaire: float, employeur: str, id_contrat: int, jour_estimation: int = 15) -> float:
        if not self.heure_model:
            raise ValueError("HeureTravail manager non initialisé")

        heures_total = self.heure_model.get_total_heures_mois(user_id, employeur, id_contrat, annee, mois)
        heures_avant = self.heure_model.get_heures_periode(
            user_id, employeur, id_contrat, annee, mois, 1, jour_estimation
        ) or 0.0

        # Normaliser les valeurs
        heures_total = float(heures_total)
        heures_avant = float(heures_avant)

        # Heures après le jour d'estimation
        heures_apres = max(0.0, heures_total - heures_avant)

        # Log en cas d’incohérence (utile pour le debug)
        if heures_apres < 0:
            logger.warning(
                f"Incohérence heures acompte 10: total={heures_total}, avant={heures_avant} "
                f"(user={user_id}, mois={mois}/{annee}, employeur={employeur})"
            )
            heures_apres = 0.0
        result = round(heures_apres * salaire_horaire, 2)
        logger.info(f"calculer_acompte_10 → heures_apres={heures_apres}, result={result}")
        logger.error(f"calculer_acompte_10 → heures_apres={heures_apres}, result={result}")
        return result
    def recalculer_salaire(self, salaire_id: int, contrat: Dict) -> bool:
        try:
            salaire = self.get_by_id(salaire_id)
            if not salaire:
                logger.warning(f"Salaire ID {salaire_id} introuvable.")
                return False

            heures_reelles = salaire.get('heures_reelles') or 0.0
            salaire_horaire = float(contrat.get('salaire_horaire', 27.12))
            user_id = salaire['user_id']
            employeur = salaire['employeur']
            id_contrat = salaire['id_contrat']
            annee = salaire['annee']
            mois = salaire['mois']
            jour_estimation = contrat.get('jour_estimation_salaire', 15)

            # 1. Calcul du salaire net réel (mois entier)
            result = self.calculer_salaire_net_avec_details(
                heures_reelles=heures_reelles,
                contrat=contrat,
                contrat_id=id_contrat,
                annee=annee,
                user_id=user_id,
                mois=mois,
                jour_estimation=jour_estimation
            )

            if result['erreur']:
                logger.error(f"Erreur recalcul salaire : {result['erreur']}")
                return False

            salaire_net = result['salaire_net']

            # 2. Acompte du 25 → heures du 1 au 15
            acompte_25_estime = 0.0
            if contrat.get('versement_25', False):
                acompte_25_estime = self.calculer_acompte_25(
                    user_id=user_id,
                    annee=annee,
                    mois=mois,
                    salaire_horaire=salaire_horaire,
                    employeur=employeur,
                    id_contrat=id_contrat,
                    jour_estimation=jour_estimation
                )

            # 3. Acompte du 10 → différence SALAIRE NET - ACOMPTE 25
            acompte_10_estime = round(salaire_net - acompte_25_estime, 2)

            # 4. Différence avec salaire versé (si saisi)
            salaire_verse = salaire.get('salaire_verse')
            difference, difference_pourcent = self.calculer_differences(salaire_net, salaire_verse)

            # 5. Mise à jour
            update_data = {
                'salaire_horaire': salaire_horaire,
                'salaire_calcule': result['details']['salaire_brut'],
                'salaire_net': salaire_net,
                'acompte_25_estime': round(acompte_25_estime, 2),
                'acompte_10_estime': acompte_10_estime,
                'difference': round(difference, 2),
                'difference_pourcent': round(difference_pourcent, 2),
            }

            return self.update(salaire_id, update_data)

        except Exception as e:
            logger.error(f"Erreur recalcul salaire ID {salaire_id}: {e}", exc_info=True)
            return False
    #def recalculer_salaire(self, salaire_id: int, contrat: Dict) -> bool:
    #    """
    #    Recalcule les champs dérivés d’un salaire existant à partir du contrat et des heures réelles.
    #    Met à jour l’entrée en base.
    #    """
    #    try:
    #        # 1. Récupérer le salaire existant
    #        salaire = self.get_by_id(salaire_id)
    #        if not salaire:
    #            logger.warning(f"Salaire ID {salaire_id} introuvable pour recalcul.")
    #            return False

    #        # 2. Extraire les données nécessaires
    #        heures_reelles = salaire.get('heures_reelles') or 0.0
    #        salaire_horaire = float(contrat.get('salaire_horaire', 27.12))
    #        user_id = salaire['user_id']
    #        employeur = salaire['employeur']
    #        id_contrat = salaire['id_contrat']
     #       annee = salaire['annee']
    #        mois = salaire['mois']
    #        jour_estimation = contrat.get('jour_estimation_salaire', 15)

    #        # 3. Recalculer les valeurs
    #        salaire_calcule = self.calculer_salaire(heures_reelles, salaire_horaire)
    #        salaire_net = self.calculer_salaire_net(heures_reelles, contrat)

    #        # Acomptes estimés
    #        acompte_25_estime = 0.0
    #        acompte_10_estime = 0.0

    #        if contrat.get('versement_25', False):
    #            acompte_25_estime = self.calculer_acompte_25(
     #               user_id=user_id,
    #                annee=annee,
    #                mois=mois,
    #                salaire_horaire=salaire_horaire,
    #                employeur=employeur,
    #                id_contrat=id_contrat,  # ⬅️ Correctement passé ici
    #                jour_estimation=jour_estimation
    #            )
    #        if contrat.get('versement_10', False):
    #            acompte_10_estime = self.calculer_acompte_10(
    #                user_id=user_id,
    #                annee=annee,
     #               mois=mois,
    #                salaire_horaire=salaire_horaire,
    #                employeur=employeur,
    #                id_contrat=id_contrat,  # ⬅️ Correctement passé ici
    #                jour_estimation=jour_estimation
    #            )

            # Différence avec le salaire versé (si présent)
    #        salaire_verse = salaire.get('salaire_verse')
    #        difference, difference_pourcent = self.calculer_differences(salaire_calcule, salaire_verse)

            # 4. Préparer les données à mettre à jour
    #        update_data = {
    #            'salaire_horaire': salaire_horaire,
    #            'salaire_calcule': salaire_calcule,
    #            'salaire_net': salaire_net,
    #            'acompte_25_estime': round(acompte_25_estime, 2),
    #            'acompte_10_estime': round(acompte_10_estime, 2),
    #            'difference': round(difference, 2),
    #            'difference_pourcent': round(difference_pourcent, 2),
    #        }

    #        # 5. Mettre à jour en base
    #        logger.info(f'update_data : {update_data}')
    #        return self.update(salaire_id, update_data)

    #    except Exception as e:
    #        logger.error(f"Erreur lors du recalcul du salaire ID {salaire_id}: {e}", exc_info=True)
    #        return False

    def get_salaire_employe_mois(self, employe_id: int, annee: int, mois: int) -> float:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT SUM(salaire_net) FROM salaires
                    WHERE employe_id = %s AND annee = %s AND mois = %s
                """, (employe_id, annee, mois))
                row = cursor.fetchone()
                return float(row[0]) if row and row[0] else 0.0
        except Exception as e:
            logger.error(f"Erreur get_salaire_employe_mois: {e}")
            return 0.0

    def get_by_user_and_month_with_employe(self,user_id: int,annee: int,mois: int,employe_id: Optional[int] = None) -> List[Dict]:
        clause = "AND employe_id = %s" if employe_id is not None else "AND employe_id IS NULL"
        params = [user_id, annee, mois]
        if employe_id is not None:
            params.append(employe_id)

        query = f"""
            SELECT * FROM salaires
            WHERE user_id = %s AND annee = %s AND mois = %s {clause}
            ORDER BY annee DESC, mois DESC
        """
        with self.db.get_cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()

class SyntheseHebdomadaire:
    def __init__(self, db):
        self.db = db
   
    # Dans la classe SyntheseHebdomadaire
    def calculate_for_week_by_contrat(self, user_id: int, annee: int, semaine: int) -> list[dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT
                        ht.id_contrat,
                        c.employeur,
                        SUM(ht.total_h) AS total_heures
                    FROM heures_travail ht
                    JOIN contrats c ON ht.id_contrat = c.id
                    WHERE ht.user_id = %s
                    AND YEAR(ht.date) = %s
                    AND ht.semaine_annee = %s
                    AND ht.total_h IS NOT NULL
                    AND ht.id_contrat IS NOT NULL
                    GROUP BY ht.id_contrat, c.employeur
                """
                cursor.execute(query, (user_id, annee, semaine))
                rows = cursor.fetchall()

                resultats = []
                for row in rows:
                    id_contrat = row['id_contrat']
                    employeur = row['employeur']
                    heures = float(row['total_heures'])
                    heures_simulees = 0.0  # à implémenter plus tard si besoin

                    resultats.append({
                        'user_id': user_id,
                        'annee': annee,
                        'semaine_numero': semaine,
                        'id_contrat': id_contrat,
                        'employeur': employeur,
                        'heures_reelles': round(heures, 2),
                        'heures_simulees': round(heures_simulees, 2),
                        'difference': round(heures - heures_simulees, 2),
                        'moyenne_mobile': 0.0,
                    })
                return resultats
        except Exception as e:
            logger.error(f"Erreur calcul synthèse hebdo par contrat: {e}")
            return []

    def create_or_update(self, data: dict) -> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                # Vérifier si une entrée existe déjà
                cursor.execute("""
                    SELECT id FROM synthese_hebdo
                    WHERE semaine_numero = %s AND annee = %s AND user_id = %s
                """, (data['semaine_numero'], data['annee'], data['user_id']))
                existing = cursor.fetchone()

                if existing:
                    query = """
                    UPDATE synthese_hebdo
                    SET heures_reelles = %s, heures_simulees = %s,
                        difference = %s, moyenne_mobile = %s
                    WHERE id = %s
                    """
                    cursor.execute(query, (
                        data['heures_reelles'], data['heures_simulees'],
                        data['difference'], data['moyenne_mobile'],
                        existing[0]
                    ))
                else:
                    query = """
                    INSERT INTO synthese_hebdo
                    (semaine_numero, annee, heures_reelles, heures_simulees,
                    difference, moyenne_mobile, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(query, (
                        data['semaine_numero'], data['annee'],
                        data['heures_reelles'], data['heures_simulees'],
                        data['difference'], data['moyenne_mobile'],
                        data['user_id']
                    ))
            return True
        except Error as e:
            logger.error(f"Erreur synthèse hebdo: {e}")
            return False

    def create_or_update_batch(self, data_list: list[dict]) -> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                for data in data_list:
                    cursor.execute("""
                        SELECT id FROM synthese_hebdo
                        WHERE user_id = %s AND annee = %s AND semaine_numero = %s AND id_contrat = %s
                    """, (
                        data['user_id'],
                        data['annee'],
                        data['semaine_numero'],
                        data['id_contrat']
                    ))
                    existing = cursor.fetchone()

                    if existing:
                        query = """
                            UPDATE synthese_hebdo SET
                                employeur = %s,
                                heures_reelles = %s,
                                heures_simulees = %s,
                                difference = %s,
                                moyenne_mobile = %s
                            WHERE id = %s
                        """
                        cursor.execute(query, (
                            data['employeur'],
                            data['heures_reelles'],
                            data['heures_simulees'],
                            data['difference'],
                            data['moyenne_mobile'],
                            existing['id']
                        ))
                    else:
                        query = """
                            INSERT INTO synthese_hebdo
                            (user_id, annee, semaine_numero, id_contrat, employeur,
                            heures_reelles, heures_simulees, difference, moyenne_mobile)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        cursor.execute(query, (
                            data['user_id'],
                            data['annee'],
                            data['semaine_numero'],
                            data['id_contrat'],
                            data['employeur'],
                            data['heures_reelles'],
                            data['heures_simulees'],
                            data['difference'],
                            data['moyenne_mobile']
                        ))
            return True
        except Exception as e:
            logger.error(f"Erreur batch synthèse hebdo: {e}")
            return False

    def get_by_user(self, user_id: int, limit: int = 12) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT * FROM synthese_hebdo
                WHERE user_id = %s
                ORDER BY annee DESC, semaine_numero DESC
                LIMIT %s
                """
                cursor.execute(query, (user_id, limit))
                syntheses = cursor.fetchall()
                return syntheses
        except Error as e:
            logger.error(f"Erreur récupération synthèses: {e}")
            return []

    def get_by_user_and_year(self, user_id: int, annee: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT * FROM synthese_hebdo
                    WHERE user_id = %s AND annee = %s
                    ORDER BY semaine_numero ASC
                """
                cursor.execute(query, (user_id, annee))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération synthèse hebdo année: {e}")
            return []

    def get_by_user_and_week(self, user_id: int, annee: int = None, semaine: int = None) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT * FROM synthese_hebdo WHERE user_id = %s
                """
                params = [user_id]
                if annee is not None:
                    query += " AND annee = %s"
                    params.append(annee)
                if semaine is not None:
                    query += " AND semaine_numero = %s"
                    params.append(semaine)
                query += " ORDER BY annee DESC, semaine_numero DESC"
                cursor.execute(query, tuple(params))
                result = cursor.fetchall()
                return result
        except Error as e:
            logger.error(f"Erreur récupération synthèse par semaine: {e}")
            return []

    def get_by_user_and_week_and_contrat(self, user_id: int, id_contrat: int, annee: int = None, semaine: int = None) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT * FROM synthese_hebdo
                WHERE user_id = %s AND id_contrat = %s AND annee = %s AND semaine_numero =%s
                ORDER BY annee DESC, semaine_numero DESC
                """
                cursor.execute(query, (user_id, id_contrat, annee, semaine))
                syntheses = cursor.fetchall()
                return syntheses
        except Error as e:
            logger.error(f'erreur récupération synthpèse: {e}')
            return []

    def get_by_user_and_filters(self, user_id: int, annee: int = None, semaine: int = None,
                            employeur: str = None, contrat_id: int = None) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM synthese_hebdo WHERE user_id = %s"
                params = [user_id]
                if annee is not None:
                    query += " AND annee = %s"
                    params.append(annee)
                if semaine is not None:
                    query += " AND semaine_numero = %s"
                    params.append(semaine)
                if employeur:
                    query += " AND employeur = %s"
                    params.append(employeur)
                if contrat_id:
                    query += " AND id_contrat = %s"
                    params.append(contrat_id)
                query += " ORDER BY annee DESC, semaine_numero DESC"
                cursor.execute(query, tuple(params))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur filtre synthèse hebdo: {e}")
            return []

    def prepare_svg_data_hebdo(self, user_id: int, annee: int, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        """Prépare les données pour un graphique SVG des heures hebdomadaires TOTALES (agrégées par semaine)."""
        # Récupère TOUTES les synthèses de l'année (y compris plusieurs contrats/semaine)
        synthese_list = self.get_by_user_and_year(user_id, annee)

        # Agrège par semaine
        total_par_semaine = {}
        for s in synthese_list:
            semaine = s['semaine_numero']
            if semaine not in total_par_semaine:
                total_par_semaine[semaine] = {'heures_reelles': 0.0, 'heures_simulees': 0.0}
            total_par_semaine[semaine]['heures_reelles'] += float(s.get('heures_reelles', 0))
            total_par_semaine[semaine]['heures_simulees'] += float(s.get('heures_simulees', 0))

        # Prépare les listes pour les 53 semaines
        heures_reelles_vals = []
        heures_simulees_vals = []
        semaine_labels = []

        for semaine in range(1, 54):
            data = total_par_semaine.get(semaine, {'heures_reelles': 0.0, 'heures_simulees': 0.0})
            heures_reelles_vals.append(data['heures_reelles'])
            heures_simulees_vals.append(data['heures_simulees'])
            semaine_labels.append(f"S{semaine}")

        # Calcul des bornes Y
        all_vals = heures_reelles_vals + heures_simulees_vals
        min_val = min(all_vals) if all_vals else 0.0
        max_val = max(all_vals) if all_vals else 100.0
        if min_val == max_val:
            max_val = min_val + 40.0 if min_val == 0 else min_val * 1.1

        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        def y_coord(val):
            if max_val == min_val:
                return margin_y + plot_height / 2
            return margin_y + plot_height - ((val - min_val) / (max_val - min_val)) * plot_height

        # Ticks (tous les 10h)
        ticks = []
        step = 10
        y_val = math.floor(min_val / step) * step
        while y_val <= max_val + step:
            if y_val >= 0:
                y_px = y_coord(y_val)
                ticks.append({'value': int(y_val), 'y_px': y_px})
            y_val += step

        # Barres (heures réelles)
        bar_width = plot_width / 53 * 0.6
        colonnes_svg = []
        for i in range(53):
            x = margin_x + (i + 0.5) * (plot_width / 53) - bar_width / 2
            y_top = y_coord(heures_reelles_vals[i])
            height = plot_height - (y_top - margin_y)
            if height < 0:
                height = 0
                y_top = margin_y + plot_height
            colonnes_svg.append({'x': x, 'y': y_top, 'width': bar_width, 'height': height})

        # Ligne simulée (heures simulées)
        points_simule = [
            f"{margin_x + (i + 0.5) * (plot_width / 53)},{y_coord(heures_simulees_vals[i])}"
            for i in range(53)
        ]

        return {
            'colonnes': colonnes_svg,
            'ligne_simule': points_simule,
            'min_val': min_val,
            'max_val': max_val,
            'semaine_labels': semaine_labels,
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'ticks': ticks,
            'annee': annee
        }

    def get_employeurs_distincts(self, user_id: int) -> List[str]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT employeur
                    FROM synthese_hebdo
                    WHERE user_id = %s AND employeur IS NOT NULL
                    ORDER BY employeur
                """, (user_id,))
                return [row['employeur'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erreur employeurs: {e}")
            return []

    def calculate_h2f_stats(self, heure_model, user_id: int, employeur: str, id_contrat: int, annee: int, seuil_h2f_minutes: int = 18 * 60) -> Dict:
        """
        Calcule les statistiques sur h2f pour une année donnée.
        seuil_h2f_minutes: seuil en minutes (ex: 18h = 18*60 min). Défaut à 18h.
        Retourne un dictionnaire avec les moyennes hebdomadaires et la moyenne mobile.
        """
        weekly_counts = {} # { semaine: nb_jours_avec_h2f_apres_seuil }

        for semaine in range(1, 53): # Semaines de 1 à 52 (ou 53)
            jours_semaine = heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, semaine=semaine)
            count = 0
            for jour in jours_semaine:
                h2f_minutes = heure_model.time_to_minutes(jour.get('h2f'))
                if h2f_minutes != -1 and h2f_minutes > seuil_h2f_minutes:
                    count += 1
            weekly_counts[semaine] = count

        # Calcul des moyennes hebdomadaires
        moyennes_hebdo = { semaine: float(count) for semaine, count in weekly_counts.items() }

        # Calcul de la moyenne mobile
        moyennes_mobiles = {}
        cumulative_count = 0
        cumulative_weeks = 0
        for semaine in range(1, 53):
            cumulative_count += weekly_counts[semaine]
            cumulative_weeks += 1
            if cumulative_weeks > 0:
                moyennes_mobiles[semaine] = round(cumulative_count / cumulative_weeks, 2)
            else:
                moyennes_mobiles[semaine] = 0.0

        return {
            'moyennes_hebdo': moyennes_hebdo,
            'moyennes_mobiles': moyennes_mobiles,
            'seuil_heure': f"{seuil_h2f_minutes // 60}:{seuil_h2f_minutes % 60:02d}"
        }


    def prepare_svg_data_horaire_jour(self, heure_model, user_id: int, employeur: str, id_contrat: int, annee: int, semaine: int, seuil_h2f_heure: float = 18.0, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        """
        Prépare les données pour un graphique SVG des horaires de début/fin de journée.
        Axe X: Jours de la semaine (Lun, Mar, Mer, Jeu, Ven, Sam, Dim)
        Axe Y: Heures (6h en haut, 24h en bas)
        seuil_h2f_heure: Heure du seuil à afficher (par défaut 18h).
        """

        jours_semaine = heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, semaine=semaine)

        # Constantes pour la conversion des heures en pixels
        heure_debut_affichage = 6  # 6h du matin
        heure_fin_affichage = 24   # 24h (minuit)
        plage_heures = heure_fin_affichage - heure_debut_affichage # 18h
        minute_debut_affichage = heure_debut_affichage * 60
        minute_fin_affichage = heure_fin_affichage * 60
        plage_minutes = plage_heures * 60 # 1080 minutes

        seuil_h2f_minutes = int(seuil_h2f_heure * 60) # Convertir le seuil en minutes

        # Marges
        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        # Calcul de la position Y de la ligne seuil

        seuil_minutes_affiche = max(minute_debut_affichage, min(seuil_h2f_minutes, minute_fin_affichage))
        seuil_y = margin_y + plot_height - ((seuil_minutes_affiche - minute_debut_affichage) / plage_minutes) * plot_height
        # Calcul des rectangles pour chaque jour
        rectangles_svg = []
        jours_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        # On itère sur les données de la liste `jours_semaine`
        for i, jour_data in enumerate(jours_semaine):
            # Utiliser le jour de la semaine de la date pour positionner l'élément
            date_obj_raw = jour_data['date']
            if isinstance(date_obj_raw, str):
                date_obj = datetime.fromisoformat(date_obj_raw).date()
            elif isinstance(date_obj_raw, datetime):
                date_obj = date_obj_raw.date()
            elif isinstance(date_obj_raw, date):
                date_obj = date_obj_raw
            else:
                logger.error(f'Type inattendu pour la date : {type(date_obj_raw)}, valeur : {date_obj_raw}')
                continue

            jour_semaine_numero = date_obj.isocalendar()[2] # 1=Lundi, 7=Dimanche
            if jour_semaine_numero < 1 or jour_semaine_numero > 7:
                continue # Ignorer les jours en dehors de Lundi-Dimanche si nécessaire

            h1d_minutes = self.heure_model.time_to_minutes(jour_data.get('h1d'))
            h2f_minutes = self.heure_model.time_to_minutes(jour_data.get('h2f'))

            # Calcul des coordonnées X pour la colonne du jour
            x_jour_debut = margin_x + (jour_semaine_numero - 1) * (plot_width / 7)
            x_jour_fin = margin_x + jour_semaine_numero * (plot_width / 7)
            largeur_rect = (x_jour_fin - x_jour_debut) * 0.8 # Laisser un peu d'espace
            x_rect_debut = x_jour_debut + (x_jour_fin - x_jour_debut) * 0.1

            # Calcul des coordonnées Y pour h1d (début) et h2f (fin)
            # La formule est: y = marge_y + hauteur_plot - ((minutes - minute_debut) / plage_minutes) * hauteur_plot
            if h1d_minutes != -1 and h1d_minutes >= minute_debut_affichage and h1d_minutes <= minute_fin_affichage:
                y_h1d = margin_y + plot_height - ((h1d_minutes - minute_debut_affichage) / plage_minutes) * plot_height
            else:
                y_h1d = None # Ne pas afficher si hors plage ou manquant

            if h2f_minutes != -1 and h2f_minutes >= minute_debut_affichage and h2f_minutes <= minute_fin_affichage:
                y_h2f = margin_y + plot_height - ((h2f_minutes - minute_debut_affichage) / plage_minutes) * plot_height
            else:
                y_h2f = None

            # Vérifier si h2f dépasse le seuil
            depasse_seuil = (h2f_minutes != -1 and h2f_minutes > seuil_h2f_minutes)
            couleur = 'red' if depasse_seuil else 'steelblue'

            if y_h1d is not None and y_h2f is not None:
                # Dessiner un rectangle entre h1d et h2f
                y_top = min(y_h1d, y_h2f)
                y_bottom = max(y_h1d, y_h2f)
                hauteur_rect = y_bottom - y_top
                rectangles_svg.append({
                    'x': x_rect_debut,
                    'y': y_top,
                    'width': largeur_rect,
                    'height': hauteur_rect,
                    'jour': jour_data['date'], # Pour info éventuelle dans le template
                    'type': 'h1d_to_h2f', # Type pour distinguer dans le template
                    'depasse_seuil': depasse_seuil, # Indicateur pour la couleur.
                    'couleur': 'red' if depasse_seuil else 'steelblue'
                })
            elif y_h1d is not None: # Si h2f est manquant ou hors plage
                # Dessiner un point ou une petite barre pour h1d
                rectangles_svg.append({
                    'x': x_rect_debut,
                    'y': y_h1d - 2, # Hauteur arbitraire pour un point
                    'width': largeur_rect,
                    'height': 4,
                    'jour': jour_data['date'],
                    'type': 'h1d_only',
                    'depasse_seuil': False, # h1d seul ne dépasse pas le seuil de h2f
                    'couleur': 'red' if depasse_seuil else 'steelblue'
                })
            elif y_h2f is not None: # Si h1d est manquant ou hors plage
                # Dessiner un point ou une petite barre pour h2f
                rectangles_svg.append({
                    'x': x_rect_debut,
                    'y': y_h2f - 2, # Hauteur arbitraire pour un point
                    'width': largeur_rect,
                    'height': 4,
                    'jour': jour_data['date'],
                    'type': 'h2f_only',
                    'depasse_seuil': depasse_seuil, # Utiliser la vérification pour h2f
                    'couleur': 'red' if depasse_seuil else 'steelblue'
                })

        # Ticks pour l'axe Y (heures)
        ticks_y = []
        for h in range(heure_debut_affichage, heure_fin_affichage + 1):
            y_tick = margin_y + plot_height - ((h * 60 - minute_debut_affichage) / plage_minutes) * plot_height
            ticks_y.append({'heure': f"{h:02d}h", 'y': y_tick})

        # Labels pour l'axe X (jours)
        labels_x = []
        for i in range(7):
            x_label = margin_x + (i + 0.5) * (plot_width / 7)
            labels_x.append({'jour': jours_labels[i], 'x': x_label})
        total_minutes = int(round(seuil_h2f_heure * 60))
        heures = total_minutes // 60
        minutes = total_minutes % 60
        seuil_heure_label = f"{heures}h{minutes:02d}"

        return {
            'rectangles': rectangles_svg,
            'ticks_y': ticks_y,
            'labels_x': labels_x,
            'seuil_y': seuil_y, # <-- Ajout de la position Y du seuil
            'seuil_heure': seuil_heure_label, # <-- Ajout de l'heure du seuil pour le label
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'semaine': semaine,
            'annee': annee
        }

class SyntheseMensuelle:
    def __init__(self, db):
        self.db = db


    def calculate_for_month_by_contrat(self, user_id: int, annee: int, mois: int) -> list[dict]:
        try:
            with self.db.get_cursor() as cursor:
                query_contrats = """
                    SELECT
                        h.id_contrat,
                        c.employeur,
                        SUM(h.total_h) AS heures_contrat
                    FROM heures_travail h
                    JOIN contrats c ON h.id_contrat = c.id
                    WHERE h.user_id = %s
                    AND YEAR(h.date) = %s
                    AND MONTH(h.date) = %s
                    AND h.total_h IS NOT NULL
                    AND h.id_contrat IS NOT NULL
                    GROUP BY h.id_contrat, c.employeur
                """
                cursor.execute(query_contrats, (user_id, annee, mois))
                rows = cursor.fetchall()

                resultats = []
                for row in rows:
                    id_contrat = row['id_contrat']
                    employeur = row['employeur']
                    heures_c = float(row['heures_contrat'])

                    cursor.execute("SELECT salaire_horaire FROM contrats WHERE id = %s", (id_contrat,))
                    contrat = cursor.fetchone()
                    taux = float(contrat['salaire_horaire']) if contrat and contrat['salaire_horaire'] else 0.0
                    salaire = heures_c * taux

                    resultats.append({
                        'user_id': user_id,
                        'annee': annee,
                        'mois': mois,
                        'id_contrat': id_contrat,
                        'employeur': employeur,
                        'heures_reelles': round(heures_c, 2),
                        'heures_simulees': 0.0,
                        'salaire_reel': round(salaire, 2),
                        'salaire_simule': 0.0,
                    })
                return resultats
        except Exception as e:
            logger.error(f"Erreur calcul synthèse mensuelle par contrat: {e}")
            return []

    def prepare_svg_data_mensuel(self, user_id: int, annee: int, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        """
        Prépare les données pour un graphique SVG des salaires mensuels.
        Retourne un dict compatible avec le template.
        """
        # Récupérer toutes les synthèses mensuelles de l'année
        synthese_list = self.get_by_user_and_year(user_id, annee)

        # Indexer par mois
        synthese_par_mois = {s['mois']: s for s in synthese_list}

        # Initialiser les listes pour les 12 mois
        salaire_reel_vals = []
        salaire_simule_vals = []
        mois_labels = []

        for mois in range(1, 13):
            s = synthese_par_mois.get(mois)
            if s:
                salaire_reel_vals.append(float(s.get('salaire_reel', 0)))
                salaire_simule_vals.append(float(s.get('salaire_simule', 0)))
            else:
                salaire_reel_vals.append(0.0)
                salaire_simule_vals.append(0.0)
            mois_labels.append(f"{mois:02d}/{annee}")

        # Calcul des bornes
        all_vals = salaire_reel_vals + salaire_simule_vals
        min_val = min(all_vals) if all_vals else 0.0
        max_val = max(all_vals) if all_vals else 100.0
        if min_val == max_val:
            max_val = min_val + 100.0 if min_val == 0 else min_val * 1.1

        # Marges et dimensions
        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        # Fonction utilitaire pour coordonnée Y
        def y_coord(val):
            if max_val == min_val:
                return margin_y + plot_height / 2
            return margin_y + plot_height - ((val - min_val) / (max_val - min_val)) * plot_height

        # === CALCUL DES TICKS POUR L'AXE Y ===
        tick_step_minor = 200
        tick_step_major = 1000

        y_axis_min = math.floor(min_val / tick_step_minor) * tick_step_minor
        y_axis_max = math.ceil(max_val / tick_step_minor) * tick_step_minor
        if y_axis_max <= y_axis_min:
            y_axis_max = y_axis_min + tick_step_major
        if max_val < tick_step_major:
            y_axis_max = tick_step_major

        ticks = []
        y_val = y_axis_min
        while y_val <= y_axis_max:
            if y_val >= min_val - 500 and y_val <= max_val + 500:  # plage raisonnable
                is_major = (y_val % tick_step_major == 0)
                y_px = y_coord(y_val)
                ticks.append({
                    'value': int(y_val),
                    'y_px': y_px,
                    'is_major': is_major
                })
            y_val += tick_step_minor

        # === PRÉPARATION DES ÉLÉMENTS SVG ===
        # Colonnes (barres) pour salaire réel
        colonnes_svg = []
        bar_width = plot_width / 12 * 0.6
        for i in range(12):
            x = margin_x + (i + 0.5) * (plot_width / 12) - bar_width / 2
            y_top = y_coord(salaire_reel_vals[i])
            height = plot_height - (y_top - margin_y)
            if height < 0:
                height = 0
                y_top = margin_y + plot_height
            colonnes_svg.append({
                'x': x,
                'y': y_top,
                'width': bar_width,
                'height': height
            })

        # Lignes pour salaire simulé (points)
        points_simule = [
            f"{margin_x + (i + 0.5) * (plot_width / 12)},{y_coord(salaire_simule_vals[i])}"
            for i in range(12)
        ]

        return {
            'colonnes': colonnes_svg,
            'ligne_simule': points_simule,
            'min_val': min_val,
            'max_val': max_val,
            'mois_labels': mois_labels,
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'ticks': ticks,
            'annee': annee
        }

    def get_by_user_and_year(self, user_id: int, annee: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT * FROM synthese_mensuelle
                    WHERE user_id = %s AND annee = %s
                    ORDER BY mois ASC
                """
                cursor.execute(query, (user_id, annee))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération synthèse annuelle: {e}")
            return []

    def get_by_user_and_month(self, user_id: int, annee : int, mois: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                    SELECT * FROM synthese_mensuelle
                    WHERE user_id = %s AND annee = %s AND mois = %s
                    ORDER BY mois ASC
                """
                cursor.execute(query, (user_id, annee, mois))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération synthèse annuelle: {e}")
            return []

    def get_by_user_and_filters(self, user_id: int, annee: int = None, mois: int = None, employeur: str = None, contrat_id: int = None) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM synthese_mensuelle WHERE user_id = %s"
                params = [user_id]
                if annee is not None:
                    query += " AND annee = %s"
                    params.append(annee)
                if mois is not None:
                    query += " AND mois = %s"
                    params.append(mois)
                if employeur:
                    query += " AND employeur = %s"
                    params.append(employeur)
                if contrat_id:
                    query += " AND id_contrat = %s"
                    params.append(contrat_id)
                query += " ORDER BY annee DESC, mois DESC"
                cursor.execute(query, tuple(params))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur filtre synthèse: {e}")
            return []

    def get_employeurs_distincts(self, user_id: int) -> List[str]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT employeur
                    FROM synthese_mensuelle
                    WHERE user_id = %s AND employeur IS NOT NULL
                    ORDER BY employeur
                """, (user_id,))
                return [row['employeur'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Erreur employeurs: {e}")
            return []

    def create_or_update(self, data: dict) -> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                    SELECT id FROM synthese_mensuelle
                    WHERE user_id = %s AND annee = %s AND mois = %s AND id_contrat = %s
                """, (data['user_id'], data['annee'], data['mois'], data['id_contrat']))
                existing = cursor.fetchone()

                if existing:
                    query = """
                        UPDATE synthese_mensuelle SET
                            employeur = %s,
                            heures_reelles = %s,
                            heures_simulees = %s,
                            salaire_reel = %s,
                            salaire_simule = %s
                        WHERE id = %s
                    """
                    cursor.execute(query, (
                        data['employeur'],
                        data['heures_reelles'],
                        data['heures_simulees'],
                        data['salaire_reel'],
                        data['salaire_simule'],
                        existing['id']
                    ))
                else:
                    query = """
                        INSERT INTO synthese_mensuelle
                        (user_id, annee, mois, id_contrat, employeur,
                        heures_reelles, heures_simulees, salaire_reel, salaire_simule)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    cursor.execute(query, (
                        data['user_id'],
                        data['annee'],
                        data['mois'],
                        data['id_contrat'],
                        data['employeur'],
                        data['heures_reelles'],
                        data['heures_simulees'],
                        data['salaire_reel'],
                        data['salaire_simule']
                    ))
            return True
        except Exception as e:
            logger.error(f"Erreur synthèse mensuelle: {e}")
            return False

    def delete_by_user_and_year(self, user_id: int, annee: int):
        with self.db.get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM synthese_mensuelle WHERE user_id = %s AND annee = %s", (user_id, annee))

    def get_monthly_total(self, user_id: int, annee: int, mois: int) -> dict:
        rows = self.get_by_user_and_filters(user_id, annee=annee, mois=mois)
        total_heures = sum(float(r.get('heures_reelles', 0)) for r in rows)
        total_salaire = sum(float(r.get('salaire_reel', 0)) for r in rows)
        return {
            'heures_reelles': round(total_heures, 2),
            'salaire_reel': round(total_salaire, 2)
        }

    def get_by_user(self, user_id: int, limit: int = 6) -> List[Dict]:
        """
        Récupère les synthèses mensuelles pour un utilisateur donné.
        """
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT * FROM synthese_mensuelle
                WHERE user_id = %s
                ORDER BY annee DESC, mois DESC
                LIMIT %s
                """
                cursor.execute(query, (user_id, limit))
                syntheses = cursor.fetchall()
                return syntheses
        except Error as e:
            logger.error(f"Erreur récupération synthèses: {e}")
            return []

    def calculate_h2f_stats_mensuel(self,heure_model, user_id: int, employeur: str, id_contrat: int,
                                    annee: int, mois: int, seuil_h2f_minutes: int = 18 * 60) -> Dict:
        """
        Calcule les statistiques sur h2f pour un mois donné.
        """
        seuil_h2f_minutes = int(round(seuil_h2f_minutes))

        jours_mois = heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, mois=mois)
        count = 0
        for jour in jours_mois:
            h2f_minutes = heure_model.time_to_minutes(jour.get('h2f'))
            if h2f_minutes != -1 and h2f_minutes > seuil_h2f_minutes:
                count += 1

        moyenne_mensuelle = count / len(jours_mois) if jours_mois else 0.0
        seuil_int = int(round(seuil_h2f_minutes))
        return {
            'nb_jours_apres_seuil': count,
            'jours_travailles': len(jours_mois),
            'moyenne_mensuelle': round(moyenne_mensuelle, 2),
            'seuil_heure': f"{seuil_int // 60}:{seuil_int % 60:02d}"
        }

    def prepare_svg_data_horaire_mois(self, heure_model, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int, largeur_svg: int = 1000, hauteur_svg: int = 400) -> Dict:
        """
        Prépare les données pour un graphique SVG des horaires sur un mois.
        Axe X: Jours du mois (1, 2, 3, ..., 31)
        Axe Y: Heures (6h en haut, 22h en bas)
        """

        jours_mois = heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, mois=mois)

        # Constantes pour la conversion des heures en pixels
        heure_debut_affichage = 6
        heure_fin_affichage = 22
        minute_debut_affichage = heure_debut_affichage * 60
        minute_fin_affichage = heure_fin_affichage * 60
        plage_minutes = (heure_fin_affichage - heure_debut_affichage) * 60

        margin_x = largeur_svg * 0.1
        margin_y = hauteur_svg * 0.1
        plot_width = largeur_svg * 0.8
        plot_height = hauteur_svg * 0.8

        rectangles_svg = []
        # On suppose que `jours_mois` est trié par date
        for i, jour_data in enumerate(jours_mois):
            date_value = jour_data['date']
            if isinstance(date_value, str):
                date_obj = datetime.fromisoformat(date_value).date()
            elif isinstance(date_value, datetime):
                date_obj = date_value.date()
            elif isinstance(date_value, date):
                date_obj = date_value
            else:
                logger.warning(f"Type de date inattendu : {type(date_value)}")
                continue
            jour_du_mois = date_obj.day

            h1d_minutes = self.heure_model.time_to_minutes(jour_data.get('h1d'))
            h2f_minutes = self.heure_model.time_to_minutes(jour_data.get('h2f'))

            # Coordonnée X basée sur le jour du mois
            # On suppose que le mois a au maximum 31 jours
            x_jour_debut = margin_x + (jour_du_mois - 1) * (plot_width / 31)
            x_jour_fin = margin_x + jour_du_mois * (plot_width / 31)
            largeur_rect = (x_jour_fin - x_jour_debut) * 0.8
            x_rect_debut = x_jour_debut + (x_jour_fin - x_jour_debut) * 0.1

            # Coordonnées Y
            if h1d_minutes != -1 and h1d_minutes >= minute_debut_affichage and h1d_minutes <= minute_fin_affichage:
                y_h1d = margin_y + plot_height - ((h1d_minutes - minute_debut_affichage) / plage_minutes) * plot_height
            else:
                y_h1d = None

            if h2f_minutes != -1 and h2f_minutes >= minute_debut_affichage and h2f_minutes <= minute_fin_affichage:
                y_h2f = margin_y + plot_height - ((h2f_minutes - minute_debut_affichage) / plage_minutes) * plot_height
            else:
                y_h2f = None

            if y_h1d is not None and y_h2f is not None:
                y_top = min(y_h1d, y_h2f)
                y_bottom = max(y_h1d, y_h2f)
                hauteur_rect = y_bottom - y_top
                rectangles_svg.append({
                    'x': x_rect_debut,
                    'y': y_top,
                    'width': largeur_rect,
                    'height': hauteur_rect,
                    'jour': jour_data['date'],
                    'type': 'h1d_to_h2f'
                })
            elif y_h1d is not None:
                rectangles_svg.append({
                    'x': x_rect_debut,
                    'y': y_h1d - 2,
                    'width': largeur_rect,
                    'height': 4,
                    'jour': jour_data['date'],
                    'type': 'h1d_only'
                })
            elif y_h2f is not None:
                rectangles_svg.append({
                    'x': x_rect_debut,
                    'y': y_h2f - 2,
                    'width': largeur_rect,
                    'height': 4,
                    'jour': jour_data['date'],
                    'type': 'h2f_only'
                })

        # Ticks Y
        ticks_y = []
        for h in range(heure_debut_affichage, heure_fin_affichage + 1):
             y_tick = margin_y + plot_height - ((h * 60 - minute_debut_affichage) / plage_minutes) * plot_height
             ticks_y.append({'heure': f"{h:02d}h", 'y': y_tick})

        # Labels X (jours du mois)
        labels_x = []
        # On affiche un label tous les 5 jours pour moins encombrer l'axe
        for j in range(1, 32):
            if j % 5 == 0 or j == 1: # Label pour le 1er et tous les 5ème jour
                x_label = margin_x + (j - 1) * (plot_width / 31)
                labels_x.append({'jour': str(j), 'x': x_label})

        return {
            'rectangles': rectangles_svg,
            'ticks_y': ticks_y,
            'labels_x': labels_x,
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'mois': mois,
            'annee': annee
        }

    def prepare_svg_data_h2f_annuel(self, synthese_hebdo_model, user_id: int, employeur: str, id_contrat: int, annee: int, seuil_h2f_minutes: int = 18 * 60, largeur_svg: int = 900, hauteur_svg: int = 400) -> Dict:
    # Récupérer les stats hebdomadaires
        stats = synthese_hebdo_model.calculate_h2f_stats(user_id, employeur, id_contrat, annee, seuil_h2f_minutes)

        semaines = list(range(1, 53))  # ou 54 si besoin
        depassements = [stats['moyennes_hebdo'].get(s, 0) for s in semaines]
        moyennes_mobiles = [stats['moyennes_mobiles'].get(s, 0) for s in semaines]

        # Calcul des dimensions SVG
        margin_x = 60
        margin_y = 40
        plot_width = largeur_svg - margin_x - 50
        plot_height = hauteur_svg - margin_y - 50

        max_val = max(max(depassements), max(moyennes_mobiles)) if (depassements or moyennes_mobiles) else 1

        # Barres
        barres = []
        for i, (semaine, val) in enumerate(zip(semaines, depassements)):
            x = margin_x + i * (plot_width / 52)
            largeur_barre = (plot_width / 52) * 0.7
            hauteur_barre = (val / max_val) * plot_height if max_val > 0 else 0
            y = hauteur_svg - margin_y - hauteur_barre
            barres.append({
                'x': x,
                'y': y,
                'width': largeur_barre,
                'height': hauteur_barre,
                'value': val
            })

        # Ligne moyenne mobile
        points_ligne = []
        for i, val in enumerate(moyennes_mobiles):
            x = margin_x + (i + 0.5) * (plot_width / 52)
            y = hauteur_svg - margin_y - (val / max_val) * plot_height if max_val > 0 else hauteur_svg - margin_y
            points_ligne.append(f"{x},{y}")

        return {
            'barres': barres,
            'ligne': points_ligne,
            'semaines': [f"S{num}" for num in semaines],
            'largeur_svg': largeur_svg,
            'hauteur_svg': hauteur_svg,
            'margin_x': margin_x,
            'margin_y': margin_y,
            'plot_width': plot_width,
            'plot_height': plot_height,
            'max_val': max_val,
            'annee': annee,
            'seuil_heure': f"{seuil_h2f_minutes // 60}h{seuil_h2f_minutes % 60:02d}"
        }


    def calculate_h2f_stats_weekly_for_month(self, heure_model, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int, seuil_h2f_minutes: int) -> Dict:
        # Bornes du mois
        if mois == 12:
            fin_mois = date(annee + 1, 1, 1) - timedelta(days=1)
        else:
            fin_mois = date(annee, mois + 1, 1) - timedelta(days=1)
        debut_mois = date(annee, mois, 1)

        # Récupérer TOUS les jours du mois
        tous_les_jours = heure_model.get_h1d_h2f_for_period(
            user_id=user_id,
            employeur=employeur,
            id_contrat=id_contrat,
            annee=annee,
            mois=mois
        )

        # Regrouper par semaine ISO
        par_semaine = {}
        for j in tous_les_jours:
            date_val = j['date']
            # Gérer les différents types possibles de `date`
            if isinstance(date_val, str):
                d = datetime.fromisoformat(date_val).date()
            elif isinstance(date_val, datetime):
                d = date_val.date()
            elif isinstance(date_val, date):
                d = date_val
            else:
                continue  # type inconnu, on ignore

            # Vérifier que la date est bien dans le mois (sécurité)
            if d < debut_mois or d > fin_mois:
                continue

            semaine_iso = d.isocalendar()[1]
            if semaine_iso not in par_semaine:
                par_semaine[semaine_iso] = []
            par_semaine[semaine_iso].append(j)

        # Compter les dépassements
        semaines_sorted = sorted(par_semaine.keys())
        depassements = []
        for semaine in semaines_sorted:
            count = 0
            for jour in par_semaine[semaine]:
                h2f_min = heure_model.time_to_minutes(jour.get('h2f'))
                if h2f_min != -1 and h2f_min > seuil_h2f_minutes:
                    count += 1
            depassements.append(count)

        # Moyenne mobile cumulative
        moyennes_mobiles = []
        cumul = 0
        for i, val in enumerate(depassements, 1):
            cumul += val
            moyennes_mobiles.append(round(cumul / i, 2))

        return {
            'semaines': semaines_sorted,
            'jours_depassement': depassements,
            'moyenne_mobile': moyennes_mobiles
        }


class Equipe:
    def __init__(self, db):
        self.db = db

    def create(self, user_id, nom: str, description:str) -> int:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO equipes (user_id, nom, description, created_at)
                VALUES (%s, %s, %s, NOW())
                """
                cursor.execute(query, (user_id, nom, description))
            return cursor.lastrowid
        except Error as e:
            logger.error(f'"erreur création équipe : {e}')
            return None

    def modifier(self, user_id:int, id_equipe: int, nom: str, description: str)-> int:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                query = """
                UPDATE equipes 
                SET nom = %s, description = %s 
                WHERE id = %s AND user_id = %s
                """
                params = (nom, description, id_equipe, user_id)
                return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Erreur mise à jour équipe {id_equipe} : {e}")
            return False
    
    def get_equipe_id(self, user_id: int, id_equipe: int)-> Dict:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT * FROM equipes WHERE user_id = %s AND id = %s", (user_id, id_equipe))
                equipe = cursor.fetchone()
                return equipe
        except Exception as e:
            logger.error(f"Erreur dans récupération equipe {id_equipe} : {e}")
            return False

    def supprimer(self, user_id: int, id_equipe: int) -> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM Equipes_competences_requises WHERE equipe_id = %s", (id_equipe,))
                cursor.execute("DELETE FROM equipes_employes WHERE equipe_id = %s", (id_equipe,))
                cursor.execute("DELETE FROM equipes WHERE id = %s AND user_id = %s", (id_equipe, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur suppression equipe {id_equipe}: {e}")
            return False

    def ajouter_employe_to_equipe(self, employe_model, id_equipe: int, employe_id: int, user_id: int) -> bool:
        employe = employe_model.get_by_id(employe_id, user_id)
        if not employe:
            return False
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                INSERT IGNORE INTO equipes_employes (id_equipe, employe_id, added_at)
                VALUES (%s, %s, NOW())
                """, (id_equipe, employe_id)
                )
                return True
        except Exception as e:
            logger.error(f"Erreur ajout employe {employe_id} à equipe {id_equipe}: {e}")
            return False
    def retirer_employe_to_equipe(self, id_equipe: int, employe_id: int) -> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                DELETE FROM equipes_employes
                WHERE id_equipe = %s AND employe_id = %s
                """, (id_equipe, employe_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur retrait employe {employe_id} de l'equipe {id_equipe} : {e}")
            return False

    def get_employes_from_equipe(self, user_id: int, id_equipe: int)-> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT e.*
                FROM employes e
                JOIN equipes_employes ee ON e.id = ee.employe_id
                WHERE e.user_id = %s AND ee.id_equipe = %s
                ORDER BY e.nom, e.prenom
                """
                cursor.execute(query, (user_id, id_equipe))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur Récupération employé equipe {id_equipe}: {e}")
            return []
    def get_equipes_from_user(self, user_id:int)->List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT * FROM equipes WHERE user_id = %s ORDER BY nom", (user_id))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération équipes user {user_id}: {e}")
            return []

    def get_equipes_avec_employe(self, user_id: int)-> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                query= """
                SELECT t.*,
                          e.id as employe_id, e.nom as employe_nom, e.prenom as employe_prenom
                          FROM equipes t
                          LEFT JOIN equipes_employes te ON t.id = te.equipe_id
                          LEFT JOIN employes e ON te.employe_id = e.id
                            WHERE t.user_id = %s
                            ORDER BY t.nom, e.nom, e.prenom
                """
                cursor.execute(query, (user_id,))
                rows = cursor.fetchall()
                equipes = {}
                for row in rows:
                    equipe_id = row['id']
                    if equipe_id not in equipes:
                        equipes[equipe_id] = {
                            'id': equipe_id,
                            'nom': row['nom'],
                            'membres': []
                        }
                    if row['employe_id']:
                        equipes[equipe_id]['membres'].append({
                            'id': row['employe_id'],
                            'nom': row['employe_nom'],
                            'prenom': row['employe_prenom']
                        })
                return list(equipes.values())
        except Exception as e:
            logger.error(f"Erreur récupération des équipes avec employes de user {user_id}: {e}")
            return []

    def get_all_by_user(self, user_id: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT * FROM equipes WHERE user_id = %s ORDER BY nom", (user_id,))
                return cursor.fetchall()
        except Exception as e:  
            logger.error(f"Erreur récupération équipes user {user_id}: {e}")
            return []

class Competence:
    def __init__(self, db):
        self.db = db
    def create(self, user_id: int, nom: str) -> int:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                INSERT INTP competences (user_id, nom, created_at)
                VALUES (%s, %s, NOW())
                """, (user_id, nom))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Erreur créatio competence : {e}")
            return None
    def modifier(self, user_id:int, nom: str, id_competence: int)-> int:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.excecute("""
                UPDATE competences
                SET nom = %s
                WHERE id= %s AND user_id = %s
                """, (nom, id_competence, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur mise à jour compétence : {e}")
            return False
    def supprimer(self, user_id: int, id_competence: int)-> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM employes_competences WHERE id_competence = %s", (id_competence,))
                cursor.execute("DELETE FROM equipes_competences_requises WHERE id_competence = %s", (id_competence,))
                cursor.execute("DELETE FROM competences WHERE id = %s AND user_id = %s", (id_competence, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur suppression compétence {id_competence} : {e}")
            return False
    def assigner_employe_competence(self, employe_model, id_competence: int, employe_id: int, user_id:int) -> bool:
        if not employe_model.get_by_id(employe_id, user_id):
            return False
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT IGNORE INTO employes_competences (id_competence, employe_id, assigned_at)
                    VALUES (%s, %s, NOW())
                """, (id_competence, employe_id))
                return True
        except Exception as e:
            logger.error(f"Erreur assignation compétence {id_competence} à employé {employe_id} : {e}")
            return False
    def retirer_de_employe(self, id_competence: int, employe_id: int) -> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                    DELETE FROM employes_competences
                    WHERE competence_id = %s AND employe_id = %s
                """, (id_competence, employe_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur retrait compétence {id_competence} de employé {employe_id} : {e}")
            return False

    def get_competences_employe(self, employe_id: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT c.id, c.nom
                    FROM competences c
                    JOIN employes_competences ec ON c.id = ec.competence_id
                    WHERE ec.employe_id = %s
                """, (employe_id,))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération compétences employé {employe_id} : {e}")
            return []
    def get_employes_avec_competence(self, user_id: int, id_competence: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT e.*
                    FROM employes e
                    JOIN employes_competences ec ON e.id = ec.employe_id
                    WHERE ec.competence_id = %s AND e.user_id = %s
                """, (id_competence, user_id))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération employés compétence {id_competence} : {e}")
            return []
    def definir_competence_requise_equipe(self, equipe_model, user_id: int, equipe_id: int, id_competence: int, quantite_min: int = 1) -> bool:
        # Vérifier que l’équipe appartient à l’utilisateur
        equipes = equipe_model.get_all_by_user(user_id)
        if not any(eq['id'] == equipe_id for eq in equipes):
            return False
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO equipes_competences_requises (equipe_id, id_competence, quantite_min)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE quantite_min = VALUES(quantite_min)
                """, (equipe_id, id_competence, quantite_min))
                return True
        except Exception as e:
            logger.error(f"Erreur définition comp. requise équipe {equipe_id} : {e}")
            return False
    def get_competences_requises_equipe(self, user_id: int, equipe_id: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT c.id, c.nom, ecr.quantite_min
                    FROM competences c
                    JOIN equipes_competences_requises ecr ON c.id = ecr.competence_id
                    JOIN equipes eq ON ecr.equipe_id = eq.id
                    WHERE eq.id = %s AND eq.user_id = %s
                """, (equipe_id, user_id))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récupération comp. requises équipe {equipe_id} : {e}")
            return []

class Planning:
    def __init__(self, db):
        self.db = db

    def creer_shift(self, data: Dict)-> bool:
        "Crée un créneau horaire"
        required = ('employe_id', 'date', 'heure_debut', 'heure_fin', 'type_shift')
        if not all(k in data for k in required):
            raise ValueError("Champs manquants")
        try:
            with self.db.get_cursor(commit=True) as cursor:
                query = """
                INSERT INTO shifts
                (employe_id, date, heure_debut, heure_fin, type_shift, commentaire, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """
                values = (
                    data['employe_id'],
                    data['date'],
                    data['heure_debut'],
                    data['heure_fin'],
                    data['type_shift'],
                    data.get('commentaire', '')
                )
                cursor.execute(query, values)
                return True
        except Error as e:
            logger.error("Erreur création shift {e}")
            return False

    def get_shifts_for_period(self, user_id: int, date_debut: str, date_fin: str)-> Dict:
        "Récupère tous les créneaux horaires pour une période donnée"
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT s.*, e.nom, e.prenom, e.id as employe_id
                FROM shifts s
                JOIN employes e ON s.employe_id = e.id
                WHERE user_id = %s
                AND s.date BETWEEN %s AND %s
                ORDER BY s.date, s.heure_debut
                """
                cursor.execute(query, (user_id, date_debut, date_fin))
                shifts = cursor.fetchall()

                organized = {}
                for shift in shifts:
                    employe_id = shift['employe_id']
                    date_str = str(shift['date'])
                    
                    if employe_id not in organized:
                        organized[employe_id] = {}  # Correction : '=' au lieu de ':'
                    
                    if date_str not in organized[employe_id]: # Correction : [] au lieu de ()
                        organized[employe_id][date_str] = []  # Correction : '=' au lieu de ':'
                        
                    organized[employe_id][date_str].append(shift)

                return organized
        except Exception as e:
            logger.error(f"Erreur récupération shifts: {e}")

class PlanningRegles:
    def __init__(self, db):
        self.db = db

    def create_regle(self, user_id: int, nom: str, type_regle: str, params: Dict[str, Any]) -> int:
        """
        Types supportés :
          - 'competence_min_simulee'
          - 'bilinguisme_simultane_simule'
        """
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("""
                    INSERT INTO planning_regles (user_id, nom, type_regle, params_json, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                """, (user_id, nom, type_regle, json.dumps(params)))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Erreur création règle planning : {e}")
            return None

    def get_regles_by_user(self, user_id: int) -> List[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT id, nom, type_regle, params_json
                    FROM planning_regles
                    WHERE user_id = %s
                    ORDER BY nom
                """, (user_id,))
                return [
                    {**row, 'params': json.loads(row['params_json'])}
                    for row in cursor.fetchall()
                ]
        except Exception as e:
            logger.error(f"Erreur récup règles user {user_id} : {e}")
            return []

    def delete_regle(self, user_id: int, regle_id: int) -> bool:
        try:
            with self.db.get_cursor(commit=True) as cursor:
                cursor.execute("DELETE FROM planning_regles WHERE id = %s AND user_id = %s", (regle_id, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Erreur suppression règle {regle_id} : {e}")
            return False

    def valider_periode_simulee(self, user_id: int, date_debut: date, date_fin: date) -> List[Dict]:
        """
        Valide les règles sur les **heures simulées** uniquement.
        """
        violations = []
        regles = self.get_regles_by_user(user_id)

        for regle in regles:
            if regle['type_regle'] == 'competence_min_simulee':
                violations += self._valider_competence_min_simulee(user_id, regle, date_debut, date_fin)
            elif regle['type_regle'] == 'bilinguisme_simultane_simule':
                violations += self._valider_bilinguisme_simultane_simule(user_id, regle, date_debut, date_fin)

        return violations

    def _get_employes_simules_jour(self, user_id: int, equipe_id: int, date_jour: date) -> List[Dict]:
        """
        Récupère les employés **planifiés** (simulés) dans une équipe à une date donnée.
        """
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT e.*
                    FROM employes e
                    JOIN heures_simulees hs ON e.id = hs.employe_id
                    WHERE hs.user_id = %s
                      AND hs.equipe_id = %s
                      AND hs.date = %s
                """, (user_id, equipe_id, date_jour))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Erreur récup simulés {date_jour} équipe {equipe_id} : {e}")
            return []

    def _valider_competence_min_simulee(self, equipe_model, competence_model, user_id: int, regle: Dict, debut: date, fin: date) -> List[Dict]:
        params = regle['params']
        equipe_id = params.get('equipe_id')
        competence_id = params.get('competence_id')
        quantite_min = params.get('quantite_min', 1)

        # Vérifier propriété
        equipes = equipe_model.get_equipes_from_user(user_id)
        if not any(eq['id'] == equipe_id for eq in equipes):
            return []

        violations = []
        current = debut
        while current <= fin:
            employes_presents = self._get_employes_simules_jour(user_id, equipe_id, current)
            employes_qualifies = [
                e for e in employes_presents
                if competence_id in [c['id'] for c in competence_model.get_competences_employe(e['id'])]
            ]
            if len(employes_qualifies) < quantite_min:
                violations.append({
                    'regle_id': regle['id'],
                    'nom_regle': regle['nom'],
                    'type': 'competence_min_simulee',
                    'violation': f"Seulement {len(employes_qualifies)} sur {quantite_min} employés requis avec compétence ID {competence_id}",
                    'date': current.isoformat(),
                    'equipe_id': equipe_id
                })
            current += timedelta(days=1)
        return violations

    def _valider_bilinguisme_simultane_simule(self, equipe_model, competence_model,user_id: int, regle: Dict, debut: date, fin: date) -> List[Dict]:
        params = regle['params']
        equipe_id = params.get('equipe_id')

        equipes = equipe_model.get_equipes_from_user(user_id)
        if not any(eq['id'] == equipe_id for eq in equipes):
            return []

        comp_fr = self._get_competence_by_nom(user_id, 'francais')
        comp_de = self._get_competence_by_nom(user_id, 'allemand')
        if not comp_fr or not comp_de:
            return [{'regle_id': regle['id'], 'violation': "Compétences langue non trouvées", 'date': debut.isoformat()}]

        violations = []
        current = debut
        while current <= fin:
            employes_presents = self._get_employes_simules_jour(user_id, equipe_id, current)
            a_fr = any(comp_fr['id'] in [c['id'] for c in competence_model.get_competences_employe(e['id'])] for e in employes_presents)
            a_de = any(comp_de['id'] in [c['id'] for c in competence_model.get_competences_employe(e['id'])] for e in employes_presents)

            if not (a_fr and a_de):
                violations.append({
                    'regle_id': regle['id'],
                    'nom_regle': regle['nom'],
                    'type': 'bilinguisme_simultane_simule',
                    'violation': "Bilinguisme (FR+DE) manquant dans planning simulé",
                    'date': current.isoformat(),
                    'equipe_id': equipe_id
                })
            current += timedelta(days=1)
        return violations

    def _get_competence_by_nom(self, user_id: int, nom: str) -> Optional[Dict]:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT id, nom FROM competences WHERE user_id = %s AND nom = %s", (user_id, nom))
                return cursor.fetchone()
        except:
            return None

    # --- Fonctionnalité bonus : contexte réel pour aide à la planification ---
    def get_contexte_reel_pour_plage(self, user_id: int, employe_id: int, date_ref: date, plage_h1d: str, plage_h2f: str, tolerance_min: int = 30) -> Dict:
        """
        Retourne des stats réelles sur les comportements passés de l'employé
        pour des plages horaires comparables (même jour de semaine ± tolérance).
        Utile pour afficher : "en moyenne, cet employé commence 12 min plus tard que prévu".
        """
        jour_semaine = date_ref.weekday()  # 0=Lundi
        try:
            with self.db.get_cursor() as cursor:
                # Rechercher les entrées réelles du même jour de semaine ± tolérance
                cursor.execute("""
                    SELECT h1d, h2f, total_h
                    FROM heures_travail
                    WHERE user_id = %s
                      AND employe_id = %s
                      AND type_heure = 'reel'
                      AND DAYOFWEEK(date) = %s + 1  -- MySQL: 1=Dim, donc +1
                      AND date < %s
                    ORDER BY date DESC
                    LIMIT 20
                """, (user_id, employe_id, jour_semaine, date_ref))
                historique = cursor.fetchall()

                if not historique:
                    return {'message': 'Aucun historique réel trouvé'}

                # Convertir plage simulée en minutes
                h1d_sim = self._time_to_minutes(plage_h1d)
                h2f_sim = self._time_to_minutes(plage_h2f)

                ecarts_h1d = []
                ecarts_h2f = []
                for h in historique:
                    h1d_r = self._time_to_minutes(h['h1d'])
                    h2f_r = self._time_to_minutes(h['h2f'])
                    if h1d_r != -1 and h1d_sim != -1:
                        ecarts_h1d.append(h1d_r - h1d_sim)
                    if h2f_r != -1 and h2f_sim != -1:
                        ecarts_h2f.append(h2f_r - h2f_sim)

                return {
                    'moyenne_ecart_h1d_min': round(sum(ecarts_h1d) / len(ecarts_h1d), 1) if ecarts_h1d else 0,
                    'moyenne_ecart_h2f_min': round(sum(ecarts_h2f) / len(ecarts_h2f), 1) if ecarts_h2f else 0,
                    'nb_echantillons': len(historique),
                    'plage_simulee': f"{plage_h1d} → {plage_h2f}"
                }
        except Exception as e:
            logger.error(f"Erreur contexte réel pour {employe_id} le {date_ref} : {e}")
            return {'erreur': str(e)}

    def _time_to_minutes(self, t) -> int:
        if not t:
            return -1
        if isinstance(t, str):
            h, m = map(int, t.split(':')[:2])
            return h * 60 + m
        elif hasattr(t, 'hour'):
            return t.hour * 60 + t.minute
        return -1

class ParametreUtilisateur:
    """Modèle pour gérer les paramètres utilisateur"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get(self, user_id: int) -> Dict:
        """Récupère tous les paramètres d'un utilisateur de manière sécurisée"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM parametres_utilisateur WHERE utilisateur_id = %s"
                cursor.execute(query, (user_id,))
                params = cursor.fetchone()
                return params or {}
        except Error as e:
            logger.error(f"Erreur lors de la récupération des paramètres: {e}")
            return {}

    def update(self, user_id: int, data: Dict) -> bool:
        """Met à jour les paramètres utilisateur de manière sécurisée"""
        try:
            with self.db.get_cursor(commit=True) as cursor:
                # Vérifie si l'utilisateur a déjà des paramètres
                cursor.execute("SELECT 1 FROM parametres_utilisateur WHERE utilisateur_id = %s", (user_id,))
                exists = cursor.fetchone()

                if exists:
                    # Mise à jour
                    query = """
                    UPDATE parametres_utilisateur
                    SET devise_principale = %s, theme = %s, notifications_email = %s,
                        alertes_solde = %s, seuil_alerte_solde = %s
                    WHERE utilisateur_id = %s
                    """
                    values = (
                        data.get('devise_principale', 'CHF'),
                        data.get('theme', 'clair'),
                        data.get('notifications_email', True),
                        data.get('alertes_solde', True),
                        data.get('seuil_alerte_solde', 500),
                        user_id
                    )
                else:
                    # Insertion
                    query = """
                    INSERT INTO parametres_utilisateur
                    (utilisateur_id, devise_principale, theme, notifications_email,
                    alertes_solde, seuil_alerte_solde)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                    values = (
                        user_id,
                        data.get('devise_principale', 'CHF'),
                        data.get('theme', 'clair'),
                        data.get('notifications_email', True),
                        data.get('alertes_solde', True),
                        data.get('seuil_alerte_solde', 500)
                    )

                cursor.execute(query, values)
            return True
        except Error as e:
            logger.error(f"Erreur lors de la mise à jour des paramètres: {e}")
            return False

class Entreprise:
    def __init__(self, db):
        self.db = db

    def get_or_create_for_user(self, user_id: int) -> Dict:
        """
        Récupère ou crée une entrée par défaut pour l'utilisateur.
        """
        with self.db.get_cursor(dictionary=True) as cursor:
            cursor.execute("""
                SELECT * FROM entreprise WHERE user_id = %s
            """, (user_id,))
            row = cursor.fetchone()
            if row:
                return row
            # Création par défaut
            cursor.execute("""
                INSERT INTO entreprise (user_id, nom, rue, code_postal, commune, email, telephone)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, f"Entreprise de utilisateur {user_id}", "", "", "", "", ""))
            cursor.execute("""
                SELECT * FROM entreprise WHERE user_id = %s
            """, (user_id,))
            return cursor.fetchone()

    def update(self, user_id: int, data: Dict) -> bool:
        """
        Met à jour les infos de l'entreprise.
        Champs autorisés : nom, rue, code_postal, commune, email, telephone, logo_path
        """
        allowed = {'nom', 'rue', 'code_postal', 'commune', 'email', 'telephone', 'logo_path'}
        update_data = {k: v for k, v in data.items() if k in allowed}
        if not update_data:
            return False

        set_clause = ", ".join([f"{k} = %s" for k in update_data.keys()])
        values = list(update_data.values()) + [user_id]

        with self.db.get_cursor() as cursor:
            cursor.execute(f"""
                UPDATE entreprise SET {set_clause} WHERE user_id = %s
            """, values)
            return cursor.rowcount > 0

    def get_logo_path(self, user_id: int) -> Optional[str]:
        """
        Renvoie le chemin du logo (relatif à static/) ou None.
        """
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT logo_path FROM entreprise WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    def entreprise_exists_for_user(self, user_id: int) -> bool:
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute("SELECT 1 FROM entreprise WHERE user_id = %s", (user_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Pas d'entreprise pour l'utilisateur {user_id} : {e}")
            return False


class ModelManager:
    def __init__(self, db):
        self._db = db
        self._cache = {}
    def _get_model(self, name, cls):
        if name not in self._cache:
            self._cache[name] = cls(self._db)
        return self._cache[name]
    @property
    def banque_model(self):
        return self._get_model('banque', Banque)
    @property
    def periode_favorite_model(self):
        return self._get_model('periode_favorite', PeriodeFavorite)
    @property       
    def compte_model(self):
        return self._get_model('compte', ComptePrincipal)
    @property
    def compte__principal_rapport_model(self):
        return self._get_model('compte__principal_rapport', ComptePrincipalRapport)
    @property
    def sous_compte_model(self):
        return self._get_model('sous_compte', SousCompte)
    @property
    def transaction_financiere_model(self):
        return self._get_model('transaction_financiere', TransactionFinanciere)
    @property   
    def categorie_transaction_model(self):
        return self._get_model('categorie_transaction', CategorieTransaction)
    @property
    def stats_model(self):
        return self._get_model('stats', StatistiquesBancaires)
    @property
    def plan_comptable_model(self):
        return self._get_model('plan_comptable', PlanComptable)
    @property
    def categorie_comptable_model(self):
        return self._get_model('categorie_comptable', CategorieComptable)
    @property
    def ecriture_comptable_model(self):
        return self._get_model('ecriture_comptable', EcritureComptable)
    @property
    def contact_plan_model(self):
        return self._get_model('contact_plan', ContactPlan)
    @property
    def contact_model(self):
        return self._get_model('contact', Contacts)
    @property
    def contact_compte_model(self):
        return self._get_model('contact_compte', ContactCompte)
    @property
    def contact_plan_model(self):
        return self._get_model('contact_plan', ContactPlan)
    @property
    def rapport_model(self):
        self.bareme_cotisation_model = BaremeCotisation(self.db)
    @property
    def bareme_indemnite_model(self):
        return self._get_model('bareme_indemnite', BaremeIndemnite)
    @property
    def type_cotisations_model(self):
        return self._get_model('type_cotisations', TypeCotisation)
    @property
    def type_indemnites_model(self):
        return self._get_model('type_indemnites', TypeIndemnite)
    @property
    def cotisations_contrat_model(self):
        return self._get_model('cotisations_contrat', CotisationContrat)
    @property
    def indemnites_contrat_model(self):
        return self._get_model('indemnites_contrat', IndemniteContrat)
    @property
    def heure_model(self):
        return self._get_model('heure', HeureTravail)
    @property
    def salaire_model(self):
        return self._get_model('salaire', Salaire)
    @property
    def synthese_hebdo_model(self):
        return self._get_model('synthese_hebdo', SyntheseHebdomadaire)
    @property
    def synthese_mensuelle_model(self):
        return self._get_model('synthese_mensuelle', SyntheseMensuelle)
    @property
    def contrat_model(self):
        return self._get_model('contrat', Contrat)
    @property
    def employe_model(self):
        return self._get_model('employe', Employe)
    @property
    def equipe_model(self):
        return self._get_model('equipe', Equipe)
    @property
    def competence_model(self):
        return self._get_model('competence', Competence)
    @property
    def planning_model(self):
        return self._get_model('planning', Planning)
    @property
    def planning_regles_model(self):
        return self._get_model('planning_regles', PlanningRegles)
    @property
    def entreprise_model(self):
        return self._get_model('entreprise', Entreprise)
    @property
    def parametre_utilisateur_model(self):
        return self._get_model('parametre_utilisateur', ParametreUtilisateur)
    def get_user_by_username(self, username):
        """
        Récupère un utilisateur par nom d'utilisateur.
        Ceci est un exemple de fonction de modèle.
        """
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM users WHERE username = %s"
                cursor.execute(query, (username,))
                user_data = cursor.fetchone()
                return user_data
        except Exception as e:
            logger.error(f"Erreur lors de la récupération de l'utilisateur : {e}")
            return None

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modèles de données pour la gestion bancaire
Classes pour manipuler les banques, comptes et sous-comptes
"""
import statistics
from dbutils.pooled_db import PooledDB
import pymysql
from pymysql import Error
from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
import csv
import os
import uuid
import time
import math
from collections import defaultdict

from typing import List, Dict, Optional, Tuple, TypedDict
import traceback
from contextlib import contextmanager
from flask_login import UserMixin
import logging
from flask import current_app
import secrets


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
            logging.info("Initialisation du pool de connexions avec DBUtils...")
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
                logging.info("Pool de connexions DBUtils initialisé avec succès.")
            except Error as err:
                logging.error(f"Erreur lors de l'initialisation du pool de connexions : {err}")
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
            logging.info("Pool de connexions fermé")
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
            logging.error(f"Erreur dans le gestionnaire de curseur : {e}", exc_info=True)
            if connection:
                try:
                    connection.rollback()  # Annule les changements en cas d'erreur
                except Exception as rollback_error:
                    logging.error(f"Erreur lors du rollback : {rollback_error}", exc_info=True)
            raise  # Relance l'exception
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception as close_error:
                    logging.error(f"Erreur lors de la fermeture du curseur : {close_error}", exc_info=True)
            if connection:
                try:
                    connection.close()  # Retourne la connexion au pool
                except Exception as close_error:
                    logging.error(f"Erreur lors de la fermeture de la connexion : {close_error}", exc_info=True)

    def create_tables(self):
        """
        Crée toutes les tables de la base de données si elles n'existent pas.
        """
        logging.info("Vérification et création des tables de la base de données...")
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
                    genre ENUM('M', 'F', 'Autre') NOT NULL,
                    date_de_naissance DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id) ON DELETE CASCADE
                );"""
                cursor.execute(create_employes_table_query)

            logging.info("Toutes les tables ont été vérifiées/créées avec succès.")
        
        except Exception as e:
            logging.error(f"Erreur lors de la création des tables : {e}")

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
        """
        Charge l'utilisateur depuis la base de données en utilisant le gestionnaire de contexte.
        """
        try:
            with db.get_cursor(dictionary=True) as cursor:
                query = "SELECT id, nom, prenom, email, mot_de_passe FROM utilisateurs WHERE id = %s"
                cursor.execute(query, (user_id,))
                row = cursor.fetchone()
                if row:
                    return Utilisateur(row['id'], row['nom'], row['prenom'], row['email'], row['mot_de_passe'])
                return None
        except Error as e:
            logging.error(f"Erreur lors de la récupération de l'utilisateur: {e}")
            return None

    @staticmethod
    def get_by_email(email: str, db):
        """
        Récupère un utilisateur par son adresse email.
        """
        try:
            with db.get_cursor(dictionary=True) as cursor:
                cursor.execute("SELECT id, nom, prenom, email, mot_de_passe FROM utilisateurs WHERE email = %s", (email,))
                row = cursor.fetchone()
                if row:
                    return Utilisateur(row['id'], row['nom'], row['prenom'], row['email'], row['mot_de_passe'])
                return None
        except Error as e:
            logging.error(f"Erreur lors de la récupération de l'utilisateur par email: {e}")
            return None

    @staticmethod
    def create(nom: str, prenom: str, email: str, mot_de_passe: str, db):
        """
        Crée un nouvel utilisateur dans la base de données.
        """
        try:
            with db.get_cursor() as cursor:
                cursor.execute("""
                    INSERT INTO utilisateurs (nom, prenom, email, mot_de_passe)
                    VALUES (%s, %s, %s, %s)
                """, (nom, prenom, email, mot_de_passe))
                user_id = cursor.lastrowid
                logging.info(f"Utilisateur créé avec ID: {user_id}")
            return user_id
        except Error as e:
            logging.error(f"Erreur création utilisateur : {e}")
            return False

class Contrat:
    def __init__(self, db):
        self.db = db

    def create_or_update(self, data: Dict) -> bool:
        try:
            with self.db.get_cursor() as cursor:
                if 'id' in data and data['id']:
                    # Mise à jour
                    query = """
                        UPDATE contrats
                        SET 
                            employeur = %s,
                            heures_hebdo = %s, 
                            date_debut = %s, 
                            date_fin = %s,
                            salaire_horaire = %s,
                            jour_estimation_salaire = %s,
                            versement_10 = %s,
                            versement_25 = %s,
                            indemnite_vacances_tx = %s,
                            indemnite_jours_feries_tx = %s,
                            indemnite_jour_conges_tx = %s,
                            indemnite_repas_tx = %s,
                            indemnite_retenues_tx = %s,
                            cotisation_avs_tx = %s,
                            cotisation_ac_tx = %s,
                            cotisation_accident_n_prof_tx = %s,
                            cotisation_assurance_indemnite_maladie_tx = %s,
                            cotisation_cap_tx = %s
                        WHERE id = %s;
                    """
                    params = (
                        data['employeur'], 
                        data['heures_hebdo'], 
                        data['date_debut'], 
                        data.get('date_fin'),
                        data.get('salaire_horaire', 24.05),
                        data.get('jour_estimation_salaire', 15),
                        bool(data.get('versement_10', True)),
                        bool(data.get('versement_25', True)),
                        data.get('indemnite_vacances_tx', 0),
                        data.get('indemnite_jours_feries_tx', 0),
                        data.get('indemnite_jour_conges_tx', 0),
                        data.get('indemnite_repas_tx', 0),
                        data.get('indemnite_retenues_tx', 0),
                        data.get('cotisation_avs_tx', 0),
                        data.get('cotisation_ac_tx', 0),
                        data.get('cotisation_accident_n_prof_tx', 0),
                        data.get('cotisation_assurance_indemnite_maladie_tx', 0),
                        data.get('cotisation_cap_tx', 0),
                        data['id']
                    )
                else:
                    # Insertion
                    query = """
                    INSERT INTO contrats 
                    (user_id, employeur, heures_hebdo, date_debut, date_fin,
                    salaire_horaire, jour_estimation_salaire, versement_10, versement_25, 
                    indemnite_vacances_tx, indemnite_jours_feries_tx, indemnite_jour_conges_tx, 
                    indemnite_repas_tx, indemnite_retenues_tx,
                    cotisation_avs_tx, cotisation_ac_tx, cotisation_accident_n_prof_tx, 
                    cotisation_assurance_indemnite_maladie_tx, cotisation_cap_tx)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """
                    params = (
                        data['user_id'], data['employeur'], data['heures_hebdo'], data['date_debut'], data.get('date_fin'),
                        data.get('salaire_horaire', 24.05),
                        data.get('jour_estimation_salaire', 15),
                        bool(data.get('versement_10', True)),
                        bool(data.get('versement_25', True)),
                        data.get('indemnite_vacances_tx', 0),
                        data.get('indemnite_jours_feries_tx', 0),
                        data.get('indemnite_jour_conges_tx', 0),
                        data.get('indemnite_repas_tx', 0),
                        data.get('indemnite_retenues_tx', 0),
                        data.get('cotisation_avs_tx', 0),
                        data.get('cotisation_ac_tx', 0),
                        data.get('cotisation_accident_n_prof_tx', 0),
                        data.get('cotisation_assurance_indemnite_maladie_tx', 0),
                        data.get('cotisation_cap_tx', 0)
                    )

                cursor.execute(query, params)
                return True
                
        except Exception as e:
            logging.error(f"Erreur lors de la création/mise à jour du contrat: {e}")
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
            logging.error(f"Erreur lors de la récupération du contrat: {e}")
            return None

    def get_all_contrats(self, user_id: int) -> List[Dict]:
        """Liste tous les contrats de l'utilisateur, du plus récent au plus ancien."""
        try:
            with self.db.get_cursor(dictionary=True) as cursor:
                query = "SELECT * FROM contrats WHERE user_id = %s ORDER BY date_debut ASC;"
                logging.debug(f"SQL: {query} | Params: {user_id}")
                cursor.execute(query, (user_id,))  # ← CORRIGÉ : virgule ajoutée
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des contrats: {e}")
            return []

    def delete(self, contrat_id: int) -> bool:
        """Supprime un contrat par son id."""
        try:
            with self.db.get_cursor() as cursor:
                query = "DELETE FROM contrats WHERE id = %s;"
                cursor.execute(query, (contrat_id,))
                return True
        except Exception as e:
            logging.error(f"Erreur lors de la suppression du contrat: {e}")
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
            logging.error(f"Erreur lors de la récupération du contrat pour la date {date_str}: {e}")
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
            logging.error(f"Erreur lors de la récupération des contrats actifs: {e}")
            return []

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
                current_app.logger.error(f"Impossible d'obtenir une connexion ou erreur d'exécution: {str(e)}")
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
                WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s 
                    AND employe_id IS NOT DISTINCT FROM %S AND type_heure_heures = %s
                """,
                (date_obj, cleaned_data['date'], cleaned_data['user_id'], 
                cleaned_data['employeur'], cleaned_data['id_contrat'],
                cleaned_data['employe_id'], cleaned_data['type_heures'])
            )
            existing = cursor.fetchone()
            
            # Préparer les valeurs avec fallback
            values = {
                'date': date_obj,
                'user_id': cleaned_data['user_id'],
                'employe_id' : cleaned_data['employe_id'],
                'employeur': cleaned_data['employeur'],
                'id_contrat': cleaned_data.get('id_contrat'),
                'vacances': cleaned_data.get('vacances', False),
                'type_heures': cleaned_data['type_heures']
            }
            
            # Gestion des champs horaires avec protection
            for field in ['h1d', 'h1f', 'h2d', 'h2f']:
                if field in cleaned_data:
                    values[field] = cleaned_data[field]
                elif existing:
                    values[field] = existing.get(field)
                else:
                    values[field] = None
            
            # Calculer le total
            values['total_h'] = self.calculer_heures(
                values.get('h1d'),
                values.get('h1f'),
                values.get('h2d'),
                values.get('h2f')
            )
            
            # Requête UPSERT unique
            upsert_query = """
            INSERT INTO heures_travail
            (date, user_id, employe_id, employeur, id_contrat, h1d, h1f, h2d, h2f, total_h, type_heures, vacances, jour_semaine, semaine_annee, mois)
            VALUES (%(date)s, %(user_id)s, %(employe_id)s, %(employeur)s, %(id_contrat)s, %(h1d)s, %(h1f)s, %(h2d)s, %(h2f)s, %(total_h)s, %(type_heures)s, %(vacances)s, %(jour_semaine)s, %(semaine_annee)s, %(mois)s)
            ON DUPLICATE KEY UPDATE
                h1d = COALESCE(VALUES(h1d), h1d),
                h1f = COALESCE(VALUES(h1f), h1f),
                h2d = COALESCE(VALUES(h2d), h2d),
                h2f = COALESCE(VALUES(h2f), h2f),
                total_h = VALUES(total_h),
                type_heures = VALUES(type_heures),         -- ✅
                vacances = COALESCE(VALUES(vacances), vacances),
                jour_semaine = VALUES(jour_semaine),
                semaine_annee = VALUES(semaine_annee),
                mois = VALUES(mois);
            """
            
            # Ajouter les métadonnées calculées
            values.update({
                'jour_semaine': date_obj.strftime('%A'),
                'semaine_annee': date_obj.isocalendar()[1],
                'mois': date_obj.month
            })
            
            cursor.execute(upsert_query, values)
            return True
            
        except Exception as e:
            current_app.logger.error(f"Erreur _execute_create_or_update: {str(e)}")
            return False
        
    def _clean_data(self, data: dict) -> dict:
        cleaned = data.copy()
    
        # Nettoyer uniquement les champs time présents
        time_fields = ['h1d', 'h1f', 'h2d', 'h2f']
        for field in time_fields:
            if field in cleaned:
                value = str(cleaned[field]).strip()
                cleaned[field] = value if value else None
        
        # Normaliser le champ vacances si présent
        if 'vacances' in cleaned:
            cleaned['vacances'] = bool(cleaned['vacances'])
        if 'employe_id' in cleaned:
        # Accepte None ou un entier
            if cleaned['employe_id'] is not None:
                cleaned['employe_id'] = int(cleaned['employe_id'])
        else:
            cleaned['employe_id'] = None

        # type_heures : 'reelles' ou 'simulees'
        cleaned['type_heures'] = cleaned.get('type_heures', 'reelles')
        if cleaned['type_heures'] not in ('reelles', 'simulees'):
            cleaned['type_heures'] = 'reelles'
            
        # Validation des champs obligatoires
        if 'user_id' not in cleaned or cleaned['user_id'] is None:
            raise ValueError("user_id manquant dans les données")
        
        if 'date' not in cleaned or not cleaned['date']:
            raise ValueError("date manquante dans les données")
        if 'employeur' not in cleaned or not cleaned['employeur']:
            raise ValueError("employeur manquant dans les données")
        if 'id_contrat' not in cleaned or cleaned['id_contrat'] is None:
            raise ValueError("id_contrat manquant dans les données")
        
        return cleaned

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

    def get_by_date(self, date_str: str, user_id: int, employeur: str, id_contrat: int) -> Optional[Dict]:
        """Récupère les données pour une date et un utilisateur donnés"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM heures_travail WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s"
                current_app.logger.debug(f"[get_by_date] Query: {query} avec params: ({date_str}, {user_id}, {employeur}, {id_contrat})")

                cursor.execute(query, (date_str, user_id, employeur, id_contrat))
                jour = cursor.fetchone()
                
                if jour:
                    current_app.logger.debug(f"[get_by_date] Données trouvées pour {date_str}, user_id: {user_id}, employeur: {employeur}, id_contrat: {id_contrat}  ")
                    self._convert_timedelta_fields(jour, ['h1d', 'h1f', 'h2d', 'h2f'])
                else:
                    current_app.logger.debug(f"[get_by_date] Aucune donnée trouvée pour {date_str}, user_id: {user_id}, employeur: {employeur}, id_contrat: {id_contrat}  ")

                return jour
                
        except Exception as e:
            current_app.logger.error(f"Erreur get_by_date pour {date_str}: {str(e)}")
            return None

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

                current_app.logger.debug(f"[get_jours_travail] Query: {query} avec params: {params}")
                cursor.execute(query, params)
                jours = cursor.fetchall()
                
                current_app.logger.debug(f"[get_jours_travail] {len(jours)} jours trouvés")
                
                for jour in jours:
                    self._convert_timedelta_fields(jour, ['h1d', 'h1f', 'h2d', 'h2f'])
                
                return jours
                
        except Exception as e:
            current_app.logger.error(f"Erreur get_jours_travail: {str(e)}")
            return []

    def delete_by_date(self, date_str: str, user_id: int, employeur: str, id_contrat: int) -> bool:
        """Supprime les données pour une date et un utilisateur donnés"""
        try:
            with self.db.get_cursor(commit=True) as cursor:
                query = "DELETE FROM heures_travail WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s"
                current_app.logger.debug(f"[delete_by_date] Query: {query} avec params: ({date_str}, {user_id}, {employeur}, {id_contrat})")

                cursor.execute(query, (date_str, user_id, employeur, id_contrat))
                rows_affected = cursor.rowcount
                
                current_app.logger.debug(f"[delete_by_date] {rows_affected} ligne(s) supprimée(s) pour {date_str}")
                return True
                
        except Exception as e:
            current_app.logger.error(f"Erreur delete_by_date pour {date_str}: {str(e)}")
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
                current_app.logger.info(f"get_total_heures_mois → user={user_id}, mois={mois}/{annee}, employeur={employeur}, contrat={id_contrat} → total={total}")
                return total
        except Exception as e:
            current_app.logger.error(f"Erreur get_total_heures_mois: {e}")
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
                current_app.logger.info(f"get_heures_periode → user={user_id}, mois={mois}/{annee}, jours={start_day}-{end_day}, employeur={employeur}, contrat={id_contrat} → total={total}")
                return total
        except Exception as e:
            current_app.logger.error(f"Erreur get_heures_periode: {e}")
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
                            current_app.logger.warning(f"[Import CSV] id_contrat manquant pour la ligne avec date : {row}. Ligne ignorée.")
                            continue
                        try:
                            id_contrat = int(id_contrat)
                        except ValueError:
                            current_app.logger.warning(f"[Import CSV] id_contrat invalide pour la ligne avec date : {id_contrat}")
                            continue
                        if not date_str or not employeur:
                            continue

                        try:
                            date_obj = datetime.fromisoformat(date_str).date()
                        except ValueError:
                            current_app.logger.warning(f"[Import CSV] Date invalide ignorée : {date_str}")
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

            current_app.logger.info(f"[Import CSV] {lignes_importees} lignes importées avec succès")
            return lignes_importees

        except Exception as e:
            current_app.logger.error(f"[Import CSV] Erreur : {e}")
            return 0


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
            current_app.logger.error(f"Erreur has_hours_for_employeur: {e}")
            return False

    
    def get_h1d_h2f_for_period(self, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int = None, semaine: int = None) -> List[Dict]:
        """
        Récupère les heures de début (h1d) et de fin (h2f) pour une période donnée.
        Si 'mois' est spécifié, récupère les données du mois.
        Si 'semaine' est spécifiée, récupère les données de la semaine.
        """
        try:
            with self.db.get_cursor() as cursor:
                if semaine is not None:
                    query = """
                    SELECT date, h1d, h2f
                    FROM heures_travail
                    WHERE user_id = %s AND employeur = %s AND id_contrat = %s
                    AND YEAR(date) = %s AND semaine_annee = %s
                    ORDER BY date
                    """
                    params = (user_id, employeur, id_contrat, annee, semaine)
                elif mois is not None:
                    query = """
                    SELECT date, h1d, h2f
                    FROM heures_travail
                    WHERE user_id = %s AND employeur = %s AND id_contrat = %s
                    AND YEAR(date) = %s AND mois = %s
                    ORDER BY date
                    """
                    params = (user_id, employeur, id_contrat, annee, mois)
                else:
                    # Si ni mois ni semaine n'est spécifié, on pourrait récupérer l'année entière
                    # ou lever une erreur. Ici, on lève une erreur.
                    raise ValueError("Vous devez spécifier soit 'mois', soit 'semaine'.")

                cursor.execute(query, params)
                rows = cursor.fetchall()

                # Convertir les timedelta en HH:MM pour l'affichage
                for row in rows:
                    self._convert_timedelta_fields(row, ['h1d', 'h2f'])

                return rows
        except Exception as e:
            current_app.logger.error(f"Erreur get_h1d_h2f_for_period: {e}")
            return []

    def get_jour_travaille(self, date_str: str, user_id: int, employeur: str, id_contrat: int) -> Optional[Dict]:
        """
        Récupère les heures de début (h1d) et de fin (h2f) pour une date spécifique.
        """
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT date, h1d, h2f
                FROM heures_travail
                WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s
                """
                cursor.execute(query, (date_str, user_id, employeur, id_contrat))
                jour = cursor.fetchone()
                if jour:
                    self._convert_timedelta_fields(jour, ['h1d', 'h2f'])
                return jour
        except Exception as e:
            current_app.logger.error(f"Erreur get_jour_travaille pour {date_str}: {e}")
            return None

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
        

class Salaire:
    def __init__(self, db):
        self.db = db
        self.heure_model = HeureTravail(self.db)
    
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
            current_app.logger.error(f"Erreur création salaire: {e}")
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

        set_clauses = []
        values = []
        for key, value in update_data.items():
            set_clauses.append(f"{key} = %s")
            values.append(value)
        
        values.append(salaire_id)
        
        try:
            with self.db.get_cursor() as cursor:
                if not cursor:
                    return False
                    
                query = f"UPDATE salaires SET {', '.join(set_clauses)} WHERE id = %s"
                cursor.execute(query, values)
            return True
        except Exception as e:
            current_app.logger.error(f"Erreur mise à jour salaire: {e}")
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
            current_app.logger.error(f"Erreur suppression salaire: {e}")
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
                logging.info(f'ligne 4785 salaire selectionné: {result}')
                return result
        except Exception as e:
            current_app.logger.error(f"Erreur récupération salaire par mois/année: {e}")
            return []

    def calculer_salaire(self, heures_reelles: float, salaire_horaire: float) -> float:
        try:
            heures_reelles = round(heures_reelles, 2)
            return round(heures_reelles * float(salaire_horaire), 2)
        except Exception as e:
            current_app.logger.error(f"Erreur calcul salaire: {e}")
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
            current_app.logger.error(f"Erreur calcul salaire net: {e}")
            return 0.0
    

    def calculer_salaire_net_avec_details(self, heures_reelles: float, contrat: Dict, user_id: int = None, annee: int = None, 
                                        mois: int = None, jour_estimation: int = 15) -> Dict:
        """
        Calcule le salaire net et retourne tous les détails du calcul pour affichage
        avec des noms explicites pour chaque élément
        """
        try:
            # Validation des paramètres
            if not contrat or heures_reelles <= 0:
                return {
                    'salaire_net': 0.0,
                    'erreur': 'Paramètres invalides',
                    'details': {}
                }
            
            # Conversion du salaire horaire
            salaire_horaire = contrat.get('salaire_horaire', 24.05)
            if isinstance(salaire_horaire, Decimal):  # Utilisez Decimal directement
                salaire_horaire = float(salaire_horaire)
            elif isinstance(salaire_horaire, str):
                salaire_horaire = float(salaire_horaire)
            
            # Calcul du salaire brut
            salaire_brut = round(heures_reelles * salaire_horaire, 2)
            
            # Récupération des taux depuis le contrat
            def get_taux(key, default=0.0):
                value = contrat.get(key, default)
                if isinstance(value, Decimal):  # Utilisez Decimal directement
                    return float(value)
                elif isinstance(value, str):
                    return float(value) if value else default
                elif isinstance(value, bool):
                    return default if not value else default
                return float(value) if value is not None else default
            
            # Dictionnaire des noms pour les indemnités
            noms_indemnites = {
                'vacances': 'Indemnité de vacances',
                'jours_feries': 'Indemnité de jours fériés',
                'jour_conges': 'Indemnité de jours de congés',
                'repas': 'Indemnité de repas',
                'retenues': 'Retenues pour indemnités'
            }
            
            # Récupération des taux d'indemnités (en pourcentage)
            indemnites = {}
            for key, nom in noms_indemnites.items():
                taux_key = f'indemnite_{key}_tx'
                taux = get_taux(taux_key, 0.0)
                indemnites[key] = {
                    'nom': nom,
                    'taux': taux,
                    'montant': 0.0,
                    'actif': taux > 0 
                }
            
            # Calcul des montants d'indemnités
            total_indemnites = 0.0
            for key, info in indemnites.items():
                if info['actif']:
                    info['montant'] = round(salaire_brut * (info['taux'] / 100), 2)
                    total_indemnites += info['montant']
            
            salaire_brut_tot = salaire_brut + total_indemnites
            
            # Dictionnaire des noms pour les cotisations
            noms_cotisations = {
                'avs': 'AVS/AI/APG',
                'ac': 'Assurance chômage (AC)',
                'accident_n_prof': 'Accidents non professionnels',
                'assurance_indemnite_maladie': 'Assurance indemnité journalière maladie',
                'cap': 'Retenue pour la capitalisation (2ème pilier)'
            }
            
            # Récupération des taux de cotisations
            cotisations = {}
            for key, nom in noms_cotisations.items():
                taux_key = f'cotisation_{key}_tx'
                taux = get_taux(taux_key, 0.0)
                cotisations[key] = {
                    'nom': nom,
                    'taux': taux,
                    'montant': 0.0
                }
                
            # Calcul des montants de cotisations
            total_cotisations = 0.0
            for key, info in cotisations.items():
                # Si le taux est >= 10, on considère que c'est un montant fixe, sinon un pourcentage
                if info['taux'] < 10:
                    info['montant'] = round(salaire_brut_tot * (info['taux'] / 100), 2)
                else:
                    info['montant'] = info['taux']  # Montant fixe
                total_cotisations += info['montant']
            
            # Calcul des versements anticipés
            versements = {}
            total_versements = 0.0
            
            # Calcul des acomptes avec la même logique que calculer_acompte_25/10
            if user_id is not None and annee is not None and mois is not None:
                try:
                    # Calcul acompte du 25
                    if contrat.get('versement_25', False):
                        acompte_25 = self.calculer_acompte_25(
                            user_id=user_id, 
                            annee=annee, 
                            mois=mois, 
                            salaire_horaire=salaire_horaire, 
                            employeur=contrat['employeur'],
                            id_contrat=contrat['id'],
                            jour_estimation=contrat.get('jour_estimation_salaire', 15)
                        )
                        versements['acompte_25'] = {
                            'nom': 'Acompte du 25',
                            'actif': True,
                            'montant': round(acompte_25, 2),
                            'taux': 25
                        }
                        total_versements += acompte_25
                    
                    # Calcul acompte du 10
                    if contrat.get('versement_10', False):
                        acompte_10 = self.calculer_acompte_10(
                            user_id=user_id, 
                            annee=annee, 
                            mois=mois, 
                            salaire_horaire=salaire_horaire,
                            employeur=contrat['employeur'], 
                            id_contrat=contrat['id'],
                            jour_estimation=contrat.get('jour_estimation_salaire', 15)
                        )
                        versements['acompte_10'] = {
                            'nom': 'Acompte du 10',
                            'actif': True,
                            'montant': round(acompte_10, 2),
                            'taux': 10
                        }
                        total_versements += acompte_10
                        
                except Exception as e:
                    logging.error(f"Erreur calcul versements: {e}")
            
            # Calcul final du salaire net
            salaire_net = salaire_brut + total_indemnites - total_cotisations
            
            return {
                'salaire_net': round(salaire_net, 2),
                'erreur': None,
                'details': {
                    'heures_reelles': heures_reelles,
                    'salaire_horaire': salaire_horaire,
                    'salaire_brut': salaire_brut,
                    'indemnites': indemnites,
                    'total_indemnites': round(total_indemnites, 2),
                    'cotisations': cotisations,
                    'total_cotisations': round(total_cotisations, 2),
                    'versements': versements,
                    'total_versements': round(total_versements, 2),
                    'calcul_final': {
                        'brut': salaire_brut,
                        'plus_indemnites': round(salaire_brut + total_indemnites, 2),
                        'moins_cotisations': round(salaire_brut + total_indemnites - total_cotisations, 2),
                        'moins_versements': round(salaire_net, 2)
                    }
                }
            }
            
        except Exception as e:
            logging.error(f"Erreur détaillée dans calculer_salaire_net_avec_details: {str(e)}")
            return {
                'salaire_net': 0.0,
                'erreur': f"Erreur dans calculer_salaire_net_avec_details: {str(e)}",
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
            current_app.logger.error(f"Erreur import salaires: {e}")
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
        return round(heures * salaire_horaire, 2)
    
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
            current_app.logger.warning(
                f"Incohérence heures acompte 10: total={heures_total}, avant={heures_avant} "
                f"(user={user_id}, mois={mois}/{annee}, employeur={employeur})"
            )
            heures_apres = 0.0
        result = round(heures_apres * salaire_horaire, 2)
        current_app.logger.info(f"calculer_acompte_10 → heures_apres={heures_apres}, result={result}")
        logging.error(f"calculer_acompte_10 → heures_apres={heures_apres}, result={result}")
        return result
    
    def recalculer_salaire(self, salaire_id: int, contrat: Dict) -> bool:
        """
        Recalcule les champs dérivés d’un salaire existant à partir du contrat et des heures réelles.
        Met à jour l’entrée en base.
        """
        try:
            # 1. Récupérer le salaire existant
            salaire = self.get_by_id(salaire_id)
            if not salaire:
                current_app.logger.warning(f"Salaire ID {salaire_id} introuvable pour recalcul.")
                return False

            # 2. Extraire les données nécessaires
            heures_reelles = salaire.get('heures_reelles') or 0.0
            salaire_horaire = float(contrat.get('salaire_horaire', 27.12))
            user_id = salaire['user_id']
            employeur = salaire['employeur']
            id_contrat = salaire['id_contrat']
            annee = salaire['annee']
            mois = salaire['mois']
            jour_estimation = contrat.get('jour_estimation_salaire', 15)

            # 3. Recalculer les valeurs
            salaire_calcule = self.calculer_salaire(heures_reelles, salaire_horaire)
            salaire_net = self.calculer_salaire_net(heures_reelles, contrat)

            # Acomptes estimés
            acompte_25_estime = 0.0
            acompte_10_estime = 0.0

            if contrat.get('versement_25', False):
                acompte_25_estime = self.calculer_acompte_25(
                    user_id=user_id,
                    annee=annee,
                    mois=mois,
                    salaire_horaire=salaire_horaire,
                    employeur=employeur,
                    id_contrat=id_contrat,  # ⬅️ Correctement passé ici
                    jour_estimation=jour_estimation
                )
            if contrat.get('versement_10', False):
                acompte_10_estime = self.calculer_acompte_10(
                    user_id=user_id,
                    annee=annee,
                    mois=mois,
                    salaire_horaire=salaire_horaire,
                    employeur=employeur,
                    id_contrat=id_contrat,  # ⬅️ Correctement passé ici
                    jour_estimation=jour_estimation
                )

            # Différence avec le salaire versé (si présent)
            salaire_verse = salaire.get('salaire_verse')
            difference, difference_pourcent = self.calculer_differences(salaire_calcule, salaire_verse)

            # 4. Préparer les données à mettre à jour
            update_data = {
                'salaire_horaire': salaire_horaire,
                'salaire_calcule': salaire_calcule,
                'salaire_net': salaire_net,
                'acompte_25_estime': round(acompte_25_estime, 2),
                'acompte_10_estime': round(acompte_10_estime, 2),
                'difference': round(difference, 2),
                'difference_pourcent': round(difference_pourcent, 2),
            }

            # 5. Mettre à jour en base
            logging.info(f'update_data : {update_data}')
            return self.update(salaire_id, update_data)

        except Exception as e:
            current_app.logger.error(f"Erreur lors du recalcul du salaire ID {salaire_id}: {e}", exc_info=True)
            return False

class SyntheseHebdomadaire:
    def __init__(self, db):
        self.db = db
        self.heure_model = HeureTravail(self.db)
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
            logging.error(f"Erreur calcul synthèse hebdo par contrat: {e}")
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
            logging.error(f"Erreur synthèse hebdo: {e}")
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
            logging.error(f"Erreur batch synthèse hebdo: {e}")
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
            logging.error(f"Erreur récupération synthèses: {e}")
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
            logging.error(f"Erreur récupération synthèse hebdo année: {e}")
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
            logging.error(f"Erreur récupération synthèse par semaine: {e}")
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
            logging.error(f'erreur récupération synthpèse: {e}')
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
            logging.error(f"Erreur filtre synthèse hebdo: {e}")
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
            logging.error(f"Erreur employeurs: {e}")
            return []

    def calculate_h2f_stats(self, user_id: int, employeur: str, id_contrat: int, annee: int, seuil_h2f_minutes: int = 18 * 60) -> Dict:
        """
        Calcule les statistiques sur h2f pour une année donnée.
        seuil_h2f_minutes: seuil en minutes (ex: 18h = 18*60 min). Défaut à 18h.
        Retourne un dictionnaire avec les moyennes hebdomadaires et la moyenne mobile.
        """
        weekly_counts = {} # { semaine: nb_jours_avec_h2f_apres_seuil }

        for semaine in range(1, 53): # Semaines de 1 à 52 (ou 53)
            jours_semaine = self.heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, semaine=semaine)
            count = 0
            for jour in jours_semaine:
                h2f_minutes = self.heure_model.time_to_minutes(jour.get('h2f'))
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
    

    def prepare_svg_data_horaire_jour(self, user_id: int, employeur: str, id_contrat: int, annee: int, semaine: int, seuil_h2f_heure: float = 18.0, largeur_svg: int = 800, hauteur_svg: int = 400) -> Dict:
        """
        Prépare les données pour un graphique SVG des horaires de début/fin de journée.
        Axe X: Jours de la semaine (Lun, Mar, Mer, Jeu, Ven, Sam, Dim)
        Axe Y: Heures (6h en haut, 24h en bas)
        seuil_h2f_heure: Heure du seuil à afficher (par défaut 18h).
        """

        jours_semaine = self.heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, semaine=semaine)

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
        seuil_y = margin_y + plot_height - ((seuil_h2f_minutes - minute_debut_affichage) / plage_minutes) * plot_height

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
                current_app.logger.error(f'Type inattendu pour la date : {type(date_obj_raw)}, valeur : {date_obj_raw}')
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
                    'depasse_seuil': depasse_seuil # Indicateur pour la couleur
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
                    'depasse_seuil': False # h1d seul ne dépasse pas le seuil de h2f
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
                    'depasse_seuil': depasse_seuil # Utiliser la vérification pour h2f
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
        self.heure_model = HeureTravail(self.db)
        self.synthese_hebdo_model = SyntheseHebdomadaire(self.db)
        

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
            logging.error(f"Erreur calcul synthèse mensuelle par contrat: {e}")
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
            logging.error(f"Erreur récupération synthèse annuelle: {e}")
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
            logging.error(f"Erreur récupération synthèse annuelle: {e}")
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
            logging.error(f"Erreur filtre synthèse: {e}")
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
            logging.error(f"Erreur employeurs: {e}")
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
            logging.error(f"Erreur synthèse mensuelle: {e}")
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
            logging.error(f"Erreur récupération synthèses: {e}")
            return []

    def calculate_h2f_stats_mensuel(self, user_id: int, employeur: str, id_contrat: int, 
                                    annee: int, mois: int, seuil_h2f_minutes: int = 18 * 60) -> Dict:
        """
        Calcule les statistiques sur h2f pour un mois donné.
        """
        seuil_h2f_minutes = int(round(seuil_h2f_minutes))

        jours_mois = self.heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, mois=mois)
        count = 0
        for jour in jours_mois:
            h2f_minutes = self.heure_model.time_to_minutes(jour.get('h2f'))
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

    def prepare_svg_data_horaire_mois(self, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int, largeur_svg: int = 1000, hauteur_svg: int = 400) -> Dict:
        """
        Prépare les données pour un graphique SVG des horaires sur un mois.
        Axe X: Jours du mois (1, 2, 3, ..., 31)
        Axe Y: Heures (6h en haut, 22h en bas)
        """

        jours_mois = self.heure_model.get_h1d_h2f_for_period(user_id, employeur, id_contrat, annee, mois=mois)

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
                current_app.logger.warning(f"Type de date inattendu : {type(date_value)}")
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

    def prepare_svg_data_h2f_annuel(self, user_id: int, employeur: str, id_contrat: int, annee: int, seuil_h2f_minutes: int = 18 * 60, largeur_svg: int = 900, hauteur_svg: int = 400) -> Dict:
    # Récupérer les stats hebdomadaires
        stats = self.synthese_hebdo_model.calculate_h2f_stats(user_id, employeur, id_contrat, annee, seuil_h2f_minutes)
        
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


    def calculate_h2f_stats_weekly_for_month(self, user_id: int, employeur: str, id_contrat: int, annee: int, mois: int, seuil_h2f_minutes: int) -> Dict:
        # Bornes du mois
        if mois == 12:
            fin_mois = date(annee + 1, 1, 1) - timedelta(days=1)
        else:
            fin_mois = date(annee, mois + 1, 1) - timedelta(days=1)
        debut_mois = date(annee, mois, 1)

        # Récupérer TOUS les jours du mois
        tous_les_jours = self.heure_model.get_h1d_h2f_for_period(
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
                h2f_min = self.heure_model.time_to_minutes(jour.get('h2f'))
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

class Employe:
    def __init__(self, db):
        self.db
        self.heure_model = HeureTravail(self.db)
        self.salaire_model = Salaire(self.db)
        self.synthese_hebdo_model = SyntheseHebdomadaire(self.db)
        self.synthese_mensuelle_model = SyntheseMensuelle(self.db)
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
        required = ('user_i', 'nom', 'prenom', 'genre', 'date_de_naissance')
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
            logging.error(f"Erreur lors de création fr l'employe: {e}")
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
                cursor.execute(query, user_id)
                return cursor.fetchall()
        except Exception as e:
            current_app.logger.error(f'Erreur de récupération des employées pour user_id {user_id}: {e}')
    
    def get_by_id(self, employe_id: int, user_id : int) -> Optional[Dict]:
        """ 
        récupère un employe avec vérification de sécurité"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT * FROM employes
                WHERE id = %s AND user_id = %s
                """
                cursor.execute(query, employe_id, user_id)
                return cursor.fetchone()
        except Exception as e:
            current_app.logger.error(f'Erreur de récupération employe ID {employe_id} de user_id {user_id}: {e}')
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
            current_app.logger.error(f'Erreur lors de la mise à jour employe {employe_id} pour {data}: {e}')
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
            current_app.logger.error(f'Erreur dans la suppresion employe {employe_id} de user {user_id}; {e}')
            return False
        
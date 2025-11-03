#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modèles de données pour la gestion bancaire
Classes pour manipuler les banques, comptes et sous-comptes
"""
from dbutils.pooled_db import PooledDB
import pymysql
from pymysql import Error
from decimal import Decimal
from datetime import datetime, date, timedelta
import calendar
import csv
import time
import math

from typing import List, Dict, Optional, Tuple
import decimal
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
            with self.db.get_cursor() as cursor:
                
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

                # Table ecritures_comptables
                create_ecritures_table_query = """
                CREATE TABLE IF NOT EXISTS ecritures_comptables (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    date_ecriture DATE NOT NULL,
                    compte_bancaire_id INT NOT NULL,
                    sous_compte_id INT,
                    categorie_id INT NOT NULL,
                    montant DECIMAL(15,2) NOT NULL,
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
                    h1d TIME,
                    h1f TIME,
                    h2d TIME,
                    h2f TIME,
                    total_h DECIMAL(5,2),
                    vacances BOOLEAN DEFAULT FALSE,
                    jour_semaine VARCHAR(10),
                    semaine_annee INT,
                    mois INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY unique_date_user (date, user_id),
                    FOREIGN KEY (user_id) REFERENCES utilisateurs(id)
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
            logging.error(f"Erreur lors de la récupération des périodes favorites: {e}")
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
            logging.error(f"Erreur lors de la création de la période favorite: {e}")
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
            logging.error(f"Erreur lors de la mise à jour de la période favorite: {e}")
            return False

    def delete(self, user_id: int, periode_id: int) -> bool:
        """Supprime une période favorite par son ID."""
        try:
            with self.db.get_cursor() as cursor:
                query = "DELETE FROM periode_favorite WHERE id = %s AND user_id = %s"
                cursor.execute(query, (periode_id, user_id))
                return cursor.rowcount > 0
        except Error as e:
            logging.error(f"Erreur lors de la suppression de la période favorite: {e}")
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
            logging.error(f"Erreur lors de la récupération de la période favorite: {e}")
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
            logging.error(f"Erreur lors de la récupération des banques: {e}")
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
            logging.error(f"Erreur lors de la récupération de la banque: {e}")
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
            logging.error(f"Erreur lors de la création de la banque: {e}")
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
            logging.error(f"Erreur lors de la mise à jour de la banque: {e}")
            return False
    
    def delete_banque(self, banque_id: int) -> bool:
        """Désactive (supprime logiquement) une banque par son ID."""
        try:
            with self.db.get_cursor() as cursor:
                query = "UPDATE banques SET actif = FALSE WHERE id = %s"
                cursor.execute(query, (banque_id,))
                return cursor.rowcount > 0 # Returns True if the row was found and updated
        except Error as e:
            logging.error(f"Erreur lors de la suppression de la banque: {e}")
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
                logging.info(f"models 710 - Comptes récupérés - comptes - pour l'utilisateur {user_id}: {len(comptes)}")
                return comptes
        except Error as e:
            logging.error(f"713 Erreur lors de la récupération des comptes: {e}")
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
            logging.error(f"Erreur lors de la récupération du compte: {e}")
            return None
    
    def create(self, data: Dict) -> bool:
        """Crée un nouveau compte principal"""
        try:
            # Correction de la syntaxe 'with self.db.get.cursor()'
            with self.db.get_cursor() as cursor:
                # Ces vérifications sont des requêtes SELECT, elles n'ont pas besoin d'être dans une transaction.
                cursor.execute("SELECT id FROM utilisateurs WHERE id = %s", (data['utilisateur_id'],))
                if not cursor.fetchone():
                    logging.error(f"746 Erreur: Utilisateur avec ID {data['utilisateur_id']} n'existe pas")
                    return False
                
                cursor.execute("SELECT id FROM banques WHERE id = %s", (data['banque_id'],))
                if not cursor.fetchone():
                    logging.error(f"Erreur: Banque avec ID {data['banque_id']} n'existe pas")
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
            logging.error(f"769 Erreur lors de la création du compte: {e}")
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
            logging.error(f"781 Erreur lors de la mise à jour du solde: {e}")
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
            logging.error(f"808 Erreur lors du calcul du solde total pour le compte {compte_id}: {e}")
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
            logging.error(f"839Erreur lors du calcul du solde avec écritures: {e}")
            return Decimal('0')
    
    @classmethod
    def get_all_accounts(cls, db):
        # Cette méthode de classe n'est pas cohérente avec les autres méthodes d'instance.
        # Il est préférable de la rendre une méthode d'instance si possible.
        # Si vous devez la garder en l'état, voici la correction.
        comptes = []
        try:
            # Correction de l'utilisation de db
            with db.get_cursor() as cursor:
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
            logging.error(f"Erreur SQL: {e}")
            return []

class SousCompte:
    """Modèle pour les sous-comptes d'épargne"""
    
    def __init__(self, db):
        self.db = db
    
    def get_by_compte_principal_id(self, compte_principal_id: int) -> List[Dict]:
        """Récupère tous les sous-comptes d'un compte principal"""
        logging.debug(f"Récupération des sous-comptes pour le compte principal {compte_principal_id}")
        
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
                
                logging.debug(f"Résultat de la requête: {result}")
                return result
            
        except Error as e:
            logging.error(f"Erreur lors de la récupération des sous-comptes: {e}")
            return []
    
    def get_all_sous_comptes_by_user_id(self, user_id) -> List:
        """Récupère tous les sous-comptes d'un utilisateur"""
        logging.debug(f"Récupération de tous les sous-comptes pour l'utilisateur {user_id}")
        
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
            logging.error(f"Erreur lors de la récupération des sous-comptes: {e}")
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
                logging.debug(f'voici le resultat de get_by_id {sous_compte}')
                return sous_compte
        except Error as e:
            logging.error(f"Erreur lors de la récupération du sous-compte: {e}")
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
            logging.error(f"Erreur lors de la création du sous-compte: {e}")
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
            logging.error(f"Erreur lors de la mise à jour du sous-compte: {e}")
            return False
    
    def delete(self, sous_compte_id: int) -> bool:
        """Supprime un sous-compte (soft delete)"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier si le sous-compte a un solde
                cursor.execute("SELECT solde FROM sous_comptes WHERE id = %s", (sous_compte_id,))
                result = cursor.fetchone()
                
                if result and Decimal(str(result['solde'])) > 0:
                    logging.warning(f"Impossible de supprimer le sous-compte {sous_compte_id} car son solde n'est pas nul.")
                    return False
                
                # Soft delete
                cursor.execute("UPDATE sous_comptes SET actif = FALSE WHERE id = %s", (sous_compte_id,))
                return cursor.rowcount > 0
        except Error as e:
            logging.error(f"Erreur lors de la suppression du sous-compte: {e}")
            return False
    
    def update_solde(self, sous_compte_id: int, nouveau_solde: float) -> bool:
        """Met à jour le solde d'un sous-compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = "UPDATE sous_comptes SET solde = %s WHERE id = %s"
                cursor.execute(query, (nouveau_solde, sous_compte_id))
                return cursor.rowcount > 0
        except Error as e:
            logging.error(f"Erreur lors de la mise à jour du solde: {e}")
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
            logging.error(f"Erreur lors de la récupération du solde : {e}")
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
        logging.debug(f"Vérification du solde pour {compte_type} ID {compte_id}")
        
        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    cursor.execute("SELECT solde FROM comptes_principaux WHERE id = %s", (compte_id,))
                elif compte_type == 'sous_compte':
                    cursor.execute("SELECT solde FROM sous_comptes WHERE id = %s", (compte_id,))
                else:
                    logging.error(f"Type de compte invalide: {compte_type}")
                    return False, Decimal('0')
                
                result = cursor.fetchone()
                if not result or 'solde' not in result:
                    logging.warning(f"Aucun solde trouvé pour {compte_type} ID {compte_id}")
                    return False, Decimal('0')
                    
                solde_actuel = Decimal(str(result['solde']))
                return solde_actuel >= montant, solde_actuel
        except Error as e:
            logging.error(f"Erreur validation solde: {e}")
            return False, Decimal('0')

    def _get_previous_transaction(self, compte_type: str, compte_id: int, date_transaction: datetime) -> Optional[Dict]:
        """Trouve la transaction précédente la plus proche pour un compte donné"""
        logging.debug(f"Recherche de la transaction précédente pour {compte_type} ID {compte_id}")

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
            logging.error(f"Erreur recherche transaction précédente: {e}")
            return None

    def _get_solde_initial(self, compte_type: str, compte_id: int) -> Decimal:
        """Récupère le solde initial d'un compte"""
        logging.debug(f"Récupération du solde initial pour {compte_type} ID {compte_id}")
        
        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    cursor.execute("SELECT solde_initial FROM comptes_principaux WHERE id = %s", (compte_id,))
                else:
                    cursor.execute("SELECT solde_initial FROM sous_comptes WHERE id = %s", (compte_id,))
                
                result = cursor.fetchone()
                return Decimal(str(result['solde_initial'])) if result and 'solde_initial' in result else Decimal('0')
        except Error as e:
            logging.error(f"Erreur récupération solde initial: {e}")
            return Decimal('0')

    def _update_subsequent_transactions(self, cursor, compte_type: str, compte_id: int, 
                                      date_transaction: datetime, transaction_id: int, 
                                      solde_apres_insere: Decimal) -> Optional[Decimal]:
        """Met à jour les soldes des transactions suivantes après une insertion ou modification"""
        logging.debug("Mise à jour des transactions suivantes")
        
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
        logging.info(f"Insertion de la transaction de type '{type_transaction}'")
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
            logging.error(f"Erreur insertion transaction: {e}")
            return False, f"Erreur lors de l'insertion: {str(e)}", None

    def _recalculer_soldes_apres_date(self, compte_type: str, compte_id: int, date_modification: datetime) -> bool:
        """Recalcule tous les soldes_apres des transactions postérieures à une date"""
        logging.info("Recalcul des soldes après modification")
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
            logging.error(f"Erreur recalcul soldes: {e}")
            return False

    def _recalculer_soldes_apres_date_with_cursor(self, cursor, compte_type: str, compte_id: int, date_modification: datetime) -> bool:
        """Recalcule tous les soldes_apres des transactions postérieures à une date — version avec curseur existant"""
        logging.info("Recalcul des soldes après modification")
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
            logging.error(f"Erreur recalcul soldes: {e}")
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
            logging.error(f"Erreur récupération solde historique: {e}")
            return []

    def _mettre_a_jour_solde(self, compte_type: str, compte_id: int, nouveau_solde: Decimal) -> bool:
        """Met à jour le solde d'un compte"""
        logging.info(f"Mise à jour solde {compte_type} ID {compte_id} -> {nouveau_solde}")
        try:
            with self.db.get_cursor() as cursor:
                if compte_type == 'compte_principal':
                    query = "UPDATE comptes_principaux SET solde = %s WHERE id = %s"
                else:
                    query = "UPDATE sous_comptes SET solde = %s WHERE id = %s"
                cursor.execute(query, (float(nouveau_solde), compte_id))
                return cursor.rowcount > 0
        except Error as e:
            logging.error(f"Erreur mise à jour solde: {e}")
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
                        logging.info("Recalcul des soldes réussi de la transaction après modification")
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
                                logging.info("Recalcul des soldes réussi de l'autre transaction du transfert après modification")  
                return True, "Transaction modifiée avec succès"

        except Exception as e:
            logging.error(f"Erreur modification transaction: {e}")
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
                    logging.info(f'Transaction {transaction_id} non trouvée pour suppression')
                if transaction['owner_user_id'] != user_id:
                    logging.info(f'Utilisateur {user_id} non autorisé à supprimer cette transaction')
                    return False, "Non autorisé à supprimer cette transaction"

                type_tx = transaction['type_transaction']
                compte_type = 'compte_principal' if transaction['compte_principal_id'] else 'sous_compte'
                compte_id = transaction['compte_principal_id'] or transaction['sous_compte_id']
                date_transaction = transaction['date_transaction']

                # === CAS SPÉCIAL : TRANSFERT INTERNE (entrant/sortant) ===
                if type_tx in ['transfert_entrant', 'transfert_sortant']:
                    reference_transfert = transaction.get('reference_transfert')
                    if not reference_transfert:
                        logging.error(f"Transfert corrompu : référence manquante pour la transaction {transaction_id}") 
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
                    logging.info(f"Demande de suppression de la Transaction {transaction_id} supprimée avec succès")
                    cursor.execute("SELECT * FROM transactions WHERE id = %s", (transaction_id,))
                    logging.info(f"Vérification post-suppression: {cursor.fetchone()} (devrait être None)")
                    # Recalculer les soldes à partir de la date de la transaction
                    success = self._recalculer_soldes_apres_date_with_cursor(
                        cursor, compte_type, compte_id, date_transaction
                    )
                    logging.info(f"Recalcul des soldes après suppression de la transaction {transaction_id} du compte {compte_id} en date du {date_transaction} {'réussi' if success else 'échoué'}")
                    if not success:
                        raise Exception("Erreur lors du recalcul des soldes")

                    return True, "Transaction supprimée avec succès"

        except Exception as e:
            logging.error(f"Erreur lors de la suppression de la transaction {transaction_id}: {e}", exc_info=True)
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
                logging.info(f"🔧 Réparation des soldes pour {compte_type} ID {compte_id}. Solde initial: {solde_initial}")
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
                    logging.info(f"  - Transaction ID {tx['id']} ({tx['type_transaction']} {montant} le {tx['date_transaction']}): solde_apres mis à jour à {solde_courant}")

                # Mettre à jour le solde final du compte
                if not self._mettre_a_jour_solde_with_cursor(cursor, compte_type, compte_id, solde_courant):
                    logging.error(f"Échec de la mise à jour du solde {solde_courant} du compte {compte_id} de type {compte_type}après réparation")
                    raise Exception("Échec de la mise à jour du solde du compte")
                
                logging.info(f"✅ Soldes du {compte_type} ID {compte_id} réparés avec succès. Nouveau solde: {solde_courant}")
                return True, "Soldes réparés avec succès"

        except Exception as e:
            logging.error(f"Erreur lors de la réparation des soldes: {e}")
            return False, f"Erreur: {str(e)}"
    
    def _verifier_appartenance_compte(self, compte_type: str, compte_id: int, user_id: int) -> bool:
        """Vérifie que le compte appartient à l'utilisateur"""
        logging.debug(f"Vérification appartenance: {compte_type} ID {compte_id} pour user {user_id}")
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
                    logging.error("Type de compte invalide")
                    return False
                
                result = cursor.fetchone()
                appartenance = result and result['utilisateur_id'] == user_id
                logging.debug(f"Résultat vérification appartenance: {appartenance}")
                return appartenance
        except Error as e:
            logging.error(f"Erreur vérification appartenance: {e}")
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
            logging.error(f"Erreur récupération transactions par compte: {e}")
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
                -- Jointures pour les comptes principaux
                LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                LEFT JOIN comptes_principaux cp_dest ON t.compte_destination_id = cp_dest.id
                -- Jointures pour les sous-comptes
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                LEFT JOIN sous_comptes sc_dest ON t.sous_compte_destination_id = sc_dest.id
                -- Filtrer par utilisateur (via compte principal source ou destination)
                WHERE (
                    (cp.utilisateur_id = %(user_id)s) OR
                    (sc.compte_principal_id IN (
                        SELECT id FROM comptes_principaux WHERE utilisateur_id = %(user_id)s
                    )) OR
                    (cp_dest.utilisateur_id = %(user_id)s) OR
                    (sc_dest.compte_principal_id IN (
                        SELECT id FROM comptes_principaux WHERE utilisateur_id = %(user_id)s
                    ))
                )
                """

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
            logging.error(f"Erreur dans get_all_user_transactions: {e}", exc_info=True)
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
                success, message, _ = self._inserer_transaction_with_cursor(
                    cursor, compte_type, compte_id, 'depot', montant, 
                    description, user_id, date_transaction, False
                )
                return success, message
        except Exception as e:
            logging.error(f"Erreur création dépôt: {e}")
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
            logging.error(f"Erreur création retrait: {e}")
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
            logging.error(f"Erreur lors de la validation du solde: {e}")
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
        logging.error(f"Récupération solde pour {compte_type} ID {compte_id}")
        
        if compte_type == 'compte_principal':
            query = "SELECT solde FROM comptes_principaux WHERE id = %s"
        else: # Supposant que le seul autre type est 'sous_compte'
            query = "SELECT solde FROM sous_comptes WHERE id = %s"
        
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(query, (compte_id,))
                result = cursor.fetchone()
                solde = Decimal(result['solde']) if result  and 'solde' in result else Decimal('0')
                logging.error(f"Solde trouvé: {solde}")
                return solde
        except Exception as e:
            logging.error(f"Erreur lors de la récupération du solde: {e}")
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
            logging.error(f"Erreur lors de la vérification de l'appartenance du compte: {e}")
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
            logging.error(f"Erreur lors de la récupération du solde : {e}", exc_info=True)
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
                        date_transaction: datetime, validate_balance: bool = True, reference_transfert: str = None) -> Tuple[bool, str, Optional[int]]:
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
            # Insérer la transaction
            if compte_type == 'compte_principal':
                query = """
                INSERT INTO transactions 
                (compte_principal_id, type_transaction, montant, description, utilisateur_id, date_transaction, solde_apres, reference_transfert)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (compte_id, type_transaction, montant, 
                                    description, user_id, date_transaction, solde_apres, reference_transfert))
                #cursor.execute(query, (compte_id, type_transaction, float(montant), description, user_id, date_transaction, float(solde_apres), reference_transfert))

            else:
                query = """
                INSERT INTO transactions 
                (sous_compte_id, type_transaction, montant, description, utilisateur_id, date_transaction, solde_apres, reference_transfert)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, (compte_id, type_transaction, montant, 
                                    description, user_id, date_transaction, solde_apres, reference_transfert))
    #cursor.execute(query, (compte_id, type_transaction, float(montant), description, user_id, date_transaction, float(solde_apres), reference_transfert))

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
            logging.error(f"Erreur lors de l'insertion de la transaction: {e}", exc_info=True)
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
            logging.error(f"Erreur lors de la recherche de la transaction précédente: {e}")
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
            logging.error(f"Erreur lors de la récupération du solde initial: {e}")
            return Decimal('0')

    def _mettre_a_jour_solde_with_cursor(self, cursor, compte_type: str, compte_id: int, nouveau_solde: Decimal) -> bool:
        """
        Met à jour le solde d'un compte en utilisant un curseur existant.
        """
        try:
            logging.info(f"➡️ Mise à jour solde: compte_type={compte_type}, compte_id={compte_id}, solde={nouveau_solde} (type={type(nouveau_solde)})")
        
            if compte_type == 'compte_principal':
                query = "UPDATE comptes_principaux SET solde = %s WHERE id = %s"
            else:
                query = "UPDATE sous_comptes SET solde = %s WHERE id = %s"
            
            cursor.execute(query, (nouveau_solde, compte_id))#cursor.execute(query, (float(nouveau_solde), compte_id))
            if cursor.rowcount > 0:
                logging.info(f"✅ Nombre de lignes mises à jour : {cursor.rowcount}")
            return True  
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour du solde: {e}")
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
                logging.warning(f"Type de transaction non reconnu: {type_transaction_val}")
                continue
            logging.info(f"Solde final à enregistrer pour {transaction['id']}: {solde_courant} (type: {type(solde_courant)})")
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
        logging.info(f"=== DÉBUT TRANSFERT INTERNE ===")
        logging.info(f"Source: {source_type} ID {source_id}")
        logging.info(f"Destination: {dest_type} ID {dest_id}")
        logging.info(f"Utilisateur: {user_id}, Montant: {montant}")
        
        # Validations initiales
        if montant <= 0:
            logging.warning("❌ Échec: Le montant doit être positif")
            return False, "Le montant doit être positif"
        
        if source_type == dest_type and source_id == dest_id:
            logging.warning("❌ Échec: Les comptes source et destination doivent être différents")
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
                logging.info(f"✅ Transfert interne réussi : débit={debit_tx_id}, crédit={credit_tx_id}")
                
                # Le commit est automatique à la sortie du bloc 'with'
                return True, "Transfert interne effectué avec succès"
                    
        except Exception as e:
            logging.error(f"❌ Erreur lors du transfert interne: {e}", exc_info=True)
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
            logging.error(f"Erreur transfert compte → sous-compte: {e}")
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
            logging.error(f"Erreur transfert sous-compte → compte: {e}")
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
            logging.error(f"Erreur transfert externe: {e}")
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
            logging.error(f"Erreur récupération historique: {e}")
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
            logging.error(f"Erreur récupération statistiques: {e}")
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
            logging.error(f"Erreur récupération transferts externes: {e}")
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
            logging.error(f"Erreur annulation transfert externe: {e}")
            return False, f"Erreur lors de l'annulation: {str(e)}"
    
    def get_evolution_soldes_quotidiens_compte(self, compte_id: int, user_id: int, date_debut: str = None, date_fin: str = None) -> List[Dict]:

        """Récupère l'évolution quotidienne des soldes d'un compte principal"""
        try:
            with self.db.get_cursor() as cursor:
                # Vérifier l'appartenance
                cursor.execute("SELECT id, solde_initial FROM comptes_principaux WHERE id = %s AND utilisateur_id = %s", (compte_id, user_id))
                row = cursor.fetchone()
                row_id = row['id']
                logging.info(f"Vérification appartenance compte {compte_id} à user {user_id}: {'trouvé' if row else 'non trouvé'}: row_id {row['id'] if row else 'N/A'} / solde_initial {row['solde_initial'] if row else 'N/A'}    ")
                if row and row_id == user_id:
                    solde_initial = Decimal(str(row['solde_initial'] or '0.00'))
                    logging.info(f"Vérification appartenance compte {compte_id} à user {user_id}: {'trouvé' if row else 'non trouvé'}: {row}")
                if not row:
                    return []
                logging.info(f'Vérification des formats de dates : date_debut={date_debut} (type={type(date_debut)}) / date_fin={date_fin} (type={type(date_fin)})  ')
                debut_dt = datetime.strptime(date_debut, '%Y-%m-%d')
                logging.info(f"Date début: {debut_dt}")
                fin_dt = datetime.strptime(date_fin, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
                logging.info(f"Date fin: {fin_dt}")
                current = debut_dt
                dates = []
                while current <= fin_dt:
                    dates.append(current)
                    current += timedelta(days=1)
                #query = """
                #SELECT 
                #    DATE(date_transaction) as date,
                #    solde_apres
                #FROM transactions
                #WHERE compte_principal_id = %s
                #AND date_transaction BETWEEN %s AND %s
                #AND id IN (
                #    SELECT MAX(id)
                #    FROM transactions
                #    WHERE compte_principal_id = %s
                #    AND date_transaction BETWEEN %s AND %s
                #    GROUP BY DATE(date_transaction)
                #)
                #ORDER BY date
                #"""
                query = """
                SELECT date, solde_apres
                    FROM (
                        SELECT 
                            DATE(date_transaction) as date,
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
                    ORDER BY date;
                """
                cursor.execute(query, (compte_id, date_debut, date_fin))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Erreur récupération évolution soldes compte: {e}")
            return []

    def get_evolution_soldes_quotidiens_sous_compte(self, sous_compte_id: int, user_id: int, nb_jours: int = 30) -> List[Dict]:
        """Récupère l'évolution quotidienne des soldes d'un sous-compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT 
                    DATE(date_transaction) as date,
                    solde_apres
                FROM transactions
                WHERE sous_compte_id = %s
                AND date_transaction >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                AND id IN (
                    SELECT MAX(id)
                    FROM transactions
                    WHERE sous_compte_id = %s
                    AND date_transaction >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                    GROUP BY DATE(date_transaction)
                )
                ORDER BY date
                """
                cursor.execute(query, (sous_compte_id, nb_jours, sous_compte_id, nb_jours))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Erreur récupération évolution soldes sous-compte: {e}")
            return []

    def get_transaction_by_id(self, transaction_id: int) -> Optional[Dict]:
        """Récupère une transaction par son ID avec les infos de propriété"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT t.*, 
                    COALESCE(cp.utilisateur_id, (
                        SELECT cp2.utilisateur_id 
                        FROM sous_comptes sc 
                        JOIN comptes_principaux cp2 ON sc.compte_principal_id = cp2.id 
                        WHERE sc.id = t.sous_compte_id
                    )) as owner_user_id,
                    cp.nom_compte as compte_nom,
                    sc.nom_sous_compte as sous_compte_nom
                FROM transactions t
                LEFT JOIN comptes_principaux cp ON t.compte_principal_id = cp.id
                LEFT JOIN sous_comptes sc ON t.sous_compte_id = sc.id
                WHERE t.id = %s
                """
                cursor.execute(query, (transaction_id,))
                return cursor.fetchone()
        except Exception as e:
            logging.error(f"Erreur récupération transaction: {e}")
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
            logging.error(f"Erreur récupération solde courant: {e}")
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
            logging.error(f"Erreur calcul solde total: {e}")
            return Decimal('0')
        
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
            logging.error(f"Erreur lors du calcul des statistiques: {e}")
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
            logging.error(f"Erreur lors du calcul de la répartition par banque: {e}")
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
            logging.error(f"Erreur lors du calcul de l'évolution: {e}")
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
            logging.error(f"Erreur lors du calcul de l'évolution quotidienne: {e}")
            return {'comptes_principaux': [], 'sous_comptes': [], 'total': []}
    def preparer_svg_tresorie(self, user_id: int, compte_id: int, date_debut: date, date_fin : date)
        
class PlanComptable:
    """Modèle pour gérer le plan comptable"""
    
    def __init__(self, db):
        self.db = db
    
    def get_all_categories(self) -> List[Dict]:
        """Récupère toutes les catégories comptables"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                SELECT id, numero, nom, parent_id, type_compte, compte_systeme, compte_associe, type_tva, actif, created_at, updated_at 
                FROM categories_comptables 
                ORDER BY numero
                """
                cursor.execute(query)
                categories = cursor.fetchall()
            return categories
        except Error as e:
            logging.error(f"Erreur lors de la récupération des catégories comptables: {e}")
            return []
    
    def get_by_id(self, categorie_id: int) -> Optional[Dict]:
        """Récupère une catégorie par son ID"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM categories_comptables WHERE id = %s"
                cursor.execute(query, (categorie_id,))
                categorie = cursor.fetchone()
            return categorie
        except Error as e:
            logging.error(f"Erreur lors de la récupération de la catégorie comptable: {e}")
            return None
    
    def get_by_numero(self, numero: str) -> Optional[Dict]:
        """Récupère une catégorie par son numéro"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM categories_comptables WHERE numero = %s"
                cursor.execute(query, (numero,))
                categorie = cursor.fetchone()
            return categorie
        except Error as e:
            logging.error(f"Erreur lors de la récupération de la catégorie comptable: {e}")
            return None
            
    def get_by_type(self, type_compte: str) -> List[Dict]:
        """Récupère les catégories par type de compte"""
        try:
            with self.db.get_cursor() as cursor:
                query = "SELECT * FROM categories_comptables WHERE type_compte = %s ORDER BY numero"
                cursor.execute(query, (type_compte,))
                categories = cursor.fetchall()
            return categories
        except Error as e:
            logging.error(f"Erreur lors de la récupération des catégories comptables: {e}")
            return []
    
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
            logging.error(f"Erreur lors de la création de la catégorie comptable: {e}")
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
            logging.error(f"Erreur lors de la mise à jour de la catégorie comptable: {e}")
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
            logging.error(f"Erreur lors de la suppression de la catégorie comptable: {e}")
            return False

class EcritureComptable:
    """Modèle pour gérer les écritures comptables"""
    
    def __init__(self, db):
        self.db = db
    
    def create(self, data: Dict) -> bool:
        """Crée une nouvelle écriture comptable"""
        try:
            with self.db.get_cursor() as cursor:
                query = """
                INSERT INTO ecritures_comptables 
                (date_ecriture, compte_bancaire_id, categorie_id, montant, devise, 
                description, reference, type_ecriture, tva_taux, tva_montant, 
                utilisateur_id, justificatif_url, statut, id_contact)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                values = (
                    data['date_ecriture'],
                    data['compte_bancaire_id'],
                    data['categorie_id'],
                    data['montant'],
                    data.get('devise', 'CHF'),
                    data.get('description', ''),
                    data.get('reference', ''),
                    data['type_ecriture'],  # 'depense' ou 'recette'
                    data.get('tva_taux'),
                    data.get('tva_montant'),
                    data['utilisateur_id'],
                    data.get('justificatif_url'),
                    data.get('statut', 'pending'),  # 'pending', 'validée', 'rejetée'
                    data.get('id_contact')  # Ajout du id_contact à la fin
                )
                cursor.execute(query, values)
                # Récupérer l'ID de la dernière insertion
                self.last_insert_id = cursor.lastrowid
            return True
        except Error as e:
            logging.error(f"Erreur lors de la création de l'écriture comptable: {e}")
            return False
    
    def update(self, ecriture_id: int, data: Dict) -> bool:
        try:
            with self.db.get_cursor() as cursor:
                query = """
                UPDATE ecritures_comptables 
                SET date_ecriture = %s, compte_bancaire_id = %s, categorie_id = %s, 
                    montant = %s, devise = %s, description = %s, id_contact = %s, reference = %s, 
                    type_ecriture = %s, tva_taux = %s, tva_montant = %s, 
                    justificatif_url = %s, statut = %s
                WHERE id = %s AND utilisateur_id = %s
                """
                values = (
                    data['date_ecriture'],
                    data['compte_bancaire_id'],
                    data['categorie_id'],
                    data['montant'],
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
        except Error as e:
            logging.error(f"Erreur lors de la mise à jour de l'écriture comptable: {e}")
            return False

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
            logging.error(f"Erreur lors de la récupération de l'écriture comptable: {e}")
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
            logging.error(f"Erreur lors de la récupération des écritures: {e}")
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
            logging.error(f"Erreur lors de la récupération des écritures par catégorie: {e}")
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
                    SUM(CASE WHEN e.type_ecriture = 'recette' AND e.statut = %s THEN e.montant ELSE 0 END) as total_recettes,
                    COUNT(e.id) as nb_ecritures
                FROM categories_comptables c
                LEFT JOIN ecritures_comptables e ON c.id = e.categorie_id AND e.utilisateur_id = %s
                """
                params = [statut, statut, user_id]
                
                if date_from:
                    query += " AND e.date_ecriture >= %s"
                    params.append(date_from)
                if date_to:
                    query += " AND e.date_ecriture <= %s"
                    params.append(date_to)
                
                query += """
                WHERE c.actif = TRUE
                GROUP BY c.id, c.numero, c.nom, c.type_compte
                ORDER BY c.numero
                """
                
                cursor.execute(query, tuple(params))
                stats = cursor.fetchall()
            return stats
        except Error as e:
            logging.error(f"Erreur lors de la récupération des statistiques par catégorie: {e}")
            return []
    
    def get_compte_de_resultat(self, user_id: int, date_from: str, date_to: str) -> Dict:
        """Génère les données pour le compte de résultat"""
        try:
            with self.db.get_cursor() as cursor:
                # 1. PRODUITS
                cursor.execute("""
                    SELECT 
                        c.numero, 
                        c.nom as categorie_nom,
                        c.id as categorie_id,
                        COUNT(e.id) as nombre_ecritures,
                        SUM(CASE WHEN e.type_ecriture = 'recette' AND e.statut = 'validée' THEN e.montant ELSE 0 END) as montant
                    FROM ecritures_comptables e
                    JOIN categories_comptables c ON e.categorie_id = c.id
                    WHERE e.utilisateur_id = %s 
                    AND e.date_ecriture BETWEEN %s AND %s
                    AND c.type_compte = 'Revenus'
                    GROUP BY c.id, c.numero, c.nom
                    ORDER BY c.numero
                """, (user_id, date_from, date_to))
                produits = cursor.fetchall()
                
                # 2. CHARGES
                cursor.execute("""
                    SELECT 
                        c.numero, 
                        c.nom as categorie_nom,
                        c.id as categorie_id,
                        COUNT(e.id) as nombre_ecritures,
                        SUM(CASE WHEN e.type_ecriture = 'depense' AND e.statut = 'validée' THEN e.montant ELSE 0 END) as montant
                    FROM ecritures_comptables e
                    JOIN categories_comptables c ON e.categorie_id = c.id
                    WHERE e.utilisateur_id = %s 
                    AND e.date_ecriture BETWEEN %s AND %s
                    AND c.type_compte = 'Charge'
                    GROUP BY c.id, c.numero, c.nom
                    ORDER BY c.numero
                """, (user_id, date_from, date_to))
                charges = cursor.fetchall()
                
            # 3. CALCUL DES TOTAUX
            total_produits = sum(p['montant'] or 0 for p in produits)
            total_charges = sum(c['montant'] or 0 for c in charges)
            resultat = total_produits - total_charges
            
            return {
                'produits': produits,
                'charges': charges,
                'total_produits': total_produits,
                'total_charges': total_charges,
                'resultat': resultat,
                'date_from': date_from,
                'date_to': date_to
            }
        except Exception as e:
            logging.error(f"Erreur génération compte de résultat: {e}")
            return {}
        
    def update_statut(self, ecriture_id: int, user_id: int, statut: str) -> bool:
        """Met à jour uniquement le statut d'une écriture"""
        try:
            with self.db.get_cursor() as cursor:
                query = "UPDATE ecritures_comptables SET statut = %s WHERE id = %s AND utilisateur_id = %s"
                cursor.execute(query, (statut, ecriture_id, user_id))
            return True
        except Error as e:
            logging.error(f"Erreur lors de la mise à jour du statut: {e}")
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
            logging.error(f"Erreur lors de la récupération des écritures par statut: {e}")
        
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
                    SUM(CASE WHEN type_ecriture = 'recette' THEN montant ELSE 0 END) as total_recettes,
                    AVG(CASE WHEN type_ecriture = 'depense' THEN montant ELSE NULL END) as moyenne_depenses,
                    AVG(CASE WHEN type_ecriture = 'recette' THEN montant ELSE NULL END) as moyenne_recettes
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
            logging.error(f"Erreur lors du calcul des statistiques par statut: {e}")
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
            logging.error(f"Erreur lors de la récupération des alertes: {e}")
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
            logging.error(f"Erreur lors du calcul des indicateurs de performance: {e}")
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
            logging.error(f"Erreur lors de la récupération des années disponibles : {e}")
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
            logging.error(f"Erreur lors de la récupération des écritures: {e}")
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
            logging.error(f"Erreur lors de la récupération des écritures par période: {e}")
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
            logging.error(f"Erreur lors de la récupération des écritures: {e}")  
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
                    SUM(CASE WHEN type_ecriture = 'recette' THEN montant ELSE 0 END) as total_recettes
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
            logging.error(f"Erreur lors de la récupération de la synthèse des statuts: {e}")
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
            logging.error(f"Erreur lors de la récupération des écritures par contact: {e}")
            return []

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
            # Utilisez un logger au lieu de logging.error pour un environnement de production
            logging.error(f"Erreur lors de la création du contact: {e}")
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
                current_app.logger.debug(f"[update] Query: {query} avec params: {values}")

                cursor.execute(query, values)
                # Le commit est géré par la classe DatabaseManager (autocommit)
                # ou via une transaction si vous l'avez configurée.
                return cursor.rowcount > 0 # Vérifie si une ligne a été modifiée
        except Error as e:
            logging.error(f"Erreur lors de la mise à jour du contact: {e}")
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
            logging.error(f"Erreur lors de la récupération des contacts: {e}")
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
            logging.error(f"Erreur lors de la récupération du contact: {e}")
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
            logging.error(f"Erreur lors de la suppression du contact: {e}")
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
            logging.error(f"Erreur lors de la récupération du dernier ID: {e}")
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
            logging.error(f"Erreur lors de la recherche de contacts: {e}")
            return []

class Rapport:
    def __init__(self, db):
        self.db = db
    
    def generate_rapport_mensuel(self, user_id: int, annee: int, mois: int, statut: str = 'validée') -> Dict:
        """Génère un rapport mensuel avec filtrage par statut"""
        date_debut = date(annee, mois, 1)
        date_fin = date(annee, mois + 1, 1) if mois < 12 else date(annee + 1, 1, 1)
        date_fin = date_fin - timedelta(days=1)
        
        # Utilisez EcritureComptable pour obtenir les données
        ecriture_comptable = EcritureComptable(self.db)
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
                    ORDER BY date_debut DESC
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
                query = "SELECT * FROM contrats WHERE user_id = %s ORDER BY date_debut DESC;"
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
                "SELECT * FROM heures_travail WHERE date = %s AND user_id = %s AND employeur = %s AND id_contrat = %s",
                (cleaned_data['date'], cleaned_data['user_id'], cleaned_data['employeur'], cleaned_data['id_contrat'])
            )
            existing = cursor.fetchone()
            
            # Préparer les valeurs avec fallback
            values = {
                'date': date_obj,
                'user_id': cleaned_data['user_id'],
                'employeur': cleaned_data['employeur'],
                'id_contrat': cleaned_data.get('id_contrat'),
                'vacances': cleaned_data.get('vacances', False)
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
            (date, user_id, employeur, id_contrat, h1d, h1f, h2d, h2f, total_h, vacances,
            jour_semaine, semaine_annee, mois)
            VALUES (%(date)s, %(user_id)s, %(employeur)s, %(id_contrat)s, %(h1d)s, %(h1f)s, %(h2d)s, %(h2f)s, 
                    %(total_h)s, %(vacances)s, %(jour_semaine)s, %(semaine_annee)s, %(mois)s)
            ON DUPLICATE KEY UPDATE
                h1d = COALESCE(VALUES(h1d), h1d),
                h1f = COALESCE(VALUES(h1f), h1f),
                h2d = COALESCE(VALUES(h2d), h2d),
                h2f = COALESCE(VALUES(h2f), h2f),
                total_h = VALUES(total_h),
                vacances = COALESCE(VALUES(vacances), vacances),
                jour_semaine = VALUES(jour_semaine),
                semaine_annee = VALUES(semaine_annee),
                mois = VALUES(mois)
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

        
class Salaire:
    def __init__(self, db, heure_travail_manager=None):
        self.db = db
        self.heure_travail_manager = heure_travail_manager
    def create(self, data: dict) -> bool:
        try:
            with self.db.get_cursor() as cursor:
                if not cursor:
                    return False
                
                query = """
                INSERT INTO salaires 
                (mois, annee, heures_reelles, salaire_horaire,
                salaire_calcule, salaire_net, salaire_verse, acompte_25, acompte_10,
                acompte_25_estime, acompte_10_estime, difference, difference_pourcent, user_id, employeur, id_contrat)
                VALUES (%s, %s, %s, %s, %s, %s,%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                """
                values = (
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
            if isinstance(salaire_horaire, decimal.Decimal):
                salaire_horaire = float(salaire_horaire)
            elif isinstance(salaire_horaire, str):
                salaire_horaire = float(salaire_horaire)
            
            # Calcul du salaire brut
            salaire_brut = round(heures_reelles * salaire_horaire, 2)
            
            # Récupération des taux depuis le contrat
            def get_taux(key, default=0.0):
                value = contrat.get(key, default)
                if isinstance(value, decimal.Decimal):
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
        if not self.heure_travail_manager:
            raise ValueError("HeureTravail manager non initialisé")
        
        heures = self.heure_travail_manager.get_heures_periode(
            user_id, employeur, id_contrat, annee, mois, 1, jour_estimation
        )
        # Protection contre les valeurs négatives ou None
        heures = max(0.0, heures or 0.0)
        return round(heures * salaire_horaire, 2)
    
    def calculer_acompte_10(self, user_id: int, annee: int, mois: int, salaire_horaire: float, employeur: str, id_contrat: int, jour_estimation: int = 15) -> float:
        if not self.heure_travail_manager:
            raise ValueError("HeureTravail manager non initialisé")

        heures_total = self.heure_travail_manager.get_total_heures_mois(user_id, employeur, id_contrat, annee, mois)
        heures_avant = self.heure_travail_manager.get_heures_periode(
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
    # Dans SyntheseHebdomadaire
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
class SyntheseMensuelle:
    def __init__(self, db):
        self.db = db
    # Dans la classe SyntheseMensuelle
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
    # Dans SyntheseMensuelle
    def get_by_user_and_filters(self, user_id: int, annee: int = None, mois: int = None, 
                            employeur: str = None, contrat_id: int = None) -> List[Dict]:
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
            logging.error(f"Erreur lors de la récupération des paramètres: {e}")
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
            logging.error(f"Erreur lors de la mise à jour des paramètres: {e}")
            return False


class ModelManager:
    def __init__(self, db):
        self.db = db
        self.banque_model = Banque(self.db)
        self.user_model = Utilisateur(self.db)
        self.periode_favorite_model = PeriodeFavorite(self.db)
        self.compte_model = ComptePrincipal(self.db)
        self.sous_compte_model = SousCompte(self.db)
        self.transaction_financiere_model = TransactionFinanciere(self.db)
        self.stats_model = StatistiquesBancaires(self.db)
        self.plan_comptable_model = PlanComptable(self.db)
        self.ecriture_comptable_model = EcritureComptable(self.db)
        self.contact_model = Contacts(self.db)
        self.heure_model = HeureTravail(self.db)
        self.salaire_model = Salaire(self.db, self.heure_model)
        self.synthese_hebdo_model = SyntheseHebdomadaire(self.db)
        self.synthese_mensuelle_model = SyntheseMensuelle(self.db)
        self.contrat_model = Contrat(self.db)
        self.parametre_utilisateur_model = ParametreUtilisateur(self.db)    
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
            logging.error(f"Erreur lors de la récupération de l'utilisateur : {e}")
            return None

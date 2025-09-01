#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration Flask pour l'application bancaire
Compatible développement local et production (Hostpoint)
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env
load_dotenv()

class Config:
    """Configuration de base"""

    # Clé secrète Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'votre-cle-secrete-super-secure-changez-moi'

    # Configuration MySQL via SQLAlchemy
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'root')
    DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
    DB_PORT = os.environ.get('DB_PORT', '8889')
    DB_NAME = os.environ.get('DB_NAME', 'banking2')

    # URI pour SQLAlchemy
    SQLALCHEMY_DATABASE_URI = (
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # Options SQLAlchemy
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Sessions
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)
    SESSION_COOKIE_SECURE = True  # HTTPS obligatoire en prod
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # Upload de fichiers (si nécessaire)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')

    # Pagination
    USERS_PER_PAGE = 20

    # Email (optionnel)
    MAIL_SERVER = 'mail.hostpoint.ch'
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')


class DevelopmentConfig(Config):
    """Configuration pour le développement"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False  # Pas besoin de HTTPS en local


class ProductionConfig(Config):
    """Configuration pour la production (Hostpoint)"""
    DEBUG = False


class TestingConfig(Config):
    """Configuration pour les tests"""
    TESTING = True
    DB_NAME = 'banking_test'
    SECRET_KEY = 'test-secret-key'


# Dictionnaire des configurations
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig
}


def get_config():
    """Retourne la configuration basée sur FLASK_ENV"""
    return config.get(os.environ.get('FLASK_ENV', 'default'))

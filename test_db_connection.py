import mysql.connector
from mysql.connector import Error

def test_db_connection():
    config = {
        'host': '127.0.0.1',     # Adresse IP à utiliser (localhost = parfois socket Unix)
        'port': 8889,            # Port par défaut MAMP MySQL
        'user': 'root',          # Ton utilisateur MySQL
        'password': 'root',      # Ton mot de passe MySQL
        'database': 'banking2',   # Ta base de données
        'charset': 'utf8mb4',
        'use_unicode': True,
        'autocommit': True
    }

    try:
        connection = mysql.connector.connect(**config)

        if connection.is_connected():
            print("Connexion réussie à MySQL via MAMP !")
            cursor = connection.cursor()
            cursor.execute("SELECT DATABASE();")
            db = cursor.fetchone()
            print(f"Base utilisée : {db[0]}")
            cursor.close()
        else:
            print("Échec de la connexion à la base de données.")

    except Error as e:
        print(f"Erreur lors de la connexion : {e}")

    finally:
        if 'connection' in locals() and connection.is_connected():
            connection.close()
            print("Connexion fermée.")

if __name__ == '__main__':
    test_db_connection()

from werkzeug.security import generate_password_hash
import mysql.connector

# Connexion à la base
conn = mysql.connector.connect(
    host='127.0.0.1',
    port=8889,
    user='root',
    password='root',  # ton mdp MAMP
    database='banking',
    charset='utf8mb4',
    use_unicode=True,
    autocommit=True
)
cursor = conn.cursor()

# Nouvel mot de passe à mettre (en clair)
nouveau_mdp = "1234"

# Générer le hash
hashed_password = generate_password_hash(nouveau_mdp)

# Mettre à jour l'utilisateur avec email donné
email = "jean.dupont@example.com"
sql = "UPDATE utilisateurs SET mot_de_passe = %s WHERE email = %s"
cursor.execute(sql, (hashed_password, email))
conn.commit()

print(f"Mot de passe hashé mis à jour pour {email}")

cursor.close()
conn.close()
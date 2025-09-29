import pymysql

conn = pymysql.connect(
    host='localhost',
    port=8889,
    user='root',
    password='root',
    database='banking2',
    charset='utf8mb4'
)
print("✅ Connexion réussie à MAMP !")
conn.close()
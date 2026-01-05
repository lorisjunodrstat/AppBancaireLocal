#!/bin/bash

set -e  # Arrête le script dès qu'une commande échoue

APP_NAME="cleo"
VENV_DIR="venv"
REQUIREMENTS="requirements.txt"

echo "🚀 Installation de $APP_NAME — Votre hub financier local, suisse et privé"

# 1. Vérifier Python et pip
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 n’est pas installé. Veuillez l’installer d’abord."
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 n’est pas installé. Installez-le via 'python3 -m ensurepip'."
    exit 1
fi

# 2. Créer l’environnement virtuel
echo "📦 Création de l’environnement virtuel dans '$VENV_DIR'..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# 3. Mettre à jour pip
echo "⬆️ Mise à jour de pip..."
pip install --upgrade pip

# 4. Installer les dépendances
if [ -f "$REQUIREMENTS" ]; then
    echo "📥 Installation des dépendances depuis $REQUIREMENTS..."
    pip install -r "$REQUIREMENTS"
else
    echo "⚠️ Aucun fichier $REQUIREMENTS trouvé. Installez manuellement Flask, PyMySQL, etc."
fi

# 5. Créer le dossier uploads
mkdir -p app/uploads/justificatifs

# 6. Initialiser la base de données (option SQLite pour simplicité)
if ! command -v mysql &> /dev/null; then
    echo "ℹ️ MySQL non détecté → configuration automatique avec SQLite (optionnel dans config.py)."
    # Tu peux adapter ton `config.py` pour basculer sur SQLite si pas de MySQL
else
    echo "✅ MySQL détecté. Assure-toi que la base de données est créée et accessible."
    echo "   → Modifie config.py avec tes identifiants."
fi

# 7. Créer un script de démarrage simple
cat > run.sh << EOF
#!/bin/bash
source venv/bin/activate
python app.py
EOF
chmod +x run.sh

echo "✅ Installation terminée !"

# 8. Demander si l’utilisateur veut installer Tailscale
read -p "Souhaitez-vous installer Tailscale pour un accès distant sécurisé ? (o/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Oo]$ ]]; then
    echo "🔗 Installation de Tailscale..."
    curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
    curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list
    sudo apt-get update
    sudo apt-get install tailscale -y
    echo "🔑 Connectez Tailscale :"
    echo "   sudo tailscale up"
    echo "👉 Votre IP Tailscale : \$(tailscale ip -4)"
else
    echo "ℹ️ Tailscale non installé. Vous accéderez à l’appli uniquement en local."
fi

echo
echo "▶️ Pour lancer l’application :"
echo "   ./run.sh"
echo
echo "🌐 Ouvrez dans votre navigateur : http://localhost:5000"
echo
echo "🔒 Vos données restent 100 % locales. Aucune information n’est envoyée dans le cloud."
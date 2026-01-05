🏠 CLEO – Mon Hub Financier Suisse

Une application 100 % locale, hors cloud, conçue pour les administratifs·ves suisses exigeants·es.
Gérez banque, comptabilité et salaire sans jamais quitter votre réseau.

🔒 Aucune donnée dans le cloud • 🇨🇭 Conforme au droit suisse • 🖥️ Auto-hébergement recommandé
🧩 Fonctionnalités clés

🏦 Banque & Transactions

Gérez vos comptes bancaires (PostFinance, UBS, Raiffeisen, etc.) avec précision :

✅ Comptes principaux + sous-comptes (épargne vacances, projet vélo…)
🔄 Transferts internes (compte ↔ sous-compte) et externes (IBAN/BIC)
📥/📤 Dépôts, retraits, historique complet avec solde recalculé à chaque opération
📊 Graphiques SVG natifs (flux quotidiens, répartition par type)
📤 Export PDF/Excel pour vos archives
⚖️ Comparaison de comptes ou réel vs simulé
📊 Comptabilité & Écritures

Une comptabilité rigoureuse et automatisée, conforme au plan comptable suisse :

📝 Création d’écritures comptables liées aux transactions
🤖 Automatisation intelligente : génération automatique d’écritures TVA (3.20%, 2.6%, etc.)
🗂️ Catégories avec catégories complémentaires (ex: "Dépense bureau" → "TVA déductible")
📑 Compte de résultat (Produits vs Charges) et Bilan (Actif/Passif)
📎 Justificatifs joints (PDF, images)
📤 Export vers fiscaliste via PDF ou Excel
💼 Salaire & Heures de Travail

Suivez et simulez votre rémunération avec une précision suisse :

🕘 Saisie manuelle ou import CSV : h1d → h1f, h2d → h2f
🔄 Deux modes : heures réelles (facturées) vs heures simulées (planifiées)
📈 Graphiques SVG : matin en haut, soir en bas, seuil configurable (ex: 18h)
💰 Calcul salarial avancé :
Cotisations AVS 5.30%, AC, 2e pilier
Indemnités (vacances, jours fériés, repas)
Acomptes du 10 et du 25
📊 Synthèses hebdo/mensuelles : comparaison réel vs simulé + moyennes mobiles
🛠️ Installation & Accès Distant (Tailscale)

Déployez en local et accédez depuis n’importe où, en toute sécurité.

1️⃣ Installer localement

Sur un Raspberry Pi, un NAS ou un mini-PC :

bash

1234
git clone https://github.com/votreuser/cleo.gitcd cleopip install -r requirements.txtpython app.py

Ouvrez http://localhost:5000 dans votre navigateur.
2️⃣ Accéder partout avec Tailscale

Installez Tailscale sur votre serveur local et vos appareils.
Connectez-les à votre compte Tailscale.
Accédez à votre hub via l’IP privée Tailscale :
http://100.x.y.z:5000
✅ Zéro ouverture de port
✅ Chiffrement de bout en bout
✅ Vous êtes chez vous, même en vacances

🚀 Tester la démo

Clonez le dépôt
Créez un compte utilisateur
Importez vos premières transactions ou simulez un mois
📦 L’application inclut sa base de données, ses modèles métier et ses graphiques SVG — aucun JavaScript requis.
🛡️ Philosophie

Vos données vous appartiennent — jamais envoyées à un tiers.
Zéro dépendance cloud — fonctionne entièrement en local.
Conçu pour la Suisse — AVS, TVA, plan comptable, CHF.
Open, privé, et maîtrisable — idéal pour un home lab.
Parce que votre vie financière mérite mieux qu’un SaaS opaque.
C’est votre argent. C’est votre logiciel.

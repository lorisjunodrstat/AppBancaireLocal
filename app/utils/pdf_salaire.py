import io
import os
from flask import current_app
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

def generer_pdf_salaire(
    entreprise: dict,
    employe_info: dict,
    mois: int,
    annee: int,
    heures_reelles: float,
    result: dict,
    details: dict
) -> io.BytesIO:
    """
    Génère un PDF de fiche de salaire.
    Retourne un objet BytesIO prêt à être envoyé.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=14,
        alignment=1
    )

    # Logo
    if entreprise and entreprise.get('logo_path'):
        logo_full = os.path.join(current_app.static_folder, entreprise['logo_path'])
        if os.path.exists(logo_full):
            img = Image(logo_full, width=1.5*inch, height=1.5*inch)
            elements.append(img)
            elements.append(Spacer(1, 12))

    # En-tête entreprise
    nom_entreprise = entreprise.get('nom', 'Votre entreprise') if entreprise else 'Votre entreprise'
    elements.append(Paragraph(nom_entreprise, title_style))
    if entreprise:
        if entreprise.get('rue'):
            elements.append(Paragraph(entreprise['rue'], styles['Normal']))
        if entreprise.get('code_postal') or entreprise.get('commune'):
            cp_commune = f"{entreprise.get('code_postal', '')} {entreprise.get('commune', '')}".strip()
            if cp_commune:
                elements.append(Paragraph(cp_commune, styles['Normal']))

    elements.append(Spacer(1, 24))

    # Titre
    mois_noms = ["", "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
                 "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    elements.append(Paragraph(f"Fiche de salaire – {mois_noms[mois]} {annee}", styles['Heading1']))

    # Info employé (si fourni)
    if employe_info:
        nom_employe = f"{employe_info.get('prenom', '')} {employe_info.get('nom', '')}".strip()
        if nom_employe:
            elements.append(Paragraph(f"Employé : {nom_employe}", styles['Normal']))
    if employe_info and employe_info.get('employeur'):
        elements.append(Paragraph(f"Employeur : {employe_info['employeur']}", styles['Normal']))

    elements.append(Spacer(1, 18))

    # Tableau
    data = [
        ["Élément", "Montant (CHF)"],
        ["Heures réelles", f"{heures_reelles:.2f} h"],
        ["Salaire brut", f"{details.get('salaire_brut', 0):.2f}"],
        ["+ Indemnités", f"+{details.get('total_indemnites', 0):.2f}"],
        ["- Cotisations", f"-{details.get('total_cotisations', 0):.2f}"],
        ["= Salaire net", f"{result.get('salaire_net', 0):.2f}"],
    ]
    table = Table(data, colWidths=[3*inch, 1.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)
    elements.append(Spacer(1, 24))

    # Acomptes (logique métier)
    acompte_25 = details.get('versements', {}).get('acompte_25', {}).get('montant', 0)
    acompte_10 = details.get('versements', {}).get('acompte_10', {}).get('montant', 0)
    elements.append(Paragraph(f"Acompte du 25 : {acompte_25:.2f} CHF", styles['Normal']))
    elements.append(Paragraph(f"Acompte du 10 (salaire net − acompte 25) : {acompte_10:.2f} CHF", styles['Normal']))
    elements.append(Spacer(1, 12))

    # Signature
    elements.append(Paragraph("_________________________", styles['Normal']))
    elements.append(Paragraph("Signature employeur", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    return buffer
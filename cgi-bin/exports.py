from flask import render_template
from xlsxwriter import Workbook
from io import BytesIO
from weasyprint import HTML
import datetime

def generate_excel(stats, annee):
    """Génère un fichier Excel du compte de résultat"""
    output = BytesIO()
    workbook = Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet(f"Compte de résultat {annee}")
    
    # Formats
    header_format = workbook.add_format({
        'bold': True, 'bg_color': '#4472C4', 'font_color': 'white', 
        'border': 1, 'align': 'center'
    })
    money_format = workbook.add_format({'num_format': '#,##0.00'})
    total_format = workbook.add_format({
        'bold': True, 'num_format': '#,##0.00',
        'bg_color': '#E7E6E6', 'border': 1
    })
    
    # En-têtes
    worksheet.write(0, 0, f"Compte de résultat {annee}", header_format)
    worksheet.merge_range(0, 0, 0, 2, f"Compte de résultat {annee}", header_format)
    
    # Section Produits
    worksheet.write(2, 0, "PRODUITS", header_format)
    worksheet.merge_range(2, 0, 2, 2, "PRODUITS", header_format)
    
    row = 3
    for produit in stats['produits']:
        if produit['montant']:
            worksheet.write(row, 0, produit['numero'])
            worksheet.write(row, 1, produit['categorie_nom'])
            worksheet.write(row, 2, produit['montant'], money_format)
            row += 1
    
    worksheet.write(row, 1, "TOTAL PRODUITS", total_format)
    worksheet.write(row, 2, stats['total_produits'], total_format)
    row += 2
    
    # Section Charges
    worksheet.write(row, 0, "CHARGES", header_format)
    worksheet.merge_range(row, 0, row, 2, "CHARGES", header_format)
    row += 1
    
    for charge in stats['charges']:
        if charge['montant']:
            worksheet.write(row, 0, charge['numero'])
            worksheet.write(row, 1, charge['categorie_nom'])
            worksheet.write(row, 2, charge['montant'], money_format)
            row += 1
    
    worksheet.write(row, 1, "TOTAL CHARGES", total_format)
    worksheet.write(row, 2, stats['total_charges'], total_format)
    row += 1
    
    # Résultat
    result_format = workbook.add_format({
        'bold': True, 'num_format': '#,##0.00',
        'bg_color': '#70AD47' if stats['resultat'] >= 0 else '#FF0000',
        'font_color': 'white', 'border': 1
    })
    
    worksheet.write(row, 1, "RÉSULTAT", result_format)
    worksheet.write(row, 2, stats['resultat'], result_format)
    
    # Ajustement des colonnes
    worksheet.set_column(0, 0, 15)
    worksheet.set_column(1, 1, 40)
    worksheet.set_column(2, 2, 20)
    
    workbook.close()
    output.seek(0)
    return output.getvalue()

def generate_pdf(stats, annee):
    """Génère un PDF du compte de résultat"""
    html = render_template('comptabilite/export_pdf.html', 
                         stats=stats,
                         annee=annee,
                         date=datetime.datetime.now().strftime('%d.%m.%Y'))
    
    pdf = HTML(string=html).write_pdf()
    return pdf
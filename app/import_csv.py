import csv
import io
from decimal import Decimal, InvalidOperation
from datetime import datetime
from flask import request, render_template, redirect, url_for, flash, session

@bp.route('/import/csv', methods=['GET', 'POST'])
@login_required
def import_csv_upload():
    if request.method == 'GET':
        return render_template('banking/import_csv_upload.html')
    
    file = request.files.get('csv_file')
    if not file or not file.filename.endswith('.csv'):
        flash("Veuillez uploader un fichier CSV.", "danger")
        return redirect(url_for('banking.import_csv_upload'))

    # Lire le CSV
    stream = io.TextIOWrapper(file.stream, encoding='utf-8')
    reader = csv.DictReader(stream)
    headers = reader.fieldnames or []
    rows = [row for row in reader][:20]  # Prévisualisation limitée

    if not headers:
        flash("Le fichier CSV est vide ou mal formaté.", "danger")
        return redirect(url_for('banking.import_csv_upload'))

    # Sauvegarder dans la session
    session['csv_headers'] = headers
    session['csv_rows'] = rows

    # Récupérer les comptes de l'utilisateur
    user_id = current_user.id
    comptes = g.models.compte_model.get_by_user_id(user_id)
    sous_comptes = g.models.sous_compte_model.get_all_sous_comptes_by_user_id(user_id)

    comptes_possibles = []
    for c in comptes:
        comptes_possibles.append({
            'id': c['id'],
            'nom': c['nom_compte'],
            'type': 'compte_principal'
        })
    for sc in sous_comptes:
        comptes_possibles.append({
            'id': sc['id'],
            'nom': sc['nom_sous_compte'],
            'type': 'sous_compte'
        })

    session['comptes_possibles'] = comptes_possibles

    return redirect(url_for('banking.import_csv_map'))


@bp.route('/import/csv/map', methods=['GET'])
@login_required
def import_csv_map():
    if 'csv_headers' not in session:
        return redirect(url_for('banking.import_csv_upload'))
    return render_template('banking/import_csv_map.html')


@bp.route('/import/csv/confirm', methods=['POST'])
@login_required
def import_csv_confirm():
    user_id = current_user.id
    mapping = {
        'date': request.form['col_date'],
        'montant': request.form['col_montant'],
        'type': request.form['col_type'],
        'description': request.form.get('col_description') or None,
        'source': request.form['col_source'],
        'dest': request.form.get('col_dest') or None,
    }
    session['column_mapping'] = mapping

    # === 🔁 TRIER LES LIGNES DÈS MAINTENANT ===
    csv_rows = session.get('csv_rows', [])
    date_col = mapping['date']

    def parse_date_for_sort(row):
        d = row.get(date_col, '').strip()
        if not d:
            return datetime.max
        try:
            return datetime.strptime(d, '%Y-%m-%d')
        except ValueError:
            try:
                return datetime.strptime(d, '%Y-%m-%dT%H:%M')
            except ValueError:
                return datetime.max

    csv_rows_sorted = sorted(csv_rows, key=parse_date_for_sort)
    session['csv_rows'] = csv_rows_sorted  # <-- on remplace par la version triée

    # Préparer les lignes avec options de sélection (dans le nouvel ordre)
    rows_with_options = []
    for i, row in enumerate(csv_rows_sorted):
        source_val = row.get(mapping['source'], '').strip()
        dest_val = row.get(mapping['dest'], '').strip() if mapping['dest'] else ''
        rows_with_options.append({
            'index': i,
            'source_val': source_val,
            'dest_val': dest_val,
        })

    return render_template('banking/import_csv_confirm.html', rows=rows_with_options)

@bp.route('/import/csv/final', methods=['POST'])
@login_required
def import_csv_final():
    user_id = current_user.id
    mapping = session.get('column_mapping')
    csv_rows = session.get('csv_rows', [])
    comptes_possibles = {str(c['id']) + '|' + c['type']: c for c in session.get('comptes_possibles', [])}

    if not mapping or not csv_rows:
        flash("Données d'import manquantes. Veuillez recommencer.", "danger")
        return redirect(url_for('banking.import_csv_upload'))

    success_count = 0
    errors = []

    for i, row in enumerate(csv_rows):
        try:
            # Extraction
            date_str = row[mapping['date']].strip()
            montant_str = row[mapping['montant']].strip().replace(',', '.')
            tx_type = row[mapping['type']].lower().strip()
            desc = row.get(mapping['description'], '').strip() if mapping['description'] else ''

            # Conversion
            try:
                montant = Decimal(montant_str)
                if montant <= 0:
                    raise ValueError("Montant doit être > 0")
            except (InvalidOperation, ValueError) as e:
                errors.append(f"Ligne {i+1}: montant invalide ({montant_str})")
                continue

            try:
                date_tx = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                # Essayer avec heure si présent (comme dans tes formulaires)
                try:
                    date_tx = datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    errors.append(f"Ligne {i+1}: date invalide ({date_str})")
                    continue

            # Récupérer les choix utilisateur
            source_key = request.form.get(f'row_{i}_source')
            dest_key = request.form.get(f'row_{i}_dest')

            if not source_key or source_key not in comptes_possibles:
                errors.append(f"Ligne {i+1}: compte source invalide")
                continue

            source_info = comptes_possibles[source_key]
            source_id = source_info['id']
            source_type = source_info['type']

            if tx_type in ['depot', 'retrait']:
                if tx_type == 'depot':
                    ok, msg = g.models.transaction_financiere_model.create_depot(
                        compte_id=source_id,
                        user_id=user_id,
                        montant=montant,
                        description=desc,
                        compte_type=source_type,
                        date_transaction=date_tx
                    )
                else:  # retrait
                    ok, msg = g.models.transaction_financiere_model.create_retrait(
                        compte_id=source_id,
                        user_id=user_id,
                        montant=montant,
                        description=desc,
                        compte_type=source_type,
                        date_transaction=date_tx
                    )
                if ok:
                    success_count += 1
                else:
                    errors.append(f"Ligne {i+1}: {msg}")

            elif tx_type == 'transfert':
                if not dest_key or dest_key not in comptes_possibles:
                    errors.append(f"Ligne {i+1}: compte destination requis pour transfert")
                    continue
                dest_info = comptes_possibles[dest_key]
                dest_id = dest_info['id']
                dest_type = dest_info['type']

                # Vérifier que les comptes sont différents
                if source_id == dest_id and source_type == dest_type:
                    errors.append(f"Ligne {i+1}: source et destination identiques")
                    continue

                ok, msg = g.models.transaction_financiere_model.create_transfert_interne(
                    source_type=source_type,
                    source_id=source_id,
                    dest_type=dest_type,
                    dest_id=dest_id,
                    user_id=user_id,
                    montant=montant,
                    description=desc,
                    date_transaction=date_tx
                )
                if ok:
                    success_count += 1
                else:
                    errors.append(f"Ligne {i+1}: {msg}")
            else:
                errors.append(f"Ligne {i+1}: type inconnu '{tx_type}' (attendu: depot, retrait, transfert)")

        except Exception as e:
            errors.append(f"Ligne {i+1}: erreur inattendue ({str(e)})")

    # Nettoyer la session
    session.pop('csv_headers', None)
    session.pop('csv_rows', None)
    session.pop('comptes_possibles', None)
    session.pop('column_mapping', None)

    flash(f"✅ Import terminé : {success_count} transaction(s) créée(s).", "success")
    for err in errors[:5]:  # Limiter les messages d'erreur affichés
        flash(f"❌ {err}", "danger")

    return redirect(url_for('banking.banking_dashboard'))
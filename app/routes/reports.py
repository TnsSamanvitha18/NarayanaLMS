from flask import Blueprint, render_template, request, redirect, url_for, session, send_file
from app.services.report_service import generate_report_dataframe, export_report_csv, ALL_REPORT_COLUMNS

reports_bp = Blueprint('reports', __name__)

def check_admin():
    return session.get('admin_logged_in')

@reports_bp.route('/')
def index():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    search_query = request.args.get('search', '').strip()
    mode_filter = request.args.get('mode', 'ALL').strip()
    selected_cols = request.args.getlist('cols')

    if not selected_cols:
        selected_cols = list(ALL_REPORT_COLUMNS.keys())

    df = generate_report_dataframe(selected_columns=selected_cols, search_query=search_query, mode_filter=mode_filter)

    # Conversion to dictionary records for rendering in Jinja template table
    records = df.to_dict(orient='records')
    headers = list(df.columns)

    return render_template(
        'reports/index.html',
        all_columns=ALL_REPORT_COLUMNS,
        selected_cols=selected_cols,
        headers=headers,
        records=records,
        search_query=search_query,
        mode_filter=mode_filter
    )


@reports_bp.route('/export_csv')
def export_csv():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    search_query = request.args.get('search', '').strip()
    mode_filter = request.args.get('mode', 'ALL').strip()
    selected_cols = request.args.getlist('cols')

    if not selected_cols:
        selected_cols = list(ALL_REPORT_COLUMNS.keys())

    df = generate_report_dataframe(selected_columns=selected_cols, search_query=search_query, mode_filter=mode_filter)
    csv_buffer = export_report_csv(df)

    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name='Narayana_LND_Report.csv'
    )

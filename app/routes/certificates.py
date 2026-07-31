from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_file
import os
from datetime import datetime
from app.models import db
from app.models.certificate import Certificate
from app.models.user import Learner
from app.models.course import Course
from app.services.pdf_service import generate_certificate_pdf

certificates_bp = Blueprint('certificates', __name__)

def check_admin():
    return session.get('admin_logged_in')

@certificates_bp.route('/')
def list_certificates():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    search_query = request.args.get('search', '').strip()
    query = Certificate.query.join(Learner).join(Course)

    if search_query:
        query = query.filter(
            (Certificate.certificate_id.ilike(f'%{search_query}%')) |
            (Learner.name.ilike(f'%{search_query}%')) |
            (Learner.global_id.ilike(f'%{search_query}%')) |
            (Course.name.ilike(f'%{search_query}%'))
        )

    certs = query.order_by(Certificate.issue_date.desc()).all()
    return render_template('certificates/list.html', certificates=certs, search_query=search_query)


@certificates_bp.route('/download/<cert_id_str>')
def download_certificate(cert_id_str):
    cert = Certificate.query.filter_by(certificate_id=cert_id_str).first_or_404()
    learner = cert.learner
    course = cert.course

    cert_filename = f"cert_{cert.certificate_id}.pdf"
    pdf_dir = os.path.join(certificates_bp.root_path, '..', '..', 'uploads', 'certificates')
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, cert_filename)

    if not os.path.exists(pdf_path):
        date_str = cert.issue_date.strftime('%d-%b-%Y')
        generate_certificate_pdf(learner.name, course.name, date_str, cert.certificate_id, pdf_path)

    return send_file(pdf_path, as_attachment=True, download_name=f"Narayana_Certificate_{cert.certificate_id}.pdf")

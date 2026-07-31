from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.user import AdminUser, Learner

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('auth.admin_login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard.index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if username == 'admin' and password == 'admin':
            session['admin_logged_in'] = True
            session['admin_username'] = 'admin'
            flash('Successfully logged in as L&D Administrator.', 'success')
            return redirect(url_for('dashboard.index'))
        else:
            error = "Invalid Username or Password"

    return render_template('auth/admin_login.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.admin_login'))


@auth_bp.route('/learner/login', methods=['GET', 'POST'])
def learner_login():
    """
    Learner Login endpoint.
    URL format: http://localhost:5000/learner/login?classId=xxxxx
    Later this endpoint will be replaced by Google SSO.
    """
    class_id_str = request.args.get('classId') or request.form.get('class_id', '')
    course_id_str = request.args.get('courseId') or request.form.get('course_id', '')
    
    error = None
    if request.method == 'POST':
        global_id = request.form.get('global_id', '').strip()
        password = request.form.get('password', '').strip()
        class_id_str = request.form.get('class_id', '').strip() or class_id_str
        course_id_str = request.form.get('course_id', '').strip() or course_id_str

        if not global_id:
            error = "Please enter your Global ID."
        else:
            # Find or auto-register Learner for POC testing
            learner = Learner.query.filter_by(global_id=global_id).first()
            if not learner:
                from app.models import db
                learner = Learner(global_id=global_id, name=f"Learner {global_id}", department="L&D")
                db.session.add(learner)
                db.session.commit()

            session['learner_id'] = learner.id
            session['learner_global_id'] = learner.global_id
            session['learner_name'] = learner.name

            flash(f"Welcome, {learner.name}!", "success")

            if class_id_str:
                return redirect(url_for('learners.class_flow', class_id_str=class_id_str))
            elif course_id_str:
                return redirect(url_for('learners.self_paced_flow', course_id_str=course_id_str))
            else:
                return redirect(url_for('learners.my_portal'))

    return render_template('auth/learner_login.html', class_id=class_id_str, course_id=course_id_str, error=error)

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file
from datetime import datetime
import os
from app.models import db
from app.models.course import Course, CourseAssessment
from app.models.live_class import LiveClass, AuditLog
from app.models.feedback import FeedbackRepository
from app.services.qr_service import generate_class_qr
from app.services.lock_service import unlock_class, check_and_auto_lock_classes

classes_bp = Blueprint('classes', __name__)

def check_admin():
    return session.get('admin_logged_in')

@classes_bp.route('/')
def list_classes():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    check_and_auto_lock_classes()

    search_query = request.args.get('search', '').strip()
    mode_filter = request.args.get('mode', '').strip()

    query = LiveClass.query

    if search_query:
        query = query.filter(
            (LiveClass.class_name.ilike(f'%{search_query}%')) |
            (LiveClass.class_id.ilike(f'%{search_query}%')) |
            (LiveClass.facilitator_name.ilike(f'%{search_query}%'))
        )

    if mode_filter and mode_filter != 'ALL':
        query = query.filter_by(class_mode=mode_filter)

    classes = query.order_by(LiveClass.class_date.desc(), LiveClass.id.desc()).all()
    return render_template('classes/list.html', classes=classes, search_query=search_query, mode_filter=mode_filter)


@classes_bp.route('/create', methods=['GET', 'POST'])
def create_class():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    live_courses = Course.query.filter(Course.mode.like('Live%')).all()
    feedback_repos = FeedbackRepository.query.all()

    if request.method == 'POST':
        course_id = int(request.form.get('course_id'))
        course = Course.query.get_or_404(course_id)
        
        class_mode = request.form.get('class_mode', 'In Person')
        date_str = request.form.get('class_date')
        class_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        location = request.form.get('location', '').strip()
        branch = request.form.get('branch', '').strip()
        session_time = request.form.get('session_time', 'Morning').strip()
        meet_link = request.form.get('meet_link', '').strip()

        facilitator_name = request.form.get('facilitator_name', '').strip()
        co_facilitator_name = request.form.get('co_facilitator_name', '').strip()
        expected_attendance = int(request.form.get('expected_attendance', 30))
        feedback_repo_id = request.form.get('feedback_repo_id')
        feedback_repo_id = int(feedback_repo_id) if feedback_repo_id else None

        class_id = LiveClass.generate_class_id()

        temp_cls = LiveClass(
            class_id=class_id,
            class_name='',
            course_id=course.id,
            class_mode=class_mode,
            class_date=class_date,
            location=location,
            branch=branch,
            session_time=session_time,
            meet_link=meet_link,
            facilitator_name=facilitator_name,
            co_facilitator_name=co_facilitator_name,
            duration_hours=course.duration_hours,
            expected_attendance=expected_attendance,
            feedback_repo_id=feedback_repo_id
        )
        
        # Build standard auto name: COURSECODE-DD-MMM-YYYY-LOCATION-CAMPUS-SESSION
        course_code = course.name.split()[0] if course.name else 'CRS'
        temp_cls.class_name = temp_cls.build_class_name(course_code)

        db.session.add(temp_cls)

        # Handle Pre/Post assessment CSV files if uploaded
        from app.services.assessment_service import parse_assessment_csv
        from app.models.course import CourseAssessment

        pre_file = request.files.get('pre_assessment_csv')
        post_file = request.files.get('post_assessment_csv')

        if pre_file and pre_file.filename:
            q_list, errs = parse_assessment_csv(pre_file.stream, filename=pre_file.filename)
            for q in q_list:
                ca = CourseAssessment(
                    course_id=course.id,
                    assessment_type='PRE',
                    serial_number=q.get('serial_number'),
                    question=q.get('question'),
                    option1=q.get('option1'),
                    option2=q.get('option2'),
                    option3=q.get('option3'),
                    option4=q.get('option4'),
                    correct_option=q.get('correct_option')
                )
                db.session.add(ca)

        if post_file and post_file.filename:
            q_list, errs = parse_assessment_csv(post_file.stream, filename=post_file.filename)
            for q in q_list:
                ca = CourseAssessment(
                    course_id=course.id,
                    assessment_type='POST',
                    serial_number=q.get('serial_number'),
                    question=q.get('question'),
                    option1=q.get('option1'),
                    option2=q.get('option2'),
                    option3=q.get('option3'),
                    option4=q.get('option4'),
                    correct_option=q.get('correct_option')
                )
                db.session.add(ca)

        db.session.commit()

        # Generate QR code for the class
        generate_class_qr(temp_cls.class_id)

        flash(f"Class {temp_cls.class_name} ({temp_cls.class_id}) created successfully!", "success")
        return redirect(url_for('classes.view_class', class_id=temp_cls.id))

    auto_id = LiveClass.generate_class_id()
    return render_template('classes/create_edit.html', auto_id=auto_id, live_courses=live_courses, feedback_repos=feedback_repos, live_class=None)


@classes_bp.route('/<int:class_id>')
def view_class(class_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    live_class = LiveClass.query.get_or_404(class_id)
    qr_url = generate_class_qr(live_class.class_id)

    # Fetch associated pre/post assessment counts
    pre_count = CourseAssessment.query.filter_by(course_id=live_class.course_id, assessment_type='PRE').count()
    post_count = CourseAssessment.query.filter_by(course_id=live_class.course_id, assessment_type='POST').count()

    audit_logs = AuditLog.query.filter_by(entity_type='LiveClass', entity_id=live_class.class_id).order_by(AuditLog.timestamp.desc()).all()

    return render_template(
        'classes/detail.html',
        live_class=live_class,
        qr_url=qr_url,
        pre_count=pre_count,
        post_count=post_count,
        audit_logs=audit_logs
    )


@classes_bp.route('/<int:class_id>/edit', methods=['GET', 'POST'])
def edit_class(class_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    live_class = LiveClass.query.get_or_404(class_id)
    live_courses = Course.query.filter_by(mode='Live').all()
    feedback_repos = FeedbackRepository.query.all()

    if request.method == 'POST':
        live_class.course_id = int(request.form.get('course_id'))
        course = Course.query.get(live_class.course_id)
        
        live_class.class_mode = request.form.get('class_mode', 'In Person')
        date_str = request.form.get('class_date')
        live_class.class_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        live_class.location = request.form.get('location', '').strip()
        live_class.branch = request.form.get('branch', '').strip()
        live_class.session_time = request.form.get('session_time', 'Morning').strip()
        live_class.meet_link = request.form.get('meet_link', '').strip()

        live_class.facilitator_name = request.form.get('facilitator_name', '').strip()
        live_class.co_facilitator_name = request.form.get('co_facilitator_name', '').strip()
        live_class.expected_attendance = int(request.form.get('expected_attendance', 30))
        live_class.duration_hours = course.duration_hours
        
        feedback_repo_id = request.form.get('feedback_repo_id')
        live_class.feedback_repo_id = int(feedback_repo_id) if feedback_repo_id else None

        course_code = course.name.split()[0] if course.name else 'CRS'
        live_class.class_name = live_class.build_class_name(course_code)

        db.session.commit()
        flash(f"Class {live_class.class_id} updated successfully.", "success")
        return redirect(url_for('classes.view_class', class_id=live_class.id))

    return render_template(
        'classes/create_edit.html',
        live_class=live_class,
        auto_id=live_class.class_id,
        live_courses=live_courses,
        feedback_repos=feedback_repos
    )


@classes_bp.route('/<int:class_id>/delete', methods=['POST'])
def delete_class(class_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    live_class = LiveClass.query.get_or_404(class_id)
    db.session.delete(live_class)
    db.session.commit()
    flash(f"Class {live_class.class_id} deleted.", "success")
    return redirect(url_for('classes.list_classes'))


@classes_bp.route('/unlock', methods=['POST'])
def unlock_class_route():
    if not check_admin():
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    class_id_str = request.form.get('class_id', '').strip()
    reason = request.form.get('reason', '').strip()

    success, msg = unlock_class(class_id_str, reason, session.get('admin_username', 'admin'))
    return jsonify({'success': success, 'message': msg})


@classes_bp.route('/download_qr/<class_id_str>')
def download_qr(class_id_str):
    qr_filename = f"qr_{class_id_str}.png"
    qr_file_path = os.path.join(classes_bp.root_path, '..', 'static', 'qr_codes', qr_filename)
    
    if not os.path.exists(qr_file_path):
        generate_class_qr(class_id_str)
        
    return send_file(qr_file_path, as_attachment=True, download_name=f"QR_{class_id_str}.png")

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from datetime import datetime
from app.models import db
from app.models.attendance import Attendance
from app.models.live_class import LiveClass, AuditLog
from app.models.user import Learner

attendance_bp = Blueprint('attendance', __name__)

def check_admin():
    return session.get('admin_logged_in')

@attendance_bp.route('/')
def list_attendance():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    search_query = request.args.get('search', '').strip()
    class_filter = request.args.get('class_id', '').strip()

    query = Attendance.query.join(Learner).join(LiveClass)

    if search_query:
        query = query.filter((Learner.global_id.ilike(f'%{search_query}%')) | (Learner.name.ilike(f'%{search_query}%')))

    if class_filter:
        query = query.filter(LiveClass.class_id == class_filter)

    attendances = query.order_by(Attendance.timestamp.desc()).all()
    live_classes = LiveClass.query.all()

    total_records = len(attendances)
    present_count = sum(1 for a in attendances if a.status in ['Present', 'Late'])
    pct = round((present_count / total_records * 100.0), 1) if total_records > 0 else 0.0

    return render_template(
        'attendance/list.html',
        attendances=attendances,
        live_classes=live_classes,
        search_query=search_query,
        class_filter=class_filter,
        total_records=total_records,
        present_count=present_count,
        pct=pct
    )


@attendance_bp.route('/manual_override', methods=['GET', 'POST'])
def manual_override():
    """
    Exception Flow: Add Manual Attendance if QR or SSO fails.
    Fields: Global ID, Class, Reason, Attendance Status (Present/Absent/Late).
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    live_classes = LiveClass.query.order_by(LiveClass.class_date.desc()).all()

    if request.method == 'POST':
        global_id = request.form.get('global_id', '').strip()
        class_id = int(request.form.get('class_id'))
        reason = request.form.get('reason', '').strip()
        status = request.form.get('status', 'Present').strip()

        if not global_id or not reason:
            flash("Global ID and mandatory Exception Reason are required.", "danger")
            return redirect(url_for('attendance.manual_override'))

        learner = Learner.query.filter_by(global_id=global_id).first()
        if not learner:
            learner = Learner(global_id=global_id, name=f"Learner {global_id}", department="L&D")
            db.session.add(learner)
            db.session.commit()

        live_cls = LiveClass.query.get_or_404(class_id)

        # Check existing attendance
        existing = Attendance.query.filter_by(class_id=live_cls.id, learner_id=learner.id).first()
        if existing:
            existing.status = status
            existing.recorded_via = 'Manual'
            existing.manual_reason = reason
        else:
            new_att = Attendance(
                class_id=live_cls.id,
                learner_id=learner.id,
                status=status,
                recorded_via='Manual',
                manual_reason=reason
            )
            db.session.add(new_att)

        # Write audit log entry
        audit_log = AuditLog(
            entity_type='Attendance',
            entity_id=f"{live_cls.class_id}:{learner.global_id}",
            action='MANUAL_ATTENDANCE',
            reason=reason,
            performed_by=session.get('admin_username', 'admin')
        )
        db.session.add(audit_log)
        db.session.commit()

        flash(f"Manual attendance override recorded for Learner {global_id} ({status}).", "success")
        return redirect(url_for('attendance.list_attendance'))

    return render_template('attendance/manual_override.html', live_classes=live_classes)


@attendance_bp.route('/bulk_upload', methods=['POST'])
def bulk_upload():
    """
    Bulk Attendance Entry via CSV Upload or Global ID Text Box for Live In Person and Live Online classes.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    class_id = request.form.get('class_id')
    if not class_id:
        flash("Please select a Live Class.", "danger")
        return redirect(request.referrer or url_for('attendance.list_attendance'))

    live_cls = LiveClass.query.get_or_404(class_id)
    
    global_ids_text = request.form.get('global_ids_text', '').strip()
    status = request.form.get('status', 'Present').strip()
    reason = request.form.get('reason', 'Admin Bulk Entry').strip()
    csv_file = request.files.get('attendance_csv')

    target_gids = []

    # 1. Parse text box (comma or newline separated Global IDs)
    if global_ids_text:
        lines = [x.strip() for x in global_ids_text.replace('\r', '').replace('\n', ',').split(',') if x.strip()]
        target_gids.extend(lines)

    # 2. Parse CSV / Excel upload if provided
    if csv_file and csv_file.filename:
        import pandas as pd
        try:
            filename = csv_file.filename.lower()
            if filename.endswith('.xlsx') or filename.endswith('.xls'):
                df = pd.read_excel(csv_file.stream)
            else:
                df = pd.read_csv(csv_file.stream)
            
            df.columns = [str(c).strip().lower() for c in df.columns]
            
            gid_col = None
            for col in df.columns:
                if 'global' in col or 'id' in col or 'learner' in col:
                    gid_col = col
                    break
            if not gid_col and len(df.columns) > 0:
                gid_col = df.columns[0]
                
            if gid_col:
                for _, row in df.iterrows():
                    val = str(row.get(gid_col, '')).strip()
                    if val and val.lower() != 'nan':
                        target_gids.append(val)
        except Exception as e:
            flash(f"Error reading attendance file: {str(e)}", "danger")
            return redirect(request.referrer or url_for('attendance.list_attendance'))

    if not target_gids:
        flash("No Global IDs found. Please enter Global IDs in text box or upload a CSV file.", "warning")
        return redirect(request.referrer or url_for('attendance.list_attendance'))

    from app.models.enrollment import LearnerEnrollment

    added_count = 0
    updated_count = 0

    for gid in set(target_gids):
        learner = Learner.query.filter_by(global_id=gid).first()
        if not learner:
            learner = Learner(global_id=gid, name=f"Learner {gid}", department="L&D")
            db.session.add(learner)
            db.session.commit()

        # Ensure enrollment exists for the course
        en = LearnerEnrollment.query.filter_by(learner_id=learner.id, course_id=live_cls.course_id).first()
        if not en:
            en = LearnerEnrollment(learner_id=learner.id, course_id=live_cls.course_id, class_id=live_cls.id, completion_status='In Progress')
            db.session.add(en)

        att = Attendance.query.filter_by(class_id=live_cls.id, learner_id=learner.id).first()
        if att:
            att.status = status
            att.recorded_via = 'Bulk CSV/Text'
            att.manual_reason = reason
            updated_count += 1
        else:
            new_att = Attendance(
                class_id=live_cls.id,
                learner_id=learner.id,
                status=status,
                recorded_via='Bulk CSV/Text',
                manual_reason=reason
            )
            db.session.add(new_att)
            added_count += 1

    db.session.commit()
    flash(f"Attendance recorded for class '{live_cls.class_name}': {added_count} new entries, {updated_count} updated ({status}).", "success")
    return redirect(request.referrer or url_for('attendance.list_attendance'))

from flask import Blueprint, render_template, session, redirect, url_for
from datetime import datetime, date
from app.models import db
from app.models.course import Course
from app.models.live_class import LiveClass, AuditLog
from app.models.user import Learner
from app.models.attendance import Attendance
from app.models.certificate import Certificate
from app.services.lock_service import check_and_auto_lock_classes

dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/dashboard')
def index():
    if not session.get('admin_logged_in'):
        return redirect(url_for('auth.admin_login'))

    # Auto-lock check on load
    check_and_auto_lock_classes()

    today = date.today()
    current_month_start = date(today.year, today.month, 1)

    # Core Metrics
    total_courses = Course.query.count()
    self_paced_courses = Course.query.filter_by(mode='Self Paced').count()
    live_courses = Course.query.filter_by(mode='Live').count()
    
    total_classes = LiveClass.query.count()
    upcoming_classes_query = LiveClass.query.filter(LiveClass.class_date >= today).order_by(LiveClass.class_date.asc())
    upcoming_classes_count = upcoming_classes_query.count()
    upcoming_classes_list = upcoming_classes_query.limit(5).all()

    total_learners = Learner.query.count()
    certificates_count = Certificate.query.count()

    # Attendance Percentage Calculation
    total_attendances = Attendance.query.count()
    present_attendances = Attendance.query.filter(Attendance.status.in_(['Present', 'Late'])).count()
    attendance_pct = round((present_attendances / total_attendances * 100.0), 1) if total_attendances > 0 else 0.0

    # Facilitation Credits Calculation
    all_classes = LiveClass.query.all()
    overall_facilitator_hours = sum(c.duration_hours for c in all_classes)
    overall_co_facilitator_hours = sum(c.duration_hours for c in all_classes if c.co_facilitator_name)

    current_month_classes = LiveClass.query.filter(LiveClass.class_date >= current_month_start).all()
    current_month_hours = sum(c.duration_hours for c in current_month_classes)

    # Recent Audit Activities
    recent_activities = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(6).all()

    return render_template(
        'dashboard/index.html',
        total_courses=total_courses,
        self_paced_courses=self_paced_courses,
        live_courses=live_courses,
        total_classes=total_classes,
        upcoming_classes_count=upcoming_classes_count,
        upcoming_classes_list=upcoming_classes_list,
        total_learners=total_learners,
        attendance_pct=attendance_pct,
        certificates_count=certificates_count,
        overall_facilitator_hours=overall_facilitator_hours,
        overall_co_facilitator_hours=overall_co_facilitator_hours,
        current_month_hours=current_month_hours,
        recent_activities=recent_activities
    )

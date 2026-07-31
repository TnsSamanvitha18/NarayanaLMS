import pandas as pd
import io
from app.models import db
from app.models.course import Course
from app.models.live_class import LiveClass
from app.models.user import Learner
from app.models.enrollment import LearnerEnrollment, AssessmentAttempt
from app.models.attendance import Attendance
from app.models.certificate import Certificate
from app.models.feedback import FeedbackResponse, FeedbackRepository

ALL_REPORT_COLUMNS = {
    'course_name': 'Course Name',
    'class_name': 'Class Name',
    'global_id': 'Learner Global ID',
    'learner_name': 'Learner Name',
    'attendance_status': 'Attendance Status',
    'pre_assessment': 'Pre Assessment Score (%)',
    'post_assessment': 'Post Assessment Score (%)',
    'completion_status': 'Completion Status',
    'certificate_id': 'Certificate ID',
    'facilitator': 'Facilitator Name',
    'co_facilitator': 'Co-Facilitator Name',
    'duration': 'Duration (Hours)',
    'feedback_status': 'Feedback Submitted'
}

def generate_report_dataframe(selected_columns=None, search_query=None, mode_filter=None):
    """
    Queries DB for learner enrollments, builds flat data records,
    and returns a Pandas DataFrame with selected columns.
    """
    if not selected_columns:
        selected_columns = list(ALL_REPORT_COLUMNS.keys())

    enrollments = LearnerEnrollment.query.all()
    rows = []

    for en in enrollments:
        learner = en.learner
        course = en.course
        live_cls = en.live_class

        # Check search query
        if search_query:
            sq = search_query.lower()
            match = (
                sq in (course.name or '').lower() or
                sq in (learner.global_id or '').lower() or
                sq in (learner.name or '').lower() or
                (live_cls and sq in (live_cls.class_name or '').lower())
            )
            if not match:
                continue

        # Check mode filter
        if mode_filter and mode_filter != 'ALL':
            if course.mode != mode_filter:
                continue

        # Get attendance status
        att_status = 'N/A'
        if live_cls:
            att = Attendance.query.filter_by(class_id=live_cls.id, learner_id=learner.id).first()
            att_status = att.status if att else 'Absent'

        # Get pre & post assessment scores
        pre_attempt = AssessmentAttempt.query.filter_by(enrollment_id=en.id, assessment_type='PRE').order_by(AssessmentAttempt.id.desc()).first()
        post_attempt = AssessmentAttempt.query.filter_by(enrollment_id=en.id, assessment_type='POST').order_by(AssessmentAttempt.id.desc()).first()

        pre_score = f"{pre_attempt.score_percentage}%" if pre_attempt else "N/A"
        post_score = f"{post_attempt.score_percentage}%" if post_attempt else "N/A"

        # Certificate
        cert = Certificate.query.filter_by(learner_id=learner.id, course_id=course.id).first()
        cert_id = cert.certificate_id if cert else "None"

        # Feedback
        fb_resp = None
        if live_cls and live_cls.feedback_repo_id:
            fb_resp = FeedbackResponse.query.filter_by(class_id=live_cls.id, learner_id=learner.id).first()
        fb_status = "Yes" if fb_resp else "No"

        row = {
            'course_name': course.name if course else 'N/A',
            'class_name': live_cls.class_name if live_cls else 'Self-Paced (N/A)',
            'global_id': learner.global_id if learner else 'N/A',
            'learner_name': learner.name if learner else 'N/A',
            'attendance_status': att_status,
            'pre_assessment': pre_score,
            'post_assessment': post_score,
            'completion_status': en.completion_status,
            'certificate_id': cert_id,
            'facilitator': live_cls.facilitator_name if live_cls else 'N/A',
            'co_facilitator': live_cls.co_facilitator_name if (live_cls and live_cls.co_facilitator_name) else 'N/A',
            'duration': f"{course.duration_hours} hrs",
            'feedback_status': fb_status
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=[ALL_REPORT_COLUMNS[col] for col in selected_columns if col in ALL_REPORT_COLUMNS])
    else:
        # Filter columns
        filtered_cols = [c for c in selected_columns if c in df.columns]
        df = df[filtered_cols]
        # Rename columns to human readable titles
        df.rename(columns={c: ALL_REPORT_COLUMNS[c] for c in filtered_cols}, inplace=True)

    return df


def export_report_csv(df):
    """
    Exports DataFrame to CSV string buffer.
    """
    output = io.BytesIO()
    df.to_csv(output, index=False, encoding='utf-8')
    output.seek(0)
    return output


def generate_course_analytics_csv(course_id):
    """
    Builds and exports Course Performance Analytics CSV for a specific course.
    """
    course = Course.query.get(course_id)
    if not course:
        df = pd.DataFrame()
        return export_report_csv(df)

    enrollments = LearnerEnrollment.query.filter_by(course_id=course.id).all()
    rows = []

    for en in enrollments:
        learner = en.learner
        live_cls = en.live_class

        att_status = 'N/A'
        if live_cls:
            att = Attendance.query.filter_by(class_id=live_cls.id, learner_id=learner.id).first()
            att_status = att.status if att else 'Absent'

        pre_attempt = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == en.id) & (AssessmentAttempt.assessment_type.in_(['PRE', 'LESSON_PRE']))).order_by(AssessmentAttempt.id.desc()).first()
        post_attempt = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == en.id) & (AssessmentAttempt.assessment_type.in_(['POST', 'LESSON_POST']))).order_by(AssessmentAttempt.id.desc()).first()
        course_end_attempt = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == en.id) & (AssessmentAttempt.assessment_type == 'COURSE_END')).order_by(AssessmentAttempt.id.desc()).first()

        cert = Certificate.query.filter_by(learner_id=learner.id, course_id=course.id).first()

        row = {
            'Course ID': course.course_id,
            'Course Name': course.name,
            'Course Mode': course.mode,
            'Learner Global ID': learner.global_id if learner else 'N/A',
            'Learner Name': learner.name if learner else 'N/A',
            'Department': learner.department if learner else 'N/A',
            'Attendance Status': att_status,
            'Pre Assessment Score': f"{pre_attempt.score_percentage}%" if pre_attempt else "N/A",
            'Post Assessment Score': f"{post_attempt.score_percentage}%" if post_attempt else "N/A",
            'Course End Exam Score': f"{course_end_attempt.score_percentage}%" if course_end_attempt else "N/A",
            'Completion Status': en.completion_status,
            'Certificate Issued': cert.certificate_id if cert else 'None',
            'Enrolled At': en.assigned_at.strftime('%Y-%m-%d %H:%M') if en.assigned_at else 'N/A'
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    return export_report_csv(df)


def generate_class_attendance_csv(class_id):
    """
    Builds and exports Class Attendance Log CSV for a specific live class.
    """
    live_cls = LiveClass.query.get(class_id)
    if not live_cls:
        df = pd.DataFrame()
        return export_report_csv(df)

    attendances = Attendance.query.filter_by(class_id=live_cls.id).all()
    rows = []

    for att in attendances:
        learner = att.learner
        row = {
            'Class ID': live_cls.class_id,
            'Class Name': live_cls.class_name,
            'Class Date': live_cls.class_date.strftime('%Y-%m-%d') if live_cls.class_date else 'N/A',
            'Session Time': live_cls.session_time or 'N/A',
            'Learner Global ID': learner.global_id if learner else 'N/A',
            'Learner Name': learner.name if learner else 'N/A',
            'Department': learner.department if learner else 'N/A',
            'Attendance Status': att.status,
            'Scan Method': att.recorded_via,
            'Recorded Timestamp': att.timestamp.strftime('%Y-%m-%d %H:%M:%S') if att.timestamp else 'N/A'
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    return export_report_csv(df)

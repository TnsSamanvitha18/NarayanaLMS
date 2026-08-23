import os
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime
import pandas as pd
from app.models import db
from app.models.user import Learner
from app.models.course import Course, CourseAssessment, CourseLesson
from app.models.live_class import LiveClass
from app.models.enrollment import LearnerEnrollment, AssessmentAttempt, LessonReview
from app.models.attendance import Attendance
from app.models.feedback import FeedbackRepository, FeedbackQuestion, FeedbackResponse
from app.models.certificate import Certificate
from app.services.assessment_service import evaluate_assessment
from app.services.pdf_service import generate_certificate_pdf
from app.services.learning_wall_service import create_completion_post

learners_bp = Blueprint('learners', __name__)

def check_admin():
    return session.get('admin_logged_in')

# --- ADMIN LEARNER MANAGEMENT ---

@learners_bp.route('/')
def list_learners():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    search_query = request.args.get('search', '').strip()
    query = Learner.query

    if search_query:
        query = query.filter(
            (Learner.global_id.ilike(f'%{search_query}%')) |
            (Learner.name.ilike(f'%{search_query}%')) |
            (Learner.department.ilike(f'%{search_query}%'))
        )

    learners = query.order_by(Learner.id.desc()).all()
    courses = Course.query.all()
    return render_template('learners/list.html', learners=learners, courses=courses, search_query=search_query)


@learners_bp.route('/reset_attempts/<int:learner_id>', methods=['POST'])
def reset_learner_attempts(learner_id):
    """
    Admin Route: Reset assessment attempts for a learner so they can retake the Course End Assessment.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    learner = Learner.query.get_or_404(learner_id)
    enrollments = LearnerEnrollment.query.filter_by(learner_id=learner.id).all()
    for en in enrollments:
        en.attempts_count = 0
        en.completion_status = 'Enrolled'
        en.final_score = None
        en.completion_date = None
        AssessmentAttempt.query.filter_by(enrollment_id=en.id).delete()

    db.session.commit()
    flash(f"Assessment attempts reset to 0 for Learner '{learner.global_id} - {learner.name}'. They can take the Course End Assessment again!", "success")
    return redirect(url_for('learners.list_learners'))


@learners_bp.route('/assign', methods=['GET', 'POST'])
def assign_learners():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    courses = Course.query.filter_by(mode='Self Paced').all()

    if request.method == 'POST':
        course_id = int(request.form.get('course_id'))
        course = Course.query.get_or_404(course_id)
        
        global_ids_text = request.form.get('global_ids', '').strip()
        csv_file = request.files.get('learner_csv')

        parsed_global_ids = []

        if global_ids_text:
            # Split lines
            lines = global_ids_text.split('\n')
            parsed_global_ids.extend([line.strip() for line in lines if line.strip()])

        if csv_file and csv_file.filename:
            try:
                df = pd.read_csv(csv_file.stream)
                # Check for Global ID or first column
                col_name = df.columns[0]
                for col in df.columns:
                    if 'global' in str(col).lower() or 'id' in str(col).lower():
                        col_name = col
                        break
                for val in df[col_name].dropna():
                    clean_val = str(val).strip()
                    if clean_val and clean_val not in parsed_global_ids:
                        parsed_global_ids.append(clean_val)
            except Exception as e:
                flash(f"Error parsing Learner CSV: {str(e)}", "danger")

        if not parsed_global_ids:
            flash("No valid Global IDs provided.", "warning")
            return redirect(url_for('learners.assign_learners'))

        assigned_count = 0
        already_enrolled_count = 0
        invalid_ids = []

        from app.models.notification import LearnerNotification

        for gid in parsed_global_ids:
            learner = Learner.query.filter_by(global_id=gid).first()
            if not learner:
                invalid_ids.append(gid)
                continue

            # Check if enrollment already exists
            existing_en = LearnerEnrollment.query.filter_by(learner_id=learner.id, course_id=course.id).first()
            if not existing_en:
                en = LearnerEnrollment(
                    learner_id=learner.id,
                    course_id=course.id,
                    completion_status='Enrolled'
                )
                db.session.add(en)
                assigned_count += 1

                # Send Course Assignment notification to learner
                notif = LearnerNotification(
                    learner_id=learner.id,
                    course_id=course.id,
                    title=f"New Course Assigned: {course.name}",
                    message=f"You have been assigned to the self-paced course '{course.name}' ({course.course_id}). Start learning now!",
                    notification_type='COURSE_ASSIGNED'
                )
                db.session.add(notif)
            else:
                already_enrolled_count += 1

        db.session.commit()

        msg = f"Assignment Results for Course '{course.name}': {assigned_count} newly assigned."
        if already_enrolled_count > 0:
            msg += f" {already_enrolled_count} learner(s) were already enrolled."
        if invalid_ids:
            msg += f" {len(invalid_ids)} invalid/non-existing Global ID(s) could not be assigned: {', '.join(invalid_ids[:5])}{'...' if len(invalid_ids) > 5 else ''}."
            flash(msg, "warning" if assigned_count == 0 else "info")
        else:
            flash(msg, "success")

        return redirect(url_for('courses.view_course', course_id=course.id))

    return render_template('learners/assign.html', courses=courses)


# --- LEARNER PORTAL FLOWS ---

@learners_bp.route('/portal')
def my_portal():
    learner_id = session.get('learner_id')
    if not learner_id:
        flash("Please log in with your Global ID.", "info")
        return redirect(url_for('auth.learner_login'))

    learner = Learner.query.get_or_404(learner_id)
    enrollments = LearnerEnrollment.query.filter_by(learner_id=learner.id).all()
    all_courses = Course.query.all()
    
    from app.models.notification import LearnerNotification
    notifications = LearnerNotification.query.filter_by(learner_id=learner.id).order_by(LearnerNotification.created_at.desc()).all()
    
    return render_template(
        'learner_portal/portal.html',
        learner=learner,
        enrollments=enrollments,
        all_courses=all_courses,
        notifications=notifications
    )


@learners_bp.route('/notifications/mark_read/<int:notif_id>', methods=['POST'])
def mark_notification_read(notif_id):
    learner_id = session.get('learner_id')
    if not learner_id:
        return jsonify({'status': 'error'}), 401
    
    from app.models.notification import LearnerNotification
    if notif_id == 0:
        # Mark all as read
        notifications = LearnerNotification.query.filter_by(learner_id=learner_id, is_read=False).all()
        for n in notifications:
            n.is_read = True
    else:
        notif = LearnerNotification.query.filter_by(id=notif_id, learner_id=learner_id).first()
        if notif:
            notif.is_read = True
    
    db.session.commit()
    return jsonify({'status': 'success'})


@learners_bp.route('/class_flow/<class_id_str>')
def class_flow(class_id_str):
    """
    LIVE COURSE FLOW:
    QR -> Login -> Attendance Auto-recorded -> Pre Assessment -> Training / Google Meet -> Post Assessment -> Downloads -> Feedback
    """
    learner_id = session.get('learner_id')
    if not learner_id:
        return redirect(url_for('auth.learner_login', classId=class_id_str))

    learner = Learner.query.get_or_404(learner_id)
    live_class = LiveClass.query.filter_by(class_id=class_id_str).first_or_404()
    course = live_class.course

    is_expired = (live_class.class_date < datetime.utcnow().date()) or live_class.is_locked

    # 1. Automatic Attendance Recording upon scanning QR & logging in (only if class not expired)
    att = Attendance.query.filter_by(class_id=live_class.id, learner_id=learner.id).first()
    if not att and not is_expired:
        att = Attendance(
            class_id=live_class.id,
            learner_id=learner.id,
            status='Present',
            recorded_via='QR'
        )
        db.session.add(att)

    # Find or create enrollment
    enrollment = LearnerEnrollment.query.filter_by(learner_id=learner.id, course_id=course.id, class_id=live_class.id).first()
    if not enrollment:
        enrollment = LearnerEnrollment(
            learner_id=learner.id,
            course_id=course.id,
            class_id=live_class.id,
            completion_status='In Progress'
        )
        db.session.add(enrollment)
    db.session.commit()

    # Pre and Post attempts & Pre questions check
    has_pre_questions = CourseAssessment.query.filter((CourseAssessment.course_id == course.id) & (CourseAssessment.assessment_type.in_(['PRE', 'LESSON_PRE']))).count() > 0
    pre_attempt = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == enrollment.id) & (AssessmentAttempt.assessment_type.in_(['PRE', 'LESSON_PRE']))).order_by(AssessmentAttempt.id.desc()).first()
    post_attempt = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == enrollment.id) & (AssessmentAttempt.assessment_type.in_(['POST', 'LESSON_POST']))).order_by(AssessmentAttempt.id.desc()).first()
    feedback_resp = FeedbackResponse.query.filter_by(class_id=live_class.id, learner_id=learner.id).first()
    cert = Certificate.query.filter_by(learner_id=learner.id, course_id=course.id).first()

    return render_template(
        'learner_portal/class_flow.html',
        learner=learner,
        live_class=live_class,
        course=course,
        enrollment=enrollment,
        attendance=att,
        is_expired=is_expired,
        has_pre_questions=has_pre_questions,
        pre_attempt=pre_attempt,
        post_attempt=post_attempt,
        feedback_resp=feedback_resp,
        certificate=cert
    )


@learners_bp.route('/self_paced_flow/<course_id_str>')
def self_paced_flow(course_id_str):
    """
    SELF PACED COURSE FLOW:
    Pre Assessment (if created) -> Lessons & Courseware -> Course End Assessment -> Certificate
    """
    learner_id = session.get('learner_id')
    if not learner_id:
        return redirect(url_for('auth.learner_login', courseId=course_id_str))

    learner = Learner.query.get_or_404(learner_id)
    course = Course.query.filter_by(course_id=course_id_str).first_or_404()

    enrollment = LearnerEnrollment.query.filter_by(learner_id=learner.id, course_id=course.id).first()
    if not enrollment:
        enrollment = LearnerEnrollment(
            learner_id=learner.id,
            course_id=course.id,
            completion_status='In Progress'
        )
        db.session.add(enrollment)
        db.session.commit()

    has_pre_questions = CourseAssessment.query.filter_by(course_id=course.id, assessment_type='PRE').count() > 0
    pre_attempt = AssessmentAttempt.query.filter_by(enrollment_id=enrollment.id, assessment_type='PRE').first()
    post_attempt = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == enrollment.id) & (AssessmentAttempt.assessment_type.in_(['POST', 'LESSON_POST']))).order_by(AssessmentAttempt.id.desc()).first()
    course_end_attempt = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == enrollment.id) & (AssessmentAttempt.assessment_type == 'COURSE_END')).order_by(AssessmentAttempt.id.desc()).first()

    all_attempts = AssessmentAttempt.query.filter_by(enrollment_id=enrollment.id).order_by(AssessmentAttempt.id.asc()).all()
    lesson_pre_attempts = {}
    lesson_post_attempts = {}
    for att in all_attempts:
        if att.assessment_type == 'LESSON_PRE':
            if att.lesson_id is not None:
                lesson_pre_attempts[att.lesson_id] = att
            elif att.lesson_number is not None:
                lesson_pre_attempts[att.lesson_number] = att
        elif att.assessment_type == 'LESSON_POST':
            if att.lesson_id is not None:
                lesson_post_attempts[att.lesson_id] = att
            elif att.lesson_number is not None:
                lesson_post_attempts[att.lesson_number] = att

    reviewed_reviews = LessonReview.query.filter_by(enrollment_id=enrollment.id).all()
    reviewed_lesson_ids = [r.lesson_id for r in reviewed_reviews]

    completed_lesson_ids = set()
    for les in course.lessons:
        has_les_post = CourseAssessment.query.filter_by(course_id=course.id, lesson_id=les.id, assessment_type='LESSON_POST').count() > 0
        post_att = lesson_post_attempts.get(les.id) or lesson_post_attempts.get(les.lesson_number)
        
        is_cw_reviewed = les.id in reviewed_lesson_ids
        if has_les_post:
            if post_att and post_att.passed:
                completed_lesson_ids.add(les.id)
        elif is_cw_reviewed:
            completed_lesson_ids.add(les.id)

    feedback_repo = course.feedback_repository or FeedbackRepository.query.first()
    feedback_resp = None
    if feedback_repo:
        feedback_resp = FeedbackResponse.query.filter_by(repo_id=feedback_repo.id, learner_id=learner.id).first()

    cert = Certificate.query.filter_by(learner_id=learner.id, course_id=course.id).first()

    return render_template(
        'learner_portal/self_paced_flow.html',
        learner=learner,
        course=course,
        enrollment=enrollment,
        has_pre_questions=has_pre_questions,
        pre_attempt=pre_attempt,
        post_attempt=post_attempt,
        course_end_attempt=course_end_attempt,
        lesson_pre_attempts=lesson_pre_attempts,
        lesson_post_attempts=lesson_post_attempts,
        reviewed_lesson_ids=reviewed_lesson_ids,
        completed_lesson_ids=completed_lesson_ids,
        feedback_repo=feedback_repo,
        feedback_resp=feedback_resp,
        certificate=cert
    )


@learners_bp.route('/record_courseware_time/<int:lesson_id>', methods=['POST'])
def record_courseware_time(lesson_id):
    learner_id = session.get('learner_id')
    if not learner_id:
        return jsonify({'status': 'error', 'message': 'Not authenticated'}), 401

    lesson = CourseLesson.query.get_or_404(lesson_id)
    course = Course.query.get_or_404(lesson.course_id)
    enrollment = LearnerEnrollment.query.filter_by(learner_id=learner_id, course_id=course.id).first()
    if enrollment:
        existing = LessonReview.query.filter_by(enrollment_id=enrollment.id, lesson_id=lesson.id).first()
        if not existing:
            review = LessonReview(enrollment_id=enrollment.id, lesson_id=lesson.id)
            db.session.add(review)
            db.session.commit()
        return jsonify({'status': 'success', 'unlocked': True, 'lesson_id': lesson_id})
    return jsonify({'status': 'error', 'message': 'Enrollment not found'}), 404


@learners_bp.route('/take_assessment/<course_id>/<assessment_type>', methods=['GET', 'POST'])
def take_assessment(course_id, assessment_type):
    learner_id = session.get('learner_id')
    if not learner_id:
        return redirect(url_for('auth.learner_login'))

    learner = Learner.query.get_or_404(learner_id)
    
    # Dual lookup: support both integer ID (e.g. 1) and public string course_id (e.g. CRS-000001)
    if str(course_id).isdigit():
        course = Course.query.get(int(course_id)) or Course.query.filter_by(course_id=str(course_id)).first_or_404()
    else:
        course = Course.query.filter_by(course_id=str(course_id)).first_or_404()
    
    class_id_str = request.args.get('class_id')
    lesson_id_param = request.args.get('lesson_id')
    live_class = LiveClass.query.filter_by(class_id=class_id_str).first() if class_id_str else None

    enrollment = LearnerEnrollment.query.filter_by(learner_id=learner.id, course_id=course.id).first()
    if not enrollment:
        enrollment = LearnerEnrollment(learner_id=learner.id, course_id=course.id, class_id=live_class.id if live_class else None)
        db.session.add(enrollment)
        db.session.commit()

    # Determine if this is strictly the final Course End Assessment
    type_upper = assessment_type.upper()
    is_course_end = (type_upper == 'COURSE_END')

    # Check attempt limits and lesson completion strictly ONLY for Course End Assessment (max 3 attempts)
    if course.mode == 'Self Paced' and is_course_end:
        reviewed_reviews = LessonReview.query.filter_by(enrollment_id=enrollment.id).all()
        reviewed_lesson_ids = [r.lesson_id for r in reviewed_reviews]
        
        all_completed = True
        for les in course.lessons:
            has_les_post = CourseAssessment.query.filter_by(course_id=course.id, lesson_id=les.id, assessment_type='LESSON_POST').count() > 0
            post_att = AssessmentAttempt.query.filter((AssessmentAttempt.enrollment_id == enrollment.id) & (AssessmentAttempt.assessment_type.in_(['LESSON_POST', 'POST'])) & ((AssessmentAttempt.lesson_id == les.id) | (AssessmentAttempt.lesson_number == les.lesson_number)) & (AssessmentAttempt.passed == True)).first()
            is_cw_reviewed = les.id in reviewed_lesson_ids
            
            les_done = bool(post_att) if has_les_post else is_cw_reviewed
            if not les_done:
                all_completed = False
                break
                
        if not all_completed:
            flash("Course End Assessment is locked. You must complete all lessons and post-assessments first.", "warning")
            return redirect(url_for('learners.self_paced_flow', course_id_str=course.course_id))

        if enrollment.attempts_count >= 3 and not (enrollment.final_score and enrollment.final_score >= course.pass_percentage):
            flash("Maximum attempt limit (3 attempts) reached for the Course End Assessment.", "danger")
            return redirect(url_for('learners.self_paced_flow', course_id_str=course.course_id))

    # Ensure courseware is reviewed before taking Post-Assessment
    if 'POST' in type_upper:
        target_les_id = int(lesson_id_param) if lesson_id_param else (course.lessons[0].id if course.lessons else None)
        if target_les_id:
            rev = LessonReview.query.filter_by(enrollment_id=enrollment.id, lesson_id=target_les_id).first()
            if not rev:
                flash("You must review and complete the uploading courseware before attempting the Post-Assessment.", "warning")
                return redirect(url_for('learners.self_paced_flow', course_id_str=course.course_id))

    # Query questions: filter by course_id and matching assessment_type
    query = CourseAssessment.query.filter_by(course_id=course.id)
    if lesson_id_param:
        query = query.filter_by(lesson_id=int(lesson_id_param))
        if 'PRE' in type_upper:
            query = query.filter(CourseAssessment.assessment_type.in_(['LESSON_PRE', 'PRE']))
        else:
            query = query.filter(CourseAssessment.assessment_type.in_(['LESSON_POST', 'POST']))
    else:
        if type_upper in ['PRE', 'LESSON_PRE']:
            # First try course-level PRE assessments
            pre_count = CourseAssessment.query.filter_by(course_id=course.id, assessment_type='PRE').count()
            if pre_count > 0:
                query = query.filter_by(assessment_type='PRE')
            else:
                # If only lesson-level PRE assessments exist, isolate first lesson to prevent multi-lesson duplicates
                first_lesson = CourseLesson.query.filter_by(course_id=course.id).order_by(CourseLesson.lesson_number.asc()).first()
                if first_lesson:
                    query = query.filter((CourseAssessment.lesson_id == first_lesson.id) & (CourseAssessment.assessment_type.in_(['PRE', 'LESSON_PRE'])))
                else:
                    query = query.filter(CourseAssessment.assessment_type.in_(['PRE', 'LESSON_PRE']))
        elif is_course_end:
            query = query.filter(CourseAssessment.assessment_type == 'COURSE_END')
        else:
            first_lesson = CourseLesson.query.filter_by(course_id=course.id).order_by(CourseLesson.lesson_number.asc()).first()
            if first_lesson:
                query = query.filter((CourseAssessment.lesson_id == first_lesson.id) & (CourseAssessment.assessment_type.in_(['POST', 'LESSON_POST'])))
            else:
                query = query.filter(CourseAssessment.assessment_type.in_(['POST', 'LESSON_POST']))

    raw_questions = query.order_by(CourseAssessment.serial_number.asc(), CourseAssessment.id.asc()).all()

    # Deduplicate questions by question text to ensure no repeated questions appear
    seen_texts = set()
    questions = []
    for q in raw_questions:
        norm_text = (q.question or '').strip().lower()
        if norm_text not in seen_texts:
            seen_texts.add(norm_text)
            questions.append(q)

    # Fallback: if specific lesson query yielded no questions, filter broadly by type without mixing types
    if not questions:
        if type_upper in ['PRE', 'LESSON_PRE']:
            raw_fallback = CourseAssessment.query.filter((CourseAssessment.course_id == course.id) & (CourseAssessment.assessment_type.in_(['PRE', 'LESSON_PRE']))).order_by(CourseAssessment.serial_number.asc()).all()
        elif is_course_end:
            raw_fallback = CourseAssessment.query.filter((CourseAssessment.course_id == course.id) & (CourseAssessment.assessment_type.in_(['COURSE_END', 'POST']))).order_by(CourseAssessment.serial_number.asc()).all()
        else:
            raw_fallback = []
        
        seen_texts_fb = set()
        for q in raw_fallback:
            norm_text = (q.question or '').strip().lower()
            if norm_text not in seen_texts_fb:
                seen_texts_fb.add(norm_text)
                questions.append(q)

    if request.method == 'POST':
        user_answers = request.form.to_dict()
        score_pct, passed, total, correct = evaluate_assessment(questions, user_answers, pass_percentage=course.pass_percentage)

        if type_upper in ['PRE', 'LESSON_PRE']:
            passed = True

        if is_course_end:
            enrollment.attempts_count += 1
            attempt_num = enrollment.attempts_count
        else:
            attempt_num = AssessmentAttempt.query.filter_by(enrollment_id=enrollment.id, assessment_type=type_upper).count() + 1

        les_id_val = int(lesson_id_param) if lesson_id_param and str(lesson_id_param).isdigit() else None
        les_obj_val = CourseLesson.query.get(les_id_val) if les_id_val else None
        les_num_val = les_obj_val.lesson_number if les_obj_val else 1

        attempt = AssessmentAttempt(
            enrollment_id=enrollment.id,
            assessment_type=type_upper,
            score_percentage=score_pct,
            passed=passed,
            attempt_number=attempt_num,
            lesson_id=les_id_val,
            lesson_number=les_num_val
        )
        db.session.add(attempt)

        if is_course_end:
            enrollment.final_score = score_pct
            if not passed:
                if enrollment.attempts_count >= 3:
                    enrollment.completion_status = 'Failed'

        db.session.commit()

        if is_course_end:
            if passed:
                flash(f"Congratulations! You passed the Course-End Assessment with {score_pct}% ({correct}/{total}). Please submit the Course Feedback form below to complete your course and receive your certificate!", "success")
            else:
                flash(f"Course-End Assessment score: {score_pct}% ({correct}/{total}). Pass mark is {course.pass_percentage}%. Attempts remaining: {max(0, 3 - enrollment.attempts_count)}.", "warning" if enrollment.attempts_count < 3 else "danger")
        else:
            flash(f"{type_upper.replace('_', ' ')} Assessment completed! Your score: {score_pct}% ({correct}/{total}).", "success")

        if live_class:
            return redirect(url_for('learners.class_flow', class_id_str=live_class.class_id))
        else:
            return redirect(url_for('learners.self_paced_flow', course_id_str=course.course_id))

    return render_template(
        'learner_portal/assessment.html',
        course=course,
        assessment_type=assessment_type,
        questions=questions,
        live_class=live_class
    )


@learners_bp.route('/submit_feedback/<int:repo_id>', methods=['GET', 'POST'])
def submit_feedback(repo_id):
    learner_id = session.get('learner_id')
    if not learner_id:
        return redirect(url_for('auth.learner_login'))

    repo = FeedbackRepository.query.get_or_404(repo_id)
    class_id_str = request.args.get('class_id')
    course_id_param = request.args.get('course_id')

    live_class = None
    if class_id_str:
        if str(class_id_str).isdigit():
            live_class = LiveClass.query.get(int(class_id_str))
        if not live_class:
            live_class = LiveClass.query.filter_by(class_id=class_id_str).first()

    course = None
    enrollment = None

    if live_class:
        course = live_class.course
        enrollment = LearnerEnrollment.query.filter_by(learner_id=learner_id, course_id=course.id, class_id=live_class.id).first()
        if not enrollment:
            enrollment = LearnerEnrollment.query.filter_by(learner_id=learner_id, course_id=course.id).first()
    elif course_id_param:
        if str(course_id_param).isdigit():
            course = Course.query.get(int(course_id_param))
        if not course:
            course = Course.query.filter_by(course_id=course_id_param).first()
        if course:
            enrollment = LearnerEnrollment.query.filter_by(learner_id=learner_id, course_id=course.id).first()
    else:
        # Fallback to course linked to repo
        course = Course.query.filter_by(feedback_repo_id=repo.id).first()
        if course:
            enrollment = LearnerEnrollment.query.filter_by(learner_id=learner_id, course_id=course.id).first()

    # Auto-seed default feedback questions if repo has no questions defined
    questions = FeedbackQuestion.query.filter_by(repo_id=repo.id).all()
    if not questions:
        q1 = FeedbackQuestion(repo_id=repo.id, question_text='How would you rate the overall quality of the course content?', question_type='MCQ', options_json=json.dumps(["Excellent", "Good", "Average", "Poor"]))
        q2 = FeedbackQuestion(repo_id=repo.id, question_text='Was the trainer / facilitation clear and engaging?', question_type='MCQ', options_json=json.dumps(["Strongly Agree", "Agree", "Neutral", "Disagree"]))
        q3 = FeedbackQuestion(repo_id=repo.id, question_text='Please share any additional comments or suggestions for improvement.', question_type='Text')
        db.session.add_all([q1, q2, q3])
        db.session.commit()
        questions = [q1, q2, q3]

    if request.method == 'POST':
        resp_dict = request.form.to_dict()

        existing_resp = FeedbackResponse.query.filter_by(
            repo_id=repo.id,
            learner_id=learner_id,
            class_id=live_class.id if live_class else None
        ).first()

        if existing_resp:
            existing_resp.responses_json = json.dumps(resp_dict)
            existing_resp.submitted_at = datetime.utcnow()
        else:
            fb_resp = FeedbackResponse(
                repo_id=repo.id,
                class_id=live_class.id if live_class else None,
                learner_id=learner_id,
                responses_json=json.dumps(resp_dict)
            )
            db.session.add(fb_resp)

        # Trigger Course Completion & Certificate Generation ONLY ON FEEDBACK SUBMISSION
        if enrollment:
            enrollment.completion_status = 'Completed'
            enrollment.completion_date = datetime.utcnow()

            # Trigger automated Learning Wall post for course completion
            if course:
                try:
                    create_completion_post(learner_id, course.id, final_score=enrollment.final_score)
                except Exception:
                    pass

            # Check if certificate exists/is enabled for this course
            has_cert = getattr(course, 'has_certificate', True) if course else True
            if has_cert and course:
                existing_cert = Certificate.query.filter_by(learner_id=learner_id, course_id=course.id).first()
                if not existing_cert:
                    cert_id = Certificate.generate_certificate_id()
                    cert_filename = f"cert_{cert_id}.pdf"
                    cert_file_path = os.path.join(learners_bp.root_path, '..', '..', 'uploads', 'certificates', cert_filename)
                    os.makedirs(os.path.dirname(cert_file_path), exist_ok=True)

                    learner_obj = Learner.query.get(learner_id)
                    date_str = datetime.now().strftime('%d-%b-%Y')
                    try:
                        generate_certificate_pdf(learner_obj.name, course.name, date_str, cert_id, cert_file_path)
                    except Exception:
                        pass

                    cert = Certificate(
                        certificate_id=cert_id,
                        learner_id=learner_id,
                        course_id=course.id,
                        pdf_filename=cert_filename
                    )
                    db.session.add(cert)
                    flash("Thank you! Feedback recorded. Your course is marked as COMPLETED and Certificate generated!", "success")
                else:
                    flash("Thank you! Feedback recorded. Your course is marked as COMPLETED!", "success")
            else:
                flash("Thank you! Feedback recorded. Your course is marked as COMPLETED!", "success")

        db.session.commit()

        if live_class:
            return redirect(url_for('learners.class_flow', class_id_str=live_class.class_id))
        elif course:
            return redirect(url_for('learners.self_paced_flow', course_id_str=course.course_id))
        else:
            return redirect(url_for('learners.my_portal'))

    existing_resp = FeedbackResponse.query.filter_by(
        repo_id=repo.id,
        learner_id=learner_id,
        class_id=live_class.id if live_class else None
    ).first()

    saved_responses = {}
    if existing_resp and existing_resp.responses_json:
        try:
            saved_responses = json.loads(existing_resp.responses_json)
        except Exception:
            saved_responses = {}

    return render_template(
        'learner_portal/feedback.html',
        repo=repo,
        questions=questions,
        live_class=live_class,
        course=course,
        saved_responses=saved_responses,
        is_submitted=bool(existing_resp)
    )


@learners_bp.route('/scorm/progress', methods=['POST'])
def save_scorm_progress():
    learner_id = session.get('learner_id')
    if not learner_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401

    data = request.get_json() or {}
    lesson_id = data.get('lesson_id')
    status = data.get('status', '').lower() # 'completed', 'passed', 'failed'

    if not lesson_id:
        return jsonify({'status': 'error', 'message': 'Missing lesson_id'}), 400

    lesson = CourseLesson.query.get_or_404(lesson_id)

    if status in ['completed', 'passed']:
        rev = LessonReview.query.filter_by(learner_id=learner_id, lesson_id=lesson.id).first()
        if not rev:
            rev = LessonReview(
                learner_id=learner_id,
                lesson_id=lesson.id,
                course_id=lesson.course_id,
                time_spent_seconds=600
            )
            db.session.add(rev)
            db.session.commit()

    return jsonify({'status': 'success', 'lesson_id': lesson.id, 'scorm_status': status})

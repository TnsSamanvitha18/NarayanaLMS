import os
import uuid
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file, current_app
from app.models import db
from app.models.course import Course, CourseAssessment, CourseMaterial, CourseLesson, LessonCourseware
from app.models.live_class import LiveClass
from app.services.assessment_service import parse_assessment_csv
from app.services.report_service import generate_course_analytics_csv, generate_class_attendance_csv
from app.utils.pptx_parser import parse_pptx_slides
from app.utils.slide_renderer import render_pdf_to_slide_images

courses_bp = Blueprint('courses', __name__)

def check_admin():
    return session.get('admin_logged_in')

def format_youtube_embed(url):
    if not url:
        return url
    if 'youtube.com/watch?v=' in url:
        video_id = url.split('v=')[1].split('&')[0]
        return f"https://www.youtube.com/embed/{video_id}"
    elif 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[1].split('?')[0]
        return f"https://www.youtube.com/embed/{video_id}"
    return url

@courses_bp.route('/')
def list_courses():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    search_query = request.args.get('search', '').strip()
    mode_filter = request.args.get('mode', '').strip()

    query = Course.query

    if search_query:
        query = query.filter(
            (Course.name.ilike(f'%{search_query}%')) |
            (Course.course_id.ilike(f'%{search_query}%')) |
            (Course.description.ilike(f'%{search_query}%')) |
            (Course.mode.ilike(f'%{search_query}%'))
        )

    if mode_filter and mode_filter != 'ALL':
        query = query.filter_by(mode=mode_filter)

    courses = query.order_by(Course.id.desc()).all()
    return render_template('courses/list.html', courses=courses, search_query=search_query, mode_filter=mode_filter)


@courses_bp.route('/create', methods=['GET', 'POST'])
def create_course():
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        mode = request.form.get('mode', 'Live').strip()
        pass_percentage = float(request.form.get('pass_percentage', 80.0))
        fb_id = request.form.get('feedback_repo_id')
        feedback_repo_id = int(fb_id) if fb_id else None
        has_certificate = (request.form.get('has_certificate', '1') == '1')
        is_sequential = (request.form.get('is_sequential', '1') == '1')
        comp_date_str = request.form.get('completion_date', '').strip()
        completion_date = None
        if comp_date_str:
            try:
                completion_date = datetime.strptime(comp_date_str, '%Y-%m-%d')
            except Exception:
                completion_date = None

        if not name:
            flash('Course Name is required.', 'danger')
            return redirect(url_for('courses.create_course'))

        course_id = Course.generate_course_id()
        new_course = Course(
            course_id=course_id,
            name=name,
            duration_hours=0.0, # Auto-calculated when lessons are added
            description=description,
            mode=mode,
            pass_percentage=pass_percentage,
            feedback_repo_id=feedback_repo_id,
            has_certificate=has_certificate,
            is_sequential=is_sequential,
            completion_date=completion_date
        )
        db.session.add(new_course)
        db.session.commit()

        # Handle Thumbnail Upload
        thumb_file = request.files.get('thumbnail_file')
        if thumb_file and thumb_file.filename:
            ext = os.path.splitext(thumb_file.filename)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                thumb_filename = f"thumb_{new_course.course_id}_{uuid.uuid4().hex[:8]}{ext}"
                thumb_dir = os.path.join(current_app.root_path, '..', 'uploads', 'thumbnails')
                os.makedirs(thumb_dir, exist_ok=True)
                thumb_file.save(os.path.join(thumb_dir, thumb_filename))
                new_course.thumbnail_filename = thumb_filename

        # Live Online duration set directly by admin at course level
        if mode == 'Live Online':
            try:
                new_course.duration_hours = float(request.form.get('duration_hours', 1.0))
            except Exception:
                new_course.duration_hours = 1.0

        # Handle CSV uploads enforcing mode-based assessment availability
        summative_file = request.files.get('summative_assessment_csv') or request.files.get('course_end_assessment_csv')
        pre_file = request.files.get('pre_assessment_csv')
        post_file = request.files.get('post_assessment_csv')

        summative_errs, pre_errs, post_errs = [], [], []

        # 1. Course End Assessment ONLY available for Self Paced courses
        if mode == 'Self Paced' and summative_file and summative_file.filename:
            q_list, errs = parse_assessment_csv(summative_file.stream, filename=summative_file.filename)
            if errs:
                summative_errs = errs
            else:
                for q in q_list:
                    assessment = CourseAssessment(
                        course_id=new_course.id,
                        assessment_type='COURSE_END',
                        serial_number=q['serial_number'],
                        question=q['question'],
                        option1=q['option1'],
                        option2=q['option2'],
                        option3=q['option3'],
                        option4=q['option4'],
                        correct_option=q['correct_option']
                    )
                    db.session.add(assessment)

        # 2. Pre and Post Assessments ONLY available for Live In Person / Live Online courses
        if mode != 'Self Paced':
            if pre_file and pre_file.filename:
                q_list, errs = parse_assessment_csv(pre_file.stream, filename=pre_file.filename)
                if errs:
                    pre_errs = errs
                else:
                    for q in q_list:
                        assessment = CourseAssessment(
                            course_id=new_course.id,
                            assessment_type='PRE',
                            serial_number=q['serial_number'],
                            question=q['question'],
                            option1=q['option1'],
                            option2=q['option2'],
                            option3=q['option3'],
                            option4=q['option4'],
                            correct_option=q['correct_option']
                        )
                        db.session.add(assessment)

            if post_file and post_file.filename:
                q_list, errs = parse_assessment_csv(post_file.stream, filename=post_file.filename)
                if errs:
                    post_errs = errs
                else:
                    for q in q_list:
                        assessment = CourseAssessment(
                            course_id=new_course.id,
                            assessment_type='POST',
                            serial_number=q['serial_number'],
                            question=q['question'],
                            option1=q['option1'],
                            option2=q['option2'],
                            option3=q['option3'],
                            option4=q['option4'],
                            correct_option=q['correct_option']
                        )
                        db.session.add(assessment)

        db.session.commit()

        if summative_errs or pre_errs or post_errs:
            flash(f"Course created ({course_id}), but CSV had errors: Summative ({len(summative_errs)}), Pre ({len(pre_errs)}), Post ({len(post_errs)}).", "warning")
        else:
            flash(f"Course {course_id} - {name} created successfully!", "success")

        return redirect(url_for('courses.view_course', course_id=new_course.id))

    from app.models.feedback import FeedbackRepository
    feedback_repos = FeedbackRepository.query.all()
    auto_id = Course.generate_course_id()
    return render_template('courses/create_edit.html', auto_id=auto_id, course=None, feedback_repos=feedback_repos)


@courses_bp.route('/<int:course_id>')
def view_course(course_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    pre_questions = CourseAssessment.query.filter_by(course_id=course.id, assessment_type='PRE').order_by(CourseAssessment.serial_number.asc()).all()
    post_questions = CourseAssessment.query.filter_by(course_id=course.id, assessment_type='POST').order_by(CourseAssessment.serial_number.asc()).all()
    course_end_questions = CourseAssessment.query.filter((CourseAssessment.course_id == course.id) & (CourseAssessment.assessment_type == 'COURSE_END')).order_by(CourseAssessment.serial_number.asc()).all()
    
    # Lessons created inside this course
    lessons = CourseLesson.query.filter_by(course_id=course.id).order_by(CourseLesson.lesson_number.asc()).all()

    # Classes created inside this course
    from app.models.live_class import LiveClass
    from app.models.feedback import FeedbackRepository
    from app.services.qr_service import generate_class_qr

    live_classes = LiveClass.query.filter_by(course_id=course.id).order_by(LiveClass.class_date.desc()).all()
    
    for cls in live_classes:
        generate_class_qr(cls.class_id)

    feedback_repos = FeedbackRepository.query.all()

    return render_template(
        'courses/detail.html',
        course=course,
        pre_questions=pre_questions,
        post_questions=post_questions,
        course_end_questions=course_end_questions,
        lessons=lessons,
        live_classes=live_classes,
        feedback_repos=feedback_repos
    )


def recalculate_course_duration(course_id):
    course = Course.query.get(course_id)
    if course and course.mode != 'Live Online':
        lessons = CourseLesson.query.filter_by(course_id=course.id).all()
        if lessons:
            course.duration_hours = round(sum(l.duration_hours for l in lessons if l.duration_hours is not None), 2)
        else:
            course.duration_hours = 0.0
        db.session.commit()


@courses_bp.route('/thumbnail/<filename>')
def download_thumbnail(filename):
    thumb_dir = os.path.join(current_app.root_path, '..', 'uploads', 'thumbnails')
    file_path = os.path.join(thumb_dir, filename)
    if os.path.exists(file_path):
        return send_file(file_path)
    return redirect(url_for('static', filename='images/default_course_thumb.png'))


@courses_bp.route('/<int:course_id>/add_lesson', methods=['POST'])
def add_lesson(course_id):
    """
    Add a new Lesson / Module directly inside a Course in a single step,
    including optional Lesson Pre-Assessment CSV, Non-Downloadable Courseware, and Post-Assessment CSV.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    title = request.form.get('title', '').strip()
    summary = request.form.get('summary', '').strip()
    content = request.form.get('content', '').strip()
    video_url = request.form.get('video_url', '').strip()
    lesson_number = int(request.form.get('lesson_number', len(course.lessons) + 1))
    duration_hours = float(request.form.get('duration_hours', 1.0))
    min_time_minutes = float(request.form.get('min_time_minutes', 1.0))
    deadline_str = request.form.get('deadline', '').strip()
    deadline = None
    if deadline_str:
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
        except Exception:
            deadline = None

    if not title:
        flash("Lesson title is required.", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    cw_type = request.form.get('courseware_type', 'Video URL').strip()
    external_url = request.form.get('external_url', '').strip() or request.form.get('video_url', '').strip()
    if external_url:
        from app.services.gdrive_service import parse_gdrive_url
        is_gd, emb_url, g_type, file_id = parse_gdrive_url(external_url)
        if is_gd:
            external_url = emb_url
            if cw_type in ['Auto', 'Video URL', 'Google Drive', '']:
                cw_type = f"Google Drive ({g_type})"
        else:
            external_url = format_youtube_embed(external_url)

    lesson = CourseLesson(
        course_id=course.id,
        lesson_number=lesson_number,
        title=title,
        summary=summary,
        content=content,
        video_url=None,
        duration_hours=duration_hours,
        min_time_minutes=min_time_minutes,
        deadline=deadline
    )
    db.session.add(lesson)
    db.session.flush() # Generate lesson.id

    # 1. Handle Lesson Pre-Assessment CSV
    pre_csv = request.files.get('pre_assessment_csv')
    if pre_csv and pre_csv.filename:
        q_list, errs = parse_assessment_csv(pre_csv.stream, filename=pre_csv.filename)
        if not errs:
            for q in q_list:
                ass = CourseAssessment(
                    course_id=course.id,
                    lesson_id=lesson.id,
                    assessment_type='LESSON_PRE',
                    serial_number=q['serial_number'],
                    question=q['question'],
                    option1=q['option1'],
                    option2=q['option2'],
                    option3=q['option3'],
                    option4=q['option4'],
                    correct_option=q['correct_option'],
                    lesson_number=lesson_number
                )
                db.session.add(ass)

    # 2. Handle Non-Downloadable Lesson Courseware File / Text / Video URL
    cw_file = request.files.get('courseware_file')
    cw_title = request.form.get('courseware_title', '').strip() or f"{title} Courseware"
    cw_text = request.form.get('courseware_text', '').strip()

    filename = None
    if cw_file and cw_file.filename:
        ext = os.path.splitext(cw_file.filename)[1].lower()
        short_id = uuid.uuid4().hex[:8]
        filename = f"cw_{lesson.id}_{short_id}{ext}"
        save_path = os.path.join(current_app.config['MATERIALS_FOLDER'], filename)
        cw_file.save(save_path)

        mat = CourseMaterial(
            course_id=course.id,
            title=f"[Lesson {lesson_number}] {cw_title}",
            material_type='Video' if ext in ['.mp4', '.webm'] else ('PDF' if ext == '.pdf' else 'PPT'),
            filename=filename,
            allow_download=False # Non-downloadable
        )
        db.session.add(mat)

    if filename or cw_text or external_url:
        cw = LessonCourseware(
            lesson_id=lesson.id,
            title=cw_title,
            courseware_type=cw_type,
            filename=filename,
            external_url=external_url if external_url else None,
            content_text=cw_text if cw_text else None
        )
        db.session.add(cw)

    # 3. Handle Lesson Post-Assessment CSV
    post_csv = request.files.get('post_assessment_csv')
    if post_csv and post_csv.filename:
        q_list, errs = parse_assessment_csv(post_csv.stream, filename=post_csv.filename)
        if not errs:
            for q in q_list:
                ass = CourseAssessment(
                    course_id=course.id,
                    lesson_id=lesson.id,
                    assessment_type='LESSON_POST',
                    serial_number=q['serial_number'],
                    question=q['question'],
                    option1=q['option1'],
                    option2=q['option2'],
                    option3=q['option3'],
                    option4=q['option4'],
                    correct_option=q['correct_option'],
                    lesson_number=lesson_number
                )
                db.session.add(ass)

    # Notify enrolled learners about new/updated lesson
    from app.models.notification import LearnerNotification
    for en in course.enrollments:
        notif = LearnerNotification(
            learner_id=en.learner_id,
            course_id=course.id,
            lesson_id=lesson.id,
            title=f"Lesson Updated: {title}",
            message=f"Lesson #{lesson_number} '{title}' has been added/updated in '{course.name}'.",
            notification_type='LESSON_UPDATED'
        )
        db.session.add(notif)

    db.session.commit()
    recalculate_course_duration(course.id)

    flash(f"Lesson #{lesson_number} '{title}' ({duration_hours} hrs) created and course total duration auto-updated!", "success")
    return redirect(url_for('courses.view_course', course_id=course.id))


@courses_bp.route('/<int:course_id>/clear_lessons', methods=['POST'])
def clear_lessons(course_id):
    """
    Admin Route: Remove all existing lessons for a course.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    # Remove all lessons (cascades courseware & lesson assessments)
    CourseLesson.query.filter_by(course_id=course.id).delete()
    db.session.commit()
    recalculate_course_duration(course.id)

    flash(f"All existing lessons cleared for course '{course.name}'.", "info")
    return redirect(url_for('courses.view_course', course_id=course.id))


@courses_bp.route('/lesson/<int:lesson_id>/delete', methods=['POST'])
def delete_lesson(lesson_id):
    """
    Admin Route: Delete an individual lesson and all its attached courseware & assessments.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    lesson = CourseLesson.query.get_or_404(lesson_id)
    course_id = lesson.course_id
    lesson_title = lesson.title
    
    # Delete linked assessments and courseware
    CourseAssessment.query.filter_by(lesson_id=lesson.id).delete()
    LessonCourseware.query.filter_by(lesson_id=lesson.id).delete()
    db.session.delete(lesson)
    db.session.commit()
    recalculate_course_duration(course_id)

    flash(f"Lesson '{lesson_title}' deleted and course total duration auto-updated.", "success")
    return redirect(url_for('courses.view_course', course_id=course_id))


@courses_bp.route('/lesson/<int:lesson_id>/add_courseware', methods=['POST'])
def add_lesson_courseware(lesson_id):
    """
    Attach Non-Downloadable Courseware (Video, PDF view, PPT slides, SCORM, Text) to a Lesson.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    lesson = CourseLesson.query.get_or_404(lesson_id)
    title = request.form.get('title', '').strip()
    c_type = request.form.get('courseware_type', 'Video URL').strip()
    external_url = request.form.get('external_url', '').strip()
    if external_url:
        from app.services.gdrive_service import parse_gdrive_url
        is_gd, emb_url, g_type, file_id = parse_gdrive_url(external_url)
        if is_gd:
            external_url = emb_url
            if c_type in ['Auto', 'Video URL', '']:
                c_type = f"Google Drive ({g_type})"
        else:
            external_url = format_youtube_embed(external_url)
    content_text = request.form.get('content_text', '').strip()
    file_obj = request.files.get('courseware_file')

    if not title:
        flash("Courseware title is required.", "danger")
        return redirect(url_for('courses.view_course', course_id=lesson.course_id))

    filename = None
    if file_obj and file_obj.filename:
        ext = os.path.splitext(file_obj.filename)[1].lower()
        short_id = uuid.uuid4().hex[:8]
        filename = f"cw_{lesson.id}_{short_id}{ext}"
        save_path = os.path.join(current_app.config['MATERIALS_FOLDER'], filename)
        file_obj.save(save_path)

        # Also create a non-downloadable CourseMaterial record for inline viewing
        mat = CourseMaterial(
            course_id=lesson.course_id,
            title=f"[Lesson {lesson.lesson_number} Courseware] {title}",
            material_type='Video' if ext in ['.mp4', '.webm'] else ('PDF' if ext == '.pdf' else 'PPT'),
            filename=filename,
            allow_download=False # NON-DOWNLOADABLE as required!
        )
        db.session.add(mat)

    cw = LessonCourseware(
        lesson_id=lesson.id,
        title=title,
        courseware_type=c_type,
        filename=filename,
        external_url=external_url if external_url else None,
        content_text=content_text if content_text else None
    )
    db.session.add(cw)
    db.session.commit()

    flash(f"Non-downloadable courseware '{title}' attached to Lesson #{lesson.lesson_number}.", "success")
    return redirect(url_for('courses.view_course', course_id=lesson.course_id))


@courses_bp.route('/lesson/<int:lesson_id>/upload_assessment', methods=['POST'])
def upload_lesson_assessment(lesson_id):
    """
    Upload CSV questions specifically for a Lesson's Pre-Assessment or Post-Assessment.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    lesson = CourseLesson.query.get_or_404(lesson_id)
    assessment_type = request.form.get('assessment_type', 'LESSON_PRE').strip() # 'LESSON_PRE' or 'LESSON_POST'
    csv_file = request.files.get('assessment_csv')

    if not csv_file or not csv_file.filename:
        flash("Please select a CSV file.", "danger")
        return redirect(url_for('courses.view_course', course_id=lesson.course_id))

    q_list, errs = parse_assessment_csv(csv_file.stream, filename=csv_file.filename)
    if errs:
        flash(f"CSV Errors: {', '.join(errs[:3])}", "danger")
        return redirect(url_for('courses.view_course', course_id=lesson.course_id))

    # Delete existing questions for this lesson & type
    CourseAssessment.query.filter_by(lesson_id=lesson.id, assessment_type=assessment_type).delete()

    for q in q_list:
        assessment = CourseAssessment(
            course_id=lesson.course_id,
            lesson_id=lesson.id,
            assessment_type=assessment_type,
            serial_number=q['serial_number'],
            question=q['question'],
            option1=q['option1'],
            option2=q['option2'],
            option3=q['option3'],
            option4=q['option4'],
            correct_option=q['correct_option'],
            lesson_number=lesson.lesson_number
        )
        db.session.add(assessment)

    db.session.commit()
    flash(f"Successfully uploaded {len(q_list)} questions for Lesson #{lesson.lesson_number} {assessment_type}.", "success")
    return redirect(url_for('courses.view_course', course_id=lesson.course_id))


@courses_bp.route('/<int:course_id>/upload_course_end_assessment', methods=['POST'])
def upload_course_end_assessment(course_id):
    """
    Upload CSV questions for the Course End Assessment.
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    csv_file = request.files.get('assessment_csv')

    if not csv_file or not csv_file.filename:
        flash("Please select a CSV file.", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    q_list, errs = parse_assessment_csv(csv_file.stream, filename=csv_file.filename)
    if errs:
        flash(f"CSV Errors: {', '.join(errs[:3])}", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    CourseAssessment.query.filter((CourseAssessment.course_id == course.id) & (CourseAssessment.assessment_type.in_(['COURSE_END', 'POST'])) & (CourseAssessment.lesson_id == None)).delete()

    for q in q_list:
        assessment = CourseAssessment(
            course_id=course.id,
            lesson_id=None,
            assessment_type='COURSE_END',
            serial_number=q['serial_number'],
            question=q['question'],
            option1=q['option1'],
            option2=q['option2'],
            option3=q['option3'],
            option4=q['option4'],
            correct_option=q['correct_option']
        )
        db.session.add(assessment)

    from app.models.notification import LearnerNotification
    for en in course.enrollments:
        notif = LearnerNotification(
            learner_id=en.learner_id,
            course_id=course.id,
            title=f"Course End Assessment Available: {course.name}",
            message=f"The Course End Assessment CSV question bank ({len(q_list)} questions) has been attached to '{course.name}'.",
            notification_type='ASSESSMENT_UNLOCKED'
        )
        db.session.add(notif)

    db.session.commit()
    flash(f"Uploaded {len(q_list)} questions for Course End Assessment.", "success")
    return redirect(url_for('courses.view_course', course_id=course.id))


@courses_bp.route('/<int:course_id>/create_class', methods=['POST'])
def create_course_class(course_id):
    """
    Schedule a Live Class directly within the Course itself (Merged Course & Class Management).
    """
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    
    from app.models.live_class import LiveClass
    from app.services.qr_service import generate_class_qr

    class_mode = request.form.get('class_mode', 'In Person')
    date_str = request.form.get('class_date')
    from datetime import datetime
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

    new_cls = LiveClass(
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

    course_code = course.name.split()[0] if course.name else 'CRS'
    new_cls.class_name = new_cls.build_class_name(course_code)

    db.session.add(new_cls)
    db.session.commit()

    generate_class_qr(new_cls.class_id)

    pre_file = request.files.get('pre_assessment_file')
    post_file = request.files.get('post_assessment_file')

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

    flash(f"Live Class '{new_cls.class_name}' ({new_cls.class_id}) created inside course '{course.name}'!", "success")
    return redirect(url_for('courses.view_course', course_id=course.id))


@courses_bp.route('/<int:course_id>/edit', methods=['GET', 'POST'])
def edit_course(course_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)

    if request.method == 'POST':
        course.name = request.form.get('name', '').strip()
        course.description = request.form.get('description', '').strip()
        course.mode = request.form.get('mode', 'Live').strip()
        course.pass_percentage = float(request.form.get('pass_percentage', 80.0))
        fb_id = request.form.get('feedback_repo_id')
        course.feedback_repo_id = int(fb_id) if fb_id else None
        course.has_certificate = (request.form.get('has_certificate', '1') == '1')
        course.is_sequential = (request.form.get('is_sequential', '1') == '1')
        comp_date_str = request.form.get('completion_date', '').strip()
        if comp_date_str:
            try:
                course.completion_date = datetime.strptime(comp_date_str, '%Y-%m-%d')
            except Exception:
                course.completion_date = None
        else:
            course.completion_date = None

        # Handle Thumbnail Upload
        thumb_file = request.files.get('thumbnail_file')
        if thumb_file and thumb_file.filename:
            ext = os.path.splitext(thumb_file.filename)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
                thumb_filename = f"thumb_{course.course_id}_{uuid.uuid4().hex[:8]}{ext}"
                thumb_dir = os.path.join(current_app.root_path, '..', 'uploads', 'thumbnails')
                os.makedirs(thumb_dir, exist_ok=True)
                thumb_file.save(os.path.join(thumb_dir, thumb_filename))
                course.thumbnail_filename = thumb_filename

        # Live Online duration defined directly by admin at course level
        if course.mode == 'Live Online':
            try:
                course.duration_hours = float(request.form.get('duration_hours', course.duration_hours or 1.0))
            except Exception:
                pass
        else:
            recalculate_course_duration(course.id)

        # Replace CSV questions enforcing mode-based assessment rules
        summative_file = request.files.get('summative_assessment_csv') or request.files.get('course_end_assessment_csv')
        pre_file = request.files.get('pre_assessment_csv')
        post_file = request.files.get('post_assessment_csv')

        if course.mode == 'Self Paced' and summative_file and summative_file.filename:
            q_list, errs = parse_assessment_csv(summative_file.stream, filename=summative_file.filename)
            if not errs:
                CourseAssessment.query.filter((CourseAssessment.course_id == course.id) & (CourseAssessment.assessment_type == 'COURSE_END') & (CourseAssessment.lesson_id == None)).delete()
                for q in q_list:
                    assessment = CourseAssessment(
                        course_id=course.id,
                        assessment_type='COURSE_END',
                        serial_number=q['serial_number'],
                        question=q['question'],
                        option1=q['option1'],
                        option2=q['option2'],
                        option3=q['option3'],
                        option4=q['option4'],
                        correct_option=q['correct_option']
                    )
                    db.session.add(assessment)

        if course.mode != 'Self Paced':
            if pre_file and pre_file.filename:
                q_list, errs = parse_assessment_csv(pre_file.stream, filename=pre_file.filename)
                if not errs:
                    CourseAssessment.query.filter_by(course_id=course.id, assessment_type='PRE').delete()
                    for q in q_list:
                        assessment = CourseAssessment(
                            course_id=course.id,
                            assessment_type='PRE',
                            serial_number=q['serial_number'],
                            question=q['question'],
                            option1=q['option1'],
                            option2=q['option2'],
                            option3=q['option3'],
                            option4=q['option4'],
                            correct_option=q['correct_option']
                        )
                        db.session.add(assessment)

            if post_file and post_file.filename:
                q_list, errs = parse_assessment_csv(post_file.stream, filename=post_file.filename)
                if not errs:
                    CourseAssessment.query.filter_by(course_id=course.id, assessment_type='POST').delete()
                    for q in q_list:
                        assessment = CourseAssessment(
                            course_id=course.id,
                            assessment_type='POST',
                            serial_number=q['serial_number'],
                            question=q['question'],
                            option1=q['option1'],
                            option2=q['option2'],
                            option3=q['option3'],
                            option4=q['option4'],
                            correct_option=q['correct_option']
                        )
                        db.session.add(assessment)

        db.session.commit()
        flash(f"Course {course.course_id} updated successfully.", "success")
        return redirect(url_for('courses.view_course', course_id=course.id))

    from app.models.feedback import FeedbackRepository
    feedback_repos = FeedbackRepository.query.all()
    return render_template('courses/create_edit.html', course=course, auto_id=course.course_id, feedback_repos=feedback_repos)


@courses_bp.route('/<int:course_id>/delete', methods=['POST'])
def delete_course(course_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    course_name = course.course_id
    try:
        from app.models.certificate import Certificate
        Certificate.query.filter_by(course_id=course.id).delete(synchronize_session=False)
        db.session.delete(course)
        db.session.commit()
        flash(f"Course {course_name} and all associated data deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Failed to delete course: {str(e)}", "danger")
        
    return redirect(url_for('courses.list_courses'))


@courses_bp.route('/<int:course_id>/upload_material', methods=['POST'])
def upload_material(course_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    title = request.form.get('material_title', '').strip()
    description = request.form.get('material_description', '').strip()
    user_mat_type = request.form.get('material_type', 'Auto').strip()
    external_url = request.form.get('external_url', '').strip()
    material_file = request.files.get('material_file')
    allow_download = request.form.get('allow_download') == 'on' # Checkbox toggle

    if not title:
        flash("Material title is required.", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    filename = None
    material_type = user_mat_type if user_mat_type != 'Auto' else 'External Link'
    size_str = 'N/A'

    if external_url:
        from app.services.gdrive_service import parse_gdrive_url
        is_gdrive, embed_url, g_type, file_id = parse_gdrive_url(external_url)
        if is_gdrive:
            if user_mat_type in ['Auto', 'Google Drive', '']:
                material_type = f"Google Drive ({g_type})"
            size_str = 'Google Drive'
        elif user_mat_type == 'Auto':
            if 'scorm' in external_url.lower():
                material_type = 'SCORM Link'
            else:
                material_type = 'External Link'

    elif material_file and material_file.filename:
        orig_filename = material_file.filename
        ext = os.path.splitext(orig_filename)[1].lower()

        if user_mat_type == 'Auto':
            if ext in ['.pdf']:
                material_type = 'PDF'
            elif ext in ['.ppt', '.pptx']:
                material_type = 'PPT'
            elif ext in ['.mp4', '.webm', '.avi', '.mkv', '.mov']:
                material_type = 'Video'
            elif ext in ['.xlsx', '.xls', '.csv']:
                material_type = 'Excel'
            elif ext in ['.zip', '.rar']:
                material_type = 'SCORM'
            elif ext in ['.doc', '.docx', '.txt']:
                material_type = 'Document'
            else:
                material_type = 'Other File'

        short_id = uuid.uuid4().hex[:8]
        filename = f"mat_{course.course_id}_{short_id}{ext}"
        save_path = os.path.join(current_app.config['MATERIALS_FOLDER'], filename)
        material_file.save(save_path)

        file_size_bytes = os.path.getsize(save_path)
        if file_size_bytes < 1024 * 1024:
            size_str = f"{round(file_size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(file_size_bytes / (1024 * 1024), 2)} MB"
    else:
        flash("Please provide a Google Drive URL / External link or upload a file.", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    new_mat = CourseMaterial(
        course_id=course.id,
        title=title,
        description=description if description else None,
        material_type=material_type,
        filename=filename,
        external_url=external_url if external_url else None,
        file_size_str=size_str,
        allow_download=allow_download
    )
    db.session.add(new_mat)
    db.session.commit()

    flash(f"Learning material '{title}' saved successfully.", "success")
    return redirect(url_for('courses.view_course', course_id=course.id))


@courses_bp.route('/material/<int:material_id>/toggle_download', methods=['POST'])
def toggle_download(material_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    mat = CourseMaterial.query.get_or_404(material_id)
    mat.allow_download = not mat.allow_download
    db.session.commit()

    status_str = "Download Allowed" if mat.allow_download else "Download Restricted (View-Only)"
    flash(f"Updated permission for '{mat.title}': {status_str}.", "info")
    return redirect(url_for('courses.view_course', course_id=mat.course_id))


@courses_bp.route('/material/<int:material_id>/download')
def download_material(material_id):
    mat = CourseMaterial.query.get_or_404(material_id)

    # Check download permissions for non-admin learners
    is_admin = session.get('admin_logged_in', False)
    force_download = request.args.get('download', '0') == '1'

    if not is_admin and not mat.allow_download and force_download:
        flash("File download restricted by L&D Admin. View inline only.", "warning")
        return redirect(url_for('learners.self_paced_flow', course_id_str=mat.course.course_id))

    if mat.external_url and not mat.filename:
        return redirect(mat.external_url)

    if mat.filename:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], mat.filename)
        if os.path.exists(file_path):
            ext = os.path.splitext(mat.filename)[1].lower()
            as_attach = force_download if is_admin or mat.allow_download else False
            
            # Determine correct MIME type for browser inline preview vs download
            mimetype = None
            if ext == '.pptx':
                mimetype = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
            elif ext == '.ppt':
                mimetype = 'application/vnd.ms-powerpoint'
            elif ext == '.pdf':
                mimetype = 'application/pdf'
            elif ext == '.mp4':
                mimetype = 'video/mp4'

            return send_file(
                file_path,
                mimetype=mimetype,
                as_attachment=as_attach,
                download_name=f"{mat.title}{ext}"
            )

    flash("Material file not found on server.", "danger")
    return redirect(url_for('courses.view_course', course_id=mat.course_id))


@courses_bp.route('/courseware/<int:courseware_id>/raw_file')
def get_courseware_raw_file(courseware_id):
    cw = LessonCourseware.query.get_or_404(courseware_id)
    if cw.filename:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], cw.filename)
        if os.path.exists(file_path):
            return send_file(
                file_path,
                mimetype='application/octet-stream',
                as_attachment=False
            )
    return jsonify({'error': 'File not found'}), 404


@courses_bp.route('/courseware/<int:courseware_id>/slide_img/<filename>')
def serve_slide_image(courseware_id, filename):
    img_folder = os.path.join(current_app.config['MATERIALS_FOLDER'], 'slides', str(courseware_id))
    img_path = os.path.join(img_folder, filename)
    if os.path.exists(img_path):
        return send_file(img_path)
    return jsonify({'error': 'Image not found'}), 404


@courses_bp.route('/courseware/<int:courseware_id>/stream')
def stream_courseware(courseware_id):
    cw = LessonCourseware.query.get_or_404(courseware_id)

    # Allow explicit download ONLY when query param download=1 is sent AND allow_download is True
    if request.args.get('download') == '1':
        if cw.allow_download and cw.filename:
            file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], cw.filename)
            if os.path.exists(file_path):
                return send_file(file_path, as_attachment=True)

    cw_type_upper = (cw.courseware_type or '').upper()
    ext = os.path.splitext(cw.filename)[1].lower() if cw.filename else ''
    
    is_ppt = ('PPT' in cw_type_upper) or ('POWERPOINT' in cw_type_upper) or ('SLIDE' in cw_type_upper) or (ext in ['.ppt', '.pptx'])
    is_pdf = ('PDF' in cw_type_upper) or (ext == '.pdf')

    # 1. REVEAL.JS HTML5 PRESENTATION PLAYER ENGINE FOR PPT / PPTX
    if is_ppt:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], cw.filename) if cw.filename else ''
        img_out_dir = os.path.join(current_app.config['MATERIALS_FOLDER'], 'slides', str(cw.id))
        img_rel_prefix = f"/courses/courseware/{cw.id}/slide_img"

        slides_data = []
        if file_path and os.path.exists(file_path):
            slides_data = parse_pptx_slides(file_path, output_img_dir=img_out_dir, rel_img_prefix=img_rel_prefix)

        if not slides_data:
            text_bullets = [line.strip() for line in (cw.content_text or "").split('\n') if line.strip()]
            if not text_bullets:
                text_bullets = [f"Overview of {cw.title}", "Key Concepts Breakdown", "Summary & Best Practices"]
            slides_data = [{"slide_number": 1, "title": cw.title, "bullets": text_bullets, "images": [], "notes": ""}]

        # Construct Reveal.js <section> slides HTML
        sections_html = []
        for s in slides_data:
            title_html = f'<h3 style="color:#F59E0B; font-weight:700; margin-bottom:20px; font-size:1.6rem;">{s.get("title") or cw.title}</h3>'
            
            bullets_html = ""
            if s.get("bullets"):
                items = "".join([f'<li style="margin-bottom:12px; font-size:1.05rem; color:#E2E8F0;">{b}</li>' for b in s["bullets"]])
                bullets_html = f'<ul style="text-align:left; display:inline-block; max-width:90%; font-size:1rem; margin-bottom:20px;">{items}</ul>'

            images_html = ""
            if s.get("images"):
                img_tags = "".join([f'<img src="{img_url}" style="max-height:280px; max-width:90%; border-radius:10px; border:1px solid #334155; margin:10px auto; display:block; box-shadow:0 10px 30px rgba(0,0,0,0.5);">' for img_url in s["images"]])
                images_html = f'<div style="margin-top:15px;">{img_tags}</div>'

            notes_html = f'<aside class="notes">{s.get("notes")}</aside>' if s.get("notes") else ""

            section = f"""
            <section style="padding: 20px; box-sizing: border-box;">
                {title_html}
                {bullets_html}
                {images_html}
                {notes_html}
            </section>
            """
            sections_html.append(section)

        slides_content = "\n".join(sections_html)

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{cw.title} - Reveal.js Presentation Deck</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/reveal.min.css">
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/theme/dracula.min.css">
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                html, body, .reveal {{ width: 100%; height: 100%; background: #091214; overflow: hidden; font-family: system-ui, -apple-system, sans-serif; }}
                .reveal h1, .reveal h2, .reveal h3, .reveal h4 {{ font-family: system-ui, sans-serif; text-transform: none; word-break: break-word; }}
                .reveal .slides {{ text-align: center; }}
                .reveal .slides section {{
                    padding: 12px !important;
                    box-sizing: border-box !important;
                    max-height: 100% !important;
                    overflow-y: auto !important;
                }}
                .reveal h3 {{ color: #F59E0B !important; font-weight: 700 !important; font-size: 1.6rem !important; margin-bottom: 16px !important; border-bottom: 1px solid rgba(245, 158, 11, 0.2); padding-bottom: 8px; }}
                .reveal ul {{ max-width: 92% !important; text-align: left !important; display: inline-block !important; font-size: 1.05rem !important; line-height: 1.6 !important; margin-bottom: 16px !important; color: #E2E8F0 !important; }}
                .reveal ul li {{ margin-bottom: 10px !important; word-break: break-word !important; }}
                .reveal img {{ max-width: 95% !important; max-height: 380px !important; object-fit: contain !important; margin: 12px auto !important; display: block !important; border-radius: 10px !important; border: 1px solid #334155 !important; box-shadow: 0 10px 30px rgba(0,0,0,0.6) !important; }}
                .reveal .controls {{ color: #F59E0B !important; }}
                .reveal .progress {{ color: #F59E0B !important; height: 5px !important; }}
                .reveal .slide-number {{ font-family: monospace !important; color: #F59E0B !important; font-weight: 700 !important; background: rgba(15, 23, 42, 0.9) !important; border: 1px solid #334155 !important; padding: 4px 10px !important; border-radius: 6px !important; }}
            </style>
        </head>
        <body>
            <div class="reveal">
                <div class="slides">
                    {slides_content}
                </div>
            </div>

            <script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/reveal.min.js"></script>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/reveal.js/4.5.0/plugin/notes/notes.min.js"></script>
            <script>
                Reveal.initialize({{
                    width: "100%",
                    height: "100%",
                    margin: 0.04,
                    minScale: 0.2,
                    maxScale: 2.0,
                    hash: true,
                    slideNumber: 'c / t',
                    controls: true,
                    progress: true,
                    center: true,
                    transition: 'slide',
                    plugins: [ RevealNotes ]
                }});
            </script>
        </body>
        </html>
        """, 200, {'Content-Type': 'text/html'}

    # 2. MOZILLA PDF.JS VECTOR PRESENTATION ENGINE FOR PDF
    if is_pdf:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], cw.filename) if cw.filename else ''
        img_out_dir = os.path.join(current_app.config['MATERIALS_FOLDER'], 'slides', str(cw.id))
        img_rel_prefix = f"/courses/courseware/{cw.id}/slide_img"
        slide_images = render_pdf_to_slide_images(file_path, img_out_dir, img_rel_prefix) if (file_path and os.path.exists(file_path)) else []

        raw_file_url = url_for('courses.get_courseware_raw_file', courseware_id=cw.id)

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>{cw.title} - Mozilla PDF Viewer</title>
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
            <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
            <style>
                * {{ box-sizing: border-box; margin: 0; padding: 0; }}
                body {{ background: #091214; color: #FAFAF9; font-family: system-ui, sans-serif; min-height: 100vh; display: flex; flex-direction: column; overflow: hidden; }}
                .deck-header {{ background: #0F172A; padding: 10px 16px; border-bottom: 1px solid #1E293B; display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }}
                .deck-title {{ font-size: 0.95rem; font-weight: 700; color: #FFFFFF; display: flex; align-items: center; gap: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
                .nav-controls {{ display: flex; align-items: center; gap: 10px; }}
                .btn-nav {{ background: #F59E0B; color: #0F172A; border: none; padding: 6px 14px; border-radius: 6px; font-size: 0.82rem; font-weight: 700; cursor: pointer; transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 6px; }}
                .btn-nav:hover:not(:disabled) {{ background: #D97706; color: #FFFFFF; }}
                .btn-nav:disabled {{ opacity: 0.35; cursor: not-allowed; background: #334155; color: #94A3B8; }}
                .slide-counter {{ font-size: 0.85rem; font-weight: 700; color: #F59E0B; font-family: monospace; background: rgba(245, 158, 11, 0.15); padding: 4px 10px; border-radius: 20px; border: 1px solid rgba(245, 158, 11, 0.3); }}
                .slide-stage {{ flex: 1; padding: 12px; display: flex; align-items: center; justify-content: center; background: radial-gradient(circle at center, #1E293B 0%, #091214 100%); overflow: auto; height: calc(100vh - 52px); }}
                #pdfCanvas {{ max-width: 100%; max-height: calc(100vh - 70px); border-radius: 8px; box-shadow: 0 12px 32px rgba(0,0,0,0.6); background: #FFFFFF; display: block; margin: 0 auto; }}
            </style>
        </head>
        <body>
            <div class="deck-header">
                <div class="deck-title">
                    <i class="fa-solid fa-file-pdf" style="color:#F59E0B;"></i> {cw.title}
                </div>
                <div class="nav-controls">
                    <button class="btn-nav" id="btnPrev" onclick="prevPage()"><i class="fa-solid fa-arrow-left"></i> Prev</button>
                    <span class="slide-counter" id="slideCounter">Page 1 of 1</span>
                    <button class="btn-nav" id="btnNext" onclick="nextPage()">Next <i class="fa-solid fa-arrow-right"></i></button>
                </div>
            </div>

            <div class="slide-stage">
                <canvas id="pdfCanvas"></canvas>
            </div>

            <script>
                pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                let pdfDoc = null;
                let pageNum = 1;
                const canvas = document.getElementById('pdfCanvas');
                const ctx = canvas.getContext('2d');

                pdfjsLib.getDocument('{raw_file_url}').promise.then(function(doc) {{
                    pdfDoc = doc;
                    renderPage(1);
                }});

                function renderPage(num) {{
                    pdfDoc.getPage(num).then(function(page) {{
                        const viewport = page.getViewport({{ scale: 1.4 }});
                        canvas.height = viewport.height;
                        canvas.width = viewport.width;
                        page.render({{ canvasContext: ctx, viewport: viewport }});
                    }});
                    document.getElementById('slideCounter').textContent = 'Page ' + num + ' of ' + pdfDoc.numPages;
                    document.getElementById('btnPrev').disabled = (num <= 1);
                    document.getElementById('btnNext').disabled = (num >= pdfDoc.numPages);
                }}

                function prevPage() {{ if (pageNum > 1) {{ pageNum--; renderPage(pageNum); }} }}
                function nextPage() {{ if (pageNum < pdfDoc.numPages) {{ pageNum++; renderPage(pageNum); }} }}

                document.addEventListener('keydown', (e) => {{
                    if (e.key === 'ArrowLeft') prevPage();
                    if (e.key === 'ArrowRight') nextPage();
                }});
            </script>
        </body>
        </html>
        """, 200, {'Content-Type': 'text/html'}

    # 3. Handle PDF, Video, or other uploads (NEVER send raw PPT files to browser)
    if cw.filename and ext not in ['.ppt', '.pptx']:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], cw.filename)
        if os.path.exists(file_path):
            mimetype = None
            if ext == '.pdf':
                mimetype = 'application/pdf'
            elif ext in ['.mp4', '.webm', '.ogg', '.mov']:
                mimetype = f'video/{ext[1:]}'

            return send_file(
                file_path,
                mimetype=mimetype,
                as_attachment=False
            )

    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><style>body{{background:#091214;color:#FAFAF9;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}</style></head>
    <body>
        <div style="text-align:center;padding:20px;background:#0F172A;border-radius:12px;border:1px solid #334155;max-width:500px;">
            <h3 style="color:#F59E0B;margin-bottom:10px;">{cw.title}</h3>
            <p style="color:#94A3B8;font-size:0.9rem;">{cw.content_text or 'Presentation deck loaded cleanly.'}</p>
        </div>
    </body>
    </html>
    """, 200, {'Content-Type': 'text/html'}

    # 2. Handle PDF, Video, or other uploads
    if cw.filename:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], cw.filename)
        if os.path.exists(file_path):
            mimetype = None
            if ext == '.pdf':
                mimetype = 'application/pdf'
            elif ext in ['.mp4', '.webm', '.ogg', '.mov']:
                mimetype = f'video/{ext[1:]}'

            return send_file(
                file_path,
                mimetype=mimetype,
                as_attachment=False
            )

    return redirect(url_for('courses.view_course', course_id=cw.lesson.course_id))

    # 2. Handle PDF, Video, or other uploads
    if cw.filename:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], cw.filename)
        if os.path.exists(file_path):
            mimetype = None
            if ext == '.pdf':
                mimetype = 'application/pdf'
            elif ext in ['.mp4', '.webm', '.ogg', '.mov']:
                mimetype = f'video/{ext[1:]}'

            return send_file(
                file_path,
                mimetype=mimetype,
                as_attachment=False
            )

    return redirect(url_for('courses.view_course', course_id=cw.lesson.course_id))


@courses_bp.route('/material/<int:material_id>/delete', methods=['POST'])
def delete_material(material_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    mat = CourseMaterial.query.get_or_404(material_id)
    course_id = mat.course_id

    if mat.filename:
        file_path = os.path.join(current_app.config['MATERIALS_FOLDER'], mat.filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception:
                pass

    db.session.delete(mat)
    db.session.commit()

    flash(f"Learning material '{mat.title}' deleted.", "success")
    return redirect(url_for('courses.view_course', course_id=course_id))


@courses_bp.route('/<int:course_id>/download_analytics')
def download_analytics(course_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    csv_buffer = generate_course_analytics_csv(course.id)

    safe_name = "".join(c for c in course.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    filename = f"Course_Analytics_{safe_name}.csv"

    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


@courses_bp.route('/class/<int:class_id>/download_attendance')
def download_attendance(class_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    live_cls = LiveClass.query.get_or_404(class_id)
    csv_buffer = generate_class_attendance_csv(live_cls.id)

    safe_name = "".join(c for c in live_cls.class_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    filename = f"Attendance_{safe_name}.csv"

    return send_file(
        csv_buffer,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )


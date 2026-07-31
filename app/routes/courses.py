import os
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, send_file, current_app
from app.models import db
from app.models.course import Course, CourseAssessment, CourseMaterial, CourseLesson, LessonCourseware
from app.models.live_class import LiveClass
from app.services.assessment_service import parse_assessment_csv
from app.services.report_service import generate_course_analytics_csv, generate_class_attendance_csv

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
        query = query.filter((Course.name.ilike(f'%{search_query}%')) | (Course.course_id.ilike(f'%{search_query}%')))

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
            pass_percentage=pass_percentage
        )
        db.session.add(new_course)
        db.session.commit()

        # Handle CSV uploads for Summative, Pre and Post Assessments (all optional)
        summative_file = request.files.get('summative_assessment_csv') or request.files.get('course_end_assessment_csv')
        pre_file = request.files.get('pre_assessment_csv')
        post_file = request.files.get('post_assessment_csv')

        summative_errs, pre_errs, post_errs = [], [], []

        if summative_file and summative_file.filename:
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

    auto_id = Course.generate_course_id()
    return render_template('courses/create_edit.html', auto_id=auto_id, course=None)


@courses_bp.route('/<int:course_id>')
def view_course(course_id):
    if not check_admin():
        return redirect(url_for('auth.admin_login'))

    course = Course.query.get_or_404(course_id)
    pre_questions = CourseAssessment.query.filter_by(course_id=course.id, assessment_type='PRE').order_by(CourseAssessment.serial_number.asc()).all()
    post_questions = CourseAssessment.query.filter_by(course_id=course.id, assessment_type='POST').order_by(CourseAssessment.serial_number.asc()).all()
    
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
        lessons=lessons,
        live_classes=live_classes,
        feedback_repos=feedback_repos
    )


def recalculate_course_duration(course_id):
    course = Course.query.get(course_id)
    if course:
        lessons = CourseLesson.query.filter_by(course_id=course.id).all()
        if lessons:
            course.duration_hours = round(sum(l.duration_hours for l in lessons if l.duration_hours is not None), 2)
        else:
            course.duration_hours = 0.0
        db.session.commit()


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

    if not title:
        flash("Lesson title is required.", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    external_url = request.form.get('external_url', '').strip() or request.form.get('video_url', '').strip()
    if external_url:
        external_url = format_youtube_embed(external_url)

    lesson = CourseLesson(
        course_id=course.id,
        lesson_number=lesson_number,
        title=title,
        summary=summary,
        content=content,
        video_url=None,
        duration_hours=duration_hours,
        min_time_minutes=min_time_minutes
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
    cw_type = request.form.get('courseware_type', 'Video URL').strip()
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

        # Recalculate duration automatically from lessons
        recalculate_course_duration(course.id)

        # Replace CSV questions if uploaded
        summative_file = request.files.get('summative_assessment_csv') or request.files.get('course_end_assessment_csv')
        pre_file = request.files.get('pre_assessment_csv')
        post_file = request.files.get('post_assessment_csv')

        if summative_file and summative_file.filename:
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

    return render_template('courses/create_edit.html', course=course, auto_id=course.course_id)


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
    external_url = request.form.get('external_url', '').strip()
    material_file = request.files.get('material_file')
    allow_download = request.form.get('allow_download') == 'on' # Checkbox toggle

    if not title:
        flash("Material title is required.", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    filename = None
    material_type = 'External Link'
    size_str = 'N/A'

    if material_file and material_file.filename:
        orig_filename = material_file.filename
        ext = os.path.splitext(orig_filename)[1].lower()

        # Determine type from extension
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

        # Secure filename
        short_id = uuid.uuid4().hex[:8]
        filename = f"mat_{course.course_id}_{short_id}{ext}"
        save_path = os.path.join(current_app.config['MATERIALS_FOLDER'], filename)
        
        material_file.save(save_path)

        # File size calculation
        file_size_bytes = os.path.getsize(save_path)
        if file_size_bytes < 1024 * 1024:
            size_str = f"{round(file_size_bytes / 1024, 1)} KB"
        else:
            size_str = f"{round(file_size_bytes / (1024 * 1024), 2)} MB"

    elif external_url:
        material_type = 'External Link'
        if 'scorm' in external_url.lower():
            material_type = 'SCORM Link'
    else:
        flash("Please upload a file or provide an external URL.", "danger")
        return redirect(url_for('courses.view_course', course_id=course.id))

    new_mat = CourseMaterial(
        course_id=course.id,
        title=title,
        material_type=material_type,
        filename=filename,
        external_url=external_url if external_url else None,
        file_size_str=size_str,
        allow_download=allow_download
    )
    db.session.add(new_mat)
    db.session.commit()

    flash(f"Learning material '{title}' uploaded successfully (Download Allowed: {allow_download}).", "success")
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
            # If download is allowed or forced by admin, set as_attachment=True
            as_attach = force_download if is_admin or mat.allow_download else False
            return send_file(
                file_path,
                as_attachment=as_attach,
                download_name=f"{mat.title}{os.path.splitext(mat.filename)[1]}"
            )

    flash("Material file not found on server.", "danger")
    return redirect(url_for('courses.view_course', course_id=mat.course_id))


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


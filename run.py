import os
import uuid
import datetime
from app import create_app
from app.models import db
from app.models.user import AdminUser, Learner
from app.models.course import Course, CourseAssessment, CourseLesson, LessonCourseware, CourseMaterial
from app.models.live_class import LiveClass
from app.models.enrollment import LearnerEnrollment, AssessmentAttempt, LessonReview
from app.models.attendance import Attendance
from app.models.feedback import FeedbackRepository, FeedbackQuestion
from app.models.notification import LearnerNotification
from app.config import Config

app = create_app()

def init_db_if_needed():
    with app.app_context():
        try:
            db.create_all()
        except Exception as e:
            db.session.rollback()
            print(f"db.create_all warning handled: {e}")

        try:
            db.session.execute(db.text("ALTER TABLE learners ADD COLUMN date_of_birth DATE;"))
            db.session.commit()
        except Exception:
            db.session.rollback()
        try:
            db.session.execute(db.text("ALTER TABLE course_lessons ADD COLUMN duration_hours FLOAT DEFAULT 1.0;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE course_lessons ADD COLUMN min_time_minutes FLOAT DEFAULT 1.0;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE courses ADD COLUMN feedback_repo_id INTEGER;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE courses ADD COLUMN has_certificate BOOLEAN DEFAULT 1;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE courses ADD COLUMN thumbnail_filename VARCHAR(255);"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE courses ADD COLUMN is_sequential BOOLEAN DEFAULT 1;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE courses ADD COLUMN completion_date DATETIME;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE course_lessons ADD COLUMN deadline DATETIME;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        try:
            db.session.execute(db.text("ALTER TABLE course_materials ADD COLUMN description TEXT;"))
            db.session.commit()
        except Exception:
            db.session.rollback()

        os.makedirs(os.path.join(app.root_path, '..', 'uploads', 'thumbnails'), exist_ok=True)

        admin = AdminUser.query.filter_by(username='admin').first()
        if not admin or Course.query.count() == 0:
            print("Database missing initial seed. Seeding data...")
            if not admin:
                admin = AdminUser(username='admin', password_hash='admin')
                db.session.add(admin)

            # 2. Seed Clean Learners if empty
            if Learner.query.count() == 0:
                learner1 = Learner(global_id='10001', name='Rajesh Kumar', department='L&D Academics')
                learner2 = Learner(global_id='10002', name='Priya Sharma', department='Mathematics Faculty')
                learner3 = Learner(global_id='10003', name='Anil Reddy', department='Physics Department')
                learner4 = Learner(global_id='10004', name='Sneha Patel', department='Chemistry Department')
                learner5 = Learner(global_id='10005', name='Vikram Verma', department='L&D Operations')
                db.session.add_all([learner1, learner2, learner3, learner4, learner5])
                db.session.commit()

            # 3. Seed Feedback Repositories
            fb_repo = FeedbackRepository(title='Standard L&D Session Feedback Survey', description='Facilitation & Course Quality Feedback')
            db.session.add(fb_repo)
            db.session.commit()

            q1 = FeedbackQuestion(repo_id=fb_repo.id, question_text='How would you rate the course content quality?', question_type='MCQ', options_json='["Excellent", "Good", "Average", "Poor"]')
            q2 = FeedbackQuestion(repo_id=fb_repo.id, question_text='Was the facilitator engaging and clear?', question_type='MCQ', options_json='["Strongly Agree", "Agree", "Neutral", "Disagree"]')
            q3 = FeedbackQuestion(repo_id=fb_repo.id, question_text='What key learnings will you apply in your role?', question_type='Text')
            db.session.add_all([q1, q2, q3])
            db.session.commit()

            # COURSE TYPE 1: Self Paced Course
            c1 = Course(
                course_id='CRS-000001',
                name='Python Data Structures & Algorithms Masterclass',
                duration_hours=6.0,
                description='Self-paced course covering lists, dictionaries, trees, graphs, dynamic programming, and complexity analysis.',
                mode='Self Paced',
                pass_percentage=80.0,
                feedback_repo_id=fb_repo.id,
                has_certificate=True
            )
            db.session.add(c1)
            db.session.commit()

            # Course End Assessment (Final Exam) Questions
            ass_end1 = CourseAssessment(course_id=c1.id, lesson_id=None, assessment_type='COURSE_END', serial_number=1, question='What is the worst-case time complexity of QuickSort?', option1='O(n log n)', option2='O(n^2)', option3='O(n)', option4='O(1)', correct_option='Option2')
            ass_end2 = CourseAssessment(course_id=c1.id, lesson_id=None, assessment_type='COURSE_END', serial_number=2, question='Which algorithm finds the shortest path in a weighted graph without negative edges?', option1='Dijkstra', option2='Kruskal', option3='Prim', option4='Bellman-Ford', correct_option='Option1')
            db.session.add_all([ass_end1, ass_end2])

            # Course Downloadable Resource
            mat1 = CourseMaterial(course_id=c1.id, title='Python DSA Reference CheatSheet (PDF)', material_type='PDF', filename='dsa_cheatsheet.pdf', allow_download=True, file_size_str='1.2 MB')
            db.session.add(mat1)

            # COURSE TYPE 2: Live In Person Course
            c2 = Course(
                course_id='CRS-000002',
                name='Advanced Machine Learning & AI Workshop',
                duration_hours=8.0,
                description='Live in-person campus training covering supervised learning, neural networks, and model deployment.',
                mode='Live In Person',
                pass_percentage=80.0,
                feedback_repo_id=fb_repo.id,
                has_certificate=True
            )
            db.session.add(c2)
            db.session.commit()

            # Class 1 for Live In Person
            cls_in1 = LiveClass(
                class_id='CLS-INP-000001',
                class_name='CRS000002-30-JUL-2026-HYD-KPHB-MORNING',
                course_id=c2.id,
                class_mode='In Person',
                class_date=datetime.date(2026, 7, 30),
                location='HYD',
                branch='KPHB Campus',
                session_time='Morning',
                facilitator_name='Dr. Sharma',
                co_facilitator_name='Rahul Verma',
                duration_hours=4.0,
                expected_attendance=40,
                feedback_repo_id=fb_repo.id
            )
            db.session.add(cls_in1)

            # In-Person Pre & Post Assessment Questions
            ass_inp_pre = CourseAssessment(course_id=c2.id, assessment_type='PRE', serial_number=1, question='What type of learning uses labeled data?', option1='Supervised', option2='Unsupervised', option3='Reinforcement', option4='Semi-supervised', correct_option='Option1')
            ass_inp_post = CourseAssessment(course_id=c2.id, assessment_type='POST', serial_number=1, question='Which metric evaluates classification accuracy?', option1='F1 Score', option2='MSE', option3='MAE', option4='R-Squared', correct_option='Option1')
            db.session.add_all([ass_inp_pre, ass_inp_post])

            # In-Person Session Download Resource
            mat2 = CourseMaterial(course_id=c2.id, title='ML Model Training Code Exercises (ZIP)', material_type='Excel', filename='ml_code.zip', allow_download=True, file_size_str='3.5 MB')
            db.session.add(mat2)

            # COURSE TYPE 3: Live Online Course
            c3 = Course(
                course_id='CRS-000003',
                name='Cloud Native Architecture & Kubernetes Masterclass',
                duration_hours=5.0,
                description='Live virtual online classroom training with Google Meet integration, containers, and microservices.',
                mode='Live Online',
                pass_percentage=80.0,
                feedback_repo_id=fb_repo.id,
                has_certificate=True
            )
            db.session.add(c3)
            db.session.commit()

            # Class 1 for Live Online
            cls_on1 = LiveClass(
                class_id='CLS-ONL-000001',
                class_name='CRS000003-31-JUL-2026-ONLINE-MEET-EVENING',
                course_id=c3.id,
                class_mode='Online',
                class_date=datetime.date(2026, 7, 31),
                location='Online Virtual',
                branch='Google Meet',
                session_time='Evening',
                meet_link='https://meet.google.com/abc-defg-hij',
                facilitator_name='Ananya Roy',
                duration_hours=5.0,
                expected_attendance=50,
                feedback_repo_id=fb_repo.id
            )
            db.session.add(cls_on1)

            # Online Pre & Post Assessment Questions
            ass_onl_pre = CourseAssessment(course_id=c3.id, assessment_type='PRE', serial_number=1, question='What is a Kubernetes Pod?', option1='A group of containers', option2='A virtual machine', option3='A disk drive', option4='A load balancer', correct_option='Option1')
            ass_onl_post = CourseAssessment(course_id=c3.id, assessment_type='POST', serial_number=1, question='Which kubectl command deploys a manifest file?', option1='kubectl apply -f', option2='kubectl run', option3='kubectl start', option4='kubectl get', correct_option='Option1')
            db.session.add_all([ass_onl_pre, ass_onl_post])

            # Online Session Download Resource
            mat3 = CourseMaterial(course_id=c3.id, title='Kubernetes Deployment Manifests (YAML)', material_type='Document', filename='k8s_manifests.yaml', allow_download=True, file_size_str='850 KB')
            db.session.add(mat3)

            # Enroll Learner 10001 in all 3 courses for demo testing
            l1 = Learner.query.filter_by(global_id='10001').first()
            if l1:
                en1 = LearnerEnrollment(learner_id=l1.id, course_id=c1.id, completion_status='In Progress', attempts_count=0)
                en2 = LearnerEnrollment(learner_id=l1.id, course_id=c2.id, class_id=cls_in1.id, completion_status='Enrolled')
                en3 = LearnerEnrollment(learner_id=l1.id, course_id=c3.id, class_id=cls_on1.id, completion_status='Enrolled')
                db.session.add_all([en1, en2, en3])

            db.session.commit()
            print("Database initialized successfully!")

if __name__ == '__main__':
    init_db_if_needed()
    print("Starting Narayana Learning Hub L&D Management Server on http://localhost:5000 ...")
    app.run(host='0.0.0.0', port=5000, debug=True)

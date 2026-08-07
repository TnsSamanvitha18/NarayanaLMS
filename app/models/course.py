from datetime import datetime
from app.models import db

class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.String(20), unique=True, nullable=False, index=True) # CRS-000001
    name = db.Column(db.String(150), nullable=False)
    duration_hours = db.Column(db.Float, nullable=False, default=1.0)
    description = db.Column(db.Text, nullable=True)
    mode = db.Column(db.String(20), nullable=False, default='Live') # 'Self Paced', 'Live'
    pass_percentage = db.Column(db.Float, nullable=False, default=80.0)
    feedback_repo_id = db.Column(db.Integer, db.ForeignKey('feedback_repositories.id'), nullable=True)
    has_certificate = db.Column(db.Boolean, nullable=False, default=True)
    thumbnail_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assessments = db.relationship('CourseAssessment', backref='course', lazy=True, cascade='all, delete-orphan')
    materials = db.relationship('CourseMaterial', backref='course', lazy=True, cascade='all, delete-orphan')
    lessons = db.relationship('CourseLesson', backref='course', lazy=True, cascade='all, delete-orphan')
    classes = db.relationship('LiveClass', backref='course', lazy=True, cascade='all, delete-orphan')
    enrollments = db.relationship('LearnerEnrollment', backref='course', lazy=True, cascade='all, delete-orphan')
    feedback_repository = db.relationship('FeedbackRepository', backref='courses', lazy=True)

    @staticmethod
    def generate_course_id():
        last_course = Course.query.order_by(Course.id.desc()).first()
        if not last_course:
            return "CRS-000001"
        last_num = int(last_course.course_id.split('-')[1])
        return f"CRS-{last_num + 1:06d}"

    def __repr__(self):
        return f'<Course {self.course_id} - {self.name}>'


class CourseAssessment(db.Model):
    __tablename__ = 'course_assessments'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('course_lessons.id'), nullable=True) # Optional link to specific lesson
    assessment_type = db.Column(db.String(30), nullable=False) # 'LESSON_PRE', 'LESSON_POST', 'COURSE_END', 'PRE', 'POST'
    serial_number = db.Column(db.Integer, nullable=False, default=1)
    question = db.Column(db.Text, nullable=False)
    option1 = db.Column(db.String(255), nullable=False)
    option2 = db.Column(db.String(255), nullable=False)
    option3 = db.Column(db.String(255), nullable=False)
    option4 = db.Column(db.String(255), nullable=False)
    correct_option = db.Column(db.String(50), nullable=False)
    lesson_number = db.Column(db.Integer, nullable=True, default=1)

    def __repr__(self):
        return f'<Assessment Q{self.serial_number} for Course {self.course_id} ({self.assessment_type})>'


class CourseLesson(db.Model):
    __tablename__ = 'course_lessons'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    lesson_number = db.Column(db.Integer, nullable=False, default=1)
    title = db.Column(db.String(150), nullable=False)
    summary = db.Column(db.Text, nullable=True)
    content = db.Column(db.Text, nullable=True)
    video_url = db.Column(db.String(500), nullable=True)
    duration_hours = db.Column(db.Float, nullable=False, default=1.0)
    min_time_minutes = db.Column(db.Float, nullable=False, default=1.0) # Admin minimum required time on courseware
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    courseware = db.relationship('LessonCourseware', backref='lesson', lazy=True, cascade='all, delete-orphan')
    assessments = db.relationship('CourseAssessment', backref='lesson', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<CourseLesson {self.lesson_number}: {self.title}>'


class LessonCourseware(db.Model):
    __tablename__ = 'lesson_courseware'

    id = db.Column(db.Integer, primary_key=True)
    lesson_id = db.Column(db.Integer, db.ForeignKey('course_lessons.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    courseware_type = db.Column(db.String(30), nullable=False, default='Text') # 'Video', 'PDF', 'PPT', 'Text', 'SCORM'
    filename = db.Column(db.String(255), nullable=True) # Non-downloadable file in uploads/materials
    external_url = db.Column(db.String(500), nullable=True)
    content_text = db.Column(db.Text, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LessonCourseware {self.title} ({self.courseware_type})>'


class CourseMaterial(db.Model):
    __tablename__ = 'course_materials'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    material_type = db.Column(db.String(30), nullable=False, default='PDF') # 'PDF', 'PPT', 'Video', 'Excel', 'SCORM', 'External Link', 'Document'
    filename = db.Column(db.String(255), nullable=True) # Filename in uploads/materials
    external_url = db.Column(db.String(500), nullable=True) # Optional URL link
    file_size_str = db.Column(db.String(50), nullable=True, default='N/A')
    allow_download = db.Column(db.Boolean, default=True) # Admin permission toggle: True = Downloadable, False = View-only
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<CourseMaterial {self.title} ({self.material_type})>'


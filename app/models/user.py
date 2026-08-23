from datetime import datetime
from app.models import db

class AdminUser(db.Model):
    __tablename__ = 'admin_users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, default='admin')
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(120), default='L&D Administrator')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, password):
        return self.password_hash == password  # Temporary password verification for POC


class Learner(db.Model):
    __tablename__ = 'learners'

    id = db.Column(db.Integer, primary_key=True)
    global_id = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    department = db.Column(db.String(100), nullable=True, default='L&D')
    date_of_birth = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    enrollments = db.relationship('LearnerEnrollment', backref='learner', lazy=True, cascade='all, delete-orphan')
    attendances = db.relationship('Attendance', backref='learner', lazy=True, cascade='all, delete-orphan')
    certificates = db.relationship('Certificate', backref='learner', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Learner {self.global_id} - {self.name}>'

from datetime import datetime
import uuid
from app.models import db

class Certificate(db.Model):
    __tablename__ = 'certificates'

    id = db.Column(db.Integer, primary_key=True)
    certificate_id = db.Column(db.String(50), unique=True, nullable=False, index=True) # CERT-XXXXXX
    learner_id = db.Column(db.Integer, db.ForeignKey('learners.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    pdf_filename = db.Column(db.String(255), nullable=True)

    course = db.relationship('Course', backref=db.backref('certificates', cascade='all, delete-orphan'))

    @staticmethod
    def generate_certificate_id():
        short_uuid = uuid.uuid4().hex[:6].upper()
        return f"CERT-{short_uuid}"

    def __repr__(self):
        return f'<Certificate {self.certificate_id} for Learner {self.learner_id}>'

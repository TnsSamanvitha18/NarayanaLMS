from datetime import datetime
from app.models import db

class Attendance(db.Model):
    __tablename__ = 'attendances'

    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('live_classes.id'), nullable=False)
    learner_id = db.Column(db.Integer, db.ForeignKey('learners.id'), nullable=False)
    
    status = db.Column(db.String(20), nullable=False, default='Present') # 'Present', 'Absent', 'Late'
    recorded_via = db.Column(db.String(20), nullable=False, default='QR') # 'QR', 'Manual'
    manual_reason = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Attendance Class {self.class_id} - Learner {self.learner_id} ({self.status})>'

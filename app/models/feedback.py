from datetime import datetime
import json
from app.models import db

class FeedbackRepository(db.Model):
    __tablename__ = 'feedback_repositories'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship('FeedbackQuestion', backref='repository', lazy=True, cascade='all, delete-orphan')
    classes = db.relationship('LiveClass', backref='feedback_repository', lazy=True)
    responses = db.relationship('FeedbackResponse', backref='repository', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<FeedbackRepository {self.title}>'


class FeedbackQuestion(db.Model):
    __tablename__ = 'feedback_questions'

    id = db.Column(db.Integer, primary_key=True)
    repo_id = db.Column(db.Integer, db.ForeignKey('feedback_repositories.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False, default='MCQ') # 'MCQ', 'Text'
    options_json = db.Column(db.Text, nullable=True) # JSON list string e.g. ["Excellent", "Good", "Average", "Poor"]

    def get_options(self):
        if self.options_json:
            try:
                return json.loads(self.options_json)
            except Exception:
                return []
        return []

    def set_options(self, options_list):
        self.options_json = json.dumps(options_list)


class FeedbackResponse(db.Model):
    __tablename__ = 'feedback_responses'

    id = db.Column(db.Integer, primary_key=True)
    repo_id = db.Column(db.Integer, db.ForeignKey('feedback_repositories.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('live_classes.id'), nullable=True)
    learner_id = db.Column(db.Integer, db.ForeignKey('learners.id'), nullable=False)
    responses_json = db.Column(db.Text, nullable=False) # JSON dictionary of question_id -> response
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

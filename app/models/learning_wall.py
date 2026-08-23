from datetime import datetime
from app.models import db

class LearningWallPost(db.Model):
    __tablename__ = 'learning_wall_posts'

    id = db.Column(db.Integer, primary_key=True)
    post_type = db.Column(db.String(50), nullable=False, default='SYSTEM_UPDATE') # 'COURSE_COMPLETION', 'BIRTHDAY', 'CERTIFICATE_EARNED', 'SYSTEM_UPDATE'
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    
    learner_id = db.Column(db.Integer, db.ForeignKey('learners.id'), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=True)
    
    icon = db.Column(db.String(50), default='fa-bullhorn')
    badge_color = db.Column(db.String(50), default='bg-teal-subtle text-teal')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    learner = db.relationship('Learner', backref=db.backref('wall_posts', lazy=True, cascade='all, delete-orphan'))
    course = db.relationship('Course', backref=db.backref('wall_posts', lazy=True, cascade='all, delete-orphan'))
    reactions = db.relationship('LearningWallReaction', backref='post', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<LearningWallPost {self.post_type} - {self.title}>'


class LearningWallReaction(db.Model):
    __tablename__ = 'learning_wall_reactions'

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('learning_wall_posts.id'), nullable=False)
    
    user_identifier = db.Column(db.String(100), nullable=False) # Learner Global ID or admin username
    user_name = db.Column(db.String(120), nullable=False)
    reaction_type = db.Column(db.String(20), nullable=False, default='like') # 'like', 'love', 'celebrate', 'clap', 'fire'
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<LearningWallReaction {self.reaction_type} by {self.user_name} on Post {self.post_id}>'

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

from app.models.learning_wall import LearningWallPost, LearningWallReaction


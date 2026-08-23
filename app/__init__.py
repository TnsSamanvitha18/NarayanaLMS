import os
from flask import Flask, session, g
from app.config import Config
from app.models import db

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    config_class.init_app(app)
    db.init_app(app)

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.courses import courses_bp
    from app.routes.classes import classes_bp
    from app.routes.learners import learners_bp
    from app.routes.attendance import attendance_bp
    from app.routes.feedback import feedback_bp
    from app.routes.certificates import certificates_bp
    from app.routes.reports import reports_bp
    from app.routes.learning_wall import learning_wall_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(courses_bp, url_prefix='/courses')
    app.register_blueprint(classes_bp, url_prefix='/classes')
    app.register_blueprint(learners_bp, url_prefix='/learners')
    app.register_blueprint(attendance_bp, url_prefix='/attendance')
    app.register_blueprint(feedback_bp, url_prefix='/feedback')
    app.register_blueprint(certificates_bp, url_prefix='/certificates')
    app.register_blueprint(reports_bp, url_prefix='/reports')
    app.register_blueprint(learning_wall_bp, url_prefix='/learning_wall')

    # Custom Jinja template filters
    @app.template_filter('format_duration')
    def format_duration_filter(hours):
        if not hours or float(hours) <= 0:
            return "0 hrs"
        hours = round(float(hours), 2)
        total_mins = int(round(hours * 60))
        hrs = total_mins // 60
        mins = total_mins % 60
        
        if hrs > 0 and mins > 0:
            return f"{hrs} hr{'s' if hrs > 1 else ''} {mins} mins"
        elif hrs > 0:
            return f"{hrs} hr{'s' if hrs > 1 else ''}"
        else:
            return f"{mins} mins"

    @app.template_filter('from_json')
    def from_json_filter(json_str):
        import json
        if not json_str:
            return {}
        try:
            return json.loads(json_str)
        except Exception:
            return {}

    # Global context processors for templates
    @app.context_processor
    def inject_global_vars():
        from app.services.gdrive_service import parse_gdrive_url
        learner_id = session.get('learner_id')
        user_notifications = []
        unread_notif_count = 0
        
        if learner_id:
            try:
                from app.models.notification import LearnerNotification
                user_notifications = LearnerNotification.query.filter_by(learner_id=learner_id).order_by(LearnerNotification.created_at.desc()).limit(8).all()
                unread_notif_count = LearnerNotification.query.filter_by(learner_id=learner_id, is_read=False).count()
            except Exception:
                pass

        return {
            'admin_logged_in': session.get('admin_logged_in', False),
            'admin_username': session.get('admin_username', 'admin'),
            'learner_id': learner_id,
            'learner_global_id': session.get('learner_global_id', None),
            'parse_gdrive_url': parse_gdrive_url,
            'user_notifications': user_notifications,
            'unread_notif_count': unread_notif_count
        }

    return app

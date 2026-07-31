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

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(courses_bp, url_prefix='/courses')
    app.register_blueprint(classes_bp, url_prefix='/classes')
    app.register_blueprint(learners_bp, url_prefix='/learners')
    app.register_blueprint(attendance_bp, url_prefix='/attendance')
    app.register_blueprint(feedback_bp, url_prefix='/feedback')
    app.register_blueprint(certificates_bp, url_prefix='/certificates')
    app.register_blueprint(reports_bp, url_prefix='/reports')

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

    # Global context processors for templates
    @app.context_processor
    def inject_global_vars():
        return {
            'admin_logged_in': session.get('admin_logged_in', False),
            'admin_username': session.get('admin_username', 'admin'),
            'learner_id': session.get('learner_id', None),
            'learner_global_id': session.get('learner_global_id', None)
        }

    return app

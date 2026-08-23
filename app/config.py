import os

BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('SECRET_KEY', 'narayana-lnd-lms-super-secret-key-2026')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "lms.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload Directories
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    QR_FOLDER = os.path.join(BASE_DIR, 'app', 'static', 'qr_codes')
    CERT_FOLDER = os.path.join(BASE_DIR, 'uploads', 'certificates')
    MATERIALS_FOLDER = os.path.join(BASE_DIR, 'uploads', 'materials')
    
    # Maximum allowed payload size (50 MB for videos/PPT/PDF)
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB

    TEMPLATES_AUTO_RELOAD = True
    SEND_FILE_MAX_AGE_DEFAULT = 0

    @staticmethod
    def init_app(app):
        app.config['TEMPLATES_AUTO_RELOAD'] = True
        app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.QR_FOLDER, exist_ok=True)
        os.makedirs(Config.CERT_FOLDER, exist_ok=True)
        os.makedirs(Config.MATERIALS_FOLDER, exist_ok=True)

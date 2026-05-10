"""
config.py - إعدادات تطبيق Flask
"""

import os
from datetime import timedelta


def _normalise_db_url(url):
    """Render gives postgres:// — SQLAlchemy 2.x wants postgresql://."""
    if url and url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    """الإعدادات الأساسية"""
    
    # معلومات التطبيق
    APP_NAME = "نظام إدارة المشاريع الهندسية الذكي"
    APP_VERSION = "1.0.0"
    TRIAL_DAYS = 30
    # السرية والأمان
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'jwt-secret-key-change-in-production'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=24)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    
    # قاعدة البيانات
    SQLALCHEMY_DATABASE_URI = _normalise_db_url(os.environ.get('DATABASE_URL')) or \
        'sqlite:///manag_project.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'pool_recycle': 300,
        'pool_pre_ping': True
    }
    
    # البريد الإلكتروني
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'najmyjomaan@gmail.com')
    
    # الذكاء الاصطناعي
    OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')
    AI_MODEL = os.environ.get('AI_MODEL', 'gpt-4')

    
    # الملفات
    # UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    # MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    ALLOWED_EXTENSIONS = {
        'images': {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg'},
        'documents': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'},
        'cad': {'dwg', 'dxf', 'dwf'},
        'archive': {'zip', 'rar', '7z'}
    }
    # إعدادات رفع الملفات
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'app/static/uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    
    # إعدادات الذكاء الاصطناعي
    AI_MODELS_CONFIG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config', 'models_config.yml')
    AI_WORKFLOW_CONFIG = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'config', 'ai_config.yml')
    AI_EMBEDDINGS_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data', 'embeddings')
    AI_CACHE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data', 'cache')
    
    # إعدادات txtai
    TXTAI_WRAPPER = True
    TXTAI_THREADS = 4
    TXTAI_BATCH_SIZE = 100
    # Redis (للمهام المتزامنة)
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
    
    # السجلات
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # الجلسة
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # معدل التحويل
    RATE_LIMIT_DEFAULT = "100 per minute"
    # إعدادات الذكاء الاصطناعي
    AI_CONFIG = {
        'max_file_size': 20 * 1024 * 1024,  # 20MB
        'supported_formats': ['pdf', 'docx', 'xlsx', 'csv', 'txt', 'jpg', 'png'],
        'ocr_enabled': True,
        'ocr_languages': 'ara+eng',  # العربية والإنجليزية
        'nlp_models': {
            'arabic': 'ar_core_web_sm',
            'english': 'en_core_web_sm',
            'ner': 'aubmindlab/bert-base-arabertv2'
        },
        'report_defaults': {
            'chart_height': 400,
            'chart_width': 600,
            'max_data_points': 50
        },
        'suggestions': {
            'enabled': True,
            'check_interval': 6,  # ساعات
            'min_confidence': 70
        }
    }
    
    # مسارات التخزين
    AI_UPLOAD_FOLDER = 'static/uploads/ai_commands'
    AI_TEMP_FOLDER = 'tmp/ai_temp'
    # التخزين
    USE_S3 = os.environ.get('USE_S3', 'False').lower() == 'true'
    if USE_S3:
        AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
        AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
        AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
        S3_BUCKET = os.environ.get('S3_BUCKET')
    
    # إعدادات إضافية
    TIMEZONE = 'Asia/Riyadh'
    DEFAULT_LANGUAGE = 'ar'
    SUPPORTED_LANGUAGES = ['ar', 'en']
    CURRENCY = 'SAR'
    DATE_FORMAT = 'dd/MM/yyyy'

class DevelopmentConfig(Config):
    """إعدادات التطوير"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DEV_DATABASE_URL') or \
        'sqlite:///manag_project.db'

class TestingConfig(Config):
    """إعدادات الاختبار"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('TEST_DATABASE_URL') or \
        'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    """إعدادات الإنتاج"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SECRET_KEY = os.environ.get('SECRET_KEY')
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY')

# خريطة التكوين
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

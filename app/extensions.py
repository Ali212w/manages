"""
extensions.py - امتدادات Flask
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_mail import Mail
from flask_caching import Cache
from celery import Celery
from flask_login import LoginManager
# تهيئة الامتدادات
db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cors = CORS()
mail = Mail()
cache = Cache()
celery = Celery()
login_manager = LoginManager()

def init_extensions(app):
    """تهيئة جميع الامتدادات"""

    migrate.init_app(app, db)
    jwt.init_app(app)
    cors.init_app(app)
    mail.init_app(app)

    # تكوين التخزين المؤقت
    cache.init_app(app, config={
        'CACHE_TYPE': 'redis',
        'CACHE_REDIS_URL': app.config.get('REDIS_URL'),
        'CACHE_DEFAULT_TIMEOUT': 300
    })
    
    # تكوين Celery للمهام الخلفية
    celery.conf.update(
        broker_url=app.config.get('REDIS_URL'),
        result_backend=app.config.get('REDIS_URL'),
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='Asia/Riyadh',
        enable_utc=True,
    )
    
    # جعل السياق متاحاً لمهام Celery
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
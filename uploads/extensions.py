# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from flask_wtf.csrf import CSRFProtect
from flask_caching import Cache
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_cors import CORS
from prometheus_flask_exporter import PrometheusMetrics
from elasticapm.contrib.flask import ElasticAPM
from celery import Celery
import redis

# قاعدة البيانات
db = SQLAlchemy()

# إدارة تسجيل الدخول
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة'
login_manager.login_message_category = 'info'

# الترحيل
migrate = Migrate()

# البريد الإلكتروني
mail = Mail()

# حماية CSRF
csrf = CSRFProtect()

# التخزين المؤقت
cache = Cache(config={'CACHE_TYPE': 'redis', 'CACHE_REDIS_URL': 'redis://localhost:6379/0'})

# البث المباشر
socketio = SocketIO(cors_allowed_origins="*", async_mode='gevent')

# تحديد المعدل
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

# أمان HTTP
talisman = Talisman()

# CORS
cors = CORS()

# مراقبة الأداء
metrics = PrometheusMetrics(app=None)

# مراقبة الأخطاء
apm = ElasticAPM()

# Redis للتخزين المؤقت
redis_client = redis.Redis.from_url('redis://localhost:6379/0')

# Celery للمهام غير المتزامنة
celery = Celery(__name__, broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')
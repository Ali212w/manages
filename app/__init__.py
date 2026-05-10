"""
app.py - ملف التطبيق الرئيسي
نظام إدارة المشاريع الهندسية الذكي
"""
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, g
from flask_login import current_user
from flask_cors import CORS
from flask_socketio import SocketIO
from config import config
from app.extensions import init_extensions
import logging
from logging.handlers import RotatingFileHandler
import json
from flask_babel import Babel
from datetime import datetime
from flask_wtf.csrf import generate_csrf
from app.services.smart_scheduler import SmartProjectManager
from app.services.translator import Translator, _
from app.models import PlatformOwner, PlatformAdmin
from app.extensions import login_manager

# تهيئة الملحقات
db = None

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

socketio = SocketIO()
celery = None
babel = Babel()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة'
login_manager.login_message_category = 'warning'
login_manager.session_protection = 'strong'


def create_app(config_name='default'):
    """إنشاء وتكوين تطبيق Flask"""
    global db

    # إنشاء التطبيق
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # تحميل إعدادات إضافية من ملف .env
    if app.config.get('FLASK_ENV') == 'production':
        app.config.from_pyfile('config_prod.py', silent=True)

    # ضبط الوقت المحلي
    app.config['TIMEZONE'] = 'Asia/Riyadh'



    @app.before_request
    def set_language():
        """تعيين اللغة قبل كل طلب"""
        # تحميل الترجمات
        Translator.load_translations()

        # تحديد اللغة
        if 'lang' in request.args:
            session['language'] = request.args['lang']
        elif 'language' not in session:
            # اللغة الافتراضية من المستخدم أو العربية
            if current_user.is_authenticated and hasattr(current_user, 'language'):
                session['language'] = current_user.language
            else:
                session['language'] = 'ar'

        # تخزين اللغة في g
        g.current_lang = session.get('language', 'ar')
        g.current_dir = 'rtl' if g.current_lang == 'ar' else 'ltr'

    # تهيئة SQLAlchemy
    import app.models as apmod
    db = apmod.init_models(app)

    with app.app_context():
        from app.models import core_models, task_models, primavera_models
        from app.models import project_models, enterprise_models

        # ⭐ تسجيل أحداث التحديث التلقائي للتكاليف
        try:
            from app.models.events import register_events
            register_events()
            logger.info("✅ تم تفعيل نظام التحديث التلقائي للتكاليف")
        except Exception as e:
            logger.error(f"❌ فشل في تفعيل نظام التحديث التلقائي: {str(e)}")
        if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
            try:
                from app.scheduler2 import init_scheduler
                init_scheduler(app)
                app.logger.info("✅ تم تهيئة المجدول الذكي بنجاح")
            except Exception as e:
                app.logger.error(f"❌ فشل في تهيئة المجدول: {str(e)}")

    # تهيئة CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # تهيئة WebSocket
    socketio.init_app(app, cors_allowed_origins="*", async_mode='eventlet')

    # إعداد التسجيل
    setup_logging(app)
    init_extensions(app)

    # ============================================
    # ⭐ دوال مساعدة للقوالب (Context Processors)
    # ============================================

    @app.context_processor
    def inject_csrf_token():
        """حقن CSRF token في جميع القوالب"""
        def get_csrf_token():
            try:
                return generate_csrf()
            except:
                return ''

        return dict(csrf_token=get_csrf_token)
    # في app/__init__.py - أضف هذه الدالة
    @app.context_processor
    def inject_trial_info():
        """حقن معلومات الخطة المجانية في جميع القوالب"""

        def get_trial_days_remaining():
            if current_user.is_authenticated and hasattr(current_user, 'organization'):
                return current_user.organization.trial_days_remaining
            return 0

        def is_trial_active():
            if current_user.is_authenticated and hasattr(current_user, 'organization'):
                return current_user.organization.is_trial_active
            return False

        def is_trial_expiring_soon():
            if current_user.is_authenticated and hasattr(current_user, 'organization'):
                return current_user.organization.is_trial_expiring_soon
            return False

        def get_trial_percentage():
            if current_user.is_authenticated and hasattr(current_user, 'organization'):
                return current_user.organization.trial_percentage
            return 0

        return {
            'trial_days_remaining': get_trial_days_remaining,
            'is_trial_active': is_trial_active,
            'is_trial_expiring_soon': is_trial_expiring_soon,
            'trial_percentage': get_trial_percentage
        }
    @app.context_processor
    def inject_platform_notifications():
        """حقن إشعارات المنصة في القوالب"""
        from app.models.core_models import PlatformNotification

        def get_platform_unread_count():
            if current_user.is_authenticated and hasattr(current_user, 'role') and current_user.role in ['super_admin', 'admin']:
                return PlatformNotification.query.filter_by(
                    admin_id=current_user.id,
                    is_read=False
                ).count()
            return 0

        def get_platform_high_priority_count():
            if current_user.is_authenticated and hasattr(current_user, 'role') and current_user.role in ['super_admin', 'admin']:
                return PlatformNotification.query.filter_by(
                    admin_id=current_user.id,
                    is_read=False,
                    priority='high'
                ).count()
            return 0

        def get_platform_latest_notifications(limit=5):
            if current_user.is_authenticated and hasattr(current_user, 'role') and current_user.role in ['super_admin', 'admin']:
                return PlatformNotification.query.filter_by(
                    admin_id=current_user.id,
                    is_read=False
                ).order_by(PlatformNotification.created_at.desc()).limit(limit).all()
            return []

        return {
            'platform_unread_count': get_platform_unread_count(),
            'platform_high_priority_count': get_platform_high_priority_count(),
            'platform_latest_notifications': get_platform_latest_notifications()
        }
    @app.context_processor
    def inject_chat_helpers():
        """حقن دوال مساعدة للدردشة في جميع القوالب"""
        from app.models.communication_models import ChatParticipant, ChatMessage, ProjectChat
        from app.models.primavera_models import Activity
        from app.models.task_models import Task
        from app.models.project_models import Project

        def get_unread_chats_count():
            """عدد الرسائل غير المقروءة للمستخدم الحالي"""
            if not current_user.is_authenticated:
                return 0

            try:
                # جلب جميع المحادثات التي يشارك فيها المستخدم
                participations = ChatParticipant.query.filter_by(user_id=current_user.id).all()
                chat_ids = [p.chat_id for p in participations]

                if not chat_ids:
                    return 0

                # حساب الرسائل غير المقروءة
                unread = ChatMessage.query.filter(
                    ChatMessage.chat_id.in_(chat_ids),
                    ChatMessage.sender_id != current_user.id,
                    ChatMessage.is_read == False,
                    ChatMessage.is_deleted == False
                ).count()

                return unread
            except Exception as e:
                return 0

        def get_user_recent_chats(limit=5):
            """آخر 5 محادثات للمستخدم"""
            if not current_user.is_authenticated:
                return []

            try:
                participations = ChatParticipant.query.filter_by(user_id=current_user.id).all()
                chat_ids = [p.chat_id for p in participations]

                chats = ProjectChat.query.filter(
                    ProjectChat.id.in_(chat_ids),
                    ProjectChat.is_archived == False
                ).order_by(ProjectChat.updated_at.desc()).limit(limit).all()

                # إضافة آخر رسالة لكل محادثة وتحديد الاسم المناسب
                for chat in chats:
                    last_message = ChatMessage.query.filter_by(
                        chat_id=chat.id,
                        is_deleted=False
                    ).order_by(ChatMessage.created_at.desc()).first()
                    chat.last_message = last_message

                    # تحديث اسم المحادثة إذا كان مرتبطاً بعنصر (نشاط/مهمة/مشروع)
                    if chat.chat_type == 'activity' and chat.activity_id:
                        activity = Activity.query.get(chat.activity_id)
                        if activity and not chat.name:
                            chat.name = f"مناقشة النشاط: {activity.activity_name}"
                    elif chat.chat_type == 'task' and chat.task_id:
                        task = Task.query.get(chat.task_id)
                        if task and not chat.name:
                            chat.name = f"مناقشة المهمة: {task.task_name}"
                    elif chat.chat_type == 'project' and chat.project_id:
                        project = Project.query.get(chat.project_id)
                        if project and not chat.name:
                            chat.name = f"مناقشة المشروع: {project.name}"

                return chats
            except Exception as e:
                return []

        def get_activity_chat(activity_id):
            """الحصول على محادثة النشاط"""
            if not current_user.is_authenticated:
                return None

            try:
                chat = ProjectChat.query.filter_by(
                    activity_id=activity_id,
                    chat_type='activity',
                    is_archived=False
                ).first()
                return chat
            except Exception:
                return None

        def get_task_chat(task_id):
            """الحصول على محادثة المهمة"""
            if not current_user.is_authenticated:
                return None

            try:
                chat = ProjectChat.query.filter_by(
                    task_id=task_id,
                    chat_type='task',
                    is_archived=False
                ).first()
                return chat
            except Exception:
                return None

        def get_project_chat(project_id):
            """الحصول على محادثة المشروع"""
            if not current_user.is_authenticated:
                return None

            try:
                chat = ProjectChat.query.filter_by(
                    project_id=project_id,
                    chat_type='project',
                    is_archived=False
                ).first()
                return chat
            except Exception:
                return None

        def get_activity_chat_status(activity_id):
            """الحصول على حالة محادثة النشاط (مع عدد الرسائل غير المقروءة)"""
            if not current_user.is_authenticated:
                return {'has_chat': False, 'unread_count': 0}

            try:
                chat = ProjectChat.query.filter_by(
                    activity_id=activity_id,
                    chat_type='activity',
                    is_archived=False
                ).first()

                if chat:
                    unread_count = ChatMessage.query.filter(
                        ChatMessage.chat_id == chat.id,
                        ChatMessage.sender_id != current_user.id,
                        ChatMessage.is_read == False,
                        ChatMessage.is_deleted == False
                    ).count()

                    return {
                        'has_chat': True,
                        'chat_id': chat.id,
                        'unread_count': unread_count,
                        'chat_name': chat.name
                    }
                return {'has_chat': False, 'unread_count': 0}
            except Exception:
                return {'has_chat': False, 'unread_count': 0}

        def get_task_chat_status(task_id):
            """الحصول على حالة محادثة المهمة (مع عدد الرسائل غير المقروءة)"""
            if not current_user.is_authenticated:
                return {'has_chat': False, 'unread_count': 0}

            try:
                chat = ProjectChat.query.filter_by(
                    task_id=task_id,
                    chat_type='task',
                    is_archived=False
                ).first()

                if chat:
                    unread_count = ChatMessage.query.filter(
                        ChatMessage.chat_id == chat.id,
                        ChatMessage.sender_id != current_user.id,
                        ChatMessage.is_read == False,
                        ChatMessage.is_deleted == False
                    ).count()

                    return {
                        'has_chat': True,
                        'chat_id': chat.id,
                        'unread_count': unread_count,
                        'chat_name': chat.name
                    }
                return {'has_chat': False, 'unread_count': 0}
            except Exception:
                return {'has_chat': False, 'unread_count': 0}

        def get_project_chat_status(project_id):
            """الحصول على حالة محادثة المشروع (مع عدد الرسائل غير المقروءة)"""
            if not current_user.is_authenticated:
                return {'has_chat': False, 'unread_count': 0}

            try:
                chat = ProjectChat.query.filter_by(
                    project_id=project_id,
                    chat_type='project',
                    is_archived=False
                ).first()

                if chat:
                    unread_count = ChatMessage.query.filter(
                        ChatMessage.chat_id == chat.id,
                        ChatMessage.sender_id != current_user.id,
                        ChatMessage.is_read == False,
                        ChatMessage.is_deleted == False
                    ).count()

                    return {
                        'has_chat': True,
                        'chat_id': chat.id,
                        'unread_count': unread_count,
                        'chat_name': chat.name
                    }
                return {'has_chat': False, 'unread_count': 0}
            except Exception:
                return {'has_chat': False, 'unread_count': 0}

        def get_chat_url_by_entity(entity_type, entity_id):
            """الحصول على رابط الدردشة حسب نوع العنصر"""
            chat = None

            if entity_type == 'activity':
                chat = get_activity_chat(entity_id)
            elif entity_type == 'task':
                chat = get_task_chat(entity_id)
            elif entity_type == 'project':
                chat = get_project_chat(entity_id)

            if chat:
                return url_for('communication.chat_room', chat_id=chat.id)
            return None

        return {
            # الدوال الأساسية
            'get_unread_chats_count': get_unread_chats_count,
            'get_user_recent_chats': get_user_recent_chats,

            # دوال المحادثات حسب النوع
            'get_activity_chat': get_activity_chat,
            'get_task_chat': get_task_chat,
            'get_project_chat': get_project_chat,

            # دوال حالة المحادثات
            'get_activity_chat_status': get_activity_chat_status,
            'get_task_chat_status': get_task_chat_status,
            'get_project_chat_status': get_project_chat_status,

            # دوال الروابط
            'get_chat_url_by_entity': get_chat_url_by_entity
        }
    @app.context_processor
    def inject_globals():
        """حقن متغيرات عامة في جميع القوالب"""
        from app.models import Notification, Organization, Project, Task

        # إحصائيات الإشعارات
        notifications_count = 0
        recent_notifications = []

        if current_user.is_authenticated:
            # عدد الإشعارات غير المقروءة
            notifications_count = Notification.query.filter_by(
                user_id=current_user.id,
                is_read=False
            ).count()

            # آخر 5 إشعارات
            recent_notifications = Notification.query.filter_by(
                user_id=current_user.id
            ).order_by(
                Notification.created_at.desc()
            ).limit(5).all()

        # إحصائيات المشاريع المتأخرة
        delayed_tasks_count = 0
        if current_user.is_authenticated and hasattr(current_user, 'org_id'):
            delayed_tasks_count = Task.query.join(Project).filter(
                Project.org_id == current_user.org_id,
                Task.status.in_(['pending', 'in_progress'])
                # Task.created_at < datetime.now().date()
            ).count()

        # إحصائيات طلبات التوريد المعلقة
        pending_deliveries_count = 0
        if current_user.is_authenticated and current_user.role in ['org_admin', 'project_manager']:
            from app.models.primavera_models import ResourceDelivery
            pending_deliveries_count = ResourceDelivery.query.filter_by(
                status='pending'
            ).count()

        # الاجتماعات القادمة
        upcoming_meetings_count = 0
        open_issues_count = 0

        if current_user.is_authenticated and hasattr(current_user, 'org_id'):
            from app.models import Meeting, Issue

            today = datetime.now().date()
            upcoming_meetings_count = Meeting.query.join(Project).filter(
                Project.org_id == current_user.org_id,
                Meeting.scheduled_date >= today,
                Meeting.status == 'scheduled'
            ).count()

            open_issues_count = Issue.query.join(Project).filter(
                Project.org_id == current_user.org_id,
                Issue.status.in_(['open', 'in_progress'])
            ).count()

        # دوال مساعدة للوقت
        def time_ago(dt):
            if not dt:
                return ''
            now = datetime.utcnow()
            diff = now - dt

            if diff.days > 365:
                return f'منذ {diff.days // 365} سنة'
            elif diff.days > 30:
                return f'منذ {diff.days // 30} شهر'
            elif diff.days > 0:
                return f'منذ {diff.days} يوم'
            elif diff.seconds > 3600:
                return f'منذ {diff.seconds // 3600} ساعة'
            elif diff.seconds > 60:
                return f'منذ {diff.seconds // 60} دقيقة'
            else:
                return 'منذ لحظات'

        # دالة الحصول على شارة الحالة
        def get_status_badge(status):
            badges = {
                'active': '<span class="badge bg-success">نشط</span>',
                'completed': '<span class="badge bg-info">مكتمل</span>',
                'planning': '<span class="badge bg-warning">قيد التخطيط</span>',
                'suspended': '<span class="badge bg-secondary">معلق</span>',
                'cancelled': '<span class="badge bg-danger">ملغي</span>',
                'delayed': '<span class="badge bg-danger">متأخر</span>',
                'in_progress': '<span class="badge bg-primary">قيد التنفيذ</span>',
                'pending': '<span class="badge bg-warning">قيد الانتظار</span>',
                'approved': '<span class="badge bg-success">معتمد</span>',
                'rejected': '<span class="badge bg-danger">مرفوض</span>'
            }
            return badges.get(status, f'<span class="badge bg-secondary">{status}</span>')

        # الحصول على عدد طلبات التحقق المعلقة
        def get_pending_verifications_count():
            if not current_user.is_authenticated:
                return 0
            from app.models.task_models import TaskRequirementVerification, TaskRequirement, Task
            if current_user.role in ['org_admin', 'project_manager', 'supervisor']:
                return TaskRequirementVerification.query.filter_by(
                    status='pending'
                ).join(TaskRequirement).join(Task).filter(
                    Task.supervisor_id == current_user.id
                ).count()
            return 0

        return {
            # إحصائيات
            'notifications_count': notifications_count,
            'recent_notifications': recent_notifications,
            'delayed_tasks_count': delayed_tasks_count,
            'pending_deliveries_count': pending_deliveries_count,
            'upcoming_meetings_count': upcoming_meetings_count,
            'open_issues_count': open_issues_count,

            # دوال مساعدة
            'time_ago': time_ago,
            'get_status_badge': get_status_badge,
            'get_pending_verifications_count': get_pending_verifications_count,
            'now': datetime.now(),

            # لغة واتجاه
            'current_lang': session.get('language', 'ar'),
            'current_dir': 'rtl' if session.get('language', 'ar') == 'ar' else 'ltr'
        }
    @app.context_processor
    def inject_utility_functions():
        """حقن دوال مساعدة عامة في جميع القوالب"""

        def get_status_badge(status):
            """
            الحصول على شارة الحالة مع لون مناسب
            تستخدم في جميع القوالب لعرض حالة المشاريع والمهام والأنشطة
            """
            status_map = {
                # حالات المشاريع
                'active': '<span class="badge bg-success">نشط</span>',
                'completed': '<span class="badge bg-info">مكتمل</span>',
                'planning': '<span class="badge bg-warning">قيد التخطيط</span>',
                'suspended': '<span class="badge bg-secondary">معلق</span>',
                'cancelled': '<span class="badge bg-danger">ملغي</span>',
                'delayed': '<span class="badge bg-danger">متأخر</span>',
                'critical_delay': '<span class="badge bg-dark">تأخير خطير</span>',
                'in_progress': '<span class="badge bg-primary">قيد التنفيذ</span>',
                'on_hold': '<span class="badge bg-secondary">متوقف</span>',

                # حالات المهام والأنشطة
                'pending': '<span class="badge bg-warning">قيد الانتظار</span>',
                'not_started': '<span class="badge bg-secondary">لم يبدأ</span>',
                'started': '<span class="badge bg-info">بدأ</span>',
                'approved': '<span class="badge bg-success">معتمد</span>',
                'rejected': '<span class="badge bg-danger">مرفوض</span>',
                'submitted': '<span class="badge bg-info">مرسل</span>',
                'under_review': '<span class="badge bg-warning">قيد المراجعة</span>',
                'implemented': '<span class="badge bg-success">منفذ</span>',
                'verified': '<span class="badge bg-success">تم التحقق</span>',
                'failed': '<span class="badge bg-danger">فشل</span>',
                'processing': '<span class="badge bg-primary">قيد المعالجة</span>',

                # حالات المستخدمين
                'org_admin': '<span class="badge bg-danger">مدير مؤسسة</span>',
                'project_manager': '<span class="badge bg-primary">مدير مشروع</span>',
                'supervisor': '<span class="badge bg-info">مشرف</span>',
                'delegate': '<span class="badge bg-warning">مندوب</span>',
                'employee': '<span class="badge bg-secondary">موظف</span>',
                'client': '<span class="badge bg-success">مالك</span>',
                'supplier': '<span class="badge bg-info">مورد</span>',
            }
            return status_map.get(status, f'<span class="badge bg-secondary">{status}</span>')

        def format_currency(amount, currency='SAR'):
            """تنسيق العملة بشكل آمن"""
            currency_symbols = {
                'SAR': 'ر.س',
                'USD': '$',
                'EUR': '€',
                'GBP': '£',
                'AED': 'د.إ',
                'KWD': 'د.ك',
                'QAR': 'ر.ق',
                'BHD': 'د.ب',
                'OMR': 'ر.ع',
                'EGP': 'ج.م',
                'JOD': 'د.ا',
                'LYD': 'د.ل',
                'TND': 'د.ت',
                'MAD': 'د.م',
                'SYP': 'ل.س',
                'IQD': 'د.ع',
                'YER': 'ر.ي',
            }
            symbol = currency_symbols.get(currency, 'ر.س')

            # معالجة شاملة لأنواع البيانات المختلفة
            numeric_amount = 0
            if amount is None:
                numeric_amount = 0
            elif isinstance(amount, (int, float)):
                numeric_amount = amount
            elif isinstance(amount, str):
                try:
                    cleaned = amount.replace(',', '').replace(' ', '').replace('ر.س', '').replace('$', '').strip()
                    numeric_amount = float(cleaned) if cleaned else 0
                except ValueError:
                    numeric_amount = 0
            else:
                numeric_amount = 0

            if currency in ['KWD', 'BHD', 'OMR']:
                return f"{numeric_amount:,.3f} {symbol}"
            return f"{numeric_amount:,.2f} {symbol}"

        def format_date(date_obj, format_str='%Y-%m-%d'):
            """تنسيق التاريخ بشكل آمن"""
            if date_obj is None:
                return '-'
            if hasattr(date_obj, 'strftime'):
                return date_obj.strftime(format_str)
            return str(date_obj)

        def format_datetime(dt_obj, format_str='%Y-%m-%d %H:%M'):
            """تنسيق التاريخ والوقت بشكل آمن"""
            if dt_obj is None:
                return '-'
            if hasattr(dt_obj, 'strftime'):
                return dt_obj.strftime(format_str)
            return str(dt_obj)

        def get_progress_color(progress):
            """الحصول على لون شريط التقدم بناءً على النسبة"""
            if progress is None:
                return 'secondary'
            if progress >= 75:
                return 'success'
            elif progress >= 40:
                return 'warning'
            elif progress > 0:
                return 'info'
            return 'secondary'

        def truncate_text(text, length=100, suffix='...'):
            """قص النص مع إضافة نقاط"""
            if text is None:
                return ''
            if not isinstance(text, str):
                text = str(text)
            if len(text) <= length:
                return text
            return text[:length] + suffix

        def time_ago(dt):
            """حساب الوقت المنقضي منذ تاريخ معين"""
            if dt is None:
                return ''
            now = datetime.now()
            diff = now - dt

            if diff.days > 365:
                return f'منذ {diff.days // 365} سنة'
            elif diff.days > 30:
                return f'منذ {diff.days // 30} شهر'
            elif diff.days > 0:
                return f'منذ {diff.days} يوم'
            elif diff.seconds > 3600:
                return f'منذ {diff.seconds // 3600} ساعة'
            elif diff.seconds > 60:
                return f'منذ {diff.seconds // 60} دقيقة'
            else:
                return 'منذ لحظات'

        def get_task_progress(task):
            """الحصول على نسبة تقدم المهمة بشكل آمن"""
            if task is None:
                return 0
            try:
                if hasattr(task, 'progress') and task.progress:
                    return task.progress.progress_percentage or 0
                return 0
            except Exception:
                return 0

        def get_task_planned_date(task):
            """الحصول على التاريخ المخطط للمهمة"""
            if task is None:
                return None
            try:
                if hasattr(task, 'planning') and task.planning:
                    return task.planning.planned_start
                return None
            except Exception:
                return None

        def get_task_planned_end(task):
            """الحصول على تاريخ الانتهاء المخطط للمهمة"""
            if task is None:
                return None
            try:
                if hasattr(task, 'planning') and task.planning:
                    return task.planning.planned_finish
                return None
            except Exception:
                return None

        def get_status_text(status):
            """ترجمة حالة المهمة أو النشاط"""
            status_map = {
                'completed': 'مكتمل',
                'in_progress': 'قيد التنفيذ',
                'pending': 'قيد الانتظار',
                'not_started': 'لم يبدأ',
                'delayed': 'متأخر',
                'cancelled': 'ملغي',
                'active': 'نشط',
                'planning': 'تخطيط',
                'suspended': 'معلق',
                'approved': 'معتمد',
                'rejected': 'مرفوض',
                'verified': 'تم التحقق'
            }
            return status_map.get(status, status)

        def get_priority_badge(priority):
            """الحصول على شارة الأولوية"""
            if priority is None:
                return '<span class="badge bg-secondary">متوسطة</span>'

            priority_map = {
                5: '<span class="badge bg-danger">حرجة</span>',
                4: '<span class="badge bg-warning">عالية</span>',
                3: '<span class="badge bg-info">متوسطة</span>',
                2: '<span class="badge bg-secondary">منخفضة</span>',
                1: '<span class="badge bg-light text-dark">منخفضة جداً</span>',
                'critical': '<span class="badge bg-danger">حرجة</span>',
                'high': '<span class="badge bg-warning">عالية</span>',
                'medium': '<span class="badge bg-info">متوسطة</span>',
                'low': '<span class="badge bg-secondary">منخفضة</span>'
            }
            return priority_map.get(priority, '<span class="badge bg-secondary">متوسطة</span>')

        def get_risk_badge(risk_level):
            """الحصول على شارة مستوى الخطر"""
            risk_map = {
                'critical': '<span class="badge bg-danger">حرجة</span>',
                'high': '<span class="badge bg-warning">عالية</span>',
                'medium': '<span class="badge bg-info">متوسطة</span>',
                'low': '<span class="badge bg-success">منخفضة</span>'
            }
            return risk_map.get(risk_level, f'<span class="badge bg-secondary">{risk_level}</span>')

        def get_icon_class(notification_type):
            """الحصول على كلاس الأيقونة حسب نوع الإشعار"""
            icons = {
                'delivery': 'fas fa-truck',
                'task': 'fas fa-tasks',
                'project': 'fas fa-project-diagram',
                'risk': 'fas fa-shield-alt',
                'issue': 'fas fa-bug',
                'verification': 'fas fa-clipboard-check',
                'user': 'fas fa-user',
                'document': 'fas fa-file-alt',
                'resource': 'fas fa-cube',
                'message': 'fas fa-comment',
                'system': 'fas fa-server',
                'performance': 'fas fa-chart-line',
                'eps': 'fas fa-sitemap'
            }
            for key, icon in icons.items():
                if key in notification_type:
                    return icon
            return 'fas fa-bell'

        return {
            # الاسم المطلوب في القالب (getStatusBadge)
            'getStatusBadge': get_status_badge,
            # أسماء بديلة للتوافق
            'status_badge': get_status_badge,
            'get_status_badge': get_status_badge,
            # دوال التقدم والتواريخ
            'get_task_progress': get_task_progress,
            'get_task_planned_date': get_task_planned_date,
            'get_task_planned_end': get_task_planned_end,
            # دوال أخرى
            'formatCurrency': format_currency,
            'format_currency': format_currency,
            'formatDate': format_date,
            'format_date': format_date,
            'formatDateTime': format_datetime,
            'format_datetime': format_datetime,
            'getProgressColor': get_progress_color,
            'get_progress_color': get_progress_color,
            'truncateText': truncate_text,
            'truncate_text': truncate_text,
            'timeAgo': time_ago,
            'time_ago': time_ago,
            'getPriorityBadge': get_priority_badge,
            'get_priority_badge': get_priority_badge,
            'getRiskBadge': get_risk_badge,
            'get_risk_badge': get_risk_badge,
            'getIconClass': get_icon_class,
            'get_icon_class': get_icon_class,
        }

    @app.context_processor
    def inject_context():
        """حقن متغيرات في جميع القوالب"""
        from app.models import Notification

        def get_user_notifications(user_id, limit=5):
            """الحصول على إشعارات المستخدم"""
            if not user_id:
                return []
            return Notification.query.filter_by(
                user_id=user_id
            ).order_by(
                Notification.created_at.desc()
            ).limit(limit).all()

        return {
            'current_year': datetime.now().year,
            'app_name': app.config.get('APP_NAME_AR', 'نظام إدارة المشاريع'),
            'current_user': current_user,
            'config': app.config,
            'now': datetime.now(),
            'get_user_notifications': get_user_notifications
        }

    @app.context_processor
    def inject_verification_helpers():
        """إضافة دوال مساعدة للتحقق في القوالب"""
        from app.models import TaskRequirementVerification, TaskRequirement, Task

        def get_pending_verifications_count():
            """عدد طلبات التحقق المعلقة للمستخدم الحالي"""
            if current_user.is_authenticated:
                if current_user.role in ['org_admin', 'project_manager', 'supervisor']:
                    return TaskRequirementVerification.query.filter_by(
                        status='pending'
                    ).join(TaskRequirement).join(Task).filter(
                        Task.supervisor_id == current_user.id
                    ).count()
            return 0

        return {
            'get_pending_verifications_count': get_pending_verifications_count
        }

    @app.context_processor
    def inject_translations():
        """
        حقن دوال الترجمة في جميع القوالب
        هذه الدالة تجعل دوال الترجمة متاحة في كل قالب دون الحاجة لاستيرادها
        """
        from app.services.translator import (
            _, __, get_current_lang, get_direction, get_text_align,
            reload_translations, format_date, format_number,
            format_currency, get_status_text
        )

        # الحصول على اللغة الحالية من المتغير العام g
        current_lang = getattr(g, 'current_lang', 'ar')
        current_dir = getattr(g, 'current_dir', 'rtl')

        return {
            # دوال الترجمة الأساسية
            '_': _,           # دالة الترجمة الرئيسية
            '__': __,         # اسم بديل للدالة
            'gettext': _,     # اسم بديل آخر

            # دوال اللغة
            'get_current_lang': get_current_lang,
            'get_direction': get_direction,
            'get_text_align': get_text_align,
            'current_lang': current_lang,
            'current_dir': current_dir,
            'is_rtl': current_dir == 'rtl',
            'is_ltr': current_dir == 'ltr',

            # دوال التنسيق
            'format_date': format_date,
            'format_number': format_number,
            'format_currency': format_currency,
            'get_status_text': get_status_text,

            # دوال إضافية (للتطوير)
            'reload_translations': reload_translations,
        }

    @app.context_processor
    def inject_notification_helpers():
        """حقن دوال مساعدة للإشعارات"""

        def notification_icon(notification_type):
            """الحصول على أيقونة الإشعار"""
            icons = {
                'resource_request': 'fas fa-truck',
                'delivery_pending': 'fas fa-box',
                'delivery_confirmed': 'fas fa-check-circle',
                'delivery_rejected': 'fas fa-times-circle',
                'task_assigned': 'fas fa-tasks',
                'task_started': 'fas fa-play',
                'task_completed': 'fas fa-check',
                'system': 'fas fa-info-circle',
                'suggestion': 'fas fa-lightbulb',
                'ai_command': 'fas fa-robot'
            }
            icon = icons.get(notification_type, 'fas fa-bell')
            return f'<i class="{icon}"></i>'

        def notification_color(notification_type):
            """الحصول على لون الإشعار"""
            colors = {
                'resource_request': 'warning',
                'delivery_pending': 'info',
                'delivery_confirmed': 'success',
                'delivery_rejected': 'danger',
                'task_assigned': 'primary',
                'task_started': 'success',
                'task_completed': 'success',
                'system': 'secondary',
                'suggestion': 'warning',
                'ai_command': 'info'
            }
            return colors.get(notification_type, 'secondary')

        def time_ago(dt):
            """حساب الوقت المنقضي"""
            if not dt:
                return ''
            now = datetime.now()
            diff = now - dt

            if diff.days > 365:
                return f'منذ {diff.days // 365} سنة'
            elif diff.days > 30:
                return f'منذ {diff.days // 30} شهر'
            elif diff.days > 0:
                return f'منذ {diff.days} يوم'
            elif diff.seconds > 3600:
                return f'منذ {diff.seconds // 3600} ساعة'
            elif diff.seconds > 60:
                return f'منذ {diff.seconds // 60} دقيقة'
            else:
                return 'منذ لحظات'

        return {
            'notification_icon': notification_icon,
            'notification_color': notification_color,
            'time_ago': time_ago
        }

    @app.before_request
    def before_request():
        """تنفيذ قبل كل طلب - تعيين اللغة والاتجاه"""
        from app.services.translator import get_direction

        # تحميل الترجمات
        Translator.load_translations()

        # تحديد اللغة
        if 'lang' in request.args:
            session['language'] = request.args['lang']
        elif 'language' not in session:
            # محاولة الحصول من المستخدم
            if current_user.is_authenticated and hasattr(current_user, 'language'):
                session['language'] = current_user.language
            else:
                session['language'] = 'ar'

        # تخزين اللغة والاتجاه في المتغير العام g
        g.current_lang = session.get('language', 'ar')
        g.current_dir = 'rtl' if g.current_lang == 'ar' else 'ltr'
    # تسجيل Blueprints
    register_blueprints(app)

    # تسجيل معالجات الأخطاء
    register_error_handlers(app)

    # تسجيل الفلاتر
    register_filters(app)

    # إنشاء مجلدات الرفع
    create_upload_folders(app)

    # مسار البداية
    @app.route('/')
    def index():
        """الصفحة الرئيسية"""
        if current_user.is_authenticated:
            from app.routes.auth_routes import redirect_to_user_dashboard
            return redirect_to_user_dashboard()
        return render_template('layouts/index.html')

    @app.route('/change-language/<lang>')
    def change_language(lang):
        """تغيير اللغة"""
        if lang in ['ar', 'en']:
            session['language'] = lang

            # تحديث لغة المستخدم في قاعدة البيانات
            if current_user.is_authenticated and hasattr(current_user, 'language'):
                current_user.language = lang
                db.session.commit()

            # إعادة تحميل الترجمات
            from app.services.translator import reload_translations
            reload_translations()

            flash(_('language_changed_successfully'), 'success')

        return redirect(request.referrer or url_for('index'))

    @app.route('/health')
    def health_check():
        """فحص صحة التطبيق"""
        try:
            # فحص الاتصال بقاعدة البيانات
            db.session.execute('SELECT 1')
            return jsonify({
                'status': 'healthy',
                'database': 'connected',
                'timestamp': datetime.utcnow().isoformat()
            }), 200
        except Exception as e:
            return jsonify({
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }), 500

    return app


def setup_logging(app):
    """إعداد نظام التسجيل"""
    if not app.debug and not app.testing:
        # إنشاء مجلد السجلات
        if not os.path.exists('logs'):
            os.mkdir('logs')

        # ملف السجل مع التدوير
        file_handler = RotatingFileHandler('logs/project_management.log',
                                          maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s '
            '[in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('بدء تشغيل نظام إدارة المشاريع')


def register_blueprints(app):
    """تسجيل Blueprints"""
    from app.routes.auth_routes import auth_bp
    from app.routes.dashboard_routes import dashboard_bp
    from app.routes.project_routes import project_bp
    from app.routes.task_routes import task_bp
    from app.routes.document_routes import document_bp
    from app.routes.company_routes import company_bp
    from app.routes.platform_routes import platform_bp
    from app.routes.employee_routes import employee_bp
    from app.routes.admin_routes import admin_bp
    from app.routes.project_tracking_routes import tracking_bp
    from app.routes.communication_routes import communication_bp
    from app.routes.upload_routes import upload_bp
    from app.routes.template_routes import template_bp
    from app.routes.notifications_routes import notifications_bp
    from app.routes.primavera_routes import primavera_bp
    from app.routes.enterprise_routes import enterprise_bp
    from app.routes.codes_routes import codes_bp
    from app.routes.resource_routes import resource_bp
    from app.routes.supplier_routes import supplier_bp
    from app.routes.ai_routes import ai_bp
    from app.routes.delivery_routes import delivery_bp
    from app.routes.attachment_routes import attachment_bp
    from app.routes.client_routes import client_bp
    from app.routes.consultant_routes import consultant_bp
    from app.routes.role_dashboard_routes import role_dashboard_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
    app.register_blueprint(project_bp, url_prefix='/projects')
    app.register_blueprint(task_bp, url_prefix='/tasks')
    app.register_blueprint(document_bp, url_prefix='/documents')
    app.register_blueprint(company_bp, url_prefix='/company')
    app.register_blueprint(platform_bp, url_prefix='/platform')
    app.register_blueprint(employee_bp, url_prefix='/employee')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tracking_bp, url_prefix='/tracking')
    app.register_blueprint(communication_bp, url_prefix='/communication')
    app.register_blueprint(upload_bp, url_prefix='/upload')
    app.register_blueprint(template_bp, url_prefix='/template')
    app.register_blueprint(notifications_bp, url_prefix='/notifications')
    app.register_blueprint(primavera_bp, url_prefix='/primavera')
    app.register_blueprint(enterprise_bp, url_prefix='/enterprise')
    app.register_blueprint(ai_bp, url_prefix='/ai')
    app.register_blueprint(codes_bp, url_prefix='/codes')
    app.register_blueprint(resource_bp, url_prefix='/resources')
    app.register_blueprint(supplier_bp, url_prefix='/supplier')
    app.register_blueprint(delivery_bp, url_prefix='/delivery')
    app.register_blueprint(attachment_bp, url_prefix='/attachments')
    app.register_blueprint(client_bp, url_prefix='/client')
    app.register_blueprint(consultant_bp, url_prefix='/consultant')
    app.register_blueprint(role_dashboard_bp)


def register_error_handlers(app):
    """تسجيل معالجات الأخطاء"""

    @app.errorhandler(404)
    def not_found_error(error):
        if request.accept_mimetypes.accept_json and \
           not request.accept_mimetypes.accept_html:
            return jsonify({'error': 'الصفحة غير موجودة'}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        if request.accept_mimetypes.accept_json and \
           not request.accept_mimetypes.accept_html:
            return jsonify({'error': 'غير مصرح بالوصول'}), 403
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        if request.accept_mimetypes.accept_json and \
           not request.accept_mimetypes.accept_html:
            return jsonify({'error': 'خطأ داخلي في الخادم'}), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(413)
    def too_large_error(error):
        if request.accept_mimetypes.accept_json and \
           not request.accept_mimetypes.accept_html:
            return jsonify({'error': 'الملف كبير جداً'}), 413
        return render_template('errors/413.html'), 413


def register_filters(app):
    """تسجيل الفلاتر المخصصة"""

    @app.template_filter('format_date')
    def format_date(value, format='%Y-%m-%d'):
        """تنسيق التاريخ"""
        if value is None:
            return ''
        return value.strftime(format)

    @app.template_filter('format_currency')
    def format_currency_filter(amount, currency='SAR'):
        """تنسيق المبلغ مع رمز العملة - نسخة آمنة"""
        currency_symbols = {
            'SAR': 'ر.س',
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'AED': 'د.إ',
            'KWD': 'د.ك',
            'QAR': 'ر.ق',
            'BHD': 'د.ب',
            'OMR': 'ر.ع',
            'EGP': 'ج.م',
            'JOD': 'د.ا',
            'LYD': 'د.ل',
            'TND': 'د.ت',
            'MAD': 'د.م',
            'SYP': 'ل.س',
            'IQD': 'د.ع',
            'YER': 'ر.ي',
        }

        symbol = currency_symbols.get(currency, 'ر.س')

        numeric_amount = 0
        if amount is None:
            numeric_amount = 0
        elif isinstance(amount, (int, float)):
            numeric_amount = amount
        elif isinstance(amount, str):
            try:
                cleaned = amount.replace(',', '').replace(' ', '').replace('ر.س', '').replace('$', '').strip()
                numeric_amount = float(cleaned) if cleaned else 0
            except ValueError:
                numeric_amount = 0
        else:
            numeric_amount = 0

        if currency in ['KWD', 'BHD', 'OMR']:
            return f"{numeric_amount:,.3f} {symbol}"
        else:
            return f"{numeric_amount:,.2f} {symbol}"

    @app.template_filter('truncate')
    def truncate(value, length=100):
        """تقليم النص - معالج للقيم الفارغة"""
        if value is None:
            return ''
        if not isinstance(value, str):
            value = str(value)
        if len(value) <= length:
            return value
        return value[:length] + '...'

    @app.template_filter('status_badge')
    def status_badge_filter(status):
        """فلتر لتحويل الحالة إلى شارة HTML"""
        status_map = {
            'active':        '<span class="badge bg-success">نشط</span>',
            'completed':     '<span class="badge bg-info">مكتمل</span>',
            'planning':      '<span class="badge bg-warning">قيد التخطيط</span>',
            'suspended':     '<span class="badge bg-secondary">معلق</span>',
            'cancelled':     '<span class="badge bg-danger">ملغي</span>',
            'delayed':       '<span class="badge bg-danger">متأخر</span>',
            'critical_delay':'<span class="badge bg-dark">تأخير خطير</span>',
            'in_progress':   '<span class="badge bg-primary">قيد التنفيذ</span>',
            'on_hold':       '<span class="badge bg-secondary">متوقف</span>',
            'pending':       '<span class="badge bg-warning">قيد الانتظار</span>',
            'not_started':   '<span class="badge bg-secondary">لم يبدأ</span>',
            'approved':      '<span class="badge bg-success">معتمد</span>',
            'rejected':      '<span class="badge bg-danger">مرفوض</span>',
        }
        return status_map.get(status, f'<span class="badge bg-secondary">{status}</span>')


def create_upload_folders(app):
    """إنشاء مجلدات الرفع"""
    folders = [
        app.config['UPLOAD_FOLDER'],
        os.path.join(app.config['UPLOAD_FOLDER'], 'documents'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'images'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'exports'),
        os.path.join(app.config['UPLOAD_FOLDER'], 'temp')
    ]

    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)


def create_initial_data():
    """إنشاء البيانات الأولية للنظام"""
    global db
    try:
        # إنشاء المنصة (Platform Owner)
        platform = PlatformOwner.query.first()
        if not platform:
            platform = PlatformOwner(
                company_name='منصة إدارة المشاريع',
                email='info@platform.com',
                commercial_register='0000000',
                phone='777898117'
            )
            db.session.add(platform)
            db.session.commit()

            # إنشاء مدير المنصة الرئيسي (Super Admin)
            super_admin = PlatformAdmin(
                platform_id=platform.id,
                username='superadmin',
                email='najmyjomaan@gmail.com',
                full_name='المشرف العام',
                role='super_admin',
                is_active=True
            )
            super_admin.set_password('admin123')
            db.session.add(super_admin)

            # إنشاء مدير منصة عادي
            admin = PlatformAdmin(
                platform_id=platform.id,
                username='admin',
                email='admin@platform.com',
                full_name='مدير المنصة',
                role='admin',
                is_active=True
            )
            admin.set_password('Admin123!')
            db.session.add(admin)

            db.session.commit()

            print("="*50)
            print("✅ تم إنشاء المنصة ومدرائها بنجاح")
            print("="*50)
            print("📧 المشرف العام: superadmin / admin123")
            print("📧 مدير المنصة: admin / Admin123!")
            print("="*50)

    except Exception as e:
        print(f"❌ خطأ في إنشاء البيانات الأولية: {str(e)}")
        db.session.rollback()


# إنشاء التطبيق
app = create_app()


# # إذا كنت تريد تشغيل التطبيق مباشرة
# if __name__ == '__main__':
#     socketio.run(app, debug=True, host='0.0.0.0', port=5000)
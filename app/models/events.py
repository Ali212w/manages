"""
events.py - أحداث SQLAlchemy للتحديث التلقائي للتكاليف والمؤشرات
تم التحسين لمنع قفل قاعدة البيانات (database is locked)
"""

from sqlalchemy import event
import logging
import time
from threading import Lock
from flask import current_app, g

# إعداد التسجيل
logger = logging.getLogger(__name__)

# قفل لمنع التحديثات المتزامنة (لحماية SQLite من القفل)
_update_lock = Lock()

# سجل آخر وقت تحديث لكل كيان (لمنع التحديثات المتكررة جداً)
_last_update_time = {}

# سجل المعرفات قيد التحديث حالياً (لمنع الحلقات اللانهائية)
_updating_entities = set()


def _safe_update(entity_type, entity_id, delay=0.5):
    """
    تحديث آمن يتجنب التكرار ومشاكل الجلسة وقفل قاعدة البيانات
    
    Args:
        entity_type: نوع الكيان (task, activity, project, wbs)
        entity_id: معرف الكيان
        delay: الحد الأدنى للفاصل الزمني بين التحديثات (بالثواني)
    """
    lock_key = f"{entity_type}:{entity_id}"
    
    # منع التكرار (حماية ضد الحلقات اللانهائية)
    if lock_key in _updating_entities:
        logger.debug(f"⏭️ تخطي التحديث - {lock_key} قيد التحديث بالفعل")
        return False
    
    # منع التحديثات المتكررة جداً (حماية ضد flood)
    with _update_lock:
        now = time.time()
        last_time = _last_update_time.get(lock_key, 0)
        if now - last_time < delay:
            logger.debug(f"⏭️ تخطي التحديث - {lock_key} تم تحديثه منذ {now - last_time:.1f} ثانية")
            return False
        
        _last_update_time[lock_key] = now
        _updating_entities.add(lock_key)
    
    try:
        # استخدام current_app للحصول على سياق التطبيق
        with current_app.app_context():
            from app.services.cost_update_service import CostUpdateService
            
            logger.debug(f"🔄 تحديث {entity_type} {entity_id}")
            
            # إضافة معالجة خاصة لـ SQLite لتجنب القفل
            if entity_type == 'task':
                CostUpdateService.update_task_cost(entity_id)
            elif entity_type == 'activity':
                CostUpdateService.update_activity_cost(entity_id)
            elif entity_type == 'project':
                CostUpdateService.update_project_cost(entity_id)
            elif entity_type == 'wbs':
                CostUpdateService.update_wbs_cost(entity_id)
            
            return True
            
    except Exception as e:
        # لا نريد إيقاف التطبيق بسبب خطأ في التحديث
        logger.warning(f"⚠️ تحذير في تحديث {entity_type} {entity_id}: {str(e)}")
        return False
    finally:
        _updating_entities.discard(lock_key)


def _get_changed_fields(target):
    """
    الحصول على الحقول التي تغيرت بشكل آمن
    """
    try:
        if hasattr(target, '_sa_instance_state'):
            modified = target._sa_instance_state.modified
            if isinstance(modified, (set, list, tuple)):
                return set(modified)
    except Exception:
        pass
    return set()


def _is_update_enabled():
    """
    التحقق مما إذا كانت التحديثات التلقائية مفعلة
    يمكن تعطيلها مؤقتاً عن طريق متغير البيئة
    """
    import os
    return os.environ.get('ENABLE_AUTO_UPDATES', 'True').lower() == 'true'


# ============================================
# دوال مساعدة لتجنب الاستيراد الدائري
# ============================================

def _get_models():
    """الحصول على النماذج - يتم استدعاؤها داخل الأحداث فقط"""
    from app.models.task_models import (
        Task, TaskResource, TaskExecution, TaskProgressUpdate
    )
    from app.models.primavera_models import (
        Activity, ActivityResource, ActivityExpense, Resource, WBS
    )
    from app.models.project_models import Project
    
    return {
        'Task': Task,
        'TaskResource': TaskResource,
        'TaskExecution': TaskExecution,
        'TaskProgressUpdate': TaskProgressUpdate,
        'Activity': Activity,
        'ActivityResource': ActivityResource,
        'ActivityExpense': ActivityExpense,
        'Resource': Resource,
        'Project': Project,
        'WBS': WBS
    }


# ============================================
# 1. أحداث المهام (Task)
# ============================================

def register_task_events():
    """تسجيل أحداث المهام"""
    if not _is_update_enabled():
        logger.info("⚠️ التحديثات التلقائية للمهام معطلة")
        return
    
    models = _get_models()
    TaskResource = models['TaskResource']
    Task = models['Task']
    TaskExecution = models['TaskExecution']
    TaskProgressUpdate = models['TaskProgressUpdate']
    
    @event.listens_for(TaskResource, 'after_update')
    @event.listens_for(TaskResource, 'after_insert')
    def task_resource_after_change(mapper, connection, target):
        try:
            # تأخير قصير لمنع التحديثات المتكررة
            _safe_update('task', target.task_id, delay=1.0)
        except Exception as e:
            logger.error(f"خطأ في TaskResource: {e}")
    
    @event.listens_for(Task, 'after_update')
    def task_after_change(mapper, connection, target):
        try:
            changed = _get_changed_fields(target)
            # تحديث المشروع فقط إذا تغيرت حقول مهمة
            if 'status' in changed or 'progress_percentage' in changed:
                _safe_update('task', target.id, delay=0.5)
                if target.activity_id:
                    _safe_update('activity', target.activity_id, delay=0.5)
                _safe_update('project', target.project_id, delay=0.5)
        except Exception as e:
            logger.error(f"خطأ في Task: {e}")
    
    @event.listens_for(TaskExecution, 'after_update')
    @event.listens_for(TaskExecution, 'after_insert')
    def task_execution_after_change(mapper, connection, target):
        try:
            _safe_update('task', target.task_id, delay=0.5)
        except Exception as e:
            logger.error(f"خطأ في TaskExecution: {e}")
    
    @event.listens_for(TaskProgressUpdate, 'after_insert')
    def progress_update_after_insert(mapper, connection, target):
        try:
            _safe_update('task', target.task_id, delay=0.5)
        except Exception as e:
            logger.error(f"خطأ في TaskProgressUpdate: {e}")


# ============================================
# 2. أحداث الأنشطة (Activity)
# ============================================

def register_activity_events():
    """تسجيل أحداث الأنشطة"""
    if not _is_update_enabled():
        logger.info("⚠️ التحديثات التلقائية للأنشطة معطلة")
        return
    
    models = _get_models()
    ActivityResource = models['ActivityResource']
    Activity = models['Activity']
    ActivityExpense = models['ActivityExpense']
    
    @event.listens_for(ActivityResource, 'after_update')
    @event.listens_for(ActivityResource, 'after_insert')
    def activity_resource_after_change(mapper, connection, target):
        try:
            _safe_update('activity', target.activity_id, delay=0.5)
        except Exception as e:
            logger.error(f"خطأ في ActivityResource: {e}")
    
    @event.listens_for(Activity, 'after_update')
    def activity_after_change(mapper, connection, target):
        try:
            changed = _get_changed_fields(target)
            # تحديث WBS والمشروع فقط إذا تغيرت حقول مهمة
            important_fields = {'status', 'progress_percentage', 'actual_start', 'actual_finish'}
            if important_fields.intersection(changed):
                _safe_update('activity', target.id, delay=0.5)
                if target.wbs_id:
                    _safe_update('wbs', target.wbs_id, delay=1.0)
                _safe_update('project', target.project_id, delay=1.0)
        except Exception as e:
            logger.error(f"خطأ في Activity: {e}")
    
    @event.listens_for(ActivityExpense, 'after_update')
    @event.listens_for(ActivityExpense, 'after_insert')
    def expense_after_change(mapper, connection, target):
        try:
            if target.is_approved:
                _safe_update('activity', target.activity_id, delay=1.0)
        except Exception as e:
            logger.error(f"خطأ في ActivityExpense: {e}")


# ============================================
# 3. أحداث الموارد (Resource)
# ============================================

def register_resource_events():
    """تسجيل أحداث الموارد"""
    if not _is_update_enabled():
        logger.info("⚠️ التحديثات التلقائية للموارد معطلة")
        return
    
    models = _get_models()
    Resource = models['Resource']
    
    @event.listens_for(Resource, 'after_update')
    def resource_after_change(mapper, connection, target):
        try:
            changed = _get_changed_fields(target)
            # تحديث التكاليف فقط إذا تغير سعر الوحدة
            if 'cost_per_unit' in changed:
                models_local = _get_models()
                TaskResource = models_local['TaskResource']
                ActivityResource = models_local['ActivityResource']
                
                # تحديث المهام المرتبطة (مع تأخير)
                task_resources = TaskResource.query.filter_by(resource_id=target.id).all()
                for tr in task_resources:
                    _safe_update('task', tr.task_id, delay=1.0)
                
                # تحديث الأنشطة المرتبطة (مع تأخير)
                activity_resources = ActivityResource.query.filter_by(resource_id=target.id).all()
                for ar in activity_resources:
                    _safe_update('activity', ar.activity_id, delay=1.0)
        except Exception as e:
            logger.error(f"خطأ في Resource: {e}")


# ============================================
# 4. أحداث المشروع و WBS
# ============================================

def register_project_events():
    """تسجيل أحداث المشاريع و WBS"""
    if not _is_update_enabled():
        logger.info("⚠️ التحديثات التلقائية للمشاريع معطلة")
        return
    
    models = _get_models()
    Project = models['Project']
    WBS = models['WBS']
    
    @event.listens_for(Project, 'after_update')
    def project_after_change(mapper, connection, target):
        try:
            changed = _get_changed_fields(target)
            budget_fields = {'current_budget', 'original_budget'}
            if budget_fields.intersection(changed):
                # تأخير أطول لتجنب التحديثات المتكررة
                _safe_update('project', target.id, delay=2.0)
        except Exception as e:
            logger.error(f"خطأ في Project: {e}")
    
    @event.listens_for(WBS, 'after_update')
    def wbs_after_change(mapper, connection, target):
        try:
            _safe_update('wbs', target.id, delay=1.0)
            if target.project_id:
                _safe_update('project', target.project_id, delay=1.5)
        except Exception as e:
            logger.error(f"خطأ في WBS: {e}")


# ============================================
# 5. أحداث الأداء (Performance)
# ============================================

def register_performance_events():
    """تسجيل أحداث الأداء"""
    if not _is_update_enabled():
        logger.info("⚠️ التحديثات التلقائية للأداء معطلة")
        return
    
    models = _get_models()
    Activity = models['Activity']
    
    @event.listens_for(Activity, 'after_update')
    def activity_progress_change(mapper, connection, target):
        try:
            changed = _get_changed_fields(target)
            # تحديث المشروع فقط عندما يتغير التقدم بشكل كبير
            if 'progress_percentage' in changed:
                old_progress = getattr(target, '_old_progress', 0)
                new_progress = target.progress_percentage or 0
                
                # تحديث المشروع فقط إذا تغير التقدم بأكثر من 1% (تقليل التحديثات)
                if abs(new_progress - old_progress) >= 1:
                    setattr(target, '_old_progress', new_progress)
                    _safe_update('project', target.project_id, delay=2.0)
        except Exception as e:
            logger.error(f"خطأ في Performance: {e}")


# ============================================
# دالة لتعطيل الأحداث مؤقتاً
# ============================================

def disable_auto_updates():
    """تعطيل التحديثات التلقائية مؤقتاً (للمهام الكبيرة)"""
    import os
    os.environ['ENABLE_AUTO_UPDATES'] = 'False'
    logger.info("⏸️ تم تعطيل التحديثات التلقائية مؤقتاً")


def enable_auto_updates():
    """إعادة تفعيل التحديثات التلقائية"""
    import os
    os.environ['ENABLE_AUTO_UPDATES'] = 'True'
    logger.info("▶️ تم إعادة تفعيل التحديثات التلقائية")


def is_update_in_progress():
    """التحقق مما إذا كانت هناك تحديثات قيد التنفيذ"""
    with _update_lock:
        return len(_updating_entities) > 0


def get_update_status():
    """الحصول على حالة التحديثات الحالية"""
    with _update_lock:
        return {
            'active_updates': len(_updating_entities),
            'active_updates_list': list(_updating_entities),
            'last_updates': dict(list(_last_update_time.items())[-10:])  # آخر 10 تحديثات
        }


# ============================================
# الدالة الرئيسية
# ============================================

def register_events():
    """تسجيل جميع الأحداث"""
    logger.info("=" * 60)
    logger.info("🚀 بدء تسجيل أحداث التحديث التلقائي")
    logger.info(f"📊 حالة التحديثات: {'مفعلة' if _is_update_enabled() else 'معطلة'}")
    
    # تسجيل الأحداث فقط إذا كانت مفعلة
    if _is_update_enabled():
        register_task_events()
        register_activity_events()
        register_performance_events()
        register_resource_events()
        register_project_events()
        logger.info("✅ تم تسجيل جميع الأحداث بنجاح")
    else:
        logger.info("⚠️ الأحداث معطلة (ENABLE_AUTO_UPDATES=False)")
    
    logger.info("=" * 60)


# ============================================
# تسجيل تلقائي عند تحميل الملف (في وضع الإنتاج فقط)
# ============================================

def _auto_register():
    """تسجيل تلقائي مع التحقق من بيئة التشغيل"""
    import os
    # لا نسجل الأحداث في وضع التصحيح مع إعادة التحميل التلقائي
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        # هذا هو الوضع الرئيسي فقط
        if os.environ.get('FLASK_ENV') != 'development':
            try:
                register_events()
            except Exception as e:
                logger.warning(f"⚠️ خطأ في التسجيل التلقائي: {e}")
        else:
            logger.info("ℹ️ أحداث SQLAlchemy مسجلة في وضع التطوير")
    else:
        # الوضع الفرعي لإعادة التحميل - لا نسجل
        pass


# استدعاء التسجيل التلقائي
_auto_register()
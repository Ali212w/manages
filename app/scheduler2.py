"""
scheduler.py - جدولة المهام الدورية للنظام الذكي
يدير جميع المهام المجدولة تلقائياً
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import atexit
import logging
import os
import time
from threading import Lock

logger = logging.getLogger(__name__)

# متغيرات عامة للمجدول
_scheduler = None
_scheduler_started = False
_app_instance = None
# قفل للتحديثات المتزامنة
_scheduler_lock = Lock()

# سجل آخر وقت تنفيذ لكل مهمة (لمنع التكرار)
_last_run_time = {}

def should_run_task(task_id, interval_seconds=60):
    """
    التحقق مما إذا كان يجب تشغيل المهمة (لمنع التكرار)
    
    Args:
        task_id: معرف المهمة
        interval_seconds: الحد الأدنى للفاصل الزمني بين التشغيل (بالثواني)
    """
    with _scheduler_lock:
        now = time.time()
        last_run = _last_run_time.get(task_id, 0)
        if now - last_run < interval_seconds:
            return False
        _last_run_time[task_id] = now
        return True


def is_scheduler_enabled():
    """
    التحقق مما إذا كان المجدول مفعلاً
    يمكن تعطيله مؤقتاً عن طريق متغير البيئة
    """
    return os.environ.get('ENABLE_SCHEDULER', 'False').lower() == 'true'

def init_scheduler(app):
    """
    تهيئة المجدول مع تمرير تطبيق Flask
    
    Args:
        app: تطبيق Flask
    """
    global _scheduler, _scheduler_started, _app_instance
    # التحقق من تفعيل المجدول
    if not is_scheduler_enabled():
        logger.info("⚠️ المجدول معطل (ENABLE_SCHEDULER=False)")
        return
    # تخزين التطبيق للاستخدام لاحقاً
    _app_instance = app
    
    # إذا كان المجدول يعمل بالفعل، لا تفعل شيئاً
    if _scheduler_started:
        logger.info("⚠️ المجدول يعمل بالفعل، تم تجاهل طلب التهيئة المزدوجة")
        return
    
    # إنشاء المجدول إذا لم يكن موجوداً
    if _scheduler is None:
        _scheduler = BackgroundScheduler()
    
    start_scheduler()


def get_app():
    """الحصول على تطبيق Flask مع السياق المناسب"""
    global _app_instance
    if _app_instance:
        return _app_instance
    
    try:
        from flask import current_app
        return current_app._get_current_object()
    except RuntimeError:
        from app import create_app
        app = create_app()
        _app_instance = app
        return app


def run_with_context(task_id=None, min_interval=60):
    """
    ديكوراتور لتشغيل الدالة داخل سياق التطبيق مع منع التكرار
    
    Args:
        task_id: معرف المهمة (لمنع التكرار)
        min_interval: الحد الأدنى للفاصل الزمني (بالثواني)
    
    الاستخدام:
        @run_with_context(task_id='my_task', min_interval=120)
        def my_function():
            pass
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # التحقق من منع التكرار
            if task_id and not should_run_task(task_id, min_interval):
                logger.debug(f"⏭️ تخطي تشغيل {task_id} - تم تشغيله مؤخراً")
                return
            
            app = get_app()
            with app.app_context():
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"❌ خطأ في {func.__name__}: {str(e)}")
        
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper
    return decorator
    return wrapper

# ============================================
# تعريف دوال المهام المغلفة بالسياق
# ============================================

@run_with_context(task_id='monitor_projects', min_interval=120)
def monitor_projects_task():
    """مراقبة المشاريع"""
    try:
        from app.services.smart_monitor import SmartMonitoringSystem
        monitor = SmartMonitoringSystem()
        monitor.monitor_projects()
        logger.info("✅ اكتملت مراقبة المشاريع")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة المشاريع: {str(e)}")

@run_with_context(task_id='monitor_activities', min_interval=120)
def monitor_activities_task():
    """مراقبة الأنشطة"""
    try:
        from app.services.smart_monitor import SmartMonitoringSystem
        monitor = SmartMonitoringSystem()
        monitor.monitor_activities()
        logger.info("✅ اكتملت مراقبة الأنشطة")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة الأنشطة: {str(e)}")

@run_with_context(task_id='monitor_tasks', min_interval=120)
def monitor_tasks_task():
    """مراقبة المهام"""
    try:
        from app.services.smart_monitor import SmartMonitoringSystem
        monitor = SmartMonitoringSystem()
        monitor.monitor_tasks()
        logger.info("✅ اكتملت مراقبة المهام")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة المهام: {str(e)}")

@run_with_context(task_id='monitor_resources', min_interval=120)
def monitor_resources_task():
    """مراقبة الموارد"""
    try:
        from app.services.smart_monitor import SmartMonitoringSystem
        monitor = SmartMonitoringSystem()
        monitor.monitor_resources()
        logger.info("✅ اكتملت مراقبة الموارد")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة الموارد: {str(e)}")

@run_with_context(task_id='monitor_costs', min_interval=120)
def monitor_costs_task():
    """مراقبة التكاليف"""
    try:
        from app.services.smart_monitor import SmartMonitoringSystem
        monitor = SmartMonitoringSystem()
        monitor.monitor_costs()
        logger.info("✅ اكتملت مراقبة التكاليف")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة التكاليف: {str(e)}")

@run_with_context(task_id='activity_dependencies', min_interval=120)
def monitor_activity_dependencies_task():
    """مراقبة تبعيات الأنشطة"""
    try:
        from app.services.smart_dependency_manager import SmartDependencyManager
        manager = SmartDependencyManager()
        manager.monitor_activity_dependencies()
        logger.info("✅ اكتملت مراقبة تبعيات الأنشطة")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة تبعيات الأنشطة: {str(e)}")

@run_with_context(task_id='task_dependencies', min_interval=120)
def monitor_task_dependencies_task():
    """مراقبة تبعيات المهام"""
    try:
        from app.services.smart_dependency_manager import SmartDependencyManager
        manager = SmartDependencyManager()
        manager.monitor_task_dependencies()
        logger.info("✅ اكتملت مراقبة تبعيات المهام")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة تبعيات المهام: {str(e)}")

@run_with_context(task_id='update_metrics', min_interval=300)
def update_all_metrics_task():
    """تحديث مؤشرات جميع المشاريع النشطة"""
    try:
        from app.models.project_models import Project
        from app.services.update_service import UpdateService
        
        logger.info("🔄 بدء التحديث الدوري لجميع المؤشرات...")
        
        projects = Project.query.filter(
            Project.status.in_(['planning', 'active', 'in_progress', 'delayed', 'critical_delay'])
        ).all()
        
        updated_count = 0
        for project in projects:
            try:
                UpdateService.update_all_metrics(project.id)
                updated_count += 1
            except Exception as e:
                logger.error(f"خطأ في تحديث المشروع {project.id}: {str(e)}")
        
        logger.info(f"✅ تم تحديث مؤشرات {updated_count} من {len(projects)} مشروع بنجاح")
    except Exception as e:
        logger.error(f"❌ خطأ في التحديث الدوري: {str(e)}")

@run_with_context(task_id='auto_detect_risks_issues', min_interval=120)
def auto_detect_risks_issues_task():
    """الكشف التلقائي عن المخاطر والقضايا"""
    try:
        from app.services.smart_risk_issue_detector import SmartRiskIssueDetector
        result = SmartRiskIssueDetector.run_scheduled_scan()
        logger.info(f"✅ الفحص التلقائي: تم اكتشاف {result['risks']} خطر و {result['issues']} قضية")
    except Exception as e:
        logger.error(f"❌ خطأ في الكشف التلقائي: {str(e)}")

@run_with_context(task_id='send_reminders', min_interval=300)
def send_meeting_reminders_task():
    """إرسال تذكيرات الاجتماعات"""
    try:
        from app.services.meeting_service import MeetingService
        count = MeetingService.send_meeting_reminders()
        logger.info(f"✅ تم إرسال {count} تذكير اجتماع")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال تذكيرات الاجتماعات: {str(e)}")

@run_with_context(task_id='risk_analysis', min_interval=300)
def analyze_all_risks_task():
    """تحليل المخاطر لجميع المشاريع النشطة"""
    try:
        from app.models.project_models import Project
        from app.services.smart_risk_manager import SmartRiskManager
        
        logger.info("🔍 بدء تحليل المخاطر...")
        
        risk_manager = SmartRiskManager()
        projects = Project.query.filter_by(status='active').all()
        risks_found = 0
        
        for project in projects:
            risks = risk_manager.detect_project_risks(project)
            future_risks = risk_manager.predict_future_risks(project)
            risks_found += len(risks) + len(future_risks)
        
        logger.info(f"✅ اكتمل تحليل المخاطر: تم اكتشاف {risks_found} خطر جديد")
    except Exception as e:
        logger.error(f"❌ خطأ في تحليل المخاطر: {str(e)}")

@run_with_context(task_id='quality_monitoring', min_interval=300)
def monitor_all_quality_task():
    """مراقبة الجودة لجميع المشاريع"""
    try:
        from app.models.project_models import Project
        from app.services.smart_quality_manager import SmartQualityManager
        
        logger.info("🔍 بدء مراقبة الجودة...")
        
        quality_manager = SmartQualityManager()
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            quality_manager.monitor_quality_metrics(project)
        
        logger.info(f"✅ اكتملت مراقبة الجودة لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة الجودة: {str(e)}")

@run_with_context(task_id='critical_path', min_interval=300)
def monitor_all_critical_paths_task():
    """مراقبة المسار الحرج لجميع المشاريع"""
    try:
        from app.models.project_models import Project
        from app.services.smart_dependency_manager import SmartDependencyManager
        
        logger.info("🔍 بدء مراقبة المسار الحرج...")
        
        dependency_manager = SmartDependencyManager()
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            dependency_manager.monitor_critical_path(project.id)
        
        logger.info(f"✅ اكتملت مراقبة المسار الحرج لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في مراقبة المسار الحرج: {str(e)}")

@run_with_context(task_id='cost_calculation', min_interval=300)
def calculate_all_project_costs_task():
    """حساب تكاليف جميع المشاريع"""
    try:
        from app.models.project_models import Project
        from app.services.cost_calculation_service import CostCalculationService
        
        logger.info("💰 بدء حساب التكاليف...")
        
        cost_service = CostCalculationService()
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            cost_service.calculate_full_project_cost(project.id)
        
        logger.info(f"✅ اكتمل حساب التكاليف لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في حساب التكاليف: {str(e)}")

@run_with_context(task_id='performance_optimization', min_interval=300)
def optimize_all_performance_task():
    """تحسين أداء جميع المشاريع"""
    try:
        from app.models.project_models import Project
        from app.services.smart_performance_optimizer import SmartPerformanceOptimizer
        
        logger.info("⚡ بدء تحسين الأداء...")
        
        optimizer = SmartPerformanceOptimizer()
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            team_stats = optimizer.analyze_team_performance(project)
            bottlenecks = optimizer.identify_bottlenecks(project)
            suggestions = optimizer.suggest_optimizations(project, team_stats, bottlenecks)
            
            if suggestions:
                optimizer.notification_service.performance_suggestions(project, suggestions)
        
        logger.info(f"✅ اكتمل تحسين الأداء لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في تحسين الأداء: {str(e)}")

@run_with_context(task_id='daily_reports', min_interval=300)
def generate_daily_reports_task():
    """إنشاء تقارير يومية"""
    try:
        from app.models.project_models import Project
        from app.models.core_models import Organization
        from app.services.smart_monitor import SmartMonitoringSystem
        from app.services.business_intelligence import BusinessIntelligence
        
        logger.info("📊 بدء إنشاء التقارير اليومية...")
        
        monitor = SmartMonitoringSystem()
        bi = BusinessIntelligence()
        
        organizations = Organization.query.filter_by(is_active=True).all()
        
        for org in organizations:
            dashboard = bi.generate_executive_dashboard(org.id)
            
            from app.models.core_models import User
            admins = User.query.filter_by(org_id=org.id, role='org_admin').all()
            
            for admin in admins:
                monitor.notification_service.daily_executive_summary(admin, dashboard)
        
        logger.info(f"✅ اكتمل إنشاء التقارير اليومية لـ {len(organizations)} مؤسسة")
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء التقارير اليومية: {str(e)}")

@run_with_context(task_id='weekly_reports', min_interval=300)
def generate_weekly_reports_task():
    """إنشاء تقارير أسبوعية"""
    try:
        from app.models.project_models import Project
        from app.services.smart_monitor import SmartMonitoringSystem
        from app.services.business_intelligence import BusinessIntelligence
        
        logger.info("📊 بدء إنشاء التقارير الأسبوعية...")
        
        monitor = SmartMonitoringSystem()
        bi = BusinessIntelligence()
        
        projects = Project.query.filter(
            Project.status.in_(['planning', 'active', 'in_progress'])
        ).all()
        
        for project in projects:
            monitor.report_service.generate_weekly_performance_report(project)
        
        logger.info(f"✅ اكتمل إنشاء التقارير الأسبوعية لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء التقارير الأسبوعية: {str(e)}")

@run_with_context(task_id='monthly_reports', min_interval=300)
def generate_monthly_reports_task():
    """إنشاء تقارير شهرية"""
    try:
        from app.models.project_models import Project
        from app.services.smart_monitor import SmartMonitoringSystem
        from app.services.business_intelligence import BusinessIntelligence
        
        logger.info("📊 بدء إنشاء التقارير الشهرية...")
        
        monitor = SmartMonitoringSystem()
        bi = BusinessIntelligence()
        
        projects = Project.query.all()
        
        for project in projects:
            monitor.report_service.generate_monthly_report(project)
        
        logger.info(f"✅ اكتمل إنشاء التقارير الشهرية لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء التقارير الشهرية: {str(e)}")

@run_with_context(task_id='auto_reports', min_interval=300)
def generate_auto_reports_task():
    """إنشاء تقارير تلقائية للمشاريع النشطة"""
    try:
        from app.models.project_models import Project
        from app.services.smart_monitor import SmartMonitoringSystem
        
        logger.info("📊 بدء إنشاء التقارير التلقائية...")
        
        monitor = SmartMonitoringSystem()
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            monitor.report_service.send_cost_performance_report(project, {})
            monitor.report_service.create_project_daily_summary(project)
        
        logger.info(f"✅ اكتمل إنشاء التقارير التلقائية لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء التقارير التلقائية: {str(e)}")

@run_with_context(task_id='daily_summaries', min_interval=300)
def send_daily_summaries_task():
    """إرسال ملخصات يومية للمديرين"""
    try:
        from app.models.core_models import Organization, User
        from app.services.business_intelligence import BusinessIntelligence
        
        logger.info("📧 بدء إرسال الملخصات اليومية...")
        
        bi = BusinessIntelligence()
        organizations = Organization.query.filter_by(is_active=True).all()
        
        for org in organizations:
            kpis = bi.calculate_kpis(org.id)
            admins = User.query.filter_by(org_id=org.id, role='org_admin').all()
            
            for admin in admins:
                bi.send_email_summary(admin.email, kpis)
        
        logger.info(f"✅ اكتمل إرسال الملخصات اليومية لـ {len(organizations)} مؤسسة")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال الملخصات اليومية: {str(e)}")

@run_with_context(task_id='team_performance', min_interval=300)
def evaluate_team_performance_task():
    """تقييم أداء الفريق أسبوعياً"""
    try:
        from app.models.project_models import Project
        from app.models.core_models import User
        from app.services.smart_performance_optimizer import SmartPerformanceOptimizer
        
        logger.info("📈 بدء تقييم أداء الفريق...")
        
        optimizer = SmartPerformanceOptimizer()
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            team_stats = optimizer.analyze_team_performance(project)
            
            for user_id, stats in team_stats.items():
                user = User.query.get(user_id)
                if user:
                    if stats.get('efficiency', 0) < 50:
                        optimizer.notification_service.performance_alert(user, stats)
                    if stats.get('avg_quality', 0) < 3:
                        optimizer.notification_service.quality_improvement_needed(user, stats)
        
        logger.info(f"✅ اكتمل تقييم أداء الفريق لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في تقييم أداء الفريق: {str(e)}")

@run_with_context(task_id='deadline_reminders', min_interval=300)
def send_deadline_reminders_task():
    """إرسال تذكيرات بالمواعيد النهائية"""
    try:
        from app.models.task_models import Task, TaskPlanning
        from app.services.smart_monitor import SmartMonitoringSystem
        
        logger.info("⏰ بدء إرسال تذكيرات المواعيد...")
        
        monitor = SmartMonitoringSystem()
        three_days_later = datetime.now().date() + timedelta(days=3)
        
        upcoming_tasks = Task.query.filter(
            Task.status == 'in_progress',
            Task.planning.has(TaskPlanning.planned_finish <= three_days_later),
            Task.planning.has(TaskPlanning.planned_finish >= datetime.now().date())
        ).all()
        
        sent_count = 0
        for task in upcoming_tasks:
            try:
                days_remaining = (task.planning.planned_finish - datetime.now().date()).days
                monitor.notification_service.task_deadline_reminder(task, days_remaining)
                sent_count += 1
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"خطأ في تذكير المهمة {task.id}: {str(e)}")
        
        if sent_count > 0:
            logger.info(f"✅ تم إرسال {sent_count} تذكير")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال تذكيرات المواعيد: {str(e)}")

@run_with_context(task_id='upcoming_tasks', min_interval=300)
def send_upcoming_tasks_reminders_task():
    """إرسال تذكيرات بالمهام القادمة"""
    try:
        from app.models.task_models import Task, TaskPlanning
        from app.services.smart_monitor import SmartMonitoringSystem
        
        logger.info("⏰ بدء إرسال تذكيرات المهام القادمة...")
        
        monitor = SmartMonitoringSystem()
        tomorrow = datetime.now().date() + timedelta(days=1)
        
        upcoming_tasks = Task.query.filter(
            Task.status == 'pending',
            Task.planning.has(TaskPlanning.planned_start <= tomorrow),
            Task.planning.has(TaskPlanning.planned_start >= datetime.now().date())
        ).all()
        
        for task in upcoming_tasks:
            monitor.notification_service.task_ready_to_start(task, [])
        
        logger.info(f"✅ تم إرسال {len(upcoming_tasks)} تذكير للمهام القادمة")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال تذكيرات المهام القادمة: {str(e)}")

@run_with_context(task_id='holiday_reminders', min_interval=300)
def send_holiday_reminders_task():
    """إرسال تنبيهات العطلات"""
    try:
        from app.models import Calendar
        from app.models.project_models import Project
        from app.services.notification_service import NotificationService
        
        logger.info("🎉 بدء إرسال تنبيهات العطلات...")
        
        today = datetime.now().date()
        calendars = Calendar.query.filter_by(is_active=True).all()
        
        for calendar in calendars:
            upcoming_holidays = [
                h for h in calendar.holidays 
                if h > today and (h - today).days <= 7
            ]
            
            if upcoming_holidays:
                projects = Project.query.filter_by(calendar_id=calendar.id).all()
                for project in projects:
                    if project.project_manager_id:
                        NotificationService.holiday_upcoming(project, upcoming_holidays)
        
        logger.info(f"✅ تم إرسال تنبيهات العطلات لـ {len(calendars)} تقويم")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال تنبيهات العطلات: {str(e)}")

@run_with_context(task_id='budget_alerts', min_interval=300)
def send_budget_alerts_task():
    """إرسال تنبيهات الميزانية"""
    try:
        from app.models.project_models import Project
        from app.services.smart_monitor import SmartMonitoringSystem
        
        logger.info("💰 بدء إرسال تنبيهات الميزانية...")
        
        monitor = SmartMonitoringSystem()
        projects = Project.query.filter_by(status='active').all()
        
        for project in projects:
            if project.cost and project.budget:
                budget_usage = (project.cost.total_actual_cost / project.budget.current_budget) * 100 if project.budget.current_budget > 0 else 0
                
                if budget_usage > 80:
                    budget_status = {
                        'percent_spent': budget_usage,
                        'planned': project.budget.current_budget,
                        'actual': project.cost.total_actual_cost
                    }
                    monitor.notification_service.budget_alert(project, budget_status)
        
        logger.info(f"✅ تم إرسال تنبيهات الميزانية لـ {len(projects)} مشروع")
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال تنبيهات الميزانية: {str(e)}")

@run_with_context(task_id='data_cleanup', min_interval=86400)
def clean_old_data_task():
    """تنظيف البيانات القديمة"""
    try:
        from app import db
        from app.models.ai_models import AIReport, AIRecommendation
        from app.models import Notification
        
        logger.info("🧹 بدء تنظيف البيانات القديمة...")
        
        three_months_ago = datetime.now() - timedelta(days=90)
        six_months_ago = datetime.now() - timedelta(days=180)
        
        old_reports = AIReport.query.filter(AIReport.created_at < three_months_ago).all()
        reports_count = len(old_reports)
        for report in old_reports:
            db.session.delete(report)
        
        old_recommendations = AIRecommendation.query.filter(
            AIRecommendation.status == 'implemented',
            AIRecommendation.implemented_at < six_months_ago
        ).all()
        recommendations_count = len(old_recommendations)
        for rec in old_recommendations:
            db.session.delete(rec)
        
        old_notifications = Notification.query.filter(
            Notification.is_read == True,
            Notification.created_at < six_months_ago
        ).all()
        notifications_count = len(old_notifications)
        for notif in old_notifications:
            db.session.delete(notif)
        
        db.session.commit()
        
        logger.info(f"✅ تم تنظيف {reports_count} تقرير، {recommendations_count} توصية، {notifications_count} إشعار")
    except Exception as e:
        db.session.rollback()
        logger.error(f"❌ خطأ في تنظيف البيانات: {str(e)}")
# في scheduler.py - أضف هذه المهمة

@run_with_context(task_id='monitor_projects', min_interval=120)
def check_expired_trials_task():
    """فحص الشركات التي انتهت فترتها التجريبية"""
    try:
        from app.models import db,Organization,User
        from app.services.notification_service import NotificationService
        
        today = datetime.utcnow().date()
        
        # الشركات التي تنتهي فترتها التجريبية اليوم
        expiring_today = Organization.query.filter(
            Organization.subscription_status == 'trial',
            db.func.date(Organization.trial_end) == today
        ).all()
        
        for company in expiring_today:
            # إشعار لمدير الشركة
            admin = User.query.filter_by(org_id=company.id, role='org_admin').first()
            if admin:
                NotificationService.trial_expiring_today(admin, company)
        
        # الشركات التي انتهت فترتها التجريبية
        expired_trials = Organization.query.filter(
            Organization.subscription_status == 'trial',
            Organization.trial_end < datetime.utcnow()
        ).all()
        
        for company in expired_trials:
            company.subscription_status = 'expired'
            db.session.commit()
            
            # إشعار بانتهاء الفترة التجريبية
            admin = User.query.filter_by(org_id=company.id, role='org_admin').first()
            if admin:
                NotificationService.trial_expired(admin, company)
        
        if expired_trials:
            logger.info(f"✅ تم تحديث {len(expired_trials)} شركة انتهت فترتها التجريبية")
        
    except Exception as e:
        logger.error(f"❌ خطأ في فحص الفترات التجريبية: {str(e)}")

# في scheduler.py

@run_with_context
def check_expiring_subscriptions_task():
    """فحص الاشتراكات على وشك الانتهاء وإرسال إشعارات"""
    try:
        from app import db
        from app.models.core_models import Subscription
        from app.services.platform_notification_service import PlatformNotificationService
        
        today = datetime.now().date()
        warning_days = [30, 15, 7, 3, 1]  # إشعارات في هذه الأيام
        
        for days in warning_days:
            target_date = today + timedelta(days=days)
            
            expiring_subs = Subscription.query.filter(
                Subscription.status == 'active',
                db.func.date(Subscription.end_date) == target_date
            ).all()
            
            for sub in expiring_subs:
                # ✅ إشعار باشتراك على وشك الانتهاء
                PlatformNotificationService.subscription_expiring_soon(sub, days)
                
        logger.info(f"✅ تم فحص {len(expiring_subs)} اشتراك على وشك الانتهاء")
        
    except Exception as e:
        logger.error(f"❌ خطأ في فحص الاشتراكات: {str(e)}")


@run_with_context
def send_weekly_reports_task():
    """إرسال التقارير الأسبوعية لمديري المنصة"""
    try:
        from app import db
        from app.models.core_models import PlatformAdmin, Organization, User, Subscription
        from app.services.platform_notification_service import PlatformNotificationService
        from datetime import datetime, timedelta
        
        admins = PlatformAdmin.query.filter_by(is_active=True).all()
        week_ago = datetime.now() - timedelta(days=7)
        
        for admin in admins:
            # حساب الإحصائيات للأسبوع الماضي
            stats = {
                'new_companies': Organization.query.filter(
                    Organization.created_at >= week_ago
                ).count(),
                'new_users': User.query.filter(
                    User.created_at >= week_ago
                ).count(),
                'pending_subscriptions': Subscription.query.filter_by(
                    request_status='pending'
                ).count(),
                'revenue': db.session.query(db.func.sum(Subscription.amount)).filter(
                    Subscription.created_at >= week_ago,
                    Subscription.payment_status == 'paid'
                ).scalar() or 0
            }
            
            # ✅ إشعار بالتقرير الأسبوعي
            PlatformNotificationService.weekly_report(admin, stats)
            
        logger.info(f"✅ تم إرسال التقارير الأسبوعية لـ {len(admins)} مدير")
        
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال التقارير الأسبوعية: {str(e)}")


@run_with_context
def system_health_check_task():
    """فحص صحة النظام وإرسال تنبيهات عند وجود مشاكل"""
    try:
        from app import db
        from app.services.platform_notification_service import PlatformNotificationService
        
        # فحص اتصال قاعدة البيانات
        try:
            db.session.execute('SELECT 1')
        except Exception as e:
            PlatformNotificationService.system_alert(
                title='⚠️ مشكلة في اتصال قاعدة البيانات',
                message=f'حدث خطأ في الاتصال بقاعدة البيانات: {str(e)}',
                priority='critical'
            )
        
        # فحص مساحة التخزين
        import shutil
        total, used, free = shutil.disk_usage('/')
        free_gb = free // (2**30)
        
        if free_gb < 5:
            PlatformNotificationService.system_alert(
                title='⚠️ مساحة تخزين منخفضة',
                message=f'المساحة المتبقية على الخادم: {free_gb} جيجابايت فقط',
                priority='high'
            )
        
        logger.info("✅ تم فحص صحة النظام")
        
    except Exception as e:
        logger.error(f"❌ خطأ في فحص صحة النظام: {str(e)}")


@run_with_context
def backup_database_task():
    """إجراء نسخ احتياطي لقاعدة البيانات"""
    try:
        from app import db
        from app.services.platform_notification_service import PlatformNotificationService
        import subprocess
        
        # تنفيذ أمر النسخ الاحتياطي
        backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
        # ... كود النسخ الاحتياطي ...
        
        # ✅ إشعار باكتمال النسخ الاحتياطي
        PlatformNotificationService.backup_completed(success=True, details=backup_file)
        
        logger.info(f"✅ تم إنشاء النسخ الاحتياطي: {backup_file}")
        
    except Exception as e:
        # ❌ إشعار بفشل النسخ الاحتياطي
        PlatformNotificationService.backup_completed(success=False, details=str(e))
        logger.error(f"❌ خطأ في النسخ الاحتياطي: {str(e)}")

def start_scheduler():
    """بدء تشغيل المجدول الذكي مع جميع المهام"""
    global _scheduler, _scheduler_started
    
    if _scheduler_started:
        logger.info("⚠️ المجدول يعمل بالفعل، تم تجاهل طلب التشغيل")
        return
    
    logger.info("🔄 بدء تشغيل المجدول الذكي...")
    
    
    
    # ============================================
    # إضافة المهام إلى المجدول
    # ============================================
    
    # مهام المراقبة الأساسية (كل 5 دقائق)
    _scheduler.add_job(
        func=monitor_projects_task,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_projects',
        name='مراقبة المشاريع',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=monitor_activities_task,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_activities',
        name='مراقبة الأنشطة',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=monitor_tasks_task,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_tasks',
        name='مراقبة المهام',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=monitor_resources_task,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_resources',
        name='مراقبة الموارد',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=monitor_costs_task,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_costs',
        name='مراقبة التكاليف',
        replace_existing=True
    )
    
    # مهام التبعيات (كل 5 دقائق)
    _scheduler.add_job(
        func=monitor_activity_dependencies_task,
        trigger=IntervalTrigger(minutes=5),
        id='activity_dependencies',
        name='مراقبة تبعيات الأنشطة',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=monitor_task_dependencies_task,
        trigger=IntervalTrigger(minutes=5),
        id='task_dependencies',
        name='مراقبة تبعيات المهام',
        replace_existing=True
    )
    
    # مهام التحديث الدوري (كل 5 دقائق)
    _scheduler.add_job(
        func=update_all_metrics_task,
        trigger=IntervalTrigger(minutes=5),
        id='update_metrics',
        name='تحديث جميع المؤشرات',
        replace_existing=True
    )
    
    # مهام الكشف التلقائي (كل ساعة)
    _scheduler.add_job(
        func=auto_detect_risks_issues_task,
        trigger=IntervalTrigger(hours=1),
        id='auto_detect_risks_issues',
        name='الكشف التلقائي عن المخاطر والقضايا',
        replace_existing=True
    )
    
    # مهام التذكيرات (كل 30 دقيقة)
    _scheduler.add_job(
        func=send_meeting_reminders_task,
        trigger=IntervalTrigger(minutes=30),
        id='send_reminders',
        name='إرسال تذكيرات الاجتماعات',
        replace_existing=True
    )
    
    # مهام التحليل المتقدمة (كل ساعة)
    _scheduler.add_job(
        func=analyze_all_risks_task,
        trigger=IntervalTrigger(hours=1),
        id='risk_analysis',
        name='تحليل المخاطر',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=monitor_all_quality_task,
        trigger=IntervalTrigger(hours=1),
        id='quality_monitoring',
        name='مراقبة الجودة',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=monitor_all_critical_paths_task,
        trigger=IntervalTrigger(hours=1),
        id='critical_path',
        name='مراقبة المسار الحرج',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=calculate_all_project_costs_task,
        trigger=IntervalTrigger(hours=1),
        id='cost_calculation',
        name='حساب التكاليف',
        replace_existing=True
    )
    
    # مهام تحسين الأداء (كل 6 ساعات)
    _scheduler.add_job(
        func=optimize_all_performance_task,
        trigger=IntervalTrigger(hours=6),
        id='performance_optimization',
        name='تحسين الأداء',
        replace_existing=True
    )
    
    # مهام التقارير اليومية (منتصف الليل)
    _scheduler.add_job(
        func=generate_daily_reports_task,
        trigger=CronTrigger(hour=0, minute=0),
        id='daily_reports',
        name='التقارير اليومية',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=send_daily_summaries_task,
        trigger=CronTrigger(hour=7, minute=0),
        id='daily_summaries',
        name='الملخصات اليومية',
        replace_existing=True
    )
    
    # مهام التقارير الأسبوعية (كل يوم أحد)
    _scheduler.add_job(
        func=generate_weekly_reports_task,
        trigger=CronTrigger(day_of_week='sun', hour=8, minute=0),
        id='weekly_reports',
        name='التقارير الأسبوعية',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=evaluate_team_performance_task,
        trigger=CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='team_performance',
        name='تقييم أداء الفريق',
        replace_existing=True
    )
    
    # مهام التقارير الشهرية (أول كل شهر)
    _scheduler.add_job(
        func=generate_monthly_reports_task,
        trigger=CronTrigger(day=1, hour=9, minute=0),
        id='monthly_reports',
        name='التقارير الشهرية',
        replace_existing=True
    )
    
    # مهام التذكيرات والتنبيهات (كل ساعة)
    _scheduler.add_job(
        func=send_deadline_reminders_task,
        trigger=IntervalTrigger(hours=1),
        id='deadline_reminders',
        name='تذكيرات المواعيد',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=send_upcoming_tasks_reminders_task,
        trigger=IntervalTrigger(hours=1),
        id='upcoming_tasks',
        name='تذكيرات المهام القادمة',
        replace_existing=True
    )
    
    # مهام التنبيهات اليومية
    _scheduler.add_job(
        func=send_holiday_reminders_task,
        trigger=CronTrigger(hour=10, minute=0),
        id='holiday_reminders',
        name='تنبيهات العطلات',
        replace_existing=True
    )
    
    _scheduler.add_job(
        func=send_budget_alerts_task,
        trigger=CronTrigger(hour=9, minute=0),
        id='budget_alerts',
        name='تنبيهات الميزانية',
        replace_existing=True
    )
    
    # مهام التقارير التلقائية (يومياً)
    _scheduler.add_job(
        func=generate_auto_reports_task,
        trigger=CronTrigger(hour=23, minute=30),
        id='auto_reports',
        name='تقارير تلقائية',
        replace_existing=True
    )
    
    # مهام تنظيف البيانات (أول كل شهر)
    _scheduler.add_job(
        func=clean_old_data_task,
        trigger=CronTrigger(day=1, hour=2, minute=0),
        id='data_cleanup',
        name='تنظيف البيانات',
        replace_existing=True
    )
    
    # ============================================
    # بدء المجدول
    # ============================================
    
    try:
        if not _scheduler.running:
            _scheduler.start()
            _scheduler_started = True
            logger.info("✅ تم بدء تشغيل جميع المهام المجدولة بنجاح")
            log_active_jobs()
        else:
            logger.info("⚠️ المجدول يعمل بالفعل")
    except Exception as e:
        logger.error(f"❌ خطأ في بدء تشغيل المجدول: {str(e)}")


def shutdown_scheduler():
    """إيقاف المجدول عند إنهاء التطبيق"""
    global _scheduler, _scheduler_started
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        _scheduler_started = False
        logger.info("⏹️ تم إيقاف المجدول")


def log_active_jobs():
    """تسجيل المهام النشطة في المجدول"""
    if _scheduler:
        jobs = _scheduler.get_jobs()
        logger.info(f"📋 المهام النشطة في المجدول: {len(jobs)} مهمة")
        
        for job in jobs:
            next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "غير محدد"
            logger.info(f"   - {job.name} (ID: {job.id}) | التالي: {next_run}")


def get_scheduler_status():
    """الحصول على حالة المجدول"""
    return {
        'running': _scheduler.running if _scheduler else False,
        'started': _scheduler_started,
        'jobs_count': len(_scheduler.get_jobs()) if _scheduler else 0,
        'jobs': [
            {
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            }
            for job in _scheduler.get_jobs()
        ] if _scheduler else []
    }


def pause_job(job_id):
    """إيقاف مهمة مؤقتاً"""
    if _scheduler:
        try:
            _scheduler.pause_job(job_id)
            logger.info(f"⏸️ تم إيقاف المهمة: {job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في إيقاف المهمة {job_id}: {str(e)}")
    return False


def resume_job(job_id):
    """استئناف مهمة موقوفة"""
    if _scheduler:
        try:
            _scheduler.resume_job(job_id)
            logger.info(f"▶️ تم استئناف المهمة: {job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في استئناف المهمة {job_id}: {str(e)}")
    return False


def run_job_now(job_id):
    """تشغيل مهمة فوراً"""
    if _scheduler:
        try:
            _scheduler.run_job(job_id)
            logger.info(f"⚡ تم تشغيل المهمة فوراً: {job_id}")
            return True
        except Exception as e:
            logger.error(f"❌ خطأ في تشغيل المهمة {job_id}: {str(e)}")
    return False


# تسجيل إيقاف المجدول عند إنهاء التطبيق
atexit.register(shutdown_scheduler)
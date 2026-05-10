# app/scheduler.py

"""
جدولة المهام الدورية للنظام الذكي
يدير جميع المهام المجدولة تلقائياً
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
import atexit
import logging

logger = logging.getLogger(__name__)

# إنشاء المجدول
scheduler = BackgroundScheduler()

def get_app():
    """الحصول على تطبيق Flask مع السياق المناسب"""
    try:
        from flask import current_app
        return current_app._get_current_object()
    except RuntimeError:
        # إذا كنا خارج سياق التطبيق، نستخدم التطبيق الرئيسي
        from app import create_app
        app=create_app()
        return app


def run_with_context(func):
    """ديكوراتور لتشغيل الدالة داخل سياق التطبيق"""
    def wrapper(*args, **kwargs):
        app = get_app()
        with app.app_context():
            return func(*args, **kwargs)
    return wrapper


def start_scheduler():
    """بدء تشغيل المجدول الذكي مع جميع المهام"""
    logger.info("🔄 بدء تشغيل المجدول الذكي...")
    
    # استيراد الخدمات المطلوبة
    from app.services.smart_monitor import SmartMonitoringSystem
    from app.services.smart_risk_manager import SmartRiskManager
    from app.services.smart_quality_manager import SmartQualityManager
    from app.services.smart_performance_optimizer import SmartPerformanceOptimizer
    from app.services.business_intelligence import BusinessIntelligence
    from app.services.smart_communicator import SmartCommunicator
    from app.services.smart_dependency_manager import SmartDependencyManager
    from app.services.cost_calculation_service import CostCalculationService
    from app.services.smart_risk_issue_detector import SmartRiskIssueDetector
    from app.services.meeting_service import MeetingService
    
    # إنشاء كائنات الخدمات
    monitor = SmartMonitoringSystem()
    risk_manager = SmartRiskManager()
    quality_manager = SmartQualityManager()
    optimizer = SmartPerformanceOptimizer()
    bi = BusinessIntelligence()
    communicator = SmartCommunicator()
    dependency_manager = SmartDependencyManager()
    cost_service = CostCalculationService()
    
    # ============================================
    # مهام المراقبة الأساسية (كل 5 دقائق) - مع السياق
    # ============================================
    
    @run_with_context
    def monitor_projects_wrapper():
        monitor.monitor_projects()
    
    @run_with_context
    def monitor_activities_wrapper():
        monitor.monitor_activities()
    
    @run_with_context
    def monitor_tasks_wrapper():
        monitor.monitor_tasks()
    
    @run_with_context
    def monitor_resources_wrapper():
        monitor.monitor_resources()
    
    @run_with_context
    def monitor_costs_wrapper():
        monitor.monitor_costs()
    
    scheduler.add_job(
        func=monitor_projects_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_projects',
        name='مراقبة المشاريع',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=monitor_activities_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_activities',
        name='مراقبة الأنشطة',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=monitor_tasks_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_tasks',
        name='مراقبة المهام',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=monitor_resources_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_resources',
        name='مراقبة الموارد',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=monitor_costs_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='monitor_costs',
        name='مراقبة التكاليف',
        replace_existing=True
    )
    # أضف هذه الوظائف
    @run_with_context
    def auto_detect_risks_issues_task():
        """الكشف التلقائي عن المخاطر والقضايا"""
        try:
            result = SmartRiskIssueDetector.run_scheduled_scan()
            logger.info(f"✅ الفحص التلقائي: تم اكتشاف {result['risks']} خطر و {result['issues']} قضية")
        except Exception as e:
            logger.error(f"❌ خطأ في الكشف التلقائي: {str(e)}")


    @run_with_context
    def send_meeting_reminders_task():
        """إرسال تذكيرات الاجتماعات"""
        try:
            count = MeetingService.send_meeting_reminders()
            logger.info(f"✅ تم إرسال {count} تذكير اجتماع")
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال تذكيرات الاجتماعات: {str(e)}")
    # فحص المخاطر والقضايا كل ساعة
    scheduler.add_job(
        func=auto_detect_risks_issues_task,
        trigger=IntervalTrigger(hours=1),
        id='auto_detect_risks_issues',
        name='الكشف التلقائي عن المخاطر والقضايا',
        replace_existing=True
    )

    # إرسال تذكيرات الاجتماعات كل 30 دقيقة
    scheduler.add_job(
        func=send_meeting_reminders_task,
        trigger=IntervalTrigger(minutes=30),
        id='send_meeting_reminders',
        name='إرسال تذكيرات الاجتماعات',
        replace_existing=True
    )
    # ============================================
    # مهام التبعيات (كل 5 دقائق)
    # ============================================
    
    @run_with_context
    def monitor_activity_dependencies_wrapper():
        dependency_manager.monitor_activity_dependencies()
    
    @run_with_context
    def monitor_task_dependencies_wrapper():
        dependency_manager.monitor_task_dependencies()
    
    scheduler.add_job(
        func=monitor_activity_dependencies_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='activity_dependencies',
        name='مراقبة تبعيات الأنشطة',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=monitor_task_dependencies_wrapper,
        trigger=IntervalTrigger(minutes=5),
        id='task_dependencies',
        name='مراقبة تبعيات المهام',
        replace_existing=True
    )
    
    # ============================================
    # مهام التحليل المتقدمة (كل ساعة)
    # ============================================
    @run_with_context
    def analyze_all_risks(risk_manager):
        """تحليل المخاطر لجميع المشاريع النشطة"""
        try:
            from app.models.project_models import Project
            
            logger.info("🔍 بدء تحليل المخاطر...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            risks_found = 0
            
            for project in projects:
                risks = risk_manager.detect_project_risks(project)
                future_risks = risk_manager.predict_future_risks(project)
                risks_found += len(risks) + len(future_risks)
            
            logger.info(f"✅ اكتمل تحليل المخاطر: تم اكتشاف {risks_found} خطر جديد")
            
        except Exception as e:
            logger.error(f"❌ خطأ في تحليل المخاطر: {str(e)}")
    
    scheduler.add_job(
        func=analyze_all_risks,
        args=[risk_manager],
        trigger=IntervalTrigger(hours=1),
        id='risk_analysis',
        name='تحليل المخاطر',
        replace_existing=True
    )

    @run_with_context
    def monitor_all_quality(quality_manager):
        """مراقبة الجودة لجميع المشاريع"""
        try:
            from app.models.project_models import Project
            
            logger.info("🔍 بدء مراقبة الجودة...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            
            for project in projects:
                quality_manager.monitor_quality_metrics(project)
            
            logger.info(f"✅ اكتملت مراقبة الجودة لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في مراقبة الجودة: {str(e)}")

    scheduler.add_job(
        func=monitor_all_quality,
        args=[quality_manager],
        trigger=IntervalTrigger(hours=1),
        id='quality_monitoring',
        name='مراقبة الجودة',
        replace_existing=True
    )

    @run_with_context
    def monitor_all_critical_paths(dependency_manager):
        """مراقبة المسار الحرج لجميع المشاريع النشطة"""
        try:
            from app.models.project_models import Project
            
            logger.info("🔍 بدء مراقبة المسار الحرج...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            
            for project in projects:
                dependency_manager.monitor_critical_path(project.id)
            
            logger.info(f"✅ اكتملت مراقبة المسار الحرج لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في مراقبة المسار الحرج: {str(e)}")

    @run_with_context
    def calculate_all_project_costs(cost_service):
        """حساب تكاليف جميع المشاريع"""
        try:
            from app.models.project_models import Project
            
            logger.info("💰 بدء حساب التكاليف...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            
            for project in projects:
                cost_service.calculate_full_project_cost(project.id)
            
            logger.info(f"✅ اكتمل حساب التكاليف لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في حساب التكاليف: {str(e)}")

    scheduler.add_job(
        func=monitor_all_critical_paths,
        args=[dependency_manager],
        trigger=IntervalTrigger(hours=1),
        id='critical_path',
        name='مراقبة المسار الحرج',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=calculate_all_project_costs,
        args=[cost_service],
        trigger=IntervalTrigger(hours=1),
        id='cost_calculation',
        name='حساب التكاليف',
        replace_existing=True
    )
    
    # ============================================
    # مهام تحسين الأداء (كل 6 ساعات)
    # ============================================
    @run_with_context
    def optimize_all_performance(optimizer):
        """تحسين أداء جميع المشاريع"""
        try:
            from app.models.project_models import Project
            
            logger.info("⚡ بدء تحسين الأداء...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            
            for project in projects:
                team_stats = optimizer.analyze_team_performance(project)
                bottlenecks = optimizer.identify_bottlenecks(project)
                suggestions = optimizer.suggest_optimizations(project, team_stats, bottlenecks)
                
                if suggestions:
                    optimizer.notification_service.performance_suggestions(project, suggestions)
            
            logger.info(f"✅ اكتمل تحسين الأداء لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في تحسين الأداء: {str(e)}")

    scheduler.add_job(
        func=optimize_all_performance,
        args=[optimizer],
        trigger=IntervalTrigger(hours=6),
        id='performance_optimization',
        name='تحسين الأداء',
        replace_existing=True
    )
    
    # ============================================
    # مهام التقارير اليومية (منتصف الليل)
    # ============================================
    @run_with_context
    def generate_daily_reports(monitor, bi):
        """إنشاء تقارير يومية"""
        try:
            from app.models.project_models import Project
            from app.models.core_models import Organization
            
            logger.info("📊 بدء إنشاء التقارير اليومية...")
            
            organizations = Organization.query.filter_by(is_active=True).all()
            
            for org in organizations:
                dashboard = bi.generate_executive_dashboard(org.id)
                
                # إرسال للمديرين
                from app.models.core_models import User
                admins = User.query.filter_by(org_id=org.id, role='org_admin').all()
                
                for admin in admins:
                    monitor.notification_service.daily_executive_summary(admin, dashboard)
            
            logger.info(f"✅ اكتمل إنشاء التقارير اليومية لـ {len(organizations)} مؤسسة")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء التقارير اليومية: {str(e)}")

    @run_with_context
    def generate_weekly_reports(monitor, bi):
        """إنشاء تقارير أسبوعية"""
        try:
            from app.models.project_models import Project
            
            logger.info("📊 بدء إنشاء التقارير الأسبوعية...")
            
            projects = Project.query.filter(
                Project.status.in_(['planning', 'in_progress'])
            ).all()
            
            for project in projects:
                monitor.report_service.generate_weekly_performance_report(project)
            
            logger.info(f"✅ اكتمل إنشاء التقارير الأسبوعية لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء التقارير الأسبوعية: {str(e)}")

    @run_with_context
    def generate_monthly_reports(monitor, bi):
        """إنشاء تقارير شهرية"""
        try:
            from app.models.project_models import Project
            
            logger.info("📊 بدء إنشاء التقارير الشهرية...")
            
            projects = Project.query.all()
            
            for project in projects:
                monitor.report_service.generate_monthly_report(project)
            
            logger.info(f"✅ اكتمل إنشاء التقارير الشهرية لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء التقارير الشهرية: {str(e)}")

    @run_with_context
    def generate_auto_reports(monitor):
        """إنشاء تقارير تلقائية للمشاريع النشطة"""
        try:
            from app.models.project_models import Project
            
            logger.info("📊 بدء إنشاء التقارير التلقائية...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            
            for project in projects:
                # تقرير الأداء
                monitor.report_service.send_cost_performance_report(project, {})
                
                # تقرير التقدم
                monitor.report_service.create_project_daily_summary(project)
            
            logger.info(f"✅ اكتمل إنشاء التقارير التلقائية لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إنشاء التقارير التلقائية: {str(e)}")

    @run_with_context
    def send_daily_summaries(bi):
        """إرسال ملخصات يومية للمديرين"""
        try:
            from app.models.core_models import Organization, User
            
            logger.info("📧 بدء إرسال الملخصات اليومية...")
            
            organizations = Organization.query.filter_by(is_active=True).all()
            
            for org in organizations:
                kpis = bi.calculate_kpis(org.id)
                
                admins = User.query.filter_by(org_id=org.id, role='org_admin').all()
                
                for admin in admins:
                    # إرسال ملخص عبر البريد الإلكتروني
                    bi.send_email_summary(admin.email, kpis)
            
            logger.info(f"✅ اكتمل إرسال الملخصات اليومية لـ {len(organizations)} مؤسسة")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال الملخصات اليومية: {str(e)}")

    scheduler.add_job(
        func=generate_daily_reports,
        args=[monitor, bi],
        trigger=CronTrigger(hour=0, minute=0),
        id='daily_reports',
        name='التقارير اليومية',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=send_daily_summaries,
        args=[bi],
        trigger=CronTrigger(hour=7, minute=0),
        id='daily_summaries',
        name='الملخصات اليومية',
        replace_existing=True
    )
    
    # ============================================
    # مهام التقارير الأسبوعية (كل يوم أحد)
    # ============================================
    
    scheduler.add_job(
        func=generate_weekly_reports,
        args=[monitor, bi],
        trigger=CronTrigger(day_of_week='sun', hour=8, minute=0),
        id='weekly_reports',
        name='التقارير الأسبوعية',
        replace_existing=True
    )

    @run_with_context
    def evaluate_team_performance(optimizer):
        """تقييم أداء الفريق أسبوعياً"""
        try:
            from app.models.project_models import Project
            from app.models.core_models import User
            
            logger.info("📈 بدء تقييم أداء الفريق...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            
            for project in projects:
                team_stats = optimizer.analyze_team_performance(project)
                
                for user_id, stats in team_stats.items():
                    user = User.query.get(user_id)
                    
                    if user:
                        if stats['efficiency'] < 50:
                            # إشعار للمشرف
                            optimizer.notification_service.performance_alert(user, stats)
                        
                        if stats['avg_quality'] < 3:
                            # إشعار لتحسين الجودة
                            optimizer.notification_service.quality_improvement_needed(user, stats)
            
            logger.info(f"✅ اكتمل تقييم أداء الفريق لـ {len(projects)} مشروع")
            
        except Exception as e:
            logger.error(f"❌ خطأ في تقييم أداء الفريق: {str(e)}")

    scheduler.add_job(
        func=evaluate_team_performance,
        args=[optimizer],
        trigger=CronTrigger(day_of_week='mon', hour=9, minute=0),
        id='team_performance',
        name='تقييم أداء الفريق',
        replace_existing=True
    )
    
    # ============================================
    # مهام التقارير الشهرية (أول كل شهر)
    # ============================================
    
    scheduler.add_job(
        func=generate_monthly_reports,
        args=[monitor, bi],
        trigger=CronTrigger(day=1, hour=9, minute=0),
        id='monthly_reports',
        name='التقارير الشهرية',
        replace_existing=True
    )
    
    # ============================================
    # مهام التذكيرات والتنبيهات (كل ساعة)
    # ============================================
    @run_with_context
    def send_deadline_reminders(monitor):
        """إرسال تذكيرات بالمواعيد النهائية"""
        try:
            from app.models.task_models import Task, TaskPlanning
            
            logger.info("⏰ بدء إرسال تذكيرات المواعيد...")
            
            # المهام التي ستنتهي خلال 3 أيام
            three_days_later = datetime.now().date() + timedelta(days=3)
            
            upcoming_tasks = Task.query.filter(
                Task.status == 'in_progress',
                Task.planning.has(TaskPlanning.planned_finish <= three_days_later),
                Task.planning.has(TaskPlanning.planned_finish >= datetime.now().date())
            ).all()
            
            for task in upcoming_tasks:
                days_remaining = (task.planning.planned_finish - datetime.now().date()).days
                monitor.notification_service.task_deadline_reminder(task, days_remaining)
            
            logger.info(f"✅ تم إرسال {len(upcoming_tasks)} تذكير")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال تذكيرات المواعيد: {str(e)}")

    @run_with_context
    def send_upcoming_tasks_reminders(monitor):
        """إرسال تذكيرات بالمهام القادمة"""
        try:
            from app.models.task_models import Task, TaskPlanning
            
            logger.info("⏰ بدء إرسال تذكيرات المهام القادمة...")
            
            # المهام التي ستبدأ خلال 24 ساعة
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

    @run_with_context
    def send_holiday_reminders():
        """إرسال تنبيهات العطلات"""
        try:
            from app.models import Calendar
            from app.models.project_models import Project
            
            logger.info("🎉 بدء إرسال تنبيهات العطلات...")
            
            today = datetime.now().date()
            
            calendars = Calendar.query.filter_by(is_active=True).all()
            
            for calendar in calendars:
                upcoming_holidays = [
                    h for h in calendar.holidays 
                    if h > today and (h - today).days <= 7
                ]
                
                if upcoming_holidays:
                    # إشعار للمشاريع التي تستخدم هذا التقويم
                    projects = Project.query.filter_by(calendar_id=calendar.id).all()
                    for project in projects:
                        # إرسال إشعارات للمشاريع المتأثرة
                        if project.project_manager_id:
                            from app.services.notification_service import NotificationService
                            NotificationService.holiday_upcoming(project, upcoming_holidays)
            
            logger.info(f"✅ تم إرسال تنبيهات العطلات لـ {len(calendars)} تقويم")
            
        except Exception as e:
            logger.error(f"❌ خطأ في إرسال تنبيهات العطلات: {str(e)}")

    @run_with_context
    def send_budget_alerts(monitor):
        """إرسال تنبيهات الميزانية"""
        try:
            from app.models.project_models import Project
            
            logger.info("💰 بدء إرسال تنبيهات الميزانية...")
            
            projects = Project.query.filter_by(status='in_progress').all()
            
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

    scheduler.add_job(
        func=send_deadline_reminders,
        args=[monitor],
        trigger=IntervalTrigger(hours=1),
        id='deadline_reminders',
        name='تذكيرات المواعيد',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=send_upcoming_tasks_reminders,
        args=[monitor],
        trigger=IntervalTrigger(hours=1),
        id='upcoming_tasks',
        name='تذكيرات المهام القادمة',
        replace_existing=True
    )
    
    # ============================================
    # مهام التنبيهات اليومية
    # ============================================
    
    scheduler.add_job(
        func=send_holiday_reminders,
        trigger=CronTrigger(hour=10, minute=0),
        id='holiday_reminders',
        name='تنبيهات العطلات',
        replace_existing=True
    )
    
    scheduler.add_job(
        func=send_budget_alerts,
        args=[monitor],
        trigger=CronTrigger(hour=9, minute=0),
        id='budget_alerts',
        name='تنبيهات الميزانية',
        replace_existing=True
    )
    
    # ============================================
    # مهام تنظيف البيانات (أول كل شهر)
    # ============================================
    @run_with_context
    def clean_old_data():
        """تنظيف البيانات القديمة"""
        try:
            from app.models import db
            from app.models.ai_models import AIReport, AIRecommendation
            from app.models import Notification
            
            logger.info("🧹 بدء تنظيف البيانات القديمة...")
            
            three_months_ago = datetime.now() - timedelta(days=90)
            six_months_ago = datetime.now() - timedelta(days=180)
            
            # حذف التقارير القديمة (أكثر من 3 أشهر)
            old_reports = AIReport.query.filter(AIReport.created_at < three_months_ago).all()
            reports_count = len(old_reports)
            for report in old_reports:
                db.session.delete(report)
            
            # حذف التوصيات المنفذة القديمة (أكثر من 6 أشهر)
            old_recommendations = AIRecommendation.query.filter(
                AIRecommendation.status == 'implemented',
                AIRecommendation.implemented_at < six_months_ago
            ).all()
            recommendations_count = len(old_recommendations)
            for rec in old_recommendations:
                db.session.delete(rec)
            
            # حذف الإشعارات المقروءة القديمة (أكثر من 6 أشهر)
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


    scheduler.add_job(
        func=clean_old_data,
        trigger=CronTrigger(day=1, hour=2, minute=0),
        id='data_cleanup',
        name='تنظيف البيانات',
        replace_existing=True
    )
    
    # ============================================
    # مهام إنشاء التقارير التلقائية (يومياً)
    # ============================================
    
    scheduler.add_job(
        func=generate_auto_reports,
        args=[monitor],
        trigger=CronTrigger(hour=23, minute=30),
        id='auto_reports',
        name='تقارير تلقائية',
        replace_existing=True
    )
    @run_with_context
    def update_all_projects_metrics():
        """تحديث مؤشرات جميع المشاريع النشطة"""
        try:
            from app.models.project_models import Project
            from app.services.update_service import UpdateService
            
            logger.info("🔄 بدء التحديث الدوري لجميع المؤشرات...")
            
            projects = Project.query.filter(
                Project.status.in_(['planning', 'in_progress', 'delayed', 'critical_delay'])
            ).all()
            
            for project in projects:
                UpdateService.update_all_metrics(project.id)
            
            logger.info(f"✅ تم تحديث مؤشرات {len(projects)} مشروع بنجاح")
            
        except Exception as e:
            logger.error(f"❌ خطأ في التحديث الدوري: {str(e)}")
    scheduler.add_job(
    func=update_all_projects_metrics,
    trigger=IntervalTrigger(minutes=5),
    id='update_all_metrics',
    name='تحديث جميع المؤشرات',
    replace_existing=True
)
    
    # بدء المجدول
    scheduler.start()
    logger.info("✅ تم بدء تشغيل جميع المهام المجدولة بنجاح")
    
    # تسجيل المهام النشطة
    log_active_jobs()


def shutdown_scheduler():
    """إيقاف المجدول عند إنهاء التطبيق"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("⏹️ تم إيقاف المجدول")


# ============================================
# دوال المهام المجدولة - المخاطر والجودة
# ============================================
# app/scheduler.py - إضافة المهمة



# إضافة المهمة في start_scheduler()









# ============================================
# دوال المهام المجدولة - تحسين الأداء
# ============================================




# ============================================
# دوال المهام المجدولة - التقارير
# ============================================



# ============================================
# دوال المهام المجدولة - التذكيرات
# ============================================



# ============================================
# دوال المهام المجدولة - تقييم الأداء
# ============================================


# ============================================
# دوال المهام المجدولة - تنظيف البيانات
# ============================================


# ============================================
# دوال مساعدة
# ============================================

def log_active_jobs():
    """تسجيل المهام النشطة في المجدول"""
    jobs = scheduler.get_jobs()
    logger.info(f"📋 المهام النشطة في المجدول: {len(jobs)} مهمة")
    
    for job in jobs:
        next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "غير محدد"
        logger.info(f"   - {job.name} (ID: {job.id}) | التالي: {next_run}")


def get_scheduler_status():
    """الحصول على حالة المجدول"""
    return {
        'running': scheduler.running,
        'jobs_count': len(scheduler.get_jobs()),
        'jobs': [
            {
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            }
            for job in scheduler.get_jobs()
        ]
    }


def pause_job(job_id):
    """إيقاف مهمة مؤقتاً"""
    try:
        scheduler.pause_job(job_id)
        logger.info(f"⏸️ تم إيقاف المهمة: {job_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في إيقاف المهمة {job_id}: {str(e)}")
        return False


def resume_job(job_id):
    """استئناف مهمة موقوفة"""
    try:
        scheduler.resume_job(job_id)
        logger.info(f"▶️ تم استئناف المهمة: {job_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في استئناف المهمة {job_id}: {str(e)}")
        return False


def run_job_now(job_id):
    """تشغيل مهمة فوراً"""
    try:
        scheduler.run_job(job_id)
        logger.info(f"⚡ تم تشغيل المهمة فوراً: {job_id}")
        return True
    except Exception as e:
        logger.error(f"❌ خطأ في تشغيل المهمة {job_id}: {str(e)}")
        return False


# تسجيل إيقاف المجدول عند إنهاء التطبيق
atexit.register(shutdown_scheduler)
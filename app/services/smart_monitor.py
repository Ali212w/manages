# app/services/smart_monitor.py

"""
نظام المراقبة الذكية - يدير جميع جوانب المشروع تلقائياً
"""

from datetime import datetime, date, timedelta
from flask import current_app
from app.models import db
from app.models.project_models import Project,ProjectDates
from app.models.primavera_models import Activity, ActivityStep,ActivityResource
from app.models.task_models import Task,TaskPlanning
from app.services.notification_service import NotificationService
from app.services.recommendation_service import RecommendationService
from app.services.cost_calculation_service import CostCalculationService
from app.services.report_service import ReportService
import logging

logger = logging.getLogger(__name__)


class SmartMonitoringSystem:
    """النظام الذكي لإدارة المشاريع تلقائياً"""
    
    def __init__(self):
        self.notification_service = NotificationService()
        self.recommendation_service = RecommendationService()
        self.cost_service = CostCalculationService()  # إضافة خدمة التكاليف
        self.report_service = ReportService()
    
    # ============================================
    # مراقبة المشاريع
    # ============================================
    
    def monitor_projects(self):
        """مراقبة جميع المشاريع بشكل دوري"""
        try:
            with current_app.app_context():
                # المشاريع في حالة التخطيط
                planning_projects = Project.query.filter_by(status='planning').all()
                for project in planning_projects:
                    self.check_project_ready_to_start(project)
                
                # المشاريع قيد التنفيذ
                active_projects = Project.query.filter_by(status='in_progress').all()
                for project in active_projects:
                    self.monitor_active_project(project)
                
                # المشاريع المتأخرة
                delayed_projects = Project.query.filter(
                    Project.status == 'in_progress',
                    Project.dates.has(ProjectDates.planned_finish < date.today())
                ).all()
                for project in delayed_projects:
                    self.handle_delayed_project(project)
                
        except Exception as e:
            logger.error(f"خطأ في مراقبة المشاريع: {str(e)}")
    
    def check_project_ready_to_start(self, project):
        """التحقق من جاهزية المشروع للبدء"""
        today = date.today()
        planned_start = project.dates.planned_start.date() if project.dates and project.dates.planned_start else None
        
        if planned_start and planned_start <= today:
            # إرسال إشعار لمدير المشروع
            self.notification_service.project_ready_to_start(project)
            
            # إنشاء توصية ذكية
            self.recommendation_service.recommend_project_start(project)
    
    def monitor_active_project(self, project):
        """مراقبة مشروع قيد التنفيذ"""
        try:
            with current_app.app_context():
                # تسجيل التقدم الحالي في السجل التاريخي
                self.record_project_progress(project)  # ✅ تسجيل أولاً
                
                # حساب نسبة الإنجاز
                progress = project.get_progress()
                
                # تحديث بيانات التقدم الحالية
                if project.progress:
                    project.progress.progress_percentage = progress
                    project.progress.physical_progress = progress
                
                # التحقق من التأخير
                if project.is_overdue:
                    self.handle_delayed_project(project)
                
                # مراقبة الميزانية
                budget_status = project.get_budget_status()
                if budget_status.get('percent_spent', 0) > 90:
                    self.notification_service.budget_alert(project, budget_status)
                
                # مراقبة التكاليف
                if project.cost and project.budget:
                    cost_variance = project.cost.total_actual_cost - project.budget.current_budget
                    if cost_variance > project.budget.current_budget * 0.1:
                        self.notification_service.cost_overrun_alert(project, cost_variance)
                
                # إرسال تقرير أداء أسبوعي
                if self.should_send_weekly_report(project):
                    self.report_service.send_weekly_performance_report(project)
                
                # تحديث إحصائيات المشروع
                if project.statistics:
                    project.statistics.update()
                
                db.session.commit()
                
                logger.info(f"تم تحديث بيانات المشروع {project.name}: تقدم {progress:.1f}%")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في مراقبة المشروع النشط {project.id}: {str(e)}")
    
    def handle_project_overdue(self, project):
        """معالجة المشروع المتأخر"""
        delay_days = (date.today() - project.dates.planned_finish.date()).days
        
        # إشعار لمدير المشروع
        self.notification_service.project_overdue(project, delay_days)
        
        # إشعار لإدارة الشركة
        self.notification_service.project_overdue_alert(project, delay_days)
        
        # إنشاء توصيات لتحسين الوضع
        self.recommendation_service.recommend_project_recovery(project)

    def handle_delayed_project(self, project):
        """معالجة المشروع المتأخر"""
        try:
            # حساب أيام التأخير
            if project.dates and project.dates.planned_finish:
                delay_days = (datetime.now().date() - project.dates.planned_finish.date()).days
            else:
                delay_days = 0
            
            # إشعار لمدير المشروع
            self.notification_service.project_overdue(project, delay_days)
            
            # إشعار لإدارة الشركة
            self.notification_service.project_overdue_alert(project, delay_days)
            
            # إنشاء توصيات لتحسين الوضع
            self.recommendation_service.recommend_project_recovery(project)
            
            # تحديث حالة المشروع إذا كان التأخير كبيراً
            if delay_days > 15:
                project.status = 'critical_delay'
                db.session.commit()
                
            # تسجيل التأخير في سجل المشروع
            self.log_project_delay(project, delay_days)
            
            logger.info(f"تم معالجة المشروع المتأخر {project.name} - تأخير {delay_days} يوم")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة المشروع المتأخر {project.id}: {str(e)}")
    
    def log_project_delay(self, project, delay_days):
        """تسجيل تأخير المشروع"""
        # يمكن إضافة جدول لتسجيل التأخيرات
        pass
    # ============================================
    # مراقبة الأنشطة
    # ============================================
    
    def monitor_activities(self):
        """مراقبة جميع الأنشطة"""
        try:
            with current_app.app_context():
                # الأنشطة التي لم تبدأ بعد
                pending_activities = Activity.query.filter_by(status='not_started').all()
                for activity in pending_activities:
                    self.check_activity_ready_to_start(activity)
                
                # الأنشطة قيد التنفيذ
                active_activities = Activity.query.filter_by(status='in_progress').all()
                for activity in active_activities:
                    self.monitor_active_activity(activity)
                
                # الأنشطة المتأخرة
                overdue_activities = Activity.query.filter(
                    Activity.status == 'in_progress',
                    Activity.planned_finish < datetime.now()
                ).all()
                for activity in overdue_activities:
                    self.handle_overdue_activity(activity)
                
        except Exception as e:
            logger.error(f"خطأ في مراقبة الأنشطة: {str(e)}")
    
    def check_activity_ready_to_start(self, activity):
        """التحقق من جاهزية النشاط للبدء"""
        if activity.planned_start and activity.planned_start <= datetime.now():
            # التحقق من توفر الموارد
            resources_available = self.check_activity_resources(activity)
            
            if resources_available:
                self.notification_service.activity_ready_to_start(activity)
                self.recommendation_service.recommend_activity_start(activity)
            else:
                self.check_activity_resources(activity)
    
    def monitor_active_activity(self, activity):
        """مراقبة نشاط قيد التنفيذ"""
        # حساب التقدم
        progress = activity.progress_percentage
        
        # مراقبة الخطوات
        steps = ActivityStep.query.filter_by(activity_id=activity.id).all()
        if steps:
            completed_steps = sum(1 for s in steps if s.is_completed)
            steps_progress = (completed_steps / len(steps)) * 100
            
            # تحديث تقدم النشاط بناءً على الخطوات
            if abs(progress - steps_progress) > 10:
                self.recommendation_service.recommend_update_activity_progress(activity, steps_progress)
    
    def handle_overdue_activity(self, activity):
        """معالجة نشاط متأخر"""
        try:
            # حساب أيام التأخير
            if activity.planned_finish:
                delay_days = (datetime.now() - activity.planned_finish).days
            else:
                delay_days = 0
            
            # إشعار للمشرف والمنفذ
            self.notification_service.activity_overdue(activity, delay_days)
            
            # إنشاء توصيات لمعالجة التأخير
            self.recommendation_service.recommend_activity_recovery(activity)
            
            # تحديث حالة النشاط
            if activity.status != 'completed':
                activity.status = 'delayed'
                db.session.commit()
            
            logger.info(f"تم معالجة النشاط المتأخر {activity.activity_name} - تأخير {delay_days} يوم")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة النشاط المتأخر {activity.id}: {str(e)}")
    
    def check_activity_resources(self, activity):
        """التحقق من توفر موارد النشاط"""
        try:
            required_resources = ActivityResource.query.filter_by(activity_id=activity.id).all()
            missing_resources = []
            
            for req in required_resources:
                resource = req.resource
                if resource and resource.available_quantity < req.planned_quantity:
                    missing_resources.append({
                        'resource_name': resource.name,
                        'required': req.planned_quantity,
                        'available': resource.available_quantity,
                        'shortage': req.planned_quantity - resource.available_quantity
                    })
            
            if missing_resources:
                self.notification_service.activity_missing_resources(activity, missing_resources)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"خطأ في التحقق من موارد النشاط {activity.id}: {str(e)}")
            return False

    
    # ============================================
    # مراقبة المهام
    # ============================================
    
    def monitor_tasks(self):
        """مراقبة جميع المهام"""
        try:
            with current_app.app_context():
                # المهام الجديدة
                new_tasks = Task.query.filter_by(status='pending').all()
                for task in new_tasks:
                    self.check_task_ready_to_start(task)
                
                # المهام قيد التنفيذ
                active_tasks = Task.query.filter_by(status='in_progress').all()
                for task in active_tasks:
                    self.monitor_active_task(task)
                
                # المهام المتأخرة
                overdue_tasks = Task.query.filter(
                    Task.status == 'in_progress',
                    Task.planning.has(TaskPlanning.planned_finish < date.today())
                ).all()
                for task in overdue_tasks:
                    self.handle_overdue_task(task)
                
        except Exception as e:
            logger.error(f"خطأ في مراقبة المهام: {str(e)}")
    
    def check_task_ready_to_start(self, task):
        """التحقق من جاهزية المهمة للبدء"""
        try:
            can_start, reason = task.can_start()
            
            if can_start:
                self.notification_service.task_ready_to_start(task, [])
            else:
                # جلب المتطلبات غير المكتملة
                pending_reqs = task.get_pending_requirements()
                if pending_reqs:
                    self.notification_service.task_missing_requirements(task, pending_reqs)
                    
        except Exception as e:
            logger.error(f"خطأ في التحقق من جاهزية المهمة {task.id}: {str(e)}")
    
    def monitor_active_task(self, task):
        """مراقبة مهمة قيد التنفيذ"""
        try:
            with current_app.app_context():
                # حساب التقدم
                progress = task.progress_percentage
                
                # تذكير قبل الموعد النهائي
                if task.planning and task.planning.planned_finish:
                    days_remaining = (task.planning.planned_finish - datetime.now().date()).days
                    if 0 < days_remaining <= 3 and progress < 80:
                        self.notification_service.task_deadline_reminder(task, days_remaining)
                
                # إشعار بالإنجاز الكامل
                if progress >= 100 and task.status != 'completed':
                    self.notification_service.task_ready_for_review(task)
                
        except Exception as e:
            logger.error(f"خطأ في مراقبة المهمة {task.id}: {str(e)}")
    
    def handle_overdue_task(self, task):
        """معالجة مهمة متأخرة"""
        try:
            delay_days = task.delay_days
            
            # إشعار للمنفذ
            self.notification_service.task_overdue(task, delay_days)
            
            # إشعار للمشرف
            if task.supervisor_id:
                self.notification_service.task_overdue_supervisor(task, delay_days)
            
            # إنشاء توصية لمعالجة التأخير
            self.recommendation_service.recommend_task_recovery(task)
            
            logger.info(f"تم معالجة المهمة المتأخرة {task.task_name} - تأخير {delay_days} يوم")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة المهمة المتأخرة {task.id}: {str(e)}")
    
    # ============================================
    # مراقبة الموارد
    # ============================================
    
    def monitor_resources(self):
        """مراقبة الموارد"""
        try:
            with current_app.app_context():
                from app.models.primavera_models import Resource
                
                # المواد منخفضة المخزون
                low_stock_resources = Resource.query.filter(
                    Resource.resource_type == 'material',
                    Resource.available_quantity <= Resource.minimum_quantity
                ).all()
                for resource in low_stock_resources:
                    self.handle_low_stock(resource)
                
                # المعدات التي تحتاج صيانة
                equipment_needing_maintenance = Resource.query.filter(
                    Resource.resource_type == 'equipment',
                    Resource.next_maintenance <= date.today()
                ).all()
                for equipment in equipment_needing_maintenance:
                    self.handle_maintenance_reminder(equipment)
                
        except Exception as e:
            logger.error(f"خطأ في مراقبة الموارد: {str(e)}")
    
    def handle_low_stock(self, resource):
        """معالجة المواد منخفضة المخزون"""
        self.notification_service.resource_low_stock(resource)
        self.recommendation_service.recommend_reorder_resource(resource)
    
    def handle_maintenance_reminder(self, equipment):
        """تذكير بصيانة المعدات"""
        try:
            self.notification_service.equipment_maintenance_reminder(equipment)
            
            # إنشاء توصية للصيانة
            self.recommendation_service.recommend_equipment_maintenance(equipment)
            
            logger.info(f"تم إرسال تذكير صيانة للمعدة {equipment.name}")
            
        except Exception as e:
            logger.error(f"خطأ في تذكير الصيانة للمعدة {equipment.id}: {str(e)}")
    
    # ============================================
    # مراقبة التكاليف
    # ============================================
    
    def monitor_costs(self):
        """مراقبة التكاليف بشكل دوري"""
        try:
            with current_app.app_context():
                # المشاريع النشطة
                projects = Project.query.filter(
                    Project.status.in_(['planning', 'in_progress'])
                ).all()
                
                for project in projects:
                    # حساب تكاليف المشروع
                    cost_data = self.cost_service.calculate_project_cost(project.id)
                    
                    if cost_data:
                        # التحقق من تجاوز الميزانية
                        if cost_data['variance'] > 0:
                            self.handle_cost_overrun(project, cost_data)
                        
                        # تحديث أداء المشروع
                        if project.performance:
                            self.check_performance_metrics(project, cost_data)
                        
                        # إرسال تقرير التكاليف الأسبوعي
                        if self.should_send_cost_report(project):
                            self.report_service.send_cost_performance_report(project, cost_data)
                
                # مراقبة الأنشطة ذات التكاليف العالية
                self.monitor_high_cost_activities()
            
        except Exception as e:
            logger.error(f"خطأ في مراقبة التكاليف: {str(e)}")
    
    def handle_cost_overrun(self, project, cost_data):
        """معالجة تجاوز الميزانية"""
        try:
            overrun_amount = cost_data['variance']
            overrun_percentage = cost_data['variance_percentage']
            
            # إشعارات حسب درجة التجاوز
            if overrun_percentage >= 20:
                self.notification_service.cost_critical_overrun(project, overrun_percentage, overrun_amount)
                self.recommendation_service.recommend_urgent_cost_reduction(project)
            elif overrun_percentage >= 10:
                self.notification_service.cost_significant_overrun(project, overrun_percentage, overrun_amount)
                self.recommendation_service.recommend_cost_reduction(project)
            elif overrun_percentage >= 5:
                self.notification_service.cost_minor_overrun(project, overrun_percentage, overrun_amount)
            
            # إرسال تقرير الأداء
            self.report_service.send_cost_performance_report(project, cost_data)
            
            logger.info(f"تم معالجة تجاوز الميزانية للمشروع {project.name} - {overrun_percentage:.1f}%")
            
        except Exception as e:
            logger.error(f"خطأ في معالجة تجاوز الميزانية للمشروع {project.id}: {str(e)}")
    
    def monitor_high_cost_activities(self):
        """مراقبة الأنشطة ذات التكاليف العالية"""
        activities = Activity.query.filter(
            Activity.status == 'in_progress',
            Activity.planned_cost > 10000  # حد التكلفة العالية
        ).all()
        
        for activity in activities:
            cost_data = self.cost_service.calculate_activity_cost(activity.id)
            
            if cost_data and cost_data['variance'] > 0:
                if cost_data['variance_percentage'] > 15:
                    self.notification_service.activity_cost_overrun(
                        activity, 
                        cost_data['variance'], 
                        cost_data['variance_percentage']
                    )
    
    def check_performance_metrics(self, project, cost_data):
        """التحقق من مؤشرات الأداء"""
        try:
            if project.performance:
                # التحقق من أداء التكلفة
                if project.performance.cpi < 0.8:
                    self.notification_service.cost_performance_alert(project, project.performance.cpi)
                
                # التحقق من أداء الجدول
                if project.performance.spi < 0.8:
                    self.notification_service.schedule_performance_alert(project, project.performance.spi)
                    
        except Exception as e:
            logger.error(f"خطأ في التحقق من مؤشرات الأداء للمشروع {project.id}: {str(e)}")
    
    def should_send_cost_report(self, project):
        """التحقق من الحاجة لإرسال تقرير التكاليف"""
        today = datetime.now()
        # إرسال كل يوم اثنين
        return today.weekday() == 0
    
    # ============================================
    # دوال مساعدة
    # ============================================
    
    def check_activity_resources(self, activity):
        """التحقق من توفر موارد النشاط"""
        from app.models.primavera_models import ActivityResource, Resource
        
        required_resources = ActivityResource.query.filter_by(activity_id=activity.id).all()
        
        for req in required_resources:
            resource = Resource.query.get(req.resource_id)
            if resource and resource.available_quantity < req.planned_quantity:
                return False
        return True
    
    def should_send_weekly_report(self, project):
        """التحقق من الحاجة لإرسال تقرير أسبوعي"""
        today = datetime.now()
        # إرسال كل يوم اثنين
        return today.weekday() == 0 and not hasattr(project, 'last_weekly_report_sent')
    
    # ============================================
    # التشغيل الدوري
    # ============================================
    
    def run_scheduled_tasks(self):
        """تشغيل المهام المجدولة"""
        logger.info("بدء تشغيل المراقبة الذكية...")
        
        self.monitor_projects()
        self.monitor_activities()
        self.monitor_tasks()
        self.monitor_resources()
        self.monitor_costs()
        
        # إنشاء تقارير تلقائية
        self.report_service.generate_daily_summary()
        
        logger.info("انتهاء المراقبة الذكية")

    def record_project_progress(self, project):
        """تسجيل تقدم المشروع في السجل التاريخي"""
        try:
            with current_app.app_context():
                from app.models.project_models import ProjectProgress, ProjectProgressLog
                from datetime import date
                
                today = date.today()
                
                # تحديث البيانات الحالية (ProjectProgress)
                current_progress = project.get_progress()
                progress_record = ProjectProgress.query.filter_by(project_id=project.id).first()
                
                if not progress_record:
                    progress_record = ProjectProgress(project_id=project.id)
                    db.session.add(progress_record)
                
                progress_record.progress_percentage = current_progress
                progress_record.physical_progress = current_progress
                progress_record.performance_index = project.performance.spi if project.performance else 1.0
                progress_record.total_float = project.progress.total_float if project.progress else 0
                progress_record.updated_at = datetime.utcnow()
                progress_record.updated_by = project.project_manager_id
                
                # تسجيل في السجل التاريخي (ProjectProgressLog)
                existing_log = ProjectProgressLog.query.filter_by(
                    project_id=project.id,
                    record_date=today
                ).first()
                
                if not existing_log:
                    progress_log = ProjectProgressLog(
                        project_id=project.id,
                        record_date=today,
                        progress_percentage=current_progress,
                        physical_progress=current_progress,
                        performance_progress=current_progress,
                        performance_index=project.performance.spi if project.performance else 1.0,
                        completed_activities=sum(1 for a in project.activities if a.status == 'completed'),
                        total_activities=len(project.activities.all()),
                        actual_cost=project.cost.total_actual_cost if project.cost else 0,
                        planned_cost=project.budget.current_budget if project.budget else 0,
                        completed_tasks=sum(1 for t in project.tasks if t.status == 'completed'),
                        total_tasks=len(project.tasks.all()),
                        created_by=project.project_manager_id
                    )
                    db.session.add(progress_log)
                
                db.session.commit()
                logger.info(f"تم تسجيل تقدم المشروع {project.name}: {current_progress:.1f}%")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تسجيل تقدم المشروع {project.id}: {str(e)}")
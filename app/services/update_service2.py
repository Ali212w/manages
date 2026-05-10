"""
update_service.py - خدمة التحديث المتكاملة للمشاريع والأنشطة والمهام (نسخة مطورة)
"""

from datetime import datetime, timedelta, date
from flask import current_app, url_for
from app.models import db
from app.models import (
    Project, ProjectProgress, ProjectPerformance, ProjectCost, ProjectDates, EPS,
    Organization, Notification
)
from app.models.primavera_models import (
    Activity, ActivityStep, ActivityResource, ActivityExpense, 
    WBS, ActivityRelationship, Resource, ActivityCompletion
)
from app.models.task_models import (
    Task, TaskPlanning, TaskExecution, TaskProgress, TaskResource,
    TaskRequirement, TaskRequirementVerification, TaskAssignment
)
from app.models.ai_models import AICommand, AISuggestion
from app.services.notification_service import NotificationService
import logging
import json

logger = logging.getLogger(__name__)


class UpdateService:
    """خدمة التحديث المتكاملة - تحديث جميع المؤشرات"""

    # ============================================
    # التحديث الرئيسي
    # ============================================

    @staticmethod
    def update_all_metrics(project_id, update_type='full', trigger_ai=True):
        """
        تحديث جميع مؤشرات المشروع

        Args:
            project_id: معرف المشروع
            update_type: نوع التحديث ('full', 'progress', 'cost', 'schedule')
            trigger_ai: تفعيل الذكاء الاصطناعي لتوليد التوصيات
        """
        try:
            project = Project.query.get(project_id)
            if not project:
                logger.error(f"المشروع {project_id} غير موجود")
                return False

            logger.info(f"بدء تحديث مؤشرات المشروع {project.name} - النوع: {update_type}")

            # 1. تحديث الأنشطة
            activities = Activity.query.filter_by(project_id=project_id).all()
            for activity in activities:
                UpdateService.update_activity_metrics(activity, update_type)

            # 2. تحديث WBS
            wbs_nodes = WBS.query.filter_by(project_id=project_id).all()
            for wbs in wbs_nodes:
                UpdateService.update_wbs_metrics(wbs)

            # 3. تحديث المشروع
            UpdateService.update_project_metrics(project)

            # 4. تحديث المسار الحرج
            UpdateService.update_critical_path(project_id)

            # 5. تحديث المؤشرات المتقدمة
            UpdateService.update_advanced_project_metrics(project)

            # 6. تحديث التقارير التلقائية
            if update_type in ['full', 'progress']:
                UpdateService.check_and_generate_reports(project)

            # 7. تفعيل الذكاء الاصطناعي للتوصيات
            if trigger_ai:
                UpdateService.generate_ai_recommendations(project)

            # 8. تحديث الإحصائيات للتخزين المؤقت
            UpdateService.update_project_statistics(project_id)

            db.session.commit()
            logger.info(f"✅ تم تحديث مؤشرات المشروع {project.name} بنجاح")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تحديث مؤشرات المشروع {project_id}: {str(e)}")
            return False

    # ============================================
    # تحديث الأنشطة (محسن)
    # ============================================

    @staticmethod
    def update_activity_metrics(activity, update_type='full'):
        """تحديث مؤشرات النشاط (محسن)"""
        try:
            # تحديث التقدم
            if update_type in ['full', 'progress']:
                UpdateService._update_activity_progress(activity)

            # تحديث التكاليف
            if update_type in ['full', 'cost']:
                UpdateService._update_activity_cost(activity)

            # تحديث التواريخ
            if update_type in ['full', 'schedule']:
                UpdateService._update_activity_dates(activity)

            # تحديث المدة
            UpdateService._update_activity_duration(activity)

            # تحديث حالة النشاط
            UpdateService._update_activity_status(activity)

            # تحديث الفارق الزمني
            UpdateService._update_activity_float(activity)

            # ✅ إضافة: تحديث الوحدات (ولاعات العمل)
            UpdateService._update_activity_units(activity)

            # ✅ إضافة: تحديث القيمة المكتسبة للنشاط
            UpdateService._update_activity_earned_value(activity)

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات النشاط {activity.id}: {str(e)}")

    @staticmethod
    def _update_activity_progress(activity):
        """تحديث نسبة إنجاز النشاط (محسن)"""
        # 1. من الخطوات
        steps = ActivityStep.query.filter_by(activity_id=activity.id).all()
        if steps:
            completed_steps = sum(1 for s in steps if s.is_completed)
            progress = (completed_steps / len(steps)) * 100
            activity.progress_percentage = min(progress, 100)
            return

        # 2. من المهام
        tasks = Task.query.filter_by(activity_id=activity.id).all()
        if tasks:
            total_weight = 0
            weighted_progress = 0
            for task in tasks:
                # استخدام TaskPlanning للمدة
                if task.planning and task.planning.planned_duration:
                    weight = task.planning.planned_duration
                else:
                    weight = 1
                total_weight += weight
                # استخدام TaskProgress لنسبة التقدم
                if task.progress:
                    weighted_progress += (task.progress.progress_percentage or 0) * weight
                else:
                    weighted_progress += 0

            # ✅ إضافة وزن تعيينات المستخدمين
            task_assignments = TaskAssignment.query.join(Task).filter(
                Task.activity_id == activity.id
            ).all()
            for assignment in task_assignments:
                if assignment.status == 'completed':
                    weighted_progress += 5  # زيادة بسيطة للإنجاز

            activity.progress_percentage = (weighted_progress / total_weight) if total_weight > 0 else 0
            return

        # 3. من المدة
        if activity.original_duration and activity.original_duration > 0:
            activity.progress_percentage = min((activity.actual_duration or 0) / activity.original_duration * 100, 100)

        # ✅ إضافة: تحديث percentage complete بناءً على القيمة المكتسبة
        if activity.planned_cost and activity.planned_cost > 0:
            ev_percentage = (activity.earned_value or 0) / activity.planned_cost * 100
            if ev_percentage > activity.progress_percentage:
                activity.progress_percentage = min(ev_percentage, 100)

    @staticmethod
    def _update_activity_cost(activity):
        """تحديث تكلفة النشاط (محسن)"""
        total_planned = 0
        total_actual = 0

        # 1. تكاليف الموارد المباشرة
        for resource_assign in activity.resources:
            resource = resource_assign.resource
            if resource:
                unit_price = resource.cost_per_unit or 0
                planned = (resource_assign.planned_quantity or 0) * unit_price
                actual = (resource_assign.actual_quantity or 0) * unit_price
                total_planned += planned
                total_actual += actual
                resource_assign.planned_cost = planned
                resource_assign.actual_cost = actual
            else:
                total_planned += resource_assign.planned_cost or 0
                total_actual += resource_assign.actual_cost or 0

        # 2. تكاليف المهام المرتبطة
        for task in activity.tasks:
            if task.execution:
                total_planned += task.execution.planned_cost or 0
                total_actual += task.execution.actual_cost or 0

            # ✅ إضافة تكاليف موارد المهام
            for task_resource in task.resources:
                total_planned += task_resource.planned_cost or 0
                total_actual += task_resource.actual_cost or 0

        # 3. مصروفات النشاط (المعتمدة فقط)
        for expense in activity.expenses:
            if expense.is_approved:
                total_actual += expense.amount or 0
            else:
                total_planned += expense.amount or 0

        # تحديث حقول النشاط
        activity.planned_cost = total_planned
        activity.actual_cost = total_actual
        activity.remaining_cost = max(0, total_planned - total_actual)
        activity.cost_variance = total_actual - total_planned

        # ✅ إضافة تباين التكلفة بالنسبة المئوية
        if total_planned > 0:
            activity.cost_variance_percentage = (activity.cost_variance / total_planned) * 100
        else:
            activity.cost_variance_percentage = 0

    @staticmethod
    def _update_activity_units(activity):
        """✅ تحديث وحدات العمل للنشاط"""
        total_budgeted_units = 0
        total_actual_units = 0

        for resource_assign in activity.resources:
            total_budgeted_units += resource_assign.planned_quantity or 0
            total_actual_units += resource_assign.actual_quantity or 0

        for task in activity.tasks:
            if task.execution:
                total_budgeted_units += task.execution.planned_units or 0
                total_actual_units += task.execution.actual_units or 0

        activity.budgeted_units = total_budgeted_units
        activity.actual_units = total_actual_units
        activity.remaining_units = max(0, total_budgeted_units - total_actual_units)
        activity.at_complete_units = total_budgeted_units

    @staticmethod
    def _update_activity_earned_value(activity):
        """✅ تحديث القيمة المكتسبة للنشاط"""
        # EV = Budget * % Complete
        if activity.planned_cost and activity.planned_cost > 0:
            activity.earned_value = activity.planned_cost * (activity.progress_percentage / 100)
        else:
            activity.earned_value = 0

        # Planned Value (المخطط)
        activity.planned_value = activity.planned_cost or 0

        # CPI (Cost Performance Index)
        if activity.actual_cost and activity.actual_cost > 0:
            activity.cpi = activity.earned_value / activity.actual_cost
        else:
            activity.cpi = 1.0

        # SPI (Schedule Performance Index)
        if activity.planned_value and activity.planned_value > 0:
            activity.spi = activity.earned_value / activity.planned_value
        else:
            activity.spi = 1.0

    @staticmethod
    def _update_activity_dates(activity):
        """تحديث تواريخ النشاط (محسن)"""
        tasks = Task.query.filter_by(activity_id=activity.id).all()

        if tasks:
            # التواريخ المخططة من TaskPlanning
            planned_starts = []
            planned_finishes = []
            for t in tasks:
                if t.planning:
                    if t.planning.planned_start:
                        planned_starts.append(t.planning.planned_start)
                    if t.planning.planned_finish:
                        planned_finishes.append(t.planning.planned_finish)

            if planned_starts:
                activity.planned_start = min(planned_starts)
            if planned_finishes:
                activity.planned_finish = max(planned_finishes)

            # التواريخ الفعلية من TaskExecution
            actual_starts = []
            actual_finishes = []
            for t in tasks:
                if t.execution:
                    if t.execution.actual_start:
                        actual_starts.append(t.execution.actual_start)
                    if t.execution.actual_finish:
                        actual_finishes.append(t.execution.actual_finish)

            if actual_starts:
                activity.actual_start = min(actual_starts)
            if actual_finishes:
                activity.actual_finish = max(actual_finishes)

    @staticmethod
    def _update_activity_duration(activity):
        """تحديث مدة النشاط (محسن)"""
        # المدة المخططة
        if activity.planned_start and activity.planned_finish:
            start = activity.planned_start
            finish = activity.planned_finish
            if hasattr(start, 'date'):
                start = start.date()
            if hasattr(finish, 'date'):
                finish = finish.date()
            activity.original_duration = (finish - start).days

        # المدة الفعلية
        if activity.actual_start and activity.actual_finish:
            start = activity.actual_start
            finish = activity.actual_finish
            if hasattr(start, 'date'):
                start = start.date()
            if hasattr(finish, 'date'):
                finish = finish.date()
            activity.actual_duration = (finish - start).days
        else:
            # حساب المدة الفعلية من التقدم
            if activity.original_duration and activity.original_duration > 0:
                activity.actual_duration = (activity.progress_percentage / 100) * activity.original_duration

        activity.remaining_duration = max(0, (activity.original_duration or 0) - (activity.actual_duration or 0))
        activity.at_complete_duration = (activity.actual_duration or 0) + (activity.remaining_duration or 0)

        # ✅ إضافة نسبة إنجاز المدة
        if activity.original_duration and activity.original_duration > 0:
            activity.duration_percent_complete = (activity.actual_duration / activity.original_duration) * 100
        else:
            activity.duration_percent_complete = 0

    @staticmethod
    def _update_activity_status(activity):
        """تحديث حالة النشاط (محسن)"""
        if activity.progress_percentage >= 100:
            activity.status = 'completed'
            if not activity.actual_finish:
                activity.actual_finish = datetime.utcnow()
        elif activity.progress_percentage > 0:
            activity.status = 'in_progress'
            if not activity.actual_start:
                activity.actual_start = datetime.utcnow()
        else:
            activity.status = 'not_started'

        # التحقق من التأخير
        if activity.planned_finish and activity.status != 'completed':
            planned_finish = activity.planned_finish
            if hasattr(planned_finish, 'date'):
                planned_finish = planned_finish.date()
            now_date = datetime.now().date()
            
            # تأخير بسيط
            if now_date > planned_finish:
                delay = (now_date - planned_finish).days
                if delay <= 7:
                    activity.status = 'delayed'
                else:
                    activity.status = 'critical_delay'

        # ✅ تحديث إكمال النشاط إذا كان مكتملاً
        if activity.status == 'completed' and not activity.completion:
            completion = ActivityCompletion(
                activity_id=activity.id,
                completion_status='pending'
            )
            db.session.add(completion)

    @staticmethod
    def _update_activity_float(activity):
        """تحديث الفارق الزمني للنشاط"""
        # Total Float = Late Start - Early Start
        if activity.late_start and activity.early_start:
            late_start = activity.late_start
            early_start = activity.early_start
            if hasattr(late_start, 'date'):
                late_start = late_start.date()
            if hasattr(early_start, 'date'):
                early_start = early_start.date()
            activity.total_float = (late_start - early_start).days
        else:
            activity.total_float = 0

        # Free Float = ES(successor) - EF
        successors = ActivityRelationship.query.filter_by(predecessor_id=activity.id).all()
        if successors and activity.early_finish:
            min_es = None
            for s in successors:
                if s.successor and s.successor.early_start:
                    es = s.successor.early_start
                    if hasattr(es, 'date'):
                        es = es.date()
                    if min_es is None or es < min_es:
                        min_es = es
            if min_es:
                ef = activity.early_finish
                if hasattr(ef, 'date'):
                    ef = ef.date()
                activity.free_float = (min_es - ef).days
            else:
                activity.free_float = 0
        else:
            activity.free_float = 0

    # ============================================
    # تحديث المشروع (محسن)
    # ============================================

    @staticmethod
    def update_project_metrics(project):
        """تحديث مؤشرات المشروع (محسن)"""
        try:
            # إنشاء السجلات إذا لم تكن موجودة
            if not project.progress:
                project.progress = ProjectProgress(project_id=project.id)
                db.session.add(project.progress)

            if not project.cost:
                project.cost = ProjectCost(project_id=project.id)
                db.session.add(project.cost)

            if not project.performance:
                project.performance = ProjectPerformance(project_id=project.id)
                db.session.add(project.performance)

            if not project.dates:
                project.dates = ProjectDates(project_id=project.id)
                db.session.add(project.dates)

            # تحديث التقدم
            UpdateService._update_project_progress(project)

            # تحديث التكاليف
            UpdateService._update_project_cost(project)

            # تحديث القيمة المكتسبة
            UpdateService._update_project_earned_value(project)

            # تحديث التواريخ
            UpdateService._update_project_dates(project)

            # تحديث حالة المشروع
            UpdateService._update_project_status(project)

            # ✅ إضافة توقعات المشروع
            UpdateService._update_project_forecast(project)

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات المشروع {project.id}: {str(e)}")

    @staticmethod
    def _update_project_forecast(project):
        """✅ تحديث توقعات المشروع"""
        if project.performance:
            # CPI و SPI للتوقعات
            cpi = project.performance.cpi or 1.0
            spi = project.performance.spi or 1.0

            # توقع تاريخ الانتهاء
            if project.dates and project.dates.planned_finish:
                planned_finish = project.dates.planned_finish
                if hasattr(planned_finish, 'date'):
                    planned_finish = planned_finish.date()
                
                if spi > 0:
                    remaining_days = (planned_finish - datetime.now().date()).days
                    expected_days = remaining_days / spi if remaining_days > 0 else 0
                    project.dates.expected_finish = datetime.now() + timedelta(days=expected_days)

            # توقع التكلفة النهائية (EAC)
            if project.performance.eac and project.budget:
                project.performance.eac = project.budget.current_budget / cpi if cpi > 0 else project.budget.current_budget

    @staticmethod
    def update_advanced_project_metrics(project):
        """✅ تحديث مؤشرات المشروع المتقدمة"""
        activities = Activity.query.filter_by(project_id=project.id).all()

        if not activities:
            return

        # إحصائيات الأنشطة
        project.statistics.total_activities = len(activities)
        project.statistics.completed_activities = len([a for a in activities if a.status == 'completed'])
        project.statistics.in_progress_activities = len([a for a in activities if a.status == 'in_progress'])
        project.statistics.not_started_activities = len([a for a in activities if a.status == 'not_started'])
        project.statistics.critical_activities = len([a for a in activities if a.is_critical])

        # إحصائيات المهام
        total_tasks = 0
        completed_tasks = 0
        for activity in activities:
            activity_tasks = Task.query.filter_by(activity_id=activity.id).all()
            total_tasks += len(activity_tasks)
            completed_tasks += len([t for t in activity_tasks if t.status == 'completed'])

        project.statistics.total_tasks = total_tasks
        project.statistics.completed_tasks = completed_tasks

        # إحصائيات الموارد
        all_resources = set()
        total_manpower = 0
        for activity in activities:
            for resource_assign in activity.resources:
                if resource_assign.resource_id:
                    all_resources.add(resource_assign.resource_id)
                if resource_assign.resource and resource_assign.resource.resource_type == 'labor':
                    total_manpower += resource_assign.planned_quantity or 0

        project.statistics.total_resources = len(all_resources)
        project.statistics.total_manpower = int(total_manpower)
        project.statistics.last_calculated = datetime.utcnow()

        db.session.commit()

    # ============================================
    # توليد توصيات الذكاء الاصطناعي
    # ============================================

    @staticmethod
    def generate_ai_recommendations(project):
        """✅ توليد توصيات ذكية بناءً على أداء المشروع"""
        try:
            recommendations = []

            # 1. توصيات الميزانية
            if project.performance and project.budget:
                cpi = project.performance.cpi or 1.0
                if cpi < 0.8:
                    recommendations.append({
                        'type': 'cost',
                        'title': '⚠️ تجاوز الميزانية',
                        'description': f'نسبة كفاءة التكلفة (CPI = {cpi:.2f}) منخفضة. يوصى بمراجعة المصروفات وتقليل الهدر.',
                        'priority': 'high',
                        'confidence': 0.85
                    })
                elif cpi > 1.2:
                    recommendations.append({
                        'type': 'cost',
                        'title': '✅ أداء مالي ممتاز',
                        'description': f'نسبة كفاءة التكلفة (CPI = {cpi:.2f}) ممتازة. استمر بنفس الكفاءة.',
                        'priority': 'medium',
                        'confidence': 0.9
                    })

            # 2. توصيات الجدول الزمني
            if project.performance:
                spi = project.performance.spi or 1.0
                if spi < 0.8:
                    recommendations.append({
                        'type': 'schedule',
                        'title': '⚠️ تأخر في الجدول الزمني',
                        'description': f'نسبة كفاءة الجدول (SPI = {spi:.2f}) منخفضة. يوصى بتسريع المهام الحرجة.',
                        'priority': 'high',
                        'confidence': 0.85
                    })

            # 3. توصيات الموارد
            activities = Activity.query.filter_by(project_id=project.id).all()
            for activity in activities:
                if activity.status == 'delayed' and activity.total_float < 0:
                    recommendations.append({
                        'type': 'resource',
                        'title': f'🔧 مورد مطلوب: {activity.activity_name}',
                        'description': f'النشاط {activity.activity_name} متأخر ويحتاج إلى موارد إضافية.',
                        'priority': 'high',
                        'confidence': 0.75,
                        'related_activity_id': activity.id
                    })
                    break  # تجنب التكرار

            # 4. توصيات الجودة
            poor_quality_tasks = Task.query.join(TaskProgress).filter(
                Task.project_id == project.id,
                TaskProgress.completion_quality.in_(['fair', 'poor'])
            ).count()

            if poor_quality_tasks > 3:
                recommendations.append({
                    'type': 'quality',
                    'title': '📋 مراجعة الجودة',
                    'description': f'يوجد {poor_quality_tasks} مهمة بجودة منخفضة. يوصى بمراجعة إجراءات ضمان الجودة.',
                    'priority': 'medium',
                    'confidence': 0.8
                })

            # حفظ التوصيات في قاعدة البيانات
            for rec in recommendations:
                suggestion = AISuggestion(
                    org_id=project.org_id,
                    suggestion_type=rec['type'],
                    priority=rec['priority'],
                    title=rec['title'],
                    description=rec['description'],
                    related_project_id=project.id,
                    confidence_score=rec['confidence'] * 100,
                    status='active'
                )
                db.session.add(suggestion)

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في توليد توصيات AI للمشروع {project.id}: {str(e)}")

    # ============================================
    # التقارير التلقائية
    # ============================================

    @staticmethod
    def check_and_generate_reports(project):
        """✅ التحقق من الحاجة لتوليد تقارير تلقائية"""
        from app.models.project_models import ProjectProgressLog

        today = date.today()

        # تسجيل التقدم اليومي
        existing_log = ProjectProgressLog.query.filter_by(
            project_id=project.id,
            record_date=today
        ).first()

        if not existing_log and project.progress:
            progress_log = ProjectProgressLog(
                project_id=project.id,
                record_date=today,
                progress_percentage=project.progress.progress_percentage,
                physical_progress=project.progress.physical_progress,
                performance_progress=project.progress.performance_progress,
                performance_index=project.progress.performance_index,
                actual_cost=project.cost.total_actual_cost if project.cost else 0,
                planned_cost=project.cost.total_planned_cost if project.cost else 0
            )
            db.session.add(progress_log)

            # إذا وصل المشروع إلى 50% أو 75% أو 90%، أضف ملاحظة
            milestones = [50, 75, 90]
            if project.progress.progress_percentage in milestones:
                NotificationService.project_milestone_reached(project, project.progress.progress_percentage)

    @staticmethod
    def update_project_statistics(project_id):
        """✅ تحديث الإحصائيات للتخزين المؤقت"""
        from app.models.project_models import ProjectStatistics

        project = Project.query.get(project_id)
        if not project:
            return

        if not project.statistics:
            project.statistics = ProjectStatistics(project_id=project_id)
            db.session.add(project.statistics)

        activities = Activity.query.filter_by(project_id=project_id).all()

        project.statistics.total_activities = len(activities)
        project.statistics.completed_activities = len([a for a in activities if a.status == 'completed'])
        project.statistics.in_progress_activities = len([a for a in activities if a.status == 'in_progress'])
        project.statistics.not_started_activities = len([a for a in activities if a.status == 'not_started'])
        project.statistics.critical_activities = len([a for a in activities if a.is_critical])

        total_tasks = 0
        completed_tasks = 0
        for activity in activities:
            activity_tasks = Task.query.filter_by(activity_id=activity.id).all()
            total_tasks += len(activity_tasks)
            completed_tasks += len([t for t in activity_tasks if t.status == 'completed'])

        project.statistics.total_tasks = total_tasks
        project.statistics.completed_tasks = completed_tasks

        project.statistics.last_calculated = datetime.utcnow()
        db.session.commit()

    # ============================================
    # تحديث المهام (محسن)
    # ============================================

    @staticmethod
    def update_task_metrics(task_id):
        """تحديث مؤشرات المهمة (محسن)"""
        try:
            task = Task.query.get(task_id)
            if not task:
                return

            # التأكد من وجود TaskProgress
            if not task.progress:
                task.progress = TaskProgress(task_id=task.id)
                db.session.add(task.progress)

            # تحديث التقدم من المتطلبات
            requirements = TaskRequirement.query.filter_by(task_id=task.id, is_active=True).all()
            if requirements:
                verified_count = TaskRequirementVerification.query.filter(
                    TaskRequirementVerification.requirement_id.in_([r.id for r in requirements]),
                    TaskRequirementVerification.status == 'verified'
                ).count()
                task.progress.progress_percentage = (verified_count / len(requirements)) * 100

            # تحديث التقدم من الموارد
            task_resources = TaskResource.query.filter_by(task_id=task.id).all()
            if task_resources and not requirements:
                total_planned = sum(r.planned_quantity or 0 for r in task_resources)
                total_actual = sum(r.actual_quantity or 0 for r in task_resources)
                if total_planned > 0:
                    task.progress.progress_percentage = (total_actual / total_planned) * 100

            # تحديث الحالة
            if task.progress.progress_percentage >= 100:
                task.status = 'completed'
            elif task.progress.progress_percentage > 0:
                task.status = 'in_progress'
            else:
                task.status = 'pending'

            # التأكد من وجود TaskExecution
            if not task.execution:
                task.execution = TaskExecution(task_id=task.id)
                db.session.add(task.execution)

            # تحديث المدة الفعلية
            if task.execution.actual_start:
                if task.execution.actual_finish:
                    duration = task.execution.actual_finish - task.execution.actual_start
                    task.execution.actual_duration = duration.total_seconds() / 3600
                else:
                    duration = datetime.utcnow() - task.execution.actual_start
                    task.execution.actual_duration = duration.total_seconds() / 3600

            db.session.commit()

            # تحديث النشاط المرتبط إذا وجد
            if task.activity_id:
                UpdateService.update_activity_metrics(task.activity)

            # تحديث المشروع
            if task.project_id:
                UpdateService.update_project_metrics(task.project)

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات المهمة {task_id}: {str(e)}")

    # ============================================
    # تحديث طلبات الموارد والمعدات
    # ============================================

    @staticmethod
    def update_resource_request_metrics(resource_request_id):
        """تحديث مؤشرات طلب الموارد"""
        from app.models import ResourceRequest, ResourceRequestItem
        
        resource_request = ResourceRequest.query.get(resource_request_id)
        if not resource_request:
            return
        
        items = ResourceRequestItem.query.filter_by(request_id=resource_request_id).all()
        
        total_required = sum(item.required_quantity for item in items)
        total_delivered = sum(item.delivered_quantity for item in items)
        
        resource_request.total_required_quantity = total_required
        resource_request.total_delivered_quantity = total_delivered
        resource_request.total_remaining_quantity = total_required - total_delivered
        
        if total_required > 0:
            resource_request.completion_percentage = (total_delivered / total_required) * 100
        
        # تحديث حالة الطلب
        all_completed = all(item.is_completed for item in items)
        
        if all_completed and resource_request.status != 'completed':
            resource_request.status = 'completed'
            resource_request.completed_at = datetime.utcnow()
        elif not all_completed and resource_request.status == 'completed':
            resource_request.status = 'started'
        
        resource_request.updated_at = datetime.utcnow()
        
        db.session.commit()

    @staticmethod
    def update_equipment_request_metrics(equipment_request_id):
        """تحديث مؤشرات طلب المعدات"""
        from app.models import EquipmentRequest, EquipmentRequestItem
        
        equipment_request = EquipmentRequest.query.get(equipment_request_id)
        if not equipment_request:
            return
        
        items = EquipmentRequestItem.query.filter_by(request_id=equipment_request_id).all()
        
        total_required = sum(item.required_quantity for item in items)
        total_delivered = sum(item.delivered_quantity for item in items)
        
        equipment_request.total_required_quantity = total_required
        equipment_request.total_delivered_quantity = total_delivered
        equipment_request.total_remaining_quantity = total_required - total_delivered
        
        if total_required > 0:
            equipment_request.completion_percentage = (total_delivered / total_required) * 100
        
        # تحديث حالة الطلب
        all_completed = all(item.is_completed for item in items)
        
        if all_completed and equipment_request.status != 'completed':
            equipment_request.status = 'completed'
            equipment_request.completed_at = datetime.utcnow()
        elif not all_completed and equipment_request.status == 'completed':
            equipment_request.status = 'started'
        
        equipment_request.updated_at = datetime.utcnow()
        
        db.session.commit()

    # ============================================
    # تحديث الهيكل الهرمي
    # ============================================

    @staticmethod
    def update_wbs_hierarchy(wbs_id):
        """تحديث المسار الهرمي لـ WBS"""
        try:
            wbs = WBS.query.get(wbs_id)
            if not wbs:
                return

            if wbs.parent_id:
                parent = WBS.query.get(wbs.parent_id)
                if parent:
                    wbs.level = parent.level + 1
                    wbs.wbs_path = f"{parent.wbs_path}.{wbs.wbs_code}" if parent.wbs_path else wbs.wbs_code
            else:
                wbs.level = 1
                wbs.wbs_path = wbs.wbs_code

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث مسار WBS {wbs_id}: {str(e)}")

    @staticmethod
    def update_eps_hierarchy(eps_id):
        """تحديث المسار الهرمي لـ EPS"""
        try:
            eps = EPS.query.get(eps_id)
            if not eps:
                return

            if eps.parent_id:
                parent = EPS.query.get(eps.parent_id)
                if parent:
                    eps.level = parent.level + 1
                    eps.path = f"{parent.path}.{eps.eps_code}" if parent.path else eps.eps_code
            else:
                eps.level = 1
                eps.path = eps.eps_code

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث مسار EPS {eps_id}: {str(e)}")

    # ============================================
    # تحديث الموارد
    # ============================================

    @staticmethod
    def update_resource_metrics(resource_id):
        """تحديث مؤشرات المورد (محسن)"""
        try:
            resource = Resource.query.get(resource_id)
            if not resource:
                return

            # حساب الكمية المخصصة من الأنشطة
            total_allocated = 0
            total_cost = 0
            for assignment in resource.assignments:
                total_allocated += assignment.planned_quantity or 0
                total_cost += assignment.planned_cost or 0

            # حساب الكمية المخصصة من المهام
            for task_assign in resource.task_assignments:
                total_allocated += task_assign.planned_quantity or 0
                total_cost += task_assign.planned_cost or 0

            # تحديث الكمية المتاحة
            resource.available_quantity = (resource.available_quantity or 0) - total_allocated
            resource.total_allocated = total_allocated
            resource.total_cost = total_cost

            # تحديث نسبة الاستخدام
            if resource.maximum_quantity and resource.maximum_quantity > 0:
                resource.utilization = (total_allocated / resource.maximum_quantity) * 100
            else:
                resource.utilization = 0

            # التحقق من المخزون المنخفض
            if resource.minimum_quantity and resource.available_quantity < resource.minimum_quantity:
                # إشعار بانخفاض المخزون
                if resource.org_id:
                    org_admins = User.query.filter_by(org_id=resource.org_id, role='org_admin').all()
                    for admin in org_admins:
                        NotificationService.low_stock_alert(admin, resource)

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات المورد {resource_id}: {str(e)}")

    # ============================================
    # تحديث WBS
    # ============================================

    @staticmethod
    def update_wbs_metrics(wbs):
        """تحديث مؤشرات WBS (محسن)"""
        try:
            activities = Activity.query.filter_by(wbs_id=wbs.id).all()

            if not activities:
                return

            # حساب التقدم
            total_weight = 0
            weighted_progress = 0
            total_planned = 0
            total_actual = 0

            for activity in activities:
                weight = activity.planned_cost or 1
                total_weight += weight
                weighted_progress += (activity.progress_percentage or 0) * weight
                total_planned += activity.planned_cost or 0
                total_actual += activity.actual_cost or 0

            wbs.progress_percentage = (weighted_progress / total_weight) if total_weight > 0 else 0
            wbs.planned_cost = total_planned
            wbs.actual_cost = total_actual
            wbs.cost_variance = total_actual - total_planned

            # تحديث المجموع التراكمي (WBS Summary)
            children = WBS.query.filter_by(parent_id=wbs.id).all()
            for child in children:
                child.progress_percentage = UpdateService._aggregate_child_progress(child)

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات WBS {wbs.id}: {str(e)}")

    @staticmethod
    def _aggregate_child_progress(wbs):
        """تجميع تقدم الأطفال في WBS"""
        activities = Activity.query.filter_by(wbs_id=wbs.id).all()
        if activities:
            return sum(a.progress_percentage or 0 for a in activities) / len(activities)
        
        children = WBS.query.filter_by(parent_id=wbs.id).all()
        if children:
            return sum(c.progress_percentage or 0 for c in children) / len(children)
        
        return 0

    # ============================================
    # تحديث التقدم التلقائي
    # ============================================

    @staticmethod
    def auto_update_progress(project_id):
        """✅ تحديث تلقائي للتقدم بناءً على الوقت المنقضي"""
        project = Project.query.get(project_id)
        if not project:
            return

        activities = Activity.query.filter_by(project_id=project_id).all()

        for activity in activities:
            if activity.status == 'in_progress' and activity.original_duration:
                # حساب التقدم الافتراضي بناءً على الوقت المنقضي
                if activity.actual_start:
                    elapsed = (datetime.utcnow() - activity.actual_start).days
                    expected_progress = min(100, (elapsed / activity.original_duration) * 100)
                    
                    # تحديث فقط إذا كان التقدم الفعلي أقل من المتوقع
                    if activity.progress_percentage < expected_progress:
                        activity.progress_percentage = min(activity.progress_percentage + 2, expected_progress)

        db.session.commit()
        UpdateService.update_project_metrics(project)

    # ============================================
    # إعادة حساب كاملة
    # ============================================

    @staticmethod
    def full_recalculation(org_id=None):
        """✅ إعادة حساب كاملة لجميع المشاريع في المؤسسة"""
        try:
            query = Project.query
            if org_id:
                query = query.filter_by(org_id=org_id)
            
            projects = query.all()
            total = len(projects)
            
            logger.info(f"بدء إعادة الحساب الكاملة لـ {total} مشروع")
            
            for idx, project in enumerate(projects):
                logger.info(f"تحديث المشروع {idx+1}/{total}: {project.name}")
                UpdateService.update_all_metrics(project.id, trigger_ai=False)
            
            logger.info(f"✅ اكتملت إعادة الحساب الكاملة لـ {total} مشروع")
            return True
            
        except Exception as e:
            logger.error(f"خطأ في إعادة الحساب الكاملة: {str(e)}")
            return False
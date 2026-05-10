"""
update_service.py - خدمة التحديث المتكاملة للمشاريع والأنشطة والمهام
"""

from datetime import datetime, timedelta, date
from flask import current_app
from app.models import db
from app.models import (
    Project, ProjectProgress, ProjectPerformance, ProjectCost, ProjectDates,EPS
)
from app.models.primavera_models import (
    Activity, ActivityStep, ActivityResource, ActivityExpense, 
    WBS, ActivityRelationship, Resource
)
from app.models.task_models import (
    Task, TaskPlanning, TaskExecution, TaskProgress, TaskResource,
    TaskRequirement, TaskRequirementVerification
)
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class UpdateService:
    """خدمة التحديث المتكاملة - تحديث جميع المؤشرات"""

    # ============================================
    # التحديث الرئيسي
    # ============================================

    @staticmethod
    def update_all_metrics(project_id, update_type='full'):
        """
        تحديث جميع مؤشرات المشروع

        Args:
            project_id: معرف المشروع
            update_type: نوع التحديث ('full', 'progress', 'cost', 'schedule')
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

            db.session.commit()
            logger.info(f"✅ تم تحديث مؤشرات المشروع {project.name} بنجاح")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تحديث مؤشرات المشروع {project_id}: {str(e)}")
            return False

    # ============================================
    # تحديث الأنشطة
    # ============================================

    @staticmethod
    def update_activity_metrics(activity, update_type='full'):
        """تحديث مؤشرات النشاط"""
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

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات النشاط {activity.id}: {str(e)}")

    @staticmethod
    def _update_activity_progress(activity):
        """تحديث نسبة إنجاز النشاط"""
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
            activity.progress_percentage = (weighted_progress / total_weight) if total_weight > 0 else 0
            return

        # 3. من المدة
        if activity.original_duration and activity.original_duration > 0:
            activity.progress_percentage = (activity.actual_duration or 0) / activity.original_duration * 100

    @staticmethod
    def _update_activity_cost(activity):
        """تحديث تكلفة النشاط"""
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

    @staticmethod
    def _update_activity_dates(activity):
        """تحديث تواريخ النشاط"""
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
        """تحديث مدة النشاط"""
        # المدة المخططة
        if activity.planned_start and activity.planned_finish:
            # التأكد من أن planned_start و planned_finish من نفس النوع
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

    @staticmethod
    def _update_activity_status(activity):
        """تحديث حالة النشاط"""
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
            # التحقق من النوع قبل المقارنة
            planned_finish = activity.planned_finish
            if hasattr(planned_finish, 'date'):
                planned_finish = planned_finish.date()
            now_date = datetime.now().date()
            if now_date > planned_finish:
                activity.status = 'delayed'

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
    # تحديث WBS
    # ============================================

    @staticmethod
    def update_wbs_metrics(wbs):
        """تحديث مؤشرات WBS"""
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

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات WBS {wbs.id}: {str(e)}")

    # ============================================
    # تحديث المشروع
    # ============================================

    @staticmethod
    def update_project_metrics(project):
        """تحديث مؤشرات المشروع"""
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

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات المشروع {project.id}: {str(e)}")

    @staticmethod
    def _update_project_progress(project):
        """تحديث تقدم المشروع"""
        # حساب التقدم من WBS
        wbs_nodes = WBS.query.filter_by(project_id=project.id).all()
        if wbs_nodes:
            total_weight = 0
            weighted_progress = 0
            for wbs in wbs_nodes:
                weight = wbs.planned_cost or 1
                total_weight += weight
                weighted_progress += (wbs.progress_percentage or 0) * weight
            project.progress.progress_percentage = (weighted_progress / total_weight) if total_weight > 0 else 0
        else:
            # حساب من الأنشطة
            activities = Activity.query.filter_by(project_id=project.id).all()
            if activities:
                total_weight = 0
                weighted_progress = 0
                for activity in activities:
                    weight = activity.planned_cost or 1
                    total_weight += weight
                    weighted_progress += (activity.progress_percentage or 0) * weight
                project.progress.progress_percentage = (weighted_progress / total_weight) if total_weight > 0 else 0

        # تحديث physical_progress
        project.progress.physical_progress = project.progress.progress_percentage
        project.progress.updated_at = datetime.utcnow()

    @staticmethod
    def _update_project_cost(project):
        """تحديث تكاليف المشروع"""
        total_planned = 0
        total_actual = 0
        labor_cost = 0
        material_cost = 0
        equipment_cost = 0
        other_cost = 0

        activities = Activity.query.filter_by(project_id=project.id).all()

        for activity in activities:
            total_planned += activity.planned_cost or 0
            total_actual += activity.actual_cost or 0

            # تصنيف التكاليف حسب نوع المورد
            for resource_assign in activity.resources:
                if resource_assign.resource:
                    cost = resource_assign.actual_cost or 0
                    res_type = resource_assign.resource.resource_type or 'other'
                    if res_type == 'labor':
                        labor_cost += cost
                    elif res_type == 'material':
                        material_cost += cost
                    elif res_type == 'equipment':
                        equipment_cost += cost
                    else:
                        other_cost += cost

        project.cost.total_planned_cost = total_planned
        project.cost.total_actual_cost = total_actual
        project.cost.labor_cost = labor_cost
        project.cost.material_cost = material_cost
        project.cost.equipment_cost = equipment_cost
        project.cost.other_cost = other_cost

    @staticmethod
    def _update_project_earned_value(project):
        """تحديث القيمة المكتسبة للمشروع"""
        # الحصول على الميزانية
        if project.budget:
            total_budget = project.budget.current_budget or 0
        else:
            total_budget = 0

        progress = project.progress.progress_percentage if project.progress else 0

        # PV (Planned Value)
        project.performance.planned_value = total_budget

        # EV (Earned Value)
        project.performance.earned_value = total_budget * (progress / 100)

        # AC (Actual Cost)
        project.performance.actual_cost = project.cost.total_actual_cost if project.cost else 0

        # CPI (Cost Performance Index)
        if project.performance.actual_cost and project.performance.actual_cost > 0:
            project.performance.cpi = project.performance.earned_value / project.performance.actual_cost
        else:
            project.performance.cpi = 1.0

        # SPI (Schedule Performance Index)
        if project.performance.planned_value and project.performance.planned_value > 0:
            project.performance.spi = project.performance.earned_value / project.performance.planned_value
        else:
            project.performance.spi = 1.0

        # CSI (Cost Schedule Index)
        project.performance.csi = (project.performance.cpi or 1.0) * (project.performance.spi or 1.0)

        # EAC (Estimate at Completion)
        if project.performance.cpi and project.performance.cpi > 0:
            project.performance.eac = total_budget / project.performance.cpi

        # ETC (Estimate to Complete)
        if project.performance.eac:
            project.performance.etc = project.performance.eac - (project.performance.actual_cost or 0)

        # VAC (Variance at Completion)
        if project.performance.eac:
            project.performance.vac = total_budget - project.performance.eac

    @staticmethod
    def _update_project_dates(project):
        """تحديث تواريخ المشروع"""
        activities = Activity.query.filter_by(project_id=project.id).all()

        # التواريخ المخططة
        planned_starts = []
        planned_finishes = []
        for a in activities:
            if a.planned_start:
                planned_starts.append(a.planned_start)
            if a.planned_finish:
                planned_finishes.append(a.planned_finish)

        if planned_starts:
            project.dates.planned_start = min(planned_starts)
        if planned_finishes:
            project.dates.planned_finish = max(planned_finishes)

        # التواريخ الفعلية
        actual_starts = []
        actual_finishes = []
        for a in activities:
            if a.actual_start:
                actual_starts.append(a.actual_start)
            if a.actual_finish:
                actual_finishes.append(a.actual_finish)

        if actual_starts:
            project.dates.actual_start = min(actual_starts)
        if actual_finishes:
            project.dates.actual_finish = max(actual_finishes)

        # تحديث تاريخ البيانات
        project.dates.data_date = datetime.utcnow()

    @staticmethod
    def _update_project_status(project):
        """تحديث حالة المشروع"""
        progress = project.progress.progress_percentage if project.progress else 0

        # مكتمل
        if progress >= 100:
            project.status = 'completed'
            if project.dates and not project.dates.actual_finish:
                project.dates.actual_finish = datetime.utcnow()
            return

        # تأخير خطير
        if project.dates and project.dates.planned_finish:
            planned_finish = project.dates.planned_finish
            if hasattr(planned_finish, 'date'):
                planned_finish = planned_finish.date()
            delay_days = (datetime.now().date() - planned_finish).days
            if delay_days > 15:
                project.status = 'critical_delay'
                return

        # تأخير
        if hasattr(project, 'is_overdue') and callable(project.is_overdue):
            if project.is_overdue():
                project.status = 'delayed'
                return
        else:
            # حساب بسيط للتأخير
            if project.dates and project.dates.planned_finish:
                planned_finish = project.dates.planned_finish
                if hasattr(planned_finish, 'date'):
                    planned_finish = planned_finish.date()
                if datetime.now().date() > planned_finish:
                    project.status = 'delayed'
                    return

        # قيد التنفيذ
        if progress > 0:
            project.status = 'active'  # استخدام active بدلاً من in_progress
            if project.dates and not project.dates.actual_start:
                project.dates.actual_start = datetime.utcnow()
            return

        # تخطيط
        project.status = 'planning'

    # ============================================
    # تحديث المسار الحرج
    # ============================================

    @staticmethod
    def update_critical_path(project_id):
        """تحديث المسار الحرج للمشروع"""
        try:
            activities = Activity.query.filter_by(project_id=project_id).all()

            if not activities:
                return

            # إعادة تعيين جميع الأنشطة كغير حرجة
            for activity in activities:
                activity.is_critical = False

            # حساب التواريخ المبكرة (Forward Pass)
            # ترتيب الأنشطة حسب التبعيات
            sorted_activities = UpdateService._topological_sort(activities)

            for activity in sorted_activities:
                UpdateService._calculate_forward_pass(activity)

            # حساب التواريخ المتأخرة (Backward Pass)
            for activity in reversed(sorted_activities):
                UpdateService._calculate_backward_pass(activity)

            # تحديد الأنشطة الحرجة (Total Float = 0)
            for activity in activities:
                if activity.total_float is not None and activity.total_float <= 0:
                    activity.is_critical = True

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث المسار الحرج للمشروع {project_id}: {str(e)}")

    @staticmethod
    def _topological_sort(activities):
        """ترتيب الأنشطة طوبولوجياً حسب التبعيات"""
        # بناء رسم بياني بسيط للتبعيات
        activity_dict = {a.id: a for a in activities}
        graph = {a.id: [] for a in activities}
        in_degree = {a.id: 0 for a in activities}

        for activity in activities:
            predecessors = ActivityRelationship.query.filter_by(successor_id=activity.id).all()
            for pred in predecessors:
                if pred.predecessor_id in activity_dict:
                    graph[pred.predecessor_id].append(activity.id)
                    in_degree[activity.id] += 1

        # قائمة الانتظار للأنشطة بدون تبعيات
        queue = [aid for aid, degree in in_degree.items() if degree == 0]
        sorted_activities = []

        while queue:
            current_id = queue.pop(0)
            sorted_activities.append(activity_dict[current_id])

            for neighbor in graph[current_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return sorted_activities

    @staticmethod
    def _calculate_forward_pass(activity):
        """حساب التواريخ المبكرة (Forward Pass)"""
        # حساب ES (Early Start)
        predecessors = ActivityRelationship.query.filter_by(successor_id=activity.id).all()

        if not predecessors:
            # بداية المشروع
            activity.early_start = activity.planned_start or datetime.utcnow()
        else:
            max_ef = None
            for pred in predecessors:
                pred_activity = Activity.query.get(pred.predecessor_id)
                if pred_activity and pred_activity.early_finish:
                    ef = pred_activity.early_finish
                    if pred.lag_days:
                        ef += timedelta(days=pred.lag_days)
                    if max_ef is None or ef > max_ef:
                        max_ef = ef
            activity.early_start = max_ef or activity.planned_start or datetime.utcnow()

        # EF (Early Finish) = ES + Duration
        duration = activity.original_duration or 0
        activity.early_finish = activity.early_start + timedelta(days=duration)

    @staticmethod
    def _calculate_backward_pass(activity):
        """حساب التواريخ المتأخرة (Backward Pass)"""
        # حساب LF (Late Finish)
        successors = ActivityRelationship.query.filter_by(predecessor_id=activity.id).all()

        if not successors:
            # نهاية المشروع
            activity.late_finish = activity.planned_finish or activity.early_finish or datetime.utcnow()
        else:
            min_ls = None
            for succ in successors:
                succ_activity = Activity.query.get(succ.successor_id)
                if succ_activity and succ_activity.late_start:
                    ls = succ_activity.late_start
                    if succ.lag_days:
                        ls -= timedelta(days=succ.lag_days)
                    if min_ls is None or ls < min_ls:
                        min_ls = ls
            activity.late_finish = min_ls or activity.planned_finish or activity.early_finish or datetime.utcnow()

        # LS (Late Start) = LF - Duration
        duration = activity.original_duration or 0
        activity.late_start = activity.late_finish - timedelta(days=duration)

        # Total Float
        if activity.early_start and activity.late_start:
            total_float = activity.late_start - activity.early_start
            activity.total_float = total_float.days

    # ============================================
    # تحديث الموارد
    # ============================================

    @staticmethod
    def update_resource_metrics(resource_id):
        """تحديث مؤشرات المورد"""
        try:
            resource = Resource.query.get(resource_id)
            if not resource:
                return

            # حساب الكمية المخصصة
            total_allocated = 0
            for assignment in resource.assignments:  # ActivityResource
                total_allocated += assignment.planned_quantity or 0

            # تحديث الكمية المتاحة
            resource.available_quantity = (resource.available_quantity or 0) - total_allocated

            # تحديث نسبة الاستخدام
            if resource.maximum_quantity and resource.maximum_quantity > 0:
                resource.utilization = (total_allocated / resource.maximum_quantity) * 100
            else:
                resource.utilization = 0

            db.session.commit()

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات المورد {resource_id}: {str(e)}")

    # ============================================
    # تحديث المهام
    # ============================================

    @staticmethod
    def update_task_metrics(task_id):
        """تحديث مؤشرات المهمة"""
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

        except Exception as e:
            logger.error(f"خطأ في تحديث مؤشرات المهمة {task_id}: {str(e)}")

    # ============================================
    # دوال مساعدة إضافية
    # ============================================
    # أضف هذه الدوال في update_service.py

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
        
        # تحديث حالة الطلب إذا لزم الأمر
        all_completed = all(item.is_completed for item in items)
        
        if all_completed and equipment_request.status != 'completed':
            equipment_request.status = 'completed'
            equipment_request.completed_at = datetime.utcnow()
        elif not all_completed and equipment_request.status == 'completed':
            equipment_request.status = 'partially_delivered'
        
        equipment_request.updated_at = datetime.utcnow()
        
        db.session.commit()
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
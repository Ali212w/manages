"""
cost_update_service.py - خدمة متكاملة لتحديث وحساب التكاليف
تضمن تحديث جميع التكاليف من أدنى مستوى إلى أعلى مستوى بدقة
"""

from datetime import datetime
from sqlalchemy import func
from app.models import db
import logging

logger = logging.getLogger(__name__)


class CostUpdateService:
    """
    خدمة متكاملة لتحديث وحساب التكاليف
    تضمن تحديث جميع المستويات: Task → Activity → WBS → Project
    """

    # ============================================
    # 1. تحديث تكاليف المهمة (المستوى الأساسي)
    # ============================================
    
    @staticmethod
    def update_task_cost(task_id):
        """
        تحديث التكلفة الفعلية للمهمة
        المصادر:
        1. الموارد المخصصة للمهمة (TaskResource)
        2. التكاليف المباشرة من TaskExecution
        """
        from app.models.task_models import Task, TaskResource, TaskExecution
        
        task = Task.query.get(task_id)
        if not task:
            logger.warning(f"⚠️ المهمة {task_id} غير موجودة")
            return None
        
        logger.info(f"📊 تحديث تكاليف المهمة: {task.task_code} - {task.task_name}")
        
        # حساب التكاليف
        total_planned_cost = 0
        total_actual_cost = 0
        
        # 1.1 تكاليف الموارد
        task_resources = TaskResource.query.filter_by(task_id=task_id).all()
        for tr in task_resources:
            if tr.resource:
                unit_price = tr.resource.cost_per_unit or 0
                total_planned_cost += (tr.planned_quantity or 0) * unit_price
                total_actual_cost += (tr.actual_quantity or 0) * unit_price
            else:
                total_planned_cost += tr.planned_cost or 0
                total_actual_cost += tr.actual_cost or 0
        
        # 1.2 تكاليف التنفيذ
        if task.execution:
            task.execution.planned_cost = total_planned_cost
            task.execution.actual_cost = total_actual_cost
        else:
            execution = TaskExecution(
                task_id=task_id,
                planned_cost=total_planned_cost,
                actual_cost=total_actual_cost
            )
            db.session.add(execution)
        
        db.session.commit()
        
        logger.info(f"   ✅ المهمة: المخطط={total_planned_cost:.2f} | الفعلي={total_actual_cost:.2f}")
        
        return {
            'task_id': task_id,
            'planned_cost': total_planned_cost,
            'actual_cost': total_actual_cost,
            'variance': total_planned_cost - total_actual_cost
        }

    # ============================================
    # 2. تحديث تكاليف النشاط
    # ============================================
    
    @staticmethod
    def update_activity_cost(activity_id):
        """
        تحديث التكلفة الفعلية للنشاط
        المصادر:
        1. الموارد المخصصة للنشاط (ActivityResource)
        2. المهام المرتبطة بالنشاط (Tasks)
        3. المصروفات المباشرة (ActivityExpense)
        """
        from app.models.primavera_models import Activity, ActivityResource, ActivityExpense
        from app.models.task_models import Task
        
        activity = Activity.query.get(activity_id)
        if not activity:
            logger.warning(f"⚠️ النشاط {activity_id} غير موجود")
            return None
        
        logger.info(f"📊 تحديث تكاليف النشاط: {activity.activity_id} - {activity.activity_name}")
        
        total_planned_cost = 0
        total_actual_cost = 0
        labor_cost = 0
        material_cost = 0
        equipment_cost = 0
        
        # 2.1 تكاليف الموارد المباشرة
        activity_resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
        for ar in activity_resources:
            total_planned_cost += ar.planned_cost or 0
            total_actual_cost += ar.actual_cost or 0
            
            # تفصيل حسب نوع المورد
            if ar.resource:
                if ar.resource.resource_type == 'labor':
                    labor_cost += ar.actual_cost or 0
                elif ar.resource.resource_type == 'material':
                    material_cost += ar.actual_cost or 0
                elif ar.resource.resource_type == 'equipment':
                    equipment_cost += ar.actual_cost or 0
        
        # 2.2 تكاليف المهام المرتبطة
        tasks = Task.query.filter_by(activity_id=activity_id).all()
        for task in tasks:
            if task.execution:
                total_planned_cost += task.execution.planned_cost or 0
                total_actual_cost += task.execution.actual_cost or 0
        
        # 2.3 المصروفات المعتمدة
        expenses = ActivityExpense.query.filter_by(
            activity_id=activity_id,
            is_approved=True
        ).all()
        for expense in expenses:
            total_actual_cost += expense.amount or 0
        
        # تحديث النشاط
        activity.planned_cost = total_planned_cost
        activity.actual_cost = total_actual_cost
        activity.remaining_cost = max(0, total_planned_cost - total_actual_cost)
        activity.cost_variance = total_actual_cost - total_planned_cost
        
        db.session.commit()
        
        logger.info(f"   ✅ النشاط: المخطط={total_planned_cost:.2f} | الفعلي={total_actual_cost:.2f}")
        
        return {
            'activity_id': activity_id,
            'planned_cost': total_planned_cost,
            'actual_cost': total_actual_cost,
            'labor_cost': labor_cost,
            'material_cost': material_cost,
            'equipment_cost': equipment_cost,
            'variance': total_planned_cost - total_actual_cost
        }

    # ============================================
    # 3. تحديث تكاليف WBS
    # ============================================
    
    @staticmethod
    def update_wbs_cost(wbs_id):
        """
        تحديث تكاليف عنصر WBS
        يجمع التكاليف من الأنشطة والعناصر الفرعية
        """
        from app.models.primavera_models import WBS, Activity
        
        wbs = WBS.query.get(wbs_id)
        if not wbs:
            logger.warning(f"⚠️ WBS {wbs_id} غير موجود")
            return None
        
        logger.info(f"📊 تحديث تكاليف WBS: {wbs.wbs_code} - {wbs.name}")
        
        total_planned_cost = 0
        total_actual_cost = 0
        
        # 3.1 تكاليف الأنشطة المباشرة
        activities = Activity.query.filter_by(wbs_id=wbs_id).all()
        for activity in activities:
            total_planned_cost += activity.planned_cost or 0
            total_actual_cost += activity.actual_cost or 0
        
        # 3.2 تكاليف العناصر الفرعية
        children = WBS.query.filter_by(parent_id=wbs_id).all()
        for child in children:
            child_costs = CostUpdateService.update_wbs_cost(child.id)
            if child_costs:
                total_planned_cost += child_costs['planned_cost']
                total_actual_cost += child_costs['actual_cost']
        
        # تحديث WBS
        wbs.planned_cost = total_planned_cost
        wbs.actual_cost = total_actual_cost
        wbs.cost_variance = total_planned_cost - total_actual_cost
        
        db.session.commit()
        
        logger.info(f"   ✅ WBS: المخطط={total_planned_cost:.2f} | الفعلي={total_actual_cost:.2f}")
        
        return {
            'wbs_id': wbs_id,
            'planned_cost': total_planned_cost,
            'actual_cost': total_actual_cost,
            'variance': total_planned_cost - total_actual_cost
        }

    # ============================================
    # 4. تحديث تكاليف المشروع (المستوى الأعلى)
    # ============================================
    
    @staticmethod
    def update_project_cost(project_id):
        """
        تحديث التكلفة الفعلية للمشروع
        يجمع التكاليف من جميع الأنشطة والمهام المباشرة
        """
        from app.models.project_models import Project, ProjectCost
        from app.models.primavera_models import Activity,ActivityResource
        from app.models.task_models import Task
        
        project = Project.query.get(project_id)
        if not project:
            logger.warning(f"⚠️ المشروع {project_id} غير موجود")
            return None
        
        logger.info(f"📊 تحديث تكاليف المشروع: {project.project_code} - {project.name}")
        
        total_planned_cost = 0
        total_actual_cost = 0
        labor_cost = 0
        material_cost = 0
        equipment_cost = 0
        other_cost = 0
        
        # 4.1 تكاليف الأنشطة
        activities = Activity.query.filter_by(project_id=project_id).all()
        for activity in activities:
            total_planned_cost += activity.planned_cost or 0
            total_actual_cost += activity.actual_cost or 0
        
        # 4.2 تكاليف المهام المباشرة (غير المرتبطة بأنشطة)
        tasks = Task.query.filter_by(project_id=project_id, activity_id=None).all()
        for task in tasks:
            if task.execution:
                total_planned_cost += task.execution.planned_cost or 0
                total_actual_cost += task.execution.actual_cost or 0
        
        # 4.3 تفصيل التكاليف حسب النوع (من الأنشطة)
        for activity in activities:
            activity_resources = ActivityResource.query.filter_by(activity_id=activity.id).all()
            for ar in activity_resources:
                if ar.resource:
                    if ar.resource.resource_type == 'labor':
                        labor_cost += ar.actual_cost or 0
                    elif ar.resource.resource_type == 'material':
                        material_cost += ar.actual_cost or 0
                    elif ar.resource.resource_type == 'equipment':
                        equipment_cost += ar.actual_cost or 0
                    else:
                        other_cost += ar.actual_cost or 0
        
        # 4.4 تحديث أو إنشاء ProjectCost
        project_cost = ProjectCost.query.filter_by(project_id=project_id).first()
        if project_cost:
            project_cost.total_planned_cost = total_planned_cost
            project_cost.total_actual_cost = total_actual_cost
            project_cost.labor_cost = labor_cost
            project_cost.material_cost = material_cost
            project_cost.equipment_cost = equipment_cost
            project_cost.other_cost = other_cost
        else:
            project_cost = ProjectCost(
                project_id=project_id,
                total_planned_cost=total_planned_cost,
                total_actual_cost=total_actual_cost,
                labor_cost=labor_cost,
                material_cost=material_cost,
                equipment_cost=equipment_cost,
                other_cost=other_cost
            )
            db.session.add(project_cost)
        
        # 4.5 تحديث القيمة المكتسبة
        ev_result = CostUpdateService.update_earned_value(project_id)
        
        # 4.6 تحديث تقدم المشروع
        CostUpdateService.update_project_progress(project_id)
        
        db.session.commit()
        
        logger.info(f"   ✅ المشروع: المخطط={total_planned_cost:.2f} | الفعلي={total_actual_cost:.2f}")
        logger.info(f"   📈 SPI={ev_result.get('spi', 1):.2f} | CPI={ev_result.get('cpi', 1):.2f}")
        
        return {
            'project_id': project_id,
            'planned_cost': total_planned_cost,
            'actual_cost': total_actual_cost,
            'labor_cost': labor_cost,
            'material_cost': material_cost,
            'equipment_cost': equipment_cost,
            'other_cost': other_cost,
            'variance': total_planned_cost - total_actual_cost,
            'variance_percentage': ((total_planned_cost - total_actual_cost) / total_planned_cost * 100) if total_planned_cost > 0 else 0,
            'spi': ev_result.get('spi', 1),
            'cpi': ev_result.get('cpi', 1)
        }

    # ============================================
    # 5. تحديث القيمة المكتسبة (Earned Value)
    # ============================================
    
    @staticmethod
    def update_earned_value(project_id):
        """
        تحديث مؤشرات القيمة المكتسبة للمشروع
        """
        from app.models.project_models import Project, ProjectPerformance, ProjectCost
        from app.models.primavera_models import Activity
        
        project = Project.query.get(project_id)
        if not project:
            return None
        
        # الحصول على التكاليف
        project_cost = ProjectCost.query.filter_by(project_id=project_id).first()
        planned_cost = project_cost.total_planned_cost if project_cost else 0
        actual_cost = project_cost.total_actual_cost if project_cost else 0
        
        # حساب القيمة المكتسبة من الأنشطة
        activities = Activity.query.filter_by(project_id=project_id).all()
        earned_value = 0
        for activity in activities:
            # القيمة المكتسبة = التكلفة المخططة × نسبة التقدم
            ev = (activity.planned_cost or 0) * (activity.progress_percentage / 100)
            earned_value += ev
        
        # حساب المؤشرات
        spi = earned_value / planned_cost if planned_cost > 0 else 1
        cpi = earned_value / actual_cost if actual_cost > 0 else 1
        csi = spi * cpi
        
        # التوقعات
        if cpi > 0:
            eac = actual_cost + (planned_cost - earned_value) / cpi
            etc = (planned_cost - earned_value) / cpi
            vac = planned_cost - eac
        else:
            eac = actual_cost
            etc = 0
            vac = planned_cost - actual_cost
        
        # تحديث الأداء
        performance = ProjectPerformance.query.filter_by(project_id=project_id).first()
        if performance:
            performance.planned_value = planned_cost
            performance.earned_value = earned_value
            performance.actual_cost = actual_cost
            performance.spi = spi
            performance.cpi = cpi
            performance.csi = csi
            performance.eac = eac
            performance.etc = etc
            performance.vac = vac
        else:
            performance = ProjectPerformance(
                project_id=project_id,
                planned_value=planned_cost,
                earned_value=earned_value,
                actual_cost=actual_cost,
                spi=spi,
                cpi=cpi,
                csi=csi,
                eac=eac,
                etc=etc,
                vac=vac
            )
            db.session.add(performance)
        
        db.session.commit()
        
        logger.info(f"   📊 القيمة المكتسبة: EV={earned_value:.2f} | SPI={spi:.2f} | CPI={cpi:.2f}")
        
        return {
            'planned_value': planned_cost,
            'earned_value': earned_value,
            'actual_cost': actual_cost,
            'spi': spi,
            'cpi': cpi,
            'csi': csi,
            'eac': eac,
            'etc': etc,
            'vac': vac
        }

    # ============================================
    # 6. تحديث تقدم المشروع
    # ============================================
    
    @staticmethod
    def update_project_progress(project_id):
        """
        تحديث نسبة تقدم المشروع
        """
        from app.models.project_models import Project, ProjectProgress
        from app.models.primavera_models import Activity
        
        # حساب متوسط تقدم الأنشطة
        activities = Activity.query.filter_by(project_id=project_id).all()
        if activities:
            avg_progress = sum(a.progress_percentage or 0 for a in activities) / len(activities)
        else:
            avg_progress = 0
        
        # تحديث أو إنشاء ProjectProgress
        progress = ProjectProgress.query.filter_by(project_id=project_id).first()
        if progress:
            progress.progress_percentage = avg_progress
            progress.physical_progress = avg_progress
            progress.updated_at = datetime.utcnow()
        else:
            progress = ProjectProgress(
                project_id=project_id,
                progress_percentage=avg_progress,
                physical_progress=avg_progress
            )
            db.session.add(progress)
        
        db.session.commit()
        
        return avg_progress

    # ============================================
    # 7. تحديث شامل من أي نقطة
    # ============================================
    
    @staticmethod
    def update_all_costs(entity_type, entity_id):
        """
        تحديث جميع التكاليف من الأسفل إلى الأعلى
        """
        from app.models import Task,Activity,WBS,ActivityResource,Resource,TaskResource
        logger.info(f"🔄 بدء التحديث الشامل للكيان: {entity_type} ID={entity_id}")
        
        result = {}
        
        if entity_type == 'task':
            result = CostUpdateService.update_task_cost(entity_id)
            task = Task.query.get(entity_id)
            if task and task.activity_id:
                CostUpdateService.update_activity_cost(task.activity_id)
            if task and task.project_id:
                CostUpdateService.update_project_cost(task.project_id)
        
        elif entity_type == 'activity':
            result = CostUpdateService.update_activity_cost(entity_id)
            activity = Activity.query.get(entity_id)
            if activity and activity.wbs_id:
                CostUpdateService.update_wbs_cost(activity.wbs_id)
            if activity and activity.project_id:
                CostUpdateService.update_project_cost(activity.project_id)
        
        elif entity_type == 'wbs':
            result = CostUpdateService.update_wbs_cost(entity_id)
            wbs = WBS.query.get(entity_id)
            if wbs and wbs.project_id:
                CostUpdateService.update_project_cost(wbs.project_id)
        
        elif entity_type == 'project':
            result = CostUpdateService.update_project_cost(entity_id)
        
        elif entity_type == 'resource':
            # تحديث جميع المهام والأنشطة المرتبطة بهذا المورد
            resource = Resource.query.get(entity_id)
            if resource:
                # تحديث المهام
                task_resources = TaskResource.query.filter_by(resource_id=entity_id).all()
                for tr in task_resources:
                    CostUpdateService.update_task_cost(tr.task_id)
                
                # تحديث الأنشطة
                activity_resources = ActivityResource.query.filter_by(resource_id=entity_id).all()
                for ar in activity_resources:
                    CostUpdateService.update_activity_cost(ar.activity_id)
            
            result = {'updated_tasks': len(task_resources), 'updated_activities': len(activity_resources)}
        
        logger.info(f"✅ اكتمل التحديث الشامل")
        
        return result


# دالة مساعدة للحصول على ملخص التكاليف لمشروع
def get_project_cost_summary(project_id):
    """
    الحصول على ملخص كامل لتكاليف المشروع
    """
    from app.models.project_models import Project, ProjectCost, ProjectPerformance
    from app.models.primavera_models import Activity
    
    project = Project.query.get(project_id)
    if not project:
        return None
    
    project_cost = ProjectCost.query.filter_by(project_id=project_id).first()
    performance = ProjectPerformance.query.filter_by(project_id=project_id).first()
    
    # إحصائيات إضافية
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    return {
        'project': {
            'id': project.id,
            'name': project.name,
            'code': project.project_code,
            'status': project.status
        },
        'costs': {
            'planned': project_cost.total_planned_cost if project_cost else 0,
            'actual': project_cost.total_actual_cost if project_cost else 0,
            'variance': (project_cost.total_planned_cost - project_cost.total_actual_cost) if project_cost else 0,
            'labor': project_cost.labor_cost if project_cost else 0,
            'material': project_cost.material_cost if project_cost else 0,
            'equipment': project_cost.equipment_cost if project_cost else 0,
            'other': project_cost.other_cost if project_cost else 0
        },
        'performance': {
            'spi': performance.spi if performance else 1,
            'cpi': performance.cpi if performance else 1,
            'csi': performance.csi if performance else 1,
            'eac': performance.eac if performance else 0,
            'etc': performance.etc if performance else 0,
            'vac': performance.vac if performance else 0
        },
        'activities': {
            'total': len(activities),
            'with_cost': len([a for a in activities if a.actual_cost > 0]),
            'total_planned': sum(a.planned_cost or 0 for a in activities),
            'total_actual': sum(a.actual_cost or 0 for a in activities)
        }
    }
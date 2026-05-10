# app/services/cost_calculation_service.py

"""
نظام حساب التكاليف المتكامل
يحسب التكاليف بشكل هرمي: Task → Activity → WBS → Project
"""

from datetime import datetime
from flask import current_app
from app.models import db
from app.models.project_models import Project, ProjectCost, ProjectBudget, ProjectPerformance
from app.models.primavera_models import Activity, ActivityResource, WBS, Resource
from app.models.task_models import Task, TaskResource
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class CostCalculationService:
    """خدمة حساب التكاليف المتكاملة"""
    
    def __init__(self):
        self.notification_service = NotificationService()
    
    # ============================================
    # حساب تكاليف المهام (أدنى مستوى)
    # ============================================
    
    def calculate_task_cost(self, task_id):
        """حساب تكاليف مهمة واحدة"""
        task = Task.query.get(task_id)
        if not task:
            return None
        
        # حساب التكاليف من الموارد المخصصة للمهمة
        total_planned = 0
        total_actual = 0
        
        for resource_assign in task.resources:
            planned_cost = resource_assign.planned_quantity * (resource_assign.resource.cost_per_unit if resource_assign.resource else 0)
            actual_cost = resource_assign.actual_quantity * (resource_assign.resource.cost_per_unit if resource_assign.resource else 0)
            
            total_planned += planned_cost
            total_actual += actual_cost
            
            # تحديث سجل المهمة
            resource_assign.planned_cost = planned_cost
            resource_assign.actual_cost = actual_cost
        
        # تحديث التكاليف في جدول التنفيذ
        if task.execution:
            task.execution.planned_cost = total_planned
            task.execution.actual_cost = total_actual
        
        return {
            'task_id': task.id,
            'task_name': task.task_name,
            'planned_cost': total_planned,
            'actual_cost': total_actual,
            'variance': total_actual - total_planned,
            'variance_percentage': ((total_actual - total_planned) / total_planned * 100) if total_planned > 0 else 0
        }
    
    def calculate_all_tasks_costs(self, activity_id=None, project_id=None):
        """حساب تكاليف جميع المهام في نطاق معين"""
        query = Task.query
        
        if activity_id:
            query = query.filter_by(activity_id=activity_id)
        if project_id:
            query = query.filter_by(project_id=project_id)
        
        tasks = query.all()
        results = []
        
        for task in tasks:
            cost_data = self.calculate_task_cost(task.id)
            if cost_data:
                results.append(cost_data)
        
        return results
    
    # ============================================
    # حساب تكاليف الأنشطة (تجميع من المهام)
    # ============================================
    
    def calculate_activity_cost(self, activity_id):
        """حساب تكاليف نشاط واحد (تجميع من المهام والموارد المباشرة)"""
        activity = Activity.query.get(activity_id)
        if not activity:
            return None
        
        # 1. جمع تكاليف المهام المرتبطة بالنشاط
        tasks_cost = self.calculate_all_tasks_costs(activity_id=activity_id)
        
        total_planned_from_tasks = sum(t['planned_cost'] for t in tasks_cost)
        total_actual_from_tasks = sum(t['actual_cost'] for t in tasks_cost)
        
        # 2. جمع تكاليف الموارد المباشرة للنشاط (غير المرتبطة بمهام)
        direct_resources_cost = self.calculate_activity_direct_resources(activity_id)
        
        # 3. جمع مصروفات النشاط
        expenses_cost = self.calculate_activity_expenses(activity_id)
        
        # 4. حساب الإجماليات
        total_planned = total_planned_from_tasks + direct_resources_cost['planned'] + expenses_cost['planned']
        total_actual = total_actual_from_tasks + direct_resources_cost['actual'] + expenses_cost['actual']
        
        # تحديث تكاليف النشاط
        activity.planned_cost = total_planned
        activity.actual_cost = total_actual
        
        return {
            'activity_id': activity.id,
            'activity_name': activity.activity_name,
            'planned_cost': total_planned,
            'actual_cost': total_actual,
            'variance': total_actual - total_planned,
            'variance_percentage': ((total_actual - total_planned) / total_planned * 100) if total_planned > 0 else 0,
            'breakdown': {
                'from_tasks': {
                    'planned': total_planned_from_tasks,
                    'actual': total_actual_from_tasks
                },
                'direct_resources': direct_resources_cost,
                'expenses': expenses_cost
            }
        }
    
    def calculate_activity_direct_resources(self, activity_id):
        """حساب تكاليف الموارد المباشرة للنشاط"""
        resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
        
        planned = 0
        actual = 0
        
        for res in resources:
            resource = Resource.query.get(res.resource_id)
            if resource:
                planned += res.planned_quantity * resource.cost_per_unit
                actual += res.actual_quantity * resource.cost_per_unit
        
        return {'planned': planned, 'actual': actual}
    
    def calculate_activity_expenses(self, activity_id):
        """حساب مصروفات النشاط"""
        from app.models.primavera_models import ActivityExpense
        
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
        
        planned = sum(e.amount for e in expenses if not e.is_approved)
        actual = sum(e.amount for e in expenses if e.is_approved)
        
        return {'planned': planned, 'actual': actual}
    
    def calculate_all_activities_costs(self, wbs_id=None, project_id=None):
        """حساب تكاليف جميع الأنشطة في نطاق معين"""
        query = Activity.query
        
        if wbs_id:
            query = query.filter_by(wbs_id=wbs_id)
        if project_id:
            query = query.filter_by(project_id=project_id)
        
        activities = query.all()
        results = []
        
        for activity in activities:
            cost_data = self.calculate_activity_cost(activity.id)
            if cost_data:
                results.append(cost_data)
        
        return results
    
    # ============================================
    # حساب تكاليف WBS (تجميع من الأنشطة)
    # ============================================
    
    def calculate_wbs_cost(self, wbs_id):
        """حساب تكاليف WBS واحد (تجميع من الأنشطة)"""
        wbs = WBS.query.get(wbs_id)
        if not wbs:
            return None
        
        # جمع تكاليف الأنشطة في هذا الـ WBS
        activities_cost = self.calculate_all_activities_costs(wbs_id=wbs_id)
        
        total_planned = sum(a['planned_cost'] for a in activities_cost)
        total_actual = sum(a['actual_cost'] for a in activities_cost)
        
        # تحديث تكاليف الـ WBS
        wbs.planned_cost = total_planned
        wbs.actual_cost = total_actual
        wbs.budget = total_planned
        
        # حساب نسبة التقدم المرجحة
        self.calculate_wbs_progress(wbs, activities_cost)
        
        return {
            'wbs_id': wbs.id,
            'wbs_name': wbs.name,
            'planned_cost': total_planned,
            'actual_cost': total_actual,
            'variance': total_actual - total_planned,
            'variance_percentage': ((total_actual - total_planned) / total_planned * 100) if total_planned > 0 else 0,
            'activities_count': len(activities_cost),
            'activities': activities_cost
        }
    
    def calculate_wbs_progress(self, wbs, activities_cost):
        """حساب تقدم WBS بناءً على التكاليف"""
        if not activities_cost:
            wbs.progress_percentage = 0
            return
        
        total_weight = 0
        weighted_progress = 0
        
        for activity in activities_cost:
            # الوزن بناءً على التكلفة المخططة
            weight = activity['planned_cost']
            total_weight += weight
            weighted_progress += (activity['actual_cost'] / activity['planned_cost'] * 100) * weight if activity['planned_cost'] > 0 else 0
        
        if total_weight > 0:
            wbs.progress_percentage = weighted_progress / total_weight
    
    def calculate_all_wbs_costs(self, project_id):
        """حساب تكاليف جميع WBS في مشروع"""
        wbs_nodes = WBS.query.filter_by(project_id=project_id).all()
        results = []
        
        for wbs in wbs_nodes:
            cost_data = self.calculate_wbs_cost(wbs.id)
            if cost_data:
                results.append(cost_data)
        
        return results
    
    # ============================================
    # حساب تكاليف المشروع (أعلى مستوى)
    # ============================================
    
    def calculate_project_cost(self, project_id):
        """حساب تكاليف المشروع (تجميع من WBS)"""
        project = Project.query.get(project_id)
        if not project:
            return None
        
        # جمع تكاليف جميع WBS في المشروع
        wbs_costs = self.calculate_all_wbs_costs(project_id)
        
        total_planned = sum(w['planned_cost'] for w in wbs_costs)
        total_actual = sum(w['actual_cost'] for w in wbs_costs)
        
        # إضافة تكاليف إضافية للمشروع (مصاريف عامة، إلخ)
        overhead_cost = self.calculate_project_overhead(project_id)
        
        total_planned += overhead_cost['planned']
        total_actual += overhead_cost['actual']
        
        # تحديث جدول تكاليف المشروع
        if not project.cost:
            project.cost = ProjectCost(project_id=project_id)
        
        project.cost.total_planned_cost = total_planned
        project.cost.total_actual_cost = total_actual
        
        # تحديث ميزانية المشروع
        if not project.budget:
            project.budget = ProjectBudget(project_id=project_id)
        
        project.budget.current_budget = total_planned
        project.budget.distributed_budget = total_planned
        
        # حساب أداء المشروع (القيمة المكتسبة)
        self.calculate_project_earned_value(project)
        
        # التحقق من تجاوز الميزانية
        self.check_budget_overrun(project, total_planned, total_actual)
        
        return {
            'project_id': project.id,
            'project_name': project.name,
            'planned_cost': total_planned,
            'actual_cost': total_actual,
            'variance': total_actual - total_planned,
            'variance_percentage': ((total_actual - total_planned) / total_planned * 100) if total_planned > 0 else 0,
            'overhead': overhead_cost,
            'wbs_breakdown': wbs_costs
        }
    
    def calculate_project_overhead(self, project_id):
        """حساب المصاريف العامة للمشروع"""
        # يمكن تخصيص هذه الدالة حسب احتياجات المشروع
        return {'planned': 0, 'actual': 0}
    
    def calculate_project_earned_value(self, project):
        """حساب القيمة المكتسبة للمشروع (Earned Value Management)"""
        if not project.performance:
            project.performance = ProjectPerformance(project_id=project.id)
        
        # PV (Planned Value) - القيمة المخططة
        project.performance.planned_value = project.cost.total_planned_cost
        
        # EV (Earned Value) - القيمة المكتسبة (بناءً على التقدم)
        progress = project.get_progress()
        project.performance.earned_value = project.cost.total_planned_cost * (progress / 100)
        
        # AC (Actual Cost) - التكلفة الفعلية
        project.performance.actual_cost = project.cost.total_actual_cost
        
        # مؤشرات الأداء
        if project.performance.planned_value > 0:
            project.performance.spi = project.performance.earned_value / project.performance.planned_value
        if project.performance.earned_value > 0:
            project.performance.cpi = project.performance.earned_value / project.performance.actual_cost if project.performance.actual_cost > 0 else 1
        
        project.performance.csi = project.performance.spi * project.performance.cpi
        
        # تقديرات الإكمال
        if project.performance.cpi > 0:
            project.performance.eac = project.performance.planned_value / project.performance.cpi
            project.performance.etc = project.performance.eac - project.performance.actual_cost
            project.performance.vac = project.performance.planned_value - project.performance.eac
    
    def check_budget_overrun(self, project, planned_cost, actual_cost):
        """التحقق من تجاوز الميزانية وإرسال إشعارات"""
        if planned_cost == 0:
            return
        
        overrun_percentage = ((actual_cost - planned_cost) / planned_cost) * 100
        
        # مستويات التحذير
        if overrun_percentage >= 20:
            # تجاوز خطير
            self.notification_service.cost_critical_overrun(project, overrun_percentage, actual_cost - planned_cost)
        elif overrun_percentage >= 10:
            # تجاوز متوسط
            self.notification_service.cost_significant_overrun(project, overrun_percentage, actual_cost - planned_cost)
        elif overrun_percentage >= 5:
            # تجاوز بسيط
            self.notification_service.cost_minor_overrun(project, overrun_percentage, actual_cost - planned_cost)
        
        # إرسال تقرير إذا كانت التكلفة الفعلية > المخططة
        if actual_cost > planned_cost:
            self.notification_service.cost_overrun_alert(project, actual_cost - planned_cost, overrun_percentage)
    
    # ============================================
    # حساب كامل للمشروع (جميع المستويات)
    # ============================================
    
    def calculate_full_project_cost(self, project_id):
        """حساب كامل لتكاليف المشروع بجميع مستوياته"""
        # حساب تكاليف المهام
        tasks_cost = self.calculate_all_tasks_costs(project_id=project_id)
        
        # حساب تكاليف الأنشطة
        activities_cost = self.calculate_all_activities_costs(project_id=project_id)
        
        # حساب تكاليف WBS
        wbs_costs = self.calculate_all_wbs_costs(project_id)
        
        # حساب تكاليف المشروع
        project_cost = self.calculate_project_cost(project_id)
        
        return {
            'project': project_cost,
            'wbs': wbs_costs,
            'activities': activities_cost,
            'tasks': tasks_cost,
            'summary': {
                'total_planned': project_cost['planned_cost'] if project_cost else 0,
                'total_actual': project_cost['actual_cost'] if project_cost else 0,
                'total_variance': project_cost['variance'] if project_cost else 0,
                'wbs_count': len(wbs_costs),
                'activities_count': len(activities_cost),
                'tasks_count': len(tasks_cost)
            }
        }
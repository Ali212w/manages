# app/services/smart_performance_optimizer.py

"""
نظام تحسين الأداء الذكي - يقدم اقتراحات لتحسين الكفاءة
"""

from datetime import datetime, timedelta
from app.models import db
from app.models.primavera_models import Activity, ActivityResource
from app.models.task_models import Task, TaskAssignment
from app.services.notification_service import NotificationService
import numpy as np
import logging

logger = logging.getLogger(__name__)


class SmartPerformanceOptimizer:
    """نظام ذكي لتحسين الأداء"""
    
    def __init__(self):
        self.notification_service = NotificationService()
    
    def analyze_team_performance(self, project):
        """تحليل أداء الفريق"""
        from app.models.task_models import TaskAssignment
        
        team_stats = {}
        
        assignments = TaskAssignment.query.join(Task).filter(
            Task.project_id == project.id
        ).all()
        
        for assignment in assignments:
            user_id = assignment.user_id
            if user_id not in team_stats:
                team_stats[user_id] = {
                    'tasks_completed': 0,
                    'total_tasks': 0,
                    'avg_quality': 0,
                    'on_time_rate': 0,
                    'efficiency': 0,
                    'user_name': assignment.user.full_name if assignment.user else 'مستخدم'
                }
            
            team_stats[user_id]['total_tasks'] += 1
            
            if assignment.status == 'completed':
                team_stats[user_id]['tasks_completed'] += 1
                if assignment.quality_rating:
                    team_stats[user_id]['avg_quality'] += assignment.quality_rating
        
        # حساب المتوسطات
        for user_id, stats in team_stats.items():
            if stats['tasks_completed'] > 0:
                stats['avg_quality'] /= stats['tasks_completed']
            stats['efficiency'] = (stats['tasks_completed'] / stats['total_tasks']) * 100 if stats['total_tasks'] > 0 else 0
        
        return team_stats
    
    def identify_bottlenecks(self, project):
        """تحديد الاختناقات في سير العمل"""
        bottlenecks = []
        
        # 1. المهام المتأخرة
        overdue_tasks = [t for t in project.tasks if t.is_delayed]
        if overdue_tasks:
            bottlenecks.append({
                'type': 'schedule',
                'description': f'{len(overdue_tasks)} مهمة متأخرة',
                'impact': 'high',
                'affected_tasks': [t.task_name for t in overdue_tasks]
            })
        
        # 2. الموارد الناقصة
        missing_resources = self._check_resource_shortage(project.id)
        if missing_resources:
            bottlenecks.append({
                'type': 'resource',
                'description': f'نقص في الموارد: {", ".join(missing_resources[:3])}',
                'impact': 'medium',
                'resources': missing_resources
            })
        
        # 3. الاعتماديات الحرجة
        critical_activities = [a for a in project.activities if a.is_critical]
        if len(critical_activities) > 5:
            bottlenecks.append({
                'type': 'dependency',
                'description': f'{len(critical_activities)} نشاط على المسار الحرج',
                'impact': 'high',
                'activities': [a.activity_name for a in critical_activities]
            })
        
        return bottlenecks
    
    def suggest_optimizations(self, project, team_stats, bottlenecks):
        """اقتراح تحسينات بناءً على التحليل"""
        suggestions = []
        
        # 1. تحسين توزيع المهام
        low_performers = [
            user_id for user_id, stats in team_stats.items() 
            if stats['efficiency'] < 50
        ]
        
        if low_performers:
            suggestions.append({
                'type': 'training',
                'title': 'تدريب الموظفين',
                'description': f'{len(low_performers)} موظف يحتاجون تدريباً إضافياً',
                'users': low_performers,
                'priority': 'high'
            })
        
        # 2. إعادة توزيع الموارد
        resource_bottlenecks = [b for b in bottlenecks if b['type'] == 'resource']
        if resource_bottlenecks:
            suggestions.append({
                'type': 'resource_reallocation',
                'title': 'إعادة توزيع الموارد',
                'description': f'يوصى بإعادة توزيع {len(resource_bottlenecks)} مورد',
                'priority': 'medium'
            })
        
        # 3. تحسين الجدولة
        if any(b['type'] == 'dependency' for b in bottlenecks):
            suggestions.append({
                'type': 'rescheduling',
                'title': 'تحسين الجدولة',
                'description': 'يوصى بإعادة جدولة الأنشطة لتقليل المسار الحرج',
                'priority': 'high'
            })
        
        return suggestions
    
    def optimize_schedule(self, project):
        """تحسين الجدول الزمني"""
        # حساب التواريخ المثلى
        activities = project.activities.order_by(Activity.early_start).all()
        
        optimized_schedule = []
        current_date = datetime.now()
        
        for activity in activities:
            if activity.status == 'not_started':
                # حساب التاريخ الأمثل للبدء
                recommended_start = max(activity.early_start, current_date)
                
                if recommended_start > activity.planned_start:
                    # تأخير مقترح
                    optimized_schedule.append({
                        'activity': activity,
                        'current_start': activity.planned_start,
                        'recommended_start': recommended_start,
                        'reason': 'تجنب ازدحام الموارد'
                    })
        
        return optimized_schedule
    
    def _check_resource_shortage(self, project_id):
        """التحقق من نقص الموارد"""
        from app.models import ActivityResource, Resource
        
        activities = Activity.query.filter_by(project_id=project_id).all()
        missing = []
        
        for activity in activities:
            resources = ActivityResource.query.filter_by(activity_id=activity.id).all()
            for res in resources:
                resource = Resource.query.get(res.resource_id)
                if resource and resource.available_quantity < res.planned_quantity:
                    missing.append(resource.name)
        
        return list(set(missing))
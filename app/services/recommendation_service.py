# app/services/recommendation_service.py

"""
خدمة التوصيات الذكية - تقدم اقتراحات لتحسين الأداء
"""

from app.models import db
from app.models.primavera_models import Activity, ActivityStep
from app.models.ai_models import AIRecommendation
from datetime import datetime
import json

class RecommendationService:
    """خدمة التوصيات الذكية"""
    
    def recommend_project_start(self, project):
        """توصية ببدء المشروع"""
        recommendation = AIRecommendation(
            project_id=project.id,
            recommendation_type='project_start',
            title=f'جاهزية مشروع {project.name} للبدء',
            title_ar=f'جاهزية مشروع {project.name} للبدء',
            description=f'جميع المتطلبات جاهزة، يمكن بدء المشروع وفقاً للجدول المخطط.',
            current_state={
                'planned_start': project.dates.planned_start.isoformat() if project.dates.planned_start else None,
                'status': project.status,
                'resources_ready': True
            },
            recommended_action='بدء المشروع رسمياً',
            expected_benefit='تجنب التأخير في الجدول الزمني',
            confidence_score=0.95,
            urgency_level='high',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_activity_start(self, activity):
        """توصية ببدء نشاط"""
        recommendation = AIRecommendation(
            project_id=activity.project_id,
            recommendation_type='activity_start',
            title=f'بدء نشاط {activity.activity_name}',
            title_ar=f'بدء نشاط {activity.activity_name}',
            description=f'حان وقت بدء النشاط حسب الجدول الزمني. جميع الموارد متوفرة.',
            current_state={
                'planned_start': activity.planned_start.isoformat() if activity.planned_start else None,
                'status': activity.status,
                'resources_available': True
            },
            recommended_action='بدء تنفيذ النشاط',
            expected_benefit='المحافظة على الجدول الزمني',
            confidence_score=0.9,
            urgency_level='high',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_update_activity_progress(self, activity, steps_progress):
        """توصية بتحديث تقدم النشاط"""
        recommendation = AIRecommendation(
            project_id=activity.project_id,
            recommendation_type='progress_update',
            title=f'تحديث تقدم النشاط {activity.activity_name}',
            title_ar=f'تحديث تقدم النشاط {activity.activity_name}',
            description=f'اكتملت {steps_progress:.1f}% من خطوات النشاط، ولكن نسبة الإنجاز المسجلة {activity.progress_percentage:.1f}%. يرجى تحديث النسبة.',
            current_state={
                'current_progress': activity.progress_percentage,
                'steps_completion': steps_progress,
                'difference': steps_progress - activity.progress_percentage
            },
            recommended_action=f'تحديث نسبة الإنجاز إلى {steps_progress:.1f}%',
            expected_benefit='متابعة دقيقة لتقدم المشروع',
            confidence_score=0.85,
            urgency_level='medium',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_task_recovery(self, task):
        """توصية لمعالجة مهمة متأخرة"""
        recommendation = AIRecommendation(
            project_id=task.project_id,
            recommendation_type='task_recovery',
            title=f'معالجة تأخر المهمة {task.task_name}',
            title_ar=f'معالجة تأخر المهمة {task.task_name}',
            description=f'المهمة متأخرة {task.delay_days} يوماً. يوصى بزيادة الموارد أو إعادة جدولة المهام التابعة.',
            current_state={
                'delay_days': task.delay_days,
                'current_progress': task.progress_percentage,
                'planned_finish': task.planning.planned_finish.isoformat() if task.planning.planned_finish else None
            },
            recommended_action='تخصيص موارد إضافية للمهمة',
            expected_benefit=f'تقليل التأخير بمقدار {task.delay_days} يوماً',
            confidence_score=0.75,
            urgency_level='high',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_reorder_resource(self, resource):
        """توصية بإعادة طلب مورد"""
        recommendation = AIRecommendation(
            project_id=None,
            recommendation_type='resource_reorder',
            title=f'إعادة طلب {resource.name}',
            title_ar=f'إعادة طلب {resource.name}',
            description=f'المخزون المتبقي {resource.available_quantity} {resource.unit} أقل من الحد الأدنى {resource.minimum_quantity} {resource.unit}. يوصى بإعادة الطلب فوراً.',
            current_state={
                'available_quantity': resource.available_quantity,
                'minimum_quantity': resource.minimum_quantity,
                'reorder_quantity': resource.reorder_quantity
            },
            recommended_action=f'طلب {resource.reorder_quantity} {resource.unit} من {resource.name}',
            expected_benefit='تجنب توقف العمل بسبب نقص المواد',
            confidence_score=0.95,
            urgency_level='critical',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_cost_reduction(self, project):
        """توصية بتقليل التكاليف"""
        recommendation = AIRecommendation(
            project_id=project.id,
            recommendation_type='cost_reduction',
            title=f'تقليل تكاليف مشروع {project.name}',
            title_ar=f'تقليل تكاليف مشروع {project.name}',
            description=f'المشروع يتجاوز الميزانية بنسبة {((project.cost.total_actual_cost - project.budget.current_budget) / project.budget.current_budget * 100):.1f}%. يوصى بمراجعة المصروفات غير الضرورية.',
            current_state={
                'budget': project.budget.current_budget,
                'actual_cost': project.cost.total_actual_cost,
                'variance': project.cost.total_actual_cost - project.budget.current_budget
            },
            recommended_action='مراجعة المصروفات وتحديد الأولويات',
            expected_benefit='خفض التكاليف بنسبة 10-15%',
            confidence_score=0.7,
            urgency_level='high',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()

    # خدمه التوصيات الذكية 
    
    def recommend_project_recovery(self, project):
        """توصية لاسترداد المشروع المتأخر"""
        recommendation = AIRecommendation(
            project_id=project.id,
            recommendation_type='project_recovery',
            title=f'خطة استرداد للمشروع {project.name}',
            title_ar=f'خطة استرداد للمشروع {project.name}',
            description=f'المشروع متأخر. يوصى بإعادة توزيع الموارد على المهام الحرجة وزيادة عدد ساعات العمل.',
            current_state={
                'delay_days': (datetime.now().date() - project.dates.planned_finish.date()).days if project.dates and project.dates.planned_finish else 0,
                'current_progress': project.get_progress(),
                'critical_tasks': [t.task_name for t in project.tasks if t.is_critical]
            },
            recommended_action='تخصيص موارد إضافية للمهام الحرجة وزيادة ساعات العمل',
            expected_benefit='تقليل التأخير بنسبة 50% خلال أسبوعين',
            confidence_score=0.75,
            urgency_level='high',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_activity_recovery(self, activity):
        """توصية لاسترداد النشاط المتأخر"""
        recommendation = AIRecommendation(
            project_id=activity.project_id,
            recommendation_type='activity_recovery',
            title=f'تحسين أداء النشاط {activity.activity_name}',
            title_ar=f'تحسين أداء النشاط {activity.activity_name}',
            description=f'النشاط متأخر. يوصى بزيادة الموارد أو تبسيط الإجراءات.',
            current_state={
                'delay_days': (datetime.now() - activity.planned_finish).days if activity.planned_finish else 0,
                'current_progress': activity.progress_percentage,
                'assigned_resources': [r.resource.name for r in activity.assigned_resources]
            },
            recommended_action='زيادة عدد العاملين في النشاط',
            expected_benefit='تعويض التأخير خلال أسبوع',
            confidence_score=0.7,
            urgency_level='high',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_urgent_cost_reduction(self, project):
        """توصية عاجلة لتقليل التكاليف"""
        recommendation = AIRecommendation(
            project_id=project.id,
            recommendation_type='urgent_cost_reduction',
            title=f'خفض التكاليف العاجل - {project.name}',
            title_ar=f'خفض التكاليف العاجل - {project.name}',
            description=f'المشروع يعاني من تجاوز خطير في الميزانية. يوصى بمراجعة جميع المصروفات وإيقاف الأنشطة غير الضرورية.',
            current_state={
                'budget_overrun': project.cost.total_actual_cost - project.budget.current_budget,
                'overrun_percentage': ((project.cost.total_actual_cost - project.budget.current_budget) / project.budget.current_budget * 100),
                'high_cost_activities': [a.activity_name for a in project.activities if a.actual_cost > a.planned_cost * 1.2]
            },
            recommended_action='مراجعة عقود الموردين وإعادة التفاوض على الأسعار',
            expected_benefit='خفض التكاليف بنسبة 15-20%',
            confidence_score=0.8,
            urgency_level='critical',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
    
    def recommend_equipment_maintenance(self, equipment):
        """توصية بصيانة المعدات"""
        recommendation = AIRecommendation(
            project_id=None,
            recommendation_type='equipment_maintenance',
            title=f'صيانة المعدة {equipment.name}',
            title_ar=f'صيانة المعدة {equipment.name}',
            description=f'المعدة {equipment.name} تحتاج إلى صيانة دورية. يوصى بجدولة الصيانة فوراً.',
            current_state={
                'last_maintenance': equipment.last_maintenance,
                'next_maintenance': equipment.next_maintenance,
                'maintenance_cycle': equipment.maintenance_cycle,
                'current_usage': equipment.get_usage_hours() if hasattr(equipment, 'get_usage_hours') else 0
            },
            recommended_action='جدولة الصيانة خلال الأسبوع الحالي',
            expected_benefit='زيادة عمر المعدة وتجنب الأعطال المفاجئة',
            confidence_score=0.9,
            urgency_level='high',
            generated_by='Smart Monitoring System'
        )
        db.session.add(recommendation)
        db.session.commit()
# app/services/smart_risk_manager.py

"""
نظام إدارة المخاطر الذكي - يكتشف ويتنبأ بالمخاطر تلقائياً
"""

from datetime import datetime, timedelta
from app.models import db
from app.models.primavera_models import Activity, ActivityRisk
from app.models import Risk
from app.services.notification_service import NotificationService
from app.services.recommendation_service import RecommendationService
import numpy as np
from sklearn.ensemble import RandomForestClassifier
import joblib
import logging

logger = logging.getLogger(__name__)

# app/services/smart_risk_manager.py

class SmartRiskManager:
    """نظام ذكي لإدارة المخاطر"""
    
    def __init__(self):
        self.notification_service = NotificationService()
        self.recommendation_service = RecommendationService()
        self.risk_model = None
    
    def detect_project_risks(self, project):
        """اكتشاف مخاطر المشروع تلقائياً"""
        risks_found = []
        
        # 1. مخاطر الميزانية
        if project.cost and project.budget:
            budget_usage = (project.cost.total_actual_cost / project.budget.current_budget) * 100 if project.budget.current_budget > 0 else 0
            
            if budget_usage > 80:
                risk_level = 'high' if budget_usage > 90 else 'medium'
                risk = {
                    'type': 'budget',
                    'title': 'مخاطر الميزانية',
                    'description': f'تم استخدام {budget_usage:.1f}% من الميزانية المخططة للمشروع',
                    'level': risk_level,
                    'probability': min(budget_usage / 100, 0.95)
                }
                risks_found.append(risk)
                self._save_risk(project, risk)
        
        # 2. مخاطر الجدول الزمني
        if project.dates and project.dates.planned_finish:
            if datetime.now().date() > project.dates.planned_finish.date():
                delay_days = (datetime.now().date() - project.dates.planned_finish.date()).days
                risk = {
                    'type': 'schedule',
                    'title': 'مخاطر التأخير',
                    'description': f'المشروع متأخر {delay_days} يوماً عن الجدول المخطط',
                    'level': 'high' if delay_days > 15 else 'medium',
                    'probability': min(delay_days / 30, 0.9)
                }
                risks_found.append(risk)
                self._save_risk(project, risk)
        
        # 3. مخاطر الموارد
        resource_risk = self._assess_resource_risks(project.id)
        if resource_risk:
            risks_found.append(resource_risk)
            self._save_risk(project, resource_risk)
        
        # 4. مخاطر الجودة
        quality_risk = self._assess_quality_risks(project.id)
        if quality_risk:
            risks_found.append(quality_risk)
            self._save_risk(project, quality_risk)
        
        return risks_found
    
    def predict_future_risks(self, project):
        """التنبؤ بالمخاطر المستقبلية"""
        future_risks = []
        
        # تحليل اتجاهات التقدم
        if project.statistics and project.statistics.progress_percentage:
            weekly_progress = self._get_weekly_progress(project)
            
            if len(weekly_progress) >= 4:
                avg_progress = sum(weekly_progress) / len(weekly_progress)
                if avg_progress < 5:  # تقدم أقل من 5% أسبوعياً
                    risk = {
                        'title': 'تباطؤ خطير في التقدم',
                        'description': 'معدل التقدم الأسبوعي أقل من المعدل المطلوب، خطر عدم الالتزام بالجدول',
                        'probability': 0.7,
                        'recommended_action': 'زيادة الموارد للمهام الحرجة'
                    }
                    future_risks.append(risk)
        
        # تحليل اتجاهات التكاليف
        if project.cost and project.budget:
            cost_trend = self._get_cost_trend(project)
            if cost_trend > 0.1:  # زيادة التكاليف بأكثر من 10%
                risk = {
                    'title': 'ارتفاع غير متوقع في التكاليف',
                    'description': f'التكاليف ترتفع بمعدل {cost_trend:.1f}% أسبوعياً',
                    'probability': 0.65,
                    'recommended_action': 'مراجعة عقود الموردين وإعادة التفاوض'
                }
                future_risks.append(risk)
        
        return future_risks
    
    def _assess_resource_risks(self, project_id):
        """تقييم مخاطر الموارد"""
        from app.models.primavera_models import ActivityResource, Resource
        
        activities = Activity.query.filter_by(project_id=project_id).all()
        missing_resources = []
        
        for activity in activities:
            required = ActivityResource.query.filter_by(activity_id=activity.id).all()
            for req in required:
                resource = Resource.query.get(req.resource_id)
                if resource and resource.available_quantity < req.planned_quantity:
                    missing_resources.append({
                        'resource': resource.name,
                        'activity': activity.activity_name,
                        'shortage': req.planned_quantity - resource.available_quantity
                    })
        
        if missing_resources:
            return {
                'type': 'resource',
                'title': 'مخاطر نقص الموارد',
                'description': f'يوجد نقص في {len(missing_resources)} مورد',
                'level': 'high' if len(missing_resources) > 5 else 'medium',
                'probability': min(len(missing_resources) / 20, 0.8),
                'details': missing_resources
            }
        return None
    
    def _assess_quality_risks(self, project_id):
        """تقييم مخاطر الجودة"""
        from app.models.task_models import Task
        
        tasks = Task.query.filter_by(project_id=project_id).all()
        if not tasks:
            return None
        
        poor_quality_tasks = [t for t in tasks if t.completion_quality in ['fair', 'poor']]
        
        if poor_quality_tasks:
            return {
                'type': 'quality',
                'title': 'مخاطر الجودة',
                'description': f'{len(poor_quality_tasks)} مهمة ذات جودة منخفضة تحتاج إعادة عمل',
                'level': 'high' if len(poor_quality_tasks) > 10 else 'medium',
                'probability': min(len(poor_quality_tasks) / len(tasks), 0.7)
            }
        return None
    
    def _save_risk(self, project, risk_data):
        """حفظ الخطر المكتشف"""
        from app.models.project_models import Risk
        
        risk = Risk(
            project_id=project.id,
            risk_code=f"R-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            title=risk_data['title'],
            description=risk_data['description'],
            category=risk_data['type'],
            probability=risk_data['probability'] * 100,
            impact=risk_data['level'],
            severity=risk_data['probability'] * (4 if risk_data['level'] == 'high' else 2),
            risk_level=risk_data['level'],
            status='identified',
            identified_date=datetime.now().date()
        )
        
        db.session.add(risk)
        db.session.commit()
        
        # إرسال إشعار
        self.notification_service.risk_detected(risk)
    

    def _get_weekly_progress(self, project):
        """الحصول على تقدم المشروع أسبوعياً من السجل التاريخي"""
        try:
            from app.models.project_models import ProjectProgressLog
            from datetime import datetime, timedelta
            
            weeks_data = []
            today = datetime.now().date()
            
            # جلب آخر 4 أسابيع من السجل
            for i in range(4, 0, -1):
                week_start = today - timedelta(days=i*7)
                week_end = week_start + timedelta(days=6)
                
                # البحث عن سجل في هذا الأسبوع
                logs = ProjectProgressLog.query.filter(
                    ProjectProgressLog.project_id == project.id,
                    ProjectProgressLog.record_date >= week_start,
                    ProjectProgressLog.record_date <= week_end
                ).order_by(ProjectProgressLog.record_date.desc()).all()
                
                if logs:
                    # أخذ متوسط التقدم للأسبوع
                    avg_progress = sum(log.progress_percentage for log in logs) / len(logs)
                    weeks_data.append(avg_progress)
                else:
                    # إذا لم يوجد سجل، استخدم التقدم الحالي مع تقدير
                    weekly_progress = self._estimate_weekly_progress(project, i)
                    weeks_data.append(weekly_progress)
            
            # إذا لم تكن هناك بيانات كافية، استخدم التقدم الحالي
            if not weeks_data or len(weeks_data) < 4:
                current_progress = project.get_progress()
                weeks_data = self._generate_estimated_progress(current_progress)
            
            return weeks_data
            
        except Exception as e:
            logger.error(f"خطأ في جلب التقدم الأسبوعي للمشروع {project.id}: {str(e)}")
            return self._generate_estimated_progress(project.get_progress())

    def _estimate_weekly_progress(self, project, weeks_ago):
        """تقدير التقدم الأسبوعي بناءً على البيانات المتاحة"""
        try:
            current_progress = project.get_progress()
            
            # الحصول على تاريخ بدء المشروع
            start_date = project.dates.actual_start.date() if project.dates and project.dates.actual_start else None
            
            if start_date:
                total_days = (datetime.now().date() - start_date).days
                if total_days > 0:
                    # تقدير التقدم الأسبوعي بناءً على المعدل العام
                    weekly_rate = current_progress / (total_days / 7)
                    weeks_ago_progress = max(0, current_progress - (weekly_rate * weeks_ago))
                    return min(100, weeks_ago_progress)
            
            # إذا لم تكن هناك بيانات كافية، استخدم تقدير بسيط
            return max(0, current_progress - (weeks_ago * 5))
            
        except Exception as e:
            logger.error(f"خطأ في تقدير التقدم الأسبوعي: {str(e)}")
            return 0


    def _generate_estimated_progress(self, current_progress):
        """إنشاء بيانات تقديرية للتقدم الأسبوعي"""
        # إنشاء توزيع تقديري للتقدم على 4 أسابيع
        if current_progress >= 80:
            # مراحل متقدمة - تقدم أبطأ
            return [current_progress - 15, current_progress - 10, current_progress - 5, current_progress]
        elif current_progress >= 50:
            # مراحل متوسطة - تقدم متسارع
            return [current_progress - 12, current_progress - 8, current_progress - 4, current_progress]
        elif current_progress >= 20:
            # مراحل مبكرة - تقدم جيد
            return [current_progress - 10, current_progress - 6, current_progress - 3, current_progress]
        else:
            # مراحل أولية - تقدم بطيء
            return [max(0, current_progress - 5), max(0, current_progress - 3), max(0, current_progress - 1), current_progress]
    
    def _get_cost_trend(self, project):
        """الحصول على اتجاه التكاليف"""
        if project.cost and project.budget:
            return (project.cost.total_actual_cost / project.budget.current_budget) - 1
        return 0


# class SmartRiskManager:
#     """نظام ذكي لإدارة المخاطر"""
    
#     def __init__(self):
#         self.notification_service = NotificationService()
#         self.recommendation_service = RecommendationService()
#         self.risk_model = None
#         self.load_risk_model()
    
#     def load_risk_model(self):
#         """تحميل نموذج التنبؤ بالمخاطر"""
#         try:
#             self.risk_model = joblib.load('models/risk_predictor.pkl')
#         except:
#             logger.warning("نموذج التنبؤ بالمخاطر غير موجود، سيتم إنشاؤه لاحقاً")
    
#     def detect_project_risks(self, project):
#         """اكتشاف مخاطر المشروع تلقائياً"""
#         risks_found = []
        
#         # 1. مخاطر الميزانية
#         if project.cost and project.budget:
#             budget_usage = (project.cost.total_actual_cost / project.budget.current_budget) * 100
#             if budget_usage > 80:
#                 risks_found.append({
#                     'type': 'budget',
#                     'title': 'مخاطر الميزانية',
#                     'description': f'تم استخدام {budget_usage:.1f}% من الميزانية',
#                     'level': 'high' if budget_usage > 90 else 'medium',
#                     'probability': budget_usage / 100
#                 })
        
#         # 2. مخاطر الجدول الزمني
#         if project.is_overdue:
#             delay_days = (datetime.now().date() - project.dates.planned_finish.date()).days
#             risks_found.append({
#                 'type': 'schedule',
#                 'title': 'مخاطر التأخير',
#                 'description': f'المشروع متأخر {delay_days} يوماً',
#                 'level': 'high' if delay_days > 15 else 'medium',
#                 'probability': min(delay_days / 30, 1.0)
#             })
        
#         # 3. مخاطر الموارد
#         resource_risk = self.assess_resource_risks(project.id)
#         if resource_risk['has_risk']:
#             risks_found.append(resource_risk)
        
#         # 4. مخاطر الجودة
#         quality_risk = self.assess_quality_risks(project.id)
#         if quality_risk['has_risk']:
#             risks_found.append(quality_risk)
        
#         # حفظ المخاطر المكتشفة
#         for risk_data in risks_found:
#             self.save_detected_risk(project, risk_data)
        
#         return risks_found
    
#     def assess_resource_risks(self, project_id):
#         """تقييم مخاطر الموارد"""
#         from app.models.primavera_models import ActivityResource, Resource
        
#         # التحقق من الموارد الناقصة
#         activities = Activity.query.filter_by(project_id=project_id).all()
#         missing_resources = []
        
#         for activity in activities:
#             required = ActivityResource.query.filter_by(activity_id=activity.id).all()
#             for req in required:
#                 resource = Resource.query.get(req.resource_id)
#                 if resource and resource.available_quantity < req.planned_quantity:
#                     missing_resources.append({
#                         'resource': resource.name,
#                         'activity': activity.activity_name,
#                         'shortage': req.planned_quantity - resource.available_quantity
#                     })
        
#         if missing_resources:
#             return {
#                 'type': 'resource',
#                 'title': 'مخاطر نقص الموارد',
#                 'description': f'يوجد نقص في {len(missing_resources)} مورد',
#                 'level': 'high' if len(missing_resources) > 5 else 'medium',
#                 'probability': min(len(missing_resources) / 20, 1.0),
#                 'details': missing_resources
#             }
        
#         return {'has_risk': False}
    
#     def assess_quality_risks(self, project_id):
#         """تقييم مخاطر الجودة"""
#         tasks = Task.query.filter_by(project_id=project_id).all()
        
#         poor_quality_tasks = [t for t in tasks if t.completion_quality in ['fair', 'poor']]
        
#         if poor_quality_tasks:
#             return {
#                 'type': 'quality',
#                 'title': 'مخاطر الجودة',
#                 'description': f'{len(poor_quality_tasks)} مهمة ذات جودة منخفضة',
#                 'level': 'high' if len(poor_quality_tasks) > 10 else 'medium',
#                 'probability': min(len(poor_quality_tasks) / len(tasks), 1.0) if tasks else 0,
#                 'details': poor_quality_tasks
#             }
        
#         return {'has_risk': False}
    
#     def predict_future_risks(self, project):
#         """التنبؤ بالمخاطر المستقبلية باستخدام الذكاء الاصطناعي"""
#         if not self.risk_model:
#             return []
        
#         # جمع البيانات التاريخية
#         features = self.extract_risk_features(project)
        
#         # التنبؤ
#         predictions = self.risk_model.predict_proba([features])[0]
        
#         future_risks = []
        
#         if predictions[1] > 0.7:  # احتمال خطر مرتفع
#             future_risks.append({
#                 'title': 'خطر متوقع',
#                 'description': 'من المتوقع حدوث تأخير في الجدول الزمني خلال الأسبوعين القادمين',
#                 'probability': predictions[1],
#                 'recommended_action': 'زيادة الموارد للمهام الحرجة'
#             })
        
#         return future_risks
    
#     def extract_risk_features(self, project):
#         """استخراج ميزات المشروع للتنبؤ بالمخاطر"""
#         return [
#             project.progress_percentage if project.progress else 0,
#             project.total_float if project.progress else 0,
#             len([t for t in project.tasks if t.is_delayed]),
#             project.cost.total_actual_cost / project.budget.current_budget if project.cost and project.budget else 0,
#             len(project.activities.all())
#         ]
    
#     def save_detected_risk(self, project, risk_data):
#         """حفظ الخطر المكتشف"""
#         risk = Risk(
#             project_id=project.id,
#             risk_code=f"R-{datetime.now().strftime('%Y%m%d%H%M%S')}",
#             title=risk_data['title'],
#             description=risk_data['description'],
#             category=risk_data['type'],
#             probability=risk_data['probability'],
#             impact=risk_data['level'],
#             severity=risk_data['probability'] * (4 if risk_data['level'] == 'high' else 2),
#             risk_level=risk_data['level'],
#             status='identified',
#             identified_date=datetime.now().date()
#         )
        
#         db.session.add(risk)
#         db.session.commit()
        
#         # إرسال إشعار
#         self.notification_service.risk_detected(risk)
# app/services/smart_quality_manager.py

"""
نظام إدارة الجودة الذكي - يراقب جودة المخرجات تلقائياً
"""

from datetime import datetime
from app.models import db
from app.models.project_models import QualityCheck
from app.models.task_models import Task
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class SmartQualityManager:
    """نظام ذكي لإدارة الجودة"""
    
    def __init__(self):
        self.notification_service = NotificationService()
        self.quality_thresholds = {
            'excellent': 90,
            'good': 75,
            'fair': 60,
            'poor': 0
        }
    
    def monitor_quality_metrics(self, project):
        """مراقبة مؤشرات الجودة"""
        metrics = {
            'completion_rate': self.calculate_completion_rate(project),
            'defect_rate': self.calculate_defect_rate(project),
            'rework_rate': self.calculate_rework_rate(project),
            'customer_satisfaction': self.get_customer_satisfaction(project)
        }
        
        # التحقق من جودة المخرجات
        if metrics['defect_rate'] > 10:  # أكثر من 10% عيوب
            self.notification_service.quality_alert(project, metrics)
            self.recommend_quality_improvement(project, metrics)
        
        return metrics
    
    def calculate_completion_rate(self, project):
        """حساب نسبة الإكمال بجودة جيدة"""
        tasks = project.tasks.all()
        if not tasks:
            return 0
        
        good_tasks = [t for t in tasks if t.completion_quality in ['excellent', 'good']]
        return (len(good_tasks) / len(tasks)) * 100
    
    def calculate_defect_rate(self, project):
        """حساب نسبة العيوب"""
        quality_checks = QualityCheck.query.filter_by(project_id=project.id).all()
        if not quality_checks:
            return 0
        
        failed_checks = [qc for qc in quality_checks if qc.status == 'failed']
        return (len(failed_checks) / len(quality_checks)) * 100
    
    def calculate_rework_rate(self, project):
        """حساب نسبة إعادة العمل"""
        tasks = project.tasks.all()
        if not tasks:
            return 0
        
        rework_tasks = [t for t in tasks if t.status == 'rework']
        return (len(rework_tasks) / len(tasks)) * 100
    
    def get_customer_satisfaction(self, project):
        """الحصول على رضا العميل"""
        # يمكن جلب من نموذج التقييمات
        return 85  # نسبة افتراضية
    
    def recommend_quality_improvement(self, project, metrics):
        """تقديم توصيات لتحسين الجودة"""
        recommendations = []
        
        if metrics['defect_rate'] > 10:
            recommendations.append({
                'title': 'تحسين جودة المخرجات',
                'action': 'عقد ورشة عمل حول معايير الجودة',
                'priority': 'high'
            })
        
        if metrics['rework_rate'] > 15:
            recommendations.append({
                'title': 'تقليل إعادة العمل',
                'action': 'مراجعة الإجراءات والتدريب على المهارات',
                'priority': 'high'
            })
        
        if metrics['completion_rate'] < 70:
            recommendations.append({
                'title': 'تحسين نسبة الإكمال الجيد',
                'action': 'تخصيص مشرفين جودة للمهام الحرجة',
                'priority': 'medium'
            })
        
        # حفظ التوصيات
        self.save_quality_recommendations(project, recommendations)
        
        return recommendations
    
    def save_quality_recommendations(self, project, recommendations):
        """حفظ توصيات الجودة"""
        for rec in recommendations:
            self.notification_service.quality_recommendation(project, rec)
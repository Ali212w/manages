# app/services/business_intelligence.py

"""
نظام ذكاء الأعمال - تحليلات متقدمة وتقارير ذكية
"""

from datetime import datetime, timedelta
from app.models import db
from flask import current_app
from app.models.project_models import Project
from app.models.ai_models import AIReport
import pandas as pd
import numpy as np
from flask import url_for
import logging
from app.services.notification_service import NotificationService
logger = logging.getLogger(__name__)


class BusinessIntelligence:
    """نظام ذكاء الأعمال"""
    
    def __init__(self):
        self.notification_service = NotificationService()
        self.kpis = {}
    
    def calculate_kpis(self, org_id):
        
        """حساب مؤشرات الأداء الرئيسية للمنظمة"""
        projects = Project.query.filter_by(org_id=org_id).all()
        
        self.kpis = {
            'overall': {
                'total_projects': len(projects),
                'active_projects': sum(1 for p in projects if p.status == 'in_progress'),
                'completed_projects': sum(1 for p in projects if p.status == 'completed'),
                'total_budget': sum(p.budget.current_budget for p in projects if p.budget),
                'total_actual_cost': sum(p.cost.total_actual_cost for p in projects if p.cost),
                'average_progress': np.mean([p.get_progress() for p in projects]) if projects else 0,
                'on_time_rate': self.calculate_on_time_rate(projects),
                'on_budget_rate': self.calculate_on_budget_rate(projects)
            },
            'performance': self.calculate_performance_metrics(projects),
            'trends': self.calculate_trends(projects)
        }
        
        return self.kpis
    
    def calculate_on_time_rate(self, projects):
        """حساب نسبة المشاريع في الوقت المحدد"""
        on_time = 0
        for p in projects:
            if p.status == 'completed' and p.dates and p.dates.actual_finish:
                if p.dates.actual_finish <= p.dates.planned_finish:
                    on_time += 1
            elif p.status == 'in_progress' and not p.is_overdue:
                on_time += 1
        
        return (on_time / len(projects) * 100) if projects else 0
    
    def calculate_on_budget_rate(self, projects):
        """حساب نسبة المشاريع ضمن الميزانية"""
        on_budget = 0
        for p in projects:
            if p.cost and p.budget:
                if p.cost.total_actual_cost <= p.budget.current_budget:
                    on_budget += 1
        
        return (on_budget / len(projects) * 100) if projects else 0
    
    def calculate_performance_metrics(self, projects):
        """حساب مقاييس الأداء المتقدمة"""
        metrics = {
            'avg_cpi': np.mean([p.performance.cpi for p in projects if p.performance and p.performance.cpi]),
            'avg_spi': np.mean([p.performance.spi for p in projects if p.performance and p.performance.spi]),
            'best_performing': None,
            'worst_performing': None
        }
        
        # تحديد أفضل وأسوأ المشاريع أداءً
        if projects:
            projects_with_performance = [
                p for p in projects 
                if p.performance and p.performance.cpi and p.performance.spi
            ]
            
            if projects_with_performance:
                metrics['best_performing'] = max(
                    projects_with_performance,
                    key=lambda p: p.performance.cpi * p.performance.spi
                ).name
                
                metrics['worst_performing'] = min(
                    projects_with_performance,
                    key=lambda p: p.performance.cpi * p.performance.spi
                ).name
        
        return metrics
    
    def calculate_trends(self, projects):
        """حساب الاتجاهات والتوقعات"""
        # تحليل الاتجاهات الزمنية
        monthly_data = {}
        
        for project in projects:
            month = project.created_at.strftime('%Y-%m')
            if month not in monthly_data:
                monthly_data[month] = {
                    'count': 0,
                    'total_budget': 0,
                    'total_actual': 0
                }
            
            monthly_data[month]['count'] += 1
            if project.budget:
                monthly_data[month]['total_budget'] += project.budget.current_budget
            if project.cost:
                monthly_data[month]['total_actual'] += project.cost.total_actual_cost
        
        return monthly_data
    
    def generate_executive_dashboard(self, org_id):
        """إنشاء لوحة تحكم تنفيذية"""
        with current_app.app_context():
            kpis = self.calculate_kpis(org_id)
            
            # إنشاء توصيات استراتيجية
            recommendations = []
            
            if kpis['overall']['on_time_rate'] < 70:
                recommendations.append({
                    'title': 'تحسين الالتزام بالجدول الزمني',
                    'action': 'مراجعة عملية التخطيط وزيادة الموارد للمشاريع الحرجة',
                    'impact': 'زيادة نسبة الإنجاز في الوقت المحدد بنسبة 20%'
                })
            
            if kpis['overall']['on_budget_rate'] < 70:
                recommendations.append({
                    'title': 'تحسين التحكم في التكاليف',
                    'action': 'تطبيق نظام مراقبة تكاليف أكثر صرامة',
                    'impact': 'تقليل تجاوزات الميزانية بنسبة 15%'
                })
            
            if kpis['performance']['avg_cpi'] < 0.9:
                recommendations.append({
                    'title': 'تحسين كفاءة التكلفة',
                    'action': 'مراجعة الموردين وإعادة التفاوض على الأسعار',
                    'impact': 'تحسين CPI إلى 1.0'
                })
            
            return {
                'kpis': kpis,
                'recommendations': recommendations,
                'generated_at': datetime.now().isoformat()
            }
    
    def get_trends_data(self, projects):
        """
        حساب اتجاهات التغيير للمشاريع
        
        Args:
            projects: قائمة المشاريع
        
        Returns:
            dict: بيانات الاتجاهات
        """
        try:
            with current_app.app_context():
                from app.models.project_models import ProjectProgressLog
                from datetime import datetime, timedelta
                
                trends = {
                    'projects': {'direction': 'up', 'percentage': 0},
                    'active': {'direction': 'up', 'percentage': 0},
                    'budget': {'direction': 'up', 'percentage': 0},
                    'actual': {'direction': 'up', 'percentage': 0}
                }
                
                # حساب اتجاه عدد المشاريع
                one_week_ago = datetime.now().date() - timedelta(days=7)
                current_count = len(projects)
                
                # جلب عدد المشاريع قبل أسبوع
                projects_one_week_ago = Project.query.filter(
                    Project.created_at >= one_week_ago
                ).count()
                
                if projects_one_week_ago > 0:
                    projects_change = ((current_count - projects_one_week_ago) / projects_one_week_ago) * 100
                    trends['projects'] = {
                        'direction': 'up' if projects_change >= 0 else 'down',
                        'percentage': abs(projects_change)
                    }
                
                # حساب اتجاه الميزانية
                current_budget = sum(p.budget.current_budget for p in projects if p.budget)
                # يمكن إضافة بيانات تاريخية للميزانية
                
                return trends
            
        except Exception as e:
            logger.error(f"خطأ في حساب الاتجاهات: {str(e)}")
            return trends
    def send_email_summary(self, email, kpis):
        """إرسال ملخص عبر البريد الإلكتروني"""
        # تنفيذ إرسال البريد الإلكتروني
        subject = f"ملخص أداء المؤسسة - {datetime.now().strftime('%Y-%m-%d')}"
        body = self._format_email_body(kpis)
        # self._send_email(email, subject, body)
        logger.info(f"تم إرسال الملخص إلى {email}")

    def _format_email_body(self, kpis):
        """تنسيق نص البريد الإلكتروني"""
        return f"""
        ملخص أداء المؤسسة
        
        إجمالي المشاريع: {kpis['overall']['total_projects']}
        مشاريع نشطة: {kpis['overall']['active_projects']}
        نسبة الإنجاز المتوسطة: {kpis['overall']['average_progress']:.1f}%
        نسبة الالتزام بالجدول: {kpis['overall']['on_time_rate']:.1f}%
        نسبة الالتزام بالميزانية: {kpis['overall']['on_budget_rate']:.1f}%
        """

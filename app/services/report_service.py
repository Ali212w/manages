# app/services/report_service.py

"""
خدمة التقارير التلقائية - تنشئ تقارير دورية ذكية
"""

from app.models import db
from app.models.ai_models import AIReport
from datetime import datetime, timedelta
from flask import url_for
from app.services.notification_service import NotificationService
# app/services/report_service.py

class ReportService:
    """خدمة التقارير"""
    
    def __init__(self):
        self.notification_service = NotificationService()
    
    def generate_daily_summary(self):
        """إنشاء ملخص يومي تلقائي"""
        from app.models.project_models import Project
        
        today = datetime.now().date()
        
        # جلب جميع المشاريع النشطة
        projects = Project.query.filter(
            Project.status.in_(['planning', 'in_progress'])
        ).all()
        
        for project in projects:
            self.create_project_daily_summary(project)
    
    def create_project_daily_summary(self, project):
        """إنشاء ملخص يومي لمشروع"""
        from app.models.ai_models import AIReport
        
        # جمع البيانات
        total_activities = len(project.activities.all())
        completed_activities = sum(1 for a in project.activities if a.status == 'completed')
        in_progress_activities = sum(1 for a in project.activities if a.status == 'in_progress')
        
        # حساب التأخيرات
        overdue_tasks = sum(1 for t in project.tasks if t.is_delayed)
        
        # تحليل التكاليف
        cost_data = self.get_cost_summary(project)
        
        # إنشاء التقرير
        report = AIReport(
            org_id=project.org_id,
            created_by=project.project_manager_id,
            report_name=f'تقرير يومي - {project.name} - {datetime.now().strftime("%Y-%m-%d")}',
            report_type='daily',
            report_format='summary',
            report_data={
                'project_id': project.id,
                'project_name': project.name,
                'date': datetime.now().isoformat(),
                'cost_data': cost_data
            },
            report_summary=f'تقدم المشروع: {project.get_progress()}%',
            total_records=total_activities,
            date_range_start=datetime.now().date(),
            date_range_end=datetime.now().date(),
            parameters={
                'total_activities': total_activities,
                'completed_activities': completed_activities,
                'in_progress_activities': in_progress_activities,
                'overdue_tasks': overdue_tasks,
                'cost_data': cost_data
            },
            report_insights=self.generate_insights(project),
            recommendations=self.generate_recommendations(project)
        )
        
        db.session.add(report)
        db.session.commit()
        
        # إرسال إشعار التقرير اليومي
        self.notification_service.daily_report_ready(project, report)
    
    def generate_weekly_performance_report(self, project):
        """إنشاء تقرير أداء أسبوعي"""
        from app.models.ai_models import AIReport
        
        # حساب مؤشرات الأداء
        ev_analysis = self.get_earned_value_analysis(project)
        
        report = AIReport(
            org_id=project.org_id,
            created_by=project.project_manager_id,
            report_name=f'تقرير أداء أسبوعي - {project.name}',
            report_type='weekly_performance',
            report_format='detailed',
            report_data={
                'project_id': project.id,
                'week_start': (datetime.now() - timedelta(days=7)).date().isoformat(),
                'week_end': datetime.now().date().isoformat(),
                'earned_value': ev_analysis
            },
            report_summary=f'SPI: {ev_analysis["spi"]:.2f}, CPI: {ev_analysis["cpi"]:.2f}',
            report_insights=self.generate_weekly_insights(project, ev_analysis),
            recommendations=self.generate_weekly_recommendations(project, ev_analysis)
        )
        
        db.session.add(report)
        db.session.commit()
        
        # إرسال إشعار التقرير الأسبوعي
        self.notification_service.weekly_report_ready(project, report)
    
    def send_cost_performance_report(self, project, cost_data):
        """إنشاء وإرسال تقرير أداء التكاليف"""
        from app.models.ai_models import AIReport
        
        report = AIReport(
            org_id=project.org_id,
            created_by=project.project_manager_id,
            report_name=f'تقرير أداء التكاليف - {project.name}',
            report_type='cost_performance',
            report_format='detailed',
            report_data={
                'project_id': project.id,
                'planned_cost': cost_data['planned_cost'],
                'actual_cost': cost_data['actual_cost'],
                'variance': cost_data['variance'],
                'variance_percentage': cost_data['variance_percentage'],
                'breakdown': cost_data.get('breakdown', {})
            },
            report_summary=f'الفارق: {cost_data["variance"]:,.2f} ريال ({cost_data["variance_percentage"]:.1f}%)',
            report_insights=self.generate_cost_insights(project, cost_data),
            recommendations=self.generate_cost_recommendations(project, cost_data)
        )
        
        db.session.add(report)
        db.session.commit()
        
        # إرسال إشعار تقرير التكاليف
        self.notification_service.cost_report_ready(project, report)
    
    # ============================================
    # دوال مساعدة
    # ============================================
    
    def get_cost_summary(self, project):
        """الحصول على ملخص التكاليف"""
        return {
            'planned': project.budget.current_budget if project.budget else 0,
            'actual': project.cost.total_actual_cost if project.cost else 0,
            'variance': (project.cost.total_actual_cost - project.budget.current_budget) if project.budget and project.cost else 0,
            'percent_spent': (project.cost.total_actual_cost / project.budget.current_budget * 100) if project.budget and project.budget.current_budget else 0
        }
    
    def get_earned_value_analysis(self, project):
        """تحليل القيمة المكتسبة"""
        return {
            'spi': project.performance.spi if project.performance else 1.0,
            'cpi': project.performance.cpi if project.performance else 1.0,
            'eac': project.performance.eac if project.performance else 0,
            'etc': project.performance.etc if project.performance else 0
        }
    
    def generate_insights(self, project):
        """إنشاء رؤى ذكية عن المشروع"""
        insights = []
        progress = project.get_progress()
        
        if progress < 30:
            insights.append("المشروع في مراحله الأولى، التركيز على بداية قوية")
        elif progress < 70:
            insights.append("المشروع في مرحلة التنفيذ، مراقبة الموارد والتكاليف")
        else:
            insights.append("المشروع يقترب من النهاية، التركيز على جودة التسليم")
        
        overdue_count = sum(1 for t in project.tasks if t.is_delayed)
        if overdue_count > 0:
            insights.append(f"يوجد {overdue_count} مهمة متأخرة تحتاج إلى اهتمام فوري")
        
        return insights
    
    def generate_recommendations(self, project):
        """إنشاء توصيات ذكية"""
        recommendations = []
        
        if project.is_overdue:
            recommendations.append("مراجعة الجدول الزمني وإعادة تخصيص الموارد للمهام المتأخرة")
        
        cost_data = self.get_cost_summary(project)
        if cost_data['percent_spent'] > 80:
            recommendations.append("مراقبة المصروفات عن كثب، الميزانية تقترب من النفاد")
        
        return recommendations
    
    def generate_weekly_insights(self, project, ev_analysis):
        """إنشاء رؤى أسبوعية"""
        insights = []
        
        if ev_analysis['spi'] >= 1:
            insights.append("الأداء الزمني جيد، المشروع في الموعد المحدد")
        else:
            insights.append(f"الأداء الزمني يحتاج إلى تحسين (SPI = {ev_analysis['spi']:.2f})")
        
        if ev_analysis['cpi'] >= 1:
            insights.append("الأداء المالي جيد، التكاليف ضمن الميزانية")
        else:
            insights.append(f"الأداء المالي يحتاج إلى تحسين (CPI = {ev_analysis['cpi']:.2f})")
        
        return insights
    
    def generate_weekly_recommendations(self, project, ev_analysis):
        """إنشاء توصيات أسبوعية"""
        recommendations = []
        
        if ev_analysis['spi'] < 0.9:
            recommendations.append("تخصيص موارد إضافية للمهام الحرجة")
        
        if ev_analysis['cpi'] < 0.9:
            recommendations.append("مراجعة عقود الموردين وإعادة التفاوض على الأسعار")
        
        return recommendations
    
    def generate_cost_insights(self, project, cost_data):
        """إنشاء رؤى عن التكاليف"""
        insights = []
        
        if cost_data['variance'] > 0:
            insights.append(f"تجاوز الميزانية بمبلغ {cost_data['variance']:,.2f} ريال")
        elif cost_data['variance'] < 0:
            insights.append(f"توفير في الميزانية بمبلغ {abs(cost_data['variance']):,.2f} ريال")
        else:
            insights.append("المشروع ضمن الميزانية المخططة")
        
        return insights
    
    def generate_cost_recommendations(self, project, cost_data):
        """إنشاء توصيات للتكاليف"""
        recommendations = []
        
        if cost_data['variance_percentage'] > 10:
            recommendations.append("عقد اجتماع عاجل مع الفريق المالي لمراجعة المصروفات")
            recommendations.append("مراجعة جدول المدفوعات مع الموردين")
        
        return recommendations
    
    def send_weekly_performance_report(self, project):
        """إرسال تقرير أداء أسبوعي"""
        # حساب مؤشرات الأداء
        progress = project.get_progress()
        cpi = project.performance.cpi if project.performance else 1.0
        spi = project.performance.spi if project.performance else 1.0
        
        report = AIReport(
            org_id=project.org_id,
            created_by=project.project_manager_id,
            report_name=f'تقرير أداء أسبوعي - {project.name}',
            report_type='weekly_performance',
            report_format='detailed',
            report_data={
                'project_id': project.id,
                'week_start': (datetime.now() - timedelta(days=7)).date().isoformat(),
                'week_end': datetime.now().date().isoformat()
            },
            report_summary=f'التقدم: {progress:.1f}% | SPI: {spi:.2f} | CPI: {cpi:.2f}',
            report_insights=[
                f'مؤشر أداء الجدول: {"جيد" if spi >= 1 else "ضعيف"}',
                f'مؤشر أداء التكلفة: {"جيد" if cpi >= 1 else "ضعيف"}',
                f'نسبة الإنجاز الأسبوعية: {progress - project.previous_week_progress if hasattr(project, "previous_week_progress") else progress:.1f}%'
            ],
            recommendations=self.generate_weekly_recommendations(project)
        )
        db.session.add(report)
        db.session.commit()
        
        # إرسال إشعار بالتقرير
        self.notification_service.weekly_report_ready(project, report)
    
    def send_cost_performance_report(self, project, cost_data):
        """إرسال تقرير أداء التكاليف"""
        report = AIReport(
            org_id=project.org_id,
            created_by=project.project_manager_id,
            report_name=f'تقرير أداء التكاليف - {project.name}',
            report_type='cost_performance',
            report_format='detailed',
            report_data={
                'project_id': project.id,
                'planned_cost': cost_data['planned_cost'],
                'actual_cost': cost_data['actual_cost'],
                'variance': cost_data['variance'],
                'variance_percentage': cost_data['variance_percentage'],
                'breakdown': cost_data.get('breakdown', {})
            },
            report_summary=f'الفارق: {cost_data["variance"]:,.2f} ريال ({cost_data["variance_percentage"]:.1f}%)',
            report_insights=[
                f'الميزانية المخططة: {cost_data["planned_cost"]:,.2f} ريال',
                f'التكلفة الفعلية: {cost_data["actual_cost"]:,.2f} ريال',
                f'الفارق: {"تجاوز" if cost_data["variance"] > 0 else "توفير"} {abs(cost_data["variance"]):,.2f} ريال'
            ],
            recommendations=self.generate_cost_recommendations(project, cost_data)
        )
        db.session.add(report)
        db.session.commit()
        
        # إرسال إشعار بالتقرير
        self.notification_service.cost_report_ready(project, report)
    
    def generate_weekly_recommendations(self, project):
        """توليد توصيات أسبوعية"""
        recommendations = []
        
        if project.performance and project.performance.spi < 0.9:
            recommendations.append("تحسين الجدول الزمني: زيادة الموارد للمهام الحرجة")
        
        if project.performance and project.performance.cpi < 0.9:
            recommendations.append("تحسين أداء التكلفة: مراجعة عقود الموردين")
        
        if project.get_progress() < 50 and project.dates and project.dates.planned_finish:
            days_remaining = (project.dates.planned_finish.date() - datetime.now().date()).days
            if days_remaining < 30:
                recommendations.append("زيادة وتيرة العمل: إضافة نوبات عمل إضافية")
        
        return recommendations
    
    def generate_cost_recommendations(self, project, cost_data):
        """توليد توصيات للتكاليف"""
        recommendations = []
        
        if cost_data['variance'] > 0:
            recommendations.append(f"مراجعة المصروفات الزائدة: {cost_data['variance']:,.2f} ريال")
            recommendations.append("عقد اجتماع مع الفريق المالي لتحديد أسباب التجاوز")
        
        if cost_data['variance_percentage'] > 10:
            recommendations.append("إعادة تقييم الميزانية وتحديث التوقعات")
        
        return recommendations
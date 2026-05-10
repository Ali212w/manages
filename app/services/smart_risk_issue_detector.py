"""
smart_risk_issue_detector.py - خدمة الكشف والتسجيل التلقائي للمخاطر والقضايا
"""

from datetime import datetime, timedelta
from app.models import db
from app.models import Risk, Issue, Project, Activity, Task, Notification,ProjectChat
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class SmartRiskIssueDetector:
    """كاشف ذكي للمخاطر والقضايا - يسجلها تلقائياً عند اكتشافها"""
    
    # شروط اكتشاف المخاطر
    RISK_CONDITIONS = {
        'schedule_delay': {
            'name': 'تأخير في الجدول الزمني',
            'name_en': 'Schedule Delay',
            'description': 'تم اكتشاف تأخير في الجدول الزمني للمشروع',
            'description_en': 'Schedule delay detected in project',
            'category': 'schedule',
            'default_probability': 0.7,
            'default_impact': 0.6
        },
        'budget_overrun': {
            'name': 'تجاوز الميزانية',
            'name_en': 'Budget Overrun',
            'description': 'تم اكتشاف تجاوز في ميزانية المشروع',
            'description_en': 'Budget overrun detected in project',
            'category': 'cost',
            'default_probability': 0.6,
            'default_impact': 0.8
        },
        'resource_shortage': {
            'name': 'نقص في الموارد',
            'name_en': 'Resource Shortage',
            'description': 'تم اكتشاف نقص في الموارد المطلوبة',
            'description_en': 'Resource shortage detected',
            'category': 'resource',
            'default_probability': 0.5,
            'default_impact': 0.5
        },
        'task_overdue': {
            'name': 'مهام متأخرة',
            'name_en': 'Overdue Tasks',
            'description': 'توجد مهام متأخرة عن الجدول الزمني',
            'description_en': 'Tasks are overdue',
            'category': 'schedule',
            'default_probability': 0.8,
            'default_impact': 0.5
        },
        'quality_issue': {
            'name': 'مشكلة في الجودة',
            'name_en': 'Quality Issue',
            'description': 'تم اكتشاف مشكلة في جودة العمل',
            'description_en': 'Quality issue detected',
            'category': 'quality',
            'default_probability': 0.4,
            'default_impact': 0.7
        },
        'safety_violation': {
            'name': 'مخالفة سلامة',
            'name_en': 'Safety Violation',
            'description': 'تم اكتشاف مخالفة في إجراءات السلامة',
            'description_en': 'Safety violation detected',
            'category': 'safety',
            'default_probability': 0.3,
            'default_impact': 0.9
        },
        'stakeholder_conflict': {
            'name': 'نزاع مع أصحاب المصلحة',
            'name_en': 'Stakeholder Conflict',
            'description': 'تم اكتشاف نزاع مع أصحاب المصلحة',
            'description_en': 'Stakeholder conflict detected',
            'category': 'stakeholder',
            'default_probability': 0.5,
            'default_impact': 0.6
        },
        'weather_delay': {
            'name': 'تأخير بسبب الطقس',
            'name_en': 'Weather Delay',
            'description': 'تم اكتشاف تأخير بسبب الظروف الجوية',
            'description_en': 'Weather-related delay detected',
            'category': 'external',
            'default_probability': 0.4,
            'default_impact': 0.4
        }
    }
    
    # شروط اكتشاف القضايا
    ISSUE_CONDITIONS = {
        'technical_problem': {
            'name': 'مشكلة تقنية',
            'name_en': 'Technical Problem',
            'description': 'تم اكتشاف مشكلة تقنية في التنفيذ',
            'description_en': 'Technical problem detected',
            'category': 'technical',
            'default_priority': 'high'
        },
        'design_change': {
            'name': 'تغيير في التصميم',
            'name_en': 'Design Change',
            'description': 'تم طلب تغيير في التصميم',
            'description_en': 'Design change requested',
            'category': 'design',
            'default_priority': 'medium'
        },
        'material_defect': {
            'name': 'عيوب في المواد',
            'name_en': 'Material Defect',
            'description': 'تم اكتشاف عيوب في المواد المستخدمة',
            'description_en': 'Material defects detected',
            'category': 'quality',
            'default_priority': 'critical'
        },
        'equipment_failure': {
            'name': 'عطل في المعدات',
            'name_en': 'Equipment Failure',
            'description': 'تم اكتشاف عطل في المعدات',
            'description_en': 'Equipment failure detected',
            'category': 'equipment',
            'default_priority': 'high'
        },
        'communication_gap': {
            'name': 'فجوة تواصل',
            'name_en': 'Communication Gap',
            'description': 'تم اكتشاف فجوة في التواصل بين الفرق',
            'description_en': 'Communication gap detected',
            'category': 'communication',
            'default_priority': 'medium'
        },
        'approval_delay': {
            'name': 'تأخير في الموافقات',
            'name_en': 'Approval Delay',
            'description': 'تأخير في الحصول على الموافقات المطلوبة',
            'description_en': 'Delay in obtaining approvals',
            'category': 'administrative',
            'default_priority': 'high'
        }
    }
    
    @classmethod
    def detect_and_log_risks(cls, project_id):
        """الكشف عن المخاطر وتسجيلها تلقائياً"""
        project = Project.query.get(project_id)
        if not project:
            return []
        
        detected_risks = []
        
        # 1. الكشف عن تأخير الجدول
        if cls._check_schedule_delay(project):
            risk = cls._create_risk(project, 'schedule_delay')
            detected_risks.append(risk)
        
        # 2. الكشف عن تجاوز الميزانية
        if cls._check_budget_overrun(project):
            risk = cls._create_risk(project, 'budget_overrun')
            detected_risks.append(risk)
        
        # 3. الكشف عن نقص الموارد
        if cls._check_resource_shortage(project):
            risk = cls._create_risk(project, 'resource_shortage')
            detected_risks.append(risk)
        
        # 4. الكشف عن مهام متأخرة
        overdue_tasks = cls._get_overdue_tasks(project)
        if overdue_tasks:
            risk = cls._create_risk(project, 'task_overdue')
            risk.description = f"توجد {len(overdue_tasks)} مهام متأخرة عن الجدول"
            detected_risks.append(risk)
        
        # 5. الكشف عن مشاكل الجودة
        if cls._check_quality_issues(project):
            risk = cls._create_risk(project, 'quality_issue')
            detected_risks.append(risk)
        
        # 6. الكشف عن مخالفات السلامة
        if cls._check_safety_violations(project):
            risk = cls._create_risk(project, 'safety_violation')
            detected_risks.append(risk)
        
        # إرسال إشعارات للمخاطر المكتشفة
        for risk in detected_risks:
            if risk:  # تم إنشاؤه حديثاً
                cls._notify_risk_detected(risk)
        
        return detected_risks
    
    @classmethod
    def detect_and_log_issues(cls, project_id):
        """الكشف عن القضايا وتسجيلها تلقائياً"""
        project = Project.query.get(project_id)
        if not project:
            return []
        
        detected_issues = []
        
        # 1. الكشف عن مشاكل تقنية
        technical_issues = cls._check_technical_problems(project)
        if technical_issues:
            for issue in technical_issues:
                new_issue = cls._create_issue(project, 'technical_problem', issue)
                detected_issues.append(new_issue)
        
        # 2. الكشف عن عيوب في المواد
        material_defects = cls._check_material_defects(project)
        if material_defects:
            for defect in material_defects:
                new_issue = cls._create_issue(project, 'material_defect', defect)
                detected_issues.append(new_issue)
        
        # 3. الكشف عن أعطال في المعدات
        equipment_failures = cls._check_equipment_failures(project)
        if equipment_failures:
            for failure in equipment_failures:
                new_issue = cls._create_issue(project, 'equipment_failure', failure)
                detected_issues.append(new_issue)
        
        # 4. الكشف عن فجوات التواصل
        if cls._check_communication_gaps(project):
            issue = cls._create_issue(project, 'communication_gap')
            detected_issues.append(issue)
        
        # إرسال إشعارات للقضايا المكتشفة
        for issue in detected_issues:
            if issue:
                cls._notify_issue_detected(issue)
        
        return detected_issues
    
    # ============================================
    # دوال الكشف عن المخاطر
    # ============================================
    
    @classmethod
    def _check_schedule_delay(cls, project):
        """التحقق من تأخير الجدول"""
        if project.dates and project.dates.planned_finish:
            today = datetime.now().date()
            planned_finish = project.dates.planned_finish
            if hasattr(planned_finish, 'date'):
                planned_finish = planned_finish.date()
            
            if today > planned_finish:
                delay_days = (today - planned_finish).days
                if delay_days > 5:  # تأخير أكثر من 5 أيام
                    return True
        return False
    
    @classmethod
    def _check_budget_overrun(cls, project):
        """التحقق من تجاوز الميزانية"""
        if project.cost and project.budget:
            if project.budget.current_budget > 0:
                overrun_percentage = (project.cost.total_actual_cost / project.budget.current_budget) * 100
                if overrun_percentage > 100:  # تجاوز الميزانية
                    return True
        return False
    
    @classmethod
    def _check_resource_shortage(cls, project):
        """التحقق من نقص الموارد"""
        from app.models.primavera_models import Resource, ActivityResource
        
        resources = Resource.query.filter_by(org_id=project.org_id).all()
        for resource in resources:
            if resource.available_quantity < resource.minimum_quantity:
                return True
        return False
    
    @classmethod
    def _get_overdue_tasks(cls, project):
        """الحصول على المهام المتأخرة"""
        tasks = Task.query.filter_by(project_id=project.id).all()
        overdue = [t for t in tasks if t.is_delayed]
        return overdue
    
    @classmethod
    def _check_quality_issues(cls, project):
        """التحقق من مشاكل الجودة"""
        from app.models.project_models import QualityCheck
        
        failed_checks = QualityCheck.query.filter_by(
            project_id=project.id,
            status='failed'
        ).count()
        
        return failed_checks > 3  # أكثر من 3 فحوصات فاشلة
    
    @classmethod
    def _check_safety_violations(cls, project):
        """التحقق من مخالفات السلامة"""
        from app.models.ai_models import SafetyInspection
        
        failed_inspections = SafetyInspection.query.filter_by(
            project_id=project.id,
            status='failed'
        ).count()
        
        return failed_inspections > 2  # أكثر من 2 فحص فاشل
    
    # ============================================
    # دوال الكشف عن القضايا
    # ============================================
    
    @classmethod
    def _check_technical_problems(cls, project):
        """التحقق من المشاكل التقنية"""
        problems = []
        
        # فحص الأنشطة المتعطلة
        stalled_activities = Activity.query.filter(
            Activity.project_id == project.id,
            Activity.status == 'delayed',
            Activity.progress_percentage < 30
        ).all()
        
        for activity in stalled_activities:
            problems.append({
                'title': f'نشاط متعطل: {activity.activity_name}',
                'description': f'النشاط {activity.activity_name} متعطل منذ فترة طويلة'
            })
        
        return problems
    
    @classmethod
    def _check_material_defects(cls, project):
        """التحقق من عيوب المواد"""
        from app.models.project_models import QualityCheck
        
        defects = []
        material_checks = QualityCheck.query.filter_by(
            project_id=project.id,
            check_type='material'
        ).all()
        
        for check in material_checks:
            if check.status == 'failed':
                defects.append({
                    'title': f'عيوب في المواد: {check.check_name}',
                    'description': check.result or 'تم اكتشاف عيوب في المواد'
                })
        
        return defects
    
    @classmethod
    def _check_equipment_failures(cls, project):
        """التحقق من أعطال المعدات"""
        from app.models.primavera_models import Resource, ActivityResource
        
        failures = []
        equipment_resources = Resource.query.filter_by(
            org_id=project.org_id,
            resource_type='equipment'
        ).all()
        
        for equipment in equipment_resources:
            # التحقق من آخر صيانة
            if equipment.last_maintenance:
                days_since_maintenance = (datetime.now().date() - equipment.last_maintenance).days
                if days_since_maintenance > equipment.maintenance_cycle:
                    failures.append({
                        'title': f'معدة بحاجة لصيانة: {equipment.name}',
                        'description': f'لم يتم صيانة المعدة منذ {days_since_maintenance} يوم'
                    })
        
        return failures
    
    @classmethod
    def _check_communication_gaps(cls, project):
        """التحقق من فجوات التواصل"""
        from app.models.communication_models import ChatMessage
        
        # فحص آخر رسالة في المحادثة
        last_message = ChatMessage.query.join(
            ProjectChat, ChatMessage.chat_id == ProjectChat.id
        ).filter(
            ProjectChat.project_id == project.id
        ).order_by(ChatMessage.created_at.desc()).first()
        
        if last_message:
            days_since_last = (datetime.now() - last_message.created_at).days
            if days_since_last > 7:  # أكثر من أسبوع بدون تواصل
                return True
        
        return False
    
    # ============================================
    # دوال إنشاء المخاطر والقضايا
    # ============================================
    
    @classmethod
    def _create_risk(cls, project, risk_type, additional_data=None):
        """إنشاء خطر جديد"""
        # التحقق من عدم وجود خطر مشابه مسجل مسبقاً
        existing = Risk.query.filter_by(
            project_id=project.id,
            title=cls.RISK_CONDITIONS[risk_type]['name']
        ).filter(Risk.status != 'closed').first()
        
        if existing:
            return None
        
        risk_config = cls.RISK_CONDITIONS[risk_type]
        
        risk = Risk(
            project_id=project.id,
            risk_code=f"RISK-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            title=risk_config['name'],
            description=additional_data.get('description', risk_config['description']) if additional_data else risk_config['description'],
            category=risk_config['category'],
            probability=risk_config['default_probability'],
            impact=risk_config['default_impact'],
            risk_level='high' if risk_config['default_probability'] * risk_config['default_impact'] > 0.5 else 'medium',
            status='identified',
            identified_date=datetime.now().date(),
            created_by=project.project_manager_id
        )
        
        risk.calculate_severity()
        db.session.add(risk)
        db.session.commit()
        
        logger.info(f"✅ تم اكتشاف خطر جديد: {risk.title} في المشروع {project.name}")
        
        return risk
    
    @classmethod
    def _create_issue(cls, project, issue_type, additional_data=None):
        """إنشاء قضية جديدة"""
        issue_config = cls.ISSUE_CONDITIONS[issue_type]
        
        issue = Issue(
            project_id=project.id,
            issue_code=f"ISS-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            title=additional_data.get('title', issue_config['name']) if additional_data else issue_config['name'],
            description=additional_data.get('description', issue_config['description']) if additional_data else issue_config['description'],
            category=issue_config['category'],
            priority=issue_config['default_priority'],
            status='open',
            reported_by=project.project_manager_id,
            reported_date=datetime.utcnow(),
            assigned_to=project.project_manager_id
        )
        
        db.session.add(issue)
        db.session.commit()
        
        logger.info(f"✅ تم اكتشاف قضية جديدة: {issue.title} في المشروع {project.name}")
        
        return issue
    
    @classmethod
    def _notify_risk_detected(cls, risk):
        """إرسال إشعار باكتشاف خطر"""
        NotificationService.risk_detected2(
            risk=risk,
            project=risk.project,
            severity=risk.risk_level
        )
    
    @classmethod
    def _notify_issue_detected(cls, issue):
        """إرسال إشعار باكتشاف قضية"""
        NotificationService.issue_reported2(
            issue=issue,
            project=issue.project,
            priority=issue.priority
        )
    
    @classmethod
    def run_scheduled_scan(cls):
        """تشغيل فحص مجدول لجميع المشاريع النشطة"""
        projects = Project.query.filter_by(status='active').all()
        
        total_risks = 0
        total_issues = 0
        
        for project in projects:
            risks = cls.detect_and_log_risks(project.id)
            issues = cls.detect_and_log_issues(project.id)
            total_risks += len(risks)
            total_issues += len(issues)
        
        logger.info(f"📊 الفحص التلقائي: تم اكتشاف {total_risks} خطر و {total_issues} قضية")
        
        return {'risks': total_risks, 'issues': total_issues}
# services/plan_validation_service.py
"""
خدمة التحقق من حدود الباقة والامتيازات
"""

from flask import current_app
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PlanValidationService:
    """خدمة التحقق من حدود الباقة والامتيازات"""
    
    @staticmethod
    def get_company_plan(company):
        """
        الحصول على خطة الشركة الحالية
        
        Args:
            company: كائن الشركة
        
        Returns:
            dict: معلومات الخطة
        """
        from app.models.core_models import SubscriptionPlan, Subscription
        
        # التحقق من الاشتراك النشط
        active_sub = Subscription.query.filter_by(
            org_id=company.id,
            status='active'
        ).first()
        
        if active_sub and active_sub.plan_id:
            plan = SubscriptionPlan.query.filter_by(plan_id=active_sub.plan_id, is_active=True).first()
            if plan:
                return plan
        
        # التحقق من الفترة التجريبية
        if company.subscription_status == 'trial' and company.trial_end and company.trial_end > datetime.utcnow():
            # خطة تجريبية بمدة 20 يوم
            trial_plan = {
                'plan_id': 'free',
                'name': 'Free Trial',
                'max_users': 10,
                'max_projects': 5,
                'storage_gb': 1,
                'currency': 'USD',
                'price_monthly': 0
            }
            return trial_plan
        
        # خطة افتراضية
        default_plan = SubscriptionPlan.query.filter_by(is_default=True, is_active=True).first()
        return default_plan
    
    @staticmethod
    def check_user_limit(company):
        """
        التحقق من عدم تجاوز الحد الأقصى للمستخدمين
        
        Args:
            company: كائن الشركة
        
        Returns:
            tuple: (is_allowed, message, current, max)
        """
        plan = PlanValidationService.get_company_plan(company)
        
        if not plan:
            return True, "", 0, 0
        
        max_users = plan.max_users if hasattr(plan, 'max_users') else plan.get('max_users', 0)
        current_users = company.current_users
        
        if max_users > 0 and current_users >= max_users:
            return False, f"لقد تجاوزت الحد الأقصى لعدد المستخدمين ({max_users} مستخدم). يرجى ترقية اشتراكك.", current_users, max_users
        
        remaining = max_users - current_users if max_users > 0 else float('inf')
        return True, f"يمكنك إضافة {remaining} مستخدم إضافي", current_users, max_users
    
    @staticmethod
    def check_project_limit(company):
        """
        التحقق من عدم تجاوز الحد الأقصى للمشاريع
        
        Args:
            company: كائن الشركة
        
        Returns:
            tuple: (is_allowed, message, current, max)
        """
        from app.models.project_models import Project
        
        plan = PlanValidationService.get_company_plan(company)
        
        if not plan:
            return True, "", 0, 0
        
        max_projects = plan.max_projects if hasattr(plan, 'max_projects') else plan.get('max_projects', 0)
        current_projects = Project.query.filter_by(org_id=company.id).count()
        
        if max_projects > 0 and current_projects >= max_projects:
            return False, f"لقد تجاوزت الحد الأقصى لعدد المشاريع ({max_projects} مشروع). يرجى ترقية اشتراكك.", current_projects, max_projects
        
        remaining = max_projects - current_projects if max_projects > 0 else float('inf')
        return True, f"يمكنك إنشاء {remaining} مشروع إضافي", current_projects, max_projects
    
    @staticmethod
    def check_storage_limit(company, additional_mb=0):
        """
        التحقق من عدم تجاوز الحد الأقصى للتخزين
        
        Args:
            company: كائن الشركة
            additional_mb: المساحة الإضافية المطلوبة بالميجابايت
        
        Returns:
            tuple: (is_allowed, message, current, max)
        """
        plan = PlanValidationService.get_company_plan(company)
        
        if not plan:
            return True, "", 0, 0
        
        max_storage_mb = (plan.storage_gb if hasattr(plan, 'storage_gb') else plan.get('storage_gb', 0)) * 1024
        current_storage = company.storage_used_mb
        
        if max_storage_mb > 0 and (current_storage + additional_mb) > max_storage_mb:
            used_percent = (current_storage / max_storage_mb) * 100
            return False, f"مساحة التخزين ممتلئة بنسبة {used_percent:.1f}%. يرجى حذف بعض الملفات أو ترقية اشتراكك.", current_storage, max_storage_mb
        
        remaining = max_storage_mb - current_storage if max_storage_mb > 0 else float('inf')
        return True, f"المساحة المتبقية: {remaining / 1024:.1f} جيجابايت", current_storage, max_storage_mb
    
    @staticmethod
    def check_feature_access(company, feature_name):
        """
        التحقق من صلاحية الوصول إلى ميزة معينة
        
        Args:
            company: كائن الشركة
            feature_name: اسم الميزة المطلوبة
        
        Returns:
            tuple: (has_access, message)
        """
        plan = PlanValidationService.get_company_plan(company)
        
        if not plan:
            return False, "لا توجد خطة نشطة"
        
        # قائمة الميزات حسب الخطة
        plan_features = plan.features if hasattr(plan, 'features') else plan.get('features', [])
        
        # التحقق من وجود الميزة في الخطة
        feature_found = any(feature_name.lower() in f.lower() for f in plan_features)
        
        if not feature_found:
            return False, f"هذه الميزة ({feature_name}) غير متاحة في خطتك الحالية. يرجى ترقية اشتراكك."
        
        return True, "الميزة متاحة"
    
    @staticmethod
    def get_plan_limits(company):
        """
        الحصول على جميع حدود الخطة
        
        Args:
            company: كائن الشركة
        
        Returns:
            dict: حدود الخطة
        """
        from app.models.project_models import Project
        
        plan = PlanValidationService.get_company_plan(company)
        
        if not plan:
            return {}
        
        # الحصول على الاستخدام الحالي
        current_projects = Project.query.filter_by(org_id=company.id).count()
        
        limits = {
            'plan_id': plan.plan_id if hasattr(plan, 'plan_id') else plan.get('plan_id'),
            'plan_name': plan.name if hasattr(plan, 'name') else plan.get('name'),
            'max_users': plan.max_users if hasattr(plan, 'max_users') else plan.get('max_users', 0),
            'current_users': company.current_users,
            'users_remaining': (plan.max_users - company.current_users) if (hasattr(plan, 'max_users') and plan.max_users > 0) else float('inf'),
            'max_projects': plan.max_projects if hasattr(plan, 'max_projects') else plan.get('max_projects', 0),
            'current_projects': current_projects,
            'projects_remaining': (plan.max_projects - current_projects) if (hasattr(plan, 'max_projects') and plan.max_projects > 0) else float('inf'),
            'max_storage_gb': plan.storage_gb if hasattr(plan, 'storage_gb') else plan.get('storage_gb', 0),
            'current_storage_gb': company.storage_used_mb / 1024,
            'storage_remaining_gb': ((plan.storage_gb * 1024) - company.storage_used_mb) / 1024 if (hasattr(plan, 'storage_gb') and plan.storage_gb > 0) else float('inf'),
            'currency': plan.currency if hasattr(plan, 'currency') else plan.get('currency', 'USD'),
            'price_monthly': plan.price_monthly if hasattr(plan, 'price_monthly') else plan.get('price_monthly', 0),
            'features': plan.features if hasattr(plan, 'features') else plan.get('features', [])
        }
        
        # تحويل القيم غير المحدودة إلى نص مناسب
        for key, value in limits.items():
            if value == float('inf'):
                limits[key] = 'unlimited'
        
        return limits
    
    @staticmethod
    def validate_before_action(company, action_type, **kwargs):
        """
        التحقق من الصلاحية قبل تنفيذ إجراء معين
        
        Args:
            company: كائن الشركة
            action_type: نوع الإجراء (create_user, create_project, upload_file, etc.)
            **kwargs: معاملات إضافية
        
        Returns:
            tuple: (is_allowed, message)
        """
        validators = {
            'create_user': lambda: PlanValidationService.check_user_limit(company),
            'create_project': lambda: PlanValidationService.check_project_limit(company),
            'upload_file': lambda: PlanValidationService.check_storage_limit(company, kwargs.get('file_size_mb', 0)),
            'access_feature': lambda: PlanValidationService.check_feature_access(company, kwargs.get('feature_name', ''))
        }
        
        if action_type not in validators:
            return True, "لا يوجد قيد لهذا الإجراء"
        
        return validators[action_type]()
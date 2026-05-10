# app/decorators.py - ملف مستقل للديكوراتورات
"""
مجلد: app/decorators.py
الوصف: يحتوي على جميع الديكوراتورات المستخدمة في التطبيق
"""

from functools import wraps
from flask import flash, redirect, url_for, request, current_app
from flask_login import current_user
from datetime import datetime


def login_required_with_message(f):
    """
    ديكوراتور لتسجيل الدخول مع رسالة مخصصة
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً للوصول إلى هذه الصفحة', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def subscription_required(f):
    """
    ديكوراتور للتحقق من أن الشركة لديها اشتراك نشط
    يسمح فقط بالوصول إلى واجهات الخطط والاشتراك إذا كانت الفترة التجريبية منتهية
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        # التحقق من وجود شركة
        if not hasattr(current_user, 'organization') or not current_user.organization:
            return f(*args, **kwargs)
        
        company = current_user.organization
        
        # قائمة المسارات المسموح بها حتى لو انتهت الفترة التجريبية
        allowed_endpoints = [
            'company.view_plans',
            'company.subscribe_to_plan',
            'company.subscription_status',
            'company.subscription_payment_info',
            'company.upload_payment_proof',
            'company.process_payment',
            'company.payment_success',
            'company.payment_cancel',
            'company.upgrade_subscription',
            'company.downgrade_subscription',
            'company.logout',
            'company.plans',
            'company.subscription',
            # أضف أي مسارات أخرى تريد السماح بها
        ]
        
        # إذا كانت الفترة التجريبية منتهية والاشتراك غير نشط
        if company.subscription_status == 'expired' and company.trial_end and company.trial_end < datetime.utcnow():
            # التحقق من أن المسار الحالي مسموح به
            if request.endpoint not in allowed_endpoints:
                flash('انتهت الفترة التجريبية لشركتك. يرجى الاشتراك في إحدى الباقات للاستمرار في استخدام المنصة.', 'danger')
                return redirect(url_for('company.view_plans'))
        
        return f(*args, **kwargs)
    return decorated_function


def active_subscription_required(f):
    """
    ديكوراتور للتحقق من أن الشركة لديها اشتراك نشط (مدفوع أو تجريبي غير منتهي)
    يستخدم للوظائف الحيوية التي تتطلب اشتراك نشط
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not hasattr(current_user, 'organization') or not current_user.organization:
            return f(*args, **kwargs)
        
        company = current_user.organization
        
        # التحقق من وجود اشتراك نشط
        has_active = False
        
        # فحص الفترة التجريبية
        if company.subscription_status == 'trial':
            if company.trial_end and company.trial_end > datetime.utcnow():
                has_active = True
        
        # فحص الاشتراك المدفوع
        if company.subscription_status == 'active':
            # التحقق من وجود اشتراك في جدول الاشتراكات
            from app.models.core_models import Subscription
            active_sub = Subscription.query.filter_by(
                org_id=company.id,
                status='active'
            ).first()
            if active_sub and active_sub.end_date and active_sub.end_date > datetime.utcnow():
                has_active = True
        
        if not has_active:
            flash('لا يمكنك الوصول إلى هذه الصفحة. يرجى الاشتراك في إحدى الباقات أولاً.', 'danger')
            return redirect(url_for('company.view_plans'))
        
        return f(*args, **kwargs)
    return decorated_function


def platform_admin_required(f):
    """
    ديكوراتور للتحقق من أن المستخدم هو مدير منصة
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not hasattr(current_user, 'role') or current_user.role not in ['super_admin', 'admin']:
            flash('غير مصرح بالوصول إلى هذه الصفحة', 'danger')
            return redirect(url_for('company.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def super_admin_required(f):
    """
    ديكوراتور للتحقق من أن المستخدم هو مشرف عام
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not hasattr(current_user, 'role') or current_user.role != 'super_admin':
            flash('غير مصرح بالوصول إلى هذه الصفحة - المشرف العام فقط', 'danger')
            return redirect(url_for('platform.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def org_admin_required(f):
    """
    ديكوراتور للتحقق من أن المستخدم هو مدير شركة
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not hasattr(current_user, 'role') or current_user.role != 'org_admin':
            flash('غير مصرح بالوصول إلى هذه الصفحة - مدير الشركة فقط', 'danger')
            return redirect(url_for('employee.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """
    ديكوراتور للتحقق من أن المستخدم لديه دور مسموح به
    الاستخدام: @role_required('admin', 'super_admin')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('يرجى تسجيل الدخول أولاً', 'warning')
                return redirect(url_for('auth.login'))
            
            if not hasattr(current_user, 'role') or current_user.role not in allowed_roles:
                flash('غير مصرح بالوصول إلى هذه الصفحة', 'danger')
                return redirect(url_for('auth.login'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def company_owner_required(f):
    """
    ديكوراتور للتحقق من أن المستخدم هو مالك الشركة (مدير الشركة)
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        # التحقق من وجود شركة
        if not hasattr(current_user, 'organization'):
            flash('لا توجد شركة مرتبطة بهذا الحساب', 'danger')
            return redirect(url_for('auth.login'))
        
        # التحقق من أن المستخدم هو مدير الشركة
        if current_user.role != 'org_admin':
            flash('غير مصرح بالوصول - فقط مدير الشركة يمكنه الوصول', 'danger')
            return redirect(url_for('employee.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


def ajax_required(f):
    """
    ديكوراتور للتحقق من أن الطلب هو AJAX
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            flash('طلب غير صالح', 'danger')
            return redirect(url_for('company.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def rate_limit(limit_per_minute=60):
    """
    ديكوراتور للحد من عدد الطلبات (Rate Limiting)
    الاستخدام: @rate_limit(limit_per_minute=30)
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # يمكن تنفيذ منطق rate limiting هنا
            # باستخدام redis أو cache
            return f(*args, **kwargs)
        return decorated_function
    return decorator
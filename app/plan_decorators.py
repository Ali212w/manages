# app/decorators/plan_decorators.py
"""
ديكوراتورات للتحقق من حدود الباقة
"""

from functools import wraps
from flask import flash, redirect, url_for, request
from flask_login import current_user
from app.services.plan_validation_service import PlanValidationService


def check_user_limit(f):
    """
    ديكوراتور للتحقق من عدم تجاوز حد المستخدمين قبل إضافة مستخدم جديد
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not hasattr(current_user, 'organization'):
            return f(*args, **kwargs)
        
        company = current_user.organization
        is_allowed, message, current, max_limit = PlanValidationService.check_user_limit(company)
        
        if not is_allowed:
            flash(message, 'danger')
            return redirect(url_for('company.users'))
        
        return f(*args, **kwargs)
    return decorated_function


def check_project_limit(f):
    """
    ديكوراتور للتحقق من عدم تجاوز حد المشاريع قبل إنشاء مشروع جديد
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not hasattr(current_user, 'organization'):
            return f(*args, **kwargs)
        
        company = current_user.organization
        is_allowed, message, current, max_limit = PlanValidationService.check_project_limit(company)
        
        if not is_allowed:
            flash(message, 'danger')
            return redirect(url_for('company.projects'))
        
        return f(*args, **kwargs)
    return decorated_function


def check_storage_limit(file_size_mb=0):
    """
    ديكوراتور للتحقق من عدم تجاوز حد التخزين قبل رفع ملف
    
    Args:
        file_size_mb: حجم الملف المتوقع رفعه بالميجابايت
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('يرجى تسجيل الدخول أولاً', 'warning')
                return redirect(url_for('auth.login'))
            
            if not hasattr(current_user, 'organization'):
                return f(*args, **kwargs)
            
            company = current_user.organization
            
            # محاولة الحصول على حجم الملف من الطلب
            actual_file_size = file_size_mb
            if 'file' in request.files:
                file = request.files['file']
                if file and file.filename:
                    file.seek(0, 2)
                    file_size_bytes = file.tell()
                    file.seek(0)
                    actual_file_size = file_size_bytes / (1024 * 1024)
            
            is_allowed, message, current, max_limit = PlanValidationService.check_storage_limit(company, actual_file_size)
            
            if not is_allowed:
                flash(message, 'danger')
                return redirect(request.referrer or url_for('company.documents'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def feature_required(feature_name):
    """
    ديكوراتور للتحقق من صلاحية الوصول إلى ميزة معينة
    
    Args:
        feature_name: اسم الميزة المطلوبة
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('يرجى تسجيل الدخول أولاً', 'warning')
                return redirect(url_for('auth.login'))
            
            if not hasattr(current_user, 'organization'):
                return f(*args, **kwargs)
            
            company = current_user.organization
            has_access, message = PlanValidationService.check_feature_access(company, feature_name)
            
            if not has_access:
                flash(message, 'warning')
                return redirect(url_for('company.view_plans'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
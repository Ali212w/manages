# app/utils.py
from functools import wraps
from flask import flash, redirect, url_for, current_app
from flask_login import current_user
from app.models import User, Organization

def get_user_type():
    """تحديد نوع المستخدم الحالي"""
    if not current_user.is_authenticated:
        return 'anonymous'
    
    # الحصول على اسم النموذج الفعلي
    model_name = current_user.__class__.__name__
    
    if model_name == 'User':
        return 'user'
    elif model_name == 'Organization':
        return 'organ'
    else:
        return 'unknown'

def is_user():
    return get_user_type() == 'user'

def is_organ():
    return get_user_type() == 'organ'


def get_current_user_info():
    """الحصول على معلومات كاملة عن المستخدم الحالي"""
    if not current_user.is_authenticated:
        return {'type': 'anonymous', 'user': None}
    
    user_info = {
        'id': current_user.id,
        'username': getattr(current_user, 'username', 'Unknown'),
        'name': getattr(current_user, 'name', 'Unknown')
    }
    
    if is_user():
        user_info.update({
            'type': 'user',
            'branch_id': current_user.branch_id,
            'permissions': [p.name for p in current_user.permissions]
        })
    elif is_organ():
        user_info.update({
            'type': 'representative',
            'user_id': current_user.user_id,
            'phone': getattr(current_user, 'phone', ''),
            'permissions': [p.name for p in current_user.permissions]
        })
    
    
    return user_info

def require_user_type(allowed_types):
    """ديكوراتور للتحقق من نوع المستخدم"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_type = get_user_type()
            if user_type not in allowed_types:
                flash('⚠️ غير مسموح بالوصول لهذه الصفحة', 'danger')
                return redirect(url_for('admin.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator
"""
platform_routes.py - مسارات لوحة تحكم المنصة (SaaS Management)
إدارة كاملة للمنصة مثل باقي المنصات
"""

from ..extensions import db
from flask import render_template, request, redirect, url_for, flash, jsonify, g, send_file
from flask_login import login_required, current_user
from app.models import PlatformAdmin, Organization, User, Subscription, PlatformOwner,PlatformAuditLog,SubscriptionPlan,PlatformNotification
from app.routes import platform_bp
from datetime import datetime, timedelta
from functools import wraps
from sqlalchemy import func, and_, or_
import pandas as pd
from io import BytesIO
import hashlib
import hmac
import json
from app.decorators import platform_admin_required, super_admin_required, role_required
# ============================================
# دوال التحقق من الصلاحيات
# ============================================

def platform_admin_required(f):
    """التحقق من أن المستخدم مدير منصة"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        # التحقق من أن المستخدم هو مدير منصة (super_admin أو admin)
        if not hasattr(current_user, 'role') or current_user.role not in ['super_admin', 'admin', 'support']:
            flash('غير مصرح بالوصول إلى لوحة تحكم المنصة', 'danger')
            return redirect(url_for('auth.login'))
        
        # التحقق من أن الحساب نشط
        if hasattr(current_user, 'is_active') and not current_user.is_active:
            flash('حسابك معطل، يرجى التواصل مع مدير المنصة', 'danger')
            return redirect(url_for('auth.login'))
        
        return f(*args, **kwargs)
    return decorated_function

def super_admin_required(f):
    """التحقق من أن المستخدم هو مشرف عام (Super Admin)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        if not hasattr(current_user, 'role') or current_user.role != 'super_admin':
            flash('غير مصرح بالوصول - هذه الصفحة للمشرف العام فقط', 'danger')
            return redirect(url_for('platform.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# قبل كل طلب
# ============================================

@platform_bp.before_request
def load_platform_data():
    """تحميل بيانات المنصة قبل كل طلب"""
    if current_user.is_authenticated and hasattr(current_user, 'role') and current_user.role in ['super_admin', 'admin', 'support']:
        g.platform = PlatformOwner.query.first()
        g.user_role = current_user.role
        g.is_super_admin = current_user.role == 'super_admin'
        
        # إحصائيات سريعة للـ navbar
        g.total_companies = Organization.query.count()
        g.total_users = User.query.count()
        g.pending_companies = Organization.query.filter_by(is_verified=False).count()
        g.expiring_subscriptions = Subscription.query.filter(
            Subscription.end_date <= datetime.now() + timedelta(days=7),
            Subscription.end_date > datetime.now(),
            Subscription.status == 'active'
        ).count()


# ============================================
# لوحة تحكم المنصة الرئيسية (Dashboard)
# ============================================

@platform_bp.route('/')
@login_required
@platform_admin_required
def dashboard():
    """لوحة تحكم المنصة الرئيسية - Dashboard متقدم"""
    
    # ============================================
    # إحصائيات عامة
    # ============================================
    
    total_companies = Organization.query.count()
    active_companies = Organization.query.filter_by(is_active=True).count()
    inactive_companies = Organization.query.filter_by(is_active=False).count()
    trial_companies = Organization.query.filter_by(subscription_status='trial').count()
    expired_companies = Organization.query.filter(
        Organization.subscription_status == 'expired'
    ).count()
    
    total_users = User.query.count()
    active_users = User.query.filter_by(is_user_active=True).count()
    inactive_users = User.query.filter_by(is_user_active=False).count()
    
    total_platform_admins = PlatformAdmin.query.count()
    
    # ============================================
    # إحصائيات اليوم
    # ============================================
    
    today = datetime.now().date()
    start_of_today = datetime.combine(today, datetime.min.time())
    
    new_companies_today = Organization.query.filter(
        Organization.created_at >= start_of_today
    ).count()
    
    new_users_today = User.query.filter(
        User.created_at >= start_of_today
    ).count()
    
    # ============================================
    # إحصائيات الاشتراكات
    # ============================================
    
    total_revenue = db.session.query(db.func.sum(Subscription.amount)).filter_by(status='active').scalar() or 0
    total_revenue_all = db.session.query(db.func.sum(Subscription.amount)).scalar() or 0
    active_subscriptions = Subscription.query.filter_by(status='active').count()
    trial_subscriptions = Subscription.query.filter_by(plan='trial').count()
    
    # الاشتراكات المنتهية قريباً
    expiring_soon = Subscription.query.filter(
        Subscription.end_date <= datetime.now() + timedelta(days=7),
        Subscription.end_date > datetime.now(),
        Subscription.status == 'active'
    ).count()
    
    # الإيرادات الشهرية (آخر 6 أشهر)
    monthly_revenue = []
    for i in range(5, -1, -1):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1)
        
        revenue = db.session.query(db.func.sum(Subscription.amount)).filter(
            Subscription.created_at >= month_start,
            Subscription.created_at < month_end,
            Subscription.status == 'active'
        ).scalar() or 0
        
        monthly_revenue.append({
            'month': month_date.strftime('%b %Y'),
            'revenue': revenue
        })
    
    # ============================================
    # نمو الشركات (آخر 6 أشهر)
    # ============================================
    
    companies_growth = []
    for i in range(5, -1, -1):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1)
        
        count = Organization.query.filter(
            Organization.created_at >= month_start,
            Organization.created_at < month_end
        ).count()
        
        companies_growth.append({
            'month': month_date.strftime('%b %Y'),
            'count': count
        })
    
    # ============================================
    # إحصائيات حسب الخطة
    # ============================================
    
    subscriptions_by_plan = db.session.query(
        Subscription.plan,
        db.func.count(Subscription.id).label('count'),
        db.func.sum(Subscription.amount).label('revenue')
    ).group_by(Subscription.plan).all()
    
    plans_stats = []
    for plan in subscriptions_by_plan:
        plans_stats.append({
            'name': plan[0],
            'count': plan[1],
            'revenue': float(plan[2] or 0)
        })
    
    # ============================================
    # آخر النشاطات
    # ============================================
    
    recent_companies = Organization.query.order_by(
        Organization.created_at.desc()
    ).limit(10).all()
    
    recent_users = User.query.order_by(
        User.created_at.desc()
    ).limit(10).all()
    
    recent_admins = PlatformAdmin.query.order_by(
        PlatformAdmin.created_at.desc()
    ).limit(5).all()
    
    # ============================================
    # أكثر الشركات استخداماً
    # ============================================
    
    top_companies = Organization.query.order_by(
        Organization.current_users.desc()
    ).limit(5).all()
    
    # ============================================
    # إحصائيات التخزين
    # ============================================
    
    total_storage = db.session.query(db.func.sum(Organization.storage_used_mb)).scalar() or 0
    total_storage_limit = db.session.query(db.func.sum(Organization.storage_limit_mb)).scalar() or 0
    
    # ============================================
    # تجميع الإحصائيات
    # ============================================
    
    stats = {
        'companies': {
            'total': total_companies,
            'active': active_companies,
            'inactive': inactive_companies,
            'trial': trial_companies,
            'expired': expired_companies,
            'new_today': new_companies_today
        },
        'users': {
            'total': total_users,
            'active': active_users,
            'inactive': inactive_users,
            'new_today': new_users_today
        },
        'admins': {
            'total': total_platform_admins
        },
        'subscriptions': {
            'total_revenue': total_revenue,
            'total_revenue_all': total_revenue_all,
            'active': active_subscriptions,
            'trial': trial_subscriptions,
            'expiring_soon': expiring_soon
        },
        'storage': {
            'used_gb': round(total_storage / 1024, 2),
            'limit_gb': round(total_storage_limit / 1024, 2),
            'usage_percent': round((total_storage / total_storage_limit * 100), 1) if total_storage_limit > 0 else 0
        }
    }
    
    return render_template('platform/dashboard.html',
                         stats=stats,
                         monthly_revenue=monthly_revenue,
                         companies_growth=companies_growth,
                         plans_stats=plans_stats,
                         recent_companies=recent_companies,
                         recent_users=recent_users,
                         recent_admins=recent_admins,
                         top_companies=top_companies,
                         now=datetime.now())


# ============================================
# إدارة الشركات (Companies Management)
# ============================================

@platform_bp.route('/companies')
@login_required
@platform_admin_required
def companies():
    """قائمة الشركات مع إمكانية البحث والتصفية"""
    
    # معاملات التصفية
    status = request.args.get('status', 'all')
    subscription = request.args.get('subscription', 'all')
    search = request.args.get('search', '')
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    sort_by = request.args.get('sort', 'created_at')
    sort_order = request.args.get('order', 'desc')
    per_page = request.args.get('per_page', 20, type=int)
    page = request.args.get('page', 1, type=int)
    
    query = Organization.query
    
    # فلتر الحالة
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)
    
    # فلتر الاشتراك
    if subscription != 'all':
        query = query.filter_by(subscription_status=subscription)
    
    # فلتر البحث
    if search:
        query = query.filter(
            or_(
                Organization.name.ilike(f'%{search}%'),
                Organization.email.ilike(f'%{search}%'),
                Organization.org_code.ilike(f'%{search}%'),
                Organization.phone.ilike(f'%{search}%')
            )
        )
    
    # فلتر التاريخ
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(Organization.created_at >= from_date)
        except:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(Organization.created_at <= to_date)
        except:
            pass
    
    # الترتيب
    if sort_by == 'name':
        order_col = Organization.name
    elif sort_by == 'users':
        order_col = Organization.current_users
    elif sort_by == 'projects':
        order_col = Organization.current_projects
    elif sort_by == 'created_at':
        order_col = Organization.created_at
    else:
        order_col = Organization.created_at
    
    if sort_order == 'asc':
        query = query.order_by(order_col.asc())
    else:
        query = query.order_by(order_col.desc())
    
    # Pagination
    companies = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # إحصائيات سريعة
    stats = {
        'total': Organization.query.count(),
        'active': Organization.query.filter_by(is_active=True).count(),
        'inactive': Organization.query.filter_by(is_active=False).count(),
        'trial': Organization.query.filter_by(subscription_status='trial').count(),
        'active_subscriptions': Organization.query.filter_by(subscription_status='active').count(),
        'expired': Organization.query.filter_by(subscription_status='expired').count(),
        'pending_verification': Organization.query.filter_by(is_verified=False).count()
    }
    
    return render_template('platform/companies/index.html',
                         companies=companies,
                         stats=stats,
                         filters={
                             'status': status,
                             'subscription': subscription,
                             'search': search,
                             'from': date_from,
                             'to': date_to,
                             'sort': sort_by,
                             'order': sort_order
                         },
                         per_page=per_page,
                         now=datetime.now())


@platform_bp.route('/companies/<int:company_id>')
@login_required
@platform_admin_required
def view_company(company_id):
    """عرض تفاصيل الشركة"""
    
    company = Organization.query.get_or_404(company_id)
    
    # إحصائيات الشركة
    users = User.query.filter_by(org_id=company_id).all()
    subscriptions = Subscription.query.filter_by(org_id=company_id).order_by(Subscription.created_at.desc()).all()
    
    # إحصائيات المشاريع
    from app.models.project_models import Project
    projects = Project.query.filter_by(org_id=company_id).all()
    
    # إحصائيات الاستخدام
    usage_stats = {
        'total_users': len(users),
        'active_users': len([u for u in users if u.is_user_active]),
        'total_projects': len(projects),
        'max_projects': company.max_projects,
        'storage_used_mb': company.storage_used_mb,
        'storage_limit_mb': company.storage_limit_mb,
        'storage_percent': round((company.storage_used_mb / company.storage_limit_mb * 100), 1) if company.storage_limit_mb > 0 else 0,
        'users_percent': round((len(users) / company.max_users * 100), 1) if company.max_users > 0 else 0,
        'projects_percent': round((len(projects) / company.max_projects * 100), 1) if company.max_projects > 0 else 0
    }
    
    # نشاط الشركة (آخر 30 يوماً)
    thirty_days_ago = datetime.now() - timedelta(days=30)
    recent_activity = {
        'new_users': User.query.filter(User.org_id == company_id, User.created_at >= thirty_days_ago).count(),
        'new_projects': Project.query.filter(Project.org_id == company_id, Project.created_at >= thirty_days_ago).count()
    }
    
    return render_template('platform/companies/view.html',
                         company=company,
                         users=users,
                         subscriptions=subscriptions,
                         projects=projects,
                         usage_stats=usage_stats,
                         recent_activity=recent_activity,
                         now=datetime.now())


# أضف هذه الدوال في نهاية platform_routes.py

@platform_bp.route('/companies/create', methods=['POST'])
@login_required
@platform_admin_required
def create_company():
    """إنشاء شركة جديدة"""
    try:
        # التحقق من عدم تكرار البريد
        if Organization.query.filter_by(email=request.form.get('email')).first():
            return jsonify({'success': False, 'error': 'البريد الإلكتروني موجود مسبقاً'}), 400
        
        # إنشاء كود فريد للشركة
        import random
        import string
        org_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # الحصول على الخطة الافتراضية
        default_plan = get_default_plan()
        
        company = Organization(
            org_code=org_code,
            name=request.form.get('name'),
            name_ar=request.form.get('name_ar'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            website=request.form.get('website'),
            address=request.form.get('address'),
            tax_number=request.form.get('tax_number'),
            commercial_register=request.form.get('commercial_register'),
            max_users=default_plan.get('max_users', 50),
            max_projects=default_plan.get('max_projects', 100),
            storage_limit_mb=default_plan.get('storage_gb', 10) * 1024,
            subscription_status='trial',
            trial_end=datetime.now() + timedelta(days=30),
            is_active=True,
            is_verified=False
        )
        company.password = request.form.get('password', 'Password123!')
        
        db.session.add(company)
        db.session.flush()
        
        # إنشاء المستخدم المدير
        admin = User(
            org_id=company.id,
            username=request.form.get('email').split('@')[0],
            email=request.form.get('email'),
            full_name=request.form.get('name'),
            role='org_admin',
            is_user_active=True,
            is_verified=True
        )
        admin.set_password(request.form.get('password', 'Password123!'))
        
        db.session.add(admin)
        
        # إنشاء اشتراك تجريبي
        subscription = Subscription(
            org_id=company.id,
            plan='trial',
            plan_name='تجريبي',
            amount=0,
            currency='SAR',
            status='trial',
            start_date=datetime.now(),
            end_date=datetime.now() + timedelta(days=30)
        )
        db.session.add(subscription)
        
        db.session.commit()
        
        log_platform_activity('create_company', company.id, f'إنشاء شركة جديدة: {company.name}')
        
        return jsonify({'success': True, 'message': 'تم إنشاء الشركة بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@platform_bp.route('/companies/<int:company_id>/edit', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def edit_company(company_id):
    """تعديل بيانات الشركة"""
    company = Organization.query.get_or_404(company_id)
    
    if request.method == 'POST':
        try:
            company.name = request.form.get('name', company.name)
            company.name_ar = request.form.get('name_ar', company.name_ar)
            company.phone = request.form.get('phone', company.phone)
            company.website = request.form.get('website', company.website)
            company.address = request.form.get('address', company.address)
            company.tax_number = request.form.get('tax_number', company.tax_number)
            company.commercial_register = request.form.get('commercial_register', company.commercial_register)
            company.max_users = int(request.form.get('max_users', company.max_users))
            company.max_projects = int(request.form.get('max_projects', company.max_projects))
            company.storage_limit_mb = int(request.form.get('storage_limit_mb', company.storage_limit_mb))
            company.is_active = 'is_active' in request.form
            company.is_verified = 'is_verified' in request.form
            
            db.session.commit()
            
            log_platform_activity('edit_company', company.id, f'تعديل بيانات الشركة: {company.name}')
            
            flash('تم تحديث بيانات الشركة بنجاح', 'success')
            return redirect(url_for('platform.view_company', company_id=company.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # جلب الخطط المتاحة للتعديل
    available_plans = get_available_plans()
    
    return render_template('platform/companies/edit.html', 
                         company=company, 
                         available_plans=available_plans,
                         now=datetime.now())

@platform_bp.route('/companies/<int:company_id>/toggle-status', methods=['POST'])
@login_required
@platform_admin_required
def toggle_company_status(company_id):
    """تفعيل/تعطيل الشركة"""
    
    company = Organization.query.get_or_404(company_id)
    company.is_active = not company.is_active
    db.session.commit()
    
    status = 'مفعلة' if company.is_active else 'معطلة'
    
    # تسجيل النشاط
    log_platform_activity('toggle_company_status', company.id, f'تم {status} الشركة {company.name}')
    
    return jsonify({'success': True, 'message': f'تم {status} الشركة بنجاح'})


@platform_bp.route('/companies/<int:company_id>/verify', methods=['POST'])
@login_required
@platform_admin_required
def verify_company(company_id):
    """الموافقة على تسجيل الشركة"""
    
    company = Organization.query.get_or_404(company_id)
    company.is_verified = True
    db.session.commit()
    
    # تسجيل النشاط
    log_platform_activity('verify_company', company.id, f'تم الموافقة على تسجيل الشركة {company.name}')
    
    # ✅ إشعار بطلب توثيق شركة (يمكن إرساله لمديري المنصة الآخرين)
    from app.services.platform_notification_service import PlatformNotificationService
    PlatformNotificationService.company_verification_request(company)
    
    return jsonify({'success': True, 'message': 'تم الموافقة على تسجيل الشركة بنجاح'})


@platform_bp.route('/companies/<int:company_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_company(company_id):
    """حذف الشركة (للمشرف العام فقط)"""
    
    company = Organization.query.get_or_404(company_id)
    company_name = company.name
    
    try:
        # حذف جميع المستخدمين
        User.query.filter_by(org_id=company_id).delete()
        # حذف الاشتراكات
        Subscription.query.filter_by(org_id=company_id).delete()
        # حذف الشركة
        db.session.delete(company)
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('delete_company', company_id, f'حذف الشركة {company_name}')
        
        return jsonify({'success': True, 'message': 'تم حذف الشركة وجميع بياناتها بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة الاشتراكات (Subscriptions Management)
# ============================================

@platform_bp.route('/subscriptions')
@login_required
@platform_admin_required
def subscriptions():
    """إدارة الاشتراكات"""
    
    # معاملات التصفية
    plan_filter = request.args.get('plan', 'all')
    status_filter = request.args.get('status', 'all')
    search = request.args.get('search', '')
    
    query = Subscription.query
    
    if plan_filter != 'all':
        query = query.filter_by(plan=plan_filter)
    
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    if search:
        query = query.join(Organization).filter(
            or_(
                Organization.name.ilike(f'%{search}%'),
                Organization.email.ilike(f'%{search}%')
            )
        )
    
    subscriptions_list = query.order_by(Subscription.created_at.desc()).all()
    
    # إحصائيات الاشتراكات
    stats = {
        'total_revenue': db.session.query(db.func.sum(Subscription.amount)).scalar() or 0,
        'active_count': Subscription.query.filter_by(status='active').count(),
        'trial_count': Subscription.query.filter_by(plan='trial').count(),
        'expiring_soon': Subscription.query.filter(
            Subscription.end_date <= datetime.now() + timedelta(days=7),
            Subscription.end_date > datetime.now(),
            Subscription.status == 'active'
        ).count(),
        'expired': Subscription.query.filter(
            Subscription.end_date <= datetime.now(),
            Subscription.status == 'active'
        ).count()
    }
    
    # خطط الاشتراك المتاحة
    available_plans = get_available_plans()
    
    return render_template('platform/subscriptions/index.html',
                         subscriptions=subscriptions_list,
                         stats=stats,
                         available_plans=available_plans,
                         filters={'plan': plan_filter, 'status': status_filter, 'search': search},
                         now=datetime.now())


@platform_bp.route('/subscriptions/create', methods=['POST'])
@login_required
@platform_admin_required
def create_subscription():
    """إنشاء اشتراك جديد لشركة"""
    
    data = request.get_json()
    
    try:
        company = Organization.query.get(data.get('company_id'))
        if not company:
            return jsonify({'success': False, 'error': 'الشركة غير موجودة'}), 404
        
        # تحديد تاريخ الانتهاء
        plan = data.get('plan')
        duration_months = data.get('duration_months', 12)
        end_date = datetime.now() + timedelta(days=duration_months * 30)
        
        # حساب السعر
        amount = calculate_plan_price(plan, duration_months)
        
        subscription = Subscription(
            org_id=company.id,
            plan=plan,
            plan_name=data.get('plan_name', plan),
            amount=amount,
            currency=data.get('currency', 'SAR'),
            payment_method=data.get('payment_method', 'manual'),
            status='active',
            start_date=datetime.now(),
            end_date=end_date,
            auto_renew=data.get('auto_renew', True),
            created_by=current_user.id
        )
        
        db.session.add(subscription)
        
        # تحديث حالة الشركة
        company.subscription_status = 'active'
        company.subscription_end = end_date
        
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('create_subscription', company.id, f'إنشاء اشتراك {plan} للشركة {company.name}')
        
        return jsonify({'success': True, 'message': 'تم إنشاء الاشتراك بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@platform_bp.route('/subscriptions/<int:sub_id>/cancel', methods=['POST'])
@login_required
@platform_admin_required
def cancel_subscription(sub_id):
    """إلغاء اشتراك"""
    
    subscription = Subscription.query.get_or_404(sub_id)
    
    try:
        subscription.status = 'cancelled'
        subscription.auto_renew = False
        
        # تحديث حالة الشركة
        company = Organization.query.get(subscription.org_id)
        if company:
            company.subscription_status = 'expired'
        
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('cancel_subscription', sub_id, f'إلغاء اشتراك الشركة {company.name if company else "غير معروف"}')
        
        return jsonify({'success': True, 'message': 'تم إلغاء الاشتراك بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@platform_bp.route('/subscriptions/<int:sub_id>/renew', methods=['POST'])
@login_required
@platform_admin_required
def renew_subscription(sub_id):
    """تجديد اشتراك"""
    
    subscription = Subscription.query.get_or_404(sub_id)
    data = request.get_json()
    
    try:
        duration_months = data.get('duration_months', 12)
        new_end_date = datetime.now() + timedelta(days=duration_months * 30)
        
        # إنشاء اشتراك جديد
        new_subscription = Subscription(
            org_id=subscription.org_id,
            plan=subscription.plan,
            plan_name=subscription.plan_name,
            amount=calculate_plan_price(subscription.plan, duration_months),
            currency=subscription.currency,
            payment_method=data.get('payment_method', subscription.payment_method),
            status='active',
            start_date=datetime.now(),
            end_date=new_end_date,
            auto_renew=data.get('auto_renew', True),
            created_by=current_user.id
        )
        
        db.session.add(new_subscription)
        
        # تحديث الاشتراك القديم
        subscription.status = 'expired'
        
        # تحديث حالة الشركة
        company = Organization.query.get(subscription.org_id)
        if company:
            company.subscription_status = 'active'
            company.subscription_end = new_end_date
        
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('renew_subscription', sub_id, f'تجديد اشتراك الشركة {company.name if company else "غير معروف"}')
        
        return jsonify({'success': True, 'message': 'تم تجديد الاشتراك بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة خطط الاشتراك (Plans Management)
# ============================================

# @platform_bp.route('/plans')
# @login_required
# @super_admin_required
# def plans():
#     """إدارة خطط الاشتراك (للمشرف العام فقط)"""
    
#     # قراءة الخطط من قاعدة البيانات أو من ملف الإعدادات
#     plans = get_available_plans()
    
#     return render_template('platform/plans/index.html', plans=plans, now=datetime.now())




# ============================================
# دوال API الإضافية
# ============================================

@platform_bp.route('/api/dashboard/recent-activities')
@login_required
@platform_admin_required
def api_recent_activities():
    """API للحصول على آخر النشاطات"""
    limit = request.args.get('limit', 10, type=int)
    
    logs = PlatformAuditLog.query.order_by(PlatformAuditLog.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'success': True,
        'activities': [{
            'id': log.id,
            'action': log.action,
            'admin_name': log.admin_name,
            'details': log.details,
            'time_ago': time_ago(log.created_at),
            'created_at': log.created_at.isoformat()
        } for log in logs]
    })


@platform_bp.route('/api/companies/<int:company_id>/stats')
@login_required
@platform_admin_required
def api_company_stats(company_id):
    """API لإحصائيات شركة محددة"""
    company = Organization.query.get_or_404(company_id)
    
    users = User.query.filter_by(org_id=company_id).all()
    from app.models.project_models import Project
    projects = Project.query.filter_by(org_id=company_id).all()
    
    return jsonify({
        'success': True,
        'stats': {
            'users': {
                'total': len(users),
                'active': len([u for u in users if u.is_user_active]),
                'by_role': {
                    'org_admin': len([u for u in users if u.role == 'org_admin']),
                    'project_manager': len([u for u in users if u.role == 'project_manager']),
                    'employee': len([u for u in users if u.role == 'employee'])
                }
            },
            'projects': {
                'total': len(projects),
                'active': len([p for p in projects if p.status == 'active']),
                'completed': len([p for p in projects if p.status == 'completed'])
            },
            'storage': {
                'used_mb': company.storage_used_mb,
                'limit_mb': company.storage_limit_mb,
                'percent': round((company.storage_used_mb / company.storage_limit_mb * 100), 1) if company.storage_limit_mb > 0 else 0
            }
        }
    })


@platform_bp.route('/api/export-all-data')
@login_required
@super_admin_required
def export_all_data():
    """تصدير جميع بيانات المنصة (للمشرف العام فقط)"""
    try:
        # تصدير الشركات
        companies = Organization.query.all()
        companies_data = [{
            'name': c.name,
            'email': c.email,
            'phone': c.phone,
            'status': c.subscription_status,
            'users_count': c.current_users,
            'created_at': c.created_at.strftime('%Y-%m-%d %H:%M:%S') if c.created_at else ''
        } for c in companies]
        
        # تصدير المستخدمين
        users = User.query.all()
        users_data = [{
            'name': u.full_name,
            'email': u.email,
            'role': u.role,
            'company': u.organization.name if u.organization else '',
            'status': 'active' if u.is_user_active else 'inactive',
            'created_at': u.created_at.strftime('%Y-%m-%d %H:%M:%S') if u.created_at else ''
        } for u in users]
        
        # تصدير الاشتراكات
        subscriptions = Subscription.query.all()
        subscriptions_data = [{
            'company': s.organization.name if s.organization else '',
            'plan': s.plan,
            'amount': s.amount,
            'status': s.status,
            'start_date': s.start_date.strftime('%Y-%m-%d') if s.start_date else '',
            'end_date': s.end_date.strftime('%Y-%m-%d') if s.end_date else ''
        } for s in subscriptions]
        
        # إنشاء ملف Excel واحد
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame(companies_data).to_excel(writer, sheet_name='Companies', index=False)
            pd.DataFrame(users_data).to_excel(writer, sheet_name='Users', index=False)
            pd.DataFrame(subscriptions_data).to_excel(writer, sheet_name='Subscriptions', index=False)
        
        output.seek(0)
        
        log_platform_activity('export_all_data', None, 'تصدير جميع بيانات المنصة')
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'platform_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# دالة الوقت المنقضي (Time Ago)
# ============================================

def time_ago(dt):
    """حساب الوقت المنقضي"""
    if not dt:
        return ''
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days > 365:
        return f'منذ {diff.days // 365} سنة'
    elif diff.days > 30:
        return f'منذ {diff.days // 30} شهر'
    elif diff.days > 0:
        return f'منذ {diff.days} يوم'
    elif diff.seconds > 3600:
        return f'منذ {diff.seconds // 3600} ساعة'
    elif diff.seconds > 60:
        return f'منذ {diff.seconds // 60} دقيقة'
    else:
        return 'منذ لحظات'
    
@platform_bp.route('/plans/<plan_id>/update', methods=['POST'])
@login_required
@super_admin_required
def update_plan(plan_id):
    """تحديث خطة اشتراك"""
    
    data = request.get_json()
    
    try:
        update_plan_data(plan_id, data)
        
        return jsonify({'success': True, 'message': 'تم تحديث الخطة بنجاح'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500





# ============================================
# إدارة مدراء المنصة (Platform Admins Management)
# ============================================

@platform_bp.route('/admins')
@login_required
@platform_admin_required
def admins():
    """إدارة مدراء المنصة"""
    
    platform = PlatformOwner.query.first()
    if not platform:
        flash('لم يتم العثور على المنصة', 'danger')
        return redirect(url_for('platform.dashboard'))
    
    admins_list = PlatformAdmin.query.filter_by(platform_id=platform.id).all()
    
    # إحصائيات الأدمن
    stats = {
        'total': len(admins_list),
        'super_admins': len([a for a in admins_list if a.role == 'super_admin']),
        'admins': len([a for a in admins_list if a.role == 'admin']),
        'support': len([a for a in admins_list if a.role == 'support']),
        'active': len([a for a in admins_list if a.is_active])
    }
    
    return render_template('platform/admins/index.html', admins=admins_list, stats=stats, now=datetime.now())


@platform_bp.route('/admins/create', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_admin():
    """إنشاء مدير منصة جديد (للمشرف العام فقط)"""
    
    if request.method == 'POST':
        try:
            platform = PlatformOwner.query.first()
            if not platform:
                flash('لم يتم العثور على المنصة', 'danger')
                return redirect(url_for('platform.admins'))
            
            # التحقق من عدم تكرار البريد
            if PlatformAdmin.query.filter_by(email=request.form.get('email')).first():
                flash('البريد الإلكتروني موجود مسبقاً', 'danger')
                return redirect(url_for('platform.create_admin'))
            
            admin = PlatformAdmin(
                platform_id=platform.id,
                username=request.form.get('username'),
                email=request.form.get('email'),
                full_name=request.form.get('full_name'),
                full_name_ar=request.form.get('full_name_ar'),
                phone=request.form.get('phone'),
                role=request.form.get('role', 'admin'),
                is_active=True
            )
            admin.set_password(request.form.get('password', 'Admin123!'))
            
            db.session.add(admin)
            db.session.commit()
            
            # تسجيل النشاط
            log_platform_activity('create_admin', admin.id, f'إنشاء مدير منصة جديد: {admin.full_name}')
            
            flash('تم إنشاء مدير منصة جديد بنجاح', 'success')
            return redirect(url_for('platform.admins'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('platform/admins/create.html', now=datetime.now())


# أضف هذه الدوال في نهاية platform_routes.py

@platform_bp.route('/admins/<int:admin_id>/edit', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_admin(admin_id):
    """تعديل بيانات مدير المنصة (للمشرف العام فقط)"""
    admin = PlatformAdmin.query.get_or_404(admin_id)
    
    # منع تعديل حساب المشرف العام من قبل شخص آخر
    if admin.role == 'super_admin' and current_user.id != admin.id:
        flash('لا يمكن تعديل بيانات المشرف العام', 'danger')
        return redirect(url_for('platform.admins'))
    
    if request.method == 'POST':
        try:
            admin.full_name = request.form.get('full_name', admin.full_name)
            admin.full_name_ar = request.form.get('full_name_ar', admin.full_name_ar)
            admin.phone = request.form.get('phone', admin.phone)
            admin.is_active = request.form.get('is_active') == '1'
            
            # تحديث الدور (فقط المشرف العام يمكنه تغيير أدوار الآخرين)
            if current_user.role == 'super_admin' and admin.id != current_user.id:
                new_role = request.form.get('role')
                if new_role in ['super_admin', 'admin', 'support', 'finance']:
                    admin.role = new_role
            
            # تغيير كلمة المرور
            new_password = request.form.get('new_password')
            if new_password:
                admin.set_password(new_password)
            
            db.session.commit()
            
            log_platform_activity('edit_admin', admin.id, f'تعديل بيانات مدير المنصة: {admin.full_name}')
            
            return jsonify({'success': True, 'message': 'تم تحديث بيانات المدير بنجاح'})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    return render_template('platform/admins/edit.html', admin=admin, now=datetime.now())

@platform_bp.route('/admins/<int:admin_id>/toggle-status', methods=['POST'])
@login_required
@super_admin_required
def toggle_admin_status(admin_id):
    """تفعيل/تعطيل مدير منصة (للمشرف العام فقط)"""
    
    admin = PlatformAdmin.query.get_or_404(admin_id)
    
    # منع تعطيل المشرف العام
    if admin.role == 'super_admin':
        return jsonify({'success': False, 'error': 'لا يمكن تعطيل المشرف العام'}), 400
    
    # منع تعطيل الحساب الخاص
    if admin.id == current_user.id:
        return jsonify({'success': False, 'error': 'لا يمكن تعطيل حسابك الخاص'}), 400
    
    admin.is_active = not admin.is_active
    db.session.commit()
    
    status = 'مفعل' if admin.is_active else 'معطل'
    
    # تسجيل النشاط
    log_platform_activity('toggle_admin_status', admin.id, f'تم {status} مدير المنصة: {admin.full_name}')
    
    return jsonify({'success': True, 'message': f'تم {status} المدير بنجاح'})


@platform_bp.route('/admins/<int:admin_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_admin(admin_id):
    """حذف مدير منصة (للمشرف العام فقط)"""
    
    admin = PlatformAdmin.query.get_or_404(admin_id)
    
    # منع حذف المشرف العام
    if admin.role == 'super_admin':
        return jsonify({'success': False, 'error': 'لا يمكن حذف المشرف العام'}), 400
    
    # منع حذف الحساب الخاص
    if admin.id == current_user.id:
        return jsonify({'success': False, 'error': 'لا يمكن حذف حسابك الخاص'}), 400
    
    admin_name = admin.full_name
    
    try:
        db.session.delete(admin)
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('delete_admin', admin_id, f'حذف مدير المنصة: {admin_name}')
        
        return jsonify({'success': True, 'message': 'تم حذف المدير بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة الملف الشخصي للمشرف
# ============================================

@platform_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def profile():
    """الملف الشخصي لمدير المنصة"""
    
    if request.method == 'POST':
        try:
            current_user.full_name = request.form.get('full_name', current_user.full_name)
            current_user.full_name_ar = request.form.get('full_name_ar', current_user.full_name_ar)
            current_user.phone = request.form.get('phone', current_user.phone)
            
            # تغيير كلمة المرور
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if new_password:
                if not current_user.check_password(current_password):
                    flash('كلمة المرور الحالية غير صحيحة', 'danger')
                elif new_password != confirm_password:
                    flash('كلمة المرور الجديدة غير متطابقة', 'danger')
                elif len(new_password) < 8:
                    flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'danger')
                else:
                    current_user.set_password(new_password)
                    flash('تم تغيير كلمة المرور بنجاح', 'success')
            
            db.session.commit()
            flash('تم تحديث الملف الشخصي بنجاح', 'success')
            return redirect(url_for('platform.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('platform/profile/index.html', admin=current_user, now=datetime.now())


# ============================================
# الإحصائيات والتقارير المتقدمة
# ============================================

@platform_bp.route('/reports')
@login_required
@platform_admin_required
def reports():
    """لوحة التقارير المتقدمة"""
    
    # إحصائيات النمو
    growth_stats = {}
    
    # نمو الشركات
    companies_by_month = []
    for i in range(11, -1, -1):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1)
        
        new_companies = Organization.query.filter(
            Organization.created_at >= month_start,
            Organization.created_at < month_end
        ).count()
        
        companies_by_month.append({
            'month': month_date.strftime('%b %Y'),
            'new': new_companies
        })
    
    # نمو المستخدمين
    users_by_month = []
    for i in range(11, -1, -1):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1)
        
        new_users = User.query.filter(
            User.created_at >= month_start,
            User.created_at < month_end
        ).count()
        
        users_by_month.append({
            'month': month_date.strftime('%b %Y'),
            'new': new_users
        })
    
    # توزيع الشركات حسب الخطة
    companies_by_plan = db.session.query(
        Organization.subscription_status,
        db.func.count(Organization.id)
    ).group_by(Organization.subscription_status).all()
    
    # توزيع المستخدمين حسب الدور
    users_by_role = db.session.query(
        User.role,
        db.func.count(User.id)
    ).group_by(User.role).all()
    
    # توزيع الشركات حسب عدد المستخدمين
    companies_by_size = {
        'small': Organization.query.filter(Organization.current_users <= 10).count(),
        'medium': Organization.query.filter(Organization.current_users.between(11, 50)).count(),
        'large': Organization.query.filter(Organization.current_users > 50).count()
    }
    
    return render_template('platform/reports/index.html',
                         companies_by_month=companies_by_month,
                         users_by_month=users_by_month,
                         companies_by_plan=companies_by_plan,
                         users_by_role=users_by_role,
                         companies_by_size=companies_by_size,
                         now=datetime.now())


@platform_bp.route('/reports/export/<report_type>')
@login_required
@platform_admin_required
def export_report(report_type):
    """تصدير التقارير (Excel/CSV)"""
    
    export_format = request.args.get('format', 'excel')
    
    if report_type == 'companies':
        companies = Organization.query.all()
        data = [{
            'اسم الشركة': c.name,
            'البريد الإلكتروني': c.email,
            'كود الشركة': c.org_code,
            'عدد المستخدمين': c.current_users,
            'عدد المشاريع': c.current_projects,
            'حالة الاشتراك': c.subscription_status,
            'تاريخ التسجيل': c.created_at.strftime('%Y-%m-%d') if c.created_at else ''
        } for c in companies]
        
        df = pd.DataFrame(data)
        
    elif report_type == 'subscriptions':
        subscriptions_list = Subscription.query.all()
        data = [{
            'الشركة': s.organization.name if s.organization else '',
            'الخطة': s.plan,
            'المبلغ': s.amount,
            'العملة': s.currency,
            'الحالة': s.status,
            'تاريخ البداية': s.start_date.strftime('%Y-%m-%d') if s.start_date else '',
            'تاريخ النهاية': s.end_date.strftime('%Y-%m-%d') if s.end_date else ''
        } for s in subscriptions_list]
        
        df = pd.DataFrame(data)
        
    elif report_type == 'users':
        users = User.query.all()
        data = [{
            'الاسم': u.full_name,
            'البريد الإلكتروني': u.email,
            'الدور': u.role,
            'الشركة': u.organization.name if u.organization else '',
            'الحالة': 'نشط' if u.is_user_active else 'معطل',
            'تاريخ التسجيل': u.created_at.strftime('%Y-%m-%d') if u.created_at else ''
        } for u in users]
        
        df = pd.DataFrame(data)
        
    else:
        flash('نوع التقرير غير صالح', 'danger')
        return redirect(url_for('platform.reports'))
    
    # تصدير الملف
    if export_format == 'excel':
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Report')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'{report_type}_report_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
    
    else:  # csv
        output = BytesIO()
        df.to_csv(output, index=False, encoding='utf-8-sig')
        output.seek(0)
        
        return send_file(
            output,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{report_type}_report_{datetime.now().strftime("%Y%m%d")}.csv'
        )


# ============================================
# إعدادات المنصة المتقدمة
# ============================================

@platform_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def settings():
    """إعدادات المنصة المتقدمة"""
    
    platform = PlatformOwner.query.first()
    if not platform:
        flash('لم يتم العثور على المنصة', 'danger')
        return redirect(url_for('platform.dashboard'))
    
    if request.method == 'POST':
        try:
            # معلومات الشركة
            platform.company_name = request.form.get('company_name', platform.company_name)
            platform.company_name_ar = request.form.get('company_name_ar', platform.company_name_ar)
            platform.email = request.form.get('email', platform.email)
            platform.phone = request.form.get('phone', platform.phone)
            platform.address = request.form.get('address', platform.address)
            platform.website = request.form.get('website', platform.website)
            platform.tax_number = request.form.get('tax_number', platform.tax_number)
            platform.commercial_register = request.form.get('commercial_register', platform.commercial_register)
            
            # إعدادات النظام
            settings = platform.platform_settings or {}
            settings['allow_multi_companies'] = 'allow_multi_companies' in request.form
            settings['max_companies'] = int(request.form.get('max_companies', 100))
            settings['require_company_verification'] = 'require_company_verification' in request.form
            settings['allow_public_registration'] = 'allow_public_registration' in request.form
            settings['default_plan'] = request.form.get('default_plan', 'trial')
            settings['trial_days'] = int(request.form.get('trial_days', 30))
            settings['maintenance_mode'] = 'maintenance_mode' in request.form
            
            # إعدادات الاشتراك الافتراضية
            settings['default_company_quota'] = {
                'max_users': int(request.form.get('default_max_users', 50)),
                'max_projects': int(request.form.get('default_max_projects', 100)),
                'storage_gb': int(request.form.get('default_storage_gb', 10))
            }
            
            # إعدادات البريد
            settings['mail'] = {
                'smtp_server': request.form.get('smtp_server', ''),
                'smtp_port': int(request.form.get('smtp_port', 587)),
                'smtp_username': request.form.get('smtp_username', ''),
                'smtp_password': request.form.get('smtp_password', ''),
                'mail_from': request.form.get('mail_from', ''),
                'mail_from_name': request.form.get('mail_from_name', '')
            }
            
            # إعدادات الدفع
            settings['payment'] = {
                'stripe_public_key': request.form.get('stripe_public_key', ''),
                'stripe_secret_key': request.form.get('stripe_secret_key', ''),
                'currency': request.form.get('currency', 'SAR'),
                'tax_rate': float(request.form.get('tax_rate', 0))
            }
            
            platform.platform_settings = settings
            db.session.commit()
            
            # تسجيل النشاط
            log_platform_activity('update_settings', platform.id, 'تحديث إعدادات المنصة')
            
            flash('تم تحديث إعدادات المنصة بنجاح', 'success')
            return redirect(url_for('platform.settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('platform/settings/index.html', platform=platform, now=datetime.now())




def log_platform_activity(action, target_id=None, details=None, target_type=None):
    """تسجيل نشاط في سجل المنصة"""
    try:
        log = PlatformAuditLog(
            admin_id=current_user.id,
            admin_name=current_user.full_name,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', '')[:500]
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"خطأ في تسجيل النشاط: {e}")


@platform_bp.route('/audit-log')
@login_required
@super_admin_required
def audit_log():
    """سجل نشاطات المنصة (للمشرف العام فقط)"""
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    action_filter = request.args.get('action', '')
    admin_filter = request.args.get('admin', '')
    
    query = PlatformAuditLog.query
    
    if action_filter:
        query = query.filter(PlatformAuditLog.action == action_filter)
    
    if admin_filter:
        query = query.filter(PlatformAuditLog.admin_id == int(admin_filter))
    
    logs = query.order_by(PlatformAuditLog.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    
    # قائمة الإجراءات للفلترة
    actions = db.session.query(PlatformAuditLog.action).distinct().all()
    actions = [a[0] for a in actions]
    
    # قائمة المدراء للفلترة
    admins = PlatformAdmin.query.all()
    
    return render_template('platform/audit_log.html',
                         logs=logs,
                         actions=actions,
                         admins=admins,
                         now=datetime.now())


# ============================================
# دوال مساعدة (Helper Functions)
# ============================================

def get_available_plans():
    """الحصول على خطط الاشتراك المتاحة"""
    # يمكن قراءة هذا من قاعدة البيانات أو من ملف إعدادات
    return [
        {
            'id': 'free',
            'name': 'Free',
            'name_ar': 'مجاني',
            'price_monthly': 0,
            'price_yearly': 0,
            'max_users': 5,
            'max_projects': 3,
            'storage_gb': 1,
            'features': ['مستخدم واحد', 'مشروع واحد', 'تخزين 1 جيجابايت', 'دعم أساسي'],
            'is_active': True
        },
        {
            'id': 'basic',
            'name': 'Basic',
            'name_ar': 'أساسي',
            'price_monthly': 29,
            'price_yearly': 290,
            'max_users': 20,
            'max_projects': 10,
            'storage_gb': 10,
            'features': ['10 مشاريع', '20 مستخدم', 'تخزين 10 جيجابايت', 'دعم البريد الإلكتروني', 'تقارير أساسية'],
            'is_active': True
        },
        {
            'id': 'professional',
            'name': 'Professional',
            'name_ar': 'احترافي',
            'price_monthly': 79,
            'price_yearly': 790,
            'max_users': 100,
            'max_projects': 50,
            'storage_gb': 50,
            'features': ['50 مشروع', '100 مستخدم', 'تخزين 50 جيجابايت', 'دعم أولوية', 'تقارير متقدمة', 'API'],
            'is_active': True
        },
        {
            'id': 'enterprise',
            'name': 'Enterprise',
            'name_ar': 'شركات',
            'price_monthly': 199,
            'price_yearly': 1990,
            'max_users': -1,  # غير محدود
            'max_projects': -1,  # غير محدود
            'storage_gb': 200,
            'features': ['مشاريع غير محدودة', 'مستخدمين غير محدودين', 'تخزين 200 جيجابايت', 'دعم VIP', 'API مخصص', 'نشر خاص'],
            'is_active': True
        }
    ]


def calculate_plan_price(plan_id, duration_months):
    """حساب سعر الخطة بناءً على المدة"""
    plans = get_available_plans()
    for plan in plans:
        if plan['id'] == plan_id:
            if duration_months == 12:
                return plan.get('price_yearly', plan['price_monthly'] * 12)
            else:
                return plan['price_monthly'] * duration_months
    return 0

# ============================================
# إدارة خطط الاشتراك (Subscription Plans Management)
# ============================================

@platform_bp.route('/plans')
@login_required
@super_admin_required
def plans():
    """إدارة خطط الاشتراك (للمشرف العام فقط)"""
    
    # جلب جميع الخطط من قاعدة البيانات
    all_plans = SubscriptionPlan.query.order_by(SubscriptionPlan.display_order).all()
    
    # إحصائيات الخطط
    stats = {
        'total': len(all_plans),
        'active': len([p for p in all_plans if p.is_active]),
        'inactive': len([p for p in all_plans if not p.is_active]),
        'featured': len([p for p in all_plans if p.is_featured]),
        'default': next((p for p in all_plans if p.is_default), None)
    }
    
    return render_template('platform/plans/index.html', 
                         plans=all_plans, 
                         stats=stats,
                         now=datetime.now())


@platform_bp.route('/plans/create', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_plan():
    """إنشاء خطة اشتراك جديدة"""
    
    if request.method == 'POST':
        try:
            # التحقق من عدم وجود plan_id مكرر
            plan_id = request.form.get('plan_id')
            existing = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
            if existing:
                flash(f'معرف الخطة "{plan_id}" موجود مسبقاً', 'danger')
                return redirect(url_for('platform.create_plan'))
            
            # معالجة الميزات (Features)
            features = request.form.getlist('features[]')
            
            # إنشاء الخطة الجديدة
            plan = SubscriptionPlan(
                plan_id=plan_id,
                name=request.form.get('name'),
                description=request.form.get('description'),
                price_monthly=float(request.form.get('price_monthly', 0)),
                price_yearly=float(request.form.get('price_yearly', 0)),
                currency=request.form.get('currency', 'USD'),
                max_users=int(request.form.get('max_users', 0)),
                max_projects=int(request.form.get('max_projects', 0)),
                storage_gb=int(request.form.get('storage_gb', 0)),
                features=features,
                features_ar=features_ar,
                display_order=int(request.form.get('display_order', 0)),
                is_featured='is_featured' in request.form,
                is_active='is_active' in request.form,
                is_default='is_default' in request.form,
                created_by=current_user.id
            )
            
            # إذا كانت هذه الخطة هي الخطة الافتراضية، قم بإلغاء تحديد الخطط الأخرى
            if plan.is_default:
                SubscriptionPlan.query.update({SubscriptionPlan.is_default: False})
            
            db.session.add(plan)
            db.session.commit()
            
            # تسجيل النشاط
            log_platform_activity('create_plan', plan.id, f'إنشاء خطة جديدة: {plan.name}')
            
            flash('تم إنشاء الخطة بنجاح', 'success')
            return redirect(url_for('platform.plans'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('platform/plans/create.html', now=datetime.now())


@platform_bp.route('/plans/<int:plan_id>/edit', methods=['GET', 'POST'])
@login_required
@super_admin_required
def edit_plan(plan_id):
    """تعديل خطة اشتراك"""
    
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    
    if request.method == 'POST':
        try:
            # تحديث البيانات
            plan.name = request.form.get('name', plan.name)
            plan.description = request.form.get('description', plan.description)
            plan.price_monthly = float(request.form.get('price_monthly', plan.price_monthly))
            plan.price_yearly = float(request.form.get('price_yearly', plan.price_yearly))
            plan.currency = request.form.get('currency', plan.currency)
            plan.max_users = int(request.form.get('max_users', plan.max_users))
            plan.max_projects = int(request.form.get('max_projects', plan.max_projects))
            plan.storage_gb = int(request.form.get('storage_gb', plan.storage_gb))
            plan.features = request.form.getlist('features[]')
            plan.display_order = int(request.form.get('display_order', plan.display_order))
            plan.is_featured = 'is_featured' in request.form
            plan.is_active = 'is_active' in request.form
            
            # معالجة الخطة الافتراضية
            new_is_default = 'is_default' in request.form
            if new_is_default and not plan.is_default:
                # إلغاء تحديد أي خطة افتراضية أخرى
                SubscriptionPlan.query.update({SubscriptionPlan.is_default: False})
                plan.is_default = True
            elif not new_is_default:
                plan.is_default = False
            
            plan.updated_by = current_user.id
            plan.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # تسجيل النشاط
            log_platform_activity('edit_plan', plan.id, f'تعديل الخطة: {plan.name}')
            
            flash('تم تحديث الخطة بنجاح', 'success')
            return redirect(url_for('platform.plans'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('platform/plans/edit.html', plan=plan, now=datetime.now())


@platform_bp.route('/plans/<int:plan_id>/delete', methods=['POST'])
@login_required
@super_admin_required
def delete_plan(plan_id):
    """حذف خطة اشتراك"""
    
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    
    # التحقق من وجود شركات تستخدم هذه الخطة
    companies_using = Organization.query.filter_by(subscription_status=plan.plan_id).count()
    if companies_using > 0:
        return jsonify({
            'success': False, 
            'error': f'لا يمكن حذف الخطة لأن {companies_using} شركة تستخدمها حالياً'
        }), 400
    
    plan_name = plan.name
    
    try:
        db.session.delete(plan)
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('delete_plan', plan_id, f'حذف الخطة: {plan_name}')
        
        return jsonify({'success': True, 'message': 'تم حذف الخطة بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@platform_bp.route('/plans/<int:plan_id>/toggle-status', methods=['POST'])
@login_required
@super_admin_required
def toggle_plan_status(plan_id):
    """تفعيل/تعطيل خطة اشتراك"""
    
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    plan.is_active = not plan.is_active
    db.session.commit()
    
    status = 'مفعلة' if plan.is_active else 'معطلة'
    
    # تسجيل النشاط
    log_platform_activity('toggle_plan_status', plan.id, f'تم {status} الخطة: {plan.name}')
    
    return jsonify({'success': True, 'message': f'تم {status} الخطة بنجاح'})


@platform_bp.route('/plans/<int:plan_id>/set-default', methods=['POST'])
@login_required
@super_admin_required
def set_default_plan(plan_id):
    """تعيين خطة كخطة افتراضية"""
    
    plan = SubscriptionPlan.query.get_or_404(plan_id)
    
    try:
        # إلغاء تحديد أي خطة افتراضية حالية
        SubscriptionPlan.query.update({SubscriptionPlan.is_default: False})
        
        # تعيين الخطة الحالية كافتراضية
        plan.is_default = True
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('set_default_plan', plan.id, f'تعيين الخطة {plan.name} كخطة افتراضية')
        
        return jsonify({'success': True, 'message': 'تم تعيين الخطة كخطة افتراضية'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@platform_bp.route('/plans/reorder', methods=['POST'])
@login_required
@super_admin_required
def reorder_plans():
    """إعادة ترتيب الخطط"""
    
    data = request.get_json()
    plan_order = data.get('order', [])
    
    try:
        for index, plan_id in enumerate(plan_order):
            plan = SubscriptionPlan.query.get(plan_id)
            if plan:
                plan.display_order = index
        db.session.commit()
        
        # تسجيل النشاط
        log_platform_activity('reorder_plans', None, 'إعادة ترتيب خطط الاشتراك')
        
        return jsonify({'success': True, 'message': 'تم إعادة ترتيب الخطط بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@platform_bp.route('/api/plans')
@login_required
def api_get_plans():
    """API لجلب خطط الاشتراك (للعرض العام)"""
    
    lang = request.args.get('lang', 'ar')
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.display_order).all()
    
    return jsonify({
        'success': True,
        'plans': [plan.to_dict(lang) for plan in plans]
    })


@platform_bp.route('/api/plans/<plan_id>')
@login_required
def api_get_plan(plan_id):
    """API لجلب تفاصيل خطة محددة"""
    
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id, is_active=True).first_or_404()
    lang = request.args.get('lang', 'ar')
    
    return jsonify({
        'success': True,
        'plan': plan.to_dict(lang)
    })


# ============================================
# دوال مساعدة لخطط الاشتراك (للتكامل مع الـ API السابقة)
# ============================================

def get_available_plans():
    """الحصول على خطط الاشتراك المتاحة (للتكامل مع الكود القديم)"""
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.display_order).all()
    
    return [{
        'id': p.plan_id,
        'name': p.name,
        'price_monthly': p.price_monthly,
        'price_yearly': p.price_yearly,
        'max_users': p.max_users,
        'max_projects': p.max_projects,
        'storage_gb': p.storage_gb,
        'features': p.features,
        'is_active': p.is_active,
        'is_featured': p.is_featured,
        'is_default': p.is_default
    } for p in plans]


def save_plan(plan_data):
    """حفظ خطة جديدة في قاعدة البيانات"""
    try:
        # التحقق من عدم وجود plan_id مكرر
        existing = SubscriptionPlan.query.filter_by(plan_id=plan_data.get('id')).first()
        if existing:
            return False, "معرف الخطة موجود مسبقاً"
        
        plan = SubscriptionPlan(
            plan_id=plan_data.get('id'),
            name=plan_data.get('name'),
            price_monthly=plan_data.get('price_monthly', 0),
            price_yearly=plan_data.get('price_yearly', 0),
            max_users=plan_data.get('max_users', 0),
            max_projects=plan_data.get('max_projects', 0),
            storage_gb=plan_data.get('storage_gb', 0),
            features=plan_data.get('features', []),
            display_order=plan_data.get('display_order', 0),
            is_featured=plan_data.get('is_featured', False),
            is_active=plan_data.get('is_active', True),
            created_by=current_user.id
        )
        
        db.session.add(plan)
        db.session.commit()
        
        return True, "تم حفظ الخطة بنجاح"
        
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def update_plan_data(plan_id, data):
    """تحديث بيانات خطة موجودة"""
    try:
        plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
        if not plan:
            return False, "الخطة غير موجودة"
        
        # تحديث الحقول
        if 'name' in data:
            plan.name = data['name']
     
        if 'price_monthly' in data:
            plan.price_monthly = float(data['price_monthly'])
        if 'price_yearly' in data:
            plan.price_yearly = float(data['price_yearly'])
        if 'max_users' in data:
            plan.max_users = int(data['max_users'])
        if 'max_projects' in data:
            plan.max_projects = int(data['max_projects'])
        if 'storage_gb' in data:
            plan.storage_gb = int(data['storage_gb'])
        if 'features' in data:
            plan.features = data['features']
  
        if 'is_active' in data:
            plan.is_active = data['is_active']
        if 'is_featured' in data:
            plan.is_featured = data['is_featured']
        
        plan.updated_by = current_user.id
        plan.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return True, "تم تحديث الخطة بنجاح"
        
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def delete_plan_data(plan_id):
    """حذف خطة من قاعدة البيانات"""
    try:
        plan = SubscriptionPlan.query.filter_by(plan_id=plan_id).first()
        if not plan:
            return False, "الخطة غير موجودة"
        
        # التحقق من وجود شركات تستخدم هذه الخطة
        companies_using = Organization.query.filter_by(subscription_status=plan_id).count()
        if companies_using > 0:
            return False, f"لا يمكن حذف الخطة لأن {companies_using} شركة تستخدمها"
        
        db.session.delete(plan)
        db.session.commit()
        
        return True, "تم حذف الخطة بنجاح"
        
    except Exception as e:
        db.session.rollback()
        return False, str(e)


def get_plan_by_id(plan_id):
    """الحصول على خطة بواسطة معرفها"""
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id, is_active=True).first()
    if plan:
        return plan.to_dict()
    return None


def get_default_plan():
    """الحصول على الخطة الافتراضية"""
    plan = SubscriptionPlan.query.filter_by(is_default=True, is_active=True).first()
    if not plan:
        plan = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.price_monthly).first()
    return plan.to_dict() if plan else None

# في platform_routes.py - إضافة مسارات إدارة طلبات الاشتراك

@platform_bp.route('/subscription-requests')
@login_required
@platform_admin_required
def subscription_requests():
    """عرض طلبات الاشتراك المعلقة"""
    
    pending_requests = Subscription.query.filter_by(
        request_status='pending',
        payment_status='paid'
    ).order_by(Subscription.requested_at.desc()).all()
    
    # طلبات بانتظار رفع إثبات الدفع
    pending_payment = Subscription.query.filter_by(
        request_status='pending',
        payment_status='pending'
    ).order_by(Subscription.requested_at.desc()).all()
    
    # الطلبات الم approving
    approved_requests = Subscription.query.filter_by(
        request_status='approved'
    ).order_by(Subscription.approved_at.desc()).limit(20).all()
    
    # الطلبات المرفوضة
    rejected_requests = Subscription.query.filter_by(
        request_status='rejected'
    ).order_by(Subscription.updated_at.desc()).limit(20).all()
    
    stats = {
        'pending': len(pending_requests),
        'pending_payment': len(pending_payment),
        'approved': Subscription.query.filter_by(request_status='approved').count(),
        'rejected': Subscription.query.filter_by(request_status='rejected').count(),
        'total_revenue': db.session.query(db.func.sum(Subscription.total_amount)).filter(
            Subscription.payment_status == 'paid',
            Subscription.request_status == 'approved'
        ).scalar() or 0
    }
    
    return render_template('platform/subscription_requests/index.html',
                         pending_requests=pending_requests,
                         pending_payment=pending_payment,
                         approved_requests=approved_requests,
                         rejected_requests=rejected_requests,
                         stats=stats,
                         now=datetime.now())


@platform_bp.route('/subscription-requests/<int:request_id>/approve', methods=['POST'])
@login_required
@platform_admin_required
def approve_subscription_request(request_id):
    """الموافقة على طلب اشتراك"""
    
    subscription = Subscription.query.get_or_404(request_id)
    
    try:
        subscription.approve(current_user.id)
        
        # تحديث حدود الشركة حسب الخطة
        if subscription.plan_details:
            company = subscription.organization
            company.max_users = subscription.plan_details.max_users
            company.max_projects = subscription.plan_details.max_projects
            company.storage_limit_mb = subscription.plan_details.storage_gb * 1024
            company.subscription_status = 'active'
            company.subscription_end = subscription.end_date
            db.session.commit()
        # ✅ إرسال إشعار للشركة بقبول الاشتراك
        from app.services.notification_service import NotificationService
        NotificationService.subscription_approved_for_company(subscription)
        
        # ✅ إرسال إشعار آخر للشركة بتفعيل الاشتراك
        NotificationService.subscription_activated_for_company(subscription)
        log_platform_activity('approve_subscription', subscription.id, 
                             f'الموافقة على اشتراك {subscription.organization.name} في باقة {subscription.plan_name}')
        
        return jsonify({'success': True, 'message': 'تمت الموافقة على طلب الاشتراك'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@platform_bp.route('/subscription-requests/<int:request_id>/reject', methods=['POST'])
@login_required
@platform_admin_required
def reject_subscription_request(request_id):
    """رفض طلب اشتراك"""
    
    subscription = Subscription.query.get_or_404(request_id)
    data = request.get_json()
    reason = data.get('reason', '')
    
    try:
        subscription.reject(current_user.id, reason)
        # ✅ إرسال إشعار للشركة برفض الاشتراك
        from app.services.notification_service import NotificationService
        NotificationService.subscription_rejected_for_company(subscription, reason)
        
        log_platform_activity('reject_subscription', subscription.id, 
                             f'رفض اشتراك {subscription.organization.name} - السبب: {reason}')
        
        return jsonify({'success': True, 'message': 'تم رفض طلب الاشتراك'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@platform_bp.route('/subscription-requests/<int:request_id>/confirm-payment', methods=['POST'])
@login_required
@platform_admin_required
def confirm_payment(request_id):
    """تأكيد استلام الدفع (للتحويل البنكي)"""
    
    subscription = Subscription.query.get_or_404(request_id)
    
    try:
        subscription.mark_paid(current_user.id)
        
        # ✅ إرسال إشعار للشركة بتأكيد استلام الدفع
        from app.services.notification_service import NotificationService
        NotificationService.payment_received_for_company(subscription)

        log_platform_activity('confirm_payment', subscription.id, 
                             f'تأكيد دفع اشتراك {subscription.organization.name}')
        
        return jsonify({'success': True, 'message': 'تم تأكيد استلام الدفع'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# تحديث دوال إنشاء الشركة لاستخدام الخطط من قاعدة البيانات
# ============================================

def get_default_plan_limits():
    """الحصول على حدود الخطة الافتراضية"""
    default_plan = get_default_plan()
    if default_plan:
        return {
            'max_users': default_plan.get('max_users', 50),
            'max_projects': default_plan.get('max_projects', 100),
            'storage_gb': default_plan.get('storage_gb', 10)
        }
    return {
        'max_users': 50,
        'max_projects': 100,
        'storage_gb': 10
    }
# ============================================
# API Routes
# ============================================

@platform_bp.route('/api/dashboard/stats')
@login_required
@platform_admin_required
def api_dashboard_stats():
    """API للإحصائيات الرئيسية"""
    
    stats = get_dashboard_stats()
    
    return jsonify({'success': True, 'stats': stats})


@platform_bp.route('/api/dashboard/chart-data')
@login_required
@platform_admin_required
def api_chart_data():
    """API لبيانات الرسوم البيانية"""
    
    chart_type = request.args.get('type', 'revenue')
    period = request.args.get('period', '6')
    
    if chart_type == 'revenue':
        data = get_monthly_revenue(int(period))
    elif chart_type == 'companies':
        data = get_companies_growth(int(period))
    elif chart_type == 'users':
        data = get_users_growth(int(period))
    else:
        data = []
    
    return jsonify({'success': True, 'data': data})


def get_dashboard_stats():
    """الحصول على إحصائيات لوحة التحكم"""
    return {
        'companies': {
            'total': Organization.query.count(),
            'active': Organization.query.filter_by(is_active=True).count(),
            'trial': Organization.query.filter_by(subscription_status='trial').count()
        },
        'users': {
            'total': User.query.count(),
            'active': User.query.filter_by(is_user_active=True).count()
        },
        'revenue': {
            'total': db.session.query(db.func.sum(Subscription.amount)).scalar() or 0,
            'this_month': db.session.query(db.func.sum(Subscription.amount)).filter(
                db.extract('month', Subscription.created_at) == datetime.now().month
            ).scalar() or 0
        }
    }


def get_monthly_revenue(months=6):
    """الحصول على الإيرادات الشهرية"""
    data = []
    for i in range(months-1, -1, -1):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1)
        
        revenue = db.session.query(db.func.sum(Subscription.amount)).filter(
            Subscription.created_at >= month_start,
            Subscription.created_at < month_end,
            Subscription.status == 'active'
        ).scalar() or 0
        
        data.append({
            'month': month_date.strftime('%b %Y'),
            'revenue': revenue
        })
    return data


def get_companies_growth(months=6):
    """الحصول على نمو الشركات"""
    data = []
    for i in range(months-1, -1, -1):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1)
        
        count = Organization.query.filter(
            Organization.created_at >= month_start,
            Organization.created_at < month_end
        ).count()
        
        data.append({
            'month': month_date.strftime('%b %Y'),
            'count': count
        })
    return data


def get_users_growth(months=6):
    """الحصول على نمو المستخدمين"""
    data = []
    for i in range(months-1, -1, -1):
        month_date = datetime.now() - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1)
        
        count = User.query.filter(
            User.created_at >= month_start,
            User.created_at < month_end
        ).count()
        
        data.append({
            'month': month_date.strftime('%b %Y'),
            'count': count
        })
    return data

# ============================================
# إشعارات المنصة (Platform Notifications)
# ============================================

@platform_bp.route('/notifications')
@login_required
@platform_admin_required
def platform_notifications():
    """عرض جميع إشعارات المنصة"""
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    type_filter = request.args.get('type', 'all')
    priority_filter = request.args.get('priority', 'all')
    read_filter = request.args.get('read', 'all')
    
    query = PlatformNotification.query.filter_by(admin_id=current_user.id)
    
    if type_filter != 'all':
        query = query.filter_by(notification_type=type_filter)
    
    if priority_filter != 'all':
        query = query.filter_by(priority=priority_filter)
    
    if read_filter == 'read':
        query = query.filter_by(is_read=True)
    elif read_filter == 'unread':
        query = query.filter_by(is_read=False)
    
    notifications = query.order_by(PlatformNotification.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # إحصائيات
    stats = {
        'total': PlatformNotification.query.filter_by(admin_id=current_user.id).count(),
        'unread': PlatformNotification.query.filter_by(admin_id=current_user.id, is_read=False).count(),
        'high_priority': PlatformNotification.query.filter_by(admin_id=current_user.id, priority='high').count(),
        'critical': PlatformNotification.query.filter_by(admin_id=current_user.id, priority='critical').count()
    }
    
    # أنواع الإشعارات للفلترة
    types = db.session.query(PlatformNotification.notification_type).filter_by(
        admin_id=current_user.id
    ).distinct().all()
    types = [t[0] for t in types if t[0]]
    
    return render_template('platform/notifications/index.html',
                         notifications=notifications,
                         stats=stats,
                         types=types,
                         filters={
                             'type': type_filter,
                             'priority': priority_filter,
                             'read': read_filter
                         },
                         now=datetime.now())


@platform_bp.route('/notifications/<int:notif_id>')
@login_required
@platform_admin_required
def platform_notification_detail(notif_id):
    """عرض تفاصيل إشعار المنصة"""
    
    notification = PlatformNotification.query.get_or_404(notif_id)
    
    if notification.admin_id != current_user.id:
        flash('غير مصرح بالوصول إلى هذا الإشعار', 'danger')
        return redirect(url_for('platform.platform_notifications'))
    
    # تحديث الإشعار كمقروء إذا لم يكن مقروءاً
    if not notification.is_read:
        notification.mark_as_read()
    
    return render_template('platform/notifications/detail.html',
                         notification=notification,
                         now=datetime.now())


@platform_bp.route('/notifications/<int:notif_id>/mark-read', methods=['POST'])
@login_required
@platform_admin_required
def platform_mark_notification_read(notif_id):
    """تحديد إشعار المنصة كمقروء"""
    
    notification = PlatformNotification.query.get_or_404(notif_id)
    
    if notification.admin_id != current_user.id:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    notification.mark_as_read()
    
    return jsonify({'success': True})


@platform_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
@platform_admin_required
def platform_mark_all_notifications_read():
    """تحديد جميع إشعارات المنصة كمقروءة"""
    
    PlatformNotification.query.filter_by(
        admin_id=current_user.id,
        is_read=False
    ).update({'is_read': True, 'read_at': datetime.utcnow()})
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم تحديد جميع الإشعارات كمقروءة'})


@platform_bp.route('/notifications/<int:notif_id>/delete', methods=['DELETE'])
@login_required
@platform_admin_required
def platform_delete_notification(notif_id):
    """حذف إشعار المنصة"""
    
    notification = PlatformNotification.query.get_or_404(notif_id)
    
    if notification.admin_id != current_user.id:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم حذف الإشعار بنجاح'})


@platform_bp.route('/notifications/delete-all-read', methods=['POST'])
@login_required
@platform_admin_required
def platform_delete_all_read_notifications():
    """حذف جميع إشعارات المنصة المقروءة"""
    
    PlatformNotification.query.filter_by(
        admin_id=current_user.id,
        is_read=True
    ).delete()
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم حذف جميع الإشعارات المقروءة'})


@platform_bp.route('/api/notifications/unread-count')
@login_required
@platform_admin_required
def api_platform_unread_count():
    """API لعدد إشعارات المنصة غير المقروءة"""
    
    count = PlatformNotification.query.filter_by(
        admin_id=current_user.id,
        is_read=False
    ).count()
    
    high_priority_count = PlatformNotification.query.filter_by(
        admin_id=current_user.id,
        is_read=False,
        priority='high'
    ).count()
    
    return jsonify({
        'success': True,
        'count': count,
        'high_priority_count': high_priority_count
    })


@platform_bp.route('/api/notifications/latest')
@login_required
@platform_admin_required
def api_platform_latest_notifications():
    """API لأحدث إشعارات المنصة"""
    
    limit = request.args.get('limit', 10, type=int)
    
    notifications = PlatformNotification.query.filter_by(
        admin_id=current_user.id
    ).order_by(PlatformNotification.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'success': True,
        'notifications': [n.to_dict() for n in notifications],
        'unread_count': PlatformNotification.query.filter_by(
            admin_id=current_user.id, is_read=False
        ).count()
    })
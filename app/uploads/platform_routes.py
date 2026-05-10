"""
platform_routes.py - مسارات لوحة تحكم المنصة
"""
from ..extensions import db
from flask import render_template, request, redirect, url_for, flash, jsonify, g
from flask_login import login_required, current_user
from app.models import  PlatformAdmin, Organization, User, Subscription
from app.routes import platform_bp
from datetime import datetime, timedelta
from functools import wraps

# ============================================
# دالة التحقق من صلاحية مدير المنصة
# ============================================

def platform_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not hasattr(current_user, 'role') or current_user.role != 'super_admin':
            flash('غير مصرح بالوصول إلى لوحة تحكم المنصة', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# قبل كل طلب
# ============================================

@platform_bp.before_request
def load_platform_data():
    if current_user.is_authenticated and hasattr(current_user, 'role') and current_user.role == 'super_admin':
        g.platform = current_user.platform
        g.notifications_count = 0  # TODO: إضافة نظام إشعارات للمنصة

# ============================================
# لوحة تحكم المنصة الرئيسية
# ============================================

@platform_bp.route('/')
@login_required
@platform_admin_required
def dashboard():
    """لوحة تحكم المنصة الرئيسية"""
    
    # إحصائيات عامة
    total_companies = Organization.query.count()
    active_companies = Organization.query.filter_by(is_active=True).count()
    trial_companies = Organization.query.filter_by(subscription_status='trial').count()
    expired_companies = Organization.query.filter(
        Organization.subscription_status == 'expired'
    ).count()
    
    total_users = User.query.count()
    active_users = User.query.filter_by(is_user_active=True).count()
    
    # إحصائيات اليوم
    today = datetime.now().date()
    new_companies_today = Organization.query.filter(
        db.func.date(Organization.created_at) == today
    ).count()
    
    new_users_today = User.query.filter(
        db.func.date(User.created_at) == today
    ).count()
    
    # آخر الشركات المسجلة
    recent_companies = Organization.query.order_by(
        Organization.created_at.desc()
    ).limit(5).all()
    
    # آخر المستخدمين
    recent_users = User.query.order_by(
        User.created_at.desc()
    ).limit(5).all()
    
    # إحصائيات الاشتراكات
    subscriptions = {
        'total_revenue': db.session.query(db.func.sum(Subscription.amount)).filter_by(status='active').scalar() or 0,
        'active_subs': Subscription.query.filter_by(status='active').count(),
        'expiring_soon': Subscription.query.filter(
            Subscription.end_date <= datetime.now() + timedelta(days=7),
            Subscription.end_date > datetime.now()
        ).count()
    }
    
    stats = {
        'companies': {
            'total': total_companies,
            'active': active_companies,
            'trial': trial_companies,
            'expired': expired_companies,
            'new_today': new_companies_today
        },
        'users': {
            'total': total_users,
            'active': active_users,
            'new_today': new_users_today
        },
        'subscriptions': subscriptions
    }
    
    return render_template('platform/dashboard.html',
                         stats=stats,
                         recent_companies=recent_companies,
                         recent_users=recent_users,
                         now=datetime.now())

# ============================================
# إدارة الشركات
# ============================================

@platform_bp.route('/companies')
@login_required
@platform_admin_required
def companies():
    """قائمة الشركات"""
    
    # معاملات التصفية
    status = request.args.get('status', 'all')
    search = request.args.get('search', '')
    date_from = request.args.get('from', '')
    date_to = request.args.get('to', '')
    
    query = Organization.query
    
    if status != 'all':
        if status == 'active':
            query = query.filter_by(is_active=True)
        elif status == 'inactive':
            query = query.filter_by(is_active=False)
        elif status == 'trial':
            query = query.filter_by(subscription_status='trial')
        elif status == 'expired':
            query = query.filter_by(subscription_status='expired')
    
    if search:
        query = query.filter(
            (Organization.name.contains(search)) |
            (Organization.email.contains(search)) |
            (Organization.org_code.contains(search))
        )
    
    if date_from:
        query = query.filter(Organization.created_at >= datetime.strptime(date_from, '%Y-%m-%d'))
    
    if date_to:
        query = query.filter(Organization.created_at <= datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    
    companies = query.order_by(Organization.created_at.desc()).all()
    
    # إحصائيات سريعة
    stats = {
        'total': Organization.query.count(),
        'active': Organization.query.filter_by(is_active=True).count(),
        'trial': Organization.query.filter_by(subscription_status='trial').count(),
        'expired': Organization.query.filter_by(subscription_status='expired').count()
    }
    
    return render_template('platform/companies/index.html',
                         companies=companies,
                         stats=stats,
                         filters={'status': status, 'search': search, 'from': date_from, 'to': date_to})

@platform_bp.route('/companies/<int:company_id>')
@login_required
@platform_admin_required
def view_company(company_id):
    """عرض تفاصيل الشركة"""
    
    company = Organization.query.get_or_404(company_id)
    
    # إحصائيات الشركة
    users = User.query.filter_by(org_id=company_id).all()
    subscriptions = Subscription.query.filter_by(org_id=company_id).order_by(Subscription.created_at.desc()).all()
    
    stats = {
        'total_users': len(users),
        'active_users': len([u for u in users if u.is_user_active]),
        'total_projects': company.current_projects,
        'max_projects': company.max_projects,
        'storage_used': company.storage_used_mb,
        'storage_limit': company.storage_limit_mb,
        'usage_percent': (company.current_projects / company.max_projects * 100) if company.max_projects > 0 else 0
    }
    
    return render_template('platform/companies/view.html',
                         company=company,
                         users=users,
                         subscriptions=subscriptions,
                         stats=stats)

@platform_bp.route('/companies/<int:company_id>/toggle-status', methods=['POST'])
@login_required
@platform_admin_required
def toggle_company_status(company_id):
    """تفعيل/تعطيل الشركة"""
    
    company = Organization.query.get_or_404(company_id)
    company.is_active = not company.is_active
    db.session.commit()
    
    status = 'مفعلة' if company.is_active else 'معطلة'
    return jsonify({'success': True, 'message': f'تم {status} الشركة بنجاح'})

@platform_bp.route('/companies/<int:company_id>/delete', methods=['POST'])
@login_required
@platform_admin_required
def delete_company(company_id):
    """حذف الشركة"""
    
    company = Organization.query.get_or_404(company_id)
    
    try:
        # حذف جميع المستخدمين أولاً
        User.query.filter_by(org_id=company_id).delete()
        # حذف الاشتراكات
        Subscription.query.filter_by(org_id=company_id).delete()
        # حذف الشركة
        db.session.delete(company)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم حذف الشركة وجميع بياناتها بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# إدارة الاشتراكات
# ============================================

@platform_bp.route('/subscriptions')
@login_required
@platform_admin_required
def subscriptions():
    """إدارة الاشتراكات"""
    
    subscriptions = Subscription.query.order_by(Subscription.created_at.desc()).all()
    
    # إحصائيات الاشتراكات
    stats = {
        'total_revenue': db.session.query(db.func.sum(Subscription.amount)).scalar() or 0,
        'active_count': Subscription.query.filter_by(status='active').count(),
        'trial_count': Subscription.query.filter_by(plan='trial').count(),
        'expiring_soon': Subscription.query.filter(
            Subscription.end_date <= datetime.now() + timedelta(days=7),
            Subscription.end_date > datetime.now()
        ).count()
    }
    
    return render_template('platform/subscriptions/index.html',
                         subscriptions=subscriptions,
                         stats=stats)

# ============================================
# إدارة مستخدمي المنصة (Platform Admins)
# ============================================

@platform_bp.route('/admins')
@login_required
@platform_admin_required
def admins():
    """إدارة مدراء المنصة"""
    
    admins = PlatformAdmin.query.filter_by(platform_id=current_user.platform_id).all()
    
    return render_template('platform/admins/index.html', admins=admins)

@platform_bp.route('/admins/create', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def create_admin():
    """إنشاء مدير منصة جديد"""
    
    if request.method == 'POST':
        try:
            admin = PlatformAdmin(
                platform_id=current_user.platform_id,
                username=request.form.get('username'),
                email=request.form.get('email'),
                full_name=request.form.get('full_name'),
                full_name_ar=request.form.get('full_name_ar'),
                phone=request.form.get('phone'),
                role=request.form.get('role', 'admin')
            )
            admin.set_password(request.form.get('password', 'Admin123!'))
            
            db.session.add(admin)
            db.session.commit()
            
            flash('تم إنشاء مدير منصة جديد بنجاح', 'success')
            return redirect(url_for('platform.admins'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('platform/admins/create.html')

# ============================================
# التقارير والإحصائيات
# ============================================

@platform_bp.route('/reports')
@login_required
@platform_admin_required
def reports():
    """تقارير المنصة"""
    
    # تقرير نمو الشركات
    companies_growth = db.session.query(
        db.func.date_trunc('month', Organization.created_at).label('month'),
        db.func.count(Organization.id).label('count')
    ).group_by('month').order_by('month').all()
    
    # تقرير الاشتراكات
    subscriptions_by_plan = db.session.query(
        Subscription.plan,
        db.func.count(Subscription.id).label('count'),
        db.func.sum(Subscription.amount).label('revenue')
    ).group_by(Subscription.plan).all()
    
    # أكثر الشركات استخداماً
    top_companies = Organization.query.order_by(
        Organization.current_users.desc()
    ).limit(5).all()
    
    return render_template('platform/reports/index.html',
                         companies_growth=companies_growth,
                         subscriptions_by_plan=subscriptions_by_plan,
                         top_companies=top_companies)

# ============================================
# إعدادات المنصة
# ============================================

@platform_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@platform_admin_required
def settings():
    """إعدادات المنصة"""
    
    if request.method == 'POST':
        try:
            # تحديث إعدادات المنصة
            platform = current_user.platform
            platform.company_name = request.form.get('company_name', platform.company_name)
            platform.company_name_ar = request.form.get('company_name_ar', platform.company_name_ar)
            platform.email = request.form.get('email', platform.email)
            platform.phone = request.form.get('phone', platform.phone)
            
            # تحديث إعدادات النظام
            settings = platform.platform_settings or {}
            settings['allow_multi_companies'] = bool(request.form.get('allow_multi_companies'))
            settings['max_companies'] = int(request.form.get('max_companies', 100))
            settings['default_company_quota']['max_users'] = int(request.form.get('default_max_users', 50))
            settings['default_company_quota']['max_projects'] = int(request.form.get('default_max_projects', 100))
            settings['default_company_quota']['storage_gb'] = int(request.form.get('default_storage_gb', 10))
            
            platform.platform_settings = settings
            db.session.commit()
            
            flash('تم تحديث إعدادات المنصة بنجاح', 'success')
            return redirect(url_for('platform.settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('platform/settings/index.html', platform=current_user.platform)

# ============================================
# API Routes للمنصة
# ============================================

@platform_bp.route('/api/stats')
@login_required
@platform_admin_required
def api_stats():
    """API للإحصائيات"""
    
    stats = {
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
    
    return jsonify({'success': True, 'stats': stats})

@platform_bp.route('/api/companies/search')
@login_required
@platform_admin_required
def api_search_companies():
    """API للبحث عن الشركات"""
    
    query = request.args.get('q', '')
    
    companies = Organization.query.filter(
        (Organization.name.contains(query)) |
        (Organization.email.contains(query)) |
        (Organization.org_code.contains(query))
    ).limit(10).all()
    
    results = [{
        'id': c.id,
        'name': c.name,
        'email': c.email,
        'code': c.org_code,
        'status': c.subscription_status
    } for c in companies]
    
    return jsonify({'results': results})
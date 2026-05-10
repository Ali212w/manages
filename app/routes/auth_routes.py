"""
auth_routes.py - مسارات المصادقة وتسجيل الدخول
"""
from ..extensions import db
from flask import render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from app.models import  User, Organization, Subscription,PlatformAdmin
from app.routes import auth_bp
from datetime import datetime, timedelta
import uuid
import re
import stripe
from app.services.notification_service import NotificationService
# ============================================
# دالة التحقق من صحة البريد الإلكتروني
# ============================================

def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

# ============================================
# دالة التحقق من قوة كلمة المرور
# ============================================

def is_strong_password(password):
    if len(password) < 8:
        return False, 'كلمة المرور يجب أن تكون 8 أحرف على الأقل'
    if not re.search(r'[A-Z]', password):
        return False, 'كلمة المرور يجب أن تحتوي على حرف كبير واحد على الأقل'
    if not re.search(r'[a-z]', password):
        return False, 'كلمة المرور يجب أن تحتوي على حرف صغير واحد على الأقل'
    if not re.search(r'[0-9]', password):
        return False, 'كلمة المرور يجب أن تحتوي على رقم واحد على الأقل'
    return True, ''

# ============================================
# الصفحة الرئيسية - اختيار نوع الدخول
# ============================================

# ============================================
# تسجيل الدخول
# ============================================
"""
auth_routes.py - إضافة مسار دخول مدير المنصة
"""
@auth_bp.route('/')
def index():
    """الصفحة الرئيسية للمصادقة"""
    return render_template('layouts/index.html')

def redirect_to_user_dashboard():
    """توجيه المستخدم إلى لوحة التحكم المناسبة حسب الدور"""
    if current_user.is_authenticated:
        from app.models import PlatformAdmin
        if isinstance(current_user, PlatformAdmin):
            return redirect(url_for('platform.dashboard'))
        if hasattr(current_user, 'role'):
            role = current_user.role
            if role == 'platform_admin':
                return redirect(url_for('platform.dashboard'))
            elif role == 'org_admin':
                return redirect(url_for('company.dashboard'))
            elif role == 'supplier':
                return redirect(url_for('supplier.dashboard'))
            elif role == 'client':
                return redirect(url_for('client.dashboard'))
            elif role == 'consultant':
                return redirect(url_for('consultant.dashboard'))
            elif role in ['project_manager', 'supervisor', 'delegate', 'employee']:
                # لوحة المعلومات الجديدة المخصصة حسب الدور
                return redirect(url_for('role_dashboard.my_dashboard'))
    return redirect(url_for('auth.login'))

# ============================================
# تسجيل الدخول
# ============================================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """تسجيل الدخول للمستخدمين"""
    # إذا كان المستخدم مسجل الدخول بالفعل
    if current_user.is_authenticated:
        print(f"✅ المستخدم مسجل بالفعل: {current_user.get_id()}")
        return redirect_to_user_dashboard()
    
    # الحصول على عنوان العودة
    # next_url = request.args.get('next') or session.pop('next_url', None)
    
    if request.method == 'POST':
        login_type = request.form.get('login_type', 'user')
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        remember = True if request.form.get('remember') else False
        
        if not email or not password:
            flash('البريد الإلكتروني وكلمة المرور مطلوبان', 'danger')
            return redirect(url_for('auth.login'))
        from app.models import PlatformAdmin
        
        platform_admin = PlatformAdmin.query.filter_by(email=email).first()
        
        if platform_admin and platform_admin.check_password(password):
            if platform_admin.is_active:
                # تسجيل الدخول
                login_user(platform_admin, remember=remember, force=True)
                
                # تحديث بيانات الدخول
                platform_admin.increment_login_count()
                db.session.commit()
                
                print(f"✅ تم تسجيل دخول مدير المنصة: {platform_admin.email}")
                print(f"🔑 الدور: {platform_admin.role}")
                print(f"🔑 مفتاح الجلسة: {platform_admin.get_id()}")
                
                flash(f'مرحباً {platform_admin.full_name}! تم تسجيل الدخول بنجاح', 'success')
                session.permanent = True
                
                # التوجيه حسب الدور
                if platform_admin.role == 'super_admin':
                    return redirect(url_for('platform.dashboard'))
                else:
                    return redirect(url_for('platform.dashboard'))
            else:
                flash('الحساب معطل، يرجى التواصل مع مدير المنصة', 'danger')
                return redirect(url_for('auth.login'))
            
        if login_type == 'user':
            # تسجيل دخول المستخدمين العاديين
            user = User.query.filter_by(email=email).first()
            
            if user and user.check_password(password):
                if user.is_user_active:
                    # تسجيل الدخول
                    login_user(user, remember=remember, force=True)
                    
                    # تحديث بيانات الدخول
                    user.increment_login_count()
                    db.session.commit()
                    
                    # طباعة معلومات للتصحيح
                    print(f"✅ تم تسجيل دخول المستخدم: {user.email}")
                    print(f"🔑 معرف المستخدم: {user.id}")
                    print(f"🔑 مفتاح الجلسة: {user.get_id()}")
                    print(f"🍪 الجلسة: {dict(session)}")
                    
                    flash(f'مرحباً {user.full_name}! تم تسجيل الدخول بنجاح', 'success')
                    
                    # حفظ الجلسة بشكل دائم
                    session.permanent = True
                    
                    # إذا كان هناك عنوان عودة صالح، استخدمه
                    # if next_url and next_url.startswith('/'):
                    #     print(f"↪️ توجيه إلى: {next_url}")
                    #     return redirect(next_url)
                    
                    # توجيه حسب الدور
                    role = user.role
                    if role == 'org_admin':
                        next_page = request.args.get('next') or url_for('company.dashboard')
                        print("↪️ توجيه إلى لوحة تحكم الشركة")
                        return redirect(next_page)
                    elif role == 'super_admin':
                        next_page = request.args.get('next') or url_for('platform.dashboard')
                        print("↪️ توجيه إلى لوحة تحكم المنصة")
                        return redirect(next_page)
                    elif role == 'supplier':
                        next_page = request.args.get('next') or url_for('supplier.dashboard')
                        return redirect(next_page)
                    elif role == 'client':
                        next_page = request.args.get('next') or url_for('client.dashboard')
                        return redirect(next_page)
                    elif role == 'consultant':
                        next_page = request.args.get('next') or url_for('consultant.dashboard')
                        return redirect(next_page)
                    elif role in ['project_manager', 'supervisor', 'delegate', 'employee']:
                        # ← لوحة المعلومات المخصصة حسب الدور (جديد)
                        next_page = request.args.get('next') or url_for('role_dashboard.my_dashboard')
                        print(f"↪️ توجيه إلى لوحة الدور: {role}")
                        return redirect(next_page)
                    else:
                        next_page = request.args.get('next') or url_for('employee.dashboard')
                        print("↪️ توجيه إلى لوحة الموظف (افتراضي)")
                        return redirect(next_page)
                else:
                    flash('الحساب معطل، يرجى التواصل مع مدير الشركة', 'danger')
            else:
                flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'danger')
        
        elif login_type == 'org':
            # تسجيل دخول المؤسسة
            organization = Organization.query.filter_by(email=email).first()
            
            if organization and organization.verify_password(password):
                if organization.is_active:
                    # لا نستخدم login_user للمؤسسة لأنها ليست من UserMixin
                    session['org_id'] = organization.id
                    session['org_name'] = organization.name
                    session.permanent = True
                    
                    print(f"✅ تم تسجيل دخول المؤسسة: {organization.name}")
                    print(f"🍪 الجلسة: {dict(session)}")
                    
                    flash(f'مرحباً {organization.name}! تم تسجيل دخول المؤسسة بنجاح', 'success')
                    return redirect(url_for('auth.org_dashboard'))
                else:
                    flash('المؤسسة معطلة، يرجى التواصل مع الدعم', 'danger')
            else:
                flash('بيانات المؤسسة غير صحيحة', 'danger')
    
    return render_template('auth/login.html')

# ============================================
# تسجيل الخروج
# ============================================

@auth_bp.route('/logout')
@login_required
def logout():
    """تسجيل الخروج"""
    from flask import session, redirect, url_for, flash, make_response
    
    # تخزين اسم المستخدم للرسالة
    username = current_user.full_name if current_user.full_name else 'المستخدم'
    
    # تسجيل الخروج
    logout_user()
    
    # مسح الجلسة بالكامل
    session.clear()
    
    # إنشاء استجابة
    response =redirect(url_for('auth.index')) 
    
    # حذف الكوكيز
    response.delete_cookie('session')
    response.delete_cookie('remember_token')
    
    print(f"✅ تم تسجيل خروج {username} ومسح الجلسة")
    
    flash(f'👋 وداعاً {username}، تم تسجيل الخروج بنجاح. نتمنى لك يوماً سعيداً!', 'success')
    
    return response

# ============================================
# لوحة تحكم المؤسسة (كيان)
# ============================================

@auth_bp.route('/org-dashboard')
def org_dashboard():
    """لوحة تحكم المؤسسة (عند تسجيل الدخول كمؤسسة)"""
    if 'org_id' not in session:
        flash('الرجاء تسجيل الدخول أولاً', 'warning')
        return redirect(url_for('auth.login'))
    
    org = Organization.query.get(session['org_id'])
    if not org:
        session.pop('org_id', None)
        session.pop('org_name', None)
        flash('المؤسسة غير موجودة', 'danger')
        return redirect(url_for('auth.login'))
    
    # إحصائيات المؤسسة
    stats = {
        'users_count': User.query.filter_by(org_id=org.id).count(),
        'active_users': User.query.filter_by(org_id=org.id, is_user_active=True).count(),
        'subscription_status': org.subscription_status,
        'trial_days_left': (org.trial_end - datetime.utcnow()).days if org.trial_end else 0
    }
    
    return render_template('auth/org_dashboard.html', org=org, stats=stats,now=datetime.now())

# ============================================
# تسجيل شركة جديدة
# ============================================

@auth_bp.route('/register-company', methods=['GET', 'POST'])
def register_company():
    """تسجيل شركة جديدة"""
    if current_user.is_authenticated:
        return redirect_to_user_dashboard()
    
    if request.method == 'POST':
        try:
            # التحقق من البيانات
            company_name = request.form.get('company_name', '').strip()
            company_email = request.form.get('company_email', '').strip()
            admin_name = request.form.get('admin_name', '').strip()
            admin_email = request.form.get('admin_email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            phone = request.form.get('phone', '').strip()
            
            # التحقق من المدخلات
            if not all([company_name, company_email, admin_name, admin_email, password]):
                flash('جميع الحقول المطلوبة يجب أن تمتلئ', 'danger')
                return render_template('auth/register_company.html')
            
            if password != confirm_password:
                flash('كلمة المرور غير متطابقة', 'danger')
                return render_template('auth/register_company.html')
            
            # التحقق من قوة كلمة المرور
            is_strong, msg = is_strong_password(password)
            if not is_strong:
                flash(msg, 'danger')
                return render_template('auth/register_company.html')
            
            # التحقق من صحة البريد الإلكتروني
            if not is_valid_email(company_email) or not is_valid_email(admin_email):
                flash('البريد الإلكتروني غير صالح', 'danger')
                return render_template('auth/register_company.html')
            
            # التحقق من عدم تكرار البريد
            if Organization.query.filter_by(email=company_email).first():
                flash('البريد الإلكتروني للشركة مسجل مسبقاً', 'danger')
                return render_template('auth/register_company.html')
            
            if User.query.filter_by(email=admin_email).first():
                flash('البريد الإلكتروني لمدير الشركة مسجل مسبقاً', 'danger')
                return render_template('auth/register_company.html')
            
            
            # إنشاء كود فريد للشركة
            import random
            import string
            org_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
            
            # إنشاء الشركة
            trial_end = datetime.utcnow() + timedelta(days=30)  # 30 يوم تجريبي
            
            organization = Organization(
                org_code=org_code,
                name=company_name,
                email=company_email,
                phone=phone,
                subscription_status='trial',
                trial_start=datetime.utcnow(),
                trial_end=trial_end,
                is_active=True,
                is_verified=False,
                settings={
                    'currency': 'USD',
                    'language': 'en',
                    'timezone': 'Asia/Riyadh',
                    'date_format': 'dd/MM/yyyy'
                }
            )
            organization.password = password  # استخدام الـ setter
            
            db.session.add(organization)
            db.session.flush()  # للحصول على ID
            
            # إنشاء مدير الشركة
            admin = User(
                org_id=organization.id,
                username=admin_email.split('@')[0],
                email=admin_email,
                full_name=admin_name,
                phone=phone,
                role='org_admin',
                is_user_active=True,
                is_verified=True,
                created_at=datetime.utcnow()
            )
            admin.set_password(password)
            
            db.session.add(admin)
            
            # إنشاء اشتراك تجريبي
            subscription = Subscription(
                org_id=organization.id,
                plan='free',
                plan_id='free',
                plan_name='Free Trial',
                amount=0,
                currency='USD',
                payment_method='system',
                status='trial',
                start_date=datetime.utcnow(),
                end_date=datetime.utcnow() + timedelta(days=20),
                auto_renew=False,
                duration_months=0
            )
            db.session.add(subscription)
            
            db.session.commit()
            
            # تسجيل الدخول تلقائياً
            login_user(admin, remember=True)
            NotificationService.user_registered(admin)
            # ✅ إشعار بإضافة شركة جديدة
            from app.services.platform_notification_service import PlatformNotificationService
            PlatformNotificationService.new_company_registered(organization)
            
            flash(f'مرحباً {admin_name}! تم إنشاء حساب الشركة بنجاح. لديك 30 يوم تجريبي', 'success')
            return redirect(url_for('company.dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ أثناء التسجيل: {str(e)}', 'danger')
    
    return render_template('auth/register_company.html')

# ============================================
# تسجيل مستخدم جديد في شركة
# ============================================

@auth_bp.route('/register-user', methods=['GET', 'POST'])
def register_user():
    """تسجيل مستخدم جديد في شركة (عن طريق دعوة)"""
    # هذا المسار للمستخدمين الذين تلقوا دعوة من مدير الشركة
    
    # الحصول على رمز الدعوة من الرابط
    invitation_token = request.args.get('token')
    
    if request.method == 'POST':
        try:
            full_name = request.form.get('full_name', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            invitation_token = request.form.get('invitation_token', '')
            
            # التحقق من المدخلات
            if not all([full_name, email, password]):
                flash('جميع الحقول المطلوبة يجب أن تمتلئ', 'danger')
                return render_template('auth/register_user.html', token=invitation_token)
            
            if password != confirm_password:
                flash('كلمة المرور غير متطابقة', 'danger')
                return render_template('auth/register_user.html', token=invitation_token)
            
            # التحقق من قوة كلمة المرور
            is_strong, msg = is_strong_password(password)
            if not is_strong:
                flash(msg, 'danger')
                return render_template('auth/register_user.html', token=invitation_token)
            
            # التحقق من صحة البريد
            if not is_valid_email(email):
                flash('البريد الإلكتروني غير صالح', 'danger')
                return render_template('auth/register_user.html', token=invitation_token)
            
            # التحقق من رمز الدعوة
            # TODO: تنفيذ نظام الدعوات
            
            flash('تم تفعيل حسابك بنجاح، يرجى انتظار موافقة مدير الشركة', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('auth/register_user.html', token=invitation_token)

@auth_bp.route('/approve-user/<int:user_id>', methods=['POST'])
@login_required
def approve_user(user_id):
    """الموافقة على حساب مستخدم (للمدير فقط)"""
    if current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    user = User.query.get_or_404(user_id)
    user.is_verified = True
    user.is_user_active = True
    db.session.commit()
    
    # إرسال إشعار للمستخدم
    NotificationService.user_approved(user, current_user)
    # ✅ إشعار بإضافة مستخدم جديد
    from app.services.platform_notification_service import PlatformNotificationService
    PlatformNotificationService.new_user_registered(user)
    return jsonify({'success': True, 'message': 'تم الموافقة على الحساب'})

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """الصفحة الشخصية"""
    if request.method == 'POST':
        try:
            user = current_user
            
            # تحديث البيانات الأساسية
            user.full_name = request.form.get('full_name', user.full_name)
            user.full_name_ar = request.form.get('full_name_ar', user.full_name_ar)
            user.phone = request.form.get('phone', user.phone)
            user.mobile = request.form.get('mobile', user.mobile)
            user.job_title = request.form.get('job_title', user.job_title)
            user.job_title_ar = request.form.get('job_title_ar', user.job_title_ar)
            
            # تحديث كلمة المرور إذا تم إدخالها
            new_password = request.form.get('new_password')
            if new_password:
                confirm_password = request.form.get('confirm_password')
                current_password = request.form.get('current_password')
                
                if not user.check_password(current_password):
                    flash('كلمة المرور الحالية غير صحيحة', 'danger')
                elif new_password != confirm_password:
                    flash('كلمة المرور غير متطابقة', 'danger')
                else:
                    user.set_password(new_password)
                    flash('تم تحديث كلمة المرور بنجاح', 'success')
            
            db.session.commit()
            flash('تم تحديث البيانات بنجاح', 'success')
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('auth/profile.html', user=current_user)
# ============================================
# نسيان كلمة المرور
# ============================================

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """طلب إعادة تعيين كلمة المرور"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        # البحث عن المستخدم
        user = User.query.filter_by(email=email).first()
        
        if user:
            # TODO: إرسال بريد إلكتروني لإعادة التعيين
            flash('تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك الإلكتروني', 'success')
        else:
            # نعطي نفس الرسالة لأمان النظام
            flash('تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك الإلكتروني', 'success')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/forgot-password.html')

# ============================================
# إعادة تعيين كلمة المرور
# ============================================

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """إعادة تعيين كلمة المرور"""
    # TODO: التحقق من صحة الرمز
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if password != confirm_password:
            flash('كلمة المرور غير متطابقة', 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        # التحقق من قوة كلمة المرور
        is_strong, msg = is_strong_password(password)
        if not is_strong:
            flash(msg, 'danger')
            return render_template('auth/reset_password.html', token=token)
        
        # TODO: تحديث كلمة المرور
        
        flash('تم تحديث كلمة المرور بنجاح', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', token=token)

# ============================================
# تسجيل الخروج
# ============================================


# ============================================
# API Routes للمصادقة
# ============================================

@auth_bp.route('/api/login', methods=['POST'])
def api_login():
    """API تسجيل الدخول"""
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'البريد الإلكتروني وكلمة المرور مطلوبان'}), 400
    
    user = User.query.filter_by(email=data['email']).first()
    
    if user and user.check_password(data['password']):
        if user.is_user_active:
            login_user(user, remember=data.get('remember', False))
            user.increment_login_count()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم تسجيل الدخول بنجاح',
                'user': user.to_dict(),
                'redirect': url_for('company.dashboard')
            }), 200
        else:
            return jsonify({'error': 'الحساب معطل'}), 403
    else:
        return jsonify({'error': 'بيانات الدخول غير صحيحة'}), 401

@auth_bp.route('/api/register-company', methods=['POST'])
def api_register_company():
    """API تسجيل شركة جديدة"""
    try:
        data = request.get_json()
        
        # التحقق من البيانات
        required_fields = ['company_name', 'company_email', 'admin_name', 'admin_email', 'password']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'الحقل {field} مطلوب'}), 400
        
        # التحقق من قوة كلمة المرور
        is_strong, msg = is_strong_password(data['password'])
        if not is_strong:
            return jsonify({'error': msg}), 400
        
        # التحقق من عدم التكرار
        if Organization.query.filter_by(email=data['company_email']).first():
            return jsonify({'error': 'البريد الإلكتروني للشركة مسجل مسبقاً'}), 400
        
        if User.query.filter_by(email=data['admin_email']).first():
            return jsonify({'error': 'البريد الإلكتروني لمدير الشركة مسجل مسبقاً'}), 400
        
        # إنشاء كود فريد للشركة
        import random
        import string
        org_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # إنشاء الشركة
        trial_end = datetime.utcnow() + timedelta(days=30)
        
        organization = Organization(
            org_code=org_code,
            name=data['company_name'],
            name_ar=data['company_name'],
            email=data['company_email'],
            phone=data.get('phone', ''),
            subscription_status='trial',
            trial_start=datetime.utcnow(),
            trial_end=trial_end,
            is_active=True,
            is_verified=False
        )
        organization.password = data['password']
        
        db.session.add(organization)
        db.session.flush()
        
        # إنشاء مدير الشركة
        admin = User(
            org_id=organization.id,
            username=data['admin_email'].split('@')[0],
            email=data['admin_email'],
            full_name=data['admin_name'],
            full_name_ar=data['admin_name'],
            phone=data.get('phone', ''),
            role='org_admin',
            is_user_active=True,
            is_verified=True
        )
        admin.set_password(data['password'])
        
        db.session.add(admin)
        db.session.commit()
        # إضافة إشعار ترحيبي لمدير الشركة
        NotificationService.user_registered(admin)
        
        # إشعار للمنصة بوجود شركة جديدة
        platform_admins = PlatformAdmin.query.all()
        for plat_admin in platform_admins:
            NotificationService.system_alert(
                user_id=plat_admin.id,
                title='🏢 شركة جديدة',
                message=f'تم تسجيل شركة {organization.name} بواسطة {admin.full_name}',
                priority='medium'
            )
        
        return jsonify({
            'success': True,
            'message': 'تم تسجيل الشركة بنجاح',
            'organization': {
                'id': organization.id,
                'name': organization.name,
                'code': organization.org_code
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/api/check-email', methods=['POST'])
def api_check_email():
    """التحقق من توفر البريد الإلكتروني"""
    data = request.get_json()
    email = data.get('email', '')
    
    user_exists = User.query.filter_by(email=email).first() is not None
    org_exists = Organization.query.filter_by(email=email).first() is not None
    
    return jsonify({
        'available': not (user_exists or org_exists),
        'message': 'البريد الإلكتروني متاح' if not (user_exists or org_exists) else 'البريد الإلكتروني مسجل مسبقاً'
    })

@auth_bp.route('/subscribe')
@login_required
def subscribe():
    """صفحة الاشتراك"""
    plans = [
        {'id': 'basic', 'name': 'Basic', 'price': 29, 'interval': 'شهري', 
        'features': ['5 مشاريع', '10 مستخدمين', 'تخزين 10 جيجابايت', 'دعم أساسي']},
        {'id': 'pro', 'name': 'Pro', 'price': 79, 'interval': 'شهري',
        'features': ['مشاريع غير محدودة', '50 مستخدمين', 'تخزين 50 جيجابايت', 'دعم priorit', 'تقارير متقدمة']},
        {'id': 'enterprise', 'name': 'Enterprise', 'price': 199, 'interval': 'شهري',
        'features': ['مشاريع غير محدودة', 'مستخدمين غير محدودين', 'تخزين 200 جيجابايت', 'دعم VIP', 'API مخصص']}
    ]
    
    return render_template('auth/subscribe.html', plans=plans, stripe_public_key=app.config['STRIPE_PUBLIC_KEY'])

@auth_bp.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout_session():
    """إنشاء جلسة دفع عبر Stripe"""
    try:
        plan_id = request.form.get('plan_id')
        plans = {
            'basic': {'price': 2900, 'name': 'Basic Plan'},  # بالسنت
            'pro': {'price': 7900, 'name': 'Pro Plan'},
            'enterprise': {'price': 19900, 'name': 'Enterprise Plan'}
        }
        
        if plan_id not in plans:
            return jsonify({'error': 'خطأ في اختيار الخطة'}), 400
        
        # إنشاء جلسة الدفع
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': plans[plan_id]['price'],
                    'product_data': {
                        'name': plans[plan_id]['name'],
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=url_for('payment_success', plan_id=plan_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('payment_cancel', _external=True),
            client_reference_id=current_user.id
        )
        
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        flash(f'حدث خطأ في عملية الدفع: {str(e)}', 'danger')
        return redirect(url_for('auth.subscribe'))

@auth_bp.route('/payment-success')
@login_required
def payment_success():
    """معالجة نجاح الدفع"""
    session_id = request.args.get('session_id')
    plan_id = request.args.get('plan_id')
    
    if session_id:
        try:
            # التحقق من صحة الجلسة
            checkout_session = stripe.checkout.Session.retrieve(session_id)
            
            if checkout_session.payment_status == 'paid':
                # تحديث حالة المستخدم
                current_user.is_paid = True
                current_user.subscription_end = datetime.utcnow() + timedelta(days=30)  # اشتراك شهر
                
                # تسجيل الاشتراك
                subscription = Subscription(
                    organ_id=current_user.id,
                    plan=plan_id,
                    amount=checkout_session.amount_total / 100,  # تحويل من سنت
                    currency=checkout_session.currency,
                    stripe_subscription_id=session_id,
                    stripe_customer_id=checkout_session.customer,
                    status='active',
                    end_date=datetime.utcnow() + timedelta(days=30)
                )
                db.session.add(subscription)
                db.session.commit()
                
                flash('تم الدفع بنجاح! شكراً لاشتراكك', 'success')
                
                # إرسال إشعار ترحيبي
                send_notification(
                    current_user.id,
                    'مرحباً بك في الباقة المدفوعة',
                    'تم تفعيل اشتراكك بنجاح. يمكنك الآن الاستفادة من جميع الميزات المتقدمة.',
                    'success'
                )
        except Exception as e:
            flash(f'حدث خطأ في تأكيد الدفع: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard.dashboard'))

@auth_bp.route('/payment-cancel')
@login_required
def payment_cancel():
    """معالجة إلغاء الدفع"""
    flash('تم إلغاء عملية الدفع. يمكنك المحاولة مرة أخرى في أي وقت.', 'info')
    return redirect(url_for('auth.subscribe'))

@auth_bp.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    """معالجة webhook من Stripe"""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, app.config['STRIPE_WEBHOOK_SECRET']
        )
    except ValueError:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
        return 'Invalid signature', 400
    
    # معالجة الأحداث
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('client_reference_id')
        if user_id:
            user = User.query.get(user_id)
            if user:
                user.is_paid = True
                user.subscription_end = datetime.utcnow() + timedelta(days=30)
                db.session.commit()
    
    return 'Success', 200
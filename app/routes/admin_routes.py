"""
admin_routes.py - مسارات إدارة النظام
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.models import db, User, Organization, Department, Project, SystemMetric,TaskAssignment,Task
from app.routes import admin_bp
from datetime import datetime, date, timedelta
import json

@admin_bp.route('/admin')
@login_required
def dashboard():
    """لوحة تحكم المدير"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح بالوصول إلى لوحة التحكم', 'danger')
        return redirect(url_for('dashboard.dashboard'))
    
    # إحصائيات النظام
    stats = {
        'total_users': User.query.filter_by(org_id=current_user.id).count(),
        'active_users': User.query.filter_by(org_id=current_user.id, is_active=True).count(),
        'total_projects': Project.query.filter_by(org_id=current_user.id).count(),
        'active_projects': Project.query.filter_by(org_id=current_user.id, status='active').count(),
        'total_departments': Department.query.filter_by(org_id=current_user.id).count(),
        'pending_approvals': User.query.filter_by(org_id=current_user.id, is_verified=False).count()
    }
    
    # النشاط الأخير
    recent_activities = get_recent_activities()
    
    # المستخدمون الجدد
    new_users = User.query.filter_by(org_id=current_user.id).order_by(
        User.created_at.desc()
    ).limit(5).all()
    
    # المشاريع الجديدة
    new_projects = Project.query.filter_by(org_id=current_user.id).order_by(
        Project.created_at.desc()
    ).limit(5).all()
    
    # مقاييس النظام
    system_metrics = get_system_metrics()
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         recent_activities=recent_activities,
                         new_users=new_users,
                         new_projects=new_projects,
                         system_metrics=system_metrics)

def get_recent_activities():
    """الحصول على الأنشطة الأخيرة"""
    # TODO: تنفيذ سجل الأنشطة
    return []

def get_system_metrics():
    """الحصول على مقاييس النظام"""
    metrics = SystemMetric.query.filter_by(project_id=None).order_by(
        SystemMetric.timestamp.desc()
    ).limit(10).all()
    
    return metrics

@admin_bp.route('/users')
@login_required
def users():
    """إدارة المستخدمين"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح بالوصول إلى إدارة المستخدمين', 'danger')
        return redirect(url_for('dashboard.index'))
    
    users = User.query.filter_by(org_id=current_user.org_id).order_by(User.created_at.desc()).all()
    
    # التصفية حسب الدور
    role_filter = request.args.get('role')
    if role_filter:
        users = [u for u in users if u.role == role_filter]
    
    # التصفية حسب الحالة
    status_filter = request.args.get('status')
    if status_filter == 'active':
        users = [u for u in users if u.is_active]
    elif status_filter == 'inactive':
        users = [u for u in users if not u.is_active]
    
    # البحث
    search_query = request.args.get('search')
    if search_query:
        users = [u for u in users if 
                search_query.lower() in u.full_name.lower() or 
                search_query.lower() in u.email.lower()]
    
    return render_template('admin/users.html', users=users)

@admin_bp.route('/users/<int:user_id>')
@login_required
def view_user(user_id):
    """عرض تفاصيل المستخدم"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    user = User.query.get_or_404(user_id)
    
    # التحقق من أن المستخدم في نفس المؤسسة
    if user.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('admin.users'))
    
    # المشاريع التي يديرها
    managed_projects = user.managed_projects[:10]
    
    # المهام التي يشرف عليها
    supervised_tasks = user.supervised_tasks[:10]
    
    # المهام المفوضة إليه
    delegate_tasks = user.delegate_tasks[:10]
    
    # المهام المعينة له
    assigned_tasks = Task.query.join(Task.assignments).filter(
        TaskAssignment.user_id == user_id
    ).limit(10).all()
    
    # المهارات
    user_skills = user.user_skills
    
    # سجل الدخول
    login_history = []  # TODO: تنفيذ سجل الدخول
    
    return render_template('admin/view_user.html',
                         user=user,
                         managed_projects=managed_projects,
                         supervised_tasks=supervised_tasks,
                         delegate_tasks=delegate_tasks,
                         assigned_tasks=assigned_tasks,
                         user_skills=user_skills,
                         login_history=login_history)

@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """تعديل بيانات المستخدم"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    user = User.query.get_or_404(user_id)
    
    # التحقق من أن المستخدم في نفس المؤسسة
    if user.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('admin.users'))
    
    if request.method == 'POST':
        try:
            # تحديث البيانات الأساسية
            user.full_name = request.form.get('full_name', user.full_name)
            user.full_name_ar = request.form.get('full_name_ar', user.full_name_ar)
            user.email = request.form.get('email', user.email)
            user.phone = request.form.get('phone', user.phone)
            user.mobile = request.form.get('mobile', user.mobile)
            user.job_title = request.form.get('job_title', user.job_title)
            user.job_title_ar = request.form.get('job_title_ar', user.job_title_ar)
            user.employee_id = request.form.get('employee_id', user.employee_id)
            user.national_id = request.form.get('national_id', user.national_id)
            user.birth_date = datetime.strptime(
                request.form.get('birth_date', user.birth_date.strftime('%Y-%m-%d')),
                '%Y-%m-%d'
            ).date() if request.form.get('birth_date') else user.birth_date
            user.hire_date = datetime.strptime(
                request.form.get('hire_date', user.hire_date.strftime('%Y-%m-%d')),
                '%Y-%m-%d'
            ).date() if request.form.get('hire_date') else user.hire_date
            
            # تحديث الدور
            user.role = request.form.get('role', user.role)
            
            # تحديث القسم
            dept_id = request.form.get('dept_id')
            if dept_id:
                user.dept_id = int(dept_id)
            
            # تحديث الحالة
            user.is_active = bool(request.form.get('is_active'))
            user.is_verified = bool(request.form.get('is_verified'))
            
            # تحديث الصلاحيات
            permissions = {}
            for field in ['view_projects', 'create_tasks', 'approve_expenses', 
                         'manage_users', 'view_reports', 'upload_documents']:
                permissions[field] = bool(request.form.get(f'permission_{field}'))
            user.permissions = permissions
            
            # تحديث كلمة المرور إذا تم إدخالها
            new_password = request.form.get('new_password')
            if new_password:
                confirm_password = request.form.get('confirm_password')
                if new_password == confirm_password:
                    user.set_password(new_password)
                    flash('تم تحديث كلمة المرور', 'success')
                else:
                    flash('كلمة المرور غير متطابقة', 'danger')
            
            db.session.commit()
            flash('تم تحديث بيانات المستخدم بنجاح', 'success')
            
            return redirect(url_for('admin.view_user', user_id=user_id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الحصول على الأقسام
    departments = Department.query.filter_by(org_id=current_user.org_id, is_active=True).all()
    
    return render_template('admin/edit_user.html', user=user, departments=departments)

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
def create_user():
    """إنشاء مستخدم جديد"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        try:
            # جمع بيانات المستخدم
            user_data = {
                'org_id': current_user.org_id,
                'username': request.form.get('username'),
                'email': request.form.get('email'),
                'full_name': request.form.get('full_name'),
                'full_name_ar': request.form.get('full_name_ar'),
                'phone': request.form.get('phone'),
                'mobile': request.form.get('mobile'),
                'job_title': request.form.get('job_title'),
                'job_title_ar': request.form.get('job_title_ar'),
                'employee_id': request.form.get('employee_id'),
                'national_id': request.form.get('national_id'),
                'birth_date': request.form.get('birth_date'),
                'hire_date': request.form.get('hire_date') or date.today().isoformat(),
                'role': request.form.get('role', 'employee'),
                'dept_id': request.form.get('dept_id'),
                'is_active': bool(request.form.get('is_active')),
                'is_verified': bool(request.form.get('is_verified'))
            }
            
            # التحقق من وجود المستخدم
            existing_user = User.query.filter_by(email=user_data['email']).first()
            if existing_user:
                flash('البريد الإلكتروني مسجل مسبقاً', 'danger')
                return render_template('admin/create_user.html')
            
            # تحويل التواريخ
            if user_data['birth_date']:
                user_data['birth_date'] = datetime.strptime(user_data['birth_date'], '%Y-%m-%d').date()
            if user_data['hire_date']:
                user_data['hire_date'] = datetime.strptime(user_data['hire_date'], '%Y-%m-%d').date()
            
            # إنشاء المستخدم
            user = User(**user_data)
            
            # تعيين كلمة المرور
            password = request.form.get('password')
            if password:
                user.set_password(password)
            else:
                # كلمة مرور افتراضية
                user.set_password('Password123!')
            
            # تعيين الصلاحيات
            permissions = {}
            for field in ['view_projects', 'create_tasks', 'approve_expenses', 
                         'manage_users', 'view_reports', 'upload_documents']:
                permissions[field] = bool(request.form.get(f'permission_{field}'))
            user.permissions = permissions
            
            db.session.add(user)
            db.session.commit()
            
            flash('تم إنشاء المستخدم بنجاح', 'success')
            return redirect(url_for('admin.view_user', user_id=user.id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الحصول على الأقسام
    departments = Department.query.filter_by(org_id=current_user.org_id, is_active=True).all()
    
    return render_template('admin/create_user.html', departments=departments)

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """حذف مستخدم"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    user = User.query.get_or_404(user_id)
    
    # التحقق من أن المستخدم في نفس المؤسسة
    if user.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('admin.users'))
    
    # التحقق من عدم حذف المستخدم الحالي
    if user.id == current_user.id:
        flash('لا يمكن حذف حسابك الخاص', 'danger')
        return redirect(url_for('admin.view_user', user_id=user_id))
    
    try:
        # حذف المستخدم
        db.session.delete(user)
        db.session.commit()
        
        flash('تم حذف المستخدم بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('admin.users'))

@admin_bp.route('/departments')
@login_required
def departments():
    """إدارة الأقسام"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    departments = Department.query.filter_by(org_id=current_user.org_id).order_by(
        Department.created_at.desc()
    ).all()
    
    return render_template('admin/departments.html', departments=departments)

@admin_bp.route('/departments/<int:dept_id>')
@login_required
def view_department(dept_id):
    """عرض تفاصيل القسم"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    department = Department.query.get_or_404(dept_id)
    
    # التحقق من أن القسم في نفس المؤسسة
    if department.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('admin.departments'))
    
    # موظفو القسم
    employees = department.employees
    
    # المشاريع المرتبطة (عبر الموظفين)
    projects = Project.query.join(User).filter(
        User.dept_id == dept_id
    ).distinct().all()
    
    return render_template('admin/view_department.html',
                         department=department,
                         employees=employees,
                         projects=projects)

@admin_bp.route('/departments/create', methods=['GET', 'POST'])
@login_required
def create_department():
    """إنشاء قسم جديد"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        try:
            # جمع بيانات القسم
            dept_data = {
                'org_id': current_user.org_id,
                'dept_code': request.form.get('dept_code'),
                'name': request.form.get('name'),
                'name_ar': request.form.get('name_ar'),
                'description': request.form.get('description'),
                'parent_id': request.form.get('parent_id'),
                'manager_id': request.form.get('manager_id'),
                'budget': float(request.form.get('budget', 0) or 0),
                'is_active': bool(request.form.get('is_active'))
            }
            
            # التحقق من عدم تكرار رمز القسم
            existing_dept = Department.query.filter_by(
                org_id=current_user.org_id,
                dept_code=dept_data['dept_code']
            ).first()
            
            if existing_dept:
                flash('رمز القسم مسجل مسبقاً', 'danger')
                return render_template('admin/create_department.html')
            
            # إنشاء القسم
            department = Department(**dept_data)
            
            db.session.add(department)
            db.session.commit()
            
            flash('تم إنشاء القسم بنجاح', 'success')
            return redirect(url_for('admin.view_department', dept_id=department.id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الحصول على الأقسام الرئيسية
    parent_departments = Department.query.filter_by(
        org_id=current_user.org_id,
        parent_id=None
    ).all()
    
    # الحصول على المدراء المحتملين
    potential_managers = User.query.filter(
    User.org_id == current_user.org_id,
    User.role.in_(['admin', 'project_manager', 'supervisor']),
    User.is_active == True
).all()
    
    return render_template('admin/create_department.html',
                         parent_departments=parent_departments,
                         potential_managers=potential_managers)

@admin_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_department(dept_id):
    """تعديل القسم"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    department = Department.query.get_or_404(dept_id)
    
    # التحقق من أن القسم في نفس المؤسسة
    if department.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('admin.departments'))
    
    if request.method == 'POST':
        try:
            # تحديث بيانات القسم
            department.name = request.form.get('name', department.name)
            department.name_ar = request.form.get('name_ar', department.name_ar)
            department.description = request.form.get('description', department.description)
            department.parent_id = request.form.get('parent_id')
            department.manager_id = request.form.get('manager_id')
            department.budget = float(request.form.get('budget', department.budget) or 0)
            department.is_active = bool(request.form.get('is_active'))
            
            db.session.commit()
            flash('تم تحديث بيانات القسم بنجاح', 'success')
            
            return redirect(url_for('admin.view_department', dept_id=dept_id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الحصول على الأقسام الرئيسية (باستثناء القسم الحالي وأقسامه الفرعية)
    parent_departments = Department.query.filter_by(
        org_id=current_user.org_id,
        parent_id=None
    ).filter(Department.id != dept_id).all()
    
    # الحصول على المدراء المحتملين
    potential_managers = User.query.filter_by(
        org_id=current_user.org_id,
        role=['admin', 'project_manager', 'supervisor'],
        is_active=True
    ).all()
    
    return render_template('admin/edit_department.html',
                         department=department,
                         parent_departments=parent_departments,
                         potential_managers=potential_managers)

@admin_bp.route('/departments/<int:dept_id>/delete', methods=['POST'])
@login_required
def delete_department(dept_id):
    """حذف قسم"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    department = Department.query.get_or_404(dept_id)
    
    # التحقق من أن القسم في نفس المؤسسة
    if department.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('admin.departments'))
    
    # التحقق من عدم وجود أقسام فرعية
    if department.sub_departments:
        flash('لا يمكن حذف قسم له أقسام فرعية', 'danger')
        return redirect(url_for('admin.view_department', dept_id=dept_id))
    
    # التحقق من عدم وجود موظفين في القسم
    if department.employees:
        flash('لا يمكن حذف قسم به موظفين', 'danger')
        return redirect(url_for('admin.view_department', dept_id=dept_id))
    
    try:
        # حذف القسم
        db.session.delete(department)
        db.session.commit()
        
        flash('تم حذف القسم بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('admin.departments'))

@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """إعدادات النظام"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    organization = Organization.query.get_or_404(current_user.org_id)
    
    if request.method == 'POST':
        try:
            # تحديث بيانات المؤسسة
            organization.name = request.form.get('name', organization.name)
            organization.name_ar = request.form.get('name_ar', organization.name_ar)
            organization.description = request.form.get('description', organization.description)
            organization.address = request.form.get('address', organization.address)
            organization.phone = request.form.get('phone', organization.phone)
            organization.email = request.form.get('email', organization.email)
            organization.website = request.form.get('website', organization.website)
            organization.tax_number = request.form.get('tax_number', organization.tax_number)
            organization.commercial_register = request.form.get('commercial_register', organization.commercial_register)
            
            # تحديث الإعدادات
            settings_data = organization.settings or {}
            settings_data['currency'] = request.form.get('currency', settings_data.get('currency', 'SAR'))
            settings_data['language'] = request.form.get('language', settings_data.get('language', 'ar'))
            settings_data['timezone'] = request.form.get('timezone', settings_data.get('timezone', 'Asia/Riyadh'))
            settings_data['date_format'] = request.form.get('date_format', settings_data.get('date_format', 'dd/MM/yyyy'))
            settings_data['decimal_places'] = int(request.form.get('decimal_places', settings_data.get('decimal_places', 2)))
            settings_data['auto_approve_threshold'] = float(request.form.get('auto_approve_threshold', settings_data.get('auto_approve_threshold', 50000)))
            
            organization.settings = settings_data
            
            db.session.commit()
            flash('تم تحديث إعدادات النظام بنجاح', 'success')
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('admin/settings.html', organization=organization)

@admin_bp.route('/system-logs')
@login_required
def system_logs():
    """سجلات النظام"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # TODO: تنفيذ نظام السجلات
    logs = []
    
    return render_template('admin/system_logs.html', logs=logs)

@admin_bp.route('/backup')
@login_required
def backup():
    """نسخ احتياطي للنظام"""
    
    # التحقق من الصلاحية
    if current_user.role != 'admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # TODO: تنفيذ النسخ الاحتياطي
    
    return render_template('admin/backup.html')

# API Routes للإدارة
@admin_bp.route('/api/users', methods=['GET'])
@login_required
def api_users():
    """API للحصول على قائمة المستخدمين"""
    try:
        # التحقق من الصلاحية
        if current_user.role != 'admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        users = User.query.filter_by(org_id=current_user.org_id).all()
        
        users_data = [{
            'id': u.id,
            'full_name': u.full_name,
            'full_name_ar': u.full_name_ar,
            'email': u.email,
            'phone': u.phone,
            'job_title': u.job_title,
            'role': u.role,
            'department': u.department.name if u.department else None,
            'is_active': u.is_active,
            'is_verified': u.is_verified,
            'created_at': u.created_at.isoformat() if u.created_at else None,
            'last_login': u.last_login.isoformat() if u.last_login else None
        } for u in users]
        
        return jsonify({'success': True, 'users': users_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/users/<int:user_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_user_detail(user_id):
    """API لإدارة مستخدم"""
    try:
        # التحقق من الصلاحية
        if current_user.role != 'admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        user = User.query.get_or_404(user_id)
        
        # التحقق من أن المستخدم في نفس المؤسسة
        if user.org_id != current_user.org_id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        if request.method == 'GET':
            user_data = {
                'id': user.id,
                'full_name': user.full_name,
                'full_name_ar': user.full_name_ar,
                'email': user.email,
                'phone': user.phone,
                'mobile': user.mobile,
                'job_title': user.job_title,
                'job_title_ar': user.job_title_ar,
                'employee_id': user.employee_id,
                'national_id': user.national_id,
                'birth_date': user.birth_date.isoformat() if user.birth_date else None,
                'hire_date': user.hire_date.isoformat() if user.hire_date else None,
                'role': user.role,
                'permissions': user.permissions,
                'department': {
                    'id': user.department.id,
                    'name': user.department.name
                } if user.department else None,
                'is_active': user.is_active,
                'is_verified': user.is_verified,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'last_login': user.last_login.isoformat() if user.last_login else None
            }
            
            return jsonify({'success': True, 'user': user_data}), 200
        
        elif request.method == 'PUT':
            data = request.get_json()
            
            # تحديث البيانات المسموح بها
            allowed_fields = [
                'full_name', 'full_name_ar', 'email', 'phone', 'mobile',
                'job_title', 'job_title_ar', 'employee_id', 'national_id',
                'birth_date', 'hire_date', 'role', 'dept_id',
                'is_active', 'is_verified'
            ]
            
            for field in allowed_fields:
                if field in data:
                    if field in ['birth_date', 'hire_date'] and data[field]:
                        setattr(user, field, datetime.strptime(data[field], '%Y-%m-%d').date())
                    else:
                        setattr(user, field, data[field])
            
            # تحديث الصلاحيات إذا تم إرسالها
            if 'permissions' in data:
                user.permissions = data['permissions']
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم تحديث بيانات المستخدم بنجاح'
            }), 200
        
        elif request.method == 'DELETE':
            # التحقق من عدم حذف المستخدم الحالي
            if user.id == current_user.id:
                return jsonify({'error': 'لا يمكن حذف حسابك الخاص'}), 400
            
            db.session.delete(user)
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'تم حذف المستخدم بنجاح'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/departments', methods=['GET', 'POST'])
@login_required
def api_departments():
    """API لإدارة الأقسام"""
    try:
        # التحقق من الصلاحية
        if current_user.role != 'admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        if request.method == 'GET':
            departments = Department.query.filter_by(org_id=current_user.org_id).all()
            
            departments_data = [{
                'id': d.id,
                'dept_code': d.dept_code,
                'name': d.name,
                'name_ar': d.name_ar,
                'description': d.description,
                'parent_id': d.parent_id,
                'manager': d.manager.full_name if d.manager else None,
                'budget': d.budget,
                'is_active': d.is_active,
                'employee_count': len(d.employees),
                'sub_departments_count': len(d.sub_departments)
            } for d in departments]
            
            return jsonify({'success': True, 'departments': departments_data}), 200
        
        elif request.method == 'POST':
            data = request.get_json()
            
            # التحقق من البيانات المطلوبة
            required_fields = ['dept_code', 'name']
            for field in required_fields:
                if field not in data:
                    return jsonify({'error': f'حقل {field} مطلوب'}), 400
            
            # التحقق من عدم تكرار رمز القسم
            existing_dept = Department.query.filter_by(
                org_id=current_user.org_id,
                dept_code=data['dept_code']
            ).first()
            
            if existing_dept:
                return jsonify({'error': 'رمز القسم مسجل مسبقاً'}), 400
            
            # إنشاء القسم
            department = Department(
                org_id=current_user.org_id,
                dept_code=data['dept_code'],
                name=data['name'],
                name_ar=data.get('name_ar'),
                description=data.get('description'),
                parent_id=data.get('parent_id'),
                manager_id=data.get('manager_id'),
                budget=data.get('budget', 0),
                is_active=data.get('is_active', True)
            )
            
            db.session.add(department)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم إنشاء القسم بنجاح',
                'department': {
                    'id': department.id,
                    'dept_code': department.dept_code,
                    'name': department.name
                }
            }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_bp.route('/api/system-metrics')
@login_required
def api_system_metrics():
    """API للحصول على مقاييس النظام"""
    try:
        # التحقق من الصلاحية
        if current_user.role != 'admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        # مقاييس النظام
        metrics = SystemMetric.query.filter_by(project_id=None).order_by(
            SystemMetric.timestamp.desc()
        ).limit(50).all()
        
        metrics_data = [{
            'id': m.id,
            'metric_type': m.metric_type,
            'metric_name': m.metric_name,
            'value': m.value,
            'timestamp': m.timestamp.isoformat() if m.timestamp else None,
            'metadata': m.metadata
        } for m in metrics]
        
        return jsonify({'success': True, 'metrics': metrics_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
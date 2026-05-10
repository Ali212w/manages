"""
enterprise_routes.py - مسارات نظام Enterprise (إعدادات المؤسسة)
"""
from ..extensions import db
from flask import render_template, request, redirect, url_for, flash, jsonify, g,send_file
from flask_login import login_required, current_user
from app.models import User, Organization, Department, Project, Task,Notification
from app.models import (
    EPS, WBS, Calendar, Activity, ActivityRelationship,
    Resource, ActivityResource, Baseline,EPSOBSAssignment,Meeting,Issue,TaskPlanning,
    OBS, ResourceCode, ActivityCodeDictionary,ActivityCodeValue,ActivityCodeAssignment,Role, UDF, GlobalChange, AdminPreference,ResourceDelivery
)

from app.routes import enterprise_bp
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_
import json
from app.services.notification_service import NotificationService
import re
import pandas as pd
import io
# ============================================
# دوال مساعدة للتحقق من الصلاحيات
# ============================================

def check_enterprise_access():
    """التحقق من صلاحية الوصول لإعدادات المؤسسة"""
    if current_user.role not in ['platform_admin', 'org_admin']:
        flash('غير مصرح بالوصول إلى إعدادات المؤسسة', 'danger')
        return False
    return True

def get_org_id():
    """الحصول على معرف المؤسسة"""
    if current_user.role == 'platform_admin':
        return None
    return current_user.org_id

@enterprise_bp.before_request
def load_company():
    if current_user.is_authenticated:
        g.company = Organization.query.get(current_user.org_id)
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        g.delayed_tasks_count = Task.query.join(Project).filter(
            Task.status.in_(['pending', 'in_progress']),
            TaskPlanning.planned_finish < date.today()
        ).count()
        g.pending_deliveries_count = ResourceDelivery.query.filter_by(
            status='pending'
        ).count() if current_user.role in ['org_admin', 'project_manager'] else 0
        
        # إضافة إحصائيات الموارد
        g.low_stock_resources = Resource.query.filter(
            Resource.available_quantity < Resource.minimum_quantity
        ).count() if hasattr(Resource, 'minimum_quantity') else 0
        # ⭐ إحصائيات الاجتماعات القادمة
        # ========== الاجتماعات القادمة ==========
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        
        upcoming_meetings_query = Meeting.query.filter(
            Meeting.project.has(org_id=current_user.org_id),
            Meeting.scheduled_date >= today,
            Meeting.scheduled_date <= next_week,
            Meeting.status == 'scheduled'
        ).order_by(Meeting.scheduled_date)
        
        # الحصول على القائمة للعرض
        g.upcoming_meetings = upcoming_meetings_query.limit(5).all()
        
        # ✅ حساب العدد بشكل صحيح
        g.upcoming_meetings_count = upcoming_meetings_query.count()
        
        # ========== القضايا المفتوحة ==========
        open_issues_count = Issue.query.join(Project).filter(
            Project.org_id == current_user.org_id,
            Issue.status.in_(['open', 'in_progress'])
        ).count()
        g.open_issues_count = open_issues_count
        
        # آخر 5 قضايا
        recent_issues = Issue.query.join(Project).filter(
            Project.org_id == current_user.org_id
        ).order_by(Issue.reported_date.desc()).limit(5).all()
        g.recent_issues = recent_issues
        
        # إحصائيات القضايا
        g.issues_stats = {
            'open': Issue.query.join(Project).filter(
                Project.org_id == current_user.org_id, 
                Issue.status == 'open'
            ).count(),
            'in_progress': Issue.query.join(Project).filter(
                Project.org_id == current_user.org_id, 
                Issue.status == 'in_progress'
            ).count(),
            'total': Issue.query.join(Project).filter(
                Project.org_id == current_user.org_id
            ).count()
        }
    else:
        g.company = None
        g.upcoming_meetings =None
        g.recent_issues=None
        g.delayed_tasks_count = 0
        g.notifications_count = 0
        g.pending_deliveries_count=0
        g.low_stock_resources=0
        g.upcoming_meetings_count=0
        g.open_issues_count =0
        g.issues_stats={}
# ============================================
# الصفحة الرئيسية لـ Enterprise
# ============================================

@enterprise_bp.route('/')
@login_required
def index():
    """الصفحة الرئيسية لمركز المؤسسة"""
    if not check_enterprise_access():
        return redirect(url_for('company.dashboard'))
    
    # إحصائيات سريعة
    org_id = get_org_id()
    
    stats = {
        'eps_count': EPS.query.filter_by(org_id=org_id).count() if org_id else EPS.query.count(),
        'obs_count': OBS.query.filter_by(org_id=org_id).count() if org_id else OBS.query.count(),
        'resources_count': Resource.query.filter_by(org_id=org_id).count() if org_id else Resource.query.count(),
        'roles_count': Role.query.filter_by(org_id=org_id).count() if org_id else Role.query.count(),
        'calendars_count': Calendar.query.filter_by(org_id=org_id).count() if org_id else Calendar.query.count(),
        'activity_codes_count': ActivityCodeDictionary.query.filter_by(org_id=org_id).count() if org_id else ActivityCodeDictionary.query.count(),
    }
    
    return render_template('enterprise/index.html', stats=stats)

# ============================================
# 1️⃣ EPS – Enterprise Project Structure
# ============================================

@enterprise_bp.route('/eps')
@login_required
def eps_list():
    """عرض هيكل المؤسسة"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        eps_nodes = EPS.query.filter_by(org_id=org_id).order_by(EPS.level, EPS.eps_code).all()
    else:
        eps_nodes = EPS.query.order_by(EPS.level, EPS.eps_code).all()
    
    root_nodes = [n for n in eps_nodes if n.parent_id is None]
    managers = User.query.filter(
        User.org_id == current_user.org_id,
        User.role.in_(['org_admin', 'project_manager']),
        User.is_user_active == True
    ).all()
    return render_template('enterprise/eps/index.html',
                         eps_nodes=eps_nodes,
                         root_nodes=root_nodes,managers=managers)

@enterprise_bp.route('/eps/create', methods=['GET', 'POST'])
@login_required
def eps_create():
    """إنشاء عنصر EPS جديد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الرمز
            existing = EPS.query.filter_by(
                org_id=current_user.org_id,
                eps_code=request.form.get('eps_code')
            ).first()
            
            if existing:
                flash('رمز EPS موجود مسبقاً', 'danger')
                return redirect(url_for('enterprise.eps_create'))
            
            eps = EPS(
                org_id=current_user.org_id,
                eps_code=request.form.get('eps_code'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                parent_id=request.form.get('parent_id') or None,
                manager_id=request.form.get('manager_id') or None
            )
            
            if eps.parent_id:
                parent = EPS.query.get(eps.parent_id)
                eps.path = f"{parent.path}/{eps.eps_code}" if parent.path else eps.eps_code
                eps.level = parent.level + 1
            else:
                eps.path = eps.eps_code
                eps.level = 1
            
            db.session.add(eps)
            db.session.commit()
            
            flash('تم إنشاء عنصر EPS بنجاح', 'success')
            return redirect(url_for('enterprise.eps_view', eps_id=eps.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    parents = EPS.query.filter_by(org_id=current_user.org_id).all()
    managers = User.query.filter(
        User.org_id == current_user.org_id,
        User.role.in_(['org_admin', 'project_manager']),
        User.is_user_active == True
    ).all()
    
    return render_template('enterprise/eps/create.html',
                         parents=parents,
                         managers=managers)

@enterprise_bp.route('/eps/<int:eps_id>')
@login_required
def eps_view(eps_id):
    """عرض تفاصيل عنصر EPS"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    eps = EPS.query.get_or_404(eps_id)
    children = EPS.query.filter_by(parent_id=eps_id).all()
    projects = Project.query.filter_by(eps_id=eps_id).all()
    
    return render_template('enterprise/eps/view.html',
                         eps=eps,
                         children=children,
                         projects=projects)
@enterprise_bp.route('/eps/<int:eps_id>/edit', methods=['GET', 'POST'])
@login_required
def eps_edit(eps_id):
    """تعديل عنصر EPS"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    eps = EPS.query.get_or_404(eps_id)
    
    if request.method == 'POST':
        try:
            eps.name = request.form.get('name', eps.name)
            eps.description = request.form.get('description', eps.description)
            eps.manager_id = request.form.get('manager_id') or None
            
            db.session.commit()
            flash('تم تحديث عنصر EPS بنجاح', 'success')
            return redirect(url_for('enterprise.eps_view', eps_id=eps.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    managers = User.query.filter(
        User.org_id == current_user.org_id,
        User.role.in_(['org_admin', 'project_manager']),
        User.is_user_active == True
    ).all()
    
    return render_template('enterprise/eps/edit.html', eps=eps, managers=managers)

@enterprise_bp.route('/eps/<int:eps_id>/delete', methods=['POST'])
@login_required
def eps_delete(eps_id):
    """حذف عنصر EPS"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    eps = EPS.query.get_or_404(eps_id)
    
    # التحقق من عدم وجود عناصر فرعية
    if EPS.query.filter_by(parent_id=eps_id).first():
        return jsonify({'error': 'لا يمكن حذف عنصر له عناصر فرعية'}), 400
    
    # التحقق من عدم وجود مشاريع مرتبطة
    if Project.query.filter_by(eps_id=eps_id).first():
        return jsonify({'error': 'لا يمكن حذف عنصر مرتبط بمشاريع'}), 400
    
    try:
        db.session.delete(eps)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
# ============================================
# 2️⃣ OBS – Organizational Breakdown Structure
# ============================================



@enterprise_bp.route('/obs')
@login_required
def obs_list():
    """عرض هيكل المسؤولية"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        obs_nodes = OBS.query.filter_by(org_id=org_id).order_by(OBS.level, OBS.obs_code).all()
    else:
        obs_nodes = OBS.query.order_by(OBS.level, OBS.obs_code).all()
    
    root_nodes = [n for n in obs_nodes if n.parent_id is None]
    
    parents = OBS.query.filter_by(org_id=org_id).all()
    users = User.query.filter_by(org_id=org_id, is_user_active=True).all()
    return render_template('enterprise/obs/index.html',
                         obs_nodes=obs_nodes,
                         root_nodes=root_nodes,
                         parents=parents,
                         users=users)

@enterprise_bp.route('/obs/create', methods=['GET', 'POST'])
@login_required
def obs_create():
    """إنشاء عنصر OBS جديد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    org_id = get_org_id()
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الرمز
            existing = OBS.query.filter_by(
                org_id=current_user.org_id,
                obs_code=request.form.get('obs_code')
            ).first()
            
            if existing:
                flash('رمز OBS موجود مسبقاً', 'danger')
                return redirect(url_for('enterprise.obs_create'))
            
            obs = OBS(
                org_id=current_user.org_id,
                obs_code=request.form.get('obs_code'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                parent_id=request.form.get('parent_id') or None,
                responsible_id=request.form.get('responsible_id') or None
            )
            
            if obs.parent_id:
                parent = OBS.query.get(obs.parent_id)
                obs.path = f"{parent.path}/{obs.obs_code}" if parent.path else obs.obs_code
                obs.level = parent.level + 1
            else:
                obs.path = obs.obs_code
                obs.level = 1
            
            db.session.add(obs)
            db.session.commit()
            
            flash('تم إنشاء عنصر OBS بنجاح', 'success')
            return redirect(url_for('enterprise.obs_view', obs_id=obs.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    parents = OBS.query.filter_by(org_id=org_id).all()
    users = User.query.filter_by(org_id=org_id, is_user_active=True).all()
    
    return render_template('enterprise/obs/create.html',
                         parents=parents,
                         users=users)
@enterprise_bp.route('/obs/<int:parent_id>/create-child', methods=['GET', 'POST'])
@login_required
def obs_create_child(parent_id):
    """إنشاء عنصر فرعي تحت عنصر OBS موجود"""
    # جلب العنصر الأب
    parent_obs = OBS.query.get_or_404(parent_id)
    
    # التحقق من الصلاحية
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الرمز
            existing = OBS.query.filter_by(
                org_id=current_user.org_id,
                obs_code=request.form.get('obs_code')
            ).first()
            
            if existing:
                flash('رمز OBS موجود مسبقاً', 'danger')
                return redirect(url_for('enterprise.obs_create_child', parent_id=parent_id))
            
            # إنشاء العنصر الفرعي
            child_obs = OBS(
                org_id=current_user.org_id,
                obs_code=request.form.get('obs_code'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                parent_id=parent_id,
                responsible_id=request.form.get('responsible_id') or None
            )
            
            # حساب المستوى والمسار
            child_obs.level = parent_obs.level + 1
            child_obs.path = f"{parent_obs.path}/{child_obs.obs_code}" if parent_obs.path else child_obs.obs_code
            
            db.session.add(child_obs)
            db.session.commit()
            
            # إشعار للمسؤول الجديد
            if child_obs.responsible_id:
                NotificationService.assign_responsible_id(
                    user_id=child_obs.responsible_id,
                    title='📋 مسؤولية جديدة',
                    message=f'تم تعيينك كمسؤول عن {child_obs.name} تحت {parent_obs.name}',
                    priority='medium'
                )
            
            flash(f'تم إنشاء العنصر الفرعي {child_obs.name} بنجاح تحت {parent_obs.name}', 'success')
            return redirect(url_for('enterprise.obs_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # جلب المستخدمين لاختيار المسؤول
    users = User.query.filter_by(org_id=current_user.org_id, is_user_active=True).all()
    
    return render_template('enterprise/obs/obs_create_child.html',
                         parent_obs=parent_obs,
                         users=users)

@enterprise_bp.route('/obs/<int:obs_id>')
@login_required
def obs_view(obs_id):
    """عرض تفاصيل عنصر OBS"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    obs = OBS.query.get_or_404(obs_id)
    children = OBS.query.filter_by(parent_id=obs_id).all()
    
    # المشاريع المرتبطة بهذا العنصر
    projects = Project.query.filter_by(obs_id=obs_id).all()
    
    return render_template('enterprise/obs/view.html',
                         obs=obs,
                         children=children,
                         projects=projects)

@enterprise_bp.route('/obs/<int:obs_id>/edit', methods=['GET', 'POST'])
@login_required
def obs_edit(obs_id):
    """تعديل عنصر OBS"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    obs = OBS.query.get_or_404(obs_id)
    
    if request.method == 'POST':
        try:
            obs.name = request.form.get('name', obs.name)
            obs.description = request.form.get('description', obs.description)
            obs.responsible_id = request.form.get('responsible_id') or None
            
            db.session.commit()
            flash('تم تحديث عنصر OBS بنجاح', 'success')
            return redirect(url_for('enterprise.obs_view', obs_id=obs.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    users = User.query.filter_by(org_id=current_user.org_id, is_user_active=True).all()
    
    return render_template('enterprise/obs/edit.html', obs=obs, users=users)

@enterprise_bp.route('/obs/<int:obs_id>/delete', methods=['POST'])
@login_required
def obs_delete(obs_id):
    """حذف عنصر OBS"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    obs = OBS.query.get_or_404(obs_id)
    
    if OBS.query.filter_by(parent_id=obs_id).first():
        return jsonify({'error': 'لا يمكن حذف عنصر له عناصر فرعية'}), 400
    
    try:
        db.session.delete(obs)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
# ============================================
# 3️⃣ Resources – الموارد
# ============================================

@enterprise_bp.route('/resources')
@login_required
def resources_list():
    """عرض قائمة الموارد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    # جلب جميع الموارد
    if org_id:
        resources = Resource.query.filter_by(org_id=org_id).all()
    else:
        resources = Resource.query.all()
    
    # جلب أكواد التصنيف
    dept_codes = ResourceCode.query.filter_by(org_id=org_id, code_type='department').all()
    skill_codes = ResourceCode.query.filter_by(org_id=org_id, code_type='skill').all()
    certification_codes = ResourceCode.query.filter_by(org_id=org_id, code_type='certification').all()
    location_codes = ResourceCode.query.filter_by(org_id=org_id, code_type='location').all()
    project_codes = ResourceCode.query.filter_by(org_id=org_id, code_type='project').all()
    
    # إحصائيات
    stats = {
        'labor_count': sum(1 for r in resources if r.resource_type == 'labor'),
        'equipment_count': sum(1 for r in resources if r.resource_type == 'equipment'),
        'material_count': sum(1 for r in resources if r.resource_type == 'material'),
    }
    
    codes_count = (len(dept_codes) + len(skill_codes) + len(certification_codes) + 
                   len(location_codes) + len(project_codes))
    employees = User.query.filter_by(org_id=current_user.org_id, is_user_active=True,role="employee").all()
    suppliers = User.query.filter_by(org_id=current_user.org_id, is_user_active=True,role="supplier").all()
    return render_template('enterprise/resources/index.html',
                         resources=resources,
                         stats=stats,
                         codes_count=codes_count,
                         dept_codes=dept_codes,
                         skill_codes=skill_codes,
                         certification_codes=certification_codes,
                         location_codes=location_codes,
                         employees=employees,
                         suppliers=suppliers,
                         project_codes=project_codes)

@enterprise_bp.route('/api/resources/add', methods=['POST'])
@login_required
def api_resource_add():
    """API لإضافة مورد جديد"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم تكرار الكود
        existing = Resource.query.filter_by(
            org_id=current_user.org_id,
            resource_id=data.get('code')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'كود المورد موجود مسبقاً'}), 400
        
        # إنشاء المورد حسب النوع
        resource = Resource(
            org_id=current_user.org_id,
            resource_id=data.get('code'),
            name=data.get('name'),
            resource_type=data.get('type'),
            currency=data.get('currency', 'SAR'),
            is_active=True
        )
        
        # إضافة الحقول الخاصة حسب النوع
        if data.get('type') == 'labor':
            resource.employee_id = data.get('employeeId')
            resource.specialization = data.get('specialization')
            resource.skills = data.get('skills', [])
            resource.certifications = data.get('certs', [])
            resource.cost_per_unit = float(data.get('hourlyRate', 0))
            resource.unit = 'hour'
            
        elif data.get('type') == 'equipment':
            resource.equipment_type = data.get('equipmentType')
            resource.cost_per_unit = float(data.get('dailyRate', 0))
            resource.unit = 'day'
            resource.supplier = data.get('supplier_id')
            resource.maintenance_schedule = {
                'last': data.get('lastMaintenance'),
                'next': data.get('nextMaintenance'),
                'cycle': data.get('maintenanceCycle')
            }
            
        elif data.get('type') == 'material':
            resource.material_type = data.get('materialType')
            resource.unit = data.get('materialUnit')
            resource.cost_per_unit = float(data.get('unitPrice', 0))
            resource.available_quantity = float(data.get('availableQty', 0))
            resource.supplier = data.get('supplier_id')
        
        # إضافة أكواد التصنيف
        resource.classification_codes = {
            'department': data.get('deptCode'),
            'location': data.get('locationCode'),
            'project': data.get('projectCode')
        }
        
        db.session.add(resource)
        db.session.commit()
        
        return jsonify({'success': True, 'id': resource.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
@enterprise_bp.route('/resources/create', methods=['GET', 'POST'])
@login_required
def resource_create():
    """إنشاء مورد جديد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الرمز
            existing = Resource.query.filter_by(
                org_id=current_user.org_id,
                resource_id=request.form.get('resource_id')
            ).first()
            
            if existing:
                flash('رمز المورد موجود مسبقاً', 'danger')
                return redirect(url_for('enterprise.resource_create'))
            
            resource = Resource(
                org_id=current_user.org_id,
                resource_id=request.form.get('resource_id'),
                name=request.form.get('name'),
                resource_type=request.form.get('resource_type'),
                unit=request.form.get('unit'),
                cost_per_unit=float(request.form.get('cost_per_unit', 0)),
                currency=request.form.get('currency', 'SAR'),
                available_quantity=float(request.form.get('available_quantity', 0)),
                calendar_id=request.form.get('calendar_id') or None,
                specifications=json.loads(request.form.get('specifications', '{}'))
            )
            
            db.session.add(resource)
            db.session.commit()
            
            flash('تم إنشاء المورد بنجاح', 'success')
            return redirect(url_for('enterprise.resources_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    calendars = Calendar.query.filter_by(org_id=current_user.org_id).all()
    return render_template('enterprise/resources/create.html', calendars=calendars)
@enterprise_bp.route('/resources/<int:resource_id>/edit', methods=['GET', 'POST'])
@login_required
def resource_edit(resource_id):
    """تعديل مورد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    resource = Resource.query.get_or_404(resource_id)
    
    if request.method == 'POST':
        try:
            resource.name = request.form.get('name', resource.name)
            resource.resource_type = request.form.get('resource_type', resource.resource_type)
            resource.unit = request.form.get('unit', resource.unit)
            resource.cost_per_unit = float(request.form.get('cost_per_unit', resource.cost_per_unit))
            resource.currency = request.form.get('currency', resource.currency)
            resource.available_quantity = float(request.form.get('available_quantity', resource.available_quantity))
            resource.calendar_id = request.form.get('calendar_id') or None
            resource.specifications = json.loads(request.form.get('specifications', '{}'))
            
            db.session.commit()
            flash('تم تحديث المورد بنجاح', 'success')
            return redirect(url_for('enterprise.resources_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    calendars = Calendar.query.filter_by(org_id=current_user.org_id).all()
    return render_template('enterprise/resources/edit.html', resource=resource, calendars=calendars)

@enterprise_bp.route('/resources/<int:resource_id>/delete', methods=['POST'])
@login_required
def resource_delete(resource_id):
    """حذف مورد"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    resource = Resource.query.get_or_404(resource_id)
    
    try:
        db.session.delete(resource)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# 4️⃣ Roles – الأدوار الوظيفية
# ============================================



@enterprise_bp.route('/roles')
@login_required
def roles_list():
    """عرض قائمة الأدوار"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        roles = Role.query.filter_by(org_id=org_id).all()
    else:
        roles = Role.query.all()
    
    return render_template('enterprise/roles/index.html', roles=roles)

@enterprise_bp.route('/roles/create', methods=['GET', 'POST'])
@login_required
def role_create():
    """إنشاء دور جديد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الرمز
            existing = Role.query.filter_by(
                org_id=current_user.org_id,
                role_code=request.form.get('role_code')
            ).first()
            
            if existing:
                flash('رمز الدور موجود مسبقاً', 'danger')
                return redirect(url_for('enterprise.role_create'))
            
            # معالجة المهارات
            skills = request.form.getlist('skills[]') or []
            
            role = Role(
                org_id=current_user.org_id,
                role_code=request.form.get('role_code'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                default_cost_per_hour=float(request.form.get('default_cost_per_hour', 0)),
                currency=request.form.get('currency', 'SAR'),
                required_skills=skills
            )
            
            db.session.add(role)
            db.session.commit()
            
            flash('تم إنشاء الدور بنجاح', 'success')
            return redirect(url_for('enterprise.roles_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('enterprise/roles/create.html')

@enterprise_bp.route('/roles/<int:role_id>/edit', methods=['GET', 'POST'])
@login_required
def role_edit(role_id):
    """تعديل دور"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    role = Role.query.get_or_404(role_id)
    
    if request.method == 'POST':
        try:
            role.name = request.form.get('name', role.name)
            role.description = request.form.get('description', role.description)
            role.default_cost_per_hour = float(request.form.get('default_cost_per_hour', role.default_cost_per_hour))
            role.currency = request.form.get('currency', role.currency)
            role.required_skills = request.form.getlist('skills[]') or []
            
            db.session.commit()
            flash('تم تحديث الدور بنجاح', 'success')
            return redirect(url_for('enterprise.roles_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('enterprise/roles/edit.html', role=role)

@enterprise_bp.route('/roles/<int:role_id>/delete', methods=['POST'])
@login_required
def role_delete(role_id):
    """حذف دور"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    role = Role.query.get_or_404(role_id)
    
    try:
        db.session.delete(role)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@enterprise_bp.route('/api/role/<int:role_id>')
@login_required
def api_role_detail(role_id):
    """API للحصول على تفاصيل دور"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    role = Role.query.get_or_404(role_id)
    
    resources = Resource.query.filter_by(org_id=current_user.org_id).all()
    
    return jsonify({
        'success': True,
        'role': {
            'id': role.id,
            'name': role.name,
            'description': role.description,
            'code': role.role_code,
            'cost': role.default_cost_per_hour,
            'currency': role.currency,
            'skills': role.required_skills
        },
        'resources': [{
            'id': r.id,
            'name': r.name,
            'resource_type': r.resource_type,
            'unit': r.unit
        } for r in resources]
    })

@enterprise_bp.route('/api/assign-role', methods=['POST'])
@login_required
def api_assign_role():
    """API لتعيين دور لمورد"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    # TODO: تنفيذ منطق تعيين الدور لمورد
    # يمكن إنشاء جدول ResourceRoleAssignments لربط الموارد بالأدوار
    
    return jsonify({'success': True})
# ============================================
# 5️⃣ Resource Codes – أكواد الموارد
# ============================================



@enterprise_bp.route('/resource-codes')
@login_required
def resource_codes_list():
    """عرض أكواد الموارد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        codes = ResourceCode.query.filter_by(org_id=org_id).order_by(ResourceCode.code_type).all()
    else:
        codes = ResourceCode.query.order_by(ResourceCode.code_type).all()
    
    # تجميع حسب النوع
    grouped_codes = {}
    for code in codes:
        if code.code_type not in grouped_codes:
            grouped_codes[code.code_type] = []
        grouped_codes[code.code_type].append(code)
    
    return render_template('enterprise/resource_codes/index.html', grouped_codes=grouped_codes)

@enterprise_bp.route('/api/resource-codes/<int:code_id>', methods=['GET'])
@login_required
def api_resource_code_get(code_id):
    """API لجلب بيانات كود مورد"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    code = ResourceCode.query.get_or_404(code_id)
    
    return jsonify({
        'success': True,
        'code': {
            'id': code.id,
            'code_type': code.code_type,
            'code_value': code.code_value,
            'code_description': code.code_description
        }
    })

@enterprise_bp.route('/api/resource-codes/<int:code_id>/update', methods=['POST'])
@login_required
def api_resource_code_update(code_id):
    """API لتحديث كود مورد"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    code = ResourceCode.query.get_or_404(code_id)
    data = request.get_json()
    
    try:
        if 'code_type' in data:
            code.code_type = data['code_type']
        if 'code_value' in data:
            # التحقق من عدم تكرار القيمة (إذا تغيرت)
            if data['code_value'] != code.code_value:
                existing = ResourceCode.query.filter_by(
                    org_id=current_user.org_id,
                    code_type=code.code_type,
                    code_value=data['code_value']
                ).first()
                if existing:
                    return jsonify({'success': False, 'error': 'قيمة الكود موجودة مسبقاً'}), 400
            code.code_value = data['code_value']
        if 'code_description' in data:
            code.code_description = data['code_description']
        
        db.session.commit()
        return jsonify({'success': True, 'id': code.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# تحديث Route الإضافة للتحقق من التكرار
@enterprise_bp.route('/api/resource-codes/add', methods=['POST'])
@login_required
def api_resource_code_add():
    """API لإضافة كود مورد جديد"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم تكرار الكود
        existing = ResourceCode.query.filter_by(
            org_id=current_user.org_id,
            code_type=data.get('code_type'),
            code_value=data.get('code_value')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'قيمة الكود موجودة مسبقاً لهذا النوع'}), 400
        
        code = ResourceCode(
            org_id=current_user.org_id,
            code_type=data.get('code_type'),
            code_value=data.get('code_value'),
            code_description=data.get('code_description')
        )
        
        db.session.add(code)
        db.session.commit()
        
        return jsonify({'success': True, 'id': code.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@enterprise_bp.route('/api/resource-codes/<int:code_id>/delete', methods=['POST'])
@login_required
def api_resource_code_delete(code_id):
    """API لحذف كود مورد"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    code = ResourceCode.query.get_or_404(code_id)
    
    try:
        db.session.delete(code)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
# ============================================
# 6️⃣ Activity Codes – أكواد الأنشطة
# ============================================



@enterprise_bp.route('/activity-codes')
@login_required
def activity_codes_list():
    """عرض أكواد الأنشطة"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        codes = ActivityCode.query.filter_by(org_id=org_id).order_by(ActivityCode.code_type).all()
    else:
        codes = ActivityCode.query.order_by(ActivityCode.code_type).all()
    
    # تجميع حسب النوع
    grouped_codes = {}
    for code in codes:
        if code.code_type not in grouped_codes:
            grouped_codes[code.code_type] = []
        grouped_codes[code.code_type].append(code)
    
    return render_template('enterprise/activity_codes/ndex.html', grouped_codes=grouped_codes)

@enterprise_bp.route('/api/activity-codes/<int:code_id>', methods=['GET'])
@login_required
def api_activity_code_get(code_id):
    """API لجلب بيانات كود نشاط"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    code = ActivityCode.query.get_or_404(code_id)
    
    return jsonify({
        'success': True,
        'code': {
            'id': code.id,
            'code_scope': code.code_scope,
            'code_type': code.code_type,
            'code_value': code.code_value,
            'code_description': code.code_description,
            'code_color': code.code_color
        }
    })

@enterprise_bp.route('/api/activity-codes/<int:code_id>/update', methods=['POST'])
@login_required
def api_activity_code_update(code_id):
    """API لتحديث كود نشاط"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    code = ActivityCode.query.get_or_404(code_id)
    data = request.get_json()
    
    try:
        # التحقق من عدم تكرار القيمة (إذا تغيرت)
        if 'code_value' in data and data['code_value'] != code.code_value:
            existing = ActivityCode.query.filter_by(
                org_id=current_user.org_id,
                code_type=data.get('code_type', code.code_type),
                code_value=data['code_value']
            ).first()
            if existing:
                return jsonify({'success': False, 'error': 'قيمة الكود موجودة مسبقاً'}), 400
        
        if 'code_scope' in data:
            code.code_scope = data['code_scope']
        if 'code_type' in data:
            code.code_type = data['code_type']
        if 'code_value' in data:
            code.code_value = data['code_value']
        if 'code_description' in data:
            code.code_description = data['code_description']
        if 'code_color' in data:
            code.code_color = data['code_color']
        
        db.session.commit()
        return jsonify({'success': True, 'id': code.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@enterprise_bp.route('/api/activity-codes/<int:code_id>/delete', methods=['POST'])
@login_required
def api_activity_code_delete(code_id):
    """API لحذف كود نشاط"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    code = ActivityCode.query.get_or_404(code_id)
    
    try:
        # التحقق من عدم استخدام الكود
        # يمكن إضافة هذا التحقق إذا كان لديك علاقات مع Activities
        # activities_count = Activity.query.filter(Activity.activity_code_values.contains(code.code_value)).count()
        # if activities_count > 0:
        #     return jsonify({'success': False, 'error': f'لا يمكن حذف الكود لأنه مستخدم في {activities_count} أنشطة'}), 400
        
        db.session.delete(code)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# تحديث Route الإضافة للتحقق من التكرار
@enterprise_bp.route('/api/activity-codes/add', methods=['POST'])
@login_required
def api_activity_code_add():
    """API لإضافة كود نشاط جديد"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم تكرار الكود
        existing = ActivityCode.query.filter_by(
            org_id=current_user.org_id,
            code_type=data.get('code_type'),
            code_value=data.get('code_value')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'قيمة الكود موجودة مسبقاً'}), 400
        
        code = ActivityCode(
            org_id=current_user.org_id,
            code_scope=data.get('code_scope', 'global'),
            code_type=data.get('code_type'),
            code_value=data.get('code_value'),
            code_description=data.get('code_description'),
            code_color=data.get('code_color', '#4361ee')
        )
        
        db.session.add(code)
        db.session.commit()
        
        return jsonify({'success': True, 'id': code.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
# ============================================
# 7️⃣ Calendars – التقويمات
# ============================================

@enterprise_bp.route('/calendars')
@login_required
def calendars_list():
    """عرض قائمة التقويمات"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        calendars = Calendar.query.filter_by(org_id=org_id).all()
    else:
        calendars = Calendar.query.all()
    
    return render_template('enterprise/calendars/index.html', calendars=calendars)

# ============================================
# 8️⃣ UDF – User Defined Fields
# ============================================



@enterprise_bp.route('/udf')
@login_required
def udf_list():
    """عرض الحقول المعرفة من قبل المستخدم"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        udfs = UDF.query.filter_by(org_id=org_id).order_by(UDF.udf_type, UDF.udf_name).all()
    else:
        udfs = UDF.query.order_by(UDF.udf_type, UDF.udf_name).all()
    
    # تجميع حسب النوع
    grouped_udfs = {
        'activity': [],
        'project': [],
        'resource': [],
        'wbs': []
    }
    
    for udf in udfs:
        if udf.udf_type in grouped_udfs:
            grouped_udfs[udf.udf_type].append(udf)
    
    return render_template('enterprise/udf/index.html', grouped_udfs=grouped_udfs)

@enterprise_bp.route('/api/udf/<int:udf_id>', methods=['GET'])
@login_required
def api_udf_get(udf_id):
    """API لجلب بيانات حقل مخصص"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    udf = UDF.query.get_or_404(udf_id)
    
    return jsonify({
        'success': True,
        'udf': {
            'id': udf.id,
            'udf_type': udf.udf_type,
            'udf_name': udf.udf_name,
            'udf_label': udf.udf_label,
            'data_type': udf.data_type,
            'default_value': udf.default_value,
            'list_values': udf.list_values,
            'is_required': udf.is_required
        }
    })

@enterprise_bp.route('/api/udf/<int:udf_id>/update', methods=['POST'])
@login_required
def api_udf_update(udf_id):
    """API لتحديث حقل مخصص"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    udf = UDF.query.get_or_404(udf_id)
    data = request.get_json()
    
    try:
        # التحقق من عدم تكرار الاسم (إذا تغير)
        if 'udf_name' in data and data['udf_name'] != udf.udf_name:
            existing = UDF.query.filter_by(
                org_id=current_user.org_id,
                udf_type=data.get('udf_type', udf.udf_type),
                udf_name=data['udf_name']
            ).first()
            if existing:
                return jsonify({'success': False, 'error': 'اسم الحقل موجود مسبقاً'}), 400
        
        if 'udf_type' in data:
            udf.udf_type = data['udf_type']
        if 'udf_name' in data:
            udf.udf_name = data['udf_name']
        if 'udf_label' in data:
            udf.udf_label = data['udf_label']
      
        if 'data_type' in data:
            udf.data_type = data['data_type']
        if 'default_value' in data:
            udf.default_value = data['default_value']
        if 'list_values' in data:
            udf.list_values = data['list_values']
        if 'is_required' in data:
            udf.is_required = data['is_required']
        
        db.session.commit()
        return jsonify({'success': True, 'id': udf.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@enterprise_bp.route('/api/udf/<int:udf_id>/delete', methods=['POST'])
@login_required
def api_udf_delete(udf_id):
    """API لحذف حقل مخصص"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    udf = UDF.query.get_or_404(udf_id)
    
    try:
        db.session.delete(udf)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# تحديث Route الإضافة للتحقق من التكرار
@enterprise_bp.route('/api/udf/add', methods=['POST'])
@login_required
def api_udf_add():
    """API لإضافة حقل مخصص جديد"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم تكرار الاسم
        existing = UDF.query.filter_by(
            org_id=current_user.org_id,
            udf_type=data.get('udf_type'),
            udf_name=data.get('udf_name')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'اسم الحقل موجود مسبقاً'}), 400
        
        udf = UDF(
            org_id=current_user.org_id,
            udf_type=data.get('udf_type'),
            udf_name=data.get('udf_name'),
            udf_label=data.get('udf_label'),
            data_type=data.get('data_type', 'text'),
            default_value=data.get('default_value'),
            list_values=data.get('list_values', []),
            is_required=data.get('is_required', False)
        )
        
        db.session.add(udf)
        db.session.commit()
        
        return jsonify({'success': True, 'id': udf.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
# ============================================
# 9️⃣ Global Change – التغيير الشامل
# ============================================



@enterprise_bp.route('/global-change')
@login_required
def global_change_list():
    """عرض نماذج التغيير الشامل"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        changes = GlobalChange.query.filter_by(org_id=org_id).order_by(GlobalChange.created_at.desc()).all()
    else:
        changes = GlobalChange.query.order_by(GlobalChange.created_at.desc()).all()
    
    return render_template('enterprise/global_change/index.html', changes=changes)

@enterprise_bp.route('/global-change/create', methods=['GET', 'POST'])
@login_required
def global_change_create():
    """إنشاء نموذج تغيير شامل جديد"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    if request.method == 'POST':
        try:
            change = GlobalChange(
                org_id=current_user.org_id,
                change_name=request.form.get('change_name'),
                change_description=request.form.get('change_description'),
                target_type=request.form.get('target_type'),
                conditions=json.loads(request.form.get('conditions', '[]')),
                actions=json.loads(request.form.get('actions', '[]')),
                created_by=current_user.id
            )
            
            db.session.add(change)
            db.session.commit()
            
            flash('تم إنشاء نموذج التغيير الشامل بنجاح', 'success')
            return redirect(url_for('enterprise.global_change_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('enterprise/global_change/create.html')

# @enterprise_bp.route('/global-change/<int:change_id>/edit', methods=['GET', 'POST'])
# @login_required
# def global_change_edit(change_id):
#     """تعديل نموذج تغيير شامل"""
#     if not check_enterprise_access():
#         return redirect(url_for('enterprise.index'))
    
#     change = GlobalChange.query.get_or_404(change_id)
    
#     if request.method == 'POST':
#         try:
#             change.change_name = request.form.get('change_name', change.change_name)
#             change.change_description = request.form.get('change_description', change.change_description)
#             change.target_type = request.form.get('target_type', change.target_type)
#             change.conditions = json.loads(request.form.get('conditions', '[]'))
#             change.actions = json.loads(request.form.get('actions', '[]'))
            
#             db.session.commit()
#             flash('تم تحديث نموذج التغيير الشامل بنجاح', 'success')
#             return redirect(url_for('enterprise.global_change_list'))
            
#         except Exception as e:
#             db.session.rollback()
#             flash(f'حدث خطأ: {str(e)}', 'danger')
    
#     return render_template('enterprise/global_change/edit.html', change=change)

@enterprise_bp.route('/global-change/<int:change_id>/delete', methods=['POST'])
@login_required
def global_change_delete(change_id):
    """حذف نموذج تغيير شامل"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    change = GlobalChange.query.get_or_404(change_id)
    
    try:
        db.session.delete(change)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@enterprise_bp.route('/global-change/<int:change_id>/run', methods=['POST'])
@login_required
def global_change_run(change_id):
    """تشغيل التغيير الشامل"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    change = GlobalChange.query.get_or_404(change_id)
    
    try:
        # تحديد العناصر المستهدفة
        if change.target_type == 'activity':
            query = Activity.query
        elif change.target_type == 'project':
            query = Project.query
        elif change.target_type == 'resource':
            query = Resource.query
        else:
            return jsonify({'error': 'نوع هدف غير صالح'}), 400
        
        # تطبيق الشروط
        items = query.all()  # في التطبيق الحقيقي، يجب تطبيق الشروط
        
        # تطبيق الإجراءات
        for item in items:
            for action in change.actions:
                field = action.get('field')
                value = action.get('value')
                if hasattr(item, field):
                    setattr(item, field, value)
        
        change.last_run = datetime.utcnow()
        change.run_count += 1
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'تم تطبيق التغيير على {len(items)} عنصر'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@enterprise_bp.route('/global-change/<int:change_id>/edit', methods=['GET', 'POST'])
@login_required
def global_change_edit(change_id):
    """تعديل نموذج تغيير شامل"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    change = GlobalChange.query.get_or_404(change_id)
    
    # التحقق من الصلاحية
    if change.org_id != current_user.org_id and current_user.role != 'platform_admin':
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('enterprise.global_change_list'))
    
    if request.method == 'POST':
        try:
            # تحديث المعلومات الأساسية
            change.change_name = request.form.get('change_name', change.change_name)
            change.change_description = request.form.get('change_description', change.change_description)
            change.target_type = request.form.get('target_type', change.target_type)
            
            # تحديث الشروط والإجراءات
            conditions_str = request.form.get('conditions', '[]')
            actions_str = request.form.get('actions', '[]')
            
            change.conditions = json.loads(conditions_str) if conditions_str else []
            change.actions = json.loads(actions_str) if actions_str else []
            
            db.session.commit()
            
            flash('تم تحديث نموذج التغيير الشامل بنجاح', 'success')
            return redirect(url_for('enterprise.global_change_list'))
            
        except json.JSONDecodeError as e:
            flash(f'خطأ في صيغة JSON: {str(e)}', 'danger')
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('enterprise/global_change/edit.html', change=change)


@enterprise_bp.route('/global-change/<int:change_id>/preview', methods=['GET'])
@login_required
def global_change_preview(change_id):
    """معاينة العناصر المتأثرة بالتغيير"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    change = GlobalChange.query.get_or_404(change_id)
    
    try:
        # تحديد العناصر المستهدفة
        if change.target_type == 'activity':
            items = Activity.query.limit(10).all()
            result = [{
                'id': item.id,
                'name': item.activity_name,
                'code': item.activity_id
            } for item in items]
        elif change.target_type == 'project':
            items = Project.query.limit(10).all()
            result = [{
                'id': item.id,
                'name': item.name,
                'code': item.project_code
            } for item in items]
        elif change.target_type == 'resource':
            items = Resource.query.limit(10).all()
            result = [{
                'id': item.id,
                'name': item.name,
                'code': item.resource_id
            } for item in items]
        else:
            result = []
        
        return jsonify({
            'success': True,
            'items': result,
            'total': len(result)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@enterprise_bp.route('/api/global-change/validate', methods=['POST'])
@login_required
def api_global_change_validate():
    """API للتحقق من صحة النموذج قبل الحفظ"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    target_type = data.get('target_type')
    conditions = data.get('conditions', [])
    actions = data.get('actions', [])
    
    errors = []
    
    # التحقق من وجود إجراءات
    if not actions or len(actions) == 0:
        errors.append('يجب إضافة إجراء واحد على الأقل')
    
    # التحقق من صحة الشروط
    for i, condition in enumerate(conditions):
        if not condition.get('field'):
            errors.append(f'الشرط {i+1}: اسم الحقل مطلوب')
        if not condition.get('value'):
            errors.append(f'الشرط {i+1}: القيمة مطلوبة')
    
    # التحقق من صحة الإجراءات
    for i, action in enumerate(actions):
        if not action.get('field'):
            errors.append(f'الإجراء {i+1}: اسم الحقل مطلوب')
        if not action.get('value'):
            errors.append(f'الإجراء {i+1}: القيمة مطلوبة')
    
    return jsonify({
        'success': len(errors) == 0,
        'errors': errors
    })
# ============================================
# 🔟 Admin Preferences – تفضيلات الإدارة
# ============================================

@enterprise_bp.route('/admin-preferences', methods=['GET', 'POST'])
@login_required
def admin_preferences():
    """إدارة تفضيلات الإدارة"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = current_user.org_id
    
    # جلب التفضيلات أو إنشاؤها
    preferences = AdminPreference.query.filter_by(org_id=org_id).first()
    if not preferences:
        preferences = AdminPreference(org_id=org_id)
        db.session.add(preferences)
        db.session.commit()
    
    if request.method == 'POST':
        try:
            # تحديث الإعدادات العامة
            preferences.date_format = request.form.get('date_format', preferences.date_format)
            preferences.time_format = request.form.get('time_format', preferences.time_format)
            
            week_start = request.form.get('week_start')
            if week_start:
                preferences.week_start = int(week_start)
            
            preferences.fiscal_year_start = request.form.get('fiscal_year_start', preferences.fiscal_year_start)
            
            # تحديث إعدادات العملة
            preferences.base_currency = request.form.get('base_currency', preferences.base_currency)
            
            decimal_places = request.form.get('decimal_places')
            if decimal_places:
                preferences.decimal_places = int(decimal_places)
            
            preferences.number_format = request.form.get('number_format', preferences.number_format)
            
            # تحديث وحدات القياس
            units = request.form.get('units', '')
            if units:
                # تحويل النص إلى قائمة وإزالة الفراغات
                unit_list = [u.strip() for u in units.split(',') if u.strip()]
                preferences.units_of_measure = unit_list
            
            db.session.commit()
            
            flash('تم تحديث تفضيلات الإدارة بنجاح', 'success')
            return redirect(url_for('enterprise.admin_preferences'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('enterprise/admin_preferences/index.html', preferences=preferences)


@enterprise_bp.route('/api/admin-preferences/reset', methods=['POST'])
@login_required
def api_admin_preferences_reset():
    """API لإعادة تعيين التفضيلات إلى القيم الافتراضية"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    org_id = current_user.org_id
    
    try:
        preferences = AdminPreference.query.filter_by(org_id=org_id).first()
        if not preferences:
            preferences = AdminPreference(org_id=org_id)
            db.session.add(preferences)
        
        # إعادة تعيين القيم الافتراضية
        preferences.date_format = 'dd/MM/yyyy'
        preferences.time_format = 'HH:mm'
        preferences.week_start = 1
        preferences.fiscal_year_start = '01-01'
        preferences.base_currency = 'SAR'
        preferences.decimal_places = 2
        preferences.number_format = '###,###.##'
        preferences.units_of_measure = ['day', 'hour', 'm³', 'ton']
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم إعادة تعيين التفضيلات إلى القيم الافتراضية'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/admin-preferences/validate', methods=['POST'])
@login_required
def api_admin_preferences_validate():
    """API للتحقق من صحة التفضيلات"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    errors = []
    
    # التحقق من fiscal_year_start
    fiscal_year = data.get('fiscal_year_start')
    if fiscal_year and not re.match(r'^\d{2}-\d{2}$', fiscal_year):
        errors.append('صيغة بداية السنة المالية يجب أن تكون MM-DD')
    
    # التحقق من decimal_places
    decimal_places = data.get('decimal_places')
    if decimal_places is not None:
        try:
            dp = int(decimal_places)
            if dp < 0 or dp > 6:
                errors.append('المنازل العشرية يجب أن تكون بين 0 و 6')
        except:
            errors.append('قيمة المنازل العشرية غير صالحة')
    
    return jsonify({
        'success': len(errors) == 0,
        'errors': errors
    })

# ============================================
# 1️⃣1️⃣ Reporting Settings – إعدادات التقارير
# ============================================

@enterprise_bp.route('/reporting-settings', methods=['GET', 'POST'])
@login_required
def reporting_settings():
    """إعدادات التقارير"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    # يمكن تخزين هذه الإعدادات في جدول منفصل أو في AdminPreference
    org_id = current_user.org_id
    
    if request.method == 'POST':
        # حفظ الإعدادات
        flash('تم حفظ إعدادات التقارير', 'success')
        return redirect(url_for('enterprise.reporting_settings'))
    
    return render_template('enterprise/reporting_settings/index.html')

# ============================================
# 1️⃣1️⃣ EPS-OBS Matrix – مصفوفة الصلاحيات
# ============================================

@enterprise_bp.route('/eps-obs-matrix')
@login_required
def eps_obs_matrix():
    """عرض مصفوفة الصلاحيات EPS-OBS"""
    if not check_enterprise_access():
        return redirect(url_for('enterprise.index'))
    
    org_id = get_org_id()
    
    if org_id:
        eps_nodes = EPS.query.filter_by(org_id=org_id).order_by(EPS.eps_code).all()
        obs_nodes = OBS.query.filter_by(org_id=org_id).order_by(OBS.obs_code).all()
    else:
        eps_nodes = EPS.query.order_by(EPS.eps_code).all()
        obs_nodes = OBS.query.order_by(OBS.obs_code).all()
    
    # ✅ إضافة هذا الكود لتجهيز الصلاحيات الحالية
    assignments = EPSOBSAssignment.query.all()
    permissions_data = {}
    for assignment in assignments:
        key = f"{assignment.eps_id}-{assignment.obs_id}"
        permissions_data[key] = assignment.permission_level
    
    total_assignments = len(assignments)
    
    return render_template('enterprise/eps_obs_matrix.html',
                         eps_nodes=eps_nodes,
                         obs_nodes=obs_nodes,
                         permissions_data=permissions_data,  # ✅ أضف هذا
                         total_assignments=total_assignments)

@enterprise_bp.route('/api/eps-obs-permissions', methods=['GET'])
@login_required
def api_get_permissions():
    """API لجلب جميع الصلاحيات الحالية"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    org_id = get_org_id()
    
    try:
        # بناء الاستعلام
        query = EPSOBSAssignment.query
        
        if org_id:
            # فلترة حسب المؤسسة من خلال EPS
            query = query.join(EPS).filter(EPS.org_id == org_id)
        
        assignments = query.all()
        
        permissions = []
        for assign in assignments:
            permissions.append({
                'id': assign.id,
                'eps_id': assign.eps_id,
                'obs_id': assign.obs_id,
                'permission_level': assign.permission_level,
                'created_by': assign.created_by,
                'created_at': assign.created_at.strftime('%Y-%m-%d %H:%M') if assign.created_at else None,
                'eps_name': assign.eps.name if assign.eps else None,
                'obs_name': assign.obs.name if assign.obs else None
            })
        
        return jsonify({
            'success': True,
            'permissions': permissions,
            'total': len(permissions)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/eps-obs-permission/<int:eps_id>/<int:obs_id>', methods=['GET'])
@login_required
def api_get_permission(eps_id, obs_id):
    """API لجلب صلاحية محددة"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        assignment = EPSOBSAssignment.query.filter_by(
            eps_id=eps_id,
            obs_id=obs_id
        ).first()
        
        if assignment:
            return jsonify({
                'success': True,
                'permission': {
                    'id': assignment.id,
                    'eps_id': assignment.eps_id,
                    'obs_id': assignment.obs_id,
                    'permission_level': assignment.permission_level,
                    'created_by': assignment.created_by,
                    'created_at': assignment.created_at.strftime('%Y-%m-%d %H:%M') if assignment.created_at else None
                }
            })
        else:
            return jsonify({
                'success': True,
                'permission': None
            })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/save-permissions', methods=['POST'])
@login_required
def api_save_permissions():
    """API لحفظ جميع الصلاحيات"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    permissions = data.get('permissions', [])
    
    if not permissions:
        return jsonify({'success': False, 'error': 'لا تبيانات للحفظ'}), 400
    
    try:
        changes_count = 0
        new_count = 0
        deleted_count = 0
        
        # الحصول على جميع الصلاحيات الحالية للمقارنة
        existing_assignments = EPSOBSAssignment.query.all()
        existing_dict = {(a.eps_id, a.obs_id): a for a in existing_assignments}
        
        # معالجة الصلاحيات المرسلة
        processed_keys = set()
        
        for perm in permissions:
            eps_id = perm.get('eps_id')
            obs_id = perm.get('obs_id')
            permission_level = perm.get('permission_level', 'none')
            key = (eps_id, obs_id)
            processed_keys.add(key)
            
            # البحث عن الصلاحية الحالية
            assignment = existing_dict.get(key)
            
            if permission_level == 'none':
                # حذف الصلاحية إذا كانت موجودة
                if assignment:
                    db.session.delete(assignment)
                    deleted_count += 1
            else:
                # إنشاء أو تحديث الصلاحية
                if assignment:
                    if assignment.permission_level != permission_level:
                        assignment.permission_level = permission_level
                        assignment.created_by = current_user.id
                        changes_count += 1
                else:
                    # إنشاء صلاحية جديدة
                    new_assignment = EPSOBSAssignment(
                        eps_id=eps_id,
                        obs_id=obs_id,
                        permission_level=permission_level,
                        created_by=current_user.id
                    )
                    db.session.add(new_assignment)
                    new_count += 1
        
        # حذف الصلاحيات التي لم تعد موجودة (اختياري)
        # for (eps_id, obs_id), assignment in existing_dict.items():
        #     if (eps_id, obs_id) not in processed_keys:
        #         db.session.delete(assignment)
        #         deleted_count += 1
        
        db.session.commit()
        
        # تسجيل العملية في سجل النظام
        log_action(
            user_id=current_user.id,
            action='update_permissions',
            details=f'تم تحديث {changes_count} صلاحية، إضافة {new_count}، حذف {deleted_count}'
        )
        
        return jsonify({
            'success': True,
            'message': f'تم حفظ الصلاحيات بنجاح',
            'stats': {
                'updated': changes_count,
                'added': new_count,
                'deleted': deleted_count,
                'total': changes_count + new_count + deleted_count
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/update-permission', methods=['POST'])
@login_required
def api_update_permission():
    """API لتحديث صلاحية واحدة"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    eps_id = data.get('eps_id')
    obs_id = data.get('obs_id')
    permission_level = data.get('permission_level')
    
    if not all([eps_id, obs_id, permission_level]):
        return jsonify({'success': False, 'error': 'بيانات غير كاملة'}), 400
    
    try:
        assignment = EPSOBSAssignment.query.filter_by(
            eps_id=eps_id,
            obs_id=obs_id
        ).first()
        
        if permission_level == 'none':
            # حذف الصلاحية إذا كانت موجودة
            if assignment:
                db.session.delete(assignment)
                action = 'deleted'
            else:
                action = 'no_change'
        else:
            if assignment:
                # تحديث الصلاحية
                old_level = assignment.permission_level
                assignment.permission_level = permission_level
                assignment.created_by = current_user.id
                action = 'updated'
            else:
                # إنشاء صلاحية جديدة
                assignment = EPSOBSAssignment(
                    eps_id=eps_id,
                    obs_id=obs_id,
                    permission_level=permission_level,
                    created_by=current_user.id
                )
                db.session.add(assignment)
                action = 'created'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'action': action,
            'permission': {
                'eps_id': eps_id,
                'obs_id': obs_id,
                'permission_level': permission_level if permission_level != 'none' else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/delete-permission/<int:eps_id>/<int:obs_id>', methods=['DELETE'])
@login_required
def api_delete_permission(eps_id, obs_id):
    """API لحذف صلاحية محددة"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        assignment = EPSOBSAssignment.query.filter_by(
            eps_id=eps_id,
            obs_id=obs_id
        ).first()
        
        if not assignment:
            return jsonify({'success': False, 'error': 'الصلاحية غير موجودة'}), 404
        
        db.session.delete(assignment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الصلاحية بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/clear-permissions', methods=['POST'])
@login_required
def api_clear_permissions():
    """API لمسح جميع الصلاحيات"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # التحقق من الصلاحية (يجب أن يكون مدير)
    if current_user.role not in ['org_admin', 'platform_admin']:
        return jsonify({'success': False, 'error': 'غير مصرح لهذه العملية'}), 403
    
    try:
        org_id = get_org_id()
        
        if org_id:
            # حذف صلاحيات المؤسسة فقط
            assignments = EPSOBSAssignment.query.join(EPS).filter(EPS.org_id == org_id).all()
        else:
            assignments = EPSOBSAssignment.query.all()
        
        count = len(assignments)
        
        for assignment in assignments:
            db.session.delete(assignment)
        
        db.session.commit()
        
        # تسجيل العملية
        log_action(
            user_id=current_user.id,
            action='clear_all_permissions',
            details=f'تم مسح {count} صلاحية'
        )
        
        return jsonify({
            'success': True,
            'message': f'تم مسح {count} صلاحية بنجاح',
            'deleted_count': count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/export-permissions')
@login_required
def api_export_permissions():
    """API لتصدير الصلاحيات كملف Excel"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        org_id = get_org_id()
        
        # بناء الاستعلام
        query = EPSOBSAssignment.query.join(EPS).join(OBS)
        
        if org_id:
            query = query.filter(EPS.org_id == org_id)
        
        assignments = query.all()
        
        # تجهيز البيانات
        data = []
        for assign in assignments:
            data.append({
                'EPS Code': assign.eps.eps_code if assign.eps else '',
                'EPS Name': assign.eps.name if assign.eps else '',
                'OBS Code': assign.obs.obs_code if assign.obs else '',
                'OBS Name': assign.obs.name if assign.obs else '',
                'Permission Level': assign.permission_level,
                'Created By': assign.creator.full_name if assign.creator else '',
                'Created At': assign.created_at.strftime('%Y-%m-%d %H:%M') if assign.created_at else ''
            })
        
        # إنشاء DataFrame
        df = pd.DataFrame(data)
        
        # إنشاء ملف Excel في الذاكرة
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Permissions', index=False)
        
        output.seek(0)
        
        filename = f'eps_obs_permissions_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/import-permissions', methods=['POST'])
@login_required
def api_import_permissions():
    """API لاستيراد الصلاحيات من ملف"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'لم يتم رفع ملف'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'error': 'الملف فارغ'}), 400
    
    try:
        # قراءة الملف
        if file.filename.endswith('.xlsx'):
            df = pd.read_excel(file)
        elif file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            return jsonify({'success': False, 'error': 'صيغة ملف غير مدعومة'}), 400
        
        imported_count = 0
        errors = []
        
        for index, row in df.iterrows():
            try:
                # البحث عن EPS
                eps = EPS.query.filter_by(
                    eps_code=row.get('EPS Code'),
                    org_id=get_org_id()
                ).first()
                
                # البحث عن OBS
                obs = OBS.query.filter_by(
                    obs_code=row.get('OBS Code'),
                    org_id=get_org_id()
                ).first()
                
                if not eps or not obs:
                    errors.append(f"الصف {index + 2}: EPS أو OBS غير موجود")
                    continue
                
                permission_level = row.get('Permission Level', 'read')
                
                # البحث عن صلاحية موجودة
                assignment = EPSOBSAssignment.query.filter_by(
                    eps_id=eps.id,
                    obs_id=obs.id
                ).first()
                
                if assignment:
                    # تحديث الصلاحية
                    assignment.permission_level = permission_level
                else:
                    # إنشاء صلاحية جديدة
                    assignment = EPSOBSAssignment(
                        eps_id=eps.id,
                        obs_id=obs.id,
                        permission_level=permission_level,
                        created_by=current_user.id
                    )
                    db.session.add(assignment)
                
                imported_count += 1
                
            except Exception as e:
                errors.append(f"الصف {index + 2}: {str(e)}")
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'تم استيراد {imported_count} صلاحية بنجاح',
            'imported': imported_count,
            'errors': errors[:10]  # عرض أول 10 أخطاء فقط
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@enterprise_bp.route('/api/permissions/stats')
@login_required
def api_permissions_stats():
    """API لإحصائيات الصلاحيات"""
    if not check_enterprise_access():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        org_id = get_org_id()
        
        # بناء الاستعلام
        query = EPSOBSAssignment.query.join(EPS)
        
        if org_id:
            query = query.filter(EPS.org_id == org_id)
        
        assignments = query.all()
        
        # إحصائيات حسب مستوى الصلاحية
        permission_stats = {
            'read': 0,
            'write': 0,
            'admin': 0
        }
        
        for assign in assignments:
            if assign.permission_level in permission_stats:
                permission_stats[assign.permission_level] += 1
        
        # أكثر EPS ارتباطاً
        eps_stats = db.session.query(
            EPS.id,
            EPS.name,
            EPS.eps_code,
            func.count(EPSOBSAssignment.id).label('count')
        ).outerjoin(EPSOBSAssignment, EPS.id == EPSOBSAssignment.eps_id)\
         .group_by(EPS.id, EPS.name, EPS.eps_code)\
         .order_by(func.count(EPSOBSAssignment.id).desc())\
         .limit(5).all()
        
        # أكثر OBS ارتباطاً
        obs_stats = db.session.query(
            OBS.id,
            OBS.name,
            OBS.obs_code,
            func.count(EPSOBSAssignment.id).label('count')
        ).outerjoin(EPSOBSAssignment, OBS.id == EPSOBSAssignment.obs_id)\
         .group_by(OBS.id, OBS.name, OBS.obs_code)\
         .order_by(func.count(EPSOBSAssignment.id).desc())\
         .limit(5).all()
        
        return jsonify({
            'success': True,
            'stats': {
                'total': len(assignments),
                'by_permission': permission_stats,
                'top_eps': [{
                    'id': eps.id,
                    'name': eps.name,
                    'code': eps.eps_code,
                    'count': eps.count
                } for eps in eps_stats],
                'top_obs': [{
                    'id': obs.id,
                    'name': obs.name,
                    'code': obs.obs_code,
                    'count': obs.count
                } for obs in obs_stats]
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# دوال مساعدة
# ============================================

# def check_enterprise_access():
#     """التحقق من صلاحية الوصول لنظام المؤسسة"""
#     if current_user.role == 'platform_admin':
#         return True
    
#     if hasattr(current_user, 'org_id') and current_user.org_id:
#         return True
    
#     flash('غير مصرح بالوصول إلى نظام المؤسسة', 'danger')
#     return False





def log_action(user_id, action, details=None):
    """تسجيل الإجراءات في سجل النظام"""
    try:
        from app.models.ai_models import AuditLog
        
        log = AuditLog(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string
        )
        db.session.add(log)
        db.session.commit()
    except:
        # تجاهل الأخطاء في التسجيل
        pass
# ============================================
# API Routes عامة
# ============================================

@enterprise_bp.route('/api/eps/<int:eps_id>')
@login_required
def api_eps_detail(eps_id):
    """API للحصول على تفاصيل EPS"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    eps = EPS.query.get_or_404(eps_id)
    
    return jsonify({
        'success': True,
        'eps': {
            'id': eps.id,
            'eps_code': eps.eps_code,
            'name': eps.name,
            'description': eps.description,
            'path': eps.path,
            'level': eps.level
        }
    })

@enterprise_bp.route('/api/eps/<int:eps_id>/update', methods=['POST'])
@login_required
def api_eps_update(eps_id):
    """API لتحديث بيانات EPS"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    eps = EPS.query.get_or_404(eps_id)
    data = request.get_json()
    
    try:
        if 'name' in data:
            eps.name = data['name']
        if 'description' in data:
            eps.description = data['description']
        if 'eps_code' in data:
            eps.eps_code = data['eps_code']
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@enterprise_bp.route('/api/obs/<int:obs_id>')
@login_required
def api_obs_detail(obs_id):
    """API للحصول على تفاصيل OBS"""
    if not check_enterprise_access():
        return jsonify({'error': 'غير مصرح'}), 403
    
    obs = OBS.query.get_or_404(obs_id)
    
    return jsonify({
        'success': True,
        'obs': {
            'id': obs.id,
            'obs_code': obs.obs_code,
            'name': obs.name,
            'description': obs.description,
            'responsible': obs.responsible.full_name if obs.responsible else None
        }
    })

# أضف هذه الدوال المساعدة في enterprise_routes.py

@enterprise_bp.route('/api/eps/<int:eps_id>/obs')
@login_required
def api_eps_obs(eps_id):
    """الحصول على عناصر OBS المسموح لها بهذا EPS"""
    eps = EPS.query.get_or_404(eps_id)
    
    allowed_obs = eps.get_allowed_obs()
    
    return jsonify({
        'success': True,
        'obs': [{
            'id': o.id,
            'name': o.name,
            'code': o.obs_code
        } for o in allowed_obs]
    })

@enterprise_bp.route('/api/obs/<int:obs_id>/eps')
@login_required
def api_obs_eps(obs_id):
    """الحصول على عناصر EPS المتاحة لهذا OBS"""
    obs = OBS.query.get_or_404(obs_id)
    
    accessible_eps = obs.get_accessible_eps()
    
    return jsonify({
        'success': True,
        'eps': [{
            'id': e.id,
            'name': e.name,
            'code': e.eps_code
        } for e in accessible_eps]
    })

@enterprise_bp.route('/api/apply-udf/<string:target_type>/<int:target_id>', methods=['POST'])
@login_required
def api_apply_udf(target_type, target_id):
    """تطبيق حقل مخصص على عنصر"""
    data = request.get_json()
    udf_id = data.get('udf_id')
    value = data.get('value')
    
    # تحديد العنصر المستهدف
    if target_type == 'activity':
        item = Activity.query.get_or_404(target_id)
    elif target_type == 'project':
        item = Project.query.get_or_404(target_id)
    elif target_type == 'resource':
        item = Resource.query.get_or_404(target_id)
    elif target_type == 'wbs':
        item = WBS.query.get_or_404(target_id)
    else:
        return jsonify({'error': 'نوع غير صالح'}), 400
    
    # تطبيق القيمة
    udf = UDF.query.get(udf_id)
    if udf:
        item.set_udf_value(udf.udf_name, value)
        db.session.commit()
    
    return jsonify({'success': True})

@enterprise_bp.route('/api/apply-activity-code/<int:activity_id>', methods=['POST'])
@login_required
def api_apply_activity_code(activity_id):
    """تطبيق كود نشاط على نشاط"""
    data = request.get_json()
    code_type = data.get('code_type')
    code_value = data.get('code_value')
    
    activity = Activity.query.get_or_404(activity_id)
    activity.set_activity_code(code_type, code_value)
    db.session.commit()
    
    return jsonify({'success': True})

@enterprise_bp.route('/api/apply-resource-code/<int:resource_id>', methods=['POST'])
@login_required
def api_apply_resource_code(resource_id):
    """تطبيق كود مورد على مورد"""
    data = request.get_json()
    code_type = data.get('code_type')
    code_value = data.get('code_value')
    
    resource = Resource.query.get_or_404(resource_id)
    resource.set_resource_code(code_type, code_value)
    db.session.commit()
    
    return jsonify({'success': True})


@enterprise_bp.route('/api/udf/list')
@login_required
def api_udf_list():
    """قائمة الحقول المخصصة حسب النوع"""
    udf_type = request.args.get('type', 'activity')
    
    udfs = UDF.query.filter_by(
        org_id=current_user.org_id,
        udf_type=udf_type,
        is_active=True
    ).all()
    
    return jsonify({
        'success': True,
        'udfs': [{
            'id': u.id,
            'name': u.udf_name,
            'label': u.udf_label,
            'data_type': u.data_type,
            'list_values': u.list_values,
            'is_required': u.is_required
        } for u in udfs]
    })

@enterprise_bp.route('/api/activity-codes/list')
@login_required
def api_activity_codes_list():
    """قائمة أنواع أكواد الأنشطة"""
    codes = db.session.query(ActivityCode.code_type).distinct().all()
    
    return jsonify({
        'success': True,
        'codes': [{'type': c[0]} for c in codes]
    })

@enterprise_bp.route('/api/resource-codes/list')
@login_required
def api_resource_codes_list():
    """قائمة أنواع أكواد الموارد"""
    codes = db.session.query(ResourceCode.code_type).distinct().all()
    
    return jsonify({
        'success': True,
        'codes': [{'type': c[0]} for c in codes]
    })

@enterprise_bp.route('/api/roles/list')
@login_required
def api_roles_list():
    """قائمة الأدوار الوظيفية"""
    roles = Role.query.filter_by(org_id=current_user.org_id).all()
    
    return jsonify({
        'success': True,
        'roles': [{
            'id': r.id,
            'name': r.name,
            'code': r.role_code,
            'cost': r.default_cost_per_hour
        } for r in roles]
    })
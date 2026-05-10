"""
primavera_routes.py - مسارات نظام Primavera المتكامل للمشاريع والأنشطة
"""
from flask import render_template, request, redirect, url_for, flash, jsonify, g,current_app,send_from_directory
from flask_login import login_required, current_user
from app.models import db, User, Organization, Project, Task, Notification,Issue,Meeting
from app.models import (
    EPS, WBS, Calendar, Activity, ActivityRelationship,ResourceDelivery,TaskPlanning,
    Resource, ActivityResource, Baseline,
    EPSOBSAssignment,ActivityStep,ActivityExpense,ActivityRisk,ActivityFeedback,ActivityDocument,NotebookEntry,BudgetLog,FundingSource,SpendingPlanItem
)
from app.models import (
    OBS, Role, ResourceCode, ActivityCodeDictionary,ActivityCodeValue,ActivityCodeAssignment, UDF, GlobalChange
)
from app.services.primavera_engine import PrimaveraEngine,create_baseline
from app.services.notification_service import NotificationService
from app.routes import primavera_bp
from datetime import datetime, date, timedelta
from sqlalchemy import func, and_, or_
import json
import os
from werkzeug.utils import secure_filename
from app.services.audit_service import audit_service
from app.services.update_service import UpdateService
import uuid
import mimetypes
# ============================================
# دوال مساعدة للتحقق من الصلاحيات
# ============================================

def get_org_id():
    """الحصول على معرف المؤسسة"""
    if current_user.role == 'platform_admin':
        return None
    return current_user.org_id

def check_eps_access(eps_id):
    """التحقق من الوصول إلى EPS"""
    eps = EPS.query.get_or_404(eps_id)
    if current_user.role == 'platform_admin':
        return eps
    if hasattr(eps, 'org_id') and eps.org_id != current_user.org_id:
        flash('غير مصرح بالوصول', 'danger')
        return None
    return eps

def check_project_access(project_id):
    """التحقق من الوصول إلى المشروع"""
    project = Project.query.get_or_404(project_id)
    
    if current_user.role == 'platform_admin':
        return project
    
    # التحقق من وجود EPS
    if not hasattr(project, 'eps') or not project.eps:
        flash('المشروع لا ينتمي إلى أي EPS', 'danger')
        return None
    
    if hasattr(project.eps, 'org_id') and project.eps.org_id != current_user.org_id:
        flash('غير مصرح بالوصول', 'danger')
        return None
    
    return project

def check_activity_access(activity_id):
    """التحقق من صلاحية الوصول للنشاط"""
    activity = Activity.query.get_or_404(activity_id)
    return activity
# ============================================
# 1️⃣ EPS – Enterprise Project Structure
# ============================================
@primavera_bp.before_request
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

@primavera_bp.route('/eps')
@login_required
def eps_list():
    """عرض هيكل المؤسسة"""
    org_id = get_org_id()
    
    if org_id:
        eps_nodes = EPS.query.filter_by(org_id=org_id).order_by(EPS.level, EPS.eps_code).all()
    else:
        eps_nodes = EPS.query.order_by(EPS.level, EPS.eps_code).all()
    
    # بناء الهيكل الشجري
    root_nodes = [n for n in eps_nodes if n.parent_id is None]
    
    # إحصائيات - استخدام projects بدلاً من primavera_projects
    total_projects = 0
    for node in eps_nodes:
        if hasattr(node, 'projects'):
            total_projects += node.projects.count()
    
    return render_template('primavera/eps.html',
                         eps_nodes=eps_nodes,
                         root_nodes=root_nodes,
                         total_projects=total_projects)

@primavera_bp.route('/eps/create', methods=['GET', 'POST'])
@login_required
def eps_create():
    """إنشاء عنصر EPS جديد"""
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الرمز
            existing = EPS.query.filter_by(
                org_id=current_user.org_id,
                eps_code=request.form.get('eps_code')
            ).first()
            
            if existing:
                flash('رمز EPS موجود مسبقاً', 'danger')
                return redirect(url_for('primavera.eps_create'))
            
            eps = EPS(
                org_id=current_user.org_id,
                eps_code=request.form.get('eps_code'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                parent_id=request.form.get('parent_id') or None,
                manager_id=request.form.get('manager_id') or None
            )
            
            # إنشاء المسار
            if eps.parent_id:
                parent = EPS.query.get(eps.parent_id)
                eps.path = f"{parent.path}/{eps.eps_code}" if parent.path else eps.eps_code
                eps.level = parent.level + 1
            else:
                eps.path = eps.eps_code
                eps.level = 1
            
            db.session.add(eps)
            db.session.commit()
            
            # إشعار للمدير المسؤول
            if eps.manager_id:
                NotificationService.eps_manager(
                    user_id=eps.manager_id,
                    title='📁 عنصر EPS جديد',
                    message=f'تم تعيينك كمدير لعنصر EPS {eps.name}',
                    priority='medium'
                )
            
            flash('تم إنشاء عنصر EPS بنجاح', 'success')
            return redirect(url_for('primavera.eps_view', eps_id=eps.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    parents = EPS.query.filter_by(org_id=current_user.org_id).all()
    managers = User.query.filter(
                User.org_id == current_user.org_id,
                User.role.in_(['org_admin', 'project_manager'])
            ).all()
    
    return render_template('primavera/eps_create.html',
                         parents=parents,
                         managers=managers)

@primavera_bp.route('/eps/<int:eps_id>')
@login_required
def eps_view(eps_id):
    """عرض تفاصيل عنصر EPS مع معلومات متكاملة"""
    eps = check_eps_access(eps_id)
    if not eps:
        return redirect(url_for('primavera.eps_list'))
    
    # جلب العناصر الفرعية
    children = EPS.query.filter_by(parent_id=eps_id).order_by(EPS.eps_code).all()
    
    # جلب المشاريع المرتبطة
    projects = Project.query.filter_by(eps_id=eps_id).all() if hasattr(eps, 'projects') else []
    
    # إحصائيات متقدمة
    total_activities = 0
    total_budget = 0
    completed_projects = 0
    active_projects = 0
    planning_projects = 0
    
    # إحصائيات المشاريع
    projects_data = []
    for project in projects:
        # عدد الأنشطة
        project_activities = project.activities.count() if hasattr(project, 'activities') else 0
        total_activities += project_activities
        
        # الميزانية
        project_budget = project.budget.current_budget or 0
        total_budget += project_budget
        
        # حالة المشروع
        if project.status == 'completed':
            completed_projects += 1
        elif project.status == 'active':
            active_projects += 1
        elif project.status == 'planning':
            planning_projects += 1
        
        # التقدم
        progress = 0
        if hasattr(project, 'progress') and project.progress:
            progress = project.progress.progress_percentage
        elif hasattr(project, 'get_progress'):
            progress = project.get_progress()
        
        # تجهيز بيانات المشروع للعرض
        projects_data.append({
            'id': project.id,
            'name': project.name,
            'project_code': project.project_code,
            'status': project.status,
            'progress': progress,
            'activities_count': project_activities,
            'budget': project_budget,
            'manager_name': project.manager.full_name if project.manager else 'غير محدد',
            'start_date': project.dates.planned_start.strftime('%Y-%m-%d') if project.dates and project.dates.planned_start else None,
            'finish_date': project.dates.planned_finish.strftime('%Y-%m-%d') if project.dates and project.dates.planned_finish else None
        })
    
    # إحصائيات EPS
    stats = {
        'total_children': len(children),
        'total_projects': len(projects),
        'total_activities': total_activities,
        'total_budget': total_budget,
        'completed_projects': completed_projects,
        'active_projects': active_projects,
        'planning_projects': planning_projects,
        'avg_projects_per_child': round(len(projects) / len(children), 1) if children else 0,
        'avg_activities_per_project': round(total_activities / len(projects), 1) if projects else 0
    }
    
    # الحصول على المسار الكامل
    full_path = eps.name
    parent_path = []
    current = eps
    while current.parent:
        parent_path.insert(0, current.parent.name)
        current = current.parent
    if parent_path:
        full_path = ' → '.join(parent_path + [eps.name])
    
    # الحصول على المدراء المسؤولين (OBS)
    obs_assignments = []
    if hasattr(eps, 'obs_assignments'):
        for assignment in eps.obs_assignments:
            if assignment.obs:
                obs_assignments.append({
                    'id': assignment.obs.id,
                    'name': assignment.obs.name,
                    'code': assignment.obs.obs_code,
                    'permission': assignment.permission_level,
                    'responsible': assignment.obs.responsible.full_name if assignment.obs.responsible else None
                })
    
    return render_template('primavera/eps_view.html',
                         eps=eps,
                         children=children,
                         projects=projects_data,
                         stats=stats,
                         obs_assignments=obs_assignments,
                         full_path=full_path,
                         now=datetime.now())


# ============================================
# 2️⃣ Calend ar – التقويمات
# ============================================

@primavera_bp.route('/calendars')
@login_required
def calendar_list():
    """عرض قائمة التقويمات"""
    org_id = get_org_id()
    
    if org_id:
        calendars = Calendar.query.filter_by(org_id=org_id).all()
    else:
        calendars = Calendar.query.all()
    
    # حساب الإحصائيات
    projects=Calendar.query.filter_by(org_id=org_id,calendar_type="project").all()
    resources=Calendar.query.filter_by(org_id=org_id,calendar_type="resource").all()
    projects_count=len(projects)
    resources_count=len(resources)

    calendars_count = len(calendars)
    default_count = sum(1 for c in calendars if c.is_default)
    
    return render_template('primavera/calendars.html', 
                         calendars=calendars,
                         calendars_count=calendars_count,
                         default_count=default_count,
                         projects_count=projects_count,
                         resources_count=resources_count)

@primavera_bp.route('/calendars/create', methods=['GET', 'POST'])
@login_required
def calendar_create():
    """إنشاء تقويم جديد"""
    if request.method == 'POST':
        try:
            # معالجة أيام العمل
            work_days = []
            for i in range(1, 8):
                if request.form.get(f'day_{i}'):
                    work_days.append(i)
            
            # معالجة الإجازات
            holidays = request.form.get('holidays', '').split(',') if request.form.get('holidays') else []
            holidays = [h.strip() for h in holidays if h.strip()]
            
            # معالجة الأوقات
            work_start = datetime.strptime(request.form.get('work_start', '08:00'), '%H:%M').time()
            work_end = datetime.strptime(request.form.get('work_end', '17:00'), '%H:%M').time()
            
            calendar = Calendar(
                org_id=current_user.org_id,
                name=request.form.get('name'),
                calendar_type=request.form.get('calendar_type', 'project'),
                work_days=work_days,
                work_hours_per_day=float(request.form.get('work_hours_per_day', 8)),
                work_start=work_start,
                work_end=work_end,
                holidays=holidays,
                is_default=bool(request.form.get('is_default'))
            )
            
            # إذا كان التقويم افتراضياً، قم بإلغاء افتراضية الآخرين
            if calendar.is_default:
                Calendar.query.filter_by(org_id=current_user.org_id, is_default=True).update({'is_default': False})
            
            db.session.add(calendar)
            db.session.commit()
            
            flash('تم إنشاء التقويم بنجاح', 'success')
            return redirect(url_for('primavera.calendar_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('primavera/calendar_create.html')

@primavera_bp.route('/calendars/<int:calendar_id>/edit', methods=['GET', 'POST'])
@login_required
def calendar_edit(calendar_id):
    """تعديل تقويم"""
    calendar = Calendar.query.get_or_404(calendar_id)
    
    # التحقق من الصلاحية
    if calendar.org_id != current_user.org_id and current_user.role != 'platform_admin':
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('primavera.calendar_list'))
    
    if request.method == 'POST':
        try:
            # معالجة أيام العمل
            work_days = []
            for i in range(1, 8):
                if request.form.get(f'day_{i}'):
                    work_days.append(i)
            
            # معالجة الإجازات
            holidays = request.form.get('holidays', '').split(',') if request.form.get('holidays') else []
            holidays = [h.strip() for h in holidays if h.strip()]
            
            # معالجة الأوقات
            work_start = datetime.strptime(request.form.get('work_start', '08:00'), '%H:%M').time()
            work_end = datetime.strptime(request.form.get('work_end', '17:00'), '%H:%M').time()
            
            # تحديث التقويم
            calendar.name = request.form.get('name')
            calendar.calendar_type = request.form.get('calendar_type', 'project')
            calendar.work_days = work_days
            calendar.work_hours_per_day = float(request.form.get('work_hours_per_day', 8))
            calendar.work_start = work_start
            calendar.work_end = work_end
            calendar.holidays = holidays
            
            # معالجة التقويم الافتراضي
            if request.form.get('is_default'):
                # إلغاء افتراضية الآخرين
                Calendar.query.filter_by(org_id=calendar.org_id, is_default=True).update({'is_default': False})
                calendar.is_default = True
            else:
                calendar.is_default = False
            
            db.session.commit()
            
            flash('تم تحديث التقويم بنجاح', 'success')
            return redirect(url_for('primavera.calendar_list'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('primavera/calendar_edit.html', calendar=calendar)


@primavera_bp.route('/api/calendars/<int:calendar_id>', methods=['GET'])
@login_required
def api_calendar_get(calendar_id):
    """API لجلب بيانات التقويم"""
    calendar = Calendar.query.get_or_404(calendar_id)
    
    if calendar.org_id != current_user.org_id and current_user.role != 'platform_admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'calendar': {
            'id': calendar.id,
            'name': calendar.name,
            'calendar_type': calendar.calendar_type,
            'work_days': calendar.work_days,
            'work_hours_per_day': calendar.work_hours_per_day,
            'work_start': calendar.work_start.strftime('%H:%M') if calendar.work_start else '08:00',
            'work_end': calendar.work_end.strftime('%H:%M') if calendar.work_end else '17:00',
            'holidays': calendar.holidays,
            'is_default': calendar.is_default,
            'is_active': calendar.is_active
        }
    })


@primavera_bp.route('/calendars/<int:calendar_id>/delete', methods=['POST'])
@login_required
def calendar_delete(calendar_id):
    """حذف تقويم"""
    calendar = Calendar.query.get_or_404(calendar_id)
    
    if calendar.org_id != current_user.org_id and current_user.role != 'platform_admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        # التحقق من عدم استخدام التقويم
        projects_count = calendar.projects.count()
        resources_count = calendar.resources.count()
        
        if projects_count > 0 or resources_count > 0:
            return jsonify({
                'success': False, 
                'error': f'لا يمكن حذف التقويم لأنه مستخدم في {projects_count} مشاريع و {resources_count} موارد'
            }), 400
        
        db.session.delete(calendar)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@primavera_bp.route('/calendars/<int:calendar_id>/set-default', methods=['POST'])
@login_required
def calendar_set_default(calendar_id):
    """تعيين تقويم كافتراضي"""
    calendar = Calendar.query.get_or_404(calendar_id)
    
    if calendar.org_id != current_user.org_id and current_user.role != 'platform_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # إلغاء افتراضية جميع التقويمات
        Calendar.query.filter_by(org_id=calendar.org_id, is_default=True).update({'is_default': False})
        
        # تعيين التقويم الحالي كافتراضي
        calendar.is_default = True
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# 3️⃣ WBS – Work Breakdown Structure
# ============================================

# @primavera_bp.route('/project/<int:project_id>/wbs')
# @login_required
# def wbs_view(project_id):
#     """عرض WBS للمشروع"""
#     project = check_project_access(project_id)
#     if not project:
#         return redirect(url_for('company.projects'))
    
#     wbs_nodes = WBS.query.filter_by(project_id=project_id).order_by(WBS.level, WBS.wbs_code).all()
#     root_nodes = [n for n in wbs_nodes if n.parent_id is None]
    
#     # حساب إحصائيات كل عقدة
#     for node in wbs_nodes:
#         node.total_budget = node.budget
#         node.total_activities = len(node.activities_list)
#         node.progress = node.calculate_progress()
    
#     return render_template('primavera/wbs.html',
#                          project=project,
#                          wbs_nodes=wbs_nodes,
#                          root_nodes=root_nodes)

# @primavera_bp.route('/wbs/create', methods=['POST'])
# @login_required
# def wbs_create():
#     """إنشاء عنصر WBS جديد"""
#     try:
#         project_id = request.form.get('project_id')
#         project = check_project_access(project_id)
#         if not project:
#             return jsonify({'error': 'غير مصرح'}), 403
        
#         # التحقق من عدم تكرار الرمز
#         existing = WBS.query.filter_by(
#             project_id=project_id,
#             wbs_code=request.form.get('wbs_code')
#         ).first()
        
#         if existing:
#             return jsonify({'error': 'رمز WBS موجود مسبقاً'}), 400
        
#         wbs = WBS(
#             project_id=project_id,
#             wbs_code=request.form.get('wbs_code'),
#             name=request.form.get('name'),
#             description=request.form.get('description'),
#             parent_id=request.form.get('parent_id') or None,
#             budget=float(request.form.get('budget', 0))
#         )
        
#         # إنشاء المسار
#         if wbs.parent_id:
#             parent = WBS.query.get(wbs.parent_id)
#             wbs.wbs_path = f"{parent.wbs_path}.{wbs.wbs_code}" if parent.wbs_path else wbs.wbs_code
#             wbs.level = parent.level + 1
#         else:
#             wbs.wbs_path = wbs.wbs_code
#             wbs.level = 1
        
#         db.session.add(wbs)
#         db.session.commit()
        
#         return jsonify({'success': True, 'wbs': {
#             'id': wbs.id,
#             'wbs_code': wbs.wbs_code,
#             'name': wbs.name,
#             'level': wbs.level,
#             'path': wbs.wbs_path
#         }})
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500
# ============================================
# WBS – Work Breakdown Structure
# ============================================

@primavera_bp.route('/project/<int:project_id>/wbs')
@login_required
def wbs_list(project_id):
    """عرض هيكل WBS للمشروع"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('primavera.projects_list'))
    
    # جلب جميع عناصر WBS للمشروع
    wbs_nodes = WBS.query.filter_by(project_id=project_id).order_by(WBS.level, WBS.wbs_code).all()
    
    # بناء الهيكل الشجري
    def build_tree(parent_id=None):
        tree = []
        for node in wbs_nodes:
            if node.parent_id == parent_id:
                # حساب إحصائيات العقدة
                node_stats = calculate_wbs_node_stats(node.id)
                node_dict = {
                    'id': node.id,
                    'wbs_code': node.wbs_code,
                    'name': node.name,
                    'description': node.description,
                    'level': node.level,
                    'parent_id': node.parent_id,
                    'weight': node.weight,
                    'budget': node.budget,
                    'planned_cost': node.planned_cost,
                    'actual_cost': node.actual_cost,
                    'progress': node.progress_percentage,
                    'stats': node_stats,
                    'children': build_tree(node.id)
                }
                tree.append(node_dict)
        return tree
    
    tree_data = build_tree()
    
    # إحصائيات عامة
    total_nodes = len(wbs_nodes)
    total_budget = sum(node.budget or 0 for node in wbs_nodes)
    total_planned = sum(node.planned_cost or 0 for node in wbs_nodes)
    total_actual = sum(node.actual_cost or 0 for node in wbs_nodes)
    avg_progress = sum(node.progress_percentage for node in wbs_nodes) / total_nodes if total_nodes > 0 else 0
    
    stats = {
        'total_nodes': total_nodes,
        'total_budget': total_budget,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'avg_progress': avg_progress,
        'variance': total_planned - total_actual,
        'root_nodes': len([n for n in wbs_nodes if n.parent_id is None])
    }
    
    return render_template('primavera/wbs/wbs_list.html',
                         project=project,
                         tree_data=tree_data,
                         stats=stats,
                         now=datetime.now())


@primavera_bp.route('/project/<int:project_id>/wbs/create', methods=['GET', 'POST'])
@login_required
def wbs_create(project_id):
    """إنشاء عنصر WBS جديد"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('primavera.projects_list'))
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الكود
            existing = WBS.query.filter_by(
                project_id=project_id,
                wbs_code=request.form.get('wbs_code')
            ).first()
            
            if existing:
                flash('كود WBS موجود مسبقاً', 'danger')
                return redirect(url_for('primavera.wbs_create', project_id=project_id))
            
            # إنشاء WBS جديد
            wbs = WBS(
                project_id=project_id,
                wbs_code=request.form.get('wbs_code'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                parent_id=request.form.get('parent_id') or None,
                weight=float(request.form.get('weight', 0)),
                budget=float(request.form.get('budget', 0)),
                planned_cost=float(request.form.get('planned_cost', 0))
            )
            
            # حساب المستوى والمسار
            if wbs.parent_id:
                parent = WBS.query.get(wbs.parent_id)
                wbs.level = parent.level + 1
                wbs.wbs_path = f"{parent.wbs_path}.{wbs.wbs_code}" if parent.wbs_path else wbs.wbs_code
            else:
                wbs.level = 1
                wbs.wbs_path = wbs.wbs_code
            
            db.session.add(wbs)
            db.session.commit()
            
            # ✅ تسجيل العملية (غير متزامن - لا يؤثر على الأداء)
            # audit_service.log(
            #     user_id=current_user.id,
            #     action='create_wbs',
            #     entity_type='wbs',
            #     entity_id=wbs.id,
            #     entity_code=wbs.wbs_code,
            #     details=f'تم إنشاء عنصر WBS: {wbs.wbs_code} - {wbs.name}',
            #     new_values={
            #         'wbs_code': wbs.wbs_code,
            #         'name': wbs.name,
            #         'project_id': project_id
            #     }
            # )
            
            flash('تم إنشاء عنصر WBS بنجاح', 'success')
            return redirect(url_for('primavera.wbs_list', project_id=project_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # بيانات النموذج
    wbs_list = WBS.query.filter_by(project_id=project_id).order_by(WBS.level, WBS.wbs_code).all()
    
    return render_template('primavera/wbs/wbs_create.html',
                         project=project,
                         wbs_list=wbs_list,
                         now=datetime.now())


@primavera_bp.route('/wbs/<int:wbs_id>/edit', methods=['GET', 'POST'])
@login_required
def wbs_edit(wbs_id):
    """تعديل عنصر WBS"""
    wbs = WBS.query.get_or_404(wbs_id)
    
    # التحقق من الصلاحية
    if not check_project_access(wbs.project_id):
        return redirect(url_for('primavera.projects_list'))
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار الكود
            new_code = request.form.get('wbs_code')
            if new_code and new_code != wbs.wbs_code:
                existing = WBS.query.filter_by(
                    project_id=wbs.project_id,
                    wbs_code=new_code
                ).first()
                if existing:
                    flash('كود WBS موجود مسبقاً', 'danger')
                    return redirect(url_for('primavera.wbs_edit', wbs_id=wbs.id))
            
            # تحديث البيانات
            old_parent_id = wbs.parent_id
            wbs.wbs_code = new_code
            wbs.name = request.form.get('name')
            wbs.description = request.form.get('description')
            wbs.parent_id = request.form.get('parent_id') or None
            wbs.weight = float(request.form.get('weight', 0))
            wbs.budget = float(request.form.get('budget', 0))
            wbs.planned_cost = float(request.form.get('planned_cost', 0))
            
            # تحديث المستوى والمسار إذا تغير الأب
            if old_parent_id != wbs.parent_id:
                if wbs.parent_id:
                    parent = WBS.query.get(wbs.parent_id)
                    wbs.level = parent.level + 1
                    wbs.wbs_path = f"{parent.wbs_path}.{wbs.wbs_code}" if parent.wbs_path else wbs.wbs_code
                else:
                    wbs.level = 1
                    wbs.wbs_path = wbs.wbs_code
                
                # تحديث جميع العناصر الفرعية
                update_children_levels(wbs.id)
            
            db.session.commit()
            
            flash('تم تحديث عنصر WBS بنجاح', 'success')
            return redirect(url_for('primavera.wbs_list', project_id=wbs.project_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # بيانات النموذج
    wbs_list = WBS.query.filter_by(project_id=wbs.project_id).filter(WBS.id != wbs.id).order_by(WBS.level, WBS.wbs_code).all()
    
    return render_template('primavera/wbs/wbs_edit.html',
                         wbs=wbs,
                         wbs_list=wbs_list,
                         now=datetime.now())


@primavera_bp.route('/wbs/<int:wbs_id>')
@login_required
def wbs_detail(wbs_id):
    """عرض تفاصيل عنصر WBS"""
    wbs = WBS.query.get_or_404(wbs_id)
    
    if not check_project_access(wbs.project_id):
        return redirect(url_for('primavera.projects_list'))
    
    # العناصر الفرعية
    children = WBS.query.filter_by(parent_id=wbs.id).order_by(WBS.wbs_code).all()
    
    # الأنشطة المرتبطة
    activities = Activity.query.filter_by(wbs_id=wbs.id).all()
    
    # إحصائيات
    stats = calculate_wbs_node_stats(wbs.id)
    
    # حساب التقدم
    progress = wbs.calculate_progress() if hasattr(wbs, 'calculate_progress') else wbs.progress_percentage
    
    return render_template('primavera/wbs/wbs_detail.html',
                         wbs=wbs,
                         children=children,
                         activities=activities,
                         stats=stats,
                         progress=progress,
                         now=datetime.now())

@primavera_bp.route('/apis/wbs/<int:wbs_id>')
@login_required
def wbs_detailing(wbs_id):
    """عرض تفاصيل عنصر WBS"""
    wbs = WBS.query.get_or_404(wbs_id)
    
    if not check_project_access(wbs.project_id):
        return redirect(url_for('primavera.projects_list'))
    
    # العناصر الفرعية
    children = WBS.query.filter_by(parent_id=wbs.id).order_by(WBS.wbs_code).all()
    
    # الأنشطة المرتبطة
    activities = Activity.query.filter_by(wbs_id=wbs.id).all()
    
    # إحصائيات
    stats = calculate_wbs_node_stats(wbs.id)
    
    # حساب التقدم
    progress = wbs.calculate_progress() if hasattr(wbs, 'calculate_progress') else wbs.progress_percentage
    
    return render_template('primavera/wbs/wbs_detail22.html',
                         wbs=wbs,
                         children=children,
                         activities=activities,
                         stats=stats,
                         progress=progress,
                         now=datetime.now())

@primavera_bp.route('/api/wbs/<int:wbs_id>/delete', methods=['POST'])
@login_required
def api_wbs_delete(wbs_id):
    """API لحذف عنصر WBS"""
    wbs = WBS.query.get_or_404(wbs_id)
    
    if not check_project_access(wbs.project_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        # التحقق من وجود أنشطة مرتبطة
        activities_count = Activity.query.filter_by(wbs_id=wbs.id).count()
        if activities_count > 0:
            return jsonify({
                'success': False, 
                'error': f'لا يمكن حذف العنصر لأنه مرتبط بـ {activities_count} أنشطة'
            }), 400
        
        # التحقق من وجود عناصر فرعية
        children_count = WBS.query.filter_by(parent_id=wbs.id).count()
        if children_count > 0:
            return jsonify({
                'success': False, 
                'error': f'لا يمكن حذف العنصر لأنه يحتوي على {children_count} عناصر فرعية'
            }), 400
        
        db.session.delete(wbs)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@primavera_bp.route('/api/wbs/<int:wbs_id>/progress', methods=['POST'])
@login_required
def api_wbs_update_progress(wbs_id):
    """API لتحديث تقدم عنصر WBS"""
    wbs = WBS.query.get_or_404(wbs_id)
    
    if not check_project_access(wbs.project_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # تحديث التقدم
        if hasattr(wbs, 'calculate_progress'):
            new_progress = wbs.calculate_progress()
        else:
            new_progress = data.get('progress', wbs.progress_percentage)
        
        wbs.progress_percentage = new_progress
        db.session.commit()
        
        return jsonify({
            'success': True,
            'progress': new_progress
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@primavera_bp.route('/api/wbs/<int:wbs_id>/stats')
@login_required
def api_wbs_stats(wbs_id):
    """API لإحصائيات عنصر WBS"""
    wbs = WBS.query.get_or_404(wbs_id)
    
    if not check_project_access(wbs.project_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    stats = calculate_wbs_node_stats(wbs.id)
    
    return jsonify({'success': True, 'stats': stats})


@primavera_bp.route('/api/project/<int:project_id>/wbs/export')
@login_required
def api_wbs_export(project_id):
    """API لتصدير WBS كملف"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        wbs_nodes = WBS.query.filter_by(project_id=project_id).order_by(WBS.level, WBS.wbs_code).all()
        
        # تجهيز بيانات CSV
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # كتابة الرأس
        writer.writerow(['المستوى', 'الكود', 'الاسم', 'الوزن', 'الميزانية', 'التكلفة المخططة', 'التكلفة الفعلية', 'التقدم', 'العنصر الأب'])
        
        # كتابة البيانات
        for node in wbs_nodes:
            parent_code = node.parent.wbs_code if node.parent else ''
            writer.writerow([
                node.level,
                node.wbs_code,
                node.name,
                node.weight,
                node.budget,
                node.planned_cost,
                node.actual_cost,
                f"{node.progress_percentage}%",
                parent_code
            ])
        
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=wbs_{project.project_code}.csv'}
        )
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# دوال مساعدة لـ WBS
# ============================================

def calculate_wbs_node_stats(wbs_id):
    """حساب إحصائيات عقدة WBS"""
    wbs = WBS.query.get(wbs_id)
    if not wbs:
        return {}
    
    # العناصر الفرعية
    children = WBS.query.filter_by(parent_id=wbs_id).all()
    
    # الأنشطة المرتبطة مباشرة
    direct_activities = Activity.query.filter_by(wbs_id=wbs_id).all()
    
    # حساب إحصائيات الأنشطة
    total_activities = len(direct_activities)
    completed_activities = len([a for a in direct_activities if a.status == 'completed'])
    in_progress_activities = len([a for a in direct_activities if a.status == 'in_progress'])
    
    # حساب التكلفة من الأنشطة
    activities_cost = sum(a.planned_cost or 0 for a in direct_activities)
    activities_actual = sum(a.actual_cost or 0 for a in direct_activities)
    
    # حساب إجمالي الميزانية (بما في ذلك العناصر الفرعية)
    total_budget = wbs.budget or 0
    total_planned = wbs.planned_cost or 0
    total_actual = wbs.actual_cost or 0
    
    for child in children:
        child_stats = calculate_wbs_node_stats(child.id)
        total_budget += child_stats.get('total_budget', 0)
        total_planned += child_stats.get('total_planned', 0)
        total_actual += child_stats.get('total_actual', 0)
        total_activities += child_stats.get('total_activities', 0)
        completed_activities += child_stats.get('completed_activities', 0)
        in_progress_activities += child_stats.get('in_progress_activities', 0)
    
    return {
        'total_budget': total_budget,
        'total_planned': total_planned,
        'total_actual': total_actual,
        'variance': total_planned - total_actual,
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'in_progress_activities': in_progress_activities,
        'children_count': len(children)
    }


def update_children_levels(parent_id):
    """تحديث مستويات جميع العناصر الفرعية"""
    children = WBS.query.filter_by(parent_id=parent_id).all()
    
    for child in children:
        parent = WBS.query.get(parent_id)
        child.level = parent.level + 1
        child.wbs_path = f"{parent.wbs_path}.{child.wbs_code}"
        
        # تحديث أحفادهم
        update_children_levels(child.id)
# ============================================
# 4️⃣ Activities – الأنشطة (ربط مع نظام المهام الحالي)
# ============================================

@primavera_bp.route('/project/<int:project_id>/activities')
@login_required
def activities_list(project_id):
    """عرض قائمة الأنشطة"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    activities = Activity.query.filter_by(project_id=project_id).order_by(Activity.activity_id).all()
    wbs_nodes = WBS.query.filter_by(project_id=project_id).all()
    calendars = Calendar.query.filter_by(org_id=current_user.org_id).all()
    
    # ربط مع المهام الحالية إن وجدت
    for activity in activities:
        if activity.project and activity.project.original_project:
            activity.related_task = Task.query.filter_by(
                project_id=activity.project.original_project.id,
                task_code=activity.activity_id
            ).first()
    
    return render_template('primavera/activities.html',
                         project=project,
                         activities=activities,
                         wbs_nodes=wbs_nodes,
                         calendars=calendars)
@primavera_bp.route('/project/<int:project_id>/activity/create', methods=['GET', 'POST'])
@login_required
def create_activitys(project_id):
    """إنشاء نشاط جديد في المشروع"""
    # التحقق من الوصول للمشروع
    project = check_project_access(project_id)
    if not project:
        flash('غير مصرح بالوصول إلى المشروع', 'danger')
        return redirect(url_for('primavera.projects_list'))
    
    if request.method == 'POST':
        try:
            # إنشاء activity_id تلقائي إذا لم يتم إدخاله
            activity_id = request.form.get('activity_id')
            if not activity_id:
                last_activity = Activity.query.filter_by(project_id=project_id)\
                    .order_by(Activity.id.desc()).first()
                if last_activity and last_activity.activity_id:
                    # استخراج الرقم من آخر كود (مثل A1000 -> 1000)
                    import re
                    numbers = re.findall(r'\d+', last_activity.activity_id)
                    last_num = int(numbers[0]) if numbers else 1000
                    activity_id = f"A{last_num + 1}"
                else:
                    activity_id = "A1000"
            
            # معالجة التواريخ
            planned_start = None
            if request.form.get('planned_start'):
                planned_start = datetime.strptime(request.form.get('planned_start'), '%Y-%m-%d')
            
            planned_finish = None
            if request.form.get('planned_finish'):
                planned_finish = datetime.strptime(request.form.get('planned_finish'), '%Y-%m-%d')
            
            # معالجة المدة
            original_duration = float(request.form.get('original_duration', 1))
            
            # إنشاء النشاط
            activity = Activity(
                project_id=project_id,
                wbs_id=request.form.get('wbs_id') or None,
                calendar_id=request.form.get('calendar_id') or None,
                activity_id=activity_id,
                activity_code=request.form.get('activity_code'),
                activity_name=request.form.get('activity_name'),
                description=request.form.get('description'),
                instructions=request.form.get('instructions'),
                activity_type=request.form.get('activity_type', 'task_dependent'),
                
                # المدة والتواريخ
                original_duration=original_duration,
                remaining_duration=original_duration,
                actual_duration=0,
                at_complete_duration=original_duration,
                
                planned_start=planned_start,
                planned_finish=planned_finish,
                
                # الوزن والأولوية
                weight=float(request.form.get('weight', 1)),
                priority=int(request.form.get('priority', 3)),
                
                # المسؤولون
                responsible_id=request.form.get('responsible_id') or None,
                supervisor_id=request.form.get('supervisor_id') or None,
                delegate_id=request.form.get('delegate_id') or None,
                
                # الحالة
                status='not_started',
                progress_percentage=0,
                
                # الموقع
                location=request.form.get('location'),
                coordinates=request.form.get('coordinates'),
                
                # القيود
                primary_constraint=request.form.get('primary_constraint'),
                secondary_constraint=request.form.get('secondary_constraint'),
                
                created_by=current_user.id
            )
            
            # معالجة القيود مع التواريخ
            if request.form.get('primary_constraint_date'):
                activity.primary_constraint_date = datetime.strptime(
                    request.form.get('primary_constraint_date'), '%Y-%m-%d'
                )
            
            if request.form.get('secondary_constraint_date'):
                activity.secondary_constraint_date = datetime.strptime(
                    request.form.get('secondary_constraint_date'), '%Y-%m-%d'
                )
            
            db.session.add(activity)
            db.session.flush()  # للحصول على ID قبل حفظ العلاقات
            
            # معالجة أكواد النشاط (Activity Codes)
            activity_code_types = request.form.getlist('activity_code_types[]')
            activity_code_values = request.form.getlist('activity_code_values[]')
            
            if activity_code_types and activity_code_values:
                codes_dict = {}
                for i, code_type in enumerate(activity_code_types):
                    if i < len(activity_code_values) and activity_code_values[i]:
                        codes_dict[code_type] = activity_code_values[i]
                
                if codes_dict:
                    activity.activity_code_values = codes_dict
            
            # معالجة الحقول المخصصة (UDF)
            udf_names = request.form.getlist('udf_names[]')
            udf_values = request.form.getlist('udf_values[]')
            
            if udf_names and udf_values:
                udf_dict = {}
                for i, udf_name in enumerate(udf_names):
                    if i < len(udf_values) and udf_values[i]:
                        udf_dict[udf_name] = udf_values[i]
                
                if udf_dict:
                    activity.udf_values = udf_dict
            
            db.session.commit()
            
            # إشعار للمسؤول
            if activity.responsible_id:
                from app.services.notification_service import NotificationService
                NotificationService.task_assigned(
                    task_name=activity.activity_name,
                    assigned_to=activity.responsible_id,
                    assigned_by=current_user.id,
                    project_id=project_id,
                    activity_id=activity.id
                )
            
            flash('تم إنشاء النشاط بنجاح', 'success')
            return redirect(url_for('primavera.activity_detail', activity_id=activity.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
            current_app.logger.error(f"Error creating activity: {str(e)}")
    
    # بيانات النموذج للـ GET request
    org_id = project.eps.org_id if project.eps else current_user.org_id
    
    # قائمة WBS
    wbs_list = WBS.query.filter_by(project_id=project_id).order_by(WBS.wbs_code).all()
    
    # قائمة التقويمات
    calendars = Calendar.query.filter_by(org_id=org_id, is_active=True).all()
    
    # المشرفين والمسؤولين
    supervisors = User.query.filter(
        User.org_id == org_id,
        User.role.in_(['org_admin', 'project_manager', 'supervisor'])
    ).all()
    
    delegates = User.query.filter_by(org_id=org_id, role='delegate').all()
    
    # الأدوار الوظيفية
    roles = Role.query.filter_by(org_id=org_id).all() if 'Role' in dir() else []
    
    # أنواع أكواد الأنشطة
    activity_code_types = []
    if 'ActivityCode' in dir():
        code_types = db.session.query(ActivityCode.code_type).distinct().all()
        for code_type in code_types:
            codes = ActivityCode.query.filter_by(
                org_id=org_id,
                code_type=code_type[0]
            ).all()
            activity_code_types.append({
                'type': code_type[0],
                'codes': codes
            })
    
    # الحقول المخصصة (UDF)
    udf_fields = []
    if 'UDF' in dir():
        udf_fields = UDF.query.filter_by(
            org_id=org_id,
            udf_type='activity',
            is_active=True
        ).all()
    
    # أنواع القيود
    constraint_types = [
        {'value': '', 'label': '-- بدون قيد --'},
        {'value': 'start_no_earlier_than', 'label': 'البدء ليس قبل'},
        {'value': 'start_no_later_than', 'label': 'البدء ليس بعد'},
        {'value': 'finish_no_earlier_than', 'label': 'الانتهاء ليس قبل'},
        {'value': 'finish_no_later_than', 'label': 'الانتهاء ليس بعد'},
        {'value': 'must_start_on', 'label': 'يجب أن يبدأ في'},
        {'value': 'must_finish_on', 'label': 'يجب أن ينتهي في'},
        {'value': 'as_late_as_possible', 'label': 'متأخر قدر الإمكان'}
    ]
    
    return render_template('primavera/activity_create.html',
                         project=project,
                         wbs_list=wbs_list,
                         calendars=calendars,
                         supervisors=supervisors,
                         delegates=delegates,
                         roles=roles,
                         activity_code_types=activity_code_types,
                         udf_fields=udf_fields,
                         constraint_types=constraint_types,
                         now=datetime.now(),
                         timedelta=timedelta)
@primavera_bp.route('/activities/create', methods=['POST'])
@login_required
def activity_create():
    """إنشاء نشاط جديد وربطه مع نظام المهام"""
    try:
        project_id = request.form.get('project_id')
        project = check_project_access(project_id)
        if not project:
            return jsonify({'error': 'غير مصرح'}), 403
        
        # إنشاء activity_id تلقائي إذا لم يتم إدخاله
        activity_id = request.form.get('activity_id')
        if not activity_id:
            last_activity = Activity.query.filter_by(project_id=project_id).order_by(Activity.id.desc()).first()
            if last_activity:
                last_num = int(last_activity.activity_id[1:]) if last_activity.activity_id[0] == 'A' else 1000
                activity_id = f"A{last_num + 1}"
            else:
                activity_id = "A1000"
        
        # إنشاء النشاط في Primavera
        activity = Activity(
            project_id=project_id,
            wbs_id=request.form.get('wbs_id') or None,
            calendar_id=request.form.get('calendar_id') or None,
            activity_id=activity_id,
            activity_code=request.form.get('activity_code'),
            activity_name=request.form.get('activity_name'),
            description=request.form.get('description'),
            activity_type=request.form.get('activity_type', 'task_dependent'),
            original_duration=float(request.form.get('original_duration', 1)),
            remaining_duration=float(request.form.get('original_duration', 1)),
            planned_start=datetime.strptime(request.form.get('planned_start'), '%Y-%m-%d') if request.form.get('planned_start') else None,
            planned_finish=datetime.strptime(request.form.get('planned_finish'), '%Y-%m-%d') if request.form.get('planned_finish') else None,
            weight=float(request.form.get('weight', 1)),
            priority=int(request.form.get('priority', 3)),
            responsible_id=request.form.get('responsible_id') or None
        )
        
        db.session.add(activity)
        db.session.flush()
        
        # إذا كان المشروع مرتبطاً بمشروع عادي، أنشئ مهمة مقابلة
        if project.original_project:
            # إنشاء مهمة في النظام العادي
            task = Task(
                project_id=project.original_project.id,
                task_code=activity.activity_id,
                task_name=activity.activity_name,
                description=activity.description,
                task_order=activity.id,
                supervisor_id=activity.responsible_id or project.original_project.project_manager_id,
                planned_start_date=activity.planned_start.date() if activity.planned_start else None,
                planned_end_date=activity.planned_finish.date() if activity.planned_finish else None,
                planned_duration=activity.original_duration * 8,  # تحويل الأيام إلى ساعات
                status='pending',
                created_by=current_user.id
            )
            db.session.add(task)
            
            # ربط المهمة بالنشاط (يمكن إضافة حقل في Task لربط activity_id)
        
        db.session.commit()
        
        # إشعار للمسؤول
        if activity.responsible_id:
            NotificationService.task_assigned(
                task=None,  # يمكن تعديله لاحقاً
                assigned_to=activity.responsible_id,
                assigned_by=current_user.id
            )
        
        return jsonify({'success': True, 'activity': {
            'id': activity.id,
            'activity_id': activity.activity_id,
            'activity_name': activity.activity_name,
            'activity_type': activity.activity_type
        }})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
# @primavera_bp.route('/activity/<int:activity_id>')
# @login_required
# def activity_detail(activity_id):
#     """عرض تفاصيل النشاط"""
#     activity = Activity.query.get_or_404(activity_id)

#     # التحقق من الصلاحية
#     if not check_project_access(activity.project_id):
#         flash('غير مصرح بالوصول', 'danger')
#         return redirect(url_for('company.projects'))
    
#     return render_template('primavera/activity_detail.html',
#                          activity=activity)
# ============================================
# 5️⃣ Relationships – العلاقات
# ============================================

@primavera_bp.route('/project/<int:project_id>/relationships')
@login_required
def relationships_list(project_id):
    """عرض العلاقات بين الأنشطة"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    relationships = ActivityRelationship.query.filter_by(project_id=project_id).all()
    
    # استخدام to_dict() لتحويل الأنشطة إلى JSON-friendly format
    activities_json = [activity.to_dict() for activity in activities]
    
    # تحويل العلاقات إلى JSON-friendly format
    relationships_json = []
    for rel in relationships:
        relationships_json.append({
            'id': rel.id,
            'predecessor_id': rel.predecessor_id,
            'successor_id': rel.successor_id,
            'relationship_type': rel.relationship_type,
            'lag_days': rel.lag_days,
            'is_critical': rel.is_critical
        })
    
    return render_template('primavera/relationships.html',
                         project=project,
                         activities=activities,
                         relationships=relationships,
                         activities_json=activities_json,
                         relationships_json=relationships_json)  

@primavera_bp.route('/relationships/create', methods=['POST'])
@login_required
def relationship_create():
    """إنشاء علاقة جديدة"""
    try:
        project_id = request.form.get('project_id')
        project = check_project_access(project_id)
        if not project:
            return jsonify({'error': 'غير مصرح'}), 403
        
        predecessor_id = request.form.get('predecessor_id')
        successor_id = request.form.get('successor_id')
        
        # التحقق من عدم وجود علاقة دائرية
        if _would_create_circular_relationship(predecessor_id, successor_id):
            return jsonify({'error': 'العلاقة ستؤدي إلى دورة لا نهائية'}), 400
        
        # التحقق من عدم وجود علاقة مكررة
        existing = ActivityRelationship.query.filter_by(
            project_id=project_id,
            predecessor_id=predecessor_id,
            successor_id=successor_id
        ).first()
        
        if existing:
            return jsonify({'error': 'العلاقة موجودة مسبقاً'}), 400
        
        relationship = ActivityRelationship(
            project_id=project_id,
            predecessor_id=predecessor_id,
            successor_id=successor_id,
            relationship_type=request.form.get('relationship_type', 'FS'),
            lag_days=float(request.form.get('lag_days', 0))
        )
        
        db.session.add(relationship)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def _would_create_circular_relationship(self, predecessor_id, successor_id, visited=None):
    """التحقق من عدم إنشاء علاقة دائرية"""
    if visited is None:
        visited = set()
    
    if successor_id in visited:
        return True
    
    visited.add(successor_id)
    
    # الحصول على جميع العلاقات التي تبدأ من successor
    relationships = ActivityRelationship.query.filter_by(predecessor_id=successor_id).all()
    
    for rel in relationships:
        if rel.successor_id == predecessor_id:
            return True
        if self._would_create_circular_relationship(predecessor_id, rel.successor_id, visited):
            return True
    
    return False

# ============================================
# 6️⃣ Resources – الموارد
# ============================================

@primavera_bp.route('/resources')
@login_required
def resources_list():
    """عرض قائمة الموارد"""
    org_id = get_org_id()
    
    if org_id:
        resources = Resource.query.filter_by(org_id=org_id).all()
    else:
        resources = Resource.query.all()
    
    # إحصائيات الموارد
    for resource in resources:
        resource.total_assigned = sum(a.planned_quantity for a in resource.assignments)
    
    return render_template('primavera/resources.html', resources=resources)

@primavera_bp.route('/resources/create', methods=['POST'])
@login_required
def resource_create():
    """إنشاء مورد جديد"""
    try:
        # التحقق من عدم تكرار الرمز
        existing = Resource.query.filter_by(
            org_id=current_user.org_id,
            resource_id=request.form.get('resource_id')
        ).first()
        
        if existing:
            return jsonify({'error': 'رمز المورد موجود مسبقاً'}), 400
        
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
        
        return jsonify({'success': True, 'resource': {
            'id': resource.id,
            'resource_id': resource.resource_id,
            'name': resource.name
        }})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@primavera_bp.route('/resources/assign', methods=['POST'])
@login_required
def resource_assign():
    """تعيين مورد لنشاط"""
    try:
        activity_id = request.form.get('activity_id')
        resource_id = request.form.get('resource_id')
        quantity = float(request.form.get('quantity', 0))
        
        activity = Activity.query.get_or_404(activity_id)
        resource = Resource.query.get_or_404(resource_id)
        
        # التحقق من الصلاحية
        if activity.project.eps.org_id != current_user.org_id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        # التحقق من توفر الكمية
        total_assigned = sum(a.planned_quantity for a in resource.assignments)
        if total_assigned + quantity > resource.available_quantity:
            return jsonify({'error': 'الكمية المطلوبة غير متوفرة'}), 400
        
        assignment = ActivityResource(
            activity_id=activity_id,
            resource_id=resource_id,
            planned_quantity=quantity,
            planned_cost=quantity * resource.cost_per_unit
        )
        
        db.session.add(assignment)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# 7️⃣ Scheduling – الجدولة وحساب المسار الحرج
# ============================================

@primavera_bp.route('/project/<int:project_id>/schedule', methods=['POST'])
@login_required
def run_schedule(project_id):
    """تشغيل الجدولة وحساب المسار الحرج"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    engine = PrimaveraEngine(project)
    result = engine.run_schedule()
    
    # تحديث إحصائيات المشروع
    project.total_activities = result['total_activities']
    project.critical_activities = result['critical_activities']
    project.total_float = result['total_float']
    
    if project.original_project:
        project.original_project.progress_percentage = result.get('progress', 0)
    
    db.session.commit()
    
    # إشعار للمدير
    if project.eps and project.eps.manager_id:
        NotificationService.system_alert(
            user_id=project.eps.manager_id,
            title=f'📊 جدولة مشروع {project.name}',
            message=f'تمت جدولة المشروع. المدة: {result["project_duration"]} يوم، الأنشطة الحرجة: {result["critical_activities"]}',
            priority='medium'
        )
    
    return jsonify({'success': True, 'result': result})

@primavera_bp.route('/project/<int:project_id>/critical-path')
@login_required
def critical_path(project_id):
    """عرض المسار الحرج"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    engine = PrimaveraEngine(project)
    engine.load_project_data()
    critical_activities = [a for a in engine.activities if a.is_critical]
    
    # ترتيب المسار الحرج
    path = engine.get_critical_path()
    
    # حساب إحصائيات المسار الحرج
    total_duration = sum(a.original_duration for a in critical_activities)
    
    return render_template('primavera/critical_path.html',
                         project=project,
                         critical_activities=critical_activities,
                         path=path,
                         total_duration=total_duration)

# ============================================
# 8️⃣ Baseline – خط الأساس
# ============================================

@primavera_bp.route('/project/<int:project_id>/baselines')
@login_required
def baselines_list(project_id):
    """عرض خطوط الأساس"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    baselines = Baseline.query.filter_by(project_id=project_id).order_by(Baseline.version.desc()).all()
    
    return render_template('primavera/baselines.html',
                         project=project,
                         baselines=baselines)

@primavera_bp.route('/project/<int:project_id>/baseline/create', methods=['POST'])
@login_required
def baseline_create(project_id):
    """إنشاء خط أساس جديد"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    name = request.form.get('name', f'Baseline {datetime.now().strftime("%Y-%m-%d")}')
    
    try:
        baseline = create_baseline(project, name)
        
        # إشعار
        NotificationService.system_alert(
            user_id=current_user.id,
            title='📋 خط أساس جديد',
            message=f'تم إنشاء خط الأساس "{name}" للمشروع {project.name}',
            priority='low'
        )
        
        return jsonify({'success': True, 'baseline': {
            'id': baseline.id,
            'name': baseline.name,
            'version': baseline.version
        }})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@primavera_bp.route('/project/<int:project_id>/baseline/<int:baseline_id>/compare')
@login_required
def baseline_compare(project_id, baseline_id):
    """مقارنة مع خط الأساس"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    baseline = Baseline.query.get_or_404(baseline_id)
    engine = PrimaveraEngine(project)
    engine.load_project_data()
    comparison = engine.compare_with_baseline(baseline)
    
    return render_template('primavera/baseline_compare.html',
                         project=project,
                         baseline=baseline,
                         comparison=comparison)

# ============================================
# 9️⃣ Project Dashboard – لوحة تحكم المشروع
# ============================================

@primavera_bp.route('/project/<int:project_id>/dashboard')
@login_required
def project_dashboard(project_id):
    """لوحة تحكم المشروع"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    engine = PrimaveraEngine(project)
    engine.load_project_data()
    
    # إحصائيات
    stats = {
        'total_activities': len(engine.activities),
        'completed_activities': len([a for a in engine.activities if a.status == 'completed']),
        'in_progress_activities': len([a for a in engine.activities if a.status == 'in_progress']),
        'not_started_activities': len([a for a in engine.activities if a.status == 'not_started']),
        'critical_activities': len([a for a in engine.activities if a.is_critical]),
        'total_resources': ActivityResource.query.filter(ActivityResource.activity_id.in_([a.id for a in engine.activities])).count() if engine.activities else 0,
        'total_cost': project.project.total_planned_cost,
        'actual_cost': project.project.total_actual_cost
    }
    
    # حساب التقدم
    if stats['total_activities'] > 0:
        stats['progress'] = (stats['completed_activities'] / stats['total_activities']) * 100
    else:
        stats['progress'] = 0
    
    # الموارد الأكثر استخداماً
    top_resources = db.session.query(
        Resource.name,
        func.sum(ActivityResource.planned_quantity).label('total_quantity')
    ).join(ActivityResource)\
     .join(Activity)\
     .filter(Activity.project_id == project_id)\
     .group_by(Resource.id, Resource.name)\
     .order_by(func.sum(ActivityResource.planned_quantity).desc())\
     .limit(5).all()
    
    # الأنشطة المتأخرة
    delayed_activities = [a for a in engine.activities if a.status != 'completed' and a.planned_finish and a.planned_finish.date() < date.today()]
    today = date.today()
    return render_template('primavera/dashboard.html',
                         project=project,
                         stats=stats,
                         top_resources=top_resources,
                         critical_path=engine.get_critical_path(),
                         delayed_activities=delayed_activities,today=today)

# ============================================
# 🔟 Reports – التقارير
# ============================================

@primavera_bp.route('/project/<int:project_id>/reports')
@login_required
def reports(project_id):
    """صفحة التقارير"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    return render_template('primavera/reports.html', project=project)

@primavera_bp.route('/project/<int:project_id>/reports/progress')
@login_required
def progress_report(project_id):
    """تقرير التقدم (JSON)"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    report = {
        'project_name': project.name,
        'report_date': datetime.now().strftime('%Y-%m-%d'),
        'overall_progress': project.project.progress_percentage,
        'activities_by_status': {
            'not_started': len([a for a in activities if a.status == 'not_started']),
            'in_progress': len([a for a in activities if a.status == 'in_progress']),
            'completed': len([a for a in activities if a.status == 'completed'])
        },
        'critical_activities': len([a for a in activities if a.is_critical]),
        'total_cost': project.project.total_planned_cost,
        'actual_cost': project.project.total_actual_cost,
        'activities': [{
            'id': a.activity_id,
            'name': a.activity_name,
            'status': a.status,
            'progress': a.progress_percentage,
            'planned_start': a.planned_start.strftime('%Y-%m-%d') if a.planned_start else None,
            'planned_finish': a.planned_finish.strftime('%Y-%m-%d') if a.planned_finish else None,
            'actual_start': a.actual_start.strftime('%Y-%m-%d') if a.actual_start else None,
            'actual_finish': a.actual_finish.strftime('%Y-%m-%d') if a.actual_finish else None,
            'is_critical': a.is_critical,
            'total_float': a.total_float
        } for a in activities]
    }
    
    return jsonify(report)

@primavera_bp.route('/project/<int:project_id>/reports/resources')
@login_required
def resources_report(project_id):
    """تقرير الموارد"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    resources_data = []
    
    for resource in Resource.query.filter_by(org_id=project.eps.org_id).all():
        assignments = ActivityResource.query.filter_by(resource_id=resource.id)\
            .join(Activity).filter(Activity.project_id == project_id).all()
        
        total_assigned = sum(a.planned_quantity for a in assignments)
        
        resources_data.append({
            'resource_id': resource.resource_id,
            'name': resource.name,
            'type': resource.resource_type,
            'unit': resource.unit,
            'available': resource.available_quantity,
            'assigned': total_assigned,
            'utilization': (total_assigned / resource.available_quantity * 100) if resource.available_quantity > 0 else 0,
            'cost': sum(a.planned_cost for a in assignments)
        })
    
    return jsonify({'success': True, 'resources': resources_data})

# ============================================
# تحويل المشروع العادي إلى Primavera
# ============================================
@primavera_bp.route('/convert-project/<int:project_id>', methods=['POST'])
@login_required
def convert_project(project_id):
    """تحويل مشروع عادي إلى مشروع Primavera مع دعم الملاحظات والوثائق"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != current_user.org_id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # التحقق من عدم وجود تحويل سابق
        existing = Project.query.filter_by(project_id=project_id).first()
        if existing:
            return jsonify({'error': 'المشروع محول مسبقاً', 'primavera_id': existing.id}), 400
        
        # ============ 1. إنشاء EPS ============
        # اختيار EPS افتراضي أو إنشاؤه
        default_eps = EPS.query.filter_by(org_id=project.org_id).first()
        if not default_eps:
            # إنشاء EPS افتراضي مع دعم للغات
            default_eps = EPS(
                org_id=project.org_id,
                eps_code='DEFAULT',
                name='Default Projects',
                name_ar='المشاريع الافتراضية',
                description='Auto-generated EPS for project conversion',
                level=1,
                path='DEFAULT',
                is_active=True
            )
            db.session.add(default_eps)
            db.session.flush()
        
        # ============ 2. إنشاء OBS افتراضي ============
        # إنشاء OBS مرتبط بنفس المؤسسة
        default_obs = OBS.query.filter_by(org_id=project.org_id).first()
        if not default_obs:
            default_obs = OBS(
                org_id=project.org_id,
                obs_code='DEFAULT',
                name='Default OBS',
                name_ar='الهيكل التنظيمي الافتراضي',
                description='Auto-generated OBS for project',
                level=1,
                path='DEFAULT',
                responsible_id=project.project_manager_id
            )
            db.session.add(default_obs)
            db.session.flush()
        
        # ============ 3. إنشاء التقويم ============
        # اختيار تقويم افتراضي أو إنشاؤه
        default_calendar = Calendar.query.filter_by(org_id=project.org_id, is_default=True).first()
        if not default_calendar:
            default_calendar = Calendar.query.filter_by(org_id=project.org_id).first()
            if not default_calendar:
                # إنشاء تقويم افتراضي
                default_calendar = Calendar(
                    org_id=project.org_id,
                    name='Standard Calendar',
                    calendar_type='project',
                    work_days=[1, 2, 3, 4, 5, 6],  # السبت - الخميس
                    work_hours_per_day=8.0,
                    work_start=datetime.strptime('08:00', '%H:%M').time(),
                    work_end=datetime.strptime('17:00', '%H:%M').time(),
                    is_default=True,
                    is_active=True
                )
                db.session.add(default_calendar)
                db.session.flush()
        
        # ============ 4. إنشاء مشروع Primavera ============
        primavera_project = Project(
            project_id=project.id,
            eps_id=default_eps.id,
            obs_id=default_obs.id,  # ربط OBS
            calendar_id=default_calendar.id if default_calendar else None,
            name=project.name,
            project_code=project.project_code,
            description=project.description,
            site_name=project.site_name,
            site_name_ar=project.site_name_ar,
            city=project.city,
            country=project.country or 'Yemen',
            location_address=project.location_address,
            location_coordinates=project.location_coordinates,
            planned_start=datetime.combine(project.planned_start_date, datetime.min.time()) if project.planned_start_date else None,
            planned_finish=datetime.combine(project.planned_end_date, datetime.min.time()) if project.planned_end_date else None,
            actual_start=datetime.combine(project.actual_start_date, datetime.min.time()) if project.actual_start_date else None,
            actual_end=datetime.combine(project.actual_end_date, datetime.min.time()) if project.actual_end_date else None,
            total_planned_cost=project.contract_value,
            progress_percentage=project.progress_percentage,
            status=map_project_status(project.status),
            priority=project.priority,
            risk_level=project.complexity,
            created_by=current_user.id
        )
        
        db.session.add(primavera_project)
        db.session.flush()
        
        # ============ 5. إنشاء WBS الرئيسي ============
        root_wbs = WBS(
            project_id=primavera_project.id,
            wbs_code='1',
            name='Project Root',
            name_ar='جذر المشروع',
            description='Root WBS element',
            level=1,
            wbs_path='1',
            budget=project.contract_value,
            planned_cost=project.contract_value,
            weight=100.0
        )
        db.session.add(root_wbs)
        db.session.flush()
        
        # ============ 6. تحويل المهام إلى أنشطة ============
        tasks = Task.query.filter_by(project_id=project_id).order_by(Task.task_order).all()
        activity_map = {}  # لربط المهام بالأنشطة
        
        for i, task in enumerate(tasks):
            # تحديد الحالة
            if task.status == 'completed':
                activity_status = 'completed'
            elif task.status == 'in_progress':
                activity_status = 'in_progress'
            else:
                activity_status = 'not_started'
            
            # تحويل المدة (إذا كانت بالساعات، نحولها إلى أيام)
            original_duration = (task.planned_duration / 8) if task.planned_duration else 1
            
            activity = Activity(
                project_id=primavera_project.id,
                wbs_id=root_wbs.id,
                activity_id=f"A{1000 + i}",
                activity_code=task.task_code,
                activity_name=task.task_name,
                description=task.description,
                instructions=task.instructions,
                activity_type='task_dependent',
                original_duration=original_duration,
                remaining_duration=original_duration * (1 - task.progress_percentage / 100) if task.progress_percentage < 100 else 0,
                actual_duration=task.actual_duration / 8 if task.actual_duration else 0,
                planned_start=datetime.combine(task.planned_start_date, datetime.min.time()) if task.planned_start_date else None,
                planned_finish=datetime.combine(task.planned_end_date, datetime.min.time()) if task.planned_end_date else None,
                actual_start=task.actual_start_date,
                actual_finish=task.actual_end_date,
                progress_percentage=task.progress_percentage,
                status=activity_status,
                weight=task.weight or 1.0,
                priority=task.priority,
                supervisor_id=task.supervisor_id,
                delegate_id=task.delegate_id,
                responsible_id=task.delegate_id or task.supervisor_id,
                location=task.location,
                coordinates=task.coordinates,
                created_by=current_user.id
            )
            db.session.add(activity)
            db.session.flush()
            
            activity_map[task.id] = activity.id
        
        # ============ 7. إنشاء العلاقات بين الأنشطة ============
        for task in tasks:
            if task.depends_on_task_id and task.depends_on_task_id in activity_map:
                relationship = ActivityRelationship(
                    project_id=primavera_project.id,
                    predecessor_id=activity_map[task.depends_on_task_id],
                    successor_id=activity_map[task.id],
                    relationship_type='FS',  # Finish to Start
                    lag_days=0,
                    is_driving=True
                )
                db.session.add(relationship)
        
        # ============ 8. نقل الملاحظات (Notebook Entries) ============
        # هنا نفترض وجود حقل للملاحظات في المشروع العادي
        if hasattr(project, 'notebook_entries') and project.notebook_entries:
            for note in project.notebook_entries:
                notebook_entry = NotebookEntry(
                    project_id=primavera_project.id,
                    entry_type='note',
                    status='open',
                    subject=note.subject if hasattr(note, 'subject') else 'Migrated Note',
                    content=note.content if hasattr(note, 'content') else str(note),
                    created_by=note.created_by if hasattr(note, 'created_by') else current_user.id,
                    created_at=note.created_at if hasattr(note, 'created_at') else datetime.utcnow(),
                    tags=['migrated']
                )
                db.session.add(notebook_entry)
        
        # ============ 9. نقل المستندات ============
        if hasattr(project, 'documents') and project.documents:
            for doc in project.documents:
                # إنشاء إدخال في Notebook مع المرفق
                notebook_entry = NotebookEntry(
                    project_id=primavera_project.id,
                    entry_type='note',
                    status='closed',
                    subject=f"Document: {doc.filename if hasattr(doc, 'filename') else 'Document'}",
                    content=f"Migrated document from original project",
                    created_by=current_user.id,
                    attachments=[{
                        'filename': doc.filename if hasattr(doc, 'filename') else 'document.pdf',
                        'url': doc.file_url if hasattr(doc, 'file_url') else '',
                        'size': doc.file_size if hasattr(doc, 'file_size') else 0
                    }],
                    tags=['document', 'migrated']
                )
                db.session.add(notebook_entry)
        
        # ============ 10. نقل المخاطر (إذا وجدت) ============
        if hasattr(project, 'risks') and project.risks:
            for risk in project.risks:
                # ربط الخطر بنشاط معين إذا أمكن
                activity_id = None
                if hasattr(risk, 'task_id') and risk.task_id in activity_map:
                    activity_id = activity_map[risk.task_id]
                
                activity_risk = ActivityRisk(
                    activity_id=activity_id,
                    title=risk.title if hasattr(risk, 'title') else 'Risk',
                    description=risk.description if hasattr(risk, 'description') else '',
                    risk_level=risk.risk_level if hasattr(risk, 'risk_level') else 'medium',
                    probability=risk.probability if hasattr(risk, 'probability') else 50,
                    impact=risk.impact if hasattr(risk, 'impact') else 'medium',
                    mitigation_plan=risk.mitigation_plan if hasattr(risk, 'mitigation_plan') else '',
                    status=risk.status if hasattr(risk, 'status') else 'identified',
                    created_by=current_user.id
                )
                db.session.add(activity_risk)
        
        # ============ 11. نقل القرارات (إذا وجدت) ============
        if hasattr(project, 'decisions') and project.decisions:
            for decision in project.decisions:
                notebook_entry = NotebookEntry(
                    project_id=primavera_project.id,
                    entry_type='decision',
                    status='closed' if getattr(decision, 'implemented', False) else 'open',
                    subject=decision.title if hasattr(decision, 'title') else 'Decision',
                    content=decision.description if hasattr(decision, 'description') else '',
                    decision_options=getattr(decision, 'options', []),
                    decision_rationale=getattr(decision, 'rationale', ''),
                    decision_impact=getattr(decision, 'impact', ''),
                    created_by=decision.created_by if hasattr(decision, 'created_by') else current_user.id,
                    created_at=decision.created_at if hasattr(decision, 'created_at') else datetime.utcnow(),
                    tags=['decision', 'migrated']
                )
                db.session.add(notebook_entry)
        
        # ============ 12. نقل الدروس المستفادة ============
        if hasattr(project, 'lessons_learned') and project.lessons_learned:
            for lesson in project.lessons_learned:
                notebook_entry = NotebookEntry(
                    project_id=primavera_project.id,
                    entry_type='lesson',
                    status='closed',
                    subject=lesson.title if hasattr(lesson, 'title') else 'Lesson Learned',
                    content=lesson.description if hasattr(lesson, 'description') else '',
                    category=getattr(lesson, 'category', 'general'),
                    lesson_category=getattr(lesson, 'type', 'improvement'),
                    created_by=lesson.created_by if hasattr(lesson, 'created_by') else current_user.id,
                    created_at=lesson.created_at if hasattr(lesson, 'created_at') else datetime.utcnow(),
                    tags=['lesson', 'migrated']
                )
                db.session.add(notebook_entry)
        
        # ============ 13. تحديث إحصائيات المشروع ============
        primavera_project.total_activities = len(tasks)
        primavera_project.completed_activities = len([t for t in tasks if t.status == 'completed'])
        primavera_project.critical_activities = 0  # سيتم حسابه لاحقاً
        
        # حساب التقدم
        if tasks:
            primavera_project.progress_percentage = sum(t.progress_percentage for t in tasks) / len(tasks)
        
        # ============ 14. ربط EPS مع OBS ============
        eps_obs_assignment = EPSOBSAssignment(
            eps_id=default_eps.id,
            obs_id=default_obs.id,
            permission_level='admin',
            created_by=current_user.id
        )
        db.session.add(eps_obs_assignment)
        
        # ============ 15. حفظ جميع التغييرات ============
        db.session.commit()
        
        # ============ 16. إشعار للمستخدمين ============
        # إشعار لمدير المشروع
        if project.project_manager_id:
            NotificationService.system_alert(
                user_id=project.project_manager_id,
                title='🔄 تحويل المشروع إلى Primavera',
                message=f'تم تحويل المشروع {project.name} إلى نظام Primavera بنجاح',
                notification_type='project_converted',
                related_project_id=primavera_project.id,
                priority='medium'
            )
        
        # إشعار للمشرفين على المهام
        supervisor_ids = set(t.supervisor_id for t in tasks if t.supervisor_id)
        for sup_id in supervisor_ids:
            if sup_id != project.project_manager_id:
                NotificationService.system_alert(
                    user_id=sup_id,
                    title='🔄 تحديث المشروع',
                    message=f'تم تحويل المشروع {project.name} إلى نظام Primavera. مهامك متاحة الآن في النظام الجديد',
                    notification_type='project_converted',
                    related_project_id=primavera_project.id,
                    priority='low'
                )
        
        return jsonify({
            'success': True,
            'primavera_id': primavera_project.id,
            'message': 'تم تحويل المشروع بنجاح',
            'stats': {
                'activities': len(tasks),
                'relationships': len([t for t in tasks if t.depends_on_task_id]),
                'notebook_entries': NotebookEntry.query.filter_by(project_id=primavera_project.id).count(),
                'risks': ActivityRisk.query.filter(ActivityRisk.activity_id.in_(activity_map.values())).count() if activity_map else 0
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error converting project {project_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500


def map_project_status(status):
    """تحويل حالة المشروع العادي إلى حالة Primavera"""
    status_map = {
        'pending': 'planning',
        'planning': 'planning',
        'active': 'active',
        'on_hold': 'suspended',
        'completed': 'completed',
        'cancelled': 'cancelled'
    }
    return status_map.get(status, 'planning')


def create_baseline_from_project(primavera_project_id, name=None):
    """إنشاء خط أساس للمشروع المحول"""
    try:
        if not name:
            name = f"Baseline {datetime.now().strftime('%Y-%m-%d')}"
        
        # الحصول على الأنشطة
        activities = Activity.query.filter_by(project_id=primavera_project_id).all()
        
        # إنشاء Baseline
        baseline = Baseline(
            project_id=primavera_project_id,
            name=name,
            version=1,
            created_by=current_user.id,
            activities_snapshot=[{
                'id': a.id,
                'activity_id': a.activity_id,
                'name': a.activity_name,
                'planned_start': a.planned_start.isoformat() if a.planned_start else None,
                'planned_finish': a.planned_finish.isoformat() if a.planned_finish else None,
                'duration': a.original_duration
            } for a in activities],
            total_cost=sum(a.planned_cost or 0 for a in activities)
        )
        
        db.session.add(baseline)
        db.session.commit()
        
        return baseline
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating baseline: {str(e)}")
        return None
    
# @primavera_bp.route('/convert-project/<int:project_id>', methods=['POST'])
# @login_required
# def convert_project(project_id):
#     """تحويل مشروع عادي إلى مشروع Primavera"""
#     project = Project.query.get_or_404(project_id)
    
#     if project.org_id != current_user.org_id and current_user.role != 'platform_admin':
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     try:
#         # التحقق من عدم وجود تحويل سابق
#         existing = Project.query.filter_by(project_id=project_id).first()
#         if existing:
#             return jsonify({'error': 'المشروع محول مسبقاً', 'primavera_id': existing.id}), 400
        
#         # اختيار EPS افتراضي
#         default_eps = EPS.query.filter_by(org_id=project.org_id).first()
#         if not default_eps:
#             # إنشاء EPS افتراضي
#             default_eps = EPS(
#                 org_id=project.org_id,
#                 eps_code='DEFAULT',
#                 name='المشاريع',
#                 level=1,
#                 path='DEFAULT'
#             )
#             db.session.add(default_eps)
#             db.session.flush()
        
#         # اختيار تقويم افتراضي
#         default_calendar = Calendar.query.filter_by(org_id=project.org_id, is_default=True).first()
#         if not default_calendar:
#             default_calendar = Calendar.query.filter_by(org_id=project.org_id).first()
        
#         primavera_project = Project(
#             project_id=project.id,
#             eps_id=default_eps.id,
#             calendar_id=default_calendar.id if default_calendar else None,
#             name=project.name,
#             project_code=project.project_code,
#             planned_start=datetime.combine(project.planned_start_date, datetime.min.time()) if project.planned_start_date else None,
#             planned_finish=datetime.combine(project.planned_end_date, datetime.min.time()) if project.planned_end_date else None,
#             created_by=current_user.id
#         )
        
#         db.session.add(primavera_project)
#         db.session.flush()
        
#         # إنشاء WBS رئيسي
#         root_wbs = WBS(
#             project_id=primavera_project.id,
#             wbs_code='1',
#             name='المشروع',
#             level=1,
#             wbs_path='1'
#         )
#         db.session.add(root_wbs)
        
#         # تحويل المهام إلى أنشطة
#         tasks = Task.query.filter_by(project_id=project_id).all()
#         for i, task in enumerate(tasks):
#             activity = Activity(
#                 project_id=primavera_project.id,
#                 wbs_id=root_wbs.id,
#                 activity_id=f"A{1000 + i}",
#                 activity_name=task.task_name,
#                 activity_name_ar=task.task_name_ar,
#                 description=task.description,
#                 activity_type='task_dependent',
#                 original_duration=task.planned_duration / 8 if task.planned_duration else 1,
#                 remaining_duration=task.planned_duration / 8 if task.planned_duration else 1,
#                 planned_start=datetime.combine(task.planned_start_date, datetime.min.time()) if task.planned_start_date else None,
#                 planned_finish=datetime.combine(task.planned_end_date, datetime.min.time()) if task.planned_end_date else None,
#                 progress_percentage=task.progress_percentage,
#                 status='not_started' if task.status == 'pending' else 'in_progress' if task.status == 'in_progress' else 'completed',
#                 responsible_id=task.delegate_id or task.supervisor_id,
#                 weight=1
#             )
#             db.session.add(activity)
        
#         db.session.commit()
        
#         # إشعار
#         NotificationService.system_alert(
#             # user_id=current_user.id,
#             title='🔄 تحويل المشروع',
#             message=f'تم تحويل المشروع {project.name} إلى نظام Primavera بنجاح',
#             priority='medium'
#         )
        
#         return jsonify({
#             'success': True,
#             'primavera_id': primavera_project.id,
#             'message': 'تم تحويل المشروع بنجاح'
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500
@primavera_bp.route('/project/<int:project_id>')
@login_required
def project_detail(project_id):
    """عرض تفاصيل المشروع مع جميع التبويبات"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    # بيانات التبويبات
    data = {
        'project': project,
        'eps_list': EPS.query.filter_by(org_id=project.eps.org_id).all(),
        'obs_list': OBS.query.filter_by(org_id=project.eps.org_id).all(),
        'calendars': Calendar.query.filter_by(org_id=project.eps.org_id).all(),
        'project_managers': User.query.filter(
            User.org_id == project.eps.org_id,
            User.role.in_(['org_admin', 'project_manager'])
        ).all(),
        'activity_code_types': get_activity_code_types(project.eps.org_id),
        'resource_code_types': get_resource_code_types(project.eps.org_id),
        'project_resources': get_project_resources(project.id),
        'all_resources': Resource.query.filter_by(org_id=project.eps.org_id).all(),
        'project_attachments': get_project_attachments(project.id),
        'notebook_entries': get_project_notebook_entries(project.id),
        'selected_activity_codes': get_project_activity_codes(project.id),
        'selected_resource_codes': get_project_resource_codes(project.id),
        'resource_stats': calculate_project_resource_stats(project.id),
        'roles': Role.query.filter_by(org_id=project.eps.org_id).all()
    }
    now=datetime.now()
    return render_template('primavera/project_tabs.html',now=now, **data)

# دوال مساعدة لجلب بيانات المشروع
def get_activity_code_types(org_id):
    """الحصول على أنواع أكواد الأنشطة (قواميس الأكواد)"""
    try:
        # جلب جميع قواميس الأكواد النشطة
        dictionaries = ActivityCodeDictionary.query.filter_by(
            org_id=org_id,
            is_active=True
        ).order_by(ActivityCodeDictionary.dict_name).all()
        
        result = []
        for dict in dictionaries:
            # جلب قيم الأكواد لهذا القاموس
            codes = ActivityCodeValue.query.filter_by(
                dictionary_id=dict.id,
                is_active=True
            ).order_by(ActivityCodeValue.display_sequence).all()
            
            # بناء هيكل الشجرة للعرض
            def build_tree(parent_id=None):
                tree = []
                for code in codes:
                    if code.parent_id == parent_id:
                        code_dict = {
                            'id': code.id,
                            'code_value': code.code_value,
                            'description': code.code_description,
                            'display_color': code.display_color,
                            'level': code.level
                        }
                        # إضافة الأبناء
                        children = build_tree(code.id)
                        if children:
                            code_dict['children'] = children
                        tree.append(code_dict)
                return tree
            
            result.append({
                'id': dict.id,
                'name': dict.dict_name,
                'description': dict.description,
                'codes': build_tree(),
                'total_codes': len(codes),
                'is_hierarchical': dict.is_hierarchical
            })
        
        return result
        
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_code_types: {str(e)}")
        return []

def get_resource_code_types(org_id):
    """الحصول على أنواع أكواد الموارد"""
    types = db.session.query(ResourceCode.code_type).distinct().all()
    result = []
    for t in types:
        result.append({
            'id': t[0],
            'name': t[0],
            'codes': ResourceCode.query.filter_by(org_id=org_id, code_type=t[0]).all()
        })
    return result

def get_project_resources(project_id):
    """الحصول على موارد المشروع"""
    try:
        # جلب الموارد المخصصة للأنشطة في المشروع
        activity_resources = db.session.query(
            Resource,
            func.sum(ActivityResource.planned_quantity).label('total_planned'),
            func.sum(ActivityResource.actual_quantity).label('total_actual'),
            func.sum(ActivityResource.planned_cost).label('total_planned_cost'),
            func.sum(ActivityResource.actual_cost).label('total_actual_cost')
        ).join(ActivityResource, Resource.id == ActivityResource.resource_id)\
         .join(Activity, ActivityResource.activity_id == Activity.id)\
         .filter(Activity.project_id == project_id)\
         .group_by(Resource.id).all()
        
        result = []
        for resource, planned_qty, actual_qty, planned_cost, actual_cost in activity_resources:
            result.append({
                'id': resource.id,
                'resource_id': resource.resource_id,
                'name': resource.name,
                'name_ar': resource.name_ar,
                'type': resource.resource_type,
                'unit': resource.unit,
                'available_quantity': resource.available_quantity,
                'planned_quantity': float(planned_qty or 0),
                'actual_quantity': float(actual_qty or 0),
                'planned_cost': float(planned_cost or 0),
                'actual_cost': float(actual_cost or 0),
                'utilization': (float(planned_qty or 0) / resource.available_quantity * 100) if resource.available_quantity > 0 else 0
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_project_resources: {str(e)}")
        return []

def get_project_attachments(project_id):
    """الحصول على مرفقات المشروع"""
    try:
        # هذا يفترض وجود جدول ProjectAttachments
        # إذا لم يكن موجوداً، يمكن استخدام ActivityDocument المرتبط بالمشروع
        
        # جلب المستندات من الأنشطة
        activity_docs = db.session.query(
            ActivityDocument
        ).join(Activity, ActivityDocument.activity_id == Activity.id)\
         .filter(Activity.project_id == project_id)\
         .order_by(ActivityDocument.created_at.desc()).all()
        
        attachments = []
        for doc in activity_docs:
            attachments.append({
                'id': doc.id,
                'filename': doc.original_filename,
                'file_url': doc.file_url,
                'file_size': doc.file_size,
                'file_type': doc.file_type,
                'uploaded_by': doc.uploader.full_name if doc.uploader else None,
                'uploaded_at': doc.created_at.isoformat() if doc.created_at else None,
                'activity_id': doc.activity_id,
                'activity_name': doc.activity.activity_name if doc.activity else None,
                'source': 'activity'
            })
        
        return attachments
    except Exception as e:
        current_app.logger.error(f"Error in get_project_attachments: {str(e)}")
        return []

def get_project_notebook_entries(project_id):
    """الحصول على مدخلات دفتر المشروع"""
    try:
        # هذا يفترض وجود حقل notebook_content في Project
        project = Project.query.get(project_id)
        
        entries = []
        if project and project.notebook_entries:
            # إذا كان المحتوى JSON، قم بتحليله
            if isinstance(project.notebook_entries, str):
                try:
                    entries = json.loads(project.notebook_entries)
                except:
                    # إذا كان نصاً عادياً، اعتبره إدخال واحد
                    entries = [{
                        'id': 1,
                        'content': project.notebook_content,
                        'created_at': project.project.created_at.isoformat() if project.project.created_at else None,
                        'created_by': project.project.creator.full_name if project.project.creator else None
                    }]
        
        return entries
    except Exception as e:
        current_app.logger.error(f"Error in get_project_notebook_entries: {str(e)}")
        return []

def get_project_resource_codes(project_id):
    """الحصول على أكواد الموارد المختارة للمشروع"""
    try:
        project = Project.query.get(project_id)
        if project and project.resource_code_values:
            return project.resource_code_values
        return {}
    except Exception as e:
        current_app.logger.error(f"Error in get_project_resource_codes: {str(e)}")
        return {}

def get_project_activity_codes(project_id):
    """الحصول على أكواد الأنشطة المختارة للمشروع"""
    try:
        project = Project.query.get(project_id)
        if project and project.project.activity_code_values:
            return project.project.activity_code_values
        return {}
    except Exception as e:
        current_app.logger.error(f"Error in get_project_activity_codes: {str(e)}")
        return {}

# def calculate_project_resource_stats(project_id):
#     """حساب إحصائيات موارد المشروع"""
#     return {
#         'labor_count': 0,
#         'material_count': 0,
#         'equipment_count': 0,
#         'total_planned_cost': 0,
#         'total_actual_cost': 0
#     }
def calculate_project_resource_stats(project_id):
    """حساب إحصائيات موارد المشروع"""
    try:
        # إحصائيات الموارد حسب النوع
        stats = {
            'labor_count': 0,
            'material_count': 0,
            'equipment_count': 0,
            'non_labor_count': 0,
            'total_planned_cost': 0,
            'total_actual_cost': 0,
            'total_planned_quantity': 0,
            'total_actual_quantity': 0,
            'resources_by_type': {},
            'top_resources': []
        }
        
        # جلب موارد الأنشطة
        activity_resources = db.session.query(
            Resource.resource_type,
            func.count(Resource.id).label('resource_count'),
            func.sum(ActivityResource.planned_cost).label('total_planned'),
            func.sum(ActivityResource.actual_cost).label('total_actual'),
            func.sum(ActivityResource.planned_quantity).label('total_planned_qty'),
            func.sum(ActivityResource.actual_quantity).label('total_actual_qty')
        ).join(ActivityResource, Resource.id == ActivityResource.resource_id)\
         .join(Activity, ActivityResource.activity_id == Activity.id)\
         .filter(Activity.project_id == project_id)\
         .group_by(Resource.resource_type).all()
        
        for res_type, count, planned, actual, planned_qty, actual_qty in activity_resources:
            stats['resources_by_type'][res_type] = {
                'count': count,
                'planned_cost': float(planned or 0),
                'actual_cost': float(actual or 0),
                'planned_quantity': float(planned_qty or 0),
                'actual_quantity': float(actual_qty or 0)
            }
            
            if res_type == 'labor':
                stats['labor_count'] += count
            elif res_type == 'material':
                stats['material_count'] += count
            elif res_type == 'equipment':
                stats['equipment_count'] += count
            else:
                stats['non_labor_count'] += count
            
            stats['total_planned_cost'] += float(planned or 0)
            stats['total_actual_cost'] += float(actual or 0)
            stats['total_planned_quantity'] += float(planned_qty or 0)
            stats['total_actual_quantity'] += float(actual_qty or 0)
        
        # أهم 5 موارد من حيث التكلفة
        top_resources = db.session.query(
            Resource.name,
            Resource.resource_type,
            func.sum(ActivityResource.planned_cost).label('total_cost')
        ).join(ActivityResource, Resource.id == ActivityResource.resource_id)\
         .join(Activity, ActivityResource.activity_id == Activity.id)\
         .filter(Activity.project_id == project_id)\
         .group_by(Resource.id, Resource.name, Resource.resource_type)\
         .order_by(func.sum(ActivityResource.planned_cost).desc())\
         .limit(5).all()
        
        stats['top_resources'] = [{
            'name': r.name,
            'type': r.resource_type,
            'cost': float(r.total_cost or 0)
        } for r in top_resources]
        
        return stats
    except Exception as e:
        current_app.logger.error(f"Error in calculate_project_resource_stats: {str(e)}")
        return {
            'labor_count': 0,
            'material_count': 0,
            'equipment_count': 0,
            'non_labor_count': 0,
            'total_planned_cost': 0,
            'total_actual_cost': 0,
            'total_planned_quantity': 0,
            'total_actual_quantity': 0,
            'resources_by_type': {},
            'top_resources': []
        }
    
def get_project_risk_summary(project_id):
    """الحصول على ملخص مخاطر المشروع"""
    try:
        risks = ActivityRisk.query.join(Activity).filter(
            Activity.project_id == project_id
        ).all()
        
        summary = {
            'total_risks': len(risks),
            'by_level': {'high': 0, 'medium': 0, 'low': 0},
            'by_status': {'identified': 0, 'mitigated': 0, 'closed': 0},
            'top_risks': []
        }
        
        for risk in risks:
            # حسب المستوى
            if risk.risk_level in summary['by_level']:
                summary['by_level'][risk.risk_level] += 1
            
            # حسب الحالة
            if risk.status in summary['by_status']:
                summary['by_status'][risk.status] += 1
            
            # أهم المخاطر (high)
            if risk.risk_level == 'high' and risk.status != 'closed':
                summary['top_risks'].append({
                    'id': risk.id,
                    'title': risk.title,
                    'activity': risk.activity.activity_name if risk.activity else None,
                    'probability': risk.probability,
                    'impact': risk.impact
                })
        
        return summary
    except Exception as e:
        current_app.logger.error(f"Error in get_project_risk_summary: {str(e)}")
        return {}

def get_project_earned_value(project_id):
    """حساب القيمة المكتسبة للمشروع"""
    try:
        activities = Activity.query.filter_by(project_id=project_id).all()
        
        pv = 0  # Planned Value
        ev = 0  # Earned Value
        ac = 0  # Actual Cost
        
        for activity in activities:
            pv += activity.planned_value or 0
            ev += activity.earned_value or 0
            ac += activity.actual_cost or 0
        
        return {
            'planned_value': pv,
            'earned_value': ev,
            'actual_cost': ac,
            'spi': ev / pv if pv > 0 else 1,
            'cpi': ev / ac if ac > 0 else 1,
            'variance_cost': ev - ac,
            'variance_schedule': ev - pv
        }
    except Exception as e:
        current_app.logger.error(f"Error in get_project_earned_value: {str(e)}")
        return {}

def get_project_timeline_summary(project_id):
    """ملخص الجدول الزمني للمشروع"""
    try:
        project = Project.query.get(project_id)
        activities = Activity.query.filter_by(project_id=project_id).all()
        
        today = date.today()
        
        # الأنشطة المتأخرة
        delayed = [a for a in activities if a.status != 'completed' and 
                  a.planned_finish and a.planned_finish.date() < today]
        
        # الأنشطة على المسار الحرج
        critical = [a for a in activities if a.is_critical]
        
        # الأنشطة القادمة
        upcoming = [a for a in activities if a.status == 'not_started' and 
                   a.planned_start and a.planned_start.date() <= today + timedelta(days=7)]
        
        return {
            'planned_start': project.project.planned_start.isoformat() if project.project.planned_start else None,
            'planned_finish': project.project.planned_finish.isoformat() if project.project.planned_finish else None,
            'actual_start': project.project.actual_start.isoformat() if project.project.actual_start else None,
            'actual_finish': project.project.actual_finish.isoformat() if project.project.actual_finish else None,
            'total_duration': project.project.planned_duration,
            'remaining_days': project.project.remaining_days,
            'delayed_activities': len(delayed),
            'critical_activities': len(critical),
            'upcoming_activities': len(upcoming),
            'progress': project.project.progress_percentage
        }
    except Exception as e:
        current_app.logger.error(f"Error in get_project_timeline_summary: {str(e)}")
        return {}

@primavera_bp.route('/api/project/<int:project_id>/notebook/entries', methods=['GET'])
@login_required
def api_get_notebook_entries(project_id):
    """جلب جميع مدخلات دفتر الملاحظات"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    topic = request.args.get('topic')
    
    query = NotebookEntry.query.filter_by(project_id=project_id)
    if topic:
        query = query.filter_by(topic=topic)
    
    entries = query.order_by(NotebookEntry.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'entries': [{
            'id': e.id,
            'topic': e.topic,
            'content': e.content,
            'author': e.author.full_name if e.author else None,
            'created_at': e.created_at.isoformat(),
            'preview': e.content[:100] + '...' if len(e.content) > 100 else e.content
        } for e in entries]
    })


@primavera_bp.route('/api/project/<int:project_id>/notebook/entry', methods=['POST'])
@login_required
def api_create_notebook_entry(project_id):
    """إنشاء مدخلة جديدة في دفتر الملاحظات"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        entry = NotebookEntry(
            project_id=project_id,
            topic=data.get('topic', 'General'),
            content=data['content'],
            author_id=current_user.id
        )
        
        db.session.add(entry)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'entry': {
                'id': entry.id,
                'topic': entry.topic,
                'content': entry.content,
                'created_at': entry.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/notebook/entry/<int:entry_id>', methods=['GET'])
@login_required
def api_get_notebook_entry(entry_id):
    """API لجلب تفاصيل إدخال معين"""
    entry = NotebookEntry.query.get_or_404(entry_id)
    
    if not check_project_access(entry.project_id):
        return jsonify({'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'entry': entry.to_dict()
    })

@primavera_bp.route('/api/notebook/entry/<int:entry_id>/update', methods=['POST'])
@login_required
def api_update_notebook_entry(entry_id):
    """API لتحديث إدخال"""
    entry = NotebookEntry.query.get_or_404(entry_id)
    
    if not check_project_access(entry.project_id):
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # تحديث الحقول الأساسية
        if 'status' in data:
            entry.status = data['status']
            if data['status'] == 'closed':
                entry.closed_at = datetime.utcnow()
        
        if 'content' in data:
            entry.content = data['content']
        
        if 'assigned_to' in data:
            entry.assigned_to = data['assigned_to']
        
        if 'priority' in data:
            entry.priority = data['priority']
        
        # للأسئلة
        if entry.entry_type == 'question' and 'answer' in data:
            entry.answer = data['answer']
            entry.answered_by = current_user.id
            entry.answered_at = datetime.utcnow()
        
        # لعناصر العمل
        if entry.entry_type == 'action_item' and 'completed' in data and data['completed']:
            entry.status = 'closed'
            entry.completed_at = datetime.utcnow()
            entry.completion_notes = data.get('completion_notes')
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# @primavera_bp.route('/api/notebook/entry/<int:entry_id>/comment', methods=['POST'])
# @login_required
# def api_add_notebook_comment(entry_id):
#     """API لإضافة تعليق على إدخال"""
#     entry = NotebookEntry.query.get_or_404(entry_id)
    
#     if not check_project_access(entry.project_id):
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     data = request.get_json()
    
#     try:
#         comment = NotebookComment(
#             entry_id=entry_id,
#             user_id=current_user.id,
#             content=data.get('content'),
#             mentions=data.get('mentions', [])
#         )
        
#         db.session.add(comment)
#         db.session.commit()
        
#         # إشعارات للمشار إليهم
#         if comment.mentions:
#             for user_id in comment.mentions:
#                 NotificationService.mention_notification(
#                     user_id=user_id,
#                     mentioned_by=current_user.id,
#                     project_id=entry.project_id,
#                     entry_id=entry_id,
#                     comment_id=comment.id
#                 )
        
#         return jsonify({
#             'success': True,
#             'comment': {
#                 'id': comment.id,
#                 'content': comment.content,
#                 'user': current_user.full_name,
#                 'created_at': comment.created_at.isoformat()
#             }
#         })
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500

@primavera_bp.route('/api/notebook/entry/<int:entry_id>/delete', methods=['POST'])
@login_required
def api_delete_notebook_entry(entry_id):
    """API لحذف إدخال"""
    entry = NotebookEntry.query.get_or_404(entry_id)
    
    if not check_project_access(entry.project_id):
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(entry)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500 
# ============================================
# دوال مساعدة للملاحظات (Notebook Helpers)
# ============================================

def get_project_notebook_entries(project_id, entry_type=None, status=None):
    """
    الحصول على مدخلات دفتر الملاحظات للمشروع مع إمكانية التصفية
    """
    try:
        query = NotebookEntry.query.filter_by(project_id=project_id)
        
        if entry_type:
            if isinstance(entry_type, list):
                query = query.filter(NotebookEntry.entry_type.in_(entry_type))
            else:
                query = query.filter_by(entry_type=entry_type)
        
        if status:
            if isinstance(status, list):
                query = query.filter(NotebookEntry.status.in_(status))
            else:
                query = query.filter_by(status=status)
        
        entries = query.order_by(NotebookEntry.created_at.desc()).all()
        
        return [entry.to_dict() for entry in entries]
    
    except Exception as e:
        current_app.logger.error(f"Error in get_project_notebook_entries: {str(e)}")
        return []

def get_notebook_entry_stats(project_id):
    """
    إحصائيات مدخلات دفتر الملاحظات
    """
    try:
        entries = NotebookEntry.query.filter_by(project_id=project_id).all()
        
        stats = {
            'total': len(entries),
            'by_type': {},
            'by_status': {},
            'by_priority': {},
            'open_count': 0,
            'closed_count': 0,
            'recent_count': 0,
            'with_attachments': 0
        }
        
        today = datetime.now().date()
        
        for entry in entries:
            # حسب النوع
            if entry.entry_type not in stats['by_type']:
                stats['by_type'][entry.entry_type] = 0
            stats['by_type'][entry.entry_type] += 1
            
            # حسب الحالة
            if entry.status not in stats['by_status']:
                stats['by_status'][entry.status] = 0
            stats['by_status'][entry.status] += 1
            
            # حسب الأولوية
            if entry.priority not in stats['by_priority']:
                stats['by_priority'][entry.priority] = 0
            stats['by_priority'][entry.priority] += 1
            
            # إحصائيات عامة
            if entry.status == 'open':
                stats['open_count'] += 1
            elif entry.status == 'closed':
                stats['closed_count'] += 1
            
            if entry.created_at.date() >= today - timedelta(days=7):
                stats['recent_count'] += 1
            
            if entry.attachments and len(entry.attachments) > 0:
                stats['with_attachments'] += 1
        
        return stats
    
    except Exception as e:
        current_app.logger.error(f"Error in get_notebook_entry_stats: {str(e)}")
        return {}
# ============================================
# صفحة تفاصيل النشاط مع التبويبات
# ============================================

@primavera_bp.route('/activity/<int:activity_id>')
@login_required
def activity_detail(activity_id):
    """عرض تفاصيل النشاط مع جميع التبويبات"""
    activity = check_activity_access(activity_id)
    if not activity:
        return redirect(url_for('company.projects'))
    
    org_id = current_user.org_id #activity.project.eps.org_id
    wbs_list = WBS.query.filter_by(project_id=activity.project_id).order_by(WBS.wbs_code).all()
    # بيانات التبويبات
    data = {
        'activity': activity,
        'wbs_list': wbs_list,
        'supervisors': User.query.filter(
            User.org_id == org_id,
            User.role.in_(['org_admin', 'project_manager', 'supervisor'])
        ).all(),
        'delegates': User.query.filter_by(org_id=org_id, role='delegate').all(),
        'roles': Role.query.filter_by(org_id=org_id).all(),
        'all_activities': Activity.query.filter_by(project_id=activity.project_id).all(),
        'activity_resources': get_activity_resources(activity.id),
        'all_resources': Resource.query.filter_by(org_id=org_id).all(),
        'predecessors': ActivityRelationship.query.filter_by(successor_id=activity.id).all(),
        'successors': ActivityRelationship.query.filter_by(predecessor_id=activity.id).all(),
        'activity_code_types': get_activity_code_types(org_id),
        'selected_activity_codes': get_activity_codes(activity.id),
        'activity_steps': get_activity_steps(activity.id),
        'activity_expenses': get_activity_expenses(activity.id),
        'activity_documents': get_activity_documents(activity.id),
        'activity_feedback': get_activity_feedback(activity.id),
        'activity_risks': get_activity_risks(activity.id),
        'notebook_entries': get_activity_notebook_entries(activity.id),
        'resource_stats': calculate_activity_resource_stats(activity.id),
        'expense_stats': calculate_activity_expense_stats(activity.id),
        'risk_stats': calculate_activity_risk_stats(activity.id),
        'steps_completed_percent': calculate_steps_progress(activity.id)
    }
    
    return render_template('primavera/activity_detail_tabs.html', **data)

@primavera_bp.route('/apis/activity/<int:activity_id>')
@login_required
def activity_detail22(activity_id):
    """عرض تفاصيل النشاط مع جميع التبويبات"""
    activity = check_activity_access(activity_id)
    if not activity:
        return redirect(url_for('company.projects'))
    
    org_id = current_user.org_id #activity.project.eps.org_id
    wbs_list = WBS.query.filter_by(project_id=activity.project_id).order_by(WBS.wbs_code).all()
    # بيانات التبويبات
    data = {
        'activity': activity,
        'wbs_list': wbs_list,
        'supervisors': User.query.filter(
            User.org_id == org_id,
            User.role.in_(['org_admin', 'project_manager', 'supervisor'])
        ).all(),
        'delegates': User.query.filter_by(org_id=org_id, role='delegate').all(),
        'roles': Role.query.filter_by(org_id=org_id).all(),
        'all_activities': Activity.query.filter_by(project_id=activity.project_id).all(),
        'activity_resources': get_activity_resources(activity.id),
        'all_resources': Resource.query.filter_by(org_id=org_id).all(),
        'predecessors': ActivityRelationship.query.filter_by(successor_id=activity.id).all(),
        'successors': ActivityRelationship.query.filter_by(predecessor_id=activity.id).all(),
        'activity_code_types': get_activity_code_types(org_id),
        'selected_activity_codes': get_activity_codes(activity.id),
        'activity_steps': get_activity_steps(activity.id),
        'activity_expenses': get_activity_expenses(activity.id),
        'activity_documents': get_activity_documents(activity.id),
        'activity_feedback': get_activity_feedback(activity.id),
        'activity_risks': get_activity_risks(activity.id),
        'notebook_entries': get_activity_notebook_entries(activity.id),
        'resource_stats': calculate_activity_resource_stats(activity.id),
        'expense_stats': calculate_activity_expense_stats(activity.id),
        'risk_stats': calculate_activity_risk_stats(activity.id),
        'steps_completed_percent': calculate_steps_progress(activity.id)
    }
    
    return render_template('primavera/activity_detail22.html', **data)
# دوال مساعدة لجلب بيانات النشاط
def get_activity_resources(activity_id):
    """الحصول على موارد النشاط"""
    try:
        resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
        
        result = []
        for ar in resources:
            if ar.resource:
                result.append({
                    'id': ar.id,
                    'resource_id': ar.resource.id,
                    'resource_code': ar.resource.resource_id,
                    'name': ar.resource.name,
                    'type': ar.resource.resource_type,
                    'unit': ar.resource.unit,
                    'planned_quantity': ar.planned_quantity,
                    'actual_quantity': ar.actual_quantity,
                    'planned_cost': ar.planned_cost,
                    'actual_cost': ar.actual_cost,
                    'cost_per_unit': ar.resource.cost_per_unit,
                    'currency': ar.resource.currency,
                    'allocated': ar.allocated
                })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_resources: {str(e)}")
        return []

def get_activity_codes(activity_id):
    """الحصول على أكواد النشاط"""
    try:
        activity = Activity.query.get(activity_id)
        if activity and activity.activity_code_values:
            return activity.activity_code_values
        return {}
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_codes: {str(e)}")
        return {}

def get_activity_steps(activity_id):
    """الحصول على خطوات النشاط"""
    try:
        steps = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.step_order).all()
        
        result = []
        for step in steps:
            result.append({
                'id': step.id,
                'order': step.step_order,
                'title': step.title,
                'description': step.description,
                'is_completed': step.is_completed,
                'completed_at': step.completed_at.isoformat() if step.completed_at else None,
                'completed_by': step.completer.full_name if step.completer else None,
                'completed_by_id': step.completed_by
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_steps: {str(e)}")
        return []

def get_activity_expenses(activity_id):
    """الحصول على مصروفات النشاط"""
    try:
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).order_by(ActivityExpense.expense_date.desc()).all()
        
        result = []
        for exp in expenses:
            result.append({
                'id': exp.id,
                'date': exp.expense_date.isoformat() if exp.expense_date else None,
                'category': exp.category,
                'description': exp.description,
                'amount': exp.amount,
                'currency': exp.currency,
                'is_approved': exp.is_approved,
                'approved_by': exp.approver.full_name if exp.approver else None,
                'approved_at': exp.approved_at.isoformat() if exp.approved_at else None,
                'receipt_url': exp.receipt_url,
                'created_by': exp.creator.full_name if exp.creator else None,
                'created_at': exp.created_at.isoformat() if exp.created_at else None
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_expenses: {str(e)}")
        return []

def get_activity_documents(activity_id):
    """الحصول على مستندات النشاط"""
    try:
        documents = ActivityDocument.query.filter_by(activity_id=activity_id).order_by(ActivityDocument.created_at.desc()).all()
        
        result = []
        for doc in documents:
            result.append({
                'id': doc.id,
                'filename': doc.original_filename,
                'file_url': doc.file_url,
                'file_size': doc.file_size,
                'file_type': doc.file_type,
                'uploaded_by': doc.uploader.full_name if doc.uploader else None,
                'uploaded_at': doc.created_at.isoformat() if doc.created_at else None
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_documents: {str(e)}")
        return []

def get_activity_feedback(activity_id):
    """الحصول على تعليقات النشاط"""
    try:
        feedback = ActivityFeedback.query.filter_by(activity_id=activity_id).order_by(ActivityFeedback.created_at.desc()).all()
        
        result = []
        for fb in feedback:
            result.append({
                'id': fb.id,
                'content': fb.content,
                'user_id': fb.user_id,
                'user_role':fb.user.role,
                'user_name': fb.user.full_name if fb.user else None,
                'user_image': fb.user.profile_image if fb.user else None,
                'attachment_url': fb.attachment_url,
                'created_at': fb.created_at.isoformat() if fb.created_at else None
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_feedback: {str(e)}")
        return []

def get_activity_risks(activity_id):
    """الحصول على مخاطر النشاط"""
    try:
        risks = ActivityRisk.query.filter_by(activity_id=activity_id).all()
        
        result = []
        for risk in risks:
            result.append({
                'id': risk.id,
                'title': risk.title,
                'description': risk.description,
                'risk_level': risk.risk_level,
                'probability': risk.probability,
                'impact': risk.impact,
                'mitigation_plan': risk.mitigation_plan,
                'contingency_plan': risk.contingency_plan,
                'status': risk.status,
                'created_by': risk.creator.full_name if risk.creator else None,
                'created_at': risk.created_at.isoformat() if risk.created_at else None,
                'risk_score': (risk.probability or 50) * impact_value(risk.impact) / 100
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_risks: {str(e)}")
        return []

def get_activity_notebook_entries(activity_id):
    """الحصول على مدخلات دفتر النشاط"""
    try:
        # هذا يفترض وجود حقل notebook_content في Activitys
        activity = Activity.query.get(activity_id)
        
        entries = []
        if activity and hasattr(activity, 'notebook_content') and activity.notebook_content:
            if isinstance(activity.notebook_content, str):
                try:
                    entries = json.loads(activity.notebook_content)
                except:
                    entries = [{
                        'id': 1,
                        'content': activity.notebook_content,
                        'created_at': activity.created_at.isoformat() if activity.created_at else None,
                        'created_by': activity.creator.full_name if activity.creator else None
                    }]
        
        return entries
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_notebook_entries: {str(e)}")
        return []

def calculate_activity_resource_stats(activity_id):
    """حساب إحصائيات موارد النشاط"""
    try:
        resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
        
        stats = {
            'labor_count': 0,
            'material_count': 0,
            'equipment_count': 0,
            'total_planned_cost': 0,
            'total_actual_cost': 0,
            'total_planned_quantity': 0,
            'total_actual_quantity': 0,
            'by_type': {}
        }
        
        for ar in resources:
            if ar.resource:
                res_type = ar.resource.resource_type
                
                # تحديث العدادات
                if res_type == 'labor':
                    stats['labor_count'] += 1
                elif res_type == 'material':
                    stats['material_count'] += 1
                elif res_type == 'equipment':
                    stats['equipment_count'] += 1
                
                # تحديث حسب النوع
                if res_type not in stats['by_type']:
                    stats['by_type'][res_type] = {
                        'count': 0,
                        'planned_cost': 0,
                        'actual_cost': 0,
                        'planned_quantity': 0,
                        'actual_quantity': 0
                    }
                
                stats['by_type'][res_type]['count'] += 1
                stats['by_type'][res_type]['planned_cost'] += ar.planned_cost or 0
                stats['by_type'][res_type]['actual_cost'] += ar.actual_cost or 0
                stats['by_type'][res_type]['planned_quantity'] += ar.planned_quantity or 0
                stats['by_type'][res_type]['actual_quantity'] += ar.actual_quantity or 0
                
                # تحديث الإجماليات
                stats['total_planned_cost'] += ar.planned_cost or 0
                stats['total_actual_cost'] += ar.actual_cost or 0
                stats['total_planned_quantity'] += ar.planned_quantity or 0
                stats['total_actual_quantity'] += ar.actual_quantity or 0
        
        return stats
    except Exception as e:
        current_app.logger.error(f"Error in calculate_activity_resource_stats: {str(e)}")
        return {}

def calculate_activity_expense_stats(activity_id):
    """حساب إحصائيات مصروفات النشاط"""
    try:
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
        
        stats = {
            'total': sum(e.amount for e in expenses),
            'approved': sum(e.amount for e in expenses if e.is_approved),
            'pending': sum(e.amount for e in expenses if not e.is_approved),
            'count': len(expenses),
            'approved_count': len([e for e in expenses if e.is_approved]),
            'pending_count': len([e for e in expenses if not e.is_approved]),
            'by_category': {}
        }
        
        for exp in expenses:
            if exp.category not in stats['by_category']:
                stats['by_category'][exp.category] = {
                    'total': 0,
                    'count': 0
                }
            stats['by_category'][exp.category]['total'] += exp.amount
            stats['by_category'][exp.category]['count'] += 1
        
        return stats
    except Exception as e:
        current_app.logger.error(f"Error in calculate_activity_expense_stats: {str(e)}")
        return {}

def calculate_activity_risk_stats(activity_id):
    """حساب إحصائيات مخاطر النشاط"""
    try:
        risks = ActivityRisk.query.filter_by(activity_id=activity_id).all()
        
        stats = {
            'total': len(risks),
            'high_count': len([r for r in risks if r.risk_level == 'high']),
            'medium_count': len([r for r in risks if r.risk_level == 'medium']),
            'low_count': len([r for r in risks if r.risk_level == 'low']),
            'open_count': len([r for r in risks if r.status != 'closed']),
            'closed_count': len([r for r in risks if r.status == 'closed']),
            'by_status': {
                'identified': len([r for r in risks if r.status == 'identified']),
                'mitigated': len([r for r in risks if r.status == 'mitigated']),
                'closed': len([r for r in risks if r.status == 'closed'])
            }
        }
        
        # حساب متوسط المخاطر
        if risks:
            total_score = 0
            for risk in risks:
                if risk.status != 'closed':
                    prob = risk.probability or 50
                    imp = impact_value(risk.impact)
                    total_score += (prob * imp) / 100
            stats['average_score'] = total_score / len([r for r in risks if r.status != 'closed']) if [r for r in risks if r.status != 'closed'] else 0
        else:
            stats['average_score'] = 0
        
        return stats
    except Exception as e:
        current_app.logger.error(f"Error in calculate_activity_risk_stats: {str(e)}")
        return {}

def calculate_steps_progress(activity_id):
    """حساب تقدم الخطوات"""
    try:
        steps = ActivityStep.query.filter_by(activity_id=activity_id).all()
        
        if not steps:
            return 0
        
        completed = len([s for s in steps if s.is_completed])
        return (completed / len(steps)) * 100
    except Exception as e:
        current_app.logger.error(f"Error in calculate_steps_progress: {str(e)}")
        return 0

def get_activity_predecessors(activity_id):
    """الحصول على المهام السابقة للنشاط"""
    try:
        predecessors = ActivityRelationship.query.filter_by(successor_id=activity_id).all()
        
        result = []
        for rel in predecessors:
            pred_activity = Activity.query.get(rel.predecessor_id)
            if pred_activity:
                result.append({
                'id': rel.id,
                'predecessor': {
                    'id': pred_activity.id,
                    'activity_id': pred_activity.activity_id,
                    'activity_name': pred_activity.activity_name,
                    'status': pred_activity.status,
                    'is_critical': pred_activity.is_critical,
                    'primary_resource': get_primary_resource(pred_activity.id)
                },
                'relationship_type': rel.relationship_type,
                'lag_days': rel.lag_days,
                'lag_type': rel.lag_type,
                'is_critical': rel.is_critical,
                'is_driving': rel.is_driving
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_predecessors: {str(e)}")
        return []
def get_primary_resource(activity_id):
    """الحصول على المورد الرئيسي للنشاط"""
    resource = ActivityResource.query.filter_by(activity_id=activity_id).first()
    if resource and resource.resource:
        return {
            'id': resource.resource.id,
            'name': resource.resource.name,
            'type': resource.resource.resource_type
        }
    return None
def get_activity_successors(activity_id):
    """الحصول على المهام التالية للنشاط"""
    try:
        successors = ActivityRelationship.query.filter_by(predecessor_id=activity_id).all()
        
        result = []
        for rel in successors:
            succ_activity = Activity.query.get(rel.successor_id)
            if succ_activity:
                result.append({
                    'id': rel.id,
                    'successor': {
                        'id': succ_activity.id,
                        'activity_id': succ_activity.activity_id,
                        'activity_name': succ_activity.activity_name,
                        'status': succ_activity.status,
                        'is_critical': succ_activity.is_critical,
                        'primary_resource': get_primary_resource(succ_activity.id)
                    },
                    'relationship_type': rel.relationship_type,
                    'lag_days': rel.lag_days,
                    'lag_type': rel.lag_type,
                    'is_critical': rel.is_critical,
                    'is_driving': rel.is_driving
                })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_successors: {str(e)}")
        return []

def get_activity_udf_values(activity_id):
    """الحصول على قيم الحقول المخصصة للنشاط"""
    try:
        activity = Activity.query.get(activity_id)
        if not activity:
            return {}
        
        # جلب تعريفات UDF
        udf_defs = UDF.query.filter_by(
            org_id=activity.project.eps.org_id,
            udf_type='activity',
            is_active=True
        ).all()
        
        values = activity.udf_values or {}
        
        result = []
        for udf in udf_defs:
            result.append({
                'id': udf.id,
                'name': udf.udf_name,
                'label': udf.udf_label,
                'data_type': udf.data_type,
                'value': values.get(udf.udf_name),
                'default_value': udf.default_value,
                'list_values': udf.list_values,
                'is_required': udf.is_required
            })
        
        return result
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_udf_values: {str(e)}")
        return []

def get_next_step_order(activity_id):
    """الحصول على الترتيب التالي لخطوة جديدة"""
    try:
        last_step = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.step_order.desc()).first()
        return (last_step.step_order + 1) if last_step else 1
    except Exception as e:
        current_app.logger.error(f"Error in get_next_step_order: {str(e)}")
        return 1

def get_activity_timeline_data(activity_id):
    """الحصول على بيانات الجدول الزمني للنشاط"""
    try:
        activity = Activity.query.get(activity_id)
        if not activity:
            return {}
        
        today = date.today()
        
        return {
            'planned_start': activity.planned_start.isoformat() if activity.planned_start else None,
            'planned_finish': activity.planned_finish.isoformat() if activity.planned_finish else None,
            'actual_start': activity.actual_start.isoformat() if activity.actual_start else None,
            'actual_finish': activity.actual_finish.isoformat() if activity.actual_finish else None,
            'early_start': activity.early_start.isoformat() if activity.early_start else None,
            'early_finish': activity.early_finish.isoformat() if activity.early_finish else None,
            'late_start': activity.late_start.isoformat() if activity.late_start else None,
            'late_finish': activity.late_finish.isoformat() if activity.late_finish else None,
            'original_duration': activity.original_duration,
            'remaining_duration': activity.remaining_duration,
            'actual_duration': activity.actual_duration,
            'total_float': activity.total_float,
            'free_float': activity.free_float,
            'is_critical': activity.is_critical,
            'status': activity.status,
            'progress': activity.progress_percentage,
            'is_delayed': (activity.planned_finish and activity.planned_finish.date() < today) if activity.planned_finish and activity.status != 'completed' else False,
            'delay_days': (today - activity.planned_finish.date()).days if activity.planned_finish and activity.status != 'completed' and activity.planned_finish.date() < today else 0
        }
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_timeline_data: {str(e)}")
        return {}

def get_activity_performance_metrics(activity_id):
    """الحصول على مقاييس أداء النشاط"""
    try:
        activity = Activity.query.get(activity_id)
        if not activity:
            return {}
        
        # حساب مؤشرات الأداء
        planned_progress = 0
        if activity.planned_start and activity.planned_finish and activity.actual_start:
            total_duration = (activity.planned_finish - activity.planned_start).days
            elapsed = (datetime.now() - activity.actual_start).days
            if total_duration > 0:
                planned_progress = (elapsed / total_duration) * 100
        
        return {
            'progress': activity.progress_percentage,
            'planned_progress': planned_progress,
            'progress_variance': activity.progress_percentage - planned_progress,
            'efficiency': (activity.earned_value / activity.actual_cost) if activity.actual_cost and activity.earned_value else 1,
            'planned_value': activity.planned_value,
            'earned_value': activity.earned_value,
            'actual_cost': activity.actual_cost,
            'cost_variance': (activity.earned_value or 0) - (activity.actual_cost or 0),
            'schedule_variance': (activity.earned_value or 0) - (activity.planned_value or 0)
        }
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_performance_metrics: {str(e)}")
        return {}

def impact_value(impact_str):
    """تحويل نص التأثير إلى قيمة رقمية"""
    impact_map = {
        'very_low': 20,
        'low': 40,
        'medium': 60,
        'high': 80,
        'very_high': 100
    }
    return impact_map.get(impact_str, 60)

# ============================================
# دوال مساعدة إضافية للتقارير
# ============================================

def get_project_daily_progress(project_id, days=30):
    """الحصول على التقدم اليومي للمشروع"""
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # هذا يفترض وجود جدول لتتبع التقدم اليومي
        # يمكن إنشاؤه لاحقاً
        
        return []
    except Exception as e:
        current_app.logger.error(f"Error in get_project_daily_progress: {str(e)}")
        return []

def get_activity_cost_breakdown(activity_id):
    """تحليل تكاليف النشاط"""
    try:
        resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
        
        breakdown = {
            'labor': {'planned': 0, 'actual': 0},
            'material': {'planned': 0, 'actual': 0},
            'equipment': {'planned': 0, 'actual': 0},
            'other': {'planned': 0, 'actual': 0},
            'expenses': {'planned': 0, 'actual': 0}
        }
        
        # تكاليف الموارد
        for ar in resources:
            if ar.resource:
                res_type = ar.resource.resource_type
                if res_type in breakdown:
                    breakdown[res_type]['planned'] += ar.planned_cost or 0
                    breakdown[res_type]['actual'] += ar.actual_cost or 0
                else:
                    breakdown['other']['planned'] += ar.planned_cost or 0
                    breakdown['other']['actual'] += ar.actual_cost or 0
        
        # المصروفات المباشرة
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
        for exp in expenses:
            breakdown['expenses']['actual'] += exp.amount
        
        return breakdown
    except Exception as e:
        current_app.logger.error(f"Error in get_activity_cost_breakdown: {str(e)}")
        return {}

# ============================================
# API للبيانات (للواجهات الأمامية)
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/gantt-data')
@login_required
def api_gantt_data(project_id):
    """بيانات مخطط جانت"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    gantt_data = []
    for activity in activities:
        gantt_data.append({
            'id': activity.id,
            'activity_id': activity.activity_id,
            'name': activity.activity_name,
            'start': activity.planned_start.strftime('%Y-%m-%d') if activity.planned_start else None,
            'end': activity.planned_finish.strftime('%Y-%m-%d') if activity.planned_finish else None,
            'progress': activity.progress_percentage,
            'status': activity.status,
            'is_critical': activity.is_critical,
            'dependencies': [r.predecessor_id for r in activity.predecessors]
        })
    
    return jsonify({'success': True, 'tasks': gantt_data})

@primavera_bp.route('/api/project/<int:project_id>/resource-usage')
@login_required
def api_resource_usage(project_id):
    """بيانات استخدام الموارد"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    resources_data = []
    
    resources = Resource.query.filter_by(org_id=project.eps.org_id).all()
    for resource in resources:
        assignments = ActivityResource.query.filter_by(resource_id=resource.id)\
            .join(Activity).filter(Activity.project_id == project_id).all()
        
        if assignments:
            total_assigned = sum(a.planned_quantity for a in assignments)
            resources_data.append({
                'name': resource.name,
                'type': resource.resource_type,
                'assigned': total_assigned,
                'available': resource.available_quantity,
                'utilization': (total_assigned / resource.available_quantity * 100) if resource.available_quantity > 0 else 0
            })
    
    return jsonify({'success': True, 'resources': resources_data})

@primavera_bp.route('/api/project/<int:project_id>/activities')
@login_required
def api_project_activities(project_id):
    """API لجلب أنشطة المشروع بتنسيق JSON"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    return jsonify({
        'success': True,
        'activities': [activity.to_dict() for activity in activities]
    })

@primavera_bp.route('/api/project/<int:project_id>/relationships')
@login_required
def api_project_relationships(project_id):
    """API لجلب علاقات المشروع بتنسيق JSON"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    relationships = ActivityRelationship.query.filter_by(project_id=project_id).all()
    
    return jsonify({
        'success': True,
        'relationships': [rel.to_dict() for rel in relationships]
    })

@primavera_bp.route('/api/activity/<int:activity_id>')
@login_required
def api_activity_detail(activity_id):
    """API لجلب تفاصيل نشاط معين"""
    activity = Activity.query.get_or_404(activity_id)
    
    # التحقق من الصلاحية
    if not check_project_access(activity.project_id):
        return jsonify({'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'activity': activity.to_dict()
    })


# ============================================
# API لحفظ بيانات المشروع
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/update', methods=['POST'])
@login_required
def api_update_project(project_id):
    """تحديث بيانات المشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # تحديث General Tab
        if 'general' in data:
            update_project_general(project, data['general'])
        
        # تحديث Dates Tab
        if 'dates' in data:
            update_project_dates(project, data['dates'])
        
        # تحديث Settings Tab
        if 'settings' in data:
            update_project_settings(project, data['settings'])
        
        # تحديث Defaults Tab
        if 'defaults' in data:
            update_project_defaults(project, data['defaults'])
        
        # تحديث Calculations Tab
        if 'calculations' in data:
            update_project_calculations(project, data['calculations'])
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def update_project_general(project, data):
    """تحديث المعلومات العامة للمشروع"""
    project.name = data.get('name', project.name)
    project.description = data.get('description', project.description)
    project.project.site_name = data.get('location', project.project.site_name)
    project.project.city = data.get('city', project.city)
    # ... تحديث باقي الحقول

def update_project_dates(project, data):
    """تحديث تواريخ المشروع"""
    # تحديث التواريخ المخططة
    if data.get('planned_start'):
        project.project.planned_start = datetime.strptime(data['planned_start'], '%Y-%m-%d')
    if data.get('planned_finish'):
        project.project.planned_finish = datetime.strptime(data['planned_finish'], '%Y-%m-%d')
    
    # تحديث التواريخ الفعلية
    if data.get('actual_start'):
        project.project.actual_start = datetime.strptime(data['actual_start'], '%Y-%m-%d')
    if data.get('actual_finish'):
        project.project.actual_finish = datetime.strptime(data['actual_finish'], '%Y-%m-%d')
    
    # تحديث التقدم
    if data.get('percent_complete'):
        project.project.progress_percentage = float(data['percent_complete'])

def update_project_settings(project, data):
    """تحديث إعدادات المشروع"""
    if data.get('calendar_id'):
        project.calendar_id = int(data['calendar_id'])
    if data.get('eps_id'):
        project.eps_id = int(data['eps_id'])
    if data.get('obs_id'):
        project.obs_id = int(data['obs_id'])

def update_project_defaults(project, data):
    """تحديث الافتراضيات"""
    pass

def update_project_calculations(project, data):
    """تحديث الحسابات"""
    if data.get('total_planned_cost'):
        project.project.total_planned_cost = float(data['total_planned_cost'])
    if data.get('total_actual_cost'):
        project.project.total_actual_cost = float(data['total_actual_cost'])

# ============================================
# API لحفظ بيانات النشاط
# ============================================

# app/routes/primavera_routes.py

@primavera_bp.route('/api/activity/<int:activity_id>/update', methods=['POST'])
@login_required
def api_update_activity(activity_id):
    """تحديث بيانات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # تحديث General Tab
        if 'general' in data:
            update_activity_general(activity, data['general'])
        
        # تحديث Status Tab (إذا وجد)
        if 'status' in data:
            update_activity_status(activity, data['status'])
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم حفظ التغييرات بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


def update_activity_general(activity, data):
    """تحديث المعلومات العامة للنشاط"""
    # المعلومات الأساسية
    if 'name' in data:
        activity.activity_name = data['name']
    
    if 'description' in data:
        activity.description = data['description']
    
    if 'instructions' in data:
        activity.instructions = data['instructions']
    
    # نوع النشاط
    if 'activity_type' in data:
        activity.activity_type = data['activity_type']
    
    # نوع المدة
    if 'duration_type' in data:
        activity.duration_type = data['duration_type']
    
    # نوع نسبة الإنجاز
    if 'percent_complete_type' in data:
        activity.percent_complete_type = data['percent_complete_type']
    
    # التقويم
    if 'calendar_id' in data:
        activity.calendar_id = int(data['calendar_id']) if data['calendar_id'] else None
    
    # WBS
    if 'wbs_id' in data:
        activity.wbs_id = int(data['wbs_id']) if data['wbs_id'] else None
    
    # المسؤول
    if 'responsible_id' in data:
        activity.responsible_id = int(data['responsible_id']) if data['responsible_id'] else None
    
    # المورد الرئيسي
    if 'primary_resource_id' in data:
        activity.primary_resource_id = int(data['primary_resource_id']) if data['primary_resource_id'] else None
    
    # المدة
    if 'original_duration' in data:
        activity.original_duration = float(data['original_duration'])
        # ✅ تحديث المؤشرات
        
    
    if 'remaining_duration' in data:
        activity.remaining_duration = float(data['remaining_duration'])
        # تحديث المدة الفعلية تلقائياً
        activity.actual_duration = activity.original_duration - activity.remaining_duration
        # ✅ تحديث المؤشرات
        
    # نسبة الإنجاز
    if 'progress_percentage' in data:
        activity.progress_percentage = float(data['progress_percentage'])
        # تحديث المدة الفعلية بناءً على النسبة
        if activity.original_duration > 0:
            activity.actual_duration = (activity.progress_percentage / 100) * activity.original_duration
            activity.remaining_duration = activity.original_duration - activity.actual_duration
        # ✅ تحديث المؤشرات
        
    # الحالة
    if 'status' in data:
        activity.status = data['status']
    
    # جودة الإكمال
    if 'completion_quality' in data:
        activity.completion_quality = data['completion_quality']
    
    # التواريخ
    if 'planned_start' in data and data['planned_start']:
        activity.planned_start = datetime.strptime(data['planned_start'], '%Y-%m-%d')
    
    if 'planned_finish' in data and data['planned_finish']:
        activity.planned_finish = datetime.strptime(data['planned_finish'], '%Y-%m-%d')
    
    if 'actual_start' in data and data['actual_start']:
        activity.actual_start = datetime.strptime(data['actual_start'], '%Y-%m-%d')
    
    if 'actual_finish' in data and data['actual_finish']:
        activity.actual_finish = datetime.strptime(data['actual_finish'], '%Y-%m-%d')
    
    # الخيارات المتقدمة
    if 'is_critical' in data:
        activity.is_criticall = data['is_critical']



def update_activity_status(activity, data):
    """تحديث حالة النشاط"""
    if 'percent_complete' in data:
        activity.progress_percentage = float(data['percent_complete'])
    
    if 'status' in data:
        activity.status = data['status']
    
    if 'completion_quality' in data:
        activity.completion_quality = data['completion_quality']

@primavera_bp.route('/api/activity/<int:activity_id>/status', methods=['POST'])
@login_required
def api_update_activity_status(activity_id):
    """تحديث حالة النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # تحديث المدد
        if 'original_duration' in data:
            activity.original_duration = float(data['original_duration'])
        if 'actual_duration' in data:
            activity.actual_duration = float(data['actual_duration'])
        if 'remaining_duration' in data:
            activity.remaining_duration = float(data['remaining_duration'])
        
        # تحديث التواريخ
        if 'started_date' in data and data['started_date']:
            activity.actual_start = datetime.strptime(data['started_date'], '%Y-%m-%d')
        if 'finished_date' in data and data['finished_date']:
            activity.actual_finish = datetime.strptime(data['finished_date'], '%Y-%m-%d')
        if 'suspend_date' in data and data['suspend_date']:
            activity.suspend_date = datetime.strptime(data['suspend_date'], '%Y-%m-%d')
        if 'resume_date' in data and data['resume_date']:
            activity.resume_date = datetime.strptime(data['resume_date'], '%Y-%m-%d')
        if 'expected_finish' in data and data['expected_finish']:
            activity.expected_finish = datetime.strptime(data['expected_finish'], '%Y-%m-%d')
        
        # تحديث وحدات العمل
        if 'budgeted_units' in data:
            activity.budgeted_units = float(data['budgeted_units'])
        if 'actual_units' in data:
            activity.actual_units = float(data['actual_units'])
            # تحديث الوحدات المتبقية
            activity.remaining_units = max(0, (activity.budgeted_units or 0) - activity.actual_units)
            activity.at_complete_units = activity.actual_units + activity.remaining_units
        
        # تحديث القيود
        if 'primary_constraint' in data:
            activity.primary_constraint = data['primary_constraint']
        if 'primary_constraint_date' in data and data['primary_constraint_date']:
            activity.primary_constraint_date = datetime.strptime(data['primary_constraint_date'], '%Y-%m-%d')
        if 'secondary_constraint' in data:
            activity.secondary_constraint = data['secondary_constraint']
        if 'secondary_constraint_date' in data and data['secondary_constraint_date']:
            activity.secondary_constraint_date = datetime.strptime(data['secondary_constraint_date'], '%Y-%m-%d')
        
        # تحديث المدة عند الإكمال
        activity.at_complete_duration = (activity.actual_duration or 0) + (activity.remaining_duration or 0)
        
        # تحديث نسبة التقدم
        if activity.original_duration and activity.original_duration > 0:
            activity.progress_percentage = (activity.actual_duration / activity.original_duration) * 100
        else:
            activity.progress_percentage = 0
        
        # تحديث الحالة
        if activity.actual_duration and activity.actual_duration > 0:
            if activity.remaining_duration == 0:
                activity.status = 'completed'
            else:
                activity.status = 'in_progress'
        else:
            activity.status = 'not_started'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'activity': {
                'id': activity.id,
                'status': activity.status,
                'progress': activity.progress_percentage,
                'remaining_duration': activity.remaining_duration,
                'at_complete_duration': activity.at_complete_duration
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
# ============================================
# API لإدارة موارد النشاط
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/resource', methods=['POST'])
@login_required
def api_add_activity_resource(activity_id):
    """إضافة مورد للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        resource = ActivityResource(
            activity_id=activity_id,
            resource_id=data.get('resource_id'),
            planned_quantity=float(data.get('quantity', 1)),
            planned_cost=float(data.get('total_cost', 0))
        )
        
        db.session.add(resource)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@primavera_bp.route('/api/activity-resource/<int:resource_id>/delete', methods=['POST'])
@login_required
def api_delete_activity_resource(resource_id):
    """حذف مورد من النشاط"""
    resource = ActivityResource.query.get_or_404(resource_id)
    
    try:
        db.session.delete(resource)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# API لإدارة العلاقات (Predecessors/Successors)
# ============================================

# @primavera_bp.route('/api/activity/<int:activity_id>/predecessor', methods=['POST'])
# @login_required
# def api_add_predecessor(activity_id):
#     """إضافة مهمة سابقة"""
#     activity = check_activity_access(activity_id)
#     if not activity:
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     data = request.get_json()
    
#     try:
#         # التحقق من عدم وجود علاقة دائرية
#         if would_create_circular_relationship(data['predecessor_id'], activity_id):
#             return jsonify({'error': 'العلاقة ستؤدي إلى دورة لا نهائية'}), 400
        
#         relationship = ActivityRelationship(
#             project_id=activity.project_id,
#             predecessor_id=data['predecessor_id'],
#             successor_id=activity_id,
#             relationship_type=data.get('relationship_type', 'FS'),
#             lag_days=float(data.get('lag', 0))
#         )
        
#         db.session.add(relationship)
#         db.session.commit()
        
#         return jsonify({'success': True})
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500

@primavera_bp.route('/api/activity/<int:activity_id>/successor', methods=['POST'])
@login_required
def api_add_successor(activity_id):
    """إضافة علاقة لاحقة"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم وجود علاقة دائرية
        if would_create_circular_relationship(activity_id, data['successor_id']):
            return jsonify({'success': False, 'error': 'Circular relationship detected'}), 400
        
        # التحقق من عدم وجود علاقة مكررة
        existing = ActivityRelationship.query.filter_by(
            project_id=activity.project_id,
            predecessor_id=activity_id,
            successor_id=data['successor_id']
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Relationship already exists'}), 400
        
        relationship = ActivityRelationship(
            project_id=activity.project_id,
            predecessor_id=activity_id,
            successor_id=data['successor_id'],
            relationship_type=data.get('relationship_type', 'FS'),
            lag_days=float(data.get('lag', 0)),
            lag_type=data.get('lag_type', 'days')
        )
        
        db.session.add(relationship)
        db.session.commit()
       
        
        return jsonify({'success': True, 'relationship_id': relationship.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# @primavera_bp.route('/api/relationship/<int:rel_id>/delete', methods=['POST'])
# @login_required
# def api_delete_relationship(rel_id):
#     """حذف علاقة"""
#     relationship = ActivityRelationship.query.get_or_404(rel_id)
    
#     try:
#         db.session.delete(relationship)
#         db.session.commit()
#         return jsonify({'success': True})
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500

def would_create_circular_relationship(pred_id, succ_id, visited=None):
    """التحقق من عدم إنشاء علاقة دائرية"""
    if visited is None:
        visited = set()
    
    if succ_id in visited:
        return True
    
    visited.add(succ_id)
    
    relationships = ActivityRelationship.query.filter_by(predecessor_id=succ_id).all()
    
    for rel in relationships:
        if rel.successor_id == pred_id:
            return True
        if would_create_circular_relationship(pred_id, rel.successor_id, visited):
            return True
    
    return False



# ============================================
# API لرفع الملفات
# ============================================

@primavera_bp.route('/api/upload-document', methods=['POST'])
@login_required
def api_upload_document():
    """رفع مستند"""
    if 'file' not in request.files:
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    file = request.files['file']
    activity_id = request.form.get('activity_id')
    
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    # حفظ الملف
    filename = secure_filename(file.filename)
    upload_folder = os.path.join('static', 'uploads', 'activity_documents')
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)
    
    # TODO: حفظ معلومات الملف في قاعدة البيانات
    
    return jsonify({
        'success': True,
        'filename': filename,
        'url': url_for('static', filename=f'uploads/activity_documents/{filename}')
    })

@primavera_bp.route('/api/upload-feedback-attachment', methods=['POST'])
@login_required
def api_upload_feedback_attachment():
    """رفع مرفق لتعليق"""
    # مشابه للدالة السابقة
    return jsonify({'success': True})

# ============================================
# API لجلب البيانات للواجهات
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/resources')
@login_required
def api_project_resources(project_id):
    """API لجلب موارد المشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    resources = ActivityResource.query.join(Activity).filter(
        Activity.project_id == project_id
    ).all()
    
    return jsonify({
        'success': True,
        'resources': [{
            'id': r.id,
            'name': r.resource.name if r.resource else '',
            'type': r.resource.resource_type if r.resource else '',
            'planned_quantity': r.planned_quantity,
            'actual_quantity': r.actual_quantity,
            'planned_cost': r.planned_cost,
            'actual_cost': r.actual_cost
        } for r in resources]
    })

@primavera_bp.route('/api/activity/<int:activity_id>/critical-info')
@login_required
def api_activity_critical_info(activity_id):
    """API لجلب معلومات المسار الحرج للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'is_critical': activity.is_critical,
        'total_float': activity.total_float,
        'free_float': activity.free_float,
        'early_start': activity.early_start.strftime('%Y-%m-%d') if activity.early_start else None,
        'early_finish': activity.early_finish.strftime('%Y-%m-%d') if activity.early_finish else None,
        'late_start': activity.late_start.strftime('%Y-%m-%d') if activity.late_start else None,
        'late_finish': activity.late_finish.strftime('%Y-%m-%d') if activity.late_finish else None
    })

# ============================================
# API لتشغيل الجدولة وحساب المسار الحرج
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/schedule', methods=['POST'])
@login_required
def api_schedule_project(project_id):
    """تشغيل الجدولة للمشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    engine = PrimaveraEngine(project)
    result = engine.run_schedule()
    
    return jsonify({
        'success': True,
        'result': result
    })

# ============================================
# API لإنشاء خط الأساس
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/baseline', methods=['POST'])
@login_required
def api_create_baseline(project_id):
    """إنشاء خط أساس جديد"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        baseline = Baseline(
            project_id=project_id,
            name=data.get('name', f'Baseline {datetime.now().strftime("%Y-%m-%d")}'),
            version=Baseline.query.filter_by(project_id=project_id).count() + 1,
            created_by=current_user.id,
            activities_snapshot=get_activities_snapshot(project_id)
        )
        
        db.session.add(baseline)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'baseline_id': baseline.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def get_activities_snapshot(project_id):
    """الحصول على snapshot للأنشطة"""
    activities = Activity.query.filter_by(project_id=project_id).all()
    return [{
        'id': a.id,
        'activity_id': a.activity_id,
        'name': a.activity_name,
        'planned_start': a.planned_start.isoformat() if a.planned_start else None,
        'planned_finish': a.planned_finish.isoformat() if a.planned_finish else None,
        'duration': a.original_duration
    } for a in activities]

# ============================================
# صفحة قائمة الأنشطة للمشروع
# ============================================

# @primavera_bp.route('/project/<int:project_id>/activities')
# @login_required
# def project_activities(project_id):
#     """عرض قائمة الأنشطة للمشروع"""
#     project = check_project_access(project_id)
#     if not project:
#         return redirect(url_for('company.projects'))
    
#     activities = Activity.query.filter_by(project_id=project_id).order_by(Activity.activity_id).all()
#     now=datetime.now()
#     return render_template('primavera/activities_list.html',
#                          project=project,now=now,
#                          activities=activities)

# ============================================
# إنشاء نشاط جديد
# ============================================

@primavera_bp.route('/project/<int:project_id>/activity/create', methods=['GET', 'POST'])
@login_required
def create_activity(project_id):
    """إنشاء نشاط جديد"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('company.projects'))
    
    if request.method == 'POST':
        try:
            # إنشاء activity_id تلقائي
            last_activity = Activity.query.filter_by(project_id=project_id).order_by(Activity.id.desc()).first()
            if last_activity:
                last_num = int(last_activity.activity_id[1:]) if last_activity.activity_id[0] == 'A' else 1000
                activity_id = f"A{last_num + 1}"
            else:
                activity_id = "A1000"
            
            activity = Activity(
                project_id=project_id,
                wbs_id=request.form.get('wbs_id') or None,
                calendar_id=request.form.get('calendar_id') or None,
                activity_id=activity_id,
                activity_code=request.form.get('activity_code'),
                activity_name=request.form.get('activity_name'),
                description=request.form.get('description'),
                activity_type=request.form.get('activity_type', 'task_dependent'),
                original_duration=float(request.form.get('original_duration', 1)),
                remaining_duration=float(request.form.get('original_duration', 1)),
                planned_start=datetime.strptime(request.form.get('planned_start'), '%Y-%m-%d') if request.form.get('planned_start') else None,
                planned_finish=datetime.strptime(request.form.get('planned_finish'), '%Y-%m-%d') if request.form.get('planned_finish') else None,
                weight=float(request.form.get('weight', 1)),
                priority=int(request.form.get('priority', 3)),
                responsible_id=request.form.get('responsible_id') or None,
                supervisor_id=request.form.get('supervisor_id') or None,
                delegate_id=request.form.get('delegate_id') or None
            )
            
            db.session.add(activity)
            db.session.commit()
            
            flash('تم إنشاء النشاط بنجاح', 'success')
            return redirect(url_for('primavera.activity_detail', activity_id=activity.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # بيانات النموذج
    wbs_list = WBS.query.filter_by(project_id=project_id).all()
    calendars = Calendar.query.filter_by(org_id=project.eps.org_id).all()
    supervisors = User.query.filter(
        User.org_id == project.eps.org_id,
        User.role.in_(['org_admin', 'project_manager', 'supervisor'])
    ).all()
    delegates = User.query.filter_by(org_id=project.eps.org_id, role='delegate').all()
    
    return render_template('primavera/activity_create.html',
                         project=project,
                         wbs_list=wbs_list,
                         calendars=calendars,
                         supervisors=supervisors,
                         delegates=delegates)

# ============================================
# حذف نشاط
# ============================================

@primavera_bp.route('/activity/<int:activity_id>/delete', methods=['POST'])
@login_required
def delete_activity(activity_id):
    """حذف نشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # حذف العلاقات المرتبطة
        ActivityRelationship.query.filter(
            or_(
                ActivityRelationship.predecessor_id == activity_id,
                ActivityRelationship.successor_id == activity_id
            )
        ).delete()
        
        # حذف موارد النشاط
        ActivityResource.query.filter_by(activity_id=activity_id).delete()
        
        db.session.delete(activity)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    

# ============================================
# API لمصروفات الأنشطة (Activity Expenses)
# ============================================

# @primavera_bp.route('/api/activity/<int:activity_id>/expenses', methods=['GET'])
# @login_required
# def api_activity_expenses(activity_id):
#     """API لجلب مصروفات النشاط"""
#     activity = check_activity_access(activity_id)
#     if not activity:
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     expenses = ActivityExpense.query.filter_by(activity_id=activity_id).order_by(ActivityExpense.expense_date.desc()).all()
    
#     return jsonify({
#         'success': True,
#         'expenses': [{
#             'id': e.id,
#             'date': e.expense_date.isoformat() if e.expense_date else None,
#             'category': e.category,
#             'description': e.description,
#             'amount': e.amount,
#             'currency': e.currency,
#             'is_approved': e.is_approved,
#             'approved_by': e.approver.full_name if e.approver else None,
#             'approved_at': e.approved_at.isoformat() if e.approved_at else None,
#             'receipt_url': e.receipt_url
#         } for e in expenses]
#     })

# @primavera_bp.route('/api/activity/<int:activity_id>/expense', methods=['POST'])
# @login_required
# def api_activity_expense_create(activity_id):
#     """API لإضافة مصروف جديد"""
#     activity = check_activity_access(activity_id)
#     if not activity:
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     data = request.get_json()
    
#     try:
#         expense = ActivityExpense(
#             activity_id=activity_id,
#             expense_date=datetime.strptime(data.get('date'), '%Y-%m-%d').date() if data.get('date') else date.today(),
#             category=data.get('category'),
#             description=data.get('description'),
#             amount=float(data.get('amount', 0)),
#             currency=data.get('currency', 'SAR'),
#             is_approved=False,
#             created_by=current_user.id
#         )
        
#         db.session.add(expense)
#         db.session.commit()
        
#         return jsonify({'success': True})
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500

# @primavera_bp.route('/api/activity-expense/<int:expense_id>/approve', methods=['POST'])
# @login_required
# def api_activity_expense_approve(expense_id):
#     """API للموافقة على مصروف"""
#     expense = ActivityExpense.query.get_or_404(expense_id)
    
#     # التحقق من الصلاحية
#     if not check_activity_access(expense.activity_id):
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     try:
#         expense.is_approved = True
#         expense.approved_by = current_user.id
#         expense.approved_at = datetime.utcnow()
        
#         db.session.commit()
        
#         return jsonify({'success': True})
        
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({'error': str(e)}), 500


# ============================================
# دوال مساعدة للمخاطر
# ============================================

def calculate_risk_score(probability, impact):
    """حساب درجة الخطر بناءً على الاحتمالية والتأثير"""
    impact_values = {
        'very_low': 1,
        'low': 2,
        'medium': 3,
        'high': 4,
        'very_high': 5
    }
    
    impact_value = impact_values.get(impact, 3)
    score = (probability / 100) * impact_value
    
    if score >= 3.5:
        return 'high'
    elif score >= 2:
        return 'medium'
    else:
        return 'low'

def get_risk_stats(risks):
    """حساب إحصائيات المخاطر"""
    stats = {
        'high_count': 0,
        'medium_count': 0,
        'low_count': 0,
        'total_score': 0,
        'overall_score': 0
    }
    
    for risk in risks:
        if risk.risk_level == 'high':
            stats['high_count'] += 1
            stats['total_score'] += 4
        elif risk.risk_level == 'medium':
            stats['medium_count'] += 1
            stats['total_score'] += 2
        else:
            stats['low_count'] += 1
            stats['total_score'] += 1
    
    total_risks = len(risks)
    if total_risks > 0:
        stats['overall_score'] = round(stats['total_score'] / total_risks, 1)
    
    return stats


# ============================================
# API للمخاطر
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/risks', methods=['GET'])
@login_required
def api_get_activity_risks(activity_id):
    """جلب جميع مخاطر النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        risks = ActivityRisk.query.filter_by(
            activity_id=activity_id
        ).order_by(
            # ترتيب حسب الخطورة: عالي أولاً
            db.case(
                (ActivityRisk.risk_level == 'high', 1),
                (ActivityRisk.risk_level == 'medium', 2),
                (ActivityRisk.risk_level == 'low', 3),
                else_=4
            ),
            ActivityRisk.created_at.desc()
        ).all()
        
        risks_data = []
        for risk in risks:
            risks_data.append({
                'id': risk.id,
                'title': risk.title,
                'description': risk.description,
                'risk_level': risk.risk_level,
                'probability': risk.probability,
                'impact': risk.impact,
                'mitigation_plan': risk.mitigation_plan,
                'contingency_plan': risk.contingency_plan,
                'status': risk.status,
                'created_at': risk.created_at.isoformat() if risk.created_at else None,
                'created_by': risk.creator.full_name if risk.creator else None
            })
        
        # حساب الإحصائيات
        stats = get_risk_stats(risks)
        
        return jsonify({
            'success': True,
            'risks': risks_data,
            'stats': stats,
            'count': len(risks_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/risk', methods=['POST'])
@login_required
def api_add_activity_risk(activity_id):
    """إضافة خطر جديد للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    # التحقق من البيانات المطلوبة
    if not data or not data.get('title'):
        return jsonify({'error': 'عنوان الخطر مطلوب'}), 400
    
    title = data.get('title').strip()
    description = data.get('description', '').strip()
    risk_level = data.get('level', 'medium')
    probability = data.get('probability', 50)
    impact = data.get('impact', 'medium')
    mitigation_plan = data.get('mitigation', '').strip()
    
    # التحقق من صحة القيم
    if probability < 0 or probability > 100:
        return jsonify({'error': 'نسبة الاحتمالية يجب أن تكون بين 0 و 100'}), 400
    
    valid_levels = ['low', 'medium', 'high']
    if risk_level not in valid_levels:
        risk_level = 'medium'
    
    valid_impacts = ['very_low', 'low', 'medium', 'high', 'very_high']
    if impact not in valid_impacts:
        impact = 'medium'
    
    # حساب درجة الخطر تلقائياً
    calculated_level = calculate_risk_score(probability, impact)
    
    try:
        risk = ActivityRisk(
            activity_id=activity_id,
            title=title,
            description=description,
            risk_level=calculated_level,  # استخدام المستوى المحسوب
            probability=probability,
            impact=impact,
            mitigation_plan=mitigation_plan,
            contingency_plan=data.get('contingency', ''),
            status='identified',
            created_at=datetime.utcnow(),
            created_by=current_user.id
        )
        
        db.session.add(risk)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'risk': {
                'id': risk.id,
                'title': risk.title,
                'description': risk.description,
                'risk_level': risk.risk_level,
                'probability': risk.probability,
                'impact': risk.impact,
                'mitigation_plan': risk.mitigation_plan,
                'status': risk.status,
                'created_at': risk.created_at.isoformat()
            },
            'message': 'تم إضافة الخطر بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/risk/<int:risk_id>', methods=['GET'])
@login_required
def api_get_risk(risk_id):
    """جلب تفاصيل خطر معين"""
    risk = ActivityRisk.query.get_or_404(risk_id)
    
    activity = check_activity_access(risk.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'risk': {
            'id': risk.id,
            'title': risk.title,
            'description': risk.description,
            'risk_level': risk.risk_level,
            'probability': risk.probability,
            'impact': risk.impact,
            'mitigation_plan': risk.mitigation_plan,
            'contingency_plan': risk.contingency_plan,
            'status': risk.status,
            'created_at': risk.created_at.isoformat() if risk.created_at else None,
            'created_by': risk.creator.full_name if risk.creator else None
        }
    })


@primavera_bp.route('/api/risk/<int:risk_id>', methods=['PUT'])
@login_required
def api_update_risk(risk_id):
    """تحديث خطر"""
    risk = ActivityRisk.query.get_or_404(risk_id)
    
    activity = check_activity_access(risk.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if 'title' in data:
            risk.title = data['title'].strip()
        if 'description' in data:
            risk.description = data['description'].strip()
        if 'probability' in data:
            probability = data['probability']
            if 0 <= probability <= 100:
                risk.probability = probability
        if 'impact' in data:
            valid_impacts = ['very_low', 'low', 'medium', 'high', 'very_high']
            if data['impact'] in valid_impacts:
                risk.impact = data['impact']
        if 'mitigation_plan' in data:
            risk.mitigation_plan = data['mitigation_plan'].strip()
        if 'contingency_plan' in data:
            risk.contingency_plan = data['contingency_plan'].strip()
        if 'status' in data:
            valid_statuses = ['identified', 'mitigated', 'closed']
            if data['status'] in valid_statuses:
                risk.status = data['status']
        
        # إعادة حساب مستوى الخطر
        risk.risk_level = calculate_risk_score(risk.probability, risk.impact)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'risk': {
                'id': risk.id,
                'title': risk.title,
                'risk_level': risk.risk_level,
                'probability': risk.probability,
                'impact': risk.impact,
                'status': risk.status
            },
            'message': 'تم تحديث الخطر بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/risk/<int:risk_id>', methods=['DELETE'])
@login_required
def api_delete_risk(risk_id):
    """حذف خطر"""
    risk = ActivityRisk.query.get_or_404(risk_id)
    
    activity = check_activity_access(risk.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(risk)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الخطر بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/risk/<int:risk_id>/mitigate', methods=['POST'])
@login_required
def api_mitigate_risk(risk_id):
    """تخفيف الخطر (تغيير الحالة إلى mitigated)"""
    risk = ActivityRisk.query.get_or_404(risk_id)
    
    activity = check_activity_access(risk.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if risk.status == 'mitigated':
        return jsonify({'error': 'الخطر قيد التخفيف بالفعل'}), 400
    
    try:
        risk.status = 'mitigated'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم تحديث حالة الخطر إلى قيد التخفيف'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/risk/<int:risk_id>/close', methods=['POST'])
@login_required
def api_close_risk(risk_id):
    """إغلاق الخطر"""
    risk = ActivityRisk.query.get_or_404(risk_id)
    
    activity = check_activity_access(risk.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if risk.status == 'closed':
        return jsonify({'error': 'الخطر مغلق بالفعل'}), 400
    
    try:
        risk.status = 'closed'
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم إغلاق الخطر بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/risks/stats', methods=['GET'])
@login_required
def api_get_risk_stats(activity_id):
    """جلب إحصائيات المخاطر للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        risks = ActivityRisk.query.filter_by(activity_id=activity_id).all()
        stats = get_risk_stats(risks)
        
        return jsonify({
            'success': True,
            'stats': stats,
            'risks_by_status': {
                'identified': sum(1 for r in risks if r.status == 'identified'),
                'mitigated': sum(1 for r in risks if r.status == 'mitigated'),
                'closed': sum(1 for r in risks if r.status == 'closed')
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# صفحة عرض المخاطر (GET)
# ============================================

# @primavera_bp.route('/activity/<int:activity_id>/risks', methods=['GET'])
# @login_required
# def activity_risks_view(activity_id):
#     """عرض صفحة مخاطر النشاط"""
#     activity = check_activity_access(activity_id)
#     if not activity:
#         flash('غير مصرح', 'danger')
#         return redirect(url_for('primavera.dashboard'))
    
#     risks = ActivityRisk.query.filter_by(
#         activity_id=activity_id
#     ).order_by(
#         db.case(
#             (ActivityRisk.risk_level == 'high', 1),
#             (ActivityRisk.risk_level == 'medium', 2),
#             (ActivityRisk.risk_level == 'low', 3),
#             else_=4
#         )
#     ).all()
    
#     # حساب الإحصائيات
#     stats = get_risk_stats(risks)
    
#     return render_template(
#         'primavera/tabs/activity/risks.html',
#         activity=activity,
#         activity_risks=risks,
#         risk_stats=stats,
#         now=datetime.now()
#     )

# ============================================
# دوال مساعدة للملفات
# ============================================

def get_file_extension(filename):
    """الحصول على امتداد الملف"""
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def get_file_size(file_path):
    """الحصول على حجم الملف بالكيلوبايت"""
    try:
        size_bytes = os.path.getsize(file_path)
        return round(size_bytes / 1024, 2)
    except:
        return 0

def save_document_file(file):
    """حفظ ملف المستند وإرجاع المعلومات"""
    if not file or not file.filename:
        return None
    
    # التحقق من حجم الملف (10MB)
    if file.content_length and file.content_length > 10 * 1024 * 1024:
        return None
    
    # تأمين اسم الملف
    filename = secure_filename(file.filename)
    ext = get_file_extension(filename)
    
    # إنشاء اسم فريد للملف
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    
    # إنشاء المجلد إذا لم يكن موجوداً
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'documents')
    os.makedirs(upload_folder, exist_ok=True)
    
    # حفظ الملف
    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)
    
    return {
        'filename': unique_filename,
        'original_filename': filename,
        'file_extension': ext,
        'file_size': get_file_size(file_path),
        'file_path': file_path,
        'url': url_for('static', filename=f'uploads/documents/{unique_filename}')
    }


# ============================================
# API للمستندات
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/documents', methods=['GET'])
@login_required
def api_get_activity_documents(activity_id):
    """جلب جميع مستندات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        documents = ActivityDocument.query.filter_by(
            activity_id=activity_id
        ).order_by(ActivityDocument.uploaded_at.desc()).all()
        
        documents_data = []
        for doc in documents:
            documents_data.append({
                'id': doc.id,
                'filename': doc.original_filename or doc.filename,
                'file_extension': get_file_extension(doc.filename),
                'file_size': get_file_size(os.path.join(current_app.root_path, 'static', 'uploads', 'documents', doc.filename)) if doc.filename else 0,
                'url': url_for('static', filename=f'uploads/documents/{doc.filename}'),
                'download_url': url_for('primavera.download_document', document_id=doc.id),
                'preview_url': url_for('primavera.preview_document', document_id=doc.id),
                'title': doc.title,
                'description': doc.description,
                'requires_approval': doc.requires_approval,
                'approval_status': doc.approval_status,
                'uploaded_by': doc.uploader.full_name if doc.uploader else None,
                'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                'approved_by': doc.approver.full_name if doc.approver else None,
                'approved_at': doc.approved_at.isoformat() if doc.approved_at else None
            })
        
        return jsonify({
            'success': True,
            'documents': documents_data,
            'count': len(documents_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/documents/upload', methods=['POST'])
@login_required
def api_upload_documents(activity_id):
    """رفع مستندات متعددة للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    files = request.files.getlist('files')
    
    if not files or len(files) == 0:
        return jsonify({'error': 'لم يتم اختيار أي ملفات'}), 400
    
    uploaded_documents = []
    errors = []
    
    for file in files:
        if file and file.filename:
            # حفظ الملف
            file_info = save_document_file(file)
            if not file_info:
                errors.append(f'فشل حفظ الملف {file.filename}')
                continue
            
            try:
                # إنشاء سجل في قاعدة البيانات
                document = ActivityDocument(
                    activity_id=activity_id,
                    filename=file_info['filename'],
                    original_filename=file_info['original_filename'],
                    title=file_info['original_filename'],
                    description=request.form.get('description', ''),
                    requires_approval=False,
                    approval_status='pending',
                    uploaded_by=current_user.id,
                    uploaded_at=datetime.utcnow()
                )
                
                db.session.add(document)
                db.session.flush()
                
                uploaded_documents.append({
                    'id': document.id,
                    'filename': file_info['original_filename'],
                    'file_extension': file_info['file_extension'],
                    'file_size': file_info['file_size'],
                    'url': file_info['url'],
                    'download_url': url_for('primavera.download_document', document_id=document.id),
                    'preview_url': url_for('primavera.preview_document', document_id=document.id)
                })
                
            except Exception as e:
                errors.append(f'خطأ في حفظ {file.filename}: {str(e)}')
                # حذف الملف إذا فشل حفظ البيانات
                if os.path.exists(file_info['file_path']):
                    os.remove(file_info['file_path'])
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
    return jsonify({
        'success': True,
        'uploaded': uploaded_documents,
        'errors': errors,
        'message': f'تم رفع {len(uploaded_documents)} ملف بنجاح'
    })


@primavera_bp.route('/api/document/<int:document_id>', methods=['DELETE'])
@login_required
def api_delete_document(document_id):
    """حذف مستند"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    activity = check_activity_access(document.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # حذف الملف الفعلي
        file_path = os.path.join(current_app.root_path, 'static', 'uploads', 'documents', document.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        db.session.delete(document)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف المستند بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/document/<int:document_id>/preview')
@login_required
def preview_document(document_id):
    """معاينة المستند"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    activity = check_activity_access(document.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    file_path = os.path.join(current_app.root_path, 'static', 'uploads', 'documents', document.filename)
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'الملف غير موجود'}), 404
    
    ext = get_file_extension(document.filename)
    
    # للصور والفيديو والصوت - عرض مباشر
    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4', 'mp3', 'wav']:
        return send_from_directory(
            os.path.join(current_app.root_path, 'static', 'uploads', 'documents'),
            document.filename
        )
    
    # لملفات PDF - عرض في iframe
    return render_template('primavera/preview_document.html', document=document)


@primavera_bp.route('/api/document/<int:document_id>/download')
@login_required
def download_document(document_id):
    """تحميل المستند"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    activity = check_activity_access(document.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    return send_from_directory(
        os.path.join(current_app.root_path, 'static', 'uploads', 'documents'),
        document.filename,
        as_attachment=True,
        download_name=document.original_filename or document.filename
    )


@primavera_bp.route('/api/document/<int:document_id>/approve', methods=['POST'])
@login_required
def api_approve_document(document_id):
    """الموافقة على مستند"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    activity = check_activity_access(document.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if document.approval_status == 'approved':
        return jsonify({'error': 'المستند معتمد بالفعل'}), 400
    
    try:
        document.approval_status = 'approved'
        document.approved_by = current_user.id
        document.approved_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم اعتماد المستند بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# API للتعليقات (Activity Feedback)
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/feedback', methods=['POST'])
@login_required
def api_activity_feedback_create(activity_id):
    """API لإضافة تعليق جديد مع دعم المرفقات"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # معالجة البيانات (يدعم كلاً من JSON و FormData)
    content = None
    attachments = []
    
    if request.is_json:
        # إذا كان الطلب JSON
        data = request.get_json()
        content = data.get('content')
    else:
        # إذا كان الطلب FormData
        content = request.form.get('content')
        
        # معالجة الملفات المرفوعة
        for key in request.files:
            file = request.files[key]
            if file and file.filename:
                # حفظ الملف
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4().hex}_{filename}"
                
                # إنشاء مجلد الرفع إذا لم يكن موجوداً
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'feedback')
                os.makedirs(upload_folder, exist_ok=True)
                
                file_path = os.path.join(upload_folder, unique_filename)
                file.save(file_path)
                
                # إضافة رابط الملف
                file_url = url_for('static', filename=f'uploads/feedback/{unique_filename}')
                attachments.append({
                    'name': filename,
                    'url': file_url,
                    'size': file.content_length,
                    'type': file.content_type
                })
    
    if not content:
        return jsonify({'error': 'محتوى التعليق مطلوب'}), 400
    
    try:
        feedback = ActivityFeedback(
            activity_id=activity_id,
            user_id=current_user.id,
            content=content,
            attachment_url=json.dumps(attachments) if attachments else None
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        # تجهيز البيانات للإرجاع
        feedback_data = {
            'id': feedback.id,
            'content': feedback.content,
            'user_name': current_user.full_name,
            'user_role': current_user.role,
            'user_id': current_user.id,
            'created_at': feedback.created_at.strftime('%Y-%m-%d %H:%M'),
            'attachment_url': json.loads(feedback.attachment_url) if feedback.attachment_url else []
        }
        
        return jsonify({
            'success': True,
            'feedback': feedback_data,
            'message': 'تم إضافة التعليق بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/feedback/<int:feedback_id>/update', methods=['POST'])
@login_required
def api_feedback_update(feedback_id):
    """تحديث تعليق"""
    feedback = ActivityFeedback.query.get_or_404(feedback_id)
    
    if feedback.user_id != current_user.id and current_user.role not in ['org_admin', 'project_manager']:
        return jsonify({'error': 'غير مصرح بتعديل هذا التعليق'}), 403
    
    data = request.get_json()
    new_content = data.get('content')
    
    if not new_content:
        return jsonify({'error': 'محتوى التعليق مطلوب'}), 400
    
    try:
        feedback.content = new_content
        feedback.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم تحديث التعليق بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/feedback/<int:feedback_id>/delete', methods=['POST'])
@login_required
def api_feedback_delete(feedback_id):
    """حذف تعليق"""
    feedback = ActivityFeedback.query.get_or_404(feedback_id)
    
    if feedback.user_id != current_user.id and current_user.role not in ['org_admin', 'project_manager']:
        return jsonify({'error': 'غير مصرح بحذف هذا التعليق'}), 403
    
    try:
        db.session.delete(feedback)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف التعليق بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/feedback/list', methods=['GET'])
@login_required
def api_activity_feedback_list(activity_id):
    """جلب قائمة التعليقات للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        feedbacks = ActivityFeedback.query.filter_by(
            activity_id=activity_id
        ).order_by(ActivityFeedback.created_at.desc()).all()
        
        feedbacks_data = []
        for fb in feedbacks:
            feedbacks_data.append({
                'id': fb.id,
                'content': fb.content,
                'user_name': fb.user.full_name if fb.user else 'مستخدم',
                'user_role': fb.user.role if fb.user else 'employee',
                'user_id': fb.user_id,
                'created_at': fb.created_at.strftime('%Y-%m-%d %H:%M'),
                'attachment_url': json.loads(fb.attachment_url) if fb.attachment_url else []
            })
        
        return jsonify({
            'success': True,
            'feedbacks': feedbacks_data,
            'count': len(feedbacks_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================
# API لأكواد الأنشطة (Activity Codes)
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/codes', methods=['GET'])
@login_required
def api_activity_codes(activity_id):
    """API لجلب أكواد النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'codes': activity.activity_code_values or {}
    })

@primavera_bp.route('/api/activity/<int:activity_id>/code', methods=['POST'])
@login_required
def api_activity_code_set(activity_id):
    """API لتعيين كود للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    code_type = data.get('code_type')
    code_value = data.get('code_value')
    
    try:
        activity.set_activity_code(code_type, code_value)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# API للحقول المخصصة (UDF)
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/udf', methods=['GET'])
@login_required
def api_activity_udf(activity_id):
    """API لجلب الحقول المخصصة للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # جلب تعريفات UDF الخاصة بالأنشطة
    udf_definitions = UDF.query.filter_by(
        org_id=activity.project.eps.org_id,
        udf_type='activity',
        is_active=True
    ).all()
    
    values = activity.udf_values or {}
    
    result = []
    for udf in udf_definitions:
        result.append({
            'id': udf.id,
            'name': udf.udf_name,
            'label': udf.udf_label,
            'label_ar': udf.udf_label_ar,
            'data_type': udf.data_type,
            'value': values.get(udf.udf_name),
            'list_values': udf.list_values,
            'is_required': udf.is_required
        })
    
    return jsonify({
        'success': True,
        'udf': result
    })

@primavera_bp.route('/api/activity/<int:activity_id>/udf', methods=['POST'])
@login_required
def api_activity_udf_set(activity_id):
    """API لتعيين قيمة حقل مخصص"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    udf_name = data.get('udf_name')
    value = data.get('value')
    
    try:
        activity.set_udf_value(udf_name, value)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# API لتحليل الأداء (Performance Analysis)
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/performance-analysis')
@login_required
def api_project_performance(project_id):
    """API لتحليل أداء المشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    # حساب SPI و CPI
    total_planned_value = sum(a.planned_value for a in activities if a.planned_value)
    total_earned_value = sum(a.earned_value for a in activities if a.earned_value)
    total_actual_cost = sum(a.actual_cost for a in activities if a.actual_cost)
    
    spi = total_earned_value / total_planned_value if total_planned_value > 0 else 1
    cpi = total_earned_value / total_actual_cost if total_actual_cost > 0 else 1
    
    # توقعات الإنجاز
    if spi > 0 and cpi > 0:
        estimated_duration = project.project.planned_duration / spi if project.project.planned_duration else 0
        estimated_cost = total_planned_value / cpi if total_planned_value > 0 else 0
    else:
        estimated_duration = project.project.planned_duration
        estimated_cost = total_planned_value
    
    return jsonify({
        'success': True,
        'analysis': {
            'spi': round(spi, 2),
            'cpi': round(cpi, 2),
            'eac': round(estimated_cost, 2),
            'etc': round(estimated_cost - total_actual_cost, 2) if estimated_cost > total_actual_cost else 0,
            'estimated_duration': round(estimated_duration, 1),
            'current_progress': project.project.progress_percentage,
            'expected_progress': project.project.progress_percentage * spi if spi else 0
        }
    })

# ============================================
# API لتوصيات الذكاء الاصطناعي
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/ai-recommendations')
@login_required
def api_project_ai_recommendations(project_id):
    """API لجلب توصيات الذكاء الاصطناعي للمشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    from app.models import AIRecommendation
    
    recommendations = AIRecommendation.query.filter_by(
        project_id=project_id,
        status='pending'
    ).order_by(AIRecommendation.generated_at.desc()).all()
    
    return jsonify({
        'success': True,
        'recommendations': [{
            'id': r.id,
            'type': r.recommendation_type,
            'title': r.title,
            'description': r.description,
            'confidence': r.confidence_score,
            'urgency': r.urgency_level,
            'generated_at': r.generated_at.isoformat() if r.generated_at else None
        } for r in recommendations]
    })

# ============================================
# API لتحليل المخاطر المتقدم
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/risk-analysis')
@login_required
def api_project_risk_analysis(project_id):
    """API لتحليل مخاطر المشروع المتقدم"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # تحليل مخاطر الأنشطة
    activity_risks = ActivityRisk.query.join(Activity).filter(
        Activity.project_id == project_id
    ).all()
    
    risk_matrix = {
        'high': {'count': 0, 'probability_avg': 0, 'impact_avg': 0},
        'medium': {'count': 0, 'probability_avg': 0, 'impact_avg': 0},
        'low': {'count': 0, 'probability_avg': 0, 'impact_avg': 0}
    }
    
    total_probability = 0
    total_impact = 0
    
    for risk in activity_risks:
        level = risk.risk_level
        if level in risk_matrix:
            risk_matrix[level]['count'] += 1
            risk_matrix[level]['probability_avg'] += risk.probability or 50
            risk_matrix[level]['impact_avg'] += impact_value(risk.impact)
            
            total_probability += risk.probability or 50
            total_impact += impact_value(risk.impact)
    
    # حساب المتوسطات
    for level in risk_matrix:
        if risk_matrix[level]['count'] > 0:
            risk_matrix[level]['probability_avg'] /= risk_matrix[level]['count']
            risk_matrix[level]['impact_avg'] /= risk_matrix[level]['count']
    
    # تحليل التأثير على الجدول الزمني
    schedule_impact = 0
    for risk in activity_risks:
        if risk.risk_level == 'high' and risk.status != 'closed':
            schedule_impact += 5  # 5 أيام افتراضية
        elif risk.risk_level == 'medium' and risk.status != 'closed':
            schedule_impact += 2
    
    return jsonify({
        'success': True,
        'risk_analysis': {
            'total_risks': len(activity_risks),
            'risk_matrix': risk_matrix,
            'overall_probability': total_probability / len(activity_risks) if activity_risks else 0,
            'overall_impact': total_impact / len(activity_risks) if activity_risks else 0,
            'schedule_impact_days': schedule_impact,
            'risk_response_status': {
                'identified': len([r for r in activity_risks if r.status == 'identified']),
                'mitigated': len([r for r in activity_risks if r.status == 'mitigated']),
                'closed': len([r for r in activity_risks if r.status == 'closed'])
            }
        }
    })

def impact_value(impact_str):
    """تحويل نص التأثير إلى قيمة رقمية"""
    impact_map = {'very_low': 20, 'low': 40, 'medium': 60, 'high': 80, 'very_high': 100}
    return impact_map.get(impact_str, 60)

# ============================================
# API لتحسين الجدول الزمني (Schedule Optimization)
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/optimize-schedule', methods=['POST'])
@login_required
def api_optimize_schedule(project_id):
    """API لتحسين الجدول الزمني باستخدام الذكاء الاصطناعي"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        engine = PrimaveraEngine(project)
        engine.load_project_data()
        
        # تحليل المسار الحرج
        critical_path = engine.get_critical_path()
        
        # اقتراح تحسينات
        suggestions = []
        
        for activity in critical_path:
            # تحقق من إمكانية تقليل المدة بإضافة موارد
            resources = ActivityResource.query.filter_by(activity_id=activity.id).all()
            
            if resources and activity.remaining_duration > 5:
                suggestions.append({
                    'activity_id': activity.activity_id,
                    'activity_name': activity.activity_name,
                    'current_duration': activity.remaining_duration,
                    'suggested_duration': max(1, activity.remaining_duration * 0.7),
                    'savings': activity.remaining_duration * 0.3,
                    'reason': 'إضافة موارد إضافية',
                    'resources_needed': len(resources) + 1
                })
            
            # تحقق من إمكانية البدء المبكر
            if activity.early_start and activity.planned_start:
                if activity.early_start < activity.planned_start:
                    days_saved = (activity.planned_start - activity.early_start).days
                    if days_saved > 0:
                        suggestions.append({
                            'activity_id': activity.activity_id,
                            'activity_name': activity.activity_name,
                            'savings': days_saved,
                            'reason': 'بدء مبكر',
                            'new_start': activity.early_start.strftime('%Y-%m-%d')
                        })
        
        # إنشاء مهمة ذكاء اصطناعي للتحسين
        from app.models import AITask
        ai_task = AITask(
            task_type='schedule_optimization',
            task_name=f'تحسين جدول المشروع {project.name}',
            project_id=project_id,
            parameters={
                'critical_path_length': len(critical_path),
                'suggestions_count': len(suggestions)
            },
            scheduled_time=datetime.utcnow(),
            status='completed',
            completed_at=datetime.utcnow(),
            result={'suggestions': suggestions}
        )
        db.session.add(ai_task)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'suggestions': suggestions,
            'summary': {
                'total_savings': sum(s.get('savings', 0) for s in suggestions),
                'activities_improved': len(suggestions)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# API لتحليل الموارد (Resource Analysis)
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/resource-analysis')
@login_required
def api_resource_analysis(project_id):
    """API لتحليل استخدام الموارد"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # تحليل استخدام الموارد
    resources = Resource.query.filter_by(org_id=project.eps.org_id).all()
    
    analysis = []
    for resource in resources:
        assignments = ActivityResource.query.filter_by(resource_id=resource.id)\
            .join(Activity).filter(Activity.project_id == project_id).all()
        
        total_assigned = sum(a.planned_quantity for a in assignments)
        utilization = (total_assigned / resource.available_quantity * 100) if resource.available_quantity > 0 else 0
        
        # تحليل التحميل الزائد
        overload = False
        overload_periods = []
        
        if utilization > 100:
            overload = True
            # تحديد فترات التحميل الزائد
            for assignment in assignments:
                if assignment.planned_quantity > (resource.available_quantity * 0.3):
                    overload_periods.append({
                        'activity': assignment.activity.activity_name if assignment.activity else None,
                        'quantity': assignment.planned_quantity,
                        'period': 'غير محدد'
                    })
        
        analysis.append({
            'id': resource.id,
            'name': resource.name,
            'type': resource.resource_type,
            'available': resource.available_quantity,
            'assigned': total_assigned,
            'utilization': round(utilization, 2),
            'status': 'overloaded' if overload else 'normal' if utilization > 70 else 'underutilized',
            'overload_periods': overload_periods if overload else []
        })
    
    return jsonify({
        'success': True,
        'resource_analysis': analysis
    })

# ============================================
# API للتنبؤ بالأداء (Performance Prediction)
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/performance-prediction')
@login_required
def api_performance_prediction(project_id):
    """API للتنبؤ بأداء المشروع المستقبلي"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # جمع البيانات التاريخية
    activities = Activity.query.filter_by(project_id=project_id).order_by(Activity.planned_start).all()
    
    if len(activities) < 5:
        return jsonify({
            'success': True,
            'prediction': None,
            'message': 'البيانات غير كافية للتنبؤ الدقيق'
        })
    
    # تحليل معدل التقدم
    completed_activities = [a for a in activities if a.status == 'completed']
    if completed_activities:
        avg_completion_time = sum((a.actual_finish - a.actual_start).days for a in completed_activities if a.actual_start and a.actual_finish) / len(completed_activities)
        avg_delay = sum((a.actual_finish - a.planned_finish).days for a in completed_activities if a.actual_finish and a.planned_finish) / len(completed_activities)
    else:
        avg_completion_time = 10
        avg_delay = 0
    
    # التنبؤ بالإنجاز
    remaining_activities = [a for a in activities if a.status != 'completed']
    predicted_completion_date = datetime.now()
    
    if remaining_activities:
        total_remaining_duration = sum(a.remaining_duration or a.original_duration for a in remaining_activities)
        predicted_completion_date = datetime.now() + timedelta(days=total_remaining_duration * (1 + avg_delay/30))
    
    # حساب الثقة
    confidence = min(90, len(completed_activities) * 10)
    
    return jsonify({
        'success': True,
        'prediction': {
            'completion_date': predicted_completion_date.strftime('%Y-%m-%d'),
            'confidence': confidence,
            'estimated_remaining_days': total_remaining_duration if remaining_activities else 0,
            'risk_of_delay': 'high' if avg_delay > 10 else 'medium' if avg_delay > 5 else 'low',
            'expected_delay_days': round(avg_delay * (len(remaining_activities) / max(1, len(completed_activities)))),
            'based_on': f'{len(completed_activities)} نشاط مكتمل'
        }
    })

# ============================================
# API لمقارنة خطوط الأساس (Baseline Comparison)
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/baselines/compare')
@login_required
def api_baselines_compare(project_id):
    """API لمقارنة جميع خطوط الأساس"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    baselines = Baseline.query.filter_by(project_id=project_id).order_by(Baseline.version).all()
    
    comparison = []
    for baseline in baselines:
        # حساب الفروقات
        if baseline.activities_snapshot:
            baseline_activities = baseline.activities_snapshot
            current_activities = Activity.query.filter_by(project_id=project_id).all()
            
            # حساب تباين المدة
            baseline_duration = sum(a.get('duration', 0) for a in baseline_activities)
            current_duration = sum(a.original_duration for a in current_activities)
            duration_variance = current_duration - baseline_duration
            
            # حساب تباين التكلفة
            baseline_cost = baseline.total_cost
            current_cost = project.total_planned_cost
            cost_variance = current_cost - baseline_cost
            
            comparison.append({
                'id': baseline.id,
                'name': baseline.name,
                'version': baseline.version,
                'created_at': baseline.created_at.strftime('%Y-%m-%d') if baseline.created_at else None,
                'baseline_duration': baseline_duration,
                'current_duration': current_duration,
                'duration_variance': duration_variance,
                'baseline_cost': baseline_cost,
                'current_cost': current_cost,
                'cost_variance': cost_variance,
                'variance_percentage': round((duration_variance / baseline_duration * 100) if baseline_duration > 0 else 0, 2)
            })
    
    return jsonify({
        'success': True,
        'comparison': comparison
    })

# ============================================
# API لتصدير البيانات (Data Export)
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/export/<format>')
@login_required
def api_export_project(project_id, format):
    """API لتصدير بيانات المشروع بصيغ مختلفة"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if format == 'json':
        # تصدير كـ JSON
        data = {
            'project': project.to_dict(),
            'activities': [a.to_dict() for a in Activity.query.filter_by(project_id=project_id).all()],
            'relationships': [r.to_dict() for r in ActivityRelationship.query.filter_by(project_id=project_id).all()],
            'resources': get_project_resources_data(project_id),
            'statistics': calculate_project_statistics(project_id)
        }
        
        return jsonify({
            'success': True,
            'data': data
        })
    
    elif format == 'xlsx':
        # تصدير Excel (يتطلب مكتبة openpyxl)
        from flask import send_file
        import io
        import pandas as pd
        
        # إنشاء ملف Excel في الذاكرة
        output = io.BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # ورقة الأنشطة
            activities = Activity.query.filter_by(project_id=project_id).all()
            activities_data = [{
                'ID': a.activity_id,
                'Name': a.activity_name,
                'Type': a.activity_type,
                'Status': a.status,
                'Planned Start': a.planned_start,
                'Planned Finish': a.planned_finish,
                'Progress': a.progress_percentage,
                'Duration': a.original_duration,
                'Critical': 'Yes' if a.is_critical else 'No'
            } for a in activities]
            
            df_activities = pd.DataFrame(activities_data)
            df_activities.to_excel(writer, sheet_name='Activities', index=False)
            
            # ورقة العلاقات
            relationships = ActivityRelationship.query.filter_by(project_id=project_id).all()
            rel_data = [{
                'Predecessor': r.predecessor.activity_id if r.predecessor else '',
                'Successor': r.successor.activity_id if r.successor else '',
                'Type': r.relationship_type,
                'Lag': r.lag_days
            } for r in relationships]
            
            df_relations = pd.DataFrame(rel_data)
            df_relations.to_excel(writer, sheet_name='Relationships', index=False)
        
        output.seek(0)
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'project_{project.project_code}.xlsx'
        )
    
    else:
        return jsonify({'error': 'صيغة غير مدعومة'}), 400

def get_project_resources_data(project_id):
    """جلب بيانات موارد المشروع للتصدير"""
    resources = ActivityResource.query.join(Activity).filter(
        Activity.project_id == project_id
    ).all()
    
    return [{
        'activity_id': r.activity.activity_id if r.activity else None,
        'activity_name': r.activity.activity_name if r.activity else None,
        'resource_name': r.resource.name if r.resource else None,
        'resource_type': r.resource.resource_type if r.resource else None,
        'planned_quantity': r.planned_quantity,
        'planned_cost': r.planned_cost,
        'actual_quantity': r.actual_quantity,
        'actual_cost': r.actual_cost
    } for r in resources]

def calculate_project_statistics(project_id):
    """حساب إحصائيات المشروع للتصدير"""
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    return {
        'total_activities': len(activities),
        'completed': len([a for a in activities if a.status == 'completed']),
        'in_progress': len([a for a in activities if a.status == 'in_progress']),
        'not_started': len([a for a in activities if a.status == 'not_started']),
        'critical': len([a for a in activities if a.is_critical]),
        'total_duration': sum(a.original_duration for a in activities),
        'avg_progress': sum(a.progress_percentage for a in activities) / len(activities) if activities else 0
    }

# ============================================
# API لوحة التحكم (Dashboard APIs)
# ============================================

@primavera_bp.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    """API لإحصائيات لوحة التحكم الرئيسية"""
    org_id = get_org_id()
    
    if org_id:
        # إحصائيات المؤسسة
        total_projects = Project.query.join(EPS).filter(EPS.org_id == org_id).count()
        total_activities = Activity.query.join(Project).join(EPS).filter(EPS.org_id == org_id).count()
        total_resources = Resource.query.filter_by(org_id=org_id).count()
        
        # أنشطة حسب الحالة
        activities_by_status = db.session.query(
            Activity.status, func.count(Activity.id)
        ).join(Project).join(EPS).filter(EPS.org_id == org_id)\
         .group_by(Activity.status).all()
        
        # المشاريع حسب المخاطر
        high_risk_projects = Project.query.filter(Project.risk_level == 'high').count()
        
        # تقدم المشاريع
        projects_progress = db.session.query(
            func.avg(Project.progress)
        ).join(EPS).filter(EPS.org_id == org_id).scalar() or 0
    
    else:
        # إحصائيات المنصة
        total_projects = Project.query.count()
        total_activities = Activity.query.count()
        total_resources = Resource.query.count()
        total_organizations = Organization.query.count()
        
        activities_by_status = db.session.query(
            Activity.status, func.count(Activity.id)
        ).group_by(Activity.status).all()
        
        high_risk_projects = Project.query.filter(Project.project.risk_level == 'high').count()
        projects_progress = db.session.query(func.avg(Project.progress)).scalar() or 0
    
    return jsonify({
        'success': True,
        'stats': {
            'total_projects': total_projects,
            'total_activities': total_activities,
            'total_resources': total_resources,
            'total_organizations': total_organizations if not org_id else None,
            'activities_by_status': dict(activities_by_status),
            'high_risk_projects': high_risk_projects,
            'average_progress': round(projects_progress, 2)
        }
    })

@primavera_bp.route('/api/dashboard/recent-activities')
@login_required
def api_dashboard_recent_activities():
    """API لأحدث الأنشطة المحدثة"""
    org_id = get_org_id()
    
    query = Activity.query.join(Project).join(EPS)
    
    if org_id:
        query = query.filter(EPS.org_id == org_id)
    
    recent = query.order_by(Activity.updated_at.desc()).limit(10).all()
    
    return jsonify({
        'success': True,
        'activities': [{
            'id': a.id,
            'activity_id': a.activity_id,
            'name': a.activity_name,
            'project': a.project.name if a.project else None,
            'status': a.status,
            'progress': a.progress_percentage,
            'updated_at': a.updated_at.isoformat() if a.updated_at else None
        } for a in recent]
    })

@primavera_bp.route('/api/dashboard/upcoming-deadlines')
@login_required
def api_dashboard_upcoming_deadlines():
    """API للمواعيد النهائية القريبة"""
    org_id = get_org_id()
    today = date.today()
    next_week = today + timedelta(days=7)
    
    query = Activity.query.join(Project).join(EPS).filter(
        Activity.status.in_(['not_started', 'in_progress']),
        Activity.planned_finish >= today,
        Activity.planned_finish <= next_week
    )
    
    if org_id:
        query = query.filter(EPS.org_id == org_id)
    
    deadlines = query.order_by(Activity.planned_finish).limit(10).all()
    
    return jsonify({
        'success': True,
        'deadlines': [{
            'id': a.id,
            'activity_id': a.activity_id,
            'name': a.activity_name,
            'project': a.project.name if a.project else None,
            'planned_finish': a.planned_finish.strftime('%Y-%m-%d') if a.planned_finish else None,
            'days_left': (a.planned_finish.date() - today).days if a.planned_finish else 0,
            'progress': a.progress_percentage
        } for a in deadlines]
    })

# في primavera_routes.py - إضافة الـ APIs الجديدة

# ============================================
# Budget Log APIs
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/budget-log', methods=['GET'])
@login_required
def api_get_budget_log(project_id):
    """جلب سجل تغييرات الميزانية"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    logs = BudgetLog.query.filter_by(project_id=project_id).order_by(BudgetLog.date.desc()).all()
    
    return jsonify({
        'success': True,
        'logs': [{
            'id': l.id,
            'date': l.date.isoformat(),
            'change_number': l.change_number,
            'amount': l.amount,
            'responsible': l.responsible.full_name if l.responsible else None,
            'status': l.status,
            'reason': l.reason
        } for l in logs]
    })


@primavera_bp.route('/api/project/<int:project_id>/budget-log', methods=['POST'])
@login_required
def api_add_budget_log(project_id):
    """إضافة تغيير ميزانية"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # إنشاء رقم تغيير تلقائي
        last_log = BudgetLog.query.filter_by(project_id=project_id).order_by(BudgetLog.id.desc()).first()
        if last_log and last_log.change_number:
            last_num = int(last_log.change_number.split('-')[-1])
            change_number = f"CHG-{datetime.now().strftime('%Y%m')}-{last_num + 1:04d}"
        else:
            change_number = f"CHG-{datetime.now().strftime('%Y%m')}-0001"
        
        log = BudgetLog(
            project_id=project_id,
            date=datetime.strptime(data['date'], '%Y-%m-%d').date() if data.get('date') else date.today(),
            change_number=change_number,
            amount=float(data.get('amount', 0)),
            responsible_id=current_user.id,
            status=data.get('status', 'Proposed'),
            reason=data.get('reason')
        )
        
        db.session.add(log)
        
        # تحديث الميزانية الحالية
        if data.get('status') == 'Approved':
            project.current_budget = (project.current_budget or 0) + float(data.get('amount', 0))
        
        db.session.commit()
        
        return jsonify({'success': True, 'log_id': log.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# Spending Plan APIs
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/spending-plan', methods=['GET'])
@login_required
def api_get_spending_plan(project_id):
    """جلب خطة الصرف"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    items = SpendingPlanItem.query.filter_by(project_id=project_id).order_by(SpendingPlanItem.date).all()
    
    # حساب المجاميع
    total_spending = sum(i.planned_amount for i in items)
    total_benefit = sum(i.benefit_amount for i in items)
    
    # حساب المجاميع التراكمية
    running_spending = 0
    running_benefit = 0
    for item in items:
        running_spending += item.planned_amount
        running_benefit += item.benefit_amount
        item.spending_tally = running_spending
        item.benefit_tally = running_benefit
        item.undistributed_variance = running_spending - running_benefit
        item.benefit_variance = item.benefit_amount - item.planned_amount
    
    return jsonify({
        'success': True,
        'items': [{
            'id': i.id,
            'date': i.date.isoformat(),
            'planned_amount': i.planned_amount,
            'benefit_amount': i.benefit_amount,
            'spending_tally': i.spending_tally,
            'benefit_tally': i.benefit_tally,
            'undistributed_variance': i.undistributed_variance,
            'benefit_variance': i.benefit_variance
        } for i in items],
        'totals': {
            'spending': total_spending,
            'benefit': total_benefit,
            'variance': total_spending - total_benefit
        }
    })


@primavera_bp.route('/api/project/<int:project_id>/spending-plan', methods=['POST'])
@login_required
def api_add_spending_item(project_id):
    """إضافة بند خطة صرف"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        item = SpendingPlanItem(
            project_id=project_id,
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            planned_amount=float(data.get('planned_amount', 0)),
            benefit_amount=float(data.get('benefit_amount', 0))
        )
        
        db.session.add(item)
        db.session.commit()
        
        return jsonify({'success': True, 'item_id': item.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# Funding APIs
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/funding', methods=['GET'])
@login_required
def api_get_funding(project_id):
    """جلب مصادر التمويل"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    sources = FundingSource.query.filter_by(project_id=project_id).all()
    
    total_funding = sum(s.amount for s in sources)
    
    return jsonify({
        'success': True,
        'sources': [{
            'id': s.id,
            'source_name': s.source_name,
            'amount': s.amount,
            'share_percentage': s.share_percentage,
            'currency': s.currency,
            'status': s.status
        } for s in sources],
        'total_funding': total_funding
    })


@primavera_bp.route('/api/project/<int:project_id>/funding', methods=['POST'])
@login_required
def api_add_funding(project_id):
    """إضافة مصدر تمويل"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        source = FundingSource(
            project_id=project_id,
            source_name=data['source_name'],
            amount=float(data.get('amount', 0)),
            share_percentage=float(data.get('share_percentage', 0)),
            currency=data.get('currency', 'SAR'),
            status=data.get('status', 'Proposed')
        )
        
        db.session.add(source)
        
        # تحديث إجمالي التمويل
        total = sum(s.amount for s in project.funding_sources) + source.amount
        project.total_funding = total
        
        db.session.commit()
        
        return jsonify({'success': True, 'source_id': source.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# Activity Steps APIs
# ============================================


# def check_activity_access(activity_id):
#     """التحقق من صلاحية الوصول للنشاط"""
#     activity = Activity.query.get(activity_id)
    
#     if not activity:
#         return None
    
#     # مدير المنظمة يمكنه الوصول لكل شيء
#     if current_user.role == 'org_admin':
#         return activity
    
#     # مدير المشروع يمكنه الوصول
#     if activity.project and activity.project.project_manager_id == current_user.id:
#         return activity
    
#     # المشرف على النشاط
#     if activity.supervisor_id == current_user.id:
#         return activity
    
#     # المنفذ للنشاط
#     if activity.delegate_id == current_user.id:
#         return activity
    
#     return None


# ============================================
# API لإدارة خطوات النشاط
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/step', methods=['POST'])
@login_required
def api_add_activity_step(activity_id):
    """إضافة خطوة جديدة للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    if not data or not data.get('title'):
        return jsonify({'error': 'عنوان الخطوة مطلوب'}), 400
    
    title = data.get('title').strip()
    description = data.get('description', '').strip()
    
    try:
        # حساب الترتيب الجديد (آخر ترتيب + 1)
        last_step = ActivityStep.query.filter_by(
            activity_id=activity_id
        ).order_by(ActivityStep.order.desc()).first()
        
        new_order = (last_step.order + 1) if last_step else 1
        
        # إنشاء الخطوة الجديدة
        step = ActivityStep(
            activity_id=activity_id,
            order=new_order,
            title=title,
            description=description,
            is_completed=False,
            created_at=datetime.utcnow()
        )
        
        db.session.add(step)
        db.session.commit()
        # ✅ تحديث المؤشرات
        

        return jsonify({
            'success': True,
            'step_id': step.id,
            'step_order': step.order,
            'title': step.title,
            'description': step.description,
            'message': 'تم إضافة الخطوة بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity-step/<int:step_id>/complete', methods=['POST'])
@login_required
def api_complete_activity_step(step_id):
    """تحديد خطوة كمكتملة"""
    step = ActivityStep.query.get_or_404(step_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(step.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if step.is_completed:
        return jsonify({'error': 'الخطوة مكتملة بالفعل'}), 400
    
    try:
        step.is_completed = True
        step.completed_at = datetime.utcnow()
        step.completed_by = current_user.id
        
        db.session.commit()
        # ✅ تحديث المؤشرات
        
        
        # إرسال إشعار
        NotificationService.activity_step_completed(step)
        return jsonify({
            'success': True,
            'message': 'تم إكمال الخطوة بنجاح',
            'completed_at': step.completed_at.isoformat(),
            'completed_by': current_user.full_name
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity-step/<int:step_id>', methods=['DELETE'])
@login_required
def api_delete_activity_step(step_id):
    """حذف خطوة"""
    step = ActivityStep.query.get_or_404(step_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(step.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # حفظ الترتيب الحالي للخطوة
        deleted_order = step.order
        activity_id = step.activity_id
        
        # حذف الخطوة
        db.session.delete(step)
        
        # إعادة ترتيب الخطوات المتبقية
        remaining_steps = ActivityStep.query.filter(
            ActivityStep.activity_id == activity_id,
            ActivityStep.order > deleted_order
        ).order_by(ActivityStep.order).all()
        
        for remaining_step in remaining_steps:
            remaining_step.order -= 1
        
        db.session.commit()
        # ✅ تحديث المؤشرات
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الخطوة بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity-step/<int:step_id>', methods=['PUT'])
@login_required
def api_update_activity_step(step_id):
    """تحديث خطوة (العنوان أو الوصف)"""
    step = ActivityStep.query.get_or_404(step_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(step.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'بيانات غير صالحة'}), 400
    
    try:
        if 'title' in data and data['title'].strip():
            step.title = data['title'].strip()
        
        if 'description' in data:
            step.description = data['description'].strip() if data['description'] else None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'step': {
                'id': step.id,
                'order': step.order,
                'title': step.title,
                'description': step.description,
                'is_completed': step.is_completed
            },
            'message': 'تم تحديث الخطوة بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500



@primavera_bp.route('/api/activity/<int:activity_id>/steps/reorder', methods=['POST'])
@login_required
def api_reorder_activity_steps(activity_id):
    """إعادة ترتيب جميع خطوات النشاط دفعة واحدة"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    new_orders = data.get('orders', [])
    
    if not new_orders:
        return jsonify({'error': 'لم يتم إرسال الترتيب الجديد'}), 400
    
    try:
        # التحقق من أن جميع الخطوات تنتمي لهذا النشاط
        step_ids = [item['id'] for item in new_orders]
        existing_steps = ActivityStep.query.filter(
            ActivityStep.id.in_(step_ids),
            ActivityStep.activity_id == activity_id
        ).all()
        
        if len(existing_steps) != len(step_ids):
            return jsonify({'error': 'بعض الخطوات لا تنتمي لهذا النشاط'}), 400
        
        # تحديث ترتيب كل خطوة
        for order_item in new_orders:
            step = next((s for s in existing_steps if s.id == order_item['id']), None)
            if step:
                step.order = order_item['new_order']
        
        db.session.commit()
        
        # إرجاع القائمة المحدثة
        updated_steps = ActivityStep.query.filter_by(
            activity_id=activity_id
        ).order_by(ActivityStep.order).all()
        
        steps_data = [{
            'id': s.id,
            'order': s.order,
            'title': s.title,
            'description': s.description,
            'is_completed': s.is_completed
        } for s in updated_steps]
        
        return jsonify({
            'success': True,
            'message': 'تم إعادة ترتيب الخطوات بنجاح',
            'steps': steps_data
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/steps', methods=['GET'])
@login_required
def api_get_activity_steps(activity_id):
    """جلب جميع خطوات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        steps = ActivityStep.query.filter_by(
            activity_id=activity_id
        ).order_by(ActivityStep.order).all()
        
        steps_data = []
        completed_count = 0
        
        for step in steps:
            if step.is_completed:
                completed_count += 1
            
            steps_data.append({
                'id': step.id,
                'order': step.order,
                'title': step.title,
                'description': step.description,
                'is_completed': step.is_completed,
                'completed_at': step.completed_at.isoformat() if step.completed_at else None,
                'completed_by': step.completer.full_name if step.completer else None,
                'created_at': step.created_at.isoformat() if step.created_at else None
            })
        
        total_steps = len(steps)
        completion_percentage = (completed_count / total_steps * 100) if total_steps > 0 else 0
        
        return jsonify({
            'success': True,
            'steps': steps_data,
            'total_steps': total_steps,
            'completed_steps': completed_count,
            'completion_percentage': completion_percentage
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/activity/<int:activity_id>/steps', methods=['GET'])
@login_required
def activity_steps_view(activity_id):
    """عرض صفحة خطوات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        flash('غير مصرح', 'danger')
        return redirect(url_for('primavera.dashboard'))
    
    steps = ActivityStep.query.filter_by(
        activity_id=activity_id
    ).order_by(ActivityStep.order).all()
    
    # حساب نسبة الإكمال
    completed_steps = sum(1 for step in steps if step.is_completed)
    steps_completion = int((completed_steps / len(steps) * 100)) if steps else 0
    
    return render_template(
        'primavera/tabs/activity/steps.html',
        activity=activity,
        steps=steps,
        steps_completion=steps_completion,
        now=datetime.now()
    )


@primavera_bp.route('/api/activity/<int:activity_id>/steps/stats', methods=['GET'])
@login_required
def api_get_activity_steps_stats(activity_id):
    """جلب إحصائيات خطوات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        total_steps = ActivityStep.query.filter_by(activity_id=activity_id).count()
        completed_steps = ActivityStep.query.filter_by(
            activity_id=activity_id,
            is_completed=True
        ).count()
        
        return jsonify({
            'success': True,
            'total_steps': total_steps,
            'completed_steps': completed_steps,
            'completion_percentage': (completed_steps / total_steps * 100) if total_steps > 0 else 0
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity-step/<int:step_id>/uncomplete', methods=['POST'])
@login_required
def api_uncomplete_activity_step(step_id):
    """إلغاء إكمال خطوة (إرجاعها إلى حالة غير مكتملة)"""
    step = ActivityStep.query.get_or_404(step_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(step.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if not step.is_completed:
        return jsonify({'error': 'الخطوة غير مكتملة بالفعل'}), 400
    
    try:
        step.is_completed = False
        step.completed_at = None
        step.completed_by = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم إلغاء إكمال الخطوة بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/steps/bulk-complete', methods=['POST'])
@login_required
def api_bulk_complete_steps(activity_id):
    """إكمال مجموعة من الخطوات دفعة واحدة"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    step_ids = data.get('step_ids', [])
    
    if not step_ids:
        return jsonify({'error': 'لم يتم تحديد خطوات'}), 400
    
    try:
        completed_count = 0
        for step_id in step_ids:
            step = ActivityStep.query.get(step_id)
            if step and step.activity_id == activity_id and not step.is_completed:
                step.is_completed = True
                step.completed_at = datetime.utcnow()
                step.completed_by = current_user.id
                completed_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'completed_count': completed_count,
            'message': f'تم إكمال {completed_count} خطوة بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# ============================================
# Activity Expenses APIs
# ============================================


def save_receipt_file(file):
    """حفظ ملف الإيصال وإرجاع المسار"""
    if not file or not file.filename:
        return None
    
    # التحقق من حجم الملف (5MB)
    if file.content_length and file.content_length > 5 * 1024 * 1024:
        return None
    
    # التحقق من نوع الملف
    allowed_extensions = {'pdf', 'jpg', 'jpeg', 'png'}
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    
    if ext not in allowed_extensions:
        return None
    
    # إنشاء اسم فريد للملف
    unique_filename = f"{uuid.uuid4().hex}_{filename}"
    
    # إنشاء المجلد إذا لم يكن موجوداً
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'receipts')
    os.makedirs(upload_folder, exist_ok=True)
    
    # حفظ الملف
    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)
    
    # إرجاع المسار النسبي
    return url_for('static', filename=f'uploads/receipts/{unique_filename}')


# ============================================
# API لإدارة مصروفات النشاط
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/expense', methods=['POST'])
@login_required
def api_add_activity_expense(activity_id):
    """إضافة مصروف جديد للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # معالجة البيانات (FormData)
    expense_date = request.form.get('date')
    category = request.form.get('category')
    description = request.form.get('description')
    amount = request.form.get('amount')
    receipt_file = request.files.get('receipt')
    
    # التحقق من البيانات المطلوبة
    if not expense_date:
        return jsonify({'error': 'تاريخ المصروف مطلوب'}), 400
    if not category:
        return jsonify({'error': 'فئة المصروف مطلوبة'}), 400
    if not description:
        return jsonify({'error': 'وصف المصروف مطلوب'}), 400
    if not amount:
        return jsonify({'error': 'المبلغ مطلوب'}), 400
    
    try:
        amount = float(amount)
        if amount <= 0:
            return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400
    except ValueError:
        return jsonify({'error': 'المبلغ غير صالح'}), 400
    
    # حفظ الإيصال إذا وجد
    receipt_url = None
    if receipt_file:
        receipt_url = save_receipt_file(receipt_file)
        if not receipt_url:
            return jsonify({'error': 'الملف غير مدعوم أو كبير جداً (الحد الأقصى 5MB)'}), 400
    
    try:
        # تحويل تاريخ المصروف
        try:
            expense_date_obj = datetime.strptime(expense_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'error': 'تاريخ غير صالح'}), 400
        
        # إنشاء مصروف جديد
        expense = ActivityExpense(
            activity_id=activity_id,
            expense_date=expense_date_obj,
            category=category,
            description=description,
            amount=amount,
            currency=request.form.get('currency', 'SAR'),
            is_approved=False,
            receipt_url=receipt_url,
            created_at=datetime.utcnow(),
            created_by=current_user.id
        )
        
        db.session.add(expense)
        db.session.commit()

        # ✅ تحديث المؤشرات
        

        # إرجاع البيانات
        return jsonify({
            'success': True,
            'expense': {
                'id': expense.id,
                'expense_date': expense.expense_date.strftime('%Y-%m-%d'),
                'category': expense.category,
                'description': expense.description,
                'amount': expense.amount,
                'currency': expense.currency,
                'is_approved': expense.is_approved,
                'receipt_url': expense.receipt_url,
                'created_at': expense.created_at.isoformat()
            },
            'message': 'تم إضافة المصروف بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/expenses', methods=['GET'])
@login_required
def api_get_activity_expenses(activity_id):
    """جلب جميع مصروفات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        expenses = ActivityExpense.query.filter_by(
            activity_id=activity_id
        ).order_by(ActivityExpense.expense_date.desc()).all()
        
        expenses_data = []
        total_expenses = 0
        approved_expenses = 0
        pending_expenses = 0
        
        for exp in expenses:
            amount = exp.amount
            total_expenses += amount
            
            if exp.is_approved:
                approved_expenses += amount
            else:
                pending_expenses += amount
            
            expenses_data.append({
                'id': exp.id,
                'expense_date': exp.expense_date.strftime('%Y-%m-%d'),
                'category': exp.category,
                'description': exp.description,
                'amount': exp.amount,
                'currency': exp.currency,
                'is_approved': exp.is_approved,
                'receipt_url': exp.receipt_url,
                'created_at': exp.created_at.isoformat(),
                'created_by': exp.creator.full_name if exp.creator else None,
                'approved_at': exp.approved_at.isoformat() if exp.approved_at else None,
                'approved_by': exp.approver.full_name if exp.approver else None
            })
        
        return jsonify({
            'success': True,
            'expenses': expenses_data,
            'total_expenses': total_expenses,
            'approved_expenses': approved_expenses,
            'pending_expenses': pending_expenses,
            'count': len(expenses_data)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/expense/<int:expense_id>/approve', methods=['POST'])
@login_required
def api_approve_expense(expense_id):
    """الموافقة على مصروف"""
    expense = ActivityExpense.query.get_or_404(expense_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(expense.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if expense.is_approved:
        return jsonify({'error': 'المصروف معتمد بالفعل'}), 400
    
    try:
        expense.is_approved = True
        expense.approved_by = current_user.id
        expense.approved_at = datetime.utcnow()
        
        db.session.commit()

        # ✅ تحديث المؤشرات (خاصة التكاليف)
        

        return jsonify({
            'success': True,
            'message': 'تم اعتماد المصروف بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/expense/<int:expense_id>', methods=['DELETE'])
@login_required
def api_delete_expense(expense_id):
    """حذف مصروف"""
    expense = ActivityExpense.query.get_or_404(expense_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(expense.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # يمكن حذف المصروفات غير المعتمدة فقط
    if expense.is_approved:
        return jsonify({'error': 'لا يمكن حذف مصروف معتمد'}), 400
    
    try:
        # حذف ملف الإيصال إذا وجد
        if expense.receipt_url:
            file_path = os.path.join(current_app.root_path, 'static', expense.receipt_url.replace('/static/', ''))
            if os.path.exists(file_path):
                os.remove(file_path)
        
        db.session.delete(expense)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف المصروف بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/expense/<int:expense_id>', methods=['PUT'])
@login_required
def api_update_expense(expense_id):
    """تحديث مصروف (للمصروفات غير المعتمدة فقط)"""
    expense = ActivityExpense.query.get_or_404(expense_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(expense.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if expense.is_approved:
        return jsonify({'error': 'لا يمكن تعديل مصروف معتمد'}), 400
    
    data = request.get_json()
    
    try:
        if 'description' in data:
            expense.description = data['description']
        if 'amount' in data:
            amount = float(data['amount'])
            if amount <= 0:
                return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400
            expense.amount = amount
        if 'category' in data:
            expense.category = data['category']
        if 'expense_date' in data:
            expense.expense_date = datetime.strptime(data['expense_date'], '%Y-%m-%d').date()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'expense': {
                'id': expense.id,
                'expense_date': expense.expense_date.strftime('%Y-%m-%d'),
                'category': expense.category,
                'description': expense.description,
                'amount': expense.amount,
                'is_approved': expense.is_approved
            },
            'message': 'تم تحديث المصروف بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/activity/<int:activity_id>/expenses/stats', methods=['GET'])
@login_required
def api_get_expense_stats(activity_id):
    """جلب إحصائيات المصروفات للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
        
        total = 0
        approved = 0
        pending = 0
        categories = {}
        
        for exp in expenses:
            total += exp.amount
            if exp.is_approved:
                approved += exp.amount
            else:
                pending += exp.amount
            
            if exp.category not in categories:
                categories[exp.category] = 0
            categories[exp.category] += exp.amount
        
        return jsonify({
            'success': True,
            'total_expenses': total,
            'approved_expenses': approved,
            'pending_expenses': pending,
            'categories': categories,
            'count': len(expenses)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@primavera_bp.route('/api/expense/<int:expense_id>/receipt', methods=['DELETE'])
@login_required
def api_delete_receipt(expense_id):
    """حذف إيصال المصروف"""
    expense = ActivityExpense.query.get_or_404(expense_id)
    
    # التحقق من صلاحية الوصول للنشاط المرتبط
    activity = check_activity_access(expense.activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if expense.is_approved:
        return jsonify({'error': 'لا يمكن حذف إيصال مصروف معتمد'}), 400
    
    try:
        if expense.receipt_url:
            file_path = os.path.join(current_app.root_path, 'static', expense.receipt_url.replace('/static/', ''))
            if os.path.exists(file_path):
                os.remove(file_path)
            expense.receipt_url = None
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم حذف الإيصال بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# صفحة عرض المصروفات (GET)
# ============================================

@primavera_bp.route('/activity/<int:activity_id>/expenses', methods=['GET'])
@login_required
def activity_expenses_view(activity_id):
    """عرض صفحة مصروفات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        flash('غير مصرح', 'danger')
        return redirect(url_for('primavera.dashboard'))
    
    expenses = ActivityExpense.query.filter_by(
        activity_id=activity_id
    ).order_by(ActivityExpense.expense_date.desc()).all()
    
    # حساب الإحصائيات
    total_expenses = sum(e.amount for e in expenses)
    approved_expenses = sum(e.amount for e in expenses if e.is_approved)
    pending_expenses = total_expenses - approved_expenses
    
    return render_template(
        'primavera/tabs/activity/expenses.html',
        activity=activity,
        expenses=expenses,
        total_expenses=total_expenses,
        approved_expenses=approved_expenses,
        pending_expenses=pending_expenses,
        now=datetime.now()
    )
# ============================================
# Relationship APIs
# ============================================

@primavera_bp.route('/api/activity/<int:activity_id>/predecessor', methods=['POST'])
@login_required
def api_add_predecessor(activity_id):
    """إضافة علاقة سابقة"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم وجود علاقة دائرية
        if would_create_circular_relationship(data['predecessor_id'], activity_id):
            return jsonify({'success': False, 'error': 'Circular relationship detected'}), 400
        
        # التحقق من عدم وجود علاقة مكررة
        existing = ActivityRelationship.query.filter_by(
            project_id=activity.project_id,
            predecessor_id=data['predecessor_id'],
            successor_id=activity_id
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'Relationship already exists'}), 400
        
        relationship = ActivityRelationship(
            project_id=activity.project_id,
            predecessor_id=data['predecessor_id'],
            successor_id=activity_id,
            relationship_type=data.get('relationship_type', 'FS'),
            lag_days=float(data.get('lag', 0)),
            lag_type=data.get('lag_type', 'days')
        )
        
        db.session.add(relationship)
        db.session.commit()
        
        return jsonify({'success': True, 'relationship_id': relationship.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500



@primavera_bp.route('/api/relationship/<int:rel_id>', methods=['PUT'])
@login_required
def api_update_relationship(rel_id):
    """تحديث علاقة"""
    rel = ActivityRelationship.query.get_or_404(rel_id)
    
    if not check_project_access(rel.project_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if 'relationship_type' in data:
            rel.relationship_type = data['relationship_type']
        if 'lag' in data:
            rel.lag_days = float(data['lag'])
        if 'lag_type' in data:
            rel.lag_type = data['lag_type']
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500



@primavera_bp.route('/api/relationship/<int:rel_id>', methods=['DELETE'])
@login_required
def api_delete_relationship(rel_id):
    """حذف علاقة"""
    rel = ActivityRelationship.query.get_or_404(rel_id)
    project_id = rel.project_id
    if not check_project_access(rel.project_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(rel)
        db.session.commit()
        # ✅ تحديث المؤشرات (المسار الحرج يتغير)
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

def would_create_circular_relationship(pred_id, succ_id, visited=None):
    """التحقق من عدم إنشاء علاقة دائرية"""
    if visited is None:
        visited = set()
    
    if succ_id in visited:
        return True
    
    visited.add(succ_id)
    
    # الحصول على جميع العلاقات التي تبدأ من succ_id
    relationships = ActivityRelationship.query.filter_by(predecessor_id=succ_id).all()
    
    for rel in relationships:
        if rel.successor_id == pred_id:
            return True
        if would_create_circular_relationship(pred_id, rel.successor_id, visited):
            return True
    
    return False

@primavera_bp.route('/api/activity/<int:activity_id>/relationships', methods=['GET'])
@login_required
def api_get_activity_relationships(activity_id):
    """جلب علاقات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'error': 'غير مصرح'}), 403
    
    predecessors = ActivityRelationship.query.filter_by(successor_id=activity_id).all()
    successors = ActivityRelationship.query.filter_by(predecessor_id=activity_id).all()
    
    return jsonify({
        'success': True,
        'predecessors': [{
            'id': r.id,
            'activity_id': r.predecessor.activity_id,
            'activity_name': r.predecessor.activity_name,
            'relationship_type': r.relationship_type,
            'lag_days': r.lag_days,
            'lag_type': r.lag_type,
            'is_driving': r.is_driving,
            'is_critical': r.is_critical
        } for r in predecessors],
        'successors': [{
            'id': r.id,
            'activity_id': r.successor.activity_id,
            'activity_name': r.successor.activity_name,
            'relationship_type': r.relationship_type,
            'lag_days': r.lag_days,
            'lag_type': r.lag_type,
            'is_driving': r.is_driving,
            'is_critical': r.is_critical
        } for r in successors]
    })

# ============================================
# Calculation APIs
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/earned-value', methods=['GET'])
@login_required
def api_calculate_earned_value(project_id):
    """حساب القيمة المكتسبة"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    # حساب القيم
    planned_value = sum(a.planned_value or 0 for a in activities)
    earned_value = sum(a.earned_value or 0 for a in activities)
    actual_cost = sum(a.actual_cost or 0 for a in activities)
    
    # حساب المؤشرات
    spi = earned_value / planned_value if planned_value > 0 else 1
    cpi = earned_value / actual_cost if actual_cost > 0 else 1
    
    # تحديث المشروع
    project.earned_value = earned_value
    project.planned_value = planned_value
    project.actual_cost = actual_cost
    project.spi = spi
    project.cpi = cpi
    project.csi = spi * cpi
    
    # حساب التوقعات
    if cpi > 0:
        project.eac = actual_cost + (planned_value - earned_value) / cpi
        project.etc = (planned_value - earned_value) / cpi
        project.vac = planned_value - project.eac
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'planned_value': planned_value,
        'earned_value': earned_value,
        'actual_cost': actual_cost,
        'spi': spi,
        'cpi': cpi,
        'csi': project.csi,
        'eac': project.eac,
        'etc': project.etc,
        'vac': project.vac
    })

# ============================================
# Project Dashboard Stats API
# ============================================

@primavera_bp.route('/api/project/<int:project_id>/dashboard-stats', methods=['GET'])
@login_required
def api_project_dashboard_stats(project_id):
    """إحصائيات لوحة تحكم المشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # إحصائيات الأنشطة
        activities = Activity.query.filter_by(project_id=project_id).all()
        
        # إحصائيات الميزانية
        budget_logs = BudgetLog.query.filter_by(project_id=project_id).all()
        spending_items = SpendingPlanItem.query.filter_by(project_id=project_id).all()
        funding_sources = FundingSource.query.filter_by(project_id=project_id).all()
        
        # إحصائيات الملاحظات
        notebook_entries = NotebookEntry.query.filter_by(project_id=project_id).all()
        
        return jsonify({
            'success': True,
            'stats': {
                'activities': {
                    'total': len(activities),
                    'completed': len([a for a in activities if a.status == 'Completed']),
                    'in_progress': len([a for a in activities if a.status == 'In Progress']),
                    'not_started': len([a for a in activities if a.status == 'Not Started']),
                    'critical': len([a for a in activities if a.is_critical])
                },
                'budget': {
                    'original': project.project.original_budget or 0,
                    'current': project.project.current_budget or project.project.total_planned_cost or 0,
                    'actual': project.project.total_actual_cost or 0,
                    'changes': len(budget_logs),
                    'funding_sources': len(funding_sources),
                    'total_funding': sum(f.amount for f in funding_sources)
                },
                'schedule': {
                    'planned_start': project.project.planned_start.isoformat() if project.planned_start else None,
                    'planned_finish': project.project.planned_finish.isoformat() if project.planned_finish else None,
                    'actual_start': project.project.actual_start.isoformat() if project.actual_start else None,
                    'actual_finish': project.project.actual_finish.isoformat() if project.actual_finish else None,
                    'progress': project.project.progress_percentage or 0,
                    'remaining_days': project.remaining_days
                },
                'notebook': {
                    'total': len(notebook_entries),
                    'recent': len([n for n in notebook_entries if (datetime.utcnow() - n.created_at).days < 7])
                },
                'performance': {
                    'spi': project.project.spi or 1,
                    'cpi': project.project.cpi or 1,
                    'csi': project.project.csi or 1
                }
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@primavera_bp.route('/api/project/<int:project_id>/schedule', methods=['POST'])
@login_required
def api_run_schedule(project_id):
    """تشغيل الجدولة"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        from app.services.primavera_engine import PrimaveraEngine
        engine = PrimaveraEngine(project)
        result = engine.run_schedule()
        
        return jsonify({
            'success': True,
            'result': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@primavera_bp.route('/api/project/<int:project_id>/budget-summary', methods=['GET'])
@login_required
def api_budget_summary(project_id):
    """الحصول على ملخص الميزانية"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # حساب الميزانية الموزعة على الأنشطة
        activities = Activity.query.filter_by(project_id=project_id).all()
        distributed_budget = sum(a.planned_cost or 0 for a in activities)
        
        # الميزانية الحالية
        current_budget = project.project.current_budget or project.total_planned_cost or 0
        
        # الميزانية غير المخصصة
        unallocated_budget = current_budget - distributed_budget
        
        # التكلفة الفعلية
        actual_cost = project.project.total_actual_cost or 0
        
        # الفرق الحالي
        current_variance = current_budget - actual_cost
        variance_percentage = (current_variance / current_budget * 100) if current_budget > 0 else 0
        
        # إجمالي خطة الصرف والفوائد
        spending_items = SpendingPlanItem.query.filter_by(project_id=project_id).all()
        total_spending_plan = sum(i.planned_amount for i in spending_items)
        total_benefit_plan = sum(i.benefit_amount for i in spending_items)
        
        return jsonify({
            'success': True,
            'data': {
                'current_budget': current_budget,
                'unallocated_budget': max(0, unallocated_budget),
                'distributed_budget': distributed_budget,
                'actual_cost': actual_cost,
                'current_variance': current_variance,
                'variance_percentage': variance_percentage,
                'total_spending_plan': total_spending_plan,
                'total_benefit_plan': total_benefit_plan,
                'budget_breakdown': {
                    'allocated': distributed_budget,
                    'unallocated': max(0, unallocated_budget),
                    'actual': actual_cost
                }
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@primavera_bp.route('/api/project/<int:project_id>/settings', methods=['GET', 'POST'])
@login_required
def api_project_settings(project_id):
    """إدارة إعدادات المشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'settings': {
                'last_summarized': project.last_summarized.isoformat() if project.last_summarized else None,
                'summarize_level': project.summarize_level or 1,
                'fiscal_year_start': project.fiscal_year_start or '01-01',
                'baseline_ev_id': project.baseline_ev_id,
                'critical_definition': project.critical_definition or 'Total Float <= 0',
                'schedule_method': project.schedule_method or 'cpm',
                'priority': project.priority_level,
                'risk_level': project.risk_level
            }
        })
    
    else:  # POST
        data = request.get_json()
        try:
            if 'last_summarized' in data:
                project.last_summarized = datetime.strptime(data['last_summarized'], '%Y-%m-%d')
            if 'summarize_level' in data:
                project.summarize_level = int(data['summarize_level'])
            if 'fiscal_year_start' in data:
                project.fiscal_year_start = data['fiscal_year_start']
            if 'baseline_ev_id' in data:
                project.baseline_ev_id = data['baseline_ev_id']
            if 'critical_definition' in data:
                project.critical_definition = data['critical_definition']
            
            db.session.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
        
@primavera_bp.route('/api/project/<int:project_id>/defaults', methods=['GET', 'POST'])
@login_required
def api_project_defaults(project_id):
    """إدارة القيم الافتراضية للمشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # هذه الإعدادات يمكن تخزينها في JSON field في المشروع
    defaults = project.defaults or {}
    
    if request.method == 'GET':
        return jsonify({
            'success': True,
            'defaults': {
                'duration_type': defaults.get('duration_type', 'Fixed Duration'),
                'percent_complete_type': defaults.get('percent_complete_type', 'Duration'),
                'calendar_id': defaults.get('calendar_id'),
                'activity_type': defaults.get('activity_type', 'Task Dependent'),
                'rate_type': defaults.get('rate_type', 'Standard Rate'),
                'drive_activity_dates': defaults.get('drive_activity_dates', False)
            }
        })
    
    else:  # POST
        data = request.get_json()
        try:
            # تحديث القيم الافتراضية
            if not project.defaults:
                project.defaults = {}
            
            for key, value in data.items():
                project.defaults[key] = value
            
            db.session.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
        
@primavera_bp.route('/api/project/<int:project_id>/codes', methods=['GET', 'POST'])
@login_required
def api_project_codes(project_id):
    """إدارة أكواد المشروع"""
    project = check_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if request.method == 'GET':
        # جلب جميع أنواع الأكواد المتاحة للمؤسسة
        code_types = db.session.query(ActivityCode.code_type).distinct().all()
        
        available_codes = {}
        for code_type in code_types:
            codes = ActivityCode.query.filter_by(
                org_id=project.eps.org_id,
                code_type=code_type[0]
            ).all()
            available_codes[code_type[0]] = [{
                'id': c.id,
                'value': c.code_value,
                'description': c.code_description,
                'color': c.code_color
            } for c in codes]
        
        return jsonify({
            'success': True,
            'selected_codes': project.priority_level.activity_code_values or {},
            'available_codes': available_codes
        })
    
    else:  # POST
        data = request.get_json()
        try:
            # تحديث الأكواد المحددة
            if not project.project.activity_code_values:
                project.project.activity_code_values = {}
            
            for code_type, value in data.items():
                project.project.activity_code_values[code_type] = value
            
            db.session.commit()
            return jsonify({'success': True})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500
        
# ============================================
# دوال مساعدة جديدة
# ============================================

def get_project_budget_summary(project_id):
    """الحصول على ملخص ميزانية المشروع"""
    project = Project.query.get(project_id)
    if not project:
        return None
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    distributed_budget = sum(a.planned_cost or 0 for a in activities)
    current_budget = project.current_budget or project.total_planned_cost or 0
    unallocated_budget = current_budget - distributed_budget
    
    return {
        'current_budget': current_budget,
        'unallocated_budget': max(0, unallocated_budget),
        'distributed_budget': distributed_budget,
        'actual_cost': project.total_actual_cost or 0,
        'current_variance': current_budget - (project.total_actual_cost or 0)
    }


def get_activity_progress_stats(activity_id):
    """إحصائيات تقدم النشاط"""
    activity = Activity.query.get(activity_id)
    if not activity:
        return None
    
    steps = ActivityStep.query.filter_by(activity_id=activity_id).all()
    expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
    
    steps_completed = sum(1 for s in steps if s.is_completed)
    total_expenses = sum(e.amount for e in expenses)
    
    return {
        'steps': {
            'total': len(steps),
            'completed': steps_completed,
            'percentage': (steps_completed / len(steps) * 100) if steps else 0
        },
        'expenses': {
            'total': total_expenses,
            'approved': sum(e.amount for e in expenses if e.is_approved),
            'count': len(expenses)
        },
        'progress': activity.progress_percentage or 0,
        'remaining_duration': activity.remaining_duration or 0,
        'total_float': activity.total_float or 0
    }


def calculate_activity_earned_value(activity_id):
    """حساب القيمة المكتسبة لنشاط"""
    activity = Activity.query.get(activity_id)
    if not activity:
        return None
    
    # القيمة المخططة (بناءً على المدة)
    if activity.original_duration and activity.planned_value:
        planned_value = activity.planned_value
    else:
        planned_value = activity.original_duration * 100  # قيمة افتراضية
    
    # القيمة المكتسبة (بناءً على التقدم)
    earned_value = planned_value * (activity.progress_percentage / 100)
    
    # التكلفة الفعلية
    actual_cost = activity.actual_cost or 0
    
    return {
        'planned_value': planned_value,
        'earned_value': earned_value,
        'actual_cost': actual_cost,
        'sv': earned_value - planned_value,
        'cv': earned_value - actual_cost,
        'spi': earned_value / planned_value if planned_value > 0 else 1,
        'cpi': earned_value / actual_cost if actual_cost > 0 else 1
    }

@primavera_bp.route('/eps-view')
@login_required
def eps_view_alternative():
    """عرض هيكل EPS مع خيارات العرض المختلفة (شجرة/جدول)"""
    org_id = get_org_id()
    
    # جلب جميع عناصر EPS
    if org_id:
        eps_nodes = EPS.query.filter_by(org_id=org_id).order_by(EPS.level, EPS.eps_code).all()
    else:
        eps_nodes = EPS.query.order_by(EPS.level, EPS.eps_code).all()
    
    # تجهيز البيانات للعرض
    eps_data = []
    for node in eps_nodes:
        # عدد المشاريع
        projects_count = node.projects.count() if hasattr(node, 'projects') else 0
        
        # المسار الكامل
        full_path = node.name
        if node.parent:
            full_path = f"{node.parent.name} / {node.name}"
        
        # الميزانية الإجمالية
        total_budget = 0
        if hasattr(node, 'projects'):
            for project in node.projects:
                if hasattr(project, 'total_planned_cost'):
                    total_budget += project.total_planned_cost or 0
        
        eps_data.append({
            'id': node.id,
            'eps_code': node.eps_code,
            'name': node.name,
            'description': node.description or '',
            'level': node.level,
            'parent_id': node.parent_id,
            'parent_name': node.parent.name if node.parent else None,
            'full_path': full_path,
            'projects_count': projects_count,
            'total_budget': total_budget,
            'manager_name': node.manager.full_name if node.manager else 'غير محدد',
            'created_at': node.created_at.strftime('%Y-%m-%d') if node.created_at else '',
            'is_active': node.is_active if hasattr(node, 'is_active') else True
        })
    
    # بناء هيكل الشجرة
    def build_tree(parent_id=None):
        tree = []
        for node in eps_data:
            if node['parent_id'] == parent_id:
                children = build_tree(node['id'])
                if children:
                    node['children'] = children
                tree.append(node)
        return tree
    
    tree_data = build_tree()
    
    # إحصائيات
    total_eps = len(eps_data)
    total_projects = sum(node['projects_count'] for node in eps_data)
    total_budget = sum(node['total_budget'] for node in eps_data)
    root_nodes = len([n for n in eps_data if n['parent_id'] is None])
    
    stats = {
        'total_eps': total_eps,
        'total_projects': total_projects,
        'total_budget': total_budget,
        'root_nodes': root_nodes,
        'avg_projects_per_eps': round(total_projects / total_eps, 1) if total_eps > 0 else 0
    }
    
    return render_template('primavera/eps_view2.html',
                         eps_data=eps_data,
                         tree_data=tree_data,
                         stats=stats,
                         now=datetime.now())

@primavera_bp.route('/eps/<int:eps_id>/projects')
@login_required
def eps_projects(eps_id):
    """عرض مشاريع EPS محدد"""
    eps = check_eps_access(eps_id)
    if not eps:
        return redirect(url_for('primavera.eps_view_alternative'))
    
    projects = Project.query.filter_by(eps_id=eps_id).all()
    
    return render_template('primavera/eps_projects.html',
                         eps=eps,
                         projects=projects,
                         now=datetime.now())

@primavera_bp.route('/api/eps/<int:eps_id>/stats')
@login_required
def api_eps_stats(eps_id):
    """API لإحصائيات EPS"""
    eps = check_eps_access(eps_id)
    if not eps:
        return jsonify({'error': 'غير مصرح'}), 403
    
    projects = Project.query.filter_by(eps_id=eps_id).all()
    
    stats = {
        'total_projects': len(projects),
        'active_projects': len([p for p in projects if p.status == 'active']),
        'completed_projects': len([p for p in projects if p.status == 'completed']),
        'total_budget': sum(p.total_planned_cost or 0 for p in projects),
        'total_activities': sum(p.activities.count() for p in projects if hasattr(p, 'activities')),
        'avg_progress': sum(p.progress or 0 for p in projects) / len(projects) if projects else 0
    }
    
    return jsonify(stats)
@primavera_bp.route('/project/<int:project_id>/activities')
@login_required
def project_activities(project_id):
    """عرض أنشطة المشروع"""
    project = check_project_access(project_id)
    if not project:
        return redirect(url_for('primavera.projects_list'))
    
    activities = Activity.query.filter_by(project_id=project_id).order_by(Activity.activity_id).all()
    
    # إحصائيات الأنشطة
    total = len(activities)
    completed = len([a for a in activities if a.status == 'completed'])
    in_progress = len([a for a in activities if a.status == 'in_progress'])
    not_started = len([a for a in activities if a.status == 'not_started'])
    critical = len([a for a in activities if a.is_critical])
    
    stats = {
        'total': total,
        'completed': completed,
        'in_progress': in_progress,
        'not_started': not_started,
        'critical': critical,
        'completion_rate': (completed / total * 100) if total > 0 else 0
    }
    
    return render_template('primavera/project_activities.html',
                         project=project,
                         activities=activities,
                         stats=stats,
                         now=datetime.now())

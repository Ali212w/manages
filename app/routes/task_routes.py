"""
task_routes.py - مسارات إدارة المهام المتكاملة
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session,g,current_app
from flask_login import login_required, current_user
from app.models import db
from app.models import (
    Task, TaskPlanning, TaskExecution, TaskProgress,
    TaskLocation, TaskVerification, TaskAssignment, 
    TaskResource, TaskDependency, TaskRequirement,
    TaskRequirementVerification, TaskSafetyCheck,
    TaskMaterialCheck, TaskTeamBriefing, TaskProgressUpdate,
    DailyReport, DailyReportTask, DailyReportPhoto,ResourceDelivery,
    Issue, QualityCheck,Meeting,
    Project, Activity, User, Resource,Organization,Notification
)
from datetime import datetime, date,timedelta
import uuid
import os
from app.routes import task_bp
from werkzeug.utils import secure_filename
from app.services.update_service import UpdateService


# ============================================
# دوال مساعدة
# ============================================
@task_bp.before_request
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

def check_task_access(task_id):
    """التحقق من صلاحية الوصول للمهمة"""
    task = Task.query.get_or_404(task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return None
    return task

def would_create_circular_task_relationship(pred_id, succ_id, visited=None):
    """التحقق من عدم إنشاء علاقة دائرية في المهام"""
    if visited is None:
        visited = set()
    
    if succ_id in visited:
        return True
    
    visited.add(succ_id)
    
    dependencies = TaskDependency.query.filter_by(predecessor_task_id=succ_id).all()
    
    for dep in dependencies:
        if dep.successor_task_id == pred_id:
            return True
        if would_create_circular_task_relationship(pred_id, dep.successor_task_id, visited):
            return True
    
    return False

def get_task_statistics(project_id):
    """الحصول على إحصائيات المهام للمشروع"""
    tasks = Task.query.filter_by(project_id=project_id).all()
    
    return {
        'total': len(tasks),
        'pending': sum(1 for t in tasks if t.status == 'pending'),
        'in_progress': sum(1 for t in tasks if t.status == 'in_progress'),
        'completed': sum(1 for t in tasks if t.status == 'completed'),
        'on_hold': sum(1 for t in tasks if t.status == 'on_hold'),
        'cancelled': sum(1 for t in tasks if t.status == 'cancelled'),
        'overdue': sum(1 for t in tasks if t.is_delayed())
    }

def get_user_tasks(user_id, status=None):
    """الحصول على مهام مستخدم معين"""
    query = TaskAssignment.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status)
    
    assignments = query.all()
    return [a.task for a in assignments if a.task]

# ============================================
# صفحات المهام
# ============================================

@task_bp.route('/')
@login_required
def list_tasks():
    """عرض قائمة المهام"""
    project_id = request.args.get('project_id')
    activity_id = request.args.get('activity_id')
    view = request.args.get('view', 'all')  # all, my_tasks, overdue, assigned
    
    query = Task.query.join(Project).filter(Project.created_by == current_user.id)
    
    if project_id:
        query = query.filter(Task.project_id == project_id)
    if activity_id:
        query = query.filter(Task.activity_id == activity_id)
    
    tasks = query.order_by(Task.task_order).all()
    
    # تصفية حسب view
    if view == 'my_tasks':
        # المهام التي أنشأها المستخدم أو المشرف عليها
        tasks = [t for t in tasks if t.created_by == current_user.id or t.supervisor_id == current_user.id]
    elif view == 'assigned':
        # المهام المعينة للمستخدم
        assigned_task_ids = [a.task_id for a in TaskAssignment.query.filter_by(user_id=current_user.id)]
        tasks = [t for t in tasks if t.id in assigned_task_ids]
    elif view == 'overdue':
        tasks = [t for t in tasks if t.is_delayed()]
    
    # إحصائيات
    stats = get_task_statistics(project_id) if project_id else get_task_statistics(None)
    
    project = Project.query.get(project_id) if project_id else None
    activity = Activity.query.get(activity_id) if activity_id else None
    
    # قائمة المشاريع للفلترة
    projects = Project.query.filter_by(created_by=current_user.id).all()
    
    return render_template('tasks/list.html',
                         tasks=tasks,
                         stats=stats,
                         project=project,
                         activity=activity,
                         projects=projects,
                         view=view)


@task_bp.route('/my-tasks')
@login_required
def my_tasks():
    """عرض المهام الخاصة بي"""
    return redirect(url_for('tasks.list_tasks', view='my_tasks'))


@task_bp.route('/assigned-to-me')
@login_required
def assigned_to_me():
    """عرض المهام المعينة لي"""
    return redirect(url_for('tasks.list_tasks', view='assigned'))


@task_bp.route('/overdue')
@login_required
def overdue_tasks():
    """عرض المهام المتأخرة"""
    return redirect(url_for('tasks.list_tasks', view='overdue'))


@task_bp.route('/<int:task_id>')
@login_required
def task_detail(task_id):
    """عرض تفاصيل المهمة"""
    task = check_task_access(task_id)
    if not task:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('tasks.list_tasks'))
    
    # جلب البيانات المرتبطة
    users = User.query.filter_by(org_id=current_user.org_id).all()
    resources = Resource.query.filter_by(org_id=current_user.org_id).all()
    all_tasks = Task.query.filter_by(project_id=task.project_id).all()
    
    # التبعيات
    predecessors = TaskDependency.query.filter_by(successor_task_id=task_id).all()
    successors = TaskDependency.query.filter_by(predecessor_task_id=task_id).all()
    
    # التعيينات
    assignments = TaskAssignment.query.filter_by(task_id=task_id).all()
    
    # الموارد
    task_resources = TaskResource.query.filter_by(task_id=task_id).all()
    
    # المتطلبات
    requirements = TaskRequirement.query.filter_by(task_id=task_id, is_active=True).order_by(TaskRequirement.order).all()
    
    # فحوصات السلامة
    safety_checks = TaskSafetyCheck.query.filter_by(task_id=task_id).all()
    
    # فحوصات المواد
    material_checks = TaskMaterialCheck.query.filter_by(task_id=task_id).all()
    
    # تحديثات التقدم
    progress_updates = TaskProgressUpdate.query.filter_by(task_id=task_id).order_by(TaskProgressUpdate.updated_at.desc()).limit(10).all()
    
    # القضايا المرتبطة
    issues = Issue.query.filter_by(task_id=task_id).all()
    
    # فحوصات الجودة
    quality_checks = QualityCheck.query.filter_by(task_id=task_id).all()
    
    return render_template('tasks/detail.html',
                         task=task,
                         users=users,
                         resources=resources,
                         all_tasks=all_tasks,
                         predecessors=predecessors,
                         successors=successors,
                         assignments=assignments,
                         task_resources=task_resources,
                         requirements=requirements,
                         safety_checks=safety_checks,
                         material_checks=material_checks,
                         progress_updates=progress_updates,
                         issues=issues,
                         quality_checks=quality_checks)


@task_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_task():
    """إنشاء مهمة جديدة"""
    if request.method == 'POST':
        try:
            project_id = request.form.get('project_id')
            activity_id = request.form.get('activity_id') or None
            
            # إنشاء كود المهمة تلقائياً
            last_task = Task.query.filter_by(project_id=project_id).order_by(Task.id.desc()).first()
            if last_task and last_task.task_code:
                last_num = int(last_task.task_code[1:]) if last_task.task_code[0] == 'T' else 1000
                task_code = f"T{last_num + 1}"
            else:
                task_code = "T1000"
            
            # إنشاء المهمة الرئيسية
            task = Task(
                project_id=project_id,
                activity_id=activity_id,
                wbs_id=request.form.get('wbs_id') or None,
                task_code=task_code,
                task_name=request.form.get('task_name'),
                description=request.form.get('description'),
                instructions=request.form.get('instructions'),
                task_order=int(request.form.get('task_order', 1)),
                depends_on_task_id=request.form.get('depends_on_task_id') or None,
                supervisor_id=request.form.get('supervisor_id'),
                delegate_id=request.form.get('delegate_id') or None,
                priority=int(request.form.get('priority', 3)),
                status='pending',
                assigned_users=request.form.getlist('assigned_users'),
                created_by=current_user.id,
                uuid=str(uuid.uuid4())
            )
            db.session.add(task)
            db.session.flush()
            
            # إنشاء التخطيط
            planning = TaskPlanning(
                task_id=task.id,
                planned_start=datetime.strptime(request.form.get('planned_start'), '%Y-%m-%d').date() if request.form.get('planned_start') else None,
                planned_finish=datetime.strptime(request.form.get('planned_finish'), '%Y-%m-%d').date() if request.form.get('planned_finish') else None,
                planned_duration=float(request.form.get('planned_duration', 0)) if request.form.get('planned_duration') else None,
                estimated_effort=float(request.form.get('estimated_effort', 0)) if request.form.get('estimated_effort') else None
            )
            db.session.add(planning)
            
            # إنشاء التقدم
            progress = TaskProgress(task_id=task.id)
            db.session.add(progress)
            
            # إنشاء التنفيذ
            execution = TaskExecution(task_id=task.id)
            db.session.add(execution)
            
            # إنشاء الموقع إذا وجد
            if request.form.get('location'):
                location = TaskLocation(
                    task_id=task.id,
                    location=request.form.get('location'),
                    coordinates=request.form.get('coordinates')
                )
                db.session.add(location)
            
            db.session.commit()
            
            flash('تم إنشاء المهمة بنجاح', 'success')
            return redirect(url_for('tasks.task_detail', task_id=task.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # بيانات النموذج
    project_id = request.args.get('project_id')
    activity_id = request.args.get('activity_id')
    
    project = Project.query.get(project_id) if project_id else None
    activity = Activity.query.get(activity_id) if activity_id else None
    
    projects = Project.query.filter_by(created_by=current_user.id).all()
    activities = Activity.query.filter_by(project_id=project_id).all() if project_id else []
    users = User.query.filter_by(org_id=current_user.org_id).all()
    tasks = Task.query.filter_by(project_id=project_id).all() if project_id else []
    
    return render_template('tasks/create.html',
                         project=project,
                         activity=activity,
                         projects=projects,
                         activities=activities,
                         users=users,
                         tasks=tasks,now=datetime.now())


@task_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """تعديل مهمة"""
    task = check_task_access(task_id)
    if not task:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('tasks.list_tasks'))
    
    if request.method == 'POST':
        try:
            # تحديث المعلومات الأساسية
            task.task_name = request.form.get('task_name', task.task_name)
            task.description = request.form.get('description', task.description)
            task.instructions = request.form.get('instructions', task.instructions)
            task.priority = int(request.form.get('priority', task.priority))
            task.activity_id = request.form.get('activity_id') or None
            task.delegate_id = request.form.get('delegate_id') or None
            task.assigned_users = request.form.getlist('assigned_users')
            
            # تحديث التخطيط
            if task.planning:
                task.planning.planned_start = datetime.strptime(request.form.get('planned_start'), '%Y-%m-%d').date() if request.form.get('planned_start') else None
                task.planning.planned_finish = datetime.strptime(request.form.get('planned_finish'), '%Y-%m-%d').date() if request.form.get('planned_finish') else None
                task.planning.planned_duration = float(request.form.get('planned_duration', 0)) if request.form.get('planned_duration') else None
                task.planning.estimated_effort = float(request.form.get('estimated_effort', 0)) if request.form.get('estimated_effort') else None
            
            # تحديث الموقع
            if task.location_rel:
                task.location_rel.location = request.form.get('location', task.location_rel.location)
                task.location_rel.coordinates = request.form.get('coordinates', task.location_rel.coordinates)
            elif request.form.get('location'):
                location = TaskLocation(
                    task_id=task.id,
                    location=request.form.get('location'),
                    coordinates=request.form.get('coordinates')
                )
                db.session.add(location)
            
            db.session.commit()
            
            flash('تم تحديث المهمة بنجاح', 'success')
            return redirect(url_for('tasks.task_detail', task_id=task.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # بيانات النموذج
    projects = Project.query.filter_by(created_by=current_user.id).all()
    activities = Activity.query.filter_by(project_id=task.project_id).all() if task.project_id else []
    users = User.query.filter_by(org_id=current_user.org_id).all()
    tasks = Task.query.filter_by(project_id=task.project_id).all() if task.project_id else []
    
    return render_template('tasks/edit.html',
                         task=task,
                         projects=projects,
                         activities=activities,
                         users=users,
                         tasks=tasks)


@task_bp.route('/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """حذف مهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        # التحقق من عدم وجود مهام تابعة
        successors = Task.query.filter_by(depends_on_task_id=task_id).count()
        if successors > 0:
            return jsonify({'success': False, 'error': 'لا يمكن حذف المهمة لأن هناك مهام تعتمد عليها'}), 400
        
        db.session.delete(task)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للمهام
# ============================================

@task_bp.route('/api/list')
@login_required
def api_task_list():
    """API لقائمة المهام"""
    project_id = request.args.get('project_id')
    activity_id = request.args.get('activity_id')
    
    query = Task.query.join(Project).filter(Project.created_by == current_user.id)
    
    if project_id:
        query = query.filter(Task.project_id == project_id)
    if activity_id:
        query = query.filter(Task.activity_id == activity_id)
    
    tasks = query.order_by(Task.task_order).all()
    
    return jsonify({
        'success': True,
        'tasks': [{
            'id': t.id,
            'task_code': t.task_code,
            'task_name': t.task_name,
            'status': t.status,
            'progress': t.progress.progress_percentage if t.progress else 0,
            'priority': t.priority,
            'is_delayed': t.is_delayed(),
            'project_id': t.project_id,
            'project_name': t.project.name if t.project else None,
            'activity_id': t.activity_id,
            'activity_name': t.activity.activity_name if t.activity else None
        } for t in tasks]
    })


@task_bp.route('/api/by-activity/<int:activity_id>')
@login_required
def api_tasks_by_activity(activity_id):
    """API لجلب مهام نشاط معين"""
    activity = Activity.query.get_or_404(activity_id)
    
    project = Project.query.get(activity.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    tasks = Task.query.filter_by(activity_id=activity_id).order_by(Task.task_order).all()
    
    return jsonify({
        'success': True,
        'tasks': [{
            'id': t.id,
            'task_code': t.task_code,
            'task_name': t.task_name,
            'status': t.status,
            'progress': t.progress.progress_percentage if t.progress else 0,
            'priority': t.priority,
            'is_delayed': t.is_delayed(),
            'planned_finish': t.planning.planned_finish.isoformat() if t.planning and t.planning.planned_finish else None
        } for t in tasks]
    })


@task_bp.route('/api/<int:task_id>')
@login_required
def api_task_detail(task_id):
    """API لتفاصيل المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'task': {
            'id': task.id,
            'task_code': task.task_code,
            'task_name': task.task_name,
            'description': task.description,
            'status': task.status,
            'priority': task.priority,
            'planning': {
                'planned_start': task.planning.planned_start.isoformat() if task.planning and task.planning.planned_start else None,
                'planned_finish': task.planning.planned_finish.isoformat() if task.planning and task.planning.planned_finish else None,
                'planned_duration': task.planning.planned_duration if task.planning else None,
                'estimated_effort': task.planning.estimated_effort if task.planning else None
            } if task.planning else None,
            'progress': {
                'percentage': task.progress.progress_percentage if task.progress else 0,
                'quality': task.progress.completion_quality if task.progress else None
            } if task.progress else None,
            'execution': {
                'actual_start': task.execution.actual_start.isoformat() if task.execution and task.execution.actual_start else None,
                'actual_finish': task.execution.actual_finish.isoformat() if task.execution and task.execution.actual_finish else None,
                'actual_duration': task.execution.actual_duration if task.execution else None
            } if task.execution else None,
            'location': {
                'location': task.location_rel.location if task.location_rel else None,
                'coordinates': task.location_rel.coordinates if task.location_rel else None
            } if task.location_rel else None,
            'is_delayed': task.is_delayed(),
            'delay_days': task.get_delay_days(),
            'activity_id': task.activity_id,
            'activity_name': task.activity.activity_name if task.activity else None,
            'supervisor': {
                'id': task.supervisor.id if task.supervisor else None,
                'name': task.supervisor.full_name if task.supervisor else None
            } if task.supervisor else None,
            'delegate': {
                'id': task.delegate.id if task.delegate else None,
                'name': task.delegate.full_name if task.delegate else None
            } if task.delegate else None,
            'assignments_count': task.assignments.count(),
            'resources_count': task.resources.count(),
            'requirements_count': TaskRequirement.query.filter_by(task_id=task.id, is_active=True).count()
        }
    })


@task_bp.route('/api/<int:task_id>/update', methods=['POST'])
@login_required
def api_update_task(task_id):
    """تحديث بيانات المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if 'task_name' in data:
            task.task_name = data['task_name']
        if 'description' in data:
            task.description = data['description']
        if 'status' in data:
            task.status = data['status']
        if 'priority' in data:
            task.priority = int(data['priority'])
        if 'progress' in data and task.progress:
            task.progress.progress_percentage = float(data['progress'])
            # ✅ تحديث المؤشرات
            if task.activity_id:
                UpdateService.update_activity_metrics(task.activity)
            UpdateService.update_project_metrics(task.project)
        if 'activity_id' in data:
            task.activity_id = data['activity_id'] or None
        
        if 'planning' in data and task.planning:
            if 'planned_start' in data['planning']:
                task.planning.planned_start = datetime.strptime(data['planning']['planned_start'], '%Y-%m-%d').date() if data['planning']['planned_start'] else None
            if 'planned_finish' in data['planning']:
                task.planning.planned_finish = datetime.strptime(data['planning']['planned_finish'], '%Y-%m-%d').date() if data['planning']['planned_finish'] else None
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/<int:task_id>/start', methods=['POST'])
@login_required
def api_start_task(task_id):
    """بدء المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # التحقق من إمكانية البدء
    can_start, message = task.can_start()
    if not can_start:
        return jsonify({'success': False, 'error': message}), 400
    
    if task.status == 'pending':
        task.status = 'in_progress'
        if not task.execution:
            task.execution = TaskExecution(task_id=task.id)
        task.execution.actual_start = datetime.utcnow()
        if task.progress:
            task.progress.progress_percentage = 0.1
        
        # تسجيل تحديث التقدم
        progress_update = TaskProgressUpdate(
            task_id=task.id,
            progress_percentage=0.1,
            updated_by=current_user.id,
            notes='تم بدء المهمة'
        )
        db.session.add(progress_update)
        
        db.session.commit()
        # إنشاء إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != current_user.id:
            notification = Notification(
                user_id=task.supervisor_id,
                title='بدء مهمة',
                message=f'بدأ {current_user.full_name} في تنفيذ المهمة: {task.task_name}',
                notification_type='task_started',
                related_task_id=task.id,
                related_project_id=task.project_id
            )
            db.session.add(notification)
            db.session.commit()
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'لا يمكن بدء المهمة'})


@task_bp.route('/api/<int:task_id>/complete', methods=['POST'])
@login_required
def api_complete_task(task_id):
    """إكمال المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    quality = data.get('quality', 'good')
    notes = data.get('notes')
    
    if task.status == 'in_progress':
        task.status = 'completed'
        if not task.execution:
            task.execution = TaskExecution(task_id=task.id)
        task.execution.actual_finish = datetime.utcnow()
        if task.execution.actual_start:
            duration = task.execution.actual_finish - task.execution.actual_start
            task.execution.actual_duration = duration.total_seconds() / 3600
        
        if not task.progress:
            task.progress = TaskProgress(task_id=task.id)
        task.progress.progress_percentage = 100
        task.progress.completion_quality = quality
        
        if notes:
            if not task.verification:
                task.verification = TaskVerification(task_id=task.id)
            task.verification.notes = notes
            task.verification.verified_at = datetime.utcnow()
        
        # تسجيل تحديث التقدم
        progress_update = TaskProgressUpdate(
            task_id=task.id,
            progress_percentage=100,
            updated_by=current_user.id,
            notes=f'تم إكمال المهمة بجودة: {quality}'
        )
        db.session.add(progress_update)
        
        db.session.commit()
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        # بدء المهام التالية
        task.start_successor_tasks()
        
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'لا يمكن إكمال المهمة'})


@task_bp.route('/api/<int:task_id>/pause', methods=['POST'])
@login_required
def api_pause_task(task_id):
    """إيقاف المهمة مؤقتاً"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    if task.status == 'in_progress':
        task.status = 'on_hold'
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'لا يمكن إيقاف المهمة'})


@task_bp.route('/api/<int:task_id>/resume', methods=['POST'])
@login_required
def api_resume_task(task_id):
    """استئناف المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    if task.status == 'on_hold':
        task.status = 'in_progress'
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'لا يمكن استئناف المهمة'})


@task_bp.route('/api/<int:task_id>/cancel', methods=['POST'])
@login_required
def api_cancel_task(task_id):
    """إلغاء المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    if task.status in ['pending', 'in_progress', 'on_hold']:
        task.status = 'cancelled'
        db.session.commit()
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'لا يمكن إلغاء المهمة'})

# ============================================
# API Routes للتعيينات (Assignments)
# ============================================

@task_bp.route('/api/<int:task_id>/assign-multiple', methods=['POST'])
@login_required
def assign_multiple_users(task_id):
    """تعيين عدة مستخدمين لمهمة"""
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if not can_assign_users(task, current_user):
        return jsonify({'success': False, 'error': 'غير مصرح بتعيين مستخدمين'}), 403
    
    data = request.get_json()
    user_ids = data.get('user_ids', [])
    notes = data.get('notes', '')
    
    if not user_ids:
        return jsonify({'success': False, 'error': 'لم يتم اختيار أي مستخدمين'}), 400
    
    try:
        assigned_count = 0
        for user_id in user_ids:
            # التحقق من عدم وجود تعيين مسبق
            existing = TaskAssignment.query.filter_by(
                task_id=task_id,
                user_id=user_id
            ).first()
            
            if not existing:
                assignment = TaskAssignment(
                    task_id=task_id,
                    user_id=user_id,
                    assigned_by=current_user.id,
                    assigned_at=datetime.utcnow(),
                    status='assigned',
                    notes=notes
                )
                db.session.add(assignment)
                assigned_count += 1
                
                # إنشاء إشعار للمستخدم
                notification = Notification(
                    user_id=user_id,
                    title='مهمة جديدة',
                    message=f'تم تعيينك في مهمة: {task.task_name}',
                    notification_type='task_assigned',
                    related_task_id=task.id,
                    related_project_id=task.project_id
                )
                db.session.add(notification)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'assigned_count': assigned_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/assignment/<int:assignment_id>', methods=['GET'])
@login_required
def get_assignment_details(assignment_id):
    """الحصول على تفاصيل تعيين"""
    assignment = TaskAssignment.query.get_or_404(assignment_id)
    
    # التحقق من الصلاحية
    task = assignment.task
    if not has_task_access(task, current_user):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    user = assignment.user
    
    # تحديد لون الحالة
    status_colors = {
        'assigned': 'warning',
        'accepted': 'info',
        'in_progress': 'primary',
        'completed': 'success',
        'rejected': 'danger'
    }
    
    return jsonify({
        'success': True,
        'assignment': {
            'id': assignment.id,
            'user_id': assignment.user_id,
            'user_name': user.full_name if user else 'غير معروف',
            'user_color': getattr(user, 'color', '#4361ee'),
            'status': assignment.status,
            'status_badge': status_colors.get(assignment.status, 'secondary'),
            'assigned_at': assignment.assigned_at.strftime('%Y-%m-%d %H:%M') if assignment.assigned_at else None,
            'acceptance_date': assignment.acceptance_date.strftime('%Y-%m-%d %H:%M') if assignment.acceptance_date else None,
            'completion_date': assignment.completion_date.strftime('%Y-%m-%d %H:%M') if assignment.completion_date else None,
            'quality_rating': assignment.quality_rating,
            'efficiency_rating': assignment.efficiency_rating,
            'notes': assignment.notes
        }
    })


@task_bp.route('/api/assignment/<int:assignment_id>/remove', methods=['POST'])
@login_required
def remove_assignment(assignment_id):
    """إزالة تعيين مستخدم من مهمة"""
    assignment = TaskAssignment.query.get_or_404(assignment_id)
    
    # التحقق من الصلاحية
    task = assignment.task
    if not can_remove_assignment(task, current_user):
        return jsonify({'success': False, 'error': 'غير مصرح بإزالة هذا التعيين'}), 403
    
    try:
        user_name = assignment.user.full_name if assignment.user else 'مستخدم'
        task_name = task.task_name
        
        db.session.delete(assignment)
        db.session.commit()
        
        # إنشاء إشعار للمستخدم الذي تمت إزالته
        if assignment.user_id:
            notification = Notification(
                user_id=assignment.user_id,
                title='إزالة من مهمة',
                message=f'تمت إزالتك من مهمة: {task_name}',
                notification_type='assignment_removed',
                related_task_id=task.id,
                related_project_id=task.project_id
            )
            db.session.add(notification)
            db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/assignments/remove-multiple', methods=['POST'])
@login_required
def remove_multiple_assignments():
    """إزالة عدة تعيينات دفعة واحدة"""
    data = request.get_json()
    assignment_ids = data.get('assignment_ids', [])
    
    if not assignment_ids:
        return jsonify({'success': False, 'error': 'لا توجد تعيينات محددة'}), 400
    
    try:
        removed_count = 0
        for assignment_id in assignment_ids:
            assignment = TaskAssignment.query.get(assignment_id)
            if assignment and can_remove_assignment(assignment.task, current_user):
                db.session.delete(assignment)
                removed_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'removed_count': removed_count
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# دوال مساعدة للتحقق من الصلاحيات
def can_assign_users(task, user):
    """التحقق من صلاحية تعيين مستخدمين"""
    if user.role in ['org_admin', 'project_manager']:
        return True
    if user.role == 'supervisor' and task.supervisor_id == user.id:
        return True
    return False

def can_remove_assignment(task, user):
    """التحقق من صلاحية إزالة تعيين"""
    if user.role in ['org_admin', 'project_manager']:
        return True
    if user.role == 'supervisor' and task.supervisor_id == user.id:
        return True
    return False

def has_task_access(task, user):
    """التحقق من الوصول للمهمة"""
    if user.role in ['org_admin', 'project_manager']:
        return True
    if user.role == 'supervisor' and task.supervisor_id == user.id:
        return True
    if user.role == 'delegate' and task.delegate_id == user.id:
        return True
    return False

@task_bp.route('/api/assignment/<int:assignment_id>/update-status', methods=['POST'])
@login_required
def api_update_assignment_status(assignment_id):
    """تحديث حالة التعيين"""
    assignment = TaskAssignment.query.get_or_404(assignment_id)
    
    task = Task.query.get(assignment.task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    status = data.get('status')
    
    try:
        assignment.status = status
        if status == 'accepted':
            assignment.acceptance_date = datetime.utcnow()
        elif status == 'completed':
            assignment.completion_date = datetime.utcnow()
            if 'quality_rating' in data:
                assignment.quality_rating = data['quality_rating']
            if 'efficiency_rating' in data:
                assignment.efficiency_rating = data['efficiency_rating']
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================
# API Routes للموارد (Task Resources)
# ============================================

@task_bp.route('/api/<int:task_id>/resources', methods=['GET'])
@login_required
def api_task_resources(task_id):
    """جلب موارد المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    resources = TaskResource.query.filter_by(task_id=task_id).all()
    
    return jsonify({
        'success': True,
        'resources': [{
            'id': r.id,
            'resource_id': r.resource_id,
            'resource_type': r.resource_type,
            'resource_name': r.resource_name,
            'quantity': r.quantity,
            'unit': r.unit,
            'cost': r.cost
        } for r in resources]
    })


@task_bp.route('/api/<int:task_id>/resource', methods=['POST'])
@login_required
def api_add_task_resource(task_id):
    """إضافة مورد للمهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        resource = TaskResource(
            task_id=task_id,
            resource_id=data.get('resource_id'),
            resource_type=data.get('resource_type'),
            resource_name=data.get('resource_name'),
            quantity=float(data.get('quantity', 1)),
            unit=data.get('unit'),
            cost=float(data.get('cost', 0))
        )
        
        db.session.add(resource)
        db.session.commit()
        
        return jsonify({'success': True, 'resource_id': resource.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/task-resource/<int:resource_id>/update', methods=['POST'])
@login_required
def api_update_task_resource(resource_id):
    """تحديث مورد المهمة"""
    resource = TaskResource.query.get_or_404(resource_id)
    
    task = Task.query.get(resource.task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if 'quantity' in data:
            resource.quantity = float(data['quantity'])
        if 'cost' in data:
            resource.cost = float(data['cost'])
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/task-resource/<int:resource_id>/delete', methods=['POST'])
@login_required
def api_delete_task_resource(resource_id):
    """حذف مورد من المهمة"""
    resource = TaskResource.query.get_or_404(resource_id)
    
    task = Task.query.get(resource.task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(resource)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للتبعيات (Dependencies)
# ============================================

@task_bp.route('/api/<int:task_id>/dependencies', methods=['GET'])
@login_required
def api_task_dependencies(task_id):
    """جلب تبعيات المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    predecessors = TaskDependency.query.filter_by(successor_task_id=task_id).all()
    successors = TaskDependency.query.filter_by(predecessor_task_id=task_id).all()
    
    return jsonify({
        'success': True,
        'predecessors': [{
            'id': d.id,
            'task_id': d.predecessor_task_id,
            'task_code': d.predecessor.task_code if d.predecessor else None,
            'task_name': d.predecessor.task_name if d.predecessor else None,
            'dependency_type': d.dependency_type,
            'lag': d.lag,
            'lag_type': d.lag_type,
            'is_critical': d.is_critical,
            'is_driving': d.is_driving
        } for d in predecessors],
        'successors': [{
            'id': d.id,
            'task_id': d.successor_task_id,
            'task_code': d.successor.task_code if d.successor else None,
            'task_name': d.successor.task_name if d.successor else None,
            'dependency_type': d.dependency_type,
            'lag': d.lag,
            'lag_type': d.lag_type,
            'is_critical': d.is_critical,
            'is_driving': d.is_driving
        } for d in successors]
    })


@task_bp.route('/api/<int:task_id>/predecessor', methods=['POST'])
@login_required
def api_add_task_predecessor(task_id):
    """إضافة مهمة سابقة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    predecessor_id = data.get('predecessor_id')
    
    if not predecessor_id:
        return jsonify({'success': False, 'error': 'معرف المهمة السابقة مطلوب'}), 400
    
    # التحقق من عدم وجود علاقة دائرية
    if would_create_circular_task_relationship(predecessor_id, task_id):
        return jsonify({'success': False, 'error': 'علاقة دائرية'}), 400
    
    # التحقق من عدم وجود علاقة مكررة
    existing = TaskDependency.query.filter_by(
        predecessor_task_id=predecessor_id,
        successor_task_id=task_id
    ).first()
    
    if existing:
        return jsonify({'success': False, 'error': 'العلاقة موجودة مسبقاً'}), 400
    
    try:
        dependency = TaskDependency(
            project_id=task.project_id,
            predecessor_task_id=predecessor_id,
            successor_task_id=task_id,
            dependency_type=data.get('dependency_type', 'FS'),
            lag=float(data.get('lag', 0)),
            lag_type=data.get('lag_type', 'days'),
            is_critical=data.get('is_critical', False),
            is_driving=data.get('is_driving', True)
        )
        
        db.session.add(dependency)
        db.session.commit()
        
        return jsonify({'success': True, 'dependency_id': dependency.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/<int:task_id>/successor', methods=['POST'])
@login_required
def api_add_task_successor(task_id):
    """إضافة مهمة تالية"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    successor_id = data.get('successor_id')
    
    if not successor_id:
        return jsonify({'success': False, 'error': 'معرف المهمة التالية مطلوب'}), 400
    
    # التحقق من عدم وجود علاقة مكررة
    existing = TaskDependency.query.filter_by(
        predecessor_task_id=task_id,
        successor_task_id=successor_id
    ).first()
    
    if existing:
        return jsonify({'success': False, 'error': 'العلاقة موجودة مسبقاً'}), 400
    
    try:
        dependency = TaskDependency(
            project_id=task.project_id,
            predecessor_task_id=task_id,
            successor_task_id=successor_id,
            dependency_type=data.get('dependency_type', 'FS'),
            lag=float(data.get('lag', 0)),
            lag_type=data.get('lag_type', 'days'),
            is_critical=data.get('is_critical', False),
            is_driving=data.get('is_driving', True)
        )
        
        db.session.add(dependency)
        db.session.commit()
        
        return jsonify({'success': True, 'dependency_id': dependency.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/dependency/<int:dependency_id>/update', methods=['POST'])
@login_required
def api_update_task_dependency(dependency_id):
    """تحديث تبعية"""
    dependency = TaskDependency.query.get_or_404(dependency_id)
    
    task = Task.query.get(dependency.predecessor_task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if 'dependency_type' in data:
            dependency.dependency_type = data['dependency_type']
        if 'lag' in data:
            dependency.lag = float(data['lag'])
        if 'lag_type' in data:
            dependency.lag_type = data['lag_type']
        if 'is_critical' in data:
            dependency.is_critical = data['is_critical']
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/dependency/<int:dependency_id>/delete', methods=['POST'])
@login_required
def api_delete_task_dependency(dependency_id):
    """حذف تبعية"""
    dependency = TaskDependency.query.get_or_404(dependency_id)
    
    task = Task.query.get(dependency.predecessor_task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(dependency)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للمتطلبات (Requirements)
# ============================================

@task_bp.route('/api/<int:task_id>/requirements', methods=['GET'])
@login_required
def api_task_requirements(task_id):
    """جلب متطلبات المهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    requirements = TaskRequirement.query.filter_by(task_id=task_id, is_active=True).order_by(TaskRequirement.order).all()
    
    return jsonify({
        'success': True,
        'requirements': [{
            'id': r.id,
            'type': r.requirement_type,
            'description': r.description,
            'is_mandatory': r.is_mandatory,
            'order': r.order,
            'verified': TaskRequirementVerification.query.filter_by(
                requirement_id=r.id, status='verified'
            ).first() is not None
        } for r in requirements]
    })


@task_bp.route('/api/<int:task_id>/requirement', methods=['POST'])
@login_required
def api_add_task_requirement(task_id):
    """إضافة متطلب للمهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        last_req = TaskRequirement.query.filter_by(task_id=task_id).order_by(TaskRequirement.order.desc()).first()
        next_order = (last_req.order + 1) if last_req else 1
        
        requirement = TaskRequirement(
            task_id=task_id,
            requirement_type=data.get('type'),
            description=data.get('description'),
            description_ar=data.get('description_ar'),
            required_value=data.get('required_value'),
            validation_criteria=data.get('validation_criteria'),
            is_mandatory=data.get('is_mandatory', True),
            order=next_order
        )
        
        db.session.add(requirement)
        db.session.commit()
        
        return jsonify({'success': True, 'requirement_id': requirement.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/requirement/<int:requirement_id>/verify', methods=['POST'])
@login_required
def api_verify_requirement(requirement_id):
    """تقديم طلب تحقق لمتطلب"""
    requirement = TaskRequirement.query.get_or_404(requirement_id)
    
    task = Task.query.get(requirement.task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    files = request.files
    
    try:
        verification = TaskRequirementVerification(
            requirement_id=requirement_id,
            task_id=task.id,
            user_id=current_user.id,
            status='pending',
            verified_value=data.get('value'),
            notes=data.get('notes')
        )
        
        # معالجة الملفات المرفوعة
        if 'file' in files:
            file = files['file']
            filename = secure_filename(f"req_{requirement_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
            file_path = os.path.join('uploads', 'requirements', filename)
            file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], 'requirements', filename))
            verification.file_url = url_for('static', filename=file_path)
        
        if 'photo' in files:
            photo = files['photo']
            filename = secure_filename(f"req_photo_{requirement_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            file_path = os.path.join('uploads', 'requirements', 'photos', filename)
            photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], 'requirements', 'photos', filename))
            verification.photo_url = url_for('static', filename=file_path)
        
        db.session.add(verification)
        db.session.commit()
        # ✅ تحديث المؤشرات (التقدم يعتمد على المتطلبات)
        UpdateService.update_task_metrics(task.id)
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        return jsonify({'success': True, 'verification_id': verification.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/verification/<int:verification_id>/approve', methods=['POST'])
@login_required
def api_approve_verification(verification_id):
    """الموافقة على طلب تحقق"""
    verification = TaskRequirementVerification.query.get_or_404(verification_id)
    
    task = Task.query.get(verification.task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    approve = data.get('approve', True)
    
    try:
        verification.status = 'verified' if approve else 'rejected'
        verification.verified_at = datetime.utcnow()
        verification.verified_by = current_user.id
        if 'notes' in data:
            verification.notes = data['notes']
        
        db.session.commit()
        # ✅ تحديث المؤشرات
        UpdateService.update_task_metrics(task.id)
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/requirement/<int:requirement_id>/delete', methods=['POST'])
@login_required
def api_delete_requirement(requirement_id):
    """حذف متطلب"""
    requirement = TaskRequirement.query.get_or_404(requirement_id)
    
    task = Task.query.get(requirement.task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        requirement.is_active = False
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes لفحوصات السلامة (Safety Checks)
# ============================================

@task_bp.route('/api/<int:task_id>/safety-checks', methods=['GET'])
@login_required
def api_task_safety_checks(task_id):
    """جلب فحوصات السلامة للمهمة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    checks = TaskSafetyCheck.query.filter_by(task_id=task_id).all()
    
    return jsonify({
        'success': True,
        'checks': [{
            'id': c.id,
            'check_name': c.check_name,
            'check_type': c.check_type,
            'is_verified': c.is_verified,
            'verified_at': c.verified_at.isoformat() if c.verified_at else None,
            'verified_by': c.verified_by
        } for c in checks]
    })


@task_bp.route('/api/<int:task_id>/safety-check', methods=['POST'])
@login_required
def api_add_safety_check(task_id):
    """إضافة فحص سلامة"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        check = TaskSafetyCheck(
            task_id=task_id,
            check_name=data.get('check_name'),
            check_name_ar=data.get('check_name_ar'),
            description=data.get('description'),
            check_type=data.get('check_type', 'general')
        )
        
        db.session.add(check)
        db.session.commit()
        
        return jsonify({'success': True, 'check_id': check.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/safety-check/<int:check_id>/verify', methods=['POST'])
@login_required
def api_verify_safety_check(check_id):
    """التحقق من فحص سلامة"""
    check = TaskSafetyCheck.query.get_or_404(check_id)
    
    task = Task.query.get(check.task_id)
    project = Project.query.get(task.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    files = request.files
    
    try:
        check.is_verified = True
        check.verified_at = datetime.utcnow()
        check.verified_by = current_user.id
        
        if 'proof_photo' in files:
            photo = files['proof_photo']
            filename = secure_filename(f"safety_{check_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
            file_path = os.path.join('uploads', 'safety', filename)
            photo.save(os.path.join(current_app.config['UPLOAD_FOLDER'], 'safety', filename))
            check.proof_photo = url_for('static', filename=file_path)
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes لتحديث التقدم (Progress Updates)
# ============================================

@task_bp.route('/api/<int:task_id>/progress-update', methods=['POST'])
@login_required
def api_add_progress_update(task_id):
    """إضافة تحديث تقدم"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    progress = float(data.get('progress', 0))
    
    try:
        # تحديث تقدم المهمة
        old_progress = task.progress.progress_percentage if task.progress else 0
        task.update_progress(progress, current_user.id)
        
        # إضافة سجل التحديث
        progress_update = TaskProgressUpdate(
            task_id=task_id,
            progress_percentage=progress,
            updated_by=current_user.id,
            notes=data.get('notes'),
            photos=data.get('photos', [])
        )
        
        db.session.add(progress_update)
        db.session.commit()
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        return jsonify({
            'success': True,
            'old_progress': old_progress,
            'new_progress': progress
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@task_bp.route('/api/<int:task_id>/progress-history')
@login_required
def api_progress_history(task_id):
    """جلب تاريخ تحديثات التقدم"""
    task = check_task_access(task_id)
    if not task:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    updates = TaskProgressUpdate.query.filter_by(task_id=task_id).order_by(TaskProgressUpdate.updated_at.desc()).all()
    
    return jsonify({
        'success': True,
        'updates': [{
            'id': u.id,
            'progress': u.progress_percentage,
            'notes': u.notes,
            'updated_by': u.updater.full_name if u.updater else None,
            'updated_at': u.updated_at.isoformat()
        } for u in updates]
    })

# ============================================
# API Routes لتحليل المهام
# ============================================

@task_bp.route('/api/analysis/critical-path')
@login_required
def api_critical_path_analysis():
    """تحليل المسار الحرج للمشروع"""
    project_id = request.args.get('project_id')
    
    if not project_id:
        return jsonify({'success': False, 'error': 'project_id مطلوب'}), 400
    
    project = Project.query.get(project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    analysis = Task.get_critical_path_analysis(project_id)
    
    return jsonify({
        'success': True,
        'analysis': analysis
    })


@task_bp.route('/api/analysis/user-performance/<int:user_id>')
@login_required
def api_user_performance(user_id):
    """تحليل أداء مستخدم في المهام"""
    if user_id != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    assignments = TaskAssignment.query.filter_by(user_id=user_id).all()
    
    completed = [a for a in assignments if a.status == 'completed']
    in_progress = [a for a in assignments if a.status == 'in_progress']
    
    avg_quality = sum(a.quality_rating or 0 for a in completed) / len(completed) if completed else 0
    avg_efficiency = sum(a.efficiency_rating or 0 for a in completed) / len(completed) if completed else 0
    
    on_time = sum(1 for a in completed if a.task and not a.task.is_delayed())
    
    return jsonify({
        'success': True,
        'performance': {
            'total_assignments': len(assignments),
            'completed': len(completed),
            'in_progress': len(in_progress),
            'completion_rate': (len(completed) / len(assignments) * 100) if assignments else 0,
            'on_time': on_time,
            'on_time_rate': (on_time / len(completed) * 100) if completed else 0,
            'avg_quality': round(avg_quality, 1),
            'avg_efficiency': round(avg_efficiency, 1)
        }
    })


@task_bp.route('/api/analysis/project-tasks/<int:project_id>')
@login_required
def api_project_tasks_analysis(project_id):
    """تحليل شامل لمهام المشروع"""
    project = Project.query.get(project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    tasks = Task.query.filter_by(project_id=project_id).all()
    
    # تحليل حسب الحالة
    by_status = {}
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    
    # تحليل حسب الأولوية
    by_priority = {}
    for t in tasks:
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
    
    # تحليل التأخير
    delayed = [t for t in tasks if t.is_delayed()]
    
    # تحليل التقدم
    avg_progress = sum(t.progress.progress_percentage for t in tasks if t.progress) / len(tasks) if tasks else 0
    
    return jsonify({
        'success': True,
        'analysis': {
            'total_tasks': len(tasks),
            'by_status': by_status,
            'by_priority': by_priority,
            'delayed_count': len(delayed),
            'delayed_percentage': (len(delayed) / len(tasks) * 100) if tasks else 0,
            'avg_progress': round(avg_progress, 1),
            'completion_rate': (by_status.get('completed', 0) / len(tasks) * 100) if tasks else 0
        }
    })

# ============================================
# API Routes للتقارير اليومية (Daily Reports)
# ============================================

@task_bp.route('/api/daily-report/<int:report_id>')
@login_required
def api_daily_report(report_id):
    """جلب تقرير يومي"""
    report = DailyReport.query.get_or_404(report_id)
    
    project = Project.query.get(report.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'report': {
            'id': report.id,
            'date': report.report_date.isoformat(),
            'number': report.report_number,
            'weather': report.weather_condition,
            'temperature': report.temperature,
            'workers': report.total_workers,
            'hours': report.total_hours,
            'overtime': report.overtime_hours,
            'work_summary': report.work_summary,
            'completed_work': report.completed_work,
            'planned_work': report.planned_work,
            'issues': report.issues_encountered,
            'safety': report.safety_incidents,
            'quality': report.quality_notes,
            'supervisor_notes': report.supervisor_notes,
            'engineer_notes': report.engineer_notes,
            'status': report.review_status,
            'tasks_count': report.tasks.count(),
            'photos_count': report.photos.count()
        }
    })
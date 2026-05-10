"""
task_routes.py - مسارات إدارة المهام
"""
from flask import render_template, request, redirect, url_for, flash, jsonify,g
from flask_login import login_required, current_user
from app.models import db, Task, TaskAssignment, TaskProgressUpdate, Project, User, Activitys,Organization,Notification
# from app.routes import task_bp
from datetime import datetime, date, timedelta
import json
from app.services.task_automation import TaskAutomationService

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
            Task.planned_end_date < date.today()
        ).count()
    else:
        g.company = None
        g.delayed_tasks_count = 0
        g.notifications_count = 0

@task_bp.route('/tasks')
@login_required
def index():
    """قائمة المهام"""
    
    # الحصول على المهام حسب دور المستخدم
    if current_user.role == 'admin' or current_user.role == 'org_admin':
        # مدير النظام يرى جميع المهام في المؤسسة
        tasks = Task.query.join(Project).filter(
            Project.org_id == current_user.org_id
        ).all()
    elif current_user.role == 'project_manager':
        # مدير المشروع يرى مهام مشاريعه
        tasks = Task.query.join(Project).filter(
            Project.project_manager_id == current_user.id
        ).all()
    elif current_user.role == 'supervisor':
        # المشرف يرى المهام التي يشرف عليها
        tasks = Task.query.filter_by(supervisor_id=current_user.id).all()
    elif current_user.role == 'delegate':
        # المندوب يرى المهام الموكلة إليه
        tasks = Task.query.filter_by(delegate_id=current_user.id).all()
    else:  # employee
        # الموظف يرى المهام المعينة له
        tasks = Task.query.join(Task.assignments).filter(
            TaskAssignment.user_id == current_user.id
        ).all()
    
    # التصفية حسب المعايير
    tasks = filter_tasks(tasks, request.args)
    
    return render_template('tasks/index.html', tasks=tasks,today = date.today())

def filter_tasks(tasks, filters):
    """تصفية المهام حسب المعايير"""
    filtered_tasks = tasks
    
    # التصفية حسب الحالة
    status_filter = filters.get('status')
    if status_filter:
        filtered_tasks = [t for t in filtered_tasks if t.status == status_filter]
    
    # التصفية حسب المشروع
    project_filter = filters.get('project_id')
    if project_filter:
        filtered_tasks = [t for t in filtered_tasks if t.project_id == int(project_filter)]
    
    # التصفية حسب الأولوية
    priority_filter = filters.get('priority')
    if priority_filter:
        filtered_tasks = [t for t in filtered_tasks if getattr(t, 'priority', None) == priority_filter]
    
    # البحث
    search_query = filters.get('search')
    if search_query:
        filtered_tasks = [t for t in filtered_tasks if 
                         search_query.lower() in t.task_name.lower() or 
                         search_query in t.task_code]
    
    return filtered_tasks

@task_bp.route('/<int:task_id>')
@login_required
def view(task_id):
    """عرض تفاصيل المهمة"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if not has_task_access(task, current_user):
        flash('غير مصرح بالوصول لهذه المهمة', 'danger')
        return redirect(url_for('task.index'))
    
    # تحديثات التقدم
    progress_updates = TaskProgressUpdate.query.filter_by(task_id=task_id).order_by(TaskProgressUpdate.updated_at.desc()).all()
    
    # المهام المعينة
    assignments = TaskAssignment.query.filter_by(task_id=task_id).all()
    
    # التقارير اليومية المرتبطة
    daily_reports = task.daily_reports[:10] if hasattr(task, 'daily_reports') else []
    
    # فحوصات الجودة
    quality_checks = task.quality_checks[:5] if hasattr(task, 'quality_checks') else []
    
    # القضايا
    issues = task.issues[:5] if hasattr(task, 'issues') else []
    
    return render_template('tasks/view.html',
                         task=task,
                         progress_updates=progress_updates,
                         assignments=assignments,
                         daily_reports=daily_reports,
                         quality_checks=quality_checks,
                         issues=issues)

def has_task_access(task, user):
    """التحقق من صلاحية الوصول للمهمة"""
    if user.role == 'admin' or user.role == 'org_admin':
        return task.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return task.project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return task.supervisor_id == user.id
    elif user.role == 'delegate':
        return task.delegate_id == user.id
    else:  # employee
        return any(assignment.user_id == user.id for assignment in task.assignments)
    return False

@task_bp.route('/board')
@login_required
def board():
    """لوحة المهام"""
    
    # الحصول على المشاريع
    projects = Project.query.filter_by(
        org_id=current_user.org_id,
        status__in=['active', 'planning']
    ).all()
    
    # إذا تم تحديد مشروع
    project_id = request.args.get('project_id')
    
    if project_id:
        tasks_query = Task.query.filter_by(project_id=project_id)
        selected_project = Project.query.get(project_id)
    else:
        # الحصول على مهام المشاريع النشطة
        project_ids = [p.id for p in projects]
        tasks_query = Task.query.filter(Task.project_id.in_(project_ids))
        selected_project = None
    
    # تقسيم المهام حسب الحالة
    pending_tasks = tasks_query.filter_by(status='pending').all()
    in_progress_tasks = tasks_query.filter_by(status='in_progress').all()
    completed_tasks = tasks_query.filter_by(status='completed').all()
    on_hold_tasks = tasks_query.filter_by(status='on_hold').all()
    
    return render_template('tasks/task_board.html',
                         projects=projects,
                         selected_project=selected_project,
                         pending_tasks=pending_tasks,
                         in_progress_tasks=in_progress_tasks,
                         completed_tasks=completed_tasks,
                         on_hold_tasks=on_hold_tasks)

@task_bp.route('/my')
@login_required
def my_tasks():
    """مهامي"""
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # الحصول على المهام المعينة للمستخدم
    assigned_tasks = Task.query.join(TaskAssignment).filter(
        TaskAssignment.user_id == current_user.id,
        TaskAssignment.status != 'cancelled'
    )
    
    # المهام التي يشرف عليها المستخدم
    supervised_tasks = Task.query.filter_by(supervisor_id=current_user.id)
    
    # دمج النتائج
    from sqlalchemy import union_all
    all_tasks = union_all(assigned_tasks, supervised_tasks).subquery()
    
    # تطبيق الفلاتر
    query = Task.query.filter(Task.id.in_(db.session.query(all_tasks.c.id)))
    
    if request.args.get('status'):
        query = query.filter(Task.status == request.args.get('status'))
    
    if request.args.get('priority'):
        query = query.filter(Task.priority == request.args.get('priority'))
    
    # الترقيم
    tasks = query.order_by(Task.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('tasks/my_tasks.html',
                         tasks=tasks)

@task_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """إنشاء مهمة جديدة"""
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin','admin', 'project_manager', 'supervisor']:
        flash('غير مصرح بإنشاء مهام', 'danger')
        return redirect(url_for('task.index'))
    
    if request.method == 'POST':
        try:
            # جمع بيانات المهمة
            task_data = {
                'project_id': request.form.get('project_id'),
                'activity_id': request.form.get('activity_id'),
                'task_code': request.form.get('task_code'),
                'task_name': request.form.get('task_name'),
                'task_name_ar': request.form.get('task_name_ar'),
                'description': request.form.get('description'),
                'instructions': request.form.get('instructions'),
                'task_order': int(request.form.get('task_order', 0) or 0),
                'depends_on_task_id': request.form.get('depends_on_task_id'),
                'supervisor_id': request.form.get('supervisor_id') or current_user.id,
                'delegate_id': request.form.get('delegate_id'),
                'planned_start_date': request.form.get('planned_start_date'),
                'planned_end_date': request.form.get('planned_end_date'),
                'planned_duration': float(request.form.get('planned_duration', 0) or 0),
                'estimated_effort': float(request.form.get('estimated_effort', 0) or 0),
                'location': request.form.get('location'),
                'coordinates': request.form.get('coordinates'),
                'status': 'pending',
                'created_by': current_user.id
            }
            
            # تحويل التواريخ
            if task_data['planned_start_date']:
                task_data['planned_start_date'] = datetime.strptime(task_data['planned_start_date'], '%Y-%m-%d').date()
            if task_data['planned_end_date']:
                task_data['planned_end_date'] = datetime.strptime(task_data['planned_end_date'], '%Y-%m-%d').date()
            
            # إنشاء المهمة
            task = Task(**task_data)
            
            # حفظ الموارد المطلوبة
            resources = {
                'required_skills': request.form.getlist('required_skills'),
                'required_materials': request.form.getlist('required_materials'),
                'required_equipment': request.form.getlist('required_equipment')
            }
            task.required_skills = [s for s in resources['required_skills'] if s]
            task.required_materials = [m for m in resources['required_materials'] if m]
            task.required_equipment = [e for e in resources['required_equipment'] if e]
            
            db.session.add(task)
            db.session.commit()
            
            # تعيين الموظفين إذا تم تحديدهم
            assigned_users = request.form.getlist('assigned_users')
            for user_id in assigned_users:
                if user_id:
                    task.assign_user(int(user_id), current_user.id)
            
            db.session.commit()
            flash('تم إنشاء المهمة بنجاح', 'success')
            return redirect(url_for('task.view', task_id=task.id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # البيانات اللازمة للنموذج
    if current_user.role == 'admin' or current_user.role == 'org_admin':
        projects = PrimaveraProject.query.filter_by(org_id=current_user.org_id).all()
    else:
        projects = PrimaveraProject.query.filter_by(project_manager_id=current_user.id).all()
    
    supervisors = User.query.filter_by(
        org_id=current_user.org_id,
        role='supervisor',
        is_user_active=True
    ).all()
    
    delegates = User.query.filter_by(
        org_id=current_user.org_id,
        role='delegate',
        is_user_active=True
    ).all()
    
    employees = User.query.filter_by(
        org_id=current_user.org_id,
        role='employee',
        is_user_active=True
    ).all()
    
    # الحصول على المهام في المشاريع المختارة
    tasks = []
    if projects:
        tasks = Task.query.filter(Task.project_id.in_([p.id for p in projects])).all()
    # بيانات النموذج
    project_id = request.args.get('project_id')
    activity_id = request.args.get('activity_id')
    
    project = PrimaveraProject.query.get(project_id) if project_id else None
    activity = Activitys.query.get(activity_id) if activity_id else None
    activities = Activitys.query.filter_by(project_id=project_id).all() if project_id else []
    return render_template('tasks/create.html',
                         projects=projects,
                         supervisors=supervisors,
                         delegates=delegates,
                         employees=employees,
                         project=project,
                         activity=activity,
                         tasks=tasks,
                         activities=activities)

@task_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(task_id):
    """تعديل المهمة"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if not can_edit_task(task, current_user):
        flash('غير مصرح بتعديل هذه المهمة', 'danger')
        return redirect(url_for('task.view', task_id=task_id))
    
    if request.method == 'POST':
        try:
            # تحديث بيانات المهمة
            task.task_name = request.form.get('task_name', task.task_name)
            task.task_name_ar = request.form.get('task_name_ar', task.task_name_ar)
            task.description = request.form.get('description', task.description)
            task.instructions = request.form.get('instructions', task.instructions)
            task.supervisor_id = request.form.get('supervisor_id', task.supervisor_id)
            task.delegate_id = request.form.get('delegate_id', task.delegate_id)
            task.planned_start_date = datetime.strptime(
                request.form.get('planned_start_date', task.planned_start_date.strftime('%Y-%m-%d')),
                '%Y-%m-%d'
            ).date() if request.form.get('planned_start_date') else task.planned_start_date
            task.planned_end_date = datetime.strptime(
                request.form.get('planned_end_date', task.planned_end_date.strftime('%Y-%m-%d')),
                '%Y-%m-%d'
            ).date() if request.form.get('planned_end_date') else task.planned_end_date
            task.planned_duration = float(request.form.get('planned_duration', task.planned_duration) or 0)
            task.estimated_effort = float(request.form.get('estimated_effort', task.estimated_effort) or 0)
            task.location = request.form.get('location', task.location)
            task.status = request.form.get('status', task.status)
            
            # تحديث الموارد
            resources = {
                'required_skills': request.form.getlist('required_skills'),
                'required_materials': request.form.getlist('required_materials'),
                'required_equipment': request.form.getlist('required_equipment')
            }
            task.required_skills = [s for s in resources['required_skills'] if s]
            task.required_materials = [m for m in resources['required_materials'] if m]
            task.required_equipment = [e for e in resources['required_equipment'] if e]
            
            # تحديث التعيينات
            assigned_users = request.form.getlist('assigned_users')
            current_assigned = [str(a.user_id) for a in task.assignments]
            
            # إضافة تعيينات جديدة
            for user_id in assigned_users:
                if user_id and user_id not in current_assigned:
                    task.assign_user(int(user_id), current_user.id)
            
            # إزالة التعيينات الملغاة
            for assignment in task.assignments:
                if str(assignment.user_id) not in assigned_users:
                    db.session.delete(assignment)
            
            db.session.commit()
            flash('تم تحديث المهمة بنجاح', 'success')
            
            return redirect(url_for('task.view', task_id=task_id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # البيانات اللازمة للنموذج
    supervisors = User.query.filter_by(
        org_id=current_user.org_id,
        role='supervisor',
        is_active=True
    ).all()
    
    delegates = User.query.filter_by(
        org_id=current_user.org_id,
        role='delegate',
        is_active=True
    ).all()
    
    employees = User.query.filter_by(
        org_id=current_user.org_id,
        role='employee',
        is_active=True
    ).all()
    
    return render_template('tasks/edit.html',
                         task=task,
                         supervisors=supervisors,
                         delegates=delegates,
                         employees=employees)

def can_edit_task(self, task, user):
    """التحقق من إمكانية تعديل المهمة"""
    if user.role == 'admin':
        return task.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return task.project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return task.supervisor_id == user.id
    return False

@task_bp.route('/<int:task_id>/start', methods=['POST'])
@login_required
def start_task(task_id):
    """بدء المهمة"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if not can_start_task(task, current_user):
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح ببدء هذه المهمة', 'danger')
            return redirect(url_for('task.view', task_id=task_id))
    
    try:
        if task.start_task():
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'تم بدء المهمة بنجاح'})
            else:
                flash('تم بدء المهمة بنجاح', 'success')
                
        else:
            message = 'لا يمكن بدء المهمة في حالتها الحالية'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
                
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('task.view', task_id=task_id))

def can_start_task(self, task, user):
    """التحقق من إمكانية بدء المهمة"""
    if user.role == 'admin':
        return task.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return task.project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return task.supervisor_id == user.id
    elif user.role == 'delegate':
        return task.delegate_id == user.id
    elif user.role == 'employee':
        return any(assignment.user_id == user.id for assignment in task.assignments)
    return False

@task_bp.route('/<int:task_id>/complete', methods=['POST'])
@login_required
def complete_task(task_id):
    """إكمال المهمة"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if not can_complete_task(task, current_user):
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح بإكمال هذه المهمة', 'danger')
            return redirect(url_for('task.view', task_id=task_id))
    
    try:
        quality = request.form.get('quality', 'good')
        notes = request.form.get('notes')
        
        if task.complete_task(quality=quality):
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'تم إكمال المهمة بنجاح'})
            else:
                flash('تم إكمال المهمة بنجاح', 'success')
                
        else:
            message = 'لا يمكن إكمال المهمة في حالتها الحالية'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
                
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('task.view', task_id=task_id))

def can_complete_task(self, task, user):
    """التحقق من إمكانية إكمال المهمة"""
    if user.role == 'admin':
        return task.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return task.project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return task.supervisor_id == user.id
    elif user.role == 'delegate':
        return task.delegate_id == user.id
    elif user.role == 'employee':
        return any(assignment.user_id == user.id for assignment in task.assignments)
    return False

@task_bp.route('/<int:task_id>/update-progress', methods=['POST'])
@login_required
def update_progress(task_id):
    """تحديث تقدم المهمة"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if not can_update_progress(task, current_user):
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح بتحديث تقدم هذه المهمة', 'danger')
            return redirect(url_for('task.view', task_id=task_id))
    
    try:
        progress = float(request.form.get('progress', 0))
        notes = request.form.get('notes', '')
        
        if task.update_progress(progress, current_user.id):
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'تم تحديث التقدم بنجاح'})
            else:
                flash('تم تحديث التقدم بنجاح', 'success')
                
        else:
            message = 'لا يمكن تحديث التقدم'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
                
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('task.view', task_id=task_id))

def can_update_progress(self, task, user):
    """التحقق من إمكانية تحديث التقدم"""
    if user.role == 'admin':
        return task.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return task.project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return task.supervisor_id == user.id
    elif user.role == 'delegate':
        return task.delegate_id == user.id
    elif user.role == 'employee':
        return any(assignment.user_id == user.id for assignment in task.assignments)
    return False

@task_bp.route('/<int:task_id>/assign', methods=['POST'])
@login_required
def assign_task(task_id):
    """تعيين مستخدم للمهمة"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if not can_assign_task(task, current_user):
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح بتعيين مستخدمين لهذه المهمة', 'danger')
            return redirect(url_for('task.view', task_id=task_id))
    
    try:
        user_id = request.form.get('user_id')
        
        if not user_id:
            raise ValueError('يجب اختيار مستخدم')
        
        user = User.query.get_or_404(user_id)
        
        # التحقق من عدم تكرار التعيين
        existing_assignment = TaskAssignment.query.filter_by(
            task_id=task_id,
            user_id=user_id
        ).first()
        
        if existing_assignment:
            message = 'المستخدم معين بالفعل لهذه المهمة'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
                return redirect(url_for('task.view', task_id=task_id))
        
        # إنشاء التعيين
        assignment = task.assign_user(user_id, current_user.id)
        db.session.commit()
        
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'تم تعيين المستخدم بنجاح',
                'assignment': {
                    'id': assignment.id,
                    'user': user.to_dict()
                }
            })
        else:
            flash(f'تم تعيين {user.full_name} للمهمة بنجاح', 'success')
                
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('task.view', task_id=task_id))

def can_assign_task(self, task, user):
    """التحقق من إمكانية تعيين المهمة"""
    if user.role == 'admin':
        return task.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return task.project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return task.supervisor_id == user.id
    elif user.role == 'delegate':
        return task.delegate_id == user.id
    return False

@task_bp.route('/<int:task_id>/assignment/<int:assignment_id>/accept', methods=['POST'])
@login_required
def accept_assignment(task_id, assignment_id):
    """قبول التعيين"""
    
    assignment = TaskAssignment.query.get_or_404(assignment_id)
    
    # التحقق من أن التعيين للمستخدم الحالي
    if assignment.user_id != current_user.id:
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح بقبول هذا التعيين', 'danger')
            return redirect(url_for('task.view', task_id=task_id))
    
    try:
        if assignment.accept_assignment():
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'تم قبول التعيين'})
            else:
                flash('تم قبول التعيين بنجاح', 'success')
                
        else:
            message = 'لا يمكن قبول التعيين في حالته الحالية'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
                
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('task.view', task_id=task_id))

@task_bp.route('/<int:task_id>/assignment/<int:assignment_id>/complete', methods=['POST'])
@login_required
def complete_assignment(task_id, assignment_id):
    """إكمال التعيين"""
    
    assignment = TaskAssignment.query.get_or_404(assignment_id)
    
    # التحقق من أن التعيين للمستخدم الحالي أو المشرف
    if assignment.user_id != current_user.id and not is_task_supervisor(assignment.task, current_user):
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح بإكمال هذا التعيين', 'danger')
            return redirect(url_for('task.view', task_id=task_id))
    
    try:
        quality_rating = request.form.get('quality_rating')
        efficiency_rating = request.form.get('efficiency_rating')
        notes = request.form.get('notes', '')
        
        if assignment.complete_assignment(
            quality_rating=int(quality_rating) if quality_rating else None,
            efficiency_rating=int(efficiency_rating) if efficiency_rating else None,
            notes=notes
        ):
            db.session.commit()
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'تم إكمال التعيين'})
            else:
                flash('تم إكمال التعيين بنجاح', 'success')
                
        else:
            message = 'لا يمكن إكمال التعيين في حالته الحالية'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
                
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('task.view', task_id=task_id))

def is_task_supervisor(self, task, user):
    """التحقق إذا كان المستخدم مشرفاً على المهمة"""
    return task.supervisor_id == user.id

# API Routes للمهام
@task_bp.route('/api/tasks', methods=['GET'])
@login_required
def api_tasks():
    """API للحصول على قائمة المهام"""
    try:
        # الحصول على المهام حسب دور المستخدم
        if current_user.role == 'admin':
            tasks = Task.query.join(Project).filter(
                Project.org_id == current_user.org_id
            ).all()
        elif current_user.role == 'project_manager':
            tasks = Task.query.join(Project).filter(
                Project.project_manager_id == current_user.id
            ).all()
        elif current_user.role == 'supervisor':
            tasks = Task.query.filter_by(supervisor_id=current_user.id).all()
        elif current_user.role == 'delegate':
            tasks = Task.query.filter_by(delegate_id=current_user.id).all()
        else:  # employee
            tasks = Task.query.join(Task.assignments).filter(
                TaskAssignment.user_id == current_user.id
            ).all()
        
        tasks_data = [{
            'id': t.id,
            'task_code': t.task_code,
            'task_name': t.task_name,
            'status': t.status,
            'progress_percentage': t.progress_percentage,
            'planned_start_date': t.planned_start_date.isoformat() if t.planned_start_date else None,
            'planned_end_date': t.planned_end_date.isoformat() if t.planned_end_date else None,
            'actual_start_date': t.actual_start_date.isoformat() if t.actual_start_date else None,
            'actual_end_date': t.actual_end_date.isoformat() if t.actual_end_date else None,
            'supervisor': t.supervisor.to_dict() if t.supervisor else None,
            'delegate': t.delegate.to_dict() if t.delegate else None,
            'project': {
                'id': t.project.id,
                'name': t.project.name,
                'project_code': t.project.project_code
            }
        } for t in tasks]
        
        return jsonify({'success': True, 'tasks': tasks_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@task_bp.route('/api/tasks/<int:task_id>', methods=['GET'])
@login_required
def api_task_detail(task_id):
    """API للحصول على تفاصيل المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        # التحقق من الصلاحية
        if not has_task_access(task, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        task_data = {
            'id': task.id,
            'task_code': task.task_code,
            'task_name': task.task_name,
            'task_name_ar': task.task_name_ar,
            'description': task.description,
            'instructions': task.instructions,
            'status': task.status,
            'progress_percentage': task.progress_percentage,
            'planned_start_date': task.planned_start_date.isoformat() if task.planned_start_date else None,
            'planned_end_date': task.planned_end_date.isoformat() if task.planned_end_date else None,
            'actual_start_date': task.actual_start_date.isoformat() if task.actual_start_date else None,
            'actual_end_date': task.actual_end_date.isoformat() if task.actual_end_date else None,
            'planned_duration': task.planned_duration,
            'actual_duration': task.actual_duration,
            'estimated_effort': task.estimated_effort,
            'location': task.location,
            'coordinates': task.coordinates,
            'supervisor': task.supervisor.to_dict() if task.supervisor else None,
            'delegate': task.delegate.to_dict() if task.delegate else None,
            'project': {
                'id': task.project.id,
                'name': task.project.name,
                'project_code': task.project.project_code
            },
            'assignments': [{
                'id': a.id,
                'user': a.user.to_dict(),
                'status': a.status,
                'assigned_at': a.assigned_at.isoformat() if a.assigned_at else None,
                'completion_date': a.completion_date.isoformat() if a.completion_date else None
            } for a in task.assignments],
            'required_skills': task.required_skills or [],
            'required_materials': task.required_materials or [],
            'required_equipment': task.required_equipment or []
        }
        
        return jsonify({'success': True, 'task': task_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@task_bp.route('/api/tasks/<int:task_id>/progress', methods=['POST'])
@login_required
def api_update_task_progress(task_id):
    """API لتحديث تقدم المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        # التحقق من الصلاحية
        if not can_update_progress(task, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        progress = data.get('progress_percentage')
        notes = data.get('notes', '')
        
        if progress is not None:
            # تحديث تقدم المهمة
            if task.update_progress(float(progress), current_user.id):
                if notes:
                    progress_update = TaskProgressUpdate(
                        task_id=task_id,
                        progress_percentage=float(progress),
                        updated_by=current_user.id,
                        notes=notes
                    )
                    db.session.add(progress_update)
                
                db.session.commit()
                
                return jsonify({
                    'success': True,
                    'message': 'تم تحديث تقدم المهمة',
                    'progress_percentage': task.progress_percentage
                }), 200
            else:
                return jsonify({'error': 'لا يمكن تحديث التقدم'}), 400
        else:
            return jsonify({'error': 'قيمة التقدم مطلوبة'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@task_bp.route('/api/tasks/<int:task_id>/start', methods=['POST'])
@login_required
def api_start_task(task_id):
    """API لبدء المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        # التحقق من الصلاحية
        if not can_start_task(task, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        if task.start_task():
            db.session.commit()
            return jsonify({'success': True, 'message': 'تم بدء المهمة بنجاح'}), 200
        else:
            return jsonify({'error': 'لا يمكن بدء المهمة في حالتها الحالية'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@task_bp.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
def api_complete_task(task_id):
    """API لإكمال المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        # التحقق من الصلاحية
        if not can_complete_task(task, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        quality = data.get('quality', 'good')
        notes = data.get('notes')
        
        if task.complete_task(quality=quality):
            db.session.commit()
            return jsonify({'success': True, 'message': 'تم إكمال المهمة بنجاح'}), 200
        else:
            return jsonify({'error': 'لا يمكن إكمال المهمة في حالتها الحالية'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@task_bp.route('/api/tasks/<int:task_id>/assignments', methods=['POST'])
@login_required
def api_assign_task(task_id):
    """API لتعيين مستخدم للمهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        # التحقق من الصلاحية
        if not can_assign_task(task, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'error': 'يجب اختيار مستخدم'}), 400
        
        user = User.query.get_or_404(user_id)
        
        # التحقق من عدم تكرار التعيين
        existing_assignment = TaskAssignment.query.filter_by(
            task_id=task_id,
            user_id=user_id
        ).first()
        
        if existing_assignment:
            return jsonify({'error': 'المستخدم معين بالفعل لهذه المهمة'}), 400
        
        # إنشاء التعيين
        assignment = task.assign_user(user_id, current_user.id)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم تعيين المستخدم بنجاح',
            'assignment': {
                'id': assignment.id,
                'user': user.to_dict()
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
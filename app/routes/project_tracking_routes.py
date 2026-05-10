"""
project_tracking_routes.py - نظام تتبع وتنفيذ المشاريع
"""
from ..extensions import db
from flask import render_template, request, redirect, url_for, flash, jsonify, g
from flask_login import login_required, current_user
from app.models import  User, Project, Task, TaskAssignment, Notification, DailyReport,Organization,TaskProgressUpdate,Activity
from app.models import  TaskRequirement,TaskRequirementVerification,TaskSafetyCheck,TaskMaterialCheck,Resource,ResourceDelivery

from app.routes import tracking_bp
from datetime import datetime, date, timedelta
from sqlalchemy import func,case, and_, or_
from app.services.notification_service import NotificationService
import json

# ============================================
# لوحة تحكم تقدم المشروع للمدير العام
# ============================================

@tracking_bp.before_request
def load_tracking_data():
    """تحميل بيانات التتبع للمستخدم"""
    if current_user.is_authenticated:
        g.user = current_user
        g.company = Organization.query.get(current_user.org_id)
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        g.pending_deliveries_count = ResourceDelivery.query.filter_by(
            status='pending'
        ).count() if current_user.role in ['org_admin', 'project_manager'] else 0
        
        # إضافة إحصائيات الموارد
        g.low_stock_resources = Resource.query.filter(
            Resource.available_quantity < Resource.minimum_quantity
        ).count() if hasattr(Resource, 'minimum_quantity') else 0
        # عدد المهام المتأخرة للعرض في الشريط الجانبي
        from datetime import date
        from app.models.task_models import Task, TaskPlanning
        
        if current_user.role in ['org_admin', 'project_manager']:
            # ✅ الطريقة الصحيحة - باستخدام Task.is_delayed property
            active_tasks = Task.query.join(Project).filter(
                Project.org_id == current_user.org_id,
                Task.status.in_(['pending', 'in_progress'])
            ).all()
            
            g.delayed_tasks_count = sum(1 for task in active_tasks if task.is_delayed)
            
            # ✅ أو الطريقة المباشرة مع join (أكثر كفاءة)
            # g.delayed_tasks_count = Task.query\
            #     .join(Project)\
            #     .join(TaskPlanning, Task.planning)\
            #     .filter(
            #         Project.org_id == current_user.org_id,
            #         Task.status.in_(['pending', 'in_progress']),
            #         TaskPlanning.planned_finish < date.today()
            #     )\
            #     .count()
        else:
            g.delayed_tasks_count = 0
            
    else:
        g.user = None
        g.company = None
        g.delayed_tasks_count = 0
        g.notifications_count = 0
        g.pending_deliveries_count=0
        g.low_stock_resources=0

# @company_bp.before_request
# def load_company():
#     if current_user.is_authenticated:
#         g.company = Organization.query.get(current_user.org_id)
#         g.notifications_count = Notification.query.filter_by(
#             user_id=current_user.id, 
#             is_read=False
#         ).count()
#         g.delayed_tasks_count = Task.query.join(Project).filter(
#             Task.status.in_(['pending', 'in_progress']),
#             Task.planned_end_date < date.today()
#         ).count()
#     else:
#         g.company = None
#         g.delayed_tasks_count = 0
#         g.notifications_count = 0

@tracking_bp.route('/project/<int:project_id>/overview')
@login_required
def project_overview(project_id):
    """عرض نظرة شاملة على تقدم المشروع - للمدير العام ومدير المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not can_view_project_tracking(project, current_user):
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # إحصائيات المهام
    tasks = Task.query.filter_by(project_id=project_id).all()
    
    task_stats = {
        'total': len(tasks),
        'completed': len([t for t in tasks if t.status == 'completed']),
        'in_progress': len([t for t in tasks if t.status == 'in_progress']),
        'pending': len([t for t in tasks if t.status == 'pending']),
        'delayed': len([t for t in tasks if t.status in ['pending', 'in_progress'] and 
                        t.task.planned_finish and t.task.planned_finish < date.today()])
    }
    
    # تحليل التأخيرات
    delayed_tasks = []
    for task in tasks:
        if task.status in ['pending', 'in_progress'] and task.task.planned_finish:
            if task.task.planned_finish < date.today():
                delay_days = (date.today() - task.task.planned_finish).days
                delayed_tasks.append({
                    'id': task.id,
                    'name': task.task_name,
                    'code': task.task_code,
                    'planned_end': task.task.planned_finish,
                    'delay_days': delay_days,
                    'status': task.status,
                    'responsible': task.delegate.full_name if task.delegate else task.supervisor.full_name if task.supervisor else 'غير معين',
                    'progress': task.task.progress_percentage
                })
    
    # المسار الحرج (المهام المتسلسلة)
    critical_path = get_critical_path(project_id)
    
    # أداء الموظفين
    employee_performance = get_employee_performance(project_id)
    
    # التقدم الزمني
    time_progress = calculate_time_progress(project)
    
    return render_template('tracking/project_overview.html',
                         project=project,
                         task_stats=task_stats,
                         delayed_tasks=delayed_tasks,
                         critical_path=critical_path,
                         employee_performance=employee_performance,
                         time_progress=time_progress)

def can_view_project_tracking(project, user):
    """التحقق من صلاحية مشاهدة تقدم المشروع"""
    if user.role == 'platform_admin':
        return True
    if user.role == 'org_admin' and project.org_id == user.org_id:
        return True
    if user.role == 'project_manager' and project.checked_out_by == user.id:
        return True
    return False

def get_critical_path(project_id):
    """استخراج المسار الحرج للمشروع"""
    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.task_order).all()
    
    # بناء خريطة التبعيات
    task_map = {task.id: task for task in tasks}
    dependencies = {}
    
    for task in tasks:
        if task.depends_on_task_id:
            if task.depends_on_task_id not in dependencies:
                dependencies[task.depends_on_task_id] = []
            dependencies[task.depends_on_task_id].append(task.id)
    
    # حساب المسار الحرج (تبسيط - في التطبيق الفعلي استخدم خوارزمية CPM)
    critical_path = []
    current_task = next((t for t in tasks if t.task_order == 1), None)
    
    while current_task:
        critical_path.append({
            'id': current_task.id,
            'name': current_task.task_name,
            'code': current_task.task_code,
            'status': current_task.status,
            'planned_end': current_task.task.planned_finish,
            'actual_end': current_task.task.actual_finish,
            'is_delayed': current_task.status not in ['completed'] and 
                          current_task.task.planned_finish and 
                          current_task.task.planned_finish < date.today()
        })
        
        # الانتقال إلى المهمة التالية
        next_task_id = dependencies.get(current_task.id, [None])[0]
        current_task = task_map.get(next_task_id) if next_task_id else None
    
    return critical_path

def get_employee_performance(project_id):
    """تحليل أداء الموظفين في المشروع"""
    assignments = db.session.query(
        User.id,
        User.full_name,
        User.role,
        func.count(TaskAssignment.id).label('total_tasks'),
        func.sum(case((Task.status == 'completed', 1), else_=0)).label('completed_tasks'),
        func.avg(TaskAssignment.quality_rating).label('avg_quality'),
        func.avg(TaskAssignment.efficiency_rating).label('avg_efficiency')
    ).join(TaskAssignment, User.id == TaskAssignment.user_id)\
     .join(Task, TaskAssignment.task_id == Task.id)\
     .filter(Task.project_id == project_id)\
     .group_by(User.id, User.full_name, User.role).all()
    
    performance = []
    for emp in assignments:
        completion_rate = (emp.completed_tasks / emp.total_tasks * 100) if emp.total_tasks > 0 else 0
        performance.append({
            'id': emp.id,
            'name': emp.full_name,
            'role': emp.role,
            'total_tasks': emp.total_tasks,
            'completed_tasks': emp.completed_tasks,
            'completion_rate': completion_rate,
            'avg_quality': emp.avg_quality or 0,
            'avg_efficiency': emp.avg_efficiency or 0
        })
    
    return sorted(performance, key=lambda x: x['completion_rate'], reverse=True)

def calculate_time_progress(project):
    """حساب التقدم الزمني للمشروع"""
    if not project.planned_start_date or not project.planned_end_date:
        return {'planned': 0, 'actual': 0, 'status': 'unknown'}
    
    total_days = (project.project.planned_finish - project.project.planned_start).days
    elapsed_days = (date.today() - project.project.planned_start).days
    
    planned_progress = (elapsed_days / total_days * 100) if total_days > 0 else 0
    
    return {
        'planned': min(100, planned_progress),
        'actual': project.project.progress_percentage,
        'status': 'ahead' if project.project.progress_percentage > planned_progress + 5 else
                 'behind' if project.project.progress_percentage < planned_progress - 5 else
                 'on_track'
    }

# ============================================
# مسار تنفيذ المهمة للموظف
# ============================================

@tracking_bp.route('/task/<int:task_id>/execute')
@login_required
def execute_task(task_id):
    """صفحة تنفيذ المهمة للموظف المعين"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من أن المستخدم هو المنفذ
    if not is_task_executor(task, current_user):
        flash('غير مصرح بتنفيذ هذه المهمة', 'danger')
        return redirect(url_for('employee.my_tasks'))
    
    # الحصول على المهام السابقة والتالية
    previous_task = Task.query.get(task.depends_on_task_id) if task.depends_on_task_id else None
    next_tasks = Task.query.filter_by(depends_on_task_id=task.id).all()
    
    return render_template('tracking/execute_task.html',
                         task=task,
                         previous_task=previous_task,
                         next_tasks=next_tasks)

def is_task_executor(task, user):
    """التحقق من أن المستخدم هو المنفذ المسؤول عن المهمة"""
    if task.delegate_id == user.id:
        return True
    if task.supervisor_id == user.id:
        return True
    assignment = TaskAssignment.query.filter_by(
        task_id=task.id,
        user_id=user.id
    ).first()
    return assignment is not None

@tracking_bp.route('/pending-verifications')
@login_required
def pending_verifications():
    """عرض طلبات التحقق المعلقة للمشرف"""
    if current_user.role not in ['org_admin', 'project_manager', 'supervisor']:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # طلبات التحقق للمهام التي يشرف عليها المستخدم
    pending_verifications = TaskRequirementVerification.query.filter_by(
        status='pending'
    ).join(TaskRequirement).join(Task).filter(
        Task.supervisor_id == current_user.id
    ).order_by(TaskRequirementVerification.submitted_at.desc()).all()
    
    return render_template('tracking/pending_verifications.html',
                         pending_verifications=pending_verifications)
@tracking_bp.route('/api/task/<int:task_id>/add-requirement', methods=['POST'])
@login_required
def api_add_requirement(task_id):
    """API لإضافة متطلب إلى مهمة"""
    task = Task.query.get_or_404(task_id)
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin', 'project_manager'] and current_user.id != task.supervisor_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json() or request.form
    
    requirement = TaskRequirement(
        task_id=task_id,
        requirement_type=data.get('requirement_type', 'document'),
        description=data.get('description'),
        is_mandatory=data.get('is_mandatory', 'true').lower() == 'true',
        order=int(data.get('order', 0)),
        required_value=data.get('required_value'),
        validation_criteria=json.loads(data.get('validation_criteria', '{}'))
    )
    
    db.session.add(requirement)
    db.session.commit()
    
    # إشعار للمنفذ بوجود متطلبات جديدة
    if task.delegate_id:
        notification = Notification(
            user_id=task.delegate_id,
            title=f'📋 متطلبات جديدة: {task.task_name}',
            message=f'تم إضافة متطلب جديد: {requirement.description}',
            notification_type='new_requirement',
            related_task_id=task.id,
            related_project_id=task.project_id
        )
        db.session.add(notification)
        db.session.commit()
    
    return jsonify({
        'success': True,
        'requirement': {
            'id': requirement.id,
            'description': requirement.description,
            'type': requirement.requirement_type
        }
    })

@tracking_bp.route('/api/requirement/<int:req_id>/delete', methods=['POST'])
@login_required
def api_delete_requirement(req_id):
    """حذف متطلب"""
    requirement = TaskRequirement.query.get_or_404(req_id)
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin', 'project_manager'] and current_user.id != requirement.task.supervisor_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    db.session.delete(requirement)
    db.session.commit()
    
    return jsonify({'success': True})
# ============================================
# API بدء المهمة
# ============================================

# @tracking_bp.route('/api/task/<int:task_id>/start', methods=['POST'])
# @login_required
# def api_start_task(task_id):
#     """API لبدء تنفيذ المهمة"""
    
#     task = Task.query.get_or_404(task_id)
    
#     if not is_task_executor(task, current_user):
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     if task.status != 'pending':
#         return jsonify({'error': 'لا يمكن بدء مهمة بهذه الحالة'}), 400
    
#     # بدء المهمة
#     task.status = 'in_progress'
#     task.actual_start_date = datetime.utcnow()
#     task.progress_percentage = 1
#     db.session.commit()
#     NotificationService.task_started(task, current_user.id)

    # # إرسال إشعار لمدير المشروع
    # notification = Notification(
    #     user_id=task.project.project_manager_id,
    #     title=f'✅ بدء تنفيذ مهمة: {task.task_name}',
    #     message=f'تم بدء تنفيذ مهمة {task.task_code} بواسطة {current_user.full_name}',
    #     notification_type='task_started',
    #     related_task_id=task.id,
    #     related_project_id=task.project_id,
    #     created_at=datetime.utcnow()
    # )
    # db.session.add(notification)
    
    # # إشعار للمدير العام (صاحب الشركة)
    # org_admins = User.query.filter_by(
    #     org_id=task.project.org_id,
    #     role='org_admin'
    # ).all()
    
    # for admin in org_admins:
    #     if admin.id != task.project.project_manager_id:
    #         notif = Notification(
    #             user_id=admin.id,
    #             title=f'🚀 بدء مهمة: {task.task_name}',
    #             message=f'تم بدء مهمة {task.task_code} في مشروع {task.project.name}',
    #             notification_type='task_started',
    #             related_task_id=task.id,
    #             related_project_id=task.project_id,
    #             created_at=datetime.utcnow()
    #         )
    #         db.session.add(notif)
    
    # db.session.commit()
    
    # return jsonify({
    #     'success': True,
    #     'message': 'تم بدء المهمة بنجاح',
    #     'task': {
    #         'id': task.id,
    #         'status': task.status,
    #         'start_time': task.actual_start_date.strftime('%Y-%m-%d %H:%M:%S')
    #     }
    # })

@tracking_bp.route('/api/task/<int:task_id>/start', methods=['POST'])
@login_required
def api_start_task(task_id):
    """بدء تنفيذ المهمة مع التحقق من المتطلبات"""
    
    task = Task.query.get_or_404(task_id)
    
    if not (current_user.id == task.delegate_id or 
            current_user.id == task.supervisor_id or 
            current_user.role == 'org_admin'):
        return jsonify({'error': 'غير مصرح'}), 403
    
    if task.status != 'pending':
        return jsonify({'error': 'لا يمكن بدء مهمة بهذه الحالة'}), 400
    
    # التحقق من اكتمال المتطلبات
    can_start, message = task.can_start()
    
    if not can_start:
        return jsonify({
            'error': 'لا يمكن بدء المهمة',
            'message': message,
            'redirect': url_for('tracking.task_requirements', task_id=task.id)
        }), 400
    
    # بدء المهمة
    task.status = 'in_progress'
    task.task.actual_start = datetime.utcnow()
    task.task.progress_percentage = 1
    db.session.commit()
    
    # إضافة إشعار بدء المهمة
    from app.services.notification_service import NotificationService
    NotificationService.task_started(task, current_user.id)
    
    return jsonify({
        'success': True,
        'message': 'تم بدء المهمة بنجاح',
        'task': {
            'id': task.id,
            'status': task.status,
            'start_time': task.task.actual_start.strftime('%Y-%m-%d %H:%M:%S')
        }
    })
# ============================================
# API إكمال المهمة
# ============================================

@tracking_bp.route('/api/task/<int:task_id>/complete', methods=['POST'])
@login_required
def api_complete_task(task_id):
    """API لإكمال المهمة"""
    
    task = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    
    if not is_task_executor(task, current_user):
        return jsonify({'error': 'غير مصرح'}), 403
    
    if task.status != 'in_progress':
        return jsonify({'error': 'لا يمكن إكمال مهمة بهذه الحالة'}), 400
    
    # إكمال المهمة
    task.status = 'completed'
    task.task.actual_finish = datetime.utcnow()
    task.task.progress_percentage = 100
    task.completion_quality = data.get('quality', 'good')
    
    # حساب المدة الفعلية
    if task.actual_start:
        duration = task.task.actual_finish - task.task.actual_start
        task.task.actual_duration = duration.total_seconds() / 3600
    
    db.session.commit()

    # إضافة إشعار إكمال المهمة
    NotificationService.task_completed(task, current_user.id, data.get('quality', 'good'))
    # # إشعار للمشرف
    # if task.supervisor_id and task.supervisor_id != current_user.id:
    #     notification = Notification(
    #         user_id=task.supervisor_id,
    #         title=f'✅ اكتمال مهمة: {task.task_name}',
    #         message=f'تم إكمال مهمة {task.task_code} بنجاح بواسطة {current_user.full_name}',
    #         notification_type='task_completed',
    #         related_task_id=task.id,
    #         related_project_id=task.project_id,
    #         created_at=datetime.utcnow()
    #     )
    #     db.session.add(notification)
    
    # # إشعار لمدير المشروع
    # if task.project.project_manager_id not in [task.supervisor_id, current_user.id]:
    #     notification = Notification(
    #         user_id=task.project.project_manager_id,
    #         title=f'🎉 اكتمال مهمة: {task.task_name}',
    #         message=f'تم إكمال مهمة {task.task_code} في مشروع {task.project.name}',
    #         notification_type='task_completed',
    #         related_task_id=task.id,
    #         related_project_id=task.project_id,
    #         created_at=datetime.utcnow()
    #     )
    #     db.session.add(notification)
    
    # # إشعار للمدير العام
    # org_admins = User.query.filter_by(
    #     org_id=task.project.org_id,
    #     role='org_admin'
    # ).filter(User.id.notin_([task.project.project_manager_id, task.supervisor_id or 0, current_user.id])).all()
    
    # for admin in org_admins:
    #     notification = Notification(
    #         user_id=admin.id,
    #         title=f'📊 اكتمال مهمة في مشروع {task.project.name}',
    #         message=f'تم إكمال مهمة {task.task_code} - {task.task_name}',
    #         notification_type='task_completed',
    #         related_task_id=task.id,
    #         related_project_id=task.project_id,
    #         created_at=datetime.utcnow()
    #     )
    #     db.session.add(notification)
    
    # بدء المهام التالية إذا كان ذلك مناسباً
    start_next_tasks(task)
    
    db.session.commit()
    
    # حساب وقت التنفيذ
    execution_time = None
    if task.task.actual_duration:
        hours = int(task.task.actual_duration)
        minutes = int((task.task.actual_duration - hours) * 60)
        execution_time = f"{hours} ساعة و {minutes} دقيقة"
    
    return jsonify({
        'success': True,
        'message': 'تم إكمال المهمة بنجاح',
        'task': {
            'id': task.id,
            'status': task.status,
            'end_time': task.task.actual_finish.strftime('%Y-%m-%d %H:%M:%S'),
            'execution_time': execution_time
        }
    })

def start_next_tasks(completed_task):
    """بدء المهام التالية بعد اكتمال المهمة الحالية"""
    next_tasks = Task.query.filter_by(depends_on_task_id=completed_task.id).all()
    
    for next_task in next_tasks:
        # التحقق من أن جميع المهام السابقة مكتملة
        predecessor = Task.query.get(next_task.depends_on_task_id)
        if predecessor and predecessor.status == 'completed':
            if next_task.status == 'pending':
                # إرسال إشعار للمنفذ بأن المهمة جاهزة للبدء
                if next_task.delegate_id:
                    notification = Notification(
                        user_id=next_task.delegate_id,
                        title=f'🔔 مهمة جاهزة للبدء: {next_task.task_name}',
                        message=f'مهمة {next_task.task_code} جاهزة للبدء. المهمة السابقة {completed_task.task_code} اكتملت.',
                        notification_type='task_ready',
                        related_task_id=next_task.id,
                        related_project_id=next_task.project_id
                    )
                    db.session.add(notification)

# ============================================
# API تحديث تقدم المهمة
# ============================================

@tracking_bp.route('/api/task/<int:task_id>/progress', methods=['POST'])
@login_required
def api_update_progress(task_id):
    """API لتحديث تقدم المهمة"""
    
    task = Task.query.get_or_404(task_id)
    data = request.get_json()
    
    if not is_task_executor(task, current_user):
        return jsonify({'error': 'غير مصرح'}), 403
    
    progress = data.get('progress', 0)
    notes = data.get('notes', '')
    
    # حفظ تحديث التقدم
    progress_update = TaskProgressUpdate(
        task_id=task.id,
        progress_percentage=progress,
        updated_by=current_user.id,
        notes=notes
    )
    db.session.add(progress_update)
    
    # تحديث المهمة
    old_progress = task.task.progress_percentage
    task.task.progress_percentage = progress
    
    # إذا كان التقدم 100%، أكمل المهمة
    if progress >= 100:
        return api_complete_task(task_id)
    
    db.session.commit()
    
    # إشعار للمشرف إذا كان التقدم كبيراً
    if progress - old_progress >= 25 and task.supervisor_id:
        notification = Notification(
            user_id=task.supervisor_id,
            title=f'📈 تقدم مهمة: {task.task_name}',
            message=f'تقدم المهمة {task.task_code} وصل إلى {progress}%',
            notification_type='task_progress',
            related_task_id=task.id,
            related_project_id=task.project_id,
            created_by=current_user.id
        )
        db.session.add(notification)
        db.session.commit()
    
    return jsonify({
        'success': True,
        'message': 'تم تحديث التقدم',
        'progress': progress
    })

# ============================================
# صفحة تتبع المهام للمشرف
# ============================================

@tracking_bp.route('/project/<int:project_id>/tasks-tracking')
@login_required
def tasks_tracking(project_id):
    """صفحة تتبع جميع مهام المشروع للمشرفين ومدير المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    if not can_view_project_tracking(project, current_user):
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # جميع المهام مع معلومات التنفيذ
    tasks = Task.query.filter_by(project_id=project_id).order_by(Task.task_order).all()
    
    task_data = []
    for task in tasks:
        # حساب وقت التنفيذ
        execution_time = None
        if task.task.actual_start and task.task.actual_finish:
            delta = task.task.actual_finish - task.task.actual_start
            execution_time = delta.total_seconds() / 3600  # بالساعات
        
        # تحديد التأخير
        is_delayed = False
        delay_days = 0
        if task.status != 'completed' and task.task.planned_finish:
            if task.task.planned_finish < date.today():
                is_delayed = True
                delay_days = (date.today() - task.task.planned_finish).days
        elif task.status == 'completed' and task.task.planned_finish and task.task.actual_finish:
            if task.task.actual_finish.date() > task.task.planned_finish:
                is_delayed = True
                delay_days = (task.task.actual_finish.date() - task.task.planned_finish).days
        
        task_data.append({
            'id': task.id,
            'code': task.task_code,
            'name': task.task_name,
            'status': task.status,
            'progress': task.task.progress_percentage,
            'planned_start': task.task.planned_start,
            'planned_end': task.task.planned_finish,
            'actual_start': task.task.actual_start,
            'actual_end': task.task.actual_finish,
            'execution_time': execution_time,
            'is_delayed': is_delayed,
            'delay_days': delay_days,
            'responsible': task.delegate.full_name if task.delegate else task.supervisor.full_name,
            'predecessor': Task.query.get(task.depends_on_task_id).task_code if task.depends_on_task_id else None
        })
    
    return render_template('tracking/tasks_tracking.html',
                         project=project,
                         tasks=task_data)

# ============================================
# تقرير التأخيرات
# ============================================

@tracking_bp.route('/delays-report')
@login_required
def delays_report():
    """تقرير بجميع التأخيرات في المشاريع - للمدير العام"""
    
    if current_user.role not in ['platform_admin', 'org_admin']:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # المشاريع النشطة
    projects = Project.query.filter_by(
        org_id=current_user.org_id,
        status='active'
    ).all() if current_user.role == 'org_admin' else Project.query.all()
    
    all_delays = []
    
    for project in projects:
        tasks = Task.query.filter_by(project_id=project.id).all()
        
        for task in tasks:
            delay_info = get_task_delay_info(task)
            if delay_info:
                all_delays.append({
                    'project_name': project.name,
                    'project_code': project.project_code,
                    'task_id': task.id,
                    'task_code': task.task_code,
                    'task_name': task.task_name,
                    'responsible': task.delegate.full_name if task.delegate else task.supervisor.full_name,
                    'planned_end': task.task.planned_finish,
                    'delay_days': delay_info['days'],
                    'current_status': task.status,
                    'progress': task.task.progress_percentage,
                    'delay_reason': get_delay_reason(task)
                })
    
    # ترتيب حسب أكثر تأخير
    all_delays.sort(key=lambda x: x['delay_days'], reverse=True)
    
    return render_template('tracking/delays_report.html',
                         delays=all_delays,
                         total_delays=len(all_delays))

def get_task_delay_info(task):
    """الحصول على معلومات التأخير للمهمة"""
    if task.status == 'completed':
        if task.execution.actual_finish and task.planning.planned_finish:
            if task.execution.actual_finish.date() > task.planning.planned_finish:
                days = (task.execution.actual_finish.date() - task.planning.planned_finish).days
                return {'days': days, 'type': 'completion_delay'}
    else:
        if task.planning.planned_finish and task.planning.planned_finish < date.today():
            days = (date.today() - task.planning.planned_finish).days
            return {'days': days, 'type': 'ongoing_delay'}
    return None

def get_delay_reason(task):
    """تحديد سبب التأخير (يمكن توسيعها لاحقاً)"""
    if task.issues:
        return "موجود في المهام المتأخرة"
    return "غير محدد"

def has_task_access(task, user):
    """التحقق من صلاحية الوصول للمهمة"""
    if user.role == 'admin' or user.role == 'org_admin':
        return task.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return task.project.checked_out_by == user.id
    elif user.role == 'supervisor':
        return task.supervisor_id == user.id
    elif user.role == 'delegate':
        return task.delegate_id == user.id
    else:  # employee
        return any(assignment.user_id == user.id for assignment in task.assignments)
    return False

@tracking_bp.route('/task/<int:task_id>/requirements')
@login_required
def task_requirements(task_id):
    """صفحة متطلبات المهمة"""
    task = Task.query.get_or_404(task_id)
    
    if not has_task_access(task, current_user):
        flash('غير مصرح', 'danger')
        return redirect(url_for('employee.my_tasks'))
    
    requirements = TaskRequirement.query.filter_by(task_id=task_id, is_active=True).order_by(TaskRequirement.order).all()
    
    # جلب حالة التحقق لكل متطلب
    for req in requirements:
        req.verification = TaskRequirementVerification.query.filter_by(
            requirement_id=req.id
        ).order_by(TaskRequirementVerification.submitted_at.desc()).first()
    
    safety_checks = TaskSafetyCheck.query.filter_by(task_id=task_id).all()
    materials = TaskMaterialCheck.query.filter_by(task_id=task_id).all()
    
    can_start, message = task.can_start()
    
    return render_template('tracking/task_requirements.html',
                         task=task,
                         requirements=requirements,
                         safety_checks=safety_checks,
                         materials=materials,
                         can_start=can_start,
                         message=message)

@tracking_bp.route('/api/task/<int:task_id>/submit-verification', methods=['POST'])
@login_required
def api_submit_verification(task_id):
    """تقديم طلب تحقق"""
    task = Task.query.get_or_404(task_id)
    
    if not is_task_executor(task, current_user):
        return jsonify({'error': 'غير مصرح'}), 403
    
    requirement_id = request.form.get('requirement_id')
    value = request.form.get('value')
    notes = request.form.get('notes')
    file = request.files.get('file')
    photo = request.files.get('photo')
    
    verification = task.submit_verification(
        requirement_id=requirement_id,
        user_id=current_user.id,
        value=value,
        file=file,
        photo=photo,
        notes=notes
    )
    
    return jsonify({
        'success': True,
        'verification_id': verification.id,
        'status': verification.status
    })

@tracking_bp.route('/api/task/<int:task_id>/verify-requirement/<int:verification_id>', methods=['POST'])
@login_required
def api_verify_requirement(task_id, verification_id):
    """الموافقة على طلب تحقق (للمشرف)"""
    task = Task.query.get_or_404(task_id)
    
    if current_user.id != task.supervisor_id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    approve = data.get('approve', True)
    notes = data.get('notes')
    
    verification = task.verify_requirement(
        verification_id=verification_id,
        verifier_id=current_user.id,
        approve=approve,
        notes=notes
    )
    
    return jsonify({
        'success': True,
        'status': verification.status
    })

# @tracking_bp.route('/api/task/<int:task_id>/add-requirement', methods=['POST'])
# @login_required
# def api_add_requirement(task_id):
#     """إضافة متطلب جديد (للمشرف)"""
#     task = Task.query.get_or_404(task_id)
    
#     if current_user.id != task.supervisor_id and current_user.role != 'org_admin':
#         return jsonify({'error': 'غير مصرح'}), 403
    
#     data = request.get_json()
    
#     requirement = task.add_requirement(
#         req_type=data.get('requirement_type'),
#         description=data.get('description'),
#         is_mandatory=data.get('is_mandatory', True),
#         order=data.get('order', 0)
#     )
    
#     return jsonify({
#         'success': True,
#         'requirement': {
#             'id': requirement.id,
#             'description': requirement.description,
#             'type': requirement.requirement_type
#         }
#     })

@tracking_bp.route('/api/task/<int:task_id>/check-readiness')
@login_required
def api_check_readiness(task_id):
    """التحقق من جاهزية المهمة"""
    task = Task.query.get_or_404(task_id)
    
    if not is_task_executor(task, current_user):
        return jsonify({'error': 'غير مصرح'}), 403
    
    can_start, message = task.can_start()
    pending_reqs = task.get_pending_requirements()
    
    return jsonify({
        'success': True,
        'can_start': can_start,
        'message': message,
        'pending_count': len(pending_reqs),
        'pending_requirements': [{
            'id': r.id,
            'description': r.description,
            'type': r.requirement_type
        } for r in pending_reqs]
    })
# ============================================
# API الإحصائيات للمدير العام
# ============================================

@tracking_bp.route('/api/executive-dashboard')
@login_required
def api_executive_dashboard():
    """API لوحة التحكم التنفيذية للمدير العام"""
    
    if current_user.role not in ['platform_admin', 'org_admin']:
        return jsonify({'error': 'غير مصرح'}), 403
    
    org_id = current_user.org_id if current_user.role == 'org_admin' else None
    
    # المشاريع النشطة
    projects_query = Project.query
    if org_id:
        projects_query = projects_query.filter_by(org_id=org_id)
    active_projects = projects_query.filter_by(status='active').all()
    
    # إحصائيات عامة
    total_tasks = 0
    completed_tasks = 0
    delayed_tasks = 0
    total_execution_time = 0
    completed_execution_time = 0
    
    for project in active_projects:
        tasks = Task.query.filter_by(project_id=project.id).all()
        total_tasks += len(tasks)
        completed_tasks += len([t for t in tasks if t.status == 'completed'])
        
        for task in tasks:
            if task.status != 'completed' and task.task.planned_finish and task.task.planned_finish < date.today():
                delayed_tasks += 1
            
            if task.task.actual_duration:
                total_execution_time += task.task.actual_duration
                if task.status == 'completed':
                    completed_execution_time += task.task.actual_duration
    
    return jsonify({
        'success': True,
        'stats': {
            'active_projects': len(active_projects),
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            'delayed_tasks': delayed_tasks,
            'delay_rate': (delayed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            'avg_execution_time': (total_execution_time / completed_tasks) if completed_tasks > 0 else 0
        },
        'projects': [{
            'id': p.id,
            'name': p.name,
            'progress': p.task.progress_percentage,
            'tasks_count': Task.query.filter_by(project_id=p.id).count(),
            'delayed_tasks': Task.query.filter(
                Task.project_id == p.id,
                Task.status != 'completed',
                Task.task.planned_finish < date.today()
            ).count()
        } for p in active_projects]
    })


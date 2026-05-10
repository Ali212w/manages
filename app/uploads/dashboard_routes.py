"""
dashboard_routes.py - مسارات لوحة التحكم
"""
from flask import render_template, request, jsonify, flash,redirect,url_for
from flask_login import login_required, current_user
from app.models import db, Project, Task, Notification, User,TaskAssignment
from datetime import datetime, date, timedelta
from app.routes import dashboard_bp
import json
from app.utils.userOrg import is_user,is_organ

def user_check():
    user = None
    organ = None

    if is_user():
        user = current_user.id
    elif is_organ():
        organ = current_user.id
    return user, organ

@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    """لوحة التحكم الرئيسية"""
    
    # إحصائيات حسب دور المستخدم
    if current_user.role == 'admin' or current_user.role == 'admin_org':
        projects = Project.query.filter_by(org_id=current_user.id).all()
        total_projects = len(projects)
        active_projects = len([p for p in projects if p.status == 'active'])
        completed_projects = len([p for p in projects if p.status == 'completed'])
        
        stats = {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'total_users': User.query.filter_by(org_id=current_user.id).count(),
            'pending_tasks': Task.query.join(Project).filter(
                Project.org_id == current_user.id,
                Task.status == 'pending'
            ).count()
        }
        
        recent_projects = Project.query.filter_by(
            org_id=current_user.id
        ).order_by(Project.created_at.desc()).limit(5).all()
        
    elif current_user.role == 'project_manager':
        projects = Project.query.filter_by(project_manager_id=current_user.id).all()
        total_projects = len(projects)
        
        stats = {
            'total_projects': total_projects,
            'active_projects': len([p for p in projects if p.status == 'active']),
            'completed_projects': len([p for p in projects if p.status == 'completed']),
            'total_tasks': Task.query.join(Project).filter(
                Project.project_manager_id == current_user.id
            ).count(),
            'pending_tasks': Task.query.join(Project).filter(
                Project.project_manager_id == current_user.id,
                Task.status == 'pending'
            ).count()
        }
        
        recent_projects = Project.query.filter_by(
            project_manager_id=current_user.id
        ).order_by(Project.created_at.desc()).limit(5).all()
        
    elif current_user.role == 'supervisor':
        tasks = Task.query.filter_by(supervisor_id=current_user.id).all()
        
        stats = {
            'total_tasks': len(tasks),
            'active_tasks': len([t for t in tasks if t.status == 'in_progress']),
            'completed_tasks': len([t for t in tasks if t.status == 'completed']),
            'pending_tasks': len([t for t in tasks if t.status == 'pending']),
            'assigned_delegates': len(set([t.delegate_id for t in tasks if t.delegate_id]))
        }
        
        recent_projects = Project.query.join(Task).filter(
            Task.supervisor_id == current_user.id
        ).distinct().order_by(Project.created_at.desc()).limit(5).all()
        
    elif current_user.role == 'delegate':
        tasks = Task.query.filter_by(delegate_id=current_user.id).all()
        
        stats = {
            'total_tasks': len(tasks),
            'active_tasks': len([t for t in tasks if t.status == 'in_progress']),
            'completed_tasks': len([t for t in tasks if t.status == 'completed']),
            'pending_tasks': len([t for t in tasks if t.status == 'pending']),
            'assigned_workers': len(set([a.user_id for t in tasks for a in t.assignments]))
        }
        
        recent_projects = Project.query.join(Task).filter(
            Task.delegate_id == current_user.id
        ).distinct().order_by(Project.created_at.desc()).limit(5).all()
        
    else:  # employee
        # الحصول على المهام المعينة
        task_assignments = Task.query.join(Task.assignments).filter(
            TaskAssignment.user_id == current_user.id
        ).all()
        
        stats = {
            'assigned_tasks': len(task_assignments),
            'completed_tasks': len([t for t in task_assignments if t.status == 'completed']),
            'in_progress_tasks': len([t for t in task_assignments if t.status == 'in_progress']),
            'pending_tasks': len([t for t in task_assignments if t.status == 'pending'])
        }
        
        recent_projects = Project.query.join(Task).join(Task.assignments).filter(
            TaskAssignment.user_id == current_user.id
        ).distinct().order_by(Project.created_at.desc()).limit(5).all()
    
    # الإشعارات غير المقروءة
    notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(10).all()
    
    # المهام القادمة
    upcoming_tasks = []
    if current_user.role in ['employee', 'delegate', 'supervisor']:
        # الحصول على المهام حسب الدور
        if current_user.role == 'employee':
            tasks_query = Task.query.join(Task.assignments).filter(
                TaskAssignment.user_id == current_user.id,
                Task.status.in_(['pending', 'in_progress'])
            )
        elif current_user.role == 'delegate':
            tasks_query = Task.query.filter_by(
                delegate_id=current_user.id,
                status__in=['pending', 'in_progress']
            )
        else:  # supervisor
            tasks_query = Task.query.filter_by(
                supervisor_id=current_user.id,
                status__in=['pending', 'in_progress']
            )
        
        upcoming_tasks = tasks_query.order_by(
            Task.planned_start_date.asc()
        ).limit(5).all()
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_projects=recent_projects,
                         notifications=notifications,
                         upcoming_tasks=upcoming_tasks,
                         now=datetime.now())

@dashboard_bp.route('/notifications')
@login_required
def notifications():
    """صفحة الإشعارات"""
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('dashboard/notifications.html', notifications=notifications)

@dashboard_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """تحديد جميع الإشعارات كمقروءة"""
    try:
        notifications = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).all()
        
        for notification in notifications:
            notification.mark_as_read()
        
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True, 'message': 'تم تحديد جميع الإشعارات كمقروءة'})
        else:
            flash('تم تحديد جميع الإشعارات كمقروءة', 'success')
            return redirect(url_for('dashboard.notifications'))
            
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
            return redirect(url_for('dashboard.notifications'))

@dashboard_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """تحديد إشعار كمقروء"""
    try:
        notification = Notification.query.get_or_404(notification_id)
        
        # التحقق من ملكية الإشعار
        if notification.user_id != current_user.id:
            if request.is_json:
                return jsonify({'error': 'غير مصرح'}), 403
            else:
                flash('غير مصرح', 'danger')
                return redirect(url_for('dashboard.notifications'))
        
        notification.mark_as_read()
        db.session.commit()
        
        if request.is_json:
            return jsonify({'success': True})
        else:
            return redirect(url_for('dashboard.notifications'))
            
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
            return redirect(url_for('dashboard.notifications'))

@dashboard_bp.route('/calendar')
@login_required
def calendar():
    """تقويم المهام والمشاريع"""
    return render_template('dashboard/calendar.html')

@dashboard_bp.route('/calendar/events')
@login_required
def calendar_events():
    """الحصول على أحداث التقويم"""
    events = []
    
    # أحداث المشاريع حسب دور المستخدم
    if current_user.role == 'admin':
        projects = Project.query.filter_by(org_id=current_user.org_id).all()
    elif current_user.role == 'project_manager':
        projects = Project.query.filter_by(project_manager_id=current_user.id).all()
    else:
        projects = Project.query.join(Task).filter(
            (Task.supervisor_id == current_user.id) |
            (Task.delegate_id == current_user.id) |
            (Task.assignments.any(user_id=current_user.id))
        ).distinct().all()
    
    for project in projects:
        if project.planned_start_date and project.planned_end_date:
            events.append({
                'id': f'project_{project.id}',
                'title': project.name,
                'start': project.planned_start_date.isoformat(),
                'end': project.planned_end_date.isoformat(),
                'color': get_project_color(project.status),
                'url': url_for('project.view', project_id=project.id),
                'extendedProps': {
                    'type': 'project',
                    'status': project.status,
                    'progress': project.progress_percentage
                }
            })
    
    # أحداث المهام
    if current_user.role == 'employee':
        tasks = Task.query.join(Task.assignments).filter(
            TaskAssignment.user_id == current_user.id
        ).all()
    elif current_user.role == 'delegate':
        tasks = Task.query.filter_by(delegate_id=current_user.id).all()
    elif current_user.role == 'supervisor':
        tasks = Task.query.filter_by(supervisor_id=current_user.id).all()
    else:
        tasks = []
    
    for task in tasks:
        if task.planned_start_date and task.planned_end_date:
            events.append({
                'id': f'task_{task.id}',
                'title': task.task_name,
                'start': task.planned_start_date.isoformat(),
                'end': task.planned_end_date.isoformat(),
                'color': get_task_color(task.status),
                'url': url_for('task.view', task_id=task.id),
                'extendedProps': {
                    'type': 'task',
                    'status': task.status,
                    'project_id': task.project_id
                }
            })
    
    return jsonify(events)

def get_project_color(self, status):
    """الحصول على لون المشروع حسب الحالة"""
    colors = {
        'pending': '#ffc107',  # أصفر
        'planning': '#17a2b8',  # أزرق
        'active': '#28a745',    # أخضر
        'on_hold': '#6c757d',   # رمادي
        'completed': '#007bff',  # أزرق فاتح
        'cancelled': '#dc3545'   # أحمر
    }
    return colors.get(status, '#6c757d')

def get_task_color(self, status):
    """الحصول على لون المهمة حسب الحالة"""
    colors = {
        'pending': '#6c757d',   # رمادي
        'in_progress': '#28a745', # أخضر
        'completed': '#007bff',   # أزرق
        'on_hold': '#ffc107',    # أصفر
        'cancelled': '#dc3545'    # أحمر
    }
    return colors.get(status, '#6c757d')

@dashboard_bp.route('/analytics')
@login_required
def analytics():
    """التحليلات والإحصائيات"""
    
    # البيانات حسب دور المستخدم
    if current_user.role == 'admin':
        # إحصائيات المؤسسة
        projects = Project.query.filter_by(org_id=current_user.org_id).all()
        users = User.query.filter_by(org_id=current_user.org_id).all()
        
        analytics_data = {
            'projects_by_status': count_by_status(projects, 'status'),
            'projects_by_type': count_by_field(projects, 'project_type'),
            'users_by_role': count_by_field(users, 'role'),
            'monthly_projects': get_monthly_stats(projects),
            'financial_summary': get_financial_summary(projects)
        }
        
    elif current_user.role == 'project_manager':
        # إحصائيات مدير المشروع
        projects = Project.query.filter_by(project_manager_id=current_user.id).all()
        
        analytics_data = {
            'projects_by_status': count_by_status(projects, 'status'),
            'projects_by_type': count_by_field(projects, 'project_type'),
            'tasks_by_status': get_tasks_stats(current_user.id, 'project_manager'),
            'monthly_progress': get_monthly_progress(projects)
        }
        
    elif current_user.role == 'supervisor':
        # إحصائيات المشرف
        tasks = Task.query.filter_by(supervisor_id=current_user.id).all()
        
        analytics_data = {
            'tasks_by_status': count_by_status(tasks, 'status'),
            'tasks_by_project': count_tasks_by_project(current_user.id, 'supervisor'),
            'delegates_performance': get_delegates_performance(current_user.id),
            'monthly_completion': get_monthly_completion(tasks)
        }
        
    elif current_user.role == 'delegate':
        # إحصائيات المندوب
        tasks = Task.query.filter_by(delegate_id=current_user.id).all()
        
        analytics_data = {
            'tasks_by_status': count_by_status(tasks, 'status'),
            'workers_performance': get_workers_performance(current_user.id),
            'quality_scores': get_quality_scores(current_user.id),
            'monthly_productivity': get_monthly_productivity(tasks)
        }
        
    else:  # employee
        # إحصائيات الموظف
        tasks = Task.query.join(Task.assignments).filter(
            TaskAssignment.user_id == current_user.id
        ).all()
        
        analytics_data = {
            'tasks_by_status': count_by_status(tasks, 'status'),
            'completion_rate': get_completion_rate(tasks),
            'quality_scores': get_employee_quality_scores(current_user.id),
            'monthly_work_hours': get_monthly_work_hours(current_user.id)
        }
    
    return render_template('dashboard/analytics.html', analytics_data=analytics_data)

def count_by_status(self, items, status_field):
    """عد العناصر حسب الحالة"""
    counts = {}
    for item in items:
        status = getattr(item, status_field, 'unknown')
        counts[status] = counts.get(status, 0) + 1
    return counts

def count_by_field(self, items, field):
    """عد العناصر حسب الحقل"""
    counts = {}
    for item in items:
        value = getattr(item, field, 'غير محدد')
        if not value:
            value = 'غير محدد'
        counts[value] = counts.get(value, 0) + 1
    return counts

def get_monthly_stats(self, projects):
    """الحصول على إحصائيات شهرية"""
    monthly = {}
    for project in projects:
        if project.created_at:
            month_key = project.created_at.strftime('%Y-%m')
            monthly[month_key] = monthly.get(month_key, 0) + 1
    
    return monthly

def get_financial_summary(self, projects):
    """ملخص مالي للمشاريع"""
    total_contract_value = sum(p.contract_value for p in projects if p.contract_value)
    total_invoiced = 0
    total_paid = 0
    
    # حساب الفواتير والمدفوعات
    for project in projects:
        if hasattr(project, 'invoices'):
            for invoice in project.invoices:
                total_invoiced += invoice.total_amount or 0
                total_paid += invoice.paid_amount or 0
    
    return {
        'total_contract_value': total_contract_value,
        'total_invoiced': total_invoiced,
        'total_paid': total_paid,
        'outstanding': total_invoiced - total_paid
    }

def get_tasks_stats(self, user_id, role):
    """إحصائيات المهام حسب الدور"""
    if role == 'project_manager':
        tasks = Task.query.join(Project).filter(
            Project.project_manager_id == user_id
        ).all()
    elif role == 'supervisor':
        tasks = Task.query.filter_by(supervisor_id=user_id).all()
    elif role == 'delegate':
        tasks = Task.query.filter_by(delegate_id=user_id).all()
    else:
        tasks = []
    
    return count_by_status(tasks, 'status')

def count_tasks_by_project(self, user_id, role):
    """عد المهام حسب المشروع"""
    if role == 'supervisor':
        tasks = Task.query.filter_by(supervisor_id=user_id).all()
    elif role == 'delegate':
        tasks = Task.query.filter_by(delegate_id=user_id).all()
    else:
        return {}
    
    counts = {}
    for task in tasks:
        project_name = task.project.name if task.project else 'غير معروف'
        counts[project_name] = counts.get(project_name, 0) + 1
    
    return counts

def get_delegates_performance(self, supervisor_id):
    """أداء المناديب تحت المشرف"""
    tasks = Task.query.filter_by(supervisor_id=supervisor_id).all()
    
    delegate_performance = {}
    for task in tasks:
        if task.delegate_id:
            delegate_name = task.delegate.full_name if task.delegate else 'غير معروف'
            if delegate_name not in delegate_performance:
                delegate_performance[delegate_name] = {
                    'total_tasks': 0,
                    'completed_tasks': 0,
                    'in_progress_tasks': 0,
                    'pending_tasks': 0
                }
            
            delegate_performance[delegate_name]['total_tasks'] += 1
            if task.status == 'completed':
                delegate_performance[delegate_name]['completed_tasks'] += 1
            elif task.status == 'in_progress':
                delegate_performance[delegate_name]['in_progress_tasks'] += 1
            elif task.status == 'pending':
                delegate_performance[delegate_name]['pending_tasks'] += 1
    
    return delegate_performance

@dashboard_bp.route('/api/stats')
@login_required
def api_stats():
    """API للحصول على الإحصائيات"""
    try:
        # إحصائيات حسب دور المستخدم
        stats = {}
        
        if current_user.role == 'admin':
            stats = {
                'projects': {
                    'total': Project.query.filter_by(org_id=current_user.org_id).count(),
                    'active': Project.query.filter_by(org_id=current_user.org_id, status='active').count(),
                    'completed': Project.query.filter_by(org_id=current_user.org_id, status='completed').count()
                },
                'users': User.query.filter_by(org_id=current_user.org_id).count(),
                'tasks': {
                    'total': Task.query.join(Project).filter(Project.org_id == current_user.org_id).count(),
                    'pending': Task.query.join(Project).filter(
                        Project.org_id == current_user.org_id,
                        Task.status == 'pending'
                    ).count()
                }
            }
        
        elif current_user.role == 'project_manager':
            stats = {
                'projects': {
                    'total': Project.query.filter_by(project_manager_id=current_user.id).count(),
                    'active': Project.query.filter_by(project_manager_id=current_user.id, status='active').count()
                },
                'tasks': {
                    'total': Task.query.join(Project).filter(Project.project_manager_id == current_user.id).count(),
                    'pending': Task.query.join(Project).filter(
                        Project.project_manager_id == current_user.id,
                        Task.status == 'pending'
                    ).count()
                }
            }
        
        elif current_user.role == 'supervisor':
            stats = {
                'tasks': {
                    'total': Task.query.filter_by(supervisor_id=current_user.id).count(),
                    'pending': Task.query.filter_by(supervisor_id=current_user.id, status='pending').count(),
                    'in_progress': Task.query.filter_by(supervisor_id=current_user.id, status='in_progress').count()
                }
            }
        
        elif current_user.role == 'delegate':
            stats = {
                'tasks': {
                    'total': Task.query.filter_by(delegate_id=current_user.id).count(),
                    'pending': Task.query.filter_by(delegate_id=current_user.id, status='pending').count(),
                    'in_progress': Task.query.filter_by(delegate_id=current_user.id, status='in_progress').count()
                }
            }
        
        else:  # employee
            stats = {
                'tasks': {
                    'total': Task.query.join(Task.assignments).filter(
                        TaskAssignment.user_id == current_user.id
                    ).count(),
                    'pending': Task.query.join(Task.assignments).filter(
                        TaskAssignment.user_id == current_user.id,
                        Task.status == 'pending'
                    ).count(),
                    'in_progress': Task.query.join(Task.assignments).filter(
                        TaskAssignment.user_id == current_user.id,
                        Task.status == 'in_progress'
                    ).count()
                }
            }
        
        return jsonify({'success': True, 'stats': stats}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
"""
employee_routes.py - مسارات الموظفين والمستخدمين العاديين (نسخة مطورة ومتكاملة)
"""

from flask import render_template, request, redirect, url_for, flash, jsonify, g, current_app, send_file
from flask_login import login_required, current_user
from app.models import db, User, Project, Notification
from app.models import Task, TaskAssignment, TaskPlanning, TaskExecution, TaskProgress
from app.models import ProjectDates, ProjectProgress, TaskVerification
from app.models import ProjectDocument
from app.models import Activity, ActivityStep, ActivityResource, ActivityExpense, ActivityDocument
from app.models import ResourceRequest, ResourceRequestItem, TaskRequirement, TaskRequirementVerification
from app.models import WBS, EPS, Baseline
from app.routes import employee_bp
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import or_, and_, func, desc
from app.services.update_service import UpdateService
from app.services.smart_monitor import SmartMonitoringSystem
from app.services.notification_service import NotificationService
from app.services.ai_recommendation_service import AIRecommendationService
import os
import json
import pandas as pd
import io
import logging

logger = logging.getLogger(__name__)
# ============================================
# دوال مساعدة للتعامل مع التواريخ
# ============================================

def to_date(value):
    """تحويل أي قيمة إلى كائن date"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None

def is_today(value):
    """التحقق مما إذا كان التاريخ هو اليوم"""
    if value is None:
        return False
    today_date = date.today()
    value_date = to_date(value)
    return value_date == today_date if value_date else False

def is_this_week(value):
    """التحقق مما إذا كان التاريخ في هذا الأسبوع"""
    if value is None:
        return False
    today_date = date.today()
    value_date = to_date(value)
    if not value_date:
        return False
    week_start = today_date - timedelta(days=today_date.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start <= value_date <= week_end

def get_task_planned_date(task):
    """الحصول على التاريخ المخطط للمهمة"""
    try:
        if hasattr(task, 'planning') and task.planning:
            return to_date(task.planning.planned_start)
        return None
    except Exception:
        return None

def get_task_planned_end(task):
    """الحصول على تاريخ الانتهاء المخطط للمهمة"""
    try:
        if hasattr(task, 'planning') and task.planning:
            return to_date(task.planning.planned_finish)
        return None
    except Exception:
        return None

def get_task_progress(task):
    """الحصول على نسبة تقدم المهمة"""
    try:
        if hasattr(task, 'progress') and task.progress:
            return task.progress.progress_percentage
        return 0
    except Exception:
        return 0

def get_user_tasks(user):
    """الحصول على مهام المستخدم حسب دوره (محسنة)"""
    if user.role == 'supervisor':
        return Task.query.filter_by(supervisor_id=user.id).all()
    elif user.role == 'delegate':
        return Task.query.filter_by(delegate_id=user.id).all()
    else:  # employee
        assignments = TaskAssignment.query.filter_by(user_id=user.id).all()
        return [a.task for a in assignments if a.task]

def get_user_activities(user):
    """الحصول على الأنشطة المرتبطة بالمستخدم (محسنة)"""
    activities = []
    
    if user.role == 'supervisor':
        activities = Activity.query.filter_by(supervisor_id=user.id).all()
    elif user.role == 'delegate':
        activities = Activity.query.filter_by(delegate_id=user.id).all()
    else:
        tasks = get_user_tasks(user)
        activity_ids = set(t.activity_id for t in tasks if t.activity_id)
        if activity_ids:
            activities = Activity.query.filter(Activity.id.in_(activity_ids)).all()
    
    return activities

def has_task_access(task, user):
    """التحقق من صلاحية الوصول للمهمة"""
    if user.role == 'supervisor' and task.supervisor_id == user.id:
        return True
    if user.role == 'delegate' and task.delegate_id == user.id:
        return True
    if user.role == 'employee':
        assignment = TaskAssignment.query.filter_by(
            task_id=task.id,
            user_id=user.id
        ).first()
        return assignment is not None
    return False

def can_update_task(task, user):
    """التحقق من صلاحية تحديث المهمة"""
    if task.status == 'completed':
        return False
    if user.role == 'supervisor' and task.supervisor_id == user.id:
        return True
    if user.role == 'delegate' and task.delegate_id == user.id:
        return True
    if user.role == 'employee':
        assignment = TaskAssignment.query.filter_by(
            task_id=task.id,
            user_id=user.id
        ).first()
        return assignment is not None
    return False

def _has_activity_access(activity, user):
    """التحقق من صلاحية الوصول للنشاط"""
    if user.role == 'supervisor' and activity.supervisor_id == user.id:
        return True
    if user.role == 'delegate' and activity.delegate_id == user.id:
        return True
    if user.role == 'employee':
        tasks = Task.query.filter_by(activity_id=activity.id).all()
        for task in tasks:
            if has_task_access(task, user):
                return True
    return False

def _can_update_activity(activity, user):
    """التحقق من صلاحية تحديث النشاط"""
    if activity.status == 'completed':
        return False
    return _has_activity_access(activity, user)

# ============================================
# ديكوراتورات التحقق من الصلاحيات
# ============================================

def employee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['employee', 'delegate', 'supervisor', 'client']:
            flash('غير مصرح بالوصول إلى هذه الصفحة', 'danger')
            from app.routes.auth_routes import redirect_to_user_dashboard
            return redirect_to_user_dashboard()
        return f(*args, **kwargs)
    return decorated_function

def supervisor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'supervisor':
            flash('غير مصرح بالوصول - هذه الصفحة للمشرفين فقط', 'danger')
            from app.routes.auth_routes import redirect_to_user_dashboard
            return redirect_to_user_dashboard()
        return f(*args, **kwargs)
    return decorated_function

def delegate_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'delegate':
            flash('غير مصرح بالوصول - هذه الصفحة للمناديب فقط', 'danger')
            from app.routes.auth_routes import redirect_to_user_dashboard
            return redirect_to_user_dashboard()
        return f(*args, **kwargs)
    return decorated_function

# ============================================
# قبل كل طلب - تحميل معلومات المستخدم
# ============================================

@employee_bp.before_request
def load_user_data():
    """تحميل بيانات المستخدم قبل كل طلب (محسنة)"""
    if current_user.is_authenticated and current_user.role in ['employee', 'delegate', 'supervisor', 'client']:
        g.user = current_user
        
        # حساب الإشعارات غير المقروءة
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        
        # حساب مهام اليوم
        user_tasks = get_user_tasks(current_user)
        g.today_tasks = sum(1 for task in user_tasks if is_today(get_task_planned_date(task)))
        
        # حساب المهام المتأخرة
        today = date.today()
        g.overdue_tasks = 0
        for task in user_tasks:
            if task.status in ['pending', 'in_progress']:
                planned_end = get_task_planned_end(task)
                if planned_end and planned_end < today:
                    g.overdue_tasks += 1
        
        # حساب الإشعارات غير المقروءة
        g.unread_messages = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()
        
        # ✅ إضافة إحصائيات الأنشطة - تأكد من تعريف هذه القيم
        try:
            user_activities = get_user_activities(current_user)
            g.my_activities_count = len(user_activities)
            g.in_progress_activities = sum(1 for a in user_activities if a.status == 'in_progress')
        except Exception as e:
            g.my_activities_count = 0
            g.in_progress_activities = 0
            logger.error(f"Error loading user activities: {str(e)}")
        
        # ✅ إضافة توصيات ذكية
        try:
            from app.services.ai_recommendation_service import AIRecommendationService
            ai_service = AIRecommendationService()
            g.smart_recommendations = ai_service.get_user_recommendations(current_user.id)[:3]
        except Exception as e:
            g.smart_recommendations = []
            logger.error(f"Error loading AI recommendations: {str(e)}")
        
        # ✅ إضافة معلومات الشركة
        if hasattr(current_user, 'org_id') and current_user.org_id:
            from app.models import Organization
            g.company = Organization.query.get(current_user.org_id)
        else:
            g.company = None
            
        # ✅ إضافة القيم الافتراضية للمتغيرات الأخرى
        g.delayed_tasks_count = g.overdue_tasks
        g.pending_deliveries_count = 0
        g.low_stock_resources = 0
        g.upcoming_meetings_count = 0
        g.open_issues_count = 0
        g.recent_issues = []
        g.upcoming_meetings = []
        g.issues_stats = {}
        
    else:
        # تعيين القيم الافتراضية للمستخدم غير المسجل
        g.user = None
        g.notifications_count = 0
        g.today_tasks = 0
        g.overdue_tasks = 0
        g.unread_messages = 0
        g.my_activities_count = 0
        g.in_progress_activities = 0
        g.smart_recommendations = []
        g.company = None
        g.delayed_tasks_count = 0
        g.pending_deliveries_count = 0
        g.low_stock_resources = 0
        g.upcoming_meetings_count = 0
        g.open_issues_count = 0
        g.recent_issues = []
        g.upcoming_meetings = []
        g.issues_stats = {}

# ============================================
# لوحة التحكم الرئيسية للموظف (محسنة)
# ============================================

@employee_bp.route('/')
@login_required
@employee_required
def dashboard():
    """لوحة تحكم الموظف الرئيسية (محسنة مع تحليلات ذكية)"""
    
    # المهام الخاصة بالمستخدم حسب دوره
    my_tasks = get_user_tasks(current_user)
    my_activities = get_user_activities(current_user)
    
    # ============================================
    # إحصائيات المهام
    # ============================================
    total_tasks = len(my_tasks)
    completed_tasks = len([t for t in my_tasks if t.status == 'completed'])
    in_progress_tasks = len([t for t in my_tasks if t.status == 'in_progress'])
    pending_tasks = len([t for t in my_tasks if t.status == 'pending'])
    
    # حساب المهام المتأخرة
    today = date.today()
    overdue_tasks = []
    for task in my_tasks:
        if task.status in ['pending', 'in_progress']:
            planned_end = get_task_planned_end(task)
            if planned_end and planned_end < today:
                overdue_tasks.append(task)
    
    # ============================================
    # إحصائيات الأنشطة
    # ============================================
    total_activities = len(my_activities)
    completed_activities = len([a for a in my_activities if a.status == 'completed'])
    in_progress_activities = len([a for a in my_activities if a.status == 'in_progress'])
    not_started_activities = len([a for a in my_activities if a.status == 'not_started'])
    
    # متوسط التقدم في الأنشطة
    avg_activity_progress = sum(a.progress_percentage or 0 for a in my_activities) / total_activities if total_activities > 0 else 0
    
    # ============================================
    # أداء المستخدم
    # ============================================
    # حساب نسبة الإنجاز
    completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    
    # حساب المهام المنتهية في الوقت المحدد
    on_time_tasks = 0
    for task in my_tasks:
        if task.status == 'completed' and task.execution and task.planning:
            if task.execution.actual_finish and task.planning.planned_finish:
                if task.execution.actual_finish <= task.planning.planned_finish:
                    on_time_tasks += 1
    on_time_rate = (on_time_tasks / completed_tasks * 100) if completed_tasks > 0 else 0
    
    # متوسط جودة المهام
    quality_scores = []
    for task in my_tasks:
        if task.progress and task.progress.completion_quality:
            quality_map = {'excellent': 5, 'good': 4, 'fair': 3, 'poor': 2}
            quality_scores.append(quality_map.get(task.progress.completion_quality, 0))
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    
    performance = {
        'completion_rate': round(completion_rate, 1),
        'on_time_rate': round(on_time_rate, 1),
        'avg_quality': round(avg_quality, 1),
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'avg_activity_progress': round(avg_activity_progress, 1)
    }
    
    # ============================================
    # المهام النشطة اليوم
    # ============================================
    today_tasks = []
    for task in my_tasks:
        planned_start = get_task_planned_date(task)
        planned_end = get_task_planned_end(task)
        if planned_start and planned_end:
            if planned_start <= today <= planned_end and task.status != 'completed':
                today_tasks.append(task)
    
    # ============================================
    # المشاريع التي يشارك فيها المستخدم
    # ============================================
    project_ids = set()
    for task in my_tasks:
        if task.project_id:
            project_ids.add(task.project_id)
    for activity in my_activities:
        if activity.project_id:
            project_ids.add(activity.project_id)
    
    projects = Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []
    
    # إضافة معلومات التقدم لكل مشروع
    projects_data = []
    for project in projects:
        project_tasks = [t for t in my_tasks if t.project_id == project.id]
        project_completed = len([t for t in project_tasks if t.status == 'completed'])
        project_progress = (project_completed / len(project_tasks) * 100) if project_tasks else 0
        
        projects_data.append({
            'id': project.id,
            'name': project.name,
            'code': project.project_code,
            'progress': project_progress,
            'tasks_count': len(project_tasks),
            'completed_count': project_completed
        })
    
    # ============================================
    # آخر الإشعارات
    # ============================================
    recent_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    # ============================================
    # توصيات ذكية للمستخدم
    # ============================================
    smart_suggestions = []
    
    # توصية 1: المهام المتأخرة
    if overdue_tasks:
        smart_suggestions.append({
            'type': 'warning',
            'title': '⚠️ مهام متأخرة',
            'message': f'لديك {len(overdue_tasks)} مهام متأخرة. يوصى بالتركيز عليها أولاً.',
            'action_url': url_for('employee.my_tasks', filter='overdue'),
            'icon': 'exclamation-triangle'
        })
    
    # توصية 2: الأنشطة التي لم تبدأ بعد
    if not_started_activities > 0:
        smart_suggestions.append({
            'type': 'info',
            'title': '📋 أنشطة لم تبدأ بعد',
            'message': f'لديك {not_started_activities} نشاط لم تبدأ بعد. يمكنك البدء بها الآن.',
            'action_url': url_for('employee.my_activities'),
            'icon': 'play-circle'
        })
    
    # توصية 3: أداء متميز
    if completion_rate > 80 and avg_quality > 4:
        smart_suggestions.append({
            'type': 'success',
            'title': '🌟 أداء متميز!',
            'message': f'نسبة إنجازك {completion_rate}% مع جودة عالية. استمر بهذا الأداء الرائع.',
            'icon': 'star'
        })
    
    # توصية 4: اقتراح تحسين الأداء
    if on_time_rate < 50 and completion_rate > 0:
        smart_suggestions.append({
            'type': 'danger',
            'title': '📈 تحسين الالتزام بالمواعيد',
            'message': 'نسبة التزامك بالمواعيد منخفضة. يوصى بتخطيط أفضل للمهام.',
            'icon': 'chart-line'
        })
    
    # ============================================
    # إحصائيات حسب الدور
    # ============================================
    role_stats = {
        'supervised_count': Task.query.filter_by(supervisor_id=current_user.id).count() if current_user.role == 'supervisor' else 0,
        'delegate_count': Task.query.filter_by(delegate_id=current_user.id).count() if current_user.role == 'delegate' else 0,
        'assigned_count': TaskAssignment.query.filter_by(user_id=current_user.id).count() if current_user.role == 'employee' else 0
    }
    
    stats = {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'pending_tasks': pending_tasks,
        'overdue_tasks': len(overdue_tasks),
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'in_progress_activities': in_progress_activities,
        'avg_activity_progress': round(avg_activity_progress, 1),
        'supervised_count': role_stats['supervised_count'],
        'delegate_count': role_stats['delegate_count'],
        'assigned_count': role_stats['assigned_count']
    }
    
    return render_template('employee/dashboard.html',
                         stats=stats,
                         my_tasks=my_tasks[:5],
                         today_tasks=today_tasks[:5],
                         projects=projects_data[:5],
                         recent_notifications=recent_notifications,
                         performance=performance,
                         smart_suggestions=smart_suggestions,
                         now=datetime.now())

# ============================================
# المهام الخاصة بي (محسنة)
# ============================================

@employee_bp.route('/my-tasks')
@login_required
@employee_required
def my_tasks():
    """عرض جميع المهام الخاصة بي مع تصفية وترتيب متقدم"""
    
    # الحصول على المهام حسب الدور
    tasks = get_user_tasks(current_user)
    
    # معاملات التصفية
    status_filter = request.args.get('status', 'all')
    priority_filter = request.args.get('priority', 'all')
    project_filter = request.args.get('project_id', 'all')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', 'date')
    
    # تطبيق التصفيات
    if status_filter != 'all':
        tasks = [t for t in tasks if t.status == status_filter]
    
    if priority_filter != 'all':
        priority_map = {'high': [4, 5], 'medium': [3], 'low': [1, 2]}
        if priority_filter in priority_map:
            tasks = [t for t in tasks if (t.priority or 3) in priority_map[priority_filter]]
    
    if project_filter != 'all':
        tasks = [t for t in tasks if str(t.project_id) == project_filter]
    
    if search_query:
        tasks = [t for t in tasks if search_query.lower() in t.task_name.lower() or 
                 (t.task_code and search_query.lower() in t.task_code.lower())]
    
    # ترتيب المهام
    if sort_by == 'date':
        tasks.sort(key=lambda x: get_task_planned_date(x) or datetime.max)
    elif sort_by == 'priority':
        tasks.sort(key=lambda x: -(x.priority or 0))
    elif sort_by == 'status':
        status_order = {'pending': 0, 'in_progress': 1, 'completed': 2}
        tasks.sort(key=lambda x: status_order.get(x.status, 3))
    
    # تصنيف المهام
    pending_tasks = [t for t in tasks if t.status == 'pending']
    in_progress_tasks = [t for t in tasks if t.status == 'in_progress']
    completed_tasks = [t for t in tasks if t.status == 'completed']
    
    # حساب المهام المتأخرة
    today = date.today()
    overdue_tasks = []
    for task in tasks:
        if task.status in ['pending', 'in_progress']:
            planned_end = get_task_planned_end(task)
            if planned_end and planned_end < today:
                overdue_tasks.append(task)
    
    # المشاريع للفلترة
    project_ids = set(t.project_id for t in tasks if t.project_id)
    projects = Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []
    
    if current_user.role == 'supervisor':
        view_type = 'supervised'
    elif current_user.role == 'delegate':
        view_type = 'delegated'
    else:
        view_type = 'assigned'
    
    # ✅ تأكد من تعريف stats بشكل صحيح
    stats = {
        'total': len(tasks),
        'pending': len(pending_tasks),
        'in_progress': len(in_progress_tasks),
        'completed': len(completed_tasks),
        'overdue': len(overdue_tasks),
        'completion_rate': (len(completed_tasks) / len(tasks) * 100) if tasks else 0
    }
    
    # ✅ طباعة للتأكد من وجود stats (للت Debug)
    print(f"DEBUG: stats = {stats}")
    print(f"DEBUG: len(tasks) = {len(tasks)}")
    
    # ✅ تأكد من تمرير stats في render_template
    return render_template('employee/tasks/index.html',
                         tasks=tasks,
                         pending_tasks=pending_tasks,
                         in_progress_tasks=in_progress_tasks,
                         completed_tasks=completed_tasks,
                         overdue_tasks=overdue_tasks,
                         projects=projects,
                         stats=stats,  # <- هذا هو المفتاح
                         view_type=view_type,
                         status_filter=status_filter,
                         priority_filter=priority_filter,
                         project_filter=project_filter,
                         search_query=search_query,
                         sort_by=sort_by,
                         now=datetime.now())

# ============================================
# تفاصيل المهمة (محسنة)
# ============================================

@employee_bp.route('/tasks/<int:task_id>')
@login_required
@employee_required
def view_task(task_id):
    """عرض تفاصيل المهمة مع معلومات متكاملة"""
    
    task = Task.query.get_or_404(task_id)
    
    # التحقق من صلاحية الوصول للمهمة
    if not has_task_access(task, current_user):
        flash('غير مصرح بمشاهدة هذه المهمة', 'danger')
        return redirect(url_for('employee.my_tasks'))
    
    # معلومات إضافية
    can_update = can_update_task(task, current_user)
    assignments = TaskAssignment.query.filter_by(task_id=task_id).all()
    
    # التواريخ والتقدم
    planned_start = get_task_planned_date(task)
    planned_end = get_task_planned_end(task)
    progress = get_task_progress(task)
    
    # ✅ إضافة متطلبات المهمة
    requirements = TaskRequirement.query.filter_by(task_id=task_id, is_active=True).all()
    
    # ✅ إضافة موارد المهمة
    from app.models.task_models import TaskResource
    resources = TaskResource.query.filter_by(task_id=task_id).all()
    
    # ✅ إضافة المستندات المرتبطة
    documents = ActivityDocument.query.filter_by(source_task_id=task_id).all()
    
    # ✅ إضافة سجل التحديثات
    from app.models.task_models import TaskProgressUpdate
    progress_updates = TaskProgressUpdate.query.filter_by(task_id=task_id).order_by(TaskProgressUpdate.updated_at.desc()).limit(10).all()
    
    # ✅ حساب الوقت المتبقي
    remaining_time = None
    if planned_end and task.status != 'completed':
        remaining_days = (planned_end - date.today()).days
        if remaining_days > 0:
            remaining_time = f"{remaining_days} يوم"
        elif remaining_days == 0:
            remaining_time = "اليوم"
        else:
            remaining_time = "متأخر"
    
    # ✅ اقتراحات لتحسين المهمة
    suggestions = []
    if task.status == 'in_progress' and progress < 30 and planned_end and (planned_end - date.today()).days < 3:
        suggestions.append({
            'type': 'warning',
            'message': 'التقدم بطيء مقارنة بالوقت المتبقي. يوصى بتسريع العمل.'
        })
    if resources and resources[0].remaining_quantity <= 0 and progress < 100:
        suggestions.append({
            'type': 'info',
            'message': 'قد تحتاج إلى طلب موارد إضافية لإكمال المهمة.'
        })
    
    return render_template('employee/tasks/view.html',
                         task=task,
                         assignments=assignments,
                         can_update=can_update,
                         planned_start=planned_start,
                         planned_end=planned_end,
                         progress=progress,
                         requirements=requirements,
                         resources=resources,
                         documents=documents,
                         progress_updates=progress_updates,
                         remaining_time=remaining_time,
                         suggestions=suggestions)

# ============================================
# الأنشطة الخاصة بي (محسنة)
# ============================================

@employee_bp.route('/my-activities')
@login_required
@employee_required
def my_activities():
    """عرض جميع الأنشطة المرتبطة بالمستخدم مع تحليلات متقدمة"""
    
    # الحصول على الأنشطة حسب دور المستخدم
    activities = get_user_activities(current_user)
    
    # معاملات التصفية
    status_filter = request.args.get('status', 'all')
    project_filter = request.args.get('project_id', 'all')
    search_query = request.args.get('search', '')
    
    # تطبيق التصفيات
    if status_filter != 'all':
        activities = [a for a in activities if a.status == status_filter]
    
    if project_filter != 'all':
        activities = [a for a in activities if str(a.project_id) == project_filter]
    
    if search_query:
        activities = [a for a in activities if search_query.lower() in a.activity_name.lower()]
    
    # إحصائيات الأنشطة
    total_activities = len(activities)
    not_started = sum(1 for a in activities if a.status == 'not_started')
    in_progress = sum(1 for a in activities if a.status == 'in_progress')
    completed = sum(1 for a in activities if a.status == 'completed')
    delayed = sum(1 for a in activities if a.status == 'delayed')
    
    # حساب الميزانية والتكاليف
    total_budget = sum(a.planned_cost or 0 for a in activities)
    total_actual = sum(a.actual_cost or 0 for a in activities)
    total_variance = total_actual - total_budget
    
    # حساب متوسط التقدم
    avg_progress = sum(a.progress_percentage or 0 for a in activities) / total_activities if total_activities > 0 else 0
    
    # حساب الأنشطة الحرجة (المتأخرة أو ذات الأولوية العالية)
    critical_activities = []
    today = date.today()
    for activity in activities:
        if activity.status == 'delayed':
            critical_activities.append(activity)
        elif activity.status == 'in_progress' and activity.planned_finish:
            if to_date(activity.planned_finish) and to_date(activity.planned_finish) < today:
                critical_activities.append(activity)
    
    # المشاريع للفلترة
    project_ids = set(a.project_id for a in activities if a.project_id)
    projects = Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []
    
    stats = {
        'total': total_activities,
        'not_started': not_started,
        'in_progress': in_progress,
        'completed': completed,
        'delayed': delayed,
        'critical': len(critical_activities),
        'total_budget': total_budget,
        'actual_cost': total_actual,
        'variance': total_variance,
        'progress': round(avg_progress, 1)
    }
    
    return render_template('employee/activities/index.html',
                         activities=activities,
                         stats=stats,
                         projects=projects,
                         critical_activities=critical_activities,
                         role=current_user.role,
                         status_filter=status_filter,
                         project_filter=project_filter,
                         search_query=search_query)
@employee_bp.route('/activities/<int:activity_id>')
@login_required
@employee_required
def view_activity(activity_id):
    """عرض تفاصيل النشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        # التحقق من صلاحية الوصول
        if not _has_activity_access(activity, current_user):
            flash('غير مصرح بمشاهدة هذا النشاط', 'danger')
            return redirect(url_for('employee.my_activities'))
        
        # المهام المرتبطة بالنشاط
        tasks = Task.query.filter_by(activity_id=activity_id).all()
        
        # الخطوات
        steps = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order).all()
        
        # الموارد المخصصة
        resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
        
        # المصروفات
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
        
        # المستندات
        documents = ActivityDocument.query.filter_by(activity_id=activity_id).all()
        
        # إحصائيات النشاط
        stats = {
            'total_tasks': len(tasks),
            'completed_tasks': sum(1 for t in tasks if t.status == 'completed'),
            'total_steps': len(steps),
            'completed_steps': sum(1 for s in steps if s.is_completed),
            'total_budget': activity.planned_cost or 0,
            'actual_cost': activity.actual_cost or 0,
            'variance': (activity.actual_cost or 0) - (activity.planned_cost or 0),
            'variance_percentage': (((activity.actual_cost or 0) - (activity.planned_cost or 0)) / (activity.planned_cost or 1) * 100) if (activity.planned_cost or 0) > 0 else 0
        }
        
        can_update = _can_update_activity(activity, current_user)
        can_start = can_update and activity.status == 'not_started'
        can_complete = can_update and activity.status == 'in_progress'
        
        return render_template('employee/activities/view.html',
                             activity=activity,
                             tasks=tasks,
                             steps=steps,
                             resources=resources,
                             expenses=expenses,
                             documents=documents,
                             stats=stats,
                             can_update=can_update,
                             can_start=can_start,
                             can_complete=can_complete,
                             now=datetime.now())
    except Exception as e:
        logger.error(f"Error in view_activity: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.my_activities'))
# ============================================
# API Routes للموظفين - إضافات جديدة
# ============================================

@employee_bp.route('/api/tasks/weekly-report')
@login_required
@employee_required
def api_weekly_report():
    """تقرير أسبوعي عن أداء المستخدم"""
    try:
        tasks = get_user_tasks(current_user)
        
        # حساب إحصائيات آخر 4 أسابيع
        weekly_data = []
        for i in range(4, 0, -1):
            week_start = datetime.now().date() - timedelta(days=i*7)
            week_end = week_start + timedelta(days=6)
            
            week_tasks = []
            for task in tasks:
                if task.created_at:
                    task_date = to_date(task.created_at)
                    if task_date and week_start <= task_date <= week_end:
                        week_tasks.append(task)
            
            week_completed = len([t for t in week_tasks if t.status == 'completed'])
            
            # حساب متوسط جودة المهام في هذا الأسبوع
            week_quality = 0
            quality_count = 0
            for task in week_tasks:
                if task.progress and task.progress.completion_quality:
                    quality_map = {'excellent': 5, 'good': 4, 'fair': 3, 'poor': 2}
                    week_quality += quality_map.get(task.progress.completion_quality, 0)
                    quality_count += 1
            
            avg_quality = week_quality / quality_count if quality_count > 0 else 0
            
            weekly_data.append({
                'week': f'الأسبوع {5-i}',
                'start_date': week_start.strftime('%Y-%m-%d'),
                'end_date': week_end.strftime('%Y-%m-%d'),
                'total_tasks': len(week_tasks),
                'completed_tasks': week_completed,
                'completion_rate': (week_completed / len(week_tasks) * 100) if week_tasks else 0,
                'avg_quality': round(avg_quality, 1)
            })
        
        return jsonify({'success': True, 'weekly_data': weekly_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@employee_bp.route('/api/activities/<int:activity_id>/gantt-data')
@login_required
@employee_required
def api_activity_gantt_data(activity_id):
    """بيانات Gantt Chart للنشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _has_activity_access(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        tasks = Task.query.filter_by(activity_id=activity_id).all()
        
        gantt_data = []
        for task in tasks:
            planned_start = get_task_planned_date(task)
            planned_end = get_task_planned_end(task)
            actual_start = task.execution.actual_start if task.execution else None
            actual_end = task.execution.actual_finish if task.execution else None
            
            gantt_data.append({
                'id': task.id,
                'name': task.task_name,
                'planned_start': planned_start.isoformat() if planned_start else None,
                'planned_end': planned_end.isoformat() if planned_end else None,
                'actual_start': actual_start.isoformat() if actual_start else None,
                'actual_end': actual_end.isoformat() if actual_end else None,
                'progress': task.progress.progress_percentage if task.progress else 0,
                'status': task.status
            })
        
        return jsonify({'success': True, 'gantt_data': gantt_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@employee_bp.route('/api/my-performance/export')
@login_required
@employee_required
def export_my_performance():
    """تصدير تقرير أداء المستخدم إلى Excel"""
    try:
        tasks = get_user_tasks(current_user)
        
        # إنشاء DataFrame
        data = []
        for task in tasks:
            planned_start = get_task_planned_date(task)
            planned_end = get_task_planned_end(task)
            
            data.append({
                'المهمة': task.task_name,
                'المشروع': task.project.name if task.project else '',
                'الحالة': task.status,
                'التقدم': f"{get_task_progress(task)}%",
                'تاريخ البدء المخطط': planned_start.strftime('%Y-%m-%d') if planned_start else '',
                'تاريخ الانتهاء المخطط': planned_end.strftime('%Y-%m-%d') if planned_end else '',
                'تاريخ البدء الفعلي': task.execution.actual_start.strftime('%Y-%m-%d') if task.execution and task.execution.actual_start else '',
                'تاريخ الانتهاء الفعلي': task.execution.actual_finish.strftime('%Y-%m-%d') if task.execution and task.execution.actual_finish else '',
                'الجودة': task.progress.completion_quality if task.progress and task.progress.completion_quality else ''
            })
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='مهامي', index=False)
            
            # تنسيق الأعمدة
            worksheet = writer.sheets['مهامي']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 30)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        filename = f"my_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'حدث خطأ في تصدير التقرير: {str(e)}', 'danger')
        return redirect(url_for('employee.dashboard'))


# ============================================
# لوحة تحكم المشرف (Supervisor Dashboard) - محسنة
# ============================================

@employee_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def supervisor_dashboard():
    """لوحة تحكم خاصة بالمشرف مع تحليلات متقدمة"""
    
    # المهام تحت الإشراف
    supervised_tasks = Task.query.filter_by(supervisor_id=current_user.id).all()
    
    # الأنشطة تحت الإشراف
    supervised_activities = Activity.query.filter_by(supervisor_id=current_user.id).all()
    
    # المناديب تحت الإشراف
    delegates = User.query.filter_by(org_id=current_user.org_id, role='delegate').all()
    
    # إحصائيات المهام
    total_tasks = len(supervised_tasks)
    completed_tasks = len([t for t in supervised_tasks if t.status == 'completed'])
    in_progress_tasks = len([t for t in supervised_tasks if t.status == 'in_progress'])
    pending_tasks = len([t for t in supervised_tasks if t.status == 'pending'])
    
    # حساب المهام المتأخرة
    today = date.today()
    overdue_tasks = []
    for task in supervised_tasks:
        if task.status in ['pending', 'in_progress']:
            planned_end = get_task_planned_end(task)
            if planned_end and planned_end < today:
                overdue_tasks.append(task)
    
    # إحصائيات الأنشطة
    total_activities = len(supervised_activities)
    completed_activities = len([a for a in supervised_activities if a.status == 'completed'])
    in_progress_activities = len([a for a in supervised_activities if a.status == 'in_progress'])
    
    # أداء المناديب
    delegate_performance = []
    for delegate in delegates:
        delegate_tasks = Task.query.filter_by(delegate_id=delegate.id).all()
        delegate_completed = len([t for t in delegate_tasks if t.status == 'completed'])
        delegate_total = len(delegate_tasks)
        
        delegate_performance.append({
            'id': delegate.id,
            'name': delegate.full_name,
            'total_tasks': delegate_total,
            'completed_tasks': delegate_completed,
            'completion_rate': (delegate_completed / delegate_total * 100) if delegate_total > 0 else 0
        })
    
    delegate_performance.sort(key=lambda x: x['completion_rate'], reverse=True)
    
    # طلبات التحقق المعلقة
    pending_verifications = TaskRequirementVerification.query.filter(
        TaskRequirementVerification.status == 'pending'
    ).join(Task).filter(Task.supervisor_id == current_user.id).all()
    
    # إحصائيات طلبات التحقق
    total_verifications = TaskRequirementVerification.query.join(Task).filter(
        Task.supervisor_id == current_user.id
    ).count()
    
    verified_verifications = TaskRequirementVerification.query.filter(
        TaskRequirementVerification.status == 'verified'
    ).join(Task).filter(Task.supervisor_id == current_user.id).count()
    
    # المهام التي تحتاج إلى مراجعة
    tasks_need_review = []
    for task in supervised_tasks:
        if task.status == 'in_progress' and task.progress and task.progress.progress_percentage >= 90:
            tasks_need_review.append(task)
    
    stats = {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'pending_tasks': pending_tasks,
        'overdue_tasks': len(overdue_tasks),
        'total_activities': total_activities,
        'completed_activities': completed_activities,
        'in_progress_activities': in_progress_activities,
        'total_verifications': total_verifications,
        'pending_verifications': len(pending_verifications),
        'verified_verifications': verified_verifications,
        'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
    }
    
    return render_template('employee/supervisor/dashboard.html',
                         stats=stats,
                         supervised_tasks=supervised_tasks[:10],
                         supervised_activities=supervised_activities[:10],
                         delegate_performance=delegate_performance[:5],
                         pending_verifications=pending_verifications[:10],
                         tasks_need_review=tasks_need_review[:5],
                         now=datetime.now())

@employee_bp.route('/supervisor/verifications')
@login_required
@supervisor_required
def supervisor_verifications():
    """عرض طلبات التحقق المعلقة للمشرف"""
    try:
        from app.models.task_models import TaskRequirementVerification, TaskRequirement, Task
        
        # جلب جميع طلبات التحقق للمهام التي يشرف عليها المستخدم
        verifications = TaskRequirementVerification.query.filter(
            TaskRequirementVerification.status == 'pending'
        ).join(
            TaskRequirement, TaskRequirementVerification.requirement_id == TaskRequirement.id
        ).join(
            Task, TaskRequirement.task_id == Task.id
        ).filter(
            Task.supervisor_id == current_user.id
        ).order_by(
            TaskRequirementVerification.submitted_at.desc()
        ).all()
        
        # إضافة معلومات إضافية لكل طلب
        for v in verifications:
            if v.verified_by:
                from app.models import User
                v.verified_by_user = User.query.get(v.verified_by)
            else:
                v.verified_by_user = None
        
        return render_template('employee/supervisor/verifications.html', 
                             verifications=verifications,
                             now=datetime.now())
    except Exception as e:
        logger.error(f"Error in supervisor_verifications: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.supervisor_dashboard'))
# ============================================
# تصدير تقرير أداء الفريق (للمشرف)
# ============================================

@employee_bp.route('/supervisor/export-team-report')
@login_required
@supervisor_required
def export_team_report():
    """تصدير تقرير أداء الفريق إلى Excel"""
    try:
        # المناديب تحت الإشراف
        delegates = User.query.filter_by(org_id=current_user.org_id, role='delegate').all()
        
        data = []
        for delegate in delegates:
            delegate_tasks = Task.query.filter_by(delegate_id=delegate.id).all()
            completed = len([t for t in delegate_tasks if t.status == 'completed'])
            total = len(delegate_tasks)
            
            # حساب متوسط الجودة
            quality_sum = 0
            quality_count = 0
            for task in delegate_tasks:
                if task.progress and task.progress.completion_quality:
                    quality_map = {'excellent': 5, 'good': 4, 'fair': 3, 'poor': 2}
                    quality_sum += quality_map.get(task.progress.completion_quality, 0)
                    quality_count += 1
            
            avg_quality = quality_sum / quality_count if quality_count > 0 else 0
            
            data.append({
                'المندوب': delegate.full_name,
                'إجمالي المهام': total,
                'المهام المكتملة': completed,
                'نسبة الإنجاز': f"{(completed / total * 100) if total > 0 else 0:.1f}%",
                'متوسط الجودة': f"{avg_quality:.1f}/5"
            })
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='أداء الفريق', index=False)
            
            worksheet = writer.sheets['أداء الفريق']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 25)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        filename = f"team_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('employee.supervisor_dashboard'))


# ============================================
# باقي المسارات (كما هي مع إضافة تحسينات بسيطة)
# ============================================

# ... (باقي المسارات مثل api_task_start, api_task_complete, إلخ تبقى كما هي مع إضافة تحديث المؤشرات)

# ============================================
# إضافة تحديث المؤشرات في نهاية الدوال
# ============================================

# تأكد من إضافة هذه الأسطر في نهاية دوال التحديث:
# if task.activity_id:
#     UpdateService.update_activity_metrics(task.activity)
# UpdateService.update_project_metrics(task.project)
# 
# و:
# if activity.project_id:
#     UpdateService.update_project_metrics(activity.project)
# ============================================
# إكمال باقي مسارات الموظفين مع التحسينات
# ============================================

# ============================================
# API Routes للموظفين - دوال بدء وإكمال المهام
# ============================================

@employee_bp.route('/api/tasks/<int:task_id>/start', methods=['POST'])
@login_required
@employee_required
def api_task_start(task_id):
    """API لبدء مهمة (محسنة مع التحقق من المتطلبات)"""
    try:
        task = Task.query.get_or_404(task_id)
        
        # التحقق من صلاحية الوصول
        if not has_task_access(task, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح بالوصول لهذه المهمة'}), 403
        
        # التحقق من إمكانية بدء المهمة
        if task.status != 'pending':
            return jsonify({'success': False, 'error': 'لا يمكن بدء مهمة بهذه الحالة'}), 400
        
        # التحقق من المتطلبات
        if hasattr(task, 'get_pending_requirements'):
            pending_reqs = task.get_pending_requirements()
            if pending_reqs:
                return jsonify({
                    'success': False, 
                    'error': f'يوجد {len(pending_reqs)} متطلبات معلقة',
                    'pending_requirements': True,
                    'requirements': [{'id': r.id, 'description': r.description} for r in pending_reqs]
                }), 400
        
        # التحقق من الموارد المتاحة
        from app.models.task_models import TaskResource
        task_resources = TaskResource.query.filter_by(task_id=task_id).all()
        missing_resources = []
        for res in task_resources:
            if res.resource and res.resource.available_quantity < res.planned_quantity:
                missing_resources.append({
                    'name': res.resource.name,
                    'available': res.resource.available_quantity,
                    'required': res.planned_quantity
                })
        
        if missing_resources:
            return jsonify({
                'success': False,
                'error': 'الموارد التالية غير متوفرة',
                'missing_resources': missing_resources
            }), 400
        
        # بدء المهمة
        task.status = 'in_progress'
        
        # تحديث وقت البدء الفعلي
        if not task.execution:
            task.execution = TaskExecution(task_id=task.id)
        task.execution.actual_start = datetime.utcnow()
        
        # تحديث التقدم إذا لم يكن موجوداً
        if not task.progress:
            task.progress = TaskProgress(task_id=task.id)
        task.progress.progress_percentage = 5  # بداية بسيطة
        
        db.session.commit()
        
        # إنشاء إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != current_user.id:
            notification = Notification(
                user_id=task.supervisor_id,
                title='بدء مهمة',
                message=f'بدأ {current_user.full_name} في تنفيذ المهمة: {task.task_name}',
                notification_type='task_started',
                related_task_id=task.id,
                related_project_id=task.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
        
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        
        # ✅ تسجيل التقدم في النظام الذكي
        try:
            monitor = SmartMonitoringSystem()
            monitor.record_task_progress(task)
        except Exception as e:
            current_app.logger.warning(f"خطأ في تسجيل تقدم المهمة: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'تم بدء المهمة بنجاح',
            'task': {
                'id': task.id,
                'status': task.status,
                'progress': task.progress.progress_percentage if task.progress else 0,
                'actual_start': task.execution.actual_start.isoformat() if task.execution and task.execution.actual_start else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in api_task_start: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@employee_bp.route('/api/tasks/bulk-start', methods=['POST'])
@login_required
@employee_required
def api_tasks_bulk_start():
    """بدء مجموعة من المهام دفعة واحدة"""
    try:
        data = request.get_json()
        task_ids = data.get('task_ids', [])
        
        if not task_ids:
            return jsonify({'error': 'لم يتم تحديد مهام'}), 400
        
        started_tasks = []
        failed_tasks = []
        
        for task_id in task_ids:
            task = Task.query.get(task_id)
            
            # التحقق من صلاحية الوصول
            if not task or not has_task_access(task, current_user):
                failed_tasks.append({'id': task_id, 'reason': 'غير مصرح'})
                continue
            
            # التحقق من إمكانية بدء المهمة
            if task.status != 'pending':
                failed_tasks.append({'id': task_id, 'reason': 'المهمة ليست في حالة انتظار'})
                continue
            
            # التحقق من المتطلبات
            if hasattr(task, 'get_pending_requirements'):
                pending_reqs = task.get_pending_requirements()
                if pending_reqs:
                    failed_tasks.append({'id': task_id, 'reason': f'يوجد {len(pending_reqs)} متطلبات معلقة'})
                    continue
            
            # بدء المهمة
            task.status = 'in_progress'
            
            # تحديث وقت البدء الفعلي
            if not task.execution:
                task.execution = TaskExecution(task_id=task.id)
            task.execution.actual_start = datetime.utcnow()
            
            # تحديث التقدم إذا لم يكن موجوداً
            if not task.progress:
                task.progress = TaskProgress(task_id=task.id)
            task.progress.progress_percentage = 5
            
            started_tasks.append(task_id)
            
            # إنشاء إشعار للمشرف
            if task.supervisor_id and task.supervisor_id != current_user.id:
                notification = Notification(
                    user_id=task.supervisor_id,
                    title='بدء مهمة',
                    message=f'بدأ {current_user.full_name} في تنفيذ المهمة: {task.task_name}',
                    notification_type='task_started',
                    related_task_id=task.id,
                    related_project_id=task.project_id,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification)
        
        db.session.commit()
        
        # تحديث المؤشرات للمهام التي تم بدؤها
        for task_id in started_tasks:
            task = Task.query.get(task_id)
            if task and task.activity_id:
                from app.services.update_service import UpdateService
                UpdateService.update_activity_metrics(task.activity)
            if task and task.project_id:
                from app.services.update_service import UpdateService
                UpdateService.update_project_metrics(task.project)
        
        return jsonify({
            'success': True,
            'started': started_tasks,
            'failed': failed_tasks,
            'message': f'تم بدء {len(started_tasks)} مهمة بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in api_tasks_bulk_start: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
@employee_bp.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
@employee_required
def api_task_complete(task_id):
    """API لإكمال مهمة (محسنة مع التحقق من الجودة)"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        if task.status != 'in_progress':
            return jsonify({'success': False, 'error': 'المهمة ليست قيد التنفيذ'}), 400
        
        data = request.get_json() or {}
        quality = data.get('quality', 'good')
        notes = data.get('notes', '')
        
        # التحقق من اكتمال جميع المتطلبات
        pending_reqs = task.get_pending_requirements() if hasattr(task, 'get_pending_requirements') else []
        if pending_reqs:
            return jsonify({
                'success': False,
                'error': f'يوجد {len(pending_reqs)} متطلبات لم يتم التحقق منها بعد',
                'pending_requirements': True
            }), 400
        
        # التحقق من اكتمال جميع الخطوات (إذا كان هناك خطوات)
        from app.models.primavera_models import ActivityStep
        if task.activity_id:
            activity_steps = ActivityStep.query.filter_by(activity_id=task.activity_id).all()
            incomplete_steps = [s for s in activity_steps if not s.is_completed]
            if incomplete_steps and task.activity.progress_percentage < 100:
                # لا نمنع الإكمال ولكن نعطي تحذير
                pass
        
        # إكمال المهمة
        task.status = 'completed'
        
        # تحديث وقت الانتهاء الفعلي
        if not task.execution:
            task.execution = TaskExecution(task_id=task.id)
        task.execution.actual_finish = datetime.utcnow()
        
        # حساب المدة الفعلية
        if task.execution.actual_start:
            duration = task.execution.actual_finish - task.execution.actual_start
            task.execution.actual_duration = duration.total_seconds() / 3600  # بالساعات
        
        # تحديث التقدم
        if not task.progress:
            task.progress = TaskProgress(task_id=task.id)
        task.progress.progress_percentage = 100
        task.progress.completion_quality = quality
        
        # إضافة ملاحظات إذا وجدت
        if notes:
            if not task.verification:
                task.verification = TaskVerification(task_id=task.id)
            task.verification.notes = notes
        
        db.session.commit()
        
        # إنشاء إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != current_user.id:
            notification = Notification(
                user_id=task.supervisor_id,
                title='إكمال مهمة',
                message=f'أكمل {current_user.full_name} المهمة: {task.task_name}',
                notification_type='task_completed',
                related_task_id=task.id,
                related_project_id=task.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
        
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        
        # ✅ تسجيل الإكمال في النظام الذكي
        try:
            monitor = SmartMonitoringSystem()
            monitor.record_task_completion(task)
        except Exception as e:
            current_app.logger.warning(f"خطأ في تسجيل إكمال المهمة: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'تم إكمال المهمة بنجاح',
            'task': {
                'id': task.id,
                'status': task.status,
                'progress': 100,
                'actual_duration': task.execution.actual_duration if task.execution else 0
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in api_task_complete: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/<int:task_id>/progress', methods=['POST'])
@login_required
@employee_required
def api_task_progress(task_id):
    """API لتحديث تقدم المهمة (محسنة مع تحديث تلقائي للنشاط)"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        progress = data.get('progress', 0)
        notes = data.get('notes', '')
        
        if progress < 0 or progress > 100:
            return jsonify({'success': False, 'error': 'نسبة التقدم يجب أن تكون بين 0 و 100'}), 400
        
        if not task.progress:
            task.progress = TaskProgress(task_id=task.id)
        
        old_progress = task.progress.progress_percentage
        task.progress.progress_percentage = progress
        
        # حفظ تحديث التقدم
        if notes or progress != old_progress:
            from app.models.task_models import TaskProgressUpdate
            progress_update = TaskProgressUpdate(
                task_id=task.id,
                progress_percentage=progress,
                updated_by=current_user.id,
                notes=notes
            )
            db.session.add(progress_update)
        
        # إذا وصل التقدم 100%، غير الحالة إلى مكتمل
        if progress >= 100 and task.status != 'completed':
            task.status = 'completed'
            if not task.execution:
                task.execution = TaskExecution(task_id=task.id)
            task.execution.actual_finish = datetime.utcnow()
            
            # حساب المدة الفعلية
            if task.execution.actual_start:
                duration = task.execution.actual_finish - task.execution.actual_start
                task.execution.actual_duration = duration.total_seconds() / 3600
        
        db.session.commit()
        
        # ✅ تحديث مؤشرات النشاط والمشروع
        if task.activity_id:
            # تحديث تقدم النشاط بناءً على تقدم المهام
            activity = task.activity
            activity_tasks = Task.query.filter_by(activity_id=activity.id).all()
            if activity_tasks:
                avg_progress = sum(t.progress.progress_percentage if t.progress else 0 for t in activity_tasks) / len(activity_tasks)
                activity.progress_percentage = avg_progress
                
                if avg_progress >= 100:
                    activity.status = 'completed'
                    activity.actual_finish = datetime.utcnow()
                elif avg_progress > 0 and activity.status == 'not_started':
                    activity.status = 'in_progress'
                    activity.actual_start = datetime.utcnow()
                
                db.session.commit()
            
            UpdateService.update_activity_metrics(task.activity)
        
        UpdateService.update_project_metrics(task.project)
        
        return jsonify({
            'success': True,
            'progress': progress,
            'status': task.status,
            'activity_progress': task.activity.progress_percentage if task.activity_id else None
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in api_task_progress: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/<int:task_id>/pause', methods=['POST'])
@login_required
@employee_required
def api_task_pause(task_id):
    """API لإيقاف مهمة مؤقتاً"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        if task.status != 'in_progress':
            return jsonify({'success': False, 'error': 'المهمة ليست قيد التنفيذ'}), 400
        
        old_status = task.status
        task.status = 'paused'
        
        # تسجيل وقت الإيقاف
        if not task.execution:
            task.execution = TaskExecution(task_id=task.id)
        task.execution.paused_at = datetime.utcnow()
        
        db.session.commit()
        
        # إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != current_user.id:
            NotificationService.task_paused(task, current_user)
        
        return jsonify({'success': True, 'message': 'تم إيقاف المهمة مؤقتاً', 'status': task.status})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/<int:task_id>/resume', methods=['POST'])
@login_required
@employee_required
def api_task_resume(task_id):
    """API لاستئناف مهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        if task.status != 'paused':
            return jsonify({'success': False, 'error': 'المهمة ليست متوقفة'}), 400
        
        task.status = 'in_progress'
        
        db.session.commit()
        
        # إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != current_user.id:
            NotificationService.task_resumed(task, current_user)
        
        return jsonify({'success': True, 'message': 'تم استئناف المهمة', 'status': task.status})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# API Routes للأنشطة - دوال متقدمة
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/start', methods=['POST'])
@login_required
@employee_required
def api_activity_start(activity_id):
    """بدء تنفيذ النشاط (محسن)"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        if activity.status != 'not_started':
            return jsonify({'success': False, 'error': 'لا يمكن بدء نشاط بهذه الحالة'}), 400
        
        # التحقق من توفر الموارد
        missing_resources = _check_activity_resources(activity)
        if missing_resources:
            return jsonify({
                'success': False,
                'error': 'الموارد التالية غير متوفرة',
                'missing_resources': missing_resources
            }), 400
        
        # التحقق من اكتمال الأنشطة السابقة (إذا وجدت)
        from app.models.primavera_models import ActivityRelationship
        predecessors = ActivityRelationship.query.filter_by(successor_id=activity.id).all()
        incomplete_predecessors = []
        for pred in predecessors:
            predecessor = Activity.query.get(pred.predecessor_id)
            if predecessor and predecessor.status != 'completed':
                incomplete_predecessors.append({
                    'id': predecessor.id,
                    'name': predecessor.activity_name,
                    'status': predecessor.status
                })
        
        if incomplete_predecessors:
            return jsonify({
                'success': False,
                'error': 'الأنشطة السابقة لم تكتمل بعد',
                'incomplete_predecessors': incomplete_predecessors
            }), 400
        
        # بدء النشاط
        activity.status = 'in_progress'
        activity.actual_start = datetime.utcnow()
        
        db.session.commit()
        
        # إرسال إشعار للمشرف ومدير المشروع
        _notify_activity_started(activity, current_user)
        
        # ✅ تحديث المؤشرات
        UpdateService.update_activity_metrics(activity)
        UpdateService.update_project_metrics(activity.project)
        
        return jsonify({
            'success': True, 
            'message': 'تم بدء النشاط بنجاح',
            'activity': {
                'id': activity.id,
                'status': activity.status,
                'actual_start': activity.actual_start.isoformat() if activity.actual_start else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in api_activity_start: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/complete', methods=['POST'])
@login_required
@employee_required
def api_activity_complete(activity_id):
    """إكمال النشاط (محسن مع التحقق من المهام)"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        if activity.status != 'in_progress':
            return jsonify({'success': False, 'error': 'لا يمكن إكمال نشاط بهذه الحالة'}), 400
        
        # التحقق من اكتمال جميع المهام
        incomplete_tasks = Task.query.filter(
            Task.activity_id == activity_id,
            Task.status != 'completed'
        ).count()
        
        if incomplete_tasks > 0:
            return jsonify({
                'success': False,
                'error': f'يوجد {incomplete_tasks} مهام غير مكتملة',
                'incomplete_tasks': incomplete_tasks
            }), 400
        
        # التحقق من اكتمال جميع الخطوات
        incomplete_steps = ActivityStep.query.filter(
            ActivityStep.activity_id == activity_id,
            ActivityStep.is_completed == False
        ).count()
        
        if incomplete_steps > 0:
            return jsonify({
                'success': False,
                'error': f'يوجد {incomplete_steps} خطوات غير مكتملة',
                'incomplete_steps': incomplete_steps
            }), 400
        
        # إكمال النشاط
        activity.status = 'completed'
        activity.actual_finish = datetime.utcnow()
        activity.progress_percentage = 100
        
        db.session.commit()
        
        # إرسال إشعار للمشرف ومدير المشروع
        _notify_activity_completed(activity, current_user)
        
        # ✅ تحديث المؤشرات
        UpdateService.update_activity_metrics(activity)
        UpdateService.update_project_metrics(activity.project)
        
        return jsonify({
            'success': True, 
            'message': 'تم إكمال النشاط بنجاح',
            'activity': {
                'id': activity.id,
                'status': activity.status,
                'actual_finish': activity.actual_finish.isoformat() if activity.actual_finish else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in api_activity_complete: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/progress', methods=['POST'])
@login_required
@employee_required
def api_activity_progress(activity_id):
    """تحديث تقدم النشاط (محسن مع تحديث تلقائي)"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        progress = int(data.get('progress', 0))
        notes = data.get('notes', '')
        
        if progress < 0 or progress > 100:
            return jsonify({'success': False, 'error': 'نسبة التقدم يجب أن تكون بين 0 و 100'}), 400
        
        old_progress = activity.progress_percentage
        activity.progress_percentage = progress
        
        # تحديث الحالة بناءً على التقدم
        if progress >= 100 and activity.status != 'completed':
            activity.status = 'completed'
            activity.actual_finish = datetime.utcnow()
        elif progress > 0 and activity.status == 'not_started':
            activity.status = 'in_progress'
            activity.actual_start = datetime.utcnow()
        
        db.session.commit()
        
        # ✅ تحديث المؤشرات
        UpdateService.update_activity_metrics(activity)
        UpdateService.update_project_metrics(activity.project)
        
        return jsonify({
            'success': True, 
            'progress': progress, 
            'status': activity.status,
            'old_progress': old_progress
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# API Routes للمصروفات - محسنة
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/expenses', methods=['GET', 'POST'])
@login_required
@employee_required
def api_activity_expenses(activity_id):
    """إدارة مصروفات النشاط (محسنة)"""
    
    activity = Activity.query.get_or_404(activity_id)
    
    if not _has_activity_access(activity, current_user):
        return jsonify({'error': 'غير مصرح'}), 403
    
    if request.method == 'GET':
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).order_by(ActivityExpense.expense_date.desc()).all()
        
        return jsonify({
            'success': True,
            'expenses': [{
                'id': e.id,
                'date': e.expense_date.isoformat(),
                'category': e.category,
                'description': e.description,
                'amount': e.amount,
                'currency': e.currency,
                'is_approved': e.is_approved,
                'receipt_url': e.receipt_url,
                'created_by': e.creator.full_name if e.creator else '',
                'created_at': e.created_at.isoformat() if e.created_at else None
            } for e in expenses],
            'total_approved': sum(e.amount for e in expenses if e.is_approved),
            'total_pending': sum(e.amount for e in expenses if not e.is_approved)
        })
    
    else:  # POST - إضافة مصروف جديد
        try:
            data = request.get_json()
            
            # التحقق من صحة البيانات
            if not data.get('amount') or float(data.get('amount')) <= 0:
                return jsonify({'error': 'المبلغ يجب أن يكون أكبر من صفر'}), 400
            
            expense = ActivityExpense(
                activity_id=activity_id,
                expense_date=datetime.strptime(data.get('date'), '%Y-%m-%d').date() if data.get('date') else date.today(),
                category=data.get('category', 'other'),
                description=data.get('description', ''),
                amount=float(data.get('amount')),
                currency=data.get('currency', 'SAR'),
                is_approved=False,
                created_by=current_user.id
            )
            
            db.session.add(expense)
            db.session.commit()
            
            # ✅ تحديث المؤشرات
            UpdateService.update_activity_metrics(activity)
            UpdateService.update_project_metrics(activity.project)
            
            # إشعار للمشرف (للمصروفات الكبيرة)
            if expense.amount > 1000 and activity.supervisor_id:
                notification = Notification(
                    user_id=activity.supervisor_id,
                    title=f'مصروف جديد - {activity.activity_name}',
                    message=f'تم إضافة مصروف بقيمة {expense.amount} {expense.currency} للنشاط {activity.activity_name}',
                    notification_type='expense_added',
                    related_activity_id=activity.id,
                    related_project_id=activity.project_id,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification)
                db.session.commit()
            
            return jsonify({
                'success': True, 
                'expense_id': expense.id,
                'message': 'تم إضافة المصروف بنجاح'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500


# ============================================
# API Routes للمستندات - محسنة
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/documents', methods=['GET', 'POST'])
@login_required
@employee_required
def api_activity_documents(activity_id):
    """إدارة مستندات النشاط (محسنة مع رفع متعدد)"""
    
    activity = Activity.query.get_or_404(activity_id)
    
    if not _has_activity_access(activity, current_user):
        return jsonify({'error': 'غير مصرح'}), 403
    
    if request.method == 'GET':
        documents = ActivityDocument.query.filter_by(activity_id=activity_id).order_by(ActivityDocument.uploaded_at.desc()).all()
        
        return jsonify({
            'success': True,
            'documents': [{
                'id': d.id,
                'filename': d.original_filename,
                'title': d.title,
                'description': d.description,
                'file_type': d.file_type,
                'file_size': d.file_size,
                'url': d.file_url,
                'uploaded_by': d.uploader.full_name if d.uploader else '',
                'uploaded_at': d.uploaded_at.isoformat(),
                'requires_approval': d.requires_approval,
                'approval_status': d.approval_status
            } for d in documents]
        })
    
    else:  # POST - رفع مستندات جديدة
        try:
            files = request.files.getlist('files')
            if not files:
                return jsonify({'error': 'الملفات مطلوبة'}), 400
            
            title = request.form.get('title', '')
            description = request.form.get('description', '')
            requires_approval = request.form.get('requires_approval') == 'true'
            
            uploaded_documents = []
            for file in files:
                if file and file.filename:
                    # حفظ الملف
                    result = _save_document_file(file, 'activities', activity_id)
                    if result['success']:
                        document = ActivityDocument(
                            activity_id=activity_id,
                            filename=result['filename'],
                            original_filename=result['original_filename'],
                            title=title or result['original_filename'],
                            description=description,
                            file_size=file.content_length if hasattr(file, 'content_length') else 0,
                            file_type=result.get('file_type', 'other'),
                            file_url=result['file_url'],
                            requires_approval=requires_approval,
                            uploaded_by=current_user.id,
                            uploaded_at=datetime.utcnow()
                        )
                        db.session.add(document)
                        uploaded_documents.append({
                            'id': document.id,
                            'filename': document.original_filename,
                            'url': document.file_url
                        })
            
            db.session.commit()
            
            # إشعار للمشرف إذا كان المستند يحتاج موافقة
            if requires_approval and activity.supervisor_id:
                notification = Notification(
                    user_id=activity.supervisor_id,
                    title=f'مستند جديد بحاجة موافقة - {activity.activity_name}',
                    message=f'تم رفع مستند جديد: {title} ويحتاج إلى موافقتك',
                    notification_type='document_approval_needed',
                    related_activity_id=activity.id,
                    related_project_id=activity.project_id,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification)
                db.session.commit()
            
            return jsonify({
                'success': True,
                'documents': uploaded_documents,
                'message': f'تم رفع {len(uploaded_documents)} مستند بنجاح'
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500


# ============================================
# API Routes للخطوات - محسنة
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/steps', methods=['GET'])
@login_required
@employee_required
def api_activity_steps(activity_id):
    """جلب خطوات النشاط مع إحصائيات"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _has_activity_access(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        steps = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order).all()
        
        completed_steps = [s for s in steps if s.is_completed]
        progress = (len(completed_steps) / len(steps) * 100) if steps else 0
        
        return jsonify({
            'success': True,
            'steps': [{
                'id': s.id,
                'order': s.order,
                'title': s.title,
                'description': s.description,
                'is_completed': s.is_completed,
                'completed_at': s.completed_at.isoformat() if s.completed_at else None,
                'completed_by': s.completer.full_name if s.completer else None
            } for s in steps],
            'stats': {
                'total': len(steps),
                'completed': len(completed_steps),
                'pending': len(steps) - len(completed_steps),
                'progress': round(progress, 1)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/steps/<int:step_id>/complete', methods=['POST'])
@login_required
@employee_required
def api_activity_step_complete(activity_id, step_id):
    """تحديد خطوة كمكتملة (محسن)"""
    try:
        step = ActivityStep.query.get_or_404(step_id)
        
        if step.activity_id != activity_id:
            return jsonify({'error': 'الخطوة لا تنتمي لهذا النشاط'}), 400
        
        if not _can_update_activity(step.activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        if step.is_completed:
            return jsonify({'error': 'الخطوة مكتملة بالفعل'}), 400
        
        step.is_completed = True
        step.completed_at = datetime.utcnow()
        step.completed_by = current_user.id
        
        db.session.commit()
        
        # تحديث تقدم النشاط بناءً على الخطوات
        _update_activity_progress_from_steps(step.activity)
        
        # ✅ تحديث المؤشرات
        UpdateService.update_activity_metrics(step.activity)
        UpdateService.update_project_metrics(step.activity.project)
        
        return jsonify({
            'success': True, 
            'message': 'تم إكمال الخطوة بنجاح',
            'activity_progress': step.activity.progress_percentage
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# API Routes للموارد - محسنة
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/resources/request', methods=['POST'])
@login_required
@employee_required
def api_activity_resource_request(activity_id):
    """طلب موارد إضافية للنشاط (محسن)"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        resource_id = data.get('resource_id')
        quantity = float(data.get('quantity', 0))
        required_by = data.get('required_by')  # تاريخ الاستلام المطلوب
        
        if not resource_id or quantity <= 0:
            return jsonify({'error': 'بيانات غير صالحة'}), 400
        
        from app.models.primavera_models import Resource
        resource = Resource.query.get(resource_id)
        if not resource:
            return jsonify({'error': 'المورد غير موجود'}), 404
        
        # إنشاء طلب مورد جديد
        required_date = datetime.strptime(required_by, '%Y-%m-%d').date() if required_by else datetime.now().date() + timedelta(days=7)
        
        resource_request = ResourceRequest(
            org_id=activity.project.org_id,
            project_id=activity.project_id,
            supplier_id=resource.supplier_id,  # من المورد المرتبط بالمورد
            required_date=required_date,
            notes=f'طلب مورد للنشاط {activity.activity_name} - الكمية: {quantity}',
            status='pending',
            created_by=current_user.id
        )
        
        db.session.add(resource_request)
        db.session.flush()
        
        # إضافة بند الطلب
        request_item = ResourceRequestItem(
            request_id=resource_request.id,
            resource_id=resource_id,
            resource_name=resource.name,
            unit=resource.unit,
            required_quantity=quantity,
            remaining_quantity=quantity,
            notes=f'مطلوب للنشاط {activity.activity_name}'
        )
        
        db.session.add(request_item)
        db.session.commit()
        
        # إرسال إشعار لمدير المشروع
        if activity.project.project_manager_id:
            notification = Notification(
                user_id=activity.project.project_manager_id,
                title=f'طلب موارد جديدة - {activity.activity_name}',
                message=f'تم طلب {quantity} {resource.unit} من {resource.name} للنشاط {activity.activity_name}',
                notification_type='resource_request',
                related_activity_id=activity.id,
                related_project_id=activity.project_id,
                related_link=url_for('projects.project_resource_requests', project_id=activity.project_id),
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
        
        return jsonify({
            'success': True, 
            'request_id': resource_request.id,
            'message': 'تم إرسال طلب الموارد بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# API Routes للبحث والتصفية - محسنة
# ============================================

@employee_bp.route('/api/tasks/search')
@login_required
@employee_required
def api_task_search():
    """API للبحث في المهام (محسن)"""
    try:
        query = request.args.get('q', '')
        status_filter = request.args.get('status', 'all')
        
        if len(query) < 2:
            return jsonify({'success': True, 'tasks': []})
        
        tasks = get_user_tasks(current_user)
        
        # فلترة النتائج حسب الاستعلام والحالة
        results = []
        for task in tasks:
            # تطبيق فلتر الحالة
            if status_filter != 'all' and task.status != status_filter:
                continue
            
            # البحث في النص
            if (query.lower() in task.task_name.lower() or
                (task.project and query.lower() in task.project.name.lower()) or
                (task.task_code and query.lower() in task.task_code.lower())):
                
                # حساب الوقت المتبقي
                planned_end = get_task_planned_end(task)
                remaining_days = None
                if planned_end and task.status != 'completed':
                    days = (planned_end - date.today()).days
                    if days > 0:
                        remaining_days = days
                    elif days == 0:
                        remaining_days = 0
                    else:
                        remaining_days = -days  # متأخر
                
                results.append({
                    'id': task.id,
                    'name': task.task_name,
                    'code': task.task_code,
                    'project': task.project.name if task.project else None,
                    'project_id': task.project_id,
                    'status': task.status,
                    'progress': task.progress.progress_percentage if task.progress else 0,
                    'priority': task.priority,
                    'planned_end': planned_end.isoformat() if planned_end else None,
                    'remaining_days': remaining_days,
                    'url': url_for('employee.view_task', task_id=task.id)
                })
        
        # ترتيب النتائج حسب الأولوية ثم التاريخ
        results.sort(key=lambda x: (-x.get('priority', 0), x.get('planned_end') or ''))
        
        return jsonify({
            'success': True,
            'tasks': results[:20]  # أقصى 20 نتيجة
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in api_task_search: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/filter-by-date')
@login_required
@employee_required
def api_tasks_by_date():
    """API لتصفية المهام حسب التاريخ"""
    try:
        period = request.args.get('period', 'week')  # today, week, month
        tasks = get_user_tasks(current_user)
        
        today = date.today()
        
        if period == 'today':
            filtered = [t for t in tasks if is_today(get_task_planned_date(t))]
        elif period == 'week':
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)
            filtered = [t for t in tasks if get_task_planned_date(t) and week_start <= get_task_planned_date(t) <= week_end]
        elif period == 'month':
            month_start = date(today.year, today.month, 1)
            if today.month == 12:
                month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)
            filtered = [t for t in tasks if get_task_planned_date(t) and month_start <= get_task_planned_date(t) <= month_end]
        else:
            filtered = tasks
        
        return jsonify({
            'success': True,
            'count': len(filtered),
            'tasks': [{
                'id': t.id,
                'name': t.task_name,
                'date': get_task_planned_date(t).isoformat() if get_task_planned_date(t) else None,
                'status': t.status
            } for t in filtered[:50]]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# إحصائيات المستخدم - API محسن
# ============================================

@employee_bp.route('/api/my-performance')
@login_required
@employee_required
def api_my_performance():
    """API لأداء المستخدم مع تحليلات متقدمة"""
    try:
        tasks = get_user_tasks(current_user)
        activities = get_user_activities(current_user)
        
        # إحصائيات المهام
        total_tasks = len(tasks)
        completed_tasks = len([t for t in tasks if t.status == 'completed'])
        on_time_tasks = 0
        early_tasks = 0
        delayed_tasks = 0
        
        # حساب المهام المنتهية في الوقت المحدد والمبكرة والمتأخرة
        for task in tasks:
            if task.status == 'completed' and task.execution and task.planning:
                if task.execution.actual_finish and task.planning.planned_finish:
                    if task.execution.actual_finish <= task.planning.planned_finish:
                        on_time_tasks += 1
                        if task.execution.actual_finish < task.planning.planned_finish:
                            early_tasks += 1
                    else:
                        delayed_tasks += 1
        
        # متوسط الجودة
        total_quality = 0
        quality_count = 0
        for task in tasks:
            if task.progress and task.progress.completion_quality:
                quality_map = {'excellent': 5, 'good': 4, 'fair': 3, 'poor': 2}
                total_quality += quality_map.get(task.progress.completion_quality, 0)
                quality_count += 1
        
        avg_quality = total_quality / quality_count if quality_count > 0 else 0
        
        # إحصائيات الأنشطة
        total_activities = len(activities)
        completed_activities = len([a for a in activities if a.status == 'completed'])
        avg_activity_progress = sum(a.progress_percentage or 0 for a in activities) / total_activities if total_activities > 0 else 0
        
        # الأداء الأسبوعي (آخر 4 أسابيع)
        weekly_performance = []
        for i in range(4, 0, -1):
            week_start = datetime.now().date() - timedelta(days=i*7)
            week_end = week_start + timedelta(days=6)
            
            week_tasks = []
            for task in tasks:
                if task.created_at:
                    task_date = to_date(task.created_at)
                    if task_date and week_start <= task_date <= week_end:
                        week_tasks.append(task)
            
            week_completed = len([t for t in week_tasks if t.status == 'completed'])
            week_total = len(week_tasks)
            
            weekly_performance.append({
                'week': f'الأسبوع {5-i}',
                'start_date': week_start.strftime('%Y-%m-%d'),
                'end_date': week_end.strftime('%Y-%m-%d'),
                'completed': week_completed,
                'total': week_total,
                'completion_rate': (week_completed / week_total * 100) if week_total > 0 else 0
            })
        
        # اتجاه الأداء (تحسن/تراجع)
        performance_trend = 'stable'
        if len(weekly_performance) >= 2:
            current_rate = weekly_performance[-1]['completion_rate']
            previous_rate = weekly_performance[-2]['completion_rate']
            if current_rate > previous_rate + 10:
                performance_trend = 'improving'
            elif current_rate < previous_rate - 10:
                performance_trend = 'declining'
        
        return jsonify({
            'success': True,
            'performance': {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'completion_rate': round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1),
                'on_time_rate': round((on_time_tasks / completed_tasks * 100) if completed_tasks > 0 else 0, 1),
                'early_rate': round((early_tasks / completed_tasks * 100) if completed_tasks > 0 else 0, 1),
                'delayed_rate': round((delayed_tasks / completed_tasks * 100) if completed_tasks > 0 else 0, 1),
                'avg_quality': round(avg_quality, 1),
                'total_activities': total_activities,
                'completed_activities': completed_activities,
                'avg_activity_progress': round(avg_activity_progress, 1),
                'weekly_performance': weekly_performance,
                'performance_trend': performance_trend
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in api_my_performance: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================
# إضافة دوال مساعدة إضافية
# ============================================

def _check_activity_resources(activity):
    """التحقق من توفر موارد النشاط (محسن)"""
    from app.models.primavera_models import Resource
    
    missing = []
    resources = ActivityResource.query.filter_by(activity_id=activity.id).all()
    
    for res in resources:
        resource = Resource.query.get(res.resource_id)
        if resource:
            required = res.planned_quantity - res.actual_quantity
            if required > 0 and resource.available_quantity < required:
                missing.append({
                    'id': resource.id,
                    'name': resource.name,
                    'required': required,
                    'available': resource.available_quantity,
                    'shortage': required - resource.available_quantity,
                    'unit': resource.unit
                })
    
    return missing


def _update_activity_progress_from_steps(activity):
    """تحديث تقدم النشاط بناءً على الخطوات (محسن)"""
    steps = ActivityStep.query.filter_by(activity_id=activity.id).all()
    if steps:
        completed = sum(1 for s in steps if s.is_completed)
        progress = (completed / len(steps)) * 100
        activity.progress_percentage = progress
        
        if progress >= 100 and activity.status != 'completed':
            activity.status = 'completed'
            activity.actual_finish = datetime.utcnow()
        elif progress > 0 and activity.status == 'not_started':
            activity.status = 'in_progress'
            activity.actual_start = datetime.utcnow()
        
        db.session.commit()


def _notify_activity_started(activity, user):
    """إرسال إشعار ببدء النشاط (محسن)"""
    # إشعار للمشرف
    if activity.supervisor_id and activity.supervisor_id != user.id:
        notification = Notification(
            user_id=activity.supervisor_id,
            title=f'بدء نشاط: {activity.activity_name}',
            message=f'تم بدء تنفيذ النشاط بواسطة {user.full_name}',
            notification_type='activity_started',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            related_activity_id=activity.id,
            related_project_id=activity.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    # إشعار لمدير المشروع
    if activity.project and activity.project.project_manager_id and activity.project.project_manager_id != user.id:
        notification = Notification(
            user_id=activity.project.project_manager_id,
            title=f'بدء نشاط: {activity.activity_name}',
            message=f'تم بدء تنفيذ النشاط في مشروع {activity.project.name}',
            notification_type='activity_started',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            related_activity_id=activity.id,
            related_project_id=activity.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    db.session.commit()


def _notify_activity_completed(activity, user):
    """إرسال إشعار بإكمال النشاط (محسن)"""
    # إشعار للمشرف
    if activity.supervisor_id and activity.supervisor_id != user.id:
        notification = Notification(
            user_id=activity.supervisor_id,
            title=f'إكمال نشاط: {activity.activity_name}',
            message=f'تم إكمال تنفيذ النشاط بواسطة {user.full_name}',
            notification_type='activity_completed',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            related_activity_id=activity.id,
            related_project_id=activity.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    # إشعار لمدير المشروع
    if activity.project and activity.project.project_manager_id and activity.project.project_manager_id != user.id:
        notification = Notification(
            user_id=activity.project.project_manager_id,
            title=f'إكمال نشاط: {activity.activity_name}',
            message=f'تم إكمال تنفيذ النشاط في مشروع {activity.project.name}',
            notification_type='activity_completed',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            related_activity_id=activity.id,
            related_project_id=activity.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    db.session.commit()


def _save_document_file(file, folder, activity_id):
    """حفظ ملف المستند (محسن مع دعم أنواع الملفات)"""
    import os
    import uuid
    from werkzeug.utils import secure_filename
    from flask import current_app, url_for
    
    try:
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        # تحديد نوع الملف
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        file_type_map = {
            'pdf': 'pdf', 'doc': 'word', 'docx': 'word',
            'xls': 'excel', 'xlsx': 'excel',
            'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image'
        }
        file_type = file_type_map.get(ext, 'other')
        
        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', folder, str(activity_id))
        os.makedirs(upload_path, exist_ok=True)
        
        file_path = os.path.join(upload_path, unique_filename)
        file.save(file_path)
        
        file_size = os.path.getsize(file_path)
        
        file_url = url_for('static', filename=f'uploads/{folder}/{activity_id}/{unique_filename}')
        
        return {
            'success': True,
            'filename': unique_filename,
            'original_filename': filename,
            'file_url': file_url,
            'file_path': file_path,
            'file_size': file_size,
            'file_type': file_type
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}
# ============================================
# إضافة الرواوتات المفقودة في employee_routes.py
# ============================================

# ============================================
# المشاريع الخاصة بي
# ============================================

@employee_bp.route('/my-projects')
@login_required
@employee_required
def my_projects():
    """عرض المشاريع التي يشارك فيها المستخدم"""
    try:
        # الحصول على المشاريع من المهام والأنشطة
        tasks = get_user_tasks(current_user)
        activities = get_user_activities(current_user)
        
        project_ids = set()
        for task in tasks:
            if task.project_id:
                project_ids.add(task.project_id)
        for activity in activities:
            if activity.project_id:
                project_ids.add(activity.project_id)
        
        projects = Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []
        
        # إضافة إحصائيات لكل مشروع
        projects_data = []
        for project in projects:
            project_tasks = [t for t in tasks if t.project_id == project.id]
            project_activities = [a for a in activities if a.project_id == project.id]
            
            completed_tasks = len([t for t in project_tasks if t.status == 'completed'])
            completed_activities = len([a for a in project_activities if a.status == 'completed'])
            
            projects_data.append({
                'id': project.id,
                'name': project.name,
                'code': project.project_code,
                'status': project.status,
                'progress': project.progress.progress_percentage if project.progress else 0,
                'tasks_count': len(project_tasks),
                'completed_tasks': completed_tasks,
                'activities_count': len(project_activities),
                'completed_activities': completed_activities,
                'manager': project.manager.full_name if project.manager else None
            })
        
        return render_template('employee/projects/index.html', 
                             projects=projects_data,
                             now=datetime.now())
    except Exception as e:
        logger.error(f"Error in my_projects: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.dashboard'))


@employee_bp.route('/projects/<int:project_id>')
@login_required
@employee_required
def view_my_project(project_id):
    """عرض تفاصيل مشروع معين"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # التحقق من أن المستخدم يشارك في المشروع
        tasks = get_user_tasks(current_user)
        if not any(t.project_id == project_id for t in tasks):
            activities = get_user_activities(current_user)
            if not any(a.project_id == project_id for a in activities):
                flash(_('access_denied'), 'danger')
                return redirect(url_for('employee.my_projects'))
        
        # مهام المستخدم في هذا المشروع
        user_tasks = [t for t in tasks if t.project_id == project_id]
        
        # أنشطة المستخدم في هذا المشروع
        user_activities = [a for a in activities if a.project_id == project_id]
        
        return render_template('employee/projects/view.html',
                             project=project,
                             tasks=user_tasks,
                             activities=user_activities,
                             now=datetime.now())
    except Exception as e:
        logger.error(f"Error in view_my_project: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.my_projects'))


# ============================================
# التقارير اليومية
# ============================================

@employee_bp.route('/daily-reports')
@login_required
@employee_required
def daily_reports():
    """عرض التقارير اليومية الخاصة بي"""
    try:
        from app.models.task_models import DailyReport
        
        reports = DailyReport.query.filter_by(
            prepared_by=current_user.id
        ).order_by(DailyReport.report_date.desc()).all()
        
        return render_template('employee/reports/daily.html', 
                             reports=reports,
                             now=datetime.now())
    except Exception as e:
        logger.error(f"Error in daily_reports: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.dashboard'))


@employee_bp.route('/daily-reports/create', methods=['GET', 'POST'])
@login_required
@employee_required
def create_daily_report():
    """إنشاء تقرير يومي جديد"""
    try:
        from app.models.task_models import DailyReport, DailyReportTask
        
        if request.method == 'POST':
            report_date = datetime.strptime(request.form.get('report_date'), '%Y-%m-%d').date()
            
            # التحقق من عدم وجود تقرير مكرر
            existing = DailyReport.query.filter_by(
                prepared_by=current_user.id,
                report_date=report_date
            ).first()
            
            if existing:
                flash(_('daily_report_exists'), 'danger')
                return redirect(url_for('employee.daily_reports'))
            
            # إنشاء التقرير
            report = DailyReport(
                project_id=request.form.get('project_id'),
                report_date=report_date,
                report_number=f"DR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                weather_condition=request.form.get('weather_condition'),
                temperature=float(request.form.get('temperature')) if request.form.get('temperature') else None,
                humidity=float(request.form.get('humidity')) if request.form.get('humidity') else None,
                work_summary=request.form.get('work_summary'),
                completed_work=request.form.get('completed_work'),
                planned_work=request.form.get('planned_work'),
                issues_encountered=request.form.get('issues_encountered'),
                safety_notes=request.form.get('safety_notes'),
                supervisor_notes=request.form.get('supervisor_notes'),
                prepared_by=current_user.id
            )
            
            db.session.add(report)
            db.session.flush()
            
            # إضافة المهام المنجزة
            task_ids = request.form.getlist('task_ids[]')
            task_progress = request.form.getlist('task_progress[]')
            task_notes = request.form.getlist('task_notes[]')
            
            for i, task_id in enumerate(task_ids):
                if task_id:
                    daily_task = DailyReportTask(
                        daily_report_id=report.id,
                        task_id=int(task_id),
                        progress_percentage=float(task_progress[i]) if i < len(task_progress) else 0,
                        notes=task_notes[i] if i < len(task_notes) else ''
                    )
                    db.session.add(daily_task)
            
            db.session.commit()
            
            # إشعار للمشرف
            if current_user.supervisor_id:
                NotificationService.daily_report_submitted(report, current_user)
            
            flash(_('daily_report_created'), 'success')
            return redirect(url_for('employee.view_daily_report', report_id=report.id))
        
        # GET request - عرض نموذج إنشاء التقرير
        tasks = get_user_tasks(current_user)
        projects = list(set(t.project for t in tasks if t.project))
        
        return render_template('employee/reports/create_daily.html',
                             projects=projects,
                             tasks=tasks,
                             now=datetime.now())
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_daily_report: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.daily_reports'))


@employee_bp.route('/daily-reports/<int:report_id>')
@login_required
@employee_required
def view_daily_report(report_id):
    """عرض تقرير يومي"""
    try:
        from app.models.task_models import DailyReport
        
        report = DailyReport.query.get_or_404(report_id)
        
        if report.prepared_by != current_user.id and current_user.role != 'supervisor':
            flash(_('access_denied'), 'danger')
            return redirect(url_for('employee.daily_reports'))
        
        return render_template('employee/reports/view_daily.html',
                             report=report,
                             now=datetime.now())
    except Exception as e:
        logger.error(f"Error in view_daily_report: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.daily_reports'))


# ============================================
# تصدير التقارير
# ============================================

@employee_bp.route('/export/my-tasks')
@login_required
@employee_required
def export_my_tasks():
    """تصدير مهامي إلى Excel"""
    try:
        import pandas as pd
        import io
        
        tasks = get_user_tasks(current_user)
        
        data = []
        for task in tasks:
            data.append({
                _('task_code'): task.task_code,
                _('task_name'): task.task_name,
                _('project'): task.project.name if task.project else '-',
                _('status'): task.status,
                _('progress'): f"{get_task_progress(task)}%",
                _('planned_start'): format_date(get_task_planned_date(task)),
                _('planned_end'): format_date(get_task_planned_end(task)),
                _('priority'): task.priority,
                _('created_at'): format_datetime(task.created_at)
            })
        
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=_('my_tasks'), index=False)
        
        output.seek(0)
        filename = f"my_tasks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logger.error(f"Error in export_my_tasks: {str(e)}")
        flash(str(e), 'danger')
        return redirect(url_for('employee.my_tasks'))


# @employee_bp.route('/export/my-performance')
# @login_required
# @employee_required
# def export_my_performance():
#     """تصدير أدائي إلى CSV"""
#     try:
#         import csv
#         import io
        
#         tasks = get_user_tasks(current_user)
        
#         output = io.StringIO()
#         writer = csv.writer(output)
        
#         # كتابة الرأس
#         writer.writerow([
#             _('task_code'), _('task_name'), _('project'), _('status'),
#             _('progress'), _('planned_start'), _('planned_end'), 
#             _('actual_start'), _('actual_end'), _('quality')
#         ])
        
#         # كتابة البيانات
#         for task in tasks:
#             writer.writerow([
#                 task.task_code,
#                 task.task_name,
#                 task.project.name if task.project else '-',
#                 task.status,
#                 get_task_progress(task),
#                 format_date(get_task_planned_date(task)),
#                 format_date(get_task_planned_end(task)),
#                 format_datetime(task.execution.actual_start) if task.execution else '-',
#                 format_datetime(task.execution.actual_finish) if task.execution else '-',
#                 task.progress.completion_quality if task.progress else '-'
#             ])
        
#         output.seek(0)
#         filename = f"my_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
#         return send_file(
#             io.BytesIO(output.getvalue().encode('utf-8-sig')),
#             mimetype='text/csv',
#             as_attachment=True,
#             download_name=filename
#         )
#     except Exception as e:
#         logger.error(f"Error in export_my_performance: {str(e)}")
#         flash(str(e), 'danger')
#         return redirect(url_for('employee.dashboard'))


# ============================================
# التقويم
# ============================================

@employee_bp.route('/calendar')
@login_required
@employee_required
def calendar():
    """عرض التقويم مع المهام والأنشطة"""
    return render_template('employee/calendar/index.html', now=datetime.now())


@employee_bp.route('/api/calendar/events')
@login_required
@employee_required
def api_calendar_events():
    """API لجلب أحداث التقويم"""
    try:
        start_date = request.args.get('start')
        end_date = request.args.get('end')
        
        tasks = get_user_tasks(current_user)
        
        events = []
        for task in tasks:
            planned_start = get_task_planned_date(task)
            planned_end = get_task_planned_end(task)
            
            if planned_start and planned_end:
                events.append({
                    'id': task.id,
                    'title': task.task_name,
                    'start': planned_start.isoformat(),
                    'end': planned_end.isoformat(),
                    'backgroundColor': '#4361ee' if task.status != 'completed' else '#00b894',
                    'borderColor': '#4361ee' if task.status != 'completed' else '#00b894',
                    'url': url_for('employee.view_task', task_id=task.id),
                    'extendedProps': {
                        'type': 'task',
                        'status': task.status,
                        'progress': get_task_progress(task)
                    }
                })
        
        return jsonify(events)
    except Exception as e:
        logger.error(f"Error in api_calendar_events: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================
# الوقت المسجل (Time Tracking)
# ============================================

@employee_bp.route('/api/tasks/<int:task_id>/log-time', methods=['POST'])
@login_required
@employee_required
def api_log_task_time(task_id):
    """تسجيل وقت العمل على المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'error': _('access_denied')}), 403
        
        data = request.get_json()
        hours = float(data.get('hours', 0))
        date_logged = datetime.strptime(data.get('date', datetime.now().strftime('%Y-%m-%d')), '%Y-%m-%d').date()
        description = data.get('description', '')
        
        if hours <= 0:
            return jsonify({'error': _('invalid_hours')}), 400
        
        # إنشاء سجل وقت
        from app.models import TaskTimeLog
        time_log = TaskTimeLog(
            task_id=task_id,
            user_id=current_user.id,
            hours=hours,
            date_logged=date_logged,
            description=description
        )
        
        db.session.add(time_log)
        db.session.commit()
        
        # تحديث إجمالي الوقت المسجل للمهمة
        total_hours = db.session.query(func.sum(TaskTimeLog.hours)).filter_by(task_id=task_id).scalar() or 0
        
        return jsonify({
            'success': True,
            'message': _('time_logged_success'),
            'total_hours': total_hours,
            'log': {
                'id': time_log.id,
                'hours': hours,
                'date': date_logged.isoformat(),
                'description': description
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in api_log_task_time: {str(e)}")
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/tasks/<int:task_id>/time-logs')
@login_required
@employee_required
def api_task_time_logs(task_id):
    """جلب سجل وقت المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'error': _('access_denied')}), 403
        
        from app.models.task_models import TaskTimeLog
        time_logs = TaskTimeLog.query.filter_by(task_id=task_id).order_by(TaskTimeLog.date_logged.desc()).all()
        
        return jsonify({
            'success': True,
            'time_logs': [{
                'id': log.id,
                'hours': log.hours,
                'date': log.date_logged.isoformat(),
                'description': log.description,
                'created_at': log.created_at.isoformat() if log.created_at else None
            } for log in time_logs]
        })
    except Exception as e:
        logger.error(f"Error in api_task_time_logs: {str(e)}")
        return jsonify({'error': str(e)}), 500

@employee_bp.route('/api/search')
@login_required
@employee_required
def api_advanced_search():
    """API للبحث المتقدم"""
    try:
        query = request.args.get('q', '').strip()
        type_filter = request.args.get('type', 'all')
        status_filter = request.args.get('status', 'all')
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        
        if not query:
            return jsonify({'success': True, 'results': []})
        
        results = []
        user_tasks = get_user_tasks(current_user)
        user_activities = get_user_activities(current_user)
        
        # البحث في المهام
        if type_filter in ['all', 'task']:
            for task in user_tasks:
                if (query.lower() in task.task_name.lower() or 
                    query.lower() in (task.task_code or '').lower() or
                    (task.description and query.lower() in task.description.lower())):
                    
                    if status_filter != 'all' and task.status != status_filter:
                        continue
                    
                    results.append({
                        'type': 'task',
                        'id': task.id,
                        'title': task.task_name,
                        'description': task.description,
                        'status': task.status,
                        'project_name': task.project.name if task.project else None,
                        'date': get_task_planned_end(task),
                        'url': url_for('employee.view_task', task_id=task.id)
                    })
        
        # البحث في الأنشطة
        if type_filter in ['all', 'activity']:
            for activity in user_activities:
                if (query.lower() in activity.activity_name.lower() or
                    query.lower() in (activity.activity_id or '').lower()):
                    
                    if status_filter != 'all' and activity.status != status_filter:
                        continue
                    
                    results.append({
                        'type': 'activity',
                        'id': activity.id,
                        'title': activity.activity_name,
                        'description': activity.description,
                        'status': activity.status,
                        'project_name': activity.project.name if activity.project else None,
                        'date': activity.planned_finish,
                        'url': url_for('employee.view_activity', activity_id=activity.id)
                    })
        
        # ترتيب النتائج
        results.sort(key=lambda x: x['date'] or '', reverse=True)
        
        return jsonify({'success': True, 'results': results[:50]})
        
    except Exception as e:
        logger.error(f"Error in api_advanced_search: {str(e)}")
        return jsonify({'error': str(e)}), 500
@employee_bp.route('/notifications')
@login_required
def notifications():
    """عرض جميع الإشعارات"""
    
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('employee/notifications/index.html', notifications=notifications)

@employee_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """تحديد إشعار كمقروء"""
    
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    notification.is_read = True
    notification.read_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})

@employee_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """تحديد جميع الإشعارات كمقروءة"""
    
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True, 'read_at': datetime.utcnow()})
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم تحديد جميع الإشعارات كمقروءة'})

# ============================================
# الملف الشخصي
# ============================================

@employee_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """الملف الشخصي للمستخدم"""
    
    if request.method == 'POST':
        try:
            # تحديث البيانات الشخصية
            current_user.full_name = request.form.get('full_name', current_user.full_name)
            current_user.phone = request.form.get('phone', current_user.phone)
            current_user.mobile = request.form.get('mobile', current_user.mobile)
            current_user.job_title = request.form.get('job_title', current_user.job_title)
            
            # تغيير كلمة المرور إذا تم إدخالها
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            if current_password and new_password and confirm_password:
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
            flash('تم تحديث البيانات بنجاح', 'success')
            return redirect(url_for('employee.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # إحصائيات المستخدم
    hire_date = current_user.hire_date if hasattr(current_user, 'hire_date') else None
    days_active = (datetime.now().date() - hire_date).days if hire_date else 0
    
    stats = {
        'tasks_completed': Task.query.filter_by(supervisor_id=current_user.id, status='completed').count() if current_user.role == 'supervisor' else 0,
        'days_active': days_active,
        'login_count': getattr(current_user, 'login_count', 0),
        'last_login': getattr(current_user, 'last_login', None)
    }
    
    return render_template('employee/profile/index.html', user=current_user, stats=stats)
@employee_bp.route('/update-notification-settings', methods=['POST'])
@login_required
@employee_required
def update_notification_settings():
    """تحديث إعدادات الإشعارات والمظهر للمستخدم"""
    try:
        # تحديث إعدادات الإشعارات
        current_user.email_notifications = request.form.get('email_notifications') == 'on'
        current_user.push_notifications = request.form.get('push_notifications') == 'on'
        current_user.task_reminders = request.form.get('task_reminders') == 'on'
        current_user.daily_digest = request.form.get('daily_digest') == 'on'
        
        # تحديث إعدادات المظهر
        current_user.theme = request.form.get('theme', 'light')
        current_user.sidebar_collapsed = request.form.get('sidebar_collapsed') == 'on'
        
        db.session.commit()
        
        flash('تم تحديث إعدادات الإشعارات بنجاح', 'success')
        return redirect(url_for('employee.profile'))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in update_notification_settings: {str(e)}")
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('employee.profile'))


@employee_bp.route('/api/update-settings', methods=['POST'])
@login_required
@employee_required
def api_update_settings():
    """API لتحديث إعدادات المستخدم (للاستخدام مع AJAX)"""
    try:
        data = request.get_json()
        
        # تحديث إعدادات الإشعارات
        if 'email_notifications' in data:
            current_user.email_notifications = bool(data['email_notifications'])
        if 'push_notifications' in data:
            current_user.push_notifications = bool(data['push_notifications'])
        if 'task_reminders' in data:
            current_user.task_reminders = bool(data['task_reminders'])
        if 'daily_digest' in data:
            current_user.daily_digest = bool(data['daily_digest'])
        
        # تحديث إعدادات المظهر
        if 'theme' in data:
            current_user.theme = data['theme']
        if 'sidebar_collapsed' in data:
            current_user.sidebar_collapsed = bool(data['sidebar_collapsed'])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم تحديث الإعدادات بنجاح',
            'settings': {
                'email_notifications': current_user.email_notifications,
                'push_notifications': current_user.push_notifications,
                'task_reminders': current_user.task_reminders,
                'daily_digest': current_user.daily_digest,
                'theme': current_user.theme,
                'sidebar_collapsed': current_user.sidebar_collapsed
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in api_update_settings: {str(e)}")
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/get-settings', methods=['GET'])
@login_required
@employee_required
def get_settings():
    """API لجلب إعدادات المستخدم الحالية"""
    try:
        return jsonify({
            'success': True,
            'settings': {
                'email_notifications': current_user.email_notifications,
                'push_notifications': current_user.push_notifications,
                'task_reminders': current_user.task_reminders,
                'daily_digest': current_user.daily_digest,
                'theme': current_user.theme,
                'sidebar_collapsed': current_user.sidebar_collapsed
            }
        })
    except Exception as e:
        logger.error(f"Error in get_settings: {str(e)}")
        return jsonify({'error': str(e)}), 500
def format_date(date_obj):
    """تنسيق التاريخ بشكل آمن"""
    if date_obj is None:
        return '-'
    
    # إذا كان التاريخ نصياً
    if isinstance(date_obj, str):
        try:
            date_obj = datetime.strptime(date_obj, '%Y-%m-%d')
        except:
            try:
                date_obj = datetime.strptime(date_obj, '%Y-%m-%d %H:%M:%S')
            except:
                return date_obj
    
    # إذا كان DateTime حوله إلى Date
    if isinstance(date_obj, datetime):
        date_obj = date_obj.date()
    
    if hasattr(date_obj, 'strftime'):
        try:
            return date_obj.strftime('%Y-%m-%d')
        except:
            return str(date_obj)
    return str(date_obj)

def format_datetime(dt_obj):
    """تنسيق التاريخ والوقت بشكل آمن"""
    if dt_obj is None:
        return '-'
    
    # إذا كان التاريخ نصياً
    if isinstance(dt_obj, str):
        try:
            dt_obj = datetime.strptime(dt_obj, '%Y-%m-%d %H:%M:%S')
        except:
            try:
                dt_obj = datetime.strptime(dt_obj, '%Y-%m-%d')
            except:
                return dt_obj
    
    if hasattr(dt_obj, 'strftime'):
        try:
            return dt_obj.strftime('%Y-%m-%d %H:%M')
        except:
            return str(dt_obj)
    return str(dt_obj)
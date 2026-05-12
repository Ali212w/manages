"""
dashboard_routes.py - لوحة التحكم المتقدمة مع دعم جميع الفلاتر
"""

from flask import render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.routes import dashboard_bp
from app.models import db, Project, Activity, Task, TaskResource, Resource, User,ProjectBudget
from app.models import ProjectDocument, Notification, Organization, Department,TaskAssignment
from app.models import Issue, QualityCheck, Milestone, Invoice, Payment, PlatformAdmin
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
import logging

logger = logging.getLogger(__name__)


# ============================================
# Route: لوحة التحكم - إعادة توجيه حسب الدور
# ============================================
@dashboard_bp.route('/')
@dashboard_bp.route('/index')
@login_required
def index():
    """نقطة دخول موحدة - تعيد التوجيه للوحة المخصصة حسب الدور."""
    if isinstance(current_user, PlatformAdmin):
        return redirect(url_for('platform.dashboard'))
    if hasattr(current_user, 'role'):
        role = current_user.role
        if role == 'platform_admin':
            return redirect(url_for('platform.dashboard'))
        if role == 'org_admin':
            return redirect(url_for('company.dashboard'))
        if role == 'supplier':
            return redirect(url_for('supplier.dashboard'))
        if role == 'client':
            return redirect(url_for('client.dashboard'))
        if role == 'consultant':
            return redirect(url_for('consultant.dashboard'))
        if role in ['project_manager', 'supervisor', 'delegate', 'employee']:
            return redirect(url_for('role_dashboard.my_dashboard'))
    return redirect(url_for('auth.login'))


@dashboard_bp.route('/analytics')
@login_required
def analytics():
    """مدخل تحليلات اختصاري للوحة المتقدمة."""
    return redirect(url_for('dashboard.advanced_dashboard'))


# ============================================
# Route: عرض لوحة التحكم المتقدمة
# ============================================

@dashboard_bp.route('/advanced')
@login_required
def advanced_dashboard():
    """لوحة التحكم المتقدمة مع جميع الفلاتر"""
    
    org_id = current_user.org_id
    
    # جلب البيانات الأساسية
    projects = Project.query.filter_by(org_id=org_id).all()
    users = User.query.filter_by(org_id=org_id, is_user_active=True).all()
    departments = Department.query.filter_by(org_id=org_id, is_active=True).all()
    
    # الحصول على قيم الفلاتر من URL
    filter_project = request.args.get('project', 'all')
    filter_department = request.args.get('department', 'all')
    filter_resource = request.args.getlist('resource')
    filter_status = request.args.getlist('status')
    filter_priority = request.args.getlist('priority')
    filter_date_from = request.args.get('date_from', '')
    filter_date_to = request.args.get('date_to', '')
    filter_progress_min = request.args.get('progress_min', 0, type=int)
    filter_progress_max = request.args.get('progress_max', 100, type=int)
    filter_budget_min = request.args.get('budget_min', 0, type=float)
    filter_budget_max = request.args.get('budget_max', 10000000, type=float)
    
    # تطبيق الفلاتر على المشاريع
    filtered_projects = apply_project_filters(
        projects, filter_project, filter_department, filter_resource,
        filter_status, filter_priority, filter_date_from, filter_date_to,
        filter_progress_min, filter_progress_max, filter_budget_min, filter_budget_max
    )
    
    # حساب جميع المقاييس
    general_stats = calculate_general_stats(filtered_projects)
    delay_analysis = calculate_advanced_delay_analysis(
        filtered_projects, filter_resource, filter_status, filter_priority
    )
    task_analysis = calculate_task_analysis(filtered_projects, filter_status, filter_priority)
    resource_analysis = calculate_resource_analysis(filtered_projects, filter_resource)
    financial_analysis = calculate_financial_analysis(
        filtered_projects, filter_date_from, filter_date_to, filter_budget_min, filter_budget_max
    )
    timeline_data = calculate_timeline_data(filtered_projects, filter_date_from, filter_date_to)
    gantt_data = calculate_gantt_data(filtered_projects)
    # إضافة متغيرات الإشعارات
    notifications_count = Notification.query.filter_by(
        user_id=current_user.id, 
        is_read=False
    ).count()
    
    recent_notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Notification.created_at.desc()
    ).limit(10).all()
    
    def time_ago(dt):
        if not dt:
            return ''
        now = datetime.utcnow()
        diff = now - dt
        if diff.days > 365:
            return f'منذ {diff.days // 365} سنة'
        elif diff.days > 30:
            return f'منذ {diff.days // 30} شهر'
        elif diff.days > 0:
            return f'منذ {diff.days} يوم'
        elif diff.seconds > 3600:
            return f'منذ {diff.seconds // 3600} ساعة'
        elif diff.seconds > 60:
            return f'منذ {diff.seconds // 60} دقيقة'
        else:
            return 'منذ لحظات'
    return render_template('dashboard/advanced.html',
                         projects=projects,
                         users=users,
                         departments=departments,
                         general_stats=general_stats,
                         delay_analysis=delay_analysis,
                         task_analysis=task_analysis,
                         resource_analysis=resource_analysis,
                         financial_analysis=financial_analysis,
                         timeline_data=timeline_data,
                         gantt_data=gantt_data,
                         current_filters={
                             'project': filter_project,
                             'department': filter_department,
                             'resources': filter_resource,
                             'statuses': filter_status,
                             'priorities': filter_priority,
                             'date_from': filter_date_from,
                             'date_to': filter_date_to,
                             'progress_min': filter_progress_min,
                             'progress_max': filter_progress_max,
                             'budget_min': filter_budget_min,
                             'budget_max': filter_budget_max
                         },
                         notifications_count=notifications_count,
                         recent_notifications=recent_notifications,
                         time_ago=time_ago,
                         now=datetime.now())


# ============================================
# API: جلب بيانات لوحة التحكم (AJAX)
# ============================================

@dashboard_bp.route('/api/dashboard-data', methods=['POST'])
@login_required
def api_dashboard_data():
    """API لجلب بيانات لوحة التحكم المصفاة"""
    try:
        filters = request.get_json() or {}
        
        org_id = current_user.org_id
        projects = Project.query.filter_by(org_id=org_id).all()
        
        # تطبيق الفلاتر
        filtered_projects = apply_project_filters_from_dict(projects, filters)
        
        data = {
            'general_stats': calculate_general_stats(filtered_projects),
            'delay_analysis': calculate_advanced_delay_analysis(
                filtered_projects, 
                filters.get('resources', []),
                filters.get('status', []),
                filters.get('priority', [])
            ),
            'task_analysis': calculate_task_analysis(
                filtered_projects,
                filters.get('status', []),
                filters.get('priority', [])
            ),
            'resource_analysis': calculate_resource_analysis(
                filtered_projects,
                filters.get('resources', [])
            ),
            'financial_analysis': calculate_financial_analysis(
                filtered_projects,
                filters.get('date_from', ''),
                filters.get('date_to', ''),
                filters.get('budget_min', 0),
                filters.get('budget_max', 10000000)
            ),
            'timeline_data': calculate_timeline_data(
                filtered_projects,
                filters.get('date_from', ''),
                filters.get('date_to', '')
            ),
            'gantt_data': calculate_gantt_data(filtered_projects)
        }
        
        return jsonify({'success': True, 'data': data})
        
    except Exception as e:
        logger.error(f"خطأ في api_dashboard_data: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# دوال تطبيق الفلاتر
# ============================================

def apply_project_filters(projects, project_id, department, resources, statuses, priorities,
                         date_from, date_to, progress_min, progress_max, budget_min, budget_max):
    """تطبيق جميع الفلاتر على المشاريع"""
    filtered = projects
    
    # فلتر المشروع
    if project_id != 'all':
        filtered = [p for p in filtered if p.id == int(project_id)]
    
    # فلتر القسم
    if department != 'all':
        filtered = [p for p in filtered if p.department and p.department.name == department]
    
    # فلتر الموارد
    if resources:
        filtered = [p for p in filtered if has_project_resource(p, resources)]
    
    # فلتر الحالة
    if statuses:
        filtered = [p for p in filtered if p.status in statuses]
    
    # فلتر الأولوية
    if priorities:
        filtered = [p for p in filtered if p.priority_level and str(p.priority_level) in priorities]
    
    # فلتر التاريخ
    if date_from:
        try:
            from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
            filtered = [p for p in filtered if p.created_at and p.created_at.date() >= from_date]
        except:
            pass
    
    if date_to:
        try:
            to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
            filtered = [p for p in filtered if p.created_at and p.created_at.date() <= to_date]
        except:
            pass
    
    # فلتر نسبة الإنجاز
    if progress_min > 0 or progress_max < 100:
        filtered = [p for p in filtered if progress_min <= p.get_progress() <= progress_max]
    
    # فلتر الميزانية
    if budget_min > 0 or budget_max < 10000000:
        filtered = [p for p in filtered if p.budget and budget_min <= p.budget.current_budget <= budget_max]
    
    return filtered


def apply_project_filters_from_dict(projects, filters):
    """تطبيق الفلاتر من قاموس (لـ API)"""
    filtered = projects
    
    if filters.get('project') and filters['project'] != 'all':
        filtered = [p for p in filtered if p.id == int(filters['project'])]
    
    if filters.get('department') and filters['department'] != 'all':
        filtered = [p for p in filtered if p.department and p.department.name == filters['department']]
    
    if filters.get('resources'):
        filtered = [p for p in filtered if has_project_resource(p, filters['resources'])]
    
    if filters.get('status'):
        filtered = [p for p in filtered if p.status in filters['status']]
    
    if filters.get('priority'):
        filtered = [p for p in filtered if p.priority_level and str(p.priority_level) in filters['priority']]
    
    if filters.get('date_from'):
        try:
            from_date = datetime.strptime(filters['date_from'], '%Y-%m-%d').date()
            filtered = [p for p in filtered if p.created_at and p.created_at.date() >= from_date]
        except:
            pass
    
    if filters.get('date_to'):
        try:
            to_date = datetime.strptime(filters['date_to'], '%Y-%m-%d').date()
            filtered = [p for p in filtered if p.created_at and p.created_at.date() <= to_date]
        except:
            pass
    
    if filters.get('progress_min', 0) > 0 or filters.get('progress_max', 100) < 100:
        progress_min = filters.get('progress_min', 0)
        progress_max = filters.get('progress_max', 100)
        filtered = [p for p in filtered if progress_min <= p.get_progress() <= progress_max]
    
    if filters.get('budget_min', 0) > 0 or filters.get('budget_max', 10000000) < 10000000:
        budget_min = filters.get('budget_min', 0)
        budget_max = filters.get('budget_max', 10000000)
        filtered = [p for p in filtered if p.budget and budget_min <= p.budget.current_budget <= budget_max]
    
    return filtered


def has_project_resource(project, resource_ids):
    """التحقق مما إذا كان المشروع يحتوي على مورد معين"""
    tasks = Task.query.filter_by(project_id=project.id).all()
    for task in tasks:
        assignments = TaskAssignment.query.filter_by(task_id=task.id).all()
        for assignment in assignments:
            if str(assignment.user_id) in resource_ids:
                return True
    return False


# ============================================
# 1. الإحصائيات العامة
# ============================================

def calculate_general_stats(projects):
    """حساب الإحصائيات العامة"""
    total_projects = len(projects)
    active_projects = len([p for p in projects if p.status == 'active'])
    completed_projects = len([p for p in projects if p.status == 'completed'])
    planning_projects = len([p for p in projects if p.status == 'planning'])
    delayed_projects = len([p for p in projects if p.is_overdue])
    
    total_budget = sum(p.budget.current_budget if p.budget else 0 for p in projects)
    total_actual_cost = sum(p.cost.total_actual_cost if p.cost else 0 for p in projects)
    total_variance = total_budget - total_actual_cost
    
    total_progress = sum(p.get_progress() for p in projects)
    avg_progress = round(total_progress / total_projects, 1) if total_projects > 0 else 0
    
    # إحصائيات المهام
    total_tasks = 0
    completed_tasks = 0
    in_progress_tasks = 0
    pending_tasks = 0
    
    for project in projects:
        tasks = Task.query.filter_by(project_id=project.id).all()
        total_tasks += len(tasks)
        completed_tasks += len([t for t in tasks if t.status == 'completed'])
        in_progress_tasks += len([t for t in tasks if t.status == 'in_progress'])
        pending_tasks += len([t for t in tasks if t.status == 'pending'])
    
    task_completion_rate = round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0
    
    return {
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'planning_projects': planning_projects,
        'delayed_projects': delayed_projects,
        'total_budget': total_budget,
        'total_actual_cost': total_actual_cost,
        'total_variance': total_variance,
        'avg_progress': avg_progress,
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'pending_tasks': pending_tasks,
        'task_completion_rate': task_completion_rate
    }


# ============================================
# 2. تحليل التأخيرات
# ============================================

def calculate_advanced_delay_analysis(projects, resource_filters, status_filters, priority_filters):
    """تحليل متقدم للتأخيرات"""
    result = {
        'total_delay_days': 0,
        'net_contractor_delay': 0,
        'net_client_delay': 0,
        'concurrent_delays': 0,
        'delayed_activities': [],
        'delay_by_priority': {'high': 0, 'medium': 0, 'low': 0},
        'delay_by_status': {}
    }
    
    today = datetime.now().date()
    
    for project in projects:
        # جلب الأنشطة المتأخرة
        activities = Activity.query.filter(
            Activity.project_id == project.id,
            Activity.planned_finish < today,
            Activity.status != 'completed'
        ).all()
        
        # تطبيق فلاتر إضافية
        if status_filters:
            activities = [a for a in activities if a.status in status_filters]
        
        for activity in activities:
            planned_finish = activity.planned_finish.date() if hasattr(activity.planned_finish, 'date') else activity.planned_finish
            delay = (today - planned_finish).days
            result['total_delay_days'] += delay
            
            # تصنيف المسؤولية
            responsibility = classify_delay_responsibility(activity, delay)
            if responsibility == 'contractor':
                result['net_contractor_delay'] += delay
            elif responsibility == 'client':
                result['net_client_delay'] += delay
            else:
                result['concurrent_delays'] += delay
            
            # تجميع حسب الأولوية
            priority = getattr(activity, 'priority', 'medium')
            priority_key = 'high' if priority <= 2 else 'medium' if priority == 3 else 'low'
            result['delay_by_priority'][priority_key] += delay
            
            result['delayed_activities'].append({
                'id': activity.id,
                'name': activity.activity_name,
                'project': project.name,
                'delay_days': delay,
                'responsible': responsibility,
                'priority': priority_key,
                'planned_finish': planned_finish.strftime('%Y-%m-%d')
            })
    
    return result


def classify_delay_responsibility(activity, delay_days):
    """تصنيف مسؤولية التأخير"""
    if delay_days > 30:
        return 'contractor'
    
    activity_name = activity.activity_name.lower() if activity.activity_name else ''
    if 'site' in activity_name or 'execution' in activity_name:
        return 'contractor'
    elif 'approval' in activity_name or 'review' in activity_name:
        return 'client'
    
    return 'concurrent'


# ============================================
# 3. تحليل المهام
# ============================================

def calculate_task_analysis(projects, status_filters, priority_filters):
    """تحليل المهام حسب الحالة والأولوية"""
    result = {
        'by_status': {'completed': 0, 'in_progress': 0, 'pending': 0, 'delayed': 0},
        'by_priority': {'high': 0, 'medium': 0, 'low': 0},
        'by_department': {},
        'recent_tasks': []
    }
    
    for project in projects:
        tasks = Task.query.filter_by(project_id=project.id).all()
        
        for task in tasks:
            # تطبيق فلاتر الحالة
            if status_filters and task.status not in status_filters:
                continue
            
            # تحديث إحصائيات الحالة
            if task.status in result['by_status']:
                result['by_status'][task.status] += 1
            
            # تحديث إحصائيات الأولوية
            priority = 'high' if task.priority <= 2 else 'medium' if task.priority == 3 else 'low'
            if priority in result['by_priority']:
                result['by_priority'][priority] += 1
            
            # تجميع حسب القسم
            if task.supervisor_id:
                user = User.query.get(task.supervisor_id)
                if user and user.department:
                    dept_name = user.department.name
                    if dept_name not in result['by_department']:
                        result['by_department'][dept_name] = 0
                    result['by_department'][dept_name] += 1
    
    # آخر 10 مهام
    recent_tasks = Task.query.join(Project).filter(
        Project.org_id == current_user.org_id
    ).order_by(Task.created_at.desc()).limit(10).all()
    
    result['recent_tasks'] = [{
        'id': t.id,
        'name': t.task_name,
        'project': t.project.name if t.project else None,
        'status': t.status,
        'created_at': t.created_at.strftime('%Y-%m-%d') if t.created_at else None
    } for t in recent_tasks]
    
    return result


# ============================================
# 4. تحليل الموارد
# ============================================

def calculate_resource_analysis(projects, resource_filters):
    """تحليل توزيع الموارد"""
    result = {
        'total_resources': 0,
        'resource_allocation': [],
        'top_performers': [],
        'workload_distribution': {}
    }
    
    resource_tasks = {}
    
    for project in projects:
        tasks = Task.query.filter_by(project_id=project.id).all()
        
        for task in tasks:
            assignments = TaskAssignment.query.filter_by(task_id=task.id).all()
            for assignment in assignments:
                user = User.query.get(assignment.user_id)
                if user:
                    if user.id not in resource_tasks:
                        resource_tasks[user.id] = {
                            'name': user.full_name,
                            'tasks_count': 0,
                            'completed_count': 0,
                            'department': user.department.name if user.department else None
                        }
                    resource_tasks[user.id]['tasks_count'] += 1
                    if task.status == 'completed':
                        resource_tasks[user.id]['completed_count'] += 1
    
    # تحويل إلى قائمة
    for user_id, data in resource_tasks.items():
        completion_rate = round((data['completed_count'] / data['tasks_count'] * 100), 1) if data['tasks_count'] > 0 else 0
        result['resource_allocation'].append({
            'id': user_id,
            'name': data['name'],
            'tasks_count': data['tasks_count'],
            'completed_count': data['completed_count'],
            'completion_rate': completion_rate,
            'department': data['department']
        })
        
        # تجميع حسب القسم
        if data['department']:
            if data['department'] not in result['workload_distribution']:
                result['workload_distribution'][data['department']] = 0
            result['workload_distribution'][data['department']] += data['tasks_count']
    
    # ترتيب حسب عدد المهام
    result['resource_allocation'].sort(key=lambda x: x['tasks_count'], reverse=True)
    result['top_performers'] = sorted(result['resource_allocation'], key=lambda x: x['completion_rate'], reverse=True)[:5]
    result['total_resources'] = len(resource_tasks)
    
    return result


# ============================================
# 5. التحليل المالي
# ============================================

def calculate_financial_analysis(projects, date_from, date_to, budget_min, budget_max):
    """تحليل البيانات المالية"""
    result = {
        'total_budget': 0,
        'total_actual': 0,
        'total_variance': 0,
        'budget_by_project': [],
        'monthly_spending': {},
        'invoice_status': {'paid': 0, 'pending': 0, 'overdue': 0},
        'budget_utilization': 0
    }
    
    for project in projects:
        if project.budget:
            budget = project.budget.current_budget or 0
            actual = project.cost.total_actual_cost or 0
            
            # تطبيق فلتر الميزانية
            if budget_min <= budget <= budget_max:
                result['total_budget'] += budget
                result['total_actual'] += actual
                result['budget_by_project'].append({
                    'name': project.name,
                    'budget': budget,
                    'actual': actual,
                    'variance': budget - actual,
                    'utilization': round((actual / budget * 100), 1) if budget > 0 else 0
                })
    
    result['total_variance'] = result['total_budget'] - result['total_actual']
    result['budget_utilization'] = round((result['total_actual'] / result['total_budget'] * 100), 1) if result['total_budget'] > 0 else 0
    
    # ترتيب حسب الاستخدام
    result['budget_by_project'].sort(key=lambda x: x['utilization'], reverse=True)
    
    return result


# ============================================
# 6. البيانات الزمنية
# ============================================

def calculate_timeline_data(projects, date_from, date_to):
    """حساب البيانات الزمنية للتقدم"""
    result = {
        'monthly_progress': [],
        'weekly_tasks': [],
        'milestones': []
    }
    
    # تقدم شهري (آخر 6 أشهر)
    today = datetime.now().date()
    for i in range(5, -1, -1):
        month_date = today.replace(day=1) - timedelta(days=i*30)
        month_key = month_date.strftime('%Y-%m')
        
        avg_progress = 0
        count = 0
        for project in projects:
            if project.progress and project.progress.updated_at:
                if project.progress.updated_at.date().year == month_date.year and \
                   project.progress.updated_at.date().month == month_date.month:
                    avg_progress += project.progress.progress_percentage or 0
                    count += 1
        
        result['monthly_progress'].append({
            'month': month_date.strftime('%b %Y'),
            'progress': round(avg_progress / count, 1) if count > 0 else 0
        })
    
    # المعالم القادمة
    for project in projects:
        milestones = Milestone.query.filter(
            Milestone.project_id == project.id,
            Milestone.planned_date >= today,
            Milestone.status == 'pending'
        ).order_by(Milestone.planned_date).limit(5).all()
        
        for milestone in milestones:
            result['milestones'].append({
                'name': milestone.name,
                'project': project.name,
                'date': milestone.planned_date.strftime('%Y-%m-%d'),
                'days_left': (milestone.planned_date - today).days
            })
    
    result['milestones'].sort(key=lambda x: x['days_left'])
    
    return result


# ============================================
# 7. بيانات مخطط جانت
# ============================================

def calculate_gantt_data(projects):
    """حساب بيانات مخطط جانت"""
    result = []
    
    for project in projects[:5]:  # آخر 5 مشاريع
        activities = Activity.query.filter_by(project_id=project.id).order_by(Activity.planned_start).limit(10).all()
        
        for activity in activities:
            if activity.planned_start and activity.planned_finish:
                result.append({
                    'id': activity.id,
                    'name': activity.activity_name,
                    'project': project.name,
                    'start': activity.planned_start.strftime('%Y-%m-%d') if activity.planned_start else None,
                    'end': activity.planned_finish.strftime('%Y-%m-%d') if activity.planned_finish else None,
                    'progress': activity.progress_percentage or 0,
                    'status': activity.status
                })
    
    return result


# ============================================
# API إضافية للفلترة الديناميكية
# ============================================

@dashboard_bp.route('/api/filter-options')
@login_required
def api_filter_options():
    """API لجلب خيارات الفلاتر المتاحة"""
    org_id = current_user.org_id
    
    # جلب القيم الفريدة للفلاتر
    departments = Department.query.filter_by(org_id=org_id, is_active=True).all()
    resources = User.query.filter_by(org_id=org_id, is_user_active=True).all()
    
    # جلب الحالات الفريدة من المشاريع
    statuses = db.session.query(Project.status).filter_by(org_id=org_id).distinct().all()
    statuses = [s[0] for s in statuses if s[0]]
    
    # جلب الأولويات الفريدة
    priorities = db.session.query(Project.priority_level).filter_by(org_id=org_id).distinct().all()
    priorities = [p[0] for p in priorities if p[0]]
    
    # جلب نطاق الميزانية
    budget_stats = db.session.query(
        func.min(ProjectBudget.current_budget).label('min'),
        func.max(ProjectBudget.current_budget).label('max')
    ).join(Project).filter(Project.org_id == org_id).first()
    
    return jsonify({
        'success': True,
        'options': {
            'departments': [{'id': d.id, 'name': d.name} for d in departments],
            'resources': [{'id': r.id, 'name': r.full_name} for r in resources],
            'statuses': statuses,
            'priorities': priorities,
            'budget_range': {
                'min': float(budget_stats.min) if budget_stats.min else 0,
                'max': float(budget_stats.max) if budget_stats.max else 10000000
            }
        }
    })


@dashboard_bp.route('/api/export-data')
@login_required
def api_export_data():
    """API لتصدير البيانات المصفاة"""
    filters = {
        'project': request.args.get('project', 'all'),
        'department': request.args.get('department', 'all'),
        'status': request.args.getlist('status'),
        'priority': request.args.getlist('priority')
    }
    
    org_id = current_user.org_id
    projects = Project.query.filter_by(org_id=org_id).all()
    filtered_projects = apply_project_filters_from_dict(projects, filters)
    
    # تجهيز بيانات التصدير
    export_data = []
    for project in filtered_projects:
        export_data.append({
            'project_name': project.name,
            'status': project.status,
            'progress': project.get_progress(),
            'budget': project.budget.current_budget if project.budget else 0,
            'actual_cost': project.cost.total_actual_cost if project.cost else 0,
            'created_at': project.created_at.strftime('%Y-%m-%d') if project.created_at else None
        })
    
    return jsonify({
        'success': True,
        'data': export_data,
        'count': len(export_data)
    })

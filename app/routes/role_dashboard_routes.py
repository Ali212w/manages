"""
role_dashboard_routes.py
لوحات معلومات مخصصة حسب دور المستخدم (مثل Power BI)
Roles: org_admin, project_manager, supervisor, delegate, employee
"""

from flask import render_template, jsonify, Blueprint
from flask_login import login_required, current_user
from app.models import db, Project, Task, User, Department, Notification, TaskAssignment, Organization
from sqlalchemy import func, and_
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

role_dashboard_bp = Blueprint('role_dashboard', __name__, url_prefix='/my-dashboard')


# ─────────────────────────────────────────────
# Helper: جلب إحصاءات المهام للمستخدم الحالي
# ─────────────────────────────────────────────
def _user_task_stats(user_id, org_id, project_ids=None):
    q = Task.query.join(Project, Task.project_id == Project.id).filter(Project.org_id == org_id)
    if project_ids is not None:
        q = q.filter(Task.project_id.in_(project_ids))

    # المهام المسندة لهذا المستخدم
    assigned_ids = [a.task_id for a in TaskAssignment.query.filter_by(user_id=user_id).all()]
    if assigned_ids:
        q_mine = q.filter(Task.id.in_(assigned_ids))
    else:
        q_mine = q.filter(False)  # لا شيء

    total      = q_mine.count()
    completed  = q_mine.filter(Task.status == 'completed').count()
    in_prog    = q_mine.filter(Task.status == 'in_progress').count()
    pending    = q_mine.filter(Task.status == 'pending').count()

    today = datetime.utcnow().date()
    overdue = sum(
        1 for t in q_mine.all()
        if t.end_date and t.end_date.date() < today and t.status != 'completed'
    ) if total else 0

    return {
        'total': total,
        'completed': completed,
        'in_progress': in_prog,
        'pending': pending,
        'overdue': overdue,
        'completion_rate': round(completed / total * 100, 1) if total else 0,
    }


def _recent_notifications(user_id, limit=8):
    notifs = Notification.query.filter_by(user_id=user_id)\
        .order_by(Notification.created_at.desc()).limit(limit).all()
    return notifs


# ─────────────────────────────────────────────
# الصفحة الرئيسية: توجيه حسب الدور
# ─────────────────────────────────────────────
@role_dashboard_bp.route('/')
@login_required
def my_dashboard():
    # منع مدير المنصة من الدخول — لا يملك org_id
    from app.models import PlatformAdmin
    if isinstance(current_user, PlatformAdmin) or not hasattr(current_user, 'org_id'):
        from flask import redirect, url_for
        return redirect(url_for('platform.dashboard'))

    role = getattr(current_user, 'role', 'employee')
    dispatch = {
        'org_admin':       dashboard_org_admin,
        'project_manager': dashboard_project_manager,
        'supervisor':      dashboard_supervisor,
        'delegate':        dashboard_delegate,
        'employee':        dashboard_employee,
    }
    handler = dispatch.get(role, dashboard_employee)
    return handler()


# ══════════════════════════════════════════════
# 1. مدير المؤسسة (org_admin) — الإطلاع الكامل
# ══════════════════════════════════════════════
def dashboard_org_admin():
    org_id = current_user.org_id
    today  = datetime.utcnow().date()

    projects = Project.query.filter_by(org_id=org_id).all()
    users    = User.query.filter_by(org_id=org_id, is_user_active=True).all()
    depts    = Department.query.filter_by(org_id=org_id, is_active=True).all()

    # إحصاءات المشاريع
    total_p     = len(projects)
    active_p    = sum(1 for p in projects if p.status == 'active')
    completed_p = sum(1 for p in projects if p.status == 'completed')
    # is_overdue: fallback if property not defined
    overdue_p   = sum(
        1 for p in projects
        if getattr(p, 'is_overdue', False)
        or (p.end_date and p.end_date.date() < today and p.status not in ('completed','cancelled'))
    )

    # إحصاءات المهام (كل المنظمة)
    all_tasks      = Task.query.join(Project).filter(Project.org_id == org_id).all()
    total_t        = len(all_tasks)
    completed_t    = sum(1 for t in all_tasks if t.status == 'completed')
    in_progress_t  = sum(1 for t in all_tasks if t.status == 'in_progress')
    overdue_t      = sum(1 for t in all_tasks
                         if t.end_date and t.end_date.date() < today and t.status != 'completed')

    # ميزانية
    total_budget = sum((p.budget.current_budget if p.budget else 0) for p in projects)
    total_cost   = sum((p.cost.total_actual_cost if p.cost else 0) for p in projects)
    variance     = total_budget - total_cost

    # توزيع المستخدمين حسب الدور
    role_dist = {}
    for u in users:
        role_dist[u.role] = role_dist.get(u.role, 0) + 1

    # آخر 5 مشاريع
    recent_projects = sorted(projects, key=lambda p: p.created_at or datetime.min, reverse=True)[:5]

    # الإشعارات
    unread_notifs = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    recent_notifs = _recent_notifications(current_user.id)

    kpis = {
        'total_projects': total_p,
        'active_projects': active_p,
        'completed_projects': completed_p,
        'overdue_projects': overdue_p,
        'total_users': len(users),
        'total_departments': len(depts),
        'total_tasks': total_t,
        'completed_tasks': completed_t,
        'in_progress_tasks': in_progress_t,
        'overdue_tasks': overdue_t,
        'task_completion_rate': round(completed_t / total_t * 100, 1) if total_t else 0,
        'total_budget': total_budget,
        'total_cost': total_cost,
        'budget_variance': variance,
        'budget_utilization': round(total_cost / total_budget * 100, 1) if total_budget else 0,
        'role_distribution': role_dist,
    }

    return render_template(
        'dashboard/role/org_admin.html',
        kpis=kpis,
        recent_projects=recent_projects,
        unread_notifs=unread_notifs,
        recent_notifs=recent_notifs,
        now=datetime.now(),
    )


# ══════════════════════════════════════════════
# 2. مدير المشاريع (project_manager)
# ══════════════════════════════════════════════
def dashboard_project_manager():
    org_id    = current_user.org_id
    user_id   = current_user.id
    today     = datetime.utcnow().date()

    # المشاريع التي يديرها هذا المستخدم
    my_projects = Project.query.filter_by(org_id=org_id, project_manager_id=user_id).all()
    proj_ids    = [p.id for p in my_projects]

    total_p     = len(my_projects)
    active_p    = sum(1 for p in my_projects if p.status == 'active')
    overdue_p   = sum(
        1 for p in my_projects
        if getattr(p, 'is_overdue', False)
        or (p.end_date and p.end_date.date() < today and p.status not in ('completed','cancelled'))
    )
    avg_progress = round(sum(p.get_progress() for p in my_projects) / total_p, 1) if total_p else 0

    # المهام في مشاريعه
    all_tasks     = Task.query.filter(Task.project_id.in_(proj_ids)).all() if proj_ids else []
    total_t       = len(all_tasks)
    completed_t   = sum(1 for t in all_tasks if t.status == 'completed')
    in_progress_t = sum(1 for t in all_tasks if t.status == 'in_progress')
    overdue_t     = sum(1 for t in all_tasks
                        if t.end_date and t.end_date.date() < today and t.status != 'completed')

    # فريق العمل
    team_ids  = set()
    for t in all_tasks:
        for a in TaskAssignment.query.filter_by(task_id=t.id).all():
            team_ids.add(a.user_id)
    team_size = len(team_ids)

    # الميزانية
    total_budget = sum((p.budget.current_budget if p.budget else 0) for p in my_projects)
    total_cost   = sum((p.cost.total_actual_cost if p.cost else 0) for p in my_projects)

    unread_notifs = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    recent_notifs = _recent_notifications(user_id)

    kpis = {
        'total_projects': total_p,
        'active_projects': active_p,
        'overdue_projects': overdue_p,
        'avg_progress': avg_progress,
        'total_tasks': total_t,
        'completed_tasks': completed_t,
        'in_progress_tasks': in_progress_t,
        'overdue_tasks': overdue_t,
        'task_completion_rate': round(completed_t / total_t * 100, 1) if total_t else 0,
        'team_size': team_size,
        'total_budget': total_budget,
        'total_cost': total_cost,
        'budget_utilization': round(total_cost / total_budget * 100, 1) if total_budget else 0,
    }

    return render_template(
        'dashboard/role/project_manager.html',
        kpis=kpis,
        my_projects=my_projects,
        unread_notifs=unread_notifs,
        recent_notifs=recent_notifs,
        now=datetime.now(),
    )


# ══════════════════════════════════════════════
# 3. المشرف (supervisor)
# ══════════════════════════════════════════════
def dashboard_supervisor():
    org_id  = current_user.org_id
    user_id = current_user.id
    today   = datetime.utcnow().date()

    # المهام التي يشرف عليها
    supervised_tasks = Task.query.join(Project).filter(
        Project.org_id == org_id,
        Task.supervisor_id == user_id
    ).all()

    total_t       = len(supervised_tasks)
    completed_t   = sum(1 for t in supervised_tasks if t.status == 'completed')
    in_progress_t = sum(1 for t in supervised_tasks if t.status == 'in_progress')
    overdue_t     = sum(1 for t in supervised_tasks
                        if t.end_date and t.end_date.date() < today and t.status != 'completed')

    # المشاريع المرتبطة
    proj_ids    = list({t.project_id for t in supervised_tasks})
    my_projects = Project.query.filter(Project.id.in_(proj_ids)).all() if proj_ids else []

    # الموظفون تحت إشراف هذا المشرف
    employee_ids = set()
    for t in supervised_tasks:
        for a in TaskAssignment.query.filter_by(task_id=t.id).all():
            employee_ids.add(a.user_id)

    unread_notifs = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    recent_notifs = _recent_notifications(user_id)

    # مهامي الشخصية
    my_tasks = _user_task_stats(user_id, org_id)

    kpis = {
        'supervised_tasks': total_t,
        'completed_tasks': completed_t,
        'in_progress_tasks': in_progress_t,
        'overdue_tasks': overdue_t,
        'task_completion_rate': round(completed_t / total_t * 100, 1) if total_t else 0,
        'projects_count': len(my_projects),
        'employees_count': len(employee_ids),
        'my_tasks': my_tasks,
    }

    return render_template(
        'dashboard/role/supervisor.html',
        kpis=kpis,
        supervised_tasks=supervised_tasks[:10],
        my_projects=my_projects,
        unread_notifs=unread_notifs,
        recent_notifs=recent_notifs,
        now=datetime.now(),
    )


# ══════════════════════════════════════════════
# 4. المفوض / المندوب (delegate)
# ══════════════════════════════════════════════
def dashboard_delegate():
    org_id  = current_user.org_id
    user_id = current_user.id

    my_tasks  = _user_task_stats(user_id, org_id)
    today     = datetime.utcnow().date()

    assigned_task_ids = [a.task_id for a in TaskAssignment.query.filter_by(user_id=user_id).all()]
    tasks = Task.query.filter(Task.id.in_(assigned_task_ids)).all() if assigned_task_ids else []

    proj_ids    = list({t.project_id for t in tasks})
    my_projects = Project.query.filter(Project.id.in_(proj_ids)).all() if proj_ids else []

    unread_notifs = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    recent_notifs = _recent_notifications(user_id)

    kpis = {
        'my_tasks': my_tasks,
        'projects_count': len(my_projects),
    }

    return render_template(
        'dashboard/role/delegate.html',
        kpis=kpis,
        tasks=tasks[:10],
        my_projects=my_projects,
        unread_notifs=unread_notifs,
        recent_notifs=recent_notifs,
        now=datetime.now(),
    )


# ══════════════════════════════════════════════
# 5. الموظف (employee)
# ══════════════════════════════════════════════
def dashboard_employee():
    org_id  = current_user.org_id
    user_id = current_user.id
    today   = datetime.utcnow().date()

    my_tasks_stats = _user_task_stats(user_id, org_id)

    assigned_ids = [a.task_id for a in TaskAssignment.query.filter_by(user_id=user_id).all()]
    tasks = Task.query.filter(Task.id.in_(assigned_ids)).order_by(Task.end_date).all() \
        if assigned_ids else []

    # المشاريع التي يشارك فيها
    proj_ids    = list({t.project_id for t in tasks})
    my_projects = Project.query.filter(Project.id.in_(proj_ids)).all() if proj_ids else []

    unread_notifs = Notification.query.filter_by(user_id=user_id, is_read=False).count()
    recent_notifs = _recent_notifications(user_id)

    kpis = {
        'my_tasks': my_tasks_stats,
        'projects_count': len(my_projects),
    }

    return render_template(
        'dashboard/role/employee.html',
        kpis=kpis,
        tasks=tasks[:10],
        my_projects=my_projects,
        unread_notifs=unread_notifs,
        recent_notifs=recent_notifs,
        now=datetime.now(),
    )


# ══════════════════════════════════════════════
# API: بيانات الرسوم البيانية (AJAX)
# ══════════════════════════════════════════════
@role_dashboard_bp.route('/api/chart-data')
@login_required
def api_chart_data():
    """إرجاع بيانات الرسوم البيانية حسب الدور"""
    try:
        org_id  = current_user.org_id
        user_id = current_user.id
        role    = current_user.role

        # توزيع حالات المهام
        if role == 'org_admin':
            tasks = Task.query.join(Project).filter(Project.org_id == org_id).all()
        elif role == 'project_manager':
            proj_ids = [p.id for p in Project.query.filter_by(org_id=org_id, project_manager_id=user_id).all()]
            tasks = Task.query.filter(Task.project_id.in_(proj_ids)).all() if proj_ids else []
        elif role == 'supervisor':
            tasks = Task.query.join(Project).filter(
                Project.org_id == org_id, Task.supervisor_id == user_id).all()
        else:
            assigned_ids = [a.task_id for a in TaskAssignment.query.filter_by(user_id=user_id).all()]
            tasks = Task.query.filter(Task.id.in_(assigned_ids)).all() if assigned_ids else []

        status_dist = {
            'completed': sum(1 for t in tasks if t.status == 'completed'),
            'in_progress': sum(1 for t in tasks if t.status == 'in_progress'),
            'pending': sum(1 for t in tasks if t.status == 'pending'),
        }

        # تقدم المشاريع (آخر 6 أشهر)
        today = datetime.utcnow().date()
        monthly = []
        for i in range(5, -1, -1):
            m = today.replace(day=1) - timedelta(days=i * 30)
            monthly.append({'month': m.strftime('%b'), 'value': 0})  # placeholder

        return jsonify({'success': True, 'status_dist': status_dist, 'monthly': monthly})

    except Exception as e:
        logger.error(f"role_dashboard chart_data error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

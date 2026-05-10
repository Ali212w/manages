"""
client_routes.py - مسارات المالك (العميل) لمتابعة المشاريع
"""
from flask import render_template, request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import login_required, current_user
from app.models import db, User, Organization, Project, Notification, Activity
from app.models import Task, TaskAssignment, ProjectProgress, ProjectDates, ProjectBudget, ProjectCost
from app.models import ProjectPerformance, Milestone, Issue, ChangeRequest, Meeting, Risk,DailyReport,ProjectProgressLog,ActivityExpense
from app.models import Resource, ActivityResource, ResourceRequest, ResourceDelivery
from app.routes import client_bp
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import func, and_, or_
from app.services.update_service import UpdateService

# ============================================
# دوال مساعدة للتحقق من الصلاحيات
# ============================================

def client_required(f):
    """ديكوراتور للتحقق من أن المستخدم هو مالك المشروع"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        # التحقق من أن المستخدم لديه دور client أو org_admin
        if current_user.role not in ['client', 'org_admin']:
            flash('غير مصرح بالوصول - هذه الصفحة للمالكين فقط', 'danger')
            return redirect(url_for('employee.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def check_project_ownership(project_id):
    """التحقق من أن المستخدم هو مالك المشروع"""
    project = Project.query.get_or_404(project_id)
    if project.client_id != current_user.id and current_user.role != 'client':
        flash('غير مصرح بالوصول إلى هذا المشروع', 'danger')
        return None
    return project

def get_client_projects():
    """الحصول على جميع مشاريع العميل"""
    if current_user.role == 'client':
        return Project.query.filter_by(org_id=current_user.org_id).all()
    return Project.query.filter_by(client_id=current_user.id).all()

# ============================================
# قبل كل طلب - تحميل البيانات الأساسية
# ============================================

@client_bp.before_request
@login_required
def load_client_data():
    """تحميل بيانات العميل قبل كل طلب"""
    if current_user.is_authenticated and current_user.role in ['client', 'org_admin']:
        g.user = current_user
        g.company = Organization.query.get(current_user.org_id)
        
        # المشاريع الخاصة بالعميل
        if current_user.role == 'client':
            g.client_projects = Project.query.filter_by(org_id=current_user.org_id).all()
        else:
            g.client_projects = Project.query.filter_by(client_id=current_user.id).all()
        
        # عدد الإشعارات غير المقروءة
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        
        # عدد المشاريع النشطة
        g.active_projects_count = len([p for p in g.client_projects if p.status == 'active'])
        
        # عدد المشاريع المتأخرة
        g.delayed_projects_count = len([p for p in g.client_projects if p.is_overdue])
        
        # إجمالي الميزانية لجميع المشاريع
        g.total_budget = sum(p.budget.current_budget if p.budget else 0 for p in g.client_projects)
        
        # إجمالي التكلفة الفعلية
        g.total_actual_cost = sum(p.cost.total_actual_cost if p.cost else 0 for p in g.client_projects)
        
        # عدد طلبات التغيير المعلقة
        g.pending_change_requests = 0
        for project in g.client_projects:
            g.pending_change_requests += ChangeRequest.query.filter_by(
                project_id=project.id, 
                status='submitted'
            ).count()
        
        # عدد المخاطر الحرجة
        g.critical_risks_count = 0
        for project in g.client_projects:
            g.critical_risks_count += Risk.query.filter_by(
                project_id=project.id, 
                risk_level='critical'
            ).count()
        
    else:
        g.company = None
        g.client_projects = []
        g.notifications_count = 0
        g.active_projects_count = 0
        g.delayed_projects_count = 0
        g.total_budget = 0
        g.total_actual_cost = 0
        g.pending_change_requests = 0
        g.critical_risks_count = 0

# ============================================
# لوحة التحكم الرئيسية للمالك
# ============================================

@client_bp.route('/')
@login_required
@client_required
def dashboard():
    """لوحة تحكم المالك الرئيسية"""
    
    projects = get_client_projects()
    
    # إحصائيات عامة
    stats = {
        'total_projects': len(projects),
        'active_projects': len([p for p in projects if p.status == 'active']),
        'completed_projects': len([p for p in projects if p.status == 'completed']),
        'planning_projects': len([p for p in projects if p.status == 'planning']),
        'delayed_projects': len([p for p in projects if p.is_overdue]),
        'total_budget': sum(p.budget.current_budget if p.budget else 0 for p in projects),
        'total_actual_cost': sum(p.cost.total_actual_cost if p.cost else 0 for p in projects),
        'total_variance': sum((p.budget.current_budget if p.budget else 0) - (p.cost.total_actual_cost if p.cost else 0) for p in projects),
        'avg_progress': sum(p.get_progress() for p in projects) / len(projects) if projects else 0
    }
    
    # توزيع الميزانية
    budget_distribution = [{
        'name': p.name,
        'budget': p.budget.current_budget if p.budget else 0,
        'actual': p.cost.total_actual_cost if p.cost else 0,
        'color': f"hsl({hash(p.name) % 360}, 70%, 50%)"
    } for p in projects[:10]]
    
    # تقدم المشاريع للرسم البياني
    projects_progress = [{
        'id': p.id,
        'name': p.name,
        'progress': p.get_progress(),
        'status': p.status,
        'color': 'success' if p.get_progress() >= 75 else 'warning' if p.get_progress() >= 40 else 'info'
    } for p in projects]
    
    # المشاريع النشطة (أحدث 5)
    active_projects_list = [p for p in projects if p.status == 'active'][:5]
    
    # طلبات التغيير المعلقة
    pending_changes = []
    for project in projects:
        changes = ChangeRequest.query.filter_by(
            project_id=project.id, 
            status='submitted'
        ).order_by(ChangeRequest.requested_date.desc()).limit(5).all()
        pending_changes.extend(changes)
    pending_changes = pending_changes[:5]
    
    # المخاطر الحرجة
    critical_risks = []
    for project in projects:
        risks = Risk.query.filter_by(
            project_id=project.id, 
            risk_level='critical'
        ).filter(Risk.status != 'closed').all()
        critical_risks.extend(risks)
    critical_risks = critical_risks[:5]
    
    # المعالم القادمة
    upcoming_milestones = []
    for project in projects:
        milestones = Milestone.query.filter_by(
            project_id=project.id,
            status='pending'
        ).filter(Milestone.planned_date >= date.today()).order_by(
            Milestone.planned_date
        ).limit(3).all()
        upcoming_milestones.extend(milestones)
    upcoming_milestones = sorted(upcoming_milestones, key=lambda x: x.planned_date)[:5]
    
    # آخر الإشعارات
    recent_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(10).all()
    
    # أداء المشاريع (SPI/CPI)
    project_performance = []
    for project in projects:
        if project.performance:
            project_performance.append({
                'id': project.id,
                'name': project.name,
                'spi': project.performance.spi or 1,
                'cpi': project.performance.cpi or 1,
                'status': 'good' if (project.performance.spi or 1) >= 0.9 and (project.performance.cpi or 1) >= 0.9 else 'warning' if (project.performance.spi or 1) >= 0.8 else 'critical'
            })
    
    return render_template('client/dashboard.html',
                         stats=stats,
                         budget_distribution=budget_distribution,
                         projects_progress=projects_progress,
                         active_projects=active_projects_list,
                         pending_changes=pending_changes,
                         critical_risks=critical_risks,
                         upcoming_milestones=upcoming_milestones,
                         recent_notifications=recent_notifications,
                         project_performance=project_performance,
                         now=datetime.now())

# ============================================
# عرض قائمة المشاريع
# ============================================

@client_bp.route('/projects')
@login_required
@client_required
def projects_list():
    """عرض جميع مشاريع المالك"""
    
    projects = get_client_projects()
    
    # معاملات التصفية والبحث
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('search', '')
    sort_by = request.args.get('sort', 'created_at')
    
    # تطبيق التصفية
    filtered_projects = projects
    if status_filter != 'all':
        filtered_projects = [p for p in projects if p.status == status_filter]
    
    if search_query:
        filtered_projects = [p for p in projects if search_query.lower() in p.name.lower()]
    
    # تطبيق الترتيب
    if sort_by == 'name':
        filtered_projects.sort(key=lambda x: x.name)
    elif sort_by == 'progress':
        filtered_projects.sort(key=lambda x: x.get_progress(), reverse=True)
    elif sort_by == 'budget':
        filtered_projects.sort(key=lambda x: x.budget.current_budget if x.budget else 0, reverse=True)
    elif sort_by == 'created_at':
        filtered_projects.sort(key=lambda x: x.created_at, reverse=True)
    
    # إحصائيات المشاريع
    stats = {
        'total': len(projects),
        'active': len([p for p in projects if p.status == 'active']),
        'completed': len([p for p in projects if p.status == 'completed']),
        'planning': len([p for p in projects if p.status == 'planning']),
        'delayed': len([p for p in projects if p.is_overdue])
    }
    
    return render_template('client/projects/index.html',
                         projects=filtered_projects,
                         stats=stats,
                         status_filter=status_filter,
                         search_query=search_query,
                         sort_by=sort_by,
                         now=datetime.now())

# ============================================
# تفاصيل المشروع
# ============================================

@client_bp.route('/projects/<int:project_id>')
@login_required
@client_required
def project_detail(project_id):
    """عرض تفاصيل المشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    # ========== البيانات الأساسية ==========
    
    # التواريخ
    dates = project.dates if project.dates else None
    
    # الميزانية والتكاليف
    budget = project.budget if project.budget else None
    cost = project.cost if project.cost else None
    performance = project.performance if project.performance else None
    progress = project.progress if project.progress else None
    
    # ========== إحصائيات المشروع ==========
    
    # إحصائيات الأنشطة
    activities = Activity.query.filter_by(project_id=project_id).all()
    activities_stats = {
        'total': len(activities),
        'completed': len([a for a in activities if a.status == 'completed']),
        'in_progress': len([a for a in activities if a.status == 'in_progress']),
        'not_started': len([a for a in activities if a.status == 'not_started']),
        'critical': len([a for a in activities if a.is_critical]),
        'delayed': len([a for a in activities if a.status != 'completed' and a.planned_finish and a.planned_finish.date() < date.today()])
    }
    activities_stats['completion_rate'] = (activities_stats['completed'] / activities_stats['total'] * 100) if activities_stats['total'] > 0 else 0
    
    # إحصائيات المهام
    tasks = Task.query.filter_by(project_id=project_id).all()
    tasks_stats = {
        'total': len(tasks),
        'completed': len([t for t in tasks if t.status == 'completed']),
        'in_progress': len([t for t in tasks if t.status == 'in_progress']),
        'pending': len([t for t in tasks if t.status == 'pending']),
        'delayed': len([t for t in tasks if t.is_delayed])
    }
    tasks_stats['completion_rate'] = (tasks_stats['completed'] / tasks_stats['total'] * 100) if tasks_stats['total'] > 0 else 0
    
    # إحصائيات الموارد
    resources = ActivityResource.query.join(Activity).filter(Activity.project_id == project_id).all()
    resources_stats = {
        'total': len(set(r.resource_id for r in resources)),
        'total_planned_cost': sum(r.planned_cost or 0 for r in resources),
        'total_actual_cost': sum(r.actual_cost or 0 for r in resources),
        'utilization': (sum(r.actual_cost or 0 for r in resources) / sum(r.planned_cost or 0 for r in resources) * 100) if sum(r.planned_cost or 0 for r in resources) > 0 else 0
    }
    
    # إحصائيات المخاطر
    risks = Risk.query.filter_by(project_id=project_id).all()
    risks_stats = {
        'total': len(risks),
        'critical': len([r for r in risks if r.risk_level == 'critical']),
        'high': len([r for r in risks if r.risk_level == 'high']),
        'medium': len([r for r in risks if r.risk_level == 'medium']),
        'low': len([r for r in risks if r.risk_level == 'low']),
        'closed': len([r for r in risks if r.status == 'closed'])
    }
    
    # المعالم
    milestones = Milestone.query.filter_by(project_id=project_id).order_by(Milestone.planned_date).all()
    milestones_stats = {
        'total': len(milestones),
        'achieved': len([m for m in milestones if m.status == 'achieved']),
        'pending': len([m for m in milestones if m.status == 'pending']),
        'delayed': len([m for m in milestones if m.status == 'pending' and m.planned_date < date.today()])
    }
    
    # طلبات التغيير
    change_requests = ChangeRequest.query.filter_by(project_id=project_id).order_by(ChangeRequest.requested_date.desc()).all()
    changes_stats = {
        'total': len(change_requests),
        'submitted': len([c for c in change_requests if c.status == 'submitted']),
        'approved': len([c for c in change_requests if c.status == 'approved']),
        'rejected': len([c for c in change_requests if c.status == 'rejected']),
        'implemented': len([c for c in change_requests if c.status == 'implemented'])
    }
    
    # القضايا
    issues = Issue.query.filter_by(project_id=project_id).order_by(Issue.reported_date.desc()).all()
    issues_stats = {
        'total': len(issues),
        'open': len([i for i in issues if i.status == 'open']),
        'in_progress': len([i for i in issues if i.status == 'in_progress']),
        'resolved': len([i for i in issues if i.status == 'resolved']),
        'closed': len([i for i in issues if i.status == 'closed'])
    }
    
    # الاجتماعات
    meetings = Meeting.query.filter_by(project_id=project_id).order_by(Meeting.scheduled_date.desc()).all()
    meetings_stats = {
        'total': len(meetings),
        'scheduled': len([m for m in meetings if m.status == 'scheduled']),
        'completed': len([m for m in meetings if m.status == 'completed']),
        'upcoming': len([m for m in meetings if m.status == 'scheduled' and m.scheduled_date > datetime.now()])
    }
    
    # ========== بيانات الجدول الزمني ==========
    
    # تقدم المشروع (آخر 30 يوماً)
    progress_logs = ProjectProgressLog.query.filter_by(project_id=project_id).order_by(ProjectProgressLog.record_date).all()
    progress_history = [{
        'date': log.record_date.strftime('%Y-%m-%d'),
        'progress': log.progress_percentage
    } for log in progress_logs[-30:]]
    
    # ========== بيانات القيمة المكتسبة ==========
    
    earned_value = None
    if performance:
        earned_value = {
            'planned_value': performance.planned_value or 0,
            'earned_value': performance.earned_value or 0,
            'actual_cost': performance.actual_cost or 0,
            'spi': performance.spi or 1,
            'cpi': performance.cpi or 1,
            'csi': performance.csi or 1,
            'eac': performance.eac or 0,
            'etc': performance.etc or 0,
            'vac': performance.vac or 0
        }
    
    # ========== بيانات المستخدمين ==========
    
    # أعضاء فريق المشروع
    
    # جلب المستخدمين من خلال تعيينات المهام
    project_users = User.query.join(
        TaskAssignment, TaskAssignment.user_id == User.id
    ).join(
        Task, Task.id == TaskAssignment.task_id
    ).filter(
        Task.project_id == project_id
    ).distinct().all()
    
    # إذا لم يتم العثور على مستخدمين، جرب طريقة بديلة
    if not project_users:
        # جلب المستخدمين من خلال المهام مباشرة (المشرفين والمناديب)
        project_users = User.query.filter(
            (User.id == Task.supervisor_id) | (User.id == Task.delegate_id)
        ).join(Task).filter(Task.project_id == project_id).distinct().all()
    
    # المالك والمشرفون
    client = project.client if hasattr(project, 'client') else None
    project_manager = project.manager if hasattr(project, 'manager') else None
    consultant =  project.consultant if hasattr(project, 'consultant') else None
    supplier =  project.supplier if hasattr(project, 'supplier') else None
    
    # ========== بيانات التقارير ==========
    
    # تقارير يومية
    daily_reports = DailyReport.query.filter_by(project_id=project_id).order_by(DailyReport.report_date.desc()).limit(10).all()
    
    return render_template('client/projects/detail.html',
                         project=project,
                         dates=dates,
                         budget=budget,
                         cost=cost,
                         performance=performance,
                         progress=progress,
                         activities_stats=activities_stats,
                         tasks_stats=tasks_stats,
                         resources_stats=resources_stats,
                         risks_stats=risks_stats,
                         milestones=milestones,
                         milestones_stats=milestones_stats,
                         change_requests=change_requests[:10],
                         changes_stats=changes_stats,
                         issues=issues[:10],
                         issues_stats=issues_stats,
                         meetings=meetings[:10],
                         meetings_stats=meetings_stats,
                         progress_history=progress_history,
                         earned_value=earned_value,
                         project_users=project_users,
                         client=client,
                         project_manager=project_manager,
                         consultant=consultant,
                         supplier=supplier,
                         daily_reports=daily_reports,
                         now=datetime.now())

# ============================================
# التقارير المالية
# ============================================

@client_bp.route('/projects/<int:project_id>/financial-report')
@login_required
@client_required
def financial_report(project_id):
    """التقرير المالي للمشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    # بيانات الميزانية
    budget = project.budget if project.budget else None
    cost = project.cost if project.cost else None
    performance = project.performance if project.performance else None
    
    # مصروفات الأنشطة
    expenses = ActivityExpense.query.join(Activity).filter(Activity.project_id == project_id).all()
    
    expenses_by_category = {}
    for exp in expenses:
        category = exp.category or 'أخرى'
        if category not in expenses_by_category:
            expenses_by_category[category] = 0
        expenses_by_category[category] += exp.amount
    
    # تكاليف الموارد
    resources_cost = db.session.query(
        Resource.resource_type,
        func.sum(ActivityResource.planned_cost).label('planned'),
        func.sum(ActivityResource.actual_cost).label('actual')
    ).join(ActivityResource).join(Activity).filter(
        Activity.project_id == project_id
    ).group_by(Resource.resource_type).all()
    
    resources_cost_data = [{
        'type': r.resource_type,
        'planned': r.planned or 0,
        'actual': r.actual or 0
    } for r in resources_cost]
    
    # طلبات التغيير وتأثيرها المالي
    change_requests = ChangeRequest.query.filter_by(project_id=project_id).all()
    change_impact = {
        'total_estimated': sum(c.estimated_cost or 0 for c in change_requests),
        'total_actual': sum(c.actual_cost or 0 for c in change_requests),
        'approved': sum(c.estimated_cost or 0 for c in change_requests if c.status == 'approved'),
        'rejected': sum(c.estimated_cost or 0 for c in change_requests if c.status == 'rejected')
    }
    
    # الفروقات المالية
    planned_vs_actual = {
        'planned': cost.total_planned_cost if cost else 0,
        'actual': cost.total_actual_cost if cost else 0,
        'variance': (cost.total_planned_cost if cost else 0) - (cost.total_actual_cost if cost else 0),
        'variance_percentage': ((cost.total_planned_cost - cost.total_actual_cost) / cost.total_planned_cost * 100) if cost and cost.total_planned_cost > 0 else 0
    }
    
    return render_template('client/projects/financial_report.html',
                         project=project,
                         budget=budget,
                         cost=cost,
                         performance=performance,
                         expenses_by_category=expenses_by_category,
                         resources_cost=resources_cost_data,
                         change_impact=change_impact,
                         planned_vs_actual=planned_vs_actual,
                         now=datetime.now())

# ============================================
# تقرير التقدم الزمني
# ============================================

@client_bp.route('/projects/<int:project_id>/progress-report')
@login_required
@client_required
def progress_report(project_id):
    """تقرير التقدم الزمني للمشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    # سجل التقدم
    progress_logs = ProjectProgressLog.query.filter_by(project_id=project_id).order_by(ProjectProgressLog.record_date).all()
    
    # إحصائيات التقدم
    current_progress = project.get_progress()
    target_progress = 100
    days_remaining = project.remaining_days
    
    # تحليل الأنشطة المتأخرة
    delayed_activities = Activity.query.filter(
        Activity.project_id == project_id,
        Activity.status != 'completed',
        Activity.planned_finish < datetime.now()
    ).order_by(Activity.planned_finish).all()
    
    # تحليل المهام المتأخرة
    delayed_tasks = Task.query.filter(
        Task.project_id == project_id,
        Task.status != 'completed',
        Task.planning.has(Task.planning.planned_finish < date.today())
    ).all()
    
    # المعالم المتأخرة
    delayed_milestones = Milestone.query.filter(
        Milestone.project_id == project_id,
        Milestone.status == 'pending',
        Milestone.planned_date < date.today()
    ).all()
    
    # بيانات المسار الحرج
    critical_activities = Activity.query.filter_by(
        project_id=project_id,
        is_critical=True
    ).all()
    
    return render_template('client/projects/progress_report.html',
                         project=project,
                         progress_logs=progress_logs,
                         current_progress=current_progress,
                         target_progress=target_progress,
                         days_remaining=days_remaining,
                         delayed_activities=delayed_activities,
                         delayed_tasks=delayed_tasks,
                         delayed_milestones=delayed_milestones,
                         critical_activities=critical_activities,
                         now=datetime.now())

# ============================================
# طلبات التغيير
# ============================================

@client_bp.route('/projects/<int:project_id>/change-requests')
@login_required
@client_required
def change_requests(project_id):
    """عرض طلبات التغيير للمشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    change_requests = ChangeRequest.query.filter_by(project_id=project_id).order_by(
        ChangeRequest.requested_date.desc()
    ).all()
    
    # إحصائيات طلبات التغيير
    stats = {
        'total': len(change_requests),
        'submitted': len([c for c in change_requests if c.status == 'submitted']),
        'under_review': len([c for c in change_requests if c.status == 'under_review']),
        'approved': len([c for c in change_requests if c.status == 'approved']),
        'rejected': len([c for c in change_requests if c.status == 'rejected']),
        'implemented': len([c for c in change_requests if c.status == 'implemented']),
        'total_estimated_cost': sum(c.estimated_cost or 0 for c in change_requests),
        'total_actual_cost': sum(c.actual_cost or 0 for c in change_requests)
    }
    
    return render_template('client/projects/change_requests.html',
                         project=project,
                         change_requests=change_requests,
                         stats=stats,
                         now=datetime.now())

@client_bp.route('/projects/<int:project_id>/change-requests/<int:cr_id>/review', methods=['POST'])
@login_required
@client_required
def review_change_request(project_id, cr_id):
    """مراجعة طلب تغيير (موافقة/رفض)"""
    
    project = check_project_ownership(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    change_request = ChangeRequest.query.get_or_404(cr_id)
    
    if change_request.project_id != project_id:
        return jsonify({'success': False, 'error': 'طلب التغيير لا ينتمي لهذا المشروع'}), 400
    
    data = request.get_json()
    decision = data.get('decision')
    notes = data.get('notes', '')
    
    if decision not in ['approve', 'reject', 'defer']:
        return jsonify({'success': False, 'error': 'قرار غير صالح'}), 400
    
    try:
        change_request.status = 'approved' if decision == 'approve' else 'rejected' if decision == 'reject' else 'under_review'
        change_request.decision = decision
        change_request.decision_date = datetime.utcnow()
        change_request.decision_notes = notes
        
        # إذا تمت الموافقة، تحديث الميزانية
        if decision == 'approve' and change_request.estimated_cost:
            if project.budget:
                project.budget.current_budget = (project.budget.current_budget or 0) + change_request.estimated_cost
                project.budget.proposed_budget = (project.budget.proposed_budget or 0) + change_request.estimated_cost
        
        db.session.commit()
        
        # إشعار لمدير المشروع
        if project.project_manager_id:
            notification = Notification(
                user_id=project.project_manager_id,
                title=f'قرار طلب تغيير - {project.name}',
                message=f'تم {decision} طلب التغيير #{change_request.cr_number}',
                notification_type='change_request_decision',
                related_project_id=project_id,
                send_email=True
            )
            db.session.add(notification)
            db.session.commit()
        
        # ✅ تحديث المؤشرات
        UpdateService.update_project_metrics(project)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# المخاطر
# ============================================

@client_bp.route('/projects/<int:project_id>/risks')
@login_required
@client_required
def project_risks(project_id):
    """عرض مخاطر المشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    risks = Risk.query.filter_by(project_id=project_id).order_by(
        Risk.severity.desc()
    ).all()
    
    # إحصائيات المخاطر
    stats = {
        'total': len(risks),
        'critical': len([r for r in risks if r.risk_level == 'critical']),
        'high': len([r for r in risks if r.risk_level == 'high']),
        'medium': len([r for r in risks if r.risk_level == 'medium']),
        'low': len([r for r in risks if r.risk_level == 'low']),
        'identified': len([r for r in risks if r.status == 'identified']),
        'mitigated': len([r for r in risks if r.status == 'mitigated']),
        'closed': len([r for r in risks if r.status == 'closed']),
        'avg_severity': sum(r.severity for r in risks) / len(risks) if risks else 0
    }
    
    return render_template('client/projects/risks.html',
                         project=project,
                         risks=risks,
                         stats=stats,
                         now=datetime.now())

# ============================================
# المعالم
# ============================================

@client_bp.route('/projects/<int:project_id>/milestones')
@login_required
@client_required
def project_milestones(project_id):
    """عرض معالم المشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    milestones = Milestone.query.filter_by(project_id=project_id).order_by(
        Milestone.planned_date
    ).all()
    
    # إحصائيات المعالم
    stats = {
        'total': len(milestones),
        'achieved': len([m for m in milestones if m.status == 'achieved']),
        'pending': len([m for m in milestones if m.status == 'pending']),
        'delayed': len([m for m in milestones if m.status == 'pending' and m.planned_date < date.today()]),
        'upcoming': len([m for m in milestones if m.status == 'pending' and m.planned_date >= date.today()])
    }
    
    return render_template('client/projects/milestones.html',
                         project=project,
                         milestones=milestones,
                         stats=stats,
                         now=datetime.now())

# ============================================
# التقارير اليومية
# ============================================

@client_bp.route('/projects/<int:project_id>/daily-reports')
@login_required
@client_required
def daily_reports(project_id):
    """عرض التقارير اليومية للمشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    reports = DailyReport.query.filter_by(project_id=project_id).order_by(
        DailyReport.report_date.desc()
    ).all()
    
    # إحصائيات التقارير
    stats = {
        'total': len(reports),
        'approved': len([r for r in reports if r.review_status == 'approved']),
        'pending': len([r for r in reports if r.review_status == 'pending']),
        'rejected': len([r for r in reports if r.review_status == 'rejected'])
    }
    
    return render_template('client/projects/daily_reports.html',
                         project=project,
                         reports=reports,
                         stats=stats,
                         now=datetime.now())

@client_bp.route('/projects/<int:project_id>/daily-reports/<int:report_id>')
@login_required
@client_required
def view_daily_report(project_id, report_id):
    """عرض تقرير يومي محدد"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    report = DailyReport.query.get_or_404(report_id)
    
    if report.project_id != project_id:
        flash('التقرير لا ينتمي لهذا المشروع', 'danger')
        return redirect(url_for('client.daily_reports', project_id=project_id))
    
    return render_template('client/projects/view_daily_report.html',
                         project=project,
                         report=report,
                         now=datetime.now())

# ============================================
# الاجتماعات
# ============================================

@client_bp.route('/projects/<int:project_id>/meetings')
@login_required
@client_required
def project_meetings(project_id):
    """عرض اجتماعات المشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    meetings = Meeting.query.filter_by(project_id=project_id).order_by(
        Meeting.scheduled_date.desc()
    ).all()
    
    # إحصائيات الاجتماعات
    stats = {
        'total': len(meetings),
        'scheduled': len([m for m in meetings if m.status == 'scheduled']),
        'completed': len([m for m in meetings if m.status == 'completed']),
        'cancelled': len([m for m in meetings if m.status == 'cancelled']),
        'upcoming': len([m for m in meetings if m.status == 'scheduled' and m.scheduled_date > datetime.now()])
    }
    
    return render_template('client/projects/meetings.html',
                         project=project,
                         meetings=meetings,
                         stats=stats,
                         now=datetime.now())

@client_bp.route('/projects/<int:project_id>/meetings/<int:meeting_id>')
@login_required
@client_required
def view_meeting(project_id, meeting_id):
    """عرض تفاصيل اجتماع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    meeting = Meeting.query.get_or_404(meeting_id)
    
    if meeting.project_id != project_id:
        flash('الاجتماع لا ينتمي لهذا المشروع', 'danger')
        return redirect(url_for('client.project_meetings', project_id=project_id))
    
    return render_template('client/projects/view_meeting.html',
                         project=project,
                         meeting=meeting,
                         now=datetime.now())

# ============================================
# الفريق
# ============================================

@client_bp.route('/projects/<int:project_id>/team')
@login_required
@client_required
def project_team(project_id):
    """عرض فريق المشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return redirect(url_for('client.projects_list'))
    
    # أعضاء الفريق (المستخدمين المرتبطين بالمشروع)
    team_members = User.query.join(Task).filter(Task.project_id == project_id).distinct().all()
    
    # إضافة أدوار كل عضو
    team_data = []
    for member in team_members:
        # عدد المهام المكتملة
        completed_tasks = TaskAssignment.query.filter_by(
            user_id=member.id,
            status='completed'
        ).join(Task).filter(Task.project_id == project_id).count()
        
        # عدد المهام قيد التنفيذ
        in_progress_tasks = TaskAssignment.query.filter_by(
            user_id=member.id,
            status='in_progress'
        ).join(Task).filter(Task.project_id == project_id).count()
        
        team_data.append({
            'user': member,
            'completed_tasks': completed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'total_tasks': completed_tasks + in_progress_tasks
        })
    
    # الترتيب حسب عدد المهام
    team_data.sort(key=lambda x: x['total_tasks'], reverse=True)
    
    return render_template('client/projects/team.html',
                         project=project,
                         team_data=team_data,
                         now=datetime.now())

# ============================================
# تقارير الأداء العامة
# ============================================

@client_bp.route('/performance-overview')
@login_required
@client_required
def performance_overview():
    """نظرة عامة على أداء جميع المشاريع"""
    
    projects = get_client_projects()
    
    # إحصائيات الأداء
    performance_data = []
    for project in projects:
        if project.performance:
            performance_data.append({
                'id': project.id,
                'name': project.name,
                'spi': project.performance.spi or 1,
                'cpi': project.performance.cpi or 1,
                'csi': project.performance.csi or 1,
                'eac': project.performance.eac or 0,
                'vac': project.performance.vac or 0,
                'progress': project.get_progress(),
                'status': project.status
            })
    
    # المشاريع المتأخرة
    delayed_projects = [p for p in projects if p.is_overdue]
    
    # المشاريع التي تتجاوز الميزانية
    over_budget_projects = []
    for project in projects:
        if project.performance and project.performance.cpi and project.performance.cpi < 0.9:
            over_budget_projects.append({
                'id': project.id,
                'name': project.name,
                'cpi': project.performance.cpi,
                'variance': (project.performance.planned_value or 0) - (project.performance.actual_cost or 0)
            })
    
    return render_template('client/performance_overview.html',
                         projects=projects,
                         performance_data=performance_data,
                         delayed_projects=delayed_projects,
                         over_budget_projects=over_budget_projects,
                         now=datetime.now())

# ============================================
# الإشعارات
# ============================================

@client_bp.route('/notifications')
@login_required
def notifications():
    """عرض جميع الإشعارات"""
    
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('client/notifications/index.html', notifications=notifications)

@client_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """تحديد إشعار كمقروء"""
    
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    notification.mark_as_read()
    db.session.commit()
    
    return jsonify({'success': True})

@client_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """تحديد جميع الإشعارات كمقروءة"""
    
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True, 'read_at': datetime.utcnow()})
    
    db.session.commit()
    
    return jsonify({'success': True})

# ============================================
# API Routes
# ============================================

@client_bp.route('/api/projects/<int:project_id>/stats')
@login_required
@client_required
def api_project_stats(project_id):
    """API لإحصائيات المشروع"""
    
    project = check_project_ownership(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    stats = {
        'activities': {
            'total': Activity.query.filter_by(project_id=project_id).count(),
            'completed': Activity.query.filter_by(project_id=project_id, status='completed').count(),
            'in_progress': Activity.query.filter_by(project_id=project_id, status='in_progress').count()
        },
        'tasks': {
            'total': Task.query.filter_by(project_id=project_id).count(),
            'completed': Task.query.filter_by(project_id=project_id, status='completed').count(),
            'in_progress': Task.query.filter_by(project_id=project_id, status='in_progress').count()
        },
        'risks': {
            'total': Risk.query.filter_by(project_id=project_id).count(),
            'critical': Risk.query.filter_by(project_id=project_id, risk_level='critical').count()
        },
        'budget': {
            'planned': project.budget.current_budget if project.budget else 0,
            'actual': project.cost.total_actual_cost if project.cost else 0,
            'variance': (project.budget.current_budget if project.budget else 0) - (project.cost.total_actual_cost if project.cost else 0)
        },
        'progress': project.get_progress(),
        'days_remaining': project.remaining_days
    }
    
    return jsonify({'success': True, 'stats': stats})

@client_bp.route('/api/projects/overall-stats')
@login_required
@client_required
def api_overall_stats():
    """API للإحصائيات العامة لجميع المشاريع"""
    
    projects = get_client_projects()
    
    stats = {
        'total_projects': len(projects),
        'active_projects': len([p for p in projects if p.status == 'active']),
        'completed_projects': len([p for p in projects if p.status == 'completed']),
        'delayed_projects': len([p for p in projects if p.is_overdue]),
        'total_budget': sum(p.budget.current_budget if p.budget else 0 for p in projects),
        'total_actual': sum(p.cost.total_actual_cost if p.cost else 0 for p in projects),
        'avg_progress': sum(p.get_progress() for p in projects) / len(projects) if projects else 0,
        'total_risks': sum(Risk.query.filter_by(project_id=p.id, risk_level='critical').count() for p in projects),
        'pending_changes': sum(ChangeRequest.query.filter_by(project_id=p.id, status='submitted').count() for p in projects)
    }
    
    return jsonify({'success': True, 'stats': stats})

# ============================================
# API Routes إضافية
# ============================================

@client_bp.route('/api/change-request/<int:cr_id>')
@login_required
@client_required
def api_get_change_request(cr_id):
    """API لجلب تفاصيل طلب تغيير"""
    change_request = ChangeRequest.query.get_or_404(cr_id)
    
    project = check_project_ownership(change_request.project_id)
    if not project:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'change_request': {
            'id': change_request.id,
            'cr_number': change_request.cr_number,
            'title': change_request.title,
            'description': change_request.description,
            'change_type': change_request.change_type,
            'estimated_cost': change_request.estimated_cost,
            'actual_cost': change_request.actual_cost,
            'impact_scope': change_request.impact_scope,
            'impact_schedule': change_request.impact_schedule,
            'impact_cost': change_request.impact_cost,
            'status': change_request.status,
            'requested_date': change_request.requested_date.strftime('%Y-%m-%d'),
            'decision_date': change_request.decision_date.strftime('%Y-%m-%d') if change_request.decision_date else None,
            'decision_notes': change_request.decision_notes,
            'requested_by': change_request.requester.full_name if change_request.requester else None
        }
    })


@client_bp.route('/api/risk/<int:risk_id>')
@login_required
@client_required
def api_get_risk_detail(risk_id):
    """API لجلب تفاصيل خطر"""
    risk = Risk.query.get_or_404(risk_id)
    
    project = check_project_ownership(risk.project_id)
    if not project:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'risk': {
            'id': risk.id,
            'risk_code': risk.risk_code,
            'title': risk.title,
            'description': risk.description,
            'risk_level': risk.risk_level,
            'probability': risk.probability * 100,
            'impact': risk.impact * 100,
            'severity': risk.severity * 100,
            'mitigation_plan': risk.mitigation_plan,
            'contingency_plan': risk.contingency_plan,
            'status': risk.status,
            'identified_date': risk.identified_date.strftime('%Y-%m-%d') if risk.identified_date else None,
            'target_mitigation_date': risk.target_mitigation_date.strftime('%Y-%m-%d') if risk.target_mitigation_date else None,
            'actual_mitigation_date': risk.actual_mitigation_date.strftime('%Y-%m-%d') if risk.actual_mitigation_date else None,
            'owner': risk.owner.full_name if risk.owner else None
        }
    })


@client_bp.route('/api/projects/<int:project_id>/gantt-data')
@login_required
@client_required
def api_project_gantt_data(project_id):
    """API لجلب بيانات مخطط جانت للمشروع"""
    project = check_project_ownership(project_id)
    if not project:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    activities = Activity.query.filter_by(project_id=project_id).all()
    
    gantt_data = []
    for activity in activities:
        gantt_data.append({
            'id': activity.activity_id,
            'name': activity.activity_name,
            'start': activity.planned_start.strftime('%Y-%m-%d') if activity.planned_start else None,
            'end': activity.planned_finish.strftime('%Y-%m-%d') if activity.planned_finish else None,
            'progress': activity.progress_percentage / 100,
            'status': activity.status,
            'is_critical': activity.is_critical
        })
    
    return jsonify({'success': True, 'tasks': gantt_data})

# ============================================
# الملف الشخصي للمالك (Client Profile)
# ============================================

@client_bp.route('/profile')
@login_required
@client_required
def profile():
    """عرض الملف الشخصي للمالك"""
    
    user = current_user
    
    # إحصائيات المستخدم
    from app.models.project_models import Project
    from app.models.task_models import Task, TaskAssignment
    from app.models import Notification
    
    # المشاريع المرتبطة بالمالك
    projects = Project.query.filter_by(client_id=user.id).all()
    
    # إحصائيات المشاريع
    stats = {
        'total_projects': len(projects),
        'active_projects': len([p for p in projects if p.status == 'active']),
        'completed_projects': len([p for p in projects if p.status == 'completed']),
        'delayed_projects': len([p for p in projects if p.is_overdue]),
        'total_budget': sum(p.budget.current_budget if p.budget else 0 for p in projects),
        'total_actual_cost': sum(p.cost.total_actual_cost if p.cost else 0 for p in projects),
        'avg_progress': sum(p.get_progress() for p in projects) / len(projects) if projects else 0
    }
    
    # الإشعارات غير المقروءة
    unread_notifications = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).count()
    
    # نشاط المستخدم (آخر 30 يوماً)
    from datetime import datetime, timedelta
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    
    # عدد مرات تسجيل الدخول
    login_count = user.login_count or 0
    
    # تاريخ آخر تسجيل دخول
    last_login = user.last_login
    
    # المهارات (إذا كان هناك جدول UserSkill)
    from app.models.ai_models import UserSkill
    skills = UserSkill.query.filter_by(user_id=user.id).all()
    
    # سجل النشاطات (Audit Log)
    from app.models.ai_models import AuditLog
    recent_activities = AuditLog.query.filter_by(user_id=user.id).order_by(
        AuditLog.timestamp.desc()
    ).limit(10).all()
    
    return render_template('client/profile/index.html',
                         user=user,
                         stats=stats,
                         unread_notifications=unread_notifications,
                         login_count=login_count,
                         last_login=last_login,
                         skills=skills,
                         recent_activities=recent_activities,
                         now=datetime.now())


@client_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
@client_required
def edit_profile():
    """تعديل الملف الشخصي"""
    
    user = current_user
    
    if request.method == 'POST':
        try:
            # تحديث البيانات الأساسية
            user.full_name = request.form.get('full_name', user.full_name)
            user.full_name_ar = request.form.get('full_name_ar', user.full_name_ar)
            user.phone = request.form.get('phone', user.phone)
            user.mobile = request.form.get('mobile', user.mobile)
            user.job_title = request.form.get('job_title', user.job_title)
            user.job_title_ar = request.form.get('job_title_ar', user.job_title_ar)
            user.bio = request.form.get('bio', getattr(user, 'bio', ''))
            
            # تحديث العنوان
            user.address = request.form.get('address', getattr(user, 'address', ''))
            user.city = request.form.get('city', getattr(user, 'city', ''))
            user.country = request.form.get('country', getattr(user, 'country', 'السعودية'))
            
            # تحديث إعدادات اللغة والإشعارات
            if hasattr(user, 'settings'):
                settings = user.settings or {}
                settings['language'] = request.form.get('language', 'ar')
                settings['notifications_email'] = 'notification_email' in request.form
                settings['notifications_push'] = 'notification_push' in request.form
                settings['date_format'] = request.form.get('date_format', 'dd/MM/yyyy')
                user.settings = settings
            else:
                user.settings = {
                    'language': request.form.get('language', 'ar'),
                    'notifications_email': 'notification_email' in request.form,
                    'notifications_push': 'notification_push' in request.form,
                    'date_format': request.form.get('date_format', 'dd/MM/yyyy')
                }
            
            db.session.commit()
            flash('تم تحديث الملف الشخصي بنجاح', 'success')
            return redirect(url_for('client.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('client/profile/edit.html', user=user)


@client_bp.route('/profile/change-password', methods=['POST'])
@login_required
@client_required
def change_password():
    """تغيير كلمة المرور"""
    
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    # التحقق من كلمة المرور الحالية
    if not current_user.check_password(current_password):
        return jsonify({'success': False, 'error': 'كلمة المرور الحالية غير صحيحة'}), 400
    
    # التحقق من تطابق كلمة المرور الجديدة
    if new_password != confirm_password:
        return jsonify({'success': False, 'error': 'كلمة المرور الجديدة غير متطابقة'}), 400
    
    # التحقق من قوة كلمة المرور
    if len(new_password) < 8:
        return jsonify({'success': False, 'error': 'كلمة المرور يجب أن تكون 8 أحرف على الأقل'}), 400
    
    # تحديث كلمة المرور
    current_user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم تغيير كلمة المرور بنجاح'})


@client_bp.route('/profile/upload-avatar', methods=['POST'])
@login_required
@client_required
def upload_avatar():
    """رفع صورة الملف الشخصي"""
    
    if 'avatar' not in request.files:
        return jsonify({'success': False, 'error': 'لم يتم اختيار ملف'}), 400
    
    file = request.files['avatar']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'لم يتم اختيار ملف'}), 400
    
    # التحقق من نوع الملف
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
    
    if ext not in allowed_extensions:
        return jsonify({'success': False, 'error': 'نوع الملف غير مدعوم'}), 400
    
    # التحقق من حجم الملف (max 5MB)
    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > 5 * 1024 * 1024:
        return jsonify({'success': False, 'error': 'حجم الملف يجب أن يكون أقل من 5 ميجابايت'}), 400
    
    # حفظ الملف
    from werkzeug.utils import secure_filename
    import uuid
    import os
    from flask import current_app
    
    filename = secure_filename(file.filename)
    unique_filename = f"avatar_{current_user.id}_{uuid.uuid4().hex}_{filename}"
    
    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'avatars')
    os.makedirs(upload_folder, exist_ok=True)
    
    file_path = os.path.join(upload_folder, unique_filename)
    file.save(file_path)
    
    # تحديث مسار الصورة
    current_user.profile_image = unique_filename
    db.session.commit()
    
    return jsonify({
        'success': True,
        'avatar_url': url_for('static', filename=f'uploads/avatars/{unique_filename}')
    })


@client_bp.route('/api/profile/stats')
@login_required
@client_required
def api_profile_stats():
    """API لإحصائيات الملف الشخصي"""
    
    user = current_user
    
    # حساب إحصائيات إضافية
    from app.models.project_models import Project
    from app.models import Notification
    from datetime import datetime, timedelta
    
    projects = Project.query.filter_by(client_id=user.id).all()
    
    # المشاريع المنتهية في آخر 30 يوم
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_projects = [p for p in projects if p.created_at and p.created_at >= thirty_days_ago]
    
    # متوسط التقدم
    avg_progress = sum(p.get_progress() for p in projects) / len(projects) if projects else 0
    
    # عدد الإشعارات في آخر 7 أيام
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_notifications = Notification.query.filter(
        Notification.user_id == user.id,
        Notification.created_at >= seven_days_ago
    ).count()
    
    return jsonify({
        'success': True,
        'stats': {
            'total_projects': len(projects),
            'recent_projects': len(recent_projects),
            'avg_progress': round(avg_progress, 1),
            'recent_notifications': recent_notifications,
            'member_since': user.created_at.strftime('%Y-%m-%d') if user.created_at else None,
            'last_active': user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else None
        }
    })


@client_bp.route('/api/profile/activity')
@login_required
@client_required
def api_profile_activity():
    """API لنشاط المستخدم (للرسم البياني)"""
    
    user = current_user
    from datetime import datetime, timedelta
    from app.models.ai_models import AuditLog
    
    # آخر 30 يوم
    activity_data = []
    for i in range(30, 0, -1):
        date = datetime.utcnow().date() - timedelta(days=i)
        next_date = date + timedelta(days=1)
        
        # عدد الأنشطة في هذا اليوم
        count = AuditLog.query.filter(
            AuditLog.user_id == user.id,
            AuditLog.timestamp >= datetime.combine(date, datetime.min.time()),
            AuditLog.timestamp < datetime.combine(next_date, datetime.min.time())
        ).count()
        
        activity_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': count
        })
    
    return jsonify({
        'success': True,
        'activity': activity_data
    })
# أضف هذه الـ API في نهاية client_routes.py

@client_bp.route('/api/skills/add', methods=['POST'])
@login_required
@client_required
def api_add_skill():
    """API لإضافة مهارة"""
    from app.models.ai_models import UserSkill
    
    data = request.get_json()
    
    skill = UserSkill(
        user_id=current_user.id,
        skill_name=data.get('skill_name'),
        proficiency_level=int(data.get('proficiency_level', 3)),
        experience_years=float(data.get('experience_years', 0))
    )
    
    db.session.add(skill)
    db.session.commit()
    
    return jsonify({'success': True})


@client_bp.route('/api/skills/<int:skill_id>/delete', methods=['POST'])
@login_required
@client_required
def api_delete_skill(skill_id):
    """API لحذف مهارة"""
    from app.models.ai_models import UserSkill
    
    skill = UserSkill.query.get_or_404(skill_id)
    
    if skill.user_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    db.session.delete(skill)
    db.session.commit()
    
    return jsonify({'success': True})
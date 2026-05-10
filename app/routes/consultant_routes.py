"""
consultant_routes.py - مسارات المهندس الاستشاري
"""

from flask import render_template, request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import login_required, current_user
from app.models import db, User, Organization, Project, Notification, Activity
from app.models import Task, TaskAssignment, TaskPlanning, TaskExecution, TaskProgress
from app.models import TaskVerification, TaskRequirement, TaskRequirementVerification
from app.models import ProjectDates, ProjectProgress, Milestone, Issue, Meeting
from app.models import QualityCheck, SafetyInspection
from app.routes import consultant_bp
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import or_, and_
from app.services.update_service import UpdateService

# ============================================
# دوال مساعدة للتحقق من الصلاحيات
# ============================================

def consultant_required(f):
    """ديكوراتور للتحقق من أن المستخدم هو مهندس استشاري"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('يرجى تسجيل الدخول أولاً', 'warning')
            return redirect(url_for('auth.login'))
        
        # التحقق من أن المستخدم لديه دور consultant
        if current_user.role not in ['consultant', 'org_admin']:
            flash('غير مصرح بالوصول - هذه الصفحة للمهندسين الاستشاريين فقط', 'danger')
            return redirect(url_for('employee.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

def check_consultant_project_access(project_id):
    """التحقق من أن المشروع مرتبط بالمهندس الاستشاري"""
    project = Project.query.get_or_404(project_id)
    if project.consultant_id != current_user.id and current_user.role != 'org_admin':
        flash('غير مصرح بالوصول إلى هذا المشروع', 'danger')
        return None
    return project

def get_consultant_projects():
    """الحصول على جميع مشاريع المهندس الاستشاري"""
    if current_user.role == 'org_admin':
        return Project.query.filter_by(org_id=current_user.org_id).all()
    return Project.query.filter_by(consultant_id=current_user.id).all()


# ============================================
# قبل كل طلب - تحميل البيانات الأساسية
# ============================================

@consultant_bp.before_request
@login_required
def load_consultant_data():
    """تحميل بيانات المهندس الاستشاري قبل كل طلب"""
    if current_user.is_authenticated and current_user.role in ['consultant', 'org_admin']:
        g.user = current_user
        g.company = Organization.query.get(current_user.org_id)
        
        # المشاريع المرتبطة بالمهندس الاستشاري
        if current_user.role == 'org_admin':
            g.consultant_projects = Project.query.filter_by(org_id=current_user.org_id).all()
        else:
            g.consultant_projects = Project.query.filter_by(consultant_id=current_user.id).all()
        
        # عدد الإشعارات غير المقروءة
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        
        # عدد المشاريع النشطة
        g.active_projects_count = len([p for p in g.consultant_projects if p.status == 'active'])
        
        # عدد المهام المعلقة للمراجعة
        g.pending_reviews_count = TaskVerification.query.filter_by(
            verified_by=current_user.id,
            verification_required=True
        ).filter(TaskVerification.verified_at.is_(None)).count()
        
        # عدد طلبات التحقق المعلقة
        g.pending_verifications_count = TaskRequirementVerification.query.filter_by(
            status='pending'
        ).join(TaskRequirement).join(Task).filter(
            Task.project_id.in_([p.id for p in g.consultant_projects])
        ).count()
        
    else:
        g.company = None
        g.consultant_projects = []
        g.notifications_count = 0
        g.active_projects_count = 0
        g.pending_reviews_count = 0
        g.pending_verifications_count = 0


# ============================================
# لوحة التحكم الرئيسية للمهندس الاستشاري
# ============================================

@consultant_bp.route('/')
@login_required
@consultant_required
def dashboard():
    """لوحة تحكم المهندس الاستشاري الرئيسية"""
    
    projects = get_consultant_projects()
    
    # إحصائيات عامة (بدون تفاصيل مالية)
    stats = {
        'total_projects': len(projects),
        'active_projects': len([p for p in projects if p.status == 'active']),
        'completed_projects': len([p for p in projects if p.status == 'completed']),
        'planning_projects': len([p for p in projects if p.status == 'planning']),
        'total_tasks': sum(Task.query.filter_by(project_id=p.id).count() for p in projects),
        'completed_tasks': sum(Task.query.filter_by(project_id=p.id, status='completed').count() for p in projects),
        'pending_reviews': g.pending_reviews_count,
        'pending_verifications': g.pending_verifications_count
    }
    
    # حساب متوسط التقدم (بدون تفاصيل مالية)
    total_progress = 0
    for p in projects:
        if p.progress:
            total_progress += p.progress.progress_percentage or 0
        elif hasattr(p, 'get_progress'):
            total_progress += p.get_progress()
    stats['avg_progress'] = total_progress / len(projects) if projects else 0
    
    # المشاريع النشطة (أحدث 5)
    active_projects_list = [p for p in projects if p.status == 'active'][:5]
    
    # المهام التي تحتاج مراجعة
    pending_reviews = TaskVerification.query.filter_by(
        verification_required=True,
        verified_at=None
    ).join(Task).filter(
        Task.project_id.in_([p.id for p in projects])
    ).order_by(TaskVerification.id.desc()).limit(10).all()
    
    # طلبات التحقق المعلقة
    pending_verifications = TaskRequirementVerification.query.filter_by(
        status='pending'
    ).join(TaskRequirement).join(Task).filter(
        Task.project_id.in_([p.id for p in projects])
    ).order_by(TaskRequirementVerification.submitted_at.desc()).limit(10).all()
    
    # القضايا المفتوحة
    open_issues = Issue.query.filter(
        Issue.project_id.in_([p.id for p in projects]),
        Issue.status.in_(['open', 'in_progress'])
    ).order_by(Issue.priority.desc()).limit(10).all()
    
    # الاجتماعات القادمة
    upcoming_meetings = Meeting.query.filter(
        Meeting.project_id.in_([p.id for p in projects]),
        Meeting.scheduled_date >= datetime.now(),
        Meeting.status == 'scheduled'
    ).order_by(Meeting.scheduled_date).limit(5).all()
    
    # المعالم القادمة
    upcoming_milestones = Milestone.query.filter(
        Milestone.project_id.in_([p.id for p in projects]),
        Milestone.status == 'pending',
        Milestone.planned_date >= date.today()
    ).order_by(Milestone.planned_date).limit(5).all()
    
    # آخر الإشعارات
    recent_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(10).all()
    
    return render_template('consultant/dashboard.html',
                         stats=stats,
                         projects_progress=[{
                             'id': p.id,
                             'name': p.name,
                             'progress': p.progress.progress_percentage if p.progress else (p.get_progress() if hasattr(p, 'get_progress') else 0),
                             'status': p.status
                         } for p in projects[:10]],
                         active_projects=active_projects_list,
                         pending_reviews=pending_reviews,
                         pending_verifications=pending_verifications,
                         open_issues=open_issues,
                         upcoming_meetings=upcoming_meetings,
                         upcoming_milestones=upcoming_milestones,
                         recent_notifications=recent_notifications,
                         now=datetime.now())


# ============================================
# عرض قائمة المشاريع
# ============================================

@consultant_bp.route('/projects')
@login_required
@consultant_required
def projects_list():
    """عرض جميع مشاريع المهندس الاستشاري"""
    
    projects = get_consultant_projects()
    
    # معاملات التصفية والبحث
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('search', '')
    
    # تطبيق التصفية
    filtered_projects = projects
    if status_filter != 'all':
        filtered_projects = [p for p in projects if p.status == status_filter]
    
    if search_query:
        filtered_projects = [p for p in projects if search_query.lower() in p.name.lower()]
    
    # إحصائيات المشاريع
    stats = {
        'total': len(projects),
        'active': len([p for p in projects if p.status == 'active']),
        'completed': len([p for p in projects if p.status == 'completed']),
        'planning': len([p for p in projects if p.status == 'planning'])
    }
    
    return render_template('consultant/projects/index.html',
                         projects=filtered_projects,
                         stats=stats,
                         status_filter=status_filter,
                         search_query=search_query,
                         now=datetime.now())


# ============================================
# تفاصيل المشروع (بدون معلومات مالية)
# ============================================

@consultant_bp.route('/projects/<int:project_id>')
@login_required
@consultant_required
def project_detail(project_id):
    """عرض تفاصيل المشروع (بدون معلومات مالية)"""
    
    project = check_consultant_project_access(project_id)
    if not project:
        return redirect(url_for('consultant.projects_list'))
    
    # ========== البيانات الأساسية (بدون مالية) ==========
    
    # التواريخ
    dates = project.dates if project.dates else None
    
    # التقدم فقط (بدون تكاليف)
    progress = project.progress if project.progress else None
    
    # ========== إحصائيات المشروع (بدون مالية) ==========
    
    # إحصائيات الأنشطة
    activities = Activity.query.filter_by(project_id=project_id).all()
    activities_stats = {
        'total': len(activities),
        'completed': len([a for a in activities if a.status == 'completed']),
        'in_progress': len([a for a in activities if a.status == 'in_progress']),
        'not_started': len([a for a in activities if a.status == 'not_started']),
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
    
    # المعالم
    milestones = Milestone.query.filter_by(project_id=project_id).order_by(Milestone.planned_date).all()
    milestones_stats = {
        'total': len(milestones),
        'achieved': len([m for m in milestones if m.status == 'achieved']),
        'pending': len([m for m in milestones if m.status == 'pending']),
        'delayed': len([m for m in milestones if m.status == 'pending' and m.planned_date < date.today()])
    }
    
    # القضايا
    issues = Issue.query.filter_by(project_id=project_id).order_by(Issue.priority.desc(), Issue.reported_date.desc()).all()
    issues_stats = {
        'total': len(issues),
        'open': len([i for i in issues if i.status == 'open']),
        'in_progress': len([i for i in issues if i.status == 'in_progress']),
        'resolved': len([i for i in issues if i.status == 'resolved'])
    }
    
    # الاجتماعات
    meetings = Meeting.query.filter_by(project_id=project_id).order_by(Meeting.scheduled_date.desc()).all()
    meetings_stats = {
        'total': len(meetings),
        'scheduled': len([m for m in meetings if m.status == 'scheduled']),
        'completed': len([m for m in meetings if m.status == 'completed']),
        'upcoming': len([m for m in meetings if m.status == 'scheduled' and m.scheduled_date > datetime.now()])
    }
    
    # فحوصات الجودة
    quality_checks = QualityCheck.query.filter_by(project_id=project_id).order_by(QualityCheck.planned_date.desc()).limit(10).all()
    
    # فحوصات السلامة
    safety_inspections = SafetyInspection.query.filter_by(project_id=project_id).order_by(SafetyInspection.inspection_date.desc()).limit(10).all()
    
    # ========== بيانات التقدم الزمني ==========
    
    # تقدم المشروع (آخر 30 يوماً)
    from app.models.project_models import ProjectProgressLog
    progress_logs = ProjectProgressLog.query.filter_by(project_id=project_id).order_by(ProjectProgressLog.record_date).all()
    progress_history = [{
        'date': log.record_date.strftime('%Y-%m-%d'),
        'progress': log.progress_percentage
    } for log in progress_logs[-30:]]
    
    # ========== أعضاء فريق المشروع ==========
    from app.models.task_models import TaskAssignment
    
    project_users = []
    try:
        assigned_users = User.query.join(
            TaskAssignment, TaskAssignment.user_id == User.id
        ).join(Task, Task.id == TaskAssignment.task_id).filter(
            Task.project_id == project_id
        ).distinct().all()
        
        task_users = User.query.filter(
            or_(Task.supervisor_id == User.id, Task.delegate_id == User.id)
        ).join(Task).filter(Task.project_id == project_id).distinct().all()
        
        all_users = {}
        for user in assigned_users + task_users:
            all_users[user.id] = user
        project_users = list(all_users.values())
    except Exception as e:
        project_users = []
    
    return render_template('consultant/projects/detail.html',
                         project=project,
                         dates=dates,
                         progress=progress,
                         activities_stats=activities_stats,
                         tasks_stats=tasks_stats,
                         milestones=milestones,
                         milestones_stats=milestones_stats,
                         issues=issues,
                         issues_stats=issues_stats,
                         meetings=meetings,
                         meetings_stats=meetings_stats,
                         quality_checks=quality_checks,
                         safety_inspections=safety_inspections,
                         progress_history=progress_history,
                         project_users=project_users,
                         now=datetime.now())


# ============================================
# المهام التي تحتاج مراجعة
# ============================================

@consultant_bp.route('/pending-reviews')
@login_required
@consultant_required
def pending_reviews():
    """عرض المهام التي تحتاج مراجعة"""
    
    projects = get_consultant_projects()
    
    pending_reviews = TaskVerification.query.filter_by(
        verification_required=True,
        verified_at=None
    ).join(Task).filter(
        Task.project_id.in_([p.id for p in projects])
    ).order_by(TaskVerification.id.desc()).all()
    
    # إحصائيات
    stats = {
        'total': len(pending_reviews),
        'urgent': len([r for r in pending_reviews if r.task and r.task.is_delayed]),
        'today': len([r for r in pending_reviews if r.created_at and r.created_at.date() == date.today()])
    }
    
    return render_template('consultant/pending_reviews.html',
                         pending_reviews=pending_reviews,
                         stats=stats,
                         now=datetime.now())


@consultant_bp.route('/reviews/<int:review_id>/approve', methods=['POST'])
@login_required
@consultant_required
def approve_review(review_id):
    """الموافقة على مراجعة مهمة"""
    
    review = TaskVerification.query.get_or_404(review_id)
    
    # التحقق من الصلاحية
    project = Project.query.get(review.task.project_id)
    if project.consultant_id != current_user.id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    approved = data.get('approved', True)
    notes = data.get('notes', '')
    
    try:
        if approved:
            review.verified_at = datetime.utcnow()
            review.verified_by = current_user.id
            review.notes = notes
            review.verification_required = False
            
            # تحديث حالة المهمة إذا لزم الأمر
            if review.task:
                review.task.completion_status = 'approved'
        else:
            review.notes = notes
            review.task.completion_status = 'rejected'
            review.task.rejection_reason = notes
        
        db.session.commit()
        
        # إشعار للمستخدم
        if review.task and review.task.delegate_id:
            notification = Notification(
                user_id=review.task.delegate_id,
                title=f'نتيجة مراجعة المهمة - {review.task.task_name}',
                message=f'تم {"الموافقة على" if approved else "رفض"} مراجعة المهمة',
                notification_type='review_result',
                related_task_id=review.task.id,
                related_project_id=project.id
            )
            db.session.add(notification)
            db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# طلبات التحقق
# ============================================

@consultant_bp.route('/verifications')
@login_required
@consultant_required
def verifications():
    """عرض طلبات التحقق المعلقة"""
    
    projects = get_consultant_projects()
    
    verifications = TaskRequirementVerification.query.filter_by(
        status='pending'
    ).join(TaskRequirement).join(Task).filter(
        Task.project_id.in_([p.id for p in projects])
    ).order_by(TaskRequirementVerification.submitted_at.desc()).all()
    
    # إحصائيات
    stats = {
        'total': len(verifications),
        'urgent': len([v for v in verifications if v.task and v.task.is_delayed]),
        'today': len([v for v in verifications if v.submitted_at and v.submitted_at.date() == date.today()])
    }
    
    return render_template('consultant/verifications.html',
                         verifications=verifications,
                         stats=stats,
                         now=datetime.now())


@consultant_bp.route('/verifications/<int:verification_id>/review', methods=['POST'])
@login_required
@consultant_required
def review_verification(verification_id):
    """مراجعة طلب التحقق"""
    
    verification = TaskRequirementVerification.query.get_or_404(verification_id)
    
    # التحقق من الصلاحية
    project = Project.query.get(verification.task.project_id)
    if project.consultant_id != current_user.id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    approved = data.get('approved', True)
    notes = data.get('notes', '')
    
    try:
        if approved:
            verification.status = 'verified'
            verification.verified_at = datetime.utcnow()
            verification.verified_by = current_user.id
            verification.notes = notes
        else:
            verification.status = 'rejected'
            verification.verified_at = datetime.utcnow()
            verification.verified_by = current_user.id
            verification.notes = notes
        
        db.session.commit()
        
        # إشعار للمستخدم
        if verification.user_id:
            notification = Notification(
                user_id=verification.user_id,
                title=f'نتيجة طلب التحقق',
                message=f'تم {"الموافقة على" if approved else "رفض"} طلب التحقق الخاص بك',
                notification_type='verification_result',
                related_task_id=verification.task_id,
                related_project_id=project.id
            )
            db.session.add(notification)
            db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# القضايا والمشكلات
# ============================================

@consultant_bp.route('/issues')
@login_required
@consultant_required
def issues_list():
    """عرض جميع القضايا"""
    
    projects = get_consultant_projects()
    
    issues = Issue.query.filter(
        Issue.project_id.in_([p.id for p in projects])
    ).order_by(Issue.priority.desc(), Issue.reported_date.desc()).all()
    
    # إحصائيات
    stats = {
        'total': len(issues),
        'open': len([i for i in issues if i.status == 'open']),
        'in_progress': len([i for i in issues if i.status == 'in_progress']),
        'resolved': len([i for i in issues if i.status == 'resolved']),
        'closed': len([i for i in issues if i.status == 'closed']),
        'critical': len([i for i in issues if i.priority == 'critical'])
    }
    
    return render_template('consultant/issues.html',
                         issues=issues,
                         stats=stats,
                         now=datetime.now())


@consultant_bp.route('/issues/<int:issue_id>/update', methods=['POST'])
@login_required
@consultant_required
def update_issue(issue_id):
    """تحديث حالة قضية"""
    
    issue = Issue.query.get_or_404(issue_id)
    
    # التحقق من الصلاحية
    project = Project.query.get(issue.project_id)
    if project.consultant_id != current_user.id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    status = data.get('status')
    resolution = data.get('resolution')
    
    try:
        issue.status = status
        if resolution:
            issue.resolution = resolution
        if status == 'resolved' or status == 'closed':
            issue.resolution_date = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# الاجتماعات
# ============================================

@consultant_bp.route('/meetings')
@login_required
@consultant_required
def meetings_list():
    """عرض جميع الاجتماعات"""
    
    projects = get_consultant_projects()
    
    meetings = Meeting.query.filter(
        Meeting.project_id.in_([p.id for p in projects])
    ).order_by(Meeting.scheduled_date.desc()).all()
    
    # إحصائيات
    stats = {
        'total': len(meetings),
        'scheduled': len([m for m in meetings if m.status == 'scheduled']),
        'completed': len([m for m in meetings if m.status == 'completed']),
        'upcoming': len([m for m in meetings if m.status == 'scheduled' and m.scheduled_date > datetime.now()])
    }
    
    return render_template('consultant/meetings.html',
                         meetings=meetings,
                         stats=stats,
                         now=datetime.now())


@consultant_bp.route('/meetings/<int:meeting_id>')
@login_required
@consultant_required
def view_meeting(meeting_id):
    """عرض تفاصيل اجتماع"""
    
    meeting = Meeting.query.get_or_404(meeting_id)
    
    # التحقق من الصلاحية
    project = Project.query.get(meeting.project_id)
    if project.consultant_id != current_user.id and current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('consultant.meetings_list'))
    
    return render_template('consultant/view_meeting.html',
                         meeting=meeting,
                         now=datetime.now())


# ============================================
# التقارير (بدون معلومات مالية)
# ============================================

@consultant_bp.route('/reports/progress')
@login_required
@consultant_required
def progress_reports():
    """تقارير التقدم للمشاريع"""
    
    projects = get_consultant_projects()
    
    reports = []
    for project in projects:
        # حساب التقدم الأسبوعي
        weekly_progress = []
        for i in range(4, 0, -1):
            week_start = date.today() - timedelta(days=i*7)
            week_end = week_start + timedelta(days=6)
            
            # يمكن حساب التقدم الأسبوعي من السجلات
            weekly_progress.append({
                'week': f'الأسبوع {5-i}',
                'progress': 0  # سيتم حسابه لاحقاً
            })
        
        reports.append({
            'project': project,
            'total_tasks': Task.query.filter_by(project_id=project.id).count(),
            'completed_tasks': Task.query.filter_by(project_id=project.id, status='completed').count(),
            'completion_rate': (Task.query.filter_by(project_id=project.id, status='completed').count() / 
                               Task.query.filter_by(project_id=project.id).count() * 100) if Task.query.filter_by(project_id=project.id).count() > 0 else 0,
            'delayed_tasks': Task.query.filter_by(project_id=project.id).filter(Task.status.in_(['pending', 'in_progress'])).count(),
            'weekly_progress': weekly_progress
        })
    
    return render_template('consultant/reports/progress.html',
                         reports=reports,
                         now=datetime.now())


# ============================================
# الإشعارات
# ============================================

@consultant_bp.route('/notifications')
@login_required
def notifications():
    """عرض جميع الإشعارات"""
    
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('consultant/notifications/index.html', notifications=notifications)


@consultant_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """تحديد إشعار كمقروء"""
    
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    notification.mark_as_read()
    db.session.commit()
    
    return jsonify({'success': True})


@consultant_bp.route('/notifications/mark-all-read', methods=['POST'])
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
# الملف الشخصي
# ============================================

@consultant_bp.route('/profile')
@login_required
def profile():
    """الملف الشخصي للمهندس الاستشاري"""
    
    return render_template('consultant/profile.html', user=current_user)


# ============================================
# API Routes
# ============================================

@consultant_bp.route('/api/projects/<int:project_id>/tasks')
@login_required
@consultant_required
def api_project_tasks(project_id):
    """API لجلب مهام المشروع"""
    
    project = check_consultant_project_access(project_id)
    if not project:
        return jsonify({'error': 'غير مصرح'}), 403
    
    tasks = Task.query.filter_by(project_id=project_id).all()
    
    return jsonify({
        'success': True,
        'tasks': [{
            'id': t.id,
            'task_code': t.task_code,
            'task_name': t.task_name,
            'status': t.status,
            'progress': t.progress.progress_percentage if t.progress else 0,
            'planned_start': t.planning.planned_start.strftime('%Y-%m-%d') if t.planning and t.planning.planned_start else None,
            'planned_finish': t.planning.planned_finish.strftime('%Y-%m-%d') if t.planning and t.planning.planned_finish else None
        } for t in tasks]
    })


@consultant_bp.route('/api/dashboard/stats')
@login_required
@consultant_required
def api_dashboard_stats():
    """API لإحصائيات لوحة التحكم"""
    
    projects = get_consultant_projects()
    
    stats = {
        'total_projects': len(projects),
        'active_projects': len([p for p in projects if p.status == 'active']),
        'completed_projects': len([p for p in projects if p.status == 'completed']),
        'pending_reviews': g.pending_reviews_count,
        'pending_verifications': g.pending_verifications_count,
        'total_tasks': sum(Task.query.filter_by(project_id=p.id).count() for p in projects),
        'completed_tasks': sum(Task.query.filter_by(project_id=p.id, status='completed').count() for p in projects),
        'avg_progress': sum(p.progress.progress_percentage if p.progress else 0 for p in projects) / len(projects) if projects else 0
    }
    
    return jsonify({'success': True, 'stats': stats})
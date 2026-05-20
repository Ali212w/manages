"""
company_routes.py - مسارات الشركة لمدير النظام
"""
from ..extensions import db
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file, g,session
from flask_login import login_required, current_user,logout_user
from werkzeug.utils import secure_filename
from app.models import Organization, User, Department, Project, Task, ProjectDocument, Notification,TaskAssignment,TaskPlanning,UserSkill,Meeting,Issue,RiskUpdate,PlatformOwner,PlatformAdmin
from app.models import ResourceRequest, ResourceDelivery, ResourceRequestItem,Resource,EPS,WBS,Activity,ProjectProgressLog,ActivityExpense,ResourceOfferHistory,SubscriptionPlan
from app.routes import company_bp
from datetime import datetime, date, timedelta
import os
import json
from functools import wraps
from app.utils.utils import *
from app.forms import *
from app.services.notification_service import NotificationService
from app.services.resource_delivery_service import ResourceDeliveryService
from app.services.business_intelligence import BusinessIntelligence
import requests
import time
from sqlalchemy import func, and_, or_
from app.decorators import (
    subscription_required,
    active_subscription_required,
    org_admin_required,
    company_owner_required,
    role_required
)
from app.plan_decorators import (
    check_user_limit,
    check_project_limit,
    check_storage_limit,
    feature_required
)
import logging

logger = logging.getLogger(__name__)
# ============================================
# دالة التحقق من صلاحية مدير الشركة
# ============================================

def org_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'org_admin':
            flash('غير مصرح بالوصول إلى هذه الصفحة', 'danger')
            return redirect(url_for('company.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@company_bp.route('/logout')
@login_required
def logout():
    """تسجيل الخروج والعودة للصفحة الرئيسية"""
    # تخزين اسم المستخدم للرسالة
    username = current_user.full_name if current_user.full_name else 'المستخدم'
    
    # تسجيل الخروج
    logout_user()
    
    # مسح الجلسة بالكامل
    session.clear()
    
    # رسالة ت أكيد
    flash(f'👋 وداعاً {username}، تم تسجيل الخروج بنجاح. نتمنى لك يوماً سعيداً!', 'success')
    
    # التوجيه إلى الصفحة الرئيسية للمصادقة
    return redirect(url_for('auth.index'))
# ============================================
# قبل كل طلب - تحميل معلومات الشركة
# ============================================
def get_pending_deliveries_count(org_id=None, user_role=None):
    """الحصول على عدد التسليمات المعلقة (مواد + معدات)"""
    from app.models import ResourceDelivery, EquipmentDelivery
    
    if user_role not in ['org_admin', 'project_manager']:
        return 0
    
    material_count = ResourceDelivery.query.filter_by(status='pending').count()
    equipment_count = EquipmentDelivery.query.filter_by(status='pending').count()
    
    return material_count + equipment_count

@company_bp.before_request
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
        g.pending_deliveries_count = get_pending_deliveries_count(
            current_user.org_id, 
            current_user.role
        )
        
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



# ============================================
# لوحة التحكم الرئيسية
# ============================================

@company_bp.route('/')
@login_required
# @active_subscription_required  # يتطلب اشتراك نشط
def dashboard():
    """لوحة تحكم الشركة الرئيسية مع تحليلات ذكية"""
    
    company_id = current_user.org_id
    today_date = date.today()
    
    # ============================================
    # إحصائيات سريعة محسنة
    # ============================================
    
    # إحصائيات المستخدمين
    total_users = User.query.filter_by(org_id=company_id).count()
    active_users = User.query.filter_by(org_id=company_id, is_user_active=True).count()
    
    # إحصائيات المشاريع
    total_projects = Project.query.filter_by(org_id=company_id).count()
    active_projects = Project.query.filter_by(org_id=company_id, status='active').count()
    completed_projects = Project.query.filter_by(org_id=company_id, status='completed').count()
    
    # إحصائيات المهام
    pending_tasks_count = Task.query.join(Project).filter(
        Project.org_id == company_id, 
        Task.status == 'pending'
    ).count()
    
    in_progress_tasks_count = Task.query.join(Project).filter(
        Project.org_id == company_id,
        Task.status == 'in_progress'
    ).count()
    
    completed_tasks_count = Task.query.join(Project).filter(
        Project.org_id == company_id,
        Task.status == 'completed'
    ).count()
    
    total_tasks_count = pending_tasks_count + in_progress_tasks_count + completed_tasks_count
    
    # حساب المهام المتأخرة
    all_active_tasks = Task.query.join(Project).filter(
        Project.org_id == company_id,
        Task.status.in_(['pending', 'in_progress'])
    ).all()
    
    delayed_tasks_count = sum(1 for task in all_active_tasks if hasattr(task, 'is_delayed') and task.is_delayed)
    
    # إحصائيات المستندات
    from app.models.document_models import ProjectDocument, BillItem
    
    total_documents = ProjectDocument.query.join(Project).filter(
        Project.org_id == company_id
    ).count() if 'ProjectDocument' in dir() else 0
    
    pending_approvals = ProjectDocument.query.join(Project).filter(
        Project.org_id == company_id,
        ProjectDocument.requires_approval == True,
        ProjectDocument.approval_status == 'pending'
    ).count() if 'ProjectDocument' in dir() else 0
    
    total_bill_items = BillItem.query.join(Project).filter(
        Project.org_id == company_id
    ).count() if 'BillItem' in dir() else 0
    
    # إحصائيات الذكاء الاصطناعي
    from app.models.ai_models import AICommand, AISuggestion, AIRecommendation
    
    pending_ai_commands = AICommand.query.filter_by(
        org_id=company_id,
        status='pending'
    ).count() if 'AICommand' in dir() else 0
    
    active_suggestions = AISuggestion.query.filter_by(
        org_id=company_id,
        status='pending'
    ).count() if 'AISuggestion' in dir() else 0
    
    # إحصائيات سريعة
    stats = {
        'total_users': total_users,
        'active_users': active_users,
        'total_projects': total_projects,
        'active_projects': active_projects,
        'completed_projects': completed_projects,
        'total_tasks': total_tasks_count,
        'pending_tasks': pending_tasks_count,
        'in_progress_tasks': in_progress_tasks_count,
        'completed_tasks': completed_tasks_count,
        'delayed_tasks': delayed_tasks_count,
        'total_documents': total_documents,
        'pending_approvals': pending_approvals,
        'total_bill_items': total_bill_items,
        'pending_ai_commands': pending_ai_commands,
        'active_suggestions': active_suggestions,
        'storage_used': getattr(g.company, 'storage_used_mb', 0),
        'storage_limit': getattr(g.company, 'storage_limit_mb', 0)
    }
    
    # ============================================
    # إحصائيات متقدمة للوحة التحكم
    # ============================================
    
    # 1. أداء المشاريع
    projects = Project.query.filter_by(org_id=company_id).all()
    project_performance = []
    
    for project in projects:
        # جلب مهام المشروع
        tasks = Task.query.filter_by(project_id=project.id).all()
        total_tasks = len(tasks)
        completed_tasks = len([t for t in tasks if t.status == 'completed'])
        
        # حساب المهام المتأخرة
        delayed_tasks = len([t for t in tasks if t.status in ['pending', 'in_progress'] and 
                            hasattr(t, 'is_delayed') and t.is_delayed])
        
        # حساب التقدم
        progress = 0
        if hasattr(project, 'progress') and project.progress:
            progress = project.progress.progress_percentage
        elif hasattr(project, 'get_progress'):
            progress = project.get_progress()
        elif total_tasks > 0:
            progress = (completed_tasks / total_tasks) * 100
        
        # حساب المهام الحرجة (أولوية عالية)
        critical_tasks = len([t for t in tasks if hasattr(t, 'priority') and t.priority >= 4])
        
        # اسم المشروع
        project_name = getattr(project, 'name', '')
        if not project_name and hasattr(project, 'project_name'):
            project_name = project.project_name
        
        project_performance.append({
            'id': project.id,
            'name': project_name,
            'code': getattr(project, 'project_code', ''),
            'progress': progress,
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
            'delayed_tasks': delayed_tasks,
            'critical_tasks': critical_tasks,
            'status': getattr(project, 'status', 'unknown'),
            'is_delayed': delayed_tasks > 0,
            'days_behind': sum(getattr(t, 'delay_days', 0) for t in tasks if hasattr(t, 'is_delayed') and t.is_delayed)
        })
    
    # ترتيب المشاريع حسب نسبة الإنجاز
    project_performance.sort(key=lambda x: x['completion_rate'], reverse=True)
    top_projects = project_performance[:3]
    at_risk_projects = [p for p in project_performance if p['delayed_tasks'] > 0][:3]
    
    # 2. أداء المستخدمين
    users = User.query.filter_by(org_id=company_id, is_user_active=True).all()
    user_performance = []
    
    for user in users:
        # المهام التي يشرف عليها
        supervised_tasks = Task.query.filter_by(supervisor_id=user.id).all()
        
        # المهام التي تم تفويضها للمستخدم
        delegated_tasks = Task.query.filter_by(delegate_id=user.id).all()
        
        # حساب المهام المكتملة للمستخدم
        from app.models.task_models import TaskAssignment
        if 'TaskAssignment' in dir():
            assigned_tasks = TaskAssignment.query.filter_by(user_id=user.id).all()
            total_assigned = len(assigned_tasks)
            completed_assigned = len([a for a in assigned_tasks if a.status == 'completed'])
            
            # حساب الكفاءة
            efficiency = 0
            if total_assigned > 0:
                avg_quality = sum([getattr(a, 'quality_rating', 0) or 0 for a in assigned_tasks]) / total_assigned
                completion_rate = (completed_assigned / total_assigned * 100) if total_assigned > 0 else 0
                efficiency = (completion_rate * 0.6) + (avg_quality * 20 * 0.4)
        else:
            total_assigned = 0
            completed_assigned = 0
            efficiency = 0
        
        user_performance.append({
            'id': user.id,
            'name': user.full_name,
            'role': user.role,
            'assigned_tasks': total_assigned,
            'completed_tasks': completed_assigned,
            'completion_rate': (completed_assigned / total_assigned * 100) if total_assigned > 0 else 0,
            'supervised_tasks': len(supervised_tasks),
            'delegated_tasks': len(delegated_tasks),
            'efficiency': round(efficiency, 1),
            'avatar': getattr(user, 'profile_image', None)
        })
    
    # أفضل 3 موظفين
    top_performers = sorted(user_performance, key=lambda x: x['efficiency'], reverse=True)[:3]
    
    # 3. إحصائيات التأخيرات
    total_delay_days = 0
    critical_delayed = 0
    
    for task in all_active_tasks:
        if hasattr(task, 'is_delayed') and task.is_delayed:
            total_delay_days += getattr(task, 'delay_days', 0)
            if hasattr(task, 'priority') and task.priority >= 4:
                critical_delayed += 1
    
    delayed_stats = {
        'total_delayed': delayed_tasks_count,
        'total_delay_days': total_delay_days,
        'critical_delayed': critical_delayed
    }
    
    # 4. إشعارات ذكية
    smart_notifications = []
    
    # مشاريع معرضة للخطر
    for project in at_risk_projects:
        if project['delayed_tasks'] > 0:
            smart_notifications.append({
                'type': 'warning',
                'title': f'⚠️ مشروع {project["name"]}',
                'message': f'يوجد {project["delayed_tasks"]} مهام متأخرة. يوصى بالتدخل.',
                'icon': 'exclamation-triangle',
                'link': url_for('projects.project_detail', project_id=project['id'])
            })
    
    # موظفون متميزون
    for performer in top_performers[:2]:
        smart_notifications.append({
            'type': 'success',
            'title': f'🌟 أداء متميز: {performer["name"]}',
            'message': f'كفاءة {performer["efficiency"]}% مع {performer["completed_tasks"]} مهمة مكتملة',
            'icon': 'star',
            'link': url_for('company.view_user', user_id=performer['id'])
        })
    
    # مهام حرجة
    if delayed_stats['critical_delayed'] > 0:
        smart_notifications.append({
            'type': 'danger',
            'title': '🔥 مهام حرجة متأخرة',
            'message': f'يوجد {delayed_stats["critical_delayed"]} مهام ذات أولوية عالية متأخرة',
            'icon': 'fire',
            'link': url_for('tasks.list_tasks', filter='delayed')
        })
    
    # اقتراحات ذكية
    if active_suggestions > 0:
        smart_notifications.append({
            'type': 'info',
            'title': '💡 اقتراحات ذكية جديدة',
            'message': f'يوجد {active_suggestions} اقتراحات ذكية جديدة للمشاريع',
            'icon': 'lightbulb',
            'link': url_for('ai.index')
        })
    
    # 5. آخر المشاريع
    recent_projects = Project.query.filter_by(
        org_id=company_id
    ).order_by(Project.created_at.desc()).limit(5).all()
    
    recent_projects_data = []
    for project in recent_projects:
        project_name = getattr(project, 'name', '')
        if not project_name and hasattr(project, 'project_name'):
            project_name = project.project_name
        
        recent_projects_data.append({
            'id': project.id,
            'name': project_name,
            'code': getattr(project, 'project_code', ''),
            'status': getattr(project, 'status', 'unknown')
        })
    
    # 6. آخر المستخدمين
    recent_users = User.query.filter_by(
        org_id=company_id
    ).order_by(User.created_at.desc()).limit(5).all()
    
    # 7. آخر أوامر الذكاء الاصطناعي
    recent_ai_commands = []
    if 'AICommand' in dir():
        recent_ai_commands = AICommand.query.filter_by(
            org_id=company_id
        ).order_by(AICommand.created_at.desc()).limit(3).all()
    
    # 8. المهام القادمة
    upcoming_tasks = Task.query\
        .join(Project)\
        .outerjoin(TaskPlanning)\
        .filter(
            Project.org_id == company_id,
            Task.status.in_(['pending', 'in_progress'])
        )\
        .order_by(TaskPlanning.planned_start.asc().nulls_last())\
        .limit(5)\
        .all()
    
    upcoming_tasks_data = []
    for task in upcoming_tasks:
        project_name = getattr(task.project, 'name', '')
        if not project_name and hasattr(task.project, 'project_name'):
            project_name = task.project.project_name
        
        responsible_name = 'غير معين'
        if hasattr(task, 'delegate') and task.delegate:
            responsible_name = task.delegate.full_name
        elif hasattr(task, 'supervisor') and task.supervisor:
            responsible_name = task.supervisor.full_name
        
        progress = 0
        if hasattr(task, 'progress') and task.progress:
            progress = task.progress.progress_percentage
        
        task_data = {
            'id': task.id,
            'name': task.task_name,
            'code': task.task_code,
            'status': task.status,
            'progress': progress,
            'planned_start': task.planning.planned_start if task.planning else None,
            'planned_end': task.planning.planned_finish if task.planning else None,
            'project_name': project_name,
            'is_delayed': hasattr(task, 'is_delayed') and task.is_delayed,
            'delay_days': getattr(task, 'delay_days', 0),
            'responsible': responsible_name,
            'priority': getattr(task, 'priority', 3)
        }
        upcoming_tasks_data.append(task_data)
    
    # 9. نشاط اليوم
    today_start = datetime.combine(today_date, datetime.min.time())
    
    completed_tasks_today = Task.query.join(Project).filter(
        Project.org_id == company_id,
        Task.status == 'completed',
        Task.updated_at >= today_start
    ).count()
    
    started_tasks_today = 0
    for task in Task.query.join(Project).filter(
        Project.org_id == company_id,
        Task.status == 'in_progress'
    ).all():
        if hasattr(task, 'execution') and task.execution and hasattr(task.execution, 'actual_start') and task.execution.actual_start:
            if task.execution.actual_start >= today_start:
                started_tasks_today += 1
    
    # أوامر الذكاء الاصطناعي اليوم
    ai_commands_today = AICommand.query.filter_by(
        org_id=company_id
    ).filter(AICommand.created_at >= today_start).count() if 'AICommand' in dir() else 0
    
    today_activity = {
        'new_users': User.query.filter_by(org_id=company_id).filter(User.created_at >= today_start).count(),
        'new_projects': Project.query.filter_by(org_id=company_id).filter(Project.created_at >= today_start).count(),
        'completed_tasks': completed_tasks_today,
        'started_tasks': started_tasks_today,
        'ai_commands': ai_commands_today
    }
    
    # 10. توقعات اليوم
    predictions = {
        'expected_completions': min(5, today_activity['started_tasks'] + 2),
        'risk_level': 'high' if delayed_stats['critical_delayed'] > 2 else 'medium' if delayed_stats['critical_delayed'] > 0 else 'low'
    }
    
    # 11. مشاريع Primavera
    primavera_projects = []
    if hasattr(Project, 'is_primavera_imported'):
        primavera_projects = Project.query.filter(
            Project.org_id == company_id,
            Project.is_primavera_imported == True
        ).all()
    pending_deliveries_count = ResourceDelivery.query.filter_by(
        status='pending'
    ).count() if current_user.role in ['org_admin', 'project_manager'] else 0
    
    # إضافة إحصائيات الموارد
    low_stock_resources = Resource.query.filter(
        Resource.available_quantity < Resource.minimum_quantity
    ).count() if hasattr(Resource, 'minimum_quantity') else 0
    return render_template('company/dashboard.html',
                         stats=stats,
                         project_performance=project_performance,
                         top_projects=top_projects,
                         at_risk_projects=at_risk_projects,
                         user_performance=user_performance,
                         top_performers=top_performers,
                         delayed_stats=delayed_stats,
                         smart_notifications=smart_notifications,
                         recent_projects=recent_projects_data,
                         recent_users=recent_users,
                         recent_ai_commands=recent_ai_commands,
                         upcoming_tasks=upcoming_tasks_data,
                         today_activity=today_activity,
                         predictions=predictions,
                         primavera_projects=primavera_projects,
                         pending_deliveries_count=pending_deliveries_count,
                         low_stock_resources=low_stock_resources,
                         now=datetime.now())


@company_bp.route('/executive-dashboard')
@login_required
def executive_dashboard():
    """لوحة التحكم التنفيذية"""
    if current_user.role not in ['org_admin', 'project_manager']:
        flash('غير مصرح بالوصول إلى لوحة التحكم', 'danger')
        return redirect(url_for('company.dashboard'))
    
    return render_template('company/dashboard2.html')


@company_bp.route('/api/dashboard/live-data')
@login_required
def get_live_dashboard_data():
    """API للحصول على البيانات اللحظية للوحة التحكم"""
    try:
        # جلب بيانات المشاريع
        projects_data = get_projects_data(current_user.org_id)
        
        # تجهيز بيانات الرسوم البيانية
        chart_data = prepare_chart_data(projects_data)
        
        # جلب التنبيهات النشطة
        alerts = get_active_alerts(current_user.org_id)
        
        # حساب المؤشرات الرئيسية
        total_projects = len(projects_data)
        active_projects = sum(1 for p in projects_data if p.get('status_text') == 'قيد التنفيذ')
        total_budget = sum(p.get('budget', 0) for p in projects_data)
        total_actual = sum(p.get('actual_cost', 0) for p in projects_data)
        
        # حساب الاتجاهات
        trends = calculate_trends(projects_data)
        
        # حساب نسبة الإنجاز المتوسطة
        avg_progress = sum(p.get('progress', 0) for p in projects_data) / total_projects if total_projects > 0 else 0
        
        kpis = {
            'overall': {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'total_budget': total_budget,
                'total_actual_cost': total_actual,
                'average_progress': avg_progress,
                'on_time_rate': calculate_on_time_rate(projects_data),
                'on_budget_rate': calculate_on_budget_rate(projects_data)
            },
            'trends': trends
        }
        
        return jsonify({
            'success': True,
            'kpis': kpis,
            'projects': projects_data,
            'alerts': alerts,
            'project_progress': chart_data['progress'],
            'project_names': chart_data['names'],
            'budget_distribution': chart_data['budget'],
            'cpi_data': chart_data['cpi'],
            'spi_data': chart_data['spi'],
            'evm_pv': chart_data['evm_pv'],
            'evm_ev': chart_data['evm_ev'],
            'evm_ac': chart_data['evm_ac'],
            'timestamp': time.time()
        })
        
    except Exception as e:
        logger.error(f"خطأ في API لوحة التحكم: {str(e)}")
        return jsonify({
            'success': False, 
            'error': str(e),
            'projects': [],
            'alerts': [],
            'project_progress': [],
            'project_names': []
        }), 500

@company_bp.route('/api/project/<int:project_id>/details')
@login_required
def get_project_details(project_id):
    """جلب تفاصيل مشروع معين للعرض في الـ Modal"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != current_user.org_id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'project': {
            'id': project.id,
            'name': project.name,
            'code': project.project_code,
            'progress': project.get_progress(),
            'status': project.status,
            'status_text': get_status_text(project.status),
            'status_color': get_status_color(project.status),
            'budget': project.budget.current_budget if project.budget else 0,
            'actual_cost': project.cost.total_actual_cost if project.cost else 0,
            'variance': (project.cost.total_actual_cost - project.budget.current_budget) if project.budget and project.cost else 0,
            'cpi': project.performance.cpi if project.performance else 1.0,
            'spi': project.performance.spi if project.performance else 1.0,
            'planned_start': project.dates.planned_start.strftime('%Y-%m-%d') if project.dates and project.dates.planned_start else None,
            'planned_finish': project.dates.planned_finish.strftime('%Y-%m-%d') if project.dates and project.dates.planned_finish else None
        }
    })

def get_projects_data(org_id):
    """جلب بيانات المشاريع للتحديث اللحظي"""
    try:
        projects = Project.query.filter_by(org_id=org_id).all()
        projects_data = []
        
        for project in projects:
            # حساب التقدم
            progress = project.get_progress() if hasattr(project, 'get_progress') else 0
            
            # حساب الميزانية والتكاليف
            budget = project.budget.current_budget if project.budget else 0
            actual_cost = project.cost.total_actual_cost if project.cost else 0
            variance = actual_cost - budget
            
            # حساب مؤشرات الأداء
            cpi = project.performance.cpi if project.performance and hasattr(project.performance, 'cpi') else 1.0
            spi = project.performance.spi if project.performance and hasattr(project.performance, 'spi') else 1.0
            
            projects_data.append({
                'id': project.id,
                'name': project.name,
                'code': project.project_code,
                'progress': progress,
                'budget': budget,
                'actual_cost': actual_cost,
                'variance': variance,
                'cpi': cpi,
                'spi': spi,
                'status_text': get_status_text(project.status),
                'status_color': get_status_color(project.status),
                'status': project.status
            })
        
        return projects_data
        
    except Exception as e:
        logger.error(f"خطأ في جلب بيانات المشاريع: {str(e)}")
        return []


def prepare_chart_data(projects):
    """تجهيز بيانات الرسوم البيانية من بيانات المشاريع"""
    try:
        if not projects:
            return {
                'names': [],
                'progress': [],
                'budget': [],
                'cpi': [],
                'spi': [],
                'evm_pv': [],
                'evm_ev': [],
                'evm_ac': []
            }
        
        names = []
        progress = []
        budget_values = []
        cpi = []
        spi = []
        evm_pv = []
        evm_ev = []
        evm_ac = []
        
        for project in projects:
            names.append(project.get('name', 'مشروع'))
            progress.append(project.get('progress', 0))
            budget_values.append(project.get('budget', 0))
            cpi.append(project.get('cpi', 1.0))
            spi.append(project.get('spi', 1.0))
            evm_pv.append(project.get('budget', 0))
            evm_ev.append(project.get('budget', 0) * (project.get('progress', 0) / 100))
            evm_ac.append(project.get('actual_cost', 0))
        
        # حساب توزيع الميزانية (نسب مئوية)
        total_budget = sum(budget_values)
        if total_budget > 0:
            budget_distribution = [(b / total_budget) * 100 for b in budget_values]
        else:
            budget_distribution = [0] * len(budget_values)
        
        return {
            'names': names,
            'progress': progress,
            'budget': budget_distribution,
            'cpi': cpi,
            'spi': spi,
            'evm_pv': evm_pv,
            'evm_ev': evm_ev,
            'evm_ac': evm_ac
        }
        
    except Exception as e:
        logger.error(f"خطأ في تجهيز بيانات الرسوم البيانية: {str(e)}")
        return {
            'names': [],
            'progress': [],
            'budget': [],
            'cpi': [],
            'spi': [],
            'evm_pv': [],
            'evm_ev': [],
            'evm_ac': []
        }


def get_active_alerts(org_id):
    """جلب التنبيهات النشطة للمؤسسة"""
    try:
        # جلب الإشعارات غير المقروءة من آخر 24 ساعة
        last_24h = datetime.utcnow() - timedelta(hours=24)
        
        notifications = Notification.query.filter(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
            Notification.created_at >= last_24h
        ).order_by(Notification.created_at.desc()).limit(20).all()
        
        alerts_data = []
        for notif in notifications:
            # حساب الوقت المنقضي
            time_ago = format_alert_time(notif.created_at)
            
            # تحديد نوع التنبيه
            alert_type = 'info'
            if notif.priority == 'critical':
                alert_type = 'critical'
            elif notif.priority == 'high':
                alert_type = 'warning'
            
            alerts_data.append({
                'id': notif.id,
                'title': notif.title or 'تنبيه',
                'message': notif.message or '',
                'type': alert_type,
                'time': time_ago,
                'priority': notif.priority or 'medium'
            })
        
        return alerts_data
        
    except Exception as e:
        logger.error(f"خطأ في جلب التنبيهات النشطة: {str(e)}")
        return []


def format_alert_time(created_at):
    """تنسيق وقت التنبيه بشكل مقروء"""
    try:
        if not created_at:
            return 'الآن'
        
        now = datetime.utcnow()
        diff = now - created_at
        
        if diff.total_seconds() < 60:
            return 'الآن'
        elif diff.total_seconds() < 3600:
            minutes = int(diff.total_seconds() / 60)
            return f'{minutes} دقيقة'
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f'{hours} ساعة'
        else:
            days = int(diff.total_seconds() / 86400)
            return f'{days} يوم'
            
    except Exception as e:
        logger.error(f"خطأ في تنسيق الوقت: {str(e)}")
        return 'الآن'


def calculate_trends(projects_data):
    """حساب اتجاهات التغيير للمشاريع"""
    try:
        trends = {
            'projects': {'direction': 'neutral', 'percentage': 0},
            'active': {'direction': 'neutral', 'percentage': 0},
            'budget': {'direction': 'neutral', 'percentage': 0},
            'actual': {'direction': 'neutral', 'percentage': 0}
        }
        
        if projects_data:
            # حساب عدد المشاريع النشطة
            current_active = sum(1 for p in projects_data if p.get('status_text') == 'قيد التنفيذ')
            if current_active > 0:
                # اتجاه إيجابي إذا كان هناك مشاريع نشطة
                trends['active']['direction'] = 'up'
                trends['active']['percentage'] = min(current_active * 5, 100)
            
            # حساب اتجاه الميزانية
            total_budget = sum(p.get('budget', 0) for p in projects_data)
            if total_budget > 0:
                trends['budget']['direction'] = 'up'
                trends['budget']['percentage'] = min((total_budget / 1000000) * 100, 100)
        
        return trends
        
    except Exception as e:
        logger.error(f"خطأ في حساب الاتجاهات: {str(e)}")
        return {
            'projects': {'direction': 'neutral', 'percentage': 0},
            'active': {'direction': 'neutral', 'percentage': 0},
            'budget': {'direction': 'neutral', 'percentage': 0},
            'actual': {'direction': 'neutral', 'percentage': 0}
        }


def get_status_text(status):
    """ترجمة حالة المشروع"""
    status_map = {
        'planning': 'تخطيط',
        'in_progress': 'قيد التنفيذ',
        'completed': 'مكتمل',
        'suspended': 'معلق',
        'cancelled': 'ملغي',
        'critical_delay': 'تأخير خطير'
    }
    return status_map.get(status, status)


def get_status_color(status):
    """لون حالة المشروع"""
    color_map = {
        'planning': 'secondary',
        'in_progress': 'primary',
        'completed': 'success',
        'suspended': 'warning',
        'cancelled': 'danger',
        'critical_delay': 'danger'
    }
    return color_map.get(status, 'secondary')


def calculate_on_time_rate(projects):
    """حساب نسبة المشاريع في الوقت المحدد"""
    try:
        if not projects:
            return 0
        
        on_time = 0
        for p in projects:
            # التحقق من حالة المشروع
            if p.get('status') == 'completed':
                on_time += 1
            elif p.get('status') == 'in_progress':
                on_time += 1
        
        return (on_time / len(projects)) * 100
        
    except Exception as e:
        logger.error(f"خطأ في حساب نسبة الالتزام بالوقت: {str(e)}")
        return 0


def calculate_on_budget_rate(projects):
    """حساب نسبة المشاريع ضمن الميزانية"""
    try:
        if not projects:
            return 0
        
        on_budget = 0
        for p in projects:
            actual = p.get('actual_cost', 0)
            budget = p.get('budget', 0)
            if actual <= budget:
                on_budget += 1
        
        return (on_budget / len(projects)) * 100
        
    except Exception as e:
        logger.error(f"خطأ في حساب نسبة الالتزام بالميزانية: {str(e)}")
        return 0

# app/routes/company_routes.py

@company_bp.route('/project/<int:project_id>')
@login_required
def view_project(project_id):
    """عرض صفحة تفاصيل المشروع"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != current_user.org_id and current_user.role != 'org_admin' and project.project_manager_id != current_user.id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    return render_template('company/project_detail.html', project=project)


@company_bp.route('/api/project/<int:project_id>/full-details')
@login_required
def get_project_full_details(project_id):
    """جلب التفاصيل الكاملة لمشروع معين للصفحة المنفردة"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != current_user.org_id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    try:
        # جلب البيانات التاريخية للتقدم
        from app.models.project_models import ProjectProgressLog
        historical_progress = []
        historical_dates = []
        progress_logs = ProjectProgressLog.query.filter_by(
            project_id=project_id
        ).order_by(ProjectProgressLog.record_date).limit(12).all()
        
        for log in progress_logs:
            historical_progress.append(log.progress_percentage)
            historical_dates.append(log.record_date.strftime('%Y-%m-%d'))
        
        # جلب الأنشطة
        activities = []
        activity_names = []
        activity_budgets = []
        activity_progress = []
        
        for activity in project.activities:
            activities.append({
                'id': activity.id,
                'name': activity.activity_name,
                'progress': activity.progress_percentage,
                'budget': activity.planned_cost if hasattr(activity, 'planned_cost') else 0,
                'actual_cost': activity.actual_cost if hasattr(activity, 'actual_cost') else 0,
                'cpi': (activity.actual_cost / activity.planned_cost) if activity.planned_cost and activity.planned_cost > 0 else 1.0,
                'spi': activity.progress_percentage / 100 if activity.progress_percentage > 0 else 1.0,
                'status': activity.status,
                'status_text': get_activity_status_text(activity.status),
                'status_color': get_activity_status_color(activity.status)
            })
            activity_names.append(activity.activity_name)
            activity_budgets.append(activity.planned_cost if hasattr(activity, 'planned_cost') else 0)
            activity_progress.append(activity.progress_percentage)
        
        # بيانات EVM
        evm_pv = []
        evm_ev = []
        evm_ac = []
        evm_dates = []
        
        if progress_logs:
            total_budget = project.budget.current_budget if project.budget else 0
            for log in progress_logs:
                evm_pv.append(total_budget)
                evm_ev.append(total_budget * (log.progress_percentage / 100))
                evm_ac.append(log.actual_cost if hasattr(log, 'actual_cost') else 0)
                evm_dates.append(log.record_date.strftime('%Y-%m-%d'))
        
        # بيانات المهام
        tasks = project.tasks.all()
        completed_tasks = [t for t in tasks if t.status == 'completed']
        in_progress_tasks = [t for t in tasks if t.status == 'in_progress']
        overdue_tasks = [t for t in tasks if t.is_delayed]
        
        # بيانات التكاليف الشهرية
        monthly_costs = get_monthly_costs(project_id)
        
        # بيانات مؤشرات الأداء
        cpi_data = []
        spi_data = []
        
        for activity in project.activities:
            cpi = (activity.actual_cost / activity.planned_cost) if activity.planned_cost and activity.planned_cost > 0 else 1.0
            spi = activity.progress_percentage / 100 if activity.progress_percentage > 0 else 1.0
            cpi_data.append(cpi)
            spi_data.append(spi)
        
        return jsonify({
            'success': True,
            'project': {
                'id': project.id,
                'name': project.name,
                'code': project.project_code,
                'description': project.description,
                'status': project.status,
                'status_text': get_status_text(project.status),
                'status_color': get_status_color(project.status),
                'progress': project.get_progress(),
                'budget': project.budget.current_budget if project.budget else 0,
                'actual_cost': project.cost.total_actual_cost if project.cost else 0,
                'planned_start': project.dates.planned_start.strftime('%Y-%m-%d') if project.dates and project.dates.planned_start else None,
                'planned_finish': project.dates.planned_finish.strftime('%Y-%m-%d') if project.dates and project.dates.planned_finish else None,
                'actual_start': project.dates.actual_start.strftime('%Y-%m-%d') if project.dates and project.dates.actual_start else None,
                'actual_finish': project.dates.actual_finish.strftime('%Y-%m-%d') if project.dates and project.dates.actual_finish else None,
                'cpi': project.performance.cpi if project.performance else 1.0,
                'spi': project.performance.spi if project.performance else 1.0,
                'eac': project.performance.eac if project.performance else 0,
                'etc': project.performance.etc if project.performance else 0,
                'vac': project.performance.vac if project.performance else 0
            },
            'historical_progress': historical_progress,
            'historical_dates': historical_dates,
            'activities': activities,
            'activity_names': activity_names,
            'activity_budgets': activity_budgets,
            'activity_progress': activity_progress,
            'cpi_data': cpi_data,
            'spi_data': spi_data,
            'evm_pv': evm_pv,
            'evm_ev': evm_ev,
            'evm_ac': evm_ac,
            'evm_dates': evm_dates,
            'completed_tasks': len(completed_tasks),
            'in_progress_tasks': len(in_progress_tasks),
            'overdue_tasks': len(overdue_tasks),
            'total_tasks': len(tasks),
            'monthly_costs': monthly_costs
        })
        
    except Exception as e:
        logger.error(f"خطأ في جلب تفاصيل المشروع {project_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

# app/routes/company_routes.py

@company_bp.route('/project/<int:project_id>/gallery')
@login_required
def project_gallery(project_id):
    """عرض معرض المشروع"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != current_user.org_id and current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    return render_template('company/project_gallery.html', project=project)

# app/routes/company_routes.py

@company_bp.route('/project/<int:project_id>/resource-requests')
@login_required
def project_resource_requests(project_id):
    """عرض طلبات التوريد لمشروع معين"""
    project = Project.query.get_or_404(project_id)
    
    if project.project_manager_id != current_user.id and current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    resource_requests = ResourceRequest.query.filter_by(
        project_id=project_id
    ).order_by(ResourceRequest.created_at.desc()).all()
    
    return render_template(
        'company/resource_requests.html',
        project=project,
        resource_requests=resource_requests
    )

@company_bp.route('/request/<int:request_id>/offersed')
@login_required
def view_request_offer(request_id):
    """عرض عروض أسعار الطلب"""
    resource_request = ResourceRequest.query.get_or_404(request_id)
    
    if resource_request.project.project_manager_id != current_user.id and current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    items = ResourceRequestItem.query.filter_by(request_id=request_id).all()
    
    return render_template(
        'company/request_offers.html',
        requests=resource_request,
        offers=items
    )

@company_bp.route('/api/request/<int:request_id>/offers')
@login_required
def view_request_offerss(request_id):
    """عرض عروض أسعار الطلب"""
    resource_request = ResourceRequest.query.get_or_404(request_id)
    
    if resource_request.project.project_manager_id != current_user.id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    items = ResourceRequestItem.query.filter_by(request_id=request_id).all()
    
    offers_data = []
    for item in items:
        # جلب سجل العروض باستخدام query مباشر
        history = ResourceOfferHistory.query.filter_by(
            request_item_id=item.id
        ).order_by(ResourceOfferHistory.submitted_at.desc()).all()
        
        offers_data.append({
            'id': item.id,
            'resource_name': item.resource_name,
            'required_quantity': item.required_quantity,
            'unit': item.unit,
            'offer_price': item.offer_price,
            'offer_currency': item.offer_currency,
            'offer_notes': item.offer_notes,
            'offer_status': item.offer_status,
            'offer_submitted_at': item.offer_submitted_at.isoformat() if item.offer_submitted_at else None,
            'history': [{
                'price': h.offer_price,
                'currency': h.offer_currency,
                'notes': h.offer_notes,
                'status': h.status,
                'submitted_at': h.submitted_at.isoformat(),
                'submitted_by': h.submitter.full_name if h.submitter else 'غير معروف'
            } for h in history]
        })
    
    return jsonify({
        'success': True,
        'offers': offers_data
    })


# app/routes/company_routes.py

@company_bp.route('/api/offer/<int:item_id>/approve', methods=['POST'])
@login_required
def approve_offer(item_id):
    """الموافقة على عرض سعر"""
    try:
        item = ResourceRequestItem.query.get_or_404(item_id)
        resource_request = item.request
        
        # التحقق من الصلاحية
        if resource_request.project.project_manager_id != current_user.id and current_user.role != 'org_admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        action = data.get('action')
        notes = data.get('notes', '')
        
        if action == 'approve':
            item.offer_status = 'approved'
            
            # تحديث سجل العرض
            history = ResourceOfferHistory.query.filter_by(
                request_item_id=item.id,
                status='pending'
            ).first()
            
            if history:
                history.status = 'approved'
                history.approved_by = current_user.id
                history.approved_at = datetime.utcnow()
                history.approval_notes = notes
            
            db.session.commit()
            
            # إرسال إشعار للمورد بقبول العرض
            try:
                NotificationService.offer_approved(item, resource_request, current_user, notes)
            except Exception as e:
                print(f"خطأ في إرسال الإشعار: {str(e)}")
            
            return jsonify({'success': True, 'message': 'تم اعتماد عرض السعر بنجاح'})
        
        elif action == 'reject':
            item.offer_status = 'rejected'
            
            # تحديث سجل العرض
            history = ResourceOfferHistory.query.filter_by(
                request_item_id=item.id,
                status='pending'
            ).first()
            
            if history:
                history.status = 'rejected'
                history.approved_by = current_user.id
                history.approved_at = datetime.utcnow()
                history.approval_notes = notes
            
            db.session.commit()
            
            # إرسال إشعار للمورد برفض العرض
            try:
                NotificationService.offer_rejected(item, resource_request, current_user, notes)
            except Exception as e:
                print(f"خطأ في إرسال الإشعار: {str(e)}")
            
            return jsonify({'success': True, 'message': 'تم رفض عرض السعر'})
        
        return jsonify({'error': 'إجراء غير صالح'}), 400
        
    except Exception as e:
        db.session.rollback()
        print(f"خطأ في approve_offer: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
# app/routes/company_routes.py

@company_bp.route('/api/request/<int:request_id>/send-reminder', methods=['POST'])
@login_required
def send_reminder_to_supplier(request_id):
    """إرسال تذكير للمورد بتسريع جلب المواد"""
    try:
        resource_request = ResourceRequest.query.get_or_404(request_id)
        sender=current_user.org_id
        # التحقق من الصلاحية
        if resource_request.project.project_manager_id != current_user.id and current_user.role != 'org_admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        # التحقق من حالة الطلب
        if resource_request.status in ['completed', 'cancelled']:
            return jsonify({'error': 'لا يمكن إرسال تذكير لطلب مكتمل أو ملغي'}), 400
        
        # تحديث سجل التذكير
        resource_request.last_reminder_sent = datetime.utcnow()
        resource_request.reminder_count = (resource_request.reminder_count or 0) + 1
        
        # حساب الكميات المتبقية
        remaining_items = []
        for item in resource_request.items:
            if item.remaining_quantity > 0:
                remaining_items.append({
                    'name': item.resource_name,
                    'remaining': item.remaining_quantity,
                    'unit': item.unit,
                    'required_date': resource_request.required_date.strftime('%Y-%m-%d') if resource_request.required_date else 'غير محدد'
                })
        
        db.session.commit()
        if not remaining_items:
            return jsonify({'error': 'لا توجد مواد متبقية لإرسال تذكير'}), 400
        # إرسال إشعار تذكير للمورد
        NotificationService.send_reminder_to_supplier(resource_request, remaining_items)
        
        return jsonify({
            'success': True,
            'message': f'تم إرسال تذكير للمورد {resource_request.supplier.full_name}',
            'reminder_count': resource_request.reminder_count,
            'last_reminder': resource_request.last_reminder_sent.isoformat()
        })
    
    except Exception as e:
        db.session.rollback()
        print(f"خطأ في approve_offer: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@company_bp.route('/api/request/<int:request_id>/remaining-items')
@login_required
def get_remaining_items(request_id):
    """جلب الكميات المتبقية للطلب"""
    resource_request = ResourceRequest.query.get_or_404(request_id)
    
    # التحقق من الصلاحية
    if resource_request.project.project_manager_id != current_user.id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    remaining_items = []
    for item in resource_request.items:
        if item.remaining_quantity > 0:
            remaining_items.append({
                'id': item.id,
                'name': item.resource_name,
                'code': item.resource_code,
                'required_quantity': item.required_quantity,
                'delivered_quantity': item.delivered_quantity,
                'remaining_quantity': item.remaining_quantity,
                'unit': item.unit,
                'offer_price': item.offer_price,
                'offer_currency': item.offer_currency,
                'offer_status': item.offer_status,
                'is_completed': item.is_completed
            })
    
    return jsonify({
        'success': True,
        'remaining_items': remaining_items,
        'total_remaining': sum(i['remaining_quantity'] for i in remaining_items),
        'items_count': len(remaining_items),
        'required_date': resource_request.required_date.strftime('%Y-%m-%d') if resource_request.required_date else None
    })
def get_monthly_costs(project_id):
    """جلب التكاليف الشهرية للمشروع"""
    from app.models.finance_models import Invoice, Payment
    from datetime import datetime, timedelta
    
    monthly_costs = []
    now = datetime.now()
    
    for i in range(6):
        month_date = now - timedelta(days=30 * i)
        month_name = month_date.strftime('%Y-%m')
        
        # جلب المصروفات الشهرية
        expenses = ActivityExpense.query.filter(
            ActivityExpense.activity_id.in_(
                db.session.query(Activity.id).filter(Activity.project_id == project_id)
            ),
            ActivityExpense.expense_date >= month_date.replace(day=1),
            ActivityExpense.expense_date <= month_date.replace(day=28) + timedelta(days=4)
        ).all()
        
        total = sum(e.amount for e in expenses)
        
        monthly_costs.append({
            'month': month_name,
            'amount': total
        })
    
    return monthly_costs[::-1]


def get_activity_status_text(status):
    """ترجمة حالة النشاط"""
    status_map = {
        'not_started': 'لم يبدأ',
        'in_progress': 'قيد التنفيذ',
        'completed': 'مكتمل',
        'suspended': 'معلق',
        'delayed': 'متأخر'
    }
    return status_map.get(status, status)


def get_activity_status_color(status):
    """لون حالة النشاط"""
    color_map = {
        'not_started': 'secondary',
        'in_progress': 'primary',
        'completed': 'success',
        'suspended': 'warning',
        'delayed': 'danger'
    }
    return color_map.get(status, 'secondary')
  
@company_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """الصفحة الشخصية"""
    if request.method == 'POST':
        try:
            user = current_user
            
            # تحديث البيانات الأساسية
            user.full_name = request.form.get('full_name', user.full_name)
            user.phone = request.form.get('phone', user.phone)
            user.mobile = request.form.get('mobile', user.mobile)
            user.job_title = request.form.get('job_title', user.job_title)
            if hasattr(user, 'job_title_ar'):
                user.job_title_ar = request.form.get('job_title_ar', getattr(user, 'job_title_ar', ''))
            
            # تحديث كلمة المرور إذا تم إدخالها
            new_password = request.form.get('new_password')
            if new_password:
                confirm_password = request.form.get('confirm_password')
                current_password = request.form.get('current_password')
                
                if not user.check_password(current_password):
                    flash('كلمة المرور الحالية غير صحيحة', 'danger')
                elif new_password != confirm_password:
                    flash('كلمة المرور غير متطابقة', 'danger')
                else:
                    user.set_password(new_password)
                    flash('تم تحديث كلمة المرور بنجاح', 'success')
            
            db.session.commit()
            flash('تم تحديث البيانات بنجاح', 'success')
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('auth/profile.html', user=current_user)



@company_bp.route('/hierarchy')
@login_required
def eps_hierarchy():
    """عرض هيكل المؤسسة (EPS) بشكل شجري مثل Primavera"""
    if current_user.role not in ['org_admin', 'project_manager']:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('company.dashboard'))
    
    return render_template('company/hierarchy.html')


@company_bp.route('/api/tree')
@login_required
def get_eps_tree():
    """API لجلب هيكل المؤسسة بشكل شجري (بدون تفاصيل إضافية)"""
    try:
        # جلب جميع فروع EPS
        eps_nodes = EPS.query.filter_by(
            org_id=current_user.org_id,
            is_active=True
        ).order_by(EPS.level, EPS.eps_code).all()
        
        # بناء الشجرة
        tree = []
        eps_map = {node.id: node for node in eps_nodes}
        
        # إضافة عقد EPS
        for node in eps_nodes:
            node_data = {
                'id': f"eps_{node.id}",
                'text': f"{node.eps_code} - {node.name}",
                'type': 'eps',
                'children': []
            }
            
            if node.parent_id is None:
                tree.append(node_data)
            else:
                parent = eps_map.get(node.parent_id)
                if parent:
                    add_child_to_tree(tree, f"eps_{parent.id}", node_data)
        
        # إضافة المشاريع تحت كل EPS
        projects = Project.query.filter_by(org_id=current_user.org_id).all()
        for project in projects:
            if project.eps_id:
                project_data = {
                    'id': f"project_{project.id}",
                    'text': f"{project.project_code} - {project.name}",
                    'type': 'project',
                    'children': []
                }
                
                # إضافة WBS تحت المشروع
                wbs_nodes = WBS.query.filter_by(
                    project_id=project.id,
                    parent_id=None
                ).order_by(WBS.wbs_code).all()
                
                for wbs in wbs_nodes:
                    wbs_data = build_wbs_tree(wbs)
                    project_data['children'].append(wbs_data)
                
                # إضافة المشروع إلى الـ EPS المناسب
                add_child_to_tree(tree, f"eps_{project.eps_id}", project_data)
        
        return jsonify({'success': True, 'tree': tree})
        
    except Exception as e:
        logger.error(f"خطأ في جلب هيكل المؤسسة: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


def build_wbs_tree(wbs_node):
    """بناء شجرة WBS بشكل متكرر (بدون تفاصيل إضافية)"""
    wbs_data = {
        'id': f"wbs_{wbs_node.id}",
        'text': f"{wbs_node.wbs_code} - {wbs_node.name}",
        'type': 'wbs',
        'children': []
    }
    
    # إضافة الأنشطة تحت WBS
    activities = Activity.query.filter_by(
        wbs_id=wbs_node.id
    ).order_by(Activity.activity_id).all()
    
    for activity in activities:
        activity_data = {
            'id': f"activity_{activity.id}",
            'text': f"{activity.activity_id} - {activity.activity_name}",
            'type': 'activity',
            'children': []
        }
        
        # إضافة المهام تحت النشاط
        tasks = Task.query.filter_by(
            activity_id=activity.id
        ).order_by(Task.task_code).all()
        
        for task in tasks:
            task_data = {
                'id': f"task_{task.id}",
                'text': f"{task.task_code} - {task.task_name}",
                'type': 'task',
                'children': []
            }
            activity_data['children'].append(task_data)
        
        wbs_data['children'].append(activity_data)
    
    # إضافة الـ WBS الفرعية
    children_wbs = WBS.query.filter_by(
        parent_id=wbs_node.id
    ).order_by(WBS.wbs_code).all()
    
    for child in children_wbs:
        wbs_data['children'].append(build_wbs_tree(child))
    
    return wbs_data


def add_child_to_tree(tree, parent_id, child_data):
    """إضافة عنصر كطفل لعقدة محددة في الشجرة"""
    for node in tree:
        if node['id'] == parent_id:
            node['children'].append(child_data)
            return True
        if node['children']:
            if add_child_to_tree(node['children'], parent_id, child_data):
                return True
    return False

@company_bp.route('/project/templates')
@login_required
def list_templates():
    """عرض قائمة القوالب المتاحة للتحميل"""
    from app.services.template_generator import ProjectTemplateGenerator
    
    generator = ProjectTemplateGenerator()
    formats = generator.get_available_formats()
    
    return render_template('projects/templates_list.html', formats=formats,now=datetime.utcnow())


@company_bp.route('/project/template/download/<format>')
@login_required
def download_template(format):
    """تحميل قالب بالصيغة المطلوبة"""
    from app.services.template_generator import ProjectTemplateGenerator
    
    try:
        include_examples = request.args.get('examples', 'true').lower() == 'true'
        language = request.args.get('lang', 'ar')
        
        generator = ProjectTemplateGenerator()
        result = generator.generate_template(format, include_examples, language)
        
        if result['success']:
            return send_file(
                result['filepath'],
                as_attachment=True,
                download_name=result['filename'],
                mimetype=_get_mimetype(format)
            )
        else:
            flash('حدث خطأ في توليد القالب', 'danger')
            return redirect(url_for('list_templates'))
            
    except Exception as e:
        flash(f'خطأ: {str(e)}', 'danger')
        return redirect(url_for('list_templates'))


@company_bp.route('/project/template/preview/<format>')
@login_required
def preview_template(format):
    """معاينة القالب قبل التحميل"""
    from app.services.template_generator import ProjectTemplateGenerator
    
    generator = ProjectTemplateGenerator()
    result = generator.generate_template(format, include_examples=True)
    
    return render_template('projects/template_preview.html', 
                        template=result,
                        format=format,now=datetime.utcnow())


def _get_mimetype(format: str) -> str:
    """الحصول على MIME type للصيغة"""
    mimetypes = {
        'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'word': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'csv': 'text/csv',
        'json': 'application/json',
        'pdf': 'application/pdf',
        'html': 'text/html'
    }
    return mimetypes.get(format, 'application/octet-stream')
# ============================================
# إدارة المستخدمين
# ============================================

@company_bp.route('/users')
@login_required
@org_admin_required
def users():
    """قائمة المستخدمين"""
    company_id = current_user.org_id
    
    # معاملات التصفية
    role = request.args.get('role', 'all')
    status = request.args.get('status', 'all')
    dept_id = request.args.get('dept_id', 'all')
    search = request.args.get('search', '')
    
    query = User.query.filter_by(org_id=company_id)
    
    if role != 'all':
        query = query.filter_by(role=role)
    if status == 'active':
        query = query.filter_by(is_user_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_user_active=False)
    if dept_id != 'all':
        query = query.filter_by(dept_id=dept_id)
    if search:
        query = query.filter(
            (User.full_name.contains(search)) |
            (User.email.contains(search)) |
            (User.username.contains(search))
        )
    
    users = query.order_by(User.created_at.desc()).all()
    
    # إحصائيات المستخدمين
    user_stats = {
        'total': User.query.filter_by(org_id=company_id).count(),
        'admins': User.query.filter_by(org_id=company_id, role='org_admin').count(),
        'managers': User.query.filter_by(org_id=company_id, role='project_manager').count(),
        'supervisors': User.query.filter_by(org_id=company_id, role='supervisor').count(),
        'employees': User.query.filter_by(org_id=company_id, role='employee').count(),
        'active': User.query.filter_by(org_id=company_id, is_user_active=True).count(),
        'inactive': User.query.filter_by(org_id=company_id, is_user_active=False).count()
    }
    
    # الأقسام للتصفية
    departments = Department.query.filter_by(org_id=company_id).all()
    
    return render_template('company/users/index.html',
                         users=users,
                         user_stats=user_stats,
                         departments=departments,
                         filters={'role': role, 'status': status, 'dept_id': dept_id, 'search': search})

@company_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
@org_admin_required
# @role_required('org_admin', 'project_manager')  # أدوار محددة
def create_user():
    """إنشاء مستخدم جديد"""
    
    company_id = current_user.org_id
    
    if request.method == 'POST':
        try:
            # التحقق من الحد الأقصى
            if g.company.current_users >= g.company.max_users:
                flash('لقد تجاوزت الحد الأقصى لعدد المستخدمين المسموح به', 'danger')
                return redirect(url_for('company.users'))
            
            # التحقق من عدم تكرار البريد
            if User.query.filter_by(org_id=company_id, email=request.form.get('email')).first():
                flash('البريد الإلكتروني مسجل مسبقاً لهذه الشركة', 'danger')
                return redirect(url_for('company.create_user'))
            
            # إنشاء المستخدم
            user = User(
                org_id=company_id,
                username=request.form.get('username'),
                email=request.form.get('email'),
                full_name=request.form.get('full_name'),
                phone=request.form.get('phone'),
                mobile=request.form.get('mobile'),
                job_title=request.form.get('job_title'),
                employee_id=request.form.get('employee_id'),
                role=request.form.get('role', 'employee'),
                dept_id=request.form.get('dept_id') or None,
                is_user_active=bool(request.form.get('is_user_active')),
                is_verified=bool(request.form.get('is_verified')),
                created_by=current_user.id
            )
            
            # تعيين كلمة المرور
            password = request.form.get('password', 'Password123!')
            user.set_password(password)
            
            # تعيين الصلاحيات حسب الدور
            if user.role == 'project_manager':
                user.permissions = {
                    'view_projects': True,
                    'create_tasks': True,
                    'approve_expenses': False,
                    'manage_users': False,
                    'view_reports': True,
                    'upload_documents': True,
                    'manage_projects': True
                }
            elif user.role == 'supervisor':
                user.permissions = {
                    'view_projects': True,
                    'create_tasks': True,
                    'approve_expenses': False,
                    'manage_users': False,
                    'view_reports': True,
                    'upload_documents': True
                }
            elif user.role == 'employee':
                user.permissions = {
                    'view_projects': True,
                    'create_tasks': False,
                    'approve_expenses': False,
                    'manage_users': False,
                    'view_reports': True,
                    'upload_documents': False
                }
            
            db.session.add(user)
            db.session.commit()
            
            # تحديث عداد المستخدمين
            g.company.increment_usage('users')
            db.session.commit()
            
            # إنشاء إشعار
            NotificationService.user_registered(user)
            # notification = Notification(
            #     user_id=user.id,
            #     title='مرحباً بك في النظام',
            #     message=f'تم إنشاء حسابك بنجاح بواسطة مدير الشركة. يمكنك الدخول باستخدام بريدك الإلكتروني وكلمة المرور.',
            #     notification_type='welcome',
            #     created_by=current_user.id
            # )
            # db.session.add(notification)
            # db.session.commit()
            
            flash(f'تم إنشاء المستخدم {user.full_name} بنجاح', 'success')
            return redirect(url_for('company.view_user', user_id=user.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الأقسام المتاحة
    departments = Department.query.filter_by(org_id=company_id, is_active=True).all()
    
    return render_template('company/users/create.html', departments=departments)

@company_bp.route('/users/<int:user_id>/approve', methods=['POST'])
@login_required
def approve_user(user_id):
    """الموافقة على مستخدم"""
    user = User.query.get_or_404(user_id)
    
    if user.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    user.is_verified = True
    user.is_user_active = True
    db.session.commit()
    
    # إضافة إشعار موافقة
    NotificationService.user_approved(user, current_user)
    
    return jsonify({'success': True, 'message': 'تمت الموافقة على المستخدم'})

@company_bp.route('/users/<int:user_id>')
@login_required
@org_admin_required
def view_user(user_id):
    """عرض تفاصيل المستخدم"""
    
    user = User.query.get_or_404(user_id)
    
    # التحقق من أن المستخدم في نفس الشركة
    if user.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.users'))
    
    # إحصائيات المستخدم
    stats = {
        'managed_projects': Project.query.filter_by(project_manager_id=user_id).count(),
        'supervised_tasks': Task.query.filter_by(supervisor_id=user_id).count(),
        'delegate_tasks': Task.query.filter_by(delegate_id=user_id).count(),
        'assigned_tasks': TaskAssignment.query.filter_by(user_id=user_id).count() if 'TaskAssignment' in globals() else 0,
        'completed_tasks': Task.query.filter_by(supervisor_id=user_id, status='completed').count()
    }
    
    # آخر نشاط
    recent_activity = {
        'projects': Project.query.filter_by(checked_out_by=user_id).order_by(Project.updated_at.desc()).limit(3).all(),
        'tasks': Task.query.filter(
            (Task.supervisor_id == user_id) | (Task.delegate_id == user_id)
        ).order_by(Task.updated_at.desc()).limit(5).all()
    }
    
    return render_template('company/users/view.html',
                         user=user,
                         stats=stats,
                         recent_activity=recent_activity)

@company_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@org_admin_required
def edit_user(user_id):
    """تعديل بيانات المستخدم"""
    
    user = User.query.get_or_404(user_id)
    
    if user.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.users'))
    
    if request.method == 'POST':
        try:
            # تحديث البيانات الأساسية
            user.full_name = request.form.get('full_name', user.full_name)
            user.email = request.form.get('email', user.email)
            user.phone = request.form.get('phone', user.phone)
            user.mobile = request.form.get('mobile', user.mobile)
            user.job_title = request.form.get('job_title', user.job_title)
            user.employee_id = request.form.get('employee_id', user.employee_id)
            user.role = request.form.get('role', user.role)
            user.dept_id = request.form.get('dept_id') or None
            user.is_user_active = bool(request.form.get('is_user_active'))
            user.is_verified = bool(request.form.get('is_verified'))
            
            # تحديث الصلاحيات إذا تم تغيير الدور
            if user.role == 'project_manager':
                user.permissions.update({
                    'manage_projects': True,
                    'create_tasks': True
                })
            
            # تغيير كلمة المرور إذا تم إدخالها
            new_password = request.form.get('new_password')
            if new_password:
                user.set_password(new_password)
            
            db.session.commit()
            flash('تم تحديث بيانات المستخدم بنجاح', 'success')
            return redirect(url_for('company.view_user', user_id=user.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    departments = Department.query.filter_by(org_id=current_user.org_id, is_active=True).all()
    
    return render_template('company/users/edit.html', user=user, departments=departments)

@company_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@org_admin_required
def delete_user(user_id):
    """حذف مستخدم"""
    
    user = User.query.get_or_404(user_id)
    
    if user.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if user.id == current_user.id:
        return jsonify({'error': 'لا يمكن حذف حسابك الخاص'}), 400
    
    try:
        # حذف المستخدم
        db.session.delete(user)
        db.session.commit()
        
        # تحديث عداد المستخدمين
        g.company.decrement_usage('users')
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم حذف المستخدم بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@company_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@org_admin_required
def toggle_user_status(user_id):
    """تفعيل/تعطيل المستخدم"""
    
    user = User.query.get_or_404(user_id)
    
    if user.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    user.is_user_active = not user.is_user_active
    db.session.commit()
    
    status = 'مفعل' if user.is_user_active else 'معطل'
    return jsonify({'success': True, 'message': f'تم {status} المستخدم بنجاح'})

@company_bp.route('/users/roles')
@login_required
@org_admin_required
def manage_roles():
    """إدارة الأدوار والصلاحيات"""
    
    # قائمة الأدوار المتاحة
    roles = [
        {'id': 'org_admin', 'name': 'مدير الشركة', 'description': 'صلاحيات كاملة على جميع أقسام الشركة'},
        {'id': 'project_manager', 'name': 'مدير مشروع', 'description': 'إدارة المشاريع والمهام'},
        {'id': 'supervisor', 'name': 'مشرف', 'description': 'الإشراف على المهام والمناديب'},
        {'id': 'delegate', 'name': 'مندوب', 'description': 'تنفيذ المهام الموكلة'},
        {'id': 'employee', 'name': 'موظف', 'description': 'تنفيذ المهام المعينة'}
    ]
    
    # قائمة الصلاحيات المتاحة
    permissions = [
        {'id': 'view_projects', 'name': 'عرض المشاريع', 'category': 'المشاريع'},
        {'id': 'create_projects', 'name': 'إنشاء مشاريع', 'category': 'المشاريع'},
        {'id': 'edit_projects', 'name': 'تعديل المشاريع', 'category': 'المشاريع'},
        {'id': 'delete_projects', 'name': 'حذف المشاريع', 'category': 'المشاريع'},
        {'id': 'view_tasks', 'name': 'عرض المهام', 'category': 'المهام'},
        {'id': 'create_tasks', 'name': 'إنشاء مهام', 'category': 'المهام'},
        {'id': 'assign_tasks', 'name': 'تعيين المهام', 'category': 'المهام'},
        {'id': 'view_reports', 'name': 'عرض التقارير', 'category': 'التقارير'},
        {'id': 'export_data', 'name': 'تصدير البيانات', 'category': 'التقارير'},
        {'id': 'upload_documents', 'name': 'رفع المستندات', 'category': 'المستندات'},
        {'id': 'manage_users', 'name': 'إدارة المستخدمين', 'category': 'المستخدمين'},
        {'id': 'approve_expenses', 'name': 'الموافقة على المصروفات', 'category': 'المالية'}
    ]
    
    return render_template('company/users/roles.html', roles=roles, permissions=permissions)

# ============================================
# إدارة الأقسام
# ============================================

@company_bp.route('/departments')
@login_required
@org_admin_required
def departments():
    """قائمة الأقسام"""
    
    departments = Department.query.filter_by(
        org_id=current_user.org_id
    ).order_by(Department.created_at.desc()).all()
    
    return render_template('company/departments/index.html', departments=departments)

@company_bp.route('/departments/create', methods=['GET', 'POST'])
@login_required
@org_admin_required
def create_department():
    """إنشاء قسم جديد"""
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار رمز القسم
            if Department.query.filter_by(
                org_id=current_user.org_id,
                dept_code=request.form.get('dept_code')
            ).first():
                flash('رمز القسم موجود مسبقاً', 'danger')
                return redirect(url_for('company.create_department'))
            
            department = Department(
                org_id=current_user.org_id,
                dept_code=request.form.get('dept_code'),
                name=request.form.get('name'),
                description=request.form.get('description'),
                parent_id=request.form.get('parent_id') or None,
                manager_id=request.form.get('manager_id') or None,
                budget=float(request.form.get('budget', 0)),
                is_active=bool(request.form.get('is_active'))
            )
            
            db.session.add(department)
            db.session.commit()
            
            flash('تم إنشاء القسم بنجاح', 'success')
            return redirect(url_for('company.view_department', dept_id=department.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الأقسام الرئيسية
    parent_departments = Department.query.filter_by(
        org_id=current_user.org_id,
        parent_id=None
    ).all()
    
    # المدراء المحتملين
    managers = User.query.filter(
    User.org_id == current_user.org_id,
    User.role.in_(['org_admin', 'project_manager']),
    User.is_user_active == True
).all()
    
    return render_template('company/departments/create.html',
                         parent_departments=parent_departments,
                         managers=managers)
@company_bp.route('/departments/<int:dept_id>/edit', methods=['GET', 'POST'])
@login_required
@org_admin_required
def edit_department(dept_id):
    """تعديل بيانات القسم"""
    
    department = Department.query.get_or_404(dept_id)
    
    # التحقق من أن القسم يتبع نفس الشركة
    if department.org_id != current_user.org_id:
        flash('غير مصرح بالوصول إلى هذا القسم', 'danger')
        return redirect(url_for('company.departments'))
    
    if request.method == 'POST':
        try:
            # التحقق من عدم تكرار رمز القسم (إذا تم تغييره)
            new_code = request.form.get('dept_code')
            if new_code != department.dept_code:
                existing = Department.query.filter(
                    Department.org_id == current_user.org_id,
                    Department.dept_code == new_code,
                    Department.id != dept_id
                ).first()
                if existing:
                    flash('رمز القسم موجود مسبقاً', 'danger')
                    return redirect(url_for('company.edit_department', dept_id=dept_id))
            
            # تحديث البيانات الأساسية
            department.dept_code = request.form.get('dept_code', department.dept_code)
            department.name = request.form.get('name', department.name)
            department.description = request.form.get('description', department.description)
            department.budget = float(request.form.get('budget', department.budget or 0))
            
            # تحديث العلاقات
            department.parent_id = request.form.get('parent_id') or None
            department.manager_id = request.form.get('manager_id') or None
            
            # تحديث الحالة
            department.is_active = bool(request.form.get('is_active'))
            
            # التحقق من عدم جعل القسم أباً لنفسه
            if department.parent_id == department.id:
                flash('لا يمكن جعل القسم تابعاً لنفسه', 'danger')
                return redirect(url_for('company.edit_department', dept_id=dept_id))
            
            # التحقق من عدم وجود دورة في الشجرة (إذا كان القسم له أب)
            if department.parent_id:
                # التحقق من أن الأب ليس من أحفاد القسم
                parent = Department.query.get(department.parent_id)
                if parent and parent.is_descendant_of(department):
                    flash('لا يمكن جعل هذا القسم تابعاً لأحد فروعه', 'danger')
                    return redirect(url_for('company.edit_department', dept_id=dept_id))
            
            db.session.commit()
            
            # إنشاء إشعار للتغيير
            notification = Notification(
                user_id=current_user.id,
                title='تم تحديث القسم',
                message=f'تم تحديث بيانات القسم {department.name}',
                notification_type='department_updated',
                created_by=current_user.id
            )
            db.session.add(notification)
            db.session.commit()
            
            flash('تم تحديث بيانات القسم بنجاح', 'success')
            return redirect(url_for('company.view_department', dept_id=department.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الأقسام الرئيسية (باستثناء القسم الحالي وأقسامه الفرعية)
    parent_departments = Department.query.filter(
        Department.org_id == current_user.org_id,
        Department.id != dept_id,
        Department.parent_id == None
    ).all()
    
    # المدراء المحتملين
    managers = User.query.filter(
        User.org_id == current_user.org_id,
        User.role.in_(['org_admin', 'project_manager']),
        User.is_user_active == True
    ).all()
    
    return render_template('company/departments/edit.html',
                         department=department,
                         parent_departments=parent_departments,
                         managers=managers)

@company_bp.route('/departments/<int:dept_id>')
@login_required
@org_admin_required
def view_department(dept_id):
    """عرض تفاصيل القسم"""
    
    department = Department.query.get_or_404(dept_id)
    
    if department.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.departments'))
    
    # موظفو القسم
    employees = department.employees
    
    # الأقسام الفرعية
    sub_departments = department.sub_departments
    
    # المشاريع المرتبطة
    projects = Project.query.join(User).filter(
        User.dept_id == dept_id
    ).distinct().all()
    
    # إحصائيات القسم
    stats = {
        'employees_count': len(employees),
        'sub_depts_count': len(sub_departments),
        'projects_count': len(projects),
        'budget_used': sum(p.contract_value for p in projects if p.contract_value)
    }
    
    return render_template('company/departments/view.html',
                         department=department,
                         employees=employees,
                         sub_departments=sub_departments,
                         projects=projects,
                         stats=stats)

# ============================================
# إدارة المشاريع
# ============================================
@company_bp.route('/request/<int:request_id>/deliveries')
@login_required
def request_deliveries(request_id):
    """عرض تسليمات طلب معين"""
    request_obj = ResourceRequest.query.get_or_404(request_id)
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin', 'project_manager'] and request_obj.supplier_id != current_user.id:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('company.dashboard'))
    
    deliveries = ResourceDelivery.query.filter_by(request_id=request_id).order_by(ResourceDelivery.delivery_date.desc()).all()
    items_status = ResourceRequestItem.query.filter_by(request_id=request_id).all()
    
    return render_template('delivery/request_deliveries.html',
                         requests=request_obj,
                         deliveries=deliveries,
                         items_status=items_status,
                         now=datetime.now())
@company_bp.route('/<int:delivery_id>/confirm', methods=['POST'])
@login_required
def confirm_delivery(delivery_id):
    """تأكيد أو رفض تسليم (للمشرف أو مدير المشروع)"""
    data = request.get_json()
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin', 'project_manager']:
        return jsonify({'success': False, 'error': 'غير مصرح بالتأكيد'}), 403
    
    service = ResourceDeliveryService()
    result = service.confirm_delivery(delivery_id, current_user.id, data)
    
    return jsonify(result)

@company_bp.route('/<int:delivery_id>')
@login_required
def view_delivery(delivery_id):
    """عرض ت فاصيل تسليم"""
    service = ResourceDeliveryService()
    result = service.get_delivery_details(delivery_id)
    
    if not result['success']:
        flash(result['error'], 'danger')
        return redirect(url_for('company.dashboard'))
    
    return render_template('delivery/delivery_detail.html',
                         delivery=result['delivery'],
                         updates=result['updates'],
                         now=datetime.now())
@company_bp.route('/request/<int:request_id>/status')
@login_required
def request_status(request_id):
    """عرض حالة كميات الموارد المطلوبة"""
    service = ResourceDeliveryService()
    result = service.get_request_items_status(request_id)
    
    if not result['success']:
        return jsonify(result), 404
    
    return render_template('delivery/request_status.html',
                         request_id=request_id,
                         items=result['items'],
                         now=datetime.now())

# أضف هذه المسارات في company_routes.py

@company_bp.route('/procurement-requests')
@login_required
def procurement_requests_list():
    """عرض جميع طلبات التوريد (المواد والمعدات)"""
    if current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    from app.models import EquipmentRequest, ResourceRequest
    
    # معاملات التصفية
    type_filter = request.args.get('type', 'all')  # all, materials, equipment
    status_filter = request.args.get('status', 'all')
    
    # جلب طلبات المواد
    materials_query = ResourceRequest.query.filter_by(org_id=current_user.org_id)
    if status_filter != 'all':
        materials_query = materials_query.filter_by(status=status_filter)
    materials_requests = materials_query.order_by(ResourceRequest.created_at.desc()).all()
    
    # جلب طلبات المعدات
    equipment_query = EquipmentRequest.query.filter_by(org_id=current_user.org_id)
    if status_filter != 'all':
        equipment_query = equipment_query.filter_by(status=status_filter)
    equipment_requests = equipment_query.order_by(EquipmentRequest.created_at.desc()).all()
    
    # دمج الطلبات مع تحديد النوع
    all_requests = []
    
    for req in materials_requests:
        all_requests.append({
            'id': req.id,
            'type': 'material',
            'type_icon': 'fa-boxes',
            'type_color': 'primary',
            'type_badge': 'مواد',
            'type_badge_class': 'bg-primary',
            'request': req,
            'project_name': req.project.name if req.project else 'غير محدد',
            'project_code': req.project.project_code if req.project else '',
            'supplier_name': req.supplier.full_name if req.supplier else 'غير محدد',
            'required_date': req.required_date,
            'status': req.status,
            'items_count': req.items.count(),
            'total_required': req.total_required_quantity,
            'total_delivered': req.total_delivered_quantity,
            'total_remaining': req.total_remaining_quantity,
            'completion_percentage': req.completion_percentage,
            'created_at': req.created_at,
            'offer_status': any(item.offer_status == 'pending' for item in req.items),
            'has_offers': any(item.offer_price for item in req.items)
        })
    
    for req in equipment_requests:
        all_requests.append({
            'id': req.id,
            'type': 'equipment',
            'type_icon': 'fa-tools',
            'type_color': 'success',
            'type_badge': 'معدات',
            'type_badge_class': 'bg-success',
            'request': req,
            'project_name': req.project.name if req.project else 'غير محدد',
            'project_code': req.project.project_code if req.project else '',
            'supplier_name': req.supplier.full_name if req.supplier else 'غير محدد',
            'required_date': req.required_date,
            'status': req.status,
            'items_count': req.items.count(),
            'total_required': req.total_required_quantity,
            'total_delivered': req.total_delivered_quantity,
            'total_remaining': req.total_remaining_quantity,
            'completion_percentage': req.completion_percentage,
            'created_at': req.created_at,
            'offer_status': any(item.offer_status == 'pending' for item in req.items),
            'has_offers': any(item.offer_price for item in req.items)
        })
    
    # ترتيب حسب تاريخ الإنشاء
    all_requests.sort(key=lambda x: x['created_at'], reverse=True)
    
    # تصفية حسب النوع
    if type_filter == 'materials':
        all_requests = [r for r in all_requests if r['type'] == 'material']
    elif type_filter == 'equipment':
        all_requests = [r for r in all_requests if r['type'] == 'equipment']
    
    # إحصائيات
    stats = {
        'total': len(materials_requests) + len(equipment_requests),
        'materials_total': len(materials_requests),
        'equipment_total': len(equipment_requests),
        'pending': len([r for r in all_requests if r['status'] == 'pending']),
        'started': len([r for r in all_requests if r['status'] == 'started']),
        'completed': len([r for r in all_requests if r['status'] == 'completed']),
        'delayed': len([r for r in all_requests if r['status'] == 'delayed']),
        'pending_offers': len([r for r in all_requests if r.get('offer_status')]),
        'total_value': sum(r['total_required'] for r in all_requests if r['total_required'])
    }
    
    return render_template('company/equipment_requests/index.html',
                         requests=all_requests,
                         stats=stats,
                         type_filter=type_filter,
                         status_filter=status_filter,
                         now=datetime.now())


@company_bp.route('/procurement-request/<int:request_id>/<string:request_type>')
@login_required
def view_procurement_request(request_id, request_type):
    """عرض تفاصيل طلب توريد (مواد أو معدات)"""
    if current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    from app.models import EquipmentRequest, ResourceRequest
    from app.models import EquipmentRequestItem, ResourceRequestItem
    from app.models import EquipmentRequestUpdate, ResourceRequestUpdate
    from app.models import EquipmentDelivery, ResourceDelivery
    
    if request_type == 'material':
        request_obj = ResourceRequest.query.get_or_404(request_id)
        items = ResourceRequestItem.query.filter_by(request_id=request_id).all()
        updates = ResourceRequestUpdate.query.filter_by(request_id=request_id).order_by(ResourceRequestUpdate.updated_at.desc()).all()
        deliveries = ResourceDelivery.query.filter_by(request_id=request_id).order_by(ResourceDelivery.delivery_date.desc()).all()
        type_info = {'name': 'مواد', 'icon': 'fa-boxes', 'color': 'primary', 'type': 'material'}
    else:
        request_obj = EquipmentRequest.query.get_or_404(request_id)
        items = EquipmentRequestItem.query.filter_by(request_id=request_id).all()
        updates = EquipmentRequestUpdate.query.filter_by(request_id=request_id).order_by(EquipmentRequestUpdate.updated_at.desc()).all()
        deliveries = EquipmentDelivery.query.filter_by(request_id=request_id).order_by(EquipmentDelivery.delivery_date.desc()).all()
        type_info = {'name': 'معدات', 'icon': 'fa-tools', 'color': 'success', 'type': 'equipment'}
    
    if request_obj.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.procurement_requests_list'))
    
    return render_template('company/equipment_requests/view.html',
                         requests=request_obj,
                         request_type=request_type,
                         type_info=type_info,
                         items=items,
                         updates=updates,
                         deliveries=deliveries,
                         now=datetime.now())

@company_bp.route('/export-procurement-report')
@login_required
def export_procurement_report():
    """تصدير تقرير طلبات التوريد"""
    if current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    from app.models import EquipmentRequest, ResourceRequest
    import csv
    import io
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # كتابة رؤوس الأعمدة
    writer.writerow(['رقم الطلب', 'النوع', 'المشروع', 'المورد', 'تاريخ الإنشاء', 'تاريخ التسليم', 'الحالة', 'الكمية المطلوبة', 'الكمية المسلمة', 'نسبة الإنجاز'])
    
    # طلبات المواد
    materials = ResourceRequest.query.filter_by(org_id=current_user.org_id).all()
    for req in materials:
        writer.writerow([
            req.id, 'مواد', req.project.name if req.project else '', 
            req.supplier.full_name if req.supplier else '',
            req.created_at.strftime('%Y-%m-%d') if req.created_at else '',
            req.required_date.strftime('%Y-%m-%d') if req.required_date else '',
            req.status, req.total_required_quantity, req.total_delivered_quantity,
            f"{req.completion_percentage:.1f}%"
        ])
    
    # طلبات المعدات
    equipment = EquipmentRequest.query.filter_by(org_id=current_user.org_id).all()
    for req in equipment:
        writer.writerow([
            req.id, 'معدات', req.project.name if req.project else '',
            req.supplier.full_name if req.supplier else '',
            req.created_at.strftime('%Y-%m-%d') if req.created_at else '',
            req.required_date.strftime('%Y-%m-%d') if req.required_date else '',
            req.status, req.total_required_quantity, req.total_delivered_quantity,
            f"{req.completion_percentage:.1f}%"
        ])
    
    output.seek(0)
    filename = f"procurement_requests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename
    )

@company_bp.route('/api/equipment-request/<int:request_id>/offers')
@login_required
def view_equipment_request_offers(request_id):
    """API لعرض عروض أسعار المعدات"""
    from app.models import EquipmentRequest, EquipmentRequestItem, EquipmentOfferHistory
    
    equipment_request = EquipmentRequest.query.get_or_404(request_id)
    
    if equipment_request.org_id != current_user.org_id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    items = EquipmentRequestItem.query.filter_by(request_id=request_id).all()
    
    offers_data = []
    for item in items:
        history = EquipmentOfferHistory.query.filter_by(
            request_item_id=item.id
        ).order_by(EquipmentOfferHistory.submitted_at.desc()).all()
        
        offers_data.append({
            'id': item.id,
            'equipment_name': item.equipment_name,
            'required_quantity': item.required_quantity,
            'unit': item.unit,
            'offer_price': item.offer_price,
            'offer_currency': item.offer_currency,
            'offer_notes': item.offer_notes,
            'offer_status': item.offer_status,
            'offer_submitted_at': item.offer_submitted_at.isoformat() if item.offer_submitted_at else None,
            'history': [{
                'price': h.offer_price,
                'currency': h.offer_currency,
                'notes': h.offer_notes,
                'status': h.status,
                'submitted_at': h.submitted_at.isoformat(),
                'submitted_by': h.submitter.full_name if h.submitter else 'غير معروف'
            } for h in history]
        })
    
    return jsonify({
        'success': True,
        'offers': offers_data
    })


@company_bp.route('/api/equipment-offer/<int:item_id>/approve', methods=['POST'])
@login_required
def approve_equipment_offer(item_id):
    """الموافقة على عرض سعر لمعدة"""
    from app.models import EquipmentRequestItem, EquipmentOfferHistory, EquipmentRequest
    
    try:
        item = EquipmentRequestItem.query.get_or_404(item_id)
        equipment_request = item.request
        
        # التحقق من الصلاحية
        if equipment_request.org_id != current_user.org_id and current_user.role != 'org_admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        action = data.get('action')
        notes = data.get('notes', '')
        
        if action == 'approve':
            item.offer_status = 'approved'
            
            history = EquipmentOfferHistory.query.filter_by(
                request_item_id=item.id,
                status='pending'
            ).first()
            
            if history:
                history.status = 'approved'
                history.approved_by = current_user.id
                history.approved_at = datetime.utcnow()
                history.approval_notes = notes
            
            db.session.commit()
            
            from app.services.notification_service import NotificationService
            NotificationService.equipment_offer_approved(item, equipment_request, current_user, notes)
            
            return jsonify({'success': True, 'message': 'تم اعتماد عرض السعر بنجاح'})
        
        elif action == 'reject':
            item.offer_status = 'rejected'
            
            history = EquipmentOfferHistory.query.filter_by(
                request_item_id=item.id,
                status='pending'
            ).first()
            
            if history:
                history.status = 'rejected'
                history.approved_by = current_user.id
                history.approved_at = datetime.utcnow()
                history.approval_notes = notes
            
            db.session.commit()
            
            from app.services.notification_service import NotificationService
            NotificationService.equipment_offer_rejected(item, equipment_request, current_user, notes)
            
            return jsonify({'success': True, 'message': 'تم رفض عرض السعر'})
        
        return jsonify({'error': 'إجراء غير صالح'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@company_bp.route('/api/equipment-request/<int:request_id>/send-reminder', methods=['POST'])
@login_required
def send_equipment_reminder_to_supplier(request_id):
    """إرسال تذكير للمورد بالمعدات المتبقية"""
    from app.models import EquipmentRequest
    
    try:
        equipment_request = EquipmentRequest.query.get_or_404(request_id)
        
        # التحقق من الصلاحية
        if equipment_request.org_id != current_user.org_id and current_user.role != 'org_admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        # التحقق من حالة الطلب
        if equipment_request.status in ['completed', 'cancelled']:
            return jsonify({'error': 'لا يمكن إرسال تذكير لطلب مكتمل أو ملغي'}), 400
        
        # تحديث سجل التذكير
        equipment_request.last_reminder_sent = datetime.utcnow()
        equipment_request.reminder_count = (equipment_request.reminder_count or 0) + 1
        
        # حساب الكميات المتبقية
        remaining_items = []
        for item in equipment_request.items:
            if item.remaining_quantity > 0:
                remaining_items.append({
                    'name': item.equipment_name,
                    'remaining': item.remaining_quantity,
                    'unit': item.unit,
                    'required_date': equipment_request.required_date.strftime('%Y-%m-%d') if equipment_request.required_date else 'غير محدد'
                })
        
        db.session.commit()
        
        if not remaining_items:
            return jsonify({'error': 'لا توجد معدات متبقية لإرسال تذكير'}), 400
        
        from app.services.notification_service import NotificationService
        NotificationService.send_equipment_reminder_to_supplier(equipment_request, remaining_items)
        
        return jsonify({
            'success': True,
            'message': f'تم إرسال تذكير للمورد {equipment_request.supplier.full_name}',
            'reminder_count': equipment_request.reminder_count,
            'last_reminder': equipment_request.last_reminder_sent.isoformat()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@company_bp.route('/api/equipment-delivery/<int:delivery_id>/confirm', methods=['POST'])
@login_required
def confirm_equipment_delivery(delivery_id):
    """تأكيد أو رفض تسليم المعدات"""
    from app.models import EquipmentDelivery, EquipmentRequest, EquipmentRequestItem, EquipmentDeliveryUpdate
    from app.services.update_service import UpdateService
    from app.services.notification_service import NotificationService
    
    try:
        data = request.get_json()
        action = data.get('action')
        notes = data.get('notes', '')
        equipment_condition = data.get('equipment_condition', 'good')
        serial_numbers = data.get('serial_numbers', [])
        
        delivery = EquipmentDelivery.query.get_or_404(delivery_id)
        equipment_request = delivery.request
        
        # التحقق من الصلاحية
        if equipment_request.org_id != current_user.org_id and current_user.role != 'org_admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        if action == 'confirm':
            delivery.status = 'confirmed'
            delivery.confirmed_by = current_user.id
            delivery.confirmed_at = datetime.utcnow()
            delivery.confirmation_notes = notes
            delivery.equipment_condition = equipment_condition
            delivery.equipment_serial_numbers = serial_numbers
            
            # تحديث حالة الطلب إذا لزم الأمر
            all_completed = all(item.is_completed for item in equipment_request.items)
            if all_completed:
                equipment_request.status = 'completed'
                equipment_request.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            UpdateService.update_equipment_request_metrics(equipment_request.id)
            NotificationService.equipment_delivery_confirmed(delivery, equipment_request, True, notes)
            
            return jsonify({'success': True, 'message': 'تم تأكيد استلام المعدات بنجاح'})
        
        elif action == 'reject':
            if not notes:
                return jsonify({'error': 'الرجاء إدخال سبب الرفض'}), 400
            
            delivery.status = 'rejected'
            delivery.rejection_reason = notes
            delivery.confirmed_by = current_user.id
            delivery.confirmed_at = datetime.utcnow()
            
            # إرجاع الكميات إلى العناصر
            for delivered in delivery.delivered_items:
                item = EquipmentRequestItem.query.get(delivered['item_id'])
                if item:
                    item.delivered_quantity -= delivered['quantity']
                    item.remaining_quantity = item.required_quantity - item.delivered_quantity
                    item.is_completed = False
                    item.updated_at = datetime.utcnow()
            
            # إعادة حالة الطلب إذا لزم الأمر
            if equipment_request.status == 'completed':
                equipment_request.status = 'partially_delivered'
            
            equipment_request.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            NotificationService.equipment_delivery_confirmed(delivery, equipment_request, False, notes)
            
            return jsonify({'success': True, 'message': 'تم رفض التسليم بنجاح'})
        
        return jsonify({'error': 'إجراء غير صالح'}), 400
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
    
@company_bp.route('/projects')
@login_required
def projects():
    """قائمة المشاريع"""
    
    company_id = current_user.org_id
    
    # التصفية حسب الصلاحية
    if current_user.role == 'org_admin':
        projects = Project.query.filter_by(org_id=company_id).all()
    elif current_user.role == 'project_manager':
        projects = Project.query.filter_by(project_manager_id=current_user.id).all()
    else:
        # الموظفين يرون المشاريع المرتبطة بمهامهم
        projects = Project.query.join(Task).filter(
            (Task.supervisor_id == current_user.id) |
            (Task.delegate_id == current_user.id)
        ).distinct().all()
    
    # معاملات التصفية
    status = request.args.get('status', 'all')
    if status != 'all':
        projects = [p for p in projects if p.status == status]
    
    # إحصائيات المشاريع
    stats = {
        'total': len(projects),
        'active': len([p for p in projects if p.status == 'active']),
        'completed': len([p for p in projects if p.status == 'completed']),
        'on_hold': len([p for p in projects if p.status == 'on_hold'])
    }
    
    return render_template('company/projects/index.html', projects=projects, stats=stats)

@company_bp.route('/projects/create', methods=['GET', 'POST'])
@login_required
def create_project():
    """إنشاء مشروع جديد"""
    
    # فقط مدير الشركة أو مدير المشروع يمكنهم إنشاء مشاريع
    if current_user.role not in ['org_admin', 'project_manager']:
        flash('غير مصرح بإنشاء مشاريع', 'danger')
        return redirect(url_for('company.projects'))
    
    if request.method == 'POST':
        try:
            # التحقق من الحد الأقصى
            if g.company.current_projects >= g.company.max_projects:
                flash('لقد تجاوزت الحد الأقصى لعدد المشاريع المسموح به', 'danger')
                return redirect(url_for('company.projects'))
            
            # التحقق من عدم تكرار رمز المشروع
            if Project.query.filter_by(
                org_id=current_user.org_id,
                project_code=request.form.get('project_code')
            ).first():
                flash('رمز المشروع موجود مسبقاً', 'danger')
                return redirect(url_for('company.create_project'))
            
            project = Project(
                org_id=current_user.org_id,
                project_code=request.form.get('project_code'),
                name=request.form.get('name'),
                name_ar=request.form.get('name_ar'),
                description=request.form.get('description'),
                project_manager_id=request.form.get('project_manager_id', current_user.id),
                site_name=request.form.get('site_name'),
                location_address=request.form.get('location_address'),
                contract_value=float(request.form.get('contract_value', 0)),
                planned_start_date=datetime.strptime(
                    request.form.get('planned_start_date'), '%Y-%m-%d'
                ).date(),
                planned_end_date=datetime.strptime(
                    request.form.get('planned_end_date'), '%Y-%m-%d'
                ).date(),
                status=request.form.get('status', 'pending'),
                created_by=current_user.id
            )
            
            db.session.add(project)
            db.session.commit()
            
            # تحديث عداد المشاريع
            g.company.increment_usage('projects')
            db.session.commit()
            
            flash('تم إنشاء المشروع بنجاح', 'success')
            return redirect(url_for('company.view_project', project_id=project.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # مديري المشاريع المحتملين
    project_managers = User.query.filter_by(
        org_id=current_user.org_id,
        role__in=['org_admin', 'project_manager'],
        is_user_active=True
    ).all()
    
    return render_template('company/projects/create.html', project_managers=project_managers)

# @company_bp.route('/projects/<int:project_id>')
# @login_required
# def view_project(project_id):
#     """عرض تفاصيل المشروع"""
    
#     project = Project.query.get_or_404(project_id)
    
#     # التحقق من الصلاحية
#     if not has_project_access(project, current_user):
#         flash('غير مصرح بمشاهدة هذا المشروع', 'danger')
#         return redirect(url_for('company.projects'))
    
#     # مهام المشروع
#     tasks = Task.query.filter_by(project_id=project_id).all()
    
#     # مستندات المشروع
#     documents = ProjectDocument.query.filter_by(project_id=project_id).all()
    
#     # إحصائيات المشروع
#     stats = {
#         'total_tasks': len(tasks),
#         'completed_tasks': len([t for t in tasks if t.status == 'completed']),
#         'in_progress_tasks': len([t for t in tasks if t.status == 'in_progress']),
#         'pending_tasks': len([t for t in tasks if t.status == 'pending']),
#         'progress': project.progress_percentage,
#         'days_remaining': project.get_remaining_days() if hasattr(project, 'get_remaining_days') else 0
#     }
    
#     return render_template('company/projects/view.html',
#                          project=project,
#                          tasks=tasks,
#                          documents=documents,
#                          stats=stats)

def has_project_access(project, user):
    """التحقق من صلاحية الوصول للمشروع"""
    if user.role == 'org_admin':
        return project.org_id == user.org_id
    if user.role == 'project_manager':
        return project.project_manager_id == user.id
    # التحقق من وجود مهام للمستخدم في المشروع
    task_count = Task.query.filter(
        Task.project_id == project.id,
        (Task.supervisor_id == user.id) | (Task.delegate_id == user.id)
    ).count()
    return task_count > 0

# ============================================
# إعدادات الشركة
# ============================================

@company_bp.route('/settings')
@login_required
@org_admin_required
def settings():
    """صفحة إعدادات الشركة الرئيسية"""
    return render_template('company/settings/index.html', company=g.company)

@company_bp.route('/settings/company', methods=['GET', 'POST'])
@login_required
@org_admin_required
def company_settings():
    """إعدادات معلومات الشركة"""
    
    if request.method == 'POST':
        try:
            company = g.company
            
            # تحديث المعلومات الأساسية
            company.name = request.form.get('name', company.name)
            company.name_ar = request.form.get('name_ar', company.name_ar)
            company.description = request.form.get('description', company.description)
            company.address = request.form.get('address', company.address)
            company.phone = request.form.get('phone', company.phone)
            company.email = request.form.get('email', company.email)
            company.website = request.form.get('website', company.website)
            company.tax_number = request.form.get('tax_number', company.tax_number)
            company.commercial_register = request.form.get('commercial_register', company.commercial_register)
            
            # تحديث الإعدادات
            settings = company.settings or {}
            settings['currency'] = request.form.get('currency', settings.get('currency', 'SAR'))
            settings['language'] = request.form.get('language', settings.get('language', 'ar'))
            settings['timezone'] = request.form.get('timezone', settings.get('timezone', 'Asia/Riyadh'))
            settings['date_format'] = request.form.get('date_format', settings.get('date_format', 'dd/MM/yyyy'))
            
            company.settings = settings
            
            db.session.commit()
            flash('تم تحديث معلومات الشركة بنجاح', 'success')
            return redirect(url_for('company.company_settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('company/settings/company_info.html', company=g.company)

@company_bp.route('/settings/upload-logo', methods=['POST'])
@login_required
@org_admin_required
def upload_logo():
    """رفع شعار الشركة"""
    
    if 'logo' not in request.files:
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    file = request.files['logo']
    
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    # التحقق من صيغة الملف
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'svg'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({'error': 'صيغة الملف غير مدعومة'}), 400
    
    try:
        # حفظ الملف
        filename = secure_filename(f"logo_{g.company.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file.filename.rsplit('.', 1)[1]}")
        upload_folder = os.path.join('static', 'uploads', 'logos')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # تحديث مسار الشعار
        g.company.logo_url = url_for('static', filename=f'uploads/logos/{filename}')
        db.session.commit()
        
        return jsonify({'success': True, 'logo_url': g.company.logo_url})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@company_bp.route('/settings/subscription')
@login_required
@org_admin_required
def subscription():
    """صفحة الاشتراك والفواتير"""
    
    from models import Subscription
    
    subscriptions = Subscription.query.filter_by(org_id=current_user.org_id).order_by(
        Subscription.created_at.desc()
    ).all()
    
    return render_template('company/settings/subscription.html',
                         company=g.company,
                         subscriptions=subscriptions)

@company_bp.route('/settings/appearance', methods=['GET', 'POST'])
@login_required
@org_admin_required
def appearance():
    """إعدادات المظهر"""
    
    if request.method == 'POST':
        try:
            # تحديث إعدادات المظهر
            settings = g.company.settings or {}
            settings['theme'] = request.form.get('theme', 'light')
            settings['primary_color'] = request.form.get('primary_color', '#0d6efd')
            settings['sidebar_color'] = request.form.get('sidebar_color', '#212529')
            
            g.company.settings = settings
            db.session.commit()
            
            flash('تم تحديث إعدادات المظهر بنجاح', 'success')
            return redirect(url_for('company.appearance'))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('company/settings/appearance.html', company=g.company)

# ============================================
# التقارير
# ============================================

@company_bp.route('/reports')
@login_required
def reports():
    """صفحة التقارير الرئيسية"""
    return render_template('company/reports/index.html')

@company_bp.route('/reports/projects')
@login_required
def projects_report():
    """تقرير المشاريع"""
    
    company_id = current_user.org_id
    projects = Project.query.filter_by(org_id=company_id).all()
    
    report_data = []
    for project in projects:
        tasks = Task.query.filter_by(project_id=project.id).all()
        report_data.append({
            'name': project.name,
            'code': project.project_code,
            'status': project.status,
            'progress': project.progress_percentage,
            'manager': project.manager.full_name if project.manager else 'غير محدد',
            'start_date': project.planned_start_date,
            'end_date': project.planned_end_date,
            'value': project.contract_value,
            'tasks_count': len(tasks),
            'completed_tasks': len([t for t in tasks if t.status == 'completed'])
        })
    
    return render_template('company/reports/projects.html', report_data=report_data)

@company_bp.route('/reports/tasks')
@login_required
def tasks_report():
    """تقرير المهام"""
    
    company_id = current_user.org_id
    tasks = Task.query.join(Project).filter(Project.org_id == company_id).all()
    
    report_data = []
    for task in tasks:
        report_data.append({
            'name': task.task_name,
            'project': task.project.name if task.project else 'غير محدد',
            'status': task.status,
            'progress': task.progress_percentage,
            'supervisor': task.supervisor.full_name if task.supervisor else 'غير محدد',
            'delegate': task.delegate.full_name if task.delegate else 'غير محدد',
            'start_date': task.planned_start_date,
            'end_date': task.planned_end_date
        })
    
    return render_template('company/reports/tasks.html', report_data=report_data)

@company_bp.route('/reports/users')
@login_required
@org_admin_required
def users_report():
    """تقرير المستخدمين"""
    
    company_id = current_user.org_id
    users = User.query.filter_by(org_id=company_id).all()
    
    report_data = []
    for user in users:
        report_data.append({
            'name': user.full_name,
            'email': user.email,
            'role': user.role,
            'department': user.department.name if user.department else 'غير محدد',
            'is_active': 'نعم' if user.is_user_active else 'لا',
            'last_login': user.last_login,
            'login_count': user.login_count,
            'created_at': user.created_at
        })
    
    return render_template('company/reports/users.html', report_data=report_data)

@company_bp.route('/reports/export/<report_type>')
@login_required
def export_report(report_type):
    """تصدير التقارير"""
    
    # TODO: تنفيذ تصدير التقارير (CSV, Excel, PDF)
    flash('جاري تجهيز التقرير...', 'info')
    return redirect(url_for('company.reports'))

# ============================================
# API Routes
# ============================================

@company_bp.route('/api/dashboard/stats')
@login_required
def api_dashboard_stats():
    """API لإحصائيات لوحة التحكم"""
    
    company_id = current_user.org_id
    
    stats = {
        'users': {
            'total': User.query.filter_by(org_id=company_id).count(),
            'active': User.query.filter_by(org_id=company_id, is_user_active=True).count()
        },
        'projects': {
            'total': Project.query.filter_by(org_id=company_id).count(),
            'active': Project.query.filter_by(org_id=company_id, status='active').count(),
            'completed': Project.query.filter_by(org_id=company_id, status='completed').count()
        },
        'tasks': {
            'total': Task.query.join(Project).filter(Project.org_id == company_id).count(),
            'pending': Task.query.join(Project).filter(
                Project.org_id == company_id,
                Task.status == 'pending'
            ).count(),
            'completed': Task.query.join(Project).filter(
                Project.org_id == company_id,
                Task.status == 'completed'
            ).count()
        }
    }
    
    return jsonify({'success': True, 'stats': stats})

@company_bp.route('/api/users/search')
@login_required
def api_search_users():
    """API للبحث عن المستخدمين"""
    
    query = request.args.get('q', '')
    role = request.args.get('role', 'all')
    
    users_query = User.query.filter_by(org_id=current_user.org_id)
    
    if query:
        users_query = users_query.filter(
            (User.full_name.contains(query)) |
            (User.email.contains(query))
        )
    
    if role != 'all':
        users_query = users_query.filter_by(role=role)
    
    users = users_query.limit(10).all()
    
    results = [{
        'id': u.id,
        'text': f"{u.full_name} ({u.email})",
        'role': u.role
    } for u in users]
    
    return jsonify({'results': results})

@company_bp.route('/api/departments/check-code')
@login_required
@org_admin_required
def check_department_code():
    """التحقق من توفر كود القسم"""
    code = request.args.get('code', '')
    dept_id = request.args.get('dept_id', type=int)
    
    query = Department.query.filter_by(
        org_id=current_user.org_id,
        dept_code=code
    )
    
    if dept_id:
        query = query.filter(Department.id != dept_id)
    
    exists = query.first() is not None
    
    return jsonify({'exists': exists})
@company_bp.route('/projects/<int:project_id>/convert-to-primavera', methods=['POST'])
@login_required
def convert_to_primavera(project_id):
    """تحويل مشروع إلى نظام Primavera"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != current_user.org_id and current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.view_project', project_id=project_id))
    
    # استدعاء API التحويل
    response = requests.post(
        url_for('primavera.convert_project', project_id=project_id, _external=True),
        headers={'X-CSRFToken': request.headers.get('X-CSRFToken')}
    )
    
    if response.status_code == 200:
        flash('تم تحويل المشروع إلى نظام Primavera بنجاح', 'success')
    else:
        flash('حدث خطأ أثناء تحويل المشروع', 'danger')
    
    return redirect(url_for('company.view_project', project_id=project_id))

@company_bp.route('/api/primavera-projects')
@login_required
def api_primavera_projects():
    """API لجلب مشاريع Primavera للوحة التحكم"""
    from app.models.primavera_models import PrimaveraProject,EPS
    
    projects = PrimaveraProject.query.join(EPS).filter(
        EPS.org_id == current_user.org_id
    ).order_by(PrimaveraProject.created_at.desc()).limit(5).all()
    
    return jsonify({
        'success': True,
        'projects': [{
            'id': p.id,
            'name': p.name,
            'total_activities': p.total_activities,
            'critical_activities': p.critical_activities,
            'progress': p.progress_percentage
        } for p in projects]
    })

# في ملف app/routes/employee_routes.py




@company_bp.route('/employee/<int:user_id>')
@login_required
def view_employee(user_id):
    """عرض ملف موظف مع جميع التفاصيل والإحصائيات"""
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin', 'project_manager'] and current_user.id != user_id:
        flash('غير مصرح بالوصول إلى هذه الصفحة', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # جلب بيانات الموظف
    employee = User.query.get_or_404(user_id)
    
    # التحقق من أن الموظف في نفس المؤسسة
    if employee.org_id != current_user.org_id and current_user.role != 'platform_admin':
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # ============================================
    # 1. المعلومات الأساسية
    # ============================================
    basic_info = {
        'id': employee.id,
        'full_name': employee.full_name,
        'email': employee.email,
        'phone': employee.phone,
        'mobile': employee.mobile if hasattr(employee, 'mobile') else None,
        'job_title': employee.job_title,
        'role': employee.role,
        'employee_id': employee.employee_id if hasattr(employee, 'employee_id') else None,
        'national_id': employee.national_id if hasattr(employee, 'national_id') else None,
        'birth_date': employee.birth_date.strftime('%Y-%m-%d') if employee.birth_date else None,
        'hire_date': employee.hire_date.strftime('%Y-%m-%d') if employee.hire_date else None,
        'profile_image': employee.profile_image if hasattr(employee, 'profile_image') else None,
        'is_active': employee.is_user_active if hasattr(employee, 'is_user_active') else employee.is_active,
        'created_at': employee.created_at.strftime('%Y-%m-%d') if employee.created_at else None,
        'last_login': employee.last_login.strftime('%Y-%m-%d %H:%M') if employee.last_login else None,
        'login_count': employee.login_count if hasattr(employee, 'login_count') else 0
    }
    
    # القسم
    if hasattr(employee, 'department') and employee.department:
        basic_info['department'] = {
            'id': employee.department.id,
            'name': employee.department.name,
            'dept_code': employee.department.dept_code if hasattr(employee.department, 'dept_code') else None
        }
    else:
        basic_info['department'] = None
    
    # ============================================
    # 2. إحصائيات المهام
    # ============================================
    
    # المهام التي يشرف عليها
    supervised_tasks = Task.query.filter_by(supervisor_id=user_id).all()
    
    # المهام المفوضة له
    delegated_tasks = Task.query.filter_by(delegate_id=user_id).all()
    
    # المهام المعينة له (من TaskAssignment)
    task_assignments = TaskAssignment.query.filter_by(user_id=user_id).all()
    
    # إحصائيات المهام
    task_stats = {
        'supervised': {
            'total': len(supervised_tasks),
            'pending': len([t for t in supervised_tasks if t.status == 'pending']),
            'in_progress': len([t for t in supervised_tasks if t.status == 'in_progress']),
            'completed': len([t for t in supervised_tasks if t.status == 'completed']),
            'delayed': len([t for t in supervised_tasks if hasattr(t, 'is_delayed') and t.is_delayed])
        },
        'delegated': {
            'total': len(delegated_tasks),
            'pending': len([t for t in delegated_tasks if t.status == 'pending']),
            'in_progress': len([t for t in delegated_tasks if t.status == 'in_progress']),
            'completed': len([t for t in delegated_tasks if t.status == 'completed']),
            'delayed': len([t for t in delegated_tasks if hasattr(t, 'is_delayed') and t.is_delayed])
        },
        'assigned': {
            'total': len(task_assignments),
            'completed': len([a for a in task_assignments if a.status == 'completed']),
            'accepted': len([a for a in task_assignments if a.status == 'accepted']),
            'in_progress': len([a for a in task_assignments if a.status == 'in_progress']),
            'rejected': len([a for a in task_assignments if a.status == 'rejected']),
            'avg_quality': sum([a.quality_rating or 0 for a in task_assignments]) / len(task_assignments) if task_assignments else 0,
            'avg_efficiency': sum([a.efficiency_rating or 0 for a in task_assignments]) / len(task_assignments) if task_assignments else 0
        }
    }
    
    # ============================================
    # 3. المهام الحالية (قيد التنفيذ)
    # ============================================
    current_tasks = []
    
    # المهام التي يشرف عليها
    for task in supervised_tasks:
        if task.status in ['pending', 'in_progress']:
            current_tasks.append({
                'id': task.id,
                'code': task.task_code,
                'name': task.task_name,
                'project': task.project.name if task.project else None,
                'project_id': task.project.id if task.project else None,
                'status': task.status,
                'progress': task.progress.progress_percentage if task.progress else 0,
                'priority': task.priority,
                'planned_start': task.planning.planned_start.strftime('%Y-%m-%d') if task.planning and task.planning.planned_start else None,
                'planned_finish': task.planning.planned_finish.strftime('%Y-%m-%d') if task.planning and task.planning.planned_finish else None,
                'is_delayed': task.is_delayed if hasattr(task, 'is_delayed') else False,
                'delay_days': task.delay_days if hasattr(task, 'delay_days') else 0,
                'role': 'مشرف'
            })
    
    # المهام المفوضة له
    for task in delegated_tasks:
        if task.status in ['pending', 'in_progress']:
            current_tasks.append({
                'id': task.id,
                'code': task.task_code,
                'name': task.task_name,
                'project': task.project.name if task.project else None,
                'project_id': task.project.id if task.project else None,
                'status': task.status,
                'progress': task.progress.progress_percentage if task.progress else 0,
                'priority': task.priority,
                'planned_start': task.planning.planned_start.strftime('%Y-%m-%d') if task.planning and task.planning.planned_start else None,
                'planned_finish': task.planning.planned_finish.strftime('%Y-%m-%d') if task.planning and task.planning.planned_finish else None,
                'is_delayed': task.is_delayed if hasattr(task, 'is_delayed') else False,
                'delay_days': task.delay_days if hasattr(task, 'delay_days') else 0,
                'role': 'منفذ'
            })
    
    # ترتيب المهام حسب الأولوية
    current_tasks.sort(key=lambda x: (x['priority'] or 3, x['is_delayed']), reverse=True)
    
    # ============================================
    # 4. المهام المكتملة مؤخراً
    # ============================================
    recent_completed = []
    
    # المهام المكتملة التي أشرف عليها
    completed_supervised = Task.query.filter_by(supervisor_id=user_id, status='completed')\
        .order_by(Task.updated_at.desc()).limit(5).all()
    
    for task in completed_supervised:
        recent_completed.append({
            'id': task.id,
            'code': task.task_code,
            'name': task.task_name,
            'project': task.project.name if task.project else None,
            'completed_at': task.updated_at.strftime('%Y-%m-%d') if task.updated_at else None,
            'quality': task.completion_quality if hasattr(task, 'completion_quality') else None,
            'role': 'مشرف'
        })
    
    # المهام المكتملة التي نفذها
    completed_delegated = Task.query.filter_by(delegate_id=user_id, status='completed')\
        .order_by(Task.updated_at.desc()).limit(5).all()
    
    for task in completed_delegated:
        recent_completed.append({
            'id': task.id,
            'code': task.task_code,
            'name': task.task_name,
            'project': task.project.name if task.project else None,
            'completed_at': task.updated_at.strftime('%Y-%m-%d') if task.updated_at else None,
            'quality': task.completion_quality if hasattr(task, 'completion_quality') else None,
            'role': 'منفذ'
        })
    
    # ترتيب حسب تاريخ الإكمال
    recent_completed.sort(key=lambda x: x['completed_at'] or '', reverse=True)
    recent_completed = recent_completed[:5]
    
    # ============================================
    # 5. المشاريع التي يعمل عليها
    # ============================================
    project_ids = set()
    
    for task in supervised_tasks + delegated_tasks:
        if task.project_id:
            project_ids.add(task.project_id)
    
    projects = Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []
    
    projects_data = []
    for project in projects:
        # المهام في هذا المشروع
        project_tasks = [t for t in supervised_tasks + delegated_tasks if t.project_id == project.id]
        completed_project_tasks = len([t for t in project_tasks if t.status == 'completed'])
        total_project_tasks = len(project_tasks)
        
        projects_data.append({
            'id': project.id,
            'name': project.name,
            'code': project.project_code if hasattr(project, 'project_code') else None,
            'status': project.status if hasattr(project, 'status') else None,
            'tasks_count': total_project_tasks,
            'completed_tasks': completed_project_tasks,
            'completion_rate': (completed_project_tasks / total_project_tasks * 100) if total_project_tasks > 0 else 0,
            'role': 'مشرف' if any(t.supervisor_id == user_id for t in project_tasks) else 'منفذ'
        })
    
    # ============================================
    # 6. إحصائيات الأداء
    # ============================================
    
    # حساب الكفاءة
    efficiency = 0
    if task_stats['assigned']['total'] > 0:
        completion_rate = (task_stats['assigned']['completed'] / task_stats['assigned']['total']) * 100
        avg_quality = task_stats['assigned']['avg_quality'] * 20  # تحويل 1-5 إلى 0-100
        efficiency = (completion_rate * 0.6) + (avg_quality * 0.4)
    
    performance_stats = {
        'efficiency': round(efficiency, 1),
        'completion_rate': (task_stats['assigned']['completed'] / task_stats['assigned']['total'] * 100) if task_stats['assigned']['total'] > 0 else 0,
        'avg_quality': task_stats['assigned']['avg_quality'],
        'avg_efficiency': task_stats['assigned']['avg_efficiency'],
        'tasks_per_month': get_tasks_per_month(user_id),
        'performance_trend': get_performance_trend(user_id)
    }
    
    # ============================================
    # 7. المهارات
    # ============================================
    skills = UserSkill.query.filter_by(user_id=user_id).order_by(UserSkill.proficiency_level.desc()).all()
    
    skills_data = []
    for skill in skills:
        skills_data.append({
            'id': skill.id,
            'name': skill.skill_name,
            'name_ar': skill.skill_name_ar if hasattr(skill, 'skill_name_ar') else None,
            'category': skill.skill_category if hasattr(skill, 'skill_category') else None,
            'level': skill.proficiency_level,
            'experience_years': skill.experience_years,
            'certification': skill.certification if hasattr(skill, 'certification') else None,
            'is_verified': skill.is_verified if hasattr(skill, 'is_verified') else False,
            'success_rate': skill.success_rate if hasattr(skill, 'success_rate') else 0
        })
    
    # ============================================
    # 8. الإشعارات
    # ============================================
    notifications = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    notifications_data = []
    for notif in notifications:
        notifications_data.append({
            'id': notif.id,
            'title': notif.title,
            'message': notif.message,
            'type': notif.notification_type if hasattr(notif, 'notification_type') else 'info',
            'created_at': notif.created_at.strftime('%Y-%m-%d %H:%M') if notif.created_at else None,
            'link': get_notification_link(notif)
        })
    
    # ============================================
    # 9. نشاط اليوم
    # ============================================
    today_start = datetime.combine(date.today(), datetime.min.time())
    
    today_activity = {
        'tasks_started': Task.query.filter(
            or_(
                Task.supervisor_id == user_id,
                Task.delegate_id == user_id
            ),
            Task.status == 'in_progress',
            Task.updated_at >= today_start
        ).count(),
        'tasks_completed': Task.query.filter(
            or_(
                Task.supervisor_id == user_id,
                Task.delegate_id == user_id
            ),
            Task.status == 'completed',
            Task.updated_at >= today_start
        ).count(),
        'notifications_received': Notification.query.filter(
        Notification.user_id == user_id,
        Notification.created_at >= today_start
    ).count()
    }
    
    # ============================================
    # 10. الصلاحيات
    # ============================================
    permissions = {
        'can_edit': current_user.role in ['org_admin', 'project_manager'] or current_user.id == user_id,
        'can_assign_tasks': current_user.role in ['org_admin', 'project_manager'],
        'can_view_salary': current_user.role in ['org_admin', 'project_manager'],
        'can_manage_skills': current_user.role in ['org_admin', 'project_manager'] or current_user.id == user_id
    }
    
    return render_template('employee/view_employee.html',
                         employee=employee,
                         basic_info=basic_info,
                         task_stats=task_stats,
                         current_tasks=current_tasks,
                         recent_completed=recent_completed,
                         projects=projects_data,
                         performance_stats=performance_stats,
                         skills=skills_data,
                         notifications=notifications_data,
                         today_activity=today_activity,
                         permissions=permissions,
                         now=datetime.now())


# ============================================
# دوال مساعدة
# ============================================

def get_tasks_per_month(user_id, months=6):
    """الحصول على عدد المهام لكل شهر"""
    result = []
    today = date.today()
    
    for i in range(months-1, -1, -1):
        month_date = today - timedelta(days=30*i)
        month_start = datetime(month_date.year, month_date.month, 1)
        if month_date.month == 12:
            month_end = datetime(month_date.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = datetime(month_date.year, month_date.month + 1, 1) - timedelta(days=1)
        
        count = Task.query.filter(
            or_(
                Task.supervisor_id == user_id,
                Task.delegate_id == user_id
            ),
            Task.created_at >= month_start,
            Task.created_at <= month_end
        ).count()
        
        result.append({
            'month': month_date.strftime('%Y-%m'),
            'count': count
        })
    
    return result


def get_performance_trend(user_id):
    """تحليل اتجاه الأداء"""
    # مهام آخر 3 أشهر
    months_data = get_tasks_per_month(user_id, 3)
    
    if len(months_data) < 2:
        return 'stable'
    
    # حساب الاتجاه
    first = months_data[0]['count']
    last = months_data[-1]['count']
    
    if last > first * 1.2:
        return 'improving'
    elif last < first * 0.8:
        return 'declining'
    else:
        return 'stable'


def get_notification_link(notification):
    """الحصول على رابط الإشعار"""
    if hasattr(notification, 'related_task_id') and notification.related_task_id:
        return url_for('task_bp.task_detail', task_id=notification.related_task_id)
    elif hasattr(notification, 'related_project_id') and notification.related_project_id:
        return url_for('project_bp.project_details', project_id=notification.related_project_id)
    else:
        return '#'


# ============================================
# API لجلب بيانات الموظف (للواجهات الأمامية)
# ============================================

@company_bp.route('/api/employee/<int:user_id>/tasks')
@login_required
def api_employee_tasks(user_id):
    """API لجلب مهام الموظف"""
    employee = User.query.get_or_404(user_id)
    
    if employee.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    tasks = Task.query.filter(
        or_(
            Task.supervisor_id == user_id,
            Task.delegate_id == user_id
        )
    ).order_by(Task.created_at.desc()).all()
    
    tasks_data = []
    for task in tasks:
        tasks_data.append({
            'id': task.id,
            'code': task.task_code,
            'name': task.task_name,
            'status': task.status,
            'progress': task.progress.progress_percentage if task.progress else 0,
            'priority': task.priority,
            'project': task.project.name if task.project else None,
            'created_at': task.created_at.strftime('%Y-%m-%d') if task.created_at else None,
            'role': 'مشرف' if task.supervisor_id == user_id else 'منفذ'
        })
    
    return jsonify({'success': True, 'tasks': tasks_data})


@company_bp.route('/api/employee/<int:user_id>/performance')
@login_required
def api_employee_performance(user_id):
    """API لجلب بيانات أداء الموظف"""
    employee = User.query.get_or_404(user_id)
    
    if employee.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # إحصائيات المهام
    task_assignments = TaskAssignment.query.filter_by(user_id=user_id).all()
    
    # بيانات للرسوم البيانية
    monthly_data = get_tasks_per_month(user_id, 12)
    
    # توزيع المهام حسب الحالة
    status_distribution = {
        'completed': Task.query.filter(
            or_(Task.supervisor_id == user_id, Task.delegate_id == user_id),
            Task.status == 'completed'
        ).count(),
        'in_progress': Task.query.filter(
            or_(Task.supervisor_id == user_id, Task.delegate_id == user_id),
            Task.status == 'in_progress'
        ).count(),
        'pending': Task.query.filter(
            or_(Task.supervisor_id == user_id, Task.delegate_id == user_id),
            Task.status == 'pending'
        ).count()
    }
    
    return jsonify({
        'success': True,
        'performance': {
            'monthly': monthly_data,
            'status_distribution': status_distribution,
            'avg_quality': sum([a.quality_rating or 0 for a in task_assignments]) / len(task_assignments) if task_assignments else 0,
            'completion_rate': len([a for a in task_assignments if a.status == 'completed']) / len(task_assignments) * 100 if task_assignments else 0
        }
    })


# ============================================
# تحديث بيانات الموظف
# ============================================

@company_bp.route('/employee/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_employee(user_id):
    """تعديل بيانات الموظف"""
    employee = User.query.get_or_404(user_id)
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin', 'project_manager'] and current_user.id != user_id:
        flash('غير مصرح بالتعديل', 'danger')
        return redirect(url_for('company.view_employee', user_id=user_id))
    
    if request.method == 'POST':
        try:
            # تحديث المعلومات الأساسية
            employee.full_name = request.form.get('full_name', employee.full_name)
            employee.phone = request.form.get('phone', employee.phone)
            employee.mobile = request.form.get('mobile', employee.mobile)
            employee.job_title = request.form.get('job_title', employee.job_title)
            
            # تحديث القسم
            dept_id = request.form.get('department_id')
            if dept_id:
                employee.dept_id = int(dept_id)
            
            # تحديث الصلاحيات (للمدير فقط)
            if current_user.role in ['org_admin', 'project_manager']:
                employee.role = request.form.get('role', employee.role)
                employee.is_user_active = bool(request.form.get('is_active', employee.is_user_active))
            
            db.session.commit()
            flash('تم تحديث البيانات بنجاح', 'success')
            return redirect(url_for('company.view_employee', user_id=user_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # جلب الأقسام
    departments = Department.query.filter_by(org_id=employee.org_id).all()
    
    return render_template('employee/edit_employee.html',
                         employee=employee,
                         departments=departments)

# app/routes/company_routes.py - إضافة مسارات الاجتماعات

@company_bp.route('/meetings')
@login_required
def meetings_list():
    """عرض جميع الاجتماعات"""
    if current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    projects = Project.query.filter_by(org_id=current_user.org_id).all()
    project_ids = [p.id for p in projects]
    if project_ids:
        meetings = Meeting.query.filter(Meeting.project_id.in_(project_ids)).order_by(
            Meeting.scheduled_date.desc()
        ).all()
    else:
        meetings = []
    
    # إحصائيات
    stats = {
        'total': len(meetings),
        'scheduled': len([m for m in meetings if m.status == 'scheduled']),
        'completed': len([m for m in meetings if m.status == 'completed']),
        'upcoming': len([m for m in meetings if m.status == 'scheduled' and m.scheduled_date >= datetime.now().date()])
    }
    
    return render_template('company/meetings/index.html', meetings=meetings, stats=stats, now=datetime.now())


@company_bp.route('/meetings/create', methods=['GET', 'POST'])
@login_required
def create_meeting():
    """إنشاء اجتماع جديد"""
    if current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    if request.method == 'POST':
        try:
            from app.services.meeting_service import MeetingService
            
            data = {
                'project_id': request.form.get('project_id'),
                'title': request.form.get('title'),
                'purpose': request.form.get('purpose'),
                'meeting_type': request.form.get('meeting_type'),
                'location': request.form.get('location'),
                'is_virtual': 'is_virtual' in request.form,
                'virtual_link': request.form.get('virtual_link'),
                'scheduled_date': request.form.get('scheduled_date'),
                'start_time': request.form.get('start_time'),
                'end_time': request.form.get('end_time'),
                'organizer_id': current_user.id,
                'secretary_id': request.form.get('secretary_id'),
                'agenda': request.form.getlist('agenda_items'),
                'attendees': request.form.getlist('attendees')
            }
            
            meeting = MeetingService.create_meeting(data)
            
            flash('تم إنشاء الاجتماع بنجاح', 'success')
            return redirect(url_for('company.view_meeting', meeting_id=meeting.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    projects = Project.query.filter_by(org_id=current_user.org_id).all()
    users = User.query.filter_by(org_id=current_user.org_id).all()
    
    return render_template('company/meetings/create.html', projects=projects, users=users, now=datetime.now())


@company_bp.route('/meetings/<int:meeting_id>')
@login_required
def view_meeting(meeting_id):
    """عرض تفاصيل الاجتماع"""
    meeting = Meeting.query.get_or_404(meeting_id)
    
    # التحقق من الصلاحية
    if meeting.project.org_id != current_user.org_id and current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    return render_template('company/meetings/view.html', meeting=meeting, now=datetime.now())


@company_bp.route('/meetings/<int:meeting_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_meeting(meeting_id):
    """تعديل اجتماع"""
    meeting = Meeting.query.get_or_404(meeting_id)
    
    if meeting.project.org_id != current_user.org_id and current_user.role != 'org_admin':
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    if request.method == 'POST':
        try:
            meeting.title = request.form.get('title')
            meeting.purpose = request.form.get('purpose')
            meeting.meeting_type = request.form.get('meeting_type')
            meeting.location = request.form.get('location')
            meeting.is_virtual = 'is_virtual' in request.form
            meeting.virtual_link = request.form.get('virtual_link')
            meeting.scheduled_date = datetime.strptime(request.form.get('scheduled_date'), '%Y-%m-%d').date()
            meeting.start_time = datetime.strptime(request.form.get('start_time'), '%H:%M').time() if request.form.get('start_time') else None
            meeting.end_time = datetime.strptime(request.form.get('end_time'), '%H:%M').time() if request.form.get('end_time') else None
            meeting.secretary_id = request.form.get('secretary_id')
            meeting.agenda = request.form.getlist('agenda_items')
            meeting.attendees = request.form.getlist('attendees')
            
            db.session.commit()
            flash('تم تحديث الاجتماع بنجاح', 'success')
            return redirect(url_for('company.view_meeting', meeting_id=meeting.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    projects = Project.query.filter_by(org_id=current_user.org_id).all()
    users = User.query.filter_by(org_id=current_user.org_id).all()
    
    return render_template('company/meetings/edit.html', meeting=meeting, projects=projects, users=users, now=datetime.now())


@company_bp.route('/meetings/<int:meeting_id>/cancel', methods=['POST'])
@login_required
def cancel_meeting(meeting_id):
    """إلغاء اجتماع"""
    meeting = Meeting.query.get_or_404(meeting_id)
    
    if meeting.project.org_id != current_user.org_id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    meeting.status = 'cancelled'
    db.session.commit()
    
    # إشعار للمشاركين
    from app.services.meeting_service import MeetingService
    participants = MeetingService._get_all_participants(meeting)
    for participant in participants:
        NotificationService.meeting_cancelled(
            user_id=participant.id,
            meeting=meeting
        )
    
    return jsonify({'success': True})


@company_bp.route('/meetings/<int:meeting_id>/complete', methods=['POST'])
@login_required
def complete_meeting(meeting_id):
    """إنهاء اجتماع (تسجيل المحضر)"""
    meeting = Meeting.query.get_or_404(meeting_id)
    
    if meeting.project.org_id != current_user.org_id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    meeting.status = 'completed'
    meeting.minutes = data.get('minutes')
    meeting.decisions = data.get('decisions', [])
    meeting.action_items = data.get('action_items', [])
    meeting.actual_end_time = datetime.now()
    
    db.session.commit()
    
    # إشعار للمشاركين
    from app.services.meeting_service import MeetingService
    participants = MeetingService._get_all_participants(meeting)
    for participant in participants:
        NotificationService.meeting_completed(
            user_id=participant.id,
            meeting=meeting
        )
    
    return jsonify({'success': True})
# ============================================
# مسارات إدارة القضايا (Issues)
# ============================================

@company_bp.route('/issues')
@login_required
def issues_list():
    """عرض قائمة القضايا"""
    if current_user.role != 'org_admin':
        flash(_('access_denied'), 'danger')
        return redirect(url_for('company.dashboard'))
    
    # معاملات التصفية والبحث
    status_filter = request.args.get('status', 'all')
    priority_filter = request.args.get('priority', 'all')
    project_filter = request.args.get('project_id', 'all')
    search_query = request.args.get('search', '')
    
    # بناء الاستعلام
    query = Issue.query.join(Project).filter(Project.org_id == current_user.org_id)
    
    if status_filter != 'all':
        query = query.filter(Issue.status == status_filter)
    
    if priority_filter != 'all':
        query = query.filter(Issue.priority == priority_filter)
    
    if project_filter != 'all':
        query = query.filter(Issue.project_id == project_filter)
    
    if search_query:
        query = query.filter(
            db.or_(
                Issue.title.ilike(f'%{search_query}%'),
                Issue.description.ilike(f'%{search_query}%'),
                Issue.issue_code.ilike(f'%{search_query}%')
            )
        )
    
    issues = query.order_by(Issue.priority.desc(), Issue.reported_date.desc()).all()
    
    # إحصائيات
    stats = {
        'total': Issue.query.join(Project).filter(Project.org_id == current_user.org_id).count(),
        'open': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.status == 'open').count(),
        'in_progress': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.status == 'in_progress').count(),
        'resolved': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.status == 'resolved').count(),
        'closed': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.status == 'closed').count(),
        'critical': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'critical').count(),
        'high': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'high').count(),
        'medium': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'medium').count(),
        'low': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'low').count(),
    }
    
    # المشاريع للفلترة
    projects = Project.query.filter_by(org_id=current_user.org_id).all()
    
    return render_template('company/issues/index.html',
                         issues=issues,
                         stats=stats,
                         projects=projects,
                         status_filter=status_filter,
                         priority_filter=priority_filter,
                         project_filter=project_filter,
                         search_query=search_query,
                         now=datetime.now())


@company_bp.route('/issues/<int:issue_id>')
@login_required
def view_issue(issue_id):
    """عرض تفاصيل القضية"""
    if current_user.role != 'org_admin':
        flash(_('access_denied'), 'danger')
        return redirect(url_for('company.dashboard'))
    
    issue = Issue.query.get_or_404(issue_id)
    
    # التحقق من الصلاحية
    if issue.project.org_id != current_user.org_id:
        flash(_('access_denied'), 'danger')
        return redirect(url_for('company.issues_list'))
    
    # سجل التحديثات
    updates = RiskUpdate.query.filter_by(risk_id=issue.id).order_by(RiskUpdate.updated_at.desc()).all() if hasattr(issue, 'updates') else []
    
    return render_template('company/issues/view.html',
                         issue=issue,
                         updates=updates,
                         now=datetime.now())


@company_bp.route('/issues/create', methods=['GET', 'POST'])
@login_required
def create_issue():
    """إنشاء قضية جديدة"""
    if current_user.role != 'org_admin':
        flash(_('access_denied'), 'danger')
        return redirect(url_for('company.dashboard'))
    
    if request.method == 'POST':
        try:
            # إنشاء كود فريد للقضية
            issue_code = f"ISS-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            issue = Issue(
                project_id=request.form.get('project_id'),
                task_id=request.form.get('task_id') or None,
                issue_code=issue_code,
                title=request.form.get('title'),
                title_ar=request.form.get('title_ar'),
                description=request.form.get('description'),
                category=request.form.get('category'),
                priority=request.form.get('priority', 'medium'),
                severity=request.form.get('severity', 'medium'),
                reported_by=current_user.id,
                reported_date=datetime.utcnow(),
                assigned_to=request.form.get('assigned_to') or None,
                due_date=datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date() if request.form.get('due_date') else None,
                status='open'
            )
            
            db.session.add(issue)
            db.session.commit()
            
            # إشعار للمسند إليه
            if issue.assigned_to:
                NotificationService.issue_assigned(issue, issue.assigned_to, current_user)
            
            flash(_('issue_created_success'), 'success')
            return redirect(url_for('company.view_issue', issue_id=issue.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'{_("error_occurred")}: {str(e)}', 'danger')
    
    projects = Project.query.filter_by(org_id=current_user.org_id).all()
    users = User.query.filter_by(org_id=current_user.org_id).all()
    tasks = Task.query.all() if request.args.get('project_id') else []
    
    return render_template('company/issues/create.html',
                         projects=projects,
                         users=users,
                         tasks=tasks,
                         now=datetime.now())


@company_bp.route('/issues/<int:issue_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_issue(issue_id):
    """تعديل قضية"""
    if current_user.role != 'org_admin':
        flash(_('access_denied'), 'danger')
        return redirect(url_for('company.dashboard'))
    
    issue = Issue.query.get_or_404(issue_id)
    
    if issue.project.org_id != current_user.org_id:
        flash(_('access_denied'), 'danger')
        return redirect(url_for('company.issues_list'))
    
    if request.method == 'POST':
        try:
            issue.title = request.form.get('title')
            issue.title_ar = request.form.get('title_ar')
            issue.description = request.form.get('description')
            issue.category = request.form.get('category')
            issue.priority = request.form.get('priority')
            issue.severity = request.form.get('severity')
            issue.assigned_to = request.form.get('assigned_to') or None
            issue.due_date = datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date() if request.form.get('due_date') else None
            
            db.session.commit()
            
            flash(_('issue_updated_success'), 'success')
            return redirect(url_for('company.view_issue', issue_id=issue.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'{_("error_occurred")}: {str(e)}', 'danger')
    
    projects = Project.query.filter_by(org_id=current_user.org_id).all()
    users = User.query.filter_by(org_id=current_user.org_id).all()
    
    return render_template('company/issues/edit.html',
                         issue=issue,
                         projects=projects,
                         users=users,
                         now=datetime.now())


@company_bp.route('/issues/<int:issue_id>/update-status', methods=['POST'])
@login_required
def update_issue_status(issue_id):
    """تحديث حالة القضية"""
    if current_user.role != 'org_admin':
        return jsonify({'error': _('access_denied')}), 403
    
    issue = Issue.query.get_or_404(issue_id)
    
    if issue.project.org_id != current_user.org_id:
        return jsonify({'error': _('access_denied')}), 403
    
    data = request.get_json()
    new_status = data.get('status')
    resolution = data.get('resolution', '')
    
    try:
        old_status = issue.status
        issue.status = new_status
        
        if new_status == 'resolved' or new_status == 'closed':
            issue.resolution = resolution
            issue.resolution_date = datetime.utcnow()
        
        db.session.commit()
        
        # تسجيل التحديث
        update = RiskUpdate(
            risk_id=issue.id,
            old_status=old_status,
            new_status=new_status,
            notes=resolution,
            updated_by=current_user.id,
            updated_at=datetime.utcnow()
        )
        db.session.add(update)
        db.session.commit()
        
        # إشعار للمسند إليه
        if issue.assigned_to:
            NotificationService.issue_status_updated(issue, issue.assigned_to, current_user, new_status)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@company_bp.route('/issues/<int:issue_id>/delete', methods=['POST'])
@login_required
def delete_issue(issue_id):
    """حذف قضية"""
    if current_user.role != 'org_admin':
        return jsonify({'error': _('access_denied')}), 403
    
    issue = Issue.query.get_or_404(issue_id)
    
    if issue.project.org_id != current_user.org_id:
        return jsonify({'error': _('access_denied')}), 403
    
    try:
        db.session.delete(issue)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@company_bp.route('/issues/<int:issue_id>/assign', methods=['POST'])
@login_required
def assign_issue(issue_id):
    """تعيين قضية لمستخدم"""
    if current_user.role != 'org_admin':
        return jsonify({'error': _('access_denied')}), 403
    
    issue = Issue.query.get_or_404(issue_id)
    
    if issue.project.org_id != current_user.org_id:
        return jsonify({'error': _('access_denied')}), 403
    
    data = request.get_json()
    user_id = data.get('user_id')
    
    try:
        issue.assigned_to = user_id
        issue.assigned_date = datetime.utcnow()
        db.session.commit()
        
        # إشعار للمستخدم
        if user_id:
            NotificationService.issue_assigned(issue, user_id, current_user)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@company_bp.route('/api/issues/stats')
@login_required
def api_issues_stats():
    """API لإحصائيات القضايا"""
    if current_user.role != 'org_admin':
        return jsonify({'error': _('access_denied')}), 403
    
    # إحصائيات حسب المشروع
    projects = Project.query.filter_by(org_id=current_user.org_id).all()
    
    project_stats = []
    for project in projects:
        issues = Issue.query.filter_by(project_id=project.id).all()
        project_stats.append({
            'id': project.id,
            'name': project.name,
            'total': len(issues),
            'open': len([i for i in issues if i.status == 'open']),
            'in_progress': len([i for i in issues if i.status == 'in_progress']),
            'resolved': len([i for i in issues if i.status == 'resolved']),
            'closed': len([i for i in issues if i.status == 'closed'])
        })
    
    # إحصائيات حسب الأولوية
    priority_stats = {
        'critical': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'critical').count(),
        'high': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'high').count(),
        'medium': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'medium').count(),
        'low': Issue.query.join(Project).filter(Project.org_id == current_user.org_id, Issue.priority == 'low').count()
    }
    
    return jsonify({
        'success': True,
        'project_stats': project_stats,
        'priority_stats': priority_stats
    })


# في company_routes.py - إضافة مسارات الباقات

@company_bp.route('/plans')
@login_required
# @subscription_required  # يسمح بالوصول حتى لو انتهت الفترة
def view_plans():
    """عرض جميع الباقات المتاحة للاشتراك"""
    
    # جلب جميع الباقات النشطة
    plans = SubscriptionPlan.query.filter_by(is_active=True).order_by(SubscriptionPlan.display_order).all()
    
    # جلب الاشتراك الحالي للشركة (إذا وجد)
    current_subscription = Subscription.query.filter_by(
        org_id=current_user.org_id,
        status='active'
    ).first()
    
    # جلب طلب الاشتراك المعلق (إذا وجد)
    pending_request = Subscription.query.filter_by(
        org_id=current_user.org_id
        # request_status='pending'
    ).first()
    
    return render_template('company/plans/index.html',
                         plans=plans,
                         current_subscription=current_subscription,
                         pending_request=pending_request,
                         format_currency=format_currency,
                         now=datetime.now())


@company_bp.route('/plans/<plan_id>/subscribe', methods=['GET', 'POST'])
@login_required
def subscribe_to_plan(plan_id):
    """تقديم طلب اشتراك في باقة معينة"""
    
    # جلب تفاصيل الباقة
    plan = SubscriptionPlan.query.filter_by(plan_id=plan_id, is_active=True).first_or_404()
    
    # التحقق من عدم وجود طلب معلق
    existing_pending = Subscription.query.filter_by(
        org_id=current_user.org_id,
        request_status='pending'
    ).first()
    
    if existing_pending:
        flash('لديك طلب اشتراك معلق قيد المراجعة', 'warning')
        return redirect(url_for('company.view_plans'))
    
    # التحقق من وجود اشتراك نشط
    existing_active = Subscription.query.filter_by(
        org_id=current_user.org_id,
        status='active'
    ).first()
    
    if existing_active:
        flash('لديك اشتراك نشط حالياً. يمكنك ترقية اشتراكك من خلال لوحة التحكم', 'warning')
        return redirect(url_for('company.view_plans'))
    
    if request.method == 'POST':
        duration_months = int(request.form.get('duration_months', 12))
        payment_method = request.form.get('payment_method', 'bank_transfer')
        
        # حساب المبلغ
        amount = plan.get_price_for_duration(duration_months)
        
        # حساب الضريبة (15% في السعودية)
        tax_rate = 0.15
        tax_amount = amount * tax_rate
        total_amount = amount + tax_amount
        
        # إنشاء طلب اشتراك
        subscription = Subscription(
            org_id=current_user.org_id,
            plan_id=plan.plan_id,
            plan=plan.plan_id,
            plan_name=plan.name,
            amount=amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            currency=plan.currency,
            payment_method=payment_method,
            payment_status='pending',
            request_status='pending',
            duration_months=duration_months,
            status='pending',
            created_by=current_user.id
        )
        
        db.session.add(subscription)
        db.session.commit()
        
        # إرسال إشعار لإدارة المنصة
        # ✅ إشعار بطلب اشتراك جديد
        from app.services.platform_notification_service import PlatformNotificationService
        PlatformNotificationService.new_subscription_request(subscription)
        # معالجة الدفع حسب طريقة الدفع
        if payment_method == 'credit_card':
            # توجيه إلى صفحة الدفع عبر Stripe
            return redirect(url_for('company.process_payment', subscription_id=subscription.id))
        elif payment_method == 'bank_transfer':
            # عرض معلومات التحويل البنكي
            flash('تم إرسال طلب الاشتراك بنجاح. سيتم مراجعته من قبل الإدارة.', 'success')
            return redirect(url_for('company.subscription_payment_info', subscription_id=subscription.id))
        
        flash('تم إرسال طلب الاشتراك بنجاح. سيتم مراجعته من قبل الإدارة.', 'success')
        return redirect(url_for('company.view_plans'))
    
    # حساب الأسعار للمدة المختلفة
    pricing = {
        '3_months': plan.get_price_for_duration(3),
        '6_months': plan.get_price_for_duration(6),
        '12_months': plan.get_price_for_duration(12),
        '24_months': plan.get_price_for_duration(24)
    }
    
    return render_template('company/plans/subscribe.html',
                         plan=plan,
                         pricing=pricing,
                         format_currency=format_currency,
                         now=datetime.now())


@company_bp.route('/subscription/payment/<int:subscription_id>')
@login_required
def subscription_payment_info(subscription_id):
    """عرض معلومات الدفع (للتحويل البنكي)"""
    
    subscription = Subscription.query.get_or_404(subscription_id)
    
    if subscription.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # معلومات الحساب البنكي للمنصة
    bank_info = {
        'bank_name': 'البنك الأهلي السعودي',
        'account_name': 'شركة منصة إدارة المشاريع',
        'account_number': 'SA1234567890123456789012',
        'iban': 'SA1234567890123456789012',
        'swift_code': 'NCBKSAJE'
    }
    
    return render_template('company/plans/payment_info.html',
                         subscription=subscription,
                         bank_info=bank_info,
                         now=datetime.now())


@company_bp.route('/subscription/upload-proof/<int:subscription_id>', methods=['POST'])
@login_required
def upload_payment_proof(subscription_id):
    """رفع إثبات الدفع"""
    
    subscription = Subscription.query.get_or_404(subscription_id)
    
    if subscription.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    if 'payment_proof' not in request.files:
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    file = request.files['payment_proof']
    if file.filename == '':
        return jsonify({'error': 'لم يتم اختيار ملف'}), 400
    
    # حفظ الملف
    from werkzeug.utils import secure_filename
    filename = secure_filename(f"proof_{subscription.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{file.filename.rsplit('.', 1)[1].lower()}")
    
    upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'payment_proofs')
    os.makedirs(upload_path, exist_ok=True)
    file_path = os.path.join(upload_path, filename)
    file.save(file_path)
    
    # تحديث الاشتراك
    subscription.payment_proof = url_for('static', filename=f'uploads/payment_proofs/{filename}')
    db.session.commit()
    
    # ✅ إشعار برفع إثبات دفع
    from app.services.platform_notification_service import PlatformNotificationService
    PlatformNotificationService.payment_proof_uploaded(subscription)
    
    flash('تم رفع إثبات الدفع بنجاح. سيتم مراجعته من قبل الإدارة.', 'success')
    return redirect(url_for('company.subscription_payment_info', subscription_id=subscription.id))


@company_bp.route('/subscription/status')
@login_required
def subscription_status():
    """عرض حالة طلب الاشتراك"""
    
    subscription = Subscription.query.filter_by(
        org_id=current_user.org_id
    ).order_by(Subscription.created_at.desc()).first()
    
    if not subscription:
        flash('لا يوجد طلب اشتراك', 'info')
        return redirect(url_for('company.view_plans'))
    
    return render_template('company/plans/status.html',
                         subscription=subscription,
                         now=datetime.now())


@company_bp.route('/process-payment/<int:subscription_id>')
@login_required
def process_payment(subscription_id):
    """معالجة الدفع عبر Stripe"""
    
    subscription = Subscription.query.get_or_404(subscription_id)
    
    if subscription.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # إعداد Stripe
    import stripe
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    
    # إنشاء جلسة دفع
    checkout_session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': subscription.currency.lower(),
                'unit_amount': int(subscription.total_amount * 100),  # Stripe يتعامل بالسنت
                'product_data': {
                    'name': f'اشتراك {subscription.plan_name}',
                    'description': f'مدة الاشتراك: {subscription.duration_months} شهر',
                },
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=url_for('company.payment_success', subscription_id=subscription.id, _external=True),
        cancel_url=url_for('company.payment_cancel', subscription_id=subscription.id, _external=True),
        client_reference_id=str(subscription.id),
        metadata={
            'subscription_id': subscription.id,
            'organization_id': current_user.org_id
        }
    )
    
    # حفظ session_id
    subscription.stripe_payment_intent_id = checkout_session.id
    db.session.commit()
    
    return redirect(checkout_session.url, code=303)


@company_bp.route('/payment-success/<int:subscription_id>')
@login_required
def payment_success(subscription_id):
    """نجاح عملية الدفع"""
    
    subscription = Subscription.query.get_or_404(subscription_id)
    
    if subscription.org_id != current_user.org_id:
        flash('غير مصرح', 'danger')
        return redirect(url_for('company.dashboard'))
    
    # تحديث حالة الدفع
    subscription.payment_status = 'paid'
    db.session.commit()
    
    flash('تمت عملية الدفع بنجاح! جاري مراجعة طلب الاشتراك من قبل الإدارة.', 'success')
    return redirect(url_for('company.subscription_status'))


@company_bp.route('/payment-cancel/<int:subscription_id>')
@login_required
def payment_cancel(subscription_id):
    """إلغاء عملية الدفع"""
    
    subscription = Subscription.query.get_or_404(subscription_id)
    
    flash('تم إلغاء عملية الدفع. يمكنك المحاولة مرة أخرى.', 'warning')
    return redirect(url_for('company.subscribe_to_plan', plan_id=subscription.plan))
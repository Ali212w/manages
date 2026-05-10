"""
activity_routes.py - مسارات إدارة الأنشطة المتكاملة
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models.integrated_models import (
    db, Activity, ActivityStep, ActivityExpense, ActivityRisk,
    ActivityFeedback, ActivityDocument, ActivityResource,
    ActivityRelationship, Project, WBS, Calendar, Resource, User
)
from datetime import datetime, date
import os
from werkzeug.utils import secure_filename
import uuid

activity_bp = Blueprint('activities', __name__, url_prefix='/activities')

# ============================================
# دوال مساعدة
# ============================================

def check_activity_access(activity_id):
    """التحقق من صلاحية الوصول للنشاط"""
    activity = Activity.query.get_or_404(activity_id)
    project = Project.query.get(activity.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return None
    return activity

def get_primary_resource(activity_id):
    """الحصول على المورد الرئيسي للنشاط"""
    resource = ActivityResource.query.filter_by(activity_id=activity_id).first()
    if resource and resource.resource:
        return {
            'id': resource.resource.id,
            'name': resource.resource.name,
            'type': resource.resource.resource_type
        }
    return None

def would_create_circular_relationship(pred_id, succ_id, visited=None):
    """التحقق من عدم إنشاء علاقة دائرية"""
    if visited is None:
        visited = set()
    if succ_id in visited:
        return True
    visited.add(succ_id)
    relationships = ActivityRelationship.query.filter_by(predecessor_id=succ_id).all()
    for rel in relationships:
        if rel.successor_id == pred_id:
            return True
        if would_create_circular_relationship(pred_id, rel.successor_id, visited):
            return True
    return False

def update_activity_progress(activity_id):
    """تحديث تقدم النشاط بناءً على المهام"""
    activity = Activity.query.get(activity_id)
    if activity:
        tasks = activity.tasks.all()
        if tasks:
            completed = sum(1 for t in tasks if t.status == 'completed')
            activity.progress_percentage = (completed / len(tasks)) * 100
            db.session.commit()

# ============================================
# صفحات الأنشطة
# ============================================

@activity_bp.route('/')
@login_required
def list_activities():
    """عرض قائمة الأنشطة"""
    project_id = request.args.get('project_id')
    
    if project_id:
        activities = Activity.query.filter_by(project_id=project_id).order_by(Activity.activity_code).all()
        project = Project.query.get(project_id)
    else:
        activities = Activity.query.join(Project).filter(Project.created_by == current_user.id).all()
        project = None
    
    # إحصائيات
    stats = {
        'total': len(activities),
        'completed': sum(1 for a in activities if a.status == 'completed'),
        'in_progress': sum(1 for a in activities if a.status == 'in_progress'),
        'not_started': sum(1 for a in activities if a.status == 'not_started'),
        'critical': sum(1 for a in activities if a.is_critical)
    }
    
    return render_template('activities/list.html', 
                         activities=activities, 
                         project=project,
                         stats=stats)


@activity_bp.route('/<int:activity_id>')
@login_required
def activity_detail(activity_id):
    """عرض تفاصيل النشاط مع جميع التبويبات"""
    activity = check_activity_access(activity_id)
    if not activity:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('activities.list_activities'))
    
    # جلب البيانات الأساسية
    wbs_list = WBS.query.filter_by(project_id=activity.project_id).all()
    calendars = Calendar.query.filter_by(org_id=current_user.org_id).all()
    resources = Resource.query.filter_by(org_id=current_user.org_id).all()
    users = User.query.filter_by(org_id=current_user.org_id).all()
    all_activities = Activity.query.filter_by(project_id=activity.project_id).all()
    
    # العلاقات
    predecessors = ActivityRelationship.query.filter_by(successor_id=activity_id).all()
    successors = ActivityRelationship.query.filter_by(predecessor_id=activity_id).all()
    
    # تجهيز بيانات العلاقات
    predecessors_data = []
    for rel in predecessors:
        pred_activity = Activity.query.get(rel.predecessor_id)
        if pred_activity:
            predecessors_data.append({
                'id': rel.id,
                'predecessor': {
                    'id': pred_activity.id,
                    'activity_id': pred_activity.activity_code,
                    'activity_name': pred_activity.activity_name,
                    'status': pred_activity.status,
                    'is_critical': pred_activity.is_critical,
                    'primary_resource': get_primary_resource(pred_activity.id)
                },
                'relationship_type': rel.relationship_type,
                'lag_days': rel.lag_days,
                'lag_type': rel.lag_type,
                'is_critical': rel.is_critical,
                'is_driving': rel.is_driving
            })
    
    successors_data = []
    for rel in successors:
        succ_activity = Activity.query.get(rel.successor_id)
        if succ_activity:
            successors_data.append({
                'id': rel.id,
                'successor': {
                    'id': succ_activity.id,
                    'activity_id': succ_activity.activity_code,
                    'activity_name': succ_activity.activity_name,
                    'status': succ_activity.status,
                    'is_critical': succ_activity.is_critical,
                    'primary_resource': get_primary_resource(succ_activity.id)
                },
                'relationship_type': rel.relationship_type,
                'lag_days': rel.lag_days,
                'lag_type': rel.lag_type,
                'is_critical': rel.is_critical,
                'is_driving': rel.is_driving
            })
    
    # خطوات التنفيذ
    steps = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order).all()
    steps_completed = sum(1 for s in steps if s.is_completed)
    steps_completion = (steps_completed / len(steps) * 100) if steps else 0
    
    # المصروفات
    expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
    total_expenses = sum(e.amount for e in expenses)
    approved_expenses = sum(e.amount for e in expenses if e.is_approved)
    
    # المخاطر
    risks = ActivityRisk.query.filter_by(activity_id=activity_id).all()
    
    # المستندات
    documents = ActivityDocument.query.filter_by(activity_id=activity_id).all()
    
    # التعليقات
    feedback_list = ActivityFeedback.query.filter_by(activity_id=activity_id).order_by(ActivityFeedback.created_at.desc()).all()
    
    # المهام المرتبطة
    tasks = activity.tasks.all()
    
    return render_template('activities/detail.html',
                         activity=activity,
                         wbs_list=wbs_list,
                         calendars=calendars,
                         resources=resources,
                         users=users,
                         all_activities=all_activities,
                         predecessors=predecessors_data,
                         successors=successors_data,
                         steps=steps,
                         steps_completion=steps_completion,
                         expenses=expenses,
                         total_expenses=total_expenses,
                         approved_expenses=approved_expenses,
                         pending_expenses=total_expenses - approved_expenses,
                         risks=risks,
                         documents=documents,
                         feedback_list=feedback_list,
                         tasks=tasks)


@activity_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_activity():
    """إنشاء نشاط جديد"""
    if request.method == 'POST':
        try:
            project_id = request.form.get('project_id')
            
            # إنشاء كود النشاط تلقائياً
            last_activity = Activity.query.filter_by(project_id=project_id).order_by(Activity.id.desc()).first()
            if last_activity and last_activity.activity_code:
                last_num = int(last_activity.activity_code[1:]) if last_activity.activity_code[0] == 'A' else 1000
                activity_code = f"A{last_num + 1}"
            else:
                activity_code = "A1000"
            
            activity = Activity(
                project_id=project_id,
                wbs_id=request.form.get('wbs_id') or None,
                calendar_id=request.form.get('calendar_id') or None,
                activity_code=activity_code,
                activity_name=request.form.get('activity_name'),
                activity_name_ar=request.form.get('activity_name_ar'),
                description=request.form.get('description'),
                instructions=request.form.get('instructions'),
                activity_type=request.form.get('activity_type', 'task_dependent'),
                status=request.form.get('status', 'not_started'),
                priority=int(request.form.get('priority', 3)),
                weight=float(request.form.get('weight', 1.0)),
                responsible_id=request.form.get('responsible_id') or None,
                supervisor_id=request.form.get('supervisor_id') or None,
                delegate_id=request.form.get('delegate_id') or None,
                original_duration=float(request.form.get('original_duration', 0)),
                remaining_duration=float(request.form.get('original_duration', 0)),
                planned_start=datetime.strptime(request.form.get('planned_start'), '%Y-%m-%d') if request.form.get('planned_start') else None,
                planned_finish=datetime.strptime(request.form.get('planned_finish'), '%Y-%m-%d') if request.form.get('planned_finish') else None,
                location=request.form.get('location'),
                created_by=current_user.id,
                uuid=str(uuid.uuid4())
            )
            
            db.session.add(activity)
            db.session.commit()
            
            flash('تم إنشاء النشاط بنجاح', 'success')
            return redirect(url_for('activities.activity_detail', activity_id=activity.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # بيانات النموذج
    project_id = request.args.get('project_id')
    project = Project.query.get(project_id) if project_id else None
    
    wbs_list = WBS.query.filter_by(project_id=project_id).all() if project_id else []
    calendars = Calendar.query.filter_by(org_id=current_user.org_id).all()
    users = User.query.filter_by(org_id=current_user.org_id).all()
    
    return render_template('activities/create.html',
                         project=project,
                         wbs_list=wbs_list,
                         calendars=calendars,
                         users=users)

# ============================================
# API Routes للأنشطة
# ============================================

@activity_bp.route('/api/list')
@login_required
def api_activity_list():
    """API لقائمة الأنشطة"""
    project_id = request.args.get('project_id')
    
    query = Activity.query
    if project_id:
        query = query.filter_by(project_id=project_id)
    else:
        query = query.join(Project).filter(Project.created_by == current_user.id)
    
    activities = query.order_by(Activity.activity_code).all()
    
    return jsonify({
        'success': True,
        'activities': [{
            'id': a.id,
            'activity_code': a.activity_code,
            'activity_name': a.activity_name,
            'status': a.status,
            'progress': a.progress_percentage,
            'is_critical': a.is_critical,
            'project_id': a.project_id,
            'project_name': a.project.name if a.project else None,
            'tasks_count': a.tasks.count()
        } for a in activities]
    })

@activity_bp.route('/api/<int:activity_id>')
@login_required
def api_activity_detail(activity_id):
    """API لتفاصيل النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'activity': {
            'id': activity.id,
            'activity_code': activity.activity_code,
            'activity_name': activity.activity_name,
            'activity_name_ar': activity.activity_name_ar,
            'activity_type': activity.activity_type,
            'status': activity.status,
            'progress': activity.progress_percentage,
            'original_duration': activity.original_duration,
            'remaining_duration': activity.remaining_duration,
            'actual_duration': activity.actual_duration,
            'planned_start': activity.planned_start.isoformat() if activity.planned_start else None,
            'planned_finish': activity.planned_finish.isoformat() if activity.planned_finish else None,
            'actual_start': activity.actual_start.isoformat() if activity.actual_start else None,
            'actual_finish': activity.actual_finish.isoformat() if activity.actual_finish else None,
            'total_float': activity.total_float,
            'is_critical': activity.is_critical,
            'wbs_id': activity.wbs_id,
            'responsible_id': activity.responsible_id,
            'tasks_count': activity.tasks.count(),
            'completed_tasks': activity.tasks.filter_by(status='completed').count()
        }
    })

@activity_bp.route('/api/<int:activity_id>/update', methods=['POST'])
@login_required
def api_update_activity(activity_id):
    """تحديث بيانات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if 'activity_name' in data:
            activity.activity_name = data['activity_name']
        if 'status' in data:
            activity.status = data['status']
        if 'progress_percentage' in data:
            activity.progress_percentage = float(data['progress_percentage'])
        if 'remaining_duration' in data:
            activity.remaining_duration = float(data['remaining_duration'])
        if 'actual_start' in data and data['actual_start']:
            activity.actual_start = datetime.strptime(data['actual_start'], '%Y-%m-%d')
        if 'actual_finish' in data and data['actual_finish']:
            activity.actual_finish = datetime.strptime(data['actual_finish'], '%Y-%m-%d')
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للخطوات (Steps)
# ============================================

@activity_bp.route('/api/<int:activity_id>/steps', methods=['GET'])
@login_required
def api_activity_steps(activity_id):
    """جلب خطوات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    steps = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order).all()
    
    completed = sum(1 for s in steps if s.is_completed)
    total = len(steps)
    
    return jsonify({
        'success': True,
        'steps': [{
            'id': s.id,
            'order': s.order,
            'title': s.title,
            'description': s.description,
            'is_completed': s.is_completed,
            'completed_at': s.completed_at.isoformat() if s.completed_at else None,
            'budgeted_units': s.budgeted_units,
            'actual_units': s.actual_units
        } for s in steps],
        'stats': {
            'total': total,
            'completed': completed,
            'percentage': (completed / total * 100) if total > 0 else 0
        }
    })

@activity_bp.route('/api/<int:activity_id>/step', methods=['POST'])
@login_required
def api_add_activity_step(activity_id):
    """إضافة خطوة جديدة"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if not data.get('title'):
            return jsonify({'success': False, 'error': 'عنوان الخطوة مطلوب'}), 400
        
        last_step = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order.desc()).first()
        next_order = (last_step.order + 1) if last_step else 1
        
        step = ActivityStep(
            activity_id=activity_id,
            order=next_order,
            title=data['title'],
            description=data.get('description', ''),
            is_completed=False
        )
        
        db.session.add(step)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'step_id': step.id,
            'step_order': step.order
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@activity_bp.route('/api/activity-step/<int:step_id>/complete', methods=['POST'])
@login_required
def api_complete_step(step_id):
    """إكمال خطوة"""
    step = ActivityStep.query.get_or_404(step_id)
    
    if not check_activity_access(step.activity_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        step.is_completed = True
        step.completed_at = datetime.utcnow()
        step.completed_by = current_user.id
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@activity_bp.route('/api/activity-step/<int:step_id>', methods=['DELETE'])
@login_required
def api_delete_step(step_id):
    """حذف خطوة"""
    step = ActivityStep.query.get_or_404(step_id)
    
    if not check_activity_access(step.activity_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(step)
        
        # إعادة ترتيب الخطوات المتبقية
        remaining_steps = ActivityStep.query.filter_by(activity_id=step.activity_id).order_by(ActivityStep.order).all()
        for i, s in enumerate(remaining_steps, 1):
            s.order = i
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للمصروفات (Expenses)
# ============================================

@activity_bp.route('/api/<int:activity_id>/expenses', methods=['GET'])
@login_required
def api_activity_expenses(activity_id):
    """جلب مصروفات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    expenses = ActivityExpense.query.filter_by(activity_id=activity_id).order_by(ActivityExpense.expense_date.desc()).all()
    
    total = sum(e.amount for e in expenses)
    approved = sum(e.amount for e in expenses if e.is_approved)
    
    return jsonify({
        'success': True,
        'expenses': [{
            'id': e.id,
            'expense_date': e.expense_date.isoformat(),
            'category': e.category,
            'description': e.description,
            'amount': e.amount,
            'currency': e.currency,
            'is_approved': e.is_approved,
            'units': e.units,
            'receipt_url': e.receipt_url
        } for e in expenses],
        'summary': {
            'total': total,
            'approved': approved,
            'pending': total - approved
        }
    })

@activity_bp.route('/api/<int:activity_id>/expense', methods=['POST'])
@login_required
def api_add_activity_expense(activity_id):
    """إضافة مصروف جديد"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        expense = ActivityExpense(
            activity_id=activity_id,
            expense_date=datetime.strptime(data['date'], '%Y-%m-%d').date() if data.get('date') else date.today(),
            category=data['category'],
            description=data['description'],
            amount=float(data['amount']),
            currency=data.get('currency', 'SAR'),
            units=float(data.get('units', 0)) if data.get('units') else 0,
            is_approved=False,
            created_by=current_user.id
        )
        
        db.session.add(expense)
        db.session.commit()
        
        return jsonify({'success': True, 'expense_id': expense.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@activity_bp.route('/api/expense/<int:expense_id>/approve', methods=['POST'])
@login_required
def api_approve_expense(expense_id):
    """الموافقة على مصروف"""
    expense = ActivityExpense.query.get_or_404(expense_id)
    
    if not check_activity_access(expense.activity_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        expense.is_approved = True
        expense.approved_by = current_user.id
        expense.approved_at = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للمخاطر (Risks)
# ============================================

@activity_bp.route('/api/<int:activity_id>/risks', methods=['GET'])
@login_required
def api_activity_risks(activity_id):
    """جلب مخاطر النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    risks = ActivityRisk.query.filter_by(activity_id=activity_id).all()
    
    return jsonify({
        'success': True,
        'risks': [{
            'id': r.id,
            'title': r.title,
            'description': r.description,
            'risk_level': r.risk_level,
            'probability': r.probability,
            'impact': r.impact,
            'status': r.status,
            'mitigation_plan': r.mitigation_plan,
            'contingency_plan': r.contingency_plan,
            'schedule_impact': r.schedule_impact,
            'units_impact': r.units_impact
        } for r in risks]
    })

@activity_bp.route('/api/<int:activity_id>/risk', methods=['POST'])
@login_required
def api_add_activity_risk(activity_id):
    """إضافة خطر جديد"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        risk = ActivityRisk(
            activity_id=activity_id,
            title=data['title'],
            description=data.get('description'),
            risk_level=data.get('risk_level', 'medium'),
            probability=int(data.get('probability', 50)),
            impact=data.get('impact', 'medium'),
            mitigation_plan=data.get('mitigation_plan'),
            contingency_plan=data.get('contingency_plan'),
            schedule_impact=int(data.get('schedule_impact', 0)),
            units_impact=float(data.get('units_impact', 0)),
            status='identified',
            created_by=current_user.id
        )
        
        db.session.add(risk)
        db.session.commit()
        
        return jsonify({'success': True, 'risk_id': risk.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للموارد (Resources)
# ============================================

@activity_bp.route('/api/<int:activity_id>/resources', methods=['GET'])
@login_required
def api_activity_resources(activity_id):
    """جلب موارد النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
    
    return jsonify({
        'success': True,
        'resources': [{
            'id': r.id,
            'resource_id': r.resource_id,
            'resource_name': r.resource.name if r.resource else None,
            'resource_type': r.resource.resource_type if r.resource else None,
            'planned_quantity': r.planned_quantity,
            'actual_quantity': r.actual_quantity,
            'planned_cost': r.planned_cost,
            'actual_cost': r.actual_cost
        } for r in resources]
    })

@activity_bp.route('/api/<int:activity_id>/resource', methods=['POST'])
@login_required
def api_add_activity_resource(activity_id):
    """إضافة مورد للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        resource = ActivityResource(
            activity_id=activity_id,
            resource_id=data['resource_id'],
            planned_quantity=float(data.get('quantity', 1)),
            planned_cost=float(data.get('total_cost', 0))
        )
        
        db.session.add(resource)
        db.session.commit()
        
        return jsonify({'success': True, 'resource_id': resource.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@activity_bp.route('/api/activity-resource/<int:resource_id>/delete', methods=['POST'])
@login_required
def api_delete_activity_resource(resource_id):
    """حذف مورد من النشاط"""
    resource = ActivityResource.query.get_or_404(resource_id)
    
    if not check_activity_access(resource.activity_id):
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(resource)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للتعليقات (Feedback)
# ============================================

@activity_bp.route('/api/<int:activity_id>/feedback', methods=['GET'])
@login_required
def api_activity_feedback(activity_id):
    """جلب تعليقات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    feedback_list = ActivityFeedback.query.filter_by(activity_id=activity_id).order_by(ActivityFeedback.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'feedback': [{
            'id': f.id,
            'content': f.content,
            'user_id': f.user_id,
            'user_name': f.user.full_name if f.user else None,
            'created_at': f.created_at.isoformat(),
            'attachment_url': f.attachment_url
        } for f in feedback_list]
    })

@activity_bp.route('/api/<int:activity_id>/feedback', methods=['POST'])
@login_required
def api_add_activity_feedback(activity_id):
    """إضافة تعليق جديد"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        feedback = ActivityFeedback(
            activity_id=activity_id,
            user_id=current_user.id,
            content=data['content']
        )
        
        db.session.add(feedback)
        db.session.commit()
        
        return jsonify({'success': True, 'feedback_id': feedback.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للمستندات (Documents)
# ============================================

@activity_bp.route('/api/<int:activity_id>/documents', methods=['GET'])
@login_required
def api_activity_documents(activity_id):
    """جلب مستندات النشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    documents = ActivityDocument.query.filter_by(activity_id=activity_id).all()
    
    return jsonify({
        'success': True,
        'documents': [{
            'id': d.id,
            'filename': d.filename,
            'original_filename': d.original_filename,
            'title': d.title,
            'file_url': d.file_url,
            'file_size': d.file_size,
            'uploaded_by': d.uploader.full_name if d.uploader else None,
            'uploaded_at': d.uploaded_at.isoformat(),
            'requires_approval': d.requires_approval,
            'approval_status': d.approval_status
        } for d in documents]
    })

@activity_bp.route('/api/<int:activity_id>/document/upload', methods=['POST'])
@login_required
def api_upload_activity_document(activity_id):
    """رفع مستند للنشاط"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'لم يتم رفع ملف'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'لم يتم اختيار ملف'}), 400
    
    try:
        filename = secure_filename(file.filename)
        upload_folder = os.path.join('static', 'uploads', 'activity_documents', str(activity_id))
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        document = ActivityDocument(
            activity_id=activity_id,
            filename=filename,
            original_filename=file.filename,
            title=request.form.get('title'),
            description=request.form.get('description'),
            file_url=f"/static/uploads/activity_documents/{activity_id}/{filename}",
            file_size=os.path.getsize(file_path),
            uploaded_by=current_user.id,
            requires_approval=request.form.get('requires_approval') == 'on'
        )
        
        db.session.add(document)
        db.session.commit()
        
        return jsonify({'success': True, 'document_id': document.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# API Routes للعلاقات (Relationships)
# ============================================

@activity_bp.route('/api/relationship/<int:rel_id>', methods=['PUT'])
@login_required
def api_update_relationship(rel_id):
    """تحديث علاقة"""
    rel = ActivityRelationship.query.get_or_404(rel_id)
    
    project = Project.query.get(rel.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if 'relationship_type' in data:
            rel.relationship_type = data['relationship_type']
        if 'lag' in data:
            rel.lag_days = float(data['lag'])
        if 'lag_type' in data:
            rel.lag_type = data['lag_type']
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@activity_bp.route('/api/activity/<int:activity_id>/predecessor', methods=['POST'])
@login_required
def api_add_predecessor(activity_id):
    """إضافة علاقة سابقة"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if would_create_circular_relationship(data['predecessor_id'], activity_id):
            return jsonify({'success': False, 'error': 'علاقة دائرية'}), 400
        
        existing = ActivityRelationship.query.filter_by(
            project_id=activity.project_id,
            predecessor_id=data['predecessor_id'],
            successor_id=activity_id
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'العلاقة موجودة مسبقاً'}), 400
        
        relationship = ActivityRelationship(
            project_id=activity.project_id,
            predecessor_id=data['predecessor_id'],
            successor_id=activity_id,
            relationship_type=data.get('relationship_type', 'FS'),
            lag_days=float(data.get('lag', 0)),
            lag_type=data.get('lag_type', 'days')
        )
        
        db.session.add(relationship)
        db.session.commit()
        
        return jsonify({'success': True, 'relationship_id': relationship.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@activity_bp.route('/api/activity/<int:activity_id>/successor', methods=['POST'])
@login_required
def api_add_successor(activity_id):
    """إضافة علاقة لاحقة"""
    activity = check_activity_access(activity_id)
    if not activity:
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        if would_create_circular_relationship(activity_id, data['successor_id']):
            return jsonify({'success': False, 'error': 'علاقة دائرية'}), 400
        
        existing = ActivityRelationship.query.filter_by(
            project_id=activity.project_id,
            predecessor_id=activity_id,
            successor_id=data['successor_id']
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'العلاقة موجودة مسبقاً'}), 400
        
        relationship = ActivityRelationship(
            project_id=activity.project_id,
            predecessor_id=activity_id,
            successor_id=data['successor_id'],
            relationship_type=data.get('relationship_type', 'FS'),
            lag_days=float(data.get('lag', 0)),
            lag_type=data.get('lag_type', 'days')
        )
        
        db.session.add(relationship)
        db.session.commit()
        
        return jsonify({'success': True, 'relationship_id': relationship.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@activity_bp.route('/api/relationship/<int:rel_id>', methods=['DELETE'])
@login_required
def api_delete_relationship(rel_id):
    """حذف علاقة"""
    rel = ActivityRelationship.query.get_or_404(rel_id)
    
    project = Project.query.get(rel.project_id)
    if project.created_by != current_user.id and current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        db.session.delete(rel)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
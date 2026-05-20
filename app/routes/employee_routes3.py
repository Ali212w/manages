"""
employee_routes.py - مسارات الموظفين والمستخدمين العاديين
"""
from flask import render_template, request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import login_required, current_user
from app.models import db, User, Project, Notification
from app.models import Task, TaskAssignment, TaskPlanning, TaskExecution, TaskProgress
from app.models import ProjectDates, ProjectProgress,TaskVerification
from app.models import ProjectDocument
from app.models import Activity,ActivityStep,ActivityResource,ActivityExpense,ActivityDocument,ResourceRequest,ResourceRequestItem,TaskRequirement,TaskRequirementVerification
# from app.routes import employee_bp
from datetime import datetime, date, timedelta
from functools import wraps
from sqlalchemy import or_, and_
from app.services.update_service import UpdateService
import os
# ============================================
# دوال مساعدة
# ============================================
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
    """الحصول على مهام المستخدم حسب دوره"""
    if user.role == 'supervisor':
        # المشرف يرى المهام التي يشرف عليها
        return Task.query.filter_by(supervisor_id=user.id).all()
    elif user.role == 'delegate':
        # المندوب يرى المهام الموكلة إليه
        return Task.query.filter_by(delegate_id=user.id).all()
    else:  # employee
        # الموظف العادي يرى المهام المعينة له
        assignments = TaskAssignment.query.filter_by(user_id=user.id).all()
        return [a.task for a in assignments if a.task]

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



# ============================================
# دالة التحقق من صلاحية الوصول للموظفين
# ============================================

def employee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['employee', 'delegate', 'supervisor']:
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

@employee_bp.before_request
def check_authentication():
    """التحقق من المصادقة قبل كل طلب للموظفين"""
    if not current_user.is_authenticated:
        flash('يرجى تسجيل الدخول أولاً', 'warning')
        return redirect(url_for('auth.login', next=request.path))
    
    # التحقق من أن المستخدم لديه الصلاحية المناسبة
    if current_user.role not in ['employee', 'delegate', 'supervisor','client']:
        flash('غير مصرح بالوصول إلى هذه الصفحة', 'danger')
        return redirect(url_for('auth.index'))

# ============================================
# قبل كل طلب - تحميل معلومات المستخدم
# ============================================

@employee_bp.before_request
def load_user_data():
    """تحميل بيانات المستخدم قبل كل طلب"""
    if current_user.is_authenticated:
        g.user = current_user
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        
        # حساب مهام اليوم - ✅ باستخدام الدوال المساعدة
        user_tasks = get_user_tasks(current_user)
        g.today_tasks = sum(1 for task in user_tasks if is_today(get_task_planned_date(task)))
        g.unread_messages = 0
    else:
        g.user = None
        g.notifications_count = 0
        g.today_tasks = 0
        g.unread_messages = 0

# ============================================
# لوحة التحكم الرئيسية للموظف
# ============================================

@employee_bp.route('/')
@login_required
@employee_required
def dashboard():
    """لوحة تحكم الموظف الرئيسية"""
    
    # المهام الخاصة بالمستخدم حسب دوره
    my_tasks = get_user_tasks(current_user)
    
    # إحصائيات حسب الدور
    supervised_count = 0
    delegate_count = 0
    assigned_count = 0
    
    if current_user.role == 'supervisor':
        supervised_count = len(my_tasks)
    elif current_user.role == 'delegate':
        delegate_count = len(my_tasks)
    else:  # employee
        assigned_count = TaskAssignment.query.filter_by(user_id=current_user.id).count()
    
    # إحصائيات المهام
    total_tasks = len(my_tasks)
    completed_tasks = len([t for t in my_tasks if t.status == 'completed'])
    in_progress_tasks = len([t for t in my_tasks if t.status == 'in_progress'])
    pending_tasks = len([t for t in my_tasks if t.status == 'pending'])
    
    stats = {
        'total_tasks': total_tasks,
        'completed_tasks': completed_tasks,
        'in_progress_tasks': in_progress_tasks,
        'pending_tasks': pending_tasks,
        'supervised_count': supervised_count,
        'delegate_count': delegate_count,
        'assigned_count': assigned_count
    }
    
    # المهام النشطة اليوم
    today = date.today()
    today_tasks = []
    for task in my_tasks:
        planned_start = get_task_planned_date(task)
        planned_end = get_task_planned_end(task)
        
        if planned_start and planned_end:
            # ✅ planned_start و planned_end هما already date objects
            if planned_start <= today <= planned_end:
                today_tasks.append(task)
    
    # المشاريع التي يشارك فيها المستخدم
    project_ids = set()
    for task in my_tasks:
        if task.project_id:
            project_ids.add(task.project_id)
    
    projects = Project.query.filter(Project.id.in_(project_ids)).limit(5).all() if project_ids else []
    
    # آخر الإشعارات
    recent_notifications = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    # أداء المستخدم
    performance = {
        'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
        'on_time_rate': 85,  # يمكن حسابها لاحقاً
        'quality_score': 4.5  # يمكن حسابها لاحقاً
    }
    
    return render_template('employee/dashboard.html',
                         stats=stats,
                         my_tasks=my_tasks[:5],
                         today_tasks=today_tasks,
                         projects=projects,
                         recent_notifications=recent_notifications,
                         performance=performance,
                         now=datetime.now())

# ============================================
# المهام الخاصة بي
# ============================================

@employee_bp.route('/my-tasks')
@login_required
@employee_required
def my_tasks():
    """عرض جميع المهام الخاصة بي"""
    
    # الحصول على المهام حسب الدور
    tasks = get_user_tasks(current_user)
    
    if current_user.role == 'supervisor':
        view_type = 'supervised'
    elif current_user.role == 'delegate':
        view_type = 'delegated'
    else:  # employee
        view_type = 'assigned'
    
    # ترتيب المهام حسب التاريخ
    tasks.sort(key=lambda x: get_task_planned_date(x) or datetime.max)
    
    # تصنيف المهام
    pending_tasks = [t for t in tasks if t.status == 'pending']
    in_progress_tasks = [t for t in tasks if t.status == 'in_progress']
    completed_tasks = [t for t in tasks if t.status == 'completed']
    
    overdue_tasks = []
    today = date.today()
    for task in tasks:
        if task.status in ['pending', 'in_progress']:
            planned_end = get_task_planned_end(task)
            if planned_end and planned_end < today:
                overdue_tasks.append(task)
    
    return render_template('employee/tasks/index.html',
                         tasks=tasks,
                         pending_tasks=pending_tasks,
                         in_progress_tasks=in_progress_tasks,
                         completed_tasks=completed_tasks,
                         overdue_tasks=overdue_tasks,
                         view_type=view_type)

@employee_bp.route('/tasks/<int:task_id>')
@login_required
@employee_required
def view_task(task_id):
    """عرض تفاصيل المهمة"""
    
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
    
    return render_template('employee/tasks/view.html',
                         task=task,
                         assignments=assignments,
                         can_update=can_update,
                         planned_start=planned_start,
                         planned_end=planned_end,
                         progress=progress)


# ============================================
# API Routes للموظفين
# ============================================

@employee_bp.route('/api/tasks/<int:task_id>/start', methods=['POST'])
@login_required
@employee_required
def api_task_start(task_id):
    """API لبدء مهمة"""
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
                    'pending_requirements': True
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
        
        db.session.commit()
        
        # إنشاء إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != current_user.id:
            notification = Notification(
                user_id=task.supervisor_id,
                title='بدء مهمة',
                message=f'بدأ {current_user.full_name} في تنفيذ المهمة: {task.task_name}',
                notification_type='task_started',
                related_task_id=task.id,
                related_project_id=task.project_id
            )
            db.session.add(notification)
            db.session.commit()
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        return jsonify({
            'success': True,
            'message': 'تم بدء المهمة بنجاح',
            'task': {
                'id': task.id,
                'status': task.status,
                'progress': task.progress.progress_percentage if task.progress else 0
            }
        })
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in api_task_start: {str(e)}")
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
        
        task.status = 'paused'
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم إيقاف المهمة مؤقتاً'})
        
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
        
        return jsonify({'success': True, 'message': 'تم استئناف المهمة'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/<int:task_id>/complete', methods=['POST'])
@login_required
@employee_required
def api_task_complete(task_id):
    """API لإكمال مهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        if task.status != 'in_progress':
            return jsonify({'success': False, 'error': 'المهمة ليست قيد التنفيذ'}), 400
        
        data = request.get_json() or {}
        quality = data.get('quality', 'good')
        notes = data.get('notes', '')
        
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
                related_project_id=task.project_id
            )
            db.session.add(notification)
            db.session.commit()
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        return jsonify({'success': True, 'message': 'تم إكمال المهمة بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/<int:task_id>/progress', methods=['POST'])
@login_required
@employee_required
def api_task_progress(task_id):
    """API لتحديث تقدم المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        progress = data.get('progress', 0)
        
        if progress < 0 or progress > 100:
            return jsonify({'success': False, 'error': 'نسبة التقدم يجب أن تكون بين 0 و 100'}), 400
        
        if not task.progress:
            task.progress = TaskProgress(task_id=task.id)
        
        task.progress.progress_percentage = progress
        
        # إذا وصل التقدم 100%، غير الحالة إلى مكتمل
        if progress >= 100 and task.status != 'completed':
            task.status = 'completed'
            if not task.execution:
                task.execution = TaskExecution(task_id=task.id)
            task.execution.actual_finish = datetime.utcnow()
        
        db.session.commit()
        # ✅ تحديث المؤشرات
        if task.activity_id:
            UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.project)
        return jsonify({
            'success': True,
            'progress': progress,
            'status': task.status
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/search')
@login_required
@employee_required
def api_task_search():
    """API للبحث في المهام"""
    try:
        query = request.args.get('q', '')
        if len(query) < 2:
            return jsonify({'success': True, 'tasks': []})
        
        tasks = get_user_tasks(current_user)
        
        # فلترة النتائج حسب الاستعلام
        results = []
        for task in tasks:
            if (query.lower() in task.task_name.lower() or
                (task.project and query.lower() in task.project.name.lower()) or
                (task.task_code and query.lower() in task.task_code.lower())):
                
                results.append({
                    'id': task.id,
                    'name': task.task_name,
                    'code': task.task_code,
                    'project': task.project.name if task.project else None,
                    'status': task.status,
                    'progress': task.progress.progress_percentage if task.progress else 0,
                    'url': url_for('employee.view_task', task_id=task.id)
                })
        
        return jsonify({
            'success': True,
            'tasks': results[:10]  # أقصى 10 نتائج
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
# ============================================
# التقارير اليومية
# ============================================

@employee_bp.route('/daily-reports')
@login_required
@employee_required
def daily_reports():
    """التقارير اليومية الخاصة بي"""
    
    from app.models.task_models import DailyReport
    
    reports = DailyReport.query.filter_by(
        prepared_by=current_user.id
    ).order_by(DailyReport.report_date.desc()).all()
    
    return render_template('employee/reports/daily.html', reports=reports)

@employee_bp.route('/daily-reports/create', methods=['GET', 'POST'])
@login_required
@employee_required
def create_daily_report():
    """إنشاء تقرير يومي"""
    
    from app.models.task_models import DailyReport, DailyReportTask
    
    if request.method == 'POST':
        try:
            report_date = datetime.strptime(request.form.get('report_date'), '%Y-%m-%d').date()
            
            # التحقق من عدم تكرار التقرير
            existing = DailyReport.query.filter_by(
                prepared_by=current_user.id,
                report_date=report_date
            ).first()
            
            if existing:
                flash('لديك تقرير لهذا التاريخ بالفعل', 'danger')
                return redirect(url_for('employee.daily_reports'))
            
            report = DailyReport(
                project_id=request.form.get('project_id'),
                report_date=report_date,
                report_number=f"DR-{datetime.now().strftime('%Y%m%d%H%M%S')}",
                weather_condition=request.form.get('weather_condition'),
                temperature=request.form.get('temperature', type=float),
                humidity=request.form.get('humidity', type=float),
                work_summary=request.form.get('work_summary'),
                completed_work=request.form.get('completed_work'),
                planned_work=request.form.get('planned_work'),
                issues_encountered=request.form.get('issues_encountered'),
                safety_notes=request.form.get('safety_notes'),
                supervisor_notes=request.form.get('supervisor_notes'),
                prepared_by=current_user.id
            )
            
            db.session.add(report)
            db.session.commit()
            
            flash('تم إنشاء التقرير اليومي بنجاح', 'success')
            return redirect(url_for('employee.view_daily_report', report_id=report.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # المشاريع التي يعمل بها المستخدم
    tasks = get_user_tasks(current_user)
    project_ids = set(t.project_id for t in tasks if t.project_id)
    projects = Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []
    
    return render_template('employee/reports/create_daily.html', projects=projects)

@employee_bp.route('/daily-reports/<int:report_id>')
@login_required
@employee_required
def view_daily_report(report_id):
    """عرض تقرير يومي"""
    
    from app.models.task_models import DailyReport
    
    report = DailyReport.query.get_or_404(report_id)
    
    if report.prepared_by != current_user.id:
        flash('غير مصرح بمشاهدة هذا التقرير', 'danger')
        return redirect(url_for('employee.daily_reports'))
    
    return render_template('employee/reports/view.html', report=report)
# app/routes/employee_routes.py - استكمال

# ============================================
# إدارة الأنشطة (Activities)
# ============================================

# app/routes/employee_routes.py

@employee_bp.route('/my-activities')
@login_required
@employee_required
def my_activities():
    """عرض جميع الأنشطة المرتبطة بالمستخدم"""
    
    # الحصول على الأنشطة حسب دور المستخدم
    activities = []
    
    if current_user.role == 'supervisor':
        activities = Activity.query.filter_by(supervisor_id=current_user.id).all()
    elif current_user.role == 'delegate':
        activities = Activity.query.filter_by(delegate_id=current_user.id).all()
    else:  # employee
        tasks = get_user_tasks(current_user)
        activity_ids = set(t.activity_id for t in tasks if t.activity_id)
        activities = Activity.query.filter(Activity.id.in_(activity_ids)).all() if activity_ids else []
    
    # إحصائيات الأنشطة - مع التعامل مع None
    total_activities = len(activities)
    not_started = sum(1 for a in activities if a.status == 'not_started')
    in_progress = sum(1 for a in activities if a.status == 'in_progress')
    completed = sum(1 for a in activities if a.status == 'completed')
    delayed = sum(1 for a in activities if a.status == 'delayed')
    
    # حساب الميزانية والتكاليف مع التعامل مع None
    total_budget = sum(a.planned_cost or 0 for a in activities)
    total_actual = sum(a.actual_cost or 0 for a in activities)
    
    # حساب متوسط التقدم
    if activities:
        avg_progress = sum(a.progress_percentage or 0 for a in activities) / len(activities)
    else:
        avg_progress = 0
    
    stats = {
        'total': total_activities,
        'not_started': not_started,
        'in_progress': in_progress,
        'completed': completed,
        'delayed': delayed,
        'total_budget': total_budget,
        'actual_cost': total_actual,
        'progress': avg_progress
    }
    
    return render_template('employee/activities/index.html',
                         activities=activities,
                         stats=stats,
                         role=current_user.role)


@employee_bp.route('/activities/<int:activity_id>')
@login_required
@employee_required
def view_activity(activity_id):
    """عرض تفاصيل النشاط"""
    
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
    
    # إحصائيات النشاط - مع التعامل مع None
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
                         can_complete=can_complete)


@employee_bp.route('/api/activities/<int:activity_id>/start', methods=['POST'])
@login_required
@employee_required
def api_activity_start(activity_id):
    """بدء تنفيذ النشاط"""
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
        
        # بدء النشاط
        activity.status = 'in_progress'
        activity.actual_start = datetime.utcnow()
        
        db.session.commit()
        
        # إرسال إشعار للمشرف ومدير المشروع
        _notify_activity_started(activity, current_user)
        
        # ✅ تحديث المؤشرات
        UpdateService.update_activity_metrics(activity)
        UpdateService.update_project_metrics(activity.project)
        
        return jsonify({'success': True, 'message': 'تم بدء النشاط بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/complete', methods=['POST'])
@login_required
@employee_required
def api_activity_complete(activity_id):
    """إكمال النشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        if activity.status != 'in_progress':
            return jsonify({'success': False, 'error': 'لا يمكن إكمال نشاط بهذه الحالة'}), 400
        
        # التحقق من اكتمال جميع المهام
        incomplete_tasks = Task.query.filter_by(
            activity_id=activity_id,
            status='not_started'
        ).count()
        
        if incomplete_tasks > 0:
            return jsonify({
                'success': False,
                'error': f'يوجد {incomplete_tasks} مهام غير مكتملة',
                'incomplete_tasks': incomplete_tasks
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
        
        return jsonify({'success': True, 'message': 'تم إكمال النشاط بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/progress', methods=['POST'])
@login_required
@employee_required
def api_activity_progress(activity_id):
    """تحديث تقدم النشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        progress = int(data.get('progress', 0))
        
        if progress < 0 or progress > 100:
            return jsonify({'success': False, 'error': 'نسبة التقدم يجب أن تكون بين 0 و 100'}), 400
        
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
        
        return jsonify({'success': True, 'progress': progress, 'status': activity.status})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/steps', methods=['GET'])
@login_required
@employee_required
def api_activity_steps(activity_id):
    """جلب خطوات النشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _has_activity_access(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        steps = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order).all()
        
        return jsonify({
            'success': True,
            'steps': [{
                'id': s.id,
                'order': s.order,
                'title': s.title,
                'description': s.description,
                'is_completed': s.is_completed,
                'completed_at': s.completed_at.isoformat() if s.completed_at else None
            } for s in steps]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/steps/<int:step_id>/complete', methods=['POST'])
@login_required
@employee_required
def api_activity_step_complete(activity_id, step_id):
    """تحديد خطوة كمكتملة"""
    try:
        step = ActivityStep.query.get_or_404(step_id)
        
        if step.activity_id != activity_id:
            return jsonify({'error': 'الخطوة لا تنتمي لهذا النشاط'}), 400
        
        if not _can_update_activity(step.activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        step.is_completed = True
        step.completed_at = datetime.utcnow()
        step.completed_by = current_user.id
        
        db.session.commit()
        
        # تحديث تقدم النشاط بناءً على الخطوات
        _update_activity_progress_from_steps(step.activity)
        
        return jsonify({'success': True, 'message': 'تم إكمال الخطوة بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة المصروفات (Expenses)
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/expenses', methods=['GET', 'POST'])
@login_required
@employee_required
def api_activity_expenses(activity_id):
    """إدارة مصروفات النشاط"""
    
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
                'receipt_url': e.receipt_url
            } for e in expenses]
        })
    
    else:  # POST - إضافة مصروف جديد
        try:
            data = request.get_json()
            
            expense = ActivityExpense(
                activity_id=activity_id,
                expense_date=datetime.strptime(data.get('date'), '%Y-%m-%d').date(),
                category=data.get('category'),
                description=data.get('description'),
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
            
            return jsonify({'success': True, 'expense_id': expense.id})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500


# ============================================
# إدارة الموارد (Resources)
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/resources', methods=['GET'])
@login_required
@employee_required
def api_activity_resources(activity_id):
    """جلب موارد النشاط"""
    
    activity = Activity.query.get_or_404(activity_id)
    
    if not _has_activity_access(activity, current_user):
        return jsonify({'error': 'غير مصرح'}), 403
    
    resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
    
    return jsonify({
        'success': True,
        'resources': [{
            'id': r.id,
            'resource_id': r.resource_id,
            'name': r.resource.name if r.resource else 'غير محدد',
            'planned_quantity': r.planned_quantity,
            'actual_quantity': r.actual_quantity,
            'remaining_quantity': r.remaining_quantity,
            'unit': r.resource.unit if r.resource else '',
            'cost_per_unit': r.resource.cost_per_unit if r.resource else 0
        } for r in resources]
    })


# ============================================
# إدارة المستندات (Documents)
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/documents', methods=['GET', 'POST'])
@login_required
@employee_required
def api_activity_documents(activity_id):
    """إدارة مستندات النشاط"""
    
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
                'url': d.file_url,
                'uploaded_by': d.uploader.full_name if d.uploader else '',
                'uploaded_at': d.uploaded_at.isoformat()
            } for d in documents]
        })
    
    else:  # POST - رفع مستند جديد
        try:
            file = request.files.get('file')
            if not file:
                return jsonify({'error': 'الملف مطلوب'}), 400
            
            title = request.form.get('title', '')
            description = request.form.get('description', '')
            
            # حفظ الملف
            result = _save_document_file(file, 'activities', activity_id)
            if not result['success']:
                return jsonify({'error': result['error']}), 400
            
            document = ActivityDocument(
                activity_id=activity_id,
                filename=result['filename'],
                original_filename=result['original_filename'],
                title=title or result['original_filename'],
                description=description,
                uploaded_by=current_user.id,
                uploaded_at=datetime.utcnow()
            )
            
            db.session.add(document)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'document': {
                    'id': document.id,
                    'filename': document.original_filename,
                    'url': result['file_url']
                }
            })
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': str(e)}), 500


# ============================================
# التقارير المالية والتنفيذية
# ============================================

# app/routes/employee_routes.py - إضافة دوال مساعدة للتقارير

@employee_bp.route('/activities/<int:activity_id>/financial-report')
@login_required
@employee_required
def activity_financial_report(activity_id):
    """تقرير مالي للنشاط"""
    activity = Activity.query.get_or_404(activity_id)
    
    if not _has_activity_access(activity, current_user):
        flash('غير مصرح', 'danger')
        return redirect(url_for('employee.my_activities'))
    
    # حساب التكاليف - مع التعامل مع None
    total_planned = activity.planned_cost or 0
    total_actual = activity.actual_cost or 0
    variance = total_actual - total_planned
    variance_percentage = (variance / total_planned * 100) if total_planned > 0 else 0
    
    # مصروفات النشاط
    expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
    expenses_by_category = {}
    for exp in expenses:
        category = exp.category or 'Other'
        if category not in expenses_by_category:
            expenses_by_category[category] = 0
        expenses_by_category[category] += exp.amount or 0
    
    # تكاليف الموارد
    resources = ActivityResource.query.filter_by(activity_id=activity_id).all()
    resources_cost = sum((r.actual_quantity or 0) * (r.resource.cost_per_unit or 0 if r.resource else 0) for r in resources)
    
    # تكاليف المهام
    tasks = Task.query.filter_by(activity_id=activity_id).all()
    tasks_cost = sum(t.execution.actual_cost or 0 for t in tasks if t.execution)
    
    return render_template('employee/activities/financial_report.html',
                         activity=activity,
                         total_planned=total_planned,
                         total_actual=total_actual,
                         variance=variance,
                         variance_percentage=variance_percentage,
                         expenses=expenses,
                         expenses_by_category=expenses_by_category,
                         resources_cost=resources_cost,
                         tasks_cost=tasks_cost,
                         now=datetime.now())


@employee_bp.route('/activities/<int:activity_id>/progress-report')
@login_required
@employee_required
def activity_progress_report(activity_id):
    """تقرير تقدم النشاط"""
    activity = Activity.query.get_or_404(activity_id)
    
    if not _has_activity_access(activity, current_user):
        flash('غير مصرح', 'danger')
        return redirect(url_for('employee.my_activities'))
    
    # خطوات النشاط
    steps = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order).all()
    steps_completed = sum(1 for s in steps if s.is_completed)
    steps_progress = (steps_completed / len(steps) * 100) if steps else 0
    
    # المهام
    tasks = Task.query.filter_by(activity_id=activity_id).all()
    tasks_completed = sum(1 for t in tasks if t.status == 'completed')
    tasks_progress = (tasks_completed / len(tasks) * 100) if tasks else 0
    
    # التواريخ
    planned_duration = activity.original_duration
    actual_duration = activity.actual_duration
    remaining_duration = activity.remaining_duration
    
    # التأخير
    is_delayed = False
    delay_days = 0
    if activity.planned_finish and activity.status != 'completed':
        if datetime.now() > activity.planned_finish:
            is_delayed = True
            delay_days = (datetime.now() - activity.planned_finish).days
    
    return render_template('employee/activities/progress_report.html',
                         activity=activity,
                         steps=steps,
                         steps_progress=steps_progress,
                         steps_completed=steps_completed,
                         steps_total=len(steps),
                         tasks=tasks,
                         tasks_progress=tasks_progress,
                         tasks_completed=tasks_completed,
                         tasks_total=len(tasks),
                         planned_duration=planned_duration,
                         actual_duration=actual_duration,
                         remaining_duration=remaining_duration,
                         is_delayed=is_delayed,
                         delay_days=delay_days,
                         now=datetime.now())
# app/routes/employee_routes.py - استكمال

# ============================================
# إدارة خطوات النشاط (Activity Steps)
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/steps/add', methods=['POST'])
@login_required
@employee_required
def api_activity_step_add(activity_id):
    """إضافة خطوة جديدة للنشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        title = data.get('title', '').strip()
        
        if not title:
            return jsonify({'error': 'عنوان الخطوة مطلوب'}), 400
        
        # حساب الترتيب
        last_step = ActivityStep.query.filter_by(activity_id=activity_id).order_by(ActivityStep.order.desc()).first()
        new_order = (last_step.order + 1) if last_step else 1
        
        step = ActivityStep(
            activity_id=activity_id,
            order=new_order,
            title=title,
            description=data.get('description', ''),
            is_completed=False
        )
        
        db.session.add(step)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'step': {
                'id': step.id,
                'order': step.order,
                'title': step.title,
                'description': step.description,
                'is_completed': step.is_completed
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/steps/<int:step_id>', methods=['DELETE'])
@login_required
@employee_required
def api_activity_step_delete(activity_id, step_id):
    """حذف خطوة من النشاط"""
    try:
        step = ActivityStep.query.get_or_404(step_id)
        
        if step.activity_id != activity_id:
            return jsonify({'error': 'الخطوة لا تنتمي لهذا النشاط'}), 400
        
        if not _can_update_activity(step.activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        deleted_order = step.order
        db.session.delete(step)
        
        # إعادة ترتيب الخطوات المتبقية
        remaining_steps = ActivityStep.query.filter(
            ActivityStep.activity_id == activity_id,
            ActivityStep.order > deleted_order
        ).all()
        
        for s in remaining_steps:
            s.order -= 1
        
        db.session.commit()
        
        # تحديث تقدم النشاط
        _update_activity_progress_from_steps(step.activity)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/steps/reorder', methods=['POST'])
@login_required
@employee_required
def api_activity_steps_reorder(activity_id):
    """إعادة ترتيب خطوات النشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        steps_order = data.get('steps', [])
        
        for step_data in steps_order:
            step = ActivityStep.query.get(step_data['id'])
            if step and step.activity_id == activity_id:
                step.order = step_data['order']
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة موارد النشاط (Activity Resources)
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/resources/request', methods=['POST'])
@login_required
@employee_required
def api_activity_resource_request(activity_id):
    """طلب موارد إضافية للنشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_update_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        resource_id = data.get('resource_id')
        quantity = float(data.get('quantity', 0))
        
        if not resource_id or quantity <= 0:
            return jsonify({'error': 'بيانات غير صالحة'}), 400
        
        # إنشاء طلب مورد جديد
        resource_request = ResourceRequest(
            project_id=activity.project_id,
            supplier_id=resource_id,
            required_date=datetime.now().date() + timedelta(days=7),
            notes=f'طلب مورد للنشاط {activity.activity_name}',
            status='pending'
        )
        
        db.session.add(resource_request)
        db.session.flush()
        
        # إضافة بند الطلب
        request_item = ResourceRequestItem(
            request_id=resource_request.id,
            resource_name=activity.activity_name,
            required_quantity=quantity,
            unit='وحدة',
            notes=f'مطلوب للنشاط {activity.activity_name}'
        )
        
        db.session.add(request_item)
        db.session.commit()
        
        # إرسال إشعار لمدير المشروع
        if activity.project.project_manager_id:
            notification = Notification(
                user_id=activity.project.project_manager_id,
                title=f'طلب موارد جديدة - {activity.activity_name}',
                message=f'تم طلب {quantity} وحدة من الموارد للنشاط {activity.activity_name}',
                notification_type='resource_request',
                related_activity_id=activity.id,
                related_project_id=activity.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
        
        return jsonify({'success': True, 'request_id': resource_request.id})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة مصروفات النشاط (Activity Expenses)
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/expenses/<int:expense_id>', methods=['DELETE'])
@login_required
@employee_required
def api_activity_expense_delete(activity_id, expense_id):
    """حذف مصروف من النشاط"""
    try:
        expense = ActivityExpense.query.get_or_404(expense_id)
        
        if expense.activity_id != activity_id:
            return jsonify({'error': 'المصروف لا ينتمي لهذا النشاط'}), 400
        
        if not _can_update_activity(expense.activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        db.session.delete(expense)
        db.session.commit()
        
        # تحديث المؤشرات
        UpdateService.update_activity_metrics(expense.activity)
        UpdateService.update_project_metrics(expense.activity.project)
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/activities/<int:activity_id>/expenses/summary', methods=['GET'])
@login_required
@employee_required
def api_activity_expenses_summary(activity_id):
    """ملخص مصروفات النشاط"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        
        if not _has_activity_access(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        expenses = ActivityExpense.query.filter_by(activity_id=activity_id).all()
        
        total_approved = sum(e.amount for e in expenses if e.is_approved)
        total_pending = sum(e.amount for e in expenses if not e.is_approved)
        
        by_category = {}
        for e in expenses:
            if e.category not in by_category:
                by_category[e.category] = {'approved': 0, 'pending': 0}
            if e.is_approved:
                by_category[e.category]['approved'] += e.amount
            else:
                by_category[e.category]['pending'] += e.amount
        
        return jsonify({
            'success': True,
            'total_approved': total_approved,
            'total_pending': total_pending,
            'by_category': by_category
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة المستندات (Activity Documents)
# ============================================

@employee_bp.route('/api/activities/<int:activity_id>/documents/<int:doc_id>', methods=['DELETE'])
@login_required
@employee_required
def api_activity_document_delete(activity_id, doc_id):
    """حذف مستند من النشاط"""
    try:
        document = ActivityDocument.query.get_or_404(doc_id)
        
        if document.activity_id != activity_id:
            return jsonify({'error': 'المستند لا ينتمي لهذا النشاط'}), 400
        
        if document.uploaded_by != current_user.id and not _can_update_activity(document.activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        # حذف الملف الفعلي
        if document.file_path and os.path.exists(document.file_path):
            os.remove(document.file_path)
        
        db.session.delete(document)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# تقارير الأداء (Performance Reports)
# ============================================

@employee_bp.route('/api/my-performance')
@login_required
@employee_required
def api_my_performance():
    """API لأداء المستخدم"""
    try:
        tasks = get_user_tasks(current_user)
        
        # إحصائيات المهام
        total_tasks = len(tasks)
        completed_tasks = len([t for t in tasks if t.status == 'completed'])
        on_time_tasks = 0
        
        # حساب المهام المنجزة في الوقت المحدد
        for task in tasks:
            if task.status == 'completed' and task.execution and task.planning:
                if task.execution.actual_finish and task.planning.planned_finish:
                    if task.execution.actual_finish <= task.planning.planned_finish:
                        on_time_tasks += 1
        
        # متوسط الجودة
        total_quality = 0
        quality_count = 0
        for task in tasks:
            if task.progress and task.progress.completion_quality:
                quality_map = {'excellent': 5, 'good': 4, 'fair': 3, 'poor': 2}
                total_quality += quality_map.get(task.progress.completion_quality, 0)
                quality_count += 1
        
        avg_quality = total_quality / quality_count if quality_count > 0 else 0
        
        # الأداء الأسبوعي (آخر 4 أسابيع)
        weekly_performance = []
        for i in range(4, 0, -1):
            week_start = datetime.now().date() - timedelta(days=i*7)
            week_end = week_start + timedelta(days=6)
            
            week_tasks = [t for t in tasks if t.created_at and week_start <= t.created_at.date() <= week_end]
            week_completed = len([t for t in week_tasks if t.status == 'completed'])
            
            weekly_performance.append({
                'week': f'الأسبوع {5-i}',
                'completed': week_completed,
                'total': len(week_tasks)
            })
        
        return jsonify({
            'success': True,
            'performance': {
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
                'on_time_rate': (on_time_tasks / completed_tasks * 100) if completed_tasks > 0 else 0,
                'avg_quality': round(avg_quality, 1),
                'weekly_performance': weekly_performance
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة المهام (Tasks) - دوال إضافية
# ============================================

@employee_bp.route('/api/tasks/<int:task_id>/requirements', methods=['GET'])
@login_required
@employee_required
def api_task_requirements(task_id):
    """جلب متطلبات المهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        requirements = TaskRequirement.query.filter_by(task_id=task_id, is_active=True).all()
        
        # جلب حالة كل متطلب
        requirements_data = []
        for req in requirements:
            verification = TaskRequirementVerification.query.filter_by(
                requirement_id=req.id,
                user_id=current_user.id
            ).order_by(TaskRequirementVerification.submitted_at.desc()).first()
            
            requirements_data.append({
                'id': req.id,
                'description': req.description,
                'type': req.requirement_type,
                'is_mandatory': req.is_mandatory,
                'status': verification.status if verification else 'pending',
                'verified_value': verification.verified_value if verification else None,
                'verified_at': verification.verified_at.isoformat() if verification and verification.verified_at else None
            })
        
        return jsonify({
            'success': True,
            'requirements': requirements_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@employee_bp.route('/api/tasks/<int:task_id>/requirements/verify', methods=['POST'])
@login_required
@employee_required
def api_task_requirement_verify(task_id):
    """تقديم طلب تحقق لمتطلب مهمة"""
    try:
        task = Task.query.get_or_404(task_id)
        
        if not has_task_access(task, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        requirement_id = data.get('requirement_id')
        value = data.get('value', '')
        notes = data.get('notes', '')
        
        # التحقق من وجود المتطلب
        requirement = TaskRequirement.query.get_or_404(requirement_id)
        
        # إنشاء طلب تحقق
        verification = TaskRequirementVerification(
            requirement_id=requirement_id,
            task_id=task_id,
            user_id=current_user.id,
            verified_value=value,
            notes=notes,
            status='pending'
        )
        
        db.session.add(verification)
        db.session.commit()
        
        # إشعار للمشرف
        if task.supervisor_id:
            notification = Notification(
                user_id=task.supervisor_id,
                title=f'طلب تحقق - {task.task_name}',
                message=f'قدم {current_user.full_name} طلب تحقق للمتطلب: {requirement.description}',
                notification_type='verification_request',
                related_task_id=task.id,
                related_project_id=task.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم تقديم طلب التحقق بنجاح'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# إدارة المهام الجماعية (Bulk Operations)
# ============================================

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
            if not task or not has_task_access(task, current_user):
                failed_tasks.append({'id': task_id, 'reason': 'غير مصرح'})
                continue
            
            if task.status != 'pending':
                failed_tasks.append({'id': task_id, 'reason': 'المهمة ليست في حالة انتظار'})
                continue
            
            # بدء المهمة
            task.status = 'in_progress'
            if not task.execution:
                task.execution = TaskExecution(task_id=task.id)
            task.execution.actual_start = datetime.utcnow()
            
            started_tasks.append(task_id)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'started': started_tasks,
            'failed': failed_tasks,
            'message': f'تم بدء {len(started_tasks)} مهمة'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# ============================================
# لوحة تحكم المشرف (Supervisor Dashboard)
# ============================================

@employee_bp.route('/supervisor/dashboard')
@login_required
@supervisor_required
def supervisor_dashboard():
    """لوحة تحكم خاصة بالمشرف"""
    
    # المهام تحت الإشراف
    supervised_tasks = Task.query.filter_by(supervisor_id=current_user.id).all()
    
    # إحصائيات المهام
    total = len(supervised_tasks)
    completed = len([t for t in supervised_tasks if t.status == 'completed'])
    in_progress = len([t for t in supervised_tasks if t.status == 'in_progress'])
    pending = len([t for t in supervised_tasks if t.status == 'pending'])
    overdue = len([t for t in supervised_tasks if t.is_delayed])
    
    # الأنشطة تحت الإشراف
    supervised_activities = Activity.query.filter_by(supervisor_id=current_user.id).all()
    
    # إحصائيات الأنشطة
    activities_total = len(supervised_activities)
    activities_completed = len([a for a in supervised_activities if a.status == 'completed'])
    activities_in_progress = len([a for a in supervised_activities if a.status == 'in_progress'])
    
    # طلبات التحقق المعلقة
    pending_verifications = TaskRequirementVerification.query.filter(
        TaskRequirementVerification.status == 'pending'
    ).join(Task).filter(Task.supervisor_id == current_user.id).all()
    
    return render_template('employee/supervisor/dashboard.html',
                         stats={
                             'total_tasks': total,
                             'completed_tasks': completed,
                             'in_progress_tasks': in_progress,
                             'pending_tasks': pending,
                             'overdue_tasks': overdue,
                             'total_activities': activities_total,
                             'completed_activities': activities_completed,
                             'in_progress_activities': activities_in_progress,
                             'pending_verifications': len(pending_verifications)
                         },
                         recent_tasks=supervised_tasks[:10],
                         pending_verifications=pending_verifications[:10])


# app/routes/employee_routes.py

@employee_bp.route('/supervisor/verifications')
@login_required
@supervisor_required
def supervisor_verifications():
    """عرض طلبات التحقق المعلقة والسابقة"""
    
    # جلب جميع طلبات التحقق للمهام التي يشرف عليها المستخدم
    verifications = TaskRequirementVerification.query.filter(
        TaskRequirementVerification.status.in_(['pending', 'verified', 'rejected'])
    ).join(Task).filter(Task.supervisor_id == current_user.id).order_by(
        TaskRequirementVerification.submitted_at.desc()
    ).all()
    
    # إضافة معلومات إضافية لكل طلب
    for v in verifications:
        # إضافة اسم المستخدم الذي قام بالموافقة/الرفض
        if v.verified_by:
            from app.models.core_models import User
            v.verified_by_user = User.query.get(v.verified_by)
        else:
            v.verified_by_user = None
    
    return render_template('employee/supervisor/verifications.html', verifications=verifications)

@employee_bp.route('/supervisor/verifications/<int:verification_id>/approve', methods=['POST'])
@login_required
@supervisor_required
def supervisor_approve_verification(verification_id):
    """الموافقة على طلب تحقق"""
    try:
        verification = TaskRequirementVerification.query.get_or_404(verification_id)
        task = verification.task
        
        if task.supervisor_id != current_user.id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        approved = data.get('approved', False)
        notes = data.get('notes', '')
        
        if approved:
            verification.status = 'verified'
            verification.verified_at = datetime.utcnow()
            verification.verified_by = current_user.id
            verification.notes = notes
            
            # تحديث تقدم المهمة
            _update_task_progress_from_requirements(task)
        else:
            verification.status = 'rejected'
            verification.verified_at = datetime.utcnow()
            verification.verified_by = current_user.id
            verification.notes = notes
        
        db.session.commit()
        
        # إشعار للمستخدم
        notification = Notification(
            user_id=verification.user_id,
            title=f'نتيجة طلب التحقق - {task.task_name}',
            message=f'تم {"الموافقة على" if approved else "رفض"} طلب التحقق الخاص بك',
            notification_type='verification_result',
            related_task_id=task.id,
            related_project_id=task.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


def _update_task_progress_from_requirements(task):
    """تحديث تقدم المهمة بناءً على المتطلبات"""
    requirements = TaskRequirement.query.filter_by(task_id=task.id, is_active=True).all()
    if requirements:
        verified_count = TaskRequirementVerification.query.filter(
            TaskRequirementVerification.requirement_id.in_([r.id for r in requirements]),
            TaskRequirementVerification.status == 'verified'
        ).count()
        
        progress = (verified_count / len(requirements)) * 100
        if task.progress:
            task.progress.progress_percentage = progress
        else:
            task.progress = TaskProgress(task_id=task.id, progress_percentage=progress)
        
        if progress >= 100 and task.status != 'completed':
            task.status = 'completed'
            if not task.execution:
                task.execution = TaskExecution(task_id=task.id)
            task.execution.actual_finish = datetime.utcnow()
        
        db.session.commit()


# ============================================
# دوال مساعدة إضافية
# ============================================

def get_user_activities(user):
    """الحصول على الأنشطة المرتبطة بالمستخدم"""
    activities = []
    
    if user.role == 'supervisor':
        activities = Activity.query.filter_by(supervisor_id=user.id).all()
    elif user.role == 'delegate':
        activities = Activity.query.filter_by(delegate_id=user.id).all()
    else:
        tasks = get_user_tasks(user)
        activity_ids = set(t.activity_id for t in tasks if t.activity_id)
        activities = Activity.query.filter(Activity.id.in_(activity_ids)).all() if activity_ids else []
    
    return activities


def get_user_projects(user):
    """الحصول على المشاريع المرتبطة بالمستخدم"""
    tasks = get_user_tasks(user)
    project_ids = set(t.project_id for t in tasks if t.project_id)
    return Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []


def get_user_activity_stats(user):
    """الحصول على إحصائيات الأنشطة للمستخدم"""
    activities = get_user_activities(user)
    
    return {
        'total': len(activities),
        'not_started': sum(1 for a in activities if a.status == 'not_started'),
        'in_progress': sum(1 for a in activities if a.status == 'in_progress'),
        'completed': sum(1 for a in activities if a.status == 'completed'),
        'delayed': sum(1 for a in activities if a.status == 'delayed'),
        'total_budget': sum(a.planned_cost or 0 for a in activities),
        'actual_cost': sum(a.actual_cost or 0 for a in activities),
        'progress': sum(a.progress_percentage or 0 for a in activities) / len(activities) if activities else 0
    }

# ============================================
# دوال مساعدة (Helper Functions)
# ============================================

def _has_activity_access(activity, user):
    """التحقق من صلاحية الوصول للنشاط"""
    if user.role == 'supervisor' and activity.supervisor_id == user.id:
        return True
    if user.role == 'delegate' and activity.delegate_id == user.id:
        return True
    if user.role == 'employee':
        # التحقق من وجود مهام للمستخدم في هذا النشاط
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


def _check_activity_resources(activity):
    """التحقق من توفر موارد النشاط"""
    from app.models.primavera_models import Resource
    
    missing = []
    resources = ActivityResource.query.filter_by(activity_id=activity.id).all()
    
    for res in resources:
        resource = Resource.query.get(res.resource_id)
        if resource and resource.available_quantity < res.planned_quantity:
            missing.append({
                'name': resource.name,
                'required': res.planned_quantity,
                'available': resource.available_quantity,
                'shortage': res.planned_quantity - resource.available_quantity
            })
    
    return missing


def _update_activity_progress_from_steps(activity):
    """تحديث تقدم النشاط بناءً على الخطوات"""
    steps = ActivityStep.query.filter_by(activity_id=activity.id).all()
    if steps:
        completed = sum(1 for s in steps if s.is_completed)
        progress = (completed / len(steps)) * 100
        activity.progress_percentage = progress
        
        if progress >= 100:
            activity.status = 'completed'
            activity.actual_finish = datetime.utcnow()
        elif progress > 0 and activity.status == 'not_started':
            activity.status = 'in_progress'
            activity.actual_start = datetime.utcnow()
        
        db.session.commit()

def _update_activity_metrics(activity):
    """تحديث مؤشرات النشاط"""
    try:
        # تحديث التقدم من الخطوات
        steps = ActivityStep.query.filter_by(activity_id=activity.id).all()
        if steps:
            completed = sum(1 for s in steps if s.is_completed)
            progress = (completed / len(steps)) * 100
            activity.progress_percentage = progress
        
        # تحديث التكاليف
        total_planned = 0
        total_actual = 0
        
        # تكاليف الموارد
        for resource_assign in activity.resources:
            planned = resource_assign.planned_quantity * (resource_assign.resource.cost_per_unit if resource_assign.resource else 0)
            actual = resource_assign.actual_quantity * (resource_assign.resource.cost_per_unit if resource_assign.resource else 0)
            total_planned += planned or 0
            total_actual += actual or 0
        
        # تكاليف المهام
        for task in activity.tasks:
            if task.execution:
                total_planned += task.execution.planned_cost or 0
                total_actual += task.execution.actual_cost or 0
        
        # مصروفات النشاط
        for expense in activity.expenses:
            if expense.is_approved:
                total_actual += expense.amount or 0
            else:
                total_planned += expense.amount or 0
        
        activity.planned_cost = total_planned
        activity.actual_cost = total_actual
        activity.remaining_cost = max(0, total_planned - total_actual)
        activity.cost_variance = total_actual - total_planned
        
        # تحديث الحالة
        if activity.progress_percentage >= 100:
            activity.status = 'completed'
            if not activity.actual_finish:
                activity.actual_finish = datetime.utcnow()
        elif activity.progress_percentage > 0:
            activity.status = 'in_progress'
            if not activity.actual_start:
                activity.actual_start = datetime.utcnow()
        else:
            activity.status = 'not_started'
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"خطأ في تحديث مؤشرات النشاط {activity.id}: {str(e)}")

def _notify_activity_started(activity, user):
    """إرسال إشعار ببدء النشاط"""
    # إشعار للمشرف
    if activity.supervisor_id and activity.supervisor_id != user.id:
        notification = Notification(
            user_id=activity.supervisor_id,
            title=f'بدء نشاط: {activity.activity_name}',
            message=f'تم بدء تنفيذ النشاط بواسطة {user.full_name}',
            notification_type='activity_started',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    # إشعار لمدير المشروع
    if activity.project and activity.project.project_manager_id:
        notification = Notification(
            user_id=activity.project.project_manager_id,
            title=f'بدء نشاط: {activity.activity_name}',
            message=f'تم بدء تنفيذ النشاط في مشروع {activity.project.name}',
            notification_type='activity_started',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    db.session.commit()


def _notify_activity_completed(activity, user):
    """إرسال إشعار بإكمال النشاط"""
    # إشعار للمشرف
    if activity.supervisor_id and activity.supervisor_id != user.id:
        notification = Notification(
            user_id=activity.supervisor_id,
            title=f'إكمال نشاط: {activity.activity_name}',
            message=f'تم إكمال تنفيذ النشاط بواسطة {user.full_name}',
            notification_type='activity_completed',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    # إشعار لمدير المشروع
    if activity.project and activity.project.project_manager_id:
        notification = Notification(
            user_id=activity.project.project_manager_id,
            title=f'إكمال نشاط: {activity.activity_name}',
            message=f'تم إكمال تنفيذ النشاط في مشروع {activity.project.name}',
            notification_type='activity_completed',
            related_link=url_for('employee.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
    
    db.session.commit()


def _save_document_file(file, folder, activity_id):
    """حفظ ملف المستند"""
    import os
    import uuid
    from werkzeug.utils import secure_filename
    from flask import current_app, url_for
    
    try:
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        upload_path = os.path.join(current_app.root_path, 'static', 'uploads', folder, str(activity_id))
        os.makedirs(upload_path, exist_ok=True)
        
        file_path = os.path.join(upload_path, unique_filename)
        file.save(file_path)
        
        file_url = url_for('static', filename=f'uploads/{folder}/{activity_id}/{unique_filename}')
        
        return {
            'success': True,
            'filename': unique_filename,
            'original_filename': filename,
            'file_url': file_url,
            'file_path': file_path
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}
# ============================================
# الإشعارات
# ============================================

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

# ============================================
# المشاريع التي يشارك بها المستخدم
# ============================================

@employee_bp.route('/my-projects')
@login_required
@employee_required
def my_projects():
    """المشاريع التي يشارك بها المستخدم"""
    
    tasks = get_user_tasks(current_user)
    project_ids = set(t.project_id for t in tasks if t.project_id)
    projects = Project.query.filter(Project.id.in_(project_ids)).all() if project_ids else []
    
    return render_template('employee/projects/index.html', projects=projects)

@employee_bp.route('/projects/<int:project_id>')
@login_required
@employee_required
def view_project(project_id):
    """عرض تفاصيل المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من أن المستخدم يشارك في المشروع
    tasks = get_user_tasks(current_user)
    if not any(t.project_id == project_id for t in tasks):
        flash('غير مصرح بمشاهدة هذا المشروع', 'danger')
        return redirect(url_for('employee.my_projects'))
    
    # مهام المستخدم في هذا المشروع
    user_tasks = [t for t in tasks if t.project_id == project_id]
    
    # معلومات المشروع
    progress = 0
    if hasattr(project, 'progress') and project.progress:
        progress = project.progress.progress_percentage
    
    return render_template('employee/projects/view.html',
                         project=project,
                         tasks=user_tasks,
                         progress=progress)

# ============================================
# API Routes
# ============================================

@employee_bp.route('/api/tasks/stats')
@login_required
@employee_required
def api_task_stats():
    """API لإحصائيات المهام"""
    try:
        tasks = get_user_tasks(current_user)
        
        total = len(tasks)
        completed = len([t for t in tasks if t.status == 'completed'])
        in_progress = len([t for t in tasks if t.status == 'in_progress'])
        pending = len([t for t in tasks if t.status == 'pending'])
        
        # حساب المهام المتأخرة
        today = date.today()
        overdue = 0
        for task in tasks:
            if task.status in ['pending', 'in_progress']:
                planned_end = get_task_planned_end(task)
                if planned_end and planned_end < today:
                    overdue += 1
        
        return jsonify({
            'success': True,
            'stats': {
                'total': total,
                'completed': completed,
                'in_progress': in_progress,
                'pending': pending,
                'overdue': overdue
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error in api_task_stats: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@employee_bp.route('/api/tasks/upcoming')
@login_required
@employee_required
def api_upcoming_tasks():
    """API للمهام القادمة"""
    
    tasks = get_user_tasks(current_user)
    today = date.today()
    next_week = today + timedelta(days=7)
    
    upcoming = []
    for task in tasks:
        planned_start = get_task_planned_date(task)
        if planned_start and today <= planned_start <= next_week:
            upcoming.append({
                'id': task.id,
                'name': task.task_name,
                'project': task.project.name if task.project else None,
                'date': planned_start.strftime('%Y-%m-%d') if planned_start else None,
                'status': task.status
            })
    
    upcoming.sort(key=lambda x: x['date'])
    
    return jsonify({'success': True, 'tasks': upcoming[:10]})

@employee_bp.route('/api/notifications/unread-count')
@login_required
def api_unread_notifications():
    """عدد الإشعارات غير المقروءة"""
    
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return jsonify({'count': count})
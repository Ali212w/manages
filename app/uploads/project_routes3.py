"""
project_routes.py - مسارات إدارة المشاريع
"""
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file,g,current_app
from flask_login import login_required, current_user
from app.models import db, Project, User, Task,  Activity, BillItem, Client, Consultant,Organization,Notification
# from app.routes import project_bp
from datetime import datetime, date
import json
import os
from app.services.document_parser import DocumentParser
from app.services.task_automation import TaskAutomationService
from werkzeug.utils import secure_filename
from app.services.notification_service import NotificationService

@project_bp.before_request
def load_company():
    if current_user.is_authenticated:
        g.company = Organization.query.get(current_user.org_id)
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        g.delayed_tasks_count = Task.query.join(Project).filter(
            Task.status.in_(['pending', 'in_progress']),
            Task.planned_end_date < date.today()
        ).count()
    else:
        g.company = None
        g.delayed_tasks_count = 0
        g.notifications_count = 0

@project_bp.route('/projects')
@login_required
def index():
    """قائمة المشاريع"""
    
    # الحصول على المشاريع حسب دور المستخدم
    if current_user.role == 'org_admin':
        projects = Project.query.filter_by(org_id=current_user.org_id).all()
    elif current_user.role == 'project_manager':
        projects = Project.query.filter_by(project_manager_id=current_user.id).all()
    else:
        # للمشرفين والمناديب والموظفين: المشاريع التي لديهم فيها مهام
        projects = Project.query.join(Task).filter(
            (Task.supervisor_id == current_user.id) |
            (Task.delegate_id == current_user.id) |
            (Task.assignments.any(user_id=current_user.id))
        ).distinct().all()
    
    # التصفية حسب الحالة
    status_filter = request.args.get('status')
    if status_filter:
        projects = [p for p in projects if p.status == status_filter]
    
    # البحث
    search_query = request.args.get('search')
    if search_query:
        projects = [p for p in projects if 
                   search_query.lower() in p.name.lower() or 
                   search_query in p.project_code]
    
    return render_template('projects/index.html', projects=projects)

@project_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    """إنشاء مشروع جديد"""
    
    # التحقق من الصلاحية
    if current_user.role not in ['org_admin','admin', 'project_manager']:
        flash('غير مصرح بإنشاء مشاريع', 'danger')
        return redirect(url_for('project.index'))
    
    if request.method == 'POST':
        try:
            # جمع بيانات المشروع
            project_data = {
                'org_id': current_user.org_id,
                'project_code': request.form.get('project_code'),
                'project_number': request.form.get('project_number'),
                'name': request.form.get('name'),
                'name_ar': request.form.get('name_ar'),
                'description': request.form.get('description'),
                'project_manager_id': request.form.get('project_manager_id') or current_user.id,
                'site_name': request.form.get('site_name'),
                'site_name_ar': request.form.get('site_name_ar'),
                'area_name': request.form.get('area_name'),
                'area_name_ar': request.form.get('area_name_ar'),
                'location_address': request.form.get('location_address'),
                'location_coordinates': request.form.get('location_coordinates'),
                'governorate': request.form.get('governorate'),
                'city': request.form.get('city'),
                'contract_number': request.form.get('contract_number'),
                'contract_date': request.form.get('contract_date'),
                'client_id': request.form.get('client_id'),
                'client_project_manager': request.form.get('client_project_manager'),
                'client_phone': request.form.get('client_phone'),
                'client_email': request.form.get('client_email'),
                'consultant_id': request.form.get('consultant_id'),
                'consultant_project_manager': request.form.get('consultant_project_manager'),
                'contract_value': float(request.form.get('contract_value', 0) or 0),
                'estimated_value': float(request.form.get('estimated_value', 0) or 0),
                'planned_start_date': request.form.get('planned_start_date'),
                'planned_end_date': request.form.get('planned_end_date'),
                'project_type': request.form.get('project_type'),
                'project_category': request.form.get('project_category'),
                'project_scale': request.form.get('project_scale'),
                'status': 'planning',
                'created_by': current_user.id
            }
            
            # تحويل التواريخ
            if project_data['contract_date']:
                project_data['contract_date'] = datetime.strptime(project_data['contract_date'], '%Y-%m-%d').date()
            if project_data['planned_start_date']:
                project_data['planned_start_date'] = datetime.strptime(project_data['planned_start_date'], '%Y-%m-%d').date()
            if project_data['planned_end_date']:
                project_data['planned_end_date'] = datetime.strptime(project_data['planned_end_date'], '%Y-%m-%d').date()
            
            # إنشاء المشروع
            project = Project(**project_data)
            project.calculate_planned_duration()
            
            db.session.add(project)
            db.session.commit()
            NotificationService.project_created(project, current_user)

            flash('تم إنشاء المشروع بنجاح', 'success')
            return redirect(url_for('project.view', project_id=project.id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # البيانات اللازمة للنموذج
    clients = Client.query.filter_by(org_id=current_user.org_id, is_active=True).all()
    consultants = Consultant.query.filter_by(org_id=current_user.org_id, is_active=True).all()
    project_managers = User.query.filter(
    User.org_id == current_user.org_id,
    User.role.in_(['org_admin','admin', 'project_manager', 'supervisor']),
    User.is_user_active == True
).all()
    return render_template('projects/create.html',
                         clients=clients,
                         consultants=consultants,
                         project_managers=project_managers)

# @project_bp.route('/projects/<int:project_id>/start', methods=['POST'])
# @login_required
# def start_project(project_id):
#     """بدء المشروع"""
#     project = Project.query.get_or_404(project_id)
    
#     if project.project_manager_id != current_user.id and current_user.role != 'org_admin':
#         flash('غير مصرح', 'danger')
#         return redirect(url_for('project.view', project_id=project_id))
    
#     project.status = 'active'
#     project.actual_start_date = datetime.utcnow()
#     db.session.commit()
    
#     # إضافة إشعارات بدء المشروع
#     NotificationService.project_started(project)
    
#     flash('تم بدء المشروع بنجاح', 'success')
#     return redirect(url_for('project.view_proj', project_id=project_id))

@project_bp.route('/my')
@login_required
def my_projects():
    """مشاريعي"""
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    
    # الحصول على مشاريع المستخدم
    query = Project.query.filter_by(project_manager_id=current_user.id)
    
    # الفلاتر
    if request.args.get('status'):
        query = query.filter(Project.status == request.args.get('status'))
    
    # الترقيم
    projects = query.order_by(Project.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('projects/my_projects.html',
                         projects=projects)
@project_bp.route('/calendar')
@login_required
def calendar():
    """تقويم المشاريع"""
    
    # الحصول على المشاريع للتقويم
    projects = Project.query.filter_by(
        org_id=current_user.org_id
    ).filter(
        Project.planned_start_date.isnot(None)
    ).all()
    
    # تحويل المشاريع لتنسيق تقويم
    calendar_events = []
    for project in projects:
        if project.planned_start_date and project.planned_end_date:
            calendar_events.append({
                'id': project.id,
                'title': project.name,
                'start': project.planned_start_date.isoformat(),
                'end': project.planned_end_date.isoformat(),
                'color': get_project_color(project.status),
                'url': url_for('projects.detail', project_id=project.id)
            })
    
    return render_template('projects/project_calendar.html',
                         events=json.dumps(calendar_events))
def get_project_color(status):
    """الحصول على لون المشروع بناءً على حالته"""
    colors = {
        'pending': '#6c757d',    # رمادي
        'planning': '#17a2b8',   # أزرق فاتح
        'active': '#007bff',     # أزرق
        'on_hold': '#ffc107',    # أصفر
        'completed': '#28a745',  # أخضر
        'cancelled': '#dc3545'   # أحمر
    }
    return colors.get(status, '#6c757d')

@project_bp.route('/<int:project_id>')
@login_required
def view(project_id):
    """عرض تفاصيل المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح بالوصول لهذا المشروع', 'danger')
        return redirect(url_for('project.index'))
    
    # الحصول على إحصائيات المشروع
    stats = get_project_stats(project)
    
    # المهام القريبة
    upcoming_tasks = Task.query.filter_by(
        project_id=project.id,
        status=Task.status.in_(['pending', 'in_progress'])
    ).order_by(Task.planned_start_date.asc()).limit(5).all()
    
    # المخاطر
    risks = project.risks[:5] if hasattr(project, 'risks') else []
    
    # القضايا
    issues = project.issues[:5] if hasattr(project, 'issues') else []
    
    # آخر التقارير
    daily_reports = project.daily_reports[:5] if hasattr(project, 'daily_reports') else []
    
    return render_template('projects/view.html',
                         project=project,
                         stats=stats,
                         upcoming_tasks=upcoming_tasks,
                         risks=risks,
                         issues=issues,
                         daily_reports=daily_reports)

def has_project_access(project, user):
    """التحقق من صلاحية الوصول للمشروع"""
    if user.role == 'org_admin' and project.org_id == user.org_id:
        return True
    elif user.role == 'project_manager' and project.project_manager_id == user.id:
        return True
    elif user.role == 'supervisor' and project.id in [t.project_id for t in user.supervised_tasks]:
        return True
    elif user.role == 'delegate' and project.id in [t.project_id for t in user.delegate_tasks]:
        return True
    elif user.role == 'employee' and project.id in [t.project_id for a in user.task_assignments for t in [a.task]]:
        return True
    return False

def get_project_stats(project):
    """الحصول على إحصائيات المشروع"""
    tasks = Task.query.filter_by(project_id=project.id).all()
    
    return {
        'total_tasks': len(tasks),
        'completed_tasks': len([t for t in tasks if t.status == 'completed']),
        'in_progress_tasks': len([t for t in tasks if t.status == 'in_progress']),
        'pending_tasks': len([t for t in tasks if t.status == 'pending']),
        'total_activities': len(project.activities) if hasattr(project, 'activities') else 0,
        'total_bill_items': len(project.bill_items) if hasattr(project, 'bill_items') else 0,
        'total_documents': len(project.documents) if hasattr(project, 'documents') else 0,
        'total_risks': len(project.risks) if hasattr(project, 'risks') else 0,
        'total_issues': len(project.issues) if hasattr(project, 'issues') else 0
    }

@project_bp.route('/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(project_id):
    """تعديل المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not (current_user.role in ['org_admin','admin', 'project_manager'] and 
            (current_user.role == 'admin' or project.project_manager_id == current_user.id)):
        flash('غير مصرح بتعديل هذا المشروع', 'danger')
        return redirect(url_for('project.view', project_id=project_id))
    
    if request.method == 'POST':
        try:
            # تحديث بيانات المشروع
            project.name = request.form.get('name', project.name)
            project.name_ar = request.form.get('name_ar', project.name_ar)
            project.description = request.form.get('description', project.description)
            project.site_name = request.form.get('site_name', project.site_name)
            project.site_name_ar = request.form.get('site_name_ar', project.site_name_ar)
            project.area_name = request.form.get('area_name', project.area_name)
            project.area_name_ar = request.form.get('area_name_ar', project.area_name_ar)
            project.location_address = request.form.get('location_address', project.location_address)
            project.contract_value = float(request.form.get('contract_value', project.contract_value) or 0)
            project.planned_start_date = datetime.strptime(
                request.form.get('planned_start_date', project.planned_start_date.strftime('%Y-%m-%d')),
                '%Y-%m-%d'
            ).date() if request.form.get('planned_start_date') else project.planned_start_date
            project.planned_end_date = datetime.strptime(
                request.form.get('planned_end_date', project.planned_end_date.strftime('%Y-%m-%d')),
                '%Y-%m-%d'
            ).date() if request.form.get('planned_end_date') else project.planned_end_date
            project.status = request.form.get('status', project.status)
            project.priority = request.form.get('priority', project.priority)
            
            project.calculate_planned_duration()
            project.calculate_progress()
            
            db.session.commit()
            flash('تم تحديث المشروع بنجاح', 'success')
            
            return redirect(url_for('project.view', project_id=project_id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    clients = Client.query.filter_by(org_id=current_user.org_id, is_active=True).all()
    consultants = Consultant.query.filter_by(org_id=current_user.org_id, is_active=True).all()
    
    return render_template('projects/edit.html',
                         project=project,
                         clients=clients,
                         consultants=consultants)

@project_bp.route('/<int:project_id>/upload-document', methods=['GET', 'POST'])
@login_required
def upload_document(project_id):
    """رفع مستند للمشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح برفع مستندات لهذا المشروع', 'danger')
        return redirect(url_for('project.view', project_id=project_id))
    
    if request.method == 'POST':
        try:
            # التحقق من وجود الملف
            if 'document' not in request.files:
                flash('لم يتم اختيار ملف', 'danger')
                return redirect(request.url)
            
            file = request.files['document']
            
            if file.filename == '':
                flash('لم يتم اختيار ملف', 'danger')
                return redirect(request.url)
            
            # التحقق من صيغة الملف
            allowed_extensions = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv'}
            filename = secure_filename(file.filename)
            file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            
            if file_extension not in allowed_extensions:
                flash('صيغة الملف غير مدعومة', 'danger')
                return redirect(request.url)
            
            # حفظ الملف
            from app.models import ProjectDocument
            import uuid
            
            upload_folder = current_app.config['UPLOAD_FOLDER']
            documents_folder = os.path.join(upload_folder, 'documents')
            os.makedirs(documents_folder, exist_ok=True)
            
            unique_filename = f"{uuid.uuid4()}_{filename}"
            file_path = os.path.join(documents_folder, unique_filename)
            file.save(file_path)
            
            # إنشاء سجل المستند
            document = ProjectDocument(
                project_id=project_id,
                document_type=request.form.get('document_type', 'other'),
                category=request.form.get('category', 'general'),
                filename=unique_filename,
                original_filename=filename,
                file_extension=file_extension,
                file_size=os.path.getsize(file_path),
                file_path=file_path,
                title=request.form.get('title', filename),
                description=request.form.get('description', ''),
                uploaded_by=current_user.id,
                extraction_status='pending'
            )
            
            db.session.add(document)
            db.session.commit()
            
            # إذا كان الملف جدول كميات، قم بتحليله
            if request.form.get('document_type') == 'bill_of_quantities':
                from services.document_parser import DocumentParser
                parser = DocumentParser(upload_folder)
                
                try:
                    parsed_data = parser.parse_document(file_path, file_extension)
                    parser.save_parsed_data(project_id, parsed_data)
                    
                    document.extraction_status = 'completed'
                    document.extraction_metadata = parsed_data
                    db.session.commit()
                    
                    flash('تم رفع وتحليل المستند بنجاح', 'success')
                    
                except Exception as e:
                    document.extraction_status = 'failed'
                    db.session.commit()
                    flash(f'تم رفع المستند ولكن حدث خطأ في التحليل: {str(e)}', 'warning')
            else:
                flash('تم رفع المستند بنجاح', 'success')
            
            return redirect(url_for('project.view', project_id=project_id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('projects/upload_document.html', project=project)

@project_bp.route('/<int:project_id>/wbs')
@login_required
def wbs(project_id):
    """هيكل تقسيم العمل (WBS)"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح بالوصول لهذا المشروع', 'danger')
        return redirect(url_for('project.index'))
    
    wbs_nodes = WBSNode.query.filter_by(project_id=project_id).order_by(WBSNode.wbs_code).all()
    
    # تنظيم العقد في هيكل شجري
    wbs_tree = build_wbs_tree(wbs_nodes)
    
    return render_template('projects/wbs.html', project=project, wbs_tree=wbs_tree)

def build_wbs_tree(self, wbs_nodes):
    """بناء هيكل شجري لـ WBS"""
    tree = []
    node_dict = {node.id: {'node': node, 'children': []} for node in wbs_nodes}
    
    for node in wbs_nodes:
        if node.parent_id:
            node_dict[node.parent_id]['children'].append(node_dict[node.id])
        else:
            tree.append(node_dict[node.id])
    
    return tree

@project_bp.route('/<int:project_id>/activities')
@login_required
def activities(project_id):
    """أنشطة المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح بالوصول لهذا المشروع', 'danger')
        return redirect(url_for('project.index'))
    
    activities = Activity.query.filter_by(project_id=project_id).order_by(Activity.planned_start_date).all()
    
    return render_template('projects/activities.html', project=project, activities=activities)

@project_bp.route('/<int:project_id>/bill-of-quantities')
@login_required
def bill_of_quantities(project_id):
    """جدول الكميات والمواصفات"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح بالوصول لهذا المشروع', 'danger')
        return redirect(url_for('project.index'))
    
    bill_items = BillItem.query.filter_by(project_id=project_id).order_by(BillItem.item_code).all()
    
    # تنظيم البنود في هيكل شجري
    boq_tree = build_boq_tree(bill_items)
    
    return render_template('projects/bill_of_quantities.html', project=project, boq_tree=boq_tree)

def build_boq_tree(self, bill_items):
    """بناء هيكل شجري لجدول الكميات"""
    tree = []
    item_dict = {item.id: {'item': item, 'children': []} for item in bill_items}
    
    for item in bill_items:
        if item.parent_item_id:
            if item.parent_item_id in item_dict:
                item_dict[item.parent_item_id]['children'].append(item_dict[item.id])
        else:
            tree.append(item_dict[item.id])
    
    return tree

@project_bp.route('/<int:project_id>/risks')
@login_required
def risks(project_id):
    """مخاطر المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح بالوصول لهذا المشروع', 'danger')
        return redirect(url_for('project.index'))
    
    risks = project.risks if hasattr(project, 'risks') else []
    
    return render_template('projects/risks.html', project=project, risks=risks)

@project_bp.route('/<int:project_id>/issues')
@login_required
def issues(project_id):
    """قضايا المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح بالوصول لهذا المشروع', 'danger')
        return redirect(url_for('project.index'))
    
    issues = project.issues if hasattr(project, 'issues') else []
    
    return render_template('projects/issues.html', project=project, issues=issues)

@project_bp.route('/<int:project_id>/reports')
@login_required
def reports(project_id):
    """تقارير المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not has_project_access(project, current_user):
        flash('غير مصرح بالوصول لهذا المشروع', 'danger')
        return redirect(url_for('project.index'))
    
    daily_reports = project.daily_reports if hasattr(project, 'daily_reports') else []
    
    return render_template('projects/reports.html', project=project, daily_reports=daily_reports)

@project_bp.route('/<int:project_id>/start', methods=['POST'])
@login_required
def start_project(project_id):
    """بدء المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not (current_user.role in ['admin', 'project_manager'] and 
            (current_user.role == 'admin' or project.project_manager_id == current_user.id)):
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح ببدء هذا المشروع', 'danger')
            return redirect(url_for('project.view', project_id=project_id))
    
    try:
        if project.status == 'planning':
            project.status = 'active'
            project.actual_start_date = date.today()
            
            db.session.commit()
            
            # إرسال إشعارات
            notify_project_started(project)
            NotificationService.project_started(project)
            if request.is_json:
                return jsonify({'success': True, 'message': 'تم بدء المشروع بنجاح'})
            else:
                flash('تم بدء المشروع بنجاح', 'success')
                
        else:
            message = 'لا يمكن بدء المشروع في حالته الحالية'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
                
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('project.view', project_id=project_id))

def notify_project_started(self, project):
    """إرسال إشعارات بدء المشروع"""
    from app.models import Notification
    
    # إشعار مدير المشروع
    notification = Notification(
        user_id=project.project_manager_id,
        title=f'بدء المشروع: {project.name}',
        message=f'تم بدء المشروع {project.project_code}',
        notification_type='project_started',
        related_project_id=project.id,
        priority='high'
    )
    db.session.add(notification)
    
    # إشعار المشرفين
    supervisors = User.query.join(Task).filter(
        Task.project_id == project.id,
        Task.supervisor_id.isnot(None)
    ).distinct().all()
    
    for supervisor in supervisors:
        notification = Notification(
            user_id=supervisor.id,
            title=f'بدء المشروع: {project.name}',
            message=f'تم بدء المشروع {project.project_code}، الرجاء متابعة المهام',
            notification_type='project_started',
            related_project_id=project.id,
            priority='medium'
        )
        db.session.add(notification)
    
    db.session.commit()

@project_bp.route('/<int:project_id>/complete', methods=['POST'])
@login_required
def complete_project(project_id):
    """إكمال المشروع"""
    
    project = Project.query.get_or_404(project_id)
    
    # التحقق من الصلاحية
    if not (current_user.role in ['admin', 'project_manager'] and 
            (current_user.role == 'admin' or project.project_manager_id == current_user.id)):
        if request.is_json:
            return jsonify({'error': 'غير مصرح'}), 403
        else:
            flash('غير مصرح بإكمال هذا المشروع', 'danger')
            return redirect(url_for('project.view', project_id=project_id))
    
    try:
        if project.status == 'active' and project.progress_percentage >= 100:
            project.status = 'completed'
            project.actual_end_date = date.today()
            
            db.session.commit()
            
            # إرسال إشعارات
            # notify_project_completed(project)
            NotificationService.project_completed(project)
            
            if request.is_json:
                return jsonify({'success': True, 'message': 'تم إكمال المشروع بنجاح'})
            else:
                flash('تم إكمال المشروع بنجاح', 'success')
                
        else:
            message = 'لا يمكن إكمال المشروع، يجب أن يكون نشطاً ومكتملاً 100%'
            if request.is_json:
                return jsonify({'error': message}), 400
            else:
                flash(message, 'warning')
        
    except Exception as e:
        if request.is_json:
            return jsonify({'error': str(e)}), 500
        else:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('project.view', project_id=project_id))

def notify_project_completed(self, project):
    """إرسال إشعارات إكمال المشروع"""
    from app.models import Notification
    
    # إشعار مدير المشروع
    notification = Notification(
        user_id=project.project_manager_id,
        title=f'اكتمال المشروع: {project.name}',
        message=f'تم إكمال المشروع {project.project_code} بنجاح',
        notification_type='project_completed',
        related_project_id=project.id,
        priority='high'
    )
    db.session.add(notification)
    
    # إشعار العميل (إذا كان هناك عميل)
    if project.client_id and project.client:
        # TODO: إرسال بريد إلكتروني للعميل
        
        notification = Notification(
            user_id=project.project_manager_id,  # سيتم إرسال بريد للمدير لإعلام العميل
            title=f'إعلام العميل: اكتمال {project.name}',
            message=f'الرجاء إعلام العميل {project.client.name} بإنهاء المشروع',
            notification_type='client_notification',
            related_project_id=project.id,
            priority='medium'
        )
        db.session.add(notification)
    
    db.session.commit()

# API Routes للمشاريع
@project_bp.route('/api/projects', methods=['GET'])
@login_required
def api_projects():
    """API للحصول على قائمة المشاريع"""
    try:
        # الحصول على المشاريع حسب دور المستخدم
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
        
        projects_data = [{
            'id': p.id,
            'project_code': p.project_code,
            'name': p.name,
            'status': p.status,
            'progress_percentage': p.progress_percentage,
            'planned_start_date': p.planned_start_date.isoformat() if p.planned_start_date else None,
            'planned_end_date': p.planned_end_date.isoformat() if p.planned_end_date else None,
            'contract_value': p.contract_value,
            'manager': p.manager.full_name if p.manager else None
        } for p in projects]
        
        return jsonify({'success': True, 'projects': projects_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@project_bp.route('/api/projects/<int:project_id>', methods=['GET'])
@login_required
def api_project_detail(project_id):
    """API للحصول على تفاصيل المشروع"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # التحقق من الصلاحية
        if not has_project_access(project, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        project_data = {
            'id': project.id,
            'project_code': project.project_code,
            'name': project.name,
            'name_ar': project.name_ar,
            'description': project.description,
            'site_name': project.site_name,
            'site_name_ar': project.site_name_ar,
            'area_name': project.area_name,
            'area_name_ar': project.area_name_ar,
            'location_address': project.location_address,
            'status': project.status,
            'progress_percentage': project.progress_percentage,
            'planned_start_date': project.planned_start_date.isoformat() if project.planned_start_date else None,
            'planned_end_date': project.planned_end_date.isoformat() if project.planned_end_date else None,
            'actual_start_date': project.actual_start_date.isoformat() if project.actual_start_date else None,
            'actual_end_date': project.actual_end_date.isoformat() if project.actual_end_date else None,
            'contract_value': project.contract_value,
            'manager': project.manager.to_dict() if project.manager else None,
            'client': {
                'id': project.client.id,
                'name': project.client.name
            } if project.client else None,
            'stats': get_project_stats(project)
        }
        
        return jsonify({'success': True, 'project': project_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@project_bp.route('/api/projects/<int:project_id>/progress', methods=['PUT'])
@login_required
def api_update_project_progress(project_id):
    """API لتحديث تقدم المشروع"""
    try:
        project = Project.query.get_or_404(project_id)
        
        # التحقق من الصلاحية
        if not has_project_access(project, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        progress = data.get('progress_percentage')
        
        if progress is not None:
            # تحديث تقدم المشروع
            project.progress_percentage = float(progress)
            project.calculate_progress()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'تم تحديث تقدم المشروع',
                'progress_percentage': project.progress_percentage
            }), 200
        else:
            return jsonify({'error': 'قيمة التقدم مطلوبة'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
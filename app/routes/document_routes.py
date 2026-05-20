"""
document_routes.py - مسارات إدارة المستندات
"""
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from app.models import db, ProjectDocument, BillItem, Project, Task
from app.routes import document_bp
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from app.services.document_parser import DocumentParser

@document_bp.context_processor
def inject_document_helpers():
    from app.helpers.document_helpers import get_document_type_label, format_file_size
    
    def document_types_counts():
        if not current_user.is_authenticated:
            return []
        
        # الحصول على المستندات حسب دور المستخدم
        if current_user.role in ['admin', 'org_admin']:
            documents = ProjectDocument.query.join(Project).filter(
                Project.org_id == current_user.org_id
            ).all()
        elif current_user.role == 'project_manager':
            documents = ProjectDocument.query.join(Project).filter(
                Project.project_manager_id == current_user.id
            ).all()
        else:
            projects = Project.query.join(Task).filter(
                (Task.supervisor_id == current_user.id) |
                (Task.delegate_id == current_user.id) |
                (Task.assignments.any(user_id=current_user.id))
            ).distinct().all()
            
            documents = ProjectDocument.query.filter(
                ProjectDocument.project_id.in_([p.id for p in projects])
            ).all()
        
        # حساب التكرارات لكل نوع
        counts = {}
        for d in documents:
            t = d.document_type or 'other'
            counts[t] = counts.get(t, 0) + 1
        
        # إرجاع القائمة كـ (النوع، العدد)
        return list(counts.items())
        
    return dict(
        get_document_type_label=get_document_type_label,
        format_file_size=format_file_size,
        can_delete_document=can_delete_document,
        document_types_counts=document_types_counts
    )

@document_bp.route('/documents')
@login_required
def index():
    """قائمة المستندات"""
    
    # الحصول على المستندات حسب دور المستخدم
    if current_user.role in ['admin', 'org_admin']:
        documents = ProjectDocument.query.join(Project).filter(
            Project.org_id == current_user.org_id
        ).all()
    elif current_user.role == 'project_manager':
        documents = ProjectDocument.query.join(Project).filter(
            Project.project_manager_id == current_user.id
        ).all()
    else:
        # للمشرفين والمناديب والموظفين: المستندات في مشاريعهم
        projects = Project.query.join(Task).filter(
            (Task.supervisor_id == current_user.id) |
            (Task.delegate_id == current_user.id) |
            (Task.assignments.any(user_id=current_user.id))
        ).distinct().all()
        
        documents = ProjectDocument.query.filter(
            ProjectDocument.project_id.in_([p.id for p in projects])
        ).all()
    
    # التصفية حسب النوع
    doc_type = request.args.get('type')
    if doc_type:
        documents = [d for d in documents if d.document_type == doc_type]
    
    # البحث
    search_query = request.args.get('search')
    if search_query:
        documents = [d for d in documents if 
                    search_query.lower() in d.title.lower() or 
                    search_query.lower() in d.filename.lower()]
    
    return render_template('documents/index.html', documents=documents)

@document_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """رفع مستند جديد"""
    
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
            allowed_extensions = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'txt', 'jpg', 'jpeg', 'png'}
            filename = secure_filename(file.filename)
            file_extension = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            
            if file_extension not in allowed_extensions:
                flash('صيغة الملف غير مدعومة', 'danger')
                return redirect(request.url)
            
            # الحصول على المشروع
            project_id = request.form.get('project_id')
            if not project_id:
                flash('يجب اختيار مشروع', 'danger')
                return redirect(request.url)
            
            project = Project.query.get_or_404(project_id)
            
            # التحقق من صلاحية رفع المستند للمشروع
            if not can_upload_to_project(project, current_user):
                flash('غير مصرح برفع مستندات لهذا المشروع', 'danger')
                return redirect(url_for('document.index'))
            
            # حفظ الملف
            from uploads.app import app
            upload_folder = app.config['UPLOAD_FOLDER']
            documents_folder = os.path.join(upload_folder, 'documents')
            os.makedirs(documents_folder, exist_ok=True)
            
            unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
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
                extraction_status='pending',
                requires_approval=bool(request.form.get('requires_approval')),
                access_level=request.form.get('access_level', 'team'),
                is_public=bool(request.form.get('is_public'))
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
            
            return redirect(url_for('document.view', document_id=document.id))
            
        except Exception as e:
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    # الحصول على المشاريع المتاحة
    if current_user.role in ['admin', 'org_admin']:
        projects = Project.query.filter_by(org_id=current_user.org_id).all()
    elif current_user.role == 'project_manager':
        projects = Project.query.filter_by(project_manager_id=current_user.id).all()
    else:
        projects = Project.query.join(Task).filter(
            (Task.supervisor_id == current_user.id) |
            (Task.delegate_id == current_user.id) |
            (Task.assignments.any(user_id=current_user.id))
        ).distinct().all()
    
    return render_template('documents/upload.html', projects=projects)

def can_upload_to_project(project, user):
    """التحقق من صلاحية رفع مستندات للمشروع"""
    if user.role in ['admin', 'org_admin']:
        return project.org_id == user.org_id
    elif user.role == 'project_manager':
        return project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return project.id in [t.project_id for t in user.supervised_tasks]
    elif user.role == 'delegate':
        return project.id in [t.project_id for t in user.delegate_tasks]
    elif user.role == 'employee':
        return project.id in [t.project_id for a in user.task_assignments for t in [a.task]]
    return False

@document_bp.route('/<int:document_id>')
@login_required
def view(document_id):
    """عرض تفاصيل المستند"""
    
    document = ProjectDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if not has_document_access(document, current_user):
        flash('غير مصرح بالوصول لهذا المستند', 'danger')
        return redirect(url_for('document.index'))
    
    # المستندات المرتبطة
    related_documents = ProjectDocument.query.filter_by(
        project_id=document.project_id,
        document_type=document.document_type
    ).filter(ProjectDocument.id != document.id).limit(5).all()
    
    # بنود الجدول المرتبطة (إذا كان جدول كميات)
    bill_items = []
    if document.document_type == 'bill_of_quantities' and hasattr(document, 'bill_items'):
        bill_items = document.bill_items[:10]
    
    return render_template('documents/view.html',
                         document=document,
                         related_documents=related_documents,
                         bill_items=bill_items)

def has_document_access(document, user):
    """التحقق من صلاحية الوصول للمستند"""
    # إذا كان المستند عاماً
    if document.is_public:
        return True
    
    # إذا كان المستند للمؤسسة
    if document.access_level == 'organization':
        return document.project.org_id == user.org_id
    
    # إذا كان المستند للفريق
    if document.access_level == 'team':
        return has_project_access(document.project, user)
    
    # إذا كان المستند مقيداً
    if document.access_level == 'restricted':
        # فقط منشئ المستند والموافق عليه
        return document.uploaded_by == user.id or document.approved_by == user.id
    
    return False

def has_project_access(project, user):
    """التحقق من صلاحية الوصول للمشروع"""
    if user.role in ['admin', 'org_admin']:
        return project.org_id == user.org_id
    elif user.role == 'project_manager':
        return project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return project.id in [t.project_id for t in user.supervised_tasks]
    elif user.role == 'delegate':
        return project.id in [t.project_id for t in user.delegate_tasks]
    elif user.role == 'employee':
        return project.id in [t.project_id for a in user.task_assignments for t in [a.task]]
    return False

@document_bp.route('/<int:document_id>/download')
@login_required
def download(document_id):
    """تحميل المستند"""
    
    document = ProjectDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if not has_document_access(document, current_user):
        flash('غير مصرح بتحميل هذا المستند', 'danger')
        return redirect(url_for('document.index'))
    
    try:
        # التحقق من وجود الملف
        if not os.path.exists(document.file_path):
            flash('الملف غير موجود', 'danger')
            return redirect(url_for('document.view', document_id=document_id))
        
        # إرسال الملف
        return send_file(
            document.file_path,
            as_attachment=True,
            download_name=document.original_filename
        )
        
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('document.view', document_id=document_id))

@document_bp.route('/<int:document_id>/approve', methods=['POST'])
@login_required
def approve_document(document_id):
    """الموافقة على المستند"""
    
    document = ProjectDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية (فقط مدير النظام ومدير المشروع)
    if current_user.role not in ['admin', 'project_manager']:
        flash('غير مصرح بالموافقة على المستندات', 'danger')
        return redirect(url_for('document.view', document_id=document_id))
    
    # التحقق من صلاحية الموافقة على مستند هذا المشروع
    if not can_approve_document(document, current_user):
        flash('غير مصرح بالموافقة على هذا المستند', 'danger')
        return redirect(url_for('document.view', document_id=document_id))
    
    try:
        if document.requires_approval:
            document.approval_status = 'approved'
            document.approved_by = current_user.id
            document.approved_at = datetime.utcnow()
            
            db.session.commit()
            
            flash('تمت الموافقة على المستند بنجاح', 'success')
        else:
            flash('هذا المستند لا يتطلب موافقة', 'info')
            
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('document.view', document_id=document_id))

def can_approve_document(document, user):
    """التحقق من صلاحية الموافقة على المستند"""
    if user.role in ['admin', 'org_admin']:
        return document.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return document.project.project_manager_id == user.id
    return False

@document_bp.route('/<int:document_id>/reject', methods=['POST'])
@login_required
def reject_document(document_id):
    """رفض المستند"""
    
    document = ProjectDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if not can_approve_document(document, current_user):
        flash('غير مصرح برفض هذا المستند', 'danger')
        return redirect(url_for('document.view', document_id=document_id))
    
    try:
        if document.requires_approval:
            document.approval_status = 'rejected'
            document.approved_by = current_user.id
            document.approved_at = datetime.utcnow()
            
            db.session.commit()
            
            flash('تم رفض المستند', 'success')
        else:
            flash('هذا المستند لا يتطلب موافقة', 'info')
            
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('document.view', document_id=document_id))

@document_bp.route('/<int:document_id>/extract', methods=['POST'])
@login_required
def extract_document(document_id):
    """استخراج البيانات من المستند"""
    
    document = ProjectDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if not has_document_access(document, current_user):
        flash('غير مصرح باستخراج بيانات من هذا المستند', 'danger')
        return redirect(url_for('document.view', document_id=document_id))
    
    try:
        from uploads.app import app
        from services.document_parser import DocumentParser
        
        upload_folder = app.config['UPLOAD_FOLDER']
        parser = DocumentParser(upload_folder)
        
        # تحليل المستند
        parsed_data = parser.parse_document(document.file_path, document.file_extension)
        
        # حفظ البيانات المستخرجة
        document.extraction_status = 'completed'
        document.extraction_metadata = parsed_data
        
        if document.document_type == 'bill_of_quantities':
            parser.save_parsed_data(document.project_id, parsed_data)
        
        db.session.commit()
        
        flash('تم استخراج البيانات من المستند بنجاح', 'success')
        
    except Exception as e:
        document.extraction_status = 'failed'
        db.session.commit()
        flash(f'حدث خطأ في استخراج البيانات: {str(e)}', 'danger')
    
    return redirect(url_for('document.view', document_id=document_id))

@document_bp.route('/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_document(document_id):
    """حذف المستند"""
    
    document = ProjectDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if not can_delete_document(document, current_user):
        flash('غير مصرح بحذف هذا المستند', 'danger')
        return redirect(url_for('document.view', document_id=document_id))
    
    try:
        # حذف الملف من النظام
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
        
        # حذف السجل من قاعدة البيانات
        db.session.delete(document)
        db.session.commit()
        
        flash('تم حذف المستند بنجاح', 'success')
        
    except Exception as e:
        flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return redirect(url_for('document.index'))

def can_delete_document(document, user):
    """التحقق من صلاحية حذف المستند"""
    if user.role in ['admin', 'org_admin']:
        return document.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return document.project.project_manager_id == user.id
    elif user.role in ['supervisor', 'delegate', 'employee']:
        # يمكن للمستخدم حذف المستندات التي رفعها فقط
        return document.uploaded_by == user.id
    return False

# API Routes للمستندات
@document_bp.route('/api/documents', methods=['GET'])
@login_required
def api_documents():
    """API للحصول على قائمة المستندات"""
    try:
        # الحصول على المستندات حسب دور المستخدم
        if current_user.role == 'admin':
            documents = ProjectDocument.query.join(Project).filter(
                Project.org_id == current_user.org_id
            ).all()
        elif current_user.role == 'project_manager':
            documents = ProjectDocument.query.join(Project).filter(
                Project.project_manager_id == current_user.id
            ).all()
        else:
            projects = Project.query.join(Task).filter(
                (Task.supervisor_id == current_user.id) |
                (Task.delegate_id == current_user.id) |
                (Task.assignments.any(user_id=current_user.id))
            ).distinct().all()
            
            documents = ProjectDocument.query.filter(
                ProjectDocument.project_id.in_([p.id for p in projects])
            ).all()
        
        documents_data = [{
            'id': d.id,
            'title': d.title,
            'document_type': d.document_type,
            'filename': d.filename,
            'file_size': d.file_size,
            'uploaded_at': d.uploaded_at.isoformat() if d.uploaded_at else None,
            'uploaded_by': d.uploader.full_name if d.uploader else None,
            'approval_status': d.approval_status,
            'project': {
                'id': d.project.id,
                'name': d.project.name
            }
        } for d in documents]
        
        return jsonify({'success': True, 'documents': documents_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@document_bp.route('/api/documents/<int:document_id>', methods=['GET'])
@login_required
def api_document_detail(document_id):
    """API للحصول على تفاصيل المستند"""
    try:
        document = ProjectDocument.query.get_or_404(document_id)
        
        # التحقق من الصلاحية
        if not has_document_access(document, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        document_data = {
            'id': document.id,
            'title': document.title,
            'title_ar': document.title_ar,
            'description': document.description,
            'document_type': document.document_type,
            'category': document.category,
            'filename': document.filename,
            'original_filename': document.original_filename,
            'file_extension': document.file_extension,
            'file_size': document.file_size,
            'version': document.version,
            'revision_number': document.revision_number,
            'uploaded_at': document.uploaded_at.isoformat() if document.uploaded_at else None,
            'uploaded_by': document.uploader.to_dict() if document.uploader else None,
            'approved_by': document.approver.to_dict() if document.approver else None,
            'approved_at': document.approved_at.isoformat() if document.approved_at else None,
            'approval_status': document.approval_status,
            'extraction_status': document.extraction_status,
            'extraction_metadata': document.extraction_metadata,
            'analysis_summary': document.analysis_summary,
            'requires_approval': document.requires_approval,
            'access_level': document.access_level,
            'is_public': document.is_public,
            'project': {
                'id': document.project.id,
                'name': document.project.name,
                'project_code': document.project.project_code
            }
        }
        
        return jsonify({'success': True, 'document': document_data}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@document_bp.route('/api/documents/<int:document_id>/download-url', methods=['GET'])
@login_required
def api_document_download_url(document_id):
    """API للحصول على رابط تحميل المستند"""
    try:
        document = ProjectDocument.query.get_or_404(document_id)
        
        # التحقق من الصلاحية
        if not has_document_access(document, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        # التحقق من وجود الملف
        if not os.path.exists(document.file_path):
            return jsonify({'error': 'الملف غير موجود'}), 404
        
        download_url = url_for('document.download', document_id=document_id, _external=True)
        
        return jsonify({
            'success': True,
            'download_url': download_url,
            'filename': document.original_filename
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@document_bp.route('/api/documents/<int:document_id>/extract', methods=['POST'])
@login_required
def api_extract_document(document_id):
    """API لاستخراج البيانات من المستند"""
    try:
        document = ProjectDocument.query.get_or_404(document_id)
        
        # التحقق من الصلاحية
        if not has_document_access(document, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        from uploads.app import app
        from services.document_parser import DocumentParser
        
        upload_folder = app.config['UPLOAD_FOLDER']
        parser = DocumentParser(upload_folder)
        
        # تحليل المستند
        parsed_data = parser.parse_document(document.file_path, document.file_extension)
        
        # حفظ البيانات المستخرجة
        document.extraction_status = 'completed'
        document.extraction_metadata = parsed_data
        
        if document.document_type == 'bill_of_quantities':
            parser.save_parsed_data(document.project_id, parsed_data)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'تم استخراج البيانات بنجاح',
            'parsed_data': parsed_data
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# app/routes/attachment_routes.py

from flask import Blueprint, render_template, request, jsonify, send_file,url_for,current_app
from flask_login import login_required, current_user
from app.models.task_models import Task
from app.models.primavera_models import Activity, ActivityDocument
from app.services.file_upload_service import FileUploadService
from app.services.update_service import UpdateService
from app.services.notification_service import NotificationService
from app.extensions import db
import os
from datetime import datetime

from app.routes import attachment_bp 


@attachment_bp.route('/activity/<int:activity_id>/upload', methods=['POST'])
@login_required
def upload_activity_documents(activity_id):
    """رفع مستندات للنشاط"""
    activity = Activity.query.get_or_404(activity_id)
    
    # التحقق من الصلاحية
    if activity.supervisor_id != current_user.id and activity.delegate_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    files = request.files.getlist('files')
    title = request.form.get('title', '')
    description = request.form.get('description', '')
    
    uploaded_files = []
    errors = []
    
    for file in files:
        if file and file.filename:
            # التحقق من صحة الملف
            is_valid, error = FileUploadService.is_allowed_file(file.filename, len(file.read()))
            file.seek(0)
            
            if not is_valid:
                errors.append(f"{file.filename}: {error}")
                continue
            
            # حفظ الملف
            result = FileUploadService.save_file(file, 'uploads/activities')
            
            if result['success']:
                document = ActivityDocument(
                    activity_id=activity_id,
                    filename=result['filename'],
                    original_filename=result['original_filename'],
                    file_size=result['file_size'],
                    file_type=result['file_type'],
                    file_extension=result['file_extension'],
                    file_path=result['file_path'],
                    file_url=result['file_url'],
                    thumbnail_url=result['thumbnail_url'],
                    title=title or result['original_filename'],
                    description=description,
                    requires_approval=True,
                    approval_status='pending',
                    uploaded_by=current_user.id
                )
                
                db.session.add(document)
                uploaded_files.append({
                    'id': document.id,
                    'filename': document.original_filename,
                    'url': document.file_url,
                    'thumbnail': document.thumbnail_url,
                    'type': document.file_type
                })
            else:
                errors.append(f"{file.filename}: {result['error']}")
    
    if uploaded_files:
        db.session.commit()
        
        # إرسال إشعار
        NotificationService.activity_documents_uploaded(activity, None, uploaded_files, current_user)
        
        # تحديث المؤشرات
        UpdateService.update_activity_metrics(activity)
        UpdateService.update_project_metrics(activity.project)
    
    return jsonify({
        'success': True,
        'uploaded': uploaded_files,
        'errors': errors,
        'message': f'تم رفع {len(uploaded_files)} ملف بنجاح'
    })


@attachment_bp.route('/task/<int:task_id>/upload', methods=['POST'])
@login_required
def upload_task_documents(task_id):
    """رفع مستندات للمهمة (يتم حفظها في النشاط المرتبط)"""
    task = Task.query.get_or_404(task_id)
    
    if task.delegate_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # التحقق من وجود نشاط مرتبط
    if not task.activity_id:
        return jsonify({'error': 'المهمة غير مرتبطة بنشاط'}), 400
    
    files = request.files.getlist('files')
    title = request.form.get('title', '')
    description = request.form.get('description', '')
    
    uploaded_files = []
    errors = []
    
    for file in files:
        if file and file.filename:
            is_valid, error = FileUploadService.is_allowed_file(file.filename, len(file.read()))
            file.seek(0)
            
            if not is_valid:
                errors.append(f"{file.filename}: {error}")
                continue
            
            result = FileUploadService.save_file(file, 'uploads/activities')
            
            if result['success']:
                document = ActivityDocument(
                    activity_id=task.activity_id,
                    filename=result['filename'],
                    original_filename=result['original_filename'],
                    file_size=result['file_size'],
                    file_type=result['file_type'],
                    file_extension=result['file_extension'],
                    file_path=result['file_path'],
                    file_url=result['file_url'],
                    thumbnail_url=result['thumbnail_url'],
                    title=title or result['original_filename'],
                    description=description,
                    source_task_id=task.id,
                    requires_approval=True,
                    approval_status='pending',
                    uploaded_by=current_user.id
                )
                
                db.session.add(document)
                uploaded_files.append({
                    'id': document.id,
                    'filename': document.original_filename,
                    'url': document.file_url,
                    'thumbnail': document.thumbnail_url,
                    'type': document.file_type
                })
            else:
                errors.append(f"{file.filename}: {result['error']}")
    
    if uploaded_files:
        db.session.commit()
        
        # إرسال إشعار
        NotificationService.activity_documents_uploaded(task.activity, task, uploaded_files, current_user)
        
        # تحديث المؤشرات
        UpdateService.update_activity_metrics(task.activity)
        UpdateService.update_project_metrics(task.activity.project)
    
    return jsonify({
        'success': True,
        'uploaded': uploaded_files,
        'errors': errors,
        'message': f'تم رفع {len(uploaded_files)} ملف بنجاح'
    })

@attachment_bp.route('/activity/<int:activity_id>/documents', methods=['GET'])
@login_required
def get_activity_documents(activity_id):
    """جلب مستندات النشاط"""
    activity = Activity.query.get_or_404(activity_id)
    
    if activity.project.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    documents = ActivityDocument.query.filter_by(activity_id=activity_id).order_by(ActivityDocument.uploaded_at.desc()).all()
    
    return jsonify({
        'success': True,
        'documents': [{
            'id': d.id,
            'filename': d.original_filename,
            'title': d.title,
            'description': d.description,
            'url': d.file_url,
            'thumbnail': d.thumbnail_url,
            'type': d.file_type,
            'size': d.file_size,
            'file_extension': d.file_extension,
            'uploaded_by': d.uploader.full_name,
            'uploaded_at': d.uploaded_at.isoformat(),
            'source_task': d.source_task.task_name if d.source_task else None,
            'approval_status': d.approval_status
        } for d in documents],
        'count': len(documents)
    })

@attachment_bp.route('/api/activity/<int:activity_id>/tasks', methods=['GET'])
@login_required
def get_activity_tasks(activity_id):
    """جلب مهام النشاط (لاختيار المهمة عند الرفع)"""
    activity = Activity.query.get_or_404(activity_id)
    
    if activity.project.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    tasks = Task.query.filter_by(activity_id=activity_id).all()
    
    return jsonify({
        'success': True,
        'tasks': [{
            'id': t.id,
            'name': t.task_name,
            'code': t.task_code,
            'status': t.status
        } for t in tasks]
    })

@attachment_bp.route('/project/<int:project_id>/gallery')
@login_required
def get_project_gallery(project_id):
    """جلب معرض مستندات المشروع (من جميع الأنشطة)"""
    from app.models.project_models import Project
    
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # جلب جميع المستندات من أنشطة المشروع
    documents = ActivityDocument.query.join(Activity).filter(
        Activity.project_id == project_id
    ).order_by(ActivityDocument.uploaded_at.desc()).all()
    
    # تجميع حسب النوع
    images = [d for d in documents if d.file_type == 'image']
    videos = [d for d in documents if d.file_type == 'video']
    documents_list = [d for d in documents if d.file_type == 'document']
    
    return jsonify({
        'success': True,
        'images': [{
            'id': d.id,
            'filename': d.original_filename,
            'title': d.title,
            'url': d.file_url,
            'thumbnail': d.thumbnail_url,
            'uploaded_at': d.uploaded_at.isoformat(),
            'activity_name': d.activity.activity_name,
            'source_task': d.source_task.task_name if d.source_task else None
        } for d in images],
        'videos': [{
            'id': d.id,
            'filename': d.original_filename,
            'title': d.title,
            'url': d.file_url,
            'thumbnail': d.thumbnail_url,
            'uploaded_at': d.uploaded_at.isoformat(),
            'activity_name': d.activity.activity_name
        } for d in videos],
        'documents': [{
            'id': d.id,
            'filename': d.original_filename,
            'title': d.title,
            'url': d.file_url,
            'uploaded_at': d.uploaded_at.isoformat(),
            'activity_name': d.activity.activity_name
        } for d in documents_list],
        'total': len(documents)
    })


@attachment_bp.route('/document/<int:document_id>', methods=['PUT'])
@login_required
def update_document(document_id):
    """تحديث معلومات المستند (العنوان والوصف)"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if document.uploaded_by != current_user.id and document.activity.project.project_manager_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    if 'title' in data:
        document.title = data['title']
    if 'description' in data:
        document.description = data['description']
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم تحديث المعلومات'})


@attachment_bp.route('/document/<int:document_id>', methods=['DELETE'])
@login_required
def delete_document(document_id):
    """حذف مستند"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if document.uploaded_by != current_user.id and document.activity.project.project_manager_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    # حذف الملفات
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    if document.thumbnail_url:
        thumb_path = document.thumbnail_url.replace(url_for('static', filename=''), '')
        thumb_path = os.path.join(current_app.root_path, 'static', thumb_path)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
    
    db.session.delete(document)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم حذف المستند'})


@attachment_bp.route('/document/<int:document_id>/approve', methods=['POST'])
@login_required
def approve_document(document_id):
    """الموافقة على مستند (للمشرف/مدير المشروع)"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if document.activity.project.project_manager_id != current_user.id and current_user.role != 'org_admin':
        return jsonify({'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    action = data.get('action')
    notes = data.get('notes', '')
    
    if action == 'approve':
        document.approval_status = 'approved'
        document.approved_by = current_user.id
        document.approved_at = datetime.utcnow()
        document.approval_notes = notes
        message = 'تم اعتماد المستند'
    elif action == 'reject':
        document.approval_status = 'rejected'
        document.approved_by = current_user.id
        document.approved_at = datetime.utcnow()
        document.approval_notes = notes
        message = 'تم رفض المستند'
    else:
        return jsonify({'error': 'إجراء غير صالح'}), 400
    
    db.session.commit()
    
    # إرسال إشعار للمستخدم الذي رفع الملف
    if action == 'approve':
        NotificationService.document_approved(document, current_user)
    else:
        NotificationService.document_rejected(document, current_user, notes)
    
    return jsonify({'success': True, 'message': message})


@attachment_bp.route('/document/<int:document_id>/download', methods=['GET'])
@login_required
def download_document(document_id):
    """تحميل المستند"""
    document = ActivityDocument.query.get_or_404(document_id)
    
    # التحقق من الصلاحية
    if document.activity.project.org_id != current_user.org_id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    return send_file(
        document.file_path,
        as_attachment=True,
        download_name=document.original_filename,
        mimetype=document.mime_type or 'application/octet-stream'
    )
"""
upload_routes.py - مسارات رفع وتحليل الملفات
"""
import os
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app,g
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.models import db, Project, Task, Notification,Organization,ResourceDelivery,Resource,TaskPlanning,Meeting,Issue
from app.routes import upload_bp
from app.services.ai_extractor import AIExtractor, ProjectCreator
from datetime import datetime
import uuid
from datetime import datetime, date, timedelta
from app.services.notification_service import NotificationService

@upload_bp.before_request
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
        g.pending_deliveries_count = ResourceDelivery.query.filter_by(
            status='pending'
        ).count() if current_user.role in ['org_admin', 'project_manager'] else 0
        
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
# إعدادات رفع الملفات
# ============================================

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'txt', 'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 ميجابايت

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ============================================
# صفحة رفع الملفات
# ============================================

@upload_bp.route('/upload')
@login_required
def upload_page():
    """صفحة رفع وتحليل الملفات"""
    return render_template('upload/index.html')

# ============================================
# API رفع وتحليل الملفات
# ============================================

@upload_bp.route('/api/upload', methods=['POST'])
@login_required
def api_upload_files():
    """رفع وتحليل ملف واحد أو عدة ملفات"""
    
    if 'files' not in request.files:
        return jsonify({'error': 'لم يتم اختيار أي ملفات'}), 400
    
    files = request.files.getlist('files')
    project_type = request.form.get('project_type', 'general')
    
    if not files or files[0].filename == '':
        return jsonify({'error': 'لم يتم اختيار أي ملفات'}), 400
    
    # تهيئة المحرك
    extractor = AIExtractor(current_app)
    creator = ProjectCreator()
    
    results = []
    all_extracted_data = []
    
    # إنشاء مجلد مؤقت للملفات
    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', str(uuid.uuid4()))
    os.makedirs(upload_folder, exist_ok=True)
    
    try:
        for file in files:
            # التحقق من نوع الملف
            if not allowed_file(file.filename):
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': 'نوع الملف غير مدعوم'
                })
                continue
            
            # التحقق من حجم الملف
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            
            if file_size > MAX_FILE_SIZE:
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': 'حجم الملف يتجاوز 500 ميجابايت'
                })
                continue
            
            # حفظ الملف مؤقتاً
            filename = secure_filename(file.filename)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            # استخراج البيانات
            extracted = extractor.extract_data(file_path)
            
            if extracted.get('success'):
                all_extracted_data.append(extracted)
                results.append({
                    'filename': file.filename,
                    'success': True,
                    'summary': extracted.get('structured_data', {}).get('project', {}),
                    'tasks_count': len(extracted.get('structured_data', {}).get('tasks', []))
                })
            else:
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': extracted.get('error', 'فشل استخراج البيانات')
                })
        
        # دمج البيانات المستخرجة من جميع الملفات
        merged_data = _merge_extracted_data(all_extracted_data)
        
        # إنشاء المشروع من البيانات المدمجة
        if merged_data and merged_data.get('structured_data'):
            creation_result = creator.create_from_extracted_data(
                merged_data,
                current_user.org_id,
                current_user.id
            )
            
            if creation_result.get('success'):
                # إشعار للمستخدم
                # notification = Notification(
                #     user_id=current_user.id,
                #     title=f'✅ تم إنشاء المشروع: {creation_result["project"].name}',
                #     message=f'تم إنشاء المشروع و {len(creation_result["tasks"])} مهام بنجاح من الملفات المرفوعة',
                #     notification_type='project_created',
                #     related_project_id=creation_result["project"].id
                # )
                # db.session.add(notification)
                # db.session.commit()
                # إضافة إشعارات إنشاء المشروع والمستندات
                NotificationService.project_created(creation_result['project'], current_user)
                
                return jsonify({
                    'success': True,
                    'results': results,
                    'project': {
                        'id': creation_result['project'].id,
                        'name': creation_result['project'].name,
                        'code': creation_result['project'].project_code
                    },
                    'tasks_count': len(creation_result['tasks']),
                    'message': creation_result['message']
                })
            else:
                return jsonify({
                    'success': False,
                    'error': creation_result.get('error', 'فشل إنشاء المشروع'),
                    'results': results
                }), 500
        else:
            return jsonify({
                'success': False,
                'error': 'لم يتم استخراج بيانات كافية لإنشاء مشروع',
                'results': results
            }), 400
            
    except Exception as e:
        current_app.logger.error(f"خطأ في رفع الملفات: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
    finally:
        # تنظيف الملفات المؤقتة
        import shutil
        shutil.rmtree(upload_folder, ignore_errors=True)

def _merge_extracted_data(extracted_list):
    """دمج البيانات المستخرجة من عدة ملفات"""
    if not extracted_list:
        return None
    
    merged = {
        'structured_data': {
            'project': {},
            'tasks': [],
            'resources': {}
        }
    }
    
    project_names = []
    project_codes = []
    all_tasks = []
    
    for extracted in extracted_list:
        data = extracted.get('structured_data', {})
        
        # جمع أسماء المشاريع
        if data.get('project', {}).get('name'):
            project_names.append(data['project']['name'])
        
        # جمع رموز المشاريع
        if data.get('project', {}).get('code'):
            project_codes.append(data['project']['code'])
        
        # جمع المهام
        if data.get('tasks'):
            all_tasks.extend(data['tasks'])
    
    # اختيار أفضل اسم مشروع
    if project_names:
        # اختيار الاسم الأكثر شيوعاً
        from collections import Counter
        merged['structured_data']['project']['name'] = Counter(project_names).most_common(1)[0][0]
    
    # اختيار أفضل رمز
    if project_codes:
        merged['structured_data']['project']['code'] = project_codes[0]
    
    # إضافة المهام (مع إزالة التكرار)
    seen_tasks = set()
    unique_tasks = []
    for task in all_tasks:
        task_name = task.get('name', '')
        if task_name and task_name not in seen_tasks:
            seen_tasks.add(task_name)
            unique_tasks.append(task)
    
    merged['structured_data']['tasks'] = unique_tasks
    
    return merged

# ============================================
# معاينة البيانات قبل الإنشاء
# ============================================

@upload_bp.route('/api/preview', methods=['POST'])
@login_required
def api_preview():
    """معاينة البيانات المستخرجة قبل إنشاء المشروع"""
    
    if 'files' not in request.files:
        return jsonify({'error': 'لم يتم اختيار أي ملفات'}), 400
    
    files = request.files.getlist('files')
    
    if not files or files[0].filename == '':
        return jsonify({'error': 'لم يتم اختيار أي ملفات'}), 400
    
    extractor = AIExtractor(current_app)
    
    preview_data = {
        'project_info': {},
        'tasks_preview': [],
        'resources': {}
    }
    
    upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp', str(uuid.uuid4()))
    os.makedirs(upload_folder, exist_ok=True)
    
    try:
        for file in files:
            if not allowed_file(file.filename):
                continue
            
            filename = secure_filename(file.filename)
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            
            extracted = extractor.extract_data(file_path)
            
            if extracted.get('success'):
                data = extracted.get('structured_data', {})
                
                # تجميع معلومات المشروع
                if data.get('project'):
                    preview_data['project_info'].update(data['project'])
                
                # تجميع المهام
                if data.get('tasks'):
                    preview_data['tasks_preview'].extend(data['tasks'][:5])  # أول 5 مهام فقط
        
        return jsonify({
            'success': True,
            'preview': preview_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
    finally:
        import shutil
        shutil.rmtree(upload_folder, ignore_errors=True)

# ============================================
# إنشاء مشروع يدوياً من النص
# ============================================

@upload_bp.route('/api/manual-create', methods=['POST'])
@login_required
def api_manual_create():
    """إنشاء مشروع يدوياً من النص المدخل"""
    
    data = request.get_json()
    project_text = data.get('text', '').strip()
    
    if not project_text:
        return jsonify({'error': 'الرجاء إدخال نص المشروع'}), 400
    
    extractor = AIExtractor(current_app)
    creator = ProjectCreator()
    
    # تحليل النص المدخل
    extracted = extractor.analyze_with_ai(project_text)
    
    if not extracted:
        return jsonify({'error': 'فشل تحليل النص'}), 400
    
    # إنشاء المشروع
    creation_result = creator.create_from_extracted_data(
        {'structured_data': extracted},
        current_user.org_id,
        current_user.id
    )
    
    if creation_result.get('success'):
        return jsonify({
            'success': True,
            'project': {
                'id': creation_result['project'].id,
                'name': creation_result['project'].name
            },
            'tasks_count': len(creation_result['tasks'])
        })
    else:
        return jsonify({'error': creation_result.get('error', 'فشل إنشاء المشروع')}), 500
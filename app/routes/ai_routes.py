# app/routes/ai_routes.py

from flask import render_template, request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import login_required, current_user
from app.models import db, User, Organization,Meeting,Issue
from app.models import AICommand, AICommandAttachment,Project,Notification, AIExtraction, AIReport,Task,ResourceDelivery,TaskPlanning,TaskPlanning,Resource
from app.services.ai_service import AIService
from datetime import datetime,date,timedelta
import os
from werkzeug.utils import secure_filename

from app.routes import ai_bp 

# إعدادات رفع الملفات
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'jpg', 'jpeg', 'png', 'gif'}
UPLOAD_FOLDER = 'static/uploads/ai_commands'

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_pending_deliveries_count(org_id=None, user_role=None):
    """الحصول على عدد التسليمات المعلقة (مواد + معدات)"""
    from app.models import ResourceDelivery, EquipmentDelivery
    
    if user_role not in ['org_admin', 'project_manager']:
        return 0
    
    material_count = ResourceDelivery.query.filter_by(status='pending').count()
    equipment_count = EquipmentDelivery.query.filter_by(status='pending').count()
    
    return material_count + equipment_count

@ai_bp.before_request
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


@ai_bp.route('/')
@login_required
def index():
    """صفحة الذكاء الاصطناعي الرئيسية"""
    recent_commands = AICommand.query.filter_by(
        org_id=current_user.org_id,
        user_id=current_user.id
    ).order_by(AICommand.created_at.desc()).limit(10).all()
    
    recent_reports = AIReport.query.filter_by(
        org_id=current_user.org_id,
        created_by=current_user.id
    ).order_by(AIReport.created_at.desc()).limit(5).all()
    
    return render_template('ai/index.html',
                         recent_commands=recent_commands,
                         recent_reports=recent_reports,
                         now=datetime.now())


@ai_bp.route('/command/new', methods=['GET', 'POST'])
@login_required
def new_command():
    """صفحة إنشاء أمر جديد"""
    if request.method == 'POST':
        command_text = request.form.get('command_text')
        files = request.files.getlist('attachments')
        
        if not command_text:
            flash('يرجى إدخال الأمر', 'danger')
            return redirect(url_for('ai.new_command'))
        
        try:
            # إنشاء الأمر
            ai_command = AICommand(
                org_id=current_user.org_id,
                user_id=current_user.id,
                command_text=command_text,
                status='pending'
            )
            db.session.add(ai_command)
            db.session.flush()
            
            # معالجة الملفات
            if files and files[0].filename:
                upload_path = os.path.join(current_app.root_path, 'static', 'uploads', 'ai_commands')
                os.makedirs(upload_path, exist_ok=True)
                
                for file in files:
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        new_filename = f"{ai_command.id}_{timestamp}_{filename}"
                        file_path = os.path.join(upload_path, new_filename)
                        file.save(file_path)
                        
                        attachment = AICommandAttachment(
                            command_id=ai_command.id,
                            filename=new_filename,
                            original_filename=filename,
                            file_size=os.path.getsize(file_path),
                            file_type=filename.rsplit('.', 1)[1].lower(),
                            file_path=file_path,
                            file_url=url_for('static', filename=f"uploads/ai_commands/{new_filename}")
                        )
                        db.session.add(attachment)
            
            db.session.commit()
            
            # معالجة الأمر في الخلفية (يمكن تحويلها إلى Celery)
            g.ai_service.process_command(ai_command.id)
            
            flash('تم إرسال الأمر للمعالجة', 'success')
            return redirect(url_for('ai.command_detail', command_id=ai_command.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'حدث خطأ: {str(e)}', 'danger')
    
    return render_template('ai/command_new.html', now=datetime.now())


@ai_bp.route('/command/<int:command_id>')
@login_required
def command_detail(command_id):
    """عرض تفاصيل الأمر"""
    command = AICommand.query.get_or_404(command_id)
    
    if command.org_id != current_user.org_id:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('ai.index'))
    
    attachments = command.attachments.all()
    extractions = command.extractions.all()
    
    return render_template('ai/command_detail.html',
                         command=command,
                         attachments=attachments,
                         extractions=extractions,
                         now=datetime.now())


@ai_bp.route('/extraction/<int:extraction_id>')
@login_required
def review_extraction(extraction_id):
    """مراجعة البيانات المستخرجة"""
    extraction = AIExtraction.query.get_or_404(extraction_id)
    
    if extraction.command.org_id != current_user.org_id:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('ai.index'))
    
    return render_template('ai/extraction_review.html',
                         extraction=extraction,
                         now=datetime.now())


@ai_bp.route('/api/extraction/<int:extraction_id>/save', methods=['POST'])
@login_required
def api_save_extraction(extraction_id):
    """API لحفظ البيانات المستخرجة"""
    data = request.get_json()
    modifications = data.get('modifications')
    
    result = g.ai_service.save_extraction(extraction_id, current_user.id, modifications)
    
    return jsonify(result)


@ai_bp.route('/reports')
@login_required
def reports_list():
    """عرض قائمة التقارير"""
    reports = AIReport.query.filter_by(
        org_id=current_user.org_id
    ).order_by(AIReport.created_at.desc()).all()
    
    return render_template('ai/reports.html',
                         reports=reports,
                         now=datetime.now())


@ai_bp.route('/report/<int:report_id>')
@login_required
def view_report(report_id):
    """عرض تقرير"""
    report = AIReport.query.get_or_404(report_id)
    
    if report.org_id != current_user.org_id:
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('ai.reports_list'))
    
    return render_template('ai/report_view.html',
                         report=report,
                         now=datetime.now())


@ai_bp.route('/api/generate-report', methods=['POST'])
@login_required
def api_generate_report():
    """API لتوليد تقرير حسب الطلب"""
    data = request.get_json()
    command_text = data.get('command')
    
    if not command_text:
        return jsonify({'success': False, 'error': 'الأمر مطلوب'}), 400
    
    try:
        # إنشاء أمر مؤقت
        command = AICommand(
            org_id=current_user.org_id,
            user_id=current_user.id,
            command_text=command_text,
            status='processing'
        )
        db.session.add(command)
        db.session.commit()
        
        # معالجة الأمر
        result = g.ai_service.process_command(command.id)
        
        if result['success'] and 'report_id' in result.get('result', {}):
            return jsonify({
                'success': True,
                'report_id': result['result']['report_id'],
                'data': result['result']
            })
        else:
            return jsonify({'success': False, 'error': 'فشل توليد التقرير'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@ai_bp.route('/api/quick-search', methods=['POST'])
@login_required
def api_quick_search():
    """API للبحث السريع"""
    data = request.get_json()
    query = data.get('query')
    
    if not query:
        return jsonify({'success': False, 'error': 'استعلام البحث مطلوب'}), 400
    
    try:
        # استخدام NLP لفهم الاستعلام
        understanding = g.ai_service.nlp_processor.understand_command(query)
        
        # البحث في قاعدة البيانات حسب النوع
        results = []
        
        if understanding['target_type'] == 'project':
            from app.models.project_models import Project
            projects = Project.query.filter(
                Project.org_id == current_user.org_id,
                Project.name.ilike(f'%{query}%')
            ).limit(10).all()
            
            results = [{'id': p.id, 'name': p.name, 'type': 'project'} for p in projects]
        
        elif understanding['target_type'] == 'task':
            from app.models.task_models import Task
            tasks = Task.query.join(Project).filter(
                Project.org_id == current_user.org_id,
                Task.task_name.ilike(f'%{query}%')
            ).limit(10).all()
            
            results = [{'id': t.id, 'name': t.task_name, 'type': 'task'} for t in tasks]
        
        return jsonify({
            'success': True,
            'understanding': understanding,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
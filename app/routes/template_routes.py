"""
template_routes.py - مسارات توليد وتحميل قوالب المشاريع
"""
from flask import render_template, request, jsonify, send_file,g
from flask_login import login_required, current_user
from app.routes import template_bp
from app.services.template_generator import TemplateGenerator
import json
from app.models import Organization, User, Department, Project, Task, ProjectDocument, Notification,TaskAssignment,ResourceDelivery,Resource,TaskPlanning,Meeting,Issue
from datetime import datetime, date, timedelta

generator = TemplateGenerator()

@template_bp.before_request
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

@template_bp.route('/')
@login_required
def template_page():
    """صفحة توليد القوالب"""
    return render_template('templates/index.html')

@template_bp.route('/generate', methods=['POST'])
@login_required
def generate_template():
    """توليد قالب وتحميله"""
    data = request.get_json()
    format_type = data.get('format', 'excel')
    include_data = data.get('include_data', False)
    
    # تجهيز بيانات المشروع إذا طلب المستخدم تضمينها
    project_data = None
    if include_data and data.get('project_data'):
        project_data = data['project_data']
    
    # توليد القالب
    output, error = generator.generate_template(format_type, project_data)
    
    if error:
        return jsonify({'error': error}), 400
    
    # إرسال الملف
    return send_file(
        output,
        as_attachment=True,
        download_name=generator.get_filename(format_type, 
                                            project_data.get('name') if project_data else 'project'),
        mimetype=generator.get_mime_type(format_type)
    )

@template_bp.route('/preview', methods=['POST'])
@login_required
def preview_template():
    """معاينة هيكل القالب"""
    data = request.get_json()
    format_type = data.get('format', 'excel')
    
    # إرجاع معلومات عن هيكل القالب
    template_info = {
        'excel': {
            'sheets': ['معلومات المشروع', 'المهام', 'تعليمات'],
            'description': 'ملف Excel مع ثلاث أوراق عمل',
            'features': ['يدعم العربية', 'صيغ التاريخ', 'قوائم منسدلة']
        },
        'word': {
            'sections': ['معلومات المشروع', 'المهام', 'الموارد'],
            'description': 'مستند Word منسق',
            'features': ['يدعم العربية', 'جداول منظمة', 'مسافات للتعبئة']
        },
        'pdf': {
            'pages': 2,
            'description': 'ملف PDF للطباعة',
            'features': ['جاهز للطباعة', 'تصميم احترافي', 'يدعم العربية']
        },
        'csv': {
            'structure': 'معلومات المشروع ثم المهام',
            'description': 'ملف CSV بسيط',
            'features': ['خفيف', 'متوافق مع كل البرامج', 'يدعم العربية']
        },
        'json': {
            'structure': 'JSON منظم',
            'description': 'ملف JSON للبرمجة',
            'features': ['منظم', 'سهل المعالجة', 'يدعم Unicode']
        }
    }
    
    return jsonify({
        'success': True,
        'info': template_info.get(format_type, {})
    })
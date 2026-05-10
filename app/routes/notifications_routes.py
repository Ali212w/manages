"""
notifications_routes.py - مسارات إدارة الإشعارات
"""
from flask import render_template, request, jsonify, g
from flask_login import login_required, current_user
from app.models import db, Notification,Organization,Project,Task,ResourceDelivery,Resource,TaskPlanning,Meeting,Issue
from app.routes import notifications_bp
from datetime import datetime,date,timedelta

@notifications_bp.before_request
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
        
@notifications_bp.route('/')
@login_required
def index():
    """صفحة عرض جميع الإشعارات"""
    notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notifications/index.html', notifications=notifications)

@notifications_bp.route('/api/unread-count')
@login_required
def api_unread_count():
    """API لعدد الإشعارات غير المقروءة"""
    count = Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return jsonify({'count': count})

@notifications_bp.route('/api/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def api_mark_read(notification_id):
    """تحديد إشعار كمقروء"""
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    notification.mark_as_read()
    db.session.commit()
    
    return jsonify({'success': True})

@notifications_bp.route('/api/mark-all-read', methods=['POST'])
@login_required
def api_mark_all_read():
    """تحديد جميع الإشعارات كمقروءة"""
    Notification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True, 'read_at': datetime.utcnow()})
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'تم تحديد الكل كمقروء'})

@notifications_bp.route('/api/delete/<int:notification_id>', methods=['DELETE'])
@login_required
def api_delete(notification_id):
    """حذف إشعار"""
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        return jsonify({'error': 'غير مصرح'}), 403
    
    db.session.delete(notification)
    db.session.commit()
    
    return jsonify({'success': True})
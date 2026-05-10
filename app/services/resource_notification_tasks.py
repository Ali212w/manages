# app/tasks/resource_notification_tasks.py

from datetime import datetime, timedelta
from app.models import db
from app.models import ResourceRequest, ResourceRequestNotification
from app.services.resource_request_service import ResourceRequestService

def send_resource_reminders():
    """إرسال الإشعارات التذكيرية للموردين"""
    service = ResourceRequestService()
    
    today = datetime.now().date()
    
    # إشعار قبل يومين
    reminder_2_days = today + timedelta(days=2)
    requests_2_days = ResourceRequest.query.filter(
        ResourceRequest.required_date == reminder_2_days,
        ResourceRequest.status.in_(['pending', 'started'])
    ).all()
    
    for request in requests_2_days:
        service._send_notification(
            request.supplier_id,
            f'تذكير: توريد موارد لمشروع {request.project.name}',
            f'يتبقى يومان على موعد توريد الموارد للمشروع {request.project.name}. الرجاء الاستعداد.',
            request.id
        )
    
    # إشعار قبل يوم
    reminder_1_day = today + timedelta(days=1)
    requests_1_day = ResourceRequest.query.filter(
        ResourceRequest.required_date == reminder_1_day,
        ResourceRequest.status.in_(['pending', 'started'])
    ).all()
    
    for request in requests_1_day:
        service._send_notification(
            request.supplier_id,
            f'تذكير عاجل: توريد موارد لمشروع {request.project.name}',
            f'يتبقى يوم واحد على موعد توريد الموارد للمشروع {request.project.name}. الرجاء التجهيز.',
            request.id
        )
    
    # إشعار عند الموعد
    deadline_requests = ResourceRequest.query.filter(
        ResourceRequest.required_date == today,
        ResourceRequest.status.in_(['pending', 'started'])
    ).all()
    
    for request in deadline_requests:
        service._send_notification(
            request.supplier_id,
            f'الموعد النهائي: توريد موارد لمشروع {request.project.name}',
            f'اليوم هو آخر موعد لتوريد الموارد للمشروع {request.project.name}. الرجاء الإسراع.',
            request.id
        )
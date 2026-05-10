# app/services/resource_request_service.py

from flask import current_app, url_for
from app.models import db
from app.models import ResourceRequest, ResourceRequestUpdate, ResourceRequestNotification,Project
from app.models import Notification
from datetime import datetime, timedelta
from dateutil import parser
import json

class ResourceRequestService:
    """خدمة إدارة طلبات توريد الموارد"""
    
    def __init__(self, app=None):
        self.app = app
    
    def create_resource_request(self, data):
        """إنشاء طلب توريد موارد جديد"""
        try:
            # التحقق من وجود طلب سابق لنفس  المشروع والمورد
            existing = ResourceRequest.query.filter_by(
                org_id=data['org_id'],
                project_id=data['project_id'],
                supplier_id=data['supplier_id'],
                status='pending'
            ).first()
            
            if existing:
                return {
                    'success': False,
                    'error': 'يوجد طلب سابق غير مكتمل لهذا المورد والمشروع'
                }
            
            request = ResourceRequest(
                org_id=data['org_id'],
                project_id=data['project_id'],
                supplier_id=data['supplier_id'],
                resources=data['resources'],
                required_date=parser.parse(data['required_date']).date(),
                site_location=data.get('site_location'),
                coordinates=data.get('coordinates'),
                notes=data.get('notes'),
                created_by=data['created_by']
            )
            
            db.session.add(request)
            db.session.flush()
            
            # إنشاء تحديث أولي
            update = ResourceRequestUpdate(
                request_id=request.id,
                new_status='pending',
                message='تم إنشاء طلب توريد الموارد',
                updated_by=data['created_by']
            )
            db.session.add(update)
            
            db.session.commit()
            
            # جدولة الإشعارات
            self._schedule_notifications(request)
            
            return {'success': True, 'request': request.to_dict()}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def start_request(self, request_id, user_id):
        """بدء عملية توريد الموارد"""
        try:
            request = ResourceRequest.query.get(request_id)
            if not request:
                return {'success': False, 'error': 'الطلب غير موجود'}
            
            if request.status != 'pending':
                return {'success': False, 'error': 'لا يمكن بدء طلب غير معلق'}
            
            old_status = request.status
            request.status = 'started'
            request.started_at = datetime.utcnow()
            
            # إنشاء تحديث
            update = ResourceRequestUpdate(
                request_id=request.id,
                old_status=old_status,
                new_status='started',
                message=f'تم بدء عملية توريد الموارد للمشروع {request.project.name}',
                updated_by=user_id,
                location=request.site_location,
                coordinates=request.coordinates
            )
            db.session.add(update)
            
            db.session.commit()
            
            # إرسال إشعار لمدير المشروع والمالك
            self._notify_project_manager(request, 'started')
            self._notify_owner(request, 'started')
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def complete_request(self, request_id, user_id, location=None, coordinates=None, photos=None):
        """إكمال عملية توريد الموارد"""
        try:
            request = ResourceRequest.query.get(request_id)
            if not request:
                return {'success': False, 'error': 'الطلب غير موجود'}
            
            if request.status != 'started':
                return {'success': False, 'error': 'لا يمكن إكمال طلب لم يبدأ'}
            
            old_status = request.status
            request.status = 'completed'
            request.completed_at = datetime.utcnow()
            
            # إنشاء تحديث
            update = ResourceRequestUpdate(
                request_id=request.id,
                old_status=old_status,
                new_status='completed',
                message=f'تم إكمال توريد الموارد للمشروع {request.project.name}',
                updated_by=user_id,
                location=location,
                coordinates=coordinates,
                photos=photos
            )
            db.session.add(update)
            
            db.session.commit()
            
            # إرسال إشعار لمدير المشروع والمالك
            self._notify_project_manager(request, 'completed')
            self._notify_owner(request, 'completed')
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def _schedule_notifications(self, request):
        """جدولة الإشعارات التذكيرية"""
        # إشعار قبل يومين من الموعد
        reminder_date = request.required_date - timedelta(days=2)
        
        # هنا يمكن إضافة مهمة مجدولة (Celery) لإرسال الإشعارات
        # سنقوم بإنشاء سجلات إشعارات مبدئية
        notification = ResourceRequestNotification(
            request_id=request.id,
            user_id=request.supplier_id,
            notification_type='reminder',
            title=f'تذكير: توريد موارد لمشروع {request.project.name}',
            message=f'يتبقى يومان على موعد توريد الموارد للمشروع {request.project.name}'
        )
        db.session.add(notification)
        
        # إشعار قبل الموعد بيوم
        reminder_date_1 = request.required_date - timedelta(days=1)
        notification2 = ResourceRequestNotification(
            request_id=request.id,
            user_id=request.supplier_id,
            notification_type='reminder',
            title=f'تذكير عاجل: توريد موارد لمشروع {request.project.name}',
            message=f'يتبقى يوم واحد على موعد توريد الموارد للمشروع {request.project.name}'
        )
        db.session.add(notification2)
        
        # إشعار عند الوصول للموعد
        deadline_notif = ResourceRequestNotification(
            request_id=request.id,
            user_id=request.supplier_id,
            notification_type='deadline',
            title=f'الموعد النهائي: توريد موارد لمشروع {request.project.name}',
            message=f'اليوم هو آخر موعد لتوريد الموارد للمشروع {request.project.name}'
        )
        db.session.add(deadline_notif)
        
        db.session.commit()
    
    def _send_notification(self, user_id, title, message, notification_type, reference_id):
        """إرسال إشعار للمستخدم"""
        try:
            
            notification = Notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                related_link=url_for('projects.project_resource_requests', request_id=reference_id) if notification_type == 'resource_request' else url_for('project_bp.project_resource_requests', project_id=0).replace('0', str(reference_id)),
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Error sending notification: {str(e)}")
    
    def _notify_project_manager(self, request, action):
        """إشعار مدير المشروع"""
        if not request.project.project_manager_id:
            return
        
        titles = {
            'started': f'بدء توريد موارد لمشروع {request.project.name}',
            'completed': f'اكتمال توريد موارد لمشروع {request.project.name}'
        }
        
        messages = {
            'started': f'تم بدء عملية توريد الموارد للمشروع {request.project.name} بواسطة {request.supplier.full_name}',
            'completed': f'تم إكمال توريد الموارد للمشروع {request.project.name} بنجاح'
        }
        self._send_notification(
            request.project.project_manager_id,
            titles.get(action, 'تحديث طلب توريد'),
            messages.get(action, ''),
            request.id
        )
    
    def _notify_owner(self, request, action):
        """إشعار مالك المشروع (العميل)"""
        if not request.project.client_id:
            return
        
        titles = {
            'started': f'بدء توريد مواد لمشروع {request.project.name}',
            'completed': f'اكتمال توريد مواد لمشروع {request.project.name}'
        }
        
        messages = {
            'started': f'تم بدء جلب المواد للمشروع {request.project.name}',
            'completed': f'تم إكمال جلب المواد للمشروع {request.project.name} بنجاح'
        }
        
        self._send_notification(
            request.project.client.user_id,
            titles.get(action, 'تحديث طلب توريد'),
            messages.get(action, ''),
            request.id
        )
    

    def get_supplier_requests(self, supplier_id):
        """جلب طلبات مورد معين"""
        try:
            from datetime import datetime
            
            requests = ResourceRequest.query.filter_by(
                supplier_id=supplier_id
            ).order_by(ResourceRequest.created_at.desc()).all()
            
            result = []
            for req in requests:
                project = Project.query.get(req.project_id)
                result.append({
                    'id': req.id,
                    'project_name': project.name if project else 'غير معروف',
                    'project_code': project.project_code if project else '',
                    'required_date': req.required_date,  # ✅ كائن date
                    'required_date_str': req.required_date.strftime('%Y-%m-%d') if req.required_date else None,
                    'status': req.status,
                    'resources': req.resources,
                    'notes': req.notes,
                    'created_at': req.created_at,
                    'created_at_str': req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else None,
                    'started_at': req.started_at,
                    'completed_at': req.completed_at
                })
            
            return result
            
        except Exception as e:
            current_app.logger.error(f"Error in get_supplier_requests: {str(e)}")
            return []
    
    def get_project_requests(self, project_id):
        """جلب طلبات مشروع معين"""
        requests = ResourceRequest.query.filter_by(
            project_id=project_id
        ).order_by(ResourceRequest.created_at.desc()).all()
        
        return [req.to_dict() for req in requests]
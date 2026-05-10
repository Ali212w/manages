# app/services/resource_delivery_service.py

from flask import current_app, url_for
from app.models import db
from app.models import (
    ResourceRequest, ResourceDelivery, ResourceDeliveryUpdate, 
    ResourceRequestItem, ResourceRequestNotification
)
from app.models import Notification
from datetime import datetime
import uuid

class ResourceDeliveryService:
    """خدمة إدارة تسليم الموارد"""
    
    def __init__(self):
        pass
    
    def create_delivery(self, data):
        """إنشاء عملية تسليم جديدة"""
        try:
            request = ResourceRequest.query.get(data['request_id'])
            if not request:
                return {'success': False, 'error': 'الطلب غير موجود'}
            
            # التحقق من صلاحية المورد
            if request.supplier_id != data['supplier_id']:
                return {'success': False, 'error': 'غير مصرح بهذا الطلب'}
            
            # إنشاء رقم تسليم فريد
            delivery_number = f"DEL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
            
            # إنشاء سجل التسليم
            delivery = ResourceDelivery(
                request_id=request.id,
                supplier_id=data['supplier_id'],
                delivery_number=delivery_number,
                delivered_items=data['delivered_items'],
                delivery_location=data.get('delivery_location'),
                coordinates=data.get('coordinates'),
                photos=data.get('photos'),
                status='pending'
            )
            db.session.add(delivery)
            db.session.flush()
            
            # تحديث كميات الموارد في الطلب
            for item in data['delivered_items']:
                req_item = ResourceRequestItem.query.filter_by(
                    request_id=request.id,
                    resource_id=item['resource_id']
                ).first()
                
                if req_item:
                    req_item.delivered_quantity += item['quantity']
                    req_item.remaining_quantity = req_item.required_quantity - req_item.delivered_quantity
                    
                    if req_item.remaining_quantity <= 0:
                        req_item.is_completed = True
            
            # تحديث حالة الطلب العام إذا اكتملت جميع الموارد
            all_completed = all(item.is_completed for item in request.items)
            if all_completed:
                request.status = 'completed'
                request.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            # إنشاء تحديث للتسليم
            update = ResourceDeliveryUpdate(
                delivery_id=delivery.id,
                new_status='pending',
                message=f'تم إنشاء طلب تسليم رقم {delivery_number}',
                updated_by=data['supplier_id']
            )
            db.session.add(update)
            db.session.commit()
            
            # إرسال إشعارات
            self._notify_project_manager(request, delivery)
            self._notify_owner(request, delivery)
            self._notify_supplier_remaining(request)
            
            return {'success': True, 'delivery': delivery.to_dict()}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def confirm_delivery(self, delivery_id, user_id, data):
        """تأكيد أو رفض عملية التسليم"""
        try:
            delivery = ResourceDelivery.query.get(delivery_id)
            if not delivery:
                return {'success': False, 'error': 'عملية التسليم غير موجودة'}
            
            request = delivery.request
            action = data.get('action')  # confirm, reject, partial
            notes = data.get('notes')
            
            if action == 'confirm':
                delivery.status = 'confirmed'
                delivery.confirmed_by = user_id
                delivery.confirmed_at = datetime.utcnow()
                delivery.confirmation_notes = notes
                
                # تحديث كميات الموارد المستلمة نهائياً
                for item in delivery.delivered_items:
                    req_item = ResourceRequestItem.query.filter_by(
                        request_id=request.id,
                        resource_id=item['resource_id']
                    ).first()
                    # الكميات تم تحديثها مسبقاً، هنا فقط للتأكيد
                
                message = f'تم تأكيد استلام المواد للتسليم رقم {delivery.delivery_number}'
                
                # التحقق من اكتمال الطلب
                if all(item.is_completed for item in request.items):
                    request.status = 'completed'
                    request.completed_at = datetime.utcnow()
                    self._notify_completion(request)
                
            elif action == 'reject':
                delivery.status = 'rejected'
                delivery.rejection_reason = notes
                delivery.confirmed_by = user_id
                delivery.confirmed_at = datetime.utcnow()
                
                message = f'تم رفض التسليم رقم {delivery.delivery_number}'
                
                # إرجاع الكميات إلى الطلب
                for item in delivery.delivered_items:
                    req_item = ResourceRequestItem.query.filter_by(
                        request_id=request.id,
                        resource_id=item['resource_id']
                    ).first()
                    if req_item:
                        req_item.delivered_quantity -= item['quantity']
                        req_item.remaining_quantity = req_item.required_quantity - req_item.delivered_quantity
                        req_item.is_completed = req_item.remaining_quantity <= 0
                
                # إرسال إشعار للمورد بالرفض
                self._notify_supplier_rejection(delivery, notes)
                
            else:
                return {'success': False, 'error': 'إجراء غير معروف'}
            
            db.session.commit()
            
            # تسجيل التحديث
            update = ResourceDeliveryUpdate(
                delivery_id=delivery.id,
                old_status='pending',
                new_status=delivery.status,
                message=message,
                updated_by=user_id
            )
            db.session.add(update)
            db.session.commit()
            
            # إرسال إشعارات للمعنيين
            self._notify_project_manager_status(delivery, action)
            self._notify_owner_status(delivery, action)
            
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def get_delivery_details(self, delivery_id):
        """الحصول على تفاصيل التسليم"""
        delivery = ResourceDelivery.query.get(delivery_id)
        if not delivery:
            return {'success': False, 'error': 'غير موجود'}
        
        updates = ResourceDeliveryUpdate.query.filter_by(delivery_id=delivery_id).all()
        
        return {
            'success': True,
            'delivery': delivery.to_dict(),
            'updates': [{
                'old_status': u.old_status,
                'new_status': u.new_status,
                'message': u.message,
                'updater': u.updater.full_name if u.updater else None,
                'updated_at': u.updated_at.strftime('%Y-%m-%d %H:%M') if u.updated_at else None
            } for u in updates]
        }
    
    def get_request_items_status(self, request_id):
        """الحصول على حالة كميات الموارد المطلوبة"""
        items = ResourceRequestItem.query.filter_by(request_id=request_id).all()
        
        return {
            'success': True,
            'items': [{
                'id': i.id,
                'resource_name': i.resource_name,
                'required': i.required_quantity,
                'delivered': i.delivered_quantity,
                'remaining': i.remaining_quantity,
                'unit': i.unit,
                'is_completed': i.is_completed
            } for i in items]
        }
    
    def _notify_project_manager(self, request, delivery):
        """إشعار مدير المشروع بوصول تسليم جديد"""
        if not request.project.project_manager_id:
            return
        
        title = f'استلام مواد جديدة لمشروع {request.project.name}'
        message = f'تم استلام تسليم رقم {delivery.delivery_number} للمشروع {request.project.name}. الرجاء المراجعة والتأكيد.'
        
        self._send_notification(
            request.project.project_manager_id,
            title,
            message,
            'delivery_pending',
            delivery.id
        )
    
    def _notify_owner(self, request, delivery):
        """إشعار مالك المشروع بوصول تسليم جديد"""
        if not request.project.client_id:
            return
        
        title = f'استلام مواد لمشروع {request.project.name}'
        message = f'تم استلام تسليم رقم {delivery.delivery_number} للمشروع {request.project.name}. في انتظار التأكيد.'
        
        self._send_notification(
            request.project.client.user_id,
            title,
            message,
            'delivery_pending',
            delivery.id
        )
    
    def _notify_supplier_remaining(self, request):
        """إشعار المورد بالكميات المتبقية"""
        remaining_items = [item for item in request.items if item.remaining_quantity > 0]
        
        if remaining_items:
            items_text = '\n'.join([
                f"- {item.resource_name}: {item.remaining_quantity} {item.unit}"
                for item in remaining_items
            ])
            
            title = f'تحديث: كميات متبقية لمشروع {request.project.name}'
            message = f'الكميات المتبقية لتوريدها:\n{items_text}'
            
            self._send_notification(
                request.supplier_id,
                title,
                message,
                'remaining_items',
                request.id
            )
    
    def _notify_supplier_rejection(self, delivery, reason):
        """إشعار المورد برفض التسليم"""
        request = delivery.request
        
        items_text = '\n'.join([
            f"- {item['name']}: {item['quantity']} {item['unit']}"
            for item in delivery.delivered_items
        ])
        
        title = f'رفض تسليم رقم {delivery.delivery_number}'
        message = f'تم رفض التسليم التالي للمشروع {request.project.name}:\n{items_text}\n\nسبب الرفض: {reason}'
        
        self._send_notification(
            request.supplier_id,
            title,
            message,
            'delivery_rejected',
            delivery.id
        )
    
    def _notify_project_manager_status(self, delivery, action):
        """إشعار مدير المشروع بتأكيد/رفض التسليم"""
        request = delivery.request
        if not request.project.project_manager_id:
            return
        
        if action == 'confirm':
            title = f'تأكيد استلام مواد لمشروع {request.project.name}'
            message = f'تم تأكيد استلام التسليم رقم {delivery.delivery_number} للمشروع {request.project.name}.'
        else:
            title = f'رفض استلام مواد لمشروع {request.project.name}'
            message = f'تم رفض التسليم رقم {delivery.delivery_number} للمشروع {request.project.name}. السبب: {delivery.rejection_reason}'
        
        self._send_notification(
            request.project.project_manager_id,
            title,
            message,
            'delivery_processed',
            delivery.id
        )
    
    def _notify_owner_status(self, delivery, action):
        """إشعار مالك المشروع بتأكيد/رفض التسليم"""
        request = delivery.request
        if not request.project.client_id:
            return
        
        if action == 'confirm':
            title = f'تأكيد استلام مواد لمشروع {request.project.name}'
            message = f'تم تأكيد استلام التسليم رقم {delivery.delivery_number} للمشروع {request.project.name}.'
        else:
            title = f'رفض استلام مواد لمشروع {request.project.name}'
            message = f'تم رفض التسليم رقم {delivery.delivery_number} للمشروع {request.project.name}.'
        
        self._send_notification(
            request.project.client.user_id,
            title,
            message,
            'delivery_processed',
            delivery.id
        )
    
    def _notify_completion(self, request):
        """إشعار بإكمال جميع الموارد المطلوبة"""
        # إشعار لمدير المشروع
        if request.project.project_manager_id:
            self._send_notification(
                request.project.project_manager_id,
                f'اكتمال توريد مواد مشروع {request.project.name}',
                f'تم استلام جميع المواد المطلوبة للمشروع {request.project.name}. يمكن البدء في تنفيذ المهام.',
                'request_completed',
                request.id
            )
        
        # إشعار للمالك
        if request.project.client_id:
            self._send_notification(
                request.project.client.user_id,
                f'اكتمال توريد مواد مشروع {request.project.name}',
                f'تم استلام جميع المواد المطلوبة للمشروع {request.project.name}.',
                'request_completed',
                request.id
            )
    
    def _send_notification(self, user_id, title, message, notification_type, reference_id):
        """إرسال إشعار للمستخدم"""
        try:
            from app.models import Notification
            
            # تحديد الرابط حسب نوع الإشعار
            if notification_type in ['resource_request', 'remaining_items', 'request_completed']:
                related_link = url_for('supplier.view_request', request_id=reference_id)
            elif notification_type in ['delivery_pending', 'delivery_confirmed', 'delivery_rejected', 'delivery_started']:
                related_link = url_for('delivery.view_delivery', delivery_id=reference_id)
            else:
                related_link = '#'
            
            notification = Notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type=notification_type,
                related_link=related_link,
                created_at=datetime.utcnow()
            )
            db.session.add(notification)
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Error sending notification: {str(e)}")
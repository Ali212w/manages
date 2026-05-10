# app/routes/delivery_routes.py

from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.models import db
from app.models import ResourceRequest, ResourceRequestItem, ResourceDelivery
from app.models import Notification
from app.routes import delivery_bp
from datetime import datetime
import json
import uuid

# @delivery_bp.route('/request/<int:request_id>/create', methods=['GET', 'POST'])
# @login_required
# def create_delivery(request_id):
#     """صفحة إنشاء تسليم جديد للمورد"""
#     request_obj = ResourceRequest.query.get_or_404(request_id)
    
#     if request_obj.supplier_id != current_user.id:
#         flash('غير مصرح بالوصول', 'danger')
#         return redirect(url_for('supplier.dashboard'))
    
#     if request_obj.status not in ['pending']:
#         flash('لا يمكن إنشاء تسليم لطلب غير نشط', 'danger')
#         return redirect(url_for('supplier.view_request', request_id=request_id))
    
#     # جلب العناصر المتبقية
#     remaining_items = [item for item in request_obj.items if item.remaining_quantity > 0]
    
#     if request.method == 'POST':
#         delivered_items = []
#         for item in remaining_items:
#             qty = float(request.form.get(f'qty_{item.id}', 0))
#             if qty > 0:
#                 delivered_items.append({
#                     'item_id': item.id,
#                     'name': item.resource_name,
#                     'quantity': qty,
#                     'unit': item.unit,
#                     'notes': request.form.get(f'notes_{item.id}', '')
#                 })
        
#         if not delivered_items:
#             flash('الرجاء إدخال كمية واحدة على الأقل', 'danger')
#             return redirect(url_for('delivery.create_delivery', request_id=request_id))
        
#         # إنشاء رقم تسليم
#         delivery_number = f"DEL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{request_obj.id}"
        
#         delivery = ResourceDelivery(
#             request_id=request_id,
#             supplier_id=current_user.id,
#             delivery_number=delivery_number,
#             delivered_items=delivered_items,
#             delivery_location=request.form.get('delivery_location'),
#             coordinates=request.form.get('coordinates'),
#             status='pending'
#         )
        
#         db.session.add(delivery)
#         db.session.flush()
        
#         # تحديث كميات العناصر
#         for item_data in delivered_items:
#             req_item = ResourceRequestItem.query.get(item_data['item_id'])
#             if req_item:
#                 req_item.delivered_quantity += item_data['quantity']
#                 req_item.remaining_quantity = req_item.required_quantity - req_item.delivered_quantity
#                 req_item.is_completed = req_item.remaining_quantity <= 0
        
#         # تحديث حالة الطلب
#         all_completed = all(item.is_completed for item in request_obj.items)
#         if all_completed:
#             request_obj.status = 'completed'
#             request_obj.completed_at = datetime.utcnow()
#         else:
#             request_obj.status = 'started'
#             if not request_obj.started_at:
#                 request_obj.started_at = datetime.utcnow()
        
#         db.session.commit()
        
#         # إرسال إشعارات
#         send_notifications(delivery, request_obj)
        
#         flash('تم إنشاء التسليم بنجاح، في انتظار التأكيد', 'success')
#         return redirect(url_for('supplier.view_request', request_id=request_id))
    
#     return render_template('delivery/create.html',
#                          request=request_obj,
#                          remaining_items=remaining_items,
#                          now=datetime.now())


@delivery_bp.route('/<int:delivery_id>/confirm', methods=['POST'])
@login_required
def confirm_delivery(delivery_id):
    """تأكيد أو رفض التسليم (للمشرف أو مدير المشروع)"""
    delivery = ResourceDelivery.query.get_or_404(delivery_id)
    request_obj = delivery.request
    
    # التحقق من الصلاحية
    if request_obj.created_by != current_user.id and current_user.role != 'org_admin':
        return jsonify({'success': False, 'error': 'غير مصرح بالتأكيد'}), 403
    
    if delivery.status != 'pending':
        return jsonify({'success': False, 'error': 'تم معالجة هذا التسليم بالفعل'}), 400
    
    data = request.get_json()
    action = data.get('action')
    notes = data.get('notes')
    
    try:
        if action == 'confirm':
            delivery.status = 'confirmed'
            delivery.confirmed_by = current_user.id
            delivery.confirmed_at = datetime.utcnow()
            delivery.confirmation_notes = notes
            
            message = f'تم تأكيد استلام التسليم رقم {delivery.delivery_number}'
            
            # إشعار للمورد
            send_supplier_notification(delivery, 'confirmed', notes)
            
            # إشعار للمالك
            if request_obj.project.client_id:
                send_owner_notification(delivery, 'confirmed', notes)
            
        elif action == 'reject':
            delivery.status = 'rejected'
            delivery.rejection_reason = notes
            delivery.confirmed_by = current_user.id
            delivery.confirmed_at = datetime.utcnow()
            
            message = f'تم رفض التسليم رقم {delivery.delivery_number}'
            
            # إرجاع الكميات
            for item_data in delivery.delivered_items:
                req_item = ResourceRequestItem.query.get(item_data['item_id'])
                if req_item:
                    req_item.delivered_quantity -= item_data['quantity']
                    req_item.remaining_quantity = req_item.required_quantity - req_item.delivered_quantity
                    req_item.is_completed = req_item.remaining_quantity <= 0
            
            # إعادة حالة الطلب
            if request_obj.status == 'completed':
                request_obj.status = 'started'
                request_obj.completed_at = None
            
            # إشعار للمورد
            send_supplier_notification(delivery, 'rejected', notes)
            
            # إشعار للمالك
            if request_obj.project.client_id:
                send_owner_notification(delivery, 'rejected', notes)
            
        else:
            return jsonify({'success': False, 'error': 'إجراء غير معروف'}), 400
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def send_notifications(delivery, request_obj):
    """إرسال إشعارات للمدير والمالك"""
    # إشعار لمدير المشروع
    if request_obj.created_by:
        notification = Notification(
            user_id=request_obj.created_by,
            title=f'تسليم جديد - {request_obj.project.name}',
            message=f'تم استلام تسليم رقم {delivery.delivery_number} للمشروع {request_obj.project.name}. الرجاء التأكيد.',
            notification_type='delivery_pending',
            related_link=url_for('projects.confirm_delivery', delivery_id=delivery.id),
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
    
    # إشعار لمالك المشروع
    if request_obj.project.client_id:
        notification = Notification(
            user_id=request_obj.project.client_id,
            title=f'تسليم مواد - {request_obj.project.name}',
            message=f'تم استلام تسليم رقم {delivery.delivery_number} للمشروع {request_obj.project.name}.',
            notification_type='delivery_pending',
            related_link=url_for('projects.confirm_delivery', delivery_id=delivery.id),
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
    
    db.session.commit()


def send_supplier_notification(delivery, status, notes):
    """إشعار المورد بنتيجة التسليم"""
    request_obj = delivery.request
    
    if status == 'confirmed':
        title = f'تم تأكيد التسليم - {request_obj.project.name}'
        message = f'تم تأكيد استلام التسليم رقم {delivery.delivery_number} للمشروع {request_obj.project.name}.'
    else:
        title = f'رفض التسليم - {request_obj.project.name}'
        message = f'تم رفض التسليم رقم {delivery.delivery_number} للمشروع {request_obj.project.name}. السبب: {notes}'
    
    # إضافة معلومات الكميات المتبقية
    remaining_items = [item for item in request_obj.items if item.remaining_quantity > 0]
    if remaining_items:
        items_text = ', '.join([f'{item.resource_name}: {item.remaining_quantity} {item.unit}' for item in remaining_items])
        message += f'\n\nالكميات المتبقية: {items_text}'
    
    notification = Notification(
        user_id=delivery.supplier_id,
        title=title,
        message=message,
        notification_type=f'delivery_{status}',
        related_link=url_for('supplier.view_request', request_id=request_obj.id),
        created_at=datetime.utcnow()
    )
    db.session.add(notification)
    db.session.commit()


def send_owner_notification(delivery, status, notes):
    """إشعار مالك المشروع بنتيجة التسليم"""
    request_obj = delivery.request
    
    title = f'نتيجة تسليم مواد - {request_obj.project.name}'
    if status == 'confirmed':
        message = f'تم تأكيد استلام التسليم رقم {delivery.delivery_number} للمشروع {request_obj.project.name}.'
    else:
        message = f'تم رفض التسليم رقم {delivery.delivery_number} للمشروع {request_obj.project.name}. السبب: {notes}'
    
    notification = Notification(
        user_id=request_obj.project.client.user_id,
        title=title,
        message=message,
        notification_type=f'delivery_{status}',
        related_link=url_for('projects.view_delivery', delivery_id=delivery.id),
        created_at=datetime.utcnow()
    )
    db.session.add(notification)
    db.session.commit()
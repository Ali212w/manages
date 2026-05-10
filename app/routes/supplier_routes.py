# app/routes/supplier_routes.py

from flask import render_template, request, redirect, url_for, flash, jsonify, g,current_app
from flask_login import login_required, current_user
from app.models import db
from app.services.resource_request_service import ResourceRequestService
from app.models import ResourceRequest, ResourceRequestUpdate,ResourceRequestNotification,Project,ResourceRequestItem,ResourceDelivery,Notification,ResourceOfferHistory
from datetime import datetime
from app.services.resource_delivery_service import ResourceDeliveryService
from app.routes import supplier_bp
from functools import wraps
import json
import os
import uuid
from werkzeug.utils import secure_filename
from app.services.update_service import UpdateService
from app.services.notification_service import NotificationService
# إضافة الدوال المساعدة لرفع الصور
def allowed_file(filename):
    """التحقق من امتداد الملف المسموح"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_photo(file):
    """حفظ الصورة وإرجاع المسار النسبي"""
    if file and allowed_file(file.filename):
        # تأمين اسم الملف
        filename = secure_filename(file.filename)
        # إضافة معرف فريد لتجنب تكرار الأسماء
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        
        # تحديد المسار الكامل
        upload_folder = os.path.join(current_app.root_path, 'static', 'images', 'deliveries')
        
        # إنشاء المجلد إذا لم يكن موجوداً
        os.makedirs(upload_folder, exist_ok=True)
        
        # المسار الكامل للصورة
        file_path = os.path.join(upload_folder, unique_filename)
        
        # حفظ الصورة
        file.save(file_path)
        
        # إرجاع المسار النسبي للتخزين في قاعدة البيانات
        return f'/static/images/deliveries/{unique_filename}'
    
    return None

def save_multiple_photos(files):
    """حفظ مجموعة من الصور وإرجاع قائمة المسارات"""
    photo_urls = []
    for file in files:
        if file and file.filename:
            photo_url = save_photo(file)
            if photo_url:
                photo_urls.append(photo_url)
    return photo_urls

def supplier_required(f):
    """ديكوراتور للتحقق من صلاحية المورد"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role not in ['supplier', 'org_admin']:
            flash('غير مصرح بالوصول - هذه الصفحة للموردين فقط', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@supplier_bp.before_request
def load_supplier_data():
    """تحميل بيانات المورد"""
    today = datetime.now().date()
    if current_user.is_authenticated and current_user.role == 'supplier':
        g.user = current_user
        g.pending_requests = ResourceRequest.query.filter_by(
            supplier_id=current_user.id,
            status='pending'
        ).count()
        g.in_progress_requests = ResourceRequest.query.filter_by(
            supplier_id=current_user.id,
            status='started'
        ).count()
        g.completed_requests = ResourceRequest.query.filter_by(
            supplier_id=current_user.id,
            status='completed'
        ).count()
        g.today_deadlines = ResourceRequest.query.filter(
            ResourceRequest.supplier_id == current_user.id,
            ResourceRequest.required_date == today,
            ResourceRequest.status.in_(['pending', 'started'])
        ).count()


@supplier_bp.route('/')
@login_required
@supplier_required
def dashboard():
    """لوحة تحكم المورد"""
    from datetime import datetime, date
    
    service = ResourceRequestService()
    requests = service.get_supplier_requests(current_user.id)
    
    today = date.today()
    
    # ✅ معالجة التواريخ وتحويلها إلى كائنات date للمقارنة
    processed_requests = []
    for req in requests:
        # تحويل required_date إلى كائن date إذا كان نصاً
        required_date = req.get('required_date')
        if isinstance(required_date, str):
            try:
                required_date = datetime.strptime(required_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                required_date = None
        elif isinstance(required_date, datetime):
            required_date = required_date.date()
        
        # تحويل created_at
        created_at = req.get('created_at')
        if isinstance(created_at, str):
            try:
                created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                created_at = None
        
        processed_requests.append({
            **req,  # نسخ جميع الحقول الموجودة
            'required_date_obj': required_date,  # كائن date للمقارنة
            'required_date_str': required_date.strftime('%Y-%m-%d') if required_date else None,
            'created_at_obj': created_at,
            'created_at_str': created_at.strftime('%Y-%m-%d %H:%M') if created_at else None,
            'is_overdue': required_date and required_date < today if required_date else False
        })
    
    stats = {
        'total': len(processed_requests),
        'pending': len([r for r in processed_requests if r['status'] == 'pending']),
        'started': len([r for r in processed_requests if r['status'] == 'started']),
        'completed': len([r for r in processed_requests if r['status'] == 'completed'])
    }
    
    # الطلبات النشطة
    active_requests = [r for r in processed_requests if r['status'] in ['pending', 'started']]
    
    return render_template('supplier/dashboard.html',
                         requests=active_requests,
                         stats=stats,
                         now=datetime.now(),
                         today=today)

# app/routes/supplier_routes.py
@supplier_bp.route('/requests')
@login_required
def requests_list():
    """عرض طلبات التوريد للمورد"""
    if current_user.role != 'supplier':
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('auth.login'))
    
    # جلب الطلبات
    requests = ResourceRequest.query.filter_by(
        supplier_id=current_user.id
    ).order_by(ResourceRequest.created_at.desc()).all()
    
    # تجهيز البيانات للقالب
    requests_data = []
    for req in requests:
        # جلب المشروع
        project = Project.query.get(req.project_id)
        
        # ✅ تجهيز items - تحويل كل كائن إلى قاموس
        items_list = []
        for item in req.items:  # req.items هي قائمة من كائنات ResourceRequestItem
            items_list.append({
                'id': item.id,
                'resource_name': str(item.resource_name) if item.resource_name else '',
                'required_quantity': float(item.required_quantity) if item.required_quantity else 0,
                'delivered_quantity': float(item.delivered_quantity) if item.delivered_quantity else 0,
                'remaining_quantity': float(item.remaining_quantity) if item.remaining_quantity else 0,
                'unit': str(item.unit) if item.unit else '',
                'is_completed': bool(item.is_completed)
            })
        
        # ✅ تجهيز resources (JSON)
        resources = []
        if req.resources:
            if isinstance(req.resources, list):
                resources = req.resources
            elif isinstance(req.resources, str):
                try:
                    resources = json.loads(req.resources)
                except:
                    resources = []
        
        requests_data.append({
            'id': req.id,
            'project_name': str(project.name) if project else 'غير معروف',
            'project_code': str(project.project_code) if project else '',
            'required_date': req.required_date.strftime('%Y-%m-%d') if req.required_date else None,
            'status': str(req.status),
            'resources': resources,
            'items': items_list,  # ✅ قائمة من القواميس
            'notes': str(req.notes) if req.notes else '',
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else None,
            'started_at': req.started_at.strftime('%Y-%m-%d') if req.started_at else None,
            'completed_at': req.completed_at.strftime('%Y-%m-%d') if req.completed_at else None,
            'site_location': str(req.site_location) if req.site_location else ''
        })
    
    return render_template('supplier/requests.html',
                         requests=requests_data,
                         now=datetime.now())


@supplier_bp.route('/request/<int:request_id>')
@login_required
@supplier_required
def view_request(request_id):
    """عرض تفاصيل طلب توريد"""
    # استخدام اسم مختلف لتجنب التعارض مع كائن Flask request
    resource_request = ResourceRequest.query.get_or_404(request_id)
    
    # التحقق من الصلاحية
    if resource_request.supplier_id != current_user.id:
        flash('غير مصرح بمشاهدة هذا الطلب', 'danger')
        return redirect(url_for('supplier.dashboard'))
    
    # جلب التحديثات
    updates = ResourceRequestUpdate.query.filter_by(
        request_id=request_id
    ).order_by(ResourceRequestUpdate.updated_at.desc()).all()
    
    # جلب العناصر المرتبطة بالطلب (إذا كانت موجودة)
    request_items = ResourceRequestItem.query.filter_by(
        request_id=request_id
    ).all()
    # جلب سجل التسليمات
    deliveries = ResourceDelivery.query.filter_by(
        request_id=request_id
    ).order_by(ResourceDelivery.delivery_date.desc()).all()
    
    return render_template(
        'supplier/request_detail2.html',
        resource_request=resource_request,  # استخدام اسم مختلف
        updates=updates,
        items=request_items,
        deliveries=deliveries,
        now=datetime.now()
    )

# app/routes/supplier_routes.py

# app/routes/supplier_routes.py

@supplier_bp.route('/request/<int:request_id>/submit-offer', methods=['POST'])
@login_required
def submit_offer(request_id):
    """تقديم عرض سعر من المورد"""
    try:
        resource_request = ResourceRequest.query.get_or_404(request_id)
        
        if resource_request.supplier_id != current_user.id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'لم يتم إرسال البيانات'}), 400
        
        items_data = data.get('items', [])
        
        if not items_data:
            return jsonify({'error': 'لا توجد عناصر للتحديث'}), 400
        
        updated_items = []
        
        for item_data in items_data:
            item_id = item_data.get('item_id')
            if not item_id:
                continue
                
            item = ResourceRequestItem.query.get(item_id)
            if not item or item.request_id != request_id:
                continue
            
            # التحقق من صحة السعر
            price = item_data.get('price', 0)
            if price <= 0:
                return jsonify({'error': f'السعر غير صحيح للمادة {item.resource_name}'}), 400
            
            # حفظ عرض السعر
            item.offer_price = price
            item.offer_currency = item_data.get('currency', 'SAR')
            item.offer_notes = item_data.get('notes', '')
            item.offer_submitted_at = datetime.utcnow()
            item.offer_status = 'pending'
            
            # تسجيل في سجل العروض
            history = ResourceOfferHistory(
                request_item_id=item.id,
                offer_price=item.offer_price,
                offer_currency=item.offer_currency,
                offer_notes=item.offer_notes,
                status='pending',
                submitted_by=current_user.id
            )
            db.session.add(history)
            
            updated_items.append({
                'id': item.id,
                'resource_name': item.resource_name,
                'price': item.offer_price,
                'currency': item.offer_currency,
                'notes': item.offer_notes
            })
        
        db.session.commit()
        
        # إرسال إشعار لمدير المشروع
        try:
            NotificationService.offer_submitted(resource_request, updated_items, current_user)
        except Exception as e:
            # حتى لو فشل الإشعار، لا نريد إلغاء العملية
            print(f"خطأ في إرسال الإشعار: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'تم إرسال عرض السعر بنجاح',
            'items': updated_items
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"خطأ في submit_offer: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'حدث خطأ: {str(e)}'}), 500

# app/routes/supplier_routes.py

@supplier_bp.route('/request/<int:request_id>/deliver', methods=['POST'])
@login_required
def deliver_itemses(request_id):
    """تسليم المواد (بعد الموافقة على العرض) مع رفع الصور"""
    try:
        resource_request = ResourceRequest.query.get_or_404(request_id)
        
        if resource_request.supplier_id != current_user.id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        # استلام البيانات من FormData (وليس JSON)
        location = request.form.get('location', '')
        coordinates = request.form.get('coordinates', '')
        notes = request.form.get('notes', '')
        items_json = request.form.get('items', '[]')
        
        # تحويل items من JSON string إلى list
        import json
        try:
            items_data = json.loads(items_json)
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            items_data = []
        
        # معالجة الصور المرفوعة
        uploaded_photos = []
        # استلام الملفات المرفوعة
        if 'photos' in request.files:
            files = request.files.getlist('photos')
            uploaded_photos = save_multiple_photos(files)

        # files = request.files.getlist('photos')
        
        # for file in files:
        #     if file and file.filename:
        #         # التحقق من نوع الملف
        #         allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
        #         ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                
        #         if ext not in allowed_extensions:
        #             continue
                
        #         # حفظ الصورة
        #         result = save_delivery_photo(file, request_id)
        #         if result['success']:
        #             uploaded_photos.append(result['file_url'])
        
        if not items_data:
            return jsonify({'error': 'لا توجد مواد للتسليم'}), 400
        
        # التحقق من أن العروض معتمدة
        for item_data in items_data:
            item_id = item_data.get('item_id')
            item = ResourceRequestItem.query.get(item_id)
            if item and item.offer_status != 'approved':
                return jsonify({'error': f'عرض سعر {item.resource_name} غير معتمد بعد'}), 400
        
        delivered_items = []
        
        for item_data in items_data:
            item_id = item_data.get('item_id')
            quantity = item_data.get('quantity', 0)
            item_notes = item_data.get('notes', '')
            
            if quantity <= 0:
                continue
                
            item = ResourceRequestItem.query.get(item_id)
            if not item or item.request_id != request_id:
                continue
            
            if quantity > item.remaining_quantity:
                return jsonify({'error': f'الكمية المسلمة لـ {item.resource_name} تتجاوز الكمية المتبقية ({item.remaining_quantity})'}), 400
            
            # تحديث الكميات
            item.delivered_quantity += quantity
            item.remaining_quantity = item.required_quantity - item.delivered_quantity
            item.is_completed = item.remaining_quantity <= 0
            
            # استخدام السعر المعتمد
            item.unit_price = item.offer_price
            item.total_price = item.delivered_quantity * item.unit_price
            item.notes = item_notes
            
            delivered_items.append({
                'item_id': item.id,
                'name': item.resource_name,
                'quantity': quantity,
                'unit': item.unit,
                'unit_price': item.unit_price,
                'currency': item.offer_currency,
                'notes': item_notes
            })
        
        if not delivered_items:
            return jsonify({'error': 'لم يتم تحديد كميات صالحة للتسليم'}), 400
        
        # إنشاء سجل تسليم مع الصور
        delivery = ResourceDelivery(
            request_id=request_id,
            supplier_id=current_user.id,
            delivery_number=f"DEL-{request_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            delivered_items=delivered_items,
            delivery_location=location,
            coordinates=coordinates,
            photos=uploaded_photos,
            notes=notes,
            status='pending'
        )
        
        db.session.add(delivery)
        db.session.commit()
        
        # إرسال إشعار لمدير المشروع
        try:
            from app.services.notification_service import NotificationService
            NotificationService.delivery_submitted(delivery, resource_request, sum(i['quantity'] for i in delivered_items))
        except Exception as e:
            print(f"خطأ في إرسال الإشعار: {str(e)}")
        
        return jsonify({
            'success': True,
            'message': 'تم تسجيل عملية التسليم بنجاح',
            'delivery_id': delivery.id,
            'photos': uploaded_photos
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"خطأ في deliver_items: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'حدث خطأ: {str(e)}'}), 500




@supplier_bp.route('/request/<int:request_id>/deliveres', methods=['GET', 'POST'])
@login_required
def deliver_items(request_id):
    """صفحة تسليم جزء من المواد"""
    resource_request = ResourceRequest.query.get_or_404(request_id)
    
    # التحقق من الصلاحية
    if resource_request.supplier_id != current_user.id:
        flash('غير مصرح لك', 'danger')
        return redirect(url_for('supplier.supplier_requests'))
    
    # التحقق من حالة الطلب
    if resource_request.status in ['completed', 'cancelled']:
        flash('لا يمكن تسليم مواد لطلب مكتمل أو ملغي', 'danger')
        return redirect(url_for('supplier.view_request', request_id=request_id))
    
    # جلب العناصر غير المكتملة
    request_items = ResourceRequestItem.query.filter_by(
        request_id=request_id,
        is_completed=False
    ).all()
    
    if not request_items:
        flash('جميع المواد تم تسليمها بالكامل', 'info')
        return redirect(url_for('supplier.view_request', request_id=request_id))
    
    if request.method == 'POST':
        try:
            # استلام البيانات
            delivered_items = []
            total_delivered = 0
            uploaded_photos = []
            
            # استلام الملفات المرفوعة
            if 'photos' in request.files:
                files = request.files.getlist('photos')
                uploaded_photos = save_multiple_photos(files)
            for item in request_items:
                delivered_quantity = request.form.get(f'quantity_{item.id}', type=float) or 0
                
                if delivered_quantity > 0:
                    # لا يمكن تسليم أكثر من المتبقي
                    if delivered_quantity > item.remaining_quantity:
                        return jsonify({
                            'success': False,
                            'error': f'الكمية المسلمة لـ {item.resource_name} تتجاوز الكمية المتبقية'
                        }), 400
                    
                    delivered_items.append({
                        'item_id': item.id,
                        'resource_id': item.resource_id,
                        'name': item.resource_name,
                        'quantity': delivered_quantity,
                        'unit': item.unit,
                        'notes': request.form.get(f'notes_{item.id}', '')
                    })
                    
                    total_delivered += delivered_quantity
            
            if not delivered_items:
                return jsonify({
                    'success': False,
                    'error': 'الرجاء إدخال الكميات المراد تسليمها'
                }), 400
            
            # إنشاء سجل تسليم جديد
            delivery_number = f"DEL-{resource_request.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            delivery = ResourceDelivery(
                request_id=request_id,
                supplier_id=current_user.id,
                delivery_number=delivery_number,
                delivery_date=datetime.utcnow(),
                delivered_items=delivered_items,
                delivery_location=request.form.get('delivery_location'),
                coordinates=request.form.get('coordinates'),
                photos=uploaded_photos,  # روابط الصور
                status='pending'
            )
            
            db.session.add(delivery)
            
            # تحديث كميات العناصر
            for delivered in delivered_items:
                item = ResourceRequestItem.query.get(delivered['item_id'])
                item.delivered_quantity += delivered['quantity']
                item.remaining_quantity = item.required_quantity - item.delivered_quantity
                item.is_completed = item.remaining_quantity <= 0
                item.updated_at = datetime.utcnow()
            
            # تحديث حالة الطلب الرئيسي
            all_completed = all(item.is_completed for item in request_items)
            
            if all_completed:
                resource_request.status = 'completed'
                resource_request.completed_at = datetime.utcnow()
            else:
                resource_request.status = 'partially_delivered'
            
            resource_request.updated_at = datetime.utcnow()
            
            db.session.commit()
            # ✅ تحديث مؤشرات الطلب
            UpdateService.update_resource_request_metrics(request_id)
            # إرسال الإشعارات
            send_delivery_notifications(delivery, resource_request, total_delivered)
            
            flash('تم تسليم المواد بنجاح', 'success')
            return jsonify({'success': True, 'redirect': url_for('supplier.view_request', request_id=request_id)})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500
    
    # GET request - عرض صفحة التسليم
    return render_template(
        'supplier/deliver_items.html',
        resource_request=resource_request,
        request_items=request_items
    )


def send_delivery_notifications(delivery, resource_request, total_delivered):
    """إرسال إشعارات عند تسليم المواد"""
    
    # 1. إشعار لمدير المشروع
    if resource_request.project and resource_request.project.project_manager_id:
        confirm_url = url_for('projects.confirm_delivery', delivery_id=delivery.id, _external=True)
        
        notification_pm = Notification(
            user_id=resource_request.project.project_manager_id,
            title=f"تسليم مواد - {resource_request.project.name}",
            title_ar=f"تسليم مواد - {resource_request.project.name}",
            message=f"تم تسليم {total_delivered} وحدة من المواد للطلب #{resource_request.id}. يرجى تأكيد الاستلام.",
            message_ar=f"تم تسليم {total_delivered} وحدة من المواد للطلب #{resource_request.id}. يرجى تأكيد الاستلام.",
            notification_type='delivery_pending',
            priority='high',
            related_link=confirm_url,
            related_project_id=resource_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification_pm)
    
    # 2. إشعار للمالك (إذا كان موجوداً)
    if resource_request.project and resource_request.project.client_id:

        notification_owner = Notification(
            user_id=resource_request.project.client_id,
            title=f"تسليم مواد - {resource_request.project.name}",
            title_ar=f"تسليم مواد - {resource_request.project.name}",
            message=f"تم تسليم {total_delivered} وحدة من المواد للمشروع. في انتظار التأكيد من مدير المشروع.",
            message_ar=f"تم تسليم {total_delivered} وحدة من المواد للمشروع. في انتظار التأكيد من مدير المشروع.",
            notification_type='delivery_submitted',
            priority='medium',
            related_link=url_for('projects.project_resource_requests', project_id=resource_request.project_id, _external=True),
            related_project_id=resource_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification_owner)
    
    db.session.commit()

@supplier_bp.route('/request/<int:request_id>/start', methods=['POST'])
@login_required
@supplier_required
def start_request(request_id):
    """بدء عملية التوريد"""
    
    service = ResourceRequestService()
    result = service.start_request(
        request_id=request_id,
        user_id=current_user.id
    )
    
    if result['success']:
        # تحديث حالة الإشعارات
        ResourceRequestNotification.query.filter_by(
            request_id=request_id,
            user_id=current_user.id,
            is_sent=False
        ).update({'is_sent': True, 'sent_at': datetime.utcnow()})
        db.session.commit()
        
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result['error']}), 400


@supplier_bp.route('/request/<int:request_id>/complete', methods=['POST'])
@login_required
@supplier_required
def complete_request(request_id):
    """إكمال عملية التوريد"""
    data = request.get_json()
    
    service = ResourceRequestService()
    result = service.complete_request(
        request_id=request_id,
        user_id=current_user.id,
        location=data.get('location'),
        coordinates=data.get('coordinates'),
        photos=data.get('photos')
    )
    
    if result['success']:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result['error']}), 400

# أضف هذه المسارات في supplier_routes.py

@supplier_bp.route('/equipment-requests')
@login_required
def equipment_requests_list():
    """عرض طلبات المعدات للمورد"""
    if current_user.role != 'supplier':
        flash('غير مصرح بالوصول', 'danger')
        return redirect(url_for('auth.login'))
    
    from app.models import EquipmentRequest
    
    equipment_requests = EquipmentRequest.query.filter_by(
        supplier_id=current_user.id
    ).order_by(EquipmentRequest.created_at.desc()).all()
    
    requests_data = []
    for req in equipment_requests:
        project = Project.query.get(req.project_id)
        
        items_list = []
        for item in req.items:
            items_list.append({
                'id': item.id,
                'equipment_name': str(item.equipment_name) if item.equipment_name else '',
                'required_quantity': float(item.required_quantity) if item.required_quantity else 0,
                'delivered_quantity': float(item.delivered_quantity) if item.delivered_quantity else 0,
                'remaining_quantity': float(item.remaining_quantity) if item.remaining_quantity else 0,
                'unit': str(item.unit) if item.unit else '',
                'is_completed': bool(item.is_completed),
                'offer_status': item.offer_status
            })
        
        requests_data.append({
            'id': req.id,
            'project_name': str(project.name) if project else 'غير معروف',
            'project_code': str(project.project_code) if project else '',
            'required_date': req.required_date.strftime('%Y-%m-%d') if req.required_date else None,
            'status': str(req.status),
            'items': items_list,
            'notes': str(req.notes) if req.notes else '',
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M') if req.created_at else None,
            'started_at': req.started_at.strftime('%Y-%m-%d') if req.started_at else None,
            'completed_at': req.completed_at.strftime('%Y-%m-%d') if req.completed_at else None,
            'site_location': str(req.site_location) if req.site_location else ''
        })
    
    return render_template('supplier/equipment_requests.html',
                         requests=requests_data,
                         now=datetime.now())


@supplier_bp.route('/equipment-request/<int:request_id>')
@login_required
def view_equipment_request(request_id):
    """عرض تفاصيل طلب معدات"""
    from app.models import EquipmentRequest, EquipmentRequestUpdate, EquipmentRequestItem, EquipmentDelivery
    
    equipment_request = EquipmentRequest.query.get_or_404(request_id)
    
    if equipment_request.supplier_id != current_user.id:
        flash('غير مصرح بمشاهدة هذا الطلب', 'danger')
        return redirect(url_for('supplier.dashboard'))
    
    updates = EquipmentRequestUpdate.query.filter_by(
        request_id=request_id
    ).order_by(EquipmentRequestUpdate.updated_at.desc()).all()
    
    request_items = EquipmentRequestItem.query.filter_by(
        request_id=request_id
    ).all()
    
    deliveries = EquipmentDelivery.query.filter_by(
        request_id=request_id
    ).order_by(EquipmentDelivery.delivery_date.desc()).all()
    
    return render_template('supplier/equipment_request_detail.html',
                         resource_request=equipment_request,
                         updates=updates,
                         items=request_items,
                         deliveries=deliveries,
                         now=datetime.now())


@supplier_bp.route('/equipment-request/<int:request_id>/submit-offer', methods=['POST'])
@login_required
def submit_equipment_offer(request_id):
    """تقديم عرض سعر للمعدات"""
    from app.models import EquipmentRequest, EquipmentRequestItem, EquipmentOfferHistory
    
    try:
        equipment_request = EquipmentRequest.query.get_or_404(request_id)
        
        if equipment_request.supplier_id != current_user.id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'لم يتم إرسال البيانات'}), 400
        
        items_data = data.get('items', [])
        
        if not items_data:
            return jsonify({'error': 'لا توجد عناصر للتحديث'}), 400
        
        updated_items = []
        
        for item_data in items_data:
            item_id = item_data.get('item_id')
            if not item_id:
                continue
                
            item = EquipmentRequestItem.query.get(item_id)
            if not item or item.request_id != request_id:
                continue
            
            price = item_data.get('price', 0)
            if price <= 0:
                return jsonify({'error': f'السعر غير صحيح للمعدة {item.equipment_name}'}), 400
            
            item.offer_price = price
            item.offer_currency = item_data.get('currency', 'SAR')
            item.offer_notes = item_data.get('notes', '')
            item.offer_submitted_at = datetime.utcnow()
            item.offer_status = 'pending'
            
            history = EquipmentOfferHistory(
                request_item_id=item.id,
                offer_price=item.offer_price,
                offer_currency=item.offer_currency,
                offer_notes=item.offer_notes,
                status='pending',
                submitted_by=current_user.id
            )
            db.session.add(history)
            
            updated_items.append({
                'id': item.id,
                'equipment_name': item.equipment_name,
                'price': item.offer_price,
                'currency': item.offer_currency,
                'notes': item.offer_notes
            })
        
        db.session.commit()
        
        from app.services.notification_service import NotificationService
        NotificationService.equipment_offer_submitted(equipment_request, updated_items, current_user)
        
        return jsonify({
            'success': True,
            'message': 'تم إرسال عرض السعر بنجاح',
            'items': updated_items
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'حدث خطأ: {str(e)}'}), 500


@supplier_bp.route('/equipment-request/<int:request_id>/deliver', methods=['POST'])
@login_required
def deliver_equipment(request_id):
    """تسليم المعدات (بعد الموافقة على العرض) مع رفع الصور"""
    from app.models import EquipmentRequest, EquipmentRequestItem, EquipmentDelivery
    
    try:
        equipment_request = EquipmentRequest.query.get_or_404(request_id)
        
        if equipment_request.supplier_id != current_user.id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        location = request.form.get('location', '')
        coordinates = request.form.get('coordinates', '')
        notes = request.form.get('notes', '')
        equipment_condition = request.form.get('equipment_condition', 'good')
        serial_numbers = request.form.get('serial_numbers', '{}')
        
        items_json = request.form.get('items', '[]')
        
        try:
            items_data = json.loads(items_json)
            serial_numbers_data = json.loads(serial_numbers) if serial_numbers else {}
        except json.JSONDecodeError as e:
            items_data = []
            serial_numbers_data = {}
        
        uploaded_photos = []
        if 'photos' in request.files:
            files = request.files.getlist('photos')
            uploaded_photos = save_multiple_photos(files)
        
        if not items_data:
            return jsonify({'error': 'لا توجد معدات للتسليم'}), 400
        
        for item_data in items_data:
            item_id = item_data.get('item_id')
            item = EquipmentRequestItem.query.get(item_id)
            if item and item.offer_status != 'approved':
                return jsonify({'error': f'عرض سعر المعدة {item.equipment_name} غير معتمد بعد'}), 400
        
        delivered_items = []
        
        for item_data in items_data:
            item_id = item_data.get('item_id')
            quantity = item_data.get('quantity', 0)
            item_notes = item_data.get('notes', '')
            
            if quantity <= 0:
                continue
                
            item = EquipmentRequestItem.query.get(item_id)
            if not item or item.request_id != request_id:
                continue
            
            if quantity > item.remaining_quantity:
                return jsonify({'error': f'الكمية المسلمة لـ {item.equipment_name} تتجاوز الكمية المتبقية ({item.remaining_quantity})'}), 400
            
            item.delivered_quantity += quantity
            item.remaining_quantity = item.required_quantity - item.delivered_quantity
            item.is_completed = item.remaining_quantity <= 0
            
            item.unit_price = item.offer_price
            item.total_price = item.delivered_quantity * item.unit_price
            item.notes = item_notes
            
            delivered_items.append({
                'item_id': item.id,
                'equipment_id': item.equipment_id,
                'name': item.equipment_name,
                'quantity': quantity,
                'unit': item.unit,
                'unit_price': item.unit_price,
                'currency': item.offer_currency,
                'notes': item_notes,
                'serial_numbers': serial_numbers_data.get(str(item_id), [])
            })
        
        if not delivered_items:
            return jsonify({'error': 'لم يتم تحديد كميات صالحة للتسليم'}), 400
        
        delivery = EquipmentDelivery(
            request_id=request_id,
            supplier_id=current_user.id,
            delivery_number=f"EQDEL-{request_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            delivered_items=delivered_items,
            delivery_location=location,
            coordinates=coordinates,
            photos=uploaded_photos,
            notes=notes,
            status='pending',
            equipment_condition=equipment_condition
        )
        
        db.session.add(delivery)
        db.session.commit()
        
        from app.services.notification_service import NotificationService
        NotificationService.equipment_delivery_submitted(delivery, equipment_request, sum(i['quantity'] for i in delivered_items))
        
        return jsonify({
            'success': True,
            'message': 'تم تسجيل عملية التسليم بنجاح',
            'delivery_id': delivery.id,
            'photos': uploaded_photos
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'حدث خطأ: {str(e)}'}), 500


@supplier_bp.route('/equipment-request/<int:request_id>/start', methods=['POST'])
@login_required
def start_equipment_request(request_id):
    """بدء عملية توريد المعدات"""
    from app.models import EquipmentRequest, EquipmentRequestUpdate
    from app.services.notification_service import NotificationService
    
    try:
        equipment_request = EquipmentRequest.query.get_or_404(request_id)
        
        if equipment_request.supplier_id != current_user.id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        if equipment_request.status != 'pending':
            return jsonify({'error': 'لا يمكن بدء طلب غير معلق'}), 400
        
        old_status = equipment_request.status
        equipment_request.status = 'started'
        equipment_request.started_at = datetime.utcnow()
        
        update = EquipmentRequestUpdate(
            request_id=request_id,
            old_status=old_status,
            new_status='started',
            message='تم بدء عملية توريد المعدات',
            updated_by=current_user.id
        )
        db.session.add(update)
        
        db.session.commit()
        
        NotificationService.equipment_request_updated(equipment_request, 'started')
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@supplier_bp.route('/equipment-request/<int:request_id>/complete', methods=['POST'])
@login_required
def complete_equipment_request(request_id):
    """إكمال عملية توريد المعدات"""
    from app.models import EquipmentRequest, EquipmentRequestUpdate
    from app.services.notification_service import NotificationService
    
    try:
        equipment_request = EquipmentRequest.query.get_or_404(request_id)
        
        if equipment_request.supplier_id != current_user.id:
            return jsonify({'error': 'غير مصرح'}), 403
        
        if equipment_request.status not in ['started', 'partially_delivered']:
            return jsonify({'error': 'لا يمكن إكمال طلب لم يبدأ بعد'}), 400
        
        all_completed = all(item.is_completed for item in equipment_request.items)
        
        if not all_completed:
            return jsonify({'error': 'لا يمكن إكمال الطلب حيث لا تزال هناك كميات متبقية'}), 400
        
        old_status = equipment_request.status
        equipment_request.status = 'completed'
        equipment_request.completed_at = datetime.utcnow()
        
        update = EquipmentRequestUpdate(
            request_id=request_id,
            old_status=old_status,
            new_status='completed',
            message='اكتملت عملية توريد المعدات',
            updated_by=current_user.id
        )
        db.session.add(update)
        
        db.session.commit()
        
        NotificationService.equipment_request_updated(equipment_request, 'completed')
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@supplier_bp.route('/equipment-delivery/<int:delivery_id>')
@login_required
def view_equipment_delivery(delivery_id):
    """عرض تفاصيل تسليم معدات"""
    from app.models import EquipmentDelivery, EquipmentDeliveryUpdate
    
    delivery = EquipmentDelivery.query.get_or_404(delivery_id)
    
    if delivery.supplier_id != current_user.id:
        flash('غير مصرح بمشاهدة هذا التسليم', 'danger')
        return redirect(url_for('supplier.dashboard'))
    
    updates = EquipmentDeliveryUpdate.query.filter_by(
        delivery_id=delivery_id
    ).order_by(EquipmentDeliveryUpdate.updated_at.desc()).all()
    
    return render_template('supplier/equipment_delivery_detail.html',
                         delivery=delivery,
                         updates=updates,
                         now=datetime.now())
# app/routes/supplier_routes.py
# app/routes/supplier_routes.py

@supplier_bp.route('/notifications')
@login_required
def notifications():
    """صفحة الإشعارات الكاملة للمورد"""
    return render_template('supplier/notifications.html')


@supplier_bp.route('/notifications/<int:notification_id>')
@login_required
def view_notification(notification_id):
    """عرض تفاصيل إشعار معين"""
    notification = Notification.query.get_or_404(notification_id)
    
    if notification.user_id != current_user.id:
        flash('غير مصرح لك', 'danger')
        return redirect(url_for('supplier.dashboard'))
    
    # تحديث الإشعار كمقروء
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.session.commit()
    
    # الانتقال إلى الرابط المرتبط
    link = notification.get_primary_link()
    if link:
        return redirect(link)
    
    return redirect(url_for('supplier.notifications'))

@supplier_bp.route('/api/notifications')
@login_required
@supplier_required
def api_notifications():
    """API لجلب إشعارات المورد"""
    try:
        notifications = Notification.query.filter_by(
            user_id=current_user.id
        ).order_by(Notification.created_at.desc()).limit(20).all()
        
        unread_count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()
        
        notifications_data = []
        for notif in notifications:
            notifications_data.append({
                'id': notif.id,
                'title': notif.title,
                'message': notif.message,
                'notification_type': notif.notification_type,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat(),
                'related_link': notif.get_primary_link()
            })
        
        return jsonify({
            'success': True,
            'notifications': notifications_data,
            'unread_count': unread_count
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@supplier_bp.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
@supplier_required
def api_mark_notification_read(notification_id):
    """تحديد إشعار كمقروء"""
    try:
        notification = Notification.query.get_or_404(notification_id)
        
        if notification.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'غير مصرح'}), 403
        
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@supplier_bp.route('/api/notifications/mark-all-read', methods=['POST'])
@login_required
@supplier_required
def api_mark_all_read():
    """تحديد جميع الإشعارات كمقروءة"""
    try:
        Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).update({'is_read': True, 'read_at': datetime.utcnow()})
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم تحديد جميع الإشعارات كمقروءة'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@supplier_bp.route('/api/notifications/unread-count')
@login_required
@supplier_required
def api_unread_count():
    """جلب عدد الإشعارات غير المقروءة"""
    try:
        count = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).count()
        
        return jsonify({'success': True, 'count': count})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
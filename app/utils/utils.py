# utils.py
import os
import secrets
import hashlib
import json
from datetime import datetime, timedelta
from PIL import Image
from flask import current_app, url_for, request
from flask_mail import Message
from app.extensions import db, mail # redis_client , 
from app.models import Notification, User, Subscription,Project #,ActivityLog
import qrcode
import io
import base64
from urllib.parse import urlparse, urljoin
from flask import current_app

def save_picture(form_picture):
    """حفظ الصورة الشخصية مع تغيير الحجم"""
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/profile_pics', picture_fn)
    
    # تغيير حجم الصورة
    output_size = (300, 300)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)
    
    return picture_fn

def save_uploaded_file(file, subfolder='uploads'):
    """حفظ ملف مرفوع"""
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(file.filename)
    file_fn = f"{random_hex}{f_ext}"
    file_path = os.path.join(current_app.root_path, 'static', subfolder, file_fn)
    file.save(file_path)
    return file_fn

def send_notification(user_id, title, message, notification_type='info', task_id=None, project_id=None, is_urgent=False):
    """إرسال إشعار إلى مستخدم"""
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        type=notification_type,
        related_task_id=task_id,
        related_project_id=project_id,
        is_urgent=is_urgent
    )
    db.session.add(notification)
    db.session.commit()
    
    # إرسال إشعار بريد إلكتروني إذا كان مفعلاً
    user = User.query.get(user_id)
    if user and user.notification_settings.get('email_notifications', True):
        send_email_notification(user.email, title, message, task_id, project_id)
    
    # تخزين في Redis للإشعارات الفورية
    # redis_client.publish('notifications', json.dumps({
    #     'user_id': user_id,
    #     'notification': {
    #         'id': notification.id,
    #         'title': title,
    #         'message': message,
    #         'type': notification_type,
    #         'is_urgent': is_urgent
    #     }
    # }))
    
    return notification
# def send_project_invitation_email(email, full_name, project, role, token, is_existing_user=False, custom_message=''):
#     """إرسال بريد إلكتروني لدعوة المستخدم للمشروع"""
#     from flask_mail import Message
#     from flask import url_for
    
#     accept_link = url_for('accept_invitation', token=token, _external=True)
    
#     role_names = {
#         'supervisor': 'مشرف',
#         'delegate': 'مندوب',
#         'worker': 'فرد'
#     }
    
#     role_ar = role_names.get(role, role)
    
#     subject = f'دعوة للمشاركة في مشروع {project.title}'
    
#     html_content = f"""
#     <html dir="rtl">
#     <head>
#         <meta charset="UTF-8">
#         <style>
#             body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; background-color: #f4f4f4; margin: 0; padding: 0; }}
#             .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
#             .header {{ background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 30px; text-align: center; }}
#             .content {{ padding: 30px; }}
#             .project-info {{ background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0; border-right: 4px solid #28a745; }}
#             .button {{ display: inline-block; padding: 12px 30px; background: #28a745; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
#             .footer {{ background: #f8f9fa; padding: 20px; text-align: center; font-size: 0.9em; color: #6c757d; }}
#             .inviter {{ background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 15px 0; }}
#         </style>
#     </head>
#     <body>
#         <div class="container">
#             <div class="header">
#                 <h2>دعوة للمشاركة في مشروع</h2>
#             </div>
#             <div class="content">
#                 <h3>مرحباً {full_name or email}،</h3>
                
#                 <p>تمت دعوتك من قبل <strong>{current_user.full_name}</strong> (مشرف المشروع) للمشاركة في:</p>
                
#                 <div class="project-info">
#                     <h4 style="color: #28a745; margin-top: 0;">{project.title}</h4>
#                     <p><strong>الموقع:</strong> {project.location or 'غير محدد'}</p>
#                     <p><strong>الوصف:</strong> {project.description or 'لا يوجد وصف'}</p>
#                     <p><strong>الدور المقترح:</strong> {role_ar}</p>
#                 </div>
                
#                 {custom_message and f'''
#                 <div class="inviter">
#                     <strong>رسالة من {current_user.full_name}:</strong>
#                     <p>{custom_message}</p>
#                 </div>
#                 ''' or ''}
                
#                 <div style="text-align: center;">
#                     <a href="{accept_link}" class="button">
#                         {'قبول الدعوة والدخول للمشروع' if is_existing_user else 'إنشاء حساب وقبول الدعوة'}
#                     </a>
#                 </div>
                
#                 <p style="color: #dc3545; font-size: 0.9em; text-align: center;">
#                     <i class="fas fa-clock"></i> هذه الدعوة صالحة لمدة 7 أيام فقط.
#                 </p>
#             </div>
#             <div class="footer">
#                 <p>هذا بريد إلكتروني تلقائي، يرجى عدم الرد عليه.</p>
#                 <p>منصة إدارة المشاريع الذكية</p>
#             </div>
#         </div>
#     </body>
#     </html>
#     """
    
#     msg = Message(subject, recipients=[email], html=html_content)
#     mail.send(msg)
    
def send_email_notification(email, subject, message, task_id=None, project_id=None):
    """إرسال إشعار عبر البريد الإلكتروني"""
    try:
        msg = Message(subject,
                      sender=current_app.config['MAIL_USERNAME'],
                      recipients=[email])
        msg.body = message
        msg.html = f"""
        <html>
            <body dir="rtl">
                <h2>{subject}</h2>
                <p>{message}</p>
                <hr>
                <p>منصة إدارة المشاريع الذكية</p>
            </body>
        </html>
        """
        mail.send(msg)
    except Exception as e:
        current_app.logger.error(f"Error sending email: {e}")

def log_activity(user_id, action, details, ip_address=None, task_id=None, project_id=None):
    """تسجيل نشاط المستخدم"""
    if not ip_address:
        ip_address = request.remote_addr if request else None
    
    log = ActivityLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=ip_address,
        task_id=task_id,
        project_id=project_id
    )
    db.session.add(log)
    db.session.commit()
    return log

def generate_qr_code(data):
    """توليد رمز QR"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    # تحويل إلى base64
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return img_str

def format_currency(amount, currency='USD'):
    """تنسيق العملة"""
    if amount is None:
        return f"0 {currency}"
    return f"{amount:,.2f} {currency}"

def format_duration(seconds):
    """تنسيق المدة الزمنية"""
    if not seconds:
        return "0 ثانية"
    
    intervals = [
        ('سنة', 31536000),
        ('شهر', 2592000),
        ('أسبوع', 604800),
        ('يوم', 86400),
        ('ساعة', 3600),
        ('دقيقة', 60),
        ('ثانية', 1)
    ]
    
    result = []
    for name, count in intervals:
        value = seconds // count
        if value:
            seconds -= value * count
            if value == 1:
                result.append(f"{value} {name}")
            else:
                result.append(f"{value} {name}")
    
    return ' و '.join(result[:2]) if result else "0 ثانية"

def generate_invoice(user, plan, amount):
    """توليد فاتورة"""
    invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"
    
    invoice = {
        'invoice_number': invoice_number,
        'date': datetime.utcnow().isoformat(),
        'customer': {
            'name': user.full_name,
            'email': user.email,
            'phone': user.phone
        },
        'items': [
            {
                'description': f'اشتراك {plan} - منصة إدارة المشاريع',
                'quantity': 1,
                'unit_price': amount,
                'total': amount
            }
        ],
        'total': amount,
        'currency': 'USD',
        'due_date': (datetime.utcnow() + timedelta(days=30)).isoformat()
    }
    
    return invoice

def check_subscription_expiry():
    """التحقق من انتهاء الاشتراكات"""
    expired_subs = Subscription.query.filter(
        Subscription.end_date < datetime.utcnow(),
        Subscription.status == 'active'
    ).all()
    
    for sub in expired_subs:
        sub.status = 'expired'
        user = User.query.get(sub.user_id)
        if user:
            user.is_paid = False
            user.subscription_end = None
            
            # إرسال إشعار
            send_notification(
                user.id,
                'انتهاء الاشتراك',
                'انتهت صلاحية اشتراكك. يرجى تجديد الاشتراك للاستمرار في استخدام الميزات المتقدمة.',
                'warning',
                is_urgent=True
            )
    
    db.session.commit()
    return len(expired_subs)

def calculate_project_progress(project_id):
    """حساب تقدم المشروع"""
    from models import Task
    
    total_tasks = Task.query.filter_by(project_id=project_id).count()
    if total_tasks == 0:
        return 0
    
    completed_tasks = Task.query.filter_by(project_id=project_id, status='completed').count()
    return (completed_tasks / total_tasks) * 100

def get_client_ip():
    """الحصول على IP العميل"""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0]
    return request.remote_addr

def is_safe_url(target):
    
    """التحقق من أمان URL"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def generate_password_reset_token(email):
    """توليد رمز إعادة تعيين كلمة المرور"""
    import jwt
    from flask import current_app
    
    expiry = datetime.utcnow() + timedelta(hours=24)
    token = jwt.encode(
        {'email': email, 'exp': expiry},
        current_app.config['SECRET_KEY'],
        algorithm='HS256'
    )
    return token

def verify_password_reset_token(token):
    """التحقق من رمز إعادة تعيين كلمة المرور"""
    import jwt
    from flask import current_app
    
    try:
        data = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=['HS256'])
        return data['email']
    except:
        return None
    
# أضف هذه الدوال إلى utils.py

def generate_qr_code(data):
    """توليد رمز QR"""
    import qrcode
    from io import BytesIO
    import base64
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # تحويل إلى base64
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return img_str

def send_task_reminders():
    """
    إرسال تذكيرات للمهام القادمة والمتأخرة
    تعمل بشكل دوري عبر Celery Beat أو cron job
    """
    from models import Task, User, Notification
    from datetime import datetime, timedelta
    from extensions import db
    import logging
    
    logger = logging.getLogger(__name__)
    now = datetime.utcnow()
    reminders_sent = {
        'upcoming': 0,
        'overdue': 0,
        'starting_soon': 0,
        'daily_digest': 0
    }
    
    try:
        # 1. تذكيرات المهام التي ستبدأ قريباً (خلال ساعة)
        soon_start = now + timedelta(hours=1)
        upcoming_tasks = Task.query.filter(
            Task.planned_start <= soon_start,
            Task.planned_start > now,
            Task.status == 'pending',
            Task.assigned_to_id.isnot(None)
        ).all()
        
        for task in upcoming_tasks:
            minutes_until_start = int((task.planned_start - now).total_seconds() / 60)
            
            # إرسال تذكير للمستخدم المسند إليه المهمة
            if task.assignee and task.assignee.notification_settings.get('task_reminders', True):
                # تحديد نوع التذكير حسب الوقت المتبقي
                if minutes_until_start <= 15:
                    urgency = 'high'
                    title = '🔴 تنبيه: مهمة على وشك البدء'
                    message = f'مهمة "{task.title}" ستبدأ خلال {minutes_until_start} دقيقة'
                elif minutes_until_start <= 30:
                    urgency = 'medium'
                    title = '🟡 تذكير: مهمة قريبة'
                    message = f'مهمة "{task.title}" ستبدأ خلال {minutes_until_start} دقيقة'
                else:
                    urgency = 'normal'
                    title = '🔵 تذكير: مهمة قادمة'
                    message = f'مهمة "{task.title}" ستبدأ بعد {minutes_until_start} دقيقة'
                
                send_notification(
                    user_id=task.assignee.id,
                    title=title,
                    message=message,
                    notification_type='reminder',
                    task_id=task.id,
                    project_id=task.project_id,
                    is_urgent=(urgency == 'high')
                )
                reminders_sent['starting_soon'] += 1
            
            # إرسال تذكير للمشرف (إذا كان مختلفاً)
            if task.project.manager_id and task.project.manager_id != task.assignee.id:
                manager = User.query.get(task.project.manager_id)
                if manager and manager.notification_settings.get('task_reminders', True):
                    send_notification(
                        user_id=manager.id,
                        title='📋 تذكير: مهمة لفريقك ستبدأ قريباً',
                        message=f'المهمة "{task.title}" في مشروع "{task.project.title}" ستبدأ خلال {minutes_until_start} دقيقة (مسندة إلى {task.assignee.full_name})',
                        notification_type='reminder',
                        task_id=task.id,
                        project_id=task.project_id
                    )
        
        # 2. تذكيرات المهام المتأخرة
        overdue_tasks = Task.query.filter(
            Task.planned_end < now,
            Task.status.in_(['pending', 'in_progress']),
            Task.assigned_to_id.isnot(None)
        ).all()
        
        for task in overdue_tasks:
            delay_days = (now - task.planned_end).days
            delay_hours = int((now - task.planned_end).total_seconds() / 3600)
            
            if task.assignee and task.assignee.notification_settings.get('task_reminders', True):
                if delay_days > 0:
                    title = '🔴 تنبيه: مهمة متأخرة'
                    message = f'مهمة "{task.title}" متأخرة بـ {delay_days} يوم'
                else:
                    title = '🟠 تنبيه: مهمة متأخرة'
                    message = f'مهمة "{task.title}" متأخرة بـ {delay_hours} ساعة'
                
                send_notification(
                    user_id=task.assignee.id,
                    title=title,
                    message=message,
                    notification_type='reminder',
                    task_id=task.id,
                    project_id=task.project_id,
                    is_urgent=True
                )
                reminders_sent['overdue'] += 1
            
            # إرسال تذكير لمدير المشروع
            if task.project.manager_id and task.project.manager_id != task.assignee.id:
                manager = User.query.get(task.project.manager_id)
                if manager and manager.notification_settings.get('task_reminders', True):
                    send_notification(
                        user_id=manager.id,
                        title='⚠️ تنبيه: مهمة متأخرة في مشروعك',
                        message=f'المهمة "{task.title}" في مشروع "{task.project.title}" متأخرة بـ {delay_days if delay_days > 0 else f"{delay_hours} ساعة"} (مسندة إلى {task.assignee.full_name})',
                        notification_type='reminder',
                        task_id=task.id,
                        project_id=task.project_id,
                        is_urgent=True
                    )
        
        # 3. تذكيرات المهام التي ستنتهي قريباً
        soon_end = now + timedelta(days=1)
        ending_soon_tasks = Task.query.filter(
            Task.planned_end <= soon_end,
            Task.planned_end > now,
            Task.status.in_(['pending', 'in_progress']),
            Task.assigned_to_id.isnot(None)
        ).all()
        
        for task in ending_soon_tasks:
            hours_left = int((task.planned_end - now).total_seconds() / 3600)
            
            if task.assignee and task.assignee.notification_settings.get('task_reminders', True):
                if hours_left <= 2:
                    title = '🔴 تنبيه: مهمة على وشك الانتهاء'
                    message = f'مهمة "{task.title}" متبقي عليها {hours_left} ساعة فقط'
                elif hours_left <= 6:
                    title = '🟡 تذكير: مهمة قريبة من الانتهاء'
                    message = f'مهمة "{task.title}" متبقي عليها {hours_left} ساعة'
                else:
                    title = '🔵 تذكير: موعد تسليم قريب'
                    message = f'مهمة "{task.title}" ستنتهي غداً'
                
                send_notification(
                    user_id=task.assignee.id,
                    title=title,
                    message=message,
                    notification_type='reminder',
                    task_id=task.id,
                    project_id=task.project_id
                )
                reminders_sent['upcoming'] += 1
        
        # 4. الملخص اليومي للمديرين (مرة واحدة في اليوم)
        if now.hour == 8:  # الساعة 8 صباحاً
            managers = User.query.filter_by(role='project_manager').all()
            
            for manager in managers:
                if manager.notification_settings.get('task_reminders', True):
                    # جلب مهام المشاريع التي يديرها
                    managed_projects = Project.query.filter_by(manager_id=manager.id).all()
                    
                    total_overdue = 0
                    total_upcoming = 0
                    tasks_list = []
                    
                    for project in managed_projects:
                        # المهام المتأخرة
                        overdue = Task.query.filter(
                            Task.project_id == project.id,
                            Task.planned_end < now,
                            Task.status.in_(['pending', 'in_progress'])
                        ).count()
                        total_overdue += overdue
                        
                        # المهام القادمة
                        upcoming = Task.query.filter(
                            Task.project_id == project.id,
                            Task.planned_start <= now + timedelta(days=3),
                            Task.planned_start > now,
                            Task.status == 'pending'
                        ).count()
                        total_upcoming += upcoming
                        
                        if overdue > 0 or upcoming > 0:
                            tasks_list.append(f"• {project.title}: {upcoming} قادمة، {overdue} متأخرة")
                    
                    if total_overdue > 0 or total_upcoming > 0:
                        message = f"ملخص يومي لمشاريعك:\n" + "\n".join(tasks_list)
                        
                        send_notification(
                            user_id=manager.id,
                            title='📊 الملخص اليومي للمشاريع',
                            message=message,
                            notification_type='daily_digest'
                        )
                        reminders_sent['daily_digest'] += 1
        
        logger.info(f"Reminders sent: {reminders_sent}")
        return reminders_sent
        
    except Exception as e:
        logger.error(f"Error sending task reminders: {str(e)}")
        raise e
    
def send_task_reminders_with_email():
    """
    نسخة متقدمة من دالة التذكيرات مع دعم البريد الإلكتروني
    """
    from models import Task, User, Notification
    from datetime import datetime, timedelta
    from extensions import db, mail
    from flask_mail import Message
    from flask import render_template
    import logging
    
    logger = logging.getLogger(__name__)
    now = datetime.utcnow()
    results = {'notifications': 0, 'emails': 0}
    
    try:
        # 1. المهام التي ستبدأ خلال 30 دقيقة
        soon_start = now + timedelta(minutes=30)
        starting_tasks = Task.query.filter(
            Task.planned_start <= soon_start,
            Task.planned_start > now,
            Task.status == 'pending',
            Task.assigned_to_id.isnot(None)
        ).all()
        
        for task in starting_tasks:
            user = task.assignee
            if not user:
                continue
            
            minutes_left = int((task.planned_start - now).total_seconds() / 60)
            
            # إشعار داخل التطبيق
            send_notification(
                user_id=user.id,
                title='⏰ مهمة على وشك البدء',
                message=f'المهمة "{task.title}" ستبدأ خلال {minutes_left} دقيقة',
                notification_type='reminder',
                task_id=task.id,
                project_id=task.project_id
            )
            results['notifications'] += 1
            
            # إرسال بريد إلكتروني إذا كان مفعلاً
            if user.notification_settings.get('email_notifications', True) and user.email:
                try:
                    msg = Message(
                        subject=f'⏰ تذكير: مهمة ستبدأ قريباً - {task.title}',
                        recipients=[user.email]
                    )
                    msg.html = render_template(
                        'emails/task_reminder.html',
                        user=user,
                        task=task,
                        minutes_left=minutes_left,
                        reminder_type='starting_soon'
                    )
                    mail.send(msg)
                    results['emails'] += 1
                except Exception as e:
                    logger.error(f"Failed to send email to {user.email}: {e}")
        
        # 2. المهام المتأخرة
        overdue_tasks = Task.query.filter(
            Task.planned_end < now,
            Task.status.in_(['pending', 'in_progress']),
            Task.assigned_to_id.isnot(None)
        ).all()
        
        for task in overdue_tasks:
            user = task.assignee
            if not user:
                continue
            
            delay = now - task.planned_end
            delay_minutes = int(delay.total_seconds() / 60)
            
            send_notification(
                user_id=user.id,
                title='⚠️ مهمة متأخرة',
                message=f'المهمة "{task.title}" متأخرة بـ {delay_minutes} دقيقة',
                notification_type='reminder',
                task_id=task.id,
                project_id=task.project_id,
                is_urgent=True
            )
            results['notifications'] += 1
            
            # إرسال بريد إلكتروني للمهام المتأخرة فقط كل 6 ساعات
            if delay_minutes % 360 < 30:  # كل 6 ساعات تقريباً
                if user.email and user.notification_settings.get('email_notifications', True):
                    try:
                        msg = Message(
                            subject=f'⚠️ تنبيه: مهمة متأخرة - {task.title}',
                            recipients=[user.email]
                        )
                        msg.html = render_template(
                            'emails/task_reminder.html',
                            user=user,
                            task=task,
                            delay_minutes=delay_minutes,
                            reminder_type='overdue'
                        )
                        mail.send(msg)
                        results['emails'] += 1
                    except Exception as e:
                        logger.error(f"Failed to send email to {user.email}: {e}")
        
        # 3. تذكيرات أسبوعية للمديرين (كل يوم أحد)
        if now.weekday() == 6:  # الأحد
            managers = User.query.filter_by(role='project_manager').all()
            
            for manager in managers:
                if manager.email and manager.notification_settings.get('email_notifications', True):
                    projects = Project.query.filter_by(manager_id=manager.id).all()
                    
                    if projects:
                        try:
                            msg = Message(
                                subject='📊 تقرير أسبوعي للمشاريع',
                                recipients=[manager.email]
                            )
                            msg.html = render_template(
                                'emails/weekly_report.html',
                                user=manager,
                                projects=projects,
                                now=now
                            )
                            mail.send(msg)
                            results['emails'] += 1
                        except Exception as e:
                            logger.error(f"Failed to send weekly report to {manager.email}: {e}")
        
        logger.info(f"Reminders sent successfully: {results}")
        return results
        
    except Exception as e:
        logger.error(f"Error in send_task_reminders_with_email: {str(e)}")
        raise e
    
# utils.py - دوال مساعدة لإدارة الفرق

def generate_invitation_token():
    """توليد رمز دعوة فريد"""
    import secrets
    return secrets.token_urlsafe(32)

def send_project_invitation_email(email, project, inviter, role, token):
    from flask_mail import Message
    from flask import url_for
    
    """إرسال بريد إلكتروني لدعوة المستخدم"""
    subject = f"دعوة للانضمام لمشروع {project.title}"
    
    invitation_link = url_for('accept_project_invitation', token=token, _external=True)
    
    html_content = f"""
    <html dir="rtl">
        <body>
            <h2>دعوة للانضمام للمشروع</h2>
            <p>مرحباً،</p>
            <p>لقد تمت دعوتك من قبل {inviter.full_name} للانضمام لمشروع "{project.title}" بدور {role}.</p>
            <p>للقبول، يرجى الضغط على الرابط التالي:</p>
            <p><a href="{invitation_link}">قبول الدعوة</a></p>
            <p>هذه الدعوة صالحة لمدة 7 أيام.</p>
            <br>
            <p>تحياتنا،</p>
            <p>فريق منصة إدارة المشاريع</p>
        </body>
    </html>
    """
    
    msg = Message(subject, recipients=[email], html=html_content)
    mail.send(msg)

def resend_project_invitation(invitation_id):
    """إعادة إرسال دعوة موجودة"""
    invitation = ProjectInvitation.query.get(invitation_id)
    if not invitation:
        return False, 'الدعوة غير موجودة'

    if invitation.status != 'pending':
        return False, 'لا يمكن إعادة إرسال دعوة غير معلقة'

    # تجديد رمز الدعوة وتاريخ الانتهاء
    import secrets
    invitation.token = secrets.token_urlsafe(32)
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)
    db.session.commit()

    # إرسال البريد الإلكتروني
    send_project_invitation_email(
        email=invitation.email,
        full_name=invitation.full_name,
        project=invitation.project,
        role=invitation.role_in_project,
        token=invitation.token,
        is_existing_user=invitation.existing_user_id is not None
    )

    return True, 'تم إعادة إرسال الدعوة بنجاح'
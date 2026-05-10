"""
notification_service.py - خدمة الإشعارات المركزية
"""
from app.models import db, Notification, User, Project, Task
from datetime import datetime
from flask import current_app, url_for
from flask_login import  current_user,logout_user
import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """خدمة موحدة لإدارة جميع الإشعارات في النظام"""
    
    # ============================================
    # إشعارات المهام
    # ============================================
    
    @staticmethod
    def task_assigned(task, assigned_to, assigned_by):
        """إشعار عند تعيين مهمة لمستخدم"""
        notification = Notification(
            user_id=assigned_to,
            title=f'📋 مهمة جديدة: {task.task_name}',
            message=f'تم تعيينك لمهمة {task.task_code} في مشروع {task.project.name}',
            notification_type='task_assigned',
            priority='high',
            related_project_id=task.project_id,
            related_task_id=task.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار للمشرف أيضاً
        if task.supervisor_id and task.supervisor_id != assigned_to:
            notif_supervisor = Notification(
                user_id=task.supervisor_id,
                title=f'👥 تعيين منفذ: {task.task_name}',
                message=f'تم تعيين {User.query.get(assigned_to).full_name} لمهمة {task.task_code}',
                notification_type='task_assigned_info',
                priority='low',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notif_supervisor)
        
        db.session.commit()
    
    @staticmethod
    def task_started(task, started_by):
        """إشعار عند بدء تنفيذ مهمة"""
        # إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != started_by:
            notification = Notification(
                user_id=task.supervisor_id,
                title=f'▶️ بدء تنفيذ: {task.task_name}',
                message=f'بدأ {User.query.get(started_by).full_name} تنفيذ مهمة {task.task_code}',
                notification_type='task_started',
                priority='medium',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notification)
        
        # إشعار لمدير المشروع
        if task.project.project_manager_id and task.project.project_manager_id not in [task.supervisor_id, started_by]:
            notification_pm = Notification(
                user_id=task.project.project_manager_id,
                title=f'🚀 تقدم في المشروع: {task.project.name}',
                message=f'بدأ تنفيذ مهمة {task.task_code} - {task.task_name}',
                notification_type='project_progress',
                priority='low',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notification_pm)
        
        # إشعار للمدير العام (صاحب الشركة)
        org_admins = User.query.filter_by(
            org_id=task.project.org_id,
            role='org_admin'
        ).all()

        for admin in org_admins:
            if admin.id != task.project.project_manager_id:
                notif = Notification(
                    user_id=admin.id,
                    title=f'🚀 بدء مهمة: {task.task_name}',
                    message=f'تم بدء مهمة {task.task_code} في مشروع {task.project.name}',
                    notification_type='task_started',
                    related_task_id=task.id,
                    related_project_id=task.project_id
                )
                db.session.add(notif)
        db.session.commit()
    
    @staticmethod
    def task_completed(task, completed_by, quality='good'):
        """إشعار عند إكمال مهمة"""
        quality_text = {
            'excellent': 'ممتازة',
            'good': 'جيدة',
            'fair': 'متوسطة',
            'poor': 'ضعيفة'
        }
        
        # إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != completed_by:
            notification = Notification(
                user_id=task.supervisor_id,
                title=f'✅ اكتمال مهمة: {task.task_name}',
                message=f'اكتملت مهمة {task.task_code} بجودة {quality_text.get(quality, quality)}',
                notification_type='task_completed',
                priority='high',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notification)
        
        # إشعار لمدير المشروع
        if task.project.project_manager_id and task.project.project_manager_id not in [task.supervisor_id, completed_by]:
            notification_pm = Notification(
                user_id=task.project.project_manager_id,
                title=f'🎯 إنجاز: {task.task_name}',
                message=f'تم إكمال مهمة {task.task_code} في مشروع {task.project.name}',
                notification_type='task_completed',
                priority='medium',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notification_pm)
        
        # إشعار للمدير العام
        admins = User.query.filter_by(org_id=task.project.org_id, role='org_admin').all()
        for admin in admins:
            if admin.id not in [task.supervisor_id, task.project.project_manager_id, completed_by]:
                notification_admin = Notification(
                    user_id=admin.id,
                    title=f'📊 تقدم مشروع: {task.project.name}',
                    message=f'اكتملت مهمة {task.task_code} - نسبة إنجاز المشروع: {task.project.progress.progress_percentage if task.project.progress else 0}%',
                    notification_type='project_progress',
                    priority='low',
                    related_project_id=task.project_id,
                    related_task_id=task.id
                )
                db.session.add(notification_admin)
        
        db.session.commit()
    
    @staticmethod
    def task_overdue(task, delay_days):
        """إشعار عند تأخر مهمة"""
        # إشعار للمنفذ
        delegate = User.query.get(task.delegate_id) if task.delegate_id else None
        if task.delegate_id:
            notification = Notification(
                user_id=task.delegate_id,
                title=f'⚠️ مهمة متأخرة: {task.task_name}',
                message=f'مهمتك {task.task_code} متأخرة {delay_days} أيام. يرجى الإسراع.',
                notification_type='task_overdue',
                priority='high',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notification)
        
        # إشعار للمشرف
        if task.supervisor_id:
            notification_sup = Notification(
                user_id=task.supervisor_id,
                title=f'⚠️ تنبيه تأخير: {task.task_name}',
                message=f'المهمة {task.task_code} للمندوب {delegate.full_name if delegate else "غير معين"} متأخرة {delay_days} أيام',
                notification_type='task_overdue_supervisor',
                priority='critical',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notification_sup)
        
        db.session.commit()
    
    @staticmethod
    def task_reminder(task, days_remaining):
        """تذكير بمهمة قبل موعدها"""
        if task.delegate_id:
            notification = Notification(
                user_id=task.delegate_id,
                title=f'⏰ تذكير: {task.task_name}',
                message=f'مهمتك {task.task_code} متبقٍ عليها {days_remaining} أيام',
                notification_type='task_reminder',
                priority='medium',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(notification)
            db.session.commit()

    @staticmethod
    def activity_documents_uploaded(self, activity, task, documents, uploader):
        """إشعار برفع مستندات للنشاط"""
        # إشعار للمشرف
        if activity.supervisor_id:
            notification = Notification(
                user_id=activity.supervisor_id,
                title=f'📎 مرفقات جديدة - {activity.activity_name}',
                message=f'تم رفع {len(documents)} مرفق بواسطة {uploader.full_name}',
                notification_type='activity_documents',
                priority='medium',
                related_link=url_for('attachments.get_activity_documents', activity_id=activity.id),
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
        
        # إشعار لمدير المشروع
        if activity.project.project_manager_id:
            pm_notif = Notification(
                user_id=activity.project.project_manager_id,
                title=f'📎 مرفقات جديدة - {activity.activity_name}',
                message=f'تم رفع {len(documents)} مرفق',
                notification_type='activity_documents',
                priority='medium',
                related_link=url_for('project.project_gallery', project_id=activity.project_id)
            )
            db.session.add(pm_notif)
        
        db.session.commit()

    @staticmethod
    def document_approved(self, document, approver):
        """إشعار باعتماد مستند"""
        notification = Notification(
            user_id=document.uploaded_by,
            title=f'✅ تم اعتماد المستند: {document.original_filename}',
            message=f'تم اعتماد المستند بواسطة {approver.full_name}',
            notification_type='document_approved',
            priority='low',
            related_link=document.file_url,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()

    @staticmethod
    def document_rejected(self, document, rejecter, reason):
        """إشعار برفض مستند"""
        notification = Notification(
            user_id=document.uploaded_by,
            title=f'❌ تم رفض المستند: {document.original_filename}',
            message=f'تم رفض المستند بواسطة {rejecter.full_name}\nالسبب: {reason}',
            notification_type='document_rejected',
            priority='medium',
            related_link=document.file_url,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    # ============================================
    # إشعارات المشاريع
    # ============================================
    
    @staticmethod
    def project_created(project, created_by):
        """إشعار عند إنشاء مشروع جديد"""
        # إشعار لمدير المشروع
        if project.project_manager_id and project.project_manager_id != created_by:
            notification = Notification(
                user_id=project.project_manager_id,
                title=f'🆕 مشروع جديد: {project.name}',
                message=f'تم تعيينك كمدير لمشروع {project.project_code}',
                notification_type='project_assigned',
                priority='high',
                related_project_id=project.id
            )
            db.session.add(notification)
        
        # إشعار للمالك (العميل)
        if project.client_id:
            notification_client = Notification(
                user_id=project.client_id,
                title=f'🏗️ بدء مشروع: {project.name}',
                message=f'تم إنشاء مشروع {project.project_code} وبدء العمل عليه',
                notification_type='project_created',
                priority='medium',
                related_project_id=project.id
            )
            db.session.add(notification_client)
        
        # إشعار للمدير العام
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            if admin.id not in [project.project_manager_id, created_by, project.client_id]:
                notification_admin = Notification(
                    user_id=admin.id,
                    title=f'📁 مشروع جديد: {project.name}',
                    message=f'تم إنشاء مشروع {project.project_code} بقيادة {project.project_manager.full_name if project.project_manager else "غير معين"}',
                    notification_type='project_created',
                    priority='medium',
                    related_project_id=project.id
                )
                db.session.add(notification_admin)
        
        db.session.commit()
    
    @staticmethod
    def project_started(project):
        """إشعار عند بدء المشروع"""
        # إشعار لجميع أعضاء الفريق
        team_members = set()
        if project.project_manager_id:
            team_members.add(project.project_manager_id)
        
        for task in project.tasks:
            if task.delegate_id:
                team_members.add(task.delegate_id)
            if task.supervisor_id:
                team_members.add(task.supervisor_id)
        
        for member_id in team_members:
            notification = Notification(
                user_id=member_id,
                title=f'🚀 بدء المشروع: {project.name}',
                message=f'بدأ مشروع {project.project_code} رسمياً. يرجى متابعة مهامك.',
                notification_type='project_started',
                priority='high',
                related_project_id=project.id
            )
            db.session.add(notification)
        
        # إشعار للمالك
        if project.client_id:
            notif_client = Notification(
                user_id=project.client_id,
                title=f'🚀 بدء تنفيذ مشروعك: {project.name}',
                message=f'تم بدء تنفيذ مشروع {project.project_code} حسب الجدول المحدد',
                notification_type='project_started',
                priority='high',
                related_project_id=project.id
            )
            db.session.add(notif_client)
        
        db.session.commit()
    
    @staticmethod
    def project_completed(project):
        """إشعار عند اكتمال المشروع"""
        # إشعار لجميع أعضاء الفريق
        team_members = set()
        if project.project_manager_id:
            team_members.add(project.project_manager_id)
        
        for task in project.tasks:
            if task.delegate_id:
                team_members.add(task.delegate_id)
            if task.supervisor_id:
                team_members.add(task.supervisor_id)
        
        for member_id in team_members:
            notification = Notification(
                user_id=member_id,
                title=f'🏆 اكتمال المشروع: {project.name}',
                message=f'تهانينا! تم إكمال مشروع {project.project_code} بنجاح',
                notification_type='project_completed',
                priority='high',
                related_project_id=project.id
            )
            db.session.add(notification)
        
        # إشعار للمالك
        if project.client_id:
            notif_client = Notification(
                user_id=project.client_id,
                title=f'🎉 اكتمال مشروعك: {project.name}',
                message=f'تم إكمال مشروع {project.project_code} بنجاح. شكراً لثقتكم بنا.',
                notification_type='project_completed',
                priority='high',
                related_project_id=project.id
            )
            db.session.add(notif_client)
        
        # إشعار للمدير العام
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            notification_admin = Notification(
                user_id=admin.id,
                title=f'🎉 اكتمال مشروع: {project.name}',
                message=f'تم إكمال مشروع {project.project_code} بنجاح',
                notification_type='project_completed',
                priority='high',
                related_project_id=project.id
            )
            db.session.add(notification_admin)
        
        db.session.commit()
    
    @staticmethod
    def project_updated(project, changes):
        """إشعار عند تحديث المشروع"""
        # إشعار لمدير المشروع
        if project.project_manager_id:
            notification = Notification(
                user_id=project.project_manager_id,
                title=f'📝 تحديث مشروع: {project.name}',
                message=f'تم تحديث بيانات المشروع: {changes}',
                notification_type='project_updated',
                priority='medium',
                related_project_id=project.id
            )
            db.session.add(notification)
        
        db.session.commit()
    
    # ============================================
    # إشعارات التسليمات
    # ============================================
    # app/services/notification_service.py


    @staticmethod
    def delivery_submitted(delivery, resource_request, total_delivered):
        """إشعار عند تقديم تسليم جديد"""
        confirm_url = url_for('company.confirm_delivery', delivery_id=delivery.id, _external=True)
        
        # إشعار لمدير المشروع
        if resource_request.project and resource_request.project.project_manager_id:
            notification_pm = Notification(
                user_id=resource_request.project.project_manager_id,
                title=f"تسليم مواد - {resource_request.project.name}",
                message=f"تم تسليم {total_delivered} وحدة من المواد للطلب #{resource_request.id}. يرجى تأكيد الاستلام.",
                notification_type='delivery_pending',
                priority='high',
                related_link=confirm_url,
                related_project_id=resource_request.project_id,
                related_delivery_id=delivery.id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_pm)
        
        # إشعار للمورد
        request_url = url_for('supplier.view_request', request_id=resource_request.id, _external=True)
        
        notification_supplier = Notification(
            user_id=resource_request.supplier_id,
            title=f"تم تسليم مواد - {resource_request.project.name}",
            message=f"تم تسجيل تسليم {total_delivered} وحدة من المواد للطلب #{resource_request.id}. في انتظار تأكيد مدير المشروع.",
            notification_type='delivery_submitted',
            priority='medium',
            related_link=request_url,
            related_project_id=resource_request.project_id,
            related_delivery_id=delivery.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification_supplier)
        
        # إشعار للمالك
        if resource_request.project and resource_request.project.client_id:
            notification_owner = Notification(
                user_id=resource_request.project.client_id,
                title=f"تسليم مواد - {resource_request.project.name}",
                message=f"تم تسليم {total_delivered} وحدة من المواد للمشروع. في انتظار التأكيد من مدير المشروع.",
                notification_type='delivery_submitted',
                priority='medium',
                related_link=url_for('projects.project_resource_requests', project_id=resource_request.project_id, _external=True),
                related_project_id=resource_request.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_owner)
        
        db.session.commit()
    
    @staticmethod
    def delivery_confirmed(delivery, resource_request, confirmed, notes):
        """إشعار بعد تأكيد أو رفض التسليم"""
        
        # إشعار للمورد
        confirm_url = url_for('supplier.view_request', request_id=resource_request.id, _external=True)
        
        if confirmed:
            title = f"✅ تم تأكيد استلام المواد - {resource_request.project.name}"
            message = f"تم تأكيد استلام المواد للطلب #{resource_request.id}. شكراً لك."
            notification_type = 'delivery_confirmed'
            priority = 'medium'
        else:
            title = f"❌ رفض استلام المواد - {resource_request.project.name}"
            message = f"تم رفض استلام المواد للطلب #{resource_request.id}. السبب: {notes}"
            notification_type = 'delivery_rejected'
            priority = 'high'
        
        notification_supplier = Notification(
            user_id=resource_request.supplier_id,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            related_link=confirm_url,
            related_project_id=resource_request.project_id,
            related_delivery_id=delivery.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification_supplier)
        
        # إشعار للمالك بتأكيد الاستلام (إذا كان هناك ملاحظات)
        if confirmed and notes:
            if resource_request.project and resource_request.project.client_id:
                notification_owner = Notification(
                    user_id=resource_request.project.client_id,
                    title=f"📝 ملاحظات على التسليم - {resource_request.project.name}",
                    message=f"مدير المشروع أضاف ملاحظات على التسليم: {notes}",
                    notification_type='delivery_notes',
                    priority='low',
                    related_link=url_for('projects.project_resource_requests', project_id=resource_request.project_id, _external=True),
                    related_project_id=resource_request.project_id,
                    related_delivery_id=delivery.id,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification_owner)
        
        # إشعار لإدارة الشركة (إذا كان هناك رفض أو ملاحظات مهمة)
        if not confirmed or (confirmed and notes and notes.strip()):
            admins = User.query.filter_by(role='org_admin', org_id=resource_request.org_id).all()
            
            for admin in admins:
                notification_admin = Notification(
                    user_id=admin.id,
                    title=f"⚠️ تنبيه: {'رفض' if not confirmed else 'ملاحظات'} تسليم - {resource_request.project.name}",
                    message=f"الطلب #{resource_request.id} - المورد {resource_request.supplier.full_name}\nالسبب: {notes}",
                    notification_type='delivery_alert',
                    priority='high' if not confirmed else 'medium',
                    related_link=url_for('projects.project_resource_requests', project_id=resource_request.project_id, _external=True),
                    related_project_id=resource_request.project_id,
                    related_delivery_id=delivery.id,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification_admin)
        
        db.session.commit()
    
    @staticmethod
    def delivery_partial(resource_request, remaining_items):
        """إشعار للمورد بالمواد المتبقية"""
        if remaining_items:
            message = f"المواد المتبقية للطلب #{resource_request.id}:\n"
            for item in remaining_items:
                message += f"• {item.resource_name}: {item.remaining_quantity} {item.unit}\n"
            
            notification = Notification(
                user_id=resource_request.supplier_id,
                title=f"📦 تذكير: مواد متبقية - {resource_request.project.name}",
                message=message[:500],  # الحد الأقصى للطول
                notification_type='remaining_items_reminder',
                priority='medium',
                related_link=url_for('supplier.view_request', request_id=resource_request.id, _external=True),
                related_project_id=resource_request.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
    @staticmethod  
    def offer_submitted( resource_request, items, supplier):
        """إشعار بتقديم عرض سعر جديد"""
        try:
            
            items_text = '\n'.join([f"- {i['resource_name']}: {i['price']} {i['currency']}" for i in items])
            
            notification = Notification(
                user_id=resource_request.project.project_manager_id,
                title=f'💰 عرض سعر جديد للطلب #{resource_request.id}',
                message=f'قام المورد {supplier.full_name} بتقديم عرض سعر للمواد التالية:\n{items_text}',
                notification_type='offer_submitted',
                priority='high',
                related_request_id=resource_request.id,
                related_project_id=resource_request.project_id,
                related_link=url_for('company.view_request_offers', request_id=resource_request.id, _external=True),
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            
            # إشعار لإدارة الشركة
            from app.models.core_models import User
            admins = User.query.filter_by(org_id=resource_request.org_id, role='org_admin').all()
            for admin in admins:
                admin_notif = Notification(
                    user_id=admin.id,
                    title=f'💰 عرض سعر جديد - مشروع {resource_request.project.name}',
                    message=f'تم استلام عرض سعر من المورد {supplier.full_name}',
                    notification_type='offer_submitted_alert',
                    priority='medium',
                    related_request_id=resource_request.id,
                    related_project_id=resource_request.project_id
                )
                db.session.add(admin_notif)
            
            db.session.commit()
            
        except Exception as e:
            print(f"خطأ في offer_submitted: {str(e)}")
            db.session.rollback()
            raise e

    @staticmethod
    def offer_approved(item, resource_request, approver, notes):
        """إشعار بقبول عرض السعر"""
        notification = Notification(
            user_id=resource_request.supplier_id,
            title=f'✅ تم اعتماد عرض سعرك - {item.resource_name}',
            message=f'تم اعتماد عرض سعرك للمادة {item.resource_name} بقيمة {item.offer_price} {item.offer_currency}\nالملاحظات: {notes}',
            notification_type='offer_approved',
            priority='high',
            related_request_id=resource_request.id,
            related_project_id=resource_request.project_id,
            related_link=url_for('supplier.view_request', request_id=resource_request.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()

    @staticmethod
    def offer_rejected(item, resource_request, rejecter, notes):
        """إشعار برفض عرض السعر"""
        notification = Notification(
            user_id=resource_request.supplier_id,
            title=f'❌ تم رفض عرض سعرك - {item.resource_name}',
            message=f'تم رفض عرض سعرك للمادة {item.resource_name}\nالسبب: {notes}',
            notification_type='offer_rejected',
            priority='medium',
            related_request_id=resource_request.id,
            related_project_id=resource_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    # app/services/notification_service.py
    @staticmethod 
    def send_reminder_to_supplier(resource_request, remaining_items):
        """إرسال تذكير للمورد بتسريع جلب المواد"""
        
        # تجهيز نص المواد المتبقية
        items_text = '\n'.join([
            f"• {item['name']}: {item['remaining']} {item['unit']} (مطلوب بحلول {item['required_date']})"
            for item in remaining_items
        ])
        
        notification = Notification(
            user_id=resource_request.supplier_id,
            title=f'⏰ تذكير عاجل: تسريع جلب المواد - الطلب #{resource_request.id}',
            message=f'الرجاء تسريع جلب المواد المتبقية للطلب #{resource_request.id}\n\nالمواد المتبقية:\n{items_text}\n\nالتاريخ المطلوب: {resource_request.required_date.strftime("%Y-%m-%d") if resource_request.required_date else "غير محدد"}',
            notification_type='reminder_to_supplier',
            priority='high',
            related_request_id=resource_request.id,
            related_project_id=resource_request.project_id,
            related_link=url_for('supplier.view_request', request_id=resource_request.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لإدارة الشركة بأن التذكير تم إرساله
        admins = User.query.filter_by(org_id=current_user.org_id, role='org_admin').all()
        for admin in admins:
            admin_notif = Notification(
                user_id=admin.id,
                title=f'📢 تم إرسال تذكير للمورد - الطلب #{resource_request.id}',
                message=f'تم إرسال تذكير للمورد {resource_request.supplier.full_name} لتسريع جلب المواد المتبقية',
                notification_type='reminder_sent',
                priority='medium',
                related_request_id=resource_request.id,
                related_project_id=resource_request.project_id
            )
            db.session.add(admin_notif)
        
        db.session.commit()
    @staticmethod 
    def send_remaining_items_notification(resource_request):
        """إرسال إشعار للمورد بالمواد المتبقية"""
        remaining_items = []
        for item in resource_request.items:
            if item.remaining_quantity > 0:
                remaining_items.append(f"{item.resource_name}: {item.remaining_quantity} {item.unit}")
        
        if remaining_items:
            message = f"المواد المتبقية للطلب #{resource_request.id}:\n" + "\n".join(remaining_items)
            
            notification = Notification(
                user_id=resource_request.supplier_id,
                title=f"تذكير: مواد متبقية - {resource_request.project.name}",
                title_ar=f"تذكير: مواد متبقية - {resource_request.project.name}",
                message=message,
                message_ar=message,
                notification_type='remaining_items_reminder',
                priority='medium',
                related_link=url_for('supplier.view_request', request_id=resource_request.id, _external=True),
                related_project_id=resource_request.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
    # أضف هذه الدوال في notification_service.py

    @staticmethod
    def equipment_request_created(equipment_request):
        """إشعار بإنشاء طلب معدات جديد"""
        from app.models import Notification
        
        # إشعار للمورد
        notification = Notification(
            user_id=equipment_request.supplier_id,
            title=f"طلب معدات جديد - {equipment_request.project.name}",
            title_ar=f"طلب معدات جديد - {equipment_request.project.name}",
            message=f"تم إنشاء طلب معدات جديد برقم {equipment_request.id}. يرجى تقديم عرض السعر.",
            message_ar=f"تم إنشاء طلب معدات جديد برقم {equipment_request.id}. يرجى تقديم عرض السعر.",
            notification_type='equipment_request_new',
            priority='high',
            related_link=url_for('supplier.view_equipment_request', request_id=equipment_request.id, _external=True),
            related_project_id=equipment_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def equipment_request_updated(equipment_request, new_status):
        """إشعار بتحديث حالة طلب المعدات"""
        from app.models import Notification
        
        status_messages = {
            'started': {'ar': 'بدأت عملية توريد المعدات', 'en': 'Equipment supply process started'},
            'completed': {'ar': 'اكتملت عملية توريد المعدات', 'en': 'Equipment supply completed'},
            'cancelled': {'ar': 'تم إلغاء طلب المعدات', 'en': 'Equipment request cancelled'}
        }
        
        message = status_messages.get(new_status, {'ar': f'تم تغيير حالة الطلب إلى {new_status}', 'en': f'Request status changed to {new_status}'})
        
        notification = Notification(
            user_id=equipment_request.supplier_id,
            title=f"تحديث طلب المعدات - {equipment_request.project.name}",
            title_ar=f"تحديث طلب المعدات - {equipment_request.project.name}",
            message=message['ar'],
            message_ar=message['ar'],
            notification_type=f'equipment_request_{new_status}',
            priority='medium',
            related_link=url_for('supplier.view_equipment_request', request_id=equipment_request.id, _external=True),
            related_project_id=equipment_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def equipment_offer_submitted(equipment_request, items, supplier):
        """إشعار بتقديم عرض سعر لمعدات"""
        from app.models import Notification
        
        # إشعار لمدير المشروع
        if equipment_request.project.project_manager_id:
            items_text = "\n".join([f"- {item['resource_name']}: {item['price']} {item['currency']}" for item in items])
            
            notification = Notification(
                user_id=equipment_request.project.project_manager_id,
                title=f"عرض سعر جديد - {equipment_request.project.name}",
                title_ar=f"عرض سعر جديد - {equipment_request.project.name}",
                message=f"قدم المورد {supplier.full_name} عرض سعر للطلب #{equipment_request.id}\n\nالعناصر:\n{items_text}",
                message_ar=f"قدم المورد {supplier.full_name} عرض سعر للطلب #{equipment_request.id}\n\nالعناصر:\n{items_text}",
                notification_type='equipment_offer_submitted',
                priority='high',
                related_link=url_for('projects.project_equipment_requests', project_id=equipment_request.project_id, _external=True),
                related_project_id=equipment_request.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()


    @staticmethod
    def equipment_offer_approved(item, equipment_request, approver, notes):
        """إشعار بقبول عرض سعر المعدات"""
        from app.models import Notification
        
        notification = Notification(
            user_id=equipment_request.supplier_id,
            title=f"تم اعتماد عرض السعر - {equipment_request.project.name}",
            title_ar=f"تم اعتماد عرض السعر - {equipment_request.project.name}",
            message=f"تم اعتماد عرض السعر للمعدة {item.resource_name} بسعر {item.offer_price} {item.offer_currency}\nملاحظات: {notes}",
            message_ar=f"تم اعتماد عرض السعر للمعدة {item.resource_name} بسعر {item.offer_price} {item.offer_currency}\nملاحظات: {notes}",
            notification_type='equipment_offer_approved',
            priority='high',
            related_link=url_for('supplier.view_equipment_request', request_id=equipment_request.id, _external=True),
            related_project_id=equipment_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def equipment_offer_rejected(item, equipment_request, rejecter, notes):
        """إشعار برفض عرض سعر المعدات"""
        from app.models import Notification
        
        notification = Notification(
            user_id=equipment_request.supplier_id,
            title=f"تم رفض عرض السعر - {equipment_request.project.name}",
            title_ar=f"تم رفض عرض السعر - {equipment_request.project.name}",
            message=f"تم رفض عرض السعر للمعدة {item.resource_name}\nالسبب: {notes}",
            message_ar=f"تم رفض عرض السعر للمعدة {item.resource_name}\nالسبب: {notes}",
            notification_type='equipment_offer_rejected',
            priority='high',
            related_link=url_for('supplier.view_equipment_request', request_id=equipment_request.id, _external=True),
            related_project_id=equipment_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def equipment_delivery_submitted(delivery, equipment_request, total_quantity):
        """إشعار بتقديم تسليم معدات"""
        from app.models import Notification
        
        confirm_url = url_for('projects.confirm_equipment_delivery', delivery_id=delivery.id, _external=True)
        
        # إشعار لمدير المشروع
        if equipment_request.project.project_manager_id:
            notification = Notification(
                user_id=equipment_request.project.project_manager_id,
                title=f"تسليم معدات - {equipment_request.project.name}",
                title_ar=f"تسليم معدات - {equipment_request.project.name}",
                message=f"تم تسليم {total_quantity} وحدة من المعدات للطلب #{equipment_request.id}. يرجى تأكيد الاستلام.",
                message_ar=f"تم تسليم {total_quantity} وحدة من المعدات للطلب #{equipment_request.id}. يرجى تأكيد الاستلام.",
                notification_type='equipment_delivery_pending',
                priority='high',
                related_link=confirm_url,
                related_project_id=equipment_request.project_id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()


    @staticmethod
    def equipment_delivery_confirmed(delivery, equipment_request, approved, notes):
        """إشعار بنتيجة تأكيد تسليم المعدات"""
        from app.models import Notification
        
        status_text = "تم تأكيد الاستلام" if approved else "تم رفض الاستلام"
        
        notification = Notification(
            user_id=equipment_request.supplier_id,
            title=f"{status_text} - {equipment_request.project.name}",
            title_ar=f"{status_text} - {equipment_request.project.name}",
            message=f"تم {status_text} للتسليم رقم {delivery.delivery_number}\nملاحظات: {notes}",
            message_ar=f"تم {status_text} للتسليم رقم {delivery.delivery_number}\nملاحظات: {notes}",
            notification_type='equipment_delivery_confirmed' if approved else 'equipment_delivery_rejected',
            priority='high' if approved else 'critical',
            related_link=url_for('supplier.view_equipment_request', request_id=equipment_request.id, _external=True),
            related_project_id=equipment_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def send_equipment_reminder_to_supplier(equipment_request, remaining_items):
        """إرسال تذكير للمورد بالمعدات المتبقية"""
        from app.models import Notification
        
        items_text = "\n".join([f"- {item['name']}: {item['remaining']} {item['unit']} (مطلوب بحلول {item['required_date']})" for item in remaining_items])
        
        notification = Notification(
            user_id=equipment_request.supplier_id,
            title=f"تذكير: معدات متبقية - {equipment_request.project.name}",
            title_ar=f"تذكير: معدات متبقية - {equipment_request.project.name}",
            message=f"الكميات المتبقية من المعدات للطلب #{equipment_request.id}:\n{items_text}\nالرجاء الإسراع في توريدها.",
            message_ar=f"الكميات المتبقية من المعدات للطلب #{equipment_request.id}:\n{items_text}\nالرجاء الإسراع في توريدها.",
            notification_type='equipment_remaining_reminder',
            priority='high',
            related_link=url_for('supplier.view_equipment_request', request_id=equipment_request.id, _external=True),
            related_project_id=equipment_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    # ============================================
    # إشعارات المستخدمين
    # ============================================
    
    @staticmethod
    def user_registered(user):
        """إشعار عند تسجيل مستخدم جديد"""
        # إشعار للمدير العام
        admins = User.query.filter_by(org_id=user.org_id, role='org_admin').all()
        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                title=f'👤 مستخدم جديد: {user.full_name}',
                message=f'تم تسجيل مستخدم جديد: {user.email} بدور {user.role}',
                notification_type='user_registered',
                priority='medium',
                related_user_id=user.id
            )
            db.session.add(notification)
        
        # إشعار ترحيبي للمستخدم الجديد
        welcome = Notification(
            user_id=user.id,
            title=f'🎉 مرحباً بك {user.full_name}',
            message=f'تم إنشاء حسابك بنجاح. يمكنك الآن بدء استخدام النظام.',
            notification_type='user_welcome',
            priority='low',
            related_user_id=user.id
        )
        db.session.add(welcome)
        db.session.commit()
    
    @staticmethod
    def user_approved(user, approved_by):
        """إشعار عند الموافقة على حساب مستخدم"""
        notification = Notification(
            user_id=user.id,
            title=f'✅ تم تفعيل حسابك',
            message=f'تمت الموافقة على حسابك بواسطة {approved_by.full_name}. يمكنك الآن تسجيل الدخول.',
            notification_type='user_approved',
            priority='high',
            related_user_id=user.id
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def user_role_changed(user, old_role, new_role, changed_by):
        """إشعار عند تغيير دور المستخدم"""
        notification = Notification(
            user_id=user.id,
            title=f'🔄 تغيير صلاحيات الحساب',
            message=f'تم تغيير دورك من {old_role} إلى {new_role} بواسطة {changed_by.full_name}',
            notification_type='user_role_changed',
            priority='high',
            related_user_id=user.id
        )
        db.session.add(notification)
        db.session.commit()
    
    # ============================================
    # إشعارات المخاطر والمشكلات
    # ============================================
    @staticmethod
    def meeting_scheduled(user_id, meeting, role):
        """إشعار بجدولة اجتماع"""
        notification = Notification(
            user_id=user_id,
            title=f'اجتماع جديد: {meeting.title}',
            message=f'تم جدولة اجتماع {meeting.title} في {meeting.scheduled_date.strftime("%Y-%m-%d")} الساعة {meeting.start_time.strftime("%H:%M") if meeting.start_time else "-"}',
            notification_type='meeting_scheduled',
            related_link=url_for('company.view_meeting', meeting_id=meeting.id),
            related_project_id=meeting.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def meeting_reminder(user_id, meeting, urgency='normal'):
        """تذكير باجتماع قادم"""
        if urgency == 'urgent':
            title = f'تذكير عاجل: اجتماع {meeting.title} بعد ساعة'
            message = f'سيبدأ اجتماع {meeting.title} بعد ساعة في {meeting.start_time.strftime("%H:%M") if meeting.start_time else "-"}'
        else:
            title = f'تذكير: اجتماع {meeting.title} غداً'
            message = f'لديك اجتماع {meeting.title} غداً الساعة {meeting.start_time.strftime("%H:%M") if meeting.start_time else "-"}'
        
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type='meeting_reminder',
            related_link=url_for('company.view_meeting', meeting_id=meeting.id),
            related_project_id=meeting.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def meeting_completed(user_id, meeting):
        """إشعار بانتهاء اجتماع"""
        notification = Notification(
            user_id=user_id,
            title=f'انتهاء اجتماع: {meeting.title}',
            message=f'تم انتهاء اجتماع {meeting.title}. يمكنك الاطلاع على المحضر',
            notification_type='meeting_completed',
            related_link=url_for('company.view_meeting', meeting_id=meeting.id),
            related_project_id=meeting.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def meeting_cancelled(user_id, meeting):
        """إشعار بإلغاء اجتماع"""
        notification = Notification(
            user_id=user_id,
            title=f'إلغاء اجتماع: {meeting.title}',
            message=f'تم إلغاء اجتماع {meeting.title} المقرر في {meeting.scheduled_date.strftime("%Y-%m-%d")}',
            notification_type='meeting_cancelled',
            related_project_id=meeting.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def risk_detected2(risk, project, severity):
        """إشعار باكتشاف خطر"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'خطر جديد: {risk.title}',
            message=f'تم اكتشاف خطر جديد في المشروع {project.name} بمستوى {severity}',
            notification_type='risk_detected',
            related_link=url_for('company.view_risk', risk_id=risk.id),
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()


    @staticmethod
    def issue_reported2(issue, project, priority):
        """إشعار بقضية جديدة"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'قضية جديدة: {issue.title}',
            message=f'تم الإبلاغ عن قضية جديدة في المشروع {project.name} بأولوية {priority}',
            notification_type='issue_reported',
            related_link=url_for('company.view_issue', issue_id=issue.id),
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    @staticmethod
    def risk_detected(risk):
        """إشعار عند اكتشاف خطر جديد"""
        # إشعار لمدير المشروع
        if risk.project.project_manager_id:
            notification = Notification(
                user_id=risk.project.project_manager_id,
                title=f'⚠️ خطر جديد: {risk.title}',
                message=f'تم اكتشاف خطر جديد في مشروع {risk.project.name} بدرجة {risk.risk_level}',
                notification_type='risk_detected',
                priority='critical' if risk.risk_level == 'critical' else 'high',
                related_project_id=risk.project_id,
                related_risk_id=risk.id
            )
            db.session.add(notification)
        
        # إشعار للمالك
        if risk.project.client_id:
            notif_client = Notification(
                user_id=risk.project.client_id,
                title=f'⚠️ تنبيه خطر في مشروعك: {risk.title}',
                message=f'تم اكتشاف خطر جديد في مشروع {risk.project.name} بدرجة {risk.risk_level}',
                notification_type='risk_alert',
                priority='high',
                related_project_id=risk.project_id,
                related_risk_id=risk.id
            )
            db.session.add(notif_client)
        
        # إشعار للمشرفين
        supervisors = set()
        for task in risk.project.tasks:
            if task.supervisor_id:
                supervisors.add(task.supervisor_id)
        
        for sup_id in supervisors:
            if sup_id != risk.project.project_manager_id and sup_id != risk.project.client_id:
                notif = Notification(
                    user_id=sup_id,
                    title=f'⚠️ تنبيه خطر: {risk.title}',
                    message=f'خطر جديد في المشروع: {risk.description[:100] if risk.description else risk.title}',
                    notification_type='risk_alert',
                    priority='high',
                    related_project_id=risk.project_id,
                    related_risk_id=risk.id
                )
                db.session.add(notif)
        
        db.session.commit()
    
    @staticmethod
    def risk_mitigated(risk):
        """إشعار عند تخفيف خطر"""
        # إشعار لمدير المشروع
        if risk.project.project_manager_id:
            notification = Notification(
                user_id=risk.project.project_manager_id,
                title=f'✅ تم تخفيف خطر: {risk.title}',
                message=f'تم تخفيف خطر {risk.title} في مشروع {risk.project.name}',
                notification_type='risk_mitigated',
                priority='medium',
                related_project_id=risk.project_id,
                related_risk_id=risk.id
            )
            db.session.add(notification)
        
        db.session.commit()
    
    @staticmethod
    def issue_reported(issue):
        """إشعار عند الإبلاغ عن مشكلة"""
        # إشعار للمشرف المختص
        if issue.assigned_to:
            notification = Notification(
                user_id=issue.assigned_to,
                title=f'🔴 مشكلة جديدة: {issue.title}',
                message=f'تم تعيينك لمشكلة في مشروع {issue.project.name}',
                notification_type='issue_assigned',
                priority='high',
                related_project_id=issue.project_id,
                related_issue_id=issue.id
            )
            db.session.add(notification)
        
        # إشعار لمدير المشروع
        if issue.project.project_manager_id and issue.project.project_manager_id != issue.assigned_to:
            notif_pm = Notification(
                user_id=issue.project.project_manager_id,
                title=f'📌 مشكلة في المشروع: {issue.title}',
                message=f'تم الإبلاغ عن مشكلة جديدة: {issue.description[:100] if issue.description else issue.title}',
                notification_type='issue_reported',
                priority='medium',
                related_project_id=issue.project_id,
                related_issue_id=issue.id
            )
            db.session.add(notif_pm)
        
        db.session.commit()
    
    @staticmethod
    def issue_resolved(issue):
        """إشعار عند حل مشكلة"""
        # إشعار للمبلغ
        if issue.reported_by:
            notification = Notification(
                user_id=issue.reported_by,
                title=f'✅ تم حل المشكلة: {issue.title}',
                message=f'تم حل المشكلة التي أبلغت عنها في مشروع {issue.project.name}',
                notification_type='issue_resolved',
                priority='medium',
                related_project_id=issue.project_id,
                related_issue_id=issue.id
            )
            db.session.add(notification)
        
        db.session.commit()
    
    # ============================================
    # إشعارات المستندات
    # ============================================
    
    @staticmethod
    def document_uploaded(document):
        """إشعار عند رفع مستند جديد"""
        # إشعار لمدير المشروع
        if document.project.project_manager_id:
            notification = Notification(
                user_id=document.project.project_manager_id,
                title=f'📄 مستند جديد: {document.title or document.original_filename}',
                message=f'تم رفع مستند {document.original_filename} في مشروع {document.project.name}',
                notification_type='document_uploaded',
                priority='low',
                related_project_id=document.project_id,
                related_document_id=document.id
            )
            db.session.add(notification)
        
        # إشعار للمالك
        if document.project.client_id:
            notif_client = Notification(
                user_id=document.project.client_id,
                title=f'📄 مستند جديد في مشروعك',
                message=f'تم رفع مستند {document.original_filename} في مشروع {document.project.name}',
                notification_type='document_uploaded',
                priority='low',
                related_project_id=document.project_id,
                related_document_id=document.id
            )
            db.session.add(notif_client)
        
        db.session.commit()
    
    @staticmethod
    def document_approved(document, approved_by):
        """إشعار عند الموافقة على مستند"""
        if document.uploaded_by:
            notification = Notification(
                user_id=document.uploaded_by,
                title=f'✅ الموافقة على المستند: {document.title or document.original_filename}',
                message=f'تمت الموافقة على مستندك {document.original_filename} بواسطة {approved_by.full_name}',
                notification_type='document_approved',
                priority='medium',
                related_project_id=document.project_id,
                related_document_id=document.id
            )
            db.session.add(notification)
            db.session.commit()
    
    # ============================================
    # إشعارات الدردشة والتعليقات
    # ============================================
    
    @staticmethod
    def new_message(chat, message, sender, mentioned_users=None):
        """إشعار برسالة جديدة في الدردشة"""
        from app.models import ChatParticipant
        
        # إشعار لجميع المشاركين في المحادثة
        participants = ChatParticipant.query.filter_by(chat_id=chat.id).all()
        for participant in participants:
            if participant.user_id != sender.id:
                notification = Notification(
                    user_id=participant.user_id,
                    title=f'💬 رسالة جديدة: {chat.name}',
                    message=f'{sender.full_name}: {message.content[:100]}',
                    notification_type='new_message',
                    priority='low',
                    related_project_id=chat.project_id,
                    related_task_id=chat.task_id
                )
                db.session.add(notification)
        
        # إشعارات للمستخدمين المذكورين
        if mentioned_users:
            for user_id in mentioned_users:
                if user_id != sender.id:
                    mention_notif = Notification(
                        user_id=user_id,
                        title=f'🔔 تم ذكرك في محادثة',
                        message=f'ذكرك {sender.full_name} في محادثة {chat.name}',
                        notification_type='mention',
                        priority='medium',
                        related_project_id=chat.project_id,
                        related_task_id=chat.task_id
                    )
                    db.session.add(mention_notif)
        
        db.session.commit()
    
    @staticmethod
    def new_comment(comment):
        """إشعار بتعليق جديد"""
        # إشعار لصاحب المهمة
        if comment.task_id:
            task = Task.query.get(comment.task_id)
            if task and task.delegate_id and task.delegate_id != comment.user_id:
                notification = Notification(
                    user_id=task.delegate_id,
                    title=f'💭 تعليق جديد على مهمتك',
                    message=f'{comment.user.full_name} علق على مهمة {task.task_name}: {comment.content[:100]}',
                    notification_type='new_comment',
                    priority='low',
                    related_project_id=task.project_id,
                    related_task_id=task.id
                )
                db.session.add(notification)
            
            # إشعار للمشرف
            if task and task.supervisor_id and task.supervisor_id not in [comment.user_id, task.delegate_id]:
                notif_sup = Notification(
                    user_id=task.supervisor_id,
                    title=f'💬 تعليق على مهمة',
                    message=f'{comment.user.full_name} علق على مهمة {task.task_name}',
                    notification_type='new_comment',
                    priority='low',
                    related_project_id=task.project_id,
                    related_task_id=task.id
                )
                db.session.add(notif_sup)
        
        db.session.commit()
    
    # ============================================
    # إشعارات التحقق
    # ============================================
    
    @staticmethod
    def verification_submitted(task, requirement, user_id):
        """إشعار عند تقديم طلب تحقق"""
        notification = Notification(
            user_id=task.supervisor_id,
            title=f'📋 طلب تحقق جديد: {task.task_name}',
            message=f'تم تقديم طلب تحقق للمتطلب: {requirement.description}',
            notification_type='verification_submitted',
            priority='medium',
            related_task_id=task.id,
            related_project_id=task.project_id,
            verification_request_id=requirement.id
        )
        db.session.add(notification)
        db.session.commit()

    @staticmethod
    def verification_result(task, user_id, approved, requirement_desc):
        """إشعار بنتيجة طلب التحقق"""
        status = 'تمت الموافقة' if approved else 'تم الرفض'
        icon = '✅' if approved else '❌'
        
        notification = Notification(
            user_id=user_id,
            title=f'{icon} نتيجة طلب التحقق',
            message=f'{status} على المتطلب: {requirement_desc}',
            notification_type='verification_result',
            priority='high' if not approved else 'medium',
            related_task_id=task.id,
            related_project_id=task.project_id
        )
        db.session.add(notification)
        db.session.commit()
    
    # ============================================
    # إشعارات الموارد
    # ============================================
    
    @staticmethod
    def resource_low_stock(resource):
        """إشعار عند انخفاض مخزون المورد"""
        # إشعار للموردين
        if resource.supplier_id:
            notification = Notification(
                user_id=resource.supplier_id,
                title=f'⚠️ مخزون منخفض: {resource.name}',
                message=f'المخزون المتبقي: {resource.available_quantity} {resource.unit} أقل من الحد الأدنى {resource.minimum_quantity}',
                notification_type='resource_low_stock',
                priority='high',
                related_resource_id=resource.id
            )
            db.session.add(notification)
        
        # إشعار لمدير المشروع
        projects = Project.query.filter_by(org_id=resource.org_id).all()
        for project in projects:
            if project.project_manager_id:
                notif_pm = Notification(
                    user_id=project.project_manager_id,
                    title=f'⚠️ تنبيه مخزون: {resource.name}',
                    message=f'مخزون {resource.name} منخفض، يرجى إعادة التوريد',
                    notification_type='resource_low_stock',
                    priority='medium',
                    related_resource_id=resource.id
                )
                db.session.add(notif_pm)
        
        db.session.commit()
    
    @staticmethod
    def resource_request_created(resource_request):
        """إشعار عند إنشاء طلب توريد جديد"""
        # إشعار للمورد
        notification = Notification(
            user_id=resource_request.supplier_id,
            title=f'📦 طلب توريد جديد: {resource_request.project.name}',
            message=f'تم إنشاء طلب توريد جديد للمشروع {resource_request.project.name}، التاريخ المطلوب: {resource_request.required_date}',
            notification_type='resource_request_created',
            priority='high',
            related_project_id=resource_request.project_id,
            related_request_id=resource_request.id
        )
        db.session.add(notification)
        
        # إشعار لمدير المشروع
        if resource_request.project.project_manager_id:
            notif_pm = Notification(
                user_id=resource_request.project.project_manager_id,
                title=f'📦 تم إرسال طلب توريد',
                message=f'تم إرسال طلب التوريد #{resource_request.id} إلى المورد {resource_request.supplier.full_name}',
                notification_type='resource_request_sent',
                priority='medium',
                related_project_id=resource_request.project_id,
                related_request_id=resource_request.id
            )
            db.session.add(notif_pm)
        
        db.session.commit()
    @staticmethod
    def resource_request_updated(resource_request,new_status):
        """إشعار عند إنشاء طلب توريد جديد"""
        # إشعار للمورد
        notification = Notification(
            user_id=resource_request.supplier_id,
            title=f'📦 تحديث طلب توريد: {resource_request.project.name}',
            message=f'تم  تغيير حالة الطلب إلى {new_status}،',
            notification_type='resource_request_created',
            priority='high',
            related_project_id=resource_request.project_id,
            related_request_id=resource_request.id
        )
        db.session.add(notification)
        
        # إشعار لمدير المشروع
        if resource_request.project.project_manager_id:
            notif_pm = Notification(
                user_id=resource_request.project.project_manager_id,
                title=f'📦 تم إرسال تحديث طلب توريد',
                message=f'تم إرسال تحديث طلب التوريد #{resource_request.id} إلى المورد {resource_request.supplier.full_name}',
                notification_type='resource_request_sent',
                priority='medium',
                related_project_id=resource_request.project_id,
                related_request_id=resource_request.id
            )
            db.session.add(notif_pm)
        
        db.session.commit()
    @staticmethod
    def remind_supplier_notification(resource_request):
        """إشعار عند إنشاء طلب توريد جديد"""
        # إشعار للمورد
        notification = Notification(
            user_id=resource_request.supplier_id,
            title=f'📦 تذكير طلب توريد: {resource_request.project.name}',
            message=f'يرجى  مراجعة طلب التوريد للمشروع {resource_request.project.name}،التاريخ المطلوب: {resource_request.required_date}',
            notification_type='reminder',
            priority='high',
            related_project_id=resource_request.project_id,
            related_request_id=resource_request.id
        )
        db.session.add(notification)
        
        db.session.commit()
    # ============================================
    # إشعارات النظام
    # ============================================
    
    @staticmethod
    def system_alert(message, title='🔔 تنبيه النظام', priority='medium', user_id=None):
        """إشعار عام للنظام"""
        if user_id:
            # إشعار لمستخدم محدد
            notification = Notification(
                user_id=user_id,
                title=title,
                message=message,
                notification_type='system_alert',
                priority=priority
            )
            db.session.add(notification)
        else:
            # إشعار لجميع المديرين
            admins = User.query.filter_by(role='org_admin').all()
            for admin in admins:
                notification = Notification(
                    user_id=admin.id,
                    title=title,
                    message=message,
                    notification_type='system_alert',
                    priority=priority
                )
                db.session.add(notification)
        
        db.session.commit()
    
    @staticmethod
    def eps_assigned(eps, user):
        """إشعار عند تعيين EPS"""
        notification = Notification(
            user_id=user.id,
            title=f'📊 تعيين EPS: {eps.name}',
            message=f'تم تعيينك كمدير لهيكل EPS {eps.name}',
            notification_type='eps_assigned',
            priority='medium',
            related_eps_id=eps.id
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def performance_report(user, report_data):
        """تقرير أداء دوري"""
        notification = Notification(
            user_id=user.id,
            title=f'📊 تقرير أدائك',
            message=f'إنجازك هذا الأسبوع: {report_data}',
            notification_type='performance_report',
            priority='low'
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def daily_summary(user, summary_data):
        """ملخص يومي للإشعارات"""
        notification = Notification(
            user_id=user.id,
            title=f'📅 ملخص يومي',
            message=f'ملخص أنشطتك اليوم: {summary_data}',
            notification_type='daily_summary',
            priority='low'
        )
        db.session.add(notification)
        db.session.commit()

    # اشعارات تجاوز الميزانية
    @staticmethod
    def cost_overrun_alert(project, overrun_amount, overrun_percentage):
        """إشعار بتجاوز الميزانية"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'⚠️ تجاوز ميزانية المشروع - {project.name}',
            title_ar=f'⚠️ تجاوز ميزانية المشروع - {project.name}',
            message=f'تم تجاوز ميزانية المشروع بمبلغ {overrun_amount:,.2f} ريال ({overrun_percentage:.1f}%)',
            message_ar=f'تم تجاوز ميزانية المشروع بمبلغ {overrun_amount:,.2f} ريال ({overrun_percentage:.1f}%)',
            notification_type='cost_overrun',
            priority='high',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لإدارة الشركة
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            admin_notif = Notification(
                user_id=admin.id,
                title=f'⚠️ تنبيه: تجاوز ميزانية مشروع {project.name}',
                title_ar=f'⚠️ تنبيه: تجاوز ميزانية مشروع {project.name}',
                message=f'تم تجاوز ميزانية المشروع بمبلغ {overrun_amount:,.2f} ريال ({overrun_percentage:.1f}%)',
                message_ar=f'تم تجاوز ميزانية المشروع بمبلغ {overrun_amount:,.2f} ريال ({overrun_percentage:.1f}%)',
                notification_type='cost_overrun_alert',
                priority='high',
                related_project_id=project.id,
                send_email=True,
                send_push=True
            )
            db.session.add(admin_notif)
        
        db.session.commit()

    @staticmethod
    def cost_critical_overrun(project, overrun_percentage, overrun_amount):
        """إشعار بتجاوز خطير للميزانية"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'🔴 تنبيه عاجل: تجاوز خطير في ميزانية {project.name}',
            title_ar=f'🔴 تنبيه عاجل: تجاوز خطير في ميزانية {project.name}',
            message=f'تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال). مطلوب تدخل فوري!',
            message_ar=f'تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال). مطلوب تدخل فوري!',
            notification_type='cost_critical_overrun',
            priority='critical',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()

    @staticmethod
    def activity_cost_overrun(activity, overrun_amount, overrun_percentage):
        """إشعار بتجاوز ميزانية نشاط"""
        notification = Notification(
            user_id=activity.supervisor_id,
            title=f'⚠️ تجاوز ميزانية النشاط - {activity.activity_name}',
            title_ar=f'⚠️ تجاوز ميزانية النشاط - {activity.activity_name}',
            message=f'تم تجاوز ميزانية النشاط بمبلغ {overrun_amount:,.2f} ريال ({overrun_percentage:.1f}%)',
            message_ar=f'تم تجاوز ميزانية النشاط بمبلغ {overrun_amount:,.2f} ريال ({overrun_percentage:.1f}%)',
            notification_type='activity_cost_overrun',
            priority='high',
            related_project_id=activity.project_id,
            related_task_id=None,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    # اشعارات الانشطه والمهام المكتمله واشعارات لبدء التالي 
    @staticmethod
    def activity_ready_to_start(activity, completed_predecessors, receiver_id, role):
        """إشعار بأن النشاط جاهز للبدء بعد اكتمال الأنشطة السابقة"""
        predecessors_names = [a.activity_name for a in completed_predecessors]
        
        role_text = {
            'supervisor': 'المشرف',
            'delegate': 'المنفذ',
            'manager': 'مدير المشروع'
        }.get(role, 'المستخدم')
        
        notification = Notification(
            user_id=receiver_id,
            title=f'✅ جاهزية النشاط: {activity.activity_name}',
            title_ar=f'✅ جاهزية النشاط: {activity.activity_name}',
            message=f'اكتملت الأنشطة السابقة: {", ".join(predecessors_names)}. يمكنك الآن بدء النشاط {activity.activity_name}.',
            message_ar=f'اكتملت الأنشطة السابقة: {", ".join(predecessors_names)}. يمكنك الآن بدء النشاط {activity.activity_name}.',
            notification_type='activity_ready_to_start',
            priority='high',
            related_project_id=activity.project_id,
            related_task_id=None,
            related_link=url_for('primavera.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار إضافي للمشرف إذا كان المستلم هو المنفذ
        if role == 'delegate' and activity.supervisor_id:
            supervisor_notif = Notification(
                user_id=activity.supervisor_id,
                title=f'📋 نشاط جاهز للتنفيذ: {activity.activity_name}',
                title_ar=f'📋 نشاط جاهز للتنفيذ: {activity.activity_name}',
                message=f'النشاط {activity.activity_name} جاهز للبدء بعد اكتمال الأنشطة السابقة. تم تعيين {User.query.get(receiver_id).full_name} للتنفيذ.',
                message_ar=f'النشاط {activity.activity_name} جاهز للبدء بعد اكتمال الأنشطة السابقة. تم تعيين {User.query.get(receiver_id).full_name} للتنفيذ.',
                notification_type='activity_ready_assigned',
                priority='medium',
                related_project_id=activity.project_id,
                related_link=url_for('primavera.view_activity', activity_id=activity.id)
            )
            db.session.add(supervisor_notif)
        
        db.session.commit()
    
    @staticmethod
    def task_ready_to_start(task, completed_predecessors, receiver_id, role):
        """إشعار بأن المهمة جاهزة للبدء بعد اكتمال المهام السابقة"""
        predecessors_names = [t.task_name for t in completed_predecessors]
        
        role_text = {
            'delegate': 'المنفذ',
            'supervisor': 'المشرف',
            'manager': 'مدير المشروع'
        }.get(role, 'المستخدم')
        
        notification = Notification(
            user_id=receiver_id,
            title=f'✅ جاهزية المهمة: {task.task_name}',
            title_ar=f'✅ جاهزية المهمة: {task.task_name}',
            message=f'اكتملت المهام السابقة: {", ".join(predecessors_names)}. يمكنك الآن بدء المهمة {task.task_name}.',
            message_ar=f'اكتملت المهام السابقة: {", ".join(predecessors_names)}. يمكنك الآن بدء المهمة {task.task_name}.',
            notification_type='task_ready_to_start',
            priority='high',
            related_project_id=task.project_id,
            related_task_id=task.id,
            related_link=url_for('company.view_task', task_id=task.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار للمشرف إذا كان المستلم هو المنفذ
        if role == 'delegate' and task.supervisor_id:
            supervisor_notif = Notification(
                user_id=task.supervisor_id,
                title=f'📋 مهمة جاهزة للتنفيذ: {task.task_name}',
                title_ar=f'📋 مهمة جاهزة للتنفيذ: {task.task_name}',
                message=f'المهمة {task.task_name} جاهزة للبدء بعد اكتمال المهام السابقة. تم تعيين {User.query.get(receiver_id).full_name} للتنفيذ.',
                message_ar=f'المهمة {task.task_name} جاهزة للبدء بعد اكتمال المهام السابقة. تم تعيين {User.query.get(receiver_id).full_name} للتنفيذ.',
                notification_type='task_ready_assigned',
                priority='medium',
                related_project_id=task.project_id,
                related_task_id=task.id,
                related_link=url_for('company.view_task', task_id=task.id)
            )
            db.session.add(supervisor_notif)
        
        db.session.commit()

    @staticmethod
    def predecessor_activity_delayed(activity, delayed_activity, receiver_id):
        """إشعار بأن نشاط سابق متأخر يؤثر على النشاط الحالي"""
        delay_days = (datetime.now() - delayed_activity.planned_finish).days if delayed_activity.planned_finish else 0
        
        notification = Notification(
            user_id=receiver_id,
            title=f'⚠️ تنبيه: تأخر في النشاط السابق - {activity.activity_name}',
            title_ar=f'⚠️ تنبيه: تأخر في النشاط السابق - {activity.activity_name}',
            message=f'النشاط السابق {delayed_activity.activity_name} متأخر {delay_days} يوماً. هذا سيؤثر على بدء نشاطك {activity.activity_name}.',
            message_ar=f'النشاط السابق {delayed_activity.activity_name} متأخر {delay_days} يوماً. هذا سيؤثر على بدء نشاطك {activity.activity_name}.',
            notification_type='predecessor_activity_delayed',
            priority='high',
            related_project_id=activity.project_id,
            related_link=url_for('primavera.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def predecessor_task_delayed(task, delayed_task, receiver_id):
        """إشعار بأن مهمة سابقة متأخرة تؤثر على المهمة الحالية"""
        delay_days = (datetime.now().date() - delayed_task.planning.planned_finish).days if delayed_task.planning and delayed_task.planning.planned_finish else 0
        
        notification = Notification(
            user_id=receiver_id,
            title=f'⚠️ تنبيه: تأخر في المهمة السابقة - {task.task_name}',
            title_ar=f'⚠️ تنبيه: تأخر في المهمة السابقة - {task.task_name}',
            message=f'المهمة السابقة {delayed_task.task_name} متأخرة {delay_days} يوماً. هذا سيؤثر على بدء مهمتك {task.task_name}.',
            message_ar=f'المهمة السابقة {delayed_task.task_name} متأخرة {delay_days} يوماً. هذا سيؤثر على بدء مهمتك {task.task_name}.',
            notification_type='predecessor_task_delayed',
            priority='high',
            related_project_id=task.project_id,
            related_task_id=task.id,
            related_link=url_for('company.view_task', task_id=task.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def critical_activity_delayed( activity, delay_days):
        """إشعار بتأخر نشاط حرج"""
        notification = Notification(
            user_id=activity.project.project_manager_id,
            title=f'🔴 تنبيه عاجل: تأخر نشاط حرج - {activity.activity_name}',
            title_ar=f'🔴 تنبيه عاجل: تأخر نشاط حرج - {activity.activity_name}',
            message=f'النشاط الحرج {activity.activity_name} متأخر {delay_days} يوماً. هذا سيؤثر على موعد انتهاء المشروع بالكامل!',
            message_ar=f'النشاط الحرج {activity.activity_name} متأخر {delay_days} يوماً. هذا سيؤثر على موعد انتهاء المشروع بالكامل!',
            notification_type='critical_activity_delayed',
            priority='critical',
            related_project_id=activity.project_id,
            related_link=url_for('primavera.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار للمشرف أيضاً
        if activity.supervisor_id and activity.supervisor_id != activity.project.project_manager_id:
            supervisor_notif = Notification(
                user_id=activity.supervisor_id,
                title=f'🔴 تنبيه عاجل: تأخر نشاط حرج تحت مسؤوليتك',
                title_ar=f'🔴 تنبيه عاجل: تأخر نشاط حرج تحت مسؤوليتك',
                message=f'النشاط الحرج {activity.activity_name} متأخر {delay_days} يوماً. مطلوب تدخل فوري!',
                message_ar=f'النشاط الحرج {activity.activity_name} متأخر {delay_days} يوماً. مطلوب تدخل فوري!',
                notification_type='critical_activity_delayed',
                priority='critical',
                related_project_id=activity.project_id,
                related_link=url_for('primavera.view_activity', activity_id=activity.id)
            )
            db.session.add(supervisor_notif)
        
        db.session.commit()
    
    @staticmethod
    def critical_activity_reminder(activity, days_remaining):
        """تذكير بانتهاء نشاط حرج"""
        notification = Notification(
            user_id=activity.project.project_manager_id,
            title=f'⏰ تذكير: نشاط حرج ينتهي قريباً - {activity.activity_name}',
            title_ar=f'⏰ تذكير: نشاط حرج ينتهي قريباً - {activity.activity_name}',
            message=f'النشاط الحرج {activity.activity_name} ينتهي بعد {days_remaining} أيام. يرجى المتابعة.',
            message_ar=f'النشاط الحرج {activity.activity_name} ينتهي بعد {days_remaining} أيام. يرجى المتابعة.',
            notification_type='critical_activity_reminder',
            priority='high',
            related_project_id=activity.project_id,
            related_link=url_for('primavera.view_activity', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار للمشرف
        if activity.supervisor_id:
            supervisor_notif = Notification(
                user_id=activity.supervisor_id,
                title=f'⏰ تذكير: نشاط حرج ينتهي قريباً',
                title_ar=f'⏰ تذكير: نشاط حرج ينتهي قريباً',
                message=f'النشاط الحرج {activity.activity_name} ينتهي بعد {days_remaining} أيام. يرجى المتابعة.',
                message_ar=f'النشاط الحرج {activity.activity_name} ينتهي بعد {days_remaining} أيام. يرجى المتابعة.',
                notification_type='critical_activity_reminder',
                priority='high',
                related_project_id=activity.project_id,
                related_link=url_for('primavera.view_activity', activity_id=activity.id)
            )
            db.session.add(supervisor_notif)
        
        db.session.commit()
    
    @staticmethod
    def dependency_chain_status(activity, chain):
        """إشعار بحالة سلسلة التبعيات"""
        notification = Notification(
            user_id=activity.project.project_manager_id,
            title=f'📊 حالة سلسلة التبعيات - {activity.activity_name}',
            title_ar=f'📊 حالة سلسلة التبعيات - {activity.activity_name}',
            message=f'هناك {len(chain)} أنشطة مرتبطة بهذا النشاط. راجع التفاصيل لمتابعة سير العمل.',
            message_ar=f'هناك {len(chain)} أنشطة مرتبطة بهذا النشاط. راجع التفاصيل لمتابعة سير العمل.',
            notification_type='dependency_chain_status',
            priority='medium',
            related_project_id=activity.project_id,
            related_link=url_for('primavera.view_activity_dependencies', activity_id=activity.id),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    # ============================================
    # إشعارات المشاريع
    # ============================================
    @staticmethod
    def project_ready_to_start( project):
        """إشعار بأن المشروع جاهز للبدء"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'🚀 المشروع جاهز للبدء: {project.name}',
            title_ar=f'🚀 المشروع جاهز للبدء: {project.name}',
            message=f'جميع المتطلبات جاهزة. يمكنك بدء مشروع {project.name} الآن.',
            message_ar=f'جميع المتطلبات جاهزة. يمكنك بدء مشروع {project.name} الآن.',
            notification_type='project_ready_to_start',
            priority='high',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لإدارة الشركة
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            admin_notif = Notification(
                user_id=admin.id,
                title=f'📢 مشروع جاهز للبدء: {project.name}',
                title_ar=f'📢 مشروع جاهز للبدء: {project.name}',
                message=f'مشروع {project.name} جاهز للبدء. يرجى متابعة التنفيذ.',
                message_ar=f'مشروع {project.name} جاهز للبدء. يرجى متابعة التنفيذ.',
                notification_type='project_ready_alert',
                priority='medium',
                related_project_id=project.id
            )
            db.session.add(admin_notif)
        
        db.session.commit()
    
    @staticmethod
    def project_overdue(project, delay_days):
        """إشعار بتأخر المشروع"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'⚠️ المشروع متأخر: {project.name}',
            title_ar=f'⚠️ المشروع متأخر: {project.name}',
            message=f'المشروع متأخر {delay_days} يوماً عن الجدول المخطط. مطلوب اتخاذ إجراءات تصحيحية.',
            message_ar=f'المشروع متأخر {delay_days} يوماً عن الجدول المخطط. مطلوب اتخاذ إجراءات تصحيحية.',
            notification_type='project_overdue',
            priority='critical' if delay_days > 10 else 'high',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()

    @staticmethod
    def project_overdue_alert( project, delay_days):
        """إشعار لإدارة الشركة بتأخر المشروع"""
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            notification = Notification(
                user_id=admin.id,
                title=f'🔴 تنبيه: مشروع متأخر - {project.name}',
                title_ar=f'🔴 تنبيه: مشروع متأخر - {project.name}',
                message=f'مشروع {project.name} متأخر {delay_days} يوماً. مطلوب متابعة فورية.',
                message_ar=f'مشروع {project.name} متأخر {delay_days} يوماً. مطلوب متابعة فورية.',
                notification_type='project_overdue_alert',
                priority='critical',
                related_project_id=project.id,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def budget_alert(project, budget_status):
        """إشعار بتجاوز الميزانية"""
        percent_spent = budget_status.get('percent_spent', 0)
        
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'💰 تنبيه الميزانية: {project.name}',
            title_ar=f'💰 تنبيه الميزانية: {project.name}',
            message=f'تم استخدام {percent_spent:.1f}% من ميزانية المشروع. يرجى مراقبة المصروفات.',
            message_ar=f'تم استخدام {percent_spent:.1f}% من ميزانية المشروع. يرجى مراقبة المصروفات.',
            notification_type='budget_alert',
            priority='high' if percent_spent > 90 else 'medium',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def cost_critical_overrun(project, overrun_percentage, overrun_amount):
        """إشعار بتجاوز خطير للميزانية"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'🔴 تجاوز خطير في الميزانية: {project.name}',
            title_ar=f'🔴 تجاوز خطير في الميزانية: {project.name}',
            message=f'تم تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال). مطلوب تدخل فوري!',
            message_ar=f'تم تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال). مطلوب تدخل فوري!',
            notification_type='cost_critical_overrun',
            priority='critical',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لإدارة الشركة
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            admin_notif = Notification(
                user_id=admin.id,
                title=f'🔴 تنبيه عاجل: تجاوز ميزانية مشروع {project.name}',
                title_ar=f'🔴 تنبيه عاجل: تجاوز ميزانية مشروع {project.name}',
                message=f'تجاوز الميزانية بنسبة {overrun_percentage:.1f}% ({overrun_amount:,.2f} ريال)',
                message_ar=f'تجاوز الميزانية بنسبة {overrun_percentage:.1f}% ({overrun_amount:,.2f} ريال)',
                notification_type='cost_critical_alert',
                priority='critical',
                related_project_id=project.id
            )
            db.session.add(admin_notif)
        
        db.session.commit()
    
    @staticmethod
    def cost_significant_overrun( project, overrun_percentage, overrun_amount):
        """إشعار بتجاوز كبير للميزانية"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'⚠️ تجاوز كبير في الميزانية: {project.name}',
            title_ar=f'⚠️ تجاوز كبير في الميزانية: {project.name}',
            message=f'تم تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال). يرجى المراجعة.',
            message_ar=f'تم تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال). يرجى المراجعة.',
            notification_type='cost_significant_overrun',
            priority='high',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def cost_minor_overrun( project, overrun_percentage, overrun_amount):
        """إشعار بتجاوز بسيط للميزانية"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'📊 تنبيه: تجاوز بسيط في الميزانية - {project.name}',
            title_ar=f'📊 تنبيه: تجاوز بسيط في الميزانية - {project.name}',
            message=f'تم تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال).',
            message_ar=f'تم تجاوز الميزانية بنسبة {overrun_percentage:.1f}% (مبلغ {overrun_amount:,.2f} ريال).',
            notification_type='cost_minor_overrun',
            priority='medium',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def cost_performance_alert( project, cpi):
        """إشعار بأداء التكلفة"""
        status = 'ضعيف' if cpi < 0.8 else 'متوسط'
        
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'📉 أداء التكلفة: {project.name}',
            title_ar=f'📉 أداء التكلفة: {project.name}',
            message=f'مؤشر أداء التكلفة (CPI) = {cpi:.2f} ({status}). يوصى بمراجعة المصروفات.',
            message_ar=f'مؤشر أداء التكلفة (CPI) = {cpi:.2f} ({status}). يوصى بمراجعة المصروفات.',
            notification_type='cost_performance_alert',
            priority='high' if cpi < 0.8 else 'medium',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def schedule_performance_alert(project, spi):
        """إشعار بأداء الجدول"""
        status = 'ضعيف' if spi < 0.8 else 'متوسط'
        
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'📅 أداء الجدول: {project.name}',
            title_ar=f'📅 أداء الجدول: {project.name}',
            message=f'مؤشر أداء الجدول (SPI) = {spi:.2f} ({status}). يوصى بمراجعة الجدول الزمني.',
            message_ar=f'مؤشر أداء الجدول (SPI) = {spi:.2f} ({status}). يوصى بمراجعة الجدول الزمني.',
            notification_type='schedule_performance_alert',
            priority='high' if spi < 0.8 else 'medium',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    # ============================================
    # إشعارات الأنشطة
    # ============================================
    @staticmethod
    def activity_missing_resources( activity, missing_resources):
        """إشعار بنقص الموارد للنشاط"""
        resources_text = ', '.join([r['resource_name'] for r in missing_resources])
        
        notification = Notification(
            user_id=activity.supervisor_id,
            title=f'⚠️ نقص موارد للنشاط: {activity.activity_name}',
            title_ar=f'⚠️ نقص موارد للنشاط: {activity.activity_name}',
            message=f'يوجد نقص في الموارد: {resources_text}. يرجى توفير الموارد المطلوبة.',
            message_ar=f'يوجد نقص في الموارد: {resources_text}. يرجى توفير الموارد المطلوبة.',
            notification_type='activity_missing_resources',
            priority='high',
            related_project_id=activity.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لمدير المشروع
        if activity.project.project_manager_id:
            pm_notif = Notification(
                user_id=activity.project.project_manager_id,
                title=f'⚠️ نقص موارد: {activity.activity_name}',
                title_ar=f'⚠️ نقص موارد: {activity.activity_name}',
                message=f'النشاط {activity.activity_name} يحتاج إلى {resources_text}',
                message_ar=f'النشاط {activity.activity_name} يحتاج إلى {resources_text}',
                notification_type='activity_resources_alert',
                priority='high',
                related_project_id=activity.project_id
            )
            db.session.add(pm_notif)
        
        db.session.commit()

    @staticmethod
    def activity_overdue(activity, delay_days):
        """إشعار بتأخر النشاط"""
        notification = Notification(
            user_id=activity.supervisor_id,
            title=f'⚠️ نشاط متأخر: {activity.activity_name}',
            title_ar=f'⚠️ نشاط متأخر: {activity.activity_name}',
            message=f'النشاط متأخر {delay_days} يوماً عن الجدول المخطط.',
            message_ar=f'النشاط متأخر {delay_days} يوماً عن الجدول المخطط.',
            notification_type='activity_overdue',
            priority='high',
            related_project_id=activity.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لمدير المشروع
        if activity.project.project_manager_id:
            pm_notif = Notification(
                user_id=activity.project.project_manager_id,
                title=f'⚠️ نشاط متأخر: {activity.activity_name}',
                title_ar=f'⚠️ نشاط متأخر: {activity.activity_name}',
                message=f'النشاط {activity.activity_name} متأخر {delay_days} يوماً',
                message_ar=f'النشاط {activity.activity_name} متأخر {delay_days} يوماً',
                notification_type='activity_overdue_alert',
                priority='high',
                related_project_id=activity.project_id
            )
            db.session.add(pm_notif)
        
        db.session.commit()
    
    # ============================================
    # إشعارات المهام
    # ============================================
    @staticmethod
    def task_missing_requirements(task, pending_reqs):
        """إشعار بالمتطلبات غير المكتملة للمهمة"""
        reqs_text = ', '.join([r.description for r in pending_reqs])
        
        notification = Notification(
            user_id=task.delegate_id,
            title=f'⚠️ متطلبات غير مكتملة: {task.task_name}',
            title_ar=f'⚠️ متطلبات غير مكتملة: {task.task_name}',
            message=f'المتطلبات التالية غير مكتملة: {reqs_text}. يرجى إكمالها لبدء المهمة.',
            message_ar=f'المتطلبات التالية غير مكتملة: {reqs_text}. يرجى إكمالها لبدء المهمة.',
            notification_type='task_missing_requirements',
            priority='high',
            related_project_id=task.project_id,
            related_task_id=task.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار للمشرف
        if task.supervisor_id:
            sup_notif = Notification(
                user_id=task.supervisor_id,
                title=f'⚠️ متطلبات غير مكتملة: {task.task_name}',
                title_ar=f'⚠️ متطلبات غير مكتملة: {task.task_name}',
                message=f'المهمة {task.task_name} تحتاج إلى إكمال: {reqs_text}',
                message_ar=f'المهمة {task.task_name} تحتاج إلى إكمال: {reqs_text}',
                notification_type='task_requirements_alert',
                priority='medium',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(sup_notif)
        
        db.session.commit()

    @staticmethod
    def task_deadline_reminder(task, days_remaining):
        """تذكير بموعد تسليم المهمة"""
        notification = Notification(
            user_id=task.delegate_id,
            title=f'⏰ تذكير: {task.task_name}',
            title_ar=f'⏰ تذكير: {task.task_name}',
            message=f'متبقي {days_remaining} أيام على موعد تسليم المهمة. نسبة الإنجاز الحالية: {task.progress_percentage}%',
            message_ar=f'متبقي {days_remaining} أيام على موعد تسليم المهمة. نسبة الإنجاز الحالية: {task.progress_percentage}%',
            notification_type='task_deadline_reminder',
            priority='high' if days_remaining <= 1 else 'medium',
            related_project_id=task.project_id,
            related_task_id=task.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # تذكير للمشرف أيضاً
        if task.supervisor_id:
            sup_notif = Notification(
                user_id=task.supervisor_id,
                title=f'⏰ تذكير بمهمة: {task.task_name}',
                title_ar=f'⏰ تذكير بمهمة: {task.task_name}',
                message=f'مهمة {task.task_name} تنتهي بعد {days_remaining} أيام',
                message_ar=f'مهمة {task.task_name} تنتهي بعد {days_remaining} أيام',
                notification_type='task_deadline_supervisor',
                priority='medium',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(sup_notif)
        
        db.session.commit()
    
    @staticmethod
    def task_ready_for_review(task):
        """إشعار بأن المهمة جاهزة للمراجعة"""
        notification = Notification(
            user_id=task.supervisor_id,
            title=f'✅ مهمة جاهزة للمراجعة: {task.task_name}',
            title_ar=f'✅ مهمة جاهزة للمراجعة: {task.task_name}',
            message=f'المهمة {task.task_name} مكتملة بنسبة 100%. يرجى مراجعة جودة العمل.',
            message_ar=f'المهمة {task.task_name} مكتملة بنسبة 100%. يرجى مراجعة جودة العمل.',
            notification_type='task_ready_for_review',
            priority='high',
            related_project_id=task.project_id,
            related_task_id=task.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لمدير المشروع
        if task.project.project_manager_id:
            pm_notif = Notification(
                user_id=task.project.project_manager_id,
                title=f'✅ مهمة مكتملة: {task.task_name}',
                title_ar=f'✅ مهمة مكتملة: {task.task_name}',
                message=f'المهمة {task.task_name} مكتملة في انتظار المراجعة',
                message_ar=f'المهمة {task.task_name} مكتملة في انتظار المراجعة',
                notification_type='task_completed_review',
                priority='medium',
                related_project_id=task.project_id,
                related_task_id=task.id
            )
            db.session.add(pm_notif)
        
        db.session.commit()
    
    @staticmethod
    def task_overdue_supervisor(task, delay_days):
        """إشعار للمشرف بتأخر المهمة"""
        notification = Notification(
            user_id=task.supervisor_id,
            title=f'⚠️ مهمة متأخرة: {task.task_name}',
            title_ar=f'⚠️ مهمة متأخرة: {task.task_name}',
            message=f'المهمة {task.task_name} تحت مسؤولية {task.delegate.full_name} متأخرة {delay_days} يوماً.',
            message_ar=f'المهمة {task.task_name} تحت مسؤولية {task.delegate.full_name} متأخرة {delay_days} يوماً.',
            notification_type='task_overdue_supervisor',
            priority='high',
            related_project_id=task.project_id,
            related_task_id=task.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    # ============================================
    # إشعارات المعدات
    # ============================================
    @staticmethod
    def equipment_maintenance_reminder( equipment):
        """تذكير بصيانة المعدات"""
        notification = Notification(
            user_id=equipment.supplier_id,
            title=f'🔧 تذكير صيانة: {equipment.name}',
            title_ar=f'🔧 تذكير صيانة: {equipment.name}',
            message=f'حان موعد الصيانة الدورية للمعدة {equipment.name}. التاريخ المطلوب: {equipment.next_maintenance}',
            message_ar=f'حان موعد الصيانة الدورية للمعدة {equipment.name}. التاريخ المطلوب: {equipment.next_maintenance}',
            notification_type='equipment_maintenance',
            priority='high',
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        
        # إشعار لمدير المشروع إذا كانت المعدة مستخدمة في مشروع
        if equipment.assigned_projects:
            for project in equipment.assigned_projects:
                if project.project_manager_id:
                    pm_notif = Notification(
                        user_id=project.project_manager_id,
                        title=f'🔧 صيانة معدات: {equipment.name}',
                        title_ar=f'🔧 صيانة معدات: {equipment.name}',
                        message=f'المعدة {equipment.name} تحتاج صيانة في تاريخ {equipment.next_maintenance}',
                        message_ar=f'المعدة {equipment.name} تحتاج صيانة في تاريخ {equipment.next_maintenance}',
                        notification_type='equipment_maintenance_project',
                        priority='medium',
                        related_project_id=project.id
                    )
                    db.session.add(pm_notif)
        
        db.session.commit()
    
    # ============================================
    # إشعارات التقارير
    # ============================================
    def daily_report_ready(self, project, report):
        """إشعار بأن التقرير اليومي جاهز"""
        # إنشاء رابط التقرير
        report_url = url_for('reports.view_report', report_id=report.id, _external=True)
        
        # إشعار لمدير المشروع
        if project.project_manager_id:
            notification_pm = Notification(
                user_id=project.project_manager_id,
                title=f'📊 تقرير يومي جاهز - {project.name}',
                title_ar=f'📊 تقرير يومي جاهز - {project.name}',
                message=f'تم إنشاء التقرير اليومي للمشروع {project.name}. يمكنك الاطلاع على تفاصيل الأداء والإنجازات.',
                message_ar=f'تم إنشاء التقرير اليومي للمشروع {project.name}. يمكنك الاطلاع على تفاصيل الأداء والإنجازات.',
                notification_type='daily_report_ready',
                priority='medium',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_pm)
        
        # إشعار للمشرفين على المشروع
        supervisors = set()
        for task in project.tasks:
            if task.supervisor_id:
                supervisors.add(task.supervisor_id)
        
        for supervisor_id in supervisors:
            if supervisor_id != project.project_manager_id:
                notification_sup = Notification(
                    user_id=supervisor_id,
                    title=f'📊 تقرير يومي - {project.name}',
                    title_ar=f'📊 تقرير يومي - {project.name}',
                    message=f'تم إنشاء التقرير اليومي للمشروع. يمكنك متابعة تقدم المهام تحت مسؤوليتك.',
                    message_ar=f'تم إنشاء التقرير اليومي للمشروع. يمكنك متابعة تقدم المهام تحت مسؤوليتك.',
                    notification_type='daily_report_ready',
                    priority='low',
                    related_project_id=project.id,
                    related_link=report_url,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification_sup)
        
        # إشعار للمالك (العميل) إذا كان التقرير يتضمن معلومات مهمة
        if project.client_id:
            # التحقق من وجود معلومات مهمة في التقرير
            has_critical_info = self.check_critical_info_in_report(report)
            
            if has_critical_info:
                notification_client = Notification(
                    user_id=project.client_id,
                    title=f'📊 تحديث يومي - {project.name}',
                    title_ar=f'📊 تحديث يومي - {project.name}',
                    message=f'تم تحديث معلومات المشروع. يمكنك متابعة آخر التطورات.',
                    message_ar=f'تم تحديث معلومات المشروع. يمكنك متابعة آخر التطورات.',
                    notification_type='daily_report_client',
                    priority='medium',
                    related_project_id=project.id,
                    related_link=report_url,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification_client)
        
        # إشعار لإدارة الشركة (ملخص يومي)
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            notification_admin = Notification(
                user_id=admin.id,
                title=f'📊 ملخص يومي - {project.name}',
                title_ar=f'📊 ملخص يومي - {project.name}',
                message=f'تقرير يومي للمشروع {project.name}: {report.report_summary}',
                message_ar=f'تقرير يومي للمشروع {project.name}: {report.report_summary}',
                notification_type='daily_summary',
                priority='low',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_admin)
        
        db.session.commit()
        logger.info(f"تم إرسال إشعارات التقرير اليومي للمشروع {project.name}")
    
    def weekly_report_ready(self, project, report):
        """إشعار بأن التقرير الأسبوعي جاهز"""
        report_url = url_for('reports.view_report', report_id=report.id, _external=True)
        
        # استخراج المؤشرات الرئيسية من التقرير
        performance_summary = self.extract_performance_summary(report)
        
        # إشعار لمدير المشروع (بأولوية عالية)
        if project.project_manager_id:
            notification_pm = Notification(
                user_id=project.project_manager_id,
                title=f'📈 تقرير أسبوعي جاهز - {project.name}',
                title_ar=f'📈 تقرير أسبوعي جاهز - {project.name}',
                message=f'التقرير الأسبوعي للمشروع {project.name} جاهز.\n{performance_summary}',
                message_ar=f'التقرير الأسبوعي للمشروع {project.name} جاهز.\n{performance_summary}',
                notification_type='weekly_report_ready',
                priority='high',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_pm)
        
        # إشعار للمشرفين الرئيسيين
        supervisors = set()
        for task in project.tasks:
            if task.supervisor_id:
                supervisors.add(task.supervisor_id)
        
        for supervisor_id in supervisors:
            notification_sup = Notification(
                user_id=supervisor_id,
                title=f'📈 تقرير أسبوعي - {project.name}',
                title_ar=f'📈 تقرير أسبوعي - {project.name}',
                message=f'تم إنشاء التقرير الأسبوعي للمشروع. يرجى مراجعة أداء المهام تحت مسؤوليتك.',
                message_ar=f'تم إنشاء التقرير الأسبوعي للمشروع. يرجى مراجعة أداء المهام تحت مسؤوليتك.',
                notification_type='weekly_report_ready',
                priority='medium',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_sup)
        
        # إشعار للمالك (العميل) مع ملخص الأداء
        if project.client_id:
            notification_client = Notification(
                user_id=project.client_id,
                title=f'📈 تقرير أسبوعي - تقدم مشروع {project.name}',
                title_ar=f'📈 تقرير أسبوعي - تقدم مشروع {project.name}',
                message=f'تقرير الأداء الأسبوعي للمشروع:\n{performance_summary}',
                message_ar=f'تقرير الأداء الأسبوعي للمشروع:\n{performance_summary}',
                notification_type='weekly_report_client',
                priority='high',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_client)
        
        # إشعار لإدارة الشركة مع توصيات
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        recommendations = self.extract_recommendations(report)
        
        for admin in admins:
            notification_admin = Notification(
                user_id=admin.id,
                title=f'📈 تقرير أسبوعي - {project.name}',
                title_ar=f'📈 تقرير أسبوعي - {project.name}',
                message=f'التقرير الأسبوعي للمشروع {project.name}\n{performance_summary}\n\nالتوصيات:\n{recommendations}',
                message_ar=f'التقرير الأسبوعي للمشروع {project.name}\n{performance_summary}\n\nالتوصيات:\n{recommendations}',
                notification_type='weekly_summary',
                priority='high',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_admin)
        
        # إشعار خاص إذا كان هناك تجاوزات في الميزانية أو التأخير
        if self.has_budget_overrun(report) or self.has_schedule_delay(report):
            self.send_alert_notifications(project, report)
        
        db.session.commit()
        logger.info(f"تم إرسال إشعارات التقرير الأسبوعي للمشروع {project.name}")
    
    def cost_report_ready(self, project, report):
        """إشعار بأن تقرير التكاليف جاهز"""
        report_url = url_for('reports.view_report', report_id=report.id, _external=True)
        
        # استخراج معلومات التكاليف من التقرير
        cost_summary = self.extract_cost_summary(report)
        cost_status = self.get_cost_status(report)
        
        # إشعار لمدير المشروع (بأولوية عالية جداً)
        if project.project_manager_id:
            notification_pm = Notification(
                user_id=project.project_manager_id,
                title=f'💰 تقرير التكاليف جاهز - {project.name}',
                title_ar=f'💰 تقرير التكاليف جاهز - {project.name}',
                message=f'تقرير التكاليف للمشروع {project.name} جاهز.\n{cost_summary}\n\nالحالة: {cost_status["text"]}',
                message_ar=f'تقرير التكاليف للمشروع {project.name} جاهز.\n{cost_summary}\n\nالحالة: {cost_status["text"]}',
                notification_type='cost_report_ready',
                priority='critical' if cost_status['is_critical'] else 'high',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_pm)
        
        # إشعار للفريق المالي
        finance_team = User.query.filter_by(org_id=project.org_id, role='finance').all()
        for finance_user in finance_team:
            notification_finance = Notification(
                user_id=finance_user.id,
                title=f'💰 تقرير التكاليف - {project.name}',
                title_ar=f'💰 تقرير التكاليف - {project.name}',
                message=f'تقرير التكاليف للمشروع {project.name}\n{cost_summary}',
                message_ar=f'تقرير التكاليف للمشروع {project.name}\n{cost_summary}',
                notification_type='cost_report_finance',
                priority='high',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_finance)
        
        # إشعار للمالك إذا كان هناك تجاوزات كبيرة
        if cost_status['is_critical'] and project.client_id:
            notification_client = Notification(
                user_id=project.client_id,
                title=f'⚠️ تنبيه: تقرير التكاليف - {project.name}',
                title_ar=f'⚠️ تنبيه: تقرير التكاليف - {project.name}',
                message=f'تم رصد تجاوزات في ميزانية المشروع. التفاصيل في التقرير المرفق.',
                message_ar=f'تم رصد تجاوزات في ميزانية المشروع. التفاصيل في التقرير المرفق.',
                notification_type='cost_alert_client',
                priority='critical',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_client)
        
        # إشعار لإدارة الشركة مع توصيات مالية
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        cost_recommendations = self.extract_cost_recommendations(report)
        
        for admin in admins:
            notification_admin = Notification(
                user_id=admin.id,
                title=f'💰 تقرير التكاليف - {project.name}',
                title_ar=f'💰 تقرير التكاليف - {project.name}',
                message=f'تقرير التكاليف للمشروع {project.name}\n{cost_summary}\n\nالتوصيات:\n{cost_recommendations}',
                message_ar=f'تقرير التكاليف للمشروع {project.name}\n{cost_summary}\n\nالتوصيات:\n{cost_recommendations}',
                notification_type='cost_summary',
                priority='high' if cost_status['is_critical'] else 'medium',
                related_project_id=project.id,
                related_link=report_url,
                send_email=True,
                send_push=True
            )
            db.session.add(notification_admin)
        
        db.session.commit()
        logger.info(f"تم إرسال إشعارات تقرير التكاليف للمشروع {project.name}")
    
    # ============================================
    # دوال مساعدة لاستخراج معلومات التقارير
    # ============================================

    def check_critical_info_in_report(self, report):
        """التحقق من وجود معلومات مهمة في التقرير"""
        if not report.report_data:
            return False
        
        # التحقق من وجود تجاوزات أو تأخيرات
        if report.report_data.get('variance', 0) > 0:
            return True
        
        if report.report_insights:
            for insight in report.report_insights:
                if 'تأخير' in insight or 'تجاوز' in insight:
                    return True
        
        return False

    def extract_performance_summary(self, report):
        """استخراج ملخص الأداء من التقرير"""
        if report.report_summary:
            return report.report_summary
        
        summary = []
        if report.report_insights:
            summary.extend(report.report_insights[:3])
        
        if report.recommendations:
            summary.append(f"التوصيات: {report.recommendations[0]}")
        
        return "\n".join(summary) if summary else "لا يوجد ملخص متاح"
    

    def extract_recommendations(self, report):
        """استخراج التوصيات من التقرير"""
        if report.recommendations:
            return "\n".join(report.recommendations[:5])
        return "لا توجد توصيات محددة"

    def extract_cost_summary(self, report):
        """استخراج ملخص التكاليف من التقرير"""
        if report.report_data:
            planned = report.report_data.get('planned_cost', 0)
            actual = report.report_data.get('actual_cost', 0)
            variance = report.report_data.get('variance', 0)
            variance_percent = report.report_data.get('variance_percentage', 0)
            
            status = "تجاوز" if variance > 0 else "توفير"
            return f"الميزانية المخططة: {planned:,.2f} ريال\nالتكلفة الفعلية: {actual:,.2f} ريال\n{status}: {abs(variance):,.2f} ريال ({abs(variance_percent):.1f}%)"
        
        return report.report_summary or "لا يوجد ملخص للتكاليف"
    
    def get_cost_status(self, report):
        """تحديد حالة التكاليف من التقرير"""
        if not report.report_data:
            return {'text': 'غير محدد', 'is_critical': False}
        
        variance_percent = report.report_data.get('variance_percentage', 0)
        
        if variance_percent >= 20:
            return {'text': 'تجاوز خطير', 'is_critical': True}
        elif variance_percent >= 10:
            return {'text': 'تجاوز كبير', 'is_critical': True}
        elif variance_percent >= 5:
            return {'text': 'تجاوز بسيط', 'is_critical': False}
        elif variance_percent <= -5:
            return {'text': 'توفير', 'is_critical': False}
        else:
            return {'text': 'ضمن الميزانية', 'is_critical': False}
    
    def extract_cost_recommendations(self, report):
        """استخراج توصيات التكاليف من التقرير"""
        if report.recommendations:
            cost_recs = [r for r in report.recommendations if 'تكلف' in r or 'ميزان' in r or 'مصروف' in r]
            return "\n".join(cost_recs[:3]) if cost_recs else "مراجعة المصروفات غير الضرورية"
        return "مراجعة المصروفات غير الضرورية"
    
    def has_budget_overrun(self, report):
        """التحقق من وجود تجاوز في الميزانية"""
        if not report.report_data:
            return False
        return report.report_data.get('variance', 0) > 0
    
    def has_schedule_delay(self, report):
        """التحقق من وجود تأخير في الجدول"""
        if not report.report_insights:
            return False
        
        for insight in report.report_insights:
            if 'تأخير' in insight or 'متأخر' in insight:
                return True
        return False
    
    def send_alert_notifications(self, project, report):
        """إرسال إشعارات تنبيه إضافية للمشاكل الخطيرة"""
        # إشعار للمشرفين المباشرين
        supervisors = set()
        for task in project.tasks:
            if task.supervisor_id:
                supervisors.add(task.supervisor_id)
        
        alert_message = "تم رصد مشاكل في المشروع تحتاج إلى تدخل فوري:\n"
        
        if self.has_budget_overrun(report):
            alert_message += f"- تجاوز في الميزانية بنسبة {report.report_data.get('variance_percentage', 0):.1f}%\n"
        
        if self.has_schedule_delay(report):
            alert_message += "- تأخير في الجدول الزمني\n"
        
        for supervisor_id in supervisors:
            alert = Notification(
                user_id=supervisor_id,
                title=f'⚠️ تنبيه عاجل: مشاكل في المشروع {project.name}',
                title_ar=f'⚠️ تنبيه عاجل: مشاكل في المشروع {project.name}',
                message=alert_message,
                message_ar=alert_message,
                notification_type='project_alert',
                priority='critical',
                related_project_id=project.id,
                send_email=True,
                send_push=True
            )
            db.session.add(alert)
        
        db.session.commit()

    
    def daily_executive_summary(self, admin, dashboard):
        """إرسال ملخص تنفيذي يومي للمدير"""
        notification = Notification(
            user_id=admin.id,
            title=f'📊 الملخص التنفيذي اليومي',
            title_ar=f'📊 الملخص التنفيذي اليومي',
            message=f'عدد المشاريع النشطة: {dashboard["kpis"]["overall"]["active_projects"]}\n'
                    f'نسبة الإنجاز المتوسطة: {dashboard["kpis"]["overall"]["average_progress"]:.1f}%\n'
                    f'توصيات: {len(dashboard["recommendations"])}',
            message_ar=f'عدد المشاريع النشطة: {dashboard["kpis"]["overall"]["active_projects"]}\n'
                    f'نسبة الإنجاز المتوسطة: {dashboard["kpis"]["overall"]["average_progress"]:.1f}%\n'
                    f'توصيات: {len(dashboard["recommendations"])}',
            notification_type='daily_executive_summary',
            priority='high',
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    def performance_suggestions(self, project, suggestions):
        """إرسال اقتراحات تحسين الأداء"""
        suggestion_text = "\n".join([f"- {s['title']}: {s['description']}" for s in suggestions])
        
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'⚡ اقتراحات تحسين الأداء - {project.name}',
            title_ar=f'⚡ اقتراحات تحسين الأداء - {project.name}',
            message=f'تم رصد فرص لتحسين الأداء:\n{suggestion_text}',
            message_ar=f'تم رصد فرص لتحسين الأداء:\n{suggestion_text}',
            notification_type='performance_suggestions',
            priority='high',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    def quality_improvement_needed(self, user, stats):
        """إشعار بتحسين الجودة المطلوب"""
        notification = Notification(
            user_id=user.id,
            title=f'📊 تحسين الجودة المطلوب',
            title_ar=f'📊 تحسين الجودة المطلوب',
            message=f'متوسط جودة عملك: {stats["avg_quality"]:.1f}/5. يرجى مراجعة معايير الجودة.',
            message_ar=f'متوسط جودة عملك: {stats["avg_quality"]:.1f}/5. يرجى مراجعة معايير الجودة.',
            notification_type='quality_improvement',
            priority='medium',
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    def quality_alert(self, project, metrics):
        """إشعار بإنذار الجودة"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'⚠️ إنذار الجودة - {project.name}',
            title_ar=f'⚠️ إنذار الجودة - {project.name}',
            message=f'نسبة العيوب: {metrics["defect_rate"]:.1f}%\nنسبة إعادة العمل: {metrics["rework_rate"]:.1f}%',
            message_ar=f'نسبة العيوب: {metrics["defect_rate"]:.1f}%\nنسبة إعادة العمل: {metrics["rework_rate"]:.1f}%',
            notification_type='quality_alert',
            priority='high',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    def quality_recommendation(self, project, recommendation):
        """إشعار بتوصية جودة"""
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'💡 توصية لتحسين الجودة - {project.name}',
            title_ar=f'💡 توصية لتحسين الجودة - {project.name}',
            message=f'{recommendation["title"]}: {recommendation["action"]}',
            message_ar=f'{recommendation["title"]}: {recommendation["action"]}',
            notification_type='quality_recommendation',
            priority=recommendation.get('priority', 'medium'),
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    def holiday_upcoming(self, project, holidays):
        """إشعار بقدوم عطلة"""
        holiday_dates = [h.strftime('%Y-%m-%d') for h in holidays]
        
        notification = Notification(
            user_id=project.project_manager_id,
            title=f'🎉 تنبيه: عطلات قادمة - {project.name}',
            title_ar=f'🎉 تنبيه: عطلات قادمة - {project.name}',
            message=f'هناك عطلات خلال الأسبوع القادم: {", ".join(holiday_dates)}',
            message_ar=f'هناك عطلات خلال الأسبوع القادم: {", ".join(holiday_dates)}',
            notification_type='holiday_upcoming',
            priority='medium',
            related_project_id=project.id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    
    def performance_alert(self, user, stats):
        """إشعار بإنذار الأداء"""
        notification = Notification(
            user_id=user.id,
            title=f'⚠️ إنذار الأداء',
            title_ar=f'⚠️ إنذار الأداء',
            message=f'كفاءتك {stats["efficiency"]:.1f}% أقل من المستوى المطلوب (50%). يرجى تحسين الأداء.',
            message_ar=f'كفاءتك {stats["efficiency"]:.1f}% أقل من المستوى المطلوب (50%). يرجى تحسين الأداء.',
            notification_type='performance_alert',
            priority='high',
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()

    # ============================================
    # إشعارات الاشتراكات الخاصة بالشركات
    # ============================================
    
    @staticmethod
    def subscription_approved_for_company(subscription):
        """
        إرسال إشعار للشركة بأن طلب الاشتراك قد تمت الموافقة عليه
        
        Args:
            subscription: كائن الاشتراك
        """
        from app.models.core_models import User
        from flask import url_for
        
        company = subscription.organization
        # جلب مدير الشركة (Org Admin)
        company_admin = User.query.filter_by(org_id=company.id, role='org_admin').first()
        
        if not company_admin:
            # إذا لم يوجد مدير شركة، حاول جلب أي مستخدم نشط
            company_admin = User.query.filter_by(org_id=company.id, is_user_active=True).first()
        
        if company_admin:
            # إنشاء الإشعار
            notification = Notification(
                user_id=company_admin.id,
                organ_id=company.id,
                title=f'✅ تم قبول طلب الاشتراك - {subscription.plan_name}',
                title_ar=f'✅ تم قبول طلب الاشتراك - {subscription.plan_name}',
                message=f'تمت الموافقة على طلب اشتراككم في باقة "{subscription.plan_name}". يمكنكم الآن الاستفادة من جميع ميزات الباقة.',
                message_ar=f'تمت الموافقة على طلب اشتراككم في باقة "{subscription.plan_name}". يمكنكم الآن الاستفادة من جميع ميزات الباقة.',
                notification_type='subscription_approved',
                priority='high',
                related_link=url_for('company.subscription_status', _external=True),
                related_project_id=None,
                related_task_id=None,
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
            
            # تسجيل في السجل
            logger.info(f"✅ تم إرسال إشعار قبول الاشتراك للشركة {company.name}")
            
            # يمكن إضافة إرسال بريد إلكتروني هنا
            # NotificationService._send_email_notification(company_admin.email, notification)
            
            return notification
        return None
    
    @staticmethod
    def subscription_rejected_for_company(subscription, reason):
        """
        إرسال إشعار للشركة بأن طلب الاشتراك قد تم رفضه
        
        Args:
            subscription: كائن الاشتراك
            reason: سبب الرفض
        """
        from app.models.core_models import User
        from flask import url_for
        
        company = subscription.organization
        company_admin = User.query.filter_by(org_id=company.id, role='org_admin').first()
        
        if not company_admin:
            company_admin = User.query.filter_by(org_id=company.id, is_user_active=True).first()
        
        if company_admin:
            notification = Notification(
                user_id=company_admin.id,
                organ_id=company.id,
                title=f'❌ تم رفض طلب الاشتراك - {subscription.plan_name}',
                title_ar=f'❌ تم رفض طلب الاشتراك - {subscription.plan_name}',
                message=f'عذراً، تم رفض طلب اشتراككم في باقة "{subscription.plan_name}". السبب: {reason}',
                message_ar=f'عذراً، تم رفض طلب اشتراككم في باقة "{subscription.plan_name}". السبب: {reason}',
                notification_type='subscription_rejected',
                priority='high',
                related_link=url_for('company.view_plans', _external=True),
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
            
            logger.info(f"✅ تم إرسال إشعار رفض الاشتراك للشركة {company.name}")
            return notification
        return None
    
    @staticmethod
    def subscription_activated_for_company(subscription):
        """
        إرسال إشعار للشركة بأن الاشتراك تم تفعيله
        
        Args:
            subscription: كائن الاشتراك
        """
        from app.models.core_models import User
        from flask import url_for
        
        company = subscription.organization
        company_admin = User.query.filter_by(org_id=company.id, role='org_admin').first()
        
        if not company_admin:
            company_admin = User.query.filter_by(org_id=company.id, is_user_active=True).first()
        
        if company_admin:
            notification = Notification(
                user_id=company_admin.id,
                organ_id=company.id,
                title=f'🎉 تم تفعيل اشتراكك - {subscription.plan_name}',
                title_ar=f'🎉 تم تفعيل اشتراكك - {subscription.plan_name}',
                message=f'تم تفعيل اشتراكك في باقة "{subscription.plan_name}" بنجاح. تاريخ الانتهاء: {subscription.end_date.strftime("%Y-%m-%d") if subscription.end_date else "غير محدد"}',
                message_ar=f'تم تفعيل اشتراكك في باقة "{subscription.plan_name}" بنجاح. تاريخ الانتهاء: {subscription.end_date.strftime("%Y-%m-%d") if subscription.end_date else "غير محدد"}',
                notification_type='subscription_activated',
                priority='high',
                related_link=url_for('company.dashboard', _external=True),
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
            
            logger.info(f"✅ تم إرسال إشعار تفعيل الاشتراك للشركة {company.name}")
            return notification
        return None
    
    @staticmethod
    def subscription_expiring_soon_for_company(subscription, days_left):
        """
        إرسال إشعار للشركة بأن الاشتراك على وشك الانتهاء
        
        Args:
            subscription: كائن الاشتراك
            days_left: عدد الأيام المتبقية
        """
        from app.models.core_models import User
        from flask import url_for
        
        company = subscription.organization
        company_admin = User.query.filter_by(org_id=company.id, role='org_admin').first()
        
        if not company_admin:
            company_admin = User.query.filter_by(org_id=company.id, is_user_active=True).first()
        
        if company_admin:
            notification = Notification(
                user_id=company_admin.id,
                organ_id=company.id,
                title=f'⚠️ اشتراكك على وشك الانتهاء - {subscription.plan_name}',
                title_ar=f'⚠️ اشتراكك على وشك الانتهاء - {subscription.plan_name}',
                message=f'ينتهي اشتراكك في باقة "{subscription.plan_name}" بعد {days_left} يوم. يرجى تجديد الاشتراك لضمان استمرارية الخدمة.',
                message_ar=f'ينتهي اشتراكك في باقة "{subscription.plan_name}" بعد {days_left} يوم. يرجى تجديد الاشتراك لضمان استمرارية الخدمة.',
                notification_type='subscription_expiring',
                priority='high',
                related_link=url_for('company.view_plans', _external=True),
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
            
            logger.info(f"✅ تم إرسال إشعار انتهاء الاشتراك للشركة {company.name}")
            return notification
        return None
    
    @staticmethod
    def payment_received_for_company(subscription):
        """
        إرسال إشعار للشركة بتأكيد استلام الدفع
        
        Args:
            subscription: كائن الاشتراك
        """
        from app.models.core_models import User
        from flask import url_for
        
        company = subscription.organization
        company_admin = User.query.filter_by(org_id=company.id, role='org_admin').first()
        
        if not company_admin:
            company_admin = User.query.filter_by(org_id=company.id, is_user_active=True).first()
        
        if company_admin:
            notification = Notification(
                user_id=company_admin.id,
                organ_id=company.id,
                title=f'💰 تم تأكيد استلام الدفع - {subscription.plan_name}',
                title_ar=f'💰 تم تأكيد استلام الدفع - {subscription.plan_name}',
                message=f'تم تأكيد استلام مبلغ {subscription.total_amount} {subscription.currency} للاشتراك في باقة "{subscription.plan_name}". جاري مراجعة طلبك.',
                message_ar=f'تم تأكيد استلام مبلغ {subscription.total_amount} {subscription.currency} للاشتراك في باقة "{subscription.plan_name}". جاري مراجعة طلبك.',
                notification_type='payment_received',
                priority='medium',
                related_link=url_for('company.subscription_status', _external=True),
                send_email=True,
                send_push=True
            )
            db.session.add(notification)
            db.session.commit()
            
            logger.info(f"✅ تم إرسال إشعار تأكيد الدفع للشركة {company.name}")
            return notification
        return None
    
    @staticmethod
    def trial_expiring_soon(user, company, days_left):
        """إشعار باقتراب انتهاء الفترة التجريبية"""
        notification = Notification(
            user_id=user.id,
            title=f'⚠️ الفترة التجريبية على وشك الانتهاء',
            message=f'تنتهي الفترة التجريبية لشركتك بعد {days_left} يوم. يرجى ترقية اشتراكك للاستمرار.',
            notification_type='trial_expiring',
            priority='high',
            related_link=url_for('company.view_plans', _external=True),
            send_email=True
        )
        db.session.add(notification)
        db.session.commit()
    
    @staticmethod
    def trial_expired(user, company):
        """إشعار بانتهاء الفترة التجريبية"""
        notification = Notification(
            user_id=user.id,
            title=f'❌ انتهت الفترة التجريبية',
            message=f'انتهت الفترة التجريبية لشركتك. يرجى الاشتراك في إحدى الباقات المدفوعة للاستمرار في استخدام المنصة.',
            notification_type='trial_expired',
            priority='critical',
            related_link=url_for('company.view_plans', _external=True),
            send_email=True
        )
        db.session.add(notification)
        db.session.commit()
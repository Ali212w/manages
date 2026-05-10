"""
notification_service.py - خدمة الإشعارات المركزية
"""
from app.models import db, Notification, User, Project, Task
from datetime import datetime
from flask import current_app,url_for
import logging

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
                    related_project_id=task.project_id,
                    created_at=datetime.utcnow()
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
        
        # إشعار للمدير العام (صاحب الشركة)
        admins = User.query.filter_by(org_id=task.project.org_id, role='org_admin').all()
        for admin in admins:
            if admin.id not in [task.supervisor_id, task.project.project_manager_id, completed_by]:
                notification_admin = Notification(
                    user_id=admin.id,
                    title=f'📊 تقدم مشروع: {task.project.name}',
                    message=f'اكتملت مهمة {task.task_code} - نسبة إنجاز المشروع: {task.project.progress_percentage}%',
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
                message=f'المهمة {task.task_code} للمندوب {task.delegate.full_name if task.delegate else "غير معين"} متأخرة {delay_days} أيام',
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
    
    # ============================================
    # إشعارات المشاريع
    # ============================================
    
    @staticmethod
    def project_created(project, created_by):
        """إشعار عند إنشاء مشروع جديد"""
        # إشعار لمدير  المشروع
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
        
        # إشعار للمدير العام
        admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
        for admin in admins:
            if admin.id not in [project.project_manager_id, created_by]:
                notification_admin = Notification(
                    user_id=admin.id,
                    title=f'📁 مشروع جديد: {project.name}',
                    message=f'تم إنشاء مشروع {project.project_code} بقيادة {project.manager.full_name if project.manager else "غير معين"}',
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
        
        db.session.commit()
    
    @staticmethod
    def project_completed(project):
        """إشعار عند اكتمال المشروع"""
        # إشعار لجميع أعضاء الفريق
        team_members = set()
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
        
        # إشخاص للمدير العام
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
                priority='medium'
            )
            db.session.add(notification)
        
        # إشعار ترحيبي للمستخدم الجديد
        welcome = Notification(
            user_id=user.id,
            title=f'🎉 مرحباً بك {user.full_name}',
            message=f'تم إنشاء حسابك بنجاح. يمكنك الآن بدء استخدام النظام.',
            notification_type='user_welcome',
            priority='low'
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
            priority='high'
        )
        db.session.add(notification)
        db.session.commit()
    
    # ============================================
    # إشعارات المخاطر والمشكلات
    # ============================================
    
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
                priority='critical' if risk.risk_level == 'high' else 'high',
                related_project_id=risk.project_id,
                related_risk_id=risk.id
            )
            db.session.add(notification)
        
        # إشعار للمشرفين
        supervisors = set()
        for task in risk.project.tasks:
            if task.supervisor_id:
                supervisors.add(task.supervisor_id)
        
        for sup_id in supervisors:
            if sup_id != risk.project.project_manager_id:
                notif = Notification(
                    user_id=sup_id,
                    title=f'⚠️ تنبيه خطر: {risk.title}',
                    message=f'خطر جديد في المشروع: {risk.description[:100]}',
                    notification_type='risk_alert',
                    priority='high',
                    related_project_id=risk.project_id,
                    related_risk_id=risk.id
                )
                db.session.add(notif)
        
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
                message=f'تم الإبلاغ عن مشكلة جديدة: {issue.description[:100]}',
                notification_type='issue_reported',
                priority='medium',
                related_project_id=issue.project_id,
                related_issue_id=issue.id
            )
            db.session.add(notif_pm)
        
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
                title=f'📄 مستند جديد: {document.title}',
                message=f'تم رفع مستند {document.original_filename} في مشروع {document.project.name}',
                notification_type='document_uploaded',
                priority='low',
                related_project_id=document.project_id
            )
            db.session.add(notification)
        
        # إشعار للمشرفين
        supervisors = set()
        for task in document.project.tasks:
            if task.supervisor_id:
                supervisors.add(task.supervisor_id)
        
        for sup_id in supervisors:
            if sup_id != document.project.project_manager_id:
                notif = Notification(
                    user_id=sup_id,
                    title=f'📂 مستند جديد',
                    message=f'تم رفع مستند {document.title} في مشروع {document.project.name}',
                    notification_type='document_uploaded',
                    priority='low',
                    related_project_id=document.project_id
                )
                db.session.add(notif)
        
        db.session.commit()
    
    @staticmethod
    def document_approved(document, approved_by):
        """إشعار عند الموافقة على مستند"""
        if document.uploaded_by:
            notification = Notification(
                user_id=document.uploaded_by,
                title=f'✅ الموافقة على المستند: {document.title}',
                message=f'تمت الموافقة على مستندك {document.original_filename} بواسطة {approved_by.full_name}',
                notification_type='document_approved',
                priority='medium',
                related_project_id=document.project_id
            )
            db.session.add(notification)
            db.session.commit()
    
    # ============================================
    # إشعارات الدردشة والتعليقات
    # ============================================
    
    @staticmethod
    def new_message(chat, message, sender, mentioned_users=None):
        """إشعار برسالة جديدة في الدردشة"""
        # إشعار لجميع المشاركين في المحادثة
        from app.models import ChatParticipant
        
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
    def new_comment(comment,task_id):
        """إشعار بتعليق جديد"""
        # إشعار لصاحب المهمة
        if comment.task_id:
            task = Task.query.get(comment.task_id)
            if task.delegate_id and task.delegate_id != comment.user_id:
                notification = Notification(
                    user_id=task.delegate_id,
                    title=f'💭 تعليق جديد على مهمتك',
                    message=f'{comment.user.full_name} علق على مهمة {task.task_name}: {comment.content[:100]}',
                    notification_type='new_comment',
                    priority='low',
                    related_project_id=task.project_id,
                    related_task_id=task.id,
                    related_link=url_for('communication.task_comments', task_id=task_id)
                )
                db.session.add(notification)
            
            # إشعار للمشرف
            if task.supervisor_id and task.supervisor_id not in [comment.user_id, task.delegate_id]:
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
    # إشعارات النظام
    # ============================================
    
    @staticmethod
    def assign_responsible_id(user_id,message, title='🔔 تنبيه النظام', priority='medium'):
        """إشعار عام للنظام"""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type='system_alert',
            priority=priority
        )
        db.session.add(notification)
        db.session.commit()

    @staticmethod
    def system_alert(message, title='🔔 تنبيه النظام', priority='medium'):
        """إشعار عام للنظام"""
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
    def eps_manager(user_id,message, title='🔔 تنبيه النظام', priority='medium'):
        """إشعار عام للنظام"""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type='eps_assigned_info',
            priority=priority
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
    def verification_submitted(task, requirement_id, user_id):
        """إشعار عند تقديم طلب تحقق"""
        from app.models import TaskRequirement
        
        req = TaskRequirement.query.get(requirement_id)
        
        notification = Notification(
            user_id=task.supervisor_id,
            title=f'📋 طلب تحقق جديد: {task.task_name}',
            message=f'تم تقديم طلب تحقق للمتطلب: {req.description}',
            notification_type='verification_submitted',
            priority='medium',
            related_task_id=task.id,
            related_project_id=task.project_id
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
        
    @staticmethod
    def send_confirmation_notifications(delivery, resource_request, confirmed, notes):
        """إرسال إشعارات بعد تأكيد أو رفض التسليم"""
        
        # 1. إشعار للمورد
        confirm_url = url_for('supplier.view_request', request_id=resource_request.id, _external=True)
        
        if confirmed:
            title = f"تم تأكيد استلام المواد - {resource_request.project.name}"
            message = f"تم تأكيد استلام المواد للطلب #{resource_request.id}. شكراً لك."
            notification_type = 'delivery_confirmed'
            priority = 'medium'
        else:
            title = f"رفض استلام المواد - {resource_request.project.name}"
            message = f"تم رفض استلام المواد للطلب #{resource_request.id}. السبب: {notes}"
            notification_type = 'delivery_rejected'
            priority = 'high'
        
        notification_supplier = Notification(
            user_id=resource_request.supplier_id,
            title=title,
            title_ar=title,
            message=message,
            message_ar=message,
            notification_type=notification_type,
            priority=priority,
            related_link=confirm_url,
            related_project_id=resource_request.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification_supplier)
        
        # 2. إشعار للمالك بتأكيد الاستلام (إذا كان هناك ملاحظات)
        if confirmed and notes:
            if resource_request.project and resource_request.project.client_id:
            
                notification_owner = Notification(
                    user_id=resource_request.project.client_id,
                    title=f"ملاحظات على التسليم - {resource_request.project.name}",
                    title_ar=f"ملاحظات على التسليم - {resource_request.project.name}",
                    message=f"مدير المشروع أضاف ملاحظات على التسليم: {notes}",
                    message_ar=f"مدير المشروع أضاف ملاحظات على التسليم: {notes}",
                    notification_type='delivery_notes',
                    priority='low',
                    related_link=url_for('projects.project_resource_requests', project_id=resource_request.project_id, _external=True),
                    related_project_id=resource_request.project_id,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification_owner)
        
        # 3. إشعار لإدارة الشركة (إذا كان هناك رفض أو ملاحظات مهمة)
        if not confirmed or (confirmed and notes and notes.strip()):
            # إرسال إشعار للمديرين
            from app.models.core_models import User
            admins = User.query.filter_by(role='org_admin', org_id=resource_request.org_id).all()
            
            for admin in admins:
                notification_admin = Notification(
                    user_id=admin.id,
                    title=f"تنبيه: {'رفض' if not confirmed else 'ملاحظات'} تسليم - {resource_request.project.name}",
                    title_ar=f"تنبيه: {'رفض' if not confirmed else 'ملاحظات'} تسليم - {resource_request.project.name}",
                    message=f"الطلب #{resource_request.id} - المورد {resource_request.supplier.full_name}\nالسبب: {notes}",
                    message_ar=f"الطلب #{resource_request.id} - المورد {resource_request.supplier.full_name}\nالسبب: {notes}",
                    notification_type='delivery_alert',
                    priority='high' if not confirmed else 'medium',
                    related_link=url_for('projects.project_resource_requests', project_id=resource_request.project_id, _external=True),
                    related_project_id=resource_request.project_id,
                    send_email=True,
                    send_push=True
                )
                db.session.add(notification_admin)
        
        db.session.commit()
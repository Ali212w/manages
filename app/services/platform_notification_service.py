# في services/platform_notification_service.py - خدمة متخصصة لإشعارات المنصة

from app.models import db, PlatformNotification, PlatformAdmin, Organization, User, Subscription
from flask import url_for
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class PlatformNotificationService:
    """خدمة إدارة إشعارات المنصة"""
    
    @staticmethod
    def _create_notification(admin_id, title, message, notification_type, 
                             priority='medium', action_url=None, action_text=None,
                             icon=None, data=None, title_en=None, message_en=None,
                             action_text_en=None):
        """إنشاء إشعار جديد"""
        try:
            notification = PlatformNotification(
                admin_id=admin_id,
                title=title,
                title_en=title_en or title,
                message=message,
                message_en=message_en or message,
                notification_type=notification_type,
                priority=priority,
                action_url=action_url,
                action_text=action_text,
                action_text_en=action_text_en,
                icon=icon,
                data=data or {},
                is_read=False,
                is_sent=False
            )
            db.session.add(notification)
            db.session.commit()
            return notification
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في إنشاء الإشعار: {str(e)}")
            return None
    
    @staticmethod
    def _notify_all_admins(title, message, notification_type, priority='medium', 
                           action_url=None, action_text=None, data=None,
                           title_en=None, message_en=None, action_text_en=None,
                           exclude_admin_ids=None):
        """إرسال إشعار لجميع مدراء المنصة"""
        admins = PlatformAdmin.query.filter_by(is_active=True).all()
        exclude_ids = exclude_admin_ids or []
        
        notifications = []
        for admin in admins:
            if admin.id in exclude_ids:
                continue
            notif = PlatformNotificationService._create_notification(
                admin_id=admin.id,
                title=title,
                message=message,
                notification_type=notification_type,
                priority=priority,
                action_url=action_url,
                action_text=action_text,
                data=data,
                title_en=title_en,
                message_en=message_en,
                action_text_en=action_text_en
            )
            if notif:
                notifications.append(notif)
        
        return notifications
    
    # ============================================
    # أحداث الشركات (Company Events)
    # ============================================
    
    @staticmethod
    def new_company_registered(company):
        """إشعار بتسجيل شركة جديدة"""
        admins = PlatformAdmin.query.filter_by(is_active=True).all()
        
        for admin in admins:
            PlatformNotificationService._create_notification(
                admin_id=admin.id,
                title=f'🏢 شركة جديدة: {company.name}',
                title_en=f'🏢 New Company: {company.name}',
                message=f'تم تسجيل شركة جديدة "{company.name}" في المنصة. يرجى مراجعة بيانات الشركة والموافقة عليها.',
                message_en=f'A new company "{company.name}" has registered on the platform. Please review and verify.',
                notification_type='new_company_registration',
                priority='high',
                action_url=url_for('platform.view_company', company_id=company.id),
                action_text='مراجعة الشركة',
                action_text_en='Review Company',
                data={'company_id': company.id, 'company_name': company.name}
            )
    
    @staticmethod
    def company_verification_request(company):
        """إشعار بطلب توثيق شركة"""
        PlatformNotificationService._notify_all_admins(
            title=f'🔍 طلب توثيق: {company.name}',
            title_en=f'🔍 Verification Request: {company.name}',
            message=f'قامت شركة "{company.name}" بطلب توثيق حسابها. يرجى مراجعة المستندات المرفقة.',
            message_en=f'Company "{company.name}" has requested account verification. Please review attached documents.',
            notification_type='company_verification_request',
            priority='high',
            action_url=url_for('platform.view_company', company_id=company.id),
            action_text='مراجعة الطلب',
            action_text_en='Review Request',
            data={'company_id': company.id, 'company_name': company.name}
        )
    
    # ============================================
    # أحداث الاشتراكات (Subscription Events)
    # ============================================
    
    @staticmethod
    def new_subscription_request(subscription):
        """إشعار بطلب اشتراك جديد"""
        company = subscription.organization
        
        PlatformNotificationService._notify_all_admins(
            title=f'📋 طلب اشتراك جديد: {company.name}',
            title_en=f'📋 New Subscription Request: {company.name}',
            message=f'قامت شركة "{company.name}" بتقديم طلب اشتراك في باقة "{subscription.plan_name}". المبلغ: {subscription.total_amount} {subscription.currency}',
            message_en=f'Company "{company.name}" has submitted a subscription request for "{subscription.plan_name}" plan. Amount: {subscription.total_amount} {subscription.currency}',
            notification_type='subscription_request',
            priority='high',
            action_url=url_for('platform.subscription_requests'),
            action_text='مراجعة الطلب',
            action_text_en='Review Request',
            data={
                'subscription_id': subscription.id,
                'company_id': company.id,
                'company_name': company.name,
                'plan_name': subscription.plan_name,
                'amount': subscription.total_amount,
                'currency': subscription.currency
            }
        )
    
    @staticmethod
    def payment_proof_uploaded(subscription):
        """إشعار برفع إثبات دفع"""
        company = subscription.organization
        
        PlatformNotificationService._notify_all_admins(
            title=f'💰 إثبات دفع مرفوع: {company.name}',
            title_en=f'💰 Payment Proof Uploaded: {company.name}',
            message=f'قامت شركة "{company.name}" برفع إثبات دفع للاشتراك في باقة "{subscription.plan_name}". المبلغ: {subscription.total_amount} {subscription.currency}',
            message_en=f'Company "{company.name}" has uploaded payment proof for "{subscription.plan_name}" subscription. Amount: {subscription.total_amount} {subscription.currency}',
            notification_type='payment_proof_uploaded',
            priority='high',
            action_url=url_for('platform.subscription_requests'),
            action_text='مراجعة الإثبات',
            action_text_en='Review Proof',
            data={
                'subscription_id': subscription.id,
                'company_id': company.id,
                'company_name': company.name,
                'proof_url': subscription.payment_proof
            }
        )
    
    @staticmethod
    def subscription_expiring_soon(subscription, days_left):
        """إشعار باشتراك على وشك الانتهاء"""
        company = subscription.organization
        
        PlatformNotificationService._notify_all_admins(
            title=f'⚠️ اشتراك على وشك الانتهاء: {company.name}',
            title_en=f'⚠️ Subscription Expiring Soon: {company.name}',
            message=f'اشتراك شركة "{company.name}" في باقة "{subscription.plan_name}" سينتهي بعد {days_left} يوم.',
            message_en=f'Subscription of company "{company.name}" for "{subscription.plan_name}" plan will expire in {days_left} days.',
            notification_type='subscription_expiring',
            priority='high',
            action_url=url_for('platform.view_company', company_id=company.id),
            action_text='تجديد الاشتراك',
            action_text_en='Renew Subscription',
            data={
                'subscription_id': subscription.id,
                'company_id': company.id,
                'company_name': company.name,
                'days_left': days_left
            }
        )
    
    # ============================================
    # أحداث المستخدمين (User Events)
    # ============================================
    
    @staticmethod
    def new_user_registered(user):
        """إشعار بمستخدم جديد في المنصة"""
        company = user.organization
        
        PlatformNotificationService._notify_all_admins(
            title=f'👤 مستخدم جديد: {user.full_name}',
            title_en=f'👤 New User: {user.full_name}',
            message=f'تم تسجيل مستخدم جديد "{user.full_name}" في شركة "{company.name}".',
            message_en=f'A new user "{user.full_name}" has been registered in company "{company.name}".',
            notification_type='new_user_registration',
            priority='medium',
            action_url=url_for('platform.view_company', company_id=company.id),
            action_text='عرض المستخدمين',
            action_text_en='View Users',
            data={
                'user_id': user.id,
                'user_name': user.full_name,
                'company_id': company.id,
                'company_name': company.name
            }
        )
    
    # ============================================
    # أحداث النظام (System Events)
    # ============================================
    
    @staticmethod
    def system_alert(title, message, priority='medium', action_url=None, data=None):
        """تنبيه نظام عام"""
        PlatformNotificationService._notify_all_admins(
            title=title,
            title_en=title,
            message=message,
            message_en=message,
            notification_type='system_alert',
            priority=priority,
            action_url=action_url,
            action_text='عرض التفاصيل',
            action_text_en='View Details',
            data=data
        )
    
    @staticmethod
    def backup_completed(success=True, details=None):
        """إشعار باكتمال النسخ الاحتياطي"""
        status = '✅' if success else '❌'
        status_text = 'نجاح' if success else 'فشل'
        
        PlatformNotificationService._notify_all_admins(
            title=f'{status} النسخ الاحتياطي: {status_text}',
            title_en=f'{status} Backup: {status_text}',
            message=f'تم الانتهاء من عملية النسخ الاحتياطي لقاعدة البيانات بنجاح.' if success else f'حدث خطأ أثناء عملية النسخ الاحتياطي: {details}',
            message_en=f'Database backup completed successfully.' if success else f'Error during backup: {details}',
            notification_type='backup_completed',
            priority='medium' if success else 'high',
            data={'success': success, 'details': details}
        )
    
    @staticmethod
    def error_alert(error_message, error_location=None, stack_trace=None):
        """إشعار بخطأ في النظام"""
        PlatformNotificationService._notify_all_admins(
            title='⚠️ خطأ في النظام',
            title_en='⚠️ System Error',
            message=f'حدث خطأ في النظام: {error_message}',
            message_en=f'System error occurred: {error_message}',
            notification_type='error_alert',
            priority='critical',
            data={
                'error_message': error_message,
                'error_location': error_location,
                'stack_trace': stack_trace,
                'timestamp': datetime.utcnow().isoformat()
            }
        )
    
    # ============================================
    # أحداث الدعم (Support Events)
    # ============================================
    
    @staticmethod
    def new_support_ticket(ticket):
        """إشعار بتذكرة دعم جديدة"""
        PlatformNotificationService._notify_all_admins(
            title=f'🎫 تذكرة دعم جديدة: #{ticket.id}',
            title_en=f'🎫 New Support Ticket: #{ticket.id}',
            message=f'تم استلام تذكرة دعم جديدة من {ticket.user_name} بخصوص "{ticket.subject}"',
            message_en=f'New support ticket received from {ticket.user_name} regarding "{ticket.subject}"',
            notification_type='support_ticket',
            priority='high',
            action_url=url_for('platform.view_ticket', ticket_id=ticket.id),
            action_text='عرض التذكرة',
            action_text_en='View Ticket',
            data={'ticket_id': ticket.id}
        )
    
    # ============================================
    # التقارير الدورية (Periodic Reports)
    # ============================================
    
    @staticmethod
    def weekly_report(admin, stats):
        """إرسال تقرير أسبوعي لمدير منصة معين"""
        PlatformNotificationService._create_notification(
            admin_id=admin.id,
            title='📊 التقرير الأسبوعي للمنصة',
            title_en='📊 Weekly Platform Report',
            message=f'💰 الإيرادات: {stats.get("revenue", 0)} | 🏢 شركات جديدة: {stats.get("new_companies", 0)} | 👤 مستخدمين جدد: {stats.get("new_users", 0)} | 📋 طلبات اشتراك: {stats.get("pending_subscriptions", 0)}',
            message_en=f'💰 Revenue: {stats.get("revenue", 0)} | 🏢 New Companies: {stats.get("new_companies", 0)} | 👤 New Users: {stats.get("new_users", 0)} | 📋 Pending Subscriptions: {stats.get("pending_subscriptions", 0)}',
            notification_type='weekly_report',
            priority='medium',
            action_url=url_for('platform.reports'),
            action_text='عرض التقرير الكامل',
            action_text_en='View Full Report',
            data=stats
        )
    
    @staticmethod
    def monthly_report(admin, stats):
        """إرسال تقرير شهري لمدير منصة معين"""
        PlatformNotificationService._create_notification(
            admin_id=admin.id,
            title='📈 التقرير الشهري للمنصة',
            title_en='📈 Monthly Platform Report',
            message=f'📊 إجمالي الإيرادات: {stats.get("total_revenue", 0)} | 🏢 إجمالي الشركات: {stats.get("total_companies", 0)} | 👤 إجمالي المستخدمين: {stats.get("total_users", 0)} | ✅ اشتراكات نشطة: {stats.get("active_subscriptions", 0)}',
            message_en=f'📊 Total Revenue: {stats.get("total_revenue", 0)} | 🏢 Total Companies: {stats.get("total_companies", 0)} | 👤 Total Users: {stats.get("total_users", 0)} | ✅ Active Subscriptions: {stats.get("active_subscriptions", 0)}',
            notification_type='weekly_report',  # يمكن إضافة نوع منفصل
            priority='medium',
            action_url=url_for('platform.reports'),
            action_text='عرض التقرير الكامل',
            action_text_en='View Full Report',
            data=stats
        )
    
    # ============================================
    # دالة مساعدة لتنظيف الإشعارات القديمة
    # ============================================
    
    @staticmethod
    def cleanup_old_notifications(days=90):
        """حذف الإشعارات القديمة المقروءة"""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        old_notifications = PlatformNotification.query.filter(
            PlatformNotification.is_read == True,
            PlatformNotification.created_at < cutoff_date
        ).all()
        
        count = len(old_notifications)
        for notif in old_notifications:
            db.session.delete(notif)
        
        db.session.commit()
        logger.info(f"🗑️ تم حذف {count} إشعار قديم")
        return count
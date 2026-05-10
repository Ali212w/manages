# tasks_async.py
from extensions import celery, db
from models import Project, Task, User, Notification
from utils import send_notification
from datetime import datetime, timedelta
import logging
from services.ai_extractor import DataExtractor 
from reporting_engine import ReportingEngine
import smtplib
import os
from celery.schedules import crontab

logger = logging.getLogger(__name__)

@celery.task
def process_project_file_async(file_path, project_id):
    """معالجة ملف المشروع بشكل غير متزامن"""
    try:
        # استخراج البيانات
        project_data = DataExtractor.parse_project_with_ai(file_path)
        
        if project_data:
            # حفظ المهام
            from services.ai_extractor import DataExtractor 
            DataExtractor.save_tasks_recursively(project_data['tasks'], project_id)
            
            # تحديث المشروع
            project = Project.query.get(project_id)
            if project:
                import json
                project.extracted_data_json = json.dumps(project_data)
                db.session.commit()
            
            # إرسال إشعار للمستخدم
            project = Project.query.get(project_id)
            if project:
                send_notification(
                    project.manager_id,
                    'اكتملت معالجة الملف',
                    f'تم استخراج بيانات المشروع "{project.title}" بنجاح',
                    'success',
                    project_id=project_id
                )
            
            return {'status': 'success', 'message': 'تمت المعالجة بنجاح'}
        else:
            return {'status': 'error', 'message': 'فشل استخراج البيانات'}
            
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        
        # إرسال إشعار بالفشل
        project = Project.query.get(project_id)
        if project:
            send_notification(
                project.manager_id,
                'فشل في معالجة الملف',
                f'حدث خطأ في معالجة ملف المشروع: {str(e)}',
                'error',
                project_id=project_id
            )
        
        return {'status': 'error', 'message': str(e)}

@celery.task
def send_daily_reminders():
    """إرسال التذكيرات اليومية"""
    try:
        # المهام التي ستبدأ غداً
        tomorrow = datetime.utcnow() + timedelta(days=1)
        
        tasks = Task.query.filter(
            Task.planned_start <= tomorrow,
            Task.planned_start > datetime.utcnow(),
            Task.status == 'pending'
        ).all()
        
        for task in tasks:
            if task.assigned_to_id:
                send_notification(
                    task.assigned_to_id,
                    'تذكير بمهمة قادمة',
                    f'مهمة "{task.title}" في مشروع "{task.project.title}" ستبدأ غداً',
                    'reminder',
                    task_id=task.id,
                    project_id=task.project_id
                )
        
        return {'status': 'success', 'sent': len(tasks)}
    except Exception as e:
        logger.error(f"Error sending reminders: {e}")
        return {'status': 'error', 'message': str(e)}

@celery.task
def generate_weekly_reports():
    """توليد التقارير الأسبوعية"""
    try:
        # المشاريع النشطة
        projects = Project.query.filter_by(status='in_progress').all()
        
        engine = ReportingEngine()
        reports_generated = 0
        
        for project in projects:
            # توليد تقرير PDF
            pdf_buffer = engine.generate_pdf_report(project.id)
            
            # حفظ التقرير
            report_path = f"reports/weekly_report_{project.id}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
            with open(report_path, 'wb') as f:
                f.write(pdf_buffer.getvalue())
            
            # إرسال للمدير
            if project.manager_id:
                send_notification(
                    project.manager_id,
                    'التقرير الأسبوعي جاهز',
                    f'تم توليد التقرير الأسبوعي لمشروع "{project.title}"',
                    'report',
                    project_id=project.id
                )
            
            reports_generated += 1
        
        return {'status': 'success', 'reports_generated': reports_generated}
    except Exception as e:
        logger.error(f"Error generating reports: {e}")
        return {'status': 'error', 'message': str(e)}

@celery.task
def cleanup_old_files(days=30):
    """تنظيف الملفات القديمة"""
    try:
        import os
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        # حذف الملفات المؤقتة
        temp_dir = 'static/uploads/temp'
        if os.path.exists(temp_dir):
            for file in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    if file_time < cutoff_date:
                        os.remove(file_path)
        
        return {'status': 'success', 'message': f'تم تنظيف الملفات الأقدم من {days} يوم'}
    except Exception as e:
        logger.error(f"Error cleaning files: {e}")
        return {'status': 'error', 'message': str(e)}

@celery.task
def sync_with_external_system(system_name, data):
    """مزامنة مع نظام خارجي"""
    try:
        if system_name == 'github':
            # مزامنة مع GitHub
            from api_v1 import GitHubWebhook
            webhook = GitHubWebhook()
            webhook.process_commit(data)
        
        elif system_name == 'slack':
            # إرسال إشعار إلى Slack
            import requests
            webhook_url = current_app.config.get('SLACK_WEBHOOK_URL')
            if webhook_url:
                requests.post(webhook_url, json={'text': data['message']})
        
        return {'status': 'success', 'system': system_name}
    except Exception as e:
        logger.error(f"Error syncing with {system_name}: {e}")
        return {'status': 'error', 'message': str(e)}

@celery.task
def backup_database():
    """النسخ الاحتياطي لقاعدة البيانات"""
    try:
        import subprocess
        from flask import current_app
        
        # تحديد اسم الملف
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        backup_file = f"backups/db_backup_{timestamp}.sql"
        
        # تنفيذ backup
        db_url = current_app.config['SQLALCHEMY_DATABASE_URI']
        
        if 'sqlite' in db_url:
            # SQLite backup
            import shutil
            db_path = db_url.replace('sqlite:///', '')
            shutil.copy2(db_path, backup_file)
        else:
            # PostgreSQL backup
            cmd = f"pg_dump {db_url} > {backup_file}"
            subprocess.run(cmd, shell=True, check=True)
        
        # ضغط الملف
        import gzip
        with open(backup_file, 'rb') as f_in:
            with gzip.open(f"{backup_file}.gz", 'wb') as f_out:
                f_out.writelines(f_in)
        
        # حذف الملف غير المضغوط
        os.remove(backup_file)
        
        return {'status': 'success', 'file': f"{backup_file}.gz"}
    except Exception as e:
        logger.error(f"Error backing up database: {e}")
        return {'status': 'error', 'message': str(e)}
    
@celery.task
def scheduled_task_reminders():
    """مهمة مجدولة لإرسال التذكيرات"""
    from utils.utils import send_task_reminders_with_email
    
    result = send_task_reminders_with_email()
    logger.info(f"Scheduled reminders completed: {result}")
    return result

# جدولة المهمة
@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # إرسال تذكيرات كل 15 دقيقة
    sender.add_periodic_task(
        15 * 60,  # 15 دقيقة
        scheduled_task_reminders.s(),
        name='send-task-reminders-every-15-minutes'
    )
    
    # إرسال تقارير أسبوعية كل يوم أحد الساعة 8 صباحاً
    sender.add_periodic_task(
        crontab(day_of_week='sunday', hour=8, minute=0),
        scheduled_task_reminders.s(),
        name='send-weekly-reports'
    )
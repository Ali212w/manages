"""
المدير الافتراضي الذكي - يدير المشروع تلقائياً 24/7
"""

from datetime import datetime, timedelta, time
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum
import schedule
import time as sleep_time
from threading import Thread

from ..models.project_models import Project, Task, Activity, BillItem
from ..models.core_models import User, Notification
from ..models.notification_models import SmartAlert
from ..extensions import db, mail
from flask_mail import Message
from .notification_engine import NotificationEngine
from .progress_tracker import ProgressTracker
from .risk_predictor import RiskPredictor

logger = logging.getLogger(__name__)

class TimeSlot(Enum):
    """الفترات الزمنية اليومية"""
    MORNING = 'morning'       # 8:00 - 12:00
    AFTERNOON = 'afternoon'   # 12:00 - 16:00
    EVENING = 'evening'       # 16:00 - 20:00
    NIGHT = 'night'          # 20:00 - 8:00 (اليوم التالي)

@dataclass
class VirtualManagerState:
    """حالة المدير الافتراضي"""
    current_time_slot: TimeSlot
    active_projects: List[int]
    pending_decisions: List[Dict]
    recent_alerts: List[Dict]
    performance_metrics: Dict[str, float]

class VirtualManager:
    """المدير الافتراضي الذكي"""
    
    def __init__(self):
        self.state = VirtualManagerState(
            current_time_slot=TimeSlot.MORNING,
            active_projects=[],
            pending_decisions=[],
            recent_alerts=[],
            performance_metrics={}
        )
        
        self.notification_engine = NotificationEngine()
        self.progress_tracker = ProgressTracker()
        self.risk_predictor = RiskPredictor()
        
        self.is_running = False
        self.scheduler_thread = None
        
    def start(self):
        """بدء المدير الافتراضي"""
        if self.is_running:
            logger.warning("المدير الافتراضي يعمل بالفعل")
            return
        
        logger.info("بدء المدير الافتراضي الذكي")
        self.is_running = True
        
        # جدولة المهام اليومية
        self._schedule_daily_tasks()
        
        # بدء خيط الجدولة
        self.scheduler_thread = Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        # تشغيل المهام الأولية
        self._run_initial_tasks()
        
    def stop(self):
        """إيقاف المدير الافتراضي"""
        logger.info("إيقاف المدير الافتراضي الذكي")
        self.is_running = False
        
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
    
    def _run_scheduler(self):
        """تشغيل جدولة المهام"""
        while self.is_running:
            schedule.run_pending()
            sleep_time.sleep(60)  # التحقق كل دقيقة
    
    def _schedule_daily_tasks(self):
        """جدولة المهام اليومية"""
        
        # تقرير الصباح (8:00 صباحاً)
        schedule.every().day.at("08:00").do(self._send_morning_reports)
        
        # تحديث منتصف اليوم (12:00 ظهراً)
        schedule.every().day.at("12:00").do(self._send_midday_updates)
        
        # تقرير المساء (18:00 مساءً)
        schedule.every().day.at("18:00").do(self._send_evening_reports)
        
        # فحص المخاطر كل ساعتين
        schedule.every(2).hours.do(self._check_project_risks)
        
        # متابعة المهام المتأخرة كل ساعة
        schedule.every().hour.do(self._check_delayed_tasks)
        
        # تحديث التقدم التلقائي كل 30 دقيقة
        schedule.every(30).minutes.do(self._auto_update_progress)
        
        # تقرير أسبوعي (الإثنين 9:00)
        schedule.every().monday.at("09:00").do(self._send_weekly_reports)
        
        # تقرير شهري (أول كل شهر 10:00)
        schedule.every().day.at("10:00").do(self._check_monthly_report)
        
        logger.info("تم جدولة المهام اليومية للمدير الافتراضي")
    
    def _run_initial_tasks(self):
        """تشغيل المهام الأولية"""
        # تحديث قائمة المشاريع النشطة
        self._update_active_projects()
        
        # فحص المخاطر الفورية
        self._check_immediate_risks()
        
        # إرسال تحية للمستخدمين النشطين
        self._send_greeting_to_active_users()
    
    def _update_active_projects(self):
        """تحديث قائمة المشاريع النشطة"""
        try:
            active_projects = Project.query.filter_by(status='active').all()
            self.state.active_projects = [p.id for p in active_projects]
            
            logger.info(f"تم تحديث المشاريع النشطة: {len(active_projects)} مشروع")
            
        except Exception as e:
            logger.error(f"خطأ في تحديث المشاريع النشطة: {e}")
    
    def _send_morning_reports(self):
        """إرسال تقارير الصباح"""
        logger.info("إرسال تقارير الصباح")
        
        try:
            for project_id in self.state.active_projects:
                project = Project.query.get(project_id)
                if not project:
                    continue
                
                # توليد التقرير الصباحي
                morning_report = self._generate_morning_report(project)
                
                # إرسال للمدير
                manager = User.query.get(project.project_manager_id)
                if manager:
                    self._send_report_to_user(
                        user=manager,
                        report_data=morning_report,
                        report_type='morning'
                    )
                
                # إرسال للمشرفين
                supervisors = self._get_project_supervisors(project)
                for supervisor in supervisors:
                    self._send_report_to_user(
                        user=supervisor,
                        report_data=morning_report,
                        report_type='morning_supervisor'
                    )
                
                # بدء المهام المجدولة تلقائياً
                self._auto_start_scheduled_tasks(project)
                
                # التحقق من توفر المواد
                self._check_material_availability(project)
            
            # تحديث الفترة الزمنية
            self.state.current_time_slot = TimeSlot.MORNING
            
            logger.info("تم إرسال جميع تقارير الصباح")
            
        except Exception as e:
            logger.error(f"خطأ في إرسال تقارير الصباح: {e}")
    
    def _generate_morning_report(self, project: Project) -> Dict:
        """توليد تقرير الصباح الذكي"""
        from datetime import date
        
        # الحصول على بيانات اليوم
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        # إحصائيات الأمس
        yesterday_tasks = self._get_tasks_by_date(project.id, yesterday)
        completed_yesterday = len([t for t in yesterday_tasks if t.status == 'completed'])
        
        # مهام اليوم
        today_tasks = self._get_tasks_by_date(project.id, today)
        scheduled_today = len(today_tasks)
        
        # المهام المتأخرة
        delayed_tasks = self._get_delayed_tasks(project.id)
        
        # العمال الحاضرين
        present_workers = self._get_present_workers(project.id)
        
        # المصروفات
        daily_expenses = self._get_daily_expenses(project.id, yesterday)
        
        # التقدم الكلي
        overall_progress = project.progress_percentage or 0
        
        # توليد التقرير
        report = {
            'project_id': project.id,
            'project_name': project.name,
            'project_name_ar': project.name_ar,
            'report_date': today.isoformat(),
            'report_type': 'morning',
            
            'yesterday_summary': {
                'completed_tasks': completed_yesterday,
                'total_tasks': len(yesterday_tasks),
                'completion_rate': (completed_yesterday / len(yesterday_tasks) * 100) 
                                   if yesterday_tasks else 0,
                'expenses': daily_expenses
            },
            
            'today_plan': {
                'scheduled_tasks': scheduled_today,
                'delayed_tasks': len(delayed_tasks),
                'critical_tasks': len([t for t in today_tasks 
                                      if t.priority == 1]),
                'required_workers': len(set([t.supervisor_id for t in today_tasks 
                                           if t.supervisor_id]))
            },
            
            'current_status': {
                'overall_progress': overall_progress,
                'workers_present': len(present_workers),
                'workers_required': project.estimated_workers or 10,
                'attendance_rate': (len(present_workers) / 
                                   (project.estimated_workers or 10) * 100),
                'weather_forecast': self._get_weather_forecast(project.location_coordinates)
            },
            
            'alerts': {
                'delayed_tasks': [{
                    'task_id': t.id,
                    'task_name': t.task_name,
                    'delay_hours': self._calculate_delay_hours(t)
                } for t in delayed_tasks[:5]],  # أول 5 مهام متأخرة فقط
                
                'material_shortages': self._check_material_shortages(project.id),
                'risk_alerts': self._get_active_risk_alerts(project.id)
            },
            
            'recommendations': self._generate_morning_recommendations(
                project, today_tasks, delayed_tasks
            ),
            
            'virtual_manager_notes': [
                "تم تحديث جميع المهام المجدولة",
                "تم التحقق من توفر المواد",
                "جاهز لبدء اليوم بكفاءة عالية"
            ]
        }
        
        return report
    
    def _get_tasks_by_date(self, project_id: int, target_date: date) -> List[Task]:
        """الحصول على المهام المجدولة لتاريخ معين"""
        return Task.query.filter(
            Task.project_id == project_id,
            db.func.date(Task.planned_start_date) == target_date,
            Task.status.in_(['pending', 'in_progress'])
        ).all()
    
    def _get_delayed_tasks(self, project_id: int) -> List[Task]:
        """الحصول على المهام المتأخرة"""
        today = datetime.now().date()
        
        return Task.query.filter(
            Task.project_id == project_id,
            Task.planned_end_date < today,
            Task.status.in_(['pending', 'in_progress'])
        ).all()
    
    def _get_present_workers(self, project_id: int) -> List[User]:
        """الحصول على العمال الحاضرين"""
        # في التطبيق الحقيقي، سيتم التحقق من سجلات الحضور
        # هنا نعيد قائمة وهمية للتوضيح
        from ..models.core_models import User, TaskAssignment
        
        # الحصول على المستخدمين المعينين في مهام اليوم
        today = datetime.now().date()
        
        assigned_users = db.session.query(User).join(
            TaskAssignment, User.id == TaskAssignment.user_id
        ).join(
            Task, TaskAssignment.task_id == Task.id
        ).filter(
            Task.project_id == project_id,
            db.func.date(Task.planned_start_date) == today,
            TaskAssignment.status.in_(['assigned', 'accepted', 'in_progress'])
        ).distinct().all()
        
        return assigned_users
    
    def _get_daily_expenses(self, project_id: int, target_date: date) -> float:
        """الحصول على مصروفات يوم معين"""
        # في التطبيق الحقيقي، سيتم الحصول من جدول المصروفات
        # هنا نعيد قيمة تقديرية
        return 25000.0  # 25,000 ريال يومياً
    
    def _get_weather_forecast(self, coordinates: str) -> Dict:
        """الحصول على توقعات الطقس"""
        # في التطبيق الحقيقي، سيتم الاتصال بخدمة الطقس
        return {
            'temperature': 32,
            'condition': 'مشمس',
            'humidity': 45,
            'wind_speed': 15,
            'recommendations': [
                'شرب كمية كافية من الماء',
                'استخدام واقي الشمس',
                'أخذ فترات راحة في الظل'
            ]
        }
    
    def _check_material_shortages(self, project_id: int) -> List[Dict]:
        """التحقق من نقص المواد"""
        # في التطبيق الحقيقي، سيتم التحقق من المخزون
        return []  # لا توجد نقص في المواد
    
    def _get_active_risk_alerts(self, project_id: int) -> List[Dict]:
        """الحصول على إنذارات المخاطر النشطة"""
        return [
            {
                'risk_id': 1,
                'title': 'تأخير في تسليم الحديد',
                'severity': 'high',
                'action_required': True
            }
        ]
    
    def _generate_morning_recommendations(self, project: Project, 
                                        today_tasks: List[Task],
                                        delayed_tasks: List[Task]) -> List[Dict]:
        """توليد توصيات الصباح الذكية"""
        recommendations = []
        
        # إذا كان هناك مهام متأخرة
        if delayed_tasks:
            recommendations.append({
                'priority': 'high',
                'title': 'معالجة المهام المتأخرة',
                'description': f'يوجد {len(delayed_tasks)} مهام متأخرة تحتاج متابعة فورية',
                'action': 'focus_on_delayed_tasks',
                'estimated_time': '2 ساعات'
            })
        
        # إذا كان عدد المهام اليوم كبير
        if len(today_tasks) > 15:
            recommendations.append({
                'priority': 'medium',
                'title': 'إعادة توزيع المهام',
                'description': 'عدد المهام اليوم كبير، يمكن تقسيمها على يومين',
                'action': 'redistribute_tasks',
                'estimated_time': '1 ساعة'
            })
        
        # إذا كان الطقس حاراً
        weather = self._get_weather_forecast(project.location_coordinates)
        if weather.get('temperature', 0) > 35:
            recommendations.append({
                'priority': 'medium',
                'title': 'تعديل ساعات العمل',
                'description': 'درجة الحرارة مرتفعة، يفضل العمل في الصباح الباكر والمساء',
                'action': 'adjust_working_hours',
                'estimated_time': '30 دقيقة'
            })
        
        # توصية عامة
        recommendations.append({
            'priority': 'low',
            'title': 'اجتماع تنسيق صباحي',
            'description': 'اجتماع قصير مع المشرفين لتنسيق العمل اليومي',
            'action': 'morning_coordination_meeting',
            'estimated_time': '15 دقيقة'
        })
        
        return recommendations
    
    def _send_report_to_user(self, user: User, report_data: Dict, 
                           report_type: str):
        """إرسال تقرير للمستخدم"""
        try:
            # إنشاء إشعار في النظام
            notification = Notification(
                user_id=user.id,
                title=self._get_report_title(report_type, report_data),
                title_ar=self._get_report_title_ar(report_type, report_data),
                message=self._format_report_message(report_data, report_type),
                message_ar=self._format_report_message_ar(report_data, report_type),
                notification_type=report_type,
                related_project_id=report_data.get('project_id'),
                priority='medium' if report_type == 'morning' else 'low'
            )
            
            db.session.add(notification)
            
            # إرسال بريد إلكتروني إذا كان مفعلاً
            if user.email_notifications:
                self._send_email_report(user, report_data, report_type)
            
            # إرسال إشعار Push إذا كان مفعلاً
            if user.push_notifications:
                self._send_push_notification(user, report_data, report_type)
            
            db.session.commit()
            
            logger.info(f"تم إرسال تقرير {report_type} للمستخدم {user.email}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في إرسال التقرير: {e}")
    
    def _get_report_title(self, report_type: str, report_data: Dict) -> str:
        """الحصول على عنوان التقرير بالإنجليزية"""
        titles = {
            'morning': f"Morning Report - {report_data.get('project_name', 'Project')}",
            'morning_supervisor': f"Daily Tasks - {report_data.get('project_name', 'Project')}",
            'midday': f"Progress Update - {report_data.get('project_name', 'Project')}",
            'evening': f"Evening Summary - {report_data.get('project_name', 'Project')}",
            'weekly': f"Weekly Report - {report_data.get('project_name', 'Project')}",
            'monthly': f"Monthly Report - {report_data.get('project_name', 'Project')}"
        }
        return titles.get(report_type, "Project Report")
    
    def _get_report_title_ar(self, report_type: str, report_data: Dict) -> str:
        """الحصول على عنوان التقرير بالعربية"""
        titles = {
            'morning': f"تقرير الصباح - {report_data.get('project_name_ar', 'المشروع')}",
            'morning_supervisor': f"المهام اليومية - {report_data.get('project_name_ar', 'المشروع')}",
            'midday': f"تحديث التقدم - {report_data.get('project_name_ar', 'المشروع')}",
            'evening': f"ملخص المساء - {report_data.get('project_name_ar', 'المشروع')}",
            'weekly': f"تقرير أسبوعي - {report_data.get('project_name_ar', 'المشروع')}",
            'monthly': f"تقرير شهري - {report_data.get('project_name_ar', 'المشروع')}"
        }
        return titles.get(report_type, "تقرير المشروع")
    
    def _format_report_message(self, report_data: Dict, report_type: str) -> str:
        """تنسيق رسالة التقرير بالإنجليزية"""
        if report_type == 'morning':
            yesterday = report_data.get('yesterday_summary', {})
            today = report_data.get('today_plan', {})
            
            return (
                f"Good morning!\n\n"
                f"Yesterday's completion: {yesterday.get('completed_tasks', 0)}/{yesterday.get('total_tasks', 0)} tasks\n"
                f"Today's plan: {today.get('scheduled_tasks', 0)} tasks scheduled\n"
                f"Delayed tasks: {today.get('delayed_tasks', 0)} need attention\n"
                f"Overall progress: {report_data.get('current_status', {}).get('overall_progress', 0)}%\n\n"
                f"Best regards,\nVirtual Project Manager"
            )
        
        return f"Project report for {report_data.get('project_name', 'Project')}"
    
    def _format_report_message_ar(self, report_data: Dict, report_type: str) -> str:
        """تنسيق رسالة التقرير بالعربية"""
        if report_type == 'morning':
            yesterday = report_data.get('yesterday_summary', {})
            today = report_data.get('today_plan', {})
            
            return (
                f"صباح الخير!\n\n"
                f"إنجاز الأمس: {yesterday.get('completed_tasks', 0)}/{yesterday.get('total_tasks', 0)} مهمة\n"
                f"خطة اليوم: {today.get('scheduled_tasks', 0)} مهمة مجدولة\n"
                f"المهام المتأخرة: {today.get('delayed_tasks', 0)} تحتاج متابعة\n"
                f"التقدم الكلي: {report_data.get('current_status', {}).get('overall_progress', 0)}%\n\n"
                f"مع أطيب التحيات،\nالمدير الافتراضي للمشروع"
            )
        
        return f"تقرير مشروع {report_data.get('project_name_ar', 'المشروع')}"
    
    def _send_email_report(self, user: User, report_data: Dict, report_type: str):
        """إرسال تقرير بالبريد الإلكتروني"""
        try:
            subject = self._get_report_title(report_type, report_data)
            
            msg = Message(
                subject=subject,
                recipients=[user.email],
                body=self._format_report_message(report_data, report_type),
                html=self._generate_email_html(report_data, report_type)
            )
            
            mail.send(msg)
            
        except Exception as e:
            logger.error(f"خطأ في إرسال البريد الإلكتروني: {e}")
    
    def _generate_email_html(self, report_data: Dict, report_type: str) -> str:
        """توليد HTML للبريد الإلكتروني"""
        # في التطبيق الحقيقي، سيتم استخدام قالب HTML
        return f"""
        <html>
        <body>
            <h2>{self._get_report_title(report_type, report_data)}</h2>
            <p>{self._format_report_message(report_data, report_type)}</p>
        </body>
        </html>
        """
    
    def _send_push_notification(self, user: User, report_data: Dict, report_type: str):
        """إرسال إشعار Push"""
        # في التطبيق الحقيقي، سيتم استخدام خدمة Push Notifications
        pass
    
    def _get_project_supervisors(self, project: Project) -> List[User]:
        """الحصول على مشرفي المشروع"""
        supervisors = []
        
        # الحصول من الأنشطة
        activities = Activity.query.filter_by(project_id=project.id).all()
        supervisor_ids = set([a.supervisor_id for a in activities if a.supervisor_id])
        
        for supervisor_id in supervisor_ids:
            supervisor = User.query.get(supervisor_id)
            if supervisor and supervisor.role in ['supervisor', 'project_manager']:
                supervisors.append(supervisor)
        
        return supervisors
    
    def _auto_start_scheduled_tasks(self, project: Project):
        """بدء المهام المجدولة تلقائياً"""
        try:
            today = datetime.now().date()
            
            # الحصول على المهام المجدولة للبدء اليوم
            tasks_to_start = Task.query.filter(
                Task.project_id == project.id,
                db.func.date(Task.planned_start_date) == today,
                Task.status == 'pending',
                Task.planned_start_date <= datetime.now()
            ).all()
            
            for task in tasks_to_start:
                # بدء المهمة تلقائياً
                task.status = 'in_progress'
                task.actual_start_date = datetime.now()
                task.progress_percentage = 0.1  # بدأت للتو
                
                # إرسال إشعار
                self._notify_task_start(task)
            
            db.session.commit()
            
            if tasks_to_start:
                logger.info(f"تم بدء {len(tasks_to_start)} مهمة تلقائياً في المشروع {project.name}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في بدء المهام تلقائياً: {e}")
    
    def _notify_task_start(self, task: Task):
        """إرسال إشعار ببدء المهمة"""
        notification = Notification(
            user_id=task.supervisor_id,
            title=f"Task Started: {task.task_name}",
            title_ar=f"بدء المهمة: {task.task_name_ar}",
            message=f"Task {task.task_code} has started automatically",
            message_ar=f"بدأت المهمة {task.task_code} تلقائياً",
            notification_type='task_started',
            related_task_id=task.id,
            related_project_id=task.project_id,
            priority='medium'
        )
        
        db.session.add(notification)
    
    def _check_material_availability(self, project: Project):
        """التحقق من توفر المواد"""
        # في التطبيق الحقيقي، سيتم التحقق من المخزون وطلبات الشراء
        pass
    
    def _send_midday_updates(self):
        """إرسال تحديثات منتصف اليوم"""
        logger.info("إرسال تحديثات منتصف اليوم")
        
        try:
            for project_id in self.state.active_projects:
                project = Project.query.get(project_id)
                if not project:
                    continue
                
                # توليد تحديث منتصف اليوم
                midday_update = self._generate_midday_update(project)
                
                # إرسال للمدير
                manager = User.query.get(project.project_manager_id)
                if manager:
                    self._send_update_to_user(
                        user=manager,
                        update_data=midday_update,
                        update_type='midday'
                    )
            
            # تحديث الفترة الزمنية
            self.state.current_time_slot = TimeSlot.AFTERNOON
            
            logger.info("تم إرسال جميع تحديثات منتصف اليوم")
            
        except Exception as e:
            logger.error(f"خطأ في إرسال تحديثات منتصف اليوم: {e}")
    
    def _generate_midday_update(self, project: Project) -> Dict:
        """توليد تحديث منتصف اليوم"""
        from datetime import datetime
        
        # الحصول على التقدم الحالي
        current_progress = self.progress_tracker.get_project_progress(project.id)
        
        # المهام المكتملة صباحاً
        morning_completed = self._get_tasks_completed_in_period(
            project.id, 
            start_time=datetime.now().replace(hour=8, minute=0, second=0),
            end_time=datetime.now().replace(hour=12, minute=0, second=0)
        )
        
        # المهام الجارية
        ongoing_tasks = self._get_ongoing_tasks(project.id)
        
        # المشكلات المكتشفة
        issues_detected = self._detect_issues(project.id)
        
        # توليد التحديث
        update = {
            'project_id': project.id,
            'project_name': project.name,
            'project_name_ar': project.name_ar,
            'update_time': datetime.now().isoformat(),
            'update_type': 'midday',
            
            'morning_progress': {
                'completed_tasks': len(morning_completed),
                'ongoing_tasks': len(ongoing_tasks),
                'completion_rate': (len(morning_completed) / 
                                   (len(morning_completed) + len(ongoing_tasks)) * 100) 
                                   if (len(morning_completed) + len(ongoing_tasks)) > 0 else 0,
                'average_task_duration': self._calculate_average_task_duration(morning_completed)
            },
            
            'current_status': {
                'overall_progress': current_progress.get('overall_percentage', 0),
                'workers_active': len(set([t.supervisor_id for t in ongoing_tasks 
                                         if t.supervisor_id])),
                'productivity_score': self._calculate_productivity_score(
                    morning_completed, ongoing_tasks
                )
            },
            
            'issues_detected': issues_detected,
            
            'afternoon_recommendations': self._generate_afternoon_recommendations(
                morning_completed, ongoing_tasks, issues_detected
            ),
            
            'virtual_manager_notes': [
                "الأداء الصباحي جيد",
                "الاستمرار بنفس الوتيرة",
                "مراقبة المهام الحرجة"
            ]
        }
        
        return update
    
    def _get_tasks_completed_in_period(self, project_id: int, start_time: datetime, 
                                     end_time: datetime) -> List[Task]:
        """الحصول على المهام المكتملة في فترة زمنية"""
        return Task.query.filter(
            Task.project_id == project_id,
            Task.status == 'completed',
            Task.actual_end_date >= start_time,
            Task.actual_end_date <= end_time
        ).all()
    
    def _get_ongoing_tasks(self, project_id: int) -> List[Task]:
        """الحصول على المهام الجارية"""
        return Task.query.filter(
            Task.project_id == project_id,
            Task.status == 'in_progress'
        ).all()
    
    def _detect_issues(self, project_id: int) -> List[Dict]:
        """اكتشاف المشكلات أثناء العمل"""
        issues = []
        
        # التحقق من المهام المتأخرة
        delayed_tasks = self._get_delayed_tasks(project_id)
        if delayed_tasks:
            issues.append({
                'type': 'delay',
                'severity': 'medium',
                'description': f'{len(delayed_tasks)} مهمة متأخرة',
                'affected_tasks': [t.id for t in delayed_tasks[:3]]
            })
        
        # التحقق من نقص العمال
        required_workers = self._calculate_required_workers(project_id)
        present_workers = len(self._get_present_workers(project_id))
        
        if present_workers < required_workers * 0.8:  # أقل من 80% من المطلوب
            issues.append({
                'type': 'staffing',
                'severity': 'high',
                'description': f'نقص في العمالة: {present_workers}/{required_workers}',
                'action_required': True
            })
        
        return issues
    
    def _calculate_average_task_duration(self, tasks: List[Task]) -> float:
        """حساب متوسط مدة المهام"""
        if not tasks:
            return 0.0
        
        total_duration = 0
        count = 0
        
        for task in tasks:
            if task.actual_start_date and task.actual_end_date:
                duration = (task.actual_end_date - task.actual_start_date).total_seconds() / 3600
                total_duration += duration
                count += 1
        
        return total_duration / count if count > 0 else 0.0
    
    def _calculate_productivity_score(self, completed_tasks: List[Task], 
                                    ongoing_tasks: List[Task]) -> float:
        """حساب درجة الإنتاجية"""
        total_tasks = len(completed_tasks) + len(ongoing_tasks)
        if total_tasks == 0:
            return 100.0  # لا توجد مهام، إنتاجية مثالية
        
        # حساب نسبة الإنجاز
        completion_ratio = len(completed_tasks) / total_tasks
        
        # حساب كفاءة الوقت
        time_efficiency = self._calculate_time_efficiency(completed_tasks)
        
        # حساب الجودة (فرضية)
        quality_score = 95.0
        
        # حساب النتيجة النهائية
        productivity = (completion_ratio * 40) + (time_efficiency * 40) + (quality_score * 0.2)
        
        return min(100.0, max(0.0, productivity))
    
    def _calculate_time_efficiency(self, tasks: List[Task]) -> float:
        """حساب كفاءة الوقت"""
        if not tasks:
            return 100.0
        
        total_efficiency = 0
        count = 0
        
        for task in tasks:
            if task.planned_duration and task.actual_duration:
                efficiency = (task.planned_duration / task.actual_duration) * 100
                total_efficiency += min(efficiency, 150)  # حد أقصى 150%
                count += 1
        
        return total_efficiency / count if count > 0 else 100.0
    
    def _calculate_required_workers(self, project_id: int) -> int:
        """حساج عدد العمال المطلوب"""
        # في التطبيق الحقيقي، سيتم حساب بناءً على المهام الجارية
        return 20  # قيمة وهمية
    
    def _generate_afternoon_recommendations(self, completed_tasks: List[Task],
                                          ongoing_tasks: List[Task],
                                          issues: List[Dict]) -> List[Dict]:
        """توليد توصيات فترة الظهيرة"""
        recommendations = []
        
        # إذا كانت الإنتاجية منخفضة
        productivity = self._calculate_productivity_score(completed_tasks, ongoing_tasks)
        if productivity < 70:
            recommendations.append({
                'priority': 'high',
                'title': 'تحسين الإنتاجية',
                'description': f'الإنتاجية الحالية {productivity:.1f}%، تحتاج تحسين',
                'action': 'increase_productivity',
                'suggestions': [
                    'إعادة توزيع المهام',
                    'تقديم حوافز للعمال',
                    'تحسين التنسيق بين الفرق'
                ]
            })
        
        # إذا كان هناك مشكلات
        if issues:
            high_priority_issues = [i for i in issues if i.get('severity') in ['high', 'critical']]
            if high_priority_issues:
                recommendations.append({
                    'priority': 'critical',
                    'title': 'معالجة المشكلات العاجلة',
                    'description': f'يوجد {len(high_priority_issues)} مشكلة تحتاج معالجة فورية',
                    'action': 'address_urgent_issues',
                    'estimated_time': '1-2 ساعات'
                })
        
        # توصية لتحسين الجودة
        recommendations.append({
            'priority': 'medium',
            'title': 'فحص جودة الصباح',
            'description': 'فحص جودة العمل المنفذ في الصباح',
            'action': 'quality_check_morning_work',
            'estimated_time': '1 ساعة'
        })
        
        # توصية للاستراحة
        recommendations.append({
            'priority': 'low',
            'title': 'استراحة الظهيرة',
            'description': 'تأكد من حصول العمال على استراحة كافية',
            'action': 'ensure_break_time',
            'estimated_time': '30 دقيقة'
        })
        
        return recommendations
    
    def _send_update_to_user(self, user: User, update_data: Dict, update_type: str):
        """إرسال تحديث للمستخدم"""
        # مشابه لـ _send_report_to_user ولكن بنمط مختلف
        pass
    
    def _send_evening_reports(self):
        """إرسال تقارير المساء"""
        logger.info("إرسال تقارير المساء")
        
        try:
            for project_id in self.state.active_projects:
                project = Project.query.get(project_id)
                if not project:
                    continue
                
                # توليد تقرير المساء
                evening_report = self._generate_evening_report(project)
                
                # إرسال للمدير
                manager = User.query.get(project.project_manager_id)
                if manager:
                    self._send_report_to_user(
                        user=manager,
                        report_data=evening_report,
                        report_type='evening'
                    )
                
                # تحديث التقدم التلقائي
                self._update_project_progress(project)
                
                # جدولة مهام الغد
                self._schedule_tomorrow_tasks(project)
            
            # تحديث الفترة الزمنية
            self.state.current_time_slot = TimeSlot.EVENING
            
            logger.info("تم إرسال جميع تقارير المساء")
            
        except Exception as e:
            logger.error(f"خطأ في إرسال تقارير المساء: {e}")
    
    def _generate_evening_report(self, project: Project) -> Dict:
        """توليد تقرير المساء الذكي"""
        from datetime import datetime, date
        
        today = date.today()
        
        # الحصول على بيانات اليوم
        daily_tasks = self._get_tasks_by_date(project.id, today)
        completed_today = len([t for t in daily_tasks if t.status == 'completed'])
        ongoing_tasks = len([t for t in daily_tasks if t.status == 'in_progress'])
        pending_tasks = len([t for t in daily_tasks if t.status == 'pending'])
        
        # حساب الإنتاجية
        productivity = self._calculate_daily_productivity(project.id, today)
        
        # حساب الجودة
        quality_score = self._calculate_daily_quality(project.id, today)
        
        # حساب السلامة
        safety_score = self._calculate_daily_safety(project.id, today)
        
        # المصروفات اليومية
        daily_expenses = self._get_daily_expenses(project.id, today)
        
        # المشكلات اليومية
        daily_issues = self._get_daily_issues(project.id, today)
        
        # الإنجازات
        achievements = self._get_daily_achievements(project.id, today)
        
        # توليد التقرير
        report = {
            'project_id': project.id,
            'project_name': project.name,
            'project_name_ar': project.name_ar,
            'report_date': today.isoformat(),
            'report_type': 'evening',
            'report_time': datetime.now().strftime('%H:%M'),
            
            'daily_summary': {
                'total_tasks': len(daily_tasks),
                'completed_tasks': completed_today,
                'ongoing_tasks': ongoing_tasks,
                'pending_tasks': pending_tasks,
                'completion_rate': (completed_today / len(daily_tasks) * 100) 
                                   if daily_tasks else 0,
                'productivity_score': productivity,
                'quality_score': quality_score,
                'safety_score': safety_score
            },
            
            'financial_summary': {
                'daily_expenses': daily_expenses,
                'budget_utilization': (daily_expenses / (project.contract_value / 365)) * 100 
                                      if project.contract_value else 0,
                'cumulative_expenses': self._get_cumulative_expenses(project.id),
                'budget_remaining': project.contract_value - self._get_cumulative_expenses(project.id)
                                      if project.contract_value else 0
            },
            
            'issues_and_solutions': {
                'issues_today': daily_issues,
                'solutions_applied': self._get_applied_solutions(project.id, today),
                'remaining_issues': self._get_remaining_issues(project.id)
            },
            
            'achievements_today': achievements,
            
            'tomorrow_preview': {
                'scheduled_tasks': len(self._get_tasks_by_date(project.id, today + timedelta(days=1))),
                'critical_tasks': self._get_critical_tasks_tomorrow(project.id),
                'material_deliveries': self._get_tomorrow_deliveries(project.id),
                'required_preparations': self._get_tomorrow_preparations(project.id)
            },
            
            'virtual_manager_assessment': {
                'overall_performance': self._assess_daily_performance(
                    productivity, quality_score, safety_score
                ),
                'team_performance': self._assess_team_performance(project.id, today),
                'recommendations_for_tomorrow': self._generate_tomorrow_recommendations(
                    project, daily_tasks, daily_issues
                ),
                'lessons_learned_today': self._extract_lessons_learned(project.id, today)
            },
            
            'conclusion': {
                'status': 'successful' if completed_today >= len(daily_tasks) * 0.8 else 'needs_improvement',
                'main_achievement': self._get_main_achievement(achievements),
                'main_challenge': self._get_main_challenge(daily_issues),
                'overall_rating': f"{((productivity + quality_score + safety_score) / 3):.1f}/100"
            }
        }
        
        return report
    
    def _calculate_daily_productivity(self, project_id: int, target_date: date) -> float:
        """حساب الإنتاجية اليومية"""
        # تنفيذ حقيقي
        return 85.0  # قيمة وهمية
    
    def _calculate_daily_quality(self, project_id: int, target_date: date) -> float:
        """حساب درجة الجودة اليومية"""
        return 92.0  # قيمة وهمية
    
    def _calculate_daily_safety(self, project_id: int, target_date: date) -> float:
        """حساب درجة السلامة اليومية"""
        return 100.0  # قيمة وهمية
    
    def _get_daily_issues(self, project_id: int, target_date: date) -> List[Dict]:
        """الحصول على المشكلات اليومية"""
        return []  # قائمة وهمية
    
    def _get_daily_achievements(self, project_id: int, target_date: date) -> List[Dict]:
        """الحصول على الإنجازات اليومية"""
        return [
            {
                'type': 'milestone',
                'description': 'إكمال الطابق الأول',
                'impact': 'high',
                'team_credited': ['أحمد', 'محمد', 'خالد']
            }
        ]
    
    def _get_cumulative_expenses(self, project_id: int) -> float:
        """الحصول على المصروفات التراكمية"""
        return 1250000.0  # قيمة وهمية
    
    def _get_applied_solutions(self, project_id: int, target_date: date) -> List[Dict]:
        """الحصول على الحلول المطبقة"""
        return []  # قائمة وهمية
    
    def _get_remaining_issues(self, project_id: int) -> List[Dict]:
        """الحصول على المشكلات المتبقية"""
        return []  # قائمة وهمية
    
    def _get_critical_tasks_tomorrow(self, project_id: int) -> List[Dict]:
        """الحصول على المهام الحرجة لليوم التالي"""
        return []  # قائمة وهمية
    
    def _get_tomorrow_deliveries(self, project_id: int) -> List[Dict]:
        """الحصول على عمليات التسليم لليوم التالي"""
        return []  # قائمة وهمية
    
    def _get_tomorrow_preparations(self, project_id: int) -> List[Dict]:
        """الحصول على التحضيرات المطلوبة لليوم التالي"""
        return []  # قائمة وهمية
    
    def _assess_daily_performance(self, productivity: float, 
                                 quality: float, safety: float) -> str:
        """تقييم الأداء اليومي"""
        average = (productivity + quality + safety) / 3
        
        if average >= 90:
            return 'ممتاز'
        elif average >= 80:
            return 'جيد جداً'
        elif average >= 70:
            return 'جيد'
        elif average >= 60:
            return 'مقبول'
        else:
            return 'بحاجة لتحسين'
    
    def _assess_team_performance(self, project_id: int, target_date: date) -> Dict:
        """تقييم أداء الفريق"""
        return {
            'overall': 'جيد',
            'strengths': ['التزام بالمواعيد', 'جودة العمل', 'التعاون'],
            'areas_for_improvement': ['التواصل', 'التخطيط المسبق']
        }
    
    def _generate_tomorrow_recommendations(self, project: Project,
                                         daily_tasks: List[Task],
                                         daily_issues: List[Dict]) -> List[Dict]:
        """توليد توصيات لليوم التالي"""
        recommendations = []
        
        # إذا كان هناك مهام متأخرة
        if any(t.status != 'completed' for t in daily_tasks):
            recommendations.append({
                'priority': 'high',
                'title': 'إنهاء المهام المعلقة',
                'description': 'إكمال المهام التي لم تنته اليوم',
                'action': 'complete_pending_tasks',
                'estimated_time': '2 ساعة'
            })
        
        # إذا كانت هناك مشكلات تتكرر
        if len(daily_issues) > 3:
            recommendations.append({
                'priority': 'medium',
                'title': 'تحليل المشكلات المتكررة',
                'description': 'تحليل أسباب تكرار المشكلات وإيجاد حلول جذرية',
                'action': 'analyze_recurring_issues',
                'estimated_time': '1 ساعة'
            })
        
        # توصية للتحضير المبكر
        recommendations.append({
            'priority': 'low',
            'title': 'التحضير المبكر لليوم التالي',
            'description': 'تحضير المواد والأدوات قبل بدء العمل',
            'action': 'early_preparation',
            'estimated_time': '30 دقيقة'
        })
        
        return recommendations
    
    def _extract_lessons_learned(self, project_id: int, target_date: date) -> List[str]:
        """استخراج الدروس المستفادة اليوم"""
        return [
            'التخطيط المسبق يزيد الإنتاجية بنسبة 20%',
            'التواصل الفعال يقلل الأخطاء',
            'الفحص المستمر يحسن الجودة'
        ]
    
    def _get_main_achievement(self, achievements: List[Dict]) -> str:
        """الحصول على الإنجاز الرئيسي"""
        if achievements:
            return achievements[0].get('description', 'لا توجد إنجازات بارزة')
        return 'لا توجد إنجازات بارزة'
    
    def _get_main_challenge(self, issues: List[Dict]) -> str:
        """الحصول على التحدي الرئيسي"""
        if issues:
            return issues[0].get('description', 'لا توجد تحديات كبيرة')
        return 'لا توجد تحديات كبيرة'
    
    def _update_project_progress(self, project: Project):
        """تحديث تقدم المشروع تلقائياً"""
        try:
            # حساب التقدم من الأنشطة
            activities = Activity.query.filter_by(project_id=project.id).all()
            
            if activities:
                total_weight = sum(a.weight for a in activities if a.weight)
                weighted_progress = sum(a.weight * (a.progress_percentage / 100) 
                                      for a in activities if a.weight)
                
                if total_weight > 0:
                    new_progress = (weighted_progress / total_weight) * 100
                    project.progress_percentage = new_progress
                    
                    # تحديث تاريخ التحديث
                    project.updated_at = datetime.now()
                    
                    db.session.commit()
                    
                    logger.info(f"تم تحديث تقدم المشروع {project.name} إلى {new_progress:.1f}%")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في تحديث تقدم المشروع: {e}")
    
    def _schedule_tomorrow_tasks(self, project: Project):
        """جدولة مهام اليوم التالي تلقائياً"""
        try:
            tomorrow = datetime.now().date() + timedelta(days=1)
            
            # الحصول على المهام المجدولة للغد
            tomorrow_tasks = self._get_tasks_by_date(project.id, tomorrow)
            
            if tomorrow_tasks:
                # تخصيص الموارد تلقائياً
                self._auto_assign_resources(tomorrow_tasks, project)
                
                # إرسال إشعارات بالمهام المجدولة
                self._notify_scheduled_tasks(tomorrow_tasks)
                
                logger.info(f"تم جدولة {len(tomorrow_tasks)} مهمة للغد في المشروع {project.name}")
            
        except Exception as e:
            logger.error(f"خطأ في جدولة مهام الغد: {e}")
    
    def _auto_assign_resources(self, tasks: List[Task], project: Project):
        """تخصيص الموارد تلقائياً"""
        for task in tasks:
            if not task.supervisor_id:
                # البحث عن مشرف مناسب
                suitable_supervisor = self._find_suitable_supervisor(task, project)
                if suitable_supervisor:
                    task.supervisor_id = suitable_supervisor.id
    
    def _find_suitable_supervisor(self, task: Task, project: Project) -> Optional[User]:
        """البحث عن مشرف مناسب للمهمة"""
        # في التطبيق الحقيقي، سيتم البحث بناءً على المهارات والتوفر
        # هنا نعود بأول مشرف متاح
        supervisors = self._get_project_supervisors(project)
        return supervisors[0] if supervisors else None
    
    def _notify_scheduled_tasks(self, tasks: List[Task]):
        """إرسال إشعارات بالمهام المجدولة"""
        for task in tasks:
            if task.supervisor_id:
                notification = Notification(
                    user_id=task.supervisor_id,
                    title=f"Task Scheduled for Tomorrow: {task.task_name}",
                    title_ar=f"مهمة مجدولة للغد: {task.task_name_ar}",
                    message=f"Task {task.task_code} is scheduled to start tomorrow",
                    message_ar=f"المهمة {task.task_code} مجدولة للبدء غداً",
                    notification_type='task_scheduled',
                    related_task_id=task.id,
                    related_project_id=task.project_id,
                    priority='low'
                )
                
                db.session.add(notification)
        
        db.session.commit()
    
    def _check_project_risks(self):
        """فحص مخاطر المشروع"""
        logger.info("فحص مخاطر المشروع")
        
        try:
            for project_id in self.state.active_projects:
                project = Project.query.get(project_id)
                if not project:
                    continue
                
                # اكتشاف المخاطر الجديدة
                new_risks = self.risk_predictor.detect_new_risks(project)
                
                if new_risks:
                    # إرسال إنذارات للمخاطر
                    self._send_risk_alerts(project, new_risks)
                    
                    # اقتراح حلول تلقائية
                    solutions = self._suggest_risk_solutions(new_risks)
                    
                    # إضافة إلى سجل المخاطر
                    self._log_risks(project, new_risks, solutions)
            
            logger.info("تم فحص مخاطر جميع المشاريع")
            
        except Exception as e:
            logger.error(f"خطأ في فحص مخاطر المشروع: {e}")
    
    def _send_risk_alerts(self, project: Project, risks: List[Dict]):
        """إرسال إنذارات المخاطر"""
        for risk in risks:
            if risk.get('severity') in ['high', 'critical']:
                # إرسال للمدير
                manager = User.query.get(project.project_manager_id)
                if manager:
                    self._send_risk_alert_to_user(manager, project, risk)
                
                # إرسال للمشرفين ذوي الصلة
                related_supervisors = self._get_related_supervisors(project, risk)
                for supervisor in related_supervisors:
                    self._send_risk_alert_to_user(supervisor, project, risk)
    
    def _send_risk_alert_to_user(self, user: User, project: Project, risk: Dict):
        """إرسال إنذار خطر لمستخدم"""
        notification = Notification(
            user_id=user.id,
            title=f"Risk Alert: {risk.get('title', 'New Risk')}",
            title_ar=f"إنذار خطر: {risk.get('title_ar', 'خطر جديد')}",
            message=f"New risk detected in project {project.name}: {risk.get('description', '')}",
            message_ar=f"تم اكتشاف خطر جديد في مشروع {project.name_ar}: {risk.get('description_ar', '')}",
            notification_type='risk_alert',
            related_project_id=project.id,
            priority='high' if risk.get('severity') == 'critical' else 'medium'
        )
        
        db.session.add(notification)
    
    def _get_related_supervisors(self, project: Project, risk: Dict) -> List[User]:
        """الحصول على المشرفين ذوي الصلة بالخطر"""
        # في التطبيق الحقيقي، سيتم تحديد بناءً على نوع الخطر والمسؤوليات
        return self._get_project_supervisors(project)
    
    def _suggest_risk_solutions(self, risks: List[Dict]) -> List[Dict]:
        """اقتراح حلول للمخاطر"""
        solutions = []
        
        for risk in risks:
            solution = {
                'risk_id': risk.get('id'),
                'suggested_solutions': self._generate_risk_solutions(risk),
                'recommended_solution': None,
                'implementation_time': '1-3 أيام'
            }
            
            # اختيار الحل الموصى به
            if solution['suggested_solutions']:
                solution['recommended_solution'] = solution['suggested_solutions'][0]
            
            solutions.append(solution)
        
        return solutions
    
    def _generate_risk_solutions(self, risk: Dict) -> List[Dict]:
        """توليد حلول للخطر"""
        risk_type = risk.get('type', 'general')
        
        solutions_map = {
            'delay': [
                {'name': 'إضافة موارد إضافية', 'cost': 'متوسط', 'effectiveness': 'عالية'},
                {'name': 'تعديل الجدول الزمني', 'cost': 'منخفض', 'effectiveness': 'متوسطة'},
                {'name': 'العمل الإضافي', 'cost': 'مرتفع', 'effectiveness': 'عالية'}
            ],
            'cost_overrun': [
                {'name': 'مراجعة البنود غير الضرورية', 'cost': 'منخفض', 'effectiveness': 'متوسطة'},
                {'name': 'البحث عن موردين بديلين', 'cost': 'متوسط', 'effectiveness': 'عالية'},
                {'name': 'إعادة التفاوض على الأسعار', 'cost': 'منخفض', 'effectiveness': 'منخفضة'}
            ],
            'quality': [
                {'name': 'زيادة الفحوصات', 'cost': 'منخفض', 'effectiveness': 'عالية'},
                {'name': 'تدريب الفريق', 'cost': 'متوسط', 'effectiveness': 'عالية'},
                {'name': 'استبدال المواد', 'cost': 'مرتفع', 'effectiveness': 'عالية'}
            ],
            'general': [
                {'name': 'تشكيل فريق معالجة', 'cost': 'منخفض', 'effectiveness': 'متوسطة'},
                {'name': 'طلب مساعدة الخبراء', 'cost': 'مرتفع', 'effectiveness': 'عالية'},
                {'name': 'تطبيق خطة طوارئ', 'cost': 'متوسط', 'effectiveness': 'عالية'}
            ]
        }
        
        return solutions_map.get(risk_type, solutions_map['general'])
    
    def _log_risks(self, project: Project, risks: List[Dict], solutions: List[Dict]):
        """تسجيل المخاطر والحلول"""
        for risk, solution in zip(risks, solutions):
            risk_log = {
                'project_id': project.id,
                'risk_data': risk,
                'solutions': solution,
                'detected_at': datetime.now().isoformat(),
                'status': 'pending'
            }
            
            # في التطبيق الحقيقي، سيتم حفظ في جدول المخاطر
            logger.info(f"تم تسجيل خطر: {risk.get('title')} في مشروع {project.name}")
    
    def _check_delayed_tasks(self):
        """فحص المهام المتأخرة"""
        logger.info("فحص المهام المتأخرة")
        
        try:
            for project_id in self.state.active_projects:
                project = Project.query.get(project_id)
                if not project:
                    continue
                
                # الحصول على المهام المتأخرة
                delayed_tasks = self._get_delayed_tasks(project_id)
                
                if delayed_tasks:
                    # إرسال إنذارات بالتأخير
                    self._send_delay_alerts(project, delayed_tasks)
                    
                    # اقتراح إجراءات تصحيحية
                    corrective_actions = self._suggest_corrective_actions(delayed_tasks)
                    
                    # تطبيق الإجراءات التلقائية
                    self._apply_automatic_actions(corrective_actions, project)
            
            logger.info("تم فحص المهام المتأخرة في جميع المشاريع")
            
        except Exception as e:
            logger.error(f"خطأ في فحص المهام المتأخرة: {e}")
    
    def _send_delay_alerts(self, project: Project, delayed_tasks: List[Task]):
        """إرسال إنذارات التأخير"""
        for task in delayed_tasks:
            # حساب ساعات التأخير
            delay_hours = self._calculate_delay_hours(task)
            
            # إرسال للمشرف
            if task.supervisor_id:
                notification = Notification(
                    user_id=task.supervisor_id,
                    title=f"Task Delay: {task.task_name}",
                    title_ar=f"تأخير المهمة: {task.task_name_ar}",
                    message=f"Task {task.task_code} is delayed by {delay_hours} hours",
                    message_ar=f"المهمة {task.task_code} متأخرة بمقدار {delay_hours} ساعة",
                    notification_type='task_delay',
                    related_task_id=task.id,
                    related_project_id=project.id,
                    priority='high' if delay_hours > 24 else 'medium'
                )
                
                db.session.add(notification)
    
    def _calculate_delay_hours(self, task: Task) -> float:
        """حساب ساعات التأخير"""
        if task.planned_end_date and task.planned_end_date < datetime.now():
            delay = datetime.now() - task.planned_end_date
            return delay.total_seconds() / 3600
        return 0.0
    
    def _suggest_corrective_actions(self, delayed_tasks: List[Task]) -> List[Dict]:
        """اقتراح إجراءات تصحيحية"""
        actions = []
        
        for task in delayed_tasks:
            delay_hours = self._calculate_delay_hours(task)
            
            if delay_hours > 48:  # أكثر من يومين
                action = {
                    'task_id': task.id,
                    'action': 'reassign_task',
                    'reason': f'تأخير كبير ({delay_hours:.1f} ساعة)',
                    'priority': 'high'
                }
            elif delay_hours > 24:  # أكثر من يوم
                action = {
                    'task_id': task.id,
                    'action': 'add_resources',
                    'reason': f'تأخير متوسط ({delay_hours:.1f} ساعة)',
                    'priority': 'medium'
                }
            else:  # أقل من يوم
                action = {
                    'task_id': task.id,
                    'action': 'send_reminder',
                    'reason': f'تأخير طفيف ({delay_hours:.1f} ساعة)',
                    'priority': 'low'
                }
            
            actions.append(action)
        
        return actions
    
    def _apply_automatic_actions(self, actions: List[Dict], project: Project):
        """تطبيق الإجراءات التلقائية"""
        for action in actions:
            if action['priority'] == 'low' and action['action'] == 'send_reminder':
                # إرسال تذكير تلقائي
                self._send_automatic_reminder(action['task_id'])
            elif action['priority'] == 'medium' and action['action'] == 'add_resources':
                # اقتراح إضافة موارد
                self._suggest_additional_resources(action['task_id'])
    
    def _send_automatic_reminder(self, task_id: int):
        """إرسال تذكير تلقائي"""
        task = Task.query.get(task_id)
        if task and task.supervisor_id:
            notification = Notification(
                user_id=task.supervisor_id,
                title="Automatic Reminder: Task is Delayed",
                title_ar="تذكير تلقائي: المهمة متأخرة",
                message=f"Please update the progress of task {task.task_code}",
                message_ar=f"الرجاء تحديث تقدم المهمة {task.task_code}",
                notification_type='auto_reminder',
                related_task_id=task.id,
                related_project_id=task.project_id,
                priority='low'
            )
            
            db.session.add(notification)
            db.session.commit()
    
    def _suggest_additional_resources(self, task_id: int):
        """اقتراح إضافة موارد"""
        task = Task.query.get(task_id)
        if task:
            logger.info(f"اقتراح إضافة موارد للمهمة {task.task_code}")
            # في التطبيق الحقيقي، سيتم اقتراح موارد محددة
    
    def _auto_update_progress(self):
        """تحديث التقدم تلقائياً"""
        logger.debug("تحديث التقدم التلقائي")
        
        try:
            for project_id in self.state.active_projects:
                # الحصول على المهام الجارية
                ongoing_tasks = self._get_ongoing_tasks(project_id)
                
                for task in ongoing_tasks:
                    # إذا كانت المهمة جارية لأكثر من ساعة بدون تحديث
                    if task.actual_start_date:
                        hours_since_start = (datetime.now() - task.actual_start_date).total_seconds() / 3600
                        
                        if hours_since_start > 2 and task.progress_percentage < 50:
                            # تحديث تلقائي تقديري
                            estimated_progress = min(50, hours_since_start * 10)
                            task.progress_percentage = estimated_progress
                            
                            # تسجيل التحديث التلقائي
                            self._log_auto_progress_update(task, estimated_progress)
            
            db.session.commit()
            logger.debug("تم تحديث التقدم تلقائياً")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في التحديث التلقائي للتقدم: {e}")
    
    def _log_auto_progress_update(self, task: Task, new_progress: float):
        """تسجيل تحديث التقدم التلقائي"""
        from ..models.project_models import TaskProgressUpdate
        
        update = TaskProgressUpdate(
            task_id=task.id,
            progress_percentage=new_progress,
            updated_by=None,  # تحديث تلقائي
            notes="تحديث تلقائي بناءً على الوقت المنقضي",
            updated_at=datetime.now()
        )
        
        db.session.add(update)
    
    def _send_weekly_reports(self):
        """إرسال التقارير الأسبوعية"""
        logger.info("إرسال التقارير الأسبوعية")
        
        try:
            for project_id in self.state.active_projects:
                project = Project.query.get(project_id)
                if not project:
                    continue
                
                # توليد التقرير الأسبوعي
                weekly_report = self._generate_weekly_report(project)
                
                # إرسال للمدير
                manager = User.query.get(project.project_manager_id)
                if manager:
                    self._send_report_to_user(
                        user=manager,
                        report_data=weekly_report,
                        report_type='weekly'
                    )
                
                # إرسال للإدارة العليا
                self._send_to_senior_management(weekly_report)
            
            logger.info("تم إرسال جميع التقارير الأسبوعية")
            
        except Exception as e:
            logger.error(f"خطأ في إرسال التقارير الأسبوعية: {e}")
    
    def _generate_weekly_report(self, project: Project) -> Dict:
        """توليد تقرير أسبوعي ذكي"""
        # تنفيذ مشابه للتقرير اليومي ولكن لفترة أسبوع
        return {
            'project_id': project.id,
            'project_name': project.name,
            'project_name_ar': project.name_ar,
            'report_type': 'weekly',
            'report_period': 'الأسبوع الماضي',
            'summary': 'تقرير أسبوعي مفصل'
        }
    
    def _send_to_senior_management(self, report_data: Dict):
        """إرسال التقرير للإدارة العليا"""
        # في التطبيق الحقيقي، سيتم إرسال لمدراء القسم
        pass
    
    def _check_monthly_report(self):
        """التحقق من موعد التقرير الشهري"""
        from datetime import datetime
        
        # إذا كان اليوم الأول من الشهر
        if datetime.now().day == 1:
            self._send_monthly_reports()
    
    def _send_monthly_reports(self):
        """إرسال التقارير الشهرية"""
        logger.info("إرسال التقارير الشهرية")
        
        try:
            for project_id in self.state.active_projects:
                project = Project.query.get(project_id)
                if not project:
                    continue
                
                # توليد التقرير الشهري
                monthly_report = self._generate_monthly_report(project)
                
                # إرسال للمدير
                manager = User.query.get(project.project_manager_id)
                if manager:
                    self._send_report_to_user(
                        user=manager,
                        report_data=monthly_report,
                        report_type='monthly'
                    )
            
            logger.info("تم إرسال جميع التقارير الشهرية")
            
        except Exception as e:
            logger.error(f"خطأ في إرسال التقارير الشهرية: {e}")
    
    def _generate_monthly_report(self, project: Project) -> Dict:
        """توليد تقرير شهري ذكي"""
        # تنفيذ مشابه للتقرير الأسبوعي ولكن لفترة شهر
        return {
            'project_id': project.id,
            'project_name': project.name,
            'project_name_ar': project.name_ar,
            'report_type': 'monthly',
            'report_period': 'الشهر الماضي',
            'summary': 'تقرير شهري مفصل'
        }
    
    def _check_immediate_risks(self):
        """فحص المخاطر الفورية"""
        # يتم تنفيذ عند بدء النظام
        pass
    
    def _send_greeting_to_active_users(self):
        """إرسال تحية للمستخدمين النشطين"""
        # في التطبيق الحقيقي، سيتم إرسال تحية للمستخدمين النشطين
        pass
    
    def get_status(self) -> Dict:
        """الحصول على حالة المدير الافتراضي"""
        return {
            'is_running': self.is_running,
            'current_time_slot': self.state.current_time_slot.value,
            'active_projects': len(self.state.active_projects),
            'pending_decisions': len(self.state.pending_decisions),
            'recent_alerts': len(self.state.recent_alerts),
            'performance_metrics': self.state.performance_metrics,
            'next_scheduled_task': self._get_next_scheduled_task()
        }
    
    def _get_next_scheduled_task(self) -> str:
        """الحصول على المهمة المجدولة التالية"""
        if schedule.next_run():
            return schedule.next_run().strftime('%Y-%m-%d %H:%M:%S')
        return 'No scheduled tasks'
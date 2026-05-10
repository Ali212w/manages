"""
smart_scheduler.py - نظام الجدولة الذكية وإدارة المهام التلقائية
"""
from datetime import datetime, date, timedelta
from app.extensions import db
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import current_app
from app.models import  Task, User, Project, Notification, TaskAssignment
import logging
from sqlalchemy import func

class SmartProjectManager:
    """المدير الذكي للمشاريع - يعمل تلقائياً دون تدخل بشري"""
    
    def __init__(self, app=None):
        self.scheduler = BackgroundScheduler(timezone='Asia/Riyadh')
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """تهيئة المدير الذكي مع التطبيق"""
        with app.app_context():
            # جدولة المهام الذكية
            self.scheduler.add_job(
                func=self.check_tasks_status,
                trigger=CronTrigger(minute='*/15'),  # كل 15 دقيقة
                id='check_tasks_status',
                name='فحص حالة المهام',
                replace_existing=True
            )
            
            self.scheduler.add_job(
                func=self.send_task_reminders,
                trigger=CronTrigger(hour='8,12,16', minute='0'),  # 8 صباحاً، 12 ظهراً، 4 عصراً
                id='send_task_reminders',
                name='إرسال تذكيرات المهام',
                replace_existing=True
            )
            
            self.scheduler.add_job(
                func=self.check_overdue_tasks,
                trigger=CronTrigger(hour='*', minute='0'),  # كل ساعة
                id='check_overdue_tasks',
                name='فحص المهام المتأخرة',
                replace_existing=True
            )
            
            self.scheduler.add_job(
                func=self.generate_recommendations,
                trigger=CronTrigger(hour='6', minute='0'),  # كل يوم 6 صباحاً
                id='generate_recommendations',
                name='توليد توصيات ذكية',
                replace_existing=True
            )
            
            self.scheduler.add_job(
                func=self.auto_assign_tasks,
                trigger=CronTrigger(day_of_week='sun', hour='1', minute='0'),  # كل أحد 1 صباحاً
                id='auto_assign_tasks',
                name='التعيين التلقائي للمهام',
                replace_existing=True
            )
            
            self.scheduler.add_job(
                func=self.check_resource_allocation,
                trigger=CronTrigger(hour='9,15', minute='30'),  # 9:30 صباحاً و 3:30 عصراً
                id='check_resource_allocation',
                name='فحص توزيع الموارد',
                replace_existing=True
            )
            
            self.scheduler.add_job(
                func=self.analyze_performance,
                trigger=CronTrigger(day_of_week='mon', hour='5', minute='0'),  # كل اثنين 5 صباحاً
                id='analyze_performance',
                name='تحليل الأداء',
                replace_existing=True
            )
            
            self.scheduler.start()
            app.logger.info("✅ المدير الذكي للمشاريع بدأ العمل بنجاح")
    
    # ============================================
    # 1. فحص حالة المهام تلقائياً
    # ============================================
    
    def check_tasks_status(self):
        """فحص جميع المهام وتحديث حالتها تلقائياً"""
        with self.app.app_context():
            try:
                today = date.today()
                
                # المهام التي يجب أن تبدأ اليوم
                tasks_to_start = Task.query.filter(
                    Task.status == 'pending',
                    Task.planned_start_date <= today
                ).all()
                
                for task in tasks_to_start:
                    self._auto_start_task(task)
                
                # المهام التي اقترب موعدها (تذكير قبل 3 أيام)
                upcoming_tasks = Task.query.filter(
                    Task.status == 'pending',
                    Task.planned_start_date <= today + timedelta(days=3),
                    Task.planned_start_date > today
                ).all()
                
                for task in upcoming_tasks:
                    self._send_upcoming_reminder(task)
                
                # المهام التي تجاوزت موعدها
                overdue_tasks = Task.query.filter(
                    Task.status.in_(['pending', 'in_progress']),
                    Task.planned_end_date < today
                ).all()
                
                for task in overdue_tasks:
                    self._handle_overdue_task(task)
                
                self.app.logger.info(f"✅ فحص المهام: {len(tasks_to_start)} بدأت، {len(upcoming_tasks)} قادمة، {len(overdue_tasks)} متأخرة")
                
            except Exception as e:
                self.app.logger.error(f"❌ خطأ في فحص المهام: {str(e)}")
    
    def _auto_start_task(self, task):
        """بدء المهمة تلقائياً إذا كان وقتها قد حان"""
        if task.status == 'pending':
            task.status = 'in_progress'
            task.actual_start_date = datetime.utcnow()
            task.progress_percentage = 1
            
            # إشعار للمسؤول
            self._send_notification(
                user_id=task.delegate_id or task.supervisor_id,
                title=f'🚀 بدء تلقائي للمهمة: {task.task_name}',
                message=f'تم بدء المهمة {task.task_code} تلقائياً حسب الجدول الزمني',
                task=task,
                notification_type='task_auto_started'
            )
            
            db.session.commit()
    
    def _send_upcoming_reminder(self, task):
        """إرسال تذكير بمهمة قادمة"""
        days_until = (task.planned_start_date - date.today()).days
        self._send_notification(
            user_id=task.delegate_id or task.supervisor_id,
            title=f'⏰ تذكير: مهمة بعد {days_until} أيام',
            message=f'المهمة {task.task_code} - {task.task_name} ستبدأ بعد {days_until} أيام',
            task=task,
            notification_type='task_upcoming'
        )
    
    def _handle_overdue_task(self, task):
        """معالجة المهمة المتأخرة"""
        delay_days = (date.today() - task.planned_end_date).days
        
        # إشعار للمسؤول
        self._send_notification(
            user_id=task.delegate_id or task.supervisor_id,
            title=f'⚠️ مهمة متأخرة: {task.task_name}',
            message=f'المهمة {task.task_code} متأخرة {delay_days} أيام',
            task=task,
            notification_type='task_overdue',
            priority='high'
        )
        
        # إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != (task.delegate_id or task.supervisor_id):
            self._send_notification(
                user_id=task.supervisor_id,
                title=f'⚠️ تنبيه: مهمة متأخرة',
                message=f'المهمة {task.task_code} - {task.task_name} متأخرة {delay_days} أيام',
                task=task,
                notification_type='task_overdue_supervisor',
                priority='high'
            )
        
        # إذا كان التأخير كبيراً (أكثر من 5 أيام)، أرسل للمدير
        if delay_days >= 5 and task.project:
            self._send_notification(
                user_id=task.project.project_manager_id,
                title=f'🚨 تأخير كبير في المشروع: {task.project.name}',
                message=f'المهمة {task.task_code} - {task.task_name} متأخرة {delay_days} أيام',
                task=task,
                notification_type='critical_delay',
                priority='critical'
            )
    
    # ============================================
    # 2. إرسال تذكيرات ذكية
    # ============================================
    
    def send_task_reminders(self):
        """إرسال تذكيرات ذكية للمستخدمين بناءً على أولويات المهام"""
        with self.app.app_context():
            try:
                today = date.today()
                
                # تذكيرات للمهام التي ستبدأ غداً
                tomorrow_tasks = Task.query.filter(
                    Task.status == 'pending',
                    Task.planned_start_date == today + timedelta(days=1)
                ).all()
                
                for task in tomorrow_tasks:
                    self._send_reminder(task, 'tomorrow')
                
                # تذكيرات للمهام التي ستنتهي غداً
                tomorrow_deadlines = Task.query.filter(
                    Task.status.in_(['pending', 'in_progress']),
                    Task.planned_end_date == today + timedelta(days=1)
                ).all()
                
                for task in tomorrow_deadlines:
                    self._send_reminder(task, 'deadline_tomorrow')
                
                # تذكيرات أسبوعية للمهام البعيدة
                if today.weekday() == 6:  # الأحد
                    weekly_tasks = Task.query.filter(
                        Task.status.in_(['pending', 'in_progress']),
                        Task.planned_start_date <= today + timedelta(days=7)
                    ).all()
                    
                    for task in weekly_tasks:
                        self._send_reminder(task, 'weekly')
                
                self.app.logger.info(f"✅ تم إرسال {len(tomorrow_tasks) + len(tomorrow_deadlines)} تذكير")
                
            except Exception as e:
                self.app.logger.error(f"❌ خطأ في إرسال التذكيرات: {str(e)}")
    
    def _send_reminder(self, task, reminder_type):
        """إرسال تذكير محدد حسب نوعه"""
        messages = {
            'tomorrow': {
                'title': f'📅 مهمة تبدأ غداً: {task.task_name}',
                'message': f'المهمة {task.task_code} ستبدأ غداً. يرجى التحضير.',
                'priority': 'medium'
            },
            'deadline_tomorrow': {
                'title': f'⏳ مهمة تنتهي غداً: {task.task_name}',
                'message': f'الموعد النهائي للمهمة {task.task_code} غداً. التقدم الحالي: {task.progress_percentage}%',
                'priority': 'high'
            },
            'weekly': {
                'title': f'📋 ملخص أسبوعي: {task.task_name}',
                'message': f'مهمة {task.task_code} - الحالة: {task.status} - التقدم: {task.progress_percentage}%',
                'priority': 'low'
            }
        }
        
        msg = messages.get(reminder_type, messages['weekly'])
        
        self._send_notification(
            user_id=task.delegate_id or task.supervisor_id,
            title=msg['title'],
            message=msg['message'],
            task=task,
            notification_type=f'task_reminder_{reminder_type}',
            priority=msg['priority']
        )
    
    # ============================================
    # 3. فحص المهام المتأخرة وإرسال تنبيهات تصعيدية
    # ============================================
    
    def check_overdue_tasks(self):
        """فحص المهام المتأخرة وإرسال تنبيهات تصعيدية حسب درجة التأخير"""
        with self.app.app_context():
            try:
                today = date.today()
                
                # مستويات التأخير المختلفة
                overdue_levels = {
                    1: {'days': 1, 'action': 'remind'},
                    2: {'days': 3, 'action': 'escalate_supervisor'},
                    3: {'days': 7, 'action': 'escalate_manager'},
                    4: {'days': 14, 'action': 'escalate_owner'}
                }
                
                for level, config in overdue_levels.items():
                    tasks = Task.query.filter(
                        Task.status.in_(['pending', 'in_progress']),
                        Task.planned_end_date <= today - timedelta(days=config['days'])
                    ).all()
                    
                    for task in tasks:
                        self._escalate_overdue_task(task, config['action'], config['days'])
                
                self.app.logger.info("✅ تم فحص المهام المتأخرة")
                
            except Exception as e:
                self.app.logger.error(f"❌ خطأ في فحص المهام المتأخرة: {str(e)}")
    
    def _escalate_overdue_task(self, task, action, days):
        """تصعيد المهمة المتأخرة حسب مستوى التأخير"""
        if action == 'remind':
            self._send_notification(
                user_id=task.delegate_id or task.supervisor_id,
                title=f'⏰ تذكير: مهمة متأخرة يوم',
                message=f'المهمة {task.task_code} متأخرة يوم واحد. يرجى الإسراع.',
                task=task,
                notification_type='task_overdue_1d',
                priority='high'
            )
        
        elif action == 'escalate_supervisor':
            self._send_notification(
                user_id=task.supervisor_id,
                title=f'⚠️ تصعيد: مهمة متأخرة 3 أيام',
                message=f'المهمة {task.task_code} - {task.task_name} متأخرة 3 أيام. يرجى التدخل.',
                task=task,
                notification_type='task_overdue_3d',
                priority='critical'
            )
            
            # تذكير المنفذ أيضاً
            if task.delegate_id and task.delegate_id != task.supervisor_id:
                self._send_notification(
                    user_id=task.delegate_id,
                    title=f'⚠️ تنبيه: مهمتك متأخرة 3 أيام',
                    message=f'المهمة {task.task_code} متأخرة 3 أيام. المشرف على علم.',
                    task=task,
                    notification_type='task_overdue_3d_executor',
                    priority='high'
                )
        
        elif action == 'escalate_manager':
            # إشعار لمدير المشروع
            if task.project and task.project.project_manager_id:
                self._send_notification(
                    user_id=task.project.project_manager_id,
                    title=f'🚨 تأخير كبير في المشروع: {task.project.name}',
                    message=f'المهمة {task.task_code} متأخرة أسبوع. يرجى التدخل العاجل.',
                    task=task,
                    notification_type='task_overdue_7d',
                    priority='critical'
                )
        
        elif action == 'escalate_owner':
            # إشعار لمالك المنصة أو المدير العام
            if task.project and task.project.org_id:
                admins = User.query.filter_by(
                    org_id=task.project.org_id,
                    role='org_admin'
                ).all()
                
                for admin in admins:
                    self._send_notification(
                        user_id=admin.id,
                        title=f'🔥 تأخير حرج في المشروع: {task.project.name}',
                        message=f'المهمة {task.task_code} متأخرة {days} يوم. هذا تأخير حرج.',
                        task=task,
                        notification_type='task_overdue_14d',
                        priority='critical'
                    )
    
    # ============================================
    # 4. توليد توصيات ذكية للإدارة
    # ============================================
    
    def generate_recommendations(self):
        """توليد توصيات ذكية للإدارة بناءً على تحليل البيانات"""
        with self.app.app_context():
            try:
                recommendations = []
                
                # تحليل أداء المشاريع
                projects = Project.query.filter_by(status='active').all()
                for project in projects:
                    recs = self._analyze_project_performance(project)
                    recommendations.extend(recs)
                
                # تحليل أداء المستخدمين
                top_performers = self._find_top_performers()
                low_performers = self._find_low_performers()
                
                # توليد توصيات للمستخدمين
                for user, score in low_performers:
                    recommendations.append({
                        'type': 'performance_warning',
                        'user_id': user.id,
                        'title': f'⚠️ تنبيه أداء: {user.full_name}',
                        'message': f'أداء {user.full_name} أقل من المتوسط. نسبة الإنجاز: {score}%',
                        'priority': 'medium'
                    })
                
                for user, score in top_performers[:3]:
                    recommendations.append({
                        'type': 'performance_praise',
                        'user_id': user.id,
                        'title': f'🌟 أداء متميز: {user.full_name}',
                        'message': f'{user.full_name} من أفضل المنفذين! نسبة الإنجاز: {score}%',
                        'priority': 'low'
                    })
                
                # حفظ التوصيات وإرسالها
                self._save_recommendations(recommendations)
                
                self.app.logger.info(f"✅ تم توليد {len(recommendations)} توصية ذكية")
                
            except Exception as e:
                self.app.logger.error(f"❌ خطأ في توليد التوصيات: {str(e)}")
    
    def _analyze_project_performance(self, project):
        """تحليل أداء المشروع وتوليد توصيات"""
        recommendations = []
        tasks = Task.query.filter_by(project_id=project.id).all()
        
        if not tasks:
            return recommendations
        
        # حساب إحصائيات المشروع
        total_tasks = len(tasks)
        completed = len([t for t in tasks if t.status == 'completed'])
        in_progress = len([t for t in tasks if t.status == 'in_progress'])
        delayed = len([t for t in tasks if t.is_delayed()])
        
        completion_rate = (completed / total_tasks * 100) if total_tasks > 0 else 0
        
        # توصيات بناءً على النتائج
        if delayed > total_tasks * 0.3:
            recommendations.append({
                'type': 'project_delay_warning',
                'project_id': project.id,
                'title': f'⚠️ مشروع {project.name} يعاني من تأخيرات',
                'message': f'نسبة التأخير {delayed}/{total_tasks} مهمة ({delayed/total_tasks*100:.0f}%). يوصى بمراجعة خطة العمل.',
                'priority': 'high'
            })
        
        if completion_rate < 30 and project.planned_end_date - date.today() < timedelta(days=30):
            recommendations.append({
                'type': 'project_risk_warning',
                'project_id': project.id,
                'title': f'🚨 مشروع {project.name} معرض للخطر',
                'message': f'نسبة الإنجاز {completion_rate:.0f}% فقط ويتبقى أقل من شهر.',
                'priority': 'critical'
            })
        
        if in_progress == 0 and completed < total_tasks:
            recommendations.append({
                'type': 'project_stagnation',
                'project_id': project.id,
                'title': f'💤 مشروع {project.name} متوقف',
                'message': 'لا توجد مهام قيد التنفيذ حالياً. يوصى بتوزيع مهام جديدة.',
                'priority': 'medium'
            })
        
        return recommendations
    
    def _find_top_performers(self):
        """العثور على أفضل المنفذين"""
        from sqlalchemy import func
        
        performers = db.session.query(
            User,
            func.avg(TaskAssignment.quality_rating).label('avg_quality'),
            func.count(Task.id).label('tasks_count')
        ).join(TaskAssignment, User.id == TaskAssignment.user_id)\
         .join(Task, TaskAssignment.task_id == Task.id)\
         .filter(Task.status == 'completed')\
         .group_by(User.id)\
         .having(func.count(Task.id) >= 5)\
         .all()
        
        scored = [(p[0], (p[1] or 0) * 20 + p[2]) for p in performers]
        return sorted(scored, key=lambda x: x[1], reverse=True)
    
    def _find_low_performers(self):
        """العثور على أقل المنفذين أداءً"""
        from sqlalchemy import func
        
        performers = db.session.query(
            User,
            func.avg(TaskAssignment.quality_rating).label('avg_quality'),
            func.avg(Task.progress_percentage).label('avg_progress')
        ).join(TaskAssignment, User.id == TaskAssignment.user_id)\
         .join(Task, TaskAssignment.task_id == Task.id)\
         .filter(Task.status != 'completed')\
         .group_by(User.id)\
         .all()
        
        low_performers = []
        for user, avg_quality, avg_progress in performers:
            if (avg_quality or 0) < 3 or (avg_progress or 0) < 30:
                score = ((avg_quality or 0) * 20 + (avg_progress or 0)) / 2
                low_performers.append((user, score))
        
        return sorted(low_performers, key=lambda x: x[1])
    
    def _save_recommendations(self, recommendations):
        """حفظ التوصيات وإرسالها للمعنيين"""
        for rec in recommendations:
            if rec['type'] in ['performance_praise', 'performance_warning']:
                # إرسال للمستخدم نفسه
                self._send_notification(
                    user_id=rec['user_id'],
                    title=rec['title'],
                    message=rec['message'],
                    notification_type=rec['type'],
                    priority=rec['priority']
                )
            
            elif rec['type'] in ['project_delay_warning', 'project_risk_warning', 'project_stagnation']:
                # إرسال لمدير المشروع
                project = Project.query.get(rec['project_id'])
                if project and project.project_manager_id:
                    self._send_notification(
                        user_id=project.project_manager_id,
                        title=rec['title'],
                        message=rec['message'],
                        notification_type=rec['type'],
                        priority=rec['priority'],
                        project_id=project.id
                    )
                
                # إرسال للمدير العام
                admins = User.query.filter_by(org_id=project.org_id, role='org_admin').all()
                for admin in admins:
                    if admin.id != project.project_manager_id:
                        self._send_notification(
                            user_id=admin.id,
                            title=f'📊 تقرير إداري: {rec["title"]}',
                            message=rec['message'],
                            notification_type=rec['type'],
                            priority=rec['priority'],
                            project_id=project.id
                        )
    
    # ============================================
    # 5. التعيين التلقائي للمهام
    # ============================================
    
    def auto_assign_tasks(self):
        """تعيين المهام تلقائياً للمستخدمين المناسبين"""
        with self.app.app_context():
            try:
                # المهام غير المعينة
                unassigned_tasks = Task.query.filter(
                    Task.delegate_id == None,
                    Task.status == 'pending'
                ).all()
                
                for task in unassigned_tasks:
                    best_user = self._find_best_user_for_task(task)
                    if best_user:
                        task.delegate_id = best_user.id
                        
                        # إشعار للمستخدم
                        self._send_notification(
                            user_id=best_user.id,
                            title=f'📋 مهمة جديدة: {task.task_name}',
                            message=f'تم تعيينك تلقائياً للمهمة {task.task_code} بناءً على كفاءتك',
                            task=task,
                            notification_type='task_auto_assigned'
                        )
                        
                        db.session.commit()
                
                self.app.logger.info(f"✅ تم تعيين {len(unassigned_tasks)} مهمة تلقائياً")
                
            except Exception as e:
                self.app.logger.error(f"❌ خطأ في التعيين التلقائي: {str(e)}")
    
    def _find_best_user_for_task(self, task):
        """العثور على أفضل مستخدم للمهمة بناءً على عدة عوامل"""
        from sqlalchemy import func
        
        # المستخدمون المتاحون في نفس القسم أو المشروع
        users = User.query.filter_by(
            org_id=task.project.org_id if task.project else None,
            is_user_active=True
        ).all()
        
        if not users:
            return None
        
        scored_users = []
        for user in users:
            score = 0
            
            # 1. المهارات المطلوبة (وزن كبير)
            if task.required_skills and user.skills:
                common_skills = set(task.required_skills) & set(user.skills)
                score += len(common_skills) * 10
            
            # 2. أداء سابق في مهام مماثلة
            previous_tasks = TaskAssignment.query.filter_by(
                user_id=user.id
            ).all()
            
            if previous_tasks:
                avg_quality = sum([t.quality_rating or 0 for t in previous_tasks]) / len(previous_tasks)
                score += avg_quality * 5
                
                completion_rate = len([t for t in previous_tasks if t.status == 'completed']) / len(previous_tasks) * 100
                score += completion_rate / 10
            
            # 3. عبء العمل الحالي (كلما قل العبء، زادت النقاط)
            current_tasks = TaskAssignment.query.filter_by(
                user_id=user.id,
                status= TaskAssignment.status.in_(['assigned', 'accepted', 'in_progress'])
            ).count()
            
            score -= current_tasks * 5  # نقاط سلبية لكل مهمة حالية
            
            scored_users.append((user, score))
        
        # اختيار أفضل مستخدم
        scored_users.sort(key=lambda x: x[1], reverse=True)
        return scored_users[0][0] if scored_users else None
    
    # ============================================
    # 6. فحص توزيع الموارد
    # ============================================
    
    def check_resource_allocation(self):
        """فحص توزيع الموارد وتقديم توصيات"""
        with self.app.app_context():
            try:
                users = User.query.filter_by(is_user_active=True).all()
                
                for user in users:
                    # عدد المهام الحالية
                    current_tasks = TaskAssignment.query.filter_by(
                        user_id=user.id,
                       status= TaskAssignment.status.in_(['assigned', 'accepted', 'in_progress'])
                    ).count()
                    
                    if current_tasks > 5:
                        # تحذير من زيادة العبء
                        self._send_notification(
                            user_id=user.id,
                            title=f'⚠️ عبء عمل مرتفع',
                            message=f'لديك {current_tasks} مهام حالياً. قد يؤثر ذلك على جودة العمل.',
                            notification_type='workload_warning',
                            priority='medium'
                        )
                        
                        # إشعار للمشرفين
                        if user.supervised_tasks:
                            for task in user.supervised_tasks[:1]:
                                if task.supervisor_id:
                                    self._send_notification(
                                        user_id=task.supervisor_id,
                                        title=f'📊 تنبيه إداري: عبء عمل {user.full_name}',
                                        message=f'{user.full_name} لديه {current_tasks} مهام. يوصى بإعادة توزيع.',
                                        notification_type='workload_alert',
                                        priority='medium'
                                    )
                    
                    elif current_tasks == 0:
                        # تنبيه بعدم وجود مهام
                        self._send_notification(
                            user_id=user.id,
                            title=f'💤 لا توجد مهام',
                            message='ليس لديك أي مهام حالياً. يرجى التواصل مع المشرف.',
                            notification_type='no_tasks_warning',
                            priority='low'
                        )
                
                self.app.logger.info("✅ تم فحص توزيع الموارد")
                
            except Exception as e:
                self.app.logger.error(f"❌ خطأ في فحص الموارد: {str(e)}")
    
    # ============================================
    # 7. تحليل الأداء الأسبوعي
    # ============================================
    
    def analyze_performance(self):
        """تحليل أداء الفريق وتقديم تقرير أسبوعي"""
        with self.app.app_context():
            try:
                last_week = date.today() - timedelta(days=7)
                
                # إحصائيات الأسبوع
                stats = {
                    'completed_tasks': Task.query.filter(
                        Task.status == 'completed',
                        Task.updated_at >= last_week
                    ).count(),
                    'new_tasks': Task.query.filter(
                        Task.created_at >= last_week
                    ).count(),
                    'overdue_tasks': Task.query.filter(
                        Task.status.in_(['pending', 'in_progress']),
                        Task.planned_end_date < date.today()
                    ).count(),
                    'top_performers': []
                }
                
                # أفضل المنفذين هذا الأسبوع
                top = db.session.query(
                    User,
                    func.count(Task.id).label('completed')
                ).join(Task, Task.delegate_id == User.id)\
                 .filter(
                    Task.status == 'completed',
                    Task.updated_at >= last_week
                ).group_by(User.id)\
                 .order_by(func.count(Task.id).desc())\
                 .limit(5).all()
                
                for user, count in top:
                    stats['top_performers'].append(f"{user.full_name} ({count} مهام)")
                
                # إرسال التقرير للمديرين
                admins = User.query.filter_by(role='org_admin').all()
                for admin in admins:
                    self._send_performance_report(admin, stats)
                
                self.app.logger.info("✅ تم تحليل الأداء الأسبوعي")
                
            except Exception as e:
                self.app.logger.error(f"❌ خطأ في تحليل الأداء: {str(e)}")
    
    def _send_performance_report(self, user, stats):
        """إرسال تقرير الأداء للمستخدم"""
        message = f"""📊 تقرير أداء الأسبوع:
        
✅ مهام مكتملة: {stats['completed_tasks']}
➕ مهام جديدة: {stats['new_tasks']}
⚠️ مهام متأخرة: {stats['overdue_tasks']}

🌟 أفضل المنفذين:
{chr(10).join(['  • ' + p for p in stats['top_performers']])}
        """
        
        self._send_notification(
            user_id=user.id,
            title='📈 تقرير الأداء الأسبوعي',
            message=message,
            notification_type='weekly_report',
            priority='medium'
        )
    
    # ============================================
    # دوال مساعدة
    # ============================================
    
    def _send_notification(self, user_id, title, message, notification_type, 
                          priority='medium', task=None, project_id=None):
        """إرسال إشعار إلى مستخدم"""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            priority=priority,
            created_at=datetime.utcnow()
        )
        
        if task:
            notification.related_task_id = task.id
            notification.related_project_id = task.project_id
        elif project_id:
            notification.related_project_id = project_id
        
        db.session.add(notification)
        db.session.commit()
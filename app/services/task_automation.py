"""
task_automation.py - خدمة أتمتة المهام والتحكم بالتسلسل
"""
from celery import Celery
from datetime import datetime, timedelta
import json
from app.models import db, Task, TaskAssignment, Notification, Project, User

def make_celery(app):
    """إنشاء كائن Celery"""
    celery = Celery(
        app.import_name,
        backend=app.config['REDIS_URL'],
        broker=app.config['REDIS_URL']
    )
    celery.conf.update(app.config)
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

class TaskAutomationService:
    """خدمة أتمتة المهام"""
    
    def __init__(self, app):
        self.app = app
    
    def start_task_automatically(self, task_id, user_id):
        """بدء المهمة تلقائياً"""
        with self.app.app_context():
            try:
                task = Task.query.get(task_id)
                if not task:
                    return False
                
                # التحقق من صلاحية المستخدم
                user = User.query.get(user_id)
                if not user:
                    return False
                
                # بدء المهمة
                if task.start_task():
                    db.session.commit()
                    
                    # تسجيل النشاط
                    self.log_activity(
                        user_id=user_id,
                        action='task_started',
                        details=f'بدأ المهمة {task.task_code}',
                        task_id=task_id,
                        project_id=task.project_id
                    )
                    
                    return True
                
                return False
                
            except Exception as e:
                print(f"خطأ في بدء المهمة تلقائياً: {str(e)}")
                db.session.rollback()
                return False
    
    def complete_task_automatically(self, task_id, user_id, quality='good'):
        """إكمال المهمة تلقائياً"""
        with self.app.app_context():
            try:
                task = Task.query.get(task_id)
                if not task:
                    return False
                
                # إكمال المهمة
                if task.complete_task(quality=quality):
                    db.session.commit()
                    
                    # تسجيل النشاط
                    self.log_activity(
                        user_id=user_id,
                        action='task_completed',
                        details=f'أكمل المهمة {task.task_code}',
                        task_id=task_id,
                        project_id=task.project_id
                    )
                    
                    # بدء المهام التالية
                    self.start_next_tasks(task)
                    
                    return True
                
                return False
                
            except Exception as e:
                print(f"خطأ في إكمال المهمة تلقائياً: {str(e)}")
                db.session.rollback()
                return False
    
    def start_next_tasks(self, completed_task):
        """بدء المهام التالية"""
        with self.app.app_context():
            try:
                for successor in completed_task.successor_tasks:
                    # التحقق من استيفاء جميع الشروط
                    can_start = self.can_start_task(successor)
                    
                    if can_start and successor.status == 'pending':
                        successor.start_task()
                        
                        # إشعار المعنيين
                        self.notify_task_started(successor)
                
                db.session.commit()
                return True
                
            except Exception as e:
                print(f"خطأ في بدء المهام التالية: {str(e)}")
                db.session.rollback()
                return False
    
    def can_start_task(self, task):
        """التحقق من إمكانية بدء المهمة"""
        # التحقق من المهام السابقة
        if task.predecessor:
            if task.predecessor.status != 'completed':
                return False
        
        # التحقق من الموارد
        if not self.check_resources_availability(task):
            return False
        
        # التحقق من التاريخ المخطط
        if task.planned_start_date and task.planned_start_date > datetime.utcnow().date():
            return False
        
        return True
    
    def check_resources_availability(self, task):
        """التحقق من توفر الموارد"""
        # TODO: تنفيذ التحقق من توفر المواد والمعدات والأفراد
        return True
    
    def notify_task_started(self, task):
        """إرسال إشعارات بدء المهمة"""
        try:
            # إشعار المشرف
            if task.supervisor_id:
                notification = Notification(
                    user_id=task.supervisor_id,
                    title=f'بدء المهمة: {task.task_name}',
                    message=f'تم بدء المهمة {task.task_code} تلقائياً',
                    notification_type='task_started_auto',
                    related_task_id=task.id,
                    related_project_id=task.project_id,
                    priority='medium'
                )
                db.session.add(notification)
            
            # إشعار المندوب
            if task.delegate_id:
                notification = Notification(
                    user_id=task.delegate_id,
                    title=f'مهمة جديدة قيد التنفيذ: {task.task_name}',
                    message=f'تم بدء المهمة {task.task_code}، الرجاء متابعتها',
                    notification_type='task_assigned',
                    related_task_id=task.id,
                    related_project_id=task.project_id,
                    priority='high'
                )
                db.session.add(notification)
            
            db.session.commit()
            
        except Exception as e:
            print(f"خطأ في إرسال الإشعارات: {str(e)}")
    
    def log_activity(self, user_id, action, details, task_id=None, project_id=None):
        """تسجيل نشاط النظام"""
        try:
            from uploads.temp.models import AuditLog
            
            audit_log = AuditLog(
                user_id=user_id,
                action=action,
                entity_type='task' if task_id else 'project',
                entity_id=task_id or project_id,
                changes={'details': details},
                timestamp=datetime.utcnow()
            )
            db.session.add(audit_log)
            db.session.commit()
            
        except Exception as e:
            print(f"خطأ في تسجيل النشاط: {str(e)}")
            db.session.rollback()
    
    def generate_task_sequence(self, project_id):
        """توليد تسلسل المهام للمشروع"""
        with self.app.app_context():
            try:
                project = Project.query.get(project_id)
                if not project:
                    return None
                
                # الحصول على جميع المهام
                tasks = Task.query.filter_by(project_id=project_id).all()
                
                # إنشاء تسلسل المهام
                sequence = self.build_task_sequence(tasks)
                
                return sequence
                
            except Exception as e:
                print(f"خطأ في توليد تسلسل المهام: {str(e)}")
                return None
    
    def build_task_sequence(self, tasks):
        """بناء تسلسل المهام"""
        sequence = []
        
        # فرز المهام حسب التبعيات
        task_dict = {task.id: task for task in tasks}
        
        # العثور على المهام البدائية (بدون أسلاف)
        root_tasks = [task for task in tasks if not task.predecessor]
        
        # BFS للعثور على التسلسل
        visited = set()
        queue = root_tasks.copy()
        
        while queue:
            task = queue.pop(0)
            
            if task.id not in visited:
                visited.add(task.id)
                sequence.append({
                    'id': task.id,
                    'code': task.task_code,
                    'name': task.task_name,
                    'status': task.status,
                    'order': task.task_order
                })
                
                # إضافة المهام التالية
                for successor in task.successor_tasks:
                    if successor.id not in visited:
                        queue.append(successor)
        
        return sequence
    
    def calculate_critical_path(self, project_id):
        """حساب المسار الحرج للمشروع"""
        with self.app.app_context():
            try:
                tasks = Task.query.filter_by(project_id=project_id).all()
                
                # حساب أوقات البدء والانتهاء
                task_data = {}
                for task in tasks:
                    task_data[task.id] = {
                        'duration': task.planned_duration or 0,
                        'successors': [s.id for s in task.successor_tasks],
                        'predecessors': [task.predecessor.id] if task.predecessor else []
                    }
                
                # حساب المسار الحرج (CPM)
                critical_path = self.perform_cpm(task_data)
                
                return critical_path
                
            except Exception as e:
                print(f"خطأ في حساب المسار الحرج: {str(e)}")
                return None
    
    def perform_cpm(self, task_data):
        """تنفيذ طريقة المسار الحرج"""
        # حساب أوقات البدء المبكر
        early_start = {}
        early_finish = {}
        
        # البحث عن المهام البدائية
        start_tasks = [task_id for task_id, data in task_data.items() if not data['predecessors']]
        
        for task_id in start_tasks:
            early_start[task_id] = 0
            early_finish[task_id] = task_data[task_id]['duration']
        
        # الانتشار للأمام
        remaining = list(set(task_data.keys()) - set(start_tasks))
        while remaining:
            for task_id in remaining[:]:
                predecessors = task_data[task_id]['predecessors']
                
                # التحقق من توفر جميع أسلاف
                if all(pred in early_finish for pred in predecessors):
                    early_start[task_id] = max(early_finish[pred] for pred in predecessors)
                    early_finish[task_id] = early_start[task_id] + task_data[task_id]['duration']
                    remaining.remove(task_id)
        
        # حساب أوقات البدء المتأخر
        late_finish = {}
        late_start = {}
        
        # البحث عن المهام النهائية
        end_tasks = [task_id for task_id, data in task_data.items() if not data['successors']]
        project_duration = max(early_finish.values())
        
        for task_id in end_tasks:
            late_finish[task_id] = project_duration
            late_start[task_id] = late_finish[task_id] - task_data[task_id]['duration']
        
        # الانتشار للخلف
        remaining = list(set(task_data.keys()) - set(end_tasks))
        while remaining:
            for task_id in remaining[:]:
                successors = task_data[task_id]['successors']
                
                # التحقق من توفر جميع الخلف
                if all(succ in late_start for succ in successors):
                    late_finish[task_id] = min(late_start[succ] for succ in successors)
                    late_start[task_id] = late_finish[task_id] - task_data[task_id]['duration']
                    remaining.remove(task_id)
        
        # تحديد المهام الحرجة
        critical_tasks = []
        for task_id in task_data:
            slack = late_start[task_id] - early_start[task_id]
            if slack == 0:
                critical_tasks.append(task_id)
        
        return {
            'project_duration': project_duration,
            'critical_tasks': critical_tasks,
            'early_start': early_start,
            'early_finish': early_finish,
            'late_start': late_start,
            'late_finish': late_finish
        }
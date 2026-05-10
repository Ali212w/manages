# app/services/smart_dependency_manager.py

"""
نظام إدارة التبعيات الذكي - يراقب العلاقات بين الأنشطة والمهام ويرسل إشعارات تلقائية
"""

from datetime import datetime, timedelta
from app.models import db
from app.models.primavera_models import Activity, ActivityRelationship
from app.models.task_models import Task, TaskDependency
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class SmartDependencyManager:
    """نظام ذكي لإدارة التبعيات بين الأنشطة والمهام"""
    
    def __init__(self):
        self.notification_service = NotificationService()
    
    # ============================================
    # مراقبة تبعيات الأنشطة
    # ============================================
    
    def monitor_activity_dependencies(self):
        """مراقبة تبعيات الأنشطة وإرسال إشعارات عند انتهاء الأنشطة السابقة"""
        try:
            # جلب جميع الأنشطة التي لها أنشطة سابقة
            activities_with_predecessors = db.session.query(
                ActivityRelationship.successor_id
            ).distinct().all()
            
            for (activity_id,) in activities_with_predecessors:
                self.check_activity_dependencies(activity_id)
                
        except Exception as e:
            logger.error(f"خطأ في مراقبة تبعيات الأنشطة: {str(e)}")
    
    def check_activity_dependencies(self, activity_id):
        """التحقق من تبعيات نشاط معين"""
        activity = Activity.query.get(activity_id)
        if not activity or activity.status == 'completed':
            return
        
        # جلب جميع الأنشطة السابقة
        predecessors = ActivityRelationship.query.filter_by(
            successor_id=activity_id
        ).all()
        
        if not predecessors:
            return
        
        # التحقق من اكتمال الأنشطة السابقة
        completed_predecessors = []
        pending_predecessors = []
        
        for pred in predecessors:
            predecessor_activity = Activity.query.get(pred.predecessor_id)
            if predecessor_activity:
                if predecessor_activity.status == 'completed':
                    completed_predecessors.append(predecessor_activity)
                else:
                    pending_predecessors.append(predecessor_activity)
        
        # إذا اكتملت جميع الأنشطة السابقة
        if pending_predecessors:
            # هناك أنشطة سابقة لم تكتمل
            if activity.status == 'not_started':
                self.send_pending_dependencies_notification(activity, pending_predecessors)
        elif completed_predecessors:
            # جميع الأنشطة السابقة اكتملت
            self.notify_activity_ready_to_start(activity, completed_predecessors)
    
    def notify_activity_ready_to_start(self, activity, completed_predecessors):
        """إشعار بأن النشاط جاهز للبدء بعد اكتمال الأنشطة السابقة"""
        # إشعار للمشرف على النشاط
        if activity.supervisor_id:
            self.notification_service.activity_ready_to_start(
                activity=activity,
                completed_predecessors=completed_predecessors,
                receiver_id=activity.supervisor_id,
                role='supervisor'
            )
        
        # إشعار للمنفذ (delegate) إن وجد
        if activity.delegate_id:
            self.notification_service.activity_ready_to_start(
                activity=activity,
                completed_predecessors=completed_predecessors,
                receiver_id=activity.delegate_id,
                role='delegate'
            )
        
        # إشعار لمدير المشروع
        if activity.project and activity.project.project_manager_id:
            self.notification_service.activity_ready_to_start(
                activity=activity,
                completed_predecessors=completed_predecessors,
                receiver_id=activity.project.project_manager_id,
                role='manager'
            )
        
        # إنشاء توصية لبدء النشاط
        self.create_activity_start_recommendation(activity, completed_predecessors)
    
    def send_pending_dependencies_notification(self, activity, pending_predecessors):
        """إشعار بوجود أنشطة سابقة لم تكتمل"""
        # إشعار للمشرف فقط إذا كانت الأنشطة متأخرة
        for pred in pending_predecessors:
            if pred.planned_finish and pred.planned_finish < datetime.now():
                # النشاط السابق متأخر
                self.notification_service.predecessor_activity_delayed(
                    activity=activity,
                    delayed_activity=pred,
                    receiver_id=activity.supervisor_id
                )
    
    def create_activity_start_recommendation(self, activity, completed_predecessors):
        """إنشاء توصية ذكية لبدء النشاط"""
        from app.models.ai_models import AIRecommendation
        
        predecessors_names = [a.activity_name for a in completed_predecessors]
        
        recommendation = AIRecommendation(
            project_id=activity.project_id,
            recommendation_type='activity_start_ready',
            title=f'جاهزية النشاط: {activity.activity_name}',
            title_ar=f'جاهزية النشاط: {activity.activity_name}',
            description=f'اكتملت الأنشطة السابقة: {", ".join(predecessors_names)}. يمكن بدء النشاط الآن.',
            current_state={
                'activity_status': activity.status,
                'predecessors_completed': len(completed_predecessors),
                'planned_start': activity.planned_start.isoformat() if activity.planned_start else None
            },
            recommended_action='بدء تنفيذ النشاط فوراً',
            expected_benefit='المحافظة على الجدول الزمني ومنع التأخير',
            confidence_score=0.95,
            urgency_level='high',
            generated_by='Smart Dependency Manager'
        )
        
        db.session.add(recommendation)
        db.session.commit()
    
    # ============================================
    # مراقبة تبعيات المهام
    # ============================================
    
    def monitor_task_dependencies(self):
        """مراقبة تبعيات المهام وإرسال إشعارات عند انتهاء المهام السابقة"""
        try:
            # جلب جميع المهام التي لها مهام سابقة
            tasks_with_predecessors = db.session.query(
                TaskDependency.successor_task_id
            ).distinct().all()
            
            for (task_id,) in tasks_with_predecessors:
                self.check_task_dependencies(task_id)
                
        except Exception as e:
            logger.error(f"خطأ في مراقبة تبعيات المهام: {str(e)}")
    
    def check_task_dependencies(self, task_id):
        """التحقق من تبعيات مهمة معينة"""
        task = Task.query.get(task_id)
        if not task or task.status == 'completed':
            return
        
        # جلب جميع المهام السابقة
        predecessors = TaskDependency.query.filter_by(
            successor_task_id=task_id
        ).all()
        
        if not predecessors:
            return
        
        # التحقق من اكتمال المهام السابقة
        completed_predecessors = []
        pending_predecessors = []
        
        for pred in predecessors:
            predecessor_task = Task.query.get(pred.predecessor_task_id)
            if predecessor_task:
                if predecessor_task.status == 'completed':
                    completed_predecessors.append(predecessor_task)
                else:
                    pending_predecessors.append(predecessor_task)
        
        # إذا اكتملت جميع المهام السابقة
        if pending_predecessors:
            # هناك مهام سابقة لم تكتمل
            if task.status == 'pending':
                self.send_task_pending_dependencies(task, pending_predecessors)
        elif completed_predecessors:
            # جميع المهام السابقة اكتملت
            self.notify_task_ready_to_start(task, completed_predecessors)
    
    def notify_task_ready_to_start(self, task, completed_predecessors):
        """إشعار بأن المهمة جاهزة للبدء بعد اكتمال المهام السابقة"""
        # إشعار للمنفذ (delegate)
        if task.delegate_id:
            self.notification_service.task_ready_to_start(
                task=task,
                completed_predecessors=completed_predecessors,
                receiver_id=task.delegate_id,
                role='delegate'
            )
        
        # إشعار للمشرف
        if task.supervisor_id and task.supervisor_id != task.delegate_id:
            self.notification_service.task_ready_to_start(
                task=task,
                completed_predecessors=completed_predecessors,
                receiver_id=task.supervisor_id,
                role='supervisor'
            )
        
        # إشعار لمدير المشروع
        if task.project and task.project.project_manager_id:
            self.notification_service.task_ready_to_start(
                task=task,
                completed_predecessors=completed_predecessors,
                receiver_id=task.project.project_manager_id,
                role='manager'
            )
        
        # إنشاء توصية لبدء المهمة
        self.create_task_start_recommendation(task, completed_predecessors)
    
    def send_task_pending_dependencies(self, task, pending_predecessors):
        """إشعار بوجود مهام سابقة لم تكتمل"""
        for pred in pending_predecessors:
            # التحقق من تأخر المهمة السابقة
            if pred.planning and pred.planning.planned_finish:
                if pred.planning.planned_finish < datetime.now().date():
                    # المهمة السابقة متأخرة
                    self.notification_service.predecessor_task_delayed(
                        task=task,
                        delayed_task=pred,
                        receiver_id=task.supervisor_id
                    )
                    
                    # إشعار لمدير المشروع أيضاً
                    if task.project and task.project.project_manager_id:
                        self.notification_service.predecessor_task_delayed(
                            task=task,
                            delayed_task=pred,
                            receiver_id=task.project.project_manager_id
                        )
    
    def create_task_start_recommendation(self, task, completed_predecessors):
        """إنشاء توصية ذكية لبدء المهمة"""
        from app.models.ai_models import AIRecommendation
        
        predecessors_names = [t.task_name for t in completed_predecessors]
        
        recommendation = AIRecommendation(
            project_id=task.project_id,
            recommendation_type='task_start_ready',
            title=f'جاهزية المهمة: {task.task_name}',
            title_ar=f'جاهزية المهمة: {task.task_name}',
            description=f'اكتملت المهام السابقة: {", ".join(predecessors_names)}. يمكن بدء المهمة الآن.',
            current_state={
                'task_status': task.status,
                'predecessors_completed': len(completed_predecessors),
                'planned_start': task.planning.planned_start.isoformat() if task.planning and task.planning.planned_start else None
            },
            recommended_action='بدء تنفيذ المهمة فوراً',
            expected_benefit='المحافظة على الجدول الزمني ومنع التأخير',
            confidence_score=0.95,
            urgency_level='high',
            generated_by='Smart Dependency Manager'
        )
        
        db.session.add(recommendation)
        db.session.commit()
    
    # ============================================
    # مراقبة المسار الحرج (Critical Path)
    # ============================================
    
    def monitor_critical_path(self, project_id):
        """مراقبة الأنشطة على المسار الحرج"""
        from app.models import Activity
        
        # جلب جميع الأنشطة على المسار الحرج
        critical_activities = Activity.query.filter_by(
            project_id=project_id,
            is_critical=True
        ).all()
        
        for activity in critical_activities:
            # التحقق من تأخر أي نشاط حرج
            if activity.status == 'in_progress' and activity.planned_finish:
                if activity.planned_finish < datetime.now():
                    days_delayed = (datetime.now() - activity.planned_finish).days
                    self.notification_service.critical_activity_delayed(activity, days_delayed)
            
            # تذكير قبل موعد انتهاء النشاط الحرج
            elif activity.status != 'completed' and activity.planned_finish:
                days_remaining = (activity.planned_finish - datetime.now()).days
                if days_remaining <= 3 and days_remaining > 0:
                    self.notification_service.critical_activity_reminder(activity, days_remaining)

        return len(critical_activities)

    
    # ============================================
    # مراقبة السلسلة الكاملة للتبعيات
    # ============================================
    
    def monitor_dependency_chain(self, activity_id):
        """مراقبة السلسلة الكاملة للتبعيات لنشاط معين"""
        activity = Activity.query.get(activity_id)
        if not activity:
            return
        
        # بناء سلسلة التبعيات
        chain = self.build_dependency_chain(activity_id)
        
        if chain:
            self.notification_service.dependency_chain_status(activity, chain)
    
    def build_dependency_chain(self, activity_id, direction='forward'):
        """بناء سلسلة التبعيات (للأمام أو للخلف)"""
        chain = []
        current_id = activity_id
        
        if direction == 'forward':
            # جلب الأنشطة التابعة (Successors)
            while True:
                successors = ActivityRelationship.query.filter_by(
                    predecessor_id=current_id
                ).all()
                
                if not successors:
                    break
                
                for succ in successors:
                    succ_activity = Activity.query.get(succ.successor_id)
                    if succ_activity:
                        chain.append({
                            'id': succ_activity.id,
                            'name': succ_activity.activity_name,
                            'status': succ_activity.status,
                            'relation_type': succ.relationship_type,
                            'lag': succ.lag_days
                        })
                        current_id = succ_activity.id
        
        else:
            # جلب الأنشطة السابقة (Predecessors)
            while True:
                predecessors = ActivityRelationship.query.filter_by(
                    successor_id=current_id
                ).all()
                
                if not predecessors:
                    break
                
                for pred in predecessors:
                    pred_activity = Activity.query.get(pred.predecessor_id)
                    if pred_activity:
                        chain.append({
                            'id': pred_activity.id,
                            'name': pred_activity.activity_name,
                            'status': pred_activity.status,
                            'relation_type': pred.relationship_type,
                            'lag': pred.lag_days
                        })
                        current_id = pred_activity.id
        
        return chain
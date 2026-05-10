"""
task_models.py - نماذج المهام والتنفيذ
"""
from . import db
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship, backref
from datetime import datetime,date,timedelta
import uuid
from flask import current_app
from werkzeug.utils import secure_filename
import os
from flask import url_for
from flask_login import current_user

class Task(db.Model):
    """المهام التنفيذية"""
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'))
    wbs_id = db.Column(db.Integer, db.ForeignKey("wbs.id"))
    # التعريف
    task_code = db.Column(db.String(50), nullable=False)
    task_name = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)  # تعليمات التنفيذ
    
    # التسلسل
    task_order = db.Column(db.Integer, nullable=False)  # ترتيب في التسلسل
    depends_on_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))  # المهمة السابقة
    
    # المسؤولية
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    supervisor_approved = db.Column(db.Boolean, default=False)
    supervisor_approved_at = db.Column(db.DateTime)
    supervisor_notes = db.Column(db.Text)

    delegate_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    delegate_confirmed = db.Column(db.Boolean, default=False)
    delegate_confirmed_at = db.Column(db.DateTime)
    delegate_notes = db.Column(db.Text)

    assigned_users = db.Column(db.JSON, default=[])

    # التقدم
    progress_percentage = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='pending')  # pending, in_progress, completed, on_hold, cancelled
    priority = db.Column(db.Integer, default=3)  # 1-5
    completion_quality = db.Column(db.String(20))  # excellent, good, fair, poor
    completion_status = db.Column(db.String(50), default='pending')  
    # pending, supervisor_approved, delegate_confirmed, manager_approved, completed, rejected
    rejection_reason = db.Column(db.Text)
    rejected_at = db.Column(db.DateTime)
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])
    delegate = db.relationship('User', foreign_keys=[delegate_id])
    creator = db.relationship('User', foreign_keys=[created_by])

    planning = db.relationship("TaskPlanning", backref="task", uselist=False, cascade="all, delete-orphan")
    execution = db.relationship("TaskExecution", backref="task", uselist=False, cascade="all, delete-orphan")
    progress = db.relationship("TaskProgress", backref="task", uselist=False, cascade="all, delete-orphan")
    location_rel = db.relationship("TaskLocation", backref="task", uselist=False, cascade="all, delete-orphan")
    verification = db.relationship("TaskVerification", backref="task", uselist=False, cascade="all, delete-orphan")
    assignments = db.relationship("TaskAssignment", backref="task", lazy="dynamic", cascade="all, delete-orphan")
    resources = db.relationship("TaskResource", backref="task", lazy="dynamic", cascade="all, delete-orphan")
    dependencies = db.relationship("TaskDependency", 
                                   foreign_keys="TaskDependency.predecessor_task_id",
                                   backref="predecessor", 
                                   lazy="dynamic")
    successor_dependencies = db.relationship("TaskDependency",
                                            foreign_keys="TaskDependency.successor_task_id",
                                            backref="successor",
                                            lazy="dynamic")
    daily_reports = db.relationship('DailyReportTask', backref='task', lazy=True)
    quality_checks = db.relationship('QualityCheck', backref='task', lazy=True)
    issues = db.relationship('Issue', backref='task', lazy=True)
    chats = db.relationship(
        'ProjectChat',
        backref='task',  # يسمح بالوصول من chat.task
        lazy='dynamic',
        foreign_keys='ProjectChat.task_id',
        cascade='all, delete-orphan'
    )
    # فهرسة
    __table_args__ = (
        Index("idx_task_project", "project_id"),
        Index("idx_task_activity", "activity_id"),
        Index("idx_task_status", "status"),
        Index("idx_task_code", "task_code"),
        Index("idx_task_order", "project_id", "task_order"),
        UniqueConstraint('project_id', 'task_code', name='uq_task_project_code'),
    )
    
    @property
    def is_delayed(self):
        """هل المهمة متأخرة"""
        if self.status == 'completed':
            if self.execution and self.execution.actual_finish and self.planning and self.planning.planned_finish:
                return self.execution.actual_finish.date() > self.planning.planned_finish
        else:
            if self.planning and self.planning.planned_finish:
                return date.today() > self.planning.planned_finish
        return False

    @property
    def delay_days(self):
        """عدد أيام التأخير"""
        if not self.is_delayed:
            return 0
        if self.status == 'completed' and self.execution and self.execution.actual_finish and self.planning:
            return (self.execution.actual_finish.date() - self.planning.planned_finish).days
        elif self.planning and self.planning.planned_finish:
            return (date.today() - self.planning.planned_finish).days
        return 0
    @property
    def active_chat(self):
        """الحصول على المحادثة النشطة للمهمة"""
        from app.models.communication_models import ProjectChat
        return ProjectChat.query.filter_by(
            task_id=self.id,
            chat_type='task',
            is_archived=False
        ).first()
    
    @property
    def has_chat(self):
        """التحقق من وجود محادثة للمهمة"""
        return self.active_chat is not None
    
    def can_start(self):
        """التحقق من إمكانية البدء"""
        predecessors = TaskDependency.query.filter_by(successor_task_id=self.id).all()
        for pred in predecessors:
            predecessor = Task.query.get(pred.predecessor_task_id)
            if predecessor and predecessor.status != 'completed':
                return False, f"المهمة السابقة {predecessor.task_code} لم تكتمل بعد"
        
        if not self.assignments.first():
            return False, "لم يتم تعيين مستخدمين للمهمة"
        
        return True, "يمكن البدء"

    def start(self, user_id):
        """بدء المهمة"""
        if self.status == 'pending':
            self.status = 'in_progress'
            if not self.execution:
                self.execution = TaskExecution(task_id=self.id)
            self.execution.actual_start = datetime.utcnow()
            if self.progress:
                self.progress.progress_percentage = 0.1
            return True
        return False

    def complete(self, quality='good', notes=None):
        """إكمال المهمة"""
        if self.status == 'in_progress':
            self.status = 'completed'
            if not self.execution:
                self.execution = TaskExecution(task_id=self.id)
            self.execution.actual_finish = datetime.utcnow()
            if self.execution.actual_start:
                duration = self.execution.actual_finish - self.execution.actual_start
                self.execution.actual_duration = duration.total_seconds() / 3600
            
            if not self.progress:
                self.progress = TaskProgress(task_id=self.id)
            self.progress.progress_percentage = 100
            self.progress.completion_quality = quality
            
            if notes:
                if not self.verification:
                    self.verification = TaskVerification(task_id=self.id)
                self.verification.notes = notes
            
            return True
        return False
    
    def get_dependencies_chain(self):
        """الحصول على سلسلة التبعيات للمهمة (المهام السابقة)"""
        try:
            chain = []
            
            # البحث عن المهام السابقة (predecessors)
            # هذا يعتمد على كيفية تخزين التبعيات في نظامك
            
            # إذا كان لديك نموذج TaskDependency
            if hasattr(self, 'dependencies'):
                predecessors = TaskDependency.query.filter_by(successor_task_id=self.id).all()
                for pred in predecessors:
                    predecessor = Task.query.get(pred.predecessor_task_id)
                    if predecessor:
                        chain.append({
                            'id': predecessor.id,
                            'code': predecessor.task_code,
                            'name': predecessor.task_name,
                            'status': predecessor.status,
                            'relation_type': pred.dependency_type if hasattr(pred, 'dependency_type') else 'FS',
                            'lag': pred.lag if hasattr(pred, 'lag') else 0
                        })
            
            # إذا كان لديك حقل depends_on_task_id
            elif hasattr(self, 'depends_on_task_id') and self.depends_on_task_id:
                predecessor = Task.query.get(self.depends_on_task_id)
                if predecessor:
                    chain.append({
                        'id': predecessor.id,
                        'code': predecessor.task_code,
                        'name': predecessor.task_name,
                        'status': predecessor.status,
                        'relation_type': 'FS',
                        'lag': 0
                    })
            
            return chain
            
        except Exception as e:
            # تسجيل الخطأ وإرجاع قائمة فارغة
            print(f"Error in get_dependencies_chain: {str(e)}")
            return []
    def get_successors_chain(self):
        """الحصول على المهام التالية (التي تعتمد على هذه المهمة)"""
        try:
            successors = []
            
            # استخدام TaskDependency إذا كان موجوداً
            from app.models.task_models import TaskDependency
            
            # البحث عن المهام التالية (successors)
            dependencies = TaskDependency.query.filter_by(predecessor_task_id=self.id).all()
            for dep in dependencies:
                successor = Task.query.get(dep.successor_task_id)
                if successor:
                    successors.append({
                        'id': successor.id,
                        'code': successor.task_code,
                        'name': successor.task_name,
                        'status': successor.status,
                        'relation_type': dep.dependency_type if hasattr(dep, 'dependency_type') else 'FS',
                        'lag': dep.lag if hasattr(dep, 'lag') else 0,
                        'is_critical': dep.is_critical if hasattr(dep, 'is_critical') else False
                    })
            
            return successors
            
        except Exception as e:
            print(f"Error in get_successors_chain: {str(e)}")
            return []
    def get_pending_requirements(self):
        """الحصول على المتطلبات غير المكتملة للمهمة"""
        try:
            # جلب المتطلبات النشطة للمهمة
            requirements = TaskRequirement.query.filter_by(
                task_id=self.id, 
                is_active=True
            ).all()
            
            pending = []
            
            for req in requirements:
                # التحقق من وجود تحقق معتمد لهذا المتطلب
                verification = TaskRequirementVerification.query.filter_by(
                    requirement_id=req.id,
                    status='verified'  # أو 'approved' حسب نظامك
                ).first()
                
                # إذا لم يكن هناك تحقق معتمد، أضف المتطلب للقائمة
                if not verification:
                    pending.append(req)
            
            return pending
            
        except Exception as e:
            print(f"Error in get_pending_requirements: {str(e)}")
            return []
    
    def verify_requirement(self, verification_id, verifier_id, approve=True, notes=None):
        """الموافقة على طلب تحقق (للمشرف)"""
        verification = TaskRequirementVerification.query.get(verification_id)
        
        verification.status = 'verified' if approve else 'rejected'
        verification.verified_at = datetime.utcnow()
        verification.verified_by = verifier_id
        if notes:
            verification.notes = notes
        
        db.session.commit()
        
        # إشعار للمستخدم
        from app.services.notification_service import NotificationService
        NotificationService.verification_result(
            self, 
            verification.user_id, 
            approve, 
            verification.requirement.description if verification.requirement else ''
        )
        
        return verification


class TaskPlanning(db.Model):
    """تخطيط المهمة"""
    __tablename__ = "task_planning"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    planned_start = db.Column(db.Date)
    planned_finish = db.Column(db.Date)
    planned_duration = db.Column(db.Float)  # بالساعات
    estimated_effort = db.Column(db.Float)  # جهد مقدر (ساعة رجل)


class TaskExecution(db.Model):
    """تنفيذ المهمة"""
    __tablename__ = "task_execution"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    actual_start = db.Column(db.DateTime)
    actual_finish = db.Column(db.DateTime)
    actual_duration = db.Column(db.Float)  # بالساعات
    # إضافة حقول التكاليف
    planned_cost = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)

class TaskProgress(db.Model):
    """تقدم المهمة"""
    __tablename__ = "task_progress"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    progress_percentage = db.Column(db.Float, default=0.0)
    completion_quality = db.Column(db.String(20))
    
    __table_args__ = (
        CheckConstraint('progress_percentage >= 0 AND progress_percentage <= 100', name='chk_task_progress'),
    )


class TaskLocation(db.Model):
    """موقع المهمة"""
    __tablename__ = "task_locations"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))


class TaskVerification(db.Model):
    """التحقق من المهمة"""
    __tablename__ = "task_verifications"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)
    # التحقق
    verification_required = db.Column(db.Boolean, default=True)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    verified_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)

class TaskResource(db.Model):
    """موارد المهمة"""
    __tablename__ = "task_resources"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"))
    activity_resource_id = db.Column(db.Integer, db.ForeignKey('activity_resources.id'), nullable=True)
    # الكمية المخصصة للمهمة من موارد النشاط
    planned_quantity = db.Column(db.Float, default=0.0)
    actual_quantity = db.Column(db.Float, default=0.0)
    remaining_quantity = db.Column(db.Float, default=0.0)
    
    # التكلفة
    planned_cost = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)
    
    # نسبة التوزيع من موارد النشاط
    allocation_percentage = db.Column(db.Float, default=0.0)  # 0-100
    
    # التواريخ
    planned_start = db.Column(db.DateTime)
    planned_finish = db.Column(db.DateTime)
    actual_start = db.Column(db.DateTime)
    actual_finish = db.Column(db.DateTime)
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    # resource_type = db.Column(db.String(50))  # labor, material, equipment
    # resource_name = db.Column(db.String(200))
    # quantity = db.Column(db.Float, default=0.0)
    # unit = db.Column(db.String(50))
    # cost = db.Column(db.Float, default=0.0)
    creator = db.relationship('User', foreign_keys=[created_by])
    activity_resource = db.relationship('ActivityResource', backref='task_assignments')

    __table_args__ = (
        Index('idx_task_res_task', 'task_id'),
        Index('idx_task_res_resource', 'resource_id'),
        Index('idx_task_res_activity', 'activity_resource_id'),
        UniqueConstraint('task_id', 'resource_id', name='uq_task_resource'),
    )

class TaskDependency(db.Model):
    """تبعيات المهام"""
    __tablename__ = "task_dependencies"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    
    predecessor_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    successor_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    
    dependency_type = db.Column(db.String(20), default='FS')  # FS, SS, FF, SF
    lag = db.Column(db.Float, default=0.0)
    lag_type = db.Column(db.String(20), default='days')  #  days, hours
    
    is_critical = db.Column(db.Boolean, default=False)
    is_driving = db.Column(db.Boolean, default=False)
    
    __table_args__ = (
        Index('idx_dependency_project', 'project_id'),
        Index('idx_dependency_predecessor', 'predecessor_task_id'),
        Index('idx_dependency_successor', 'successor_task_id'),
        UniqueConstraint('predecessor_task_id', 'successor_task_id', name='uq_task_dependency'),
    )

class TaskAssignment(db.Model):
    """تعيين المهام للمستخدمين"""
    __tablename__ = 'task_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # الحالة
    status = db.Column(db.String(50), default='assigned')  # assigned, accepted, in_progress, completed, rejected
    acceptance_date = db.Column(db.DateTime)
    completion_date = db.Column(db.DateTime)
    
    # الأداء
    quality_rating = db.Column(db.Integer)  # 1-5
    efficiency_rating = db.Column(db.Integer)  # 1-5
    notes = db.Column(db.Text)
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id], backref='task_assignments')
    assigner = db.relationship('User', foreign_keys=[assigned_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_assignment_task', 'task_id'),
        Index('idx_assignment_user', 'user_id'),
        Index('idx_assignment_status', 'status'),
        Index('idx_assignment_dates', 'assigned_at', 'completion_date'),
        UniqueConstraint('task_id', 'user_id', name='uq_task_user_assignment'),
    )
    
    # الدوال
    def accept_assignment(self):
        """قبول التعيين"""
        if self.status == 'assigned':
            self.status = 'accepted'
            self.acceptance_date = datetime.utcnow()
            return True
        return False
    
    def complete_assignment(self, quality_rating=None, efficiency_rating=None, notes=None):
        """إكمال التعيين"""
        if self.status in ['accepted', 'in_progress']:
            self.status = 'completed'
            self.completion_date = datetime.utcnow()
            self.quality_rating = quality_rating
            self.efficiency_rating = efficiency_rating
            self.notes = notes
            return True
        return False
    
    def reject_assignment(self, reason):
        """رفض التعيين"""
        if self.status == 'assigned':
            self.status = 'rejected'
            self.notes = reason
            return True
        return False
"""
task_models.py - إضافة متطلبات التحقق قبل بدء المهمة
"""

class TaskRequirement(db.Model):
    """متطلبات يجب تحقيقها قبل بدء المهمة"""
    __tablename__ = 'task_requirements'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    
    # نوع المتطلب
    requirement_type = db.Column(db.String(50), nullable=False)
    # document, photo, approval, checklist, training, safety, material, equipment
    
    # وصف المتطلب
    description = db.Column(db.Text, nullable=False)
    
    # تفاصيل المتطلب
    required_value = db.Column(db.String(500))  # قيمة مطلوبة (مثل عدد الوثائق)
    validation_criteria = db.Column(db.JSON)    # معايير التحقق (JSON)
    
    # هل المتطلب إلزامي؟
    is_mandatory = db.Column(db.Boolean, default=True)
    
    # ترتيب المتطلب
    order = db.Column(db.Integer, default=0)
    
    # الحالة
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    task = db.relationship('Task', backref='requirements')
    verifications = db.relationship('TaskRequirementVerification', backref='requirement', lazy=True)
    
    __table_args__ = (
        Index('idx_req_task', 'task_id'),
        Index('idx_req_type', 'requirement_type'),
    )


class TaskRequirementVerification(db.Model):
    """سجل التحقق من المتطلبات"""
    __tablename__ = 'task_requirement_verifications'
    
    id = db.Column(db.Integer, primary_key=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('task_requirements.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # حالة التحقق
    status = db.Column(db.String(20), default='pending')  # pending, verified, rejected
    
    # بيانات التحقق
    verified_value = db.Column(db.Text)  # القيمة المدخلة
    file_url = db.Column(db.String(500))  # رابط الملف المرفوع
    photo_url = db.Column(db.String(500))  # رابط الصورة
    notes = db.Column(db.Text)  # ملاحظات
    
    # تواريخ
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    verifier = db.relationship('User', foreign_keys=[verified_by])
    
    __table_args__ = (
        Index('idx_verification_req', 'requirement_id'),
        Index('idx_verification_task', 'task_id'),
        Index('idx_verification_user', 'user_id'),
        Index('idx_verification_status', 'status'),
    )


class TaskSafetyCheck(db.Model):
    """فحوصات السلامة الإلزامية قبل البدء"""
    __tablename__ = 'task_safety_checks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    
    check_name = db.Column(db.String(200), nullable=False)
    check_name_ar = db.Column(db.String(200))
    description = db.Column(db.Text)
    
    # نوع الفحص
    check_type = db.Column(db.String(50))  # equipment, ppe, training, permit
    
    # هل تم التحقق؟
    is_verified = db.Column(db.Boolean, default=False)
    verified_at = db.Column(db.DateTime)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # صورة الإثبات
    proof_photo = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TaskMaterialCheck(db.Model):
    """فحص توفر المواد قبل البدء"""
    __tablename__ = 'task_material_checks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    
    material_name = db.Column(db.String(200), nullable=False)
    required_quantity = db.Column(db.Float, nullable=False)
    available_quantity = db.Column(db.Float, default=0)
    unit = db.Column(db.String(50))
    
    # مصدر المادة
    source = db.Column(db.String(200))  # مخزن، مورد، موقع
    source_id = db.Column(db.Integer)  # معرف المصدر
    
    # هل تم التأكد من توفرها؟
    is_available = db.Column(db.Boolean, default=False)
    checked_at = db.Column(db.DateTime)
    checked_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    notes = db.Column(db.Text)


class TaskTeamBriefing(db.Model):
    """توعية الفريق قبل البدء"""
    __tablename__ = 'task_team_briefings'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    
    briefing_date = db.Column(db.DateTime)
    conducted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # المواضيع المناقشة
    topics = db.Column(db.JSON)
    
    # الحضور
    attendees = db.Column(db.JSON)  # قائمة IDs الحضور
    
    # تواقيع الحضور
    signatures = db.Column(db.JSON)
    
    # صورة الجلسة
    photo_url = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TaskProgressUpdate(db.Model):
    """تحديثات تقدم المهام"""
    __tablename__ = 'task_progress_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    
    progress_percentage = db.Column(db.Float, nullable=False)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    notes = db.Column(db.Text)
    photos = db.Column(db.JSON)  # روابط الصور
    
    # العلاقات
    task = db.relationship('Task', backref='progress_updates')
    updater = db.relationship('User', foreign_keys=[updated_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_progress_task', 'task_id'),
        Index('idx_progress_date', 'updated_at'),
        Index('idx_progress_updater', 'updated_by'),
        CheckConstraint("progress_percentage >= 0 AND progress_percentage <= 100", 
                       name='chk_progress_range'),
    )



# ============================================================================
# جداول التقارير اليومية والتتبع
# ============================================================================

class DailyReport(db.Model):
    """التقارير اليومية للمشروع"""
    __tablename__ = 'daily_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    report_date = db.Column(db.Date, nullable=False)
    report_number = db.Column(db.String(50), nullable=False)
    
    weather_condition = db.Column(db.String(100))
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    
    total_workers = db.Column(db.Integer, default=0)
    total_hours = db.Column(db.Float, default=0.0)
    overtime_hours = db.Column(db.Float, default=0.0)
    
    work_summary = db.Column(db.Text)
    completed_work = db.Column(db.Text)
    planned_work = db.Column(db.Text)
    
    materials_received = db.Column(db.Text)
    equipment_used = db.Column(db.Text)
    
    issues_encountered = db.Column(db.Text)
    safety_incidents = db.Column(db.Text)
    quality_notes = db.Column(db.Text)
    
    supervisor_notes = db.Column(db.Text)
    engineer_notes = db.Column(db.Text)
    
    # التوقيعات
    prepared_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    prepared_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    
    # العلاقات
    preparer = db.relationship('User', foreign_keys=[prepared_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    
    tasks = db.relationship('DailyReportTask', backref='daily_report', lazy=True, cascade='all, delete-orphan')
    photos = db.relationship('DailyReportPhoto', backref='daily_report', lazy=True, cascade='all, delete-orphan')
    
    # فهرسة
    __table_args__ = (
        Index('idx_daily_report_project', 'project_id'),
        Index('idx_daily_report_date', 'report_date'),
        Index('idx_daily_report_number', 'report_number'),
        Index('idx_daily_report_status', 'review_status'),
        Index('idx_daily_report_prepared', 'prepared_by'),
        UniqueConstraint('project_id', 'report_date', name='uq_daily_report_date'),
        UniqueConstraint('project_id', 'report_number', name='uq_daily_report_number'),
    )
    
    # الدوال
    def calculate_productivity(self):
        """حساب الإنتاجية اليومية"""
        if self.total_workers > 0 and self.total_hours > 0:
            man_hours = self.total_workers * self.total_hours
            return man_hours
        return 0
    
    def get_progress_summary(self):
        """ملخص التقدم اليومي"""
        completed_tasks = [t for t in self.tasks if t.status == 'completed']
        in_progress_tasks = [t for t in self.tasks if t.status == 'in_progress']
        
        return {
            'total_tasks': len(self.tasks),
            'completed_tasks': len(completed_tasks),
            'in_progress_tasks': len(in_progress_tasks),
            'completion_rate': (len(completed_tasks) / len(self.tasks) * 100) if self.tasks else 0
        }


class DailyReportTask(db.Model):
    """المهام في التقرير اليومي"""
    __tablename__ = 'daily_report_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    daily_report_id = db.Column(db.Integer, db.ForeignKey('daily_reports.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    
    planned_work = db.Column(db.Text)
    actual_work = db.Column(db.Text)
    progress_percentage = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='pending')  # pending, in_progress, completed, delayed
    
    workers_assigned = db.Column(db.Integer, default=0)
    hours_worked = db.Column(db.Float, default=0.0)
    
    materials_used = db.Column(db.Text)
    equipment_used = db.Column(db.Text)
    
    issues = db.Column(db.Text)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # فهرسة
    __table_args__ = (
        Index('idx_daily_task_report', 'daily_report_id'),
        Index('idx_daily_task_task', 'task_id'),
        Index('idx_daily_task_status', 'status'),
        UniqueConstraint('daily_report_id', 'task_id', name='uq_daily_report_task'),
        CheckConstraint("progress_percentage >= 0 AND progress_percentage <= 100", 
                       name='chk_daily_task_progress'),
    )


class DailyReportPhoto(db.Model):
    """الصور في التقرير اليومي"""
    __tablename__ = 'daily_report_photos'
    
    id = db.Column(db.Integer, primary_key=True)
    daily_report_id = db.Column(db.Integer, db.ForeignKey('daily_reports.id'), nullable=False)
    
    photo_url = db.Column(db.String(500), nullable=False)
    thumbnail_url = db.Column(db.String(500))
    
    caption = db.Column(db.String(500))
    location = db.Column(db.String(200))
    coordinates = db.Column(db.String(100))
    
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    bill_item_id = db.Column(db.Integer, db.ForeignKey('bill_items.id'))
    
    taken_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    taken_at = db.Column(db.DateTime)
    
    # العلاقات
    task = db.relationship('Task')
    bill_item = db.relationship('BillItem')
    photographer = db.relationship('User', foreign_keys=[taken_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_daily_photo_report', 'daily_report_id'),
        Index('idx_daily_photo_task', 'task_id'),
        Index('idx_daily_photo_bill', 'bill_item_id'),
        Index('idx_daily_photo_date', 'taken_at'),
    )
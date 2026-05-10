from ..extensions import db
from datetime import datetime
import uuid

class OrganizationalHierarchy(db.Model):
    """
    الهيكل التنظيمي للمشروع
    يحدد العلاقات بين المديرين والمشرفين والمناديب والافراد
    """
    __tablename__ = 'org_hierarchy'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    # المستخدم الحالي
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # المستوى الهرمي
    level = db.Column(db.Integer, default=1)  # 1: مدير مشروع, 2: مشرف, 3: مندوب, 4: فرد
    
    # المدير المباشر (الرئيس)
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # الصلاحيات المخصصة لهذا المستخدم في المشروع
    custom_permissions = db.Column(db.JSON, default={})
    
    # الفريق الذي يشرف عليه (قائمة معرفات المستخدمين)
    team_members = db.Column(db.JSON, default=[])  # للمشرفين والمناديب
    
    # المناطق المسؤول عنها (للمشاريع الجغرافية)
    responsible_areas = db.Column(db.JSON, default=[])
    
    # التخصصات
    specializations = db.Column(db.JSON, default=[])
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

class TaskAssignment(db.Model):
    """
    تعيين المهام للمستخدمين مع تتبع الحالة والوقت
    """
    __tablename__ = 'task_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # المهمة
    activity_id = db.Column(db.Integer, db.ForeignKey('universal_activities.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    # المستخدمون المعنيون
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # المنفذ
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # المكلف
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # المشرف المباشر
    delegate_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # المندوب
    
    # التسلسل الزمني
    sequence_order = db.Column(db.Integer, default=1)  # ترتيب المهمة في التسلسل
    
    # الحالة
    status = db.Column(db.String(50), default='pending')  # pending, in_progress, completed, rejected, on_hold
    
    # أوقات البدء والانتهاء
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    estimated_duration = db.Column(db.Float)  # المدة المتوقعة بالساعات
    actual_duration = db.Column(db.Float)  # المدة الفعلية بالساعات
    
    # ملاحظات التنفيذ
    execution_notes = db.Column(db.Text)
    completion_notes = db.Column(db.Text)
    
    # المخرجات
    deliverables = db.Column(db.JSON, default=[])  # مخرجات المهمة (روابط ملفات، صور، إلخ)
    
    # الاعتمادات
    requires_approval = db.Column(db.Boolean, default=True)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)
    
    # الجودة
    quality_score = db.Column(db.Float, default=0.0)
    quality_check_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    quality_check_at = db.Column(db.DateTime)
    quality_notes = db.Column(db.Text)
    
    # التبعيات - المهام التي يجب أن تسبق هذه المهمة
    dependencies = db.Column(db.JSON, default=[])  # قائمة معرفات المهام السابقة
    
    # إشعارات
    notifications_sent = db.Column(db.JSON, default={})  # سجل الإشعارات المرسلة
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class TaskDependency(db.Model):
    """
    تبعيات المهام - تحديد العلاقات بين المهام
    """
    __tablename__ = 'task_dependencies'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # المهمة السابقة (يجب أن تكتمل أولاً)
    predecessor_id = db.Column(db.Integer, db.ForeignKey('task_assignments.id'), nullable=False)
    
    # المهمة اللاحقة (تعتمد على السابقة)
    successor_id = db.Column(db.Integer, db.ForeignKey('task_assignments.id'), nullable=False)
    
    # نوع التبعية
    dependency_type = db.Column(db.String(20), default='finish_to_start')  # finish_to_start, start_to_start, finish_to_finish
    
    # الفاصل الزمني (بالأيام)
    lag_days = db.Column(db.Integer, default=0)

class TaskNotification(db.Model):
    """
    إشعارات المهام
    """
    __tablename__ = 'task_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    
    task_assignment_id = db.Column(db.Integer, db.ForeignKey('task_assignments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # نوع الإشعار
    notification_type = db.Column(db.String(50))  # task_started, task_completed, task_assigned, approval_required, etc
    
    # المحتوى
    title = db.Column(db.String(500))
    message = db.Column(db.Text)
    
    # الحالة
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    
    # الإجراء المطلوب
    action_url = db.Column(db.String(500))
    action_required = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class TaskAuditLog(db.Model):
    """
    سجل تدقيق المهام - لتتبع كل الإجراءات
    """
    __tablename__ = 'task_audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    task_assignment_id = db.Column(db.Integer, db.ForeignKey('task_assignments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # الإجراء
    action = db.Column(db.String(100))  # assigned, started, paused, resumed, completed, approved, rejected
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50))
    
    # البيانات
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
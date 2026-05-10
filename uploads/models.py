# models.py
from extensions import db
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import json

# --- نموذج المستخدمين والصلاحيات ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))
    full_name = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    role = db.Column(db.String(50), default='worker')  # 'admin', 'project_manager', 'supervisor', 'delegate', 'worker'
    profile_image = db.Column(db.String(200), default='default.jpg')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    is_paid = db.Column(db.Boolean, default=False)
    trial_start = db.Column(db.DateTime, default=datetime.utcnow)
    trial_end = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)
    # حقول جديدة
    job_title = db.Column(db.String(100), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    timezone = db.Column(db.String(50), default='Asia/Riyadh')
    date_format = db.Column(db.String(10), default='Y-m-d')
    time_format = db.Column(db.String(2), default='24')
    week_start = db.Column(db.String(10), default='saturday')
    two_factor_enabled = db.Column(db.Boolean, default=False)
    two_factor_secret = db.Column(db.String(100), nullable=True)
    
    # تحديث بنية notification_settings الافتراضية
    notification_settings = db.Column(db.JSON, default=lambda: {
        'email_notifications': True,
        'browser_notifications': True,
        'mobile_notifications': False,
        'task_reminders': True,
        'project_notifications': True,
        'comment_notifications': True,
        'daily_reminder_time': '09:00'
    })
    
    privacy_settings = db.Column(db.JSON, default=lambda: {
        'public_profile': False,
        'show_email': True,
        'show_phone': False
    })
    
    # العلاقات
    managed_projects = db.relationship('Project', backref='manager', lazy=True, foreign_keys='Project.manager_id')
    assigned_tasks = db.relationship('Task', backref='assignee', lazy=True, foreign_keys='Task.assigned_to_id')
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade='all, delete-orphan')
    activities = db.relationship('ActivityLog', backref='user', lazy=True, cascade='all, delete-orphan')
    project_accesses = db.relationship(
        'UserProjectAccess',
        foreign_keys='UserProjectAccess.user_id',
        backref='user_info',
        lazy='dynamic',
        cascade='all, delete-orphan'
    )

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_trial_active(self):
        if self.is_paid:
            return False
        if self.trial_end and self.trial_end > datetime.utcnow():
            return True
        return False
    
    def get_accessible_projects(self):
        """الحصول على المشاريع التي يمكن للمستخدم الوصول إليها"""
        if self.role == 'admin':
            return Project.query.all()
        elif self.role == 'project_manager':
            return self.managed_projects
        else:
            # للمستخدمين العاديين: المشاريع التي لديهم وصول إليها
            accesses = self.project_accesses.filter_by(is_active=True).all()
            return [access.project for access in accesses]
    
    def can_access_project(self, project_id):
        """التحقق من إمكانية الوصول لمشروع معين"""
        if self.role == 'admin':
            return True
        
        # مدير مشروع
        project = Project.query.get(project_id)
        if project and project.manager_id == self.id:
            return True
        
        # مستخدم عادي مع وصول
        return self.project_accesses.filter_by(
            project_id=project_id,
            is_active=True
        ).first() is not None
    
    def get_project_role(self, project_id):
        """الحصول على دور المستخدم في مشروع معين"""
        if self.role == 'admin':
            return 'admin'
        
        project = Project.query.get(project_id)
        if project and project.manager_id == self.id:
            return 'project_manager'
        
        access = self.project_accesses.filter_by(
            project_id=project_id,
            is_active=True
        ).first()
        
        return access.role_in_project if access else None
    
    def get_pending_invitations(self):
        """الحصول على الدعوات المعلقة للمستخدم"""
        return ProjectInvitation.query.filter_by(
            email=self.email,
            status='pending'
        ).all()
    
    def get_unread_notifications_count(self):
        return Notification.query.filter_by(user_id=self.id, is_read=False).count()
    
    def __repr__(self):
        return f'<User {self.username}>'


# --- نموذج المشروع ---
class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    region = db.Column(db.String(100))
    client_name = db.Column(db.String(100))
    client_phone = db.Column(db.String(20))
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    estimated_budget = db.Column(db.Float, default=0)
    actual_cost = db.Column(db.Float, default=0)
    status = db.Column(db.String(50), default='planning')  # planning, in_progress, on_hold, completed, cancelled
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    progress_percentage = db.Column(db.Float, default=0)
    
    # الملفات
    original_file_path = db.Column(db.String(300))
    extracted_data_json = db.Column(db.Text)  # حفظ البيانات المستخرجة كـ JSON للرجوع إليها
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    tasks = db.relationship('Task', backref='project', lazy=True, cascade='all, delete-orphan')
    # تصحيح علاقة team_members - تحديد المفتاح الخارجي بوضوح
    team_members = db.relationship(
        'ProjectTeam',
        foreign_keys='ProjectTeam.project_id',  # تحديد المفتاح الخارجي بوضوح
        backref=db.backref('project', lazy='joined'),
        lazy='dynamic',
        cascade='all, delete-orphan'
    )
    documents = db.relationship('ProjectDocument', backref='project', lazy=True, cascade='all, delete-orphan')

    max_team_members = db.Column(db.Integer, default=10)
    is_team_locked = db.Column(db.Boolean, default=False)  # منع إضافة أعضاء جدد
    invitations = db.relationship('ProjectInvitation', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    custom_roles = db.relationship('ProjectRole', backref='project', lazy='dynamic', cascade='all, delete-orphan')
    
    # علاقات جديدة
    
    # دوال المساعدة
    def get_team_members_by_role(self, role):
        """الحصول على أعضاء الفريق حسب الدور"""
        return self.team_members.filter_by(role_in_project=role, is_active=True).all()
    
    def is_user_in_team(self, user_id):
        """التحقق من وجود مستخدم في فريق المشروع"""
        return self.team_members.filter_by(user_id=user_id, is_active=True).first() is not None
    
    def get_user_role(self, user_id):
        """الحصول على دور مستخدم في المشروع"""
        member = self.team_members.filter_by(user_id=user_id, is_active=True).first()
        return member.role_in_project if member else None
    
    def get_available_users_for_task(self, current_user_id=None):
        """الحصول على المستخدمين المتاحين لإسناد مهمة"""
        query = self.team_members.filter_by(is_active=True)
        
        if current_user_id:
            query = query.filter(ProjectTeam.user_id != current_user_id)
        
        return query.all()
    
    def get_users_by_role(self, role):
        """الحصول على المستخدمين بدور محدد"""
        return self.team_members.filter_by(role_in_project=role, is_active=True).all()
    
    def get_team_stats(self):
        """إحصائيات الفريق"""
        total = self.team_members.filter_by(is_active=True).count()
        by_role = {
            'manager': self.team_members.filter_by(role_in_project='manager', is_active=True).count(),
            'supervisor': self.team_members.filter_by(role_in_project='supervisor', is_active=True).count(),
            'delegate': self.team_members.filter_by(role_in_project='delegate', is_active=True).count(),
            'worker': self.team_members.filter_by(role_in_project='worker', is_active=True).count()
        }
        
        return {
            'total': total,
            'by_role': by_role,
            'usage_percentage': (total / self.max_team_members * 100) if self.max_team_members > 0 else 0
        }
    
    def can_user_perform_action(self, user_id, action):
        """التحقق من قدرة المستخدم على تنفيذ إجراء"""
        if user_id == self.manager_id:
            return True
        
        team_member = self.team_members.filter_by(user_id=user_id, is_active=True).first()
        
        if not team_member:
            return False
        
        # الصلاحيات الافتراضية حسب الدور
        default_permissions = {
            'supervisor': {
                'create_task': True,
                'edit_task': True,
                'delete_task': False,
                'assign_task': True,
                'add_member': False
            },
            'delegate': {
                'create_task': False,
                'edit_task': True,
                'delete_task': False,
                'assign_task': True,
                'add_member': False
            },
            'worker': {
                'create_task': False,
                'edit_task': False,
                'delete_task': False,
                'assign_task': False,
                'add_member': False
            }
        }
        
        # دمج الصلاحيات الافتراضية مع المخصصة
        permissions = default_permissions.get(team_member.role_in_project, {})
        permissions.update(team_member.permissions or {})
        
        return permissions.get(action, False)
        
    
    def __repr__(self):
        return f'<Project {self.title}>'

# --- نموذج فريق المشروع (لربط المستخدمين بالمشاريع) ---
# models.py - إضافة نماذج جديدة لإدارة فرق المشروع

class ProjectTeam(db.Model):
    """نموذج فريق المشروع - ربط المستخدمين بالمشاريع"""
    __tablename__ = 'project_teams'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role_in_project = db.Column(db.String(50), nullable=False)  # 'manager', 'supervisor', 'delegate', 'worker'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    added_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_active = db.Column(db.Boolean, default=True)
    permissions = db.Column(db.JSON, default={})  # صلاحيات مخصصة داخل المشروع
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    added_by = db.relationship('User', foreign_keys=[added_by_id])
    
    __table_args__ = (
        db.UniqueConstraint('project_id', 'user_id', name='unique_project_user'),
    )


# models.py - إضافة نموذج لدعوات المشروع

class ProjectInvitation(db.Model):
    """دعوات الانضمام للمشروع"""
    __tablename__ = 'project_invitations'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    
    # معلومات المدعو
    email = db.Column(db.String(120), nullable=False)
    full_name = db.Column(db.String(100))  # إذا كان مستخدم جديد
    phone = db.Column(db.String(20))
    
    # الدور المطلوب
    role_in_project = db.Column(db.String(50), nullable=False)  # supervisor, delegate, worker
    
    # حالة الدعوة
    status = db.Column(db.String(20), default='pending')  # pending, accepted, expired, cancelled
    token = db.Column(db.String(100), unique=True, nullable=False)
    
    # تواريخ
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime)
    accepted_at = db.Column(db.DateTime)
    
    # من قام بالدعوة
    invited_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # إذا كان المستخدم مسجل مسبقاً
    existing_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # العلاقات
    invited_by = db.relationship('User', foreign_keys=[invited_by_id])
    existing_user = db.relationship('User', foreign_keys=[existing_user_id])
    
    __table_args__ = (
        db.UniqueConstraint('project_id', 'email', name='unique_project_invitation_email'),
    )


class UserProjectAccess(db.Model):
    """سجل وصول المستخدمين للمشاريع"""
    __tablename__ = 'user_project_access'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    
    # معلومات الوصول
    role_in_project = db.Column(db.String(50), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_access = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    
    # إعدادات خاصة بالمستخدم في هذا المشروع
    display_name = db.Column(db.String(100))
    notification_settings = db.Column(db.JSON, default={})
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    project = db.relationship('Project', foreign_keys=[project_id])
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'project_id', name='unique_user_project_access'),
    )

class ProjectRole(db.Model):
    """أدوار مخصصة داخل المشروع"""
    __tablename__ = 'project_roles'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    permissions = db.Column(db.JSON, default={})  # {'create_task': True, 'delete_task': False, ...}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    

# --- نموذج المهام المتسلسلة ---
class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50))  # رقم البند (مثال: 1.1, 1.1.1)
    title = db.Column(db.String(500))  # مواصفات الأعمال المطلوبة
    description = db.Column(db.Text)
    unit = db.Column(db.String(20))  # الوحدة
    
    # الكميات والأسعار
    quantity = db.Column(db.Float, default=0)  # الكمية الإجمالية المخططة
    unit_price = db.Column(db.Float, default=0)
    total_price = db.Column(db.Float, default=0)
    
    previous_quantity = db.Column(db.Float, default=0)
    previous_amount = db.Column(db.Float, default=0)
    current_quantity = db.Column(db.Float, default=0)
    current_amount = db.Column(db.Float, default=0)
    total_quantity_done = db.Column(db.Float, default=0)
    total_amount_done = db.Column(db.Float, default=0)
    
    expected_extra_quantity = db.Column(db.Float, default=0)
    expected_total_quantity = db.Column(db.Float, default=0)
    expected_total_amount = db.Column(db.Float, default=0)
    
    notes = db.Column(db.Text)
    
    # حالة المهمة والتسلسل
    status = db.Column(db.String(50), default='pending')  # pending, in_progress, completed, approved, rejected
    order_index = db.Column(db.Integer)
    is_started = db.Column(db.Boolean, default=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer)
    estimated_duration = db.Column(db.Integer)  # بالدقائق
    actual_duration = db.Column(db.Integer)  # بالدقائق
    
    # التواريخ
    planned_start = db.Column(db.DateTime)
    planned_end = db.Column(db.DateTime)
    actual_start = db.Column(db.DateTime)
    actual_end = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    parent_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات العكسية
    sub_tasks = db.relationship('Task', backref=db.backref('parent_task', remote_side=[id]), lazy=True)
    dependencies = db.relationship('TaskDependency', foreign_keys='TaskDependency.task_id', backref='task', lazy=True)
    dependents = db.relationship('TaskDependency', foreign_keys='TaskDependency.depends_on_id', backref='depends_on', lazy=True)
    attachments = db.relationship('TaskAttachment', backref='task', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('TaskComment', backref='task', lazy=True, cascade='all, delete-orphan')
    time_logs = db.relationship('TimeLog', backref='task', lazy=True, cascade='all, delete-orphan')
    
    def start_task(self):
        """بدء المهمة"""
        self.status = 'in_progress'
        self.is_started = True
        self.actual_start = datetime.utcnow()
        self.started_at = datetime.utcnow()
        
        # تسجيل النشاط
        log = ActivityLog(
            user_id=self.assigned_to_id,
            action='start_task',
            details=f'بدأ المهمة: {self.title}',
            task_id=self.id,
            project_id=self.project_id
        )
        db.session.add(log)
        
    def complete_task(self):
        """إنهاء المهمة"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.actual_end = datetime.utcnow()
        
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_seconds = int(delta.total_seconds())
            self.actual_duration = int(delta.total_seconds() / 60)
        
        # تحديث كميات المشروع
        self.total_quantity_done = self.current_quantity
        self.total_amount_done = self.current_amount
        
        # تسجيل النشاط
        log = ActivityLog(
            user_id=self.assigned_to_id,
            action='complete_task',
            details=f'أكمل المهمة: {self.title}',
            task_id=self.id,
            project_id=self.project_id
        )
        db.session.add(log)
        
        # تحديث تقدم المشروع
        project = Project.query.get(self.project_id)
        if project:
            project.update_progress()
    
    def get_task_path(self):
        """الحصول على مسار المهمة الكامل (لتحديد التسلسل الهرمي)"""
        path = []
        task = self
        while task:
            path.append(task.code)
            task = task.parent_task
        return ' -> '.join(reversed(path))
    
    def __repr__(self):
        return f'<Task {self.code}: {self.title}>'

# --- تبعيات المهام (مهمة تعتمد على أخرى) ---
class TaskDependency(db.Model):
    __tablename__ = 'task_dependencies'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    depends_on_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    dependency_type = db.Column(db.String(20), default='finish_to_start')  # finish_to_start, start_to_start, etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- مرفقات المهام ---
class TaskAttachment(db.Model):
    __tablename__ = 'task_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    filename = db.Column(db.String(200))
    file_path = db.Column(db.String(300))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    uploader = db.relationship('User', foreign_keys=[uploaded_by_id])

# --- تعليقات المهام ---
class TaskComment(db.Model):
    __tablename__ = 'task_comments'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id])

# --- تسجيل الوقت ---
class TimeLog(db.Model):
    __tablename__ = 'time_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    duration_minutes = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- وثائق المشروع ---
class ProjectDocument(db.Model):
    __tablename__ = 'project_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    title = db.Column(db.String(200))
    description = db.Column(db.Text)
    file_path = db.Column(db.String(300))
    file_type = db.Column(db.String(50))
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    version = db.Column(db.Integer, default=1)
    
    uploader = db.relationship('User', foreign_keys=[uploaded_by_id])

# --- الإشعارات ---
class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    title = db.Column(db.String(200))
    message = db.Column(db.String(500))
    type = db.Column(db.String(50))  # 'task_start', 'task_complete', 'task_assigned', 'project_update', 'reminder', 'info'
    related_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    related_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    is_read = db.Column(db.Boolean, default=False)
    is_urgent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    task = db.relationship('Task', foreign_keys=[related_task_id])
    project = db.relationship('Project', foreign_keys=[related_project_id])
    
    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.utcnow()
        db.session.commit()

# --- سجل النشاطات ---
class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    action = db.Column(db.String(50))  # create, update, delete, start_task, complete_task, etc.
    details = db.Column(db.String(500))
    ip_address = db.Column(db.String(50))
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    task = db.relationship('Task', foreign_keys=[task_id])
    project = db.relationship('Project', foreign_keys=[project_id])

# --- نموذج الاشتراكات ---
class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    plan = db.Column(db.String(50))  # basic, pro, enterprise
    amount = db.Column(db.Float)
    currency = db.Column(db.String(3), default='USD')
    stripe_subscription_id = db.Column(db.String(100))
    stripe_customer_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='active')  # active, cancelled, expired
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    auto_renew = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', foreign_keys=[user_id])
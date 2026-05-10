"""
primavera_models.py - نماذج متوافقة مع Primavera
"""
from app.extensions import db
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, date, timedelta
import uuid

# ============================================
# 1️⃣ EPS – Enterprise Project Structure
# ============================================
class EPSOBSAssignment(db.Model):
    """ربط EPS مع OBS لتحديد الصلاحيات"""
    __tablename__ = 'eps_obs_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    eps_id = db.Column(db.Integer, db.ForeignKey('eps.id'), nullable=False)
    obs_id = db.Column(db.Integer, db.ForeignKey('obs.id'), nullable=False)
    
    permission_level = db.Column(db.String(20), default='read')  # read, write, admin
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # # العلاقات
    # العلاقات
    eps = db.relationship('EPS', back_populates='obs_assignments')
    obs = db.relationship('OBS', back_populates='eps_assignments')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_eps_obs_eps', 'eps_id'),
        Index('idx_eps_obs_obs', 'obs_id'),
        UniqueConstraint('eps_id', 'obs_id', name='uq_eps_obs'),
    )

class EPS(db.Model):
    """هيكل المؤسسة للمشاريع - Enterprise Project Structure"""
    __tablename__ = 'eps'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    eps_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('eps.id'))
    level = db.Column(db.Integer, default=1)
    path = db.Column(db.String(500))  # المسار الكامل مثل: 1.2.3
    
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # إعدادات
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    parent = db.relationship('EPS', remote_side=[id], backref='eps_children')
    manager = db.relationship('User', foreign_keys=[manager_id])
    projects = db.relationship('Project', backref='eps', lazy='dynamic')
    # علاقة مع EPSOBSAssignment - استخدم string للإشارة
    obs_assignments = db.relationship('EPSOBSAssignment', back_populates='eps', lazy=True)
    __table_args__ = (
        Index('idx_eps_org', 'org_id'),
        Index('idx_eps_code', 'eps_code'),
        Index('idx_eps_parent', 'parent_id'),
        Index('idx_eps_level', 'level'),
        UniqueConstraint('org_id', 'eps_code', name='uq_eps_code'),
    )
    
    def get_allowed_obs(self, permission='read'):
        """الحصول على عناصر OBS المسموح لها بهذا EPS"""
        return [a.obs for a in self.obs_permissions 
                if a.permission_level in [permission, 'admin']]
    
    def check_obs_permission(self, obs_id, permission='read'):
        """التحقق من صلاحية OBS معين"""
        assignment = EPSOBSAssignment.query.filter_by(
            eps_id=self.id,
            obs_id=obs_id
        ).first()
        
        if not assignment:
            return False
        
        if permission == 'admin':
            return assignment.permission_level == 'admin'
        return assignment.permission_level in [permission, 'admin']
    
    def get_full_path(self):
        """الحصول على المسار الكامل"""
        if self.parent:
            return f"{self.parent.get_full_path()} / {self.name}"
        return self.name


# ============================================
# 2️⃣ WBS – Work Breakdown Structure
# ============================================

class WBS(db.Model):
    """هيكل تقسيم العمل - Work Breakdown Structure"""
    __tablename__ = 'wbs'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    wbs_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('wbs.id'))
    level = db.Column(db.Integer, default=1)
    wbs_path = db.Column(db.String(500))  # مثل: 1.1.2
    
    # الوزن النسبي
    weight = db.Column(db.Float, default=0.0)
    
    # الميزانية
    budget = db.Column(db.Float, default=0.0)
    planned_cost = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)
    cost_variance = db.Column(db.Float, default=0.0)
    # التقدم
    progress_percentage = db.Column(db.Float, default=0.0)
    # إضافة حقل للحقول المخصصة
    udf_values = db.Column(db.JSON, default={})
    # الحالة
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    parent = db.relationship('WBS', remote_side=[id], backref='children')
    activities = db.relationship('Activity', back_populates='wbs', lazy='dynamic')
    milestone = db.relationship('Milestone', backref='wbs', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_wbss_project', 'project_id'),
        Index('idx_wbss_parents', 'parent_id'),
        Index('idx_wbss_level', 'level'),
        UniqueConstraint('project_id', 'wbs_code', name='uq_wbs_code'),
    )   
    
    def calculate_progress(self):
        """حساب التقدم من الأنشطة الفرعية"""
        if self.activities.count() > 0:
            total_weight = sum(a.weight for a in self.activities if a.weight)
            if total_weight > 0:
                weighted_progress = sum(a.progress_percentage * a.weight for a in self.activities if a.weight)
                self.progress_percentage = weighted_progress / total_weight
            else:
                self.progress_percentage = sum(a.progress_percentage for a in self.activities) / self.activities.count()
        
        return self.progress_percentage
    
    
    def get_udf_value(self, udf_name):
        """الحصول على قيمة حقل مخصص"""
        return self.udf_values.get(udf_name) if self.udf_values else None
    
    def set_udf_value(self, udf_name, value):
        """تعيين قيمة حقل مخصص"""
        if not self.udf_values:
            self.udf_values = {}
        self.udf_values[udf_name] = value
    def to_dict(self):
        """تحويل WBS إلى قاموس JSON-friendly"""
        return {
            'id': self.id,
            'wbs_code': self.wbs_code,
            'name': self.name,
            'name_ar': self.name_ar,
            'description': self.description,
            'level': self.level,
            'wbs_path': self.wbs_path,
            'weight': self.weight,
            'budget': self.budget,
            'planned_cost': self.planned_cost,
            'actual_cost': self.actual_cost,
            'progress_percentage': self.progress_percentage
        }

# ============================================
# 3️⃣ Calendar – التقويمات الزمنية
# ============================================

class Calendar(db.Model):
    """التقويم الزمني للمشروع"""
    __tablename__ = 'calendars'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)
    calendar_type = db.Column(db.String(50))  # project, resource, global
    
    # أيام العمل (1-7, 1 = الأحد)
    work_days = db.Column(db.JSON, default=[1, 2, 3, 4, 5, 6])  # 6 أيام
    work_hours_per_day = db.Column(db.Float, default=8.0)
    
    # ساعات العمل
    work_start = db.Column(db.Time, default='08:00')
    work_end = db.Column(db.Time, default='17:00')
    
    # إجازات
    holidays = db.Column(db.JSON, default=[])  # قائمة التواريخ
    
    is_default = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    projects = db.relationship('Project', foreign_keys='Project.calendar_id', backref='calendar')
    financial_projects = db.relationship('Project', foreign_keys='Project.financial_calendar_id', backref='financial_calendar')
    resources = db.relationship('Resource', backref='calendar', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_calendar_org', 'org_id'),
        Index('idx_calendar_type', 'calendar_type'),
    )
    
    def is_work_day(self, day_date):
        """التحقق مما إذا كان اليوم يوم عمل"""
        weekday = day_date.isoweekday()  # 1-7, الاثنين 1
        # تحويل إلى نظامنا (الأحد 1)
        weekday = (weekday % 7) + 1 if weekday != 7 else 1
        
        if weekday not in self.work_days:
            return False
        
        if day_date.isoformat() in self.holidays:
            return False
        
        return True
    
    def calculate_duration_days(self, start_date, duration_hours):
        """حساب تاريخ الانتهاء بناءً على المدة بالساعات"""
        remaining_hours = duration_hours
        current_date = start_date
        
        while remaining_hours > 0:
            if self.is_work_day(current_date):
                remaining_hours -= self.work_hours_per_day
            if remaining_hours > 0:
                current_date += timedelta(days=1)
        
        return current_date


# ============================================
# 4️⃣ Activity – الأنشطة (المهام)
# ============================================

class Activity(db.Model):
    """الأنشطة - قلب Primavera"""
    __tablename__ = 'activities'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    wbs_id = db.Column(db.Integer, db.ForeignKey('wbs.id'))
    calendar_id = db.Column(db.Integer, db.ForeignKey('calendars.id'))
    
    # المعرفات
    activity_id = db.Column(db.String(50), nullable=False)  # مثل: A1000
    activity_code = db.Column(db.String(100))
    activity_name = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)
    # نوع النشاط
    activity_type = db.Column(db.String(50), default='task_dependent')
    # task_dependent, resource_dependent, level_of_effort, start_milestone, finish_milestone, wbs_summary
    
    # المدة والتواريخ
    original_duration = db.Column(db.Float, default=0.0)  # المدة الأصلية
    remaining_duration = db.Column(db.Float, default=0.0)  # المدة المتبقية
    actual_duration = db.Column(db.Float, default=0.0)  # المدة الفعلية
    at_complete_duration = db.Column(db.Float, default=0.0)  # ✅ المدة عند الإكمال (Actual + Remaining)
    # ========== حقول وحدات العمل (Labor Units) ==========
    budgeted_units = db.Column(db.Float, default=0.0)  # ✅ وحدات العمل المخططة
    actual_units = db.Column(db.Float, default=0.0)    # ✅ وحدات العمل الفعلية
    remaining_units = db.Column(db.Float, default=0.0) # ✅ وحدات العمل المتبقية
    at_complete_units = db.Column(db.Float, default=0.0) # ✅ وحدات العمل عند الإكمال
    
    # التواريخ المخططة
    planned_start = db.Column(db.DateTime)
    planned_finish = db.Column(db.DateTime)
    
    # التواريخ المبكرة
    early_start = db.Column(db.DateTime)
    early_finish = db.Column(db.DateTime)
    
    # التواريخ المتأخرة
    late_start = db.Column(db.DateTime)
    late_finish = db.Column(db.DateTime)
    
    # التواريخ الفعلية
    actual_start = db.Column(db.DateTime)
    actual_finish = db.Column(db.DateTime)
    
    # إضافة حقول التكاليف
    planned_cost = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)
    remaining_cost = db.Column(db.Float, default=0.0)
    cost_variance = db.Column(db.Float, default=0.0)

    # التقدم
    progress_percentage = db.Column(db.Float, default=0.0)
    physical_complete = db.Column(db.Float, default=0.0)  # الإنجاز الفعلي
    duration_percent_complete = db.Column(db.Float, default=0.0)  # ✅ نسبة إنجاز المدة

    # Float (الوقت السماحي)
    total_float = db.Column(db.Float, default=0.0)
    free_float = db.Column(db.Float, default=0.0)
    float_path = db.Column(db.String(50))

    # المسار الحرج
    is_criticall = db.Column(db.Boolean, default=False)
    
    # الحالة
    status = db.Column(db.String(50), default='not_started')
    # not_started, in_progress, completed, suspended
    
    # الوزن
    weight = db.Column(db.Float, default=1.0)
    
    # الأولوية
    priority = db.Column(db.Integer, default=3)  # 1-5
    difficulty_level = db.Column(db.String(20), default='medium')  # ✅ مستوى الصعوبة (low, medium, high)
    # المسؤول
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    delegate_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # إضافة حقل لتخزين أكواد الأنشطة
    activity_code_values = db.Column(db.JSON, default={})
    
    # إضافة حقل للحقول المخصصة
    udf_values = db.Column(db.JSON, default={})
    
    # إضافة حقل للربط مع الدور الوظيفي
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)
    # التحقق
    # verification_required = db.Column(db.Boolean, default=True)
    # verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    # verified_at = db.Column(db.DateTime)
    # verification_notes = db.Column(db.Text)
    completion_quality = db.Column(db.String(20))
    
    # الموقع
    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    # القيود
    primary_constraint = db.Column(db.String(50))
    primary_constraint_date = db.Column(db.DateTime)  # ✅ تاريخ القيد الأساسي
    secondary_constraint = db.Column(db.String(50))   # ✅ القيد الثانوي
    secondary_constraint_date = db.Column(db.DateTime) # ✅ تاريخ القيد الثانوي
    must_finish_by = db.Column(db.DateTime)
    # أداء القيمة المكتسبة
    earned_value = db.Column(db.Float, default=0.0)
    planned_value = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)
    cpi = db.Column(db.Float, default=1.0)
    spi = db.Column(db.Float, default=1.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    # العلاقات الجديدة
    # role = db.relationship('Role', foreign_keys=[role_id], backref='activities')
    # العلاقات
    project = db.relationship('Project', back_populates='activities')
    wbs = db.relationship('WBS', back_populates='activities')
    calendar = db.relationship('Calendar')
    responsible = db.relationship('User', foreign_keys=[responsible_id])
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])
    delegate = db.relationship('User', foreign_keys=[delegate_id])
    # verifier = db.relationship('User', foreign_keys=[verified_by])
    creator = db.relationship('User', foreign_keys=[created_by])
    tasks = db.relationship("Task", backref="activity", lazy="dynamic", cascade="all, delete-orphan")
    predecessors = db.relationship('ActivityRelationship',
                                   foreign_keys='ActivityRelationship.successor_id',
                                   backref='successor')
    successors = db.relationship('ActivityRelationship',
                                foreign_keys='ActivityRelationship.predecessor_id',
                                backref='predecessor')
    
    resources = db.relationship('ActivityResource', backref='activity', lazy=True)
    chats = db.relationship(
        'ProjectChat',
        backref='activity',  # يسمح بالوصول من chat.activity
        lazy='dynamic',
        foreign_keys='ProjectChat.activity_id',
        cascade='all, delete-orphan'
    )
    __table_args__ = (
        Index('idx_activity_project', 'project_id'),
        Index('idx_activity_wbss', 'wbs_id'),
        Index('idx_activity_id', 'activity_id'),
        Index('idx_activity_type', 'activity_type'),
        Index('idx_activity_status', 'status'),
        Index('idx_activity_supervisor', 'supervisor_id'),
        Index('idx_activity_dates', 'planned_start', 'planned_finish'),
        Index('idx_activity_constraint', 'primary_constraint'),
        UniqueConstraint('project_id', 'activity_id', name='uq_activity_id'),
        CheckConstraint('progress_percentage >= 0 AND progress_percentage <= 100', 
                       name='chk_activity_progress'),
    )

    
    # ========== الخصائص المحسوبة ==========
    
    @property
    def is_milestone(self):
        return self.activity_type in ['start_milestone', 'finish_milestone']
    
    @property
    def is_critical(self):
        return self.total_float == 0
    
    @property
    def at_complete_duration_calc(self):
        """حساب المدة عند الإكمال (Actual + Remaining)"""
        return (self.actual_duration or 0) + (self.remaining_duration or 0)
    
    @property
    def at_complete_units_calc(self):
        """حساب وحدات العمل عند الإكمال (Actual + Remaining)"""
        return (self.actual_units or 0) + (self.remaining_units or 0)
    
    @property
    def remaining_units_calc(self):
        """حساب وحدات العمل المتبقية (Budgeted - Actual)"""
        return max(0, (self.budgeted_units or 0) - (self.actual_units or 0))
    
    @property
    def duration_percent(self):
        """نسبة إنجاز المدة"""
        if self.original_duration and self.original_duration > 0:
            return (self.actual_duration / self.original_duration) * 100
        return 0
    @property
    def active_chat(self):
        """الحصول على المحادثة النشطة للنشاط"""
        from app.models.communication_models import ProjectChat
        return ProjectChat.query.filter_by(
            activity_id=self.id,
            chat_type='activity',
            is_archived=False
        ).first()
    
    @property
    def has_chat(self):
        """التحقق من وجود محادثة للنشاط"""
        return self.active_chat is not None
    
    @property
    def chat_unread_count(self):
        """عدد الرسائل غير المقروءة في محادثة النشاط"""
        from app.models.communication_models import ChatMessage
        from flask_login import current_user
        
        chat = self.active_chat
        if chat and current_user.is_authenticated:
            return ChatMessage.query.filter(
                ChatMessage.chat_id == chat.id,
                ChatMessage.sender_id != current_user.id,
                ChatMessage.is_read == False,
                ChatMessage.is_deleted == False
            ).count()
        return 0
    # ========== الدوال ==========
    
    def update_from_status(self, data):
        """تحديث النشاط من بيانات نافذة Status"""
        if 'original_duration' in data:
            self.original_duration = float(data['original_duration'])
        if 'actual_duration' in data:
            self.actual_duration = float(data['actual_duration'])
        if 'remaining_duration' in data:
            self.remaining_duration = float(data['remaining_duration'])
        
        # تحديث المدة عند الإكمال
        self.at_complete_duration = self.at_complete_duration_calc
        
        # تحديث وحدات العمل
        if 'budgeted_units' in data:
            self.budgeted_units = float(data['budgeted_units'])
        if 'actual_units' in data:
            self.actual_units = float(data['actual_units'])
            self.remaining_units = self.remaining_units_calc
            self.at_complete_units = self.at_complete_units_calc
        
        # تحديث التواريخ
        date_fields = ['started_date', 'finished_date', 'suspend_date', 
                      'resume_date', 'expected_finish']
        date_map = {
            'started_date': 'actual_start',
            'finished_date': 'actual_finish',
            'suspend_date': 'suspend_date',
            'resume_date': 'resume_date',
            'expected_finish': 'expected_finish'
        }
        
        for field, model_field in date_map.items():
            if field in data and data[field]:
                setattr(self, model_field, datetime.strptime(data[field], '%Y-%m-%d'))
        
        # تحديث القيود
        if 'primary_constraint' in data:
            self.primary_constraint = data['primary_constraint']
        if 'primary_constraint_date' in data and data['primary_constraint_date']:
            self.primary_constraint_date = datetime.strptime(data['primary_constraint_date'], '%Y-%m-%d')
        if 'secondary_constraint' in data:
            self.secondary_constraint = data['secondary_constraint']
        if 'secondary_constraint_date' in data and data['secondary_constraint_date']:
            self.secondary_constraint_date = datetime.strptime(data['secondary_constraint_date'], '%Y-%m-%d')
        
        # تحديث نسبة التقدم
        if self.original_duration and self.original_duration > 0:
            self.progress_percentage = (self.actual_duration / self.original_duration) * 100
            self.duration_percent_complete = self.progress_percentage
        
        # تحديث الحالة
        if self.actual_duration and self.actual_duration > 0:
            if self.remaining_duration == 0:
                self.status = 'completed'
            else:
                self.status = 'in_progress'
        else:
            self.status = 'not_started'
    
    def get_activity_code(self, code_type):
        """الحصول على كود نشاط من نوع معين"""
        return self.activity_code_values.get(code_type) if self.activity_code_values else None
    
    def set_activity_code(self, code_type, value):
        """تعيين كود نشاط"""
        if not self.activity_code_values:
            self.activity_code_values = {}
        self.activity_code_values[code_type] = value
    
    def get_udf_value(self, udf_name):
        """الحصول على قيمة حقل مخصص"""
        return self.udf_values.get(udf_name) if self.udf_values else None
    
    def set_udf_value(self, udf_name, value):
        """تعيين قيمة حقل مخصص"""
        if not self.udf_values:
            self.udf_values = {}
        self.udf_values[udf_name] = value

    def to_dict(self):
        """تحويل النشاط إلى قاموس JSON-friendly"""
        return {
            'id': self.id,
            'activity_id': self.activity_id,
            'activity_name': self.activity_name,
            'activity_type': self.activity_type,
            'status': self.status,
            'is_critical': self.is_critical,
            'progress_percentage': self.progress_percentage,
            'duration_percent': self.duration_percent,
            'original_duration': self.original_duration,
            'remaining_duration': self.remaining_duration,
            'actual_duration': self.actual_duration,
            'at_complete_duration': self.at_complete_duration,
            'budgeted_units': self.budgeted_units,
            'actual_units': self.actual_units,
            'remaining_units': self.remaining_units,
            'at_complete_units': self.at_complete_units,
            'planned_start': self.planned_start.isoformat() if self.planned_start else None,
            'planned_finish': self.planned_finish.isoformat() if self.planned_finish else None,
            'actual_start': self.actual_start.isoformat() if self.actual_start else None,
            'actual_finish': self.actual_finish.isoformat() if self.actual_finish else None,
            'early_start': self.early_start.isoformat() if self.early_start else None,
            'early_finish': self.early_finish.isoformat() if self.early_finish else None,
            'late_start': self.late_start.isoformat() if self.late_start else None,
            'late_finish': self.late_finish.isoformat() if self.late_finish else None,
            'total_float': self.total_float,
            'free_float': self.free_float,
            'primary_constraint': self.primary_constraint,
            'primary_constraint_date': self.primary_constraint_date.isoformat() if self.primary_constraint_date else None,
            'secondary_constraint': self.secondary_constraint,
            'secondary_constraint_date': self.secondary_constraint_date.isoformat() if self.secondary_constraint_date else None,
            'wbs_id': self.wbs_id,
            'calendar_id': self.calendar_id,
            'responsible_id': self.responsible_id,
            'priority': self.priority,
            'weight': self.weight,
            'difficulty_level': self.difficulty_level
        }
    
class ActivityCompletion(db.Model):
    """سجل إكمال النشاط"""
    __tablename__ = 'activity_completions'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    completion_status = db.Column(db.String(50), default='pending')
    
    supervisor_approved = db.Column(db.Boolean, default=False)
    supervisor_approved_at = db.Column(db.DateTime)
    supervisor_approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    supervisor_notes = db.Column(db.Text)
    
    delegate_confirmed = db.Column(db.Boolean, default=False)
    delegate_confirmed_at = db.Column(db.DateTime)
    delegate_confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    delegate_notes = db.Column(db.Text)
    
    manager_approved = db.Column(db.Boolean, default=False)
    manager_approved_at = db.Column(db.DateTime)
    manager_approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    manager_notes = db.Column(db.Text)
    
    rejection_reason = db.Column(db.Text)
    rejected_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    rejected_at = db.Column(db.DateTime)
    
    # العلاقات
    activity = db.relationship('Activity', backref='completion')
    supervisor_approver = db.relationship('User', foreign_keys=[supervisor_approved_by])
    delegate_confirmer = db.relationship('User', foreign_keys=[delegate_confirmed_by])
    manager_approver = db.relationship('User', foreign_keys=[manager_approved_by])
    rejecter = db.relationship('User', foreign_keys=[rejected_by])
# ============================================
# 5️⃣ Relationship – العلاقات بين الأنشطة
# ============================================

class ActivityRelationship(db.Model):
    """العلاقات بين الأنشطة"""
    __tablename__ = 'activity_relationships'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    predecessor_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    successor_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    # نوع العلاقة
    relationship_type = db.Column(db.String(20), default='FS')
    # FS (Finish to Start), SS (Start to Start), FF (Finish to Finish), SF (Start to Finish)
    
    # التأخير
    lag_days = db.Column(db.Float, default=0.0)
    lag_type = db.Column(db.String(20), default='days')  # days, hours, percent
    
    # هل هي علاقة حرجة؟
    is_critical = db.Column(db.Boolean, default=False)
    is_driving = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_rel_project', 'project_id'),
        Index('idx_rel_predecessor', 'predecessor_id'),
        Index('idx_rel_successor', 'successor_id'),
        Index('idx_rel_type', 'relationship_type'),
        UniqueConstraint('predecessor_id', 'successor_id', name='uq_relationship'),
    )

    def to_dict(self):
        """تحويل العلاقة إلى قاموس JSON-friendly"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'predecessor_id': self.predecessor_id,
            'successor_id': self.successor_id,
            'relationship_type': self.relationship_type,
            'lag_days': self.lag_days,
            'lag_type': self.lag_type,
            'is_critical': self.is_critical,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# ============================================
# 6️⃣ Resource – الموارد
# ============================================

class Resource(db.Model):
    """الموارد (عمال، معدات، مواد)"""
    __tablename__ = 'resources'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    resource_id = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    
    # نوع المورد
    resource_type = db.Column(db.String(50), nullable=False)
    # labor, material, equipment, non_labor
    # ========== حقل خاص بالموارد البشرية ==========
    # employee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # معرف الموظف
    specialization = db.Column(db.String(200))  # التخصص
    skills = db.Column(db.JSON, default=[])  # المهارات
    certifications = db.Column(db.JSON, default=[])  # الشهادات
    experience_years = db.Column(db.Float, default=0)  # سنوات الخبرة
    # ========== حقول خاصة بالمعدات ==========
    equipment_type = db.Column(db.String(100))  # نوع المعدة (حفار، رافعة، إلخ)
    equipment_model = db.Column(db.String(100))  # الموديل
    equipment_serial = db.Column(db.String(100))  # الرقم التسلسلي
    manufacturer = db.Column(db.String(200))  # الشركة المصنعة
    manufacturing_year = db.Column(db.Integer)  # سنة الصنع
    
    # الصيانة
    maintenance_schedule = db.Column(db.JSON, default={
        'last': None,
        'next': None,
        'cycle': 30,
        'type': 'preventive'
    })  # جدول الصيانة
    # ========== حقول خاصة بالمواد ==========
    material_type = db.Column(db.String(100))  # نوع المادة (حديد، اسمنت، إلخ)
    material_grade = db.Column(db.String(50))  # درجة المادة
    material_specifications = db.Column(db.JSON, default={})  # مواصفات المادة
    # الوحدة
    unit = db.Column(db.String(50))  # ساعة، يوم، طن، متر مكعب
    
    # التكلفة
    cost_per_unit = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    
    # الكمية المتاحة
    available_quantity = db.Column(db.Float, default=0.0)
    minimum_quantity = db.Column(db.Float, default=0.0)
    maximum_quantity = db.Column(db.Float, default=0.0)
    reorder_quantity = db.Column(db.Float, default=0.0)  # كمية إعادة الطلب
    # التقويم الخاص
    calendar_id = db.Column(db.Integer, db.ForeignKey('calendars.id'))
    # المورد
    supplier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # معرف المورد
    # ========== التواريخ ==========
    last_maintenance = db.Column(db.Date)  # آخر صيانة
    next_maintenance = db.Column(db.Date)  # الصيانة القادمة
    maintenance_cycle = db.Column(db.Integer, default=30)  # دورة الصيانة (بالأيام)
    # المواصفات
    specifications = db.Column(db.JSON,default={})
    attributes = db.Column(db.JSON, default={})
    # الحالة
    is_active = db.Column(db.Boolean, default=True)
    is_shared = db.Column(db.Boolean, default=True)  # هل يمكن مشاركته بين عدة مهام
    is_available = db.Column(db.Boolean, default=True)  # هل المورد متاح حالياً

    # إضافة حقل لتخزين أكواد الموارد
    resource_code_values = db.Column(db.JSON, default={})
    
    # إضافة حقل للحقول المخصصة
    udf_values = db.Column(db.JSON, default={})
    
    # إضافة حقل للربط مع الدور الوظيفي
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
   
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    creator_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    # العلاقات الجديدة
    # role = db.relationship('Role', foreign_keys=[role_id], backref='resources')
    # العلاقات
    # calendar = db.relationship('Calendar')
    supplier = db.relationship('User', foreign_keys=[supplier_id],backref='resources')
    # العلاقة مع المستخدم (الموظف)
    # employee = db.relationship('User', foreign_keys=[employee_id], backref='assigned_resources')
    creator = db.relationship('User', foreign_keys=[creator_id])
    assignments = db.relationship('ActivityResource', backref='resource', lazy=True)
    task_assignments = db.relationship('TaskResource', backref='resource', lazy='dynamic')
    __table_args__ = (
        Index('idx_resource_org', 'org_id'),
        Index('idx_resource_id', 'resource_id'),
        Index('idx_resource_type', 'resource_type'),
        Index('idx_resource_active', 'is_active'),
        UniqueConstraint('org_id', 'resource_id', name='uq_resource_id'),
    )

    @property
    def utilization(self):
        """نسبة استخدام المورد"""
        total_assigned = self.get_total_assigned()
        if self.available_quantity > 0:
            return (total_assigned / self.available_quantity) * 100
        return 0

    def get_total_assigned(self):
        """إجمالي الكمية المخصصة"""
        total = 0
        for assignment in self.assignments:
            total += assignment.planned_quantity or 0
        for task_assign in self.task_assignments:
            total += task_assign.planned_quantity or 0
        return total
    
    def get_available_quantity(self):
        """الكمية المتاحة"""
        return self.available_quantity - self.get_total_assigned()
    
    def get_resource_code(self, code_type):
        """الحصول على كود مورد من نوع معين"""
        return self.resource_code_values.get(code_type) if self.resource_code_values else None
    
    def set_resource_code(self, code_type, value):
        """تعيين كود مورد"""
        if not self.resource_code_values:
            self.resource_code_values = {}
        self.resource_code_values[code_type] = value
    
    def get_udf_value(self, udf_name):
        """الحصول على قيمة حقل مخصص"""
        return self.udf_values.get(udf_name) if self.udf_values else None
    
    def set_udf_value(self, udf_name, value):
        """تعيين قيمة حقل مخصص"""
        if not self.udf_values:
            self.udf_values = {}
        self.udf_values[udf_name] = value

    def to_dict(self):
        return {
            'id': self.id,
            'resource_id': self.resource_id,
            'name': self.name,
            'type': self.resource_type,
            'unit': self.unit,
            'cost_per_unit': self.cost_per_unit,
            'available_quantity': self.available_quantity,
            'utilization': self.utilization
        }
    
class ActivityResource(db.Model):
    """تخصيص الموارد للأنشطة"""
    __tablename__ = 'activity_resources'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    
    # الكمية المخصصة
    planned_quantity = db.Column(db.Float, default=0.0)
    actual_quantity = db.Column(db.Float, default=0.0)
    remaining_quantity = db.Column(db.Float, default=0.0)
    # التكلفة
    planned_cost = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)
    remaining_cost = db.Column(db.Float, default=0.0)

    allocated = db.Column(db.Boolean, default=True)
    is_approved = db.Column(db.Boolean, default=False)
    rate_type= db.Column(db.String(3), default='Standard')
    start_date = db.Column(db.DateTime)
    finish_date = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    creator = db.relationship('User', foreign_keys=[created_by])
    __table_args__ = (
        Index('idx_act_res_activity', 'activity_id'),
        Index('idx_act_res_resource', 'resource_id'),
    )

# app/models/resource_models.py



class ResourceRequest(db.Model):
    """طلبات توريد الموارد"""
    __tablename__ = 'resource_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # المشروع
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    # المورد المسؤول
    supplier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # مستخدم من نوع supplier
    
    # الموارد المطلوبة
    resources = db.Column(db.JSON)  # قائمة بالموارد المطلوبة مع الكميات
    
    # التواريخ
    required_date = db.Column(db.Date, nullable=False)  # التاريخ المطلوب للاستلام
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # الحالة
    status = db.Column(db.String(20), default='pending')  # pending, started, completed, cancelled, delayed
    
    # التتبع
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # الموقع
    site_location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    
    # ملاحظات
    notes = db.Column(db.Text)
    # حقل لتتبع آخر تذكير
    last_reminder_sent = db.Column(db.DateTime)
    reminder_count = db.Column(db.Integer, default=0)
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    project = db.relationship('Project', backref='resource_requests')
    supplier = db.relationship('User', foreign_keys=[supplier_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    updates = db.relationship('ResourceRequestUpdate', backref='request', lazy='dynamic')
    notifications = db.relationship('ResourceRequestNotification', backref='request', lazy='dynamic')
    items = db.relationship('ResourceRequestItem', back_populates='request', lazy='dynamic', cascade='all, delete-orphan')
    
    
    __table_args__ = (
        Index('idx_resource_request_project', 'project_id'),
        Index('idx_resource_request_supplier', 'supplier_id'),
        Index('idx_resource_request_status', 'status'),
        Index('idx_resource_request_required_date', 'required_date'),
        # UniqueConstraint('project_id', 'supplier_id', name='uq_resource_request_project_supplier'),
    )
    
    @property
    def total_required_quantity(self):
        """إجمالي الكمية المطلوبة"""
        return sum(item.required_quantity for item in self.items)
    
    @property
    def total_delivered_quantity(self):
        """إجمالي الكمية المسلمة"""
        return sum(item.delivered_quantity for item in self.items)
    
    @property
    def total_remaining_quantity(self):
        """إجمالي الكمية المتبقية"""
        return self.total_required_quantity - self.total_delivered_quantity
    
    @property
    def completion_percentage(self):
        """نسبة الإنجاز"""
        if self.total_required_quantity > 0:
            return (self.total_delivered_quantity / self.total_required_quantity) * 100
        return 0
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'project_id': self.project_id,
            'project_name': self.project.name if self.project else None,
            'project_code': self.project.project_code if self.project else None,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.full_name if self.supplier else None,
            'resources': self.resources,
            'required_date': self.required_date.strftime('%Y-%m-%d') if self.required_date else None,
            'status': self.status,
            'site_location': self.site_location,
            'coordinates': self.coordinates,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ResourceRequestUpdate(db.Model):
    """تحديثات حالة طلب توريد الموارد"""
    __tablename__ = 'resource_request_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('resource_requests.id'), nullable=False)
    
    # الحالة الجديدة
    new_status = db.Column(db.String(20), nullable=False)
    old_status = db.Column(db.String(20))
    
    # تفاصيل التحديث
    message = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # موقع التحديث
    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    
    # الصور
    photos = db.Column(db.JSON)
    
    # العلاقات
    updater = db.relationship('User', foreign_keys=[updated_by])
    
    __table_args__ = (
        Index('idx_req_update_request', 'request_id'),
        Index('idx_req_update_status', 'new_status'),
    )


class ResourceRequestNotification(db.Model):
    """إشعارات طلبات توريد الموارد"""
    __tablename__ = 'resource_request_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('resource_requests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # نوع الإشعار
    notification_type = db.Column(db.String(50))  # reminder, start_reminder, deadline, completion
    
    # حالة الإشعار
    is_sent = db.Column(db.Boolean, default=False)
    is_read = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    
    # محتوى الإشعار
    title = db.Column(db.String(500))
    message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_req_notif_request', 'request_id'),
        Index('idx_req_notif_user', 'user_id'),
        Index('idx_req_notif_type', 'notification_type'),
    )

# app/models/resource_models.py (إضافة نماذج جديدة)

class ResourceDelivery(db.Model):
    """عمليات تسليم الموارد"""
    __tablename__ = 'resource_deliveries'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    request_id = db.Column(db.Integer, db.ForeignKey('resource_requests.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # بيانات التسليم
    delivery_date = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_number = db.Column(db.String(50), unique=True)
    
    # الموارد المسلمة
    delivered_items = db.Column(db.JSON)  # [{resource_id, name, quantity, unit, notes}]
    
    # موقع التسليم
    delivery_location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    
    # الصور
    photos = db.Column(db.JSON)
    
    notes = db.Column(db.Text)

    # حالة التسليم
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, rejected, partially_confirmed
    
    # التأكيد
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    confirmed_at = db.Column(db.DateTime)
    confirmation_notes = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    request = db.relationship('ResourceRequest', backref='deliveries')
    supplier = db.relationship('User', foreign_keys=[supplier_id])
    confirmer = db.relationship('User', foreign_keys=[confirmed_by])
    
    __table_args__ = (
        Index('idx_delivery_request', 'request_id'),
        Index('idx_delivery_supplier', 'supplier_id'),
        Index('idx_delivery_status', 'status'),
        Index('idx_delivery_date', 'delivery_date'),
        # UniqueConstraint('request_id', 'delivery_number', name='uq_delivery_number'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'delivery_number': self.delivery_number,
            'delivery_date': self.delivery_date.strftime('%Y-%m-%d %H:%M') if self.delivery_date else None,
            'delivered_items': self.delivered_items,
            'delivery_location': self.delivery_location,
            'status': self.status,
            'photos': self.photos,
            'confirmation_notes': self.confirmation_notes,
            'rejection_reason': self.rejection_reason,
            'confirmed_by': self.confirmer.full_name if self.confirmer else None,
            'confirmed_at': self.confirmed_at.strftime('%Y-%m-%d %H:%M') if self.confirmed_at else None
        }


class ResourceDeliveryUpdate(db.Model):
    """تحديثات عمليات التسليم"""
    __tablename__ = 'resource_delivery_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('resource_deliveries.id'), nullable=False)
    
    old_status = db.Column(db.String(20))
    new_status = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    updater = db.relationship('User', foreign_keys=[updated_by])
    
    __table_args__ = (
        Index('idx_delivery_update_delivery', 'delivery_id'),
    )


class ResourceRequestItem(db.Model):
    """بنود طلب الموارد (لتتبع الكميات المتبقية)"""
    __tablename__ = 'resource_request_items'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('resource_requests.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    
    resource_name = db.Column(db.String(200))
    resource_type = db.Column(db.String(50))
    resource_code = db.Column(db.String(50))
    resource_type = db.Column(db.String(50))
    unit = db.Column(db.String(50))
    
    required_quantity = db.Column(db.Float, nullable=False)
    delivered_quantity = db.Column(db.Float, default=0.0)
    remaining_quantity = db.Column(db.Float, default=0.0)
    # حقول عرض السعر
    offer_price = db.Column(db.Float, default=0.0)  # سعر الوحدة المقترح من المورد
    offer_currency = db.Column(db.String(3), default='SAR')  # عملة عرض السعر
    offer_notes = db.Column(db.Text)  # ملاحظات عرض السعر
    offer_submitted_at = db.Column(db.DateTime)  # تاريخ تقديم عرض السعر
    offer_status = db.Column(db.String(50), default='pending')  # pending, approved, rejected

    # حقول التسليم الفعلي
    unit_price = db.Column(db.Float, default=0.0)  # السعر المعتمد بعد الموافقة
    total_price = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)

    is_completed = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # العلاقات
    request = db.relationship('ResourceRequest', back_populates='items')
    resource = db.relationship('Resource', foreign_keys=[resource_id])
    
    __table_args__ = (
        Index('idx_req_item_request', 'request_id'),
        Index('idx_req_item_resource', 'resource_id'),
        # UniqueConstraint('request_id', 'resource_id', name='uq_req_item'),
    )

class ResourceOfferHistory(db.Model):
    """سجل عروض أسعار الموارد"""
    __tablename__ = 'resource_offer_histories'
    
    id = db.Column(db.Integer, primary_key=True)
    request_item_id = db.Column(db.Integer, db.ForeignKey('resource_request_items.id'), nullable=False)
    
    offer_price = db.Column(db.Float, nullable=False)
    offer_currency = db.Column(db.String(3), default='SAR')
    offer_notes = db.Column(db.Text)
    
    status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)
    
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    request_item = db.relationship('ResourceRequestItem', backref='offer_history')
    approver = db.relationship('User', foreign_keys=[approved_by])
    submitter = db.relationship('User', foreign_keys=[submitted_by])
    
    __table_args__ = (
        Index('idx_offer_request_item', 'request_item_id'),
        Index('idx_offer_status', 'status'),
    )
# أضف هذه النماذج في نهاية ملف primavera_models.py

class EquipmentRequest(db.Model):
    """طلبات توريد المعدات"""
    __tablename__ = 'equipment_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # المشروع
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    # المورد المسؤول
    supplier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # مستخدم من نوع supplier
    
    # المعدات المطلوبة
    equipment_items = db.Column(db.JSON)  # قائمة بالمعدات المطلوبة مع الكميات
    
    # التواريخ
    required_date = db.Column(db.Date, nullable=False)  # التاريخ المطلوب للاستلام
    request_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # حالة الطلب
    status = db.Column(db.String(20), default='pending')  # pending, started, completed, cancelled, delayed
    
    # التتبع
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # الموقع
    site_location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    
    # ملاحظات
    notes = db.Column(db.Text)
    
    # حقل لتتبع آخر تذكير
    last_reminder_sent = db.Column(db.DateTime)
    reminder_count = db.Column(db.Integer, default=0)
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    project = db.relationship('Project', backref='equipment_requests')
    supplier = db.relationship('User', foreign_keys=[supplier_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    updates = db.relationship('EquipmentRequestUpdate', backref='request', lazy='dynamic')
    notifications = db.relationship('EquipmentRequestNotification', backref='request', lazy='dynamic')
    items = db.relationship('EquipmentRequestItem', back_populates='request', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_equipment_request_project', 'project_id'),
        Index('idx_equipment_request_supplier', 'supplier_id'),
        Index('idx_equipment_request_status', 'status'),
        Index('idx_equipment_request_required_date', 'required_date'),
    )
    
    @property
    def total_required_quantity(self):
        """إجمالي الكمية المطلوبة"""
        return sum(item.required_quantity for item in self.items)
    
    @property
    def total_delivered_quantity(self):
        """إجمالي الكمية المسلمة"""
        return sum(item.delivered_quantity for item in self.items)
    
    @property
    def total_remaining_quantity(self):
        """إجمالي الكمية المتبقية"""
        return self.total_required_quantity - self.total_delivered_quantity
    
    @property
    def completion_percentage(self):
        """نسبة الإنجاز"""
        if self.total_required_quantity > 0:
            return (self.total_delivered_quantity / self.total_required_quantity) * 100
        return 0
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'project_id': self.project_id,
            'project_name': self.project.name if self.project else None,
            'project_code': self.project.project_code if self.project else None,
            'supplier_id': self.supplier_id,
            'supplier_name': self.supplier.full_name if self.supplier else None,
            'equipment_items': self.equipment_items,
            'required_date': self.required_date.strftime('%Y-%m-%d') if self.required_date else None,
            'status': self.status,
            'site_location': self.site_location,
            'coordinates': self.coordinates,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class EquipmentRequestUpdate(db.Model):
    """تحديثات حالة طلب توريد المعدات"""
    __tablename__ = 'equipment_request_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('equipment_requests.id'), nullable=False)
    
    # الحالة الجديدة
    new_status = db.Column(db.String(20), nullable=False)
    old_status = db.Column(db.String(20))
    
    # تفاصيل التحديث
    message = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # موقع التحديث
    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    
    # الصور
    photos = db.Column(db.JSON)
    
    # العلاقات
    updater = db.relationship('User', foreign_keys=[updated_by])
    
    __table_args__ = (
        Index('idx_eq_req_update_request', 'request_id'),
        Index('idx_eq_req_update_status', 'new_status'),
    )


class EquipmentRequestNotification(db.Model):
    """إشعارات طلبات توريد المعدات"""
    __tablename__ = 'equipment_request_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('equipment_requests.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # نوع الإشعار
    notification_type = db.Column(db.String(50))  # reminder, start_reminder, deadline, completion
    
    # حالة الإشعار
    is_sent = db.Column(db.Boolean, default=False)
    is_read = db.Column(db.Boolean, default=False)
    sent_at = db.Column(db.DateTime)
    read_at = db.Column(db.DateTime)
    
    # محتوى الإشعار
    title = db.Column(db.String(500))
    message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_eq_req_notif_request', 'request_id'),
        Index('idx_eq_req_notif_user', 'user_id'),
        Index('idx_eq_req_notif_type', 'notification_type'),
    )


class EquipmentRequestItem(db.Model):
    """بنود طلب المعدات (لتتبع الكميات المتبقية)"""
    __tablename__ = 'equipment_request_items'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('equipment_requests.id'), nullable=False)
    equipment_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    
    equipment_name = db.Column(db.String(200))
    equipment_type = db.Column(db.String(50))
    equipment_code = db.Column(db.String(50))
    unit = db.Column(db.String(50))
    
    required_quantity = db.Column(db.Float, nullable=False)
    delivered_quantity = db.Column(db.Float, default=0.0)
    remaining_quantity = db.Column(db.Float, default=0.0)
    
    # حقول عرض السعر
    offer_price = db.Column(db.Float, default=0.0)  # سعر الوحدة المقترح من المورد
    offer_currency = db.Column(db.String(3), default='SAR')  # عملة عرض السعر
    offer_notes = db.Column(db.Text)  # ملاحظات عرض السعر
    offer_submitted_at = db.Column(db.DateTime)  # تاريخ تقديم عرض السعر
    offer_status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    
    # حقول التسليم الفعلي
    unit_price = db.Column(db.Float, default=0.0)  # السعر المعتمد بعد الموافقة
    total_price = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    
    is_completed = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    request = db.relationship('EquipmentRequest', back_populates='items')
    equipment = db.relationship('Resource', foreign_keys=[equipment_id])
    
    __table_args__ = (
        Index('idx_eq_req_item_request', 'request_id'),
        Index('idx_eq_req_item_equipment', 'equipment_id'),
    )


class EquipmentDelivery(db.Model):
    """عمليات تسليم المعدات"""
    __tablename__ = 'equipment_deliveries'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    request_id = db.Column(db.Integer, db.ForeignKey('equipment_requests.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # بيانات التسليم
    delivery_date = db.Column(db.DateTime, default=datetime.utcnow)
    delivery_number = db.Column(db.String(50), unique=True)
    
    # المعدات المسلمة
    delivered_items = db.Column(db.JSON)  # [{equipment_id, name, quantity, unit, notes}]
    
    # موقع التسليم
    delivery_location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    
    # الصور
    photos = db.Column(db.JSON)
    
    notes = db.Column(db.Text)
    
    # حالة التسليم
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, rejected, partially_confirmed
    
    # التأكيد
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    confirmed_at = db.Column(db.DateTime)
    confirmation_notes = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)
    
    # معلومات المعدات المسلمة (حالتها وموقعها)
    equipment_condition = db.Column(db.String(50))  # new, used, good, needs_maintenance
    equipment_serial_numbers = db.Column(db.JSON)  # أرقام مسلسلة للمعدات
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    request = db.relationship('EquipmentRequest', backref='deliveries')
    supplier = db.relationship('User', foreign_keys=[supplier_id])
    confirmer = db.relationship('User', foreign_keys=[confirmed_by])
    
    __table_args__ = (
        Index('idx_eq_delivery_request', 'request_id'),
        Index('idx_eq_delivery_supplier', 'supplier_id'),
        Index('idx_eq_delivery_status', 'status'),
        Index('idx_eq_delivery_date', 'delivery_date'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'delivery_number': self.delivery_number,
            'delivery_date': self.delivery_date.strftime('%Y-%m-%d %H:%M') if self.delivery_date else None,
            'delivered_items': self.delivered_items,
            'delivery_location': self.delivery_location,
            'status': self.status,
            'photos': self.photos,
            'confirmation_notes': self.confirmation_notes,
            'rejection_reason': self.rejection_reason,
            'confirmed_by': self.confirmer.full_name if self.confirmer else None,
            'confirmed_at': self.confirmed_at.strftime('%Y-%m-%d %H:%M') if self.confirmed_at else None,
            'equipment_condition': self.equipment_condition,
            'equipment_serial_numbers': self.equipment_serial_numbers
        }


class EquipmentDeliveryUpdate(db.Model):
    """تحديثات عمليات تسليم المعدات"""
    __tablename__ = 'equipment_delivery_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    delivery_id = db.Column(db.Integer, db.ForeignKey('equipment_deliveries.id'), nullable=False)
    
    old_status = db.Column(db.String(20))
    new_status = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    updater = db.relationship('User', foreign_keys=[updated_by])
    
    __table_args__ = (
        Index('idx_eq_delivery_update_delivery', 'delivery_id'),
    )


class EquipmentOfferHistory(db.Model):
    """سجل عروض أسعار المعدات"""
    __tablename__ = 'equipment_offer_histories'
    
    id = db.Column(db.Integer, primary_key=True)
    request_item_id = db.Column(db.Integer, db.ForeignKey('equipment_request_items.id'), nullable=False)
    
    offer_price = db.Column(db.Float, nullable=False)
    offer_currency = db.Column(db.String(3), default='SAR')
    offer_notes = db.Column(db.Text)
    
    status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_notes = db.Column(db.Text)
    
    submitted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    request_item = db.relationship('EquipmentRequestItem', backref='offer_history')
    approver = db.relationship('User', foreign_keys=[approved_by])
    submitter = db.relationship('User', foreign_keys=[submitted_by])
    
    __table_args__ = (
        Index('idx_eq_offer_request_item', 'request_item_id'),
        Index('idx_eq_offer_status', 'status'),
    )
class Baseline(db.Model):
    """خط الأساس للمقارنة"""
    __tablename__ = 'baselines'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)
    version = db.Column(db.Integer, default=1)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # بيانات Baseline (JSON)
    activities_snapshot = db.Column(db.JSON)
    relationships_snapshot = db.Column(db.JSON)
    resources_snapshot = db.Column(db.JSON)
    
    # إحصائيات
    planned_start = db.Column(db.DateTime)
    planned_finish = db.Column(db.DateTime)
    total_cost = db.Column(db.Float, default=0.0)
    # العلاقات
    project = db.relationship('Project', backref='baselines')
    creator = db.relationship('User', foreign_keys=[created_by])
    __table_args__ = (
        Index('idx_baseline_project', 'project_id'),
        UniqueConstraint('project_id', 'version', name='uq_baseline_version'),
    )


# ============================================
# 🔟 نماذج إضافية للأنشطة (Steps, Expenses, Risks, etc.)
# ============================================

class ActivityStep(db.Model):
    """خطوات تنفيذ النشاط"""
    __tablename__ = 'activity_steps'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    order = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime)
    completed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    activity = db.relationship('Activity', backref='steps')
    completer = db.relationship('User', foreign_keys=[completed_by])
    
    __table_args__ = (
        Index('idx_step_activity', 'activity_id'),
        Index('idx_step_order', 'activity_id', 'order'),
        UniqueConstraint('activity_id', 'order', name='uq_step_order'),
    )

    
class ActivityExpense(db.Model):
    """مصروفات النشاط"""
    __tablename__ = 'activity_expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    expense_date = db.Column(db.Date, default=date.today)
    category = db.Column(db.String(50))  # labor, material, equipment, transport, other
    description = db.Column(db.String(500))
    
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='SAR')
    
    is_approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    
    receipt_url = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    activity = db.relationship('Activity', backref='expenses')
    approver = db.relationship('User', foreign_keys=[approved_by])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_expense_activity', 'activity_id'),
        Index('idx_expense_date', 'expense_date'),
        Index('idx_expense_category', 'category'),
    )


class ActivityRisk(db.Model):
    """مخاطر النشاط"""
    __tablename__ = 'activity_risks'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    risk_level = db.Column(db.String(20), default='medium')  # low, medium, high
    probability = db.Column(db.Integer, default=50)  # 0-100
    impact = db.Column(db.String(20), default='medium')  # very_low, low, medium, high, very_high
    
    mitigation_plan = db.Column(db.Text)
    contingency_plan = db.Column(db.Text)
    
    status = db.Column(db.String(50), default='identified')  # identified, mitigated, closed
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    activity = db.relationship('Activity', backref='risks')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_risk_activity', 'activity_id'),
        Index('idx_risk_activity_level', 'risk_level'),
        Index('idx_risk_activity_status', 'status'),
    )


class ActivityFeedback(db.Model):
    """تعليقات وملاحظات على النشاط"""
    __tablename__ = 'activity_feedback'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    content = db.Column(db.Text, nullable=False)
    attachment_url = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    activity = db.relationship('Activity', backref='feedback')
    user = db.relationship('User', foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_feedback_activity', 'activity_id'),
        Index('idx_feedback_user', 'user_id'),
        Index('idx_feedback_created', 'created_at'),
    )


class ActivityDocument(db.Model):
    """مستندات النشاط"""
    __tablename__ = 'activity_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(100))
    file_extension = db.Column(db.String(20))
    mime_type = db.Column(db.String(100))
    
    file_path = db.Column(db.String(1000))
    file_url = db.Column(db.String(1000))
    thumbnail_url = db.Column(db.String(1000))

    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    # المهمة المصدر (إذا كان الملف مرفوعاً من مهمة)
    source_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    # التوقيع والموافقة
    requires_approval = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    approval_notes = db.Column(db.Text)

    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # العلاقات
    
    activity = db.relationship('Activity', backref='document')
    source_task = db.relationship('Task', foreign_keys=[source_task_id], backref='activity_documents')
    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    approver = db.relationship('User', foreign_keys=[approved_by])

    __table_args__ = (
        Index('idx_document_activity', 'activity_id'),
        Index('idx_document_task', 'source_task_id'),
        Index('idx_document_upload', 'uploaded_by'),
        Index('idx_document_approved', 'approved_by'),
    )
"""
integrated_models.py - النماذج المتكاملة لإدارة المشاريع (متوافقة مع Primavera P6)
"""

from app.extensions import db
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from datetime import datetime, date
import uuid

# ============================================
# 🏢 النماذج الأساسية (Base Models)
# ============================================

class BaseModel(db.Model):
    """نموذج أساسي يحتوي على الحقول المشتركة"""
    __abstract__ = True
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    is_active = db.Column(db.Boolean, default=True)


# ============================================
# 🏗️ EPS – Enterprise Project Structure
# ============================================

class EPS(BaseModel):
    """هيكل المؤسسة للمشاريع - Enterprise Project Structure"""
    __tablename__ = 'eps'
    
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    eps_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('eps.id'))
    level = db.Column(db.Integer, default=1)
    path = db.Column(db.String(500))  # المسار الكامل مثل: 1.2.3
    
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    parent = db.relationship('EPS', remote_side=[id], backref='children')
    manager = db.relationship('User', foreign_keys=[manager_id])
    projects = db.relationship('Project', backref='eps', lazy='dynamic')
    obs_permissions = db.relationship('EPSOBSAssignment', back_populates='eps', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_eps_org', 'org_id'),
        Index('idx_eps_code', 'eps_code'),
        Index('idx_eps_parent', 'parent_id'),
        UniqueConstraint('org_id', 'eps_code', name='uq_eps_code'),
    )
    
    def get_full_path(self):
        """الحصول على المسار الكامل"""
        if self.parent:
            return f"{self.parent.get_full_path()} / {self.name}"
        return self.name


class OBS(BaseModel):
    """Organizational Breakdown Structure - هيكل المسؤولية"""
    __tablename__ = 'obs'
    
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    obs_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('obs.id'))
    level = db.Column(db.Integer, default=1)
    path = db.Column(db.String(500))
    
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    parent = db.relationship('OBS', remote_side=[id], backref='children')
    responsible = db.relationship('User', foreign_keys=[responsible_id])
    
    __table_args__ = (
        Index('idx_obs_org', 'org_id'),
        Index('idx_obs_code', 'obs_code'),
        Index('idx_obs_parent', 'parent_id'),
        UniqueConstraint('org_id', 'obs_code', name='uq_obs_code'),
    )


class EPSOBSAssignment(BaseModel):
    """ربط EPS مع OBS لتحديد الصلاحيات"""
    __tablename__ = 'eps_obs_assignments'
    
    eps_id = db.Column(db.Integer, db.ForeignKey('eps.id'), nullable=False)
    obs_id = db.Column(db.Integer, db.ForeignKey('obs.id'), nullable=False)
    
    permission_level = db.Column(db.String(20), default='read')  # read, write, admin
    
    # العلاقات
    eps = db.relationship('EPS', back_populates='obs_permissions')
    obs = db.relationship('OBS')
    
    __table_args__ = (
        Index('idx_eps_obs_eps', 'eps_id'),
        Index('idx_eps_obs_obs', 'obs_id'),
        UniqueConstraint('eps_id', 'obs_id', name='uq_eps_obs'),
    )


# ============================================
# 📅 التقويمات (Calendars)
# ============================================

class Calendar(BaseModel):
    """التقويم الزمني للمشروع"""
    __tablename__ = 'calendars'
    
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)
    name_ar = db.Column(db.String(100))
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
        weekday = day_date.isoweekday()
        weekday = (weekday % 7) + 1 if weekday != 7 else 1
        
        if weekday not in self.work_days:
            return False
        
        if day_date.isoformat() in self.holidays:
            return False
        
        return True


# ============================================
# 📊 المشروع (Project)
# ============================================

class Project(BaseModel):
    """المشروع الرئيسي"""
    __tablename__ = "projects"
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    project_code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)

    # الهيكل التنظيمي
    eps_id = db.Column(db.Integer, db.ForeignKey("eps.id"))
    obs_id = db.Column(db.Integer, db.ForeignKey("obs.id"))

    # التقويمات
    calendar_id = db.Column(db.Integer, db.ForeignKey("calendars.id"))
    financial_calendar_id = db.Column(db.Integer, db.ForeignKey("calendars.id"))

    # الحالة والإعدادات
    status = db.Column(db.String(50), default="planning")
    priority_level = db.Column(db.Integer, default=50)  # 1-100
    risk_level = db.Column(db.String(20), default="medium")  # low, medium, high, critical
    category = db.Column(db.String(50))
    project_type = db.Column(db.String(50))
    is_template = db.Column(db.Boolean, default=False)

    # التحكم
    checked_out_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    #المالك
    client_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    checked_out_at = db.Column(db.DateTime)
    website = db.Column(db.String(500))

    # العلاقات
    dates = db.relationship("ProjectDates", backref="project", uselist=False, cascade="all, delete-orphan")
    budget = db.relationship("ProjectBudget", backref="project", uselist=False, cascade="all, delete-orphan")
    performance = db.relationship("ProjectPerformance", backref="project", uselist=False, cascade="all, delete-orphan")
    cost = db.relationship("ProjectCost", backref="project", uselist=False, cascade="all, delete-orphan")
    progress = db.relationship("ProjectProgress", backref="project", uselist=False, cascade="all, delete-orphan")
    location = db.relationship("ProjectLocation", backref="project", uselist=False, cascade="all, delete-orphan")
    statistics = db.relationship("ProjectStatistics", backref="project", uselist=False, cascade="all, delete-orphan")
    codes = db.relationship("ProjectCode", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    udfs = db.relationship("ProjectUDF", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    funding_sources = db.relationship("FundingSource", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    spending_plan = db.relationship("SpendingPlanItem", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    budget_logs = db.relationship("BudgetLog", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    activities = db.relationship("Activity", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    tasks = db.relationship("Task", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    wbs_nodes = db.relationship("WBS", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    notebook_entries = db.relationship("NotebookEntry", backref="project", lazy="dynamic", cascade="all, delete-orphan")
    meetings = db.relationship('Meeting', backref='project', lazy=True)
    daily_reports = db.relationship('DailyReport', backref='project', lazy=True)
    risks = db.relationship('Risk', backref='project', lazy=True)
    issues = db.relationship('Issue', backref='project', lazy=True)
    milestones = db.relationship('Milestone', backref='project', lazy=True)
    documents = db.relationship('ProjectDocument', backref='project', lazy=True)
    bill_items = db.relationship('BillItem', backref='project', lazy=True)
    __table_args__ = (
        Index("idx_project_eps", "eps_id"),
        Index("idx_project_status", "status"),
        Index("idx_project_code", "project_code"),
        Index("idx_project_priority", "priority_level"),
    )

    @property
    def remaining_days(self):
        """الأيام المتبقية حتى الانتهاء"""
        if self.dates and self.dates.planned_finish:
            return (self.dates.planned_finish.date() - date.today()).days
        return 0

    @property
    def is_overdue(self):
        """هل المشروع متأخر"""
        if self.dates and self.dates.planned_finish:
            return date.today() > self.dates.planned_finish.date() and self.status != 'completed'
        return False

    def get_progress(self):
        """الحصول على نسبة التقدم"""
        if self.progress:
            return self.progress.progress_percentage
        return 0.0

    def get_budget_status(self):
        """الحصول على حالة الميزانية"""
        if self.budget and self.cost:
            return {
                'planned': self.budget.current_budget,
                'actual': self.cost.total_actual_cost,
                'variance': self.budget.current_budget - self.cost.total_actual_cost,
                'percent_spent': (self.cost.total_actual_cost / self.budget.current_budget * 100) if self.budget.current_budget else 0
            }
        return {}


class ProjectLocation(BaseModel):
    """موقع المشروع"""
    __tablename__ = "project_locations"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    site_name = db.Column(db.String(500))
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    address = db.Column(db.Text)
    coordinates = db.Column(db.String(100))


class ProjectDates(BaseModel):
    """تواريخ المشروع"""
    __tablename__ = "project_dates"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    planned_start = db.Column(db.DateTime)
    planned_finish = db.Column(db.DateTime)
    actual_start = db.Column(db.DateTime)
    actual_finish = db.Column(db.DateTime)
    baseline_start = db.Column(db.DateTime)
    baseline_finish = db.Column(db.DateTime)
    anticipated_start = db.Column(db.DateTime)
    anticipated_finish = db.Column(db.DateTime)
    must_finish_by = db.Column(db.DateTime)
    data_date = db.Column(db.DateTime, default=datetime.utcnow)
    expected_finish = db.Column(db.DateTime)
    late_finish = db.Column(db.DateTime)


class ProjectBudget(BaseModel):
    """ميزانية المشروع"""
    __tablename__ = "project_budgets"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    original_budget = db.Column(db.Float, default=0.0)
    current_budget = db.Column(db.Float, default=0.0)
    proposed_budget = db.Column(db.Float, default=0.0)
    unallocated_budget = db.Column(db.Float, default=0.0)
    distributed_budget = db.Column(db.Float, default=0.0)


class ProjectCost(BaseModel):
    """تكاليف المشروع"""
    __tablename__ = "project_costs"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    total_planned_cost = db.Column(db.Float, default=0.0)
    total_actual_cost = db.Column(db.Float, default=0.0)
    labor_cost = db.Column(db.Float, default=0.0)
    material_cost = db.Column(db.Float, default=0.0)
    equipment_cost = db.Column(db.Float, default=0.0)
    other_cost = db.Column(db.Float, default=0.0)


class ProjectPerformance(BaseModel):
    """أداء المشروع - القيمة المكتسبة"""
    __tablename__ = "project_performance"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    planned_value = db.Column(db.Float, default=0.0)  # PV
    earned_value = db.Column(db.Float, default=0.0)  # EV
    actual_cost = db.Column(db.Float, default=0.0)  # AC

    spi = db.Column(db.Float, default=1.0)  # Schedule Performance Index
    cpi = db.Column(db.Float, default=1.0)  # Cost Performance Index
    csi = db.Column(db.Float, default=1.0)  # Cost Schedule Index

    eac = db.Column(db.Float)  # Estimate at Completion
    etc = db.Column(db.Float)  # Estimate to Complete
    vac = db.Column(db.Float)  # Variance at Completion


class ProjectProgress(BaseModel):
    """تقدم المشروع"""
    __tablename__ = "project_progress"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    progress_percentage = db.Column(db.Float, default=0.0)
    physical_progress = db.Column(db.Float, default=0.0)
    performance_progress = db.Column(db.Float, default=0.0)

    total_float = db.Column(db.Float, default=0.0)
    free_float = db.Column(db.Float, default=0.0)
    float_path = db.Column(db.String(50))


class ProjectStatistics(BaseModel):
    """إحصائيات المشروع"""
    __tablename__ = "project_statistics"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    total_activities = db.Column(db.Integer, default=0)
    completed_activities = db.Column(db.Integer, default=0)
    in_progress_activities = db.Column(db.Integer, default=0)
    not_started_activities = db.Column(db.Integer, default=0)
    critical_activities = db.Column(db.Integer, default=0)
    
    total_tasks = db.Column(db.Integer, default=0)
    completed_tasks = db.Column(db.Integer, default=0)
    
    total_resources = db.Column(db.Integer, default=0)
    total_manpower = db.Column(db.Integer, default=0)
    
    last_calculated = db.Column(db.DateTime, default=datetime.utcnow)

    def update(self):
        """تحديث الإحصائيات"""
        self.total_activities = Activity.query.filter_by(project_id=self.project_id).count()
        self.completed_activities = Activity.query.filter_by(project_id=self.project_id, status='completed').count()
        self.in_progress_activities = Activity.query.filter_by(project_id=self.project_id, status='in_progress').count()
        self.not_started_activities = Activity.query.filter_by(project_id=self.project_id, status='not_started').count()
        self.critical_activities = Activity.query.filter_by(project_id=self.project_id, is_critical=True).count()
        
        self.total_tasks = Task.query.filter_by(project_id=self.project_id).count()
        self.completed_tasks = Task.query.filter_by(project_id=self.project_id, status='completed').count()
        
        self.last_calculated = datetime.utcnow()


class ProjectCode(BaseModel):
    """أكواد المشروع"""
    __tablename__ = "project_codes"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))

    code_type = db.Column(db.String(100), nullable=False)  # region, sector, department, etc.
    code_value = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500))
    
    __table_args__ = (
        UniqueConstraint('project_id', 'code_type', name='uq_project_code_type'),
    )


class ProjectUDF(BaseModel):
    """الحقول المخصصة للمشروع"""
    __tablename__ = "project_udf"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))

    udf_name = db.Column(db.String(200), nullable=False)
    udf_value = db.Column(db.Text)
    udf_type = db.Column(db.String(50), default='text')  # text, number, date, boolean
    
    __table_args__ = (
        UniqueConstraint('project_id', 'udf_name', name='uq_project_udf'),
    )


# ============================================
# 💰 الميزانية والتمويل (Budget & Funding)
# ============================================

class BudgetLog(BaseModel):
    """سجل تغييرات الميزانية"""
    __tablename__ = 'budget_logs'
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    change_number = db.Column(db.String(50))
    amount = db.Column(db.Float, nullable=False)
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(20), default='Proposed')  # Proposed, Approved, Rejected
    reason = db.Column(db.String(500))
    
    # العلاقات
    responsible = db.relationship('User', foreign_keys=[responsible_id])


class FundingSource(BaseModel):
    """مصادر التمويل"""
    __tablename__ = 'funding_sources'
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    source_name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    share_percentage = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    status = db.Column(db.String(20), default='Proposed')  # Proposed, Approved, Received


class SpendingPlanItem(BaseModel):
    """بنود خطة الصرف"""
    __tablename__ = 'spending_plan_items'
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    planned_amount = db.Column(db.Float, default=0.0)
    benefit_amount = db.Column(db.Float, default=0.0)
    actual_amount = db.Column(db.Float, default=0.0)
    
    # حقول محسوبة
    variance = db.Column(db.Float, default=0.0)
    spending_tally = db.Column(db.Float, default=0.0)
    benefit_tally = db.Column(db.Float, default=0.0)


# ============================================
# 📋 WBS – Work Breakdown Structure
# ============================================

class WBS(BaseModel):
    """هيكل تقسيم العمل - Work Breakdown Structure"""
    __tablename__ = 'wbs'
    
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
    
    # التقدم
    progress_percentage = db.Column(db.Float, default=0.0)
    
    # الحقول المخصصة
    udf_values = db.Column(db.JSON, default={})
    
    # العلاقات
    parent = db.relationship('WBS', remote_side=[id], backref='children')
    activities = db.relationship('Activity', backref='wbs', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_wbs_project', 'project_id'),
        Index('idx_wbs_parent', 'parent_id'),
        Index('idx_wbs_level', 'level'),
        UniqueConstraint('project_id', 'wbs_code', name='uq_wbs_code'),
    )
    
    def calculate_progress(self):
        """حساب التقدم من الأنشطة الفرعية"""
        activities = self.activities.all()
        if activities:
            total_weight = sum(a.weight for a in activities if a.weight)
            if total_weight > 0:
                weighted_progress = sum(a.progress_percentage * a.weight for a in activities if a.weight)
                self.progress_percentage = weighted_progress / total_weight
            else:
                self.progress_percentage = sum(a.progress_percentage for a in activities) / len(activities)
        
        return self.progress_percentage


# ============================================
# ⚡ النشاط (Activity)
# ============================================

class Activity(BaseModel):
    """الأنشطة"""
    __tablename__ = "activities"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    wbs_id = db.Column(db.Integer, db.ForeignKey("wbs.id"))
    calendar_id = db.Column(db.Integer, db.ForeignKey("calendars.id"))

    activity_code = db.Column(db.String(50), index=True, nullable=False)
    activity_name = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)

    # النوع والحالة
    activity_type = db.Column(db.String(50), default='task_dependent')
    status = db.Column(db.String(50), default="not_started")
    priority = db.Column(db.Integer, default=3)  # 1-5
    weight = db.Column(db.Float, default=1.0)

    # المسؤولون
    responsible_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    supervisor_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    delegate_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    # التواريخ
    planned_start = db.Column(db.DateTime)
    planned_finish = db.Column(db.DateTime)
    actual_start = db.Column(db.DateTime)
    actual_finish = db.Column(db.DateTime)
    early_start = db.Column(db.DateTime)
    early_finish = db.Column(db.DateTime)
    late_start = db.Column(db.DateTime)
    late_finish = db.Column(db.DateTime)

    # المدة
    original_duration = db.Column(db.Float, default=0.0)
    remaining_duration = db.Column(db.Float, default=0.0)
    actual_duration = db.Column(db.Float, default=0.0)
    at_complete_duration = db.Column(db.Float, default=0.0)

    # التقدم
    progress_percentage = db.Column(db.Float, default=0.0)
    physical_progress = db.Column(db.Float, default=0.0)

    # Float
    total_float = db.Column(db.Float, default=0.0)
    free_float = db.Column(db.Float, default=0.0)
    is_critical = db.Column(db.Boolean, default=False)

    # القيمة المكتسبة
    planned_value = db.Column(db.Float, default=0.0)
    earned_value = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)

    # القيود
    primary_constraint = db.Column(db.String(50))
    secondary_constraint = db.Column(db.String(50))
    constraint_date = db.Column(db.DateTime)

    # الموقع
    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))

    # أكواد النشاط
    activity_code_values = db.Column(db.JSON, default={})

    # العلاقات
    tasks = db.relationship("Task", backref="activity", lazy="dynamic", cascade="all, delete-orphan")
    steps = db.relationship("ActivityStep", backref="activity", lazy="dynamic", cascade="all, delete-orphan")
    expenses = db.relationship("ActivityExpense", backref="activity", lazy="dynamic", cascade="all, delete-orphan")
    risks = db.relationship("ActivityRisk", backref="activity", lazy="dynamic", cascade="all, delete-orphan")
    documents = db.relationship("ActivityDocument", backref="activity", lazy="dynamic", cascade="all, delete-orphan")
    feedback = db.relationship("ActivityFeedback", backref="activity", lazy="dynamic", cascade="all, delete-orphan")
    resources = db.relationship("ActivityResource", backref="activity", lazy="dynamic", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_activity_project", "project_id"),
        Index("idx_activity_code", "activity_code"),
        Index("idx_activity_status", "status"),
        Index("idx_activity_critical", "is_critical"),
        UniqueConstraint('project_id', 'activity_code', name='uq_activity_project_code'),
        CheckConstraint('progress_percentage >= 0 AND progress_percentage <= 100', name='chk_activity_progress'),
    )

    @property
    def is_milestone(self):
        return self.activity_type in ['start_milestone', 'finish_milestone']

    @property
    def is_completed(self):
        return self.status == 'completed'

    def update_progress_from_tasks(self):
        """تحديث التقدم بناءً على المهام"""
        tasks = self.tasks.all()
        if tasks:
            total_weight = len(tasks)
            completed = sum(1 for t in tasks if t.status == 'completed')
            self.progress_percentage = (completed / total_weight) * 100





class ActivityExpense(BaseModel):
    """مصروفات النشاط"""
    __tablename__ = "activity_expenses"

    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    
    expense_date = db.Column(db.Date, default=date.today)
    category = db.Column(db.String(50))  # labor, material, equipment, transport, other
    description = db.Column(db.String(500))
    
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='SAR')
    
    is_approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    
    receipt_url = db.Column(db.String(500))
    
    __table_args__ = (
        Index('idx_expense_activity', 'activity_id'),
        Index('idx_expense_date', 'expense_date'),
    )


class ActivityRisk(BaseModel):
    """مخاطر النشاط"""
    __tablename__ = "activity_risks"

    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    risk_level = db.Column(db.String(20), default='medium')  # low, medium, high
    probability = db.Column(db.Integer, default=50)  # 0-100
    impact = db.Column(db.String(20), default='medium')  # very_low, low, medium, high, very_high
    
    mitigation_plan = db.Column(db.Text)
    contingency_plan = db.Column(db.Text)
    
    status = db.Column(db.String(50), default='identified')  # identified, mitigated, closed
    
    __table_args__ = (
        Index('idx_risk_activity', 'activity_id'),
        Index('idx_risk_level', 'risk_level'),
    )


class ActivityFeedback(BaseModel):
    """تعليقات وملاحظات على النشاط"""
    __tablename__ = "activity_feedback"

    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    content = db.Column(db.Text, nullable=False)
    attachment_url = db.Column(db.String(500))
    
    __table_args__ = (
        Index('idx_feedback_activity', 'activity_id'),
        Index('idx_feedback_user', 'user_id'),
    )


class ActivityDocument(BaseModel):
    """مستندات النشاط"""
    __tablename__ = "activity_documents"

    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255))
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    file_url = db.Column(db.String(500))
    file_size = db.Column(db.Integer)
    file_type = db.Column(db.String(100))
    
    requires_approval = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    approved_at = db.Column(db.DateTime)
    approval_status = db.Column(db.String(50), default='pending')  # pending, approved, rejected

    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    
    __table_args__ = (
        Index('idx_document_activity', 'activity_id'),
    )


# ============================================
# 📋 المهام (Task)
# ============================================

class Task(BaseModel):
    """المهام"""
    __tablename__ = "tasks"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"))
    wbs_id = db.Column(db.Integer, db.ForeignKey("wbs.id"))

    task_code = db.Column(db.String(50), nullable=False)
    task_name = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)

    # الترتيب والتبعية
    task_order = db.Column(db.Integer)
    depends_on_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"))

    # المسؤولون
    supervisor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    delegate_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    assigned_users = db.Column(db.JSON, default=[])

    # الحالة
    status = db.Column(db.String(50), default="pending")
    priority = db.Column(db.Integer, default=3)  # 1-5
    completion_quality = db.Column(db.String(20))  # excellent, good, fair, poor

    # الموقع
    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))

    # العلاقات
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


class TaskPlanning(BaseModel):
    """تخطيط المهمة"""
    __tablename__ = "task_planning"

    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    planned_start = db.Column(db.Date)
    planned_finish = db.Column(db.Date)
    planned_duration = db.Column(db.Float)  # بالساعات
    estimated_effort = db.Column(db.Float)  # جهد مقدر (ساعة رجل)


class TaskExecution(BaseModel):
    """تنفيذ المهمة"""
    __tablename__ = "task_execution"

    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    actual_start = db.Column(db.DateTime)
    actual_finish = db.Column(db.DateTime)
    actual_duration = db.Column(db.Float)  # بالساعات


class TaskProgress(BaseModel):
    """تقدم المهمة"""
    __tablename__ = "task_progress"

    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    progress_percentage = db.Column(db.Float, default=0.0)
    completion_quality = db.Column(db.String(20))
    
    __table_args__ = (
        CheckConstraint('progress_percentage >= 0 AND progress_percentage <= 100', name='chk_task_progress'),
    )


class TaskLocation(BaseModel):
    """موقع المهمة"""
    __tablename__ = "task_locations"

    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))


class TaskVerification(BaseModel):
    """التحقق من المهمة"""
    __tablename__ = "task_verifications"

    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), unique=True)

    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    verified_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)


class TaskAssignment(BaseModel):
    """تعيين المهام للمستخدمين"""
    __tablename__ = "task_assignments"

    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    assigned_by = db.Column(db.Integer)
    
    status = db.Column(db.String(50), default='assigned')  # assigned, accepted, rejected, completed
    acceptance_date = db.Column(db.DateTime)
    completion_date = db.Column(db.DateTime)
    
    quality_rating = db.Column(db.Integer)  # 1-5
    efficiency_rating = db.Column(db.Integer)  # 1-5
    notes = db.Column(db.Text)

    __table_args__ = (
        Index('idx_assignment_task', 'task_id'),
        Index('idx_assignment_user', 'user_id'),
        Index('idx_assignment_status', 'status'),
        UniqueConstraint('task_id', 'user_id', name='uq_task_user_assignment'),
    )


class TaskResource(BaseModel):
    """موارد المهمة"""
    __tablename__ = "task_resources"

    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"))
    
    resource_type = db.Column(db.String(50))  # labor, material, equipment
    resource_name = db.Column(db.String(200))
    quantity = db.Column(db.Float, default=0.0)
    unit = db.Column(db.String(50))
    cost = db.Column(db.Float, default=0.0)


class TaskDependency(BaseModel):
    """تبعيات المهام"""
    __tablename__ = "task_dependencies"

    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    
    predecessor_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    successor_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    
    dependency_type = db.Column(db.String(20), default='FS')  # FS, SS, FF, SF
    lag = db.Column(db.Float, default=0.0)
    lag_type = db.Column(db.String(20), default='days')  # days, hours
    
    is_critical = db.Column(db.Boolean, default=False)
    is_driving = db.Column(db.Boolean, default=False)
    
    __table_args__ = (
        Index('idx_dependency_project', 'project_id'),
        Index('idx_dependency_predecessor', 'predecessor_task_id'),
        Index('idx_dependency_successor', 'successor_task_id'),
        UniqueConstraint('predecessor_task_id', 'successor_task_id', name='uq_task_dependency'),
    )


# ============================================
# 📦 الموارد (Resources)
# ============================================

class Resource(BaseModel):
    """الموارد (عمال، معدات، مواد)"""
    __tablename__ = 'resources'
    
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    resource_id = db.Column(db.String(50), nullable=False, unique=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    # نوع المورد
    resource_type = db.Column(db.String(50), nullable=False)  # labor, material, equipment, non_labor
    
    # الوحدة والتكلفة
    unit = db.Column(db.String(50))
    cost_per_unit = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    available_quantity = db.Column(db.Float, default=0.0)
    
    # التقويم والدور
    calendar_id = db.Column(db.Integer, db.ForeignKey('calendars.id'))
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'))
    
    # المواصفات
    specifications = db.Column(db.JSON)
    resource_code_values = db.Column(db.JSON, default={})
    
    # الحقول المخصصة
    udf_values = db.Column(db.JSON, default={})
    
    # العلاقات
    calendar = db.relationship('Calendar')
    role = db.relationship('Role', foreign_keys=[role_id])
    assignments = db.relationship('ActivityResource', backref='resource', lazy='dynamic')
    task_assignments = db.relationship('TaskResource', backref='resource', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_resource_org', 'org_id'),
        Index('idx_resource_id', 'resource_id'),
        Index('idx_resource_type', 'resource_type'),
    )


class ActivityResource(BaseModel):
    """تخصيص الموارد للأنشطة"""
    __tablename__ = 'activity_resources'
    
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=False)
    
    planned_quantity = db.Column(db.Float, default=0.0)
    actual_quantity = db.Column(db.Float, default=0.0)
    remaining_quantity = db.Column(db.Float, default=0.0)
    
    planned_cost = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)
    
    start_date = db.Column(db.DateTime)
    finish_date = db.Column(db.DateTime)
    
    allocated = db.Column(db.Boolean, default=True)
    
    __table_args__ = (
        Index('idx_act_res_activity', 'activity_id'),
        Index('idx_act_res_resource', 'resource_id'),
        UniqueConstraint('activity_id', 'resource_id', name='uq_activity_resource'),
    )


# ============================================
# 📝 دفتر الملاحظات (Notebook)
# ============================================

class NotebookEntry(BaseModel):
    """مدخلات دفتر الملاحظات"""
    __tablename__ = 'notebook_entries'
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    # نوع الإدخال
    entry_type = db.Column(db.String(50), nullable=False, default='note')
    # note, topic, issue, decision, question, action_item, risk, milestone, lesson
    
    # الحالة
    status = db.Column(db.String(50), default='open')
    # open, in_progress, closed, pending, approved, rejected
    
    # المحتوى الأساسي
    subject = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, nullable=False)
    
    # التصنيف
    category = db.Column(db.String(100))
    
    # أولوية
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    
    # تواريخ
    target_date = db.Column(db.Date)
    closed_at = db.Column(db.DateTime)
    
    # المسؤولون
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    
    # للإشارات والمرفقات
    mentions = db.Column(db.JSON, default=[])
    attachments = db.Column(db.JSON, default=[])
    
    # حقول خاصة حسب النوع
    decision_options = db.Column(db.JSON)
    decision_rationale = db.Column(db.Text)
    decision_impact = db.Column(db.Text)
    
    risk_probability = db.Column(db.Integer)
    risk_impact = db.Column(db.Integer)
    risk_score = db.Column(db.Integer)
    mitigation_plan = db.Column(db.Text)
    contingency_plan = db.Column(db.Text)
    
    answer = db.Column(db.Text)
    answered_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    answered_at = db.Column(db.DateTime)
    
    due_date = db.Column(db.Date)
    completed_at = db.Column(db.DateTime)
    completion_notes = db.Column(db.Text)
    
    lesson_category = db.Column(db.String(100))  # positive, negative, improvement
    
    # العلاقات
    creator = db.relationship('User', foreign_keys=[created_by])
    assignee = db.relationship('User', foreign_keys=[assigned_to])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    answerer = db.relationship('User', foreign_keys=[answered_by])
    comments = db.relationship('NotebookComment', backref='entry', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_notebook_project', 'project_id'),
        Index('idx_notebook_type', 'entry_type'),
        Index('idx_notebook_status', 'status'),
        Index('idx_notebook_created', 'created_at'),
    )


class NotebookComment(BaseModel):
    """تعليقات على مدخلات دفتر الملاحظات"""
    __tablename__ = 'notebook_comments'
    
    entry_id = db.Column(db.Integer, db.ForeignKey('notebook_entries.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    content = db.Column(db.Text, nullable=False)
    attachments = db.Column(db.JSON, default=[])
    mentions = db.Column(db.JSON, default=[])
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_notebook_comment_entry', 'entry_id'),
        Index('idx_notebook_comment_user', 'user_id'),
    )


# ============================================
# 📈 خط الأساس (Baseline)
# ============================================

class Baseline(BaseModel):
    """خط الأساس للمقارنة"""
    __tablename__ = 'baselines'
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)
    version = db.Column(db.Integer, default=1)
    
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
    
    __table_args__ = (
        Index('idx_baseline_project', 'project_id'),
        UniqueConstraint('project_id', 'version', name='uq_baseline_version'),
    )


# ============================================
# 🔗 العلاقات بين الأنشطة
# ============================================

class ActivityRelationship(BaseModel):
    """العلاقات بين الأنشطة"""
    __tablename__ = 'activity_relationships'
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    predecessor_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    successor_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    # نوع العلاقة
    relationship_type = db.Column(db.String(20), default='FS')  # FS, SS, FF, SF
    
    # التأخير
    lag_days = db.Column(db.Float, default=0.0)
    lag_type = db.Column(db.String(20), default='days')  # days, hours, percent
    
    # خصائص
    is_critical = db.Column(db.Boolean, default=False)
    is_driving = db.Column(db.Boolean, default=False)
    
    __table_args__ = (
        Index('idx_rel_project', 'project_id'),
        Index('idx_rel_predecessor', 'predecessor_id'),
        Index('idx_rel_successor', 'successor_id'),
        UniqueConstraint('predecessor_id', 'successor_id', name='uq_relationship'),
    )


# ============================================
# 👥 الأدوار الوظيفية (Roles)
# ============================================

class Role(BaseModel):
    """الأدوار الوظيفية"""
    __tablename__ = 'roles'
    
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    role_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    default_cost_per_hour = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    
    required_skills = db.Column(db.JSON, default=[])
    
    __table_args__ = (
        Index('idx_role_org', 'org_id'),
        Index('idx_role_code', 'role_code'),
        UniqueConstraint('org_id', 'role_code', name='uq_role_code'),
    )
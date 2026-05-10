"""
project_models.py - نماذج المشاريع والتخطيط
"""
from . import db
from sqlalchemy import Index, UniqueConstraint, ForeignKeyConstraint, CheckConstraint
from sqlalchemy.orm import relationship, backref
from datetime import datetime, date, timedelta
import uuid
from app.models.primavera_models import Activity
from app.models.task_models import Task

# ============================================
# 📊 المشروع (Project)
# ============================================


class Project(db.Model):
    """المشروع الرئيسي"""
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)

    name = db.Column(db.String(200), nullable=False)
    project_code = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)

    # الهيكل ال تنظيمي
    eps_id = db.Column(db.Integer, db.ForeignKey("eps.id"))
    obs_id = db.Column(db.Integer, db.ForeignKey("obs.id"))

    # التقويمات
    calendar_id = db.Column(db.Integer, db.ForeignKey("calendars.id"))
    financial_calendar_id = db.Column(db.Integer, db.ForeignKey("calendars.id"))

    # الحالة والإعدادات
    status = db.Column(db.String(50), default="planning")
    priority_level = db.Column(db.Integer, default=50)  # 1-100
    risk_level = db.Column(db.String(20), default="medium")  # low, medium, high, critical
    complexity = db.Column(db.String(20), default='medium')  # low, medium, high

    category = db.Column(db.String(50)) # حكومي، خاص، خيري
    project_type = db.Column(db.String(50)) # بناء، طرق، جسور، إلخ
    project_scale = db.Column(db.String(50))  # صغير، متوسط، كبير، عملاق
    is_template = db.Column(db.Boolean, default=False)
    # طريقة الجدولة
    schedule_method = db.Column(db.String(50), default='cpm')  # cpm, pert
    # التحكم
    checked_out_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    checked_out_date = db.Column(db.DateTime)
    #المالك
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    consultant_id=db.Column(db.Integer, db.ForeignKey('consultants.id'))
    supplier_id=db.Column(db.Integer, db.ForeignKey('suppliers.id'))

    website = db.Column(db.String(500))
    # حقول Settings
    last_summarized = db.Column(db.DateTime)
    summarize_level = db.Column(db.Integer, default=1)
    fiscal_year_start = db.Column(db.String(10), default='01-01')
    critical_definition = db.Column(db.String(50), default='Total Float <= 0')
    # إعدادات JSON
    settings = db.Column(db.JSON, default={})  # تخزين الإعدادات المتنوعة
    defaults = db.Column(db.JSON, default={})  # تخزين القيم الافتراضية
    calculation_settings = db.Column(db.JSON, default={})  # إعدادات الحسابات
    project_manager_id=db.Column(db.Integer, db.ForeignKey('users.id'))
    # حقول إضافية
    wbs_separator = db.Column(db.String(10), default='.')  # فاصل WBS
    float_threshold = db.Column(db.Float, default=0.0)  # حد العائم
    base_currency = db.Column(db.String(3), default='USD')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    # العلاقات
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
    activities = db.relationship("Activity", back_populates="project", lazy="dynamic", cascade="all, delete-orphan")
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
    def get_days_behind_schedule(self):
        """عدد الأيام المتأخرة عن الجدول"""
        if self.project.actual_start_date and self.project.planned_start_date:
            if self.project.actual_start_date > self.project.planned_start_date:
                return (self.project.actual_start_date - self.project.planned_start_date).days
        return 0
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

class Issue(db.Model):
    """قضايا المشروع"""
    __tablename__ = 'issues'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    
    issue_code = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    title_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    category = db.Column(db.String(100))  # technical, quality, safety, coordination, etc.
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    severity = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    
    reported_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reported_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_date = db.Column(db.DateTime)
    
    status = db.Column(db.String(50), default='open')  # open, assigned, in_progress, resolved, closed
    resolution = db.Column(db.Text)
    resolution_date = db.Column(db.DateTime)
    
    due_date = db.Column(db.Date)
    actual_completion_date = db.Column(db.Date)
    
    impact_days = db.Column(db.Integer, default=0)
    impact_cost = db.Column(db.Float, default=0.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    reporter = db.relationship('User', foreign_keys=[reported_by])
    assignee = db.relationship('User', foreign_keys=[assigned_to])
    
    # فهرسة
    __table_args__ = (
        Index('idx_issue_project', 'project_id'),
        Index('idx_issue_task', 'task_id'),
        Index('idx_issue_code', 'issue_code'),
        Index('idx_issue_status', 'status'),
        Index('idx_issue_priority', 'priority'),
        Index('idx_issue_reporter', 'reported_by'),
        Index('idx_issue_assignee', 'assigned_to'),
        Index('idx_issue_dates', 'reported_date', 'due_date'),
        UniqueConstraint('project_id', 'issue_code', name='uq_issue_code_project'),
    )


class QualityCheck(db.Model):
    """فحوصات الجودة"""
    __tablename__ = 'quality_checks'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    
    check_code = db.Column(db.String(50), nullable=False)
    check_name = db.Column(db.String(500), nullable=False)
    check_name_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    check_type = db.Column(db.String(100))  # inspection, test, review, audit
    standard = db.Column(db.String(200))  # المعيار المستخدم
    criteria = db.Column(db.JSON)  # معايير الفحص
    
    planned_date = db.Column(db.Date)
    actual_date = db.Column(db.Date)
    
    conducted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    witnessed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    status = db.Column(db.String(50), default='pending')  # pending, passed, failed, conditional
    result = db.Column(db.Text)
    score = db.Column(db.Float)  # النتيجة النسبية
    
    non_conformities = db.Column(db.JSON)  # عدم المطابقات
    corrective_actions = db.Column(db.Text)
    
    photos = db.Column(db.JSON)  # روابط الصور
    documents = db.Column(db.JSON)  # روابط المستندات
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    conductor = db.relationship('User', foreign_keys=[conducted_by])
    witness = db.relationship('User', foreign_keys=[witnessed_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_quality_project', 'project_id'),
        Index('idx_quality_task', 'task_id'),
        Index('idx_quality_code', 'check_code'),
        Index('idx_quality_status', 'status'),
        Index('idx_quality_date', 'actual_date'),
        Index('idx_quality_type', 'check_type'),
        UniqueConstraint('project_id', 'check_code', name='uq_quality_code_project'),
    )

class ProjectLocation(db.Model):
    """موقع المشروع"""
    __tablename__ = "project_locations"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    site_name = db.Column(db.String(500))
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    address = db.Column(db.Text)
    coordinates = db.Column(db.String(100))


class ProjectDates(db.Model):
    """تواريخ المشروع"""
    __tablename__ = "project_dates"

    id = db.Column(db.Integer, primary_key=True)
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


class ProjectBudget(db.Model):
    """ميزانية المشروع"""
    __tablename__ = "project_budgets"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    original_budget = db.Column(db.Float, default=0.0)
    current_budget = db.Column(db.Float, default=0.0)
    proposed_budget = db.Column(db.Float, default=0.0)
    unallocated_budget = db.Column(db.Float, default=0.0)
    distributed_budget = db.Column(db.Float, default=0.0)


class ProjectCost(db.Model):
    """تكاليف المشروع"""
    __tablename__ = "project_costs"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    total_planned_cost = db.Column(db.Float, default=0.0)
    total_actual_cost = db.Column(db.Float, default=0.0)
    labor_cost = db.Column(db.Float, default=0.0)
    material_cost = db.Column(db.Float, default=0.0)
    equipment_cost = db.Column(db.Float, default=0.0)
    other_cost = db.Column(db.Float, default=0.0)


class ProjectPerformance(db.Model):
    """أداء المشروع - القيمة المكتسبة"""
    __tablename__ = "project_performance"

    id = db.Column(db.Integer, primary_key=True)
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


class ProjectProgress(db.Model):
    """تقدم المشروع"""
    __tablename__ = "project_progress"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), unique=True)

    progress_percentage = db.Column(db.Float, default=0.0)
    physical_progress = db.Column(db.Float, default=0.0)
    performance_progress = db.Column(db.Float, default=0.0)
    performance_index = db.Column(db.Float, default=1.0)  # SPI
    
    total_float = db.Column(db.Float, default=0.0)
    free_float = db.Column(db.Float, default=0.0)
    float_path = db.Column(db.String(50))


class ProjectStatistics(db.Model):
    """إحصائيات المشروع"""
    __tablename__ = "project_statistics"
    id = db.Column(db.Integer, primary_key=True)
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


class ProjectCode(db.Model):
    """أكواد المشروع"""
    __tablename__ = "project_codes"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"))

    code_type = db.Column(db.String(100), nullable=False)  # region, sector, department, etc.
    code_value = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('project_id', 'code_type', name='uq_project_code_type'),
        Index('idx_code_project', 'project_id'),
        Index('idx_code_type', 'code_type'),
    )


class ProjectUDF(db.Model):
    """الحقول المخصصة للمشروع"""
    __tablename__ = "project_udf"
    id = db.Column(db.Integer, primary_key=True)
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

class BudgetLog(db.Model):
    """سجل تغييرات الميزانية"""
    __tablename__ = 'budget_logs'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    change_number = db.Column(db.String(50))
    amount = db.Column(db.Float, nullable=False)
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(20), default='Proposed')  # Proposed, Approved, Rejected
    reason = db.Column(db.String(500))
    
    # العلاقات
    responsible = db.relationship('User', foreign_keys=[responsible_id])


class FundingSource(db.Model):
    """مصادر التمويل"""
    __tablename__ = 'funding_sources'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    source_name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, default=0.0)
    share_percentage = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    status = db.Column(db.String(20), default='Proposed')  # Proposed, Approved, Received


class SpendingPlanItem(db.Model):
    """بنود خطة الصرف"""
    __tablename__ = 'spending_plan_items'
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    planned_amount = db.Column(db.Float, default=0.0)
    benefit_amount = db.Column(db.Float, default=0.0)
    actual_amount = db.Column(db.Float, default=0.0)
    
    # حقول محسوبة
    spending_tally = db.Column(db.Float, default=0.0)  # المجموع التراكمي للصرف
    benefit_tally = db.Column(db.Float, default=0.0)   # المجموع التراكمي للفوائد
    undistributed_variance = db.Column(db.Float, default=0.0)  # الفرق غير الموزع
    benefit_variance = db.Column(db.Float, default=0.0)  # فرق الفوائد

class NotebookEntry(db.Model):
    """مدخلات دفتر الملاحظات"""
    __tablename__ = 'notebook_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    # ===== حقول جديدة =====
    topic = db.Column(db.String(100), nullable=False)  # موضوع الملاحظة
    entry_type = db.Column(db.String(50), default='note')  # نوع الإدخال
    content = db.Column(db.Text, nullable=False)
    
    # التواريخ
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # المسؤول
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # العلاقات
    creator = db.relationship('User', foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_notebook_project', 'project_id'),
        Index('idx_notebook_topic', 'topic'),
        Index('idx_notebook_created', 'created_at'),
    )

class Milestone(db.Model):
    """معالم المشروع"""
    __tablename__ = 'milestones'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    wbs_node_id = db.Column(db.Integer, db.ForeignKey('wbs.id'))
    
    milestone_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    description = db.Column(db.Text)
    
    planned_date = db.Column(db.Date, nullable=False)
    actual_date = db.Column(db.Date)
    
    milestone_type = db.Column(db.String(50))  # contractual, technical, administrative
    weight = db.Column(db.Float, default=0.0)
    
    status = db.Column(db.String(50), default='pending')  # pending, achieved, delayed, cancelled
    achieved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    achieved_by_user = db.relationship('User', foreign_keys=[achieved_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_milestone_project', 'project_id'),
        Index('idx_milestone_date', 'planned_date'),
        Index('idx_milestone_status', 'status'),
        Index('idx_milestone_type', 'milestone_type'),
        UniqueConstraint('project_id', 'milestone_code', name='uq_milestone_code_project'),
    )


# ============================================================================
# جداول الموردين والعملاء
# ============================================================================

class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    client_code = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(50))  # government, private, individual
    
    contact_person = db.Column(db.String(200))
    position = db.Column(db.String(200))
    
    
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    country = db.Column(db.String(100))
    
    tax_number = db.Column(db.String(100))
    commercial_register = db.Column(db.String(100))
    
    rating = db.Column(db.Integer)  # 1-5
    payment_terms = db.Column(db.Text)
    credit_limit = db.Column(db.Float)
    
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = db.relationship('Project', backref='client',lazy="dynamic")
    # فهرسة
    __table_args__ = (
        Index('idx_client_code', 'client_code'),
        Index('idx_client_type', 'type'),
        Index('idx_client_active', 'is_active'),
        UniqueConstraint('user_id', 'client_code', name='uq_client_code_user'),
    )


class Consultant(db.Model):
    __tablename__ = 'consultants'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    consultant_code = db.Column(db.String(50), nullable=False)

    contact_person = db.Column(db.String(200))
    position = db.Column(db.String(200))

    specialization = db.Column(db.String(200))  # معماري، إنشائي، ميكانيكا، إلخ
    license_number = db.Column(db.String(100))
    
    rating = db.Column(db.Integer)
    daily_rate = db.Column(db.Float)
    
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    project = db.relationship('Project', backref='consult',lazy="dynamic")
    # فهرسة
    __table_args__ = (
        Index('idx_consultant_code', 'consultant_code'),
        Index('idx_consultant_specialization', 'specialization'),
        UniqueConstraint('user_id', 'consultant_code', name='uq_consultant_code_user'),
    )


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    supplier_code = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(50))  # material, equipment, subcontractor
    
    contact_person = db.Column(db.String(200))

    
    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    
    tax_number = db.Column(db.String(100))
    commercial_register = db.Column(db.String(100))
    
    rating = db.Column(db.Integer)
    delivery_lead_time = db.Column(db.Integer)  # بالأيام
    payment_terms = db.Column(db.Text)
    
    materials_provided = db.Column(db.JSON)  # قائمة المواد التي يوفرها
    equipment_provided = db.Column(db.JSON)  # قائمة المعدات
    
    is_approved = db.Column(db.Boolean, default=False)
    is_blacklisted = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    purchase_orders = db.relationship('PurchaseOrder', backref='supplier', lazy=True)
    project = db.relationship('Project', backref='supplier',lazy="dynamic")
    # فهرسة
    __table_args__ = (
        Index('idx_supplier_code', 'supplier_code'),
        Index('idx_supplier_type', 'type'),
        Index('idx_supplier_approved', 'is_approved'),
        Index('idx_supplier_blacklisted', 'is_blacklisted'),
        UniqueConstraint('user_id', 'supplier_code', name='uq_supplier_code_user'),
    )

class PurchaseOrder(db.Model):
    """طلبات الشراء"""
    __tablename__ = 'purchase_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'), nullable=False)
    
    po_number = db.Column(db.String(50), nullable=False)
    po_date = db.Column(db.Date, nullable=False)
    
    total_amount = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    grand_total = db.Column(db.Float, default=0.0)
    
    status = db.Column(db.String(50), default='draft')  # draft, submitted, approved, ordered, delivered, cancelled
    delivery_date = db.Column(db.Date)
    
    prepared_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    preparer = db.relationship('User', foreign_keys=[prepared_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    items = db.relationship('PurchaseOrderItem', backref='purchase_order', lazy=True, cascade='all, delete-orphan')
    
    # فهرسة
    __table_args__ = (
        Index('idx_po_project', 'project_id'),
        Index('idx_po_supplier', 'supplier_id'),
        Index('idx_po_number', 'po_number'),
        Index('idx_po_status', 'status'),
        Index('idx_po_date', 'po_date'),
        UniqueConstraint('project_id', 'po_number', name='uq_po_number_project'),
    )


class PurchaseOrderItem(db.Model):
    """بنود طلب الشراء"""
    __tablename__ = 'purchase_order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    material_id = db.Column(db.Integer, db.ForeignKey('material_items.id'))
    
    item_description = db.Column(db.Text)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    received_quantity = db.Column(db.Float, default=0.0)
    rejected_quantity = db.Column(db.Float, default=0.0)
    
    notes = db.Column(db.Text)
    
    # فهرسة
    __table_args__ = (
        Index('idx_po_item_po', 'purchase_order_id'),
        Index('idx_po_item_material', 'material_id'),
    )
    
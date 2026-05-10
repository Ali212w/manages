"""
models.py - ملف نماذج قاعدة البيانات الكامل مع العلاقات والفهرسة
نظام إدارة المشاريع الهندسية الذكي - الإصدار المتكامل
"""

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, ForeignKeyConstraint, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import relationship, backref
from datetime import datetime, date, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json
import uuid

db = SQLAlchemy()

# ============================================================================
# الجداول الأساسية للمستخدمين والمؤسسة
# ============================================================================

class Organization(db.Model):
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    org_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    description = db.Column(db.Text)
    address = db.Column(db.Text)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    website = db.Column(db.String(200))
    tax_number = db.Column(db.String(100))
    commercial_register = db.Column(db.String(100))
    logo_url = db.Column(db.String(500))
    
    # الإعدادات
    settings = db.Column(db.JSON, default={
        'currency': 'SAR',
        'language': 'ar',
        'timezone': 'Asia/Riyadh',
        'date_format': 'dd/MM/yyyy',
        'decimal_places': 2,
        'auto_approve_threshold': 50000
    })
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    departments = relationship('Department', backref='organization', lazy=True, cascade='all, delete-orphan')
    projects = relationship('Project', backref='organization', lazy=True)
    users = relationship('User', backref='organization', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_org_code', 'org_code'),
        Index('idx_org_name', 'name'),
        Index('idx_org_tax', 'tax_number'),
    )


class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    dept_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    name_ar = db.Column(db.String(150))
    description = db.Column(db.Text)
    parent_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    budget = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    parent = relationship('Department', remote_side=[id], backref='sub_departments')
    manager = relationship('User', foreign_keys=[manager_id])
    employees = relationship('User', backref='department', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_dept_org', 'org_id', 'dept_code'),
        Index('idx_dept_parent', 'parent_id'),
        Index('idx_dept_active', 'is_active'),
        UniqueConstraint('org_id', 'dept_code', name='uq_dept_code'),
    )


class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    dept_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    
    # معلومات الحساب
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    mobile = db.Column(db.String(20))
    employee_id = db.Column(db.String(50), unique=True)
    
    # المعلومات الشخصية
    full_name = db.Column(db.String(200), nullable=False)
    full_name_ar = db.Column(db.String(200))
    job_title = db.Column(db.String(150))
    job_title_ar = db.Column(db.String(150))
    national_id = db.Column(db.String(50), unique=True)
    birth_date = db.Column(db.Date)
    hire_date = db.Column(db.Date, default=date.today)
    
    # الأدوار والصلاحيات
    role = db.Column(db.String(50), nullable=False, default='employee')  # admin, project_manager, supervisor, delegate, employee
    permissions = db.Column(db.JSON, default={
        'view_projects': True,
        'create_tasks': False,
        'approve_expenses': False,
        'manage_users': False,
        'view_reports': True
    })
    
    # الحالة
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)
    
    # السجل الزمني
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    managed_projects = relationship('Project', backref='manager', lazy=True, foreign_keys='Project.project_manager_id')
    supervised_tasks = relationship('Task', backref='supervisor', lazy=True, foreign_keys='Task.supervisor_id')
    delegate_tasks = relationship('Task', backref='delegate', lazy=True, foreign_keys='Task.delegate_id')
    task_assignments = relationship('TaskAssignment', backref='user', lazy=True)
    user_skills = relationship('UserSkill', backref='user', lazy=True, cascade='all, delete-orphan')
    notifications = relationship('Notification', backref='user', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_user_org', 'org_id'),
        Index('idx_user_dept', 'dept_id'),
        Index('idx_user_email', 'email'),
        Index('idx_user_username', 'username'),
        Index('idx_user_role', 'role'),
        Index('idx_user_active', 'is_active'),
        Index('idx_user_national_id', 'national_id'),
        Index('idx_user_employee_id', 'employee_id'),
    )
    
    # الدوال
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self, lang='ar'):
        return self.full_name_ar if lang == 'ar' and self.full_name_ar else self.full_name
    
    def has_permission(self, permission):
        return self.permissions.get(permission, False) or self.role == 'admin'
    
    def increment_login_count(self):
        self.login_count += 1
        self.last_login = datetime.utcnow()
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'full_name': self.full_name,
            'full_name_ar': self.full_name_ar,
            'email': self.email,
            'phone': self.phone,
            'job_title': self.job_title,
            'role': self.role,
            'department': self.department.name if self.department else None,
            'is_active': self.is_active
        }


# ============================================================================
# جداول المشاريع والتخطيط
# ============================================================================

class Project(db.Model):
    __tablename__ = 'projects'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # المعلومات الأساسية
    project_code = db.Column(db.String(50), unique=True, nullable=False)
    project_number = db.Column(db.String(100))
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    description = db.Column(db.Text)
    
    # إدارة المشروع
    project_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assistant_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    project_director_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # معلومات الموقع
    site_name = db.Column(db.String(500))
    site_name_ar = db.Column(db.String(500))
    area_name = db.Column(db.String(500))
    area_name_ar = db.Column(db.String(500))
    location_address = db.Column(db.Text)
    location_coordinates = db.Column(db.String(100))  # "lat,lng"
    governorate = db.Column(db.String(100))
    city = db.Column(db.String(100))
    
    # معلومات العقد
    contract_number = db.Column(db.String(100))
    contract_date = db.Column(db.Date)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    client_project_manager = db.Column(db.String(200))
    client_phone = db.Column(db.String(50))
    client_email = db.Column(db.String(150))
    
    consultant_id = db.Column(db.Integer, db.ForeignKey('consultants.id'))
    consultant_project_manager = db.Column(db.String(200))
    
    # القيم المالية
    contract_value = db.Column(db.Float, nullable=False)
    estimated_value = db.Column(db.Float)
    contingency_amount = db.Column(db.Float, default=0.0)
    retention_amount = db.Column(db.Float, default=0.0)
    tax_percentage = db.Column(db.Float, default=15.0)
    advance_payment = db.Column(db.Float, default=0.0)
    
    # الجدول الزمني
    planned_start_date = db.Column(db.Date, nullable=False)
    planned_end_date = db.Column(db.Date, nullable=False)
    actual_start_date = db.Column(db.Date)
    actual_end_date = db.Column(db.Date)
    planned_duration = db.Column(db.Integer)  # بالأيام
    actual_duration = db.Column(db.Integer)
    
    # التقدم والمقاييس
    progress_percentage = db.Column(db.Float, default=0.0)
    physical_progress = db.Column(db.Float, default=0.0)
    financial_progress = db.Column(db.Float, default=0.0)
    quality_score = db.Column(db.Float, default=100.0)
    safety_score = db.Column(db.Float, default=100.0)
    
    # الحالة
    status = db.Column(db.String(50), default='pending')  # pending, planning, active, on_hold, completed, cancelled
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    complexity = db.Column(db.String(20), default='medium')  # low, medium, high
    
    # التصنيفات
    project_type = db.Column(db.String(100))  # بناء، طرق، جسور، إلخ
    project_category = db.Column(db.String(100))  # حكومي، خاص، خيري
    project_scale = db.Column(db.String(50))  # صغير، متوسط، كبير، عملاق
    
    # ملفات ومرفقات
    contract_file_url = db.Column(db.String(500))
    drawings_file_url = db.Column(db.String(500))
    specifications_file_url = db.Column(db.String(500))
    
    # السجل الزمني
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    assistant_manager = relationship('User', foreign_keys=[assistant_manager_id])
    project_director = relationship('User', foreign_keys=[project_director_id])
    client = relationship('Client', backref='projects')
    consultant = relationship('Consultant', backref='projects')
    creator = relationship('User', foreign_keys=[created_by])
    approver = relationship('User', foreign_keys=[approved_by])
    
    wbs_nodes = relationship('WBSNode', backref='project', lazy=True, cascade='all, delete-orphan')
    activities = relationship('Activity', backref='project', lazy=True)
    milestones = relationship('Milestone', backref='project', lazy=True)
    documents = relationship('ProjectDocument', backref='project', lazy=True)
    bill_items = relationship('BillItem', backref='project', lazy=True)
    tasks = relationship('Task', backref='project', lazy=True)
    risks = relationship('Risk', backref='project', lazy=True)
    issues = relationship('Issue', backref='project', lazy=True)
    change_requests = relationship('ChangeRequest', backref='project', lazy=True)
    meetings = relationship('Meeting', backref='project', lazy=True)
    inspections = relationship('Inspection', backref='project', lazy=True)
    daily_reports = relationship('DailyReport', backref='project', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_project_org', 'org_id'),
        Index('idx_project_code', 'project_code'),
        Index('idx_project_manager', 'project_manager_id'),
        Index('idx_project_status', 'status'),
        Index('idx_project_dates', 'planned_start_date', 'planned_end_date'),
        Index('idx_project_client', 'client_id'),
        Index('idx_project_type', 'project_type'),
        Index('idx_project_priority', 'priority'),
        Index('idx_project_progress', 'progress_percentage'),
        UniqueConstraint('org_id', 'project_code', name='uq_project_code_org'),
    )
    
    # الدوال
    def calculate_planned_duration(self):
        if self.planned_start_date and self.planned_end_date:
            delta = self.planned_end_date - self.planned_start_date
            self.planned_duration = delta.days + 1
        return self.planned_duration
    
    def calculate_progress(self):
        """حساب التقدم الشامل للمشروع"""
        # وزن الأنشطة بناءً على قيمتها
        total_weight = 0
        weighted_progress = 0
        
        for activity in self.activities:
            if activity.weight:
                total_weight += activity.weight
                weighted_progress += activity.weight * (activity.progress_percentage / 100)
        
        if total_weight > 0:
            self.progress_percentage = (weighted_progress / total_weight) * 100
        else:
            # متوسط بسيط
            if self.activities:
                total = sum(a.progress_percentage for a in self.activities)
                self.progress_percentage = total / len(self.activities)
        
        return self.progress_percentage
    
    def get_days_behind_schedule(self):
        """عدد الأيام المتأخرة عن الجدول"""
        if self.actual_start_date and self.planned_start_date:
            if self.actual_start_date > self.planned_start_date:
                return (self.actual_start_date - self.planned_start_date).days
        return 0
    
    def get_remaining_days(self):
        """الأيام المتبقية"""
        if self.actual_end_date:
            return 0
        elif self.planned_end_date:
            remaining = self.planned_end_date - date.today()
            return max(0, remaining.days)
        return None
    
    def get_financial_status(self):
        """الحالة المالية للمشروع"""
        total_invoiced = sum(invoice.total_amount for invoice in self.invoices)
        total_paid = sum(invoice.paid_amount for invoice in self.invoices)
        
        return {
            'contract_value': self.contract_value,
            'total_invoiced': total_invoiced,
            'total_paid': total_paid,
            'remaining': self.contract_value - total_invoiced,
            'outstanding': total_invoiced - total_paid
        }
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_code': self.project_code,
            'name': self.name,
            'name_ar': self.name_ar,
            'site_name': self.site_name,
            'site_name_ar': self.site_name_ar,
            'status': self.status,
            'progress_percentage': self.progress_percentage,
            'planned_start_date': self.planned_start_date.isoformat() if self.planned_start_date else None,
            'planned_end_date': self.planned_end_date.isoformat() if self.planned_end_date else None,
            'contract_value': self.contract_value,
            'manager': self.manager.full_name if self.manager else None
        }


class WBSNode(db.Model):
    """هيكل تقسيم العمل (Work Breakdown Structure)"""
    __tablename__ = 'wbs_nodes'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('wbs_nodes.id'))
    
    # الترميز
    wbs_code = db.Column(db.String(50), nullable=False)  # مثل: 1.1.2
    wbs_level = db.Column(db.Integer, nullable=False, default=1)
    wbs_path = db.Column(db.String(500))  # المسار الكامل
    
    # المعلومات
    name = db.Column(db.String(500), nullable=False)
    name_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    node_type = db.Column(db.String(50), default='deliverable')  # phase, deliverable, work_package, activity
    
    # القياسات
    weight = db.Column(db.Float, default=0.0)  # الوزن النسبي
    budget = db.Column(db.Float, default=0.0)  # الميزانية المخصصة
    actual_cost = db.Column(db.Float, default=0.0)
    progress = db.Column(db.Float, default=0.0)
    
    # إدارة القيمة المكتسبة
    earned_value_method = db.Column(db.String(50), default='weight_milestone')  # وزن مرحلة، نسبة مئوية، الخ
    
    # السجل الزمني
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    parent = relationship('WBSNode', remote_side=[id], backref='children')
    activities = relationship('Activity', backref='wbs_node', lazy=True)
    milestones = relationship('Milestone', backref='wbs_node', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_wbs_project', 'project_id'),
        Index('idx_wbs_parent', 'parent_id'),
        Index('idx_wbs_code', 'wbs_code'),
        Index('idx_wbs_level', 'wbs_level'),
        Index('idx_wbs_type', 'node_type'),
        UniqueConstraint('project_id', 'wbs_code', name='uq_wbs_code_project'),
    )
    
    # الدوال
    def get_full_path(self):
        """الحصول على المسار الكامل للعقدة"""
        path = []
        node = self
        while node:
            path.insert(0, node.name)
            node = node.parent
        return ' → '.join(path)
    
    def calculate_progress(self):
        """حساب تقدم العقدة من العقد الفرعية"""
        if self.children:
            total_weight = 0
            weighted_progress = 0
            for child in self.children:
                if child.weight:
                    total_weight += child.weight
                    weighted_progress += child.weight * (child.progress / 100)
            
            if total_weight > 0:
                self.progress = (weighted_progress / total_weight) * 100
        return self.progress
    
    def get_all_children(self):
        """الحصول على جميع العقد الفرعية بشكل متكرر"""
        children = []
        for child in self.children:
            children.append(child)
            children.extend(child.get_all_children())
        return children


class Activity(db.Model):
    """الأنشطة في جدول المشروع"""
    __tablename__ = 'activities'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    wbs_node_id = db.Column(db.Integer, db.ForeignKey('wbs_nodes.id'))
    
    # التعريف
    activity_code = db.Column(db.String(100), nullable=False)
    activity_name = db.Column(db.String(500), nullable=False)
    activity_name_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    # التخطيط
    planned_start_date = db.Column(db.Date)
    planned_end_date = db.Column(db.Date)
    planned_duration = db.Column(db.Float)  # بالأيام
    planned_quantity = db.Column(db.Float)
    planned_cost = db.Column(db.Float)
    
    # التنفيذ
    actual_start_date = db.Column(db.Date)
    actual_end_date = db.Column(db.Date)
    actual_duration = db.Column(db.Float)
    actual_quantity = db.Column(db.Float)
    actual_cost = db.Column(db.Float)
    
    # التقدم
    progress_percentage = db.Column(db.Float, default=0.0)
    remaining_duration = db.Column(db.Float)
    weight = db.Column(db.Float, default=1.0)
    
    # المسؤولية
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    delegate_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # الحالة
    status = db.Column(db.String(50), default='not_started')  # not_started, in_progress, completed, on_hold, cancelled
    priority = db.Column(db.Integer, default=3)  # 1-5
    
    # التصنيف
    activity_type = db.Column(db.String(50))  # construction, installation, testing, etc.
    work_type = db.Column(db.String(50))  # civil, electrical, mechanical, etc.
    
    # القيود
    constraint_type = db.Column(db.String(50))  # start_on, finish_on, asap, etc.
    constraint_date = db.Column(db.Date)
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    supervisor = relationship('User', foreign_keys=[supervisor_id])
    delegate = relationship('User', foreign_keys=[delegate_id])
    tasks = relationship('Task', backref='activity', lazy=True)
    dependencies = relationship('ActivityDependency', 
                               primaryjoin="or_(Activity.id==ActivityDependency.predecessor_id, "
                                         "Activity.id==ActivityDependency.successor_id)")
    
    # فهرسة
    __table_args__ = (
        Index('idx_activity_project', 'project_id'),
        Index('idx_activity_wbs', 'wbs_node_id'),
        Index('idx_activity_code', 'activity_code'),
        Index('idx_activity_status', 'status'),
        Index('idx_activity_dates', 'planned_start_date', 'planned_end_date'),
        Index('idx_activity_supervisor', 'supervisor_id'),
        Index('idx_activity_type', 'activity_type'),
        Index('idx_activity_priority', 'priority'),
        UniqueConstraint('project_id', 'activity_code', name='uq_activity_code_project'),
    )
    
    # الدوال
    def calculate_duration(self):
        """حساب المدة المخططة"""
        if self.planned_start_date and self.planned_end_date:
            delta = self.planned_end_date - self.planned_start_date
            self.planned_duration = delta.days + 1
        return self.planned_duration
    
    def get_earliest_start(self):
        """أقرب تاريخ بدء ممكن بناءً على الأنشطة السابقة"""
        if not self.dependencies:
            return self.planned_start_date
        
        earliest = None
        for dep in self.dependencies:
            if dep.successor_id == self.id:  # هذا النشاط هو خلف
                pred = Activity.query.get(dep.predecessor_id)
                if pred and pred.planned_end_date:
                    if dep.lag_days:
                        date = pred.planned_end_date + timedelta(days=dep.lag_days)
                    else:
                        date = pred.planned_end_date
                    
                    if not earliest or date > earliest:
                        earliest = date
        
        return earliest
    
    def update_progress(self, new_progress):
        """تحديث التقدم مع التحقق"""
        old_progress = self.progress_percentage
        self.progress_percentage = max(0, min(100, new_progress))
        
        # تحديث المدة المتبقية
        if self.actual_start_date:
            if new_progress > old_progress and new_progress > 0:
                elapsed_days = (date.today() - self.actual_start_date).days
                if new_progress > 0:
                    estimated_total = elapsed_days / (new_progress / 100)
                    self.remaining_duration = max(0, estimated_total - elapsed_days)
        
        # إذا اكتمل النشاط
        if self.progress_percentage >= 100 and self.status != 'completed':
            self.status = 'completed'
            self.actual_end_date = date.today()
    
    def is_on_critical_path(self):
        """هل النشاط على المسار الحرج؟"""
        return self.remaining_duration == 0 and self.status == 'in_progress'


class ActivityDependency(db.Model):
    """تبعيات الأنشطة"""
    __tablename__ = 'activity_dependencies'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    predecessor_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    successor_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    # نوع التبعية
    dependency_type = db.Column(db.String(50), default='FS')  # FS, SS, FF, SF
    lag_days = db.Column(db.Float, default=0.0)  # التأخير بالأيام
    
    # الخصائص
    is_hard = db.Column(db.Boolean, default=True)  # تبعية صلبة
    is_critical = db.Column(db.Boolean, default=False)
    
    # العلاقات
    project = relationship('Project')
    predecessor = relationship('Activity', foreign_keys=[predecessor_id], 
                               backref=backref('successor_dependencies'))
    successor = relationship('Activity', foreign_keys=[successor_id],
                             backref=backref('predecessor_dependencies'))
    
    # فهرسة
    __table_args__ = (
        Index('idx_dep_project', 'project_id'),
        Index('idx_dep_predecessor', 'predecessor_id'),
        Index('idx_dep_successor', 'successor_id'),
        Index('idx_dep_type', 'dependency_type'),
        UniqueConstraint('predecessor_id', 'successor_id', name='uq_dependency_pair'),
        ForeignKeyConstraint(['project_id', 'predecessor_id'], 
                           ['activities.project_id', 'activities.id']),
        ForeignKeyConstraint(['project_id', 'successor_id'], 
                           ['activities.project_id', 'activities.id']),
    )


class Milestone(db.Model):
    """معالم المشروع"""
    __tablename__ = 'milestones'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    wbs_node_id = db.Column(db.Integer, db.ForeignKey('wbs_nodes.id'))
    
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
    achieved_by_user = relationship('User', foreign_keys=[achieved_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_milestone_project', 'project_id'),
        Index('idx_milestone_date', 'planned_date'),
        Index('idx_milestone_status', 'status'),
        Index('idx_milestone_type', 'milestone_type'),
        UniqueConstraint('project_id', 'milestone_code', name='uq_milestone_code_project'),
    )


# ============================================================================
# جداول المهام والتنفيذ
# ============================================================================

class Task(db.Model):
    """المهام التنفيذية"""
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'))
    
    # التعريف
    task_code = db.Column(db.String(50), nullable=False)
    task_name = db.Column(db.String(500), nullable=False)
    task_name_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    instructions = db.Column(db.Text)  # تعليمات التنفيذ
    
    # التسلسل
    task_order = db.Column(db.Integer, nullable=False)  # ترتيب في التسلسل
    depends_on_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))  # المهمة السابقة
    
    # المسؤولية
    supervisor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    delegate_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # التخطيط
    planned_start_date = db.Column(db.Date)
    planned_end_date = db.Column(db.Date)
    planned_duration = db.Column(db.Float)  # بالساعات
    estimated_effort = db.Column(db.Float)  # جهد مقدر (ساعة رجل)
    
    # التنفيذ
    actual_start_date = db.Column(db.DateTime)
    actual_end_date = db.Column(db.DateTime)
    actual_duration = db.Column(db.Float)
    
    # التقدم
    progress_percentage = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='pending')  # pending, in_progress, completed, on_hold, cancelled
    completion_quality = db.Column(db.String(20))  # excellent, good, fair, poor
    
    # الموارد
    required_skills = db.Column(db.JSON)  # قائمة المهارات المطلوبة
    required_materials = db.Column(db.JSON)  # قائمة المواد المطلوبة
    required_equipment = db.Column(db.JSON)  # قائمة المعدات المطلوبة
    
    # التحقق
    verification_required = db.Column(db.Boolean, default=True)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_at = db.Column(db.DateTime)
    verification_notes = db.Column(db.Text)
    
    # الموقع
    location = db.Column(db.String(500))
    coordinates = db.Column(db.String(100))
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    supervisor = relationship('User', foreign_keys=[supervisor_id])
    delegate = relationship('User', foreign_keys=[delegate_id])
    verifier = relationship('User', foreign_keys=[verified_by])
    creator = relationship('User', foreign_keys=[created_by])
    predecessor = relationship('Task', remote_side=[id], 
                               backref=backref('successor_tasks'))
    
    assignments = relationship('TaskAssignment', backref='task', lazy=True, cascade='all, delete-orphan')
    daily_reports = relationship('DailyReportTask', backref='task', lazy=True)
    quality_checks = relationship('QualityCheck', backref='task', lazy=True)
    issues = relationship('Issue', backref='task', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_task_project', 'project_id'),
        Index('idx_task_activity', 'activity_id'),
        Index('idx_task_code', 'task_code'),
        Index('idx_task_status', 'status'),
        Index('idx_task_dates', 'planned_start_date', 'planned_end_date'),
        Index('idx_task_supervisor', 'supervisor_id'),
        Index('idx_task_delegate', 'delegate_id'),
        Index('idx_task_order', 'project_id', 'task_order'),
        UniqueConstraint('project_id', 'task_code', name='uq_task_code_project'),
        CheckConstraint("progress_percentage >= 0 AND progress_percentage <= 100", 
                       name='chk_task_progress_range'),
    )
    
    # الدوال
    def start_task(self):
        """بدء المهمة"""
        if self.status == 'pending' and self.actual_start_date is None:
            self.status = 'in_progress'
            self.actual_start_date = datetime.utcnow()
            self.progress_percentage = 0.1  # بدأت للتو
            
            # إشعار المشرف
            notification = Notification(
                user_id=self.supervisor_id,
                title=f'بدء المهمة: {self.task_name}',
                message=f'تم بدء المهمة {self.task_code} بواسطة {self.delegate.full_name if self.delegate else "المسؤول"}',
                notification_type='task_started',
                related_task_id=self.id,
                related_project_id=self.project_id,
                priority='medium'
            )
            db.session.add(notification)
            
            return True
        return False
    
    def complete_task(self, quality='good', notes=None):
        """إكمال المهمة"""
        if self.status == 'in_progress':
            self.status = 'completed'
            self.actual_end_date = datetime.utcnow()
            self.progress_percentage = 100
            self.completion_quality = quality
            
            # حساب المدة الفعلية
            if self.actual_start_date:
                duration = self.actual_end_date - self.actual_start_date
                self.actual_duration = duration.total_seconds() / 3600  # بالساعات
            
            # إشعار المشرف والمندوب
            notifications = []
            
            if self.supervisor_id:
                notifications.append(Notification(
                    user_id=self.supervisor_id,
                    title=f'اكتمال المهمة: {self.task_name}',
                    message=f'تم إكمال المهمة {self.task_code} بنجاح',
                    notification_type='task_completed',
                    related_task_id=self.id,
                    related_project_id=self.project_id,
                    priority='medium'
                ))
            
            if self.delegate_id:
                notifications.append(Notification(
                    user_id=self.delegate_id,
                    title=f'تهنئة: مهمة مكتملة',
                    message=f'تم تسجيل إكمال المهمة {self.task_code}',
                    notification_type='task_completed',
                    related_task_id=self.id,
                    related_project_id=self.project_id,
                    priority='low'
                ))
            
            db.session.add_all(notifications)
            
            # بدء المهام التالية تلقائياً
            self.start_successor_tasks()
            
            return True
        return False
    
    def start_successor_tasks(self):
        """بدء المهام التالية تلقائياً"""
        for successor in self.successor_tasks:
            # التحقق من جميع المهام السابقة
            all_predecessors_completed = True
            for pred in successor.predecessor:
                if pred.status != 'completed':
                    all_predecessors_completed = False
                    break
            
            if all_predecessors_completed and successor.status == 'pending':
                successor.start_task()
    
    def assign_user(self, user_id, assigned_by_id):
        """تعيين مستخدم للمهمة"""
        assignment = TaskAssignment(
            task_id=self.id,
            user_id=user_id,
            assigned_by=assigned_by_id,
            assigned_at=datetime.utcnow(),
            status='assigned'
        )
        db.session.add(assignment)
        
        # إشعار المستخدم
        notification = Notification(
            user_id=user_id,
            title=f'مهمة جديدة: {self.task_name}',
            message=f'تم تعيينك للمهمة {self.task_code} في مشروع {self.project.name}',
            notification_type='task_assigned',
            related_task_id=self.id,
            related_project_id=self.project_id,
            priority='high'
        )
        db.session.add(notification)
        
        return assignment
    
    def get_assigned_users(self):
        """الحصول على المستخدمين المعينين للمهمة"""
        return [assignment.user for assignment in self.assignments if assignment.status != 'cancelled']
    
    def update_progress(self, progress, updated_by_id):
        """تحديث تقدم المهمة"""
        old_progress = self.progress_percentage
        self.progress_percentage = progress
        
        if progress >= 100:
            self.complete_task()
        elif progress > 0 and self.status == 'pending':
            self.status = 'in_progress'
            if not self.actual_start_date:
                self.actual_start_date = datetime.utcnow()
        
        # تسجيل التحديث
        progress_update = TaskProgressUpdate(
            task_id=self.id,
            progress_percentage=progress,
            updated_by=updated_by_id,
            notes=f'تحديث التقدم من {old_progress}% إلى {progress}%'
        )
        db.session.add(progress_update)
        
        return True


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
    assigner = relationship('User', foreign_keys=[assigned_by])
    
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
    task = relationship('Task', backref='progress_updates')
    updater = relationship('User', foreign_keys=[updated_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_progress_task', 'task_id'),
        Index('idx_progress_date', 'updated_at'),
        Index('idx_progress_updater', 'updated_by'),
        CheckConstraint("progress_percentage >= 0 AND progress_percentage <= 100", 
                       name='chk_progress_range'),
    )


# ============================================================================
# جداول جدول الكميات والمواصفات
# ============================================================================

class BillItem(db.Model):
    """بنود جدول الكميات والمواصفات"""
    __tablename__ = 'bill_items'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    parent_item_id = db.Column(db.Integer, db.ForeignKey('bill_items.id'))
    
    # الترميز
    item_code = db.Column(db.String(100), nullable=False)
    item_number = db.Column(db.String(50))
    
    # الوصف
    description = db.Column(db.Text, nullable=False)
    description_ar = db.Column(db.Text)
    specifications = db.Column(db.Text)  # المواصفات التفصيلية
    unit = db.Column(db.String(50))
    
    # الكميات المخططة
    planned_quantity = db.Column(db.Float, default=0.0)
    unit_price = db.Column(db.Float, default=0.0)
    planned_amount = db.Column(db.Float, default=0.0)
    
    # التنفيذ الحالي
    current_quantity = db.Column(db.Float, default=0.0)
    current_amount = db.Column(db.Float, default=0.0)
    
    # التنفيذ السابق
    previous_quantity = db.Column(db.Float, default=0.0)
    previous_amount = db.Column(db.Float, default=0.0)
    
    # الإجماليات
    total_quantity = db.Column(db.Float, default=0.0)  # الكميات المجمعة
    total_amount = db.Column(db.Float, default=0.0)    # المبالغ المجمعة
    
    # التوقعات
    expected_variation_quantity = db.Column(db.Float, default=0.0)  # الزيادة/النقصان المتوقع
    expected_variation_price = db.Column(db.Float, default=0.0)     # سعر الزيادة/النقصان
    expected_variation_amount = db.Column(db.Float, default=0.0)    # مبلغ الزيادة/النقصان
    
    # المجاميع المتوقعة
    total_expected_quantity = db.Column(db.Float, default=0.0)  # إجمالي الكمية المتوقع
    total_expected_amount = db.Column(db.Float, default=0.0)    # إجمالي المبلغ المتوقع
    
    # الملاحظات
    notes = db.Column(db.Text)
    
    # التسلسل الهرمي
    item_level = db.Column(db.Integer, default=1)
    item_type = db.Column(db.String(50), default='item')  # main_item, sub_item, activity, sub_activity
    
    # التحليل التلقائي
    complexity_score = db.Column(db.Float, default=0.5)
    estimated_duration_days = db.Column(db.Float)
    risk_level = db.Column(db.String(20))  # low, medium, high
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    parent = relationship('BillItem', remote_side=[id], backref='sub_items')
    activities = relationship('Activity', secondary='bill_item_activities', 
                             backref='bill_items')
    materials = relationship('MaterialItem', backref='bill_item', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_bill_project', 'project_id'),
        Index('idx_bill_parent', 'parent_item_id'),
        Index('idx_bill_code', 'item_code'),
        Index('idx_bill_type', 'item_type'),
        Index('idx_bill_level', 'item_level'),
        Index('idx_bill_risk', 'risk_level'),
        UniqueConstraint('project_id', 'item_code', name='uq_bill_code_project'),
    )
    
    # الدوال
    def calculate_amounts(self):
        """حساب جميع المبالغ تلقائياً"""
        # المبلغ المخطط
        self.planned_amount = self.planned_quantity * self.unit_price
        
        # الإجماليات
        self.total_quantity = self.previous_quantity + self.current_quantity
        self.total_amount = self.previous_amount + self.current_amount
        
        # الكمية المتوقعة
        self.total_expected_quantity = self.total_quantity + self.expected_variation_quantity
        self.total_expected_amount = self.total_expected_quantity * self.unit_price
        
        # مبلغ الزيادة/النقصان
        self.expected_variation_amount = self.expected_variation_quantity * self.expected_variation_price
        
        return {
            'planned_amount': self.planned_amount,
            'total_amount': self.total_amount,
            'total_expected_amount': self.total_expected_amount
        }
    
    def get_hierarchy_path(self):
        """الحصول على المسار الهرمي للبند"""
        path = []
        item = self
        while item:
            path.insert(0, {
                'code': item.item_code,
                'description': item.description[:50] + '...' if len(item.description) > 50 else item.description
            })
            item = item.parent
        return path
    
    def is_summary_item(self):
        """هل البند عبارة عن بند ملخص (له بنود فرعية)؟"""
        return len(self.sub_items) > 0
    
    def update_progress_from_activities(self):
        """تحديث التقدم من الأنشطة المرتبطة"""
        if self.activities:
            total_progress = 0
            for activity in self.activities:
                total_progress += activity.progress_percentage
            avg_progress = total_progress / len(self.activities)
            
            # تحديث الكمية الحالية بناءً على التقدم
            self.current_quantity = (avg_progress / 100) * self.planned_quantity
            self.current_amount = self.current_quantity * self.unit_price
            
            self.calculate_amounts()
            
            return avg_progress
        return 0


class BillItemActivity(db.Model):
    """جدول الربط بين بنود الجدول والأنشطة"""
    __tablename__ = 'bill_item_activities'
    
    id = db.Column(db.Integer, primary_key=True)
    bill_item_id = db.Column(db.Integer, db.ForeignKey('bill_items.id'), nullable=False)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    
    quantity_allocation = db.Column(db.Float, default=1.0)  # نسبة الكمية المخصصة للنشاط
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # فهرسة
    __table_args__ = (
        Index('idx_bill_activity_bill', 'bill_item_id'),
        Index('idx_bill_activity_activity', 'activity_id'),
        UniqueConstraint('bill_item_id', 'activity_id', name='uq_bill_activity'),
    )


class MaterialItem(db.Model):
    """المواد في المشروع"""
    __tablename__ = 'material_items'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    bill_item_id = db.Column(db.Integer, db.ForeignKey('bill_items.id'))
    
    material_code = db.Column(db.String(100), nullable=False)
    material_name = db.Column(db.String(500), nullable=False)
    material_name_ar = db.Column(db.String(500))
    material_type = db.Column(db.String(100))  # خرسانة، حديد، بلوك، إلخ
    specification = db.Column(db.Text)
    
    unit = db.Column(db.String(50))
    planned_quantity = db.Column(db.Float, default=0.0)
    unit_price = db.Column(db.Float, default=0.0)
    total_price = db.Column(db.Float, default=0.0)
    
    # المستلم
    received_quantity = db.Column(db.Float, default=0.0)
    remaining_quantity = db.Column(db.Float, default=0.0)
    
    # المورد
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id'))
    order_number = db.Column(db.String(100))
    delivery_date = db.Column(db.Date)
    
    # المخزون
    storage_location = db.Column(db.String(200))
    min_stock_level = db.Column(db.Float)
    current_stock = db.Column(db.Float, default=0.0)
    
    # الحالة
    status = db.Column(db.String(50), default='pending')  # pending, ordered, delivered, consumed
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    supplier = relationship('Supplier', backref='materials')
    deliveries = relationship('MaterialDelivery', backref='material', lazy=True)
    usages = relationship('MaterialUsage', backref='material', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_material_project', 'project_id'),
        Index('idx_material_bill', 'bill_item_id'),
        Index('idx_material_code', 'material_code'),
        Index('idx_material_type', 'material_type'),
        Index('idx_material_status', 'status'),
        Index('idx_material_supplier', 'supplier_id'),
        UniqueConstraint('project_id', 'material_code', name='uq_material_code_project'),
    )
    
    # الدوال
    def calculate_totals(self):
        """حساب المجاميع"""
        self.total_price = self.planned_quantity * self.unit_price
        self.remaining_quantity = self.received_quantity - self.current_stock
        
        # تحذير إذا كان المخزون منخفضاً
        if self.min_stock_level and self.current_stock < self.min_stock_level:
            # إنشاء تنبيه
            pass
        
        return {
            'total_price': self.total_price,
            'remaining_quantity': self.remaining_quantity,
            'consumed_quantity': self.received_quantity - self.remaining_quantity
        }
    
    def update_stock(self, quantity_change, transaction_type, reference_id=None, notes=None):
        """تحديث المخزون"""
        old_stock = self.current_stock
        self.current_stock += quantity_change
        
        if self.current_stock < 0:
            self.current_stock = 0
        
        # تسجيل الحركة
        transaction = MaterialTransaction(
            material_id=self.id,
            transaction_type=transaction_type,  # receive, consume, adjust, etc.
            quantity=quantity_change,
            previous_stock=old_stock,
            new_stock=self.current_stock,
            reference_id=reference_id,
            notes=notes,
            created_by=None  # سيتم تعيينه من المستخدم الحالي
        )
        
        db.session.add(transaction)
        
        return transaction


class MaterialTransaction(db.Model):
    """حركات المواد"""
    __tablename__ = 'material_transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('material_items.id'), nullable=False)
    
    transaction_type = db.Column(db.String(50), nullable=False)  # receive, consume, return, adjust, transfer
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float)
    total_price = db.Column(db.Float)
    
    previous_stock = db.Column(db.Float)
    new_stock = db.Column(db.Float)
    
    reference_id = db.Column(db.Integer)  # معرف المرجع (طلب شراء، استهلاك، إلخ)
    reference_type = db.Column(db.String(50))  # purchase_order, usage, adjustment
    
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    material = relationship('MaterialItem', backref='transactions')
    creator = relationship('User', foreign_keys=[created_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_transaction_material', 'material_id'),
        Index('idx_transaction_type', 'transaction_type'),
        Index('idx_transaction_date', 'created_at'),
        Index('idx_transaction_reference', 'reference_type', 'reference_id'),
    )


# ============================================================================
# جداول الموردين والعملاء
# ============================================================================

class Client(db.Model):
    __tablename__ = 'clients'
    
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    client_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    type = db.Column(db.String(50))  # government, private, individual
    
    contact_person = db.Column(db.String(200))
    position = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    mobile = db.Column(db.String(50))
    email = db.Column(db.String(150))
    
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
    
    # فهرسة
    __table_args__ = (
        Index('idx_client_org', 'org_id'),
        Index('idx_client_code', 'client_code'),
        Index('idx_client_name', 'name'),
        Index('idx_client_type', 'type'),
        Index('idx_client_active', 'is_active'),
        UniqueConstraint('org_id', 'client_code', name='uq_client_code_org'),
    )


class Consultant(db.Model):
    __tablename__ = 'consultants'
    
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    consultant_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    
    contact_person = db.Column(db.String(200))
    position = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    
    specialization = db.Column(db.String(200))  # معماري، إنشائي، ميكانيكا، إلخ
    license_number = db.Column(db.String(100))
    
    rating = db.Column(db.Integer)
    daily_rate = db.Column(db.Float)
    
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # فهرسة
    __table_args__ = (
        Index('idx_consultant_org', 'org_id'),
        Index('idx_consultant_code', 'consultant_code'),
        Index('idx_consultant_name', 'name'),
        Index('idx_consultant_specialization', 'specialization'),
        UniqueConstraint('org_id', 'consultant_code', name='uq_consultant_code_org'),
    )


class Supplier(db.Model):
    __tablename__ = 'suppliers'
    
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    supplier_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    name_ar = db.Column(db.String(200))
    type = db.Column(db.String(50))  # material, equipment, subcontractor
    
    contact_person = db.Column(db.String(200))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    
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
    purchase_orders = relationship('PurchaseOrder', backref='supplier', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_supplier_org', 'org_id'),
        Index('idx_supplier_code', 'supplier_code'),
        Index('idx_supplier_name', 'name'),
        Index('idx_supplier_type', 'type'),
        Index('idx_supplier_approved', 'is_approved'),
        Index('idx_supplier_blacklisted', 'is_blacklisted'),
        UniqueConstraint('org_id', 'supplier_code', name='uq_supplier_code_org'),
    )


# ============================================================================
# جداول الملفات والمستندات
# ============================================================================

class ProjectDocument(db.Model):
    """مستندات المشروع"""
    __tablename__ = 'project_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    document_type = db.Column(db.String(100), nullable=False)  # contract, drawing, specification, report
    category = db.Column(db.String(100))  # engineering, financial, legal, etc.
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_extension = db.Column(db.String(20))
    file_size = db.Column(db.Integer)  # بالبايت
    file_path = db.Column(db.String(500))
    thumbnail_path = db.Column(db.String(500))
    
    title = db.Column(db.String(500))
    title_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    version = db.Column(db.String(50), default='1.0')
    revision_number = db.Column(db.Integer, default=1)
    is_latest = db.Column(db.Boolean, default=True)
    
    # التحليل التلقائي
    extraction_status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    extraction_metadata = db.Column(db.JSON)
    analysis_summary = db.Column(db.JSON)
    
    # التوقيع والموافقة
    requires_approval = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    approval_status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    
    # الصلاحيات
    is_public = db.Column(db.Boolean, default=False)
    access_level = db.Column(db.String(50), default='team')  # public, organization, team, restricted
    
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    uploader = relationship('User', foreign_keys=[uploaded_by])
    approver = relationship('User', foreign_keys=[approved_by])
    bill_items = relationship('BillItem', secondary='document_bill_items', 
                             backref='documents')
    
    # فهرسة
    __table_args__ = (
        Index('idx_document_project', 'project_id'),
        Index('idx_document_type', 'document_type'),
        Index('idx_document_status', 'extraction_status'),
        Index('idx_document_approval', 'approval_status'),
        Index('idx_document_uploaded', 'uploaded_at'),
        Index('idx_document_uploader', 'uploaded_by'),
        Index('idx_document_filename', 'filename'),
    )


class DocumentBillItem(db.Model):
    """جدول الربط بين المستندات وبنود الجدول"""
    __tablename__ = 'document_bill_items'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('project_documents.id'), nullable=False)
    bill_item_id = db.Column(db.Integer, db.ForeignKey('bill_items.id'), nullable=False)
    
    page_number = db.Column(db.Integer)
    coordinates = db.Column(db.JSON)  # إحداثيات البند في المستند
    confidence_score = db.Column(db.Float)  # درجة ثقة الاستخراج
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # فهرسة
    __table_args__ = (
        Index('idx_doc_bill_document', 'document_id'),
        Index('idx_doc_bill_item', 'bill_item_id'),
        UniqueConstraint('document_id', 'bill_item_id', name='uq_document_bill_item'),
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
    preparer = relationship('User', foreign_keys=[prepared_by])
    reviewer = relationship('User', foreign_keys=[reviewed_by])
    approver = relationship('User', foreign_keys=[approved_by])
    
    tasks = relationship('DailyReportTask', backref='daily_report', lazy=True, cascade='all, delete-orphan')
    photos = relationship('DailyReportPhoto', backref='daily_report', lazy=True, cascade='all, delete-orphan')
    
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
            # يمكن إضافة حسابات الإنتاجية هنا
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
    task = relationship('Task')
    bill_item = relationship('BillItem')
    photographer = relationship('User', foreign_keys=[taken_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_daily_photo_report', 'daily_report_id'),
        Index('idx_daily_photo_task', 'task_id'),
        Index('idx_daily_photo_bill', 'bill_item_id'),
        Index('idx_daily_photo_date', 'taken_at'),
    )


# ============================================================================
# جداول المخاطر والقضايا
# ============================================================================

class Risk(db.Model):
    """مخاطر المشروع"""
    __tablename__ = 'risks'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    risk_code = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    title_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    category = db.Column(db.String(100))  # technical, financial, schedule, legal, etc.
    risk_type = db.Column(db.String(100))  # threat, opportunity
    
    # التقييم
    probability = db.Column(db.Float, default=0.5)  # 0-1
    impact = db.Column(db.Float, default=0.5)  # 0-1
    severity = db.Column(db.Float, default=0.25)  # probability * impact
    risk_level = db.Column(db.String(20))  # low, medium, high, critical
    
    # المالك والمسؤول
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # الحالة
    status = db.Column(db.String(50), default='identified')  # identified, assessed, mitigated, closed
    mitigation_status = db.Column(db.String(50))  # not_started, in_progress, completed
    
    # التواريخ
    identified_date = db.Column(db.Date, default=date.today)
    target_mitigation_date = db.Column(db.Date)
    actual_mitigation_date = db.Column(db.Date)
    
    # خطة الاستجابة
    response_strategy = db.Column(db.String(100))  # avoid, mitigate, transfer, accept
    mitigation_plan = db.Column(db.Text)
    contingency_plan = db.Column(db.Text)
    
    # التكلفة
    estimated_cost_impact = db.Column(db.Float)
    actual_cost_impact = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    owner = relationship('User', foreign_keys=[owner_id])
    assignee = relationship('User', foreign_keys=[assigned_to])
    creator = relationship('User', foreign_keys=[created_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_risk_project', 'project_id'),
        Index('idx_risk_code', 'risk_code'),
        Index('idx_risk_status', 'status'),
        Index('idx_risk_level', 'risk_level'),
        Index('idx_risk_category', 'category'),
        Index('idx_risk_owner', 'owner_id'),
        Index('idx_risk_dates', 'identified_date', 'target_mitigation_date'),
        UniqueConstraint('project_id', 'risk_code', name='uq_risk_code_project'),
        CheckConstraint("probability >= 0 AND probability <= 1", name='chk_risk_probability'),
        CheckConstraint("impact >= 0 AND impact <= 1", name='chk_risk_impact'),
    )
    
    # الدوال
    def calculate_severity(self):
        """حساب شدة الخطر"""
        self.severity = self.probability * self.impact
        
        # تحديد مستوى الخطر
        if self.severity >= 0.7:
            self.risk_level = 'critical'
        elif self.severity >= 0.5:
            self.risk_level = 'high'
        elif self.severity >= 0.3:
            self.risk_level = 'medium'
        else:
            self.risk_level = 'low'
        
        return self.risk_level
    
    def update_mitigation_progress(self, progress_percentage, notes=None):
        """تحديث تقدم المعالجة"""
        old_status = self.mitigation_status
        
        if progress_percentage <= 0:
            self.mitigation_status = 'not_started'
        elif progress_percentage < 100:
            self.mitigation_status = 'in_progress'
        else:
            self.mitigation_status = 'completed'
            self.status = 'closed'
            self.actual_mitigation_date = date.today()
        
        # تسجيل التحديث
        if old_status != self.mitigation_status:
            update = RiskUpdate(
                risk_id=self.id,
                old_status=old_status,
                new_status=self.mitigation_status,
                progress_percentage=progress_percentage,
                notes=notes,
                updated_by=None  # سيتم تعيينه من المستخدم الحالي
            )
            db.session.add(update)
        
        return True


class RiskUpdate(db.Model):
    """تحديثات المخاطر"""
    __tablename__ = 'risk_updates'
    
    id = db.Column(db.Integer, primary_key=True)
    risk_id = db.Column(db.Integer, db.ForeignKey('risks.id'), nullable=False)
    
    old_status = db.Column(db.String(50))
    new_status = db.Column(db.String(50))
    progress_percentage = db.Column(db.Float)
    
    notes = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    risk = relationship('Risk', backref='updates')
    updater = relationship('User', foreign_keys=[updated_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_risk_update_risk', 'risk_id'),
        Index('idx_risk_update_date', 'updated_at'),
        Index('idx_risk_update_status', 'new_status'),
        CheckConstraint("progress_percentage >= 0 AND progress_percentage <= 100", 
                       name='chk_risk_progress'),
    )


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
    reporter = relationship('User', foreign_keys=[reported_by])
    assignee = relationship('User', foreign_keys=[assigned_to])
    
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


# ============================================================================
# جداول الجودة والسلامة
# ============================================================================

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
    conductor = relationship('User', foreign_keys=[conducted_by])
    witness = relationship('User', foreign_keys=[witnessed_by])
    
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


class SafetyInspection(db.Model):
    """فحوصات السلامة"""
    __tablename__ = 'safety_inspections'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    inspection_code = db.Column(db.String(50), nullable=False)
    inspection_type = db.Column(db.String(100))  # daily, weekly, monthly, special
    area = db.Column(db.String(200))  # منطقة الفحص
    
    inspection_date = db.Column(db.Date, nullable=False)
    conducted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    checklist_items = db.Column(db.JSON)  # بنود قائمة الفحص
    findings = db.Column(db.JSON)  # النتائج
    violations = db.Column(db.JSON)  # المخالفات
    
    total_score = db.Column(db.Float)
    status = db.Column(db.String(50), default='pending')  # pending, completed, failed
    
    corrective_actions = db.Column(db.Text)
    follow_up_date = db.Column(db.Date)
    
    photos = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    conductor = relationship('User', foreign_keys=[conducted_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_safety_project', 'project_id'),
        Index('idx_safety_code', 'inspection_code'),
        Index('idx_safety_date', 'inspection_date'),
        Index('idx_safety_type', 'inspection_type'),
        Index('idx_safety_conductor', 'conducted_by'),
        UniqueConstraint('project_id', 'inspection_code', name='uq_safety_code_project'),
    )


# ============================================================================
# جداول الإشعارات والاتصالات
# ============================================================================

class Notification(db.Model):
    """الإشعارات"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    message_ar = db.Column(db.Text)
    
    notification_type = db.Column(db.String(50), nullable=False)  # task_started, task_completed, risk_alert, etc.
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    
    # المراجع
    related_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    related_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    related_risk_id = db.Column(db.Integer, db.ForeignKey('risks.id'))
    related_issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'))
    
    # الحالة
    is_read = db.Column(db.Boolean, default=False)
    is_sent = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    
    # قنوات الإرسال
    send_email = db.Column(db.Boolean, default=True)
    send_push = db.Column(db.Boolean, default=True)
    send_sms = db.Column(db.Boolean, default=False)
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    
    # العلاقات
    project = relationship('Project')
    task = relationship('Task')
    risk = relationship('Risk')
    issue = relationship('Issue')
    
    # فهرسة
    __table_args__ = (
        Index('idx_notification_user', 'user_id'),
        Index('idx_notification_type', 'notification_type'),
        Index('idx_notification_priority', 'priority'),
        Index('idx_notification_read', 'is_read'),
        Index('idx_notification_created', 'created_at'),
        Index('idx_notification_project', 'related_project_id'),
        Index('idx_notification_task', 'related_task_id'),
    )
    
    # الدوال
    def mark_as_read(self):
        """تحديد الإشعار كمقروء"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
            return True
        return False
    
    def mark_as_sent(self):
        """تحديد الإشعار كمرسل"""
        if not self.is_sent:
            self.is_sent = True
            self.sent_at = datetime.utcnow()
            return True
        return False
    
    def to_dict(self):
        """تحويل إلى قاموس"""
        return {
            'id': self.id,
            'uuid': self.uuid,
            'title': self.title,
            'title_ar': self.title_ar,
            'message': self.message,
            'message_ar': self.message_ar,
            'type': self.notification_type,
            'priority': self.priority,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'project': self.project.to_dict() if self.project else None,
            'task': {
                'id': self.task.id,
                'task_name': self.task.task_name
            } if self.task else None
        }


# ============================================================================
# جداول التتبع والتحليلات
# ============================================================================

class AuditLog(db.Model):
    """سجل التدقيق"""
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user_ip = db.Column(db.String(50))
    user_agent = db.Column(db.Text)
    
    action = db.Column(db.String(200), nullable=False)
    entity_type = db.Column(db.String(100))  # project, task, user, etc.
    entity_id = db.Column(db.Integer)
    
    old_values = db.Column(db.JSON)
    new_values = db.Column(db.JSON)
    changes = db.Column(db.JSON)  # التغييرات فقط
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    user = relationship('User', foreign_keys=[user_id])
    
    # فهرسة
    __table_args__ = (
        Index('idx_audit_user', 'user_id'),
        Index('idx_audit_action', 'action'),
        Index('idx_audit_entity', 'entity_type', 'entity_id'),
        Index('idx_audit_timestamp', 'timestamp'),
    )


class SystemMetric(db.Model):
    """مقاييس النظام"""
    __tablename__ = 'system_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    
    metric_type = db.Column(db.String(100), nullable=False)
    metric_name = db.Column(db.String(200), nullable=False)
    value = db.Column(db.Float, nullable=False)
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    metadata = db.Column(db.JSON)
    
    # العلاقات
    project = relationship('Project')
    user = relationship('User', foreign_keys=[user_id])
    
    # فهرسة
    __table_args__ = (
        Index('idx_metric_type', 'metric_type'),
        Index('idx_metric_name', 'metric_name'),
        Index('idx_metric_timestamp', 'timestamp'),
        Index('idx_metric_project', 'project_id'),
        Index('idx_metric_user', 'user_id'),
    )


# ============================================================================
# جداول إضافية للميزات المتقدمة
# ============================================================================

class UserSkill(db.Model):
    """مهارات المستخدمين"""
    __tablename__ = 'user_skills'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    skill_name = db.Column(db.String(200), nullable=False)
    skill_name_ar = db.Column(db.String(200))
    skill_category = db.Column(db.String(100))  # technical, managerial, safety, etc.
    
    proficiency_level = db.Column(db.Integer, default=1)  # 1-5
    experience_years = db.Column(db.Float, default=0.0)
    
    certification = db.Column(db.String(200))
    certification_date = db.Column(db.Date)
    
    last_used = db.Column(db.Date)
    success_rate = db.Column(db.Float, default=0.0)  # نسبة النجاح في المهام
    
    is_verified = db.Column(db.Boolean, default=False)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_at = db.Column(db.DateTime)
    
    notes = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    verifier = relationship('User', foreign_keys=[verified_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_skill_user', 'user_id'),
        Index('idx_skill_name', 'skill_name'),
        Index('idx_skill_category', 'skill_category'),
        Index('idx_skill_level', 'proficiency_level'),
        Index('idx_skill_verified', 'is_verified'),
        UniqueConstraint('user_id', 'skill_name', name='uq_user_skill'),
        CheckConstraint("proficiency_level >= 1 AND proficiency_level <= 5", 
                       name='chk_skill_level'),
        CheckConstraint("success_rate >= 0 AND success_rate <= 100", 
                       name='chk_skill_success'),
    )


class ChangeRequest(db.Model):
    """طلبات التغيير"""
    __tablename__ = 'change_requests'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    cr_number = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    title_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    change_type = db.Column(db.String(100))  # scope, schedule, cost, quality, etc.
    impact_scope = db.Column(db.Text)
    impact_schedule = db.Column(db.Text)
    impact_cost = db.Column(db.Text)
    
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requested_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    review_date = db.Column(db.Date)
    
    status = db.Column(db.String(50), default='submitted')  # submitted, under_review, approved, rejected, implemented
    decision = db.Column(db.String(50))  # approve, reject, defer
    decision_date = db.Column(db.DateTime)
    decision_notes = db.Column(db.Text)
    
    estimated_cost = db.Column(db.Float)
    actual_cost = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    requester = relationship('User', foreign_keys=[requested_by])
    assignee = relationship('User', foreign_keys=[assigned_to])
    
    # فهرسة
    __table_args__ = (
        Index('idx_change_project', 'project_id'),
        Index('idx_change_number', 'cr_number'),
        Index('idx_change_status', 'status'),
        Index('idx_change_type', 'change_type'),
        Index('idx_change_requester', 'requested_by'),
        Index('idx_change_assignee', 'assigned_to'),
        Index('idx_change_dates', 'requested_date', 'review_date'),
        UniqueConstraint('project_id', 'cr_number', name='uq_change_number_project'),
    )


class Meeting(db.Model):
    """اجتماعات المشروع"""
    __tablename__ = 'meetings'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    meeting_code = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    title_ar = db.Column(db.String(500))
    purpose = db.Column(db.Text)
    
    meeting_type = db.Column(db.String(100))  # progress, coordination, technical, management
    location = db.Column(db.String(500))
    is_virtual = db.Column(db.Boolean, default=False)
    virtual_link = db.Column(db.String(500))
    
    scheduled_date = db.Column(db.DateTime, nullable=False)
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    actual_start_time = db.Column(db.DateTime)
    actual_end_time = db.Column(db.DateTime)
    
    organizer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    secretary_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    status = db.Column(db.String(50), default='scheduled')  # scheduled, in_progress, completed, cancelled
    
    agenda = db.Column(db.JSON)
    minutes = db.Column(db.Text)
    decisions = db.Column(db.JSON)
    action_items = db.Column(db.JSON)
    
    attendees = db.Column(db.JSON)  # قائمة الحضور
    documents = db.Column(db.JSON)  # روابط المستندات
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    organizer = relationship('User', foreign_keys=[organizer_id])
    secretary = relationship('User', foreign_keys=[secretary_id])
    
    # فهرسة
    __table_args__ = (
        Index('idx_meeting_project', 'project_id'),
        Index('idx_meeting_code', 'meeting_code'),
        Index('idx_meeting_date', 'scheduled_date'),
        Index('idx_meeting_status', 'status'),
        Index('idx_meeting_organizer', 'organizer_id'),
        Index('idx_meeting_type', 'meeting_type'),
        UniqueConstraint('project_id', 'meeting_code', name='uq_meeting_code_project'),
    )


# ============================================================================
# جداول نظام الأتمتة والذكاء الاصطناعي
# ============================================================================

class AITask(db.Model):
    """مهام الذكاء الاصطناعي المجدولة"""
    __tablename__ = 'ai_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    
    task_type = db.Column(db.String(100), nullable=False)  # schedule_optimization, risk_prediction, etc.
    task_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    parameters = db.Column(db.JSON)
    
    scheduled_time = db.Column(db.DateTime, nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    status = db.Column(db.String(50), default='pending')  # pending, running, completed, failed
    result = db.Column(db.JSON)
    error_message = db.Column(db.Text)
    
    priority = db.Column(db.Integer, default=3)  # 1-5
    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    project = relationship('Project')
    
    # فهرسة
    __table_args__ = (
        Index('idx_ai_task_type', 'task_type'),
        Index('idx_ai_task_status', 'status'),
        Index('idx_ai_task_project', 'project_id'),
        Index('idx_ai_task_scheduled', 'scheduled_time'),
        Index('idx_ai_task_priority', 'priority'),
    )


class AIRecommendation(db.Model):
    """توصيات الذكاء الاصطناعي"""
    __tablename__ = 'ai_recommendations'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    recommendation_type = db.Column(db.String(100), nullable=False)  # schedule, cost, risk, resource
    title = db.Column(db.String(500), nullable=False)
    title_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    
    current_state = db.Column(db.JSON)
    recommended_action = db.Column(db.Text)
    expected_benefit = db.Column(db.Text)
    
    confidence_score = db.Column(db.Float, default=0.0)  # 0-1
    urgency_level = db.Column(db.String(20), default='medium')  # low, medium, high
    
    generated_by = db.Column(db.String(100))  # اسم النموذج/الخوارزمية
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(50), default='pending')  # pending, reviewed, approved, implemented, rejected
    
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    reviewed_at = db.Column(db.DateTime)
    review_notes = db.Column(db.Text)
    
    implemented_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    implemented_at = db.Column(db.DateTime)
    implementation_notes = db.Column(db.Text)
    
    actual_benefit = db.Column(db.JSON)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    assignee = relationship('User', foreign_keys=[assigned_to])
    reviewer = relationship('User', foreign_keys=[reviewed_by])
    implementer = relationship('User', foreign_keys=[implemented_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_ai_rec_project', 'project_id'),
        Index('idx_ai_rec_type', 'recommendation_type'),
        Index('idx_ai_rec_status', 'status'),
        Index('idx_ai_rec_urgency', 'urgency_level'),
        Index('idx_ai_rec_confidence', 'confidence_score'),
        Index('idx_ai_rec_generated', 'generated_at'),
        Index('idx_ai_rec_assignee', 'assigned_to'),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 1", 
                       name='chk_ai_confidence'),
    )


# ============================================================================
# دالة تهيئة قاعدة البيانات
# ============================================================================

def init_db(app):
    """تهيئة قاعدة البيانات"""
    with app.app_context():
        # إنشاء جميع الجداول
        db.create_all()
        
        # إضافة البيانات الأولية
        create_initial_data()
        
        print("✅ قاعدة البيانات مهيأة بنجاح!")


def create_initial_data():
    """إنشاء البيانات الأولية"""
    
    # التحقق من وجود المؤسسة الافتراضية
    org = Organization.query.filter_by(org_code='DEFAULT').first()
    if not org:
        org = Organization(
            org_code='DEFAULT',
            name='الشركة الافتراضية',
            name_ar='الشركة الافتراضية',
            description='المؤسسة الافتراضية للنظام',
            settings={
                'currency': 'SAR',
                'language': 'ar',
                'timezone': 'Asia/Riyadh',
                'date_format': 'dd/MM/yyyy',
                'decimal_places': 2
            }
        )
        db.session.add(org)
        db.session.commit()
    
    # التحقق من وجود مدير النظام
    admin = User.query.filter_by(email='admin@company.com').first()
    if not admin:
        admin = User(
            org_id=org.id,
            username='admin',
            email='admin@company.com',
            full_name='مدير النظام',
            full_name_ar='مدير النظام',
            role='admin',
            is_active=True,
            is_verified=True
        )
        admin.set_password('Admin123!')
        db.session.add(admin)
        db.session.commit()
    
    print("✅ البيانات الأولية منشأة بنجاح!")
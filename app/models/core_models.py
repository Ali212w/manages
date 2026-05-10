"""
core_models.py - النماذج الأساسية مع دعم Multi-tenant
"""

from ..extensions import db
from sqlalchemy import Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, date,timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import uuid

# ============================================
# المؤسسة (الشركة المستخدمة للمنصة)
# ============================================
class PlatformOwner(db.Model):
    """الشركة المالكة للمنصة (SaaS Provider)"""
    __tablename__ = 'platform_owners'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # معلومات الشركة
    company_name = db.Column(db.String(200), nullable=False)
    commercial_register = db.Column(db.String(100), unique=True)
    tax_number = db.Column(db.String(100))
    
    # معلومات الاتصال
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    website = db.Column(db.String(200))
    
    # إعدادات المنصة
    platform_settings = db.Column(db.JSON, default={
        'allow_multi_companies': True,
        'max_companies': 100,
        'default_company_quota': {
            'max_users': 50,
            'max_projects': 100,
            'storage_gb': 10
        }
    })
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    platform_admins = relationship('PlatformAdmin', backref='platform', lazy=True)
    
    __table_args__ = (
        Index('idx_platform_email', 'email'),
        Index('idx_platform_commercial', 'commercial_register'),
    )

class PlatformAdmin(db.Model, UserMixin):
    """مدراء المنصة (Platform Admins)"""
    __tablename__ = 'platform_admins'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    platform_id = db.Column(db.Integer, db.ForeignKey('platform_owners.id'), nullable=False)
    
    # معلومات الحساب
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # المعلومات الشخصية
    full_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(20))
    profile_image = db.Column(db.String(200), default='default.jpg')
    
    # الدور في المنصة
    role = db.Column(db.String(50), default='admin')  # super_admin, admin, support, finance
    
    # الصلاحيات
    permissions = db.Column(db.JSON, default={
        'manage_platform': True,
        'manage_companies': True,
        'view_reports': True,
        'manage_admins': False,
        'manage_support': True,
        'manage_finance': True
    })
    
    # الحالة
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    def get_id(self):
        """الحصول على مفتاح الدخول الموحد"""
        return f"platform-{self.id}"
    # دوال المصادقة
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # def get_id(self):
    #     return str(self.id)
    
    # @property
    # def is_active(self):
    #     return self.is_active
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def increment_login_count(self):
        self.login_count = (self.login_count or 0) + 1
        self.last_login = datetime.utcnow()
    
    def has_permission(self, permission):
        if self.role == 'super_admin':
            return True
        return self.permissions.get(permission, False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'full_name': self.full_name,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    __table_args__ = (
        Index('idx_platform_admin_email', 'email'),
        Index('idx_platform_admin_platform', 'platform_id'),
        Index('idx_platform_admin_role', 'role'),
    )

class Organization(db.Model):
    """المؤسسة - الشركة المستخدمة للمنصة"""
    __tablename__ = 'organizations'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # معلومات المؤسسة
    org_code = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    # معلومات الاتصال
    address = db.Column(db.Text)
    phone = db.Column(db.String(50))
    email = db.Column(db.String(150))
    password_hash = db.Column(db.String(255), nullable=False)
    website = db.Column(db.String(200))
    tax_number = db.Column(db.String(100))
    commercial_register = db.Column(db.String(100))
    logo_url = db.Column(db.String(500))
    
    # حدود الاستخدام
    max_users = db.Column(db.Integer, default=50)
    max_projects = db.Column(db.Integer, default=100)
    storage_limit_mb = db.Column(db.Integer, default=10240)  # 10GB
    
    # الإحصائيات
    current_users = db.Column(db.Integer, default=0)
    current_projects = db.Column(db.Integer, default=0)
    storage_used_mb = db.Column(db.Integer, default=0)
    
    # الاشتراك
    subscription_status = db.Column(db.String(50), default='trial')  # trial, active, suspended, expired
    subscription_start = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)
    
    # الفترة التجريبية
    trial_start = db.Column(db.DateTime, default=datetime.utcnow)
    trial_end = db.Column(db.DateTime)
    
    # الحالة
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    
    # الإعدادات
    settings = db.Column(db.JSON, default={
        'currency': 'SAR',
        'language': 'ar',
        'timezone': 'Asia/Riyadh',
        'date_format': 'dd/MM/yyyy',
        'decimal_places': 2
    })
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer)  # من المنصة
    
    # العلاقات
    departments = relationship('Department', backref='organization', lazy=True, cascade='all, delete-orphan')
    projects = relationship('Project', backref='organization', lazy=True)
    users = relationship('User', backref='organization', lazy=True, cascade='all, delete-orphan')
    
    # فهرسة
    __table_args__ = (
        Index('idx_org_code', 'org_code'),
        Index('idx_org_name', 'name'),
        Index('idx_org_email', 'email'),
        Index('idx_org_status', 'subscription_status'),
    )

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)
    @property
    def trial_days_remaining(self):
        """الأيام المتبقية في الفترة التجريبية"""
        if self.subscription_status != 'trial':
            return 0
        if not self.trial_end:
            return 0
        remaining = (self.trial_end - datetime.utcnow()).days
        return max(0, remaining)
    
    @property
    def trial_days_used(self):
        """الأيام المستخدمة من الفترة التجريبية"""
        if not self.trial_start:
            return 0
        used = (datetime.utcnow() - self.trial_start).days
        return max(0, used)
    
    @property
    def trial_percentage(self):
        """نسبة الاستخدام من الفترة التجريبية (لشريط التقدم)"""
        if not self.trial_start or not self.trial_end:
            return 0
        total_days = (self.trial_end - self.trial_start).days
        if total_days <= 0:
            return 0
        used_days = self.trial_days_used
        return min(100, int((used_days / total_days) * 100))
    
    @property
    def is_trial_expiring_soon(self):
        """هل الفترة التجريبية على وشك الانتهاء (أقل من 3 أيام)"""
        return self.trial_days_remaining <= 3 and self.trial_days_remaining > 0
    
    @property
    def is_trial_active(self):
        """هل الفترة التجريبية لا تزال سارية"""
        if self.subscription_status != 'trial':
            return False
        if self.trial_end and self.trial_end > datetime.utcnow():
            return True
        return False
    
    def activate_trial(self, days=20):
        """تفعيل الفترة التجريبية للشركة"""
        self.subscription_status = 'trial'
        self.trial_start = datetime.utcnow()
        self.trial_end = datetime.utcnow() + timedelta(days=days)
        
        # تعيين حدود الخطة المجانية
        self.max_users = 10
        self.max_projects = 5
        self.storage_limit_mb = 1024  # 1 GB
        
        db.session.commit()
        
        # إنشاء اشتراك تجريبي في جدول الاشتراكات
        trial_subscription = Subscription(
            org_id=self.id,
            plan='free',
            plan_id='free',
            plan_name='Free Trial',
            amount=0,
            currency='SAR',
            payment_method='system',
            status='trial',
            start_date=datetime.utcnow(),
            end_date=self.trial_end,
            auto_renew=False,
            duration_months=0,
            created_by=None
        )
        db.session.add(trial_subscription)
        db.session.commit()
        
        return True
    
    def check_trial_expiration(self):
        """التحقق من انتهاء الفترة التجريبية وتحديث الحالة"""
        if self.subscription_status == 'trial':
            if self.trial_end and self.trial_end < datetime.utcnow():
                self.subscription_status = 'expired'
                db.session.commit()
                return True
        return False
    
    def get_id(self):
        """الحصول على مفتاح الدخول الموحد"""
        return f"org-{self.id}"
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    # الدوال
    def check_quota(self, resource_type):
        """التحقق من الحدود المسموحة"""
        if resource_type == 'users':
            return self.current_users < self.max_users
        elif resource_type == 'projects':
            return self.current_projects < self.max_projects
        elif resource_type == 'storage':
            return self.storage_used_mb < self.storage_limit_mb
        return True
    
    def increment_usage(self, resource_type):
        """زيادة عداد الاستخدام"""
        if resource_type == 'users':
            self.current_users += 1
        elif resource_type == 'projects':
            self.current_projects += 1
    
    def decrement_usage(self, resource_type):
        """إنقاص عداد الاستخدام"""
        if resource_type == 'users' and self.current_users > 0:
            self.current_users -= 1
        elif resource_type == 'projects' and self.current_projects > 0:
            self.current_projects -= 1
    
    
    
    def __repr__(self):
        return f'<Organization {self.org_code}: {self.name}>'


# ============================================
# الأقسام
# ============================================

class Department(db.Model):
    """الإدارة"""
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    dept_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    budget = db.Column(db.Float, default=0.0)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    parent = relationship('Department', remote_side=[id], backref='sub_departments')
    manager = relationship('User', foreign_keys=[manager_id], backref='managed_departments')
    employees = relationship('User', 
                           foreign_keys='User.dept_id',
                           backref='department', 
                           lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_dept_org', 'org_id', 'dept_code'),
        Index('idx_dept_parent', 'parent_id'),
        Index('idx_dept_manager', 'manager_id'),
        Index('idx_dept_active', 'is_active'),
        UniqueConstraint('org_id', 'dept_code', name='uq_dept_code_org'),
    )
    
    def is_descendant_of(self, dept):
        """التحقق مما إذا كان هذا القسم تابعاً للقسم المحدد"""
        if self.parent_id is None:
            return False
        
        if self.parent_id == dept.id:
            return True
        
        parent = Department.query.get(self.parent_id)
        if parent:
            return parent.is_descendant_of(dept)
        
        return False
    
    def get_all_children(self):
        """الحصول على جميع الأقسام الفرعية بشكل متكرر"""
        children = []
        for child in self.sub_departments:
            children.append(child)
            children.extend(child.get_all_children())
        return children
    def __repr__(self):
        return f'<Department {self.dept_code}: {self.name}>'


# ============================================
# المستخدمين
# ============================================

class User(db.Model, UserMixin):
    """المستخدم"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    dept_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    
    # معلومات الحساب
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    mobile = db.Column(db.String(20))
    employee_id = db.Column(db.String(50))
    
    # المعلومات الشخصية
    full_name = db.Column(db.String(200), nullable=False)
    job_title = db.Column(db.String(150))
    national_id = db.Column(db.String(50))
    birth_date = db.Column(db.Date)
    hire_date = db.Column(db.Date, default=date.today)
    profile_image = db.Column(db.String(200), default='default.jpg')
    # إعدادات الإشعارات
    email_notifications = db.Column(db.Boolean, default=True)
    push_notifications = db.Column(db.Boolean, default=True)
    task_reminders = db.Column(db.Boolean, default=True)
    daily_digest = db.Column(db.Boolean, default=False)
    
    # إعدادات المظهر
    theme = db.Column(db.String(20), default='light')
    sidebar_collapsed = db.Column(db.Boolean, default=False)
    # الأدوار والصلاحيات
    role = db.Column(db.String(50), nullable=False, default='employee')
    # roles: org_admin, project_manager, supervisor, delegate, employee
    
    permissions = db.Column(db.JSON, default={
        'view_projects': True,
        'create_tasks': False,
        'approve_expenses': False,
        'manage_users': False,
        'view_reports': True,
        'upload_documents': False,
        'manage_projects': False
    })
    
    # الحالة
    is_user_active = db.Column(db.Boolean, default=True)  # تغيير الاسم لتجنب التعارض
    is_verified = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)
    login_count = db.Column(db.Integer, default=0)
    
    # السجل الزمني
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer)  # من أنشأ المستخدم
    
    # العلاقات
    notifications = relationship('Notification', backref='user', lazy=True, cascade='all, delete-orphan')
    client_projects = relationship('Project',foreign_keys='Project.client_id',  backref='client')
    consultant_projects = relationship('Project', foreign_keys='Project.consultant_id', backref='consultant')
    supplier_projects = relationship('Project',foreign_keys='Project.supplier_id',  backref='supplier')
    # العلاقات مع المشاريع والمهام (سيتم تعريفها في ملفات أخرى)
    managed_projects = relationship('Project', foreign_keys='Project.project_manager_id', backref='manager')
    # supervised_tasks = relationship('Task', foreign_keys='Task.supervisor_id', backref='supervisor')
    # delegate_tasks = relationship('Task', foreign_keys='Task.delegate_id', backref='delegate')
    # ta sk_assignments = relationship('TaskAssignment', backref='assigned_user', lazy=True)
    # المحادثات التي أنشأها المستخدم
    created_chats = db.relationship(
        'ProjectChat',
        backref='creator',  # يسمح بالوصول من chat.creator
        lazy='dynamic',
        foreign_keys='ProjectChat.created_by',
        cascade='all, delete-orphan'
    )
    # فهرسة
    __table_args__ = (
        Index('idx_user_org', 'org_id'),
        Index('idx_user_dept', 'dept_id'),
        Index('idx_user_email', 'email'),
        Index('idx_user_username', 'username'),
        Index('idx_user_role', 'role'),
        Index('idx_user_active', 'is_user_active'),
        Index('idx_user_employee', 'employee_id'),
        UniqueConstraint('org_id', 'email', name='uq_user_email_org'),
        UniqueConstraint('org_id', 'username', name='uq_user_username_org'),
        UniqueConstraint('org_id', 'employee_id', name='uq_user_employee_org'),
    )
    
    # ==========================================
    # دوال Flask-Login
    # ==========================================
    def get_id(self):
        """الحصول على مفتاح الدخول الموحد"""
        return f"user-{self.id}"
    
    # def get_id(self):
    #     """إرجاع معرف المستخدم كسلسلة نصية"""
    #     return str(self.id)
    
    @property
    def is_active(self):
        """هل المستخدم نشط؟"""
        return self.is_user_active
    
    @property
    def is_authenticated(self):
        """هل المستخدم موثق؟"""
        return True
    
    @property
    def is_anonymous(self):
        """هل المستخدم مجهول؟"""
        return False
    @property
    def all_chats(self):
        """جميع محادثات المستخدم"""
        from app.models.communication_models import ProjectChat, ChatParticipant
        participations = ChatParticipant.query.filter_by(user_id=self.id).all()
        chat_ids = [p.chat_id for p in participations]
        return ProjectChat.query.filter(ProjectChat.id.in_(chat_ids)).all()
    
    @property
    def unread_chats_count(self):
        """عدد المحادثات ذات الرسائل غير المقروءة"""
        from app.models.communication_models import ChatMessage, ChatParticipant
        participations = ChatParticipant.query.filter_by(user_id=self.id).all()
        chat_ids = [p.chat_id for p in participations]
        
        if not chat_ids:
            return 0
        
        return ChatMessage.query.filter(
            ChatMessage.chat_id.in_(chat_ids),
            ChatMessage.sender_id != self.id,
            ChatMessage.is_read == False,
            ChatMessage.is_deleted == False
        ).count()
    # ==========================================
    # دوال إدارة كلمة المرور
    # ==========================================
    
    def set_password(self, password):
        """تعيين كلمة المرور"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """التحقق من كلمة المرور"""
        return check_password_hash(self.password_hash, password)
    
    @property
    def password(self):
        """منع قراءة كلمة المرور"""
        raise AttributeError('password is not a readable attribute')
    
    # ==========================================
    # دوال أخرى
    # ==========================================
    
    def increment_login_count(self):
        """زيادة عداد الدخول وتحديث آخر وقت دخول"""
        self.login_count = (self.login_count or 0) + 1
        self.last_login = datetime.utcnow()
    
    def get_full_name(self, lang='ar'):
        """الحصول على الاسم الكامل حسب اللغة"""
        if lang == 'ar' and self.full_name_ar:
            return self.full_name_ar
        return self.full_name
    
    def has_permission(self, permission):
        """التحقق من وجود صلاحية"""
        if self.role == 'org_admin':
            return True
        return self.permissions.get(permission, False)
    
    def is_admin(self):
        """هل المستخدم مدير المؤسسة؟"""
        return self.role == 'org_admin'
    
    def to_dict(self):
        """تحويل إلى قاموس"""
        return {
            'id': self.id,
            'uuid': self.uuid,
            'full_name': self.full_name,
            'full_name_ar': self.full_name_ar,
            'email': self.email,
            'phone': self.phone,
            'job_title': self.job_title,
            'role': self.role,
            'is_user_active': self.is_user_active,
            'is_verified': self.is_verified,
            'department': self.department.name if self.department else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }
    
    def __repr__(self):
        return f'<User {self.username} ({self.email})>'


# ============================================
# الاشتراكات
# ============================================

class Subscription(db.Model):
    """اشتراكات المؤسسات - معدل للربط مع SubscriptionPlan"""
    __tablename__ = 'subscriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # ============================================
    # 🔗 ربط الخطة مع SubscriptionPlan (تعديل مهم)
    # ============================================
    # الطريقة القديمة (احتفظ بها للتوافق مع البيانات القديمة)
    plan = db.Column(db.String(50), nullable=False)  # basic, professional, enterprise
    
    # ⭐ الطريقة الجديدة: ربط مع جدول الخطط
    plan_id = db.Column(db.String(50), db.ForeignKey('subscription_plans.plan_id'), nullable=True)
    
    # اسم الخطة (يمكن استخلاصه من العلاقة)
    plan_name = db.Column(db.String(100))
    
    # ⭐ العلاقة مع نموذج الخطة
    sub_plan = db.relationship(
        'SubscriptionPlan', 
        foreign_keys=[plan_id],
        backref='subscriptions_list',  # يمكن الوصول من الخطة: plan.subscriptions_list
        lazy='joined'  # تحميل تلقائي للخطة عند جلب الاشتراك
    )
    
    # المبالغ
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='SAR')
    
    # معلومات الدفع
    payment_method = db.Column(db.String(50))  # credit_card, bank_transfer, etc.
    transaction_id = db.Column(db.String(100))
    invoice_number = db.Column(db.String(100))
    
    # معلومات Stripe (إذا استخدمت)
    stripe_subscription_id = db.Column(db.String(100))
    stripe_customer_id = db.Column(db.String(100))
    stripe_payment_method_id = db.Column(db.String(100))
    
    # الحالة
    status = db.Column(db.String(20), default='active')  # active, cancelled, expired, pending, trial
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    auto_renew = db.Column(db.Boolean, default=True)
    
    # ⭐ حقل الفترة (بالأشهر)
    duration_months = db.Column(db.Integer, default=12)
    
    # ⭐ حقل تاريخ الإلغاء (إذا تم الإلغاء)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    cancelled_reason = db.Column(db.Text, nullable=True)
    
    # ⭐ حقل تاريخ التجديد التلقائي الأخير
    last_renewed_at = db.Column(db.DateTime, nullable=True)
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # تعديل: ربط مع users
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # ⭐ إضافة حقل محدث بواسطة
    
    # ============================================
    # 🔗 العلاقات
    # ============================================
    
    # العلاقة مع المؤسسة
    organization = db.relationship('Organization', backref='subscriptions', lazy='joined')
    
    # ⭐ العلاقة مع المستخدم الذي أنشأ الاشتراك
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_subscriptions')
    
    # ⭐ العلاقة مع المستخدم الذي عدل الاشتراك
    updater = db.relationship('User', foreign_keys=[updated_by], backref='updated_subscriptions')
    
    # ⭐ العلاقة مع الفواتير (إذا كان لديك نموذج Invoice)
    # invoices = db.relationship('Invoice', backref='subscription', lazy='dynamic')
    
    # ============================================
    # 📋 الفهرسة (معدلة)
    # ============================================
    
    __table_args__ = (
        Index('idx_sub_org', 'org_id'),
        Index('idx_sub_status', 'status'),
        Index('idx_sub_dates', 'start_date', 'end_date'),
        Index('idx_sub_stripe', 'stripe_subscription_id'),
        Index('idx_sub_plan', 'plan_id'),  # ⭐ إضافة فهرس للخطة
        Index('idx_sub_plan_old', 'plan'),  # فهرس للخطة القديمة
        Index('idx_sub_auto_renew', 'auto_renew'),
        Index('idx_sub_created', 'created_at'),
    )
    
    # ============================================
    # 📋 الخصائص المحسوبة (Properties)
    # ============================================
    
    @property
    def is_active(self):
        """التحقق من أن الاشتراك نشط"""
        if self.status != 'active':
            return False
        if self.end_date and self.end_date < datetime.utcnow():
            return False
        return True
    
    @property
    def is_expired(self):
        """التحقق من انتهاء الاشتراك"""
        if self.end_date and self.end_date < datetime.utcnow():
            return True
        return False
    
    @property
    def is_trial(self):
        """التحقق من أن الاشتراك تجريبي"""
        return self.status == 'trial' or self.plan == 'trial'
    
    @property
    def is_cancelled(self):
        """التحقق من إلغاء الاشتراك"""
        return self.status == 'cancelled'
    
    @property
    def days_remaining(self):
        """الأيام المتبقية في الاشتراك"""
        if not self.end_date:
            return None
        remaining = (self.end_date - datetime.utcnow()).days
        return max(0, remaining)
    
    @property
    def days_used(self):
        """الأيام المستخدمة من الاشتراك"""
        if not self.start_date:
            return 0
        used = (datetime.utcnow() - self.start_date).days
        return max(0, used)
    
    @property
    def usage_percentage(self):
        """نسبة الاستخدام (للعرض في شريط التقدم)"""
        if not self.start_date or not self.end_date:
            return 0
        total_days = (self.end_date - self.start_date).days
        if total_days <= 0:
            return 0
        used_days = self.days_used
        return min(100, int((used_days / total_days) * 100))
    
    @property
    def plan_info(self):
        """الحصول على معلومات الخطة كاملة (من العلاقة أو من البيانات المخزنة)"""
        if self.plan_details:
            return self.plan_details
        # إذا لم توجد علاقة، قم بإنشاء كائن افتراضي
        return self._get_fallback_plan_info()
    
    @property
    def plan_features(self):
        """الحصول على ميزات الخطة"""
        if self.plan_details:
            return self.plan_details.features
        return self._get_default_features()
    
    @property
    def total_paid(self):
        """إجمالي المدفوعات لهذا الاشتراك"""
        from sqlalchemy import func
        from app.models.finance_models import Payment
        from app.models.finance_models import Invoice
        
        total = db.session.query(func.sum(Payment.amount)).filter(
            Payment.invoice_id == Invoice.id,
            Invoice.subscription_id == self.id
        ).scalar() or 0
        return total
    
    # ============================================
    # 📋 الدوال
    # ============================================
    
    def days_remaining(self):
        """الأيام المتبقية في الاشتراك"""
        if not self.end_date:
            return None
        remaining = (self.end_date - datetime.utcnow()).days
        return max(0, remaining)
    
    def renew(self, duration_months=None, payment_method=None):
        """
        تجديد الاشتراك
        
        Args:
            duration_months: عدد أشهر التجديد (افتراضي: نفس المدة السابقة)
            payment_method: طريقة الدفع
        """
        if duration_months is None:
            duration_months = self.duration_months or 12
        
        # حساب تاريخ الانتهاء الجديد
        if self.end_date and self.end_date > datetime.utcnow():
            new_end_date = self.end_date + timedelta(days=duration_months * 30)
        else:
            new_end_date = datetime.utcnow() + timedelta(days=duration_months * 30)
        
        # حساب المبلغ الجديد
        if self.plan_details:
            new_amount = self.plan_details.get_price_for_duration(duration_months)
        else:
            new_amount = self.amount
        
        # إنشاء اشتراك جديد
        new_subscription = Subscription(
            org_id=self.org_id,
            plan=self.plan,
            plan_id=self.plan_id,
            plan_name=self.plan_name,
            amount=new_amount,
            currency=self.currency,
            payment_method=payment_method or self.payment_method,
            status='active',
            start_date=datetime.utcnow(),
            end_date=new_end_date,
            auto_renew=self.auto_renew,
            duration_months=duration_months,
            created_by=self.created_by
        )
        
        # تحديث الاشتراك الحالي
        self.status = 'expired'
        self.auto_renew = False
        
        db.session.add(new_subscription)
        db.session.commit()
        
        return new_subscription
    
    def cancel(self, reason=None):
        """إلغاء الاشتراك"""
        self.status = 'cancelled'
        self.auto_renew = False
        self.cancelled_at = datetime.utcnow()
        self.cancelled_reason = reason
        db.session.commit()
        return True
    
    def upgrade(self, new_plan_id, duration_months=None):
        """
        ترقية الاشتراك إلى خطة أعلى
        
        Args:
            new_plan_id: معرف الخطة الجديدة (مثل 'professional')
            duration_months: المدة بالأشهر
        """
        from app.models.core_models import SubscriptionPlan
        
        new_plan = SubscriptionPlan.query.filter_by(plan_id=new_plan_id, is_active=True).first()
        if not new_plan:
            raise ValueError(f"الخطة {new_plan_id} غير موجودة أو غير نشطة")
        
        if duration_months is None:
            duration_months = self.duration_months or 12
        
        # حساب المبلغ الجديد
        new_amount = new_plan.get_price_for_duration(duration_months)
        
        # حساب الخصم إذا كان هناك وقت متبقي في الاشتراك الحالي
        remaining_days = self.days_remaining
        if remaining_days > 0 and self.amount > 0:
            daily_rate = self.amount / (self.duration_months * 30)
            refund = daily_rate * remaining_days
            new_amount = max(0, new_amount - refund)
        
        # إنشاء اشتراك جديد
        new_subscription = Subscription(
            org_id=self.org_id,
            plan=new_plan_id,
            plan_id=new_plan_id,
            plan_name=new_plan.name,
            amount=new_amount,
            currency=self.currency,
            payment_method=self.payment_method,
            status='active',
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=duration_months * 30),
            auto_renew=self.auto_renew,
            duration_months=duration_months,
            created_by=self.created_by
        )
        
        # إنهاء الاشتراك الحالي
        self.status = 'expired'
        self.auto_renew = False
        
        db.session.add(new_subscription)
        db.session.commit()
        
        return new_subscription
    
    def downgrade(self, new_plan_id, duration_months=None):
        """
        تخفيض الاشتراك إلى خطة أقل
        
        Args:
            new_plan_id: معرف الخطة الجديدة
            duration_months: المدة بالأشهر
        """
        from app.models.core_models import SubscriptionPlan
        
        new_plan = SubscriptionPlan.query.filter_by(plan_id=new_plan_id, is_active=True).first()
        if not new_plan:
            raise ValueError(f"الخطة {new_plan_id} غير موجودة أو غير نشطة")
        
        if duration_months is None:
            duration_months = self.duration_months or 12
        
        # حساب المبلغ الجديد
        new_amount = new_plan.get_price_for_duration(duration_months)
        
        # إنشاء اشتراك جديد (يبدأ بعد انتهاء الاشتراك الحالي)
        new_subscription = Subscription(
            org_id=self.org_id,
            plan=new_plan_id,
            plan_id=new_plan_id,
            plan_name=new_plan.name,
            amount=new_amount,
            currency=self.currency,
            payment_method=self.payment_method,
            status='pending',  # في انتظار بدء الاشتراك الجديد
            start_date=self.end_date,  # يبدأ بعد انتهاء الاشتراك الحالي
            end_date=self.end_date + timedelta(days=duration_months * 30) if self.end_date else None,
            auto_renew=self.auto_renew,
            duration_months=duration_months,
            created_by=self.created_by
        )
        
        db.session.add(new_subscription)
        db.session.commit()
        
        return new_subscription
    
    def get_invoice(self):
        """الحصول على الفاتورة المرتبطة بهذا الاشتراك"""
        from app.models.finance_models import Invoice
        return Invoice.query.filter_by(subscription_id=self.id).first()
    
    def send_reminder(self):
        """إرسال تذكير باقتراب انتهاء الاشتراك"""
        from app.services.notification_service import NotificationService
        
        days_left = self.days_remaining
        if days_left <= 7 and days_left > 0:
            NotificationService.subscription_expiring(self.organization, self, days_left)
            return True
        return False
    
    def to_dict(self, lang='ar'):
        """تحويل الاشتراك إلى قاموس"""
        from app.services.translator import format_currency
        return {
            'id': self.id,
            'uuid': self.uuid,
            'organization': {
                'id': self.organization.id,
                'name': self.organization.name,
                'name_ar': getattr(self.organization, 'name_ar', None)
            } if self.organization else None,
            'plan': {
                'id': self.plan,
                'name': self.plan_name,
                'details': self.plan_details.to_dict(lang) if self.plan_details else None
            },
            'amount': self.amount,
            'amount_formatted': format_currency(self.amount, self.currency, lang),
            'currency': self.currency,
            'payment_method': self.payment_method,
            'status': self.status,
            'status_text': self._get_status_text(lang),
            'start_date': self.start_date.strftime('%Y-%m-%d') if self.start_date else None,
            'end_date': self.end_date.strftime('%Y-%m-%d') if self.end_date else None,
            'auto_renew': self.auto_renew,
            'days_remaining': self.days_remaining,
            'usage_percentage': self.usage_percentage,
            'is_active': self.is_active,
            'is_expired': self.is_expired,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }
    
    def _get_status_text(self, lang='ar'):
        """الحصول على نص الحالة مترجماً"""
        status_map = {
            'active': _('subscriptions.active') if lang == 'ar' else 'Active',
            'cancelled': _('subscriptions.cancelled') if lang == 'ar' else 'Cancelled',
            'expired': _('subscriptions.expired') if lang == 'ar' else 'Expired',
            'pending': _('status.pending') if lang == 'ar' else 'Pending',
            'trial': _('subscriptions.trial') if lang == 'ar' else 'Trial'
        }
        return status_map.get(self.status, self.status)
    
    def _get_fallback_plan_info(self):
        """إنشاء معلومات خطة افتراضية عندما لا توجد علاقة"""
        class FallbackPlan:
            def __init__(self, plan_id, name):
                self.plan_id = plan_id
                self.name = name
                self.features = []
                self.max_users = 0
                self.max_projects = 0
                self.storage_gb = 0
        
        plan_name_map = {
            'basic': 'Basic',
            'professional': 'Professional',
            'enterprise': 'Enterprise',
            'trial': 'Trial'
        }
        return FallbackPlan(self.plan, plan_name_map.get(self.plan, self.plan))
    
    def _get_default_features(self):
        """الميزات الافتراضية حسب الخطة"""
        features_map = {
            'basic': ['5 مشاريع', '20 مستخدم', '10 جيجابايت', 'دعم البريد الإلكتروني'],
            'professional': ['50 مشروع', '100 مستخدم', '50 جيجابايت', 'دعم أولوية', 'API'],
            'enterprise': ['مشاريع غير محدودة', 'مستخدمين غير محدودين', '200 جيجابايت', 'دعم VIP', 'API مخصص'],
            'trial': ['جميع الميزات لمدة 30 يوم']
        }
        return features_map.get(self.plan, [])
    
    def __repr__(self):
        return f'<Subscription {self.plan} for org {self.org_id}>'
# أضف هذا الكلاس في ملف core_models.py

class SubscriptionPlan(db.Model):
    """خطط الاشتراك في المنصة"""
    __tablename__ = 'subscription_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # معرف الخطة (مثل: basic, professional, enterprise)
    plan_id = db.Column(db.String(50), unique=True, nullable=False)
    
    # معلومات الخطة
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    
    # الأسعار
    price_monthly = db.Column(db.Float, default=0.0)
    price_yearly = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    
    # حدود الاستخدام
    max_users = db.Column(db.Integer, default=0)  # 0 = غير محدود
    max_projects = db.Column(db.Integer, default=0)  # 0 = غير محدود
    storage_gb = db.Column(db.Integer, default=0)  # 0 = غير محدود
    
    # الميزات (JSON array)
    features = db.Column(db.JSON, default=[])
    
    # ترتيب العرض
    display_order = db.Column(db.Integer, default=0)
    
    # هل الخطة مميزة (تظهر في أعلى القائمة)
    is_featured = db.Column(db.Boolean, default=False)
    
    # هل الخطة نشطة
    is_active = db.Column(db.Boolean, default=True)
    
    # خطة افتراضية للشركات الجديدة
    is_default = db.Column(db.Boolean, default=False)
    
    # إعدادات إضافية
    settings = db.Column(db.JSON, default={})
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('platform_admins.id'))
    updated_by = db.Column(db.Integer, db.ForeignKey('platform_admins.id'))
    
    # ============================================
    # 🔗 العلاقات مع النماذج الأخرى
    # ============================================
    
    # 1. علاقة مع مستخدم (من قام بإنشاء الخطة)
    creator = db.relationship('PlatformAdmin', foreign_keys=[created_by], backref='created_plans')
    
    # 2. علاقة مع مستخدم (من قام بتحديث الخطة)
    updater = db.relationship('PlatformAdmin', foreign_keys=[updated_by], backref='updated_plans')
    
    # 3. ⭐ علاقة مع الاشتراكات (كل خطة لها عدة اشتراكات)
    subscriptions = db.relationship(
        'Subscription', 
        backref='plan_details',  # يمكن الوصول من Subscription: subscription.plan_details
        lazy='dynamic',           # استخدام lazy='dynamic' للاستعلامات الكبيرة
        cascade='all, delete-orphan'  # حذف الاشتراكات عند حذف الخطة
    )
    
    # 4. ⭐ علاقة مع الشركات (الشركات التي تستخدم هذه الخطة حالياً)
    # ملاحظة: هذه علاقة غير مباشرة عبر جدول الاشتراكات
    @property
    def active_companies(self):
        """الحصول على الشركات النشطة التي تستخدم هذه الخطة"""
        from app.models.core_models import Organization
        return Organization.query.join(
            Subscription, Organization.id == Subscription.org_id
        ).filter(
            Subscription.plan == self.plan_id,
            Subscription.status == 'active'
        ).all()
    
    # 5. ⭐ عدد الشركات النشطة على هذه الخطة
    @property
    def active_companies_count(self):
        """عدد الشركات النشطة على هذه الخطة"""
        from app.models.core_models import Organization
        return Organization.query.join(
            Subscription, Organization.id == Subscription.org_id
        ).filter(
            Subscription.plan == self.plan_id,
            Subscription.status == 'active'
        ).count()
    
    __table_args__ = (
        Index('idx_sub_plan_id', 'plan_id'),
        Index('idx_sub_plan_active', 'is_active'),
        Index('idx_sub_plan_order', 'display_order'),
        Index('idx_sub_plan_default', 'is_default'),
    )
    
    # ============================================
    # 📋 دوال مساعدة
    # ============================================
    
    def to_dict(self, lang='ar'):
        """تحويل الخطة إلى قاموس"""
        return {
            'id': self.id,
            'plan_id': self.plan_id,
            'name': self.name,
            'description':  self.description,
            'price_monthly': self.price_monthly,
            'price_yearly': self.price_yearly,
            'currency': self.currency,
            'max_users': self.max_users,
            'max_projects': self.max_projects,
            'storage_gb': self.storage_gb,
            'features':  self.features,
            'is_featured': self.is_featured,
            'is_active': self.is_active,
            'is_default': self.is_default,
            'display_order': self.display_order,
            'active_companies': self.active_companies_count  # عدد الشركات النشطة
        }
    
    def get_price_for_duration(self, months=1):
        """الحصول على السعر حسب المدة"""
        if months >= 12:
            return self.price_yearly or (self.price_monthly * 12)
        return self.price_monthly * months
    
    def get_max_users_display(self, lang='ar'):
        """عرض الحد الأقصى للمستخدمين"""
        if self.max_users == 0:
            return _('plans.unlimited') if lang == 'ar' else 'Unlimited'
        return str(self.max_users)
    
    def get_max_projects_display(self, lang='ar'):
        """عرض الحد الأقصى للمشاريع"""
        if self.max_projects == 0:
            return _('plans.unlimited') if lang == 'ar' else 'Unlimited'
        return str(self.max_projects)
    
    def get_storage_display(self, lang='ar'):
        """عرض حد التخزين"""
        if self.storage_gb == 0:
            return _('plans.unlimited') if lang == 'ar' else 'Unlimited'
        return f'{self.storage_gb} ' + (_('storage.gb') if lang == 'ar' else 'GB')
    
    def is_available_for_company(self, company):
        """التحقق مما إذا كانت الخطة متاحة لشركة معينة"""
        if not self.is_active:
            return False
        
        # التحقق من حدود الشركة
        if self.max_users > 0 and company.current_users >= self.max_users:
            return False
        if self.max_projects > 0 and company.current_projects >= self.max_projects:
            return False
        if self.storage_gb > 0 and company.storage_used_mb >= self.storage_gb * 1024:
            return False
        
        return True
    
    def get_subscription_stats(self):
        """الحصول على إحصائيات الاشتراكات لهذه الخطة"""
        from sqlalchemy import func
        
        total_subscriptions = self.subscriptions.count()
        active_subscriptions = self.subscriptions.filter_by(status='active').count()
        expired_subscriptions = self.subscriptions.filter_by(status='expired').count()
        
        total_revenue = db.session.query(func.sum(Subscription.amount)).filter(
            Subscription.plan == self.plan_id,
            Subscription.status == 'active'
        ).scalar() or 0
        
        return {
            'total': total_subscriptions,
            'active': active_subscriptions,
            'expired': expired_subscriptions,
            'total_revenue': total_revenue
        }
    
    def __repr__(self):
        return f'<SubscriptionPlan {self.plan_id}: {self.name}>'
# ============================================
# سجل النشاطات (Audit Log)
# ============================================

# # جدول سجل النشاطات (يمكن إضافة نموذج جديد)
class PlatformAuditLog(db.Model):
    """سجل نشاطات المنصة"""
    __tablename__ = 'platform_audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, nullable=False)
    admin_name = db.Column(db.String(200))
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))
    target_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# في core_models.py - أضف هذا النموذج

class PlatformNotification(db.Model):
    """إشعارات إدارة المنصة"""
    __tablename__ = 'platform_notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # المستهدف (مدير المنصة)
    admin_id = db.Column(db.Integer, db.ForeignKey('platform_admins.id'), nullable=False)
    
    # محتوى الإشعار
    title = db.Column(db.String(500), nullable=False)
    title_en = db.Column(db.String(500))
    message = db.Column(db.Text, nullable=False)
    message_en = db.Column(db.Text)
    
    # نوع الإشعار
    notification_type = db.Column(db.String(50), nullable=False)
    # possible types:
    # - new_company_registration (تسجيل شركة جديدة)
    # - subscription_request (طلب اشتراك جديد)
    # - payment_proof_uploaded (رفع إثبات دفع)
    # - company_verification_request (طلب توثيق شركة)
    # - system_alert (تنبيه نظام)
    # - weekly_report (تقرير أسبوعي)
    # - subscription_expiring (اشتراك على وشك الانتهاء)
    # - new_user_registration (مستخدم جديد)
    # - support_ticket (تذكرة دعم)
    # - backup_completed (اكتمال النسخ الاحتياطي)
    # - error_alert (تنبيه خطأ)
    
    # أولوية الإشعار
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    
    # رابط الإجراء
    action_url = db.Column(db.String(500))
    action_text = db.Column(db.String(100))
    action_text_en = db.Column(db.String(100))
    
    # أيقونة الإشعار
    icon = db.Column(db.String(50), default='bell')
    
    # بيانات إضافية (JSON)
    data = db.Column(db.JSON, default={})
    
    # الحالة
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime)
    is_sent = db.Column(db.Boolean, default=False)  # هل تم إرسال بريد إلكتروني
    sent_at = db.Column(db.DateTime)
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    admin = db.relationship('PlatformAdmin', foreign_keys=[admin_id], backref='notifications')
    
    __table_args__ = (
        Index('idx_platform_notif_admin', 'admin_id'),
        Index('idx_platform_notif_type', 'notification_type'),
        Index('idx_platform_notif_priority', 'priority'),
        Index('idx_platform_notif_read', 'is_read'),
        Index('idx_platform_notif_created', 'created_at'),
        Index('idx_platform_notif_sent', 'is_sent'),
    )
    
    def mark_as_read(self):
        """تحديد الإشعار كمقروء"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    def mark_as_sent(self):
        """تحديد الإشعار كمرسل (بريد إلكتروني)"""
        if not self.is_sent:
            self.is_sent = True
            self.sent_at = datetime.utcnow()
            db.session.commit()
            return True
        return False
    
    def get_title(self, lang='ar'):
        """الحصول على العنوان حسب اللغة"""
        if lang == 'ar':
            return self.title
        return self.title_en or self.title
    
    def get_message(self, lang='ar'):
        """الحصول على الرسالة حسب اللغة"""
        if lang == 'ar':
            return self.message
        return self.message_en or self.message
    
    def get_action_text(self, lang='ar'):
        """الحصول على نص الإجراء حسب اللغة"""
        if lang == 'ar':
            return self.action_text or 'عرض التفاصيل'
        return self.action_text_en or self.action_text or 'View Details'
    
    def get_icon_class(self):
        """الحصول على كلاس الأيقونة حسب نوع الإشعار"""
        icons = {
            'new_company_registration': 'building',
            'subscription_request': 'credit-card',
            'payment_proof_uploaded': 'file-invoice-dollar',
            'company_verification_request': 'check-circle',
            'system_alert': 'exclamation-triangle',
            'weekly_report': 'chart-line',
            'subscription_expiring': 'hourglass-half',
            'new_user_registration': 'user-plus',
            'support_ticket': 'headset',
            'backup_completed': 'database',
            'error_alert': 'bug'
        }
        icon_name = icons.get(self.notification_type, 'bell')
        return f'fas fa-{icon_name}'
    
    def get_priority_class(self):
        """الحصول على كلاس الأولوية"""
        classes = {
            'low': 'info',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'danger'
        }
        return classes.get(self.priority, 'secondary')
    
    def get_priority_badge(self, lang='ar'):
        """الحصول على شارة الأولوية"""
        texts = {
            'low': {'ar': 'منخفضة', 'en': 'Low'},
            'medium': {'ar': 'متوسطة', 'en': 'Medium'},
            'high': {'ar': 'عالية', 'en': 'High'},
            'critical': {'ar': 'حرجة', 'en': 'Critical'}
        }
        text = texts.get(self.priority, {'ar': self.priority, 'en': self.priority})[lang]
        return f'<span class="badge bg-{self.get_priority_class()}">{text}</span>'
    
    def to_dict(self, lang='ar'):
        """تحويل الإشعار إلى قاموس"""
        return {
            'id': self.id,
            'uuid': self.uuid,
            'title': self.get_title(lang),
            'message': self.get_message(lang),
            'type': self.notification_type,
            'priority': self.priority,
            'priority_badge': self.get_priority_badge(lang),
            'icon': self.get_icon_class(),
            'action_url': self.action_url,
            'action_text': self.get_action_text(lang),
            'data': self.data,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat(),
            'created_at_formatted': self.created_at.strftime('%Y-%m-%d %H:%M'),
            'time_ago': self._get_time_ago()
        }
    
    def _get_time_ago(self):
        """حساب الوقت المنقضي"""
        if not self.created_at:
            return ''
        now = datetime.utcnow()
        diff = now - self.created_at
        
        if diff.days > 365:
            return f'منذ {diff.days // 365} سنة'
        elif diff.days > 30:
            return f'منذ {diff.days // 30} شهر'
        elif diff.days > 0:
            return f'منذ {diff.days} يوم'
        elif diff.seconds > 3600:
            return f'منذ {diff.seconds // 3600} ساعة'
        elif diff.seconds > 60:
            return f'منذ {diff.seconds // 60} دقيقة'
        else:
            return 'منذ لحظات'
    
    def __repr__(self):
        return f'<PlatformNotification {self.notification_type} for admin {self.admin_id}>'
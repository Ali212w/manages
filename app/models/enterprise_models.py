"""
enterprise_models.py - إضافة العلاقات مع النماذج السابقة
"""

from . import db
from sqlalchemy import Index, UniqueConstraint
from datetime import datetime
import uuid

# ============================================
# نموذج OBS مع العلاقات
# ============================================

class OBS(db.Model):
    """Organizational Breakdown Structure - هيكل المسؤولية"""
    __tablename__ = 'obs'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    obs_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    parent_id = db.Column(db.Integer, db.ForeignKey('obs.id'))
    level = db.Column(db.Integer, default=1)
    path = db.Column(db.String(500))
    
    responsible_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    parent = db.relationship('OBS', remote_side=[id], backref='children')
    responsible = db.relationship('User', foreign_keys=[responsible_id], backref='responsible_obs')
    
    # علاقات مع EPS
    eps_assignments = db.relationship('EPSOBSAssignment', back_populates='obs', lazy=True)
    
    # المشاريع المرتبطة
    # المشاريع المسؤولة عنها هذه OBS
    projects = db.relationship(
        'Project', 
        backref='obs',  # استخدم back_populates
        lazy='dynamic'
    )
    
    __table_args__ = (
        Index('idx_obs_org', 'org_id'),
        Index('idx_obs_code', 'obs_code'),
        Index('idx_obs_parent', 'parent_id'),
        Index('idx_obs_responsible', 'responsible_id'),
        UniqueConstraint('org_id', 'obs_code', name='uq_obs_code'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'obs_code': self.obs_code,
            'name': self.name,
            'description': self.description,
            'level': self.level,
            'path': self.path,
            'responsible': self.responsible.full_name if self.responsible else None,
            'projects_count': self.projects.count()
        }
    
    def get_accessible_eps(self, permission='read'):
        """الحصول على عناصر EPS المتاحة لهذا OBS"""
        return [a.eps for a in self.eps_permissions 
                if a.permission_level in [permission, 'admin']]


# ============================================
# نموذج Role مع العلاقات
# ============================================

class Role(db.Model):
    """الأدوار الوظيفية"""
    __tablename__ = 'roles'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    role_code = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    
    default_cost_per_hour = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    
    required_skills = db.Column(db.JSON, default=[])
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    activities = db.relationship('Activity', 
                                foreign_keys='Activity.role_id',
                                backref='assigned_role',
                                lazy='dynamic')
    
    resources = db.relationship('Resource', 
                               foreign_keys='Resource.role_id',
                               backref='assigned_role',
                               lazy='dynamic')
    
    __table_args__ = (
        Index('idx_role_org', 'org_id'),
        Index('idx_role_code', 'role_code'),
        Index('idx_role_cost', 'default_cost_per_hour'),
        UniqueConstraint('org_id', 'role_code', name='uq_role_code'),
    )
    
    def get_assigned_count(self):
        """الحصول على عدد الموارد المعينة لهذا الدور"""
        return self.resources.count()
    
    def get_activity_count(self):
        """الحصول على عدد الأنشطة التي تستخدم هذا الدور"""
        return self.activities.count()


# ============================================
# نموذج ResourceCode مع العلاقات
# ============================================

class ResourceCode(db.Model):
    """أكواد تصنيف الموارد"""
    __tablename__ = 'resource_codes'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    code_type = db.Column(db.String(100), nullable=False)
    code_value = db.Column(db.String(50), nullable=False)
    code_description = db.Column(db.String(200))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # لا توجد علاقات مباشرة - يتم تخزين القيم في JSON
    
    __table_args__ = (
        Index('idx_resource_code_org', 'org_id'),
        Index('idx_resource_code_type', 'code_type'),
        Index('idx_resource_code_value', 'code_value'),
    )


# ============================================
# نموذج ActivityCode مع العلاقات
# ============================================

class ActivityCodeDictionary(db.Model):
    """قاموس أكواد الأنشطة - مثل Primavera"""
    __tablename__ = 'activity_code_dictionaries'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # معلومات القاموس
    dict_name = db.Column(db.String(100), nullable=False)  # اسم القاموس (مثل: الأولويات، المسؤولية)
    description = db.Column(db.Text)
    
    # إعدادات القاموس
    max_length = db.Column(db.Integer, default=20)  # أقصى طول للكود
    is_active = db.Column(db.Boolean, default=True)
    is_hierarchical = db.Column(db.Boolean, default=False)  # هل الكود هرمي؟
    delimiter = db.Column(db.String(5), default='.')  # الفاصل في الأكواد الهرمية
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    codes = db.relationship('ActivityCodeValue', backref='dictionary', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('ActivityCodeAssignment', backref='dictionary', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_activity_dict_org', 'org_id'),
        UniqueConstraint('org_id', 'dict_name', name='uq_activity_dict_name'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'name': self.dict_name,
            'description': self.description,
            'max_length': self.max_length,
            'is_hierarchical': self.is_hierarchical,
            'delimiter': self.delimiter,
            'codes_count': self.codes.count()
        }


class ActivityCodeValue(db.Model):
    """قيم أكواد الأنشطة - القيم التي تظهر عند الضغط على +"""
    __tablename__ = 'activity_code_values'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    dictionary_id = db.Column(db.Integer, db.ForeignKey('activity_code_dictionaries.id'), nullable=False)
    
    # قيمة الكود
    code_value = db.Column(db.String(100), nullable=False)  # قيمة الكود (مثل: High, Medium, Low)
    code_description = db.Column(db.Text)
    
    # للعرض في القائمة (Primavera style)
    display_sequence = db.Column(db.Integer, default=0)  # ترتيب العرض
    display_color = db.Column(db.String(20), default='#4361ee')  # لون العرض
    
    # التسلسل الهرمي (للهياكل الهرمية)
    parent_id = db.Column(db.Integer, db.ForeignKey('activity_code_values.id'), nullable=True)
    level = db.Column(db.Integer, default=1)
    full_path = db.Column(db.String(500))  # المسار الكامل (مثل: 1.2.3)
    
    # الحالة
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    parent = db.relationship('ActivityCodeValue', remote_side=[id], backref='children')
    assignments = db.relationship('ActivityCodeAssignment', backref='code_value', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_activity_code_dict', 'dictionary_id'),
        Index('idx_activity_code_parent', 'parent_id'),
        Index('idx_activity_code_value', 'code_value'),
        UniqueConstraint('dictionary_id', 'code_value', name='uq_activity_code_value'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'code_value': self.code_value,
            'description': self.code_description,
            'display_sequence': self.display_sequence,
            'display_color': self.display_color,
            'level': self.level,
            'full_path': self.full_path,
            'parent_id': self.parent_id,
            'has_children': len(self.children) > 0 if self.children else False
        }


class ActivityCodeAssignment(db.Model):
    """ربط قيم الأكواد بالأنشطة"""
    __tablename__ = 'activity_code_assignments'
    
    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=False)
    dictionary_id = db.Column(db.Integer, db.ForeignKey('activity_code_dictionaries.id'), nullable=False)
    code_value_id = db.Column(db.Integer, db.ForeignKey('activity_code_values.id'), nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    activity = db.relationship('Activity', backref='code_assignments')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_activity_code_assign_activity', 'activity_id'),
        Index('idx_activity_code_assign_dict', 'dictionary_id'),
        Index('idx_activity_code_assign_value', 'code_value_id'),
        UniqueConstraint('activity_id', 'dictionary_id', name='uq_activity_code_per_dict'),
    )
# ============================================
# نموذج UDF مع العلاقات
# ============================================

class UDF(db.Model):
    """User Defined Fields - الحقول المخصصة"""
    __tablename__ = 'udf'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    udf_type = db.Column(db.String(50), nullable=False)  # activity, project, resource, wbs
    udf_name = db.Column(db.String(100), nullable=False)
    udf_label = db.Column(db.String(200))
    udf_label_ar = db.Column(db.String(200))
    
    data_type = db.Column(db.String(50), default='text')  # text, number, date, boolean, list
    default_value = db.Column(db.String(500))
    
    list_values = db.Column(db.JSON, default=[])
    
    is_required = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # لا توجد علاقات مباشرة - يتم تطبيقها على العناصر
    
    __table_args__ = (
        Index('idx_udf_org', 'org_id'),
        Index('idx_udf_type', 'udf_type'),
    )


# ============================================
# نموذج GlobalChange مع العلاقات
# ============================================

class GlobalChange(db.Model):
    """نماذج التغيير الشامل"""
    __tablename__ = 'global_changes'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    change_name = db.Column(db.String(200), nullable=False)
    change_description = db.Column(db.Text)
    
    target_type = db.Column(db.String(50), nullable=False)  # activity, project, resource
    conditions = db.Column(db.JSON, default=[])
    actions = db.Column(db.JSON, default=[])
    
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_run = db.Column(db.DateTime)
    run_count = db.Column(db.Integer, default=0)
    
    # العلاقات
    creator = db.relationship('User', foreign_keys=[created_by], backref='global_changes')
    
    __table_args__ = (
        Index('idx_global_change_org', 'org_id'),
        Index('idx_global_change_target', 'target_type'),
    )


# ============================================
# نموذج AdminPreference مع العلاقات
# ============================================

class AdminPreference(db.Model):
    """تفضيلات الإدارة"""
    __tablename__ = 'admin_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    date_format = db.Column(db.String(20), default='dd/MM/yyyy')
    time_format = db.Column(db.String(20), default='HH:mm')
    week_start = db.Column(db.Integer, default=1)
    fiscal_year_start = db.Column(db.String(10), default='01-01')
    
    base_currency = db.Column(db.String(3), default='SAR')
    decimal_places = db.Column(db.Integer, default=2)
    
    number_format = db.Column(db.String(20), default='###,###.##')
    
    units_of_measure = db.Column(db.JSON, default=['day', 'hour', 'm³', 'ton'])
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    organization = db.relationship('Organization', foreign_keys=[org_id], backref='admin_preferences')
    
    __table_args__ = (
        Index('idx_admin_pref_org', 'org_id'),
    )
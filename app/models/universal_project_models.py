"""
نماذج موحدة لإدارة جميع أنواع المشاريع
"""
from . import db
from sqlalchemy import Index, UniqueConstraint, JSON, Float, Integer, String, Text, Date, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

class UniversalProject(db.Model):
    """
    نموذج موحد للمشروع يدعم جميع المجالات
    """
    __tablename__ = 'universal_projects'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # ============ المعلومات الأساسية ============
    project_code = db.Column(db.String(50), nullable=False)
    project_name = db.Column(db.String(500), nullable=False)
    project_name_ar = db.Column(db.String(500))
    description = db.Column(db.Text)
    objectives = db.Column(db.Text)  # أهداف المشروع
    
    # ============ التصنيف الذكي ============
    domain = db.Column(db.String(100))  # هندسي، تقني، إداري، إلخ
    subdomain = db.Column(db.String(100))  # تخصص دقيق
    project_type = db.Column(db.String(100))  # نوع محدد
    classification_confidence = db.Column(db.Float, default=0.0)  # ثقة التصنيف
    classified_by_ai = db.Column(db.Boolean, default=False)
    classified_at = db.Column(db.DateTime)
    
    # ============ المنهجية ============
    methodology_primary = db.Column(db.String(50), default='pmbok')  # pmbok, agile, prince2, scrum, hybrid
    methodology_secondary = db.Column(db.String(50))
    methodology_custom = db.Column(db.Text)
    
    # ============ الجدول الزمني ============
    start_date = db.Column(db.Date)  # تاريخ البداية
    planned_end_date = db.Column(db.Date)  # تاريخ النهاية المخطط
    actual_end_date = db.Column(db.Date)  # تاريخ النهاية الفعلي
    duration_days = db.Column(db.Integer)  # المدة بالأيام
    
    # ============ التقدم ============
    progress_percentage = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='pending')
    health_status = db.Column(db.String(20), default='good')  # good, at_risk, critical
    
    # ============ الفريق ============
    project_manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    sponsor_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # راعي المشروع
    team_members = db.Column(JSON)  # قائمة أعضاء الفريق
    
    # ============ المالية ============
    budget = db.Column(db.Float, default=0.0)
    actual_cost = db.Column(db.Float, default=0.0)
    currency = db.Column(db.String(3), default='SAR')
    
    # ============ الجودة ============
    quality_score = db.Column(db.Float, default=100.0)
    quality_standards = db.Column(JSON)  # معايير الجودة المطبقة
    
    # ============ المخاطر ============
    risk_score = db.Column(db.Float, default=0.0)  # درجة المخاطرة
    risk_level = db.Column(db.String(20), default='low')
    
    # ============ حقول مخصصة حسب المجال ============
    custom_fields = db.Column(JSON)  # JSON مرن للحقول المخصصة
    
    # ============ مستندات ومرفقات ============
    attachments = db.Column(JSON)  # قائمة المرفقات
    
    # ============ السجل الزمني ============
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # ============ العلاقات ============
    manager = db.relationship('User', foreign_keys=[project_manager_id])
    sponsor = db.relationship('User', foreign_keys=[sponsor_id])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # العلاقات مع الجداول الأخرى
    phases = db.relationship('ProjectPhase', backref='project', lazy=True, cascade='all, delete-orphan')
    deliverables = db.relationship('Deliverable', backref='project', lazy=True, cascade='all, delete-orphan')
    metrics = db.relationship('ProjectMetric', backref='project', lazy=True, cascade='all, delete-orphan')
    risks = db.relationship('UniversalRisk', backref='project', lazy=True, cascade='all, delete-orphan')
    issues = db.relationship('UniversalIssue', backref='project', lazy=True, cascade='all, delete-orphan')
    decisions = db.relationship('Decision', backref='project', lazy=True, cascade='all, delete-orphan')
    lessons_learned = db.relationship('LessonLearned', backref='project', lazy=True, cascade='all, delete-orphan')
    stakeholders = db.relationship('Stakeholder', backref='project', lazy=True, cascade='all, delete-orphan')
    communications = db.relationship('Communication', backref='project', lazy=True, cascade='all, delete-orphan')
    
    # الفهارس
    __table_args__ = (
        Index('idx_universal_project_org', 'org_id'),
        Index('idx_universal_project_code', 'project_code'),
        Index('idx_universal_project_domain', 'domain'),
        Index('idx_universal_project_status', 'status'),
        Index('idx_universal_project_dates', 'start_date', 'planned_end_date'),
        Index('idx_universal_project_health', 'health_status'),
        UniqueConstraint('org_id', 'project_code', name='uq_universal_project_code'),
    )
    
    def to_dict(self):
        """تحويل المشروع إلى قاموس"""
        return {
            'id': self.id,
            'uuid': self.uuid,
            'project_code': self.project_code,
            'project_name': self.project_name,
            'project_name_ar': self.project_name_ar,
            'domain': self.domain,
            'subdomain': self.subdomain,
            'project_type': self.project_type,
            'status': self.status,
            'health_status': self.health_status,
            'progress_percentage': self.progress_percentage,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'planned_end_date': self.planned_end_date.isoformat() if self.planned_end_date else None,
            'budget': self.budget,
            'actual_cost': self.actual_cost,
            'methodology': self.methodology_primary,
            'custom_fields': self.custom_fields
        }
    
    def calculate_health(self):
        """حساب صحة المشروع بناءً على الوقت، التكلفة، الجودة"""
        health_score = 100
        
        # عامل الوقت
        if self.planned_end_date and self.start_date:
            today = datetime.now().date()
            total_duration = (self.planned_end_date - self.start_date).days
            elapsed = (today - self.start_date).days
            
            if total_duration > 0:
                expected_progress = (elapsed / total_duration) * 100
                progress_variance = self.progress_percentage - expected_progress
                
                if progress_variance < -10:
                    health_score -= 30
                    self.health_status = 'critical'
                elif progress_variance < -5:
                    health_score -= 15
                    self.health_status = 'at_risk'
        
        # عامل التكلفة
        if self.budget > 0:
            cost_variance = ((self.actual_cost - self.budget) / self.budget) * 100
            if cost_variance > 10:
                health_score -= 25
                self.health_status = 'critical'
            elif cost_variance > 5:
                health_score -= 15
                self.health_status = 'at_risk'
        
        # عامل الجودة
        health_score = (health_score + self.quality_score) / 2
        
        return health_score


class ProjectPhase(db.Model):
    """مراحل المشروع"""
    __tablename__ = 'project_phases'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    phase_name = db.Column(db.String(200), nullable=False)
    phase_order = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    progress = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(50), default='pending')
    
    deliverables = db.Column(JSON)  # مخرجات المرحلة
    gate_criteria = db.Column(JSON)  # معايير اجتياز المرحلة
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Deliverable(db.Model):
    """مخرجات المشروع"""
    __tablename__ = 'deliverables'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    phase_id = db.Column(db.Integer, db.ForeignKey('project_phases.id'))
    
    deliverable_name = db.Column(db.String(500), nullable=False)
    deliverable_type = db.Column(db.String(100))  # مستند، برنامج، منتج، خدمة
    description = db.Column(db.Text)
    
    acceptance_criteria = db.Column(db.Text)  # معايير القبول
    quality_requirements = db.Column(JSON)
    
    planned_date = db.Column(db.Date)
    actual_date = db.Column(db.Date)
    status = db.Column(db.String(50), default='pending')
    
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_at = db.Column(db.DateTime)
    
    attachments = db.Column(JSON)
    
    __table_args__ = (
        Index('idx_deliverable_project', 'project_id'),
        Index('idx_deliverable_status', 'status'),
    )


class ProjectMetric(db.Model):
    """مقاييس المشروع المخصصة"""
    __tablename__ = 'project_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    metric_name = db.Column(db.String(200), nullable=False)
    metric_type = db.Column(db.String(50))  # kpi, performance, quality, etc.
    metric_category = db.Column(db.String(50))  # time, cost, quality, scope, risk
    
    target_value = db.Column(db.Float)
    actual_value = db.Column(db.Float)
    unit = db.Column(db.String(50))
    
    measurement_date = db.Column(db.Date)
    trend = db.Column(db.String(20))  # improving, stable, declining
    
    notes = db.Column(db.Text)
    
    __table_args__ = (
        Index('idx_metric_project', 'project_id'),
        Index('idx_metric_category', 'metric_category'),
    )


class UniversalRisk(db.Model):
    """مخاطر المشروع"""
    __tablename__ = 'universal_risks'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    risk_code = db.Column(db.String(50))
    risk_title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))  # تقني، مالي، قانوني، تنظيمي، إلخ
    
    probability = db.Column(db.Integer)  # 1-5
    impact = db.Column(db.Integer)  # 1-5
    risk_score = db.Column(db.Integer)  # probability * impact
    
    response_strategy = db.Column(db.String(50))  # avoid, mitigate, transfer, accept
    response_plan = db.Column(db.Text)
    
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(50), default='identified')
    
    identified_date = db.Column(db.Date, default=datetime.now)
    reviewed_date = db.Column(db.Date)
    
    __table_args__ = (
        Index('idx_risk_project', 'project_id'),
        Index('idx_risk_status', 'status'),
        Index('idx_risk_score', 'risk_score'),
    )


class Stakeholder(db.Model):
    """أصحاب المصلحة"""
    __tablename__ = 'stakeholders'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    stakeholder_name = db.Column(db.String(200), nullable=False)
    stakeholder_type = db.Column(db.String(50))  # internal, external, client, sponsor
    organization = db.Column(db.String(200))
    position = db.Column(db.String(200))
    
    influence = db.Column(db.Integer)  # 1-5
    interest = db.Column(db.Integer)  # 1-5
    engagement_level = db.Column(db.String(50))  # unaware, resistant, neutral, supportive, leading
    
    communication_needs = db.Column(db.Text)
    expectations = db.Column(db.Text)
    
    contact_info = db.Column(JSON)
    
    __table_args__ = (
        Index('idx_stakeholder_project', 'project_id'),
    )


class Communication(db.Model):
    """التواصل في المشروع"""
    __tablename__ = 'communications'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    comm_type = db.Column(db.String(50))  # meeting, email, report, presentation
    subject = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text)
    
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    recipients = db.Column(JSON)  # قائمة المستلمين
    
    sent_date = db.Column(db.DateTime, default=datetime.utcnow)
    requires_response = db.Column(db.Boolean, default=False)
    response_by = db.Column(db.DateTime)
    
    attachments = db.Column(JSON)
    
    __table_args__ = (
        Index('idx_comm_project', 'project_id'),
        Index('idx_comm_date', 'sent_date'),
    )


class Decision(db.Model):
    """القرارات المتخذة"""
    __tablename__ = 'decisions'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    decision_title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    decision_type = db.Column(db.String(100))
    
    alternatives = db.Column(JSON)  # البدائل
    rationale = db.Column(db.Text)  # مبررات القرار
    
    made_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    made_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    impact = db.Column(db.Text)  # تأثير القرار
    approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)


class LessonLearned(db.Model):
    """الدروس المستفادة"""
    __tablename__ = 'lessons_learned'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('universal_projects.id'), nullable=False)
    
    title = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(100))
    
    situation = db.Column(db.Text)  # الموقف
    action = db.Column(db.Text)  # الإجراء
    result = db.Column(db.Text)  # النتيجة
    recommendation = db.Column(db.Text)  # التوصية
    
    documented_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    documented_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    is_positive = db.Column(db.Boolean, default=True)
    shared_with = db.Column(JSON)
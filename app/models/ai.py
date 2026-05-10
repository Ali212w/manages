"""
ai_models.py - نماذج الذكاء الاصطناعي المتقدمة لإدارة المشاريع
"""

from . import db
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from datetime import datetime, date
import uuid
import json

# ============================================
# 🤖 AI Command - أوامر الذكاء الاصطناعي
# ============================================

class AICommand(db.Model):
    """
    نموذج لتخزين أوامر الذكاء الاصطناعي التي يرسلها مدير الشركة
    """
    __tablename__ = 'ai_commands'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # الأمر والبرومبت
    command_text = db.Column(db.Text, nullable=False)  # النص الذي كتبه المدير
    command_type = db.Column(db.String(50))  # create, update, delete, read, analyze, report
    target_type = db.Column(db.String(50))  # project, task, user, resource, wbs, eps, obs, document
    
    # الملفات المرفقة
    has_attachments = db.Column(db.Boolean, default=False)
    attachments_count = db.Column(db.Integer, default=0)
    
    # حالة المعالجة
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    progress = db.Column(db.Integer, default=0)  # 0-100
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # نتيجة المعالجة
    result_summary = db.Column(db.Text)  # ملخص النتيجة
    result_data = db.Column(db.JSON)  # البيانات المستخرجة
    result_stats = db.Column(db.JSON)  # إحصائيات النتيجة
    error_message = db.Column(db.Text)  # رسالة الخطأ إن وجد
    
    # التكلفة والمدة
    processing_time = db.Column(db.Float)  # بالثواني
    tokens_used = db.Column(db.Integer)  # عدد التوكنز المستخدمة
    estimated_cost = db.Column(db.Float)  # التكلفة التقديرية
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    organization = db.relationship('Organization', backref='ai_commands')
    user = db.relationship('User', backref='ai_commands')
    attachments = db.relationship('AICommandAttachment', backref='command', lazy='dynamic', cascade='all, delete-orphan')
    results = db.relationship('AICommandResult', backref='command', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_ai_command_org', 'org_id'),
        Index('idx_ai_command_user', 'user_id'),
        Index('idx_ai_command_type', 'command_type'),
        Index('idx_ai_command_target', 'target_type'),
        Index('idx_ai_command_status', 'status'),
        Index('idx_ai_command_created', 'created_at'),
    )
    
    def to_dict(self):
        """تحويل الأمر إلى قاموس"""
        return {
            'id': self.id,
            'uuid': self.uuid,
            'command': self.command_text[:100] + ('...' if len(self.command_text) > 100 else ''),
            'command_full': self.command_text,
            'type': self.command_type,
            'target': self.target_type,
            'status': self.status,
            'progress': self.progress,
            'has_attachments': self.has_attachments,
            'attachments_count': self.attachments_count,
            'result_summary': self.result_summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time': self.processing_time,
            'user': self.user.full_name if self.user else None
        }


class AICommandAttachment(db.Model):
    """
    الملفات المرفقة مع أوامر الذكاء الاصطناعي
    """
    __tablename__ = 'ai_command_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'), nullable=False)
    
    # معلومات الملف
    filename = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)  # بالبايت
    file_type = db.Column(db.String(100))  # pdf, docx, xlsx, txt, jpg, etc.
    mime_type = db.Column(db.String(100))
    
    # مسار الملف
    file_path = db.Column(db.String(1000))
    file_url = db.Column(db.String(1000))
    
    # محتوى مستخرج
    extracted_text = db.Column(db.Text)  # النص المستخرج من الملف
    extracted_data = db.Column(db.JSON)  # البيانات المستخرجة (جداول، قوائم)
    page_count = db.Column(db.Integer)  # عدد الصفحات للمستندات
    word_count = db.Column(db.Integer)  # عدد الكلمات
    
    # حالة المعالجة
    processing_status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    error_message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_ai_attachment_command', 'command_id'),
        Index('idx_ai_attachment_type', 'file_type'),
    )


class AICommandResult(db.Model):
    """
    نتائج معالجة أوامر الذكاء الاصطناعي - البيانات المستخرجة
    """
    __tablename__ = 'ai_command_results'
    
    id = db.Column(db.Integer, primary_key=True)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'), nullable=False)
    
    # نوع النتيجة
    result_type = db.Column(db.String(50))  # project, task, user, resource, wbs, report, analysis
    action_type = db.Column(db.String(20))  # created, updated, deleted, read
    
    # البيانات
    data = db.Column(db.JSON)  # البيانات المستخرجة/المعدلة
    affected_ids = db.Column(db.JSON)  # IDs العناصر المتأثرة
    affected_count = db.Column(db.Integer, default=0)
    
    # للتقارير
    report_data = db.Column(db.JSON)  # بيانات التقرير
    chart_data = db.Column(db.JSON)  # بيانات للرسوم البيانية
    summary = db.Column(db.Text)  # ملخص النتيجة
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_ai_result_command', 'command_id'),
        Index('idx_ai_result_type', 'result_type'),
    )


# ============================================
# 📊 AI Report - تقارير ذكية
# ============================================

class AIReport(db.Model):
    """
    تقارير ذكية يتم إنشاؤها بناءً على أوامر المدير
    """
    __tablename__ = 'ai_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'))
    
    # معلومات التقرير
    report_name = db.Column(db.String(500), nullable=False)
    report_type = db.Column(db.String(50))  # executive, detailed, summary, analytical
    report_format = db.Column(db.String(20))  # table, chart, both
    
    # البيانات
    report_data = db.Column(db.JSON)  # البيانات الرئيسية
    report_summary = db.Column(db.Text)  # ملخص التقرير
    report_insights = db.Column(db.JSON)  # insights واستنتاجات
    
    # إحصائيات
    total_records = db.Column(db.Integer)
    date_range_start = db.Column(db.Date)
    date_range_end = db.Column(db.Date)
    
    # تنسيق العرض
    display_config = db.Column(db.JSON, default={
        'group_by': None,
        'sort_by': None,
        'chart_type': 'bar',
        'columns': []
    })
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    organization = db.relationship('Organization', backref='ai_reports')
    creator = db.relationship('User', foreign_keys=[created_by])
    command = db.relationship('AICommand', foreign_keys=[command_id])
    
    __table_args__ = (
        Index('idx_ai_report_org', 'org_id'),
        Index('idx_ai_report_type', 'report_type'),
        Index('idx_ai_report_created', 'created_at'),
    )


# ============================================
# 📝 AI Document Analysis - تحليل المستندات
# ============================================

class AIDocumentAnalysis(db.Model):
    """
    تحليل المستندات واستخراج البيانات منها
    """
    __tablename__ = 'ai_document_analyses'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # الملف
    filename = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50))
    file_size = db.Column(db.Integer)
    
    # نوع المستند
    document_type = db.Column(db.String(50))  # contract, boq, schedule, drawing, specification
    document_category = db.Column(db.String(50))  # tender, design, execution, handover
    
    # البيانات المستخرجة
    extracted_entities = db.Column(db.JSON)  # كيانات مستخرجة (أسماء، تواريخ، أرقام)
    extracted_tables = db.Column(db.JSON)  # جداول مستخرجة
    extracted_text = db.Column(db.Text)  # النص الكامل
    
    # تحليل محدد
    projects_detected = db.Column(db.JSON)  # مشاريع مكتشفة
    tasks_detected = db.Column(db.JSON)  # مهام مكتشفة
    resources_detected = db.Column(db.JSON)  # موارد مكتشفة
    risks_detected = db.Column(db.JSON)  # مخاطر مكتشفة
    
    # علاقات مع العناصر الموجودة
    matched_projects = db.Column(db.JSON)  # مشاريع مطابقة
    matched_tasks = db.Column(db.JSON)  # مهام مطابقة
    suggested_actions = db.Column(db.JSON)  # إجراءات مقترحة
    
    # حالة المعالجة
    status = db.Column(db.String(20), default='pending')
    confidence_score = db.Column(db.Float)  # 0-100
    processing_time = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    organization = db.relationship('Organization', backref='document_analyses')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_ai_doc_org', 'org_id'),
        Index('idx_ai_doc_type', 'document_type'),
        Index('idx_ai_doc_status', 'status'),
    )


# ============================================
# 🎯 AI Suggestion - اقتراحات ذكية
# ============================================

class AISuggestion(db.Model):
    """
    اقتراحات ذكية يتم توليدها تلقائياً
    """
    __tablename__ = 'ai_suggestions'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # نوع الاقتراح
    suggestion_type = db.Column(db.String(50))  # optimization, risk, resource, schedule, cost
    priority = db.Column(db.String(20))  # high, medium, low
    category = db.Column(db.String(50))  # timeline, budget, quality, resources
    
    # المحتوى
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    reasoning = db.Column(db.Text)  # لماذا هذا الاقتراح
    expected_impact = db.Column(db.Text)  # التأثير المتوقع
    
    # البيانات المرتبطة
    related_project_id = db.Column(db.Integer, db.ForeignKey('primavera_projects.id'))
    related_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    related_activity_id = db.Column(db.Integer, db.ForeignKey('activitiess.id'))
    
    # البيانات الكمية
    potential_savings = db.Column(db.Float)  # توفير متوقع
    potential_delay_reduction = db.Column(db.Integer)  # تقليل تأخير (أيام)
    confidence = db.Column(db.Float)  # نسبة الثقة 0-100
    
    # حالة الاقتراح
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected, implemented
    implemented_at = db.Column(db.DateTime)
    implemented_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    feedback = db.Column(db.Text)  # ملاحظات على الاقتراح
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # AI or user
    
    # العلاقات
    organization = db.relationship('Organization', backref='ai_suggestions')
    project = db.relationship('PrimaveraProject', foreign_keys=[related_project_id])
    task = db.relationship('Task', foreign_keys=[related_task_id])
    activity = db.relationship('Activitys', foreign_keys=[related_activity_id])
    implementer = db.relationship('User', foreign_keys=[implemented_by])
    creator_user = db.relationship('User', foreign_keys=[created_by])
    
    __table_args__ = (
        Index('idx_ai_suggestion_org', 'org_id'),
        Index('idx_ai_suggestion_type', 'suggestion_type'),
        Index('idx_ai_suggestion_priority', 'priority'),
        Index('idx_ai_suggestion_status', 'status'),
        Index('idx_ai_suggestion_project', 'related_project_id'),
    )


# ============================================
# 📈 AI Analytics - تحليلات متقدمة
# ============================================

class AIAnalytics(db.Model):
    """
    تحليلات متقدمة للبيانات
    """
    __tablename__ = 'ai_analytics'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # نوع التحليل
    analysis_type = db.Column(db.String(50))  # trend, forecast, correlation, anomaly
    data_source = db.Column(db.String(50))  # projects, tasks, resources, costs
    
    # المعلمات
    parameters = db.Column(db.JSON)  # معلمات التحليل
    time_range = db.Column(db.JSON)  # النطاق الزمني
    
    # النتائج
    results = db.Column(db.JSON)  # نتائج التحليل
    charts = db.Column(db.JSON)  # بيانات للرسوم البيانية
    insights = db.Column(db.JSON)  # استنتاجات
    
    # أداء
    accuracy = db.Column(db.Float)  # دقة التحليل
    processing_time = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    __table_args__ = (
        Index('idx_ai_analytics_org', 'org_id'),
        Index('idx_ai_analytics_type', 'analysis_type'),
        Index('idx_ai_analytics_created', 'created_at'),
    )


# ============================================
# 🤖 AI Processing Queue - طابور المعالجة
# ============================================

class AIProcessingQueue(db.Model):
    """
    طابور معالجة مهام الذكاء الاصطناعي
    """
    __tablename__ = 'ai_processing_queue'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    # نوع المهمة
    task_type = db.Column(db.String(50))  # command_processing, document_analysis, report_generation
    priority = db.Column(db.Integer, default=3)  # 1-5, 1 أعلى
    
    # البيانات
    data = db.Column(db.JSON)  # بيانات المهمة
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'))
    document_id = db.Column(db.Integer, db.ForeignKey('ai_document_analyses.id'))
    
    # الحالة
    status = db.Column(db.String(20), default='queued')  # queued, processing, completed, failed
    attempts = db.Column(db.Integer, default=0)
    max_attempts = db.Column(db.Integer, default=3)
    
    # وقت المعالجة
    queued_at = db.Column(db.DateTime, default=datetime.utcnow)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # النتيجة
    result = db.Column(db.JSON)
    error = db.Column(db.Text)
    
    __table_args__ = (
        Index('idx_ai_queue_status', 'status'),
        Index('idx_ai_queue_priority', 'priority'),
        Index('idx_ai_queue_type', 'task_type'),
    )
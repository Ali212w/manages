"""
ai_models.py - نماذج الذكاء الاصطناعي والتحليلات المتقدمة
"""
from . import db
from sqlalchemy import Index, UniqueConstraint, CheckConstraint,JSON, Text, Float, Integer, String, DateTime, Boolean, ForeignKey
from datetime import datetime, date
import uuid
import json
from app.models import User

# ============================================
# 🤖 AI Command - أوامر الذكاء الاصطناعي
# ============================================


# app/models/ai_models.py


class AICommand(db.Model):
    """أوامر الذكاء الاصطناعي"""
    __tablename__ = 'ai_commands'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # الأمر والبرومبت (يدعم العربية والإنجليزية)
    command_text = db.Column(db.Text, nullable=False)
    command_language = db.Column(db.String(10), default='ar')  # ar, en, mixed
    command_type = db.Column(db.String(50))  # extract, analyze, report, search, create, update
    target_type = db.Column(db.String(50))  # project, task, resource, wbs, eps, obs, general
    
    # حالة المعالجة
    status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed
    progress = db.Column(db.Integer, default=0)  # 0-100
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    # نتيجة المعالجة
    result_summary = db.Column(db.Text)
    result_data = db.Column(JSON)  # البيانات المستخرجة
    confidence_score = db.Column(db.Float)  # 0-100
    processing_time = db.Column(db.Float)  # بالثواني
    processing_notes = db.Column(Text)  # ملاحظات المعالجة
    
    # السجل
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات - تم إصلاحها
    organization = db.relationship('Organization', backref='ai_commands')
    user = db.relationship('User', backref='ai_commands')
    attachments = db.relationship('AICommandAttachment', backref='command', lazy='dynamic', cascade='all, delete-orphan')
    extractions = db.relationship('AIExtraction', back_populates='ai_command', lazy='dynamic', cascade='all, delete-orphan')
    reports = db.relationship('AIReport', backref='command', lazy='dynamic')
    results = db.relationship('AICommandResult', backref='command', lazy='dynamic', cascade='all, delete-orphan')
    analysis_results = db.relationship('AIAnalysisResult', backref='command', lazy='dynamic', cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_ai_command_org', 'org_id'),
        Index('idx_ai_command_user', 'user_id'),
        Index('idx_ai_command_type', 'command_type'),
        Index('idx_ai_command_status', 'status'),
        Index('idx_ai_command_created', 'created_at'),
    )
    
    def to_dict(self):
        return {
            'id': self.id,
            'uuid': self.uuid,
            'command': self.command_text[:100] + ('...' if len(self.command_text) > 100 else ''),
            'language': self.command_language,
            'type': self.command_type,
            'target': self.target_type,
            'status': self.status,
            'progress': self.progress,
            'result_summary': self.result_summary,
            'confidence': self.confidence_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user': self.user.full_name if self.user else None
        }


class AICommandAttachment(db.Model):
    """الملفات المرفقة مع أوامر الذكاء الاصطناعي"""
    __tablename__ = 'ai_command_attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'), nullable=False)
    
    # معلومات الملف
    filename = db.Column(db.String(500), nullable=False)
    original_filename = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.Integer)  # بالبايت
    file_type = db.Column(db.String(100))  # pdf, docx, xlsx, txt, jpg, png, etc.
    mime_type = db.Column(db.String(100))
    
    # مسار الملف
    file_path = db.Column(db.String(1000))
    file_url = db.Column(db.String(1000))
    
    # محتوى مستخرج
    extracted_text = db.Column(db.Text)  # النص المستخرج من الملف
    extracted_text_en = db.Column(db.Text)  # النص بالإنجليزية (للترجمة)
    extracted_text_ar = db.Column(db.Text)  # النص بالعربية
    extracted_data = db.Column(JSON)  # البيانات المستخرجة (جداول، قوائم)
    page_count = db.Column(db.Integer)  # عدد الصفحات للمستندات
    word_count = db.Column(db.Integer)  # عدد الكلمات
    language = db.Column(db.String(10))  # اللغة المكتشفة
    
    # حالة المعالجة
    processing_status = db.Column(db.String(20), default='pending')
    error_message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_ai_attachment_command', 'command_id'),
    )


class AIExtraction(db.Model):
    """البيانات المستخرجة وربطها بالجداول"""
    __tablename__ = 'ai_extractions'
    
    id = db.Column(db.Integer, primary_key=True)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'), nullable=False)
    
    # نوع البيانات المستخرجة
    extraction_type = db.Column(db.String(50))  # project, task, resource, wbs, eps, obs, user
    confidence = db.Column(db.Float)  # 0-100
    
    # البيانات المستخرجة (JSON)
    extracted_data = db.Column(JSON)
    suggested_mappings = db.Column(JSON)  # اقتراحات الربط مع الجداول
    
    # الروابط مع الجداول (بعد الموافقة)
    linked_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    linked_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    linked_resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=True)
    linked_wbs_id = db.Column(db.Integer, db.ForeignKey('wbs.id'), nullable=True)
    linked_eps_id = db.Column(db.Integer, db.ForeignKey('eps.id'), nullable=True)
    linked_obs_id = db.Column(db.Integer, db.ForeignKey('obs.id'), nullable=True)
    linked_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # حالة الربط
    is_approved = db.Column(db.Boolean, default=False)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_at = db.Column(db.DateTime)
    
    # تعديلات المستخدم
    user_modifications = db.Column(JSON)  # التعديلات التي أجراها المستخدم
    rejection_reason = db.Column(Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات - تم إصلاحها
    ai_command = db.relationship('AICommand', back_populates='extractions')
    project = db.relationship('Project', foreign_keys=[linked_project_id])
    task = db.relationship('Task', foreign_keys=[linked_task_id])
    resource = db.relationship('Resource', foreign_keys=[linked_resource_id])
    wbs = db.relationship('WBS', foreign_keys=[linked_wbs_id])
    eps = db.relationship('EPS', foreign_keys=[linked_eps_id])
    obs = db.relationship('OBS', foreign_keys=[linked_obs_id])
    user = db.relationship('User', foreign_keys=[linked_user_id])
    approver = db.relationship('User', foreign_keys=[approved_by])
    
    __table_args__ = (
        Index('idx_ai_extraction_command', 'command_id'),
        Index('idx_ai_extraction_type', 'extraction_type'),
    )


class AIReport(db.Model):
    """التقارير الذكية"""
    __tablename__ = 'ai_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'), nullable=True)
    
    # معلومات التقرير
    report_name = db.Column(db.String(500), nullable=False)
    report_name_ar = db.Column(db.String(500))
    report_name_en = db.Column(db.String(500))
    report_type = db.Column(db.String(50))  # executive, detailed, summary, analytical, custom
    report_format = db.Column(db.String(20))  # table, chart, both, text
    
    # البيانات
    report_data = db.Column(JSON)  # البيانات الرئيسية
    report_summary = db.Column(Text)  # ملخص التقرير
    report_summary_ar = db.Column(Text)
    report_summary_en = db.Column(Text)
    report_insights = db.Column(JSON)  # insights واستنتاجات
    recommendations = db.Column(JSON)  # توصيات
    
    # إحصائيات
    total_records = db.Column(db.Integer)
    date_range_start = db.Column(db.Date)
    date_range_end = db.Column(db.Date)
    
    # معلمات التقرير
    parameters = db.Column(JSON)  # معلمات التقرير
    filters = db.Column(JSON)  # الفلاتر المستخدمة
    sort_by = db.Column(db.String(100))
    group_by = db.Column(db.String(100))
    
    # بيانات للرسوم البيانية
    chart_data = db.Column(JSON)  # بيانات Chart.js/Plotly
    chart_type = db.Column(db.String(50))  # bar, line, pie, donut, etc.
    
    # تصدير
    export_formats = db.Column(JSON, default=['pdf', 'excel', 'csv'])  # الصيغ المدعومة
    last_exported_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    organization = db.relationship('Organization', backref='ai_reports')
    creator = db.relationship('User', foreign_keys=[created_by])
    # command = db.relationship('AICommand', foreign_keys=[command_id])
    
    __table_args__ = (
        Index('idx_ai_report_org', 'org_id'),
        Index('idx_ai_report_type', 'report_type'),
        Index('idx_ai_report_created', 'created_at'),
    )


class AICommandResult(db.Model):
    """نتائج أوامر الذكاء الاصطناعي"""
    __tablename__ = 'ai_command_results'
    
    id = db.Column(db.Integer, primary_key=True)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'), nullable=False)
    
    result_type = db.Column(db.String(50))  # text, json, chart, etc.
    result_data = db.Column(db.JSON)
    confidence = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    # command = db.relationship('AICommand', backref='command_results')


class AIAnalysisResult(db.Model):
    """نتائج التحليل المتقدم"""
    __tablename__ = 'ai_analysis_results'
    
    id = db.Column(db.Integer, primary_key=True)
    command_id = db.Column(db.Integer, db.ForeignKey('ai_commands.id'), nullable=False)
    
    analysis_type = db.Column(db.String(50))  # risk, performance, resource, etc.
    findings = db.Column(db.JSON)
    recommendations = db.Column(db.JSON)
    confidence = db.Column(db.Float)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    # command = db.relationship('AICommand', backref='analysis_results')


class AISuggestion(db.Model):
    """الاقتراحات الذكية"""
    __tablename__ = 'ai_suggestions'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False)
    
    # نوع الاقتراح
    suggestion_type = db.Column(db.String(50))  # optimization, risk, resource, schedule, cost, quality
    priority = db.Column(db.String(20), default='medium')  # critical, high, medium, low
    
    # المحتوى
    title = db.Column(db.String(500), nullable=False)
    title_ar = db.Column(db.String(500))
    title_en = db.Column(db.String(500))
    description = db.Column(db.Text)
    description_ar = db.Column(db.Text)
    description_en = db.Column(db.Text)
    
    # العناصر المرتبطة
    related_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    related_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    related_activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=True)
    related_resource_id = db.Column(db.Integer, db.ForeignKey('resources.id'), nullable=True)
    
    # البيانات الكمية
    potential_impact = db.Column(db.Float)  # تأثير متوقع (ساعات/ريال)
    confidence_score = db.Column(db.Float)  # 0-100
    
    # حالة الاقتراح
    status = db.Column(db.String(20), default='active')  # active, accepted, rejected, implemented
    implemented_at = db.Column(db.DateTime)
    implemented_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    organization = db.relationship('Organization', backref='ai_suggestions')
    project = db.relationship('Project', foreign_keys=[related_project_id])
    task = db.relationship('Task', foreign_keys=[related_task_id])
    activity = db.relationship('Activity', foreign_keys=[related_activity_id])
    resource = db.relationship('Resource', foreign_keys=[related_resource_id])
    implementer = db.relationship('User', foreign_keys=[implemented_by])
    
    __table_args__ = (
        Index('idx_ai_suggestion_org', 'org_id'),
        Index('idx_ai_suggestion_type', 'suggestion_type'),
        Index('idx_ai_suggestion_priority', 'priority'),
    )

class Risk(db.Model):
    """مخاطر المشروع"""
    __tablename__ = 'risks'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    risk_code = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text)
    
    category = db.Column(db.String(100))  # technical, financial, schedule, legal, etc.
    # risk_type = db.Column(db.String(100))  # threat, opportunity
    
    # التقييم
    probability = db.Column(db.Float, default=0.5)  # 0-1
    impact = db.Column(db.Float, default=0.5)  # 0-1
    severity = db.Column(db.Float, default=0.25)  # probability * impact
    risk_level = db.Column(db.String(20))  # low, medium, high, critical
    
    # المالك والمسؤول
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    # assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'))
    
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
    owner = db.relationship('User', foreign_keys=[owner_id])
    # assignee = db.relationship('User', foreign_keys=[assigned_to])
    creator = db.relationship('User', foreign_keys=[created_by])
    
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
    risk = db.relationship('Risk', backref='updates')
    updater = db.relationship('User', foreign_keys=[updated_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_risk_update_risk', 'risk_id'),
        Index('idx_risk_update_date', 'updated_at'),
        Index('idx_risk_update_status', 'new_status'),
        CheckConstraint("progress_percentage >= 0 AND progress_percentage <= 100", 
                       name='chk_risk_progress'),
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
    conductor = db.relationship('User', foreign_keys=[conducted_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_safety_project', 'project_id'),
        Index('idx_safety_code', 'inspection_code'),
        Index('idx_safety_date', 'inspection_date'),
        Index('idx_safety_type', 'inspection_type'),
        Index('idx_safety_conductor', 'conducted_by'),
        UniqueConstraint('project_id', 'inspection_code', name='uq_safety_code_project'),
    )


class Notification(db.Model):
    """الإشعارات"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    organ_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True)
    
    title = db.Column(db.String(200), nullable=False)
    title_ar = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    message_ar = db.Column(db.Text)
    
    notification_type = db.Column(db.String(50), nullable=False)  # task_started, task_completed, risk_alert, etc.
    priority = db.Column(db.String(20), default='medium')  # low, medium, high, critical
    related_link = db.Column(db.String(500))
    
    # المراجع
    related_project_id = db.Column(db.Integer, db.ForeignKey('projects.id'))
    related_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'))
    related_risk_id = db.Column(db.Integer, db.ForeignKey('risks.id'))
    related_issue_id = db.Column(db.Integer, db.ForeignKey('issues.id'))
    related_delivery_id = db.Column(db.Integer, db.ForeignKey('resource_deliveries.id'))
    related_request_id = db.Column(db.Integer, db.ForeignKey('resource_requests.id'))

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
    project = db.relationship('Project')
    task = db.relationship('Task')
    risk = db.relationship('Risk')
    issue = db.relationship('Issue')
    delivery = db.relationship('ResourceDelivery')
    request = db.relationship('ResourceRequest')
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

    def get_primary_link(self):
        """الحصول على الرابط الرئيسي للإشعار"""
        from flask import url_for
        
        # 1. استخدام related_link المباشر
        if self.related_link:
            return self.related_link
        
        # 2. رابط التسليم
        if self.related_delivery_id:
            return url_for('company.confirm_delivery', delivery_id=self.related_delivery_id, _external=True)
        
        # 3. رابط طلب التوريد
        if self.related_request_id:
            return url_for('supplier.view_request', request_id=self.related_request_id, _external=True)
        
        # 4. رابط المهمة
        if self.related_task_id:
            return url_for('company.view_task', task_id=self.related_task_id, _external=True)
        
        # 5. رابط المشروع
        if self.related_project_id:
            return url_for('company.view_project', project_id=self.related_project_id, _external=True)
        
        # 6. رابط المورد
        # if self.related_resource_id:
        #     return url_for('company.view_resource', resource_id=self.related_resource_id, _external=True)
        
        # 7. رابط الخطر
        if self.related_risk_id:
            return url_for('company.view_risk', risk_id=self.related_risk_id, _external=True)
        
        # 8. رابط المشكلة
        if self.related_issue_id:
            return url_for('company.view_issue', issue_id=self.related_issue_id, _external=True)
        
        # 9. رابط المستند
        # if self.related_document_id:
        #     return url_for('company.view_document', document_id=self.related_document_id, _external=True)
        
        # 10. رابط المستخدم
        # if self.related_user_id:
        #     return url_for('company.view_user', user_id=self.related_user_id, _external=True)
        
        # # 11. رابط EPS
        # if self.related_eps_id:
        #     return url_for('company.view_eps', eps_id=self.related_eps_id, _external=True)
        
        # # 12. رابط طلب التحقق
        # if self.verification_request_id:
        #     return url_for('tracking.verify_requirement', request_id=self.verification_request_id, _external=True)
        
        # 13. رابط صفحة الإشعارات العامة
        return url_for('notifications.index', _external=True)
    
    def get_links(self):
        """الحصول على قائمة الروابط المتاحة للإشعار"""
        from flask import url_for
        
        links = []
        
        # 1. رابط التفاصيل المباشر
        if self.related_link:
            links.append({
                'url': self.related_link,
                'text': 'عرض التفاصيل',
                'icon': 'fa-external-link-alt'
            })
        
        # 2. رابط المشروع
        if self.related_project_id:
            links.append({
                'url': url_for('company.view_project', project_id=self.related_project_id, _external=True),
                'text': 'عرض المشروع',
                'icon': 'fa-project-diagram'
            })
        
        # 3. رابط المهمة
        if self.related_task_id:
            links.append({
                'url': url_for('company.view_task', task_id=self.related_task_id, _external=True),
                'text': 'عرض المهمة',
                'icon': 'fa-tasks'
            })
        
        # 4. رابط التسليم
        if self.related_delivery_id:
            links.append({
                'url': url_for('company.confirm_delivery', delivery_id=self.related_delivery_id, _external=True),
                'text': 'مراجعة التسليم',
                'icon': 'fa-truck'
            })
        
        # 5. رابط طلب التوريد
        if self.related_request_id:
            links.append({
                'url': url_for('supplier.view_request', request_id=self.related_request_id, _external=True),
                'text': 'عرض طلب التوريد',
                'icon': 'fa-file-invoice'
            })
        
        # 6. رابط المورد
        # if self.related_resource_id:
        #     links.append({
        #         'url': url_for('company.view_resource', resource_id=self.related_resource_id, _external=True),
        #         'text': 'عرض المورد',
        #         'icon': 'fa-cube'
        #     })
        
        # 7. رابط الخطر
        if self.related_risk_id:
            links.append({
                'url': url_for('company.view_risk', risk_id=self.related_risk_id, _external=True),
                'text': 'عرض الخطر',
                'icon': 'fa-shield-alt'
            })
        
        # 8. رابط المشكلة
        if self.related_issue_id:
            links.append({
                'url': url_for('company.view_issue', issue_id=self.related_issue_id, _external=True),
                'text': 'عرض المشكلة',
                'icon': 'fa-bug'
            })
        
        # 9. رابط المستند
        # if self.related_document_id:
        #     links.append({
        #         'url': url_for('company.view_document', document_id=self.related_document_id, _external=True),
        #         'text': 'عرض المستند',
        #         'icon': 'fa-file-alt'
        #     })
        
        # # 10. رابط المستخدم
        # if self.related_user_id:
        #     links.append({
        #         'url': url_for('company.view_user', user_id=self.related_user_id, _external=True),
        #         'text': 'عرض المستخدم',
        #         'icon': 'fa-user'
        #     })
        
        # # 11. رابط طلب التحقق
        # if self.verification_request_id:
        #     links.append({
        #         'url': url_for('tracking.verify_requirement', request_id=self.verification_request_id, _external=True),
        #         'text': 'مراجعة طلب التحقق',
        #         'icon': 'fa-clipboard-check'
        #     })
        
        return links
    
    def get_icon_class(self):
        """الحصول على كلاس الأيقونة حسب نوع الإشعار"""
        notification_type = self.notification_type
        
        if 'delivery' in notification_type:
            return 'delivery'
        elif 'task' in notification_type:
            return 'task'
        elif 'project' in notification_type:
            return 'project'
        elif 'risk' in notification_type:
            return 'risk'
        elif 'issue' in notification_type:
            return 'issue'
        elif 'verification' in notification_type:
            return 'verification'
        elif 'user' in notification_type:
            return 'user'
        elif 'document' in notification_type:
            return 'document'
        elif 'resource' in notification_type:
            return 'resource'
        elif 'message' in notification_type or 'comment' in notification_type:
            return 'message'
        elif 'mention' in notification_type:
            return 'mention'
        elif 'eps' in notification_type:
            return 'eps'
        elif 'performance' in notification_type:
            return 'performance'
        elif 'system' in notification_type:
            return 'system'
        else:
            return 'default'
    
    def get_icon_html(self):
        """الحصول على أيقونة HTML حسب نوع الإشعار"""
        notification_type = self.notification_type
        
        # إشعارات التسليمات
        if 'delivery' in notification_type:
            if 'pending' in notification_type:
                return '<i class="fas fa-clock"></i>'
            elif 'confirmed' in notification_type:
                return '<i class="fas fa-check-double"></i>'
            elif 'rejected' in notification_type:
                return '<i class="fas fa-times-circle"></i>'
            elif 'submitted' in notification_type:
                return '<i class="fas fa-truck"></i>'
            elif 'notes' in notification_type:
                return '<i class="fas fa-sticky-note"></i>'
            elif 'alert' in notification_type:
                return '<i class="fas fa-bell"></i>'
            return '<i class="fas fa-truck"></i>'
        
        # إشعارات المهام
        if 'task' in notification_type:
            if 'assigned' in notification_type:
                return '<i class="fas fa-user-plus"></i>'
            elif 'started' in notification_type:
                return '<i class="fas fa-play-circle"></i>'
            elif 'completed' in notification_type:
                return '<i class="fas fa-check-circle"></i>'
            elif 'overdue' in notification_type:
                return '<i class="fas fa-exclamation-triangle"></i>'
            elif 'reminder' in notification_type:
                return '<i class="fas fa-bell"></i>'
            return '<i class="fas fa-tasks"></i>'
        
        # إشعارات المشاريع
        if 'project' in notification_type:
            if 'created' in notification_type:
                return '<i class="fas fa-plus-circle"></i>'
            elif 'assigned' in notification_type:
                return '<i class="fas fa-user-check"></i>'
            elif 'started' in notification_type:
                return '<i class="fas fa-play"></i>'
            elif 'completed' in notification_type:
                return '<i class="fas fa-trophy"></i>'
            elif 'progress' in notification_type:
                return '<i class="fas fa-chart-line"></i>'
            elif 'updated' in notification_type:
                return '<i class="fas fa-edit"></i>'
            return '<i class="fas fa-project-diagram"></i>'
        
        # إشعارات المخاطر
        if 'risk' in notification_type:
            if 'detected' in notification_type:
                return '<i class="fas fa-shield-alt"></i>'
            elif 'mitigated' in notification_type:
                return '<i class="fas fa-check-shield"></i>'
            elif 'alert' in notification_type:
                return '<i class="fas fa-exclamation-circle"></i>'
            return '<i class="fas fa-shield-alt"></i>'
        
        # إشعارات المشكلات
        if 'issue' in notification_type:
            if 'reported' in notification_type:
                return '<i class="fas fa-bug"></i>'
            elif 'assigned' in notification_type:
                return '<i class="fas fa-user-tag"></i>'
            elif 'resolved' in notification_type:
                return '<i class="fas fa-check-circle"></i>'
            return '<i class="fas fa-bug"></i>'
        
        # إشعارات التحقق
        if 'verification' in notification_type:
            if 'submitted' in notification_type:
                return '<i class="fas fa-clipboard-list"></i>'
            elif 'result' in notification_type:
                return '<i class="fas fa-clipboard-check"></i>'
            return '<i class="fas fa-clipboard-check"></i>'
        
        # إشعارات المستخدمين
        if 'user' in notification_type:
            if 'registered' in notification_type:
                return '<i class="fas fa-user-plus"></i>'
            elif 'welcome' in notification_type:
                return '<i class="fas fa-smile-wink"></i>'
            elif 'approved' in notification_type:
                return '<i class="fas fa-user-check"></i>'
            elif 'role_changed' in notification_type:
                return '<i class="fas fa-user-cog"></i>'
            return '<i class="fas fa-user"></i>'
        
        # إشعارات المستندات
        if 'document' in notification_type:
            if 'uploaded' in notification_type:
                return '<i class="fas fa-file-upload"></i>'
            elif 'approved' in notification_type:
                return '<i class="fas fa-file-signature"></i>'
            return '<i class="fas fa-file-alt"></i>'
        
        # إشعارات الموارد
        if 'resource' in notification_type:
            if 'low_stock' in notification_type:
                return '<i class="fas fa-box-open"></i>'
            elif 'request_created' in notification_type:
                return '<i class="fas fa-file-invoice"></i>'
            elif 'request_sent' in notification_type:
                return '<i class="fas fa-paper-plane"></i>'
            return '<i class="fas fa-cube"></i>'
        
        # إشعارات الرسائل والتعليقات
        if 'message' in notification_type:
            return '<i class="fas fa-comment-dots"></i>'
        if 'comment' in notification_type:
            return '<i class="fas fa-comment"></i>'
        if 'mention' in notification_type:
            return '<i class="fas fa-at"></i>'
        
        # إشعارات النظام
        if 'system' in notification_type:
            return '<i class="fas fa-server"></i>'
        
        # إشعارات الأداء
        if 'performance' in notification_type:
            return '<i class="fas fa-chart-bar"></i>'
        if 'daily_summary' in notification_type:
            return '<i class="fas fa-calendar-day"></i>'
        
        # إشعارات EPS
        if 'eps' in notification_type:
            return '<i class="fas fa-sitemap"></i>'
        
        # إشعارات المواد المتبقية
        if 'remaining_items_reminder' in notification_type:
            return '<i class="fas fa-boxes"></i>'
        
        # أيقونة افتراضية
        return '<i class="fas fa-bell"></i>'
    
    def get_status_badge(self):
        """الحصول على شارة الحالة حسب نوع الإشعار"""
        notification_type = self.notification_type
        
        if notification_type == 'delivery_pending':
            return '<span class="badge bg-warning ms-2"><i class="fas fa-clock"></i> في انتظار التأكيد</span>'
        elif notification_type == 'delivery_confirmed':
            return '<span class="badge bg-success ms-2"><i class="fas fa-check-circle"></i> تم التأكيد</span>'
        elif notification_type == 'delivery_rejected':
            return '<span class="badge bg-danger ms-2"><i class="fas fa-times-circle"></i> مرفوض</span>'
        elif notification_type == 'task_overdue':
            return '<span class="badge bg-danger ms-2"><i class="fas fa-hourglass-end"></i> متأخر</span>'
        elif notification_type == 'task_completed':
            return '<span class="badge bg-success ms-2"><i class="fas fa-check"></i> مكتمل</span>'
        elif notification_type == 'risk_detected':
            return '<span class="badge bg-danger ms-2"><i class="fas fa-exclamation-triangle"></i> خطر جديد</span>'
        elif notification_type == 'risk_mitigated':
            return '<span class="badge bg-success ms-2"><i class="fas fa-check-shield"></i> تم التخفيف</span>'
        elif notification_type == 'issue_reported':
            return '<span class="badge bg-warning ms-2"><i class="fas fa-bug"></i> مشكلة جديدة</span>'
        elif notification_type == 'issue_resolved':
            return '<span class="badge bg-success ms-2"><i class="fas fa-check"></i> تم الحل</span>'
        elif notification_type == 'resource_low_stock':
            return '<span class="badge bg-danger ms-2"><i class="fas fa-box-open"></i> مخزون منخفض</span>'
        elif notification_type == 'verification_submitted':
            return '<span class="badge bg-info ms-2"><i class="fas fa-clipboard-list"></i> في انتظار المراجعة</span>'
        elif 'verification_result' in notification_type:
            if 'تمت الموافقة' in self.message:
                return '<span class="badge bg-success ms-2"><i class="fas fa-check-circle"></i> تمت الموافقة</span>'
            else:
                return '<span class="badge bg-danger ms-2"><i class="fas fa-times-circle"></i> مرفوض</span>'
        
        return ''
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
    user = db.relationship('User', foreign_keys=[user_id])
    
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
    
    meta_data = db.Column(db.JSON)
    
    # العلاقات
    project = db.relationship('Project')
    user = db.relationship('User', foreign_keys=[user_id])
    
    # فهرسة
    __table_args__ = (
        Index('idx_metric_type', 'metric_type'),
        Index('idx_metric_name', 'metric_name'),
        Index('idx_metric_timestamp', 'timestamp'),
        Index('idx_metric_project', 'project_id'),
        Index('idx_metric_user', 'user_id'),
    )


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
    verifier = db.relationship('User', foreign_keys=[verified_by])
    
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
    requester = db.relationship('User', foreign_keys=[requested_by])
    assignee = db.relationship('User', foreign_keys=[assigned_to])
    
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
    organizer = db.relationship('User', foreign_keys=[organizer_id])
    secretary = db.relationship('User', foreign_keys=[secretary_id])
    
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
    project = db.relationship('Project')
    
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
    assignee = db.relationship('User', foreign_keys=[assigned_to])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])
    implementer = db.relationship('User', foreign_keys=[implemented_by])
    
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
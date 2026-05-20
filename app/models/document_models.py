"""
document_models.py - نماذج المستندات والتحليل
"""
from . import db
from sqlalchemy import Index, UniqueConstraint
from datetime import datetime
import uuid

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
    parent = db.relationship('BillItem', remote_side=[id], backref='sub_items')
    activities = db.relationship('Activity', secondary='bill_item_activities', 
                                 backref='bill_items')
    materials = db.relationship('MaterialItem', backref='bill_item', lazy=True)
    
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


class ProjectDocument(db.Model):
    """مستندات المشروع"""
    __tablename__ = 'project_documents'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    
    title = db.Column(db.String(500))
    description = db.Column(db.Text)
    category = db.Column(db.String(100))  # engineering, financial, legal, etc.
    
    from sqlalchemy.orm import synonym
    file_type = db.Column(db.String(100), nullable=False)  # contract, drawing, specification, report
    document_type = synonym('file_type')
    file_extension = db.Column(db.String(20))
    file_size = db.Column(db.Integer)  # بالبايت

    file_path = db.Column(db.String(1000))
    file_url = db.Column(db.String(500))
    
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
    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    approver = db.relationship('User', foreign_keys=[approved_by])
    bill_items = db.relationship('BillItem', secondary='document_bill_items', 
                                 backref='documents')
    
    # فهرسة
    __table_args__ = (
        Index('idx_document_project', 'project_id'),
        Index('idx_document_type', 'file_type'),
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
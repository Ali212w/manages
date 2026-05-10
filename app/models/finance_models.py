"""
finance_models.py - نماذج الجداول المالية
"""
from ..extensions import db
from sqlalchemy import Index, UniqueConstraint, CheckConstraint
from datetime import datetime, date
import uuid

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
    supplier = db.relationship('Supplier', backref='materials')
    # deliveries = db.relationship('MaterialDelivery', backref='material', lazy=True)
    # usages = db.relationship('MaterialUsage', backref='material', lazy=True)
    
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
    material = db.relationship('MaterialItem', backref='transactions')
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_transaction_material', 'material_id'),
        Index('idx_transaction_type', 'transaction_type'),
        Index('idx_transaction_date', 'created_at'),
        Index('idx_transaction_reference', 'reference_type', 'reference_id'),
    )




class Invoice(db.Model):
    """الفواتير"""
    __tablename__ = 'invoices'
    
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    
    invoice_number = db.Column(db.String(50), nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date)
    
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'))
    client_name = db.Column(db.String(200))
    
    subtotal = db.Column(db.Float, default=0.0)
    tax_amount = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    balance_due = db.Column(db.Float, default=0.0)
    
    status = db.Column(db.String(50), default='draft')  # draft, sent, partial, paid, overdue, cancelled
    
    sent_date = db.Column(db.Date)
    paid_date = db.Column(db.Date)
    
    notes = db.Column(db.Text)
    terms = db.Column(db.Text)
    
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    client = db.relationship('Client')
    creator = db.relationship('User', foreign_keys=[created_by])
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='invoice', lazy=True)
    
    # فهرسة
    __table_args__ = (
        Index('idx_invoice_project', 'project_id'),
        Index('idx_invoice_number', 'invoice_number'),
        Index('idx_invoice_status', 'status'),
        Index('idx_invoice_date', 'invoice_date'),
        Index('idx_invoice_client', 'client_id'),
        UniqueConstraint('project_id', 'invoice_number', name='uq_invoice_number_project'),
    )


class InvoiceItem(db.Model):
    """بنود الفاتورة"""
    __tablename__ = 'invoice_items'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    bill_item_id = db.Column(db.Integer, db.ForeignKey('bill_items.id'))
    
    description = db.Column(db.Text, nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    
    # فهرسة
    __table_args__ = (
        Index('idx_invoice_item_invoice', 'invoice_id'),
        Index('idx_invoice_item_bill', 'bill_item_id'),
    )


class Payment(db.Model):
    """المدفوعات"""
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    
    payment_number = db.Column(db.String(50), nullable=False)
    payment_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    
    payment_method = db.Column(db.String(50))  # cash, bank_transfer, cheque, credit_card
    reference_number = db.Column(db.String(100))
    
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(100))
    
    status = db.Column(db.String(50), default='pending')  # pending, confirmed, rejected
    
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    confirmed_at = db.Column(db.DateTime)
    
    notes = db.Column(db.Text)
    
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    confirmator = db.relationship('User', foreign_keys=[confirmed_by])
    creator = db.relationship('User', foreign_keys=[created_by])
    
    # فهرسة
    __table_args__ = (
        Index('idx_payment_invoice', 'invoice_id'),
        Index('idx_payment_number', 'payment_number'),
        Index('idx_payment_date', 'payment_date'),
        Index('idx_payment_status', 'status'),
        Index('idx_payment_method', 'payment_method'),
        UniqueConstraint('invoice_id', 'payment_number', name='uq_payment_number_invoice'),
    )
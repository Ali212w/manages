# forms.py
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, TextAreaField, FloatField, IntegerField, SelectField, DateField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, Optional
from app.models import User,Organization
from datetime import datetime

class LoginForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    password = PasswordField('كلمة المرور', validators=[DataRequired()])
    remember = BooleanField('تذكرني')

class RegistrationForm(FlaskForm):
    org_code = StringField('رقم المعرف', validators=[DataRequired(), Length(min=3, max=80)])
    email = StringField('البريد الإلكتروني', validators=[DataRequired(), Email()])
    full_name = StringField('اسم الشركة او المؤسسة', validators=[DataRequired(), Length(min=3, max=100)])
    phone = StringField('رقم الهاتف', validators=[Optional(), Length(max=20)])
    password = PasswordField('كلمة المرور', validators=[
        DataRequired(),
        Length(min=6, message='كلمة المرور يجب أن تكون على الأقل 6 أحرف')
    ])
    confirm_password = PasswordField('تأكيد كلمة المرور', validators=[
        DataRequired(),
        EqualTo('password', message='كلمات المرور غير متطابقة')
    ])

    
    def validate_username(self, name):
        organ = Organization.query.filter_by(name=name.data).first()
        if organ:
            raise ValidationError('الاسم موجود بالفعل')
        
    def validate_orgcod(self, org_code):
        organ = Organization.query.filter_by(org_code=org_code.data).first()
        if organ:
            raise ValidationError('رقم المعرف موجود بالفعل')
        
    def validate_email(self, email):
        organ = Organization.query.filter_by(email=email.data).first()
        if organ:
            raise ValidationError('البريد الإلكتروني موجود بالفعل')

class ProjectForm(FlaskForm):
    title = StringField('عنوان المشروع', validators=[DataRequired(), Length(max=200)])
    description = TextAreaField('وصف المشروع', validators=[Optional()])
    location = StringField('الموقع', validators=[Optional(), Length(max=200)])
    region = StringField('المنطقة', validators=[Optional(), Length(max=100)])
    client_name = StringField('اسم العميل', validators=[Optional(), Length(max=100)])
    client_phone = StringField('رقم هاتف العميل', validators=[Optional(), Length(max=20)])
    estimated_budget = FloatField('الميزانية التقديرية', validators=[Optional()])
    start_date = DateField('تاريخ البدء', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('تاريخ الانتهاء المتوقع', format='%Y-%m-%d', validators=[Optional()])
    priority = SelectField('الأولوية', choices=[
        ('low', 'منخفضة'),
        ('medium', 'متوسطة'),
        ('high', 'عالية'),
        ('critical', 'حرجة')
    ], default='medium')
    
    # ملف المشروع
    project_file = FileField('ملف المشروع', validators=[
        Optional(),
        FileAllowed(['xlsx', 'xls', 'docx', 'pdf', 'csv', 'txt'], 'الملفات المسموحة: Excel, Word, PDF, CSV, TXT')
    ])

class TaskForm(FlaskForm):
    code = StringField('رقم البند', validators=[DataRequired(), Length(max=50)])
    title = StringField('مواصفات العمل', validators=[DataRequired(), Length(max=500)])
    description = TextAreaField('وصف المهمة', validators=[Optional()])
    unit = StringField('الوحدة', validators=[Optional(), Length(max=20)])
    quantity = FloatField('الكمية', validators=[Optional()], default=0)
    unit_price = FloatField('سعر الوحدة', validators=[Optional()], default=0)
    
    planned_start = DateField('تاريخ البدء المخطط', format='%Y-%m-%d', validators=[Optional()])
    planned_end = DateField('تاريخ الانتهاء المخطط', format='%Y-%m-%d', validators=[Optional()])
    estimated_duration = IntegerField('المدة التقديرية (بالدقائق)', validators=[Optional()])
    
    assigned_to_id = SelectField('مسند إلى', coerce=int, validators=[Optional()])
    
    notes = TextAreaField('ملاحظات', validators=[Optional()])

class AssignTaskForm(FlaskForm):
    user_id = SelectField('المستخدم', coerce=int, validators=[DataRequired()])
    role_in_task = SelectField('الدور في المهمة', choices=[
        ('supervisor', 'مشرف'),
        ('delegate', 'مندوب'),
        ('worker', 'فرد')
    ], validators=[DataRequired()])
    notes = TextAreaField('ملاحظات', validators=[Optional()])

class ProfileForm(FlaskForm):
    full_name = StringField('الاسم الكامل', validators=[DataRequired(), Length(max=100)])
    phone = StringField('رقم الهاتف', validators=[Optional(), Length(max=20)])
    current_password = PasswordField('كلمة المرور الحالية', validators=[Optional()])
    new_password = PasswordField('كلمة المرور الجديدة', validators=[
        Optional(),
        Length(min=6, message='كلمة المرور يجب أن تكون على الأقل 6 أحرف')
    ])
    confirm_new_password = PasswordField('تأكيد كلمة المرور الجديدة', validators=[
        Optional(),
        EqualTo('new_password', message='كلمات المرور غير متطابقة')
    ])

class NotificationSettingsForm(FlaskForm):
    email_notifications = BooleanField('إشعارات البريد الإلكتروني')
    browser_notifications = BooleanField('إشعارات المتصفح')
    task_reminders = BooleanField('تذكيرات المهام')


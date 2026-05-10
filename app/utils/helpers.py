"""
helpers.py - دوال مساعدة
"""
import os
import uuid
from datetime import datetime, date,timedelta
from werkzeug.utils import secure_filename
import json
import re

def generate_unique_filename(filename):
    """إنشاء اسم ملف فريد"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_name = secure_filename(filename.rsplit('.', 1)[0] if '.' in filename else filename)
    
    return f"{timestamp}_{unique_id}_{safe_name}.{ext}" if ext else f"{timestamp}_{unique_id}_{safe_name}"

def format_date(value, format_str='%Y-%m-%d'):
    """تنسيق التاريخ"""
    if isinstance(value, datetime):
        return value.strftime(format_str)
    elif isinstance(value, date):
        return value.strftime(format_str)
    elif isinstance(value, str):
        try:
            date_obj = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return date_obj.strftime(format_str)
        except:
            return value
    return value

def format_currency(value, currency='SAR'):
    """تنسيق العملة"""
    try:
        amount = float(value)
        if currency == 'SAR':
            return f"{amount:,.2f} ريال"
        else:
            return f"{amount:,.2f} {currency}"
    except:
        return str(value)

def truncate_text(text, length=100):
    """تقليم النص"""
    if len(text) <= length:
        return text
    return text[:length] + '...'

def is_valid_email(email):
    """التحقق من صحة البريد الإلكتروني"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_phone(phone):
    """التحقق من صحة رقم الهاتف"""
    # هذا نموذج بسيط، يمكن تعديله حسب الدولة
    pattern = r'^\+?[0-9]{10,15}$'
    return re.match(pattern, phone) is not None

def calculate_percentage(part, total):
    """حساب النسبة المئوية"""
    if total == 0:
        return 0
    return (part / total) * 100

def get_file_extension(filename):
    """الحصول على امتداد الملف"""
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

def is_allowed_file(filename, allowed_extensions):
    """التحقق من صيغة الملف"""
    return get_file_extension(filename) in allowed_extensions

def get_file_size_mb(file_path):
    """الحصول على حجم الملف بالميجابايت"""
    try:
        size_bytes = os.path.getsize(file_path)
        return size_bytes / (1024 * 1024)
    except:
        return 0

def clean_json_data(data):
    """تنظيف بيانات JSON"""
    if isinstance(data, dict):
        return {k: clean_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_json_data(item) for item in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, date):
        return data.isoformat()
    elif isinstance(data, uuid.UUID):
        return str(data)
    else:
        return data

def create_slug(text):
    """إنشاء slug من النص"""
    # تحويل النص إلى أحرف صغيرة
    text = text.lower()
    
    # استبدال المسافات بشرطات
    text = re.sub(r'\s+', '-', text)
    
    # إزالة الأحرف غير المرغوب فيها
    text = re.sub(r'[^\w\-]', '', text)
    
    # إزالة الشرطات المكررة
    text = re.sub(r'\-+', '-', text)
    
    # إزالة الشرطات من البداية والنهاية
    text = text.strip('-')
    
    return text

def get_week_range(date_obj=None):
    """الحصول على بداية ونهاية الأسبوع"""
    if date_obj is None:
        date_obj = date.today()
    
    # الاثنين هو أول أيام الأسبوع
    start = date_obj - timedelta(days=date_obj.weekday())
    end = start + timedelta(days=6)
    
    return start, end

def get_month_range(date_obj=None):
    """الحصول على بداية ونهاية الشهر"""
    if date_obj is None:
        date_obj = date.today()
    
    start = date_obj.replace(day=1)
    
    if date_obj.month == 12:
        end = date_obj.replace(year=date_obj.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = date_obj.replace(month=date_obj.month + 1, day=1) - timedelta(days=1)
    
    return start, end

def safe_int(value, default=0):
    """تحويل آمن إلى عدد صحيح"""
    try:
        return int(value)
    except:
        return default

def safe_float(value, default=0.0):
    """تحويل آمن إلى عدد عشري"""
    try:
        return float(value)
    except:
        return default

def parse_date_string(date_str, format_str='%Y-%m-%d'):
    """تحويل سلسلة نصية إلى تاريخ"""
    try:
        return datetime.strptime(date_str, format_str).date()
    except:
        return None

def human_readable_size(size_bytes):
    """تحويل الحجم إلى صيغة مقروءة"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"
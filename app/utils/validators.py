"""
validators.py - دوال التحقق من الصحة
"""
import re
from datetime import datetime, date
from werkzeug.security import check_password_hash
import json

class Validators:
    """فئة للتحقق من صحة البيانات"""
    
    @staticmethod
    def validate_required(data, required_fields):
        """التحقق من الحقول المطلوبة"""
        missing = []
        for field in required_fields:
            if field not in data or data[field] in [None, '', []]:
                missing.append(field)
        
        if missing:
            return False, f"الحقول التالية مطلوبة: {', '.join(missing)}"
        return True, None
    
    @staticmethod
    def validate_email(email):
        """التحقق من صحة البريد الإلكتروني"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(pattern, email):
            return True, None
        return False, "بريد إلكتروني غير صحيح"
    
    @staticmethod
    def validate_phone(phone):
        """التحقق من صحة رقم الهاتف"""
        # نمط بسيط لرقم هاتف دولي
        pattern = r'^\+?[1-9]\d{1,14}$'
        if re.match(pattern, phone):
            return True, None
        return False, "رقم هاتف غير صحيح"
    
    @staticmethod
    def validate_password(password):
        """التحقق من قوة كلمة المرور"""
        errors = []
        
        if len(password) < 8:
            errors.append("كلمة المرور يجب أن تكون 8 أحرف على الأقل")
        
        if not re.search(r'[A-Z]', password):
            errors.append("كلمة المرور يجب أن تحتوي على حرف كبير على الأقل")
        
        if not re.search(r'[a-z]', password):
            errors.append("كلمة المرور يجب أن تحتوي على حرف صغير على الأقل")
        
        if not re.search(r'[0-9]', password):
            errors.append("كلمة المرور يجب أن تحتوي على رقم على الأقل")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("كلمة المرور يجب أن تحتوي على رمز خاص على الأقل")
        
        if errors:
            return False, "\n".join(errors)
        return True, None
    
    @staticmethod
    def validate_date(date_str, format_str='%Y-%m-%d'):
        """التحقق من صحة التاريخ"""
        try:
            datetime.strptime(date_str, format_str)
            return True, None
        except ValueError:
            return False, f"تاريخ غير صحيح، استخدم الصيغة {format_str}"
    
    @staticmethod
    def validate_number(value, min_val=None, max_val=None):
        """التحقق من صحة الرقم"""
        try:
            num = float(value)
            
            if min_val is not None and num < min_val:
                return False, f"القيمة يجب أن تكون {min_val} على الأقل"
            
            if max_val is not None and num > max_val:
                return False, f"القيمة يجب أن تكون {max_val} على الأكثر"
            
            return True, None
        except ValueError:
            return False, "قيمة غير رقمية"
    
    @staticmethod
    def validate_json(json_str):
        """التحقق من صحة JSON"""
        try:
            json.loads(json_str)
            return True, None
        except json.JSONDecodeError as e:
            return False, f"JSON غير صحيح: {str(e)}"
    
    @staticmethod
    def validate_file_extension(filename, allowed_extensions):
        """التحقق من امتداد الملف"""
        if '.' not in filename:
            return False, "الملف بدون امتداد"
        
        ext = filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            return False, f"صيغة الملف غير مدعومة، المسموح: {', '.join(allowed_extensions)}"
        
        return True, None
    
    @staticmethod
    def validate_file_size(file_size, max_size_mb):
        """التحقق من حجم الملف"""
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            return False, f"حجم الملف كبير جداً، الحد الأقصى: {max_size_mb} MB"
        
        return True, None
    
    @staticmethod
    def validate_project_code(code):
        """التحقق من صحة رمز المشروع"""
        pattern = r'^[A-Z]{2,4}-[0-9]{3,6}$'
        if re.match(pattern, code):
            return True, None
        return False, "رمز المشروع غير صحيح، استخدم الصيغة: XXX-123"
    
    @staticmethod
    def validate_coordinates(coords):
        """التحقق من صحة الإحداثيات"""
        pattern = r'^-?[0-9]{1,3}\.[0-9]+,-?[0-9]{1,3}\.[0-9]+$'
        if re.match(pattern, coords):
            return True, None
        return False, "إحداثيات غير صحيحة، استخدم الصيغة: lat,lng"
    
    @staticmethod
    def validate_percentage(value):
        """التحقق من صحة النسبة المئوية"""
        try:
            num = float(value)
            if 0 <= num <= 100:
                return True, None
            return False, "النسبة المئوية يجب أن تكون بين 0 و 100"
        except ValueError:
            return False, "قيمة غير رقمية"
    
    @staticmethod
    def validate_url(url):
        """التحقق من صحة الرابط"""
        pattern = r'^https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
        if re.match(pattern, url):
            return True, None
        return False, "رابط غير صحيح"
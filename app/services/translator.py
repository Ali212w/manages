"""
services/translator.py - خدمة الترجمة المتقدمة
"""
import json
import os
from flask import session, g, request, current_app
from functools import lru_cache
import logging

logger = logging.getLogger(__name__)


class Translator:
    """خدمة الترجمة المتقدمة"""
    
    _translations = {}
    _fallback_lang = 'ar'
    _translations_loaded = False
    _translations_dir = None
    
    @classmethod
    def get_translations_dir(cls):
        """الحصول على مسار مجلد الترجمات"""
        if cls._translations_dir is None:
            # تحديد مسار مجلد الترجمات بشكل صحيح
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            cls._translations_dir = os.path.join(base_dir, 'translations')
        return cls._translations_dir
    
    @classmethod
    def load_translations(cls, force=False):
        """
        تحميل جميع ملفات الترجمة
        
        Args:
            force: إجبار إعادة التحميل
        """
        if cls._translations_loaded and not force:
            return cls._translations
        
        translations_dir = cls.get_translations_dir()
        
        # إنشاء المجلد إذا لم يكن موجوداً
        if not os.path.exists(translations_dir):
            os.makedirs(translations_dir)
            logger.info(f"✅ تم إنشاء مجلد الترجمات: {translations_dir}")
        
        # تحميل الترجمات لكل لغة
        for lang in ['ar', 'en']:
            file_path = os.path.join(translations_dir, f'{lang}.json')
            try:
                if os.path.exists(file_path):
                    with open(file_path, 'r', encoding='utf-8') as f:
                        cls._translations[lang] = json.load(f)
                    logger.info(f"✅ تم تحميل ترجمات {lang}: {len(cls._translations[lang])} مفتاح")
                else:
                    # إذا لم يكن الملف موجوداً، استخدم قاموساً فارغاً
                    cls._translations[lang] = {}
                    # إنشاء ملف ترجمة فارغ
                    cls._save_translations(lang)
                    logger.info(f"📝 تم إنشاء ملف ترجمة جديد: {file_path}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ خطأ في ملف الترجمة {lang}: {e}")
                cls._translations[lang] = {}
            except Exception as e:
                logger.error(f"❌ خطأ غير متوقع في {lang}: {e}")
                cls._translations[lang] = {}
        
        cls._translations_loaded = True
        return cls._translations
    
    @classmethod
    def _save_translations(cls, lang=None):
        """حفظ الترجمات إلى الملفات"""
        translations_dir = cls.get_translations_dir()
        
        if lang:
            # حفظ لغة محددة
            file_path = os.path.join(translations_dir, f'{lang}.json')
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(cls._translations.get(lang, {}), f, ensure_ascii=False, indent=2)
                logger.info(f"✅ تم حفظ ترجمات {lang}")
            except Exception as e:
                logger.error(f"❌ خطأ في حفظ ملف الترجمة {lang}: {e}")
        else:
            # حفظ جميع اللغات
            for lang_code, data in cls._translations.items():
                file_path = os.path.join(translations_dir, f'{lang_code}.json')
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info(f"✅ تم حفظ ترجمات {lang_code}")
                except Exception as e:
                    logger.error(f"❌ خطأ في حفظ ملف الترجمة {lang_code}: {e}")
    
    @classmethod
    def get_current_lang(cls):
        """الحصول على اللغة الحالية"""
        # التحقق من وجود اللغة في g (من before_request)
        if hasattr(g, 'current_lang') and g.current_lang:
            return g.current_lang
        
        # التحقق من الجلسة
        if hasattr(session, 'get') and session.get('language'):
            return session['language']
        
        # التحقق من الطلب (للتطوير)
        try:
            if request and 'lang' in request.args:
                return request.args['lang']
        except RuntimeError:
            # خارج سياق الطلب
            pass
        
        # اللغة الافتراضية
        return cls._fallback_lang
    
    @classmethod
    def set_current_lang(cls, lang):
        """تعيين اللغة الحالية"""
        if lang in ['ar', 'en']:
            session['language'] = lang
            if hasattr(g, 'current_lang'):
                g.current_lang = lang
            return True
        return False
    
    @classmethod
    def _get_nested_value(cls, data, keys):
        """الحصول على قيمة متداخلة من القاموس"""
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
                if current is None:
                    return None
            else:
                return None
        return current
    
    @classmethod
    @lru_cache(maxsize=1000)
    def get_text(cls, key, lang=None, **kwargs):
        """
        الحصول على نص مترجم مع caching
        
        Args:
            key: مفتاح الترجمة (يدعم النقاط للمفاتيح المتداخلة مثل 'navigation.dashboard')
            lang: اللغة المطلوبة (اختياري)
            **kwargs: متغيرات للاستبدال في النص
        
        Returns:
            str: النص المترجم
        """
        if lang is None:
            lang = cls.get_current_lang()
        
        # تحميل الترجمات إذا لم تكن محملة
        translations = cls.load_translations()
        
        # دعم النقاط للوصول للقيم المتداخلة
        keys = key.split('.')
        value = cls._get_nested_value(translations.get(lang, {}), keys)
        
        # إذا لم يتم العثور على الترجمة، جرب اللغة الافتراضية
        if value is None or not isinstance(value, str):
            if lang != cls._fallback_lang:
                value = cls._get_nested_value(translations.get(cls._fallback_lang, {}), keys)
                if value is None or not isinstance(value, str):
                    # إذا لم نجد الترجمة، استخدم المفتاح نفسه
                    text = key
                else:
                    text = value
            else:
                text = key
        else:
            text = value
        
        # التأكد من أن النص هو string
        if not isinstance(text, str):
            text = key
        
        # استبدال المتغيرات
        if kwargs:
            for var_name, var_value in kwargs.items():
                placeholder = f'{{{{{var_name}}}}}'
                text = text.replace(placeholder, str(var_value))
        
        return text
    
    @classmethod
    def get_all(cls, lang=None):
        """الحصول على جميع الترجمات للغة محددة"""
        if lang is None:
            lang = cls.get_current_lang()
        
        translations = cls.load_translations()
        return translations.get(lang, {})
    
    @classmethod
    def get_direction(cls, lang=None):
        """الحصول على اتجاه اللغة"""
        if lang is None:
            lang = cls.get_current_lang()
        return 'rtl' if lang == 'ar' else 'ltr'
    
    @classmethod
    def is_rtl(cls, lang=None):
        """التحقق مما إذا كانت اللغة الحالية هي العربية"""
        return cls.get_direction(lang) == 'rtl'
    
    @classmethod
    def get_text_align(cls, lang=None):
        """الحصول على محاذاة النص"""
        if lang is None:
            lang = cls.get_current_lang()
        return 'right' if lang == 'ar' else 'left'
    
    @classmethod
    def add_translation(cls, key, translation, lang='ar'):
        """إضافة ترجمة جديدة"""
        translations = cls.load_translations(force=True)
        
        # دعم النقاط للوصول للقيم المتداخلة
        keys = key.split('.')
        current = translations[lang]
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = translation
        
        # حفظ الملف
        cls._save_translations(lang)
        
        # مسح الكاش
        cls.get_text.cache_clear()
        
        return True
    
    @classmethod
    def reload(cls):
        """إعادة تحميل الترجمات (مفيد للتطوير)"""
        cls._translations = {}
        cls._translations_loaded = False
        cls.load_translations(force=True)
        cls.get_text.cache_clear()
        logger.info("🔄 تم إعادة تحميل الترجمات")


# ============================================
# دوال مساعدة للاستخدام السهل
# ============================================

def _(key, **kwargs):
    """
    دالة الترجمة الرئيسية - يمكن استخدامها في القوالب وملفات Python
    
    الاستخدام:
        {{ _('navigation.dashboard') }}
        {{ _('welcome_message', name=user.name) }}
        flash(_('messages.save_success'), 'success')
    """
    return Translator.get_text(key, **kwargs)


def __(key, **kwargs):
    """اسم بديل لدالة الترجمة"""
    return Translator.get_text(key, **kwargs)


def get_current_lang():
    """الحصول على اللغة الحالية"""
    return Translator.get_current_lang()


def get_direction():
    """الحصول على اتجاه الصفحة"""
    return Translator.get_direction()


def get_text_align():
    """الحصول على محاذاة النص"""
    return Translator.get_text_align()


def reload_translations():
    """إعادة تحميل الترجمات (للتطوير)"""
    Translator.reload()


def add_translation(key, translation, lang='ar'):
    """إضافة ترجمة جديدة"""
    return Translator.add_translation(key, translation, lang)


# ============================================
# دوال إضافية لتنسيق البيانات حسب اللغة
# ============================================

def format_date(date_obj, format_type='date', lang=None):
    """
    تنسيق التاريخ حسب اللغة
    
    Args:
        date_obj: كائن التاريخ
        format_type: نوع التنسيق ('date', 'datetime', 'time', 'full')
        lang: اللغة (اختياري)
    """
    if date_obj is None:
        return ''
    
    if lang is None:
        lang = get_current_lang()
    
    if format_type == 'date':
        if lang == 'ar':
            return date_obj.strftime('%Y-%m-%d')
        else:
            return date_obj.strftime('%Y-%m-%d')
    elif format_type == 'datetime':
        if lang == 'ar':
            return date_obj.strftime('%Y-%m-%d %H:%M')
        else:
            return date_obj.strftime('%Y-%m-%d %H:%M')
    elif format_type == 'time':
        return date_obj.strftime('%H:%M')
    elif format_type == 'full':
        if lang == 'ar':
            months_ar = ['يناير', 'فبراير', 'مارس', 'إبريل', 'مايو', 'يونيو',
                        'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
            return f"{date_obj.day} {months_ar[date_obj.month - 1]} {date_obj.year}"
        else:
            months_en = ['January', 'February', 'March', 'April', 'May', 'June',
                        'July', 'August', 'September', 'October', 'November', 'December']
            return f"{months_en[date_obj.month - 1]} {date_obj.day}, {date_obj.year}"
    
    return str(date_obj)


def format_number(number, decimals=2, lang=None):
    """
    تنسيق الأرقام حسب اللغة
    
    Args:
        number: الرقم
        decimals: عدد المنازل العشرية
        lang: اللغة (اختياري)
    """
    if number is None:
        number = 0
    
    if lang is None:
        lang = get_current_lang()
    
    if lang == 'ar':
        # الأرقام العربية
        arabic_numerals = {
            '0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤',
            '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩',
            '.': '.', ',': '،'
        }
        formatted = f"{number:,.{decimals}f}"
        result = ''.join(arabic_numerals.get(c, c) for c in formatted)
        return result
    else:
        return f"{number:,.{decimals}f}"


def format_currency(amount, currency='SAR', lang=None):
    """
    تنسيق العملة حسب اللغة
    
    Args:
        amount: المبلغ
        currency: العملة ('SAR', 'USD', 'EUR', etc.)
        lang: اللغة (اختياري)
    """
    if amount is None:
        amount = 0
    
    if lang is None:
        lang = get_current_lang()
    
    currency_symbols = {
        'SAR': {'ar': 'ر.س', 'en': 'SAR'},
        'USD': {'ar': 'دولار', 'en': 'USD'},
        'EUR': {'ar': 'يورو', 'en': 'EUR'},
        'GBP': {'ar': 'جنيه', 'en': 'GBP'},
        'AED': {'ar': 'د.إ', 'en': 'AED'},
        'KWD': {'ar': 'د.ك', 'en': 'KWD'},
        'QAR': {'ar': 'ر.ق', 'en': 'QAR'},
        'BHD': {'ar': 'د.ب', 'en': 'BHD'},
        'OMR': {'ar': 'ر.ع', 'en': 'OMR'},
        'EGP': {'ar': 'ج.م', 'en': 'EGP'},
    }
    
    symbol = currency_symbols.get(currency, {'ar': currency, 'en': currency})[lang]
    formatted_amount = format_number(amount, 2, lang)
    
    if lang == 'ar':
        return f"{formatted_amount} {symbol}"
    else:
        return f"{symbol} {formatted_amount}"


def get_status_text(status_key, lang=None):
    """
    الحصول على نص الحالة مترجماً
    
    Args:
        status_key: مفتاح الحالة (مثل 'active', 'completed')
        lang: اللغة (اختياري)
    """
    status_map = {
        # Project status
        'active': 'status.active',
        'completed': 'status.completed',
        'planning': 'projects.status_planning',
        'suspended': 'status.inactive',
        'cancelled': 'status.cancelled',
        'delayed': 'status.delayed',
        'critical_delay': 'priority.critical',
        'in_progress': 'status.in_progress',
        'on_hold': 'status.on_hold',
        'approved': 'status.approved',
        'rejected': 'status.rejected',
        'pending': 'status.pending',
        'under_review': 'status.reviewed',
        
        # Task status
        'task_pending': 'status.pending',
        'task_in_progress': 'status.in_progress',
        'task_completed': 'status.completed',
        'task_on_hold': 'status.on_hold',
        'task_cancelled': 'status.cancelled',
        'task_overdue': 'status.delayed',
        
        # Priority
        'low': 'priority.low',
        'medium': 'priority.medium',
        'high': 'priority.high',
        'critical': 'priority.critical',
    }
    
    translation_key = status_map.get(status_key, status_key)
    return _(translation_key, lang=lang)
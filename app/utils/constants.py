# ثوابت النظام

# حالات المشروع
PROJECT_STATUS = {
    'pending': 'قيد الانتظار',
    'in_progress': 'قيد التنفيذ',
    'completed': 'مكتمل',
    'on_hold': 'متوقف',
    'cancelled': 'ملغي'
}

# حالات النشاط
ACTIVITY_STATUS = {
    'not_started': 'لم يبدأ',
    'in_progress': 'قيد التنفيذ',
    'completed': 'مكتمل',
    'blocked': 'متوقف',
    'delayed': 'متأخر'
}

# أولويات
PRIORITIES = {
    'high': 'عالية',
    'medium': 'متوسطة',
    'low': 'منخفضة'
}

# أنواع المشاريع
PROJECT_DOMAINS = {
    'engineering': 'هندسي',
    'software': 'برمجي',
    'administrative': 'إداري',
    'agricultural': 'زراعي',
    'commercial': 'تجاري',
    'research': 'بحثي',
    'general': 'عام'
}

# أنواع الموارد
RESOURCE_TYPES = {
    'human': 'بشري',
    'equipment': 'معدات',
    'material': 'مواد',
    'financial': 'مالي'
}

# أنواع المخاطر
RISK_LEVELS = {
    'very_low': 'منخفض جداً',
    'low': 'منخفض',
    'medium': 'متوسط',
    'high': 'عالي',
    'very_high': 'عالي جداً'
}

# وحدات القياس
UNITS = {
    'm': 'متر',
    'm2': 'متر مربع',
    'm3': 'متر مكعب',
    'kg': 'كيلو جرام',
    'ton': 'طن',
    'hour': 'ساعة',
    'day': 'يوم',
    'week': 'أسبوع',
    'month': 'شهر',
    'unit': 'وحدة'
}

# العملات
CURRENCIES = {
    'SAR': 'ريال سعودي',
    'USD': 'دولار أمريكي',
    'EUR': 'يورو',
    'AED': 'درهم إماراتي',
    'EGP': 'جنيه مصري'
}

# أنماط التاريخ
DATE_FORMATS = [
    '%Y-%m-%d',
    '%Y/%m/%d',
    '%d-%m-%Y',
    '%d/%m/%Y',
    '%m/%d/%Y',
    '%Y%m%d',
    '%d.%m.%Y'
]
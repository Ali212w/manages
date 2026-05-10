# app/services/nlp_processor.py

import re
from datetime import datetime
import json
from typing import Dict, List, Any
import spacy
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification
import langdetect
from flask import current_app

class NLPProcessor:
    """معالجة اللغة الطبيعية وفهم الأوامر"""
    
    def __init__(self):
        # تحميل نماذج NLP
        self.load_models()
        
        # قوائم الكلمات المفتاحية
        self.keywords = self._init_keywords()
    
    def load_models(self):
        """تحميل نماذج NLP"""
        try:
            # نموذج للغة العربية
            self.nlp_ar = spacy.load("ar_core_web_sm")
        except:
            self.nlp_ar = None
            current_app.logger.warning("Arabic NLP model not loaded")
        
        try:
            # نموذج للغة الإنجليزية
            self.nlp_en = spacy.load("en_core_web_sm")
        except:
            self.nlp_en = None
            current_app.logger.warning("English NLP model not loaded")
        
        # نموذج للتعرف على الكيانات (NER)
        try:
            self.ner_model = pipeline("ner", model="aubmindlab/bert-base-arabertv2")
        except:
            self.ner_model = None
    
    def _init_keywords(self):
        """تهيئة قوائم الكلمات المفتاحية"""
        return {
            'command_types': {
                'extract': {
                    'ar': ['استخرج', 'استخراج', 'أستخرج', 'خذ', 'اجلب'],
                    'en': ['extract', 'get', 'retrieve', 'pull', 'fetch']
                },
                'analyze': {
                    'ar': ['حلل', 'تحليل', 'ادرس', 'افحص'],
                    'en': ['analyze', 'analyse', 'examine', 'study']
                },
                'report': {
                    'ar': ['تقرير', 'احصاء', 'أحصائيات', 'ملخص'],
                    'en': ['report', 'summary', 'statistics', 'overview']
                },
                'search': {
                    'ar': ['ابحث', 'بحث', 'فتش', 'دور'],
                    'en': ['search', 'find', 'lookup']
                },
                'create': {
                    'ar': ['أنشئ', 'إنشاء', 'أضف', 'جديد'],
                    'en': ['create', 'add', 'new', 'make']
                },
                'update': {
                    'ar': ['حدث', 'تحديث', 'عدل', 'غير'],
                    'en': ['update', 'modify', 'change', 'edit']
                }
            },
            
            'target_types': {
                'project': {
                    'ar': ['مشروع', 'مشاريع'],
                    'en': ['project', 'projects']
                },
                'task': {
                    'ar': ['مهمة', 'مهام', 'نشاط', 'أنشطة'],
                    'en': ['task', 'tasks', 'activity', 'activities']
                },
                'resource': {
                    'ar': ['مورد', 'موارد', 'معدات'],
                    'en': ['resource', 'resources', 'equipment']
                },
                'eps': {
                    'ar': ['eps', 'هيكل'],
                    'en': ['eps']
                },
                'obs': {
                    'ar': ['obs', 'هيكل تنظيمي'],
                    'en': ['obs']
                },
                'wbs': {
                    'ar': ['wbs', 'تقسيم العمل'],
                    'en': ['wbs']
                },
                'user': {
                    'ar': ['مستخدم', 'موظف', 'عامل'],
                    'en': ['user', 'employee', 'staff']
                }
            },
            
            'entities': {
                'date': {
                    'ar': ['تاريخ', 'يوم', 'شهر', 'سنة'],
                    'en': ['date', 'day', 'month', 'year']
                },
                'money': {
                    'ar': ['ريال', 'دولار', 'سعر', 'تكلفة', 'ميزانية'],
                    'en': ['rial', 'dollar', 'cost', 'price', 'budget']
                },
                'quantity': {
                    'ar': ['كمية', 'عدد', 'مقدار'],
                    'en': ['quantity', 'amount', 'number']
                },
                'name': {
                    'ar': ['اسم', 'عنوان'],
                    'en': ['name', 'title']
                }
            }
        }
    
    def understand_command(self, command_text: str) -> Dict[str, Any]:
        """فهم الأمر وتحديد نوعه والهدف"""
        result = {
            'command_type': 'unknown',
            'target_type': 'general',
            'language': self._detect_language(command_text),
            'entities': {},
            'parameters': {},
            'confidence': 0,
            'original_text': command_text
        }
        
        # تطبيع النص
        normalized_text = self._normalize_text(command_text)
        
        # تحديد نوع الأمر
        cmd_type, type_conf = self._identify_command_type(normalized_text, result['language'])
        result['command_type'] = cmd_type
        result['confidence'] += type_conf * 0.3
        
        # تحديد الهدف
        target, target_conf = self._identify_target(normalized_text, result['language'])
        result['target_type'] = target
        result['confidence'] += target_conf * 0.3
        
        # استخراج الكيانات
        entities, entity_conf = self._extract_entities(normalized_text, result['language'])
        result['entities'] = entities
        result['confidence'] += entity_conf * 0.2
        
        # استخراج المعلمات
        params, param_conf = self._extract_parameters(normalized_text, result['language'])
        result['parameters'] = params
        result['confidence'] += param_conf * 0.2
        
        return result
    
    def _detect_language(self, text: str) -> str:
        """تحديد لغة النص"""
        try:
            lang = langdetect.detect(text)
            if lang == 'ar':
                return 'arabic'
            elif lang == 'en':
                return 'english'
            else:
                return 'mixed'
        except:
            # فحص بسيط
            arabic_chars = re.findall(r'[\u0600-\u06FF]', text[:100])
            if len(arabic_chars) > 10:
                return 'arabic'
            return 'english'
    
    def _normalize_text(self, text: str) -> str:
        """تطبيع النص (إزالة علامات التشكيل، توحيد الأحرف)"""
        # إزالة علامات التشكيل العربية
        text = re.sub(r'[\u0617-\u061A\u064B-\u0652]', '', text)
        
        # توحيد الألف
        text = re.sub(r'[إأآا]', 'ا', text)
        
        # توحيد التاء المربوطة
        text = re.sub(r'[ةه]', 'ة', text)
        
        return text.lower().strip()
    
    def _identify_command_type(self, text: str, language: str) -> tuple:
        """تحديد نوع الأمر"""
        max_score = 0
        best_type = 'unknown'
        
        for cmd_type, keywords in self.keywords['command_types'].items():
            lang_key = 'ar' if language == 'arabic' else 'en'
            score = 0
            
            for keyword in keywords.get(lang_key, []):
                if keyword in text:
                    score += 1
            
            if score > max_score:
                max_score = score
                best_type = cmd_type
        
        confidence = min(max_score * 25, 100) if max_score > 0 else 0
        return best_type, confidence
    
    def _identify_target(self, text: str, language: str) -> tuple:
        """تحديد الهدف"""
        max_score = 0
        best_target = 'general'
        
        for target, keywords in self.keywords['target_types'].items():
            lang_key = 'ar' if language == 'arabic' else 'en'
            score = 0
            
            for keyword in keywords.get(lang_key, []):
                if keyword in text:
                    score += 1
            
            if score > max_score:
                max_score = score
                best_target = target
        
        confidence = min(max_score * 33, 100) if max_score > 0 else 0
        return best_target, confidence
    
    def _extract_entities(self, text: str, language: str) -> tuple:
        """استخراج الكيانات (أرقام، تواريخ، أسماء)"""
        entities = {
            'dates': [],
            'numbers': [],
            'currencies': [],
            'names': []
        }
        
        # استخراج التواريخ
        date_patterns = [
            r'\d{2,4}[/-]\d{1,2}[/-]\d{1,2}',  # YYYY-MM-DD
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # DD-MM-YYYY
            r'\d{1,2}\s+[ينايرفبرايرمارسيوليواغسطسمتوبرنوفمبرديسمبر]+\s+\d{2,4}'  # تاريخ عربي
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            entities['dates'].extend(matches)
        
        # استخراج الأرقام
        numbers = re.findall(r'\d+(?:[.,]\d+)?', text)
        entities['numbers'] = [float(n.replace(',', '')) for n in numbers if n]
        
        # استخراج العملات
        currency_patterns = [
            r'(\d+(?:[.,]\d+)?)\s*(ريال|دولار|جنيه|دينار|درهم)',
            r'(ريال|دولار|جنيه|دينار|درهم)\s*(\d+(?:[.,]\d+)?)'
        ]
        
        for pattern in currency_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) == 2:
                    try:
                        amount = float(match[0].replace(',', ''))
                        currency = match[1]
                        entities['currencies'].append({
                            'amount': amount,
                            'currency': currency
                        })
                    except:
                        pass
        
        confidence = 70 if entities['dates'] or entities['numbers'] else 30
        return entities, confidence
    
    def _extract_parameters(self, text: str, language: str) -> tuple:
        """استخراج معلمات إضافية"""
        params = {}
        
        # البحث عن كلمات مثل "لـ" أو "for" للإشارة إلى الهدف
        if ' لـ ' in text or ' ل ' in text:
            parts = text.split(' لـ ' if ' لـ ' in text else ' ل ')
            if len(parts) > 1:
                params['target_name'] = parts[1].strip()
        
        if ' for ' in text:
            parts = text.split(' for ')
            if len(parts) > 1:
                params['target_name'] = parts[1].strip()
        
        # البحث عن فترة زمنية
        time_periods = re.findall(r'آخر\s+(\d+)\s+(أيام|شهور|سنوات)', text)
        if time_periods:
            params['period'] = {
                'value': int(time_periods[0][0]),
                'unit': time_periods[0][1]
            }
        
        confidence = 60 if params else 20
        return params, confidence
    
    def extract_information(self, text: str, target_type: str) -> Dict[str, Any]:
        """استخراج معلومات محددة من النص"""
        extracted = {}
        
        if target_type == 'project':
            extracted = self._extract_project_info(text)
        elif target_type == 'task':
            extracted = self._extract_task_info(text)
        elif target_type == 'resource':
            extracted = self._extract_resource_info(text)
        elif target_type == 'eps':
            extracted = self._extract_eps_info(text)
        elif target_type == 'obs':
            extracted = self._extract_obs_info(text)
        elif target_type == 'wbs':
            extracted = self._extract_wbs_info(text)
        
        return extracted
    
    def _extract_project_info(self, text: str) -> Dict[str, Any]:
        """استخراج معلومات المشروع"""
        info = {}
        
        # البحث عن اسم المشروع
        name_patterns = [
            r'اسم المشروع[:\s]+(.+)',
            r'project name[:\s]+(.+)',
            r'مشروع\s+([^\n]+)'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['name'] = match.group(1).strip()
                break
        
        # البحث عن الميزانية
        budget_patterns = [
            r'الميزانية[:\s]+(\d+(?:[.,]\d+)?)',
            r'budget[:\s]+(\d+(?:[.,]\d+)?)',
            r'قيمة العقد[:\s]+(\d+(?:[.,]\d+)?)'
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['budget'] = float(match.group(1).replace(',', ''))
                break
        
        # البحث عن التواريخ
        date_pattern = r'(\d{2,4}[/-]\d{1,2}[/-]\d{1,2})'
        dates = re.findall(date_pattern, text)
        if len(dates) >= 2:
            info['start_date'] = dates[0]
            info['end_date'] = dates[1]
        
        return info
    
    def _extract_task_info(self, text: str) -> Dict[str, Any]:
        """استخراج معلومات المهمة"""
        info = {}
        
        # البحث عن وصف المهمة
        lines = text.split('\n')
        for line in lines[:10]:  # أول 10 أسطر
            if len(line.strip()) > 10 and not re.search(r'\d', line):
                info['description'] = line.strip()
                break
        
        # البحث عن المدة
        duration_patterns = [
            r'المدة[:\s]+(\d+)',
            r'duration[:\s]+(\d+)',
            r'(\d+)\s*(يوم|ساعة)'
        ]
        
        for pattern in duration_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['duration'] = int(match.group(1))
                break
        
        return info
    
    def _extract_resource_info(self, text: str) -> Dict[str, Any]:
        """استخراج معلومات المورد"""
        info = {}
        
        # البحث عن اسم المورد
        name_patterns = [
            r'اسم المورد[:\s]+(.+)',
            r'resource name[:\s]+(.+)'
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['name'] = match.group(1).strip()
                break
        
        # البحث عن الكمية
        quantity_patterns = [
            r'الكمية[:\s]+(\d+(?:[.,]\d+)?)',
            r'quantity[:\s]+(\d+(?:[.,]\d+)?)'
        ]
        
        for pattern in quantity_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['quantity'] = float(match.group(1).replace(',', ''))
                break
        
        return info
    
    def _extract_eps_info(self, text: str) -> Dict[str, Any]:
        """استخراج معلومات EPS"""
        info = {}
        
        # البحث عن كود EPS
        code_patterns = [
            r'كود EPS[:\s]+([A-Z0-9-]+)',
            r'EPS code[:\s]+([A-Z0-9-]+)'
        ]
        
        for pattern in code_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['code'] = match.group(1).strip()
                break
        
        return info
    
    def _extract_obs_info(self, text: str) -> Dict[str, Any]:
        """استخراج معلومات OBS"""
        info = {}
        
        # البحث عن كود OBS
        code_patterns = [
            r'كود OBS[:\s]+([A-Z0-9-]+)',
            r'OBS code[:\s]+([A-Z0-9-]+)'
        ]
        
        for pattern in code_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['code'] = match.group(1).strip()
                break
        
        return info
    
    def _extract_wbs_info(self, text: str) -> Dict[str, Any]:
        """استخراج معلومات WBS"""
        info = {}
        
        # البحث عن كود WBS
        code_patterns = [
            r'كود WBS[:\s]+([0-9.]+)',
            r'WBS code[:\s]+([0-9.]+)'
        ]
        
        for pattern in code_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['code'] = match.group(1).strip()
                break
        
        return info
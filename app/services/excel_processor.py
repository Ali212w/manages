"""
معالج Excel الذكي - يقوم بتحليل ملفات Excel وإنشاء المشاريع تلقائياً
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import re
from typing import Dict, List, Any, Optional, Tuple
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class SmartExcelProcessor:
    """معالج Excel الذكي"""
    
    def __init__(self):
        self.column_patterns = {
            'item_code': [
                r'رقم البند', r'كود', r'رمز', r'item.*code', r'code',
                r'البند', r'رقم', r'no\.', r'number'
            ],
            'description': [
                r'الوصف', r'مواصفات', r'description', r'specification',
                r'العمل', r'work', r'item.*description'
            ],
            'unit': [
                r'الوحدة', r'unit', r'وحدة', r'measurement'
            ],
            'quantity': [
                r'الكمية', r'quantity', r'qty', r'كمية',
                r'amount', r'volume'
            ],
            'unit_price': [
                r'سعر الوحدة', r'سعر', r'unit.*price', r'rate',
                r'price', r'cost.*per.*unit'
            ],
            'total_price': [
                r'الإجمالي', r'المبلغ', r'total', r'amount',
                r'sub.*total', r'مجموع'
            ],
            'category': [
                r'الفئة', r'نوع', r'category', r'type',
                r'classification', r'group'
            ],
            'notes': [
                r'ملاحظات', r'notes', r'remarks', r'تعليقات'
            ]
        }
        
        self.construction_keywords = {
            'excavation': ['حفر', 'نزح', 'ردم', 'قطع', 'excavation', 'digging'],
            'concrete': ['خرسانة', 'صب', 'قواعد', 'أعمدة', 'أسقف', 'concrete', 'pour'],
            'masonry': ['بناء', 'طوب', 'بلوك', 'حجر', 'masonry', 'brick'],
            'plumbing': ['سباكة', 'صرف', 'مواسير', 'plumbing', 'pipes'],
            'electrical': ['كهرباء', 'إنارة', 'أسلاك', 'electrical', 'wiring'],
            'finishing': ['تشطيب', 'دهان', 'بلاط', 'سيراميك', 'finishing', 'tiles']
        }
    
    def process_excel_file(self, file_path: Path) -> Dict[str, Any]:
        """
        معالجة ملف Excel وإنشاء هيكل المشروع
        
        Args:
            file_path: مسار ملف Excel
            
        Returns:
            dict: هيكل المشروع والمعلومات المستخرجة
        """
        logger.info(f"بدء معالجة ملف Excel: {file_path}")
        
        try:
            # قراءة ملف Excel
            excel_data = self._read_excel_file(file_path)
            
            if not excel_data['success']:
                return excel_data
            
            # تحليل كل ورقة
            analyzed_sheets = []
            bill_items = []
            
            for sheet_name, sheet_data in excel_data['sheets'].items():
                sheet_analysis = self._analyze_sheet(sheet_name, sheet_data)
                analyzed_sheets.append(sheet_analysis)
                
                # استخراج بنود جدول الكميات من هذه الورقة
                if sheet_analysis.get('contains_bill_items', False):
                    items = self._extract_bill_items_from_sheet(sheet_data, sheet_analysis)
                    bill_items.extend(items)
            
            # بناء الهيكل الهرمي
            hierarchical_structure = self._build_hierarchical_structure(bill_items)
            
            # تحليل الأنشطة
            activity_analysis = self._analyze_activities(bill_items)
            
            # حساب التكاليف
            cost_analysis = self._analyze_costs(bill_items)
            
            # إنشاء التقرير النهائي
            result = {
                'success': True,
                'file_name': file_path.name,
                'sheets_analyzed': len(analyzed_sheets),
                'total_bill_items': len(bill_items),
                'bill_items': bill_items[:50],  # أول 50 بند فقط
                'hierarchical_structure': hierarchical_structure,
                'activity_analysis': activity_analysis,
                'cost_analysis': cost_analysis,
                'summary': self._generate_summary(bill_items, cost_analysis),
                'recommendations': self._generate_recommendations(bill_items, cost_analysis)
            }
            
            logger.info(f"تم معالجة ملف Excel بنجاح: {len(bill_items)} بند")
            return result
            
        except Exception as e:
            logger.error(f"خطأ في معالجة ملف Excel: {e}")
            return {
                'success': False,
                'error': str(e),
                'file_name': file_path.name
            }
    
    def _read_excel_file(self, file_path: Path) -> Dict[str, Any]:
        """قراءة ملف Excel"""
        try:
            # قراءة جميع الأوراق
            excel_file = pd.ExcelFile(file_path)
            sheets = {}
            
            for sheet_name in excel_file.sheet_names:
                try:
                    # قراءة الورقة
                    df = excel_file.parse(sheet_name, header=None)
                    
                    # تحويل إلى قائمة
                    sheet_data = df.values.tolist()
                    
                    sheets[sheet_name] = {
                        'data': sheet_data,
                        'shape': df.shape,
                        'headers': self._extract_headers(df)
                    }
                    
                except Exception as e:
                    logger.warning(f"خطأ في قراءة ورقة {sheet_name}: {e}")
                    continue
            
            if not sheets:
                return {'success': False, 'error': 'لا توجد أوراق صالحة في الملف'}
            
            return {
                'success': True,
                'sheets': sheets,
                'total_sheets': len(sheets)
            }
            
        except Exception as e:
            return {'success': False, 'error': f'خطأ في قراءة الملف: {str(e)}'}
    
    def _extract_headers(self, df: pd.DataFrame) -> List[str]:
        """استخراج رؤوس الجدول"""
        headers = []
        
        # البحث عن صف الرؤوس (عادةً الصف الأول أو الثاني)
        for i in range(min(3, len(df))):
            row = df.iloc[i].fillna('').astype(str).tolist()
            if any(isinstance(cell, str) and len(cell.strip()) > 3 for cell in row):
                headers = [str(cell).strip() for cell in row]
                break
        
        return headers
    
    def _analyze_sheet(self, sheet_name: str, sheet_data: Dict) -> Dict[str, Any]:
        """تحليل ورقة Excel"""
        data = sheet_data.get('data', [])
        headers = sheet_data.get('headers', [])
        shape = sheet_data.get('shape', (0, 0))
        
        # تحليل محتوى الورقة
        contains_bill_items = self._detect_bill_items(data, headers)
        contains_schedule = 'جدول' in sheet_name.lower() or 'schedule' in sheet_name.lower()
        contains_costs = any(word in sheet_name.lower() for word in ['تكاليف', 'costs', 'ميزانية'])
        
        # تحليل الأنماط
        patterns = self._detect_patterns(data)
        
        return {
            'sheet_name': sheet_name,
            'rows': shape[0],
            'columns': shape[1],
            'contains_bill_items': contains_bill_items,
            'contains_schedule': contains_schedule,
            'contains_costs': contains_costs,
            'detected_patterns': patterns,
            'header_analysis': self._analyze_headers(headers)
        }
    
    def _detect_bill_items(self, data: List[List], headers: List[str]) -> bool:
        """الكشف عما إذا كانت الورقة تحتوي على بنود جدول كميات"""
        if not data:
            return False
        
        # التحقق من الرؤوس
        header_text = ' '.join([str(h).lower() for h in headers])
        bill_keywords = ['بند', 'وصف', 'وحدة', 'كمية', 'سعر', 'إجمالي']
        
        for keyword in bill_keywords:
            if keyword in header_text:
                return True
        
        # التحقق من البيانات
        sample_rows = min(10, len(data))
        for i in range(sample_rows):
            row_text = ' '.join([str(cell).lower() for cell in data[i]])
            if any(keyword in row_text for keyword in bill_keywords):
                return True
        
        return False
    
    def _detect_patterns(self, data: List[List]) -> Dict[str, Any]:
        """اكتشاف الأنماط في البيانات"""
        patterns = {
            'hierarchical_codes': False,
            'numeric_quantities': False,
            'monetary_values': False,
            'unit_patterns': False
        }
        
        if not data:
            return patterns
        
        sample_size = min(20, len(data))
        sample_data = data[:sample_size]
        
        # التحقق من الأكواد الهرمية (مثل 1.1, 1.1.1)
        for row in sample_data:
            for cell in row:
                cell_str = str(cell)
                if re.match(r'^\d+(\.\d+)+$', cell_str.strip()):
                    patterns['hierarchical_codes'] = True
                    break
        
        # التحقق من الكميات الرقمية
        numeric_count = 0
        for row in sample_data:
            for cell in row:
                try:
                    float(str(cell).replace(',', ''))
                    numeric_count += 1
                except:
                    pass
        
        if numeric_count > len(sample_data) * 2:
            patterns['numeric_quantities'] = True
        
        # التحقق من القيم النقدية
        for row in sample_data:
            for cell in row:
                cell_str = str(cell)
                if 'ريال' in cell_str or 'SAR' in cell_str or '$' in cell_str:
                    patterns['monetary_values'] = True
                    break
        
        # التحقق من أنماط الوحدات
        unit_patterns = [r'م\d', r'متر', r'كجم', r'طن', r'حبة', r'يوم']
        for row in sample_data:
            for cell in row:
                cell_str = str(cell)
                for pattern in unit_patterns:
                    if re.search(pattern, cell_str, re.IGNORECASE):
                        patterns['unit_patterns'] = True
                        break
        
        return patterns
    
    def _analyze_headers(self, headers: List[str]) -> Dict[str, Any]:
        """تحليل رؤوس الجدول"""
        analysis = {
            'detected_columns': {},
            'confidence_scores': {},
            'suggested_mapping': {}
        }
        
        for english_name, arabic_patterns in self.column_patterns.items():
            for i, header in enumerate(headers):
                header_lower = str(header).lower()
                
                for pattern in arabic_patterns:
                    if re.search(pattern, header_lower, re.IGNORECASE):
                        analysis['detected_columns'][english_name] = {
                            'index': i,
                            'header': header,
                            'pattern': pattern
                        }
                        
                        # حساب درجة الثقة
                        confidence = self._calculate_confidence(header, pattern)
                        analysis['confidence_scores'][english_name] = confidence
                        
                        break
        
        return analysis
    
    def _calculate_confidence(self, header: str, pattern: str) -> float:
        """حساب درجة الثقة في اكتشاف العمود"""
        header_lower = str(header).lower()
        pattern_lower = pattern.lower()
        
        # إذا كان النمط مطابقاً تماماً
        if pattern_lower in header_lower:
            return 1.0
        
        # حساب التشابه
        words_header = set(header_lower.split())
        words_pattern = set(pattern_lower.split())
        
        intersection = words_header.intersection(words_pattern)
        union = words_header.union(words_pattern)
        
        if union:
            similarity = len(intersection) / len(union)
            return similarity
        
        return 0.5
    
    def _extract_bill_items_from_sheet(self, sheet_data: Dict, 
                                     sheet_analysis: Dict) -> List[Dict]:
        """استخراج بنود جدول الكميات من الورقة"""
        data = sheet_data.get('data', [])
        headers = sheet_data.get('headers', [])
        column_mapping = sheet_analysis.get('header_analysis', {}).get('detected_columns', {})
        
        bill_items = []
        
        # بداية البيانات (تخطي الرؤوس)
        start_row = 2 if headers else 0
        
        for row_idx in range(start_row, len(data)):
            row = data[row_idx]
            
            # تخطي الصفوف الفارغة
            if all(pd.isna(cell) or str(cell).strip() == '' for cell in row):
                continue
            
            # استخراج البند
            bill_item = self._extract_bill_item_from_row(row, column_mapping, headers)
            if bill_item:
                bill_items.append(bill_item)
        
        return bill_items
    
    def _extract_bill_item_from_row(self, row: List, column_mapping: Dict,
                                  headers: List[str]) -> Optional[Dict]:
        """استخراج بند من صف الجدول"""
        try:
            bill_item = {}
            
            # استخراج الكود
            if 'item_code' in column_mapping:
                col_idx = column_mapping['item_code']['index']
                if col_idx < len(row):
                    bill_item['item_code'] = str(row[col_idx]).strip()
            
            # استخراج الوصف
            if 'description' in column_mapping:
                col_idx = column_mapping['description']['index']
                if col_idx < len(row):
                    bill_item['description'] = str(row[col_idx]).strip()
                    bill_item['description_ar'] = bill_item['description']
            
            # إذا لم يكن هناك وصف، نستخدم أول عمود غير فارغ
            if 'description' not in bill_item or not bill_item['description']:
                for i, cell in enumerate(row):
                    cell_str = str(cell).strip()
                    if cell_str and not self._looks_like_number(cell_str):
                        bill_item['description'] = cell_str
                        bill_item['description_ar'] = cell_str
                        break
            
            # إذا لم يكن هناك وصف بعد، نتخطى الصف
            if 'description' not in bill_item or not bill_item['description']:
                return None
            
            # استخراج الوحدة
            if 'unit' in column_mapping:
                col_idx = column_mapping['unit']['index']
                if col_idx < len(row):
                    bill_item['unit'] = str(row[col_idx]).
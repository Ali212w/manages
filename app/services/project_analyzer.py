"""
محلل المشاريع الذكي - يقوم بتحليل ملف Excel وإنشاء المشروع تلقائياً
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import json
from typing import Dict, List, Any, Optional
import logging
from ..models.project_models import Project, BillItem, Activity, Task
from ..models.core_models import User
from ..ai_engine.excel_ai_parser import ExcelAIParser
from ..ai_engine.schedule_optimizer import ScheduleOptimizer
from ..ai_engine.cost_predictor import CostPredictor
from ..ai_engine.risk_analyzer import RiskAnalyzer

logger = logging.getLogger(__name__)

class SmartProjectAnalyzer:
    """محلل المشاريع الذكي"""
    
    def __init__(self):
        self.excel_parser = ExcelAIParser()
        self.schedule_optimizer = ScheduleOptimizer()
        self.cost_predictor = CostPredictor()
        self.risk_analyzer = RiskAnalyzer()
        
    def analyze_excel_and_create_project(self, excel_path: Path, user: User, 
                                        project_data: Dict) -> Dict[str, Any]:
        """
        تحليل ملف Excel وإنشاء المشروع تلقائياً
        
        Args:
            excel_path: مسار ملف Excel
            user: المستخدم المنشئ
            project_data: بيانات المشروع الأساسية
            
        Returns:
            dict: نتيجة التحليل والمشروع المنشأ
        """
        logger.info(f"بدء تحليل ملف Excel: {excel_path}")
        
        # الخطوة 1: قراءة وتحليل ملف Excel
        excel_data = self.excel_parser.parse_excel_file(excel_path)
        
        if not excel_data['success']:
            raise ValueError(f"فشل في تحليل ملف Excel: {excel_data.get('error')}")
        
        # الخطوة 2: استخراج بنود جدول الكميات
        bill_items = self._extract_bill_items(excel_data['data'])
        
        # الخطوة 3: بناء الهيكل الهرمي الذكي
        project_structure = self._build_smart_hierarchy(bill_items, project_data)
        
        # الخطوة 4: حساب التكاليف والتقديرات
        cost_estimates = self.cost_predictor.estimate_project_costs(
            bill_items, 
            project_structure,
            project_data
        )
        
        # الخطوة 5: تحليل المخاطر
        risk_analysis = self.risk_analyzer.analyze_project_risks(
            project_structure,
            cost_estimates,
            project_data
        )
        
        # الخطوة 6: إنشاء الجدول الزمني الذكي
        schedule = self.schedule_optimizer.create_optimal_schedule(
            project_structure,
            cost_estimates,
            project_data
        )
        
        # الخطوة 7: إنشاء المشروع في قاعدة البيانات
        project = self._create_project_in_db(
            project_data,
            project_structure,
            cost_estimates,
            risk_analysis,
            schedule,
            user
        )
        
        # الخطوة 8: إنشاء الأنشطة والمهام
        activities = self._create_activities_and_tasks(
            project,
            project_structure,
            schedule,
            user
        )
        
        logger.info(f"تم إنشاء المشروع بنجاح: {project.name}")
        
        return {
            'success': True,
            'project': project.to_dict(),
            'analysis': {
                'bill_items_count': len(bill_items),
                'structure_levels': project_structure.get('levels', 0),
                'total_cost': cost_estimates.get('total_cost', 0),
                'estimated_duration': schedule.get('total_duration_days', 0),
                'risks_identified': len(risk_analysis.get('risks', [])),
                'critical_path_activities': schedule.get('critical_path_count', 0)
            },
            'recommendations': self._generate_recommendations(
                project_structure,
                cost_estimates,
                risk_analysis,
                schedule
            )
        }
    
    def _extract_bill_items(self, excel_data: Dict) -> List[Dict]:
        """استخراج بنود جدول الكميات من بيانات Excel"""
        bill_items = []
        
        # البحث عن جدول البنود
        for sheet_name, sheet_data in excel_data.get('sheets', {}).items():
            if any(keyword in sheet_name.lower() for keyword in ['كميات', 'بنود', 'جدول']):
                df = pd.DataFrame(sheet_data)
                
                # اكتشاف الأعمدة تلقائياً
                column_mapping = self._detect_columns(df)
                
                # معالجة كل صف
                for _, row in df.iterrows():
                    bill_item = self._create_bill_item_from_row(row, column_mapping)
                    if bill_item:
                        bill_items.append(bill_item)
        
        logger.info(f"تم استخراج {len(bill_items)} بند من جدول الكميات")
        return bill_items
    
    def _detect_columns(self, df: pd.DataFrame) -> Dict[str, str]:
        """اكتشاف أعمدة جدول الكميات تلقائياً"""
        column_mapping = {}
        
        # قائمة الأعمدة المتوقعة
        expected_columns = {
            'item_code': ['رقم البند', 'رمز البند', 'الكود', 'item', 'code'],
            'description': ['الوصف', 'مواصفات', 'description', 'specifications'],
            'unit': ['الوحدة', 'unit'],
            'quantity': ['الكمية', 'quantity', 'qty'],
            'unit_price': ['سعر الوحدة', 'سعر', 'unit price', 'rate'],
            'total_price': ['الإجمالي', 'المبلغ', 'total', 'amount'],
            'category': ['الفئة', 'نوع', 'category', 'type'],
            'notes': ['ملاحظات', 'notes', 'remarks']
        }
        
        # البحث عن الأعمدة في رؤوس الجدول
        df_columns = [str(col).strip().lower() for col in df.columns]
        
        for english_name, arabic_names in expected_columns.items():
            for arabic_name in arabic_names:
                arabic_lower = arabic_name.lower()
                for idx, col in enumerate(df_columns):
                    if arabic_lower in col:
                        column_mapping[english_name] = df.columns[idx]
                        break
                if english_name in column_mapping:
                    break
        
        return column_mapping
    
    def _create_bill_item_from_row(self, row, column_mapping: Dict) -> Optional[Dict]:
        """إنشاء بند من صف الجدول"""
        try:
            # استخراج البيانات من الصف
            item_code = str(row.get(column_mapping.get('item_code', ''), '')).strip()
            description = str(row.get(column_mapping.get('description', ''), '')).strip()
            
            # إذا لم يكن هناك وصف أو كود، نتخطى الصف
            if not description and not item_code:
                return None
            
            # استخراج البيانات الأخرى
            unit = str(row.get(column_mapping.get('unit', ''), '')).strip()
            quantity = self._parse_number(row.get(column_mapping.get('quantity', 0)))
            unit_price = self._parse_number(row.get(column_mapping.get('unit_price', 0)))
            total_price = self._parse_number(row.get(column_mapping.get('total_price', 0)))
            
            # إذا كان الإجمالي غير محسوب، نحسبه
            if total_price == 0 and quantity > 0 and unit_price > 0:
                total_price = quantity * unit_price
            
            bill_item = {
                'item_code': item_code,
                'description': description,
                'description_ar': description,  # نفس الوصف بالعربية
                'unit': unit or 'وحدة',
                'planned_quantity': float(quantity),
                'unit_price': float(unit_price),
                'planned_amount': float(total_price),
                'item_type': self._determine_item_type(item_code, description),
                'item_level': self._calculate_item_level(item_code),
                'category': str(row.get(column_mapping.get('category', ''), '')).strip(),
                'notes': str(row.get(column_mapping.get('notes', ''), '')).strip()
            }
            
            return bill_item
            
        except Exception as e:
            logger.warning(f"خطأ في معالجة صف البند: {e}")
            return None
    
    def _parse_number(self, value) -> float:
        """تحويل القيمة إلى عدد"""
        try:
            if pd.isna(value):
                return 0.0
            
            if isinstance(value, (int, float)):
                return float(value)
            
            # إزالة أي أحرف غير رقمية
            value_str = str(value).strip()
            value_str = ''.join(ch for ch in value_str if ch.isdigit() or ch in '.,-')
            
            # استبدال الفواصل بالنقاط
            value_str = value_str.replace(',', '.')
            
            # إذا كان هناك أكثر من نقطة، نأخذ الأولى
            if value_str.count('.') > 1:
                parts = value_str.split('.')
                value_str = '.'.join(parts[:-1]) + parts[-1]
            
            return float(value_str) if value_str else 0.0
            
        except:
            return 0.0
    
    def _determine_item_type(self, item_code: str, description: str) -> str:
        """تحديد نوع البند بناءً على الكود والوصف"""
        description_lower = description.lower()
        
        # تحليل الكود الهرمي
        if '.' in str(item_code):
            parts = str(item_code).split('.')
            if len(parts) >= 3:
                return 'sub_activity'
            elif len(parts) == 2:
                return 'activity'
            else:
                return 'main_item'
        
        # تحليل الوصف
        if any(word in description_lower for word in ['حفر', 'صب', 'تركيب', 'تشطيب']):
            return 'activity'
        elif any(word in description_lower for word in ['ملخص', 'إجمالي', 'مجموع']):
            return 'summary_item'
        else:
            return 'item'
    
    def _calculate_item_level(self, item_code: str) -> int:
        """حساب مستوى البند في الهيكل الهرمي"""
        if not item_code:
            return 1
        
        item_str = str(item_code)
        if '.' in item_str:
            return item_str.count('.') + 1
        else:
            return 1
    
    def _build_smart_hierarchy(self, bill_items: List[Dict], 
                              project_data: Dict) -> Dict[str, Any]:
        """بناء الهيكل الهرمي الذكي للمشروع"""
        logger.info("بناء الهيكل الهرمي الذكي للمشروع")
        
        # تجميع البنود حسب المستوى والنوع
        hierarchy = {
            'project_name': project_data.get('name', 'مشروع جديد'),
            'levels': {},
            'activities': [],
            'phases': [],
            'work_packages': []
        }
        
        # تجميع حسب المستوى
        for item in bill_items:
            level = item.get('item_level', 1)
            if level not in hierarchy['levels']:
                hierarchy['levels'][level] = []
            hierarchy['levels'][level].append(item)
            
            # تصنيف حسب النوع
            item_type = item.get('item_type', 'item')
            if item_type == 'activity':
                hierarchy['activities'].append(item)
            elif item_type == 'main_item':
                hierarchy['phases'].append(item)
            elif item_type == 'summary_item':
                hierarchy['work_packages'].append(item)
        
        # تنظيم البنود في هيكل هرمي
        hierarchy['structured_items'] = self._organize_hierarchical_items(bill_items)
        
        # حساب الإحصائيات
        hierarchy['statistics'] = {
            'total_items': len(bill_items),
            'levels_count': len(hierarchy['levels']),
            'activities_count': len(hierarchy['activities']),
            'phases_count': len(hierarchy['phases']),
            'work_packages_count': len(hierarchy['work_packages']),
            'total_amount': sum(item.get('planned_amount', 0) for item in bill_items)
        }
        
        logger.info(f"تم بناء هيكل هرمي بمستويات: {len(hierarchy['levels'])}")
        return hierarchy
    
    def _organize_hierarchical_items(self, bill_items: List[Dict]) -> List[Dict]:
        """تنظيم البنود في هيكل هرمي"""
        # فرز البنود حسب المستوى والكود
        sorted_items = sorted(bill_items, 
                            key=lambda x: (x.get('item_level', 1), 
                                         str(x.get('item_code', ''))))
        
        hierarchical_items = []
        parent_stack = []
        
        for item in sorted_items:
            current_level = item.get('item_level', 1)
            item_code = str(item.get('item_code', ''))
            
            # ضبط مكدس الوالدين
            while parent_stack and parent_stack[-1]['level'] >= current_level:
                parent_stack.pop()
            
            # تحديد الوالد
            parent_id = parent_stack[-1]['id'] if parent_stack else None
            
            # إضافة إلى القائمة الهرمية
            hierarchical_item = {
                'id': len(hierarchical_items),
                'item_code': item_code,
                'description': item.get('description', ''),
                'level': current_level,
                'parent_id': parent_id,
                'children': [],
                'data': item
            }
            
            hierarchical_items.append(hierarchical_item)
            
            # إضافة كوالد للمستويات التالية
            parent_stack.append({
                'id': hierarchical_item['id'],
                'level': current_level,
                'code': item_code
            })
        
        # بناء علاقات الأطفال
        for item in hierarchical_items:
            parent_id = item['parent_id']
            if parent_id is not None:
                hierarchical_items[parent_id]['children'].append(item['id'])
        
        return hierarchical_items
    
    def _create_project_in_db(self, project_data: Dict, structure: Dict,
                            costs: Dict, risks: Dict, schedule: Dict,
                            user: User) -> Project:
        """إنشاء المشروع في قاعدة البيانات"""
        from ..extensions import db
        
        try:
            # إنشاء كود المشروع
            project_code = self._generate_project_code(project_data.get('name'))
            
            # حساب التواريخ
            start_date = datetime.now().date()
            end_date = start_date + timedelta(days=schedule.get('total_duration_days', 365))
            
            # إنشاء المشروع
            project = Project(
                org_id=user.org_id,
                project_code=project_code,
                project_number=project_data.get('project_number', ''),
                name=project_data.get('name', 'مشروع جديد'),
                name_ar=project_data.get('name_ar', 'مشروع جديد'),
                description=project_data.get('description', ''),
                
                # إدارة المشروع
                project_manager_id=user.id,
                
                # معلومات الموقع
                site_name=project_data.get('site_name', ''),
                site_name_ar=project_data.get('site_name_ar', ''),
                location_address=project_data.get('location_address', ''),
                governorate=project_data.get('governorate', ''),
                city=project_data.get('city', ''),
                
                # القيم المالية
                contract_value=float(costs.get('total_cost', 0)),
                estimated_value=float(costs.get('total_cost', 0)),
                
                # الجدول الزمني
                planned_start_date=start_date,
                planned_end_date=end_date,
                planned_duration=schedule.get('total_duration_days', 365),
                
                # الحالة
                status='planning',
                priority=project_data.get('priority', 'medium'),
                complexity=self._determine_project_complexity(structure, costs),
                
                # التصنيفات
                project_type=project_data.get('project_type', 'بناء'),
                project_category=project_data.get('project_category', 'خاص'),
                project_scale=self._determine_project_scale(costs),
                
                # التحليل الذكي
                ai_analysis=json.dumps({
                    'cost_estimation': costs,
                    'risk_analysis': risks,
                    'schedule_optimization': schedule,
                    'structure_analysis': structure.get('statistics', {})
                }),
                
                # السجل الزمني
                created_by=user.id
            )
            
            db.session.add(project)
            db.session.commit()
            
            logger.info(f"تم إنشاء المشروع في قاعدة البيانات: {project.name}")
            return project
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"خطأ في إنشاء المشروع: {e}")
            raise
    
    def _generate_project_code(self, project_name: str) -> str:
        """توليد كود فريد للمشروع"""
        from datetime import datetime
        
        # أخذ أول ثلاثة أحرف من اسم المشروع
        name_part = ''.join([c for c in project_name[:3] if c.isalpha()]).upper()
        if not name_part:
            name_part = 'PRJ'
        
        # إضافة التاريخ
        date_part = datetime.now().strftime('%y%m%d')
        
        # إضافة رقم تسلسلي
        from ..models.project_models import Project
        from ..extensions import db
        
        today = datetime.now().date()
        count = Project.query.filter(
            db.func.date(Project.created_at) == today
        ).count() + 1
        
        serial_part = f"{count:03d}"
        
        return f"{name_part}-{date_part}-{serial_part}"
    
    def _determine_project_complexity(self, structure: Dict, costs: Dict) -> str:
        """تحديد تعقيد المشروع"""
        total_items = structure.get('statistics', {}).get('total_items', 0)
        total_cost = costs.get('total_cost', 0)
        
        if total_items > 100 or total_cost > 10000000:  # أكثر من 10 مليون
            return 'high'
        elif total_items > 50 or total_cost > 5000000:  # أكثر من 5 مليون
            return 'medium'
        else:
            return 'low'
    
    def _determine_project_scale(self, costs: Dict) -> str:
        """تحديد حجم المشروع"""
        total_cost = costs.get('total_cost', 0)
        
        if total_cost > 50000000:  # أكثر من 50 مليون
            return 'عملاق'
        elif total_cost > 10000000:  # أكثر من 10 مليون
            return 'كبير'
        elif total_cost > 1000000:   # أكثر من 1 مليون
            return 'متوسط'
        else:
            return 'صغير'
    
    def _create_activities_and_tasks(self, project: Project, structure: Dict,
                                   schedule: Dict, user: User) -> List[Activity]:
        """إنشاء الأنشطة والمهام تلقائياً"""
        from ..extensions import db
        
        activities = []
        
        # الحصول على الأنشطة من الهيكل
        for activity_data in structure.get('activities', []):
            try:
                # إنشاء النشاط
                activity = Activity(
                    project_id=project.id,
                    activity_code=activity_data.get('item_code', ''),
                    activity_name=activity_data.get('description', ''),
                    activity_name_ar=activity_data.get('description', ''),
                    
                    # التخطيط
                    planned_quantity=activity_data.get('planned_quantity', 0),
                    planned_cost=activity_data.get('planned_amount', 0),
                    
                    # التقدم
                    progress_percentage=0.0,
                    weight=self._calculate_activity_weight(activity_data, structure),
                    
                    # المسؤولية
                    supervisor_id=user.id,  # يمكن تعديله لاحقاً
                    
                    # الحالة
                    status='not_started',
                    priority=self._determine_activity_priority(activity_data),
                    
                    # التصنيف
                    activity_type=self._determine_activity_type(activity_data),
                    work_type=self._determine_work_type(activity_data)
                )
                
                db.session.add(activity)
                activities.append(activity)
                
                # إنشاء المهام للنشاط
                self._create_tasks_for_activity(activity, activity_data, user)
                
            except Exception as e:
                logger.error(f"خطأ في إنشاء النشاط: {e}")
                continue
        
        db.session.commit()
        logger.info(f"تم إنشاء {len(activities)} نشاط للمشروع {project.name}")
        
        return activities
    
    def _calculate_activity_weight(self, activity_data: Dict, structure: Dict) -> float:
        """حساب وزن النشاط النسبي"""
        total_amount = structure.get('statistics', {}).get('total_amount', 1)
        activity_amount = activity_data.get('planned_amount', 0)
        
        if total_amount > 0:
            return (activity_amount / total_amount) * 100
        else:
            return 1.0
    
    def _determine_activity_priority(self, activity_data: Dict) -> int:
        """تحديد أولوية النشاط"""
        description = activity_data.get('description', '').lower()
        
        if any(word in description for word in ['أساس', 'حفر', 'هيكل']):
            return 1  # عالية
        elif any(word in description for word in ['تشطيب', 'نهائي']):
            return 3  # متوسطة
        else:
            return 2  # متوسطة-عالية
    
    def _determine_activity_type(self, activity_data: Dict) -> str:
        """تحديد نوع النشاط"""
        description = activity_data.get('description', '').lower()
        
        if 'حفر' in description:
            return 'excavation'
        elif 'صب' in description:
            return 'concrete'
        elif 'تركيب' in description:
            return 'installation'
        elif 'تشطيب' in description:
            return 'finishing'
        else:
            return 'general'
    
    def _determine_work_type(self, activity_data: Dict) -> str:
        """تحديد نوع العمل"""
        description = activity_data.get('description', '').lower()
        
        if any(word in description for word in ['خرسانة', 'صب', 'قواعد']):
            return 'civil'
        elif any(word in description for word in ['كهرباء', 'إنارة']):
            return 'electrical'
        elif any(word in description for word in ['سباكة', 'صرف']):
            return 'plumbing'
        else:
            return 'general'
    
    def _create_tasks_for_activity(self, activity: Activity, activity_data: Dict,
                                 user: User):
        """إنشاء المهام للنشاط تلقائياً"""
        from ..extensions import db
        from ..models.project_models import Task
        
        description = activity_data.get('description', '')
        item_code = activity_data.get('item_code', '')
        
        # تقسيم النشاط إلى مهام بناءً على نوعه
        task_templates = self._get_task_templates_for_activity(activity_data)
        
        for i, template in enumerate(task_templates, 1):
            task_code = f"{item_code}.{i:02d}"
            
            task = Task(
                project_id=activity.project_id,
                activity_id=activity.id,
                task_code=task_code,
                task_name=template['name'],
                task_name_ar=template['name_ar'],
                description=template.get('description', ''),
                instructions=template.get('instructions', ''),
                
                # التسلسل
                task_order=i,
                
                # المسؤولية
                supervisor_id=user.id,
                
                # التقديرات
                planned_duration=template.get('duration_hours', 8),
                estimated_effort=template.get('effort_hours', 8),
                
                # الموارد
                required_skills=template.get('required_skills', []),
                required_materials=template.get('required_materials', []),
                
                # الحالة
                status='pending',
                
                # السجل
                created_by=user.id
            )
            
            db.session.add(task)
    
    def _get_task_templates_for_activity(self, activity_data: Dict) -> List[Dict]:
        """الحصول على قوالب المهام للنشاط"""
        activity_type = self._determine_activity_type(activity_data)
        
        templates = {
            'excavation': [
                {
                    'name': 'Site Survey and Marking',
                    'name_ar': 'مسح وتحديد الموقع',
                    'description': 'Survey the site and mark excavation boundaries',
                    'instructions': '1. Review site plans\n2. Mark boundaries with stakes\n3. Verify measurements',
                    'duration_hours': 4,
                    'effort_hours': 4,
                    'required_skills': ['surveying', 'measurement'],
                    'required_materials': ['stakes', 'string', 'measuring tape']
                },
                {
                    'name': 'Excavation Work',
                    'name_ar': 'أعمال الحفر',
                    'description': 'Excavate according to specifications',
                    'instructions': '1. Start excavation\n2. Monitor depth\n3. Check for obstacles',
                    'duration_hours': 16,
                    'effort_hours': 24,
                    'required_skills': ['excavation', 'heavy_equipment'],
                    'required_materials': ['excavator', 'shovels', 'safety_cones']
                }
            ],
            'concrete': [
                {
                    'name': 'Formwork Installation',
                    'name_ar': 'تركيب القوالب',
                    'description': 'Install formwork for concrete pouring',
                    'instructions': '1. Assemble formwork\n2. Secure in place\n3. Check alignment',
                    'duration_hours': 8,
                    'effort_hours': 12,
                    'required_skills': ['carpentry', 'measurement'],
                    'required_materials': ['plywood', 'nails', 'bracing']
                },
                {
                    'name': 'Concrete Pouring',
                    'name_ar': 'صب الخرسانة',
                    'description': 'Pour and level concrete',
                    'instructions': '1. Prepare concrete mix\n2. Pour evenly\n3. Level surface',
                    'duration_hours': 6,
                    'effort_hours': 8,
                    'required_skills': ['concrete_work', 'finishing'],
                    'required_materials': ['concrete', 'vibrator', 'float']
                }
            ],
            'general': [
                {
                    'name': 'Activity Preparation',
                    'name_ar': 'تحضير النشاط',
                    'description': 'Prepare for activity execution',
                    'instructions': '1. Gather materials\n2. Review specifications\n3. Prepare work area',
                    'duration_hours': 2,
                    'effort_hours': 2,
                    'required_skills': ['planning', 'organization'],
                    'required_materials': []
                },
                {
                    'name': 'Activity Execution',
                    'name_ar': 'تنفيذ النشاط',
                    'description': 'Execute the main activity work',
                    'instructions': '1. Follow work procedures\n2. Maintain quality standards\n3. Document progress',
                    'duration_hours': 8,
                    'effort_hours': 8,
                    'required_skills': ['execution', 'quality_control'],
                    'required_materials': []
                }
            ]
        }
        
        return templates.get(activity_type, templates['general'])
    
    def _generate_recommendations(self, structure: Dict, costs: Dict,
                                risks: Dict, schedule: Dict) -> List[Dict]:
        """توليد توصيات ذكية للمشروع"""
        recommendations = []
        
        # توصيات بناءً على الهيكل
        if structure.get('statistics', {}).get('activities_count', 0) > 20:
            recommendations.append({
                'type': 'structure',
                'priority': 'medium',
                'title': 'تقسيم المشروع إلى مراحل',
                'description': 'عدد الأنشطة كبير، يفضل تقسيم المشروع إلى مراحل أصغر',
                'action': 'split_project_into_phases'
            })
        
        # توصيات بناءً على التكاليف
        total_cost = costs.get('total_cost', 0)
        if total_cost > 10000000:  # أكثر من 10 مليون
            recommendations.append({
                'type': 'cost',
                'priority': 'high',
                'title': 'مراجعة الميزانية',
                'description': 'المشروع كبير التكلفة، يفضل مراجعة البنود الرئيسية',
                'action': 'review_major_cost_items'
            })
        
        # توصيات بناءً على المخاطر
        high_risks = [r for r in risks.get('risks', []) 
                     if r.get('risk_level') == 'high']
        if len(high_risks) > 5:
            recommendations.append({
                'type': 'risk',
                'priority': 'critical',
                'title': 'معالجة المخاطر العالية',
                'description': f'يوجد {len(high_risks)} مخاطر عالية تحتاج معالجة فورية',
                'action': 'address_high_risks'
            })
        
        # توصيات بناءً على الجدول الزمني
        if schedule.get('total_duration_days', 0) > 365:
            recommendations.append({
                'type': 'schedule',
                'priority': 'medium',
                'title': 'ضغط الجدول الزمني',
                'description': 'مدة المشروع طويلة، يمكن تحسين الجدول الزمني',
                'action': 'optimize_schedule'
            })
        
        return recommendations
"""
ai_extractor.py - نظام استخراج البيانات الذكي من الملفات
يدعم استخراج بيانات المشاريع والمهام من أي نوع ملف
"""
import os
import re
import json
import PyPDF2
import docx
import pandas as pd
from PIL import Image
# import pytesseract
from werkzeug.utils import secure_filename
from datetime import datetime, date,timedelta
import openai
from flask import current_app
import logging


class AIExtractor:
    """محرك استخراج البيانات الذكي"""
    
    def __init__(self, app=None):
        self.app = app
        self.supported_extensions = {
            'pdf': self.extract_from_pdf,
            'docx': self.extract_from_docx,
            'doc': self.extract_from_docx,
            'xlsx': self.extract_from_excel,
            'xls': self.extract_from_excel,
            'csv': self.extract_from_csv,
            'txt': self.extract_from_text
            # 'jpg': self.extract_from_image,
            # 'jpeg': self.extract_from_image,
            # 'png': self.extract_from_image
        }
        
        # تهيئة OpenAI API إذا كان متاحاً
        self.openai_api_key = os.environ.get('OPENAI_API_KEY')
        if self.openai_api_key:
            openai.api_key = self.openai_api_key
        
    def extract_data(self, file_path, file_type=None):
        """
        استخراج البيانات من الملف بناءً على نوعه
        
        Args:
            file_path: مسار الملف
            file_type: نوع الملف (اختياري)
            
        Returns:
            dict: البيانات المستخرجة
        """
        try:
            # تحديد نوع الملف
            if not file_type:
                file_type = file_path.split('.')[-1].lower()
            
            # اختيار دالة الاستخراج المناسبة
            extractor = self.supported_extensions.get(file_type)
            if not extractor:
                return {'error': f'نوع الملف {file_type} غير مدعوم'}
            
            # استخراج النص الخام
            raw_text = extractor(file_path)
            
            if not raw_text:
                return {'error': 'لم يتم استخراج أي نص من الملف'}
            
            # تحليل النص واستخراج البيانات المنظمة
            structured_data = self.analyze_with_ai(raw_text)
            
            return {
                'success': True,
                'raw_text': raw_text[:1000] + '...' if len(raw_text) > 1000 else raw_text,
                'structured_data': structured_data,
                'file_type': file_type,
                'file_size': os.path.getsize(file_path)
            }
            
        except Exception as e:
            current_app.logger.error(f"خطأ في استخراج البيانات: {str(e)}")
            return {'error': str(e)}
    
    # ============================================
    # دوال استخراج النص من أنواع الملفات المختلفة
    # ============================================
    
    def extract_from_pdf(self, file_path):
        """استخراج النص من ملف PDF"""
        try:
            text = ""
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
            return text
        except Exception as e:
            current_app.logger.error(f"خطأ في استخراج PDF: {str(e)}")
            return ""
    
    def extract_from_docx(self, file_path):
        """استخراج النص من ملف Word"""
        try:
            doc = docx.Document(file_path)
            text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
            return text
        except Exception as e:
            current_app.logger.error(f"خطأ في استخراج Word: {str(e)}")
            return ""
    
    def extract_from_excel(self, file_path):
        """استخراج النص من ملف Excel"""
        try:
            df = pd.read_excel(file_path)
            text = df.to_string(index=False)
            return text
        except Exception as e:
            current_app.logger.error(f"خطأ في استخراج Excel: {str(e)}")
            return ""
    
    def extract_from_csv(self, file_path):
        """استخراج النص من ملف CSV"""
        try:
            df = pd.read_csv(file_path)
            text = df.to_string(index=False)
            return text
        except Exception as e:
            current_app.logger.error(f"خطأ في استخراج CSV: {str(e)}")
            return ""
    
    def extract_from_text(self, file_path):
        """استخراج النص من ملف نصي"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except UnicodeDecodeError:
            # محاولة بترميز مختلف
            with open(file_path, 'r', encoding='cp1256') as file:
                return file.read()
        except Exception as e:
            current_app.logger.error(f"خطأ في استخراج نص: {str(e)}")
            return ""
    
    # def extract_from_image(self, file_path):
    #     """استخراج النص من صورة باستخدام OCR"""
    #     try:
    #         image = Image.open(file_path)
    #         text = pytesseract.image_to_string(image, lang='ara+eng')
    #         return text
    #     except Exception as e:
    #         current_app.logger.error(f"خطأ في استخراج من صورة: {str(e)}")
    #         return ""
    
    # ============================================
    # تحليل النص باستخدام الذكاء الاصطناعي
    # ============================================
    
    def analyze_with_ai(self, text):
        """
        تحليل النص واستخراج البيانات المنظمة باستخدام الذكاء الاصطناعي
        
        يدعم:
        - استخراج معلومات المشروع (الاسم، الرمز، الوصف، التاريخ، القيمة)
        - استخراج المهام (الاسم، الوصف، المسؤول، التاريخ، المدة)
        - استخراج العلاقات والتبعيات بين المهام
        - استخراج الموارد المطلوبة
        """
        
        # محاولة استخدام OpenAI API إذا كان متاحاً
        if self.openai_api_key:
            return self._analyze_with_openai(text)
        else:
            # استخدام الطرق التقليدية إذا لم يتوفر OpenAI
            return self._analyze_with_regex(text)
    
    def _analyze_with_openai(self, text):
        """تحليل النص باستخدام OpenAI GPT"""
        try:
            # تقطيع النص الطويل
            if len(text) > 10000:
                text = text[:10000]
            
            prompt = f"""
            أنا بحاجة لاستخراج معلومات مشروع ومهام من النص التالي. 
            النص قد يكون غير منظم وقد يكون بالعربية أو الإنجليزية أو خليطاً.
            
            النص:
            {text}
            
            الرجاء استخراج المعلومات التالية بصيغة JSON:
            
            1. معلومات المشروع:
               - project_name: اسم المشروع
               - project_code: رمز المشروع (إذا وجد)
               - description: وصف المشروع
               - start_date: تاريخ البدء (YYYY-MM-DD)
               - end_date: تاريخ الانتهاء (YYYY-MM-DD)
               - budget: الميزانية أو قيمة العقد
               - client: اسم العميل
               - location: موقع المشروع
            
            2. المهام (tasks):
               قائمة من المهام، كل مهمة تحتوي على:
               - task_name: اسم المهمة
               - description: وصف المهمة
               - assigned_to: المسؤول عن المهمة
               - start_date: تاريخ بدء المهمة
               - end_date: تاريخ انتهاء المهمة
               - duration: المدة المتوقعة (بالأيام)
               - depends_on: المهام التي تعتمد عليها هذه المهمة
               - priority: الأولوية (high/medium/low)
               - resources: الموارد المطلوبة (قائمة)
            
            3. الموارد العامة:
               - materials: المواد المطلوبة
               - equipment: المعدات المطلوبة
               - skills: المهارات المطلوبة
            
            قم بإرجاع JSON صالح فقط، بدون أي نص إضافي.
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "أنت مساعد ذكي لاستخراج بيانات المشاريع."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            result = response.choices[0].message.content
            
            # استخراج JSON من النص
            json_match = re.search(r'\{.*\}', result, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return {"error": "لم يتم العثور على JSON في استجابة OpenAI"}
                
        except Exception as e:
            current_app.logger.error(f"خطأ في OpenAI: {str(e)}")
            return self._analyze_with_regex(text)
    
    def _analyze_with_regex(self, text):
        """تحليل النص باستخدام الأنماط النصية (Regex)"""
        
        result = {
            'project': {},
            'tasks': [],
            'resources': {}
        }
        
        # البحث عن اسم المشروع
        project_patterns = [
            r'(?:اسم المشروع|Project Name)[:\s]+([^\n]+)',
            r'(?:مشروع|Project)[:\s]+([^\n]+)',
            r'^([^\n]{5,50})$'  # أي سطر طويل قد يكون اسم المشروع
        ]
        
        for pattern in project_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                result['project']['name'] = match.group(1).strip()
                break
        
        # البحث عن رمز المشروع
        code_patterns = [
            r'(?:رمز|Code|رقم|Number)[:\s]+([A-Z0-9\-_]+)',
            r'(?:PRJ|PROJ)[\-_]?(\d+)',
            r'\b([A-Z]{2,5}[-_]?\d+)\b'
        ]
        
        for pattern in code_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['project']['code'] = match.group(1).strip()
                break
        
        # البحث عن التواريخ
        date_patterns = [
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
            r'(\d{1,2}\s+\w+\s+\d{4})'  # 15 يناير 2024
        ]
        
        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            dates.extend(matches)
        
        if len(dates) >= 2:
            result['project']['start_date'] = dates[0]
            result['project']['end_date'] = dates[-1]
        
        # البحث عن الميزانية
        budget_patterns = [
            r'(?:ميزانية|Budget|قيمة|Value)[:\s]+([\d,]+)',
            r'([\d,]+)\s*(?:ر\.س|SAR|ريال)',
            r'([\d,]+)\s*(?:دولار|USD)'
        ]
        
        for pattern in budget_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                budget_str = match.group(1).replace(',', '')
                try:
                    result['project']['budget'] = float(budget_str)
                except:
                    result['project']['budget'] = budget_str
                break
        
        # البحث عن المهام
        task_lines = []
        lines = text.split('\n')
        task_keywords = ['مهمة', 'Task', 'نشاط', 'Activity', 'عمل', 'Work']
        
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in task_keywords):
                task_lines.append((i, line))
        
        for idx, line in task_lines[:10]:  # حد أقصى 10 مهام
            task = {
                'name': line.strip(),
                'description': '',
                'assigned_to': '',
                'duration': 1
            }
            
            # البحث عن وصف المهمة في الأسطر التالية
            if idx + 1 < len(lines):
                task['description'] = lines[idx + 1].strip()[:100]
            
            result['tasks'].append(task)
        
        return result


class ProjectCreator:
    """فئة إنشاء المشاريع والمهام من البيانات المستخرجة"""
    
    def __init__(self):
        from app.models import db, Project, Task, User, Department
    
    def create_from_extracted_data(self, extracted_data, org_id, created_by_id):
        """
        إنشاء مشروع ومهام من البيانات المستخرجة
        
        Args:
            extracted_data: البيانات المستخرجة من الملف
            org_id: معرف المؤسسة
            created_by_id: معرف منشئ المشروع
            
        Returns:
            dict: نتيجة الإنشاء مع المشروع والمهام المنشأة
        """
        from app.models import db, Project, Task, User
        from datetime import datetime
        
        try:
            structured = extracted_data.get('structured_data', {})
            project_info = structured.get('project', {})
            tasks_info = structured.get('tasks', [])
            
            # ============================================
            # إنشاء المشروع
            # ============================================
            
            # إنشاء رمز المشروع إذا لم يكن موجوداً
            project_code = project_info.get('code')
            if not project_code:
                import random
                import string
                project_code = f"AI-{datetime.now().strftime('%Y%m%d')}-{random.randint(100, 999)}"
            
            # تحويل التاريخ
            start_date = None
            end_date = None
            
            if project_info.get('start_date'):
                try:
                    start_date = self._parse_date(project_info['start_date'])
                except:
                    start_date = datetime.now().date()
            
            if project_info.get('end_date'):
                try:
                    end_date = self._parse_date(project_info['end_date'])
                except:
                    end_date = datetime.now().date() + timedelta(days=30)
            
            # إنشاء المشروع
            project = Project(
                org_id=org_id,
                project_code=project_code,
                name=project_info.get('name', f'مشروع {datetime.now().strftime("%Y-%m-%d")}'),
                description=project_info.get('description', 'تم إنشاؤه تلقائياً من رفع ملف'),
                planned_start_date=start_date,
                planned_end_date=end_date,
                contract_value=project_info.get('budget', 0.0),
                site_name=project_info.get('location', ''),
                status='planning',
                created_by=created_by_id,
                project_manager_id=created_by_id  # المدير الافتراضي هو المنشئ
            )
            
            db.session.add(project)
            db.session.flush()  # للحصول على ID المشروع
            
            # ============================================
            # إنشاء المهام
            # ============================================
            
            created_tasks = []
            task_order = 1
            
            for task_info in tasks_info:
                # تحديد المسؤول عن المهمة (افتراضياً المنشئ)
                responsible_id = created_by_id
                
                # البحث عن مستخدم بنفس الاسم إذا وجد
                if task_info.get('assigned_to'):
                    user = User.query.filter(
                        User.org_id == org_id,
                        User.full_name.contains(task_info['assigned_to'])
                    ).first()
                    if user:
                        responsible_id = user.id
                
                # إنشاء المهمة
                task = Task(
                    project_id=project.id,
                    task_code=f"{project_code}-T{task_order:03d}",
                    task_name=task_info.get('name', f'مهمة {task_order}'),
                    description=task_info.get('description', ''),
                    task_order=task_order,
                    supervisor_id=responsible_id,
                    planned_start_date=self._parse_date(task_info.get('start_date')) if task_info.get('start_date') else start_date,
                    planned_end_date=self._parse_date(task_info.get('end_date')) if task_info.get('end_date') else end_date,
                    planned_duration=task_info.get('duration', 1),
                    status='pending',
                    created_by=created_by_id
                )
                
                db.session.add(task)
                created_tasks.append(task)
                task_order += 1
            
            db.session.commit()
            
            return {
                'success': True,
                'project': project,
                'tasks': created_tasks,
                'message': f'تم إنشاء المشروع {project.name} و {len(created_tasks)} مهام بنجاح'
            }
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"خطأ في إنشاء المشروع: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _parse_date(self, date_str):
        """تحويل النص إلى تاريخ"""
        from dateutil import parser
        try:
            return parser.parse(date_str).date()
        except:
            return datetime.now().date()
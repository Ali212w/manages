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
            أنا بحاجة لاستخراج معلومات مشروع متكاملة وهيكل تقسيم العمل (WBS) والأنشطة والمهام والعلاقات والموارد من النص التالي.
            النص قد يكون غير منظم وقد يكون بالعربية أو الإنجليزية أو خليطاً.
            
            النص:
            {text}
            
            الرجاء استخراج المعلومات التالية بصيغة JSON فقط:
            
            {{
              "project": {{
                "project_name": "اسم المشروع (مثال: مشروع إنشاء مجمع سكني)",
                "project_code": "رمز المشروع (إذا وجد، أو اتركه فارغاً ليتم توليده)",
                "description": "وصف المشروع بالتفصيل",
                "start_date": "تاريخ البدء المتوقع بصيغة YYYY-MM-DD",
                "end_date": "تاريخ الانتهاء المتوقع بصيغة YYYY-MM-DD",
                "budget": 150000.0,
                "client": "اسم المالك أو العميل",
                "location": "موقع المشروع (مثال: الرياض، حي الملقا)"
              }},
              "wbs_phases": [
                "قائمة بأسماء مراحل المشروع أو هيكل تقسيم العمل (مثل: التصميم والهندسة، التوريدات، الأعمال المدنية، التشطيبات)"
              ],
              "tasks": [
                {{
                  "name": "اسم النشاط/المهمة (مثال: حفر الموقع وتجهيز الأرضيات)",
                  "description": "وصف النشاط بالتفصيل والتعليمات الخاصة به",
                  "wbs_phase": "اسم مرحلة الـ WBS التي ينتمي إليها هذا النشاط (يجب أن يكون مطابقاً لأحد الأسماء في قائمة wbs_phases)",
                  "assigned_to": "المسؤول عن التنفيذ (مثال: المهندس أحمد)",
                  "start_date": "تاريخ بدء النشاط بصيغة YYYY-MM-DD",
                  "end_date": "تاريخ انتهاء النشاط بصيغة YYYY-MM-DD",
                  "duration": 5,
                  "priority": "الأولوية (high, medium, low)",
                  "depends_on": ["أسماء أو أكواد الأنشطة التي يعتمد عليها هذا النشاط للبدء"],
                  "resources": [
                    {{
                      "name": "اسم المورد المطلوب (مثال: حديد تسليح، خلاطة خرسانة، عمالة ماهرة)",
                      "type": "نوع المورد (labor, material, equipment)",
                      "quantity": 10.0,
                      "unit": "الوحدة (طن، ساعة، يوم، إلخ)",
                      "cost_per_unit": 350.0
                    }}
                  ]
                }}
              ]
            }}
            
            قم بإرجاع JSON صالح فقط، بدون أي نص إضافي أو علامات markdown خارج الـ JSON.
            """
            
            # التحقق من إصدار OpenAI ودعم كلتا الصياغتين (القديمة والحديثة)
            if hasattr(openai, 'ChatCompletion'):
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
            else:
                from openai import OpenAI
                client = OpenAI(api_key=self.openai_api_key)
                response = client.chat.completions.create(
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
                parsed_data = json.loads(json_match.group())
                # توافقية المفاتيح مع upload_routes.py
                if 'project' in parsed_data:
                    p = parsed_data['project']
                    if 'project_name' in p and 'name' not in p:
                        p['name'] = p['project_name']
                    if 'project_code' in p and 'code' not in p:
                        p['code'] = p['project_code']
                return parsed_data
            else:
                return {"error": "لم يتم العثور على JSON في استجابة OpenAI"}
                
        except Exception as e:
            current_app.logger.error(f"خطأ في OpenAI: {str(e)}")
            return self._analyze_with_regex(text)
    
    def _analyze_with_regex(self, text):
        """تحليل النص باستخدام الأنماط النصية (Regex)"""
        result = {
            'project': {
                'project_name': '',
                'name': '',
                'project_code': '',
                'code': '',
                'description': 'تم استخراج المشروع تلقائياً عبر تحليل النص',
                'start_date': None,
                'end_date': None,
                'budget': 0.0,
                'client': '',
                'location': ''
            },
            'wbs_phases': ['الأعمال العامة'],
            'tasks': []
        }
        
        # البحث عن اسم المشروع
        project_patterns = [
            r'(?:اسم المشروع|Project Name)[:\s]+([^\n]+)',
            r'(?:مشروع|Project)[:\s]+([^\n]+)',
        ]
        for pattern in project_patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                val = match.group(1).strip()
                result['project']['project_name'] = val
                result['project']['name'] = val
                break
        
        if not result['project']['project_name']:
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if lines:
                val = lines[0][:100]
                result['project']['project_name'] = val
                result['project']['name'] = val
                
        # البحث عن رمز المشروع
        code_patterns = [
            r'(?:رمز|Code|رقم|Number)[:\s]+([A-Za-z0-9\-_]+)',
            r'\b([A-Z]{2,5}[-_]?\d+)\b'
        ]
        for pattern in code_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                result['project']['project_code'] = val
                result['project']['code'] = val
                break
                
        # البحث عن التواريخ
        date_patterns = [
            r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
            r'(\d{1,2}[-/]\d{1,2}[-/]\d{4})',
        ]
        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text)
            if matches:
                dates.extend(matches)
        
        if len(dates) >= 2:
            result['project']['start_date'] = dates[0]
            result['project']['end_date'] = dates[-1]
            
        # البحث عن الميزانية
        budget_patterns = [
            r'(?:ميزانية|Budget|قيمة|Value|تكلفة|Cost)[:\s]+([\d,]+)',
            r'([\d,]+)\s*(?:ر\.س|SAR|ريال|USD|\$)'
        ]
        for pattern in budget_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                budget_str = match.group(1).replace(',', '')
                try:
                    result['project']['budget'] = float(budget_str)
                    break
                except:
                    pass
                    
        # البحث عن العميل والموقع
        client_match = re.search(r'(?:المالك|العميل|Client|Owner)[:\s]+([^\n]+)', text, re.IGNORECASE)
        if client_match:
            result['project']['client'] = client_match.group(1).strip()
            
        location_match = re.search(r'(?:الموقع|موقع|Location|Site)[:\s]+([^\n]+)', text, re.IGNORECASE)
        if location_match:
            result['project']['location'] = location_match.group(1).strip()
            
        # استخراج المهام بشكل أذكى
        lines = text.split('\n')
        task_keywords = ['مهمة', 'Task', 'نشاط', 'Activity', 'عمل', 'Work', 'البند', 'Item', 'فاز', 'Phase']
        
        task_list = []
        for idx, line in enumerate(lines):
            line_str = line.strip()
            if not line_str:
                continue
                
            is_task = False
            if re.match(r'^(\d+[\.\-\u0640]*|[\-\*\u2022])\s+', line_str):
                is_task = True
            elif any(keyword in line_str for keyword in task_keywords):
                is_task = True
                
            if is_task:
                clean_name = re.sub(r'^(\d+[\.\-\u0640]*|[\-\*\u2022])\s+', '', line_str).strip()
                if len(clean_name) > 3:
                    duration = 5  # افتراضي
                    dur_match = re.search(r'(?:المدة|مدة|Duration)[:\s]+(\d+)\s*(?:يوم|أيام|Days|Day)', line_str, re.IGNORECASE)
                    if not dur_match:
                        dur_match = re.search(r'(\d+)\s*(?:يوم|أيام|Days|Day)', line_str, re.IGNORECASE)
                    if dur_match:
                        try:
                            duration = int(dur_match.group(1))
                        except:
                            pass
                            
                    task_item = {
                        'name': clean_name[:150],
                        'description': '',
                        'wbs_phase': 'الأعمال العامة',
                        'assigned_to': '',
                        'duration': duration,
                        'priority': 'medium',
                        'depends_on': [],
                        'resources': []
                    }
                    
                    desc_lines = []
                    next_idx = idx + 1
                    while next_idx < len(lines):
                        next_line = lines[next_idx].strip()
                        if not next_line:
                            next_idx += 1
                            continue
                        if re.match(r'^(\d+[\.\-\u0640]*|[\-\*\u2022])\s+', next_line) or any(keyword in next_line for keyword in task_keywords):
                            break
                        desc_lines.append(next_line)
                        next_idx += 1
                        if len(desc_lines) >= 2:
                            break
                    if desc_lines:
                        task_item['description'] = " \n".join(desc_lines)[:500]
                        
                    task_list.append(task_item)
                    
        if not task_list:
            non_empty_lines = [l.strip() for l in lines if len(l.strip()) > 10]
            for i, line in enumerate(non_empty_lines[1:11]):
                task_list.append({
                    'name': line[:100],
                    'description': line,
                    'wbs_phase': 'الأعمال العامة',
                    'assigned_to': '',
                    'duration': 5,
                    'priority': 'medium',
                    'depends_on': [],
                    'resources': []
                })
                
        result['tasks'] = task_list
        return result


class ProjectCreator:
    """فئة إنشاء المشاريع والمهام من البيانات المستخرجة"""
    
    def __init__(self):
        pass
    
    def create_from_extracted_data(self, extracted_data, org_id, created_by_id):
        """
        إنشاء مشروع متكامل والمهام التابعة له من البيانات المستخرجة
        
        Args:
            extracted_data: البيانات المستخرجة من الملف
            org_id: معرف المؤسسة
            created_by_id: معرف منشئ المشروع
            
        Returns:
            dict: نتيجة الإنشاء مع المشروع والمهام المنشأة
        """
        from app.models import (
            db, Project, Task, User, EPS, Calendar, WBS, Activity,
            ActivityRelationship, TaskPlanning, TaskProgress, TaskExecution,
            TaskLocation, TaskVerification, Resource, ActivityResource, TaskDependency,
            ProjectLocation, ProjectDates, ProjectBudget, ProjectCost,
            ProjectPerformance, ProjectProgress, ProjectStatistics
        )
        from datetime import datetime, timedelta, date, time
        import random
        import string

        try:
            structured = extracted_data.get('structured_data', {})
            project_info = structured.get('project', {})
            tasks_info = structured.get('tasks', [])
            wbs_phases_info = structured.get('wbs_phases', [])

            # ============================================
            # 1. حل وتحديد الـ EPS الافتراضي
            # ============================================
            eps = EPS.query.filter_by(org_id=org_id).first()
            if not eps:
                eps = EPS(
                    org_id=org_id,
                    eps_code="EPS-GEN",
                    name="المشاريع العامة",
                    description="هيكل تقسيم المشاريع الافتراضي التابع للنظام",
                    level=1
                )
                db.session.add(eps)
                db.session.flush()

            # ============================================
            # 2. حل وتحديد التقويم الافتراضي
            # ============================================
            calendar = Calendar.query.filter_by(org_id=org_id).first()
            if not calendar:
                calendar = Calendar(
                    org_id=org_id,
                    name="التقويم القياسي",
                    calendar_type="global",
                    work_days=[1, 2, 3, 4, 5, 6],
                    work_hours_per_day=8.0,
                    work_start=time(8, 0),
                    work_end=time(17, 0)
                )
                db.session.add(calendar)
                db.session.flush()

            # ============================================
            # 3. إنشاء رمز المشروع وإعداد التواريخ
            # ============================================
            project_code = project_info.get('project_code') or project_info.get('code')
            if not project_code:
                random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
                project_code = f"PRJ-{datetime.now().strftime('%Y%m%d')}-{random_suffix}"
            
            # التأكد من أن رمز المشروع فريد عالمياً لمنع أخطاء IntegrityError
            base_code = project_code
            counter = 1
            while Project.query.filter_by(project_code=project_code).first():
                project_code = f"{base_code}-{counter}"
                counter += 1

            start_date = None
            end_date = None

            if project_info.get('start_date'):
                try:
                    start_date = self._parse_date(project_info['start_date'])
                except:
                    start_date = datetime.now().date()
            else:
                start_date = datetime.now().date()

            if project_info.get('end_date'):
                try:
                    end_date = self._parse_date(project_info['end_date'])
                except:
                    end_date = start_date + timedelta(days=30)
            else:
                end_date = start_date + timedelta(days=30)

            # ============================================
            # 4. إنشاء الكيان الرئيسي للمشروع
            # ============================================
            project = Project(
                org_id=org_id,
                project_code=project_code,
                name=project_info.get('project_name') or project_info.get('name') or f'مشروع {datetime.now().strftime("%Y-%m-%d")}',
                description=project_info.get('description', 'تم إنشاؤه تلقائياً من تحليل ملف'),
                eps_id=eps.id,
                calendar_id=calendar.id,
                status='planning',
                created_by=created_by_id,
                project_manager_id=created_by_id
            )
            db.session.add(project)
            db.session.flush() # الحصول على ID المشروع

            # ============================================
            # 5. إنشاء الجداول الفرعية التابعة للمشروع لمنع أخطاء NoneType
            # ============================================
            start_dt = datetime.combine(start_date, datetime.min.time())
            end_dt = datetime.combine(end_date, datetime.min.time())

            p_dates = ProjectDates(
                project_id=project.id,
                planned_start=start_dt,
                planned_finish=end_dt
            )
            db.session.add(p_dates)

            budget_val = 0.0
            if project_info.get('budget'):
                try:
                    budget_val = float(project_info['budget'])
                except:
                    pass

            p_budget = ProjectBudget(
                project_id=project.id,
                original_budget=budget_val,
                current_budget=budget_val
            )
            db.session.add(p_budget)

            p_location = ProjectLocation(
                project_id=project.id,
                site_name=project_info.get('location', '')
            )
            db.session.add(p_location)

            # تكاليف وإحصائيات فارغة
            db.session.add(ProjectCost(project_id=project.id))
            db.session.add(ProjectPerformance(project_id=project.id))
            db.session.add(ProjectProgress(project_id=project.id))
            db.session.add(ProjectStatistics(project_id=project.id))

            db.session.flush()

            # ============================================
            # 6. إنشاء مراحل هيكل تقسيم العمل (WBS)
            # ============================================
            phases = set()
            if wbs_phases_info:
                for phase in wbs_phases_info:
                    if phase and isinstance(phase, str):
                        phases.add(phase.strip())
            
            for t_info in tasks_info:
                p_name = t_info.get('wbs_phase')
                if p_name and isinstance(p_name, str):
                    phases.add(p_name.strip())

            if not phases:
                phases.add("الأعمال العامة")

            wbs_map = {}
            wbs_index = 1
            for phase_name in sorted(phases):
                wbs_code = f"{project_code}-WBS-{wbs_index:02d}"
                wbs_node = WBS(
                    project_id=project.id,
                    wbs_code=wbs_code,
                    name=phase_name,
                    description=f"مرحلة {phase_name}",
                    level=1,
                    wbs_path=str(wbs_index)
                )
                db.session.add(wbs_node)
                db.session.flush()
                wbs_map[phase_name] = wbs_node
                wbs_index += 1

            # ============================================
            # 7. إنشاء الأنشطة والمهام والموارد
            # ============================================
            created_tasks = []
            created_activities = []
            
            activity_map = {}
            task_map = {}
            task_order = 1
            
            for task_info in tasks_info:
                t_name = task_info.get('name') or task_info.get('task_name')
                if not t_name:
                    continue
                t_name = t_name.strip()

                phase_name = task_info.get('wbs_phase', '').strip()
                wbs_node = wbs_map.get(phase_name) or list(wbs_map.values())[0]

                t_start = start_date
                t_end = end_date
                t_duration = task_info.get('duration') or 1
                try:
                    t_duration = float(t_duration)
                except:
                    t_duration = 1.0

                if task_info.get('start_date'):
                    try:
                        t_start = self._parse_date(task_info['start_date'])
                    except:
                        pass
                
                if task_info.get('end_date'):
                    try:
                        t_end = self._parse_date(task_info['end_date'])
                    except:
                        t_end = t_start + timedelta(days=int(t_duration))
                else:
                    t_end = t_start + timedelta(days=int(t_duration))

                responsible_id = created_by_id
                if task_info.get('assigned_to'):
                    user = User.query.filter(
                        User.org_id == org_id,
                        User.full_name.contains(task_info['assigned_to'])
                    ).first()
                    if user:
                        responsible_id = user.id

                # أ. إنشاء النشاط
                act_code = f"ACT-{task_order:04d}"
                activity = Activity(
                    project_id=project.id,
                    wbs_id=wbs_node.id,
                    calendar_id=calendar.id,
                    activity_id=act_code,
                    activity_name=t_name[:500],
                    description=task_info.get('description', ''),
                    original_duration=t_duration,
                    remaining_duration=t_duration,
                    planned_start=datetime.combine(t_start, datetime.min.time()),
                    planned_finish=datetime.combine(t_end, datetime.min.time()),
                    status='not_started',
                    priority=3,
                    responsible_id=responsible_id,
                    supervisor_id=responsible_id
                )
                db.session.add(activity)
                db.session.flush()
                
                activity_map[t_name] = activity
                created_activities.append(activity)

                # ب. إنشاء المهمة
                task = Task(
                    project_id=project.id,
                    activity_id=activity.id,
                    wbs_id=wbs_node.id,
                    task_code=f"{project_code}-T{task_order:03d}",
                    task_name=t_name[:500],
                    description=task_info.get('description', ''),
                    task_order=task_order,
                    supervisor_id=responsible_id,
                    status='pending',
                    priority=3,
                    created_by=created_by_id
                )
                db.session.add(task)
                db.session.flush()
                
                task_map[t_name] = task
                created_tasks.append(task)

                # ج. إنشاء الجداول الفرعية للمهمة
                t_planning = TaskPlanning(
                    task_id=task.id,
                    planned_start=t_start,
                    planned_finish=t_end,
                    planned_duration=t_duration * 8.0
                )
                db.session.add(t_planning)
                db.session.add(TaskProgress(task_id=task.id))
                db.session.add(TaskExecution(task_id=task.id))

                # د. الموارد
                resources_info = task_info.get('resources', [])
                if resources_info:
                    for res_info in resources_info:
                        if not res_info or not isinstance(res_info, dict):
                            continue
                        res_name = res_info.get('name')
                        if not res_name:
                            continue
                        res_name = res_name.strip()
                        res_type = res_info.get('type', 'labor')
                        if res_type not in ['labor', 'material', 'equipment', 'non_labor']:
                            res_type = 'labor'
                        
                        resource = Resource.query.filter_by(org_id=org_id, name=res_name).first()
                        if not resource:
                            res_id = f"RES-{res_type.upper()[:3]}-{random.randint(1000, 9999)}"
                            resource = Resource(
                                org_id=org_id,
                                resource_id=res_id,
                                name=res_name,
                                resource_type=res_type,
                                cost_per_unit=float(res_info.get('cost_per_unit', 0.0) or 0.0),
                                unit=res_info.get('unit', 'ساعة') if res_type == 'labor' else res_info.get('unit', 'وحدة'),
                                available_quantity=float(res_info.get('quantity', 1.0) or 1.0)
                            )
                            db.session.add(resource)
                            db.session.flush()

                        act_res = ActivityResource(
                            activity_id=activity.id,
                            resource_id=resource.id,
                            planned_quantity=float(res_info.get('quantity', 1.0) or 1.0)
                        )
                        db.session.add(act_res)

                task_order += 1

            db.session.flush()

            # ============================================
            # 8. حل العلاقات والاعتماديات
            # ============================================
            for task_info in tasks_info:
                t_name = task_info.get('name') or task_info.get('task_name')
                if not t_name:
                    continue
                t_name = t_name.strip()
                
                depends_on = task_info.get('depends_on')
                if not depends_on:
                    continue
                
                if isinstance(depends_on, str):
                    depends_on = [depends_on]
                
                current_activity = activity_map.get(t_name)
                current_task = task_map.get(t_name)
                
                if not current_activity or not current_task:
                    continue
                    
                for dep_name in depends_on:
                    if not dep_name:
                        continue
                    dep_name = dep_name.strip()
                    
                    predecessor_activity = activity_map.get(dep_name)
                    predecessor_task = task_map.get(dep_name)
                    
                    if predecessor_activity:
                        rel = ActivityRelationship(
                            project_id=project.id,
                            predecessor_id=predecessor_activity.id,
                            successor_id=current_activity.id,
                            relationship_type='FS',
                            lag_days=0.0
                        )
                        db.session.add(rel)
                        
                    if predecessor_task:
                        task_dep = TaskDependency(
                            project_id=project.id,
                            predecessor_task_id=predecessor_task.id,
                            successor_task_id=current_task.id,
                            dependency_type='FS',
                            lag=0.0
                        )
                        db.session.add(task_dep)
                        
                        if not current_task.depends_on_task_id:
                            current_task.depends_on_task_id = predecessor_task.id

            db.session.commit()

            return {
                'success': True,
                'project': project,
                'tasks': created_tasks,
                'message': f'تم إنشاء المشروع {project.name} و {len(created_tasks)} مهام بنجاح من التحليل الذكي'
            }

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"خطأ في إنشاء المشروع من التحليل: {str(e)}")
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
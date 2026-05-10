"""
ai_integration.py - ربط الذكاء الاصطناعي مع جميع نماذج النظام
"""

from flask import current_app
from app.models import db
from app.models.core_models import Organization, User, Department
from app.models import (
    EPS, WBS, Calendar, Resource,
    Project, ActivityRelationship, ActivityResource,
    EPSOBSAssignment
)
from app.models.enterprise_models import Role, ResourceCode, ActivityCode, UDF, OBS
from app.models.project_models import Project,  Activity, Client, Consultant, Supplier
from app.models.task_models import Task, TaskAssignment, TaskRequirement, DailyReport
from app.models.ai_models import (
    AICommand, AICommandResult, AIReport, AISuggestion
)
from app.models.document_models import BillItem
from datetime import datetime, date
import json
import re

class AIIntegration:
    """
    ربط الذكاء الاصطناعي مع جميع نماذج النظام
    """
    
    def __init__(self, org_id, user_id):
        self.org_id = org_id
        self.user_id = user_id
        self.organization = Organization.query.get(org_id)
        self.user = User.query.get(user_id)
    
    # ============================================
    # 🏢 ربط مع Core Models
    # ============================================
    
    def process_organization_command(self, command_text, entities):
        """معالجة أوامر المؤسسة"""
        result = {
            'model': 'Organization',
            'action': None,
            'data': [],
            'count': 0
        }
        
        # تحديث إعدادات المؤسسة
        if 'إعدادات' in command_text or 'settings' in command_text:
            settings = {}
            
            # استخراج الإعدادات الجديدة
            if 'الحد الأقصى للمستخدمين' in command_text:
                value = self.extract_number(command_text)
                if value:
                    self.organization.max_users = value
                    settings['max_users'] = value
            
            if 'الحد الأقصى للمشاريع' in command_text:
                value = self.extract_number(command_text)
                if value:
                    self.organization.max_projects = value
                    settings['max_projects'] = value
            
            if 'تخزين' in command_text and 'جيجابايت' in command_text:
                value = self.extract_number(command_text)
                if value:
                    self.organization.storage_limit_mb = value * 1024
                    settings['storage_gb'] = value
            
            db.session.commit()
            result['action'] = 'update_settings'
            result['data'] = settings
            result['count'] = 1
        
        return result
    
    def process_department_command(self, command_text, entities):
        """معالجة أوامر الأقسام"""
        result = {
            'model': 'Department',
            'action': None,
            'data': [],
            'count': 0
        }
        
        # إنشاء قسم جديد
        if 'قسم' in command_text and ('إنشاء' in command_text or 'إضافة' in command_text):
            dept_name = self.extract_name(command_text, 'قسم')
            dept_code = self.generate_dept_code(dept_name)
            
            # استخراج المدير
            manager_name = self.extract_name(command_text, 'مدير')
            manager = None
            if manager_name:
                manager = User.query.filter_by(
                    org_id=self.org_id,
                    full_name=manager_name
                ).first()
            
            # استخراج القسم الأب
            parent_name = self.extract_name(command_text, 'تحت')
            parent = None
            if parent_name:
                parent = Department.query.filter_by(
                    org_id=self.org_id,
                    name=parent_name
                ).first()
            
            department = Department(
                org_id=self.org_id,
                dept_code=dept_code,
                name=dept_name,
                name_ar=dept_name,
                parent_id=parent.id if parent else None,
                manager_id=manager.id if manager else None,
                budget=self.extract_number(command_text, 'ميزانية')
            )
            db.session.add(department)
            db.session.commit()
            
            result['action'] = 'create'
            result['data'].append({
                'id': department.id,
                'code': department.dept_code,
                'name': department.name,
                'manager': manager.full_name if manager else None
            })
            result['count'] = 1
        
        return result
    
    # ============================================
    # 📊 ربط مع Primavera Models
    # ============================================
    
    def process_eps_command(self, command_text, entities, attachments=None):
        """معالجة أوامر EPS"""
        result = {
            'model': 'EPS',
            'action': None,
            'data': [],
            'count': 0
        }
        
        # إنشاء EPS من ملف Excel
        if attachments and ('eps' in command_text or 'هيكل' in command_text):
            for attachment in attachments:
                if attachment.file_type in ['xlsx', 'xls']:
                    eps_data = self.extract_eps_from_excel(attachment.extracted_data)
                    
                    for item in eps_data:
                        # البحث عن العنصر الأب
                        parent = None
                        if item.get('parent_code'):
                            parent = EPS.query.filter_by(
                                org_id=self.org_id,
                                eps_code=item['parent_code']
                            ).first()
                        
                        eps = EPS(
                            org_id=self.org_id,
                            eps_code=item['code'],
                            name=item['name'],
                            name_ar=item.get('name_ar', item['name']),
                            description=item.get('description'),
                            parent_id=parent.id if parent else None,
                            level=(parent.level + 1) if parent else 1,
                            path=f"{parent.path}/{item['code']}" if parent else item['code'],
                            manager_id=self.find_manager_id(item.get('manager'))
                        )
                        db.session.add(eps)
                        result['count'] += 1
                    
                    db.session.commit()
                    result['action'] = 'create_bulk'
        
        # إنشاء EPS واحد
        elif 'eps' in command_text and ('إنشاء' in command_text or 'إضافة' in command_text):
            eps_name = self.extract_name(command_text, 'eps')
            eps_code = self.generate_eps_code(eps_name)
            
            # استخراج العنصر الأب
            parent_name = self.extract_name(command_text, 'تحت')
            parent = None
            if parent_name:
                parent = EPS.query.filter_by(
                    org_id=self.org_id,
                    name=parent_name
                ).first()
            
            # استخراج المدير
            manager_name = self.extract_name(command_text, 'مدير')
            manager = None
            if manager_name:
                manager = User.query.filter_by(
                    org_id=self.org_id,
                    full_name=manager_name
                ).first()
            
            eps = EPS(
                org_id=self.org_id,
                eps_code=eps_code,
                name=eps_name,
                parent_id=parent.id if parent else None,
                level=(parent.level + 1) if parent else 1,
                path=f"{parent.path}/{eps_code}" if parent else eps_code,
                manager_id=manager.id if manager else None
            )
            db.session.add(eps)
            db.session.commit()
            
            result['action'] = 'create'
            result['data'].append({
                'id': eps.id,
                'code': eps.eps_code,
                'name': eps.name,
                'level': eps.level,
                'path': eps.path
            })
            result['count'] = 1
        
        return result
    
    def process_obs_command(self, command_text, entities, attachments=None):
        """معالجة أوامر OBS"""
        result = {
            'model': 'OBS',
            'action': None,
            'data': [],
            'count': 0
        }
        
        if 'obs' in command_text and ('إنشاء' in command_text or 'إضافة' in command_text):
            obs_name = self.extract_name(command_text, 'obs')
            obs_code = self.generate_obs_code(obs_name)
            
            # استخراج المسؤول
            responsible_name = self.extract_name(command_text, 'مسؤول')
            responsible = None
            if responsible_name:
                responsible = User.query.filter_by(
                    org_id=self.org_id,
                    full_name=responsible_name
                ).first()
            
            obs = OBS(
                org_id=self.org_id,
                obs_code=obs_code,
                name=obs_name,
                responsible_id=responsible.id if responsible else None,
                level=1
            )
            db.session.add(obs)
            db.session.commit()
            
            result['action'] = 'create'
            result['data'].append({
                'id': obs.id,
                'code': obs.obs_code,
                'name': obs.name,
                'responsible': responsible.full_name if responsible else None
            })
            result['count'] = 1
        
        return result
    
    def process_calendar_command(self, command_text, entities):
        """معالجة أوامر التقويمات"""
        result = {
            'model': 'Calendar',
            'action': None,
            'data': [],
            'count': 0
        }
        
        if 'تقويم' in command_text and ('إنشاء' in command_text or 'إضافة' in command_text):
            calendar_name = self.extract_name(command_text, 'تقويم')
            
            # استخراج أيام العمل
            work_days = [1, 2, 3, 4, 5, 6]  # افتراضي: السبت - الخميس
            if 'أيام العمل' in command_text:
                days_text = self.extract_between(command_text, 'أيام العمل', 'ساعات')
                work_days = self.parse_work_days(days_text)
            
            # استخراج ساعات العمل
            work_hours = self.extract_number(command_text, 'ساعات')
            if not work_hours:
                work_hours = 8
            
            calendar = Calendar(
                org_id=self.org_id,
                name=calendar_name,
                calendar_type='project',
                work_days=work_days,
                work_hours_per_day=work_hours,
                is_default='افتراضي' in command_text
            )
            db.session.add(calendar)
            db.session.commit()
            
            result['action'] = 'create'
            result['data'].append({
                'id': calendar.id,
                'name': calendar.name,
                'work_days': work_days,
                'hours_per_day': work_hours
            })
            result['count'] = 1
        
        return result
    
    # ============================================
    # 👥 ربط مع User Models
    # ============================================
    
    def process_user_command(self, command_text, entities, attachments=None):
        """معالجة أوامر المستخدمين"""
        result = {
            'model': 'User',
            'action': None,
            'data': [],
            'count': 0
        }
        
        # استيراد مستخدمين من Excel
        if attachments and ('مستخدم' in command_text or 'user' in command_text):
            for attachment in attachments:
                if attachment.file_type in ['xlsx', 'xls']:
                    users_data = self.extract_users_from_excel(attachment.extracted_data)
                    
                    for user_info in users_data:
                        # التحقق من عدم التكرار
                        existing = User.query.filter_by(
                            org_id=self.org_id,
                            email=user_info['email']
                        ).first()
                        
                        if not existing:
                            user = self.create_user_from_data(user_info)
                            if user:
                                result['count'] += 1
                                result['data'].append({
                                    'id': user.id,
                                    'name': user.full_name,
                                    'email': user.email,
                                    'role': user.role
                                })
                    
                    db.session.commit()
                    result['action'] = 'import_bulk'
        
        # إنشاء مستخدم واحد
        elif 'مستخدم' in command_text and ('إنشاء' in command_text or 'إضافة' in command_text):
            user_info = self.extract_user_info(command_text)
            user = self.create_user_from_data(user_info)
            
            if user:
                result['action'] = 'create'
                result['data'].append({
                    'id': user.id,
                    'name': user.full_name,
                    'email': user.email,
                    'role': user.role,
                    'password': user_info.get('password', 'Welcome@123')
                })
                result['count'] = 1
        
        # تحديث مستخدم
        elif 'تحديث' in command_text or 'تعديل' in command_text:
            user_id = self.extract_user_id(command_text)
            if user_id:
                user = User.query.get(user_id)
                if user and user.org_id == self.org_id:
                    updates = {}
                    
                    if 'دور' in command_text or 'role' in command_text:
                        new_role = self.extract_role(command_text)
                        if new_role:
                            user.role = new_role
                            updates['role'] = new_role
                    
                    if 'قسم' in command_text:
                        dept_name = self.extract_name(command_text, 'قسم')
                        dept = Department.query.filter_by(
                            org_id=self.org_id,
                            name=dept_name
                        ).first()
                        if dept:
                            user.dept_id = dept.id
                            updates['department'] = dept.name
                    
                    db.session.commit()
                    result['action'] = 'update'
                    result['data'].append(updates)
                    result['count'] = 1
        
        # تعطيل/تفعيل مستخدم
        elif 'تعطيل' in command_text:
            user_id = self.extract_user_id(command_text)
            if user_id:
                user = User.query.get(user_id)
                if user:
                    user.is_user_active = False
                    db.session.commit()
                    result['action'] = 'disable'
                    result['data'].append({'id': user.id, 'status': 'disabled'})
                    result['count'] = 1
        
        return result
    
    def process_role_command(self, command_text, entities):
        """معالجة أوامر الأدوار الوظيفية"""
        result = {
            'model': 'Role',
            'action': None,
            'data': [],
            'count': 0
        }
        
        if 'دور' in command_text and ('إنشاء' in command_text or 'إضافة' in command_text):
            role_name = self.extract_name(command_text, 'دور')
            role_code = self.generate_role_code(role_name)
            
            # استخراج التكلفة
            cost = self.extract_number(command_text, 'تكلفة')
            
            # استخراج المهارات
            skills_text = self.extract_between(command_text, 'مهارات', '')
            skills = [s.strip() for s in skills_text.split(',')] if skills_text else []
            
            role = Role(
                org_id=self.org_id,
                role_code=role_code,
                name=role_name,
                default_cost_per_hour=cost or 0,
                required_skills=skills
            )
            db.session.add(role)
            db.session.commit()
            
            result['action'] = 'create'
            result['data'].append({
                'id': role.id,
                'code': role.role_code,
                'name': role.name,
                'cost': cost
            })
            result['count'] = 1
        
        return result
    
    # ============================================
    # 📋 ربط مع Project Models
    # ============================================
    
    def process_project_command(self, command_text, entities, attachments=None):
        """معالجة أوامر المشاريع"""
        result = {
            'model': 'Project',
            'action': None,
            'data': [],
            'count': 0
        }
        
        # استيراد مشاريع من Excel
        if attachments and ('مشروع' in command_text or 'project' in command_text):
            for attachment in attachments:
                if attachment.file_type in ['xlsx', 'xls']:
                    projects_data = self.extract_projects_from_excel(attachment.extracted_data)
                    
                    for proj_info in projects_data:
                        project = self.create_project_from_data(proj_info)
                        if project:
                            result['count'] += 1
                            result['data'].append({
                                'id': project.id,
                                'name': project.name,
                                'code': project.project_code,
                                'value': project.contract_value
                            })
                    
                    db.session.commit()
                    result['action'] = 'import_bulk'
        
        # إنشاء مشروع واحد
        elif 'مشروع' in command_text and ('إنشاء' in command_text or 'إضافة' in command_text):
            proj_info = self.extract_project_info(command_text)
            project = self.create_project_from_data(proj_info)
            
            if project:
                result['action'] = 'create'
                result['data'].append({
                    'id': project.id,
                    'name': project.name,
                    'code': project.project_code,
                    'value': project.contract_value,
                    'start': project.planned_start_date,
                    'end': project.planned_end_date
                })
                result['count'] = 1
        
        return result
    
    def process_boq_command(self, command_text, entities, attachments=None):
        """معالجة أوامر جداول الكميات"""
        result = {
            'model': 'BillItem',
            'action': None,
            'data': [],
            'count': 0
        }
        
        # استيراد جدول كميات من Excel
        if attachments and ('جدول' in command_text or 'boq' in command_text):
            project_id = self.extract_project_id(command_text)
            
            if project_id:
                for attachment in attachments:
                    if attachment.file_type in ['xlsx', 'xls']:
                        boq_data = self.extract_boq_from_excel(attachment.extracted_data)
                        
                        for item in boq_data:
                            bill_item = BillItem(
                                project_id=project_id,
                                item_code=item['code'],
                                description=item['description'],
                                description_ar=item.get('description_ar', item['description']),
                                unit=item.get('unit', 'each'),
                                quantity=item['quantity'],
                                unit_price=item['unit_price'],
                                total_price=item['quantity'] * item['unit_price'],
                                created_by=self.user_id
                            )
                            db.session.add(bill_item)
                            result['count'] += 1
                        
                        db.session.commit()
                        result['action'] = 'import_boq'
                        result['data'] = boq_data[:10]  # أول 10 عناصر
        
        return result
    
    # ============================================
    # 📊 ربط مع Task Models
    # ============================================
    
    def process_task_command(self, command_text, entities, attachments=None):
        """معالجة أوامر المهام"""
        result = {
            'model': 'Task',
            'action': None,
            'data': [],
            'count': 0
        }
        
        # استيراد مهام من Excel
        if attachments and ('مهم' in command_text or 'task' in command_text):
            project_id = self.extract_project_id(command_text)
            
            if project_id:
                for attachment in attachments:
                    if attachment.file_type in ['xlsx', 'xls']:
                        tasks_data = self.extract_tasks_from_excel(attachment.extracted_data)
                        
                        for task_info in tasks_data:
                            task = self.create_task_from_data(task_info, project_id)
                            if task:
                                result['count'] += 1
                                result['data'].append({
                                    'id': task.id,
                                    'code': task.task_code,
                                    'name': task.task_name
                                })
                        
                        db.session.commit()
                        result['action'] = 'import_tasks'
        
        # تكليف مهام
        elif 'وزع' in command_text or 'assign' in command_text:
            project_id = self.extract_project_id(command_text)
            if project_id:
                # استخراج المهام والمستخدمين
                tasks = self.extract_tasks_from_text(command_text)
                users = self.extract_users_from_text(command_text)
                
                assignments = self.distribute_tasks(tasks, users, project_id)
                
                result['action'] = 'assign'
                result['data'] = assignments
                result['count'] = len(assignments)
        
        return result
    
    # ============================================
    # 🔄 ربط مع العلاقات والصلاحيات
    # ============================================
    
    def process_permission_command(self, command_text, entities):
        """معالجة أوامر الصلاحيات"""
        result = {
            'model': 'EPSOBSAssignment',
            'action': None,
            'data': [],
            'count': 0
        }
        
        if 'صلاحية' in command_text:
            user_name = self.extract_name(command_text, 'لمستخدم')
            eps_name = self.extract_name(command_text, 'على EPS')
            obs_name = self.extract_name(command_text, 'OBS')
            level = self.extract_permission_level(command_text)
            
            user = User.query.filter_by(org_id=self.org_id, full_name=user_name).first()
            eps = EPS.query.filter_by(org_id=self.org_id, name=eps_name).first()
            obs = OBS.query.filter_by(org_id=self.org_id, name=obs_name).first()
            
            if user and eps and obs:
                # إنشاء أو تحديث الصلاحية
                assignment = EPSOBSAssignment.query.filter_by(
                    eps_id=eps.id,
                    obs_id=obs.id
                ).first()
                
                if not assignment:
                    assignment = EPSOBSAssignment(
                        eps_id=eps.id,
                        obs_id=obs.id,
                        permission_level=level,
                        created_by=self.user_id
                    )
                    db.session.add(assignment)
                else:
                    assignment.permission_level = level
                
                db.session.commit()
                
                result['action'] = 'set_permission'
                result['data'].append({
                    'user': user_name,
                    'eps': eps_name,
                    'obs': obs_name,
                    'level': level
                })
                result['count'] = 1
        
        return result
    
    # ============================================
    # 📈 ربط مع التقارير والتحليلات
    # ============================================
    
    def generate_report(self, command_text, entities):
        """توليد تقرير من البيانات"""
        result = {
            'type': 'report',
            'data': {},
            'summary': ''
        }
        
        # تقرير المشاريع
        if 'مشروع' in command_text or 'projects' in command_text:
            projects = PrimaveraProject.query.filter_by(org_id=self.org_id).all()
            
            report_data = {
                'total_projects': len(projects),
                'by_status': {},
                'total_value': sum(p.total_planned_cost or 0 for p in projects),
                'projects': []
            }
            
            for p in projects:
                status = p.status or 'unknown'
                report_data['by_status'][status] = report_data['by_status'].get(status, 0) + 1
                
                report_data['projects'].append({
                    'name': p.name,
                    'status': p.status,
                    'progress': p.progress_percentage,
                    'value': p.total_planned_cost
                })
            
            report_data['summary'] = f"إجمالي {len(projects)} مشروع بقيمة {report_data['total_value']:,.2f} ريال"
            
            result['data'] = report_data
            result['summary'] = report_data['summary']
        
        # تقرير المستخدمين
        elif 'مستخدم' in command_text or 'users' in command_text:
            users = User.query.filter_by(org_id=self.org_id).all()
            
            report_data = {
                'total_users': len(users),
                'by_role': {},
                'active_users': 0,
                'users': []
            }
            
            for u in users:
                report_data['by_role'][u.role] = report_data['by_role'].get(u.role, 0) + 1
                if u.is_user_active:
                    report_data['active_users'] += 1
                
                report_data['users'].append({
                    'name': u.full_name,
                    'role': u.role,
                    'email': u.email,
                    'active': u.is_user_active
                })
            
            result['data'] = report_data
            result['summary'] = f"إجمالي {len(users)} مستخدم، {report_data['active_users']} نشط"
        
        # تقرير المهام
        elif 'مهم' in command_text or 'tasks' in command_text:
            tasks = Task.query.join(Project).filter(Project.org_id == self.org_id).all()
            
            report_data = {
                'total_tasks': len(tasks),
                'by_status': {},
                'completed': 0,
                'delayed': 0,
                'tasks': []
            }
            
            today = date.today()
            
            for t in tasks:
                report_data['by_status'][t.status] = report_data['by_status'].get(t.status, 0) + 1
                
                if t.status == 'completed':
                    report_data['completed'] += 1
                
                if t.status != 'completed' and t.planned_end_date and t.planned_end_date < today:
                    report_data['delayed'] += 1
                
                report_data['tasks'].append({
                    'name': t.task_name,
                    'status': t.status,
                    'progress': t.progress_percentage,
                    'due_date': t.planned_end_date,
                    'project': t.project.name if t.project else None
                })
            
            result['data'] = report_data
            result['summary'] = f"إجمالي {len(tasks)} مهمة، {report_data['completed']} مكتملة، {report_data['delayed']} متأخرة"
        
        # حفظ التقرير
        report = AIReport(
            org_id=self.org_id,
            created_by=self.user_id,
            report_name=f"تقرير {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            report_type='executive',
            report_data=result['data'],
            report_summary=result['summary'],
            total_records=result['data'].get('total_projects') or result['data'].get('total_users') or result['data'].get('total_tasks', 0)
        )
        db.session.add(report)
        db.session.commit()
        
        return result
    
    # ============================================
    # 🛠️ دوال مساعدة
    # ============================================
    
    def extract_number(self, text, keyword=None):
        """استخراج رقم من النص"""
        if keyword:
            pattern = f'{keyword}[\s:]*(\d+(?:\.\d+)?)'
            match = re.search(pattern, text)
            if match:
                return float(match.group(1))
        
        # أي رقم في النص
        match = re.search(r'(\d+(?:\.\d+)?)', text)
        return float(match.group(1)) if match else None
    
    def extract_name(self, text, keyword):
        """استخراج اسم بعد كلمة معينة"""
        patterns = [
            f'{keyword}[\s:]+["\']?([^"\']+)["\']?',
            f'{keyword}[\s:]+([^\s،,]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None
    
    def extract_between(self, text, start, end):
        """استخراج نص بين كلمتين"""
        pattern = f'{start}[\s:]+(.*?)(?:{end}|$)'
        match = re.search(pattern, text)
        return match.group(1).strip() if match else None
    
    def generate_eps_code(self, name):
        """توليد كود EPS"""
        prefix = ''.join(word[0].upper() for word in name.split()[:2])
        count = EPS.query.filter_by(org_id=self.org_id).count() + 1
        return f"{prefix}{count:03d}"
    
    def generate_dept_code(self, name):
        """توليد كود قسم"""
        prefix = name[:3].upper()
        count = Department.query.filter_by(org_id=self.org_id).count() + 1
        return f"{prefix}{count:03d}"
    
    def generate_role_code(self, name):
        """توليد كود دور"""
        prefix = name[:3].upper()
        count = Role.query.filter_by(org_id=self.org_id).count() + 1
        return f"R{count:03d}"
    
    def create_user_from_data(self, data):
        """إنشاء مستخدم من البيانات المستخرجة"""
        # التحقق من وجود البريد
        if User.query.filter_by(org_id=self.org_id, email=data['email']).first():
            return None
        
        # البحث عن القسم
        dept = None
        if data.get('department'):
            dept = Department.query.filter_by(
                org_id=self.org_id,
                name=data['department']
            ).first()
        
        user = User(
            org_id=self.org_id,
            username=data['email'].split('@')[0],
            email=data['email'],
            full_name=data.get('name', data['email'].split('@')[0]),
            full_name_ar=data.get('name_ar'),
            phone=data.get('phone'),
            mobile=data.get('mobile'),
            job_title=data.get('job_title'),
            role=data.get('role', 'employee'),
            dept_id=dept.id if dept else None,
            is_user_active=True,
            created_by=self.user_id
        )
        
        # تعيين كلمة مرور افتراضية
        default_password = data.get('password', 'Welcome@123')
        user.set_password(default_password)
        
        db.session.add(user)
        db.session.flush()
        
        return user
    
    def create_project_from_data(self, data):
        """إنشاء مشروع من البيانات المستخرجة"""
        # البحث عن EPS
        eps = None
        if data.get('eps'):
            eps = EPS.query.filter_by(
                org_id=self.org_id,
                name=data['eps']
            ).first()
        
        if not eps:
            eps = EPS.query.filter_by(org_id=self.org_id).first()
        
        project = PrimaveraProject(
            org_id=self.org_id,
            eps_id=eps.id if eps else None,
            name=data.get('name', 'مشروع جديد'),
            project_code=self.generate_project_code(data.get('name')),
            description=data.get('description'),
            planned_start=data.get('start_date'),
            planned_finish=data.get('end_date'),
            total_planned_cost=data.get('budget', 0),
            status='planning',
            created_by=self.user_id
        )
        
        db.session.add(project)
        db.session.flush()
        
        return project
    
    def generate_project_code(self, name):
        """توليد كود مشروع"""
        prefix = 'PRJ'
        count = PrimaveraProject.query.filter_by(org_id=self.org_id).count() + 1
        return f"{prefix}{count:04d}"
    
    def create_task_from_data(self, data, project_id):
        """إنشاء مهمة من البيانات المستخرجة"""
        # البحث عن المستخدم المسؤول
        user = None
        if data.get('assigned_to'):
            user = User.query.filter_by(
                org_id=self.org_id,
                full_name=data['assigned_to']
            ).first()
        
        task = Task(
            project_id=project_id,
            task_code=data.get('code', f"T{datetime.now().strftime('%Y%m%d%H%M%S')}"),
            task_name=data.get('name', 'مهمة جديدة'),
            description=data.get('description'),
            task_order=data.get('order', 1),
            supervisor_id=user.id if user else self.user_id,
            delegate_id=user.id if user else None,
            planned_start_date=data.get('start_date'),
            planned_end_date=data.get('end_date'),
            planned_duration=data.get('duration'),
            status='pending',
            created_by=self.user_id
        )
        
        db.session.add(task)
        db.session.flush()
        
        return task
    
    def extract_users_from_excel(self, data):
        """استخراج المستخدمين من Excel"""
        users = []
        
        if data and 'tables' in data:
            for table in data['tables']:
                for row in table:
                    user = {
                        'name': row.get('الاسم') or row.get('name'),
                        'email': row.get('البريد') or row.get('email'),
                        'phone': row.get('الهاتف') or row.get('phone'),
                        'role': row.get('الدور') or row.get('role'),
                        'department': row.get('القسم') or row.get('department')
                    }
                    if user['email']:
                        users.append(user)
        
        return users
    
    def extract_projects_from_excel(self, data):
        """استخراج المشاريع من Excel"""
        projects = []
        
        if data and 'tables' in data:
            for table in data['tables']:
                for row in table:
                    project = {
                        'name': row.get('اسم المشروع') or row.get('project'),
                        'code': row.get('الكود') or row.get('code'),
                        'budget': float(row.get('الميزانية', 0)) if row.get('الميزانية') else 0,
                        'start_date': row.get('تاريخ البدء'),
                        'end_date': row.get('تاريخ الانتهاء'),
                        'eps': row.get('EPS')
                    }
                    if project['name']:
                        projects.append(project)
        
        return projects
    
    def extract_eps_from_excel(self, data):
        """استخراج EPS من Excel"""
        eps_items = []
        
        if data and 'tables' in data:
            for table in data['tables']:
                for row in table:
                    item = {
                        'code': row.get('الكود') or row.get('code'),
                        'name': row.get('الاسم') or row.get('name'),
                        'parent_code': row.get('الأب') or row.get('parent'),
                        'manager': row.get('المدير') or row.get('manager')
                    }
                    if item['code'] and item['name']:
                        eps_items.append(item)
        
        return eps_items
    
    def extract_boq_from_excel(self, data):
        """استخراج جدول كميات من Excel"""
        boq_items = []
        
        if data and 'tables' in data:
            for table in data['tables']:
                for row in table:
                    item = {
                        'code': row.get('البند') or row.get('code'),
                        'description': row.get('البيان') or row.get('description'),
                        'unit': row.get('الوحدة') or row.get('unit'),
                        'quantity': float(row.get('الكمية', 0)) if row.get('الكمية') else 0,
                        'unit_price': float(row.get('سعر الوحدة', 0)) if row.get('سعر الوحدة') else 0
                    }
                    if item['code'] and item['description']:
                        boq_items.append(item)
        
        return boq_items
    
    def extract_tasks_from_excel(self, data):
        """استخراج المهام من Excel"""
        tasks = []
        
        if data and 'tables' in data:
            for table in data['tables']:
                for row in table:
                    task = {
                        'code': row.get('الكود') or row.get('code'),
                        'name': row.get('المهمة') or row.get('task'),
                        'description': row.get('الوصف') or row.get('description'),
                        'assigned_to': row.get('المسؤول') or row.get('assigned'),
                        'duration': float(row.get('المدة', 0)) if row.get('المدة') else 0,
                        'start_date': row.get('تاريخ البدء'),
                        'end_date': row.get('تاريخ الانتهاء')
                    }
                    if task['name']:
                        tasks.append(task)
        
        return tasks
    
    def extract_permission_level(self, text):
        """استخراج مستوى الصلاحية"""
        if 'قراءة فقط' in text or 'read' in text:
            return 'read'
        elif 'كتابة' in text or 'write' in text:
            return 'write'
        elif 'admin' in text or 'مدير' in text:
            return 'admin'
        return 'read'
    
    def find_manager_id(self, manager_name):
        """البحث عن معرف المدير"""
        if manager_name:
            user = User.query.filter_by(
                org_id=self.org_id,
                full_name=manager_name
            ).first()
            return user.id if user else None
        return None
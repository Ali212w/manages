"""
ai_service_extended.py - خدمات الذكاء الاصطناعي المتقدمة لإدارة المؤسسة
"""
from app.models import *
from app.services.notification_service import NotificationService
from datetime import datetime
from app.models.primavera_models import EPSOBSAssignment
from app.models.task_models import TaskAssignment
import re
class CommandProcessor:
    """معالج الأوامر الموسع ليشمل جميع جوانب المؤسسة"""
    
    # ============================================
    # 🏢 إدارة هيكل المؤسسة (EPS - Enterprise Project Structure)
    # ============================================
    
    @staticmethod
    def handle_eps_commands(command, analysis, user, org_id):
        """معالجة أوامر EPS"""
        result = {
            'type': 'eps',
            'action': analysis['intent'],
            'count': 0,
            'data': []
        }
        
        text = command.command_text.lower()
        
        # إنشاء EPS جديد
        if analysis['intent'] == 'create' and ('eps' in text or 'هيكل' in text):
            eps_name = CommandProcessor.extract_eps_name(text)
            eps_code = CommandProcessor.generate_eps_code(eps_name)
            
            # استخراج المعلومات الإضافية
            parent_eps = CommandProcessor.extract_parent_eps(text, org_id)
            manager_id = CommandProcessor.extract_manager(text, org_id)
            
            eps = EPS(
                org_id=org_id,
                eps_code=eps_code,
                name=eps_name,
                name_ar=eps_name,  # يمكن تحسين الترجمة
                description=f"تم إنشاؤه تلقائياً بواسطة AI: {command.command_text}",
                parent_id=parent_eps.id if parent_eps else None,
                manager_id=manager_id,
                level=(parent_eps.level + 1) if parent_eps else 1,
                path=f"{parent_eps.path}/{eps_code}" if parent_eps else eps_code,
                is_active=True
            )
            db.session.add(eps)
            db.session.flush()
            
            result['count'] += 1
            result['data'].append({
                'id': eps.id,
                'code': eps.eps_code,
                'name': eps.name,
                'level': eps.level,
                'path': eps.path
            })
            
            # إضافة رسالة نجاح
            result['message'] = f"تم إنشاء عنصر EPS '{eps_name}' بنجاح بكود {eps_code}"
        
        # تعديل EPS
        elif analysis['intent'] == 'update' and ('eps' in text or 'هيكل' in text):
            eps_id = CommandProcessor.extract_eps_id(text)
            if eps_id:
                eps = EPS.query.get(eps_id)
                if eps and eps.org_id == org_id:
                    # تحديث الاسم
                    new_name = CommandProcessor.extract_new_name(text)
                    if new_name:
                        eps.name = new_name
                    
                    # تحديث المدير
                    new_manager = CommandProcessor.extract_manager(text, org_id)
                    if new_manager:
                        eps.manager_id = new_manager
                    
                    db.session.commit()
                    
                    result['count'] += 1
                    result['data'].append({'id': eps.id, 'updated': True})
                    result['message'] = f"تم تحديث عنصر EPS '{eps.name}' بنجاح"
        
        # حذف EPS
        elif analysis['intent'] == 'delete' and ('eps' in text or 'هيكل' in text):
            eps_id = CommandProcessor.extract_eps_id(text)
            if eps_id:
                eps = EPS.query.get(eps_id)
                if eps and eps.org_id == org_id:
                    # التحقق من عدم وجود مشاريع مرتبطة
                    if eps.primavera_projects.count() == 0:
                        db.session.delete(eps)
                        db.session.commit()
                        result['count'] += 1
                        result['message'] = f"تم حذف عنصر EPS '{eps.name}' بنجاح"
                    else:
                        result['error'] = "لا يمكن حذف EPS لأنه يحتوي على مشاريع مرتبطة"
        
        return result
    
    # ============================================
    # 👥 إدارة المستخدمين والأدوار
    # ============================================
    
    @staticmethod
    def handle_user_commands(command, analysis, user, org_id):
        """معالجة أوامر المستخدمين"""
        result = {
            'type': 'user',
            'action': analysis['intent'],
            'count': 0,
            'data': []
        }
        
        text = command.command_text.lower()
        
        # إنشاء مستخدم جديد
        if analysis['intent'] == 'create' and ('مستخدم' in text or 'user' in text or 'موظف' in text):
            # استخراج معلومات المستخدم
            user_info = CommandProcessor.extract_user_info(text)
            
            if user_info.get('email'):
                # التحقق من عدم وجود المستخدم
                existing = User.query.filter_by(org_id=org_id, email=user_info['email']).first()
                if existing:
                    result['error'] = f"المستخدم {user_info['email']} موجود مسبقاً"
                    return result
                
                # إنشاء المستخدم
                new_user = User(
                    org_id=org_id,
                    username=user_info.get('username', user_info['email'].split('@')[0]),
                    email=user_info['email'],
                    full_name=user_info.get('name', user_info['email'].split('@')[0]),
                    full_name_ar=user_info.get('name_ar'),
                    phone=user_info.get('phone'),
                    mobile=user_info.get('mobile'),
                    job_title=user_info.get('job_title'),
                    job_title_ar=user_info.get('job_title_ar'),
                    role=user_info.get('role', 'employee'),
                    is_user_active=True,
                    created_by=user.id
                )
                
                # تعيين كلمة مرور افتراضية
                default_password = CommandProcessor.generate_password()
                new_user.set_password(default_password)
                
                db.session.add(new_user)
                db.session.flush()
                
                result['count'] += 1
                result['data'].append({
                    'id': new_user.id,
                    'name': new_user.full_name,
                    'email': new_user.email,
                    'role': new_user.role,
                    'default_password': default_password  # سيتم إرسالها للمدير
                })
                result['message'] = f"تم إنشاء المستخدم {new_user.full_name} بنجاح"
                
                # إضافة إشعار للمستخدم الجديد
                NotificationService.user_created(
                    user_id=new_user.id,
                    created_by=user.id,
                    default_password=default_password
                )
        
        # تحديث مستخدم
        elif analysis['intent'] == 'update' and ('مستخدم' in text or 'user' in text):
            user_id = CommandProcessor.extract_user_id(text)
            if user_id:
                target_user = User.query.get(user_id)
                if target_user and target_user.org_id == org_id:
                    updates = {}
                    
                    # تحديث الصلاحيات
                    if 'صلاحية' in text or 'permission' in text:
                        new_role = CommandProcessor.extract_role(text)
                        if new_role:
                            target_user.role = new_role
                            updates['role'] = new_role
                    
                    # تحديث القسم
                    if 'قسم' in text or 'department' in text:
                        dept_id = CommandProcessor.extract_department_id(text, org_id)
                        if dept_id:
                            target_user.dept_id = dept_id
                            updates['department'] = dept_id
                    
                    db.session.commit()
                    
                    result['count'] += 1
                    result['data'].append(updates)
                    result['message'] = f"تم تحديث المستخدم {target_user.full_name} بنجاح"
        
        # تعطيل/تفعيل مستخدم
        elif 'تعطيل' in text or 'disable' in text:
            user_id = CommandProcessor.extract_user_id(text)
            if user_id:
                target_user = User.query.get(user_id)
                if target_user and target_user.org_id == org_id:
                    target_user.is_user_active = False
                    db.session.commit()
                    result['message'] = f"تم تعطيل المستخدم {target_user.full_name}"
        
        # إسناد مهمة لمستخدم
        elif 'اسند' in text or 'assign' in text:
            task_id = CommandProcessor.extract_task_id(text)
            user_id = CommandProcessor.extract_user_id(text)
            
            if task_id and user_id:
                task = Task.query.get(task_id)
                if task and task.project.org_id == org_id:
                    task.assign_user(user_id, user.id)
                    result['message'] = f"تم إسناد المهمة {task.task_code} للمستخدم"
        
        return result
    
    # ============================================
    # 📊 إدارة جداول الكميات والمواصفات (BOQ)
    # ============================================
    
    @staticmethod
    def handle_boq_commands(command, analysis, attachments, user, org_id):
        """معالجة أوامر جداول الكميات"""
        result = {
            'type': 'boq',
            'action': analysis['intent'],
            'count': 0,
            'data': []
        }
        
        text = command.command_text.lower()
        
        # استيراد جدول كميات من ملف
        if attachments and ('جدول' in text or 'boq' in text or 'كميات' in text):
            for attachment in attachments:
                if attachment.file_type in ['xlsx', 'xls']:
                    # استخراج جدول الكميات من Excel
                    boq_data = CommandProcessor.extract_boq_from_excel(
                        attachment.extracted_data,
                        attachment.extracted_text
                    )
                    
                    # تحديد المشروع المرتبط
                    project_id = CommandProcessor.extract_project_id(text, org_id)
                    
                    if boq_data and project_id:
                        items_created = CommandProcessor.create_boq_items(
                            boq_data, project_id, user.id
                        )
                        result['count'] += items_created
                        result['data'].extend(boq_data[:10])  # أول 10 عناصر
                        result['message'] = f"تم استيراد {items_created} بند من جدول الكميات"
        
        # إنشاء بند جديد في جدول الكميات
        elif 'بند' in text or 'item' in text:
            project_id = CommandProcessor.extract_project_id(text, org_id)
            if project_id:
                item_info = CommandProcessor.extract_boq_item(text)
                
                bill_item = BillItem(
                    project_id=project_id,
                    item_code=item_info.get('code', CommandProcessor.generate_boq_code()),
                    description=item_info.get('description'),
                    description_ar=item_info.get('description_ar'),
                    unit=item_info.get('unit', 'each'),
                    quantity=item_info.get('quantity', 1),
                    unit_price=item_info.get('unit_price', 0),
                    total_price=item_info.get('quantity', 1) * item_info.get('unit_price', 0),
                    created_by=user.id
                )
                db.session.add(bill_item)
                db.session.commit()
                
                result['count'] += 1
                result['message'] = f"تم إضافة بند '{item_info.get('description')}' إلى جدول الكميات"
        
        return result
    
    # ============================================
    # ⚙️ إدارة الأدوار الوظيفية (Roles)
    # ============================================
    
    @staticmethod
    def handle_role_commands(command, analysis, user, org_id):
        """معالجة أوامر الأدوار الوظيفية"""
        result = {
            'type': 'role',
            'action': analysis['intent'],
            'count': 0,
            'data': []
        }
        
        text = command.command_text.lower()
        
        # إنشاء دور وظيفي جديد
        if analysis['intent'] == 'create' and ('دور' in text or 'role' in text):
            role_info = CommandProcessor.extract_role_info(text)
            
            role = Role(
                org_id=org_id,
                role_code=CommandProcessor.generate_role_code(role_info.get('name')),
                name=role_info.get('name'),
                name_ar=role_info.get('name_ar'),
                description=role_info.get('description'),
                default_cost_per_hour=role_info.get('cost_per_hour', 0),
                currency='SAR',
                required_skills=role_info.get('skills', [])
            )
            db.session.add(role)
            db.session.commit()
            
            result['count'] += 1
            result['data'].append({'id': role.id, 'name': role.name})
            result['message'] = f"تم إنشاء الدور الوظيفي '{role.name}' بنجاح"
        
        # تعيين دور لمستخدم
        elif 'عين' in text or 'assign' in text:
            user_id = CommandProcessor.extract_user_id(text)
            role_id = CommandProcessor.extract_role_id(text, org_id)
            
            if user_id and role_id:
                target_user = User.query.get(user_id)
                if target_user:
                    target_user.role = Role.query.get(role_id).name
                    db.session.commit()
                    result['message'] = f"تم تعيين الدور للمستخدم {target_user.full_name}"
        
        return result
    
    # ============================================
    # 📋 إدارة المهام والتكليفات
    # ============================================
    
    @staticmethod
    def handle_task_assignment_commands(command, analysis, user, org_id):
        """معالجة أوامر تكليف المهام"""
        result = {
            'type': 'task_assignment',
            'action': analysis['intent'],
            'count': 0,
            'data': []
        }
        
        text = command.command_text.lower()
        
        # تكليف مهمة لمستخدمين متعددين
        if 'وزع' in text or 'توزيع' in text or 'assign multiple' in text:
            project_id = CommandProcessor.extract_project_id(text, org_id)
            if project_id:
                # استخراج قائمة المهام والمستخدمين
                tasks = CommandProcessor.extract_tasks_from_text(text)
                users = CommandProcessor.extract_users_from_text(text, org_id)
                
                if tasks and users:
                    assignments = CommandProcessor.distribute_tasks(
                        tasks, users, project_id, user.id
                    )
                    result['count'] = len(assignments)
                    result['data'] = assignments
                    result['message'] = f"تم توزيع {len(assignments)} مهمة على {len(users)} مستخدم"
        
        # تحديث صلاحيات المستخدم على مشروع
        elif 'صلاحية' in text or 'permission' in text:
            user_id = CommandProcessor.extract_user_id(text)
            project_id = CommandProcessor.extract_project_id(text, org_id)
            permission_level = CommandProcessor.extract_permission_level(text)
            
            if user_id and project_id:
                project=Project.query.filter_by(id=project_id).first()
                # إنشاء أو تحديث الصلاحية
                assignment = EPSOBSAssignment.query.filter_by(
                    eps_id=project.eps_id,
                    obs_id=project.obs_id
                ).first()
                
                if assignment:
                    assignment.permission_level = permission_level
                else:
                    assignment = EPSOBSAssignment(
                        eps_id=project.eps_id,
                        obs_id=project.obs_id,
                        permission_level=permission_level,
                        created_by=user.id
                    )
                    db.session.add(assignment)
                
                db.session.commit()
                result['message'] = f"تم تحديث صلاحيات المستخدم على المشروع"
        
        return result
    
    # ============================================
    # 🏗️ إدارة عناصر WBS
    # ============================================
    
    @staticmethod
    def handle_wbs_commands(command, analysis, user, org_id):
        """معالجة أوامر WBS"""
        result = {
            'type': 'wbs',
            'action': analysis['intent'],
            'count': 0,
            'data': []
        }
        
        text = command.command_text.lower()
        
        # إنشاء هيكل WBS كامل
        if 'wbs' in text and ('أنشئ' in text or 'create' in text):
            project_id = CommandProcessor.extract_project_id(text, org_id)
            if project_id:
                # استخراج هيكل WBS من النص
                wbs_structure = CommandProcessor.extract_wbs_structure(text)
                
                created_items = CommandProcessor.create_wbs_hierarchy(
                    wbs_structure, project_id, user.id
                )
                
                result['count'] = len(created_items)
                result['data'] = created_items
                result['message'] = f"تم إنشاء هيكل WBS بـ {len(created_items)} عنصر"
        
        return result
    
    # ============================================
    # 🔄 الدوال المساعدة
    # ============================================
    
    @staticmethod
    def extract_user_info(text):
        """استخراج معلومات المستخدم من النص"""
        info = {}
        
        # استخراج الاسم
        name_patterns = [
            r'اسمه\s+["\']?([^"\']+)["\']?',
            r'name\s+["\']?([^"\']+)["\'\s]',
            r'الاسم\s+["\']?([^"\']+)["\']?'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                info['name'] = match.group(1).strip()
                break
        
        # استخراج البريد الإلكتروني
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        email_match = re.search(email_pattern, text)
        if email_match:
            info['email'] = email_match.group()
        
        # استخراج رقم الهاتف
        phone_pattern = r'(?:\+966|0)?5\d{8}'
        phone_match = re.search(phone_pattern, text)
        if phone_match:
            info['phone'] = phone_match.group()
        
        # استخراج الدور الوظيفي
        role_patterns = [r'بدور\s+["\']?([^"\']+)["\']?', r'as\s+["\']?([^"\']+)["\']?']
        for pattern in role_patterns:
            match = re.search(pattern, text)
            if match:
                role_text = match.group(1).lower()
                if 'مدير' in role_text:
                    info['role'] = 'project_manager'
                elif 'مشرف' in role_text:
                    info['role'] = 'supervisor'
                elif 'مندوب' in role_text:
                    info['role'] = 'delegate'
                else:
                    info['role'] = 'employee'
                break
        
        return info
    
    @staticmethod
    def extract_eps_name(text):
        """استخراج اسم EPS"""
        patterns = [
            r'eps\s+["\']?([^"\']+)["\']?',
            r'هيكل\s+["\']?([^"\']+)["\']?'
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return f"EPS_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    @staticmethod
    def extract_parent_eps(text, org_id):
        """استخراج الـ EPS الأب"""
        patterns = [r'تحت\s+["\']?([^"\']+)["\']?', r'under\s+["\']?([^"\']+)["\']?']
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                parent_name = match.group(1).strip()
                return EPS.query.filter_by(org_id=org_id, name=parent_name).first()
        return None
    
    @staticmethod
    def extract_manager(text, org_id):
        """استخراج معرف المدير"""
        patterns = [r'مدير\s+["\']?([^"\']+)["\']?', r'manager\s+["\']?([^"\']+)["\']?']
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                manager_name = match.group(1).strip()
                user = User.query.filter_by(org_id=org_id, full_name=manager_name).first()
                return user.id if user else None
        return None
    
    @staticmethod
    def extract_boq_from_excel(extracted_data, extracted_text):
        """استخراج جدول الكميات من Excel"""
        boq_items = []
        
        if extracted_data and 'tables' in extracted_data:
            for table in extracted_data['tables']:
                for row in table:
                    item = {
                        'code': row.get('code') or row.get('البند') or row.get('Item'),
                        'description': row.get('description') or row.get('البيان'),
                        'unit': row.get('unit') or row.get('الوحدة'),
                        'quantity': float(row.get('quantity', 0)) if row.get('quantity') else 0,
                        'unit_price': float(row.get('unit_price', 0)) if row.get('unit_price') else 0
                    }
                    if item['code'] and item['description']:
                        boq_items.append(item)
        
        return boq_items
    
    @staticmethod
    def create_boq_items(boq_data, project_id, user_id):
        """إنشاء بنود جدول الكميات"""
        count = 0
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
                created_by=user_id
            )
            db.session.add(bill_item)
            count += 1
        
        db.session.commit()
        return count
    
    @staticmethod
    def extract_role_info(text):
        """استخراج معلومات الدور الوظيفي"""
        info = {}
        
        # اسم الدور
        name_match = re.search(r'دور\s+["\']?([^"\']+)["\']?', text)
        if name_match:
            info['name'] = name_match.group(1).strip()
        
        # التكلفة في الساعة
        cost_match = re.search(r'(\d+(?:\.\d+)?)\s*(ريال|SAR)', text)
        if cost_match:
            info['cost_per_hour'] = float(cost_match.group(1))
        
        return info
    
    @staticmethod
    def distribute_tasks(tasks, users, project_id, assigner_id):
        """توزيع المهام على المستخدمين"""
        assignments = []
        user_count = len(users)
        
        for i, task_info in enumerate(tasks):
            user = users[i % user_count]
            
            task = Task(
                project_id=project_id,
                task_code=f"T{datetime.now().strftime('%Y%m%d%H%M%S')}{i}",
                task_name=task_info['name'],
                task_order=i + 1,
                supervisor_id=user.id,
                delegate_id=user.id,
                created_by=assigner_id,
                status='pending'
            )
            db.session.add(task)
            db.session.flush()
            
            # إنشاء تعيين
            assignment = TaskAssignment(
                task_id=task.id,
                user_id=user.id,
                assigned_by=assigner_id,
                status='assigned'
            )
            db.session.add(assignment)
            
            assignments.append({
                'task_id': task.id,
                'task_name': task.task_name,
                'user_id': user.id,
                'user_name': user.full_name
            })
        
        db.session.commit()
        return assignments
    
    @staticmethod
    def create_wbs_hierarchy(structure, project_id, user_id):
        """إنشاء هرمية WBS"""
        created_items = []
        
        def create_wbs_node(node_data, parent_id=None, level=1):
            parent=WBS.query.filter_by(parent_id=parent_id).first()
            wbs = WBS(
                project_id=project_id,
                wbs_code=node_data['code'],
                name=node_data['name'],
                name_ar=node_data.get('name_ar', node_data['name']),
                description=node_data.get('description'),
                parent_id=parent_id,
                level=level,
                wbs_path=f"{parent.wbs_path}.{node_data['code']}" if parent_id else node_data['code'],
                weight=node_data.get('weight', 0)
            )
            db.session.add(wbs)
            db.session.flush()
            
            created_items.append({
                'id': wbs.id,
                'code': wbs.wbs_code,
                'name': wbs.name,
                'level': level
            })
            
            # إنشاء العقد الفرعية
            if 'children' in node_data:
                for child in node_data['children']:
                    create_wbs_node(child, wbs.id, level + 1)
        
        for root_node in structure:
            create_wbs_node(root_node)
        
        db.session.commit()
        return created_items
    
    @staticmethod
    def extract_wbs_structure(text):
        """استخراج هيكل WBS من النص"""
        structure = []
        
        # تحليل النص المنظم
        lines = text.split('\n')
        current_level = 0
        current_path = []
        
        for line in lines:
            # الكشف عن مستويات WBS
            indent = len(line) - len(line.lstrip())
            level = indent // 2  # كل مسافتين = مستوى
            
            # استخراج الكود والاسم
            match = re.match(r'(\d+(?:\.\d+)*)\s*[.-]\s*(.+)', line.strip())
            if match:
                code = match.group(1)
                name = match.group(2)
                
                node = {
                    'code': code,
                    'name': name
                }
                
                if level == 0:
                    structure.append(node)
                    current_path = [node]
                else:
                    # إضافة كعقدة فرعية
                    parent = current_path[level - 1]
                    if 'children' not in parent:
                        parent['children'] = []
                    parent['children'].append(node)
                    
                    # تحديث المسار
                    current_path = current_path[:level] + [node]
        
        return structure
# helpers/document_helpers.py - دوال مساعدة لإدارة المستندات

import os
from datetime import datetime
from werkzeug.utils import secure_filename
from uploads.temp.models import ProjectDocument, BillItem, Project,Task,TaskAssignment
from services.document_parser import DocumentParser

def get_user_documents(user):
    """الحصول على مستندات المستخدم حسب دوره"""
    if user.role == 'admin':
        documents = ProjectDocument.query.join(Project).filter(
            Project.org_id == user.org_id
        ).all()
    elif user.role == 'project_manager':
        documents = ProjectDocument.query.join(Project).filter(
            Project.project_manager_id == user.id
        ).all()
    else:
        # للمشرفين والمناديب والموظفين
        projects = get_user_projects(user)
        documents = ProjectDocument.query.filter(
            ProjectDocument.project_id.in_([p.id for p in projects])
        ).all()
    
    return documents

def get_user_projects(user):
    """الحصول على مشاريع المستخدم حسب دوره"""
    if user.role == 'admin':
        projects = Project.query.filter_by(org_id=user.org_id).all()
    elif user.role == 'project_manager':
        projects = Project.query.filter_by(project_manager_id=user.id).all()
    elif user.role == 'supervisor':
        projects = Project.query.join(Task).filter(
            Task.supervisor_id == user.id
        ).distinct().all()
    elif user.role == 'delegate':
        projects = Project.query.join(Task).filter(
            Task.delegate_id == user.id
        ).distinct().all()
    elif user.role == 'employee':
        projects = Project.query.join(Task).join(Task.assignments).filter(
            TaskAssignment.user_id == user.id
        ).distinct().all()
    else:
        projects = []
    
    return projects

def can_upload_to_project(project, user):
    """التحقق من صلاحية رفع مستندات للمشروع"""
    if user.role == 'admin':
        return project.org_id == user.org_id
    elif user.role == 'project_manager':
        return project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return project.id in [t.project_id for t in user.supervised_tasks]
    elif user.role == 'delegate':
        return project.id in [t.project_id for t in user.delegate_tasks]
    elif user.role == 'employee':
        return project.id in [t.project_id for a in user.task_assignments for t in [a.task]]
    return False

def has_document_access(document, user):
    """التحقق من صلاحية الوصول للمستند"""
    # إذا كان المستند عاماً
    if document.is_public:
        return True
    
    # إذا كان المستند للمؤسسة
    if document.access_level == 'organization':
        return document.project.org_id == user.org_id
    
    # إذا كان المستند للفريق
    if document.access_level == 'team':
        return has_project_access(document.project, user)
    
    # إذا كان المستند مقيداً
    if document.access_level == 'restricted':
        # فقط منشئ المستند والموافق عليه
        return document.uploaded_by == user.id or document.approved_by == user.id
    
    return False

def has_project_access(project, user):
    """التحقق من صلاحية الوصول للمشروع"""
    if user.role == 'admin':
        return project.org_id == user.org_id
    elif user.role == 'project_manager':
        return project.project_manager_id == user.id
    elif user.role == 'supervisor':
        return project.id in [t.project_id for t in user.supervised_tasks]
    elif user.role == 'delegate':
        return project.id in [t.project_id for t in user.delegate_tasks]
    elif user.role == 'employee':
        return project.id in [t.project_id for a in user.task_assignments for t in [a.task]]
    return False

def can_approve_document(document, user):
    """التحقق من صلاحية الموافقة على المستند"""
    if user.role == 'admin':
        return document.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return document.project.project_manager_id == user.id
    return False

def can_delete_document(document, user):
    """التحقق من صلاحية حذف المستند"""
    if user.role == 'admin':
        return document.project.org_id == user.org_id
    elif user.role == 'project_manager':
        return document.project.project_manager_id == user.id
    elif user.role in ['supervisor', 'delegate', 'employee']:
        # يمكن للمستخدم حذف المستندات التي رفعها فقط
        return document.uploaded_by == user.id
    return False

def get_document_type_label(doc_type):
    """الحصول على وصف لنوع المستند"""
    labels = {
        'bill_of_quantities': 'جدول كميات',
        'contract': 'عقد',
        'drawing': 'رسم',
        'specification': 'مواصفات',
        'report': 'تقرير',
        'invoice': 'فاتورة',
        'other': 'أخرى'
    }
    return labels.get(doc_type, doc_type)

def format_file_size(size_in_bytes):
    """تنسيق حجم الملف"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} بايت"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.2f} كيلوبايت"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes / (1024 * 1024):.2f} ميجابايت"
    else:
        return f"{size_in_bytes / (1024 * 1024 * 1024):.2f} جيجابايت"

def get_allowed_extensions():
    """الحصول على الامتدادات المسموح بها"""
    return {
        'pdf', 'docx', 'doc', 'xlsx', 'xls', 'csv', 'txt',
        'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'dwg', 'dxf'
    }

def generate_unique_filename(original_filename, upload_folder):
    """إنشاء اسم فريد للملف"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    secure_name = secure_filename(original_filename)
    unique_name = f"{timestamp}_{secure_name}"
    
    # التحقق من عدم تكرار الاسم
    file_path = os.path.join(upload_folder, 'documents', unique_name)
    counter = 1
    
    while os.path.exists(file_path):
        name_parts = secure_name.rsplit('.', 1)
        if len(name_parts) == 2:
            name, ext = name_parts
            unique_name = f"{timestamp}_{name}_{counter}.{ext}"
        else:
            unique_name = f"{timestamp}_{secure_name}_{counter}"
        file_path = os.path.join(upload_folder, 'documents', unique_name)
        counter += 1
    
    return unique_name

def parse_document_content(file_path, file_extension):
    """تحليل محتوى المستند"""
    try:
        parser = DocumentParser(os.path.dirname(file_path))
        parsed_data = parser.parse_document(file_path, file_extension)
        return parsed_data
    except Exception as e:
        print(f"Error parsing document: {str(e)}")
        return None

def create_bill_items_from_data(project_id, parsed_data):
    """إنشاء بنود جدول الكميات من البيانات المستخرجة"""
    try:
        items = []
        
        if isinstance(parsed_data, list):
            for item_data in parsed_data:
                item = BillItem(
                    project_id=project_id,
                    item_number=item_data.get('item_number'),
                    description=item_data.get('description'),
                    description_ar=item_data.get('description_ar'),
                    unit=item_data.get('unit'),
                    quantity=item_data.get('quantity', 0),
                    unit_price=item_data.get('unit_price', 0),
                    total_price=item_data.get('total_price', 0),
                    notes=item_data.get('notes')
                )
                items.append(item)
        
        return items
    except Exception as e:
        print(f"Error creating bill items: {str(e)}")
        return []
# app/route s/codes_routes.py

from flask import render_template, request, redirect, url_for, flash, jsonify, g, current_app
from flask_login import login_required, current_user
from app.models import db
from app.models import (
    ActivityCodeDictionary, ActivityCodeValue, ActivityCodeAssignment,Issue,Task,TaskPlanning,ResourceDelivery,Resource,Meeting,
    ProjectCodeDictionary, ProjectCodeValue, ProjectCodeAssignment,Organization,Notification
)
from app.models.primavera_models import Activity
from app.models.project_models import Project
from datetime import datetime,timedelta,date
from sqlalchemy import or_, and_

from app.routes import codes_bp

# ============================================
# دوال مساعدة
# ============================================

def get_org_id():
    return current_user.org_id
@codes_bp.before_request
def load_company():
    if current_user.is_authenticated:
        g.company = Organization.query.get(current_user.org_id)
        g.notifications_count = Notification.query.filter_by(
            user_id=current_user.id, 
            is_read=False
        ).count()
        g.delayed_tasks_count = Task.query.join(Project).filter(
            Task.status.in_(['pending', 'in_progress']),
            TaskPlanning.planned_finish < date.today()
        ).count()
        g.pending_deliveries_count = ResourceDelivery.query.filter_by(
            status='pending'
        ).count() if current_user.role in ['org_admin', 'project_manager'] else 0
        
        # إضافة إحصائيات الموارد
        g.low_stock_resources = Resource.query.filter(
            Resource.available_quantity < Resource.minimum_quantity
        ).count() if hasattr(Resource, 'minimum_quantity') else 0
        # ⭐ إحصائيات الاجتماعات القادمة
        # ========== الاجتماعات القادمة ==========
        today = datetime.now().date()
        next_week = today + timedelta(days=7)
        
        upcoming_meetings_query = Meeting.query.filter(
            Meeting.project.has(org_id=current_user.org_id),
            Meeting.scheduled_date >= today,
            Meeting.scheduled_date <= next_week,
            Meeting.status == 'scheduled'
        ).order_by(Meeting.scheduled_date)
        
        # الحصول على القائمة للعرض
        g.upcoming_meetings = upcoming_meetings_query.limit(5).all()
        
        # ✅ حساب العدد بشكل صحيح
        g.upcoming_meetings_count = upcoming_meetings_query.count()
        
        # ========== القضايا المفتوحة ==========
        open_issues_count = Issue.query.join(Project).filter(
            Project.org_id == current_user.org_id,
            Issue.status.in_(['open', 'in_progress'])
        ).count()
        g.open_issues_count = open_issues_count
        
        # آخر 5 قضايا
        recent_issues = Issue.query.join(Project).filter(
            Project.org_id == current_user.org_id
        ).order_by(Issue.reported_date.desc()).limit(5).all()
        g.recent_issues = recent_issues
        
        # إحصائيات القضايا
        g.issues_stats = {
            'open': Issue.query.join(Project).filter(
                Project.org_id == current_user.org_id, 
                Issue.status == 'open'
            ).count(),
            'in_progress': Issue.query.join(Project).filter(
                Project.org_id == current_user.org_id, 
                Issue.status == 'in_progress'
            ).count(),
            'total': Issue.query.join(Project).filter(
                Project.org_id == current_user.org_id
            ).count()
        }
    else:
        g.company = None
        g.upcoming_meetings =None
        g.recent_issues=None
        g.delayed_tasks_count = 0
        g.notifications_count = 0
        g.pending_deliveries_count=0
        g.low_stock_resources=0
        g.upcoming_meetings_count=0
        g.open_issues_count =0
        g.issues_stats={}
# ============================================
# أكواد الأنشطة - الصفحة الرئيسية
# ============================================

@codes_bp.route('/activity')
@login_required
def activity_codes():
    """الصفحة الرئيسية لأكواد الأنشطة - مثل Primavera"""
    org_id = get_org_id()
    
    # جلب جميع قواميس الأكواد
    dictionaries = ActivityCodeDictionary.query.filter_by(org_id=org_id).order_by(ActivityCodeDictionary.dict_name).all()
    
    # تجهيز البيانات مع قيم الأكواد
    dicts_data = []
    for dict in dictionaries:
        # جلب الأكواد الرئيسية (المستوى الأول)
        root_codes = ActivityCodeValue.query.filter_by(
            dictionary_id=dict.id,
            parent_id=None
        ).order_by(ActivityCodeValue.display_sequence).all()
        
        # بناء الهيكل الشجري
        def build_tree(parent_id=None):
            tree = []
            codes = ActivityCodeValue.query.filter_by(
                dictionary_id=dict.id,
                parent_id=parent_id
            ).order_by(ActivityCodeValue.display_sequence).all()
            
            for code in codes:
                children = build_tree(code.id)
                code_dict = code.to_dict()
                if children:
                    code_dict['children'] = children
                tree.append(code_dict)
            return tree
        
        dicts_data.append({
            'dictionary': dict,
            'root_codes': build_tree(),
            'total_codes': dict.codes.count()
        })
    
    return render_template('codes/activity_codes.html',
                         dictionaries=dicts_data,
                         now=datetime.now())


@codes_bp.route('/activity/dictionary/create', methods=['POST'])
@login_required
def create_activity_dictionary():
    """إنشاء قاموس أكواد جديد للأنشطة"""
    data = request.get_json()
    
    try:
        # التحقق من عدم وجود قاموس بنفس الاسم
        existing = ActivityCodeDictionary.query.filter_by(
            org_id=get_org_id(),
            dict_name=data.get('dict_name')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'قاموس بنفس الاسم موجود مسبقاً'}), 400
        
        dictionary = ActivityCodeDictionary(
            org_id=get_org_id(),
            dict_name=data.get('dict_name'),
            description=data.get('description'),
            max_length=data.get('max_length', 20),
            is_hierarchical=data.get('is_hierarchical', False),
            delimiter=data.get('delimiter', '.'),
            created_by=current_user.id
        )
        
        db.session.add(dictionary)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'dictionary': {
                'id': dictionary.id,
                'name': dictionary.dict_name,
                'description': dictionary.description
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@codes_bp.route('/activity/dictionary/<int:dictionary_id>/codes', methods=['GET'])
@login_required
def get_activity_dictionary_codes(dictionary_id):
    """جلب جميع قيم الأكواد لقاموس معين (مع الهيكل الشجري)"""
    dictionary = ActivityCodeDictionary.query.get_or_404(dictionary_id)
    
    if dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # بناء الهيكل الشجري
    def build_tree(parent_id=None):
        tree = []
        codes = ActivityCodeValue.query.filter_by(
            dictionary_id=dictionary_id,
            parent_id=parent_id,
            is_active=True
        ).order_by(ActivityCodeValue.display_sequence).all()
        
        for code in codes:
            children = build_tree(code.id)
            code_dict = {
                'id': code.id,
                'code_value': code.code_value,
                'description': code.code_description,
                'display_color': code.display_color,
                'display_sequence': code.display_sequence,
                'level': code.level,
                'full_path': code.full_path,
                'has_children': len(children) > 0,
                'assignments_count': code.assignments.count(),
                'dictionary_id': code.dictionary_id,
                'is_active': code.is_active
            }
            if children:
                code_dict['children'] = children
            tree.append(code_dict)
        return tree
    
    return jsonify({
        'success': True,
        'dictionary': {
            'id': dictionary.id,
            'name': dictionary.dict_name,
            'description': dictionary.description,
            'is_hierarchical': dictionary.is_hierarchical,
            'delimiter': dictionary.delimiter
        },
        'codes': build_tree()
    })


@codes_bp.route('/activity/code/create', methods=['POST'])
@login_required
def create_activity_code():
    """إنشاء قيمة كود جديدة للنشاط"""
    data = request.get_json()
    
    try:
        # التحقق من وجود القاموس
        dictionary = ActivityCodeDictionary.query.get(data.get('dictionary_id'))
        if not dictionary or dictionary.org_id != get_org_id():
            return jsonify({'success': False, 'error': 'قاموس غير صالح'}), 400
        
        # التحقق من عدم وجود قيمة مكررة
        existing = ActivityCodeValue.query.filter_by(
            dictionary_id=data.get('dictionary_id'),
            code_value=data.get('code_value')
        ).first()
        
        if existing:
            return jsonify({'success': False, 'error': 'قيمة الكود موجودة مسبقاً'}), 400
        
        # إنشاء الكود الجديد
        code = ActivityCodeValue(
            dictionary_id=data.get('dictionary_id'),
            code_value=data.get('code_value'),
            code_description=data.get('description', ''),
            display_color=data.get('display_color', '#4361ee'),
            display_sequence=data.get('display_sequence', 0),
            parent_id=data.get('parent_id'),
            created_by=current_user.id,
            is_active=True
        )
        
        # حساب المستوى والمسار
        if code.parent_id:
            parent = ActivityCodeValue.query.get(code.parent_id)
            if parent:
                code.level = parent.level + 1
                code.full_path = f"{parent.full_path}{dictionary.delimiter}{code.code_value}" if parent.full_path else code.code_value
            else:
                code.level = 1
                code.full_path = code.code_value
        else:
            code.level = 1
            code.full_path = code.code_value
        
        db.session.add(code)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'code': {
                'id': code.id,
                'code_value': code.code_value,
                'description': code.code_description,
                'display_color': code.display_color,
                'display_sequence': code.display_sequence,
                'level': code.level,
                'full_path': code.full_path,
                'dictionary_id': code.dictionary_id,
                'is_active': code.is_active
            }
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@codes_bp.route('/activity/code/<int:code_id>', methods=['GET'])
@login_required
def get_activity_code(code_id):
    """جلب تفاصيل قيمة كود محددة"""
    code = ActivityCodeValue.query.get_or_404(code_id)
    
    if code.dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # الحصول على المسار الكامل للعرض
    path_parts = []
    current = code
    while current:
        path_parts.insert(0, current.code_value)
        current = current.parent
    full_path_display = ' → '.join(path_parts)
    
    return jsonify({
        'success': True,
        'code': {
            'id': code.id,
            'dictionary_id': code.dictionary_id,
            'dictionary_name': code.dictionary.dict_name,
            'code_value': code.code_value,
            'description': code.code_description,
            'display_color': code.display_color,
            'display_sequence': code.display_sequence,
            'level': code.level,
            'full_path': code.full_path,
            'full_path_display': full_path_display,
            'is_active': code.is_active,
            'parent_id': code.parent_id,
            'parent_value': code.parent.code_value if code.parent else None,
            'assignments_count': code.assignments.count(),
            'created_at': code.created_at.strftime('%Y-%m-%d %H:%M') if code.created_at else None,
            'created_by': code.creator.full_name if code.creator else None
        }
    })


@codes_bp.route('/activity/code/<int:code_id>/update', methods=['POST'])
@login_required
def update_activity_code(code_id):
    """تحديث قيمة كود نشاط"""
    code = ActivityCodeValue.query.get_or_404(code_id)
    
    if code.dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم وجود قيمة مكررة (إذا تغيرت القيمة)
        if data.get('code_value') and data['code_value'] != code.code_value:
            existing = ActivityCodeValue.query.filter_by(
                dictionary_id=code.dictionary_id,
                code_value=data['code_value']
            ).first()
            
            if existing:
                return jsonify({'success': False, 'error': 'قيمة الكود موجودة مسبقاً'}), 400
        
        # تحديث الحقول
        code.code_value = data.get('code_value', code.code_value)
        code.code_description = data.get('description', code.code_description)
        code.display_color = data.get('display_color', code.display_color)
        code.display_sequence = data.get('display_sequence', code.display_sequence)
        code.is_active = data.get('is_active', code.is_active)
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@codes_bp.route('/activity/code/<int:code_id>/delete', methods=['POST'])
@login_required
def delete_activity_code(code_id):
    """حذف قيمة كود نشاط"""
    code = ActivityCodeValue.query.get_or_404(code_id)
    
    if code.dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        # التحقق من وجود أبناء
        children_count = ActivityCodeValue.query.filter_by(parent_id=code_id).count()
        if children_count > 0:
            return jsonify({
                'success': False,
                'error': f'لا يمكن حذف الكود لأنه يحتوي على {children_count} أكواد فرعية'
            }), 400
        
        # التحقق من وجود ارتباطات بأنشطة
        assignments_count = code.assignments.count()
        if assignments_count > 0:
            return jsonify({
                'success': False,
                'error': f'لا يمكن حذف الكود لأنه مرتبط بـ {assignments_count} أنشطة'
            }), 400
        
        db.session.delete(code)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# تخصيص الأكواد للأنشطة (Activity Code Assignments)
# ============================================
@codes_bp.route('/activity/dictionaries', methods=['GET'])
@login_required
def get_activity_dictionaries():
    """API لجلب جميع قواميس أكواد الأنشطة"""
    org_id = get_org_id()
    
    dictionaries = ActivityCodeDictionary.query.filter_by(
        org_id=org_id,
        is_active=True
    ).order_by(ActivityCodeDictionary.dict_name).all()
    
    result = []
    for dict in dictionaries:
        result.append({
            'id': dict.id,
            'name': dict.dict_name,
            'description': dict.description,
            'is_hierarchical': dict.is_hierarchical,
            'codes_count': ActivityCodeValue.query.filter_by(dictionary_id=dict.id).count()
        })
    
    return jsonify({'success': True, 'dictionaries': result})

@codes_bp.route('/activity/api/dictionarys/<int:dictionary_id>/codes', methods=['GET'])
@login_required
def activity_dictionary(dictionary_id):
    """API لجلب جميع قيم الأكواد لقاموس نشاط معين"""
    dictionary = ActivityCodeDictionary.query.get_or_404(dictionary_id)
    
    if dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # بناء الهيكل الشجري
    def build_tree(parent_id=None):
        tree = []
        codes = ActivityCodeValue.query.filter_by(
            dictionary_id=dictionary_id,
            parent_id=parent_id,
            is_active=True
        ).order_by(ActivityCodeValue.display_sequence).all()
        
        for code in codes:
            children = build_tree(code.id)
            code_dict = {
                'id': code.id,
                'code_value': code.code_value,
                'description': code.code_description,
                'display_color': code.display_color,
                'display_sequence': code.display_sequence,
                'level': code.level,
                'full_path': code.full_path,
                'has_children': len(children) > 0,
                'assignments_count': code.assignments.count()
            }
            if children:
                code_dict['children'] = children
            tree.append(code_dict)
        return tree
    
    return jsonify({
        'success': True,
        'dictionary': {
            'id': dictionary.id,
            'name': dictionary.dict_name,
            'description': dictionary.description,
            'is_hierarchical': dictionary.is_hierarchical,
            'delimiter': dictionary.delimiter
        },
        'codes': build_tree()
    })


@codes_bp.route('/activity/<int:activity_id>/assignments', methods=['GET'])
@login_required
def get_activity_assignments(activity_id):
    """API لجلب الأكواد المرتبطة بنشاط"""
    from app.models.primavera_models import Activity
    
    activity = Activity.query.get_or_404(activity_id)
    
    # جلب جميع قواميس الأكواد النشطة
    dictionaries = ActivityCodeDictionary.query.filter_by(
        org_id=get_org_id(),
        is_active=True
    ).all()
    
    result = []
    for dictionary in dictionaries:
        assignment = ActivityCodeAssignment.query.filter_by(
            activity_id=activity_id,
            dictionary_id=dictionary.id
        ).first()
        
        result.append({
            'dictionary_id': dictionary.id,
            'dictionary_name': dictionary.dict_name,
            'is_hierarchical': dictionary.is_hierarchical,
            'assigned_code_id': assignment.code_value_id if assignment else None,
            'assigned_code': {
                'id': assignment.code_value.id,
                'code_value': assignment.code_value.code_value,
                'description': assignment.code_value.code_description,
                'display_color': assignment.code_value.display_color
            } if assignment else None
        })
    
    return jsonify({
        'success': True,
        'assignments': result
    })


@codes_bp.route('/activity/<int:activity_id>/assign', methods=['POST'])
@login_required
def assign_code_to_activity(activity_id):
    """تعيين كود لنشاط"""
    from app.models.primavera_models import Activity
    
    activity = Activity.query.get_or_404(activity_id)
    
    data = request.get_json()
    dictionary_id = int(data.get('dictionary_id'))
    code_value_id = data.get('code_value_id')
    
    if not dictionary_id or not code_value_id:
        return jsonify({'success': False, 'error': 'البيانات غير كاملة'}), 400
    
    try:
        # التحقق من صحة الكود
        code = ActivityCodeValue.query.get(code_value_id)
        if not code or code.dictionary_id != dictionary_id:
            return jsonify({'success': False, 'error': 'قيمة كود غير صالحة'}), 400
        
        # البحث عن تعيين موجود لنفس القاموس
        assignment = ActivityCodeAssignment.query.filter_by(
            activity_id=activity_id,
            dictionary_id=dictionary_id
        ).first()
        
        if assignment:
            # تحديث التعيين الموجود
            assignment.code_value_id = code_value_id
            assignment.created_by = current_user.id
        else:
            # إنشاء تعيين جديد
            assignment = ActivityCodeAssignment(
                activity_id=activity_id,
                dictionary_id=dictionary_id,
                code_value_id=code_value_id,
                created_by=current_user.id
            )
            db.session.add(assignment)
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@codes_bp.route('/activity/<int:activity_id>/unassign', methods=['POST'])
@login_required
def unassign_code_from_activity(activity_id):
    """إزالة كود من نشاط"""
    from app.models.primavera_models import Activity
    
    activity = Activity.query.get_or_404(activity_id)
    
    data = request.get_json()
    dictionary_id = data.get('dictionary_id')
    
    if not dictionary_id:
        return jsonify({'success': False, 'error': 'معرف القاموس مطلوب'}), 400
    
    try:
        assignment = ActivityCodeAssignment.query.filter_by(
            activity_id=activity_id,
            dictionary_id=dictionary_id
        ).first()
        
        if assignment:
            db.session.delete(assignment)
            db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@codes_bp.route('/activity/<int:activity_id>/unassign-multiple', methods=['POST'])
@login_required
def unassign_multiple_activity_codes(activity_id):
    """إزالة عدة أكواد من نشاط دفعة واحدة"""
    from app.models.primavera_models import Activity
    
    activity = Activity.query.get_or_404(activity_id)
    
    data = request.get_json()
    assignment_ids = data.get('assignment_ids', [])
    
    if not assignment_ids:
        return jsonify({'success': False, 'error': 'لا توجد أكواد محددة'}), 400
    
    try:
        deleted = ActivityCodeAssignment.query.filter(
            ActivityCodeAssignment.activity_id == activity_id,
            ActivityCodeAssignment.id.in_(assignment_ids)
        ).delete(synchronize_session=False)
        
        db.session.commit()
        return jsonify({'success': True, 'count': deleted})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@codes_bp.route('/activity/code/<int:code_id>', methods=['GET'])
@login_required
def get_activity_code_details(code_id):
    """API لجلب تفاصيل قيمة كود نشاط"""
    code = ActivityCodeValue.query.get_or_404(code_id)
    
    if code.dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # حساب المسار الكامل للعرض
    path_parts = []
    current = code
    while current:
        path_parts.insert(0, current.code_value)
        current = current.parent
    full_path_display = ' → '.join(path_parts)
    
    return jsonify({
        'success': True,
        'code': {
            'id': code.id,
            'dictionary_id': code.dictionary_id,
            'dictionary_name': code.dictionary.dict_name,
            'code_value': code.code_value,
            'description': code.code_description,
            'display_color': code.display_color,
            'display_sequence': code.display_sequence,
            'level': code.level,
            'full_path': code.full_path,
            'full_path_display': full_path_display,
            'is_active': code.is_active,
            'parent_id': code.parent_id,
            'parent_value': code.parent.code_value if code.parent else None,
            'assignments_count': code.assignments.count()
        }
    })

# ============================================
# أكواد المشاريع - مشابهة للأنشطة
# ============================================

@codes_bp.route('/project')
@login_required
def project_codes():
    """الصفحة الرئيسية لأكواد المشاريع"""
    org_id = get_org_id()
    
    dictionaries = ProjectCodeDictionary.query.filter_by(org_id=org_id).order_by(ProjectCodeDictionary.dict_name).all()
    
    dicts_data = []
    for dict in dictionaries:
        def build_tree(parent_id=None):
            tree = []
            codes = ProjectCodeValue.query.filter_by(
                dictionary_id=dict.id,
                parent_id=parent_id
            ).order_by(ProjectCodeValue.display_sequence).all()
            
            for code in codes:
                children = build_tree(code.id)
                code_dict = {
                    'id': code.id,
                    'code_value': code.code_value,
                    'description': code.code_description,
                    'display_color': code.display_color,
                    'level': code.level,
                    'full_path': code.full_path
                }
                if children:
                    code_dict['children'] = children
                tree.append(code_dict)
            return tree
        
        dicts_data.append({
            'dictionary': dict,
            'root_codes': build_tree(),
            'total_codes': dict.codes.count()
        })
    
    return render_template('codes/project_codes.html',
                         dictionaries=dicts_data,
                         now=datetime.now())


@codes_bp.route('/project/dictionary/create', methods=['POST'])
@login_required
def create_project_dictionary():
    """إنشاء قاموس أكواد جديد للمشاريع"""
    data = request.get_json()
    
    try:
        dictionary = ProjectCodeDictionary(
            org_id=get_org_id(),
            dict_name=data.get('dict_name'),
            description=data.get('description'),
            max_length=data.get('max_length', 20),
            is_hierarchical=data.get('is_hierarchical', False),
            delimiter=data.get('delimiter', '.'),
            created_by=current_user.id
        )
        
        db.session.add(dictionary)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@codes_bp.route('/project/code/create', methods=['POST'])
@login_required
def create_project_code():
    """إنشاء قيمة كود جديدة للمشروع"""
    data = request.get_json()
    
    try:
        code = ProjectCodeValue(
            dictionary_id=data.get('dictionary_id'),
            code_value=data.get('code_value'),
            code_description=data.get('description'),
            display_sequence=data.get('display_sequence', 0),
            display_color=data.get('display_color', '#4361ee'),
            parent_id=data.get('parent_id'),
            created_by=current_user.id
        )
        
        if code.parent_id:
            parent = ProjectCodeValue.query.get(code.parent_id)
            code.level = parent.level + 1
            code.full_path = f"{parent.full_path}{parent.dictionary.delimiter}{code.code_value}" if parent.full_path else code.code_value
        else:
            code.level = 1
            code.full_path = code.code_value
        
        db.session.add(code)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@codes_bp.route('/project/dictionary/<int:dictionary_id>/codes', methods=['GET'])
@login_required
def get_project_dictionary_codes(dictionary_id):
    """API لجلب جميع قيم الأكواد لقاموس مشروع معين"""
    dictionary = ProjectCodeDictionary.query.get_or_404(dictionary_id)
    
    if dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # بناء الشجرة
    def build_tree(parent_id=None):
        tree = []
        codes = ProjectCodeValue.query.filter_by(
            dictionary_id=dictionary_id,
            parent_id=parent_id,
            is_active=True
        ).order_by(ProjectCodeValue.display_sequence).all()
        
        for code in codes:
            children = build_tree(code.id)
            code_dict = {
                'id': code.id,
                'code_value': code.code_value,
                'description': code.code_description,
                'display_color': code.display_color,
                'display_sequence': code.display_sequence,
                'level': code.level,
                'full_path': code.full_path,
                'has_children': len(children) > 0,
                'assignments_count': code.assignments.count()
            }
            if children:
                code_dict['children'] = children
            tree.append(code_dict)
        return tree
    
    return jsonify({
        'success': True,
        'dictionary': {
            'id': dictionary.id,
            'name': dictionary.dict_name,
            'description': dictionary.description,
            'is_hierarchical': dictionary.is_hierarchical
        },
        'codes': build_tree()
    })

@codes_bp.route('/project/<int:project_id>/assignments')
@login_required
def get_project_assignments(project_id):
    """الحصول على الأكواد المرتبطة بمشروع"""
    project = Project.query.get_or_404(project_id)
    
    dictionaries = ProjectCodeDictionary.query.filter_by(
        org_id=get_org_id(),
        is_active=True
    ).all()
    
    result = []
    for dict in dictionaries:
        assignment = ProjectCodeAssignment.query.filter_by(
            project_id=project_id,
            dictionary_id=dict.id
        ).first()
        
        result.append({
            'dictionary_id': dict.id,
            'dictionary_name': dict.dict_name,
            'assigned_code_id': assignment.code_value_id if assignment else None,
            'assigned_code': {
                'id': assignment.code_value.id,
                'code_value': assignment.code_value.code_value,
                'display_color': assignment.code_value.display_color
            } if assignment else None
        })
    
    return jsonify({
        'success': True,
        'assignments': result
    })

@codes_bp.route('/api/dictionaries', methods=['GET'])
@login_required
def get_dictionaries():
    """جلب جميع قواميس الأكواد"""
    org_id = get_org_id()
    
    dictionaries = ProjectCodeDictionary.query.filter_by(
        org_id=org_id,
        is_active=True
    ).order_by(ProjectCodeDictionary.dict_name).all()
    
    result = [{
        'id': d.id,
        'name': d.dict_name,
        'description': d.description
    } for d in dictionaries]
    
    return jsonify({'success': True, 'dictionaries': result})

@codes_bp.route('/api/dictionary/<int:dictionary_id>/codes', methods=['GET'])
@login_required
def get_dictionary_codes(dictionary_id):
    """جلب جميع قيم الأكواد لقاموس معين"""
    dictionary = ProjectCodeDictionary.query.get_or_404(dictionary_id)
    
    if dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    # بناء الشجرة
    def build_tree(parent_id=None):
        tree = []
        codes = ProjectCodeValue.query.filter_by(
            dictionary_id=dictionary_id,
            parent_id=parent_id,
            is_active=True
        ).order_by(ProjectCodeValue.display_sequence).all()
        
        for code in codes:
            children = build_tree(code.id)
            code_dict = {
                'id': code.id,
                'code_value': code.code_value,
                'description': code.code_description,
                'display_color': code.display_color,
                'level': code.level,
                'has_children': len(children) > 0
            }
            if children:
                code_dict['children'] = children
            tree.append(code_dict)
        return tree
    
    return jsonify({
        'success': True,
        'codes': build_tree()
    })

@codes_bp.route('/api/project/<int:project_id>/assign', methods=['POST'])
@login_required
def assign_code_to_project(project_id):
    """تعيين كود لمشروع"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    dictionary_id = int(data.get('dictionary_id'))
    code_id = data.get('code_id')
    
    if not dictionary_id or not code_id:
        return jsonify({'success': False, 'error': 'البيانات غير كاملة'}), 400
    
    try:
        # التحقق من صحة الكود
        code = ProjectCodeValue.query.get(code_id)
        if not code or code.dictionary_id != dictionary_id:
            return jsonify({'success': False, 'error': 'قيمة كود غير صالحة'}), 400
        
        # البحث عن تعيين موجود لنفس القاموس
        assignment = ProjectCodeAssignment.query.filter_by(
            project_id=project_id,
            dictionary_id=dictionary_id
        ).first()
        
        if assignment:
            # تحديث التعيين الموجود
            assignment.code_value_id = code_id
        else:
            # إنشاء تعيين جديد
            assignment = ProjectCodeAssignment(
                project_id=project_id,
                dictionary_id=dictionary_id,
                code_value_id=code_id,
                created_by=current_user.id
            )
            db.session.add(assignment)
        
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
@codes_bp.route('/api/projects/<int:project_id>/codeassignments', methods=['GET'])
@login_required
def project_assign(project_id):
    """جلب الأكواد المرتبطة بمشروع"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    assignments = ProjectCodeAssignment.query.filter_by(project_id=project_id).all()
    
    result = []
    for assignment in assignments:
        code = assignment.code_value
        result.append({
            'id': assignment.id,
            'dictionary_id': assignment.dictionary_id,
            'dictionary_name': assignment.dictionary.dict_name,
            'code_value': code.code_value,
            'description': code.code_description,
            'display_color': code.display_color
        })
    
    return jsonify({'success': True, 'assignments': result})

@codes_bp.route('/api/project/<int:project_id>/unassign-multiple', methods=['POST'])
@login_required
def unassign_multiple_codes(project_id):
    """إزالة عدة أكواد من مشروع دفعة واحدة"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    assignment_ids = data.get('assignment_ids', [])
    
    if not assignment_ids:
        return jsonify({'success': False, 'error': 'لا توجد أكواد محددة'}), 400
    
    try:
        # حذف التعيينات المحددة
        deleted = ProjectCodeAssignment.query.filter(
            ProjectCodeAssignment.project_id == project_id,
            ProjectCodeAssignment.id.in_(assignment_ids)
        ).delete(synchronize_session=False)
        
        db.session.commit()
        return jsonify({'success': True, 'count': deleted})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
@codes_bp.route('/api/project/<int:project_id>/unassign/<int:assignment_id>', methods=['DELETE'])
@login_required
def unassign_single_code(project_id, assignment_id):
    """إزالة كود واحد من مشروع"""
    project = Project.query.get_or_404(project_id)
    
    if project.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    assignment = ProjectCodeAssignment.query.get_or_404(assignment_id)
    
    if assignment.project_id != project_id:
        return jsonify({'success': False, 'error': 'التعيين لا ينتمي لهذا المشروع'}), 400
    
    try:
        db.session.delete(assignment)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
       
# أكواد المشاريع - تحديث وحذف
@codes_bp.route('/project/code/<int:code_id>/update', methods=['POST'])
@login_required
def update_project_code(code_id):
    """تحديث قيمة كود مشروع"""
    code = ProjectCodeValue.query.get_or_404(code_id)
    
    if code.dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    data = request.get_json()
    
    try:
        # التحقق من عدم وجود قيمة مكررة (إذا تغيرت القيمة)
        if data.get('code_value') and data['code_value'] != code.code_value:
            existing = ProjectCodeValue.query.filter_by(
                dictionary_id=code.dictionary_id,
                code_value=data['code_value']
            ).first()
            
            if existing:
                return jsonify({'success': False, 'error': 'قيمة الكود موجودة مسبقاً'}), 400
        
        code.code_value = data.get('code_value', code.code_value)
        code.code_description = data.get('description', code.code_description)
        code.display_color = data.get('display_color', code.display_color)
        code.display_sequence = data.get('display_sequence', code.display_sequence)
        code.is_active = data.get('is_active', code.is_active)
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@codes_bp.route('/project/code/<int:code_id>/delete', methods=['POST'])
@login_required
def delete_project_code(code_id):
    """حذف قيمة كود مشروع"""
    code = ProjectCodeValue.query.get_or_404(code_id)
    
    if code.dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    try:
        # التحقق من وجود أبناء
        children_count = ProjectCodeValue.query.filter_by(parent_id=code_id).count()
        if children_count > 0:
            return jsonify({
                'success': False,
                'error': f'لا يمكن حذف الكود لأنه يحتوي على {children_count} أكواد فرعية'
            }), 400
        
        # التحقق من وجود ارتباطات بمشاريع
        assignments_count = code.assignments.count()
        if assignments_count > 0:
            return jsonify({
                'success': False,
                'error': f'لا يمكن حذف الكود لأنه مرتبط بـ {assignments_count} مشاريع'
            }), 400
        
        db.session.delete(code)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
@codes_bp.route('/project/<int:project_id>/unassign', methods=['POST'])
@login_required
def unassign_code_from_project(project_id):
    """إزالة كود من مشروع"""
    data = request.get_json()
    dictionary_id = data.get('dictionary_id')
    
    try:
        assignment = ProjectCodeAssignment.query.filter_by(
            project_id=project_id,
            dictionary_id=dictionary_id
        ).first()
        
        if assignment:
            db.session.delete(assignment)
            db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@codes_bp.route('/project/code/<int:code_id>', methods=['GET'])
@login_required
def get_project_code(code_id):
    """الحصول على تفاصيل كود مشروع"""
    code = ProjectCodeValue.query.get_or_404(code_id)
    
    if code.dictionary.org_id != get_org_id():
        return jsonify({'success': False, 'error': 'غير مصرح'}), 403
    
    return jsonify({
        'success': True,
        'code': {
            'id': code.id,
            'dictionary_id': code.dictionary_id,
            'dictionary_name': code.dictionary.dict_name_ar or code.dictionary.dict_name,
            'code_value': code.code_value,
            'code_description': code.code_description,
            'display_color': code.display_color,
            'display_sequence': code.display_sequence,
            'level': code.level,
            'full_path': code.full_path,
            'is_active': code.is_active,
            'parent_id': code.parent_id,
            'assignments_count': code.assignments.count()
        }
    })
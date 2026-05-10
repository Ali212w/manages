# app/services/resource_service.py

from flask import current_app
from app.models import db
from flask_login import current_user
from app.models import Resource, ActivityResource
from app.models import TaskResource, Task
from app.models import Activity
from app.models import Project
from datetime import datetime
import json

class ResourceService:
    """خدمة إدارة الموارد"""
    
    def __init__(self, org_id):
        self.org_id = org_id
    
    # ============================================
    # إدارة الموارد الأساسية
    # ============================================
    
    def create_resource(self, data):
        """إنشاء مورد جديد مع دعم الحقول الخاصة حسب النوع"""
        try:
            # التحقق من عدم تكرار الكود
            existing = Resource.query.filter_by(
                org_id=self.org_id,
                resource_id=data.get('resource_id')
            ).first()
            
            if existing:
                return {'success': False, 'error': 'كود المورد موجود مسبقاً'}
            
            resource = Resource(
                org_id=self.org_id,
                resource_id=data.get('resource_id'),
                name=data.get('name'),
                resource_type=data.get('resource_type'),
                unit=data.get('unit', 'piece'),
                cost_per_unit=data.get('cost_per_unit', 0),
                available_quantity=data.get('available_quantity', 0),
                currency=data.get('currency', 'SAR'),
                calendar_id=data.get('calendar_id'),
                is_active=True,
                creator_id=current_user.id
            )
            
            # إضافة حقول خاصة حسب النوع
            if data.get('resource_type') == 'labor':
                resource.employee_id = data.get('employeeId')
                resource.specialization = data.get('specialization')
                resource.skills = data.get('skills', [])
                resource.experience_years = data.get('experience_years', 0)
            elif data.get('resource_type') == 'equipment':
                resource.equipment_type = data.get('equipment_type')
                resource.equipment_model = data.get('equipment_model')
                resource.manufacturer = data.get('manufacturer')
                resource.supplier_id = data.get('supplier_id')
            elif data.get('resource_type') == 'material':
                resource.material_type = data.get('material_type')
                resource.material_grade = data.get('material_grade')
                resource.supplier_id = data.get('supplier_id')
                resource.minimum_quantity = data.get('minimum_quantity', 0)
                resource.reorder_quantity = data.get('reorder_quantity', 0)
            
            db.session.add(resource)
            db.session.commit()
            
            return {'success': True, 'resource': resource.to_dict()}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def get_resource(self, resource_id):
        """الحصول على مورد مع تفاصيله"""
        resource = Resource.query.get_or_404(resource_id)
        if resource.org_id != self.org_id:
            return {'success': False, 'error': 'غير مصرح'}
        
        # حساب الكمية المخصصة
        total_allocated = resource.get_total_assigned()
        
        resource_dict = resource.to_dict()
        resource_dict['total_allocated'] = total_allocated
        resource_dict['remaining_quantity'] = resource.available_quantity - total_allocated
        resource_dict['utilization'] = resource.utilization
        
        return {'success': True, 'resource': resource_dict}
    
    def update_resource(self, resource_id, data):
        """تحديث مورد"""
        resource = Resource.query.get_or_404(resource_id)
        
        if resource.org_id != self.org_id:
            return {'success': False, 'error': 'غير مصرح'}
        
        try:
            # تحديث الحقول الأساسية
            for key in ['name',  'unit', 'cost_per_unit', 
                        'available_quantity', 'currency', 'calendar_id', 'is_active']:
                if key in data:
                    setattr(resource, key, data[key])
            
            # تحديث الحقول الخاصة حسب النوع
            if resource.resource_type == 'labor':
                if 'employeeId' in data:
                    resource.employee_id = data['employeeId']
                if 'specialization' in data:
                    resource.specialization = data['specialization']
                if 'skills' in data:
                    resource.skills = data['skills']
            elif resource.resource_type == 'equipment':
                if 'equipment_type' in data:
                    resource.equipment_type = data['equipment_type']
                if 'equipment_model' in data:
                    resource.equipment_model = data['equipment_model']
            elif resource.resource_type == 'material':
                if 'material_type' in data:
                    resource.material_type = data['material_type']
                if 'minimum_quantity' in data:
                    resource.minimum_quantity = data['minimum_quantity']
                if 'supplier_id' in data:
                    resource.supplier_id = data['supplier_id']
            
            # لا يمكن تعديل كود المورد
            db.session.commit()
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def delete_resource(self, resource_id):
        """حذف مورد"""
        resource = Resource.query.get_or_404(resource_id)
        if resource.org_id != self.org_id:
            return {'success': False, 'error': 'غير مصرح'}
        
        try:
            # التحقق من وجود تعيينات في الأنشطة
            if resource.assignments.count() > 0:
                return {'success': False, 'error': 'لا يمكن حذف المورد لأنه مرتبط بأنشطة'}
            
            # التحقق من وجود تعيينات في المهام
            if resource.task_assignments.count() > 0:
                return {'success': False, 'error': 'لا يمكن حذف المورد لأنه مرتبط بمهام'}
            
            db.session.delete(resource)
            db.session.commit()
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # توزيع الموارد على الأنشطة
    # ============================================
    
    def allocate_resource_to_activity(self, activity_id, resource_id, quantity):
        """تخصيص مورد لنشاط"""
        activity = Activity.query.get_or_404(activity_id)
        resource = Resource.query.get_or_404(resource_id)
        
        # التحقق من توفر الكمية
        available = resource.available_quantity - resource.get_total_assigned()
        if quantity > available:
            return {
                'success': False, 
                'error': f'الكمية غير متوفرة. المتاح: {available} {resource.unit}'
            }
        
        try:
            # البحث عن تعيين موجود
            assignment = ActivityResource.query.filter_by(
                activity_id=activity_id,
                resource_id=resource_id
            ).first()
            
            if assignment:
                # تحديث التعيين
                assignment.planned_quantity += quantity
                assignment.planned_cost = assignment.planned_quantity * resource.cost_per_unit
                assignment.remaining_quantity = assignment.planned_quantity - assignment.actual_quantity
            else:
                # إنشاء تعيين جديد
                assignment = ActivityResource(
                    activity_id=activity_id,
                    resource_id=resource_id,
                    planned_quantity=quantity,
                    planned_cost=quantity * resource.cost_per_unit,
                    remaining_quantity=quantity,
                    allocated_quantity=quantity,
                    created_by=current_user.id
                )
                db.session.add(assignment)
            
            # تحديث الكمية المخصصة في المورد
            resource.total_allocated = resource.get_total_assigned()
            resource.update_utilization()
            
            db.session.commit()
            return {'success': True, 'assignment': assignment.id}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def get_activity_resources(self, activity_id):
        """جلب موارد النشاط"""
        activity = Activity.query.get_or_404(activity_id)
        
        assignments = ActivityResource.query.filter_by(activity_id=activity_id).all()
        
        resources = []
        for assign in assignments:
            resource = assign.resource
            resources.append({
                'id': assign.id,
                'resource_id': resource.id,
                'resource_name': resource.name,
                'resource_code': resource.resource_id,
                'resource_type': resource.resource_type,
                'unit': resource.unit,
                'planned_quantity': assign.planned_quantity,
                'actual_quantity': assign.actual_quantity,
                'remaining_quantity': assign.remaining_quantity,
                'planned_cost': assign.planned_cost,
                'actual_cost': assign.actual_cost,
                'cost_per_unit': resource.cost_per_unit,
                'utilization': (assign.actual_quantity / assign.planned_quantity * 100) if assign.planned_quantity > 0 else 0
            })
        
        return {'success': True, 'resources': resources}
    
    def update_activity_resource(self, assignment_id, quantity):
        """تحديث كمية مورد في نشاط"""
        assignment = ActivityResource.query.get_or_404(assignment_id)
        
        if quantity <= 0:
            return {'success': False, 'error': 'الكمية يجب أن تكون أكبر من صفر'}
        
        try:
            # الفرق في الكمية
            diff = quantity - assignment.planned_quantity
            
            if diff > 0:
                # زيادة الكمية
                resource = assignment.resource
                available = resource.available_quantity - resource.get_total_assigned()
                if available < diff:
                    return {
                        'success': False,
                        'error': f'الكمية غير متوفرة. المتاح: {available} {resource.unit}'
                    }
                resource.total_allocated += diff
            elif diff < 0:
                # تقليل الكمية
                assignment.resource.total_allocated += diff  # diff سالب
            
            assignment.planned_quantity = quantity
            assignment.planned_cost = quantity * assignment.resource.cost_per_unit
            assignment.remaining_quantity = quantity - assignment.actual_quantity
            assignment.resource.update_utilization()
            
            db.session.commit()
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def remove_activity_resource(self, assignment_id):
        """إزالة مورد من نشاط"""
        assignment = ActivityResource.query.get_or_404(assignment_id)
        
        try:
            # تحرير الكمية المخصصة
            assignment.resource.total_allocated -= assignment.planned_quantity
            assignment.resource.update_utilization()
            
            db.session.delete(assignment)
            db.session.commit()
            return {'success': True}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    # ============================================
    # توزيع موارد النشاط على المهام
    # ============================================
    
    def allocate_resource_to_task(self, task_id, activity_resource_id, quantity, allocation_percentage=0):
        """توزيع مورد من النشاط على مهمة"""
        task = Task.query.get_or_404(task_id)
        activity_resource = ActivityResource.query.get_or_404(activity_resource_id)
        
        # التحقق من أن المورد ينتمي لنفس النشاط
        if activity_resource.activity_id != task.activity_id:
            return {'success': False, 'error': 'المورد لا ينتمي للنشاط المرتبط بالمهمة'}
        
        # التحقق من أن الكمية لا تتجاوز المتاح
        if quantity > activity_resource.remaining_quantity:
            return {
                'success': False,
                'error': f'الكمية غير متوفرة. المتاح: {activity_resource.remaining_quantity}'
            }
        
        try:
            # حساب التكلفة
            resource = activity_resource.resource
            cost = quantity * resource.cost_per_unit
            
            # إنشاء تعيين للمهمة
            task_assignment = TaskResource(
                task_id=task_id,
                resource_id=resource.id,
                activity_resource_id=activity_resource_id,
                planned_quantity=quantity,
                planned_cost=cost,
                allocation_percentage=allocation_percentage or (quantity / activity_resource.planned_quantity * 100),
                created_by=current_user.id
            )
            db.session.add(task_assignment)
            
            # تحديث الكمية المتبقية في النشاط
            activity_resource.remaining_quantity -= quantity
            activity_resource.remaining_cost -= cost
            
            db.session.commit()
            
            return {'success': True, 'task_assignment': task_assignment.id}
            
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def get_task_resources(self, task_id):
        """جلب موارد المهمة"""
        task = Task.query.get_or_404(task_id)
        
        assignments = TaskResource.query.filter_by(task_id=task_id).all()
        
        resources = []
        for assign in assignments:
            resource = assign.resource
            resources.append({
                'id': assign.id,
                'resource_id': resource.id,
                'resource_name': resource.name,
                'resource_type': resource.resource_type,
                'unit': resource.unit,
                'planned_quantity': assign.planned_quantity,
                'actual_quantity': assign.actual_quantity,
                'planned_cost': assign.planned_cost,
                'actual_cost': assign.actual_cost,
                'cost_per_unit': resource.cost_per_unit,
                'allocation_percentage': assign.allocation_percentage,
                'status': assign.status if hasattr(assign, 'status') else 'pending'
            })
        
        return {'success': True, 'resources': resources}
    
    # ============================================
    # إحصائيات الموارد
    # ============================================
    
    def get_resource_summary(self, project_id=None):
        """ملخص استخدام الموارد"""
        query = Resource.query.filter_by(org_id=self.org_id)
        
        if project_id:
            # فلترة حسب المشروع عبر الأنشطة
            project = Project.query.get(project_id)
            if project:
                activity_ids = [a.id for a in project.activities]
                resource_ids = db.session.query(ActivityResource.resource_id).filter(
                    ActivityResource.activity_id.in_(activity_ids)
                ).distinct().all()
                query = query.filter(Resource.id.in_([r[0] for r in resource_ids]))
        
        resources = query.all()
        
        summary = {
            'total_resources': len(resources),
            'by_type': {
                'labor': 0,
                'material': 0,
                'equipment': 0,
                'non_labor': 0
            },
            'total_allocated': 0,
            'total_available': 0,
            'total_cost': 0,
            'resources_list': []
        }
        
        for resource in resources:
            summary['by_type'][resource.resource_type] += 1
            summary['total_available'] += resource.available_quantity
            allocated = resource.get_total_assigned()
            summary['total_allocated'] += allocated
            
            resource_data = resource.to_dict()
            resource_data['total_allocated'] = allocated
            resource_data['remaining_quantity'] = resource.available_quantity - allocated
            resource_data['utilization'] = resource.utilization
            resource_data['total_cost'] = allocated * resource.cost_per_unit
            
            summary['total_cost'] += resource_data['total_cost']
            summary['resources_list'].append(resource_data)
        
        return {'success': True, 'summary': summary}
    
    def get_available_resources(self):
        """جلب الموارد المتاحة للاختيار"""
        resources = Resource.query.filter_by(
            org_id=self.org_id,
            is_active=True
        ).all()
        
        available = []
        for resource in resources:
            available_qty = resource.available_quantity - resource.get_total_assigned()
            if available_qty > 0:
                available.append({
                    'id': resource.id,
                    'resource_id': resource.resource_id,
                    'name': resource.name,
                    'resource_type': resource.resource_type,
                    'unit': resource.unit,
                    'available_quantity': available_qty,
                    'cost_per_unit': resource.cost_per_unit
                })
        
        return {'success': True, 'resources': available}
    
    def get_low_stock_resources(self):
        """جلب الموارد ذات المخزون المنخفض"""
        resources = Resource.query.filter_by(
            org_id=self.org_id,
            resource_type='material',
            is_active=True
        ).all()
        
        low_stock = []
        for resource in resources:
            remaining = resource.available_quantity - resource.get_total_assigned()
            if resource.minimum_quantity and remaining <= resource.minimum_quantity:
                low_stock.append({
                    'id': resource.id,
                    'name': resource.name,
                    'resource_id': resource.resource_id,
                    'available': remaining,
                    'minimum': resource.minimum_quantity,
                    'unit': resource.unit
                })
        
        return {'success': True, 'resources': low_stock}
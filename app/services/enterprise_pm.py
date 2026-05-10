"""
enterprise_pm.py - نظام إدارة المشاريع المؤسسي المتكامل
يشبه Primavera P6 مع إضافات ذكية وإدارة ذاتية
"""
from datetime import datetime, date, timedelta
from flask import current_app
from app.models import db, Project, Task, User, Notification, Risk, Issue,WBS
from app.services.notification_service import NotificationService
import numpy as np
import json
from collections import defaultdict

class EnterpriseProjectManager:
    """نظام إدارة المشاريع المؤسسي - الإصدار الذكي"""
    
    def __init__(self, app=None):
        self.app = app
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """تهيئة النظام مع التطبيق"""
        self.app = app
        app.enterprise_pm = self
        
    # ============================================
    # 1. هيكل تقسيم العمل (WBS) - Work Breakdown Structure
    # ============================================
    
    def create_wbs(self, project_id, wbs_data):
        """
        إنشاء هيكل تقسيم العمل للمشروع
        يشبه WBS في Primavera
        """
        from app.models import WBSNode
        
        project = Project.query.get(project_id)
        if not project:
            return {'error': 'المشروع غير موجود'}
        
        wbs_nodes = []
        
        def create_node(data, parent_id=None, level=0):
            node = WBS(
                project_id=project_id,
                parent_id=parent_id,
                wbs_code=data.get('code', f"WBS-{len(wbs_nodes)+1}"),
                wbs_level=level,
                name=data.get('name', ''),
                name_ar=data.get('name_ar', ''),
                description=data.get('description', ''),
                node_type=data.get('type', 'deliverable'),
                weight=data.get('weight', 0.0),
                budget=data.get('budget', 0.0)
            )
            db.session.add(node)
            db.session.flush()
            wbs_nodes.append(node)
            
            # إنشاء العقد الفرعية
            for child in data.get('children', []):
                create_node(child, node.id, level + 1)
            
            return node
        
        try:
            for root_node in wbs_data:
                create_node(root_node)
            
            db.session.commit()
            
            return {
                'success': True,
                'nodes': len(wbs_nodes),
                'message': f'تم إنشاء {len(wbs_nodes)} عقدة في هيكل المشروع'
            }
            
        except Exception as e:
            db.session.rollback()
            return {'error': str(e)}
    
    def get_wbs_hierarchy(self, project_id):
        """استخراج هيكل المشروع بشكل هرمي"""
        from app.models import WBSNode
        
        nodes = WBSNode.query.filter_by(project_id=project_id).order_by(WBSNode.wbs_level).all()
        
        # بناء الشجرة
        hierarchy = {}
        root_nodes = []
        
        for node in nodes:
            hierarchy[node.id] = {
                'id': node.id,
                'code': node.wbs_code,
                'name': node.name,
                'name_ar': node.name_ar,
                'type': node.node_type,
                'level': node.wbs_level,
                'weight': node.weight,
                'budget': node.budget,
                'actual_cost': node.actual_cost,
                'progress': node.progress,
                'children': []
            }
        
        for node in nodes:
            if node.parent_id and node.parent_id in hierarchy:
                hierarchy[node.parent_id]['children'].append(hierarchy[node.id])
            else:
                root_nodes.append(hierarchy[node.id])
        
        return root_nodes
    
    # ============================================
    # 2. الجدولة الزمنية (Scheduling) - مثل Primavera
    # ============================================
    
    def calculate_schedule(self, project_id):
        """
        حساب الجدول الزمني للمشروع باستخدام CPM
        (Critical Path Method) مثل Primavera
        """
        from app.models import Task
        
        tasks = Task.query.filter_by(project_id=project_id).order_by(Task.task_order).all()
        
        if not tasks:
            return {'error': 'لا توجد مهام في المشروع'}
        
        # بناء خريطة التبعيات
        task_map = {task.id: task for task in tasks}
        dependencies = {}
        dependents = {}
        
        for task in tasks:
            if task.depends_on_task_id:
                if task.depends_on_task_id not in dependencies:
                    dependencies[task.depends_on_task_id] = []
                dependencies[task.depends_on_task_id].append(task.id)
                
                if task.id not in dependents:
                    dependents[task.id] = []
                dependents[task.id].append(task.depends_on_task_id)
        
        # Forward Pass - حساب التواريخ المبكرة
        early_start = {}
        early_finish = {}
        
        for task in tasks:
            if not dependents.get(task.id):  # مهام بدون مهام سابقة
                early_start[task.id] = task.planned_start_date
            else:
                pred_dates = [early_finish[pred] for pred in dependents[task.id] 
                             if pred in early_finish and early_finish[pred]]
                early_start[task.id] = max(pred_dates) if pred_dates else task.planned_start_date
            
            if early_start[task.id] and task.planned_duration:
                early_finish[task.id] = early_start[task.id] + timedelta(days=task.planned_duration)
            else:
                early_finish[task.id] = task.planned_end_date
        
        # Backward Pass - حساب التواريخ المتأخرة
        late_start = {}
        late_finish = {}
        
        project_end = max([early_finish[t.id] for t in tasks if early_finish[t.id]] or [date.today()])
        
        for task in reversed(tasks):
            if not dependencies.get(task.id):  # مهام بدون مهام تالية
                late_finish[task.id] = project_end
            else:
                succ_dates = [late_start[succ] for succ in dependencies[task.id] 
                             if succ in late_start and late_start[succ]]
                late_finish[task.id] = min(succ_dates) if succ_dates else project_end
            
            if late_finish[task.id] and task.planned_duration:
                late_start[task.id] = late_finish[task.id] - timedelta(days=task.planned_duration)
            else:
                late_start[task.id] = task.planned_start_date
        
        # حساب المسار الحرج
        critical_path = []
        for task in tasks:
            if task.id in early_start and task.id in late_start:
                if early_start[task.id] and late_start[task.id]:
                    float_time = (late_start[task.id] - early_start[task.id]).days
                    if abs(float_time) <= 1:  # المهام الحرجة
                        critical_path.append(task.id)
        
        # تحديث المهام في قاعدة البيانات
        for task in tasks:
            task.early_start = early_start.get(task.id)
            task.early_finish = early_finish.get(task.id)
            task.late_start = late_start.get(task.id)
            task.late_finish = late_finish.get(task.id)
            task.is_critical = task.id in critical_path
        
        db.session.commit()
        
        return {
            'success': True,
            'project_end': project_end,
            'total_tasks': len(tasks),
            'critical_tasks': len(critical_path),
            'schedule': {
                'early_start': {str(k): v.isoformat() if v else None for k, v in early_start.items()},
                'early_finish': {str(k): v.isoformat() if v else None for k, v in early_finish.items()},
                'late_start': {str(k): v.isoformat() if v else None for k, v in late_start.items()},
                'late_finish': {str(k): v.isoformat() if v else None for k, v in late_finish.items()}
            }
        }
    
    # ============================================
    # 3. توزيع الموارد (Resource Allocation)
    # ============================================
    
    def allocate_resources(self, project_id):
        """
        توزيع الموارد على المهام بشكل ذكي
        مثل Resource Leveling في Primavera
        """
        from app.models import Task, User, TaskAssignment
        
        tasks = Task.query.filter_by(project_id=project_id, status='pending').order_by(
            Task.priority.desc(), Task.planned_start_date
        ).all()
        
        users = User.query.filter_by(org_id=Project.query.get(project_id).org_id, is_user_active=True).all()
        
        # تحميل الموارد الحالية للمستخدمين
        user_load = {}
        user_skills = {}
        
        for user in users:
            current_tasks = TaskAssignment.query.filter_by(
                user_id=user.id,
                status.in_(['assigned', 'accepted', 'in_progress'])
            ).count()
            
            user_load[user.id] = {
                'user': user,
                'current_tasks': current_tasks,
                'max_tasks': 5,  # حد أقصى
                'allocated_tasks': []
            }
            
            if hasattr(user, 'skills') and user.skills:
                user_skills[user.id] = user.skills
        
        # توزيع المهام
        allocations = []
        for task in tasks:
            best_user = None
            best_score = -1
            
            for user_id, load in user_load.items():
                if load['current_tasks'] + len(load['allocated_tasks']) >= load['max_tasks']:
                    continue
                
                # حساب درجة التوافق
                score = 0
                
                # التوافق مع المهارات
                if task.required_skills and user_id in user_skills:
                    common = set(task.required_skills) & set(user_skills[user_id])
                    score += len(common) * 10
                
                # توفر المستخدم
                score += (load['max_tasks'] - (load['current_tasks'] + len(load['allocated_tasks']))) * 5
                
                # أداء سابق (يمكن إضافته لاحقاً)
                
                if score > best_score:
                    best_score = score
                    best_user = user_id
            
            if best_user:
                user_load[best_user]['allocated_tasks'].append(task.id)
                allocations.append({
                    'task_id': task.id,
                    'task_name': task.task_name,
                    'user_id': best_user,
                    'user_name': user_load[best_user]['user'].full_name,
                    'score': best_score
                })
        
        return {
            'success': True,
            'total_tasks': len(tasks),
            'allocated': len(allocations),
            'allocations': allocations
        }
    
    # ============================================
    # 4. إدارة القيمة المكتسبة (EVM) - Earned Value Management
    # ============================================
    
    def calculate_evm(self, project_id):
        """
        حساب مؤشرات الأداء باستخدام EVM
        مثل Primavera
        """
        from app.models import Task, WBSNode
        
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        if not tasks:
            return {'error': 'لا توجد مهام'}
        
        # Planned Value (PV)
        pv = 0
        # Earned Value (EV)
        ev = 0
        # Actual Cost (AC)
        ac = 0
        
        task_details = []
        for task in tasks:
            task_pv = task.planned_cost or 0
            task_ev = task_pv * (task.progress_percentage / 100) if task.progress_percentage else 0
            task_ac = task.actual_cost or 0
            
            pv += task_pv
            ev += task_ev
            ac += task_ac
            
            task_details.append({
                'id': task.id,
                'name': task.task_name,
                'pv': task_pv,
                'ev': task_ev,
                'ac': task_ac,
                'progress': task.progress_percentage
            })
        
        # مؤشرات الأداء
        cv = ev - ac  # Cost Variance
        sv = ev - pv  # Schedule Variance
        cpi = ev / ac if ac > 0 else 1.0  # Cost Performance Index
        spi = ev / pv if pv > 0 else 1.0  # Schedule Performance Index
        
        # تقدير عند الاكتمال
        eac = ac + (pv - ev) / cpi if cpi > 0 else pv  # Estimate at Completion
        etc = eac - ac  # Estimate to Complete
        vac = pv - eac  # Variance at Completion
        
        return {
            'success': True,
            'project_name': project.name,
            'evm': {
                'pv': round(pv, 2),
                'ev': round(ev, 2),
                'ac': round(ac, 2),
                'cv': round(cv, 2),
                'sv': round(sv, 2),
                'cpi': round(cpi, 2),
                'spi': round(spi, 2),
                'eac': round(eac, 2),
                'etc': round(etc, 2),
                'vac': round(vac, 2)
            },
            'status': {
                'cost': 'تحت الميزانية' if cv > 0 else 'تجاوز الميزانية' if cv < 0 else 'ضمن الميزانية',
                'schedule': 'متقدم' if sv > 0 else 'متأخر' if sv < 0 else 'ضمن الجدول'
            },
            'tasks': task_details
        }
    
    # ============================================
    # 5. إدارة المخاطر (Risk Management)
    # ============================================
    
    def analyze_risks(self, project_id):
        """
        تحليل المخاطر وتحديد أولوياتها
        """
        from app.models import Risk
        
        risks = Risk.query.filter_by(project_id=project_id).all()
        
        risk_matrix = {
            'critical': [],
            'high': [],
            'medium': [],
            'low': []
        }
        
        for risk in risks:
            risk_score = risk.probability * risk.impact
            
            if risk_score >= 0.7:
                risk_matrix['critical'].append(risk)
            elif risk_score >= 0.5:
                risk_matrix['high'].append(risk)
            elif risk_score >= 0.3:
                risk_matrix['medium'].append(risk)
            else:
                risk_matrix['low'].append(risk)
        
        return {
            'success': True,
            'total_risks': len(risks),
            'risk_matrix': {
                'critical': len(risk_matrix['critical']),
                'high': len(risk_matrix['high']),
                'medium': len(risk_matrix['medium']),
                'low': len(risk_matrix['low'])
            },
            'risks': risk_matrix
        }
    
    # ============================================
    # 6. إدارة التغيير (Change Management)
    # ============================================
    
    def process_change_request(self, change_request_id, decision, notes=''):
        """
        معالجة طلبات التغيير
        """
        from app.models import ChangeRequest, Project
        
        cr = ChangeRequest.query.get(change_request_id)
        if not cr:
            return {'error': 'طلب التغيير غير موجود'}
        
        cr.status = 'approved' if decision == 'approve' else 'rejected'
        cr.decision = decision
        cr.decision_notes = notes
        cr.decision_date = datetime.utcnow()
        
        db.session.commit()
        
        # إشعار للمعنيين
        if decision == 'approve':
            # تحديث المشروع حسب طلب التغيير
            project = Project.query.get(cr.project_id)
            
            # إرسال إشعارات
            NotificationService.system_alert(
                title=f'✅ تمت الموافقة على طلب التغيير: {cr.title}',
                message=f'تمت الموافقة على طلب التغيير وسيتم تطبيقه على المشروع',
                priority='high'
            )
        
        return {
            'success': True,
            'message': f'تم {cr.status} طلب التغيير'
        }
    
    # ============================================
    # 7. التقارير المتقدمة (Advanced Reporting)
    # ============================================
    
    def generate_portfolio_report(self, org_id):
        """
        تقرير شامل عن جميع المشاريع في المؤسسة
        مثل Portfolio Analysis في Primavera
        """
        projects = Project.query.filter_by(org_id=org_id).all()
        
        portfolio = {
            'total_projects': len(projects),
            'total_budget': 0,
            'total_actual': 0,
            'projects_by_status': defaultdict(int),
            'projects_by_type': defaultdict(int),
            'performance': []
        }
        
        for project in projects:
            portfolio['total_budget'] += project.contract_value or 0
            
            # حساب التكلفة الفعلية
            actual_cost = sum([task.actual_cost or 0 for task in project.tasks])
            portfolio['total_actual'] += actual_cost
            
            portfolio['projects_by_status'][project.status] += 1
            portfolio['projects_by_type'][project.project_type or 'غير محدد'] += 1
            
            # حساب مؤشرات الأداء
            evm = self.calculate_evm(project.id)
            
            portfolio['performance'].append({
                'id': project.id,
                'name': project.name,
                'code': project.project_code,
                'status': project.status,
                'progress': project.progress_percentage,
                'budget': project.contract_value,
                'actual': actual_cost,
                'cpi': evm.get('evm', {}).get('cpi', 1.0) if isinstance(evm, dict) else 1.0,
                'spi': evm.get('evm', {}).get('spi', 1.0) if isinstance(evm, dict) else 1.0
            })
        
        return portfolio
    
    # ============================================
    # 8. تحليل السيناريوهات (What-If Analysis)
    # ============================================
    
    def what_if_analysis(self, project_id, scenario):
        """
        تحليل ماذا لو - What-If Analysis
        مثل Primavera
        """
        from app.models import Task
        
        project = Project.query.get(project_id)
        tasks = Task.query.filter_by(project_id=project_id).all()
        
        original_duration = (project.planned_end_date - project.planned_start_date).days if project.planned_end_date and project.planned_start_date else 0
        
        scenario_results = {
            'original': {
                'end_date': project.planned_end_date,
                'duration': original_duration,
                'cost': project.contract_value
            },
            'scenario': {}
        }
        
        # سيناريو 1: تأخير مهمة حرجة
        if scenario.get('delay_task'):
            task_id = scenario['delay_task']['id']
            delay_days = scenario['delay_task']['days']
            
            task = Task.query.get(task_id)
            if task and task.is_critical:
                new_end = project.planned_end_date + timedelta(days=delay_days)
                scenario_results['scenario']['delay_task'] = {
                    'task': task.task_name,
                    'new_end_date': new_end,
                    'impact_days': delay_days,
                    'impact_cost': delay_days * 1000  # تقدير مبسط
                }
        
        # سيناريو 2: إضافة موارد
        if scenario.get('add_resources'):
            resource_count = scenario['add_resources']['count']
            efficiency_gain = min(resource_count * 0.1, 0.5)  # 10% تحسن لكل مورد إضافي
            
            new_duration = int(original_duration * (1 - efficiency_gain))
            scenario_results['scenario']['add_resources'] = {
                'resources_added': resource_count,
                'new_duration': new_duration,
                'saved_days': original_duration - new_duration
            }
        
        # سيناريو 3: تغيير الميزانية
        if scenario.get('budget_change'):
            change_percent = scenario['budget_change']['percent']
            new_budget = project.contract_value * (1 + change_percent/100)
            
            scenario_results['scenario']['budget_change'] = {
                'change_percent': change_percent,
                'new_budget': new_budget,
                'difference': new_budget - project.contract_value
            }
        
        return scenario_results
    
    # ============================================
    # 9. إدارة العقود والمشتريات (Contracts & Procurement)
    # ============================================
    
    def manage_contract(self, contract_data):
        """
        إدارة العقود والمشتريات
        """
        from app.models import Contract, PurchaseOrder
        
        # إنشاء عقد جديد
        contract = Contract(
            project_id=contract_data['project_id'],
            contract_number=contract_data.get('number'),
            title=contract_data['title'],
            contractor=contract_data['contractor'],
            value=contract_data['value'],
            start_date=datetime.strptime(contract_data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(contract_data['end_date'], '%Y-%m-%d').date(),
            status='active',
            created_by=contract_data['created_by']
        )
        
        db.session.add(contract)
        db.session.flush()
        
        # إنشاء أوامر الشراء المرتبطة
        for po_data in contract_data.get('purchase_orders', []):
            po = PurchaseOrder(
                project_id=contract_data['project_id'],
                po_number=po_data['number'],
                supplier_id=po_data['supplier_id'],
                total_amount=po_data['amount'],
                status='pending',
                created_by=contract_data['created_by']
            )
            db.session.add(po)
        
        db.session.commit()
        
        return {
            'success': True,
            'contract_id': contract.id,
            'message': 'تم إنشاء العقد بنجاح'
        }
    
    # ============================================
    # 10. الإدارة الذاتية (Self Management)
    # ============================================
    
    def auto_optimize_project(self, project_id):
        """
        تحسين المشروع ذاتياً - الميزة الذكية
        """
        project = Project.query.get(project_id)
        
        optimizations = []
        
        # 1. تحسين الجدول الزمني
        schedule = self.calculate_schedule(project_id)
        if schedule.get('success'):
            critical_count = schedule.get('critical_tasks', 0)
            if critical_count > len(project.tasks) * 0.3:
                optimizations.append({
                    'type': 'schedule',
                    'action': 'إعادة توزيع الموارد على المهام الحرجة',
                    'priority': 'high'
                })
        
        # 2. تحسين الموارد
        allocation = self.allocate_resources(project_id)
        if allocation.get('success'):
            if allocation['allocated'] < allocation['total_tasks']:
                optimizations.append({
                    'type': 'resources',
                    'action': f'توجد {allocation["total_tasks"] - allocation["allocated"]} مهام غير موزعة',
                    'priority': 'medium'
                })
        
        # 3. تحليل المخاطر
        risks = self.analyze_risks(project_id)
        if risks.get('success'):
            if risks['risk_matrix']['critical'] > 0:
                optimizations.append({
                    'type': 'risk',
                    'action': 'توجد مخاطر حرجة تحتاج معالجة فورية',
                    'priority': 'critical'
                })
        
        # 4. تحليل الأداء
        evm = self.calculate_evm(project_id)
        if evm.get('success'):
            if evm['evm']['cpi'] < 0.8:
                optimizations.append({
                    'type': 'cost',
                    'action': 'تجاوز الميزانية - يوصى بمراجعة التكاليف',
                    'priority': 'high'
                })
            if evm['evm']['spi'] < 0.8:
                optimizations.append({
                    'type': 'schedule',
                    'action': 'تأخر في الجدول - يوصى بتسريع العمل',
                    'priority': 'high'
                })
        
        # تطبيق التحسينات المقترحة
        for opt in optimizations:
            if opt['priority'] == 'critical':
                # إشعار فوري للمدير
                NotificationService.system_alert(
                    user_id=project.project_manager_id,
                    title=f'🚨 تنبيه حرج: {project.name}',
                    message=opt['action'],
                    priority='critical'
                )
        
        return {
            'success': True,
            'project': project.name,
            'optimizations': optimizations,
            'recommendations': len(optimizations)
        }
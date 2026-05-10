"""
dashboard_service.py - خدمة جلب بيانات لوحة التحكم المتقدمة
"""

from datetime import datetime, timedelta, date
from sqlalchemy import func, and_, or_
from app import db
from app.models import (
    Project, Activity, Task, TaskPlanning, TaskExecution, TaskAssignment,
    Resource, ActivityResource, ProjectDocument, Invoice, Payment,
    User, ProjectProgress, ProjectPerformance, ProjectCost, ProjectBudget,
    Issue, QualityCheck, Milestone
)
import logging

logger = logging.getLogger(__name__)


class DashboardService:
    """خدمة جلب وتحليل بيانات لوحة التحكم"""
    
    @staticmethod
    def get_general_stats(filters):
        """
        الحصول على الإحصائيات العامة
        
        Args:
            filters: dict يحتوي على معاملات التصفية
                - project: معرف المشروع أو 'all'
                - zone: المنطقة أو 'all'
                - sub: اسم المقاول من الباطن أو 'all'
                - responsible: المسؤولية أو 'all'
                - date_from: تاريخ البداية
                - date_to: تاريخ النهاية
        
        Returns:
            dict: الإحصائيات العامة
        """
        try:
            # بناء الاستعلام الأساسي للمشاريع
            query = Project.query
            
            # تطبيق فلتر المشروع
            if filters.get('project') and filters.get('project') != 'all':
                query = query.filter(Project.id == int(filters['project']))
            
            projects = query.all()
            
            # حساب الإحصائيات
            total_projects = len(projects)
            active_projects = len([p for p in projects if p.status == 'active'])
            completed_projects = len([p for p in projects if p.status == 'completed'])
            planning_projects = len([p for p in projects if p.status == 'planning'])
            delayed_projects = len([p for p in projects if p.is_overdue])
            
            # الميزانيات والتكاليف
            total_budget = sum(p.budget.current_budget if p.budget else 0 for p in projects)
            total_actual_cost = sum(p.cost.total_actual_cost if p.cost else 0 for p in projects)
            total_variance = total_budget - total_actual_cost
            
            # التقدم
            total_progress = sum(p.get_progress() for p in projects)
            avg_progress = total_progress / total_projects if total_projects > 0 else 0
            
            # إجمالي المهام
            total_tasks = 0
            completed_tasks = 0
            for project in projects:
                tasks = Task.query.filter_by(project_id=project.id).all()
                total_tasks += len(tasks)
                completed_tasks += len([t for t in tasks if t.status == 'completed'])
            
            return {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'completed_projects': completed_projects,
                'planning_projects': planning_projects,
                'delayed_projects': delayed_projects,
                'total_budget': total_budget,
                'total_actual_cost': total_actual_cost,
                'total_variance': total_variance,
                'avg_progress': round(avg_progress, 1),
                'total_tasks': total_tasks,
                'completed_tasks': completed_tasks,
                'task_completion_rate': round((completed_tasks / total_tasks * 100), 1) if total_tasks > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"خطأ في get_general_stats: {str(e)}")
            return DashboardService._get_empty_general_stats()
    
    @staticmethod
    def _get_empty_general_stats():
        """إرجاع إحصائيات عامة فارغة"""
        return {
            'total_projects': 0, 'active_projects': 0, 'completed_projects': 0,
            'planning_projects': 0, 'delayed_projects': 0, 'total_budget': 0,
            'total_actual_cost': 0, 'total_variance': 0, 'avg_progress': 0,
            'total_tasks': 0, 'completed_tasks': 0, 'task_completion_rate': 0
        }
    
    @staticmethod
    def get_delay_analysis(filters):
        """
        تحليل التأخيرات وتصنيف المسؤولية
        
        Args:
            filters: dict معاملات التصفية
        
        Returns:
            dict: تحليل التأخيرات
        """
        try:
            # بناء استعلام الأنشطة
            query = Activity.query
            
            # تطبيق فلاتر المشروع
            if filters.get('project') and filters.get('project') != 'all':
                query = query.filter(Activity.project_id == int(filters['project']))
            
            # تطبيق فلتر المنطقة
            if filters.get('zone') and filters.get('zone') != 'all':
                query = query.filter(Activity.zone == filters['zone'])
            
            # تطبيق فلتر المسؤولية
            responsible_filter = filters.get('responsible')
            
            activities = query.all()
            
            # حساب التأخيرات
            total_delay_days = 0
            net_contractor_delay = 0
            net_client_delay = 0
            concurrent_delays = 0
            delayed_activities = []
            delay_by_zone = {}
            delay_by_trade = {}
            
            today = date.today()
            
            for activity in activities:
                if activity.planned_finish and activity.status != 'completed':
                    planned_finish = activity.planned_finish
                    if hasattr(planned_finish, 'date'):
                        planned_finish = planned_finish.date()
                    
                    if today > planned_finish:
                        delay = (today - planned_finish).days
                        
                        # تصنيف المسؤولية
                        responsibility = DashboardService._classify_responsibility(activity, delay)
                        
                        # تطبيق فلتر المسؤولية
                        if responsible_filter != 'all' and responsibility != responsible_filter:
                            continue
                        
                        total_delay_days += delay
                        
                        if responsibility == 'contractor':
                            net_contractor_delay += delay
                        elif responsibility == 'client':
                            net_client_delay += delay
                        else:
                            concurrent_delays += delay
                        
                        # تفاصيل الأنشطة المتأخرة
                        delayed_activities.append({
                            'id': activity.id,
                            'name': activity.activity_name,
                            'project': activity.project.name if activity.project else 'N/A',
                            'delay_days': delay,
                            'responsible': responsibility,
                            'zone': getattr(activity, 'zone', 'General'),
                            'trade': getattr(activity, 'trade', 'General'),
                            'planned_finish': planned_finish.strftime('%Y-%m-%d'),
                            'current_status': activity.status
                        })
                        
                        # تجميع حسب المنطقة
                        zone = getattr(activity, 'zone', 'General')
                        if zone not in delay_by_zone:
                            delay_by_zone[zone] = 0
                        delay_by_zone[zone] += delay
                        
                        # تجميع حسب نوع العمل
                        trade = getattr(activity, 'trade', 'General')
                        if trade not in delay_by_trade:
                            delay_by_trade[trade] = 0
                        delay_by_trade[trade] += delay
            
            return {
                'total_delay_days': total_delay_days,
                'net_contractor_delay': net_contractor_delay,
                'net_client_delay': net_client_delay,
                'concurrent_delays': concurrent_delays,
                'delayed_activities': delayed_activities[:50],
                'delay_by_zone': delay_by_zone,
                'delay_by_trade': delay_by_trade
            }
            
        except Exception as e:
            logger.error(f"خطأ في get_delay_analysis: {str(e)}")
            return DashboardService._get_empty_delay_analysis()
    
    @staticmethod
    def _classify_responsibility(activity, delay_days):
        """
        تصنيف مسؤولية التأخير
        
        Args:
            activity: كائن النشاط
            delay_days: عدد أيام التأخير
        
        Returns:
            str: 'contractor', 'client', أو 'concurrent'
        """
        # عوامل التصنيف
        responsible = 'concurrent'
        
        # 1. بناءً على اسم النشاط
        activity_id_lower = activity.activity_id.lower() if activity.activity_id else ''
        activity_name_lower = activity.activity_name.lower() if activity.activity_name else ''
        
        if 'contractor' in activity_id_lower or 'subcon' in activity_id_lower or 'site' in activity_name_lower:
            responsible = 'contractor'
        elif 'client' in activity_id_lower or 'owner' in activity_id_lower or 'approval' in activity_name_lower:
            responsible = 'client'
        
        # 2. بناءً على نوع المورد المرتبط
        for ar in activity.resources:
            if ar.resource and ar.resource.supplier_id:
                responsible = 'contractor'
        
        # 3. بناءً على حالة التأخير
        if delay_days > 30:
            responsible = 'contractor'
        
        return responsible
    
    @staticmethod
    def _get_empty_delay_analysis():
        """إرجاع تحليل تأخيرات فارغ"""
        return {
            'total_delay_days': 0, 'net_contractor_delay': 0, 'net_client_delay': 0,
            'concurrent_delays': 0, 'delayed_activities': [], 'delay_by_zone': {}, 'delay_by_trade': {}
        }
    
    @staticmethod
    def get_performance_metrics(filters):
        """
        الحصول على مؤشرات الأداء SPI/CPI
        
        Args:
            filters: dict معاملات التصفية
        
        Returns:
            dict: مؤشرات الأداء
        """
        try:
            # بناء استعلام المشاريع
            project_query = Project.query
            if filters.get('project') and filters.get('project') != 'all':
                project_query = project_query.filter(Project.id == int(filters['project']))
            
            projects = project_query.all()
            
            # حساب المؤشرات الإجمالية
            total_pv = 0
            total_ev = 0
            total_ac = 0
            
            for project in projects:
                if project.performance:
                    total_pv += project.performance.planned_value or 0
                    total_ev += project.performance.earned_value or 0
                    total_ac += project.performance.actual_cost or 0
            
            overall_spi = round(total_ev / total_pv, 2) if total_pv > 0 else 1.0
            overall_cpi = round(total_ev / total_ac, 2) if total_ac > 0 else 1.0
            
            # البيانات الشهرية (آخر 12 شهراً)
            monthly_spi = []
            monthly_cpi = []
            monthly_labels = []
            
            today = date.today()
            for i in range(11, -1, -1):
                month_date = today.replace(day=1) - timedelta(days=i*30)
                month_key = month_date.strftime('%Y-%m')
                monthly_labels.append(month_date.strftime('%b %Y'))
                
                # هنا يمكن جلب البيانات الشهرية من جدول الأداء الشهري
                # حالياً نستخدم بيانات افتراضية
                monthly_spi.append(round(0.8 + (i * 0.02), 2))
                monthly_cpi.append(round(0.9 + (i * 0.01), 2))
            
            # الأنشطة الحرجة
            critical_activities = []
            for project in projects:
                activities = Activity.query.filter_by(
                    project_id=project.id, 
                    is_critical=True
                ).limit(20).all()
                
                for activity in activities:
                    critical_activities.append({
                        'id': activity.id,
                        'name': activity.activity_name,
                        'project': project.name,
                        'progress': activity.progress_percentage or 0,
                        'total_float': activity.total_float or 0,
                        'planned_finish': activity.planned_finish.strftime('%Y-%m-%d') if activity.planned_finish else 'N/A',
                        'status': activity.status
                    })
            
            return {
                'spi': overall_spi,
                'cpi': overall_cpi,
                'monthly_spi': monthly_spi,
                'monthly_cpi': monthly_cpi,
                'monthly_labels': monthly_labels,
                'critical_activities': critical_activities[:20]
            }
            
        except Exception as e:
            logger.error(f"خطأ في get_performance_metrics: {str(e)}")
            return DashboardService._get_empty_performance_metrics()
    
    @staticmethod
    def _get_empty_performance_metrics():
        """إرجاع مؤشرات أداء فارغة"""
        return {
            'spi': 1.0, 'cpi': 1.0, 'monthly_spi': [], 'monthly_cpi': [],
            'monthly_labels': [], 'critical_activities': []
        }
    
    @staticmethod
    def get_productivity_metrics(filters):
        """
        الحصول على مؤشرات الإنتاجية للعمالة والمعدات
        
        Args:
            filters: dict معاملات التصفية
        
        Returns:
            dict: مؤشرات الإنتاجية
        """
        try:
            # بناء استعلام الموارد
            org_id = None
            if filters.get('project') and filters.get('project') != 'all':
                project = Project.query.get(int(filters['project']))
                if project:
                    org_id = project.org_id
            
            if org_id:
                labor_resources = Resource.query.filter_by(org_id=org_id, resource_type='labor').all()
                equipment_resources = Resource.query.filter_by(org_id=org_id, resource_type='equipment').all()
            else:
                labor_resources = Resource.query.filter_by(resource_type='labor').all()
                equipment_resources = Resource.query.filter_by(resource_type='equipment').all()
            
            # حساب إنتاجية العمالة
            total_planned_labor = 0
            total_actual_labor = 0
            
            for resource in labor_resources:
                for assignment in resource.assignments:
                    total_planned_labor += assignment.planned_quantity or 0
                    total_actual_labor += assignment.actual_quantity or 0
            
            labor_pi = round((total_actual_labor / total_planned_labor * 100), 1) if total_planned_labor > 0 else 0
            
            # حساب إنتاجية المعدات
            total_planned_equipment = 0
            total_actual_equipment = 0
            
            for resource in equipment_resources:
                for assignment in resource.assignments:
                    total_planned_equipment += assignment.planned_quantity or 0
                    total_actual_equipment += assignment.actual_quantity or 0
            
            equipment_pi = round((total_actual_equipment / total_planned_equipment * 100), 1) if total_planned_equipment > 0 else 0
            
            # كفاءة الموارد الفردية
            resource_efficiency = []
            for resource in labor_resources + equipment_resources:
                planned = sum(a.planned_quantity or 0 for a in resource.assignments)
                actual = sum(a.actual_quantity or 0 for a in resource.assignments)
                efficiency = round((actual / planned * 100), 1) if planned > 0 else 0
                
                resource_efficiency.append({
                    'id': resource.id,
                    'name': resource.name,
                    'type': resource.resource_type,
                    'planned': planned,
                    'actual': actual,
                    'efficiency': efficiency
                })
            
            # ترتيب حسب الكفاءة
            resource_efficiency.sort(key=lambda x: x['efficiency'])
            
            overall_pi = round((labor_pi + equipment_pi) / 2, 1)
            
            return {
                'labor_pi': labor_pi,
                'equipment_pi': equipment_pi,
                'overall_pi': overall_pi,
                'resource_efficiency': resource_efficiency[:10]
            }
            
        except Exception as e:
            logger.error(f"خطأ في get_productivity_metrics: {str(e)}")
            return {'labor_pi': 0, 'equipment_pi': 0, 'overall_pi': 0, 'resource_efficiency': []}
    
    @staticmethod
    def get_document_metrics(filters):
        """
        الحصول على مقاييس جودة المستندات
        
        Args:
            filters: dict معاملات التصفية
        
        Returns:
            dict: مقاييس المستندات
        """
        try:
            # بناء استعلام المستندات
            query = ProjectDocument.query
            
            if filters.get('project') and filters.get('project') != 'all':
                query = query.filter(ProjectDocument.project_id == int(filters['project']))
            
            documents = query.all()
            
            # إحصائيات المستندات
            total = len(documents)
            approved = len([d for d in documents if d.approval_status == 'approved'])
            pending = len([d for d in documents if d.approval_status == 'pending'])
            rejected = len([d for d in documents if d.approval_status == 'rejected'])
            
            # إحصائيات المراجعات
            first_attempt = 0
            second_attempt = 0
            third_attempt = 0
            
            for doc in documents:
                revision = getattr(doc, 'revision_count', 1)
                if revision == 1:
                    first_attempt += 1
                elif revision == 2:
                    second_attempt += 1
                else:
                    third_attempt += 1
            
            total_attempts = first_attempt + second_attempt + third_attempt
            first_attempt_rate = round((first_attempt / total_attempts * 100), 1) if total_attempts > 0 else 0
            second_attempt_rate = round((second_attempt / total_attempts * 100), 1) if total_attempts > 0 else 0
            third_attempt_rate = round((third_attempt / total_attempts * 100), 1) if total_attempts > 0 else 0
            
            # اختناقات الموافقة
            approval_bottlenecks = []
            for doc in documents:
                if doc.approved_at and doc.uploaded_at:
                    review_days = (doc.approved_at - doc.uploaded_at).days
                    if review_days > 10:  # تجاوز الحد التعاقدي
                        approval_bottlenecks.append({
                            'id': doc.id,
                            'title': doc.title,
                            'project': doc.project.name if doc.project else 'N/A',
                            'review_days': review_days,
                            'exceeded_by': review_days - 10
                        })
            
            # ترتيب حسب الأكثر تأخيراً
            approval_bottlenecks.sort(key=lambda x: x['review_days'], reverse=True)
            
            return {
                'total': total,
                'approved': approved,
                'pending': pending,
                'rejected': rejected,
                'first_attempt': first_attempt,
                'second_attempt': second_attempt,
                'third_attempt': third_attempt,
                'first_attempt_rate': first_attempt_rate,
                'second_attempt_rate': second_attempt_rate,
                'third_attempt_rate': third_attempt_rate,
                'approval_bottlenecks': approval_bottlenecks[:10]
            }
            
        except Exception as e:
            logger.error(f"خطأ في get_document_metrics: {str(e)}")
            return DashboardService._get_empty_document_metrics()
    
    @staticmethod
    def _get_empty_document_metrics():
        """إرجاع مقاييس مستندات فارغة"""
        return {
            'total': 0, 'approved': 0, 'pending': 0, 'rejected': 0,
            'first_attempt': 0, 'second_attempt': 0, 'third_attempt': 0,
            'first_attempt_rate': 0, 'second_attempt_rate': 0, 'third_attempt_rate': 0,
            'approval_bottlenecks': []
        }
    
    @staticmethod
    def get_granular_metrics(filters):
        """
        الحصول على المقاييس الدقيقة حسب المنطقة والمقاولين
        
        Args:
            filters: dict معاملات التصفية
        
        Returns:
            dict: المقاييس الدقيقة
        """
        try:
            # بناء استعلام المشاريع
            project_query = Project.query
            if filters.get('project') and filters.get('project') != 'all':
                project_query = project_query.filter(Project.id == int(filters['project']))
            
            projects = project_query.all()
            
            # إحصائيات المقاول الرئيسي
            main_contractor = {
                'total_value': 0,
                'progress': 0,
                'tasks_count': 0,
                'completed_tasks': 0
            }
            
            # إحصائيات المقاولين من الباطن
            subcontractors = {}
            
            # إحصائيات المناطق
            zones = {}
            
            # إحصائيات الطوابق
            floors = {}
            
            # إحصائيات أنواع العمل
            trades = {}
            
            for project in projects:
                # الميزانية
                if project.budget:
                    main_contractor['total_value'] += project.budget.current_budget or 0
                    main_contractor['progress'] += project.get_progress()
                
                # المهام
                tasks = Task.query.filter_by(project_id=project.id).all()
                main_contractor['tasks_count'] += len(tasks)
                main_contractor['completed_tasks'] += len([t for t in tasks if t.status == 'completed'])
                
                # تحليل المقاولين من الباطن
                for task in tasks:
                    if task.delegate_id:
                        sub = User.query.get(task.delegate_id)
                        if sub:
                            if sub.id not in subcontractors:
                                subcontractors[sub.id] = {
                                    'id': sub.id,
                                    'name': sub.full_name,
                                    'total_value': 0,
                                    'progress': 0,
                                    'tasks_count': 0,
                                    'completed_tasks': 0
                                }
                            subcontractors[sub.id]['tasks_count'] += 1
                            if task.status == 'completed':
                                subcontractors[sub.id]['completed_tasks'] += 1
                            if task.execution:
                                subcontractors[sub.id]['total_value'] += task.execution.actual_cost or 0
                
                # تحليل الأنشطة حسب المنطقة والطابق ونوع العمل
                activities = Activity.query.filter_by(project_id=project.id).all()
                for activity in activities:
                    zone = getattr(activity, 'zone', 'General')
                    floor = getattr(activity, 'floor', 'General')
                    trade = getattr(activity, 'trade', 'General')
                    
                    # مناطق
                    if zone not in zones:
                        zones[zone] = {'activities': 0, 'progress': 0, 'delayed': 0}
                    zones[zone]['activities'] += 1
                    zones[zone]['progress'] += activity.progress_percentage or 0
                    if activity.status == 'delayed':
                        zones[zone]['delayed'] += 1
                    
                    # طوابق
                    if floor not in floors:
                        floors[floor] = {'activities': 0, 'progress': 0}
                    floors[floor]['activities'] += 1
                    floors[floor]['progress'] += activity.progress_percentage or 0
                    
                    # أنواع العمل
                    if trade not in trades:
                        trades[trade] = {'activities': 0, 'progress': 0}
                    trades[trade]['activities'] += 1
                    trades[trade]['progress'] += activity.progress_percentage or 0
            
            # حساب المتوسطات
            for zone in zones:
                if zones[zone]['activities'] > 0:
                    zones[zone]['progress'] = round(zones[zone]['progress'] / zones[zone]['activities'], 1)
            
            for floor in floors:
                if floors[floor]['activities'] > 0:
                    floors[floor]['progress'] = round(floors[floor]['progress'] / floors[floor]['activities'], 1)
            
            for trade in trades:
                if trades[trade]['activities'] > 0:
                    trades[trade]['progress'] = round(trades[trade]['progress'] / trades[trade]['activities'], 1)
            
            # حساب تقدم المقاولين من الباطن
            for sub_id in subcontractors:
                if subcontractors[sub_id]['tasks_count'] > 0:
                    subcontractors[sub_id]['progress'] = round(
                        (subcontractors[sub_id]['completed_tasks'] / subcontractors[sub_id]['tasks_count']) * 100, 1
                    )
            
            # حساب تقدم المقاول الرئيسي
            if len(projects) > 0:
                main_contractor['progress'] = round(main_contractor['progress'] / len(projects), 1)
            
            return {
                'main_contractor': main_contractor,
                'subcontractors': subcontractors,
                'zones': zones,
                'floors': floors,
                'trades': trades
            }
            
        except Exception as e:
            logger.error(f"خطأ في get_granular_metrics: {str(e)}")
            return DashboardService._get_empty_granular_metrics()
    
    @staticmethod
    def _get_empty_granular_metrics():
        """إرجاع مقاييس دقيقة فارغة"""
        return {
            'main_contractor': {'total_value': 0, 'progress': 0, 'tasks_count': 0, 'completed_tasks': 0},
            'subcontractors': {}, 'zones': {}, 'floors': {}, 'trades': {}
        }
    
    @staticmethod
    def get_cash_flow_metrics(filters):
        """
        الحصول على مقاييس التدفق النقدي
        
        Args:
            filters: dict معاملات التصفية
        
        Returns:
            dict: مقاييس التدفق النقدي
        """
        try:
            query = Invoice.query
            
            if filters.get('project') and filters.get('project') != 'all':
                query = query.filter(Invoice.project_id == int(filters['project']))
            
            if filters.get('date_from'):
                query = query.filter(Invoice.invoice_date >= filters['date_from'])
            
            if filters.get('date_to'):
                query = query.filter(Invoice.invoice_date <= filters['date_to'])
            
            invoices = query.all()
            
            total_invoiced = sum(i.total_amount for i in invoices)
            total_paid = sum(i.paid_amount for i in invoices)
            total_pending = sum(i.balance_due for i in invoices)
            
            # الفواتير المتأخرة
            overdue_invoices = []
            for invoice in invoices:
                if invoice.due_date and invoice.due_date < date.today() and invoice.balance_due > 0:
                    overdue_invoices.append({
                        'id': invoice.id,
                        'number': invoice.invoice_number,
                        'amount': invoice.balance_due,
                        'due_date': invoice.due_date.strftime('%Y-%m-%d'),
                        'project': invoice.project.name if invoice.project else 'N/A'
                    })
            
            # متوسط أيام السداد
            payments = Payment.query.join(Invoice).filter(Invoice.id.in_([i.id for i in invoices]))
            total_payment_days = 0
            payment_count = 0
            
            for payment in payments:
                if payment.payment_date and payment.invoice and payment.invoice.invoice_date:
                    days = (payment.payment_date - payment.invoice.invoice_date).days
                    total_payment_days += days
                    payment_count += 1
            
            avg_payment_days = round(total_payment_days / payment_count, 1) if payment_count > 0 else 0
            
            # التدفق النقدي الشهري
            monthly_cash_flow = {}
            for invoice in invoices:
                month_key = invoice.invoice_date.strftime('%Y-%m')
                if month_key not in monthly_cash_flow:
                    monthly_cash_flow[month_key] = {'invoiced': 0, 'paid': 0, 'pending': 0}
                monthly_cash_flow[month_key]['invoiced'] += invoice.total_amount
                monthly_cash_flow[month_key]['paid'] += invoice.paid_amount
                monthly_cash_flow[month_key]['pending'] += invoice.balance_due
            
            return {
                'total_invoiced': total_invoiced,
                'total_paid': total_paid,
                'total_pending': total_pending,
                'avg_payment_days': avg_payment_days,
                'overdue_invoices': overdue_invoices,
                'monthly_cash_flow': monthly_cash_flow
            }
            
        except Exception as e:
            logger.error(f"خطأ في get_cash_flow_metrics: {str(e)}")
            return {
                'total_invoiced': 0, 'total_paid': 0, 'total_pending': 0,
                'avg_payment_days': 0, 'overdue_invoices': [], 'monthly_cash_flow': {}
            }


# دوال مساعدة للاستخدام المباشر
def get_general_stats(filters=None):
    return DashboardService.get_general_stats(filters or {})

def get_delay_analysis(filters=None):
    return DashboardService.get_delay_analysis(filters or {})

def get_performance_metrics(filters=None):
    return DashboardService.get_performance_metrics(filters or {})

def get_productivity_metrics(filters=None):
    return DashboardService.get_productivity_metrics(filters or {})

def get_document_metrics(filters=None):
    return DashboardService.get_document_metrics(filters or {})

def get_granular_metrics(filters=None):
    return DashboardService.get_granular_metrics(filters or {})

def get_cash_flow_metrics(filters=None):
    return DashboardService.get_cash_flow_metrics(filters or {})
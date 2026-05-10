# app/services/report_generator.py

import json
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
from flask import current_app, url_for
import plotly.graph_objects as go
import plotly.utils
from app.models import db
from app.models import Project, Activity
from app.models import Task
from app.models import Resource, EPS, OBS, WBS
from app.models import User

class ReportGenerator:
    """توليد التقارير الذكية"""
    
    def __init__(self):
        self.report_types = {
            'project_performance': self._generate_project_performance,
            'task_summary': self._generate_task_summary,
            'resource_utilization': self._generate_resource_utilization,
            'budget_analysis': self._generate_budget_analysis,
            'risk_assessment': self._generate_risk_assessment,
            'timeline_overview': self._generate_timeline_overview,
            'team_productivity': self._generate_team_productivity,
            'custom': self._generate_custom_report
        }
    
    def generate_report(self, org_id, command):
        """توليد تقرير بناءً على الأمر"""
        result = {
            'success': False,
            'report_type': command.get('target_type', 'general'),
            'title': '',
            'summary': '',
            'data': {},
            'charts': [],
            'insights': [],
            'recommendations': [],
            'error': None
        }
        
        try:
            # تحديد نوع التقرير
            report_type = self._determine_report_type(command)
            result['report_type'] = report_type
            
            # توليد التقرير
            if report_type in self.report_types:
                report_data = self.report_types[report_type](org_id, command)
                result.update(report_data)
            else:
                # تقرير عام
                report_data = self._generate_general_report(org_id, command)
                result.update(report_data)
            
            result['success'] = True
            
        except Exception as e:
            result['error'] = str(e)
            current_app.logger.error(f"Report generation error: {str(e)}")
        
        return result
    
    def _determine_report_type(self, command):
        """تحديد نوع التقرير من الأمر"""
        cmd_text = command.get('command_text', '').lower()
        target = command.get('target_type', 'general')
        
        # كلمات مفتاحية لأنواع التقارير
        keywords = {
            'project_performance': ['أداء', 'performance', 'تقدم', 'progress'],
            'task_summary': ['مهام', 'tasks', 'أنشطة', 'activities'],
            'resource_utilization': ['موارد', 'resources', 'استخدام', 'utilization'],
            'budget_analysis': ['ميزانية', 'budget', 'تكلفة', 'cost'],
            'risk_assessment': ['مخاطر', 'risks', 'تقييم', 'assessment'],
            'timeline_overview': ['جدول', 'timeline', 'مواعيد', 'deadlines'],
            'team_productivity': ['فريق', 'team', 'إنتاجية', 'productivity']
        }
        
        for report_type, words in keywords.items():
            if any(word in cmd_text for word in words):
                return report_type
        
        return target if target != 'general' else 'general'
    
    def _generate_project_performance(self, org_id, command):
        """تقرير أداء المشاريع"""
        # تحديد المشروع
        project_id = command.get('parameters', {}).get('project_id')
        
        if project_id:
            projects = Project.query.filter_by(id=project_id).all()
        else:
            # آخر 10 مشاريع
            projects = Project.query.filter_by(org_id=org_id)\
                .order_by(Project.created_at.desc()).limit(10).all()
        
        data = []
        for project in projects:
            activities = Activity.query.filter_by(project_id=project.id).all()
            tasks = Task.query.filter_by(project_id=project.id).all()
            
            completed_activities = len([a for a in activities if a.status == 'completed'])
            completed_tasks = len([t for t in tasks if t.status == 'completed'])
            
            data.append({
                'id': project.id,
                'name': project.name,
                'code': project.project_code,
                'status': project.status,
                'progress': project.progress.progress_percentage if project.progress else 0,
                'activities': {
                    'total': len(activities),
                    'completed': completed_activities,
                    'percentage': (completed_activities / len(activities) * 100) if activities else 0
                },
                'tasks': {
                    'total': len(tasks),
                    'completed': completed_tasks,
                    'percentage': (completed_tasks / len(tasks) * 100) if tasks else 0
                }
            })
        
        # إنشاء رسوم بيانية
        charts = []
        
        # رسم بياني للتقدم
        if data:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name='التقدم',
                x=[p['name'] for p in data],
                y=[p['progress'] for p in data],
                marker_color='#4361ee'
            ))
            fig.update_layout(
                title='تقدم المشاريع',
                xaxis_title='المشروع',
                yaxis_title='نسبة التقدم %',
                template='plotly_white'
            )
            charts.append({
                'id': 'progress_chart',
                'title': 'تقدم المشاريع',
                'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
            })
        
        # رؤى وتحليلات
        insights = []
        if data:
            avg_progress = sum(p['progress'] for p in data) / len(data)
            insights.append(f"متوسط تقدم المشاريع: {avg_progress:.1f}%")
            
            delayed = len([p for p in data if p['progress'] < 30])
            if delayed > 0:
                insights.append(f"{delayed} مشاريع تقدمها أقل من 30%")
        
        return {
            'title': 'تقرير أداء المشاريع',
            'summary': f"تم تحليل {len(data)} مشاريع",
            'data': {'projects': data},
            'charts': charts,
            'insights': insights,
            'recommendations': self._get_project_recommendations(data)
        }
    
    def _generate_task_summary(self, org_id, command):
        """تقرير ملخص المهام"""
        # تحديد الفترة
        period = command.get('parameters', {}).get('period', {})
        
        query = Task.query.join(Project).filter(Project.org_id == org_id)
        
        # تصفية حسب الفترة
        if period:
            days = period.get('value', 30)
            cutoff = datetime.now() - timedelta(days=days)
            query = query.filter(Task.created_at >= cutoff)
        
        tasks = query.all()
        
        # إحصائيات
        by_status = {
            'pending': len([t for t in tasks if t.status == 'pending']),
            'in_progress': len([t for t in tasks if t.status == 'in_progress']),
            'completed': len([t for t in tasks if t.status == 'completed'])
        }
        
        by_priority = {
            'high': len([t for t in tasks if t.priority >= 4]),
            'medium': len([t for t in tasks if 2 <= t.priority <= 3]),
            'low': len([t for t in tasks if t.priority <= 1])
        }
        
        delayed = len([t for t in tasks if hasattr(t, 'is_delayed') and t.is_delayed])
        
        # رسم بياني
        fig = go.Figure(data=[
            go.Pie(
                labels=list(by_status.keys()),
                values=list(by_status.values()),
                hole=.3
            )
        ])
        fig.update_layout(title='توزيع المهام حسب الحالة')
        
        charts = [{
            'id': 'status_chart',
            'title': 'توزيع المهام',
            'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        }]
        
        insights = [
            f"إجمالي المهام: {len(tasks)}",
            f"المهام المكتملة: {by_status['completed']} ({by_status['completed']/len(tasks)*100:.1f}%)" if tasks else "",
            f"المهام المتأخرة: {delayed}"
        ]
        
        return {
            'title': 'تقرير ملخص المهام',
            'summary': f"تحليل {len(tasks)} مهمة",
            'data': {
                'by_status': by_status,
                'by_priority': by_priority,
                'delayed': delayed
            },
            'charts': charts,
            'insights': [i for i in insights if i]
        }
    
    def _generate_resource_utilization(self, org_id, command):
        """تقرير استخدام الموارد"""
        resources = Resource.query.filter_by(org_id=org_id).all()
        
        data = []
        for resource in resources:
            from app.models.primavera_models import ActivityResource
            
            assignments = ActivityResource.query.filter_by(resource_id=resource.id).all()
            total_assigned = sum(a.planned_quantity for a in assignments)
            utilization = (total_assigned / resource.available_quantity * 100) if resource.available_quantity > 0 else 0
            
            data.append({
                'id': resource.id,
                'name': resource.name,
                'type': resource.resource_type,
                'available': resource.available_quantity,
                'assigned': total_assigned,
                'utilization': utilization,
                'status': 'overloaded' if utilization > 100 else 'optimal' if utilization > 70 else 'underutilized'
            })
        
        # رسم بياني
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='الاستخدام',
            x=[r['name'] for r in data[:10]],
            y=[r['utilization'] for r in data[:10]],
            marker_color=['red' if r['utilization'] > 100 else 'orange' if r['utilization'] > 70 else 'green' for r in data[:10]]
        ))
        fig.update_layout(
            title='استخدام الموارد',
            xaxis_title='المورد',
            yaxis_title='نسبة الاستخدام %',
            template='plotly_white'
        )
        
        charts = [{
            'id': 'utilization_chart',
            'title': 'نسب استخدام الموارد',
            'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        }]
        
        insights = [
            f"إجمالي الموارد: {len(data)}",
            f"موارد محملة فوق الطاقة: {len([r for r in data if r['utilization'] > 100])}",
            f"موارد غير مستغلة: {len([r for r in data if r['utilization'] < 50])}"
        ]
        
        recommendations = []
        if len([r for r in data if r['utilization'] > 100]) > 0:
            recommendations.append("يوجد موارد محملة فوق الطاقة، يوصى بإعادة توزيع المهام")
        
        return {
            'title': 'تقرير استخدام الموارد',
            'summary': f"تحليل {len(data)} مورد",
            'data': {'resources': data},
            'charts': charts,
            'insights': insights,
            'recommendations': recommendations
        }
    
    def _generate_budget_analysis(self, org_id, command):
        """تقرير تحليل الميزانية"""
        projects = Project.query.filter_by(org_id=org_id).all()
        
        data = []
        total_budget = 0
        total_actual = 0
        
        for project in projects:
            if project.budget and project.cost:
                budget = project.budget.current_budget or 0
                actual = project.cost.total_actual_cost or 0
                variance = budget - actual
                
                data.append({
                    'id': project.id,
                    'name': project.name,
                    'budget': budget,
                    'actual': actual,
                    'variance': variance,
                    'variance_percent': (variance / budget * 100) if budget > 0 else 0
                })
                
                total_budget += budget
                total_actual += actual
        
        # رسم بياني
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name='الميزانية',
            x=[p['name'] for p in data[:10]],
            y=[p['budget'] for p in data[:10]],
            marker_color='#4361ee'
        ))
        fig.add_trace(go.Bar(
            name='التكلفة الفعلية',
            x=[p['name'] for p in data[:10]],
            y=[p['actual'] for p in data[:10]],
            marker_color='#f8961e'
        ))
        fig.update_layout(
            title='تحليل الميزانية',
            barmode='group',
            template='plotly_white'
        )
        
        charts = [{
            'id': 'budget_chart',
            'title': 'الميزانية مقابل التكلفة',
            'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        }]
        
        over_budget = len([p for p in data if p['variance'] < 0])
        
        insights = [
            f"إجمالي الميزانية: {total_budget:,.0f}",
            f"إجمالي التكلفة: {total_actual:,.0f}",
            f"الفرق الكلي: {total_budget - total_actual:,.0f}",
            f"مشاريع فوق الميزانية: {over_budget}"
        ]
        
        return {
            'title': 'تقرير تحليل الميزانية',
            'summary': f"تحليل ميزانية {len(data)} مشاريع",
            'data': {'projects': data, 'totals': {'budget': total_budget, 'actual': total_actual}},
            'charts': charts,
            'insights': insights
        }
    
    def _generate_risk_assessment(self, org_id, command):
        """تقرير تقييم المخاطر"""
        from app.models.ai_models import Risk
        
        risks = Risk.query.filter_by(org_id=org_id).all()
        
        by_level = {
            'high': len([r for r in risks if r.risk_level == 'high']),
            'medium': len([r for r in risks if r.risk_level == 'medium']),
            'low': len([r for r in risks if r.risk_level == 'low'])
        }
        
        by_status = {
            'open': len([r for r in risks if r.status != 'closed']),
            'closed': len([r for r in risks if r.status == 'closed'])
        }
        
        # أهم المخاطر
        top_risks = []
        for risk in risks:
            if risk.risk_level == 'high' and risk.status != 'closed':
                top_risks.append({
                    'id': risk.id,
                    'title': risk.title,
                    'project': risk.project.name if risk.project else None,
                    'probability': risk.probability,
                    'impact': risk.impact
                })
        
        # رسم بياني
        fig = go.Figure(data=[
            go.Pie(
                labels=list(by_level.keys()),
                values=list(by_level.values()),
                hole=.3
            )
        ])
        fig.update_layout(title='توزيع المخاطر حسب المستوى')
        
        charts = [{
            'id': 'risk_chart',
            'title': 'توزيع المخاطر',
            'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        }]
        
        insights = [
            f"إجمالي المخاطر: {len(risks)}",
            f"مخاطر مفتوحة: {by_status['open']}",
            f"مخاطر عالية: {by_level['high']}"
        ]
        
        return {
            'title': 'تقرير تقييم المخاطر',
            'summary': f"تحليل {len(risks)} خطر",
            'data': {
                'by_level': by_level,
                'by_status': by_status,
                'top_risks': top_risks[:5]
            },
            'charts': charts,
            'insights': insights
        }
    
    def _generate_timeline_overview(self, org_id, command):
        """تقرير نظرة عامة على الجدول الزمني"""
        today = datetime.now().date()
        
        # المهام القادمة
        upcoming_tasks = Task.query.join(Project).filter(
            Project.org_id == org_id,
            Task.status.in_(['pending', 'in_progress'])
        ).all()
        
        timeline_data = []
        for task in upcoming_tasks:
            if task.planning and task.planning.planned_finish:
                finish_date = task.planning.planned_finish.date()
                days_left = (finish_date - today).days
                
                if 0 <= days_left <= 30:
                    timeline_data.append({
                        'id': task.id,
                        'name': task.task_name,
                        'project': task.project.name if task.project else None,
                        'finish_date': finish_date.strftime('%Y-%m-%d'),
                        'days_left': days_left,
                        'priority': 'high' if days_left <= 7 else 'medium' if days_left <= 14 else 'low'
                    })
        
        # ترتيب حسب التاريخ
        timeline_data.sort(key=lambda x: x['days_left'])
        
        # رسم بياني
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[t['name'][:20] for t in timeline_data[:10]],
            y=[t['days_left'] for t in timeline_data[:10]],
            marker_color=['red' if t['days_left'] <= 7 else 'orange' if t['days_left'] <= 14 else 'green' for t in timeline_data[:10]]
        ))
        fig.update_layout(
            title='المواعيد النهائية القادمة',
            xaxis_title='المهمة',
            yaxis_title='الأيام المتبقية',
            template='plotly_white'
        )
        
        charts = [{
            'id': 'timeline_chart',
            'title': 'المواعيد النهائية',
            'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        }]
        
        urgent = len([t for t in timeline_data if t['days_left'] <= 7])
        
        insights = [
            f"مهام مستحقة خلال 30 يوم: {len(timeline_data)}",
            f"مهام حرجة (أقل من 7 أيام): {urgent}"
        ]
        
        return {
            'title': 'نظرة عامة على الجدول الزمني',
            'summary': f"تحليل {len(timeline_data)} مهمة قادمة",
            'data': {'upcoming': timeline_data},
            'charts': charts,
            'insights': insights
        }
    
    def _generate_team_productivity(self, org_id, command):
        """تقرير إنتاجية الفريق"""
        users = User.query.filter_by(org_id=org_id, is_active=True).all()
        
        data = []
        for user in users:
            # المهام المسندة للمستخدم
            tasks = Task.query.filter(
                or_(
                    Task.supervisor_id == user.id,
                    Task.delegate_id == user.id
                )
            ).all()
            
            completed = len([t for t in tasks if t.status == 'completed'])
            total = len(tasks)
            
            if total > 0:
                productivity = (completed / total) * 100
            else:
                productivity = 0
            
            data.append({
                'id': user.id,
                'name': user.full_name,
                'role': user.role,
                'tasks_assigned': total,
                'tasks_completed': completed,
                'productivity': productivity
            })
        
        # ترتيب حسب الإنتاجية
        data.sort(key=lambda x: x['productivity'], reverse=True)
        
        # رسم بياني
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=[u['name'] for u in data[:10]],
            y=[u['productivity'] for u in data[:10]],
            marker_color='#4361ee'
        ))
        fig.update_layout(
            title='إنتاجية الفريق',
            xaxis_title='المستخدم',
            yaxis_title='نسبة الإنتاجية %',
            template='plotly_white'
        )
        
        charts = [{
            'id': 'productivity_chart',
            'title': 'إنتاجية الفريق',
            'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        }]
        
        avg_productivity = sum(u['productivity'] for u in data) / len(data) if data else 0
        
        insights = [
            f"إجمالي أعضاء الفريق: {len(data)}",
            f"متوسط الإنتاجية: {avg_productivity:.1f}%",
            f"أعلى إنتاجية: {data[0]['name'] if data else 'N/A'} ({data[0]['productivity']:.1f}%)"
        ]
        
        return {
            'title': 'تقرير إنتاجية الفريق',
            'summary': f"تحليل إنتاجية {len(data)} عضو",
            'data': {'team': data},
            'charts': charts,
            'insights': insights
        }
    
    def _generate_general_report(self, org_id, command):
        """تقرير عام للمؤسسة"""
        # إحصائيات سريعة
        projects_count = Project.query.filter_by(org_id=org_id).count()
        tasks_count = Task.query.join(Project).filter(Project.org_id == org_id).count()
        resources_count = Resource.query.filter_by(org_id=org_id).count()
        users_count = User.query.filter_by(org_id=org_id, is_active=True).count()
        
        # مشاريع حسب الحالة
        projects_by_status = db.session.query(
            Project.status,
            func.count(Project.id)
        ).filter_by(org_id=org_id).group_by(Project.status).all()
        
        data = {
            'summary': {
                'projects': projects_count,
                'tasks': tasks_count,
                'resources': resources_count,
                'users': users_count
            },
            'projects_by_status': dict(projects_by_status)
        }
        
        # رسم بياني للمشاريع
        if projects_by_status:
            fig = go.Figure(data=[
                go.Pie(
                    labels=[s[0] for s in projects_by_status],
                    values=[s[1] for s in projects_by_status],
                    hole=.3
                )
            ])
            fig.update_layout(title='توزيع المشاريع حسب الحالة')
            
            charts = [{
                'id': 'projects_chart',
                'title': 'توزيع المشاريع',
                'data': json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
            }]
        else:
            charts = []
        
        insights = [
            f"إجمالي المشاريع: {projects_count}",
            f"إجمالي المهام: {tasks_count}",
            f"إجمالي الموارد: {resources_count}",
            f"إجمالي المستخدمين: {users_count}"
        ]
        
        return {
            'title': 'تقرير عام للمؤسسة',
            'summary': 'نظرة عامة على أداء المؤسسة',
            'data': data,
            'charts': charts,
            'insights': insights
        }
    
    def _generate_custom_report(self, org_id, command):
        """تقرير مخصص حسب طلب المستخدم"""
        # يمكن تخصيص هذا حسب متطلبات المستخدم
        return self._generate_general_report(org_id, command)
    
    def _get_project_recommendations(self, projects):
        """توليد توصيات للمشاريع"""
        recommendations = []
        
        for project in projects:
            if project['progress'] < 30:
                recommendations.append(f"مشروع {project['name']}: تقدم منخفض، يوصى بمراجعة الخطة")
            
            if project['activities']['percentage'] < 50 and project['progress'] > 50:
                recommendations.append(f"مشروع {project['name']}: تقدم المشروع أعلى من تقدم الأنشطة")
        
        return recommendations[:5]
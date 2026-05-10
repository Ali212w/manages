"""
ai_recommendation_service.py - خدمة التوصيات الذكية باستخدام الذكاء الاصطناعي
"""

from datetime import datetime, timedelta, date
from flask import current_app
from app.models import db
from app.models import (
    Project, Activity, Task, User, Notification,
    ProjectProgress, ProjectPerformance
)
from app.models.ai_models import AISuggestion, AICommand
from app.services.notification_service import NotificationService
import logging
import json
import random
from sqlalchemy import func, and_, or_

logger = logging.getLogger(__name__)


class AIRecommendationService:
    """خدمة التوصيات الذكية للمستخدمين والمشاريع"""

    # ============================================
    # توصيات المستخدم
    # ============================================

    @staticmethod
    def get_user_recommendations(user_id, limit=5):
        """
        الحصول على توصيات ذكية لمستخدم معين
        
        Args:
            user_id: معرف المستخدم
            limit: الحد الأقصى لعدد التوصيات
            
        Returns:
            list: قائمة بالتوصيات
        """
        try:
            user = User.query.get(user_id)
            if not user:
                return []

            recommendations = []

            # 1. توصيات المهام المتأخرة
            overdue_recs = AIRecommendationService._get_overdue_tasks_recommendations(user)
            recommendations.extend(overdue_recs)

            # 2. توصيات المهام القادمة
            upcoming_recs = AIRecommendationService._get_upcoming_tasks_recommendations(user)
            recommendations.extend(upcoming_recs)

            # 3. توصيات الأداء
            performance_recs = AIRecommendationService._get_performance_recommendations(user)
            recommendations.extend(performance_recs)

            # 4. توصيات الأنشطة
            activity_recs = AIRecommendationService._get_activity_recommendations(user)
            recommendations.extend(activity_recs)

            # 5. توصيات وقت الراحة
            break_recs = AIRecommendationService._get_break_recommendations(user)
            recommendations.extend(break_recs)

            # ترتيب حسب الأولوية والأهمية
            recommendations.sort(key=lambda x: (
                0 if x.get('priority') == 'high' else 
                1 if x.get('priority') == 'medium' else 2,
                -x.get('confidence', 0)
            ))

            return recommendations[:limit]

        except Exception as e:
            logger.error(f"Error in get_user_recommendations: {str(e)}")
            return []

    @staticmethod
    def _get_overdue_tasks_recommendations(user):
        """توصيات للمهام المتأخرة"""
        recommendations = []
        today = date.today()

        # المهام المتأخرة
        if user.role == 'supervisor':
            tasks = Task.query.filter_by(supervisor_id=user.id).all()
        elif user.role == 'delegate':
            tasks = Task.query.filter_by(delegate_id=user.id).all()
        else:
            from app.models.task_models import TaskAssignment
            assignments = TaskAssignment.query.filter_by(user_id=user.id).all()
            tasks = [a.task for a in assignments if a.task]

        overdue_tasks = []
        for task in tasks:
            if task.status in ['pending', 'in_progress']:
                # محاولة الحصول على تاريخ الانتهاء المخطط من TaskPlanning
                planned_end = None
                if hasattr(task, 'planning') and task.planning:
                    planned_end = task.planning.planned_finish
                
                if planned_end and planned_end < today:
                    overdue_tasks.append({
                        'id': task.id,
                        'name': task.task_name,
                        'delay_days': (today - planned_end).days
                    })

        if overdue_tasks:
            # أظهر أول مهمة متأخرة
            first_overdue = overdue_tasks[0]
            recommendations.append({
                'type': 'warning',
                'title': '⚠️ مهام متأخرة',
                'message': f'لديك {len(overdue_tasks)} مهام متأخرة. أقدمها: {first_overdue["name"]} (متأخرة {first_overdue["delay_days"]} يوم)',
                'action_url': '/employee/my-tasks?status=overdue',
                'icon': 'exclamation-triangle',
                'priority': 'high',
                'confidence': 90
            })

        return recommendations

    @staticmethod
    def _get_upcoming_tasks_recommendations(user):
        """توصيات للمهام القادمة"""
        recommendations = []
        today = date.today()
        next_week = today + timedelta(days=7)

        # المهام القادمة خلال الأسبوع
        if user.role == 'supervisor':
            tasks = Task.query.filter_by(supervisor_id=user.id).all()
        elif user.role == 'delegate':
            tasks = Task.query.filter_by(delegate_id=user.id).all()
        else:
            from app.models.task_models import TaskAssignment
            assignments = TaskAssignment.query.filter_by(user_id=user.id).all()
            tasks = [a.task for a in assignments if a.task]

        upcoming_tasks = []
        for task in tasks:
            if task.status == 'pending':
                planned_start = None
                if hasattr(task, 'planning') and task.planning:
                    planned_start = task.planning.planned_start
                
                if planned_start and today <= planned_start <= next_week:
                    upcoming_tasks.append({
                        'id': task.id,
                        'name': task.task_name,
                        'start_date': planned_start
                    })

        if upcoming_tasks:
            recommendations.append({
                'type': 'info',
                'title': '📅 مهام قادمة',
                'message': f'لديك {len(upcoming_tasks)} مهام ستبدأ خلال الأسبوع القادم',
                'action_url': '/employee/my-tasks?status=pending',
                'icon': 'calendar-alt',
                'priority': 'medium',
                'confidence': 85
            })

        return recommendations

    @staticmethod
    def _get_performance_recommendations(user):
        """توصيات لتحسين الأداء"""
        recommendations = []

        # حساب إحصائيات المستخدم
        if user.role == 'supervisor':
            tasks = Task.query.filter_by(supervisor_id=user.id).all()
        elif user.role == 'delegate':
            tasks = Task.query.filter_by(delegate_id=user.id).all()
        else:
            from app.models.task_models import TaskAssignment
            assignments = TaskAssignment.query.filter_by(user_id=user.id).all()
            tasks = [a.task for a in assignments if a.task]

        total_tasks = len(tasks)
        if total_tasks == 0:
            return recommendations

        completed_tasks = len([t for t in tasks if t.status == 'completed'])
        completion_rate = (completed_tasks / total_tasks) * 100

        # توصيات لتحسين الإنجاز
        if completion_rate < 30 and total_tasks > 5:
            recommendations.append({
                'type': 'warning',
                'title': '📈 تحسين الإنتاجية',
                'message': f'نسبة إنجازك {completion_rate:.0f}%. حاول التركيز على المهام الصغيرة أولاً لرفع الإنجاز',
                'action_url': '/employee/my-tasks?priority=high',
                'icon': 'chart-line',
                'priority': 'medium',
                'confidence': 75
            })
        elif completion_rate > 80:
            recommendations.append({
                'type': 'success',
                'title': '🌟 أداء ممتاز',
                'message': f'نسبة إنجازك {completion_rate:.0f}%! استمر بنفس المستوى العالي',
                'icon': 'star',
                'priority': 'low',
                'confidence': 95
            })

        return recommendations

    @staticmethod
    def _get_activity_recommendations(user):
        """توصيات للأنشطة"""
        recommendations = []

        # الأنشطة التي تحتاج إلى متابعة (تقدم منخفض)
        if user.role == 'supervisor':
            activities = Activity.query.filter_by(supervisor_id=user.id).all()
        else:
            # للمندوب والموظف
            if user.role == 'delegate':
                activities = Activity.query.filter_by(delegate_id=user.id).all()
            else:
                from app.models.task_models import TaskAssignment
                assignments = TaskAssignment.query.filter_by(user_id=user.id).all()
                task_activity_ids = set(t.task.activity_id for t in assignments if t.task and t.task.activity_id)
                activities = Activity.query.filter(Activity.id.in_(task_activity_ids)).all() if task_activity_ids else []

        slow_activities = []
        for activity in activities:
            if activity.status == 'in_progress' and activity.progress_percentage < 30:
                slow_activities.append(activity)

        if slow_activities:
            first_activity = slow_activities[0]
            recommendations.append({
                'type': 'info',
                'title': '⚙️ متابعة الأنشطة',
                'message': f'النشاط "{first_activity.activity_name}" تقدمه منخفض ({first_activity.progress_percentage:.0f}%). ركز عليه لتحسين الإنجاز',
                'action_url': f'/employee/activities/{first_activity.id}',
                'icon': 'microchip',
                'priority': 'medium',
                'confidence': 80
            })

        return recommendations

    @staticmethod
    def _get_break_recommendations(user):
        """توصيات لوقت الراحة"""
        recommendations = []
        
        # إذا كان هناك العديد من المهام المكتملة اليوم، اقترح راحة
        today = date.today()
        today_start = datetime.combine(today, datetime.min.time())
        
        if user.role == 'delegate':
            completed_today = Task.query.filter(
                Task.delegate_id == user.id,
                Task.status == 'completed',
                Task.updated_at >= today_start
            ).count()
        else:
            from app.models.task_models import TaskAssignment
            completed_today = TaskAssignment.query.filter(
                TaskAssignment.user_id == user.id,
                TaskAssignment.status == 'completed',
                TaskAssignment.completion_date >= today_start
            ).count()

        if completed_today >= 3:
            recommendations.append({
                'type': 'success',
                'title': '☕ وقت للراحة',
                'message': f'أنجزت {completed_today} مهام اليوم! خذ استراحة قصيرة لتجديد النشاط',
                'action_url': '#',
                'icon': 'coffee',
                'priority': 'low',
                'confidence': 70
            })

        return recommendations

    # ============================================
    # توصيات المشروع
    # ============================================

    @staticmethod
    def get_project_recommendations(project_id, limit=5):
        """
        الحصول على توصيات ذكية لمشروع معين
        
        Args:
            project_id: معرف المشروع
            limit: الحد الأقصى لعدد التوصيات
            
        Returns:
            list: قائمة بالتوصيات
        """
        try:
            project = Project.query.get(project_id)
            if not project:
                return []

            recommendations = []

            # 1. توصيات الميزانية
            budget_recs = AIRecommendationService._get_budget_recommendations(project)
            recommendations.extend(budget_recs)

            # 2. توصيات الجدول الزمني
            schedule_recs = AIRecommendationService._get_schedule_recommendations(project)
            recommendations.extend(schedule_recs)

            # 3. توصيات الموارد
            resource_recs = AIRecommendationService._get_resource_recommendations(project)
            recommendations.extend(resource_recs)

            # 4. توصيات المخاطر
            risk_recs = AIRecommendationService._get_risk_recommendations(project)
            recommendations.extend(risk_recs)

            # 5. توصيات الإنجاز
            progress_recs = AIRecommendationService._get_progress_recommendations(project)
            recommendations.extend(progress_recs)

            return recommendations[:limit]

        except Exception as e:
            logger.error(f"Error in get_project_recommendations: {str(e)}")
            return []

    @staticmethod
    def _get_budget_recommendations(project):
        """توصيات الميزانية للمشروع"""
        recommendations = []

        if project.performance:
            cpi = project.performance.cpi or 1.0
            
            if cpi < 0.8:
                recommendations.append({
                    'type': 'danger',
                    'title': '💰 تجاوز الميزانية',
                    'message': f'نسبة كفاءة التكلفة (CPI = {cpi:.2f}) منخفضة. يوصى بمراجعة المصروفات وتقليل الهدر',
                    'priority': 'high',
                    'confidence': 85
                })
            elif cpi > 1.2:
                recommendations.append({
                    'type': 'success',
                    'title': '✅ أداء مالي ممتاز',
                    'message': f'نسبة كفاءة التكلفة (CPI = {cpi:.2f}) ممتازة. استمر بنفس الكفاءة',
                    'priority': 'medium',
                    'confidence': 90
                })

        return recommendations

    @staticmethod
    def _get_schedule_recommendations(project):
        """توصيات الجدول الزمني للمشروع"""
        recommendations = []

        if project.performance:
            spi = project.performance.spi or 1.0
            
            if spi < 0.8:
                recommendations.append({
                    'type': 'danger',
                    'title': '⏰ تأخر في الجدول',
                    'message': f'نسبة كفاءة الجدول (SPI = {spi:.2f}) منخفضة. يوصى بتسريع المهام الحرجة',
                    'priority': 'high',
                    'confidence': 85
                })
            elif spi > 1.1:
                recommendations.append({
                    'type': 'success',
                    'title': '🚀 متقدم عن الجدول',
                    'message': f'المشروع متقدم عن الجدول المخطط (SPI = {spi:.2f})',
                    'priority': 'low',
                    'confidence': 80
                })

        # الأنشطة على المسار الحرج
        critical_activities = Activity.query.filter_by(
            project_id=project.id,
            is_critical=True,
            status='in_progress'
        ).limit(3).all()

        if critical_activities:
            activity_names = ', '.join([a.activity_name for a in critical_activities])
            recommendations.append({
                'type': 'warning',
                'title': '🔴 أنشطة حرجة',
                'message': f'هذه الأنشطة على المسار الحرج وتحتاج متابعة: {activity_names}',
                'priority': 'high',
                'confidence': 90
            })

        return recommendations

    @staticmethod
    def _get_resource_recommendations(project):
        """توصيات الموارد للمشروع"""
        recommendations = []

        # الموارد المنخفضة
        from app.models.primavera_models import Resource, ActivityResource
        
        low_resources = db.session.query(
            Resource, func.sum(ActivityResource.planned_quantity).label('total_allocated')
        ).join(
            ActivityResource, Resource.id == ActivityResource.resource_id
        ).join(
            Activity, ActivityResource.activity_id == Activity.id
        ).filter(
            Activity.project_id == project.id,
            Resource.minimum_quantity > 0,
            Resource.available_quantity < Resource.minimum_quantity
        ).group_by(Resource.id).all()

        if low_resources:
            resource_names = ', '.join([r[0].name for r in low_resources[:3]])
            recommendations.append({
                'type': 'warning',
                'title': '📦 مخزون منخفض',
                'message': f'الموارد التالية منخفضة: {resource_names}. يوصى بإعادة تزويدها',
                'priority': 'high',
                'confidence': 85
            })

        return recommendations

    @staticmethod
    def _get_risk_recommendations(project):
        """توصيات المخاطر للمشروع"""
        recommendations = []

        # المشاريع المتأخرة
        today = date.today()
        if project.dates and project.dates.planned_finish:
            planned_finish = project.dates.planned_finish
            if hasattr(planned_finish, 'date'):
                planned_finish = planned_finish.date()
            
            if planned_finish and planned_finish < today:
                delay = (today - planned_finish).days
                recommendations.append({
                    'type': 'danger',
                    'title': '⚠️ مشروع متأخر',
                    'message': f'المشروع متأخر {delay} يوماً عن الجدول المخطط',
                    'priority': 'high',
                    'confidence': 95
                })

        return recommendations

    @staticmethod
    def _get_progress_recommendations(project):
        """توصيات التقدم للمشروع"""
        recommendations = []

        progress = project.progress.progress_percentage if project.progress else 0
        
        if progress >= 75 and progress < 90:
            recommendations.append({
                'type': 'success',
                'title': '🎯 مرحلة متقدمة',
                'message': f'المشروع في مرحلة متقدمة ({progress:.0f}%). ركز على إنهاء المهام المتبقية',
                'priority': 'medium',
                'confidence': 85
            })
        elif progress < 25 and progress > 0:
            recommendations.append({
                'type': 'info',
                'title': '🚀 بداية المشروع',
                'message': 'المشروع لا يزال في بدايته. حافظ على الزخم وخطط للمراحل القادمة',
                'priority': 'low',
                'confidence': 75
            })

        return recommendations

    # ============================================
    # حفظ التوصيات
    # ============================================

    @staticmethod
    def save_recommendation(org_id, recommendation_type, title, description, 
                           related_project_id=None, priority='medium', confidence=75):
        """حفظ توصية في قاعدة البيانات"""
        try:
            suggestion = AISuggestion(
                org_id=org_id,
                suggestion_type=recommendation_type,
                priority=priority,
                title=title,
                description=description,
                related_project_id=related_project_id,
                confidence_score=confidence,
                status='active'
            )
            db.session.add(suggestion)
            db.session.commit()
            return suggestion
        except Exception as e:
            logger.error(f"Error in save_recommendation: {str(e)}")
            db.session.rollback()
            return None

    # ============================================
    # معالجة أوامر الذكاء الاصطناعي
    # ============================================

    @staticmethod
    def process_ai_command(command_id):
        """معالجة أمر ذكاء اصطناعي"""
        try:
            command = AICommand.query.get(command_id)
            if not command:
                return {'success': False, 'error': 'Command not found'}

            # تحديث الحالة
            command.status = 'processing'
            command.started_at = datetime.utcnow()
            db.session.commit()

            # معالجة حسب نوع الأمر
            result = None
            if command.command_type == 'analyze':
                result = AIRecommendationService._analyze_command(command)
            elif command.command_type == 'predict':
                result = AIRecommendationService._predict_command(command)
            elif command.command_type == 'suggest':
                result = AIRecommendationService._suggest_command(command)
            else:
                result = {'message': 'Command processed', 'data': None}

            # تحديث النتيجة
            command.status = 'completed'
            command.completed_at = datetime.utcnow()
            command.result_data = result
            command.processing_time = (command.completed_at - command.started_at).total_seconds()
            db.session.commit()

            return {'success': True, 'result': result}

        except Exception as e:
            logger.error(f"Error in process_ai_command: {str(e)}")
            command.status = 'failed'
            command.processing_notes = str(e)
            db.session.commit()
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _analyze_command(command):
        """تحليل أمر تحليلي"""
        target = command.target_type
        
        if target == 'project':
            # تحليل المشروع
            project = Project.query.filter_by(org_id=command.org_id).first()
            if project:
                return {
                    'analysis': 'project_analysis',
                    'data': {
                        'progress': project.progress.progress_percentage if project.progress else 0,
                        'status': project.status,
                        'recommendations': AIRecommendationService.get_project_recommendations(project.id)
                    }
                }
        elif target == 'task':
            # تحليل المهام
            tasks = Task.query.join(Project).filter(Project.org_id == command.org_id).all()
            return {
                'analysis': 'tasks_analysis',
                'data': {
                    'total': len(tasks),
                    'completed': len([t for t in tasks if t.status == 'completed']),
                    'overdue': len([t for t in tasks if t.status in ['pending', 'in_progress'] and 
                                    hasattr(t, 'is_delayed') and t.is_delayed])
                }
            }
        
        return {'message': 'Analysis completed', 'data': None}

    @staticmethod
    def _predict_command(command):
        """معالجة أمر تنبؤي"""
        return {
            'prediction': 'estimated_completion',
            'confidence': 85,
            'estimated_date': (datetime.now() + timedelta(days=30)).isoformat()
        }

    @staticmethod
    def _suggest_command(command):
        """معالجة أمر اقتراح"""
        recommendations = AIRecommendationService.get_project_recommendations(
            command.org_id
        ) if command.target_type == 'project' else []
        
        return {
            'suggestions': recommendations,
            'count': len(recommendations)
        }

    # ============================================
    # تحديث تلقائي للتوصيات
    # ============================================

    @staticmethod
    def update_all_recommendations(org_id=None):
        """تحديث جميع التوصيات للمنظمة"""
        try:
            query = Project.query
            if org_id:
                query = query.filter_by(org_id=org_id)
            
            projects = query.all()
            
            for project in projects:
                recommendations = AIRecommendationService.get_project_recommendations(project.id)
                
                # حفظ التوصيات الجديدة
                for rec in recommendations:
                    AIRecommendationService.save_recommendation(
                        org_id=project.org_id,
                        recommendation_type=rec.get('type', 'general'),
                        title=rec.get('title', ''),
                        description=rec.get('message', ''),
                        related_project_id=project.id,
                        priority=rec.get('priority', 'medium'),
                        confidence=rec.get('confidence', 75)
                    )
            
            return {'success': True, 'projects_updated': len(projects)}
            
        except Exception as e:
            logger.error(f"Error in update_all_recommendations: {str(e)}")
            return {'success': False, 'error': str(e)}
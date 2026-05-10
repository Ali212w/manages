"""
models/__init__.py - تهيئة نماذج قاعدة البيانات
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from datetime import datetime, date 
from flask import g
# استيراد جميع النماذج
from .core_models import *
from .project_models import *
from .task_models import *
from .document_models import *
from .finance_models import *
from .ai_models import *
from .communication_models import *
from .primavera_models import *
from .enterprise_models import *
# إنشاء كائنات Flask Extensions
from app.extensions import db,login_manager



def init_models(app):
    """تهيئة النماذج مع التطبيق"""
    db.init_app(app)
    login_manager.init_app(app)
    
    # استيراد النماذج بعد تهيئة db
    from .core_models import User, Organization, Department,Subscription,PlatformOwner,PlatformAdmin,SubscriptionPlan,PlatformAuditLog,PlatformNotification
    from .project_models import Project,Milestone, Client, Consultant, Supplier,PurchaseOrder,PurchaseOrderItem,ProjectLocation,NotebookEntry,ProjectDates,ProjectBudget,ProjectCost,ProjectPerformance,ProjectProgress,ProjectStatistics,ProjectCodeDictionary,ProjectCodeValue,ProjectCodeAssignment,ProjectUDF,FundingSource,BudgetLog,SpendingPlanItem,Issue,QualityCheck
    from .task_models import Task, TaskPlanning,TaskExecution,TaskProgress,TaskLocation,TaskVerification,TaskResource,TaskDependency,TaskAssignment,TaskRequirement,TaskRequirementVerification,TaskSafetyCheck,TaskMaterialCheck,TaskTeamBriefing,TaskProgressUpdate, DailyReport,DailyReportTask,DailyReportPhoto
    from .document_models import BillItem,BillItemActivity, ProjectDocument,DocumentBillItem
    from .finance_models import MaterialItem,MaterialTransaction, Invoice,InvoiceItem,Payment
    from .ai_models import Risk,RiskUpdate,SafetyInspection, Notification,AuditLog,SystemMetric, UserSkill, ChangeRequest, Meeting, AITask, AIRecommendation,AICommand,AICommandAttachment,AIReport,AISuggestion,AIExtraction
    from .communication_models import ProjectChat,ChatParticipant,ChatMessage,Comment,Mention,Attachment
    from .primavera_models import EPSOBSAssignment,EPS,WBS,Calendar,Activity,ActivityRelationship,Resource,ActivityResource,ResourceRequest,ResourceRequestUpdate,ResourceRequestNotification,ResourceDelivery,ResourceDeliveryUpdate,ResourceRequestItem,Baseline,ActivityStep,ActivityExpense,ActivityRisk,ActivityFeedback,ActivityDocument,EquipmentRequest,EquipmentRequestUpdate,EquipmentRequestNotification,EquipmentRequestItem,EquipmentDelivery,EquipmentDeliveryUpdate,EquipmentOfferHistory                            
    from .enterprise_models import OBS,Role,ResourceCode,ActivityCodeDictionary,ActivityCodeValue,ActivityCodeAssignment,UDF,GlobalChange,AdminPreference
    # تهيئة user_loader لـ Flask-Login
    # @login_manager.user_loader
    # def load_user(user_id):
    #     return User.query.get(int(user_id))
    # علاقات PrimaveraProject مع OBS
    # PrimaveraProject.obs = db.relationship('OBS', foreign_keys='PrimaveraProject.obs_id', backref='primavera_projects')
    
    # # علاقات Activity مع Role
    # Activitys.role = db.relationship('Role', foreign_keys='Activitys.role_id', backref='activity_refs')
    
    # # علاقات Resource مع Role
    # Resource.role = db.relationship('Role', foreign_keys='Resource.role_id', backref='resource_refs')
    
    # ============================================
    # دوال مساعدة للاستعلامات
    # ============================================
    
    def get_enterprise_stats(org_id):
        """الحصول على إحصائيات المؤسسة"""
        from sqlalchemy import func
        
        return {
            # إحصائيات EPS
            'eps_count': EPS.query.filter_by(org_id=org_id).count(),
            
            # إحصائيات OBS
            'obs_count': OBS.query.filter_by(org_id=org_id).count(),
            
            # إحصائيات الموارد
            'resources_count': Resource.query.filter_by(org_id=org_id).count(),
            
            # إحصائيات الأدوار
            'roles_count': Role.query.filter_by(org_id=org_id).count(),
            
            # إحصائيات أكواد الأنشطة - ✅ تم التصحيح
            'activity_code_dicts_count': ActivityCodeDictionary.query.filter_by(org_id=org_id).count(),
            'activity_code_values_count': ActivityCodeValue.query.join(ActivityCodeDictionary).filter(
                ActivityCodeDictionary.org_id == org_id
            ).count(),
            
            # إحصائيات أكواد المشاريع - ✅ تم التصحيح
            'project_code_dicts_count': ProjectCodeDictionary.query.filter_by(org_id=org_id).count(),
            'project_code_values_count': ProjectCodeValue.query.join(ProjectCodeDictionary).filter(
                ProjectCodeDictionary.org_id == org_id
            ).count(),
            
            # إحصائيات الحقول المخصصة
            'udf_count': UDF.query.filter_by(org_id=org_id).count(),
        }

    
    # إضافة الدوال المساعدة إلى `g` في كل طلب
    @app.before_request
    def load_enterprise_stats():
        if current_user.is_authenticated and hasattr(current_user, 'org_id'):
            g.enterprise_stats = get_enterprise_stats(current_user.org_id)
    # إنشاء الجداول
    with app.app_context():
        db.create_all()
    
    return db



# تصدير النماذج
__all__ = [
    'db',
    'init_models',
    'User',
    'Organization',
    'Department',
    'Subscription',
    'Project',
    'WBSNode',
    'Activity',
    'Task',
    'TaskRequirement',
    'TaskRequirementVerification',
    'TaskSafetyCheck',
    'TaskMaterialCheck',
    'TaskTeamBriefing',
    'PlatformAdmin',
    'PlatformOwner',
    'BillItem',
    'ProjectDocument',
    'DailyReport',
    'Risk',
    'Notification',
    'UserSkill',
    'ChangeRequest',
    'Meeting',
    'AITask',
    'AIRecommendation',
    'Client',
    'Consultant',
    'Supplier',
    'MaterialItem',
    'PurchaseOrder',
    'Invoice',
    'ProjectChat',
    'ChatParticipant',
    'ChatMessage',
    'Comment',
    'Mention',
    'Attachment',
    'EPS',
    'WBS',
    'Calendar',
    'Activitys',
    'ActivityRelationship',
    'Resource',
    'ActivityResource',
    'PrimaveraProject',
    'Baseline',
    'OBS',
    'Role',
    'ResourceCode',
    'ActivityCode',
    'UDF',
    'GlobalChange',
    'AdminPreference'

    
]
# app/services/smart_communicator.py

"""
نظام التواصل الذكي - يدير التواصل بين الأطراف المعنية
"""

from datetime import datetime, timedelta
from app.models import db
from app.models.communication_models import ProjectChat, ChatMessage
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class SmartCommunicator:
    """نظام تواصل ذكي"""
    
    def __init__(self):
        self.notification_service = NotificationService()
    
    def create_auto_meeting(self, project, topic, participants):
        """إنشاء اجتماع تلقائي"""
        from app.models.project_models import Meeting
        
        meeting = Meeting(
            project_id=project.id,
            meeting_code=f"MTG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            title=f"اجتماع تلقائي: {topic}",
            purpose=f"مناقشة {topic}",
            meeting_type='auto',
            scheduled_date=datetime.now() + timedelta(days=2),
            organizer_id=project.project_manager_id,
            status='scheduled',
            agenda=[topic],
            attendees=participants
        )
        
        db.session.add(meeting)
        db.session.commit()
        
        # إشعار للمشاركين
        for participant in participants:
            self.notification_service.meeting_invitation(meeting, participant)
    
    def send_team_alert(self, project, message, priority='medium'):
        """إرسال تنبيه للفريق"""
        team_members = self.get_team_members(project.id)
        
        for member in team_members:
            self.notification_service.team_alert(member, project, message, priority)
    
    def get_team_members(self, project_id):
        """الحصول على أعضاء الفريق"""
        from app.models.core_models import User
        
        tasks = Task.query.filter_by(project_id=project_id).all()
        member_ids = set()
        
        for task in tasks:
            if task.delegate_id:
                member_ids.add(task.delegate_id)
            if task.supervisor_id:
                member_ids.add(task.supervisor_id)
        
        return User.query.filter(User.id.in_(member_ids)).all()
    
    def create_progress_chat(self, project, milestone):
        """إنشاء محادثة حول التقدم"""
        chat = ProjectChat(
            project_id=project.id,
            chat_type='progress',
            name=f'مناقشة إنجاز: {milestone}',
            is_active=True,
            created_by=project.project_manager_id
        )
        
        db.session.add(chat)
        
        # إضافة المشاركين
        team_members = self.get_team_members(project.id)
        from app.models.communication_models import ChatParticipant
        
        for member in team_members:
            participant = ChatParticipant(
                chat_id=chat.id,
                user_id=member.id,
                role='member'
            )
            db.session.add(participant)
        
        db.session.commit()
        
        return chat
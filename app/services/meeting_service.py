"""
meeting_service.py - خدمة إدارة الاجتماعات الذكية
"""

from datetime import datetime, timedelta
from app.models import db
from flask_login import current_user
from app.models import Meeting, Project, User, Notification
from app.services.notification_service import NotificationService
import logging

logger = logging.getLogger(__name__)


class MeetingService:
    """خدمة إدارة الاجتماعات - إنشاء، جدولة، إشعارات"""
    
    @classmethod
    def create_meeting(cls, data):
        """إنشاء اجتماع جديد"""
        meeting = Meeting(
            project_id=data.get('project_id'),
            meeting_code=cls._generate_meeting_code(),
            title=data.get('title'),
            purpose=data.get('purpose'),
            meeting_type=data.get('meeting_type', 'progress'),
            location=data.get('location'),
            is_virtual=data.get('is_virtual', False),
            virtual_link=data.get('virtual_link'),
            scheduled_date=datetime.strptime(data.get('scheduled_date'), '%Y-%m-%d') if data.get('scheduled_date') else datetime.now(),
            start_time=datetime.strptime(data.get('start_time'), '%H:%M').time() if data.get('start_time') else None,
            end_time=datetime.strptime(data.get('end_time'), '%H:%M').time() if data.get('end_time') else None,
            organizer_id=data.get('organizer_id'),
            secretary_id=data.get('secretary_id'),
            status='scheduled',
            agenda=data.get('agenda', []),
            attendees=data.get('attendees', [])
        )
        
        db.session.add(meeting)
        db.session.commit()
        
        # إرسال إشعارات للمشاركين
        cls._notify_participants(meeting)
        
        return meeting
    
    @classmethod
    def _generate_meeting_code(cls):
        """إنشاء كود اجتماع فريد"""
        from datetime import datetime
        return f"MTG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    @classmethod
    def _notify_participants(cls, meeting):
        """إرسال إشعارات للمشاركين في الاجتماع"""
        # إشعار للمنظم
        if meeting.organizer_id:
            NotificationService.meeting_scheduled(
                user_id=meeting.organizer_id,
                meeting=meeting,
                role='organizer'
            )
        
        # إشعار للسكرتير
        if meeting.secretary_id and meeting.secretary_id != meeting.organizer_id:
            NotificationService.meeting_scheduled(
                user_id=meeting.secretary_id,
                meeting=meeting,
                role='secretary'
            )
        
        # إشعار للحضور
        for attendee in meeting.attendees:
            if isinstance(attendee, dict):
                user_id = attendee.get('user_id')
            elif isinstance(attendee, int):
                user_id = attendee
            else:
                continue
            
            if user_id and user_id not in [meeting.organizer_id, meeting.secretary_id]:
                NotificationService.meeting_scheduled(
                    user_id=user_id,
                    meeting=meeting,
                    role='attendee'
                )
    
    @classmethod
    def send_meeting_reminders(cls):
        """إرسال تذكيرات للاجتماعات القادمة"""
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        one_hour_from_now = now + timedelta(hours=1)
        
        # اجتماعات خلال الـ 24 ساعة القادمة
        upcoming_meetings = Meeting.query.filter(
            Meeting.scheduled_date >= now.date(),
            Meeting.scheduled_date <= tomorrow.date(),
            Meeting.status == 'scheduled'
        ).all()
        
        reminders_sent = 0
        for meeting in upcoming_meetings:
            meeting_datetime = datetime.combine(meeting.scheduled_date, meeting.start_time) if meeting.start_time else meeting.scheduled_date
            
            if meeting_datetime <= one_hour_from_now:
                # إرسال تذكير عاجل
                cls._send_urgent_reminder(meeting)
                reminders_sent += 1
            elif meeting_datetime <= tomorrow:
                # إرسال تذكير مبكر
                cls._send_early_reminder(meeting)
                reminders_sent += 1
        
        logger.info(f"📧 تم إرسال {reminders_sent} تذكير للاجتماعات")
        
        return reminders_sent
    
    @classmethod
    def _send_urgent_reminder(cls, meeting):
        """إرسال تذكير عاجل (قبل ساعة)"""
        participants = cls._get_all_participants(meeting)
        
        for participant in participants:
            NotificationService.meeting_reminder(
                user_id=participant.id,
                meeting=meeting,
                urgency='urgent'
            )
    
    @classmethod
    def _send_early_reminder(cls, meeting):
        """إرسال تذكير مبكر (قبل 24 ساعة)"""
        participants = cls._get_all_participants(meeting)
        
        for participant in participants:
            NotificationService.meeting_reminder(
                user_id=participant.id,
                meeting=meeting,
                urgency='normal'
            )
    
    @classmethod
    def _get_all_participants(cls, meeting):
        """الحصول على جميع المشاركين في الاجتماع"""
        participant_ids = set()
        
        if meeting.organizer_id:
            participant_ids.add(meeting.organizer_id)
        if meeting.secretary_id:
            participant_ids.add(meeting.secretary_id)
        
        for attendee in meeting.attendees:
            if isinstance(attendee, dict):
                user_id = attendee.get('user_id')
            elif isinstance(attendee, int):
                user_id = attendee
            else:
                continue
            if user_id:
                participant_ids.add(user_id)
        
        return User.query.filter(User.id.in_(participant_ids)).all()
    
    @classmethod
    def update_meeting_status(cls, meeting_id, status, minutes=None, decisions=None):
        """تحديث حالة الاجتماع"""
        meeting = Meeting.query.get(meeting_id)
        if not meeting:
            return None
        
        meeting.status = status
        
        if status == 'completed':
            meeting.actual_end_time = datetime.now()
            if minutes:
                meeting.minutes = minutes
            if decisions:
                meeting.decisions = decisions
        
        db.session.commit()
        
        # إشعار بانتهاء الاجتماع
        if status == 'completed':
            participants = cls._get_all_participants(meeting)
            for participant in participants:
                NotificationService.meeting_completed(
                    user_id=participant.id,
                    meeting=meeting
                )
        
        return meeting
    
    @classmethod
    def get_upcoming_meetings(cls, user_id, days=7):
        """الحصول على الاجتماعات القادمة لمستخدم"""
        today = datetime.now().date()
        end_date = today + timedelta(days=days)
        
        # الاجتماعات التي يشارك فيها المستخدم
        meetings = Meeting.query.filter(
            Meeting.scheduled_date >= today,
            Meeting.scheduled_date <= end_date,
            Meeting.status == 'scheduled'
        ).all()
        
        # تصفية الاجتماعات التي يشارك فيها المستخدم
        user_meetings = []
        for meeting in meetings:
            participants = cls._get_all_participants(meeting)
            if current_user.id in [p.id for p in participants]:
                user_meetings.append(meeting)
        
        return user_meetings
"""
communication_models.py - نماذج التواصل والمحادثات
"""
from ..extensions import db
from sqlalchemy import Index, UniqueConstraint
from datetime import datetime
import uuid

class ProjectChat(db.Model):
    """غرف المحادثة للمشاريع والمهام"""
    __tablename__ = 'project_chats'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    activity_id = db.Column(db.Integer, db.ForeignKey('activities.id'), nullable=True)  # ✅ إضافة هذا الحقل
    chat_type = db.Column(db.String(50), nullable=False)  # 'project', 'task', 'activity', 'direct'
    name = db.Column(db.String(200))
    description = db.Column(db.Text)
    
    is_active = db.Column(db.Boolean, default=True)
    is_archived = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # العلاقات
    # creator = db.relationship('User', foreign_keys=[created_by])
    participants = db.relationship('ChatParticipant', backref='chat', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('ChatMessage', backref='chat', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_chat_project', 'project_id'),
        Index('idx_chat_task', 'task_id'),
        Index('idx_chat_activity', 'activity_id'),
        Index('idx_chat_type', 'chat_type'),
        Index('idx_chat_created', 'created_at'),
    )

class ChatParticipant(db.Model):
    """المشاركون في المحادثات"""
    __tablename__ = 'chat_participants'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('project_chats.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    role = db.Column(db.String(50), default='member')  # 'admin', 'moderator', 'member'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen = db.Column(db.DateTime)
    is_muted = db.Column(db.Boolean, default=False)
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id],backref='chat_participations')
    
    __table_args__ = (
        Index('idx_participant_chat', 'chat_id'),
        Index('idx_participant_user', 'user_id'),
        UniqueConstraint('chat_id', 'user_id', name='uq_chat_user'),
    )

class ChatMessage(db.Model):
    """الرسائل في المحادثات"""
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    chat_id = db.Column(db.Integer, db.ForeignKey('project_chats.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(50), default='text')  # 'text', 'image', 'file'
    
    is_read = db.Column(db.Boolean, default=False)
    is_edited = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    sender = db.relationship('User', foreign_keys=[sender_id])
    mentions = db.relationship('Mention', backref='message', lazy=True, cascade='all, delete-orphan')
    attachments = db.relationship('Attachment', backref='message', lazy=True, cascade='all, delete-orphan')
    reply_to = db.relationship('ChatMessage', remote_side=[id], backref='replies')
    __table_args__ = (
        Index('idx_message_chat', 'chat_id'),
        Index('idx_message_sender', 'sender_id'),
        Index('idx_message_created', 'created_at'),
        Index('idx_message_reply_to', 'reply_to_id'),
    )

class Comment(db.Model):
    """التعليقات على المهام والمشاريع"""
    __tablename__ = 'comments'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True)
    
    content = db.Column(db.Text, nullable=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    parent = db.relationship('Comment', remote_side=[id], backref='replies')
    mentions = db.relationship('Mention', backref='comment', lazy=True, cascade='all, delete-orphan')
    
    __table_args__ = (
        Index('idx_comment_task', 'task_id'),
        Index('idx_comment_project', 'project_id'),
        Index('idx_comment_user', 'user_id'),
        Index('idx_comment_parent', 'parent_id'),
        Index('idx_comment_created', 'created_at'),
    )

class Mention(db.Model):
    """الإشارات للمستخدمين"""
    __tablename__ = 'mentions'
    
    id = db.Column(db.Integer, primary_key=True)
    
    message_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True)
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    # العلاقات
    user = db.relationship('User', foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_mention_user', 'user_id'),
        Index('idx_mention_message', 'message_id'),
        Index('idx_mention_comment', 'comment_id'),
        Index('idx_mention_read', 'is_read'),
    )

class Attachment(db.Model):
    """الملفات المرفقة في المحادثات"""
    __tablename__ = 'attachments'
    
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
    message_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)  # بالبايت
    file_type = db.Column(db.String(100))
    mime_type = db.Column(db.String(100))
    file_extension = db.Column(db.String(20))
    
    # مسارات الملفات
    file_path = db.Column(db.String(1000))
    file_url = db.Column(db.String(500))
    thumbnail_url = db.Column(db.String(1000))  # للصور والفيديوهات
    
    # بيانات إضافية للصور
    image_width = db.Column(db.Integer)
    image_height = db.Column(db.Integer)
    
    # بيانات إضافية للفيديو
    video_duration = db.Column(db.Integer)  # بالثواني
    video_thumbnail = db.Column(db.String(1000))
    
    # حالة المعالجة
    processing_status = db.Column(db.String(20), default='completed')  # pending, processing, completed, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # العلاقات
    sender = db.relationship('User', foreign_keys=[sender_id])
    
    __table_args__ = (
        Index('idx_attachment_message', 'message_id'),
        Index('idx_attachment_sender', 'sender_id'),
        Index('idx_attachment_file_type', 'file_type'),
    )

# class Notification(db.Model):
#     """الإشعارات"""
#     __tablename__ = 'notifications'
    
#     id = db.Column(db.Integer, primary_key=True)
#     uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    
#     user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
#     title = db.Column(db.String(200), nullable=False)
#     message = db.Column(db.Text, nullable=False)
#     notification_type = db.Column(db.String(50))  # 'mention', 'comment', 'message', 'task'
    
#     related_link = db.Column(db.String(500))
#     is_read = db.Column(db.Boolean, default=False)
    
#     created_at = db.Column(db.DateTime, default=datetime.utcnow)
#     read_at = db.Column(db.DateTime)
    
#     # العلاقات
#     user = db.relationship('User', foreign_keys=[user_id], backref='notifications')
    
#     __table_args__ = (
#         Index('idx_notification_user', 'user_id'),
#         Index('idx_notification_read', 'is_read'),
#         Index('idx_notification_created', 'created_at'),
#     )
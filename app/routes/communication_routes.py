"""
communication_routes.py - مسارات التواصل والمحادثات
"""

from flask import render_template, request, jsonify, redirect, url_for, flash, session,send_file, send_from_directory, abort, current_app
from flask_login import login_required, current_user
from app.models import db, User, Project, Task, Notification
from app.models.communication_models import ProjectChat, ChatParticipant, ChatMessage, Mention, Attachment
from app.routes import communication_bp
from datetime import datetime
import logging
from sqlalchemy import or_, and_
import os
import uuid
from werkzeug.utils import secure_filename
from PIL import Image
import moviepy.editor as mp
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================
# دوال مساعدة
# ============================================

def get_user_chats(user_id):
    """الحصول على جميع محادثات المستخدم (بما في ذلك محادثات الأنشطة)"""
    try:
        participations = ChatParticipant.query.filter_by(user_id=user_id).all()
        chat_ids = [p.chat_id for p in participations]
        
        chats = ProjectChat.query.filter(
            ProjectChat.id.in_(chat_ids),
            ProjectChat.is_archived == False
        ).order_by(ProjectChat.updated_at.desc()).all()
        
        for chat in chats:
            # تحديد اسم المحادثة إذا كان مرتبطاً بنشاط
            if chat.chat_type == 'activity' and chat.activity_id:
                from app.models.primavera_models import Activity
                activity = Activity.query.get(chat.activity_id)
                if activity and not chat.name:
                    chat.name = f"مناقشة النشاط: {activity.activity_name}"
            
            last_message = ChatMessage.query.filter_by(
                chat_id=chat.id,
                is_deleted=False
            ).order_by(ChatMessage.created_at.desc()).first()
            chat.last_message = last_message
            
            unread_count = ChatMessage.query.filter(
                ChatMessage.chat_id == chat.id,
                ChatMessage.sender_id != user_id,
                ChatMessage.is_read == False,
                ChatMessage.is_deleted == False
            ).count()
            chat.unread_count = unread_count
        
        return chats
    except Exception as e:
        logger.error(f"Error in get_user_chats: {str(e)}")
        return []


def get_or_create_direct_chat(user1_id, user2_id):
    """إنشاء أو الحصول على محادثة مباشرة بين مستخدمين"""
    try:
        # البحث عن محادثة موجودة
        existing_chat = db.session.query(ProjectChat).join(
            ChatParticipant
        ).filter(
            ProjectChat.chat_type == 'direct',
            ProjectChat.is_archived == False
        ).group_by(ProjectChat.id).having(
            db.func.count(ChatParticipant.user_id) == 2
        ).all()
        
        for chat in existing_chat:
            participants = [p.user_id for p in chat.participants]
            if user1_id in participants and user2_id in participants:
                return chat
        
        # إنشاء محادثة جديدة
        chat = ProjectChat(
            chat_type='direct',
            name=f"محادثة بين {User.query.get(user1_id).full_name} و {User.query.get(user2_id).full_name}",
            is_active=True,
            created_by=user1_id
        )
        db.session.add(chat)
        db.session.flush()
        
        # إضافة المشاركين
        participant1 = ChatParticipant(chat_id=chat.id, user_id=user1_id, role='member')
        participant2 = ChatParticipant(chat_id=chat.id, user_id=user2_id, role='member')
        db.session.add_all([participant1, participant2])
        
        db.session.commit()
        return chat
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in get_or_create_direct_chat: {str(e)}")
        return None


def create_project_chat(project_id, created_by, participants_ids):
    """إنشاء محادثة جماعية للمشروع"""
    try:
        project = Project.query.get(project_id)
        if not project:
            return None
        
        chat = ProjectChat(
            project_id=project_id,
            chat_type='project',
            name=f"محادثة مشروع {project.name}",
            description=f"محادثة فريق عمل مشروع {project.name}",
            is_active=True,
            created_by=created_by
        )
        db.session.add(chat)
        db.session.flush()
        
        # إضافة المشاركين
        for user_id in participants_ids:
            participant = ChatParticipant(chat_id=chat.id, user_id=user_id, role='member')
            db.session.add(participant)
        
        db.session.commit()
        return chat
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_project_chat: {str(e)}")
        return None


def create_task_chat(task_id, created_by, participants_ids):
    """إنشاء محادثة جماعية للمهمة"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return None
        
        chat = ProjectChat(
            task_id=task_id,
            chat_type='task',
            name=f"محادثة مهمة {task.task_name}",
            description=f"محادثة فريق عمل المهمة {task.task_name}",
            is_active=True,
            created_by=created_by
        )
        db.session.add(chat)
        db.session.flush()
        
        # إضافة المشاركين
        for user_id in participants_ids:
            participant = ChatParticipant(chat_id=chat.id, user_id=user_id, role='member')
            db.session.add(participant)
        
        db.session.commit()
        return chat
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_task_chat: {str(e)}")
        return None


# ============================================
# صفحات الدردشة
# ============================================

@communication_bp.route('/')
@login_required
def index():
    """الصفحة الرئيسية للدردشة - قائمة المحادثات"""
    chats = get_user_chats(current_user.id)
    
    # إحصائيات
    stats = {
        'total_chats': len(chats),
        'unread_total': sum(c.unread_count for c in chats if hasattr(c, 'unread_count')),
        'direct_chats': len([c for c in chats if c.chat_type == 'direct']),
        'project_chats': len([c for c in chats if c.chat_type == 'project']),
        'task_chats': len([c for c in chats if c.chat_type == 'task'])
    }
    
    return render_template('communication/index.html',
                         chats=chats,
                         stats=stats,
                         now=datetime.now())


@communication_bp.route('/chat/<int:chat_id>')
@login_required
def chat_room(chat_id):
    """غرفة المحادثة"""
    chat = ProjectChat.query.get_or_404(chat_id)
    
    # التحقق من مشاركة المستخدم
    participant = ChatParticipant.query.filter_by(
        chat_id=chat_id,
        user_id=current_user.id
    ).first()
    
    if not participant:
        flash('غير مصرح بالوصول إلى هذه المحادثة', 'danger')
        return redirect(url_for('communication.index'))
    
    # تحديث وقت آخر ظهور
    participant.last_seen = datetime.utcnow()
    db.session.commit()
    
    # تحديث الرسائل كمقروءة
    ChatMessage.query.filter(
        ChatMessage.chat_id == chat_id,
        ChatMessage.sender_id != current_user.id,
        ChatMessage.is_read == False
    ).update({'is_read': True, 'updated_at': datetime.utcnow()})
    db.session.commit()
    
    # جلب المشاركين
    participants = ChatParticipant.query.filter_by(chat_id=chat_id).all()
    
    return render_template('communication/chat.html',
                         chat=chat,
                         participants=participants,
                         current_user=current_user,
                         now=datetime.now())

# إضافة هذه الرواوتات في communication_routes.py

@communication_bp.route('/new-chat')
@login_required
def new_chat():
    """بدء محادثة جديدة - اختيار المستخدمين"""
    # جلب المستخدمين في نفس المؤسسة
    users = User.query.filter(
        User.org_id == current_user.org_id,
        User.is_user_active == True,
        User.id != current_user.id
    ).all()
    
    # تجميع المستخدمين حسب الدور
    users_by_role = {
        'org_admin': [],
        'project_manager': [],
        'supervisor': [],
        'delegate': [],
        'employee': [],
        'supplier': [],
        'client': [],
        'consultant': []
    }
    
    for user in users:
        if user.role in users_by_role:
            users_by_role[user.role].append(user)
    
    return render_template('communication/new_chat.html',
                         users_by_role=users_by_role,
                         now=datetime.now())


@communication_bp.route('/create-group-chat', methods=['POST'])
@login_required
def create_group_chat():
    """إنشاء محادثة جماعية جديدة"""
    try:
        chat_name = request.form.get('chat_name', '').strip()
        chat_type = request.form.get('chat_type', 'group')
        project_id = request.form.get('project_id', type=int)
        task_id = request.form.get('task_id', type=int)
        selected_users = request.form.getlist('selected_users[]')
        
        if not chat_name:
            flash('الرجاء إدخال اسم للمحادثة', 'danger')
            return redirect(url_for('communication.new_chat'))
        
        if not selected_users:
            flash('الرجاء اختيار مشاركين على الأقل', 'danger')
            return redirect(url_for('communication.new_chat'))
        
        # إضافة المستخدم الحالي تلقائياً
        if str(current_user.id) not in selected_users:
            selected_users.append(str(current_user.id))
        
        # إنشاء المحادثة
        chat = ProjectChat(
            chat_type=chat_type,
            name=chat_name,
            project_id=project_id,
            task_id=task_id,
            is_active=True,
            created_by=current_user.id
        )
        db.session.add(chat)
        db.session.flush()
        
        # إضافة المشاركين
        for user_id in selected_users:
            participant = ChatParticipant(
                chat_id=chat.id,
                user_id=int(user_id),
                role='admin' if int(user_id) == current_user.id else 'member'
            )
            db.session.add(participant)
        
        db.session.commit()
        
        flash('تم إنشاء المحادثة بنجاح', 'success')
        return redirect(url_for('communication.chat_room', chat_id=chat.id))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_group_chat: {str(e)}")
        flash(f'حدث خطأ: {str(e)}', 'danger')
        return redirect(url_for('communication.new_chat'))


@communication_bp.route('/api/chats/<int:chat_id>/add-participants', methods=['POST'])
@login_required
def add_chat_participants(chat_id):
    """إضافة مشاركين جدد إلى المحادثة"""
    try:
        chat = ProjectChat.query.get_or_404(chat_id)
        
        # التحقق من صلاحية المستخدم (يجب أن يكون منشئ المحادثة أو مديراً)
        if chat.created_by != current_user.id and current_user.role not in ['org_admin', 'project_manager']:
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        new_users = data.get('user_ids', [])
        
        added = []
        for user_id in new_users:
            existing = ChatParticipant.query.filter_by(
                chat_id=chat_id,
                user_id=user_id
            ).first()
            
            if not existing:
                participant = ChatParticipant(
                    chat_id=chat_id,
                    user_id=user_id,
                    role='member'
                )
                db.session.add(participant)
                added.append(user_id)
                
                # إشعار للمستخدم الجديد
                send_chat_invite_notification(user_id, current_user, chat)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'added_count': len(added),
            'added_users': added
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in add_chat_participants: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/chats/<int:chat_id>/leave', methods=['POST'])
@login_required
def leave_chat(chat_id):
    """مغادرة المحادثة"""
    try:
        participant = ChatParticipant.query.filter_by(
            chat_id=chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            return jsonify({'error': 'غير مصرح'}), 403
        
        db.session.delete(participant)
        db.session.commit()
        
        # إشعار للمشاركين الآخرين
        notify_chat_participants(chat_id, current_user.id, 'left')
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in leave_chat: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/search-users')
@login_required
def search_users():
    """API للبحث عن مستخدمين لإضافتهم للمحادثة"""
    try:
        query = request.args.get('q', '').strip()
        chat_id = request.args.get('chat_id', type=int)
        
        if len(query) < 2:
            return jsonify({'users': []})
        
        # البحث عن المستخدمين في نفس المؤسسة
        users_query = User.query.filter(
            User.org_id == current_user.org_id,
            User.is_user_active == True,
            User.id != current_user.id,
            User.full_name.ilike(f'%{query}%')
        )
        
        # استبعاد المستخدمين الموجودين بالفعل في المحادثة
        if chat_id:
            existing_participants = ChatParticipant.query.filter_by(chat_id=chat_id).all()
            existing_ids = [p.user_id for p in existing_participants]
            users_query = users_query.filter(User.id.notin_(existing_ids))
        
        users = users_query.limit(20).all()
        
        return jsonify({
            'success': True,
            'users': [{
                'id': u.id,
                'name': u.full_name,
                'email': u.email,
                'role': u.role,
                'avatar': u.profile_image
            } for u in users]
        })
        
    except Exception as e:
        logger.error(f"Error in search_users: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/messages/<int:message_id>/react', methods=['POST'])
@login_required
def react_to_message(message_id):
    """إضافة تفاعل (Reaction) على رسالة"""
    try:
        data = request.get_json()
        reaction = data.get('reaction', '👍')  # 👍, ❤️, 😂, 😮, 😢, 😡
        
        message = ChatMessage.query.get_or_404(message_id)
        
        # التحقق من وجود الرسالة في محادثة يشارك فيها المستخدم
        participant = ChatParticipant.query.filter_by(
            chat_id=message.chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            return jsonify({'error': 'غير مصرح'}), 403
        
        # تحديث التفاعلات (تخزين JSON)
        if not message.reactions:
            message.reactions = {}
        
        message.reactions[str(current_user.id)] = reaction
        db.session.commit()
        
        return jsonify({'success': True, 'reaction': reaction})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in react_to_message: {str(e)}")
        return jsonify({'error': str(e)}), 500
    
@communication_bp.route('/direct/<int:user_id>')
@login_required
def direct_chat(user_id):
    """بدء محادثة مباشرة مع مستخدم"""
    target_user = User.query.get_or_404(user_id)
    
    # لا يمكن بدء محادثة مع النفس
    if target_user.id == current_user.id:
        flash('لا يمكنك بدء محادثة مع نفسك', 'warning')
        return redirect(url_for('communication.index'))
    
    # الحصول على المحادثة أو إنشاؤها
    chat = get_or_create_direct_chat(current_user.id, target_user.id)
    
    if chat:
        return redirect(url_for('communication.chat_room', chat_id=chat.id))
    else:
        flash('حدث خطأ في إنشاء المحادثة', 'danger')
        return redirect(url_for('communication.index'))


@communication_bp.route('/project/<int:project_id>/chat')
@login_required
def project_chat(project_id):
    """فتح محادثة المشروع"""
    project = Project.query.get_or_404(project_id)
    
    # البحث عن محادثة المشروع
    chat = ProjectChat.query.filter_by(
        project_id=project_id,
        chat_type='project',
        is_archived=False
    ).first()
    
    if not chat:
        # إنشاء محادثة جديدة مع فريق المشروع
        # جلب جميع المشاركين في المشروع
        participants_ids = [project.project_manager_id] if project.project_manager_id else []
        
        # إضافة المشرفين والمناديب
        tasks = Task.query.filter_by(project_id=project_id).all()
        for task in tasks:
            if task.supervisor_id and task.supervisor_id not in participants_ids:
                participants_ids.append(task.supervisor_id)
            if task.delegate_id and task.delegate_id not in participants_ids:
                participants_ids.append(task.delegate_id)
        
        # إضافة المستخدم الحالي إذا لم يكن موجوداً
        if current_user.id not in participants_ids:
            participants_ids.append(current_user.id)
        
        chat = create_project_chat(project_id, current_user.id, participants_ids)
    
    if chat:
        return redirect(url_for('communication.chat_room', chat_id=chat.id))
    else:
        flash('حدث خطأ في إنشاء محادثة المشروع', 'danger')
        return redirect(url_for('communication.index'))


@communication_bp.route('/task/<int:task_id>/chat')
@login_required
def task_chat(task_id):
    """فتح محادثة المهمة"""
    task = Task.query.get_or_404(task_id)
    
    # البحث عن محادثة المهمة
    chat = ProjectChat.query.filter_by(
        task_id=task_id,
        chat_type='task',
        is_archived=False
    ).first()
    
    if not chat:
        # إنشاء محادثة جديدة مع فريق المهمة
        participants_ids = []
        
        if task.supervisor_id:
            participants_ids.append(task.supervisor_id)
        if task.delegate_id:
            participants_ids.append(task.delegate_id)
        
        # إضافة المستخدم الحالي إذا لم يكن موجوداً
        if current_user.id not in participants_ids:
            participants_ids.append(current_user.id)
        
        chat = create_task_chat(task_id, current_user.id, participants_ids)
    
    if chat:
        return redirect(url_for('communication.chat_room', chat_id=chat.id))
    else:
        flash('حدث خطأ في إنشاء محادثة المهمة', 'danger')
        return redirect(url_for('communication.index'))


# ============================================
# API Routes للدردشة
# ============================================

@communication_bp.route('/api/messages', methods=['GET'])
@login_required
def get_messages():
    """جلب رسائل المحادثة"""
    try:
        chat_id = request.args.get('chat_id', type=int)
        limit = request.args.get('limit', 50, type=int)
        before_id = request.args.get('before_id', type=int)
        
        if not chat_id:
            return jsonify({'error': 'chat_id مطلوب'}), 400
        
        participant = ChatParticipant.query.filter_by(
            chat_id=chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            return jsonify({'error': 'غير مصرح'}), 403
        
        query = ChatMessage.query.filter(
            ChatMessage.chat_id == chat_id,
            ChatMessage.is_deleted == False
        )
        
        if before_id:
            query = query.filter(ChatMessage.id < before_id)
        
        messages = query.order_by(ChatMessage.created_at.desc()).limit(limit).all()
        
        result_messages = []
        for msg in reversed(messages):
            # جلب المرفقات لكل رسالة
            attachments = []
            for att in msg.attachments:
                attachments.append({
                    'id': att.id,
                    'filename': att.original_filename,
                    'file_type': att.file_type,
                    'file_size': att.file_size,
                    'file_url': att.file_url,
                    'thumbnail_url': att.thumbnail_url,
                    'mime_type': att.mime_type,
                    'file_extension': att.file_extension
                })
            
            result_messages.append({
                'id': msg.id,
                'sender_id': msg.sender_id,
                'sender_name': msg.sender.full_name if msg.sender else '',
                'content': msg.content,
                'message_type': msg.message_type,
                'created_at': msg.created_at.isoformat(),
                'created_at_formatted': msg.created_at.strftime('%H:%M %Y-%m-%d'),
                'is_read': msg.is_read,
                'is_edited': msg.is_edited,
                'attachments': attachments,
                'reply_to': {
                    'id': msg.reply_to.id,
                    'content': msg.reply_to.content[:100],
                    'sender_name': msg.reply_to.sender.full_name if msg.reply_to.sender else ''
                } if msg.reply_to else None
            })
            # ✅ طباعة للتصحيح
        for msg in result_messages:
            if msg['attachments']:
                print(f"Message {msg['id']} has {len(msg['attachments'])} attachments")
                for att in msg['attachments']:
                    print(f"  - {att['filename']} ({att['file_type']})")
        
        return jsonify({
            'success': True,
            'messages': result_messages
        })
        
        # return jsonify({
        #     'success': True,
        #     'messages': result_messages
        # })
        
    except Exception as e:
        logger.error(f"Error in api_get_messages: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/messages', methods=['POST'])
@login_required
def send_message():
    """إرسال رسالة"""
    try:
        data = request.get_json()
        chat_id = data.get('chat_id')
        content = data.get('content', '').strip()
        message_type = data.get('message_type', 'text')
        reply_to_id = data.get('reply_to_id')
        
        if not chat_id or not content:
            return jsonify({'error': 'البيانات غير مكتملة'}), 400
        
        # التحقق من المشاركة
        participant = ChatParticipant.query.filter_by(
            chat_id=chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            return jsonify({'error': 'غير مصرح'}), 403
        
        # إنشاء الرسالة
        message = ChatMessage(
            chat_id=chat_id,
            sender_id=current_user.id,
            content=content,
            message_type=message_type,
            is_read=False
        )
        db.session.add(message)
        db.session.flush()
        
        # معالجة الإشارات (@username)
        mentioned_users = []
        import re
        mentions = re.findall(r'@([a-zA-Z0-9_]+)', content)
        
        for username in mentions:
            user = User.query.filter_by(username=username).first()
            if user and user.id != current_user.id:
                mention = Mention(
                    message_id=message.id,
                    user_id=user.id,
                    is_read=False
                )
                db.session.add(mention)
                mentioned_users.append(user)
                
                # إرسال إشعار للمستخدم المذكور
                send_mention_notification(user, current_user, message, chat_id)
        
        # تحديث وقت آخر رسالة في المحادثة
        chat = ProjectChat.query.get(chat_id)
        chat.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # إرسال إشعار للمشاركين الآخرين (غير المرسل)
        participants = ChatParticipant.query.filter_by(chat_id=chat_id).all()
        for p in participants:
            if p.user_id != current_user.id:
                send_message_notification(p.user_id, current_user, message, chat)
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'sender_id': message.sender_id,
                'sender_name': current_user.full_name,
                'content': message.content,
                'created_at': message.created_at.isoformat(),
                'created_at_formatted': message.created_at.strftime('%H:%M %Y-%m-%d'),
                'mentions': [{'user_id': u.id, 'user_name': u.full_name} for u in mentioned_users]
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in send_message: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/messages/<int:message_id>', methods=['PUT'])
@login_required
def edit_message(message_id):
    """تعديل رسالة"""
    try:
        data = request.get_json()
        content = data.get('content', '').strip()
        
        message = ChatMessage.query.get_or_404(message_id)
        
        # التحقق من أن المرسل هو المستخدم الحالي
        if message.sender_id != current_user.id:
            return jsonify({'error': 'لا يمكن تعديل رسالة الآخرين'}), 403
        
        # التحقق من أن الرسالة قديمة (أقل من 5 دقائق)
        from datetime import timedelta
        if datetime.utcnow() - message.created_at > timedelta(minutes=5):
            return jsonify({'error': 'لا يمكن تعديل رسالة أقدم من 5 دقائق'}), 400
        
        message.content = content
        message.is_edited = True
        message.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True, 'content': content})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in edit_message: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/messages/<int:message_id>', methods=['DELETE'])
@login_required
def delete_message(message_id):
    """حذف رسالة (حذف منطقي)"""
    try:
        message = ChatMessage.query.get_or_404(message_id)
        
        # التحقق من أن المرسل هو المستخدم الحالي أو مشرف
        if message.sender_id != current_user.id and current_user.role != 'org_admin':
            return jsonify({'error': 'لا يمكن حذف رسالة الآخرين'}), 403
        
        message.is_deleted = True
        message.content = "[تم حذف هذه الرسالة]"
        message.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in delete_message: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/chats')
@login_required
def get_chats():
    """جلب قائمة محادثات المستخدم"""
    try:
        chats = get_user_chats(current_user.id)
        
        return jsonify({
            'success': True,
            'chats': [{
                'id': c.id,
                'name': c.name,
                'type': c.chat_type,
                'unread_count': getattr(c, 'unread_count', 0),
                'last_message': {
                    'content': getattr(c, 'last_message', None).content if hasattr(c, 'last_message') and c.last_message else None,
                    'created_at': c.last_message.created_at.isoformat() if hasattr(c, 'last_message') and c.last_message else None,
                    'sender_name': c.last_message.sender.full_name if hasattr(c, 'last_message') and c.last_message and c.last_message.sender else None
                } if hasattr(c, 'last_message') and c.last_message else None,
                'updated_at': c.updated_at.isoformat()
            } for c in chats]
        })
        
    except Exception as e:
        logger.error(f"Error in get_chats: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/chats/<int:chat_id>/participants')
@login_required
def get_chat_participants(chat_id):
    """جلب مشاركي المحادثة"""
    try:
        participants = ChatParticipant.query.filter_by(chat_id=chat_id).all()
        
        return jsonify({
            'success': True,
            'participants': [{
                'id': p.user_id,
                'name': p.user.full_name if p.user else '',
                'role': p.role,
                'joined_at': p.joined_at.isoformat(),
                'last_seen': p.last_seen.isoformat() if p.last_seen else None,
                'is_online': p.last_seen and (datetime.utcnow() - p.last_seen).seconds < 300
            } for p in participants]
        })
        
    except Exception as e:
        logger.error(f"Error in get_chat_participants: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/chats/<int:chat_id>/typing', methods=['POST'])
@login_required
def typing_indicator(chat_id):
    """إشارة الكتابة"""
    try:
        # يمكن استخدام WebSocket لهذه الميزة
        # هنا نقوم فقط بتحديث وقت آخر نشاط
        participant = ChatParticipant.query.filter_by(
            chat_id=chat_id,
            user_id=current_user.id
        ).first()
        
        if participant:
            participant.last_seen = datetime.utcnow()
            db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500



# ============================================
# إعدادات رفع الملفات
# ============================================

ALLOWED_EXTENSIONS = {
    'image': {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'},
    'video': {'mp4', 'webm', 'avi', 'mov', 'mkv', 'flv'},
    'audio': {'mp3', 'wav', 'ogg', 'm4a'},
    'document': {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'zip', 'rar'}
}

MAX_FILE_SIZE = {
    'image': 10 * 1024 * 1024,   # 10 MB
    'video': 100 * 1024 * 1024,  # 100 MB
    'audio': 20 * 1024 * 1024,   # 20 MB
    'document': 25 * 1024 * 1024  # 25 MB
}

def allowed_file(filename, file_type):
    """التحقق من امتداد الملف المسموح"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in ALLOWED_EXTENSIONS.get(file_type, set())


def get_file_type(filename):
    """تحديد نوع الملف بناءً على الامتداد"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    for ftype, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return ftype
    return 'other'


def generate_thumbnail(file_path, thumbnail_path, file_type):
    """إنشاء صورة مصغرة للملف"""
    try:
        if file_type == 'image':
            with Image.open(file_path) as img:
                img.thumbnail((200, 200))
                img.save(thumbnail_path, 'JPEG', quality=85)
                return True
        elif file_type == 'video':
            # استخدام moviepy لإنشاء صورة مصغرة للفيديو
            video = mp.VideoFileClip(file_path)
            frame = video.get_frame(0)  # أول إطار
            # حفظ كصورة
            from PIL import Image as PILImage
            import numpy as np
            img = PILImage.fromarray(np.uint8(frame))
            img.thumbnail((200, 200))
            img.save(thumbnail_path, 'JPEG', quality=85)
            video.close()
            return True
        return False
    except Exception as e:
        logger.error(f"Error generating thumbnail: {str(e)}")
        return False


def save_attachment_file(file, message_id, sender_id):
    """حفظ الملف المرفق وإنشاء الصور المصغرة"""
    try:
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_type = get_file_type(filename)
        
        # إنشاء المجلدات
        upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'chat_attachments', str(message_id))
        os.makedirs(upload_folder, exist_ok=True)
        
        # حفظ الملف الأصلي
        file_path = os.path.join(upload_folder, unique_filename)
        file.save(file_path)
        
        # حساب حجم الملف
        file_size = os.path.getsize(file_path)
        
        # إنشاء الصورة المصغرة
        thumbnail_url = None
        thumbnail_path = os.path.join(upload_folder, f"thumb_{unique_filename}")
        if generate_thumbnail(file_path, thumbnail_path, file_type):
            thumbnail_url = url_for('static', filename=f'uploads/chat_attachments/{message_id}/thumb_{unique_filename}')
        
        # مسار الملف للعرض
        file_url = url_for('communication.download_attachment', attachment_id=0)  # سيتم تحديثه بعد الإنشاء
        
        return {
            'success': True,
            'filename': unique_filename,
            'original_filename': filename,
            'file_path': file_path,
            'file_url': file_url,
            'thumbnail_url': thumbnail_url,
            'file_size': file_size,
            'file_type': file_type,
            'mime_type': file.mimetype
        }
        
    except Exception as e:
        logger.error(f"Error saving attachment: {str(e)}")
        return {'success': False, 'error': str(e)}

def get_dashboard_url_by_role(user_role):
    """الحصول على رابط لوحة التحكم حسب دور المستخدم"""
    urls = {
        'org_admin': 'company.dashboard',
        'project_manager': 'company.dashboard',
        'supervisor': 'employee.dashboard',
        'delegate': 'employee.dashboard',
        'employee': 'employee.dashboard',
        'supplier': 'supplier.dashboard',
        'client': 'client.dashboard',
        'consultant': 'consultant.dashboard'
    }
    return urls.get(user_role, 'auth.index')
# ============================================
# راوتات رفع الملفات
# ============================================
@communication_bp.route('/api/upload-attachment', methods=['POST'])
@login_required
def upload_attachment():
    """رفع ملف مرفق (صورة، فيديو، مستند)"""
    try:
        chat_id = request.form.get('chat_id', type=int)
        if not chat_id:
            return jsonify({'error': 'chat_id مطلوب'}), 400
        
        if 'file' not in request.files:
            return jsonify({'error': 'لا توجد ملفات مرفوعة'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'لم يتم اختيار ملف'}), 400
        
        # التحقق من نوع الملف
        file_type = get_file_type(file.filename)
        if file_type == 'other':
            return jsonify({'error': 'نوع الملف غير مدعوم'}), 400
        
        # التحقق من حجم الملف
        max_size = MAX_FILE_SIZE.get(file_type, 25 * 1024 * 1024)
        file.seek(0, 2)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > max_size:
            return jsonify({'error': f'حجم الملف يتجاوز الحد المسموح ({max_size // (1024*1024)} MB)'}), 400
        
        # التحقق من صلاحية المستخدم في المحادثة
        participant = ChatParticipant.query.filter_by(
            chat_id=chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            return jsonify({'error': 'غير مصرح'}), 403
        
        # إنشاء رسالة جديدة للملف
        message = ChatMessage(
            chat_id=chat_id,
            sender_id=current_user.id,
            content=f"📎 {file.filename}",
            message_type=file_type,
            is_read=False
        )
        db.session.add(message)
        db.session.flush()
        
        # حفظ الملف المرفق
        result = save_attachment_file(file, message.id, current_user.id)
        
        if not result['success']:
            db.session.rollback()
            return jsonify({'error': result['error']}), 500
        
        # إنشاء سجل المرفق
        attachment = Attachment(
            message_id=message.id,
            sender_id=current_user.id,
            filename=result['filename'],
            original_filename=result['original_filename'],
            file_size=result['file_size'],
            file_type=result['file_type'],
            mime_type=result['mime_type'],
            file_extension=result['original_filename'].rsplit('.', 1)[1].lower() if '.' in result['original_filename'] else '',
            file_path=result['file_path'],
            thumbnail_url=result['thumbnail_url'],
            processing_status='completed'
        )
        db.session.add(attachment)
        db.session.commit()
        
        # تحديث رابط الملف في قاعدة البيانات
        attachment.file_url = url_for('communication.download_attachment', attachment_id=attachment.id, _external=True)
        db.session.commit()
        
        # تحديث وقت المحادثة
        chat = ProjectChat.query.get(chat_id)
        chat.updated_at = datetime.utcnow()
        db.session.commit()
        
        # إرسال إشعار للمشاركين
        notify_chat_participants_about_attachment(chat_id, current_user, message, attachment)
        
        return jsonify({
            'success': True,
            'message': {
                'id': message.id,
                'sender_id': message.sender_id,
                'sender_name': current_user.full_name,
                'content': message.content,
                'message_type': message.message_type,
                'created_at': message.created_at.isoformat(),
                'attachment': {
                    'id': attachment.id,
                    'filename': attachment.original_filename,
                    'file_type': attachment.file_type,
                    'file_size': attachment.file_size,
                    'file_url': attachment.file_url,
                    'thumbnail_url': attachment.thumbnail_url
                }
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in upload_attachment: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/upload-multiple', methods=['POST'])
@login_required
def upload_multiple_attachments():
    """رفع ملفات متعددة"""
    try:
        chat_id = request.form.get('chat_id', type=int)
        if not chat_id:
            return jsonify({'error': 'chat_id مطلوب'}), 400
        
        files = request.files.getlist('files[]')
        if not files:
            return jsonify({'error': 'لا توجد ملفات مرفوعة'}), 400
        
        # التحقق من الصلاحية
        participant = ChatParticipant.query.filter_by(
            chat_id=chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            return jsonify({'error': 'غير مصرح'}), 403
        
        uploaded = []
        failed = []
        
        for file in files:
            if file.filename:
                try:
                    file_type = get_file_type(file.filename)
                    if file_type == 'other':
                        failed.append({'filename': file.filename, 'error': 'نوع الملف غير مدعوم'})
                        continue
                    
                    # إنشاء رسالة
                    message = ChatMessage(
                        chat_id=chat_id,
                        sender_id=current_user.id,
                        content=f"📎 {file.filename}",
                        message_type=file_type,
                        is_read=False
                    )
                    db.session.add(message)
                    db.session.flush()
                    
                    # حفظ الملف
                    result = save_attachment_file(file, message.id, current_user.id)
                    
                    if result['success']:
                        attachment = Attachment(
                            message_id=message.id,
                            sender_id=current_user.id,
                            filename=result['filename'],
                            original_filename=result['original_filename'],
                            file_size=result['file_size'],
                            file_type=result['file_type'],
                            mime_type=result['mime_type'],
                            file_extension=result['original_filename'].rsplit('.', 1)[1].lower() if '.' in result['original_filename'] else '',
                            file_path=result['file_path'],
                            thumbnail_url=result['thumbnail_url']
                        )
                        db.session.add(attachment)
                        db.session.flush()
                        
                        attachment.file_url = url_for('communication.download_attachment', attachment_id=attachment.id, _external=True)
                        
                        uploaded.append({
                            'id': message.id,
                            'filename': attachment.original_filename,
                            'file_type': attachment.file_type,
                            'file_url': attachment.file_url,
                            'thumbnail_url': attachment.thumbnail_url
                        })
                    else:
                        failed.append({'filename': file.filename, 'error': result.get('error', 'خطأ غير معروف')})
                        
                except Exception as e:
                    failed.append({'filename': file.filename, 'error': str(e)})
        
        db.session.commit()
        
        # تحديث وقت المحادثة
        chat = ProjectChat.query.get(chat_id)
        chat.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({
            'success': True,
            'uploaded': uploaded,
            'failed': failed,
            'count': len(uploaded)
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in upload_multiple_attachments: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/attachments/<int:attachment_id>')
@login_required
def download_attachment(attachment_id):
    """تحميل الملف المرفق"""
    try:
        attachment = Attachment.query.get_or_404(attachment_id)
        message = ChatMessage.query.get(attachment.message_id)
        
        # التحقق من صلاحية المستخدم
        participant = ChatParticipant.query.filter_by(
            chat_id=message.chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            abort(403)
        
        # تحديد نوع العرض حسب نوع الملف
        if attachment.file_type == 'image':
            return send_file(
                attachment.file_path,
                mimetype=attachment.mime_type,
                as_attachment=False
            )
        else:
            return send_file(
                attachment.file_path,
                mimetype=attachment.mime_type,
                as_attachment=True,
                download_name=attachment.original_filename
            )
            
    except Exception as e:
        logger.error(f"Error in download_attachment: {str(e)}")
        abort(500)


@communication_bp.route('/attachments/<int:attachment_id>/preview')
@login_required
def preview_attachment(attachment_id):
    """عرض معاينة الملف حسب نوعه"""
    try:
        attachment = Attachment.query.get_or_404(attachment_id)
        message = ChatMessage.query.get(attachment.message_id)
        
        # التحقق من الصلاحية
        participant = ChatParticipant.query.filter_by(
            chat_id=message.chat_id,
            user_id=current_user.id
        ).first()
        
        if not participant:
            abort(403)
        
        # توجيه إلى القالب المناسب حسب نوع الملف
        if attachment.file_type == 'image':
            return render_template('communication/image_preview.html', attachment=attachment)
        elif attachment.file_type == 'video':
            return render_template('communication/video_preview.html', attachment=attachment)
        elif attachment.file_type == 'audio':
            return render_template('communication/audio_preview.html', attachment=attachment)
        elif attachment.file_type == 'document':
            return render_template('communication/document_preview.html', attachment=attachment)
        else:
            return send_file(attachment.file_path, as_attachment=True)
            
    except Exception as e:
        logger.error(f"Error in preview_attachment: {str(e)}")
        abort(500)


@communication_bp.route('/api/attachments/<int:attachment_id>/delete', methods=['DELETE'])
@login_required
def delete_attachment(attachment_id):
    """حذف الملف المرفق"""
    try:
        attachment = Attachment.query.get_or_404(attachment_id)
        message = ChatMessage.query.get(attachment.message_id)
        
        # التحقق من الصلاحية (المرسل فقط أو المشرف)
        if message.sender_id != current_user.id and current_user.role != 'org_admin':
            return jsonify({'error': 'غير مصرح'}), 403
        
        # حذف الملف الفعلي
        if os.path.exists(attachment.file_path):
            os.remove(attachment.file_path)
        
        # حذف الصورة المصغرة إن وجدت
        if attachment.thumbnail_url:
            thumb_path = attachment.thumbnail_url.replace(url_for('static', filename=''), '')
            thumb_full_path = os.path.join(current_app.root_path, 'static', thumb_path)
            if os.path.exists(thumb_full_path):
                os.remove(thumb_full_path)
        
        # تحديث محتوى الرسالة
        message.content = f"[تم حذف الملف: {attachment.original_filename}]"
        message.message_type = 'text'
        
        db.session.delete(attachment)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in delete_attachment: {str(e)}")
        return jsonify({'error': str(e)}), 500
# ============================================
# دوال الإشعارات
# ============================================

def send_message_notification(user_id, sender, message, chat):
    """إرسال إشعار برسالة جديدة"""
    try:
        notification = Notification(
            user_id=user_id,
            title=f"رسالة جديدة من {sender.full_name}",
            title_ar=f"رسالة جديدة من {sender.full_name}",
            message=message.content[:100],
            message_ar=message.content[:100],
            notification_type='chat_message',
            priority='medium',
            related_link=url_for('communication.chat_room', chat_id=chat.id, _external=True),
            related_project_id=chat.project_id,
            related_task_id=chat.task_id,
            send_email=True,
            send_push=True,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error in send_message_notification: {str(e)}")


def send_mention_notification(mentioned_user, sender, message, chat_id):
    """إرسال إشعار بالإشارة"""
    try:
        notification = Notification(
            user_id=mentioned_user.id,
            title=f"{{ sender.full_name }} أشار إليك في محادثة",
            title_ar=f"{{ sender.full_name }} أشار إليك في محادثة",
            message=message.content[:100],
            message_ar=message.content[:100],
            notification_type='chat_mention',
            priority='high',
            related_link=url_for('communication.chat_room', chat_id=chat_id, _external=True),
            send_email=True,
            send_push=True,
            created_at=datetime.utcnow()
        )
        db.session.add(notification)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error in send_mention_notification: {str(e)}")

# أضف هذه الدوال في communication_routes.py

def send_chat_invite_notification(user_id, inviter, chat):
    """إرسال إشعار دعوة للمحادثة"""
    try:
        notification = Notification(
            user_id=user_id,
            title=f"دعوة للانضمام إلى محادثة {chat.name}",
            title_ar=f"دعوة للانضمام إلى محادثة {chat.name}",
            message=f"دعاك {inviter.full_name} للانضمام إلى محادثة {chat.name}",
            message_ar=f"دعاك {inviter.full_name} للانضمام إلى محادثة {chat.name}",
            notification_type='chat_invite',
            priority='medium',
            related_link=url_for('communication.chat_room', chat_id=chat.id, _external=True),
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
    except Exception as e:
        logger.error(f"Error in send_chat_invite_notification: {str(e)}")


def notify_chat_participants(chat_id, user_id, action):
    """إشعار المشاركين الآخرين في المحادثة"""
    try:
        participants = ChatParticipant.query.filter(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id != user_id
        ).all()
        
        user = User.query.get(user_id)
        action_text = "غادر" if action == 'left' else "انضم"
        
        for p in participants:
            notification = Notification(
                user_id=p.user_id,
                title=f"تحديث في المحادثة",
                title_ar=f"تحديث في المحادثة",
                message=f"{user.full_name} {action_text} المحادثة",
                message_ar=f"{user.full_name} {action_text} المحادثة",
                notification_type='chat_update',
                priority='low',
                related_link=url_for('communication.chat_room', chat_id=chat_id, _external=True),
                send_email=False,
                send_push=True
            )
            db.session.add(notification)
        
        db.session.commit()
    except Exception as e:
        logger.error(f"Error in notify_chat_participants: {str(e)}")

def notify_chat_participants_about_attachment(chat_id, sender, message, attachment):
    """إشعار المشاركين بوجود ملف مرفق"""
    try:
        participants = ChatParticipant.query.filter(
            ChatParticipant.chat_id == chat_id,
            ChatParticipant.user_id != sender.id
        ).all()
        
        for p in participants:
            notification = Notification(
                user_id=p.user_id,
                title=f"ملف جديد في المحادثة",
                title_ar=f"ملف جديد في المحادثة",
                message=f"{sender.full_name} أرسل ملف: {attachment.original_filename}",
                message_ar=f"{sender.full_name} أرسل ملف: {attachment.original_filename}",
                notification_type='chat_attachment',
                priority='medium',
                related_link=url_for('communication.chat_room', chat_id=chat_id, _external=True),
                send_email=False,
                send_push=True
            )
            db.session.add(notification)
        
        db.session.commit()
    except Exception as e:
        logger.error(f"Error in notify_chat_participants_about_attachment: {str(e)}")
# ============================================
# روابط الدردشة الخاصة بالأنشطة (Activities)
# ============================================

@communication_bp.route('/activity/<int:activity_id>/chat')
@login_required
def get_activity_chat(activity_id):
    """الحصول على محادثة مرتبطة بنشاط معين أو إنشاؤها"""
    try:
        from app.models.primavera_models import Activity
        
        activity = Activity.query.get_or_404(activity_id)
        
        # التحقق من صلاحية الوصول للنشاط
        if not _can_access_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح بالوصول إلى هذا النشاط'}), 403
        
        # البحث عن محادثة مرتبطة بهذا النشاط
        chat = ProjectChat.query.filter_by(
            activity_id=activity_id,
            chat_type='activity',
            is_archived=False
        ).first()
        
        if chat:
            return jsonify({
                'success': True,
                'chat_id': chat.id,
                'chat_name': chat.name,
                'exists': True
            })
        else:
            return jsonify({
                'success': True,
                'exists': False,
                'activity_id': activity_id,
                'activity_name': activity.activity_name
            })
            
    except Exception as e:
        logger.error(f"Error in get_activity_chat: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/activity/<int:activity_id>/create-chat', methods=['POST'])
@login_required
def create_activity_chat(activity_id):
    """إنشاء محادثة جديدة مرتبطة بنشاط"""
    try:
        from app.models.primavera_models import Activity
        from app.models.task_models import Task, TaskAssignment
        
        activity = Activity.query.get_or_404(activity_id)
        
        # التحقق من صلاحية الوصول للنشاط
        if not _can_access_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح بالوصول إلى هذا النشاط'}), 403
        
        data = request.get_json()
        chat_name = data.get('name', '').strip()
        
        if not chat_name:
            chat_name = f"مناقشة النشاط: {activity.activity_name}"
        
        # جلب المشاركين المحتملين في النشاط
        participants_ids = set()
        
        # 1. المشرف على النشاط
        if activity.supervisor_id:
            participants_ids.add(activity.supervisor_id)
        
        # 2. المندوب المسؤول عن النشاط
        if activity.delegate_id:
            participants_ids.add(activity.delegate_id)
        
        # 3. المستخدم المسؤول (responsible)
        if activity.responsible_id:
            participants_ids.add(activity.responsible_id)
        
        # 4. المهام المرتبطة بالنشاط وجلب المشاركين فيها
        tasks = Task.query.filter_by(activity_id=activity_id).all()
        for task in tasks:
            if task.supervisor_id:
                participants_ids.add(task.supervisor_id)
            if task.delegate_id:
                participants_ids.add(task.delegate_id)
            
            # تعيينات المهام
            assignments = TaskAssignment.query.filter_by(task_id=task.id).all()
            for assignment in assignments:
                participants_ids.add(assignment.user_id)
        
        # 5. مدير المشروع
        if activity.project and activity.project.project_manager_id:
            participants_ids.add(activity.project.project_manager_id)
        
        # 6. إضافة المستخدم الحالي إذا لم يكن موجوداً
        participants_ids.add(current_user.id)
        
        # إنشاء المحادثة
        chat = ProjectChat(
            activity_id=activity_id,
            chat_type='activity',
            name=chat_name,
            description=f"محادثة فريق عمل النشاط: {activity.activity_name}",
            is_active=True,
            created_by=current_user.id
        )
        db.session.add(chat)
        db.session.flush()
        
        # إضافة المشاركين
        for user_id in participants_ids:
            user = User.query.get(user_id)
            if user and user.is_user_active:
                participant = ChatParticipant(
                    chat_id=chat.id,
                    user_id=user_id,
                    role='admin' if user_id == current_user.id else 'member',
                    joined_at=datetime.utcnow()
                )
                db.session.add(participant)
        
        # إنشاء رسالة ترحيبية في المحادثة
        welcome_message = ChatMessage(
            chat_id=chat.id,
            sender_id=current_user.id,
            content=f"تم إنشاء هذه المحادثة لمناقشة النشاط: {activity.activity_name}\n\nيمكنك هنا مناقشة تفاصيل النشاط، مشاركة الملفات، والتنسيق مع الفريق.",
            message_type='text',
            is_read=False
        )
        db.session.add(welcome_message)
        
        db.session.commit()
        
        # إرسال إشعارات للمشاركين
        for user_id in participants_ids:
            if user_id != current_user.id:
                _send_activity_chat_invite_notification(
                    user_id=user_id,
                    inviter=current_user,
                    activity=activity,
                    chat=chat
                )
        
        return jsonify({
            'success': True,
            'chat_id': chat.id,
            'chat_name': chat.name,
            'participants_count': len(participants_ids),
            'message': 'تم إنشاء محادثة النشاط بنجاح'
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in create_activity_chat: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/activity/<int:activity_id>/chat/participants')
@login_required
def get_activity_chat_participants(activity_id):
    """جلب المشاركين المحتملين في محادثة النشاط"""
    try:
        from app.models.primavera_models import Activity
        from app.models.task_models import Task, TaskAssignment
        
        activity = Activity.query.get_or_404(activity_id)
        
        # التحقق من صلاحية الوصول
        if not _can_access_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        participants = []
        
        # جلب جميع المستخدمين المرتبطين بالنشاط
        user_ids = set()
        
        if activity.supervisor_id:
            user_ids.add(activity.supervisor_id)
        if activity.delegate_id:
            user_ids.add(activity.delegate_id)
        if activity.responsible_id:
            user_ids.add(activity.responsible_id)
        
        tasks = Task.query.filter_by(activity_id=activity_id).all()
        for task in tasks:
            if task.supervisor_id:
                user_ids.add(task.supervisor_id)
            if task.delegate_id:
                user_ids.add(task.delegate_id)
            
            assignments = TaskAssignment.query.filter_by(task_id=task.id).all()
            for assignment in assignments:
                user_ids.add(assignment.user_id)
        
        if activity.project and activity.project.project_manager_id:
            user_ids.add(activity.project.project_manager_id)
        
        user_ids.add(current_user.id)
        
        # جلب معلومات المستخدمين
        for user_id in user_ids:
            user = User.query.get(user_id)
            if user and user.is_user_active:
                participants.append({
                    'id': user.id,
                    'name': user.full_name,
                    'email': user.email,
                    'role': user.role,
                    'avatar': user.profile_image
                })
        
        return jsonify({
            'success': True,
            'participants': participants,
            'count': len(participants)
        })
        
    except Exception as e:
        logger.error(f"Error in get_activity_chat_participants: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/activity/<int:activity_id>/chat/invite', methods=['POST'])
@login_required
def invite_to_activity_chat(activity_id):
    """دعوة مستخدمين إلى محادثة النشاط"""
    try:
        from app.models.primavera_models import Activity
        
        activity = Activity.query.get_or_404(activity_id)
        
        # البحث عن محادثة النشاط
        chat = ProjectChat.query.filter_by(
            activity_id=activity_id,
            chat_type='activity',
            is_archived=False
        ).first()
        
        if not chat:
            return jsonify({'error': 'لا توجد محادثة مرتبطة بهذا النشاط'}), 404
        
        # التحقق من صلاحية المستخدم (يجب أن يكون منشئ المحادثة أو مديراً)
        if chat.created_by != current_user.id and current_user.role not in ['org_admin', 'project_manager']:
            return jsonify({'error': 'غير مصرح'}), 403
        
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        
        added_users = []
        for user_id in user_ids:
            existing = ChatParticipant.query.filter_by(
                chat_id=chat.id,
                user_id=user_id
            ).first()
            
            if not existing:
                participant = ChatParticipant(
                    chat_id=chat.id,
                    user_id=user_id,
                    role='member',
                    joined_at=datetime.utcnow()
                )
                db.session.add(participant)
                added_users.append(user_id)
                
                # إرسال إشعار دعوة
                _send_activity_chat_invite_notification(
                    user_id=user_id,
                    inviter=current_user,
                    activity=activity,
                    chat=chat
                )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'added_count': len(added_users),
            'added_users': added_users
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error in invite_to_activity_chat: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/activity/<int:activity_id>/chat/info')
@login_required
def get_activity_chat_info(activity_id):
    """الحصول على معلومات محادثة النشاط"""
    try:
        from app.models.primavera_models import Activity
        
        activity = Activity.query.get_or_404(activity_id)
        
        chat = ProjectChat.query.filter_by(
            activity_id=activity_id,
            chat_type='activity',
            is_archived=False
        ).first()
        
        if not chat:
            return jsonify({'exists': False})
        
        # جلب إحصائيات المحادثة
        participants_count = ChatParticipant.query.filter_by(chat_id=chat.id).count()
        messages_count = ChatMessage.query.filter_by(
            chat_id=chat.id,
            is_deleted=False
        ).count()
        unread_count = ChatMessage.query.filter(
            ChatMessage.chat_id == chat.id,
            ChatMessage.sender_id != current_user.id,
            ChatMessage.is_read == False,
            ChatMessage.is_deleted == False
        ).count()
        
        return jsonify({
            'exists': True,
            'chat': {
                'id': chat.id,
                'name': chat.name,
                'description': chat.description,
                'created_at': chat.created_at.isoformat(),
                'updated_at': chat.updated_at.isoformat(),
                'participants_count': participants_count,
                'messages_count': messages_count,
                'unread_count': unread_count
            }
        })
        
    except Exception as e:
        logger.error(f"Error in get_activity_chat_info: {str(e)}")
        return jsonify({'error': str(e)}), 500


@communication_bp.route('/api/activities/<int:activity_id>/chat-status')
@login_required
def api_activity_chat_status(activity_id):
    """API للتحقق من وجود محادثة للنشاط (للاستخدام مع AJAX)"""
    try:
        from app.models.primavera_models import Activity
        
        activity = Activity.query.get_or_404(activity_id)
        
        if not _can_access_activity(activity, current_user):
            return jsonify({'error': 'غير مصرح'}), 403
        
        chat = ProjectChat.query.filter_by(
            activity_id=activity_id,
            chat_type='activity',
            is_archived=False
        ).first()
        
        if chat:
            # جلب آخر رسالة
            last_message = ChatMessage.query.filter_by(
                chat_id=chat.id,
                is_deleted=False
            ).order_by(ChatMessage.created_at.desc()).first()
            
            # عدد الرسائل غير المقروءة
            unread_count = ChatMessage.query.filter(
                ChatMessage.chat_id == chat.id,
                ChatMessage.sender_id != current_user.id,
                ChatMessage.is_read == False,
                ChatMessage.is_deleted == False
            ).count()
            
            return jsonify({
                'has_chat': True,
                'chat_id': chat.id,
                'chat_name': chat.name,
                'unread_count': unread_count,
                'last_message': {
                    'content': last_message.content[:100] if last_message else None,
                    'created_at': last_message.created_at.isoformat() if last_message else None,
                    'sender_name': last_message.sender.full_name if last_message and last_message.sender else None
                } if last_message else None
            })
        else:
            return jsonify({'has_chat': False})
            
    except Exception as e:
        logger.error(f"Error in api_activity_chat_status: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================
# دوال مساعدة للأنشطة
# ============================================

def _can_access_activity(activity, user):
    """التحقق من صلاحية الوصول للنشاط"""
    try:
        # مدير المنصة أو مدير الشركة يمكنهم الوصول
        if user.role in ['org_admin', 'platform_admin']:
            return True
        
        # المشرف على النشاط
        if activity.supervisor_id == user.id:
            return True
        
        # المندوب المسؤول
        if activity.delegate_id == user.id:
            return True
        
        # المستخدم المسؤول
        if activity.responsible_id == user.id:
            return True
        
        # مدير المشروع
        if activity.project and activity.project.project_manager_id == user.id:
            return True
        
        # الموظف الذي لديه مهام في هذا النشاط
        from app.models.task_models import Task, TaskAssignment
        tasks = Task.query.filter_by(activity_id=activity.id).all()
        for task in tasks:
            if task.supervisor_id == user.id or task.delegate_id == user.id:
                return True
            
            assignment = TaskAssignment.query.filter_by(
                task_id=task.id,
                user_id=user.id
            ).first()
            if assignment:
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in _can_access_activity: {str(e)}")
        return False


def _send_activity_chat_invite_notification(user_id, inviter, activity, chat):
    """إرسال إشعار دعوة لمحادثة النشاط"""
    try:
        from app.models.core_models import Notification
        
        notification = Notification(
            user_id=user_id,
            title=f"دعوة للانضمام إلى محادثة النشاط: {activity.activity_name}",
            title_ar=f"دعوة للانضمام إلى محادثة النشاط: {activity.activity_name}",
            message=f"دعاك {inviter.full_name} للانضمام إلى محادثة النشاط {activity.activity_name}",
            message_ar=f"دعاك {inviter.full_name} للانضمام إلى محادثة النشاط {activity.activity_name}",
            notification_type='chat_invite',
            priority='medium',
            related_link=url_for('communication.chat_room', chat_id=chat.id, _external=True),
            related_activity_id=activity.id,
            related_project_id=activity.project_id,
            send_email=True,
            send_push=True
        )
        db.session.add(notification)
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error in _send_activity_chat_invite_notification: {str(e)}")
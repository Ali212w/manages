# في ملف app/services/audit_service.py

from app.models.ai_models import AuditLog
from flask import current_app, request
from datetime import datetime
import json
from typing import Optional, Dict, Any, List
import threading
from queue import Queue

# قائمة انتظار للتسجيل غير المتزامن
_log_queue = Queue()
_worker_thread = None

class AuditService:
    """خدمة مركزية للتسجيل - تدعم التسجيل غير المتزامن"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._start_worker()
        return cls._instance
    
    def _start_worker(self):
        """بدء عامل خلفية للتسجيل غير المتزامن"""
        def worker():
            while True:
                try:
                    logs = []
                    # جمع حتى 100 سجل أو الانتظار 5 ثوان
                    for _ in range(100):
                        try:
                            log = _log_queue.get(timeout=5)
                            logs.append(log)
                        except:
                            break
                    
                    if logs:
                        self._save_batch(logs)
                except Exception as e:
                    current_app.logger.error(f"Audit worker error: {str(e)}")
        
        global _worker_thread
        if not _worker_thread or not _worker_thread.is_alive():
            _worker_thread = threading.Thread(target=worker, daemon=True)
            _worker_thread.start()
    
    def _save_batch(self, logs):
        """حفظ مجموعة من السجلات"""
        try:
            from app import db
            
            audit_logs = []
            for log_data in logs:
                log = AuditLog(**log_data)
                audit_logs.append(log)
            
            db.session.add_all(audit_logs)
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Batch save error: {str(e)}")
            db.session.rollback()
    
    @classmethod
    def log(cls, user_id, action, category=None, entity_type=None, 
            entity_id=None, entity_code=None, old_values=None, 
            new_values=None, details=None, sync=False):
        """
        تسجيل إجراء
        
        Args:
            sync: إذا كان True يتم الحفظ مباشرة (للسجلات المهمة)
        """
        # تجهيز بيانات السجل
        log_data = {
            'user_id': user_id,
            'username': cls._get_username(user_id),
            'action': action,
            'category': category or cls._get_category(action),
            'entity_type': entity_type,
            'entity_id': entity_id,
            'entity_code': entity_code,
            'old_values': old_values,
            'new_values': new_values,
            'details': details,
            'ip_address': request.remote_addr if request else None,
            'user_agent': request.user_agent.string[:500] if request and request.user_agent else None,
            'request_method': request.method if request else None,
            'request_url': request.url[:500] if request else None,
            'created_at': datetime.utcnow()
        }
        
        if sync:
            # حفظ مباشر للسجلات المهمة
            cls._save_sync(log_data)
        else:
            # إضافة إلى قائمة الانتظار (غير متزامن)
            _log_queue.put(log_data)
    
    @staticmethod
    def _save_sync(log_data):
        """حفظ مباشر"""
        try:
            from app import db
            log = AuditLog(**log_data)
            db.session.add(log)
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Sync audit error: {str(e)}")
            db.session.rollback()
    
    @staticmethod
    def _get_username(user_id):
        """الحصول على اسم المستخدم (مع caching)"""
        from app.models import User
        from flask_caching import Cache
        
        cache = Cache()
        cache_key = f'username_{user_id}'
        username = cache.get(cache_key)
        
        if not username:
            user = User.query.get(user_id)
            username = user.full_name if user else None
            cache.set(cache_key, username, timeout=3600)  # cache لمدة ساعة
        
        return username
    
    @staticmethod
    def _get_category(action):
        """تحديد الفئة من الإجراء"""
        categories = {
            'create': ['create', 'add', 'new', 'إنشاء', 'إضافة'],
            'update': ['update', 'edit', 'modify', 'تعديل', 'تحديث'],
            'delete': ['delete', 'remove', 'حذف', 'إزالة'],
            'view': ['view', 'read', 'show', 'عرض', 'مشاهدة'],
        }
        
        action_lower = action.lower()
        for category, keywords in categories.items():
            if any(keyword in action_lower for keyword in keywords):
                return category
        return 'other'

# instance واحدة للتطبيق
audit_service = AuditService()
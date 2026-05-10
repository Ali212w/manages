# app/services/file_upload_service.py

import os
import uuid
from PIL import Image
from werkzeug.utils import secure_filename
from flask import current_app, url_for
import logging

logger = logging.getLogger(__name__)


class FileUploadService:
    """خدمة رفع ومعالجة الملفات"""
    
    ALLOWED_EXTENSIONS = {
        'image': ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'],
        'video': ['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'],
        'document': ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt']
    }
    
    MAX_FILE_SIZE = {
        'image': 10 * 1024 * 1024,
        'video': 100 * 1024 * 1024,
        'document': 20 * 1024 * 1024
    }
    
    @staticmethod
    def get_file_type(filename):
        """تحديد نوع الملف"""
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        for file_type, extensions in FileUploadService.ALLOWED_EXTENSIONS.items():
            if ext in extensions:
                return file_type, ext
        return None, None
    
    @staticmethod
    def is_allowed_file(filename, file_size):
        """التحقق من صحة الملف"""
        file_type, ext = FileUploadService.get_file_type(filename)
        if not file_type:
            return False, "نوع الملف غير مدعوم"
        max_size = FileUploadService.MAX_FILE_SIZE.get(file_type, 0)
        if file_size > max_size:
            return False, f"حجم الملف يتجاوز الحد المسموح ({max_size // (1024*1024)}MB)"
        return True, None
    
    @staticmethod
    def generate_thumbnail(file_path, file_type, output_path):
        """إنشاء صورة مصغرة"""
        try:
            if file_type == 'image':
                with Image.open(file_path) as img:
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        img = background
                    img.thumbnail((300, 300), Image.Resampling.LANCZOS)
                    img.save(output_path, 'JPEG', quality=85)
                    return True
            elif file_type == 'video':
                # يمكن استخدام ffmpeg لإنشاء صورة مصغرة
                pass
            return True
        except Exception as e:
            logger.error(f"خطأ في إنشاء الصورة المصغرة: {str(e)}")
            return False
    
    @staticmethod
    def save_file(file, upload_folder, generate_thumb=True):
        """حفظ الملف وإنشاء صورة مصغرة"""
        try:
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            file_type, ext = FileUploadService.get_file_type(filename)
            
            upload_path = os.path.join(current_app.root_path, 'static', upload_folder)
            os.makedirs(upload_path, exist_ok=True)
            
            file_path = os.path.join(upload_path, unique_filename)
            file.save(file_path)
            file_size = os.path.getsize(file_path)
            file_url = url_for('static', filename=f'{upload_folder}/{unique_filename}')
            
            thumbnail_url = None
            if generate_thumb and file_type in ['image', 'video']:
                thumb_filename = f"thumb_{unique_filename}"
                thumb_path = os.path.join(upload_path, thumb_filename)
                if FileUploadService.generate_thumbnail(file_path, file_type, thumb_path):
                    thumbnail_url = url_for('static', filename=f'{upload_folder}/{thumb_filename}')
            
            return {
                'success': True,
                'filename': unique_filename,
                'original_filename': filename,
                'file_path': file_path,
                'file_url': file_url,
                'thumbnail_url': thumbnail_url,
                'file_size': file_size,
                'file_type': file_type,
                'file_extension': ext
            }
        except Exception as e:
            logger.error(f"خطأ في حفظ الملف: {str(e)}")
            return {'success': False, 'error': str(e)}
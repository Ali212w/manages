"""
run.py - تشغيل التطبيق مع تحسينات الأداء والإيقاف السلس
"""

import os
import sys
import signal
import atexit
import time

from app import app, socketio
from app.extensions import login_manager


@login_manager.user_loader
def load_user(user_key):
    """تحميل المستخدم مع معرفة نوعه"""
    from app.models.core_models import User, Organization, PlatformAdmin
    from flask import session
    
    print(f"🔍 [load_user] محاولة تحميل مستخدم بالمفتاح: '{user_key}'")
    print(f"🍪 [load_user] الجلسة الحالية: {dict(session)}")
    
    if not user_key:
        print("⚠️ [load_user] مفتاح فارغ")
        return None
    
    # إذا كان المفتاح رقمي، نحاول تحويله إلى الصيغة الموحدة
    if user_key.isdigit():
        print(f"⚠️ [load_user] مفتاح رقمي: {user_key} - محاولة تحويله")
        try:
            user = User.query.get(int(user_key))
            if user:
                print(f"✅ [load_user] تم تحميل مستخدم من مفتاح رقمي: {user.email}")
                return user
        except:
            pass
        return None
    
    try:
        if '-' not in user_key:
            print(f"⚠️ [load_user] مفتاح بدون شرطة: {user_key}")
            return None
        
        user_type, user_id_str = user_key.split("-", 1)
        user_id = int(user_id_str)
        
        print(f"📌 [load_user] النوع: '{user_type}', ID: '{user_id}'")
        
        if user_type == "user":
            user = User.query.get(user_id)
            if user:
                print(f"✅ [load_user] تم تحميل مستخدم: {user.email}")
            else:
                print(f"❌ [load_user] مستخدم غير موجود: {user_id}")
            return user
            
        elif user_type in ["organ", "org", "organization"]:
            org = Organization.query.get(user_id)
            if org:
                print(f"✅ [load_user] تم تحميل مؤسسة: {org.name}")
            else:
                print(f"❌ [load_user] مؤسسة غير موجودة: {user_id}")
            return org
            
        elif user_type == "platform":
            admin = PlatformAdmin.query.get(user_id)
            if admin:
                print(f"✅ [load_user] تم تحميل مدير منصة: {admin.email}")
            else:
                print(f"❌ [load_user] مدير منصة غير موجود: {user_id}")
            return admin
            
        else:
            print(f"❌ [load_user] نوع غير معروف: {user_type}")
            return None
            
    except Exception as e:
        print(f"❌ [load_user] استثناء: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


# ============================================
# إيقاف آمن وسريع
# ============================================

def fast_shutdown():
    """إيقاف سريع للتطبيق وجميع العمليات الخلفية"""
    print("\n🛑 جاري إيقاف التطبيق...")
    
    # 1. إيقاف SocketIO
    try:
        socketio.stop()
        print("   ✓ تم إيقاف SocketIO")
    except:
        pass
    
    # 2. إيقاف المجدول (بدون انتظار)
    try:
        from app.scheduler import get_scheduler, shutdown_scheduler
        shutdown_scheduler()
        print("   ✓ تم إيقاف المجدول")
    except:
        pass
    
    # 3. إغلاق اتصالات قاعدة البيانات
    try:
        from app.models import db
        db.session.close_all()
        if hasattr(db, 'engine') and db.engine:
            db.engine.dispose()
        print("   ✓ تم إغلاق قاعدة البيانات")
    except:
        pass
    
    print("✅ تم إيقاف التطبيق بنجاح")
    sys.exit(0)


def signal_handler(signum, frame):
    """معالج سريع لإشارات النظام"""
    print(f"\n⚠️ استلام إشارة {signum}")
    fast_shutdown()


# تسجيل معالجات الإشارات
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # إشارة الإنهاء
atexit.register(fast_shutdown)


# ============================================
# التشغيل الرئيسي
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    
    print("=" * 50)
    print("🚀 تشغيل سريع (بدون WebSocket)")
    print(f"🌐 http://localhost:{port}")
    print("🔄 إعادة تحميل تلقائي: نعم")
    print("💡 حفظ الملف = تحديث فوري")
    print("💡 Ctrl+C = إيقاف فوري")
    print("=" * 50)
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=True
    )
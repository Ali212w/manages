# check_columns.py

# from app import create_app
# from app.models import Activity, db,PlatformOwner,PlatformAdmin
# from sqlalchemy import inspect
# import logging
# logger = logging.getLogger(__name__)
# app = create_app()

# with app.app_context():
    # print("=" * 50)
    # print("فحص أعمدة نموذج Activity")
    # print("=" * 50)
    
    # # طريقة 1: استخدام __table__
    # print("\n📋 الطريقة 1: __table__.columns")
    # print("-" * 40)
    # for column in Activity.__table__.columns:
    #     print(f"  • {column.name:<20} -> {column.type}")
    
    # # طريقة 2: استخدام inspect
    # print("\n📋 الطريقة 2: SQLAlchemy inspect")
    # print("-" * 40)
    # inspector = inspect(Activity)
    # for column in inspector.columns:
    #     print(f"  • {column.name:<20} -> {column.type}")
    
    # # طريقة 3: الحصول على أسماء فقط
    # print("\n📋 الطريقة 3: أسماء الأعمدة فقط")
    # print("-" * 40)
    # column_names = [column.name for column in Activity.__table__.columns]
    # print(f"  {column_names}")
    
    # # طريقة 4: أعمدة Boolean فقط
    # print("\n📋 الطريقة 4: أعمدة Boolean")
    # print("-" * 40)
    # boolean_columns = [column.name for column in Activity.__table__.columns 
    #                    if str(column.type).startswith('BOOLEAN')]
    # for col in boolean_columns:
    #     print(f"  • {col}")
    
    # # التحقق من وجود is_critical
    # print("\n📋 التحقق من وجود is_critical")
    # print("-" * 40)
    # if 'is_critical' in column_names:
    #     print("  ✅ العمود 'is_critical' موجود")
    # else:
    #     print("  ❌ العمود 'is_critical' غير موجود")
    
    # # عرض معلومات إضافية
    # print("\n📋 معلومات إضافية")
    # print("-" * 40)
    # print(f"  عدد الأعمدة الكلي: {len(column_names)}")
    # print(f"  أسماء الأعمدة: {', '.join(column_names[:10])}...")

# init_platform.py
# fix_platform_table.py
# """
# إصلاح جدول platform_admins - حذف وإعادة إنشاء
# """

# import sys
# import os

# sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# from app import create_app, db
# from sqlalchemy import inspect, text

# app = create_app()

# with app.app_context():
#     print("=" * 60)
#     print("🔧 إصلاح جدول platform_admins...")
#     print("=" * 60)
    
#     # 1. التحقق من وجود الجدول
#     inspector = inspect(db.engine)
#     tables = inspector.get_table_names()
    
#     if 'platform_admins' in tables:
#         print("⚠️ جدول platform_admins موجود، جاري حذفه...")
        
#         # حذف الجدول باستخدام SQL مباشر (لضمان الحذف الكامل)
#         db.session.execute(text("DROP TABLE IF EXISTS platform_admins"))
#         db.session.commit()
#         print("✅ تم حذف الجدول القديم")
#     else:
#         print("ℹ️ جدول platform_admins غير موجود")
    
#     # 2. إعادة إنشاء جميع الجداول (أو فقط هذا الجدول)
#     print("🔄 جاري إعادة إنشاء الجداول...")
#     db.create_all()
#     print("✅ تم إعادة إنشاء جميع الجداول")
    
#     # 3. التحقق من وجود العمود is_active
#     inspector = inspect(db.engine)
#     columns = [col['name'] for col in inspector.get_columns('platform_admins')]
    
#     if 'is_active' in columns:
#         print("✅ العمود is_active موجود في الجدول")
#     else:
#         print("❌ العمود is_active لا يزال غير موجود!")
#         # إضافة العمود يدوياً إذا لزم الأمر
#         db.session.execute(text("ALTER TABLE platform_admins ADD COLUMN is_active BOOLEAN DEFAULT 1"))
#         db.session.commit()
#         print("✅ تم إضافة العمود is_active يدوياً")
    
#     print("=" * 60)
#     print("✅ تم إصلاح الجدول بنجاح!")
#     print("=" * 60)
# """
# تهيئة مستخدمي المنصة (Platform Admins)
# قم بتشغيل هذا الملف مرة واحدة فقط
# """

import sys
import os

# أضف المسار الحالي إلى sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import PlatformOwner, PlatformAdmin
from datetime import datetime

def init_platform_users():
    """تهيئة مستخدمي المنصة"""
    app = create_app()
    
    with app.app_context():
        print("=" * 60)
        print("🚀 بدء تهيئة مستخدمي المنصة...")
        print("=" * 60)
        
        try:
            # 1. إنشاء المنصة (Platform Owner) إذا لم توجد
            platform = PlatformOwner.query.first()
            if not platform:
                platform = PlatformOwner(
                    company_name='منصة إدارة المشاريع الذكية',
                    commercial_register='0000000',
                    tax_number='1234567890',
                    email='info@platform.com',
                    phone='+966500000000',
                    address='الرياض، المملكة العربية السعودية',
                    website='https://platform.com'
                )
                db.session.add(platform)
                db.session.commit()
                print("✅ تم إنشاء المنصة (Platform Owner)")
            else:
                print(f"✅ المنصة موجودة مسبقاً: {platform.company_name}")
            
            # 2. إنشاء المشرف العام (Super Admin)
            super_admin = PlatformAdmin.query.filter_by(email='najmyjomaan@gmail.com').first()
            if not super_admin:
                super_admin = PlatformAdmin(
                    platform_id=platform.id,
                    username='superadmin',
                    email='najmyjomaan@gmail.com',
                    full_name='المشرف العام',
                    phone='+966500000001',
                    role='super_admin',
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                # تعيين كلمة المرور
                super_admin.set_password('admin123')
                db.session.add(super_admin)
                print("✅ تم إنشاء المشرف العام (Super Admin)")
            else:
                print(f"✅ المشرف العام موجود مسبقاً: {super_admin.email}")
                # تحديث كلمة المرور للتأكيد
                super_admin.set_password('admin123')
                db.session.commit()
            
            # 3. إنشاء مدير منصة عادي
            admin = PlatformAdmin.query.filter_by(email='admin@platform.com').first()
            if not admin:
                admin = PlatformAdmin(
                    platform_id=platform.id,
                    username='admin',
                    email='admin@platform.com',
                    full_name='مدير المنصة',
                    phone='+966500000002',
                    role='admin',
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                admin.set_password('Admin123!')
                db.session.add(admin)
                print("✅ تم إنشاء مدير المنصة (Admin)")
            else:
                print(f"✅ مدير المنصة موجود مسبقاً: {admin.email}")
                admin.set_password('Admin123!')
                db.session.commit()
            
            # 4. (اختياري) إنشاء مدير دعم إضافي
            support_admin = PlatformAdmin.query.filter_by(email='support@platform.com').first()
            if not support_admin:
                support_admin = PlatformAdmin(
                    platform_id=platform.id,
                    username='support',
                    email='support@platform.com',
                    full_name='مدير الدعم الفني',
                    phone='+966500000003',
                    role='support',
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                support_admin.set_password('Support123!')
                db.session.add(support_admin)
                print("✅ تم إنشاء مدير الدعم الفني (Support)")
            
            # حفظ جميع التغييرات
            db.session.commit()
            
            print("=" * 60)
            print("✅ تم تهيئة مستخدمي المنصة بنجاح!")
            print("=" * 60)
            print("\n📋 بيانات الدخول:")
            print("-" * 40)
            print("🔹 المشرف العام (Super Admin):")
            print("   📧 البريد: najmyjomaan@gmail.com")
            print("   🔑 كلمة المرور: admin123")
            print()
            print("🔹 مدير المنصة (Admin):")
            print("   📧 البريد: admin@platform.com")
            print("   🔑 كلمة المرور: Admin123!")
            print()
            print("🔹 مدير الدعم (Support):")
            print("   📧 البريد: support@platform.com")
            print("   🔑 كلمة المرور: Support123!")
            print("-" * 40)
            print("\n🔐 يرجى تغيير كلمات المرور بعد تسجيل الدخول الأول")
            print("=" * 60)
            
            # عرض عدد المستخدمين
            total_admins = PlatformAdmin.query.count()
            print(f"\n📊 إجمالي مدراء المنصة: {total_admins}")
            
            # عرض قائمة المدراء
            admins = PlatformAdmin.query.all()
            print("\n📋 قائمة مدراء المنصة:")
            for a in admins:
                print(f"   - {a.full_name} ({a.email}) - {a.role} - {'نشط' if a.is_active else 'معطل'}")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ خطأ أثناء التهيئة: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        
        return True

if __name__ == '__main__':
    success = init_platform_users()
    sys.exit(0 if success else 1)
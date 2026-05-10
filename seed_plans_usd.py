# seed_plans_usd.py
"""
تهيئة خطط الاشتراك بالدولار الأمريكي (USD)
"""

from app import create_app, db
from app.models.core_models import SubscriptionPlan
from datetime import datetime

app = create_app()

with app.app_context():
    print("=" * 60)
    print("💰 بدء تهيئة خطط الاشتراك بالدولار الأمريكي...")
    print("=" * 60)
    
    # حذف الخطط القديمة (اختياري - كن حذراً)
    # SubscriptionPlan.query.delete()
    
    # خطط الاشتراك بالدولار
    usd_plans = [
        {
            'plan_id': 'free',
            'name': 'Free',
            'description': 'Perfect for individuals and small teams starting out',
            'price_monthly': 0,
            'price_yearly': 0,
            'currency': 'USD',
            'max_users': 5,
            'max_projects': 3,
            'storage_gb': 1,
            'features': [
                'Up to 5 users',
                '3 projects',
                '1 GB storage',
                'Basic support',
                'Community access'
            ],
            'display_order': 1,
            'is_featured': False,
            'is_active': True,
            'is_default': False
        },
        {
            'plan_id': 'starter',
            'name': 'Starter',
            'description': 'Ideal for small businesses and startups',
            'price_monthly': 19,
            'price_yearly': 190,
            'currency': 'USD',
            'max_users': 20,
            'max_projects': 10,
            'storage_gb': 20,
            'features': [
                'Up to 20 users',
                '10 projects',
                '20 GB storage',
                'Email support',
                'Basic reports',
                'API access'
            ],
            'display_order': 2,
            'is_featured': False,
            'is_active': True,
            'is_default': False
        },
        {
            'plan_id': 'professional',
            'name': 'Professional',
            'description': 'For growing businesses with advanced needs',
            'price_monthly': 49,
            'price_yearly': 490,
            'currency': 'USD',
            'max_users': 100,
            'max_projects': 50,
            'storage_gb': 100,
            'features': [
                'Up to 100 users',
                '50 projects',
                '100 GB storage',
                'Priority support',
                'Advanced reports',
                'Full API access',
                'Team collaboration tools',
                'Custom integrations'
            ],
            'display_order': 3,
            'is_featured': True,
            'is_active': True,
            'is_default': True  # جعل هذه الخطة افتراضية
        },
        {
            'plan_id': 'business',
            'name': 'Business',
            'description': 'For medium to large enterprises',
            'price_monthly': 99,
            'price_yearly': 990,
            'currency': 'USD',
            'max_users': 500,
            'max_projects': 200,
            'storage_gb': 500,
            'features': [
                'Up to 500 users',
                '200 projects',
                '500 GB storage',
                '24/7 priority support',
                'Advanced analytics',
                'Custom reports',
                'SSO integration',
                'Audit logs',
                'Dedicated account manager'
            ],
            'display_order': 4,
            'is_featured': True,
            'is_active': True,
            'is_default': False
        },
        {
            'plan_id': 'enterprise',
            'name': 'Enterprise',
            'description': 'For large organizations with custom requirements',
            'price_monthly': 249,
            'price_yearly': 2490,
            'currency': 'USD',
            'max_users': 0,  # 0 = unlimited
            'max_projects': 0,  # 0 = unlimited
            'storage_gb': 2000,
            'features': [
                'Unlimited users',
                'Unlimited projects',
                '2 TB storage',
                '24/7 VIP support',
                'Custom development',
                'On-premise deployment',
                'SLA guarantee',
                'Custom training',
                'Dedicated infrastructure'
            ],
            'display_order': 5,
            'is_featured': True,
            'is_active': True,
            'is_default': False
        }
    ]
    
    created_count = 0
    updated_count = 0
    
    for plan_data in usd_plans:
        existing = SubscriptionPlan.query.filter_by(plan_id=plan_data['plan_id']).first()
        
        if existing:
            # تحديث الخطة الموجودة
            existing.name = plan_data['name']
            existing.description = plan_data['description']
            existing.price_monthly = plan_data['price_monthly']
            existing.price_yearly = plan_data['price_yearly']
            existing.currency = plan_data['currency']
            existing.max_users = plan_data['max_users']
            existing.max_projects = plan_data['max_projects']
            existing.storage_gb = plan_data['storage_gb']
            existing.features = plan_data['features']
            existing.display_order = plan_data['display_order']
            existing.is_featured = plan_data['is_featured']
            existing.is_active = plan_data['is_active']
            existing.is_default = plan_data['is_default']
            updated_count += 1
            print(f"🔄 تحديث الخطة: {plan_data['name']} (${plan_data['price_monthly']})")
        else:
            # إنشاء خطة جديدة
            plan = SubscriptionPlan(**plan_data)
            db.session.add(plan)
            created_count += 1
            print(f"✅ إنشاء خطة جديدة: {plan_data['name']} (${plan_data['price_monthly']})")
    
    # التأكد من وجود خطة افتراضية واحدة فقط
    if not SubscriptionPlan.query.filter_by(is_default=True).first():
        professional = SubscriptionPlan.query.filter_by(plan_id='professional').first()
        if professional:
            professional.is_default = True
            print("⭐ تعيين خطة Professional كخطة افتراضية")
    else:
        # إلغاء تحديد الخطط الافتراضية الأخرى
        SubscriptionPlan.query.update({SubscriptionPlan.is_default: False})
        professional = SubscriptionPlan.query.filter_by(plan_id='professional').first()
        if professional:
            professional.is_default = True
            print("⭐ تعيين خطة Professional كخطة افتراضية")
    
    db.session.commit()
    
    print("=" * 60)
    print(f"📊 تم إنشاء {created_count} خطة جديدة وتحديث {updated_count} خطة")
    print("✅ تم تهيئة خطط الاشتراك بالدولار بنجاح!")
    print("=" * 60)
    
    # عرض جميع الخطط
    plans = SubscriptionPlan.query.order_by(SubscriptionPlan.display_order).all()
    print("\n📋 قائمة خطط الاشتراك (USD):")
    print("-" * 50)
    for plan in plans:
        status = "🟢 نشطة" if plan.is_active else "🔴 معطلة"
        default = "⭐ [افتراضية]" if plan.is_default else ""
        print(f"   - {plan.name} ({plan.plan_id})")
        print(f"     💰 ${plan.price_monthly}/شهر أو ${plan.price_yearly}/سنة")
        print(f"     📊 {status} {default}")
        print()

# seed_subscription_plans.py
"""
تهيئة خطط الاشتراك في المنصة
تشمل خطة مجانية (Trial) لمدة 20 يوماً، وخطط مدفوعة بالدولار
"""

from app import create_app, db
from app.models.core_models import SubscriptionPlan, Organization, Subscription
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()

def seed_plans():
    """تهيئة خطط الاشتراك"""
    
    with app.app_context():
        print("=" * 60)
        print("🚀 بدء تهيئة خطط الاشتراك...")
        print("=" * 60)
        
        # تعريف الخطط
        plans = [
            {
                'plan_id': 'trial',
                'name': 'فترة تجريبية',
                'name_ar': 'فترة تجريبية',
                'description': 'فترة تجريبية مجانية لمدة 20 يوم للتعرف على المنصة',
                'description_ar': 'فترة تجريبية مجانية لمدة 20 يوم للتعرف على المنصة',
                'price_monthly': 0,
                'price_yearly': 0,
                'currency': 'USD',
                'max_users': 10,
                'max_projects': 5,
                'storage_gb': 1,
                'features': [
                    '10 مستخدمين كحد أقصى',
                    '5 مشاريع كحد أقصى',
                    '1 جيجابايت تخزين',
                    'دعم أساسي',
                    'فترة تجريبية 20 يوم'
                ],
                'display_order': 1,
                'is_featured': False,
                'is_active': True,
                'is_default': True,
                'trial_days': 20
            },
            {
                'plan_id': 'basic',
                'name': 'Basic',
                'name_ar': 'أساسي',
                'description': 'خطة أساسية للشركات الصغيرة',
                'description_ar': 'خطة أساسية للشركات الصغيرة',
                'price_monthly': 29,
                'price_yearly': 290,
                'currency': 'USD',
                'max_users': 50,
                'max_projects': 20,
                'storage_gb': 10,
                'features': [
                    '50 مستخدم كحد أقصى',
                    '20 مشروع كحد أقصى',
                    '10 جيجابايت تخزين',
                    'دعم البريد الإلكتروني',
                    'تقارير أساسية',
                    'API أساسي'
                ],
                'display_order': 2,
                'is_featured': False,
                'is_active': True,
                'is_default': False
            },
            {
                'plan_id': 'professional',
                'name': 'Professional',
                'name_ar': 'احترافي',
                'description': 'خطة احترافية للشركات المتوسطة',
                'description_ar': 'خطة احترافية للشركات المتوسطة',
                'price_monthly': 79,
                'price_yearly': 790,
                'currency': 'USD',
                'max_users': 200,
                'max_projects': 100,
                'storage_gb': 50,
                'features': [
                    '200 مستخدم كحد أقصى',
                    '100 مشروع كحد أقصى',
                    '50 جيجابايت تخزين',
                    'دعم أولوية',
                    'تقارير متقدمة',
                    'API كامل',
                    'تعاون الفريق',
                    'تحليلات متقدمة'
                ],
                'display_order': 3,
                'is_featured': True,
                'is_active': True,
                'is_default': False
            },
            {
                'plan_id': 'enterprise',
                'name': 'Enterprise',
                'name_ar': 'شركات',
                'description': 'خطة متكاملة للشركات الكبيرة',
                'description_ar': 'خطة متكاملة للشركات الكبيرة',
                'price_monthly': 199,
                'price_yearly': 1990,
                'currency': 'USD',
                'max_users': 0,  # غير محدود
                'max_projects': 0,  # غير محدود
                'storage_gb': 200,
                'features': [
                    'مستخدمين غير محدودين',
                    'مشاريع غير محدودة',
                    '200 جيجابايت تخزين',
                    'دعم VIP 24/7',
                    'API مخصص',
                    'خادم مخصص',
                    'ضمان مستوى الخدمة',
                    'تدريب مخصص',
                    'تكامل مخصص'
                ],
                'display_order': 4,
                'is_featured': True,
                'is_active': True,
                'is_default': False
            }
        ]
        
        created_count = 0
        updated_count = 0
        
        for plan_data in plans:
            existing = SubscriptionPlan.query.filter_by(plan_id=plan_data['plan_id']).first()
            
            if existing:
                # تحديث الخطة الموجودة
                existing.name = plan_data['name']
                existing.description = plan_data['description']
                existing.price_monthly = plan_data['price_monthly']
                existing.price_yearly = plan_data['price_yearly']
                existing.currency = plan_data['currency']
                existing.max_users = plan_data['max_users']
                existing.max_projects = plan_data['max_projects']
                existing.storage_gb = plan_data['storage_gb']
                existing.features = plan_data['features']
                existing.display_order = plan_data['display_order']
                existing.is_featured = plan_data['is_featured']
                existing.is_active = plan_data['is_active']
                existing.is_default = plan_data.get('is_default', False)
                updated_count += 1
                print(f"🔄 تحديث الخطة: {plan_data['name']} ({plan_data['currency']})")
            else:
                # إنشاء خطة جديدة
                plan = SubscriptionPlan(
                    plan_id=plan_data['plan_id'],
                    name=plan_data['name'],
                    description=plan_data['description'],
                    price_monthly=plan_data['price_monthly'],
                    price_yearly=plan_data['price_yearly'],
                    currency=plan_data['currency'],
                    max_users=plan_data['max_users'],
                    max_projects=plan_data['max_projects'],
                    storage_gb=plan_data['storage_gb'],
                    features=plan_data['features'],
                    display_order=plan_data['display_order'],
                    is_featured=plan_data['is_featured'],
                    is_active=plan_data['is_active'],
                    is_default=plan_data.get('is_default', False)
                )
                db.session.add(plan)
                created_count += 1
                print(f"✅ إنشاء خطة جديدة: {plan_data['name']} ({plan_data['currency']})")
        
        # تعيين الخطة التجريبية كخطة افتراضية
        trial_plan = SubscriptionPlan.query.filter_by(plan_id='trial').first()
        if trial_plan:
            # إلغاء الخطة الافتراضية الحالية
            SubscriptionPlan.query.update({SubscriptionPlan.is_default: False})
            trial_plan.is_default = True
            print(f"⭐ تعيين الخطة التجريبية كخطة افتراضية للشركات الجديدة")
        
        db.session.commit()
        
        print("=" * 60)
        print(f"📊 تم إنشاء {created_count} خطة جديدة وتحديث {updated_count} خطة")
        print("✅ تم تهيئة خطط الاشتراك بنجاح!")
        print("=" * 60)
        
        # عرض جميع الخطط
        plans = SubscriptionPlan.query.order_by(SubscriptionPlan.display_order).all()
        print("\n📋 قائمة خطط الاشتراك:")
        for plan in plans:
            status = "🟢 نشطة" if plan.is_active else "🔴 معطلة"
            default = "⭐ [افتراضية]" if plan.is_default else ""
            print(f"   - {plan.name} ({plan.plan_id}) - {plan.currency} {plan.price_monthly}/شهر - {status} {default}")


def update_existing_companies_trial():
    """تحديث الشركات الموجودة لتعيين الفترة التجريبية لها"""
    
    with app.app_context():
        print("\n" + "=" * 60)
        print("🔄 تحديث الشركات الموجودة بالفترة التجريبية...")
        print("=" * 60)
        
        # جلب جميع الشركات التي ليس لها اشتراك نشط
        companies = Organization.query.all()
        updated_count = 0
        
        for company in companies:
            # التحقق من وجود اشتراك نشط
            active_subscription = Subscription.query.filter_by(
                org_id=company.id,
                status='active'
            ).first()
            
            if not active_subscription and company.subscription_status != 'active':
                # تعيين الفترة التجريبية للشركة
                trial_end = datetime.utcnow() + timedelta(days=20)
                company.subscription_status = 'trial'
                company.subscription_start = datetime.utcnow()
                company.subscription_end = trial_end
                company.trial_start = datetime.utcnow()
                company.trial_end = trial_end
                
                # إنشاء اشتراك تجريبي
                trial_plan = SubscriptionPlan.query.filter_by(plan_id='trial').first()
                
                subscription = Subscription(
                    org_id=company.id,
                    plan='trial',
                    plan_id='trial',
                    plan_name='فترة تجريبية',
                    amount=0,
                    currency='USD',
                    payment_method='system',
                    status='trial',
                    start_date=datetime.utcnow(),
                    end_date=trial_end,
                    auto_renew=False,
                    duration_months=0,
                    created_by=None
                )
                db.session.add(subscription)
                updated_count += 1
                print(f"   ✅ تم تعيين الفترة التجريبية لشركة: {company.name} (تنتهي في {trial_end.strftime('%Y-%m-%d')})")
        
        db.session.commit()
        print(f"\n✅ تم تحديث {updated_count} شركة بالفترة التجريبية")


if __name__ == '__main__':
    seed_plans()
    update_existing_companies_trial()
    print("\n🎉 اكتملت تهيئة خطط الاشتراك بنجاح!")
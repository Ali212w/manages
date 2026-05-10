# app.py
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify, session, abort,send_file
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
import stripe

from config import Config
from extensions import db, login_manager, migrate , mail, csrf, cache
from uploads.temp.models import *
from forms import *
from decorators import role_required, subscription_required, can_access_project, can_access_task,project_member_required,project_role_required,project_isolated_required,user_can_access_project
from workflow import WorkflowManager
from services.ai_extractor import DataExtractor 
from utils.utils import *


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # تهيئة الامتدادات
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة'
    login_manager.login_message_category = 'info'
    
    migrate.init_app(app, db)
    mail.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    
    # إعداد Stripe
    stripe.api_key = app.config['STRIPE_SECRET_KEY']
    
    # إنشاء مجلد الرفع إذا لم يكن موجوداً
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('static/profile_pics', exist_ok=True)

    with app.app_context():
        db.create_all()
        print("Tables created successfully!")
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # ==================== الصفحات العامة ====================
    
    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return render_template('index.html')
    
    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(
                username=form.username.data,
                email=form.email.data,
                full_name=form.full_name.data,
                phone=form.phone.data,
                role='project_manager',  # دور افتراضي
                trial_end=datetime.utcnow() + timedelta(days=app.config['TRIAL_DAYS'])
            )
            user.password = form.password.data
            
            db.session.add(user)
            db.session.commit()
            
            flash('تم إنشاء الحساب بنجاح! يمكنك تسجيل الدخول الآن', 'success')
            return redirect(url_for('login'))
        
        return render_template('auth/register.html', form=form)
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        
        form = LoginForm()
        if form.validate_on_submit():
            user = User.query.filter_by(email=form.email.data).first()
            if user and user.verify_password(form.password.data):
                login_user(user, remember=form.remember.data)
                user.last_login = datetime.utcnow()
                db.session.commit()
                
                next_page = request.args.get('next')
                flash(f'مرحباً {user.full_name}! تم تسجيل الدخول بنجاح', 'success')
                return redirect(next_page) if next_page else redirect(url_for('dashboard'))
            else:
                flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'danger')
        
        return render_template('auth/login.html', form=form)
    
    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        flash('تم تسجيل الخروج بنجاح', 'success')
        return redirect(url_for('index'))
    
    # ==================== لوحات التحكم حسب الدور ====================
    
    @app.route('/dashboard')
    @login_required
    @subscription_required
    def dashboard():
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif current_user.role == 'project_manager':
            return redirect(url_for('pm_dashboard'))
        elif current_user.role == 'supervisor':
            return redirect(url_for('supervisor_dashboard'))
        elif current_user.role == 'delegate':
            return redirect(url_for('delegate_dashboard'))
        else:
            return redirect(url_for('worker_dashboard'))
    
    @app.route('/dashboard/admin')
    @login_required
    @role_required('admin')
    def admin_dashboard():
        # إحصائيات عامة
        total_users = User.query.count()
        total_projects = Project.query.count()
        active_projects = Project.query.filter_by(status='in_progress').count()
        total_tasks = Task.query.count()
        
        # آخر المستخدمين
        recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
        
        # آخر المشاريع
        recent_projects = Project.query.order_by(Project.created_at.desc()).limit(5).all()
        
        return render_template('dashboard/admin_dashboard.html',
                             total_users=total_users,
                             total_projects=total_projects,
                             active_projects=active_projects,
                             total_tasks=total_tasks,
                             recent_users=recent_users,
                             recent_projects=recent_projects,User=User)
    
    @app.route('/dashboard/pm')
    @login_required
    @role_required('project_manager')
    def pm_dashboard():
        projects = Project.query.filter_by(manager_id=current_user.id).all()
        
        # إحصائيات
        total_projects = len(projects)
        active_projects = sum(1 for p in projects if p.status == 'in_progress')
        completed_projects = sum(1 for p in projects if p.status == 'completed')
        
        # المهام القادمة
        upcoming_tasks = Task.query.join(Project).filter(
            Project.manager_id == current_user.id,
            Task.status == 'pending',
            Task.planned_start <= datetime.utcnow() + timedelta(days=3)
        ).limit(10).all()
        task_count = Task.query.join(Project).filter(Project.manager_id == current_user.id).count()
        
        return render_template('dashboard/pm_dashboard.html',
                             projects=projects,
                             total_projects=total_projects,
                             active_projects=active_projects,
                             completed_projects=completed_projects,
                             upcoming_tasks=upcoming_tasks,task_count=task_count,now=datetime.utcnow())
    
    @app.route('/dashboard/supervisor')
    @login_required
    @role_required('supervisor')
    def supervisor_dashboard():
        # المهام التي يشرف عليها
        supervised_tasks = Task.query.filter_by(
            assigned_to_id=current_user.id,
            status='in_progress'
        ).all()
        
        # المهام المنجزة
        completed_tasks = Task.query.filter_by(
            assigned_to_id=current_user.id,
            status='completed'
        ).count()
        
        # أعضاء الفريق (المناديب والأفراد)
        team_members = User.query.filter_by(role='worker').limit(10).all()
        
        return render_template('dashboard/supervisor_dashboard.html',
                             supervised_tasks=supervised_tasks,
                             completed_tasks=completed_tasks,
                             team_members=team_members,now=datetime.utcnow())
    
    @app.route('/dashboard/delegate')
    @login_required
    @role_required('delegate')
    def delegate_dashboard():
        # المهام المسندة
        assigned_tasks = Task.query.filter_by(
            assigned_to_id=current_user.id
        ).order_by(Task.created_at.desc()).all()
        
        return render_template('dashboard/delegate_dashboard.html',
                             assigned_tasks=assigned_tasks,now=datetime.utcnow())
    
    @app.route('/dashboard/worker')
    @login_required
    @role_required('worker')
    def worker_dashboard():
        # المهام الحالية
        current_tasks = Task.query.filter_by(
            assigned_to_id=current_user.id,
            status='in_progress'
        ).all()
        
        # المهام المنجزة
        completed_tasks = Task.query.filter_by(
            assigned_to_id=current_user.id,
            status='completed'
        ).order_by(Task.completed_at.desc()).limit(10).all()
        # المهام في الانتظار
        pending_tasks_count = Task.query.filter_by(
            assigned_to_id=current_user.id,
            status='pending'
        ).count()
        
        return render_template('dashboard/worker_dashboard.html',
                             current_tasks=current_tasks,
                             completed_tasks=completed_tasks,pending_tasks_count=pending_tasks_count,now=datetime.utcnow())
    
    # ==================== إدارة المشاريع ====================
    
    @app.route('/projects')
    @login_required
    @subscription_required
    def projects_list():
        if current_user.role == 'admin':
            projects = Project.query.all()
        elif current_user.role == 'project_manager':
            projects = Project.query.filter_by(manager_id=current_user.id).all()
        else:
            # للمستخدمين الآخرين: المشاريع التي لديهم مهام فيها
            projects = Project.query.join(Task).filter(Task.assigned_to_id == current_user.id).distinct().all()
        
        return render_template('projects/projects_list.html', projects=projects,now=datetime.utcnow())
    
    @app.route('/project/new', methods=['GET', 'POST'])
    @login_required
    @role_required('project_manager', 'admin')
    @subscription_required
    def new_project():
        form = ProjectForm()
        from services.hybrid_extractor import HybridExtractor
        extractor = HybridExtractor()
        extraction_status = extractor.get_status()

        if form.validate_on_submit():
            project = Project(
                title=form.title.data,
                description=form.description.data,
                location=form.location.data,
                region=form.region.data,
                client_name=form.client_name.data,
                client_phone=form.client_phone.data,
                estimated_budget=form.estimated_budget.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                priority=form.priority.data,
                manager_id=current_user.id
            )
            
            db.session.add(project)
            db.session.commit()
            # إضافة مدير المشروع كعضو في الفريق
            team_member = ProjectTeam(
                project_id=project.id,
                user_id=current_user.id,
                role_in_project='manager',
                added_by_id=current_user.id
            )
            db.session.add(team_member)
            db.session.commit()
            
            # معالجة الملف إذا تم رفعه
            extraction_method = request.form.get('extraction_method', 'auto')
            # معالجة الملف إذا تم رفعه
            if form.project_file.data:
                try:
                    file = form.project_file.data
                    filename = secure_filename(file.filename)
                    file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"project_{project.id}_{filename}")
                    file.save(file_path)
                    
                    project.original_file_path = file_path
                    
                    # اختيار طريقة الاستخراج
                    if extraction_method == 'auto':
                        # استخدام النظام الهجين
                        extractor = HybridExtractor(use_ai=True)
                        result = extractor.extract(file_path, file_ext, project.id)
                        
                    elif extraction_method == 'ai':
                        #强制 استخدام الذكاء الاصطناعي
                        if extractor.ai_available:
                            from services.ai_extractor import parse_project_with_ai
                            result = parse_project_with_ai(file_path, file_ext)
                            result['method'] = 'ai_forced'
                        else:
                            flash('الذكاء الاصطناعي غير متاح، سيتم استخدام الاستخراج اليدوي', 'warning')
                            from services.manual_extractor import ManualExtractor
                            manual = ManualExtractor()
                            result = manual.extract(file_path, file_ext)
                            result['method'] = 'manual_fallback'
                    
                    elif extraction_method == 'manual':
                        # استخدام الاستخراج اليدوي
                        from services.manual_extractor import ManualExtractor
                        manual = ManualExtractor()
                        result = manual.extract(file_path, file_ext)
                        result['method'] = 'manual'
                    
                    # معالجة النتيجة
                    if result and result.get('success'):
                        # تحديث بيانات المشروع
                        if 'project' in result and result['project']:
                            if result['project'].get('title'):
                                project.title = result['project']['title']
                            if result['project'].get('location'):
                                project.location = result['project']['location']
                            if result['project'].get('region'):
                                project.region = result['project']['region']
                            if result['project'].get('client_name'):
                                project.client_name = result['project']['client_name']
                            if result['project'].get('estimated_budget'):
                                project.estimated_budget = result['project']['estimated_budget']
                        
                        # حفظ المهام
                        if 'tasks' in result and result['tasks']:
                            from services.ai_extractor import save_tasks_recursively
                            tasks_saved = save_tasks_recursively(result['tasks'], project.id)
                            
                            # رسالة حسب طريقة الاستخراج
                            method_messages = {
                                'ai': 'بالذكاء الاصطناعي',
                                'ai_forced': 'بالذكاء الاصطناعي (إجباري)',
                                'manual': 'يدوياً',
                                'manual_fallback': 'يدوياً (بعد فشل الذكاء الاصطناعي)',
                                'none': ''
                            }
                            
                            method_name = method_messages.get(result.get('method', ''), '')
                            
                            flash(f'✅ تم رفع الملف واستخراج {tasks_saved} مهمة {method_name} بنجاح', 'success')
                            
                            if result.get('warnings'):
                                for warning in result['warnings']:
                                    flash(f'⚠️ {warning}', 'warning')
                        else:
                            flash('⚠️ تم رفع الملف ولكن لم يتم العثور على مهام', 'warning')
                        
                        # حفظ البيانات المستخرجة
                        import json
                        project.extracted_data_json = json.dumps(result)
                        
                    else:
                        error_msg = result.get('error', 'فشل غير معروف') if result else 'فشل في معالجة الملف'
                        flash(f'❌ فشل في استخراج البيانات: {error_msg}', 'danger')
                    
                    db.session.commit()
                    
                except Exception as e:
                    flash(f'❌ حدث خطأ في معالجة الملف: {str(e)}', 'danger')
                    logger.error(f"File processing error: {e}")
            
            log_activity(current_user.id, 'create_project', f'أنشأ مشروع: {project.title}', project_id=project.id)
            flash('🎉 تم إنشاء المشروع بنجاح', 'success')
            return redirect(url_for('project_view', project_id=project.id))
        
        return render_template('projects/upload_project.html', form=form,extraction_status=extraction_status,now=datetime.utcnow())
    
    @app.route('/project/<int:project_id>')
    @login_required
    @project_member_required
    @subscription_required
    def project_view(project_id):
        project = Project.query.get_or_404(project_id)
        
        # جلب المهام الرئيسية
        main_tasks = Task.query.filter_by(
            project_id=project_id,
            parent_task_id=None
        ).order_by(Task.order_index).all()
        
        # إحصائيات المشروع
        total_tasks = Task.query.filter_by(project_id=project_id).count()
        completed_tasks = Task.query.filter_by(project_id=project_id, status='completed').count()
        in_progress_tasks = Task.query.filter_by(project_id=project_id, status='in_progress').count()
        
        return render_template('projects/project_detail.html',
                             project=project,
                             tasks=main_tasks,
                             total_tasks=total_tasks,
                             completed_tasks=completed_tasks,
                             in_progress_tasks=in_progress_tasks,now=datetime.utcnow())
    
    @app.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
    @login_required
    @can_access_project
    @subscription_required
    def edit_project(project_id):
        project = Project.query.get_or_404(project_id)
        form = ProjectForm(obj=project)
        
        if form.validate_on_submit():
            form.populate_obj(project)
            db.session.commit()
            
            log_activity(current_user.id, 'edit_project', f'عدل مشروع: {project.title}', project_id=project.id)
            flash('تم تحديث المشروع بنجاح', 'success')
            return redirect(url_for('project_view', project_id=project.id))
        
        return render_template('projects/edit_project.html', form=form, project=project,now=datetime.utcnow())
    
    @app.route('/project/<int:project_id>/timeline')
    @login_required
    @can_access_project
    @subscription_required
    def project_timeline(project_id):
        project = Project.query.get_or_404(project_id)
        
        # جلب جميع المهام مرتبة حسب تاريخ البدء
        tasks = Task.query.filter_by(project_id=project_id).order_by(Task.planned_start).all()
        
        return render_template('projects/project_timeline.html', project=project, tasks=tasks,now=datetime.utcnow())
    
    # ==================== إدارة فريق المشروع ====================

    @app.route('/project/<int:project_id>/team')
    @login_required
    def project_team(project_id):
        """صفحة إدارة فريق المشروع"""
        project = Project.query.get_or_404(project_id)
        
        # التحقق من الصلاحية (مدير المشروع فقط)
        if current_user.role != 'admin' and project.manager_id != current_user.id:
            flash('ليس لديك صلاحية لإدارة فريق هذا المشروع', 'danger')
            return redirect(url_for('project_view', project_id=project.id))
        
        # الحصول على أعضاء الفريق
        team_members = ProjectTeam.query.filter_by(project_id=project_id, is_active=True).all()
        
        # الحصول على الدعوات المعلقة
        pending_invitations = ProjectInvitation.query.filter_by(
            project_id=project_id, 
            status='pending'
        ).all()
        
        # المستخدمين المتاحين للإضافة (ليسوا في الفريق)
        team_user_ids = [m.user_id for m in team_members]
        available_users = User.query.filter(
            User.id.notin_(team_user_ids) if team_user_ids else True,
            User.is_active == True
        ).limit(20).all()
        
        return render_template('projects/team.html', 
                            project=project,
                            team_members=team_members,
                            pending_invitations=pending_invitations,
                            available_users=available_users,now=datetime.utcnow())


    @app.route('/project/<int:project_id>/team/add', methods=['POST'])
    @login_required
    def add_team_member(project_id):
        """إضافة عضو جديد للفريق"""
        project = Project.query.get_or_404(project_id)
        
        # التحقق من الصلاحية
        if current_user.role != 'admin' and project.manager_id != current_user.id:
            flash('ليس لديك صلاحية لإضافة أعضاء', 'danger')
            return redirect(url_for('project_view', project_id=project.id))
        
        user_id = request.form.get('user_id')
        role = request.form.get('role')
        
        if not user_id or not role:
            flash('الرجاء اختيار مستخدم ودور', 'warning')
            return redirect(url_for('project_team', project_id=project.id))
        
        # التحقق من أن المستخدم ليس في الفريق بالفعل
        existing = ProjectTeam.query.filter_by(project_id=project_id, user_id=user_id).first()
        if existing:
            if existing.is_active:
                flash('هذا المستخدم موجود بالفعل في الفريق', 'warning')
            else:
                # إعادة تفعيل العضو
                existing.is_active = True
                existing.role_in_project = role
                db.session.commit()
                flash('تم إعادة تفعيل العضو في الفريق', 'success')
            return redirect(url_for('project_team', project_id=project.id))
        
        # إضافة العضو الجديد
        team_member = ProjectTeam(
            project_id=project_id,
            user_id=user_id,
            role_in_project=role,
            added_by_id=current_user.id
        )
        db.session.add(team_member)
        db.session.commit()
        
        # إرسال إشعار للمستخدم
        send_notification(
            user_id,
            'انضمام لفريق مشروع',
            f'تمت إضافتك كـ {role} في مشروع "{project.title}"',
            'success',
            project_id=project.id
        )
        
        flash('تم إضافة العضو بنجاح', 'success')
        return redirect(url_for('project_team', project_id=project.id))


    @app.route('/project/<int:project_id>/team/invite', methods=['POST'])
    @login_required
    def invite_team_member(project_id):
        """إرسال دعوة للانضمام للفريق"""
        project = Project.query.get_or_404(project_id)
        
        # التحقق من الصلاحية
        if current_user.role != 'admin' and project.manager_id != current_user.id:
            flash('ليس لديك صلاحية لإرسال دعوات', 'danger')
            return redirect(url_for('project_view', project_id=project.id))
        
        email = request.form.get('email')
        role = request.form.get('role')
        
        if not email or not role:
            flash('الرجاء إدخال البريد الإلكتروني واختيار دور', 'warning')
            return redirect(url_for('project_team', project_id=project.id))
        
        # التحقق من وجود دعوة سابقة معلقة
        existing = ProjectInvitation.query.filter_by(
            project_id=project_id,
            email=email,
            status='pending'
        ).first()
        
        if existing:
            flash('هناك دعوة معلقة بالفعل لهذا البريد', 'warning')
            return redirect(url_for('project_team', project_id=project.id))
        
        # إنشاء دعوة جديدة
        token = generate_invitation_token()
        invitation = ProjectInvitation(
            project_id=project_id,
            email=email,
            role_in_project=role,
            invited_by_id=current_user.id,
            token=token,
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
        db.session.add(invitation)
        db.session.commit()
        
        # إرسال البريد الإلكتروني
        send_project_invitation_email(email, project, current_user, role, token)
        
        flash('تم إرسال الدعوة بنجاح', 'success')
        return redirect(url_for('project_team', project_id=project.id))


    @app.route('/invitation/<token>')
    def accept_project_invitation(token):
        """قبول دعوة الانضمام للمشروع"""
        invitation = ProjectInvitation.query.filter_by(token=token).first_or_404()
        
        if invitation.status != 'pending':
            flash('هذه الدعوة منتهية الصلاحية أو تم استخدامها', 'warning')
            return redirect(url_for('index'))
        
        if invitation.expires_at < datetime.utcnow():
            invitation.status = 'expired'
            db.session.commit()
            flash('انتهت صلاحية هذه الدعوة', 'warning')
            return redirect(url_for('index'))
        
        # إذا كان المستخدم مسجل الدخول
        if current_user.is_authenticated:
            # التحقق من أن البريد الإلكتروني يطابق
            if current_user.email != invitation.email:
                flash('هذه الدعوة موجهة لبريد إلكتروني آخر', 'danger')
                return redirect(url_for('dashboard'))
            
            # إضافة المستخدم للفريق
            team_member = ProjectTeam(
                project_id=invitation.project_id,
                user_id=current_user.id,
                role_in_project=invitation.role_in_project,
                added_by_id=invitation.invited_by_id
            )
            db.session.add(team_member)
            
            # تحديث حالة الدعوة
            invitation.status = 'accepted'
            db.session.commit()
            
            flash(f'تم انضمامك لفريق مشروع "{invitation.project.title}" بنجاح', 'success')
            return redirect(url_for('project_view', project_id=invitation.project_id))
        
        # إذا لم يكن مسجل الدخول، نخزنه في session ونوجهه للتسجيل
        session['pending_invitation_token'] = token
        flash('الرجاء تسجيل الدخول أو إنشاء حساب لقبول الدعوة', 'info')
        return redirect(url_for('register', email=invitation.email))


    @app.route('/project/<int:project_id>/team/remove/<int:user_id>', methods=['POST'])
    @login_required
    def remove_team_member(project_id, user_id):
        """إزالة عضو من الفريق"""
        project = Project.query.get_or_404(project_id)
        
        # التحقق من الصلاحية
        if current_user.role != 'admin' and project.manager_id != current_user.id:
            flash('ليس لديك صلاحية لإزالة أعضاء', 'danger')
            return redirect(url_for('project_view', project_id=project.id))
        
        # لا يمكن إزالة مدير المشروع نفسه
        if user_id == project.manager_id:
            flash('لا يمكن إزالة مدير المشروع', 'warning')
            return redirect(url_for('project_team', project_id=project.id))
        
        team_member = ProjectTeam.query.filter_by(
            project_id=project_id,
            user_id=user_id,
            is_active=True
        ).first_or_404()
        
        # بدلاً من الحذف، نعطل العضو فقط
        team_member.is_active = False
        db.session.commit()
        
        # إرسال إشعار
        send_notification(
            user_id,
            'إزالة من فريق مشروع',
            f'تمت إزالتك من فريق مشروع "{project.title}"',
            'info'
        )
        
        flash('تم إزالة العضو من الفريق', 'success')
        return redirect(url_for('project_team', project_id=project.id))


    @app.route('/project/<int:project_id>/team/role/<int:user_id>', methods=['POST'])
    @login_required
    def update_team_member_role(project_id, user_id):
        """تحديث دور عضو في الفريق"""
        project = Project.query.get_or_404(project_id)
        
        # التحقق من الصلاحية
        if current_user.role != 'admin' and project.manager_id != current_user.id:
            flash('ليس لديك صلاحية لتغيير الأدوار', 'danger')
            return redirect(url_for('project_view', project_id=project.id))
        
        new_role = request.form.get('role')
        if not new_role:
            flash('الرجاء اختيار دور', 'warning')
            return redirect(url_for('project_team', project_id=project.id))
        
        team_member = ProjectTeam.query.filter_by(
            project_id=project_id,
            user_id=user_id,
            is_active=True
        ).first_or_404()
        
        old_role = team_member.role_in_project
        team_member.role_in_project = new_role
        db.session.commit()
        
        # إرسال إشعار
        send_notification(
            user_id,
            'تحديث دورك في المشروع',
            f'تم تغيير دورك في مشروع "{project.title}" من {old_role} إلى {new_role}',
            'info',
            project_id=project.id
        )
        
        flash('تم تحديث دور العضو بنجاح', 'success')
        return redirect(url_for('project_team', project_id=project.id))


    @app.route('/project/<int:project_id>/team/permissions/<int:user_id>', methods=['POST'])
    @login_required
    def update_member_permissions(project_id, user_id):
        """تحديث صلاحيات مخصصة لعضو"""
        project = Project.query.get_or_404(project_id)
        
        if current_user.role != 'admin' and project.manager_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        team_member = ProjectTeam.query.filter_by(
            project_id=project_id,
            user_id=user_id,
            is_active=True
        ).first_or_404()
        
        permissions = request.json
        team_member.permissions = permissions
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'تم تحديث الصلاحيات'})


    @app.route('/api/project/<int:project_id>/team')
    @login_required
    def get_project_team_api(project_id):
        """API للحصول على فريق المشروع (للاستخدام في JavaScript)"""
        project = Project.query.get_or_404(project_id)
        
        # التحقق من أن المستخدم في الفريق
        if not project.is_user_in_team(current_user.id) and current_user.role != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        team_members = ProjectTeam.query.filter_by(project_id=project_id, is_active=True).all()
        
        result = []
        for member in team_members:
            result.append({
                'id': member.user.id,
                'name': member.user.full_name,
                'email': member.user.email,
                'avatar': url_for('static', filename=f'profile_pics/{member.user.profile_image}'),
                'role': member.role_in_project,
                'joined_at': member.joined_at.strftime('%Y-%m-%d'),
                'permissions': member.permissions
            })
        
        return jsonify(result)
    
    # ==================== دعوة مستخدمين جدد للمشروع ====================

    @app.route('/project/<int:project_id>/invite', methods=['GET', 'POST'])
    @login_required
    @project_isolated_required
    @project_role_required(['project_manager', 'admin'])
    def invite_to_project(project_id):
        """صفحة دعوة مستخدمين جدد للمشروع"""
        project = Project.query.get_or_404(project_id)
        
        if request.method == 'POST':
            email = request.form.get('email')
            full_name = request.form.get('full_name')
            role = request.form.get('role')
            custom_message=request.form.get('custom_message')
            phon_number=request.form.get('phon_number')
            if not email or not role:
                flash('الرجاء إدخال البريد الإلكتروني واختيار دور', 'warning')
                return redirect(url_for('invite_to_project', project_id=project.id))
            
            # التحقق من وجود مستخدم بهذا البريد
            existing_user = User.query.filter_by(email=email).first()
            
            # التحقق من عدم وجود دعوة سابقة معلقة
            existing_invitation = ProjectInvitation.query.filter_by(
                project_id=project_id,
                email=email,
                status='pending'
            ).first()
            
            if existing_invitation:
                flash('هناك دعوة معلقة بالفعل لهذا البريد', 'warning')
                return redirect(url_for('project_team', project_id=project.id))
            
            # التحقق من أن المستخدم ليس بالفعل في المشروع
            if existing_user:
                existing_access = UserProjectAccess.query.filter_by(
                    project_id=project_id,
                    user_id=existing_user.id
                ).first()
                
                if existing_access and existing_access.is_active:
                    flash('هذا المستخدم موجود بالفعل في المشروع', 'warning')
                    return redirect(url_for('project_team', project_id=project.id))
            
            # إنشاء رمز دعوة فريد
            import secrets
            token = secrets.token_urlsafe(32)
            
            # إنشاء الدعوة
            invitation = ProjectInvitation(
                project_id=project_id,
                email=email,
                full_name=full_name,
                phone=phon_number,
                role_in_project=role,
                invited_by_id=current_user.id,
                token=token,
                expires_at=datetime.utcnow() + timedelta(days=7),
                existing_user_id=existing_user.id if existing_user else None
            )
            db.session.add(invitation)
            db.session.commit()
            
            # إرسال البريد الإلكتروني
            send_project_invitation_email(email, project, invitation, role, token)
            
            flash('تم إرسال الدعوة بنجاح', 'success')
            return redirect(url_for('project_team', project_id=project.id))
        
        return render_template('project/invite.html', project=project)


    @app.route('/invitation/<token>')
    def accept_invitation(token):
        """صفحة قبول الدعوة"""
        invitation = ProjectInvitation.query.filter_by(token=token).first_or_404()
        
        # التحقق من صلاحية الدعوة
        if invitation.status != 'pending':
            flash('هذه الدعوة منتهية الصلاحية أو تم استخدامها', 'warning')
            return redirect(url_for('index'))
        
        if invitation.expires_at < datetime.utcnow():
            invitation.status = 'expired'
            db.session.commit()
            flash('انتهت صلاحية هذه الدعوة', 'warning')
            return redirect(url_for('index'))
        
        project = invitation.project
        
        # إذا كان المستخدم مسجل الدخول بالفعل
        if current_user.is_authenticated:
            # التحقق من تطابق البريد
            if current_user.email != invitation.email:
                flash('هذه الدعوة موجهة لبريد إلكتروني آخر', 'danger')
                return redirect(url_for('dashboard'))
            
            # إضافة المستخدم للمشروع
            access = UserProjectAccess(
                user_id=current_user.id,
                project_id=invitation.project_id,
                role_in_project=invitation.role_in_project,
                display_name=invitation.full_name or current_user.full_name
            )
            db.session.add(access)
            
            # تحديث حالة الدعوة
            invitation.status = 'accepted'
            invitation.accepted_at = datetime.utcnow()
            db.session.commit()
            
            flash(f'تم انضمامك لمشروع "{project.title}" بنجاح', 'success')
            return redirect(url_for('project_view', project_id=project.id))
        
        # إذا لم يكن مسجل الدخول، نعرض له خيارات التسجيل أو إنشاء حساب
        return render_template('project/accept_invitation.html', 
                            invitation=invitation, 
                            project=project)


    @app.route('/invitation/<token>/register', methods=['POST'])
    def register_from_invitation(token):
        """إنشاء حساب جديد من خلال الدعوة"""
        invitation = ProjectInvitation.query.filter_by(token=token).first_or_404()
        
        if invitation.status != 'pending':
            flash('هذه الدعوة غير صالحة', 'warning')
            return redirect(url_for('index'))
        
        # إنشاء مستخدم جديد
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('الرجاء إدخال اسم المستخدم وكلمة المرور', 'warning')
            return redirect(url_for('accept_invitation', token=token))
        
        # التحقق من عدم وجود اسم المستخدم
        if User.query.filter_by(username=username).first():
            flash('اسم المستخدم موجود بالفعل', 'danger')
            return redirect(url_for('accept_invitation', token=token))
        
        # إنشاء المستخدم
        new_user = User(
            username=username,
            email=invitation.email,
            full_name=invitation.full_name or invitation.email.split('@')[0],
            role='worker',  # دور افتراضي
            is_active=True
        )
        new_user.password = password
        
        db.session.add(new_user)
        db.session.flush()  # للحصول على ID المستخدم
        
        # إضافة المستخدم للمشروع
        access = UserProjectAccess(
            user_id=new_user.id,
            project_id=invitation.project_id,
            role_in_project=invitation.role_in_project,
            display_name=invitation.full_name or new_user.full_name
        )
        db.session.add(access)
        
        # تحديث الدعوة
        invitation.status = 'accepted'
        invitation.accepted_at = datetime.utcnow()
        invitation.existing_user_id = new_user.id
        
        db.session.commit()
        
        # تسجيل الدخول تلقائياً
        login_user(new_user)
        
        flash(f'تم إنشاء حسابك وانضمامك لمشروع "{invitation.project.title}" بنجاح', 'success')
        return redirect(url_for('project_view', project_id=invitation.project_id))


    @app.route('/invitation/<token>/login', methods=['POST'])
    def login_from_invitation(token):
        """تسجيل الدخول لحساب موجود من خلال الدعوة"""
        invitation = ProjectInvitation.query.filter_by(token=token).first_or_404()
        
        if invitation.status != 'pending':
            flash('هذه الدعوة غير صالحة', 'warning')
            return redirect(url_for('index'))
        
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not email or not password:
            flash('الرجاء إدخال البريد الإلكتروني وكلمة المرور', 'warning')
            return redirect(url_for('accept_invitation', token=token))
        
        # التحقق من المستخدم
        user = User.query.filter_by(email=email).first()
        
        if not user or not user.verify_password(password):
            flash('البريد الإلكتروني أو كلمة المرور غير صحيحة', 'danger')
            return redirect(url_for('accept_invitation', token=token))
        
        # التحقق من تطابق البريد مع الدعوة
        if user.email != invitation.email:
            flash('هذه الدعوة موجهة لبريد إلكتروني آخر', 'danger')
            return redirect(url_for('accept_invitation', token=token))
        
        # إضافة المستخدم للمشروع
        access = UserProjectAccess(
            user_id=user.id,
            project_id=invitation.project_id,
            role_in_project=invitation.role_in_project,
            display_name=invitation.full_name or user.full_name
        )
        db.session.add(access)
        
        # تحديث الدعوة
        invitation.status = 'accepted'
        invitation.accepted_at = datetime.utcnow()
        invitation.existing_user_id = user.id
        
        db.session.commit()
        
        # تسجيل الدخول
        login_user(user)
        
        flash(f'تم انضمامك لمشروع "{invitation.project.title}" بنجاح', 'success')
        return redirect(url_for('project_view', project_id=invitation.project_id))


    @app.route('/project/<int:project_id>/invitations')
    @login_required
    @project_isolated_required
    @project_role_required(['project_manager', 'admin'])
    def project_invitations(project_id):
        """عرض الدعوات المرسلة للمشروع"""
        project = Project.query.get_or_404(project_id)
        
        invitations = ProjectInvitation.query.filter_by(project_id=project_id)\
            .order_by(ProjectInvitation.created_at.desc()).all()
        
        return render_template('project/invitations.html', 
                            project=project, 
                            invitations=invitations)


    @app.route('/project/<int:project_id>/invitation/<int:invitation_id>/cancel', methods=['POST'])
    @login_required
    @project_isolated_required
    @project_role_required(['project_manager', 'admin'])
    def cancel_invitation(project_id, invitation_id):
        """إلغاء دعوة معلقة"""
        invitation = ProjectInvitation.query.get_or_404(invitation_id)
        
        if invitation.project_id != project_id:
            abort(404)
        
        invitation.status = 'cancelled'
        db.session.commit()
        
        flash('تم إلغاء الدعوة', 'success')
        return redirect(url_for('project_invitations', project_id=project_id))


    @app.route('/project/<int:project_id>/invitation/<int:invitation_id>/resend', methods=['POST'])
    @login_required
    @project_isolated_required
    @project_role_required(['project_manager', 'admin'])
    def resend_invitation(project_id, invitation_id):
        """إعادة إرسال دعوة"""
        invitation = ProjectInvitation.query.get_or_404(invitation_id)
        
        if invitation.project_id != project_id:
            abort(404)
        
        if invitation.status != 'pending':
            flash('لا يمكن إعادة إرسال دعوة غير معلقة', 'warning')
            return redirect(url_for('project_invitations', project_id=project_id))
        
        # تجديد تاريخ الانتهاء
        invitation.expires_at = datetime.utcnow() + timedelta(days=7)
        db.session.commit()
        
        # إعادة إرسال البريد
        send_project_invitation_email(
            invitation.email, 
            invitation.full_name, 
            invitation.project, 
            invitation.role_in_project, 
            invitation.token
        )
        
        flash('تم إعادة إرسال الدعوة', 'success')
        return redirect(url_for('project_invitations', project_id=project_id))
    # app.py - صفحة عرض المشروع للمستخدم العادي

    @app.route('/user/project/<int:project_id>')
    @login_required
    @user_can_access_project
    def user_project_view(project_id):
        """عرض المشروع من وجهة نظر المستخدم العادي"""
        project = Project.query.get_or_404(project_id)
        
        # الحصول على دور المستخدم في هذا المشروع
        user_role = current_user.get_project_role(project_id)
        
        # جلب المهام المسندة للمستخدم في هذا المشروع فقط
        user_tasks = Task.query.filter_by(
            project_id=project_id,
            assigned_to_id=current_user.id
        ).order_by(Task.created_at.desc()).all()
        
        # إحصائيات للمستخدم
        total_tasks = len(user_tasks)
        completed_tasks = sum(1 for t in user_tasks if t.status == 'completed')
        in_progress_tasks = sum(1 for t in user_tasks if t.status == 'in_progress')
        pending_tasks = sum(1 for t in user_tasks if t.status == 'pending')
        
        # أعضاء الفريق الآخرين (للعرض فقط)
        team_members = UserProjectAccess.query.filter_by(
            project_id=project_id,
            is_active=True
        ).all()
        
        return render_template('user/project_view.html',
                            project=project,
                            user_role=user_role,
                            user_tasks=user_tasks,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            in_progress_tasks=in_progress_tasks,
                            pending_tasks=pending_tasks,
                            team_members=team_members)
    
    @app.route('/user/dashboard')
    @login_required
    def user_dashboard():
        """لوحة تحكم المستخدم العادي"""
        # المشاريع التي يمكن للمستخدم الوصول إليها
        accessible_projects = current_user.get_accessible_projects()
        
        # جميع مهام المستخدم
        all_tasks = Task.query.filter_by(assigned_to_id=current_user.id).all()
        
        # تجميع المهام حسب المشروع
        tasks_by_project = {}
        for task in all_tasks:
            if task.project_id not in tasks_by_project:
                tasks_by_project[task.project_id] = []
            tasks_by_project[task.project_id].append(task)
        
        # إحصائيات
        total_tasks = len(all_tasks)
        completed_tasks = sum(1 for t in all_tasks if t.status == 'completed')
        in_progress_tasks = sum(1 for t in all_tasks if t.status == 'in_progress')
        pending_tasks = sum(1 for t in all_tasks if t.status == 'pending')
        
        # الدعوات المعلقة
        pending_invitations = current_user.get_pending_invitations()
        
        return render_template('user/dashboard.html',
                            projects=accessible_projects,
                            tasks_by_project=tasks_by_project,
                            total_tasks=total_tasks,
                            completed_tasks=completed_tasks,
                            in_progress_tasks=in_progress_tasks,
                            pending_tasks=pending_tasks,
                            pending_invitations=pending_invitations)
    # ==================== إدارة المهام ====================
    # تحديث route إنشاء مهمة جديدة
    @app.route('/project/<int:project_id>/task/new', methods=['GET', 'POST'])
    @login_required
    @project_role_required(['manager', 'supervisor', 'admin','project_manager'])
    def new_task(project_id):
        """إنشاء مهمة جديدة في المشروع"""
        project = Project.query.get_or_404(project_id)
        
        # التحقق من أن المستخدم في فريق المشروع
        if not project.is_user_in_team(current_user.id) and current_user.role != 'admin':
            flash('ليس لديك صلاحية إنشاء مهام في هذا المشروع', 'danger')
            return redirect(url_for('project_view', project_id=project.id))
        
        form = TaskForm()
        
        # تعبئة قائمة المستخدمين المتاحين (فريق المشروع فقط)
        form.assigned_to_id.choices = [('', '-- اختر --')] + [
            (member.user.id, f"{member.user.full_name} ({member.role_in_project})") 
            for member in project.team_members.filter_by(is_active=True).all()
            if member.user.id != current_user.id
        ]
        
        if form.validate_on_submit():
            # إنشاء المهمة الجديدة
            task = Task(
                project_id=project_id,
                code=form.code.data,
                title=form.title.data,
                description=form.description.data,
                unit=form.unit.data,
                quantity=form.quantity.data or 0,
                unit_price=form.unit_price.data or 0,
                total_price=(form.quantity.data or 0) * (form.unit_price.data or 0),
                planned_start=form.planned_start.data,
                planned_end=form.planned_end.data,
                estimated_duration=form.estimated_duration.data,
                assigned_to_id=form.assigned_to_id.data or None,
                created_by_id=current_user.id,
                status=request.form.get('status', 'pending'),
                notes=form.notes.data
            )
            
            # التعامل مع المهمة الأم
            parent_task_id = request.form.get('parent_task_id')
            if parent_task_id:
                task.parent_task_id = int(parent_task_id)
            
            db.session.add(task)
            db.session.commit()
            
            # معالجة المرفقات إذا وجدت
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                for file in files:
                    if file and file.filename:
                        filename = secure_filename(file.filename)
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"task_{task.id}_{filename}")
                        file.save(file_path)
                        
                        attachment = TaskAttachment(
                            task_id=task.id,
                            filename=filename,
                            file_path=file_path,
                            uploaded_by_id=current_user.id
                        )
                        db.session.add(attachment)
                
                db.session.commit()
            
            # إرسال إشعار للمستخدم المعين
            if task.assigned_to_id:
                send_notification(
                    task.assigned_to_id,
                    'مهمة جديدة',
                    f'تم إسناد مهمة "{task.title}" إليك في مشروع "{project.title}"',
                    'task_assigned',
                    task_id=task.id,
                    project_id=project.id
                )
            
            # تسجيل النشاط
            log_activity(
                current_user.id,
                'create_task',
                f'أنشأ مهمة جديدة: {task.code} - {task.title}',
                task_id=task.id,
                project_id=project.id
            )
            
            flash('تم إنشاء المهمة بنجاح', 'success')
            return redirect(url_for('project_view', project_id=project.id))
        choices = [('', '-- اختر عضواً من الفريق --')]
        for member in project.team_members.filter_by(is_active=True).all():
            if member.user.id != current_user.id:
                role_name = {'supervisor': 'مشرف', 'delegate': 'مندوب', 'worker': 'فرد'}.get(member.role_in_project, member.role_in_project)
                choices.append((str(member.user.id), f"{member.display_name or member.user.full_name} ({role_name})"))

        form.assigned_to_id.choices = choices
        return render_template('task/new_task.html', form=form, project=project,now=datetime.utcnow())
    
    # @app.route('/project/<int:project_id>/invitation/<int:invitation_id>/cancel', methods=['POST'])
    # @login_required
    # @project_role_required(['manager'])
    # def cancel_invitation(project_id, invitation_id):
    #     """إلغاء دعوة معلقة"""
    #     invitation = ProjectInvitation.query.get_or_404(invitation_id)
        
    #     if invitation.project_id != project_id:
    #         abort(404)
        
    #     invitation.status = 'cancelled'
    #     db.session.commit()
        
    #     return jsonify({'success': True})


    @app.route('/api/project/<int:project_id>/team/member/<int:user_id>/permissions')
    @login_required
    @project_role_required(['project_manager'])
    def get_member_permissions(project_id, user_id):
        """الحصول على صلاحيات عضو في المشروع"""
        team_member = ProjectTeam.query.filter_by(
            project_id=project_id,
            user_id=user_id,
            is_active=True
        ).first_or_404()
        
        return jsonify(team_member.permissions)

    @app.route('/task/<int:task_id>')
    @login_required
    @can_access_task
    @subscription_required
    def task_detail(task_id):
        task = Task.query.get_or_404(task_id)
        
        # جلب التعليقات
        comments = TaskComment.query.filter_by(task_id=task_id).order_by(TaskComment.created_at.desc()).all()
        
        return render_template('task/task_detail.html', task=task, comments=comments,now=datetime.utcnow())
    
    @app.route('/task/<int:task_id>/start', methods=['POST'])
    @login_required
    @subscription_required
    def start_task(task_id):
        result = WorkflowManager.start_task(task_id, current_user.id)
        
        if result['success']:
            return jsonify({'success': True, 'message': result['message']})
        else:
            return jsonify({'success': False, 'message': result['message']}), 400
    
    @app.route('/task/<int:task_id>/complete', methods=['POST'])
    @login_required
    @subscription_required
    def complete_task(task_id):
        data = request.get_json() if request.is_json else {}
        result = WorkflowManager.complete_task(task_id, current_user.id, data)
        
        if result['success']:
            return jsonify({'success': True, 'message': result['message']})
        else:
            return jsonify({'success': False, 'message': result['message']}), 400
    
    @app.route('/task/<int:task_id>/assign', methods=['GET', 'POST'])
    @login_required
    @project_role_required(['manager', 'supervisor', 'admin','project_manager'])
    def assign_task(task_id):
        """إسناد مهمة لعضو في الفريق"""
        task = Task.query.get_or_404(task_id)
        project = task.project
        
        # التحقق من أن المستخدم في فريق المشروع
        if not project.is_user_in_team(current_user.id) and current_user.role != 'admin':
            flash('ليس لديك صلاحية إسناد مهام في هذا المشروع', 'danger')
            return redirect(url_for('task_detail', task_id=task.id))
        
        form = AssignTaskForm()
        
        # الحصول على أعضاء الفريق النشطين
        team_members = project.team_members.filter_by(is_active=True).all()
        
        # تعبئة خيارات المستخدمين
        form.user_id.choices = [('', '-- اختر --')] + [
            (member.user.id, f"{member.user.full_name} ({member.role_in_project})") 
            for member in team_members
            if member.user.id != current_user.id  # استبعاد المستخدم الحالي
        ]
        
        # توصية الذكاء الاصطناعي (اختياري)
        recommended_user = None
        if team_members:
            # منطق بسيط للتوصية: اختر من لديه أقل عدد من المهام النشطة
            min_tasks = float('inf')
            for member in team_members:
                active_tasks = Task.query.filter_by(
                    assigned_to_id=member.user.id,
                    status='in_progress'
                ).count()
                if active_tasks < min_tasks:
                    min_tasks = active_tasks
                    recommended_user = member.user
        
        if form.validate_on_submit():
            # تحديث المهمة
            task.assigned_to_id = form.user_id.data
            
            # إضافة تعليق تلقائي
            comment = TaskComment(
                task_id=task.id,
                user_id=current_user.id,
                comment=f"تم إسناد المهمة إلى {User.query.get(form.user_id.data).full_name}\nملاحظات: {form.notes.data or 'لا توجد'}"
            )
            db.session.add(comment)
            db.session.commit()
            
            # إرسال إشعارات
            if form.send_email.data:
                send_notification(
                    form.user_id.data,
                    'مهمة جديدة',
                    f'تم إسناد مهمة "{task.title}" إليك في مشروع "{project.title}"',
                    'task_assigned',
                    task_id=task.id,
                    project_id=project.id
                )
            
            # تسجيل النشاط
            log_activity(
                current_user.id,
                'assign_task',
                f'أسند مهمة {task.code} إلى {User.query.get(form.user_id.data).full_name}',
                task_id=task.id,
                project_id=project.id
            )
            
            flash('تم إسناد المهمة بنجاح', 'success')
            return redirect(url_for('task_detail', task_id=task.id))
        
        return render_template('task/assign_task.html',
                            form=form,
                            task=task,
                            project=project,
                            team_members=team_members,
                            recommended_user=recommended_user,
                            now=datetime.utcnow())
    
    @app.route('/task/<int:task_id>/comment', methods=['POST'])
    @login_required
    @subscription_required
    def add_comment(task_id):
        task = Task.query.get_or_404(task_id)
        
        comment_text = request.form.get('comment')
        if comment_text:
            comment = TaskComment(
                task_id=task_id,
                user_id=current_user.id,
                comment=comment_text
            )
            db.session.add(comment)
            db.session.commit()
            
            # إرسال إشعار لصاحب المهمة
            if task.assigned_to_id and task.assigned_to_id != current_user.id:
                send_notification(
                    task.assigned_to_id,
                    'تعليق جديد على مهمتك',
                    f'{current_user.full_name} علق على مهمتك: {task.title}',
                    'comment',
                    task_id=task.id,
                    project_id=task.project_id
                )
            
            flash('تم إضافة التعليق', 'success')
        
        return redirect(url_for('task_detail', task_id=task_id))
    
    # ==================== الإشعارات ====================
    
    @app.route('/notifications')
    @login_required
    def notifications():
        notifications = Notification.query.filter_by(
            user_id=current_user.id
        ).order_by(Notification.created_at.desc()).all()
        
        return render_template('notifications.html', notifications=notifications,now=datetime.utcnow())
    
    @app.route('/notifications/<int:notification_id>/read', methods=['POST'])
    @login_required
    def mark_notification_read(notification_id):
        notification = Notification.query.get_or_404(notification_id)
        
        if notification.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        notification.mark_as_read()
        return jsonify({'success': True})
    
    @app.route('/notifications/read-all', methods=['POST'])
    @login_required
    def mark_all_notifications_read():
        notifications = Notification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).all()
        
        for notification in notifications:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
        
        db.session.commit()
        return jsonify({'success': True, 'count': len(notifications)})
    
    @app.route('/api/unread-count')
    @login_required
    def unread_notifications_count():
        count = current_user.get_unread_notifications_count()
        return jsonify({'count': count})
    
    # ==================== الملف الشخصي ====================
    
    @app.route('/profile', methods=['GET', 'POST'])
    @login_required
    def profile():
        form = ProfileForm(obj=current_user)
        
        if form.validate_on_submit():
            # التحقق من كلمة المرور الحالية إذا تم تغييرها
            if form.new_password.data:
                if not current_user.verify_password(form.current_password.data):
                    flash('كلمة المرور الحالية غير صحيحة', 'danger')
                    return render_template('profile.html', form=form)
                current_user.password = form.new_password.data
            
            current_user.full_name = form.full_name.data
            current_user.phone = form.phone.data
            
            # معالجة الصورة الشخصية إذا تم رفعها
            if request.files.get('profile_image'):
                picture_file = request.files['profile_image']
                if picture_file.filename:
                    picture_path = save_picture(picture_file)
                    current_user.profile_image = picture_path
            
            db.session.commit()
            flash('تم تحديث الملف الشخصي', 'success')
            return redirect(url_for('profile'))
        
        return render_template('profile.html', form=form,now=datetime.utcnow())
    
    @app.route('/profile/settings', methods=['GET', 'POST'])
    @login_required
    def profile_settings():
        form = ProfileForm()  # إنشاء نموذج فارغ
        
        if request.method == 'POST':
            # التحقق من أي إجراء تم إرساله
            action = request.form.get('action')
            
            if action == 'update_profile':
                # تحديث المعلومات الشخصية
                current_user.full_name = request.form.get('full_name', current_user.full_name)
                current_user.phone = request.form.get('phone', current_user.phone)
                current_user.job_title = request.form.get('job_title', current_user.job_title)
                current_user.department = request.form.get('department', current_user.department)
                
                # معالجة الصورة الشخصية
                if 'profile_image' in request.files:
                    file = request.files['profile_image']
                    if file and file.filename:
                        picture_path = save_picture(file)
                        current_user.profile_image = picture_path
                
                db.session.commit()
                flash('تم تحديث المعلومات الشخصية', 'success')
                
            elif action == 'update_locale':
                # تحديث إعدادات المنطقة الزمنية
                current_user.timezone = request.form.get('timezone', 'Asia/Riyadh')
                current_user.date_format = request.form.get('date_format', 'Y-m-d')
                current_user.time_format = request.form.get('time_format', '24')
                current_user.week_start = request.form.get('week_start', 'saturday')
                db.session.commit()
                flash('تم تحديث إعدادات المنطقة الزمنية', 'success')
                
            elif action == 'update_notifications':
                # تحديث إعدادات الإشعارات
                settings = {
                    'email_notifications': request.form.get('email_notifications') == 'on',
                    'browser_notifications': request.form.get('browser_notifications') == 'on',
                    'mobile_notifications': request.form.get('mobile_notifications') == 'on',
                    'task_reminders': request.form.get('task_reminders') == 'on',
                    'project_notifications': request.form.get('project_notifications') == 'on',
                    'comment_notifications': request.form.get('comment_notifications') == 'on',
                    'daily_reminder_time': request.form.get('daily_reminder_time', '09:00')
                }
                current_user.notification_settings = settings
                db.session.commit()
                flash('تم تحديث إعدادات الإشعارات', 'success')
                
            elif action == 'change_password':
                # تغيير كلمة المرور
                current_password = request.form.get('current_password')
                new_password = request.form.get('new_password')
                confirm_password = request.form.get('confirm_password')
                
                if not current_user.verify_password(current_password):
                    flash('كلمة المرور الحالية غير صحيحة', 'danger')
                elif new_password != confirm_password:
                    flash('كلمات المرور الجديدة غير متطابقة', 'danger')
                elif len(new_password) < 8:
                    flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل', 'danger')
                else:
                    current_user.password = new_password
                    db.session.commit()
                    flash('تم تغيير كلمة المرور بنجاح', 'success')
            
            return redirect(url_for('profile_settings'))
        
        # بيانات إضافية للقالب
        two_factor_qr = generate_qr_code(f"otpauth://totp/ProjectManagement:{current_user.email}?secret=SECRET&issuer=ProjectManagement") if not current_user.two_factor_enabled else None
        backup_codes = ['ABCD-1234', 'EFGH-5678', 'IJKL-9012', 'MNOP-3456'] if current_user.two_factor_enabled else []
        
        return render_template('profile_settings.html', 
                            form=form,
                            two_factor_qr=two_factor_qr,
                            backup_codes=backup_codes,
                            now=datetime.utcnow())
    

    @app.route('/project/templates')
    @login_required
    def list_templates():
        """عرض قائمة القوالب المتاحة للتحميل"""
        from template_generator import ProjectTemplateGenerator
        
        generator = ProjectTemplateGenerator()
        formats = generator.get_available_formats()
        
        return render_template('projects/templates_list.html', formats=formats,now=datetime.utcnow())


    @app.route('/project/template/download/<format>')
    @login_required
    def download_template(format):
        """تحميل قالب بالصيغة المطلوبة"""
        from template_generator import ProjectTemplateGenerator
        
        try:
            include_examples = request.args.get('examples', 'true').lower() == 'true'
            language = request.args.get('lang', 'ar')
            
            generator = ProjectTemplateGenerator()
            result = generator.generate_template(format, include_examples, language)
            
            if result['success']:
                return send_file(
                    result['filepath'],
                    as_attachment=True,
                    download_name=result['filename'],
                    mimetype=_get_mimetype(format)
                )
            else:
                flash('حدث خطأ في توليد القالب', 'danger')
                return redirect(url_for('list_templates'))
                
        except Exception as e:
            flash(f'خطأ: {str(e)}', 'danger')
            return redirect(url_for('list_templates'))


    @app.route('/project/template/preview/<format>')
    @login_required
    def preview_template(format):
        """معاينة القالب قبل التحميل"""
        from template_generator import ProjectTemplateGenerator
        
        generator = ProjectTemplateGenerator()
        result = generator.generate_template(format, include_examples=True)
        
        return render_template('projects/template_preview.html', 
                            template=result,
                            format=format,now=datetime.utcnow())


    def _get_mimetype(format: str) -> str:
        """الحصول على MIME type للصيغة"""
        mimetypes = {
            'excel': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'word': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'csv': 'text/csv',
            'json': 'application/json',
            'pdf': 'application/pdf',
            'html': 'text/html'
        }
        return mimetypes.get(format, 'application/octet-stream')
    # ==================== نظام الدفع ====================
    
    # متابعة app.py - الجزء الثاني

    @app.route('/subscribe')
    @login_required
    def subscribe():
        """صفحة الاشتراك"""
        plans = [
            {'id': 'basic', 'name': 'Basic', 'price': 29, 'interval': 'شهري', 
            'features': ['5 مشاريع', '10 مستخدمين', 'تخزين 10 جيجابايت', 'دعم أساسي']},
            {'id': 'pro', 'name': 'Pro', 'price': 79, 'interval': 'شهري',
            'features': ['مشاريع غير محدودة', '50 مستخدمين', 'تخزين 50 جيجابايت', 'دعم priorit', 'تقارير متقدمة']},
            {'id': 'enterprise', 'name': 'Enterprise', 'price': 199, 'interval': 'شهري',
            'features': ['مشاريع غير محدودة', 'مستخدمين غير محدودين', 'تخزين 200 جيجابايت', 'دعم VIP', 'API مخصص']}
        ]
        
        return render_template('subscribe.html', plans=plans, stripe_public_key=app.config['STRIPE_PUBLIC_KEY'])

    @app.route('/create-checkout-session', methods=['POST'])
    @login_required
    def create_checkout_session():
        """إنشاء جلسة دفع عبر Stripe"""
        try:
            plan_id = request.form.get('plan_id')
            plans = {
                'basic': {'price': 2900, 'name': 'Basic Plan'},  # بالسنت
                'pro': {'price': 7900, 'name': 'Pro Plan'},
                'enterprise': {'price': 19900, 'name': 'Enterprise Plan'}
            }
            
            if plan_id not in plans:
                return jsonify({'error': 'خطأ في اختيار الخطة'}), 400
            
            # إنشاء جلسة الدفع
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'unit_amount': plans[plan_id]['price'],
                        'product_data': {
                            'name': plans[plan_id]['name'],
                        },
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=url_for('payment_success', plan_id=plan_id, _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
                cancel_url=url_for('payment_cancel', _external=True),
                client_reference_id=current_user.id
            )
            
            return redirect(checkout_session.url, code=303)
        except Exception as e:
            flash(f'حدث خطأ في عملية الدفع: {str(e)}', 'danger')
            return redirect(url_for('subscribe'))

    @app.route('/payment-success')
    @login_required
    def payment_success():
        """معالجة نجاح الدفع"""
        session_id = request.args.get('session_id')
        plan_id = request.args.get('plan_id')
        
        if session_id:
            try:
                # التحقق من صحة الجلسة
                checkout_session = stripe.checkout.Session.retrieve(session_id)
                
                if checkout_session.payment_status == 'paid':
                    # تحديث حالة المستخدم
                    current_user.is_paid = True
                    current_user.subscription_end = datetime.utcnow() + timedelta(days=30)  # اشتراك شهر
                    
                    # تسجيل الاشتراك
                    subscription = Subscription(
                        user_id=current_user.id,
                        plan=plan_id,
                        amount=checkout_session.amount_total / 100,  # تحويل من سنت
                        currency=checkout_session.currency,
                        stripe_subscription_id=session_id,
                        stripe_customer_id=checkout_session.customer,
                        status='active',
                        end_date=datetime.utcnow() + timedelta(days=30)
                    )
                    db.session.add(subscription)
                    db.session.commit()
                    
                    flash('تم الدفع بنجاح! شكراً لاشتراكك', 'success')
                    
                    # إرسال إشعار ترحيبي
                    send_notification(
                        current_user.id,
                        'مرحباً بك في الباقة المدفوعة',
                        'تم تفعيل اشتراكك بنجاح. يمكنك الآن الاستفادة من جميع الميزات المتقدمة.',
                        'success'
                    )
            except Exception as e:
                flash(f'حدث خطأ في تأكيد الدفع: {str(e)}', 'danger')
        
        return redirect(url_for('dashboard'))

    @app.route('/payment-cancel')
    @login_required
    def payment_cancel():
        """معالجة إلغاء الدفع"""
        flash('تم إلغاء عملية الدفع. يمكنك المحاولة مرة أخرى في أي وقت.', 'info')
        return redirect(url_for('subscribe'))

    @app.route('/webhook/stripe', methods=['POST'])
    def stripe_webhook():
        """معالجة webhook من Stripe"""
        payload = request.get_data(as_text=True)
        sig_header = request.headers.get('Stripe-Signature')
        
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, app.config['STRIPE_WEBHOOK_SECRET']
            )
        except ValueError:
            return 'Invalid payload', 400
        except stripe.error.SignatureVerificationError:
            return 'Invalid signature', 400
        
        # معالجة الأحداث
        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            user_id = session.get('client_reference_id')
            if user_id:
                user = User.query.get(user_id)
                if user:
                    user.is_paid = True
                    user.subscription_end = datetime.utcnow() + timedelta(days=30)
                    db.session.commit()
        
        return 'Success', 200

    # ==================== API للتقارير والإحصائيات ====================

    @app.route('/api/project/<int:project_id>/stats')
    @login_required
    @can_access_project
    def project_stats(project_id):
        """إحصائيات المشروع بصيغة JSON"""
        project = Project.query.get_or_404(project_id)
        
        # إحصائيات المهام
        total_tasks = Task.query.filter_by(project_id=project_id).count()
        completed_tasks = Task.query.filter_by(project_id=project_id, status='completed').count()
        in_progress_tasks = Task.query.filter_by(project_id=project_id, status='in_progress').count()
        pending_tasks = Task.query.filter_by(project_id=project_id, status='pending').count()
        
        # إحصائيات التكاليف
        total_planned_cost = db.session.query(db.func.sum(Task.total_price)).filter_by(project_id=project_id).scalar() or 0
        total_actual_cost = db.session.query(db.func.sum(Task.total_amount_done)).filter_by(project_id=project_id).scalar() or 0
        
        # توزيع المهام حسب المسؤول
        tasks_by_assignee = db.session.query(
            User.full_name, db.func.count(Task.id)
        ).join(Task, User.id == Task.assigned_to_id)\
        .filter(Task.project_id == project_id)\
        .group_by(User.id).all()
        
        return jsonify({
            'project': {
                'id': project.id,
                'title': project.title,
                'progress': project.progress_percentage,
                'status': project.status
            },
            'tasks': {
                'total': total_tasks,
                'completed': completed_tasks,
                'in_progress': in_progress_tasks,
                'pending': pending_tasks,
                'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
            },
            'costs': {
                'planned': total_planned_cost,
                'actual': total_actual_cost,
                'variance': total_planned_cost - total_actual_cost
            },
            'tasks_by_assignee': [{'name': name, 'count': count} for name, count in tasks_by_assignee]
        })

    @app.route('/api/tasks/upcoming')
    @login_required
    def upcoming_tasks():
        """المهام القادمة (للعرض في لوحة التحكم)"""
        days = request.args.get('days', 7, type=int)
        
        # تحديد المهام حسب دور المستخدم
        if current_user.role == 'admin':
            tasks = Task.query.filter(
                Task.planned_start <= datetime.utcnow() + timedelta(days=days),
                Task.planned_start >= datetime.utcnow(),
                Task.status == 'pending'
            ).order_by(Task.planned_start).limit(20).all()
        elif current_user.role == 'project_manager':
            tasks = Task.query.join(Project).filter(
                Project.manager_id == current_user.id,
                Task.planned_start <= datetime.utcnow() + timedelta(days=days),
                Task.planned_start >= datetime.utcnow(),
                Task.status == 'pending'
            ).order_by(Task.planned_start).limit(20).all()
        else:
            tasks = Task.query.filter(
                Task.assigned_to_id == current_user.id,
                Task.planned_start <= datetime.utcnow() + timedelta(days=days),
                Task.planned_start >= datetime.utcnow(),
                Task.status == 'pending'
            ).order_by(Task.planned_start).limit(20).all()
        
        return jsonify([{
            'id': t.id,
            'title': t.title,
            'project': t.project.title,
            'planned_start': t.planned_start.strftime('%Y-%m-%d %H:%M') if t.planned_start else None,
            'code': t.code
        } for t in tasks])

# ==================== إدارة المستخدمين (للمدير العام) ====================

    @app.route('/admin/users')
    @login_required
    @role_required('admin')
    def admin_users():
        """إدارة المستخدمين (للمدير العام)"""
        users = User.query.order_by(User.created_at.desc()).all()
        return render_template('admin/users.html', users=users,now=datetime.utcnow())

    @app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
    @login_required
    @role_required('admin')
    def admin_edit_user(user_id):
        """تعديل مستخدم (للمدير العام)"""
        user = User.query.get_or_404(user_id)
        
        if request.method == 'POST':
            user.role = request.form.get('role')
            user.is_active = request.form.get('is_active') == 'on'
            user.is_paid = request.form.get('is_paid') == 'on'
            
            # تحديث تاريخ انتهاء الاشتراك
            subscription_days = request.form.get('subscription_days', type=int)
            if subscription_days:
                user.subscription_end = datetime.utcnow() + timedelta(days=subscription_days)
                user.is_paid = True
            
            db.session.commit()
            flash(f'تم تحديث بيانات المستخدم {user.username}', 'success')
            return redirect(url_for('admin_users'))
        
        return render_template('admin/edit_user.html', user=user,now=datetime.utcnow())

    @app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
    @login_required
    @role_required('admin')
    def admin_delete_user(user_id):
        """حذف مستخدم (للمدير العام)"""
        if user_id == current_user.id:
            flash('لا يمكن حذف المستخدم الحالي', 'danger')
            return redirect(url_for('admin_users'))
        
        user = User.query.get_or_404(user_id)
        username = user.username
        
        db.session.delete(user)
        db.session.commit()
        
        flash(f'تم حذف المستخدم {username}', 'success')
        return redirect(url_for('admin_users'))

    # ==================== معالجة الأخطاء ====================

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html',now=datetime.utcnow()), 404

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html',now=datetime.utcnow()), 403

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html',now=datetime.utcnow()), 500

    # ==================== أوامر CLI ====================

    @app.cli.command("create-admin")
    def create_admin():
        """إنشاء مستخدم مدير"""
        import getpass
        
        username = input("Username: ")
        email = input("Email: ")
        password = getpass.getpass("Password: ")
        
        admin = User(
            username=username,
            email=email,
            full_name="System Administrator",
            role="admin",
            is_paid=True,
            trial_end=datetime.utcnow() + timedelta(days=3650)  # 10 سنوات
        )
        admin.password = password
        
        db.session.add(admin)
        db.session.commit()
        
        print(f"Admin user '{username}' created successfully!")

    @app.cli.command("check-subscriptions")
    def check_subscriptions_command():
        """التحقق من انتهاء الاشتراكات"""
        check_subscription_expiry()
        print("Subscription check completed.")

    @app.cli.command("send-reminders")
    def send_reminders_command():
        """إرسال تذكيرات المهام"""
        send_task_reminders()
        print("Reminders sent successfully.")

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
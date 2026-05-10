"""
routes/__init__.py - تهيئة المسارات
"""
from flask import Blueprint

# إنشاء Blueprints
auth_bp = Blueprint('auth', __name__, template_folder='templates')
dashboard_bp = Blueprint('dashboard', __name__, template_folder='templates')
platform_bp = Blueprint('platform', __name__, template_folder='templates')
company_bp = Blueprint('company', __name__, template_folder='templates')
project_bp = Blueprint('projects', __name__, template_folder='templates')
task_bp = Blueprint('tasks', __name__, template_folder='templates')
document_bp = Blueprint('document', __name__, template_folder='templates')
employee_bp = Blueprint('employee', __name__, template_folder='templates')
admin_bp = Blueprint('admin', __name__, template_folder='templates')
tracking_bp = Blueprint('tracking', __name__, template_folder='templates')
communication_bp = Blueprint('communication', __name__, template_folder='templates')
upload_bp = Blueprint('upload', __name__, template_folder='templates')
template_bp = Blueprint('template', __name__, template_folder='templates')
notifications_bp = Blueprint('notifications', __name__, template_folder='templates')
primavera_bp = Blueprint('primavera', __name__, template_folder='templates')
enterprise_bp = Blueprint('enterprise', __name__, template_folder='templates')
codes_bp = Blueprint('codes', __name__, template_folder='templates')
resource_bp = Blueprint('resource', __name__, template_folder='templates')
supplier_bp = Blueprint('supplier', __name__, template_folder='templates')
ai_bp = Blueprint('ai', __name__,template_folder='templates')
delivery_bp=Blueprint('delivery', __name__,template_folder='templates')
attachment_bp = Blueprint('attachments', __name__, template_folder='templates')
client_bp = Blueprint('client', __name__, template_folder='templates')
consultant_bp = Blueprint('consultant', __name__, template_folder='templates')
# استيراد المسارات
from . import auth_routes, dashboard_routes, project_routes, document_routes,  admin_routes, task_routes  #, report_routes,api_routes
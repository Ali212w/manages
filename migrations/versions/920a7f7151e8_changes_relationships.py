"""changes relationships

Revision ID: 920a7f7151e8
Revises: c4ae965ef1d1
Create Date: 2026-03-24 01:54:40.757873

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = '920a7f7151e8'
down_revision = 'c4ae965ef1d1'
branch_labels = None
depends_on = None


def get_foreign_keys(table_name):
    """الحصول على أسماء constraints الموجودة في الجدول"""
    conn = op.get_bind()
    inspector = inspect(conn)
    fks = inspector.get_foreign_keys(table_name)
    return [fk['name'] for fk in fks]


def upgrade():
    # الحصول على قائمة constraints الموجودة
    existing_fks = get_foreign_keys('projects')
    
    with op.batch_alter_table('projects', schema=None) as batch_op:
        # حذف constraints القديمة إذا كانت موجودة
        if 'fk_projects_client_id_clients' in existing_fks:
            batch_op.drop_constraint('fk_projects_client_id_clients', type_='foreignkey')
        if 'client_id' in existing_fks:
            batch_op.drop_constraint('client_id', type_='foreignkey')
        
        if 'fk_projects_consultant_id_consultants' in existing_fks:
            batch_op.drop_constraint('fk_projects_consultant_id_consultants', type_='foreignkey')
        if 'consultant_id' in existing_fks:
            batch_op.drop_constraint('consultant_id', type_='foreignkey')
        
        if 'fk_projects_supplier_id_suppliers' in existing_fks:
            batch_op.drop_constraint('fk_projects_supplier_id_suppliers', type_='foreignkey')
        if 'supplier_id' in existing_fks:
            batch_op.drop_constraint('supplier_id', type_='foreignkey')
        
        # إنشاء constraints جديدة
        batch_op.create_foreign_key(
            'fk_projects_client_id_users',
            'users',
            ['client_id'],
            ['id'],
            ondelete='SET NULL'
        )
        
        batch_op.create_foreign_key(
            'fk_projects_consultant_id_users',
            'users',
            ['consultant_id'],
            ['id'],
            ondelete='SET NULL'
        )
        
        batch_op.create_foreign_key(
            'fk_projects_supplier_id_users',
            'users',
            ['supplier_id'],
            ['id'],
            ondelete='SET NULL'
        )


def downgrade():
    # الحصول على قائمة constraints الموجودة
    existing_fks = get_foreign_keys('projects')
    
    with op.batch_alter_table('projects', schema=None) as batch_op:
        # حذف constraints الجديدة
        if 'fk_projects_client_id_users' in existing_fks:
            batch_op.drop_constraint('fk_projects_client_id_users', type_='foreignkey')
        
        if 'fk_projects_consultant_id_users' in existing_fks:
            batch_op.drop_constraint('fk_projects_consultant_id_users', type_='foreignkey')
        
        if 'fk_projects_supplier_id_users' in existing_fks:
            batch_op.drop_constraint('fk_projects_supplier_id_users', type_='foreignkey')
        
        # إعادة إنشاء constraints القديمة
        batch_op.create_foreign_key(
            'fk_projects_client_id_clients',
            'clients',
            ['client_id'],
            ['id'],
            ondelete='SET NULL'
        )
        
        batch_op.create_foreign_key(
            'fk_projects_consultant_id_consultants',
            'consultants',
            ['consultant_id'],
            ['id'],
            ondelete='SET NULL'
        )
        
        batch_op.create_foreign_key(
            'fk_projects_supplier_id_suppliers',
            'suppliers',
            ['supplier_id'],
            ['id'],
            ondelete='SET NULL'
        )
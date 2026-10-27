"""Self profiles, explicit publication snapshots and private normalized rasters."""
from alembic import op
import sqlalchemy as sa
revision = '0015_persistent_profiles'
down_revision = '0014_staff_enrollment'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('profile_json', sa.Text(), nullable=False, server_default='{}'))
    op.add_column('users', sa.Column('profile_revision', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('profile_photo_id', sa.String(64), nullable=True))
    op.add_column('dx_physician_profiles', sa.Column('published_json', sa.Text(), nullable=True))
    op.create_table('profile_photos',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('owner_id', sa.String(64), sa.ForeignKey('users.id'), unique=True, nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))


def downgrade():
    op.drop_table('profile_photos')
    op.drop_column('dx_physician_profiles', 'published_json')
    op.drop_column('users', 'profile_photo_id')
    op.drop_column('users', 'profile_revision')
    op.drop_column('users', 'profile_json')

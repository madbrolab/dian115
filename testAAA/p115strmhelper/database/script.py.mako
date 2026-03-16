"""
${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Branch Labels: ${branch_labels | comma,n}
Depends On: ${depends_on | comma,n}
Create Date: ${create_date}

"""
<%
has_ops = 'op.' in upgrades or 'op.' in downgrades
%>
% if has_ops:
from alembic import op
import sqlalchemy as sa
% endif
${imports if imports else ""}

# revision identifiers, used by Alembic.
db_version = '${config.attributes.get("version", "")}'
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
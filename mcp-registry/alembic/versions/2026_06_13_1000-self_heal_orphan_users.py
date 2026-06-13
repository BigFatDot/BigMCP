"""self_heal_orphan_users

Revision ID: self_heal_orphan_users
Revises: add_lemonsqueezy_webhook_events
Create Date: 2026-06-13 10:00

Data-only migration — Sprint 3.A.

Repairs every active user account that does not have any
``organization_members`` row. For each orphan we mint a personal
``Organization`` (organization_type='personal', slug='org-<user_id>')
plus an ``organization_members`` row with role=ADMIN.

This mirrors the auto-provision performed by ``POST /auth/register``
since the very first SaaS deploy, and the runtime self-heal added in
``POST /auth/login`` in the same sprint. The migration closes the gap
for users created before either of those code paths existed (Cerema
dry-run vintage), so that the next time they log in they don't trip
the legacy 500 even on a worker that hasn't yet picked up the
runtime self-heal.

The migration is **idempotent**: re-running it produces zero inserts
because the orphan-query joins on ``organization_members`` and only
emits rows where the LEFT JOIN is NULL.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op


revision: str = "self_heal_orphan_users"
down_revision: Union[str, None] = "add_lemonsqueezy_webhook_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1) Collect the orphan users in a single round-trip. We pick the
    #    deterministic ordering by created_at so the slugs / org names
    #    end up stable if this ever needs to be re-run after a partial
    #    failure mid-deploy.
    orphans = bind.execute(
        sa.text(
            """
            SELECT u.id AS user_id, u.email, u.name
            FROM users u
            LEFT JOIN organization_members om ON om.user_id = u.id
            WHERE om.id IS NULL
              AND COALESCE(u.status, 'active') = 'active'
            ORDER BY u.created_at ASC
            """
        )
    ).fetchall()

    if not orphans:
        return

    # 2) For each orphan, INSERT the personal org + the ADMIN
    #    membership inside the same transaction. We use parametrised
    #    statements rather than the ORM to keep the migration free of
    #    application-model imports (those drift over time).
    insert_org = sa.text(
        """
        INSERT INTO organizations (id, name, slug, organization_type, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :slug, 'personal', NOW(), NOW())
        RETURNING id
        """
    )
    insert_member = sa.text(
        """
        INSERT INTO organization_members
            (id, user_id, organization_id, role, created_at, updated_at)
        VALUES
            (gen_random_uuid(), :user_id, :org_id, 'admin', NOW(), NOW())
        """
    )

    for row in orphans:
        user_id = row.user_id
        display = row.name or row.email
        org_name = f"{display}'s Organization"
        slug = f"org-{user_id}"

        org_id = bind.execute(
            insert_org, {"name": org_name, "slug": slug}
        ).scalar_one()

        bind.execute(
            insert_member, {"user_id": user_id, "org_id": org_id}
        )


def downgrade() -> None:
    # No-op: this is a data repair, the personal orgs we created are
    # indistinguishable from the ones produced by /auth/register and
    # we don't want to drop user-owned tenants on a rollback.
    pass

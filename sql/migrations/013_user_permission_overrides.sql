-- Per-user permission overrides: individual grants and revokes layered over
-- the user's role bundle, so an admin can adjust exactly one person's access
-- without inventing a whole role. Effective permissions are
-- (bundle + grants) - revokes, still subject to the role-rank floor each
-- permission requires (see PERMISSION_MIN_ROLE in obs/auth.py).
CREATE TABLE IF NOT EXISTS obs.user_permission_overrides (
    user_id bigint PRIMARY KEY REFERENCES obs.users(user_id) ON DELETE CASCADE,
    grants jsonb NOT NULL DEFAULT '[]'::jsonb,
    revokes jsonb NOT NULL DEFAULT '[]'::jsonb,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Custom roles: a named permission bundle layered over a base access level.
-- users.role remains the enforcement level (viewer/operator/admin); role_name
-- records which bundle the user was assigned, and bundle permissions drive
-- the newer permission-checked endpoints and the console's menus.
ALTER TABLE obs.users ADD COLUMN IF NOT EXISTS role_name text;

CREATE TABLE IF NOT EXISTS obs.roles (
    name text PRIMARY KEY,
    base_level text NOT NULL CHECK (base_level IN ('viewer', 'operator', 'admin')),
    permissions jsonb NOT NULL DEFAULT '[]'::jsonb,
    description text,
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE obs.saved_views (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 user_id bigint NOT NULL REFERENCES obs.users(user_id) ON DELETE CASCADE,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 80),
 filters jsonb NOT NULL DEFAULT '{}',
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(user_id,name)
);
GRANT SELECT,INSERT,UPDATE,DELETE ON obs.saved_views TO obs_app;
GRANT USAGE,SELECT ON SEQUENCE obs.saved_views_id_seq TO obs_app;
GRANT SELECT ON obs.saved_views TO obs_ro;

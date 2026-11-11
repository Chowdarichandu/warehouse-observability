-- Dev mailbox (SPEC §13): in demo mode, account emails (invites and password
-- resets) are captured here instead of being sent, and admins read them at
-- /dev/mailbox. The table stays empty in live mode.
CREATE TABLE obs.dev_mailbox (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recipient text NOT NULL,
    subject text NOT NULL,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX dev_mailbox_created_idx ON obs.dev_mailbox(created_at DESC);
GRANT SELECT, INSERT, UPDATE, DELETE ON obs.dev_mailbox TO obs_app;
GRANT USAGE, SELECT ON SEQUENCE obs.dev_mailbox_id_seq TO obs_app;

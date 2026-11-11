-- Prevent concurrent dispatchers from queuing the same in-flight notification.
CREATE UNIQUE INDEX notification_outbox_inflight_thread_key_idx
    ON obs.notification_outbox(thread_key)
    WHERE thread_key IS NOT NULL AND state IN ('pending', 'sending');

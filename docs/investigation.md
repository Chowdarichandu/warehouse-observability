# Operator investigation

Pipeline runs has account-private saved views. Name the current filters to save tenant, status, source, load type, failure stage/class, search, sort and time range. Selecting a view restores its shareable URL parameters. Views follow your authenticated account across browsers, are limited to 30 per account, and can be deleted by their owner. Read-only viewers can manage their own views; this does not grant pipeline mutation rights. Every save/delete checks session/CSRF and writes audit history. Search and names are redacted before persistence.

Open a run and choose a previous run in **Compare runs**. The comparison displays recorded status, duration, queue delay, rows/bytes, Airbyte attempts, error class and stream counts. Change is current minus baseline. Missing metrics remain unknown; a different pipeline/tenant triggers a comparability notice. The baseline key is part of the URL for sharing. Neither run is changed.

The log viewer searches redacted content, navigates next/previous matching lines, optionally hides nonmatching lines, wraps lines and downloads the redacted log. Search/filter state is in the URL. Original line numbers remain visible when filtering; large logs use linear matching rather than repeated full-list searches.

**Activity** combines recorded run lifecycle events, alert lifecycle events, onboarding progress, durable operator outcomes and data-quality results. Filter by tenant and the shared time range. Run detail embeds its execution's events plus nearby tenant context; an alert or quality result is not claimed to belong to that particular run. The newest 200 events are returned, with an explicit truncation notice. Timestamps come from recorded events, not inferred causal ordering. Operation payloads, credentials and actor emails are excluded; text is redacted before display.

All views use the console's authenticated API and work offline with seeded demo data. Polling/SSE refresh the evidence. Theme, keyboard navigation and reduced-motion preferences continue to apply.

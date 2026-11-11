# Hosting the web console behind an API proxy

The web app is a static Vite build. It can be served from nginx or a CDN when the same origin proxies `/api` requests to the API service. A static deployment does not host PostgreSQL, the API, the collector or the worker.

Configure `CONSOLE_URL` to the exact browser-facing origin, such as `https://console.example.com`. Keep API rewrites ahead of the single-page application fallback. Preserve streaming responses for `/api/stream`; the proxy must not buffer or close server-sent event connections.

Login and authenticated mutations require the configured origin and CSRF checks. Cookies remain Secure and HttpOnly. Do not put API credentials or upstream Airflow, Airbyte or warehouse secrets in frontend environment variables.

For a read-only reachability check, `/api/config` and `/api/health` return JSON. An unsigned request to `/api/me` returns HTTP 401. If an API path returns the SPA document, correct the proxy rewrite order or destination. If the API returns a gateway error, check the API service and its database connection.

Use [deployment](deployment.md) for the API, database and worker services. Use [release checklist](release-checklist.md) to verify a hosted environment before promotion.

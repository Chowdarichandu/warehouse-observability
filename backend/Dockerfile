FROM postgres:16.9-bookworm AS postgres_tools
FROM python:3.11.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 liblz4-1 libzstd1 && rm -rf /var/lib/apt/lists/*
COPY --from=postgres_tools /usr/lib/postgresql/16/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=postgres_tools /usr/lib/postgresql/16/bin/pg_restore /usr/local/bin/pg_restore
COPY backend/ /app/
COPY sql/ /app/sql/
COPY deploy/certs/ /app/certs/
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home obs
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "obs.entrypoint", "--"]
CMD ["uvicorn", "obs.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM postgres:16.15-bookworm@sha256:5264710be20f409750ac6dc4e5706dcef929c87e241605463f0f9aefa932a8d9 AS postgres_tools
FROM python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 liblz4-1 libzstd1 && rm -rf /var/lib/apt/lists/*
COPY --from=postgres_tools /usr/lib/postgresql/16/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=postgres_tools /usr/lib/postgresql/16/bin/pg_restore /usr/local/bin/pg_restore
COPY backend/ /app/
COPY sql/ /app/sql/
COPY deploy/certs/ /app/certs/
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && pip uninstall -y setuptools wheel && useradd --uid 10001 --create-home obs
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "obs.entrypoint", "--"]
CMD ["uvicorn", "obs.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

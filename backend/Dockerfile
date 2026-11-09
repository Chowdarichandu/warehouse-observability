FROM python:3.11.12-slim-bookworm
WORKDIR /app
COPY backend/ /app/
COPY sql/ /app/sql/
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --create-home obs
USER obs
CMD ["uvicorn","obs.api.main:app","--host","0.0.0.0","--port","8000"]

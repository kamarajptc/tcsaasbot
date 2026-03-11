# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=9100

WORKDIR /app

COPY backend/requirements-prod.txt /app/requirements-prod.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r /app/requirements-prod.txt

COPY backend/app /app/app

RUN mkdir -p /app/artifacts /app/data/qdrant

EXPOSE 9100

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9100}"]

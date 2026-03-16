# syntax=docker/dockerfile:1.4

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ARG PLATFORM_DIR=rentbot_platform

WORKDIR /workspace

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=legacy_src . /workspace
COPY . /workspace/${PLATFORM_DIR}
RUN python -m venv /opt/legacy-venv \
    && /opt/legacy-venv/bin/pip install --no-cache-dir -r /workspace/requirements.txt

WORKDIR /workspace/${PLATFORM_DIR}
RUN pip install --no-cache-dir .

ENV LEGACY_BOT_PYTHON=/opt/legacy-venv/bin/python

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--loop", "uvloop"]

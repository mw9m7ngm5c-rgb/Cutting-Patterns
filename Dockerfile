# The web app in a container, for a cloud host (see docs/DEPLOY_CLOUD.md).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CP_DB=/data/cutting_patterns.db \
    CP_HOST=0.0.0.0 \
    PORT=8000 \
    CP_REQUIRE_LOGIN=1 \
    CP_BEHIND_PROXY=1

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data

EXPOSE 8000
CMD ["python", "-m", "app", "--no-browser"]

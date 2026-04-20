FROM python:3.11-slim

WORKDIR /app

RUN groupadd --system appuser \
    && useradd --system --gid appuser --create-home --home-dir /home/appuser appuser

COPY requirements.txt ./

RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY cyber_dashboard_scheduler ./cyber_dashboard_scheduler

USER appuser

CMD ["python", "-m", "cyber_dashboard_scheduler.main"]
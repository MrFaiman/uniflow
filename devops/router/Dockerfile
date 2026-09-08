FROM python:3.13-slim-trixie

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY router/router.py /app/router.py
COPY config.py /app/config.py
COPY healthcheck.py /app/healthcheck.py

CMD ["python", "-u", "router.py"]
